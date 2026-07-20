from __future__ import annotations

import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import patch

from treasury_data.scoring_equity import (
    EQUITY_RISK_V2_CANONICAL_NORMALIZED_WEIGHTS,
    equity_component,
    equity_short_term_signal_at,
    unavailable_equity_component,
)
from treasury_data.sources import MarketDailyBar


class EquityScoreScaleContractTests(unittest.TestCase):
    def component(self, key: str, weight: float, score: float = 50.0) -> dict[str, object]:
        return equity_component(key, key, weight, score, key, drivers=[], metrics={})

    def signal(
        self,
        *,
        missing: str | None = None,
        event_score: float = 50.0,
        weight_override: tuple[str, float] | None = None,
    ) -> dict[str, object]:
        specs = {
            "equity_vol_target_pressure_component": ("volTargetPressure", 0.22),
            "equity_qqq_tlt_rotation_component": ("qqqTltRotation", 0.14),
            "equity_market_flow_component": ("marketFlow", 0.22),
            "equity_sector_rotation_component": ("sectorRotation", 0.06),
            "equity_hot_stock_reversal_component": ("hotStockReversal", 0.18),
            "equity_turnover_component": ("turnover", 0.14),
            "equity_event_risk_component": ("eventRisk", 0.01),
        }
        target = date(2026, 7, 16)
        bars = {
            "SPY": [
                MarketDailyBar("SPY", target, 100, 101, 99, 100, 1_000_000, "test"),
            ]
        }
        with ExitStack() as stack:
            for function_name, (key, weight) in specs.items():
                effective_weight = weight_override[1] if weight_override and key == weight_override[0] else weight
                value = (
                    unavailable_equity_component(key, key, effective_weight, "missing")
                    if key == missing
                    else self.component(key, effective_weight, event_score if key == "eventRisk" else 50.0)
                )
                stack.enter_context(patch(f"treasury_data.scoring_equity.{function_name}", return_value=value))
            stack.enter_context(
                patch(
                    "treasury_data.scoring_equity.equity_macro_overlay_component",
                    return_value=self.component("macroOverlay", 0.03, 100.0),
                )
            )
            stack.enter_context(
                patch(
                    "treasury_data.scoring_equity.equity_option_oi_component",
                    return_value=unavailable_equity_component("optionOI", "optionOI", 0.0, "missing"),
                )
            )
            stack.enter_context(
                patch(
                    "treasury_data.scoring_equity.equity_score_adjustments",
                    side_effect=lambda components, *, base_score: {
                        "baseScore": round(base_score, 1),
                        "amplifier": 0.0,
                        "dampener": 0.0,
                        "scoreFloor": 0.0,
                        "adjustedBeforeFloor": round(base_score, 1),
                        "floorApplied": False,
                        "finalScore": round(base_score, 1),
                        "rules": [],
                    },
                )
            )
            return equity_short_term_signal_at(
                bars,
                target,
                macro_liquidity_equity={"currentSignal": {"score3mChange": 20.0}},
                spy_early_warning={"score": 100.0},
                calendar_events=[],
                option_open_interest=None,
            )

    def test_current_macro_snapshot_is_context_only_and_does_not_change_score_scale(self) -> None:
        result = self.signal(event_score=100.0)
        components = {row["key"]: row for row in result["components"]}

        self.assertEqual(result["score"], 50.0)
        self.assertEqual(components["macroOverlay"]["score"], 100.0)
        self.assertEqual(components["macroOverlay"]["scoreUse"], "context")
        self.assertEqual(result["scoreScale"]["contextComponents"], ["eventRisk", "macroOverlay"])
        self.assertEqual(components["eventRisk"]["scoreUse"], "context")
        self.assertFalse(components["eventRisk"]["historicalReplay"])
        self.assertIsNone(components["eventRisk"]["metrics"].get("knownBeforeSignal"))
        self.assertFalse(components["eventRisk"]["metrics"].get("pointInTimeAvailabilityVerified"))
        self.assertEqual(
            result["scoreScale"]["observedNormalizedWeights"],
            EQUITY_RISK_V2_CANONICAL_NORMALIZED_WEIGHTS,
        )
        self.assertTrue(result["scoreScale"]["weightsMatchCanonical"])
        self.assertTrue(result["actionable"])

    def test_core_weight_drift_breaks_threshold_comparability(self) -> None:
        result = self.signal(weight_override=("sectorRotation", 0.12))

        self.assertTrue(result["scoreScale"]["coreComplete"])
        self.assertFalse(result["scoreScale"]["weightsMatchCanonical"])
        self.assertFalse(result["scoreScale"]["thresholdComparable"])
        self.assertTrue(
            any(row["component"] == "sectorRotation" for row in result["scoreScale"]["weightMismatches"])
        )
        self.assertFalse(result["actionable"])
        self.assertIsNone(result["allocation"]["exposureBandPct"])

    def test_missing_core_component_suppresses_action_but_keeps_diagnostics(self) -> None:
        result = self.signal(missing="qqqTltRotation")

        self.assertTrue(result["available"])
        self.assertFalse(result["actionable"])
        self.assertEqual(result["scoreScale"]["missingCoreComponents"], ["qqqTltRotation"])
        self.assertIsNone(result["allocation"]["exposureBandPct"])
        self.assertIsNotNone(result["contextAllocation"]["exposureBandPct"])

    def test_missing_context_event_does_not_renormalize_the_ohlcv_score_scale(self) -> None:
        result = self.signal(missing="eventRisk")

        self.assertTrue(result["scoreScale"]["coreComplete"])
        self.assertEqual(result["scoreScale"]["missingCoreComponents"], [])
        self.assertEqual(result["scoreScale"]["missingScoredComponents"], [])
        self.assertTrue(result["scoreScale"]["thresholdComparable"])
        self.assertTrue(result["actionable"])


if __name__ == "__main__":
    unittest.main()
