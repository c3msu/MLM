from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from treasury_data.history_backfill import fetch_public_history
from treasury_data.sources import TimeSeries, YieldCurveRecord, SeriesPoint


class HistoryBackfillTests(unittest.TestCase):
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
        self.assertEqual(meta["sourceErrors"], [{"name": "TreasuryDirect auctioned securities", "error": "auction timeout", "severity": "warning"}])
        self.assertTrue(any(row["category"] == "curve_yield" and row["name"] == "10Y收益率" for row in observations))
        self.assertTrue(any(row["category"] == "policy" and row["name"] == "EFFR" for row in observations))
        self.assertFalse(any(row["category"] == "auction" for row in observations))


if __name__ == "__main__":
    unittest.main()
