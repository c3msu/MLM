"""Versioned dashboard payload contract.

The dashboard intentionally remains a broad JSON document, but producers and
consumers still need a small, stable envelope.  This module keeps that envelope
dependency-free so refresh jobs can reject malformed snapshots before the
atomic publish step.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import math
from typing import Any


CURRENT_SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({CURRENT_SCHEMA_VERSION})
# Decision-surface model versions live in this dependency-free contract layer
# so both producers and health checks compare against one authoritative value.
CURRENT_SPY_WARNING_RULES_VERSION = "2026-07-20-v3"
CURRENT_EQUITY_RISK_SCORE_SCALE_ID = "equity-risk-ohlcv-core-v2"
CURRENT_EQUITY_RISK_PRODUCTION_THRESHOLD = 75
CURRENT_EQUITY_RISK_RAW_WEIGHTS: dict[str, float] = {
    "volTargetPressure": 0.22,
    "qqqTltRotation": 0.14,
    "marketFlow": 0.22,
    "sectorRotation": 0.06,
    "hotStockReversal": 0.18,
    "turnover": 0.14,
}
_CURRENT_EQUITY_RISK_WEIGHT_TOTAL = sum(CURRENT_EQUITY_RISK_RAW_WEIGHTS.values())
CURRENT_EQUITY_RISK_NORMALIZED_WEIGHTS: dict[str, float] = {
    key: round(weight / _CURRENT_EQUITY_RISK_WEIGHT_TOTAL, 8)
    for key, weight in sorted(CURRENT_EQUITY_RISK_RAW_WEIGHTS.items())
}
CURRENT_EQUITY_RISK_SCORED_COMPONENTS = frozenset(
    CURRENT_EQUITY_RISK_RAW_WEIGHTS
)
_REGIONAL_RISK_FACTOR_IDS = frozenset({"lpplScore", "realizedVol"})
_REGIONAL_ACTIONABLE_MIN_OBSERVATIONS = 60
_REGIONAL_ACTIONABLE_MIN_OOS_OBSERVATIONS = 20
_REGIONAL_ACTIONABLE_MIN_OOS_ALERTS = 3

_OPTIONAL_TOP_LEVEL_TYPES: dict[str, type | tuple[type, ...]] = {
    "curve": dict,
    "groups": list,
    "ideas": list,
    "macroLiquidity": dict,
    "macroLiquidityEquity": dict,
    "spyEarlyWarning": dict,
    "equityShortTermRisk": dict,
    "globalLpplRisk": dict,
    "regionalMonitor": dict,
    "sourceStatus": list,
}


def stamp_dashboard_contract(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Stamp the current envelope version in-place and return ``dashboard``."""
    dashboard.setdefault("schemaVersion", CURRENT_SCHEMA_VERSION)
    return dashboard


