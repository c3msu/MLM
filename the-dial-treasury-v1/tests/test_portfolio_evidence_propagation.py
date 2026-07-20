import math
import unittest
from datetime import date, timedelta

from treasury_data.build_dashboard import (
    GLOBAL_LPPL_REGIONAL_COMPOSITE_FAMILY_SIZE,
    GLOBAL_LPPL_REGIONAL_FACTOR_FAMILY_SIZE,
    apply_global_lppl_factor_family_correction,
    build_global_lppl_breadth_confirmation,
    build_global_lppl_forward_signal,
    global_lppl_summary,
)
from treasury_data.scoring_regional import (
    build_region_allocation,
    build_regional_rotation,
    regional_signal_qualifies_as_actionable,
)
from treasury_data.scoring_lppl import GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
from treasury_data.signal_validation import SortedSeries, apply_benjamini_hochberg
from treasury_data.sources import SeriesPoint
from treasury_data.validation_build import build_bhadial_predictive_lens


class GlobalLpplEvidencePropagationTests(unittest.TestCase):
    @staticmethod
    def _row(symbol: str, *, research_forward: bool) -> dict:
        actionable = not research_forward
        return {
            "available": True,
            "symbol": symbol,
            "score": 50.0 if research_forward else 72.0,
            "daysToCritical": 60,
            "weight": 1.0,
            "productionEligible": actionable,
            "actionable": actionable,
            "validation": {
                "productionEvidenceAvailable": actionable,
                "productionActionable": actionable,
            },
            "forwardSignal": {
                "available": True,
                # Deliberately make the research score visually higher.  It
                # must remain context while the lower production score counts
                # as the sole trigger.
                "score": 82.0 if research_forward else 42.0,
                "actionable": actionable,
                "scoreUse": "research_only" if research_forward else "production_signal",
            },
        }

    def test_research_forward_score_cannot_raise_production_breadth_or_summary(self) -> None:
        rows = [
            self._row("RESEARCH", research_forward=True),
            self._row("PRODUCTION", research_forward=False),
        ]

        breadth = build_global_lppl_breadth_confirmation(rows)
        summary = global_lppl_summary(rows, rows)

        self.assertEqual(breadth["forwardRiskCount"], 1)
        self.assertEqual(breadth["researchForwardRiskCount"], 1)
        self.assertEqual(breadth["validatedCount"], 1)
        self.assertIn("production forward triggers 1", breadth["summary"])
        self.assertIn("生产级前瞻触发1/2", summary)
        self.assertIn("1个研究层前瞻高压读数,不计入动作层", summary)

    def test_research_forward_signal_summary_is_explicitly_non_actionable(self) -> None:
        signal = build_global_lppl_forward_signal(
            {
                "available": True,
                "symbol": "TEST",
                "score": 90.0,
                "confidence": 0.9,
                "productionEligible": False,
                "validation": {
                    "productionEvidenceAvailable": False,
                    "productionActionable": False,
                },
            }
        )

        self.assertFalse(signal["actionable"])
        self.assertEqual(signal["scoreUse"], "research_only")
        self.assertIn("仅研究背景", signal["summary"])

    def test_regional_factor_fdr_uses_fixed_all_market_families(self) -> None:
        factor = {
            "pValue3m": 0.02,
            "robust": True,
            "wrongWay": False,
            "inferenceValid3m": True,
            "foldStability3m": {"stablePositive": True},
        }
        composite = {
            "available": True,
            "pValue3m": 0.02,
            "robust": True,
            "wrongWay": False,
            "inferenceValid3m": True,
            "foldStability3m": {"stablePositive": True},
        }
        rows = [
            {
                "symbol": "SPY",
                "factorValidation": {
                    "available": True,
                    "factors": [factor],
                    "composite": composite,
                },
            }
        ]

        apply_global_lppl_factor_family_correction(rows)

        self.assertEqual(factor["fdrFamilySize"], GLOBAL_LPPL_REGIONAL_FACTOR_FAMILY_SIZE)
        self.assertEqual(
            composite["fdrFamilySize"],
            GLOBAL_LPPL_REGIONAL_COMPOSITE_FAMILY_SIZE,
        )
        self.assertFalse(factor["fdrSignificant3m"])
        self.assertFalse(factor["actionableRobust"])
        self.assertFalse(composite["fdrSignificant3m"])
        audit = rows[0]["factorValidation"]["multipleTesting"]
        self.assertEqual(audit["families"][0]["size"], 23)
        self.assertEqual(audit["families"][1]["size"], 6)
        self.assertEqual(audit["families"][0]["implicitUnavailableHypotheses"], 22)


