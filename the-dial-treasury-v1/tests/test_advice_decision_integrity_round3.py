from __future__ import annotations

import copy
import unittest

from treasury_data.advice import (
    build_portfolio_overview,
    global_lppl_overview_evidence,
    global_lppl_portfolio_action_qualifies,
    portfolio_overview_regional_tilt,
)
from treasury_data.investment_views import build_ideas
from treasury_data.scoring_lppl import GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID


def _indicators(**overrides: float) -> dict:
    values = {
        "cpi_yoy": 3.2,
        "pce_yoy": 2.8,
        "core_pce_yoy": 2.8,
        "trimmed_mean_pce_yoy": 2.7,
        "ppi_yoy": 3.1,
        "two_year_m1_change_bp": 10.0,
        "s5s30": 80.0,
        "two_year": 4.13,
        "sofr": 3.51,
        "dff": 3.62,
        "breakeven_10y": 2.40,
        "wti": 82.0,
        "wti_shock": 0.12,
    }
    values.update(overrides)
    return values


def _canonical_equity_panel(score: float = 80.0) -> dict:
    triggered = score >= 75.0
    production_test = {
        "threshold": 75,
        "productionUse": True,
        "oosValidated": True,
        "precision": 70.6,
        "baseRate": 50.5,
        "liftVsBaseRate": 1.4,
        "sampleSize": 198,
        "alertDays": 17,
    }
    context = {
        "horizon": "1-10d",
        "regime": "Strong Alert" if triggered else "Normal",
        "regimeCn": "强告警" if triggered else "正常",
        "hedgeAction": "短线降风险" if triggered else "无需额外对冲",
        "exposureBandPct": [50, 80] if triggered else [100, 100],
        "actionable": True,
    }
    return {
        "available": True,
        "score": score,
        "actionable": triggered,
        "scoreScale": {"coreComplete": True, "thresholdComparable": True},
        "allocation": (
            {**context, "actionable": True}
            if triggered
            else {**context, "exposureBandPct": None, "actionable": False}
        ),
        "contextAllocation": None if triggered else context,
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
                "outOfSample": {"sampleSize": 198},
            }
        },
    }


