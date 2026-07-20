from __future__ import annotations

import copy
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from scripts import update_equity_risk
from treasury_data.build_dashboard import EQUITY_RISK_SYMBOLS
from treasury_data.dashboard_contract import (
    CURRENT_SCHEMA_VERSION,
    dashboard_contract_issues,
)
from treasury_data.sources import MarketDailyBar
from treasury_data.scoring_equity import (
    EQUITY_RISK_REPLAY_SCORED_COMPONENTS,
    EQUITY_RISK_SCORE_SCALE_ID,
    EQUITY_RISK_V2_CANONICAL_NORMALIZED_WEIGHTS,
)


def market_bar(symbol: str, day: date = date(2026, 7, 17)) -> MarketDailyBar:
    return MarketDailyBar(
        symbol=symbol,
        date=day,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1_000_000,
        source="unit-test",
    )


def complete_equity_bars() -> dict[str, list[MarketDailyBar]]:
    return {symbol: [market_bar(symbol)] for symbol in EQUITY_RISK_SYMBOLS}


def legacy_equity_root() -> dict:
    return {
        "available": True,
        "asOf": "2026-07-17",
        "score": 39.7,
        "regime": "Normal",
        "regimeCn": "正常",
        "allocation": {
            "horizon": "1-10d",
            "horizonCn": "1-10个交易日",
            "regime": "Normal",
            "regimeCn": "正常",
            "stance": "风险可承受",
            "equityExposure": "维持计划仓位",
            "exposureBandPct": [100, 100],
            "hedgeAction": "无需额外对冲",
        },
        "backtest": {
            "walkForward": {
                "thresholdTests": [
                    {
                        "threshold": 75,
                        "productionUse": True,
                        # A legacy row has no explicit OOS validation verdict.
                        "precision": 68.8,
                        "baseRate": 51.0,
                    }
                ]
            }
        },
    }


def current_equity_root(*, validated: bool = True, score: float = 80.0) -> dict:
    scored_components = sorted(EQUITY_RISK_REPLAY_SCORED_COMPONENTS)
    normalized_weights = dict(EQUITY_RISK_V2_CANONICAL_NORMALIZED_WEIGHTS)
    allocation = {
        "horizon": "1-10d",
        "horizonCn": "1-10个交易日",
        "regime": "Strong Alert",
        "regimeCn": "强告警",
        "stance": "短线降风险",
        "equityExposure": "降低高Beta仓位",
        "exposureBandPct": [50, 80],
        "hedgeAction": "减仓或对冲",
        "actionable": True,
    }
    return {
        "available": True,
        "asOf": "2026-07-17",
        "score": score,
        "actionable": True,
        "scoreScale": {
            "id": EQUITY_RISK_SCORE_SCALE_ID,
            "coreComplete": True,
            "thresholdComparable": True,
            "requiredScoredComponents": scored_components,
            "scoredComponents": scored_components,
            "canonicalNormalizedWeights": normalized_weights,
            "observedNormalizedWeights": normalized_weights,
            "weightMismatches": [],
            "weightsMatchCanonical": True,
        },
        "allocation": allocation,
        "backtest": {
            "scoreScale": {
                "id": EQUITY_RISK_SCORE_SCALE_ID,
                "requiredScoredComponents": scored_components,
                "canonicalNormalizedWeights": normalized_weights,
                "observedNormalizedWeights": normalized_weights,
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
                        "oosValidated": validated,
                        "validationStatus": "validated" if validated else "research-only",
                        "sampleRole": "walkForwardOos",
                        "sampleSize": 100,
                        "independentAlertClusters": 10,
                        "independentHitClusters": 10,
                        "precision": 100.0,
                        "clusterPrecision": 100.0,
                        "baseRate": 50.0,
                    }
                ]
            }
        },
    }


