import unittest

from treasury_data import scoring_equity


class EquityVolatilityEstimatorIntegrityTests(unittest.TestCase):
    @staticmethod
    def strict_metrics(**overrides):
        metrics = {
            "validationDesign": "singlePurgedChronologicalHoldout",
            "splitDate": "2025-10-01",
            "purgedTrainingRows": 15,
            "purgeRule": "keep labels ending before split",
            "threshold": 75,
            "horizon": 15,
            "eventDefinition": "next-open 15-session drawdown <= -2%",
            "oosSampleSize": 40,
            "oosDateRange": {"start": "2025-10-01", "end": "2025-11-26"},
            "oosObservationFingerprint": "same-oos-label-sample",
            "oosSampleRole": "walkForwardOos",
            "oosProductionUse": True,
            "oosClusterDedupeRule": "first alert owns its 15-session label window",
            "oosIndependentEpisodeMetricsAvailable": True,
            "oosValidated": True,
            "oosAlertEpisodes": 6,
            "oosAlertDays": 18,
            "oosPrecision": 60.0,
            "oosLiftVsBaseRate": 2.0,
            "oosFalsePositives": 3,
            "precision": 70.0,
        }
        metrics.update(overrides)
        return metrics

    def test_metrics_use_independent_episodes_for_promotion_fields(self):
        backtest = {
            "sampleSize": 100,
            "preferredHorizon": 15,
            "drawdownEvent": "next-open 15-session drawdown <= -2%",
            "preferredThresholdTest": {
                "horizon": 15,
                "alertDays": 30,
                "precision": 95.0,
                "recall": 80.0,
                "falsePositives": 2,
                "liftVsBaseRate": 3.8,
            },
            "walkForward": {
                "validationDesign": "singlePurgedChronologicalHoldout",
                "splitDate": "2025-10-01",
                "purgedTrainingRows": 15,
                "purgeRule": "keep labels ending before split",
                "oosObservationFingerprint": "sample-fingerprint",
                "outOfSample": {
                    "sampleSize": 40,
                    "dateRange": {"start": "2025-10-01", "end": "2025-11-26"},
                },
            },
            "outOfSampleThresholdTests": [
                {
                    "threshold": 75,
                    "horizon": 15,
                    "sampleSize": 40,
                    "sampleRole": "walkForwardOos",
                    "productionUse": True,
                    "alertDays": 20,
                    "precision": 90.0,
                    "recall": 75.0,
                    "falsePositives": 2,
                    "liftVsBaseRate": 3.6,
                    "baseRate": 25.0,
                    "independentAlertClusters": 1,
                    "independentHitClusters": 0,
                    "independentFalseClusters": 1,
                    "clusterPrecision": 0.0,
                    "clusterDedupeRule": "first alert owns its 15-session label window",
                    "oosValidated": False,
                }
            ],
            "componentDiagnostics": [],
        }

        metrics = scoring_equity.equity_estimator_backtest_metrics(backtest)

        self.assertEqual(metrics["oosAlertEpisodes"], 1)
        self.assertEqual(metrics["oosPrecision"], 0.0)
        self.assertEqual(metrics["oosFalsePositives"], 1)
        self.assertEqual(metrics["oosDailyPrecision"], 90.0)
        self.assertEqual(metrics["oosDailyFalsePositives"], 2)
        self.assertEqual(metrics["oosAlertDays"], 20)
        self.assertEqual(metrics["oosPrecisionMetric"], "independentAlertClusterPrecision")
        self.assertFalse(metrics["fullSampleEligibleForPromotion"])

    def test_many_daily_alerts_from_one_episode_cannot_advance(self):
        production = self.strict_metrics()
        candidate = self.strict_metrics(
            oosAlertEpisodes=1,
            oosAlertDays=30,
            oosPrecision=100.0,
            oosLiftVsBaseRate=3.5,
            oosFalsePositives=0,
        )

        verdict = scoring_equity.equity_estimator_audit_verdict(production, candidate)

        self.assertEqual(verdict["verdict"], "insufficientEvidence")
        self.assertIn("episode", verdict["summary"])

    def test_full_sample_precision_is_descriptive_not_a_promotion_gate(self):
        production = self.strict_metrics(precision=95.0)
        candidate = self.strict_metrics(
            precision=10.0,
            oosPrecision=65.0,
            oosLiftVsBaseRate=2.2,
            oosFalsePositives=2,
        )

        verdict = scoring_equity.equity_estimator_audit_verdict(production, candidate)

        self.assertEqual(verdict["verdict"], "candidatePromising")
        self.assertTrue(verdict["comparisonContract"]["fullSampleExcluded"])

    def test_different_purged_holdout_blocks_candidate(self):
        production = self.strict_metrics()
        candidate = self.strict_metrics(
            splitDate="2025-10-02",
            oosDateRange={"start": "2025-10-02", "end": "2025-11-27"},
            oosObservationFingerprint="different-oos-label-sample",
            oosPrecision=70.0,
            oosLiftVsBaseRate=2.4,
            oosFalsePositives=1,
        )

        verdict = scoring_equity.equity_estimator_audit_verdict(production, candidate)

        self.assertEqual(verdict["verdict"], "insufficientEvidence")
        self.assertFalse(verdict["comparisonContract"]["samePurgedHoldout"])
        self.assertIn("splitDate", verdict["comparisonContract"]["mismatchedFields"])
        self.assertIn("oosObservationFingerprint", verdict["comparisonContract"]["mismatchedFields"])

    def test_candidate_must_pass_fixed_threshold_oos_validation(self):
        production = self.strict_metrics()
        candidate = self.strict_metrics(
            oosValidated=False,
            oosPrecision=70.0,
            oosLiftVsBaseRate=2.4,
            oosFalsePositives=1,
        )

        verdict = scoring_equity.equity_estimator_audit_verdict(production, candidate)

        self.assertEqual(verdict["verdict"], "insufficientEvidence")
        self.assertIn("预注册阈值", verdict["summary"])

    def test_validation_sample_fingerprint_ignores_candidate_scores(self):
        first = [
            {
                "date": "2025-10-01",
                "executionDate": "2025-10-02",
                "labelStartDate15d": "2025-10-02",
                "labelEndDate15d": "2025-10-22",
                "maxDrawdown15d": -2.5,
                "drawdownEvent15d": True,
                "score": 74.0,
            }
        ]
        second = [{**first[0], "score": 88.0}]
        changed_label = [{**first[0], "maxDrawdown15d": -1.5, "drawdownEvent15d": False}]

        first_fingerprint = scoring_equity.equity_validation_sample_fingerprint(first, horizon=15)

        self.assertEqual(
            first_fingerprint,
            scoring_equity.equity_validation_sample_fingerprint(second, horizon=15),
        )
        self.assertNotEqual(
            first_fingerprint,
            scoring_equity.equity_validation_sample_fingerprint(changed_label, horizon=15),
        )


if __name__ == "__main__":
    unittest.main()
