"""Walk-forward signal validation utilities.

Pure-Python (no numpy) helpers that evaluate any score series against forward
S&P 500 returns: out-of-sample information coefficients, hit rate vs base rate,
lead time to drawdown troughs, lead/lag classification, redundancy clusters,
and redundancy-adjusted effective weights. Thresholds are always chosen on the
calibration slice only; the evaluation slice is never used for tuning.
"""

from __future__ import annotations

import math
import random
from bisect import bisect_left, bisect_right
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable

from .dashboard_core import SIGNAL_VALIDATION_DRAWDOWN_DAYS, SIGNAL_VALIDATION_DRAWDOWN_PCT, SIGNAL_VALIDATION_OOS_SPLIT
from .sources import SeriesPoint

DEFAULT_OOS_SPLIT = 0.65
DEFAULT_HORIZON_DAYS = (7, 30, 91)
DEFAULT_BOOTSTRAP_SEED = 20260612
MIN_IC_OBSERVATIONS = 8
FORWARD_POINT_TOLERANCE_DAYS = 10
ALERT_EPISODE_GAP_DAYS = 14
DEFAULT_FDR_ALPHA = 0.10


def window_start(end: date, years: int = 5) -> date:
    try:
        return end.replace(year=end.year - years)
    except ValueError:
        return end.replace(year=end.year - years, day=28)


def rank_percentile(current: float, values: list[float]) -> int | None:
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


class SortedSeries:
    """Pre-sorted (dates, values) view of a point series for fast as-of lookups."""

    __slots__ = ("dates", "values")

    def __init__(self, points: Iterable[SeriesPoint]):
        cleaned = sorted(
            ((point.date, point.value) for point in points if math.isfinite(point.value)),
            key=lambda item: item[0],
        )
        self.dates: list[date] = [item[0] for item in cleaned]
        self.values: list[float] = [item[1] for item in cleaned]

    def __len__(self) -> int:
        return len(self.dates)

    def index_at_or_before(self, target: date) -> int | None:
        index = bisect_right(self.dates, target) - 1
        return index if index >= 0 else None

    def value_at_or_before(self, target: date) -> float | None:
        index = self.index_at_or_before(target)
        return self.values[index] if index is not None else None

    def value_at_or_after(self, target: date, *, tolerance_days: int = FORWARD_POINT_TOLERANCE_DAYS) -> float | None:
        index = self.index_at_or_after(target, tolerance_days=tolerance_days)
        return self.values[index] if index is not None else None

    def index_at_or_after(self, target: date, *, tolerance_days: int = FORWARD_POINT_TOLERANCE_DAYS) -> int | None:
        """Return the first observation on/after ``target`` within tolerance.

        Forward labels use this as their completeness gate.  Requiring the
        calendar-horizon endpoint prevents a one-day tail from being silently
        reported as a complete 3M outcome while still allowing weekends and
        market holidays to roll to the next available close.
        """
        index = bisect_left(self.dates, target)
        if index >= len(self.dates):
            return None
        if self.dates[index] > target + timedelta(days=tolerance_days):
            return None
        return index

    def percentile_with_sample_count_at(
        self,
        target: date,
        *,
        years: int = 5,
    ) -> tuple[int | None, int]:
        """Return the trailing percentile and its finite point count as of ``target``.

        Validation replays need the count as well as the percentile so they can
        apply the same explicit warm-up gate as the live Conditions scorer.  The
        lookup stays point-in-time: neither the current value nor the trailing
        sample can include an observation dated after ``target``.
        """
        end_index = self.index_at_or_before(target)
        if end_index is None:
            return None, 0
        start_index = bisect_left(self.dates, window_start(target, years=years))
        if start_index > end_index:
            start_index = end_index
        sample = self.values[start_index : end_index + 1]
        return rank_percentile(self.values[end_index], sample), len(sample)

    def percentile_at(self, target: date, *, years: int = 5) -> int | None:
        percentile, _ = self.percentile_with_sample_count_at(target, years=years)
        return percentile

    def forward_return_pct(self, start: date, *, days: int) -> float | None:
        current = self.value_at_or_before(start)
        future = self.value_at_or_after(start + timedelta(days=days))
        if current is None or future is None or current == 0:
            return None
        return (future / current - 1) * 100

    def forward_max_drawdown_pct(self, start: date, *, days: int) -> float | None:
        start_index = self.index_at_or_before(start)
        if start_index is None or self.values[start_index] == 0:
            return None
        end = start + timedelta(days=days)
        endpoint_index = self.index_at_or_after(end)
        if endpoint_index is None or endpoint_index <= start_index:
            return None
        future_values = self.values[start_index + 1 : endpoint_index + 1]
        if not future_values:
            return None
        return min(0.0, (min(future_values) / self.values[start_index] - 1) * 100)

    def forward_trough_date(self, start: date, *, days: int) -> date | None:
        start_index = self.index_at_or_before(start)
        if start_index is None:
            return None
        end = start + timedelta(days=days)
        endpoint_index = self.index_at_or_after(end)
        if endpoint_index is None or endpoint_index <= start_index:
            return None
        window = range(start_index + 1, endpoint_index + 1)
        if not window:
            return None
        trough_index = min(window, key=lambda index: self.values[index])
        return self.dates[trough_index]


