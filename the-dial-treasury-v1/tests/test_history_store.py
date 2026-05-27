import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from treasury_data.history_store import history_summary, list_dashboard_snapshots, save_dashboard_history
from treasury_data.history_store import (
    latest_history_backfill_run,
    historical_series_points,
    list_historical_series_stats,
    save_history_backfill_run,
    save_historical_observations,
)


class HistoryStoreTests(unittest.TestCase):
    def test_save_dashboard_history_persists_snapshot_and_key_metrics(self):
        dashboard = {
            "asOf": "2026-05-22",
            "generatedAt": "2026-05-24T11:45:10+00:00",
            "curve": {"tenors": ["2Y", "10Y"], "today": [4.13, 4.56], "d1": [0.05, -0.01]},
            "groups": [
                {
                    "id": "macro",
                    "name": "宏观基本面",
                    "factors": [
                        {"n": "CPI 通胀", "v": "超预期", "score": -2},
                        {"n": "劳动力市场", "v": "降温", "score": 1},
                    ],
                }
            ],
            "percentiles": {
                "items": [
                    {"name": "净流动性", "value": "$5.93T", "percentile": 13, "source": "FRED WALCL - WTREGEN - RRPONTSYD"},
                ]
            },
            "sourceStatus": [{"name": "FRED", "status": "ok", "latest": "2026-05-22"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"

            snapshot_id = save_dashboard_history(dashboard, db_path)

            self.assertTrue(db_path.exists())
            with closing(sqlite3.connect(db_path)) as connection:
                snapshot = connection.execute(
                    "select as_of, generated_at, payload_json from dashboard_snapshots where id = ?",
                    (snapshot_id,),
                ).fetchone()
                metric_rows = connection.execute(
                    "select category, name, value, text_value from metric_observations order by category, name",
                ).fetchall()

            self.assertEqual(snapshot[0], "2026-05-22")
            self.assertEqual(snapshot[1], "2026-05-24T11:45:10+00:00")
            self.assertEqual(json.loads(snapshot[2])["curve"]["today"][1], 4.56)
            self.assertIn(("curve_yield", "10Y", 4.56, None), metric_rows)
            self.assertIn(("factor_percentile", "净流动性", 13.0, "$5.93T"), metric_rows)
            self.assertIn(("factor_score", "CPI 通胀", -2.0, "超预期"), metric_rows)

    def test_save_dashboard_history_is_idempotent_for_same_snapshot(self):
        dashboard = {
            "asOf": "2026-05-22",
            "generatedAt": "2026-05-24T11:45:10+00:00",
            "curve": {"tenors": ["10Y"], "today": [4.56]},
            "sourceStatus": [{"name": "FRED", "status": "ok", "latest": "2026-05-22"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"

            first_id = save_dashboard_history(dashboard, db_path)
            second_id = save_dashboard_history(dashboard, db_path)
            summary = history_summary(db_path)
            snapshots = list_dashboard_snapshots(db_path)

            self.assertEqual(second_id, first_id)
            self.assertEqual(summary["snapshotCount"], 1)
            self.assertEqual(summary["metricCount"], 1)
            self.assertEqual(snapshots, [{"asOf": "2026-05-22", "generatedAt": "2026-05-24T11:45:10+00:00", "metricCount": 1}])

    def test_save_historical_observations_persists_five_year_series_and_stats(self):
        observations = [
            {"date": "2021-05-24", "category": "curve_yield", "name": "10Y收益率", "value": 1.62, "unit": "%", "source": "Treasury"},
            {"date": "2022-05-24", "category": "curve_yield", "name": "10Y收益率", "value": 2.76, "unit": "%", "source": "Treasury"},
            {"date": "2023-05-24", "category": "curve_yield", "name": "10Y收益率", "value": 3.74, "unit": "%", "source": "Treasury"},
            {"date": "2024-05-24", "category": "curve_yield", "name": "10Y收益率", "value": 4.47, "unit": "%", "source": "Treasury"},
            {"date": "2025-05-24", "category": "curve_yield", "name": "10Y收益率", "value": 4.51, "unit": "%", "source": "Treasury"},
            {"date": "2026-05-22", "category": "curve_yield", "name": "10Y收益率", "value": 4.56, "unit": "%", "source": "Treasury"},
            {"date": "2026-05-22", "category": "macro", "name": "VIX", "value": 16.8, "unit": "", "source": "FRED VIXCLS"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"

            inserted = save_historical_observations(observations, db_path)
            second_insert = save_historical_observations(observations, db_path)
            summary = history_summary(db_path)
            stats = list_historical_series_stats(db_path)
            points = historical_series_points(db_path, category="curve_yield", name="10Y收益率")

            self.assertEqual(inserted, 7)
            self.assertEqual(second_insert, 7)
            self.assertEqual(summary["historicalObservationCount"], 7)
            self.assertEqual(summary["historicalSeriesCount"], 2)
            self.assertEqual(summary["historicalStartDate"], "2021-05-24")
            self.assertEqual(summary["historicalEndDate"], "2026-05-22")
            ten_year = next(item for item in stats if item["name"] == "10Y收益率")
            self.assertEqual(ten_year["count"], 6)
            self.assertEqual(ten_year["min"], 1.62)
            self.assertEqual(ten_year["max"], 4.56)
            self.assertEqual(ten_year["latest"], 4.56)
            self.assertEqual(ten_year["p50"], 4.105)
            self.assertEqual(len(points), 6)
            self.assertEqual(points[-1]["date"], "2026-05-22")

    def test_save_history_backfill_run_tracks_source_errors_in_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            summary = {
                "startDate": "2021-05-25",
                "endDate": "2026-05-25",
                "observationCount": 64572,
                "savedObservationCount": 64572,
                "sourceErrors": [
                    {"name": "TreasuryDirect auctioned securities", "error": "curl timeout"},
                ],
            }

            run_id = save_history_backfill_run(summary, db_path, years=5)
            latest = latest_history_backfill_run(db_path)
            history = history_summary(db_path)

            self.assertEqual(run_id, 1)
            self.assertEqual(latest["status"], "degraded")
            self.assertEqual(latest["years"], 5)
            self.assertEqual(latest["startDate"], "2021-05-25")
            self.assertEqual(latest["endDate"], "2026-05-25")
            self.assertEqual(latest["savedObservationCount"], 64572)
            self.assertEqual(latest["sourceErrors"], [{"name": "TreasuryDirect auctioned securities", "error": "curl timeout"}])
            self.assertEqual(history["latestBackfill"], latest)

    def test_warning_only_history_backfill_run_keeps_status_ok(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            summary = {
                "startDate": "2021-05-25",
                "endDate": "2026-05-25",
                "observationCount": 64572,
                "savedObservationCount": 64572,
                "sourceErrors": [
                    {"name": "TreasuryDirect auctioned securities", "error": "curl timeout", "severity": "warning"},
                ],
            }

            save_history_backfill_run(summary, db_path, years=5)
            latest = latest_history_backfill_run(db_path)

            self.assertEqual(latest["status"], "ok")
            self.assertEqual(latest["sourceErrors"], [{"name": "TreasuryDirect auctioned securities", "error": "curl timeout", "severity": "warning"}])


if __name__ == "__main__":
    unittest.main()
