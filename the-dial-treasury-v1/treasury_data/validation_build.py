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
    (including Funding's five-daily-availability-observation EMA) but uses
    bisect lookups and memoized module scores so a 5Y weekly replay stays fast.
    """

    def __init__(self, series: dict[str, list[SeriesPoint]]):
        self.sorted_series: dict[str, SortedSeries] = {
            key: SortedSeries(series.get(key) or []) for key in BHADIAL_CONDITION_SERIES_KEYS
        }
        self._factor_cache: dict[tuple[str, date], tuple[float, bool]] = {}
        self._module_raw_cache: dict[tuple[str, date], tuple[float, int]] = {}
        self._module_decision_dates_cache: dict[str, list[date]] = {}

    @staticmethod
    def publication_lag_days(spec: dict[str, Any]) -> int:
        """Delegate to the same availability rule used by live scoring."""
        return bhadial_publication_lag_days(spec)

    def factor_score_at(self, spec: dict[str, Any], target: date) -> tuple[float, bool]:
        """Return the decision-date score and whether it is eligible for use.

        ``target`` is always the decision date.  This method owns the release-lag
        cutoff so callers cannot accidentally omit it or apply it twice.  A
        missing, stale, or warming observation is neutralised to 50 and excluded
        from validation, matching the live scorer's eligibility contract.
        """
        cache_key = (str(spec["id"]), target)
        cached = self._factor_cache.get(cache_key)
        if cached is not None:
            return cached
        availability_cutoff = target - timedelta(days=self.publication_lag_days(spec))
        sorted_points = self.sorted_series.get(str(spec["scoreKey"]))
        current_index = sorted_points.index_at_or_before(availability_cutoff) if sorted_points is not None else None
        current = sorted_points.values[current_index] if sorted_points is not None and current_index is not None else None
        if current is None:
            row = (50.0, False)
        else:
            observation_date = sorted_points.dates[current_index]
            age_days = max(0, (target - observation_date).days)
            max_age_days = int(spec["maxAgeDays"])
            percentile, sample_count = sorted_points.percentile_with_sample_count_at(availability_cutoff)
            min_sample_count = int(spec["minSampleCount"])
            eligible = (
                age_days <= max_age_days
                and sample_count >= min_sample_count
                and percentile is not None
            )
            if not eligible:
                row = (50.0, False)
                self._factor_cache[cache_key] = row
                return row
            score = bhadial_score_from_observation(
                current,
                percentile,
                method=str(spec["method"]),
                direction=str(spec["direction"]),
            )
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

    def module_decision_dates(self, module: dict[str, Any]) -> list[date]:
        """Return unique dates when an input becomes available to the scorer."""
        key = str(module["name"])
        cached = self._module_decision_dates_cache.get(key)
        if cached is not None:
            return cached
        decision_dates: set[date] = set()
        for spec in module["factors"]:
            sorted_points = self.sorted_series.get(str(spec["scoreKey"]))
            if sorted_points is None:
                continue
            lag = self.publication_lag_days(spec)
            for point_date in sorted_points.dates:
                decision_dates.add(point_date + timedelta(days=lag))
        result = sorted(decision_dates)
        self._module_decision_dates_cache[key] = result
        return result

    def module_ema_score_at(self, module: dict[str, Any], target: date, *, span: int = 5) -> float | None:
        if span <= 0:
            raise ValueError("span must be positive")
        start = window_start(target, years=5)
        point_dates = [
            point_date
            for point_date in self.module_decision_dates(module)
            if start <= point_date <= target
        ]
        if point_dates and point_dates[-1] < target:
            prior_score, prior_observed = self.module_raw_score_at(module, point_dates[-1])
            target_score, target_observed = self.module_raw_score_at(module, target)
            if prior_score != target_score or prior_observed != target_observed:
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
                    score, score_eligible = self.factor_score_at(spec, target)
                    components.append(
                        {
                            "id": str(spec["id"]),
                            "module": str(module["name"]),
                            "moduleCn": str(module["nameCn"]),
                            "remoteName": str(spec["remoteName"]),
                            "name": str(spec["name"]),
                            "score": round(score, 1),
                            "observed": score_eligible,
                            "scoreEligible": score_eligible,
                            "freshnessStatus": "fresh" if score_eligible else "unavailable",
                            "scoringStatus": "scored" if score_eligible else "unavailable",
                            "value": "",
                            "source": str(spec["source"]),
                        }
                    )
        return {
            "score": composite_total / max(weight_total, 1e-9),
            "observedFactorCount": observed_total,
            "components": components,
        }




EQUITY_SHORT_TERM_VALIDATION_EXCLUSION = {
    "id": "equityShortTermRisk",
    "reason": (
        "Excluded from the 91-calendar-day composite/FDR family because its "
        "primary endpoint is 15 trading days and it has a dedicated walk-forward backtest."
    ),
    "primaryEndpoint": "15 trading days",
    "validationPath": "equityShortTermRisk.backtest",
}


def unavailable_signal_validation(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        # Keep the intended SPY model version explicit even when no aggregate
        # row can be estimated.  Consumers must still require the aggregate
        # row's own version before promoting any action.
        "spyEarlyWarningRulesVersion": SPY_WARNING_RULES_VERSION,
        "factors": [],
        "composites": [],
        "excludedModels": [dict(EQUITY_SHORT_TERM_VALIDATION_EXCLUSION)],
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
    common_split_index = max(
        0,
        min(len(week_targets) - 1, int(len(week_targets) * SIGNAL_VALIDATION_OOS_SPLIT)),
    )
    common_oos_start = week_targets[common_split_index]

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
                oos_start_date=common_oos_start,
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
            "rulesVersion": SPY_WARNING_RULES_VERSION,
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
            oos_start_date=common_oos_start,
        )
        if row is not None:
            if isinstance(spec.get("rulesVersion"), str):
                row["rulesVersion"] = str(spec["rulesVersion"])
            composite_rows.append(row)

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
            oos_start_date=common_oos_start,
        )
        if predictive_row is not None:
            composite_rows.append(predictive_row)
    factor_family_size = sum(len(module["factors"]) for module in BHADIAL_CONDITION_MODULES)
    # The predictive lens is attempted under a fixed specification.  If it is
    # unavailable, it remains an implicit p=1 member rather than silently
    # reducing the composite multiplicity penalty.
    composite_family_size = len(composite_specs) + 1
    apply_benjamini_hochberg(
        factor_rows,
        alpha=DEFAULT_FDR_ALPHA,
        family_size=factor_family_size,
    )
    apply_benjamini_hochberg(
        composite_rows,
        alpha=DEFAULT_FDR_ALPHA,
        family_size=composite_family_size,
    )
    predictive_payload = {key: value for key, value in predictive_lens.items() if key != "points"}
    summary = signal_validation_summary(factor_rows, composite_rows)
    return {
        "available": True,
        "asOf": week_targets[-1].isoformat(),
        "spyEarlyWarningRulesVersion": SPY_WARNING_RULES_VERSION,
        "summary": summary,
        "method": (
            "Weekly point-in-time replay of all condition factors and composite overlays against forward "
            "S&P 500 returns; every row uses one common calendar 65/35 OOS boundary, plus contiguous fold-stability "
            "diagnostics and Benjamini-Hochberg control on the pre-specified 3M factor endpoint. Because factor "
            "definitions and weights were informed by prior validation, the tail slice is research validation, "
            "not an untouched independent holdout. equityShortTermRisk is excluded because its primary endpoint "
            "is 15 trading days and is assessed in its dedicated walk-forward backtest."
        ),
        "validationStatus": "research-validation",
        "independentHoldout": False,
        "primaryEndpointDays": 91,
        "commonOosStartDate": common_oos_start.isoformat(),
        "multipleTesting": {
            "method": "Benjamini-Hochberg",
            "alpha": DEFAULT_FDR_ALPHA,
            "scope": "separate factor and composite oosIc3m families",
            "families": [
                {
                    "name": "factors",
                    "size": factor_family_size,
                    "reportedRows": len(factor_rows),
                    "implicitUnavailableHypotheses": max(0, factor_family_size - len(factor_rows)),
                },
                {
                    "name": "composites",
                    "size": composite_family_size,
                    "reportedRows": len(composite_rows),
                    "implicitUnavailableHypotheses": max(0, composite_family_size - len(composite_rows)),
                },
            ],
        },
        "weeklyObservationCount": len(week_targets),
        "oosSplitPct": round(SIGNAL_VALIDATION_OOS_SPLIT * 100),
        "drawdownRule": f"{SIGNAL_VALIDATION_DRAWDOWN_DAYS}D内最大回撤≤{SIGNAL_VALIDATION_DRAWDOWN_PCT:.0f}%",
        "factors": factor_rows,
        "composites": composite_rows,
        "excludedModels": [dict(EQUITY_SHORT_TERM_VALIDATION_EXCLUSION)],
        "clusters": cluster_rows,
        "effectiveWeights": weights,
        "predictiveLens": predictive_payload,
        "amplifierAudit": amplifier_audit,
    }


def signal_validation_summary(
    factor_rows: list[dict[str, Any]],
    composite_rows: list[dict[str, Any]],
    *,
    independent_holdout: bool = False,
) -> str:
    """One-line honest readout of the OOS-robustness landscape, read off the already-computed
    `robust`/`classification` fields (no new estimation). Discipline: only robust signals are
    forward-actionable; the rest are diagnostic context."""
    robust_factors = [f for f in factor_rows if isinstance(f, dict) and f.get("actionableRobust")]
    robust_leading = [f for f in robust_factors if str(f.get("classification")) == "leading"]
    robust_other = [f for f in robust_factors if str(f.get("classification")) != "leading"]
    by_id = {str(c.get("id")): c for c in composite_rows if isinstance(c, dict)}
    agg = by_id.get("spyEarlyWarning")
    if (
        isinstance(agg, dict)
        and agg.get("actionableRobust") is True
        and independent_holdout
    ):
        agg_text = "聚合预警通过CI、FDR、分折一致性与独立留出门槛"
    elif isinstance(agg, dict) and agg.get("actionableRobust") is True:
        agg_text = "聚合预警通过统计门槛,但验证尾段非独立留出,仅作研究证据"
    elif isinstance(agg, dict) and agg.get("robust") is True:
        agg_text = "聚合预警CI为正,但未通过FDR/分折门槛"
    elif isinstance(agg, dict) and "robust" in agg:
        agg_text = "聚合预警未达样本外统计显著(CI跨0)"
    else:
        agg_text = "聚合预警稳健性未知"
    return (
        f"{len(factor_rows)}因子周度回放: {len(robust_leading)}个通过CI、FDR与分折一致性的领先因子, "
        f"{len(robust_other)}个稳健同步/滞后; {agg_text}。只有统计门槛与独立留出验证同时通过时才可发布动作层。"
    )


def annotate_spy_warning_robustness(
    spy_early_warning: dict[str, Any] | None,
    signal_validation: dict[str, Any] | None,
) -> None:
    """Stamp the SPY early-warning dict with its OOS-robustness verdict + the names of its
    robust *leading* sleeves, read off the signalValidation composites. Honest labeling: the
    aggregate is not OOS-robust, but its funding/rates sleeves are robustly leading. In-place."""
    if not isinstance(spy_early_warning, dict):
        return
    # ``None`` is missing evidence, not a reason to leave the raw allocation
    # untouched.  Treat it like an empty validation payload and fail closed.
    signal_validation = signal_validation if isinstance(signal_validation, dict) else {}
    by_id = {str(c.get("id")): c for c in (signal_validation.get("composites") or []) if isinstance(c, dict)}
    agg = by_id.get("spyEarlyWarning")
    independent_holdout = signal_validation.get("independentHoldout") is True

    def version_text(value: Any) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    surface_rules_version = version_text(spy_early_warning.get("rulesVersion"))
    validation_rules_version = version_text(signal_validation.get("spyEarlyWarningRulesVersion"))
    aggregate_rules_version = version_text(agg.get("rulesVersion")) if isinstance(agg, dict) else None
    rules_version_complete = all(
        version is not None
        for version in (
            surface_rules_version,
            validation_rules_version,
            aggregate_rules_version,
        )
    )
    rules_version_matched = bool(
        rules_version_complete
        and surface_rules_version == validation_rules_version == aggregate_rules_version
        and surface_rules_version == SPY_WARNING_RULES_VERSION
    )
    rules_version_audit = {
        "expectedRulesVersion": SPY_WARNING_RULES_VERSION,
        "surfaceRulesVersion": surface_rules_version,
        "validationRulesVersion": validation_rules_version,
        "aggregateRulesVersion": aggregate_rules_version,
        "complete": rules_version_complete,
        "matched": rules_version_matched,
    }
    if not rules_version_complete:
        version_failure_reason = (
            "SPY规则版本审计不完整,当前规则或验证证据缺少版本标识,"
            "旧证据不得晋升动作层。"
        )
    elif not rules_version_matched:
        version_failure_reason = (
            f"SPY规则版本不匹配(expected={SPY_WARNING_RULES_VERSION}, "
            f"surface={surface_rules_version}, "
            f"validation={validation_rules_version}, aggregate={aggregate_rules_version}),"
            "旧验证不得晋升当前规则动作层。"
        )
    else:
        version_failure_reason = ""

    research_only_summary = (
        "SPY预警当前仅作研究背景; 统计、独立留出与规则版本门槛尚未全部通过,"
        "不依据该信号调整权益仓位。"
    )

    def fail_closed_summary() -> None:
        """Preserve the raw model narrative but remove binding action language."""
        current_summary = spy_early_warning.get("summary")
        prior_context = spy_early_warning.get("contextSummary")
        if (
            not (isinstance(prior_context, str) and prior_context.strip())
            and isinstance(current_summary, str)
            and current_summary.strip()
            and current_summary != research_only_summary
        ):
            spy_early_warning["contextSummary"] = current_summary
        spy_early_warning["summary"] = research_only_summary

    def publish_production_summary() -> None:
        """Restore the preserved model narrative after every production gate passes."""
        context_summary = spy_early_warning.get("contextSummary")
        if isinstance(context_summary, str) and context_summary.strip():
            spy_early_warning["summary"] = context_summary

    def fail_closed_allocation(hedge_action: str) -> None:
        """Move a raw band to context without erasing it on repeated binds."""
        allocation = spy_early_warning.get("allocation")
        if not isinstance(allocation, dict):
            return
        prior_context = spy_early_warning.get("contextAllocation")
        if allocation.get("exposureBandPct") is not None:
            context_allocation = dict(allocation)
            spy_early_warning["contextAllocation"] = context_allocation
        elif isinstance(prior_context, dict):
            context_allocation = dict(prior_context)
        else:
            context_allocation = dict(allocation)
            spy_early_warning["contextAllocation"] = context_allocation
        spy_early_warning["allocation"] = {
            "horizon": str(context_allocation.get("horizon") or "1-3M"),
            "horizonCn": str(context_allocation.get("horizonCn") or "1-3个月"),
            "regime": str(context_allocation.get("regime") or spy_early_warning.get("regime") or "Research"),
            "regimeCn": str(context_allocation.get("regimeCn") or spy_early_warning.get("regimeCn") or "研究观察"),
            "stance": "研究观察",
            "equityExposure": "不依据该信号调整权益仓位",
            "exposureBandPct": None,
            "hedgeAction": hedge_action,
            "tone": "neutral",
            "actionable": False,
        }

    def publish_production_allocation() -> None:
        """Restore the preserved research band if a later bind becomes valid."""
        allocation = spy_early_warning.get("allocation")
        if not isinstance(allocation, dict):
            return
        context_allocation = spy_early_warning.get("contextAllocation")
        if (
            allocation.get("exposureBandPct") is None
            and isinstance(context_allocation, dict)
            and context_allocation.get("exposureBandPct") is not None
        ):
            allocation = dict(context_allocation)
            spy_early_warning["allocation"] = allocation
        allocation["actionable"] = True

    if isinstance(agg, dict) and "robust" in agg:
        statistical_gate_passed = agg.get("actionableRobust") is True
        production_gate_passed = (
            statistical_gate_passed
            and independent_holdout
            and rules_version_matched
        )
        spy_early_warning["aggregateCiRobust"] = bool(agg.get("robust"))
        spy_early_warning["aggregateStatisticalGatePassed"] = statistical_gate_passed
        spy_early_warning["aggregateActionableRobust"] = production_gate_passed
        # Compatibility field carries the production gate, including holdout independence.
        spy_early_warning["aggregateRobust"] = production_gate_passed
        spy_early_warning["aggregateOosCi3m"] = agg.get("oosCi3m")
        spy_early_warning["predictiveValidity"] = {
            "status": "actionable" if production_gate_passed else "research-context",
            "actionable": production_gate_passed,
            "oosIc3m": agg.get("oosIc3m"),
            "oosCi3m": agg.get("oosCi3m"),
            "fdrSignificant3m": agg.get("fdrSignificant3m"),
            "foldStable": bool(
                isinstance(agg.get("foldStability3m"), dict)
                and agg["foldStability3m"].get("stablePositive") is True
            ),
            "statisticalGatePassed": statistical_gate_passed,
            "independentHoldout": independent_holdout,
            "rulesVersionAudit": rules_version_audit,
            "reason": (
                version_failure_reason
                if version_failure_reason
                else "通过统计完整性、独立留出与规则版本一致性门槛,可发布动作层。"
                if production_gate_passed
                else "统计门槛已通过,但验证尾段并非独立留出,仅作研究背景。"
                if statistical_gate_passed
                else "聚合信号未通过CI、FDR与分折一致性的完整门槛,仅作研究背景。"
            ),
        }
        if production_gate_passed:
            publish_production_summary()
        allocation = spy_early_warning.get("allocation")
        if isinstance(allocation, dict):
            if production_gate_passed:
                publish_production_allocation()
                spy_early_warning["actionable"] = True
                spy_early_warning["scoreUse"] = "production_signal"
            else:
                fail_closed_allocation("等待聚合信号通过完整样本外门槛")
        if not production_gate_passed:
            fail_closed_summary()
            spy_early_warning["actionable"] = False
            spy_early_warning["scoreUse"] = "research_only"
    else:
        # Missing validation is not neutral evidence.  It is the least certain
        # state and must fail closed instead of leaving the raw research band in
        # the binding allocation field.
        spy_early_warning["aggregateCiRobust"] = False
        spy_early_warning["aggregateStatisticalGatePassed"] = False
        spy_early_warning["aggregateActionableRobust"] = False
        spy_early_warning["aggregateRobust"] = False
        spy_early_warning["aggregateOosCi3m"] = None
        spy_early_warning["predictiveValidity"] = {
            "status": "research-context",
            "actionable": False,
            "oosIc3m": None,
            "oosCi3m": None,
            "fdrSignificant3m": False,
            "foldStable": False,
            "statisticalGatePassed": False,
            "independentHoldout": independent_holdout,
            "rulesVersionAudit": rules_version_audit,
            "reason": (
                "缺少SPY聚合样本外验证证据; "
                f"{version_failure_reason or '规则版本无法与聚合证据绑定。'}"
            ),
        }
        allocation = spy_early_warning.get("allocation")
        if isinstance(allocation, dict):
            fail_closed_allocation("等待聚合信号完成样本外验证")
        fail_closed_summary()
        spy_early_warning["actionable"] = False
        spy_early_warning["scoreUse"] = "research_only"
    statistical_sleeves = [
        cid.split(":", 1)[1]
        for cid, c in by_id.items()
        if cid.startswith("sleeve:") and c.get("actionableRobust") and (optional_float(c.get("oosIc3m")) or 0.0) > 0
    ]
    versioned_holdout = independent_holdout and rules_version_matched
    spy_early_warning["researchRobustSleeves"] = [] if versioned_holdout else statistical_sleeves
    spy_early_warning["robustSleeves"] = statistical_sleeves if versioned_holdout else []
    spy_early_warning["exploratorySleeves"] = [
        cid.split(":", 1)[1]
        for cid, c in by_id.items()
        if (
            cid.startswith("sleeve:")
            and c.get("robust")
            and (not c.get("actionableRobust") or not versioned_holdout)
            and (optional_float(c.get("oosIc3m")) or 0.0) > 0
        )
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
    split_index = max(
        0,
        min(len(week_targets) - 1, int(len(week_targets) * SIGNAL_VALIDATION_OOS_SPLIT)),
    )
    oos_start = week_targets[split_index] if week_targets else None
    purge_horizon_days = 91
    purge_payload: dict[str, Any] = {
        "applied": oos_start is not None,
        "horizonDays": purge_horizon_days,
        "oosStartDate": oos_start.isoformat() if oos_start is not None else None,
        "rule": (
            "actual first price endpoint on/after calibration signal date + 91 calendar days "
            "must be strictly before the OOS start date"
        ),
        "purgedObservationCount": 0,
        "latestEligibleSignalDate": None,
        "latestEligibleLabelEndDate": None,
    }
    selected: list[dict[str, Any]] = []
    for factor_id in sorted(factor_series):
        points = factor_series[factor_id]
        if len(points) < MIN_SIGNAL_VALIDATION_POINTS:
            continue
        pre_oos = [point for point in points if oos_start is None or point.date < oos_start]
        calibration: list[SeriesPoint] = []
        calibration_end_dates: dict[date, date] = {}
        for point in pre_oos:
            endpoint_index = prices_sorted.index_at_or_after(
                point.date + timedelta(days=purge_horizon_days)
            )
            endpoint_date = (
                prices_sorted.dates[endpoint_index]
                if endpoint_index is not None
                else None
            )
            if (
                oos_start is None
                or (endpoint_date is not None and endpoint_date < oos_start)
            ):
                calibration.append(point)
                if endpoint_date is not None:
                    calibration_end_dates[point.date] = endpoint_date
        purge_payload["purgedObservationCount"] += len(pre_oos) - len(calibration)
        if calibration:
            latest_signal_date = calibration[-1].date
            latest_label_end = calibration_end_dates.get(latest_signal_date)
            current_latest = purge_payload.get("latestEligibleSignalDate")
            if current_latest is None or latest_signal_date.isoformat() > str(current_latest):
                purge_payload["latestEligibleSignalDate"] = latest_signal_date.isoformat()
                purge_payload["latestEligibleLabelEndDate"] = (
                    latest_label_end.isoformat() if latest_label_end is not None else None
                )
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
        selected.append(
            {
                "id": factor_id,
                "calibrationIc": round(consistent_ic, 3),
                "calibrationSampleSize": len(calibration),
                "calibrationEndDate": calibration[-1].date.isoformat() if calibration else None,
            }
        )
    if len(selected) < min_factors:
        return {
            "available": False,
            "reason": f"校准段达标的领先因子不足{min_factors}个,预测镜头暂不发布。",
            "selectedFactors": selected,
            "purge": purge_payload,
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
            # BhadialWeeklyReplay owns the publication cutoff.  Passing the
            # decision date here avoids silently applying the factor lag twice.
            score, observed = replay.factor_score_at(spec, target)
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
            "with a 91-calendar-day purge before the common OOS boundary, weighted by "
            "redundancy-adjusted effective weights, and replayed with per-factor publication lags."
        ),
        "selectedFactors": selected,
        "purge": purge_payload,
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
