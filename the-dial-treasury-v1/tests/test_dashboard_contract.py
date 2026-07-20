import copy
import unittest

from treasury_data.dashboard_contract import (
    CURRENT_EQUITY_RISK_NORMALIZED_WEIGHTS,
    CURRENT_EQUITY_RISK_RAW_WEIGHTS,
    CURRENT_EQUITY_RISK_SCORE_SCALE_ID,
    CURRENT_EQUITY_RISK_SCORED_COMPONENTS,
    CURRENT_SCHEMA_VERSION,
    CURRENT_SPY_WARNING_RULES_VERSION,
    dashboard_contract_issues,
    require_dashboard_contract,
    stamp_dashboard_contract,
)
from treasury_data.scoring_equity import (
    EQUITY_RISK_COMPONENT_WEIGHTS,
    EQUITY_RISK_REPLAY_SCORED_COMPONENTS,
    EQUITY_RISK_SCORE_SCALE_ID,
    EQUITY_RISK_V2_CANONICAL_NORMALIZED_WEIGHTS,
)
from treasury_data.scoring_spy_warning import SPY_WARNING_RULES_VERSION


def _current_equity_numeric_band_payload() -> dict:
    components = sorted(CURRENT_EQUITY_RISK_SCORED_COMPONENTS)
    weights = dict(CURRENT_EQUITY_RISK_NORMALIZED_WEIGHTS)
    return {
        "schemaVersion": CURRENT_SCHEMA_VERSION,
        "asOf": "2026-07-10",
        "generatedAt": "2026-07-13T00:00:00+00:00",
        "equityShortTermRisk": {
            "score": 80.0,
            "actionable": True,
            "scoreScale": {
                "id": CURRENT_EQUITY_RISK_SCORE_SCALE_ID,
                "requiredScoredComponents": components,
                "scoredComponents": components,
                "canonicalNormalizedWeights": weights,
                "observedNormalizedWeights": dict(weights),
                "weightMismatches": [],
                "weightsMatchCanonical": True,
                "coreComplete": True,
                "thresholdComparable": True,
            },
            "productionValidation": {
                "available": True,
                "threshold": 75,
                "expectedThreshold": 75,
                "scoreContractAllowsAction": True,
                "validationEvidenceComplete": True,
                "thresholdValidated": True,
                "currentTriggered": True,
                "actionable": True,
                "scoreScaleMatchesBacktest": True,
                "scoreWeightsMatchBacktest": True,
                "sampleRole": "walkForwardOos",
                "independentAlertClusters": 10,
                "clusterPrecisionWilsonLower95": 72.2,
                "baseRate": 50.0,
            },
            "backtest": {
                "scoreScale": {
                    "id": CURRENT_EQUITY_RISK_SCORE_SCALE_ID,
                    "requiredScoredComponents": components,
                    "canonicalNormalizedWeights": weights,
                    "observedNormalizedWeights": dict(weights),
                    "weightsMatchCanonical": True,
                    "weightMismatchedObservationCount": 0,
                    "observationCount": 100,
                    "comparableObservationCount": 100,
                    "mismatchedObservationCount": 0,
                    "thresholdComparable": True,
                },
                "walkForward": {
                    "available": True,
                    "thresholdTests": [
                        {
                            "threshold": 75,
                            "productionUse": True,
                            "sampleRole": "walkForwardOos",
                            "validationStatus": "validated",
                            "oosValidated": True,
                            "sampleSize": 100,
                            "independentAlertClusters": 10,
                            "independentHitClusters": 10,
                            "baseRate": 50.0,
                        }
                    ],
                },
            },
            "allocation": {
                "actionable": True,
                "exposureBandPct": [50, 75],
            },
        },
    }


