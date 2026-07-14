import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from scripts import update_equity_risk
from treasury_data.build_dashboard import EQUITY_RISK_SYMBOLS
from treasury_data.sources import MarketDailyBar


def make_bar(symbol: str, day: date) -> MarketDailyBar:
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


def complete_market_bars(latest: date) -> dict[str, list[MarketDailyBar]]:
    return {symbol: [make_bar(symbol, latest)] for symbol in EQUITY_RISK_SYMBOLS}


class EquityUpdateDependencyTests(unittest.TestCase):
    def test_partial_refresh_rebuilds_every_downstream_surface(self):
        dashboard = {
            "asOf": "2026-07-10",
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "sourceStatus": [],
            "events": [],
            "macroLiquidity": {"score": 55.0},
            "macroLiquidityEquity": {},
            "spyEarlyWarning": {"score": 40.0},
            "signalValidation": {
                "available": True,
                "factors": [],
                "composites": [
                    {
                        "id": "spyEarlyWarning",
                        "pValue3m": 0.04,
                        "robust": True,
                        "foldStability3m": {"stablePositive": True},
                    },
                    {"id": "equityShortTermRisk", "oosIc3m": -0.9},
                ],
                "multipleTesting": {
                    "families": [
                        {"name": "factors", "size": 0},
                        {"name": "composites", "size": 1},
                    ]
                },
                "excludedModels": [
                    {"id": "legacyModel", "reason": "different endpoint"},
                    {"id": "equityShortTermRisk", "reason": "stale copy"},
                ],
            },
            "regionalMonitor": {"score": 10.0},
            "portfolioOverview": {"score": 10.0},
        }
        new_equity = {
            "score": 99.0,
            "trend": {
                "available": True,
                "points": [{"date": "2026-07-10", "score": 99.0, "componentScores": {"marketFlow": 88.0}}],
            },
        }
        new_lppl = {"available": True, "indices": [{"symbol": "SPY", "score": 99.0}]}
        new_regional = {"available": True, "derivedScore": 99.0}
        new_validation_row = {"id": "equityShortTermRisk", "oosIc3m": 0.4}
        new_portfolio = {"available": True, "derivedScore": 99.0}

        with (
            patch.object(update_equity_risk, "build_equity_short_term_risk_index", return_value=new_equity),
            patch.object(update_equity_risk, "build_global_lppl_risk_index", return_value=new_lppl),
            patch.object(update_equity_risk, "build_regional_monitor", return_value=new_regional) as regional_builder,
            patch.object(update_equity_risk, "build_equity_signal_validation_row", return_value=new_validation_row),
            patch.object(update_equity_risk, "build_portfolio_overview", return_value=new_portfolio) as portfolio_builder,
        ):
            updated = update_equity_risk.build_updated_dashboard(
                dashboard,
                complete_market_bars(date(2026, 7, 10)),
                generated_at=datetime(2026, 7, 13, 1, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(updated["equityShortTermRisk"]["score"], new_equity["score"])
        self.assertNotIn("componentScores", updated["equityShortTermRisk"]["trend"]["points"][0])
        self.assertIs(updated["globalLpplRisk"], new_lppl)
        self.assertIs(updated["regionalMonitor"], new_regional)
        self.assertIs(updated["portfolioOverview"], new_portfolio)
        composite_ids = [row.get("id") for row in updated["signalValidation"]["composites"]]
        self.assertEqual(composite_ids, ["spyEarlyWarning"])
        self.assertTrue(all("actionableRobust" in row for row in updated["signalValidation"]["composites"]))
        self.assertTrue(all("fdrQValue3m" in row for row in updated["signalValidation"]["composites"]))
        exclusions = {row["id"]: row for row in updated["signalValidation"]["excludedModels"]}
        self.assertEqual(exclusions["equityShortTermRisk"]["primaryEndpoint"], "15 trading days")
        self.assertIn("legacyModel", exclusions)
        families = {row["name"]: row["size"] for row in updated["signalValidation"]["multipleTesting"]["families"]}
        self.assertEqual(families["composites"], 1)
        partial = updated["signalValidation"]["partialRefresh"]
        self.assertFalse(partial["equityCompositeUpdated"])
        self.assertTrue(partial["equityDedicatedBacktestUpdated"])
        self.assertTrue(partial["equityExcludedFromGenericFamily"])
        regional_builder.assert_called_once_with(new_lppl)
        self.assertIs(portfolio_builder.call_args.kwargs["equity_short_term_risk"], new_equity)
        self.assertIs(portfolio_builder.call_args.kwargs["global_lppl_risk"], new_lppl)
        self.assertIs(portfolio_builder.call_args.kwargs["regional_monitor"], new_regional)

    def test_partial_validation_keeps_unavailable_preregistered_composites_in_bh_family(self):
        existing = {
            "available": True,
            "factors": [],
            "composites": [
                {
                    "id": "spyEarlyWarning",
                    "pValue3m": 0.04,
                    "robust": True,
                    "foldStability3m": {"stablePositive": True},
                },
                {"id": "equityShortTermRisk", "pValue3m": 0.001},
            ],
            "multipleTesting": {
                "families": [
                    {"name": "factors", "size": 0},
                    {"name": "composites", "size": 3},
                ]
            },
        }

        with patch.object(
            update_equity_risk,
            "build_equity_signal_validation_row",
            return_value={"id": "equityShortTermRisk"},
        ):
            updated = update_equity_risk.refresh_equity_validation(existing, {"trend": {}})

        self.assertEqual([row["id"] for row in updated["composites"]], ["spyEarlyWarning"])
        row = updated["composites"][0]
        self.assertEqual(row["fdrFamilySize"], 3)
        self.assertEqual(row["fdrQValue3m"], 0.12)
        self.assertFalse(row["fdrSignificant3m"])
        family = next(item for item in updated["multipleTesting"]["families"] if item["name"] == "composites")
        self.assertEqual(family["size"], 3)

    def test_degraded_partial_build_keeps_healthy_roots_and_rebuilds_dependents(self):
        previous_equity = {"available": True, "score": 61.0}
        previous_global = {
            "available": True,
            "indices": [
                {"symbol": "SPY", "available": True},
                {"symbol": "QQQ", "available": True},
            ],
        }
        updated = {
            "equityShortTermRisk": {"available": False, "score": None},
            "globalLpplRisk": {
                "available": True,
                "indices": [{"symbol": "SPY", "available": True}],
            },
            "signalValidation": {"available": True, "factors": [], "composites": []},
            "spyEarlyWarning": {},
            "macroLiquidity": {},
            "meta": {"equityRefresh": {"mode": "recomputed", "scoringSkipped": False}},
        }
        previous = {
            "equityShortTermRisk": previous_equity,
            "globalLpplRisk": previous_global,
        }
        rebuilt_regional = {"available": True, "source": "lkg-global"}
        rebuilt_portfolio = {"available": True, "source": "final-roots"}

        with (
            patch.object(update_equity_risk, "build_regional_monitor", return_value=rebuilt_regional) as regional_builder,
            patch.object(update_equity_risk, "build_portfolio_overview", return_value=rebuilt_portfolio) as portfolio_builder,
            patch.object(update_equity_risk, "build_equity_signal_validation_row", return_value=None),
        ):
            borrowed = update_equity_risk.preserve_partial_refresh_last_known_good(updated, previous)

        self.assertEqual(borrowed, ["equityShortTermRisk", "globalLpplRisk"])
        self.assertEqual(updated["equityShortTermRisk"], previous_equity)
        self.assertEqual(updated["globalLpplRisk"], previous_global)
        self.assertIs(updated["regionalMonitor"], rebuilt_regional)
        self.assertIs(updated["portfolioOverview"], rebuilt_portfolio)
        self.assertEqual(updated["meta"]["equityRefresh"]["mode"], "partial-lkg")
        regional_builder.assert_called_once_with(previous_global)
        self.assertEqual(portfolio_builder.call_args.kwargs["equity_short_term_risk"], previous_equity)
        self.assertEqual(portfolio_builder.call_args.kwargs["global_lppl_risk"], previous_global)

    def test_partial_refresh_does_not_rewind_usable_risk_block_dates(self):
        previous = {
            "equityShortTermRisk": {"available": True, "score": 61.0, "asOf": "2026-07-10"},
            "globalLpplRisk": {
                "available": True,
                "indices": [{"symbol": "SPY", "available": True, "asOf": "2026-07-10"}],
            },
        }
        updated = {
            "equityShortTermRisk": {"available": True, "score": 40.0, "asOf": "2026-07-09"},
            "globalLpplRisk": {
                "available": True,
                "indices": [{"symbol": "SPY", "available": True, "asOf": "2026-07-09"}],
            },
            "signalValidation": {"available": True, "factors": [], "composites": []},
            "spyEarlyWarning": {},
            "macroLiquidity": {},
            "meta": {"equityRefresh": {"mode": "recomputed", "scoringSkipped": False}},
        }
        with (
            patch.object(update_equity_risk, "build_regional_monitor", return_value={"available": True}),
            patch.object(update_equity_risk, "build_portfolio_overview", return_value={"available": True}),
            patch.object(update_equity_risk, "build_equity_signal_validation_row", return_value=None),
        ):
            borrowed = update_equity_risk.preserve_partial_refresh_last_known_good(
                updated,
                previous,
                market_bars=None,
                equity_alignment={"blocked": False},
            )

        self.assertEqual(borrowed, ["equityShortTermRisk", "globalLpplRisk"])
        self.assertEqual(updated["equityShortTermRisk"]["asOf"], "2026-07-10")
        self.assertEqual(updated["globalLpplRisk"]["indices"][0]["asOf"], "2026-07-10")

    def test_partial_equity_symbol_set_does_not_replace_healthy_multifactor_score(self):
        previous_equity = {"available": True, "score": 61.0}
        updated = {
            "equityShortTermRisk": {"available": True, "score": 35.0},
            "globalLpplRisk": {"available": False, "indices": []},
            "signalValidation": {"available": True, "factors": [], "composites": []},
            "spyEarlyWarning": {},
            "macroLiquidity": {},
            "meta": {"equityRefresh": {"mode": "recomputed", "scoringSkipped": False}},
        }
        previous = {"equityShortTermRisk": previous_equity}

        with (
            patch.object(update_equity_risk, "build_regional_monitor", return_value={"available": False}),
            patch.object(update_equity_risk, "build_portfolio_overview", return_value={"available": False}),
            patch.object(update_equity_risk, "build_equity_signal_validation_row", return_value=None),
        ):
            borrowed = update_equity_risk.preserve_partial_refresh_last_known_good(
                updated,
                previous,
                market_bars={"SPY": [object()]},
            )

        self.assertEqual(borrowed, ["equityShortTermRisk"])
        self.assertEqual(updated["equityShortTermRisk"], previous_equity)
        self.assertIn("QQQ", updated["meta"]["equityRefresh"]["missingEquitySymbols"])

    def test_stale_cache_symbol_skips_factor_recompute_and_borrows_entire_equity_root(self):
        previous_equity = {"available": True, "score": 61.0, "asOf": "2026-07-10"}
        dashboard = {
            "asOf": "2026-07-10",
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "sourceStatus": [],
            "events": [],
            "equityShortTermRisk": previous_equity,
            "signalValidation": {"available": True, "factors": [], "composites": []},
            "spyEarlyWarning": {},
            "macroLiquidity": {},
            "macroLiquidityEquity": {},
        }
        market_bars = complete_market_bars(date(2026, 7, 10))
        source_rows = [
            {
                "name": "Nasdaq QQQ OHLCV",
                "status": "stale-cache",
                "latest": "2026-07-10",
                "cacheMode": "last-known-good",
                "note": "forced timeout",
            }
        ]

        with (
            patch.object(update_equity_risk, "build_equity_short_term_risk_index") as equity_builder,
            patch.object(
                update_equity_risk,
                "build_global_lppl_risk_index",
                return_value={"available": True, "indices": []},
            ),
            patch.object(update_equity_risk, "build_regional_monitor", return_value={"available": True}),
            patch.object(update_equity_risk, "build_equity_signal_validation_row", return_value=None),
            patch.object(update_equity_risk, "build_portfolio_overview", return_value={"available": True}),
        ):
            updated = update_equity_risk.build_updated_dashboard(
                dashboard,
                market_bars,
                generated_at=datetime(2026, 7, 13, 1, 0, tzinfo=timezone.utc),
                source_status_rows=source_rows,
            )

        equity_builder.assert_not_called()
        self.assertEqual(updated["equityShortTermRisk"], previous_equity)
        refresh_meta = updated["meta"]["equityRefresh"]
        self.assertEqual(refresh_meta["mode"], "partial-lkg")
        self.assertTrue(refresh_meta["scoringSkipped"])
        self.assertEqual(refresh_meta["staleEquitySymbols"], ["QQQ"])
        self.assertEqual(refresh_meta["staleCacheEquitySymbols"], ["QQQ"])
        self.assertEqual(refresh_meta["staleEquitySymbolAges"]["QQQ"]["lagTradingDays"], 0)
        qqq_source = next(row for row in updated["sourceStatus"] if row["name"] == "Nasdaq QQQ OHLCV")
        self.assertEqual(qqq_source["status"], "stale-cache")
        self.assertEqual(qqq_source["lagTradingDays"], 0)
        self.assertTrue(qqq_source["equityRefreshBlocked"])

    def test_missing_required_symbol_skips_factor_recompute(self):
        previous_equity = {"available": True, "score": 61.0, "asOf": "2026-07-10"}
        dashboard = {
            "asOf": "2026-07-10",
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "sourceStatus": [],
            "events": [],
            "equityShortTermRisk": previous_equity,
            "signalValidation": {"available": True, "factors": [], "composites": []},
            "spyEarlyWarning": {},
            "macroLiquidity": {},
            "macroLiquidityEquity": {},
        }
        market_bars = complete_market_bars(date(2026, 7, 10))
        market_bars.pop("QQQ")

        with (
            patch.object(update_equity_risk, "build_equity_short_term_risk_index") as equity_builder,
            patch.object(
                update_equity_risk,
                "build_global_lppl_risk_index",
                return_value={"available": True, "indices": []},
            ),
            patch.object(update_equity_risk, "build_regional_monitor", return_value={"available": True}),
            patch.object(update_equity_risk, "build_equity_signal_validation_row", return_value=None),
            patch.object(update_equity_risk, "build_portfolio_overview", return_value={"available": True}),
        ):
            updated = update_equity_risk.build_updated_dashboard(
                dashboard,
                market_bars,
                generated_at=datetime(2026, 7, 13, 1, 0, tzinfo=timezone.utc),
            )

        equity_builder.assert_not_called()
        self.assertEqual(updated["equityShortTermRisk"], previous_equity)
        refresh_meta = updated["meta"]["equityRefresh"]
        self.assertTrue(refresh_meta["scoringSkipped"])
        self.assertIn("QQQ", refresh_meta["blockedEquitySymbols"])
        self.assertIn("QQQ", refresh_meta["missingEquitySymbols"])
        qqq_source = next(row for row in updated["sourceStatus"] if row["name"] == "Nasdaq QQQ OHLCV")
        self.assertEqual(qqq_source["status"], "missing")
        self.assertTrue(qqq_source["equityRefreshBlocked"])

    def test_symbol_more_than_two_spy_sessions_behind_skips_factor_recompute(self):
        previous_equity = {"available": True, "score": 61.0, "asOf": "2026-07-10"}
        dashboard = {
            "asOf": "2026-07-10",
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "sourceStatus": [],
            "events": [],
            "equityShortTermRisk": previous_equity,
            "signalValidation": {"available": True, "factors": [], "composites": []},
            "spyEarlyWarning": {},
            "macroLiquidity": {},
            "macroLiquidityEquity": {},
        }
        market_bars = complete_market_bars(date(2026, 7, 10))
        market_bars["SPY"] = [
            make_bar("SPY", date(2026, 7, 6) + timedelta(days=offset))
            for offset in range(5)
        ]
        market_bars["QQQ"] = [make_bar("QQQ", date(2026, 7, 7))]

        with (
            patch.object(update_equity_risk, "build_equity_short_term_risk_index") as equity_builder,
            patch.object(
                update_equity_risk,
                "build_global_lppl_risk_index",
                return_value={"available": True, "indices": []},
            ),
            patch.object(update_equity_risk, "build_regional_monitor", return_value={"available": True}),
            patch.object(update_equity_risk, "build_equity_signal_validation_row", return_value=None),
            patch.object(update_equity_risk, "build_portfolio_overview", return_value={"available": True}),
        ):
            updated = update_equity_risk.build_updated_dashboard(
                dashboard,
                market_bars,
                generated_at=datetime(2026, 7, 13, 1, 0, tzinfo=timezone.utc),
            )

        equity_builder.assert_not_called()
        self.assertEqual(updated["equityShortTermRisk"], previous_equity)
        refresh_meta = updated["meta"]["equityRefresh"]
        self.assertEqual(refresh_meta["laggedEquitySymbols"], ["QQQ"])
        self.assertEqual(refresh_meta["staleEquitySymbolAges"]["QQQ"]["lagTradingDays"], 3)
        qqq_source = next(row for row in updated["sourceStatus"] if row["name"] == "Nasdaq QQQ OHLCV")
        self.assertEqual(qqq_source["status"], "stale")
        self.assertEqual(qqq_source["lagTradingDays"], 3)

    def test_two_spy_sessions_of_relative_lag_remains_within_alignment_tolerance(self):
        market_bars = complete_market_bars(date(2026, 7, 10))
        market_bars["SPY"] = [
            make_bar("SPY", date(2026, 7, 6) + timedelta(days=offset))
            for offset in range(5)
        ]
        market_bars["QQQ"] = [make_bar("QQQ", date(2026, 7, 8))]

        alignment = update_equity_risk.assess_equity_refresh_alignment(market_bars)

        self.assertFalse(alignment["blocked"])
        self.assertEqual(alignment["laggedSymbols"], [])


if __name__ == "__main__":
    unittest.main()
