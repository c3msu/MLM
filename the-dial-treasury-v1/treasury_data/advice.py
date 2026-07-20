"""Portfolio-overview advice cluster extracted from build_dashboard.py
(behavior-unchanged, 2026-06-19 全面重构 Phase 1). The page-top portfolio-overview card:
per-layer overview rows + evidence, the global-LPPL overview state/evidence bridge
(reads the LPPL risk dict as data), regional + US-internal tilt rows, and
build_portfolio_overview. Consumes already-built dashboard sections (regional monitor,
LPPL risk, signal validation) as data; depends only on dashboard_core helpers.
Re-exported via `from .advice import *`."""
from __future__ import annotations

from typing import Any

from .dashboard_core import *  # noqa: F401,F403
from .scoring_bhadial import bhadial_usable_reliability_score
from .scoring_lppl import GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
from .scoring_lppl_validation import (
    GLOBAL_LPPL_OOS_MIN_EVALUATION_OBSERVATIONS,
    GLOBAL_LPPL_OOS_MIN_INDEPENDENT_ALERTS,
    GLOBAL_LPPL_OOS_MIN_INDEPENDENT_BASE_OBSERVATIONS,
    global_lppl_validation_weight,
)
from .scoring_regional import (
    regional_allocation_qualifies_as_actionable,
    regional_factor_alert_qualifies_as_actionable,
    regional_lppl_index_qualifies_as_actionable,
)


PORTFOLIO_OVERVIEW_LPPL_RISK_BAND = [60, 85]
PORTFOLIO_OVERVIEW_LPPL_WATCH_BAND = [85, 100]


def macro_reliability_regime(score: float | None) -> str:
    """Classify the decision-safe score without reusing a legacy-score label."""
    if score is None:
        return "数据不足"
    if score >= 70:
        return "流动性宽松"
    if score >= 55:
        return "边际宽松"
    if score > 45:
        return "中性"
    if score > 30:
        return "偏紧"
    return "紧缩压力"


