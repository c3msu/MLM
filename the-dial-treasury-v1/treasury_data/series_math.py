"""Time-series math helpers extracted from build_dashboard.py (behavior-unchanged,
2026-06-19 全面重构 Phase 1). Pure leaf-level: depend only on stdlib + sources types;
no domain logic. Re-exported by build_dashboard via `from .series_math import *`."""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right, insort
from collections import deque
from collections.abc import Iterator
from datetime import date, timedelta
from statistics import median
from typing import Any

from .sources import MarketDailyBar, SeriesPoint, TimeSeries, YieldCurveRecord


class RollingSampleVariance:
    """Numerically stable fixed-size sample variance using Welford add/remove."""

    def __init__(self, window: int):
        self.window = max(1, window)
        self.values: deque[float] = deque()
        self.mean = 0.0
        self.m2 = 0.0

    def append(self, value: float) -> None:
        self.values.append(value)
        count = len(self.values)
        delta = value - self.mean
        self.mean += delta / count
        self.m2 += delta * (value - self.mean)
        if count > self.window:
            self._remove_oldest()

    def _remove_oldest(self) -> None:
        value = self.values.popleft()
        old_count = len(self.values) + 1
        new_count = old_count - 1
        if new_count <= 0:
            self.mean = 0.0
            self.m2 = 0.0
            return
        new_mean = (old_count * self.mean - value) / new_count
        self.m2 -= (value - self.mean) * (value - new_mean)
        self.mean = new_mean
        if self.m2 < 0 and abs(self.m2) < 1e-18:
            self.m2 = 0.0

    @property
    def count(self) -> int:
        return len(self.values)

    def standard_deviation(self) -> float | None:
        if self.count < 2:
            return None
        return math.sqrt(max(0.0, self.m2) / (self.count - 1))


def iter_asof_aligned_points(
    primary: list[SeriesPoint],
    *secondary_series: list[SeriesPoint],
    max_alignment_gap_days: int | None = None,
) -> Iterator[tuple[SeriesPoint, list[SeriesPoint | None]]]:
    """Linearly align sorted series without ever borrowing a future observation.

    Primary dates normally increase. If a caller supplies a regressing primary
    date, the cursors are safely rewound with binary search so behavior remains
    equivalent to independent ``value_at_or_before`` lookups. When
    ``max_alignment_gap_days`` is set, an otherwise valid as-of observation is
    treated as missing once it is older than that many calendar days.
    """
    if max_alignment_gap_days is not None and max_alignment_gap_days < 0:
        raise ValueError("max_alignment_gap_days must be non-negative")
    # TimeSeries canonicalizes its own observations, but this helper is public
    # and also accepts raw lists.  Canonicalize the lookup legs so binary search
    # cannot silently return the wrong row for an unsorted/duplicated date.
    secondary_series = tuple(clean_points(points) for points in secondary_series)
    indices = [-1] * len(secondary_series)
    previous_date: date | None = None
    for primary_point in primary:
        if previous_date is not None and primary_point.date < previous_date:
            indices = [
                bisect_right(points, primary_point.date, key=lambda point: point.date) - 1
                for points in secondary_series
            ]
        else:
            for series_index, points in enumerate(secondary_series):
                point_index = indices[series_index]
                while point_index + 1 < len(points) and points[point_index + 1].date <= primary_point.date:
                    point_index += 1
                indices[series_index] = point_index
        aligned: list[SeriesPoint | None] = []
        for series_index, points in enumerate(secondary_series):
            point_index = indices[series_index]
            aligned_point = points[point_index] if point_index >= 0 else None
            if (
                aligned_point is not None
                and max_alignment_gap_days is not None
                and (primary_point.date - aligned_point.date).days > max_alignment_gap_days
            ):
                aligned_point = None
            aligned.append(aligned_point)
        yield primary_point, aligned
        previous_date = primary_point.date


