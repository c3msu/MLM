"""Signal-validation assembly layer extracted from build_dashboard.py
(behavior-unchanged, 2026-06-19 全面重构 Phase 1). Sits above the scoring domains: the
weekly Bhadial walk-forward replay (BhadialWeeklyReplay), build_signal_validation
(factor + composite OOS metric rows, redundancy clusters, regime split), the
predictive-lens composite, and the equity validation-row bridge. Imports the scoring
layers it validates (bhadial/spy-warning) plus the signal_validation primitives.
Re-exported via `from .validation_build import *`."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .sources import SeriesPoint
from .dashboard_core import *  # noqa: F401,F403
from .series_math import *  # noqa: F401,F403
from .signal_validation import *  # noqa: F401,F403
from .scoring_bhadial import *  # noqa: F401,F403
from .scoring_spy_warning import *  # noqa: F401,F403


class BhadialWeeklyReplay:
    """Point-in-time weekly factor replay over pre-sorted score series.

    Mirrors bhadial_factor_score_at / bhadial_conditions_score_at semantics
    (including the Funding EMA(5) smoothing) but uses bisect lookups and
    memoized month-end module scores so a 5Y weekly replay stays fast."""

    def __init__(self, series: dict[str, list[SeriesPoint]]):
        self.sorted_series: dict[str, SortedSeries] = {
            key: SortedSeries(series.get(key) or []) for key in BHADIAL_CONDITION_SERIES_KEYS
        }
        self._factor_cache: dict[tuple[str, date], tuple[float, bool]] = {}
        self._module_raw_cache: dict[tuple[str, date], tuple[float, int]] = {}
        self._month_ends_cache: dict[str, list[date]] = {}

    def factor_score_at(self, spec: dict[str, Any], target: date) -> tuple[float, bool]:
        cache_key = (str(spec["id"]), target)
        cached = self._factor_cache.get(cache_key)
        if cached is not None:
            return cached
        sorted_points = self.sorted_series.get(str(spec["scoreKey"]))
        current = sorted_points.value_at_or_before(target) if sorted_points is not None else None
        if current is None:
            row = (50.0, False)
        else:
            method = str(spec["method"])
            direction = str(spec["direction"])
            if method == "risk_signal":
                bounded = max(0.0, min(1.0, current))
                score = (1 - bounded) * 100 if direction == "lower_better" else bounded * 100
            elif method == "shock_only" and current <= 0:
                score = 50.0
            else:
                score = score_from_percentile(sorted_points.percentile_at(target), direction)
            row = (max(0.0, min(100.0, score)), True)
        self._factor_cache[cache_key] = row
        return row

    def module_raw_score_at(self, module: dict[str, Any], target: date) -> tuple[float, int]:
        cache_key = (str(module["name"]), target)
        cached = self._module_raw_cache.get(cache_key)
        if cached is not None:
            return cached
        total = 0.0
        total_weight = 0.0
        observed = 0
        for spec in module["factors"]:
            score, was_observed = self.factor_score_at(spec, target)
            weight = float(spec["weight"])
            total += score * weight
            total_weight += weight
            if was_observed:
                observed += 1
        row = (total / max(total_weight, 1e-9), observed)
        self._module_raw_cache[cache_key] = row
        return row

    def module_month_ends(self, module: dict[str, Any]) -> list[date]:
        key = str(module["name"])
        cached = self._month_ends_cache.get(key)
        if cached is not None:
            return cached
        month_ends: dict[tuple[int, int], date] = {}
        for spec in module["factors"]:
            sorted_points = self.sorted_series.get(str(spec["scoreKey"]))
            if sorted_points is None:
                continue
            for point_date in sorted_points.dates:
                month_key = (point_date.year, point_date.month)
                existing = month_ends.get(month_key)
                if existing is None or point_date > existing:
                    month_ends[month_key] = point_date
        result = [month_ends[month_key] for month_key in sorted(month_ends)]
        self._month_ends_cache[key] = result
        return result

    def module_ema_score_at(self, module: dict[str, Any], target: date, *, span: int = 5) -> float | None:
        start = window_start(target, years=5)
        point_dates = [point_date for point_date in self.module_month_ends(module) if start <= point_date <= target]
        if target not in point_dates:
            point_dates.append(target)
        alpha = 2 / (span + 1)
        ema: float | None = None
        for point_date in sorted(point_dates):
            score, _ = self.module_raw_score_at(module, point_date)
            ema = score if ema is None else alpha * score + (1 - alpha) * ema
        return ema

    def composite_at(self, target: date, *, include_components: bool = False) -> dict[str, Any]:
        composite_total = 0.0
        weight_total = 0.0
        observed_total = 0
        components: list[dict[str, Any]] = []
        for module in BHADIAL_CONDITION_MODULES:
            module_score, observed = self.module_raw_score_at(module, target)
            if module.get("smooth") == "ema5":
                ema = self.module_ema_score_at(module, target, span=5)
                if ema is not None:
                    module_score = ema
            module_weight = bhadial_module_weight(str(module["name"]))
            composite_total += module_score * module_weight
            weight_total += module_weight
            observed_total += observed
            if include_components:
                for spec in module["factors"]:
                    score, _ = self.factor_score_at(spec, target)
                    components.append(
                        {
                            "id": str(spec["id"]),
                            "module": str(module["name"]),
                            "moduleCn": str(module["nameCn"]),
                            "remoteName": str(spec["remoteName"]),
                            "name": str(spec["name"]),
                            "score": round(score, 1),
                            "value": "",
                            "source": str(spec["source"]),
                        }
                    )
        return {
            "score": composite_total / max(weight_total, 1e-9),
            "observedFactorCount": observed_total,
            "components": components,
        }




def unavailable_signal_validation(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "factors": [],
        "composites": [],
        "clusters": [],
        "effectiveWeights": [],
    }


def build_signal_validation(
    indicators: dict[str, Any],
    *,
    equity_short_term_risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    series = indicators.get("percentile_series") if isinstance(indicators.get("percentile_series"), dict) else {}
    sp500_points = clean_points(series.get("sp500", []))
    week_targets = weekly_dates(sp500_points, years=5)
    if len(week_targets) < SIGNAL_VALIDATION_MIN_WEEKS:
        return unavailable_signal_validation("S&P 500周度样本不足,暂不能执行走出样本验证。")
    prices_sorted = SortedSeries(sp500_points)
    replay = BhadialWeeklyReplay(series)

    factor_series: dict[str, list[SeriesPoint]] = {}
    factor_rows: list[dict[str, Any]] = []
    for module in BHADIAL_CONDITION_MODULES:
        for spec in module["factors"]:
            points = []
            for target in week_targets:
                score, observed = replay.factor_score_at(spec, target)
                if observed:
                    points.append(SeriesPoint(date=target, value=score))
            factor_series[str(spec["id"])] = points
            row = signal_validation_metric_row(
                row_id=str(spec["id"]),
                label=str(spec["remoteName"]),
                label_cn=str(spec["name"]),
                module=str(module["name"]),
                signal_points=points,
                price_points=sp500_points,
                prices_sorted=prices_sorted,
                direction="higher_better",
            )
            if row is not None:
                factor_rows.append(row)

    clusters = redundancy_clusters(
        {factor_id: points for factor_id, points in factor_series.items() if len(points) >= MIN_SIGNAL_VALIDATION_POINTS}
    )
    cluster_rows = [
        {"id": f"c{index + 1}", "factorIds": members}
        for index, members in enumerate(clusters)
    ]
    cluster_lookup = {member: row["id"] for row in cluster_rows for member in row["factorIds"]}
    for row in factor_rows:
        row["clusterId"] = cluster_lookup.get(row["id"])

    composite_points: list[SeriesPoint] = []
    weekly_components: dict[date, list[dict[str, Any]]] = {}
    for target in week_targets:
        composite = replay.composite_at(target, include_components=True)
        if int(composite.get("observedFactorCount", 0)) < 5:
            continue
        composite_points.append(SeriesPoint(date=target, value=float(composite["score"])))
        weekly_components[target] = composite["components"]

    change_points: list[SeriesPoint] = [
        SeriesPoint(date=current.date, value=current.value - composite_points[index - 13].value)
        for index, current in enumerate(composite_points)
        if index >= 13
    ]

    sleeve_series: dict[str, list[SeriesPoint]] = {str(spec["key"]): [] for spec in SPY_WARNING_COMPONENT_SLEEVES}
    spy_warning_points: list[SeriesPoint] = []
    rule_fires: dict[str, list[dict[str, Any]]] = {}
    rule_meta: dict[str, dict[str, Any]] = {}
    composite_by_date = {point.date: point.value for point in composite_points}
    change_by_date = {point.date: point.value for point in change_points}
    for point in composite_points:
        components = weekly_components.get(point.date, [])
        component_by_id = {str(item.get("id")): item for item in components}
        for spec in SPY_WARNING_COMPONENT_SLEEVES:
            sleeve = build_spy_component_sleeve(spec, component_by_id)
            if sleeve.get("available"):
                sleeve_series[str(spec["key"])].append(SeriesPoint(date=point.date, value=float(sleeve["score"])))
        score_change = change_by_date.get(point.date)
        trailing_values = trailing_return_values(prices_sorted, [point.date], days=91)
        signal = {
            "date": point.date.isoformat(),
            "conditionsScore": composite_by_date.get(point.date),
            "score3mChange": score_change,
            "levelBucket": "",
            "changeBucket": "",
            "expectedForward3m": None,
            "expectedDrawdown3m": None,
            "sp500Trailing3m": trailing_values[0],
            "hitRate": None,
            "confidence": "replay",
        }
        snapshot = spy_early_warning_snapshot(
            {"score": round(point.value, 1), "components": components},
            {"asOf": point.date.isoformat(), "currentSignal": signal},
        )
        score = optional_float(snapshot.get("score")) if snapshot.get("available") else None
        if score is not None:
            spy_warning_points.append(SeriesPoint(date=point.date, value=score))
            amplifier_items = snapshot.get("amplifiers") if isinstance(snapshot.get("amplifiers"), list) else []
            dampener_items = snapshot.get("dampeners") if isinstance(snapshot.get("dampeners"), list) else []
            for kind, items in (("amplifier", amplifier_items), ("dampener", dampener_items)):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or "")
                    if not key:
                        continue
                    effect = optional_float(item.get("scoreBoost"))
                    if effect is None:
                        effect = optional_float(item.get("scoreOffset"))
                    rule_meta.setdefault(
                        key,
                        {"label": str(item.get("label") or key), "kind": kind, "scoreEffect": effect or 0.0},
                    )
                    rule_fires.setdefault(key, []).append(
                        {"date": point.date, "trailing3m": trailing_values[0]}
                    )

    amplifier_audit = build_spy_warning_rule_audit(
        rule_fires,
        rule_meta,
        [item.date for item in spy_warning_points],
        prices_sorted,
    )

    composite_specs: list[dict[str, Any]] = [
        {
            "id": "bhadialComposite",
            "label": "Conditions Score (weekly)",
            "labelCn": "宏观环境评分(周度)",
            "points": composite_points,
            "direction": "higher_better",
        },
        {
            "id": "bhadialChange13w",
            "label": "Conditions Score 13W change",
            "labelCn": "宏观评分13周变化",
            "points": change_points,
            "direction": "higher_better",
        },
        {
            "id": "spyEarlyWarning",
            "label": "SPY Early Warning (weekly replay)",
            "labelCn": "SPY预警(周度回放)",
            "points": spy_warning_points,
            "direction": "higher_risk",
        },
    ]
    sleeve_labels = {str(spec["key"]): str(spec["label"]) for spec in SPY_WARNING_COMPONENT_SLEEVES}
    for sleeve_key, points in sleeve_series.items():
        composite_specs.append(
            {
                "id": f"sleeve:{sleeve_key}",
                "label": sleeve_key,
                "labelCn": sleeve_labels.get(sleeve_key, sleeve_key),
                "points": points,
                "direction": "higher_risk",
            }
        )

    composite_rows: list[dict[str, Any]] = []
    for spec in composite_specs:
        row = signal_validation_metric_row(
            row_id=str(spec["id"]),
            label=str(spec["label"]),
            label_cn=str(spec["labelCn"]),
            module="composite",
            signal_points=spec["points"],
            price_points=sp500_points,
            prices_sorted=prices_sorted,
            direction=str(spec["direction"]),
        )
        if row is not None:
            composite_rows.append(row)

    equity_row = build_equity_signal_validation_row(equity_short_term_risk)
    if equity_row is not None:
        composite_rows.append(equity_row)

    weights = effective_weights(BHADIAL_CONDITION_MODULES, BHADIAL_MODULE_WEIGHTS, clusters)

    predictive_lens = build_bhadial_predictive_lens(
        replay,
        week_targets,
        factor_series,
        weights,
        prices_sorted,
    )
    if predictive_lens.get("available"):
        predictive_row = signal_validation_metric_row(
            row_id="bhadialPredictive",
            label="Predictive lens (leading factors)",
            label_cn="预测镜头(领先因子)",
            module="composite",
            signal_points=predictive_lens["points"],
            price_points=sp500_points,
            prices_sorted=prices_sorted,
            direction="higher_better",
        )
        if predictive_row is not None:
            composite_rows.append(predictive_row)
    predictive_payload = {key: value for key, value in predictive_lens.items() if key != "points"}
    summary = signal_validation_summary(factor_rows, composite_rows)
    return {
        "available": True,
        "asOf": week_targets[-1].isoformat(),
        "summary": summary,
        "method": (
            "Weekly point-in-time replay of all condition factors and composite overlays against forward "
            "S&P 500 returns; thresholds and ICs are split into calibration (first 65%) and out-of-sample "
            "(last 35%) slices; alert hit rates are compared with the unconditional base rate."
        ),
        "weeklyObservationCount": len(week_targets),
        "oosSplitPct": round(SIGNAL_VALIDATION_OOS_SPLIT * 100),
        "drawdownRule": f"{SIGNAL_VALIDATION_DRAWDOWN_DAYS}D内最大回撤≤{SIGNAL_VALIDATION_DRAWDOWN_PCT:.0f}%",
        "factors": factor_rows,
        "composites": composite_rows,
        "clusters": cluster_rows,
        "effectiveWeights": weights,
        "predictiveLens": predictive_payload,
        "amplifierAudit": amplifier_audit,
    }


def signal_validation_summary(
    factor_rows: list[dict[str, Any]],
    composite_rows: list[dict[str, Any]],
) -> str:
    """One-line honest readout of the OOS-robustness landscape, read off the already-computed
    `robust`/`classification` fields (no new estimation). Discipline: only robust signals are
    forward-actionable; the rest are diagnostic context."""
    robust_factors = [f for f in factor_rows if isinstance(f, dict) and f.get("robust")]
    robust_leading = [f for f in robust_factors if str(f.get("classification")) == "leading"]
    robust_other = [f for f in robust_factors if str(f.get("classification")) != "leading"]
    by_id = {str(c.get("id")): c for c in composite_rows if isinstance(c, dict)}
    agg = by_id.get("spyEarlyWarning")
    if isinstance(agg, dict) and "robust" in agg:
        agg_text = "聚合预警样本外稳健" if agg.get("robust") else "聚合预警未达样本外稳健(CI跨0)"
    else:
        agg_text = "聚合预警稳健性未知"
    return (
        f"{len(factor_rows)}因子周度回放: {len(robust_leading)}个稳健领先(样本外CI排除0), "
        f"{len(robust_other)}个稳健同步/滞后; {agg_text}。仅稳健信号可作前瞻依据,余者仅诊断。"
    )


def annotate_spy_warning_robustness(
    spy_early_warning: dict[str, Any] | None,
    signal_validation: dict[str, Any] | None,
) -> None:
    """Stamp the SPY early-warning dict with its OOS-robustness verdict + the names of its
    robust *leading* sleeves, read off the signalValidation composites. Honest labeling: the
    aggregate is not OOS-robust, but its funding/rates sleeves are robustly leading. In-place."""
    if not isinstance(spy_early_warning, dict) or not isinstance(signal_validation, dict):
        return
    by_id = {str(c.get("id")): c for c in (signal_validation.get("composites") or []) if isinstance(c, dict)}
    agg = by_id.get("spyEarlyWarning")
    if isinstance(agg, dict) and "robust" in agg:
        spy_early_warning["aggregateRobust"] = bool(agg.get("robust"))
        spy_early_warning["aggregateOosCi3m"] = agg.get("oosCi3m")
    spy_early_warning["robustSleeves"] = [
        cid.split(":", 1)[1]
        for cid, c in by_id.items()
        if cid.startswith("sleeve:") and c.get("robust") and (optional_float(c.get("oosIc3m")) or 0.0) > 0
    ]


def build_bhadial_predictive_lens(
    replay: "BhadialWeeklyReplay",
    week_targets: list[date],
    factor_series: dict[str, list[SeriesPoint]],
    weight_rows: list[dict[str, Any]],
    prices_sorted: SortedSeries,
    *,
    min_factors: int = 3,
    min_calibration_ic: float = 0.10,
) -> dict[str, Any]:
    """Predictive-lens composite: factors are selected by their CALIBRATION-slice
    forward IC only (never the OOS slice, so the lens's OOS metrics stay honest),
    weighted by redundancy-adjusted effective weights, and replayed with each
    factor's publicationLagDays applied so only truly-available data enters."""
    spec_by_id = {
        str(spec["id"]): spec
        for module in BHADIAL_CONDITION_MODULES
        for spec in module["factors"]
    }
    selected: list[dict[str, Any]] = []
    for factor_id in sorted(factor_series):
        points = factor_series[factor_id]
        if len(points) < MIN_SIGNAL_VALIDATION_POINTS:
            continue
        split_index = max(1, int(len(points) * SIGNAL_VALIDATION_OOS_SPLIT))
        calibration = points[:split_index]
        signal_values: list[float | None] = [point.value for point in calibration]
        ic_1m = spearman_ic(signal_values, [prices_sorted.forward_return_pct(point.date, days=30) for point in calibration])
        ic_3m = spearman_ic(signal_values, [prices_sorted.forward_return_pct(point.date, days=91) for point in calibration])
        # 2026-06-18: 要求 1M 与 3M 校准段 IC 同时达标(取 min,而非之前的 max 取优)。
        # 旧逻辑只需单一horizon偶然相关即入选,导致选入同步/滞后因子(VIX/油气冲击),
        # 样本外 IC 反转至 -0.49。改为多horizon一致性筛选以降低过拟合。
        if ic_1m is None or ic_3m is None:
            continue
        consistent_ic = min(ic_1m, ic_3m)
        if consistent_ic < min_calibration_ic:
            continue
        selected.append({"id": factor_id, "calibrationIc": round(consistent_ic, 3)})
    if len(selected) < min_factors:
        return {
            "available": False,
            "reason": f"校准段达标的领先因子不足{min_factors}个,预测镜头暂不发布。",
            "selectedFactors": selected,
            "points": [],
        }
    weight_by_id = {str(row["id"]): float(row["effectiveWeight"]) for row in weight_rows}
    points: list[SeriesPoint] = []
    for target in week_targets:
        total = 0.0
        weight_total = 0.0
        for item in selected:
            spec = spec_by_id.get(item["id"])
            if spec is None:
                continue
            lag = int(spec.get("publicationLagDays") or 1)
            score, observed = replay.factor_score_at(spec, target - timedelta(days=lag))
            if not observed:
                continue
            weight = weight_by_id.get(item["id"], 0.0)
            total += score * weight
            weight_total += weight
        if weight_total > 0:
            points.append(SeriesPoint(date=target, value=total / weight_total))
    for item in selected:
        item["effectiveWeight"] = weight_by_id.get(item["id"], 0.0)
    latest_score = round(points[-1].value, 1) if points else None
    return {
        "available": bool(points),
        "method": (
            "Leading factors chosen on the calibration slice only, requiring BOTH 1M and 3M "
            f"forward IC >= {min_calibration_ic:.2f} (multi-horizon consistency, not best-of), "
            "weighted by redundancy-adjusted effective weights, replayed with per-factor publication lags."
        ),
        "selectedFactors": selected,
        "latestScore": latest_score,
        "points": points,
    }


def build_equity_signal_validation_row(equity_short_term_risk: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(equity_short_term_risk, dict):
        return None
    trend = equity_short_term_risk.get("trend")
    if not isinstance(trend, dict) or not trend.get("available"):
        return None
    signal_points: list[SeriesPoint] = []
    price_points: list[SeriesPoint] = []
    for row in trend.get("points", []):
        if not isinstance(row, dict):
            continue
        try:
            target = date.fromisoformat(str(row.get("date") or ""))
        except ValueError:
            continue
        score = optional_float(row.get("score"))
        close = optional_float(row.get("spyClose"))
        if score is None or close is None or close <= 0:
            continue
        signal_points.append(SeriesPoint(date=target, value=score))
        price_points.append(SeriesPoint(date=target, value=close))
    if len(signal_points) < MIN_SIGNAL_VALIDATION_POINTS:
        return None
    return signal_validation_metric_row(
        row_id="equityShortTermRisk",
        label="Equity Short-Term Risk (daily)",
        label_cn="股票短周期风险(日度)",
        module="composite",
        signal_points=signal_points,
        price_points=price_points,
        prices_sorted=SortedSeries(price_points),
        direction="higher_risk",
        drawdown_threshold_pct=SIGNAL_VALIDATION_EQUITY_DRAWDOWN_PCT,
        drawdown_horizon_days=SIGNAL_VALIDATION_EQUITY_DRAWDOWN_DAYS,
    )