def dashboard_with_equity(equity: dict) -> dict:
    return {
        "schemaVersion": CURRENT_SCHEMA_VERSION,
        "asOf": "2026-07-17",
        "generatedAt": "2026-07-18T02:00:00+00:00",
        "sourceStatus": [],
        "equityShortTermRisk": equity,
    }


class EquityDecisionNormalizationTests(unittest.TestCase):
    def test_refresh_uses_scoring_module_scale_identifier(self) -> None:
        self.assertEqual(update_equity_risk.CURRENT_EQUITY_SCORE_SCALE_ID, EQUITY_RISK_SCORE_SCALE_ID)

    def test_legacy_numeric_band_is_rebound_fail_closed_without_inferred_true_fields(self) -> None:
        risk = legacy_equity_root()

        update_equity_risk.normalize_equity_decision_contract(risk)

        self.assertFalse(risk["actionable"])
        self.assertFalse(risk["scoreScale"]["coreComplete"])
        self.assertFalse(risk["scoreScale"]["thresholdComparable"])
        self.assertEqual(
            risk["scoreScale"]["id"],
            update_equity_risk.LEGACY_UNVERIFIED_EQUITY_SCORE_SCALE_ID,
        )
        self.assertFalse(risk["productionValidation"]["thresholdValidated"])
        self.assertFalse(risk["productionValidation"]["actionable"])
        self.assertFalse(risk["allocation"]["actionable"])
        self.assertIsNone(risk["allocation"]["exposureBandPct"])
        self.assertEqual(risk["contextAllocation"]["exposureBandPct"], [100, 100])
        self.assertNotIn("predictiveValidity", risk)
        self.assertTrue(update_equity_risk.equity_decision_contract_complete(risk))
        self.assertFalse(update_equity_risk.equity_decision_contract_current(risk))

    def test_current_scale_can_keep_band_only_after_validated_triggered_binding(self) -> None:
        risk = current_equity_root(validated=True, score=80.0)

        update_equity_risk.normalize_equity_decision_contract(risk)

        self.assertTrue(risk["actionable"])
        self.assertTrue(risk["productionValidation"]["thresholdValidated"])
        self.assertTrue(risk["productionValidation"]["currentTriggered"])
        self.assertTrue(risk["productionValidation"]["actionable"])
        self.assertEqual(risk["allocation"]["exposureBandPct"], [50, 80])
        self.assertTrue(update_equity_risk.equity_decision_contract_complete(risk))
        self.assertTrue(update_equity_risk.equity_decision_contract_current(risk))

    def test_v2_cache_contract_requires_complete_weight_audit(self) -> None:
        risk = current_equity_root(validated=True, score=80.0)
        update_equity_risk.normalize_equity_decision_contract(risk)
        self.assertTrue(update_equity_risk.equity_decision_contract_current(risk))

        missing_cases = [
            ("scoreScale", "weightsMatchCanonical"),
            ("scoreScale", "canonicalNormalizedWeights"),
            ("scoreScale", "observedNormalizedWeights"),
            ("scoreScale", "weightMismatches"),
            ("backtestScoreScale", "weightsMatchCanonical"),
            ("backtestScoreScale", "canonicalNormalizedWeights"),
            ("backtestScoreScale", "observedNormalizedWeights"),
            ("backtestScoreScale", "weightMismatchedObservationCount"),
            ("productionValidation", "scoreScaleMatchesBacktest"),
            ("productionValidation", "scoreWeightsMatchBacktest"),
        ]
        for section, field in missing_cases:
            with self.subTest(section=section, field=field):
                malformed = copy.deepcopy(risk)
                target = (
                    malformed["backtest"]["scoreScale"]
                    if section == "backtestScoreScale"
                    else malformed[section]
                )
                target.pop(field)
                self.assertFalse(update_equity_risk.equity_decision_contract_complete(malformed))
                self.assertFalse(update_equity_risk.equity_decision_contract_current(malformed))

    def test_v2_weight_drift_forces_refresh_instead_of_cache_hit(self) -> None:
        risk = current_equity_root(validated=True, score=80.0)
        update_equity_risk.normalize_equity_decision_contract(risk)
        dashboard = dashboard_with_equity(risk)
        cached_bars = {"SPY": [market_bar("SPY")]}

        with patch.object(update_equity_risk, "dashboard_covers_market_bars", return_value=True):
            self.assertTrue(
                update_equity_risk.equity_refresh_cache_hit_allowed(
                    dashboard,
                    complete_equity_bars(),
                    cached_bars,
                )
            )

            live_drift = copy.deepcopy(dashboard)
            live_drift["equityShortTermRisk"]["scoreScale"]["observedNormalizedWeights"]["sectorRotation"] += 0.01
            self.assertFalse(
                update_equity_risk.equity_refresh_cache_hit_allowed(
                    live_drift,
                    complete_equity_bars(),
                    cached_bars,
                )
            )

            backtest_drift = copy.deepcopy(dashboard)
            backtest_drift["equityShortTermRisk"]["backtest"]["scoreScale"]["observedNormalizedWeights"]["sectorRotation"] += 0.01
            self.assertFalse(
                update_equity_risk.equity_refresh_cache_hit_allowed(
                    backtest_drift,
                    complete_equity_bars(),
                    cached_bars,
                )
            )

            missing_audit = copy.deepcopy(dashboard)
            missing_audit["equityShortTermRisk"]["productionValidation"].pop("scoreWeightsMatchBacktest")
            self.assertFalse(
                update_equity_risk.equity_refresh_cache_hit_allowed(
                    missing_audit,
                    complete_equity_bars(),
                    cached_bars,
                )
            )

    def test_uniformly_stale_cache_forces_recompute_and_disables_action(self) -> None:
        risk = current_equity_root(validated=True, score=80.0)
        update_equity_risk.normalize_equity_decision_contract(risk)
        dashboard = {
            **dashboard_with_equity(risk),
            "events": [],
            "macroLiquidity": {},
            "macroLiquidityEquity": {},
            "signalValidation": {"available": False, "factors": [], "composites": []},
            "spyEarlyWarning": {},
        }
        bars = {
            symbol: [market_bar(symbol, date(2026, 7, 17))]
            for symbol in EQUITY_RISK_SYMBOLS
        }
        reference_time = datetime(2026, 7, 20, 20, 40, tzinfo=timezone.utc)

        self.assertFalse(
            update_equity_risk.equity_refresh_cache_hit_allowed(
                dashboard,
                bars,
                bars,
                reference_time=reference_time,
            )
        )

        with (
            patch.object(update_equity_risk, "build_equity_short_term_risk_index") as builder,
            patch.object(update_equity_risk, "build_global_lppl_risk_index", return_value={}),
            patch.object(update_equity_risk, "build_regional_monitor", return_value={}),
            patch.object(update_equity_risk, "build_equity_signal_validation_row", return_value=None),
            patch.object(update_equity_risk, "build_portfolio_overview", return_value={}),
        ):
            updated = update_equity_risk.build_updated_dashboard(
                dashboard,
                bars,
                generated_at=reference_time,
            )

        builder.assert_not_called()
        refreshed_risk = updated["equityShortTermRisk"]
        self.assertFalse(refreshed_risk["actionable"])
        self.assertIsNone(refreshed_risk["allocation"]["exposureBandPct"])
        self.assertFalse(refreshed_risk["productionValidation"]["refreshEligible"])
        refresh_meta = updated["meta"]["equityRefresh"]
        self.assertTrue(refresh_meta["marketDataAbsoluteStale"])
        self.assertEqual(refresh_meta["expectedEquityDate"], "2026-07-20")
        self.assertEqual(
            refresh_meta["absoluteStaleEquitySymbols"],
            sorted(EQUITY_RISK_SYMBOLS),
        )
        spy_row = next(
            row for row in updated["sourceStatus"]
            if row.get("name") == "Nasdaq SPY OHLCV"
        )
        self.assertEqual(spy_row["status"], "stale")
        self.assertTrue(spy_row["absoluteStale"])
        self.assertEqual(spy_row["expectedDate"], "2026-07-20")

    def test_legacy_contract_forces_recompute_even_when_market_cache_covers_dates(self) -> None:
        dashboard = dashboard_with_equity(legacy_equity_root())
        with patch.object(
            update_equity_risk,
            "dashboard_covers_market_bars",
            return_value=True,
        ):
            self.assertFalse(
                update_equity_risk.equity_refresh_cache_hit_allowed(
                    dashboard,
                    complete_equity_bars(),
                    {"SPY": [market_bar("SPY")]},
                )
            )
            update_equity_risk.normalize_equity_decision_contract(
                dashboard["equityShortTermRisk"]
            )
            # Fail-closed migration is safe to serve, but still not current
            # enough to suppress the next real factor recomputation.
            self.assertFalse(
                update_equity_risk.equity_refresh_cache_hit_allowed(
                    dashboard,
                    complete_equity_bars(),
                    {"SPY": [market_bar("SPY")]},
                )
            )

    def test_cache_hit_migrates_unsafe_legacy_band_before_publication(self) -> None:
        dashboard = dashboard_with_equity(legacy_equity_root())
        dashboard["portfolioOverview"] = {
            "available": True,
            "suggestedEquityExposureBand": [50, 80],
            "layers": [
                {
                    "layer": "equityShortTermRisk",
                    "actionable": True,
                    "exposureBandPct": [50, 80],
                }
            ],
        }

        updated = update_equity_risk.build_cache_hit_dashboard(
            dashboard,
            complete_equity_bars(),
            [],
        )

        risk = updated["equityShortTermRisk"]
        self.assertFalse(risk["actionable"])
        self.assertIsNone(risk["allocation"]["exposureBandPct"])
        self.assertEqual(risk["contextAllocation"]["exposureBandPct"], [100, 100])
        overview = updated["portfolioOverview"]
        self.assertIsNone(overview["suggestedEquityExposureBand"])
        equity_layer = next(
            row for row in overview["layers"] if row.get("layer") == "equityShortTermRisk"
        )
        self.assertFalse(equity_layer["actionable"])
        self.assertIsNone(equity_layer["exposureBandPct"])
        self.assertEqual(dashboard_contract_issues(updated), [])

    def test_lkg_borrow_normalizes_equity_before_dependents_are_rebuilt(self) -> None:
        updated = {
            "equityShortTermRisk": {"available": False, "score": None},
            "globalLpplRisk": {},
            "signalValidation": {},
            "spyEarlyWarning": {},
            "macroLiquidity": {},
            "meta": {"equityRefresh": {}},
        }
        previous_risk = current_equity_root(validated=True, score=80.0)
        update_equity_risk.normalize_equity_decision_contract(previous_risk)
        self.assertEqual(previous_risk["allocation"]["exposureBandPct"], [50, 80])
        previous = {"equityShortTermRisk": previous_risk}

        with (
            patch.object(
                update_equity_risk,
                "build_regional_monitor",
                return_value={"available": False},
            ),
            patch.object(
                update_equity_risk,
                "build_equity_signal_validation_row",
                return_value=None,
            ),
            patch.object(
                update_equity_risk,
                "build_portfolio_overview",
                return_value={"available": False},
            ) as portfolio,
        ):
            borrowed = update_equity_risk.preserve_partial_refresh_last_known_good(
                updated,
                previous,
            )

        self.assertIn("equityShortTermRisk", borrowed)
        risk = updated["equityShortTermRisk"]
        self.assertFalse(risk["actionable"])
        self.assertIsNone(risk["allocation"]["exposureBandPct"])
        self.assertEqual(risk["contextAllocation"]["exposureBandPct"], [50, 80])
        self.assertFalse(risk["productionValidation"]["refreshEligible"])
        self.assertFalse(update_equity_risk.equity_decision_contract_current(risk))
        portfolio_risk = portfolio.call_args.kwargs["equity_short_term_risk"]
        self.assertIsNone(portfolio_risk["allocation"]["exposureBandPct"])


