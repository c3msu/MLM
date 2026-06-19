"""Time-series math helpers extracted from build_dashboard.py (behavior-unchanged,
2026-06-19 全面重构 Phase 1). Pure leaf-level: depend only on stdlib + sources types;
no domain logic. Re-exported by build_dashboard via `from .series_math import *`."""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import median
from typing import Any

from .sources import SeriesPoint, TimeSeries, YieldCurveRecord


def compute_tenor_realized_volatility(records: list[YieldCurveRecord], tenor: str, window: int = 20) -> float:
    ordered = sorted(records, key=lambda item: item.date)
    changes_bp: list[float] = []
    for prior, current in zip(ordered, ordered[1:]):
        if tenor not in prior.values or tenor not in current.values:
            continue
        changes_bp.append((current.values[tenor] - prior.values[tenor]) * 100)
    sample = changes_bp[-window:]
    if len(sample) < 2:
        return 0.0
    mean = sum(sample) / len(sample)
    variance = sum((item - mean) ** 2 for item in sample) / (len(sample) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def historical_percentile(current: float, values: list[float]) -> int | None:
    sample = [value for value in values if math.isfinite(value)]
    if len(sample) < 2:
        return None
    less = sum(1 for value in sample if value < current)
    equal = sum(1 for value in sample if value == current)
    if equal:
        rank = less + (equal - 1) / 2
        denominator = len(sample) - 1
    else:
        rank = less
        denominator = len(sample)
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
    latest = series.latest
    start = window_start(latest.date, years=years)
    values = [point.value for point in series.points if start <= point.date <= latest.date]
    return historical_percentile(latest.value, values)


def point_series_percentile(points: list[SeriesPoint], current: float | None = None, years: int = 5) -> int | None:
    if not points:
        return None
    latest = points[-1]
    start = window_start(latest.date, years=years)
    values = [point.value for point in points if start <= point.date <= latest.date]
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
    ordered = sorted((point for point in points if math.isfinite(point.value)), key=lambda item: item.date)
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
        values = [candidate.value for candidate in ordered[: index + 1] if start <= candidate.date <= point.date]
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
    for point in walcl.points:
        tga_point = tga.value_at_or_before(point.date)
        rrp_point = rrp.value_at_or_before(point.date)
        points.append(SeriesPoint(point.date, point.value - tga_point.value - rrp_point.value))
    return points


def point_change(points: list[SeriesPoint], days: int) -> float:
    if not points:
        return 0.0
    latest = points[-1]
    prior = points[0]
    target = latest.date - timedelta(days=days)
    for point in reversed(points):
        if point.date <= target:
            prior = point
            break
    return latest.value - prior.value


def change_points(points: list[SeriesPoint], days: int) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    for point in points:
        prior = points[0]
        target = point.date - timedelta(days=days)
        for candidate in reversed(points):
            if candidate.date <= target:
                prior = candidate
                break
        if prior.date < point.date:
            rows.append(SeriesPoint(point.date, point.value - prior.value))
    return rows


def spread_points(left: TimeSeries | None, right: TimeSeries | None, multiplier: float = 1.0) -> list[SeriesPoint]:
    if not left or not right:
        return []
    rows: list[SeriesPoint] = []
    for point in left.points:
        right_point = right.value_at_or_before(point.date)
        rows.append(SeriesPoint(point.date, (point.value - right_point.value) * multiplier))
    return rows


def ratio_points(numerator: TimeSeries | None, denominator: TimeSeries | None) -> list[SeriesPoint]:
    if not numerator or not denominator:
        return []
    rows: list[SeriesPoint] = []
    for point in numerator.points:
        denominator_point = denominator.value_at_or_before(point.date)
        if denominator_point.value == 0:
            continue
        rows.append(SeriesPoint(point.date, point.value / denominator_point.value))
    return rows


def weighted_points(left: TimeSeries | None, right: TimeSeries | None, left_weight: float, right_weight: float) -> list[SeriesPoint]:
    if not left or not right:
        return []
    rows: list[SeriesPoint] = []
    for point in left.points:
        right_point = right.value_at_or_before(point.date)
        rows.append(SeriesPoint(point.date, point.value * left_weight + right_point.value * right_weight))
    return rows


def rolling_median_deviation_points(series: TimeSeries | None, *, window_days: int, positive_only: bool = False) -> list[SeriesPoint]:
    if not series:
        return []
    return rolling_median_deviation_points_from_points(series.points, window_days=window_days, positive_only=positive_only)


def rolling_median_deviation_points_from_points(points: list[SeriesPoint], *, window_days: int, positive_only: bool = False) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    ordered = sorted(points, key=lambda item: item.date)
    for index, point in enumerate(ordered):
        start = point.date - timedelta(days=window_days)
        values = [candidate.value for candidate in ordered[: index + 1] if start <= candidate.date <= point.date and math.isfinite(candidate.value)]
        if len(values) < 2:
            continue
        deviation = point.value - median(values)
        rows.append(SeriesPoint(point.date, max(0.0, deviation) if positive_only else deviation))
    return rows


def target_distance_points(series: TimeSeries | None, *, target: float) -> list[SeriesPoint]:
    if not series:
        return []
    return [SeriesPoint(point.date, abs(point.value - target)) for point in series.points if math.isfinite(point.value)]


def curve_spread_points(records: list[YieldCurveRecord], left: str, right: str, *, multiplier: float = 1.0) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    for record in sorted(records, key=lambda item: item.date):
        if left in record.values and right in record.values:
            rows.append(SeriesPoint(record.date, (record.values[left] - record.values[right]) * multiplier))
    return rows


def treasury_curve_curvature_abs_points(records: list[YieldCurveRecord]) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    for record in sorted(records, key=lambda item: item.date):
        if all(tenor in record.values for tenor in ("2Y", "10Y", "30Y")):
            rows.append(SeriesPoint(record.date, abs(record.values["30Y"] - 2 * record.values["10Y"] + record.values["2Y"]) * 100))
    return rows


def curve_realized_volatility_points(records: list[YieldCurveRecord], tenor: str, *, window: int) -> list[SeriesPoint]:
    ordered = sorted(records, key=lambda item: item.date)
    rows: list[SeriesPoint] = []
    changes: list[tuple[date, float]] = []
    for prior, current in zip(ordered, ordered[1:]):
        if tenor not in prior.values or tenor not in current.values:
            continue
        changes.append((current.date, (current.values[tenor] - prior.values[tenor]) * 100))
        sample = [value for _, value in changes[-window:]]
        if len(sample) < 2:
            continue
        mean = sum(sample) / len(sample)
        variance = sum((item - mean) ** 2 for item in sample) / (len(sample) - 1)
        rows.append(SeriesPoint(current.date, math.sqrt(variance) * math.sqrt(252)))
    return rows


def onrrp_buffer_risk_points(series: TimeSeries | None, *, threshold_millions: float = 100_000.0) -> list[SeriesPoint]:
    if not series:
        return []
    rows: list[SeriesPoint] = []
    for point in series.points:
        depletion = max(0.0, min(1.0, (threshold_millions - point.value) / threshold_millions))
        rows.append(SeriesPoint(point.date, depletion**2))
    return rows


def realized_volatility_points(series: TimeSeries | None, *, window: int = 63) -> list[SeriesPoint]:
    if not series:
        return []
    ordered = sorted((point for point in series.points if point.value > 0), key=lambda item: item.date)
    rows: list[SeriesPoint] = []
    returns: list[tuple[date, float]] = []
    for prior, current in zip(ordered, ordered[1:]):
        returns.append((current.date, math.log(current.value / prior.value)))
        sample = [value for _, value in returns[-window:]]
        if len(sample) < 2:
            continue
        mean = sum(sample) / len(sample)
        variance = sum((value - mean) ** 2 for value in sample) / (len(sample) - 1)
        rows.append(SeriesPoint(current.date, math.sqrt(variance) * math.sqrt(252) * 100))
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


def funding_fragmentation_points(
    sofr: TimeSeries | None,
    obfr: TimeSeries | None,
    iorb: TimeSeries | None,
    rrp_award: TimeSeries | None,
    *,
    z_window: int = 252,
    smooth_window: int = 21,
) -> list[SeriesPoint]:
    if not sofr or not obfr or not iorb or not rrp_award:
        return []
    legs: list[tuple[date, float, float, float]] = []
    for point in sofr.points:
        obfr_point = obfr.value_at_or_before(point.date)
        iorb_point = iorb.value_at_or_before(point.date)
        rrp_point = rrp_award.value_at_or_before(point.date)
        legs.append(
            (
                point.date,
                (point.value - obfr_point.value) * 100,
                (point.value - iorb_point.value) * 100,
                (point.value - rrp_point.value) * 100,
            )
        )
    smoothed: list[SeriesPoint] = []
    ema: float | None = None
    alpha = 2 / (smooth_window + 1)
    for index, (point_date, *values) in enumerate(legs):
        z_scores: list[float] = []
        for leg_index, value in enumerate(values):
            sample = [row[leg_index + 1] for row in legs[max(0, index - z_window + 1) : index + 1]]
            if len(sample) < 3:
                z_scores.append(0.0)
                continue
            leg_median = median(sample)
            deviations = [abs(item - leg_median) for item in sample]
            mad = median(deviations)
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
    return sorted((point for point in points if math.isfinite(point.value)), key=lambda item: item.date)


def monthly_last_points(points: list[SeriesPoint], *, start: date) -> list[SeriesPoint]:
    by_month: dict[tuple[int, int], SeriesPoint] = {}
    for point in clean_points(points):
        if point.date < start:
            continue
        by_month[(point.date.year, point.date.month)] = point
    return [by_month[key] for key in sorted(by_month)]


def historical_percentile_at(points: list[SeriesPoint], target: date, *, years: int = 5) -> int | None:
    ordered = clean_points(points)
    current = point_at_or_before(ordered, target)
    if current is None:
        return None
    start = window_start(target, years=years)
    values = [point.value for point in ordered if start <= point.date <= current.date]
    return historical_percentile(current.value, values)


def point_at_or_before(points: list[SeriesPoint], target: date) -> SeriesPoint | None:
    for point in reversed(points):
        if point.date <= target:
            return point
    return None


def point_at_or_after(points: list[SeriesPoint], target: date, *, tolerance_days: int = 10) -> SeriesPoint | None:
    limit = target + timedelta(days=tolerance_days)
    for point in points:
        if target <= point.date <= limit:
            return point
        if point.date > limit:
            break
    return None


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
    future_values = [point.value for point in ordered if current.date < point.date <= end]
    if not future_values:
        return None
    return min(0.0, (min(future_values) / current.value - 1) * 100)
