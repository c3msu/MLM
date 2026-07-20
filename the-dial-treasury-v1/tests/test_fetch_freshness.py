from __future__ import annotations

import unittest
from datetime import date

from treasury_data.fetch import (
    annotate_source_status_freshness,
    expected_source_cadence_days,
    parse_source_latest_date,
)


class SourceFreshnessPeriodTests(unittest.TestCase):
    def test_month_only_period_uses_month_end(self) -> None:
        self.assertEqual(parse_source_latest_date("2026-05"), date(2026, 5, 31))

    def test_embedded_full_date_preserves_the_exact_day(self) -> None:
        self.assertEqual(
            parse_source_latest_date("fallback through 2026-05-14; primary failed"),
            date(2026, 5, 14),
        )

    def test_latest_tic_period_is_not_mislabeled_stale(self) -> None:
        rows = [{"name": "Treasury TIC major foreign holders", "status": "ok", "latest": "2026-05"}]

        result = annotate_source_status_freshness(rows, as_of=date(2026, 7, 16))[0]

        self.assertEqual(result["observationPeriodEnd"], "2026-05-31")
        self.assertEqual(result["ageDays"], 46)
        self.assertEqual(result["status"], "ok")

    def test_fred_monthly_and_quarterly_periods_use_reference_period_end(self) -> None:
        rows = [
            {"name": "FRED PCEPI", "status": "ok", "latest": "2026-05-01"},
            {"name": "FRED GDPC1", "status": "ok", "latest": "2026-01-01"},
        ]

        monthly, quarterly = annotate_source_status_freshness(rows, as_of=date(2026, 7, 16))

        self.assertEqual(monthly["observationDate"], "2026-05-01")
        self.assertEqual(monthly["observationPeriodEnd"], "2026-05-31")
        self.assertEqual(monthly["freshnessBasis"], "observation-period-end")
        self.assertEqual(monthly["ageDays"], 46)
        self.assertEqual(monthly["expectedMaxAgeDays"], 65)
        self.assertEqual(monthly["status"], "ok")
        self.assertEqual(quarterly["observationPeriodEnd"], "2026-03-31")
        self.assertEqual(quarterly["ageDays"], 107)
        self.assertEqual(quarterly["expectedMaxAgeDays"], 130)
        self.assertEqual(quarterly["status"], "ok")

    def test_fred_cadence_groups_match_scoring_freshness_contract(self) -> None:
        self.assertEqual(expected_source_cadence_days("U.S. Treasury yield curve XML"), 7)
        self.assertEqual(expected_source_cadence_days("FRED VIXCLS"), 7)
        self.assertEqual(expected_source_cadence_days("FRED NFCI"), 14)
        self.assertEqual(expected_source_cadence_days("FRED CPIAUCSL"), 65)
        self.assertEqual(expected_source_cadence_days("FRED GDPC1"), 130)
        self.assertEqual(expected_source_cadence_days("Cboe SPY option open interest"), 7)

    def test_stale_fred_rows_no_longer_remain_ok(self) -> None:
        rows = [
            {"name": "FRED VIXCLS", "status": "ok", "latest": "2026-07-01"},
            {"name": "FRED WALCL", "status": "ok", "latest": "2026-06-24"},
            {"name": "FRED CPIAUCSL", "status": "ok", "latest": "2026-03-01"},
            {"name": "FRED GDPC1", "status": "ok", "latest": "2025-10-01"},
        ]

        result = annotate_source_status_freshness(rows, as_of=date(2026, 7, 17))

        self.assertTrue(all(row["status"] == "stale" for row in result))
        self.assertEqual([row["expectedMaxAgeDays"] for row in result], [7, 14, 65, 130])
        self.assertTrue(all("Latest observation" in row["note"] for row in result))

    def test_forward_calendar_latest_is_coverage_horizon_not_future_observation(self) -> None:
        rows = [
            {"name": "Federal Reserve FOMC calendar", "status": "ok", "latest": "2027-12-08"},
            {"name": "FRED economic release calendar", "status": "ok", "latest": "2026-12-15"},
            {"name": "BEA release schedule", "status": "ok", "latest": "2026-12-23"},
        ]

        result = annotate_source_status_freshness(rows, as_of=date(2026, 7, 20))

        for row in result:
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["freshnessBasis"], "calendar-horizon")
            self.assertEqual(row["coverageThrough"], row["latest"])
            self.assertTrue(row["calendarCoverageActive"])
            self.assertTrue(row["periodComplete"])
            self.assertNotIn("futureDays", row)

    def test_expired_forward_calendar_horizon_is_stale(self) -> None:
        row = {
            "name": "BEA release schedule",
            "status": "ok",
            "latest": "2026-07-17",
        }

        result = annotate_source_status_freshness([row], as_of=date(2026, 7, 20))[0]

        self.assertEqual(result["status"], "stale")
        self.assertFalse(result["calendarCoverageActive"])
        self.assertEqual(result["ageDays"], 3)
        self.assertIn("Calendar coverage ended", result["note"])

    def test_forward_calendar_reannotation_repairs_legacy_generic_future_error(self) -> None:
        row = {
            "name": "Federal Reserve FOMC calendar",
            "status": "error",
            "latest": "2027-12-08",
            "note": (
                "Source date/period ends after dashboard as-of by 506 days; "
                "row is not eligible for scoring."
            ),
        }

        result = annotate_source_status_freshness([row], as_of=date(2026, 7, 20))[0]

        self.assertEqual(result["status"], "ok")
        self.assertNotIn("note", result)
        self.assertEqual(result["freshnessBasis"], "calendar-horizon")


if __name__ == "__main__":
    unittest.main()
