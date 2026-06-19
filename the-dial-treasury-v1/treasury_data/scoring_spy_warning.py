"""SPY Early-Warning domain extracted from build_dashboard.py (behavior-unchanged,
2026-06-19 全面重构 Phase 1). Equity-specific 0-100 warning index: sleeves, amplifiers/dampeners,
allocation, backtest/audit. Depends on lower layers + scoring_bhadial (consumes Conditions-Score
components). Re-exported via `from .scoring_spy_warning import *`."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from .sources import SeriesPoint, TimeSeries
from .dashboard_core import *  # noqa: F401,F403
from .series_math import *  # noqa: F401,F403
from .signal_validation import SortedSeries
from .scoring_bhadial import *  # noqa: F401,F403


SPY_WARNING_COMPONENT_SLEEVES: list[dict[str, Any]] = [
    {
        "key": "liquidityStress",
        "label": "流动性压力",
        "weight": 0.16,
        "weightBasis": "领先(OOS IC 3M +0.38): Fed净流动性/准备金领先股市数周; 2026-06-13上调0.10→0.16",
        "componentIds": ["fed_net_liquidity", "delta_net_liq_13w", "tga_dev_signed"],
    },
    {
        "key": "fundingStress",
        "label": "融资压力",
        "weight": 0.24,
        "weightBasis": "稳健领先(OOS CI[0.24,0.56]排除0, lift 1.62, 提前90日): 融资市场先于股市收紧; 2026-06-19上调0.14→0.24",
        "componentIds": ["corridor_friction_1", "cp_tbill_spread", "fragmentation_21d"],
    },
    {
        "key": "ratesCurveStress",
        "label": "利率/曲线压力",
        "weight": 0.30,
        "weightBasis": "稳健领先(OOS CI[0.13,0.55]排除0): 真实曲线/期限溢价领先股市; 2026-06-19上调0.20→0.30",
        "componentIds": ["dgs30_dgs10", "dgs10_vol_21d", "curve_curvature_abs", "real_curve", "t10yie"],
    },
    {
        "key": "creditVolStress",
        "label": "信用/波动压力(同步上下文)",
        "weight": 0.0,
        "weightBasis": "稳健反向(OOS CI[-0.78,-0.20]整体<0): VIX/OAS/NFCI是同步-反指(回撤中后才飙升),结构上不适合做前瞻预警→2026-06-19从前瞻聚合剔除(权重0),仅作\"当前压力\"上下文展示",
        "componentIds": ["nfci", "hy_credit", "vix", "vix_term_structure", "risk_vs_safe"],
    },
    {
        "key": "externalShock",
        "label": "外部冲击",
        "weight": 0.10,
        "weightBasis": "连续IC弱但告警版lift 1.62; 权重维持0.10",
        "componentIds": ["dxy", "fx_vol", "wti", "ovx_dev", "natgas"],
    },
]


SPY_WARNING_NONLINEAR_SCALE = 1.08


SPY_WARNING_POST_SELLOFF_DAMPENER = -10.0


SPY_WARNING_LATE_RALLY_ROLLOVER_BOOST = 0.0


SPY_WARNING_LOW_SCORE_STALL_BOOST = 0.0


SPY_WARNING_FRAGILE_LOW_SCORE_BOOST = 0.0


SPY_WARNING_RALLY_FRAGILITY_BOOST = 3.0


SPY_WARNING_RULES_VERSION = "2026-06-12-v2"


def build_spy_early_warning(
    macro_liquidity: dict[str, Any],
    macro_liquidity_equity: dict[str, Any] | None = None,
    condition_series: dict[str, list[SeriesPoint]] | None = None,
) -> dict[str, Any]:
    warning = spy_early_warning_snapshot(macro_liquidity, macro_liquidity_equity)
    if warning.get("available"):
        warning["trend"] = build_spy_early_warning_trend(
            condition_series or {},
            macro_liquidity_equity,
            current_signal=warning.get("currentSignal", {}),
            current_score=optional_float(warning.get("score")),
            current_regime=str(warning.get("regime") or ""),
            current_regime_cn=str(warning.get("regimeCn") or ""),
        )
    return warning


def spy_early_warning_snapshot(macro_liquidity: dict[str, Any], macro_liquidity_equity: dict[str, Any] | None = None) -> dict[str, Any]:
    components = [item for item in macro_liquidity.get("components", []) if isinstance(item, dict)]
    if not components:
        return unavailable_spy_early_warning("宏观环境分项缺失,暂不能生成SPY预警指标。")
    component_by_id = {str(item.get("id")): item for item in components if item.get("id") is not None}
    current_signal = macro_liquidity_equity.get("currentSignal", {}) if isinstance(macro_liquidity_equity, dict) else {}
    sleeves: list[dict[str, Any]] = [
        build_macro_level_sleeve(macro_liquidity, weight=0.10),
        # 2026-06-19 demoted 0.20->0.15: derived from the Conditions-Score 3M change, which is
        # validated-LAGGING (bhadialChange13w robust=False) — down-weighted as a forward driver,
        # but only mildly: the severeDeterioration amplifier still preserves the extreme-case
        # De-risk response, so a -10+ score crash with corroboration still flags max risk.
        build_macro_deterioration_sleeve(current_signal, weight=0.15),
    ]
    for spec in SPY_WARNING_COMPONENT_SLEEVES:
        sleeves.append(build_spy_component_sleeve(spec, component_by_id))
    observed_sleeves = [item for item in sleeves if item.get("available")]
    weight_total = sum(float(item["weight"]) for item in observed_sleeves)
    if weight_total <= 0:
        return unavailable_spy_early_warning("可用预警袖分不足,暂不能生成SPY预警指标。")
    base_score = sum(float(item["score"]) * float(item["weight"]) for item in observed_sleeves) / weight_total
    amplifiers = spy_warning_amplifiers(macro_liquidity, current_signal)
    dampeners = spy_warning_dampeners(current_signal)
    score = bounded_score(
        base_score * SPY_WARNING_NONLINEAR_SCALE
        + sum(float(item["scoreBoost"]) for item in amplifiers)
        + sum(float(item["scoreOffset"]) for item in dampeners)
    )
    allocation = spy_warning_allocation(score)
    drivers = spy_warning_drivers(observed_sleeves)
    summary = spy_warning_summary(score, allocation, current_signal, drivers, amplifiers, dampeners)
    return {
        "available": True,
        "title": "SPY Early Warning Index",
        "score": round(score, 1),
        "baseScore": round(base_score, 1),
        "regime": allocation["regime"],
        "regimeCn": allocation["regimeCn"],
        "method": "Equity-specific 0-100 warning index from existing macro Conditions Score components plus 3M score deterioration and calibrated nonlinear risk amplifiers; higher means greater SPY/SPX drawdown risk. Sleeve weights restructured 2026-06-19 on OOS-aligned bootstrap robustness: creditVolStress is robustly anti-predictive/coincident (OOS CI entirely <0) so it is EXCLUDED from the forward aggregate (weight 0, shown as current-stress context); the robustly-leading fundingStress & ratesCurveStress carry the freed weight; macroDeterioration (lagging-derived) demoted — see each sleeve's weightBasis. Weights remain quasi-in-sample (the OOS slice motivated them); revalidate on fresh data and do not cite the aggregate's post-restructure OOS as independent confirmation.",
        "asOf": str(current_signal.get("date") or macro_liquidity_equity.get("asOf") if isinstance(macro_liquidity_equity, dict) else ""),
        "summary": summary,
        "allocation": allocation,
        "currentSignal": {
            "conditionsScore": optional_float(macro_liquidity.get("score")),
            "score3mChange": optional_float(current_signal.get("score3mChange")),
            "levelBucket": str(current_signal.get("levelBucket") or ""),
            "changeBucket": str(current_signal.get("changeBucket") or ""),
            "expectedForward3m": optional_float(current_signal.get("expectedForward3m")),
            "expectedDrawdown3m": optional_float(current_signal.get("expectedDrawdown3m")),
            "sp500Trailing3m": optional_float(current_signal.get("sp500Trailing3m")),
            "hitRate": optional_float(current_signal.get("hitRate")),
            "confidence": str(current_signal.get("confidence") or "low"),
        },
        "sleeves": observed_sleeves,
        "amplifiers": amplifiers,
        "dampeners": dampeners,
        "drivers": drivers,
        "backtest": spy_warning_backtest_payload(macro_liquidity_equity),
    }


def unavailable_spy_early_warning(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "title": "SPY Early Warning Index",
        "score": None,
        "regime": "Unavailable",
        "regimeCn": "不可用",
        "method": "Requires macro Conditions Score components and S&P 500 lead-study state.",
        "asOf": "",
        "summary": reason,
        "allocation": {"stance": "等待", "equityExposure": "不调整", "hedgeAction": "等待更多数据", "tone": "neutral"},
        "currentSignal": {},
        "sleeves": [],
        "amplifiers": [],
        "dampeners": [],
        "drivers": [],
        "backtest": spy_warning_backtest_payload(None),
        "trend": unavailable_spy_early_warning_trend(reason),
    }


def unavailable_spy_early_warning_trend(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "summary": reason,
        "points": [],
    }


def build_spy_early_warning_trend(
    condition_series: dict[str, list[SeriesPoint]],
    macro_liquidity_equity: dict[str, Any] | None,
    *,
    current_signal: dict[str, Any] | None = None,
    current_score: float | None = None,
    current_regime: str = "",
    current_regime_cn: str = "",
) -> dict[str, Any]:
    if not condition_series or not isinstance(macro_liquidity_equity, dict):
        return unavailable_spy_early_warning_trend("缺少历史分项序列,暂不能回放SPY预警。")
    rows = [
        row for row in macro_liquidity_equity.get("series", [])
        if isinstance(row, dict) and optional_float(row.get("liquidityScore")) is not None
    ]
    if len(rows) < 18:
        return unavailable_spy_early_warning_trend("月度历史样本不足,暂不能回放SPY预警。")
    current_signal = current_signal if isinstance(current_signal, dict) else {}
    current_date = str(current_signal.get("date") or macro_liquidity_equity.get("asOf") or "")
    points: list[dict[str, Any]] = []
    for row in rows:
        target_text = str(row.get("date") or "")
        try:
            target = date.fromisoformat(target_text)
        except ValueError:
            continue
        macro_point = spy_macro_liquidity_snapshot_at(condition_series, target)
        if macro_point is None:
            continue
        signal = spy_warning_signal_for_history_row(row, rows)
        if current_date and target_text == current_date:
            signal = {**signal, **current_signal}
        snapshot = spy_early_warning_snapshot(
            macro_point,
            {
                "asOf": target_text,
                "observationCount": macro_liquidity_equity.get("observationCount"),
                "currentSignal": signal,
            },
        )
        if not snapshot.get("available"):
            continue
        score = optional_float(snapshot.get("score"))
        allocation = snapshot.get("allocation") if isinstance(snapshot.get("allocation"), dict) else {}
        points.append(
            {
                "date": target_text,
                "score": round(score, 1) if score is not None else None,
                "baseScore": optional_float(snapshot.get("baseScore")),
                "regime": str(snapshot.get("regime") or ""),
                "regimeCn": str(snapshot.get("regimeCn") or ""),
                "conditionsScore": optional_float(signal.get("conditionsScore")),
                "score3mChange": optional_float(signal.get("score3mChange")),
                "stance": str(allocation.get("stance") or ""),
                "amplifiers": snapshot.get("amplifiers") if isinstance(snapshot.get("amplifiers"), list) else [],
                "dampeners": snapshot.get("dampeners") if isinstance(snapshot.get("dampeners"), list) else [],
                "rulesVersion": SPY_WARNING_RULES_VERSION,
            }
        )
    points = [point for point in points if optional_float(point.get("score")) is not None]
    if len(points) < 18:
        return unavailable_spy_early_warning_trend("可回放SPY预警样本不足。")
    if current_score is not None:
        points[-1]["score"] = round(current_score, 1)
        if current_regime:
            points[-1]["regime"] = current_regime
        if current_regime_cn:
            points[-1]["regimeCn"] = current_regime_cn
    latest = points[-1]
    prior_3m = points[-4] if len(points) >= 4 else None
    latest_score = optional_float(latest.get("score"))
    prior_score = optional_float(prior_3m.get("score")) if prior_3m else None
    score_3m_change = round(latest_score - prior_score, 1) if latest_score is not None and prior_score is not None else None
    return {
        "available": True,
        "summary": "SPY Early Warning月度回放,使用同一组宏观分项与3M评分变化生成0-100预警分数。注意: 回放对全部历史统一应用当前规则版本,并非时点规则。",
        "rulesVersion": SPY_WARNING_RULES_VERSION,
        "date": latest["date"],
        "score": latest_score,
        "score3mChange": score_3m_change,
        "points": points,
    }


def spy_macro_liquidity_snapshot_at(series: dict[str, list[SeriesPoint]], target: date) -> dict[str, Any] | None:
    score_row = bhadial_conditions_score_at(series, target, include_components=True)
    if score_row is None or int(score_row.get("observedFactorCount", 0)) < 5:
        return None
    return {
        "score": round(float(score_row["score"]), 1),
        "components": spy_components_from_bhadial_score_row(score_row),
    }


def spy_components_from_bhadial_score_row(score_row: dict[str, Any]) -> list[dict[str, Any]]:
    raw_components_by_id = {
        str(component.get("id")): component
        for module in score_row.get("modules", [])
        if isinstance(module, dict)
        for component in module.get("factors", [])
        if isinstance(component, dict)
    }
    components: list[dict[str, Any]] = []
    for module in BHADIAL_CONDITION_MODULES:
        for spec in module["factors"]:
            component_id = str(spec["id"])
            raw = raw_components_by_id.get(component_id, {})
            component_score = optional_float(raw.get("score"))
            if component_score is None:
                component_score = 50.0
            components.append(
                {
                    "id": component_id,
                    "module": str(module["name"]),
                    "moduleCn": str(module["nameCn"]),
                    "remoteName": str(spec["remoteName"]),
                    "name": str(spec["name"]),
                    "score": round(component_score, 1),
                    "value": "",
                    "source": str(spec["source"]),
                }
            )
    return components


def spy_warning_signal_for_history_row(row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    conditions_score = optional_float(row.get("liquidityScore"))
    score_change = optional_float(row.get("score3mChange"))
    row_date = str(row.get("date") or "")
    # Point-in-time guard: bucket ranks may only use observations available on the
    # replay date, otherwise the replay leaks the future score distribution.
    visible_rows = [item for item in rows if str(item.get("date") or "") <= row_date] if row_date else list(rows)
    change_rows = [item for item in visible_rows if optional_float(item.get("score3mChange")) is not None]
    return {
        "date": row_date,
        "conditionsScore": conditions_score,
        "score3mChange": score_change,
        "levelBucket": bucket_label_by_rank(visible_rows, "liquidityScore", conditions_score, ["低评分", "中位评分", "高评分"]),
        "changeBucket": bucket_label_by_rank(change_rows, "score3mChange", score_change, ["评分下行", "变化不大", "评分上行"]),
        "expectedForward3m": None,
        "expectedDrawdown3m": None,
        "sp500Trailing3m": optional_float(row.get("sp500Trailing3m")),
        "hitRate": None,
        "confidence": "history",
    }


def spy_warning_amplifiers(macro_liquidity: dict[str, Any], current_signal: dict[str, Any]) -> list[dict[str, Any]]:
    conditions_score = optional_float(current_signal.get("conditionsScore"))
    if conditions_score is None:
        conditions_score = optional_float(macro_liquidity.get("score"))
    score_change = optional_float(current_signal.get("score3mChange"))
    trailing_3m = optional_float(current_signal.get("sp500Trailing3m"))
    amplifiers: list[dict[str, Any]] = []
    if score_change is not None and score_change <= -10:
        amplifiers.append(
            {
                "key": "severeDeterioration",
                "label": "3M评分急剧转弱",
                "scoreBoost": 10.0,
                "detail": f"3M Conditions Score变化 {format_signed_number(score_change, digits=1)}",
            }
        )
    if conditions_score is not None and score_change is not None and conditions_score >= 55 and score_change <= -2.9:
        amplifiers.append(
            {
                "key": "highScoreRollover",
                "label": "高分后回落",
                "scoreBoost": 12.0,
                "detail": f"Conditions Score {conditions_score:.1f}, 3M变化 {format_signed_number(score_change, digits=1)}",
            }
        )
    if (
        SPY_WARNING_FRAGILE_LOW_SCORE_BOOST > 0
        and conditions_score is not None
        and conditions_score <= 42
        and (score_change is None or score_change <= 1)
    ):
        amplifiers.append(
            {
                "key": "fragileLowScore",
                "label": "低分脆弱区",
                "scoreBoost": SPY_WARNING_FRAGILE_LOW_SCORE_BOOST,
                "detail": f"Conditions Score {conditions_score:.1f},缺少明显改善",
            }
        )
    if (
        SPY_WARNING_LOW_SCORE_STALL_BOOST > 0
        and conditions_score is not None
        and conditions_score <= 42
        and score_change is not None
        and 0 <= score_change <= 0.5
        and trailing_3m is not None
        and trailing_3m > -5
    ):
        amplifiers.append(
            {
                "key": "lowScoreStall",
                "label": "低分改善停滞",
                "scoreBoost": SPY_WARNING_LOW_SCORE_STALL_BOOST,
                "detail": (
                    f"Conditions Score {conditions_score:.1f},"
                    f"3M变化 {format_signed_number(score_change, digits=1)},"
                    f"SPX 3M {format_signed_number(trailing_3m, digits=1)}%"
                ),
            }
        )
    if (
        SPY_WARNING_RALLY_FRAGILITY_BOOST > 0
        and trailing_3m is not None
        and trailing_3m >= 5
        and score_change is not None
        and score_change <= -2
    ):
        amplifiers.append(
            {
                "key": "rallyFragility",
                "label": "上涨后宏观转弱",
                "scoreBoost": SPY_WARNING_RALLY_FRAGILITY_BOOST,
                "detail": f"SPX 3M {format_signed_number(trailing_3m, digits=1)}%,评分变化 {format_signed_number(score_change, digits=1)}",
            }
        )
    if (
        SPY_WARNING_LATE_RALLY_ROLLOVER_BOOST > 0
        and trailing_3m is not None
        and trailing_3m >= 9
        and conditions_score is not None
        and conditions_score > 42
        and score_change is not None
        and score_change <= -2
    ):
        amplifiers.append(
            {
                "key": "lateCycleRallyRollover",
                "label": "强涨后回落确认",
                "scoreBoost": SPY_WARNING_LATE_RALLY_ROLLOVER_BOOST,
                "detail": (
                    f"SPX 3M {format_signed_number(trailing_3m, digits=1)}%,"
                    f"Conditions Score {conditions_score:.1f},"
                    f"评分变化 {format_signed_number(score_change, digits=1)}"
                ),
            }
        )
    return amplifiers


def spy_warning_dampeners(current_signal: dict[str, Any]) -> list[dict[str, Any]]:
    score_change = optional_float(current_signal.get("score3mChange"))
    trailing_3m = optional_float(current_signal.get("sp500Trailing3m"))
    dampeners: list[dict[str, Any]] = []
    if trailing_3m is not None and trailing_3m <= -6 and score_change is not None and score_change > -10:
        dampeners.append(
            {
                "key": "postSelloffExhaustion",
                "label": "深跌后降噪",
                "scoreOffset": SPY_WARNING_POST_SELLOFF_DAMPENER,
                "detail": (
                    f"SPX 3M {format_signed_number(trailing_3m, digits=1)}%,"
                    f"评分变化 {format_signed_number(score_change, digits=1)},非急剧恶化"
                ),
            }
        )
    return dampeners


def build_macro_level_sleeve(macro_liquidity: dict[str, Any], *, weight: float) -> dict[str, Any]:
    conditions_score = optional_float(macro_liquidity.get("score"))
    risk = 100.0 - conditions_score if conditions_score is not None else 0.0
    return {
        "key": "macroLevel",
        "label": "宏观分数水平",
        "available": conditions_score is not None,
        "score": round(bounded_score(risk), 1) if conditions_score is not None else 0.0,
        "weight": weight,
        "detail": f"Conditions Score {conditions_score:.1f}" if conditions_score is not None else "Conditions Score --",
        "drivers": [
            {
                "id": "conditionsScore",
                "name": "Conditions Score水平",
                "riskScore": round(bounded_score(risk), 1) if conditions_score is not None else 0.0,
                "value": f"{conditions_score:.1f}" if conditions_score is not None else "--",
            }
        ],
    }


def build_macro_deterioration_sleeve(current_signal: dict[str, Any], *, weight: float) -> dict[str, Any]:
    score_change = optional_float(current_signal.get("score3mChange"))
    level_bucket = str(current_signal.get("levelBucket") or "")
    change_bucket = str(current_signal.get("changeBucket") or "")
    expected_forward = optional_float(current_signal.get("expectedForward3m"))
    expected_drawdown = optional_float(current_signal.get("expectedDrawdown3m"))
    deterioration = deterioration_risk_score(score_change, level_bucket, expected_forward, expected_drawdown)
    return {
        "key": "macroDeterioration",
        "label": "宏观评分转弱",
        "available": score_change is not None,
        "score": round(deterioration, 1) if score_change is not None else 0.0,
        "weight": weight,
        "detail": f"{level_bucket or '未知水平'} · {change_bucket or '未知变化'} · 3M变化 {format_signed_number(score_change, digits=1)}",
        "drivers": [
            {
                "id": "score3mChange",
                "name": "Conditions Score 3M变化",
                "riskScore": round(deterioration, 1) if score_change is not None else 0.0,
                "value": format_signed_number(score_change, digits=1),
            }
        ],
    }


def deterioration_risk_score(
    score_change: float | None,
    level_bucket: str,
    expected_forward: float | None,
    expected_drawdown: float | None,
) -> float:
    if score_change is None:
        return 0.0
    if score_change <= -10:
        risk = 100.0
    elif score_change <= -5:
        risk = 82.0
    elif score_change <= -2.9:
        risk = 68.0
    elif score_change < 0:
        risk = 45.0
    else:
        risk = max(0.0, 30.0 - score_change * 4.0)
    if level_bucket == "高评分" and score_change <= -2.9:
        risk += 12.0
    if expected_forward is not None and expected_forward < -2:
        risk += 8.0
    if expected_drawdown is not None and expected_drawdown <= -8:
        risk += 8.0
    return bounded_score(risk)


def build_spy_component_sleeve(spec: dict[str, Any], component_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for component_id in spec["componentIds"]:
        component = component_by_id.get(str(component_id))
        if component is None:
            continue
        component_score = optional_float(component.get("score"))
        if component_score is None:
            continue
        risk = 100.0 - component_score
        rows.append(
            {
                "id": str(component.get("id")),
                "name": str(component.get("name") or component.get("remoteName") or component_id),
                "module": str(component.get("module") or ""),
                "riskScore": round(bounded_score(risk), 1),
                "value": str(component.get("value") or ""),
                "componentScore": round(component_score, 1),
            }
        )
    score = sum(item["riskScore"] for item in rows) / len(rows) if rows else 0.0
    top_drivers = sorted(rows, key=lambda item: item["riskScore"], reverse=True)[:3]
    return {
        "key": spec["key"],
        "label": spec["label"],
        "available": bool(rows),
        "score": round(score, 1),
        "weight": float(spec["weight"]),
        "weightBasis": str(spec.get("weightBasis") or ""),
        "detail": f"{len(rows)}/{len(spec['componentIds'])} factors",
        "drivers": top_drivers,
    }


def spy_warning_drivers(sleeves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sleeve in sleeves:
        sleeve_score = optional_float(sleeve.get("score")) or 0.0
        for driver in sleeve.get("drivers", []):
            if not isinstance(driver, dict):
                continue
            risk_score = optional_float(driver.get("riskScore"))
            if risk_score is None:
                continue
            rows.append(
                {
                    "id": str(driver.get("id") or ""),
                    "name": str(driver.get("name") or ""),
                    "sleeve": sleeve["label"],
                    "riskScore": round(risk_score, 1),
                    "sleeveScore": round(sleeve_score, 1),
                    "value": str(driver.get("value") or ""),
                }
            )
    return sorted(rows, key=lambda item: (item["sleeveScore"], item["riskScore"]), reverse=True)[:6]


def spy_warning_allocation(score: float) -> dict[str, Any]:
    base = {"horizon": "1-3M", "horizonCn": "1-3个月"}
    if score >= 75:
        return {
            **base,
            "regime": "De-risk",
            "regimeCn": "减仓预警",
            "stance": "减仓/保护",
            "equityExposure": "权益降至常规仓位的25-50%",
            "exposureBandPct": [25, 50],
            "hedgeAction": "优先保护性对冲或降低高Beta暴露",
            "tone": "restrictive",
        }
    if score >= 60:
        return {
            **base,
            "regime": "Caution",
            "regimeCn": "谨慎",
            "stance": "降权/对冲",
            "equityExposure": "权益维持常规仓位的50-75%",
            "exposureBandPct": [50, 75],
            "hedgeAction": "新增仓位放慢,回撤保护优先",
            "tone": "restrictive",
        }
    if score >= 40:
        return {
            **base,
            "regime": "Neutral",
            "regimeCn": "中性",
            "stance": "持有/控仓",
            "equityExposure": "维持核心仓位,避免追高",
            "exposureBandPct": [75, 100],
            "hedgeAction": "等待信用/波动或评分转弱确认",
            "tone": "neutral",
        }
    return {
        **base,
        "regime": "Constructive",
        "regimeCn": "建设性",
        "stance": "正常/逢低加",
        "equityExposure": "维持常规或略高权益仓位",
        "exposureBandPct": [90, 110],
        "hedgeAction": "保护需求较低,以再平衡为主",
        "tone": "supportive",
    }


def spy_warning_summary(
    score: float,
    allocation: dict[str, str],
    current_signal: dict[str, Any],
    drivers: list[dict[str, Any]],
    amplifiers: list[dict[str, Any]] | None = None,
    dampeners: list[dict[str, Any]] | None = None,
) -> str:
    score_change = optional_float(current_signal.get("score3mChange"))
    level_bucket = str(current_signal.get("levelBucket") or "未知水平")
    change_bucket = str(current_signal.get("changeBucket") or "未知变化")
    driver_text = "、".join(item["name"] for item in drivers[:3] if item.get("name")) or "分项压力"
    amplifier_text = "、".join(item["label"] for item in (amplifiers or [])[:2] if item.get("label"))
    amplifier_clause = f"{amplifier_text}放大预警, " if amplifier_text else ""
    dampener_text = "、".join(item["label"] for item in (dampeners or [])[:2] if item.get("label"))
    dampener_clause = f"{dampener_text}已降低噪声权重, " if dampener_text else ""
    if allocation["regime"] == "De-risk":
        return (
            f"SPY预警{score:.1f},进入减仓预警: {amplifier_clause}{dampener_clause}{level_bucket}环境转弱,3M评分变化{format_signed_number(score_change, digits=1)},"
            f"主要压力来自{driver_text}; 权益应优先降风险和保护回撤。"
        )
    if allocation["regime"] == "Caution" and amplifier_text:
        return (
            f"SPY预警{score:.1f},进入谨慎区: {amplifier_clause}{dampener_clause}{level_bucket}/{change_bucket},"
            f"主要压力来自{driver_text}; 新增仓位放慢,回撤保护优先。"
        )
    if dampener_text:
        return (
            f"SPY预警{score:.1f},处于{allocation['regimeCn']}: {dampener_clause}{level_bucket}/{change_bucket},"
            f"主要压力来自{driver_text}; 等待二次走弱确认后再提高防守。"
        )
    if score_change is not None and score_change > 0:
        return (
            f"SPY预警{score:.1f},处于{allocation['regimeCn']}: 宏观评分改善({change_bucket},3M变化{format_signed_number(score_change, digits=1)}),"
            f"但{driver_text}仍需跟踪; 维持核心仓位,避免追高。"
        )
    return (
        f"SPY预警{score:.1f},处于{allocation['regimeCn']}: {level_bucket}/{change_bucket},"
        f"主要压力来自{driver_text}; 按{allocation['stance']}处理。"
    )


def spy_warning_backtest_payload(macro_liquidity_equity: dict[str, Any] | None) -> dict[str, Any]:
    observation_count = int(macro_liquidity_equity.get("observationCount") or 0) if isinstance(macro_liquidity_equity, dict) else 0
    return {
        "target": "3M SPX drawdown and negative forward-return warning",
        "sample": "Monthly 5Y S&P 500 price-index proxy observations",
        "sampleSize": observation_count,
        "evidence": [
            "score>45 and 3M score change<=-2.9 historically isolated the weakest forward-return state better than low score alone",
            "VIX, CP-TBill, curve inversion, WTI/oil-volatility shock, and NFCI ranked highest in simple 3M drawdown diagnostics",
            "The signal is a risk control overlay, not a standalone return forecast",
        ],
    }


def build_spy_warning_rule_audit(
    rule_fires: dict[str, list[dict[str, Any]]],
    rule_meta: dict[str, dict[str, Any]],
    week_dates_avail: list[date],
    prices_sorted: SortedSeries,
) -> dict[str, Any]:
    if len(week_dates_avail) < SIGNAL_VALIDATION_MIN_WEEKS:
        return {"available": False, "reason": "周度回放样本不足,暂不能审计放大器规则。", "rules": []}
    split_index = max(1, min(len(week_dates_avail) - 1, int(len(week_dates_avail) * SIGNAL_VALIDATION_OOS_SPLIT)))
    oos_start = week_dates_avail[split_index]

    def drawdown_event(target: date) -> bool | None:
        drawdown = prices_sorted.forward_max_drawdown_pct(target, days=SIGNAL_VALIDATION_DRAWDOWN_DAYS)
        if drawdown is None:
            return None
        return drawdown <= SIGNAL_VALIDATION_DRAWDOWN_PCT

    oos_scored = [(target, drawdown_event(target)) for target in week_dates_avail[split_index:]]
    oos_scored = [(target, event) for target, event in oos_scored if event is not None]
    base_rate = (sum(1 for _, event in oos_scored if event) / len(oos_scored)) if oos_scored else None
    base_forward_values = [
        value
        for value in (prices_sorted.forward_return_pct(target, days=91) for target, _ in oos_scored)
        if value is not None
    ]
    base_forward = sum(base_forward_values) / len(base_forward_values) if base_forward_values else None

    rules: list[dict[str, Any]] = []
    for key in sorted(rule_meta):
        meta = rule_meta[key]
        fires = rule_fires.get(key, [])
        fire_dates = [fire["date"] for fire in fires]
        oos_fire_dates = [target for target in fire_dates if target >= oos_start]
        scored = [(target, drawdown_event(target)) for target in oos_fire_dates]
        scored = [(target, event) for target, event in scored if event is not None]
        hit_rate = (sum(1 for _, event in scored if event) / len(scored)) if scored else None
        lift = (hit_rate / base_rate) if hit_rate is not None and base_rate else None
        forward_values = [
            value
            for value in (prices_sorted.forward_return_pct(target, days=91) for target in fire_dates)
            if value is not None
        ]
        forward_after_fire = sum(forward_values) / len(forward_values) if forward_values else None
        trailing_values = [optional_float(fire.get("trailing3m")) for fire in fires]
        trailing_values = [value for value in trailing_values if value is not None]
        trailing_at_fire = sum(trailing_values) / len(trailing_values) if trailing_values else None
        lead_times = []
        for target, event in scored:
            if not event:
                continue
            trough = prices_sorted.forward_trough_date(target, days=SIGNAL_VALIDATION_DRAWDOWN_DAYS)
            if trough is not None:
                lead_times.append((trough - target).days)
        lead_time = sum(lead_times) / len(lead_times) if lead_times else None
        rules.append(
            {
                "key": key,
                "label": meta["label"],
                "kind": meta["kind"],
                "scoreEffect": meta["scoreEffect"],
                "fireCount": len(fire_dates),
                "oosFireCount": len(scored),
                "oosHitRate": round(hit_rate, 3) if hit_rate is not None else None,
                "baseRate": round(base_rate, 3) if base_rate is not None else None,
                "lift": round(lift, 2) if lift is not None else None,
                "avgForward3mAfterFire": round(forward_after_fire, 2) if forward_after_fire is not None else None,
                "avgTrailing3mAtFire": round(trailing_at_fire, 2) if trailing_at_fire is not None else None,
                "leadTimeDays": round(lead_time, 1) if lead_time is not None else None,
                "verdict": spy_warning_rule_verdict(meta["kind"], len(scored), lift),
            }
        )
    return {
        "available": True,
        "method": (
            "Weekly point-in-time replay; each rule's post-fire OOS drawdown frequency is compared with the "
            "unconditional base rate. Amplifiers should fire BEFORE drawdowns (lift>1); a dampener is justified "
            "only when drawdowns after it fires are rarer than base rate (lift<1)."
        ),
        "oosStartDate": oos_start.isoformat(),
        "oosSampleSize": len(oos_scored),
        "baseRate": round(base_rate, 3) if base_rate is not None else None,
        "baseForward3m": round(base_forward, 2) if base_forward is not None else None,
        "drawdownRule": f"{SIGNAL_VALIDATION_DRAWDOWN_DAYS}D内最大回撤≤{SIGNAL_VALIDATION_DRAWDOWN_PCT:.0f}%",
        "rules": rules,
    }


def spy_warning_rule_verdict(kind: str, oos_fire_count: int, lift: float | None) -> str:
    if oos_fire_count < 3 or lift is None:
        return "insufficient"
    if kind == "dampener":
        if lift <= 0.85:
            return "justified"
        if lift >= 1.0:
            return "counterproductive"
        return "neutral"
    if lift >= 1.15:
        return "additive"
    if lift <= 0.85:
        return "counterproductive"
    return "neutral"
