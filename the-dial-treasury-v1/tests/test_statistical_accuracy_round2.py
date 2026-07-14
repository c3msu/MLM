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


if __name__ == "__main__":
    unittest.main()
