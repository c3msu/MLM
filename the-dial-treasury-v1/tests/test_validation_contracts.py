from __future__ import annotations

import unittest

from treasury_data.scoring_spy_warning import SPY_WARNING_RULES_VERSION
from treasury_data.validation_build import annotate_spy_warning_robustness


class PredictiveValidityContractTests(unittest.TestCase):
    def test_missing_spy_validation_fails_closed_and_keeps_band_as_context(self) -> None:
        original_summary = "SPY预警62.0,进入减仓预警: 新增仓位放慢,维持核心仓位。"
        warning = {
            "score": 62.0,
            "regime": "Caution",
            "regimeCn": "谨慎",
            "summary": original_summary,
            "allocation": {
                "horizon": "1-3M",
                "horizonCn": "1-3个月",
                "exposureBandPct": [50, 75],
            },
        }

        annotate_spy_warning_robustness(
            warning,
            {"available": False, "reason": "sample too small", "composites": []},
        )

        self.assertFalse(warning["actionable"])
        self.assertEqual(warning["scoreUse"], "research_only")
        self.assertIsNone(warning["allocation"]["exposureBandPct"])
        self.assertEqual(warning["contextAllocation"]["exposureBandPct"], [50, 75])
        self.assertFalse(warning["predictiveValidity"]["actionable"])
        self.assertIn("缺少", warning["predictiveValidity"]["reason"])
        self.assertEqual(warning["contextSummary"], original_summary)
        self.assertIn("仅作研究背景", warning["summary"])
        self.assertIn("不依据该信号调整权益仓位", warning["summary"])
        self.assertNotIn("进入减仓预警", warning["summary"])
        self.assertNotIn("新增仓位放慢", warning["summary"])

    def test_non_actionable_spy_warning_keeps_band_only_as_context(self) -> None:
        warning = {
            "score": 62.0,
            "regime": "Caution",
            "regimeCn": "谨慎",
            "allocation": {
                "horizon": "1-3M",
                "horizonCn": "1-3个月",
                "regime": "Caution",
                "regimeCn": "谨慎",
                "stance": "降权/对冲",
                "equityExposure": "权益维持常规仓位的50-75%",
                "exposureBandPct": [50, 75],
                "hedgeAction": "新增仓位放慢",
            },
        }
        validation = {
            "independentHoldout": False,
            "composites": [
                {
                    "id": "spyEarlyWarning",
                    "robust": False,
                    "actionableRobust": False,
                    "oosIc3m": 0.32,
                    "oosCi3m": [-0.01, 0.53],
                    "fdrSignificant3m": False,
                    "foldStability3m": {"stablePositive": True},
                }
            ],
        }

        annotate_spy_warning_robustness(warning, validation)

        self.assertEqual(warning["contextAllocation"]["exposureBandPct"], [50, 75])
        self.assertIsNone(warning["allocation"]["exposureBandPct"])
        self.assertFalse(warning["allocation"]["actionable"])
        self.assertEqual(warning["predictiveValidity"]["status"], "research-context")
        self.assertFalse(warning["predictiveValidity"]["independentHoldout"])

    def test_actionable_spy_warning_keeps_production_band(self) -> None:
        warning = {
            "rulesVersion": SPY_WARNING_RULES_VERSION,
            "allocation": {"exposureBandPct": [50, 75]},
        }
        validation = {
            "independentHoldout": True,
            "spyEarlyWarningRulesVersion": SPY_WARNING_RULES_VERSION,
            "composites": [
                {
                    "id": "spyEarlyWarning",
                    "rulesVersion": SPY_WARNING_RULES_VERSION,
                    "robust": True,
                    "actionableRobust": True,
                    "oosIc3m": 0.4,
                    "oosCi3m": [0.1, 0.6],
                    "fdrSignificant3m": True,
                    "foldStability3m": {"stablePositive": True},
                }
            ],
        }

        annotate_spy_warning_robustness(warning, validation)

        self.assertEqual(warning["allocation"]["exposureBandPct"], [50, 75])
        self.assertTrue(warning["allocation"]["actionable"])
        self.assertEqual(warning["predictiveValidity"]["status"], "actionable")
        self.assertTrue(warning["predictiveValidity"]["rulesVersionAudit"]["matched"])

    def test_old_unversioned_validation_cannot_promote_current_rules(self) -> None:
        warning = {
            "rulesVersion": SPY_WARNING_RULES_VERSION,
            "allocation": {"exposureBandPct": [50, 75]},
        }
        validation = {
            "independentHoldout": True,
            "composites": [
                {
                    "id": "spyEarlyWarning",
                    "robust": True,
                    "actionableRobust": True,
                    "oosCi3m": [0.1, 0.6],
                }
            ],
        }

        annotate_spy_warning_robustness(warning, validation)

        self.assertFalse(warning["actionable"])
        self.assertIsNone(warning["allocation"]["exposureBandPct"])
        self.assertEqual(warning["contextAllocation"]["exposureBandPct"], [50, 75])
        audit = warning["predictiveValidity"]["rulesVersionAudit"]
        self.assertFalse(audit["complete"])
        self.assertFalse(audit["matched"])
        self.assertIn("版本审计不完整", warning["predictiveValidity"]["reason"])

    def test_mismatched_validation_version_cannot_promote_current_rules(self) -> None:
        warning = {
            "rulesVersion": SPY_WARNING_RULES_VERSION,
            "allocation": {"exposureBandPct": [50, 75]},
        }
        validation = {
            "independentHoldout": True,
            "spyEarlyWarningRulesVersion": "2026-06-19-v2",
            "composites": [
                {
                    "id": "spyEarlyWarning",
                    "rulesVersion": "2026-06-19-v2",
                    "robust": True,
                    "actionableRobust": True,
                    "oosCi3m": [0.1, 0.6],
                }
            ],
        }

        annotate_spy_warning_robustness(warning, validation)

        self.assertFalse(warning["aggregateActionableRobust"])
        self.assertFalse(warning["predictiveValidity"]["actionable"])
        audit = warning["predictiveValidity"]["rulesVersionAudit"]
        self.assertEqual(audit["expectedRulesVersion"], SPY_WARNING_RULES_VERSION)
        self.assertFalse(audit["matched"])
        self.assertIsNone(warning["allocation"]["exposureBandPct"])
        self.assertIn("版本不匹配", warning["predictiveValidity"]["reason"])

    def test_coherent_but_stale_version_cannot_pass_current_code_gate(self) -> None:
        stale_version = "2026-06-19-v2"
        warning = {
            "rulesVersion": stale_version,
            "allocation": {"exposureBandPct": [50, 75]},
        }
        validation = {
            "independentHoldout": True,
            "spyEarlyWarningRulesVersion": stale_version,
            "composites": [
                {
                    "id": "spyEarlyWarning",
                    "rulesVersion": stale_version,
                    "robust": True,
                    "actionableRobust": True,
                    "oosCi3m": [0.1, 0.6],
                }
            ],
        }

        annotate_spy_warning_robustness(warning, validation)

        audit = warning["predictiveValidity"]["rulesVersionAudit"]
        self.assertTrue(audit["complete"])
        self.assertFalse(audit["matched"])
        self.assertEqual(audit["expectedRulesVersion"], SPY_WARNING_RULES_VERSION)
        self.assertFalse(warning["actionable"])

    def test_repeated_fail_closed_bind_preserves_band_for_later_valid_version(self) -> None:
        original_summary = "SPY预警62.0,进入减仓预警: 新增仓位放慢,维持核心仓位。"
        warning = {
            "rulesVersion": SPY_WARNING_RULES_VERSION,
            "summary": original_summary,
            "allocation": {"exposureBandPct": [50, 75]},
        }
        stale_validation = {
            "independentHoldout": True,
            "spyEarlyWarningRulesVersion": "2026-06-19-v2",
            "composites": [{
                "id": "spyEarlyWarning",
                "rulesVersion": "2026-06-19-v2",
                "robust": True,
                "actionableRobust": True,
            }],
        }
        current_validation = {
            "independentHoldout": True,
            "spyEarlyWarningRulesVersion": SPY_WARNING_RULES_VERSION,
            "composites": [{
                "id": "spyEarlyWarning",
                "rulesVersion": SPY_WARNING_RULES_VERSION,
                "robust": True,
                "actionableRobust": True,
            }],
        }

        annotate_spy_warning_robustness(warning, stale_validation)
        annotate_spy_warning_robustness(warning, stale_validation)
        self.assertEqual(warning["contextAllocation"]["exposureBandPct"], [50, 75])
        self.assertEqual(warning["contextSummary"], original_summary)
        self.assertNotEqual(warning["summary"], original_summary)

        annotate_spy_warning_robustness(warning, current_validation)

        self.assertTrue(warning["actionable"])
        self.assertEqual(warning["allocation"]["exposureBandPct"], [50, 75])
        self.assertTrue(warning["allocation"]["actionable"])
        self.assertEqual(warning["summary"], original_summary)

    def test_none_validation_fails_closed(self) -> None:
        warning = {
            "rulesVersion": SPY_WARNING_RULES_VERSION,
            "allocation": {"exposureBandPct": [50, 75]},
        }

        annotate_spy_warning_robustness(warning, None)

        self.assertFalse(warning["actionable"])
        self.assertIsNone(warning["allocation"]["exposureBandPct"])
        self.assertFalse(warning["predictiveValidity"]["rulesVersionAudit"]["complete"])

    def test_statistical_gate_without_independent_holdout_stays_research_only(self) -> None:
        warning = {"allocation": {"exposureBandPct": [50, 75]}}
        validation = {
            "independentHoldout": False,
            "composites": [
                {
                    "id": "spyEarlyWarning",
                    "robust": True,
                    "actionableRobust": True,
                    "oosIc3m": 0.4,
                    "oosCi3m": [0.1, 0.6],
                    "fdrSignificant3m": True,
                    "foldStability3m": {"stablePositive": True},
                },
                {
                    "id": "sleeve:fundingStress",
                    "robust": True,
                    "actionableRobust": True,
                    "oosIc3m": 0.35,
                },
            ],
        }

        annotate_spy_warning_robustness(warning, validation)

        self.assertFalse(warning["aggregateRobust"])
        self.assertTrue(warning["aggregateStatisticalGatePassed"])
        self.assertFalse(warning["predictiveValidity"]["actionable"])
        self.assertIsNone(warning["allocation"]["exposureBandPct"])
        self.assertEqual(warning["robustSleeves"], [])
        self.assertEqual(warning["researchRobustSleeves"], ["fundingStress"])
        self.assertEqual(warning["exploratorySleeves"], ["fundingStress"])


if __name__ == "__main__":
    unittest.main()
