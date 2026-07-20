"""Global LPPL validation and backtest helpers.

This module owns the pure validation layer: forward drawdown observations,
threshold calibration, OOS evaluation, validation weights, and risk regimes.
LPPL fit/history orchestration remains outside so this layer never imports the
dashboard facade or creates a circular dependency.
"""
from __future__ import annotations

import math
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
from .scoring_lppl import GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
from .sources import MarketDailyBar


GLOBAL_LPPL_ALERT_THRESHOLD = 65
GLOBAL_LPPL_OOS_PURGE_SESSIONS = 15
GLOBAL_LPPL_OOS_MIN_EVALUATION_OBSERVATIONS = 10
GLOBAL_LPPL_OOS_MIN_INDEPENDENT_ALERTS = 5
GLOBAL_LPPL_OOS_MIN_INDEPENDENT_BASE_OBSERVATIONS = 8
GLOBAL_LPPL_VALIDATION_FAMILY_SIZE = 6
GLOBAL_LPPL_VALIDATION_FAMILY_ALPHA = 0.10
GLOBAL_LPPL_VALIDATION_PER_TEST_ALPHA = (
    GLOBAL_LPPL_VALIDATION_FAMILY_ALPHA / GLOBAL_LPPL_VALIDATION_FAMILY_SIZE
)


def _observation_bar_index(row: dict[str, Any]) -> int | None:
    value = row.get("_barIndex")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _observation_coordinate(row: dict[str, Any], fallback: int) -> int:
    bar_index = _observation_bar_index(row)
    return bar_index if bar_index is not None else fallback