def portfolio_overview_evidence(row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {
            "available": False,
            "validationStatus": "not-assessed",
            "predictiveValidity": {
                "status": "not-assessed",
                "actionable": False,
                "validationType": "generic-weekly",
            },
            "note": "证据不足: 该层尚无走出样本验证。",
        }
    actionable = row.get("actionableRobust") is True
    status = "validated" if actionable else "research-validation"
    return {
        "available": True,
        "oosHitRate": optional_float(row.get("hitRateOos")),
        "baseRate": optional_float(row.get("baseRate")),
        "lift": optional_float(row.get("lift")),
        "leadTimeDays": optional_float(row.get("leadTimeDays")),
        "sampleSize": row.get("observationCount"),
        "classification": str(row.get("classification") or ""),
        "actionableRobust": row.get("actionableRobust"),
        "fdrQValue3m": optional_float(row.get("fdrQValue3m")),
        "foldStability3m": row.get("foldStability3m") if isinstance(row.get("foldStability3m"), dict) else {},
        "validationStatus": status,
        "predictiveValidity": {
            "status": status,
            "actionable": actionable,
            "validationType": "generic-weekly",
            "independentHoldout": row.get("independentHoldout") is True,
        },
    }


def _percent_rate(value: Any) -> float | None:
    """Normalize stored percentage metrics (70.6) to a public rate (0.706)."""
    number = optional_float(value)
    if number is None:
        return None
    return number / 100.0 if abs(number) > 1.0 else number


def _nonnegative_int(value: Any) -> int:
    """Coerce audit counts without letting malformed legacy fields raise."""
    number = optional_float(value)
    return max(0, int(number)) if number is not None else 0


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def equity_short_term_overview_evidence(
    equity_short_term_risk: dict[str, Any] | None,
) -> dict[str, Any]:
    """Read the equity model's dedicated 15-session walk-forward contract.

    The generic 91-calendar-day signal family intentionally excludes this model.
    Treating that absence as ``not assessed`` discards its real evidence.  Only a
    pre-registered/production threshold can make the *current* layer actionable;
    calibration-selected research thresholds remain visible but non-binding.
    """
    panel = equity_short_term_risk if isinstance(equity_short_term_risk, dict) else {}
    backtest = panel.get("backtest") if isinstance(panel.get("backtest"), dict) else {}
    walk_forward = backtest.get("walkForward") if isinstance(backtest.get("walkForward"), dict) else {}
    if walk_forward.get("available") is not True:
        return {
            "available": False,
            "validationStatus": "not-assessed",
            "predictiveValidity": {
                "status": "not-assessed",
                "actionable": False,
                "validationType": "dedicated-15d-walk-forward",
            },
            "validationPath": "equityShortTermRisk.backtest.walkForward",
            "note": "证据不足: 短周期模型专属15交易日走出样本不可用。",
        }

    threshold_tests = [
        row
        for row in walk_forward.get("thresholdTests", [])
        if isinstance(row, dict)
    ]
    production_test = next((row for row in threshold_tests if row.get("productionUse") is True), None)
    out_of_sample = walk_forward.get("outOfSample") if isinstance(walk_forward.get("outOfSample"), dict) else {}
    selected_test = (
        out_of_sample.get("selectedThresholdTest")
        if isinstance(out_of_sample.get("selectedThresholdTest"), dict)
        else None
    )
    test = production_test or selected_test
    if not isinstance(test, dict):
        return {
            "available": False,
            "validationStatus": "dedicated-oos-incomplete",
            "predictiveValidity": {
                "status": "dedicated-oos-incomplete",
                "actionable": False,
                "validationType": "dedicated-15d-walk-forward",
            },
            "validationPath": "equityShortTermRisk.backtest.walkForward",
            "note": "专属走出样本存在，但没有可识别的OOS阈值测试。",
        }

    hit = _percent_rate(test.get("precision"))
    base = _percent_rate(test.get("baseRate"))
    lift = optional_float(test.get("liftVsBaseRate"))
    if lift is None and hit is not None and base:
        lift = hit / base
    sample_size = _nonnegative_int(
        test.get("sampleSize")
        if test.get("sampleSize") is not None
        else out_of_sample.get("sampleSize")
    )
    alert_count = _nonnegative_int(test.get("alertDays"))
    threshold = optional_float(test.get("threshold"))
    production_validation = (
        panel.get("productionValidation")
        if isinstance(panel.get("productionValidation"), dict)
        else {}
    )
    score_scale = panel.get("scoreScale") if isinstance(panel.get("scoreScale"), dict) else {}
    allocation = panel.get("allocation") if isinstance(panel.get("allocation"), dict) else {}
    production_supported = bool(
        production_test is not None
        and production_test.get("oosValidated") is True
        and production_validation.get("available") is True
        and production_validation.get("thresholdValidated") is True
    )
    score = optional_float(panel.get("score"))
    # Do not reconstruct a production verdict from a score and attractive
    # historical precision.  The scoring layer publishes an explicit contract;
    # absent fields identify a legacy/research payload and therefore fail closed.
    score_contract_allows_action = bool(
        score_scale.get("coreComplete") is True
        and score_scale.get("thresholdComparable") is True
        and production_validation.get("scoreContractAllowsAction") is True
    )
    current_triggered = bool(
        production_supported
        and score_contract_allows_action
        and production_validation.get("currentTriggered") is True
        and production_validation.get("actionable") is True
        and panel.get("actionable") is True
        and allocation.get("actionable") is True
        and score is not None
        and threshold is not None
        and score >= threshold
    )
    status = "dedicated-oos-validated-threshold" if production_supported else "dedicated-oos-research"
    return {
        "available": True,
        "oosHitRate": round(hit, 3) if hit is not None else None,
        "baseRate": round(base, 3) if base is not None else None,
        "lift": round(lift, 2) if lift is not None else None,
        "leadTimeDays": optional_float(test.get("avgDrawdownLeadDaysWhenHit")),
        "sampleSize": sample_size,
        "oosAlertCount": alert_count,
        "recall": _percent_rate(test.get("recall")),
        "threshold": threshold,
        "rule": str(test.get("rule") or ""),
        "productionUse": production_test is not None,
        "oosValidated": production_test.get("oosValidated") is True if production_test else False,
        "scoreContractAllowsAction": score_contract_allows_action,
        "currentTriggered": current_triggered,
        "validationStatus": status,
        "validationPath": "equityShortTermRisk.backtest.walkForward",
        "predictiveValidity": {
            "status": status,
            "actionable": current_triggered,
            "thresholdValidated": production_supported,
            "currentTriggered": current_triggered,
            "validationType": "dedicated-15d-walk-forward",
            "independentHoldout": False,
        },
        "note": (
            f"专属OOS仅验证 score>={threshold:g} 的生产告警阈值；当前分数"
            f"{'已' if current_triggered else '未'}触发。"
            if production_supported and threshold is not None
            else "专属OOS存在，但当前仅达到研究验证状态，不绑定仓位。"
        ),
    }


def portfolio_overview_layer(
    *,
    layer: str,
    label: str,
    label_cn: str,
    horizon: str,
    horizon_cn: str,
    score: float | None,
    regime: str,
    regime_cn: str,
    stance: str,
    exposure_band: list[Any] | None,
    evidence: dict[str, Any],
    note: str = "",
    robust: bool | None = None,
    actionable: bool | None = None,
    validation_status: str | None = None,
) -> dict[str, Any]:
    band: list[float] | None = None
    if isinstance(exposure_band, (list, tuple)) and len(exposure_band) == 2:
        low = optional_float(exposure_band[0])
        high = optional_float(exposure_band[1])
        if low is not None and high is not None and 0.0 <= low <= high <= 100.0:
            band = [low, high]
    predictive_validity = evidence.get("predictiveValidity") if isinstance(evidence.get("predictiveValidity"), dict) else {}
    if actionable is None:
        actionable = predictive_validity.get("actionable") is True if predictive_validity else robust
    validation_status = str(
        validation_status
        or evidence.get("validationStatus")
        or predictive_validity.get("status")
        or ("validated" if robust is True else "research-validation" if robust is False else "not-assessed")
    )
    tier, context_note_cn, context_note = overview_confidence_tier(
        robust,
        actionable=actionable,
        validation_status=validation_status,
    )
    actionable_band = band if actionable is True else None
    context_band = band if actionable is not True else None
    surfaced_stance = (
        stance
        if actionable is True or band is None
        else "研究背景，仅供观察，不作为组合动作"
    )
    return {
        "layer": layer,
        "label": label,
        "labelCn": label_cn,
        "horizon": horizon,
        "horizonCn": horizon_cn,
        "score": round(score, 1) if score is not None else None,
        "regime": regime,
        "regimeCn": regime_cn,
        "stance": surfaced_stance,
        "contextStance": stance if actionable is not True and band is not None else None,
        # A portfolio band is actionable only after the validation harness has
        # passed its complete CI/FDR/fold-stability gate.  Unverified and failed
        # layers remain visible as context, but cannot silently bind the headline
        # allocation recommendation.
        "exposureBandPct": actionable_band,
        "contextBand": context_band,
        "evidence": evidence,
        "note": note,
        "robust": robust,
        "actionable": actionable is True,
        "validationStatus": validation_status,
        "predictiveValidity": predictive_validity or {
            "status": validation_status,
            "actionable": actionable is True,
        },
        "confidenceTier": tier,
        "contextNoteCn": context_note_cn,
        "contextNote": context_note,
    }


def overview_confidence_tier(
    robust: bool | None,
    *,
    actionable: bool | None = None,
    validation_status: str | None = None,
) -> tuple[str, str, str]:
    """Map a layer's OOS robustness verdict (from the signalValidation harness) to a
    presentation tier + honest context note.  The caller also uses the same verdict
    to keep non-actionable bands out of the headline recommendation."""
    if actionable is None:
        actionable = robust
    if actionable is True:
        return "validated", "", ""
    if robust is False and (
        validation_status in {None, "", "research-validation"}
        or str(validation_status).endswith("context")
    ):
        return (
            "context",
            "未通过CI、FDR与分折一致性的完整门槛—仅作背景上下文,不作前瞻信号。",
            "Did not pass the complete CI, FDR, and fold-stability gate — context only, not a forward signal.",
        )
    status = str(validation_status or "")
    if status.startswith("dedicated-oos-validated") or status.startswith("validated-own-market"):
        return (
            "validated-context",
            "已有专属样本外验证，但当前未触发已验证的生产阈值，仅作非绑定背景。",
            "Dedicated out-of-sample evidence exists, but the validated production threshold is not currently triggered.",
        )
    if status and status not in {"not-assessed", "unavailable"}:
        return (
            "research",
            "已有对应样本外研究证据，但尚未达到可绑定仓位的完整生产门槛。",
            "Relevant out-of-sample research evidence exists, but it does not pass the full production gate.",
        )
    if robust is False:
        return (
            "context",
            "未通过CI、FDR与分折一致性的完整门槛—仅作背景上下文,不作前瞻信号。",
            "Did not pass the complete CI, FDR, and fold-stability gate — context only, not a forward signal.",
        )
    return (
        "unverified",
        "未经样本外稳健性(置信区间)检验—谨慎参考。",
        "Not assessed for out-of-sample robustness — interpret with caution.",
    )


def overview_layer_robust(composite_row: dict[str, Any] | None) -> bool | None:
    """Read the complete actionable gate; legacy CI-only rows fail closed."""
    if isinstance(composite_row, dict) and "actionableRobust" in composite_row:
        return composite_row.get("actionableRobust") is True
    return None


def global_lppl_overview_state(global_lppl_risk: dict[str, Any] | None) -> dict[str, Any]:
    rows = global_lppl_risk.get("indices") if isinstance(global_lppl_risk, dict) else []
    rows = [row for row in rows if isinstance(row, dict) and row.get("available")] if isinstance(rows, list) else []
    risk_rows = [row for row in rows if str(row.get("status")) == "risk"]
    watch_rows = [row for row in rows if str(row.get("status")) == "watch"]
    if risk_rows:
        band = list(PORTFOLIO_OVERVIEW_LPPL_RISK_BAND)
        regime, regime_cn = "Risk", "泡沫风险"
        stance = "界定下行(领式/保护性认沽),不盲目追高风险指数"
    elif watch_rows:
        band = list(PORTFOLIO_OVERVIEW_LPPL_WATCH_BAND)
        regime, regime_cn = "Watch", "观察"
        stance = "维持仓位,跟踪临界窗口收敛"
    else:
        band = [100, 100]
        regime, regime_cn = "Quiet", "低风险"
        stance = "无泡沫形态约束"
    alert_symbols = [str(row.get("symbol") or "") for row in risk_rows]
    watch_symbols = [str(row.get("symbol") or "") for row in watch_rows]
    evidence_symbols = alert_symbols or watch_symbols or [
        str(row.get("symbol") or "") for row in rows
    ]
    days = [optional_float(row.get("daysToCritical")) for row in risk_rows + watch_rows]
    days = [value for value in days if value is not None]
    scores = [optional_float(row.get("score")) for row in rows]
    scores = [value for value in scores if value is not None]
    return {
        "band": band,
        "regime": regime,
        "regimeCn": regime_cn,
        "stance": stance,
        "alertSymbols": alert_symbols,
        "watchSymbols": watch_symbols,
        "evidenceSymbols": evidence_symbols,
        "minDaysToCritical": min(days) if days else None,
        "maxScore": max(scores) if scores else None,
        "observedIndexCount": len(rows),
    }


_GLOBAL_LPPL_VALIDATION_MATCH_FIELDS = (
    "symbol",
    "sourceSymbol",
    "oosAvailable",
    "oosSampleSize",
    "oosAlertDays",
    "oosTest15d",
    "replayModelAudit",
    "productionEvidenceAvailable",
    "productionActionable",
    "productionThreshold",
    "productionThresholdSource",
    "productionEffectiveWeightMultiplier",
    "productionWeightSource",
    "productionWeightMethod",
    "productionValidationRole",
)


def global_lppl_portfolio_action_qualifies(
    current_row: dict[str, Any],
    validation_row: dict[str, Any],
) -> bool:
    """Require the real LPPL replay/OOS contract before binding a broad band.

    ``productionEligible`` and ``productionActionable`` are convenient summary
    fields, not independent evidence.  This gate replays the validation role
    from the serialized OOS test, verifies independent alert episodes and the
    model fingerprint, and reconciles the canonical validation map with the
    copy attached to the live index row.
    """
    current_validation = (
        current_row.get("validation")
        if isinstance(current_row.get("validation"), dict)
        else {}
    )
    if not current_validation or not isinstance(validation_row, dict):
        return False
    if any(
        current_validation.get(field) != validation_row.get(field)
        for field in _GLOBAL_LPPL_VALIDATION_MATCH_FIELDS
    ):
        return False
    if not regional_lppl_index_qualifies_as_actionable(current_row):
        return False

    model_audit = (
        current_validation.get("replayModelAudit")
        if isinstance(current_validation.get("replayModelAudit"), dict)
        else {}
    )
    if not (
        current_row.get("modelSpecId") == GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
        and current_row.get("validationComparableToProduction") is True
        and model_audit.get("productionModelSpecId")
        == GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
        and model_audit.get("liveModelSpecId")
        == current_row.get("modelSpecId")
    ):
        return False

    oos_test = (
        current_validation.get("oosTest15d")
        if isinstance(current_validation.get("oosTest15d"), dict)
        else {}
    )
    sample_size = _nonnegative_int(oos_test.get("sampleSize"))
    alert_days = _nonnegative_int(oos_test.get("alertDays"))
    independent_sample = _nonnegative_int(oos_test.get("independentSampleSize"))
    independent_alerts = _nonnegative_int(oos_test.get("independentAlertCount"))
    threshold = optional_float(oos_test.get("threshold"))
    production_threshold = optional_float(
        current_validation.get("productionThreshold")
    )
    expected_multiplier, expected_role, _role_cn = global_lppl_validation_weight(
        oos_test
    )
    observed_multiplier = optional_float(
        current_validation.get("productionEffectiveWeightMultiplier")
    )
    return bool(
        current_validation.get("oosAvailable") is True
        and sample_size >= GLOBAL_LPPL_OOS_MIN_EVALUATION_OBSERVATIONS
        and current_validation.get("oosSampleSize") == sample_size
        and current_validation.get("oosAlertDays") == alert_days
        and independent_sample
        >= GLOBAL_LPPL_OOS_MIN_INDEPENDENT_BASE_OBSERVATIONS
        and independent_alerts >= GLOBAL_LPPL_OOS_MIN_INDEPENDENT_ALERTS
        and threshold is not None
        and production_threshold is not None
        and threshold == production_threshold
        and current_validation.get("oosThreshold") == production_threshold
        and current_validation.get("productionThresholdSource")
        == "purged_calibration_first_65pct"
        and current_validation.get("productionWeightSource")
        == "untouched_oos_last_35pct"
        and current_validation.get("productionWeightMethod")
        == "non_overlapping_alerts_wilson90_exact_binomial_bonferroni6"
        and expected_role == "validated"
        and expected_multiplier >= 0.999
        and current_validation.get("productionValidationRole") == expected_role
        and observed_multiplier is not None
        and observed_multiplier == expected_multiplier
    )


def global_lppl_overview_evidence(global_lppl_risk: dict[str, Any] | None) -> dict[str, Any]:
    """Attach each active index's own-market OOS row.

    A SPY audit describes SPY only.  In particular, it cannot be reused as the
    predictive evidence for KOSPI or TWII merely because all three appear in a
    global monitor.  Non-US evidence remains useful for regional risk context,
    but does not bind a broad/global equity allocation band.
    """
    panel = global_lppl_risk if isinstance(global_lppl_risk, dict) else {}
    index_rows = [
        row
        for row in panel.get("indices", [])
        if isinstance(row, dict) and row.get("available") is True
    ]
    risk_rows = [row for row in index_rows if str(row.get("status") or "") == "risk"]
    watch_rows = [row for row in index_rows if str(row.get("status") or "") == "watch"]
    targets = risk_rows or watch_rows or index_rows
    target_symbols = [str(row.get("symbol") or "").upper() for row in targets]

    validation = panel.get("indexValidation") if isinstance(panel.get("indexValidation"), dict) else {}
    validation_rows = [row for row in validation.get("rows", []) if isinstance(row, dict)]
    validation_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in validation_rows
        if str(row.get("symbol") or "").strip()
    }
    per_index: list[dict[str, Any]] = []
    missing_symbols: list[str] = []
    current_by_symbol = {
        str(row.get("symbol") or "").upper(): row for row in targets
    }
    for symbol in target_symbols:
        row = validation_by_symbol.get(symbol)
        if not isinstance(row, dict) or row.get("oosAvailable") is not True:
            missing_symbols.append(symbol)
            per_index.append(
                {
                    "symbol": symbol,
                    "available": False,
                    "validationStatus": "not-assessed-own-market",
                    "actionable": False,
                    "note": f"{symbol}尚无自身市场OOS证据。",
                }
            )
            continue
        current_row = current_by_symbol.get(symbol, {})
        hit = _percent_rate(row.get("precision15dOos"))
        base = _percent_rate(row.get("baseRate15dOos"))
        role = str(
            row.get("productionValidationRole")
            or row.get("oosValidationRole")
            or row.get("validationRole")
            or "unvalidated"
        )
        multiplier = optional_float(
            row.get("productionEffectiveWeightMultiplier")
            if row.get("productionEffectiveWeightMultiplier") is not None
            else row.get("effectiveWeightMultiplier")
        )
        threshold = optional_float(row.get("productionThreshold"))
        current_score = optional_float(current_row.get("score"))
        production_evidence = row.get("productionEvidenceAvailable") is True
        production_eligible = current_row.get("productionEligible") is True
        threshold_validated = global_lppl_portfolio_action_qualifies(
            current_row,
            row,
        )
        current_triggered = bool(
            threshold_validated
            and current_score is not None
            and current_score >= threshold
        )
        per_index.append(
            {
                "symbol": symbol,
                "sourceSymbol": str(row.get("sourceSymbol") or current_row.get("sourceSymbol") or symbol),
                "available": True,
                "scope": "own-market",
                "oosHitRate": round(hit, 3) if hit is not None else None,
                "baseRate": round(base, 3) if base is not None else None,
                "lift": round(hit / base, 2) if hit is not None and base else None,
                "leadTimeDays": optional_float(row.get("avgDrawdownLeadDaysWhenHit")),
                "sampleSize": _nonnegative_int(row.get("oosSampleSize")),
                "oosAlertCount": _nonnegative_int(row.get("oosAlertDays")),
                "independentAlertCount": _nonnegative_int(
                    (row.get("oosTest15d") or {}).get("independentAlertCount")
                    if isinstance(row.get("oosTest15d"), dict)
                    else None
                ),
                "productionThreshold": threshold,
                "productionEvidenceAvailable": production_evidence,
                "productionEligible": production_eligible,
                "validationRole": role,
                "effectiveWeightMultiplier": multiplier,
                "currentScore": current_score,
                "currentStatus": str(current_row.get("status") or ""),
                "thresholdValidated": threshold_validated,
                "currentTriggered": current_triggered,
                "actionable": current_triggered,
                "validationStatus": f"{role}-own-market",
                "note": f"{symbol}仅由{symbol}/{str(row.get('sourceSymbol') or symbol)}自身市场15D OOS支持。",
            }
        )

    available_rows = [row for row in per_index if row.get("available") is True]
    if not targets or not available_rows:
        return {
            "available": False,
            "scope": "per-index-own-market",
            "symbols": target_symbols,
            "perIndex": per_index,
            "missingSymbols": missing_symbols,
            "validationStatus": "not-assessed-own-market",
            "predictiveValidity": {
                "status": "not-assessed-own-market",
                "actionable": False,
                "validationType": "per-index-own-market-15d-oos",
            },
            "note": "证据不足: 当前LPPL目标指数没有同市场OOS验证。",
        }

    all_threshold_validated = not missing_symbols and all(
        row.get("thresholdValidated") is True for row in available_rows
    )
    all_current_triggered = all_threshold_validated and all(
        row.get("currentTriggered") is True for row in available_rows
    )
    us_broad_scope = bool(target_symbols) and all(symbol in {"SPY", "QQQ"} for symbol in target_symbols)
    broad_actionable = bool(us_broad_scope and all_current_triggered)
    roles = {str(row.get("validationRole") or "unvalidated") for row in available_rows}
    if all_threshold_validated:
        status = (
            "validated-own-market"
            if broad_actionable
            else "validated-own-market-inactive"
            if us_broad_scope
            else "validated-own-market-regional-context"
        )
    elif "validated" in roles or "mixed" in roles:
        status = "mixed-own-market"
    else:
        status = "weak-own-market"
    only_row = available_rows[0] if len(available_rows) == 1 else None
    return {
        "available": True,
        "scope": "per-index-own-market",
        "symbols": target_symbols,
        "perIndex": per_index,
        "missingSymbols": missing_symbols,
        # Compatibility fields remain useful for a single active index; for a
        # multi-index alert, consumers must inspect ``perIndex`` rather than
        # reading one market's metric as if it represented the whole cluster.
        "oosHitRate": only_row.get("oosHitRate") if only_row else None,
        "baseRate": only_row.get("baseRate") if only_row else None,
        "lift": only_row.get("lift") if only_row else None,
        "leadTimeDays": only_row.get("leadTimeDays") if only_row else None,
        "sampleSize": only_row.get("sampleSize") if only_row else None,
        "classification": "",
        "validationStatus": status,
        "predictiveValidity": {
            "status": status,
            "actionable": broad_actionable,
            "thresholdValidated": all_threshold_validated,
            "currentTriggered": all_current_triggered,
            "portfolioScopeMatched": us_broad_scope,
            "validationType": "per-index-own-market-15d-oos",
            "independentHoldout": False,
        },
        "note": (
            "逐指数使用各自市场15D OOS证据; 非美股告警仅作地区风险背景,不约束全局权益仓位。"
            if not us_broad_scope
            else "逐指数使用各自市场15D OOS证据; 只有已验证阈值在当前触发时才约束仓位。"
        ),
    }


