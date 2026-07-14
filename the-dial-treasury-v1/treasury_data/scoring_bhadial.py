"""Bhadial Conditions Score domain extracted from build_dashboard.py.

The 21-factor, 7-module nowcast keeps its fixed-weight compatibility score while
also exposing point-in-time freshness, warm-up, observed-only, and coverage-
shrunk reliability contracts. This pure scoring layer depends only on lower
layers (series_math / dashboard_core / indicators / sources).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from .sources import SeriesPoint, TimeSeries
from .dashboard_core import *  # noqa: F401,F403
from .series_math import *  # noqa: F401,F403
from .indicators import BHADIAL_BREAKEVEN_TARGET


BHADIAL_COMPATIBILITY_SOURCE = "bhadial-the-dial"


BHADIAL_MODULE_NAMES = ["Liquidity", "Funding", "Treasury", "Rates", "Credit", "Risk", "External"]


BHADIAL_FACTOR_COVERAGE: list[dict[str, Any]] = [
    {
        "module": "Liquidity",
        "scored": 3,
        "display": 5,
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
        "scored": 3,
        "display": 9,
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
            {"name": "Curve Curvature (Abs)", "status": "derived", "local": "曲线曲率(绝对值)", "source": "10Y residual vs linear 2Y-30Y chord"},
            {"name": "10Y Nominal Rate", "status": "public", "local": "10Y 收益率动量", "source": "U.S. Treasury curve"},
            {"name": "30Y Rate", "status": "public", "local": "30Y key tile", "source": "U.S. Treasury curve"},
            {"name": "2Y Rate", "status": "public", "local": "2Y 市场政策代理", "source": "U.S. Treasury curve"},
        ],
    },
    {
        "module": "Rates",
        "scored": 2,
        "display": 3,
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
        "scored": 2,
        "display": 2,
        "factors": [
            {"name": "NFCI", "status": "public", "local": "金融条件指数(NFCI)", "source": "FRED NFCI"},
            {"name": "HY Credit", "status": "proxy", "local": "HY信用偏好(HY/UST)", "source": "FRED ICE HY TR 63/126D relative return vs DGS10 duration proxy"},
            {"name": "IG Credit", "status": "proxy", "local": "IG信用偏好(IG/UST)", "source": "FRED ICE IG TR 63/126D relative return vs DGS10 duration proxy"},
            {"name": "Regional Banks vs SPY", "status": "proxy", "local": "银行股相对S&P500", "source": "FRED NASDAQBANK / SP500 proxy"},
        ],
    },
    {
        "module": "Risk",
        "scored": 3,
        "display": 2,
        "factors": [
            {"name": "VIX", "status": "public", "local": "VIX", "source": "FRED VIXCLS"},
            {"name": "VIX Term Structure", "status": "derived", "local": "VIX期限结构", "source": "FRED VIXCLS / VXVCLS"},
            {"name": "Risk vs Safe", "status": "proxy", "local": "风险资产/美债代理", "source": "FRED SP500 63/126D relative return vs DGS10 duration proxy"},
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
        # 2026-06-16 去冗余簇c1: 删 bank_reserves(与净流动性近substitute, OOS IC 0.26≈净流动性0.22)
        # 与 onrrp_near_zero_risk(滞后, 且RRP已含于净流动性公式内); 权重并入 fed_net_liquidity(0.30→0.60)。
        # bank_reserves/onrrp 原始值仍在指标表展示, 仅不再计入综合分。
        "factors": [
            {"id": "fed_net_liquidity", "cadence": "weekly", "maxAgeDays": 14, "minSampleCount": 12, "publicationLagDays": 2, "remoteName": "Fed Net Liquidity", "name": "净流动性", "weight": 0.60, "scoreKey": "net_liquidity", "direction": "higher_better", "method": "level_percentile", "valueKey": "net_liquidity_trillions", "format": "usd_t", "source": "FRED WALCL - WTREGEN - RRPONTSYD"},
            {"id": "delta_net_liq_13w", "cadence": "weekly", "maxAgeDays": 14, "minSampleCount": 12, "publicationLagDays": 2, "remoteName": "Net Liquidity Momentum (13W)", "name": "13周净流动性动量", "weight": 0.25, "scoreKey": "net_liquidity_13w_momentum", "direction": "higher_better", "method": "level_percentile", "valueKey": "net_liquidity_13w_change_trillions", "format": "signed_usd_t", "source": "Net liquidity 13W change"},
            {"id": "tga_dev_signed", "cadence": "weekly", "maxAgeDays": 14, "minSampleCount": 12, "publicationLagDays": 2, "remoteName": "TGA Deviation", "name": "TGA偏离度", "weight": 0.15, "scoreKey": "tga_deviation", "direction": "lower_better", "method": "level_percentile", "valueKey": "tga_deviation_trillions", "format": "signed_usd_t", "source": "FRED WTREGEN - 52W median"},
        ],
    },
    {
        "name": "Funding",
        "nameCn": "融资",
        "smooth": "ema5",
        # 2026-06-16 去冗余簇c2(3个SOFR走廊摩擦互为近substitute): 保留最规范的 SOFR-IORB 走廊
        # (corridor_friction_1, OOS IC 0.37), 删 corridor_friction_2 与 collateral_friction 并并入其权重(→0.66);
        # 另删 effr_iorb(簇c1成员, 分类none/无前瞻, 读数11与同模块其余~95严重背离=噪声), 其权重按比例归一。
        "factors": [
            {"id": "corridor_friction_1", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "Corridor Friction 1", "name": "SOFR-IORB走廊摩擦", "weight": 0.66, "scoreKey": "corridor_sofr_iorb_deviation", "displayKey": "corridor_sofr_iorb", "direction": "lower_better", "method": "deviation", "valueKey": "sofr_iorb_spread_bp", "format": "signed_bp", "source": "FRED SOFR - IORB"},
            {"id": "cp_tbill_spread", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "CP-TBill Spread", "name": "商票-TBill利差", "weight": 0.23, "scoreKey": "cp_tbill_spread", "direction": "lower_better", "method": "level_percentile", "valueKey": "cp_tbill_spread_bp", "format": "signed_bp", "source": "FRED DCPF3M - DTB3"},
            {"id": "fragmentation_21d", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "Funding Fragmentation (21D)", "name": "资金分裂度(21D)", "weight": 0.11, "scoreKey": "funding_fragmentation", "direction": "lower_better", "method": "shock_only", "valueKey": "funding_fragmentation_21d", "format": "number", "source": "SOFR corridor dispersion EMA(21 business-day observations)"},
        ],
    },
    {
        "name": "Treasury",
        "nameCn": "国债",
        "factors": [
            {"id": "dgs30_dgs10", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "30Y-10Y Term Premium", "name": "30Y-10Y期限溢价", "weight": 0.35, "scoreKey": "treasury_30y10y", "direction": "higher_better", "method": "level_percentile", "valueKey": "s30s10", "format": "bp", "source": "U.S. Treasury curve 30Y - 10Y"},
            {"id": "dgs10_vol_21d", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "10Y Rate Volatility (21D)", "name": "10Y收益率波动率(21D)", "weight": 0.35, "scoreKey": "treasury_10y_vol_21d", "direction": "lower_better", "method": "level_percentile", "valueKey": "ten_year_realized_vol_21d_bp", "format": "vol_bp", "source": "U.S. Treasury curve 10Y realized vol"},
            {"id": "curve_curvature_abs", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "Curve Curvature (Abs)", "name": "曲线曲率(绝对值)", "weight": 0.30, "scoreKey": "curve_curvature_abs", "direction": "lower_better", "method": "shock_only", "valueKey": "curve_curvature_abs_bp", "format": "bp", "source": "ABS(DGS10 - linear 2Y-30Y chord at 10Y)"},
        ],
    },
    {
        "name": "Rates",
        "nameCn": "利率",
        # 2026-06-18 去冗余簇c4: 仅留 real_curve(真实曲线斜率, 最强领先利率因子 OOS IC 0.53),
        # 删 real_rate_level(真实利率水平, OOS IC 0.25/1M -0.05 较弱)并并入其权重(0.15→0.65)。
        # 取舍: 牺牲真实利率"水平"的nowcast描述力, 换取最强前瞻斜率信号(符合系统前瞻预测性目标);
        # real_rate_level 原始值仍在指标表展示, 仅不计入综合分。
        "factors": [
            {"id": "real_curve", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "Real Curve (10Y-5Y)", "name": "真实曲线(10Y-5Y)", "weight": 0.65, "scoreKey": "real_curve", "direction": "higher_better", "method": "level_percentile", "valueKey": "real_curve_10y5y_bp", "format": "signed_bp", "source": "FRED DFII10 - DFII5"},
            {"id": "t10yie", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "10Y Breakeven", "name": "10年盈亏平衡通胀", "weight": 0.35, "scoreKey": "breakeven_target_distance", "direction": "lower_better", "method": "target_distance", "target": BHADIAL_BREAKEVEN_TARGET, "valueKey": "breakeven_10y", "format": "percent", "source": "FRED T10YIE vs 2.3% anchor"},
        ],
    },
    {
        "name": "Credit",
        "nameCn": "信用",
        # 2026-06-16 去冗余簇c3: HY与IG信用偏好近substitute(且共用DGS10价格代理), 保留更具周期敏感性的
        # HY(hy_credit)并并入IG权重(0.25→0.50); 另删 kre_spy(银行股相对强弱, lift=0/滞后, 读数25=噪声),
        # nfci 权重补足至0.50。kre_spy/ig 原始值仍在指标表展示, 仅不计入综合分。
        "factors": [
            {"id": "nfci", "cadence": "weekly", "maxAgeDays": 14, "minSampleCount": 12, "publicationLagDays": 7, "remoteName": "NFCI", "name": "金融条件指数(NFCI)", "weight": 0.50, "scoreKey": "nfci", "direction": "lower_better", "method": "level_percentile", "valueKey": "nfci", "format": "signed_number", "source": "FRED NFCI"},
            {"id": "hy_credit", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "HY Credit", "name": "HY信用偏好(HY/UST)", "weight": 0.50, "scoreKey": "hy_credit_preference", "direction": "higher_better", "method": "level_percentile", "valueKey": "hy_credit_preference", "format": "number", "source": "FRED HY total-return 63/126D relative return vs DGS10 duration proxy"},
        ],
    },
    {
        "name": "Risk",
        "nameCn": "风险",
        # 2026-06-16 删 high_beta_pref(高Beta偏好, 滞后/lift微, 读数99在回撤前易高估风险偏好而掩盖VIX抬升);
        # 权重按比例并入其余三项(vix 0.30→0.375, vix_term 0.25→0.3125, risk_vs_safe 0.25→0.3125)。
        "factors": [
            {"id": "vix", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "VIX", "name": "VIX", "weight": 0.375, "scoreKey": "vix", "direction": "lower_better", "method": "level_percentile", "valueKey": "vix", "format": "number", "source": "FRED VIXCLS"},
            {"id": "vix_term_structure", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "VIX Term Structure", "name": "VIX期限结构", "weight": 0.3125, "scoreKey": "vix_term_structure", "direction": "lower_better", "method": "level_percentile", "valueKey": "vix_term_structure", "format": "number", "source": "FRED VIXCLS / VXVCLS"},
            {"id": "risk_vs_safe", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "Risk vs Safe", "name": "风险资产/美债代理", "weight": 0.3125, "scoreKey": "risk_vs_safe", "direction": "higher_better", "method": "level_percentile", "valueKey": "risk_vs_safe", "format": "number", "source": "FRED SP500 63/126D relative return vs DGS10 duration proxy"},
        ],
    },
    {
        "name": "External",
        "nameCn": "外部",
        "factors": [
            {"id": "dxy", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "US Dollar Index (DXY)", "name": "美元广义指数", "weight": 0.25, "scoreKey": "dxy", "direction": "lower_better", "method": "level_percentile", "valueKey": "dxy", "format": "number", "source": "FRED DTWEXBGS proxy"},
            {"id": "fx_vol", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "FX Realized Volatility", "name": "美元实现波动率", "weight": 0.20, "scoreKey": "dxy_realized_vol", "direction": "lower_better", "method": "level_percentile", "valueKey": "dxy_realized_vol", "format": "vol_pct", "source": "FRED DTWEXBGS 63D realized vol"},
            {"id": "wti", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "WTI Oil", "name": "WTI原油冲击", "weight": 0.20, "scoreKey": "wti_shock", "displayKey": "wti", "direction": "lower_better", "method": "shock_only", "valueKey": "wti", "format": "price_usd", "source": "FRED DCOILWTICO positive deviation"},
            {"id": "ovx_dev", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "Oil Volatility Deviation", "name": "原油波动偏离", "weight": 0.25, "scoreKey": "oil_vol_deviation", "direction": "lower_better", "method": "shock_only", "valueKey": "oil_vol_deviation", "format": "number", "source": "FRED OVXCLS - rolling median"},
            {"id": "natgas", "cadence": "business_daily", "maxAgeDays": 7, "minSampleCount": 20, "remoteName": "Natural Gas", "name": "天然气冲击", "weight": 0.10, "scoreKey": "natgas_shock", "displayKey": "natgas", "direction": "lower_better", "method": "shock_only", "valueKey": "natgas", "format": "price_usd", "source": "FRED DHHNGSP positive deviation"},
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


class PreparedBhadialSeries(dict[str, list[SeriesPoint]]):
    """Marker mapping whose factor histories are finite and date ordered."""


def prepare_bhadial_series(
    series: dict[str, list[SeriesPoint]] | PreparedBhadialSeries,
) -> PreparedBhadialSeries:
    if isinstance(series, PreparedBhadialSeries):
        return series
    return PreparedBhadialSeries(
        (str(key), clean_points(points))
        for key, points in series.items()
    )


BHADIAL_SCORED_LOCAL_NAMES = {
    str(factor["name"])
    for module in BHADIAL_CONDITION_MODULES
    for factor in module["factors"]
}


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
    evidence_available: bool = True,
) -> dict[str, Any]:
    """Build one scorecard factor without turning missing evidence into neutral evidence.

    ``score == 0`` is a legitimate observation when the underlying series and
    its ranking history are available.  It must remain auditable in that case.
    When a derived/proxy input is absent or has no valid percentile, however,
    the same numeric zero is only a display placeholder and must not enter the
    conclusion denominator.
    """
    if not evidence_available:
        tag = "数据不足"
        value = "数据不足"
        score = 0
        source_mode = "manual-placeholder"
        if curve is not None:
            curve = 0
    factor: dict[str, Any] = {
        "n": name,
        "tag": tag,
        "v": value,
        "score": score,
        "note": note,
        "sourceMode": source_mode,
        "auditEligible": evidence_available,
        "evidenceStatus": "available" if evidence_available else "insufficient-data",
        "compatibilityWith": BHADIAL_COMPATIBILITY_SOURCE,
        "bhadialModule": module,
    }
    if curve is not None:
        factor["curve"] = curve
    return factor


def bhadial_conditions_snapshot(
    ind: dict[str, Any],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    series = prepare_bhadial_series(ind.get("percentile_series", {}))
    # Live callers should pass the dashboard observation date.  Falling back to
    # the latest raw observation keeps the helper deterministic for isolated
    # fixtures, while the explicit date makes publication-lag handling truly
    # point-in-time in production.
    target = as_of or latest_bhadial_score_date(series)
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
                "legacyFixedScore": round(module["legacyFixedScore"], 1),
                "observedOnlyScore": round(module["observedOnlyScore"], 1),
                "reliabilityScore": round(module["reliabilityScore"], 1),
                "effectiveWeightCoveragePct": round(float(module["effectiveWeightCoverage"]) * 100),
                "ema5Score": round(module["ema5Score"], 1) if module.get("ema5Score") is not None else None,
                "ema5MonthScore": round(module["ema5MonthScore"], 1) if module.get("ema5MonthScore") is not None else None,
                "emaSpanMonths": module.get("emaSpanMonths"),
                "weight": round(module_weight, 3),
                "observedFactorCount": module["observedFactorCount"],
                "scoredFactorCount": module["scoredFactorCount"],
                "factorCount": module["factorCount"],
                "method": module.get("method", "weighted factors"),
            }
        )
    for module in BHADIAL_CONDITION_MODULES:
        module_weight = bhadial_module_weight(str(module["name"]))
        for spec in module["factors"]:
            raw = raw_components_by_id.get(str(spec["id"]), {})
            score = float(raw.get("score", 50.0))
            observed = bool(raw.get("observed"))
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
                    "observed": observed,
                    "scoreEligible": bool(raw.get("scoreEligible")),
                    "percentile": raw.get("percentile"),
                    "observationDate": raw.get("observationDate"),
                    "ageDays": raw.get("ageDays"),
                    "freshnessStatus": raw.get("freshnessStatus", "missing"),
                    "scoringStatus": raw.get("scoringStatus", "missing"),
                    "effectiveSampleCount": int(raw.get("effectiveSampleCount", 0)),
                    "minSampleCount": int(raw.get("minSampleCount", spec["minSampleCount"])),
                    "cadence": raw.get("cadence", spec["cadence"]),
                    "maxAgeDays": int(raw.get("maxAgeDays", spec["maxAgeDays"])),
                    "weight": round(factor_weight, 2),
                    "effectiveWeight": round(effective_weight, 4),
                    "contribution": round((score - 50) * effective_weight, 2),
                    "value": (
                        format_bhadial_factor_value(ind.get(str(spec["valueKey"])), str(spec["format"]))
                        if observed
                        else "--"
                    ),
                    "source": spec["source"],
                    "direction": (
                        "missing"
                        if not observed
                        else "supportive"
                        if score >= 55
                        else "restrictive"
                        if score <= 45
                        else "neutral"
                    ),
                    "scoring": spec["method"],
                    "note": bhadial_factor_note(spec),
                }
            )
    observed_factor_count = int(score_row.get("observedFactorCount", 0))
    scored_factor_count = int(score_row.get("scoredFactorCount", 0))
    factor_count = sum(len(module["factors"]) for module in BHADIAL_CONDITION_MODULES)
    return {
        "score": round(float(score_row["score"]), 1),
        "legacyFixedScore": round(float(score_row["legacyFixedScore"]), 1),
        "observedOnlyScore": round(float(score_row["observedOnlyScore"]), 1),
        "reliabilityScore": round(float(score_row["reliabilityScore"]), 1),
        "effectiveWeightCoveragePct": round(float(score_row["effectiveWeightCoverage"]) * 100),
        "observedFactorCount": observed_factor_count,
        "scoredFactorCount": scored_factor_count,
        "factorCount": factor_count,
        "coveragePct": round(observed_factor_count / factor_count * 100) if factor_count else 0,
        "scoredCoveragePct": round(scored_factor_count / factor_count * 100) if factor_count else 0,
        "components": components,
        "modules": modules,
    }


def latest_bhadial_score_date(
    series: dict[str, list[SeriesPoint]] | PreparedBhadialSeries,
) -> date | None:
    prepared = prepare_bhadial_series(series)
    latest: date | None = None
    for key in BHADIAL_CONDITION_SERIES_KEYS:
        points = prepared.get(key, [])
        if points and (latest is None or points[-1].date > latest):
            latest = points[-1].date
    return latest


def bhadial_publication_lag_days(spec: dict[str, Any]) -> int:
    """Return the point-in-time availability lag shared by live and replay scoring."""
    configured = spec.get("publicationLagDays")
    return 1 if configured is None else max(0, int(configured))


def neutral_bhadial_conditions_row(*, include_components: bool = False) -> dict[str, Any]:
    modules = []
    for module in BHADIAL_CONDITION_MODULES:
        module_row = {
            "name": module["name"],
            "nameCn": module["nameCn"],
            "score": 50.0,
            "rawScore": 50.0,
            "legacyFixedScore": 50.0,
            "observedOnlyScore": 50.0,
            "reliabilityScore": 50.0,
            "effectiveWeightCoverage": 0.0,
            "ema5Score": None,
            "ema5MonthScore": None,
            "observedFactorCount": 0,
            "scoredFactorCount": 0,
            "factorCount": len(module["factors"]),
            "method": "weighted factors",
            "weight": bhadial_module_weight(str(module["name"])),
        }
        if include_components:
            module_row["factors"] = [
                {
                    "id": spec["id"],
                    "score": 50.0,
                    "percentile": None,
                    "observed": False,
                    "scoreEligible": False,
                    "observationDate": None,
                    "ageDays": None,
                    "freshnessStatus": "missing",
                    "scoringStatus": "missing",
                    "effectiveSampleCount": 0,
                    "minSampleCount": int(spec["minSampleCount"]),
                    "cadence": str(spec["cadence"]),
                    "maxAgeDays": int(spec["maxAgeDays"]),
                }
                for spec in module["factors"]
            ]
        modules.append(module_row)
    return {
        "score": 50.0,
        "legacyFixedScore": 50.0,
        "observedOnlyScore": 50.0,
        "reliabilityScore": 50.0,
        "effectiveWeightCoverage": 0.0,
        "observedFactorCount": 0,
        "scoredFactorCount": 0,
        "modules": modules,
    }


def bhadial_module_weight(name: str) -> float:
    return BHADIAL_MODULE_WEIGHTS.get(name, 1 / max(1, len(BHADIAL_CONDITION_MODULES)))


def bhadial_conditions_score_at(
    series: dict[str, list[SeriesPoint]] | PreparedBhadialSeries,
    target: date | None,
    *,
    include_components: bool = False,
) -> dict[str, Any] | None:
    if target is None:
        return None
    prepared = prepare_bhadial_series(series)
    modules: list[dict[str, Any]] = []
    composite_total = 0.0
    weight_total = 0.0
    observed_only_total = 0.0
    eligible_effective_weight = 0.0
    observed_total = 0
    scored_total = 0
    for module in BHADIAL_CONDITION_MODULES:
        raw_module = bhadial_raw_module_score_at(prepared, module, target, include_components=include_components)
        if raw_module is None:
            return None
        module_score = raw_module["rawScore"]
        module_observed_only_score = raw_module["observedOnlyScore"]
        module_reliability_score = raw_module["reliabilityScore"]
        ema5_score = None
        ema5_month_score = None
        method = "weighted factors"
        if module.get("smooth") == "ema5":
            ema_metrics = bhadial_module_ema_metrics_at(prepared, module, target, span_months=5)
            ema5_score = ema_metrics.get("legacyFixedScore")
            ema5_month_score = ema5_score
            if ema5_month_score is not None:
                module_score = ema5_month_score
                smoothed_observed_only = ema_metrics.get("observedOnlyScore")
                module_observed_only_score = (
                    float(smoothed_observed_only)
                    if smoothed_observed_only is not None
                    else 50.0
                )
                module_reliability_score = 50.0 + (
                    module_observed_only_score - 50.0
                ) * float(raw_module["effectiveWeightCoverage"])
            method = "weighted factors + EMA(5 months)"
        observed_total += int(raw_module["observedFactorCount"])
        scored_total += int(raw_module["scoredFactorCount"])
        module_row = {
            "name": module["name"],
            "nameCn": module["nameCn"],
            "score": module_score,
            "rawScore": raw_module["rawScore"],
            "legacyFixedScore": module_score,
            "observedOnlyScore": module_observed_only_score,
            "rawObservedOnlyScore": raw_module["observedOnlyScore"],
            "reliabilityScore": module_reliability_score,
            "rawReliabilityScore": raw_module["reliabilityScore"],
            "effectiveWeightCoverage": raw_module["effectiveWeightCoverage"],
            "ema5Score": ema5_score,
            "ema5MonthScore": ema5_month_score,
            "emaSpanMonths": 5 if module.get("smooth") == "ema5" else None,
            "weight": bhadial_module_weight(str(module["name"])),
            "observedFactorCount": raw_module["observedFactorCount"],
            "scoredFactorCount": raw_module["scoredFactorCount"],
            "factorCount": raw_module["factorCount"],
            "method": method,
        }
        if include_components:
            module_row["factors"] = raw_module["factors"]
        modules.append(module_row)
        module_weight = bhadial_module_weight(str(module["name"]))
        composite_total += module_score * module_weight
        module_eligible_weight = module_weight * float(raw_module["effectiveWeightCoverage"])
        observed_only_total += module_observed_only_score * module_eligible_weight
        eligible_effective_weight += module_eligible_weight
        weight_total += module_weight
    if not modules:
        return None
    legacy_fixed_score = composite_total / max(weight_total, 1e-9)
    effective_weight_coverage = eligible_effective_weight / max(weight_total, 1e-9)
    observed_only_score = (
        observed_only_total / eligible_effective_weight
        if eligible_effective_weight > 0
        else 50.0
    )
    reliability_score = 50.0 + (observed_only_score - 50.0) * effective_weight_coverage
    return {
        # Compatibility contract: existing Conditions Score consumers continue
        # to receive the fixed-weight score under the established ``score`` key.
        "score": legacy_fixed_score,
        "legacyFixedScore": legacy_fixed_score,
        "observedOnlyScore": observed_only_score,
        "reliabilityScore": reliability_score,
        "effectiveWeightCoverage": effective_weight_coverage,
        "observedFactorCount": observed_total,
        "scoredFactorCount": scored_total,
        "modules": modules,
    }


def bhadial_raw_module_score_at(
    series: dict[str, list[SeriesPoint]] | PreparedBhadialSeries,
    module: dict[str, Any],
    target: date,
    *,
    include_components: bool = False,
) -> dict[str, Any] | None:
    prepared = prepare_bhadial_series(series)
    total = 0.0
    total_weight = 0.0
    eligible_total = 0.0
    eligible_weight = 0.0
    observed = 0
    scored = 0
    factors: list[dict[str, Any]] = []
    for spec in module["factors"]:
        factor_score = bhadial_factor_score_at(prepared, spec, target)
        score = factor_score["score"]
        weight = float(spec["weight"])
        total += score * weight
        total_weight += weight
        if factor_score["observed"]:
            observed += 1
        if factor_score["scoreEligible"]:
            eligible_total += score * weight
            eligible_weight += weight
            scored += 1
        if include_components:
            factors.append({"id": spec["id"], **factor_score})
    if total_weight <= 0:
        return None
    legacy_fixed_score = total / total_weight
    effective_weight_coverage = eligible_weight / total_weight
    observed_only_score = eligible_total / eligible_weight if eligible_weight > 0 else 50.0
    reliability_score = 50.0 + (observed_only_score - 50.0) * effective_weight_coverage
    row: dict[str, Any] = {
        "rawScore": legacy_fixed_score,
        "legacyFixedScore": legacy_fixed_score,
        "observedOnlyScore": observed_only_score,
        "reliabilityScore": reliability_score,
        "effectiveWeightCoverage": effective_weight_coverage,
        "observedFactorCount": observed,
        "scoredFactorCount": scored,
        "factorCount": len(module["factors"]),
    }
    if include_components:
        row["factors"] = factors
    return row


def bhadial_factor_score_at(
    series: dict[str, list[SeriesPoint]] | PreparedBhadialSeries,
    spec: dict[str, Any],
    target: date,
) -> dict[str, Any]:
    prepared = prepare_bhadial_series(series)
    points = prepared.get(str(spec["scoreKey"]), [])
    publication_lag_days = bhadial_publication_lag_days(spec)
    availability_cutoff = target - timedelta(days=publication_lag_days)
    current = point_at_or_before(points, availability_cutoff)
    raw_percentile, effective_sample_count = (
        historical_percentile_with_sample_count_at_ordered(points, availability_cutoff)
        if points
        else (None, 0)
    )
    cadence = str(spec["cadence"])
    max_age_days = int(spec["maxAgeDays"])
    min_sample_count = int(spec["minSampleCount"])
    if current is None:
        return {
            "score": 50.0,
            "percentile": None,
            "observed": False,
            "scoreEligible": False,
            "observationDate": None,
            "ageDays": None,
            "freshnessStatus": "missing",
            "scoringStatus": "missing",
            "effectiveSampleCount": effective_sample_count,
            "minSampleCount": min_sample_count,
            "cadence": cadence,
            "maxAgeDays": max_age_days,
            "publicationLagDays": publication_lag_days,
            "availabilityCutoff": availability_cutoff.isoformat(),
        }
    age_days = max(0, (target - current.date).days)
    freshness_status = "fresh" if age_days <= max_age_days else "stale"
    observed = freshness_status == "fresh"
    score_eligible = observed and effective_sample_count >= min_sample_count and raw_percentile is not None
    if not score_eligible:
        return {
            "score": 50.0,
            "percentile": None,
            "observed": observed,
            "scoreEligible": False,
            "observationDate": current.date.isoformat(),
            "ageDays": age_days,
            "freshnessStatus": freshness_status,
            "scoringStatus": "warming" if observed else "stale",
            "effectiveSampleCount": effective_sample_count,
            "minSampleCount": min_sample_count,
            "cadence": cadence,
            "maxAgeDays": max_age_days,
            "publicationLagDays": publication_lag_days,
            "availabilityCutoff": availability_cutoff.isoformat(),
        }
    score = bhadial_score_from_observation(
        current.value,
        raw_percentile,
        method=str(spec["method"]),
        direction=str(spec["direction"]),
    )
    return {
        "score": max(0.0, min(100.0, score)),
        "percentile": raw_percentile,
        "observed": True,
        "scoreEligible": True,
        "observationDate": current.date.isoformat(),
        "ageDays": age_days,
        "freshnessStatus": freshness_status,
        "scoringStatus": "scored",
        "effectiveSampleCount": effective_sample_count,
        "minSampleCount": min_sample_count,
        "cadence": cadence,
        "maxAgeDays": max_age_days,
        "publicationLagDays": publication_lag_days,
        "availabilityCutoff": availability_cutoff.isoformat(),
    }


def bhadial_score_from_observation(
    value: float,
    percentile: int,
    *,
    method: str,
    direction: str,
) -> float:
    """Map one eligible observation to the common supportiveness scale.

    ``shock_only`` factors are asymmetric by definition: stress may reduce the
    score, but a quiet reading is neutral rather than an independent source of
    support.  Capping their upside at 50 also covers strictly-positive stress
    measures such as absolute curve curvature and funding dispersion, where a
    simple ``value <= 0`` check can never represent the no-shock state.
    """
    if method == "risk_signal":
        bounded = max(0.0, min(1.0, value))
        return (1 - bounded) * 100 if direction == "lower_better" else bounded * 100
    percentile_score = score_from_percentile(percentile, direction)
    if method == "shock_only":
        return min(50.0, percentile_score)
    return percentile_score


def bhadial_module_ema_score_at(
    series: dict[str, list[SeriesPoint]] | PreparedBhadialSeries,
    module: dict[str, Any],
    target: date,
    *,
    span: int,
) -> float | None:
    """Compatibility wrapper; ``span`` is measured in monthly observations."""
    return bhadial_module_ema_metrics_at(
        series,
        module,
        target,
        span_months=span,
    ).get("legacyFixedScore")


def bhadial_module_ema_metrics_at(
    series: dict[str, list[SeriesPoint]] | PreparedBhadialSeries,
    module: dict[str, Any],
    target: date,
    *,
    span_months: int,
) -> dict[str, float | None]:
    """Smooth module scores over month-end observations, never daily rows."""
    prepared = prepare_bhadial_series(series)
    keys = [str(spec["scoreKey"]) for spec in module["factors"]]
    start = window_start(target, years=5)
    month_end_by_period: dict[tuple[int, int], date] = {}
    for key in keys:
        for point in prepared.get(key, []):
            if start <= point.date <= target:
                period = (point.date.year, point.date.month)
                month_end_by_period[period] = max(month_end_by_period.get(period, point.date), point.date)
    # The decision-date score represents the current month. Replace that
    # month's last raw observation instead of appending a second observation;
    # otherwise an unchanged month is counted twice whenever ``target`` falls
    # after the latest source date.
    month_end_by_period[(target.year, target.month)] = target
    month_ends = [month_end_by_period[period] for period in sorted(month_end_by_period)]
    alpha = 2 / (span_months + 1)
    ema_by_field: dict[str, float | None] = {
        "legacyFixedScore": None,
        "observedOnlyScore": None,
        "reliabilityScore": None,
    }
    for point_date in sorted(month_ends):
        raw = bhadial_raw_module_score_at(prepared, module, point_date)
        if raw is None:
            continue
        for field, source_field in (
            ("legacyFixedScore", "rawScore"),
            ("observedOnlyScore", "observedOnlyScore"),
            ("reliabilityScore", "reliabilityScore"),
        ):
            if field == "observedOnlyScore" and float(raw["effectiveWeightCoverage"]) <= 0:
                continue
            score = float(raw[source_field])
            prior = ema_by_field[field]
            ema_by_field[field] = score if prior is None else alpha * score + (1 - alpha) * prior
    return ema_by_field


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
