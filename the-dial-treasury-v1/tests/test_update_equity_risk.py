import unittest
from datetime import date, datetime, timedelta, timezone

from scripts.update_equity_risk import build_updated_dashboard, dashboard_events_to_calendar_events
from treasury_data.build_dashboard import EQUITY_RISK_SYMBOLS
from treasury_data.sources import MarketDailyBar


class EquityRiskUpdateTests(unittest.TestCase):
    def make_bars(self, symbol: str, *, start_price: float = 100.0, days: int = 120) -> list[MarketDailyBar]:
        bars: list[MarketDailyBar] = []
        start = date(2026, 1, 2)
        price = start_price
        for index in range(days):
            day = start + timedelta(days=index)
            if day.weekday() >= 5:
                continue
            if index < 80:
                price *= 1.003
            elif index < 86:
                price *= 0.988 if symbol in {"SPY", "QQQ", "SMH", "XLK"} else 0.996
            else:
                price *= 1.001
            low = price * (0.985 if index in {82, 83, 84} else 0.995)
            bars.append(
                MarketDailyBar(
                    symbol=symbol,
                    date=day,
                    open=price * 0.998,
                    high=price * 1.004,
                    low=low,
                    close=price,
                    volume=1_000_000 + index * 1000,
                    source="unit-test",
                )
            )
        return bars

    def test_dashboard_events_to_calendar_events_converts_visible_event_rows(self):
        events = dashboard_events_to_calendar_events(
            {
                "events": [
                    ["2026-06-05", "BLS Employment Situation", "高"],
                    ["bad-date", "ignored", "高"],
                    ["2026-06-17", "", "高"],
                ]
            }
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].date, date(2026, 6, 5))
        self.assertEqual(events[0].title, "BLS Employment Situation")
        self.assertEqual(events[0].importance, "高")
        self.assertEqual(events[0].source, "dashboard events")

    def test_build_updated_dashboard_rebuilds_equity_risk_from_market_bars(self):
        dashboard = {
            "asOf": "2026-06-05",
            "generatedAt": "2026-06-07T09:09:09+00:00",
            "events": [["2026-04-29", "FOMC meeting", "高"]],
            "macroLiquidityEquity": {
                "currentSignal": {
                    "date": "2026-04-29",
                    "score3mChange": 7.5,
                    "levelBucket": "中位评分",
                    "changeBucket": "评分上行",
                }
            },
            "spyEarlyWarning": {"available": True, "score": 44.0, "regime": "Neutral"},
            "equityShortTermRisk": {
                "available": True,
                "trend": {"available": True, "points": [{"date": "2026-04-01", "score": 80.0, "spyClose": 100.0}]},
                "backtest": {"available": False, "sampleSize": 0},
            },
            "sourceStatus": [{"name": "Nasdaq SPY OHLCV", "status": "ok", "latest": "old"}],
        }
        market_bars = {
            symbol: self.make_bars(symbol, start_price=100 + offset * 5)
            for offset, symbol in enumerate(EQUITY_RISK_SYMBOLS)
        }

        updated = build_updated_dashboard(
            dashboard,
            market_bars,
            generated_at=datetime(2026, 6, 7, 10, 30, tzinfo=timezone.utc),
        )

        risk = updated["equityShortTermRisk"]
        self.assertTrue(risk["available"])
        self.assertTrue(risk["backtest"]["available"])
        self.assertGreaterEqual(len(risk["trend"]["points"]), 50)
        self.assertGreaterEqual(risk["backtest"]["sampleSize"], 45)
        self.assertEqual(updated["generatedAt"], "2026-06-07T10:30:00+00:00")
        self.assertTrue(any(row["name"] == "Nasdaq SPY OHLCV" and row["latest"] != "old" for row in updated["sourceStatus"]))


if __name__ == "__main__":
    unittest.main()
