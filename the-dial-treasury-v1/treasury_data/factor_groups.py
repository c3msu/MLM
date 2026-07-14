"""Treasury factor-group scoring and compatibility factor construction.

This module owns the scorecard assembly chain. build_dashboard re-exports its
public functions to preserve the historical import surface.
"""
from __future__ import annotations

import math
from datetime import date
from statistics import median
from typing import Any

from .dashboard_format import (
    format_yield,
    money_billions_value,
    money_from_millions,
    money_trillions_from_billions,
    parse_dashboard_date,
    parse_number,
    qra_supply_note,
)
from .fetch import EXPECTED_SOURCE_CADENCE_DAYS, parse_source_latest_date
from .scoring_bhadial import bhadial_factor
from .series_math import historical_percentile, percentile_label, sampled_indices, window_start
from .sources import (
    AcmRecord,
    CftcTreasuryPosition,
    DebtLimitStatus,
    NewsItem,
    PrimaryDealerStats,
    QuarterlyRefunding,
    TicHoldings,
)


REMOTE_COMPATIBILITY_SOURCE = "us-treasury-bonds-monitor-luffa"

__all__ = [
    "REMOTE_COMPATIBILITY_SOURCE",
    "auction_demand_signal",
    "auction_percentile_points",
    "build_fed_path",
    "build_fed_path_audit",
    "build_groups",
    "chair_transition_compatibility_factor",
    "compatibility_factor",
    "cftc_leveraged_position_factor",
    "fed_path_compatibility_factor",
    "growth_momentum_compatibility_factor",
    "high_pressure_score",
    "inflation_tracking_score",
    "long_bond_auction_compatibility_factor",
    "low_preference_score",
    "macro_fundamental_factors",
    "manual_placeholder_compatibility_factor",
    "market_liquidity_compatibility_factor",
    "primary_dealer_inventory_compatibility_factor",
]


def _future_fomc_meetings(
    *,
    as_of: date,
    calendar_events: list[Any],
) -> list[dict[str, str]]:
    """Return deduplicated official FOMC decisions that are not before the snapshot."""

    meetings: dict[date, dict[str, str]] = {}
    for event in calendar_events:
        event_date = getattr(event, "date", None)
        title = str(getattr(event, "title", "") or "").strip()
        source = str(getattr(event, "source", "") or "").strip()
        if not isinstance(event_date, date) or event_date < as_of:
            continue
        if not title.upper().startswith("FOMC"):
            continue
        if "federal reserve" not in source.lower():
            continue
        meetings[event_date] = {
            "date": event_date.isoformat(),
            "label": event_date.strftime("%-m/%-d"),
            "title": title,
            "source": source,
        }
    return [meetings[meeting_date] for meeting_date in sorted(meetings)]


def build_fed_path(
    ind: dict[str, Any],
    *,
    as_of: date,
    calendar_events: list[Any],
) -> list[dict[str, int | str]]:
    """Fail closed until meeting-level, calibrated probability inputs are available.

    The current public ``ZQ.F`` input is one continuous-contract monthly-average
    rate.  It can inform a directional scenario, but it cannot identify separate
    hike/hold/cut probabilities for each FOMC meeting.  Returning no probability
    bars prevents directional model scores from being presented as market odds.
    """

    del ind, as_of, calendar_events
    return []


def _fed_directional_scenario(ind: dict[str, Any]) -> dict[str, Any]:
    """Map available public inputs to a coarse direction, never to market odds."""

    inflation_values = [
        value
        for key in ("cpi_yoy", "pce_yoy", "core_pce_yoy", "trimmed_mean_pce_yoy")
        if (value := _indicator_value(ind, key)) is not None
    ]
    inflation_pressure = max(inflation_values, default=None)
    two_year_move = _indicator_value(ind, "two_year_m1_change_bp")
    futures_rate = _indicator_value(ind, "fed_funds_futures_implied_rate")
    effective_rate = _indicator_value(ind, "dff")
    futures_gap_bp = (
        (futures_rate - effective_rate) * 100
        if futures_rate is not None and effective_rate is not None
        else None
    )

    hawkish_votes = 0
    dovish_votes = 0
    drivers: list[str] = []
    if two_year_move is not None:
        drivers.append(f"2Y one-month change {two_year_move:+.1f}bp")
        hawkish_votes += int(two_year_move >= 10)
        dovish_votes += int(two_year_move <= -10)
    if inflation_pressure is not None:
        drivers.append(f"highest tracked inflation rate {inflation_pressure:.2f}%")
        hawkish_votes += int(inflation_pressure >= 3.0)
        dovish_votes += int(inflation_pressure <= 2.2)
    if futures_gap_bp is not None:
        drivers.append(f"continuous ZQ implied-rate gap versus EFFR {futures_gap_bp:+.1f}bp")
        hawkish_votes += int(futures_gap_bp >= 10)
        dovish_votes += int(futures_gap_bp <= -10)

    if not drivers:
        direction = None
        direction_label = "insufficient inputs"
    elif hawkish_votes >= 2 and hawkish_votes > dovish_votes:
        direction = "restrictive-bias"
        direction_label = "modeled restrictive bias"
    elif dovish_votes >= 2 and dovish_votes > hawkish_votes:
        direction = "easing-bias"
        direction_label = "modeled easing bias"
    else:
        direction = "balanced"
        direction_label = "modeled balanced scenario"

    return {
        "available": direction is not None,
        "direction": direction,
        "label": direction_label,
        "drivers": drivers,
    }


def build_fed_path_audit(
    ind: dict[str, Any],
    *,
    as_of: date,
    calendar_events: list[Any],
) -> dict[str, Any]:
    """Describe the qualitative policy scenario without inventing probabilities."""

    future_meetings = _future_fomc_meetings(as_of=as_of, calendar_events=calendar_events)
    scenario = _fed_directional_scenario(ind)

    if not future_meetings:
        status = "unavailable"
        reason = "No future official FOMC decision dates are available at the dashboard as-of date."
    elif not scenario["available"]:
        status = "unavailable"
        reason = "Official future meetings are available, but the directional model inputs are insufficient."
    else:
        status = "modeled-scenario-only"
        reason = (
            "A qualitative direction is available, but meeting-level probabilities are not identifiable "
            "from one continuous-contract monthly-average rate."
        )

    return {
        "asOf": as_of.isoformat(),
        "status": status,
        "probabilitiesAvailable": False,
        "isProbability": False,
        "calibrationStatus": "not-calibrated",
        "actionable": False,
        "futureMeetings": future_meetings,
        "scenario": scenario,
        "reason": reason,
        "method": (
            "Qualitative vote across the 2Y one-month move (hawkish/easing at +10/-10bp), the highest "
            "available tracked inflation rate (3.0%/2.2%), and the continuous ZQ implied-rate gap versus "
            "EFFR (+10/-10bp). A directional bias requires at least two aligned votes. This is a modeled "
            "scenario, not a probability."
        ),
        "requiredForProbabilities": (
            "Meeting-specific Fed Funds or OIS contracts plus a documented target-range mapping, "
            "normalization rule, timestamp, and calibration validation."
        ),
    }


