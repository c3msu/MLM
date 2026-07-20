from __future__ import annotations

import copy
import unittest
from datetime import date, timedelta

from treasury_data.scoring_equity import (
    EQUITY_RISK_REPLAY_SCORED_COMPONENTS,
    EQUITY_RISK_SCORE_SCALE_ID,
    EQUITY_RISK_V2_CANONICAL_NORMALIZED_WEIGHTS,
    EQUITY_RISK_COMPONENT_WEIGHTS,
    bind_equity_production_action,
    equity_backtest_alert_cluster_test,
    equity_backtest_score_scale_contract,
    equity_walk_forward_backtest,
)


def score_scale() -> dict[str, object]:
    components = sorted(EQUITY_RISK_REPLAY_SCORED_COMPONENTS)
    weights = dict(EQUITY_RISK_V2_CANONICAL_NORMALIZED_WEIGHTS)
    return {
        "id": EQUITY_RISK_SCORE_SCALE_ID,
        "requiredScoredComponents": components,
        "scoredComponents": components,
        "canonicalNormalizedWeights": dict(weights),
        "observedNormalizedWeights": dict(weights),
        "weightsMatchCanonical": True,
        "weightMismatchedObservationCount": 0,
        "thresholdComparable": True,
    }


def production_row(*, validated: bool = True) -> dict[str, object]:
    return {
        "threshold": 75,
        "productionUse": True,
        "sampleRole": "walkForwardOos",
        "sampleSize": 100,
        "independentAlertClusters": 10,
        "independentHitClusters": 10,
        "clusterPrecision": 100.0,
        "baseRate": 50.0,
        "oosValidated": validated,
        "validationStatus": "validated" if validated else "research-only",
        "validationReason": "validated" if validated else "not validated",
    }


def backtest_contract(row: dict[str, object]) -> dict[str, object]:
    scale = score_scale()
    return {
        "scoreScale": {
            "id": scale["id"],
            "requiredScoredComponents": scale["requiredScoredComponents"],
            "canonicalNormalizedWeights": scale["canonicalNormalizedWeights"],
            "observedNormalizedWeights": scale["observedNormalizedWeights"],
            "weightsMatchCanonical": True,
            "weightMismatchedObservationCount": 0,
            "thresholdComparable": True,
        },
        "walkForward": {"thresholdTests": [row]},
    }


def observation(
    index: int,
    *,
    score: float,
    event: bool,
    label_days: int = 15,
) -> dict[str, object]:
    target = date(2025, 1, 1) + timedelta(days=index)
    return {
        "date": target.isoformat(),
        "score": score,
        "maxDrawdown15d": -3.0 if event else -1.0,
        "drawdownEvent15d": event,
        "forward15d": -1.0 if event else 1.0,
        "drawdownLeadDays15d": 3 if event else None,
        "labelEndDate15d": (target + timedelta(days=label_days)).isoformat(),
    }


