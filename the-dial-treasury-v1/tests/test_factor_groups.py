import unittest
from datetime import date, timedelta

from treasury_data.dashboard_format import format_yield, parse_number
from treasury_data.build_dashboard import build_conclusion_audit, build_macro_liquidity_score
from treasury_data.factor_groups import (
    build_groups,
    cftc_leveraged_position_factor,
    growth_momentum_compatibility_factor,
    high_pressure_score,
    long_bond_auction_compatibility_factor,
    low_preference_score,
    macro_fundamental_factors,
    market_liquidity_compatibility_factor,
)
from treasury_data.indicators import compute_indicators
from treasury_data.scoring_bhadial import bhadial_conditions_snapshot, bhadial_factor
from treasury_data.sources import (
    CftcTreasuryPosition,
    SeriesPoint,
    TicHolding,
    TicHoldings,
    TimeSeries,
    YieldCurveRecord,
)


class FactorGroupTests(unittest.TestCase):
    def test_indicator_availability_distinguishes_missing_sources_from_zero(self):
        values = {
            "1M": 4.0,
            "3M": 4.0,
            "6M": 4.0,
            "1Y": 4.0,
            "2Y": 4.0,
            "3Y": 4.0,
            "5Y": 4.0,
            "7Y": 4.0,
            "10Y": 4.0,
            "20Y": 4.0,
            "30Y": 4.0,
        }
        curves = [
            YieldCurveRecord(date=date(2026, 1, 1) + timedelta(days=index), values=values)
            for index in range(3)
        ]

        indicators = compute_indicators(
            today=curves[-1],
            one_week=curves[0],
            one_month=curves[0],
            curve_records=curves,
            fred={},
        )

        self.assertEqual(indicators["unrate"], 0.0)
        self.assertFalse(indicators["availability"]["unrate"])
        self.assertFalse(indicators["availability"]["payroll_change_k"])
        self.assertFalse(indicators["availability"]["hy_oas"])
        self.assertFalse(indicators["availability"]["dff"])
        self.assertFalse(indicators["availability"]["sofr"])
        self.assertFalse(indicators["availability"]["rrp_trillions"])
        self.assertFalse(indicators["availability"]["real_10y"])
        self.assertFalse(indicators["availability"]["breakeven_10y"])
        self.assertEqual(indicators["target_range"], "--")
        self.assertFalse(indicators["availability"]["ten_year_realized_vol_20d_bp"])

        groups = build_groups(
            indicators,
            auctions=[],
            cftc_positions=[],
            tic_holdings=None,
            acm=None,
            primary_dealer_stats=None,
            quarterly_refunding=None,
            debt_limit_status=None,
            official_news=[],
        )
        by_name = {
            factor["n"]: factor
            for group in groups
            for factor in group.get("factors", [])
            if isinstance(factor, dict) and factor.get("n")
        }
        for name in ("联邦基金目标利率", "SOFR 融资锚", "实际利率", "盈亏平衡通胀", "ON RRP"):
            self.assertEqual(by_name[name]["score"], 0)
            self.assertEqual(by_name[name]["sourceMode"], "manual-placeholder")
            self.assertFalse(by_name[name]["auditEligible"])

        for name in (
            "SOFR-EFFR利差",
            "SOFR-OBFR回购摩擦",
            "真实利率水平",
            "真实曲线(10Y-5Y)",
            "10Y实现波动率",
            "银行准备金",
            "净流动性",
            "HY信用偏好(HY/UST)",
            "期限溢价 (ACM)",
            "发行节奏 / QRA",
            "债务上限空间",
            "TGA 与现金管理",
            "拍卖需求",
            "TIC 海外持仓",
        ):
            self.assertEqual(by_name[name]["tag"], "数据不足")
            self.assertEqual(by_name[name]["sourceMode"], "manual-placeholder")
            self.assertFalse(by_name[name]["auditEligible"])

        for name in ("SOMA Treasury持仓", "资产负债表 / 总资产"):
            self.assertEqual(by_name[name]["tag"], "--")
            self.assertEqual(by_name[name]["sourceMode"], "manual-placeholder")
            self.assertFalse(by_name[name]["auditEligible"])

        # The mandatory Treasury curve is real evidence even when its actual
        # curvature reading is exactly neutral.
        self.assertEqual(by_name["曲线曲率(绝对值)"]["score"], 0)
        self.assertEqual(by_name["曲线曲率(绝对值)"]["sourceMode"], "derived-public")
        self.assertTrue(by_name["曲线曲率(绝对值)"]["auditEligible"])

    def test_ranked_neutral_factor_remains_auditable_evidence(self):
        factor = bhadial_factor(
            module="Funding",
            name="neutral",
            tag="0bp · 50th pct",
            value="正常",
            score=0,
            source_mode="derived-public",
            note="fixture",
            evidence_available=True,
        )

        self.assertEqual(factor["score"], 0)
        self.assertEqual(factor["sourceMode"], "derived-public")
        self.assertTrue(factor["auditEligible"])
        self.assertEqual(factor["evidenceStatus"], "available")

    def test_curve_volatility_and_curvature_use_ranked_complete_windows(self):
        values = {
            "1M": 4.0,
            "3M": 4.0,
            "6M": 4.0,
            "1Y": 4.0,
            "2Y": 4.0,
            "3Y": 4.0,
            "5Y": 4.0,
            "7Y": 4.0,
            "10Y": 4.0,
            "20Y": 4.0,
            "30Y": 4.0,
        }
        curves = [
            YieldCurveRecord(date=date(2026, 1, 1) + timedelta(days=index), values=values)
            for index in range(24)
        ]
        indicators = compute_indicators(
            today=curves[-1],
            one_week=curves[-6],
            one_month=curves[0],
            curve_records=curves,
            fred={},
        )
        groups = build_groups(
            indicators,
            auctions=[],
            cftc_positions=[],
            tic_holdings=None,
            acm=None,
            primary_dealer_stats=None,
            quarterly_refunding=None,
            debt_limit_status=None,
            official_news=[],
        )
        factors = {
            factor["n"]: factor
            for group in groups
            for factor in group.get("factors", [])
            if isinstance(factor, dict) and factor.get("n")
        }

        realized_vol = factors["10Y实现波动率"]
        self.assertEqual(indicators["percentiles"]["treasury_10y_vol_21d"], 50)
        self.assertEqual(realized_vol["score"], 0)
        self.assertTrue(realized_vol["auditEligible"])
        self.assertIn("21D", realized_vol["tag"])
        self.assertIn("完整日变动窗口", realized_vol["note"])

        curvature = factors["曲线曲率(绝对值)"]
        self.assertEqual(indicators["percentiles"]["curve_curvature_abs"], 50)
        self.assertEqual(curvature["score"], 0)
        self.assertTrue(curvature["auditEligible"])
        self.assertIn("非等距线性弦", curvature["note"])

    def test_policy_anchors_and_curve_factors_use_observed_direction_not_presence(self):
        base_values = {
            "1M": 0.5,
            "3M": 0.6,
            "6M": 0.7,
            "1Y": 0.8,
            "2Y": 4.5,
            "3Y": 4.3,
            "5Y": 4.0,
            "7Y": 3.9,
            "10Y": 3.8,
            "20Y": 3.6,
            "30Y": 3.5,
        }
        curves = [
            YieldCurveRecord(date=date(2026, 1, 1) + timedelta(days=index), values=base_values)
            for index in range(24)
        ]
        fred = {
            "DFF": TimeSeries("DFF", [SeriesPoint(curves[-1].date, 0.5)]),
            "SOFR": TimeSeries("SOFR", [SeriesPoint(curves[-1].date, 0.6)]),
        }
        indicators = compute_indicators(
            today=curves[-1],
            one_week=curves[-6],
            one_month=curves[0],
            curve_records=curves,
            fred=fred,
        )
        groups = build_groups(
            indicators,
            auctions=[],
            cftc_positions=[],
            tic_holdings=None,
            acm=None,
            primary_dealer_stats=None,
            quarterly_refunding=None,
            debt_limit_status=None,
            official_news=[],
        )
        factors = {
            factor["n"]: factor
            for group in groups
            for factor in group.get("factors", [])
            if isinstance(factor, dict) and factor.get("n")
        }

        self.assertEqual(factors["联邦基金目标利率"]["score"], 1)
        self.assertEqual(factors["联邦基金目标利率"]["v"], "宽松")
        self.assertEqual(factors["SOFR 融资锚"]["score"], 1)
        self.assertEqual(factors["SOFR 融资锚"]["v"], "低位")
        self.assertEqual(factors["5s30s 曲线"]["v"], "倒挂")
        self.assertEqual(factors["5s30s 曲线"]["curve"], -1)
        self.assertEqual(factors["2s10s 曲线"]["v"], "倒挂")
        self.assertEqual(factors["2s10s 曲线"]["curve"], -1)

    def test_stale_monthly_tic_is_visible_but_cannot_vote_in_conclusion(self):
        values = {
            "1M": 4.0,
            "3M": 4.0,
            "6M": 4.0,
            "1Y": 4.0,
            "2Y": 4.0,
            "3Y": 4.0,
            "5Y": 4.0,
            "7Y": 4.0,
            "10Y": 4.0,
            "20Y": 4.0,
            "30Y": 4.0,
        }
        curves = [
            YieldCurveRecord(date=date(2026, 7, 1) + timedelta(days=index), values=values)
            for index in range(3)
        ]
        indicators = compute_indicators(
            today=curves[-1],
            one_week=curves[0],
            one_month=curves[0],
            curve_records=curves,
            fred={},
        )
        total = TicHolding("Total", 9_000.0, -120.0)
        groups = build_groups(
            indicators,
            auctions=[],
            cftc_positions=[],
            tic_holdings=TicHoldings("2026-01", [total], total, None),
            acm=None,
            primary_dealer_stats=None,
            quarterly_refunding=None,
            debt_limit_status=None,
            official_news=[],
            as_of=date(2026, 7, 13),
        )
        tic = next(
            factor
            for group in groups
            for factor in group.get("factors", [])
            if factor.get("n") == "TIC 海外持仓"
        )

        self.assertIn("2026-01", tic["tag"])
        self.assertEqual(tic["v"], "数据过期")
        self.assertEqual(tic["score"], 0)
        self.assertEqual(tic["curve"], 0)
        self.assertFalse(tic["auditEligible"])
        self.assertEqual(tic["evidenceStatus"], "stale")
        self.assertGreater(tic["ageDays"], tic["expectedMaxAgeDays"])
        self.assertIn("不进入结论分母", tic["note"])

    def test_conclusion_audit_ignores_manual_placeholders(self):
        base = [{"id": "g1", "name": "A", "weight": 100, "factors": [{"n": "evidence", "score": 1, "curve": 0}]}]
        with_placeholders = [
            {
                **base[0],
                "factors": [
                    *base[0]["factors"],
                    *[
                        {"n": f"missing-{index}", "score": 0, "curve": 0, "sourceMode": "manual-placeholder", "auditEligible": False}
                        for index in range(5)
                    ],
                ],
            }
        ]

        self.assertEqual(build_conclusion_audit(base)["duration"], build_conclusion_audit(with_placeholders)["duration"])

    def test_missing_macro_sources_remain_neutral_and_visible(self):
        indicators = {
            "availability": {
                "cpi_yoy": False,
                "pce_yoy": False,
                "core_pce_yoy": False,
                "trimmed_mean_pce_yoy": False,
                "ppi_yoy": False,
                "unrate": False,
                "payroll_change_k": False,
            },
            "cpi_yoy": 0.0,
            "pce_yoy": 0.0,
            "core_pce_yoy": 0.0,
            "trimmed_mean_pce_yoy": 0.0,
            "ppi_yoy": 0.0,
            "unrate": 0.0,
            "payroll_change_k": 0.0,
        }

        factors = macro_fundamental_factors(indicators)

        self.assertTrue(all(factor["score"] == 0 for factor in factors))
        self.assertTrue(all(factor["v"] == "数据不足" for factor in factors))
        self.assertTrue(all(factor["sourceMode"] == "manual-placeholder" for factor in factors))
        self.assertIn("CPI --", factors[0]["tag"])

    def test_partial_inflation_data_can_flag_pressure_but_not_claim_full_evidence(self):
        indicators = {
            "availability": {
                "cpi_yoy": True,
                "pce_yoy": False,
                "core_pce_yoy": False,
                "trimmed_mean_pce_yoy": False,
                "ppi_yoy": False,
                "unrate": False,
                "payroll_change_k": False,
            },
            "cpi_yoy": 3.8,
            "pce_yoy": 0.0,
            "core_pce_yoy": 0.0,
            "trimmed_mean_pce_yoy": 0.0,
            "ppi_yoy": 0.0,
            "unrate": 0.0,
            "payroll_change_k": 0.0,
        }

        inflation = macro_fundamental_factors(indicators)[0]

        self.assertEqual(inflation["score"], -2)
        self.assertEqual(inflation["sourceMode"], "proxy-public")
        self.assertIn("PCE --", inflation["tag"])

    def test_compatibility_factors_do_not_turn_missing_inputs_into_normal(self):
        indicators = {
            "availability": {
                "payroll_change_k": False,
                "unrate": False,
                "ten_year_realized_vol_20d_bp": False,
                "hy_oas": False,
            },
            "payroll_change_k": 0.0,
            "unrate": 0.0,
            "ten_year_realized_vol_20d_bp": 0.0,
            "hy_oas": 0.0,
        }

        growth = growth_momentum_compatibility_factor(indicators)
        liquidity = market_liquidity_compatibility_factor(indicators)

        for factor in (growth, liquidity):
            self.assertEqual(factor["score"], 0)
            self.assertEqual(factor["v"], "数据不足")
            self.assertEqual(factor["sourceMode"], "manual-placeholder")
            self.assertIn("--", factor["tag"])

    def test_unsettled_long_bond_auction_is_not_labeled_neutral_demand(self):
        factor = long_bond_auction_compatibility_factor(
            [
                {
                    "auctionDate": "2026-07-10",
                    "securityTerm": "30-Year",
                    "securityType": "Bond",
                    "highYield": "5.01",
                    "bidToCoverRatio": "nan",
                }
            ]
        )

        self.assertEqual(factor["score"], 0)
        self.assertEqual(factor["v"], "数据不足")
        self.assertEqual(factor["sourceMode"], "manual-placeholder")
        self.assertIn("btc待结果", factor["tag"])

    def test_cftc_cross_tenor_signal_uses_median_percent_open_interest(self):
        report_date = date(2026, 7, 7)
        positions = [
            CftcTreasuryPosition(report_date, "2Y", 1_000_000, 0, 0, -80_000, -8.0),
            CftcTreasuryPosition(report_date, "10Y", 100_000, 0, 0, -7_000, -7.0),
            # A very large raw long in one contract must not dominate the
            # cross-tenor signal after per-contract %OI normalization.
            CftcTreasuryPosition(report_date, "30Y", 2_000_000, 0, 0, 1_200_000, 60.0),
        ]

        factor = cftc_leveraged_position_factor(positions)

        self.assertEqual(factor["medianLeveragedNetPctOi"], -7.0)
        self.assertEqual(factor["score"], 1)
        self.assertEqual(factor["sourceMode"], "real-public")
        self.assertTrue(factor["auditEligible"])
        self.assertEqual(factor["aggregation"], "unweighted-median-leveraged-net-pct-open-interest")
        self.assertIn("-7.00% OI", factor["tag"])

    def test_cftc_cross_tenor_signal_fails_closed_below_minimum_sample(self):
        report_date = date(2026, 7, 7)
        factor = cftc_leveraged_position_factor(
            [
                CftcTreasuryPosition(report_date, "2Y", 1_000, 0, 0, -100, -10.0),
                CftcTreasuryPosition(report_date, "10Y", 2_000, 0, 0, -200, -10.0),
            ]
        )

        self.assertEqual(factor["score"], 0)
        self.assertEqual(factor["tag"], "数据不足")
        self.assertEqual(factor["sourceMode"], "manual-placeholder")
        self.assertFalse(factor["auditEligible"])

    def test_threshold_helpers_keep_boundary_semantics(self):
        self.assertEqual(high_pressure_score(None), 0)
        self.assertEqual(high_pressure_score(79), 0)
        self.assertEqual(high_pressure_score(80), -1)
        self.assertEqual(high_pressure_score(95), -2)
        self.assertEqual(low_preference_score(None), 0)
        self.assertEqual(low_preference_score(10), -2)
        self.assertEqual(low_preference_score(25), -1)
        self.assertEqual(low_preference_score(80), 1)

    def test_shared_numeric_parsers_reject_non_finite_values(self):
        self.assertIsNone(parse_number("nan"))
        self.assertIsNone(parse_number("inf"))
        self.assertEqual(format_yield("nan"), "--")
        self.assertEqual(format_yield("5.01"), "5.010%")

    def test_conditions_snapshot_marks_unobserved_active_factors_as_missing(self):
        indicators = {
            "percentile_series": {
                "net_liquidity": [
                    SeriesPoint(date(2026, 1, 1), 0.9),
                    SeriesPoint(date(2026, 2, 1), 1.0),
                ]
            },
            "net_liquidity_trillions": 1.0,
            "net_liquidity_13w_change_trillions": 0.0,
        }
        snapshot = bhadial_conditions_snapshot(indicators, as_of=date(2026, 2, 3))
        components = {component["id"]: component for component in snapshot["components"]}

        self.assertEqual(snapshot["factorCount"], 21)
        self.assertEqual(snapshot["observedFactorCount"], 1)
        self.assertEqual(snapshot["scoredFactorCount"], 0)
        self.assertEqual(snapshot["coveragePct"], 5)
        self.assertEqual(snapshot["scoredCoveragePct"], 0)
        self.assertEqual(snapshot["score"], snapshot["legacyFixedScore"])
        self.assertEqual(snapshot["reliabilityScore"], 50.0)
        self.assertTrue(components["fed_net_liquidity"]["observed"])
        self.assertFalse(components["fed_net_liquidity"]["scoreEligible"])
        self.assertEqual(components["fed_net_liquidity"]["freshnessStatus"], "fresh")
        self.assertEqual(components["fed_net_liquidity"]["scoringStatus"], "warming")
        self.assertEqual(components["fed_net_liquidity"]["effectiveSampleCount"], 2)
        self.assertEqual(components["fed_net_liquidity"]["observationDate"], "2026-02-01")
        self.assertEqual(components["fed_net_liquidity"]["ageDays"], 2)
        self.assertFalse(components["delta_net_liq_13w"]["observed"])
        self.assertEqual(components["delta_net_liq_13w"]["freshnessStatus"], "missing")
        self.assertEqual(components["delta_net_liq_13w"]["value"], "--")
        self.assertEqual(components["delta_net_liq_13w"]["direction"], "missing")
        self.assertEqual(components["delta_net_liq_13w"]["contribution"], 0.0)

        panel = build_macro_liquidity_score(indicators, as_of=date(2026, 2, 3))
        self.assertEqual(panel["coveragePct"], 5)
        self.assertEqual(panel["activeFactorCount"], 21)
        self.assertEqual(panel["scoredFactorCount"], 0)
        self.assertEqual(panel["scoredCoveragePct"], 0)
        self.assertEqual(panel["effectiveWeightCoveragePct"], 0)
        self.assertEqual(len(panel["focusComponents"]), 0)
        self.assertTrue(all(component["scoreEligible"] for component in panel["focusComponents"]))
        self.assertEqual(sum(row["count"] for row in panel["balance"]), 0)
        self.assertEqual(panel["hiddenComponentCount"], 0)


if __name__ == "__main__":
    unittest.main()
