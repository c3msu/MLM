import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import update_equity_risk
from scripts.update_equity_risk import (
    build_cache_hit_dashboard,
    dashboard_covers_market_bars,
    incremental_market_start,
    load_market_bar_cache,
    merge_market_bars,
    save_market_bar_cache,
)
from treasury_data.sources import MarketDailyBar


def make_bar(symbol: str, day: date, close: float) -> MarketDailyBar:
    return MarketDailyBar(
        symbol=symbol,
        date=day,
        open=close - 0.2,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=1_000_000,
        source="unit-test",
    )


class MarketCacheTests(unittest.TestCase):
    def test_cache_round_trip_preserves_sorted_unique_bars(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache" / "market-bars-v1.json"
            newer = make_bar("SPY", date(2026, 7, 10), 102.0)
            older = make_bar("SPY", date(2026, 7, 9), 101.0)

            save_market_bar_cache({"SPY": [newer, older, newer]}, path)
            loaded = load_market_bar_cache(path)

            self.assertEqual([bar.date for bar in loaded["SPY"]], [date(2026, 7, 9), date(2026, 7, 10)])
            self.assertEqual(loaded["SPY"][-1].close, 102.0)

    def test_incremental_start_uses_small_overlap(self):
        bars = [make_bar("SPY", date(2026, 7, 10), 102.0)]

        self.assertEqual(
            incremental_market_start(bars, date(2023, 7, 1), overlap_days=10),
            date(2026, 6, 30),
        )
        self.assertEqual(incremental_market_start([], date(2023, 7, 1)), date(2023, 7, 1))

    def test_merge_replaces_overlap_and_retains_history(self):
        cached = [
            make_bar("SPY", date(2026, 7, 8), 100.0),
            make_bar("SPY", date(2026, 7, 9), 101.0),
        ]
        fetched = [
            make_bar("SPY", date(2026, 7, 9), 101.5),
            make_bar("SPY", date(2026, 7, 10), 102.0),
        ]

        merged = merge_market_bars(cached, fetched)

        self.assertEqual([bar.date for bar in merged], [date(2026, 7, 8), date(2026, 7, 9), date(2026, 7, 10)])
        self.assertEqual(merged[1].close, 101.5)

    def test_dashboard_coverage_allows_scoring_skip_only_when_all_present_series_are_current(self):
        bars = {
            "SPY": [make_bar("SPY", date(2026, 7, 10), 102.0)],
            "QQQ": [make_bar("QQQ", date(2026, 7, 10), 103.0)],
        }
        dashboard = {
            "equityShortTermRisk": {"asOf": "2026-07-10"},
            "globalLpplRisk": {
                "indices": [
                    {"symbol": "SPY", "asOf": "2026-07-10"},
                    {"symbol": "QQQ", "asOf": "2026-07-10"},
                ]
            },
        }

        self.assertTrue(dashboard_covers_market_bars(dashboard, bars))
        dashboard["globalLpplRisk"]["indices"][1]["asOf"] = "2026-07-09"
        self.assertFalse(dashboard_covers_market_bars(dashboard, bars))

    def test_cache_hit_dashboard_keeps_scores_and_records_skipped_recompute(self):
        dashboard = {
            "asOf": "2026-07-10",
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "sourceStatus": [],
            "equityShortTermRisk": {"asOf": "2026-07-10", "score": 62.0},
            "globalLpplRisk": {"indices": [{"symbol": "SPY", "asOf": "2026-07-10"}]},
        }
        bars = {"SPY": [make_bar("SPY", date(2026, 7, 10), 102.0)]}

        updated = build_cache_hit_dashboard(
            dashboard,
            bars,
            [{"name": "Nasdaq SPY OHLCV", "status": "ok", "latest": "2026-07-10"}],
        )

        self.assertEqual(updated["equityShortTermRisk"]["score"], 62.0)
        self.assertTrue(updated["meta"]["equityRefresh"]["scoringSkipped"])
        self.assertEqual(updated["meta"]["equityRefresh"]["mode"], "cache-hit")
        self.assertEqual(updated["schemaVersion"], "1.0.0")

    def test_cache_hit_dashboard_records_stale_equity_input_age(self):
        dashboard = {
            "asOf": "2026-07-10",
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "sourceStatus": [],
            "equityShortTermRisk": {"available": True, "asOf": "2026-07-10", "score": 62.0},
            "globalLpplRisk": {"indices": [{"symbol": "SPY", "asOf": "2026-07-10"}]},
        }
        bars = {
            "SPY": [make_bar("SPY", date(2026, 7, 10), 102.0)],
            "QQQ": [make_bar("QQQ", date(2026, 7, 10), 103.0)],
        }

        updated = build_cache_hit_dashboard(
            dashboard,
            bars,
            [
                {
                    "name": "Nasdaq QQQ OHLCV",
                    "status": "stale-cache",
                    "latest": "2026-07-10",
                    "cacheMode": "last-known-good",
                }
            ],
            generated_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )

        refresh_meta = updated["meta"]["equityRefresh"]
        self.assertEqual(refresh_meta["staleEquitySymbols"], ["QQQ"])
        self.assertEqual(refresh_meta["staleEquitySymbolAges"]["QQQ"]["lagTradingDays"], 0)
        self.assertEqual(refresh_meta["lastKnownGoodBlocks"], ["equityShortTermRisk"])
        qqq_source = next(row for row in updated["sourceStatus"] if row["name"] == "Nasdaq QQQ OHLCV")
        self.assertTrue(qqq_source["equityRefreshBlocked"])

    def test_failed_spy_refresh_keeps_stale_cache_status_for_global_lppl_alias(self):
        cached = {"SPY": [make_bar("SPY", date(2026, 7, 9), 101.0)]}

        def fail(*_args, **_kwargs):
            raise RuntimeError("forced timeout")

        with patch.object(update_equity_risk, "fetch_stooq_daily_bars", side_effect=fail):
            market_bars, rows = update_equity_risk.fetch_equity_market_bars(
                end=date(2026, 7, 10),
                years=1,
                fetcher=fail,
                fallback_fetcher=fail,
                cached_bars=cached,
            )

        self.assertIn("SPY", market_bars)
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["Nasdaq SPY OHLCV"]["status"], "stale-cache")
        self.assertEqual(by_name["Global LPPL SPY OHLCV"]["status"], "stale-cache")
        self.assertEqual(by_name["Global LPPL SPY OHLCV"]["cacheMode"], "last-known-good")

    def test_cold_total_fetch_failure_writes_rejected_candidate_without_replacing_served_snapshot(self):
        dashboard = {
            "schemaVersion": "1.0.0",
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "sourceStatus": [],
            "equityShortTermRisk": {"available": True, "score": 62.0},
            "globalLpplRisk": {"available": True, "indices": [{"symbol": "SPY", "available": True}]},
        }
        source_rows = [{"name": "Nasdaq SPY OHLCV", "status": "warning", "latest": "timeout"}]
        with (
            patch.object(update_equity_risk, "read_dashboard_json", return_value=dashboard),
            patch.object(update_equity_risk, "fetch_equity_market_bars", return_value=({}, source_rows)),
            patch.object(update_equity_risk, "require_dashboard_contract"),
            patch.object(update_equity_risk, "write_failed_dashboard_json") as writer,
            patch.object(update_equity_risk, "save_dashboard_history") as history_writer,
            patch.object(update_equity_risk, "build_updated_dashboard") as builder,
        ):
            updated = update_equity_risk._run_equity_update_unlocked(use_cache=False)

        self.assertIs(updated, dashboard)
        self.assertEqual(updated["equityShortTermRisk"]["score"], 62.0)
        writer.assert_called_once()
        failed_candidate, served_path = writer.call_args.args
        self.assertEqual(failed_candidate["meta"]["equityRefresh"]["mode"], "last-known-good")
        self.assertTrue(failed_candidate["meta"]["equityRefresh"]["scoringSkipped"])
        self.assertEqual(failed_candidate["sourceStatus"][0]["status"], "warning")
        self.assertEqual(served_path.name, "dashboard.json")
        history_writer.assert_not_called()
        builder.assert_not_called()

    def test_partial_history_failure_does_not_replace_served_dashboard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            served = {
                "schemaVersion": "1.0.0",
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-10T22:00:00+00:00",
                "sourceStatus": [],
            }
            candidate = {
                **served,
                "generatedAt": "2026-07-10T22:01:00+00:00",
                "equityShortTermRisk": {"available": True, "asOf": "2026-07-10", "score": 60.0},
            }
            update_equity_risk.write_dashboard_json(served, output)
            bars = {"SPY": [make_bar("SPY", date(2026, 7, 10), 102.0)]}
            rows = [{"name": "Nasdaq SPY OHLCV", "status": "ok", "latest": "2026-07-10"}]

            with (
                patch.object(update_equity_risk, "fetch_equity_market_bars", return_value=(bars, rows)),
                patch.object(update_equity_risk, "build_updated_dashboard", return_value=candidate),
                patch.object(update_equity_risk, "save_dashboard_history", side_effect=OSError("disk full")),
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    update_equity_risk._run_equity_update_unlocked(
                        output,
                        use_cache=False,
                    )

            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), served)


if __name__ == "__main__":
    unittest.main()
