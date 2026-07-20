"""Regional-monitor domain extracted from build_dashboard.py (behavior-unchanged,
2026-06-19 全面重构 Phase 1). First-class regions (US groups SPY+QQQ) with per-region
LPPL+price factors: regional monitor grouping, diversification/correlation clustering,
per-region factor alerts + allocation + cross-region rotation, and US-internal (SPY vs
QQQ) rotation. Consumes the global LPPL risk dict as data; the lppl<->regional factor-
validation bridges stay in build_dashboard. Re-exported via `from .scoring_regional import *`.

Note: the US representative index is selected by US_INTERNAL_BROAD_SYMBOL ("SPY"), which is
value-identical to the monolith's GLOBAL_LPPL_US_BENCHMARK_SYMBOL it replaced here (decouple
from LPPL-orchestration config; runtime value unchanged)."""
from __future__ import annotations

from datetime import date
from typing import Any

from .sources import SeriesPoint
from .dashboard_core import *  # noqa: F401,F403
from .series_math import *  # noqa: F401,F403
from .signal_validation import SortedSeries, pearson_correlation, weekly_dates


REGIONAL_MONITOR_ORDER = ["us", "korea", "hongkong", "taiwan", "japan"]
REGION_STATUS_SEVERITY = {"risk": 3, "watch": 2, "quiet": 1, "missing": 0, "": 0}


def build_regional_monitor(global_lppl_risk: dict[str, Any] | None) -> dict[str, Any]:
    """Group the per-index LPPL factors into first-class regions (US groups SPY+QQQ)
    so the dashboard can surface region-distinguished factors at the top level instead
    of burying HK/TW/JP as 'ETF proxy' sub-rows. Purely a regrouping of existing index
    rows. Canonical history/backtest maps are hydrated only for calculations and
    replaced with lightweight refs at the serialized regional boundary."""
    indices = global_lppl_risk.get("indices") if isinstance(global_lppl_risk, dict) else None
    if not isinstance(indices, list) or not indices:
        return {"available": False, "reason": "缺少逐指数LPPL数据,暂不能按地区拆分。", "regions": []}

    history_by_symbol = (
        global_lppl_risk.get("perIndexHistory", {})
        if isinstance(global_lppl_risk, dict) and isinstance(global_lppl_risk.get("perIndexHistory"), dict)
        else {}
    )
    backtest_by_symbol = (
        global_lppl_risk.get("perIndexBacktests", {})
        if isinstance(global_lppl_risk, dict) and isinstance(global_lppl_risk.get("perIndexBacktests"), dict)
        else {}
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    meta: dict[str, dict[str, str]] = {}
    for row in indices:
        if not isinstance(row, dict):
            continue
        working_row = hydrate_regional_index_row(row, history_by_symbol, backtest_by_symbol)
        key = str(working_row.get("regionKey") or "").strip() or "other"
        grouped.setdefault(key, []).append(working_row)
        if key not in meta:
            meta[key] = {
                "name": str(working_row.get("regionName") or working_row.get("region") or key),
                "nameCn": str(working_row.get("regionNameCn") or working_row.get("regionName") or key),
            }

    ordered_keys = [key for key in REGIONAL_MONITOR_ORDER if key in grouped]
    ordered_keys += [key for key in grouped if key not in REGIONAL_MONITOR_ORDER]

    regions: list[dict[str, Any]] = []
    for key in ordered_keys:
        rows = grouped[key]
        region = {
            "key": key,
            "name": meta[key]["name"],
            "nameCn": meta[key]["nameCn"],
            "indices": rows,
            "aggregate": regional_monitor_aggregate(rows),
        }
        if region["aggregate"]["availableCount"] > 0:
            region["factorAlert"] = build_region_factor_alert(region)
            region["allocation"] = build_region_allocation(region)
            if region["key"] == "us" and len(region["indices"]) >= 2:
                region["internalRotation"] = build_us_internal_rotation(region)
        regions.append(region)
    available_regions = [region for region in regions if region["aggregate"]["availableCount"] > 0]
    raw_alerting = [region for region in available_regions if region["aggregate"]["status"] == "risk"]
    alerting = [
        region
        for region in raw_alerting
        if int(region["aggregate"].get("actionableRiskCount") or 0) > 0
    ]
    diversification = build_regional_diversification(regions)
    return {
        "available": bool(available_regions),
        "asOf": str(global_lppl_risk.get("asOf") or ""),
        "method": (
            "Region-grouped LPPL bubble factors (US groups SPY+QQQ; Korea/HK/Taiwan/Japan via US-listed "
            "ETF proxies). Each region carries its own indices' bubble fit, critical-date window, validation "
            "and forward signal; region status is the worst constituent status."
        ),
        "regionOrder": [region["key"] for region in regions],
        "alertingRegions": [region["key"] for region in alerting],
        "rawAlertingRegions": [region["key"] for region in raw_alerting],
        "summary": regional_monitor_summary(available_regions, alerting, raw_alerting=raw_alerting),
        "rotation": build_regional_rotation(regions, diversification),
        "diversification": diversification,
        "regions": compact_regional_regions(regions),
    }


def hydrate_regional_index_row(
    row: dict[str, Any],
    history_by_symbol: dict[str, Any],
    backtest_by_symbol: dict[str, Any],
) -> dict[str, Any]:
    """Resolve canonical LPPL refs for calculations without serializing copies."""
    hydrated = dict(row)
    symbol = str(row.get("symbol") or "").upper()
    if symbol and not isinstance(hydrated.get("history"), dict):
        history = history_by_symbol.get(symbol)
        if isinstance(history, dict):
            hydrated["history"] = history
    if symbol and not isinstance(hydrated.get("backtest"), dict):
        backtest = backtest_by_symbol.get(symbol)
        if isinstance(backtest, dict):
            hydrated["backtest"] = backtest
    return hydrated


REGIONAL_INDEX_SUMMARY_FIELDS = (
    "symbol",
    "name",
    "region",
    "regionKey",
    "regionName",
    "regionNameCn",
    "proxyNote",
    "proxyNoteCn",
    "source",
    "sourceSymbol",
    "sourceQuality",
    "available",
    "score",
    "confidence",
    "status",
    "statusCn",
    "criticalDate",
    "daysToCritical",
    "daysToCriticalRange",
    "fitR2",
    "windowDays",
    "asOf",
    "reason",
    "effectiveWeightMultiplier",
    "clipState",
    "tcAggregation",
    "forwardSignal",
    "priceFactors",
    "validation",
    "fitProductionEligible",
    "productionEligible",
    "actionable",
    "actionabilityStatus",
    "scoreUse",
    "factorValidation",
)


def compact_regional_index_row(row: dict[str, Any]) -> dict[str, Any]:
    """Keep only the index summary needed by the regional UI plus canonical refs."""
    compact = {key: row[key] for key in REGIONAL_INDEX_SUMMARY_FIELDS if key in row}
    symbol = str(row.get("symbol") or "").upper()
    if symbol:
        compact["globalIndexRef"] = {"symbol": symbol, "collection": "globalLpplRisk.indices"}
        compact["historyRef"] = {"symbol": symbol, "path": f"globalLpplRisk.perIndexHistory.{symbol}"}
        compact["backtestRef"] = {"symbol": symbol, "path": f"globalLpplRisk.perIndexBacktests.{symbol}"}
    return compact


def compact_regional_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact_regions: list[dict[str, Any]] = []
    for region in regions:
        compact = dict(region)
        indices = region.get("indices", []) if isinstance(region.get("indices"), list) else []
        compact["indices"] = [compact_regional_index_row(row) for row in indices if isinstance(row, dict)]
        compact_regions.append(compact)
    return compact_regions


def regional_monitor_aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in rows if row.get("available") and optional_float(row.get("score")) is not None]
    statuses = [str(row.get("status") or "") for row in available]
    worst_status = max(statuses, key=lambda s: REGION_STATUS_SEVERITY.get(s, 0)) if statuses else "missing"
    worst_cn = next((str(row.get("statusCn") or "") for row in available if str(row.get("status")) == worst_status), "缺失")
    scores = [optional_float(row.get("score")) for row in available]
    scores = [value for value in scores if value is not None]
    # Nearest critical window only counts rows that are actually flagged (risk/watch).
    flagged_days = [
        optional_float(row.get("daysToCritical"))
        for row in available
        if str(row.get("status")) in {"risk", "watch"} and optional_float(row.get("daysToCritical")) is not None
    ]
    factor_rows = [row.get("priceFactors") for row in available if isinstance(row.get("priceFactors"), dict) and row["priceFactors"].get("available")]
    production_eligible = [row for row in available if row.get("productionEligible") is True]
    actionable = [row for row in available if regional_lppl_index_qualifies_as_actionable(row)]
    actionable_risk = [row for row in actionable if str(row.get("status") or "") in {"risk", "watch"}]
    return {
        "status": worst_status,
        "statusCn": worst_cn,
        "maxScore": round(max(scores), 1) if scores else None,
        "minDaysToCritical": min(flagged_days) if flagged_days else None,
        "availableCount": len(available),
        "indexCount": len(rows),
        "productionEligibleCount": len(production_eligible),
        "actionableCount": len(actionable),
        "actionableRiskCount": len(actionable_risk),
        "scoreUse": "production_signal" if actionable_risk else "raw_context",
        "priceFactors": regional_price_factor_rollup(factor_rows),
    }


