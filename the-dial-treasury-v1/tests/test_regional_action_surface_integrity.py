import unittest

from treasury_data.api import regional_alerts_health
from treasury_data.dashboard_contract import CURRENT_SCHEMA_VERSION, dashboard_contract_issues
from treasury_data.scoring_regional import (
    build_region_allocation,
    build_region_factor_alert,
    build_regional_rotation,
    regional_monitor_aggregate,
)


PRODUCTION_MODEL_SPEC_ID = "lppl-multiwindow-fullgrid-refine-v1"


def _complete_replay_model_audit() -> dict:
    return {
        "required": True,
        "productionModelSpecId": PRODUCTION_MODEL_SPEC_ID,
        "liveModelSpecId": PRODUCTION_MODEL_SPEC_ID,
        "liveModelMetadataAvailable": True,
        "liveValidationComparable": True,
        "liveComparable": True,
        "observedModelSpecIds": [PRODUCTION_MODEL_SPEC_ID],
        "observationCount": 120,
        "comparableObservationCount": 120,
        "unknownModelSpecCount": 0,
        "mismatchedModelSpecCount": 0,
        "replayComparable": True,
        "comparable": True,
        "enforcementPass": True,
        "status": "comparable",
    }


def _complete_lppl_row(*, score: float = 85.0, status: str = "risk") -> dict:
    return {
        "symbol": "TEST",
        "available": True,
        "score": score,
        "status": status,
        "statusCn": "泡沫风险",
        "fitProductionEligible": True,
        "productionEligible": True,
        "actionable": True,
        "scoreUse": "production_signal",
        "actionabilityStatus": "current_threshold_triggered",
        "validation": {
            "productionEvidenceAvailable": True,
            "productionActionable": True,
            "productionThreshold": 75,
            "replayModelAudit": _complete_replay_model_audit(),
        },
    }


def _base_region(row: dict, *, key: str = "test") -> dict:
    aggregate = regional_monitor_aggregate([row])
    aggregate["priceFactors"] = {
        "available": True,
        "marketState": "stressed",
        "marketStateCn": "承压",
        "relativeStrength3m": -8.0,
    }
    return {
        "key": key,
        "name": "Test",
        "nameCn": "测试",
        "indices": [row],
        "aggregate": aggregate,
    }


def _validated_factor_region() -> dict:
    factor = {
        "id": "realizedVol",
        "labelCn": "已实现波动",
        "classification": "leading",
        "oosIc3m": 0.4,
        "wrongWay": False,
        "lift": 1.4,
        "robust": True,
        "fdrSignificant3m": True,
        "inferenceValid3m": True,
        "foldStability3m": {"stablePositive": True},
        "actionableRobust": True,
        "observationCount": 180,
        "oosSampleSize3m": 60,
        "oosAlertCount": 8,
        "alertThreshold": 20.0,
        "hitRateOos": 0.45,
        "baseRate": 0.30,
    }
    row = {
        "symbol": "TEST",
        "available": True,
        "score": 45.0,
        "status": "watch",
        "priceFactors": {"available": True, "realizedVol": 25.0},
        "factorValidation": {
            "available": True,
            "independentHoldout": True,
            "factors": [factor],
        },
    }
    region = {
        "key": "factor",
        "name": "Factor",
        "nameCn": "因子地区",
        "indices": [row],
        "aggregate": {
            "status": "watch",
            "statusCn": "观察",
            "availableCount": 1,
            "indexCount": 1,
            "actionableRiskCount": 0,
            "priceFactors": {
                "available": True,
                "marketState": "neutral",
                "marketStateCn": "中性",
                "relativeStrength3m": 0.0,
            },
        },
    }
    region["factorAlert"] = build_region_factor_alert(region)
    region["allocation"] = build_region_allocation(region)
    return region


