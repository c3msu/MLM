"""Global LPPL validation and backtest helpers.

This module owns the pure validation layer: forward drawdown observations,
threshold calibration, OOS evaluation, validation weights, and risk regimes.
LPPL fit/history orchestration remains outside so this layer never imports the
dashboard facade or creates a circular dependency.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .dashboard_core import (
    SIGNAL_VALIDATION_OOS_SPLIT,
    bounded_score,
    format_optional_percent_value,
    optional_float,
)
from .scoring_equity import (
    equity_backtest_alert_cluster_test,
    equity_backtest_threshold_test,
    equity_forward_drawdown_lead_days,
    equity_forward_max_drawdown_pct,
    equity_forward_return_pct,
    normalize_market_bars,
)
from .sources import MarketDailyBar


GLOBAL_LPPL_ALERT_THRESHOLD = 65
GLOBAL_LPPL_OOS_PURGE_SESSIONS = 15


def _observation_bar_index(row: dict[str, Any]) -> int | None:
    value = row.get("_barIndex")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _purged_lppl_calibration_observations(
    calibration_candidates: list[dict[str, Any]],
    evaluation_obs: list[dict[str, Any]],
    *,
    purge_sessions: int = GLOBAL_LPPL_OOS_PURGE_SESSIONS,
) -> tuple[list[dict[str, Any]], str]:
    """Remove calibration labels whose forward window reaches the OOS start.

    Validation observations produced by this module carry their source market
    bar index, which lets the purge operate in trading sessions even when LPPL
    replay dates are sparse. The observation-order fallback keeps the public
    helper safe for older callers that construct rows directly.
    """
    if not calibration_candidates or not evaluation_obs or purge_sessions <= 0:
        return list(calibration_candidates), "not_required"
    evaluation_start_index = _observation_bar_index(evaluation_obs[0])
    candidate_indices = [_observation_bar_index(row) for row in calibration_candidates]
    if evaluation_start_index is not None and all(index is not None for index in candidate_indices):
        return (
            [
                row
                for row, bar_index in zip(calibration_candidates, candidate_indices)
                if bar_index is not None and bar_index + purge_sessions < evaluation_start_index
            ],
            "trading_session_bar_index",
        )
    retained_count = max(0, len(calibration_candidates) - purge_sessions)
    return list(calibration_candidates[:retained_count]), "observation_order_fallback"


def global_lppl_oos_validation_fields(
    observations: list[dict[str, Any]],
    drawdown_threshold_pct: float,
) -> dict[str, Any]:
    """Select on purged first-65% data and evaluate on untouched last 35%.

    Only rows with a complete 15-session outcome are admitted before the split.
    The selected threshold is a calibration artifact; the production weight is
    derived exclusively from the untouched OOS test at that threshold.
    """
    eligible_observations = [
        row
        for row in observations
        if optional_float(row.get("maxDrawdown15d")) is not None
    ]
    split_index = max(
        1,
        min(
            len(eligible_observations) - 1,
            int(len(eligible_observations) * SIGNAL_VALIDATION_OOS_SPLIT),
        ),
    )
    calibration_candidates = eligible_observations[:split_index]
    evaluation_obs = eligible_observations[split_index:]
    calibration_obs, purge_basis = _purged_lppl_calibration_observations(
        calibration_candidates,
        evaluation_obs,
    )
    purge_metadata = {
        "oosSplitPct": round(SIGNAL_VALIDATION_OOS_SPLIT * 100),
        "oosSplitDate": evaluation_obs[0].get("date") if evaluation_obs else None,
        "oosPurgeSessions": GLOBAL_LPPL_OOS_PURGE_SESSIONS,
        "oosPurgeBasis": purge_basis,
        "oosPurgeRule": (
            "drop calibration signals whose forward 15-trading-session label "
            "reaches or crosses the OOS start"
        ),
        "oosThresholdSelectionSet": "purged_calibration_first_65pct",
        "oosWeightEvaluationSet": "untouched_oos_last_35pct",
        "oosEligibleObservationCount": len(eligible_observations),
        "oosExcludedIncompleteTailCount": len(observations) - len(eligible_observations),
        "oosCalibrationCandidateSize": len(calibration_candidates),
        "oosCalibrationSampleSize": len(calibration_obs),
        "oosPurgedCalibrationRows": len(calibration_candidates) - len(calibration_obs),
        "oosCalibrationThrough": calibration_obs[-1].get("date") if calibration_obs else None,
    }
    if len(calibration_obs) < 20 or len(evaluation_obs) < 10:
        return {
            "oosAvailable": False,
            **purge_metadata,
            "productionEvidenceAvailable": False,
            "productionThreshold": GLOBAL_LPPL_ALERT_THRESHOLD,
            "productionThresholdSource": "fixed_prior_no_oos",
            "productionEffectiveWeightMultiplier": 0.0,
            "productionWeightSource": "disabled_no_oos_evidence",
            "productionValidationRole": "unvalidated",
            "productionValidationRoleCn": "OOS证据不足",
        }
    oos_grid = [
        equity_backtest_threshold_test(candidate_threshold, calibration_obs, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    oos_recommended = global_lppl_recommended_threshold(oos_grid, len(calibration_obs))
    oos_threshold = int(oos_recommended.get("threshold") or GLOBAL_LPPL_ALERT_THRESHOLD)
    oos_test = equity_backtest_threshold_test(oos_threshold, evaluation_obs, drawdown_threshold_pct, horizon=15)
    oos_precision = optional_float(oos_test.get("precision"))
    oos_recall = optional_float(oos_test.get("recall"))
    multiplier, role, role_cn = global_lppl_validation_weight(oos_test)
    return {
        "oosAvailable": True,
        **purge_metadata,
        "oosCalibrationGrid": oos_grid,
        "oosRecommendedThreshold": oos_recommended,
        "oosThreshold": oos_threshold,
        "oosTest15d": oos_test,
        "oosSampleSize": int(oos_test.get("sampleSize") or 0),
        "oosAlertDays": int(oos_test.get("alertDays") or 0),
        "precision15dOos": round(oos_precision, 1) if oos_precision is not None else None,
        "recall15dOos": round(oos_recall, 1) if oos_recall is not None else None,
        "baseRate15dOos": oos_test.get("baseRate"),
        "oosEffectiveWeightMultiplier": multiplier,
        "oosValidationRole": role,
        "oosValidationRoleCn": role_cn,
        "productionEvidenceAvailable": True,
        "productionThreshold": oos_threshold,
        "productionThresholdSource": "purged_calibration_first_65pct",
        "productionEffectiveWeightMultiplier": multiplier,
        "productionWeightSource": "untouched_oos_last_35pct",
        "productionValidationRole": role,
        "productionValidationRoleCn": role_cn,
    }


def build_global_lppl_validation_observations(
    points: list[dict[str, Any]],
    bars: list[MarketDailyBar],
    drawdown_threshold_pct: float,
) -> list[dict[str, Any]]:
    index_by_date = {bar.date: index for index, bar in enumerate(bars)}
    observations: list[dict[str, Any]] = []
    for point in points:
        try:
            point_date = date.fromisoformat(str(point.get("date") or ""))
        except ValueError:
            continue
        score = optional_float(point.get("score"))
        index = index_by_date.get(point_date)
        if score is None or index is None or index + 1 >= len(bars):
            continue
        row = {
            "date": point_date.isoformat(),
            "score": round(bounded_score(score), 1),
            # Internal source-session coordinate used to purge overlapping
            # 15-session labels at the 65/35 OOS boundary.
            "_barIndex": index,
        }
        for horizon in (5, 10, 15, 20):
            row[f"forward{horizon}d"] = equity_forward_return_pct(bars, index, horizon)
            drawdown = equity_forward_max_drawdown_pct(bars, index, horizon)
            row[f"maxDrawdown{horizon}d"] = drawdown
            row[f"drawdownEvent{horizon}d"] = drawdown is not None and drawdown <= drawdown_threshold_pct
            row[f"drawdownLeadDays{horizon}d"] = equity_forward_drawdown_lead_days(
                bars,
                index,
                horizon,
                drawdown_threshold_pct,
            )
        observations.append(row)
    return observations


def global_lppl_validation_weight(test_15d: dict[str, Any]) -> tuple[float, str, str]:
    alert_days = optional_float(test_15d.get("alertDays")) or 0.0
    precision = optional_float(test_15d.get("precision"))
    base_rate = optional_float(test_15d.get("baseRate")) or 0.0
    if alert_days < 3 or precision is None:
        # Fewer than three OOS alerts cannot estimate hit quality. Treating
        # that as x0.75 would give more production credit than a known weak
        # result (x0.60), an inverted evidence ordering.
        return 0.0, "insufficient", "OOS告警样本不足"
    if precision >= max(60.0, base_rate + 15.0):
        return 1.0, "validated", "验证支持"
    if precision >= base_rate + 5.0:
        return 0.85, "mixed", "部分支持"
    return 0.60, "weak", "历史偏弱"


def global_lppl_validation_summary(
    symbol: str,
    test_15d: dict[str, Any],
    multiplier: float,
    role_cn: str,
) -> str:
    return (
        f"{symbol} own-market 15D audit: threshold {test_15d.get('threshold')}, "
        f"precision {format_optional_percent_value(test_15d.get('precision'))}, "
        f"recall {format_optional_percent_value(test_15d.get('recall'))}, "
        f"false {test_15d.get('falsePositives', 0)}, weight x{multiplier:.2f} ({role_cn})."
    )


def global_lppl_status(score: float, confidence: float) -> tuple[str, str]:
    if score >= GLOBAL_LPPL_ALERT_THRESHOLD and confidence >= 0.35:
        return "risk", "泡沫风险"
    if score >= 45:
        return "watch", "观察"
    return "quiet", "低风险"


def global_lppl_regime(score: float) -> tuple[str, str]:
    if score >= 70:
        return "High Risk", "高风险"
    if score >= GLOBAL_LPPL_ALERT_THRESHOLD:
        return "Risk", "泡沫风险"
    if score >= 45:
        return "Watch", "观察"
    return "Quiet", "低风险"


def build_global_lppl_backtest(
    history_points: list[dict[str, Any]],
    market_bars: list[MarketDailyBar],
    *,
    symbol: str = "SPY",
    threshold: int = GLOBAL_LPPL_ALERT_THRESHOLD,
    drawdown_threshold_pct: float = -2.0,
) -> dict[str, Any]:
    symbol = symbol.upper()
    clean_bars = normalize_market_bars({symbol: market_bars}).get(symbol, [])
    if len(clean_bars) < 30 or not history_points:
        return {
            "available": False,
            "productionUse": False,
            "validationScope": "descriptive_full_sample",
            "sampleSize": 0,
            "threshold": threshold,
            "horizonTests": [],
            "summary": f"{symbol}或LPPL历史样本不足。",
        }
    observations = build_global_lppl_validation_observations(
        history_points,
        clean_bars,
        drawdown_threshold_pct,
    )
    if not observations:
        return {
            "available": False,
            "productionUse": False,
            "validationScope": "descriptive_full_sample",
            "sampleSize": 0,
            "threshold": threshold,
            "horizonTests": [],
            "summary": f"LPPL历史点没有足够后续{symbol}交易日。",
        }
    calibration_grid = [
        equity_backtest_threshold_test(candidate_threshold, observations, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    recommended_threshold_test = global_lppl_recommended_threshold(calibration_grid, len(observations))
    threshold = int(recommended_threshold_test.get("threshold") or threshold)
    horizon_tests = [
        equity_backtest_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=horizon)
        for horizon in (5, 10, 15, 20)
    ]
    preferred = next((row for row in horizon_tests if row["horizon"] == 15), horizon_tests[-1])
    alert_cluster_test = equity_backtest_alert_cluster_test(
        threshold,
        observations,
        drawdown_threshold_pct,
        horizon=15,
    )
    summary = (
        f"{symbol} LPPL score≥{threshold}历史告警{preferred.get('alertDays', 0)}次; "
        f"15D精确率{format_optional_percent_value(preferred.get('precision'))}, "
        f"误报{preferred.get('falsePositives', 0)}次; "
        f"最大误报簇{alert_cluster_test.get('maxFalseClusterDays', 0)}个点。"
    )
    return {
        "available": True,
        "productionUse": False,
        "validationScope": "descriptive_full_sample",
        "sampleSize": len(observations),
        "threshold": threshold,
        "drawdownEvent": f"next 5/10/15/20 trading days max drawdown <= {drawdown_threshold_pct:.1f}%",
        "horizonTests": horizon_tests,
        "calibrationGrid": calibration_grid,
        "recommendedThreshold": recommended_threshold_test,
        "alertClusterTest": alert_cluster_test,
        "summary": summary,
    }


def global_lppl_recommended_threshold(
    calibration_grid: list[dict[str, Any]],
    sample_size: int,
) -> dict[str, Any]:
    candidates = [
        row
        for row in calibration_grid
        if (optional_float(row.get("alertDays")) or 0.0) >= max(3.0, min(10.0, sample_size / 25.0))
    ]
    if not candidates:
        candidates = [
            row
            for row in calibration_grid
            if (optional_float(row.get("alertDays")) or 0.0) > 0
        ]
    if not candidates:
        return {}
    base_rate = max(optional_float(row.get("baseRate")) or 0.0 for row in candidates)
    min_precision = max(45.0, base_rate + 8.0)
    qualifying = [row for row in candidates if (optional_float(row.get("precision")) or 0.0) >= min_precision]
    if not qualifying:
        qualifying = candidates

    def threshold_score(row: dict[str, Any]) -> tuple[float, float, float, float]:
        precision = optional_float(row.get("precision")) or 0.0
        recall = optional_float(row.get("recall")) or 0.0
        alert_days = optional_float(row.get("alertDays")) or 0.0
        threshold = optional_float(row.get("threshold")) or 0.0
        return (precision, recall, alert_days, threshold)

    selected = dict(max(qualifying, key=threshold_score))
    selected.update(
        {
            "key": "globalLpplRecommendedThreshold",
            "label": "LPPL推荐告警阈值",
            "labelEn": "Global LPPL Recommended Threshold",
            "useCase": "用历史SPY前瞻回撤验证后选择; 优先提高精确率,再考虑覆盖率。",
        }
    )
    return selected