def _current_spy_numeric_band_payload() -> dict:
    version = CURRENT_SPY_WARNING_RULES_VERSION
    return {
        "schemaVersion": CURRENT_SCHEMA_VERSION,
        "asOf": "2026-07-10",
        "generatedAt": "2026-07-13T00:00:00+00:00",
        "spyEarlyWarning": {
            "rulesVersion": version,
            "aggregateCiRobust": True,
            "aggregateStatisticalGatePassed": True,
            "aggregateActionableRobust": True,
            "aggregateRobust": True,
            "scoreUse": "production_signal",
            "actionable": True,
            "predictiveValidity": {
                "status": "actionable",
                "actionable": True,
                "statisticalGatePassed": True,
                "independentHoldout": True,
                "rulesVersionAudit": {
                    "expectedRulesVersion": version,
                    "surfaceRulesVersion": version,
                    "validationRulesVersion": version,
                    "aggregateRulesVersion": version,
                    "complete": True,
                    "matched": True,
                },
            },
            "allocation": {
                "actionable": True,
                "exposureBandPct": [50, 75],
            },
        },
    }


class DashboardContractTests(unittest.TestCase):
    def test_equity_scoring_and_contract_share_current_scale_weights(self):
        self.assertEqual(EQUITY_RISK_SCORE_SCALE_ID, CURRENT_EQUITY_RISK_SCORE_SCALE_ID)
        self.assertEqual(
            EQUITY_RISK_REPLAY_SCORED_COMPONENTS,
            CURRENT_EQUITY_RISK_SCORED_COMPONENTS,
        )
        self.assertEqual(
            EQUITY_RISK_V2_CANONICAL_NORMALIZED_WEIGHTS,
            CURRENT_EQUITY_RISK_NORMALIZED_WEIGHTS,
        )
        self.assertEqual(
            {key: EQUITY_RISK_COMPONENT_WEIGHTS[key] for key in CURRENT_EQUITY_RISK_SCORED_COMPONENTS},
            CURRENT_EQUITY_RISK_RAW_WEIGHTS,
        )

    def test_contract_accepts_equity_band_with_current_canonical_weight_audit(self):
        self.assertEqual(
            dashboard_contract_issues(_current_equity_numeric_band_payload()),
            [],
        )

    def test_contract_rejects_missing_or_wrong_equity_production_threshold_audit(self):
        threshold_issue = (
            "equityShortTermRisk numeric allocation requires current production threshold audit"
        )
        cases = []
        for field in ("threshold", "expectedThreshold"):
            missing_threshold = _current_equity_numeric_band_payload()
            missing_threshold["equityShortTermRisk"]["productionValidation"].pop(field)
            cases.append((f"missing {field}", missing_threshold))

            wrong_threshold = _current_equity_numeric_band_payload()
            wrong_threshold["equityShortTermRisk"]["productionValidation"][field] = 60
            cases.append((f"wrong {field}", wrong_threshold))

        bool_threshold = _current_equity_numeric_band_payload()
        bool_threshold["equityShortTermRisk"]["productionValidation"]["threshold"] = True
        cases.append(("boolean threshold", bool_threshold))

        for label, payload in cases:
            with self.subTest(label=label):
                issues = dashboard_contract_issues(payload)
                self.assertIn(threshold_issue, issues)
                self.assertIn(
                    "equityShortTermRisk numeric allocation requires every production action gate to pass",
                    issues,
                )

    def test_contract_rejects_missing_stale_or_self_consistent_drifted_equity_weight_audit(self):
        canonical_issue = (
            "equityShortTermRisk numeric allocation requires current canonical scoreScale weight audit"
        )
        validation_issue = (
            "equityShortTermRisk numeric allocation requires complete productionValidation boolean audit"
        )
        cases = []

        for field in (
            "canonicalNormalizedWeights",
            "observedNormalizedWeights",
            "weightsMatchCanonical",
        ):
            missing_audit = _current_equity_numeric_band_payload()
            missing_audit["equityShortTermRisk"]["scoreScale"].pop(field)
            cases.append((f"missing {field}", missing_audit, canonical_issue))

        stale_scale = _current_equity_numeric_band_payload()
        stale_scale["equityShortTermRisk"]["scoreScale"]["id"] = "equity-risk-ohlcv-core-v1"
        cases.append(("stale scale", stale_scale, canonical_issue))

        self_consistent_drift = _current_equity_numeric_band_payload()
        drifted_weights = dict(CURRENT_EQUITY_RISK_NORMALIZED_WEIGHTS)
        drifted_weights["hotStockReversal"] = round(
            drifted_weights["hotStockReversal"] + 0.01,
            8,
        )
        drifted_scale = self_consistent_drift["equityShortTermRisk"]["scoreScale"]
        drifted_scale["canonicalNormalizedWeights"] = drifted_weights
        drifted_scale["observedNormalizedWeights"] = dict(drifted_weights)
        drifted_scale["weightMismatches"] = []
        drifted_scale["weightsMatchCanonical"] = True
        cases.append(("self-consistent weight drift", self_consistent_drift, canonical_issue))

        for field in ("scoreScaleMatchesBacktest", "scoreWeightsMatchBacktest"):
            missing_validation = _current_equity_numeric_band_payload()
            missing_validation["equityShortTermRisk"]["productionValidation"].pop(field)
            cases.append((f"missing {field}", missing_validation, validation_issue))

            failed_validation = _current_equity_numeric_band_payload()
            failed_validation["equityShortTermRisk"]["productionValidation"][field] = False
            cases.append((f"failed {field}", failed_validation, "every production action gate"))

        for label, payload, expected_issue in cases:
            with self.subTest(label=label):
                issues = dashboard_contract_issues(copy.deepcopy(payload))
                self.assertTrue(
                    any(expected_issue in issue for issue in issues),
                    issues,
                )

    def test_contract_recomputes_equity_action_from_score_backtest_and_oos_evidence(self):
        backtest_issue = (
            "equityShortTermRisk numeric allocation requires matching replay backtest scoreScale audit"
        )
        oos_issue = (
            "equityShortTermRisk numeric allocation requires a validated fixed-threshold "
            "walkForward OOS production test"
        )
        cases: list[tuple[str, dict, str]] = []

        score_below_threshold = _current_equity_numeric_band_payload()
        score_below_threshold["equityShortTermRisk"]["score"] = 74.9
        cases.append(("score below fixed threshold", score_below_threshold, oos_issue))

        missing_backtest_scale = _current_equity_numeric_band_payload()
        missing_backtest_scale["equityShortTermRisk"]["backtest"].pop("scoreScale")
        cases.append(("missing replay scale", missing_backtest_scale, backtest_issue))

        drifted_backtest_weights = _current_equity_numeric_band_payload()
        observed = dict(CURRENT_EQUITY_RISK_NORMALIZED_WEIGHTS)
        observed["sectorRotation"] = 0.5
        drifted_backtest_weights["equityShortTermRisk"]["backtest"]["scoreScale"][
            "observedNormalizedWeights"
        ] = observed
        cases.append(("drifted replay weights", drifted_backtest_weights, backtest_issue))

        missing_walk_forward = _current_equity_numeric_band_payload()
        missing_walk_forward["equityShortTermRisk"]["backtest"].pop("walkForward")
        cases.append(("missing walk-forward", missing_walk_forward, oos_issue))

        unvalidated_oos = _current_equity_numeric_band_payload()
        unvalidated_oos["equityShortTermRisk"]["backtest"]["walkForward"][
            "thresholdTests"
        ][0]["oosValidated"] = False
        cases.append(("producer boolean hides failed OOS", unvalidated_oos, oos_issue))

        too_few_episodes = _current_equity_numeric_band_payload()
        too_few_episodes["equityShortTermRisk"]["backtest"]["walkForward"][
            "thresholdTests"
        ][0]["independentAlertClusters"] = 2
        cases.append(("too few independent episodes", too_few_episodes, oos_issue))

        for label, payload, expected_issue in cases:
            with self.subTest(label=label):
                issues = dashboard_contract_issues(payload)
                self.assertIn(expected_issue, issues)
                self.assertIn(
                    "equityShortTermRisk numeric allocation requires every production action gate to pass",
                    issues,
                )

    def test_spy_scoring_and_contract_share_current_rules_version(self):
        self.assertEqual(
            SPY_WARNING_RULES_VERSION,
            CURRENT_SPY_WARNING_RULES_VERSION,
        )

    def test_stamp_adds_current_version_without_overwriting_existing_version(self):
        payload = {"asOf": "2026-07-10", "generatedAt": "2026-07-13T00:00:00+00:00"}

        self.assertIs(stamp_dashboard_contract(payload), payload)
        self.assertEqual(payload["schemaVersion"], CURRENT_SCHEMA_VERSION)

        payload["schemaVersion"] = "future"
        stamp_dashboard_contract(payload)
        self.assertEqual(payload["schemaVersion"], "future")

    def test_contract_accepts_versioned_envelope(self):
        payload = {
            "schemaVersion": CURRENT_SCHEMA_VERSION,
            "asOf": "2026-07-10",
            "generatedAt": "2026-07-13T00:00:00+00:00",
            "sourceStatus": [],
            "curve": {"tenors": ["2Y", "10Y"]},
        }

        self.assertEqual(dashboard_contract_issues(payload), [])
        self.assertIs(require_dashboard_contract(payload), payload)

    def test_contract_rejects_unknown_version_and_wrong_nested_type(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": "2.0.0",
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "curve": {"tenors": "10Y"},
            }
        )

        self.assertIn("unsupported schemaVersion: 2.0.0", issues)
        self.assertIn("curve.tenors must be an array", issues)

    def test_contract_rejects_malformed_or_naive_snapshot_dates(self):
        malformed = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "07/10/2026",
                "generatedAt": "2026-07-13 00:00:00",
            }
        )
        self.assertIn("asOf must be an ISO date", malformed)
        self.assertIn("generatedAt must include a timezone", malformed)

        future_as_of = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-14",
                "generatedAt": "2026-07-13T23:00:00+00:00",
            }
        )
        self.assertIn("asOf must not be after generatedAt date", future_as_of)

    def test_contract_rejects_non_finite_json_numbers(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "macroLiquidity": {"score": float("nan")},
            }
        )

        self.assertTrue(any("strict JSON serializable" in issue for issue in issues))

    def test_contract_rejects_non_actionable_exposure_band(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "equityShortTermRisk": {
                    "actionable": False,
                    "scoreScale": {"coreComplete": False, "thresholdComparable": False},
                    "allocation": {"actionable": False, "exposureBandPct": [25, 50]},
                },
            }
        )

        self.assertIn(
            "equityShortTermRisk.allocation must not expose a band when non-actionable",
            issues,
        )

    def test_contract_rejects_failed_predictive_validity_with_action_layer(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "spyEarlyWarning": {
                    "predictiveValidity": {"actionable": False},
                    "allocation": {"actionable": True, "exposureBandPct": None},
                },
            }
        )

        self.assertIn(
            "spyEarlyWarning.allocation.actionable must be false when predictive validity fails",
            issues,
        )

    def test_contract_rejects_spy_numeric_band_without_complete_validation(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "spyEarlyWarning": {
                    "score": 62.0,
                    "allocation": {"exposureBandPct": [50, 75]},
                },
            }
        )

        self.assertIn(
            "spyEarlyWarning numeric allocation requires complete predictiveValidity audit",
            issues,
        )
        self.assertIn(
            "spyEarlyWarning numeric allocation requires every production action gate to pass",
            issues,
        )
        self.assertIn(
            "spyEarlyWarning numeric allocation requires complete matching rulesVersion audit",
            issues,
        )

    def test_contract_accepts_spy_numeric_band_with_matching_version_audit(self):
        issues = dashboard_contract_issues(_current_spy_numeric_band_payload())

        self.assertEqual(issues, [])

    def test_contract_recomputes_spy_action_from_aggregate_root_evidence(self):
        aggregate_issue = (
            "spyEarlyWarning numeric allocation requires matching aggregate production evidence"
        )
        for field in (
            "aggregateCiRobust",
            "aggregateStatisticalGatePassed",
            "aggregateActionableRobust",
            "aggregateRobust",
        ):
            for mutation in ("false", "missing"):
                with self.subTest(field=field, mutation=mutation):
                    payload = _current_spy_numeric_band_payload()
                    surface = payload["spyEarlyWarning"]
                    if mutation == "false":
                        surface[field] = False
                    else:
                        surface.pop(field)
                    issues = dashboard_contract_issues(payload)
                    self.assertIn(aggregate_issue, issues)
                    self.assertIn(
                        "spyEarlyWarning numeric allocation requires every production action gate to pass",
                        issues,
                    )

        for field, value in (("scoreUse", "research_only"),):
            with self.subTest(field=field):
                payload = _current_spy_numeric_band_payload()
                payload["spyEarlyWarning"][field] = value
                issues = dashboard_contract_issues(payload)
                self.assertIn(aggregate_issue, issues)

    def test_contract_rejects_spy_band_when_version_strings_disagree(self):
        version = SPY_WARNING_RULES_VERSION
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "spyEarlyWarning": {
                    "rulesVersion": version,
                    "actionable": True,
                    "predictiveValidity": {
                        "actionable": True,
                        "statisticalGatePassed": True,
                        "independentHoldout": True,
                        # Even dishonest true booleans cannot hide unequal
                        # provenance strings from the contract checker.
                        "rulesVersionAudit": {
                            "expectedRulesVersion": version,
                            "surfaceRulesVersion": version,
                            "validationRulesVersion": "2026-06-19-v2",
                            "aggregateRulesVersion": "2026-06-19-v2",
                            "complete": True,
                            "matched": True,
                        },
                    },
                    "allocation": {
                        "actionable": True,
                        "exposureBandPct": [50, 75],
                    },
                },
            }
        )

        self.assertIn(
            "spyEarlyWarning numeric allocation requires complete matching rulesVersion audit",
            issues,
        )
        self.assertIn(
            "spyEarlyWarning numeric allocation requires every production action gate to pass",
            issues,
        )

    def test_contract_rejects_coherent_but_stale_spy_version(self):
        stale_version = "2026-06-19-v2"
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "spyEarlyWarning": {
                    "rulesVersion": stale_version,
                    "actionable": True,
                    "predictiveValidity": {
                        "actionable": True,
                        "statisticalGatePassed": True,
                        "independentHoldout": True,
                        "rulesVersionAudit": {
                            "expectedRulesVersion": stale_version,
                            "surfaceRulesVersion": stale_version,
                            "validationRulesVersion": stale_version,
                            "aggregateRulesVersion": stale_version,
                            "complete": True,
                            "matched": True,
                        },
                    },
                    "allocation": {
                        "actionable": True,
                        "exposureBandPct": [50, 75],
                    },
                },
            }
        )

        self.assertIn(
            "spyEarlyWarning numeric allocation requires complete matching rulesVersion audit",
            issues,
        )
        self.assertIn(
            "spyEarlyWarning numeric allocation requires every production action gate to pass",
            issues,
        )

    def test_contract_rejects_unvalidated_high_regional_confidence(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "regionalMonitor": {
                    "regions": [
                        {
                            "allocation": {
                                "confidence": "high",
                                "validatedLeadingFactors": [],
                                "validatedComposite": False,
                            }
                        }
                    ]
                },
            }
        )

        self.assertIn(
            "regionalMonitor.regions[0].allocation high confidence requires validated evidence",
            issues,
        )

    def test_contract_accepts_high_regional_confidence_from_triggered_production_lppl(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "regionalMonitor": {
                    "regions": [
                        {
                            "allocation": {
                                "confidence": "high",
                                "validatedLeadingFactors": [],
                                "validatedComposite": False,
                                "productionLpplTriggered": True,
                            }
                        }
                    ]
                },
            }
        )

        self.assertEqual(issues, [])

    def test_contract_validates_structured_source_freshness_dates(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "sourceStatus": [
                    {
                        "observationDate": "2026-05-01",
                        "observationPeriodEnd": "2026-04-30",
                        "freshnessBasis": "estimated-release-date",
                    }
                ],
            }
        )

        self.assertIn(
            "sourceStatus[0] observationPeriodEnd must not precede observationDate",
            issues,
        )
        self.assertIn("sourceStatus[0].freshnessBasis is invalid", issues)

    def test_contract_accepts_forward_calendar_horizon(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-20",
                "generatedAt": "2026-07-20T12:00:00+00:00",
                "sourceStatus": [
                    {
                        "observationDate": "2026-12-23",
                        "observationPeriodEnd": "2026-12-23",
                        "coverageThrough": "2026-12-23",
                        "freshnessBasis": "calendar-horizon",
                    }
                ],
            }
        )

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
