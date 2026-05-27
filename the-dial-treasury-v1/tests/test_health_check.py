import contextlib
import io
import unittest

from scripts.check_health import main


class HealthCheckTests(unittest.TestCase):
    def test_main_returns_zero_for_ok_health(self):
        def fetcher(url, timeout):
            return {
                "status": "ok",
                "asOf": "2026-05-19",
                "generatedAt": "2026-05-20T14:36:24+00:00",
                "sourceCounts": {"ok": 36, "modeled": 1},
                "errors": [],
            }

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["--url", "http://127.0.0.1:8451/api/health"], fetcher=fetcher)

        self.assertEqual(exit_code, 0)
        self.assertIn("OK", stdout.getvalue())
        self.assertIn("ok=36", stdout.getvalue())

    def test_main_returns_two_for_degraded_health_and_can_notify(self):
        notifications = []

        def fetcher(url, timeout):
            return {
                "status": "degraded",
                "asOf": "2026-05-19",
                "generatedAt": "2026-05-20T14:36:24+00:00",
                "sourceCounts": {"ok": 35, "modeled": 1, "error": 1},
                "errors": [{"name": "TreasuryDirect auctioned securities", "status": "error", "latest": "timeout"}],
            }

        def notifier(title, message):
            notifications.append((title, message))

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["--notify"], fetcher=fetcher, notifier=notifier)

        self.assertEqual(exit_code, 2)
        self.assertIn("DEGRADED", stdout.getvalue())
        self.assertIn("TreasuryDirect auctioned securities", stdout.getvalue())
        self.assertEqual(len(notifications), 1)
        self.assertIn("Treasury dashboard degraded", notifications[0][0])

    def test_main_returns_two_for_history_backfill_warning(self):
        def fetcher(url, timeout):
            return {
                "status": "degraded",
                "asOf": "2026-05-22",
                "generatedAt": "2026-05-25T11:03:14+00:00",
                "sourceCounts": {"ok": 58, "modeled": 1},
                "errors": [],
                "warnings": [{"name": "TreasuryDirect auctioned securities", "latest": "curl timeout"}],
                "history": {
                    "latestBackfill": {
                        "status": "degraded",
                        "endDate": "2026-05-25",
                        "savedObservationCount": 64572,
                    }
                },
            }

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main([], fetcher=fetcher)

        self.assertEqual(exit_code, 2)
        self.assertIn("historyBackfill=degraded", stdout.getvalue())
        self.assertIn("TreasuryDirect auctioned securities", stdout.getvalue())

    def test_main_returns_three_when_health_endpoint_is_unreachable(self):
        def fetcher(url, timeout):
            raise TimeoutError("timed out")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main([], fetcher=fetcher)

        self.assertEqual(exit_code, 3)
        self.assertIn("UNREACHABLE", stdout.getvalue())
        self.assertIn("timed out", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
