from __future__ import annotations

import unittest
from datetime import date, timedelta

from treasury_data.scoring_spy_warning import (
    build_spy_component_sleeve,
    build_spy_warning_rule_audit,
    spy_components_from_bhadial_score_row,
    spy_early_warning_snapshot,
)
from treasury_data.signal_validation import SortedSeries
from treasury_data.sources import SeriesPoint
from treasury_data.validation_build import BhadialWeeklyReplay


class SpyWarningEvidenceIntegrityTests(unittest.TestCase):
    @staticmethod
    def component(component_id: str, score: float, *, eligible: bool) -> dict:
        return {
            "id": component_id,
            "name": component_id,
            "score": score,
            "scoreEligible": eligible,
            "observed": eligible,
            "freshnessStatus": "fresh" if eligible else "stale",
            "scoringStatus": "scored" if eligible else "stale",
        }

    def test_zero_coverage_neutral_placeholder_cannot_publish_spy_warning(self) -> None:
        warning = spy_early_warning_snapshot(
            {
                "score": 50.0,
                "reliabilityScore": 50.0,
                "effectiveWeightCoveragePct": 0.0,
                "scoredFactorCount": 0,
                "scoreContract": "legacy-fixed-weight-compatible",
                "components": [self.component("fed_net_liquidity", 50.0, eligible=True)],
            }
        )

        self.assertFalse(warning["available"])
        self.assertIsNone(warning["score"])
        self.assertIsNone(warning["allocation"].get("exposureBandPct"))
        self.assertIn("有效覆盖不足", warning["summary"])

    def test_explicitly_stale_factor_does_not_dilute_sleeve_denominator(self) -> None:
        spec = {
            "key": "fundingStress",
            "label": "融资压力",
            "weight": 0.24,
            "componentIds": ["corridor_friction_1", "cp_tbill_spread", "fragmentation_21d"],
        }
        sleeve = build_spy_component_sleeve(
            spec,
            {
                "corridor_friction_1": self.component("corridor_friction_1", 80.0, eligible=True),
                "cp_tbill_spread": self.component("cp_tbill_spread", 50.0, eligible=False),
                "fragmentation_21d": self.component("fragmentation_21d", 40.0, eligible=True),
            },
        )

        # Eligible risks are 20 and 60, so the sleeve is 40. Counting the stale
        # compatibility placeholder would have incorrectly produced 43.3.
        self.assertTrue(sleeve["available"])
        self.assertEqual(sleeve["score"], 40.0)
        self.assertEqual(sleeve["detail"], "2/3 factors")

    def test_historical_component_adapter_preserves_factor_eligibility(self) -> None:
        components = spy_components_from_bhadial_score_row(
            {
                "modules": [
                    {
                        "factors": [
                            {
                                "id": "cp_tbill_spread",
                                "score": 50.0,
                                "observed": False,
                                "scoreEligible": False,
                                "freshnessStatus": "stale",
                                "scoringStatus": "stale",
                            }
                        ]
                    }
                ]
            }
        )
        cp_tbill = next(row for row in components if row["id"] == "cp_tbill_spread")

        self.assertFalse(cp_tbill["observed"])
        self.assertFalse(cp_tbill["scoreEligible"])
        self.assertEqual(cp_tbill["freshnessStatus"], "stale")

    def test_weekly_replay_components_expose_neutralized_values_as_ineligible(self) -> None:
        replay = BhadialWeeklyReplay({})
        snapshot = replay.composite_at(date(2026, 7, 17), include_components=True)
        fed_liquidity = next(
            row for row in snapshot["components"] if row["id"] == "fed_net_liquidity"
        )

        self.assertEqual(fed_liquidity["score"], 50.0)
        self.assertFalse(fed_liquidity["observed"])
        self.assertFalse(fed_liquidity["scoreEligible"])

    def test_rule_forward_mean_uses_same_oos_population_as_its_baseline(self) -> None:
        start = date(2020, 1, 3)
        weeks = [start + timedelta(days=7 * index) for index in range(100)]
        prices = SortedSeries(
            [SeriesPoint(point_date, 100.0 + index) for index, point_date in enumerate(weeks)]
        )
        audit = build_spy_warning_rule_audit(
            {
                "rule": [
                    {"date": weeks[10], "trailing3m": 0.0},
                    {"date": weeks[70], "trailing3m": 0.0},
                ]
            },
            {"rule": {"label": "test", "kind": "amplifier", "scoreEffect": 1.0}},
            weeks,
            prices,
        )
        row = audit["rules"][0]
        expected_oos_return = round((183.0 / 170.0 - 1.0) * 100.0, 2)

        self.assertEqual(row["avgForward3mAfterFire"], expected_oos_return)
        self.assertEqual(row["avgForward3mSample"], "oos_complete_91d")
        self.assertEqual(row["avgForward3mSampleSize"], 1)


if __name__ == "__main__":
    unittest.main()
