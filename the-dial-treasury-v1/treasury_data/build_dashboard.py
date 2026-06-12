from __future__ import annotations

import copy
import json
import math
import re
import sqlite3
from statistics import median
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .sources import (
    AcmRecord,
    CalendarEvent,
    CftcTreasuryPosition,
    DebtLimitStatus,
    FomcProjection,
    MarketDailyBar,
    MarketQuote,
    NewsItem,
    OptionOpenInterestSnapshot,
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
    fetch_cboe_option_open_interest,
    fetch_nasdaq_daily_bars,
    fetch_primary_dealer_stats,
    fetch_quarterly_refunding,
    fetch_stooq_daily_bars,
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
GLOBAL_LPPL_INDEX_SPECS: list[dict[str, Any]] = [
    {
        "symbol": "SPY",
        "name": "SPY",
        "region": "US broad",
        "source": "nasdaq",
        "sourceSymbol": "SPY",
        "fallbackSymbol": "spy.us",
        "assetClass": "etf",
        "sourceQuality": "high",
        "weight": 0.23,
    },
    {
        "symbol": "QQQ",
        "name": "Nasdaq / QQQ proxy",
        "region": "US tech",
        "source": "nasdaq",
        "sourceSymbol": "QQQ",
        "fallbackSymbol": "qqq.us",
        "assetClass": "etf",
        "sourceQuality": "high",
        "weight": 0.23,
    },
    {
        "symbol": "KOSPI",
        "name": "KOSPI / EWY proxy",
        "region": "Korea ETF proxy",
        "source": "nasdaq",
        "sourceSymbol": "EWY",
        "fallbackSymbol": "ewy.us",
        "assetClass": "etf",
        "sourceQuality": "medium",
        "weight": 0.13,
    },
    {
        "symbol": "HSI",
        "name": "Hang Seng / EWH proxy",
        "region": "Hong Kong ETF proxy",
        "source": "nasdaq",
        "sourceSymbol": "EWH",
        "fallbackSymbol": "ewh.us",
        "assetClass": "etf",
        "sourceQuality": "medium",
        "weight": 0.13,
    },
    {
        "symbol": "TWII",
        "name": "Taiwan Weighted / EWT proxy",
        "region": "Taiwan ETF proxy",
        "source": "nasdaq",
        "sourceSymbol": "EWT",
        "fallbackSymbol": "ewt.us",
        "assetClass": "etf",
        "sourceQuality": "medium",
        "weight": 0.13,
    },
    {
        "symbol": "NIKKEI",
        "name": "Nikkei / EWJ proxy",
        "region": "Japan ETF proxy",
        "source": "nasdaq",
        "sourceSymbol": "EWJ",
        "fallbackSymbol": "ewj.us",
        "assetClass": "etf",
        "sourceQuality": "medium",
        "weight": 0.15,
    },
]
GLOBAL_LPPL_MIN_OBSERVATIONS = 120
GLOBAL_LPPL_DEFAULT_WINDOW = 252
GLOBAL_LPPL_SIGNAL_WINDOWS = (120, 180, GLOBAL_LPPL_DEFAULT_WINDOW, 375, 500, 750)
GLOBAL_LPPL_HISTORY_STEP = 1
GLOBAL_LPPL_ALERT_THRESHOLD = 65
FRED_TREASURY_CURVE_SERIES: dict[str, str] = {
    "1M": "DGS1MO",
    "3M": "DGS3MO",
    "6M": "DGS6MO",
    "1Y": "DGS1",
    "2Y": "DGS2",
    "3Y": "DGS3",
    "5Y": "DGS5",
    "7Y": "DGS7",
    "10Y": "DGS10",
    "20Y": "DGS20",
    "30Y": "DGS30",
}
EXPECTED_SOURCE_CADENCE_DAYS: dict[str, int] = {
    "NY Fed ACM term premium": 45,
    "CFTC financial futures COT": 10,
    "Treasury TIC major foreign holders": 75,
    "NY Fed primary dealer statistics": 21,
    "Federal Reserve SEP projections": 120,
    "U.S. Treasury quarterly refunding documents": 120,
    "Treasury Fiscal Data debt subject to limit": 10,
    "Stooq 30-Day Fed Funds futures ZQ.F": 5,
    "Stooq gold spot XAUUSD": 5,
}
DailyBarFetcher = Callable[..., list[MarketDailyBar]]


def stooq_fallback_symbol(symbol: str, fallback_symbol: str | None = None) -> str:
    if fallback_symbol:
        return fallback_symbol
    return f"{symbol.strip().lower()}.us"


def remap_market_bars_symbol(bars: list[MarketDailyBar], symbol: str) -> list[MarketDailyBar]:
    output_symbol = symbol.upper()
    return [
        MarketDailyBar(
            symbol=output_symbol,
            date=bar.date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            source=bar.source,
        )
        for bar in bars
    ]


def fetch_daily_bars_with_stooq_fallback(
    symbol: str,
    *,
    start: date,
    end: date,
    asset_class: str = "stocks",
    timeout: int = 14,
    limit: int = 900,
    fallback_symbol: str | None = None,
    output_symbol: str | None = None,
    fetcher: DailyBarFetcher | None = None,
    fallback_fetcher: DailyBarFetcher | None = None,
) -> tuple[list[MarketDailyBar], dict[str, Any]]:
    primary_fetcher = fetcher or fetch_nasdaq_daily_bars
    stooq_fetcher = fallback_fetcher or fetch_stooq_daily_bars
    try:
        bars = primary_fetcher(symbol, start=start, end=end, asset_class=asset_class, timeout=timeout, limit=limit)
        latest = bars[-1].date.isoformat() if bars else "none"
        return remap_market_bars_symbol(bars, output_symbol or symbol), {"status": "ok", "latest": latest, "source": "nasdaq"}
    except Exception as nasdaq_exc:  # noqa: BLE001
        fallback = stooq_fallback_symbol(symbol, fallback_symbol)
        try:
            bars = stooq_fetcher(fallback, start=start, end=end, timeout=timeout)
        except Exception as fallback_exc:  # noqa: BLE001
            raise RuntimeError(f"Nasdaq failed ({nasdaq_exc}); Stooq fallback {fallback} failed ({fallback_exc})") from fallback_exc
        latest = bars[-1].date.isoformat() if bars else "none"
        note = f"Nasdaq failed; using Stooq {fallback}: {nasdaq_exc}"
        return remap_market_bars_symbol(bars, output_symbol or symbol), {
            "status": "ok",
            "latest": latest,
            "source": "stooq-fallback",
            "note": note,
        }


def build_fred_dgs_curve_records(fred: dict[str, TimeSeries]) -> list[YieldCurveRecord]:
    points_by_tenor: dict[str, dict[date, float]] = {}
    for tenor, series_id in FRED_TREASURY_CURVE_SERIES.items():
        series = fred.get(series_id)
        if not series:
            continue
        points_by_tenor[tenor] = {point.date: point.value for point in series.points}
    if set(points_by_tenor) != set(TENORS):
        return []
    common_dates = set.intersection(*(set(values) for values in points_by_tenor.values()))
    records = [
        YieldCurveRecord(date=record_date, values={tenor: points_by_tenor[tenor][record_date] for tenor in TENORS})
        for record_date in sorted(common_dates)
    ]
    return records


def parse_source_latest_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    match = re.search(r"\b(\d{4})-(\d{2})\b", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), 1)
        except ValueError:
            return None
    return None