def compute_tenor_realized_volatility(records: list[YieldCurveRecord], tenor: str, window: int = 20) -> float:
    if window < 2:
        raise ValueError("window must be at least 2")
    ordered = clean_curve_records(records)
    changes_bp: list[float] = []
    for prior, current in zip(ordered, ordered[1:]):
        if (
            tenor not in prior.values
            or tenor not in current.values
            or not math.isfinite(prior.values[tenor])
            or not math.isfinite(current.values[tenor])
        ):
            continue
        changes_bp.append((current.values[tenor] - prior.values[tenor]) * 100)
    sample = changes_bp[-window:]
    if len(sample) < window:
        return 0.0
    mean = sum(sample) / len(sample)
    variance = sum((item - mean) ** 2 for item in sample) / (len(sample) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def historical_percentile(current: float, values: list[float]) -> int | None:
    if not math.isfinite(current):
        return None
    sample_count = 0
    less = 0
    equal = 0
    for value in values:
        if not math.isfinite(value):
            continue
        sample_count += 1
        if value < current:
            less += 1
        elif value == current:
            equal += 1
    if sample_count < 2:
        return None
    if equal:
        rank = less + (equal - 1) / 2
        denominator = sample_count - 1
    else:
        rank = less
        denominator = sample_count
    if denominator <= 0:
        return None
    return max(0, min(100, round((rank / denominator) * 100)))


def window_start(end: date, years: int = 5) -> date:
    try:
        return end.replace(year=end.year - years)
    except ValueError:
        return end.replace(year=end.year - years, day=28)


def series_percentile(series: TimeSeries | None, years: int = 5) -> int | None:
    if not series or not series.points:
        return None
    ordered = clean_points(series.points)
    if not ordered:
        return None
    latest = ordered[-1]
    start = window_start(latest.date, years=years)
    values = [point.value for point in ordered if start <= point.date <= latest.date]
    return historical_percentile(latest.value, values)


def point_series_percentile(points: list[SeriesPoint], current: float | None = None, years: int = 5) -> int | None:
    ordered = clean_points(points)
    if not ordered:
        return None
    latest = ordered[-1]
    start = window_start(latest.date, years=years)
    values = [point.value for point in ordered if start <= point.date <= latest.date]
    return historical_percentile(latest.value if current is None else current, values)


def sampled_indices(length: int, max_points: int) -> list[int]:
    if length <= 0:
        return []
    if length <= max_points:
        return list(range(length))
    if max_points <= 1:
        return [length - 1]
    last = length - 1
    return sorted({round(index * last / (max_points - 1)) for index in range(max_points)})


def historical_percentile_points(
    points: list[SeriesPoint],
    *,
    years: int = 5,
    display_years: int = 3,
    max_points: int = 52,
    value_divisor: float = 1.0,
    value_digits: int = 2,
) -> list[dict[str, Any]]:
    ordered = clean_points(points)
    if not ordered:
        return []
    display_start = window_start(ordered[-1].date, years=display_years)
    visible_indices = [index for index, point in enumerate(ordered) if point.date >= display_start]
    sampled_visible_indices = sampled_indices(len(visible_indices), max_points)
    rows: list[dict[str, Any]] = []
    for visible_index in sampled_visible_indices:
        index = visible_indices[visible_index]
        point = ordered[index]
        start = window_start(point.date, years=years)
        start_index = bisect_left(ordered, start, hi=index + 1, key=lambda candidate: candidate.date)
        values = [candidate.value for candidate in ordered[start_index : index + 1]]
        percentile = historical_percentile(point.value, values)
        if percentile is None:
            continue
        rows.append(
            {
                "date": point.date.isoformat(),
                "value": round(point.value / value_divisor, value_digits),
                "percentile": percentile,
            }
        )
    return rows


def build_net_liquidity_points(fred: dict[str, TimeSeries]) -> list[SeriesPoint]:
    walcl = fred.get("WALCL")
    tga = fred.get("WTREGEN")
    rrp = fred.get("RRPONTSYD")
    if not walcl or not tga or not rrp:
        return []
    points: list[SeriesPoint] = []
    for point, aligned in iter_asof_aligned_points(
        walcl.points,
        tga.points,
        rrp.points,
        max_alignment_gap_days=14,
    ):
        tga_point, rrp_point = aligned
        if tga_point is None or rrp_point is None:
            continue
        # WALCL and WTREGEN are published in $M; RRPONTSYD is published in $B.
        points.append(SeriesPoint(point.date, point.value - tga_point.value - rrp_point.value * 1_000.0))
    return points


def point_change_optional(
    points: list[SeriesPoint],
    days: int,
    *,
    max_target_gap_days: int | None = None,
) -> float | None:
    if days < 0:
        raise ValueError("days must be non-negative")
    if max_target_gap_days is not None and max_target_gap_days < 0:
        raise ValueError("max_target_gap_days must be non-negative")
    ordered = clean_points(points)
    if not ordered:
        return None
    latest = ordered[-1]
    target = latest.date - timedelta(days=days)
    prior = point_at_or_before(ordered, target)
    if prior is None:
        return None
    if max_target_gap_days is not None and (target - prior.date).days > max_target_gap_days:
        return None
    return latest.value - prior.value


def point_change(
    points: list[SeriesPoint],
    days: int,
    *,
    max_target_gap_days: int | None = None,
) -> float:
    value = point_change_optional(points, days, max_target_gap_days=max_target_gap_days)
    return value if value is not None else 0.0


def change_points(
    points: list[SeriesPoint],
    days: int,
    *,
    max_target_gap_days: int | None = None,
) -> list[SeriesPoint]:
    if days < 0:
        raise ValueError("days must be non-negative")
    if max_target_gap_days is not None and max_target_gap_days < 0:
        raise ValueError("max_target_gap_days must be non-negative")
    ordered = clean_points(points)
    rows: list[SeriesPoint] = []
    for point in ordered:
        target = point.date - timedelta(days=days)
        prior = point_at_or_before(ordered, target)
        if prior is not None and (
            max_target_gap_days is None or (target - prior.date).days <= max_target_gap_days
        ):
            rows.append(SeriesPoint(point.date, point.value - prior.value))
    return rows


def spread_points(
    left: TimeSeries | None,
    right: TimeSeries | None,
    multiplier: float = 1.0,
    *,
    max_alignment_gap_days: int = 7,
) -> list[SeriesPoint]:
    if not left or not right:
        return []
    rows: list[SeriesPoint] = []
    for point, aligned in iter_asof_aligned_points(
        left.points,
        right.points,
        max_alignment_gap_days=max_alignment_gap_days,
    ):
        right_point = aligned[0]
        if right_point is None:
            continue
        rows.append(SeriesPoint(point.date, (point.value - right_point.value) * multiplier))
    return rows


def ratio_points(
    numerator: TimeSeries | None,
    denominator: TimeSeries | None,
    *,
    max_alignment_gap_days: int = 7,
) -> list[SeriesPoint]:
    if not numerator or not denominator:
        return []
    rows: list[SeriesPoint] = []
    for point, aligned in iter_asof_aligned_points(
        numerator.points,
        denominator.points,
        max_alignment_gap_days=max_alignment_gap_days,
    ):
        denominator_point = aligned[0]
        if denominator_point is None or denominator_point.value == 0:
            continue
        rows.append(SeriesPoint(point.date, point.value / denominator_point.value))
    return rows


def weighted_points(
    left: TimeSeries | None,
    right: TimeSeries | None,
    left_weight: float,
    right_weight: float,
    *,
    max_alignment_gap_days: int = 7,
) -> list[SeriesPoint]:
    if not left or not right:
        return []
    rows: list[SeriesPoint] = []
    for point, aligned in iter_asof_aligned_points(
        left.points,
        right.points,
        max_alignment_gap_days=max_alignment_gap_days,
    ):
        right_point = aligned[0]
        if right_point is None:
            continue
        rows.append(SeriesPoint(point.date, point.value * left_weight + right_point.value * right_weight))
    return rows


def rolling_median_deviation_points(series: TimeSeries | None, *, window_days: int, positive_only: bool = False) -> list[SeriesPoint]:
    if not series:
        return []
    return rolling_median_deviation_points_from_points(series.points, window_days=window_days, positive_only=positive_only)


def median_from_sorted(values: list[float]) -> float:
    """Median of a non-empty sorted list without copying and sorting it again."""
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def median_absolute_deviation_from_sorted(values: list[float], center: float) -> float:
    """Median absolute deviation in O(n) from an already-sorted value window."""
    if not values:
        raise ValueError("median absolute deviation requires at least one value")
    left = bisect_right(values, center) - 1
    right = left + 1
    lower_rank = (len(values) - 1) // 2
    upper_rank = len(values) // 2
    lower_value = 0.0
    upper_value = 0.0
    for rank in range(upper_rank + 1):
        left_distance = center - values[left] if left >= 0 else math.inf
        right_distance = values[right] - center if right < len(values) else math.inf
        if left_distance <= right_distance:
            selected = left_distance
            left -= 1
        else:
            selected = right_distance
            right += 1
        if rank == lower_rank:
            lower_value = selected
        if rank == upper_rank:
            upper_value = selected
    return (lower_value + upper_value) / 2


def rolling_median_deviation_points_from_points(points: list[SeriesPoint], *, window_days: int, positive_only: bool = False) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    ordered = sorted(points, key=lambda item: item.date)
    sorted_values: list[float] = []
    left_index = 0
    for index, point in enumerate(ordered):
        start = point.date - timedelta(days=window_days)
        while left_index < index and ordered[left_index].date < start:
            stale_value = ordered[left_index].value
            if math.isfinite(stale_value):
                stale_position = bisect_left(sorted_values, stale_value)
                if stale_position < len(sorted_values) and sorted_values[stale_position] == stale_value:
                    sorted_values.pop(stale_position)
            left_index += 1
        if math.isfinite(point.value):
            insort(sorted_values, point.value)
        if len(sorted_values) < 2:
            continue
        deviation = point.value - median_from_sorted(sorted_values)
        rows.append(SeriesPoint(point.date, max(0.0, deviation) if positive_only else deviation))
    return rows


def target_distance_points(series: TimeSeries | None, *, target: float) -> list[SeriesPoint]:
    if not series:
        return []
    return [SeriesPoint(point.date, abs(point.value - target)) for point in series.points if math.isfinite(point.value)]


def curve_spread_points(records: list[YieldCurveRecord], left: str, right: str, *, multiplier: float = 1.0) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    for record in clean_curve_records(records):
        if (
            left in record.values
            and right in record.values
            and math.isfinite(record.values[left])
            and math.isfinite(record.values[right])
        ):
            rows.append(SeriesPoint(record.date, (record.values[left] - record.values[right]) * multiplier))
    return rows


def treasury_curve_curvature_abs_bp(two_year: float, ten_year: float, thirty_year: float) -> float:
    """Absolute 10Y deviation from the linear 2Y-30Y yield chord, in bp.

    The tenors are unevenly spaced, so an unweighted second difference would
    incorrectly treat 2Y, 10Y and 30Y as equidistant observations.
    """
    ten_year_chord = two_year + (10.0 - 2.0) / (30.0 - 2.0) * (thirty_year - two_year)
    return abs(ten_year - ten_year_chord) * 100.0


def treasury_curve_curvature_abs_points(records: list[YieldCurveRecord]) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    for record in clean_curve_records(records):
        if all(
            tenor in record.values and math.isfinite(record.values[tenor])
            for tenor in ("2Y", "10Y", "30Y")
        ):
            rows.append(
                SeriesPoint(
                    record.date,
                    treasury_curve_curvature_abs_bp(
                        record.values["2Y"],
                        record.values["10Y"],
                        record.values["30Y"],
                    ),
                )
            )
    return rows


def curve_realized_volatility_points(records: list[YieldCurveRecord], tenor: str, *, window: int) -> list[SeriesPoint]:
    if window < 2:
        raise ValueError("window must be at least 2")
    ordered = clean_curve_records(records)
    rows: list[SeriesPoint] = []
    rolling = RollingSampleVariance(window)
    for prior, current in zip(ordered, ordered[1:]):
        if (
            tenor not in prior.values
            or tenor not in current.values
            or not math.isfinite(prior.values[tenor])
            or not math.isfinite(current.values[tenor])
        ):
            continue
        rolling.append((current.values[tenor] - prior.values[tenor]) * 100)
        if rolling.count < window:
            continue
        standard_deviation = rolling.standard_deviation()
        if standard_deviation is None:
            continue
        rows.append(SeriesPoint(current.date, standard_deviation * math.sqrt(252)))
    return rows


def onrrp_buffer_risk_points(series: TimeSeries | None, *, threshold_billions: float = 100.0) -> list[SeriesPoint]:
    if not series:
        return []
    if threshold_billions <= 0:
        raise ValueError("threshold_billions must be positive")
    rows: list[SeriesPoint] = []
    for point in series.points:
        depletion = max(0.0, min(1.0, (threshold_billions - point.value) / threshold_billions))
        rows.append(SeriesPoint(point.date, depletion**2))
    return rows


def realized_volatility_points(series: TimeSeries | None, *, window: int = 63) -> list[SeriesPoint]:
    if not series or window < 2:
        return []
    ordered = [point for point in clean_points(series.points) if point.value > 0]
    rows: list[SeriesPoint] = []
    rolling = RollingSampleVariance(window)
    for prior, current in zip(ordered, ordered[1:]):
        rolling.append(math.log(current.value / prior.value))
        if rolling.count < window:
            continue
        standard_deviation = rolling.standard_deviation()
        if standard_deviation is None:
            continue
        rows.append(SeriesPoint(current.date, standard_deviation * math.sqrt(252) * 100))
    return rows


def treasury_price_proxy_from_yield_points(series: TimeSeries | None, *, duration: float = 8.0) -> list[SeriesPoint]:
    if not series:
        return []
    rows: list[SeriesPoint] = []
    for point in series.points:
        if not math.isfinite(point.value):
            continue
        rows.append(SeriesPoint(point.date, 100 * math.exp(-duration * point.value / 100)))
    return rows


def rolling_relative_return_points(
    numerator: TimeSeries | None,
    denominator: TimeSeries | None,
    *,
    window: int = 63,
    max_alignment_gap_days: int = 10,
) -> list[SeriesPoint]:
    """Relative total-return change over a fixed observation window.

    This avoids dividing a cumulative equity/credit index level by the level of
    a duration-derived Treasury price proxy, which creates a mechanically
    trending non-stationary ratio.  The proxy is still approximate (it omits
    carry), but its *change* over the same window is economically comparable.
    """
    if not numerator or not denominator or window < 1:
        return []
    ordered = [point for point in clean_points(numerator.points) if point.value > 0]
    rows: list[SeriesPoint] = []
    for index in range(window, len(ordered)):
        current = ordered[index]
        prior = ordered[index - window]
        current_denominator = denominator.value_at_or_before(current.date)
        prior_denominator = denominator.value_at_or_before(prior.date)
        if current_denominator is None or prior_denominator is None:
            continue
        if (current.date - current_denominator.date).days > max_alignment_gap_days:
            continue
        if (prior.date - prior_denominator.date).days > max_alignment_gap_days:
            continue
        if current_denominator.value <= 0 or prior_denominator.value <= 0:
            continue
        numerator_return = current.value / prior.value
        denominator_return = current_denominator.value / prior_denominator.value
        if denominator_return <= 0:
            continue
        rows.append(SeriesPoint(current.date, (numerator_return / denominator_return - 1.0) * 100.0))
    return rows


def blended_relative_return_points(
    numerator: TimeSeries | None,
    denominator: TimeSeries | None,
    *,
    windows: tuple[int, ...] = (63, 126),
) -> list[SeriesPoint]:
    """Average aligned rolling relative returns across all requested horizons."""
    clean_windows = tuple(sorted({int(window) for window in windows if int(window) > 0}))
    if not clean_windows:
        return []
    series_by_window = [
        {point.date: point.value for point in rolling_relative_return_points(numerator, denominator, window=window)}
        for window in clean_windows
    ]
    if not series_by_window or any(not rows for rows in series_by_window):
        return []
    common_dates = set(series_by_window[0])
    for rows in series_by_window[1:]:
        common_dates.intersection_update(rows)
    return [
        SeriesPoint(point_date, sum(rows[point_date] for rows in series_by_window) / len(series_by_window))
        for point_date in sorted(common_dates)
    ]


def funding_fragmentation_points(
    sofr: TimeSeries | None,
    obfr: TimeSeries | None,
    iorb: TimeSeries | None,
    rrp_award: TimeSeries | None,
    *,
    z_window: int = 252,
    smooth_window: int = 21,
    max_alignment_gap_days: int = 7,
) -> list[SeriesPoint]:
    if not sofr or not obfr or not iorb or not rrp_award:
        return []
    legs: list[tuple[date, float, float, float]] = []
    for point, aligned in iter_asof_aligned_points(
        sofr.points,
        obfr.points,
        iorb.points,
        rrp_award.points,
        max_alignment_gap_days=max_alignment_gap_days,
    ):
        obfr_point, iorb_point, rrp_point = aligned
        if obfr_point is None or iorb_point is None or rrp_point is None:
            continue
        legs.append(
            (
                point.date,
                (point.value - obfr_point.value) * 100,
                (point.value - iorb_point.value) * 100,
                (point.value - rrp_point.value) * 100,
            )
        )
    smoothed: list[SeriesPoint] = []
    rolling_leg_values: list[list[float]] = [[], [], []]
    ema: float | None = None
    alpha = 2 / (smooth_window + 1)
    for index, (point_date, *values) in enumerate(legs):
        if z_window > 0:
            for leg_index, value in enumerate(values):
                insort(rolling_leg_values[leg_index], value)
            if index >= z_window:
                stale = legs[index - z_window]
                for leg_index, stale_value in enumerate(stale[1:]):
                    stale_position = bisect_left(rolling_leg_values[leg_index], stale_value)
                    rolling_leg_values[leg_index].pop(stale_position)
        z_scores: list[float] = []
        for leg_index, value in enumerate(values):
            sample = rolling_leg_values[leg_index]
            if len(sample) < 3:
                z_scores.append(0.0)
                continue
            leg_median = median_from_sorted(sample)
            mad = median_absolute_deviation_from_sorted(sample, leg_median)
            z_scores.append(0.0 if mad == 0 else (value - leg_median) / (mad * 1.4826))
        mean_z = sum(z_scores) / len(z_scores)
        dispersion = math.sqrt(sum((value - mean_z) ** 2 for value in z_scores) / len(z_scores))
        ema = dispersion if ema is None else alpha * dispersion + (1 - alpha) * ema
        smoothed.append(SeriesPoint(point_date, ema))
    return smoothed


def latest_point_value(points: list[SeriesPoint], default: float = 0.0) -> float:
    return points[-1].value if points else default


def percentile_label(value: int | None) -> str:
    return f"历史p{value}" if value is not None else "历史p--"


def latest_value(fred: dict[str, TimeSeries], series_id: str, default: float = 0.0) -> float:
    series = fred.get(series_id)
    if not series:
        return default
    return series.latest.value


# --- Point-list series helpers + scoring math (2026-06-19 Phase 1: pushed down from
# build_dashboard so the scoring domains depend on this leaf layer, not the monolith) ---


def score_from_percentile(percentile: int | None, direction: str) -> float:
    if percentile is None:
        return 50.0
    if direction == "lower_better":
        return float(100 - percentile)
    return float(percentile)


def monthly_score_dates(series: dict[str, list[SeriesPoint]], keys: list[str], target: date, *, years: int = 5) -> list[date]:
    start = window_start(target, years=years)
    month_ends: dict[tuple[int, int], date] = {}
    for key in keys:
        for point in clean_points(series.get(key, [])):
            if start <= point.date <= target:
                month_ends[(point.date.year, point.date.month)] = max(month_ends.get((point.date.year, point.date.month), point.date), point.date)
    return [month_ends[key] for key in sorted(month_ends)]


def clean_points(points: list[SeriesPoint]) -> list[SeriesPoint]:
    """Return finite observations at a unique, ascending daily grain.

    A repeated date is a revision/duplicate, not another statistical sample.
    Retaining the last row matches feed and cache overwrite semantics.
    """
    by_date: dict[date, SeriesPoint] = {}
    for point in points:
        if math.isfinite(point.value):
            by_date[point.date] = point
    return [by_date[point_date] for point_date in sorted(by_date)]


def clean_curve_records(records: list[YieldCurveRecord]) -> list[YieldCurveRecord]:
    """Return one ascending curve record per date, keeping the last revision."""
    by_date: dict[date, YieldCurveRecord] = {}
    for record in records:
        by_date[record.date] = record
    return [by_date[record_date] for record_date in sorted(by_date)]


def monthly_last_points(points: list[SeriesPoint], *, start: date) -> list[SeriesPoint]:
    by_month: dict[tuple[int, int], SeriesPoint] = {}
    for point in clean_points(points):
        if point.date < start:
            continue
        by_month[(point.date.year, point.date.month)] = point
    return [by_month[key] for key in sorted(by_month)]


def historical_percentile_at(points: list[SeriesPoint], target: date, *, years: int = 5) -> int | None:
    ordered = clean_points(points)
    return historical_percentile_at_ordered(ordered, target, years=years)


def historical_percentile_at_ordered(points: list[SeriesPoint], target: date, *, years: int = 5) -> int | None:
    """Return an as-of percentile for an already-clean, date-ordered point list.

    Hot scoring paths prepare their source series once and call this helper many
    times. Keeping the ordering contract explicit avoids silently re-sorting the
    same five-year history for every factor and every monthly EMA observation.
    """
    percentile, _ = historical_percentile_with_sample_count_at_ordered(points, target, years=years)
    return percentile


def historical_percentile_with_sample_count_at_ordered(
    points: list[SeriesPoint],
    target: date,
    *,
    years: int = 5,
) -> tuple[int | None, int]:
    """Return an as-of percentile together with its effective trailing sample.

    The count is kept separate from the percentile so domain scorers can apply
    an explicit warm-up contract instead of interpreting a two-point p0/p100 as
    mature evidence. ``points`` must already be finite and date ordered.
    """
    current_index = bisect_right(points, target, key=lambda point: point.date) - 1
    if current_index < 0:
        return None, 0
    start = window_start(target, years=years)
    start_index = bisect_left(points, start, hi=current_index + 1, key=lambda point: point.date)
    current = points[current_index]
    values = [point.value for point in points[start_index : current_index + 1]]
    return historical_percentile(current.value, values), len(values)


def point_at_or_before(points: list[SeriesPoint], target: date) -> SeriesPoint | None:
    index = bisect_right(points, target, key=lambda point: point.date) - 1
    return points[index] if index >= 0 else None


def point_at_or_after(points: list[SeriesPoint], target: date, *, tolerance_days: int = 10) -> SeriesPoint | None:
    limit = target + timedelta(days=tolerance_days)
    index = bisect_left(points, target, key=lambda point: point.date)
    if index >= len(points) or points[index].date > limit:
        return None
    return points[index]


def forward_return_pct(points: list[SeriesPoint], start: date, *, days: int) -> float | None:
    ordered = clean_points(points)
    current = point_at_or_before(ordered, start)
    future = point_at_or_after(ordered, start + timedelta(days=days))
    if current is None or future is None or current.value == 0:
        return None
    return (future.value / current.value - 1) * 100


def forward_max_drawdown_pct(points: list[SeriesPoint], start: date, *, days: int) -> float | None:
    ordered = clean_points(points)
    current = point_at_or_before(ordered, start)
    if current is None or current.value == 0:
        return None
    end = start + timedelta(days=days)
    endpoint = point_at_or_after(ordered, end)
    if endpoint is None:
        return None
    future_values = [point.value for point in ordered if current.date < point.date <= endpoint.date]
    if not future_values:
        return None
    return min(0.0, (min(future_values) / current.value - 1) * 100)


# --- Market-bar (OHLCV) helpers (Phase 1: used by equity/lppl/regional) ---


def bar_index_at_or_before(bars: list[MarketDailyBar], target: date) -> int | None:
    index = bisect_right(bars, target, key=lambda bar: bar.date) - 1
    return index if index >= 0 else None


def bar_at_or_before(bars: list[MarketDailyBar], target: date) -> MarketDailyBar | None:
    index = bar_index_at_or_before(bars, target)
    return bars[index] if index is not None else None


def trailing_return(bars: list[MarketDailyBar], target: date, lookback: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None or lookback <= 0 or index < lookback:
        return None
    prior_index = index - lookback
    prior = bars[prior_index]
    current = bars[index]
    if prior.close <= 0:
        return None
    return current.close / prior.close - 1


def moving_average_gap(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None or index + 1 < window:
        return None
    sample = bars[index - window + 1: index + 1]
    average_close = sum(bar.close for bar in sample) / len(sample)
    if average_close <= 0:
        return None
    return bars[index].close / average_close - 1


def drawdown_from_recent_high(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None:
        return None
    sample = bars[max(0, index - window + 1): index + 1]
    if not sample:
        return None
    recent_high = max(bar.high for bar in sample)
    if recent_high <= 0:
        return None
    return bars[index].close / recent_high - 1


def high_to_low_drawdown_in_window(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None:
        return None
    sample = bars[max(0, index - window + 1): index + 1]
    if not sample:
        return None
    running_high: float | None = None
    worst_drawdown = 0.0
    has_ordered_pair = False
    for bar in sample:
        # A running peak prevents an earlier low from being paired with a later
        # high. With daily OHLC data, a same-session high/low pair is admissible.
        if bar.high > 0:
            running_high = bar.high if running_high is None else max(running_high, bar.high)
        if running_high is not None and bar.low > 0:
            has_ordered_pair = True
            worst_drawdown = min(worst_drawdown, bar.low / running_high - 1.0)
    return worst_drawdown if has_ordered_pair else None


def rebound_from_recent_low(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None:
        return None
    sample = bars[max(0, index - window + 1): index + 1]
    if not sample:
        return None
    recent_low = min(bar.low for bar in sample)
    if recent_low <= 0:
        return None
    return bars[index].close / recent_low - 1


def one_day_return(bars: list[MarketDailyBar], target: date) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None or index <= 0:
        return None
    prior = bars[index - 1]
    current = bars[index]
    if prior.close <= 0:
        return None
    return current.close / prior.close - 1


def close_location_value(bar: MarketDailyBar) -> float:
    if bar.high <= bar.low:
        return 0.5
    return max(0.0, min(1.0, (bar.close - bar.low) / (bar.high - bar.low)))


def volume_percentile_at(bars: list[MarketDailyBar], target: date, *, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None or window <= 0:
        return None
    current_volume = bars[index].volume
    if current_volume is None:
        return None
    sample = [
        bar.volume
        for bar in bars[max(0, index - window + 1): index + 1]
        if bar.volume is not None
    ]
    if len(sample) < 10:
        return None
    percentile = historical_percentile(float(current_volume), [float(value) for value in sample])
    return float(percentile) if percentile is not None else None
