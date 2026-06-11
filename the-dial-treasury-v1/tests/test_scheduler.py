import contextlib
import functools
import http.client
import http.server
import io
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import serve
from scripts.serve import NoStoreHandler, seconds_until_next_run, start_startup_update
from scripts.update_data import REQUIRED_EQUITY_SOURCE_STATUS_NAMES, run_update, write_dashboard_json
from treasury_data.history_store import (
    history_summary,
    save_dashboard_history,
    save_historical_observations,
    save_history_backfill_run,
)
from treasury_data.api import api_payload_for_path, api_response_for_path


class SchedulerTests(unittest.TestCase):
    def core_dashboard(self, generated_at="2026-05-20T15:39:54+00:00"):
        return {
            "asOf": "2026-05-19",
            "generatedAt": generated_at,
            "curve": {"tenors": ["10Y"], "today": [4.56]},
            "groups": [{"id": "duration", "name": "久期", "factors": [{"n": "10Y", "score": -1}]}],
            "macroLiquidity": {
                "score": 41.3,
                "trend": {
                    "available": True,
                    "points": [
                        {"date": "2026-04-30", "score": 22.8, "percentile": 7},
                        {"date": "2026-05-22", "score": 41.4, "percentile": 34},
                    ],
                },
            },
            "equityShortTermRisk": {
                "available": True,
                "score": 82.4,
                "regime": "Strong Alert",
                "regimeCn": "强告警",
                "summary": "短期股市风险为强告警。",
                "asOf": "2026-06-04",
                "method": "same-day risk controls",
                "allocation": {"stance": "短线降风险", "equityExposure": "低配", "hedgeAction": "买入保护"},
                "components": [
                    {"key": "marketFlow", "label": "股市资金/趋势", "detail": "SPY反弹", "available": True, "score": 82},
                    {"key": "sectorRotation", "label": "板块轮动断裂", "detail": "成长跑输", "available": True, "score": 79},
                    {"key": "hotStockReversal", "label": "热点股集体回落", "detail": "龙头回落", "available": True, "score": 76},
                    {"key": "turnover", "label": "成交承接", "detail": "成交偏弱", "available": True, "score": 62},
                    {"key": "eventRisk", "label": "新闻/事件风险", "detail": "事件前", "available": True, "score": 70},
                ],
                "drivers": [],
                "trend": {
                    "available": True,
                    "points": [
                        {"date": "2026-06-03", "score": 64.2, "spyClose": 100},
                        {"date": "2026-06-04", "score": 82.4, "spyClose": 101},
                    ],
                },
                "backtest": {
                    "available": True,
                    "sampleSize": 2,
                    "scoreBuckets": [{"label": "Strong Alert", "count": 1}],
                    "thresholdTests": [{"threshold": 75, "precision": 100.0}],
                    "regressionTests": [{"target": "maxDrawdown15d", "rSquared": 0.4}],
                    "worstWindows": [],
                    "componentDiagnostics": [
                        {
                            "component": "marketFlow",
                            "label": "股市资金/趋势",
                            "decision": "support",
                            "decisionCn": "辅助保留",
                            "recommendation": "保留低到中权重。",
                        }
                    ],
                },
                "lookAheadGuard": {"dataThrough": "2026-06-04"},
            },
            "sourceStatus": [{"name": "FRED", "status": "ok", "latest": "2026-05-22"}],
        }

    def test_seconds_until_next_run_uses_today_when_time_is_future(self):
        now = datetime(2026, 5, 20, 8, 30, 0)

        seconds = seconds_until_next_run("16:30", now=now)

        self.assertEqual(seconds, 8 * 60 * 60)

    def test_seconds_until_next_run_rolls_to_tomorrow_when_time_passed(self):
        now = datetime(2026, 5, 20, 17, 0, 0)

        seconds = seconds_until_next_run("16:30", now=now)

        self.assertEqual(seconds, int((datetime(2026, 5, 21, 16, 30) - now).total_seconds()))

    def test_write_dashboard_json_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nested" / "dashboard.json"

            write_dashboard_json({"asOf": "2026-05-18"}, output)

            self.assertTrue(output.exists())
            self.assertIn("2026-05-18", output.read_text())

    def test_write_dashboard_json_does_not_create_static_api_slice_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            dashboard = {
                "curve": {"tenors": ["10Y"], "today": [4.61]},
                "fedPath": [{"m": "6/17", "hold": 99, "hike": 0, "cut": 1}],
                "groups": [{"id": "g1"}],
                "auctions": [{"type": "10Y"}],
                "news": [["5/18", "FRED", "10Y"]],
                "sourceStatus": [{"name": "FRED", "status": "ok", "latest": "2026-05-18"}],
            }

            write_dashboard_json(dashboard, output)

            self.assertTrue(output.exists())
            self.assertFalse((Path(temp_dir) / "api").exists())

    def test_run_update_keeps_existing_healthy_dashboard_when_refresh_has_source_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            history_db = Path(temp_dir) / "data" / "history.sqlite3"
            healthy = {
                "asOf": "2026-05-19",
                "generatedAt": "2026-05-20T15:39:54+00:00",
                "sourceStatus": [{"name": "TreasuryDirect auctioned securities", "status": "ok", "latest": "250"}],
            }
            failed = {
                "asOf": "2026-05-19",
                "generatedAt": "2026-05-20T15:57:13+00:00",
                "sourceStatus": [{"name": "TreasuryDirect auctioned securities", "status": "error", "latest": "timeout"}],
            }
            write_dashboard_json(healthy, output)

            dashboard = run_update(output, build_func=lambda: failed, history_path=history_db)

            self.assertEqual(dashboard["generatedAt"], healthy["generatedAt"])
            self.assertIn(healthy["generatedAt"], output.read_text(encoding="utf-8"))
            failed_output = output.with_name("dashboard.failed.json")
            self.assertTrue(failed_output.exists())
            self.assertIn(failed["generatedAt"], failed_output.read_text(encoding="utf-8"))
            self.assertFalse(history_db.exists())

    def test_run_update_writes_core_usable_dashboard_when_soft_source_has_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            history_db = Path(temp_dir) / "data" / "history.sqlite3"
            healthy = {
                "asOf": "2026-05-19",
                "generatedAt": "2026-05-20T15:39:54+00:00",
                "sourceStatus": [{"name": "TreasuryDirect auctioned securities", "status": "ok", "latest": "250"}],
            }
            refreshed = self.core_dashboard("2026-05-25T02:18:13+00:00")
            refreshed["asOf"] = "2026-05-22"
            refreshed["percentiles"] = {"items": [{"name": "10Y", "percentile": 70, "value": "4.56%", "source": "Treasury"}]}
            refreshed["sourceStatus"] = [
                {"name": "TreasuryDirect auctioned securities", "status": "error", "latest": "timeout"},
                {"name": "FRED", "status": "ok", "latest": "2026-05-22"},
            ]
            write_dashboard_json(healthy, output)

            dashboard = run_update(output, build_func=lambda: refreshed, history_path=history_db)

            self.assertEqual(dashboard["generatedAt"], refreshed["generatedAt"])
            self.assertIn(refreshed["generatedAt"], output.read_text(encoding="utf-8"))
            failed_output = output.with_name("dashboard.failed.json")
            self.assertTrue(failed_output.exists())
            self.assertIn(refreshed["generatedAt"], failed_output.read_text(encoding="utf-8"))
            self.assertEqual(history_summary(history_db)["snapshotCount"], 1)

    def test_run_update_keeps_existing_core_dashboard_when_refresh_drops_equity_backtest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            history_db = Path(temp_dir) / "data" / "history.sqlite3"
            healthy = self.core_dashboard("2026-06-07T07:24:53+00:00")
            stale_refresh = self.core_dashboard("2026-06-07T09:10:13+00:00")
            stale_refresh["equityShortTermRisk"].pop("backtest")
            write_dashboard_json(healthy, output)

            dashboard = run_update(output, build_func=lambda: stale_refresh, history_path=history_db)

            self.assertEqual(dashboard["generatedAt"], healthy["generatedAt"])
            self.assertIn(healthy["generatedAt"], output.read_text(encoding="utf-8"))
            failed_output = output.with_name("dashboard.failed.json")
            self.assertTrue(failed_output.exists())
            self.assertIn(stale_refresh["generatedAt"], failed_output.read_text(encoding="utf-8"))
            self.assertFalse(history_db.exists())

    def test_run_update_keeps_existing_core_dashboard_when_refresh_drops_equity_factor_audit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            history_db = Path(temp_dir) / "data" / "history.sqlite3"
            healthy = self.core_dashboard("2026-06-07T07:24:53+00:00")
            stale_refresh = self.core_dashboard("2026-06-07T09:10:13+00:00")
            stale_refresh["equityShortTermRisk"]["backtest"].pop("componentDiagnostics")
            write_dashboard_json(healthy, output)

            dashboard = run_update(output, build_func=lambda: stale_refresh, history_path=history_db)

            self.assertEqual(dashboard["generatedAt"], healthy["generatedAt"])
            failed_output = output.with_name("dashboard.failed.json")
            self.assertTrue(failed_output.exists())
            self.assertIn(stale_refresh["generatedAt"], failed_output.read_text(encoding="utf-8"))
            self.assertFalse(history_db.exists())

    def test_run_update_keeps_existing_dashboard_when_refresh_loses_equity_source_monitoring(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            history_db = Path(temp_dir) / "data" / "history.sqlite3"
            healthy = self.core_dashboard("2026-06-07T07:24:53+00:00")
            healthy["sourceStatus"] = [
                {"name": name, "status": "ok", "latest": "2026-06-05"}
                for name in REQUIRED_EQUITY_SOURCE_STATUS_NAMES
            ]
            stale_refresh = self.core_dashboard("2026-06-07T09:10:13+00:00")
            stale_refresh["sourceStatus"] = [
                {"name": name, "status": "ok", "latest": "2026-06-05"}
                for name in REQUIRED_EQUITY_SOURCE_STATUS_NAMES
            ]
            stale_refresh["sourceStatus"][0]["status"] = "warning"
            stale_refresh["sourceStatus"][0]["latest"] = "timeout"
            write_dashboard_json(healthy, output)

            dashboard = run_update(output, build_func=lambda: stale_refresh, history_path=history_db)

            self.assertEqual(dashboard["generatedAt"], healthy["generatedAt"])
            failed_output = output.with_name("dashboard.failed.json")
            self.assertTrue(failed_output.exists())
            self.assertIn(stale_refresh["generatedAt"], failed_output.read_text(encoding="utf-8"))
            self.assertFalse(history_db.exists())

    def test_run_update_persists_successful_dashboard_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            history_db = Path(temp_dir) / "data" / "history.sqlite3"
            dashboard = {
                "asOf": "2026-05-22",
                "generatedAt": "2026-05-24T11:45:10+00:00",
                "curve": {"tenors": ["10Y"], "today": [4.56]},
                "sourceStatus": [{"name": "FRED", "status": "ok", "latest": "2026-05-22"}],
            }

            run_update(output, build_func=lambda: dashboard, history_path=history_db)

            self.assertTrue(output.exists())
            self.assertEqual(history_summary(history_db)["snapshotCount"], 1)

    def test_start_startup_update_returns_before_slow_refresh_finishes(self):
        entered = threading.Event()
        release = threading.Event()

        def slow_update(output):
            entered.set()
            release.wait(timeout=2)
            return {"asOf": "2026-05-19", "generatedAt": "2026-05-20T14:19:36+00:00"}

        with contextlib.redirect_stdout(io.StringIO()):
            started_at = time.monotonic()
            thread = start_startup_update(Path("dashboard.json"), update_func=slow_update)
            elapsed = time.monotonic() - started_at

            self.assertIsNotNone(thread)
            self.assertLess(elapsed, 0.2)
            self.assertTrue(entered.wait(timeout=1))
            release.set()
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())

    def test_start_manual_update_returns_before_slow_refresh_finishes(self):
        entered = threading.Event()
        release = threading.Event()

        def slow_update(output):
            entered.set()
            release.wait(timeout=2)
            return {"asOf": "2026-05-19", "generatedAt": "2026-05-20T14:19:36+00:00"}

        with contextlib.redirect_stdout(io.StringIO()):
            started_at = time.monotonic()
            thread = serve.start_manual_update(Path("dashboard.json"), update_func=slow_update)
            elapsed = time.monotonic() - started_at

            self.assertIsNotNone(thread)
            self.assertLess(elapsed, 0.2)
            self.assertTrue(entered.wait(timeout=1))
            release.set()
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())

    def test_default_handler_update_func_is_not_bound_to_request_instance(self):
        handler = object.__new__(NoStoreHandler)

        self.assertIs(handler.update_func, run_update)

    def test_start_manual_update_reuses_running_refresh(self):
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def slow_update(output):
            calls.append(output)
            entered.set()
            release.wait(timeout=2)
            return {"asOf": "2026-05-19", "generatedAt": "2026-05-20T14:19:36+00:00"}

        with contextlib.redirect_stdout(io.StringIO()):
            first_thread = serve.start_manual_update(Path("dashboard.json"), update_func=slow_update)
            self.assertTrue(entered.wait(timeout=1))
            second_thread = serve.start_manual_update(Path("dashboard.json"), update_func=slow_update)
            release.set()
            first_thread.join(timeout=1)

        self.assertIs(second_thread, first_thread)
        self.assertEqual(calls, [Path("dashboard.json")])

    def test_equity_update_loop_runs_lightweight_refresh_on_interval(self):
        calls = []
        sleeps = []

        def equity_update(output, *, years, timeout, limit):
            calls.append((output, years, timeout, limit))
            return {
                "asOf": "2026-06-04",
                "generatedAt": "2026-06-04T20:01:00+00:00",
                "equityShortTermRisk": {"score": 80.4, "asOf": "2026-06-04"},
            }

        with contextlib.redirect_stdout(io.StringIO()):
            serve.equity_update_loop(
                interval_minutes=30,
                output=Path("dashboard.json"),
                equity_update_func=equity_update,
                years=2,
                timeout=9,
                limit=500,
                stale_check_func=lambda output: False,
                sleep_func=lambda seconds: sleeps.append(seconds),
                max_runs=2,
                initial_delay_seconds=5,
            )

        self.assertEqual(sleeps, [5, 30 * 60])
        self.assertEqual(
            calls,
            [
                (Path("dashboard.json"), 2, 9, 500),
                (Path("dashboard.json"), 2, 9, 500),
            ],
        )

    def test_start_manual_equity_update_reuses_running_refresh(self):
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def slow_update(output, *, years, timeout, limit):
            calls.append((output, years, timeout, limit))
            entered.set()
            release.wait(timeout=2)
            return {
                "asOf": "2026-06-04",
                "generatedAt": "2026-06-04T20:01:00+00:00",
                "equityShortTermRisk": {"score": 80.4, "asOf": "2026-06-04"},
            }

        with contextlib.redirect_stdout(io.StringIO()):
            first_thread = serve.start_manual_equity_update(
                Path("dashboard.json"),
                equity_update_func=slow_update,
                years=2,
                timeout=9,
                limit=500,
            )
            self.assertTrue(entered.wait(timeout=1))
            second_thread = serve.start_manual_equity_update(
                Path("dashboard.json"),
                equity_update_func=slow_update,
                years=2,
                timeout=9,
                limit=500,
            )
            release.set()
            first_thread.join(timeout=1)

        self.assertIs(second_thread, first_thread)
        self.assertEqual(calls, [(Path("dashboard.json"), 2, 9, 500)])

    def test_full_and_equity_updates_share_dashboard_write_lock(self):
        entered_full = threading.Event()
        release_full = threading.Event()
        order = []

        def slow_full_update(output):
            order.append(("full-start", output))
            entered_full.set()
            release_full.wait(timeout=2)
            order.append(("full-end", output))
            return {"asOf": "2026-06-04", "generatedAt": "2026-06-04T20:01:00+00:00"}

        def equity_update(output, *, years, timeout, limit):
            order.append(("equity-start", output, years, timeout, limit))
            return {
                "asOf": "2026-06-04",
                "generatedAt": "2026-06-04T20:02:00+00:00",
                "equityShortTermRisk": {"score": 80.4, "asOf": "2026-06-04"},
            }

        with contextlib.redirect_stdout(io.StringIO()):
            full_thread = threading.Thread(
                target=serve.run_logged_update,
                args=("full", Path("dashboard.json"), slow_full_update),
                daemon=True,
            )
            full_thread.start()
            self.assertTrue(entered_full.wait(timeout=1))
            equity_thread = threading.Thread(
                target=serve.run_logged_equity_update,
                args=("equity", Path("dashboard.json"), equity_update),
                kwargs={"years": 2, "timeout": 9, "limit": 500},
                daemon=True,
            )
            equity_thread.start()
            time.sleep(0.05)
            self.assertEqual(order, [("full-start", Path("dashboard.json"))])
            release_full.set()
            full_thread.join(timeout=1)
            equity_thread.join(timeout=1)

        self.assertEqual(
            order,
            [
                ("full-start", Path("dashboard.json")),
                ("full-end", Path("dashboard.json")),
                ("equity-start", Path("dashboard.json"), 2, 9, 500),
            ],
        )

    def test_expected_equity_bar_date_waits_for_after_close_lag(self):
        before_ready = datetime(2026, 6, 8, 20, 10, tzinfo=timezone.utc)
        after_ready = datetime(2026, 6, 8, 20, 40, tzinfo=timezone.utc)

        self.assertEqual(
            serve.expected_equity_bar_date(before_ready, after_close_lag_minutes=30).isoformat(),
            "2026-06-05",
        )
        self.assertEqual(
            serve.expected_equity_bar_date(after_ready, after_close_lag_minutes=30).isoformat(),
            "2026-06-08",
        )

    def test_equity_risk_freshness_flags_stale_only_after_expected_bar_date_advances(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            dashboard = self.core_dashboard(generated_at="2026-06-08T20:00:00+00:00")
            dashboard["equityShortTermRisk"]["asOf"] = "2026-06-05"
            write_dashboard_json(dashboard, output)

            before_ready = serve.equity_risk_freshness(
                output,
                now=datetime(2026, 6, 8, 20, 10, tzinfo=timezone.utc),
                after_close_lag_minutes=30,
            )
            after_ready = serve.equity_risk_freshness(
                output,
                now=datetime(2026, 6, 8, 20, 40, tzinfo=timezone.utc),
                after_close_lag_minutes=30,
            )

        self.assertFalse(before_ready["stale"])
        self.assertEqual(before_ready["expectedDate"], "2026-06-05")
        self.assertTrue(after_ready["stale"])
        self.assertEqual(after_ready["expectedDate"], "2026-06-08")
        self.assertEqual(after_ready["sourceDate"], "2026-06-05")

    def test_equity_risk_freshness_reports_waiting_phase_before_expected_bar_is_due(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            dashboard = self.core_dashboard(generated_at="2026-06-08T20:00:00+00:00")
            dashboard["equityShortTermRisk"]["asOf"] = "2026-06-05"
            write_dashboard_json(dashboard, output)

            freshness = serve.equity_risk_freshness(
                output,
                now=datetime(2026, 6, 8, 20, 10, tzinfo=timezone.utc),
                after_close_lag_minutes=30,
            )

        self.assertFalse(freshness["stale"])
        self.assertEqual(freshness["phase"], "post_close_wait")
        self.assertEqual(freshness["timeliness"], "waiting")
        self.assertEqual(freshness["minutesUntilExpected"], 20)
        self.assertEqual(freshness["readyAt"], "2026-06-08T16:30:00-04:00")

    def test_equity_risk_freshness_reports_catchup_phase_after_expected_bar_is_due(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            dashboard = self.core_dashboard(generated_at="2026-06-08T20:00:00+00:00")
            dashboard["equityShortTermRisk"]["asOf"] = "2026-06-05"
            write_dashboard_json(dashboard, output)

            freshness = serve.equity_risk_freshness(
                output,
                now=datetime(2026, 6, 8, 20, 40, tzinfo=timezone.utc),
                after_close_lag_minutes=30,
            )

        self.assertTrue(freshness["stale"])
        self.assertEqual(freshness["phase"], "catchup")
        self.assertEqual(freshness["timeliness"], "catchup")
        self.assertEqual(freshness["minutesSinceExpected"], 10)
        self.assertEqual(freshness["readyAt"], "2026-06-08T16:30:00-04:00")

    def test_equity_update_loop_uses_catchup_interval_when_equity_snapshot_is_stale(self):
        calls = []
        sleeps = []

        def equity_update(output, *, years, timeout, limit):
            calls.append((output, years, timeout, limit))
            return {
                "asOf": "2026-06-04",
                "generatedAt": "2026-06-04T20:01:00+00:00",
                "equityShortTermRisk": {"score": 80.4, "asOf": "2026-06-04"},
            }

        with contextlib.redirect_stdout(io.StringIO()):
            serve.equity_update_loop(
                interval_minutes=30,
                output=Path("dashboard.json"),
                equity_update_func=equity_update,
                years=2,
                timeout=9,
                limit=500,
                catchup_interval_minutes=5,
                stale_check_func=lambda output: True,
                sleep_func=lambda seconds: sleeps.append(seconds),
                max_runs=2,
                initial_delay_seconds=0,
            )

        self.assertEqual(sleeps, [0, 5 * 60])
        self.assertEqual(len(calls), 2)

    def test_post_update_starts_manual_refresh_and_returns_current_snapshot(self):
        entered = threading.Event()
        release = threading.Event()

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            write_dashboard_json(
                {"asOf": "2026-05-19", "generatedAt": "2026-05-20T14:19:36+00:00", "sourceStatus": []},
                output,
            )

            def slow_update(path):
                self.assertEqual(path, output)
                entered.set()
                release.wait(timeout=2)
                return {"asOf": "2026-05-20", "generatedAt": "2026-05-21T14:19:36+00:00"}

            class ManualRefreshHandler(NoStoreHandler):
                dashboard_output = output
                update_func = staticmethod(slow_update)

                def log_message(self, format, *args):  # noqa: A002
                    return

            handler = functools.partial(ManualRefreshHandler, directory=temp_dir)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                connection.request("POST", "/api/update")
                response = connection.getresponse()
                body = response.read()
            finally:
                release.set()
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

            payload = json.loads(body.decode("utf-8"))
            self.assertEqual(response.status, 202)
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(payload["asOf"], "2026-05-19")
            self.assertTrue(entered.wait(timeout=1))

    def test_post_update_equity_starts_lightweight_refresh_and_returns_current_risk_snapshot(self):
        entered = threading.Event()
        release = threading.Event()

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            dashboard = self.core_dashboard(generated_at="2026-06-04T20:00:00+00:00")
            write_dashboard_json(dashboard, output)

            def slow_equity_update(path, *, years, timeout, limit):
                self.assertEqual(path, output)
                self.assertEqual((years, timeout, limit), (2, 9, 500))
                entered.set()
                release.wait(timeout=2)
                return {
                    **dashboard,
                    "generatedAt": "2026-06-04T20:02:00+00:00",
                    "equityShortTermRisk": {"score": 80.4, "asOf": "2026-06-04"},
                }

            class EquityRefreshHandler(NoStoreHandler):
                dashboard_output = output
                equity_update_func = staticmethod(slow_equity_update)
                equity_years = 2
                equity_timeout = 9
                equity_limit = 500

                def log_message(self, format, *args):  # noqa: A002
                    return

            handler = functools.partial(EquityRefreshHandler, directory=temp_dir)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                connection.request("POST", "/api/update-equity")
                response = connection.getresponse()
                body = response.read()
            finally:
                release.set()
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

            payload = json.loads(body.decode("utf-8"))
            self.assertEqual(response.status, 202)
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(payload["asOf"], "2026-05-19")
            self.assertEqual(payload["equityRiskAsOf"], "2026-06-04")
            self.assertEqual(payload["equityRiskScore"], 82.4)
            self.assertTrue(entered.wait(timeout=1))

    def test_post_update_equity_returns_current_freshness_for_immediate_ui_feedback(self):
        entered = threading.Event()
        release = threading.Event()

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            dashboard = self.core_dashboard(generated_at="2026-06-08T20:00:00+00:00")
            dashboard["equityShortTermRisk"]["asOf"] = "2026-06-05"
            write_dashboard_json(dashboard, output)

            def slow_equity_update(path, *, years, timeout, limit):
                entered.set()
                release.wait(timeout=2)
                return dashboard

            class EquityRefreshHandler(NoStoreHandler):
                dashboard_output = output
                equity_update_func = staticmethod(slow_equity_update)
                equity_freshness_now = datetime(2026, 6, 8, 20, 40, tzinfo=timezone.utc)
                equity_after_close_lag_minutes = 30

                def log_message(self, format, *args):  # noqa: A002
                    return

            handler = functools.partial(EquityRefreshHandler, directory=temp_dir)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                connection.request("POST", "/api/update-equity")
                response = connection.getresponse()
                body = response.read()
            finally:
                release.set()
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

            payload = json.loads(body.decode("utf-8"))
            self.assertEqual(response.status, 202)
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(payload["equityRiskFreshness"]["phase"], "catchup")
            self.assertEqual(payload["equityRiskFreshness"]["timeliness"], "catchup")
            self.assertEqual(payload["equityRiskFreshness"]["expectedDate"], "2026-06-08")
            self.assertEqual(payload["equityRiskFreshness"]["sourceDate"], "2026-06-05")
            self.assertTrue(entered.wait(timeout=1))

    def test_post_update_reports_running_without_starting_duplicate_refresh(self):
        entered = threading.Event()
        release = threading.Event()
        calls = []

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            write_dashboard_json(
                {"asOf": "2026-05-19", "generatedAt": "2026-05-20T14:19:36+00:00", "sourceStatus": []},
                output,
            )

            def slow_update(path):
                calls.append(path)
                entered.set()
                release.wait(timeout=2)
                return {"asOf": "2026-05-20", "generatedAt": "2026-05-21T14:19:36+00:00"}

            class ManualRefreshHandler(NoStoreHandler):
                dashboard_output = output
                update_func = staticmethod(slow_update)

                def log_message(self, format, *args):  # noqa: A002
                    return

            handler = functools.partial(ManualRefreshHandler, directory=temp_dir)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                first = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                first.request("POST", "/api/update")
                first_response = first.getresponse()
                first_payload = json.loads(first_response.read().decode("utf-8"))
                self.assertTrue(entered.wait(timeout=1))

                second = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                second.request("POST", "/api/update")
                second_response = second.getresponse()
                second_payload = json.loads(second_response.read().decode("utf-8"))
            finally:
                release.set()
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

            self.assertEqual(first_response.status, 202)
            self.assertEqual(first_payload["status"], "accepted")
            self.assertEqual(second_response.status, 202)
            self.assertEqual(second_payload["status"], "running")
            self.assertEqual(calls, [output])

    def test_api_payload_for_path_returns_dashboard_slices(self):
        dashboard = {
            "curve": {"tenors": ["10Y"], "today": [4.61]},
            "decomposition": {"components": []},
            "fedPath": [{"m": "6/17", "hold": 99, "hike": 0, "cut": 1}],
            "groups": [{"id": "g1"}],
            "policy": {"rates": []},
            "auctions": [{"type": "10Y"}],
            "positioning": {"cftc": []},
            "cross": {"yields": []},
            "percentiles": {"items": [{"name": "净流动性", "percentile": 13}]},
            "events": [["2026-06-17", "FOMC", "高"]],
            "news": [["5/18", "FRED", "10Y"]],
            "ideas": [{"title": "idea"}],
            "sourceStatus": [{"name": "FRED", "status": "ok", "latest": "2026-05-18"}],
        }

        status, payload = api_payload_for_path(dashboard, "/api/curve")

        self.assertEqual(status, 200)
        self.assertEqual(payload, dashboard["curve"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/decomposition")[1], dashboard["decomposition"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/fed_path")[1], dashboard["fedPath"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/scorecard")[1], dashboard["groups"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/policy")[1], dashboard["policy"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/auctions")[1], dashboard["auctions"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/positioning")[1], dashboard["positioning"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/cross")[1], dashboard["cross"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/percentiles")[1], dashboard["percentiles"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/events")[1], dashboard["events"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/news")[1], dashboard["news"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/ideas")[1], dashboard["ideas"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/source_status")[1], dashboard["sourceStatus"])
        self.assertEqual(api_payload_for_path(dashboard, "/api/source-status")[1], dashboard["sourceStatus"])

    def test_api_history_endpoints_return_sqlite_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            history_db = Path(temp_dir) / "data" / "history.sqlite3"
            dashboard = {
                "asOf": "2026-05-22",
                "generatedAt": "2026-05-24T11:45:10+00:00",
                "curve": {"tenors": ["10Y"], "today": [4.56]},
                "sourceStatus": [{"name": "FRED", "status": "ok", "latest": "2026-05-22"}],
            }
            write_dashboard_json(dashboard, output)
            save_dashboard_history(dashboard, history_db)
            save_historical_observations(
                [
                    {"date": "2021-05-24", "category": "curve_yield", "name": "10Y收益率", "value": 1.62, "unit": "%", "source": "Treasury"},
                    {"date": "2026-05-22", "category": "curve_yield", "name": "10Y收益率", "value": 4.56, "unit": "%", "source": "Treasury"},
                ],
                history_db,
            )
            save_history_backfill_run(
                {
                    "startDate": "2021-05-25",
                    "endDate": "2026-05-25",
                    "observationCount": 64572,
                    "savedObservationCount": 64572,
                    "sourceErrors": [
                        {"name": "TreasuryDirect auctioned securities", "error": "curl timeout"},
                    ],
                },
                history_db,
                years=5,
            )

            class HistoryHandler(NoStoreHandler):
                dashboard_output = output
                history_db_path = history_db

                def log_message(self, format, *args):  # noqa: A002
                    return

            handler = functools.partial(HistoryHandler, directory=temp_dir)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                summary_connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                summary_connection.request("GET", "/api/history")
                summary_response = summary_connection.getresponse()
                summary_payload = json.loads(summary_response.read().decode("utf-8"))

                snapshots_connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                snapshots_connection.request("GET", "/api/history/snapshots")
                snapshots_response = snapshots_connection.getresponse()
                snapshots_payload = json.loads(snapshots_response.read().decode("utf-8"))

                stats_connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                stats_connection.request("GET", "/api/history/stats")
                stats_response = stats_connection.getresponse()
                stats_payload = json.loads(stats_response.read().decode("utf-8"))

                series_connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                series_connection.request(
                    "GET",
                    "/api/history/series?category=curve_yield&name=10Y%E6%94%B6%E7%9B%8A%E7%8E%87",
                )
                series_response = series_connection.getresponse()
                series_payload = json.loads(series_response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

            self.assertEqual(summary_response.status, 200)
            self.assertEqual(summary_payload["snapshotCount"], 1)
            self.assertEqual(summary_payload["latest"]["asOf"], "2026-05-22")
            self.assertEqual(summary_payload["historicalObservationCount"], 2)
            self.assertEqual(snapshots_response.status, 200)
            self.assertEqual(snapshots_payload[0]["metricCount"], 1)
            self.assertEqual(stats_response.status, 200)
            self.assertEqual(stats_payload[0]["name"], "10Y收益率")
            self.assertEqual(series_response.status, 200)
            self.assertEqual(len(series_payload["points"]), 2)
            self.assertEqual(series_payload["series"]["name"], "10Y收益率")

    def test_unknown_history_endpoint_returns_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"

            status, payload = serve.history_payload_for_path("/api/history/unknown", db_path)

            self.assertEqual(status, 404)
            self.assertEqual(payload, {"error": "unknown api route"})

    def test_api_health_includes_latest_history_backfill_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            history_db = Path(temp_dir) / "data" / "history.sqlite3"
            dashboard = {
                "asOf": "2026-05-22",
                "generatedAt": "2026-05-25T11:03:14+00:00",
                "sourceStatus": [{"name": "FRED", "status": "ok", "latest": "2026-05-22"}],
            }
            write_dashboard_json(dashboard, output)
            save_history_backfill_run(
                {
                    "startDate": "2021-05-25",
                    "endDate": "2026-05-25",
                    "observationCount": 64572,
                    "savedObservationCount": 64572,
                    "sourceErrors": [
                        {"name": "TreasuryDirect auctioned securities", "error": "curl timeout"},
                    ],
                },
                history_db,
                years=5,
            )

            class HealthHandler(NoStoreHandler):
                dashboard_output = output
                history_db_path = history_db

                def log_message(self, format, *args):  # noqa: A002
                    return

            handler = functools.partial(HealthHandler, directory=temp_dir)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                connection.request("GET", "/api/health")
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

            self.assertEqual(response.status, 200)
            self.assertEqual(payload["status"], "degraded")
            self.assertEqual(payload["history"]["latestBackfill"]["status"], "degraded")
            self.assertEqual(payload["warnings"][0]["name"], "TreasuryDirect auctioned securities")

    def test_api_health_does_not_degrade_for_warning_only_history_backfill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            history_db = Path(temp_dir) / "data" / "history.sqlite3"
            dashboard = {
                "asOf": "2026-05-22",
                "generatedAt": "2026-05-25T11:03:14+00:00",
                "sourceStatus": [{"name": "FRED", "status": "ok", "latest": "2026-05-22"}],
            }
            write_dashboard_json(dashboard, output)
            save_history_backfill_run(
                {
                    "startDate": "2021-05-25",
                    "endDate": "2026-05-25",
                    "observationCount": 64572,
                    "savedObservationCount": 64572,
                    "sourceErrors": [
                        {"name": "TreasuryDirect auctioned securities", "error": "curl timeout", "severity": "warning"},
                    ],
                },
                history_db,
                years=5,
            )

            class HealthHandler(NoStoreHandler):
                dashboard_output = output
                history_db_path = history_db

                def log_message(self, format, *args):  # noqa: A002
                    return

            handler = functools.partial(HealthHandler, directory=temp_dir)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                connection.request("GET", "/api/health")
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

            self.assertEqual(response.status, 200)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["history"]["latestBackfill"]["status"], "ok")
            self.assertNotIn("warnings", payload)

    def test_api_health_degrades_when_equity_risk_snapshot_is_stale_after_close(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            dashboard = self.core_dashboard(generated_at="2026-06-08T20:00:00+00:00")
            dashboard["equityShortTermRisk"]["asOf"] = "2026-06-05"
            write_dashboard_json(dashboard, output)

            class HealthHandler(NoStoreHandler):
                dashboard_output = output
                equity_freshness_now = datetime(2026, 6, 8, 20, 40, tzinfo=timezone.utc)

                def log_message(self, format, *args):  # noqa: A002
                    return

            handler = functools.partial(HealthHandler, directory=temp_dir)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                connection.request("GET", "/api/health")
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

            self.assertEqual(response.status, 200)
            self.assertEqual(payload["status"], "degraded")
            self.assertEqual(payload["equityRiskFreshness"]["expectedDate"], "2026-06-08")
            self.assertEqual(payload["equityRiskFreshness"]["sourceDate"], "2026-06-05")
            self.assertTrue(payload["equityRiskFreshness"]["stale"])
            self.assertEqual(payload["equityRiskFreshness"]["phase"], "catchup")
            self.assertEqual(payload["equityRiskFreshness"]["timeliness"], "catchup")
            self.assertEqual(payload["equityRiskFreshness"]["minutesSinceExpected"], 20)
            self.assertEqual(payload["warnings"][0]["name"], "Equity Short-Term Risk")

    def test_api_payload_for_path_returns_404_for_unknown_api_route(self):
        status, payload = api_payload_for_path({}, "/api/unknown")

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "unknown api route")

    def test_api_health_summarizes_update_and_source_errors(self):
        dashboard = {
            "asOf": "2026-05-19",
            "generatedAt": "2026-05-20T14:19:36+00:00",
            "sourceStatus": [
                {"name": "FRED TREAST", "status": "ok", "latest": "2026-05-13"},
                {"name": "Fed path", "status": "modeled", "latest": "curve/macro proxy"},
                {"name": "Treasury TIC", "status": "error", "latest": "timeout"},
            ],
        }

        status, payload = api_payload_for_path(dashboard, "/api/health")

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["asOf"], "2026-05-19")
        self.assertEqual(payload["generatedAt"], "2026-05-20T14:19:36+00:00")
        self.assertEqual(payload["sourceCounts"], {"ok": 1, "modeled": 1, "error": 1})
        self.assertEqual(payload["errors"], [{"name": "Treasury TIC", "status": "error", "latest": "timeout"}])

    def test_api_payload_for_path_filters_date_range_lists(self):
        dashboard = {
            "events": [
                ["2026-05-21", "Treasury auction", "中"],
                ["2026-06-17", "FOMC decision", "高"],
                ["2026-07-29", "FOMC decision", "高"],
            ]
        }

        status, payload = api_payload_for_path(
            dashboard,
            "/api/events",
            {"from": ["2026-06-01"], "to": ["2026-06-30"]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload, [["2026-06-17", "FOMC decision", "高"]])

    def test_api_response_for_path_can_export_csv(self):
        dashboard = {
            "events": [
                ["2026-05-21", "Treasury auction", "中"],
                ["2026-06-17", "FOMC decision", "高"],
            ]
        }

        status, body, content_type = api_response_for_path(dashboard, "/api/events", {"format": ["csv"]})

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/csv; charset=utf-8")
        self.assertIn("date,title,importance", body.decode("utf-8").splitlines()[0])
        self.assertIn("2026-06-17,FOMC decision,高", body.decode("utf-8"))

    def test_api_response_for_path_exports_curve_csv_by_tenor(self):
        dashboard = {
            "curve": {
                "tenors": ["2Y", "10Y"],
                "today": [4.13, 4.67],
                "w1": [4.0, 4.46],
                "m1": [3.71, 4.26],
                "d1": [0.06, 0.04],
            }
        }

        status, body, content_type = api_response_for_path(dashboard, "/api/curve", {"format": ["csv"]})

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/csv; charset=utf-8")
        self.assertIn("tenor,today,w1,m1,d1", body.decode("utf-8").splitlines()[0])
        self.assertIn("10Y,4.67,4.46,4.26,0.04", body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
