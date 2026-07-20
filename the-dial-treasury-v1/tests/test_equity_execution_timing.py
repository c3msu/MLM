from __future__ import annotations

import unittest
from datetime import date, timedelta

from treasury_data.scoring_equity import (
    build_equity_short_term_risk_backtest,
    equity_forward_drawdown_lead_days,
    equity_forward_max_drawdown_pct,
    equity_forward_return_pct,
    equity_walk_forward_partition,
)
from treasury_data.sources import MarketDailyBar


def bar(
    session: date,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> MarketDailyBar:
    return MarketDailyBar(
        symbol="SPY",
        date=session,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1_000_000,
        source="unit-test",
    )


class EquityExecutionTimingTests(unittest.TestCase):
    def test_labels_start_at_next_open_and_exclude_untradeable_overnight_gap(self) -> None:
        sessions = [date(2026, 1, 5) + timedelta(days=index) for index in range(3)]
        bars = [
            bar(sessions[0], open_price=99.0, high=101.0, low=98.0, close=100.0),
            # The completed signal-day bar cannot trade the gap from 100 to 80.
            bar(sessions[1], open_price=80.0, high=83.0, low=79.0, close=82.0),
            bar(sessions[2], open_price=82.0, high=91.0, low=80.0, close=90.0),
        ]

        self.assertEqual(equity_forward_return_pct(bars, 0, 1), 2.5)
        self.assertEqual(equity_forward_max_drawdown_pct(bars, 0, 1), -1.25)
        self.assertIsNone(equity_forward_drawdown_lead_days(bars, 0, 1, -2.0))

    def test_backtest_exposes_decision_execution_and_exact_label_window(self) -> None:
        start = date(2026, 2, 2)
        bars: list[MarketDailyBar] = []
        prior_close = 100.0
        for index in range(20):
            session = start + timedelta(days=index)
            open_price = 90.0 if index == 1 else prior_close
            close = open_price + 1.0
            bars.append(
                bar(
                    session,
                    open_price=open_price,
                    high=close + 0.5,
                    low=open_price - 0.5,
                    close=close,
                )
            )
            prior_close = close

        result = build_equity_short_term_risk_backtest(
            [{"date": bars[0].date.isoformat(), "score": 80.0, "regime": "Strong Alert"}],
            bars,
        )

        self.assertTrue(result["available"])
        policy = result["decisionExecutionPolicy"]
        self.assertEqual(policy["signalDecisionPoint"], "afterSignalDateClose")
        self.assertEqual(policy["earliestExecutionPoint"], "nextTradingSessionOpen")
        self.assertEqual(policy["drawdownMetric"], "maximumAdverseExcursionFromExecutionOpen")
        self.assertFalse(policy["pathPeakToTroughDrawdown"])
        window = result["alertWindows"][0]
        self.assertEqual(window["decisionPoint"], "afterClose")
        self.assertEqual(window["executionPolicy"], "nextSessionOpen")
        self.assertEqual(window["executionDate"], bars[1].date.isoformat())
        self.assertEqual(window["executionOpen"], 90.0)
        self.assertEqual(window["labelStartDate15d"], bars[1].date.isoformat())
        self.assertEqual(window["labelEndDate15d"], bars[15].date.isoformat())

    def test_score_bucket_exposes_metric_specific_complete_denominators(self) -> None:
        start = date(2026, 4, 1)
        bars = [
            bar(
                start + timedelta(days=index),
                open_price=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
            )
            for index in range(20)
        ]
        result = build_equity_short_term_risk_backtest(
            [
                {"date": bars[0].date.isoformat(), "score": 50.0},
                {"date": bars[10].date.isoformat(), "score": 50.0},
            ],
            bars,
        )

        watch = next(row for row in result["scoreBuckets"] if row["label"] == "Watch")
        self.assertEqual(watch["count"], 2)
        self.assertEqual(watch["sampleSize5d"], 2)
        self.assertEqual(watch["sampleSize10d"], 1)
        self.assertEqual(watch["sampleSize15d"], 1)

    def test_training_label_touching_first_oos_signal_date_is_purged(self) -> None:
        start = date(2026, 3, 2)
        rows = []
        for index in range(10):
            signal_date = start + timedelta(days=index)
            label_end = start + timedelta(days=6 if index < 6 else 7)
            rows.append(
                {
                    "date": signal_date.isoformat(),
                    "score": 50.0,
                    "maxDrawdown15d": -1.0,
                    "labelStartDate15d": (signal_date + timedelta(days=1)).isoformat(),
                    "labelEndDate15d": label_end.isoformat(),
                }
            )

        eligible, training, out_sample, purge_count, rule = equity_walk_forward_partition(
            rows,
            horizon=15,
        )

        self.assertEqual(len(eligible), 10)
        self.assertEqual(out_sample[0]["date"], (start + timedelta(days=7)).isoformat())
        self.assertEqual(len(training), 6)
        self.assertEqual(purge_count, 1)
        self.assertIn("earlier than the OOS split date", rule)


if __name__ == "__main__":
    unittest.main()
