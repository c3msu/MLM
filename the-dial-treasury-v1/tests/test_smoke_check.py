import unittest

from scripts.smoke_check import validate_dashboard


class SmokeCheckTests(unittest.TestCase):
    def test_validate_dashboard_accepts_complete_real_public_snapshot(self):
        dashboard = {
            "asOf": "2026-05-19",
            "generatedAt": "2026-05-20T15:30:34+00:00",
            "meta": {"dataMode": "real-public-sources"},
            "sourceStatus": [
                {"name": "U.S. Treasury yield curve XML", "status": "ok", "latest": "2026-05-19"},
                {"name": "Stooq gold spot XAUUSD", "status": "ok", "latest": "2026-05-20"},
                {"name": "Fed path", "status": "modeled", "latest": "public futures proxy + curve/macro model"},
            ],
            "events": [
                ["2026-05-28", "BEA GDP (Second Estimate) and Corporate Profits, 1st Quarter 2026", "高"],
                ["2026-06-10", "BLS Consumer Price Index", "高"],
                ["2026-06-17", "FOMC decision + SEP", "高"],
                ["2026-08-05", "Treasury quarterly refunding statement", "高"],
            ],
            "news": [
                ["05/18", "U.S. Treasury", "Treasury International Capital Data for March"],
            ],
            "cross": {
                "inflation": [
                    ["黄金现货", "$4536.70", "Stooq XAUUSD"],
                ],
                "historySeries": [
                    {
                        "id": "risk",
                        "series": [
                            {"category": "risk", "name": "S&P 500", "label": "SP500"},
                        ],
                    },
                    {
                        "id": "inflation",
                        "series": [
                            {"category": "commodity", "name": "WTI原油", "label": "DCOILWTICO"},
                        ],
                    },
                ],
            },
        }

        self.assertEqual(validate_dashboard(dashboard), [])

    def test_validate_dashboard_reports_missing_core_requirements(self):
        dashboard = {
            "asOf": "2026-05-19",
            "generatedAt": "2026-05-20T15:30:34+00:00",
            "meta": {"dataMode": "static"},
            "sourceStatus": [{"name": "FRED", "status": "error", "latest": "timeout"}],
            "events": [],
            "news": [["05/19", "FRED", "10Y 4.67%"]],
            "cross": {"inflation": []},
        }

        issues = validate_dashboard(dashboard)

        self.assertIn("meta.dataMode is not real-public-sources", issues)
        self.assertIn("sourceStatus contains error rows", issues)
        self.assertIn("missing BEA event", issues)
        self.assertIn("missing official news headline", issues)
        self.assertIn("missing gold spot cross-market row", issues)
        self.assertIn("missing cross-market history series", issues)


if __name__ == "__main__":
    unittest.main()