def dashboard_contract_issues(dashboard: Any) -> list[str]:
    """Return structural envelope violations without duplicating smoke checks."""
    if not isinstance(dashboard, dict):
        return ["dashboard must be an object"]

    issues: list[str] = []
    version = dashboard.get("schemaVersion")
    if not isinstance(version, str) or not version:
        issues.append("schemaVersion must be a non-empty string")
    elif version not in SUPPORTED_SCHEMA_VERSIONS:
        issues.append(f"unsupported schemaVersion: {version}")

    raw_as_of = dashboard.get("asOf")
    parsed_as_of: date | None = None
    if not isinstance(raw_as_of, str) or not raw_as_of.strip():
        issues.append("asOf must be a non-empty string")
    else:
        try:
            parsed_as_of = date.fromisoformat(raw_as_of.strip())
        except ValueError:
            issues.append("asOf must be an ISO date")

    raw_generated_at = dashboard.get("generatedAt")
    parsed_generated_at: datetime | None = None
    if not isinstance(raw_generated_at, str) or not raw_generated_at.strip():
        issues.append("generatedAt must be a non-empty string")
    else:
        try:
            parsed_generated_at = datetime.fromisoformat(raw_generated_at.strip().replace("Z", "+00:00"))
        except ValueError:
            issues.append("generatedAt must be an ISO datetime")
        else:
            if parsed_generated_at.tzinfo is None or parsed_generated_at.utcoffset() is None:
                issues.append("generatedAt must include a timezone")

    if parsed_as_of is not None and parsed_generated_at is not None and parsed_as_of > parsed_generated_at.date():
        issues.append("asOf must not be after generatedAt date")

    source_status = dashboard.get("sourceStatus")
    if source_status is not None and not isinstance(source_status, list):
        issues.append("sourceStatus must be an array when present")

    for key, expected_type in _OPTIONAL_TOP_LEVEL_TYPES.items():
        value = dashboard.get(key)
        if value is not None and not isinstance(value, expected_type):
            issues.append(f"{key} has invalid type {type(value).__name__}")

    curve = dashboard.get("curve")
    if isinstance(curve, dict):
        tenors = curve.get("tenors")
        if tenors is not None and not isinstance(tenors, list):
            issues.append("curve.tenors must be an array")

    issues.extend(_decision_contract_issues(dashboard))
    issues.extend(_source_freshness_contract_issues(source_status))

    try:
        json.dumps(dashboard, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        issues.append(f"dashboard must be strict JSON serializable: {exc}")

    return issues


def _equity_normalized_weights_match_contract(value: Any) -> bool:
    """Compare a serialized weight audit with the current canonical mapping."""
    if not isinstance(value, dict) or set(value) != set(CURRENT_EQUITY_RISK_NORMALIZED_WEIGHTS):
        return False
    return all(
        isinstance(value.get(key), (int, float))
        and not isinstance(value.get(key), bool)
        and float(value[key]) == expected
        for key, expected in CURRENT_EQUITY_RISK_NORMALIZED_WEIGHTS.items()
    )


def _equity_score_weight_contract_current(score_scale: dict[str, Any]) -> bool:
    """Verify a live score-scale audit against this module's source of truth."""
    required_components = sorted(CURRENT_EQUITY_RISK_SCORED_COMPONENTS)
    return bool(
        score_scale.get("id") == CURRENT_EQUITY_RISK_SCORE_SCALE_ID
        and score_scale.get("requiredScoredComponents") == required_components
        and score_scale.get("scoredComponents") == required_components
        and _equity_normalized_weights_match_contract(
            score_scale.get("canonicalNormalizedWeights")
        )
        and _equity_normalized_weights_match_contract(
            score_scale.get("observedNormalizedWeights")
        )
        and score_scale.get("weightMismatches") == []
        and score_scale.get("weightsMatchCanonical") is True
    )


def _plain_number(value: Any) -> bool:
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _nonnegative_integer(value: Any) -> bool:
    return bool(
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _equity_backtest_score_scale_current(backtest: dict[str, Any]) -> bool:
    """Reconcile the replay scale itself, not a producer's summary boolean."""
    score_scale = (
        backtest.get("scoreScale")
        if isinstance(backtest.get("scoreScale"), dict)
        else {}
    )
    required_components = sorted(CURRENT_EQUITY_RISK_SCORED_COMPONENTS)
    observation_count = score_scale.get("observationCount")
    comparable_count = score_scale.get("comparableObservationCount")
    return bool(
        score_scale.get("id") == CURRENT_EQUITY_RISK_SCORE_SCALE_ID
        and score_scale.get("requiredScoredComponents") == required_components
        and score_scale.get("thresholdComparable") is True
        and _equity_normalized_weights_match_contract(
            score_scale.get("canonicalNormalizedWeights")
        )
        and _equity_normalized_weights_match_contract(
            score_scale.get("observedNormalizedWeights")
        )
        and score_scale.get("weightsMatchCanonical") is True
        and score_scale.get("weightMismatchedObservationCount") == 0
        and _nonnegative_integer(observation_count)
        and observation_count > 0
        and _nonnegative_integer(comparable_count)
        and comparable_count == observation_count
        and score_scale.get("mismatchedObservationCount") == 0
    )


def _equity_wilson_lower_bound_pct(successes: int, observations: int) -> float | None:
    """Dependency-free mirror of the production two-sided 95% Wilson bound."""
    if observations <= 0 or successes < 0 or successes > observations:
        return None
    z_score = 1.959963984540054
    probability = successes / observations
    z_squared = z_score * z_score
    denominator = 1.0 + z_squared / observations
    center = probability + z_squared / (2.0 * observations)
    margin = z_score * math.sqrt(
        probability * (1.0 - probability) / observations
        + z_squared / (4.0 * observations * observations)
    )
    return round(100.0 * (center - margin) / denominator, 1)


def _equity_oos_action_evidence_current(
    surface: dict[str, Any],
    backtest: dict[str, Any],
    production_validation: dict[str, Any],
) -> bool:
    """Cross-check the fixed production rule against its serialized OOS test."""
    walk_forward = (
        backtest.get("walkForward")
        if isinstance(backtest.get("walkForward"), dict)
        else {}
    )
    threshold_tests = (
        walk_forward.get("thresholdTests")
        if isinstance(walk_forward.get("thresholdTests"), list)
        else []
    )
    production_tests = [
        row
        for row in threshold_tests
        if isinstance(row, dict) and row.get("productionUse") is True
    ]
    if walk_forward.get("available") is not True or len(production_tests) != 1:
        return False
    test = production_tests[0]
    score = surface.get("score")
    threshold = test.get("threshold")
    sample_size = test.get("sampleSize")
    alert_clusters = test.get("independentAlertClusters")
    hit_clusters = test.get("independentHitClusters")
    base_rate = test.get("baseRate")
    if not (
        _plain_number(score)
        and _plain_number(threshold)
        and float(threshold) == float(CURRENT_EQUITY_RISK_PRODUCTION_THRESHOLD)
        and float(score) >= float(threshold)
        and test.get("sampleRole") == "walkForwardOos"
        and test.get("validationStatus") == "validated"
        and test.get("oosValidated") is True
        and _nonnegative_integer(sample_size)
        and sample_size >= 30
        and _nonnegative_integer(alert_clusters)
        and alert_clusters >= 3
        and _nonnegative_integer(hit_clusters)
        and hit_clusters <= alert_clusters
        and _plain_number(base_rate)
    ):
        return False
    precision_lower_bound = _equity_wilson_lower_bound_pct(
        hit_clusters,
        alert_clusters,
    )
    if (
        precision_lower_bound is None
        or precision_lower_bound < float(base_rate) + 5.0
    ):
        return False
    validation_lower_bound = production_validation.get(
        "clusterPrecisionWilsonLower95"
    )
    return bool(
        production_validation.get("available") is True
        and production_validation.get("validationEvidenceComplete") is True
        and production_validation.get("sampleRole") == "walkForwardOos"
        and production_validation.get("independentAlertClusters") == alert_clusters
        and _plain_number(validation_lower_bound)
        and float(validation_lower_bound) == precision_lower_bound
        and _plain_number(production_validation.get("baseRate"))
        and float(production_validation["baseRate"]) == float(base_rate)
        and _plain_number(production_validation.get("threshold"))
        and float(production_validation["threshold"]) == float(threshold)
        and _plain_number(production_validation.get("expectedThreshold"))
        and float(production_validation["expectedThreshold"])
        == float(CURRENT_EQUITY_RISK_PRODUCTION_THRESHOLD)
    )


def _regional_lppl_model_audit_complete(validation: dict[str, Any]) -> bool:
    audit = validation.get("replayModelAudit")
    if not isinstance(audit, dict):
        return False
    production_model_id = str(audit.get("productionModelSpecId") or "")
    live_model_id = str(audit.get("liveModelSpecId") or "")
    observed_model_ids = audit.get("observedModelSpecIds")
    observation_count = audit.get("observationCount")
    comparable_count = audit.get("comparableObservationCount")
    valid_counts = bool(
        isinstance(observation_count, (int, float))
        and not isinstance(observation_count, bool)
        and isinstance(comparable_count, (int, float))
        and not isinstance(comparable_count, bool)
        and float(observation_count) > 0
        and float(comparable_count) == float(observation_count)
    )
    return bool(
        audit.get("required") is True
        and audit.get("enforcementPass") is True
        and audit.get("status") == "comparable"
        and audit.get("comparable") is True
        and audit.get("replayComparable") is True
        and audit.get("liveComparable") is True
        and audit.get("liveModelMetadataAvailable") is True
        and audit.get("liveValidationComparable") is True
        and production_model_id
        and live_model_id == production_model_id
        and observed_model_ids == [production_model_id]
        and valid_counts
        and audit.get("unknownModelSpecCount") == 0
        and audit.get("mismatchedModelSpecCount") == 0
    )


def _regional_lppl_row_current_trigger_complete(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
    score = row.get("score")
    threshold = validation.get("productionThreshold")
    numeric_threshold_crossed = bool(
        isinstance(score, (int, float))
        and not isinstance(score, bool)
        and isinstance(threshold, (int, float))
        and not isinstance(threshold, bool)
        and float(score) >= float(threshold)
    )
    return bool(
        row.get("available") is True
        and row.get("fitProductionEligible") is True
        and row.get("productionEligible") is True
        and row.get("actionable") is True
        and row.get("scoreUse") == "production_signal"
        and row.get("actionabilityStatus") == "current_threshold_triggered"
        and validation.get("productionEvidenceAvailable") is True
        and validation.get("productionActionable") is True
        and _regional_lppl_model_audit_complete(validation)
        and numeric_threshold_crossed
    )


def _regional_signal_contract_complete(signal: Any) -> bool:
    """Dependency-free mirror of the regional production factor gate."""
    if not isinstance(signal, dict) or signal.get("available") is False:
        return False
    fold_stability = (
        signal.get("foldStability3m")
        if isinstance(signal.get("foldStability3m"), dict)
        else {}
    )
    return bool(
        signal.get("classification") == "leading"
        and _plain_number(signal.get("oosIc3m"))
        and float(signal["oosIc3m"]) > 0.0
        and signal.get("wrongWay") is False
        and _plain_number(signal.get("lift"))
        and float(signal["lift"]) > 1.0
        and signal.get("robust") is True
        and signal.get("fdrSignificant3m") is True
        and signal.get("inferenceValid3m") is True
        and fold_stability.get("stablePositive") is True
        and signal.get("actionableRobust") is True
        and _plain_number(signal.get("observationCount"))
        and float(signal["observationCount"])
        >= _REGIONAL_ACTIONABLE_MIN_OBSERVATIONS
        and _plain_number(signal.get("oosSampleSize3m"))
        and float(signal["oosSampleSize3m"])
        >= _REGIONAL_ACTIONABLE_MIN_OOS_OBSERVATIONS
        and _plain_number(signal.get("oosAlertCount"))
        and float(signal["oosAlertCount"])
        >= _REGIONAL_ACTIONABLE_MIN_OOS_ALERTS
    )


def _regional_representative_index(indices: Any) -> dict[str, Any] | None:
    if not isinstance(indices, list):
        return None
    validated = [
        row
        for row in indices
        if isinstance(row, dict)
        and isinstance(row.get("factorValidation"), dict)
        and row["factorValidation"].get("available") is True
    ]
    if not validated:
        return None
    return next(
        (
            row
            for row in validated
            if str(row.get("symbol") or "").upper() == "SPY"
        ),
        validated[0],
    )


def _regional_alert_value_matches(value: Any, source: Any, digits: int) -> bool:
    return bool(
        _plain_number(value)
        and _plain_number(source)
        and float(value) == round(float(source), digits)
    )


def _regional_factor_alert_contract_complete(region: dict[str, Any]) -> bool:
    """Bind a displayed factor breach to its actual OOS evidence and reading."""
    alert = (
        region.get("factorAlert")
        if isinstance(region.get("factorAlert"), dict)
        else {}
    )
    if not (
        alert.get("available") is True
        and alert.get("state") == "breached"
        and alert.get("actionable") is True
        and alert.get("scoreUse") == "production_signal"
        and _plain_number(alert.get("current"))
        and _plain_number(alert.get("threshold"))
        and float(alert["current"]) >= float(alert["threshold"])
    ):
        return False
    representative = _regional_representative_index(region.get("indices"))
    if representative is None:
        return False
    factor_validation = representative["factorValidation"]
    if factor_validation.get("independentHoldout") is not True:
        return False

    source = str(alert.get("source") or "")
    factor_id = str(alert.get("factorId") or "")
    if source == "composite":
        composite = (
            factor_validation.get("composite")
            if isinstance(factor_validation.get("composite"), dict)
            else {}
        )
        current = composite.get("currentValue")
        threshold = composite.get("alertThreshold")
        return bool(
            factor_id == "regionComposite"
            and composite.get("available") is True
            and composite.get("beatsBestSingleFactor") is True
            and composite.get("direction") == "higher_risk"
            and _regional_signal_contract_complete(composite)
            and _plain_number(current)
            and _plain_number(threshold)
            and float(current) >= float(threshold)
            and _regional_alert_value_matches(alert.get("current"), current, 2)
            and _regional_alert_value_matches(alert.get("threshold"), threshold, 2)
        )
    if source != "factor" or factor_id not in _REGIONAL_RISK_FACTOR_IDS:
        return False
    factors = (
        factor_validation.get("factors")
        if isinstance(factor_validation.get("factors"), list)
        else []
    )
    factor = next(
        (
            item
            for item in factors
            if isinstance(item, dict) and item.get("id") == factor_id
        ),
        None,
    )
    if not _regional_signal_contract_complete(factor):
        return False
    threshold = factor.get("alertThreshold")
    if factor_id == "realizedVol":
        price_factors = (
            representative.get("priceFactors")
            if isinstance(representative.get("priceFactors"), dict)
            else {}
        )
        current = price_factors.get("realizedVol")
    else:
        current = representative.get("score")
    return bool(
        _plain_number(current)
        and _plain_number(threshold)
        and float(current) >= float(threshold)
        and _regional_alert_value_matches(alert.get("current"), current, 1)
        and _regional_alert_value_matches(alert.get("threshold"), threshold, 1)
    )


def _decision_contract_issues(dashboard: dict[str, Any]) -> list[str]:
    """Reject contradictory action layers when a producer emits audit fields.

    Older snapshots may not contain these fields, so their absence remains
    backwards-compatible.  Once a producer declares a signal non-actionable,
    however, it must not publish a numeric exposure band beside that verdict.
    """
    issues: list[str] = []
    for key in ("spyEarlyWarning", "equityShortTermRisk"):
        surface = dashboard.get(key)
        if not isinstance(surface, dict):
            continue
        allocation = surface.get("allocation")
        allocation = allocation if isinstance(allocation, dict) else {}
        validity = surface.get("predictiveValidity")
        validity = validity if isinstance(validity, dict) else {}
        production_validation = surface.get("productionValidation")
        production_validation = (
            production_validation
            if isinstance(production_validation, dict)
            else {}
        )
        score_scale = surface.get("scoreScale")
        score_scale = score_scale if isinstance(score_scale, dict) else {}

        if key == "spyEarlyWarning" and allocation.get("exposureBandPct") is not None:
            exposure_band = allocation.get("exposureBandPct")
            rules_version_audit = validity.get("rulesVersionAudit")
            rules_version_audit = (
                rules_version_audit
                if isinstance(rules_version_audit, dict)
                else {}
            )
            surface_rules_version = surface.get("rulesVersion")
            audited_versions = (
                rules_version_audit.get("expectedRulesVersion"),
                rules_version_audit.get("surfaceRulesVersion"),
                rules_version_audit.get("validationRulesVersion"),
                rules_version_audit.get("aggregateRulesVersion"),
            )
            rules_version_gate_passed = bool(
                isinstance(surface_rules_version, str)
                and surface_rules_version.strip()
                and all(
                    isinstance(version, str) and version.strip()
                    for version in audited_versions
                )
                and len({surface_rules_version.strip(), *(version.strip() for version in audited_versions)}) == 1
                and surface_rules_version.strip() == CURRENT_SPY_WARNING_RULES_VERSION
                and rules_version_audit.get("complete") is True
                and rules_version_audit.get("matched") is True
            )
            aggregate_root_gate_passed = bool(
                surface.get("aggregateCiRobust") is True
                and surface.get("aggregateStatisticalGatePassed") is True
                and surface.get("aggregateActionableRobust") is True
                and surface.get("aggregateRobust") is True
                and surface.get("scoreUse") == "production_signal"
                and validity.get("status") == "actionable"
                and validity.get("statisticalGatePassed")
                is surface.get("aggregateStatisticalGatePassed")
                and validity.get("actionable")
                is surface.get("aggregateActionableRobust")
            )
            if not (
                isinstance(exposure_band, list)
                and len(exposure_band) == 2
                and all(
                    isinstance(item, (int, float)) and not isinstance(item, bool)
                    for item in exposure_band
                )
                and 0 <= float(exposure_band[0]) <= float(exposure_band[1]) <= 150
            ):
                issues.append(
                    "spyEarlyWarning numeric allocation band must be ordered within 0..150"
                )
            if not (
                isinstance(surface.get("predictiveValidity"), dict)
                and all(
                    isinstance(validity.get(field), bool)
                    for field in ("actionable", "statisticalGatePassed", "independentHoldout")
                )
            ):
                issues.append(
                    "spyEarlyWarning numeric allocation requires complete predictiveValidity audit"
                )
            if not rules_version_gate_passed:
                issues.append(
                    "spyEarlyWarning numeric allocation requires complete matching rulesVersion audit"
                )
            if not aggregate_root_gate_passed:
                issues.append(
                    "spyEarlyWarning numeric allocation requires matching aggregate production evidence"
                )
            if not isinstance(surface.get("actionable"), bool):
                issues.append(
                    "spyEarlyWarning numeric allocation requires explicit actionable verdict"
                )
            if not isinstance(allocation.get("actionable"), bool):
                issues.append(
                    "spyEarlyWarning numeric allocation requires allocation.actionable verdict"
                )
            spy_action_gates = (
                validity.get("actionable"),
                validity.get("statisticalGatePassed"),
                validity.get("independentHoldout"),
                rules_version_gate_passed,
                aggregate_root_gate_passed,
                surface.get("actionable"),
                allocation.get("actionable"),
            )
            if not all(item is True for item in spy_action_gates):
                issues.append(
                    "spyEarlyWarning numeric allocation requires every production action gate to pass"
                )

        # A numeric equity allocation is a production decision, not a legacy
        # display convenience.  Backwards compatibility remains available for
        # research/context-only snapshots with no band, but a band must carry
        # the complete dedicated action audit so cache-hit and partial-merge
        # paths cannot silently republish a pre-contract allocation.
        if key == "equityShortTermRisk" and allocation.get("exposureBandPct") is not None:
            exposure_band = allocation.get("exposureBandPct")
            backtest = (
                surface.get("backtest")
                if isinstance(surface.get("backtest"), dict)
                else {}
            )
            score_weight_contract_current = _equity_score_weight_contract_current(
                score_scale
            )
            backtest_score_scale_current = _equity_backtest_score_scale_current(
                backtest
            )
            oos_action_evidence_current = _equity_oos_action_evidence_current(
                surface,
                backtest,
                production_validation,
            )
            production_threshold_contract_current = all(
                isinstance(production_validation.get(field), (int, float))
                and not isinstance(production_validation.get(field), bool)
                and float(production_validation[field])
                == float(CURRENT_EQUITY_RISK_PRODUCTION_THRESHOLD)
                for field in ("threshold", "expectedThreshold")
            )
            if not (
                isinstance(exposure_band, list)
                and len(exposure_band) == 2
                and all(
                    isinstance(item, (int, float)) and not isinstance(item, bool)
                    for item in exposure_band
                )
                and 0 <= float(exposure_band[0]) <= float(exposure_band[1]) <= 100
            ):
                issues.append(
                    "equityShortTermRisk numeric allocation band must be ordered within 0..100"
                )
            if not (
                isinstance(surface.get("scoreScale"), dict)
                and isinstance(score_scale.get("coreComplete"), bool)
                and isinstance(score_scale.get("thresholdComparable"), bool)
            ):
                issues.append(
                    "equityShortTermRisk numeric allocation requires explicit scoreScale audit"
                )
            if not score_weight_contract_current:
                issues.append(
                    "equityShortTermRisk numeric allocation requires current canonical scoreScale weight audit"
                )
            if not backtest_score_scale_current:
                issues.append(
                    "equityShortTermRisk numeric allocation requires matching replay backtest scoreScale audit"
                )
            if not oos_action_evidence_current:
                issues.append(
                    "equityShortTermRisk numeric allocation requires a validated fixed-threshold walkForward OOS production test"
                )
            if not production_threshold_contract_current:
                issues.append(
                    "equityShortTermRisk numeric allocation requires current production threshold audit"
                )
            if not isinstance(surface.get("actionable"), bool):
                issues.append(
                    "equityShortTermRisk numeric allocation requires explicit actionable verdict"
                )
            if not isinstance(allocation.get("actionable"), bool):
                issues.append(
                    "equityShortTermRisk numeric allocation requires allocation.actionable verdict"
                )
            if not (
                isinstance(surface.get("productionValidation"), dict)
                and all(
                    isinstance(production_validation.get(field), bool)
                    for field in (
                        "available",
                        "scoreContractAllowsAction",
                        "thresholdValidated",
                        "currentTriggered",
                        "actionable",
                        "validationEvidenceComplete",
                        "scoreScaleMatchesBacktest",
                        "scoreWeightsMatchBacktest",
                    )
                )
            ):
                issues.append(
                    "equityShortTermRisk numeric allocation requires complete productionValidation boolean audit"
                )
            action_gates = (
                score_scale.get("coreComplete"),
                score_scale.get("thresholdComparable"),
                surface.get("actionable"),
                allocation.get("actionable"),
                production_validation.get("available"),
                production_validation.get("scoreContractAllowsAction"),
                production_validation.get("thresholdValidated"),
                production_validation.get("currentTriggered"),
                production_validation.get("actionable"),
                production_validation.get("validationEvidenceComplete"),
                production_validation.get("scoreScaleMatchesBacktest"),
                production_validation.get("scoreWeightsMatchBacktest"),
                score_weight_contract_current,
                backtest_score_scale_current,
                oos_action_evidence_current,
                production_threshold_contract_current,
            )
            if not all(item is True for item in action_gates):
                issues.append(
                    "equityShortTermRisk numeric allocation requires every production action gate to pass"
                )

        declared_non_actionable = (
            validity.get("actionable") is False
            or production_validation.get("actionable") is False
            or score_scale.get("thresholdComparable") is False
            or surface.get("actionable") is False
            or allocation.get("actionable") is False
        )
        if declared_non_actionable and allocation.get("exposureBandPct") is not None:
            issues.append(f"{key}.allocation must not expose a band when non-actionable")
        if validity.get("actionable") is False and allocation.get("actionable") is not False:
            issues.append(f"{key}.allocation.actionable must be false when predictive validity fails")
        if (
            production_validation.get("actionable") is False
            and allocation.get("actionable") is not False
        ):
            issues.append(
                f"{key}.allocation.actionable must be false when production validation fails"
            )
        if (
            isinstance(surface.get("actionable"), bool)
            and isinstance(production_validation.get("actionable"), bool)
            and surface.get("actionable") is not production_validation.get("actionable")
        ):
            issues.append(f"{key}.actionable must match productionValidation.actionable")
        if (
            isinstance(surface.get("actionable"), bool)
            and isinstance(allocation.get("actionable"), bool)
            and surface.get("actionable") is not allocation.get("actionable")
        ):
            issues.append(f"{key}.actionable must match allocation.actionable")
        if score_scale.get("coreComplete") is False and surface.get("actionable") is not False:
            issues.append(f"{key}.actionable must be false when score core is incomplete")

    regional = dashboard.get("regionalMonitor")
    if isinstance(regional, dict):
        regions = regional.get("regions")
        actionable_region_keys: set[str] = set()
        if isinstance(regions, list):
            for index, region in enumerate(regions):
                if not isinstance(region, dict):
                    continue
                allocation = region.get("allocation")
                allocation = allocation if isinstance(allocation, dict) else {}
                band = allocation.get("exposureBandPct")
                band_valid = bool(
                    isinstance(band, list)
                    and len(band) == 2
                    and all(
                        isinstance(item, (int, float)) and not isinstance(item, bool)
                        for item in band
                    )
                    and 0 <= float(band[0]) <= float(band[1]) <= 150
                )
                alert = region.get("factorAlert") if isinstance(region.get("factorAlert"), dict) else {}
                factor_triggered = bool(
                    allocation.get("validatedFactorTriggered") is True
                    and _regional_factor_alert_contract_complete(region)
                )
                indices = region.get("indices") if isinstance(region.get("indices"), list) else []
                lppl_triggered = bool(
                    allocation.get("productionLpplTriggered") is True
                    and any(_regional_lppl_row_current_trigger_complete(row) for row in indices)
                )
                complete_action_gate = bool(
                    allocation.get("actionable") is True
                    and allocation.get("scoreUse") == "production_signal"
                    and allocation.get("actionabilityStatus") == "current_lppl_or_validated_factor_trigger"
                    and band_valid
                    and (lppl_triggered or factor_triggered)
                )
                if band is not None and not band_valid:
                    issues.append(
                        f"regionalMonitor.regions[{index}].allocation band must be ordered within 0..150"
                    )
                if band is not None and not complete_action_gate:
                    issues.append(
                        f"regionalMonitor.regions[{index}].allocation numeric band requires complete current production trigger audit"
                    )
                if allocation.get("actionable") is True and band is None:
                    issues.append(
                        f"regionalMonitor.regions[{index}].allocation actionable verdict requires a numeric band"
                    )
                if complete_action_gate:
                    actionable_region_keys.add(str(region.get("key") or ""))
                if alert.get("available") is True and alert.get("state") == "breached" and not (
                    alert.get("actionable") is True
                    and alert.get("scoreUse") == "production_signal"
                    and factor_triggered
                ):
                    issues.append(
                        f"regionalMonitor.regions[{index}].factorAlert breach requires complete current trigger audit"
                    )
                internal_rotation = (
                    region.get("internalRotation")
                    if isinstance(region.get("internalRotation"), dict)
                    else {}
                )
                internal_tilt = str(internal_rotation.get("tilt") or "")
                if internal_rotation.get("available") is True and internal_tilt in {"broad", "tech"}:
                    riskier_symbol = "QQQ" if internal_tilt == "broad" else "SPY"
                    riskier_row_complete = any(
                        isinstance(row, dict)
                        and str(row.get("symbol") or "").upper() == riskier_symbol
                        and _regional_lppl_row_current_trigger_complete(row)
                        for row in indices
                    )
                    if not (
                        internal_rotation.get("actionable") is True
                        and internal_rotation.get("scoreUse") == "production_signal"
                        and riskier_row_complete
                    ):
                        issues.append(
                            f"regionalMonitor.regions[{index}].internalRotation directional tilt requires complete current production trigger audit"
                        )
                if allocation.get("confidence") != "high":
                    continue
                factors = allocation.get("validatedLeadingFactors")
                has_validated_factor = isinstance(factors, list) and bool(factors)
                has_production_lppl = allocation.get("productionLpplTriggered") is True
                if (
                    not has_validated_factor
                    and allocation.get("validatedComposite") is not True
                    and not has_production_lppl
                ):
                    issues.append(
                        f"regionalMonitor.regions[{index}].allocation high confidence requires validated evidence"
                    )
        rotation = regional.get("rotation") if isinstance(regional.get("rotation"), dict) else {}
        for field in ("favorRegions", "reduceRegions"):
            values = rotation.get(field)
            if not isinstance(values, list):
                continue
            unsafe = [str(value) for value in values if str(value) not in actionable_region_keys]
            if unsafe:
                issues.append(
                    f"regionalMonitor.rotation.{field} contains regions without complete production action audit"
                )
    return issues


def dashboard_decision_contract_issues(dashboard: Any) -> list[str]:
    """Expose action-layer checks for legacy envelopes and health probes.

    A running service may still hold an older producer after code is updated.
    Health checks need to detect unsafe decision payloads even when the legacy
    snapshot predates the current top-level schema envelope.
    """
    if not isinstance(dashboard, dict):
        return ["dashboard must be an object"]
    return _decision_contract_issues(dashboard)


def _source_freshness_contract_issues(source_status: Any) -> list[str]:
    """Validate structured freshness dates when a source row supplies them."""
    if not isinstance(source_status, list):
        return []
    issues: list[str] = []
    for index, row in enumerate(source_status):
        if not isinstance(row, dict):
            issues.append(f"sourceStatus[{index}] must be an object")
            continue
        raw_observation = row.get("observationDate")
        raw_period_end = row.get("observationPeriodEnd")
        if raw_observation is None and raw_period_end is None:
            continue
        try:
            observation = date.fromisoformat(str(raw_observation))
            period_end = date.fromisoformat(str(raw_period_end))
        except ValueError:
            issues.append(f"sourceStatus[{index}] freshness dates must be ISO dates")
            continue
        if period_end < observation:
            issues.append(f"sourceStatus[{index}] observationPeriodEnd must not precede observationDate")
        freshness_basis = row.get("freshnessBasis")
        if freshness_basis not in {
            "observation-date",
            "observation-period-end",
            "calendar-horizon",
        }:
            issues.append(f"sourceStatus[{index}].freshnessBasis is invalid")
        if freshness_basis == "calendar-horizon":
            try:
                coverage_through = date.fromisoformat(str(row.get("coverageThrough")))
            except ValueError:
                issues.append(f"sourceStatus[{index}].coverageThrough must be an ISO date")
            else:
                if coverage_through != period_end:
                    issues.append(
                        f"sourceStatus[{index}].coverageThrough must equal observationPeriodEnd"
                    )
    return issues


def require_dashboard_contract(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Stamp and validate a payload, raising before it can be published."""
    stamp_dashboard_contract(dashboard)
    issues = dashboard_contract_issues(dashboard)
    if issues:
        raise ValueError("dashboard contract failed: " + "; ".join(issues))
    return dashboard