def portfolio_overview_us_internal_tilt(regional_monitor: dict[str, Any] | None) -> dict[str, Any]:
    """Surface the US-internal broad(SPY)-vs-tech(QQQ) tilt in the headline overview, so the
    US equity band is paired with a within-US sleeve lean."""
    if not isinstance(regional_monitor, dict) or not regional_monitor.get("available"):
        return {"available": False}
    regions = regional_monitor.get("regions", []) if isinstance(regional_monitor.get("regions"), list) else []
    us = next((r for r in regions if isinstance(r, dict) and r.get("key") == "us"), None)
    internal = us.get("internalRotation") if isinstance(us, dict) and isinstance(us.get("internalRotation"), dict) else {}
    if not internal.get("available"):
        return {"available": False}
    actionable = internal.get("actionable") is True
    return {
        "available": True,
        "actionable": actionable,
        "tilt": internal.get("tilt") if actionable else "balanced",
        "tiltCn": internal.get("tiltCn") if actionable else "无生产级内部倾斜",
        "contextTilt": internal.get("contextTilt") or internal.get("tilt"),
        "contextTiltCn": internal.get("contextTiltCn") or internal.get("tiltCn"),
        "rationale": internal.get("rationale"),
    }


def _regional_factor_alert_actionable(region: dict[str, Any]) -> bool:
    """Match a displayed breach to the exact factor/composite production gate."""
    return bool(
        regional_allocation_qualifies_as_actionable(region)
        and regional_factor_alert_qualifies_as_actionable(region)
    )


