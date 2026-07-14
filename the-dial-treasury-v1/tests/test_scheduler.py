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
from unittest.mock import patch

from scripts import serve
from scripts.serve import NoStoreHandler, seconds_until_next_run, start_startup_update
from scripts.update_data import (
    FULL_REFRESH_DATA_MODE,
    OPTIONAL_LKG_SOURCE_STATUS_NAMES,
    REQUIRED_EQUITY_SOURCE_STATUS_NAMES,
    REQUIRED_FRED_SOURCE_STATUS_NAMES,
    full_refresh_source_issues,
    merge_last_known_good_blocks,
    run_update,
    write_failed_dashboard_json,
    write_dashboard_json,
)
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

    def full_refresh_dashboard(self, generated_at="2026-07-13T22:00:00+00:00"):
        dashboard = self.core_dashboard(generated_at)
        dashboard["asOf"] = "2026-07-13"
        dashboard["meta"] = {"dataMode": FULL_REFRESH_DATA_MODE}
        dashboard["macroLiquidity"].update(
            {
                "scoredFactorCount": 12,
                "effectiveWeightCoveragePct": 68,
            }
        )
        dashboard["sourceStatus"] = [
            {"name": "U.S. Treasury yield curve XML", "status": "ok", "latest": "2026-07-13"},
            *(
                {"name": name, "status": "ok", "latest": "2026-07-13"}
                for name in REQUIRED_FRED_SOURCE_STATUS_NAMES
            ),
            *(
                {"name": name, "status": "ok", "latest": "2026-07-13"}
                for name in REQUIRED_EQUITY_SOURCE_STATUS_NAMES
            ),
            *(
                {"name": name, "status": "ok", "latest": "2026-07-13"}
                for name in OPTIONAL_LKG_SOURCE_STATUS_NAMES
            ),
        ]
        return dashboard

    def test_seconds_until_next_run_uses_today_when_time_is_future(self):
        now = datetime(2026, 5, 20, 8, 30, 0)

        seconds = seconds_until_next_run("16:30", now=now)

        self.assertEqual(seconds, 8 * 60 * 60)

    def test_seconds_until_next_run_rolls_to_tomorrow_when_time_passed(self):
        now = datetime(2026, 5, 20, 17, 0, 0)

        seconds = seconds_until_next_run("16:30", now=now)

        self.assertEqual(seconds, int((datetime(2026, 5, 21, 16, 30) - now).total_seconds()))

    def test_equity_bar_timing_skips_observed_us_market_holidays(self):
        holiday = serve.equity_bar_timing(
            datetime(2026, 7, 3, 17, 0, tzinfo=serve.NEW_YORK_TZ)
        )
        monday_session = serve.equity_bar_timing(
            datetime(2026, 7, 6, 12, 0, tzinfo=serve.NEW_YORK_TZ)
        )

        self.assertEqual(holiday["phase"], "non_trading_day")
        self.assertEqual(holiday["expectedDate"].isoformat(), "2026-07-02")
        self.assertIsNone(holiday["readyAt"])
        self.assertEqual(monday_session["expectedDate"].isoformat(), "2026-07-02")
        self.assertEqual(monday_session["phase"], "trading_session")

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

    def test_non_finite_candidate_cannot_replace_valid_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            healthy = {"asOf": "2026-07-10", "score": 50.0}
            write_dashboard_json(healthy, output)

            with self.assertRaisesRegex(ValueError, "Out of range float values"):
                write_dashboard_json({"asOf": "2026-07-11", "score": float("nan")}, output)

            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), healthy)
            self.assertFalse(list(output.parent.glob(f".{output.name}.*.tmp")))

    def test_older_rejected_job_cannot_overwrite_newer_failure_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            newer = {"generatedAt": "2026-07-10T22:02:00+00:00", "reason": "newer"}
            older = {"generatedAt": "2026-07-10T22:01:00+00:00", "reason": "older"}

            write_failed_dashboard_json(newer, output)
            write_failed_dashboard_json(older, output)

            failed = json.loads(output.with_name("dashboard.failed.json").read_text(encoding="utf-8"))
            self.assertEqual(failed["reason"], "newer")

    def test_concurrent_dashboard_writes_remain_atomic_and_leave_no_shared_temp_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            barrier = threading.Barrier(3)
            payloads = [
                {"asOf": "2026-07-09", "blob": ["a" * 128 for _ in range(500)]},
                {"asOf": "2026-07-10", "blob": ["b" * 128 for _ in range(500)]},
            ]

            def writer(payload):
                barrier.wait(timeout=2)
                write_dashboard_json(payload, output)

            threads = [threading.Thread(target=writer, args=(payload,)) for payload in payloads]
            for thread in threads:
                thread.start()
            barrier.wait(timeout=2)
            for thread in threads:
                thread.join(timeout=2)

            published = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn(published, payloads)
            self.assertFalse(list(output.parent.glob(f".{output.name}.*.tmp")))

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

    def test_run_update_rejects_out_of_order_generated_at_and_as_of(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            healthy = self.core_dashboard("2026-05-25T12:00:00+00:00")
            healthy["asOf"] = "2026-05-24"
            write_dashboard_json(healthy, output)

            older_job = self.core_dashboard("2026-05-25T11:59:59+00:00")
            older_job["asOf"] = "2026-05-24"
            returned = run_update(output, build_func=lambda: older_job, save_history=False)
            self.assertEqual(returned["generatedAt"], healthy["generatedAt"])
            failed = json.loads(output.with_name("dashboard.failed.json").read_text(encoding="utf-8"))
            self.assertTrue(any("precedes served generatedAt" in issue for issue in failed["meta"]["refreshGate"]["issues"]))

            stale_observation = self.core_dashboard("2026-05-25T12:01:00+00:00")
            stale_observation["asOf"] = "2026-05-23"
            returned = run_update(output, build_func=lambda: stale_observation, save_history=False)
            self.assertEqual(returned["asOf"], "2026-05-24")
            failed = json.loads(output.with_name("dashboard.failed.json").read_text(encoding="utf-8"))
            self.assertTrue(any("candidate asOf" in issue for issue in failed["meta"]["refreshGate"]["issues"]))

    def test_history_failure_does_not_replace_served_dashboard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            healthy = self.core_dashboard("2026-05-25T12:00:00+00:00")
            candidate = self.core_dashboard("2026-05-25T12:01:00+00:00")
            write_dashboard_json(healthy, output)

            with patch("scripts.update_data.save_dashboard_history", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    run_update(output, build_func=lambda: candidate)

            served = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(served["generatedAt"], healthy["generatedAt"])

    def test_newer_rejected_candidate_is_visible_to_health_without_replacing_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            served = self.core_dashboard("2026-05-25T12:00:00+00:00")
            rejected = self.core_dashboard("2026-05-25T12:01:00+00:00")
            rejected.setdefault("meta", {})["refreshGate"] = {
                "status": "rejected",
                "issues": ["required source is stale"],
            }
            write_dashboard_json(served, output)
            write_dashboard_json(rejected, output.with_name("dashboard.failed.json"))

            warning = serve.rejected_refresh_warning(output, served)

            self.assertIsNotNone(warning)
            self.assertEqual(warning["scope"], "refresh_gate")
            self.assertIn("required source is stale", warning["detail"])

            newer_served = self.core_dashboard("2026-05-25T12:02:00+00:00")
            write_dashboard_json(newer_served, output)
            self.assertIsNone(serve.rejected_refresh_warning(output, newer_served))

    def test_server_health_treats_source_error_status_case_insensitively(self):
        payload = {"status": "ok", "sourceCounts": {}, "errors": []}
        serve.normalize_health_source_status(
            payload,
            {"sourceStatus": [{"name": "required feed", "status": " ERROR "}]},
        )

        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["sourceCounts"], {"error": 1})
        self.assertEqual(payload["errors"][0]["name"], "required feed")

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

    def test_full_refresh_source_gate_rejects_empty_source_status(self):
        dashboard = self.full_refresh_dashboard()
        dashboard["sourceStatus"] = []

        issues = full_refresh_source_issues(dashboard)

        self.assertIn("sourceStatus must contain full-refresh source rows", issues)

    def test_full_refresh_source_gate_rejects_missing_optional_monitoring_not_optional_errors(self):
        dashboard = self.full_refresh_dashboard()
        missing_name = OPTIONAL_LKG_SOURCE_STATUS_NAMES[0]
        dashboard["sourceStatus"] = [
            row for row in dashboard["sourceStatus"] if row.get("name") != missing_name
        ]

        issues = full_refresh_source_issues(dashboard)

        self.assertTrue(any("optional source monitoring incomplete" in issue for issue in issues))

        dashboard = self.full_refresh_dashboard()
        row = next(item for item in dashboard["sourceStatus"] if item["name"] == missing_name)
        row.update({"status": "error", "latest": "upstream timeout"})
        self.assertEqual(full_refresh_source_issues(dashboard), [])

    def test_run_update_keeps_existing_snapshot_when_full_refresh_loses_source_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            healthy = self.full_refresh_dashboard("2026-07-13T20:00:00+00:00")
            candidate = self.full_refresh_dashboard("2026-07-13T22:00:00+00:00")
            candidate["sourceStatus"] = []
            write_dashboard_json(healthy, output)

            dashboard = run_update(output, build_func=lambda: candidate, save_history=False)

            self.assertEqual(dashboard["generatedAt"], healthy["generatedAt"])
            failed = json.loads(output.with_name("dashboard.failed.json").read_text(encoding="utf-8"))
            self.assertEqual(failed["meta"]["refreshGate"]["status"], "rejected")
            self.assertTrue(failed["meta"]["refreshGate"]["issues"])

    def test_run_update_rejects_missing_fred_monitoring_row_but_allows_optional_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            healthy = self.full_refresh_dashboard("2026-07-13T20:00:00+00:00")
            missing_monitoring = self.full_refresh_dashboard("2026-07-13T22:00:00+00:00")
            missing_name = REQUIRED_FRED_SOURCE_STATUS_NAMES[-1]
            missing_monitoring["sourceStatus"] = [
                row for row in missing_monitoring["sourceStatus"] if row.get("name") != missing_name
            ]
            write_dashboard_json(healthy, output)

            rejected = run_update(output, build_func=lambda: missing_monitoring, save_history=False)

            self.assertEqual(rejected["generatedAt"], healthy["generatedAt"])
            failed = json.loads(output.with_name("dashboard.failed.json").read_text(encoding="utf-8"))
            self.assertTrue(any("FRED source monitoring incomplete" in issue for issue in failed["meta"]["refreshGate"]["issues"]))

            optional_error = self.full_refresh_dashboard("2026-07-13T23:00:00+00:00")
            optional_error["sourceStatus"].append(
                {"name": "CFTC financial futures COT", "status": "error", "latest": "timeout"}
            )
            published = run_update(output, build_func=lambda: optional_error, save_history=False)

            self.assertEqual(published["generatedAt"], optional_error["generatedAt"])
            self.assertIn(optional_error["generatedAt"], output.read_text(encoding="utf-8"))

    def test_full_refresh_source_gate_accepts_explicit_fred_curve_fallback(self):
        dashboard = self.full_refresh_dashboard()
        dashboard["sourceStatus"][0] = {
            "name": "U.S. Treasury yield curve XML",
            "status": "warning",
            "latest": "FRED DGS fallback through 2026-07-13",
            "source": "fred-fallback",
        }

        self.assertEqual(full_refresh_source_issues(dashboard), [])

    def test_full_refresh_source_gate_rejects_malformed_stale_or_future_curve_fallback_dates(self):
        cases = (
            ("FRED DGS fallback returned no dated observation", "not a valid ISO date"),
            ("FRED DGS fallback through 2026-07-08", "business days old"),
            ("FRED DGS fallback through 2026-07-14", "after generatedAt date"),
        )
        for latest, expected_issue in cases:
            with self.subTest(latest=latest):
                dashboard = self.full_refresh_dashboard()
                dashboard["sourceStatus"][0] = {
                    "name": "U.S. Treasury yield curve XML",
                    "status": "warning",
                    "latest": latest,
                    "source": "fred-fallback",
                }

                issues = full_refresh_source_issues(dashboard)

                self.assertTrue(any(expected_issue in issue for issue in issues), issues)

    def test_full_refresh_source_gate_rejects_malformed_stale_or_future_equity_dates(self):
        first_equity_name = REQUIRED_EQUITY_SOURCE_STATUS_NAMES[0]
        cases = (
            ("not-a-date", "not a valid ISO date"),
            ("2026-07-08", "business days old"),
            ("2026-07-14", "after generatedAt date"),
        )
        for latest, expected_issue in cases:
            with self.subTest(latest=latest):
                dashboard = self.full_refresh_dashboard()
                row = next(item for item in dashboard["sourceStatus"] if item["name"] == first_equity_name)
                row["latest"] = latest

                issues = full_refresh_source_issues(dashboard)

                self.assertTrue(any(expected_issue in issue for issue in issues), issues)

    def test_full_refresh_source_gate_validates_ok_fred_dates_without_requiring_every_series_to_succeed(self):
        fred_name = REQUIRED_FRED_SOURCE_STATUS_NAMES[-1]
        dashboard = self.full_refresh_dashboard()
        row = next(item for item in dashboard["sourceStatus"] if item["name"] == fred_name)
        row.update({"status": "error", "latest": "upstream timeout"})

        self.assertEqual(full_refresh_source_issues(dashboard), [])

        row.update({"status": "ok", "latest": "not-a-date"})
        self.assertTrue(
            any(f"{fred_name} latest observation" in issue for issue in full_refresh_source_issues(dashboard))
        )

        row["latest"] = "2026-07-14"
        self.assertTrue(
            any("after generatedAt date" in issue for issue in full_refresh_source_issues(dashboard))
        )

    def test_full_refresh_source_gate_rejects_invalid_snapshot_dates_and_duplicate_required_rows(self):
        dashboard = self.full_refresh_dashboard()
        dashboard["asOf"] = "not-a-date"
        dashboard["sourceStatus"].append(dict(dashboard["sourceStatus"][0]))

        issues = full_refresh_source_issues(dashboard)

        self.assertTrue(any("asOf must be an ISO date" in issue for issue in issues))
        self.assertTrue(any("source monitoring row is duplicated" in issue for issue in issues))

    def test_full_refresh_source_gate_rejects_low_current_factor_coverage(self):
        dashboard = self.full_refresh_dashboard()
        dashboard["macroLiquidity"]["scoredFactorCount"] = 4
        dashboard["macroLiquidity"]["effectiveWeightCoveragePct"] = 24

        issues = full_refresh_source_issues(dashboard)

        self.assertTrue(any("scoredFactorCount" in issue for issue in issues))
        self.assertTrue(any("effectiveWeightCoveragePct" in issue for issue in issues))

    def test_rejected_full_refresh_leaves_existing_snapshot_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            healthy = self.full_refresh_dashboard("2026-07-13T20:00:00+00:00")
            write_dashboard_json(healthy, output)
            original_bytes = output.read_bytes()
            rejected = self.full_refresh_dashboard("2026-07-13T22:00:00+00:00")
            rejected["sourceStatus"][0] = {
                "name": "U.S. Treasury yield curve XML",
                "status": "warning",
                "latest": "FRED DGS fallback through 2026-06-01",
                "source": "fred-fallback",
            }

            returned = run_update(output, build_func=lambda: rejected, save_history=False)

            self.assertEqual(returned["generatedAt"], healthy["generatedAt"])
            self.assertEqual(output.read_bytes(), original_bytes)
            failed = json.loads(output.with_name("dashboard.failed.json").read_text(encoding="utf-8"))
            self.assertEqual(failed["meta"]["refreshGate"]["status"], "rejected")
            self.assertTrue(any("business days old" in issue for issue in failed["meta"]["refreshGate"]["issues"]))

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

    def test_optional_source_blocks_use_explicit_last_known_good_cache(self):
        existing = {
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "globalLpplRisk": {"available": True, "asOf": "2026-07-10", "indices": [{"symbol": "SPY"}]},
            "regionalMonitor": {"available": True, "regions": [{"key": "us"}]},
        }
        candidate = {
            "generatedAt": "2026-07-13T01:00:00+00:00",
            "globalLpplRisk": {"available": False, "reason": "upstream timeout"},
            "regionalMonitor": {},
        }

        merged = merge_last_known_good_blocks(candidate, existing)

        self.assertTrue(merged["globalLpplRisk"]["available"])
        self.assertTrue(merged["regionalMonitor"]["available"])
        borrowed = {row["key"]: row for row in merged["meta"]["lastKnownGoodBlocks"]}
        self.assertEqual(borrowed["globalLpplRisk"]["status"], "stale-cache")
        self.assertEqual(borrowed["globalLpplRisk"]["sourceGeneratedAt"], existing["generatedAt"])

    def test_legitimate_empty_list_does_not_resurrect_stale_events_or_news(self):
        existing = {
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "events": [["2026-07-13", "old event", "高"]],
            "news": [["07/13", "Federal Reserve", "old news"]],
        }
        candidate = {
            "generatedAt": "2026-07-13T01:00:00+00:00",
            "events": [],
            "news": [],
            "sourceStatus": [
                {"name": "Federal Reserve FOMC calendar", "status": "ok", "latest": "none"},
                {"name": "FRED economic release calendar", "status": "ok", "latest": "none"},
                {"name": "BEA release schedule", "status": "ok", "latest": "none"},
                {"name": "Federal Reserve press release RSS", "status": "ok", "latest": "none"},
                {"name": "U.S. Treasury press releases", "status": "ok", "latest": "none"},
            ],
        }

        merged = merge_last_known_good_blocks(candidate, existing)

        self.assertEqual(merged["events"], [])
        self.assertEqual(merged["news"], [])
        self.assertNotIn("lastKnownGoodBlocks", merged.get("meta", {}))

    def test_missing_optional_source_monitoring_borrows_last_known_good_list(self):
        existing = {
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "events": [["2026-07-29", "FOMC decision", "高"]],
        }
        candidate = {
            "generatedAt": "2026-07-13T01:00:00+00:00",
            "events": [],
            "sourceStatus": [
                {"name": "FRED economic release calendar", "status": "ok", "latest": "2026-07-13"},
                {"name": "BEA release schedule", "status": "ok", "latest": "2026-07-13"},
            ],
        }

        merged = merge_last_known_good_blocks(candidate, existing)

        self.assertEqual(merged["events"], existing["events"])
        self.assertEqual(merged["meta"]["lastKnownGoodBlocks"][0]["key"], "events")

    def test_partial_aggregate_source_failure_preserves_complete_previous_block(self):
        existing = {
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "events": [["2026-07-29", "FOMC decision", "高"]],
        }
        candidate = {
            "generatedAt": "2026-07-13T01:00:00+00:00",
            "events": [["2026-07-31", "BEA release", "高"]],
            "sourceStatus": [
                {"name": "Federal Reserve FOMC calendar", "status": "warning", "latest": "timeout"},
                {"name": "FRED economic release calendar", "status": "ok", "latest": "2026-07-13"},
                {"name": "BEA release schedule", "status": "ok", "latest": "2026-07-13"},
            ],
        }

        merged = merge_last_known_good_blocks(candidate, existing)

        self.assertEqual(merged["events"], existing["events"])
        self.assertEqual(merged["meta"]["lastKnownGoodBlocks"][0]["key"], "events")

    def test_global_lppl_symbol_regression_borrows_dependency_group(self):
        existing = {
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "globalLpplRisk": {
                "available": True,
                "indices": [
                    {"symbol": "SPY", "available": True},
                    {"symbol": "QQQ", "available": True},
                ],
            },
            "regionalMonitor": {"available": True, "regions": [{"key": "us", "from": "old-global"}]},
            "portfolioOverview": {"available": True, "layers": [{"layer": "globalLppl", "from": "old-global"}]},
        }
        candidate = {
            "generatedAt": "2026-07-13T01:00:00+00:00",
            "globalLpplRisk": {
                "available": True,
                "indices": [{"symbol": "SPY", "available": True}],
            },
            "regionalMonitor": {"available": True, "regions": [{"key": "us", "from": "partial-global"}]},
            "portfolioOverview": {"available": True, "layers": [{"layer": "globalLppl", "from": "partial-global"}]},
        }

        merged = merge_last_known_good_blocks(candidate, existing)

        self.assertEqual(merged["globalLpplRisk"], existing["globalLpplRisk"])
        self.assertEqual(merged["regionalMonitor"], existing["regionalMonitor"])
        self.assertEqual(merged["portfolioOverview"], existing["portfolioOverview"])
        self.assertEqual(
            {row["key"] for row in merged["meta"]["lastKnownGoodBlocks"]},
            {"globalLpplRisk", "regionalMonitor", "portfolioOverview"},
        )

    def test_validation_factor_regression_during_fred_failure_borrows_portfolio_group(self):
        existing = {
            "generatedAt": "2026-07-10T22:00:00+00:00",
            "signalValidation": {
                "available": True,
                "factors": [{"id": "fed_net_liquidity"}, {"id": "vix"}],
            },
            "spyEarlyWarning": {"available": True, "score": 60.0, "from": "complete-validation"},
            "portfolioOverview": {"available": True, "layers": [{"from": "complete-validation"}]},
        }
        candidate = {
            "generatedAt": "2026-07-13T01:00:00+00:00",
            "signalValidation": {
                "available": True,
                "factors": [{"id": "fed_net_liquidity"}],
            },
            "spyEarlyWarning": {"available": True, "score": 20.0, "from": "partial-validation"},
            "portfolioOverview": {"available": True, "layers": [{"from": "partial-validation"}]},
            "sourceStatus": [{"name": "FRED VIXCLS", "status": "warning", "latest": "timeout"}],
        }

        merged = merge_last_known_good_blocks(candidate, existing)

        self.assertEqual(merged["signalValidation"], existing["signalValidation"])
        self.assertEqual(merged["spyEarlyWarning"], existing["spyEarlyWarning"])
        self.assertEqual(merged["portfolioOverview"], existing["portfolioOverview"])
        self.assertEqual(
            {row["key"] for row in merged["meta"]["lastKnownGoodBlocks"]},
            {"signalValidation", "spyEarlyWarning", "portfolioOverview"},
        )

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

    def test_dashboard_and_api_support_etag_conditional_requests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "data" / "dashboard.json"
            dashboard = self.core_dashboard()
            write_dashboard_json(dashboard, output)

            class ConditionalHandler(NoStoreHandler):
                dashboard_output = output

                def log_message(self, format, *args):  # noqa: A002
                    return

            server = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0),
                functools.partial(ConditionalHandler, directory=temp_dir),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for path in ("/data/dashboard.json", "/api/dashboard"):
                    first = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    first.request("GET", path)
                    first_response = first.getresponse()
                    first_body = first_response.read()
                    etag = first_response.getheader("ETag")
                    first.close()

                    second = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    second.request("GET", path, headers={"If-None-Match": etag})
                    second_response = second.getresponse()
                    second_body = second_response.read()
                    second.close()

                    self.assertEqual(first_response.status, 200)
                    self.assertTrue(first_body)
                    self.assertTrue(etag)
                    self.assertEqual(first_response.getheader("Cache-Control"), "private, no-cache, max-age=0")
                    self.assertEqual(second_response.status, 304)
                    self.assertEqual(second_body, b"")
                    self.assertEqual(second_response.getheader("ETag"), etag)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

    def test_etag_does_not_turn_error_responses_into_not_modified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_output = Path(temp_dir) / "data" / "missing-dashboard.json"

            class ConditionalErrorHandler(NoStoreHandler):
                dashboard_output = missing_output

                def log_message(self, format, *args):  # noqa: A002
                    return

            server = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0),
                functools.partial(ConditionalErrorHandler, directory=temp_dir),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for path, expected_status in (
                    ("/api/unknown-route", 404),
                    ("/data/dashboard.json", 500),
                ):
                    if expected_status == 404:
                        write_dashboard_json(
                            {
                                "asOf": "2026-07-10",
                                "generatedAt": "2026-07-13T00:00:00+00:00",
                                "sourceStatus": [],
                            },
                            missing_output,
                        )
                    else:
                        missing_output.unlink(missing_ok=True)
                    first = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    first.request("GET", path)
                    first_response = first.getresponse()
                    first_body = first_response.read()
                    etag = first_response.getheader("ETag")
                    first.close()

                    second = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    second.request("GET", path, headers={"If-None-Match": etag})
                    second_response = second.getresponse()
                    second_body = second_response.read()
                    second.close()

                    self.assertEqual(first_response.status, expected_status)
                    self.assertEqual(second_response.status, expected_status)
                    self.assertTrue(first_body)
                    self.assertEqual(second_body, first_body)
                    self.assertEqual(second_response.getheader("ETag"), etag)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

    def test_response_writer_ignores_normal_client_disconnects(self):
        class DisconnectingWriter:
            def __init__(self, error):
                self.error = error

            def write(self, _body):
                raise self.error

        for error in (BrokenPipeError("closed"), ConnectionResetError("reset")):
            with self.subTest(error=type(error).__name__):
                handler = object.__new__(NoStoreHandler)
                handler.command = "GET"
                handler.headers = {}
                handler.send_response = lambda _status: None
                handler.send_header = lambda _name, _value: None
                handler.end_headers = lambda: None
                handler.wfile = DisconnectingWriter(error)

                handler.write_bytes_response(200, b"payload", "application/json")


if __name__ == "__main__":
    unittest.main()