def annotate_source_status_freshness(
    rows: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    target = as_of or datetime.now(timezone.utc).date()
    annotated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        cadence = expected_source_cadence_days(str(item.get("name") or ""))
        latest_date = parse_source_latest_date(item.get("latest"))
        if cadence is not None:
            item["expectedMaxAgeDays"] = cadence
        if latest_date is not None:
            item["ageDays"] = max(0, (target - latest_date).days)
        if (
            cadence is not None
            and latest_date is not None
            and item.get("status") == "ok"
            and item["ageDays"] > cadence
        ):
            item["status"] = "stale"
            item["note"] = f"Latest observation is {item['ageDays']} days old; expected <= {cadence} days."
        annotated.append(item)
    return annotated


def expected_source_cadence_days(name: str) -> int | None:
    configured = EXPECTED_SOURCE_CADENCE_DAYS.get(name)
    if configured is not None:
        return configured
    if name.startswith("Nasdaq ") and name.endswith(" OHLCV"):
        return 2
    if name.startswith("Global LPPL ") and name.endswith(" OHLCV"):
        return 2
    return None


def build_live_dashboard() -> dict[str, Any]:
    source_status: list[dict[str, Any]] = []
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
    equity_market_bars: dict[str, list[MarketDailyBar]] = {}
    global_lppl_market_bars: dict[str, list[MarketDailyBar]] = {}
    option_open_interest: OptionOpenInterestSnapshot | None = None
    official_news: list[NewsItem] = []

    try:
        curve_records = fetch_treasury_yield_curves()
        latest = curve_records[-1].date.isoformat() if curve_records else "none"
        source_status.append({"name": "U.S. Treasury yield curve XML", "status": "ok", "latest": latest})
    except Exception as exc:  # noqa: BLE001
        try:
            dgs_fred = fetch_fred_series_bulk(FRED_TREASURY_CURVE_SERIES.values(), chunk_size=len(FRED_TREASURY_CURVE_SERIES))
            curve_records = build_fred_dgs_curve_records(dgs_fred)
            if not curve_records:
                raise ValueError("FRED DGS fallback did not return a complete curve")
            latest = curve_records[-1].date.isoformat()
            source_status.append(
                {
                    "name": "U.S. Treasury yield curve XML",
                    "status": "warning",
                    "latest": f"FRED DGS fallback through {latest}; Treasury XML failed: {exc}",
                    "source": "fred-fallback",
                    "note": "Curve built from FRED DGS1MO...DGS30 because Treasury XML was unavailable.",
                }
            )
        except Exception as fallback_exc:  # noqa: BLE001
            source_status.append({"name": "U.S. Treasury yield curve XML", "status": "error", "latest": f"{exc}; FRED DGS fallback failed: {fallback_exc}"})

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
        source_status.append({"name": "Stooq 30-Day Fed Funds futures ZQ.F", "status": "warning", "latest": str(exc)})

    try:
        gold_quote = fetch_gold_spot_quote()
        source_status.append({"name": "Stooq gold spot XAUUSD", "status": "ok", "latest": gold_quote.date.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Stooq gold spot XAUUSD", "status": "warning", "latest": str(exc)})

    equity_end = datetime.now(timezone.utc).date()
    equity_start = equity_end - timedelta(days=365 * 3 + 10)
    for symbol, asset_class in EQUITY_RISK_SYMBOLS.items():
        try:
            bars, status = fetch_daily_bars_with_stooq_fallback(
                symbol,
                start=equity_start,
                end=equity_end,
                asset_class=asset_class,
                timeout=14,
                limit=900,
            )
            equity_market_bars[symbol] = bars
            source_status.append({"name": f"Nasdaq {symbol} OHLCV", **status})
        except Exception as exc:  # noqa: BLE001
            source_status.append({"name": f"Nasdaq {symbol} OHLCV", "status": "warning", "latest": str(exc)})

    global_lppl_market_bars.update({symbol: bars for symbol, bars in equity_market_bars.items() if symbol in {"SPY", "QQQ"}})
    for spec in GLOBAL_LPPL_INDEX_SPECS:
        symbol = str(spec["symbol"]).upper()
        if symbol in global_lppl_market_bars:
            bars = global_lppl_market_bars[symbol]
            latest = bars[-1].date.isoformat() if bars else "none"
            source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "ok", "latest": latest})
            continue
        if spec.get("source") == "nasdaq":
            try:
                bars, status = fetch_daily_bars_with_stooq_fallback(
                    str(spec["sourceSymbol"]),
                    start=equity_start,
                    end=equity_end,
                    asset_class=str(spec.get("assetClass") or "etf"),
                    timeout=14,
                    limit=900,
                    fallback_symbol=str(spec.get("fallbackSymbol") or ""),
                    output_symbol=symbol,
                )
                global_lppl_market_bars[symbol] = bars
                source_status.append({"name": f"Global LPPL {symbol} OHLCV", **status})
            except Exception as exc:  # noqa: BLE001
                source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})
            continue
        if spec.get("source") != "stooq":
            continue
        try:
            bars = fetch_stooq_daily_bars(str(spec["sourceSymbol"]), start=equity_start, end=equity_end, timeout=14)
            global_lppl_market_bars[symbol] = [MarketDailyBar(symbol=symbol, date=bar.date, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume, source=bar.source) for bar in bars]
            latest = bars[-1].date.isoformat() if bars else "none"
            source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "ok", "latest": latest})
        except Exception as exc:  # noqa: BLE001
            source_status.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})

    try:
        option_open_interest = fetch_cboe_option_open_interest("SPY")
        source_status.append({"name": "Cboe SPY option open interest", "status": "ok", "latest": option_open_interest.as_of.isoformat()})
    except Exception as exc:  # noqa: BLE001
        source_status.append({"name": "Cboe SPY option open interest", "status": "warning", "latest": str(exc)})

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
        equity_market_bars=equity_market_bars,
        global_lppl_market_bars=global_lppl_market_bars,
        option_open_interest=option_open_interest,
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
    dashboard["sourceStatus"] = annotate_source_status_freshness(source_status + dashboard.get("sourceStatus", []))
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
    equity_market_bars: dict[str, list[MarketDailyBar]] | None = None,
    global_lppl_market_bars: dict[str, list[MarketDailyBar]] | None = None,
    option_open_interest: OptionOpenInterestSnapshot | None = None,
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
    equity_short_term_risk = build_equity_short_term_risk_index(
        market_bars=equity_market_bars or {},
        macro_liquidity_equity=macro_liquidity_equity,
        spy_early_warning=spy_early_warning,
        calendar_events=calendar_events or [],
        option_open_interest=option_open_interest,
    )
    lppl_bars = dict(equity_market_bars or {})
    lppl_bars.update(global_lppl_market_bars or {})
    global_lppl_risk = build_global_lppl_risk_index(market_bars=lppl_bars)
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
    if not equity_market_bars:
        source_status.append({"name": "Nasdaq equity OHLCV", "status": "manual-placeholder", "latest": "daily equity market-structure feeds unavailable"})
    if not lppl_bars:
        source_status.append({"name": "Global LPPL index OHLCV", "status": "manual-placeholder", "latest": "global index replay feeds unavailable"})
    if option_open_interest is None:
        source_status.append({"name": "Cboe SPY option open interest", "status": "manual-placeholder", "latest": "option OI snapshot unavailable"})
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
        "conclusionSourceQuality": dict(CONCLUSION_SOURCE_QUALITY),
        "curve": curve,
        "decomposition": build_decomposition(indicators, acm=acm, fomc_projection=fomc_projection),
        "fedPath": build_fed_path(indicators),
        "groups": groups,
        "conclusionAudit": conclusion_audit,
        "macroLiquidity": macro_liquidity,
        "macroLiquidityEquity": macro_liquidity_equity,
        "spyEarlyWarning": spy_early_warning,
        "equityShortTermRisk": equity_short_term_risk,
        "globalLpplRisk": global_lppl_risk,
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


