from __future__ import annotations

import json
import unittest
from datetime import date
from unittest.mock import patch

from treasury_data.fetch import annotate_source_status_freshness
from treasury_data.history_backfill import (
    LATEST_VINTAGE_SOURCE_SUFFIX,
    LATEST_VINTAGE_STATUS,
    build_historical_observations,
    fetch_public_history,
)
from treasury_data import sources
from treasury_data.sources import SeriesPoint, TimeSeries, YieldCurveRecord


class SourceFreshnessTimepointTests(unittest.TestCase):
    def test_future_observation_is_an_error_not_zero_age_fresh_data(self) -> None:
        row = {
            "name": "Nasdaq SPY OHLCV",
            "status": "ok",
            "latest": "2026-07-19",
        }

        result = annotate_source_status_freshness([row], as_of=date(2026, 7, 18))[0]

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["periodComplete"])
        self.assertEqual(result["futureDays"], 1)
        self.assertIn("not eligible for scoring", result["note"])

    def test_current_month_reference_period_is_incomplete_even_if_key_is_not_future(self) -> None:
        row = {
            "name": "FRED CPIAUCSL",
            "status": "ok",
            "latest": "2026-07-01",
        }

        result = annotate_source_status_freshness([row], as_of=date(2026, 7, 18))[0]

        self.assertEqual(result["observationPeriodEnd"], "2026-07-31")
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["periodComplete"])
        self.assertEqual(result["futureDays"], 13)


class SourceParserTimepointTests(unittest.TestCase):
    def test_fred_bulk_filters_future_rows_and_unfinished_low_frequency_periods(self) -> None:
        content = "\n".join(
            [
                "observation_date,DFF,CPIAUCSL,GDPC1",
                "2026-04-01,3.45,319.0,24000",
                "2026-06-01,3.50,320.0,.",
                "2026-07-01,3.55,321.0,24100",
                "2026-07-19,3.60,.,.",
            ]
        ).encode("utf-8")

        parsed = sources.parse_fred_bulk_zip(
            content,
            ["DFF", "CPIAUCSL", "GDPC1"],
            as_of=date(2026, 7, 18),
            complete_periods_only=True,
        )

        self.assertEqual(parsed["DFF"].latest.date, date(2026, 7, 1))
        self.assertEqual(parsed["CPIAUCSL"].latest.date, date(2026, 6, 1))
        # Q2 is complete by July 18; Q3, keyed July 1, is not.
        self.assertEqual(parsed["GDPC1"].latest.date, date(2026, 4, 1))

    def test_daily_bar_parsers_can_exclude_current_incomplete_session(self) -> None:
        stooq = "\n".join(
            [
                "Date,Open,High,Low,Close,Volume",
                "2026-07-17,100,102,99,101,1000",
                "2026-07-18,101,103,100,102,500",
            ]
        )
        nasdaq = json.dumps(
            {
                "data": {
                    "tradesTable": {
                        "rows": [
                            {"date": "07/18/2026", "open": "$101", "high": "$103", "low": "$100", "close": "$102", "volume": "500"},
                            {"date": "07/17/2026", "open": "$100", "high": "$102", "low": "$99", "close": "$101", "volume": "1000"},
                        ]
                    }
                }
            }
        )

        stooq_bars = sources.parse_stooq_daily_csv(stooq, "SPY", not_after=date(2026, 7, 17))
        nasdaq_bars = sources.parse_nasdaq_historical_json(nasdaq, "SPY", not_after=date(2026, 7, 17))

        self.assertEqual([bar.date for bar in stooq_bars], [date(2026, 7, 17)])
        self.assertEqual([bar.date for bar in nasdaq_bars], [date(2026, 7, 17)])
        self.assertEqual(
            sources.completed_daily_bar_through(date(2026, 7, 18), today=date(2026, 7, 18)),
            date(2026, 7, 17),
        )
        self.assertEqual(
            sources.completed_daily_bar_through(date(2026, 7, 16), today=date(2026, 7, 18)),
            date(2026, 7, 16),
        )

    def test_cboe_snapshot_requires_a_real_nonfuture_source_timestamp(self) -> None:
        payload = {
            "data": {
                "current_price": 620.0,
                "options": [
                    {"option": "SPY260717P00500000", "open_interest": 120, "volume": 10},
                    {"option": "SPY260717C00500000", "open_interest": 100, "volume": 8},
                ],
            }
        }
        with self.assertRaisesRegex(ValueError, "valid source timestamp"):
            sources.parse_cboe_option_open_interest_json(
                json.dumps(payload),
                "SPY",
                as_of=date(2026, 7, 18),
            )

        payload["timestamp"] = "2026-07-19T01:00:00Z"
        with self.assertRaisesRegex(ValueError, "future source timestamp"):
            sources.parse_cboe_option_open_interest_json(
                json.dumps(payload),
                "SPY",
                as_of=date(2026, 7, 18),
            )

        payload["timestamp"] = "2026-07-17T21:00:00Z"
        snapshot = sources.parse_cboe_option_open_interest_json(
            json.dumps(payload),
            "SPY",
            as_of=date(2026, 7, 18),
        )
        self.assertEqual(snapshot.as_of, date(2026, 7, 17))

    def test_curve_fetch_drops_future_dated_xml_records(self) -> None:
        records = [
            YieldCurveRecord(date(2026, 7, 18), {tenor: 4.0 for tenor in sources.TENORS}),
            YieldCurveRecord(date(2026, 7, 19), {tenor: 9.0 for tenor in sources.TENORS}),
        ]
        with patch.object(sources, "fetch_text", return_value="xml"), patch.object(
            sources,
            "parse_treasury_yield_xml",
            return_value=records,
        ):
            result = sources.fetch_treasury_yield_curves(today=date(2026, 7, 18), months_back=1)

        self.assertEqual([record.date for record in result], [date(2026, 7, 18)])


