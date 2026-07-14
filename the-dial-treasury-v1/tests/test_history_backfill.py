from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from treasury_data.history_backfill import (
    build_historical_observations,
    derived_observations,
    fetch_public_history,
    fred_observations,
)
from treasury_data.sources import TimeSeries, YieldCurveRecord, SeriesPoint


class HistoryBackfillTests(unittest.TestCase):
    def test_rrp_history_keeps_official_billions_and_net_liquidity_converts_to_millions(self):
        observed = date(2026, 1, 15)
        fred = {
            "WALCL": TimeSeries("WALCL", [SeriesPoint(observed, 10_000.0)]),
            "WTREGEN": TimeSeries("WTREGEN", [SeriesPoint(observed, 2_000.0)]),
            "RRPONTSYD": TimeSeries("RRPONTSYD", [SeriesPoint(observed, 5.0)]),
        }

        raw_rows = fred_observations(fred, observed, observed)
        derived_rows = derived_observations(fred, observed, observed)
        raw_rrp = next(row for row in raw_rows if row["label"] == "RRPONTSYD")
        net_liquidity = next(row for row in derived_rows if row["label"] == "net_liquidity")

        self.assertEqual((raw_rrp["value"], raw_rrp["unit"]), (5.0, "$B"))
        self.assertEqual((net_liquidity["value"], net_liquidity["unit"]), (3_000.0, "$M"))

    def test_fetch_public_history_keeps_core_history_when_auction_source_fails(self):
        today = date(2026, 5, 22)
        curve_records = [
            YieldCurveRecord(date=today, values={"2Y": 4.13, "10Y": 4.56, "30Y": 5.07, "5Y": 4.27, "3M": 3.68})
        ]
        fred = {
            "DFF": TimeSeries("DFF", [SeriesPoint(today, 3.62)]),
            "IORB": TimeSeries("IORB", [SeriesPoint(today, 3.65)]),
            "SP500": TimeSeries("SP500", [SeriesPoint(today, 7473.47)]),
        }

        with patch("treasury_data.history_backfill.fetch_treasury_yield_curves", return_value=curve_records):
            with patch("treasury_data.history_backfill.fetch_fred_series_bulk", return_value=fred):
                with patch("treasury_data.history_backfill.fetch_treasury_auctions", side_effect=TimeoutError("auction timeout")):
                    observations, meta = fetch_public_history(today=today, years=5)

        self.assertGreater(len(observations), 0)
        self.assertEqual(meta["auctionRecordCount"], 0)
        self.assertEqual(len(meta["missingFredSeries"]), 35)
        self.assertEqual(meta["sourceErrors"][0]["name"], "FRED bulk history")
        self.assertEqual(meta["sourceErrors"][0]["severity"], "error")
        self.assertEqual(
            meta["sourceErrors"][-1],
            {"name": "TreasuryDirect auctioned securities", "error": "auction timeout", "severity": "warning"},
        )
        self.assertTrue(any(row["category"] == "curve_yield" and row["name"] == "10Y收益率" for row in observations))
        self.assertTrue(any(row["category"] == "policy" and row["name"] == "EFFR" for row in observations))
        self.assertFalse(any(row["category"] == "auction" for row in observations))

    def test_historical_build_deduplicates_revised_rows_at_sqlite_grain(self):
        observed = date(2026, 1, 15)
        first = YieldCurveRecord(observed, {"10Y": 4.0})
        revision = YieldCurveRecord(observed, {"10Y": 4.1})
        auctions = [
            {
                "auctionDate": observed.isoformat(),
                "securityTerm": "10-Year",
                "securityType": "Note",
                "bidToCoverRatio": "2.4",
            },
            {
                "auctionDate": observed.isoformat(),
                "securityTerm": "10-Year",
                "securityType": "Note",
                "bidToCoverRatio": "2.5",
            },
        ]

        rows = build_historical_observations(
            [first, revision],
            {},
            auctions,
            today=observed,
            years=1,
        )

        identities = [
            (row["date"], row["category"], row["name"], row["label"])
            for row in rows
        ]
        self.assertEqual(len(identities), len(set(identities)))
        curve = next(row for row in rows if row["category"] == "curve_yield")
        auction = next(row for row in rows if row["category"] == "auction")
        self.assertEqual(curve["value"], 4.1)
        self.assertEqual(auction["value"], 2.5)


if __name__ == "__main__":
    unittest.main()