class RegionalAllocationEvidencePropagationTests(unittest.TestCase):
    @staticmethod
    def _region(*, production_triggered: bool, constructive: bool = False) -> dict:
        status = "risk" if production_triggered else "quiet"
        return {
            "key": "test",
            "name": "Test",
            "nameCn": "测试",
            "aggregate": {
                "availableCount": 1,
                "indexCount": 1,
                "status": status,
                "statusCn": "泡沫风险" if production_triggered else "低风险",
                "minDaysToCritical": 20 if production_triggered else None,
                "productionEligibleCount": 1 if production_triggered else 0,
                "actionableCount": 1 if production_triggered else 0,
                "actionableRiskCount": 1 if production_triggered else 0,
                "priceFactors": {
                    "available": True,
                    "marketState": "constructive" if constructive else "neutral",
                    "marketStateCn": "偏强" if constructive else "中性",
                    "relativeStrength3m": 8.0 if constructive else 0.0,
                },
            },
            "indices": [
                {
                    "symbol": "TEST",
                    "available": True,
                    "score": 90.0 if production_triggered else 30.0,
                    "status": status,
                    "fitProductionEligible": production_triggered,
                    "productionEligible": production_triggered,
                    "actionable": production_triggered,
                    "scoreUse": "production_signal" if production_triggered else "research_only",
                    "actionabilityStatus": (
                        "current_threshold_triggered"
                        if production_triggered
                        else "fit_or_predictive_validation_not_eligible"
                    ),
                    "validation": {
                        "productionEvidenceAvailable": production_triggered,
                        "productionActionable": production_triggered,
                        "productionThreshold": 75,
                        "replayModelAudit": {
                            "required": True,
                            "productionModelSpecId": GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
                            "liveModelSpecId": GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
                            "liveModelMetadataAvailable": True,
                            "liveValidationComparable": True,
                            "liveComparable": True,
                            "observedModelSpecIds": [GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID],
                            "observationCount": 120,
                            "comparableObservationCount": 120,
                            "unknownModelSpecCount": 0,
                            "mismatchedModelSpecCount": 0,
                            "replayComparable": True,
                            "comparable": True,
                            "enforcementPass": True,
                            "status": "comparable",
                        },
                    },
                    "factorValidation": {
                        "available": True,
                        "validationStatus": "research-validation",
                        "independentHoldout": False,
                        # A stale/research row may carry a historical true flag;
                        # the parent validation contract must still fail closed.
                        "factors": [
                            {
                                "id": "realizedVol",
                                "classification": "leading",
                                "oosIc3m": 0.5,
                                "wrongWay": False,
                                "lift": 2.0,
                                "robust": True,
                                "fdrSignificant3m": True,
                                "foldStability3m": {"stablePositive": True},
                                "actionableRobust": True,
                                "observationCount": 200,
                                "oosSampleSize3m": 80,
                                "oosAlertCount": 10,
                            }
                        ],
                    },
                }
            ],
        }

    def test_research_only_region_keeps_numeric_band_as_context(self) -> None:
        allocation = build_region_allocation(
            self._region(production_triggered=False, constructive=True)
        )

        self.assertFalse(allocation["actionable"])
        self.assertIsNone(allocation["exposureBandPct"])
        self.assertEqual(allocation["contextBand"], [100, 115])
        self.assertNotEqual(allocation["confidence"], "high")
        self.assertEqual(allocation["scoreUse"], "research_only")
        self.assertIn("不发布数值仓位", allocation["rationale"])

    def test_lkg_row_without_inference_audit_cannot_restore_actionability(self) -> None:
        stale_signal = {
            "classification": "leading",
            "oosIc3m": 0.5,
            "wrongWay": False,
            "lift": 2.0,
            "robust": True,
            "pValue3m": 0.001,
            "fdrSignificant3m": True,
            "foldStability3m": {"stablePositive": True},
            "actionableRobust": True,
            "observationCount": 200,
            "oosSampleSize3m": 80,
            "oosAlertCount": 10,
        }

        self.assertFalse(regional_signal_qualifies_as_actionable(stale_signal))
        apply_benjamini_hochberg([stale_signal])
        self.assertFalse(stale_signal["actionableRobust"])

    def test_production_lppl_trigger_can_publish_numeric_band(self) -> None:
        allocation = build_region_allocation(
            self._region(production_triggered=True)
        )

        self.assertTrue(allocation["actionable"])
        self.assertEqual(allocation["exposureBandPct"], [50, 75])
        self.assertIsNone(allocation["contextBand"])
        self.assertEqual(allocation["confidence"], "high")

    def test_rotation_separates_context_from_binding_regions(self) -> None:
        context = self._region(production_triggered=False, constructive=True)
        context["key"] = "context"
        context["nameCn"] = "研究地区"
        context["allocation"] = build_region_allocation(context)
        production = self._region(production_triggered=True)
        production["key"] = "production"
        production["nameCn"] = "生产地区"
        production["allocation"] = build_region_allocation(production)

        rotation = build_regional_rotation([context, production])

        self.assertEqual(rotation["favorRegions"], [])
        self.assertEqual(rotation["contextFavorRegions"], ["context"])
        self.assertEqual(rotation["reduceRegions"], ["production"])
        self.assertIn("不计入生产配置", rotation["summary"])


class PredictiveLensPurgeTests(unittest.TestCase):
    def test_purge_uses_actual_rolled_price_endpoint(self) -> None:
        start = date(2020, 1, 3)
        week_targets = [start + timedelta(days=7 * index) for index in range(60)]
        # Remove the nominal 91D endpoint for calibration point 25.  Its first
        # actual price endpoint therefore rolls to point 39, exactly the OOS
        # boundary, and must be purged rather than admitted by calendar math.
        price_points = [
            SeriesPoint(
                date=start + timedelta(days=7 * index),
                value=100.0 * math.exp(0.0005 * index * index),
            )
            for index in range(80)
            if index != 38
        ]
        factor_points = [
            SeriesPoint(date=target, value=float(index))
            for index, target in enumerate(week_targets)
        ]

        class Replay:
            @staticmethod
            def factor_score_at(_spec, target):
                return float((target - start).days / 7), True

        result = build_bhadial_predictive_lens(
            Replay(),
            week_targets,
            {"dxy": factor_points},
            [{"id": "dxy", "effectiveWeight": 1.0}],
            SortedSeries(price_points),
            min_factors=1,
            min_calibration_ic=-1.0,
        )

        self.assertTrue(result["available"])
        purge = result["purge"]
        self.assertEqual(purge["oosStartDate"], week_targets[39].isoformat())
        self.assertEqual(purge["latestEligibleSignalDate"], week_targets[24].isoformat())
        self.assertEqual(purge["latestEligibleLabelEndDate"], week_targets[37].isoformat())
        self.assertIn("actual first price endpoint", purge["rule"])


if __name__ == "__main__":
    unittest.main()