class EquityBacktestIntegrityTests(unittest.TestCase):
    def test_selected_threshold_must_pass_oos_precision_gate(self) -> None:
        rows = []
        for index in range(100):
            if index < 70:
                active = index % 4 == 0
                event = active or index % 13 == 0
            else:
                active = index % 5 == 0
                event = (not active) and index % 7 == 0
            rows.append(
                observation(
                    index,
                    score=60.0 if active else 30.0,
                    event=event,
                    label_days=0,
                )
            )

        result = equity_walk_forward_backtest(rows, -2.0, horizon=15)

        self.assertTrue(result["available"])
        self.assertEqual(result["validationDesign"], "singlePurgedChronologicalHoldout")
        self.assertEqual(result["walkForwardFoldCount"], 1)
        self.assertEqual(result["embargoSessions"], 0)
        self.assertIn("exact training-label purge", result["embargoRule"])
        self.assertEqual(result["selectedThreshold"], 60)
        recommendation = result["recommendedCautionThreshold"]
        self.assertFalse(recommendation["available"])
        self.assertIn("failed OOS precision", recommendation["reason"])
        self.assertFalse(recommendation["productionUse"])

    def test_alert_clusters_dedupe_non_contiguous_overlapping_label_windows(self) -> None:
        rows = [
            observation(0, score=80.0, event=False, label_days=15),
            observation(2, score=20.0, event=False, label_days=15),
            observation(5, score=82.0, event=True, label_days=15),
            observation(20, score=85.0, event=True, label_days=15),
        ]

        result = equity_backtest_alert_cluster_test(75, rows, -2.0, horizon=15)

        self.assertEqual(result["clusterCount"], 2)
        self.assertEqual(result["hitClusters"], 1)
        self.assertEqual(result["falseClusters"], 1)
        self.assertEqual(result["precision"], 50.0)
        self.assertEqual(result["clusters"][0]["alertDays"], 2)
        self.assertFalse(result["clusters"][0]["hit"])
        self.assertIn("labelEndDate15d", result["dedupeRule"])

    def test_production_oos_gate_uses_independent_alert_episodes(self) -> None:
        rows = []
        for index in range(100):
            active = 70 <= index < 80
            rows.append(
                observation(
                    index,
                    score=80.0 if active else 30.0,
                    event=active,
                    label_days=15,
                )
            )

        result = equity_walk_forward_backtest(rows, -2.0, horizon=15)
        production = next(row for row in result["thresholdTests"] if row["productionUse"])

        self.assertGreaterEqual(production["alertDays"], 5)
        self.assertEqual(production["independentAlertClusters"], 1)
        self.assertFalse(production["oosValidated"])
        self.assertEqual(production["validationStatus"], "research-only")
        self.assertIn("independent alert episodes", production["validationReason"])

    def test_point_precision_cannot_validate_without_episode_confidence(self) -> None:
        rows = []
        for index in range(100):
            event = index >= 70 and index % 2 == 0
            active = index in {70, 80, 91}
            rows.append(observation(index, score=80.0 if active else 30.0, event=event, label_days=0))

        result = equity_walk_forward_backtest(rows, -2.0, horizon=15)
        production = next(row for row in result["thresholdTests"] if row["productionUse"])

        self.assertEqual(production["independentAlertClusters"], 3)
        self.assertEqual(production["independentHitClusters"], 2)
        self.assertEqual(production["clusterPrecision"], 66.7)
        self.assertEqual(production["clusterPrecisionWilsonLower95"], 20.8)
        self.assertEqual(production["baseRate"], 50.0)
        self.assertFalse(production["oosValidated"])
        self.assertIn("Wilson lower bound", production["validationReason"])

    def test_replay_weight_drift_breaks_scale_contract(self) -> None:
        component_scores = {
            key: {"weight": EQUITY_RISK_COMPONENT_WEIGHTS[key], "score": 50.0}
            for key in EQUITY_RISK_REPLAY_SCORED_COMPONENTS
        }
        valid = equity_backtest_score_scale_contract([{"componentScores": component_scores}])
        self.assertTrue(valid["weightsMatchCanonical"])
        self.assertTrue(valid["thresholdComparable"])

        drifted_scores = copy.deepcopy(component_scores)
        drifted_scores["sectorRotation"]["weight"] = 0.12
        drifted = equity_backtest_score_scale_contract([{"componentScores": drifted_scores}])
        self.assertFalse(drifted["weightsMatchCanonical"])
        self.assertFalse(drifted["thresholdComparable"])
        self.assertEqual(drifted["weightMismatchedObservationCount"], 1)
        self.assertGreater(drifted["weightMismatchCounts"]["sectorRotation"], 0)

    def test_current_allocation_requires_validated_and_triggered_production_rule(self) -> None:
        signal = {
            "available": True,
            "asOf": "2026-07-16",
            "score": 80.0,
            "actionable": True,
            "scoreScale": {**score_scale(), "coreComplete": True},
            "regime": "Strong Alert",
            "regimeCn": "强告警",
            "allocation": {
                "horizon": "1-10d",
                "horizonCn": "1-10个交易日",
                "regime": "Strong Alert",
                "regimeCn": "强告警",
                "stance": "短线降风险",
                "equityExposure": "降低高Beta仓位",
                "exposureBandPct": [50, 80],
                "hedgeAction": "减仓或对冲",
                "actionable": True,
            },
        }

        research_only = bind_equity_production_action(
            signal,
            backtest_contract(production_row(validated=False)),
        )
        self.assertFalse(research_only["actionable"])
        self.assertIsNone(research_only["allocation"]["exposureBandPct"])
        self.assertEqual(research_only["contextAllocation"]["exposureBandPct"], [50, 80])

        validated = bind_equity_production_action(
            signal,
            backtest_contract(production_row(validated=True)),
        )
        self.assertTrue(validated["actionable"])
        self.assertEqual(validated["allocation"]["exposureBandPct"], [50, 80])

        below_threshold = bind_equity_production_action(
            {**signal, "score": 70.0},
            backtest_contract(production_row(validated=True)),
        )
        self.assertFalse(below_threshold["actionable"])
        self.assertFalse(below_threshold["productionValidation"]["currentTriggered"])
        self.assertIsNone(below_threshold["allocation"]["exposureBandPct"])

        mismatched_scale = backtest_contract(production_row(validated=True))
        mismatched_scale["scoreScale"]["id"] = "different-scale"
        mismatched = bind_equity_production_action(signal, mismatched_scale)
        self.assertFalse(mismatched["actionable"])
        self.assertFalse(mismatched["productionValidation"]["scoreScaleMatchesBacktest"])
        self.assertFalse(mismatched["productionValidation"]["scoreContractAllowsAction"])

        weight_drift = backtest_contract(production_row(validated=True))
        drifted_weights = dict(weight_drift["scoreScale"]["observedNormalizedWeights"])
        drifted_weights["sectorRotation"] += 0.01
        weight_drift["scoreScale"]["observedNormalizedWeights"] = drifted_weights
        drifted = bind_equity_production_action(signal, weight_drift)
        self.assertFalse(drifted["actionable"])
        self.assertFalse(drifted["productionValidation"]["scoreWeightsMatchBacktest"])
        self.assertFalse(drifted["productionValidation"]["scoreScaleMatchesBacktest"])

    def test_missing_score_contract_declarations_fail_closed(self) -> None:
        signal = {
            "available": True,
            "asOf": "2026-07-16",
            "score": 80.0,
            "actionable": True,
            "scoreScale": {**score_scale(), "coreComplete": True},
            "regime": "Strong Alert",
            "regimeCn": "强告警",
            "allocation": {
                "horizon": "1-10d",
                "horizonCn": "1-10个交易日",
                "regime": "Strong Alert",
                "regimeCn": "强告警",
                "stance": "短线降风险",
                "equityExposure": "降低高Beta仓位",
                "exposureBandPct": [50, 80],
                "hedgeAction": "减仓或对冲",
                "actionable": True,
            },
        }
        backtest = backtest_contract(production_row(validated=True))
        cases = {
            "surface actionable": ("actionable", None),
            "allocation actionable": ("allocation", "actionable"),
            "core completeness": ("scoreScale", "coreComplete"),
            "threshold comparability": ("scoreScale", "thresholdComparable"),
        }

        for label, (parent, child) in cases.items():
            with self.subTest(label=label):
                incomplete = copy.deepcopy(signal)
                if child is None:
                    incomplete.pop(parent)
                else:
                    incomplete[parent].pop(child)
                result = bind_equity_production_action(incomplete, backtest)
                self.assertFalse(result["actionable"])
                self.assertFalse(result["productionValidation"]["scoreContractAllowsAction"])
                self.assertIsNone(result["allocation"]["exposureBandPct"])
                self.assertEqual(result["contextAllocation"]["exposureBandPct"], [50, 80])


if __name__ == "__main__":
    unittest.main()