def weekly_dates(price_points: list[SeriesPoint], *, years: int = 5) -> list[date]:
    series = SortedSeries(price_points)
    if not series.dates:
        return []
    start = window_start(series.dates[-1], years=years)
    by_week: dict[tuple[int, int], date] = {}
    for point_date in series.dates:
        if point_date < start:
            continue
        iso = point_date.isocalendar()
        key = (iso[0], iso[1])
        existing = by_week.get(key)
        if existing is None or point_date > existing:
            by_week[key] = point_date
    return [by_week[key] for key in sorted(by_week)]


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        tail = position
        while tail + 1 < len(order) and values[order[tail + 1]] == values[order[position]]:
            tail += 1
        shared_rank = (position + tail) / 2 + 1
        for cursor in range(position, tail + 1):
            ranks[order[cursor]] = shared_rank
        position = tail + 1
    return ranks


def pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    count = len(xs)
    if count < 3 or count != len(ys):
        return None
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    if variance_x <= 0 or variance_y <= 0:
        return None
    return covariance / math.sqrt(variance_x * variance_y)


def finite_pairs(signal_values: list[float | None], forward_returns: list[float | None]) -> list[tuple[float, float]]:
    return [
        (signal, forward)
        for signal, forward in zip(signal_values, forward_returns)
        if signal is not None
        and forward is not None
        and math.isfinite(signal)
        and math.isfinite(forward)
    ]


def spearman_ic(signal_values: list[float | None], forward_returns: list[float | None], *, min_observations: int = MIN_IC_OBSERVATIONS) -> float | None:
    pairs = finite_pairs(signal_values, forward_returns)
    if len(pairs) < min_observations:
        return None
    return pearson_correlation(average_ranks([pair[0] for pair in pairs]), average_ranks([pair[1] for pair in pairs]))


def approximate_correlation_p_value(correlation: float | None, sample_size: int) -> float | None:
    """Two-sided large-sample p-value used only for multiple-test diagnostics.

    The bootstrap interval remains the primary uncertainty estimate.  Fisher's
    z approximation gives the factor family a common statistic for BH/FDR
    correction without introducing a heavy scientific-Python dependency.
    """
    if correlation is None or sample_size < 4 or not math.isfinite(correlation):
        return None
    bounded = max(-0.999999, min(0.999999, float(correlation)))
    z_score = abs(math.atanh(bounded)) * math.sqrt(sample_size - 3)
    return max(0.0, min(1.0, math.erfc(z_score / math.sqrt(2.0))))


def apply_benjamini_hochberg(
    rows: list[dict[str, Any]],
    *,
    p_key: str = "pValue3m",
    alpha: float = DEFAULT_FDR_ALPHA,
    family_size: int | None = None,
) -> None:
    """Attach monotone BH q-values and a conservative actionable verdict.

    ``family_size`` is the pre-registered hypothesis count.  It may exceed the
    number of reportable rows when one or more inputs lack enough history; those
    unavailable hypotheses remain in the multiplicity denominator as implicit
    p-values of one instead of shrinking the family after observing coverage.
    """
    indexed = []
    missing_p_value: set[int] = set()
    for index, row in enumerate(rows):
        raw_p_value = row.get(p_key)
        if isinstance(raw_p_value, (int, float)) and math.isfinite(float(raw_p_value)):
            p_value = max(0.0, min(1.0, float(raw_p_value)))
        else:
            # The family is pre-registered.  An unavailable test remains in its
            # multiplicity denominator as p=1 instead of making the remaining
            # rows look more significant by shrinking the family post hoc.
            p_value = 1.0
            missing_p_value.add(index)
        indexed.append((index, p_value))
    ranked = sorted(indexed, key=lambda item: item[1])
    count = max(len(ranked), int(family_size or 0))
    adjusted: dict[int, float] = {}
    running = 1.0
    # Implicit unavailable hypotheses all have p=1 and sort after the reported
    # rows, so they initialize the reverse monotonic pass at one without
    # needing materialized placeholder rows.
    for rank_index in range(len(ranked) - 1, -1, -1):
        original_index, p_value = ranked[rank_index]
        rank = rank_index + 1
        running = min(running, p_value * count / rank)
        adjusted[original_index] = max(0.0, min(1.0, running))
    for index, row in enumerate(rows):
        q_value = adjusted.get(index)
        row["fdrFamilySize"] = count
        row["fdrAlpha"] = alpha
        row["fdrQValue3m"] = round(q_value, 4) if q_value is not None else None
        row["fdrSignificant3m"] = bool(
            index not in missing_p_value
            and q_value is not None
            and q_value <= alpha
        )
        fold_stability = row.get("foldStability3m") if isinstance(row.get("foldStability3m"), dict) else {}
        row["actionableRobust"] = bool(
            row.get("robust")
            and row["fdrSignificant3m"]
            and fold_stability.get("stablePositive")
        )


