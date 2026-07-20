import math
import unittest
from datetime import date

from treasury_data.scoring_bhadial import (
    BHADIAL_CONDITION_MODULES,
    bhadial_conditions_snapshot,
    bhadial_factor_score_at,
)
from treasury_data.series_math import funding_fragmentation_points
from treasury_data.sources import SeriesPoint, TimeSeries


class BhadialAvailabilityAuditTests(unittest.TestCase):
    @staticmethod
    def factor(factor_id: str) -> dict[str, object]:
        return next(
            factor
            for module in BHADIAL_CONDITION_MODULES
            for factor in module["factors"]
            if factor["id"] == factor_id
        )

    def test_nfci_lag_matches_friday_observation_to_wednesday_release(self) -> None:
        # Chicago Fed publishes Wednesday at 08:30 ET for the week through the
        # previous Friday: five calendar days under this date-grain contract.
        nfci = self.factor("nfci")

        self.assertEqual(nfci["publicationLagDays"], 5)

        points = [
            SeriesPoint(date(2026, 1, 2), -0.2),
            SeriesPoint(date(2026, 1, 9), -0.1),
        ]
        before_release = bhadial_factor_score_at(
            {"nfci": points}, nfci, date(2026, 1, 13)
        )
        on_release = bhadial_factor_score_at(
            {"nfci": points}, nfci, date(2026, 1, 14)
        )

        self.assertEqual(before_release["observationDate"], "2026-01-02")
        self.assertEqual(on_release["observationDate"], "2026-01-09")
        self.assertEqual(on_release["availabilityDate"], "2026-01-14")
        self.assertEqual(on_release["availableAgeDays"], 0)

    def test_snapshot_separates_observation_age_from_availability_age(self) -> None:
        indicators = {
            "percentile_series": {
                "net_liquidity": [
                    SeriesPoint(date(2026, 1, 1), 1_000_000.0),
                    SeriesPoint(date(2026, 1, 2), 1_100_000.0),
                    SeriesPoint(date(2026, 1, 3), 1_200_000.0),
                    SeriesPoint(date(2026, 1, 4), 9_000_000.0),
                ]
            }
        }

        snapshot = bhadial_conditions_snapshot(indicators, as_of=date(2026, 1, 5))
        component = next(
            row for row in snapshot["components"] if row["id"] == "fed_net_liquidity"
        )

        self.assertEqual(component["observationDate"], "2026-01-03")
        self.assertEqual(component["observationAgeDays"], 2)
        self.assertEqual(component["ageDays"], 2)
        self.assertEqual(component["availabilityDate"], "2026-01-05")
        self.assertEqual(component["availableAgeDays"], 0)
        self.assertEqual(component["availabilityCutoff"], "2026-01-03")
        self.assertEqual(component["publicationLagDays"], 2)
        self.assertEqual(component["publicationLagBasis"], "calendar_days")


class FundingFragmentationNormalizationTests(unittest.TestCase):
    def test_current_shock_is_not_in_its_own_robust_reference_window(self) -> None:
        dates = [date(2026, 1, day) for day in (1, 2, 3, 4)]
        sofr = TimeSeries("SOFR", [SeriesPoint(point_date, 5.0) for point_date in dates])

        def leg(name: str, offsets_bp: list[float]) -> TimeSeries:
            return TimeSeries(
                name,
                [
                    SeriesPoint(point_date, 5.0 - offset / 100)
                    for point_date, offset in zip(dates, offsets_bp)
                ],
            )

        points = funding_fragmentation_points(
            sofr,
            leg("OBFR", [-1.0, 0.0, 1.0, 10.0]),
            leg("IORB", [-1.0, 0.0, 1.0, 0.0]),
            leg("RRP", [-1.0, 0.0, 1.0, -10.0]),
            z_window=3,
            smooth_window=1,
        )

        prior_only_z = 10.0 / 1.4826
        expected_dispersion = prior_only_z * math.sqrt(2 / 3)
        self.assertAlmostEqual(points[-1].value, expected_dispersion, places=12)

    def test_flat_prior_baseline_does_not_hide_a_real_corridor_break(self) -> None:
        dates = [date(2026, 2, day) for day in (2, 3, 4, 5)]
        sofr = TimeSeries("SOFR", [SeriesPoint(point_date, 5.0) for point_date in dates])

        def leg(name: str, offsets_bp: list[float]) -> TimeSeries:
            return TimeSeries(
                name,
                [
                    SeriesPoint(point_date, 5.0 - offset / 100)
                    for point_date, offset in zip(dates, offsets_bp)
                ],
            )

        points = funding_fragmentation_points(
            sofr,
            leg("OBFR", [0.0, 0.0, 0.0, 5.0]),
            leg("IORB", [0.0, 0.0, 0.0, 0.0]),
            leg("RRP", [0.0, 0.0, 0.0, -5.0]),
            z_window=3,
            smooth_window=1,
        )

        self.assertAlmostEqual(points[-1].value, 5.0 * math.sqrt(2 / 3), places=12)


if __name__ == "__main__":
    unittest.main()
