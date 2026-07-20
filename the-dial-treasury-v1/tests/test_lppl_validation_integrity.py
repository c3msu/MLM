from __future__ import annotations

import math
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from treasury_data import build_dashboard, scoring_lppl, scoring_lppl_history, scoring_lppl_validation
from treasury_data.sources import MarketDailyBar


def weekday_dates(start: date, count: int) -> list[date]:
    dates: list[date] = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def bars_for(symbol: str, count: int = 180) -> list[MarketDailyBar]:
    return [
        MarketDailyBar(
            symbol=symbol,
            date=point_date,
            open=100.0 + index * 0.1,
            high=101.0 + index * 0.1,
            low=99.0 + index * 0.1,
            close=100.0 + index * 0.1,
            volume=1_000_000,
            source="unit-test",
        )
        for index, point_date in enumerate(weekday_dates(date(2025, 1, 2), count))
    ]


def validation_rows(
    count: int = 100,
    *,
    model_spec_id: str | None = None,
    comparable: bool | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    dates = weekday_dates(date(2025, 1, 2), count)
    for index, point_date in enumerate(dates):
        row: dict[str, object] = {
            "date": point_date.isoformat(),
            "score": 80.0 if index % 20 == 0 else 30.0,
            "_barIndex": index,
            "maxDrawdown15d": -3.0 if index % 20 == 0 else -0.5,
            "drawdownEvent15d": index % 20 == 0,
            "forward15d": -2.0 if index % 20 == 0 else 0.5,
            "drawdownLeadDays15d": 3 if index % 20 == 0 else None,
        }
        if model_spec_id is not None:
            row["modelSpecId"] = model_spec_id
        if comparable is not None:
            row["validationComparableToProduction"] = comparable
        rows.append(row)
    return rows


class LpplModelSelectionIntegrityTests(unittest.TestCase):
    def test_fast_replay_has_a_distinct_non_comparable_model_fingerprint(self) -> None:
        source_bars = bars_for("SPY", 300)

        def fake_fit(sample: list[MarketDailyBar], *, fast: bool = False) -> dict[str, object]:
            window = len(sample)
            return {
                "available": True,
                "score": 70.0,
                "confidence": 0.8,
                "fitR2": 0.95,
                "fitSse": 1.0,
                "daysToCritical": 55 + (window % 3),
                "windowDays": window,
                "passesLpplCoreDiagnostics": True,
                "passesLpplDiagnostics": True,
            }

        with patch.object(scoring_lppl, "fit_lppl_window", side_effect=fake_fit):
            live = scoring_lppl.fit_global_lppl_signal(source_bars)
            replay = scoring_lppl.fit_global_lppl_signal(source_bars, fast=True)

        self.assertEqual(live["modelSpecId"], scoring_lppl.GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID)
        self.assertTrue(live["validationComparableToProduction"])
        self.assertTrue(live["modelSelectionAudit"]["productionEligible"])
        self.assertEqual(replay["modelSpecId"], scoring_lppl.GLOBAL_LPPL_FAST_REPLAY_MODEL_SPEC_ID)
        self.assertFalse(replay["validationComparableToProduction"])
        self.assertFalse(replay["modelSelectionAudit"]["productionEligible"])

    def test_history_as_of_boundary_trims_future_bars_before_replay(self) -> None:
        source_bars = bars_for("SPY", 160)
        cutoff = source_bars[129].date
        captured_lengths: list[int] = []

        def history_builder(_symbol: str, clean: list[MarketDailyBar]) -> list[dict[str, object]]:
            captured_lengths.append(len(clean))
            return [
                {"date": clean[-2].date.isoformat(), "score": 45.0},
                {"date": clean[-1].date.isoformat(), "score": 46.0},
            ]

        history = scoring_lppl_history.build_global_lppl_single_index_history(
            {"symbol": "SPY", "name": "S&P 500", "asOf": cutoff.isoformat()},
            source_bars,
            history_points_builder=history_builder,
        )

        self.assertEqual(captured_lengths, [130])
        self.assertEqual(history["dateRange"]["end"], cutoff.isoformat())

    def test_history_as_of_boundary_rejects_future_custom_replay_points(self) -> None:
        source_bars = bars_for("SPY", 160)
        cutoff = source_bars[129].date
        future_date = source_bars[140].date

        history = scoring_lppl_history.build_global_lppl_single_index_history(
            {"symbol": "SPY", "name": "S&P 500", "asOf": cutoff.isoformat()},
            source_bars,
            history_points_builder=lambda _symbol, clean: [
                {"date": clean[-2].date.isoformat(), "score": 45.0},
                {"date": clean[-1].date.isoformat(), "score": 46.0},
                {"date": future_date.isoformat(), "score": 99.0},
            ],
        )

        self.assertEqual(len(history["points"]), 2)
        self.assertEqual(history["dateRange"]["end"], cutoff.isoformat())
        self.assertNotIn(99.0, [point["score"] for point in history["points"]])


class LpplOosIntegrityTests(unittest.TestCase):
    def test_exact_binomial_tail_and_bonferroni_adjustment_are_auditable(self) -> None:
        probability = 0.20
        expected = sum(
            math.comb(5, hits) * probability**hits * (1.0 - probability) ** (5 - hits)
            for hits in range(4, 6)
        )
        actual = scoring_lppl_validation._exact_binomial_upper_tail(
            4,
            5,
            null_probability=probability,
        )

        self.assertAlmostEqual(actual or 0.0, expected, places=12)

    def test_contiguous_daily_alerts_are_not_counted_as_independent_trials(self) -> None:
        rows = validation_rows(90)
        for index, row in enumerate(rows):
            row["score"] = 80.0 if 10 <= index <= 30 or 55 <= index <= 65 else 30.0
            row["drawdownEvent15d"] = index in {10, 55}

        result = scoring_lppl_validation.global_lppl_threshold_test(65, rows, -2.0, horizon=15)

        self.assertEqual(result["alertDays"], 32)
        self.assertEqual(result["independentAlertCount"], 2)
        self.assertIn("first alert per contiguous episode", result["independenceRule"])
        self.assertIn("exact binomial", result["enrichmentTest"])
        if result["enrichmentPValueOneSided"] is not None:
            self.assertAlmostEqual(
                result["multipleTestingAdjustedPValue"],
                min(1.0, result["enrichmentPValueOneSided"] * 6),
                places=7,
            )

    def test_fast_replay_oos_metrics_are_audit_only_in_strict_build_path(self) -> None:
        rows = validation_rows(
            120,
            model_spec_id=scoring_lppl.GLOBAL_LPPL_FAST_REPLAY_MODEL_SPEC_ID,
            comparable=False,
        )

        result = scoring_lppl_validation.global_lppl_oos_validation_fields(
            rows,
            -2.0,
            require_model_comparability=True,
            live_model_spec_id=scoring_lppl.GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
            live_validation_comparable=True,
        )

        self.assertTrue(result["oosAvailable"])
        self.assertFalse(result["productionEvidenceAvailable"])
        self.assertFalse(result["productionActionable"])
        self.assertEqual(result["productionEffectiveWeightMultiplier"], 0.0)
        self.assertEqual(result["productionThreshold"], scoring_lppl_validation.GLOBAL_LPPL_ALERT_THRESHOLD)
        self.assertEqual(result["replayModelAudit"]["status"], "model_spec_mismatch")

    def test_exact_production_replay_can_enter_oos_gate_without_cross_market_evidence(self) -> None:
        rows = validation_rows(
            120,
            model_spec_id=scoring_lppl.GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
            comparable=True,
        )

        result = scoring_lppl_validation.global_lppl_oos_validation_fields(
            rows,
            -2.0,
            require_model_comparability=True,
            live_model_spec_id=scoring_lppl.GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
            live_validation_comparable=True,
        )

        self.assertTrue(result["productionEvidenceAvailable"])
        self.assertEqual(result["replayModelAudit"]["status"], "comparable")
        self.assertEqual(result["productionWeightSource"], "untouched_oos_last_35pct")
        self.assertIn("exact_binomial_bonferroni6", result["productionWeightMethod"])

    def test_strict_model_gate_requires_live_fingerprint_not_only_replay_id(self) -> None:
        rows = validation_rows(
            120,
            model_spec_id=scoring_lppl.GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
            comparable=True,
        )

        result = scoring_lppl_validation.global_lppl_oos_validation_fields(
            rows,
            -2.0,
            require_model_comparability=True,
        )

        self.assertFalse(result["productionEvidenceAvailable"])
        self.assertFalse(result["productionActionable"])
        self.assertEqual(result["replayModelAudit"]["status"], "live_model_unknown")

    def test_mixed_oos_weight_is_evidence_but_not_actionable(self) -> None:
        rows = validation_rows(
            120,
            model_spec_id=scoring_lppl.GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
            comparable=True,
        )
        with patch.object(
            scoring_lppl_validation,
            "global_lppl_validation_weight",
            return_value=(0.85, "mixed", "部分支持"),
        ):
            result = scoring_lppl_validation.global_lppl_oos_validation_fields(
                rows,
                -2.0,
                require_model_comparability=True,
                live_model_spec_id=scoring_lppl.GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
                live_validation_comparable=True,
            )

        self.assertTrue(result["productionEvidenceAvailable"])
        self.assertFalse(result["productionActionable"])
        self.assertEqual(result["productionValidationRole"], "mixed")

    def test_weight_requires_independent_confidence_and_six_market_correction(self) -> None:
        rejected = {
            "independentAlertCount": 6,
            "independentSampleSize": 12,
            "independentPrecision": 83.3,
            "independentBaseRate": 25.0,
            "precisionLowerBound90Pct": 50.0,
            "multipleTestingPass": False,
        }
        accepted = {
            **rejected,
            "independentPrecision": 100.0,
            "precisionLowerBound90Pct": 68.9,
            "multipleTestingPass": True,
        }

        self.assertEqual(scoring_lppl_validation.global_lppl_validation_weight(rejected)[0], 0.0)
        self.assertEqual(scoring_lppl_validation.global_lppl_validation_weight(accepted)[0], 1.0)

    def test_validation_outcomes_stop_at_latest_replay_point(self) -> None:
        source_bars = bars_for("SPY", 70)
        points = [
            {"date": bar.date.isoformat(), "score": 70.0}
            for bar in source_bars[:41]
        ]
        baseline = scoring_lppl_validation.build_global_lppl_validation_observations(
            points,
            source_bars,
            -2.0,
        )
        changed = list(source_bars)
        for index in range(41, len(changed)):
            original = changed[index]
            changed[index] = MarketDailyBar(
                symbol=original.symbol,
                date=original.date,
                open=50.0,
                high=51.0,
                low=49.0,
                close=50.0,
                volume=original.volume,
                source=original.source,
            )
        shifted = scoring_lppl_validation.build_global_lppl_validation_observations(
            points,
            changed,
            -2.0,
        )

        self.assertEqual(baseline, shifted)
        self.assertEqual(baseline[-1]["_informationCutoff"], source_bars[40].date.isoformat())
        self.assertIsNone(baseline[-1]["maxDrawdown15d"])

    def test_index_validation_strict_path_does_not_borrow_live_credit_for_fast_replay(self) -> None:
        source_bars = bars_for("SPY", 180)
        points = [
            {
                "date": bar.date.isoformat(),
                "score": 80.0 if index % 20 == 0 else 30.0,
                "modelSpecId": scoring_lppl.GLOBAL_LPPL_FAST_REPLAY_MODEL_SPEC_ID,
                "validationComparableToProduction": False,
            }
            for index, bar in enumerate(source_bars)
        ]
        validation = build_dashboard.build_global_lppl_index_validation(
            [{"available": True, "symbol": "SPY", "sourceSymbol": "SPY"}],
            {"SPY": source_bars},
            histories={"SPY": {"available": True, "points": points}},
        )

        self.assertTrue(validation["available"])
        row = validation["rows"][0]
        self.assertEqual(row["validationMarket"], "SPY")
        self.assertEqual(row["evidenceIsolation"], "own_market_only")
        self.assertFalse(row["productionEvidenceAvailable"])
        self.assertEqual(row["effectiveWeightMultiplier"], 0.0)

    def test_raw_risk_status_does_not_bypass_fit_and_validation_action_gate(self) -> None:
        rows = build_dashboard.apply_global_lppl_index_validation(
            [
                {
                    "available": True,
                    "symbol": "SPY",
                    "score": 85.0,
                    "status": "risk",
                    "fitProductionEligible": True,
                    "productionEligible": True,
                }
            ],
            {
                "rows": [
                    {
                        "symbol": "SPY",
                        "productionEvidenceAvailable": True,
                        "productionActionable": False,
                        "productionThreshold": 65,
                        "effectiveWeightMultiplier": 0.85,
                    }
                ]
            },
        )

        row = rows[0]
        self.assertEqual(row["status"], "risk")
        self.assertFalse(row["productionEligible"])
        self.assertFalse(row["actionable"])
        self.assertEqual(row["scoreUse"], "research_only")

        signal = build_dashboard.build_global_lppl_forward_signal(
            {
                **row,
                "confidence": 0.8,
                "daysToCritical": 60,
                "history": {"available": True, "points": []},
            }
        )
        self.assertEqual(signal["rawStatus"], "risk")
        self.assertFalse(signal["productionEligible"])
        self.assertFalse(signal["actionable"])
        self.assertEqual(signal["scoreUse"], "research_only")


if __name__ == "__main__":
    unittest.main()
