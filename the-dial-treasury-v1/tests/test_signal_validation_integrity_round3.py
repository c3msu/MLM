import math
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from treasury_data.signal_validation import (
    SortedSeries,
    apply_benjamini_hochberg,
    evaluate_alert_rule,
    evaluate_signal,
    fold_ic_stability,
    order_preserving_circular_shift_test,
    signal_validation_metric_row,
)
from treasury_data.sources import SeriesPoint


def daily_points(start: date, count: int) -> list[SeriesPoint]:
    return [
        SeriesPoint(start + timedelta(days=index), 100.0 * math.exp(0.00001 * index * index))
        for index in range(count)
    ]


def business_day_points(start: date, end: date) -> list[SeriesPoint]:
    points: list[SeriesPoint] = []
    current = start
    index = 0
    while current <= end:
        if current.weekday() < 5:
            points.append(SeriesPoint(current, 100.0 + index))
            index += 1
        current += timedelta(days=1)
    return points


class CircularShiftResolutionTests(unittest.TestCase):
    def test_complete_cyclic_group_includes_near_alignments_and_reports_resolution(self) -> None:
        pairs = [(float(index), float(index)) for index in range(60)]

        result = order_preserving_circular_shift_test(pairs, block_len=7)

        self.assertTrue(result["available"])
        self.assertTrue(result["nearAlignmentsIncluded"])
        self.assertEqual(result["excludedNearAlignmentRadius"], 0)
        self.assertTrue(result["completeCircularGroupUsed"])
        self.assertEqual(result["shiftsTested"], 59)
        self.assertAlmostEqual(result["minimumAttainablePValue"], 1 / 60)
        self.assertAlmostEqual(result["pValue"], 1 / 60)


class BenjaminiHochbergIntegrityTests(unittest.TestCase):
    def test_bh_uses_unrounded_randomization_p_and_each_rows_own_resolution(self) -> None:
        rows = [
            {
                "pValue3m": 0.025,
                "pValue3mAudit": {
                    "pValue": 0.02501,
                    "minimumAttainablePValue": 0.01,
                },
                "robust": True,
                "inferenceValid3m": True,
                "foldStability3m": {"stablePositive": True},
            },
            {
                "pValue3m": 0.8,
                "pValue3mAudit": {
                    "pValue": 0.8,
                    "minimumAttainablePValue": 0.04,
                },
                "robust": True,
                "inferenceValid3m": True,
                "foldStability3m": {"stablePositive": True},
            },
        ]

        apply_benjamini_hochberg(rows, alpha=0.10, family_size=4)

        self.assertEqual(rows[0]["fdrPValueInput"], 0.02501)
        # The displayed q-value rounds to 0.1000, but the exact 0.10004 input
        # must fail the alpha gate instead of being promoted by display rounding.
        self.assertEqual(rows[0]["fdrQValue3m"], 0.1)
        self.assertFalse(rows[0]["fdrSignificant3m"])
        self.assertFalse(rows[0]["actionableRobust"])
        self.assertEqual(
            rows[0]["fdrResolutionAudit"]["minimumAttainablePValue"],
            0.01,
        )
        self.assertTrue(rows[0]["fdrResolutionAudit"]["canRejectAsSoleDiscovery"])
        self.assertEqual(
            rows[1]["fdrResolutionAudit"]["minimumAttainablePValue"],
            0.04,
        )
        self.assertFalse(rows[1]["fdrResolutionAudit"]["canRejectAsSoleDiscovery"])


class FoldStabilityIntegrityTests(unittest.TestCase):
    def test_91d_folds_fail_closed_without_two_nonoverlapping_windows_per_fold(self) -> None:
        start = date(2020, 1, 1)
        prices = daily_points(start, 800)
        signals = [
            SeriesPoint(start + timedelta(days=7 * index), float(index))
            for index in range(100)
        ]

        result = fold_ic_stability(
            signals,
            prices,
            horizon_days=91,
            direction="higher_better",
        )

        self.assertFalse(result["available"])
        self.assertFalse(result["stablePositive"])
        self.assertEqual(result["overlapBlockLength"], 13)
        self.assertEqual(result["minimumNonOverlappingWindowsPerFold"], 2)
        self.assertIn("fewer than two folds", result["reason"])

    def test_unidentifiable_fold_cannot_be_silently_dropped(self) -> None:
        start = date(2024, 1, 1)
        prices: list[SeriesPoint] = []
        returns = [((index % 7) - 3) * 0.001 for index in range(120)]
        level = 100.0
        for index in range(120):
            prices.append(SeriesPoint(start + timedelta(days=index), level))
            level *= 1.0 + returns[index]
        signals = []
        for index in range(120):
            value = 1.0 if 77 <= index < 91 else returns[index]
            signals.append(SeriesPoint(start + timedelta(days=index), value))

        result = fold_ic_stability(
            signals,
            prices,
            horizon_days=1,
            direction="higher_better",
        )

        self.assertTrue(result["available"])
        self.assertFalse(result["allFoldsAvailable"])
        self.assertFalse(result["stablePositive"])