class EquityDecisionDashboardContractTests(unittest.TestCase):
    def test_numeric_band_requires_complete_boolean_action_audit(self) -> None:
        risk = current_equity_root(validated=True, score=80.0)
        update_equity_risk.normalize_equity_decision_contract(risk)
        self.assertEqual(dashboard_contract_issues(dashboard_with_equity(risk)), [])

        missing_cases = [
            ("scoreScale", "coreComplete"),
            ("scoreScale", "thresholdComparable"),
            ("surface", "actionable"),
            ("allocation", "actionable"),
            ("productionValidation", "available"),
            ("productionValidation", "scoreContractAllowsAction"),
            ("productionValidation", "thresholdValidated"),
            ("productionValidation", "currentTriggered"),
            ("productionValidation", "actionable"),
        ]
        for section, field in missing_cases:
            with self.subTest(section=section, field=field):
                malformed = copy.deepcopy(risk)
                if section == "surface":
                    malformed.pop(field)
                else:
                    malformed[section].pop(field)
                issues = dashboard_contract_issues(dashboard_with_equity(malformed))
                self.assertTrue(
                    any("numeric allocation requires" in issue for issue in issues),
                    issues,
                )

    def test_actionable_must_match_allocation_and_production_layers(self) -> None:
        risk = current_equity_root(validated=True, score=80.0)
        update_equity_risk.normalize_equity_decision_contract(risk)
        risk["allocation"]["actionable"] = False

        issues = dashboard_contract_issues(dashboard_with_equity(risk))

        self.assertIn(
            "equityShortTermRisk.actionable must match allocation.actionable",
            issues,
        )
        self.assertIn(
            "equityShortTermRisk.allocation must not expose a band when non-actionable",
            issues,
        )

    def test_numeric_band_requires_every_boolean_gate_to_be_true(self) -> None:
        risk = current_equity_root(validated=True, score=80.0)
        update_equity_risk.normalize_equity_decision_contract(risk)
        false_cases = [
            ("scoreScale", "coreComplete"),
            ("scoreScale", "thresholdComparable"),
            ("surface", "actionable"),
            ("allocation", "actionable"),
            ("productionValidation", "available"),
            ("productionValidation", "scoreContractAllowsAction"),
            ("productionValidation", "thresholdValidated"),
            ("productionValidation", "currentTriggered"),
            ("productionValidation", "actionable"),
        ]

        for section, field in false_cases:
            with self.subTest(section=section, field=field):
                malformed = copy.deepcopy(risk)
                if section == "surface":
                    malformed[field] = False
                else:
                    malformed[section][field] = False
                issues = dashboard_contract_issues(dashboard_with_equity(malformed))
                self.assertIn(
                    "equityShortTermRisk numeric allocation requires every production action gate to pass",
                    issues,
                )

    def test_numeric_band_must_be_ordered_and_bounded(self) -> None:
        risk = current_equity_root(validated=True, score=80.0)
        update_equity_risk.normalize_equity_decision_contract(risk)

        for band in ([80, 50], [-1, 50], [50, 101], ["50", 80], [True, 80]):
            with self.subTest(band=band):
                malformed = copy.deepcopy(risk)
                malformed["allocation"]["exposureBandPct"] = band
                issues = dashboard_contract_issues(dashboard_with_equity(malformed))
                self.assertIn(
                    "equityShortTermRisk numeric allocation band must be ordered within 0..100",
                    issues,
                )
                self.assertFalse(
                    update_equity_risk.equity_decision_contract_complete(malformed)
                )


if __name__ == "__main__":
    unittest.main()
