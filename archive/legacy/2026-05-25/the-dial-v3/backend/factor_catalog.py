"""Canonical 47-factor catalog used by the real-data pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


MODULE_META: Dict[str, Dict[str, Any]] = {
    "liquidity": {"name": "Liquidity", "name_cn": "流动性", "target_factors": 8},
    "funding": {"name": "Funding", "name_cn": "融资", "target_factors": 12},
    "treasury": {"name": "Treasury", "name_cn": "国债", "target_factors": 8},
    "rates": {"name": "Rates", "name_cn": "利率", "target_factors": 5},
    "credit": {"name": "Credit", "name_cn": "信用", "target_factors": 4},
    "risk": {"name": "Risk", "name_cn": "风险", "target_factors": 5},
    "external": {"name": "External", "name_cn": "外部", "target_factors": 5},
}


@dataclass(frozen=True)
class FactorDef:
    id: str
    module: str
    name: str
    name_cn: str
    display_only: bool
    weight: float
    direction: str
    frequency: str
    formula_id: str
    deps: Tuple[str, ...]
    format_hint: str
    params: Dict[str, Any] = field(default_factory=dict)


FACTOR_CATALOG: List[FactorDef] = [
    # Liquidity (8 total, 5 scored)
    FactorDef("liq_fed_balance_sheet", "liquidity", "Fed Balance Sheet", "美联储资产负债表", False, 0.2, "higher_better", "w", "direct", ("fred:WALCL",), "usd_bn"),
    FactorDef("liq_bank_reserves", "liquidity", "Bank Reserves", "银行准备金", False, 0.2, "higher_better", "w", "direct", ("fred:RESBALNS",), "usd_bn"),
    FactorDef("liq_tga_balance", "liquidity", "Treasury General Account", "TGA余额", True, 0.0, "lower_better", "d", "direct", ("fred:WTREGEN",), "usd_bn"),
    FactorDef("liq_on_rrp", "liquidity", "ON RRP", "隔夜逆回购", False, 0.2, "lower_better", "d", "direct", ("fred:RRPONTSYD",), "usd_bn"),
    FactorDef("liq_m2_growth_6m", "liquidity", "M2 6M Growth", "M2六个月增速", False, 0.2, "higher_better", "m", "pct_change", ("fred:M2SL",), "pct", {"window": 126}),
    FactorDef("liq_net_liquidity", "liquidity", "Net Liquidity", "净流动性", False, 0.2, "higher_better", "d", "net_liquidity", ("fred:WALCL", "fred:WTREGEN", "fred:RRPONTSYD"), "usd_bn"),
    FactorDef("liq_reserves_to_assets", "liquidity", "Reserves/Assets", "准备金占资产比", True, 0.0, "higher_better", "w", "ratio_pct", ("fred:RESBALNS", "fred:WALCL"), "pct"),
    FactorDef("liq_rrp_to_assets", "liquidity", "RRP/Assets", "RRP占资产比", True, 0.0, "lower_better", "d", "ratio_pct", ("fred:RRPONTSYD", "fred:WALCL"), "pct"),

    # Funding (12 total, 8 scored)
    FactorDef("fund_sofr", "funding", "SOFR", "SOFR", False, 0.125, "lower_better", "d", "direct", ("fred:SOFR",), "pct"),
    FactorDef("fund_effr", "funding", "Effective Fed Funds Rate", "EFFR", False, 0.125, "lower_better", "d", "direct", ("fred:EFFR",), "pct"),
    FactorDef("fund_ted_spread", "funding", "TED Spread", "TED利差", False, 0.125, "lower_better", "d", "direct", ("fred:TEDRATE",), "pct"),
    FactorDef("fund_obfr_sofr_spread", "funding", "OBFR-SOFR", "OBFR-SOFR利差", True, 0.0, "neutral", "d", "spread", ("fred:OBFR", "fred:SOFR"), "pct"),
    FactorDef("fund_tbill_3m", "funding", "3M T-Bill Yield", "3个月国库券利率", False, 0.125, "lower_better", "d", "direct", ("fred:DGS3MO",), "pct"),
    FactorDef("fund_ffr_effr_gap", "funding", "Fed Funds-EFFR Gap", "政策利率与EFFR偏离", True, 0.0, "neutral", "m", "spread", ("fred:FEDFUNDS", "fred:EFFR"), "pct"),
    FactorDef("fund_kre_vs_spy_1m", "funding", "KRE vs SPY (1M)", "银行股相对大盘(1M)", False, 0.125, "higher_better", "d", "relative_return", ("stooq:kre.us", "stooq:spy.us"), "pct", {"window": 21}),
    FactorDef("fund_hyg_vs_ief_1m", "funding", "HYG vs IEF (1M)", "高收益债相对中债(1M)", False, 0.125, "higher_better", "d", "relative_return", ("stooq:hyg.us", "stooq:ief.us"), "pct", {"window": 21}),
    FactorDef("fund_lqd_vs_ief_1m", "funding", "LQD vs IEF (1M)", "投资级债相对中债(1M)", False, 0.125, "higher_better", "d", "relative_return", ("stooq:lqd.us", "stooq:ief.us"), "pct", {"window": 21}),
    FactorDef("fund_iwm_vs_spy_1m", "funding", "IWM vs SPY (1M)", "小盘股相对大盘(1M)", False, 0.125, "higher_better", "d", "relative_return", ("stooq:iwm.us", "stooq:spy.us"), "pct", {"window": 21}),
    FactorDef("fund_sofr_change_3m", "funding", "SOFR 3M Change", "SOFR三个月变化", True, 0.0, "lower_better", "d", "diff", ("fred:SOFR",), "pct", {"window": 63}),
    FactorDef("fund_tbill_change_3m", "funding", "3M T-Bill Change", "3个月国库券三个月变化", True, 0.0, "lower_better", "d", "diff", ("fred:DGS3MO",), "pct", {"window": 63}),

    # Treasury (8 total, 5 scored)
    FactorDef("tsy_2y_yield", "treasury", "2Y Treasury Yield", "2年期美债收益率", False, 0.2, "lower_better", "d", "direct", ("fred:DGS2",), "pct"),
    FactorDef("tsy_10y_yield", "treasury", "10Y Treasury Yield", "10年期美债收益率", False, 0.2, "lower_better", "d", "direct", ("fred:DGS10",), "pct"),
    FactorDef("tsy_30y_yield", "treasury", "30Y Treasury Yield", "30年期美债收益率", True, 0.0, "lower_better", "d", "direct", ("fred:DGS30",), "pct"),
    FactorDef("tsy_10y2y_curve", "treasury", "10Y-2Y Curve", "10年-2年期限利差", False, 0.2, "higher_better", "d", "direct", ("fred:T10Y2Y",), "pct"),
    FactorDef("tsy_10y3m_curve", "treasury", "10Y-3M Curve", "10年-3个月期限利差", False, 0.2, "higher_better", "d", "spread", ("fred:DGS10", "fred:DGS3MO"), "pct"),
    FactorDef("tsy_10y_real_yield", "treasury", "10Y Real Yield", "10年期实际利率", True, 0.0, "lower_better", "d", "direct", ("fred:DFII10",), "pct"),
    FactorDef("tsy_10y_breakeven", "treasury", "10Y Breakeven", "10年通胀盈亏平衡", True, 0.0, "neutral", "d", "direct", ("fred:T10YIE",), "pct"),
    FactorDef("tsy_tlt_vs_ief_1m", "treasury", "TLT vs IEF (1M)", "长期债相对中债(1M)", False, 0.2, "higher_better", "d", "relative_return", ("stooq:tlt.us", "stooq:ief.us"), "pct", {"window": 21}),

    # Rates (5 total, 3 scored)
    FactorDef("rate_fedfunds", "rates", "Fed Funds Target", "联邦基金利率", False, 1.0 / 3.0, "lower_better", "m", "direct", ("fred:FEDFUNDS",), "pct"),
    FactorDef("rate_prime", "rates", "Prime Rate", "最优惠贷款利率", True, 0.0, "lower_better", "m", "direct", ("fred:MPRIME",), "pct"),
    FactorDef("rate_real_policy_rate", "rates", "Real Policy Rate", "实际政策利率", True, 0.0, "neutral", "m", "spread", ("fred:FEDFUNDS", "fred:T10YIE"), "pct"),
    FactorDef("rate_2y_change_3m", "rates", "2Y Yield 3M Change", "2年期收益率三个月变化", False, 1.0 / 3.0, "lower_better", "d", "diff", ("fred:DGS2",), "pct", {"window": 63}),
    FactorDef("rate_10y_vol_1m", "rates", "10Y Yield Volatility (1M)", "10年期收益率波动率(1M)", False, 1.0 / 3.0, "lower_better", "d", "rolling_std", ("fred:DGS10",), "pct", {"window": 21}),

    # Credit (4 total, 3 scored)
    FactorDef("cred_ig_oas", "credit", "IG OAS", "投资级利差", False, 1.0 / 3.0, "lower_better", "d", "direct", ("fred:BAMLC0A0CM",), "bp"),
    FactorDef("cred_hy_oas", "credit", "HY OAS", "高收益利差", False, 1.0 / 3.0, "lower_better", "d", "direct", ("fred:BAMLH0A0HYM2",), "bp"),
    FactorDef("cred_hy_ig_ratio", "credit", "HY/IG Spread Ratio", "高收益/投资级利差比", True, 0.0, "lower_better", "d", "ratio", ("fred:BAMLH0A0HYM2", "fred:BAMLC0A0CM"), "ratio"),
    FactorDef("cred_hyg_vs_lqd_1m", "credit", "HYG vs LQD (1M)", "高收益债相对投资级债(1M)", False, 1.0 / 3.0, "higher_better", "d", "relative_return", ("stooq:hyg.us", "stooq:lqd.us"), "pct", {"window": 21}),

    # Risk (5 total, 3 scored)
    FactorDef("risk_vix", "risk", "VIX", "VIX波动率指数", False, 1.0 / 3.0, "lower_better", "d", "direct", ("cboe:VIX",), "index"),
    FactorDef("risk_vxv_vix_ratio", "risk", "VXV/VIX", "VXV与VIX期限结构", True, 0.0, "higher_better", "d", "ratio", ("cboe:VXV", "cboe:VIX"), "ratio"),
    FactorDef("risk_ovx", "risk", "OVX", "原油波动率指数", True, 0.0, "lower_better", "d", "direct", ("cboe:OVX",), "index"),
    FactorDef("risk_spy_drawdown_1y", "risk", "SPY Drawdown (1Y)", "标普500一年回撤", False, 1.0 / 3.0, "higher_better", "d", "drawdown", ("stooq:spy.us",), "pct", {"window": 252}),
    FactorDef("risk_iwm_vs_spy_3m", "risk", "IWM vs SPY (3M)", "小盘股相对大盘(3M)", False, 1.0 / 3.0, "higher_better", "d", "relative_return", ("stooq:iwm.us", "stooq:spy.us"), "pct", {"window": 63}),

    # External (5 total, 3 scored)
    FactorDef("ext_dxy", "external", "US Dollar Index", "美元指数", False, 1.0 / 3.0, "lower_better", "d", "direct", ("fred:DTWEXBGS",), "index"),
    FactorDef("ext_eurusd", "external", "EUR/USD", "欧元兑美元", True, 0.0, "higher_better", "d", "direct", ("fred:DEXUSEU",), "fx"),
    FactorDef("ext_usdjpy", "external", "USD/JPY", "美元兑日元", True, 0.0, "neutral", "d", "direct", ("fred:DEXJPUS",), "fx"),
    FactorDef("ext_spy_vs_tlt_3m", "external", "SPY vs TLT (3M)", "风险资产相对国债(3M)", False, 1.0 / 3.0, "higher_better", "d", "relative_return", ("stooq:spy.us", "stooq:tlt.us"), "pct", {"window": 63}),
    FactorDef("ext_oil_vol", "external", "Oil Volatility", "原油波动率", False, 1.0 / 3.0, "lower_better", "d", "direct", ("cboe:OVX",), "index"),
]


def factor_map() -> Dict[str, FactorDef]:
    return {factor.id: factor for factor in FACTOR_CATALOG}


def module_factors(module_id: str) -> List[FactorDef]:
    return [factor for factor in FACTOR_CATALOG if factor.module == module_id]


def scored_factors() -> List[FactorDef]:
    return [factor for factor in FACTOR_CATALOG if not factor.display_only]


def display_factors() -> List[FactorDef]:
    return [factor for factor in FACTOR_CATALOG if factor.display_only]


def _validate_catalog() -> None:
    if len(FACTOR_CATALOG) != 47:
        raise AssertionError(f"factor count mismatch: {len(FACTOR_CATALOG)} != 47")

    scored_count = len(scored_factors())
    display_count = len(display_factors())
    if scored_count != 30:
        raise AssertionError(f"scored count mismatch: {scored_count} != 30")
    if display_count != 17:
        raise AssertionError(f"display count mismatch: {display_count} != 17")

    per_module: Dict[str, int] = {module_id: 0 for module_id in MODULE_META}
    per_module_weight: Dict[str, float] = {module_id: 0.0 for module_id in MODULE_META}

    for factor in FACTOR_CATALOG:
        if factor.module not in MODULE_META:
            raise AssertionError(f"unknown module in factor catalog: {factor.module}")
        if factor.direction not in {"higher_better", "lower_better", "neutral"}:
            raise AssertionError(f"invalid direction for {factor.id}: {factor.direction}")
        per_module[factor.module] += 1
        if factor.display_only and factor.weight != 0:
            raise AssertionError(f"display-only factor must have 0 weight: {factor.id}")
        if not factor.display_only and factor.weight <= 0:
            raise AssertionError(f"scored factor must have positive weight: {factor.id}")
        if not factor.display_only:
            per_module_weight[factor.module] += factor.weight

    for module_id, module_cfg in MODULE_META.items():
        target_count = module_cfg["target_factors"]
        if per_module[module_id] != target_count:
            raise AssertionError(
                f"module factor count mismatch for {module_id}: "
                f"{per_module[module_id]} != {target_count}"
            )

        if not (0.99 <= per_module_weight[module_id] <= 1.01):
            raise AssertionError(
                f"scored weight sum mismatch for {module_id}: {per_module_weight[module_id]:.4f}"
            )


_validate_catalog()
