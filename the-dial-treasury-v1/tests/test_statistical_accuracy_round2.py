import math
import random
import unittest
from datetime import date, timedelta

from treasury_data.scoring_equity import (
    equity_backtest_component_diagnostics,
    equity_backtest_linear_regression,
    equity_high_precision_threshold,
    equity_recommended_caution_threshold,
    equity_walk_forward_backtest,
    equity_weight_calibration_summary,
)
from treasury_data.signal_validation import (
    SortedSeries,
    apply_benjamini_hochberg,
    evaluate_signal,
    order_preserving_circular_shift_test,
    signal_validation_metric_row,
)
from treasury_data.sources import SeriesPoint


def observation(
    index: int,
    *,
    score: float,
    event: bool,
    label_end: date | None,
) -> dict:
    target = date(2025, 1, 1) + timedelta(days=index)
    return {
        "date": target.isoformat(),
        "score": score,
        "maxDrawdown15d": -3.0 if event else -1.0,
        "drawdownEvent15d": event,
        "forward15d": -1.0 if event else 1.0,
        "drawdownLeadDays15d": 3 if event else None,
        "labelEndDate15d": label_end.isoformat() if label_end else None,
    }


def business_day_prices(
    *,
    start: date,
    calendar_days: int,
    seed: int = 9,
) -> list[SeriesPoint]:
    rng = random.Random(seed)
    level = 100.0
    points: list[SeriesPoint] = []
    for index in range(calendar_days):
        point_date = start + timedelta(days=index)
        if point_date.weekday() >= 5:
            continue
        level *= 1.0 + rng.uniform(-0.01, 0.01)
        points.append(SeriesPoint(point_date, level))
    return points


