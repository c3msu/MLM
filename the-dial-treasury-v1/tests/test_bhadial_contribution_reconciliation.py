from __future__ import annotations

import unittest
from datetime import date, timedelta

from treasury_data.factor_groups import build_groups
from treasury_data.indicators import compute_indicators
from treasury_data.scoring_bhadial import (
    bhadial_conditions_score_at,
    bhadial_conditions_snapshot,
)
from treasury_data.sources import SeriesPoint, YieldCurveRecord


class BhadialContributionReconciliationTests(unittest.TestCase):
    @staticmethod
    def funding_series() -> dict[str, list[SeriesPoint]]:
        start = date(2026, 1, 2)
        dates = [start + timedelta(days=index) for index in range(30)]
        return {
            "corridor_sofr_iorb_deviation": [
                SeriesPoint(point_date, float(index if index < 29 else -10))
                for index, point_date in enumerate(dates)
            ],
            "cp_tbill_spread": [
                SeriesPoint(point_date, float(30 - index))
                for index, point_date in enumerate(dates)
            ],
            "funding_fragmentation": [
                SeriesPoint(point_date, float(index % 7))
                for index, point_date in enumerate(dates)
            ],
        }

    def test_smoothed_factor_attribution_reconciles_module_and_headline(self) -> None:
        series = self.funding_series()
        target = date(2026, 2, 1)

        score_row = bhadial_conditions_score_at(series, target, include_components=True)
        self.assertIsNotNone(score_row)
        assert score_row is not None
        funding = next(module for module in score_row["modules"] if module["name"] == "Funding")
        factors = funding["factors"]

        weighted_headline = sum(
            float(factor["headlineScore"]) * weight
            for factor, weight in zip(factors, (0.66, 0.23, 0.11))
        )
        self.assertAlmostEqual(weighted_headline, float(funding["score"]), places=12)
        self.assertTrue(
            any(
                abs(float(factor["headlineScore"]) - float(factor["score"])) > 1e-6
                for factor in factors
            )
        )

        snapshot = bhadial_conditions_snapshot(
            {"percentile_series": series},
            as_of=target,
        )
        funding_panel = next(module for module in snapshot["modules"] if module["name"] == "Funding")
        funding_components = [
            component
            for component in snapshot["components"]
            if component["module"] == "Funding"
        ]

        self.assertAlmostEqual(
            sum(float(component["rawContribution"]) for component in funding_components),
            float(funding_panel["rawContribution"]),
            places=5,
        )
        self.assertAlmostEqual(
            sum(float(component["headlineContribution"]) for component in funding_components),
            float(funding_panel["headlineContribution"]),
            places=5,
        )
        self.assertAlmostEqual(
            float(funding_panel["smoothingContribution"]),
            float(funding_panel["headlineContribution"]) - float(funding_panel["rawContribution"]),
            places=5,
        )

        audit = snapshot["contributionAudit"]
        self.assertAlmostEqual(
            float(audit["headlineContribution"]),
            float(snapshot["score"]) - 50.0,
            places=1,
        )
        self.assertAlmostEqual(float(audit["moduleResidual"]), 0.0, places=5)
        self.assertAlmostEqual(float(audit["factorResidual"]), 0.0, places=5)
        self.assertEqual(audit["headlineField"], "headlineContribution")
        self.assertEqual(audit["rawField"], "rawContribution")


class BhadialFactorGroupAlignmentTests(unittest.TestCase):
    @staticmethod
    def base_indicators() -> dict:
        values = {
            tenor: 4.0
            for tenor in ("1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y")
        }
        curves = [
            YieldCurveRecord(date(2026, 1, 1) + timedelta(days=index), values=values)
            for index in range(25)
        ]
        return compute_indicators(
            today=curves[-1],
            one_week=curves[-8],
            one_month=curves[0],
            curve_records=curves,
            fred={},
        )

    def test_legacy_factor_group_uses_the_same_transforms_as_composite(self) -> None:
        indicators = self.base_indicators()
        indicators["sofr_iorb_spread_bp"] = -1.0
        indicators["natgas"] = 2.5
        indicators["natgas_shock"] = 4.0
        indicators["percentiles"].update(
            {
                # Raw corridor level looks extreme, but its regime-normalized
                # deviation is quiet. Only the latter may vote.
                "corridor_sofr_iorb": 99,
                "corridor_sofr_iorb_deviation": 10,
                # Raw gas is cheap, but the positive shock is extreme. The
                # shock-only transform must drive the vote.
                "natgas": 10,
                "natgas_shock": 99,
            }
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

        corridor = factors["SOFR-IORB走廊摩擦"]
        self.assertEqual(corridor["score"], 0)
        self.assertIn("偏离历史p10", corridor["tag"])

        natgas = factors["天然气"]
        self.assertEqual(natgas["score"], -2)
        self.assertIn("冲击历史p99", natgas["tag"])
        self.assertEqual(natgas["sourceMode"], "derived-public")


if __name__ == "__main__":
    unittest.main()
