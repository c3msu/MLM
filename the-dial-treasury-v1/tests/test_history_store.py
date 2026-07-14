import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import treasury_data.history_store as history_store
from treasury_data.history_store import (
    HistoryPayloadPolicy,
    connect,
    history_summary,
    list_dashboard_snapshots,
    load_dashboard_snapshot,
    save_dashboard_history,
)
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
                    "select as_of, generated_at, payload_encoding, length(payload_blob), payload_bytes from dashboard_snapshots where id = ?",
                    (snapshot_id,),
                ).fetchone()
                metric_rows = connection.execute(
                    "select category, name, value, text_value from metric_observations order by category, name",
                ).fetchall()

            self.assertEqual(snapshot[0], "2026-05-22")
            self.assertEqual(snapshot[1], "2026-05-24T11:45:10+00:00")
            self.assertEqual(snapshot[2], "zlib-json-v1")
            self.assertGreater(snapshot[3], 0)
            self.assertGreater(snapshot[4], snapshot[3])
            self.assertEqual(load_dashboard_snapshot(snapshot_id, db_path)["curve"]["today"][1], 4.56)
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

    def test_save_dashboard_history_rejects_same_identity_with_different_content(self):
        dashboard = {
            "asOf": "2026-05-22",
            "generatedAt": "2026-05-24T11:45:10+00:00",
            "curve": {"tenors": ["10Y"], "today": [4.56]},
            "sourceStatus": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            save_dashboard_history(dashboard, db_path)
            changed = {**dashboard, "curve": {"tenors": ["10Y"], "today": [4.57]}}

            with self.assertRaisesRegex(ValueError, "identity collision"):
                save_dashboard_history(changed, db_path)

    def test_payload_policy_compresses_recent_and_discards_only_old_bodies(self):
        policy = HistoryPayloadPolicy(compression="zlib", retain=2)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            snapshot_ids = []
            for hour in range(3):
                snapshot_ids.append(
                    save_dashboard_history(
                        {
                            "asOf": "2026-05-22",
                            "generatedAt": f"2026-05-24T{hour:02d}:00:00+00:00",
                            "curve": {"tenors": ["10Y"], "today": [4.5 + hour / 100]},
                            "sourceStatus": [{"name": "FRED", "status": "ok"}],
                            "largeAudit": [{"index": index, "text": "repeated-payload-value" * 20} for index in range(400)],
                        },
                        db_path,
                        payload_policy=policy,
                    )
                )

            with closing(sqlite3.connect(db_path)) as connection:
                rows = connection.execute(
                    "select id, payload_encoding, length(payload_blob), payload_bytes from dashboard_snapshots order by generated_at desc"
                ).fetchall()
                oldest_metrics = connection.execute(
                    "select count(*) from metric_observations where snapshot_id = ?",
                    (snapshot_ids[0],),
                ).fetchone()[0]

            self.assertEqual([row[1] for row in rows], ["zlib-json-v1", "zlib-json-v1", "discarded-v1"])
            self.assertTrue(all(row[2] < row[3] for row in rows[:2]))
            self.assertIsNone(load_dashboard_snapshot(snapshot_ids[0], db_path))
            self.assertEqual(load_dashboard_snapshot(snapshot_ids[-1], db_path)["curve"]["today"], [4.52])
            self.assertEqual(oldest_metrics, 1)
            self.assertEqual(history_summary(db_path)["payloadStorage"]["discardedCount"], 1)

    def test_compacted_snapshot_identity_remains_idempotent_and_collision_safe(self):
        policy = HistoryPayloadPolicy(compression="zlib", retain=1)
        old = {
            "asOf": "2026-05-22",
            "generatedAt": "2026-05-24T00:00:00+00:00",
            "curve": {"tenors": ["10Y"], "today": [4.50]},
        }
        new = {
            "asOf": "2026-05-22",
            "generatedAt": "2026-05-24T01:00:00+00:00",
            "curve": {"tenors": ["10Y"], "today": [4.51]},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            old_id = save_dashboard_history(old, db_path, payload_policy=policy)
            save_dashboard_history(new, db_path, payload_policy=policy)
            self.assertIsNone(load_dashboard_snapshot(old_id, db_path))

            self.assertEqual(save_dashboard_history(old, db_path, payload_policy=policy), old_id)
            changed = {**old, "curve": {"tenors": ["10Y"], "today": [9.99]}}
            with self.assertRaisesRegex(ValueError, "identity collision"):
                save_dashboard_history(changed, db_path, payload_policy=policy)

    def test_snapshot_order_and_retention_compare_timezone_aware_instants(self):
        policy = HistoryPayloadPolicy(compression="zlib", retain=1)
        actually_newer = {
            "asOf": "2026-05-24",
            "generatedAt": "2026-05-24T23:30:00-04:00",
            "curve": {"tenors": ["10Y"], "today": [4.60]},
        }
        lexically_newer_but_earlier = {
            "asOf": "2026-05-25",
            "generatedAt": "2026-05-25T01:00:00+00:00",
            "curve": {"tenors": ["10Y"], "today": [4.55]},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            newer_id = save_dashboard_history(actually_newer, db_path, payload_policy=policy)
            earlier_id = save_dashboard_history(lexically_newer_but_earlier, db_path, payload_policy=policy)

            self.assertIsNotNone(load_dashboard_snapshot(newer_id, db_path))
            self.assertIsNone(load_dashboard_snapshot(earlier_id, db_path))
            self.assertEqual(history_summary(db_path)["latest"]["generatedAt"], actually_newer["generatedAt"])
            self.assertEqual(list_dashboard_snapshots(db_path)[0]["generatedAt"], actually_newer["generatedAt"])

    def test_history_connections_enable_wal_and_busy_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            with closing(connect(db_path)) as connection:
                journal_mode = connection.execute("pragma journal_mode").fetchone()[0]
                busy_timeout = connection.execute("pragma busy_timeout").fetchone()[0]

            self.assertEqual(journal_mode.lower(), "wal")
            self.assertGreaterEqual(busy_timeout, 5_000)

    def test_existing_history_schema_is_migrated_in_place(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    create table dashboard_snapshots (
                      id integer primary key autoincrement,
                      as_of text not null,
                      generated_at text not null,
                      created_at text not null,
                      payload_json text not null,
                      source_status_json text not null,
                      unique(as_of, generated_at)
                    )
                    """
                )

            snapshot_id = save_dashboard_history(
                {
                    "asOf": "2026-05-22",
                    "generatedAt": "2026-05-24T11:45:10+00:00",
                    "curve": {"tenors": ["10Y"], "today": [4.56]},
                },
                db_path,
            )

            with closing(sqlite3.connect(db_path)) as connection:
                columns = {row[1] for row in connection.execute("pragma table_info(dashboard_snapshots)")}
            self.assertTrue({"payload_blob", "payload_encoding", "payload_bytes", "payload_hash"}.issubset(columns))
            self.assertEqual(load_dashboard_snapshot(snapshot_id, db_path)["curve"]["today"], [4.56])

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

    def test_historical_backfill_deduplicates_overlapping_source_pages(self):
        observations = [
            {"date": "2026-05-22", "category": "macro", "name": "VIX", "value": 16.0},
            {"date": "2026-05-22", "category": "macro", "name": "VIX", "value": 17.0},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            saved = save_historical_observations(observations, db_path)
            points = historical_series_points(db_path, category="macro", name="VIX")

        self.assertEqual(saved, 1)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["value"], 17.0)

    def test_series_stats_load_values_with_one_query_instead_of_n_plus_one(self):
        observations = [
            {
                "date": f"2026-05-{day:02d}",
                "category": "macro",
                "name": name,
                "value": day + offset,
                "source": "unit-test",
            }
            for name, offset in (("A", 0), ("B", 10), ("C", 20))
            for day in range(1, 10)
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            save_historical_observations(observations, db_path)
            queries = []
            real_connect = history_store.connect

            def traced_connect(path):
                connection = real_connect(path)
                connection.set_trace_callback(queries.append)
                return connection

            with patch("treasury_data.history_store.connect", side_effect=traced_connect):
                stats = list_historical_series_stats(db_path)

            value_queries = [query for query in queries if "with selected as" in query.lower()]
            self.assertEqual(len(stats), 3)
            self.assertEqual(len(value_queries), 1)

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