def _complete_lppl_validation(symbol: str = "SPY") -> dict:
    model_id = GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID
    return {
        "symbol": symbol,
        "sourceSymbol": symbol,
        "oosAvailable": True,
        "oosSampleSize": 40,
        "oosAlertDays": 10,
        "oosThreshold": 65,
        "oosTest15d": {
            "threshold": 65,
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
        "productionThreshold": 65,
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


def _complete_lppl_panel(symbol: str = "SPY") -> dict:
    validation = _complete_lppl_validation(symbol)
    row = {
        "available": True,
        "symbol": symbol,
        "sourceSymbol": symbol,
        "status": "risk",
        "score": 80.0,
        "fitProductionEligible": True,
        "productionEligible": True,
        "actionable": True,
        "scoreUse": "production_signal",
        "actionabilityStatus": "current_threshold_triggered",
        "modelSpecId": GLOBAL_LPPL_PRODUCTION_MODEL_SPEC_ID,
        "validationComparableToProduction": True,
        "validation": copy.deepcopy(validation),
    }
    return {
        "indices": [row],
        "indexValidation": {"available": True, "rows": [validation]},
    }


class AdviceDecisionIntegrityRound3Tests(unittest.TestCase):
    def test_generic_spy_statistics_cannot_replace_surface_production_contract(self) -> None:
        overview = build_portfolio_overview(
            spy_early_warning={
                "available": True,
                "score": 70.0,
                "allocation": {
                    "exposureBandPct": [50, 75],
                    "hedgeAction": "降低风险仓位",
                },
            },
            equity_short_term_risk=None,
            global_lppl_risk=None,
            macro_liquidity={"score": 55.0},
            signal_validation={
                "available": True,
                "composites": [
                    {
                        "id": "spyEarlyWarning",
                        "actionableRobust": True,
                        "hitRateOos": 0.6,
                        "baseRate": 0.4,
                    }
                ],
            },
        )

        layer = next(row for row in overview["layers"] if row["layer"] == "spyEarlyWarning")
        self.assertFalse(layer["actionable"])
        self.assertIsNone(layer["exposureBandPct"])
        self.assertEqual(layer["contextBand"], [50.0, 75.0])
        self.assertEqual(layer["contextStance"], "降低风险仓位")
        self.assertEqual(overview["conflicts"], [])

    def test_legacy_equity_payload_cannot_reconstruct_production_action(self) -> None:
        legacy = _canonical_equity_panel()
        for field in ("actionable", "scoreScale", "productionValidation"):
            legacy.pop(field)
        legacy["allocation"].pop("actionable")

        overview = build_portfolio_overview(
            spy_early_warning=None,
            equity_short_term_risk=legacy,
            global_lppl_risk=None,
            macro_liquidity={"score": 55.0},
            signal_validation=None,
        )

        layer = next(row for row in overview["layers"] if row["layer"] == "equityShortTermRisk")
        self.assertFalse(layer["actionable"])
        self.assertIsNone(layer["exposureBandPct"])
        self.assertEqual(layer["contextBand"], [50.0, 80.0])
        self.assertEqual(layer["stance"], "研究背景，仅供观察，不作为组合动作")
        self.assertEqual(layer["contextStance"], "短线降风险")

    def test_canonical_equity_action_binds_only_while_current_threshold_is_triggered(self) -> None:
        active = build_portfolio_overview(
            spy_early_warning=None,
            equity_short_term_risk=_canonical_equity_panel(80.0),
            global_lppl_risk=None,
            macro_liquidity={"score": 55.0},
            signal_validation=None,
        )
        active_layer = next(row for row in active["layers"] if row["layer"] == "equityShortTermRisk")
        self.assertTrue(active_layer["actionable"])
        self.assertEqual(active_layer["exposureBandPct"], [50.0, 80.0])

        inactive = build_portfolio_overview(
            spy_early_warning=None,
            equity_short_term_risk=_canonical_equity_panel(50.0),
            global_lppl_risk=None,
            macro_liquidity={"score": 55.0},
            signal_validation=None,
        )
        inactive_layer = next(row for row in inactive["layers"] if row["layer"] == "equityShortTermRisk")
        self.assertFalse(inactive_layer["actionable"])
        self.assertEqual(inactive_layer["contextBand"], [100.0, 100.0])

    def test_lppl_validation_cannot_override_current_fit_eligibility(self) -> None:
        panel = {
            "indices": [
                {
                    "available": True,
                    "symbol": "SPY",
                    "status": "risk",
                    "score": 80.0,
                    "productionEligible": False,
                    "actionable": False,
                }
            ],
            "indexValidation": {
                "rows": [
                    {
                        "symbol": "SPY",
                        "oosAvailable": True,
                        "productionEvidenceAvailable": True,
                        "productionActionable": True,
                        "productionThreshold": 70,
                        "productionEffectiveWeightMultiplier": 1.0,
                        "productionValidationRole": "validated",
                    }
                ]
            },
        }

        evidence = global_lppl_overview_evidence(panel)
        self.assertFalse(evidence["predictiveValidity"]["thresholdValidated"])
        self.assertFalse(evidence["predictiveValidity"]["actionable"])

    def test_complete_lppl_replay_and_episode_contract_can_bind_us_band(self) -> None:
        panel = _complete_lppl_panel()

        evidence = global_lppl_overview_evidence(panel)
        overview = build_portfolio_overview(
            spy_early_warning=None,
            equity_short_term_risk=None,
            global_lppl_risk=panel,
            macro_liquidity={"score": 55.0},
            signal_validation=None,
        )

        self.assertTrue(
            global_lppl_portfolio_action_qualifies(
                panel["indices"][0],
                panel["indexValidation"]["rows"][0],
            )
        )
        self.assertTrue(evidence["predictiveValidity"]["actionable"])
        self.assertEqual(overview["suggestedEquityExposureBand"], [60.0, 85.0])

    def test_lppl_summary_booleans_cannot_bypass_replay_oos_contract(self) -> None:
        cases = []

        missing_model_audit = _complete_lppl_panel()
        missing_model_audit["indices"][0]["validation"].pop("replayModelAudit")
        cases.append(("missing replay model audit", missing_model_audit))

        zero_oos_sample = _complete_lppl_panel()
        for validation in (
            zero_oos_sample["indices"][0]["validation"],
            zero_oos_sample["indexValidation"]["rows"][0],
        ):
            validation["oosSampleSize"] = 0
            validation["oosTest15d"]["sampleSize"] = 0
        cases.append(("zero OOS sample", zero_oos_sample))

        too_few_episodes = _complete_lppl_panel()
        for validation in (
            too_few_episodes["indices"][0]["validation"],
            too_few_episodes["indexValidation"]["rows"][0],
        ):
            validation["oosTest15d"]["independentAlertCount"] = 1
        cases.append(("too few independent episodes", too_few_episodes))

        mismatched_threshold = _complete_lppl_panel()
        mismatched_threshold["indices"][0]["validation"]["productionThreshold"] = 70
        mismatched_threshold["indexValidation"]["rows"][0]["productionThreshold"] = 70
        cases.append(("threshold mismatch", mismatched_threshold))

        stale_current_score = _complete_lppl_panel()
        stale_current_score["indices"][0]["score"] = 50.0
        cases.append(("current threshold not triggered", stale_current_score))

        for label, panel in cases:
            with self.subTest(label=label):
                evidence = global_lppl_overview_evidence(panel)
                self.assertFalse(evidence["predictiveValidity"]["actionable"])
                self.assertFalse(evidence["perIndex"][0]["actionable"])

    def test_research_regional_rotation_and_breach_remain_context(self) -> None:
        monitor = {
            "available": True,
            "rotation": {"available": True, "favorRegions": ["japan"]},
            "regions": [
                {
                    "key": "japan",
                    "nameCn": "日本",
                    "allocation": {"actionable": False},
                    "factorAlert": {
                        "available": True,
                        "state": "breached",
                        "source": "factor",
                        "factorId": "realizedVol",
                        "factorLabelCn": "已实现波动",
                    },
                }
            ],
        }

        tilt = portfolio_overview_regional_tilt(monitor)
        self.assertFalse(tilt["actionable"])
        self.assertEqual(tilt["favorRegions"], [])
        self.assertEqual(tilt["contextFavorRegions"], ["japan"])
        self.assertEqual(tilt["breachedRegions"], [])
        self.assertEqual([row["key"] for row in tilt["contextBreachedRegions"]], ["japan"])
        self.assertIn("不进入组合动作", tilt["summary"])

    def test_research_trade_ideas_expose_no_execution_direction_or_sizing(self) -> None:
        ideas = build_ideas(_indicators(), macro_liquidity={"score": 55.0})

        self.assertEqual(len(ideas), 4)
        for idea in ideas:
            self.assertFalse(idea["actionable"])
            self.assertEqual(idea["decisionStatus"], "research-only")
            self.assertEqual(idea["direction"], "研究背景 · 不执行")
            self.assertEqual(idea["sizing"], "不建仓 · 仅作研究背景")
            self.assertTrue(idea["trigger"].startswith("研究观察条件："))
            self.assertTrue(idea["invalidation"].startswith("研究假设失效："))

    def test_deeply_priced_two_year_is_not_called_long_carry_when_move_is_flat(self) -> None:
        ideas = build_ideas(
            _indicators(two_year=3.10, dff=4.20, sofr=4.10, two_year_m1_change_bp=5.0),
            macro_liquidity={"score": 55.0},
        )

        self.assertEqual(ideas[2]["tag"], "FRONT-END 谨慎")
        self.assertNotEqual(ideas[2]["contextDirection"], "LONG 前端")

    def test_explicit_unavailability_does_not_reenable_placeholder_inputs(self) -> None:
        indicators = _indicators()
        indicators["availability"] = {
            "dff": True,
            "sofr": True,
            "cpi_yoy": False,
            "pce_yoy": False,
            "core_pce_yoy": False,
            "trimmed_mean_pce_yoy": False,
            "ppi_yoy": False,
            "breakeven_10y": False,
        }
        indicators["percentile_series"] = {}

        ideas = build_ideas(indicators, macro_liquidity={"score": 55.0})

        self.assertIn("数据不完整", ideas[0]["text"])
        self.assertEqual(ideas[3]["tag"], "RV 数据不足")


if __name__ == "__main__":
    unittest.main()