def portfolio_overview_regional_tilt(regional_monitor: dict[str, Any] | None) -> dict[str, Any]:
    """Surface the global regional rotation + active validated-factor breaches as a separate
    dimension in the headline overview (distinct axis from the US equity exposure band)."""
    if not isinstance(regional_monitor, dict) or not regional_monitor.get("available"):
        return {"available": False}
    rotation = regional_monitor.get("rotation", {}) if isinstance(regional_monitor.get("rotation"), dict) else {}
    regions = regional_monitor.get("regions", []) if isinstance(regional_monitor.get("regions"), list) else []
    name_by_key = {str(r.get("key")): str(r.get("nameCn") or r.get("name") or r.get("key")) for r in regions if isinstance(r, dict)}
    actionable_by_key = {
        str(region.get("key") or ""): region["allocation"]
        for region in regions
        if isinstance(region, dict)
        and isinstance(region.get("allocation"), dict)
        and regional_allocation_qualifies_as_actionable(region)
    }
    actionable_keys = set(actionable_by_key)
    all_breached = [
        {"key": str(r.get("key")), "nameCn": name_by_key.get(str(r.get("key")), str(r.get("key"))),
         "factorLabelCn": str(r["factorAlert"].get("factorLabelCn") or ""),
         "source": str(r["factorAlert"].get("source") or "factor"),
         "current": r["factorAlert"].get("current"), "threshold": r["factorAlert"].get("threshold"),
         "trackRecord": str(r["factorAlert"].get("trackRecord") or ""),
         "actionable": _regional_factor_alert_actionable(r)}
        for r in regions
        if isinstance(r, dict) and isinstance(r.get("factorAlert"), dict)
        and r["factorAlert"].get("available") and r["factorAlert"].get("state") == "breached"
    ]
    breached = [row for row in all_breached if row["actionable"]]
    context_breached = [row for row in all_breached if not row["actionable"]]
    composite_breaches = [b for b in breached if b["source"] == "composite"]
    declared_favor = _string_list(rotation.get("favorRegions"))
    declared_reduce = _string_list(rotation.get("reduceRegions"))
    favor_keys = [
        key
        for key in declared_favor
        if key in actionable_keys and actionable_by_key[key].get("stance") == "overweight"
    ]
    reduce_keys = [
        key
        for key in declared_reduce
        if key in actionable_keys and actionable_by_key[key].get("stance") == "underweight"
    ]
    context_favor_keys = [
        str(key)
        for key in [*_string_list(rotation.get("contextFavorRegions")), *declared_favor]
        if str(key) not in actionable_keys
    ]
    context_reduce_keys = [
        str(key)
        for key in [*_string_list(rotation.get("contextReduceRegions")), *declared_reduce]
        if str(key) not in actionable_keys
    ]
    favor = [name_by_key.get(key, key) for key in dict.fromkeys(favor_keys)]
    reduce_regions = [name_by_key.get(key, key) for key in dict.fromkeys(reduce_keys)]
    context_favor = [name_by_key.get(key, key) for key in dict.fromkeys(context_favor_keys)]
    context_reduce = [name_by_key.get(key, key) for key in dict.fromkeys(context_reduce_keys)]
    parts: list[str] = []
    if favor:
        parts.append("增持 " + "、".join(favor))
    if reduce_regions:
        parts.append("减持 " + "、".join(reduce_regions))
    if not parts:
        parts.append("各地区维持中性")
    if breached:
        parts.append(f"{len(breached)}个地区信号突破验证阈值(" + "、".join(b["nameCn"] for b in breached) + ")")
    if composite_breaches:
        parts.append(f"其中{len(composite_breaches)}个由已验证综合信号驱动(" + "、".join(b["nameCn"] for b in composite_breaches) + ")")
    context_parts: list[str] = []
    if context_favor:
        context_parts.append("研究层偏多 " + "、".join(context_favor))
    if context_reduce:
        context_parts.append("研究层偏空 " + "、".join(context_reduce))
    if context_breached:
        context_parts.append("研究层阈值突破 " + "、".join(row["nameCn"] for row in context_breached))
    if context_parts:
        parts.append("; ".join(context_parts) + "，不进入组合动作")
    return {
        "available": True,
        "actionable": bool(favor or reduce_regions or breached),
        "horizon": "1-3M",
        "horizonCn": "1-3个月(地区轮动)",
        "favorRegions": list(dict.fromkeys(favor_keys)),
        "reduceRegions": list(dict.fromkeys(reduce_keys)),
        "contextFavorRegions": list(dict.fromkeys(context_favor_keys)),
        "contextReduceRegions": list(dict.fromkeys(context_reduce_keys)),
        "breachedRegions": breached,
        "contextBreachedRegions": context_breached,
        "compositeBreachCount": len(composite_breaches),
        "summary": "; ".join(parts) + "。",
    }


