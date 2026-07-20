from __future__ import annotations

import unittest

from treasury_data.advice import (
    build_portfolio_overview,
    global_lppl_overview_evidence,
)
from treasury_data.investment_views import build_ideas
from treasury_data.scoring_lppl import GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID


def idea_indicators() -> dict:
    return {
        "cpi_yoy": 3.2,
        "pce_yoy": 2.8,
        "core_pce_yoy": 2.8,
        "trimmed_mean_pce_yoy": 2.7,
        "ppi_yoy": 3.1,
        "two_year_m1_change_bp": 15.0,
        "s5s30": 80.0,
        "two_year": 4.13,
        "sofr": 3.51,
        "dff": 3.62,
        "breakeven_10y": 2.40,
        "wti": 112.25,
        "wti_shock": 0.18,
    }


def equity_panel(score: float) -> dict:
    triggered = score >= 75
    production_test = {
        "threshold": 75,
        "rule": "score >= 75",
        "productionUse": True,
        "oosValidated": True,
        "precision": 70.6,
        "baseRate": 50.5,
        "liftVsBaseRate": 1.4,
        "recall": 12.0,
        "sampleSize": 198,
        "alertDays": 17,
        "avgDrawdownLeadDaysWhenHit": 4.8,
    }
    return {
        "available": True,
        "score": score,
        "actionable": triggered,
        "scoreScale": {"coreComplete": True, "thresholdComparable": True},
        "asOf": "2026-07-16",
        "allocation": {
            "horizon": "1-10d",
            "horizonCn": "1-10个交易日",
            "regime": "Strong Alert" if score >= 75 else "Normal",
            "regimeCn": "强告警" if score >= 75 else "正常",
            "hedgeAction": "短线降风险",
            "exposureBandPct": [50, 80] if triggered else None,
            "actionable": triggered,
        },
        "contextAllocation": None if triggered else {
            "horizon": "1-10d",
            "horizonCn": "1-10个交易日",
            "regime": "Normal",
            "regimeCn": "正常",
            "hedgeAction": "短线降风险",
            "exposureBandPct": [50, 80],
            "actionable": True,
        },
        "productionValidation": {
            "available": True,
            "scoreContractAllowsAction": True,
            "thresholdValidated": True,
            "currentTriggered": triggered,
            "actionable": triggered,
        },
        "backtest": {
            "walkForward": {
                "available": True,
                "thresholdTests": [production_test],
                "outOfSample": {
                    "sampleSize": 198,
                    "selectedThresholdTest": production_test,
                },
            }
        },
    }


def spy_panel() -> dict:
    return {
        "available": True,
        "score": 45.0,
        "regime": "Neutral",
        "regimeCn": "中性",
        "asOf": "2026-07-16",
        "allocation": {
            "horizon": "1-3M",
            "horizonCn": "1-3个月",
            "hedgeAction": "维持核心仓位",
            "exposureBandPct": [75, 100],
        },
    }


def spy_validation() -> dict:
    return {
        "available": True,
        "composites": [
            {
                "id": "spyEarlyWarning",
                "actionableRobust": True,
                "hitRateOos": 0.4,
                "baseRate": 0.3,
                "lift": 1.33,
                "leadTimeDays": 40.0,
                "observationCount": 260,
            }
        ],
    }


class InvestmentViewEvidenceContractTests(unittest.TestCase):
    def test_source_quality_cannot_promote_unvalidated_trade_confidence(self) -> None:
        ideas = build_ideas(
            idea_indicators(),
            macro_liquidity={"score": 55.0, "reliabilityScore": 58.0, "regime": "Neutral"},
            conclusion_audit={
                "confidence": {
                    "level": "high",
                    "evidenceQuality": 0.95,
                    "proxyContributionShare": 0.05,
                    "concentration": 0.20,
                },
                "weightRecommendation": "输入来源完整。",
            },
        )

        self.assertEqual(len(ideas), 4)
        proxies = {idea["tradeEvidence"]["proxy"] for idea in ideas}
        self.assertEqual(len(proxies), 4)
        self.assertTrue(all("spy" not in proxy.lower() for proxy in proxies))
        for idea in ideas:
            self.assertEqual(idea["dataQuality"]["level"], "high")
            self.assertFalse(idea["dataQuality"]["isPredictiveConfidence"])
            self.assertEqual(idea["confidenceLevel"], "low")
            self.assertEqual(idea["confidenceLabel"], "低可信")
            self.assertEqual(idea["validationStatus"], "research-background")
            self.assertFalse(idea["predictiveValidity"]["actionable"])
            self.assertEqual(idea["tradeEvidence"]["validationStatus"], "research-background")
            self.assertFalse(idea["tradeEvidence"]["actionable"])
            self.assertEqual(idea["marketContext"]["role"], "descriptive-market-context")
            self.assertEqual(idea["marketContext"]["scope"], "SPY-only")
            self.assertFalse(idea["marketContext"]["supportsTradeEvidence"])
            self.assertEqual(idea["equityImpact"], idea["marketContext"])