def regional_price_factor_rollup(factor_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not factor_rows:
        return {"available": False}
    return_3m = average_optional([row.get("return3m") for row in factor_rows])
    realized_vol = average_optional([row.get("realizedVol") for row in factor_rows])
    relative_rows = [row.get("relativeStrength3m") for row in factor_rows if not row.get("isBenchmark")]
    relative_strength = average_optional(relative_rows)
    drawdowns = [optional_float(row.get("drawdownFromHigh")) for row in factor_rows]
    drawdowns = [value for value in drawdowns if value is not None]
    # Region market-state = worst constituent state (stressed > neutral > constructive).
    state_severity = {"stressed": 2, "neutral": 1, "constructive": 0}
    states = [str(row.get("marketState") or "neutral") for row in factor_rows]
    worst_state = max(states, key=lambda s: state_severity.get(s, 1)) if states else "neutral"
    worst_state_cn = {"stressed": "承压", "neutral": "中性", "constructive": "偏强"}[worst_state]
    # return3m / realizedVol / relativeStrength3m on each row are already percentages
    # (pct_metric scaled at the index level), so average-then-round here — do not rescale.
    return {
        "available": True,
        "return3m": round(return_3m, 2) if return_3m is not None else None,
        "realizedVol": round(realized_vol, 2) if realized_vol is not None else None,
        "relativeStrength3m": round(relative_strength, 2) if relative_strength is not None else None,
        "worstDrawdownFromHigh": round(min(drawdowns), 1) if drawdowns else None,
        "marketState": worst_state,
        "marketStateCn": worst_state_cn,
    }


REGIONAL_DIVERSIFICATION_MIN_OVERLAP = 26


def region_weekly_returns(representative: dict[str, Any]) -> dict[date, float]:
    """Weekly returns for a region derived from its representative index's daily history closes."""
    history = representative.get("history") if isinstance(representative.get("history"), dict) else {}
    points = history.get("points", []) if isinstance(history, dict) else []
    close_points: list[SeriesPoint] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        close = optional_float(point.get("close"))
        try:
            point_date = date.fromisoformat(str(point.get("date")))
        except (TypeError, ValueError):
            continue
        if close is not None and close > 0:
            close_points.append(SeriesPoint(date=point_date, value=close))
    if len(close_points) < REGIONAL_DIVERSIFICATION_MIN_OVERLAP + 1:
        return {}
    sorted_closes = SortedSeries(close_points)
    week_dates = weekly_dates(close_points, years=5)
    returns: dict[date, float] = {}
    previous_close: float | None = None
    for target in week_dates:
        close = sorted_closes.value_at_or_before(target)
        if close is not None and previous_close is not None and previous_close > 0:
            returns[target] = close / previous_close - 1
        if close is not None:
            previous_close = close
    return returns


def build_regional_diversification(regions: list[dict[str, Any]]) -> dict[str, Any]:
    """Pairwise correlation of regions' weekly returns → which regions co-move (redundant
    risk) and which diversify. Lower average correlation = better diversifier."""
    returns_by_key: dict[str, dict[date, float]] = {}
    name_by_key: dict[str, str] = {}
    for region in regions:
        if region.get("aggregate", {}).get("availableCount", 0) <= 0:
            continue
        representative = regional_representative_index(region.get("indices", []) if isinstance(region.get("indices"), list) else [])
        if representative is None:
            continue
        weekly = region_weekly_returns(representative)
        if weekly:
            returns_by_key[region["key"]] = weekly
            name_by_key[region["key"]] = str(region.get("nameCn") or region.get("name") or region["key"])
    keys = sorted(returns_by_key)
    if len(keys) < 2:
        return {"available": False, "reason": "可用地区不足两个,暂不能做相关性分析。", "matrix": []}

    matrix: list[dict[str, Any]] = []
    corr_lookup: dict[tuple[str, str], float] = {}
    for index, first in enumerate(keys):
        for second in keys[index + 1:]:
            shared = sorted(set(returns_by_key[first]) & set(returns_by_key[second]))
            if len(shared) < REGIONAL_DIVERSIFICATION_MIN_OVERLAP:
                continue
            corr = pearson_correlation([returns_by_key[first][d] for d in shared], [returns_by_key[second][d] for d in shared])
            if corr is None:
                continue
            corr_lookup[(first, second)] = corr
            matrix.append({"a": first, "aCn": name_by_key[first], "b": second, "bCn": name_by_key[second], "corr": round(corr, 2)})
    if not matrix:
        return {"available": False, "reason": "地区周度收益重叠不足,暂不能做相关性分析。", "matrix": []}

    region_stats: list[dict[str, Any]] = []
    for key in keys:
        pair_corrs = [corr for (a, b), corr in corr_lookup.items() if key in (a, b)]
        if pair_corrs:
            region_stats.append({"key": key, "nameCn": name_by_key[key], "avgCorr": round(sum(pair_corrs) / len(pair_corrs), 2)})
    region_stats.sort(key=lambda item: item["avgCorr"])
    most_correlated = max(matrix, key=lambda item: item["corr"])
    best_diversifier = region_stats[0] if region_stats else None
    summary_parts = [
        f"{most_correlated['aCn']}与{most_correlated['bCn']}相关性最高({most_correlated['corr']:+.2f}, 同涨同跌、分散价值低)"
    ]
    if best_diversifier is not None:
        summary_parts.append(f"{best_diversifier['nameCn']}平均相关性最低({best_diversifier['avgCorr']:+.2f}, 分散价值最高)")
    return {
        "available": True,
        "method": "各地区代表指数周度收益两两 Pearson 相关; 高相关=同向风险冗余, 低/负相关=分散价值。",
        "matrix": matrix,
        "regionStats": region_stats,
        "mostCorrelatedPair": most_correlated,
        "bestDiversifier": best_diversifier,
        "summary": "; ".join(summary_parts) + "。",
    }


def regional_monitor_summary(
    available_regions: list[dict[str, Any]],
    alerting: list[dict[str, Any]],
    *,
    raw_alerting: list[dict[str, Any]] | None = None,
) -> str:
    if not available_regions:
        return "暂无可用地区LPPL样本。"
    if alerting:
        names = "、".join(region["nameCn"] for region in alerting)
        return f"{len(available_regions)}个地区在监控; {names}的LPPL通过生产门槛且当前触发,其余地区无生产级泡沫预警。"
    raw_alerting = raw_alerting or []
    if raw_alerting:
        names = "、".join(region["nameCn"] for region in raw_alerting)
        return f"{len(available_regions)}个地区在监控; {names}原始LPPL处于风险区,但未通过生产门槛,仅作研究背景。"
    return f"{len(available_regions)}个地区在监控,均未触发泡沫临界风险。"


# Factor ids whose high readings mean MORE risk (used to gate evidence-backed caution).
REGIONAL_RISK_FACTOR_IDS = {"lpplScore", "realizedVol"}
REGIONAL_ACTIONABLE_MIN_OBSERVATIONS = 60
REGIONAL_ACTIONABLE_MIN_OOS_OBSERVATIONS = 20
REGIONAL_ACTIONABLE_MIN_OOS_ALERTS = 3


def regional_representative_index(indices: list[dict[str, Any]]) -> dict[str, Any] | None:
    validated = [
        row for row in indices
        if isinstance(row, dict)
        and isinstance(row.get("factorValidation"), dict)
        and row["factorValidation"].get("available")
    ]
    if not validated:
        return None
    return next(
        (row for row in validated if str(row.get("symbol") or "").upper() == US_INTERNAL_BROAD_SYMBOL),
        validated[0],
    )


def regional_signal_qualifies_as_actionable(signal: dict[str, Any] | None) -> bool:
    """Fail-closed actionable gate shared by regional factors and composites.

    ``classification`` and lift describe usefulness, but are not sufficient evidence on
    their own.  A regional signal must also be positively oriented out of sample, pass
    the bootstrap/FDR/fold checks, and have enough raw observations and alert events.
    """
    if not isinstance(signal, dict) or signal.get("available") is False:
        return False
    fold_stability = signal.get("foldStability3m") if isinstance(signal.get("foldStability3m"), dict) else {}
    oos_ic = optional_float(signal.get("oosIc3m"))
    observation_count = optional_float(signal.get("observationCount")) or 0.0
    oos_sample_size = optional_float(signal.get("oosSampleSize3m")) or 0.0
    oos_alert_count = optional_float(signal.get("oosAlertCount")) or 0.0
    return bool(
        str(signal.get("classification") or "") == "leading"
        and oos_ic is not None
        and oos_ic > 0.0
        and signal.get("wrongWay") is False
        and (optional_float(signal.get("lift")) or 0.0) > 1.0
        and signal.get("robust") is True
        and signal.get("fdrSignificant3m") is True
        and signal.get("inferenceValid3m") is True
        and fold_stability.get("stablePositive") is True
        and signal.get("actionableRobust") is True
        and observation_count >= REGIONAL_ACTIONABLE_MIN_OBSERVATIONS
        and oos_sample_size >= REGIONAL_ACTIONABLE_MIN_OOS_OBSERVATIONS
        and oos_alert_count >= REGIONAL_ACTIONABLE_MIN_OOS_ALERTS
    )


def regional_lppl_index_qualifies_as_actionable(row: dict[str, Any] | None) -> bool:
    """Require the complete current LPPL production audit, not a legacy true flag.

    Regional payloads can be rebuilt from a last-known-good global LPPL block.  Older
    blocks may contain ``actionable``/``productionEligible`` booleans without the
    replay-comparability audit that now defines a production trigger.  Treat those
    rows as research context so a cache fallback cannot restore a binding allocation.
    """
    if not isinstance(row, dict) or row.get("available") is not True:
        return False
    validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
    score = optional_float(row.get("score"))
    threshold = optional_float(validation.get("productionThreshold"))
    model_audit = validation.get("replayModelAudit") if isinstance(validation.get("replayModelAudit"), dict) else {}
    production_model_id = str(model_audit.get("productionModelSpecId") or "")
    live_model_id = str(model_audit.get("liveModelSpecId") or "")
    observed_model_ids = model_audit.get("observedModelSpecIds")
    observation_count = int(optional_float(model_audit.get("observationCount")) or 0)
    comparable_count = int(optional_float(model_audit.get("comparableObservationCount")) or 0)
    complete_model_audit = bool(
        model_audit.get("required") is True
        and model_audit.get("enforcementPass") is True
        and model_audit.get("status") == "comparable"
        and model_audit.get("comparable") is True
        and model_audit.get("replayComparable") is True
        and model_audit.get("liveComparable") is True
        and model_audit.get("liveModelMetadataAvailable") is True
        and model_audit.get("liveValidationComparable") is True
        and production_model_id
        and live_model_id == production_model_id
        and observed_model_ids == [production_model_id]
        and observation_count > 0
        and comparable_count == observation_count
        and int(optional_float(model_audit.get("unknownModelSpecCount")) or 0) == 0
        and int(optional_float(model_audit.get("mismatchedModelSpecCount")) or 0) == 0
    )
    return bool(
        row.get("fitProductionEligible") is True
        and row.get("productionEligible") is True
        and row.get("actionable") is True
        and row.get("scoreUse") == "production_signal"
        and row.get("actionabilityStatus") == "current_threshold_triggered"
        and validation.get("productionEvidenceAvailable") is True
        and validation.get("productionActionable") is True
        and complete_model_audit
        and score is not None
        and threshold is not None
        and score >= threshold
    )


def regional_lppl_region_has_current_trigger(region: dict[str, Any]) -> bool:
    aggregate = region.get("aggregate") if isinstance(region.get("aggregate"), dict) else {}
    if int(aggregate.get("actionableRiskCount") or 0) <= 0:
        return False
    indices = region.get("indices") if isinstance(region.get("indices"), list) else []
    return any(
        regional_lppl_index_qualifies_as_actionable(row)
        and str(row.get("status") or "") in {"risk", "watch"}
        for row in indices
        if isinstance(row, dict)
    )


def region_validated_leading_factors(factor_validation: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Factors that pass the region's complete actionable walk-forward gate."""
    if (
        not isinstance(factor_validation, dict)
        or not factor_validation.get("available")
        or factor_validation.get("independentHoldout") is not True
    ):
        return []
    leading: list[dict[str, Any]] = []
    for factor in factor_validation.get("factors", []):
        if not regional_signal_qualifies_as_actionable(factor):
            continue
        lift = optional_float(factor.get("lift"))
        leading.append(
            {
                "id": str(factor.get("id") or ""),
                "labelCn": str(factor.get("labelCn") or factor.get("label") or ""),
                "lift": round(lift, 2) if lift is not None else None,
                "oosIc3m": optional_float(factor.get("oosIc3m")),
                "leadTimeDays": optional_float(factor.get("leadTimeDays")),
            }
        )
    return sorted(leading, key=lambda item: item["lift"] or 0.0, reverse=True)


def composite_qualifies_as_alert(composite: dict[str, Any], *, independent_holdout: bool) -> bool:
    return bool(
        independent_holdout
        and
        regional_signal_qualifies_as_actionable(composite)
        and composite.get("available") is True
        and composite.get("beatsBestSingleFactor") is True
        and str(composite.get("direction") or "") == "higher_risk"
        and composite.get("currentValue") is not None
        and composite.get("alertThreshold") is not None
    )


def build_region_factor_alert(region: dict[str, Any]) -> dict[str, Any]:
    """Live early-warning: compare a region's CURRENT reading of its strongest OOS-validated
    leading RISK signal to its calibrated alert threshold. Prefers the evidence-weighted
    COMPOSITE when the composite is validated and at least matches the best single factor;
    otherwise falls back to the single strongest validated risk factor."""
    representative = regional_representative_index(region.get("indices", []) if isinstance(region.get("indices"), list) else [])
    if representative is None:
        return {"available": False}
    factor_validation = representative.get("factorValidation") if isinstance(representative.get("factorValidation"), dict) else {}
    composite = factor_validation.get("composite") if isinstance(factor_validation.get("composite"), dict) else {}

    independent_holdout = factor_validation.get("independentHoldout") is True
    if composite_qualifies_as_alert(composite, independent_holdout=independent_holdout):
        source, label, factor_id = "composite", "证据加权综合信号", "regionComposite"
        current = optional_float(composite.get("currentValue"))
        threshold = optional_float(composite.get("alertThreshold"))
        hit = optional_float(composite.get("hitRateOos"))
        base = optional_float(composite.get("baseRate"))
        lead = optional_float(composite.get("leadTimeDays"))
        lift = optional_float(composite.get("lift"))
        breach_count_total = composite.get("breachCountTotal")
        hit_rate_total = optional_float(composite.get("breachHitRateTotal"))
        breach_events = composite.get("breachEvents", [])
        digits = 2
    else:
        validated = region_validated_leading_factors(factor_validation)
        risk_validated = [factor for factor in validated if factor["id"] in REGIONAL_RISK_FACTOR_IDS]
        if not risk_validated:
            return {"available": False}
        top = risk_validated[0]
        factor_row = next(
            (item for item in factor_validation.get("factors", []) if isinstance(item, dict) and item.get("id") == top["id"]),
            {},
        )
        source, label, factor_id = "factor", top["labelCn"], top["id"]
        threshold = optional_float(factor_row.get("alertThreshold"))
        current = region_current_factor_reading(top["id"], representative)
        hit = optional_float(factor_row.get("hitRateOos"))
        base = optional_float(factor_row.get("baseRate"))
        lead = optional_float(factor_row.get("leadTimeDays"))
        lift = optional_float(top.get("lift"))
        breach_count_total = factor_row.get("alertCountTotal")
        hit_rate_total = optional_float(factor_row.get("hitRateTotal"))
        breach_events = factor_row.get("breachEvents", [])
        digits = 1

    if threshold is None or current is None:
        return {"available": False}
    if current >= threshold:
        state, state_cn = "breached", "已突破"
    elif current >= threshold * 0.9:
        state, state_cn = "approaching", "逼近"
    else:
        state, state_cn = "normal", "正常"
    evidence = ""
    if hit is not None and base is not None:
        evidence = f"历史命中 {hit * 100:.0f}% vs 基准 {base * 100:.0f}%"
        if lead is not None:
            evidence += f"、提前{lead:.0f}天"
    track_record = ""
    if breach_count_total is not None and hit_rate_total is not None:
        track_record = f"历史共突破{int(breach_count_total)}次, 命中{hit_rate_total * 100:.0f}%"
    state_word = "突破" if state == "breached" else "逼近" if state == "approaching" else "低于"
    current_triggered = state == "breached"
    return {
        "available": True,
        "actionable": current_triggered,
        "scoreUse": "production_signal" if current_triggered else "research_only",
        "source": source,
        "factorId": factor_id,
        "factorLabelCn": label,
        "current": round(current, digits),
        "threshold": round(threshold, digits),
        "state": state,
        "stateCn": state_cn,
        "lift": lift,
        "leadTimeDays": lead,
        "evidence": evidence,
        "breachCountTotal": breach_count_total,
        "breachHitRateTotal": hit_rate_total,
        "breachEvents": breach_events[-12:] if isinstance(breach_events, list) else [],
        "trackRecord": track_record,
        "message": (
            f"{label} {current:.{digits}f} {state_word}验证阈值 {threshold:.{digits}f}"
            + (f"; {evidence}" if evidence else "")
            + (f"; {track_record}" if track_record else "")
        ),
    }


def regional_factor_alert_qualifies_as_actionable(region: dict[str, Any]) -> bool:
    """Verify that a serialized regional breach still has its full evidence chain."""
    alert = region.get("factorAlert") if isinstance(region.get("factorAlert"), dict) else {}
    if not (
        alert.get("available") is True
        and alert.get("state") == "breached"
        and alert.get("actionable") is True
        and alert.get("scoreUse") == "production_signal"
    ):
        return False
    representative = regional_representative_index(
        region.get("indices", []) if isinstance(region.get("indices"), list) else []
    )
    if representative is None:
        return False
    factor_validation = (
        representative.get("factorValidation")
        if isinstance(representative.get("factorValidation"), dict)
        else {}
    )
    if factor_validation.get("independentHoldout") is not True:
        return False
    source = str(alert.get("source") or "")
    factor_id = str(alert.get("factorId") or "")
    if source == "composite":
        composite = factor_validation.get("composite")
        return bool(
            isinstance(composite, dict)
            and composite_qualifies_as_alert(composite, independent_holdout=True)
            and factor_id == "regionComposite"
        )
    if source != "factor":
        return False
    return factor_id in {
        str(factor.get("id") or "")
        for factor in region_validated_leading_factors(factor_validation)
        if factor.get("id") in REGIONAL_RISK_FACTOR_IDS
    }


def region_current_factor_reading(factor_id: str, representative: dict[str, Any]) -> float | None:
    """Current reading of a validated factor on its representative index, in the SAME units
    the validation series used (realizedVol as annualized %, lpplScore 0-100)."""
    if factor_id == "realizedVol":
        price_factors = representative.get("priceFactors") if isinstance(representative.get("priceFactors"), dict) else {}
        return optional_float(price_factors.get("realizedVol"))
    if factor_id == "lpplScore":
        return optional_float(representative.get("score"))
    return None


def build_region_allocation(region: dict[str, Any]) -> dict[str, Any]:
    aggregate = region.get("aggregate", {}) if isinstance(region.get("aggregate"), dict) else {}
    price_factors = aggregate.get("priceFactors", {}) if isinstance(aggregate.get("priceFactors"), dict) else {}
    bubble_status = str(aggregate.get("status") or "")
    market_state = str(price_factors.get("marketState") or "neutral")
    relative_strength = optional_float(price_factors.get("relativeStrength3m"))
    representative = regional_representative_index(region.get("indices", []) if isinstance(region.get("indices"), list) else [])
    factor_validation = (
        representative.get("factorValidation")
        if representative and isinstance(representative.get("factorValidation"), dict)
        else {}
    )
    validated = region_validated_leading_factors(factor_validation)
    composite = factor_validation.get("composite") if isinstance(factor_validation.get("composite"), dict) else {}
    validated_composite = bool(
        factor_validation.get("independentHoldout") is True
        and
        regional_signal_qualifies_as_actionable(composite)
        and composite.get("available") is True
        and composite.get("beatsBestSingleFactor") is True
        and str(composite.get("direction") or "") == "higher_risk"
    )

    days_to_critical = optional_float(aggregate.get("minDaysToCritical"))
    lppl_actionable = regional_lppl_region_has_current_trigger(region)
    caution = 0.0
    drivers: list[str] = []
    if bubble_status == "risk":
        if lppl_actionable:
            caution += 40.0
            drivers.append("生产级泡沫临界风险")
        else:
            drivers.append("泡沫临界风险(研究观察)")
    elif bubble_status == "watch":
        if lppl_actionable:
            caution += 18.0
            drivers.append("生产级泡沫观察区")
        else:
            drivers.append("泡沫观察区(研究观察)")
    if market_state == "stressed":
        caution += 30.0
        drivers.append("市场承压(跌破趋势+深回撤)")
    elif market_state == "neutral":
        caution += 10.0
    else:
        drivers.append("市场偏强")
    if relative_strength is not None:
        # Strong momentum tempers but does NOT cancel a validated bubble warning — a leading
        # signal fires while price is still rising, so cap the relief at -8.
        if relative_strength <= -5.0:
            caution += 10.0
            drivers.append(f"跑输美国 {relative_strength:.0f}%")
        elif relative_strength >= 5.0:
            caution -= 8.0
            drivers.append(f"跑赢美国 +{relative_strength:.0f}%")
    # Evidence-backed conviction: a validated leading risk factor while bubble is flagged.
    has_validated_risk_signal = lppl_actionable or validated_composite or any(f["id"] in REGIONAL_RISK_FACTOR_IDS for f in validated)
    if has_validated_risk_signal and bubble_status in {"risk", "watch"}:
        caution += 12.0
        drivers.append("已验证领先信号佐证")
    # Live trigger: the validated leading risk factor has BREACHED its calibrated threshold.
    factor_alert = region.get("factorAlert") if isinstance(region.get("factorAlert"), dict) else {}
    alert_source = str(factor_alert.get("source") or "")
    alert_factor_id = str(factor_alert.get("factorId") or "")
    alert_evidence_eligible = (
        (alert_source == "composite" and validated_composite)
        or (alert_source == "factor" and any(f["id"] == alert_factor_id for f in validated))
    )
    factor_alert_triggered = bool(
        alert_evidence_eligible
        and regional_factor_alert_qualifies_as_actionable(region)
    )
    if factor_alert_triggered:
        caution += 15.0
        drivers.append(f"{factor_alert.get('factorLabelCn') or '领先因子'}突破验证阈值")
    # Imminent LPPL critical window adds urgency.
    if lppl_actionable and days_to_critical is not None and days_to_critical <= 30:
        caution += 10.0
        drivers.append(f"临界窗口仅{days_to_critical:.0f}天")
    elif days_to_critical is not None and days_to_critical <= 30:
        drivers.append(f"临界窗口仅{days_to_critical:.0f}天(研究观察)")
    caution = max(0.0, min(100.0, caution))

    # Overweight requires a genuinely constructive trend AND low caution — not merely the
    # absence of acute risk; a bubble-watch or neutral-trend region stays at most neutral.
    if caution >= 50.0:
        stance, stance_cn, band = "underweight", "减持", [50, 75]
    elif caution <= 10.0 and market_state == "constructive":
        stance, stance_cn, band = "overweight", "增持", [100, 115]
    else:
        stance, stance_cn, band = "neutral", "中性", [80, 100]

    # Model validation establishes that a signal may be useful; it is not a live
    # instruction.  A numeric regional band binds only after a complete current
    # LPPL production trigger or a validated factor/composite breach.  Raw trend,
    # relative strength, untriggered validated models and research-only LPPL stay
    # in context so they cannot silently become allocation instructions.
    allocation_actionable = bool(lppl_actionable or factor_alert_triggered)
    binding_band = band if allocation_actionable else None
    context_band = None if allocation_actionable else band
    confidence = "high" if allocation_actionable else ("medium" if drivers else "low")
    confidence_cn = {"high": "高", "medium": "中", "low": "低"}[confidence]
    return {
        "stance": stance,
        "stanceCn": stance_cn,
        "cautionScore": round(caution, 1),
        "exposureBandPct": binding_band,
        "contextBand": context_band,
        "actionable": allocation_actionable,
        "scoreUse": "production_signal" if allocation_actionable else "research_only",
        "actionabilityStatus": (
            "current_lppl_or_validated_factor_trigger"
            if allocation_actionable
            else "research_context_no_binding_allocation"
        ),
        "confidence": confidence,
        "confidenceCn": confidence_cn,
        "drivers": drivers,
        "validatedLeadingFactors": validated,
        "validatedComposite": validated_composite,
        "validatedFactorTriggered": factor_alert_triggered,
        "productionLpplTriggered": lppl_actionable,
        "rationale": build_region_alloc_rationale(
            region,
            stance_cn,
            bubble_status,
            aggregate,
            price_factors,
            validated,
            validated_composite,
            allocation_actionable,
        ),
    }


def build_region_alloc_rationale(
    region: dict[str, Any],
    stance_cn: str,
    bubble_status: str,
    aggregate: dict[str, Any],
    price_factors: dict[str, Any],
    validated: list[dict[str, Any]],
    validated_composite: bool = False,
    allocation_actionable: bool = False,
) -> str:
    name = str(region.get("nameCn") or region.get("name") or "")
    bubble_cn = str(aggregate.get("statusCn") or "--")
    state_cn = str(price_factors.get("marketStateCn") or "--")
    parts = [f"{name}: 泡沫{bubble_cn}、市场{state_cn}".replace("泡沫泡沫", "泡沫")]
    relative_strength = optional_float(price_factors.get("relativeStrength3m"))
    if relative_strength is not None:
        parts.append(f"相对美国{relative_strength:+.0f}%")
    lppl_actionable = regional_lppl_region_has_current_trigger(region)
    if lppl_actionable:
        parts.append("LPPL模型、预测验证与当前阈值均通过,可作生产级风控信号")
    if validated_composite:
        parts.append("证据加权综合信号通过完整 OOS 门槛,信号可信")
    elif validated:
        top = validated[0]
        lead = top.get("leadTimeDays")
        lead_text = f"、提前{lead:.0f}天" if lead is not None else ""
        parts.append(f"{top['labelCn']}为本地区已验证领先因子(OOS lift {top['lift']}{lead_text}),信号可信")
    else:
        parts.append("尚无 OOS 验证领先因子,信号置信偏低")
    if regional_factor_alert_qualifies_as_actionable(region):
        parts.append("当前已突破经验证的实时阈值")
    if allocation_actionable:
        return "; ".join(parts) + f" → {stance_cn}。"
    return "; ".join(parts) + f" → {stance_cn}仅作研究背景,不发布数值仓位。"


REGIONAL_CORRELATION_CLUSTER_THRESHOLD = 0.7


def cluster_correlated_regions(keys: list[str], diversification: dict[str, Any] | None) -> list[list[str]]:
    """Union-find grouping of regions whose pairwise weekly-return correlation is high
    (>= threshold) — co-moving regions are effectively ONE risk exposure."""
    if not keys:
        return []
    matrix = diversification.get("matrix", []) if isinstance(diversification, dict) else []
    parent = {key: key for key in keys}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    key_set = set(keys)
    for pair in matrix:
        if not isinstance(pair, dict):
            continue
        a, b = str(pair.get("a")), str(pair.get("b"))
        if a in key_set and b in key_set and (optional_float(pair.get("corr")) or 0.0) >= REGIONAL_CORRELATION_CLUSTER_THRESHOLD:
            parent[find(b)] = find(a)
    groups: dict[str, list[str]] = {}
    for key in keys:
        groups.setdefault(find(key), []).append(key)
    # Preserve input order within and across clusters.
    ordered = sorted(groups.values(), key=lambda members: keys.index(members[0]))
    return [sorted(members, key=keys.index) for members in ordered]


US_INTERNAL_BROAD_SYMBOL = "SPY"
US_INTERNAL_TECH_SYMBOL = "QQQ"


def us_index_risk_points(index: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """A small, scale-free risk tally for a US index from its bubble status, LPPL score
    and realized volatility (each compared head-to-head against the other index)."""
    price_factors = index.get("priceFactors") if isinstance(index.get("priceFactors"), dict) else {}
    return 0, {
        "symbol": str(index.get("symbol") or "").upper(),
        "statusSeverity": REGION_STATUS_SEVERITY.get(str(index.get("status") or ""), 0),
        "statusCn": str(index.get("statusCn") or ""),
        "lpplScore": optional_float(index.get("score")),
        "realizedVol": optional_float(price_factors.get("realizedVol")),
        "marketStateCn": str(price_factors.get("marketStateCn") or ""),
    }


def build_us_internal_rotation(us_region: dict[str, Any]) -> dict[str, Any]:
    """US-internal factor rotation: compare broad (SPY) vs tech (QQQ) on bubble status,
    LPPL score and realized vol → tilt toward the lower-risk sleeve. Descriptive risk-control
    overlay within the US bucket, not a return forecast."""
    indices = {str(i.get("symbol") or "").upper(): i for i in us_region.get("indices", []) if isinstance(i, dict)}
    broad = indices.get(US_INTERNAL_BROAD_SYMBOL)
    tech = indices.get(US_INTERNAL_TECH_SYMBOL)
    if not broad or not tech:
        return {"available": False, "reason": "美国地区缺少 SPY/QQQ 双指数,暂不能内部轮动。"}
    _, broad_stats = us_index_risk_points(broad)
    _, tech_stats = us_index_risk_points(tech)

    drivers: list[str] = []
    broad_points = 0
    tech_points = 0

    def compare(value_broad: float | None, value_tech: float | None, label: str, fmt: str = "{:.0f}") -> None:
        nonlocal broad_points, tech_points
        if value_broad is None or value_tech is None:
            return
        if value_tech > value_broad:
            tech_points += 1
            drivers.append(f"科技{label}更高({fmt.format(value_tech)} vs {fmt.format(value_broad)})")
        elif value_broad > value_tech:
            broad_points += 1
            drivers.append(f"宽基{label}更高({fmt.format(value_broad)} vs {fmt.format(value_tech)})")

    compare(float(broad_stats["statusSeverity"]), float(tech_stats["statusSeverity"]), "泡沫状态")
    compare(broad_stats["lpplScore"], tech_stats["lpplScore"], "LPPL评分")
    compare(broad_stats["realizedVol"], tech_stats["realizedVol"], "已实现波动")

    riskier_row: dict[str, Any] | None = None
    if tech_points > broad_points:
        context_tilt, context_tilt_cn = "broad", "偏宽基(SPY)、减科技(QQQ)"
        riskier = "科技(QQQ)"
        riskier_row = tech
    elif broad_points > tech_points:
        context_tilt, context_tilt_cn = "tech", "偏科技(QQQ)、减宽基(SPY)"
        riskier = "宽基(SPY)"
        riskier_row = broad
    else:
        context_tilt, context_tilt_cn = "balanced", "宽基/科技均衡"
        riskier = ""
    actionable = bool(
        riskier_row is not None
        and regional_lppl_index_qualifies_as_actionable(riskier_row)
    )
    tilt, tilt_cn = (
        (context_tilt, context_tilt_cn)
        if actionable
        else ("balanced", "无生产级内部倾斜")
    )
    context_rationale = (
        f"美股内部: {riskier}风险读数更高 → {context_tilt_cn}"
        + (f"; 依据: {'、'.join(drivers)}" if drivers else "")
        if riskier
        else f"美股内部: 宽基与科技风险读数相当 → {context_tilt_cn}"
    )
    rationale = (
        context_rationale
        if actionable
        else context_rationale + "; 相关读数未触发生产级LPPL,仅作研究背景。"
    )
    return {
        "available": True,
        "tilt": tilt,
        "tiltCn": tilt_cn,
        "contextTilt": context_tilt,
        "contextTiltCn": context_tilt_cn,
        "actionable": actionable,
        "scoreUse": "production_signal" if actionable else "research_only",
        "broadPoints": broad_points,
        "techPoints": tech_points,
        "broad": broad_stats,
        "tech": tech_stats,
        "drivers": drivers,
        "rationale": rationale,
        "method": "美股内部因子轮动: SPY宽基 vs QQQ科技, 逐项(泡沫/LPPL/波动)比较风险读数, 倾向风险更低的一侧。描述性风控叠加, 非收益预测。",
    }


def merged_cluster_band(bands: list[Any]) -> list[float] | None:
    """Element-wise min of member exposure bands — correlated regions share the tightest
    (most conservative) single allocation band rather than each cutting independently."""
    valid = [band for band in bands if isinstance(band, list) and len(band) == 2]
    if not valid:
        return None
    return [min(band[0] for band in valid), min(band[1] for band in valid)]


def regional_allocation_qualifies_as_actionable(region: dict[str, Any]) -> bool:
    """Recheck serialized allocation evidence before cross-region propagation."""
    allocation = region.get("allocation") if isinstance(region.get("allocation"), dict) else {}
    band = allocation.get("exposureBandPct")
    band_valid = bool(
        isinstance(band, list)
        and len(band) == 2
        and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in band)
        and 0 <= float(band[0]) <= float(band[1]) <= 150
    )
    lppl_triggered = bool(
        allocation.get("productionLpplTriggered") is True
        and regional_lppl_region_has_current_trigger(region)
    )
    factor_triggered = bool(
        allocation.get("validatedFactorTriggered") is True
        and regional_factor_alert_qualifies_as_actionable(region)
    )
    return bool(
        allocation.get("actionable") is True
        and allocation.get("scoreUse") == "production_signal"
        and allocation.get("actionabilityStatus") == "current_lppl_or_validated_factor_trigger"
        and band_valid
        and (lppl_triggered or factor_triggered)
    )


def build_regional_rotation(regions: list[dict[str, Any]], diversification: dict[str, Any] | None = None) -> dict[str, Any]:
    scored = [
        region for region in regions
        if isinstance(region.get("allocation"), dict) and region["aggregate"].get("availableCount", 0) > 0
    ]
    if not scored:
        return {
            "available": False,
            "favorRegions": [],
            "reduceRegions": [],
            "contextFavorRegions": [],
            "contextReduceRegions": [],
            "reduceClusters": [],
            "summary": "暂无地区配置建议。",
        }
    name_by_key = {region["key"]: region["nameCn"] for region in scored}
    actionable_scored = [region for region in scored if regional_allocation_qualifies_as_actionable(region)]
    favor = [region["key"] for region in actionable_scored if region["allocation"]["stance"] == "overweight"]
    reduce_regions = [region["key"] for region in actionable_scored if region["allocation"]["stance"] == "underweight"]
    context_favor = [
        region["key"]
        for region in scored
        if not regional_allocation_qualifies_as_actionable(region)
        and region["allocation"]["stance"] == "overweight"
    ]
    context_reduce = [
        region["key"]
        for region in scored
        if not regional_allocation_qualifies_as_actionable(region)
        and region["allocation"]["stance"] == "underweight"
    ]
    ranked = sorted(scored, key=lambda region: region["allocation"]["cautionScore"])

    # Merge risk budget: co-moving reduce-regions count as one exposure, not independent cuts.
    reduce_clusters_keys = cluster_correlated_regions(reduce_regions, diversification)
    band_by_key = {
        region["key"]: region["allocation"].get("exposureBandPct")
        for region in scored
        if isinstance(region["allocation"].get("exposureBandPct"), list)
    }
    reduce_clusters = [
        {
            "regions": cluster,
            "names": [name_by_key.get(key, key) for key in cluster],
            "merged": len(cluster) > 1,
            # Correlated regions share ONE risk budget: the cluster's allowance is the tightest
            # member band (element-wise min), applied to the cluster as a single exposure — not
            # N independent cuts that would over-reduce a single underlying bet.
            "exposureBandPct": merged_cluster_band([band_by_key.get(key) for key in cluster]),
        }
        for cluster in reduce_clusters_keys
    ]
    independent_cuts = len(reduce_clusters)
    redundant = any(cluster["merged"] for cluster in reduce_clusters)

    favor_names = "、".join(region["nameCn"] for region in scored if region["key"] in favor)
    reduce_names = "、".join(region["nameCn"] for region in scored if region["key"] in reduce_regions)
    if favor_names and reduce_names:
        summary = f"地区轮动: 增持{favor_names}; 减持{reduce_names}(泡沫/承压且多有已验证领先因子佐证)。"
    elif reduce_names:
        summary = f"地区轮动: 建议减持{reduce_names}; 其余维持中性。"
    elif favor_names:
        summary = f"地区轮动: 可增持{favor_names}; 其余维持中性。"
    else:
        summary = "地区轮动: 当前无通过生产门槛的地区倾斜。"
    context_parts: list[str] = []
    if context_favor:
        context_parts.append("研究层偏多" + "、".join(name_by_key.get(key, key) for key in context_favor))
    if context_reduce:
        context_parts.append("研究层偏空" + "、".join(name_by_key.get(key, key) for key in context_reduce))
    if context_parts:
        summary += " " + "; ".join(context_parts) + ",不计入生产配置。"
    if redundant and len(reduce_regions) > independent_cuts:
        merged_notes = []
        for cluster in reduce_clusters:
            if not cluster["merged"]:
                continue
            band = cluster.get("exposureBandPct")
            band_text = f"共享仓位带 {band[0]:.0f}-{band[1]:.0f}%" if isinstance(band, list) and len(band) == 2 else ""
            merged_notes.append("+".join(cluster["names"]) + (f"({band_text})" if band_text else ""))
        summary += (
            f" 注意: {'、'.join(merged_notes)}高度相关, 实为同一风险敞口, "
            f"{len(reduce_regions)}个减持其实只是{independent_cuts}个独立风险预算——同簇地区共享一个减仓额度, 勿叠加减仓。"
        )
    return {
        "available": True,
        "actionable": bool(favor or reduce_regions),
        "scoreUse": "production_signal" if (favor or reduce_regions) else "research_only",
        "favorRegions": favor,
        "reduceRegions": reduce_regions,
        "contextFavorRegions": context_favor,
        "contextReduceRegions": context_reduce,
        "reduceClusters": reduce_clusters,
        "independentReduceCount": independent_cuts,
        "ranking": [region["key"] for region in ranked],
        "summary": summary,
        "method": "风险-轮动叠加层: 据泡沫状态、市场状态(趋势/回撤)、相对美国强弱合成谨慎度,并以各地区自身 OOS 验证的领先因子决定置信; 高相关减持地区合并为同一风险预算。属风险控制叠加,非收益预测。",
    }