def fold_ic_stability(
    signal_points: list[SeriesPoint],
    price_points: list[SeriesPoint],
    *,
    horizon_days: int = 91,
    direction: str = "higher_risk",
    folds: int = 3,
    initial_fraction: float = DEFAULT_OOS_SPLIT,
    oos_start_date: date | None = None,
) -> dict[str, Any]:
    """Report contiguous evaluation-fold stability for a fixed signal definition.

    This is deliberately labelled a stability diagnostic, not an independent
    holdout: factor definitions and weights may have been informed by earlier
    research.  Each fold is evaluated separately so one favorable tail slice
    cannot hide sign reversals.
    """
    signal = SortedSeries(signal_points)
    prices = SortedSeries(price_points)
    observations = [
        (signal_date, signal_value, prices.forward_return_pct(signal_date, days=horizon_days))
        for signal_date, signal_value in zip(signal.dates, signal.values)
    ]
    observations = [row for row in observations if row[2] is not None and math.isfinite(float(row[2]))]
    if len(observations) < MIN_IC_OBSERVATIONS * 2:
        return {"available": False, "reason": "sample too small", "folds": []}
    if oos_start_date is None:
        start = max(MIN_IC_OBSERVATIONS, int(len(observations) * initial_fraction))
    else:
        start = bisect_left([row[0] for row in observations], oos_start_date)
    evaluation = observations[start:]
    if len(evaluation) < MIN_IC_OBSERVATIONS:
        return {"available": False, "reason": "evaluation sample too small", "folds": []}
    fold_count = max(2, min(folds, len(evaluation) // MIN_IC_OBSERVATIONS))
    base_size, remainder = divmod(len(evaluation), fold_count)
    cursor = 0
    fold_rows: list[dict[str, Any]] = []
    for index in range(fold_count):
        size = base_size + (1 if index < remainder else 0)
        sample = evaluation[cursor : cursor + size]
        cursor += size
        raw_ic = spearman_ic([row[1] for row in sample], [row[2] for row in sample])
        oriented = oriented_ic(raw_ic, direction)
        fold_rows.append(
            {
                "fold": index + 1,
                "start": sample[0][0].isoformat(),
                "end": sample[-1][0].isoformat(),
                "sampleSize": len(sample),
                "ic": round_optional(oriented),
            }
        )
    finite_ics = [float(row["ic"]) for row in fold_rows if row.get("ic") is not None]
    if not finite_ics:
        return {"available": False, "reason": "fold IC unavailable", "folds": fold_rows}
    positive = sum(1 for value in finite_ics if value > 0)
    sign_consistency = positive / len(finite_ics)
    return {
        "available": True,
        "horizonDays": horizon_days,
        "oosStartDate": oos_start_date.isoformat() if oos_start_date is not None else evaluation[0][0].isoformat(),
        "initialResearchPct": round(start / len(observations) * 100, 1),
        "foldCount": len(finite_ics),
        "medianIc": round_optional(float(median(finite_ics))),
        "worstIc": round_optional(min(finite_ics)),
        "positiveFoldPct": round(sign_consistency * 100, 1),
        "stablePositive": bool(
            len(finite_ics) >= 2
            and median(finite_ics) > 0
            and positive == len(finite_ics)
        ),
        "folds": fold_rows,
    }


def block_bootstrap_ci(
    pairs: list[tuple[float, float]],
    *,
    block_len: int,
    n_boot: int = 500,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    alpha: float = 0.10,
) -> tuple[float, float] | None:
    count = len(pairs)
    if count < 12 or block_len < 1:
        return None
    block_len = min(block_len, count)
    rng = random.Random(seed)
    max_start = count - block_len
    blocks_needed = math.ceil(count / block_len)
    statistics: list[float] = []
    for _ in range(n_boot):
        sample: list[tuple[float, float]] = []
        for _ in range(blocks_needed):
            start = rng.randint(0, max_start)
            sample.extend(pairs[start : start + block_len])
        sample = sample[:count]
        ic = spearman_ic([pair[0] for pair in sample], [pair[1] for pair in sample])
        if ic is not None:
            statistics.append(ic)
    if len(statistics) < n_boot // 2:
        return None
    statistics.sort()
    low_index = int(len(statistics) * (alpha / 2))
    high_index = min(len(statistics) - 1, int(len(statistics) * (1 - alpha / 2)))
    return (statistics[low_index], statistics[high_index])


def oriented_ic(raw_ic: float | None, direction: str) -> float | None:
    if raw_ic is None:
        return None
    return -raw_ic if direction == "higher_risk" else raw_ic


def oriented_interval(interval: tuple[float, float], direction: str) -> list[float | None]:
    """Orient a raw (low, high) IC interval to the convention where positive = predictive,
    swapping the bounds when the orientation negates (higher_risk)."""
    if direction == "higher_risk":
        low, high = oriented_ic(interval[1], direction), oriented_ic(interval[0], direction)
    else:
        low, high = interval
    return [round_optional(low), round_optional(high)]


REGIME_TRAIL_DAYS = 63  # ~3M trailing SPX return defines the up/down-market regime


def regime_conditional_split(
    observations: list[dict[str, Any]],
    forward_key: str,
    prices: "SortedSeries",
    *,
    direction: str,
    block_len: int,
    trail_days: int = REGIME_TRAIL_DAYS,
) -> dict[str, Any] | None:
    """Split observations by market-trend regime (sign of the trailing `trail_days` SPX
    return at each signal date, exogenous to the macro factors) and compute the oriented
    forward IC + block-bootstrap CI within each regime. Sub-samples are small so the CIs
    are wide — exploratory. The point: surface whether a factor's predictive DIRECTION holds
    across up- and down-markets or is regime-specific (a sign flip between regimes is a
    robustness red flag even when the pooled IC looks strong)."""
    up_pairs: list[tuple[float, float]] = []
    down_pairs: list[tuple[float, float]] = []
    for row in observations:
        signal_value = row.get("signal")
        forward_value = row.get(forward_key)
        if signal_value is None or forward_value is None:
            continue
        if not (math.isfinite(signal_value) and math.isfinite(forward_value)):
            continue
        signal_date = row["date"]
        now = prices.value_at_or_before(signal_date)
        past = prices.value_at_or_before(signal_date - timedelta(days=trail_days))
        if now is None or past is None or past == 0:
            continue
        bucket = up_pairs if (now / past - 1) >= 0 else down_pairs
        bucket.append((signal_value, forward_value))

    def regime_block(pairs: list[tuple[float, float]]) -> dict[str, Any]:
        n = len(pairs)
        if n < MIN_IC_OBSERVATIONS:
            return {"ic": None, "ci": None, "n": n}
        ic = oriented_ic(spearman_ic([pair[0] for pair in pairs], [pair[1] for pair in pairs]), direction)
        ci = None
        if n >= 12:
            raw = block_bootstrap_ci(pairs, block_len=max(1, min(block_len, n // 2)))
            if raw is not None:
                ci = oriented_interval(raw, direction)
        return {"ic": round_optional(ic), "ci": ci, "n": n}

    up = regime_block(up_pairs)
    down = regime_block(down_pairs)
    if up["ic"] is None and down["ic"] is None:
        return None
    sign_consistent: bool | None = None
    if up["ic"] is not None and down["ic"] is not None:
        sign_consistent = (up["ic"] > 0) == (down["ic"] > 0)
    return {"upMarket": up, "downMarket": down, "signConsistent": sign_consistent}


def percentile_threshold(values: list[float], percentile: float) -> float | None:
    finite = sorted(value for value in values if math.isfinite(value))
    if not finite:
        return None
    position = max(0, min(len(finite) - 1, int(round((percentile / 100) * (len(finite) - 1)))))
    return finite[position]


def typical_spacing_days(dates: list[date]) -> float:
    gaps = [(later - earlier).days for earlier, later in zip(dates, dates[1:]) if (later - earlier).days > 0]
    return float(median(gaps)) if gaps else 7.0


def evaluate_signal(
    signal_points: list[SeriesPoint],
    price_points: list[SeriesPoint],
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZON_DAYS,
    oos_split: float = DEFAULT_OOS_SPLIT,
    direction: str = "higher_risk",
    drawdown_threshold_pct: float = -5.0,
    drawdown_horizon_days: int = 91,
    alert_percentile: float = 80.0,
    bootstrap_horizon_days: int = 91,
    oos_start_date: date | None = None,
) -> dict[str, Any]:
    signal = SortedSeries(signal_points)
    prices = SortedSeries(price_points)
    if len(signal) < MIN_IC_OBSERVATIONS or len(prices) < MIN_IC_OBSERVATIONS:
        return {"available": False, "reason": "signal or price sample too small"}

    observations: list[dict[str, Any]] = []
    for index, signal_date in enumerate(signal.dates):
        row: dict[str, Any] = {"date": signal_date, "signal": signal.values[index]}
        for horizon in horizons:
            row[f"forward{horizon}"] = prices.forward_return_pct(signal_date, days=horizon)
        row["forwardDrawdown"] = prices.forward_max_drawdown_pct(signal_date, days=drawdown_horizon_days)
        observations.append(row)

    if oos_start_date is None:
        split_index = max(1, min(len(observations) - 1, int(len(observations) * oos_split)))
    else:
        split_index = bisect_left(signal.dates, oos_start_date)
    calibration = observations[:split_index]
    evaluation = observations[split_index:]

    horizon_rows: list[dict[str, Any]] = []
    for horizon in horizons:
        key = f"forward{horizon}"
        full_pairs = finite_pairs([row["signal"] for row in observations], [row[key] for row in observations])
        calibration_pairs = finite_pairs([row["signal"] for row in calibration], [row[key] for row in calibration])
        oos_pairs = finite_pairs([row["signal"] for row in evaluation], [row[key] for row in evaluation])
        raw_full = spearman_ic([row[0] for row in full_pairs], [row[1] for row in full_pairs])
        raw_calibration = spearman_ic([row[0] for row in calibration_pairs], [row[1] for row in calibration_pairs])
        raw_oos = spearman_ic([row[0] for row in oos_pairs], [row[1] for row in oos_pairs])
        spacing = typical_spacing_days(signal.dates)
        overlap_block_len = max(1, int(round(horizon / max(spacing, 1.0))))
        horizon_row: dict[str, Any] = {
            "days": horizon,
            "ic": round_optional(oriented_ic(raw_full, direction)),
            "icCalibration": round_optional(oriented_ic(raw_calibration, direction)),
            "icOos": round_optional(oriented_ic(raw_oos, direction)),
            "sampleSize": len(full_pairs),
            "calibrationSampleSize": len(calibration_pairs),
            "oosSampleSize": len(oos_pairs),
            "overlapBlockLength": overlap_block_len,
            "oosEffectiveSampleSize": max(3, math.ceil(len(oos_pairs) / overlap_block_len)) if oos_pairs else 0,
        }
        if horizon == bootstrap_horizon_days:
            block_len = overlap_block_len
            interval = block_bootstrap_ci(full_pairs, block_len=block_len)
            if interval is not None:
                horizon_row["ci"] = oriented_interval(interval, direction)
            # OOS-aligned CI: bootstrap ONLY the out-of-sample slice so the interval
            # qualifies the headline icOos rather than the full-sample IC.  Because ICs
            # are already oriented so positive means useful, a wholly negative interval
            # is statistically non-zero but explicitly wrong-way, never "robust".
            oos_interval = block_bootstrap_ci(oos_pairs, block_len=block_len)
            if oos_interval is not None:
                ci_oos = oriented_interval(oos_interval, direction)
                horizon_row["ciOos"] = ci_oos
                low, high = ci_oos
                if low is not None and high is not None:
                    horizon_row["statisticallyNonzeroOos"] = bool(low > 0 or high < 0)
                    horizon_row["wrongWayOos"] = bool(high < 0)
                    horizon_row["robustOos"] = bool(low > 0)
            regime = regime_conditional_split(observations, key, prices, direction=direction, block_len=block_len)
            if regime is not None:
                horizon_row["regimeSplit"] = regime
        horizon_rows.append(horizon_row)

    alert = evaluate_alert_rule(
        calibration,
        evaluation,
        prices,
        direction=direction,
        drawdown_threshold_pct=drawdown_threshold_pct,
        drawdown_horizon_days=drawdown_horizon_days,
        alert_percentile=alert_percentile,
        spacing_days=typical_spacing_days(signal.dates),
    )

    return {
        "available": True,
        "direction": direction,
        "observationCount": len(observations),
        "calibrationCount": len(calibration),
        "evaluationCount": len(evaluation),
        "oosSplit": oos_split,
        "oosStartDate": oos_start_date.isoformat() if oos_start_date is not None else evaluation[0]["date"].isoformat(),
        "evaluationStartDate": evaluation[0]["date"].isoformat() if evaluation else None,
        "horizons": horizon_rows,
        "alert": alert,
    }


def evaluate_alert_rule(
    calibration: list[dict[str, Any]],
    evaluation: list[dict[str, Any]],
    prices: SortedSeries,
    *,
    direction: str,
    drawdown_threshold_pct: float,
    drawdown_horizon_days: int,
    alert_percentile: float,
    spacing_days: float,
) -> dict[str, Any]:
    calibration_values = [row["signal"] for row in calibration if math.isfinite(row["signal"])]
    threshold_percentile = alert_percentile if direction == "higher_risk" else 100.0 - alert_percentile
    threshold = percentile_threshold(calibration_values, threshold_percentile)
    if threshold is None:
        return {"available": False, "reason": "calibration slice empty"}
    threshold = adjust_discrete_threshold(
        calibration_values,
        threshold,
        direction=direction,
        expected_fraction=max(0.01, (100.0 - alert_percentile) / 100.0),
    )

    def is_alert(row: dict[str, Any]) -> bool:
        if direction == "higher_risk":
            return row["signal"] >= threshold
        return row["signal"] <= threshold

    def is_event(row: dict[str, Any]) -> bool:
        drawdown = row.get("forwardDrawdown")
        return drawdown is not None and drawdown <= drawdown_threshold_pct

    scored = [row for row in evaluation if row.get("forwardDrawdown") is not None]
    alerts = [row for row in scored if is_alert(row)]
    events = [row for row in scored if is_event(row)]
    hits = [row for row in alerts if is_event(row)]
    base_rate = len(events) / len(scored) if scored else None
    hit_rate = len(hits) / len(alerts) if alerts else None
    lift = (hit_rate / base_rate) if hit_rate is not None and base_rate else None

    lead_times: list[int] = []
    for row in hits:
        trough = prices.forward_trough_date(row["date"], days=drawdown_horizon_days)
        if trough is not None:
            lead_times.append((trough - row["date"]).days)
    lead_time_days = sum(lead_times) / len(lead_times) if lead_times else None

    false_alarm_days = mean_false_alarm_days(alerts, is_event, spacing_days=spacing_days)

    # Full-history breach track record (same calibration-derived threshold applied to every
    # observation) — how often, across the whole sample, did a threshold crossing precede a
    # drawdown. Reported alongside the OOS slice so the in-sample portion is explicit.
    all_scored = [row for row in (calibration + evaluation) if row.get("forwardDrawdown") is not None]
    all_alerts = [row for row in all_scored if is_alert(row)]
    all_hits = [row for row in all_alerts if is_event(row)]
    all_events = [row for row in all_scored if is_event(row)]
    hit_rate_total = len(all_hits) / len(all_alerts) if all_alerts else None
    base_rate_total = len(all_events) / len(all_scored) if all_scored else None
    breach_events = alert_breach_episodes(all_alerts, is_event)

    return {
        "available": True,
        "thresholdValue": round_optional(threshold, digits=2),
        "thresholdPercentile": threshold_percentile,
        "drawdownThresholdPct": drawdown_threshold_pct,
        "drawdownHorizonDays": drawdown_horizon_days,
        "oosSampleSize": len(scored),
        "oosAlertCount": len(alerts),
        "oosHitRate": round_optional(hit_rate, digits=3),
        "baseRate": round_optional(base_rate, digits=3),
        "lift": round_optional(lift, digits=2),
        "leadTimeDays": round_optional(lead_time_days, digits=1),
        "falseAlarmDays": round_optional(false_alarm_days, digits=1),
        "alertCountTotal": len(all_alerts),
        "hitRateTotal": round_optional(hit_rate_total, digits=3),
        "baseRateTotal": round_optional(base_rate_total, digits=3),
        "breachEvents": breach_events,
    }


def alert_breach_episodes(alerts: list[dict[str, Any]], is_event: Any) -> list[dict[str, Any]]:
    """Collapse consecutive weekly threshold crossings into distinct breach episodes; each
    episode reports its start date, the worst forward drawdown that followed, and whether it
    qualified as a drawdown event — a dated track record of the signal's historical breaches."""
    if not alerts:
        return []
    ordered = sorted(alerts, key=lambda item: item["date"])
    episodes: list[list[dict[str, Any]]] = []
    for row in ordered:
        if episodes and (row["date"] - episodes[-1][-1]["date"]).days <= ALERT_EPISODE_GAP_DAYS:
            episodes[-1].append(row)
        else:
            episodes.append([row])
    events: list[dict[str, Any]] = []
    for episode in episodes:
        drawdowns = [row.get("forwardDrawdown") for row in episode if row.get("forwardDrawdown") is not None]
        worst = min(drawdowns) if drawdowns else None
        events.append(
            {
                "date": episode[0]["date"].isoformat(),
                "drawdownPct": round_optional(worst, digits=1),
                "hit": any(is_event(row) for row in episode),
            }
        )
    return events


def adjust_discrete_threshold(
    calibration_values: list[float],
    threshold: float,
    *,
    direction: str,
    expected_fraction: float,
) -> float:
    """Step the threshold to the next distinct value when score ties at the
    percentile cut would flag far more observations than the percentile implies
    (common with discrete 0-100 scores that pile up on default values)."""
    finite = [value for value in calibration_values if math.isfinite(value)]
    if not finite:
        return threshold
    distinct = sorted(set(finite))

    def alert_fraction(candidate: float) -> float:
        if direction == "higher_risk":
            flagged = sum(1 for value in finite if value >= candidate)
        else:
            flagged = sum(1 for value in finite if value <= candidate)
        return flagged / len(finite)

    while alert_fraction(threshold) > expected_fraction * 1.5:
        if direction == "higher_risk":
            higher = [value for value in distinct if value > threshold]
            if not higher:
                break
            threshold = higher[0]
        else:
            lower = [value for value in distinct if value < threshold]
            if not lower:
                break
            threshold = lower[-1]
    return threshold


def mean_false_alarm_days(alerts: list[dict[str, Any]], is_event: Any, *, spacing_days: float) -> float | None:
    if not alerts:
        return None
    episodes: list[list[dict[str, Any]]] = []
    for row in sorted(alerts, key=lambda item: item["date"]):
        if episodes and (row["date"] - episodes[-1][-1]["date"]).days <= ALERT_EPISODE_GAP_DAYS:
            episodes[-1].append(row)
        else:
            episodes.append([row])
    durations = [
        (episode[-1]["date"] - episode[0]["date"]).days + spacing_days
        for episode in episodes
        if not any(is_event(row) for row in episode)
    ]
    return sum(durations) / len(durations) if durations else None


def classify_lead_lag(
    *,
    forward_ic: float | None,
    contemporaneous_corr: float | None,
    trailing_ic: float | None,
    min_ic: float = 0.08,
) -> str:
    forward = abs(forward_ic) if forward_ic is not None else 0.0
    contemporaneous = abs(contemporaneous_corr) if contemporaneous_corr is not None else 0.0
    trailing = abs(trailing_ic) if trailing_ic is not None else 0.0
    best = max(forward, contemporaneous, trailing)
    if best < min_ic:
        return "none"
    if forward >= best * 0.95:
        return "leading"
    if contemporaneous >= trailing:
        return "coincident"
    return "lagging"


def aligned_pearson(first: SortedSeries, second: SortedSeries, *, min_overlap: int = 26) -> float | None:
    lookup = {point_date: value for point_date, value in zip(second.dates, second.values)}
    xs: list[float] = []
    ys: list[float] = []
    for point_date, value in zip(first.dates, first.values):
        other = lookup.get(point_date)
        if other is not None:
            xs.append(value)
            ys.append(other)
    if len(xs) < min_overlap:
        return None
    return pearson_correlation(xs, ys)


def redundancy_clusters(
    series_by_id: dict[str, list[SeriesPoint]],
    *,
    corr_threshold: float = 0.8,
    min_overlap: int = 26,
) -> list[list[str]]:
    ids = sorted(series_by_id)
    sorted_map = {series_id: SortedSeries(series_by_id[series_id]) for series_id in ids}
    parent = {series_id: series_id for series_id in ids}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for index, first_id in enumerate(ids):
        for second_id in ids[index + 1 :]:
            correlation = aligned_pearson(sorted_map[first_id], sorted_map[second_id], min_overlap=min_overlap)
            if correlation is not None and abs(correlation) >= corr_threshold:
                parent[find(second_id)] = find(first_id)

    groups: dict[str, list[str]] = {}
    for series_id in ids:
        groups.setdefault(find(series_id), []).append(series_id)
    clusters = [sorted(members) for members in groups.values() if len(members) > 1]
    return sorted(clusters, key=lambda members: (-len(members), members[0]))


def effective_weights(
    modules_config: list[dict[str, Any]],
    module_weights: dict[str, float],
    clusters: list[list[str]],
) -> list[dict[str, Any]]:
    cluster_lookup: dict[str, tuple[str, int]] = {}
    for index, members in enumerate(clusters):
        cluster_id = f"c{index + 1}"
        for member in members:
            cluster_lookup[member] = (cluster_id, len(members))

    module_weight_total = sum(module_weights.values()) or 1.0
    rows: list[dict[str, Any]] = []
    for module in modules_config:
        module_name = str(module["name"])
        module_share = module_weights.get(module_name, 0.0) / module_weight_total
        factor_weight_total = sum(float(spec["weight"]) for spec in module["factors"]) or 1.0
        for spec in module["factors"]:
            config_weight = module_share * float(spec["weight"]) / factor_weight_total
            cluster_id, cluster_size = cluster_lookup.get(str(spec["id"]), (None, 1))
            rows.append(
                {
                    "id": str(spec["id"]),
                    "module": module_name,
                    "configWeight": config_weight,
                    "rawEffectiveWeight": config_weight / cluster_size,
                    "clusterId": cluster_id,
                }
            )
    raw_total = sum(row["rawEffectiveWeight"] for row in rows) or 1.0
    for row in rows:
        row["effectiveWeight"] = round(row["rawEffectiveWeight"] / raw_total, 4)
        row["configWeight"] = round(row["configWeight"], 4)
        del row["rawEffectiveWeight"]
    return rows


def round_optional(value: float | None, *, digits: int = 3) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


# --- metric-row builder (2026-06-20 Phase 1: pulled down from monolith; the cross-cutting
# validation primitive used by lppl / regional / equity-bridge / validation_build) ---
MIN_SIGNAL_VALIDATION_POINTS = 40


def trailing_return_values(prices: SortedSeries, targets: list[date], *, days: int) -> list[float | None]:
    values: list[float | None] = []
    for target in targets:
        current = prices.value_at_or_before(target)
        past = prices.value_at_or_before(target - timedelta(days=days))
        if current is None or past is None or past == 0:
            values.append(None)
        else:
            values.append((current / past - 1) * 100)
    return values


def signal_validation_metric_row(
    *,
    row_id: str,
    label: str,
    label_cn: str,
    module: str,
    signal_points: list[SeriesPoint],
    price_points: list[SeriesPoint],
    prices_sorted: SortedSeries,
    direction: str,
    drawdown_threshold_pct: float = SIGNAL_VALIDATION_DRAWDOWN_PCT,
    drawdown_horizon_days: int = SIGNAL_VALIDATION_DRAWDOWN_DAYS,
    oos_start_date: date | None = None,
) -> dict[str, Any] | None:
    if len(signal_points) < MIN_SIGNAL_VALIDATION_POINTS:
        return None
    evaluation = evaluate_signal(
        signal_points,
        price_points,
        horizons=(7, 30, 91),
        oos_split=SIGNAL_VALIDATION_OOS_SPLIT,
        direction=direction,
        drawdown_threshold_pct=drawdown_threshold_pct,
        drawdown_horizon_days=drawdown_horizon_days,
        oos_start_date=oos_start_date,
    )
    if not evaluation.get("available"):
        return None
    horizons = {item["days"]: item for item in evaluation["horizons"]}
    targets = [point.date for point in signal_points]
    signal_values: list[float | None] = [point.value for point in signal_points]
    contemporaneous = spearman_ic(signal_values, trailing_return_values(prices_sorted, targets, days=30))
    trailing = spearman_ic(signal_values, trailing_return_values(prices_sorted, targets, days=91))
    forward_candidates = [
        horizons.get(30, {}).get("icOos"),
        horizons.get(91, {}).get("icOos"),
    ]
    forward_candidates = [value for value in forward_candidates if value is not None]
    if not forward_candidates:
        forward_candidates = [
            value
            for value in (horizons.get(30, {}).get("ic"), horizons.get(91, {}).get("ic"))
            if value is not None
        ]
    forward_ic = max(forward_candidates, key=abs) if forward_candidates else None
    alert = evaluation.get("alert", {})
    horizon_3m = horizons.get(91, {})
    oos_ic_3m = horizon_3m.get("icOos")
    oos_sample_size_3m = int(horizon_3m.get("oosSampleSize") or 0)
    oos_effective_sample_size_3m = int(horizon_3m.get("oosEffectiveSampleSize") or 0)
    fold_stability = fold_ic_stability(
        signal_points,
        price_points,
        horizon_days=91,
        direction=direction,
        oos_start_date=oos_start_date,
    )
    return {
        "id": row_id,
        "label": label,
        "labelCn": label_cn,
        "module": module,
        "direction": direction,
        "observationCount": evaluation["observationCount"],
        "calibrationCount": evaluation["calibrationCount"],
        "evaluationCount": evaluation["evaluationCount"],
        "oosStartDate": evaluation.get("oosStartDate"),
        "ic1w": horizons.get(7, {}).get("ic"),
        "ic1m": horizons.get(30, {}).get("ic"),
        "ic3m": horizons.get(91, {}).get("ic"),
        "oosIc1m": horizons.get(30, {}).get("icOos"),
        "oosIc3m": oos_ic_3m,
        "oosSampleSize3m": oos_sample_size_3m,
        "oosEffectiveSampleSize3m": oos_effective_sample_size_3m,
        "pValue3m": round_optional(
            approximate_correlation_p_value(oos_ic_3m, oos_effective_sample_size_3m),
            digits=4,
        ),
        "pValue3mMethod": "Fisher z with horizon-overlap effective sample size",
        "ci3m": horizons.get(91, {}).get("ci"),
        "oosCi3m": horizons.get(91, {}).get("ciOos"),
        "robust": horizons.get(91, {}).get("robustOos"),
        "statisticallyNonzero": horizons.get(91, {}).get("statisticallyNonzeroOos"),
        "wrongWay": horizons.get(91, {}).get("wrongWayOos"),
        "regimeSplit": horizons.get(91, {}).get("regimeSplit"),
        "foldStability3m": fold_stability,
        "hitRateOos": alert.get("oosHitRate"),
        "baseRate": alert.get("baseRate"),
        "lift": alert.get("lift"),
        "leadTimeDays": alert.get("leadTimeDays"),
        "falseAlarmDays": alert.get("falseAlarmDays"),
        "oosAlertCount": alert.get("oosAlertCount"),
        "alertThreshold": alert.get("thresholdValue"),
        "thresholdPercentile": alert.get("thresholdPercentile"),
        "alertCountTotal": alert.get("alertCountTotal"),
        "hitRateTotal": alert.get("hitRateTotal"),
        "baseRateTotal": alert.get("baseRateTotal"),
        "breachEvents": alert.get("breachEvents", []),
        "classification": classify_lead_lag(
            forward_ic=forward_ic,
            contemporaneous_corr=contemporaneous,
            trailing_ic=trailing,
        ),
        "clusterId": None,
    }