class RegionalActionSurfaceIntegrityTests(unittest.TestCase):
    def test_legacy_lppl_true_flags_without_validation_cannot_bind_allocation(self) -> None:
        legacy = {
            "symbol": "OLD",
            "available": True,
            "score": 90.0,
            "status": "risk",
            "actionable": True,
            "productionEligible": True,
        }
        region = _base_region(legacy)
        allocation = build_region_allocation(region)

        self.assertEqual(region["aggregate"]["actionableRiskCount"], 0)
        self.assertFalse(allocation["actionable"])
        self.assertIsNone(allocation["exposureBandPct"])
        self.assertEqual(allocation["contextBand"], [80, 100])

    def test_lppl_true_flags_cannot_bypass_model_fingerprint_mismatch(self) -> None:
        row = _complete_lppl_row()
        audit = row["validation"]["replayModelAudit"]
        audit.update(
            {
                "enforcementPass": False,
                "status": "model_spec_mismatch",
                "comparable": False,
                "replayComparable": False,
            }
        )
        region = _base_region(row)
        allocation = build_region_allocation(region)

        self.assertEqual(region["aggregate"]["actionableRiskCount"], 0)
        self.assertFalse(allocation["actionable"])
        self.assertIsNone(allocation["exposureBandPct"])

    def test_contract_checks_model_fingerprint_and_current_threshold_itself(self) -> None:
        mismatch = _complete_lppl_row()
        mismatch["validation"]["replayModelAudit"].update(
            {"enforcementPass": False, "status": "live_model_mismatch", "liveComparable": False}
        )
        below_threshold = _complete_lppl_row(score=74.9)
        for label, row in (("model_mismatch", mismatch), ("below_threshold", below_threshold)):
            with self.subTest(label=label):
                region = _base_region(row, key=label)
                # Simulate a dishonest/stale producer whose derived booleans and
                # allocation all say true.  The contract must recompute the two
                # immutable gates from the model audit and score/threshold pair.
                region["aggregate"]["actionableRiskCount"] = 1
                region["allocation"] = {
                    "stance": "underweight",
                    "confidence": "high",
                    "exposureBandPct": [50, 75],
                    "actionable": True,
                    "scoreUse": "production_signal",
                    "actionabilityStatus": "current_lppl_or_validated_factor_trigger",
                    "productionLpplTriggered": True,
                    "validatedFactorTriggered": False,
                    "validatedLeadingFactors": [],
                    "validatedComposite": False,
                }
                issues = dashboard_contract_issues(
                    {
                        "schemaVersion": CURRENT_SCHEMA_VERSION,
                        "asOf": "2026-07-20",
                        "generatedAt": "2026-07-20T08:00:00+00:00",
                        "regionalMonitor": {"regions": [region], "rotation": {}},
                    }
                )
                self.assertIn(
                    "regionalMonitor.regions[0].allocation numeric band requires complete current production trigger audit",
                    issues,
                )

    def test_validated_factor_requires_current_threshold_breach(self) -> None:
        region = _validated_factor_region()
        self.assertTrue(region["factorAlert"]["actionable"])
        self.assertTrue(region["allocation"]["validatedFactorTriggered"])
        self.assertTrue(region["allocation"]["actionable"])

        region["indices"][0]["priceFactors"]["realizedVol"] = 15.0
        region["factorAlert"] = build_region_factor_alert(region)
        region["allocation"] = build_region_allocation(region)

        self.assertEqual(region["factorAlert"]["state"], "normal")
        self.assertFalse(region["factorAlert"]["actionable"])
        self.assertFalse(region["allocation"]["validatedFactorTriggered"])
        self.assertFalse(region["allocation"]["actionable"])
        self.assertIsNone(region["allocation"]["exposureBandPct"])

    def test_rotation_rechecks_region_evidence_instead_of_trusting_legacy_flags(self) -> None:
        legacy_region = {
            "key": "legacy",
            "nameCn": "旧地区",
            "aggregate": {"availableCount": 1},
            "indices": [],
            "allocation": {
                "stance": "underweight",
                "cautionScore": 90.0,
                "exposureBandPct": [50, 75],
                "actionable": True,
            },
        }

        rotation = build_regional_rotation([legacy_region])

        self.assertEqual(rotation["reduceRegions"], [])
        self.assertEqual(rotation["contextReduceRegions"], ["legacy"])
        self.assertFalse(rotation["actionable"])
        self.assertEqual(rotation["scoreUse"], "research_only")

    def test_health_suppresses_legacy_breach_and_rotation_actions(self) -> None:
        legacy_monitor = {
            "available": True,
            "asOf": "2026-07-16",
            "rotation": {
                "favorRegions": ["japan"],
                "reduceRegions": ["korea", "taiwan"],
                "summary": "增持日本; 减持韩国、台湾",
            },
            "regions": [
                {
                    "key": "korea",
                    "nameCn": "韩国",
                    "indices": [],
                    "allocation": {
                        "stance": "underweight",
                        "exposureBandPct": [50, 75],
                    },
                    "factorAlert": {
                        "available": True,
                        "state": "breached",
                        "factorLabelCn": "已实现波动",
                        "current": 39.5,
                        "threshold": 12.2,
                    },
                }
            ],
        }

        health = regional_alerts_health(legacy_monitor)

        self.assertFalse(health["actionable"])
        self.assertEqual(health["breachCount"], 0)
        self.assertEqual(health["reduceRegions"], [])
        self.assertEqual(health["favorRegions"], [])
        self.assertIn("不发布", health["summary"])

    def test_health_keeps_complete_current_factor_trigger(self) -> None:
        region = _validated_factor_region()
        monitor = {
            "available": True,
            "asOf": "2026-07-20",
            "rotation": build_regional_rotation([region]),
            "regions": [region],
        }

        health = regional_alerts_health(monitor)

        self.assertTrue(health["actionable"])
        self.assertEqual(health["breachCount"], 1)
        self.assertEqual(health["breached"][0]["key"], "factor")

    def test_dashboard_contract_rejects_legacy_region_actions(self) -> None:
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-16",
                "generatedAt": "2026-07-20T00:00:00+00:00",
                "regionalMonitor": {
                    "rotation": {"favorRegions": ["japan"], "reduceRegions": ["korea"]},
                    "regions": [
                        {
                            "key": "korea",
                            "allocation": {
                                "stance": "underweight",
                                "confidence": "high",
                                "validatedLeadingFactors": [{"id": "realizedVol"}],
                                "exposureBandPct": [50, 75],
                            },
                            "factorAlert": {"available": True, "state": "breached"},
                            "internalRotation": {
                                "available": True,
                                "tilt": "broad",
                                "tiltCn": "偏宽基(SPY)、减科技(QQQ)",
                            },
                        }
                    ],
                },
            }
        )

        self.assertIn(
            "regionalMonitor.regions[0].allocation numeric band requires complete current production trigger audit",
            issues,
        )
        self.assertIn(
            "regionalMonitor.regions[0].factorAlert breach requires complete current trigger audit",
            issues,
        )
        self.assertIn(
            "regionalMonitor.rotation.reduceRegions contains regions without complete production action audit",
            issues,
        )
        self.assertIn(
            "regionalMonitor.regions[0].internalRotation directional tilt requires complete current production trigger audit",
            issues,
        )

    def test_dashboard_contract_rejects_self_declared_factor_action(self) -> None:
        region = {
            "key": "dishonest",
            "indices": [],
            "allocation": {
                "stance": "underweight",
                "confidence": "medium",
                "exposureBandPct": [50, 75],
                "actionable": True,
                "scoreUse": "production_signal",
                "actionabilityStatus": "current_lppl_or_validated_factor_trigger",
                "productionLpplTriggered": False,
                "validatedFactorTriggered": True,
                "validatedLeadingFactors": [{"id": "realizedVol"}],
                "validatedComposite": False,
            },
            "factorAlert": {
                "available": True,
                "state": "breached",
                "actionable": True,
                "scoreUse": "production_signal",
                "source": "factor",
                "factorId": "realizedVol",
                "current": 25.0,
                "threshold": 20.0,
            },
        }
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-20",
                "generatedAt": "2026-07-20T08:00:00+00:00",
                "regionalMonitor": {
                    "regions": [region],
                    "rotation": {"reduceRegions": ["dishonest"]},
                },
            }
        )

        self.assertIn(
            "regionalMonitor.regions[0].allocation numeric band requires complete current production trigger audit",
            issues,
        )
        self.assertIn(
            "regionalMonitor.regions[0].factorAlert breach requires complete current trigger audit",
            issues,
        )
        self.assertIn(
            "regionalMonitor.rotation.reduceRegions contains regions without complete production action audit",
            issues,
        )

    def test_dashboard_contract_accepts_complete_current_factor_action(self) -> None:
        region = _validated_factor_region()
        rotation = build_regional_rotation([region])
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-20",
                "generatedAt": "2026-07-20T08:00:00+00:00",
                "regionalMonitor": {"regions": [region], "rotation": rotation},
            }
        )

        self.assertEqual(issues, [])

    def test_dashboard_contract_accepts_complete_current_lppl_region_action(self) -> None:
        region = _base_region(_complete_lppl_row(), key="current")
        region["allocation"] = build_region_allocation(region)
        rotation = build_regional_rotation([region])
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-20",
                "generatedAt": "2026-07-20T08:00:00+00:00",
                "regionalMonitor": {"regions": [region], "rotation": rotation},
            }
        )

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