class PurgedCalibrationTests(unittest.TestCase):
    def test_purge_uses_actual_rolled_market_endpoint(self) -> None:
        prices = business_day_points(date(2023, 11, 1), date(2024, 5, 31))
        signals = [
            SeriesPoint(point.date, float(index % 11))
            for index, point in enumerate(prices)
            if date(2023, 12, 1) <= point.date <= date(2024, 1, 31)
        ]

        result = evaluate_signal(
            signals,
            prices,
            horizons=(3,),
            bootstrap_horizon_days=3,
            oos_start_date=date(2024, 1, 8),
        )
        horizon = result["horizons"][0]

        # Jan 3/4/5 nominal +3D endpoints fall on the weekend or boundary;
        # all roll to Jan 8 and therefore must be purged from calibration.
        self.assertEqual(horizon["calibrationPurgedOverlapCount"], 3)
        self.assertEqual(
            horizon["calibrationCandidateSampleSize"] - horizon["calibrationSampleSize"],
            3,
        )
        self.assertIn("actual first price endpoint", horizon["calibrationPurgeRule"])


class IndependentAlertEpisodeTests(unittest.TestCase):
    def test_persistent_alerts_count_once_and_only_first_alert_owns_outcome(self) -> None:
        start = date(2025, 1, 1)
        calibration = [
            {"date": start - timedelta(days=20 - index), "signal": 10.0 if index < 8 else 90.0}
            for index in range(10)
        ]
        evaluation: list[dict] = []
        first_episode = set(range(5, 10))
        second_episode = set(range(30, 35))
        for index in range(50):
            is_alert = index in first_episode or index in second_episode
            # Episode one is a hit at its first alert. Episode two only gets a
            # drawdown after its first alert, which must not extend the decision
            # window or retroactively turn the episode into a hit.
            is_event = index in first_episode or index in {31, 32, 33, 34}
            row_date = start + timedelta(days=index)
            evaluation.append(
                {
                    "date": row_date,
                    "signal": 90.0 if is_alert else 10.0,
                    "forwardDrawdown": -3.0 if is_event else -1.0,
                    "forwardDrawdownEndDate": row_date + timedelta(days=7),
                }
            )
        prices = SortedSeries(
            [SeriesPoint(start + timedelta(days=index), 100.0 - index * 0.1) for index in range(70)]
        )

        result = evaluate_alert_rule(
            calibration,
            evaluation,
            prices,
            direction="higher_risk",
            drawdown_threshold_pct=-2.0,
            drawdown_horizon_days=7,
            alert_percentile=80.0,
            spacing_days=1.0,
        )

        audit = result["alertIndependenceAudit"]
        self.assertEqual(audit["rawOosAlertObservationCount"], 10)
        self.assertEqual(audit["independentOosAlertCount"], 2)
        self.assertEqual(audit["independentOosHitCount"], 1)
        self.assertEqual(result["oosAlertCount"], 2)
        self.assertEqual(result["oosHitRate"], 0.5)
        self.assertIn("first alert's fixed forward label", audit["episodeOutcomeRule"])
        self.assertFalse(audit["overlappingLabelsCountedAsIndependent"])


class ClassificationEndpointTests(unittest.TestCase):
    def test_lead_lag_classification_uses_preregistered_91d_endpoint(self) -> None:
        start = date(2020, 1, 1)
        signals = [SeriesPoint(start + timedelta(days=index), float(index)) for index in range(40)]
        prices = daily_points(start, 140)
        fake_evaluation = {
            "available": True,
            "observationCount": 40,
            "calibrationCount": 26,
            "evaluationCount": 14,
            "oosStartDate": (start + timedelta(days=26)).isoformat(),
            "horizons": [
                {"days": 7, "ic": 0.1},
                {"days": 30, "ic": 0.9, "icOos": 0.9},
                {
                    "days": 91,
                    "ic": 0.11,
                    "icOos": 0.12,
                    "oosSampleSize": 14,
                    "oosEffectiveSampleSize": 2,
                    "robustOos": False,
                },
            ],
            "alert": {},
        }

        with (
            patch(
                "treasury_data.signal_validation.evaluate_signal",
                return_value=fake_evaluation,
            ),
            patch(
                "treasury_data.signal_validation.fold_ic_stability",
                return_value={"available": False, "stablePositive": False, "folds": []},
            ),
            patch(
                "treasury_data.signal_validation.classify_lead_lag",
                return_value="leading",
            ) as classify,
        ):
            row = signal_validation_metric_row(
                row_id="endpoint-audit",
                label="Endpoint audit",
                label_cn="端点审计",
                module="test",
                signal_points=signals,
                price_points=prices,
                prices_sorted=SortedSeries(prices),
                direction="higher_better",
            )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(classify.call_args.kwargs["forward_ic"], 0.12)
        self.assertEqual(row["classificationEndpointDays"], 91)
        self.assertEqual(row["classificationSelection"], "pre_registered_primary_endpoint")
        self.assertEqual(row["classificationSampleRole"], "oos_complete_91d_labels")
        self.assertEqual(row["classificationSampleSize"], 14)


if __name__ == "__main__":
    unittest.main()
