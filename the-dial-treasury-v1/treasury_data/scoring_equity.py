"""Equity short-term risk domain extracted from build_dashboard.py (behavior-unchanged,
2026-06-19 全面重构 Phase 1). 0-100 short-horizon equity risk index from replayable OHLCV factors
+ backtest/calibration. Depends on lower layers + signal_validation.SortedSeries.
Re-exported via `from .scoring_equity import *`."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from .sources import CalendarEvent, MarketDailyBar, OptionOpenInterestSnapshot, SeriesPoint, TimeSeries
from .dashboard_core import *  # noqa: F401,F403
from .series_math import *  # noqa: F401,F403
from .signal_validation import SortedSeries


EQUITY_RISK_SYMBOLS: dict[str, str] = {
    "SPY": "etf",
    "QQQ": "etf",
    "SMH": "etf",
    "XLK": "etf",
    "TLT": "etf",
    "RSP": "etf",
    "IWM": "etf",
    "XLV": "etf",
    "XLU": "etf",
    "XLY": "etf",
    "XLP": "etf",
    "NVDA": "stocks",
    "AVGO": "stocks",
    "AMD": "stocks",
    "TSLA": "stocks",
    "META": "stocks",
    "MSFT": "stocks",
    "AAPL": "stocks",
    "AMZN": "stocks",
    "GOOGL": "stocks",
}


EQUITY_RISK_CORE_SYMBOLS = {"SPY", "QQQ", "SMH", "XLK", "TLT", "RSP", "IWM"}


EQUITY_RISK_HOT_STOCKS = ["NVDA", "AVGO", "AMD", "TSLA", "META", "MSFT", "AAPL", "AMZN", "GOOGL"]


# 2026-06-16 评审结论: 这三项(optionOI=0/audit-only, eventRisk 0.01, macroOverlay 0.03)并非"冗余/噪声",
# 而是OOS校准时就刻意保留的低权重"上下文"项, 且高风险regime边界(score>=75)是在含这些项的标度上经OOS审计
# 锚定的。实测将其归零会把4个"无催化确认"的良性情景推过75(误报回归), 故【保留原权重】, 不在本次精简中动它们;
# 真正的去噪在宏观综合分(去冗余簇c1/c2/c3 + effr_iorb/kre_spy/high_beta噪声)。如需移除须重跑equity OOS校准。
EQUITY_RISK_COMPONENT_WEIGHTS: dict[str, float] = {
    "volTargetPressure": 0.22,
    "qqqTltRotation": 0.14,
    "marketFlow": 0.22,
    "sectorRotation": 0.06,
    "hotStockReversal": 0.18,
    "turnover": 0.14,
    "macroOverlay": 0.03,
    "eventRisk": 0.01,
    "optionOI": 0.00,
}


def build_equity_short_term_risk_index(
    *,
    market_bars: dict[str, list[MarketDailyBar]] | None = None,
    macro_liquidity_equity: dict[str, Any] | None = None,
    spy_early_warning: dict[str, Any] | None = None,
    calendar_events: list[CalendarEvent] | None = None,
    option_open_interest: OptionOpenInterestSnapshot | None = None,
) -> dict[str, Any]:
    bars_by_symbol = normalize_market_bars(market_bars or {})
    spy_bars = bars_by_symbol.get("SPY", [])
    if len(spy_bars) < 20:
        return unavailable_equity_short_term_risk("缺少SPY日线OHLCV历史,暂不能生成短期股市风险指标。")
    target, shock = choose_equity_risk_signal_date(spy_bars)
    signal = equity_short_term_signal_at(
        bars_by_symbol,
        target,
        macro_liquidity_equity=macro_liquidity_equity or {},
        spy_early_warning=spy_early_warning or {},
        calendar_events=calendar_events or [],
        option_open_interest=option_open_interest,
    )
    if not signal.get("available"):
        return signal
    trend = build_equity_short_term_risk_trend(
        bars_by_symbol,
        macro_liquidity_equity=macro_liquidity_equity or {},
        spy_early_warning=spy_early_warning or {},
        calendar_events=calendar_events or [],
        option_open_interest=option_open_interest,
    )
    backtest = build_equity_short_term_risk_backtest(trend.get("points", []), spy_bars)
    next_shock = equity_next_session_shock(spy_bars, target)
    signal.update(
        {
            "title": "短期股市风险预警",
            "trend": trend,
            "backtest": backtest,
            "weightCalibration": equity_weight_calibration_summary(
                signal.get("components", []) if isinstance(signal.get("components"), list) else [],
                backtest.get("componentDiagnostics", []) if isinstance(backtest.get("componentDiagnostics"), list) else [],
            ),
            "nextSessionShock": next_shock,
            "lookAheadGuard": {
                "dataThrough": target.isoformat(),
                "scoreInputs": "Only same-day or earlier OHLCV, official event calendar, existing macro factors, and option OI snapshots dated on/before the signal date are scored.",
                "auditOnly": "nextSessionShock is shown to audit the 2026-06-04 pre-close signal and is not used in the score.",
            },
            "dataCoverage": equity_risk_data_coverage(bars_by_symbol, option_open_interest, target),
        }
    )
    if shock:
        signal["detectedPostSignalShock"] = {
            "date": shock.date.isoformat(),
            "returnPct": round(100 * one_day_return(spy_bars, shock.date), 2),
            "note": "latest SPY bar is a material next-session drawdown, so the panel highlights the prior-session warning state.",
        }
    return signal


def unavailable_equity_short_term_risk(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "title": "短期股市风险预警",
        "score": None,
        "baseScore": None,
        "regime": "Unavailable",
        "regimeCn": "不可用",
        "asOf": "",
        "summary": reason,
        "allocation": {"stance": "等待", "equityExposure": "不调整", "hedgeAction": "等待日线市场结构数据"},
        "components": [],
        "drivers": [],
        "trend": {"available": False, "points": [], "summary": reason},
        "backtest": {
            "available": False,
            "summary": reason,
            "sampleSize": 0,
            "scoreBuckets": [],
            "thresholdTests": [],
            "horizonTests": [],
            "tieredThresholdTests": [],
            "calibrationGrid": [],
            "recommendedCautionThreshold": {},
            "precisionThresholdTests": [],
            "highPrecisionThresholdTest": {},
            "componentDiagnostics": [],
            "preferredThresholdTest": {},
            "alertClusterTest": {},
            "regressionTests": [],
            "worstWindows": [],
            "alertWindows": [],
        },
        "weightCalibration": {"available": False, "summary": reason, "rows": []},
        "lookAheadGuard": {},
        "dataCoverage": [],
        "nextSessionShock": {},
    }


def normalize_market_bars(market_bars: dict[str, list[MarketDailyBar]]) -> dict[str, list[MarketDailyBar]]:
    normalized: dict[str, list[MarketDailyBar]] = {}
    for symbol, bars in market_bars.items():
        clean = [
            bar for bar in bars
            if isinstance(bar, MarketDailyBar)
            and all(math.isfinite(float(value)) and float(value) > 0 for value in (bar.open, bar.high, bar.low, bar.close))
        ]
        if not clean:
            continue
        by_date = {bar.date: bar for bar in clean}
        normalized[str(symbol).upper()] = [by_date[day] for day in sorted(by_date)]
    return normalized


def choose_equity_risk_signal_date(spy_bars: list[MarketDailyBar]) -> tuple[date, MarketDailyBar | None]:
    latest = spy_bars[-1]
    latest_return = one_day_return(spy_bars, latest.date)
    if latest_return <= -0.02 and len(spy_bars) >= 2:
        return spy_bars[-2].date, latest
    return latest.date, None


def equity_short_term_signal_at(
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    target: date,
    *,
    macro_liquidity_equity: dict[str, Any],
    spy_early_warning: dict[str, Any],
    calendar_events: list[CalendarEvent],
    option_open_interest: OptionOpenInterestSnapshot | None,
    include_macro_overlay: bool = True,
) -> dict[str, Any]:
    components = [
        equity_vol_target_pressure_component(bars_by_symbol, target, weight=EQUITY_RISK_COMPONENT_WEIGHTS["volTargetPressure"]),
        equity_qqq_tlt_rotation_component(bars_by_symbol, target, weight=EQUITY_RISK_COMPONENT_WEIGHTS["qqqTltRotation"]),
        equity_market_flow_component(bars_by_symbol, target, weight=EQUITY_RISK_COMPONENT_WEIGHTS["marketFlow"]),
        equity_sector_rotation_component(bars_by_symbol, target, weight=EQUITY_RISK_COMPONENT_WEIGHTS["sectorRotation"]),
        equity_hot_stock_reversal_component(bars_by_symbol, target, weight=EQUITY_RISK_COMPONENT_WEIGHTS["hotStockReversal"]),
        equity_turnover_component(bars_by_symbol, target, weight=EQUITY_RISK_COMPONENT_WEIGHTS["turnover"]),
        equity_event_risk_component(bars_by_symbol, target, calendar_events, weight=EQUITY_RISK_COMPONENT_WEIGHTS["eventRisk"]),
        equity_option_oi_component(option_open_interest, target, weight=EQUITY_RISK_COMPONENT_WEIGHTS["optionOI"]),
    ]
    if include_macro_overlay:
        components.insert(
            6,
            equity_macro_overlay_component(macro_liquidity_equity, spy_early_warning, target, weight=EQUITY_RISK_COMPONENT_WEIGHTS["macroOverlay"]),
        )
    components = attach_equity_factor_evidence(
        components,
        bars_by_symbol=bars_by_symbol,
        target=target,
        option_open_interest=option_open_interest,
    )
    observed = [
        component for component in components
        if component.get("available")
        and component.get("scoreUse") == "scored"
        and optional_float(component.get("score")) is not None
    ]
    if len(observed) < 3:
        return unavailable_equity_short_term_risk("可用短周期股市风险分项不足。")
    weight_total = sum(float(component["weight"]) for component in observed)
    base_score = sum(float(component["score"]) * float(component["weight"]) for component in observed) / weight_total
    amplifier = equity_convexity_amplifier(observed)
    dampener = equity_noise_dampener(observed)
    score_floor = equity_convexity_score_floor(observed)
    score = bounded_score(max(base_score + amplifier + dampener, score_floor))
    allocation = equity_short_term_risk_allocation(score)
    drivers = equity_short_term_risk_drivers(observed)
    spy_bar = bar_at_or_before(bars_by_symbol.get("SPY", []), target)
    summary = equity_short_term_risk_summary(score, allocation, drivers, target)
    source_quality = equity_source_quality_summary(components, target)
    factor_evidence = equity_factor_evidence_list(components)
    forward_catalyst_risk = equity_forward_catalyst_risk(components)
    return {
        "available": True,
        "score": round(score, 1),
        "baseScore": round(base_score, 1),
        "regime": allocation["regime"],
        "regimeCn": allocation["regimeCn"],
        "asOf": target.isoformat(),
        "method": "0-100 short-horizon equity risk index from replayable OHLCV factors: Parkinson multi-scale volatility pressure, QQQ/TLT rotation, sector/leader rotation, hot-stock reversal, market-flow structure, and turnover confirmation. Macro and event inputs are low-weight context; option OI is audit-only unless archived same-date history is available. Higher means greater 1-15 trading-day drawdown risk.",
        "summary": summary,
        "allocation": allocation,
        "components": components,
        "drivers": drivers,
        "factorEvidence": factor_evidence,
        "sourceQuality": source_quality,
        "forwardCatalystRisk": forward_catalyst_risk,
        "marketSnapshot": equity_market_snapshot(bars_by_symbol, target, spy_bar),
    }


def equity_component_scores_payload(components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for component in components:
        key = str(component.get("key") or "")
        score = optional_float(component.get("score"))
        if not key or score is None or component.get("scoreUse") != "scored":
            continue
        payload[key] = {
            "label": str(component.get("label") or key),
            "score": round(bounded_score(score), 1),
            "weight": round(float(component.get("weight") or 0.0), 4),
            "sourceQuality": str(component.get("sourceQuality") or ""),
            "historicalReplay": bool(component.get("historicalReplay")),
        }
    return payload


def equity_vol_target_pressure_component(bars_by_symbol: dict[str, list[MarketDailyBar]], target: date, *, weight: float) -> dict[str, Any]:
    qqq_bars = bars_by_symbol.get("QQQ", [])
    spy_bars = bars_by_symbol.get("SPY", [])
    qqq_vol_22 = annualized_parkinson_vol(qqq_bars, target, 22)
    spy_vol_22 = annualized_parkinson_vol(spy_bars, target, 22)
    if qqq_vol_22 is None or spy_vol_22 is None:
        return unavailable_equity_component("volTargetPressure", "多尺度波动目标压力", weight, "QQQ/SPY 22日高低价波动样本不足")
    qqq_vol_3 = annualized_parkinson_vol(qqq_bars, target, 3)
    qqq_vol_5 = annualized_parkinson_vol(qqq_bars, target, 5)
    spy_vol_3 = annualized_parkinson_vol(spy_bars, target, 3)
    spy_vol_5 = annualized_parkinson_vol(spy_bars, target, 5)
    qqq_target = adaptive_parkinson_target_vol(qqq_bars, target) or 0.12
    spy_target = adaptive_parkinson_target_vol(spy_bars, target) or 0.12
    qqq_pressure = qqq_vol_22 / max(qqq_target, 1e-6)
    spy_pressure = spy_vol_22 / max(spy_target, 1e-6)
    burst_values = [
        recent / baseline
        for recent, baseline in ((qqq_vol_3, qqq_vol_22), (qqq_vol_5, qqq_vol_22), (spy_vol_3, spy_vol_22), (spy_vol_5, spy_vol_22))
        if recent is not None and baseline is not None and baseline > 0
    ]
    burst_ratio = max(burst_values) if burst_values else 1.0
    pressure_score = 0.58 * risk_linear(qqq_pressure, 0.95, 1.85) + 0.42 * risk_linear(spy_pressure, 0.95, 1.70)
    burst_score = risk_linear(burst_ratio, 1.08, 1.75)
    qqq_day = one_day_return(qqq_bars, target)
    price_confirm_boost = 8.0 if qqq_day is not None and qqq_day < 0 and burst_ratio >= 1.18 else 0.0
    score = bounded_score(0.62 * pressure_score + 0.38 * burst_score + price_confirm_boost)
    drivers = []
    if qqq_pressure >= 1.20 or spy_pressure >= 1.20 or burst_ratio >= 1.25:
        drivers.append(
            equity_driver(
                "parkinsonVolBurst",
                "高低价波动多尺度扩张",
                f"QQQ 22D vol {format_optional_percent_value(pct_metric(qqq_vol_22))} / target {format_optional_percent_value(pct_metric(qqq_target))}; burst {burst_ratio:.2f}x",
                score,
            )
        )
    if qqq_pressure >= 1.45:
        drivers.append(
            equity_driver(
                "volTargetDeRisk",
                "目标波动要求降风险资产",
                f"QQQ volatility pressure {qqq_pressure:.2f}x",
                score,
            )
        )
    return equity_component(
        "volTargetPressure",
        "多尺度波动目标压力",
        weight,
        score,
        f"QQQ 22D Parkinson vol {format_optional_percent_value(pct_metric(qqq_vol_22))} vs target {format_optional_percent_value(pct_metric(qqq_target))}; 3/5/22D burst {burst_ratio:.2f}x",
        drivers=drivers,
        metrics={
            "qqqParkinsonVol3d": pct_metric(qqq_vol_3),
            "qqqParkinsonVol5d": pct_metric(qqq_vol_5),
            "qqqParkinsonVol22d": pct_metric(qqq_vol_22),
            "spyParkinsonVol22d": pct_metric(spy_vol_22),
            "qqqTargetVol": pct_metric(qqq_target),
            "spyTargetVol": pct_metric(spy_target),
            "qqqVolPressure": round(qqq_pressure, 3),
            "spyVolPressure": round(spy_pressure, 3),
            "multiScaleBurstRatio": round(burst_ratio, 3),
        },
    )


def equity_qqq_tlt_rotation_component(bars_by_symbol: dict[str, list[MarketDailyBar]], target: date, *, weight: float) -> dict[str, Any]:
    qqq_bars = bars_by_symbol.get("QQQ", [])
    tlt_bars = bars_by_symbol.get("TLT", [])
    qqq_20 = trailing_return(qqq_bars, target, 20)
    tlt_20 = trailing_return(tlt_bars, target, 20)
    qqq_5 = trailing_return(qqq_bars, target, 5)
    tlt_5 = trailing_return(tlt_bars, target, 5)
    qqq_63 = trailing_return(qqq_bars, target, 63)
    tlt_63 = trailing_return(tlt_bars, target, 63)
    qqq_day = one_day_return(qqq_bars, target)
    tlt_day = one_day_return(tlt_bars, target)
    if qqq_20 is None or tlt_20 is None or qqq_day is None or tlt_day is None:
        return unavailable_equity_component("qqqTltRotation", "QQQ/TLT风险切换", weight, "QQQ/TLT日线样本不足")
    risk_off_gap = tlt_20 - qqq_20
    short_risk_off_gap = (tlt_5 - qqq_5) if qqq_5 is not None and tlt_5 is not None else risk_off_gap
    risk_on_gap = (qqq_63 - tlt_63) if qqq_63 is not None and tlt_63 is not None else None
    risk_off_score = risk_linear(risk_off_gap, 0.015, 0.10)
    short_rotation_score = risk_linear(short_risk_off_gap, 0.008, 0.065)
    crowding_score = risk_linear(risk_on_gap, 0.12, 0.32) if risk_on_gap is not None else 45.0
    hedge_failure_score = 0.0
    if qqq_day <= -0.004 and tlt_day <= 0:
        hedge_failure_score = 82.0 + 8.0 * min(1.0, abs(qqq_day) / 0.02)
    crowded_rollover_score = 0.0
    if risk_on_gap is not None and risk_on_gap >= 0.18 and qqq_day < 0:
        crowded_rollover_score = 76.0 + 10.0 * min(1.0, abs(qqq_day) / 0.012)
        if tlt_day <= 0:
            crowded_rollover_score += 4.0
    score = bounded_score(max(
        0.30 * risk_off_score + 0.18 * short_rotation_score + 0.52 * crowding_score,
        hedge_failure_score,
        crowded_rollover_score,
    ))
    drivers = []
    if hedge_failure_score >= 75:
        drivers.append(equity_driver("tltHedgeFailure", "QQQ下跌且TLT未提供保护", f"QQQ {format_signed_pct(qqq_day)}, TLT {format_signed_pct(tlt_day)}", score))
    if crowded_rollover_score >= 75:
        drivers.append(equity_driver("qqqTltCrowdedRollover", "QQQ相对TLT拥挤后回落", f"63D QQQ-TLT {format_signed_pct(risk_on_gap)}, QQQ day {format_signed_pct(qqq_day)}", score))
    if risk_off_gap >= 0.035:
        drivers.append(equity_driver("qqqTltRiskOff", "QQQ/TLT相对趋势转弱", f"20D TLT-QQQ {format_signed_pct(risk_off_gap)}", score))
    if risk_on_gap is not None and risk_on_gap >= 0.18:
        drivers.append(equity_driver("qqqTltCrowding", "QQQ相对TLT拥挤", f"63D QQQ-TLT {format_signed_pct(risk_on_gap)}", score))
    return equity_component(
        "qqqTltRotation",
        "QQQ/TLT风险切换",
        weight,
        score,
        f"20D TLT-QQQ {format_signed_pct(risk_off_gap)}; 5D {format_signed_pct(short_risk_off_gap)}; 当日QQQ/TLT {format_signed_pct(qqq_day)} / {format_signed_pct(tlt_day)}",
        drivers=drivers,
        metrics={
            "qqq20dReturn": pct_metric(qqq_20),
            "tlt20dReturn": pct_metric(tlt_20),
            "qqqTlt20dGap": pct_metric(-risk_off_gap),
            "tltQqq20dGap": pct_metric(risk_off_gap),
            "tltQqq5dGap": pct_metric(short_risk_off_gap),
            "qqqTlt63dGap": pct_metric(risk_on_gap),
            "qqqDayReturn": pct_metric(qqq_day),
            "tltDayReturn": pct_metric(tlt_day),
            "hedgeFailureScore": round(hedge_failure_score, 1),
            "crowdedRolloverScore": round(crowded_rollover_score, 1),
        },
    )


def equity_market_flow_component(bars_by_symbol: dict[str, list[MarketDailyBar]], target: date, *, weight: float) -> dict[str, Any]:
    spy_63 = trailing_return(bars_by_symbol.get("SPY", []), target, 63)
    spy_20 = trailing_return(bars_by_symbol.get("SPY", []), target, 20)
    qqq_63 = trailing_return(bars_by_symbol.get("QQQ", []), target, 63)
    smh_63 = trailing_return(bars_by_symbol.get("SMH", []), target, 63)
    values = [value for value in (spy_63, qqq_63, smh_63) if value is not None]
    if not values:
        return unavailable_equity_component("marketFlow", "股市资金/趋势", weight, "SPY/QQQ/SMH日线不足")
    spy_score = risk_linear(spy_63, 0.04, 0.12) if spy_63 is not None else 50.0
    qqq_score = risk_linear(qqq_63, 0.08, 0.22) if qqq_63 is not None else 50.0
    smh_score = risk_linear(smh_63, 0.15, 0.45) if smh_63 is not None else 50.0
    rally_extension_score = 0.50 * spy_score + 0.20 * qqq_score + 0.30 * smh_score
    downtrend_profile = equity_downtrend_fragility_profile(bars_by_symbol, target)
    downtrend_score = optional_float(downtrend_profile.get("downtrendFragilityScore")) or 0.0
    score = max(rally_extension_score, downtrend_score)
    drivers = []
    if spy_63 is not None and spy_63 >= 0.08:
        drivers.append(equity_driver("rallyExtension", "SPY三个月快速反弹", f"SPY 63D {format_signed_pct(spy_63)}", score))
    if smh_63 is not None and smh_63 >= 0.25:
        drivers.append(equity_driver("leaderConcentration", "半导体涨幅拥挤", f"SMH 63D {format_signed_pct(smh_63)}", score))
    if downtrend_score >= 75:
        drivers.append(
            equity_driver(
                "downtrendContinuation",
                "下跌扩散/趋势破位",
                f"SPY 20D高点回撤 {format_optional_percent_value(downtrend_profile.get('spyDrawdown20d'))}, 防御相对周期 {format_optional_percent_value(downtrend_profile.get('defensiveGap20d'))}",
                downtrend_score,
            )
        )
    relief_trap_score = optional_float(downtrend_profile.get("downtrendReliefRallyTrapScore")) or 0.0
    if relief_trap_score >= 60:
        volume_text = "--"
        volume_value = optional_float(downtrend_profile.get("spyVolumePercentile"))
        if volume_value is not None:
            volume_text = f"{volume_value:.0f}"
        drivers.append(
            equity_driver(
                "reliefRallyTrap",
                "破位后弱反弹",
                (
                    f"20D高低点压力 {format_optional_percent_value(downtrend_profile.get('recentStressDrawdown20d'))}, "
                    f"SPY 20D高点回撤 {format_optional_percent_value(downtrend_profile.get('spyDrawdown20d'))}, "
                    f"成交分位 p{volume_text}"
                ),
                relief_trap_score,
            )
        )
    detail = f"SPY 63D {format_optional_pct(spy_63)}, 20D {format_optional_pct(spy_20)}; QQQ 63D {format_optional_pct(qqq_63)}, SMH 63D {format_optional_pct(smh_63)}"
    if downtrend_score >= 50:
        detail += f"; 下跌扩散 {downtrend_score:.0f}"
    return equity_component(
        "marketFlow",
        "股市资金/趋势",
        weight,
        score,
        detail,
        drivers=drivers,
        metrics={
            "spy63dReturn": pct_metric(spy_63),
            "spy20dReturn": pct_metric(spy_20),
            "qqq63dReturn": pct_metric(qqq_63),
            "smh63dReturn": pct_metric(smh_63),
            **downtrend_profile,
        },
    )


def equity_downtrend_fragility_profile(bars_by_symbol: dict[str, list[MarketDailyBar]], target: date) -> dict[str, Any]:
    spy_dd20 = drawdown_from_recent_high(bars_by_symbol.get("SPY", []), target, 20)
    spy_dd63 = drawdown_from_recent_high(bars_by_symbol.get("SPY", []), target, 63)
    spy_ma20_gap = moving_average_gap(bars_by_symbol.get("SPY", []), target, 20)
    leader20 = average_optional(
        trailing_return(bars_by_symbol.get(symbol, []), target, 20)
        for symbol in ("QQQ", "SMH", "XLK")
    )
    cyclical20 = average_optional(
        trailing_return(bars_by_symbol.get(symbol, []), target, 20)
        for symbol in ("QQQ", "SMH", "XLY", "IWM")
    )
    defensive20 = average_optional(
        trailing_return(bars_by_symbol.get(symbol, []), target, 20)
        for symbol in ("XLV", "XLU", "XLP")
    )
    defensive_gap = defensive20 - cyclical20 if defensive20 is not None and cyclical20 is not None else None
    spy_day = one_day_return(bars_by_symbol.get("SPY", []), target)
    spy_bar = bar_at_or_before(bars_by_symbol.get("SPY", []), target)
    close_location = close_location_value(spy_bar) if spy_bar else None
    volume_pct = volume_percentile_at(bars_by_symbol.get("SPY", []), target, window=60)
    recent_stress_dd20 = high_to_low_drawdown_in_window(bars_by_symbol.get("SPY", []), target, 20)
    rebound_from_stress_low10 = rebound_from_recent_low(bars_by_symbol.get("SPY", []), target, 10)
    breakdown_score = max(
        risk_linear(-(spy_dd20 or 0.0), 0.025, 0.085),
        risk_linear(-(spy_dd63 or 0.0), 0.045, 0.115),
        risk_linear(-(spy_ma20_gap or 0.0), 0.004, 0.045),
    )
    leader_score = risk_linear(-(leader20 or 0.0), 0.02, 0.12)
    defensive_score = risk_linear(defensive_gap, 0.02, 0.10) if defensive_gap is not None else 50.0
    failed_rebound_score = 0.0
    if spy_day is not None and spy_day >= 0 and breakdown_score >= 45:
        failed_rebound_score = 68.0
        if close_location is not None and close_location >= 0.65:
            failed_rebound_score += 8.0
        if volume_pct is not None and volume_pct <= 55:
            failed_rebound_score += 8.0
    sell_pressure_score = 0.0
    if spy_day is not None and spy_day <= -0.008 and breakdown_score >= 35:
        sell_pressure_score = 78.0
        if close_location is not None and close_location <= 0.35:
            sell_pressure_score += 10.0
    relief_rally_trap_score = 0.0
    if (
        spy_day is not None
        and spy_day >= 0
        and recent_stress_dd20 is not None
        and recent_stress_dd20 <= -0.065
        and spy_dd20 is not None
        and spy_dd20 <= -0.025
        and (
            (leader20 is not None and leader20 <= -0.025)
            or (defensive_gap is not None and defensive_gap >= 0.025)
        )
    ):
        relief_rally_trap_score = 68.0 + 0.15 * risk_linear(-recent_stress_dd20, 0.065, 0.120)
        if rebound_from_stress_low10 is not None and rebound_from_stress_low10 >= 0.025:
            relief_rally_trap_score += 6.0
        if volume_pct is not None and volume_pct <= 50:
            relief_rally_trap_score += 8.0
        elif volume_pct is not None and volume_pct <= 65:
            relief_rally_trap_score += 4.0
        if close_location is not None and close_location >= 0.60:
            relief_rally_trap_score += 4.0
        if defensive_gap is not None and defensive_gap >= 0.04:
            relief_rally_trap_score += 4.0
    blended_score = (
        0.45 * breakdown_score
        + 0.25 * leader_score
        + 0.20 * defensive_score
        + 0.10 * max(failed_rebound_score, sell_pressure_score, relief_rally_trap_score)
    )
    score = bounded_score(max(blended_score, failed_rebound_score, sell_pressure_score, relief_rally_trap_score))
    return {
        "downtrendFragilityScore": round(score, 1),
        "spyDrawdown20d": pct_metric(spy_dd20),
        "spyDrawdown63d": pct_metric(spy_dd63),
        "spyMa20Gap": pct_metric(spy_ma20_gap),
        "leader20dReturn": pct_metric(leader20),
        "defensiveGap20d": pct_metric(defensive_gap),
        "downtrendBreakdownScore": round(breakdown_score, 1),
        "downtrendLeaderScore": round(leader_score, 1),
        "downtrendDefensiveScore": round(defensive_score, 1),
        "downtrendFailedReboundScore": round(failed_rebound_score, 1),
        "downtrendSellPressureScore": round(sell_pressure_score, 1),
        "downtrendReliefRallyTrapScore": round(bounded_score(relief_rally_trap_score), 1),
        "recentStressDrawdown20d": pct_metric(recent_stress_dd20),
        "reboundFromStressLow10d": pct_metric(rebound_from_stress_low10),
        "spyVolumePercentile": round(volume_pct, 1) if volume_pct is not None else None,
    }


def equity_sector_rotation_component(bars_by_symbol: dict[str, list[MarketDailyBar]], target: date, *, weight: float) -> dict[str, Any]:
    spy_day = one_day_return(bars_by_symbol.get("SPY", []), target)
    qqq_day = one_day_return(bars_by_symbol.get("QQQ", []), target)
    smh_day = one_day_return(bars_by_symbol.get("SMH", []), target)
    xlk_day = one_day_return(bars_by_symbol.get("XLK", []), target)
    rsp_63 = trailing_return(bars_by_symbol.get("RSP", []), target, 63)
    spy_63 = trailing_return(bars_by_symbol.get("SPY", []), target, 63)
    smh_63 = trailing_return(bars_by_symbol.get("SMH", []), target, 63)
    leaders = [value for value in (qqq_day, smh_day, xlk_day) if value is not None]
    if spy_day is None or not leaders:
        return unavailable_equity_component("sectorRotation", "板块轮动断裂", weight, "QQQ/SMH/XLK或SPY日线不足")
    avg_leader_underperf = sum(value - spy_day for value in leaders) / len(leaders)
    underperf_score = risk_linear(-avg_leader_underperf, 0.002, 0.015)
    breadth_gap = None
    if spy_63 is not None and rsp_63 is not None:
        breadth_gap = spy_63 - rsp_63
    concentration_gap = None
    if smh_63 is not None and rsp_63 is not None:
        concentration_gap = smh_63 - rsp_63
    breadth_score = max(
        risk_linear(breadth_gap, 0.03, 0.10) if breadth_gap is not None else 50.0,
        risk_linear(concentration_gap, 0.12, 0.35) if concentration_gap is not None else 50.0,
    )
    score = 0.55 * underperf_score + 0.45 * breadth_score
    drivers = []
    if avg_leader_underperf <= -0.006:
        drivers.append(equity_driver("lateRotationBreak", "高热板块当日跑输", f"QQQ/SMH/XLK vs SPY {format_signed_pct(avg_leader_underperf)}", score))
    if concentration_gap is not None and concentration_gap >= 0.20:
        drivers.append(equity_driver("leaderConcentration", "半导体相对等权过热", f"SMH-RSP 63D {format_signed_pct(concentration_gap)}", score))
    return equity_component(
        "sectorRotation",
        "板块轮动断裂",
        weight,
        score,
        f"QQQ/SMH/XLK日内相对SPY {format_signed_pct(avg_leader_underperf)}; SMH-RSP 63D {format_optional_pct(concentration_gap)}",
        drivers=drivers,
        metrics={"leaderUnderperformance": pct_metric(avg_leader_underperf), "breadthGap": pct_metric(breadth_gap), "smhRspGap": pct_metric(concentration_gap)},
    )


def equity_hot_stock_reversal_component(bars_by_symbol: dict[str, list[MarketDailyBar]], target: date, *, weight: float) -> dict[str, Any]:
    observed = []
    hot_count = reversal_count = heavy_reversal_count = 0
    for symbol in EQUITY_RISK_HOT_STOCKS:
        bars = bars_by_symbol.get(symbol, [])
        bar = bar_at_or_before(bars, target)
        ret_63 = trailing_return(bars, target, 63)
        day_ret = one_day_return(bars, target)
        if bar is None or ret_63 is None or day_ret is None:
            continue
        high_gap = bar.close / bar.high - 1 if bar.high > 0 else 0.0
        close_location = close_location_value(bar)
        is_hot = ret_63 >= 0.15 or symbol in {"NVDA", "AVGO", "AMD", "TSLA"}
        is_reversal = is_hot and (day_ret <= -0.01 or high_gap <= -0.012 or close_location <= 0.35)
        is_heavy = is_hot and day_ret <= -0.03
        if is_hot:
            hot_count += 1
        if is_reversal:
            reversal_count += 1
        if is_heavy:
            heavy_reversal_count += 1
        observed.append({"symbol": symbol, "return63d": ret_63, "dayReturn": day_ret, "highGap": high_gap, "closeLocation": close_location, "hot": is_hot, "reversal": is_reversal})
    if not observed:
        return unavailable_equity_component("hotStockReversal", "热点股集体回落", weight, "热点股票日线不足")
    hot_share = hot_count / max(1, len(observed))
    raw_reversal_share = reversal_count / max(1, hot_count)
    small_sample_adjusted = hot_count < 3
    if small_sample_adjusted:
        shrink_weight = hot_count / 3
        reversal_share = 0.50 * (1 - shrink_weight) + raw_reversal_share * shrink_weight
        heavy_reversal_score = heavy_reversal_count * 10 * shrink_weight
    else:
        reversal_share = raw_reversal_share
        heavy_reversal_score = heavy_reversal_count * 10
    score = bounded_score(20 + risk_linear(hot_share, 0.25, 0.65) * 0.25 + risk_linear(reversal_share, 0.20, 0.55) * 0.45 + heavy_reversal_count * 10)
    if small_sample_adjusted:
        score = min(score, bounded_score(20 + risk_linear(hot_share, 0.25, 0.65) * 0.18 + risk_linear(reversal_share, 0.20, 0.55) * 0.32 + heavy_reversal_score))
    drivers = []
    if reversal_count >= 2:
        drivers.append(equity_driver("hotStockReversal", "热点股日内集体回落", f"{reversal_count}/{hot_count} hot names reversed", score))
    return equity_component(
        "hotStockReversal",
        "热点股集体回落",
        weight,
        score,
        f"{reversal_count}/{hot_count}只热点股出现收盘回落或当日下跌; 重挫 {heavy_reversal_count}只",
        drivers=drivers,
        metrics={
            "hotCount": hot_count,
            "reversalCount": reversal_count,
            "heavyReversalCount": heavy_reversal_count,
            "sampleSize": len(observed),
            "reversalShare": round(raw_reversal_share, 3),
            "adjustedReversalShare": round(reversal_share, 3),
            "smallSampleAdjusted": small_sample_adjusted,
        },
    )


def equity_turnover_component(bars_by_symbol: dict[str, list[MarketDailyBar]], target: date, *, weight: float) -> dict[str, Any]:
    spy_bars = bars_by_symbol.get("SPY", [])
    bar = bar_at_or_before(spy_bars, target)
    if bar is None:
        return unavailable_equity_component("turnover", "成交承接", weight, "SPY成交量缺失")
    volume_pct = volume_percentile_at(spy_bars, target, window=60)
    close_loc = close_location_value(bar)
    day_ret = one_day_return(spy_bars, target)
    spy_63 = trailing_return(spy_bars, target, 63)
    if volume_pct is None:
        return unavailable_equity_component("turnover", "成交承接", weight, "SPY成交量不可用")
    thin_breakout_strength = 0.0
    if close_loc >= 0.70 and (spy_63 or 0) >= 0.08:
        thin_breakout_strength = max(0.0, min(1.0, (48.0 - volume_pct) / 6.0))
    thin_breakout = thin_breakout_strength > 0
    distribution_strength = 0.0
    if close_loc <= 0.40 or (day_ret is not None and day_ret < 0):
        distribution_strength = max(0.0, min(1.0, (volume_pct - 70.0) / 10.0))
    distribution = distribution_strength > 0
    if thin_breakout:
        score = 25.0 + 53.0 * thin_breakout_strength
    else:
        score = max(25.0, risk_linear(0.5 - close_loc, 0.0, 0.35))
    if distribution:
        # Ramp from the neutral reading toward 84 as volume percentile climbs 70→80,
        # so a one-percentile move no longer flips the component by 30+ points.
        score = max(score, score + (84.0 - score) * distribution_strength)
    drivers = []
    if thin_breakout:
        drivers.append(equity_driver("thinBreakout", "缩量冲高承接偏弱", f"SPY volume p{volume_pct:.0f}, close location {close_loc:.2f}", score))
    if distribution:
        drivers.append(equity_driver("distributionVolume", "放量回落", f"SPY volume p{volume_pct:.0f}", score))
    return equity_component(
        "turnover",
        "成交承接",
        weight,
        score,
        f"SPY成交量历史分位 p{volume_pct:.0f}; 收盘位置 {close_loc:.2f}",
        drivers=drivers,
        metrics={"volumePercentile": round(volume_pct, 1), "closeLocation": round(close_loc, 3), "spyDayReturn": pct_metric(day_ret), "thinBreakoutStrength": round(thin_breakout_strength, 3), "distributionStrength": round(distribution_strength, 3)},
    )


def equity_event_risk_component(
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    target: date,
    calendar_events: list[CalendarEvent],
    *,
    weight: float,
) -> dict[str, Any]:
    forward_window_days = 5
    upcoming = [
        event for event in calendar_events
        if target < event.date <= target + timedelta(days=forward_window_days)
        and (event.importance == "高" or event.title.startswith(("BLS ", "FOMC ", "BEA ")))
    ]
    spy_63 = trailing_return(bars_by_symbol.get("SPY", []), target, 63)
    smh_63 = trailing_return(bars_by_symbol.get("SMH", []), target, 63)
    if not upcoming:
        score = 30.0 if (spy_63 or 0) < 0.08 else 45.0
    else:
        event_base = 78.0 if any(event.title.startswith("BLS ") for event in upcoming) else 68.0
        extension_boost = 12.0 if (spy_63 or 0) >= 0.08 or (smh_63 or 0) >= 0.25 else 0.0
        score = bounded_score(event_base + extension_boost)
    drivers = []
    if upcoming:
        labels = ", ".join(event.title for event in upcoming[:2])
        drivers.append(equity_driver("eventRisk", "关键宏观事件前夜", labels, score))
    return equity_component(
        "eventRisk",
        "新闻/事件风险",
        weight,
        score,
        "未来1-5天高重要性事件: " + (", ".join(event.title for event in upcoming[:3]) if upcoming else "无"),
        drivers=drivers,
        metrics={
            "eventCount": len(upcoming),
            "windowDays": forward_window_days,
            "events": [
                {"date": event.date.isoformat(), "title": event.title, "source": event.source, "importance": event.importance}
                for event in upcoming[:5]
            ],
            "nextEventDate": upcoming[0].date.isoformat() if upcoming else None,
            "daysToNextEvent": (upcoming[0].date - target).days if upcoming else None,
            "knownBeforeSignal": True,
        },
    )


def equity_macro_overlay_component(
    macro_liquidity_equity: dict[str, Any],
    spy_early_warning: dict[str, Any],
    target: date,
    *,
    weight: float,
) -> dict[str, Any]:
    spy_score = optional_float(spy_early_warning.get("score"))
    current_signal = macro_liquidity_equity.get("currentSignal", {}) if isinstance(macro_liquidity_equity, dict) else {}
    score3m_change = optional_float(current_signal.get("score3mChange")) if isinstance(current_signal, dict) else None
    raw_score = spy_score if spy_score is not None else 45.0
    score = raw_score
    if score3m_change is not None and score3m_change > 6:
        score = max(score, 52.0)
    return equity_component(
        "macroOverlay",
        "已有宏观因子叠加",
        weight,
        score,
        f"SPY Early Warning {raw_score:.1f}; overlay {score:.1f}; 宏观评分3M变化 {format_optional_number(score3m_change)}",
        drivers=[],
        metrics={"spyEarlyWarning": round(raw_score, 1), "overlayScore": round(score, 1), "macroScore3mChange": score3m_change},
    )


def equity_option_oi_component(option_open_interest: OptionOpenInterestSnapshot | None, target: date, *, weight: float) -> dict[str, Any]:
    if option_open_interest is None:
        return unavailable_equity_component("optionOI", "期权OI趋势", weight, "未取得CBOE期权OI快照")
    if option_open_interest.as_of > target:
        component = unavailable_equity_component("optionOI", "期权OI趋势", weight, f"CBOE OI快照为{option_open_interest.as_of.isoformat()},晚于{target.isoformat()},不纳入前视保护评分")
        component["snapshot"] = option_oi_snapshot_payload(option_open_interest)
        return component
    ratio = option_open_interest.put_call_open_interest_ratio
    if ratio is None:
        return unavailable_equity_component("optionOI", "期权OI趋势", weight, "CBOE OI无法计算Put/Call比")
    score = risk_linear(ratio, 0.85, 1.35)
    drivers = [equity_driver("optionOiSkew", "SPY Put/Call OI偏防御", f"OI P/C {ratio:.2f}", score)] if ratio >= 1.15 else []
    component = equity_component(
        "optionOI",
        "期权OI趋势",
        weight,
        score,
        f"CBOE SPY Put/Call OI {ratio:.2f} as of {option_open_interest.as_of.isoformat()}",
        drivers=drivers,
        metrics={"putCallOpenInterestRatio": ratio, "putOpenInterest": round(option_open_interest.put_open_interest), "callOpenInterest": round(option_open_interest.call_open_interest)},
    )
    component["snapshot"] = option_oi_snapshot_payload(option_open_interest)
    return component


def equity_component(
    key: str,
    label: str,
    weight: float,
    score: float,
    detail: str,
    *,
    drivers: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    numeric = bounded_score(score)
    return {
        "key": key,
        "label": label,
        "weight": weight,
        "available": True,
        "score": round(numeric, 1),
        "tone": equity_risk_tone(numeric),
        "detail": detail,
        "drivers": drivers,
        "metrics": metrics,
    }


def unavailable_equity_component(key: str, label: str, weight: float, reason: str) -> dict[str, Any]:
    return {"key": key, "label": label, "weight": weight, "available": False, "score": None, "tone": "neutral", "detail": reason, "drivers": [], "metrics": {}}


def attach_equity_factor_evidence(
    components: list[dict[str, Any]],
    *,
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    target: date,
    option_open_interest: OptionOpenInterestSnapshot | None,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for component in components:
        evidence = equity_factor_evidence_for_component(
            component,
            bars_by_symbol=bars_by_symbol,
            target=target,
            option_open_interest=option_open_interest,
        )
        score_use = str(evidence.get("scoreUse") or "missing")
        enriched.append(
            {
                **component,
                "sourceQuality": str(evidence.get("sourceQuality") or "low"),
                "scoreUse": score_use,
                "historicalReplay": bool(evidence.get("historicalReplay")),
                "evidence": evidence,
            }
        )
    return enriched


def equity_factor_evidence_for_component(
    component: dict[str, Any],
    *,
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    target: date,
    option_open_interest: OptionOpenInterestSnapshot | None,
) -> dict[str, Any]:
    key = str(component.get("key") or "")
    available = component.get("available") is True and optional_float(component.get("score")) is not None
    if key == "volTargetPressure":
        coverage = equity_bar_evidence_coverage(("SPY", "QQQ"), bars_by_symbol, target)
        return equity_factor_evidence_payload(
            component,
            source="Nasdaq daily OHLCV: QQQ/SPY Parkinson high-low volatility",
            source_quality="high",
            historical_replay=True,
            score_use="scored" if available else "missing",
            coverage=coverage,
            timestamp_policy="Uses only high/low ranges dated on or before the signal date.",
            reason="Range-based volatility and adaptive target-vol pressure can be replayed from archived daily OHLCV bars.",
        )
    if key == "qqqTltRotation":
        coverage = equity_bar_evidence_coverage(("QQQ", "TLT"), bars_by_symbol, target)
        return equity_factor_evidence_payload(
            component,
            source="Nasdaq daily OHLCV: QQQ and TLT rotation",
            source_quality="high",
            historical_replay=True,
            score_use="scored" if available else "missing",
            coverage=coverage,
            timestamp_policy="Uses only QQQ/TLT bars dated on or before the signal date.",
            reason="QQQ/TLT relative returns and hedge-failure checks are replayable without future data.",
        )
    if key == "marketFlow":
        coverage = equity_bar_evidence_coverage(("SPY", "QQQ", "SMH"), bars_by_symbol, target)
        return equity_factor_evidence_payload(
            component,
            source="Nasdaq daily OHLCV: SPY, QQQ, SMH",
            source_quality="high",
            historical_replay=True,
            score_use="scored" if available else "missing",
            coverage=coverage,
            timestamp_policy="Uses bars dated on or before the signal date.",
            reason="Daily price/volume history can be replayed without future data.",
        )
    if key == "sectorRotation":
        coverage = equity_bar_evidence_coverage(("SPY", "QQQ", "SMH", "XLK", "RSP"), bars_by_symbol, target)
        return equity_factor_evidence_payload(
            component,
            source="Nasdaq daily OHLCV: sector and breadth ETFs",
            source_quality="high",
            historical_replay=True,
            score_use="scored" if available else "missing",
            coverage=coverage,
            timestamp_policy="Uses same-day or earlier ETF closes.",
            reason="Sector rotation is replayed from archived ETF bars.",
        )
    if key == "hotStockReversal":
        coverage = equity_bar_evidence_coverage(tuple(EQUITY_RISK_HOT_STOCKS), bars_by_symbol, target)
        return equity_factor_evidence_payload(
            component,
            source="Nasdaq daily OHLCV: hot-stock basket",
            source_quality="high",
            historical_replay=True,
            score_use="scored" if available else "missing",
            coverage=coverage,
            timestamp_policy="Uses same-day or earlier single-name bars.",
            reason="Collective reversal can be replayed from archived stock bars.",
        )
    if key == "turnover":
        coverage = equity_bar_evidence_coverage(("SPY",), bars_by_symbol, target)
        return equity_factor_evidence_payload(
            component,
            source="Nasdaq daily OHLCV: SPY volume and close location",
            source_quality="high",
            historical_replay=True,
            score_use="scored" if available else "missing",
            coverage=coverage,
            timestamp_policy="Uses SPY volume and OHLC dated on or before signal date.",
            reason="Turnover and close-location signals are replayable from daily bars.",
        )
    if key == "eventRisk":
        metrics = component.get("metrics") if isinstance(component.get("metrics"), dict) else {}
        return equity_factor_evidence_payload(
            component,
            source="Official macro release calendar",
            source_quality="medium",
            historical_replay=False,
            score_use="scored" if available else "missing",
            coverage={"start": "", "end": target.isoformat(), "observations": int(metrics.get("eventCount") or 0)},
            timestamp_policy="Scores only events known before the signal date and dated within the forward window.",
            reason="Forward calendar is decision-relevant, but long archived calendar coverage is partial in the free data set.",
        )
    if key == "macroOverlay":
        return equity_factor_evidence_payload(
            component,
            source="Existing macroLiquidityEquity and SPY Early Warning factors",
            source_quality="medium",
            historical_replay=False,
            score_use="scored" if available else "missing",
            coverage={"start": "", "end": target.isoformat(), "observations": 1 if available else 0},
            timestamp_policy="Uses already-generated macro and monthly equity-warning payload available at signal time.",
            reason="Macro overlay is bounded to a small weight because it mixes lower-frequency and partially replayed inputs.",
        )
    if key == "optionOI":
        snapshot_after_signal = bool(option_open_interest and option_open_interest.as_of > target)
        snapshot_available = bool(option_open_interest)
        reason = "No Cboe option OI snapshot was available."
        if snapshot_after_signal and option_open_interest:
            reason = f"Snapshot date {option_open_interest.as_of.isoformat()} is after signal date {target.isoformat()}."
        elif snapshot_available:
            reason = "Cboe option OI is a delayed current snapshot without archived history in this free-source pipeline."
        return equity_factor_evidence_payload(
            component,
            source="Cboe delayed option open-interest snapshot",
            source_quality="medium" if snapshot_available else "low",
            historical_replay=False,
            score_use="auditOnly" if snapshot_available else "missing",
            coverage={
                "start": option_open_interest.as_of.isoformat() if option_open_interest else "",
                "end": option_open_interest.as_of.isoformat() if option_open_interest else "",
                "observations": 1 if option_open_interest else 0,
            },
            timestamp_policy="Displayed as audit context unless an archived same-date OI feed is available.",
            reason=reason,
        )
    return equity_factor_evidence_payload(
        component,
        source="Unclassified input",
        source_quality="low",
        historical_replay=False,
        score_use="missing",
        coverage={"start": "", "end": "", "observations": 0},
        timestamp_policy="No timestamp policy declared.",
        reason="Component has not been mapped to a validated source contract.",
    )


def equity_factor_evidence_payload(
    component: dict[str, Any],
    *,
    source: str,
    source_quality: str,
    historical_replay: bool,
    score_use: str,
    coverage: dict[str, Any],
    timestamp_policy: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "component": str(component.get("key") or ""),
        "label": str(component.get("label") or component.get("key") or ""),
        "weight": round(float(component.get("weight") or 0.0), 4),
        "source": source,
        "sourceQuality": source_quality,
        "historicalReplay": bool(historical_replay),
        "scoreUse": score_use,
        "coverageStart": str(coverage.get("start") or ""),
        "coverageEnd": str(coverage.get("end") or ""),
        "observations": int(coverage.get("observations") or 0),
        "timestampPolicy": timestamp_policy,
        "reason": reason,
    }


def equity_bar_evidence_coverage(
    symbols: tuple[str, ...],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    target: date,
) -> dict[str, Any]:
    starts: list[date] = []
    ends: list[date] = []
    observations = 0
    for symbol in symbols:
        bars = [bar for bar in bars_by_symbol.get(symbol, []) if bar.date <= target]
        if not bars:
            continue
        starts.append(bars[0].date)
        ends.append(bars[-1].date)
        observations += len(bars)
    return {
        "start": min(starts).isoformat() if starts else "",
        "end": max(ends).isoformat() if ends else "",
        "observations": observations,
    }


def equity_factor_evidence_list(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_rows: list[dict[str, Any]] = []
    for component in components:
        evidence = component.get("evidence")
        if isinstance(evidence, dict):
            evidence_rows.append(evidence)
    return evidence_rows


def equity_source_quality_summary(components: list[dict[str, Any]], target: date) -> dict[str, Any]:
    total_weight = sum(float(component.get("weight") or 0.0) for component in components)
    scored_components = [
        component for component in components
        if component.get("available")
        and component.get("scoreUse") == "scored"
        and optional_float(component.get("score")) is not None
    ]
    audit_components = [component for component in components if component.get("scoreUse") == "auditOnly"]
    score_weight = sum(float(component.get("weight") or 0.0) for component in scored_components)
    high_quality_weight = sum(float(component.get("weight") or 0.0) for component in scored_components if component.get("sourceQuality") == "high")
    replayable_weight = sum(float(component.get("weight") or 0.0) for component in scored_components if component.get("historicalReplay") is True)
    audit_weight = sum(float(component.get("weight") or 0.0) for component in audit_components)
    denominator = total_weight if total_weight > 0 else 1.0
    eligible_pct = 100 * score_weight / denominator
    replayable_pct = 100 * replayable_weight / denominator
    high_quality_pct = 100 * high_quality_weight / denominator
    if eligible_pct >= 85 and replayable_pct >= 70:
        verdict = "高可信"
        detail = "主分数主要由可历史回放的日线OHLCV分项驱动。"
    elif eligible_pct >= 70 and replayable_pct >= 55:
        verdict = "中可信"
        detail = "主分数有足够可回放市场证据,但仍依赖部分低频/前瞻事件输入。"
    else:
        verdict = "低可信"
        detail = "可评分或可回放权重不足,主分数应降级为观察。"
    return {
        "verdict": verdict,
        "detail": detail,
        "dataThrough": target.isoformat(),
        "totalConfiguredWeightPct": 100.0,
        "scoreEligibleWeightPct": round(eligible_pct, 1),
        "historicalReplayableWeightPct": round(replayable_pct, 1),
        "highQualityWeightPct": round(high_quality_pct, 1),
        "auditOnlyWeightPct": round(100 * audit_weight / denominator, 1),
        "scoredComponentCount": len(scored_components),
        "auditOnlyComponentCount": len(audit_components),
        "scoredComponents": [str(component.get("key") or "") for component in scored_components],
        "auditOnlyComponents": [str(component.get("key") or "") for component in audit_components],
    }


def equity_weight_calibration_summary(
    components: list[dict[str, Any]],
    component_diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    diagnostic_by_key = {
        str(row.get("component") or ""): row
        for row in component_diagnostics
        if isinstance(row, dict) and row.get("component")
    }
    rows: list[dict[str, Any]] = []
    total_weight = 0.0
    validated_weight = 0.0
    downweighted_weight = 0.0
    context_weight = 0.0
    for component in components:
        if not isinstance(component, dict):
            continue
        key = str(component.get("key") or "")
        if not key:
            continue
        weight = float(component.get("weight") or 0.0)
        total_weight += weight
        diagnostic = diagnostic_by_key.get(key, {})
        decision = str(diagnostic.get("decision") or ("missing" if component.get("scoreUse") == "missing" else "context"))
        score_use = str(component.get("scoreUse") or "missing")
        source_quality = str(component.get("sourceQuality") or "")
        replayable = bool(component.get("historicalReplay"))
        if decision in {"core", "support"} and score_use == "scored":
            calibrated_role = "validated"
            calibrated_role_cn = "验证保留"
            validated_weight += weight
        elif decision == "trim" or score_use != "scored":
            calibrated_role = "downweighted"
            calibrated_role_cn = "降权/审计"
            downweighted_weight += weight
        else:
            calibrated_role = "context"
            calibrated_role_cn = "背景低权重"
            context_weight += weight
        precision = optional_float(diagnostic.get("precision")) if isinstance(diagnostic, dict) else None
        recall = optional_float(diagnostic.get("recall")) if isinstance(diagnostic, dict) else None
        false_positives = diagnostic.get("falsePositives") if isinstance(diagnostic, dict) else None
        rows.append(
            {
                "component": key,
                "label": str(component.get("label") or key),
                "configuredWeight": round(weight, 4),
                "configuredWeightPct": round(weight * 100, 1),
                "scoreUse": score_use,
                "sourceQuality": source_quality,
                "historicalReplay": replayable,
                "diagnosticDecision": decision,
                "diagnosticDecisionCn": str(diagnostic.get("decisionCn") or calibrated_role_cn) if isinstance(diagnostic, dict) else calibrated_role_cn,
                "calibratedRole": calibrated_role,
                "calibratedRoleCn": calibrated_role_cn,
                "precision": round(precision, 1) if precision is not None else None,
                "recall": round(recall, 1) if recall is not None else None,
                "falsePositives": int(false_positives) if isinstance(false_positives, int) else None,
                "recommendation": str(diagnostic.get("recommendation") or "") if isinstance(diagnostic, dict) else "",
            }
        )
    denominator = total_weight if total_weight > 0 else 1.0
    downweighted = sorted(
        [row for row in rows if row["calibratedRole"] == "downweighted"],
        key=lambda item: float(item.get("configuredWeight") or 0.0),
        reverse=True,
    )
    validated = sorted(
        [row for row in rows if row["calibratedRole"] == "validated"],
        key=lambda item: float(item.get("configuredWeight") or 0.0),
        reverse=True,
    )
    summary = (
        f"按历史分项诊断重配: 验证保留{validated_weight / denominator * 100:.1f}%权重,"
        f"降权/审计{downweighted_weight / denominator * 100:.1f}%,"
        f"背景{context_weight / denominator * 100:.1f}%。"
    )
    if downweighted:
        summary += " 最大降权: " + "、".join(str(row.get("label") or row.get("component")) for row in downweighted[:2]) + "。"
    return {
        "available": bool(rows),
        "basis": "componentDiagnostics from the current historical replay backtest; low-replay or weak standalone factors are kept low-weight instead of dominating the score.",
        "summary": summary,
        "validatedWeightPct": round(validated_weight / denominator * 100, 1),
        "downweightedWeightPct": round(downweighted_weight / denominator * 100, 1),
        "contextWeightPct": round(context_weight / denominator * 100, 1),
        "topValidatedComponents": [str(row.get("component") or "") for row in validated[:4]],
        "downweightedComponents": [str(row.get("component") or "") for row in downweighted],
        "rows": rows,
    }


def equity_forward_catalyst_risk(components: list[dict[str, Any]]) -> dict[str, Any]:
    event_component = next((component for component in components if component.get("key") == "eventRisk"), None)
    if not isinstance(event_component, dict):
        return {"available": False, "summary": "未生成事件窗口。"}
    metrics = event_component.get("metrics") if isinstance(event_component.get("metrics"), dict) else {}
    events = metrics.get("events") if isinstance(metrics.get("events"), list) else []
    score = optional_float(event_component.get("score"))
    window_days = int(metrics.get("windowDays") or 5)
    event_count = int(metrics.get("eventCount") or 0)
    if event_count:
        summary = f"未来{window_days}天有{event_count}个高重要性事件; 首个事件距信号日{metrics.get('daysToNextEvent')}天。"
    else:
        summary = f"未来{window_days}天没有高重要性事件,事件分项仅保留基准风险。"
    return {
        "available": event_component.get("available") is True,
        "score": round(score, 1) if score is not None else None,
        "windowDays": window_days,
        "eventCount": event_count,
        "events": events[:5],
        "nextEventDate": metrics.get("nextEventDate"),
        "daysToNextEvent": metrics.get("daysToNextEvent"),
        "knownBeforeSignal": bool(metrics.get("knownBeforeSignal")),
        "scoreUse": str(event_component.get("scoreUse") or "missing"),
        "summary": summary,
    }


def equity_driver(key: str, name: str, detail: str, risk_score: float) -> dict[str, Any]:
    return {"key": key, "name": name, "detail": detail, "riskScore": round(bounded_score(risk_score), 1)}


def equity_short_term_risk_drivers(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    drivers: list[dict[str, Any]] = []
    for component in components:
        for driver in component.get("drivers", []):
            if isinstance(driver, dict):
                drivers.append({**driver, "component": str(component.get("label") or component.get("key") or "")})
    return sorted(drivers, key=lambda item: optional_float(item.get("riskScore")) or 0.0, reverse=True)[:6]


def equity_convexity_amplifier(components: list[dict[str, Any]]) -> float:
    high_components = [component for component in components if optional_float(component.get("score")) is not None and float(component["score"]) >= 75]
    amplifier = 0.0
    if len(high_components) >= 4:
        amplifier += 5.0
    elif len(high_components) >= 3:
        amplifier += 3.0
    downtrend_score = 0.0
    downtrend_failed_rebound = 0.0
    hot_stock_score = 0.0
    market_flow_score = 0.0
    sector_score = 0.0
    qqq_tlt_score = 0.0
    vol_target_score = 0.0
    turnover_score = 0.0
    event_score = 0.0
    spy20_return = None
    for component in components:
        key = component.get("key")
        if key == "marketFlow":
            market_flow_score = optional_float(component.get("score")) or 0.0
            metrics = component.get("metrics") if isinstance(component.get("metrics"), dict) else {}
            downtrend_score = optional_float(metrics.get("downtrendFragilityScore")) or 0.0
            downtrend_failed_rebound = optional_float(metrics.get("downtrendFailedReboundScore")) or 0.0
            spy20_return = optional_float(metrics.get("spy20dReturn"))
        elif key == "hotStockReversal":
            hot_stock_score = optional_float(component.get("score")) or 0.0
        elif key == "sectorRotation":
            sector_score = optional_float(component.get("score")) or 0.0
        elif key == "qqqTltRotation":
            qqq_tlt_score = optional_float(component.get("score")) or 0.0
        elif key == "volTargetPressure":
            vol_target_score = optional_float(component.get("score")) or 0.0
        elif key == "turnover":
            turnover_score = optional_float(component.get("score")) or 0.0
        elif key == "eventRisk":
            event_score = optional_float(component.get("score")) or 0.0
    if (
        sector_score >= 85
        and hot_stock_score >= 85
        and market_flow_score >= 70
        and max(qqq_tlt_score, vol_target_score) >= 75
    ):
        amplifier += 4.0
    if (
        sector_score >= 90
        and hot_stock_score >= 90
        and market_flow_score >= 80
        and qqq_tlt_score >= 80
        and event_score >= 78
    ):
        amplifier += 4.0
    if (
        sector_score >= 95
        and hot_stock_score >= 95
        and market_flow_score >= 88
        and qqq_tlt_score >= 75
        and turnover_score >= 75
    ):
        amplifier += 14.0
    if downtrend_score >= 75 and max(hot_stock_score, turnover_score) >= 70:
        amplifier += 8.0
    elif downtrend_score >= 75:
        amplifier += 5.0
    if (
        downtrend_score >= 85
        and hot_stock_score >= 90
        and turnover_score >= 80
        and (spy20_return is None or spy20_return <= 0.0)
    ):
        amplifier += 2.0
    if downtrend_score >= 85 and downtrend_failed_rebound > 0:
        amplifier += 10.0
    return amplifier


def equity_noise_dampener(components: list[dict[str, Any]]) -> float:
    scores: dict[str, float] = {}
    market_metrics: dict[str, Any] = {}
    sector_metrics: dict[str, Any] = {}
    hot_metrics: dict[str, Any] = {}
    turnover_metrics: dict[str, Any] = {}
    for component in components:
        key = str(component.get("key") or "")
        score = optional_float(component.get("score"))
        if score is not None:
            scores[key] = score
        if key == "marketFlow" and isinstance(component.get("metrics"), dict):
            market_metrics = component["metrics"]
        elif key == "sectorRotation" and isinstance(component.get("metrics"), dict):
            sector_metrics = component["metrics"]
        elif key == "hotStockReversal" and isinstance(component.get("metrics"), dict):
            hot_metrics = component["metrics"]
        elif key == "turnover" and isinstance(component.get("metrics"), dict):
            turnover_metrics = component["metrics"]
    market_score = scores.get("marketFlow", 0.0)
    sector_score = scores.get("sectorRotation", 0.0)
    hot_stock_score = scores.get("hotStockReversal", 0.0)
    turnover_score = scores.get("turnover", 0.0)
    vol_target_score = scores.get("volTargetPressure", 0.0)
    qqq_tlt_score = scores.get("qqqTltRotation", 0.0)
    event_score = scores.get("eventRisk", 0.0)
    macro_score = scores.get("macroOverlay", 0.0)
    downtrend_score = optional_float(market_metrics.get("downtrendFragilityScore")) or 0.0
    downtrend_sell_pressure = optional_float(market_metrics.get("downtrendSellPressureScore")) or 0.0
    defensive_gap = optional_float(market_metrics.get("defensiveGap20d"))
    spy20_return = optional_float(market_metrics.get("spy20dReturn"))
    spy63_return = optional_float(market_metrics.get("spy63dReturn"))
    qqq63_return = optional_float(market_metrics.get("qqq63dReturn"))
    smh63_return = optional_float(market_metrics.get("smh63dReturn"))
    smh_rsp_gap = optional_float(sector_metrics.get("smhRspGap"))
    heavy_reversal_count = optional_float(hot_metrics.get("heavyReversalCount")) or 0.0
    volume_pct = optional_float(turnover_metrics.get("volumePercentile"))
    close_location = optional_float(turnover_metrics.get("closeLocation"))
    spy_day_return = optional_float(turnover_metrics.get("spyDayReturn"))
    if (
        sector_score >= 85
        and hot_stock_score >= 85
        and market_score >= 75
        and qqq_tlt_score >= 75
        and vol_target_score < 50
        and downtrend_score < 50
        and event_score < 60
        and macro_score < 60
    ):
        return -14.0
    if (
        sector_score < 50
        and market_score >= 85
        and hot_stock_score >= 85
        and max(vol_target_score, qqq_tlt_score) >= 85
        and turnover_score >= 75
        and event_score < 60
        and macro_score < 60
    ):
        return -25.0
    if (
        market_score >= 85
        and hot_stock_score >= 85
        and downtrend_score < 50
        and event_score < 60
        and macro_score < 60
    ):
        return -8.0
    if (
        downtrend_score >= 75
        and downtrend_sell_pressure >= 78
        and hot_stock_score >= 85
        and heavy_reversal_count <= 2
        and turnover_score >= 80
        and volume_pct is not None
        and volume_pct >= 85
        and close_location is not None
        and close_location <= 0.20
        and spy_day_return is not None
        and spy_day_return <= -0.8
        and defensive_gap is not None
        and defensive_gap >= 5.0
        and smh_rsp_gap is not None
        and smh_rsp_gap >= 8.0
        and event_score < 60
        and macro_score < 60
    ):
        return -18.0
    if (
        market_score < 75
        and downtrend_score < 50
        and sector_score >= 80
        and hot_stock_score >= 90
        and turnover_score >= 75
        and event_score < 60
        and macro_score < 60
    ):
        return -18.0
    if (
        downtrend_sell_pressure >= 78
        and hot_stock_score >= 85
        and turnover_score >= 80
        and qqq_tlt_score < 60
        and vol_target_score < 70
        and sector_score < 70
        and spy63_return is not None
        and spy63_return > -2.0
        and qqq63_return is not None
        and qqq63_return > -3.0
        and smh63_return is not None
        and smh63_return > -3.0
        and event_score < 60
        and macro_score < 60
    ):
        return -18.0
    if (
        downtrend_sell_pressure >= 78
        and hot_stock_score >= 85
        and turnover_score >= 80
        and spy_day_return is not None
        and spy_day_return > -1.0
        and event_score < 60
        and macro_score < 60
    ):
        return -14.0
    if (
        downtrend_sell_pressure >= 78
        and spy20_return is not None
        and spy20_return > 0.0
        and smh63_return is not None
        and smh63_return <= -10.0
        and event_score < 60
        and macro_score < 60
    ):
        return -18.0
    if (
        downtrend_sell_pressure >= 78
        and heavy_reversal_count <= 1
        and defensive_gap is not None
        and defensive_gap <= 3.0
        and smh_rsp_gap is not None
        and smh_rsp_gap <= 0.0
        and smh63_return is not None
        and smh63_return <= 5.0
        and event_score < 60
        and macro_score < 60
    ):
        return -18.0
    if (
        event_score >= 78
        and market_score < 75
        and downtrend_score < 50
        and turnover_score < 80
        and heavy_reversal_count <= 1
    ):
        return -14.0
    if (
        downtrend_score >= 80
        and downtrend_sell_pressure <= 5
        and hot_stock_score >= 80
        and turnover_score >= 80
        and volume_pct is not None
        and volume_pct >= 85
        and close_location is not None
        and close_location <= 0.40
        and spy_day_return is not None
        and spy_day_return > -0.8
        and defensive_gap is not None
        and defensive_gap >= 12.0
        and smh_rsp_gap is not None
        and smh_rsp_gap <= 0.0
        and event_score < 60
        and macro_score < 60
    ):
        return -14.0
    return 0.0


def equity_convexity_score_floor(components: list[dict[str, Any]]) -> float:
    relief_trap_score = 0.0
    volume_pct = None
    defensive_gap = None
    for component in components:
        if component.get("key") != "marketFlow":
            continue
        metrics = component.get("metrics") if isinstance(component.get("metrics"), dict) else {}
        relief_trap_score = optional_float(metrics.get("downtrendReliefRallyTrapScore")) or 0.0
        volume_pct = optional_float(metrics.get("spyVolumePercentile"))
        defensive_gap = optional_float(metrics.get("defensiveGap20d"))
        break
    low_volume_unresolved = (
        volume_pct is not None
        and volume_pct <= 55.0
        and defensive_gap is not None
        and defensive_gap <= 4.0
    )
    if relief_trap_score >= 90 and low_volume_unresolved:
        return 75.0
    if relief_trap_score >= 78:
        return 68.0
    if relief_trap_score >= 68:
        return 60.0
    return 0.0


def equity_short_term_risk_allocation(score: float) -> dict[str, Any]:
    base = {"horizon": "1-10d", "horizonCn": "1-10个交易日"}
    if score >= 75:
        return {
            **base,
            "regime": "Strong Alert",
            "regimeCn": "强告警",
            "stance": "短线降风险",
            "equityExposure": "高Beta/AI拥挤仓位降到低配",
            "exposureBandPct": [50, 80],
            "hedgeAction": "收盘前优先减仓或买入1-2周保护性对冲",
        }
    if score >= 60:
        return {
            **base,
            "regime": "Caution",
            "regimeCn": "警戒",
            "stance": "控制追涨",
            "equityExposure": "权益仓位降到中性以下",
            "exposureBandPct": [70, 90],
            "hedgeAction": "减少半导体/高Beta集中敞口",
        }
    if score >= 40:
        return {
            **base,
            "regime": "Watch",
            "regimeCn": "观察",
            "stance": "不追高",
            "equityExposure": "维持中性",
            "exposureBandPct": [85, 100],
            "hedgeAction": "等待确认",
        }
    return {
        **base,
        "regime": "Normal",
        "regimeCn": "正常",
        "stance": "风险可承受",
        "equityExposure": "维持计划仓位",
        "exposureBandPct": [100, 100],
        "hedgeAction": "无需额外对冲",
    }


def equity_short_term_risk_summary(score: float, allocation: dict[str, str], drivers: list[dict[str, Any]], target: date) -> str:
    if drivers:
        driver_text = "、".join(str(driver.get("name") or "") for driver in drivers[:3])
    else:
        driver_text = "未出现单一主导风险"
    return f"{target.isoformat()}收盘前短周期风险为{allocation['regimeCn']}({score:.1f}); 主要来自{driver_text}。动作: {allocation['hedgeAction']}。"


def build_equity_short_term_risk_trend(
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    *,
    macro_liquidity_equity: dict[str, Any],
    spy_early_warning: dict[str, Any],
    calendar_events: list[CalendarEvent],
    option_open_interest: OptionOpenInterestSnapshot | None,
) -> dict[str, Any]:
    spy_bars = bars_by_symbol.get("SPY", [])
    if len(spy_bars) < 20:
        return {"available": False, "points": [], "summary": "SPY日线样本不足"}
    points: list[dict[str, Any]] = []
    for bar in spy_bars:
        if len([item for item in spy_bars if item.date <= bar.date]) < 20:
            continue
        snapshot = equity_short_term_signal_at(
            bars_by_symbol,
            bar.date,
            macro_liquidity_equity=macro_liquidity_equity,
            spy_early_warning=spy_early_warning,
            calendar_events=calendar_events,
            option_open_interest=option_open_interest,
            include_macro_overlay=False,
        )
        if not snapshot.get("available"):
            continue
        allocation = snapshot.get("allocation") if isinstance(snapshot.get("allocation"), dict) else {}
        points.append(
            {
                "date": bar.date.isoformat(),
                "score": optional_float(snapshot.get("score")),
                "regime": str(snapshot.get("regime") or ""),
                "regimeCn": str(snapshot.get("regimeCn") or ""),
                "spyClose": round(bar.close, 2),
                "spyDayReturn": pct_metric(one_day_return(spy_bars, bar.date)),
                "stance": str(allocation.get("stance") or ""),
                "componentScores": equity_component_scores_payload(
                    snapshot.get("components", []) if isinstance(snapshot.get("components"), list) else []
                ),
            }
        )
    return {"available": bool(points), "summary": "短周期股市风险日度回放; 高分表示未来1-10个交易日回撤风险升高。", "points": points}


def build_equity_short_term_risk_backtest(
    trend_points: list[dict[str, Any]],
    spy_bars: list[MarketDailyBar],
    *,
    horizon: int = 10,
    drawdown_threshold_pct: float = -2.0,
) -> dict[str, Any]:
    clean_bars = normalize_market_bars({"SPY": spy_bars}).get("SPY", [])
    if len(clean_bars) < 3 or not trend_points:
        return {
            "available": False,
            "summary": "SPY日线或风险回放样本不足,暂不能做历史命中率分析。",
            "sampleSize": 0,
            "scoreBuckets": [],
            "thresholdTests": [],
            "horizonTests": [],
            "tieredThresholdTests": [],
            "calibrationGrid": [],
            "recommendedCautionThreshold": {},
            "precisionThresholdTests": [],
            "highPrecisionThresholdTest": {},
            "componentDiagnostics": [],
            "preferredThresholdTest": {},
            "alertClusterTest": {},
            "regressionTests": [],
            "worstWindows": [],
            "alertWindows": [],
        }
    index_by_date = {bar.date: index for index, bar in enumerate(clean_bars)}
    preferred_horizon = max(horizon, 15)
    horizons = sorted({1, 5, horizon, preferred_horizon})
    observations: list[dict[str, Any]] = []
    for point in trend_points:
        if not isinstance(point, dict):
            continue
        try:
            point_date = date.fromisoformat(str(point.get("date") or ""))
        except ValueError:
            continue
        score = optional_float(point.get("score"))
        if score is None:
            continue
        index = index_by_date.get(point_date)
        if index is None or index + 1 >= len(clean_bars):
            continue
        current = clean_bars[index]
        if current.close <= 0:
            continue
        end_index = min(len(clean_bars) - 1, index + horizon)
        future_bars = clean_bars[index + 1: end_index + 1]
        if not future_bars:
            continue
        observation = {
            "date": point_date.isoformat(),
            "score": round(bounded_score(score), 1),
            "regime": str(point.get("regime") or ""),
            "regimeCn": str(point.get("regimeCn") or ""),
            "spyClose": round(current.close, 2),
        }
        component_scores = point.get("componentScores")
        if isinstance(component_scores, dict):
            observation["componentScores"] = component_scores
        for target_horizon in horizons:
            observation[f"forward{target_horizon}d"] = equity_forward_return_pct(clean_bars, index, target_horizon)
            max_drawdown = equity_forward_max_drawdown_pct(clean_bars, index, target_horizon)
            observation[f"maxDrawdown{target_horizon}d"] = max_drawdown
            observation[f"drawdownEvent{target_horizon}d"] = bool(
                max_drawdown is not None
                and float(max_drawdown) <= drawdown_threshold_pct
            )
            observation[f"drawdownLeadDays{target_horizon}d"] = equity_forward_drawdown_lead_days(
                clean_bars,
                index,
                target_horizon,
                drawdown_threshold_pct,
            )
        observations.append(observation)
    if not observations:
        return {
            "available": False,
            "summary": "风险回放点没有足够的后续SPY交易日,暂不能做历史命中率分析。",
            "sampleSize": 0,
            "scoreBuckets": [],
            "thresholdTests": [],
            "horizonTests": [],
            "tieredThresholdTests": [],
            "calibrationGrid": [],
            "recommendedCautionThreshold": {},
            "componentDiagnostics": [],
            "preferredThresholdTest": {},
            "alertClusterTest": {},
            "regressionTests": [],
            "worstWindows": [],
            "alertWindows": [],
        }

    buckets = [
        ("Normal", "正常", 0.0, 40.0),
        ("Watch", "观察", 40.0, 60.0),
        ("Caution", "警戒", 60.0, 75.0),
        ("Strong Alert", "强告警", 75.0, 100.0001),
    ]
    score_buckets = [
        equity_backtest_bucket(label, label_cn, low, high, observations, drawdown_threshold_pct)
        for label, label_cn, low, high in buckets
    ]
    threshold_tests = [
        equity_backtest_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=horizon)
        for threshold in (40, 60, 75)
    ]
    horizon_tests = [
        equity_backtest_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=target_horizon)
        for target_horizon in (5, horizon, preferred_horizon)
        for threshold in (40, 60, 75)
    ]
    calibration_grid = [
        equity_backtest_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=preferred_horizon)
        for threshold in (50, 55, 60, 65, 70, 75)
    ]
    precision_threshold_tests = [
        equity_backtest_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=preferred_horizon)
        for threshold in (75, 78, 80, 82, 85, 88, 90)
    ]
    component_diagnostics = equity_backtest_component_diagnostics(
        observations,
        drawdown_threshold_pct,
        horizon=preferred_horizon,
    )
    tiered_threshold_tests = equity_backtest_tiered_threshold_tests(horizon_tests, horizon=preferred_horizon)
    recommended_caution_threshold = equity_recommended_caution_threshold(calibration_grid)
    high_precision_threshold_test = equity_high_precision_threshold(precision_threshold_tests)
    walk_forward = equity_walk_forward_backtest(
        observations,
        drawdown_threshold_pct,
        horizon=preferred_horizon,
    )
    out_of_sample_threshold_tests = walk_forward.get("thresholdTests", []) if isinstance(walk_forward, dict) else []
    preferred_threshold_test = next(
        (item for item in horizon_tests if item["threshold"] == 75 and item["horizon"] == preferred_horizon),
        {},
    )
    alert_cluster_test = equity_backtest_alert_cluster_test(
        75,
        observations,
        drawdown_threshold_pct,
        horizon=preferred_horizon,
    )
    regression_tests = equity_backtest_regression_tests(observations)
    worst_windows = [
        equity_backtest_window_payload(row)
        for row in sorted(
            observations,
            key=lambda item: optional_float(item.get(f"maxDrawdown{preferred_horizon}d")) if optional_float(item.get(f"maxDrawdown{preferred_horizon}d")) is not None else 999.0,
        )[:6]
    ]
    top_signals = [equity_backtest_window_payload(row) for row in sorted(observations, key=lambda item: float(item["score"]), reverse=True)[:6]]
    alert_windows = [
        equity_backtest_alert_window_payload(row, horizon=preferred_horizon, threshold=75)
        for row in sorted(
            [row for row in observations if float(row["score"]) >= 75],
            key=lambda item: (-float(item["score"]), str(item.get("date") or "")),
        )[:80]
    ]
    threshold_75 = next((item for item in threshold_tests if item["threshold"] == 75), {})
    strong_bucket = next((item for item in score_buckets if item["label"] == "Strong Alert"), {})
    precision = preferred_threshold_test.get("precision")
    avg_strong_drawdown = strong_bucket.get(f"avgMaxDrawdown{preferred_horizon}d")
    summary = (
        f"历史回放样本{len(observations)}个交易日; score>=75告警{preferred_threshold_test.get('alertDays', 0)}次,"
        f"{preferred_horizon}日内<-2%回撤命中率{format_optional_percent_value(precision)},"
        f"命中平均提前{format_optional_number(preferred_threshold_test.get('avgDrawdownLeadDaysWhenHit'))}个交易日,"
        f"告警簇命中率{format_optional_percent_value(alert_cluster_test.get('precision'))};"
        f"强告警桶平均{preferred_horizon}日最大回撤{format_optional_percent_value(avg_strong_drawdown)}。"
    )
    return {
        "available": True,
        "target": f"1-{preferred_horizon} trading-day SPY drawdown warning",
        "method": f"For each historical equityShortTermRisk score, measure forward 1D/5D/{horizon}D/{preferred_horizon}D SPY return and the worst next-{preferred_horizon}-trading-day SPY drawdown from same-day close. The next-day audit is never used in the score; the preferred accuracy view allows signals to be two or three days early before a drawdown window.",
        "sampleSize": len(observations),
        "dateRange": {"start": observations[0]["date"], "end": observations[-1]["date"]},
        "drawdownEvent": f"next {preferred_horizon} trading days max drawdown <= {drawdown_threshold_pct:.1f}%",
        "preferredHorizon": preferred_horizon,
        "summary": summary,
        "scoreBuckets": score_buckets,
        "thresholdTests": threshold_tests,
        "horizonTests": horizon_tests,
        "tieredThresholdTests": tiered_threshold_tests,
        "calibrationGrid": calibration_grid,
        "recommendedCautionThreshold": recommended_caution_threshold,
        "precisionThresholdTests": precision_threshold_tests,
        "highPrecisionThresholdTest": high_precision_threshold_test,
        "walkForward": walk_forward,
        "outOfSampleThresholdTests": out_of_sample_threshold_tests,
        "componentDiagnostics": component_diagnostics,
        "preferredThresholdTest": preferred_threshold_test,
        "alertClusterTest": alert_cluster_test,
        "regressionTests": regression_tests,
        "worstWindows": worst_windows,
        "topSignals": top_signals,
        "alertWindows": alert_windows,
        "caveats": [
            "Nasdaq daily OHLCV supports historical replay for price, volume, sector rotation, and hot-stock reversal factors.",
            "Historical replay excludes the current macroOverlay snapshot to avoid contaminating past scores with today's macro state.",
            "Threshold guidance includes a 70/30 chronological walk-forward view plus precision lift versus the unconditional drawdown base rate.",
            "Free Cboe option OI and broad news feeds are current snapshots or curated feeds, so full historical option/news backfills are excluded unless an archived feed is added.",
            "This is a risk-control backtest, not a standalone return forecast or personal investment recommendation.",
        ],
    }


def equity_forward_return_pct(bars: list[MarketDailyBar], index: int, days: int) -> float | None:
    if index < 0 or index >= len(bars) - 1:
        return None
    end_index = min(len(bars) - 1, index + days)
    if end_index <= index or bars[index].close <= 0:
        return None
    return pct_metric(bars[end_index].close / bars[index].close - 1)


def equity_forward_max_drawdown_pct(bars: list[MarketDailyBar], index: int, days: int) -> float | None:
    if index < 0 or index >= len(bars) - 1 or bars[index].close <= 0:
        return None
    end_index = min(len(bars) - 1, index + days)
    future_lows = [bar.low for bar in bars[index + 1: end_index + 1] if bar.low > 0]
    if not future_lows:
        return None
    return pct_metric(min(future_lows) / bars[index].close - 1)


def equity_forward_drawdown_lead_days(
    bars: list[MarketDailyBar],
    index: int,
    days: int,
    drawdown_threshold_pct: float,
) -> int | None:
    if index < 0 or index >= len(bars) - 1 or bars[index].close <= 0:
        return None
    end_index = min(len(bars) - 1, index + days)
    for lead_days, bar in enumerate(bars[index + 1: end_index + 1], start=1):
        if bar.low > 0 and pct_metric(bar.low / bars[index].close - 1) <= drawdown_threshold_pct:
            return lead_days
    return None


def equity_backtest_bucket(
    label: str,
    label_cn: str,
    low: float,
    high: float,
    observations: list[dict[str, Any]],
    drawdown_threshold_pct: float,
) -> dict[str, Any]:
    members = [row for row in observations if low <= float(row["score"]) < high]
    return {
        "label": label,
        "labelCn": label_cn,
        "scoreRange": f"{low:.0f}-{min(high, 100.0):.0f}",
        "count": len(members),
        "avgScore": round(equity_average_metric(members, "score"), 1) if members else None,
        "avgForward1d": equity_average_metric(members, "forward1d"),
        "avgForward5d": equity_average_metric(members, "forward5d"),
        "avgForward10d": equity_average_metric(members, "forward10d"),
        "avgForward15d": equity_average_metric(members, "forward15d"),
        "avgMaxDrawdown5d": equity_average_metric(members, "maxDrawdown5d"),
        "avgMaxDrawdown10d": equity_average_metric(members, "maxDrawdown10d"),
        "avgMaxDrawdown15d": equity_average_metric(members, "maxDrawdown15d"),
        "drawdownHitRate10d": equity_rate_pct(sum(1 for row in members if row.get("drawdownEvent10d")), len(members)),
        "drawdownHitRate15d": equity_rate_pct(sum(1 for row in members if row.get("drawdownEvent15d")), len(members)),
        "drawdownThreshold": drawdown_threshold_pct,
        "worstForward10d": equity_min_metric(members, "forward10d"),
        "worstMaxDrawdown10d": equity_min_metric(members, "maxDrawdown10d"),
        "worstForward15d": equity_min_metric(members, "forward15d"),
        "worstMaxDrawdown15d": equity_min_metric(members, "maxDrawdown15d"),
    }


def equity_backtest_threshold_test(
    threshold: int,
    observations: list[dict[str, Any]],
    drawdown_threshold_pct: float,
    *,
    horizon: int,
) -> dict[str, Any]:
    event_key = f"drawdownEvent{horizon}d"
    forward_key = f"forward{horizon}d"
    drawdown_key = f"maxDrawdown{horizon}d"
    lead_key = f"drawdownLeadDays{horizon}d"
    alert_rows = [row for row in observations if float(row["score"]) >= threshold]
    event_rows = [row for row in observations if row.get(event_key)]
    true_positives = sum(1 for row in alert_rows if row.get(event_key))
    false_positives = len(alert_rows) - true_positives
    false_negatives = len(event_rows) - true_positives
    hit_leads = [
        int(lead)
        for row in alert_rows
        if row.get(event_key)
        for lead in [optional_float(row.get(lead_key))]
        if lead is not None
    ]
    result = {
        "threshold": threshold,
        "horizon": horizon,
        "rule": f"score >= {threshold}",
        "event": f"maxDrawdown{horizon}d <= {drawdown_threshold_pct:.1f}%",
        "sampleSize": len(observations),
        "alertDays": len(alert_rows),
        "drawdownEvents": len(event_rows),
        "truePositives": true_positives,
        "falsePositives": false_positives,
        "falseNegatives": false_negatives,
        "precision": equity_rate_pct(true_positives, len(alert_rows)),
        "recall": equity_rate_pct(true_positives, len(event_rows)),
        "baseRate": equity_rate_pct(len(event_rows), len(observations)),
        "avgForwardWhenAlert": equity_average_metric(alert_rows, forward_key),
        "avgMaxDrawdownWhenAlert": equity_average_metric(alert_rows, drawdown_key),
        "avgDrawdownLeadDaysWhenHit": round(sum(hit_leads) / len(hit_leads), 1) if hit_leads else None,
        "medianDrawdownLeadDaysWhenHit": round(float(median(hit_leads)), 1) if hit_leads else None,
        "minDrawdownLeadDaysWhenHit": min(hit_leads) if hit_leads else None,
        "maxDrawdownLeadDaysWhenHit": max(hit_leads) if hit_leads else None,
    }
    precision_value = optional_float(result.get("precision"))
    base_rate_value = optional_float(result.get("baseRate"))
    if precision_value is not None and base_rate_value is not None:
        result["precisionMinusBaseRate"] = round(precision_value - base_rate_value, 1)
        result["liftVsBaseRate"] = round(precision_value / base_rate_value, 2) if base_rate_value > 0 else None
    else:
        result["precisionMinusBaseRate"] = None
        result["liftVsBaseRate"] = None
    result[f"avgForward{horizon}dWhenAlert"] = result["avgForwardWhenAlert"]
    result[f"avgMaxDrawdown{horizon}dWhenAlert"] = result["avgMaxDrawdownWhenAlert"]
    if horizon == 10:
        result["avgForward10dWhenAlert"] = result["avgForwardWhenAlert"]
        result["avgMaxDrawdown10dWhenAlert"] = result["avgMaxDrawdownWhenAlert"]
    return result


def equity_backtest_tiered_threshold_tests(horizon_tests: list[dict[str, Any]], *, horizon: int) -> list[dict[str, Any]]:
    tier_specs = {
        75: {
            "key": "strongAlert",
            "label": "强告警",
            "labelEn": "Strong Alert",
            "useCase": "高精度降风险触发; 适合减仓或买入短期保护。",
        },
        60: {
            "key": "cautionPlus",
            "label": "警戒以上",
            "labelEn": "Caution+",
            "useCase": "覆盖更多潜在回撤; 适合观察仓位拥挤、事件和尾盘确认。",
        },
        40: {
            "key": "watchPlus",
            "label": "观察以上",
            "labelEn": "Watch+",
            "useCase": "早期背景噪声层; 只作为风险环境过滤器。",
        },
    }
    by_threshold = {
        int(item["threshold"]): item
        for item in horizon_tests
        if int(item.get("horizon") or 0) == horizon and int(item.get("threshold") or -1) in tier_specs
    }
    tiered = []
    for threshold in (75, 60, 40):
        base = dict(by_threshold.get(threshold) or {"threshold": threshold, "horizon": horizon})
        base.update(tier_specs[threshold])
        tiered.append(base)
    return tiered


def equity_recommended_caution_threshold(calibration_grid: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        row
        for row in calibration_grid
        if 55 <= int(row.get("threshold") or 0) <= 70 and (optional_float(row.get("alertDays")) or 0) > 0
    ]
    if not candidates:
        return {}
    base_rate = max(optional_float(row.get("baseRate")) or 0.0 for row in candidates)
    min_precision = max(50.0, base_rate + 5.0)
    qualifying = [row for row in candidates if (optional_float(row.get("precision")) or 0.0) >= min_precision]
    if not qualifying:
        qualifying = candidates

    def calibration_score(row: dict[str, Any]) -> tuple[float, float, float]:
        recall = optional_float(row.get("recall")) or 0.0
        precision = optional_float(row.get("precision")) or 0.0
        threshold = optional_float(row.get("threshold")) or 0.0
        return (recall, precision, threshold)

    selected = dict(max(qualifying, key=calibration_score))
    selected.update(
        {
            "key": "recommendedCautionThreshold",
            "label": "推荐观察阈值",
            "labelEn": "Recommended Caution Threshold",
            "useCase": "推荐观察层; 在保持基础精确率约束下尽量提高回撤覆盖率。",
        }
    )
    return selected


def equity_high_precision_threshold(precision_grid: list[dict[str, Any]]) -> dict[str, Any]:
    max_alert_days = max((optional_float(row.get("alertDays")) or 0.0 for row in precision_grid), default=0.0)
    minimum_alert_days = min(5.0, max(1.0, max_alert_days))
    candidates = [
        row
        for row in precision_grid
        if (optional_float(row.get("alertDays")) or 0.0) >= minimum_alert_days
    ]
    if not candidates:
        return {}
    base_rate = max(optional_float(row.get("baseRate")) or 0.0 for row in candidates)
    min_precision = max(75.0, base_rate + 25.0)
    qualifying = [row for row in candidates if (optional_float(row.get("precision")) or 0.0) >= min_precision]
    if not qualifying:
        qualifying = candidates

    def precision_score(row: dict[str, Any]) -> tuple[float, float, float, float]:
        precision = optional_float(row.get("precision")) or 0.0
        recall = optional_float(row.get("recall")) or 0.0
        alert_days = optional_float(row.get("alertDays")) or 0.0
        threshold = optional_float(row.get("threshold")) or 0.0
        return (precision, recall, alert_days, -threshold)

    selected = dict(max(qualifying, key=precision_score))
    selected.update(
        {
            "key": "highPrecisionThreshold",
            "label": "高精度强告警阈值",
            "labelEn": "High-Precision Strong Alert Threshold",
            "useCase": "更偏执行层的高置信降风险阈值; 牺牲覆盖率来提高历史精确率。",
        }
    )
    return selected


def equity_walk_forward_backtest(
    observations: list[dict[str, Any]],
    drawdown_threshold_pct: float,
    *,
    horizon: int,
) -> dict[str, Any]:
    if len(observations) < 20:
        return {
            "available": False,
            "summary": "walk-forward sample requires at least 20 observations",
            "inSample": {"sampleSize": len(observations)},
            "outOfSample": {"sampleSize": 0},
            "thresholdTests": [],
        }
    split_index = max(1, min(len(observations) - 1, int(len(observations) * 0.70)))
    in_sample = observations[:split_index]
    out_sample = observations[split_index:]
    thresholds = (50, 55, 60, 65, 70, 75)
    in_grid = [
        equity_backtest_threshold_test(threshold, in_sample, drawdown_threshold_pct, horizon=horizon)
        for threshold in thresholds
    ]
    selected = equity_recommended_caution_threshold(in_grid) or max(
        in_grid,
        key=lambda row: (
            optional_float(row.get("precision")) or 0.0,
            optional_float(row.get("recall")) or 0.0,
            -(optional_float(row.get("threshold")) or 0.0),
        ),
    )
    selected_threshold = int(selected.get("threshold") or 75)
    tested_thresholds = sorted(set(thresholds + (selected_threshold, 75)))
    out_grid = [
        equity_backtest_threshold_test(threshold, out_sample, drawdown_threshold_pct, horizon=horizon)
        for threshold in tested_thresholds
    ]
    selected_out = next((row for row in out_grid if int(row.get("threshold") or -1) == selected_threshold), {})
    return {
        "available": True,
        "method": "70/30 chronological walk-forward: choose threshold on the first 70% and report precision/recall on the final 30%.",
        "splitDate": out_sample[0]["date"] if out_sample else None,
        "selectedThreshold": selected_threshold,
        "inSample": {
            "sampleSize": len(in_sample),
            "dateRange": {"start": in_sample[0]["date"], "end": in_sample[-1]["date"]},
            "selectedThresholdTest": selected,
            "thresholdTests": in_grid,
        },
        "outOfSample": {
            "sampleSize": len(out_sample),
            "dateRange": {"start": out_sample[0]["date"], "end": out_sample[-1]["date"]} if out_sample else {},
            "selectedThresholdTest": selected_out,
        },
        "thresholdTests": out_grid,
        "summary": (
            f"IS选择阈值{selected_threshold}; OOS告警{selected_out.get('alertDays', 0)}次, "
            f"precision {format_optional_percent_value(selected_out.get('precision'))}, "
            f"base {format_optional_percent_value(selected_out.get('baseRate'))}."
        ),
    }


def equity_backtest_component_diagnostics(
    observations: list[dict[str, Any]],
    drawdown_threshold_pct: float,
    *,
    horizon: int,
) -> list[dict[str, Any]]:
    event_key = f"drawdownEvent{horizon}d"
    drawdown_key = f"maxDrawdown{horizon}d"
    component_rows: dict[str, list[dict[str, Any]]] = {}
    component_meta: dict[str, dict[str, Any]] = {}
    for row in observations:
        component_scores = row.get("componentScores")
        if not isinstance(component_scores, dict):
            continue
        for key, payload in component_scores.items():
            if not isinstance(payload, dict):
                continue
            score = optional_float(payload.get("score"))
            if score is None:
                continue
            component_key = str(key)
            component_meta.setdefault(
                component_key,
                {
                    "label": str(payload.get("label") or component_key),
                    "weight": round(float(payload.get("weight") or 0.0), 4),
                    "sourceQuality": str(payload.get("sourceQuality") or ""),
                    "historicalReplay": bool(payload.get("historicalReplay")),
                },
            )
            component_rows.setdefault(component_key, []).append(
                {
                    "score": bounded_score(score),
                    "event": bool(row.get(event_key)),
                    "maxDrawdown": optional_float(row.get(drawdown_key)),
                }
            )

    diagnostics: list[dict[str, Any]] = []
    for key, rows in component_rows.items():
        if not rows:
            continue
        high_rows = [row for row in rows if float(row["score"]) >= 75.0]
        event_rows = [row for row in rows if row.get("event")]
        true_positives = sum(1 for row in high_rows if row.get("event"))
        false_positives = len(high_rows) - true_positives
        precision = equity_rate_pct(true_positives, len(high_rows))
        recall = equity_rate_pct(true_positives, len(event_rows))
        base_rate = equity_rate_pct(len(event_rows), len(rows))
        precision_value = optional_float(precision) or 0.0
        recall_value = optional_float(recall) or 0.0
        base_rate_value = optional_float(base_rate) or 0.0
        minimum_alert_days = min(10, max(2, len(rows) // 100))
        if not high_rows:
            decision = "context"
            decision_cn = "背景观察"
            recommendation = "高分样本不足,暂不升权; 保留为背景观察。"
        elif len(high_rows) < minimum_alert_days and precision_value >= max(75.0, base_rate_value + 20.0):
            decision = "context"
            decision_cn = "高精度低样本"
            recommendation = "历史高分命中率高但样本偏少; 保留低权重,等待更多样本确认。"
        elif precision_value >= max(60.0, base_rate_value + 15.0) and len(high_rows) >= minimum_alert_days:
            decision = "core"
            decision_cn = "核心保留"
            recommendation = "保留在核心评分; 若与其他核心因子共振可提高告警可信度。"
        elif precision_value >= base_rate_value + 2.0 or recall_value >= 15.0:
            decision = "support"
            decision_cn = "辅助保留"
            recommendation = "保留低到中权重; 需要与价格/成交确认后再触发动作。"
        else:
            decision = "trim"
            decision_cn = "降权/审计"
            recommendation = "降权或仅作审计; 单独高分对回撤预测贡献不足。"
        meta = component_meta.get(key, {})
        diagnostics.append(
            {
                "component": key,
                "label": meta.get("label") or key,
                "weight": meta.get("weight"),
                "sourceQuality": meta.get("sourceQuality") or "",
                "historicalReplay": bool(meta.get("historicalReplay")),
                "threshold": 75,
                "horizon": horizon,
                "event": f"maxDrawdown{horizon}d <= {drawdown_threshold_pct:.1f}%",
                "sampleSize": len(rows),
                "alertDays": len(high_rows),
                "drawdownEvents": len(event_rows),
                "truePositives": true_positives,
                "falsePositives": false_positives,
                "precision": precision,
                "recall": recall,
                "baseRate": base_rate,
                "avgScoreWhenActive": round(sum(float(row["score"]) for row in high_rows) / len(high_rows), 1) if high_rows else None,
                "avgMaxDrawdownWhenActive": equity_average_metric(high_rows, "maxDrawdown"),
                "decision": decision,
                "decisionCn": decision_cn,
                "recommendation": recommendation,
            }
        )

    decision_rank = {"core": 0, "support": 1, "context": 2, "trim": 3}
    return sorted(
        diagnostics,
        key=lambda row: (
            decision_rank.get(str(row.get("decision")), 9),
            -(optional_float(row.get("precision")) or -1.0),
            -(optional_float(row.get("recall")) or -1.0),
            str(row.get("component") or ""),
        ),
    )


def equity_backtest_alert_cluster_test(
    threshold: int,
    observations: list[dict[str, Any]],
    drawdown_threshold_pct: float,
    *,
    horizon: int,
) -> dict[str, Any]:
    event_key = f"drawdownEvent{horizon}d"
    drawdown_key = f"maxDrawdown{horizon}d"
    lead_key = f"drawdownLeadDays{horizon}d"
    clusters: list[list[dict[str, Any]]] = []
    active: list[dict[str, Any]] = []
    for row in observations:
        if float(row["score"]) >= threshold:
            active.append(row)
        elif active:
            clusters.append(active)
            active = []
    if active:
        clusters.append(active)
    cluster_rows = []
    for cluster in clusters:
        first = cluster[0]
        hit = bool(first.get(event_key))
        cluster_rows.append(
            {
                "start": first.get("date"),
                "end": cluster[-1].get("date"),
                "days": len(cluster),
                "maxScore": max(float(row["score"]) for row in cluster),
                "hit": hit,
                f"maxDrawdown{horizon}d": first.get(drawdown_key),
                "leadDays": first.get(lead_key) if hit else None,
            }
        )
    hit_clusters = sum(1 for row in cluster_rows if row.get("hit"))
    hit_leads = [int(row["leadDays"]) for row in cluster_rows if isinstance(row.get("leadDays"), (int, float))]
    false_clusters = [row for row in cluster_rows if not row.get("hit")]
    max_false_cluster = max(false_clusters, key=lambda row: int(row.get("days") or 0), default={})
    return {
        "threshold": threshold,
        "horizon": horizon,
        "event": f"first alert in cluster maxDrawdown{horizon}d <= {drawdown_threshold_pct:.1f}%",
        "clusterCount": len(cluster_rows),
        "hitClusters": hit_clusters,
        "falseClusters": len(cluster_rows) - hit_clusters,
        "maxFalseClusterDays": int(max_false_cluster.get("days") or 0),
        "maxFalseClusterStart": max_false_cluster.get("start"),
        "maxFalseClusterEnd": max_false_cluster.get("end"),
        "precision": equity_rate_pct(hit_clusters, len(cluster_rows)),
        "avgLeadDays": round(sum(hit_leads) / len(hit_leads), 1) if hit_leads else None,
        "clusters": cluster_rows[:8],
    }


def equity_backtest_regression_tests(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        equity_backtest_linear_regression(
            observations,
            key="forward10d",
            target="forward10d",
            label="10D forward return",
            unit="pct",
            summary_template="score每升10分,未来10日SPY收益变化{delta}个百分点",
        ),
        equity_backtest_linear_regression(
            observations,
            key="maxDrawdown10d",
            target="maxDrawdown10d",
            label="10D max drawdown",
            unit="pct",
            summary_template="score每升10分,未来10日最大回撤变化{delta}个百分点",
        ),
        equity_backtest_linear_probability_regression(observations, horizon=10),
        equity_backtest_linear_regression(
            observations,
            key="maxDrawdown15d",
            target="maxDrawdown15d",
            label="15D max drawdown",
            unit="pct",
            summary_template="score每升10分,未来15日最大回撤变化{delta}个百分点",
        ),
        equity_backtest_linear_probability_regression(observations, horizon=15),
    ]


def equity_backtest_linear_probability_regression(observations: list[dict[str, Any]], *, horizon: int) -> dict[str, Any]:
    event_key = f"drawdownEvent{horizon}d"
    rows = [
        {"score": row.get("score"), "drawdownEventPct": 100.0 if row.get(event_key) else 0.0}
        for row in observations
    ]
    return equity_backtest_linear_regression(
        rows,
        key="drawdownEventPct",
        target=event_key,
        label=f"{horizon}D drawdown event probability",
        unit="probability_pct",
        summary_template=f"score每升10分,未来{horizon}日<-2%回撤概率变化{{delta}}个百分点",
    )


def equity_backtest_linear_regression(
    rows: list[dict[str, Any]],
    *,
    key: str,
    target: str,
    label: str,
    unit: str,
    summary_template: str,
) -> dict[str, Any]:
    pairs = []
    for row in rows:
        score = optional_float(row.get("score"))
        value = optional_float(row.get(key))
        if score is not None and value is not None:
            pairs.append((score, value))
    base = {"target": target, "label": label, "unit": unit, "sampleSize": len(pairs)}
    if len(pairs) < 3:
        return {**base, "available": False, "summary": "样本不足,暂不能回归。"}
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    ssx = sum((value - x_mean) ** 2 for value in xs)
    ssy = sum((value - y_mean) ** 2 for value in ys)
    if ssx <= 0 or ssy <= 0:
        return {**base, "available": False, "summary": "score或目标变量没有足够变化,暂不能回归。"}
    cov = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    slope = cov / ssx
    intercept = y_mean - slope * x_mean
    correlation = cov / math.sqrt(ssx * ssy)
    fitted = [intercept + slope * x for x in xs]
    residual_sum_squares = sum((y - y_hat) ** 2 for y, y_hat in zip(ys, fitted))
    r_squared = max(0.0, min(1.0, correlation * correlation))
    if len(pairs) > 2 and ssx > 0:
        residual_variance = residual_sum_squares / (len(pairs) - 2)
        standard_error = math.sqrt(residual_variance / ssx) if residual_variance >= 0 else None
        t_stat = slope / standard_error if standard_error and standard_error > 0 else None
    else:
        t_stat = None
    slope_per_10 = slope * 10
    delta = f"{slope_per_10:+.2f}"
    return {
        **base,
        "available": True,
        "slopePerScore": round(slope, 4),
        "slopePer10Score": round(slope_per_10, 2),
        "intercept": round(intercept, 2),
        "correlation": round(correlation, 3),
        "rSquared": round(r_squared, 3),
        "tStat": round(t_stat, 2) if t_stat is not None and math.isfinite(t_stat) else None,
        "summary": f"{summary_template.format(delta=delta)}; R² {r_squared:.2f}。",
    }


def equity_backtest_window_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": str(row.get("date") or ""),
        "score": row.get("score"),
        "regime": str(row.get("regime") or ""),
        "regimeCn": str(row.get("regimeCn") or ""),
        "spyClose": row.get("spyClose"),
        "forward1d": row.get("forward1d"),
        "forward5d": row.get("forward5d"),
        "forward10d": row.get("forward10d"),
        "forward15d": row.get("forward15d"),
        "maxDrawdown10d": row.get("maxDrawdown10d"),
        "maxDrawdown15d": row.get("maxDrawdown15d"),
        "drawdownLeadDays10d": row.get("drawdownLeadDays10d"),
        "drawdownLeadDays15d": row.get("drawdownLeadDays15d"),
    }


def equity_backtest_alert_window_payload(row: dict[str, Any], *, horizon: int, threshold: int) -> dict[str, Any]:
    event_key = f"drawdownEvent{horizon}d"
    return {
        **equity_backtest_window_payload(row),
        "threshold": threshold,
        "horizon": horizon,
        "hit": bool(row.get(event_key)),
    }


def equity_average_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [optional_float(row.get(key)) for row in rows]
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 2)


def equity_min_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [optional_float(row.get(key)) for row in rows]
    numeric = [value for value in values if value is not None]
    return round(min(numeric), 2) if numeric else None


def equity_rate_pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(100 * numerator / denominator, 1)


def equity_risk_data_coverage(
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    option_open_interest: OptionOpenInterestSnapshot | None,
    target: date,
) -> list[dict[str, Any]]:
    rows = []
    for symbol in sorted(EQUITY_RISK_CORE_SYMBOLS | set(EQUITY_RISK_HOT_STOCKS)):
        bars = bars_by_symbol.get(symbol, [])
        latest = bar_at_or_before(bars, target)
        rows.append({"name": symbol, "status": "ok" if latest else "missing", "latest": latest.date.isoformat() if latest else "no bar"})
    rows.append(
        {
            "name": "SPY option OI",
            "status": "ok" if option_open_interest and option_open_interest.as_of <= target else "excluded",
            "latest": option_open_interest.as_of.isoformat() if option_open_interest else "not fetched",
        }
    )
    return rows


def equity_market_snapshot(bars_by_symbol: dict[str, list[MarketDailyBar]], target: date, spy_bar: MarketDailyBar | None) -> dict[str, Any]:
    return {
        "spyClose": round(spy_bar.close, 2) if spy_bar else None,
        "spyDayReturn": pct_metric(one_day_return(bars_by_symbol.get("SPY", []), target)),
        "spy63dReturn": pct_metric(trailing_return(bars_by_symbol.get("SPY", []), target, 63)),
        "qqqDayReturn": pct_metric(one_day_return(bars_by_symbol.get("QQQ", []), target)),
        "smhDayReturn": pct_metric(one_day_return(bars_by_symbol.get("SMH", []), target)),
        "rspDayReturn": pct_metric(one_day_return(bars_by_symbol.get("RSP", []), target)),
    }


def equity_next_session_shock(spy_bars: list[MarketDailyBar], target: date) -> dict[str, Any]:
    index = bar_index_at_or_before(spy_bars, target)
    if index is None or index + 1 >= len(spy_bars):
        return {"available": False, "summary": "暂无下一交易日审计数据"}
    next_bar = spy_bars[index + 1]
    next_return = one_day_return(spy_bars, next_bar.date)
    return {
        "available": True,
        "date": next_bar.date.isoformat(),
        "returnPct": pct_metric(next_return),
        "shock": bool(next_return is not None and next_return <= -0.02),
        "summary": f"下一交易日SPY {format_optional_pct(next_return)}",
    }


def option_oi_snapshot_payload(snapshot: OptionOpenInterestSnapshot) -> dict[str, Any]:
    return {
        "symbol": snapshot.symbol,
        "asOf": snapshot.as_of.isoformat(),
        "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else "",
        "putOpenInterest": round(snapshot.put_open_interest),
        "callOpenInterest": round(snapshot.call_open_interest),
        "putCallOpenInterestRatio": snapshot.put_call_open_interest_ratio,
        "putCallVolumeRatio": snapshot.put_call_volume_ratio,
        "currentPrice": snapshot.current_price,
        "source": snapshot.source,
    }


def parkinson_daily_volatility(bar: MarketDailyBar) -> float | None:
    if bar.high <= 0 or bar.low <= 0 or bar.high < bar.low:
        return None
    return abs(math.log(bar.high / bar.low)) / math.sqrt(4 * math.log(2))


def parkinson_vol_window(bars: list[MarketDailyBar], target: date, window: int) -> list[float]:
    history = [bar for bar in bars if bar.date <= target]
    if len(history) < window:
        return []
    values = [parkinson_daily_volatility(bar) for bar in history[-window:]]
    return [value for value in values if value is not None and math.isfinite(value)]


def mean_parkinson_vol(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    values = parkinson_vol_window(bars, target, window)
    if len(values) < window:
        return None
    return sum(values) / len(values)


def annualized_parkinson_vol(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    daily_vol = mean_parkinson_vol(bars, target, window)
    return daily_vol * math.sqrt(252) if daily_vol is not None else None


def adaptive_parkinson_target_vol(bars: list[MarketDailyBar], target: date, *, window: int = 22, lookback: int = 65) -> float | None:
    history = [bar for bar in bars if bar.date <= target]
    if len(history) < window + 5:
        return None
    start_index = max(window - 1, len(history) - lookback)
    realized: list[float] = []
    for end_index in range(start_index, len(history)):
        window_bars = history[end_index - window + 1: end_index + 1]
        values = [parkinson_daily_volatility(bar) for bar in window_bars]
        clean = [value for value in values if value is not None and math.isfinite(value)]
        if len(clean) == window:
            realized.append((sum(clean) / len(clean)) * math.sqrt(252))
    if not realized:
        return None
    raw_target = median(realized)
    candidates = (0.08, 0.10, 0.12, 0.14, 0.16)
    return min(candidates, key=lambda value: abs(value - raw_target))


def equity_risk_tone(score: float) -> str:
    if score >= 75:
        return "restrictive"
    if score >= 60:
        return "caution"
    if score >= 40:
        return "neutral"
    return "supportive"


def unavailable_equity_impact(summary: str) -> dict[str, Any]:
    return {
        "available": False,
        "proxy": "S&P 500 price-index proxy for SPY",
        "basis": "同类宏观评分水平 + 3M评分变化",
        "sampleSize": 0,
        "forward1mMedian": None,
        "forward3mMedian": None,
        "forward6mMedian": None,
        "hitRate3m": None,
        "avgMaxDrawdown3m": None,
        "confidence": "low",
        "confidenceLabel": "低",
        "tone": "neutral",
        "summary": summary,
    }


def equity_impact_confidence(sample_size: int, forward_3m: list[float], signal_confidence: str) -> dict[str, str]:
    spread = max(forward_3m) - min(forward_3m) if forward_3m else 0.0
    key = "high" if sample_size >= 12 and spread <= 10 else "medium" if sample_size >= 6 else "low"
    if signal_confidence == "low" and key == "high":
        key = "medium"
    return {"key": key, "label": {"high": "高", "medium": "中", "low": "低"}[key]}