def build_global_lppl_risk_index(
    *,
    market_bars: dict[str, list[MarketDailyBar]] | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    bars_by_symbol = normalize_market_bars(market_bars or {})
    index_rows = build_global_lppl_index_rows(bars_by_symbol, as_of=as_of)
    per_index_history = build_global_lppl_per_index_histories(index_rows, bars_by_symbol)
    index_validation = build_global_lppl_index_validation(index_rows, bars_by_symbol, histories=per_index_history)
    index_rows = apply_global_lppl_index_validation(index_rows, index_validation)
    per_index_backtests = build_global_lppl_per_index_backtests(per_index_history, bars_by_symbol)
    index_rows = attach_global_lppl_per_index_payloads(index_rows, per_index_history, per_index_backtests)
    index_rows = attach_global_lppl_tc_aggregations(index_rows)
    index_rows = attach_global_lppl_forward_signals(index_rows)
    available_rows = [row for row in index_rows if row.get("available") and optional_float(row.get("score")) is not None]
    if not available_rows:
        return unavailable_global_lppl_risk(index_rows, "全球LPPL逐市场评估需要至少一个可回放指数样本; 当前公开日线源不足。")

    latest_date = latest_global_lppl_date(available_rows)
    breadth_confirmation = build_global_lppl_breadth_confirmation(index_rows)
    return global_lppl_payload(
        latest_date=latest_date,
        available_rows=available_rows,
        index_rows=index_rows,
        index_validation=index_validation,
        per_index_history=per_index_history,
        per_index_backtests=per_index_backtests,
        breadth_confirmation=breadth_confirmation,
    )


def build_global_lppl_index_rows(
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    *,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    return [
        global_lppl_index_row(spec, bars_by_symbol.get(str(spec["symbol"]).upper(), []), as_of=as_of)
        for spec in GLOBAL_LPPL_INDEX_SPECS
    ]


def latest_global_lppl_date(available_rows: list[dict[str, Any]]) -> date:
    dated_rows = [
        date.fromisoformat(str(row["asOf"]))
        for row in available_rows
        if parse_payload_date(row.get("asOf"))
    ]
    return max(dated_rows) if dated_rows else date.today()


def global_lppl_summary(available_rows: list[dict[str, Any]], index_rows: list[dict[str, Any]]) -> str:
    high_risk_count = sum(
        1
        for row in available_rows
        if (optional_float(row.get("score")) or 0.0) >= GLOBAL_LPPL_ALERT_THRESHOLD
    )
    nearest = min(
        (
            int(days)
            for row in available_rows
            for days in [optional_float(row.get("daysToCritical"))]
            if days is not None
        ),
        default=None,
    )
    leaders = sorted(
        (
            (optional_float(row.get("score")) or 0.0, str(row.get("symbol") or ""))
            for row in available_rows
        ),
        reverse=True,
    )[:3]
    leader_text = ", ".join(f"{symbol} {score:.0f}" for score, symbol in leaders if symbol)
    forward_rows = [
        (
            optional_float((row.get("forwardSignal") or {}).get("score")) or 0.0,
            str(row.get("symbol") or ""),
        )
        for row in available_rows
        if isinstance(row.get("forwardSignal"), dict) and (row.get("forwardSignal") or {}).get("available")
    ]
    forward_count = sum(1 for score, _symbol in forward_rows if score >= GLOBAL_LPPL_ALERT_THRESHOLD)
    forward_leaders = sorted(forward_rows, reverse=True)[:3]
    forward_text = ", ".join(f"{symbol} {score:.0f}" for score, symbol in forward_leaders if symbol)
    breadth = build_global_lppl_breadth_confirmation(index_rows)
    breadth_text = (
        f" 市场宽度{breadth.get('riskCount')}/{breadth.get('sampleSize')}个风险, "
        f"加权{breadth.get('weightedRiskSharePct')}%。"
        if breadth.get("available")
        else ""
    )
    return (
        f"LPPL逐市场独立评估; "
        f"{high_risk_count}/{len(available_rows)}个可用指数处于风险阈值上方"
        + (f", 当前较高: {leader_text}" if leader_text else "")
        + (f", 最近临界窗口约{nearest}天。" if nearest is not None else "。")
        + (f" 前瞻压力{forward_count}/{len(available_rows)}个市场高于阈值" + (f", 领先: {forward_text}。" if forward_text else "。") if forward_rows else "")
        + breadth_text
        + f" 不计算混合综合分, 图表和回测按{len(index_rows)}个市场分别展示。"
    )


def global_lppl_payload(
    *,
    latest_date: date,
    available_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
    index_validation: dict[str, Any],
    per_index_history: dict[str, Any],
    per_index_backtests: dict[str, Any],
    breadth_confirmation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "available": True,
        "title": "Global LPPL Risk · 全球指数泡沫临界风险",
        "score": None,
        "scoreUse": "independent",
        "regime": "Per-Index",
        "regimeCn": "逐市场",
        "asOf": latest_date.isoformat(),
        "summary": global_lppl_summary(available_rows, index_rows),
        "method": "LPPL grid search over constrained tc/m/omega with linear least-squares fit; each market is scored, charted, and backtested separately.",
        "indices": index_rows,
        "indexValidation": index_validation,
        "breadthConfirmation": breadth_confirmation,
        "history": {
            "available": False,
            "points": [],
            "summary": "Top-level aggregate LPPL history is disabled; use perIndexHistory or indices[].history.",
        },
        "backtest": {
            "available": False,
            "sampleSize": 0,
            "threshold": GLOBAL_LPPL_ALERT_THRESHOLD,
            "horizonTests": [],
            "summary": "Top-level aggregate LPPL backtest is disabled; use perIndexBacktests or indices[].backtest.",
        },
        "perIndexHistory": per_index_history,
        "perIndexBacktests": per_index_backtests,
        "lookAheadGuard": {
            "dataThrough": latest_date.isoformat(),
            "scoreInputs": "Only same-day or earlier daily OHLCV bars are used. Forward drawdowns are audit-only per-market backtest outputs.",
            "scoreUse": "independent; not included in equityShortTermRisk.",
        },
    }


def build_global_lppl_breadth_confirmation(index_rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [
        row
        for row in index_rows
        if isinstance(row, dict) and row.get("available") and optional_float(row.get("score")) is not None
    ]
    if not available:
        return {
            "available": False,
            "sampleSize": 0,
            "riskCount": 0,
            "riskSharePct": 0.0,
            "weightedRiskSharePct": 0.0,
            "forwardRiskCount": 0,
            "clipLockCount": 0,
            "regime": "Unavailable",
            "regimeCn": "不可用",
            "summary": "LPPL breadth unavailable; no current market rows with scores.",
        }
    risk_rows = [
        row
        for row in available
        if (optional_float(row.get("score")) or 0.0) >= GLOBAL_LPPL_ALERT_THRESHOLD
    ]
    forward_risk_rows = [
        row
        for row in available
        if isinstance(row.get("forwardSignal"), dict)
        and (row.get("forwardSignal") or {}).get("available")
        and (optional_float((row.get("forwardSignal") or {}).get("score")) or 0.0) >= GLOBAL_LPPL_ALERT_THRESHOLD
    ]
    clip_lock_count = sum(
        1
        for row in available
        if isinstance(row.get("clipState"), dict) and bool((row.get("clipState") or {}).get("clipLock"))
    )
    validated_count = sum(
        1
        for row in available
        if optional_float(row.get("effectiveWeightMultiplier")) is not None
        and (optional_float(row.get("effectiveWeightMultiplier")) or 0.0) >= 0.75
    )
    total_weight = sum(max(0.0, optional_float(row.get("weight")) or 0.0) for row in available)
    risk_weight = sum(max(0.0, optional_float(row.get("weight")) or 0.0) for row in risk_rows)
    risk_share = 100 * len(risk_rows) / max(1, len(available))
    weighted_risk_share = 100 * risk_weight / total_weight if total_weight > 0 else risk_share
    if weighted_risk_share >= 50 or len(risk_rows) >= 4:
        regime, regime_cn = "Broad Risk", "宽度风险"
    elif len(risk_rows) >= 2 or clip_lock_count >= 2:
        regime, regime_cn = "Clustered Watch", "集群观察"
    elif len(risk_rows) >= 1 or len(forward_risk_rows) >= 1:
        regime, regime_cn = "Narrow Watch", "局部观察"
    else:
        regime, regime_cn = "Quiet", "宽度平静"
    leaders = ", ".join(str(row.get("symbol") or "") for row in risk_rows[:3] if row.get("symbol"))
    return {
        "available": True,
        "sampleSize": len(available),
        "riskCount": len(risk_rows),
        "riskSharePct": round(risk_share, 1),
        "weightedRiskSharePct": round(weighted_risk_share, 1),
        "forwardRiskCount": len(forward_risk_rows),
        "clipLockCount": clip_lock_count,
        "validatedCount": validated_count,
        "regime": regime,
        "regimeCn": regime_cn,
        "leaders": [str(row.get("symbol") or "") for row in risk_rows[:3] if row.get("symbol")],
        "summary": (
            f"LPPL breadth {len(risk_rows)}/{len(available)} markets above raw threshold"
            f"{f' ({leaders})' if leaders else ''}; weighted breadth {weighted_risk_share:.1f}%, "
            f"forward risk {len(forward_risk_rows)}, CLIP locks {clip_lock_count}."
        ),
    }


def unavailable_global_lppl_risk(index_rows: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "title": "Global LPPL Risk · 全球指数泡沫临界风险",
        "score": None,
        "scoreUse": "independent",
        "regime": "Unavailable",
        "regimeCn": "不可用",
        "asOf": "",
        "summary": reason,
        "method": "LPPL grid search over constrained tc/m/omega with linear least-squares fit.",
        "indices": index_rows,
        "indexValidation": {"available": False, "rows": [], "summary": reason},
        "breadthConfirmation": {
            "available": False,
            "sampleSize": 0,
            "riskCount": 0,
            "riskSharePct": 0.0,
            "weightedRiskSharePct": 0.0,
            "forwardRiskCount": 0,
            "clipLockCount": 0,
            "regime": "Unavailable",
            "regimeCn": "不可用",
            "summary": reason,
        },
        "history": {"available": False, "points": [], "summary": "Top-level aggregate LPPL history is disabled; use per-index histories."},
        "backtest": {"available": False, "sampleSize": 0, "threshold": GLOBAL_LPPL_ALERT_THRESHOLD, "horizonTests": [], "summary": "Top-level aggregate LPPL backtest is disabled; use per-index backtests."},
        "perIndexHistory": {},
        "perIndexBacktests": {},
        "lookAheadGuard": {"scoreUse": "independent; not included in equityShortTermRisk."},
    }


def global_lppl_index_row(
    spec: dict[str, Any],
    bars: list[MarketDailyBar],
    *,
    as_of: date | None = None,
    fast: bool = False,
) -> dict[str, Any]:
    symbol = str(spec.get("symbol") or "").upper()
    clean = normalize_market_bars({symbol: bars}).get(symbol, [])
    target_index = bar_index_at_or_before(clean, as_of) if as_of else (len(clean) - 1 if clean else None)
    if target_index is None or target_index + 1 < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {
            "symbol": symbol,
            "name": str(spec.get("name") or symbol),
            "region": str(spec.get("region") or ""),
            "available": False,
            "score": None,
            "confidence": 0.0,
            "status": "missing",
            "statusCn": "缺失",
            "criticalDate": None,
            "daysToCritical": None,
            "fitR2": None,
            "windowDays": None,
            "observations": len(clean),
            "source": str(spec.get("source") or ""),
            "sourceSymbol": str(spec.get("sourceSymbol") or symbol),
            "sourceQuality": str(spec.get("sourceQuality") or "low"),
            "reason": "source unavailable or sample shorter than LPPL minimum window",
        }
    fit = fit_global_lppl_signal(clean[: target_index + 1], fast=fast)
    latest = clean[target_index]
    if not fit.get("available"):
        return {
            "symbol": symbol,
            "name": str(spec.get("name") or symbol),
            "region": str(spec.get("region") or ""),
            "available": False,
            "score": None,
            "confidence": 0.0,
            "status": "missing",
            "statusCn": "缺失",
            "criticalDate": None,
            "daysToCritical": None,
            "fitR2": None,
            "windowDays": None,
            "observations": target_index + 1,
            "source": str(spec.get("source") or ""),
            "sourceSymbol": str(spec.get("sourceSymbol") or symbol),
            "sourceQuality": str(spec.get("sourceQuality") or "low"),
            "asOf": latest.date.isoformat(),
            "reason": str(fit.get("reason") or "LPPL fit unavailable"),
        }
    score = bounded_score(float(fit["score"]))
    confidence = max(0.0, min(1.0, float(fit.get("confidence") or 0.0)))
    status, status_cn = global_lppl_status(score, confidence)
    days_to_critical = int(fit["daysToCritical"])
    critical_date = latest.date + timedelta(days=days_to_critical)
    return {
        "symbol": symbol,
        "name": str(spec.get("name") or symbol),
        "region": str(spec.get("region") or ""),
        "available": True,
        "score": round(score, 1),
        "confidence": round(confidence, 2),
        "status": status,
        "statusCn": status_cn,
        "criticalDate": critical_date.isoformat(),
        "daysToCritical": days_to_critical,
        "daysToCriticalRange": fit.get("daysToCriticalRange"),
        "fitR2": round(float(fit["fitR2"]), 3),
        "fitSse": round(float(fit.get("fitSse") or 0.0), 6),
        "lpplImprovementPct": round(float(fit.get("lpplImprovementPct") or 0.0), 1),
        "oscillationCount": round(float(fit.get("oscillationCount") or 0.0), 2),
        "passesLpplCoreDiagnostics": bool(fit.get("passesLpplCoreDiagnostics")),
        "passesLpplDiagnostics": bool(fit.get("passesLpplDiagnostics")),
        "residualDiagnostics": fit.get("residualDiagnostics"),
        "fitEnsemble": fit.get("fitEnsemble"),
        "windowDays": int(fit["windowDays"]),
        "windowDaysRange": fit.get("windowDaysRange"),
        "selectionBasis": str(fit.get("selectionBasis") or "fit_quality"),
        "observations": target_index + 1,
        "asOf": latest.date.isoformat(),
        "source": str(spec.get("source") or ""),
        "sourceSymbol": str(spec.get("sourceSymbol") or symbol),
        "sourceQuality": str(spec.get("sourceQuality") or "low"),
        "weight": float(spec.get("weight") or 0.0),
        "trailingReturn63d": pct_metric(fit.get("trailingReturn63d")),
        "acceleration": pct_metric(fit.get("acceleration")),
        "bubbleCoefficient": round(float(fit.get("bubbleCoefficient") or 0.0), 4),
        "oscillationAmplitude": round(float(fit.get("oscillationAmplitude") or 0.0), 4),
        "reason": str(fit.get("reason") or ""),
    }


def fit_global_lppl_signal(bars: list[MarketDailyBar], *, fast: bool = False) -> dict[str, Any]:
    clean = [bar for bar in bars if bar.close > 0 and math.isfinite(bar.close)]
    if len(clean) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {"available": False, "reason": "sample shorter than LPPL minimum window"}
    windows = (
        [min(GLOBAL_LPPL_DEFAULT_WINDOW, len(clean))]
        if fast
        else [window for window in GLOBAL_LPPL_SIGNAL_WINDOWS if len(clean) >= window]
    )
    fits = []
    for window in windows:
        sample = clean[-window:]
        fit = fit_lppl_window(sample, fast=fast)
        if fit.get("available"):
            fits.append(fit)
    if not fits:
        return {"available": False, "reason": "bounded LPPL fit did not converge"}
    selected = select_lppl_fit_candidate(fits)
    selected["fitEnsemble"] = build_lppl_fit_ensemble(fits, total_fit_count=len(windows), attempted_windows=windows)
    return selected


def select_lppl_fit_candidate(fits: list[dict[str, Any]]) -> dict[str, Any]:
    available = [fit for fit in fits if fit.get("available")]
    if not available:
        return {"available": False, "reason": "bounded LPPL fit did not converge"}
    best = dict(
        max(
            available,
            key=lambda item: (
                bool(item.get("passesLpplCoreDiagnostics")),
                bool(item.get("passesLpplDiagnostics")),
                float(item.get("fitR2") or 0.0),
                -(float(item.get("fitSse") or 0.0)),
                float(item.get("confidence") or 0.0),
                float(item.get("score") or 0.0),
            ),
        )
    )
    days_values = sorted({
        int(days)
        for fit in available
        for days in [optional_float(fit.get("daysToCritical"))]
        if days is not None
    })
    if days_values:
        best["daysToCriticalRange"] = {"min": min(days_values), "max": max(days_values), "values": days_values}
    window_values = sorted({
        int(window)
        for fit in available
        for window in [optional_float(fit.get("windowDays"))]
        if window is not None
    })
    if window_values:
        best["windowDaysRange"] = {"min": min(window_values), "max": max(window_values), "values": window_values}
    best["selectionBasis"] = "fit_quality"
    return best


def build_lppl_fit_ensemble(
    fits: list[dict[str, Any]],
    *,
    total_fit_count: int,
    attempted_windows: list[int],
) -> dict[str, Any]:
    available = [fit for fit in fits if fit.get("available")]
    valid_fit_count = len(available)
    if not available:
        return {
            "available": False,
            "totalFitCount": total_fit_count,
            "validFitCount": 0,
            "validFitRatioPct": 0.0,
            "residualPassRatioPct": 0.0,
            "windowDays": attempted_windows,
            "windowAgreement": "unavailable",
            "optimizerAgreement": "not-modeled",
            "summary": "LPPL ensemble produced no valid fits.",
        }
    lead_days = sorted(
        int(days)
        for fit in available
        for days in [optional_float(fit.get("daysToCritical"))]
        if days is not None
    )
    window_days = sorted(
        int(window)
        for fit in available
        for window in [optional_float(fit.get("windowDays"))]
        if window is not None
    )
    q20 = int(round(lppl_percentile(lead_days, 0.20))) if lead_days else None
    q50 = int(round(lppl_percentile(lead_days, 0.50))) if lead_days else None
    q80 = int(round(lppl_percentile(lead_days, 0.80))) if lead_days else None
    tc_window_days = (q80 - q20) if q20 is not None and q80 is not None else None
    residual_pass_count = sum(1 for fit in available if fit.get("passesLpplDiagnostics") is True)
    residual_pass_ratio = 100 * residual_pass_count / max(1, valid_fit_count)
    if tc_window_days is None:
        agreement = "unavailable"
    elif tc_window_days <= 30:
        agreement = "tight"
    elif tc_window_days <= 75:
        agreement = "moderate"
    else:
        agreement = "scattered"
    return {
        "available": True,
        "totalFitCount": int(total_fit_count),
        "validFitCount": int(valid_fit_count),
        "validFitRatioPct": round(100 * valid_fit_count / max(1, total_fit_count), 1),
        "residualPassRatioPct": round(residual_pass_ratio, 1),
        "windowDays": window_days,
        "attemptedWindowDays": list(attempted_windows),
        "tcLeadDaysQ20": q20,
        "tcLeadDaysMedian": q50,
        "tcLeadDaysQ80": q80,
        "tcWindowDays": tc_window_days,
        "windowAgreement": agreement,
        "optimizerAgreement": "not-modeled",
        "summary": (
            f"{valid_fit_count}/{total_fit_count} LPPL windows valid; "
            f"tc lead 20/50/80% = {q20}/{q50}/{q80}D; residual pass {residual_pass_ratio:.0f}%."
        ),
    }


def fit_lppl_window(sample: list[MarketDailyBar], *, fast: bool = False) -> dict[str, Any]:
    closes = [bar.close for bar in sample if bar.close > 0]
    if len(closes) != len(sample) or len(sample) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {"available": False, "reason": "invalid close values"}
    ys = [math.log(value) for value in closes]
    n = len(sample)
    tc_offsets = (25, 60, 130) if fast else (15, 25, 40, 60, 90, 130, 170)
    m_values = (0.35, 0.55, 0.75) if fast else (0.2, 0.35, 0.5, 0.65, 0.8)
    omega_values = (7.0, 10.0, 12.0) if fast else (6.0, 8.0, 10.0, 12.0)
    candidates: list[dict[str, Any]] = []
    for tc_offset in tc_offsets:
        tc = (n - 1) + tc_offset
        for m in m_values:
            for omega in omega_values:
                rows = []
                valid = True
                for t in range(n):
                    distance = tc - t
                    if distance <= 0:
                        valid = False
                        break
                    power = distance ** m
                    log_distance = math.log(distance)
                    rows.append([1.0, power, power * math.cos(omega * log_distance), power * math.sin(omega * log_distance)])
                if not valid:
                    continue
                coefficients = linear_least_squares(rows, ys)
                if coefficients is None:
                    continue
                fitted = [sum(coef * value for coef, value in zip(coefficients, row)) for row in rows]
                fit_r2 = regression_r_squared(ys, fitted)
                if fit_r2 is None:
                    continue
                fit_sse = sum((actual - predicted) ** 2 for actual, predicted in zip(ys, fitted))
                power_rows = [[1.0, row[1]] for row in rows]
                power_coefficients = linear_least_squares(power_rows, ys)
                if power_coefficients is None:
                    continue
                power_fitted = [sum(coef * value for coef, value in zip(power_coefficients, row)) for row in power_rows]
                power_sse = sum((actual - predicted) ** 2 for actual, predicted in zip(ys, power_fitted))
                lppl_improvement_pct = 0.0 if power_sse <= 1e-12 else max(0.0, 100.0 * (power_sse - fit_sse) / power_sse)
                oscillation_count = lppl_oscillation_count(
                    tc=tc,
                    omega=omega,
                    start_index=0,
                    end_index=n - 1,
                )
                residuals = [actual - predicted for actual, predicted in zip(ys, fitted)]
                residual_diagnostics = lppl_residual_diagnostics(residuals)
                bubble_coefficient = coefficients[1]
                oscillation = math.sqrt(coefficients[2] ** 2 + coefficients[3] ** 2)
                trailing_63 = closes[-1] / closes[max(0, n - 64)] - 1 if n >= 65 else 0.0
                recent_63 = closes[-1] / closes[-64] - 1 if n >= 128 else trailing_63
                prior_63 = closes[-64] / closes[-127] - 1 if n >= 128 else 0.0
                acceleration = recent_63 - prior_63
                fit_score = bounded_score(100 * fit_r2)
                critical_score = bounded_score(100 * (1 - (tc_offset - 10) / 170))
                trend_score = risk_linear(trailing_63, 0.04, 0.35)
                acceleration_score = risk_linear(acceleration, 0.0, 0.12)
                coherent_bubble = bubble_coefficient < 0 and acceleration > 0 and trailing_63 > 0.03
                valid_oscillation_count = 2.0 <= oscillation_count <= 10.0
                passes_lppl_core_diagnostics = (
                    coherent_bubble
                    and lppl_improvement_pct >= 5.0
                    and valid_oscillation_count
                )
                passes_lppl_diagnostics = passes_lppl_core_diagnostics and bool(residual_diagnostics.get("meanReverting"))
                raw_score = 0.38 * fit_score + 0.24 * critical_score + 0.18 * trend_score + 0.20 * acceleration_score
                if not passes_lppl_core_diagnostics:
                    raw_score = min(raw_score, 35.0)
                oscillation_denominator = abs(oscillation) + abs(bubble_coefficient)
                oscillation_balance = abs(oscillation) / oscillation_denominator if oscillation_denominator > 1e-6 else 0.0
                confidence = (
                    0.45 * max(0.0, min(1.0, fit_r2))
                    + 0.25 * (critical_score / 100)
                    + 0.20 * (acceleration_score / 100)
                    + 0.10 * min(1.0, oscillation_balance)
                )
                if not passes_lppl_diagnostics:
                    confidence = min(confidence, 0.45)
                candidate = {
                    "available": True,
                    "score": bounded_score(raw_score),
                    "confidence": max(0.0, min(1.0, confidence)),
                    "fitR2": fit_r2,
                    "fitSse": fit_sse,
                    "powerLawSse": power_sse,
                    "lpplImprovementPct": lppl_improvement_pct,
                    "oscillationCount": oscillation_count,
                    "passesLpplCoreDiagnostics": passes_lppl_core_diagnostics,
                    "residualDiagnostics": residual_diagnostics,
                    "passesLpplDiagnostics": passes_lppl_diagnostics,
                    "daysToCritical": tc_offset,
                    "windowDays": n,
                    "bubbleCoefficient": bubble_coefficient,
                    "oscillationAmplitude": oscillation,
                    "trailingReturn63d": trailing_63,
                    "acceleration": acceleration,
                    "reason": (
                        f"coherent LPPL acceleration; power-law improvement {lppl_improvement_pct:.1f}%, "
                        f"{oscillation_count:.1f} log-periodic oscillations, residual mean reversion supported"
                        if passes_lppl_diagnostics
                        else f"LPPL core shape strong but residual mean reversion is weak: power-law improvement {lppl_improvement_pct:.1f}%, "
                        f"{oscillation_count:.1f} oscillations"
                        if passes_lppl_core_diagnostics
                        else f"LPPL diagnostics weak: power-law improvement {lppl_improvement_pct:.1f}%, "
                        f"{oscillation_count:.1f} oscillations, residual mean-reverting={bool(residual_diagnostics.get('meanReverting'))}"
                    ),
                }
                candidates.append(candidate)
    return select_lppl_fit_candidate(candidates) if candidates else {"available": False, "reason": "bounded LPPL grid produced no stable fit"}


def lppl_oscillation_count(*, tc: float, omega: float, start_index: int, end_index: int) -> float:
    start_distance = tc - start_index
    end_distance = tc - end_index
    if start_distance <= 0 or end_distance <= 0 or omega <= 0:
        return 0.0
    return max(0.0, omega / (2 * math.pi) * math.log(start_distance / end_distance))


def lppl_residual_diagnostics(residuals: list[float]) -> dict[str, Any]:
    clean = [value for value in residuals if math.isfinite(value)]
    if len(clean) < 20:
        return {"available": False, "meanReverting": False, "lag1Autocorrelation": None, "residualStd": None}
    mean_value = sum(clean) / len(clean)
    centered = [value - mean_value for value in clean]
    variance = sum(value * value for value in centered)
    residual_std = math.sqrt(variance / max(1, len(centered) - 1))
    if residual_std <= 7.5e-4:
        return {
            "available": True,
            "meanReverting": True,
            "adfProxyPass": True,
            "kpssProxyPass": True,
            "ljungBoxProxyPass": True,
            "passRatioPct": 100.0,
            "method": "low-variance residual proxy for ADF/KPSS/Ljung-Box checks",
            "lag1Autocorrelation": 0.0,
            "residualStd": round(residual_std, 6),
            "lowResidualVariance": True,
        }
    lag_num = sum(centered[index - 1] * centered[index] for index in range(1, len(centered)))
    lag_den = sum(value * value for value in centered[:-1])
    lag1 = lag_num / lag_den if lag_den > 1e-12 else 0.0
    sign_changes = sum(1 for index in range(1, len(centered)) if centered[index - 1] * centered[index] < 0)
    sign_change_ratio = sign_changes / max(1, len(centered) - 1)
    adf_proxy_pass = abs(lag1) < 0.98 and sign_change_ratio >= 0.03
    kpss_proxy_pass = abs(lag1) < 0.95 or residual_std <= 0.01
    ljung_box_proxy_pass = abs(lag1) < 0.90
    pass_ratio = 100 * sum((adf_proxy_pass, kpss_proxy_pass, ljung_box_proxy_pass)) / 3
    mean_reverting = adf_proxy_pass and kpss_proxy_pass
    return {
        "available": True,
        "meanReverting": mean_reverting,
        "adfProxyPass": adf_proxy_pass,
        "kpssProxyPass": kpss_proxy_pass,
        "ljungBoxProxyPass": ljung_box_proxy_pass,
        "passRatioPct": round(pass_ratio, 1),
        "method": "lag-1 autocorrelation and sign-change proxy for ADF/KPSS/Ljung-Box checks",
        "lag1Autocorrelation": round(lag1, 4),
        "residualStd": round(residual_std, 6),
        "signChangeRatio": round(sign_change_ratio, 4),
        "lowResidualVariance": False,
    }


def linear_least_squares(rows: list[list[float]], ys: list[float]) -> list[float] | None:
    if not rows or len(rows) != len(ys):
        return None
    width = len(rows[0])
    normal = [[0.0 for _ in range(width)] for _ in range(width)]
    target = [0.0 for _ in range(width)]
    for row, y in zip(rows, ys):
        if len(row) != width or not all(math.isfinite(value) for value in row):
            return None
        for i in range(width):
            target[i] += row[i] * y
            for j in range(width):
                normal[i][j] += row[i] * row[j]
    return solve_linear_system(normal, target)


def solve_linear_system(matrix: list[list[float]], target: list[float]) -> list[float] | None:
    n = len(target)
    augmented = [list(row) + [target[index]] for index, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row_index: abs(augmented[row_index][col]))
        if abs(augmented[pivot][col]) < 1e-10:
            return None
        if pivot != col:
            augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        for j in range(col, n + 1):
            augmented[col][j] /= pivot_value
        for row_index in range(n):
            if row_index == col:
                continue
            factor = augmented[row_index][col]
            if factor == 0:
                continue
            for j in range(col, n + 1):
                augmented[row_index][j] -= factor * augmented[col][j]
    return [augmented[row][n] for row in range(n)]


def regression_r_squared(actual: list[float], fitted: list[float]) -> float | None:
    if len(actual) != len(fitted) or len(actual) < 3:
        return None
    mean_y = sum(actual) / len(actual)
    total = sum((value - mean_y) ** 2 for value in actual)
    if total <= 0:
        return None
    residual = sum((value - fit) ** 2 for value, fit in zip(actual, fitted))
    return max(0.0, min(1.0, 1 - residual / total))


def build_global_lppl_per_index_histories(
    index_rows: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
) -> dict[str, Any]:
    histories: dict[str, Any] = {}
    for row in index_rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        histories[symbol] = build_global_lppl_single_index_history(row, bars_by_symbol.get(symbol, []))
    return histories


def build_global_lppl_single_index_history(
    index_row: dict[str, Any],
    bars: list[MarketDailyBar],
) -> dict[str, Any]:
    symbol = str(index_row.get("symbol") or "").upper()
    clean = normalize_market_bars({symbol: bars}).get(symbol, [])
    if len(clean) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {"available": False, "symbol": symbol, "points": [], "summary": "source unavailable or sample shorter than LPPL minimum window"}
    score_points = build_single_index_lppl_history_points(symbol, clean)
    if not score_points:
        return {"available": False, "symbol": symbol, "points": [], "summary": "LPPL history replay produced no valid fit points"}
    first_index = bar_index_at_or_before(clean, parse_lppl_point_date(score_points[0].get("date")) or clean[0].date)
    base_close = clean[first_index if first_index is not None else 0].close
    points: list[dict[str, Any]] = []
    for point in score_points:
        point_date = parse_lppl_point_date(point.get("date"))
        bar_index = bar_index_at_or_before(clean, point_date) if point_date else None
        if bar_index is None:
            continue
        close = clean[bar_index].close
        enriched = {
            "date": clean[bar_index].date.isoformat(),
            "score": point["score"],
            "close": round(close, 2),
            "indexedClose": round(100 * close / base_close, 2) if base_close > 0 else None,
        }
        for key in (
            "criticalDate",
            "daysToCritical",
            "passesLpplCoreDiagnostics",
            "passesLpplDiagnostics",
            "lpplImprovementPct",
            "oscillationCount",
        ):
            if key in point:
                enriched[key] = point[key]
        points.append(enriched)
    if len(points) < 2:
        return {"available": False, "symbol": symbol, "points": points, "summary": "LPPL history replay has fewer than two chartable points"}
    clip_state = build_lppl_clip_state(points)
    return {
        "available": True,
        "symbol": symbol,
        "name": str(index_row.get("name") or symbol),
        "sourceSymbol": str(index_row.get("sourceSymbol") or symbol),
        "summary": f"{symbol} LPPL replay; risk score and indexed own-market price are shown on separate axes.",
        "points": points,
        "dateRange": {"start": points[0]["date"], "end": points[-1]["date"]},
        "clipState": clip_state,
    }


def parse_lppl_point_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def build_lppl_clip_state(points: list[dict[str, Any]], *, lookback: int = 20) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        point_date = parse_lppl_point_date(point.get("date"))
        critical_date = parse_lppl_point_date(point.get("criticalDate"))
        if point_date is None or critical_date is None:
            continue
        observations.append(
            {
                "date": point_date,
                "criticalDate": critical_date,
                "score": optional_float(point.get("score")),
                "passesCore": bool(point.get("passesLpplCoreDiagnostics")),
            }
        )
    if len(observations) < 5:
        return {
            "available": False,
            "clipLock": False,
            "status": "insufficient",
            "statusCn": "样本不足",
            "sampleSize": len(observations),
            "summary": "CLIP requires at least five replay points with critical dates.",
        }
    recent = observations[-max(5, lookback):]
    critical_ordinals = sorted(item["criticalDate"].toordinal() for item in recent)
    q20 = lppl_percentile(critical_ordinals, 0.20)
    q50 = lppl_percentile(critical_ordinals, 0.50)
    q80 = lppl_percentile(critical_ordinals, 0.80)
    tc_window_days = max(0, int(round(q80 - q20)))
    latest_observation = max(item["date"] for item in recent)
    median_lead_days = int(round(q50 - latest_observation.toordinal()))
    core_pass_ratio = sum(1 for item in recent if item["passesCore"]) / len(recent)
    clip_lock = tc_window_days <= 30 and 5 <= median_lead_days <= 180 and core_pass_ratio >= 0.50
    converging = tc_window_days <= 60 and 5 <= median_lead_days <= 252 and core_pass_ratio >= 0.35
    if clip_lock:
        status, status_cn = "locked", "CLIP锁定"
    elif converging:
        status, status_cn = "converging", "CLIP收敛"
    elif median_lead_days < 0:
        status, status_cn = "expired", "临界已过"
    else:
        status, status_cn = "scattered", "临界分散"
    return {
        "available": True,
        "clipLock": clip_lock,
        "status": status,
        "statusCn": status_cn,
        "sampleSize": len(recent),
        "lookback": max(5, lookback),
        "tcMedian": date.fromordinal(int(round(q50))).isoformat(),
        "tcQ20": date.fromordinal(int(round(q20))).isoformat(),
        "tcQ80": date.fromordinal(int(round(q80))).isoformat(),
        "tcWindowDays": tc_window_days,
        "medianLeadDays": median_lead_days,
        "corePassRatio": round(core_pass_ratio, 3),
        "summary": (
            f"CLIP {status_cn}: recent tc 20-80% window {tc_window_days} days, "
            f"median lead {median_lead_days} days, core pass {core_pass_ratio:.0%}."
        ),
    }


def lppl_percentile(sorted_values: list[int], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pct = max(0.0, min(1.0, percentile))
    position = (len(sorted_values) - 1) * pct
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return float(sorted_values[lower_index])
    weight = position - lower_index
    return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight


def build_global_lppl_per_index_backtests(
    histories: dict[str, Any],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
) -> dict[str, Any]:
    backtests: dict[str, Any] = {}
    for symbol, history in histories.items():
        points = history.get("points", []) if isinstance(history, dict) else []
        backtests[symbol] = build_global_lppl_backtest(points, bars_by_symbol.get(symbol, []), symbol=symbol)
    return backtests


def attach_global_lppl_per_index_payloads(
    index_rows: list[dict[str, Any]],
    histories: dict[str, Any],
    backtests: dict[str, Any],
) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in index_rows:
        enriched = dict(row)
        symbol = str(enriched.get("symbol") or "").upper()
        enriched["history"] = histories.get(symbol, {"available": False, "symbol": symbol, "points": []})
        enriched["backtest"] = backtests.get(symbol, {"available": False, "sampleSize": 0, "horizonTests": []})
        history_clip = enriched["history"].get("clipState") if isinstance(enriched.get("history"), dict) else None
        if isinstance(history_clip, dict):
            enriched["clipState"] = history_clip
        enriched_rows.append(enriched)
    return enriched_rows


def attach_global_lppl_tc_aggregations(index_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in index_rows:
        enriched = dict(row)
        enriched["tcAggregation"] = build_global_lppl_tc_aggregation(enriched)
        enriched_rows.append(enriched)
    return enriched_rows


def build_global_lppl_tc_aggregation(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper()
    ensemble = row.get("fitEnsemble") if isinstance(row.get("fitEnsemble"), dict) else {}
    as_of_raw = row.get("asOf")
    try:
        as_of_date = date.fromisoformat(str(as_of_raw))
    except (TypeError, ValueError):
        as_of_date = None
    if not ensemble.get("available") or as_of_date is None:
        return {
            "available": False,
            "symbol": symbol,
            "summary": "LPPL tc aggregation unavailable; fit ensemble or asOf date missing.",
        }

    def lead_date(key: str) -> str | None:
        lead = optional_float(ensemble.get(key))
        if lead is None:
            return None
        return (as_of_date + timedelta(days=int(round(lead)))).isoformat()

    q20 = lead_date("tcLeadDaysQ20")
    median = lead_date("tcLeadDaysMedian")
    q80 = lead_date("tcLeadDaysQ80")
    return {
        "available": True,
        "symbol": symbol,
        "tcQ20": q20,
        "tcMedian": median,
        "tcQ80": q80,
        "tcLeadDaysQ20": ensemble.get("tcLeadDaysQ20"),
        "tcLeadDaysMedian": ensemble.get("tcLeadDaysMedian"),
        "tcLeadDaysQ80": ensemble.get("tcLeadDaysQ80"),
        "tcWindowDays": ensemble.get("tcWindowDays"),
        "validFitCount": ensemble.get("validFitCount"),
        "totalFitCount": ensemble.get("totalFitCount"),
        "validFitRatioPct": ensemble.get("validFitRatioPct"),
        "residualPassRatioPct": ensemble.get("residualPassRatioPct"),
        "windowDays": ensemble.get("windowDays", []),
        "windowAgreement": ensemble.get("windowAgreement") or "",
        "optimizerAgreement": ensemble.get("optimizerAgreement") or "",
        "summary": (
            f"{symbol} tc aggregation {q20 or '--'} / {median or '--'} / {q80 or '--'}; "
            f"{ensemble.get('validFitCount')}/{ensemble.get('totalFitCount')} windows valid."
        ),
    }


def attach_global_lppl_forward_signals(index_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in index_rows:
        enriched = dict(row)
        enriched["forwardSignal"] = build_global_lppl_forward_signal(enriched)
        enriched_rows.append(enriched)
    return enriched_rows


def global_lppl_ensemble_multiplier(row: dict[str, Any]) -> float:
    ensemble = row.get("fitEnsemble") if isinstance(row.get("fitEnsemble"), dict) else {}
    if not ensemble or ensemble.get("available") is not True:
        return 1.0
    valid_ratio = optional_float(ensemble.get("validFitRatioPct"))
    residual_ratio = optional_float(ensemble.get("residualPassRatioPct"))
    valid_ratio = 1.0 if valid_ratio is None else max(0.0, min(1.0, valid_ratio / 100.0))
    residual_ratio = 1.0 if residual_ratio is None else max(0.0, min(1.0, residual_ratio / 100.0))
    agreement = str(ensemble.get("windowAgreement") or "").lower()
    agreement_multiplier = {
        "tight": 1.0,
        "moderate": 0.90,
        "scattered": 0.65,
        "unavailable": 0.80,
    }.get(agreement, 0.85)
    tc_window_days = optional_float(ensemble.get("tcWindowDays"))
    if tc_window_days is None:
        tc_multiplier = 1.0
    elif tc_window_days > 120:
        tc_multiplier = 0.75
    elif tc_window_days > 75:
        tc_multiplier = 0.85
    elif tc_window_days > 45:
        tc_multiplier = 0.93
    else:
        tc_multiplier = 1.0
    valid_multiplier = 0.70 + 0.30 * valid_ratio
    residual_multiplier = 0.60 + 0.40 * residual_ratio
    return round(max(0.45, min(1.0, agreement_multiplier, tc_multiplier, valid_multiplier, residual_multiplier)), 3)


def build_global_lppl_forward_signal(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper()
    model_score = optional_float(row.get("score"))
    if not row.get("available") or model_score is None:
        return {"available": False, "symbol": symbol, "score": None, "regime": "Unavailable", "regimeCn": "不可用", "summary": "LPPL forward signal unavailable."}
    history = row.get("history") if isinstance(row.get("history"), dict) else {}
    history_points = history.get("points", []) if isinstance(history, dict) else []
    score_momentum_5d = lppl_history_score_delta(history_points, 5)
    score_momentum_20d = lppl_history_score_delta(history_points, 20)
    clip_state = row.get("clipState") if isinstance(row.get("clipState"), dict) else history.get("clipState") if isinstance(history, dict) else {}
    clip_lock = bool(clip_state.get("clipLock")) if isinstance(clip_state, dict) else False
    backtest = row.get("backtest") if isinstance(row.get("backtest"), dict) else {}
    validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
    threshold = optional_float(backtest.get("threshold") if isinstance(backtest, dict) else None)
    if threshold is None:
        threshold = optional_float(validation.get("threshold") if isinstance(validation, dict) else None)
    if threshold is None:
        threshold = GLOBAL_LPPL_ALERT_THRESHOLD
    threshold_distance = model_score - threshold
    days_to_critical = optional_float(row.get("daysToCritical"))
    confidence = max(0.0, min(1.0, optional_float(row.get("confidence")) or 0.0))
    validation_multiplier = optional_float(validation.get("effectiveWeightMultiplier")) if isinstance(validation, dict) else None
    if validation_multiplier is None:
        validation_multiplier = optional_float(row.get("effectiveWeightMultiplier"))
    validation_multiplier = max(0.0, min(1.0, validation_multiplier if validation_multiplier is not None else 0.75))
    ensemble_multiplier = global_lppl_ensemble_multiplier(row)
    threshold_pressure = risk_linear(threshold_distance, -15.0, 10.0)
    momentum_pressure = risk_linear(score_momentum_20d if score_momentum_20d is not None else 0.0, -8.0, 12.0)
    critical_pressure = risk_linear(180.0 - days_to_critical, 0.0, 140.0) if days_to_critical is not None else 50.0
    raw_score = (
        0.42 * bounded_score(model_score)
        + 0.22 * threshold_pressure
        + 0.18 * momentum_pressure
        + 0.18 * critical_pressure
    )
    if clip_lock:
        raw_score = min(100.0, raw_score + 8.0)
    elif isinstance(clip_state, dict) and clip_state.get("status") == "converging":
        raw_score = min(100.0, raw_score + 3.0)
    forward_score = bounded_score(
        raw_score
        * (0.65 + 0.35 * validation_multiplier)
        * (0.75 + 0.25 * confidence)
        * ensemble_multiplier
    )
    drivers: list[str] = []
    if threshold_distance >= 0:
        drivers.append("above_threshold")
    elif threshold_distance >= -10:
        drivers.append("near_threshold")
    if score_momentum_20d is not None and score_momentum_20d >= 8:
        drivers.append("rising")
    elif score_momentum_20d is not None and score_momentum_20d <= -8:
        drivers.append("falling")
    if days_to_critical is not None and days_to_critical <= 90:
        drivers.append("critical_window")
    if clip_lock:
        drivers.append("clip_lock")
    if validation_multiplier < 0.75:
        drivers.append("weak_validation")
    if ensemble_multiplier < 0.85:
        drivers.append("weak_ensemble")
    regime, regime_cn = global_lppl_forward_regime(forward_score, score_momentum_20d)
    return {
        "available": True,
        "symbol": symbol,
        "score": round(forward_score, 1),
        "regime": regime,
        "regimeCn": regime_cn,
        "scoreMomentum5d": round(score_momentum_5d, 1) if score_momentum_5d is not None else None,
        "scoreMomentum20d": round(score_momentum_20d, 1) if score_momentum_20d is not None else None,
        "threshold": int(threshold),
        "thresholdDistance": round(threshold_distance, 1),
        "daysToCritical": int(days_to_critical) if days_to_critical is not None else None,
        "clipLock": clip_lock,
        "clipStatus": str(clip_state.get("status") or "") if isinstance(clip_state, dict) else "",
        "validationMultiplier": round(validation_multiplier, 2),
        "ensembleMultiplier": round(ensemble_multiplier, 2),
        "drivers": drivers,
        "summary": global_lppl_forward_summary(symbol, forward_score, regime_cn, score_momentum_20d, threshold_distance, validation_multiplier, ensemble_multiplier),
    }


def lppl_history_score_delta(points: list[dict[str, Any]], lookback: int) -> float | None:
    clean_scores = [
        optional_float(point.get("score"))
        for point in points
        if isinstance(point, dict) and optional_float(point.get("score")) is not None
    ]
    if len(clean_scores) < 2:
        return None
    latest = clean_scores[-1]
    anchor = clean_scores[max(0, len(clean_scores) - 1 - max(1, lookback))]
    return latest - anchor


def global_lppl_forward_regime(score: float, score_momentum_20d: float | None) -> tuple[str, str]:
    if score_momentum_20d is not None and score_momentum_20d <= -8 and score < 60:
        return "Fading", "前瞻降温"
    if score >= 70:
        return "Forward Risk", "前瞻风险"
    if score >= 55 and (score_momentum_20d or 0.0) > 0:
        return "Rising Watch", "前瞻升温"
    if score >= 55:
        return "Watch", "观察"
    return "Quiet", "低前瞻压力"


def global_lppl_forward_summary(
    symbol: str,
    score: float,
    regime_cn: str,
    score_momentum_20d: float | None,
    threshold_distance: float,
    validation_multiplier: float,
    ensemble_multiplier: float,
) -> str:
    momentum_text = "20D动量不足" if score_momentum_20d is None else f"20D动量{score_momentum_20d:+.1f}"
    threshold_text = f"距阈值{threshold_distance:+.1f}"
    validation_text = f"验证权重x{validation_multiplier:.2f}"
    ensemble_text = f"窗口一致性x{ensemble_multiplier:.2f}"
    return f"{symbol} LPPL前瞻压力{score:.1f} ({regime_cn}); {momentum_text}, {threshold_text}, {validation_text}, {ensemble_text}."


def apply_global_lppl_index_validation(
    index_rows: list[dict[str, Any]],
    validation: dict[str, Any],
) -> list[dict[str, Any]]:
    validation_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in validation.get("rows", [])
        if isinstance(row, dict)
    } if isinstance(validation, dict) else {}
    adjusted_rows: list[dict[str, Any]] = []
    for row in index_rows:
        adjusted = dict(row)
        symbol = str(adjusted.get("symbol") or "").upper()
        validation_row = validation_by_symbol.get(symbol)
        if validation_row:
            adjusted["validation"] = validation_row
            adjusted["effectiveWeightMultiplier"] = validation_row.get("effectiveWeightMultiplier")
        elif adjusted.get("available"):
            adjusted["effectiveWeightMultiplier"] = 0.75
        adjusted_rows.append(adjusted)
    return adjusted_rows


def build_global_lppl_index_validation(
    index_rows: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    *,
    histories: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index_row in index_rows:
        if not index_row.get("available"):
            continue
        symbol = str(index_row.get("symbol") or "").upper()
        bars = bars_by_symbol.get(symbol, [])
        history = histories.get(symbol) if isinstance(histories, dict) else None
        history_points = history.get("points") if isinstance(history, dict) and isinstance(history.get("points"), list) else None
        row = build_global_lppl_single_index_validation(index_row, bars, history_points=history_points)
        if row:
            rows.append(row)
    if not rows:
        return {"available": False, "rows": [], "summary": "No index-level LPPL validation samples were available."}
    validated = sum(1 for row in rows if row.get("validationRole") == "validated")
    weak = sum(1 for row in rows if row.get("validationRole") == "weak")
    summary = f"{len(rows)} indices replayed; {validated} validated, {weak} weak by own-market 15D drawdown audit."
    return {"available": True, "rows": rows, "summary": summary}


def build_global_lppl_single_index_validation(
    index_row: dict[str, Any],
    bars: list[MarketDailyBar],
    *,
    drawdown_threshold_pct: float = -2.0,
    history_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    symbol = str(index_row.get("symbol") or "").upper()
    clean = normalize_market_bars({symbol: bars}).get(symbol, [])
    if len(clean) < GLOBAL_LPPL_MIN_OBSERVATIONS + 20:
        return None
    points = history_points if history_points is not None else build_single_index_lppl_history_points(symbol, clean)
    observations = build_global_lppl_validation_observations(points, clean, drawdown_threshold_pct)
    if not observations:
        return None
    calibration_grid = [
        equity_backtest_threshold_test(candidate_threshold, observations, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    recommended = global_lppl_recommended_threshold(calibration_grid, len(observations))
    threshold = int(recommended.get("threshold") or GLOBAL_LPPL_ALERT_THRESHOLD)
    test_15d = equity_backtest_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=15)
    multiplier, role, role_cn = global_lppl_validation_weight(test_15d)
    precision = optional_float(test_15d.get("precision"))
    recall = optional_float(test_15d.get("recall"))
    return {
        "symbol": symbol,
        "sourceSymbol": str(index_row.get("sourceSymbol") or symbol),
        "sampleSize": len(observations),
        "historyPoints": len(points),
        "threshold": threshold,
        "alertDays": int(test_15d.get("alertDays") or 0),
        "truePositives": int(test_15d.get("truePositives") or 0),
        "falsePositives": int(test_15d.get("falsePositives") or 0),
        "precision15d": round(precision, 1) if precision is not None else None,
        "recall15d": round(recall, 1) if recall is not None else None,
        "baseRate15d": test_15d.get("baseRate"),
        "avgMaxDrawdown15dWhenAlert": test_15d.get("avgMaxDrawdownWhenAlert"),
        "avgDrawdownLeadDaysWhenHit": test_15d.get("avgDrawdownLeadDaysWhenHit"),
        "effectiveWeightMultiplier": multiplier,
        "validationRole": role,
        "validationRoleCn": role_cn,
        "summary": global_lppl_validation_summary(symbol, test_15d, multiplier, role_cn),
    }


def build_single_index_lppl_history_points(symbol: str, bars: list[MarketDailyBar]) -> list[dict[str, Any]]:
    if len(bars) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return []
    points: list[dict[str, Any]] = []
    start_index = GLOBAL_LPPL_MIN_OBSERVATIONS - 1
    step = max(1, GLOBAL_LPPL_HISTORY_STEP)
    replay_indices = list(range(start_index, len(bars), step))
    if replay_indices[-1] != len(bars) - 1:
        replay_indices.append(len(bars) - 1)
    spec = {"symbol": symbol, "name": symbol, "region": symbol, "sourceQuality": "validation", "sourceSymbol": symbol}
    for index in replay_indices:
        target = bars[index].date
        row = global_lppl_index_row(spec, bars, as_of=target, fast=True)
        score = optional_float(row.get("score"))
        if row.get("available") and score is not None:
            point = {"date": target.isoformat(), "score": round(bounded_score(score), 1)}
            for key in (
                "criticalDate",
                "daysToCritical",
                "passesLpplCoreDiagnostics",
                "passesLpplDiagnostics",
                "lpplImprovementPct",
                "oscillationCount",
            ):
                if key in row:
                    point[key] = row[key]
            points.append(point)
    return points


def build_global_lppl_validation_observations(
    points: list[dict[str, Any]],
    bars: list[MarketDailyBar],
    drawdown_threshold_pct: float,
) -> list[dict[str, Any]]:
    index_by_date = {bar.date: index for index, bar in enumerate(bars)}
    observations: list[dict[str, Any]] = []
    for point in points:
        try:
            point_date = date.fromisoformat(str(point.get("date") or ""))
        except ValueError:
            continue
        score = optional_float(point.get("score"))
        index = index_by_date.get(point_date)
        if score is None or index is None or index + 1 >= len(bars):
            continue
        row = {"date": point_date.isoformat(), "score": round(bounded_score(score), 1)}
        for horizon in (5, 10, 15, 20):
            row[f"forward{horizon}d"] = equity_forward_return_pct(bars, index, horizon)
            drawdown = equity_forward_max_drawdown_pct(bars, index, horizon)
            row[f"maxDrawdown{horizon}d"] = drawdown
            row[f"drawdownEvent{horizon}d"] = drawdown is not None and drawdown <= drawdown_threshold_pct
            row[f"drawdownLeadDays{horizon}d"] = equity_forward_drawdown_lead_days(bars, index, horizon, drawdown_threshold_pct)
        observations.append(row)
    return observations


def global_lppl_validation_weight(test_15d: dict[str, Any]) -> tuple[float, str, str]:
    alert_days = optional_float(test_15d.get("alertDays")) or 0.0
    precision = optional_float(test_15d.get("precision"))
    base_rate = optional_float(test_15d.get("baseRate")) or 0.0
    if alert_days < 3 or precision is None:
        return 0.75, "thin", "样本偏少"
    if precision >= max(60.0, base_rate + 15.0):
        return 1.0, "validated", "验证支持"
    if precision >= base_rate + 5.0:
        return 0.85, "mixed", "部分支持"
    return 0.60, "weak", "历史偏弱"


def global_lppl_validation_summary(symbol: str, test_15d: dict[str, Any], multiplier: float, role_cn: str) -> str:
    return (
        f"{symbol} own-market 15D audit: threshold {test_15d.get('threshold')}, "
        f"precision {format_optional_percent_value(test_15d.get('precision'))}, "
        f"recall {format_optional_percent_value(test_15d.get('recall'))}, "
        f"false {test_15d.get('falsePositives', 0)}, weight x{multiplier:.2f} ({role_cn})."
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
        return {"available": False, "sampleSize": 0, "threshold": threshold, "horizonTests": [], "summary": f"{symbol}或LPPL历史样本不足。"}
    index_by_date = {bar.date: index for index, bar in enumerate(clean_bars)}
    observations: list[dict[str, Any]] = []
    for point in history_points:
        try:
            point_date = date.fromisoformat(str(point.get("date") or ""))
        except ValueError:
            continue
        score = optional_float(point.get("score"))
        index = index_by_date.get(point_date)
        if score is None or index is None or index + 1 >= len(clean_bars):
            continue
        row = {"date": point_date.isoformat(), "score": round(bounded_score(score), 1)}
        for horizon in (5, 10, 15, 20):
            row[f"forward{horizon}d"] = equity_forward_return_pct(clean_bars, index, horizon)
            drawdown = equity_forward_max_drawdown_pct(clean_bars, index, horizon)
            row[f"maxDrawdown{horizon}d"] = drawdown
            row[f"drawdownEvent{horizon}d"] = drawdown is not None and drawdown <= drawdown_threshold_pct
            row[f"drawdownLeadDays{horizon}d"] = equity_forward_drawdown_lead_days(clean_bars, index, horizon, drawdown_threshold_pct)
        observations.append(row)
    if not observations:
        return {"available": False, "sampleSize": 0, "threshold": threshold, "horizonTests": [], "summary": f"LPPL历史点没有足够后续{symbol}交易日。"}
    calibration_grid = [
        equity_backtest_threshold_test(candidate_threshold, observations, drawdown_threshold_pct, horizon=15)
        for candidate_threshold in (55, 60, 65, 70, 75, 80, 85, 90)
    ]
    recommended_threshold_test = global_lppl_recommended_threshold(calibration_grid, len(observations))
    threshold = int(recommended_threshold_test.get("threshold") or threshold)
    horizon_tests = [
        equity_backtest_threshold_test(threshold, observations, drawdown_threshold_pct, horizon=horizon)
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
        "sampleSize": len(observations),
        "threshold": threshold,
        "drawdownEvent": f"next 5/10/15/20 trading days max drawdown <= {drawdown_threshold_pct:.1f}%",
        "horizonTests": horizon_tests,
        "calibrationGrid": calibration_grid,
        "recommendedThreshold": recommended_threshold_test,
        "alertClusterTest": alert_cluster_test,
        "summary": summary,
    }


def global_lppl_recommended_threshold(calibration_grid: list[dict[str, Any]], sample_size: int) -> dict[str, Any]:
    candidates = [
        row
        for row in calibration_grid
        if (optional_float(row.get("alertDays")) or 0.0) >= max(3.0, min(10.0, sample_size / 25.0))
    ]
    if not candidates:
        candidates = [
            row
            for row in calibration_grid
            if (optional_float(row.get("alertDays")) or 0.0) > 0
        ]
    if not candidates:
        return {}
    base_rate = max(optional_float(row.get("baseRate")) or 0.0 for row in candidates)
    min_precision = max(45.0, base_rate + 8.0)
    qualifying = [row for row in candidates if (optional_float(row.get("precision")) or 0.0) >= min_precision]
    if not qualifying:
        qualifying = candidates

    def threshold_score(row: dict[str, Any]) -> tuple[float, float, float, float]:
        precision = optional_float(row.get("precision")) or 0.0
        recall = optional_float(row.get("recall")) or 0.0
        alert_days = optional_float(row.get("alertDays")) or 0.0
        threshold = optional_float(row.get("threshold")) or 0.0
        return (precision, recall, alert_days, threshold)

    selected = dict(max(qualifying, key=threshold_score))
    selected.update(
        {
            "key": "globalLpplRecommendedThreshold",
            "label": "LPPL推荐告警阈值",
            "labelEn": "Global LPPL Recommended Threshold",
            "useCase": "用历史SPY前瞻回撤验证后选择; 优先提高精确率,再考虑覆盖率。",
        }
    )
    return selected


def parse_payload_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


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
    distribution = volume_pct >= 75 and (close_loc <= 0.40 or (day_ret is not None and day_ret < 0))
    score = 50.0
    if thin_breakout:
        score = 25.0 + 53.0 * thin_breakout_strength
    if distribution:
        score = max(score, 84.0)
    if not thin_breakout and not distribution:
        score = max(25.0, risk_linear(0.5 - close_loc, 0.0, 0.35))
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
        metrics={"volumePercentile": round(volume_pct, 1), "closeLocation": round(close_loc, 3), "spyDayReturn": pct_metric(day_ret), "thinBreakoutStrength": round(thin_breakout_strength, 3)},
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


def equity_short_term_risk_allocation(score: float) -> dict[str, str]:
    if score >= 75:
        return {
            "regime": "Strong Alert",
            "regimeCn": "强告警",
            "stance": "短线降风险",
            "equityExposure": "高Beta/AI拥挤仓位降到低配",
            "hedgeAction": "收盘前优先减仓或买入1-2周保护性对冲",
        }
    if score >= 60:
        return {
            "regime": "Caution",
            "regimeCn": "警戒",
            "stance": "控制追涨",
            "equityExposure": "权益仓位降到中性以下",
            "hedgeAction": "减少半导体/高Beta集中敞口",
        }
    if score >= 40:
        return {
            "regime": "Watch",
            "regimeCn": "观察",
            "stance": "不追高",
            "equityExposure": "维持中性",
            "hedgeAction": "等待确认",
        }
    return {
        "regime": "Normal",
        "regimeCn": "正常",
        "stance": "风险可承受",
        "equityExposure": "维持计划仓位",
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


def format_optional_percent_value(value: object) -> str:
    numeric = optional_float(value)
    return "--" if numeric is None else f"{numeric:.1f}%"


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


def bar_index_at_or_before(bars: list[MarketDailyBar], target: date) -> int | None:
    candidates = [index for index, bar in enumerate(bars) if bar.date <= target]
    return candidates[-1] if candidates else None


def bar_at_or_before(bars: list[MarketDailyBar], target: date) -> MarketDailyBar | None:
    index = bar_index_at_or_before(bars, target)
    return bars[index] if index is not None else None


def trailing_return(bars: list[MarketDailyBar], target: date, lookback: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None or index <= 0:
        return None
    prior_index = max(0, index - lookback)
    prior = bars[prior_index]
    current = bars[index]
    if prior.close <= 0:
        return None
    return current.close / prior.close - 1


def moving_average_gap(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None or index + 1 < window:
        return None
    sample = bars[index - window + 1: index + 1]
    average_close = sum(bar.close for bar in sample) / len(sample)
    if average_close <= 0:
        return None
    return bars[index].close / average_close - 1


def drawdown_from_recent_high(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None:
        return None
    sample = bars[max(0, index - window + 1): index + 1]
    if not sample:
        return None
    recent_high = max(bar.high for bar in sample)
    if recent_high <= 0:
        return None
    return bars[index].close / recent_high - 1


def high_to_low_drawdown_in_window(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None:
        return None
    sample = bars[max(0, index - window + 1): index + 1]
    if not sample:
        return None
    recent_high = max(bar.high for bar in sample)
    recent_low = min(bar.low for bar in sample)
    if recent_high <= 0 or recent_low <= 0:
        return None
    return recent_low / recent_high - 1


def rebound_from_recent_low(bars: list[MarketDailyBar], target: date, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None:
        return None
    sample = bars[max(0, index - window + 1): index + 1]
    if not sample:
        return None
    recent_low = min(bar.low for bar in sample)
    if recent_low <= 0:
        return None
    return bars[index].close / recent_low - 1


def average_optional(values: Any) -> float | None:
    numeric = [value for value in (optional_float(item) for item in values) if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def one_day_return(bars: list[MarketDailyBar], target: date) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None or index <= 0:
        return None
    prior = bars[index - 1]
    current = bars[index]
    if prior.close <= 0:
        return None
    return current.close / prior.close - 1


def close_location_value(bar: MarketDailyBar) -> float:
    if bar.high <= bar.low:
        return 0.5
    return max(0.0, min(1.0, (bar.close - bar.low) / (bar.high - bar.low)))


def volume_percentile_at(bars: list[MarketDailyBar], target: date, *, window: int) -> float | None:
    index = bar_index_at_or_before(bars, target)
    if index is None:
        return None
    current_volume = bars[index].volume
    if current_volume is None:
        return None
    sample = [bar.volume for bar in bars[max(0, index - window): index + 1] if bar.volume is not None]
    if len(sample) < 10:
        return None
    return 100 * sum(1 for value in sample if value <= current_volume) / len(sample)


def risk_linear(value: float | None, low: float, high: float) -> float:
    if value is None:
        return 50.0
    if high <= low:
        return 50.0
    return bounded_score(100 * (float(value) - low) / (high - low))


def pct_metric(value: float | None) -> float | None:
    return round(float(value) * 100, 2) if value is not None and math.isfinite(float(value)) else None


def format_optional_pct(value: float | None) -> str:
    return "--" if value is None else format_signed_pct(value)


def format_signed_pct(value: float) -> str:
    return f"{value * 100:+.1f}%"


def format_optional_number(value: float | None) -> str:
    return "--" if value is None else f"{value:+.1f}"


def equity_risk_tone(score: float) -> str:
    if score >= 75:
        return "restrictive"
    if score >= 60:
        return "caution"
    if score >= 40:
        return "neutral"
    return "supportive"


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