def build_portfolio_overview(
    *,
    spy_early_warning: dict[str, Any] | None,
    equity_short_term_risk: dict[str, Any] | None,
    global_lppl_risk: dict[str, Any] | None,
    macro_liquidity: dict[str, Any] | None,
    signal_validation: dict[str, Any] | None,
    regional_monitor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(signal_validation, dict) and signal_validation.get("available"):
        evidence_by_id = {
            str(row.get("id")): row
            for row in signal_validation.get("composites", [])
            if isinstance(row, dict)
        }

    rows: list[dict[str, Any]] = []

    est = equity_short_term_risk if isinstance(equity_short_term_risk, dict) else {}
    est_alloc = est.get("allocation") if isinstance(est.get("allocation"), dict) else {}
    est_context_alloc = (
        est.get("contextAllocation")
        if isinstance(est.get("contextAllocation"), dict)
        else {}
    )
    est_score = optional_float(est.get("score"))
    if est_score is not None:
        est_backtest = est.get("backtest") if isinstance(est.get("backtest"), dict) else {}
        has_dedicated_contract = isinstance(est_backtest.get("walkForward"), dict)
        if has_dedicated_contract:
            est_evidence = equity_short_term_overview_evidence(est)
            est_predictive = (
                est_evidence.get("predictiveValidity")
                if isinstance(est_evidence.get("predictiveValidity"), dict)
                else {}
            )
            est_robust = (
                est_predictive.get("thresholdValidated") is True
                if est_evidence.get("available") is True
                else None
            )
            est_actionable = est_predictive.get("actionable") is True
        else:
            # Historical exports can still expose the generic 91-day audit as
            # context, but it is not the equity model's production contract.
            est_composite = evidence_by_id.get("equityShortTermRisk")
            est_evidence = portfolio_overview_evidence(est_composite)
            est_robust = overview_layer_robust(est_composite)
            est_actionable = False
            est_evidence["validationStatus"] = "legacy-generic-context"
            est_evidence["predictiveValidity"] = {
                "status": "legacy-generic-context",
                "actionable": False,
                "validationType": "generic-weekly-not-equity-production",
                "independentHoldout": False,
            }
        est_display_alloc = est_alloc if est_actionable else (est_context_alloc or est_alloc)
        rows.append(
            portfolio_overview_layer(
                layer="equityShortTermRisk",
                label="Equity Short-Term Risk",
                label_cn="短周期股票风险",
                horizon=str(est_display_alloc.get("horizon") or "1-10d"),
                horizon_cn=str(est_display_alloc.get("horizonCn") or "1-10个交易日"),
                score=est_score,
                regime=str(est_display_alloc.get("regime") or ""),
                regime_cn=str(est_display_alloc.get("regimeCn") or ""),
                stance=str(est_display_alloc.get("hedgeAction") or est_display_alloc.get("stance") or ""),
                exposure_band=est_display_alloc.get("exposureBandPct"),
                evidence=est_evidence,
                robust=est_robust,
                actionable=est_actionable,
                validation_status=str(est_evidence.get("validationStatus") or "not-assessed"),
            )
        )

    sew = spy_early_warning if isinstance(spy_early_warning, dict) else {}
    sew_alloc = sew.get("allocation") if isinstance(sew.get("allocation"), dict) else {}
    sew_context_alloc = (
        sew.get("contextAllocation")
        if isinstance(sew.get("contextAllocation"), dict)
        else {}
    )
    sew_score = optional_float(sew.get("score"))
    if sew_score is not None:
        sew_evidence = portfolio_overview_evidence(evidence_by_id.get("spyEarlyWarning"))
        sew_validity = sew.get("predictiveValidity") if isinstance(sew.get("predictiveValidity"), dict) else {}
        sew_actionable = bool(
            sew_evidence.get("available") is True
            and overview_layer_robust(evidence_by_id.get("spyEarlyWarning")) is True
            and sew_validity.get("actionable") is True
            and sew.get("aggregateActionableRobust") is True
            and sew_alloc.get("actionable") is True
        )
        sew_status = str(sew_validity.get("status") or "not-assessed-production-contract")
        sew_evidence["validationStatus"] = sew_status
        sew_evidence["predictiveValidity"] = {
            **sew_validity,
            "status": sew_status,
            "actionable": sew_actionable,
            "validationType": "generic-weekly-plus-independent-holdout",
        }
        sew_display_alloc = sew_alloc if sew_actionable else (sew_context_alloc or sew_alloc)
        rows.append(
            portfolio_overview_layer(
                layer="spyEarlyWarning",
                label="SPY Early Warning",
                label_cn="SPY宏观预警",
                horizon=str(sew_display_alloc.get("horizon") or "1-3M"),
                horizon_cn=str(sew_display_alloc.get("horizonCn") or "1-3个月"),
                score=sew_score,
                regime=str(sew.get("regime") or ""),
                regime_cn=str(sew.get("regimeCn") or ""),
                stance=str(sew_display_alloc.get("hedgeAction") or sew_display_alloc.get("stance") or ""),
                exposure_band=sew_display_alloc.get("exposureBandPct"),
                evidence=sew_evidence,
                robust=overview_layer_robust(evidence_by_id.get("spyEarlyWarning")),
                actionable=sew_actionable,
                validation_status=sew_status,
            )
        )

    lppl_state = global_lppl_overview_state(global_lppl_risk)
    if lppl_state["observedIndexCount"] > 0:
        lppl_evidence = global_lppl_overview_evidence(global_lppl_risk)
        lppl_predictive = (
            lppl_evidence.get("predictiveValidity")
            if isinstance(lppl_evidence.get("predictiveValidity"), dict)
            else {}
        )
        lppl_robust = (
            lppl_predictive.get("thresholdValidated") is True
            if lppl_evidence.get("available") is True
            else None
        )
        lppl_actionable = lppl_predictive.get("actionable") is True
        lppl_note = ""
        if lppl_state["alertSymbols"]:
            lppl_note = "告警指数: " + ", ".join(lppl_state["alertSymbols"])
            if lppl_state["minDaysToCritical"] is not None:
                lppl_note += f"; 最近临界窗口≈{lppl_state['minDaysToCritical']:.0f}天"
        rows.append(
            portfolio_overview_layer(
                layer="globalLppl",
                label="Global LPPL Bubble Monitor",
                label_cn="全球LPPL泡沫监测",
                horizon="tc-window",
                horizon_cn="临界窗口",
                score=lppl_state["maxScore"],
                regime=lppl_state["regime"],
                regime_cn=lppl_state["regimeCn"],
                stance=lppl_state["stance"],
                exposure_band=lppl_state["band"],
                evidence=lppl_evidence,
                note=lppl_note,
                robust=lppl_robust,
                actionable=lppl_actionable,
                validation_status=str(lppl_evidence.get("validationStatus") or "not-assessed"),
            )
        )

    macro = macro_liquidity if isinstance(macro_liquidity, dict) else {}
    macro_score = bhadial_usable_reliability_score(macro)
    if macro:
        macro_regime = macro_reliability_regime(macro_score)
        macro_robust = overview_layer_robust(evidence_by_id.get("bhadialComposite"))
        macro_validation_status = (
            "validated-context"
            if macro_robust is True
            else "research-context"
            if macro_robust is False
            else "not-assessed"
        )
        rows.append(
            portfolio_overview_layer(
                layer="bhadialComposite",
                label="Macro Conditions (nowcast)",
                label_cn="宏观环境评分",
                horizon="3-6M",
                horizon_cn="3-6个月",
                score=macro_score,
                regime=macro_regime,
                regime_cn=macro_regime,
                stance=(
                    "背景层: 影响久期/曲线观点,不直接给权益仓位"
                    if macro_score is not None
                    else "当前覆盖不足: 不把收缩到50的未知值当作中性环境"
                ),
                exposure_band=None,
                evidence=portfolio_overview_evidence(evidence_by_id.get("bhadialComposite")),
                note=(
                    "当前可靠性覆盖未达到至少25%有效权重且5个可评分因子的门槛。"
                    if macro_score is None
                    else ""
                ),
                robust=macro_robust,
                actionable=False,
                validation_status=macro_validation_status,
            )
        )

    scored_rows = [row for row in rows if row.get("score") is not None]
    if len(scored_rows) < 2:
        return {
            "available": False,
            "summary": "组合总览需要至少两层可用信号。",
            "layers": rows,
            "conflicts": [],
            "suggestedEquityExposureBand": None,
            "contextBand": conservative_band(
                [row["contextBand"] for row in rows if row.get("contextBand")]
            ),
        }

    bands = [
        row["exposureBandPct"]
        for row in rows
        if row.get("actionable") is True and row.get("exposureBandPct")
    ]
    context_band = conservative_band([row["contextBand"] for row in rows if row.get("contextBand")])
    suggested_band = conservative_band(bands)
    binding_layer = None
    binding_basis = None
    if suggested_band:
        high = suggested_band[1]
        for row in rows:
            band = row.get("exposureBandPct")
            if row.get("actionable") is True and band and band[1] == high:
                binding_layer = str(row.get("labelCn") or row.get("layer"))
                binding_basis = str(row.get("confidenceTier") or "")
                break

    # Display order: currently actionable layers lead; validated-but-inactive,
    # research, and unverified context follow in original order.
    rows.sort(key=lambda row: 0 if row.get("actionable") is True else 1)

    layer_by_id = {str(row.get("layer") or ""): row for row in rows}
    conflicts: list[dict[str, Any]] = []
    lppl_alerting = bool(lppl_state["alertSymbols"]) if lppl_state["observedIndexCount"] > 0 else False
    sew_is_actionable = layer_by_id.get("spyEarlyWarning", {}).get("actionable") is True
    est_is_actionable = layer_by_id.get("equityShortTermRisk", {}).get("actionable") is True
    lppl_is_actionable = layer_by_id.get("globalLppl", {}).get("actionable") is True
    if sew_score is not None and est_score is not None and sew_is_actionable and est_is_actionable:
        if sew_score < 60 and est_score >= 75:
            conflicts.append(
                {
                    "layers": ["spyEarlyWarning", "equityShortTermRisk"],
                    "actionable": True,
                    "description": f"宏观预警温和({sew_score:.0f})但短周期强告警({est_score:.0f})",
                    "resolution": "维持核心仓位,但为未来1-2周加战术性保护(对冲或减高Beta),不必战略性减仓。",
                }
            )
        if sew_score >= 60 and est_score < 40:
            conflicts.append(
                {
                    "layers": ["spyEarlyWarning", "equityShortTermRisk"],
                    "actionable": True,
                    "description": f"宏观预警偏高({sew_score:.0f})但短周期无压力({est_score:.0f})",
                    "resolution": "利用市场平静期分批降低风险敞口,而非等待回撤后被动卖出。",
                }
            )
    if lppl_alerting and lppl_is_actionable and sew_is_actionable and sew_score is not None and sew_score < 40:
        conflicts.append(
            {
                "layers": ["globalLppl", "spyEarlyWarning"],
                "actionable": True,
                "description": "泡沫形态告警与建设性宏观并存",
                "resolution": "保留上行参与,用期权界定下行(领式或保护性认沽),避免直接清仓错过泡沫后段。",
            }
        )

    if suggested_band:
        band_text = f"建议权益仓位区间{suggested_band[0]:.0f}-{suggested_band[1]:.0f}%(常规仓位=100%)"
        if binding_layer:
            band_text += f", 当前约束层: {binding_layer}"
    else:
        band_text = "暂无可合成的仓位区间"
    conflict_text = f"; 检测到{len(conflicts)}个可动作层冲突,见冲突说明" if conflicts else "; 可动作层之间无显著冲突"
    return {
        "available": True,
        "asOf": str(sew.get("asOf") or est.get("asOf") or ""),
        "method": (
            "Combines only currently triggered, production-validated, portfolio-scope-matched layers into "
            "the suggested band (element-wise minimum). Evidence follows each model's native contract: "
            "dedicated equity 15-session walk-forward, generic weekly macro validation, or per-index "
            "own-market LPPL OOS. Inactive, failed, or scope-mismatched layers remain in contextBand."
        ),
        "summary": band_text + conflict_text + "。可用命中率均来自各层自身OOS路径,并与同市场无条件基准率对照。",
        "layers": rows,
        "conflicts": conflicts,
        "suggestedEquityExposureBand": suggested_band,
        "contextBand": context_band,
        "bindingLayer": binding_layer,
        "bindingBasis": binding_basis,
        "regionalTilt": portfolio_overview_regional_tilt(regional_monitor),
        "usInternalTilt": portfolio_overview_us_internal_tilt(regional_monitor),
    }


def conservative_band(bands: list[list[Any]]) -> list[float] | None:
    """Combine comparable bands without granting them an actionability verdict."""
    valid: list[tuple[float, float]] = []
    for band in bands:
        if not isinstance(band, (list, tuple)) or len(band) != 2:
            continue
        low = optional_float(band[0])
        high = optional_float(band[1])
        if low is None or high is None:
            continue
        valid.append((low, high))
    if not valid:
        return None
    low = min(item[0] for item in valid)
    high = min(item[1] for item in valid)
    return [round(max(0.0, low), 0), round(max(low, min(high, 110.0)), 0)]
