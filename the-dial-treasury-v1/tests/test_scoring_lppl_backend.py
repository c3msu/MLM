from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import patch

from treasury_data import build_dashboard, scoring_lppl_history, scoring_lppl_validation
from treasury_data.sources import MarketDailyBar


def weekday_dates_ending(end: date, count: int) -> list[date]:
    dates: list[date] = []
    current = end
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current -= timedelta(days=1)
    return list(reversed(dates))


def market_bars(dates: list[date], *, changed_index: int | None = None) -> list[MarketDailyBar]:
    rows: list[MarketDailyBar] = []
    for index, point_date in enumerate(dates):
        close = 50.0 if index == changed_index else 100.0
        rows.append(
            MarketDailyBar(
                symbol="SPY",
                date=point_date,
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=1_000_000,
                source="unit-test",
            )
        )
    return rows


class LpplCriticalDateTests(unittest.TestCase):
    def test_tc_offset_is_disclosed_as_sessions_and_converted_to_weekdays(self) -> None:
        dates = weekday_dates_ending(date(2026, 7, 10), 120)  # Friday
        bars = market_bars(dates)
        fit = {
            "available": True,
            "score": 70.0,
            "confidence": 0.8,
            "daysToCritical": 2,
            "daysToCriticalRange": {"min": 2, "max": 5, "values": [2, 5]},
            "fitR2": 0.95,
            "windowDays": 120,
        }

        with patch.object(scoring_lppl_history, "fit_global_lppl_signal", return_value=fit):
            row = scoring_lppl_history.global_lppl_index_row(
                {"symbol": "SPY", "name": "S&P 500"},
                bars,
            )

        self.assertTrue(row["available"])
        self.assertEqual(row["sessionsToCritical"], 2)
        self.assertEqual(row["daysToCritical"], 2)  # compatibility alias
        self.assertEqual(row["criticalDate"], "2026-07-14")
        self.assertEqual(row["calendarDaysToCritical"], 4)
        self.assertEqual(row["sessionsToCriticalRange"], fit["daysToCriticalRange"])
        self.assertIn("exchange holidays are not modeled", row["criticalDateApproximation"])


