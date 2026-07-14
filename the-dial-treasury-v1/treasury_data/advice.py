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


PORTFOLIO_OVERVIEW_LPPL_RISK_BAND = [60, 85]
PORTFOLIO_OVERVIEW_LPPL_WATCH_BAND = [85, 100]


def portfolio_overview_evidence(row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"available": False, "note": "证据不足: 该层尚无走出样本验证。"}
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
) -> dict[str, Any]:
    band: list[float] | None = None
    if isinstance(exposure_band, (list, tuple)) and len(exposure_band) == 2:
        low = optional_float(exposure_band[0])
        high = optional_float(exposure_band[1])
        if low is not None and high is not None:
            band = [low, high]
    tier, context_note_cn, context_note = overview_confidence_tier(robust)
    actionable_band = band if robust is True else None
    context_band = band if robust is not True else None
    return {
        "layer": layer,
        "label": label,
        "labelCn": label_cn,
        "horizon": horizon,
        "horizonCn": horizon_cn,
        "score": round(score, 1) if score is not None else None,
        "regime": regime,
        "regimeCn": regime_cn,
        "stance": stance,
        # A portfolio band is actionable only after the validation harness has
        # passed its complete CI/FDR/fold-stability gate.  Unverified and failed
        # layers remain visible as context, but cannot silently bind the headline
        # allocation recommendation.
        "exposureBandPct": actionable_band,
        "contextBand": context_band,
        "evidence": evidence,
        "note": note,
        "robust": robust,
        "confidenceTier": tier,
        "contextNoteCn": context_note_cn,
        "contextNote": context_note,
    }


def overview_confidence_tier(robust: bool | None) -> tuple[str, str, str]:
    """Map a layer's OOS robustness verdict (from the signalValidation harness) to a
    presentation tier + honest context note.  The caller also uses the same verdict
    to keep non-actionable bands out of the headline recommendation."""
    if robust is True:
        return "validated", "", ""
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
        "minDaysToCritical": min(days) if days else None,
        "maxScore": max(scores) if scores else None,
        "observedIndexCount": len(rows),
    }