def _indicator_value(ind: dict[str, Any], key: str) -> float | None:
    availability = ind.get("availability")
    if isinstance(availability, dict) and key in availability and not availability[key]:
        return None
    try:
        value = float(ind[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _indicator_tag(ind: dict[str, Any], key: str, suffix: str, *, signed: bool = False) -> str:
    value = _indicator_value(ind, key)
    if value is None:
        return "--"
    sign = "+" if signed else ""
    return f"{value:{sign}.1f}{suffix}"


def _evidence_factor(
    factor: dict[str, Any],
    *,
    evidence_available: bool,
    source_mode: str,
) -> dict[str, Any]:
    """Tag display-only zeroes so conclusion aggregation can fail closed."""

    row = dict(factor)
    if evidence_available:
        row["sourceMode"] = source_mode
        row["auditEligible"] = True
        row["evidenceStatus"] = "available"
        return row
    row.update(
        {
            "tag": "数据不足",
            "v": "数据不足",
            "score": 0,
            "sourceMode": "manual-placeholder",
            "auditEligible": False,
            "evidenceStatus": "insufficient-data",
        }
    )
    if "curve" in row:
        row["curve"] = 0
    return row


def _freshness_gated_factor(
    factor: dict[str, Any],
    *,
    observed_at: date | None,
    as_of: date | None,
    source_name: str,
) -> dict[str, Any]:
    """Keep stale public observations visible without letting them vote."""
    max_age_days = EXPECTED_SOURCE_CADENCE_DAYS.get(source_name)
    if observed_at is None or as_of is None or max_age_days is None:
        return factor
    age_days = max(0, (as_of - observed_at).days)
    if age_days <= max_age_days:
        return factor
    row = dict(factor)
    row.update(
        {
            "v": "数据过期",
            "score": 0,
            "auditEligible": False,
            "evidenceStatus": "stale",
            "observationDate": observed_at.isoformat(),
            "ageDays": age_days,
            "expectedMaxAgeDays": max_age_days,
            "note": (
                f"{str(factor.get('note') or '')} 最新观测距快照{age_days}天,超过{max_age_days}天门槛;"
                "保留展示但不进入结论分母。"
            ),
        }
    )
    if "curve" in row:
        row["curve"] = 0
    return row


def inflation_tracking_score(ind: dict[str, Any]) -> int:
    broad_values = [value for key in ("cpi_yoy", "pce_yoy") if (value := _indicator_value(ind, key)) is not None]
    core_values = [value for key in ("core_pce_yoy", "trimmed_mean_pce_yoy") if (value := _indicator_value(ind, key)) is not None]
    broad = max(broad_values, default=None)
    core = max(core_values, default=None)
    if (broad is not None and broad >= 3.5) or (core is not None and core >= 3.0):
        return -2
    if (broad is not None and broad >= 2.8) or (core is not None and core >= 2.5):
        return -1
    if broad is not None and core is not None and broad <= 2.2 and core <= 2.2:
        return 1
    return 0


def macro_fundamental_factors(ind: dict[str, Any]) -> list[dict[str, Any]]:
    inflation_keys = ("cpi_yoy", "pce_yoy", "core_pce_yoy", "trimmed_mean_pce_yoy")
    available_inflation = sum(_indicator_value(ind, key) is not None for key in inflation_keys)
    inflation_score = inflation_tracking_score(ind)
    inflation_value = (
        "数据不足"
        if available_inflation == 0
        else "全面偏热"
        if inflation_score <= -2
        else "偏热"
        if inflation_score < 0
        else "温和"
        if inflation_score > 0
        else "中性"
    )
    inflation_source_mode = (
        "real-public" if available_inflation == len(inflation_keys) else "proxy-public" if available_inflation else "manual-placeholder"
    )

    ppi = _indicator_value(ind, "ppi_yoy")
    ppi_score = -2 if ppi is not None and ppi >= 5.0 else -1 if ppi is not None and ppi >= 3.0 else 0
    unrate = _indicator_value(ind, "unrate")
    payroll = _indicator_value(ind, "payroll_change_k")
    return [
        {
            "n": "通胀跟踪",
            "tag": (
                f"CPI {_indicator_tag(ind, 'cpi_yoy', '%')} / PCE {_indicator_tag(ind, 'pce_yoy', '%')} / "
                f"核心PCE {_indicator_tag(ind, 'core_pce_yoy', '%')} / "
                f"Dallas Trimmed PCE {_indicator_tag(ind, 'trimmed_mean_pce_yoy', '%')}"
            ),
            "v": inflation_value,
            "score": inflation_score,
            "sourceMode": inflation_source_mode,
            "auditEligible": available_inflation > 0,
            "evidenceStatus": "available" if available_inflation > 0 else "insufficient-data",
            "note": (
                "同时跟踪FRED CPIAUCSL、PCEPI、PCEPILFE与Dallas Fed Trimmed Mean PCE"
                "(PCETRIM12M159SFRBDAL);PCE与核心PCE用于政策反应函数,"
                "缺失序列显示为--且不按0%参与评分。"
            ),
        },
        {
            "n": "PPI 生产者物价",
            "tag": "--" if ppi is None else f"{ppi:.1f}% 同比",
            "v": "数据不足" if ppi is None else "偏热" if ppi_score < 0 else "中性",
            "score": ppi_score,
            "sourceMode": "real-public" if ppi is not None else "manual-placeholder",
            "auditEligible": ppi is not None,
            "evidenceStatus": "available" if ppi is not None else "insufficient-data",
            "note": "PPIACO同比衡量生产端通胀压力;缺失时保持中性,不把0当作通缩信号。",
        },
        {
            "n": "劳动力市场",
            "tag": "--" if unrate is None else f"失业率 {unrate:.1f}%",
            "v": "数据不足" if unrate is None else "降温" if unrate >= 4.2 else "韧性",
            "score": 0 if unrate is None else 1 if unrate >= 4.2 else -1,
            "sourceMode": "real-public" if unrate is not None else "manual-placeholder",
            "auditEligible": unrate is not None,
            "evidenceStatus": "available" if unrate is not None else "insufficient-data",
            "note": "失业率升温利多久期,劳动力韧性压制降息;缺失时不自动判为韧性。",
        },
        {
            "n": "非农就业",
            "tag": "--" if payroll is None else f"{payroll:+.0f}k",
            "v": "数据不足" if payroll is None else "稳健" if payroll > 100 else "降温",
            "score": 0 if payroll is None else -1 if payroll > 100 else 1,
            "curve": 0 if payroll is None else 1 if payroll > 100 else 0,
            "sourceMode": "real-public" if payroll is not None else "manual-placeholder",
            "auditEligible": payroll is not None,
            "evidenceStatus": "available" if payroll is not None else "insufficient-data",
            "note": "PAYEMS月差作为新增就业代理;少于两个观测时不生成方向信号。",
        },
    ]


def build_groups(
    ind: dict[str, Any],
    *,
    auctions: list[dict[str, object]],
    cftc_positions: list[CftcTreasuryPosition],
    tic_holdings: TicHoldings | None,
    acm: AcmRecord | None,
    primary_dealer_stats: PrimaryDealerStats | None,
    quarterly_refunding: QuarterlyRefunding | None,
    debt_limit_status: DebtLimitStatus | None,
    official_news: list[NewsItem],
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    dff_value = _indicator_value(ind, "dff")
    sofr_value = _indicator_value(ind, "sofr")
    dff_score = 0 if dff_value is None else -1 if dff_value >= 3.0 else 1 if dff_value <= 1.0 else 0
    dff_label = "数据不足" if dff_value is None else "限制性" if dff_score < 0 else "宽松" if dff_score > 0 else "中性"
    sofr_score = 0 if sofr_value is None else -1 if sofr_value >= 3.0 else 1 if sofr_value <= 1.0 else 0
    sofr_label = "数据不足" if sofr_value is None else "高位" if sofr_score < 0 else "低位" if sofr_score > 0 else "中性"
    real_10y_value = _indicator_value(ind, "real_10y")
    breakeven_10y_value = _indicator_value(ind, "breakeven_10y")
    rrp_trillions_value = _indicator_value(ind, "rrp_trillions")
    tga_trillions_value = _indicator_value(ind, "tga_trillions")
    soma_treasury_value = _indicator_value(ind, "soma_treasury_trillions")
    walcl_value = _indicator_value(ind, "walcl_trillions")
    percentiles = ind.get("percentiles") if isinstance(ind.get("percentiles"), dict) else {}
    two_year_score = -2 if ind["two_year_m1_change_bp"] >= 30 else -1 if ind["two_year_m1_change_bp"] >= 10 else 0
    sofr_spread_pct = percentiles.get("sofr_effr_spread")
    sofr_spread_score = -1 if sofr_spread_pct is not None and sofr_spread_pct >= 80 else 0
    bank_reserves_pct = percentiles.get("bank_reserves")
    bank_reserves_score = -1 if bank_reserves_pct is not None and bank_reserves_pct <= 20 else 1 if bank_reserves_pct is not None and bank_reserves_pct >= 60 else 0
    net_liquidity_pct = percentiles.get("net_liquidity")
    net_liquidity_score = -1 if net_liquidity_pct is not None and net_liquidity_pct <= 20 else 1 if net_liquidity_pct is not None and net_liquidity_pct >= 60 else 0
    net_liquidity_momentum_pct = percentiles.get("net_liquidity_momentum")
    net_liquidity_momentum_score = -1 if ind["net_liquidity_m1_change_trillions"] < -0.05 else 1 if ind["net_liquidity_m1_change_trillions"] > 0.05 else 0
    net_liquidity_13w_pct = percentiles.get("net_liquidity_13w_momentum")
    net_liquidity_13w_score = -1 if ind["net_liquidity_13w_change_trillions"] < -0.15 else 1 if ind["net_liquidity_13w_change_trillions"] > 0.15 else 0
    tga_deviation_pct = percentiles.get("tga_deviation")
    tga_deviation_score = -1 if ind["tga_deviation_trillions"] > 0.15 or (tga_deviation_pct is not None and tga_deviation_pct >= 80) else 1 if ind["tga_deviation_trillions"] < -0.15 else 0
    onrrp_buffer_risk_pct = percentiles.get("onrrp_buffer_risk")
    onrrp_buffer_risk_score = -2 if ind["onrrp_buffer_risk"] >= 0.75 else -1 if ind["onrrp_buffer_risk"] >= 0.35 else 0
    sofr_obfr_pct = percentiles.get("collateral_repo_friction")
    sofr_obfr_score = high_pressure_score(sofr_obfr_pct)
    sofr_iorb_pct = percentiles.get("corridor_sofr_iorb")
    sofr_iorb_score = high_pressure_score(sofr_iorb_pct)
    sofr_rrp_pct = percentiles.get("corridor_sofr_rrp")
    sofr_rrp_score = high_pressure_score(sofr_rrp_pct)
    effr_iorb_pct = percentiles.get("effr_iorb_spread")
    effr_iorb_score = high_pressure_score(effr_iorb_pct)
    cp_tbill_pct = percentiles.get("cp_tbill_spread")
    cp_tbill_score = high_pressure_score(cp_tbill_pct)
    fragmentation_pct = percentiles.get("funding_fragmentation")
    fragmentation_score = high_pressure_score(fragmentation_pct)
    real_rate_level_pct = percentiles.get("real_rate_level")
    real_curve_pct = percentiles.get("real_curve")
    treasury_vol_pct = percentiles.get("treasury_10y_vol_21d")
    curvature_pct = percentiles.get("curve_curvature_abs")
    nfci_pct = percentiles.get("nfci")
    nfci_score = -1 if ind["nfci"] > 0 or (nfci_pct is not None and nfci_pct >= 80) else 1 if ind["nfci"] < -0.5 and (nfci_pct is None or nfci_pct <= 35) else 0
    hy_oas_pct = percentiles.get("hy_oas")
    ig_oas_pct = percentiles.get("ig_oas")
    hy_ig_pct = percentiles.get("hy_ig_oas_spread")
    hy_ig_score = high_pressure_score(hy_ig_pct)
    vix_term_pct = percentiles.get("vix_term_structure")
    vix_term_score = -1 if ind["vix_term_structure"] > 1 or (vix_term_pct is not None and vix_term_pct >= 80) else 0
    dxy_vol_pct = percentiles.get("dxy_realized_vol")
    dxy_vol_score = high_pressure_score(dxy_vol_pct)
    oil_vol_dev_pct = percentiles.get("oil_vol_deviation")
    oil_vol_dev_score = high_pressure_score(oil_vol_dev_pct)
    natgas_pct = percentiles.get("natgas")
    natgas_score = high_pressure_score(natgas_pct)
    hy_credit_preference_pct = percentiles.get("hy_credit_preference")
    hy_credit_preference_score = low_preference_score(hy_credit_preference_pct)
    ig_credit_preference_pct = percentiles.get("ig_credit_preference")
    ig_credit_preference_score = low_preference_score(ig_credit_preference_pct)
    regional_bank_pct = percentiles.get("regional_bank_vs_market")
    regional_bank_score = low_preference_score(regional_bank_pct)
    risk_vs_safe_pct = percentiles.get("risk_vs_safe")
    risk_vs_safe_score = low_preference_score(risk_vs_safe_pct)
    high_beta_pct = percentiles.get("high_beta_preference")
    high_beta_score = low_preference_score(high_beta_pct)
    auction_signal = auction_demand_signal(auctions)
    cftc_factor = cftc_leveraged_position_factor(cftc_positions)
    cftc_report_date = parse_source_latest_date(cftc_factor.get("reportDate"))
    cftc_factor = _freshness_gated_factor(
        cftc_factor,
        observed_at=cftc_report_date,
        as_of=as_of,
        source_name="CFTC financial futures COT",
    )
    tic_change = tic_holdings.total.monthly_change_billions if tic_holdings and tic_holdings.total else None
    tic_score = -1 if tic_change is not None and tic_change < -50 else 1 if tic_change is not None and tic_change > 50 else 0
    tic_tag = f"{tic_holdings.period} 总量 {money_trillions_from_billions(tic_holdings.total.value_billions)}" if tic_holdings and tic_holdings.total else "待接月频解析"
    tic_factor = _evidence_factor(
        {"n": "TIC 海外持仓", "tag": tic_tag, "v": "走弱" if tic_score < 0 else "改善" if tic_score > 0 else "中性", "score": tic_score, "curve": 1 if tic_score < 0 else 0, "note": "TIC主要海外持有者为月频且滞后,用于衡量外资边际需求。"},
        evidence_available=tic_change is not None,
        source_mode="real-public",
    )
    tic_factor = _freshness_gated_factor(
        tic_factor,
        observed_at=parse_source_latest_date(tic_holdings.period) if tic_holdings else None,
        as_of=as_of,
        source_name="Treasury TIC major foreign holders",
    )
    acm_score = 1 if acm and acm.term_premium_10y > 0.35 else 0
    acm_tag = f"ACM {acm.term_premium_10y:+.2f}%" if acm else "数据不足"
    acm_factor = _evidence_factor(
        {"n": "期限溢价 (ACM)", "tag": acm_tag, "v": "估值转吸引" if acm_score > 0 else "中性", "score": acm_score, "curve": -1 if acm_score > 0 else 0, "note": "NY Fed ACM期限溢价高位时,长端估值补偿更充分;ACM缺失时不以10Y-EFFR冒充期限溢价。"},
        evidence_available=acm is not None,
        source_mode="real-public",
    )
    acm_factor = _freshness_gated_factor(
        acm_factor,
        observed_at=acm.date if acm else None,
        as_of=as_of,
        source_name="NY Fed ACM term premium",
    )
    qra_available = bool(
        quarterly_refunding
        and (
            quarterly_refunding.current_quarter_borrowing_billions is not None
            or quarterly_refunding.next_quarter_borrowing_billions is not None
        )
    )
    if quarterly_refunding:
        current_borrow = quarterly_refunding.current_quarter_borrowing_billions
        next_borrow = quarterly_refunding.next_quarter_borrowing_billions
        qra_score = -1 if current_borrow is not None and next_borrow is not None and next_borrow > current_borrow else 0
        displayed_borrow = next_borrow if next_borrow is not None else current_borrow
        qra_tag = f"{quarterly_refunding.quarter} · {money_billions_value(displayed_borrow)}"
        qra_note = qra_supply_note(quarterly_refunding)
    else:
        qra_score = 0
        qra_tag = "待接Treasury QRA"
        qra_note = "官方季度再融资文档不可用时不填入估计值。"
    qra_factor = _evidence_factor(
        {"n": "发行节奏 / QRA", "tag": qra_tag, "v": "供给增加" if qra_score < 0 else "中性", "score": qra_score, "curve": 1 if qra_score < 0 else 0, "note": qra_note},
        evidence_available=qra_available,
        source_mode="real-public",
    )
    qra_factor = _freshness_gated_factor(
        qra_factor,
        observed_at=quarterly_refunding.release_date if quarterly_refunding else None,
        as_of=as_of,
        source_name="U.S. Treasury quarterly refunding documents",
    )
    if debt_limit_status:
        debt_headroom_score = -2 if debt_limit_status.headroom_millions < 500_000 else -1 if debt_limit_status.headroom_millions < 1_000_000 else 0
        debt_headroom_tag = money_from_millions(debt_limit_status.headroom_millions)
        debt_headroom_note = (
            f"Fiscal Data {debt_limit_status.record_date.isoformat()}: statutory limit "
            f"{money_from_millions(debt_limit_status.statutory_limit_millions)}, "
            f"debt subject to limit {money_from_millions(debt_limit_status.debt_subject_to_limit_millions)}."
        )
    else:
        debt_headroom_score = 0
        debt_headroom_tag = "待接Fiscal Data"
        debt_headroom_note = "DTS Debt Subject to Limit不可用时不填入估计值。"
    debt_limit_factor = _evidence_factor(
        {"n": "债务上限空间", "tag": debt_headroom_tag, "v": "紧张" if debt_headroom_score < 0 else "充足", "score": debt_headroom_score, "curve": 1 if debt_headroom_score < 0 else 0, "note": debt_headroom_note},
        evidence_available=debt_limit_status is not None,
        source_mode="real-public",
    )
    debt_limit_factor = _freshness_gated_factor(
        debt_limit_factor,
        observed_at=debt_limit_status.record_date if debt_limit_status else None,
        as_of=as_of,
        source_name="Treasury Fiscal Data debt subject to limit",
    )
    primary_dealer_factor = primary_dealer_inventory_compatibility_factor(primary_dealer_stats)
    primary_dealer_factor = _freshness_gated_factor(
        primary_dealer_factor,
        observed_at=primary_dealer_stats.as_of if primary_dealer_stats else None,
        as_of=as_of,
        source_name="NY Fed primary dealer statistics",
    )
    return [
        {
            "id": "g1",
            "name": "货币政策",
            "en": "Monetary Policy",
            "weight": 25,
            "factors": [
                {
                    "n": "联邦基金目标利率",
                    "tag": ind["target_range"] if dff_value is not None else "--",
                    "v": dff_label,
                    "score": dff_score,
                    "sourceMode": "real-public" if dff_value is not None else "manual-placeholder",
                    "auditEligible": dff_value is not None,
                    "note": f"有效联邦基金利率 {dff_value:.2f}%; >=3%视为限制性,<=1%视为宽松。" if dff_value is not None else "DFF缺失时不生成政策方向贡献。",
                },
                {"n": "2Y 市场政策代理", "tag": f"1月 {ind['two_year_m1_change_bp']:+.0f}bp", "v": "偏鹰" if two_year_score < 0 else "中性", "score": two_year_score, "curve": 1 if two_year_score < 0 else 0, "note": "用2Y收益率月度变化代理政策路径再定价。"},
                fed_path_compatibility_factor(ind),
                chair_transition_compatibility_factor(official_news),
                {
                    "n": "SOFR 融资锚",
                    "tag": f"{sofr_value:.2f}%" if sofr_value is not None else "--",
                    "v": sofr_label,
                    "score": sofr_score,
                    "sourceMode": "real-public" if sofr_value is not None else "manual-placeholder",
                    "auditEligible": sofr_value is not None,
                    "note": "SOFR >=3%视为高位融资锚,<=1%视为低位;避免把任意非缺失值都判为限制性。" if sofr_value is not None else "SOFR缺失时不生成融资锚贡献。",
                },
                _evidence_factor(
                    {
                        "n": "SOFR-EFFR利差",
                        "tag": f"{ind['sofr_effr_spread_bp']:+.0f}bp · {percentile_label(sofr_spread_pct)}",
                        "v": "融资压力" if sofr_spread_score < 0 else "正常",
                        "score": sofr_spread_score,
                        "note": "参考The Dial Funding思路,用SOFR相对EFFR利差的5年历史百分位代理担保融资压力。",
                    },
                    evidence_available=sofr_spread_pct is not None,
                    source_mode="derived-public",
                ),
                bhadial_factor(
                    module="Funding",
                    name="SOFR-OBFR回购摩擦",
                    tag=f"{ind['sofr_obfr_spread_bp']:+.0f}bp · {percentile_label(sofr_obfr_pct)}",
                    value="回购偏紧" if sofr_obfr_score < 0 else "正常",
                    score=sofr_obfr_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的Collateral/Repo Friction: SOFR-OBFR,衡量担保回购相对无担保隔夜融资的压力。",
                    evidence_available=sofr_obfr_pct is not None,
                ),
                bhadial_factor(
                    module="Funding",
                    name="SOFR-IORB走廊摩擦",
                    tag=f"{ind['sofr_iorb_spread_bp']:+.0f}bp · {percentile_label(sofr_iorb_pct)}",
                    value="接近上沿" if sofr_iorb_score < 0 else "正常",
                    score=sofr_iorb_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的Corridor Friction 1: SOFR-IORB,衡量市场担保融资利率相对准备金利率上沿的位置。",
                    evidence_available=sofr_iorb_pct is not None,
                ),
                bhadial_factor(
                    module="Funding",
                    name="SOFR-ON RRP走廊摩擦",
                    tag=f"{ind['sofr_rrp_award_spread_bp']:+.0f}bp · {percentile_label(sofr_rrp_pct)}",
                    value="高于地板" if sofr_rrp_score < 0 else "正常",
                    score=sofr_rrp_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的Corridor Friction 2: SOFR-ON RRP award,衡量市场利率相对美联储隔夜逆回购利率地板的压力。",
                    evidence_available=sofr_rrp_pct is not None,
                ),
                bhadial_factor(
                    module="Funding",
                    name="EFFR-IORB利差",
                    tag=f"{ind['effr_iorb_spread_bp']:+.0f}bp · {percentile_label(effr_iorb_pct)}",
                    value="银行资金偏紧" if effr_iorb_score < 0 else "正常",
                    score=effr_iorb_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的EFFR-IORB Spread: 有效联邦基金利率相对准备金利率,观察银行间资金是否接近走廊上沿。",
                    evidence_available=effr_iorb_pct is not None,
                ),
                bhadial_factor(
                    module="Funding",
                    name="商票-TBill利差",
                    tag=f"{ind['cp_tbill_spread_bp']:+.0f}bp · {percentile_label(cp_tbill_pct)}",
                    value="短融承压" if cp_tbill_score < 0 else "正常",
                    score=cp_tbill_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的CP-TBill Spread: FRED 90日AA金融商票减3个月TBill,反映短期私人信用相对无风险利率的压力。",
                    evidence_available=cp_tbill_pct is not None,
                ),
                bhadial_factor(
                    module="Funding",
                    name="资金分裂度(21D)",
                    tag=f"{ind['funding_fragmentation_21d']:.2f} · {percentile_label(fragmentation_pct)}",
                    value="分裂" if fragmentation_score < 0 else "一致",
                    score=fragmentation_score,
                    source_mode="derived-public",
                    note="Bhadial Funding Fragmentation近似: 对SOFR-OBFR、SOFR-IORB、SOFR-ON RRP三条走廊利差做稳健z-score离散度并用21日EMA平滑。",
                    evidence_available=fragmentation_pct is not None,
                ),
                {
                    "n": "SOMA Treasury持仓",
                    "tag": f"${soma_treasury_value:.2f}T" if soma_treasury_value is not None else "--",
                    "v": "QT存量约束" if soma_treasury_value is not None else "数据不足",
                    "score": 0,
                    "sourceMode": "real-public" if soma_treasury_value is not None else "manual-placeholder",
                    "auditEligible": False,
                    "evidenceStatus": "display-only" if soma_treasury_value is not None else "insufficient-data",
                    "note": "以FRED TREAST跟踪美联储持有的美国国债规模;当前仅作展示,未定义方向阈值,不进入结论分母。",
                },
                {
                    "n": "资产负债表 / 总资产",
                    "tag": f"WALCL ${walcl_value:.2f}T" if walcl_value is not None else "--",
                    "v": "中性" if walcl_value is not None else "数据不足",
                    "score": 0,
                    "sourceMode": "real-public" if walcl_value is not None else "manual-placeholder",
                    "auditEligible": False,
                    "evidenceStatus": "display-only" if walcl_value is not None else "insufficient-data",
                    "note": "以FRED WALCL跟踪美联储资产负债表总规模;当前仅作展示,未定义方向阈值,不进入结论分母。",
                },
            ],
        },
        {
            "id": "g2",
            "name": "宏观基本面",
            "en": "Macro Fundamentals",
            "weight": 25,
            "factors": [
                *macro_fundamental_factors(ind),
                growth_momentum_compatibility_factor(ind),
            ],
        },
        {
            "id": "g3",
            "name": "供给与技术面",
            "en": "Supply & Technicals",
            "weight": 15,
            "factors": [
                long_bond_auction_compatibility_factor(auctions),
                qra_factor,
                debt_limit_factor,
                {"n": "10Y 收益率动量", "tag": f"1月 {ind['ten_year_m1_change_bp']:+.0f}bp", "v": "上行", "score": -1 if ind["ten_year_m1_change_bp"] > 10 else 0, "curve": 1 if ind["s5s30"] > 50 else 0, "note": "10Y月度上行代表供给/期限溢价压力。"},
                {
                    "n": "5s30s 曲线",
                    "tag": f"{ind['s5s30']:.0f}bp",
                    "v": "偏陡" if ind["s5s30"] > 25 else "倒挂" if ind["s5s30"] < -25 else "平坦",
                    "score": -1 if ind["s5s30"] > 60 else 0,
                    "curve": 1 if ind["s5s30"] > 25 else -1 if ind["s5s30"] < -25 else 0,
                    "note": "5s30s大于+25bp才贡献做陡方向,低于-25bp贡献做平,中间区间保持中性。",
                },
                bhadial_factor(
                    module="Treasury",
                    name="10Y-3M曲线",
                    tag=f"{ind['s10s3m']:.0f}bp",
                    value="正斜率" if ind["s10s3m"] > 0 else "倒挂",
                    score=0,
                    curve=1 if ind["s10s3m"] > 100 else -1 if ind["s10s3m"] < -100 else 0,
                    source_mode="real-public",
                    note="Bhadial Treasury的10Y-3M Spread,用U.S. Treasury curve直接计算长短端斜率。",
                ),
                bhadial_factor(
                    module="Treasury",
                    name="30Y-10Y期限溢价",
                    tag=f"{ind['s30s10']:.0f}bp",
                    value="长端补偿" if ind["s30s10"] > 30 else "平坦",
                    score=0,
                    curve=1 if ind["s30s10"] > 45 else 0,
                    source_mode="real-public",
                    note="Bhadial Treasury的30Y-10Y Term Premium公开代理,用30Y减10Y衡量超长端期限补偿和需求变化。",
                ),
                bhadial_factor(
                    module="Treasury",
                    name="曲线曲率(绝对值)",
                    tag=f"{ind['curve_curvature_abs_bp']:.0f}bp",
                    value="曲线变形" if ind["curve_curvature_abs_bp"] > 80 else "平稳",
                    score=-1 if ind["curve_curvature_abs_bp"] > 80 else 0,
                    curve=1 if ind["curve_curvature_abs_bp"] > 80 else 0,
                    source_mode="derived-public",
                    note=(
                        "Bhadial Treasury的Curve Curvature Abs近似: 10Y收益率相对2Y-30Y非等距线性弦"
                        "在10Y位置的绝对残差;2Y、10Y、30Y期限间距不等,不能使用等权二阶差分。"
                    ),
                    evidence_available=curvature_pct is not None,
                ),
                _evidence_factor(
                    {
                        "n": "TGA 与现金管理",
                        "tag": "--" if tga_trillions_value is None else f"${tga_trillions_value:.2f}T",
                        "v": "抽水" if tga_trillions_value is not None and tga_trillions_value > 0.7 else "中性",
                        "score": -1 if tga_trillions_value is not None and tga_trillions_value > 0.7 else 0,
                        "note": "TGA高位会边际抽走银行体系流动性。",
                    },
                    evidence_available=tga_trillions_value is not None,
                    source_mode="real-public",
                ),
            ],
        },
        {
            "id": "g4",
            "name": "需求与持仓",
            "en": "Demand & Positioning",
            "weight": 15,
            "factors": [
                _evidence_factor(
                    {
                        "n": "拍卖需求",
                        "tag": auction_signal["tag"],
                        "v": auction_signal["label"],
                        "score": auction_signal["score"],
                        "note": auction_signal["note"],
                    },
                    evidence_available=auction_signal.get("percentile") is not None,
                    source_mode="real-public",
                ),
                tic_factor,
                cftc_factor,
                primary_dealer_factor,
            ],
        },
        {
            "id": "g5",
            "name": "相对价值",
            "en": "Relative Value",
            "weight": 10,
            "factors": [
                acm_factor,
                {
                    "n": "实际利率",
                    "tag": f"10Y TIPS {real_10y_value:.2f}%" if real_10y_value is not None else "10Y TIPS --",
                    "v": "偏高" if real_10y_value is not None and real_10y_value > 2.0 else "中性" if real_10y_value is not None else "数据不足",
                    "score": 1 if real_10y_value is not None and real_10y_value > 2.0 else 0,
                    "curve": -1 if real_10y_value is not None and real_10y_value > 2.0 else 0,
                    "sourceMode": "real-public" if real_10y_value is not None else "manual-placeholder",
                    "auditEligible": real_10y_value is not None,
                    "note": "高实际利率提升长期债估值吸引力。" if real_10y_value is not None else "DFII10缺失时不生成实际利率贡献。",
                },
                bhadial_factor(
                    module="Rates",
                    name="真实利率水平",
                    tag=f"{ind['real_rate_level']:.2f}% · {percentile_label(real_rate_level_pct)}",
                    value="融资偏紧" if ind["real_rate_level"] > 2 else "中性",
                    score=1 if ind["real_rate_level"] > 2 else 0,
                    curve=-1 if ind["real_rate_level"] > 2 else 0,
                    source_mode="derived-public",
                    note="Bhadial Rates的Real Rate Level: 60% 5Y TIPS + 40% 10Y TIPS;宏观上越高越紧,在本久期计分中代表估值补偿更高。",
                    evidence_available=real_rate_level_pct is not None and _indicator_value(ind, "real_rate_level") is not None,
                ),
                bhadial_factor(
                    module="Rates",
                    name="真实曲线(10Y-5Y)",
                    tag=f"{ind['real_curve_10y5y_bp']:+.0f}bp · {percentile_label(real_curve_pct)}",
                    value="正斜率" if ind["real_curve_10y5y_bp"] > 0 else "倒挂",
                    score=0,
                    curve=1 if ind["real_curve_10y5y_bp"] > 25 else -1 if ind["real_curve_10y5y_bp"] < -25 else 0,
                    source_mode="derived-public",
                    note="Bhadial Rates的Real Curve: 10Y TIPS - 5Y TIPS,用于区分真实利率曲线的增长预期与期限补偿。",
                    evidence_available=real_curve_pct is not None and _indicator_value(ind, "real_curve_10y5y_bp") is not None,
                ),
                {
                    "n": "盈亏平衡通胀",
                    "tag": f"10Y BEI {breakeven_10y_value:.2f}%" if breakeven_10y_value is not None else "10Y BEI --",
                    "v": "偏高" if breakeven_10y_value is not None and breakeven_10y_value > 2.4 else "中性" if breakeven_10y_value is not None else "数据不足",
                    "score": -1 if breakeven_10y_value is not None and breakeven_10y_value > 2.4 else 0,
                    "sourceMode": "real-public" if breakeven_10y_value is not None else "manual-placeholder",
                    "auditEligible": breakeven_10y_value is not None,
                    "note": "通胀补偿高位不利名义久期。" if breakeven_10y_value is not None else "T10YIE缺失时不生成通胀补偿贡献。",
                },
                {
                    "n": "2s10s 曲线",
                    "tag": f"{ind['s2s10']:.0f}bp",
                    "v": "正斜率" if ind["s2s10"] > 25 else "倒挂" if ind["s2s10"] < -25 else "平坦",
                    "score": 0,
                    "curve": 1 if ind["s2s10"] > 25 else -1 if ind["s2s10"] < -25 else 0,
                    "note": "2s10s大于+25bp贡献做陡,低于-25bp贡献做平;中间区间不强行给方向。",
                },
                manual_placeholder_compatibility_factor("互换利差", "待接swap spread", "手动", "原站保留互换利差维度;本地未接入授权互换曲线,默认不改变评分,可在计分卡手动调整。"),
            ],
        },
        {
            "id": "g6",
            "name": "情绪与流动性",
            "en": "Sentiment & Liquidity",
            "weight": 10,
            "factors": [
                _evidence_factor(
                    {
                        "n": "10Y实现波动率",
                        "tag": f"21D {ind['ten_year_realized_vol_21d_bp']:.1f}bp ann. · {percentile_label(treasury_vol_pct)}",
                        "v": "高波动" if high_pressure_score(treasury_vol_pct) < 0 else "中性",
                        "score": high_pressure_score(treasury_vol_pct),
                        "note": (
                            "由U.S. Treasury curve 10Y日度收益率变动计算21个完整日变动窗口的年化样本波动率,"
                            "并按滚动历史百分位评分;作为MOVE授权数据不可用时的公开代理。"
                        ),
                    },
                    evidence_available=treasury_vol_pct is not None,
                    source_mode="derived-public",
                ),
                market_liquidity_compatibility_factor(ind),
                manual_placeholder_compatibility_factor("新老券利差", "待接on/off-run spread", "手动", "原站保留新老券利差维度;本地未接入逐券报价和融资微观数据,默认不改变评分,可手动维护。"),
                _evidence_factor(
                    {
                        "n": "银行准备金",
                        "tag": f"${ind['bank_reserves_trillions']:.2f}T · {percentile_label(bank_reserves_pct)}",
                        "v": "宽松" if bank_reserves_score > 0 else "偏紧" if bank_reserves_score < 0 else "中性",
                        "score": bank_reserves_score,
                        "note": "FRED WRESBAL按5年历史百分位衡量银行体系准备金缓冲。",
                    },
                    evidence_available=bank_reserves_pct is not None,
                    source_mode="real-public",
                ),
                _evidence_factor(
                    {
                        "n": "净流动性",
                        "tag": f"${ind['net_liquidity_trillions']:.2f}T · {percentile_label(net_liquidity_pct)}",
                        "v": "宽松" if net_liquidity_score > 0 else "偏紧" if net_liquidity_score < 0 else "中性",
                        "score": net_liquidity_score,
                        "note": "参考The Dial Net Liquidity,用WALCL - TGA - ON RRP计算公开代理并按5年历史百分位评分。",
                    },
                    evidence_available=net_liquidity_pct is not None and _indicator_value(ind, "net_liquidity_trillions") is not None,
                    source_mode="derived-public",
                ),
                _evidence_factor(
                    {
                        "n": "流动性动量",
                        "tag": f"1月 {ind['net_liquidity_m1_change_trillions']:+.2f}T · {percentile_label(net_liquidity_momentum_pct)}",
                        "v": "扩张" if net_liquidity_momentum_score > 0 else "收缩" if net_liquidity_momentum_score < 0 else "中性",
                        "score": net_liquidity_momentum_score,
                        "note": "净流动性1个月变化的历史百分位,用于补充The Dial Liquidity Momentum思路。",
                    },
                    evidence_available=net_liquidity_momentum_pct is not None,
                    source_mode="derived-public",
                ),
                bhadial_factor(
                    module="Liquidity",
                    name="13周净流动性动量",
                    tag=f"13周 {ind['net_liquidity_13w_change_trillions']:+.2f}T · {percentile_label(net_liquidity_13w_pct)}",
                    value="扩张" if net_liquidity_13w_score > 0 else "收缩" if net_liquidity_13w_score < 0 else "中性",
                    score=net_liquidity_13w_score,
                    source_mode="derived-public",
                    note="Bhadial Liquidity的Net Liquidity Momentum (13W): WALCL - TGA - ON RRP的13周绝对变化,捕捉QT、财政和RRP迁移的中期动量。",
                    evidence_available=net_liquidity_13w_pct is not None,
                ),
                bhadial_factor(
                    module="Liquidity",
                    name="TGA偏离度",
                    tag=f"{ind['tga_deviation_trillions']:+.2f}T · {percentile_label(tga_deviation_pct)}",
                    value="抽水偏强" if tga_deviation_score < 0 else "释放" if tga_deviation_score > 0 else "正常",
                    score=tga_deviation_score,
                    source_mode="derived-public",
                    note="Bhadial Liquidity的TGA Deviation: TGA相对52周滚动中位数的偏离;正值代表财政现金累积并抽走准备金。",
                    evidence_available=tga_deviation_pct is not None,
                ),
                {
                    "n": "ON RRP",
                    "tag": f"${rrp_trillions_value:.3f}T" if rrp_trillions_value is not None else "--",
                    "v": "低位" if rrp_trillions_value is not None and rrp_trillions_value < 0.05 else "中性" if rrp_trillions_value is not None else "数据不足",
                    "score": -1 if rrp_trillions_value is not None and rrp_trillions_value < 0.05 else 0,
                    "sourceMode": "real-public" if rrp_trillions_value is not None else "manual-placeholder",
                    "auditEligible": rrp_trillions_value is not None,
                    "note": "RRP接近枯竭时,流动性缓冲下降。" if rrp_trillions_value is not None else "RRPONTSYD缺失时不生成流动性缓冲贡献。",
                },
                bhadial_factor(
                    module="Liquidity",
                    name="ON RRP缓冲风险",
                    tag=f"{ind['onrrp_buffer_risk']:.2f} · {percentile_label(onrrp_buffer_risk_pct)}",
                    value="接近耗尽" if onrrp_buffer_risk_score < 0 else "有缓冲",
                    score=onrrp_buffer_risk_score,
                    source_mode="derived-public",
                    note="Bhadial Liquidity的ON RRP Buffer Risk: $100B以下用squared transformation刻画非线性耗尽风险,避免把RRP低位误读为宽松。",
                    evidence_available=onrrp_buffer_risk_pct is not None,
                ),
                _evidence_factor(
                    {"n": "信用利差", "tag": f"HY {ind['hy_oas']:.2f}% / IG {ind['ig_oas']:.2f}%", "v": "偏紧" if ind["hy_oas"] < 4 else "承压", "score": 0 if ind["hy_oas"] < 4 else -1, "note": "FRED ICE BofA OAS用于代理信用风险与风险偏好。"},
                    evidence_available=hy_oas_pct is not None and ig_oas_pct is not None,
                    source_mode="real-public",
                ),
                bhadial_factor(
                    module="Credit",
                    name="金融条件指数(NFCI)",
                    tag=f"{ind['nfci']:+.2f} · {percentile_label(nfci_pct)}",
                    value="宽松" if nfci_score > 0 else "偏紧" if nfci_score < 0 else "中性",
                    score=nfci_score,
                    source_mode="real-public",
                    note="Bhadial Credit的NFCI: Chicago Fed National Financial Conditions Index,正值表示金融条件紧于均值,负值表示宽松。",
                    evidence_available=nfci_pct is not None,
                ),
                bhadial_factor(
                    module="Credit",
                    name="HY-IG利差",
                    tag=f"{ind['hy_ig_oas_spread_bp']:+.0f}bp · {percentile_label(hy_ig_pct)}",
                    value="信用分层" if hy_ig_score < 0 else "正常",
                    score=hy_ig_score,
                    source_mode="derived-public",
                    note="补齐Bhadial Credit的信用分层维度;本地用FRED HY OAS - IG OAS作为公开信用相对压力代理。",
                    evidence_available=hy_ig_pct is not None,
                ),
                bhadial_factor(
                    module="Credit",
                    name="HY信用偏好(HY/UST)",
                    tag=f"{ind['hy_credit_preference']:.2f} · {percentile_label(hy_credit_preference_pct)}",
                    value="偏好改善" if hy_credit_preference_score > 0 else "信用承压" if hy_credit_preference_score < 0 else "中性",
                    score=hy_credit_preference_score,
                    source_mode="proxy-public",
                    note="Bhadial HY Credit的公开代理: FRED ICE US High Yield total return index相对10Y美债价格代理,用于替代HYG/IEI ETF历史。",
                    evidence_available=hy_credit_preference_pct is not None,
                ),
                bhadial_factor(
                    module="Credit",
                    name="IG信用偏好(IG/UST)",
                    tag=f"{ind['ig_credit_preference']:.2f} · {percentile_label(ig_credit_preference_pct)}",
                    value="承接改善" if ig_credit_preference_score > 0 else "信用承压" if ig_credit_preference_score < 0 else "中性",
                    score=ig_credit_preference_score,
                    source_mode="proxy-public",
                    note="Bhadial IG Credit的公开代理: FRED ICE US Corporate total return index相对10Y美债价格代理,用于替代LQD/IEF ETF历史。",
                    evidence_available=ig_credit_preference_pct is not None,
                ),
                bhadial_factor(
                    module="Credit",
                    name="银行股相对S&P500",
                    tag=f"{ind['regional_bank_vs_market']:.2f} · {percentile_label(regional_bank_pct)}",
                    value="银行改善" if regional_bank_score > 0 else "银行承压" if regional_bank_score < 0 else "中性",
                    score=regional_bank_score,
                    source_mode="proxy-public",
                    note="Bhadial Regional Banks vs SPY的公开代理: FRED NASDAQ Bank Index相对S&P 500;不是KRE/SPY ETF精确替代,但能捕捉银行股相对风险偏好。",
                    evidence_available=regional_bank_pct is not None,
                ),
                bhadial_factor(
                    module="Risk",
                    name="VIX期限结构",
                    tag=f"{ind['vix_term_structure']:.2f} · VIX3M {ind['vix_3m']:.2f}",
                    value="倒挂" if vix_term_score < 0 else "contango",
                    score=vix_term_score,
                    source_mode="derived-public",
                    note="Bhadial Risk的VIX Term Structure: VIX / VIX 3M,大于1代表波动率倒挂和风险偏好承压。",
                    evidence_available=vix_term_pct is not None,
                ),
                bhadial_factor(
                    module="Risk",
                    name="风险资产/美债代理",
                    tag=f"{ind['risk_vs_safe']:.2f} · {percentile_label(risk_vs_safe_pct)}",
                    value="risk-on" if risk_vs_safe_score > 0 else "risk-off" if risk_vs_safe_score < 0 else "中性",
                    score=risk_vs_safe_score,
                    source_mode="proxy-public",
                    note="Bhadial Risk vs Safe的公开代理: FRED S&P 500相对DGS10派生的10Y美债价格代理;用于替代SPY/TLT ETF历史。",
                    evidence_available=risk_vs_safe_pct is not None,
                ),
                bhadial_factor(
                    module="Risk",
                    name="高Beta偏好(NDX/US500)",
                    tag=f"{ind['high_beta_preference']:.2f} · {percentile_label(high_beta_pct)}",
                    value="高Beta占优" if high_beta_score > 0 else "高Beta退潮" if high_beta_score < 0 else "中性",
                    score=high_beta_score,
                    source_mode="proxy-public",
                    note="Bhadial High-Beta Preference的公开代理: FRED Nasdaq-100 Total Return相对Nasdaq US 500 Large Cap Total Return,用于替代IWM/SPY ETF历史。",
                    evidence_available=high_beta_pct is not None,
                ),
                bhadial_factor(
                    module="External",
                    name="美元实现波动率",
                    tag=f"{ind['dxy_realized_vol']:.1f}% · {percentile_label(dxy_vol_pct)}",
                    value="外部冲击" if dxy_vol_score < 0 else "稳定",
                    score=dxy_vol_score,
                    source_mode="derived-public",
                    note="Bhadial External的FX Realized Volatility近似: 对FRED美元广义指数计算63日年化实现波动率。",
                    evidence_available=dxy_vol_pct is not None,
                ),
                bhadial_factor(
                    module="External",
                    name="原油波动偏离",
                    tag=f"{ind['oil_vol_deviation']:.1f} · {percentile_label(oil_vol_dev_pct)}",
                    value="油市冲击" if oil_vol_dev_score < 0 else "正常",
                    score=oil_vol_dev_score,
                    source_mode="derived-public",
                    note="Bhadial External的Oil Volatility Deviation: OVX相对约1年滚动中位数的正偏离,只在恐慌高于常态时计压。",
                    evidence_available=oil_vol_dev_pct is not None,
                ),
                bhadial_factor(
                    module="External",
                    name="天然气",
                    tag=f"${ind['natgas']:.2f} · {percentile_label(natgas_pct)}",
                    value="能源压力" if natgas_score < 0 else "正常",
                    score=natgas_score,
                    source_mode="real-public",
                    note="Bhadial External的Natural Gas: FRED Henry Hub现货价格,用于补充能源冲击而非只看原油。",
                    evidence_available=natgas_pct is not None,
                ),
            ],
        },
    ]


def compatibility_factor(
    *,
    name: str,
    tag: str,
    value: str,
    score: int,
    note: str,
    source_mode: str,
    curve: int | None = None,
) -> dict[str, Any]:
    factor: dict[str, Any] = {
        "n": name,
        "tag": tag,
        "v": value,
        "score": score,
        "note": note,
        "sourceMode": source_mode,
        "auditEligible": source_mode != "manual-placeholder",
        "compatibilityWith": REMOTE_COMPATIBILITY_SOURCE,
    }
    if curve is not None:
        factor["curve"] = curve
    return factor


def high_pressure_score(percentile: int | None, *, high_score: int = -1, extreme_score: int = -2) -> int:
    if percentile is None:
        return 0
    if percentile >= 95:
        return extreme_score
    if percentile >= 80:
        return high_score
    return 0


def low_preference_score(percentile: int | None) -> int:
    if percentile is None:
        return 0
    if percentile <= 10:
        return -2
    if percentile <= 25:
        return -1
    if percentile >= 80:
        return 1
    return 0


def cftc_leveraged_position_factor(
    positions: list[CftcTreasuryPosition],
    *,
    min_contracts: int = 3,
) -> dict[str, Any]:
    """Score leveraged positioning from the cross-tenor median net share of OI.

    Raw contract counts are not comparable across Treasury futures because
    contract sizes, duration exposure and open interest differ by tenor.  Each
    contract is first normalized by its own open interest; the unweighted
    median then gives every tenor one vote and is robust to one extreme market.
    """

    if min_contracts < 3:
        raise ValueError("min_contracts must be at least 3 for a robust median")
    if not positions:
        valid: list[CftcTreasuryPosition] = []
        latest_date = None
    else:
        latest_date = max(item.report_date for item in positions)
        by_market: dict[str, CftcTreasuryPosition] = {}
        for item in positions:
            if item.report_date != latest_date or item.open_interest <= 0:
                continue
            if not math.isfinite(float(item.leveraged_net_pct_oi)):
                continue
            market_key = " ".join(item.market.upper().split())
            prior = by_market.get(market_key)
            if prior is None or item.open_interest > prior.open_interest:
                by_market[market_key] = item
        valid = list(by_market.values())
    if len(valid) < min_contracts:
        return _evidence_factor(
            {
                "n": "CFTC 杠杆基金持仓",
                "tag": f"数据不足 · 有效合约 {len(valid)}/{min_contracts}",
                "v": "数据不足",
                "score": 0,
                "curve": 0,
                "note": (
                    "CFTC financial futures COT按每个国债期货合约的杠杆基金净仓/未平仓量标准化;"
                    f"至少需要{min_contracts}个同报告日、不同国债期货合约才计算稳健跨合约中位数。"
                ),
            },
            evidence_available=False,
            source_mode="real-public",
        )

    median_pct_oi = float(median(item.leveraged_net_pct_oi for item in valid))
    score = 1 if median_pct_oi <= -5.0 else -1 if median_pct_oi >= 5.0 else 0
    factor = _evidence_factor(
        {
            "n": "CFTC 杠杆基金持仓",
            "tag": f"跨期限中位净仓 {median_pct_oi:+.2f}% OI · n={len(valid)}",
            "v": "反向利多" if score > 0 else "偏空" if score < 0 else "中性",
            "score": score,
            "curve": -1 if score > 0 else 0,
            "note": (
                "CFTC financial futures COT先将每个国债期货合约的杠杆基金净仓除以本合约未平仓量,"
                "再对同报告日不同期限取不加权中位数;避免直接相加不可比的raw contracts。"
            ),
        },
        evidence_available=True,
        source_mode="real-public",
    )
    factor.update(
        {
            "reportDate": latest_date.isoformat() if latest_date else None,
            "validContractCount": len(valid),
            "minimumContractCount": min_contracts,
            "aggregation": "unweighted-median-leveraged-net-pct-open-interest",
            "medianLeveragedNetPctOi": round(median_pct_oi, 2),
        }
    )
    return factor


def fed_path_compatibility_factor(ind: dict[str, Any]) -> dict[str, Any]:
    scenario = _fed_directional_scenario(ind)
    direction = scenario.get("direction")
    value = {
        "restrictive-bias": "偏紧情景",
        "easing-bias": "偏松情景",
        "balanced": "平衡情景",
    }.get(str(direction), "数据不足")
    factor = compatibility_factor(
        name="隐含政策路径",
        tag="定性模型 · 非概率" if scenario.get("available") else "逐会议概率不可用",
        value=value,
        score=0,
        curve=0,
        source_mode="modeled",
        note=(
            "公开连续ZQ月均利率、2Y再定价和通胀仅生成定性方向;缺少逐会议合约、"
            "目标区间映射和校准证据时不生成加息/持平/降息概率,也不计入综合评分。"
        ),
    )
    factor["auditEligible"] = False
    factor["probabilitiesAvailable"] = False
    factor["isProbability"] = False
    factor["scenarioDrivers"] = list(scenario.get("drivers") or [])
    return factor


def chair_transition_compatibility_factor(official_news: list[NewsItem]) -> dict[str, Any]:
    chair_news = None
    for item in sorted(official_news, key=lambda row: row.date, reverse=True):
        title = item.title.lower()
        if "chair" in title and ("oath" in title or "sworn" in title or "chairman" in title or "chair pro tempore" in title):
            chair_news = item
            break
    if chair_news:
        return compatibility_factor(
            name="新任主席倾向",
            tag=f"{chair_news.date.strftime('%m/%d')} {chair_news.source}",
            value="待判断",
            score=0,
            source_mode="official-news",
            note="官方新闻确认主席/代理主席相关变化;政策倾向不由标题自动推断,默认中性并保留手动评分入口。",
        )
    return compatibility_factor(
        name="新任主席倾向",
        tag="未检测官方主席变动",
        value="手动",
        score=0,
        source_mode="manual-placeholder",
        note="原站包含主席倾向叙事;本地未从官方新闻检测到主席变化时不自动给方向,可手动评分。",
    )


def growth_momentum_compatibility_factor(ind: dict[str, Any]) -> dict[str, Any]:
    payroll = _indicator_value(ind, "payroll_change_k")
    unrate = _indicator_value(ind, "unrate")
    if payroll is None or unrate is None:
        return compatibility_factor(
            name="增长动能",
            tag=f"PAYEMS {'--' if payroll is None else f'{payroll:+.0f}k'} / U-3 {'--' if unrate is None else f'{unrate:.1f}%'}",
            value="数据不足",
            score=0,
            curve=0,
            source_mode="manual-placeholder",
            note="PAYEMS月差或失业率缺失时保持中性,不把缺失值0误判为增长降温。",
        )
    if payroll > 125 and unrate < 4.5:
        score, value, curve = -1, "稳健", 1
    elif payroll < 50 or unrate >= 4.5:
        score, value, curve = 1, "降温", -1
    else:
        score, value, curve = 0, "中性", 0
    return compatibility_factor(
        name="增长动能",
        tag=f"PAYEMS {payroll:+.0f}k / U-3 {unrate:.1f}%",
        value=value,
        score=score,
        curve=curve,
        source_mode="proxy-public",
        note="对齐原站增长动能因子;用公开非农月差和失业率代理活动强弱,避免主观填写。",
    )


def long_bond_auction_compatibility_factor(auctions: list[dict[str, object]]) -> dict[str, Any]:
    long_bond = None
    for row in sorted(auctions, key=lambda item: str(item.get("auctionDate") or ""), reverse=True):
        term = str(row.get("securityTerm") or "")
        security_type = str(row.get("securityType") or "")
        if ("30" in term and ("Year" in term or "年" in term)) and "TIPS" not in security_type.upper():
            long_bond = row
            break
    if not long_bond:
        return compatibility_factor(
            name="30年期拍卖",
            tag="待接近期30Y auction",
            value="手动",
            score=0,
            curve=0,
            source_mode="manual-placeholder",
            note="原站重点跟踪30年期拍卖质量;TreasuryDirect样本未含近期30Y时默认中性,可手动评分。",
        )
    bid_to_cover = parse_number(long_bond.get("bidToCoverRatio"))
    high_yield = format_yield(str(long_bond.get("highYield") or long_bond.get("averageMedianYield") or ""))
    if bid_to_cover is None:
        return compatibility_factor(
            name="30年期拍卖",
            tag=f"{high_yield} · btc待结果",
            value="数据不足",
            score=0,
            curve=0,
            source_mode="manual-placeholder",
            note="已识别近期30年期拍卖,但TreasuryDirect尚无可用投标倍数;结果发布前不按中性需求计分。",
        )
    score = -2 if bid_to_cover < 2.35 else -1 if bid_to_cover < 2.5 else 0
    return compatibility_factor(
        name="30年期拍卖",
        tag=f"{high_yield} · {bid_to_cover:.2f}x" if bid_to_cover is not None else f"{high_yield} · btc待解析",
        value="疲弱" if score < 0 else "中性",
        score=score,
        curve=2 if score <= -2 else 1 if score < 0 else 0,
        source_mode="real-public",
        note="对齐原站30年期拍卖因子;用TreasuryDirect中标利率和投标倍数衡量长端需求。",
    )


def primary_dealer_inventory_compatibility_factor(stats: PrimaryDealerStats | None) -> dict[str, Any]:
    value = stats.metrics_millions.get("PDPOSGST-TOT") if stats else None
    if value is None:
        return compatibility_factor(
            name="一级交易商持仓",
            tag="待接NY Fed周频",
            value="手动",
            score=0,
            source_mode="manual-placeholder",
            note="原站保留交易商库存维度;NY Fed primary dealer数据不可用时默认中性。",
        )
    score = -1 if value >= 650_000 else 0
    return compatibility_factor(
        name="一级交易商持仓",
        tag=f"{money_from_millions(value)} · {stats.as_of.isoformat()}",
        value="库存高" if score < 0 else "中性",
        score=score,
        source_mode="real-public",
        note="NY Fed primary dealer UST ex-TIPS净持仓;库存高可能代表交易商资产负债表承接压力。",
    )


def manual_placeholder_compatibility_factor(name: str, tag: str, value: str, note: str) -> dict[str, Any]:
    return compatibility_factor(name=name, tag=tag, value=value, score=0, source_mode="manual-placeholder", note=note)


def market_liquidity_compatibility_factor(ind: dict[str, Any]) -> dict[str, Any]:
    realized_vol = _indicator_value(ind, "ten_year_realized_vol_20d_bp")
    hy_oas = _indicator_value(ind, "hy_oas")
    if realized_vol is None or hy_oas is None:
        return compatibility_factor(
            name="市场流动性",
            tag=f"10Y vol {'--' if realized_vol is None else f'{realized_vol:.1f}'} / HY {'--' if hy_oas is None else f'{hy_oas:.2f}%'}",
            value="数据不足",
            score=0,
            curve=0,
            source_mode="manual-placeholder",
            note="10Y实现波动率或HY信用利差缺失时不输出‘正常’结论,待两条公开代理均可用后再评分。",
        )
    stressed = realized_vol > 95 or hy_oas > 4.0
    return compatibility_factor(
        name="市场流动性",
        tag=f"10Y vol {realized_vol:.1f} / HY {hy_oas:.2f}%",
        value="轻度承压" if stressed else "正常",
        score=-1 if stressed else 0,
        curve=1 if stressed else 0,
        source_mode="proxy-public",
        note="原站市场流动性因子的公开代理:10Y实现波动率和HY信用利差同时观察,暂不伪装为订单簿深度或买卖价差。",
    )


def _auction_cohort(auction: dict[str, object]) -> tuple[str, str]:
    term = (
        auction.get("originalSecurityTerm")
        or auction.get("securityTerm")
        or auction.get("term")
        or "unknown-term"
    )
    security_type = auction.get("securityType") or auction.get("type") or "unknown-type"
    return (" ".join(str(term).lower().split()), " ".join(str(security_type).lower().split()))


def _auction_observations(
    auctions: list[dict[str, object]],
) -> list[tuple[date, float, str, tuple[str, str]]]:
    dated: list[tuple[date, float, str, tuple[str, str]]] = []
    for auction in auctions:
        auction_date = parse_dashboard_date(auction.get("auctionDate"))
        btc = parse_number(auction.get("bidToCoverRatio"))
        if auction_date is None or btc is None or not math.isfinite(btc):
            continue
        security_term = str(auction.get("securityTerm") or auction.get("term") or "").strip()
        security_type = str(auction.get("securityType") or auction.get("type") or "").strip()
        label = " ".join(part for part in (security_term, security_type) if part) or "Treasury auction"
        dated.append((auction_date, btc, label, _auction_cohort(auction)))
    return sorted(dated, key=lambda item: item[0])


def auction_demand_signal(auctions: list[dict[str, object]]) -> dict[str, Any]:
    dated = _auction_observations(auctions)
    if not dated:
        return {
            "tag": "TreasuryDirect",
            "label": "待结果",
            "score": 0,
            "note": "TreasuryDirect拍卖数据不可用时不填入历史百分位。",
            "value": "--",
            "percentile": None,
        }
    latest_date, latest_btc, latest_label, latest_cohort = dated[-1]
    cohort_values = [item[1] for item in dated if item[3] == latest_cohort]
    percentile = historical_percentile(latest_btc, cohort_values)
    score = 1 if percentile is not None and percentile >= 70 else -1 if percentile is not None and percentile <= 30 else 0
    label = "强劲" if score > 0 else "偏弱" if score < 0 else "中性"
    return {
        "tag": f"{latest_label} BTC {latest_btc:.2f} · {percentile_label(percentile)}",
        "label": label,
        "score": score,
        "note": (
            f"TreasuryDirect最新拍卖 {latest_date.isoformat()} bid-to-cover相对同期限、同证券类型"
            f"历史样本的百分位(n={len(cohort_values)}),避免跨Bill/Note/Bond直接比较。"
        ),
        "value": f"{latest_btc:.2f}",
        "percentile": percentile,
    }


def auction_percentile_points(
    auctions: list[dict[str, object]],
    display_years: int = 3,
    max_points: int = 52,
) -> list[dict[str, Any]]:
    observations = _auction_observations(auctions)
    if not observations:
        return []
    histories: dict[tuple[str, str], list[float]] = {}
    ranked: list[tuple[date, float, int]] = []
    for auction_date, btc, _label, cohort in observations:
        values = histories.setdefault(cohort, [])
        values.append(btc)
        percentile = historical_percentile(btc, values)
        if percentile is not None:
            ranked.append((auction_date, btc, percentile))
    if not ranked:
        return []
    display_start = window_start(ranked[-1][0], years=display_years)
    visible = [item for item in ranked if item[0] >= display_start]
    return [
        {"date": visible[index][0].isoformat(), "value": round(visible[index][1], 2), "percentile": visible[index][2]}
        for index in sampled_indices(len(visible), max_points)
    ]