class HistoryBackfillVintageTests(unittest.TestCase):
    def test_fred_backfill_is_explicitly_non_point_in_time(self) -> None:
        observed = date(2026, 6, 30)
        fred = {
            "DFF": TimeSeries("DFF", [SeriesPoint(observed, 3.5)]),
        }
        curve = YieldCurveRecord(observed, {"10Y": 4.2})

        rows = build_historical_observations(
            [curve],
            fred,
            [],
            today=date(2026, 7, 18),
            years=1,
        )

        fred_row = next(row for row in rows if row.get("label") == "DFF")
        curve_row = next(row for row in rows if row.get("category") == "curve_yield")
        self.assertFalse(fred_row["validationEligible"])
        self.assertEqual(fred_row["vintageStatus"], LATEST_VINTAGE_STATUS)
        self.assertIn(LATEST_VINTAGE_SOURCE_SUFFIX, fred_row["source"])
        self.assertTrue(curve_row["validationEligible"])

    def test_public_history_pins_fred_fetch_to_requested_as_of_and_reports_revision_policy(self) -> None:
        captured: dict[str, object] = {}

        def fake_fred(_series_ids, **kwargs):
            captured.update(kwargs)
            return {"DFF": TimeSeries("DFF", [SeriesPoint(date(2026, 7, 17), 3.5)])}

        with patch("treasury_data.history_backfill.fetch_treasury_yield_curves", return_value=[]), patch(
            "treasury_data.history_backfill.fetch_fred_series_bulk",
            side_effect=fake_fred,
        ), patch("treasury_data.history_backfill.fetch_treasury_auctions", return_value=[]):
            rows, meta = fetch_public_history(today=date(2026, 7, 18), years=1)

        self.assertEqual(captured["as_of"], date(2026, 7, 18))
        self.assertGreater(meta["latestVintageObservationCount"], 0)
        self.assertIn("not an ALFRED point-in-time vintage", meta["revisionPolicy"])
        self.assertTrue(all(row["date"] <= "2026-07-18" for row in rows))


if __name__ == "__main__":
    unittest.main()
