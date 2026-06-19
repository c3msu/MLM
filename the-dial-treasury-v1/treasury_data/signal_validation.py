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

from .sources import SeriesPoint

DEFAULT_OOS_SPLIT = 0.65
DEFAULT_HORIZON_DAYS = (7, 30, 91)
DEFAULT_BOOTSTRAP_SEED = 20260612
MIN_IC_OBSERVATIONS = 8
FORWARD_POINT_TOLERANCE_DAYS = 10
ALERT_EPISODE_GAP_DAYS = 14


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
        index = bisect_left(self.dates, target)
        if index >= len(self.dates):
            return None
        if self.dates[index] > target + timedelta(days=tolerance_days):
            return None
        return self.values[index]

    def percentile_at(self, target: date, *, years: int = 5) -> int | None:
        end_index = self.index_at_or_before(target)
        if end_index is None:
            return None
        start_index = bisect_left(self.dates, window_start(target, years=years))
        if start_index > end_index:
            start_index = end_index
        return rank_percentile(self.values[end_index], self.values[start_index : end_index + 1])

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
        end_index = bisect_right(self.dates, end)
        future_values = self.values[start_index + 1 : end_index]
        if not future_values:
            return None
        return min(0.0, (min(future_values) / self.values[start_index] - 1) * 100)

    def forward_trough_date(self, start: date, *, days: int) -> date | None:
        start_index = self.index_at_or_before(start)
        if start_index is None:
            return None
        end = start + timedelta(days=days)
        end_index = bisect_right(self.dates, end)
        window = range(start_index + 1, end_index)
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

    split_index = max(1, min(len(observations) - 1, int(len(observations) * oos_split)))
    calibration = observations[:split_index]
    evaluation = observations[split_index:]

    horizon_rows: list[dict[str, Any]] = []
    for horizon in horizons:
        key = f"forward{horizon}"
        raw_full = spearman_ic([row["signal"] for row in observations], [row[key] for row in observations])
        raw_calibration = spearman_ic([row["signal"] for row in calibration], [row[key] for row in calibration])
        raw_oos = spearman_ic([row["signal"] for row in evaluation], [row[key] for row in evaluation])
        horizon_row: dict[str, Any] = {
            "days": horizon,
            "ic": round_optional(oriented_ic(raw_full, direction)),
            "icCalibration": round_optional(oriented_ic(raw_calibration, direction)),
            "icOos": round_optional(oriented_ic(raw_oos, direction)),
        }
        if horizon == bootstrap_horizon_days:
            spacing = typical_spacing_days(signal.dates)
            block_len = max(1, int(round(horizon / max(spacing, 1.0))))
            pairs = finite_pairs([row["signal"] for row in observations], [row[key] for row in observations])
            interval = block_bootstrap_ci(pairs, block_len=block_len)
            if interval is not None:
                horizon_row["ci"] = oriented_interval(interval, direction)
            # OOS-aligned CI: bootstrap ONLY the out-of-sample slice so the interval
            # qualifies the headline icOos rather than the full-sample IC. robustOos is
            # True only when this OOS CI excludes zero (the IC is statistically
            # distinguishable from no-skill on held-out data — guards against reading a
            # noisy single-slice point estimate as real predictive power).
            oos_pairs = finite_pairs([row["signal"] for row in evaluation], [row[key] for row in evaluation])
            oos_interval = block_bootstrap_ci(oos_pairs, block_len=block_len)
            if oos_interval is not None:
                ci_oos = oriented_interval(oos_interval, direction)
                horizon_row["ciOos"] = ci_oos
                low, high = ci_oos
                if low is not None and high is not None:
                    horizon_row["robustOos"] = bool(low > 0 or high < 0)
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
