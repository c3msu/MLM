from __future__ import annotations

import unittest
from datetime import date, timedelta

from treasury_data.scoring_equity import (
    adaptive_parkinson_target_vol,
    equity_hot_stock_reversal_component,
    equity_market_flow_component,
    equity_qqq_tlt_rotation_component,
    equity_sector_rotation_component,
    equity_short_term_signal_at,
    equity_turnover_component,
    equity_vol_target_pressure_component,
)
from treasury_data.sources import MarketDailyBar


class EquityFactorMathIntegrityTests(unittest.TestCase):
    @staticmethod
    def trading_days(count: int, *, start: date = date(2026, 1, 2)) -> list[date]:
        days: list[date] = []
        cursor = start
        while len(days) < count:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += timedelta(days=1)
        return days

    @classmethod
    def bars(
        cls,
        symbol: str,
        count: int,
        *,
        daily_return: float = 0.001,
        final_return: float | None = None,
    ) -> list[MarketDailyBar]:
        rows: list[MarketDailyBar] = []
        close = 100.0
        for index, day in enumerate(cls.trading_days(count)):
            open_price = close
            step = final_return if final_return is not None and index == count - 1 else daily_return
            close = open_price * (1.0 + step)
            rows.append(
                MarketDailyBar(
                    symbol=symbol,
                    date=day,
                    open=open_price,
                    high=max(open_price, close) * 1.008,
                    low=min(open_price, close) * 0.992,
                    close=close,
                    volume=1_000_000 + index * 1_000,
                    source="unit-test",
                )
            )
        return rows

    def test_adaptive_target_requires_all_65_complete_22_day_windows(self) -> None:
        short = self.bars("SPY", 85)
        complete = self.bars("SPY", 86)

        self.assertIsNone(adaptive_parkinson_target_vol(short, short[-1].date))
        self.assertIsNotNone(adaptive_parkinson_target_vol(complete, complete[-1].date))

        incomplete_component = equity_vol_target_pressure_component(
            {"SPY": short, "QQQ": self.bars("QQQ", 85)},
            short[-1].date,
            weight=0.22,
        )
        self.assertTrue(incomplete_component["available"])
        self.assertFalse(incomplete_component["scaleComparable"])
        self.assertFalse(incomplete_component["metrics"]["targetVolSampleComplete"])
        self.assertEqual(incomplete_component["metrics"]["targetVolSource"], "diagnostic12pctFallback")
        self.assertIn("不绑定生产阈值", incomplete_component["detail"])

        diagnostic_bars = {
            symbol: self.bars(symbol, 85)
            for symbol in ("SPY", "QQQ", "SMH", "XLK", "TLT", "RSP", "IWM")
        }
        for symbol in ("NVDA", "AVGO", "AMD", "TSLA", "META", "MSFT", "AAPL", "AMZN", "GOOGL"):
            diagnostic_bars[symbol] = self.bars(symbol, 85)
        diagnostic_signal = equity_short_term_signal_at(
            diagnostic_bars,
            diagnostic_bars["SPY"][-1].date,
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )
        self.assertEqual(diagnostic_signal["scoreScale"]["missingCoreComponents"], ["volTargetPressure"])
        self.assertFalse(diagnostic_signal["scoreScale"]["thresholdComparable"])
        self.assertFalse(diagnostic_signal["actionable"])
        self.assertIsNone(diagnostic_signal["allocation"]["exposureBandPct"])

        complete_component = equity_vol_target_pressure_component(
            {"SPY": complete, "QQQ": self.bars("QQQ", 86)},
            complete[-1].date,
            weight=0.22,
        )
        self.assertTrue(complete_component["available"])
        self.assertTrue(complete_component["scaleComparable"])
        self.assertTrue(complete_component["metrics"]["targetVolSampleComplete"])

    def test_cross_sectional_daily_factors_reject_mixed_session_bars(self) -> None:
        bars = {
            symbol: self.bars(symbol, 90)
            for symbol in ("SPY", "QQQ", "TLT", "SMH", "XLK", "RSP")
        }
        target = bars["SPY"][-1].date
        bars["QQQ"] = bars["QQQ"][:-1]

        self.assertFalse(equity_vol_target_pressure_component(bars, target, weight=0.22)["available"])
        self.assertFalse(equity_qqq_tlt_rotation_component(bars, target, weight=0.14)["available"])
        self.assertFalse(equity_market_flow_component(bars, target, weight=0.22)["available"])
        self.assertFalse(equity_sector_rotation_component(bars, target, weight=0.06)["available"])

        stale_spy = {"SPY": bars["SPY"][:-1]}
        self.assertFalse(equity_turnover_component(stale_spy, target, weight=0.14)["available"])

    def test_qqq_tlt_rotation_requires_its_63_day_crowding_leg(self) -> None:
        short = {"QQQ": self.bars("QQQ", 63), "TLT": self.bars("TLT", 63)}
        complete = {"QQQ": self.bars("QQQ", 64), "TLT": self.bars("TLT", 64)}

        self.assertFalse(equity_qqq_tlt_rotation_component(short, short["QQQ"][-1].date, weight=0.14)["available"])
        self.assertTrue(equity_qqq_tlt_rotation_component(complete, complete["QQQ"][-1].date, weight=0.14)["available"])

    def test_fixed_candidates_must_pass_point_in_time_heat_gate(self) -> None:
        cold_amd = self.bars("AMD", 70, daily_return=-0.003, final_return=-0.02)
        cold = equity_hot_stock_reversal_component({"AMD": cold_amd}, cold_amd[-1].date, weight=0.18)

        self.assertEqual(cold["metrics"]["sampleSize"], 1)
        self.assertEqual(cold["metrics"]["hotCount"], 0)
        self.assertEqual(cold["metrics"]["reversalCount"], 0)
        self.assertEqual(cold["score"], 20.0)

        hot_amd = self.bars("AMD", 70, daily_return=0.004, final_return=-0.02)
        hot = equity_hot_stock_reversal_component({"AMD": hot_amd}, hot_amd[-1].date, weight=0.18)
        self.assertEqual(hot["metrics"]["hotCount"], 1)
        self.assertEqual(hot["metrics"]["reversalCount"], 1)

    def test_stale_hot_candidate_is_excluded_instead_of_replayed_as_today(self) -> None:
        current_cold = self.bars("GOOGL", 90, daily_return=-0.001)
        stale_amd = self.bars("AMD", 90, daily_return=0.004, final_return=-0.04)[:-1]
        target = current_cold[-1].date

        component = equity_hot_stock_reversal_component(
            {"GOOGL": current_cold, "AMD": stale_amd},
            target,
            weight=0.18,
        )

        self.assertTrue(component["available"])
        self.assertEqual(component["metrics"]["sampleSize"], 1)
        self.assertEqual(component["metrics"]["hotCount"], 0)
        self.assertEqual(component["metrics"]["reversalCount"], 0)

    def test_stale_core_symbol_makes_score_non_actionable(self) -> None:
        symbols = ("SPY", "QQQ", "SMH", "XLK", "TLT", "RSP", "IWM")
        bars = {symbol: self.bars(symbol, 90) for symbol in symbols}
        for symbol in ("NVDA", "AVGO", "AMD", "TSLA", "META", "MSFT", "AAPL", "AMZN", "GOOGL"):
            bars[symbol] = self.bars(symbol, 90)
        target = bars["SPY"][-1].date
        bars["QQQ"] = bars["QQQ"][:-1]

        signal = equity_short_term_signal_at(
            bars,
            target,
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertTrue(signal["available"])
        self.assertFalse(signal["actionable"])
        self.assertFalse(signal["scoreScale"]["coreComplete"])
        self.assertTrue(
            {"volTargetPressure", "qqqTltRotation", "marketFlow", "sectorRotation"}.issubset(
                set(signal["scoreScale"]["missingCoreComponents"])
            )
        )
        self.assertIsNone(signal["allocation"]["exposureBandPct"])


if __name__ == "__main__":
    unittest.main()
