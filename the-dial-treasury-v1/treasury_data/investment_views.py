"""Investment-view decision metadata and historical equity-impact overlays.

Kept separate from dashboard orchestration so trade-view presentation rules can
be tested and evolved without expanding ``build_dashboard.py`` further.
"""
from __future__ import annotations

from statistics import median
from typing import Any

from .dashboard_core import bucket_label_by_rank, optional_float
from .scoring_equity import equity_impact_confidence, unavailable_equity_impact
from .sources import QuarterlyRefunding


def _money_billions_value(value: float | None) -> str:
    if value is None:
        return "--"
    return f"${value:.0f}B"


def _available_indicator_value(
    ind: dict[str, Any],
    key: str,
    *,
    series_key: str | None = None,
) -> float | None:
    """Return an indicator only when its provenance says it was observed.

    ``compute_indicators`` keeps zero-valued compatibility fields for several
    optional FRED series and records the real state in ``availability``.  Trade
    views must not interpret those placeholders as measured macro data.  Older
    callers without provenance metadata remain supported for tests and exports.
    """
    availability = ind.get("availability")
    if isinstance(availability, dict) and key in availability and availability[key] is not True:
        return None
    percentile_series = ind.get("percentile_series")
    if series_key and isinstance(percentile_series, dict) and series_key in percentile_series:
        points = percentile_series.get(series_key)
        if not isinstance(points, list) or not points:
            return None
    return optional_float(ind.get(key))


def _format_percent_indicator(label: str, value: float | None) -> str:
    return f"{label} --" if value is None else f"{label} {value:.1f}%"


