import contextlib
import io
import unittest

from scripts.check_regional_alerts import main


class CheckRegionalAlertsTests(unittest.TestCase):
    def test_returns_zero_when_no_breach(self):
        def fetcher(url, timeout):
            return {
                "asOf": "2026-06-12",
                "regionalAlerts": {"available": True, "breached": [], "reduceRegions": ["korea"]},
            }

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--url", "x"], fetcher=fetcher, notifier=lambda t, m: None)
        self.assertEqual(code, 0)
        self.assertIn("REGIONAL OK", out.getvalue())
        self.assertIn("reduce=korea", out.getvalue())

    def test_returns_one_and_notifies_on_breach(self):
        notifications = []

        def fetcher(url, timeout):
            return {
                "asOf": "2026-06-12",
                "regionalAlerts": {
                    "available": True,
                    "breached": [
                        {"key": "korea", "nameCn": "韩国", "factorLabelCn": "已实现波动", "current": 43.0, "threshold": 12.0},
                    ],
                },
            }

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--notify"], fetcher=fetcher, notifier=lambda t, m: notifications.append((t, m)))
        self.assertEqual(code, 1)
        self.assertIn("REGIONAL BREACH", out.getvalue())
        self.assertIn("韩国", out.getvalue())
        self.assertEqual(len(notifications), 1)
        self.assertIn("地区因子突破告警", notifications[0][0])

    def test_returns_zero_without_regional_monitor(self):
        def fetcher(url, timeout):
            return {"asOf": "x", "status": "ok"}

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([], fetcher=fetcher, notifier=lambda t, m: None)
        self.assertEqual(code, 0)
        self.assertIn("no regional monitor data", out.getvalue())

    def test_returns_three_when_unreachable(self):
        def fetcher(url, timeout):
            raise OSError("connection refused")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([], fetcher=fetcher, notifier=lambda t, m: None)
        self.assertEqual(code, 3)
        self.assertIn("UNREACHABLE", out.getvalue())


if __name__ == "__main__":
    unittest.main()