class EquityWalkForwardAccuracyTests(unittest.TestCase):
    def test_impossible_lift_gate_does_not_publish_over_100_percent_requirement(self) -> None:
        caution = equity_recommended_caution_threshold(
            [
                {
                    "threshold": 60,
                    "sampleSize": 100,
                    "alertDays": 10,
                    "precision": 100.0,
                    "recall": 10.0,
                    "baseRate": 100.0,
                }
            ]
        )
        high_precision = equity_high_precision_threshold(
            [
                {
                    "threshold": 80,
                    "sampleSize": 100,
                    "alertDays": 10,
                    "precision": 100.0,
                    "recall": 10.0,
                    "baseRate": 100.0,
                }
            ]
        )

        self.assertFalse(caution["available"])
        self.assertEqual(caution["minimumPrecision"], 100.0)
        self.assertGreater(caution["requiredPrecisionUncapped"], 100.0)
        self.assertFalse(high_precision["available"])
        self.assertEqual(high_precision["minimumPrecision"], 100.0)
        self.assertGreater(high_precision["requiredPrecisionUncapped"], 100.0)

    def test_overlapping_forward_regression_uses_hac_standard_error(self) -> None:
        rows = [
            {
                "score": float(index),
                "forward": 0.15 * index + 2.0 * ((index // 5) % 2),
            }
            for index in range(60)
        ]

        result = equity_backtest_linear_regression(
            rows,
            key="forward",
            target="forward10d",
            label="10D forward return",
            unit="pct",
            summary_template="delta {delta}",
            hac_lag=9,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["standardErrorMethod"], "Newey-West HAC")
        self.assertEqual(result["hacLag"], 9)
        self.assertFalse(result["productionUse"])
        self.assertIsNotNone(result["tStat"])

    def test_threshold_selection_fails_closed_when_calibration_gate_fails(self) -> None:
        rows = [
            observation(
                index,
                score=60.0 if index % 2 == 0 else 30.0,
                event=index % 2 == 1,
                label_end=date(2025, 1, 1) + timedelta(days=index),
            )
            for index in range(60)
        ]

        result = equity_walk_forward_backtest(rows, -2.0, horizon=15)

        self.assertTrue(result["available"])
        self.assertFalse(result["thresholdSelectionAvailable"])
        self.assertIsNone(result["selectedThreshold"])
        self.assertFalse(result["recommendedCautionThreshold"]["available"])
        self.assertEqual([row["threshold"] for row in result["thresholdTests"]], [75])
        self.assertIn("不发布推荐阈值", result["summary"])

    def test_purge_uses_exact_label_end_dates_instead_of_row_count(self) -> None:
        split_date = date(2025, 1, 1) + timedelta(days=42)
        rows = []
        for index in range(60):
            label_end = date(2025, 1, 1) + timedelta(days=index)
            if index in {40, 41}:
                label_end = split_date + timedelta(days=1)
            rows.append(observation(index, score=60.0, event=index % 5 == 0, label_end=label_end))

        result = equity_walk_forward_backtest(rows, -2.0, horizon=15)

        self.assertTrue(result["available"])
        self.assertEqual(result["splitDate"], split_date.isoformat())
        self.assertEqual(result["purgedTrainingRows"], 2)
        self.assertIn("labelEndDate15d", result["purgeRule"])
        self.assertEqual(result["inSample"]["sampleSize"], 40)

    def test_component_audit_is_read_only_and_does_not_reweight_production(self) -> None:
        rows = []
        for index in range(30):
            row = observation(
                index,
                score=80.0 if index % 4 == 0 else 30.0,
                event=index % 4 == 0,
                label_end=date(2025, 1, 1) + timedelta(days=index + 15),
            )
            row["componentScores"] = {
                "marketFlow": {
                    "label": "市场流",
                    "score": row["score"],
                    "weight": 0.22,
                    "sourceQuality": "high",
                    "historicalReplay": True,
                }
            }
            rows.append(row)

        diagnostics = equity_backtest_component_diagnostics(
            rows,
            -2.0,
            horizon=15,
            sample_role="walkForwardOos",
            production_use=False,
        )
        calibration = equity_weight_calibration_summary(
            [
                {
                    "key": "marketFlow",
                    "label": "市场流",
                    "weight": 0.22,
                    "scoreUse": "scored",
                    "sourceQuality": "high",
                    "historicalReplay": True,
                }
            ],
            diagnostics,
        )

        self.assertEqual(diagnostics[0]["sampleRole"], "walkForwardOos")
        self.assertFalse(diagnostics[0]["productionUse"])
        self.assertFalse(calibration["productionWeightsChanged"])
        self.assertFalse(calibration["productionUse"])
        self.assertEqual(calibration["rows"][0]["configuredWeight"], 0.22)
        self.assertEqual(calibration["rows"][0]["diagnosticSampleRole"], "walkForwardOos")


class OverlapAdjustedInferenceTests(unittest.TestCase):
    def test_block_length_rounds_up_fractional_forward_overlap(self) -> None:
        start = date(2020, 1, 6)
        prices = business_day_prices(start=start, calendar_days=900)
        signals = [
            SeriesPoint(start + timedelta(days=7 * index), float(index % 17))
            for index in range(100)
        ]

        result = evaluate_signal(
            signals,
            prices,
            horizons=(30,),
            bootstrap_horizon_days=30,
            direction="higher_better",
        )
        horizon = result["horizons"][0]

        # 30 calendar days / 7-day weekly spacing is 4.29, so four samples
        # still overlap.  The dependency block must conservatively round to 5.
        self.assertEqual(horizon["overlapBlockLength"], 5)
        self.assertEqual(
            horizon["oosEffectiveSampleSize"],
            horizon["oosSampleSize"] // 5,
        )
        self.assertEqual(
            horizon["overlapAudit"]["blockLengthRule"],
            "ceil(horizon days / median valid-pair spacing days)",
        )

    def test_underpowered_overlapping_oos_sample_fails_closed(self) -> None:
        start = date(2023, 1, 2)
        prices: list[SeriesPoint] = []
        for index in range(520):
            point_date = start + timedelta(days=index)
            if point_date.weekday() < 5:
                value = 100.0 * math.exp(0.0002 * index + 0.01 * math.sin(index / 13))
                prices.append(SeriesPoint(point_date, value))
        signals = [
            SeriesPoint(start + timedelta(days=7 * index), float(index % 11))
            for index in range(60)
        ]

        result = evaluate_signal(
            signals,
            prices,
            horizons=(91,),
            bootstrap_horizon_days=91,
        )
        horizon = result["horizons"][0]

        self.assertGreater(horizon["icOos"], 0.5)
        self.assertEqual(horizon["oosEffectiveSampleSize"], 1)
        self.assertFalse(horizon["inferenceValidOos"])
        self.assertFalse(horizon["robustOos"])
        self.assertFalse(horizon["ciOosAudit"]["available"])
        self.assertFalse(horizon["pValueOosAudit"]["available"])
        self.assertNotIn("pValueOos", horizon)

    def test_bootstrap_and_randomization_audits_are_deterministic(self) -> None:
        start = date(2018, 1, 1)
        prices = business_day_prices(start=start, calendar_days=2300)
        rng = random.Random(21)
        signals = [
            SeriesPoint(start + timedelta(days=7 * index), rng.uniform(0, 100))
            for index in range(300)
        ]

        first = evaluate_signal(
            signals,
            prices,
            horizons=(91,),
            bootstrap_horizon_days=91,
            direction="higher_better",
        )["horizons"][0]
        second = evaluate_signal(
            signals,
            prices,
            horizons=(91,),
            bootstrap_horizon_days=91,
            direction="higher_better",
        )["horizons"][0]

        self.assertEqual(first["ciOos"], second["ciOos"])
        self.assertEqual(first["pValueOos"], second["pValueOos"])
        self.assertEqual(
            first["ciOosAudit"]["method"],
            "circular moving-block bootstrap percentile",
        )
        self.assertTrue(first["ciOosAudit"]["deterministic"])
        self.assertTrue(first["pValueOosAudit"]["deterministic"])
        self.assertEqual(first["ciOosAudit"]["blockLength"], 13)
        self.assertEqual(first["pValueOosAudit"]["blockLength"], 13)


class CircularShiftRandomizationTests(unittest.TestCase):
    def test_detects_aligned_serial_signal_without_destroying_order(self) -> None:
        rng = random.Random(44)
        level = 0.0
        signal: list[float] = []
        for _ in range(120):
            level = 0.6 * level + rng.gauss(0, 1)
            signal.append(level)
        pairs = [(value, value + 0.15 * rng.gauss(0, 1)) for value in signal]

        first = order_preserving_circular_shift_test(pairs, block_len=7)
        second = order_preserving_circular_shift_test(pairs, block_len=7)

        self.assertEqual(first, second)
        self.assertTrue(first["available"])
        self.assertLess(first["pValue"], 0.05)
        self.assertEqual(first["tail"], "two-sided")
        self.assertGreaterEqual(first["shiftsTested"], 9)
        self.assertEqual(
            first["preserves"],
            "within-series cyclic rank order and serial dependence",
        )

    def test_short_shift_space_is_explicitly_unavailable(self) -> None:
        pairs = [(float(index), float(index * 2)) for index in range(20)]

        result = order_preserving_circular_shift_test(pairs, block_len=8)

        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "too few horizon-separated circular shifts")


class MultipleTestingInferenceGateTests(unittest.TestCase):
    def test_actionable_requires_valid_overlap_adjusted_inference(self) -> None:
        rows = [
            {
                "pValue3m": 0.001,
                "robust": True,
                "wrongWay": False,
                "inferenceValid3m": False,
                "foldStability3m": {"stablePositive": True},
            },
            {
                "pValue3m": 0.002,
                "robust": True,
                "wrongWay": False,
                "inferenceValid3m": True,
                "foldStability3m": {"stablePositive": True},
            },
        ]

        apply_benjamini_hochberg(rows, alpha=0.10)

        self.assertTrue(rows[0]["fdrSignificant3m"])
        self.assertFalse(rows[0]["actionableRobust"])
        self.assertTrue(rows[1]["actionableRobust"])
        self.assertEqual(rows[0]["fdrMethod"], "Benjamini-Hochberg")
        self.assertTrue(rows[0]["fdrInputAvailable"])

    def test_metric_row_uses_randomization_p_value_with_full_audit(self) -> None:
        start = date(2018, 1, 1)
        prices = business_day_prices(start=start, calendar_days=2300)
        rng = random.Random(9)
        signals = [
            SeriesPoint(start + timedelta(days=7 * index), rng.uniform(0, 100))
            for index in range(300)
        ]

        row = signal_validation_metric_row(
            row_id="audit-test",
            label="Audit test",
            label_cn="审计测试",
            module="test",
            signal_points=signals,
            price_points=prices,
            prices_sorted=SortedSeries(prices),
            direction="higher_better",
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(
            row["pValue3mMethod"],
            "order-preserving circular-shift randomization (two-sided)",
        )
        self.assertTrue(row["pValue3mAudit"]["available"])
        self.assertTrue(row["bootstrapAudit3m"]["available"])
        self.assertTrue(row["inferenceValid3m"])
        self.assertEqual(
            row["oosEffectiveSampleSize3m"],
            row["oosSampleSize3m"] // row["overlapAudit3m"]["blockLength"],
        )


if __name__ == "__main__":
    unittest.main()