def global_lppl_overview_evidence(global_lppl_risk: dict[str, Any] | None) -> dict[str, Any]:
    validation = global_lppl_risk.get("indexValidation") if isinstance(global_lppl_risk, dict) else {}
    rows = validation.get("rows") if isinstance(validation, dict) else []
    spy_row = next((row for row in rows if isinstance(row, dict) and str(row.get("symbol")) == "SPY"), None)
    if not isinstance(spy_row, dict) or not spy_row.get("oosAvailable"):
        return {"available": False, "note": "证据不足: LPPL单指数OOS验证不可用。"}
    hit = optional_float(spy_row.get("precision15dOos"))
    base = optional_float(spy_row.get("baseRate15dOos"))
    hit = hit / 100 if hit is not None else None
    base = base / 100 if base is not None else None
    return {
        "available": True,
        "oosHitRate": round(hit, 3) if hit is not None else None,
        "baseRate": round(base, 3) if base is not None else None,
        "lift": round(hit / base, 2) if hit is not None and base else None,
        "leadTimeDays": optional_float(spy_row.get("avgDrawdownLeadDaysWhenHit")),
        "sampleSize": spy_row.get("oosSampleSize"),
        "classification": "",
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
    return {
        "available": True,
        "tilt": internal.get("tilt"),
        "tiltCn": internal.get("tiltCn"),
        "rationale": internal.get("rationale"),
    }


def portfolio_overview_regional_tilt(regional_monitor: dict[str, Any] | None) -> dict[str, Any]:
    """Surface the global regional rotation + active validated-factor breaches as a separate
    dimension in the headline overview (distinct axis from the US equity exposure band)."""
    if not isinstance(regional_monitor, dict) or not regional_monitor.get("available"):
        return {"available": False}
    rotation = regional_monitor.get("rotation", {}) if isinstance(regional_monitor.get("rotation"), dict) else {}
    regions = regional_monitor.get("regions", []) if isinstance(regional_monitor.get("regions"), list) else []
    name_by_key = {str(r.get("key")): str(r.get("nameCn") or r.get("name") or r.get("key")) for r in regions if isinstance(r, dict)}
    breached = [
        {"key": str(r.get("key")), "nameCn": name_by_key.get(str(r.get("key")), str(r.get("key"))),
         "factorLabelCn": str(r["factorAlert"].get("factorLabelCn") or ""),
         "source": str(r["factorAlert"].get("source") or "factor"),
         "current": r["factorAlert"].get("current"), "threshold": r["factorAlert"].get("threshold"),
         "trackRecord": str(r["factorAlert"].get("trackRecord") or "")}
        for r in regions
        if isinstance(r, dict) and isinstance(r.get("factorAlert"), dict)
        and r["factorAlert"].get("available") and r["factorAlert"].get("state") == "breached"
    ]
    composite_breaches = [b for b in breached if b["source"] == "composite"]
    favor = [name_by_key.get(k, k) for k in rotation.get("favorRegions", [])]
    reduce_regions = [name_by_key.get(k, k) for k in rotation.get("reduceRegions", [])]
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
    return {
        "available": True,
        "horizon": "1-3M",
        "horizonCn": "1-3个月(地区轮动)",
        "favorRegions": rotation.get("favorRegions", []),
        "reduceRegions": rotation.get("reduceRegions", []),
        "breachedRegions": breached,
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
    est_score = optional_float(est.get("score"))
    if est_score is not None:
        rows.append(
            portfolio_overview_layer(
                layer="equityShortTermRisk",
                label="Equity Short-Term Risk",
                label_cn="短周期股票风险",
                horizon=str(est_alloc.get("horizon") or "1-10d"),
                horizon_cn=str(est_alloc.get("horizonCn") or "1-10个交易日"),
                score=est_score,
                regime=str(est_alloc.get("regime") or ""),
                regime_cn=str(est_alloc.get("regimeCn") or ""),
                stance=str(est_alloc.get("hedgeAction") or est_alloc.get("stance") or ""),
                exposure_band=est_alloc.get("exposureBandPct"),
                evidence=portfolio_overview_evidence(evidence_by_id.get("equityShortTermRisk")),
                robust=overview_layer_robust(evidence_by_id.get("equityShortTermRisk")),
            )
        )

    sew = spy_early_warning if isinstance(spy_early_warning, dict) else {}
    sew_alloc = sew.get("allocation") if isinstance(sew.get("allocation"), dict) else {}
    sew_score = optional_float(sew.get("score"))
    if sew_score is not None:
        rows.append(
            portfolio_overview_layer(
                layer="spyEarlyWarning",
                label="SPY Early Warning",
                label_cn="SPY宏观预警",
                horizon=str(sew_alloc.get("horizon") or "1-3M"),
                horizon_cn=str(sew_alloc.get("horizonCn") or "1-3个月"),
                score=sew_score,
                regime=str(sew.get("regime") or ""),
                regime_cn=str(sew.get("regimeCn") or ""),
                stance=str(sew_alloc.get("hedgeAction") or sew_alloc.get("stance") or ""),
                exposure_band=sew_alloc.get("exposureBandPct"),
                evidence=portfolio_overview_evidence(evidence_by_id.get("spyEarlyWarning")),
                robust=overview_layer_robust(evidence_by_id.get("spyEarlyWarning")),
            )
        )

    lppl_state = global_lppl_overview_state(global_lppl_risk)
    if lppl_state["observedIndexCount"] > 0:
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
                evidence=global_lppl_overview_evidence(global_lppl_risk),
                note=lppl_note,
                robust=None,
            )
        )

    macro = macro_liquidity if isinstance(macro_liquidity, dict) else {}
    macro_score = optional_float(macro.get("score"))
    if macro_score is not None:
        rows.append(
            portfolio_overview_layer(
                layer="bhadialComposite",
                label="Macro Conditions (nowcast)",
                label_cn="宏观环境评分",
                horizon="3-6M",
                horizon_cn="3-6个月",
                score=macro_score,
                regime=str(macro.get("regime") or ""),
                regime_cn=str(macro.get("regimeCn") or macro.get("regime") or ""),
                stance="背景层: 影响久期/曲线观点,不直接给权益仓位",
                exposure_band=None,
                evidence=portfolio_overview_evidence(evidence_by_id.get("bhadialComposite")),
                robust=overview_layer_robust(evidence_by_id.get("bhadialComposite")),
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

    bands = [row["exposureBandPct"] for row in rows if row.get("robust") is True and row.get("exposureBandPct")]
    context_band = conservative_band([row["contextBand"] for row in rows if row.get("contextBand")])
    suggested_band = conservative_band(bands)
    binding_layer = None
    binding_basis = None
    if suggested_band:
        high = suggested_band[1]
        for row in rows:
            band = row.get("exposureBandPct")
            if row.get("robust") is True and band and band[1] == high:
                binding_layer = str(row.get("labelCn") or row.get("layer"))
                binding_basis = str(row.get("confidenceTier") or "")
                break

    # Display order: OOS-robust (validated) layers lead; context/unverified follow,
    # preserving original order within each tier.
    rows.sort(key=lambda row: 0 if row.get("robust") is True else 1)

    conflicts: list[dict[str, Any]] = []
    lppl_alerting = bool(lppl_state["alertSymbols"]) if lppl_state["observedIndexCount"] > 0 else False
    if sew_score is not None and est_score is not None:
        if sew_score < 60 and est_score >= 75:
            conflicts.append(
                {
                    "layers": ["spyEarlyWarning", "equityShortTermRisk"],
                    "description": f"宏观预警温和({sew_score:.0f})但短周期强告警({est_score:.0f})",
                    "resolution": "维持核心仓位,但为未来1-2周加战术性保护(对冲或减高Beta),不必战略性减仓。",
                }
            )
        if sew_score >= 60 and est_score < 40:
            conflicts.append(
                {
                    "layers": ["spyEarlyWarning", "equityShortTermRisk"],
                    "description": f"宏观预警偏高({sew_score:.0f})但短周期无压力({est_score:.0f})",
                    "resolution": "利用市场平静期分批降低风险敞口,而非等待回撤后被动卖出。",
                }
            )
    if lppl_alerting and sew_score is not None and sew_score < 40:
        conflicts.append(
            {
                "layers": ["globalLppl", "spyEarlyWarning"],
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
    conflict_text = f"; 检测到{len(conflicts)}个跨层冲突,见冲突说明" if conflicts else "; 三个时间层无显著冲突"
    return {
        "available": True,
        "asOf": str(sew.get("asOf") or est.get("asOf") or ""),
        "method": (
            "Combines only complete-gate actionable layers into the suggested band (element-wise minimum). "
            "Failed or unverified 1-10d tactical, 1-3M macro-warning, and LPPL tc-window bands remain in "
            "contextBand and cannot bind allocation. Evidence comes from the weekly walk-forward validation harness."
        ),
        "summary": band_text + conflict_text + "。每层命中率均为走出样本(OOS)统计,与无条件基准率对照。",
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