class PortfolioEvidenceContractTests(unittest.TestCase):
    def build_equity_overview(self, score: float) -> dict:
        return build_portfolio_overview(
            spy_early_warning=spy_panel(),
            equity_short_term_risk=equity_panel(score),
            global_lppl_risk=None,
            macro_liquidity=None,
            signal_validation=spy_validation(),
        )

    def test_equity_uses_dedicated_oos_and_binds_only_when_triggered(self) -> None:
        active = self.build_equity_overview(80.0)
        layer = next(
            row for row in active["layers"] if row["layer"] == "equityShortTermRisk"
        )
        self.assertEqual(
            layer["evidence"]["validationPath"],
            "equityShortTermRisk.backtest.walkForward",
        )
        self.assertEqual(
            layer["validationStatus"], "dedicated-oos-validated-threshold"
        )
        self.assertTrue(layer["evidence"]["currentTriggered"])
        self.assertTrue(layer["actionable"])
        self.assertEqual(layer["exposureBandPct"], [50.0, 80.0])

        inactive = self.build_equity_overview(50.0)
        layer = next(
            row for row in inactive["layers"] if row["layer"] == "equityShortTermRisk"
        )
        self.assertEqual(
            layer["validationStatus"], "dedicated-oos-validated-threshold"
        )
        self.assertFalse(layer["evidence"]["currentTriggered"])
        self.assertFalse(layer["actionable"])
        self.assertEqual(layer["confidenceTier"], "validated-context")
        self.assertIsNone(layer["exposureBandPct"])
        self.assertEqual(layer["contextBand"], [50.0, 80.0])

    def test_incomplete_equity_score_contract_cannot_bind_even_above_threshold(self) -> None:
        panel = equity_panel(80.0)
        panel["actionable"] = False
        panel["scoreScale"] = {"coreComplete": False, "thresholdComparable": False}
        panel["allocation"]["actionable"] = False

        overview = build_portfolio_overview(
            spy_early_warning=spy_panel(),
            equity_short_term_risk=panel,
            global_lppl_risk=None,
            macro_liquidity=None,
            signal_validation=spy_validation(),
        )
        layer = next(
            row for row in overview["layers"] if row["layer"] == "equityShortTermRisk"
        )

        self.assertTrue(layer["evidence"]["predictiveValidity"]["thresholdValidated"])
        self.assertFalse(layer["evidence"]["scoreContractAllowsAction"])
        self.assertFalse(layer["actionable"])
        self.assertIsNone(layer["exposureBandPct"])

    def test_lppl_uses_only_active_indices_own_market_evidence(self) -> None:
        lppl = {
            "indices": [
                {
                    "available": True,
                    "symbol": "SPY",
                    "sourceSymbol": "SPY",
                    "status": "quiet",
                    "score": 30.0,
                },
                {
                    "available": True,
                    "symbol": "KOSPI",
                    "sourceSymbol": "EWY",
                    "status": "risk",
                    "score": 78.0,
                    "daysToCritical": 25,
                    "productionEligible": False,
                    "actionable": False,
                },
                {
                    "available": True,
                    "symbol": "TWII",
                    "sourceSymbol": "EWT",
                    "status": "risk",
                    "score": 73.0,
                    "daysToCritical": 22,
                    "productionEligible": False,
                    "actionable": False,
                },
            ],
            "indexValidation": {
                "rows": [
                    {
                        "symbol": "SPY",
                        "sourceSymbol": "SPY",
                        "oosAvailable": True,
                        "productionEvidenceAvailable": True,
                        "productionThreshold": 55,
                        "productionEffectiveWeightMultiplier": 1.0,
                        "productionValidationRole": "validated",
                        "precision15dOos": 95.0,
                        "baseRate15dOos": 20.0,
                        "oosSampleSize": 999,
                        "oosAlertDays": 100,
                    },
                    {
                        "symbol": "KOSPI",
                        "sourceSymbol": "EWY",
                        "oosAvailable": True,
                        "productionEvidenceAvailable": True,
                        "productionActionable": False,
                        "productionThreshold": 70,
                        "productionEffectiveWeightMultiplier": 0.85,
                        "productionValidationRole": "mixed",
                        "precision15dOos": 72.8,
                        "baseRate15dOos": 62.6,
                        "oosSampleSize": 219,
                        "oosAlertDays": 125,
                    },
                    {
                        "symbol": "TWII",
                        "sourceSymbol": "EWT",
                        "oosAvailable": True,
                        "productionEvidenceAvailable": True,
                        "productionActionable": False,
                        "productionThreshold": 65,
                        "productionEffectiveWeightMultiplier": 0.6,
                        "productionValidationRole": "weak",
                        "precision15dOos": 64.1,
                        "baseRate15dOos": 62.1,
                        "oosSampleSize": 219,
                        "oosAlertDays": 78,
                    },
                ]
            },
        }

        evidence = global_lppl_overview_evidence(lppl)
        self.assertTrue(evidence["available"])
        self.assertEqual(evidence["scope"], "per-index-own-market")
        self.assertEqual(evidence["symbols"], ["KOSPI", "TWII"])
        self.assertEqual(evidence["validationStatus"], "mixed-own-market")
        self.assertFalse(evidence["predictiveValidity"]["actionable"])
        by_symbol = {row["symbol"]: row for row in evidence["perIndex"]}
        self.assertNotIn("SPY", by_symbol)
        self.assertAlmostEqual(by_symbol["KOSPI"]["oosHitRate"], 0.728)
        self.assertAlmostEqual(by_symbol["TWII"]["oosHitRate"], 0.641)
        self.assertEqual(by_symbol["KOSPI"]["sourceSymbol"], "EWY")
        self.assertEqual(by_symbol["TWII"]["sourceSymbol"], "EWT")

        overview = build_portfolio_overview(
            spy_early_warning=spy_panel(),
            equity_short_term_risk=None,
            global_lppl_risk=lppl,
            macro_liquidity={"score": 50.0, "regime": "Neutral"},
            signal_validation={"available": True, "composites": []},
        )
        lppl_layer = next(
            row for row in overview["layers"] if row["layer"] == "globalLppl"
        )
        self.assertNotEqual(lppl_layer["confidenceTier"], "unverified")
        self.assertFalse(lppl_layer["actionable"])
        self.assertIsNone(lppl_layer["exposureBandPct"])
        self.assertEqual(lppl_layer["contextBand"], [60.0, 85.0])

    def test_validated_non_us_lppl_stays_regional_context(self) -> None:
        model_id = GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
        validation = {
            "symbol": "KOSPI",
            "sourceSymbol": "EWY",
            "oosAvailable": True,
            "oosSampleSize": 40,
            "oosAlertDays": 10,
            "oosThreshold": 70,
            "oosTest15d": {
                "threshold": 70,
                "sampleSize": 40,
                "alertDays": 10,
                "precision": 80.0,
                "baseRate": 20.0,
                "independentSampleSize": 20,
                "independentAlertCount": 6,
                "independentAlertHits": 5,
                "independentPrecision": 83.3,
                "independentBaseRate": 20.0,
                "precisionLowerBound90Pct": 60.0,
                "multipleTestingPass": True,
            },
            "replayModelAudit": {
                "required": True,
                "productionModelSpecId": model_id,
                "liveModelSpecId": model_id,
                "liveModelMetadataAvailable": True,
                "liveValidationComparable": True,
                "liveComparable": True,
                "observedModelSpecIds": [model_id],
                "observationCount": 40,
                "comparableObservationCount": 40,
                "unknownModelSpecCount": 0,
                "mismatchedModelSpecCount": 0,
                "replayComparable": True,
                "comparable": True,
                "enforcementPass": True,
                "status": "comparable",
            },
            "productionEvidenceAvailable": True,
            "productionActionable": True,
            "productionThreshold": 70,
            "productionThresholdSource": "purged_calibration_first_65pct",
            "productionEffectiveWeightMultiplier": 1.0,
            "productionWeightSource": "untouched_oos_last_35pct",
            "productionWeightMethod": (
                "non_overlapping_alerts_wilson90_exact_binomial_bonferroni6"
            ),
            "productionValidationRole": "validated",
            "precision15dOos": 80.0,
            "baseRate15dOos": 20.0,
        }
        lppl = {
            "indices": [
                {
                    "available": True,
                    "symbol": "KOSPI",
                    "sourceSymbol": "EWY",
                    "status": "risk",
                    "score": 78.0,
                    "fitProductionEligible": True,
                    "productionEligible": True,
                    "actionable": True,
                    "scoreUse": "production_signal",
                    "actionabilityStatus": "current_threshold_triggered",
                    "modelSpecId": model_id,
                    "validationComparableToProduction": True,
                    "validation": validation,
                }
            ],
            "indexValidation": {
                "rows": [validation]
            },
        }

        evidence = global_lppl_overview_evidence(lppl)
        self.assertEqual(
            evidence["validationStatus"],
            "validated-own-market-regional-context",
        )
        self.assertTrue(evidence["predictiveValidity"]["thresholdValidated"])
        self.assertTrue(evidence["predictiveValidity"]["currentTriggered"])
        self.assertFalse(evidence["predictiveValidity"]["portfolioScopeMatched"])
        self.assertFalse(evidence["predictiveValidity"]["actionable"])


if __name__ == "__main__":
    unittest.main()
