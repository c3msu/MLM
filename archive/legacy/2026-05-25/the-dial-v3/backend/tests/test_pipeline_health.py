import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_service import DataService


class PipelineHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.data_dir = os.path.join(self.tmpdir.name, "data")
        self.service = DataService(self.db_path, self.data_dir)
        self.service.init_database()
        self.service.bootstrap_defaults()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _insert_raw_series(self, symbol: str, values: list[float]) -> None:
        conn = self.service._get_connection()
        cursor = conn.cursor()
        for idx, value in enumerate(values, start=1):
            cursor.execute(
                """
                INSERT OR REPLACE INTO raw_series
                (source, symbol, date, value, frequency, fetched_at, status)
                VALUES ('fred', ?, ?, ?, 'd', '2024-01-31T00:00:00', 'ok')
                """,
                (symbol, f"2024-01-{idx:02d}", value),
            )
        conn.commit()
        conn.close()

    def test_factor_layer_status_flags_seeded_missing_latest_with_raw_data(self):
        self._insert_raw_series("WALCL", [1.0, 2.0, 3.0, 4.0, 5.0])

        status = self.service.get_factor_layer_status()

        self.assertEqual(status["raw_series_rows"], 5)
        self.assertEqual(status["factor_series_rows"], 0)
        self.assertEqual(status["factor_latest_rows"], 47)
        self.assertEqual(status["factor_latest_missing"], 47)
        self.assertTrue(status["needs_rebuild"])

    def test_ensure_factor_layer_ready_rebuilds_from_existing_raw_data(self):
        self._insert_raw_series("WALCL", [1.0, 2.0, 3.0, 4.0, 5.0])

        report = self.service.ensure_factor_layer_ready()

        self.assertTrue(report["rebuilt"])
        self.assertGreaterEqual(report["factors"]["computed"], 1)

        conn = sqlite3.connect(self.db_path)
        factor_rows = conn.execute("SELECT COUNT(*) FROM factor_series").fetchone()[0]
        latest = conn.execute(
            """
            SELECT raw_value, score, data_status
            FROM factor_latest
            WHERE factor_id = 'liq_fed_balance_sheet'
            """
        ).fetchone()
        conn.close()

        self.assertGreater(factor_rows, 0)
        self.assertIsNotNone(latest)
        self.assertEqual(latest[0], 5.0)
        self.assertIsNotNone(latest[1])
        self.assertNotEqual(latest[2], "missing")

    def test_reconcile_interrupted_pipeline_runs_marks_old_running_runs_failed(self):
        self.service._create_pipeline_run("old-run")
        old_started_at = (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds")
        conn = self.service._get_connection()
        conn.execute(
            "UPDATE pipeline_runs SET started_at = ? WHERE run_id = 'old-run'",
            (old_started_at,),
        )
        conn.commit()
        conn.close()

        report = self.service.reconcile_interrupted_pipeline_runs(max_age_minutes=60)

        self.assertEqual(report["marked_failed"], 1)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status, finished_at, message FROM pipeline_runs WHERE run_id = 'old-run'"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "failed")
        self.assertIsNotNone(row[1])
        self.assertIn("interrupted", row[2])


if __name__ == "__main__":
    unittest.main()
