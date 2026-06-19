"""Bhadial Conditions Score domain extracted from build_dashboard.py (behavior-unchanged,
2026-06-19 全面重构 Phase 1). The 22-factor 7-module nowcast: constants, coverage, point-in-time
module/factor scoring. Pure scoring layer depending only on lower layers (series_math /
dashboard_core / indicators / sources). Re-exported via `from .scoring_bhadial import *`."""
from __future__ import annotations

import math
from datetime import date
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
            {"name": "Curve Curvature (Abs)", "status": "derived", "local": "曲线曲率(绝对值)", "source": "Treasury curve second-order slope"},
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
            {"name": "HY Credit", "status": "proxy", "local": "HY信用偏好(HY/UST)", "source": "FRED ICE HY TR / DGS10 price proxy"},
            {"name": "IG Credit", "status": "proxy", "local": "IG信用偏好(IG/UST)", "source": "FRED ICE IG TR / DGS10 price proxy"},
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
            {"id": "fed_net_liquidity", "publicationLagDays": 2, "remoteName": "Fed Net Liquidity", "name": "净流动性", "weight": 0.60, "scoreKey": "net_liquidity", "direction": "higher_better", "method": "level_percentile", "valueKey": "net_liquidity_trillions", "format": "usd_t", "source": "FRED WALCL - WTREGEN - RRPONTSYD"},
            {"id": "delta_net_liq_13w", "publicationLagDays": 2, "remoteName": "Net Liquidity Momentum (13W)", "name": "13周净流动性动量", "weight": 0.25, "scoreKey": "net_liquidity_13w_momentum", "direction": "higher_better", "method": "level_percentile", "valueKey": "net_liquidity_13w_change_trillions", "format": "signed_usd_t", "source": "Net liquidity 13W change"},
            {"id": "tga_dev_signed", "publicationLagDays": 2, "remoteName": "TGA Deviation", "name": "TGA偏离度", "weight": 0.15, "scoreKey": "tga_deviation", "direction": "lower_better", "method": "level_percentile", "valueKey": "tga_deviation_trillions", "format": "signed_usd_t", "source": "FRED WTREGEN - 52W median"},
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
            {"id": "corridor_friction_1", "remoteName": "Corridor Friction 1", "name": "SOFR-IORB走廊摩擦", "weight": 0.66, "scoreKey": "corridor_sofr_iorb_deviation", "displayKey": "corridor_sofr_iorb", "direction": "lower_better", "method": "deviation", "valueKey": "sofr_iorb_spread_bp", "format": "signed_bp", "source": "FRED SOFR - IORB"},
            {"id": "cp_tbill_spread", "remoteName": "CP-TBill Spread", "name": "商票-TBill利差", "weight": 0.23, "scoreKey": "cp_tbill_spread", "direction": "lower_better", "method": "level_percentile", "valueKey": "cp_tbill_spread_bp", "format": "signed_bp", "source": "FRED DCPF3M - DTB3"},
            {"id": "fragmentation_21d", "remoteName": "Funding Fragmentation (21D)", "name": "资金分裂度(21D)", "weight": 0.11, "scoreKey": "funding_fragmentation", "direction": "lower_better", "method": "shock_only", "valueKey": "funding_fragmentation_21d", "format": "number", "source": "SOFR corridor dispersion EMA(21)"},
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
        # 2026-06-18 去冗余簇c4: 仅留 real_curve(真实曲线斜率, 最强领先利率因子 OOS IC 0.53),
        # 删 real_rate_level(真实利率水平, OOS IC 0.25/1M -0.05 较弱)并并入其权重(0.15→0.65)。
        # 取舍: 牺牲真实利率"水平"的nowcast描述力, 换取最强前瞻斜率信号(符合系统前瞻预测性目标);
        # real_rate_level 原始值仍在指标表展示, 仅不计入综合分。
        "factors": [
            {"id": "real_curve", "remoteName": "Real Curve (10Y-5Y)", "name": "真实曲线(10Y-5Y)", "weight": 0.65, "scoreKey": "real_curve", "direction": "higher_better", "method": "level_percentile", "valueKey": "real_curve_10y5y_bp", "format": "signed_bp", "source": "FRED DFII10 - DFII5"},
            {"id": "t10yie", "remoteName": "10Y Breakeven", "name": "10年盈亏平衡通胀", "weight": 0.35, "scoreKey": "breakeven_target_distance", "direction": "lower_better", "method": "target_distance", "target": BHADIAL_BREAKEVEN_TARGET, "valueKey": "breakeven_10y", "format": "percent", "source": "FRED T10YIE vs 2.3% anchor"},
        ],
    },
    {
        "name": "Credit",
        "nameCn": "信用",
        # 2026-06-16 去冗余簇c3: HY与IG信用偏好近substitute(且共用DGS10价格代理), 保留更具周期敏感性的
        # HY(hy_credit)并并入IG权重(0.25→0.50); 另删 kre_spy(银行股相对强弱, lift=0/滞后, 读数25=噪声),
        # nfci 权重补足至0.50。kre_spy/ig 原始值仍在指标表展示, 仅不计入综合分。
        "factors": [
            {"id": "nfci", "publicationLagDays": 7, "remoteName": "NFCI", "name": "金融条件指数(NFCI)", "weight": 0.50, "scoreKey": "nfci", "direction": "lower_better", "method": "level_percentile", "valueKey": "nfci", "format": "signed_number", "source": "FRED NFCI"},
            {"id": "hy_credit", "remoteName": "HY Credit", "name": "HY信用偏好(HY/UST)", "weight": 0.50, "scoreKey": "hy_credit_preference", "direction": "higher_better", "method": "level_percentile", "valueKey": "hy_credit_preference", "format": "number", "source": "FRED HY total-return / DGS10 price proxy"},
        ],
    },
    {
        "name": "Risk",
        "nameCn": "风险",
        # 2026-06-16 删 high_beta_pref(高Beta偏好, 滞后/lift微, 读数99在回撤前易高估风险偏好而掩盖VIX抬升);
        # 权重按比例并入其余三项(vix 0.30→0.375, vix_term 0.25→0.3125, risk_vs_safe 0.25→0.3125)。
        "factors": [
            {"id": "vix", "remoteName": "VIX", "name": "VIX", "weight": 0.375, "scoreKey": "vix", "direction": "lower_better", "method": "level_percentile", "valueKey": "vix", "format": "number", "source": "FRED VIXCLS"},
            {"id": "vix_term_structure", "remoteName": "VIX Term Structure", "name": "VIX期限结构", "weight": 0.3125, "scoreKey": "vix_term_structure", "direction": "lower_better", "method": "level_percentile", "valueKey": "vix_term_structure", "format": "number", "source": "FRED VIXCLS / VXVCLS"},
            {"id": "risk_vs_safe", "remoteName": "Risk vs Safe", "name": "风险资产/美债代理", "weight": 0.3125, "scoreKey": "risk_vs_safe", "direction": "higher_better", "method": "level_percentile", "valueKey": "risk_vs_safe", "format": "number", "source": "FRED SP500 / DGS10 price proxy"},
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