def build_ideas(
    ind: dict[str, Any],
    *,
    macro_liquidity: dict[str, Any] | None = None,
    macro_liquidity_equity: dict[str, Any] | None = None,
    quarterly_refunding: QuarterlyRefunding | None = None,
    conclusion_audit: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    reliability_score = optional_float(macro_liquidity.get("reliabilityScore")) if macro_liquidity else None
    compatibility_score = optional_float(macro_liquidity.get("score")) if macro_liquidity else None
    liquidity_score = reliability_score if reliability_score is not None else compatibility_score
    liquidity_regime = macro_liquidity.get("regime") if macro_liquidity else "待评分"
    if reliability_score is not None:
        liquidity_text = f"宏观可靠性评分{reliability_score:.1f}"
    elif compatibility_score is not None:
        liquidity_text = f"宏观环境评分{compatibility_score:.1f}({liquidity_regime})"
    else:
        liquidity_text = f"宏观环境{liquidity_regime}"
    qra_text = "QRA待接入"
    qra_borrowing = None
    if quarterly_refunding:
        qra_borrowing = quarterly_refunding.next_quarter_borrowing_billions
        next_borrow = _money_billions_value(qra_borrowing)
        next_date = quarterly_refunding.next_policy_statement_date.isoformat() if quarterly_refunding.next_policy_statement_date else "待公布"
        qra_text = f"QRA下季借款{next_borrow},下一次政策声明{next_date}"
    cpi_yoy = _available_indicator_value(ind, "cpi_yoy")
    pce_yoy = _available_indicator_value(ind, "pce_yoy")
    core_pce_yoy = _available_indicator_value(ind, "core_pce_yoy")
    trimmed_pce_yoy = _available_indicator_value(ind, "trimmed_mean_pce_yoy")
    ppi_yoy = _available_indicator_value(ind, "ppi_yoy")
    inflation_tracker = " / ".join(
        (
            _format_percent_indicator("CPI", cpi_yoy),
            _format_percent_indicator("PCE", pce_yoy),
            _format_percent_indicator("核心PCE", core_pce_yoy),
            _format_percent_indicator("Dallas Trimmed PCE", trimmed_pce_yoy),
        )
    )
    inflation_values = [value for value in (cpi_yoy, pce_yoy, core_pce_yoy, trimmed_pce_yoy, ppi_yoy) if value is not None]
    inflation_hot = bool(inflation_values) and max(inflation_values) >= 3.0
    cool_inputs = (pce_yoy, core_pce_yoy, trimmed_pce_yoy, ppi_yoy)
    inflation_cool = (
        all(value is not None for value in cool_inputs)
        and max(float(pce_yoy), float(core_pce_yoy), float(trimmed_pce_yoy)) <= 2.4
        and float(ppi_yoy) <= 2.5
    )
    inflation_data_complete = all(value is not None for value in (cpi_yoy, *cool_inputs))
    two_year_change = ind["two_year_m1_change_bp"]
    macro_tight = liquidity_score is not None and liquidity_score < 45
    qra_supply_heavy = qra_borrowing is not None and qra_borrowing >= 500
    qra_supply_light = qra_borrowing is not None and qra_borrowing <= 350
    curve_already_steep = ind["s5s30"] >= 95
    dff = _available_indicator_value(ind, "dff")
    sofr = _available_indicator_value(ind, "sofr")
    two_year_vs_effr_bp = (ind["two_year"] - dff) * 100 if dff is not None else None
    cuts_priced = two_year_vs_effr_bp is not None and two_year_vs_effr_bp <= -60 and two_year_change <= -25
    wti = _available_indicator_value(ind, "wti", series_key="wti")
    wti_shock = _available_indicator_value(ind, "wti_shock", series_key="wti_shock")
    breakeven_10y = _available_indicator_value(ind, "breakeven_10y")
    energy_hot = wti is not None and (wti >= 80 or (wti_shock is not None and wti_shock >= 0.10))
    energy_soft = wti is not None and (wti <= 75 or (wti_shock is not None and wti_shock <= -0.10))
    bei_rich = breakeven_10y is not None and breakeven_10y >= 2.55

    if inflation_cool and two_year_change <= -15 and not macro_tight:
        duration_idea = {
            "title": "加回久期",
            "tag": "LONG 久期",
            "text": (
                f"{inflation_tracker}进入反通胀组合,2Y月变动{two_year_change:+.0f}bp显示政策路径向降息重新定价。"
                f"{liquidity_text}改善了承接环境,可把组合久期逐步加回至基准附近;若核心PCE或Dallas Trimmed PCE重新上行,暂停加仓。"
            ),
            "source": "货币政策 · 宏观基本面 · 宏观环境评分",
        }
    elif inflation_hot or two_year_change >= 15 or macro_tight:
        inflation_context = (
            f"{inflation_tracker}仍对久期不友好"
            if inflation_hot
            else f"{inflation_tracker}存在缺失,不据此判断通胀已经降温"
            if not inflation_data_complete
            else f"{inflation_tracker}尚未给出明确的反通胀确认"
        )
        duration_idea = {
            "title": "战术减久期",
            "tag": "SHORT 久期",
            "text": (
                f"{inflation_context},2Y月变动{two_year_change:+.0f}bp显示政策路径重新定价。"
                f"{liquidity_text}提示承接环境不算宽松,组合久期维持低于基准,等待PCE/核心PCE降温或2Y回落再加回。"
            ),
            "source": "货币政策 · 宏观基本面 · 宏观环境评分",
        }
    else:
        inflation_context = (
            f"{inflation_tracker}数据不完整,不把缺失值当作通胀降温信号"
            if not inflation_data_complete
            else inflation_tracker
        )
        duration_idea = {
            "title": "久期区间防守",
            "tag": "HOLD 久期",
            "text": (
                f"{inflation_context},与2Y月变动{two_year_change:+.0f}bp没有形成单边信号。"
                f"{liquidity_text}要求久期保持接近基准,用PCE/核心PCE和2Y再定价确认下一次方向。"
            ),
            "source": "货币政策 · 宏观基本面 · 宏观环境评分",
        }

    if qra_supply_light and curve_already_steep:
        curve_idea = {
            "title": "5s30s转区间交易",
            "tag": "CURVE 观望",
            "text": (
                f"5s30s已在{ind['s5s30']:.0f}bp,{qra_text}; 曲线已充分反映长端供给压力,不追做陡。"
                "更适合逢陡降风险或用期权表达尾部供给风险,等待QRA重新上修或长端回落后再加仓。"
            ),
            "source": "供给与技术面 · QRA · 期限溢价",
        }
    elif qra_supply_heavy and curve_already_steep:
        curve_idea = {
            "title": "做陡持有但降杠杆",
            "tag": "CURVE 降杠杆",
            "text": (
                f"5s30s当前{ind['s5s30']:.0f}bp,{qra_text}; 供给压力仍在,但曲线已经偏陡。"
                "保留核心做陡逻辑,同时降低新增追价,用QRA和长端拍卖结果确认是否续持。"
            ),
            "source": "供给与技术面 · QRA · 期限溢价",
        }
    elif qra_supply_heavy or ind["s5s30"] <= 45:
        curve_idea = {
            "title": "做陡 5s30s 曲线",
            "tag": "CURVE 做陡",
            "text": (
                f"5s30s当前{ind['s5s30']:.0f}bp,{qra_text}; 前端由政策锚定,长端更直接承受赤字、息票供给和期限溢价压力。"
                "若长端空头挤压或QRA低于预期,需要降低做陡敞口。"
            ),
            "source": "供给与技术面 · QRA · 期限溢价",
        }
    else:
        curve_idea = {
            "title": "5s30s轻仓观察",
            "tag": "CURVE 中性",
            "text": (
                f"5s30s当前{ind['s5s30']:.0f}bp,{qra_text}; 供给信号和曲线位置没有给出足够不对称性。"
                "维持轻仓或用事件驱动交易,等QRA、30Y拍卖和期限溢价方向确认。"
            ),
            "source": "供给与技术面 · QRA · 期限溢价",
        }

    if cuts_priced:
        front_end_idea = {
            "title": "前端谨慎 · 降息预期已定价",
            "tag": "FRONT-END 谨慎",
            "text": (
                f"2Y收益率{ind['two_year']:.2f}%已较EFFR低{abs(float(two_year_vs_effr_bp)):.0f}bp,且月变动{two_year_change:+.0f}bp,说明降息预期已经较多反映。"
                "前端仍可用于防守,但不应简单视作高确定性carry;若就业或核心PCE反弹,前端回撤风险会放大。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }
    elif dff is None or sofr is None:
        front_end_idea = {
            "title": "前端数据不足 · 暂不判断 carry",
            "tag": "FRONT-END 数据不足",
            "text": (
                f"2Y收益率{ind['two_year']:.2f}%,SOFR {'--' if sofr is None else f'{sofr:.2f}%'}、"
                f"EFFR {'--' if dff is None else f'{dff:.2f}%'}缺少完整观测。"
                "资金利率缺失时不计算2Y相对EFFR定价,也不生成前端carry结论。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }
    elif ind["two_year"] >= 3.0 and sofr >= 3.0 and dff >= 3.0:
        front_end_idea = {
            "title": "前端持有 · 吃 carry",
            "tag": "LONG 前端",
            "text": (
                f"2Y收益率{ind['two_year']:.2f}%,SOFR {sofr:.2f}%、EFFR {dff:.2f}%仍提供前端票息。"
                "相对长端,前端对供给冲击和期限溢价更不敏感,适合作为风险预算内的现金替代。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }
    else:
        front_end_idea = {
            "title": "前端中性 · 等待再定价",
            "tag": "FRONT-END 中性",
            "text": (
                f"2Y收益率{ind['two_year']:.2f}%,SOFR {sofr:.2f}%、EFFR {dff:.2f}%没有形成明确carry优势。"
                "前端更适合作为流动性仓位,等待政策路径或资金利率重新拉开风险补偿。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }

    if breakeven_10y is None or wti is None:
        breakeven_idea = {
            "title": "盈亏平衡通胀数据不足",
            "tag": "RV 数据不足",
            "text": (
                f"10Y BEI {'--' if breakeven_10y is None else f'{breakeven_10y:.2f}%'}、"
                f"WTI {'--' if wti is None else f'${wti:.2f}'}缺少完整观测。"
                "跨市场证据不完整时不生成方向性盈亏平衡通胀交易。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    elif inflation_cool and energy_soft and bei_rich:
        breakeven_idea = {
            "title": "降低盈亏平衡通胀",
            "tag": "RV 降通胀补偿",
            "text": (
                f"{inflation_tracker}降温,WTI ${wti:.2f}未提供能源上行确认,但10Y BEI仍有{breakeven_10y:.2f}%。"
                "盈亏平衡通胀的风险回报转弱,更适合减仓或等待能源/核心PCE重新加速。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    elif inflation_hot and (energy_hot or not bei_rich):
        breakeven_idea = {
            "title": "战术做多盈亏平衡通胀",
            "tag": "RV 通胀",
            "text": (
                f"10Y BEI {breakeven_10y:.2f}%、WTI ${wti:.2f}共同跟踪通胀补偿。"
                "若能源冲击或进口价格继续传导,盈亏平衡比名义久期更直接;油价回落或PCE/核心PCE降温是退出信号。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    elif bei_rich and not inflation_hot:
        breakeven_idea = {
            "title": "通胀补偿转防守",
            "tag": "RV 观望",
            "text": (
                f"10Y BEI {breakeven_10y:.2f}%已经偏高,而{inflation_tracker}没有同步恶化。"
                "盈亏平衡更适合等待回调后再布局,或只保留小额尾部对冲。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    else:
        breakeven_idea = {
            "title": "小仓位通胀对冲",
            "tag": "RV 对冲",
            "text": (
                f"10Y BEI {breakeven_10y:.2f}%、WTI ${wti:.2f}没有形成强单边信号。"
                "保留小仓位通胀对冲即可,加仓需要能源冲击或PCE/核心PCE重新上行确认。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    confidence_fields = investment_view_confidence_fields(conclusion_audit)
    equity_impact = investment_view_equity_impact(macro_liquidity_equity)
    ideas = [duration_idea, curve_idea, front_end_idea, breakeven_idea]
    return [
        {
            **idea,
            "horizon": "3-6M",
            "horizonCn": "3-6个月",
            **investment_view_decision_fields(idea, priority=index + 1),
            **confidence_fields,
            "equityImpact": equity_impact,
        }
        for index, idea in enumerate(ideas)
    ]


def investment_view_decision_fields(idea: dict[str, Any], *, priority: int) -> dict[str, Any]:
    tag = str(idea.get("tag") or "")
    if "数据不足" in tag:
        trigger = "缺失的官方数据恢复，且跨市场信号重新形成同向确认"
        invalidation = "任一关键输入继续缺失或数据时点无法对齐"
        sizing = "不建仓 · 等待数据"
    elif "久期" in tag:
        if "LONG" in tag:
            trigger = "核心PCE与Dallas Trimmed PCE继续降温，且2Y收益率延续回落"
            invalidation = "核心通胀重新上行或2Y收益率转为持续上升"
        elif "SHORT" in tag:
            trigger = "核心通胀维持偏热，或2Y收益率继续上行确认政策重定价"
            invalidation = "PCE/核心PCE降温，或2Y收益率明显回落"
        else:
            trigger = "PCE/核心PCE与2Y收益率形成同向确认"
            invalidation = "政策路径重新进入无方向震荡"
        sizing = "主观点 · 基准久期偏离"
    elif "CURVE" in tag:
        trigger = "QRA上修长债供给、30Y拍卖走弱或期限溢价继续上行"
        invalidation = "长端空头挤压、QRA低于预期或曲线已过度变陡"
        sizing = "次级观点 · 曲线相对价值"
    elif "FRONT-END" in tag or "前端" in tag:
        trigger = "SOFR/EFFR维持高位，且2Y仍提供足够正carry"
        invalidation = "降息预期充分定价，或就业/核心PCE反弹推高前端波动"
        sizing = "防守仓位 · 现金替代"
    else:
        trigger = "能源或进口价格上行，并由PCE/核心PCE重新加速确认"
        invalidation = "油价回落，或PCE/核心PCE持续降温"
        sizing = "小仓位 · 通胀尾部对冲"
    return {
        "priority": priority,
        "direction": tag or "待确认",
        "trigger": trigger,
        "invalidation": invalidation,
        "sizing": sizing,
    }


def investment_view_equity_impact(panel: dict[str, Any] | None, *, min_sample: int = 6) -> dict[str, Any]:
    if not isinstance(panel, dict) or not panel.get("available"):
        return unavailable_equity_impact("S&P 500历史样本不可用,不形成SPY影响结论。")
    rows = [row for row in panel.get("series", []) if isinstance(row, dict)]
    current_signal = panel.get("currentSignal") if isinstance(panel.get("currentSignal"), dict) else {}
    current_level = str(current_signal.get("levelBucket") or "")
    current_change = str(current_signal.get("changeBucket") or "")
    if not rows or not current_level or not current_change:
        return unavailable_equity_impact("同类宏观环境标签缺失,不形成SPY影响结论。")
    usable = [
        row
        for row in rows
        if row.get("forward3m") is not None
        and row.get("score3mChange") is not None
        and optional_float(row.get("liquidityScore")) is not None
    ]
    change_rows = [row for row in usable if optional_float(row.get("score3mChange")) is not None]
    sample = []
    for row in usable:
        level_label = bucket_label_by_rank(rows, "liquidityScore", optional_float(row.get("liquidityScore")), ["低评分", "中位评分", "高评分"])
        change_label = bucket_label_by_rank(change_rows, "score3mChange", optional_float(row.get("score3mChange")), ["评分下行", "变化不大", "评分上行"])
        if level_label == current_level and change_label == current_change:
            sample.append(row)
    if len(sample) < min_sample:
        return unavailable_equity_impact(
            f"历史同类环境样本不足({len(sample)}/{min_sample}),不形成SPY影响结论。"
        )
    forward_1m = numeric_values(sample, "forward1m")
    forward_3m = numeric_values(sample, "forward3m")
    forward_6m = numeric_values(sample, "forward6m")
    drawdowns = numeric_values(sample, "forward3mMaxDrawdown")
    median_3m = median(forward_3m)
    hit_rate_3m = (sum(1 for value in forward_3m if value > 0) / len(forward_3m)) * 100
    avg_drawdown = sum(drawdowns) / len(drawdowns) if drawdowns else None
    confidence = equity_impact_confidence(len(sample), forward_3m, str(current_signal.get("confidence") or ""))
    tone = "positive" if median_3m > 0.5 and hit_rate_3m >= 55 else "negative" if median_3m < -0.5 and hit_rate_3m <= 45 else "mixed"
    return {
        "available": True,
        "proxy": "S&P 500 price-index proxy for SPY",
        "basis": "同类宏观评分水平 + 3M评分变化",
        "levelBucket": current_level,
        "changeBucket": current_change,
        "sampleSize": len(sample),
        "forward1mMedian": round(median(forward_1m), 2) if forward_1m else None,
        "forward3mMedian": round(median_3m, 2),
        "forward6mMedian": round(median(forward_6m), 2) if forward_6m else None,
        "hitRate3m": round(hit_rate_3m),
        "avgMaxDrawdown3m": round(avg_drawdown, 2) if avg_drawdown is not None else None,
        "confidence": confidence["key"],
        "confidenceLabel": confidence["label"],
        "tone": tone,
        "summary": (
            f"历史同类环境下,S&P 500价格指数代理SPY未来3M中位回报{median_3m:+.2f}%,"
            f"胜率{hit_rate_3m:.0f}%,样本{len(sample)}; 仅为历史统计,不构成方向承诺。"
        ),
    }


def numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = optional_float(row.get(key))
        if value is not None:
            values.append(value)
    return values


def investment_view_confidence_fields(conclusion_audit: dict[str, Any] | None) -> dict[str, str]:
    confidence = conclusion_audit.get("confidence") if isinstance(conclusion_audit, dict) else {}
    confidence = confidence if isinstance(confidence, dict) else {}
    level = str(confidence.get("level") or "medium")
    if level not in {"high", "medium", "low"}:
        level = "medium"
    label = {"high": "高可信", "medium": "中等可信", "low": "低可信"}[level]
    evidence_quality = optional_float(confidence.get("evidenceQuality"))
    proxy_share = optional_float(confidence.get("proxyContributionShare"))
    concentration = optional_float(confidence.get("concentration"))
    note_parts: list[str] = []
    if evidence_quality is not None:
        note_parts.append(f"证据质量 {evidence_quality:.2f}")
    if proxy_share is not None:
        note_parts.append(f"代理/模型占比 {proxy_share:.0%}")
    if concentration is not None:
        note_parts.append(f"单因子集中度 {concentration:.0%}")
    recommendation = conclusion_audit.get("weightRecommendation") if isinstance(conclusion_audit, dict) else None
    if isinstance(recommendation, str) and recommendation:
        note_parts.append(recommendation)
    return {
        "confidenceLevel": level,
        "confidenceLabel": label,
        "confidenceNote": "; ".join(note_parts) if note_parts else "结论审计暂无异常。",
    }
