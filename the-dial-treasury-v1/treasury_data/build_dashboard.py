from __future__ import annotations

import copy
import json
import math
import re
import sqlite3
from statistics import median
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .sources import (
    AcmRecord,
    CalendarEvent,
    CftcTreasuryPosition,
    DebtLimitStatus,
    FomcProjection,
    MarketQuote,
    NewsItem,
    PrimaryDealerStats,
    QuarterlyRefunding,
    TENORS,
    SeriesPoint,
    TicHolding,
    TicHoldings,
    TimeSeries,
    YieldCurveRecord,
    fetch_acm_term_premium,
    fetch_announced_auctions,
    fetch_bea_release_events,
    fetch_cftc_treasury_positions,
    fetch_debt_limit_status,
    fetch_fed_funds_futures_quote,
    fetch_federal_reserve_press_releases,
    fetch_fomc_calendar_events,
    fetch_fomc_projection,
    fetch_fred_series_bulk,
    fetch_fred_macro_release_events,
    fetch_gold_spot_quote,
    fetch_primary_dealer_stats,
    fetch_quarterly_refunding,
    fetch_tic_major_holders,
    fetch_treasury_press_releases,
    fetch_treasury_auctions,
    fetch_treasury_yield_curves,
    fetch_text_curl_first,
    nearest_record,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERRIDES_PATH = PROJECT_ROOT / "content" / "overrides.json"
REMOTE_COMPATIBILITY_SOURCE = "us-treasury-bonds-monitor-luffa"
BHADIAL_COMPATIBILITY_SOURCE = "bhadial-the-dial"
CONCLUSION_SOURCE_QUALITY = {
    "real-public": 1.0,
    "derived-public": 0.9,
    "official-news": 0.8,
    "proxy-public": 0.65,
    "modeled": 0.55,
    "manual-placeholder": 0.25,
}
LOWER_CONFIDENCE_SOURCE_MODES = {"proxy-public", "modeled", "manual-placeholder"}
REMOTE_COMPATIBILITY_FACTOR_NAMES = [
    "隐含政策路径",
    "新任主席倾向",
    "增长动能",
    "30年期拍卖",
    "一级交易商持仓",
    "互换利差",
    "市场流动性",
    "新老券利差",
]
BHADIAL_MODULE_NAMES = ["Liquidity", "Funding", "Treasury", "Rates", "Credit", "Risk", "External"]
BHADIAL_FACTOR_COVERAGE: list[dict[str, Any]] = [
    {
        "module": "Liquidity",
        "scored": 5,
        "display": 3,
        "factors": [
            {"name": "Fed Net Liquidity", "status": "derived", "local": "净流动性", "source": "WALCL - WTREGEN - RRPONTSYD"},
            {"name": "Bank Reserves", "status": "public", "local": "银行准备金", "source": "FRED WRESBAL"},
            {"name": "Net Liquidity Momentum (13W)", "status": "derived", "local": "13周净流动性动量", "source": "Net liquidity 13W change"},
            {"name": "TGA Deviation", "status": "derived", "local": "TGA偏离度", "source": "WTREGEN - 52W median"},
            {"name": "ON RRP Buffer Risk", "status": "derived", "local": "ON RRP缓冲风险", "source": "RRPONTSYD bounded risk signal"},
            {"name": "Fed Total Assets", "status": "public", "local": "资产负债表 / 总资产", "source": "FRED WALCL"},
            {"name": "Treasury General Account", "status": "public", "local": "TGA 与现金管理", "source": "FRED WTREGEN"},
            {"name": "ON RRP", "status": "public", "local": "ON RRP", "source": "FRED RRPONTSYD"},
        ],
    },
    {
        "module": "Funding",
        "scored": 6,
        "display": 6,
        "factors": [
            {"name": "Collateral/Repo Friction", "status": "derived", "local": "SOFR-OBFR回购摩擦", "source": "FRED SOFR - OBFR"},
            {"name": "Corridor Friction 1", "status": "derived", "local": "SOFR-IORB走廊摩擦", "source": "FRED SOFR - IORB"},
            {"name": "Corridor Friction 2", "status": "derived", "local": "SOFR-ON RRP走廊摩擦", "source": "FRED SOFR - RRPONTSYAWARD"},
            {"name": "EFFR-IORB Spread", "status": "derived", "local": "EFFR-IORB利差", "source": "FRED DFF - IORB"},
            {"name": "CP-TBill Spread", "status": "derived", "local": "商票-TBill利差", "source": "FRED DCPF3M - DTB3"},
            {"name": "Funding Fragmentation (21D)", "status": "derived", "local": "资金分裂度(21D)", "source": "SOFR corridor dispersion"},
            {"name": "EFFR", "status": "public", "local": "联邦基金目标利率", "source": "FRED DFF"},
            {"name": "SOFR", "status": "public", "local": "SOFR 融资锚", "source": "FRED SOFR"},
            {"name": "IORB", "status": "public", "local": "source-only", "source": "FRED IORB"},
            {"name": "ON RRP Award Rate", "status": "public", "local": "source-only", "source": "FRED RRPONTSYAWARD"},
            {"name": "OBFR Rate", "status": "public", "local": "source-only", "source": "FRED OBFR"},
            {"name": "SRF Usage", "status": "public", "local": "source-only", "source": "FRED RPONTSYD"},
        ],
    },
    {
        "module": "Treasury",
        "scored": 3,
        "display": 5,
        "factors": [
            {"name": "10Y-2Y Spread", "status": "public", "local": "2s10s 曲线", "source": "U.S. Treasury curve"},
            {"name": "10Y-3M Spread", "status": "public", "local": "10Y-3M曲线", "source": "U.S. Treasury curve"},
            {"name": "30Y-10Y Term Premium", "status": "public", "local": "30Y-10Y期限溢价", "source": "U.S. Treasury curve"},
            {"name": "10Y Rate Volatility (21D)", "status": "derived", "local": "10Y实现波动率", "source": "Treasury curve realized vol"},
            {"name": "Curve Curvature (Abs)", "status": "derived", "local": "曲线曲率(绝对值)", "source": "Treasury curve second-order slope"},
            {"name": "10Y Nominal Rate", "status": "public", "local": "10Y 收益率动量", "source": "U.S. Treasury curve"},
            {"name": "30Y Rate", "status": "public", "local": "30Y key tile", "source": "U.S. Treasury curve"},
            {"name": "2Y Rate", "status": "public", "local": "2Y 市场政策代理", "source": "U.S. Treasury curve"},
        ],
    },
    {
        "module": "Rates",
        "scored": 3,
        "display": 2,
        "factors": [
            {"name": "Real Rate Level", "status": "derived", "local": "真实利率水平", "source": "60% DFII5 + 40% DFII10"},
            {"name": "Real Curve (10Y-5Y)", "status": "derived", "local": "真实曲线(10Y-5Y)", "source": "FRED DFII10 - DFII5"},
            {"name": "10Y Breakeven", "status": "public", "local": "盈亏平衡通胀", "source": "FRED T10YIE"},
            {"name": "5Y Real Rate", "status": "public", "local": "source-only", "source": "FRED DFII5"},
            {"name": "10Y Real Rate", "status": "public", "local": "实际利率", "source": "FRED DFII10"},
        ],
    },
    {
        "module": "Credit",
        "scored": 4,
        "display": 0,
        "factors": [
            {"name": "NFCI", "status": "public", "local": "金融条件指数(NFCI)", "source": "FRED NFCI"},
            {"name": "HY Credit", "status": "proxy", "local": "HY信用偏好(HY/UST)", "source": "FRED ICE HY TR / DGS10 price proxy"},
            {"name": "IG Credit", "status": "proxy", "local": "IG信用偏好(IG/UST)", "source": "FRED ICE IG TR / DGS10 price proxy"},
            {"name": "Regional Banks vs SPY", "status": "proxy", "local": "银行股相对S&P500", "source": "FRED NASDAQBANK / SP500 proxy"},
        ],
    },
    {
        "module": "Risk",
        "scored": 4,
        "display": 1,
        "factors": [
            {"name": "VIX", "status": "public", "local": "VIX", "source": "FRED VIXCLS"},
            {"name": "VIX Term Structure", "status": "derived", "local": "VIX期限结构", "source": "FRED VIXCLS / VXVCLS"},
            {"name": "Risk vs Safe", "status": "proxy", "local": "风险资产/美债代理", "source": "FRED SP500 / DGS10 price proxy"},
            {"name": "High-Beta Preference", "status": "proxy", "local": "高Beta偏好(NDX/US500)", "source": "FRED NASDAQXNDX / NASDAQNQUS500LCT"},
            {"name": "VIX 3M", "status": "public", "local": "VIX期限结构", "source": "FRED VXVCLS"},
        ],
    },
    {
        "module": "External",
        "scored": 5,
        "display": 0,
        "factors": [
            {"name": "US Dollar Index (DXY)", "status": "public", "local": "美元广义指数", "source": "FRED DTWEXBGS"},
            {"name": "FX Realized Volatility", "status": "derived", "local": "美元实现波动率", "source": "DTWEXBGS 63D realized vol"},
            {"name": "WTI Oil", "status": "public", "local": "WTI 原油", "source": "FRED DCOILWTICO"},
            {"name": "Oil Volatility Deviation", "status": "derived", "local": "原油波动偏离", "source": "FRED OVXCLS - rolling median"},
            {"name": "Natural Gas", "status": "public", "local": "天然气", "source": "FRED DHHNGSP"},
        ],
    },
]

BHADIAL_SCORE_SOURCE_URL = "https://bhadial.com/dashboard"
BHADIAL_BREAKEVEN_TARGET = 2.3
BHADIAL_MODULE_WEIGHTS: dict[str, float] = {
    "Liquidity": 0.17,
    "Funding": 0.22,
    "Treasury": 0.18,
    "Rates": 0.12,
    "Credit": 0.08,
    "Risk": 0.08,
    "External": 0.15,
}
BHADIAL_CONDITION_MODULES: list[dict[str, Any]] = [
    {
        "name": "Liquidity",
        "nameCn": "流动性",
        "factors": [
            {"id": "fed_net_liquidity", "remoteName": "Fed Net Liquidity", "name": "净流动性", "weight": 0.30, "scoreKey": "net_liquidity", "direction": "higher_better", "method": "level_percentile", "valueKey": "net_liquidity_trillions", "format": "usd_t", "source": "FRED WALCL - WTREGEN - RRPONTSYD"},
            {"id": "bank_reserves", "remoteName": "Bank Reserves", "name": "银行准备金", "weight": 0.20, "scoreKey": "bank_reserves", "direction": "higher_better", "method": "level_percentile", "valueKey": "bank_reserves_trillions", "format": "usd_t", "source": "FRED WRESBAL"},
            {"id": "delta_net_liq_13w", "remoteName": "Net Liquidity Momentum (13W)", "name": "13周净流动性动量", "weight": 0.25, "scoreKey": "net_liquidity_13w_momentum", "direction": "higher_better", "method": "level_percentile", "valueKey": "net_liquidity_13w_change_trillions", "format": "signed_usd_t", "source": "Net liquidity 13W change"},
            {"id": "tga_dev_signed", "remoteName": "TGA Deviation", "name": "TGA偏离度", "weight": 0.15, "scoreKey": "tga_deviation", "direction": "lower_better", "method": "level_percentile", "valueKey": "tga_deviation_trillions", "format": "signed_usd_t", "source": "FRED WTREGEN - 52W median"},
            {"id": "onrrp_near_zero_risk", "remoteName": "ON RRP Buffer Risk", "name": "ON RRP缓冲风险", "weight": 0.10, "scoreKey": "onrrp_buffer_risk", "direction": "lower_better", "method": "risk_signal", "valueKey": "onrrp_buffer_risk", "format": "risk", "source": "FRED RRPONTSYD bounded risk"},
        ],
    },
    {
        "name": "Funding",
        "nameCn": "融资",
        "smooth": "ema5",
        "factors": [
            {"id": "collateral_friction", "remoteName": "Collateral/Repo Friction", "name": "SOFR-OBFR回购摩擦", "weight": 0.18, "scoreKey": "collateral_repo_friction_deviation", "displayKey": "collateral_repo_friction", "direction": "lower_better", "method": "deviation", "valueKey": "sofr_obfr_spread_bp", "format": "signed_bp", "source": "FRED SOFR - OBFR"},
            {"id": "corridor_friction_1", "remoteName": "Corridor Friction 1", "name": "SOFR-IORB走廊摩擦", "weight": 0.22, "scoreKey": "corridor_sofr_iorb_deviation", "displayKey": "corridor_sofr_iorb", "direction": "lower_better", "method": "deviation", "valueKey": "sofr_iorb_spread_bp", "format": "signed_bp", "source": "FRED SOFR - IORB"},
            {"id": "corridor_friction_2", "remoteName": "Corridor Friction 2", "name": "SOFR-ON RRP走廊摩擦", "weight": 0.18, "scoreKey": "corridor_sofr_rrp_deviation", "displayKey": "corridor_sofr_rrp", "direction": "lower_better", "method": "deviation", "valueKey": "sofr_rrp_award_spread_bp", "format": "signed_bp", "source": "FRED SOFR - RRPONTSYAWARD"},
            {"id": "effr_iorb", "remoteName": "EFFR-IORB Spread", "name": "EFFR-IORB利差", "weight": 0.12, "scoreKey": "effr_iorb_spread", "direction": "lower_better", "method": "level_percentile", "valueKey": "effr_iorb_spread_bp", "format": "signed_bp", "source": "FRED DFF - IORB"},
            {"id": "cp_tbill_spread", "remoteName": "CP-TBill Spread", "name": "商票-TBill利差", "weight": 0.20, "scoreKey": "cp_tbill_spread", "direction": "lower_better", "method": "level_percentile", "valueKey": "cp_tbill_spread_bp", "format": "signed_bp", "source": "FRED DCPF3M - DTB3"},
            {"id": "fragmentation_21d", "remoteName": "Funding Fragmentation (21D)", "name": "资金分裂度(21D)", "weight": 0.10, "scoreKey": "funding_fragmentation", "direction": "lower_better", "method": "shock_only", "valueKey": "funding_fragmentation_21d", "format": "number", "source": "SOFR corridor dispersion EMA(21)"},
        ],
    },
    {
        "name": "Treasury",
        "nameCn": "国债",
        "factors": [
            {"id": "dgs30_dgs10", "remoteName": "30Y-10Y Term Premium", "name": "30Y-10Y期限溢价", "weight": 0.35, "scoreKey": "treasury_30y10y", "direction": "higher_better", "method": "level_percentile", "valueKey": "s30s10", "format": "bp", "source": "U.S. Treasury curve 30Y - 10Y"},
            {"id": "dgs10_vol_21d", "remoteName": "10Y Rate Volatility (21D)", "name": "10Y收益率波动率(21D)", "weight": 0.35, "scoreKey": "treasury_10y_vol_21d", "direction": "lower_better", "method": "level_percentile", "valueKey": "ten_year_realized_vol_21d_bp", "format": "vol_bp", "source": "U.S. Treasury curve 10Y realized vol"},
            {"id": "curve_curvature_abs", "remoteName": "Curve Curvature (Abs)", "name": "曲线曲率(绝对值)", "weight": 0.30, "scoreKey": "curve_curvature_abs", "direction": "lower_better", "method": "shock_only", "valueKey": "curve_curvature_abs_bp", "format": "bp", "source": "ABS(DGS30 - 2*DGS10 + DGS2)"},
        ],
    },
    {
        "name": "Rates",
        "nameCn": "利率",
        "factors": [
            {"id": "real_rate_level", "remoteName": "Real Rate Level", "name": "真实利率水平", "weight": 0.50, "scoreKey": "real_rate_level", "direction": "lower_better", "method": "level_percentile", "valueKey": "real_rate_level", "format": "percent", "source": "60% DFII5 + 40% DFII10"},
            {"id": "real_curve", "remoteName": "Real Curve (10Y-5Y)", "name": "真实曲线(10Y-5Y)", "weight": 0.15, "scoreKey": "real_curve", "direction": "higher_better", "method": "level_percentile", "valueKey": "real_curve_10y5y_bp", "format": "signed_bp", "source": "FRED DFII10 - DFII5"},
            {"id": "t10yie", "remoteName": "10Y Breakeven", "name": "10年盈亏平衡通胀", "weight": 0.35, "scoreKey": "breakeven_target_distance", "direction": "lower_better", "method": "target_distance", "target": BHADIAL_BREAKEVEN_TARGET, "valueKey": "breakeven_10y", "format": "percent", "source": "FRED T10YIE vs 2.3% anchor"},
        ],
    },
    {
        "name": "Credit",
        "nameCn": "信用",
        "factors": [
            {"id": "nfci", "remoteName": "NFCI", "name": "金融条件指数(NFCI)", "weight": 0.40, "scoreKey": "nfci", "direction": "lower_better", "method": "level_percentile", "valueKey": "nfci", "format": "signed_number", "source": "FRED NFCI"},
            {"id": "hy_credit", "remoteName": "HY Credit", "name": "HY信用偏好(HY/UST)", "weight": 0.25, "scoreKey": "hy_credit_preference", "direction": "higher_better", "method": "level_percentile", "valueKey": "hy_credit_preference", "format": "number", "source": "FRED HY total-return / DGS10 price proxy"},
            {"id": "ig_credit", "remoteName": "IG Credit", "name": "IG信用偏好(IG/UST)", "weight": 0.15, "scoreKey": "ig_credit_preference", "direction": "higher_better", "method": "level_percentile", "valueKey": "ig_credit_preference", "format": "number", "source": "FRED IG total-return / DGS10 price proxy"},
            {"id": "kre_spy", "remoteName": "Regional Banks vs SPY", "name": "银行股相对S&P500", "weight": 0.20, "scoreKey": "regional_bank_vs_market", "direction": "higher_better", "method": "level_percentile", "valueKey": "regional_bank_vs_market", "format": "number", "source": "FRED NASDAQBANK / SP500 proxy"},
        ],
    },
    {
        "name": "Risk",
        "nameCn": "风险",
        "factors": [
            {"id": "vix", "remoteName": "VIX", "name": "VIX", "weight": 0.30, "scoreKey": "vix", "direction": "lower_better", "method": "level_percentile", "valueKey": "vix", "format": "number", "source": "FRED VIXCLS"},
            {"id": "vix_term_structure", "remoteName": "VIX Term Structure", "name": "VIX期限结构", "weight": 0.25, "scoreKey": "vix_term_structure", "direction": "lower_better", "method": "level_percentile", "valueKey": "vix_term_structure", "format": "number", "source": "FRED VIXCLS / VXVCLS"},
            {"id": "risk_vs_safe", "remoteName": "Risk vs Safe", "name": "风险资产/美债代理", "weight": 0.25, "scoreKey": "risk_vs_safe", "direction": "higher_better", "method": "level_percentile", "valueKey": "risk_vs_safe", "format": "number", "source": "FRED SP500 / DGS10 price proxy"},
            {"id": "high_beta_pref", "remoteName": "High-Beta Preference", "name": "高Beta偏好(NDX/US500)", "weight": 0.20, "scoreKey": "high_beta_preference", "direction": "higher_better", "method": "level_percentile", "valueKey": "high_beta_preference", "format": "number", "source": "FRED NASDAQXNDX / NASDAQNQUS500LCT"},
        ],
    },
    {
        "name": "External",
        "nameCn": "外部",
        "factors": [
            {"id": "dxy", "remoteName": "US Dollar Index (DXY)", "name": "美元广义指数", "weight": 0.25, "scoreKey": "dxy", "direction": "lower_better", "method": "level_percentile", "valueKey": "dxy", "format": "number", "source": "FRED DTWEXBGS proxy"},
            {"id": "fx_vol", "remoteName": "FX Realized Volatility", "name": "美元实现波动率", "weight": 0.20, "scoreKey": "dxy_realized_vol", "direction": "lower_better", "method": "level_percentile", "valueKey": "dxy_realized_vol", "format": "vol_pct", "source": "FRED DTWEXBGS 63D realized vol"},
            {"id": "wti", "remoteName": "WTI Oil", "name": "WTI原油冲击", "weight": 0.20, "scoreKey": "wti_shock", "displayKey": "wti", "direction": "lower_better", "method": "shock_only", "valueKey": "wti", "format": "price_usd", "source": "FRED DCOILWTICO positive deviation"},
            {"id": "ovx_dev", "remoteName": "Oil Volatility Deviation", "name": "原油波动偏离", "weight": 0.25, "scoreKey": "oil_vol_deviation", "direction": "lower_better", "method": "shock_only", "valueKey": "oil_vol_deviation", "format": "number", "source": "FRED OVXCLS - rolling median"},
            {"id": "natgas", "remoteName": "Natural Gas", "name": "天然气冲击", "weight": 0.10, "scoreKey": "natgas_shock", "displayKey": "natgas", "direction": "lower_better", "method": "shock_only", "valueKey": "natgas", "format": "price_usd", "source": "FRED DHHNGSP positive deviation"},
        ],
    },
]
BHADIAL_CONDITION_SERIES_KEYS = sorted(
    {
        str(factor["scoreKey"])
        for module in BHADIAL_CONDITION_MODULES
        for factor in module["factors"]
    }
)

FRED_SERIES = [
    "DFII5",
    "DFII10",
    "T10YIE",
    "DFF",
    "SOFR",
    "OBFR",
    "IORB",
    "RRPONTSYAWARD",
    "RPONTSYD",
    "WTREGEN",
    "WALCL",
    "TREAST",
    "WRESBAL",
    "RRPONTSYD",
    "CPIAUCSL",
    "PCEPI",
    "PCEPILFE",
    "PCETRIM12M159SFRBDAL",
    "PPIACO",
    "UNRATE",
    "PAYEMS",
    "GDPC1",
    "SP500",
    "VIXCLS",
    "VXVCLS",
    "DTWEXBGS",
    "DCPF3M",
    "DTB3",
    "NFCI",
    "BAMLH0A0HYM2",
    "BAMLC0A0CM",
    "IRLTLT01JPM156N",
    "IRLTLT01DEM156N",
    "IRLTLT01GBM156N",
    "DCOILWTICO",
    "DHHNGSP",
    "OVXCLS",
    "GVZCLS",
    "DGS10",
    "NASDAQXNDX",
    "NASDAQNQUS500LCT",
    "NASDAQBANK",
    "BAMLHYH0A0HYM2TRIV",
    "BAMLCC0A0CMTRIV",
]


def build_live_dashboard() -> dict[str, Any]:
    source_status: list[dict[str, str]] = []
    curve_records: list[YieldCurveRecord] = []
    auctions: list[dict[str, object]] = []
    announced_auctions: list[dict[str, object]] = []
    calendar_events: list[CalendarEvent] = []
    fomc_projection: FomcProjection | None = None
    fred: dict[str, TimeSeries] = {}
    acm: AcmRecord | None = None
    cftc_positions: list[CftcTreasuryPosition] = []
    tic_holdings: TicHoldings | None = None
    primary_dealer_stats: PrimaryDealerStats | None = None
    quarterly_refunding: QuarterlyRefunding | None = None
    debt_limit_status: DebtLimitStatus | None = None
    fed_funds_futures: MarketQuote | None = None
    gold_quote: MarketQuote | None = None
    official_news: list[NewsItem] = []

    try:
        curve_records = fetch_treasury_yield_curves()
        latest = curve_records[-1].date.isoformat() if curve_records else "none"
        source_status.append({"name": "U.S. Treasury yield curve XML", "status": "ok", "latest": latest})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "U.S. Treasury yield curve XML", "status": "error", "latest": str(exc)})

    try:
        fred = fetch_fred_series_bulk(FRED_SERIES)
        for series_id in FRED_SERIES:
            series = fred.get(series_id)
            if series:
                source_status.append({"name": f"FRED {series_id}", "status": "ok", "latest": series.latest.date.isoformat()})
            else:
                source_status.append({"name": f"FRED {series_id}", "status": "error", "latest": "missing from bulk daily.csv"})
    except Exception as exc:  # noqa: BLE001
        for series_id in FRED_SERIES:
            source_status.append({"name": f"FRED {series_id}", "status": "error", "latest": str(exc)})

    try:
        auctions = fetch_treasury_auctions()
        source_status.append({"name": "TreasuryDirect auctioned securities", "status": "ok", "latest": str(len(auctions))})
    except Exception as exc:  # noqa: BLE001
        auctions = load_historical_auction_fallback()
        if auctions:
            latest = max(str(item.get("auctionDate") or "") for item in auctions)
            source_status.append(
                {
                    "name": "TreasuryDirect auctioned securities",
                    "status": "warning",
                    "latest": f"live fetch failed; using {len(auctions)} cached observations through {latest}: {exc}",
                }
            )
        else:
            source_status.append({"name": "TreasuryDirect auctioned securities", "status": "error", "latest": str(exc)})

    try:
        announced_auctions = fetch_announced_auctions()
        source_status.append({"name": "TreasuryDirect announced securities", "status": "ok", "latest": str(len(announced_auctions))})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "TreasuryDirect announced securities", "status": "warning", "latest": str(exc)})

    try:
        calendar_events = fetch_fomc_calendar_events()
        latest = max((event.date for event in calendar_events), default=None)
        source_status.append({"name": "Federal Reserve FOMC calendar", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Federal Reserve FOMC calendar", "status": "error", "latest": str(exc)})

    try:
        macro_events = fetch_fred_macro_release_events()
        calendar_events.extend(macro_events)
        latest = max((event.date for event in macro_events), default=None)
        source_status.append({"name": "FRED economic release calendar", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "FRED economic release calendar", "status": "error", "latest": str(exc)})

    try:
        bea_events = fetch_bea_release_events()
        calendar_events.extend(bea_events)
        latest = max((event.date for event in bea_events), default=None)
        source_status.append({"name": "BEA release schedule", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "BEA release schedule", "status": "error", "latest": str(exc)})

    try:
        fomc_projection = fetch_fomc_projection()
        source_status.append({"name": "Federal Reserve SEP projections", "status": "ok", "latest": fomc_projection.release_date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Federal Reserve SEP projections", "status": "warning", "latest": str(exc)})

    try:
        acm = fetch_acm_term_premium()
        source_status.append({"name": "NY Fed ACM term premium", "status": "ok", "latest": acm.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "NY Fed ACM term premium", "status": "error", "latest": str(exc)})

    try:
        cftc_positions = fetch_cftc_treasury_positions()
        latest = cftc_positions[0].report_date.isoformat() if cftc_positions else "none"
        source_status.append({"name": "CFTC financial futures COT", "status": "ok", "latest": latest})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "CFTC financial futures COT", "status": "error", "latest": str(exc)})

    try:
        tic_holdings = fetch_tic_major_holders()
        source_status.append({"name": "Treasury TIC major foreign holders", "status": "ok", "latest": tic_holdings.period})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Treasury TIC major foreign holders", "status": "error", "latest": str(exc)})

    try:
        primary_dealer_stats = fetch_primary_dealer_stats()
        source_status.append({"name": "NY Fed primary dealer statistics", "status": "ok", "latest": primary_dealer_stats.as_of.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "NY Fed primary dealer statistics", "status": "error", "latest": str(exc)})

    try:
        quarterly_refunding = fetch_quarterly_refunding()
        source_status.append({"name": "U.S. Treasury quarterly refunding documents", "status": "ok", "latest": quarterly_refunding.release_date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "U.S. Treasury quarterly refunding documents", "status": "error", "latest": str(exc)})

    try:
        debt_limit_status = fetch_debt_limit_status()
        source_status.append({"name": "Treasury Fiscal Data debt subject to limit", "status": "ok", "latest": debt_limit_status.record_date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Treasury Fiscal Data debt subject to limit", "status": "error", "latest": str(exc)})

    try:
        fed_funds_futures = fetch_fed_funds_futures_quote()
        source_status.append({"name": "Stooq 30-Day Fed Funds futures ZQ.F", "status": "ok", "latest": fed_funds_futures.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Stooq 30-Day Fed Funds futures ZQ.F", "status": "error", "latest": str(exc)})

    try:
        gold_quote = fetch_gold_spot_quote()
        source_status.append({"name": "Stooq gold spot XAUUSD", "status": "ok", "latest": gold_quote.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Stooq gold spot XAUUSD", "status": "error", "latest": str(exc)})

    try:
        fed_news = fetch_federal_reserve_press_releases()
        official_news.extend(fed_news)
        latest = max((item.date for item in fed_news), default=None)
        source_status.append({"name": "Federal Reserve press release RSS", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Federal Reserve press release RSS", "status": "warning", "latest": str(exc)})

    try:
        treasury_news = fetch_treasury_press_releases()
        official_news.extend(treasury_news)
        latest = max((item.date for item in treasury_news), default=None)
        source_status.append({"name": "U.S. Treasury press releases", "status": "ok", "latest": latest.isoformat() if latest else "none"})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "U.S. Treasury press releases", "status": "warning", "latest": str(exc)})

    dashboard = build_dashboard_from_inputs(
        curve_records=curve_records,
        fred=fred,
        auctions=auctions,
        generated_at=datetime.now(timezone.utc),
        acm=acm,
        cftc_positions=cftc_positions,
        tic_holdings=tic_holdings,
        fomc_projection=fomc_projection,
        primary_dealer_stats=primary_dealer_stats,
        quarterly_refunding=quarterly_refunding,
        debt_limit_status=debt_limit_status,
        fed_funds_futures=fed_funds_futures,
        gold_quote=gold_quote,
        official_news=official_news,
        calendar_events=calendar_events,
        announced_auctions=announced_auctions,
        overrides=load_content_overrides(),
    )
    try:
        benchmark_score = fetch_bhadial_public_score()
        macro_liquidity = dashboard.get("macroLiquidity")
        if isinstance(macro_liquidity, dict):
            local_score = optional_float(macro_liquidity.get("score"))
            macro_liquidity["benchmark"] = {
                "score": round(benchmark_score, 1),
                "delta": round(local_score - benchmark_score, 1) if local_score is not None else None,
                "sourceUrl": BHADIAL_SCORE_SOURCE_URL,
                "status": "ok",
            }
        source_status.append({"name": "Bhadial public score benchmark", "status": "ok", "latest": f"{benchmark_score:.1f}"})
    except Exception as exc:  # noqa: BLE001
        macro_liquidity = dashboard.get("macroLiquidity")
        if isinstance(macro_liquidity, dict):
            macro_liquidity["benchmark"] = {"sourceUrl": BHADIAL_SCORE_SOURCE_URL, "status": "warning", "latest": str(exc)}
        source_status.append({"name": "Bhadial public score benchmark", "status": "warning", "latest": str(exc)})
    dashboard["sourceStatus"] = source_status + dashboard.get("sourceStatus", [])
    dashboard["conclusionAudit"] = build_conclusion_audit(dashboard.get("groups", []), source_status=dashboard["sourceStatus"])
    return dashboard


def load_historical_auction_fallback(db_path: Path | None = None) -> list[dict[str, object]]:
    path = db_path or PROJECT_ROOT / "data" / "history.sqlite3"
    if not path.exists():
        return []
    query = """
        select date, label, value
        from historical_observations
        where category = 'auction'
          and name = '拍卖投标倍数'
        order by date
    """
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(query).fetchall()
    except sqlite3.Error:
        return []
    auctions: list[dict[str, object]] = []
    for auction_date, label, bid_to_cover in rows:
        term, security_type = split_auction_label(str(label or ""))
        auctions.append(
            {
                "auctionDate": str(auction_date),
                "securityTerm": term,
                "securityType": security_type,
                "bidToCoverRatio": str(bid_to_cover),
            }
        )
    return auctions


def split_auction_label(label: str) -> tuple[str, str]:
    normalized = label.strip()
    for security_type in ("TIPS", "FRN", "Bill", "Note", "Bond"):
        suffix = f" {security_type}"
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].strip(), security_type
    return normalized, ""


def parse_bhadial_public_score(html_content: str) -> float:
    patterns = (
        r'class="hero-gauge-score"[^>]*>\s*([0-9]+(?:\.[0-9]+)?)\s*<',
        r'"marketingTeaser"\s*:\s*\{[^}]*"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
    )
    for pattern in patterns:
        match = re.search(pattern, html_content)
        if match:
            return float(match.group(1))
    raise ValueError("Bhadial public score was not found in the dashboard HTML")


def fetch_bhadial_public_score(timeout: int = 12) -> float:
    return parse_bhadial_public_score(fetch_text_curl_first(BHADIAL_SCORE_SOURCE_URL, timeout=timeout, retries=0))


def build_dashboard_from_inputs(
    *,
    curve_records: list[YieldCurveRecord],
    fred: dict[str, TimeSeries],
    auctions: list[dict[str, object]],
    generated_at: datetime,
    acm: AcmRecord | None = None,
    cftc_positions: list[CftcTreasuryPosition] | None = None,
    tic_holdings: TicHoldings | None = None,
    fomc_projection: FomcProjection | None = None,
    primary_dealer_stats: PrimaryDealerStats | None = None,
    quarterly_refunding: QuarterlyRefunding | None = None,
    debt_limit_status: DebtLimitStatus | None = None,
    fed_funds_futures: MarketQuote | None = None,
    gold_quote: MarketQuote | None = None,
    official_news: list[NewsItem] | None = None,
    calendar_events: list[CalendarEvent] | None = None,
    announced_auctions: list[dict[str, object]] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not curve_records:
        raise ValueError("A real Treasury yield curve is required to build dashboard data")

    today = curve_records[-1]
    one_day = nearest_record(curve_records[:-1] or curve_records, today.date - timedelta(days=1))
    one_week = nearest_record(curve_records, today.date - timedelta(days=7))
    one_month = nearest_record(curve_records, today.date - timedelta(days=30))

    d1 = [round(today.values[tenor] - one_day.values[tenor], 4) for tenor in TENORS]
    curve = {
        "tenors": TENORS,
        "today": [today.values[tenor] for tenor in TENORS],
        "w1": [one_week.values[tenor] for tenor in TENORS],
        "m1": [one_month.values[tenor] for tenor in TENORS],
        "d1": d1,
    }

    indicators = compute_indicators(
        today=today,
        one_week=one_week,
        one_month=one_month,
        curve_records=curve_records,
        fred=fred,
        fed_funds_futures=fed_funds_futures,
        gold_quote=gold_quote,
    )
    cftc_positions = cftc_positions or []
    groups = build_groups(
        indicators,
        auctions=auctions,
        cftc_positions=cftc_positions,
        tic_holdings=tic_holdings,
        acm=acm,
        primary_dealer_stats=primary_dealer_stats,
        quarterly_refunding=quarterly_refunding,
        debt_limit_status=debt_limit_status,
        official_news=official_news or [],
    )
    policy = build_policy(indicators)
    macro_liquidity = build_macro_liquidity_score(indicators)
    macro_liquidity_equity = build_macro_liquidity_equity_lead(indicators)
    spy_early_warning = build_spy_early_warning(macro_liquidity, macro_liquidity_equity, indicators.get("percentile_series", {}))
    bhadial_coverage = build_bhadial_coverage(groups)
    source_status = [
        {"name": "Fed path", "status": "modeled", "latest": "public futures proxy + curve/macro model" if fed_funds_futures else "curve/macro proxy"},
    ]
    if acm is None:
        source_status.append({"name": "NY Fed ACM term premium", "status": "modeled", "latest": "10Y minus effective policy proxy"})
    if not cftc_positions:
        source_status.append({"name": "CFTC financial futures COT", "status": "manual-placeholder", "latest": "weekly parser unavailable"})
    if tic_holdings is None:
        source_status.append({"name": "Treasury TIC major foreign holders", "status": "manual-placeholder", "latest": "monthly parser unavailable"})
    if primary_dealer_stats is None:
        source_status.append({"name": "NY Fed primary dealer statistics", "status": "manual-placeholder", "latest": "weekly parser unavailable"})
    if quarterly_refunding is None:
        source_status.append({"name": "U.S. Treasury quarterly refunding documents", "status": "manual-placeholder", "latest": "QRA parser unavailable"})
    if debt_limit_status is None:
        source_status.append({"name": "Treasury Fiscal Data debt subject to limit", "status": "manual-placeholder", "latest": "debt-limit parser unavailable"})
    if fomc_projection is None:
        source_status.append({"name": "Federal Reserve SEP projections", "status": "manual-placeholder", "latest": "projection parser unavailable"})
    if not calendar_events and not announced_auctions:
        source_status.append({"name": "Official event calendar", "status": "manual-placeholder", "latest": "official event feeds unavailable"})
    if not official_news:
        source_status.append({"name": "Official news flow", "status": "manual-placeholder", "latest": "official news feeds unavailable"})
    conclusion_audit = build_conclusion_audit(groups, source_status=source_status)

    dashboard = {
        "asOf": today.date.isoformat(),
        "generatedAt": generated_at.replace(microsecond=0).isoformat(),
        "meta": {
            "dataMode": "real-public-sources",
            "remoteCompatibility": {
                "sourceUrl": "https://us-treasury-bonds-monitor-luffa.vercel.app/",
                "factorNames": REMOTE_COMPATIBILITY_FACTOR_NAMES,
                "scoringRule": "-2..+2 duration score, optional curve score; sourceMode marks real, proxy, modeled, official-news, or manual-placeholder data boundaries.",
            },
            "bhadialCompatibility": {
                "sourceUrl": "https://bhadial.com/",
                "moduleCount": len(BHADIAL_MODULE_NAMES),
                "modules": BHADIAL_MODULE_NAMES,
                "coverage": bhadial_coverage,
                "scoringRule": "5Y historical percentile layer plus level, deviation, target-distance, shock-only, and risk-signal interpretations where public inputs exist.",
                "gapBoundary": "ETF-exact relative-performance factors are represented by real public FRED/Nasdaq proxies where free local market-history feeds are unstable or unavailable.",
            },
            "notes": [
                "Treasury curve, QRA documents, Fiscal Data debt-limit tables, FRED macro/liquidity/cross-market series, TreasuryDirect auctions, Federal Reserve FOMC calendar, NY Fed ACM, NY Fed primary dealer statistics, CFTC COT, and TIC are fetched from public sources when available.",
                "Fed path probabilities are model estimates derived from public Fed Funds futures proxy, real curve, and macro pressure, not CME FedWatch official probabilities.",
                "Fed and Treasury official public news headlines are fetched when available; broader full-text market news remains curated because reliable redistribution usually requires licensed feeds.",
                "Remote-site narrative compatibility factors are preserved as explicit real/proxy/modeled/manual sourceMode rows rather than disguised as fully live market feeds.",
                "Bhadial-style module factors are filled with real public or derived-public series where possible; unsupported ETF-relative factors are not synthesized from unrelated data.",
            ],
        },
        "sourceStatus": source_status,
        "curve": curve,
        "decomposition": build_decomposition(indicators, acm=acm, fomc_projection=fomc_projection),
        "fedPath": build_fed_path(indicators),
        "groups": groups,
        "conclusionAudit": conclusion_audit,
        "macroLiquidity": macro_liquidity,
        "macroLiquidityEquity": macro_liquidity_equity,
        "spyEarlyWarning": spy_early_warning,
        "policy": policy,
        "auctions": build_auctions(auctions),
        "fiscal": build_fiscal(indicators, quarterly_refunding=quarterly_refunding, debt_limit_status=debt_limit_status),
        "positioning": build_positioning(cftc_positions=cftc_positions, tic_holdings=tic_holdings, primary_dealer_stats=primary_dealer_stats),
        "cross": build_cross_market(indicators),
        "percentiles": build_percentiles(indicators, auctions),
        "events": build_events(today.date, calendar_events=calendar_events or [], announced_auctions=announced_auctions or [], quarterly_refunding=quarterly_refunding),
        "news": build_news(today.date, indicators, quarterly_refunding=quarterly_refunding, official_news=official_news),
        "ideas": build_ideas(
            indicators,
            macro_liquidity=macro_liquidity,
            macro_liquidity_equity=macro_liquidity_equity,
            quarterly_refunding=quarterly_refunding,
            conclusion_audit=conclusion_audit,
        ),
    }
    return apply_content_overrides(dashboard, overrides or {})


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
    rrp_millions = latest_value(fred, "RRPONTSYD", default=0.0)
    net_liquidity_points = build_net_liquidity_points(fred)
    net_liquidity_latest = net_liquidity_points[-1].value if net_liquidity_points else walcl_millions - tga_millions - rrp_millions
    net_liquidity_m1_change = point_change(net_liquidity_points, days=30)
    net_liquidity_momentum_points = change_points(net_liquidity_points, days=30)
    net_liquidity_13w_change = point_change(net_liquidity_points, days=91)
    net_liquidity_13w_momentum_points = change_points(net_liquidity_points, days=91)
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
    hy_ig_oas_spread_points = spread_points(fred.get("BAMLH0A0HYM2"), fred.get("BAMLC0A0CM"), multiplier=100)
    vix_term_structure_points = ratio_points(fred.get("VIXCLS"), fred.get("VXVCLS"))
    dxy_realized_vol_points = realized_volatility_points(fred.get("DTWEXBGS"), window=63)
    oil_vol_deviation_points = rolling_median_deviation_points(fred.get("OVXCLS"), window_days=365, positive_only=True)
    wti_shock_points = rolling_median_deviation_points(fred.get("DCOILWTICO"), window_days=365, positive_only=True)
    natgas_shock_points = rolling_median_deviation_points(fred.get("DHHNGSP"), window_days=365, positive_only=True)
    treasury_30y10y_points = curve_spread_points(curve_records, "30Y", "10Y", multiplier=100)
    treasury_10y_vol_21d_points = curve_realized_volatility_points(curve_records, "10Y", window=21)
    curve_curvature_abs_points = treasury_curve_curvature_abs_points(curve_records)
    treasury_price_proxy_points = treasury_price_proxy_from_yield_points(fred.get("DGS10"), duration=8.0)
    treasury_price_proxy_series = TimeSeries("DGS10_PRICE_PROXY", treasury_price_proxy_points) if treasury_price_proxy_points else None
    risk_vs_safe_points = ratio_points(fred.get("SP500"), treasury_price_proxy_series)
    high_beta_preference_points = ratio_points(fred.get("NASDAQXNDX"), fred.get("NASDAQNQUS500LCT"))
    regional_bank_vs_market_points = ratio_points(fred.get("NASDAQBANK"), fred.get("SP500"))
    hy_credit_preference_points = ratio_points(fred.get("BAMLHYH0A0HYM2TRIV"), treasury_price_proxy_series)
    ig_credit_preference_points = ratio_points(fred.get("BAMLCC0A0CMTRIV"), treasury_price_proxy_series)
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
    cpi_yoy = yoy(fred.get("CPIAUCSL"))
    pce_yoy = yoy(fred.get("PCEPI"))
    core_pce_yoy = yoy(fred.get("PCEPILFE"))
    trimmed_mean_pce_yoy = latest_value(fred, "PCETRIM12M159SFRBDAL", default=0.0)
    ppi_yoy = yoy(fred.get("PPIACO"))
    unrate = latest_value(fred, "UNRATE", default=0.0)
    payroll_latest = fred.get("PAYEMS").latest.value if fred.get("PAYEMS") else 0.0
    payroll_prior = fred.get("PAYEMS").points[-2].value if fred.get("PAYEMS") and len(fred["PAYEMS"].points) > 1 else payroll_latest
    payroll_change_k = payroll_latest - payroll_prior
    gdp_yoy = yoy(fred.get("GDPC1"))
    futures_implied_rate = fed_funds_futures.implied_rate if fed_funds_futures else None
    return {
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
        "curve_curvature_abs_bp": abs(2 * ten_year - two_year - thirty_year) * 100,
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
        "dff": dff,
        "target_range": target_range_from_effective_rate(dff),
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
        "rrp_trillions": rrp_millions / 1_000_000,
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
        "gold_spot": gold_quote.close if gold_quote else 0.0,
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


def compute_tenor_realized_volatility(records: list[YieldCurveRecord], tenor: str, window: int = 20) -> float:
    ordered = sorted(records, key=lambda item: item.date)
    changes_bp: list[float] = []
    for prior, current in zip(ordered, ordered[1:]):
        if tenor not in prior.values or tenor not in current.values:
            continue
        changes_bp.append((current.values[tenor] - prior.values[tenor]) * 100)
    sample = changes_bp[-window:]
    if len(sample) < 2:
        return 0.0
    mean = sum(sample) / len(sample)
    variance = sum((item - mean) ** 2 for item in sample) / (len(sample) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def historical_percentile(current: float, values: list[float]) -> int | None:
    sample = [value for value in values if math.isfinite(value)]
    if len(sample) < 2:
        return None
    less = sum(1 for value in sample if value < current)
    equal = sum(1 for value in sample if value == current)
    if equal:
        rank = less + (equal - 1) / 2
        denominator = len(sample) - 1
    else:
        rank = less
        denominator = len(sample)
    if denominator <= 0:
        return None
    return max(0, min(100, round((rank / denominator) * 100)))


def window_start(end: date, years: int = 5) -> date:
    try:
        return end.replace(year=end.year - years)
    except ValueError:
        return end.replace(year=end.year - years, day=28)


def series_percentile(series: TimeSeries | None, years: int = 5) -> int | None:
    if not series or not series.points:
        return None
    latest = series.latest
    start = window_start(latest.date, years=years)
    values = [point.value for point in series.points if start <= point.date <= latest.date]
    return historical_percentile(latest.value, values)


def point_series_percentile(points: list[SeriesPoint], current: float | None = None, years: int = 5) -> int | None:
    if not points:
        return None
    latest = points[-1]
    start = window_start(latest.date, years=years)
    values = [point.value for point in points if start <= point.date <= latest.date]
    return historical_percentile(latest.value if current is None else current, values)


def sampled_indices(length: int, max_points: int) -> list[int]:
    if length <= 0:
        return []
    if length <= max_points:
        return list(range(length))
    if max_points <= 1:
        return [length - 1]
    last = length - 1
    return sorted({round(index * last / (max_points - 1)) for index in range(max_points)})


def historical_percentile_points(
    points: list[SeriesPoint],
    *,
    years: int = 5,
    display_years: int = 3,
    max_points: int = 52,
    value_divisor: float = 1.0,
    value_digits: int = 2,
) -> list[dict[str, Any]]:
    ordered = sorted((point for point in points if math.isfinite(point.value)), key=lambda item: item.date)
    if not ordered:
        return []
    display_start = window_start(ordered[-1].date, years=display_years)
    visible_indices = [index for index, point in enumerate(ordered) if point.date >= display_start]
    sampled_visible_indices = sampled_indices(len(visible_indices), max_points)
    rows: list[dict[str, Any]] = []
    for visible_index in sampled_visible_indices:
        index = visible_indices[visible_index]
        point = ordered[index]
        start = window_start(point.date, years=years)
        values = [candidate.value for candidate in ordered[: index + 1] if start <= candidate.date <= point.date]
        percentile = historical_percentile(point.value, values)
        if percentile is None:
            continue
        rows.append(
            {
                "date": point.date.isoformat(),
                "value": round(point.value / value_divisor, value_digits),
                "percentile": percentile,
            }
        )
    return rows


def build_net_liquidity_points(fred: dict[str, TimeSeries]) -> list[SeriesPoint]:
    walcl = fred.get("WALCL")
    tga = fred.get("WTREGEN")
    rrp = fred.get("RRPONTSYD")
    if not walcl or not tga or not rrp:
        return []
    points: list[SeriesPoint] = []
    for point in walcl.points:
        tga_point = tga.value_at_or_before(point.date)
        rrp_point = rrp.value_at_or_before(point.date)
        points.append(SeriesPoint(point.date, point.value - tga_point.value - rrp_point.value))
    return points


def point_change(points: list[SeriesPoint], days: int) -> float:
    if not points:
        return 0.0
    latest = points[-1]
    prior = points[0]
    target = latest.date - timedelta(days=days)
    for point in reversed(points):
        if point.date <= target:
            prior = point
            break
    return latest.value - prior.value


def change_points(points: list[SeriesPoint], days: int) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    for point in points:
        prior = points[0]
        target = point.date - timedelta(days=days)
        for candidate in reversed(points):
            if candidate.date <= target:
                prior = candidate
                break
        if prior.date < point.date:
            rows.append(SeriesPoint(point.date, point.value - prior.value))
    return rows


def spread_points(left: TimeSeries | None, right: TimeSeries | None, multiplier: float = 1.0) -> list[SeriesPoint]:
    if not left or not right:
        return []
    rows: list[SeriesPoint] = []
    for point in left.points:
        right_point = right.value_at_or_before(point.date)
        rows.append(SeriesPoint(point.date, (point.value - right_point.value) * multiplier))
    return rows


def ratio_points(numerator: TimeSeries | None, denominator: TimeSeries | None) -> list[SeriesPoint]:
    if not numerator or not denominator:
        return []
    rows: list[SeriesPoint] = []
    for point in numerator.points:
        denominator_point = denominator.value_at_or_before(point.date)
        if denominator_point.value == 0:
            continue
        rows.append(SeriesPoint(point.date, point.value / denominator_point.value))
    return rows


def weighted_points(left: TimeSeries | None, right: TimeSeries | None, left_weight: float, right_weight: float) -> list[SeriesPoint]:
    if not left or not right:
        return []
    rows: list[SeriesPoint] = []
    for point in left.points:
        right_point = right.value_at_or_before(point.date)
        rows.append(SeriesPoint(point.date, point.value * left_weight + right_point.value * right_weight))
    return rows


def rolling_median_deviation_points(series: TimeSeries | None, *, window_days: int, positive_only: bool = False) -> list[SeriesPoint]:
    if not series:
        return []
    return rolling_median_deviation_points_from_points(series.points, window_days=window_days, positive_only=positive_only)


def rolling_median_deviation_points_from_points(points: list[SeriesPoint], *, window_days: int, positive_only: bool = False) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    ordered = sorted(points, key=lambda item: item.date)
    for index, point in enumerate(ordered):
        start = point.date - timedelta(days=window_days)
        values = [candidate.value for candidate in ordered[: index + 1] if start <= candidate.date <= point.date and math.isfinite(candidate.value)]
        if len(values) < 2:
            continue
        deviation = point.value - median(values)
        rows.append(SeriesPoint(point.date, max(0.0, deviation) if positive_only else deviation))
    return rows


def target_distance_points(series: TimeSeries | None, *, target: float) -> list[SeriesPoint]:
    if not series:
        return []
    return [SeriesPoint(point.date, abs(point.value - target)) for point in series.points if math.isfinite(point.value)]


def curve_spread_points(records: list[YieldCurveRecord], left: str, right: str, *, multiplier: float = 1.0) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    for record in sorted(records, key=lambda item: item.date):
        if left in record.values and right in record.values:
            rows.append(SeriesPoint(record.date, (record.values[left] - record.values[right]) * multiplier))
    return rows


def treasury_curve_curvature_abs_points(records: list[YieldCurveRecord]) -> list[SeriesPoint]:
    rows: list[SeriesPoint] = []
    for record in sorted(records, key=lambda item: item.date):
        if all(tenor in record.values for tenor in ("2Y", "10Y", "30Y")):
            rows.append(SeriesPoint(record.date, abs(record.values["30Y"] - 2 * record.values["10Y"] + record.values["2Y"]) * 100))
    return rows


def curve_realized_volatility_points(records: list[YieldCurveRecord], tenor: str, *, window: int) -> list[SeriesPoint]:
    ordered = sorted(records, key=lambda item: item.date)
    rows: list[SeriesPoint] = []
    changes: list[tuple[date, float]] = []
    for prior, current in zip(ordered, ordered[1:]):
        if tenor not in prior.values or tenor not in current.values:
            continue
        changes.append((current.date, (current.values[tenor] - prior.values[tenor]) * 100))
        sample = [value for _, value in changes[-window:]]
        if len(sample) < 2:
            continue
        mean = sum(sample) / len(sample)
        variance = sum((item - mean) ** 2 for item in sample) / (len(sample) - 1)
        rows.append(SeriesPoint(current.date, math.sqrt(variance) * math.sqrt(252)))
    return rows


def onrrp_buffer_risk_points(series: TimeSeries | None, *, threshold_millions: float = 100_000.0) -> list[SeriesPoint]:
    if not series:
        return []
    rows: list[SeriesPoint] = []
    for point in series.points:
        depletion = max(0.0, min(1.0, (threshold_millions - point.value) / threshold_millions))
        rows.append(SeriesPoint(point.date, depletion**2))
    return rows


def realized_volatility_points(series: TimeSeries | None, *, window: int = 63) -> list[SeriesPoint]:
    if not series:
        return []
    ordered = sorted((point for point in series.points if point.value > 0), key=lambda item: item.date)
    rows: list[SeriesPoint] = []
    returns: list[tuple[date, float]] = []
    for prior, current in zip(ordered, ordered[1:]):
        returns.append((current.date, math.log(current.value / prior.value)))
        sample = [value for _, value in returns[-window:]]
        if len(sample) < 2:
            continue
        mean = sum(sample) / len(sample)
        variance = sum((value - mean) ** 2 for value in sample) / (len(sample) - 1)
        rows.append(SeriesPoint(current.date, math.sqrt(variance) * math.sqrt(252) * 100))
    return rows


def treasury_price_proxy_from_yield_points(series: TimeSeries | None, *, duration: float = 8.0) -> list[SeriesPoint]:
    if not series:
        return []
    rows: list[SeriesPoint] = []
    for point in series.points:
        if not math.isfinite(point.value):
            continue
        rows.append(SeriesPoint(point.date, 100 * math.exp(-duration * point.value / 100)))
    return rows


def funding_fragmentation_points(
    sofr: TimeSeries | None,
    obfr: TimeSeries | None,
    iorb: TimeSeries | None,
    rrp_award: TimeSeries | None,
    *,
    z_window: int = 252,
    smooth_window: int = 21,
) -> list[SeriesPoint]:
    if not sofr or not obfr or not iorb or not rrp_award:
        return []
    legs: list[tuple[date, float, float, float]] = []
    for point in sofr.points:
        obfr_point = obfr.value_at_or_before(point.date)
        iorb_point = iorb.value_at_or_before(point.date)
        rrp_point = rrp_award.value_at_or_before(point.date)
        legs.append(
            (
                point.date,
                (point.value - obfr_point.value) * 100,
                (point.value - iorb_point.value) * 100,
                (point.value - rrp_point.value) * 100,
            )
        )
    smoothed: list[SeriesPoint] = []
    ema: float | None = None
    alpha = 2 / (smooth_window + 1)
    for index, (point_date, *values) in enumerate(legs):
        z_scores: list[float] = []
        for leg_index, value in enumerate(values):
            sample = [row[leg_index + 1] for row in legs[max(0, index - z_window + 1) : index + 1]]
            if len(sample) < 3:
                z_scores.append(0.0)
                continue
            leg_median = median(sample)
            deviations = [abs(item - leg_median) for item in sample]
            mad = median(deviations)
            z_scores.append(0.0 if mad == 0 else (value - leg_median) / (mad * 1.4826))
        mean_z = sum(z_scores) / len(z_scores)
        dispersion = math.sqrt(sum((value - mean_z) ** 2 for value in z_scores) / len(z_scores))
        ema = dispersion if ema is None else alpha * dispersion + (1 - alpha) * ema
        smoothed.append(SeriesPoint(point_date, ema))
    return smoothed


def latest_point_value(points: list[SeriesPoint], default: float = 0.0) -> float:
    return points[-1].value if points else default


def percentile_label(value: int | None) -> str:
    return f"历史p{value}" if value is not None else "历史p--"


def latest_value(fred: dict[str, TimeSeries], series_id: str, default: float = 0.0) -> float:
    series = fred.get(series_id)
    if not series:
        return default
    return series.latest.value


def yoy(series: TimeSeries | None) -> float:
    if not series or len(series.points) < 2:
        return 0.0
    latest = series.latest
    prior = series.value_at_or_before(date(latest.date.year - 1, latest.date.month, latest.date.day))
    if prior.value == 0:
        return 0.0
    return (latest.value / prior.value - 1) * 100


def latest_pct_change(series: TimeSeries | None) -> float:
    if not series or len(series.points) < 2:
        return 0.0
    latest = series.points[-1]
    prior = series.points[-2]
    if prior.value == 0:
        return 0.0
    return (latest.value / prior.value - 1) * 100


def target_range_from_effective_rate(rate: float) -> str:
    lower = int(rate * 4) / 4
    upper = lower + 0.25
    return f"{lower:.2f}-{upper:.2f}%"


def build_decomposition(ind: dict[str, Any], acm: AcmRecord | None = None, fomc_projection: FomcProjection | None = None) -> dict[str, Any]:
    real_short = ind["dff"] - max(ind["breakeven_10y"], 0)
    if acm is not None:
        term_premium_value = f"{acm.term_premium_10y:+.2f}%"
        term_premium_note = f"NY Fed ACM 10Y期限溢价,最新日期 {acm.date.isoformat()}。"
        term_premium_driver = "NY Fed ACM"
    else:
        term_premium_value = f"{max(ind['ten_year'] - ind['dff'], -2):+.2f}%"
        term_premium_note = "ACM拉取失败时用10Y相对短端补偿近似。"
        term_premium_driver = "模型估算"
    return {
        "components": [
            {"index": "01", "name": "短端实际利率", "en": "E[real short rate]", "value": f"~{real_short:.1f}%", "note": "由有效联邦基金利率减去10Y盈亏平衡通胀近似。", "driver": "FRED DFF + T10YIE"},
            {"index": "02", "name": "短端通胀预期", "en": "E[π short]", "value": f"~{ind['breakeven_10y']:.2f}%", "note": "用10Y盈亏平衡通胀作为公开代理。", "driver": "FRED T10YIE"},
            {"index": "03", "name": "实际期限溢价", "en": "Real term premium", "value": term_premium_value, "note": term_premium_note, "driver": term_premium_driver},
            {"index": "04", "name": "通胀风险溢价", "en": "Inflation risk prem.", "value": f"{max(ind['breakeven_10y'] - 2.3, 0):+.2f}%", "note": "以盈亏平衡通胀相对2.3%锚的偏离近似。", "driver": "模型估算"},
        ],
        "attribution": [
            {"window": "1 周", "total": round(ind["ten_year_w1_change_bp"]), "real": round(ind["ten_year_w1_change_bp"] * 0.65), "inflation": round(ind["ten_year_w1_change_bp"] * 0.35), "term": 0, "risk": 0, "driver": "真实利率+通胀"},
            {"window": "1 月", "total": round(ind["ten_year_m1_change_bp"]), "real": round(ind["ten_year_m1_change_bp"] * 0.65), "inflation": round(ind["ten_year_m1_change_bp"] * 0.35), "term": 0, "risk": 0, "driver": "真实利率+通胀"},
        ],
        "frameworkNote": (
            "Clarida框架:长期名义利率 = 预期短端真实利率 + 预期短端通胀 + "
            "实际期限溢价 + 通胀风险溢价。核心用途不是机械相加,而是把收益率变化翻译成叙事变化。"
        ),
        "regimeRead": decomposition_regime_read(ind, term_premium_value),
        "policyRead": policy_path_read(ind, fomc_projection=fomc_projection),
        "marketMeasures": {
            "dff": f"{ind['dff']:.2f}%",
            "real10y": f"{ind['real_10y']:.2f}%",
            "breakeven10y": f"{ind['breakeven_10y']:.2f}%",
            "termPremium10y": term_premium_value,
        },
        "sources": build_expectation_sources(ind, fomc_projection=fomc_projection),
    }


def decomposition_regime_read(ind: dict[str, Any], term_premium_value: str) -> str:
    monthly_move = ind["ten_year_m1_change_bp"]
    direction = "上行" if monthly_move >= 0 else "下行"
    hard_combo = ind["real_10y"] >= 2.0 and ind["breakeven_10y"] >= 2.35
    combo_text = "真实利率和通胀补偿同时偏高,这是名义久期最难缠的组合" if hard_combo else "当前更多是单一驱动,需要观察真实利率与通胀补偿是否共振"
    return (
        f"10Y过去一个月{direction}{monthly_move:+.0f}bp,真实利率{ind['real_10y']:.2f}%、"
        f"通胀补偿{ind['breakeven_10y']:.2f}%、期限溢价{term_premium_value}共同解释长端定价。"
        f"{combo_text}; 若油价或CPI/PCE/核心PCE继续超预期,收益率上行会更像通胀冲击下的政策对峙。"
    )


def policy_path_read(ind: dict[str, Any], fomc_projection: FomcProjection | None) -> str:
    sep_text = "SEP待解析"
    if fomc_projection:
        years = sorted((key for key in fomc_projection.median_fed_funds if key.isdigit()), key=int)
        if years:
            year = years[0]
            sep_text = f"SEP {year}中位数{fomc_projection.median_fed_funds[year]:.2f}%"
    futures_rate = ind.get("fed_funds_futures_implied_rate")
    futures_text = f"Fed Funds期货代理{futures_rate:.2f}%" if futures_rate is not None else "2Y/通胀模型代理"
    return (
        f"市场先跑、官方后确认: {futures_text}和2Y月变动{ind['two_year_m1_change_bp']:+.0f}bp先反映路径再定价, "
        f"{sep_text}属于低频官方锚。下一次FOMC和点阵图的关键不是单次决定,而是是否正式确认降息退潮或加息尾部风险。"
    )


def build_expectation_sources(ind: dict[str, Any], fomc_projection: FomcProjection | None) -> list[dict[str, str]]:
    if fomc_projection:
        first_year = sorted((key for key in fomc_projection.median_fed_funds if key.isdigit()), key=int)[0]
        sep_value = f"{first_year} median {fomc_projection.median_fed_funds[first_year]:.2f}%"
        sep_note = f"Federal Reserve SEP, released {fomc_projection.release_date.isoformat()}, official quarterly participant projections."
    else:
        sep_value = "等待Federal Reserve SEP"
        sep_note = "官方季度点阵图解析失败时不填入估计值。"
    inflation_pressure = max(ind["cpi_yoy"], ind["pce_yoy"], ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"])
    path_bias = "加息尾部升温" if ind["two_year_m1_change_bp"] > 10 or inflation_pressure > 3 else "持平为主"
    futures_rate = ind.get("fed_funds_futures_implied_rate")
    if futures_rate is not None:
        futures_value = f"{ind['fed_funds_futures_symbol']} implied {futures_rate:.2f}%"
        futures_note = (
            f"Stooq public quote dated {ind['fed_funds_futures_date']}; futures price "
            f"{ind['fed_funds_futures_close']:.2f} implies average fed-funds rate near {futures_rate:.2f}%. "
            "Meeting probabilities remain model-converted, not official CME FedWatch."
        )
        futures_name = "30-Day Fed Funds futures · public proxy"
    else:
        futures_value = path_bias
        futures_note = "由2Y再定价、CPI/PCE通胀跟踪与曲线压力生成,不是CME FedWatch官方概率。"
        futures_name = "公开曲线代理 · Fed path model"
    survey_anchor = "公开调查待接入"
    return [
        {"name": "美联储 SEP · 点阵图", "value": sep_value, "note": sep_note},
        {"name": futures_name, "value": futures_value, "note": futures_note},
        {"name": "调查 SPF / Blue Chip", "value": survey_anchor, "note": "调查预期通常低频且滞后;当前本地版保留为授权/后续公共源接入边界。"},
    ]


def build_fed_path(ind: dict[str, Any]) -> list[dict[str, int | str]]:
    inflation_pressure = max(ind["cpi_yoy"], ind["pce_yoy"], ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"])
    pressure = max(0, min(100, int(40 + ind["two_year_m1_change_bp"] * 0.9 + (inflation_pressure - 3.0) * 12)))
    if ind.get("fed_funds_futures_implied_rate") is not None:
        futures_gap_bp = (ind["fed_funds_futures_implied_rate"] - ind["dff"]) * 100
        pressure = max(0, min(100, int(pressure + futures_gap_bp * 0.35)))
    meetings = ["6/17", "7/29", "9/16", "10/28", "12/9"]
    path = []
    for idx, meeting in enumerate(meetings):
        hike = max(0, min(90, int(pressure * idx / 4)))
        cut = max(1, int(8 - pressure / 18 - idx))
        hold = max(0, 100 - hike - cut)
        path.append({"m": meeting, "hike": hike, "hold": hold, "cut": cut})
    return path


def inflation_tracking_score(ind: dict[str, Any]) -> int:
    broad = max(ind["cpi_yoy"], ind["pce_yoy"])
    core = max(ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"])
    if broad >= 3.5 or core >= 3.0:
        return -2
    if broad >= 2.8 or core >= 2.5:
        return -1
    if broad <= 2.2 and core <= 2.2:
        return 1
    return 0


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
) -> list[dict[str, Any]]:
    inflation_score = inflation_tracking_score(ind)
    ppi_score = -2 if ind["ppi_yoy"] >= 5.0 else -1 if ind["ppi_yoy"] >= 3.0 else 0
    two_year_score = -2 if ind["two_year_m1_change_bp"] >= 30 else -1 if ind["two_year_m1_change_bp"] >= 10 else 0
    sofr_spread_pct = ind["percentiles"].get("sofr_effr_spread")
    sofr_spread_score = -1 if sofr_spread_pct is not None and sofr_spread_pct >= 80 else 0
    bank_reserves_pct = ind["percentiles"].get("bank_reserves")
    bank_reserves_score = -1 if bank_reserves_pct is not None and bank_reserves_pct <= 20 else 1 if bank_reserves_pct is not None and bank_reserves_pct >= 60 else 0
    net_liquidity_pct = ind["percentiles"].get("net_liquidity")
    net_liquidity_score = -1 if net_liquidity_pct is not None and net_liquidity_pct <= 20 else 1 if net_liquidity_pct is not None and net_liquidity_pct >= 60 else 0
    net_liquidity_momentum_pct = ind["percentiles"].get("net_liquidity_momentum")
    net_liquidity_momentum_score = -1 if ind["net_liquidity_m1_change_trillions"] < -0.05 else 1 if ind["net_liquidity_m1_change_trillions"] > 0.05 else 0
    net_liquidity_13w_pct = ind["percentiles"].get("net_liquidity_13w_momentum")
    net_liquidity_13w_score = -1 if ind["net_liquidity_13w_change_trillions"] < -0.15 else 1 if ind["net_liquidity_13w_change_trillions"] > 0.15 else 0
    tga_deviation_pct = ind["percentiles"].get("tga_deviation")
    tga_deviation_score = -1 if ind["tga_deviation_trillions"] > 0.15 or (tga_deviation_pct is not None and tga_deviation_pct >= 80) else 1 if ind["tga_deviation_trillions"] < -0.15 else 0
    onrrp_buffer_risk_pct = ind["percentiles"].get("onrrp_buffer_risk")
    onrrp_buffer_risk_score = -2 if ind["onrrp_buffer_risk"] >= 0.75 else -1 if ind["onrrp_buffer_risk"] >= 0.35 else 0
    sofr_obfr_pct = ind["percentiles"].get("collateral_repo_friction")
    sofr_obfr_score = high_pressure_score(sofr_obfr_pct)
    sofr_iorb_pct = ind["percentiles"].get("corridor_sofr_iorb")
    sofr_iorb_score = high_pressure_score(sofr_iorb_pct)
    sofr_rrp_pct = ind["percentiles"].get("corridor_sofr_rrp")
    sofr_rrp_score = high_pressure_score(sofr_rrp_pct)
    effr_iorb_pct = ind["percentiles"].get("effr_iorb_spread")
    effr_iorb_score = high_pressure_score(effr_iorb_pct)
    cp_tbill_pct = ind["percentiles"].get("cp_tbill_spread")
    cp_tbill_score = high_pressure_score(cp_tbill_pct)
    fragmentation_pct = ind["percentiles"].get("funding_fragmentation")
    fragmentation_score = high_pressure_score(fragmentation_pct)
    real_rate_level_pct = ind["percentiles"].get("real_rate_level")
    real_curve_pct = ind["percentiles"].get("real_curve")
    nfci_pct = ind["percentiles"].get("nfci")
    nfci_score = -1 if ind["nfci"] > 0 or (nfci_pct is not None and nfci_pct >= 80) else 1 if ind["nfci"] < -0.5 and (nfci_pct is None or nfci_pct <= 35) else 0
    hy_ig_pct = ind["percentiles"].get("hy_ig_oas_spread")
    hy_ig_score = high_pressure_score(hy_ig_pct)
    vix_term_pct = ind["percentiles"].get("vix_term_structure")
    vix_term_score = -1 if ind["vix_term_structure"] > 1 or (vix_term_pct is not None and vix_term_pct >= 80) else 0
    dxy_vol_pct = ind["percentiles"].get("dxy_realized_vol")
    dxy_vol_score = high_pressure_score(dxy_vol_pct)
    oil_vol_dev_pct = ind["percentiles"].get("oil_vol_deviation")
    oil_vol_dev_score = high_pressure_score(oil_vol_dev_pct)
    natgas_pct = ind["percentiles"].get("natgas")
    natgas_score = high_pressure_score(natgas_pct)
    hy_credit_preference_pct = ind["percentiles"].get("hy_credit_preference")
    hy_credit_preference_score = low_preference_score(hy_credit_preference_pct)
    ig_credit_preference_pct = ind["percentiles"].get("ig_credit_preference")
    ig_credit_preference_score = low_preference_score(ig_credit_preference_pct)
    regional_bank_pct = ind["percentiles"].get("regional_bank_vs_market")
    regional_bank_score = low_preference_score(regional_bank_pct)
    risk_vs_safe_pct = ind["percentiles"].get("risk_vs_safe")
    risk_vs_safe_score = low_preference_score(risk_vs_safe_pct)
    high_beta_pct = ind["percentiles"].get("high_beta_preference")
    high_beta_score = low_preference_score(high_beta_pct)
    auction_signal = auction_demand_signal(auctions)
    cftc_net = sum(item.leveraged_net for item in cftc_positions)
    cftc_score = 1 if cftc_net < -150_000 else -1 if cftc_net > 150_000 else 0
    cftc_tag = f"杠杆基金净{direction_word(cftc_net)} {compact_int(abs(cftc_net))}" if cftc_positions else "待接低频解析"
    tic_change = tic_holdings.total.monthly_change_billions if tic_holdings and tic_holdings.total else None
    tic_score = -1 if tic_change is not None and tic_change < -50 else 1 if tic_change is not None and tic_change > 50 else 0
    tic_tag = f"{tic_holdings.period} 总量 {money_trillions_from_billions(tic_holdings.total.value_billions)}" if tic_holdings and tic_holdings.total else "待接月频解析"
    acm_score = 1 if acm and acm.term_premium_10y > 0.35 else 0
    acm_tag = f"ACM {acm.term_premium_10y:+.2f}%" if acm else f"10Y-EFFR {ind['ten_year'] - ind['dff']:+.2f}%"
    if quarterly_refunding:
        current_borrow = quarterly_refunding.current_quarter_borrowing_billions
        next_borrow = quarterly_refunding.next_quarter_borrowing_billions
        qra_score = -1 if current_borrow is not None and next_borrow is not None and next_borrow > current_borrow else 0
        qra_tag = f"{quarterly_refunding.quarter} · {money_billions_value(next_borrow or current_borrow)}"
        qra_note = qra_supply_note(quarterly_refunding)
    else:
        qra_score = 0
        qra_tag = "待接Treasury QRA"
        qra_note = "官方季度再融资文档不可用时不填入估计值。"
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
    return [
        {
            "id": "g1",
            "name": "货币政策",
            "en": "Monetary Policy",
            "weight": 25,
            "factors": [
                {"n": "联邦基金目标利率", "tag": ind["target_range"], "v": "限制性", "score": -1, "note": f"有效联邦基金利率 {ind['dff']:.2f}%,仍处限制性区间。"},
                {"n": "2Y 市场政策代理", "tag": f"1月 {ind['two_year_m1_change_bp']:+.0f}bp", "v": "偏鹰" if two_year_score < 0 else "中性", "score": two_year_score, "curve": 1 if two_year_score < 0 else 0, "note": "用2Y收益率月度变化代理政策路径再定价。"},
                fed_path_compatibility_factor(ind),
                chair_transition_compatibility_factor(official_news),
                {"n": "SOFR 融资锚", "tag": f"{ind['sofr']:.2f}%", "v": "高位", "score": -1, "note": "SOFR 仍在限制性区间,压制久期估值。"},
                {
                    "n": "SOFR-EFFR利差",
                    "tag": f"{ind['sofr_effr_spread_bp']:+.0f}bp · {percentile_label(sofr_spread_pct)}",
                    "v": "融资压力" if sofr_spread_score < 0 else "正常",
                    "score": sofr_spread_score,
                    "note": "参考The Dial Funding思路,用SOFR相对EFFR利差的5年历史百分位代理担保融资压力。",
                },
                bhadial_factor(
                    module="Funding",
                    name="SOFR-OBFR回购摩擦",
                    tag=f"{ind['sofr_obfr_spread_bp']:+.0f}bp · {percentile_label(sofr_obfr_pct)}",
                    value="回购偏紧" if sofr_obfr_score < 0 else "正常",
                    score=sofr_obfr_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的Collateral/Repo Friction: SOFR-OBFR,衡量担保回购相对无担保隔夜融资的压力。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="SOFR-IORB走廊摩擦",
                    tag=f"{ind['sofr_iorb_spread_bp']:+.0f}bp · {percentile_label(sofr_iorb_pct)}",
                    value="接近上沿" if sofr_iorb_score < 0 else "正常",
                    score=sofr_iorb_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的Corridor Friction 1: SOFR-IORB,衡量市场担保融资利率相对准备金利率上沿的位置。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="SOFR-ON RRP走廊摩擦",
                    tag=f"{ind['sofr_rrp_award_spread_bp']:+.0f}bp · {percentile_label(sofr_rrp_pct)}",
                    value="高于地板" if sofr_rrp_score < 0 else "正常",
                    score=sofr_rrp_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的Corridor Friction 2: SOFR-ON RRP award,衡量市场利率相对美联储隔夜逆回购利率地板的压力。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="EFFR-IORB利差",
                    tag=f"{ind['effr_iorb_spread_bp']:+.0f}bp · {percentile_label(effr_iorb_pct)}",
                    value="银行资金偏紧" if effr_iorb_score < 0 else "正常",
                    score=effr_iorb_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的EFFR-IORB Spread: 有效联邦基金利率相对准备金利率,观察银行间资金是否接近走廊上沿。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="商票-TBill利差",
                    tag=f"{ind['cp_tbill_spread_bp']:+.0f}bp · {percentile_label(cp_tbill_pct)}",
                    value="短融承压" if cp_tbill_score < 0 else "正常",
                    score=cp_tbill_score,
                    source_mode="derived-public",
                    note="Bhadial Funding的CP-TBill Spread: FRED 90日AA金融商票减3个月TBill,反映短期私人信用相对无风险利率的压力。",
                ),
                bhadial_factor(
                    module="Funding",
                    name="资金分裂度(21D)",
                    tag=f"{ind['funding_fragmentation_21d']:.2f} · {percentile_label(fragmentation_pct)}",
                    value="分裂" if fragmentation_score < 0 else "一致",
                    score=fragmentation_score,
                    source_mode="derived-public",
                    note="Bhadial Funding Fragmentation近似: 对SOFR-OBFR、SOFR-IORB、SOFR-ON RRP三条走廊利差做稳健z-score离散度并用21日EMA平滑。",
                ),
                {"n": "SOMA Treasury持仓", "tag": f"${ind['soma_treasury_trillions']:.2f}T", "v": "QT存量约束", "score": 0, "note": "以FRED TREAST跟踪美联储持有的美国国债规模,比WALCL总资产更贴近计划中的SOMA Treasury held outright。"},
                {"n": "资产负债表 / 总资产", "tag": f"WALCL ${ind['walcl_trillions']:.2f}T", "v": "中性", "score": 0, "note": "以FRED WALCL跟踪美联储资产负债表总规模。"},
            ],
        },
        {
            "id": "g2",
            "name": "宏观基本面",
            "en": "Macro Fundamentals",
            "weight": 25,
            "factors": [
                {
                    "n": "通胀跟踪",
                    "tag": (
                        f"CPI {ind['cpi_yoy']:.1f}% / PCE {ind['pce_yoy']:.1f}% / "
                        f"核心PCE {ind['core_pce_yoy']:.1f}% / Dallas Trimmed PCE {ind['trimmed_mean_pce_yoy']:.1f}%"
                    ),
                    "v": "全面偏热" if inflation_score <= -2 else "偏热" if inflation_score < 0 else "温和",
                    "score": inflation_score,
                    "note": "同时跟踪FRED CPIAUCSL、PCEPI、PCEPILFE与Dallas Fed Trimmed Mean PCE(PCETRIM12M159SFRBDAL); PCE和核心PCE更贴近Fed通胀框架,Dallas Trimmed PCE过滤极端分项噪声,适合作为政策反应函数中的底层通胀趋势观察项。",
                },
                {"n": "PPI 生产者物价", "tag": f"{ind['ppi_yoy']:.1f}% 同比", "v": "偏热" if ppi_score < 0 else "中性", "score": ppi_score, "note": "PPIACO同比衡量生产端通胀压力。"},
                {"n": "劳动力市场", "tag": f"失业率 {ind['unrate']:.1f}%", "v": "降温" if ind["unrate"] >= 4.2 else "韧性", "score": 1 if ind["unrate"] >= 4.2 else -1, "note": "失业率升温利多久期,劳动力韧性压制降息。"},
                {"n": "非农就业", "tag": f"{ind['payroll_change_k']:+.0f}k", "v": "稳健" if ind["payroll_change_k"] > 100 else "降温", "score": -1 if ind["payroll_change_k"] > 100 else 1, "curve": 1 if ind["payroll_change_k"] > 100 else 0, "note": "PAYEMS月差作为新增就业代理。"},
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
                {"n": "发行节奏 / QRA", "tag": qra_tag, "v": "供给增加" if qra_score < 0 else "中性", "score": qra_score, "curve": 1 if qra_score < 0 else 0, "note": qra_note},
                {"n": "债务上限空间", "tag": debt_headroom_tag, "v": "紧张" if debt_headroom_score < 0 else "充足", "score": debt_headroom_score, "curve": 1 if debt_headroom_score < 0 else 0, "note": debt_headroom_note},
                {"n": "10Y 收益率动量", "tag": f"1月 {ind['ten_year_m1_change_bp']:+.0f}bp", "v": "上行", "score": -1 if ind["ten_year_m1_change_bp"] > 10 else 0, "curve": 1 if ind["s5s30"] > 50 else 0, "note": "10Y月度上行代表供给/期限溢价压力。"},
                {"n": "5s30s 曲线", "tag": f"{ind['s5s30']:.0f}bp", "v": "偏陡", "score": -1 if ind["s5s30"] > 60 else 0, "curve": 1, "note": "长端相对5Y更高,供给和期限溢价压力偏强。"},
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
                    note="Bhadial Treasury的Curve Curvature Abs近似: |2*10Y - 2Y - 30Y|,用于识别长端重新定价时的曲线折点。",
                ),
                {"n": "TGA 与现金管理", "tag": f"${ind['tga_trillions']:.2f}T", "v": "抽水" if ind["tga_trillions"] > 0.7 else "中性", "score": -1 if ind["tga_trillions"] > 0.7 else 0, "note": "TGA高位会边际抽走银行体系流动性。"},
            ],
        },
        {
            "id": "g4",
            "name": "需求与持仓",
            "en": "Demand & Positioning",
            "weight": 15,
            "factors": [
                {
                    "n": "拍卖需求",
                    "tag": auction_signal["tag"],
                    "v": auction_signal["label"],
                    "score": auction_signal["score"],
                    "note": auction_signal["note"],
                },
                {"n": "TIC 海外持仓", "tag": tic_tag, "v": "走弱" if tic_score < 0 else "改善" if tic_score > 0 else "中性", "score": tic_score, "curve": 1 if tic_score < 0 else 0, "note": "TIC主要海外持有者为月频且滞后,用于衡量外资边际需求。"},
                {"n": "CFTC 杠杆基金持仓", "tag": cftc_tag, "v": "反向利多" if cftc_score > 0 else "偏空" if cftc_score < 0 else "中性", "score": cftc_score, "curve": -1 if cftc_score > 0 else 0, "note": "CFTC financial futures COT聚合国债期货杠杆基金净仓位。"},
                primary_dealer_inventory_compatibility_factor(primary_dealer_stats),
            ],
        },
        {
            "id": "g5",
            "name": "相对价值",
            "en": "Relative Value",
            "weight": 10,
            "factors": [
                {"n": "期限溢价 (ACM)", "tag": acm_tag, "v": "估值转吸引" if acm_score > 0 else "中性", "score": acm_score, "curve": -1 if acm_score > 0 else 0, "note": "NY Fed ACM期限溢价高位时,长端估值补偿更充分。"},
                {"n": "实际利率", "tag": f"10Y TIPS {ind['real_10y']:.2f}%", "v": "偏高", "score": 1 if ind["real_10y"] > 2.0 else 0, "curve": -1, "note": "高实际利率提升长期债估值吸引力。"},
                bhadial_factor(
                    module="Rates",
                    name="真实利率水平",
                    tag=f"{ind['real_rate_level']:.2f}% · {percentile_label(real_rate_level_pct)}",
                    value="融资偏紧" if ind["real_rate_level"] > 2 else "中性",
                    score=1 if ind["real_rate_level"] > 2 else 0,
                    curve=-1 if ind["real_rate_level"] > 2 else 0,
                    source_mode="derived-public",
                    note="Bhadial Rates的Real Rate Level: 60% 5Y TIPS + 40% 10Y TIPS;宏观上越高越紧,在本久期计分中代表估值补偿更高。",
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
                ),
                {"n": "盈亏平衡通胀", "tag": f"10Y BEI {ind['breakeven_10y']:.2f}%", "v": "偏高", "score": -1 if ind["breakeven_10y"] > 2.4 else 0, "note": "通胀补偿高位不利名义久期。"},
                {"n": "2s10s 曲线", "tag": f"{ind['s2s10']:.0f}bp", "v": "正斜率", "score": 0, "curve": 1 if ind["s2s10"] > 25 else 0, "note": "正斜率意味着衰退信号缓和,长端承压更明显。"},
                manual_placeholder_compatibility_factor("互换利差", "待接swap spread", "手动", "原站保留互换利差维度;本地未接入授权互换曲线,默认不改变评分,可在计分卡手动调整。"),
            ],
        },
        {
            "id": "g6",
            "name": "情绪与流动性",
            "en": "Sentiment & Liquidity",
            "weight": 10,
            "factors": [
                {
                    "n": "10Y实现波动率",
                    "tag": f"20D {ind['ten_year_realized_vol_20d_bp']:.1f}bp ann.",
                    "v": "高波动" if ind["ten_year_realized_vol_20d_bp"] > 95 else "中性",
                    "score": -1 if ind["ten_year_realized_vol_20d_bp"] > 95 else 0,
                    "note": "由U.S. Treasury curve 10Y日度收益率变动计算20日年化实现波动率,作为MOVE授权数据不可用时的公开代理。",
                },
                market_liquidity_compatibility_factor(ind),
                manual_placeholder_compatibility_factor("新老券利差", "待接on/off-run spread", "手动", "原站保留新老券利差维度;本地未接入逐券报价和融资微观数据,默认不改变评分,可手动维护。"),
                {
                    "n": "银行准备金",
                    "tag": f"${ind['bank_reserves_trillions']:.2f}T · {percentile_label(bank_reserves_pct)}",
                    "v": "宽松" if bank_reserves_score > 0 else "偏紧" if bank_reserves_score < 0 else "中性",
                    "score": bank_reserves_score,
                    "note": "FRED WRESBAL按5年历史百分位衡量银行体系准备金缓冲。",
                },
                {
                    "n": "净流动性",
                    "tag": f"${ind['net_liquidity_trillions']:.2f}T · {percentile_label(net_liquidity_pct)}",
                    "v": "宽松" if net_liquidity_score > 0 else "偏紧" if net_liquidity_score < 0 else "中性",
                    "score": net_liquidity_score,
                    "note": "参考The Dial Net Liquidity,用WALCL - TGA - ON RRP计算公开代理并按5年历史百分位评分。",
                },
                {
                    "n": "流动性动量",
                    "tag": f"1月 {ind['net_liquidity_m1_change_trillions']:+.2f}T · {percentile_label(net_liquidity_momentum_pct)}",
                    "v": "扩张" if net_liquidity_momentum_score > 0 else "收缩" if net_liquidity_momentum_score < 0 else "中性",
                    "score": net_liquidity_momentum_score,
                    "note": "净流动性1个月变化的历史百分位,用于补充The Dial Liquidity Momentum思路。",
                },
                bhadial_factor(
                    module="Liquidity",
                    name="13周净流动性动量",
                    tag=f"13周 {ind['net_liquidity_13w_change_trillions']:+.2f}T · {percentile_label(net_liquidity_13w_pct)}",
                    value="扩张" if net_liquidity_13w_score > 0 else "收缩" if net_liquidity_13w_score < 0 else "中性",
                    score=net_liquidity_13w_score,
                    source_mode="derived-public",
                    note="Bhadial Liquidity的Net Liquidity Momentum (13W): WALCL - TGA - ON RRP的13周绝对变化,捕捉QT、财政和RRP迁移的中期动量。",
                ),
                bhadial_factor(
                    module="Liquidity",
                    name="TGA偏离度",
                    tag=f"{ind['tga_deviation_trillions']:+.2f}T · {percentile_label(tga_deviation_pct)}",
                    value="抽水偏强" if tga_deviation_score < 0 else "释放" if tga_deviation_score > 0 else "正常",
                    score=tga_deviation_score,
                    source_mode="derived-public",
                    note="Bhadial Liquidity的TGA Deviation: TGA相对52周滚动中位数的偏离;正值代表财政现金累积并抽走准备金。",
                ),
                {"n": "ON RRP", "tag": f"${ind['rrp_trillions']:.3f}T", "v": "低位", "score": -1 if ind["rrp_trillions"] < 0.05 else 0, "note": "RRP接近枯竭时,流动性缓冲下降。"},
                bhadial_factor(
                    module="Liquidity",
                    name="ON RRP缓冲风险",
                    tag=f"{ind['onrrp_buffer_risk']:.2f} · {percentile_label(onrrp_buffer_risk_pct)}",
                    value="接近耗尽" if onrrp_buffer_risk_score < 0 else "有缓冲",
                    score=onrrp_buffer_risk_score,
                    source_mode="derived-public",
                    note="Bhadial Liquidity的ON RRP Buffer Risk: $100B以下用squared transformation刻画非线性耗尽风险,避免把RRP低位误读为宽松。",
                ),
                {"n": "信用利差", "tag": f"HY {ind['hy_oas']:.2f}% / IG {ind['ig_oas']:.2f}%", "v": "偏紧" if ind["hy_oas"] < 4 else "承压", "score": 0 if ind["hy_oas"] < 4 else -1, "note": "FRED ICE BofA OAS用于代理信用风险与风险偏好。"},
                bhadial_factor(
                    module="Credit",
                    name="金融条件指数(NFCI)",
                    tag=f"{ind['nfci']:+.2f} · {percentile_label(nfci_pct)}",
                    value="宽松" if nfci_score > 0 else "偏紧" if nfci_score < 0 else "中性",
                    score=nfci_score,
                    source_mode="real-public",
                    note="Bhadial Credit的NFCI: Chicago Fed National Financial Conditions Index,正值表示金融条件紧于均值,负值表示宽松。",
                ),
                bhadial_factor(
                    module="Credit",
                    name="HY-IG利差",
                    tag=f"{ind['hy_ig_oas_spread_bp']:+.0f}bp · {percentile_label(hy_ig_pct)}",
                    value="信用分层" if hy_ig_score < 0 else "正常",
                    score=hy_ig_score,
                    source_mode="derived-public",
                    note="补齐Bhadial Credit的信用分层维度;本地用FRED HY OAS - IG OAS作为公开信用相对压力代理。",
                ),
                bhadial_factor(
                    module="Credit",
                    name="HY信用偏好(HY/UST)",
                    tag=f"{ind['hy_credit_preference']:.2f} · {percentile_label(hy_credit_preference_pct)}",
                    value="偏好改善" if hy_credit_preference_score > 0 else "信用承压" if hy_credit_preference_score < 0 else "中性",
                    score=hy_credit_preference_score,
                    source_mode="proxy-public",
                    note="Bhadial HY Credit的公开代理: FRED ICE US High Yield total return index相对10Y美债价格代理,用于替代HYG/IEI ETF历史。",
                ),
                bhadial_factor(
                    module="Credit",
                    name="IG信用偏好(IG/UST)",
                    tag=f"{ind['ig_credit_preference']:.2f} · {percentile_label(ig_credit_preference_pct)}",
                    value="承接改善" if ig_credit_preference_score > 0 else "信用承压" if ig_credit_preference_score < 0 else "中性",
                    score=ig_credit_preference_score,
                    source_mode="proxy-public",
                    note="Bhadial IG Credit的公开代理: FRED ICE US Corporate total return index相对10Y美债价格代理,用于替代LQD/IEF ETF历史。",
                ),
                bhadial_factor(
                    module="Credit",
                    name="银行股相对S&P500",
                    tag=f"{ind['regional_bank_vs_market']:.2f} · {percentile_label(regional_bank_pct)}",
                    value="银行改善" if regional_bank_score > 0 else "银行承压" if regional_bank_score < 0 else "中性",
                    score=regional_bank_score,
                    source_mode="proxy-public",
                    note="Bhadial Regional Banks vs SPY的公开代理: FRED NASDAQ Bank Index相对S&P 500;不是KRE/SPY ETF精确替代,但能捕捉银行股相对风险偏好。",
                ),
                bhadial_factor(
                    module="Risk",
                    name="VIX期限结构",
                    tag=f"{ind['vix_term_structure']:.2f} · VIX3M {ind['vix_3m']:.2f}",
                    value="倒挂" if vix_term_score < 0 else "contango",
                    score=vix_term_score,
                    source_mode="derived-public",
                    note="Bhadial Risk的VIX Term Structure: VIX / VIX 3M,大于1代表波动率倒挂和风险偏好承压。",
                ),
                bhadial_factor(
                    module="Risk",
                    name="风险资产/美债代理",
                    tag=f"{ind['risk_vs_safe']:.2f} · {percentile_label(risk_vs_safe_pct)}",
                    value="risk-on" if risk_vs_safe_score > 0 else "risk-off" if risk_vs_safe_score < 0 else "中性",
                    score=risk_vs_safe_score,
                    source_mode="proxy-public",
                    note="Bhadial Risk vs Safe的公开代理: FRED S&P 500相对DGS10派生的10Y美债价格代理;用于替代SPY/TLT ETF历史。",
                ),
                bhadial_factor(
                    module="Risk",
                    name="高Beta偏好(NDX/US500)",
                    tag=f"{ind['high_beta_preference']:.2f} · {percentile_label(high_beta_pct)}",
                    value="高Beta占优" if high_beta_score > 0 else "高Beta退潮" if high_beta_score < 0 else "中性",
                    score=high_beta_score,
                    source_mode="proxy-public",
                    note="Bhadial High-Beta Preference的公开代理: FRED Nasdaq-100 Total Return相对Nasdaq US 500 Large Cap Total Return,用于替代IWM/SPY ETF历史。",
                ),
                bhadial_factor(
                    module="External",
                    name="美元实现波动率",
                    tag=f"{ind['dxy_realized_vol']:.1f}% · {percentile_label(dxy_vol_pct)}",
                    value="外部冲击" if dxy_vol_score < 0 else "稳定",
                    score=dxy_vol_score,
                    source_mode="derived-public",
                    note="Bhadial External的FX Realized Volatility近似: 对FRED美元广义指数计算63日年化实现波动率。",
                ),
                bhadial_factor(
                    module="External",
                    name="原油波动偏离",
                    tag=f"{ind['oil_vol_deviation']:.1f} · {percentile_label(oil_vol_dev_pct)}",
                    value="油市冲击" if oil_vol_dev_score < 0 else "正常",
                    score=oil_vol_dev_score,
                    source_mode="derived-public",
                    note="Bhadial External的Oil Volatility Deviation: OVX相对约1年滚动中位数的正偏离,只在恐慌高于常态时计压。",
                ),
                bhadial_factor(
                    module="External",
                    name="天然气",
                    tag=f"${ind['natgas']:.2f} · {percentile_label(natgas_pct)}",
                    value="能源压力" if natgas_score < 0 else "正常",
                    score=natgas_score,
                    source_mode="real-public",
                    note="Bhadial External的Natural Gas: FRED Henry Hub现货价格,用于补充能源冲击而非只看原油。",
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
        "compatibilityWith": REMOTE_COMPATIBILITY_SOURCE,
    }
    if curve is not None:
        factor["curve"] = curve
    return factor


def build_bhadial_coverage(groups: list[dict[str, Any]]) -> dict[str, Any]:
    scorecard_factors = {
        str(factor.get("n"))
        for group in groups
        for factor in group.get("factors", [])
        if isinstance(factor, dict) and factor.get("compatibilityWith") == BHADIAL_COMPATIBILITY_SOURCE
    }
    modules: list[dict[str, Any]] = []
    status_counts = {"public": 0, "derived": 0, "proxy": 0, "missing": 0}
    missing_factor_names: list[str] = []
    proxy_factor_names: list[str] = []
    for module in BHADIAL_FACTOR_COVERAGE:
        factors = [dict(factor) for factor in module["factors"]]
        module_counts = {"public": 0, "derived": 0, "proxy": 0, "missing": 0}
        for factor in factors:
            status = str(factor.get("status") or "missing")
            module_counts[status] = module_counts.get(status, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
            if status == "missing":
                missing_factor_names.append(str(factor["name"]))
            if status == "proxy":
                proxy_factor_names.append(str(factor["name"]))
            factor["inScorecard"] = factor.get("local") in scorecard_factors
        total = len(factors)
        missing = module_counts.get("missing", 0)
        proxy = module_counts.get("proxy", 0)
        modules.append(
            {
                "module": module["module"],
                "total": total,
                "scored": module["scored"],
                "display": module["display"],
                "covered": total - missing,
                "public": module_counts.get("public", 0),
                "derived": module_counts.get("derived", 0),
                "proxy": proxy,
                "missing": missing,
                "coveragePct": round(((total - missing) / total) * 100) if total else 0,
                "factors": factors,
            }
        )
    total_factors = sum(module["total"] for module in modules)
    missing_factors = len(missing_factor_names)
    return {
        "totalFactors": total_factors,
        "coveredFactors": total_factors - missing_factors,
        "publicFactors": status_counts.get("public", 0),
        "derivedFactors": status_counts.get("derived", 0),
        "proxyFactors": status_counts.get("proxy", 0),
        "missingFactors": missing_factors,
        "coveragePct": round(((total_factors - missing_factors) / total_factors) * 100) if total_factors else 0,
        "scorecardFactorCount": sum(int(module["scored"]) for module in BHADIAL_FACTOR_COVERAGE),
        "missingFactorNames": missing_factor_names,
        "proxyFactorNames": proxy_factor_names,
        "modules": modules,
        "nextDataSource": "ETF-exact histories such as SPY/TLT, IWM/SPY, KRE/SPY, HYG/IEI and LQD/IEF can replace these proxy-public factors when a stable local market-data feed is available.",
    }


def build_conclusion_audit(groups: list[dict[str, Any]], source_status: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    total_weight = sum(max(0.0, _float_or_zero(group.get("weight"))) for group in groups)
    duration_score = 0.0
    curve_score = 0.0
    drivers: list[dict[str, Any]] = []
    group_diagnostics: list[dict[str, Any]] = []

    for group in groups:
        factors = [factor for factor in group.get("factors", []) if isinstance(factor, dict)]
        if not factors:
            continue
        group_weight = max(0.0, _float_or_zero(group.get("weight")))
        normalized_weight = group_weight / total_weight if total_weight else 0.0
        factor_count = len(factors)
        group_duration = sum(_float_or_zero(factor.get("score")) for factor in factors) / factor_count
        group_curve = sum(_float_or_zero(factor.get("curve")) for factor in factors) / factor_count
        duration_score += group_duration * normalized_weight
        curve_score += group_curve * normalized_weight

        quality_numerator = 0.0
        quality_weight = 0.0
        for factor in factors:
            score = _float_or_zero(factor.get("score"))
            curve = _float_or_zero(factor.get("curve"))
            contribution = score * normalized_weight / factor_count
            curve_contribution = curve * normalized_weight / factor_count
            source_mode = str(factor.get("sourceMode") or "real-public")
            quality = conclusion_source_quality(source_mode)
            contribution_abs = abs(contribution)
            quality_numerator += quality * max(contribution_abs, abs(curve_contribution), 0.01)
            quality_weight += max(contribution_abs, abs(curve_contribution), 0.01)
            if contribution == 0 and curve_contribution == 0:
                continue
            drivers.append(
                {
                    "module": str(group.get("name") or group.get("id") or ""),
                    "moduleEn": str(group.get("en") or group.get("name") or group.get("id") or ""),
                    "name": str(factor.get("n") or factor.get("name") or ""),
                    "value": str(factor.get("v") or factor.get("tag") or ""),
                    "score": score,
                    "curve": curve,
                    "sourceMode": source_mode,
                    "quality": quality,
                    "contribution": contribution,
                    "curveContribution": curve_contribution,
                    "direction": "buffer" if contribution > 0 else "drag" if contribution < 0 else "curve",
                }
            )

        group_diagnostics.append(
            {
                "id": str(group.get("id") or ""),
                "name": str(group.get("name") or group.get("id") or ""),
                "en": str(group.get("en") or group.get("name") or group.get("id") or ""),
                "weight": round(group_weight, 2),
                "factorCount": factor_count,
                "durationAverage": round(group_duration, 2),
                "curveAverage": round(group_curve, 2),
                "durationContribution": round(group_duration * normalized_weight, 2),
                "curveContribution": round(group_curve * normalized_weight, 2),
                "evidenceQuality": round(quality_numerator / quality_weight, 2) if quality_weight else 1.0,
            }
        )

    source_status = source_status or []
    warning_count = sum(1 for source in source_status if _source_status(source) in {"warning", "warn"})
    error_count = sum(1 for source in source_status if _source_status(source) == "error")
    absolute_total = sum(abs(item["contribution"]) for item in drivers)
    evidence_quality = (
        sum(abs(item["contribution"]) * float(item["quality"]) for item in drivers) / absolute_total
        if absolute_total
        else 1.0
    )
    proxy_contribution = sum(
        abs(item["contribution"])
        for item in drivers
        if str(item["sourceMode"]) in LOWER_CONFIDENCE_SOURCE_MODES
    )
    concentration = max((abs(item["contribution"]) for item in drivers), default=0.0) / absolute_total if absolute_total else 0.0
    proxy_share = proxy_contribution / absolute_total if absolute_total else 0.0
    confidence_level = conclusion_confidence_level(
        evidence_quality=evidence_quality,
        concentration=concentration,
        warning_count=warning_count,
        error_count=error_count,
    )
    sorted_drivers = sorted(drivers, key=lambda item: abs(float(item["contribution"])), reverse=True)
    return {
        "duration": {"score": round(duration_score, 2), "label": conclusion_duration_label(duration_score)},
        "curve": {"score": round(curve_score, 2), "label": conclusion_curve_label(curve_score)},
        "confidence": {
            "level": confidence_level,
            "label": {"high": "高", "medium": "中等", "low": "低"}[confidence_level],
            "evidenceQuality": round(evidence_quality, 2),
            "concentration": round(concentration, 2),
            "proxyContributionShare": round(proxy_share, 2),
        },
        "sourceWarningCount": warning_count,
        "sourceErrorCount": error_count,
        "weightRecommendation": conclusion_weight_recommendation(
            evidence_quality=evidence_quality,
            concentration=concentration,
            proxy_share=proxy_share,
            warning_count=warning_count,
            error_count=error_count,
        ),
        "drivers": [round_conclusion_driver(driver) for driver in sorted_drivers[:8]],
        "groupDiagnostics": group_diagnostics,
    }


def round_conclusion_driver(driver: dict[str, Any]) -> dict[str, Any]:
    item = dict(driver)
    item["score"] = round(_float_or_zero(item.get("score")), 2)
    item["curve"] = round(_float_or_zero(item.get("curve")), 2)
    item["quality"] = round(_float_or_zero(item.get("quality")), 2)
    item["contribution"] = round(_float_or_zero(item.get("contribution")), 2)
    item["curveContribution"] = round(_float_or_zero(item.get("curveContribution")), 2)
    return item


def conclusion_source_quality(source_mode: str) -> float:
    return CONCLUSION_SOURCE_QUALITY.get(str(source_mode or "real-public"), 1.0)


def conclusion_confidence_level(*, evidence_quality: float, concentration: float, warning_count: int, error_count: int) -> str:
    if error_count > 0:
        return "low"
    if evidence_quality >= 0.82 and concentration <= 0.45 and warning_count == 0:
        return "high"
    if evidence_quality >= 0.62 and concentration <= 0.65:
        return "medium"
    return "low"


def conclusion_duration_label(score: float) -> str:
    if score <= -0.5:
        return "偏空久期"
    if score < -0.18:
        return "轻度偏空"
    if score < 0.18:
        return "中性"
    if score < 0.5:
        return "轻度偏多"
    return "偏多久期"


def conclusion_curve_label(score: float) -> str:
    if score <= -0.15:
        return "偏平坦"
    if score <= 0.15:
        return "中性"
    return "偏陡峭"


def conclusion_weight_recommendation(
    *,
    evidence_quality: float,
    concentration: float,
    proxy_share: float,
    warning_count: int,
    error_count: int,
) -> str:
    notes: list[str] = []
    if error_count:
        notes.append("存在关键数据源错误,结论应降级,暂不提高受影响因子的权重。")
    elif warning_count:
        notes.append("存在数据源警告,结论可信度不应上调到高。")
    if proxy_share >= 0.25 or evidence_quality < 0.82:
        notes.append("代理/模型因子占比偏高,权重不宜继续提高代理因子;优先接入真实市场源或降低其结论措辞强度。")
    if concentration > 0.45:
        notes.append("单一因子贡献集中,应避免让一个模块主导总判断。")
    if not notes:
        notes.append("当前权重暂不需要机械调整;更适合保留模块权重,只在新增真实数据源后再重估。")
    return "".join(notes)


def _source_status(source: dict[str, Any]) -> str:
    return str(source.get("status") or "").lower()


def _float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def bhadial_factor(
    *,
    module: str,
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
        "compatibilityWith": BHADIAL_COMPATIBILITY_SOURCE,
        "bhadialModule": module,
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


def fed_path_compatibility_factor(ind: dict[str, Any]) -> dict[str, Any]:
    path = build_fed_path(ind)
    terminal = path[-1] if path else {"m": "--", "hike": 0, "hold": 100, "cut": 0}
    hike = int(terminal.get("hike") or 0)
    hold = int(terminal.get("hold") or 0)
    cut = int(terminal.get("cut") or 0)
    if hike >= 50:
        score, value, curve = -2, "偏加息", 1
    elif hike >= 20:
        score, value, curve = -1, "加息尾部", 1
    elif cut >= 20:
        score, value, curve = 1, "偏降息", -1
    else:
        score, value, curve = 0, "中性", 0
    return compatibility_factor(
        name="隐含政策路径",
        tag=f"{terminal.get('m', '--')} 加息{hike}% / 持平{hold}% / 降息{cut}%",
        value=value,
        score=score,
        curve=curve,
        source_mode="modeled",
        note="对齐原站Fed Funds期货/OIS维度;本地用公开Fed Funds期货代理、2Y曲线再定价和通胀压力建模,非CME官方概率。",
    )


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
    payroll = float(ind.get("payroll_change_k") or 0)
    unrate = float(ind.get("unrate") or 0)
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
    score = -2 if bid_to_cover is not None and bid_to_cover < 2.35 else -1 if bid_to_cover is not None and bid_to_cover < 2.5 else 0
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
    realized_vol = float(ind.get("ten_year_realized_vol_20d_bp") or 0)
    hy_oas = float(ind.get("hy_oas") or 0)
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


def build_policy(ind: dict[str, Any]) -> dict[str, list[list[str]]]:
    return {
        "rates": [
            ["联邦基金目标区间", ind["target_range"], "由DFF近似推断"],
            ["有效联邦基金利率", f"{ind['dff']:.2f}%", "FRED DFF"],
            ["SOFR", f"{ind['sofr']:.2f}%", "FRED SOFR"],
            ["SOFR-EFFR利差", f"{ind['sofr_effr_spread_bp']:+.0f}bp", percentile_label(ind["percentiles"].get("sofr_effr_spread"))],
            ["2Y收益率", f"{ind['two_year']:.2f}%", "政策路径市场代理"],
            ["10Y收益率", f"{ind['ten_year']:.2f}%", "长端定价锚"],
            ["1月2Y变化", f"{ind['two_year_m1_change_bp']:+.0f}bp", "政策再定价"],
        ],
        "plumbing": [
            ["美联储资产负债表", f"${ind['walcl_trillions']:.2f}T", "FRED WALCL"],
            ["SOMA Treasury持仓", f"${ind['soma_treasury_trillions']:.2f}T", "FRED TREAST"],
            ["银行准备金", f"${ind['bank_reserves_trillions']:.2f}T", f"FRED WRESBAL · {percentile_label(ind['percentiles'].get('bank_reserves'))}"],
            ["净流动性", f"${ind['net_liquidity_trillions']:.2f}T", f"WALCL-TGA-RRP · {percentile_label(ind['percentiles'].get('net_liquidity'))}"],
            ["SOFR", f"{ind['sofr']:.2f}%", "隔夜融资"],
            ["ON RRP", f"${ind['rrp_trillions']:.3f}T", "FRED RRPONTSYD"],
            ["财政部一般账户", f"${ind['tga_trillions']:.2f}T", "FRED WTREGEN"],
            ["流动性结论", "边际偏紧" if ind["rrp_trillions"] < 0.05 else "中性", "公开数据代理"],
        ],
    }


def build_percentiles(ind: dict[str, Any], auctions: list[dict[str, object]]) -> dict[str, Any]:
    auction_signal = auction_demand_signal(auctions)
    items = [
        {"name": "银行准备金", "value": f"${ind['bank_reserves_trillions']:.2f}T", "percentile": ind["percentiles"].get("bank_reserves"), "source": "FRED WRESBAL", "window": "5Y"},
        {"name": "净流动性", "value": f"${ind['net_liquidity_trillions']:.2f}T", "percentile": ind["percentiles"].get("net_liquidity"), "source": "FRED WALCL - WTREGEN - RRPONTSYD", "window": "5Y"},
        {"name": "流动性动量", "value": f"{ind['net_liquidity_m1_change_trillions']:+.2f}T", "percentile": ind["percentiles"].get("net_liquidity_momentum"), "source": "Net liquidity 1M change", "window": "5Y"},
        {"name": "13周净流动性动量", "value": f"{ind['net_liquidity_13w_change_trillions']:+.2f}T", "percentile": ind["percentiles"].get("net_liquidity_13w_momentum"), "source": "Net liquidity 13W change", "window": "5Y"},
        {"name": "TGA偏离度", "value": f"{ind['tga_deviation_trillions']:+.2f}T", "percentile": ind["percentiles"].get("tga_deviation"), "source": "FRED WTREGEN - 52W median", "window": "5Y"},
        {"name": "ON RRP缓冲风险", "value": f"{ind['onrrp_buffer_risk']:.2f}", "percentile": ind["percentiles"].get("onrrp_buffer_risk"), "source": "FRED RRPONTSYD risk signal", "window": "5Y"},
        {"name": "SOFR-EFFR利差", "value": f"{ind['sofr_effr_spread_bp']:+.0f}bp", "percentile": ind["percentiles"].get("sofr_effr_spread"), "source": "FRED SOFR - DFF", "window": "5Y"},
        {"name": "商票-TBill利差", "value": f"{ind['cp_tbill_spread_bp']:+.0f}bp", "percentile": ind["percentiles"].get("cp_tbill_spread"), "source": "FRED DCPF3M - DTB3", "window": "5Y"},
        {"name": "资金分裂度(21D)", "value": f"{ind['funding_fragmentation_21d']:.2f}", "percentile": ind["percentiles"].get("funding_fragmentation"), "source": "SOFR corridor spread dispersion", "window": "5Y"},
        {"name": "真实利率水平", "value": f"{ind['real_rate_level']:.2f}%", "percentile": ind["percentiles"].get("real_rate_level"), "source": "60% DFII5 + 40% DFII10", "window": "5Y"},
        {"name": "VIX", "value": f"{ind['vix']:.2f}", "percentile": ind["percentiles"].get("vix"), "source": "FRED VIXCLS", "window": "5Y"},
        {"name": "VIX期限结构", "value": f"{ind['vix_term_structure']:.2f}", "percentile": ind["percentiles"].get("vix_term_structure"), "source": "FRED VIXCLS / VXVCLS", "window": "5Y"},
        {"name": "HY信用利差", "value": f"{ind['hy_oas']:.2f}%", "percentile": ind["percentiles"].get("hy_oas"), "source": "FRED BAMLH0A0HYM2", "window": "5Y"},
        {"name": "HY-IG利差", "value": f"{ind['hy_ig_oas_spread_bp']:+.0f}bp", "percentile": ind["percentiles"].get("hy_ig_oas_spread"), "source": "FRED HY OAS - IG OAS", "window": "5Y"},
        {"name": "HY信用偏好(HY/UST)", "value": f"{ind['hy_credit_preference']:.2f}", "percentile": ind["percentiles"].get("hy_credit_preference"), "source": "FRED HY TR / DGS10 price proxy", "window": "available up to 5Y"},
        {"name": "IG信用偏好(IG/UST)", "value": f"{ind['ig_credit_preference']:.2f}", "percentile": ind["percentiles"].get("ig_credit_preference"), "source": "FRED IG TR / DGS10 price proxy", "window": "available up to 5Y"},
        {"name": "金融条件指数(NFCI)", "value": f"{ind['nfci']:+.2f}", "percentile": ind["percentiles"].get("nfci"), "source": "FRED NFCI", "window": "5Y"},
        {"name": "银行股相对S&P500", "value": f"{ind['regional_bank_vs_market']:.2f}", "percentile": ind["percentiles"].get("regional_bank_vs_market"), "source": "FRED NASDAQBANK / SP500", "window": "5Y"},
        {"name": "风险资产/美债代理", "value": f"{ind['risk_vs_safe']:.2f}", "percentile": ind["percentiles"].get("risk_vs_safe"), "source": "FRED SP500 / DGS10 price proxy", "window": "5Y"},
        {"name": "高Beta偏好(NDX/US500)", "value": f"{ind['high_beta_preference']:.2f}", "percentile": ind["percentiles"].get("high_beta_preference"), "source": "FRED NASDAQXNDX / NASDAQNQUS500LCT", "window": "5Y"},
        {"name": "美元广义指数", "value": f"{ind['dxy']:.2f}", "percentile": ind["percentiles"].get("dxy"), "source": "FRED DTWEXBGS", "window": "5Y"},
        {"name": "美元实现波动率", "value": f"{ind['dxy_realized_vol']:.1f}%", "percentile": ind["percentiles"].get("dxy_realized_vol"), "source": "FRED DTWEXBGS 63D realized vol", "window": "5Y"},
        {"name": "原油波动偏离", "value": f"{ind['oil_vol_deviation']:.1f}", "percentile": ind["percentiles"].get("oil_vol_deviation"), "source": "FRED OVXCLS - rolling median", "window": "5Y"},
        {"name": "天然气", "value": f"${ind['natgas']:.2f}", "percentile": ind["percentiles"].get("natgas"), "source": "FRED DHHNGSP", "window": "5Y"},
        {"name": "拍卖投标倍数", "value": auction_signal["value"], "percentile": auction_signal["percentile"], "source": "TreasuryDirect auctioned securities", "window": "available sample"},
    ]
    trends = build_percentile_trends(ind, auctions)
    return {
        "method": "Historical percentile rank; FRED-derived factors use a 5Y rolling window where available, auctions use the TreasuryDirect endpoint sample.",
        "items": items,
        "trends": trends,
        "movers": build_percentile_movers(trends),
        "alerts": build_percentile_alerts(items),
    }


def build_macro_liquidity_score(ind: dict[str, Any]) -> dict[str, Any]:
    snapshot = bhadial_conditions_snapshot(ind)
    score = snapshot["score"]
    components = snapshot["components"]
    modules = snapshot["modules"]
    drivers = sorted(components, key=lambda item: abs(item["contribution"]), reverse=True)[:4]
    constraint = min(components, key=lambda item: item["contribution"]) if components else {}
    offset = max(components, key=lambda item: item["contribution"]) if components else {}
    drag_components = [item for item in components if item["contribution"] < -0.01]
    buffer_components = [item for item in components if item["contribution"] > 0.01]
    neutral_components = [item for item in components if -0.01 <= item["contribution"] <= 0.01]
    focus_components = sorted(components, key=lambda item: abs(item["contribution"]), reverse=True)[:5]
    balance = [
        {
            "label": "拖累",
            "count": len(drag_components),
            "contribution": round(sum(item["contribution"] for item in drag_components), 2),
            "direction": "restrictive",
        },
        {
            "label": "中性",
            "count": len(neutral_components),
            "contribution": round(sum(item["contribution"] for item in neutral_components), 2),
            "direction": "neutral",
        },
        {
            "label": "缓冲",
            "count": len(buffer_components),
            "contribution": round(sum(item["contribution"] for item in buffer_components), 2),
            "direction": "supportive",
        },
    ]
    trend = build_macro_liquidity_trend(ind, score)
    return {
        "score": score,
        "regime": macro_liquidity_regime(score),
        "bias": "supportive" if score >= 55 else "restrictive" if score <= 45 else "neutral",
        "method": "Bhadial Conditions Score-compatible 30-factor, 7-module 5Y historical percentile composite; module weights follow the public factor-coverage/overlap method; Funding uses EMA(5).",
        "sourceUrl": BHADIAL_SCORE_SOURCE_URL,
        "moduleCount": len(BHADIAL_CONDITION_MODULES),
        "totalFactorCount": sum(int(module["scored"]) + int(module["display"]) for module in BHADIAL_FACTOR_COVERAGE),
        "scoredFactorCount": sum(len(module["factors"]) for module in BHADIAL_CONDITION_MODULES),
        "observedFactorCount": snapshot["observedFactorCount"],
        "proxyFactorCount": 5,
        "modules": modules,
        "summary": macro_liquidity_summary(score, constraint, offset, trend),
        "trend": trend,
        "constraint": constraint,
        "offset": offset,
        "balance": balance,
        "focusComponents": focus_components,
        "hiddenComponentCount": max(0, len(components) - len(focus_components)),
        "implications": macro_liquidity_implications(score, constraint, offset),
        "components": components,
        "drivers": drivers,
    }


def bhadial_conditions_snapshot(ind: dict[str, Any]) -> dict[str, Any]:
    series = ind.get("percentile_series", {})
    target = latest_bhadial_score_date(series)
    score_row = bhadial_conditions_score_at(series, target, include_components=True) if target else None
    if score_row is None:
        score_row = neutral_bhadial_conditions_row(include_components=True)
    components: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = []
    raw_components_by_id = {
        component["id"]: component
        for module in score_row.get("modules", [])
        for component in module.get("factors", [])
    }
    for module in score_row.get("modules", []):
        module_weight = bhadial_module_weight(str(module["name"]))
        modules.append(
            {
                "name": module["name"],
                "nameCn": module["nameCn"],
                "score": round(module["score"], 1),
                "rawScore": round(module["rawScore"], 1),
                "ema5Score": round(module["ema5Score"], 1) if module.get("ema5Score") is not None else None,
                "weight": round(module_weight, 3),
                "observedFactorCount": module["observedFactorCount"],
                "factorCount": module["factorCount"],
                "method": module.get("method", "weighted factors"),
            }
        )
    for module in BHADIAL_CONDITION_MODULES:
        module_weight = bhadial_module_weight(str(module["name"]))
        for spec in module["factors"]:
            raw = raw_components_by_id.get(str(spec["id"]), {})
            score = float(raw.get("score", 50.0))
            factor_weight = float(spec["weight"])
            effective_weight = module_weight * factor_weight
            components.append(
                {
                    "id": spec["id"],
                    "module": module["name"],
                    "moduleCn": module["nameCn"],
                    "remoteName": spec["remoteName"],
                    "name": spec["name"],
                    "score": round(score, 1),
                    "percentile": raw.get("percentile"),
                    "weight": round(factor_weight, 2),
                    "effectiveWeight": round(effective_weight, 4),
                    "contribution": round((score - 50) * effective_weight, 2),
                    "value": format_bhadial_factor_value(ind.get(str(spec["valueKey"])), str(spec["format"])),
                    "source": spec["source"],
                    "direction": "supportive" if score >= 55 else "restrictive" if score <= 45 else "neutral",
                    "scoring": spec["method"],
                    "note": bhadial_factor_note(spec),
                }
            )
    return {
        "score": round(float(score_row["score"]), 1),
        "observedFactorCount": int(score_row.get("observedFactorCount", 0)),
        "components": components,
        "modules": modules,
    }


def latest_bhadial_score_date(series: dict[str, list[SeriesPoint]]) -> date | None:
    latest: date | None = None
    for key in BHADIAL_CONDITION_SERIES_KEYS:
        points = clean_points(series.get(key, []))
        if points and (latest is None or points[-1].date > latest):
            latest = points[-1].date
    return latest


def neutral_bhadial_conditions_row(*, include_components: bool = False) -> dict[str, Any]:
    modules = []
    for module in BHADIAL_CONDITION_MODULES:
        module_row = {
            "name": module["name"],
            "nameCn": module["nameCn"],
            "score": 50.0,
            "rawScore": 50.0,
            "ema5Score": None,
            "observedFactorCount": 0,
            "factorCount": len(module["factors"]),
            "method": "weighted factors",
            "weight": bhadial_module_weight(str(module["name"])),
        }
        if include_components:
            module_row["factors"] = [
                {"id": spec["id"], "score": 50.0, "percentile": None, "observed": False}
                for spec in module["factors"]
            ]
        modules.append(module_row)
    return {"score": 50.0, "observedFactorCount": 0, "modules": modules}


def bhadial_module_weight(name: str) -> float:
    return BHADIAL_MODULE_WEIGHTS.get(name, 1 / max(1, len(BHADIAL_CONDITION_MODULES)))


def bhadial_conditions_score_at(series: dict[str, list[SeriesPoint]], target: date | None, *, include_components: bool = False) -> dict[str, Any] | None:
    if target is None:
        return None
    modules: list[dict[str, Any]] = []
    composite_total = 0.0
    weight_total = 0.0
    observed_total = 0
    for module in BHADIAL_CONDITION_MODULES:
        raw_module = bhadial_raw_module_score_at(series, module, target, include_components=include_components)
        if raw_module is None:
            return None
        module_score = raw_module["rawScore"]
        ema5_score = None
        method = "weighted factors"
        if module.get("smooth") == "ema5":
            ema5_score = bhadial_module_ema_score_at(series, module, target, span=5)
            if ema5_score is not None:
                module_score = ema5_score
            method = "weighted factors + EMA(5)"
        observed_total += int(raw_module["observedFactorCount"])
        module_row = {
            "name": module["name"],
            "nameCn": module["nameCn"],
            "score": module_score,
            "rawScore": raw_module["rawScore"],
            "ema5Score": ema5_score,
            "weight": bhadial_module_weight(str(module["name"])),
            "observedFactorCount": raw_module["observedFactorCount"],
            "factorCount": raw_module["factorCount"],
            "method": method,
        }
        if include_components:
            module_row["factors"] = raw_module["factors"]
        modules.append(module_row)
        module_weight = bhadial_module_weight(str(module["name"]))
        composite_total += module_score * module_weight
        weight_total += module_weight
    if not modules:
        return None
    return {
        "score": composite_total / max(weight_total, 1e-9),
        "observedFactorCount": observed_total,
        "modules": modules,
    }


def bhadial_raw_module_score_at(
    series: dict[str, list[SeriesPoint]],
    module: dict[str, Any],
    target: date,
    *,
    include_components: bool = False,
) -> dict[str, Any] | None:
    total = 0.0
    total_weight = 0.0
    observed = 0
    factors: list[dict[str, Any]] = []
    for spec in module["factors"]:
        factor_score = bhadial_factor_score_at(series, spec, target)
        score = factor_score["score"]
        weight = float(spec["weight"])
        total += score * weight
        total_weight += weight
        if factor_score["observed"]:
            observed += 1
        if include_components:
            factors.append(
                {
                    "id": spec["id"],
                    "score": score,
                    "percentile": factor_score["percentile"],
                    "observed": factor_score["observed"],
                }
            )
    if total_weight <= 0:
        return None
    row: dict[str, Any] = {
        "rawScore": total / total_weight,
        "observedFactorCount": observed,
        "factorCount": len(module["factors"]),
    }
    if include_components:
        row["factors"] = factors
    return row


def bhadial_factor_score_at(series: dict[str, list[SeriesPoint]], spec: dict[str, Any], target: date) -> dict[str, Any]:
    points = clean_points(series.get(str(spec["scoreKey"]), []))
    current = point_at_or_before(points, target)
    percentile = historical_percentile_at(points, target) if points else None
    observed = current is not None
    if current is None:
        return {"score": 50.0, "percentile": percentile, "observed": False}
    method = str(spec["method"])
    direction = str(spec["direction"])
    if method == "risk_signal":
        bounded = max(0.0, min(1.0, current.value))
        score = (1 - bounded) * 100 if direction == "lower_better" else bounded * 100
    elif method == "shock_only" and current.value <= 0:
        score = 50.0
    else:
        score = score_from_percentile(percentile, direction)
    return {"score": max(0.0, min(100.0, score)), "percentile": percentile, "observed": observed}


def score_from_percentile(percentile: int | None, direction: str) -> float:
    if percentile is None:
        return 50.0
    if direction == "lower_better":
        return float(100 - percentile)
    return float(percentile)


def bhadial_module_ema_score_at(series: dict[str, list[SeriesPoint]], module: dict[str, Any], target: date, *, span: int) -> float | None:
    keys = [str(spec["scoreKey"]) for spec in module["factors"]]
    month_ends = monthly_score_dates(series, keys, target)
    if target not in month_ends:
        month_ends.append(target)
    alpha = 2 / (span + 1)
    ema: float | None = None
    for point_date in sorted(month_ends):
        raw = bhadial_raw_module_score_at(series, module, point_date)
        if raw is None:
            continue
        score = float(raw["rawScore"])
        ema = score if ema is None else alpha * score + (1 - alpha) * ema
    return ema


def monthly_score_dates(series: dict[str, list[SeriesPoint]], keys: list[str], target: date, *, years: int = 5) -> list[date]:
    start = window_start(target, years=years)
    month_ends: dict[tuple[int, int], date] = {}
    for key in keys:
        for point in clean_points(series.get(key, [])):
            if start <= point.date <= target:
                month_ends[(point.date.year, point.date.month)] = max(month_ends.get((point.date.year, point.date.month), point.date), point.date)
    return [month_ends[key] for key in sorted(month_ends)]


def format_bhadial_factor_value(value: Any, fmt: str) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return "--"
    number = float(value)
    if fmt == "usd_t":
        return f"${number:.2f}T"
    if fmt == "signed_usd_t":
        return f"{number:+.2f}T"
    if fmt == "signed_bp":
        return f"{number:+.0f}bp"
    if fmt == "bp":
        return f"{number:.0f}bp"
    if fmt == "vol_bp":
        return f"{number:.1f}bp ann."
    if fmt == "percent":
        return f"{number:.2f}%"
    if fmt == "vol_pct":
        return f"{number:.1f}%"
    if fmt == "risk":
        return f"{number:.2f}"
    if fmt == "price_usd":
        return f"${number:.2f}"
    if fmt == "signed_number":
        return f"{number:+.2f}"
    return f"{number:.2f}"


def bhadial_factor_note(spec: dict[str, Any]) -> str:
    method = str(spec["method"]).replace("_", "-")
    direction = "higher is more supportive" if spec["direction"] == "higher_better" else "lower is more supportive"
    if spec["method"] == "target_distance":
        return f"{spec['remoteName']} uses target-distance scoring around {spec.get('target', BHADIAL_BREAKEVEN_TARGET):.1f}%; {direction} after distance is converted to a 5Y percentile."
    if spec["method"] == "shock_only":
        return f"{spec['remoteName']} uses shock-only scoring; positive stress is penalized, while no-shock readings stay neutral rather than automatically supportive."
    if spec["method"] == "risk_signal":
        return f"{spec['remoteName']} maps a bounded 0-1 risk signal to 0-100 supportiveness; {direction}."
    return f"{spec['remoteName']} uses {method} scoring over a 5Y history; {direction}."


def build_macro_liquidity_trend(ind: dict[str, Any], current_score: float) -> dict[str, Any]:
    points = macro_liquidity_history_points(ind.get("percentile_series", {}))
    if not points:
        return {
            "available": False,
            "historicalPercentile": None,
            "score1mChange": None,
            "score3mChange": None,
            "percentile1mChange": None,
            "percentile3mChange": None,
            "direction": "不足",
            "summary": "综合评分历史样本不足",
            "points": [],
        }
    latest = points[-1]
    prior_1m = points[-2] if len(points) >= 2 else None
    prior_3m = points[-4] if len(points) >= 4 else None
    score_1m_change = round(latest["score"] - prior_1m["score"], 1) if prior_1m else None
    score_3m_change = round(latest["score"] - prior_3m["score"], 1) if prior_3m else None
    percentile_1m_change = latest["percentile"] - prior_1m["percentile"] if prior_1m and latest.get("percentile") is not None and prior_1m.get("percentile") is not None else None
    percentile_3m_change = latest["percentile"] - prior_3m["percentile"] if prior_3m and latest.get("percentile") is not None and prior_3m.get("percentile") is not None else None
    direction = macro_liquidity_trend_direction(score_3m_change if score_3m_change is not None else score_1m_change)
    latest_percentile = latest.get("percentile")
    return {
        "available": True,
        "date": latest["date"],
        "score": round(current_score, 1),
        "historicalPercentile": latest_percentile,
        "score1mChange": score_1m_change,
        "score3mChange": score_3m_change,
        "percentile1mChange": percentile_1m_change,
        "percentile3mChange": percentile_3m_change,
        "direction": direction,
        "summary": macro_liquidity_trend_summary(latest_percentile, score_3m_change, percentile_3m_change, direction),
        "points": points,
    }


def macro_liquidity_history_points(series: dict[str, list[SeriesPoint]]) -> list[dict[str, Any]]:
    dated_component_points: list[SeriesPoint] = []
    for key in BHADIAL_CONDITION_SERIES_KEYS:
        dated_component_points.extend(clean_points(series.get(key, [])))
    if not dated_component_points:
        return []
    latest_date = max(point.date for point in dated_component_points)
    start = window_start(latest_date, years=5)
    month_ends: dict[tuple[int, int], date] = {}
    for point in sorted(dated_component_points, key=lambda item: item.date):
        if point.date < start:
            continue
        month_ends[(point.date.year, point.date.month)] = point.date
    raw_points: list[dict[str, Any]] = []
    for target in sorted(set(month_ends.values())):
        score_row = macro_liquidity_score_at(series, target)
        if score_row is None:
            continue
        raw_points.append(
            {
                "date": target.isoformat(),
                "score": round(score_row["score"], 1),
                "componentCoverage": score_row["coverage"],
            }
        )
    for index, point in enumerate(raw_points):
        point_date = date.fromisoformat(point["date"])
        start_date = window_start(point_date, years=5)
        values = [
            item["score"]
            for item in raw_points[: index + 1]
            if start_date <= date.fromisoformat(item["date"]) <= point_date
        ]
        point["percentile"] = historical_percentile(float(point["score"]), [float(value) for value in values])
    return raw_points


def macro_liquidity_trend_direction(score_change: float | None) -> str:
    if score_change is None:
        return "不足"
    if score_change >= 3:
        return "上行"
    if score_change <= -3:
        return "下行"
    return "震荡"


def macro_liquidity_trend_summary(
    percentile: int | None,
    score_3m_change: float | None,
    percentile_3m_change: int | None,
    direction: str,
) -> str:
    percentile_text = f"p{percentile}" if percentile is not None else "p--"
    score_change_text = format_signed_number(score_3m_change, digits=1)
    percentile_change_text = format_signed_number(float(percentile_3m_change), digits=0) if percentile_3m_change is not None else "--"
    if direction == "上行":
        return f"历史分位{percentile_text},3M综合分{score_change_text},分位{percentile_change_text}pct; 低位改善正在形成边际支撑。"
    if direction == "下行":
        return f"历史分位{percentile_text},3M综合分{score_change_text},分位{percentile_change_text}pct; 趋势转弱会放大低分位约束。"
    if direction == "震荡":
        return f"历史分位{percentile_text},3M综合分{score_change_text},分位{percentile_change_text}pct; 当前位置优先按区间震荡处理。"
    return f"历史分位{percentile_text},历史趋势样本不足; 暂以当前分项拖累和缓冲为主。"


def build_macro_liquidity_equity_lead(ind: dict[str, Any]) -> dict[str, Any]:
    series = ind.get("percentile_series", {})
    sp500_points = clean_points(series.get("sp500", []))
    if len(sp500_points) < 24:
        return unavailable_macro_liquidity_equity("S&P 500 history is unavailable or too short.")
    latest_spx = sp500_points[-1]
    start = window_start(latest_spx.date, years=5)
    monthly_spx = monthly_last_points(sp500_points, start=start)
    rows: list[dict[str, Any]] = []
    base_spx: float | None = None
    for spx_point in monthly_spx:
        score_row = macro_liquidity_score_at(series, spx_point.date)
        if score_row is None:
            continue
        if base_spx is None:
            base_spx = spx_point.value
        forward_1m = forward_return_pct(sp500_points, spx_point.date, days=30)
        forward_3m = forward_return_pct(sp500_points, spx_point.date, days=91)
        forward_6m = forward_return_pct(sp500_points, spx_point.date, days=182)
        forward_3m_drawdown = forward_max_drawdown_pct(sp500_points, spx_point.date, days=91)
        rows.append(
            {
                "date": spx_point.date.isoformat(),
                "liquidityScore": round(score_row["score"], 1),
                "componentCoverage": score_row["coverage"],
                "sp500": round(spx_point.value, 2),
                "sp500Indexed": round((spx_point.value / base_spx) * 100, 1) if base_spx else 100.0,
                "forward1m": round(forward_1m, 2) if forward_1m is not None else None,
                "forward3m": round(forward_3m, 2) if forward_3m is not None else None,
                "forward6m": round(forward_6m, 2) if forward_6m is not None else None,
                "forward3mMaxDrawdown": round(forward_3m_drawdown, 2) if forward_3m_drawdown is not None else None,
            }
        )
    if len(rows) < 18:
        return unavailable_macro_liquidity_equity("Conditions score history has fewer than 18 monthly observations.")
    add_macro_liquidity_equity_deltas(rows)
    corr_1m = row_correlation(rows, "liquidityScore", "forward1m")
    corr_3m = row_correlation(rows, "liquidityScore", "forward3m")
    corr_6m = row_correlation(rows, "liquidityScore", "forward6m")
    buckets = liquidity_forward_return_buckets(rows)
    lead_lag = macro_liquidity_lead_lag(rows)
    change_buckets = score_change_forward_return_buckets(rows)
    rolling_correlation = rolling_forward_correlation(rows)
    drawdown_risk = liquidity_drawdown_risk(rows)
    current_signal = macro_liquidity_current_signal(rows, buckets, change_buckets, lead_lag)
    state_grid = macro_liquidity_state_grid(rows, current_signal)
    high_low = None
    if len(buckets) >= 3 and buckets[0].get("avgForward3m") is not None and buckets[-1].get("avgForward3m") is not None:
        high_low = round(float(buckets[-1]["avgForward3m"]) - float(buckets[0]["avgForward3m"]), 2)
    conclusion = macro_liquidity_equity_conclusion(corr_3m, high_low, buckets)
    stats = [
        {"label": "1M forward corr", "value": format_correlation(corr_1m), "tone": correlation_tone(corr_1m)},
        {"label": "3M forward corr", "value": format_correlation(corr_3m), "tone": correlation_tone(corr_3m)},
        {"label": "6M forward corr", "value": format_correlation(corr_6m), "tone": correlation_tone(corr_6m)},
        {"label": "High-Low 3M", "value": f"{high_low:+.2f}pp" if high_low is not None else "--", "tone": "supportive" if high_low and high_low > 0 else "restrictive" if high_low and high_low < 0 else "neutral"},
    ]
    return {
        "available": True,
        "title": "宏观环境评分 vs S&P 500 · 5Y Lead Study",
        "method": "Monthly 5Y sample; macro conditions replay the same Bhadial-compatible 30-factor, 7-module composite and compare it with FRED S&P 500 price-index forward returns.",
        "asOf": latest_spx.date.isoformat(),
        "observationCount": len(rows),
        "correlations": {
            "forward1m": round(corr_1m, 3) if corr_1m is not None else None,
            "forward3m": round(corr_3m, 3) if corr_3m is not None else None,
            "forward6m": round(corr_6m, 3) if corr_6m is not None else None,
        },
        "stats": stats,
        "buckets": buckets,
        "leadLag": lead_lag,
        "changeBuckets": change_buckets,
        "rollingCorrelation": rolling_correlation,
        "drawdownRisk": drawdown_risk,
        "currentSignal": current_signal,
        "stateGrid": state_grid,
        "conclusion": conclusion,
        "series": rows,
    }


def unavailable_macro_liquidity_equity(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "title": "宏观环境评分 vs S&P 500 · 5Y Lead Study",
        "method": "Monthly 5Y sample; requires S&P 500 and Bhadial-compatible conditions-score component history.",
        "asOf": "",
        "observationCount": 0,
        "correlations": {"forward1m": None, "forward3m": None, "forward6m": None},
        "stats": [],
        "buckets": [],
        "leadLag": [],
        "changeBuckets": [],
        "rollingCorrelation": {"windowMonths": 24, "latest": None, "points": []},
        "drawdownRisk": {"maxDrawdown": None, "worstDate": "", "avgDrawdownByBucket": []},
        "currentSignal": {
            "available": False,
            "levelBucket": "",
            "changeBucket": "",
            "verdict": reason,
            "expectedForward3m": None,
            "expectedDrawdown3m": None,
            "confidence": "low",
            "cards": [],
        },
        "stateGrid": [],
        "conclusion": reason,
        "series": [],
    }


SPY_WARNING_COMPONENT_SLEEVES: list[dict[str, Any]] = [
    {
        "key": "liquidityStress",
        "label": "流动性压力",
        "weight": 0.10,
        "componentIds": ["fed_net_liquidity", "bank_reserves", "delta_net_liq_13w", "tga_dev_signed", "onrrp_near_zero_risk"],
    },
    {
        "key": "fundingStress",
        "label": "融资压力",
        "weight": 0.10,
        "componentIds": ["collateral_friction", "corridor_friction_1", "corridor_friction_2", "effr_iorb", "cp_tbill_spread", "fragmentation_21d"],
    },
    {
        "key": "ratesCurveStress",
        "label": "利率/曲线压力",
        "weight": 0.20,
        "componentIds": ["dgs30_dgs10", "dgs10_vol_21d", "curve_curvature_abs", "real_rate_level", "real_curve", "t10yie"],
    },
    {
        "key": "creditVolStress",
        "label": "信用/波动压力",
        "weight": 0.25,
        "componentIds": ["nfci", "hy_credit", "ig_credit", "kre_spy", "vix", "vix_term_structure", "risk_vs_safe", "high_beta_pref"],
    },
    {
        "key": "externalShock",
        "label": "外部冲击",
        "weight": 0.10,
        "componentIds": ["dxy", "fx_vol", "wti", "ovx_dev", "natgas"],
    },
]

SPY_WARNING_NONLINEAR_SCALE = 1.08
SPY_WARNING_POST_SELLOFF_DAMPENER = -10.0
SPY_WARNING_LATE_RALLY_ROLLOVER_BOOST = 3.0
SPY_WARNING_LOW_SCORE_STALL_BOOST = 4.0


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
        build_macro_deterioration_sleeve(current_signal, weight=0.20),
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
        "method": "Equity-specific 0-100 warning index from existing macro Conditions Score components plus 3M score deterioration and calibrated nonlinear risk amplifiers; higher means greater SPY/SPX drawdown risk.",
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
        "summary": "SPY Early Warning月度回放,使用同一组宏观分项与3M评分变化生成0-100预警分数。",
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
    change_rows = [item for item in rows if optional_float(item.get("score3mChange")) is not None]
    return {
        "date": str(row.get("date") or ""),
        "conditionsScore": conditions_score,
        "score3mChange": score_change,
        "levelBucket": bucket_label_by_rank(rows, "liquidityScore", conditions_score, ["低评分", "中位评分", "高评分"]),
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
    if conditions_score is not None and conditions_score <= 42 and (score_change is None or score_change <= 1):
        amplifiers.append(
            {
                "key": "fragileLowScore",
                "label": "低分脆弱区",
                "scoreBoost": 8.0,
                "detail": f"Conditions Score {conditions_score:.1f},缺少明显改善",
            }
        )
    if (
        conditions_score is not None
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
    if trailing_3m is not None and trailing_3m >= 5 and score_change is not None and score_change <= -2:
        amplifiers.append(
            {
                "key": "rallyFragility",
                "label": "上涨后宏观转弱",
                "scoreBoost": 6.0,
                "detail": f"SPX 3M {format_signed_number(trailing_3m, digits=1)}%,评分变化 {format_signed_number(score_change, digits=1)}",
            }
        )
    if (
        trailing_3m is not None
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


def spy_warning_allocation(score: float) -> dict[str, str]:
    if score >= 75:
        return {
            "regime": "De-risk",
            "regimeCn": "减仓预警",
            "stance": "减仓/保护",
            "equityExposure": "权益降至常规仓位的25-50%",
            "hedgeAction": "优先保护性对冲或降低高Beta暴露",
            "tone": "restrictive",
        }
    if score >= 60:
        return {
            "regime": "Caution",
            "regimeCn": "谨慎",
            "stance": "降权/对冲",
            "equityExposure": "权益维持常规仓位的50-75%",
            "hedgeAction": "新增仓位放慢,回撤保护优先",
            "tone": "restrictive",
        }
    if score >= 40:
        return {
            "regime": "Neutral",
            "regimeCn": "中性",
            "stance": "持有/控仓",
            "equityExposure": "维持核心仓位,避免追高",
            "hedgeAction": "等待信用/波动或评分转弱确认",
            "tone": "neutral",
        }
    return {
        "regime": "Constructive",
        "regimeCn": "建设性",
        "stance": "正常/逢低加",
        "equityExposure": "维持常规或略高权益仓位",
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


def bounded_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def clean_points(points: list[SeriesPoint]) -> list[SeriesPoint]:
    return sorted((point for point in points if math.isfinite(point.value)), key=lambda item: item.date)


def monthly_last_points(points: list[SeriesPoint], *, start: date) -> list[SeriesPoint]:
    by_month: dict[tuple[int, int], SeriesPoint] = {}
    for point in clean_points(points):
        if point.date < start:
            continue
        by_month[(point.date.year, point.date.month)] = point
    return [by_month[key] for key in sorted(by_month)]


def macro_liquidity_score_at(series: dict[str, list[SeriesPoint]], target: date) -> dict[str, Any] | None:
    row = bhadial_conditions_score_at(series, target)
    if row is None or row.get("observedFactorCount", 0) < 5:
        return None
    return {"score": row["score"], "coverage": row["observedFactorCount"]}


def historical_percentile_at(points: list[SeriesPoint], target: date, *, years: int = 5) -> int | None:
    ordered = clean_points(points)
    current = point_at_or_before(ordered, target)
    if current is None:
        return None
    start = window_start(target, years=years)
    values = [point.value for point in ordered if start <= point.date <= current.date]
    return historical_percentile(current.value, values)


def point_at_or_before(points: list[SeriesPoint], target: date) -> SeriesPoint | None:
    for point in reversed(points):
        if point.date <= target:
            return point
    return None


def point_at_or_after(points: list[SeriesPoint], target: date, *, tolerance_days: int = 10) -> SeriesPoint | None:
    limit = target + timedelta(days=tolerance_days)
    for point in points:
        if target <= point.date <= limit:
            return point
        if point.date > limit:
            break
    return None


def forward_return_pct(points: list[SeriesPoint], start: date, *, days: int) -> float | None:
    ordered = clean_points(points)
    current = point_at_or_before(ordered, start)
    future = point_at_or_after(ordered, start + timedelta(days=days))
    if current is None or future is None or current.value == 0:
        return None
    return (future.value / current.value - 1) * 100


def forward_max_drawdown_pct(points: list[SeriesPoint], start: date, *, days: int) -> float | None:
    ordered = clean_points(points)
    current = point_at_or_before(ordered, start)
    if current is None or current.value == 0:
        return None
    end = start + timedelta(days=days)
    future_values = [point.value for point in ordered if current.date < point.date <= end]
    if not future_values:
        return None
    return min(0.0, (min(future_values) / current.value - 1) * 100)


def add_macro_liquidity_equity_deltas(rows: list[dict[str, Any]]) -> None:
    for index, row in enumerate(rows):
        if index >= 3:
            prior = rows[index - 3]
            row["score3mChange"] = round(float(row["liquidityScore"]) - float(prior["liquidityScore"]), 1)
            current_spx = float(row["sp500"])
            prior_spx = float(prior["sp500"])
            row["sp500Trailing3m"] = round((current_spx / prior_spx - 1) * 100, 2) if prior_spx else None
        else:
            row["score3mChange"] = None
            row["sp500Trailing3m"] = None


def row_correlation(rows: list[dict[str, Any]], left_key: str, right_key: str) -> float | None:
    pairs = [
        (float(row[left_key]), float(row[right_key]))
        for row in rows
        if row.get(left_key) is not None and row.get(right_key) is not None
    ]
    if len(pairs) < 6:
        return None
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    if x_var <= 0 or y_var <= 0:
        return None
    return numerator / math.sqrt(x_var * y_var)


def macro_liquidity_lead_lag(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = [("评分水平", "liquidityScore"), ("3M评分变化", "score3mChange")]
    horizons = [("forward1m", "1M"), ("forward3m", "3M"), ("forward6m", "6M")]
    matrix: list[dict[str, Any]] = []
    for label, signal_key in specs:
        row: dict[str, Any] = {"signal": label}
        for forward_key, horizon_label in horizons:
            corr = row_correlation(rows, signal_key, forward_key)
            row[forward_key] = round(corr, 3) if corr is not None else None
            row[f"{forward_key}Label"] = horizon_label
        matrix.append(row)
    return matrix


def liquidity_forward_return_buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample = [row for row in rows if row.get("forward3m") is not None]
    if len(sample) < 9:
        return []
    ordered = sorted(sample, key=lambda item: float(item["liquidityScore"]))
    labels = ["低评分", "中位评分", "高评分"]
    buckets: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        start = round(index * len(ordered) / 3)
        end = round((index + 1) * len(ordered) / 3)
        bucket = ordered[start:end]
        returns = [float(item["forward3m"]) for item in bucket if item.get("forward3m") is not None]
        scores = [float(item["liquidityScore"]) for item in bucket]
        buckets.append(
            {
                "label": label,
                "count": len(bucket),
                "scoreRange": f"{min(scores):.0f}-{max(scores):.0f}" if scores else "--",
                "avgForward3m": round(sum(returns) / len(returns), 2) if returns else None,
                "medianForward3m": round(median(returns), 2) if returns else None,
                "hitRate": round((sum(1 for value in returns if value > 0) / len(returns)) * 100) if returns else None,
            }
        )
    return buckets


def score_change_forward_return_buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample = [row for row in rows if row.get("score3mChange") is not None and row.get("forward3m") is not None]
    if len(sample) < 9:
        return []
    ordered = sorted(sample, key=lambda item: float(item["score3mChange"]))
    labels = ["评分下行", "变化不大", "评分上行"]
    buckets: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        start = round(index * len(ordered) / 3)
        end = round((index + 1) * len(ordered) / 3)
        bucket = ordered[start:end]
        changes = [float(item["score3mChange"]) for item in bucket]
        returns = [float(item["forward3m"]) for item in bucket if item.get("forward3m") is not None]
        drawdowns = [float(item["forward3mMaxDrawdown"]) for item in bucket if item.get("forward3mMaxDrawdown") is not None]
        buckets.append(
            {
                "label": label,
                "count": len(bucket),
                "changeRange": f"{min(changes):+.1f} to {max(changes):+.1f}" if changes else "--",
                "avgForward3m": round(sum(returns) / len(returns), 2) if returns else None,
                "hitRate": round((sum(1 for value in returns if value > 0) / len(returns)) * 100) if returns else None,
                "avgMaxDrawdown3m": round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else None,
            }
        )
    return buckets


def rolling_forward_correlation(rows: list[dict[str, Any]], *, window_months: int = 24) -> dict[str, Any]:
    usable = [row for row in rows if row.get("forward3m") is not None]
    points: list[dict[str, Any]] = []
    for index in range(window_months - 1, len(usable)):
        sample = usable[index - window_months + 1 : index + 1]
        corr = row_correlation(sample, "liquidityScore", "forward3m")
        if corr is None:
            continue
        points.append({"date": usable[index]["date"], "correlation": round(corr, 3)})
    latest = points[-1]["correlation"] if points else None
    values = [float(point["correlation"]) for point in points]
    return {
        "windowMonths": window_months,
        "latest": latest,
        "points": points,
        "range": {"min": round(min(values), 3), "max": round(max(values), 3)} if values else {"min": None, "max": None},
    }


def liquidity_drawdown_risk(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sample = [row for row in rows if row.get("forward3mMaxDrawdown") is not None]
    if not sample:
        return {"maxDrawdown": None, "worstDate": "", "avgDrawdownByBucket": []}
    worst = min(sample, key=lambda item: float(item["forward3mMaxDrawdown"]))
    level_buckets = liquidity_forward_return_buckets(rows)
    drawdown_buckets: list[dict[str, Any]] = []
    if len(level_buckets) == 3:
        ordered = sorted([row for row in sample if row.get("forward3m") is not None], key=lambda item: float(item["liquidityScore"]))
        for index, label in enumerate(["低评分", "中位评分", "高评分"]):
            start = round(index * len(ordered) / 3)
            end = round((index + 1) * len(ordered) / 3)
            bucket = ordered[start:end]
            drawdowns = [float(item["forward3mMaxDrawdown"]) for item in bucket if item.get("forward3mMaxDrawdown") is not None]
            drawdown_buckets.append(
                {
                    "label": label,
                    "avgMaxDrawdown3m": round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else None,
                    "worstMaxDrawdown3m": round(min(drawdowns), 2) if drawdowns else None,
                }
            )
    return {
        "maxDrawdown": round(float(worst["forward3mMaxDrawdown"]), 2),
        "worstDate": str(worst["date"]),
        "avgDrawdownByBucket": drawdown_buckets,
    }


def macro_liquidity_current_signal(
    rows: list[dict[str, Any]],
    level_buckets: list[dict[str, Any]],
    change_buckets: list[dict[str, Any]],
    lead_lag: list[dict[str, Any]],
) -> dict[str, Any]:
    latest = rows[-1] if rows else {}
    latest_score = optional_float(latest.get("liquidityScore"))
    latest_change = optional_float(latest.get("score3mChange"))
    level_label = bucket_label_by_rank(rows, "liquidityScore", latest_score, ["低评分", "中位评分", "高评分"])
    change_label = bucket_label_by_rank(
        [row for row in rows if row.get("score3mChange") is not None],
        "score3mChange",
        latest_change,
        ["评分下行", "变化不大", "评分上行"],
    )
    level_bucket = find_bucket(level_buckets, level_label)
    change_bucket = find_bucket(change_buckets, change_label)
    expected_forward = optional_float(change_bucket.get("avgForward3m")) if change_bucket else None
    if expected_forward is None and level_bucket:
        expected_forward = optional_float(level_bucket.get("avgForward3m"))
    expected_drawdown = optional_float(change_bucket.get("avgMaxDrawdown3m")) if change_bucket else None
    hit_rate = optional_float(change_bucket.get("hitRate")) if change_bucket else None
    change_corr_3m = None
    for row in lead_lag:
        if row.get("signal") == "3M评分变化":
            change_corr_3m = optional_float(row.get("forward3m"))
            break
    confidence = signal_confidence(change_corr_3m, len(rows))
    verdict = current_signal_verdict(level_label, change_label, expected_forward, expected_drawdown, change_corr_3m)
    return {
        "available": True,
        "date": latest.get("date", ""),
        "score": latest_score,
        "score3mChange": latest_change,
        "levelBucket": level_label,
        "changeBucket": change_label,
        "expectedForward3m": round(expected_forward, 2) if expected_forward is not None else None,
        "expectedDrawdown3m": round(expected_drawdown, 2) if expected_drawdown is not None else None,
        "hitRate": round(hit_rate) if hit_rate is not None else None,
        "confidence": confidence["key"],
        "confidenceLabel": confidence["label"],
        "verdict": verdict,
        "cards": [
            {
                "label": "当前评分",
                "value": f"{latest_score:.1f}" if latest_score is not None else "--",
                "detail": f"{level_label} · {latest.get('date', '--')}",
                "tone": score_tone(latest_score),
            },
            {
                "label": "3M评分变化",
                "value": format_signed_number(latest_change, digits=1),
                "detail": change_label,
                "tone": "supportive" if latest_change is not None and latest_change > 0 else "restrictive" if latest_change is not None and latest_change < 0 else "neutral",
            },
            {
                "label": "相似样本3M",
                "value": f"{expected_forward:+.2f}%" if expected_forward is not None else "--",
                "detail": f"{round(hit_rate):.0f}% hit" if hit_rate is not None else "hit --",
                "tone": "supportive" if expected_forward is not None and expected_forward > 0 else "restrictive" if expected_forward is not None and expected_forward < 0 else "neutral",
            },
            {
                "label": "3M回撤风险",
                "value": f"{expected_drawdown:.2f}%" if expected_drawdown is not None else "--",
                "detail": "avg max drawdown",
                "tone": "restrictive" if expected_drawdown is not None and expected_drawdown < -5 else "neutral",
            },
            {
                "label": "信号置信度",
                "value": confidence["label"],
                "detail": f"3M变化corr {format_signed_number(change_corr_3m, digits=2)}",
                "tone": confidence["tone"],
            },
        ],
    }


def macro_liquidity_state_grid(rows: list[dict[str, Any]], current_signal: dict[str, Any]) -> list[dict[str, Any]]:
    labels_level = ["低评分", "中位评分", "高评分"]
    labels_change = ["评分下行", "变化不大", "评分上行"]
    change_rows = [row for row in rows if row.get("score3mChange") is not None]
    sample: list[dict[str, Any]] = []
    for row in rows:
        if row.get("forward3m") is None or row.get("score3mChange") is None:
            continue
        level_label = bucket_label_by_rank(rows, "liquidityScore", optional_float(row.get("liquidityScore")), labels_level)
        change_label = bucket_label_by_rank(change_rows, "score3mChange", optional_float(row.get("score3mChange")), labels_change)
        sample.append({**row, "levelBucket": level_label, "changeBucket": change_label})
    grid: list[dict[str, Any]] = []
    current_level = str(current_signal.get("levelBucket") or "")
    current_change = str(current_signal.get("changeBucket") or "")
    for level in labels_level:
        for change in labels_change:
            bucket = [row for row in sample if row["levelBucket"] == level and row["changeBucket"] == change]
            forwards = [float(row["forward3m"]) for row in bucket if row.get("forward3m") is not None]
            drawdowns = [float(row["forward3mMaxDrawdown"]) for row in bucket if row.get("forward3mMaxDrawdown") is not None]
            avg_forward = sum(forwards) / len(forwards) if forwards else None
            avg_drawdown = sum(drawdowns) / len(drawdowns) if drawdowns else None
            worst_drawdown = min(drawdowns) if drawdowns else None
            hit_rate = (sum(1 for value in forwards if value > 0) / len(forwards)) * 100 if forwards else None
            grid.append(
                {
                    "levelBucket": level,
                    "changeBucket": change,
                    "count": len(bucket),
                    "sampleShare": round((len(bucket) / len(sample)) * 100) if sample else 0,
                    "avgForward3m": round(avg_forward, 2) if avg_forward is not None else None,
                    "medianForward3m": round(median(forwards), 2) if forwards else None,
                    "hitRate": round(hit_rate) if hit_rate is not None else None,
                    "avgMaxDrawdown3m": round(avg_drawdown, 2) if avg_drawdown is not None else None,
                    "worstMaxDrawdown3m": round(worst_drawdown, 2) if worst_drawdown is not None else None,
                    "isCurrent": level == current_level and change == current_change,
                    "tone": "supportive" if avg_forward is not None and avg_forward > 0 else "restrictive" if avg_forward is not None and avg_forward < 0 else "neutral",
                }
            )
    return grid


def optional_float(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def bucket_label_by_rank(rows: list[dict[str, Any]], key: str, value: float | None, labels: list[str]) -> str:
    if value is None or not rows:
        return labels[1]
    values = [optional_float(row.get(key)) for row in rows]
    values = sorted(item for item in values if item is not None)
    if not values:
        return labels[1]
    rank = sum(1 for item in values if item <= value) / len(values)
    if rank <= 1 / 3:
        return labels[0]
    if rank <= 2 / 3:
        return labels[1]
    return labels[2]


def find_bucket(buckets: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for bucket in buckets:
        if bucket.get("label") == label:
            return bucket
    return {}


def signal_confidence(correlation: float | None, sample_size: int) -> dict[str, str]:
    if correlation is None or sample_size < 36 or abs(correlation) < 0.2:
        return {"key": "low", "label": "低", "tone": "neutral"}
    if abs(correlation) >= 0.45 and sample_size >= 48:
        return {"key": "high", "label": "高", "tone": "supportive"}
    return {"key": "medium", "label": "中", "tone": "supportive"}


def current_signal_verdict(
    level_label: str,
    change_label: str,
    expected_forward: float | None,
    expected_drawdown: float | None,
    change_corr_3m: float | None,
) -> str:
    forward_text = f"相似变化样本未来3个月平均{expected_forward:+.2f}%" if expected_forward is not None else "相似变化样本收益不足"
    drawdown_text = f"平均回撤{expected_drawdown:.2f}%" if expected_drawdown is not None else "回撤样本不足"
    corr_text = f"3M变化信号相关{change_corr_3m:+.2f}" if change_corr_3m is not None else "变化信号相关不足"
    if change_label == "评分上行":
        return f"当前属于{level_label},但边际流动性正在改善; {forward_text}, {drawdown_text}, {corr_text}。"
    if change_label == "评分下行":
        return f"当前属于{level_label},且边际流动性转弱; {forward_text}, {drawdown_text}, {corr_text}, 风险资产承接需要更保守。"
    return f"当前属于{level_label},边际变化不大; {forward_text}, {drawdown_text}, {corr_text}, 更适合作为环境过滤器。"


def score_tone(score: float | None) -> str:
    if score is None:
        return "neutral"
    if score >= 55:
        return "supportive"
    if score <= 45:
        return "restrictive"
    return "neutral"


def format_signed_number(value: float | None, *, digits: int = 2) -> str:
    if value is None:
        return "--"
    return f"{value:+.{digits}f}"


def macro_liquidity_equity_conclusion(corr_3m: float | None, high_low: float | None, buckets: list[dict[str, Any]]) -> str:
    if corr_3m is None or high_low is None:
        return "样本不足,暂不能判断宏观环境综合评分对S&P 500的前瞻性。"
    if corr_3m >= 0.25 and high_low > 0:
        return (
            f"过去5年样本显示,宏观环境综合评分与S&P 500未来3个月收益存在正向领先关系: "
            f"3M相关系数{corr_3m:+.2f},高评分桶相对低评分桶高{high_low:+.2f}个百分点。"
        )
    if corr_3m <= -0.25 and high_low < 0:
        return (
            f"过去5年样本显示,宏观环境高分后S&P 500未来3个月收益反而偏弱: "
            f"3M相关系数{corr_3m:+.2f},高低评分桶差{high_low:+.2f}个百分点。"
        )
    return (
        f"过去5年样本中,宏观环境综合评分对S&P 500未来3个月收益的前瞻性有限: "
        f"3M相关系数{corr_3m:+.2f},高低评分桶差{high_low:+.2f}个百分点; 更适合作为风险环境过滤器,不宜单独作为择时信号。"
    )


def format_correlation(value: float | None) -> str:
    return f"{value:+.2f}" if value is not None else "--"


def correlation_tone(value: float | None) -> str:
    if value is None or abs(value) < 0.15:
        return "neutral"
    return "supportive" if value > 0 else "restrictive"


def macro_liquidity_summary(score: float, constraint: dict[str, Any], offset: dict[str, Any], trend: dict[str, Any] | None = None) -> str:
    regime = macro_liquidity_regime(score)
    constraint_name = constraint.get("name", "关键拖累")
    constraint_value = constraint.get("value", "--")
    constraint_contribution = float(constraint.get("contribution") or 0)
    offset_name = offset.get("name", "关键缓冲")
    offset_value = offset.get("value", "--")
    offset_contribution = float(offset.get("contribution") or 0)
    return (
        f"{regime}: 最大拖累是{constraint_name}({constraint_value}, {constraint_contribution:+.1f}), "
        f"最大缓冲是{offset_name}({offset_value}, {offset_contribution:+.1f}); "
        f"{(trend or {}).get('summary') or '历史分位样本不足'}"
    )


def macro_liquidity_implications(score: float, constraint: dict[str, Any], offset: dict[str, Any]) -> list[dict[str, str]]:
    constraint_name = str(constraint.get("name") or "关键拖累")
    offset_name = str(offset.get("name") or "关键缓冲")
    if score <= 45:
        return [
            {"label": "久期", "tone": "restrictive", "text": f"{constraint_name}压制承接,长端抛售更容易放大。"},
            {"label": "风险资产", "tone": "restrictive", "text": "流动性低分位削弱估值缓冲,高贝塔资产更依赖盈利支撑。"},
            {"label": "融资压力", "tone": "watch", "text": f"{offset_name}提供局部缓冲,但不足以抵消现金抽水。"},
        ]
    if score >= 55:
        return [
            {"label": "久期", "tone": "supportive", "text": f"{offset_name}改善承接,久期回撤更容易被买盘吸收。"},
            {"label": "风险资产", "tone": "supportive", "text": "流动性分位偏高,风险资产估值缓冲较好。"},
            {"label": "融资压力", "tone": "neutral", "text": f"仍需监控{constraint_name},防止边际抽水反复。"},
        ]
    return [
        {"label": "久期", "tone": "neutral", "text": "流动性对久期影响中性,主要看通胀与政策路径。"},
        {"label": "风险资产", "tone": "neutral", "text": "风险资产缺少明确流动性方向,等待分位突破。"},
        {"label": "融资压力", "tone": "watch", "text": f"{constraint_name}与{offset_name}相互抵消,关注边际变化。"},
    ]


def macro_liquidity_regime(score: float) -> str:
    if score >= 70:
        return "流动性宽松"
    if score >= 55:
        return "边际宽松"
    if score > 45:
        return "中性"
    if score > 30:
        return "偏紧"
    return "紧缩压力"


def build_percentile_trends(ind: dict[str, Any], auctions: list[dict[str, object]]) -> list[dict[str, Any]]:
    series = ind.get("percentile_series", {})
    specs = [
        ("银行准备金", "FRED WRESBAL", "5Y", series.get("bank_reserves", []), 1_000_000, 2, "$T"),
        ("净流动性", "FRED WALCL - WTREGEN - RRPONTSYD", "5Y", series.get("net_liquidity", []), 1_000_000, 2, "$T"),
        ("流动性动量", "Net liquidity 1M change", "5Y", series.get("net_liquidity_momentum", []), 1_000_000, 2, "$T"),
        ("13周净流动性动量", "Net liquidity 13W change", "5Y", series.get("net_liquidity_13w_momentum", []), 1_000_000, 2, "$T"),
        ("TGA偏离度", "FRED WTREGEN - 52W median", "5Y", series.get("tga_deviation", []), 1_000_000, 2, "$T"),
        ("ON RRP缓冲风险", "FRED RRPONTSYD risk signal", "5Y", series.get("onrrp_buffer_risk", []), 1, 2, ""),
        ("SOFR-EFFR利差", "FRED SOFR - DFF", "5Y", series.get("sofr_effr_spread", []), 1, 1, "bp"),
        ("SOFR-OBFR回购摩擦", "FRED SOFR - OBFR", "5Y", series.get("collateral_repo_friction", []), 1, 1, "bp"),
        ("商票-TBill利差", "FRED DCPF3M - DTB3", "5Y", series.get("cp_tbill_spread", []), 1, 1, "bp"),
        ("资金分裂度(21D)", "SOFR corridor spread dispersion", "5Y", series.get("funding_fragmentation", []), 1, 2, ""),
        ("真实利率水平", "60% DFII5 + 40% DFII10", "5Y", series.get("real_rate_level", []), 1, 2, "%"),
        ("VIX", "FRED VIXCLS", "5Y", series.get("vix", []), 1, 2, ""),
        ("VIX期限结构", "FRED VIXCLS / VXVCLS", "5Y", series.get("vix_term_structure", []), 1, 2, ""),
        ("HY信用利差", "FRED BAMLH0A0HYM2", "5Y", series.get("hy_oas", []), 1, 2, "%"),
        ("HY-IG利差", "FRED HY OAS - IG OAS", "5Y", series.get("hy_ig_oas_spread", []), 1, 1, "bp"),
        ("HY信用偏好(HY/UST)", "FRED HY TR / DGS10 price proxy", "available up to 5Y", series.get("hy_credit_preference", []), 1, 2, ""),
        ("IG信用偏好(IG/UST)", "FRED IG TR / DGS10 price proxy", "available up to 5Y", series.get("ig_credit_preference", []), 1, 2, ""),
        ("金融条件指数(NFCI)", "FRED NFCI", "5Y", series.get("nfci", []), 1, 2, ""),
        ("银行股相对S&P500", "FRED NASDAQBANK / SP500", "5Y", series.get("regional_bank_vs_market", []), 1, 2, ""),
        ("风险资产/美债代理", "FRED SP500 / DGS10 price proxy", "5Y", series.get("risk_vs_safe", []), 1, 2, ""),
        ("高Beta偏好(NDX/US500)", "FRED NASDAQXNDX / NASDAQNQUS500LCT", "5Y", series.get("high_beta_preference", []), 1, 2, ""),
        ("美元广义指数", "FRED DTWEXBGS", "5Y", series.get("dxy", []), 1, 2, ""),
        ("美元实现波动率", "FRED DTWEXBGS 63D realized vol", "5Y", series.get("dxy_realized_vol", []), 1, 1, "%"),
        ("原油波动偏离", "FRED OVXCLS - rolling median", "5Y", series.get("oil_vol_deviation", []), 1, 1, ""),
        ("天然气", "FRED DHHNGSP", "5Y", series.get("natgas", []), 1, 2, "$"),
    ]
    trends: list[dict[str, Any]] = []
    for name, source, window, points, divisor, digits, unit in specs:
        trend_points = historical_percentile_points(points, value_divisor=divisor, value_digits=digits)
        if trend_points:
            trends.append(percentile_trend_payload(name, source, window, unit, trend_points))
    auction_points = auction_percentile_points(auctions)
    if auction_points:
        trends.append(percentile_trend_payload("拍卖投标倍数", "TreasuryDirect auctioned securities", "available sample", "", auction_points))
    return trends


def percentile_trend_payload(name: str, source: str, window: str, unit: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    latest = points[-1]
    prior = points[-2] if len(points) > 1 else None
    change = latest["percentile"] - prior["percentile"] if prior else None
    return {
        "name": name,
        "source": source,
        "window": window,
        "viewWindow": "3Y",
        "unit": unit,
        "latestPercentile": latest["percentile"],
        "change": change,
        "points": points,
    }


def auction_percentile_points(auctions: list[dict[str, object]], display_years: int = 3, max_points: int = 52) -> list[dict[str, Any]]:
    dated: list[tuple[date, float]] = []
    for auction in auctions:
        auction_date = parse_dashboard_date(auction.get("auctionDate"))
        btc = parse_number(auction.get("bidToCoverRatio"))
        if auction_date is not None and btc is not None and math.isfinite(btc):
            dated.append((auction_date, btc))
    dated.sort(key=lambda item: item[0])
    if not dated:
        return []
    display_start = window_start(dated[-1][0], years=display_years)
    visible_indices = [index for index, item in enumerate(dated) if item[0] >= display_start]
    sampled_visible_indices = sampled_indices(len(visible_indices), max_points)
    rows: list[dict[str, Any]] = []
    for visible_index in sampled_visible_indices:
        index = visible_indices[visible_index]
        auction_date, btc = dated[index]
        values = [item[1] for item in dated[: index + 1]]
        percentile = historical_percentile(btc, values)
        if percentile is None:
            continue
        rows.append({"date": auction_date.isoformat(), "value": round(btc, 2), "percentile": percentile})
    return rows


def build_percentile_movers(trends: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trend in trends:
        change = trend.get("change")
        if not isinstance(change, int) or change == 0:
            continue
        rows.append(
            {
                "name": trend["name"],
                "percentile": trend["latestPercentile"],
                "change": change,
                "direction": "up" if change > 0 else "down",
                "source": trend["source"],
                "window": trend["window"],
            }
        )
    return sorted(rows, key=lambda item: abs(item["change"]), reverse=True)[:limit]


def build_percentile_alerts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        percentile = item.get("percentile")
        if not isinstance(percentile, int):
            continue
        if 10 < percentile < 90:
            continue
        high = percentile >= 90
        severity = "extreme" if percentile >= 95 or percentile <= 5 else "watch"
        rows.append(
            {
                "name": item["name"],
                "value": item["value"],
                "percentile": percentile,
                "side": "high" if high else "low",
                "severity": severity,
                "source": item["source"],
                "message": "处于历史高分位区间" if high else "处于历史低分位区间",
            }
        )
    return rows


def auction_demand_signal(auctions: list[dict[str, object]]) -> dict[str, Any]:
    dated: list[tuple[date, float, str]] = []
    for auction in auctions:
        auction_date = parse_dashboard_date(auction.get("auctionDate"))
        btc = parse_number(auction.get("bidToCoverRatio"))
        if auction_date is None or btc is None:
            continue
        security_term = str(auction.get("securityTerm") or auction.get("term") or "").strip()
        security_type = str(auction.get("securityType") or auction.get("type") or "").strip()
        label = " ".join(part for part in (security_term, security_type) if part) or "Treasury auction"
        dated.append((auction_date, btc, label))
    if not dated:
        return {
            "tag": "TreasuryDirect",
            "label": "待结果",
            "score": 0,
            "note": "TreasuryDirect拍卖数据不可用时不填入历史百分位。",
            "value": "--",
            "percentile": None,
        }
    dated.sort(key=lambda item: item[0])
    latest_date, latest_btc, latest_label = dated[-1]
    percentile = historical_percentile(latest_btc, [item[1] for item in dated])
    score = 1 if percentile is not None and percentile >= 70 else -1 if percentile is not None and percentile <= 30 else 0
    label = "强劲" if score > 0 else "偏弱" if score < 0 else "中性"
    return {
        "tag": f"{latest_label} BTC {latest_btc:.2f} · {percentile_label(percentile)}",
        "label": label,
        "score": score,
        "note": f"TreasuryDirect最新拍卖 {latest_date.isoformat()} bid-to-cover相对可用历史样本的百分位。",
        "value": f"{latest_btc:.2f}",
        "percentile": percentile,
    }


def build_auctions(auctions: list[dict[str, object]]) -> list[dict[str, str]]:
    def parse_date(item: dict[str, object]) -> date:
        raw = str(item.get("auctionDate") or "1900-01-01")[:10]
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return date(1900, 1, 1)

    rows = []
    for item in sorted(auctions, key=parse_date, reverse=True)[:8]:
        security_type = str(item.get("securityType") or "")
        term = str(item.get("securityTerm") or "")
        amount = str(item.get("offeringAmount") or item.get("competitiveAccepted") or "")
        btc = str(item.get("bidToCoverRatio") or "")
        high_yield = str(item.get("highYield") or item.get("averageMedianYield") or item.get("averageMedianDiscountRate") or "")
        rows.append(
            {
                "type": f"{term} {security_type}".strip(),
                "size": money_billions(amount),
                "yield": format_yield(high_yield),
                "btc": btc[:4] if btc else "--",
                "rating": auction_rating(btc),
            }
        )
    return rows or [{"type": "TreasuryDirect", "size": "--", "yield": "--", "btc": "--", "rating": "暂无可解析拍卖"}]


def money_billions(raw: str) -> str:
    try:
        return f"${float(raw) / 1_000_000_000:.0f}B"
    except (TypeError, ValueError):
        return "--"


def money_billions_value(value: float | None) -> str:
    if value is None:
        return "--"
    return f"${value:.0f}B"


def qra_supply_note(refunding: QuarterlyRefunding) -> str:
    parts = [f"官方QRA {refunding.release_date.isoformat()}"]
    if refunding.current_quarter_borrowing_billions is not None:
        parts.append(f"本季借款 {money_billions_value(refunding.current_quarter_borrowing_billions)}")
    if refunding.next_quarter_borrowing_billions is not None:
        parts.append(f"下季借款 {money_billions_value(refunding.next_quarter_borrowing_billions)}")
    if refunding.refunding_new_cash_billions is not None:
        parts.append(f"refunding新现金 {money_billions_value(refunding.refunding_new_cash_billions)}")
    if refunding.coupon_stance:
        parts.append(refunding.coupon_stance)
    return "; ".join(parts)


def parse_number(raw: object) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return None


def parse_dashboard_date(raw: object) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def money_from_raw_dollars(value: float) -> str:
    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.0f}B"
    return f"${value / 1_000_000:.0f}M"


def format_yield(raw: str) -> str:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return "--"
    return f"{value:.3f}%"


def auction_rating(raw_btc: str) -> str:
    try:
        btc = float(raw_btc)
    except (TypeError, ValueError):
        return "待结果"
    if btc >= 2.7:
        return "强劲"
    if btc >= 2.4:
        return "稳健"
    if btc >= 2.2:
        return "偏弱"
    return "疲弱"


def build_fiscal(
    ind: dict[str, Any],
    quarterly_refunding: QuarterlyRefunding | None = None,
    debt_limit_status: DebtLimitStatus | None = None,
) -> list[list[str]]:
    rows: list[list[str]] = []
    if quarterly_refunding:
        next_borrow = quarterly_refunding.next_quarter_borrowing_billions
        current_borrow = quarterly_refunding.current_quarter_borrowing_billions
        qra_value = f"{quarterly_refunding.quarter} · 下季借款 {money_billions_value(next_borrow)}"
        if next_borrow is None:
            qra_value = f"{quarterly_refunding.quarter} · 本季借款 {money_billions_value(current_borrow)}"
        rows.append(["季度再融资 (QRA)", qra_value, f"Policy Statement {quarterly_refunding.release_date.isoformat()}"])
        if current_borrow is not None or quarterly_refunding.current_quarter_cash_balance_billions is not None:
            rows.append(
                [
                    "本季借款 / 现金余额",
                    f"{money_billions_value(current_borrow)} / {money_billions_value(quarterly_refunding.current_quarter_cash_balance_billions)}",
                    "Treasury financing estimates",
                ]
            )
        if quarterly_refunding.buyback_total_billions is not None:
            rows.append(["Buybacks", f"up to {money_billions_value(quarterly_refunding.buyback_total_billions)}", "QRA tentative schedule"])
    if debt_limit_status:
        rows.append(["债务上限空间", money_from_millions(debt_limit_status.headroom_millions), f"Fiscal Data {debt_limit_status.record_date.isoformat()}"])
        rows.append(["受限债务 / 法定上限", f"{money_from_millions(debt_limit_status.debt_subject_to_limit_millions)} / {money_from_millions(debt_limit_status.statutory_limit_millions)}", "DTS Debt Subject to Limit"])
    return rows + [
        ["TGA 余额", f"${ind['tga_trillions']:.2f}T", "FRED WTREGEN"],
        ["10Y-2Y", f"{ind['s2s10']:.0f}bp", "曲线形态"],
        ["5s30s", f"{ind['s5s30']:.0f}bp", "长端供给压力代理"],
        ["10Y月变动", f"{ind['ten_year_m1_change_bp']:+.0f}bp", "长端动量"],
    ]


def build_positioning(
    *,
    cftc_positions: list[CftcTreasuryPosition],
    tic_holdings: TicHoldings | None,
    primary_dealer_stats: PrimaryDealerStats | None,
) -> dict[str, list[list[str]]]:
    if cftc_positions:
        cftc_rows = [
            [
                f"CFTC · {item.market}",
                f"杠杆基金净{direction_word(item.leveraged_net)} {compact_int(abs(item.leveraged_net))}张 ({item.leveraged_net_pct_oi:+.1f}% OI)",
                f"资管净{direction_word(item.asset_manager_net)} {compact_int(abs(item.asset_manager_net))}张 · {item.report_date.isoformat()}",
            ]
            for item in cftc_positions[:5]
        ]
        aggregate_net = sum(item.leveraged_net for item in cftc_positions)
        aggregate_oi = sum(item.open_interest for item in cftc_positions)
        aggregate_pct = (aggregate_net / aggregate_oi) * 100 if aggregate_oi else 0.0
        cftc_rows.append(
            [
                "CFTC · 国债期货合计",
                f"杠杆基金净{direction_word(aggregate_net)} {compact_int(abs(aggregate_net))}张 ({aggregate_pct:+.1f}% OI)",
                "周频COT financial futures,按最新报告日聚合",
            ]
        )
    else:
        cftc_rows = [
            ["CFTC 期货持仓", "待接COT周频文件", "未伪装为实时"],
            ["基差交易", "需经纪商/监管报告补充", "风险提示保留"],
        ]

    if tic_holdings:
        tic_rows = [
            [holding.country, money_trillions_from_billions(holding.value_billions), change_text(holding.monthly_change_billions)]
            for holding in tic_holdings.holdings[:5]
        ]
        if tic_holdings.total:
            tic_rows.append(
                [
                    "全球外资总持仓",
                    money_trillions_from_billions(tic_holdings.total.value_billions),
                    change_text(tic_holdings.total.monthly_change_billions),
                ]
            )
        if tic_holdings.official:
            tic_rows.append(
                [
                    "官方部门持仓",
                    money_trillions_from_billions(tic_holdings.official.value_billions),
                    change_text(tic_holdings.official.monthly_change_billions),
                ]
            )
    else:
        tic_rows = [
            ["TIC 海外持仓", "待接月频CSV/TXT", "滞后约六周"],
            ["全球外资总持仓", "--", "等待低频管线"],
        ]

    if primary_dealer_stats:
        dealer_rows = primary_dealer_rows(primary_dealer_stats)
    else:
        dealer_rows = [
            ["Primary dealers", "待接NY Fed周频API", "未伪装为实时"],
            ["UST repo / fails", "--", "等待Primary Dealer Statistics"],
        ]
    return {"cftc": cftc_rows, "tic": tic_rows, "dealers": dealer_rows}


def primary_dealer_rows(stats: PrimaryDealerStats) -> list[list[str]]:
    labels = [
        ("PDPOSGST-TOT", "Primary dealers · UST ex-TIPS", "净持仓"),
        ("PDGSWOEXTTOT", "Primary dealers · UST交易量", "周成交额"),
        ("PDSORA-UTSETTOT", "Primary dealers · UST repo", "融资余额"),
        ("PDSIOSB-UTSETTOT", "Primary dealers · UST borrowed", "借券/融资"),
        ("PDSOOS-UTSETTOT", "Primary dealers · UST lent", "出借证券"),
        ("PDSIRRA-UTSETTOT", "Primary dealers · UST reverse repo", "逆回购余额"),
    ]
    rows: list[list[str]] = []
    for key, label, note in labels:
        value = stats.metrics_millions.get(key)
        if value is None:
            continue
        rows.append([label, money_from_millions(value), f"{note} · {stats.as_of.isoformat()}"])
    return rows or [["Primary dealers", "本期关键指标未披露", stats.as_of.isoformat()]]


def build_cross_market(ind: dict[str, Any]) -> dict[str, Any]:
    return {
        "yields": [
            ["美国 UST", rounded(ind["ten_year"])],
            ["德国 Bund", rounded(ind["bund_10y"])],
            ["英国 Gilt", rounded(ind["gilt_10y"])],
            ["日本 JGB", rounded(ind["jgb_10y"])],
        ],
        "risk": [
            ["标普 500", f"{ind['sp500']:.2f}", f"最新日变动 {ind['sp500_change_pct']:+.2f}%"],
            ["VIX", f"{ind['vix']:.2f}", "FRED VIXCLS"],
            ["美元广义指数", f"{ind['dxy']:.2f}", "FRED DTWEXBGS"],
            ["IG / HY 信用利差", f"{ind['ig_oas']:.2f}% / {ind['hy_oas']:.2f}%", "ICE BofA OAS"],
        ],
        "inflation": [
            ["CPI通胀", f"{ind['cpi_yoy']:.1f}%", "FRED CPIAUCSL YoY"],
            ["PCE通胀", f"{ind['pce_yoy']:.1f}%", "FRED PCEPI YoY"],
            ["核心PCE", f"{ind['core_pce_yoy']:.1f}%", "FRED PCEPILFE YoY"],
            ["达拉斯联储Trimmed Mean PCE", f"{ind['trimmed_mean_pce_yoy']:.1f}%", "FRED PCETRIM12M159SFRBDAL"],
            ["10年盈亏平衡通胀", f"{ind['breakeven_10y']:.2f}%", "FRED T10YIE"],
            ["10年实际利率", f"{ind['real_10y']:.2f}%", "FRED DFII10"],
            ["WTI 原油", f"${ind['wti']:.2f}", "FRED DCOILWTICO"],
            ["黄金现货", f"${ind['gold_spot']:.2f}", "Stooq XAUUSD"],
            ["原油/黄金波动", f"OVX {ind['oil_vol']:.2f} / GVZ {ind['gold_vol']:.2f}", "CBOE volatility indexes via FRED"],
        ],
        "historySeries": build_cross_market_history_series(),
    }


def build_cross_market_history_series() -> list[dict[str, Any]]:
    return [
        {
            "id": "global",
            "label": "全球利率",
            "en": "Global Rates",
            "series": [
                history_series_target("美国10Y", "curve_yield", "10Y收益率", "10Y", "%", "U.S. Treasury yield curve XML"),
                history_series_target("德国10Y", "global_yield", "德国10Y", "IRLTLT01DEM156N", "%", "FRED IRLTLT01DEM156N"),
                history_series_target("英国10Y", "global_yield", "英国10Y", "IRLTLT01GBM156N", "%", "FRED IRLTLT01GBM156N"),
                history_series_target("日本10Y", "global_yield", "日本10Y", "IRLTLT01JPM156N", "%", "FRED IRLTLT01JPM156N"),
            ],
        },
        {
            "id": "risk",
            "label": "风险与美元",
            "en": "Risk & USD",
            "series": [
                history_series_target("S&P 500", "risk", "S&P 500", "SP500", "index", "FRED SP500"),
                history_series_target("VIX", "risk", "VIX", "VIXCLS", "index", "FRED VIXCLS"),
                history_series_target("VIX期限结构", "risk", "VIX期限结构", "vix_term_structure", "", "FRED VIXCLS / VXVCLS"),
                history_series_target("美元广义指数", "fx", "美元广义指数", "DTWEXBGS", "index", "FRED DTWEXBGS"),
                history_series_target("HY信用利差", "credit", "HY信用利差", "BAMLH0A0HYM2", "%", "FRED BAMLH0A0HYM2"),
                history_series_target("IG信用利差", "credit", "IG信用利差", "BAMLC0A0CM", "%", "FRED BAMLC0A0CM"),
            ],
        },
        {
            "id": "inflation",
            "label": "通胀与商品",
            "en": "Inflation & Commodities",
            "series": [
                history_series_target("CPI指数", "macro", "CPI指数", "CPIAUCSL", "index", "FRED CPIAUCSL"),
                history_series_target("PCE价格指数", "macro", "PCE价格指数", "PCEPI", "index", "FRED PCEPI"),
                history_series_target("核心PCE价格指数", "macro", "核心PCE价格指数", "PCEPILFE", "index", "FRED PCEPILFE"),
                history_series_target("达拉斯Trimmed Mean PCE", "inflation", "达拉斯联储Trimmed Mean PCE", "PCETRIM12M159SFRBDAL", "%YoY", "FRED PCETRIM12M159SFRBDAL"),
                history_series_target("10Y盈亏平衡通胀", "inflation", "10Y盈亏平衡通胀", "T10YIE", "%", "FRED T10YIE"),
                history_series_target("10Y实际利率", "real_rate", "10Y实际利率", "DFII10", "%", "FRED DFII10"),
                history_series_target("WTI原油", "commodity", "WTI原油", "DCOILWTICO", "$/bbl", "FRED DCOILWTICO"),
                history_series_target("OVX原油波动率", "volatility", "OVX原油波动率", "OVXCLS", "index", "FRED OVXCLS"),
                history_series_target("GVZ黄金波动率", "volatility", "GVZ黄金波动率", "GVZCLS", "index", "FRED GVZCLS"),
            ],
        },
    ]


def history_series_target(display_name: str, category: str, name: str, series_label: str, unit: str, source: str) -> dict[str, str]:
    return {
        "displayName": display_name,
        "category": category,
        "name": name,
        "label": series_label,
        "unit": unit,
        "source": source,
    }


def build_events(
    as_of: date,
    *,
    calendar_events: list[CalendarEvent],
    announced_auctions: list[dict[str, object]],
    quarterly_refunding: QuarterlyRefunding | None = None,
) -> list[list[str]]:
    rows: list[tuple[date, str, str]] = []
    for event in calendar_events:
        if event.date >= as_of:
            rows.append((event.date, event.title, event.importance))
    if quarterly_refunding:
        if quarterly_refunding.next_financing_estimates_date and quarterly_refunding.next_financing_estimates_date >= as_of:
            rows.append((quarterly_refunding.next_financing_estimates_date, "Treasury borrowing estimates / QRA pre-release", "中"))
        if quarterly_refunding.next_policy_statement_date and quarterly_refunding.next_policy_statement_date >= as_of:
            rows.append((quarterly_refunding.next_policy_statement_date, "Treasury quarterly refunding statement", "高"))
    for auction in announced_auctions:
        auction_date = parse_dashboard_date(auction.get("auctionDate"))
        if auction_date is None or auction_date < as_of:
            continue
        security_term = str(auction.get("securityTerm") or auction.get("term") or "").strip()
        security_type = str(auction.get("securityType") or auction.get("type") or "").strip()
        amount = parse_number(auction.get("offeringAmount"))
        title = "Treasury auction"
        detail = " ".join(part for part in (security_term, security_type) if part)
        if detail:
            title = f"{title} · {detail}"
        if amount is not None:
            title = f"{title} · {money_from_raw_dollars(amount)}"
        rows.append((auction_date, title, "中"))
    if not rows:
        rows = [(as_of, "每日收益率曲线/公开源更新", "中"), (as_of + timedelta(days=1), "检查FRED与Treasury最新发布", "中")]
    rows.sort(key=lambda item: (item[0], importance_rank(item[2]), item[1]))
    rows = select_event_rows(rows, limit=10)
    return [[event_date.isoformat(), title, importance] for event_date, title, importance in rows]


def is_core_event(row: tuple[date, str, str]) -> bool:
    title = row[1]
    return (
        title.startswith("FOMC ")
        or title.startswith("BLS ")
        or title.startswith("BEA ")
        or "QRA" in title
        or "quarterly refunding" in title
        or "borrowing estimates" in title
    )


def should_force_late_event(row: tuple[date, str, str], selected: list[tuple[date, str, str]]) -> bool:
    title = row[1]
    if is_qra_event_title(title):
        return True
    if title.startswith("FOMC "):
        return sum(1 for selected_row in selected if selected_row[1].startswith("FOMC ")) < 2
    if title.startswith("BLS "):
        return sum(1 for selected_row in selected if selected_row[1].startswith("BLS ")) < 3
    if title.startswith("BEA "):
        return sum(1 for selected_row in selected if selected_row[1].startswith("BEA ")) < 2
    return False


def is_qra_event_title(title: str) -> bool:
    return "QRA" in title or "quarterly refunding" in title or "borrowing estimates" in title


def select_event_rows(rows: list[tuple[date, str, str]], limit: int) -> list[tuple[date, str, str]]:
    selected = list(rows[:limit])
    for row in rows[limit:]:
        if not should_force_late_event(row, selected) or row in selected:
            continue
        replace_candidates = [index for index, selected_row in enumerate(selected) if not is_core_event(selected_row)]
        if not replace_candidates and is_qra_event_title(row[1]):
            replace_candidates = [
                index
                for index, selected_row in enumerate(selected)
                if not selected_row[1].startswith("FOMC ") and not is_qra_event_title(selected_row[1])
            ]
        if not replace_candidates:
            continue
        replace_index = max(replace_candidates, key=lambda index: (selected[index][0], selected[index][1]))
        selected[replace_index] = row
    selected.sort(key=lambda item: (item[0], importance_rank(item[2]), item[1]))
    return selected


def build_news(
    as_of: date,
    ind: dict[str, Any],
    quarterly_refunding: QuarterlyRefunding | None = None,
    official_news: list[NewsItem] | None = None,
) -> list[list[str]]:
    rows: list[list[str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in sorted(official_news or [], key=lambda entry: (entry.date, entry.source, entry.title), reverse=True):
        row = [item.date.strftime("%m/%d"), item.source, item.title]
        key = (row[0], row[1], row[2])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if len(rows) >= 5:
            return rows

    fallback_rows = [
        [as_of.strftime("%m/%d"), "U.S. Treasury", f"10Y {ind['ten_year']:.2f}%, 30Y {ind['thirty_year']:.2f}%"],
        [as_of.strftime("%m/%d"), "FRED", f"10Y TIPS {ind['real_10y']:.2f}%, 10Y BEI {ind['breakeven_10y']:.2f}%"],
    ]
    if quarterly_refunding:
        summary = qra_supply_note(quarterly_refunding)
        fallback_rows.append([quarterly_refunding.release_date.strftime("%m/%d"), "Treasury QRA", summary[:180]])
    for row in fallback_rows:
        key = (row[0], row[1], row[2])
        if key in seen:
            continue
        rows.append(row)
        if len(rows) >= 5:
            break
    return rows


def build_ideas(
    ind: dict[str, Any],
    *,
    macro_liquidity: dict[str, Any] | None = None,
    macro_liquidity_equity: dict[str, Any] | None = None,
    quarterly_refunding: QuarterlyRefunding | None = None,
    conclusion_audit: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    liquidity_score = optional_float(macro_liquidity.get("score")) if macro_liquidity else None
    liquidity_regime = macro_liquidity.get("regime") if macro_liquidity else "待评分"
    liquidity_text = f"宏观环境评分{liquidity_score:.1f}({liquidity_regime})" if isinstance(liquidity_score, (int, float)) else f"宏观环境{liquidity_regime}"
    qra_text = "QRA待接入"
    qra_borrowing = None
    if quarterly_refunding:
        qra_borrowing = quarterly_refunding.next_quarter_borrowing_billions
        next_borrow = money_billions_value(qra_borrowing)
        next_date = quarterly_refunding.next_policy_statement_date.isoformat() if quarterly_refunding.next_policy_statement_date else "待公布"
        qra_text = f"QRA下季借款{next_borrow},下一次政策声明{next_date}"
    inflation_tracker = (
        f"CPI {ind['cpi_yoy']:.1f}% / PCE {ind['pce_yoy']:.1f}% / "
        f"核心PCE {ind['core_pce_yoy']:.1f}% / Dallas Trimmed PCE {ind['trimmed_mean_pce_yoy']:.1f}%"
    )
    inflation_max = max(ind["cpi_yoy"], ind["pce_yoy"], ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"], ind["ppi_yoy"])
    inflation_core_max = max(ind["pce_yoy"], ind["core_pce_yoy"], ind["trimmed_mean_pce_yoy"])
    inflation_hot = inflation_max >= 3.0
    inflation_cool = inflation_core_max <= 2.4 and ind["ppi_yoy"] <= 2.5
    two_year_change = ind["two_year_m1_change_bp"]
    macro_tight = liquidity_score is not None and liquidity_score < 45
    qra_supply_heavy = qra_borrowing is not None and qra_borrowing >= 500
    qra_supply_light = qra_borrowing is not None and qra_borrowing <= 350
    curve_already_steep = ind["s5s30"] >= 95
    two_year_vs_effr_bp = (ind["two_year"] - ind["dff"]) * 100
    cuts_priced = two_year_vs_effr_bp <= -60 and two_year_change <= -25
    energy_hot = ind["wti"] >= 80 or ind.get("wti_shock", 0.0) >= 0.10
    energy_soft = ind["wti"] <= 75 or ind.get("wti_shock", 0.0) <= -0.10
    bei_rich = ind["breakeven_10y"] >= 2.55

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
        duration_idea = {
            "title": "战术减久期",
            "tag": "SHORT 久期",
            "text": (
                f"{inflation_tracker}仍对久期不友好,2Y月变动{two_year_change:+.0f}bp显示政策路径重新定价。"
                f"{liquidity_text}提示承接环境不算宽松,组合久期维持低于基准,等待PCE/核心PCE降温或2Y回落再加回。"
            ),
            "source": "货币政策 · 宏观基本面 · 宏观环境评分",
        }
    else:
        duration_idea = {
            "title": "久期区间防守",
            "tag": "HOLD 久期",
            "text": (
                f"{inflation_tracker}与2Y月变动{two_year_change:+.0f}bp没有形成单边信号。"
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
                f"2Y收益率{ind['two_year']:.2f}%已较EFFR低{abs(two_year_vs_effr_bp):.0f}bp,且月变动{two_year_change:+.0f}bp,说明降息预期已经较多反映。"
                "前端仍可用于防守,但不应简单视作高确定性carry;若就业或核心PCE反弹,前端回撤风险会放大。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }
    elif ind["two_year"] >= 3.0 and ind["sofr"] >= 3.0 and ind["dff"] >= 3.0:
        front_end_idea = {
            "title": "前端持有 · 吃 carry",
            "tag": "LONG 前端",
            "text": (
                f"2Y收益率{ind['two_year']:.2f}%,SOFR {ind['sofr']:.2f}%、EFFR {ind['dff']:.2f}%仍提供前端票息。"
                "相对长端,前端对供给冲击和期限溢价更不敏感,适合作为风险预算内的现金替代。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }
    else:
        front_end_idea = {
            "title": "前端中性 · 等待再定价",
            "tag": "FRONT-END 中性",
            "text": (
                f"2Y收益率{ind['two_year']:.2f}%,SOFR {ind['sofr']:.2f}%、EFFR {ind['dff']:.2f}%没有形成明确carry优势。"
                "前端更适合作为流动性仓位,等待政策路径或资金利率重新拉开风险补偿。"
            ),
            "source": "货币政策 · SOFR/EFFR · 前端曲线",
        }

    if inflation_cool and energy_soft and bei_rich:
        breakeven_idea = {
            "title": "降低盈亏平衡通胀",
            "tag": "RV 降通胀补偿",
            "text": (
                f"{inflation_tracker}降温,WTI ${ind['wti']:.2f}未提供能源上行确认,但10Y BEI仍有{ind['breakeven_10y']:.2f}%。"
                "盈亏平衡通胀的风险回报转弱,更适合减仓或等待能源/核心PCE重新加速。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    elif inflation_hot and (energy_hot or not bei_rich):
        breakeven_idea = {
            "title": "战术做多盈亏平衡通胀",
            "tag": "RV 通胀",
            "text": (
                f"10Y BEI {ind['breakeven_10y']:.2f}%、WTI ${ind['wti']:.2f}共同跟踪通胀补偿。"
                "若能源冲击或进口价格继续传导,盈亏平衡比名义久期更直接;油价回落或PCE/核心PCE降温是退出信号。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    elif bei_rich and not inflation_hot:
        breakeven_idea = {
            "title": "通胀补偿转防守",
            "tag": "RV 观望",
            "text": (
                f"10Y BEI {ind['breakeven_10y']:.2f}%已经偏高,而{inflation_tracker}没有同步恶化。"
                "盈亏平衡更适合等待回调后再布局,或只保留小额尾部对冲。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    else:
        breakeven_idea = {
            "title": "小仓位通胀对冲",
            "tag": "RV 对冲",
            "text": (
                f"10Y BEI {ind['breakeven_10y']:.2f}%、WTI ${ind['wti']:.2f}没有形成强单边信号。"
                "保留小仓位通胀对冲即可,加仓需要能源冲击或PCE/核心PCE重新上行确认。"
            ),
            "source": "跨市场 · T10YIE · WTI",
        }
    confidence_fields = investment_view_confidence_fields(conclusion_audit)
    equity_impact = investment_view_equity_impact(macro_liquidity_equity)
    return [
        {**idea, **confidence_fields, "equityImpact": equity_impact}
        for idea in [
        duration_idea,
        curve_idea,
        front_end_idea,
        breakeven_idea,
        ]
    ]


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


def numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = optional_float(row.get(key))
        if value is not None:
            values.append(value)
    return values


def equity_impact_confidence(sample_size: int, forward_3m: list[float], signal_confidence: str) -> dict[str, str]:
    spread = max(forward_3m) - min(forward_3m) if forward_3m else 0.0
    key = "high" if sample_size >= 12 and spread <= 10 else "medium" if sample_size >= 6 else "low"
    if signal_confidence == "low" and key == "high":
        key = "medium"
    return {"key": key, "label": {"high": "高", "medium": "中", "low": "低"}[key]}


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


def direction_word(value: float) -> str:
    return "多" if value >= 0 else "空"


def compact_int(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def money_trillions_from_billions(value: float) -> str:
    return f"${value / 1_000:.2f}T"


def money_from_millions(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}T"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}B"
    return f"${value:.0f}M"


def importance_rank(value: str) -> int:
    return {"高": 0, "中": 1, "低": 2}.get(value, 3)


def change_text(value: float | None) -> str:
    if value is None:
        return "月变动暂无"
    return f"月变动 {value:+.1f}B"


def load_content_overrides(path: Path = DEFAULT_OVERRIDES_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def apply_content_overrides(dashboard: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    if not overrides:
        return dashboard
    updated = copy.deepcopy(dashboard)
    if isinstance(overrides.get("ideas"), list):
        updated["ideas"] = overrides["ideas"]
    if isinstance(overrides.get("events"), list):
        updated["events"] = overrides["events"]
    if isinstance(overrides.get("news"), list):
        updated["news"] = overrides["news"]
    group_weights = overrides.get("groupWeights")
    if isinstance(group_weights, dict):
        for group in updated.get("groups", []):
            if group.get("id") in group_weights:
                group["weight"] = group_weights[group["id"]]
    factor_overrides = overrides.get("factorOverrides")
    if isinstance(factor_overrides, dict):
        for group in updated.get("groups", []):
            group_override = factor_overrides.get(group.get("id"))
            if not isinstance(group_override, dict):
                continue
            for factor in group.get("factors", []):
                patch = group_override.get(factor.get("n"))
                if isinstance(patch, dict):
                    factor.update(patch)
    return updated


def rounded(value: float) -> float:
    return round(value, 2)
