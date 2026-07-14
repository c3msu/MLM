"""Indicator computation extracted from build_dashboard.py (behavior-unchanged,
2026-06-19 全面重构 Phase 1). The data->indicators transform (compute_indicators) plus its
small leaf helpers; depends on series_math + sources only. BHADIAL_BREAKEVEN_TARGET lives
here (lowest layer that uses it) and is re-exported for the bhadial config. Re-exported by
build_dashboard via `from .indicators import *`."""
from __future__ import annotations

import math
from typing import Any

from .sources import SeriesPoint, TimeSeries, YieldCurveRecord
from .series_math import *  # noqa: F401,F403  (series-math helpers used by compute_indicators)


BHADIAL_BREAKEVEN_TARGET = 2.3


def compute_indicators(
    *,
    today: YieldCurveRecord,
    one_week: YieldCurveRecord,
    one_month: YieldCurveRecord,
    curve_records: list[YieldCurveRecord],
    fred: dict[str, TimeSeries],
    fed_funds_futures: MarketQuote | None = None,
    gold_quote: MarketQuote | None = None,
) -> dict[str, Any]:
    ten_year = today.values["10Y"]
    two_year = today.values["2Y"]
    thirty_year = today.values["30Y"]
    five_year = today.values["5Y"]
    real_5y = latest_value(fred, "DFII5")
    real_10y = latest_value(fred, "DFII10")
    breakeven_10y = latest_value(fred, "T10YIE", default=ten_year - real_10y)
    dff = latest_value(fred, "DFF", default=3.63)
    sofr = latest_value(fred, "SOFR", default=dff)
    obfr = latest_value(fred, "OBFR", default=dff)
    iorb = latest_value(fred, "IORB", default=dff)
    rrp_award = latest_value(fred, "RRPONTSYAWARD", default=dff)
    tga_millions = latest_value(fred, "WTREGEN", default=0.0)
    walcl_millions = latest_value(fred, "WALCL", default=0.0)
    soma_treasury_millions = latest_value(fred, "TREAST", default=0.0)
    bank_reserves_millions = latest_value(fred, "WRESBAL", default=0.0)
    rrp_billions = latest_value(fred, "RRPONTSYD", default=0.0)
    net_liquidity_points = build_net_liquidity_points(fred)
    net_liquidity_latest = (
        net_liquidity_points[-1].value
        if net_liquidity_points
        else walcl_millions - tga_millions - rrp_billions * 1_000.0
    )
    # Net-liquidity legs are weekly/daily.  Do not label a change as 1M/13W
    # when the observation around the requested anchor is more than two weeks
    # old because of a historical gap.
    net_liquidity_m1_change = point_change(
        net_liquidity_points,
        days=30,
        max_target_gap_days=14,
    )
    net_liquidity_momentum_points = change_points(
        net_liquidity_points,
        days=30,
        max_target_gap_days=14,
    )
    net_liquidity_13w_change = point_change(
        net_liquidity_points,
        days=91,
        max_target_gap_days=14,
    )
    net_liquidity_13w_momentum_points = change_points(
        net_liquidity_points,
        days=91,
        max_target_gap_days=14,
    )
    tga_deviation_points = rolling_median_deviation_points(fred.get("WTREGEN"), window_days=364)
    onrrp_buffer_risk_series_points = onrrp_buffer_risk_points(fred.get("RRPONTSYD"))
    sofr_effr_spread_points = spread_points(fred.get("SOFR"), fred.get("DFF"), multiplier=100)
    sofr_effr_spread_bp = (sofr - dff) * 100
    collateral_repo_friction_points = spread_points(fred.get("SOFR"), fred.get("OBFR"), multiplier=100)
    corridor_sofr_iorb_points = spread_points(fred.get("SOFR"), fred.get("IORB"), multiplier=100)
    corridor_sofr_rrp_points = spread_points(fred.get("SOFR"), fred.get("RRPONTSYAWARD"), multiplier=100)
    effr_iorb_spread_points = spread_points(fred.get("DFF"), fred.get("IORB"), multiplier=100)
    cp_tbill_spread_points = spread_points(fred.get("DCPF3M"), fred.get("DTB3"), multiplier=100)
    funding_fragmentation_series_points = funding_fragmentation_points(fred.get("SOFR"), fred.get("OBFR"), fred.get("IORB"), fred.get("RRPONTSYAWARD"))
    collateral_repo_friction_deviation_points = rolling_median_deviation_points_from_points(collateral_repo_friction_points, window_days=365)
    corridor_sofr_iorb_deviation_points = rolling_median_deviation_points_from_points(corridor_sofr_iorb_points, window_days=365)
    corridor_sofr_rrp_deviation_points = rolling_median_deviation_points_from_points(corridor_sofr_rrp_points, window_days=365)
    real_rate_level_points = weighted_points(fred.get("DFII5"), fred.get("DFII10"), 0.6, 0.4)
    real_curve_points = spread_points(fred.get("DFII10"), fred.get("DFII5"), multiplier=100)
    breakeven_target_distance_points = target_distance_points(fred.get("T10YIE"), target=BHADIAL_BREAKEVEN_TARGET)
    real_10y_w1_change = point_change_optional(
        fred["DFII10"].points,
        days=7,
        max_target_gap_days=7,
    ) if fred.get("DFII10") else None
    real_10y_m1_change = point_change_optional(
        fred["DFII10"].points,
        days=30,
        max_target_gap_days=7,
    ) if fred.get("DFII10") else None
    breakeven_10y_w1_change = point_change_optional(
        fred["T10YIE"].points,
        days=7,
        max_target_gap_days=7,
    ) if fred.get("T10YIE") else None
    breakeven_10y_m1_change = point_change_optional(
        fred["T10YIE"].points,
        days=30,
        max_target_gap_days=7,
    ) if fred.get("T10YIE") else None
    hy_ig_oas_spread_points = spread_points(fred.get("BAMLH0A0HYM2"), fred.get("BAMLC0A0CM"), multiplier=100)
    vix_term_structure_points = ratio_points(fred.get("VIXCLS"), fred.get("VXVCLS"))
    dxy_realized_vol_points = realized_volatility_points(fred.get("DTWEXBGS"), window=63)
    oil_vol_deviation_points = rolling_median_deviation_points(fred.get("OVXCLS"), window_days=365, positive_only=True)
    wti_shock_points = rolling_median_deviation_points(fred.get("DCOILWTICO"), window_days=365, positive_only=True)
    natgas_shock_points = rolling_median_deviation_points(fred.get("DHHNGSP"), window_days=365, positive_only=True)
    treasury_30y10y_points = curve_spread_points(curve_records, "30Y", "10Y", multiplier=100)
    treasury_10y_vol_20d_points = curve_realized_volatility_points(curve_records, "10Y", window=20)
    treasury_10y_vol_21d_points = curve_realized_volatility_points(curve_records, "10Y", window=21)
    curve_curvature_abs_points = treasury_curve_curvature_abs_points(curve_records)
    treasury_price_proxy_points = treasury_price_proxy_from_yield_points(fred.get("DGS10"), duration=8.0)
    treasury_price_proxy_series = TimeSeries("DGS10_PRICE_PROXY", treasury_price_proxy_points) if treasury_price_proxy_points else None
    risk_vs_safe_points = blended_relative_return_points(fred.get("SP500"), treasury_price_proxy_series)
    high_beta_preference_points = ratio_points(fred.get("NASDAQXNDX"), fred.get("NASDAQNQUS500LCT"))
    regional_bank_vs_market_points = ratio_points(fred.get("NASDAQBANK"), fred.get("SP500"))
    hy_credit_preference_points = blended_relative_return_points(fred.get("BAMLHYH0A0HYM2TRIV"), treasury_price_proxy_series)
    ig_credit_preference_points = blended_relative_return_points(fred.get("BAMLCC0A0CMTRIV"), treasury_price_proxy_series)
    percentile_values = {
        "walcl": series_percentile(fred.get("WALCL")),
        "tga": series_percentile(fred.get("WTREGEN")),
        "tga_deviation": point_series_percentile(tga_deviation_points),
        "rrp": series_percentile(fred.get("RRPONTSYD")),
        "onrrp_buffer_risk": point_series_percentile(onrrp_buffer_risk_series_points),
        "bank_reserves": series_percentile(fred.get("WRESBAL")),
        "net_liquidity": point_series_percentile(net_liquidity_points),
        "net_liquidity_momentum": point_series_percentile(net_liquidity_momentum_points),
        "net_liquidity_13w_momentum": point_series_percentile(net_liquidity_13w_momentum_points),
        "sofr_effr_spread": point_series_percentile(sofr_effr_spread_points, current=sofr_effr_spread_bp),
        "collateral_repo_friction": point_series_percentile(collateral_repo_friction_points),
        "collateral_repo_friction_deviation": point_series_percentile(collateral_repo_friction_deviation_points),
        "corridor_sofr_iorb": point_series_percentile(corridor_sofr_iorb_points),
        "corridor_sofr_iorb_deviation": point_series_percentile(corridor_sofr_iorb_deviation_points),
        "corridor_sofr_rrp": point_series_percentile(corridor_sofr_rrp_points),
        "corridor_sofr_rrp_deviation": point_series_percentile(corridor_sofr_rrp_deviation_points),
        "effr_iorb_spread": point_series_percentile(effr_iorb_spread_points),
        "cp_tbill_spread": point_series_percentile(cp_tbill_spread_points),
        "funding_fragmentation": point_series_percentile(funding_fragmentation_series_points),
        "treasury_30y10y": point_series_percentile(treasury_30y10y_points),
        "treasury_10y_vol_21d": point_series_percentile(treasury_10y_vol_21d_points),
        "curve_curvature_abs": point_series_percentile(curve_curvature_abs_points),
        "real_rate_level": point_series_percentile(real_rate_level_points),
        "real_curve": point_series_percentile(real_curve_points),
        "breakeven_target_distance": point_series_percentile(breakeven_target_distance_points),
        "vix": series_percentile(fred.get("VIXCLS")),
        "vix_term_structure": point_series_percentile(vix_term_structure_points),
        "hy_oas": series_percentile(fred.get("BAMLH0A0HYM2")),
        "ig_oas": series_percentile(fred.get("BAMLC0A0CM")),
        "hy_ig_oas_spread": point_series_percentile(hy_ig_oas_spread_points),
        "nfci": series_percentile(fred.get("NFCI")),
        "dxy": series_percentile(fred.get("DTWEXBGS")),
        "dxy_realized_vol": point_series_percentile(dxy_realized_vol_points),
        "wti": series_percentile(fred.get("DCOILWTICO")),
        "wti_shock": point_series_percentile(wti_shock_points),
        "oil_vol_deviation": point_series_percentile(oil_vol_deviation_points),
        "natgas": series_percentile(fred.get("DHHNGSP")),
        "natgas_shock": point_series_percentile(natgas_shock_points),
        "treasury_price_proxy": point_series_percentile(treasury_price_proxy_points),
        "risk_vs_safe": point_series_percentile(risk_vs_safe_points),
        "high_beta_preference": point_series_percentile(high_beta_preference_points),
        "regional_bank_vs_market": point_series_percentile(regional_bank_vs_market_points),
        "hy_credit_preference": point_series_percentile(hy_credit_preference_points),
        "ig_credit_preference": point_series_percentile(ig_credit_preference_points),
    }
    cpi_yoy_value = yoy_or_none(fred.get("CPIAUCSL"))
    pce_yoy_value = yoy_or_none(fred.get("PCEPI"))
    core_pce_yoy_value = yoy_or_none(fred.get("PCEPILFE"))
    ppi_yoy_value = yoy_or_none(fred.get("PPIACO"))
    cpi_yoy = cpi_yoy_value if cpi_yoy_value is not None else 0.0
    pce_yoy = pce_yoy_value if pce_yoy_value is not None else 0.0
    core_pce_yoy = core_pce_yoy_value if core_pce_yoy_value is not None else 0.0
    trimmed_mean_pce_yoy = latest_value(fred, "PCETRIM12M159SFRBDAL", default=0.0)
    ppi_yoy = ppi_yoy_value if ppi_yoy_value is not None else 0.0
    unrate = latest_value(fred, "UNRATE", default=0.0)
    payroll_change = latest_absolute_change_or_none(fred.get("PAYEMS"), max_gap_days=45)
    payroll_change_k = payroll_change if payroll_change is not None else 0.0
    gdp_yoy = yoy(fred.get("GDPC1"))
    futures_implied_rate = fed_funds_futures.implied_rate if fed_funds_futures else None
    availability = {
        "dff": bool(fred.get("DFF") and fred["DFF"].points),
        "sofr": bool(fred.get("SOFR") and fred["SOFR"].points),
        "obfr": bool(fred.get("OBFR") and fred["OBFR"].points),
        "iorb": bool(fred.get("IORB") and fred["IORB"].points),
        "rrp_award": bool(fred.get("RRPONTSYAWARD") and fred["RRPONTSYAWARD"].points),
        "tga": bool(fred.get("WTREGEN") and fred["WTREGEN"].points),
        "tga_trillions": bool(fred.get("WTREGEN") and fred["WTREGEN"].points),
        "walcl": bool(fred.get("WALCL") and fred["WALCL"].points),
        "walcl_trillions": bool(fred.get("WALCL") and fred["WALCL"].points),
        "soma_treasury_trillions": bool(fred.get("TREAST") and fred["TREAST"].points),
        "rrp": bool(fred.get("RRPONTSYD") and fred["RRPONTSYD"].points),
        "rrp_trillions": bool(fred.get("RRPONTSYD") and fred["RRPONTSYD"].points),
        "bank_reserves": bool(fred.get("WRESBAL") and fred["WRESBAL"].points),
        "bank_reserves_trillions": bool(fred.get("WRESBAL") and fred["WRESBAL"].points),
        "sofr_effr_spread_bp": bool(sofr_effr_spread_points),
        "real_5y": bool(fred.get("DFII5") and fred["DFII5"].points),
        "real_10y": bool(fred.get("DFII10") and fred["DFII10"].points),
        "real_rate_level": bool(real_rate_level_points),
        "real_curve_10y5y_bp": bool(real_curve_points),
        "breakeven_10y": bool(fred.get("T10YIE") and fred["T10YIE"].points),
        "real_10y_w1_change_bp": real_10y_w1_change is not None,
        "real_10y_m1_change_bp": real_10y_m1_change is not None,
        "breakeven_10y_w1_change_bp": breakeven_10y_w1_change is not None,
        "breakeven_10y_m1_change_bp": breakeven_10y_m1_change is not None,
        "net_liquidity": bool(net_liquidity_points),
        "net_liquidity_trillions": bool(net_liquidity_points),
        "cpi_yoy": cpi_yoy_value is not None,
        "pce_yoy": pce_yoy_value is not None,
        "core_pce_yoy": core_pce_yoy_value is not None,
        "trimmed_mean_pce_yoy": bool(fred.get("PCETRIM12M159SFRBDAL") and fred["PCETRIM12M159SFRBDAL"].points),
        "ppi_yoy": ppi_yoy_value is not None,
        "unrate": bool(fred.get("UNRATE") and fred["UNRATE"].points),
        "payroll_change_k": payroll_change is not None,
        "ten_year_realized_vol_20d_bp": bool(treasury_10y_vol_20d_points),
        "hy_oas": bool(fred.get("BAMLH0A0HYM2") and fred["BAMLH0A0HYM2"].points),
    }
    return {
        "availability": availability,
        "ten_year": ten_year,
        "two_year": two_year,
        "five_year": five_year,
        "thirty_year": thirty_year,
        "s2s10": (ten_year - two_year) * 100,
        "s5s30": (thirty_year - five_year) * 100,
        "s3m10": (ten_year - today.values["3M"]) * 100,
        "fly_2s5s10s": (2 * five_year - two_year - ten_year) * 100,
        "s10s3m": (ten_year - today.values["3M"]) * 100,
        "s30s10": (thirty_year - ten_year) * 100,
        "curve_curvature_abs_bp": treasury_curve_curvature_abs_bp(two_year, ten_year, thirty_year),
        "ten_year_w1_change_bp": (ten_year - one_week.values["10Y"]) * 100,
        "ten_year_m1_change_bp": (ten_year - one_month.values["10Y"]) * 100,
        "two_year_m1_change_bp": (two_year - one_month.values["2Y"]) * 100,
        "ten_year_realized_vol_20d_bp": compute_tenor_realized_volatility(curve_records, "10Y", window=20),
        "ten_year_realized_vol_21d_bp": compute_tenor_realized_volatility(curve_records, "10Y", window=21),
        "real_5y": real_5y,
        "real_10y": real_10y,
        "real_rate_level": latest_point_value(real_rate_level_points, real_5y * 0.6 + real_10y * 0.4),
        "real_curve_10y5y_bp": latest_point_value(real_curve_points, (real_10y - real_5y) * 100),
        "breakeven_10y": breakeven_10y,
        "real_10y_w1_change_bp": real_10y_w1_change * 100 if real_10y_w1_change is not None else None,
        "real_10y_m1_change_bp": real_10y_m1_change * 100 if real_10y_m1_change is not None else None,
        "breakeven_10y_w1_change_bp": breakeven_10y_w1_change * 100 if breakeven_10y_w1_change is not None else None,
        "breakeven_10y_m1_change_bp": breakeven_10y_m1_change * 100 if breakeven_10y_m1_change is not None else None,
        "dff": dff,
        "target_range": target_range_from_effective_rate(dff) if availability["dff"] else "--",
        "fed_funds_futures_symbol": fed_funds_futures.symbol if fed_funds_futures else "",
        "fed_funds_futures_date": fed_funds_futures.date.isoformat() if fed_funds_futures else "",
        "fed_funds_futures_close": fed_funds_futures.close if fed_funds_futures else None,
        "fed_funds_futures_implied_rate": futures_implied_rate,
        "sofr": sofr,
        "obfr": obfr,
        "iorb": iorb,
        "rrp_award": rrp_award,
        "tga_trillions": tga_millions / 1_000_000,
        "tga_deviation_trillions": latest_point_value(tga_deviation_points) / 1_000_000,
        "walcl_trillions": walcl_millions / 1_000_000,
        "soma_treasury_trillions": soma_treasury_millions / 1_000_000,
        "bank_reserves_trillions": bank_reserves_millions / 1_000_000,
        "net_liquidity_trillions": net_liquidity_latest / 1_000_000,
        "net_liquidity_m1_change_trillions": net_liquidity_m1_change / 1_000_000,
        "net_liquidity_13w_change_trillions": net_liquidity_13w_change / 1_000_000,
        "sofr_effr_spread_bp": sofr_effr_spread_bp,
        "sofr_obfr_spread_bp": latest_point_value(collateral_repo_friction_points, (sofr - obfr) * 100),
        "sofr_iorb_spread_bp": latest_point_value(corridor_sofr_iorb_points, (sofr - iorb) * 100),
        "sofr_rrp_award_spread_bp": latest_point_value(corridor_sofr_rrp_points, (sofr - rrp_award) * 100),
        "effr_iorb_spread_bp": latest_point_value(effr_iorb_spread_points, (dff - iorb) * 100),
        "cp_tbill_spread_bp": latest_point_value(cp_tbill_spread_points),
        "funding_fragmentation_21d": latest_point_value(funding_fragmentation_series_points),
        "breakeven_target_distance": abs(breakeven_10y - BHADIAL_BREAKEVEN_TARGET),
        "rrp_trillions": rrp_billions / 1_000,
        "onrrp_buffer_risk": latest_point_value(onrrp_buffer_risk_series_points),
        "percentiles": percentile_values,
        "percentile_series": {
            "tga": fred["WTREGEN"].points if fred.get("WTREGEN") else [],
            "rrp": fred["RRPONTSYD"].points if fred.get("RRPONTSYD") else [],
            "bank_reserves": fred["WRESBAL"].points if fred.get("WRESBAL") else [],
            "net_liquidity": net_liquidity_points,
            "net_liquidity_momentum": net_liquidity_momentum_points,
            "net_liquidity_13w_momentum": net_liquidity_13w_momentum_points,
            "tga_deviation": tga_deviation_points,
            "onrrp_buffer_risk": onrrp_buffer_risk_series_points,
            "sofr_effr_spread": sofr_effr_spread_points,
            "collateral_repo_friction": collateral_repo_friction_points,
            "collateral_repo_friction_deviation": collateral_repo_friction_deviation_points,
            "corridor_sofr_iorb": corridor_sofr_iorb_points,
            "corridor_sofr_iorb_deviation": corridor_sofr_iorb_deviation_points,
            "corridor_sofr_rrp": corridor_sofr_rrp_points,
            "corridor_sofr_rrp_deviation": corridor_sofr_rrp_deviation_points,
            "effr_iorb_spread": effr_iorb_spread_points,
            "cp_tbill_spread": cp_tbill_spread_points,
            "funding_fragmentation": funding_fragmentation_series_points,
            "treasury_30y10y": treasury_30y10y_points,
            "treasury_10y_vol_21d": treasury_10y_vol_21d_points,
            "curve_curvature_abs": curve_curvature_abs_points,
            "real_rate_level": real_rate_level_points,
            "real_curve": real_curve_points,
            "breakeven_target_distance": breakeven_target_distance_points,
            "vix": fred["VIXCLS"].points if fred.get("VIXCLS") else [],
            "vix_term_structure": vix_term_structure_points,
            "hy_oas": fred["BAMLH0A0HYM2"].points if fred.get("BAMLH0A0HYM2") else [],
            "ig_oas": fred["BAMLC0A0CM"].points if fred.get("BAMLC0A0CM") else [],
            "hy_ig_oas_spread": hy_ig_oas_spread_points,
            "nfci": fred["NFCI"].points if fred.get("NFCI") else [],
            "dxy": fred["DTWEXBGS"].points if fred.get("DTWEXBGS") else [],
            "dxy_realized_vol": dxy_realized_vol_points,
            "wti": fred["DCOILWTICO"].points if fred.get("DCOILWTICO") else [],
            "wti_shock": wti_shock_points,
            "oil_vol_deviation": oil_vol_deviation_points,
            "natgas": fred["DHHNGSP"].points if fred.get("DHHNGSP") else [],
            "natgas_shock": natgas_shock_points,
            "sp500": fred["SP500"].points if fred.get("SP500") else [],
            "treasury_price_proxy": treasury_price_proxy_points,
            "risk_vs_safe": risk_vs_safe_points,
            "high_beta_preference": high_beta_preference_points,
            "regional_bank_vs_market": regional_bank_vs_market_points,
            "hy_credit_preference": hy_credit_preference_points,
            "ig_credit_preference": ig_credit_preference_points,
        },
        "cpi_yoy": cpi_yoy,
        "pce_yoy": pce_yoy,
        "core_pce_yoy": core_pce_yoy,
        "trimmed_mean_pce_yoy": trimmed_mean_pce_yoy,
        "ppi_yoy": ppi_yoy,
        "unrate": unrate,
        "payroll_change_k": payroll_change_k,
        "gdp_yoy": gdp_yoy,
        "sp500": latest_value(fred, "SP500"),
        "sp500_change_pct": latest_pct_change(fred.get("SP500")),
        "vix": latest_value(fred, "VIXCLS"),
        "vix_3m": latest_value(fred, "VXVCLS"),
        "vix_term_structure": latest_point_value(vix_term_structure_points),
        "dxy": latest_value(fred, "DTWEXBGS"),
        "dxy_realized_vol": latest_point_value(dxy_realized_vol_points),
        "hy_oas": latest_value(fred, "BAMLH0A0HYM2"),
        "ig_oas": latest_value(fred, "BAMLC0A0CM"),
        "hy_ig_oas_spread_bp": latest_point_value(hy_ig_oas_spread_points),
        "nfci": latest_value(fred, "NFCI"),
        "jgb_10y": latest_value(fred, "IRLTLT01JPM156N"),
        "bund_10y": latest_value(fred, "IRLTLT01DEM156N"),
        "gilt_10y": latest_value(fred, "IRLTLT01GBM156N"),
        "wti": latest_value(fred, "DCOILWTICO"),
        "wti_shock": latest_point_value(wti_shock_points),
        "natgas": latest_value(fred, "DHHNGSP"),
        "natgas_shock": latest_point_value(natgas_shock_points),
        # Missing market data must stay missing. A numeric zero is a valid-looking price
        # and previously leaked into the dashboard as "$0.00", which can be mistaken for
        # a real cross-market signal.
        "gold_spot": gold_quote.close if gold_quote else None,
        "oil_vol": latest_value(fred, "OVXCLS"),
        "oil_vol_deviation": latest_point_value(oil_vol_deviation_points),
        "gold_vol": latest_value(fred, "GVZCLS"),
        "treasury_price_proxy": latest_point_value(treasury_price_proxy_points),
        "risk_vs_safe": latest_point_value(risk_vs_safe_points),
        "high_beta_preference": latest_point_value(high_beta_preference_points),
        "regional_bank_vs_market": latest_point_value(regional_bank_vs_market_points),
        "hy_credit_preference": latest_point_value(hy_credit_preference_points),
        "ig_credit_preference": latest_point_value(ig_credit_preference_points),
    }