def _chronological_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return observations in source-session order.

    Production history is already chronological, but this validation helper is
    also called directly by tests and maintenance scripts.  Sorting here keeps
    the 65/35 split and the non-overlap gate from depending on caller order.
    """

    def sort_key(item: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        fallback, row = item
        bar_index = _observation_bar_index(row)
        if bar_index is not None:
            return (0, bar_index, fallback)
        try:
            ordinal = date.fromisoformat(str(row.get("date") or "")).toordinal()
        except ValueError:
            ordinal = fallback
        return (1, ordinal, fallback)

    return [row for _fallback, row in sorted(enumerate(rows), key=sort_key)]


def _non_overlapping_observation_anchors(
    rows: list[dict[str, Any]],
    *,
    horizon: int,
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    last_coordinate: int | None = None
    for fallback, row in enumerate(rows):
        coordinate = _observation_coordinate(row, fallback)
        if last_coordinate is None or coordinate > last_coordinate + horizon:
            anchors.append(row)
            last_coordinate = coordinate
    return anchors


def _independent_lppl_alert_anchors(
    threshold: int,
    rows: list[dict[str, Any]],
    *,
    horizon: int,
) -> list[dict[str, Any]]:
    """Collapse daily alert streaks and overlapping outcome windows.

    LPPL scores are replayed daily while the label spans 15 sessions. Counting
    every day in a persistent alert as a fresh Bernoulli trial dramatically
    inflates the effective sample.  We retain only the first row in an alert
    episode and require the next retained anchor to start after the prior label
    window closes.
    """
    anchors: list[dict[str, Any]] = []
    last_anchor_coordinate: int | None = None
    previous_coordinate: int | None = None
    previous_was_alert = False
    for fallback, row in enumerate(rows):
        coordinate = _observation_coordinate(row, fallback)
        score = optional_float(row.get("score"))
        is_alert = score is not None and score >= threshold
        contiguous = (
            previous_was_alert
            and previous_coordinate is not None
            and coordinate <= previous_coordinate + 1
        )
        episode_start = is_alert and not contiguous
        if episode_start and (
            last_anchor_coordinate is None
            or coordinate > last_anchor_coordinate + horizon
        ):
            anchors.append(row)
            last_anchor_coordinate = coordinate
        previous_was_alert = is_alert
        previous_coordinate = coordinate
    return anchors


def _exact_binomial_upper_tail(
    successes: int,
    trials: int,
    *,
    null_probability: float,
) -> float | None:
    """One-sided exact Binomial(n, p0) upper-tail probability."""
    if (
        trials <= 0
        or successes < 0
        or successes > trials
        or not math.isfinite(null_probability)
        or not 0.0 <= null_probability <= 1.0
    ):
        return None
    if null_probability == 0.0:
        return 1.0 if successes == 0 else 0.0
    if null_probability == 1.0:
        return 1.0
    tail = 0.0
    for count in range(successes, trials + 1):
        log_probability = (
            math.lgamma(trials + 1)
            - math.lgamma(count + 1)
            - math.lgamma(trials - count + 1)
            + count * math.log(null_probability)
            + (trials - count) * math.log1p(-null_probability)
        )
        tail += math.exp(log_probability)
    return max(0.0, min(1.0, tail))


def _wilson_lower_bound_pct(successes: int, trials: int, *, z: float = 1.6448536269514722) -> float | None:
    """One-sided 90% Wilson lower bound for alert precision."""
    if trials <= 0 or successes < 0 or successes > trials:
        return None
    proportion = successes / trials
    denominator = 1.0 + (z * z / trials)
    center = proportion + (z * z / (2.0 * trials))
    margin = z * math.sqrt((proportion * (1.0 - proportion) / trials) + (z * z / (4.0 * trials * trials)))
    return round(100.0 * max(0.0, (center - margin) / denominator), 1)


def global_lppl_independent_threshold_audit(
    threshold: int,
    observations: list[dict[str, Any]],
    drawdown_threshold_pct: float,
    *,
    horizon: int,
) -> dict[str, Any]:
    drawdown_key = f"maxDrawdown{horizon}d"
    event_key = f"drawdownEvent{horizon}d"
    eligible = _chronological_observations(
        [row for row in observations if optional_float(row.get(drawdown_key)) is not None]
    )
    base_anchors = _non_overlapping_observation_anchors(eligible, horizon=horizon)
    alert_anchors = _independent_lppl_alert_anchors(
        threshold,
        eligible,
        horizon=horizon,
    )
    base_events = sum(1 for row in base_anchors if row.get(event_key))
    alert_hits = sum(1 for row in alert_anchors if row.get(event_key))
    base_rate_pct = 100.0 * base_events / len(base_anchors) if base_anchors else None
    precision_pct = 100.0 * alert_hits / len(alert_anchors) if alert_anchors else None
    # Jeffreys smoothing avoids turning a short zero-event baseline into a
    # literally impossible null.  Conditional on that disclosed p0, the tail
    # below is the exact one-sided binomial probability, not a normal or Fisher
    # z approximation.
    null_alpha = base_events + 0.5
    null_beta = len(base_anchors) - base_events + 0.5
    smoothed_null_rate = null_alpha / (null_alpha + null_beta) if base_anchors else None
    enrichment_p_value = (
        _exact_binomial_upper_tail(
            alert_hits,
            len(alert_anchors),
            null_probability=smoothed_null_rate,
        )
        if base_anchors and alert_anchors
        else None
    )
    precision_lower = _wilson_lower_bound_pct(alert_hits, len(alert_anchors))
    adjusted_p_value = (
        min(1.0, enrichment_p_value * GLOBAL_LPPL_VALIDATION_FAMILY_SIZE)
        if enrichment_p_value is not None
        else None
    )
    multiple_testing_pass = bool(
        adjusted_p_value is not None
        and adjusted_p_value <= GLOBAL_LPPL_VALIDATION_FAMILY_ALPHA
    )
    return {
        "independenceRule": (
            "first alert per contiguous episode; retained anchors are separated "
            f"by more than {horizon} source-market sessions"
        ),
        "independentSampleSize": len(base_anchors),
        "independentDrawdownEvents": base_events,
        "independentBaseRate": round(base_rate_pct, 1) if base_rate_pct is not None else None,
        "independentAlertCount": len(alert_anchors),
        "independentAlertHits": alert_hits,
        "independentPrecision": round(precision_pct, 1) if precision_pct is not None else None,
        "precisionLowerBound90Pct": precision_lower,
        "enrichmentNullRatePct": round(100.0 * smoothed_null_rate, 1) if smoothed_null_rate is not None else None,
        "enrichmentPValueOneSided": round(enrichment_p_value, 8) if enrichment_p_value is not None else None,
        "enrichmentTest": "one-sided exact binomial upper tail against Jeffreys-smoothed independent base rate",
        "multipleTestingFamily": "global_lppl_six_index_validation",
        "multipleTestingMethod": "fixed-family Bonferroni FWER control",
        "multipleTestingFamilySize": GLOBAL_LPPL_VALIDATION_FAMILY_SIZE,
        "multipleTestingFamilyAlpha": GLOBAL_LPPL_VALIDATION_FAMILY_ALPHA,
        "multipleTestingPerTestAlpha": round(GLOBAL_LPPL_VALIDATION_PER_TEST_ALPHA, 8),
        "multipleTestingAdjustedPValue": round(adjusted_p_value, 8) if adjusted_p_value is not None else None,
        "multipleTestingPass": multiple_testing_pass,
        "drawdownEvent": f"maxDrawdown{horizon}d <= {drawdown_threshold_pct:.1f}%",
    }


def global_lppl_threshold_test(
    threshold: int,
    observations: list[dict[str, Any]],
    drawdown_threshold_pct: float,
    *,
    horizon: int,
) -> dict[str, Any]:
    result = equity_backtest_threshold_test(
        threshold,
        observations,
        drawdown_threshold_pct,
        horizon=horizon,
    )
    result.update(
        global_lppl_independent_threshold_audit(
            threshold,
            observations,
            drawdown_threshold_pct,
            horizon=horizon,
        )
    )
    return result


def global_lppl_replay_model_audit(
    observations: list[dict[str, Any]],
    *,
    required: bool,
    live_model_spec_id: str | None = None,
    live_validation_comparable: bool | None = None,
) -> dict[str, Any]:
    explicit_ids = sorted({
        str(row.get("modelSpecId") or "")
        for row in observations
        if str(row.get("modelSpecId") or "")
    })
    unknown_count = sum(1 for row in observations if not str(row.get("modelSpecId") or ""))
    mismatch_count = sum(
        1
        for row in observations
        if str(row.get("modelSpecId") or "")
        and str(row.get("modelSpecId")) != GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
    )
    comparable_count = sum(
        1
        for row in observations
        if str(row.get("modelSpecId") or "") == GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
        and row.get("validationComparableToProduction") is True
    )
    replay_comparable = bool(
        observations
        and mismatch_count == 0
        and unknown_count == 0
        and comparable_count == len(observations)
    )
    live_model_spec_id = str(live_model_spec_id or "")
    live_metadata_available = bool(live_model_spec_id)
    live_comparable = bool(
        live_model_spec_id == GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
        and live_validation_comparable is True
    )
    comparable = bool(replay_comparable and (live_comparable if required else True))
    enforcement_pass = comparable if required else mismatch_count == 0
    if comparable:
        status = "comparable"
    elif required and not live_metadata_available:
        status = "live_model_unknown"
    elif required and not live_comparable:
        status = "live_model_mismatch"
    elif not required and mismatch_count == 0:
        status = "legacy_unknown_not_enforced"
    elif mismatch_count > 0 or unknown_count > 0:
        status = "model_spec_mismatch"
    else:
        status = "not_comparable"
    return {
        "required": required,
        "productionModelSpecId": GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
        "liveModelSpecId": live_model_spec_id or None,
        "liveModelMetadataAvailable": live_metadata_available,
        "liveValidationComparable": live_validation_comparable is True,
        "liveComparable": live_comparable,
        "observedModelSpecIds": explicit_ids,
        "observationCount": len(observations),
        "comparableObservationCount": comparable_count,
        "unknownModelSpecCount": unknown_count,
        "mismatchedModelSpecCount": mismatch_count,
        "replayComparable": replay_comparable,
        "comparable": comparable,
        "enforcementPass": enforcement_pass,
        "status": status,
        "reason": (
            "live and replay paths use the exact production LPPL model specification"
            if comparable
            else "live LPPL model metadata is missing; production credit disabled"
            if required and not live_metadata_available
            else "live LPPL model does not match the production specification; production credit disabled"
            if required and not live_comparable
            else "legacy caller did not require a model-spec gate"
            if not required and mismatch_count == 0
            else "replay and live LPPL searches are not distribution-comparable; production credit disabled"
        ),
    }


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
    *,
    require_model_comparability: bool = False,
    live_model_spec_id: str | None = None,
    live_validation_comparable: bool | None = None,
) -> dict[str, Any]:
    """Select on purged first-65% data and evaluate on untouched last 35%.

    Only rows with a complete 15-session outcome are admitted before the split.
    The selected threshold is a calibration artifact; the production weight is
    derived exclusively from non-overlapping alert anchors in the untouched OOS
    test, with uncertainty and the six-index family search explicitly gated.
    Strict dashboard callers additionally require the replay model fingerprint
    to match the live production search.
    """
    eligible_observations = _chronological_observations([
        row for row in observations if optional_float(row.get("maxDrawdown15d")) is not None
    ])
    model_audit = global_lppl_replay_model_audit(
        eligible_observations,
        required=require_model_comparability,
        live_model_spec_id=live_model_spec_id,
        live_validation_comparable=live_validation_comparable,
    )
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
        "replayModelAudit": model_audit,
    }
    if (
        len(calibration_obs) < 20
        or len(evaluation_obs) < GLOBAL_LPPL_OOS_MIN_EVALUATION_OBSERVATIONS
    ):
        return {
            "oosAvailable": False,
            **purge_metadata,
            "productionEvidenceAvailable": False,
            "productionActionable": False,
            "productionThreshold": GLOBAL_LPPL_ALERT_THRESHOLD,
            "productionThresholdSource": "fixed_prior_no_oos",
            "productionEffectiveWeightMultiplier": 0.0,
            "productionWeightSource": "disabled_no_oos_evidence",
            "productionValidationRole": "unvalidated",
            "productionValidationRoleCn": "OOS证据不足",
        }
    oos_grid = [
        global_lppl_threshold_test(candidate_threshold, calibration_obs, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    oos_recommended = global_lppl_recommended_threshold(oos_grid, len(calibration_obs))
    oos_threshold = int(oos_recommended.get("threshold") or GLOBAL_LPPL_ALERT_THRESHOLD)
    oos_test = global_lppl_threshold_test(oos_threshold, evaluation_obs, drawdown_threshold_pct, horizon=15)
    oos_precision = optional_float(oos_test.get("precision"))
    oos_recall = optional_float(oos_test.get("recall"))
    multiplier, role, role_cn = global_lppl_validation_weight(oos_test)
    production_comparable = model_audit.get("enforcementPass") is True
    production_evidence_available = bool(production_comparable)
    if not production_evidence_available:
        multiplier, role, role_cn = 0.0, "unvalidated_model_mismatch", "回放模型与生产模型不一致"
    production_actionable = bool(
        production_evidence_available
        and role == "validated"
        and multiplier >= 0.999
    )
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
        "productionEvidenceAvailable": production_evidence_available,
        "productionActionable": production_actionable,
        "productionThreshold": oos_threshold if production_evidence_available else GLOBAL_LPPL_ALERT_THRESHOLD,
        "productionThresholdSource": (
            "purged_calibration_first_65pct"
            if production_evidence_available
            else "fixed_prior_replay_model_mismatch"
        ),
        "productionEffectiveWeightMultiplier": multiplier,
        "productionWeightSource": (
            "untouched_oos_last_35pct"
            if production_evidence_available
            else "disabled_replay_model_mismatch"
        ),
        "productionWeightMethod": (
            "non_overlapping_alerts_wilson90_exact_binomial_bonferroni6"
            if production_evidence_available
            else "disabled_replay_model_mismatch"
        ),
        "productionValidationRole": role,
        "productionValidationRoleCn": role_cn,
    }


def build_global_lppl_validation_observations(
    points: list[dict[str, Any]],
    bars: list[MarketDailyBar],
    drawdown_threshold_pct: float,
) -> list[dict[str, Any]]:
    points_by_date: dict[date, dict[str, Any]] = {}
    for point in points:
        if not isinstance(point, dict):
            continue
        try:
            point_date = date.fromisoformat(str(point.get("date") or ""))
        except ValueError:
            continue
        # A replay date is a unique information set.  Last-write-wins keeps a
        # duplicate input from inflating the OOS sample while preserving the
        # caller's most recent correction for that date.
        points_by_date[point_date] = point
    if not points_by_date:
        return []
    # The latest replay point is the information boundary of the validation
    # artifact.  Outcomes after that boundary are unavailable in an as-of build
    # and must never be pulled from a longer caller-owned price series.
    information_cutoff = max(points_by_date)
    audit_bars = [bar for bar in bars if bar.date <= information_cutoff]
    index_by_date = {bar.date: index for index, bar in enumerate(audit_bars)}
    observations: list[dict[str, Any]] = []
    for point_date in sorted(points_by_date):
        point = points_by_date[point_date]
        score = optional_float(point.get("score"))
        index = index_by_date.get(point_date)
        if score is None or index is None or index + 1 >= len(audit_bars):
            continue
        row = {
            "date": point_date.isoformat(),
            "score": round(bounded_score(score), 1),
            # Internal source-session coordinate used to purge overlapping
            # 15-session labels at the 65/35 OOS boundary.
            "_barIndex": index,
            "_informationCutoff": information_cutoff.isoformat(),
        }
        for key in (
            "modelSpecId",
            "validationComparableToProduction",
            "productionEligible",
        ):
            if key in point:
                row[key] = point[key]
        for horizon in (5, 10, 15, 20):
            row[f"forward{horizon}d"] = equity_forward_return_pct(audit_bars, index, horizon)
            drawdown = equity_forward_max_drawdown_pct(audit_bars, index, horizon)
            row[f"maxDrawdown{horizon}d"] = drawdown
            row[f"drawdownEvent{horizon}d"] = drawdown is not None and drawdown <= drawdown_threshold_pct
            row[f"drawdownLeadDays{horizon}d"] = equity_forward_drawdown_lead_days(
                audit_bars,
                index,
                horizon,
                drawdown_threshold_pct,
            )
        observations.append(row)
    return observations


def global_lppl_validation_weight(test_15d: dict[str, Any]) -> tuple[float, str, str]:
    has_independent_audit = "independentAlertCount" in test_15d
    alert_count = (
        optional_float(test_15d.get("independentAlertCount"))
        if has_independent_audit
        else optional_float(test_15d.get("alertDays"))
    ) or 0.0
    precision = optional_float(
        test_15d.get("independentPrecision")
        if has_independent_audit
        else test_15d.get("precision")
    )
    base_rate = optional_float(
        test_15d.get("independentBaseRate")
        if has_independent_audit
        else test_15d.get("baseRate")
    ) or 0.0
    minimum_alerts = GLOBAL_LPPL_OOS_MIN_INDEPENDENT_ALERTS if has_independent_audit else 3
    independent_sample = optional_float(test_15d.get("independentSampleSize"))
    if (
        alert_count < minimum_alerts
        or precision is None
        or (
            has_independent_audit
            and (independent_sample or 0.0) < GLOBAL_LPPL_OOS_MIN_INDEPENDENT_BASE_OBSERVATIONS
        )
    ):
        # A thin OOS alert sample cannot estimate hit quality. Treating
        # that as x0.75 would give more production credit than a known weak
        # result (x0.60), an inverted evidence ordering.
        return 0.0, "insufficient", "OOS告警样本不足"
    if has_independent_audit:
        precision_lower = optional_float(test_15d.get("precisionLowerBound90Pct"))
        multiple_testing_pass = test_15d.get("multipleTestingPass") is True
        if precision_lower is None or precision_lower <= base_rate or not multiple_testing_pass:
            return 0.0, "not_significant", "独立告警未通过置信下界或多市场校正"
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
    independent_alerts = test_15d.get("independentAlertCount")
    independent_precision = test_15d.get("independentPrecision")
    independent_text = (
        f", independent alerts {independent_alerts}, independent precision "
        f"{format_optional_percent_value(independent_precision)}"
        if independent_alerts is not None
        else ""
    )
    return (
        f"{symbol} own-market 15D audit: threshold {test_15d.get('threshold')}, "
        f"precision {format_optional_percent_value(test_15d.get('precision'))}, "
        f"recall {format_optional_percent_value(test_15d.get('recall'))}, "
        f"false {test_15d.get('falsePositives', 0)}{independent_text}, "
        f"weight x{multiplier:.2f} ({role_cn})."
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
        global_lppl_threshold_test(candidate_threshold, observations, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    recommended_threshold_test = global_lppl_recommended_threshold(calibration_grid, len(observations))
    threshold = int(recommended_threshold_test.get("threshold") or threshold)
    horizon_tests = [
        global_lppl_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=horizon)
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
        "selectionAudit": {
            "thresholdCandidateCount": len(calibration_grid),
            "thresholdSelectionSet": "same_full_sample_as_reported_metrics",
            "productionUse": False,
            "reason": "threshold and metrics share the full sample; use only as a descriptive sensitivity audit",
        },
        "alertClusterTest": alert_cluster_test,
        "summary": summary,
    }


def global_lppl_recommended_threshold(
    calibration_grid: list[dict[str, Any]],
    sample_size: int,
) -> dict[str, Any]:
    def metric(row: dict[str, Any], independent_key: str, fallback_key: str) -> float:
        value = optional_float(row.get(independent_key))
        if value is None:
            value = optional_float(row.get(fallback_key))
        return value or 0.0

    candidates = [
        row
        for row in calibration_grid
        if metric(row, "independentAlertCount", "alertDays")
        >= max(3.0, min(10.0, sample_size / 25.0))
    ]
    if not candidates:
        candidates = [
            row
            for row in calibration_grid
            if metric(row, "independentAlertCount", "alertDays") > 0
        ]
    if not candidates:
        return {}
    base_rate = max(metric(row, "independentBaseRate", "baseRate") for row in candidates)
    min_precision = max(45.0, base_rate + 8.0)
    qualifying = [
        row
        for row in candidates
        if metric(row, "independentPrecision", "precision") >= min_precision
    ]
    if not qualifying:
        qualifying = candidates

    def threshold_score(row: dict[str, Any]) -> tuple[float, float, float, float]:
        precision = metric(row, "independentPrecision", "precision")
        recall = optional_float(row.get("recall")) or 0.0
        alert_days = metric(row, "independentAlertCount", "alertDays")
        threshold = optional_float(row.get("threshold")) or 0.0
        return (precision, recall, alert_days, threshold)

    selected = dict(max(qualifying, key=threshold_score))
    selected.update(
        {
            "key": "globalLpplRecommendedThreshold",
            "label": "LPPL推荐告警阈值",
            "labelEn": "Global LPPL Recommended Threshold",
            "useCase": "仅在校准段按本市场非重叠告警选择; 优先提高独立告警精确率,再考虑覆盖率。",
            "selectionMetric": "independent_alert_precision",
        }
    )
    return selected