class LpplPurgedOosTests(unittest.TestCase):
    def test_thin_oos_alert_sample_gets_no_production_weight(self) -> None:
        multiplier, role, role_cn = scoring_lppl_validation.global_lppl_validation_weight(
            {"alertDays": 2, "precision": 100.0, "baseRate": 10.0}
        )

        self.assertEqual(multiplier, 0.0)
        self.assertEqual(role, "insufficient")
        self.assertIn("样本不足", role_cn)

    def test_oos_start_price_cannot_change_the_purged_calibration_grid(self) -> None:
        dates = weekday_dates_ending(date(2026, 7, 10), 90)
        baseline_bars = market_bars(dates)
        # 75 complete 15D validation observations produce split index 48.
        # Altering bar 48
        # changes every overlapping 15-session label unless the final 15
        # calibration sessions are purged.
        shifted_bars = market_bars(dates, changed_index=48)
        points = [
            {"date": point_date.isoformat(), "score": 80.0 if index % 3 == 0 else 40.0}
            for index, point_date in enumerate(dates)
        ]

        baseline_obs = scoring_lppl_validation.build_global_lppl_validation_observations(
            points,
            baseline_bars,
            -2.0,
        )
        shifted_obs = scoring_lppl_validation.build_global_lppl_validation_observations(
            points,
            shifted_bars,
            -2.0,
        )
        captured_grids: list[list[dict[str, object]]] = []

        def capture_grid(grid: list[dict[str, object]], _sample_size: int) -> dict[str, int]:
            captured_grids.append(grid)
            return {"threshold": 65}

        with patch.object(scoring_lppl_validation, "global_lppl_recommended_threshold", side_effect=capture_grid):
            baseline = scoring_lppl_validation.global_lppl_oos_validation_fields(baseline_obs, -2.0)
            shifted = scoring_lppl_validation.global_lppl_oos_validation_fields(shifted_obs, -2.0)

        self.assertEqual(captured_grids[0], captured_grids[1])
        self.assertEqual(baseline["oosThreshold"], shifted["oosThreshold"])
        self.assertEqual(baseline["oosSplitPct"], 65)
        self.assertEqual(baseline["oosPurgeSessions"], 15)
        self.assertEqual(baseline["oosPurgeBasis"], "trading_session_bar_index")
        self.assertEqual(baseline["oosEligibleObservationCount"], 75)
        self.assertEqual(baseline["oosExcludedIncompleteTailCount"], 14)
        self.assertEqual(baseline["oosCalibrationCandidateSize"], 48)
        self.assertEqual(baseline["oosCalibrationSampleSize"], 33)
        self.assertEqual(baseline["oosPurgedCalibrationRows"], 15)
        self.assertEqual(baseline["oosSplitDate"], dates[48].isoformat())
        self.assertEqual(baseline["oosCalibrationThrough"], dates[32].isoformat())
        expected_multiplier, expected_role, _ = scoring_lppl_validation.global_lppl_validation_weight(
            baseline["oosTest15d"]
        )
        self.assertEqual(baseline["productionThreshold"], baseline["oosThreshold"])
        self.assertEqual(baseline["productionEffectiveWeightMultiplier"], expected_multiplier)
        self.assertEqual(baseline["productionValidationRole"], expected_role)
        self.assertEqual(baseline["productionWeightSource"], "untouched_oos_last_35pct")

    def test_live_validation_fields_use_oos_and_keep_full_sample_descriptive(self) -> None:
        dates = weekday_dates_ending(date(2026, 7, 10), 180)
        bars = market_bars(dates)
        points = [
            {"date": point_date.isoformat(), "score": 80.0 if index % 4 == 0 else 40.0}
            for index, point_date in enumerate(dates)
        ]

        validation = build_dashboard.build_global_lppl_single_index_validation(
            {"symbol": "SPY", "sourceSymbol": "SPY"},
            bars,
            history_points=points,
        )

        self.assertIsNotNone(validation)
        self.assertTrue(validation["productionEvidenceAvailable"])
        self.assertEqual(validation["threshold"], validation["oosThreshold"])
        self.assertEqual(
            validation["effectiveWeightMultiplier"],
            validation["oosEffectiveWeightMultiplier"],
        )
        self.assertEqual(validation["validationRole"], validation["oosValidationRole"])
        self.assertFalse(validation["descriptiveFullSample"]["productionUse"])
        self.assertIn("test15d", validation["descriptiveFullSample"])

    def test_forward_signal_ignores_full_sample_backtest_threshold_and_weight(self) -> None:
        row = {
            "symbol": "SPY",
            "available": True,
            "score": 70.0,
            "confidence": 0.8,
            "daysToCritical": 60,
            "backtest": {"threshold": 55},
            "effectiveWeightMultiplier": 1.0,
            "validation": {
                "productionEvidenceAvailable": True,
                "productionThreshold": 80,
                "productionThresholdSource": "purged_calibration_first_65pct",
                "productionEffectiveWeightMultiplier": 0.6,
                "effectiveWeightMultiplier": 1.0,
            },
            "history": {"available": True, "points": []},
        }

        signal = build_dashboard.build_global_lppl_forward_signal(row)

        self.assertEqual(signal["threshold"], 80)
        self.assertEqual(signal["thresholdDistance"], -10.0)
        self.assertEqual(signal["thresholdSource"], "purged_calibration_first_65pct")
        self.assertEqual(signal["validationMultiplier"], 0.6)

        no_oos = dict(row)
        no_oos["validation"] = {
            "productionEvidenceAvailable": False,
            "effectiveWeightMultiplier": 1.0,
        }
        no_oos_signal = build_dashboard.build_global_lppl_forward_signal(no_oos)
        self.assertEqual(no_oos_signal["threshold"], scoring_lppl_validation.GLOBAL_LPPL_ALERT_THRESHOLD)
        self.assertEqual(no_oos_signal["thresholdSource"], "fixed_prior_no_oos")
        self.assertEqual(no_oos_signal["validationMultiplier"], 0.0)


if __name__ == "__main__":
    unittest.main()