def yoy_or_none(series: TimeSeries | None, *, max_prior_gap_days: int = 45) -> float | None:
    """Return a true one-year change, rejecting a stale comparison period.

    Monthly and quarterly FRED observation dates normally match the same
    calendar period one year earlier.  Without a tolerance, a missing year-ago
    observation can silently turn a multi-year change into a value labelled
    YoY.
    """
    if max_prior_gap_days < 0:
        raise ValueError("max_prior_gap_days must be non-negative")
    if not series or len(series.points) < 2:
        return None
    latest = series.latest
    target = window_start(latest.date, years=1)
    prior = series.value_at_or_before(target)
    if prior is None or prior.value == 0:
        return None
    if (target - prior.date).days > max_prior_gap_days:
        return None
    return (latest.value / prior.value - 1) * 100


def yoy(series: TimeSeries | None) -> float:
    value = yoy_or_none(series)
    return value if value is not None else 0.0


def latest_absolute_change_or_none(
    series: TimeSeries | None,
    *,
    max_gap_days: int,
) -> float | None:
    if max_gap_days < 0:
        raise ValueError("max_gap_days must be non-negative")
    if not series or len(series.points) < 2:
        return None
    latest = series.points[-1]
    prior = series.points[-2]
    if (latest.date - prior.date).days > max_gap_days:
        return None
    return latest.value - prior.value


def latest_pct_change(series: TimeSeries | None, *, max_gap_days: int = 7) -> float:
    if not series or len(series.points) < 2:
        return 0.0
    latest = series.points[-1]
    prior = series.points[-2]
    if prior.value == 0 or (latest.date - prior.date).days > max_gap_days:
        return 0.0
    return (latest.value / prior.value - 1) * 100


def target_range_from_effective_rate(rate: float) -> str:
    lower = math.floor(rate * 4) / 4
    upper = lower + 0.25
    return f"{lower:.2f}-{upper:.2f}%"
