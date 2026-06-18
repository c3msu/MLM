import unittest
import math
from contextlib import ExitStack
from datetime import date, datetime, timezone
from unittest.mock import patch

import treasury_data.build_dashboard as dashboard_builder
from treasury_data.build_dashboard import (
    apply_content_overrides,
    build_conclusion_audit,
    build_dashboard_from_inputs,
    build_equity_short_term_risk_backtest,
    build_equity_short_term_risk_index,
    build_events,
    equity_qqq_tlt_rotation_component,
    equity_short_term_signal_at,
    equity_market_flow_component,
    equity_vol_target_pressure_component,
    compute_tenor_realized_volatility,
    historical_percentile,
    parse_bhadial_public_score,
)
from treasury_data.sources import (
    AcmRecord,
    CalendarEvent,
    CftcTreasuryPosition,
    DebtLimitStatus,
    FomcProjection,
    MarketDailyBar,
    MarketQuote,
    NewsItem,
    OptionOpenInterestSnapshot,
    PrimaryDealerStats,
    QuarterlyRefunding,
    SeriesPoint,
    TicHolding,
    TicHoldings,
    TimeSeries,
    YieldCurveRecord,
)


class DashboardBuilderTests(unittest.TestCase):
    def make_equity_bars(
        self,
        symbol: str,
        *,
        start_price: float,
        pre_event_return: float,
        june4_return: float,
        june5_return: float,
        volume_base: int = 50_000_000,
        june4_volume_multiplier: float = 1.0,
    ) -> list[MarketDailyBar]:
        days: list[date] = []
        cursor = date(2026, 3, 2)
        while cursor <= date(2026, 6, 5):
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += dashboard_builder.timedelta(days=1)
        pre_days = [day for day in days if day < date(2026, 6, 4)]
        daily_return = (1 + pre_event_return) ** (1 / max(len(pre_days) - 1, 1)) - 1
        close = start_price
        bars: list[MarketDailyBar] = []
        for index, day in enumerate(days):
            if index == 0:
                day_return = 0.0
            elif day == date(2026, 6, 4):
                day_return = june4_return
            elif day == date(2026, 6, 5):
                day_return = june5_return
            else:
                day_return = daily_return
            open_price = close
            close = close * (1 + day_return)
            high = max(open_price, close) * (1.006 if day == date(2026, 6, 4) and june4_return < 0 else 1.003)
            low = min(open_price, close) * (0.997 if day == date(2026, 6, 4) else 0.998)
            volume = int(volume_base * (1 + (index % 5) * 0.03))
            if day == date(2026, 6, 4):
                volume = int(volume_base * june4_volume_multiplier)
            bars.append(
                MarketDailyBar(
                    symbol=symbol,
                    date=day,
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=volume,
                    source="unit-test",
                )
            )
        return bars

    def make_equity_bars_from_closes(
        self,
        symbol: str,
        closes: list[float],
        *,
        start: date = date(2025, 2, 3),
        volume_base: int = 50_000_000,
        last_volume_multiplier: float = 1.0,
    ) -> list[MarketDailyBar]:
        days: list[date] = []
        cursor = start
        while len(days) < len(closes):
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += dashboard_builder.timedelta(days=1)
        bars: list[MarketDailyBar] = []
        for index, (day, close) in enumerate(zip(days, closes)):
            open_price = closes[index - 1] if index else close
            high = max(open_price, close) * 1.004
            low = min(open_price, close) * 0.996
            volume = int(volume_base * (1 + (index % 7) * 0.04))
            if index == len(closes) - 1:
                volume = int(volume_base * last_volume_multiplier)
            bars.append(
                MarketDailyBar(
                    symbol=symbol,
                    date=day,
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=volume,
                    source="unit-test",
                )
            )
        return bars

    def make_equity_bars_from_closes_and_ranges(
        self,
        symbol: str,
        closes: list[float],
        ranges: list[float],
        *,
        start: date = date(2025, 2, 3),
        volume_base: int = 50_000_000,
    ) -> list[MarketDailyBar]:
        days: list[date] = []
        cursor = start
        while len(days) < len(closes):
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += dashboard_builder.timedelta(days=1)
        bars: list[MarketDailyBar] = []
        for index, (day, close, day_range) in enumerate(zip(days, closes, ranges)):
            open_price = closes[index - 1] if index else close
            high = max(open_price, close) * (1 + max(day_range, 0.001) / 2)
            low = min(open_price, close) * (1 - max(day_range, 0.001) / 2)
            bars.append(
                MarketDailyBar(
                    symbol=symbol,
                    date=day,
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=int(volume_base * (1 + (index % 5) * 0.05)),
                    source="unit-test",
                )
            )
        return bars

    def idea_indicators(self, **overrides):
        indicators = {
            "cpi_yoy": 3.8,
            "pce_yoy": 3.5,
            "core_pce_yoy": 3.2,
            "trimmed_mean_pce_yoy": 2.4,
            "ppi_yoy": 3.1,
            "two_year_m1_change_bp": 34.0,
            "s5s30": 80.0,
            "two_year": 4.13,
            "sofr": 3.51,
            "dff": 3.62,
            "breakeven_10y": 2.40,
            "wti": 112.25,
            "wti_shock": 0.18,
        }
        indicators.update(overrides)
        return indicators

    def test_historical_percentile_ranks_latest_value_against_available_history(self):
        self.assertEqual(historical_percentile(4.0, [1.0, 2.0, 3.0, 4.0]), 100)
        self.assertEqual(historical_percentile(1.0, [1.0, 2.0, 3.0, 4.0]), 0)
        self.assertEqual(historical_percentile(2.0, [1.0, 2.0, 3.0, 4.0]), 33)
        self.assertIsNone(historical_percentile(2.0, [2.0]))

    def test_build_ideas_adds_duration_when_disinflation_and_policy_repricing_align(self):
        ideas = dashboard_builder.build_ideas(
            self.idea_indicators(
                cpi_yoy=2.3,
                pce_yoy=2.2,
                core_pce_yoy=2.3,
                trimmed_mean_pce_yoy=2.2,
                ppi_yoy=1.8,
                two_year_m1_change_bp=-32.0,
            ),
            macro_liquidity={"score": 62.0, "regime": "偏松"},
        )

        self.assertEqual(ideas[0]["title"], "加回久期")
        self.assertEqual(ideas[0]["tag"], "LONG 久期")
        self.assertIn("反通胀", ideas[0]["text"])
        self.assertNotIn("仍对久期不友好", ideas[0]["text"])
        for idea in ideas:
            self.assertEqual(idea["horizon"], "3-6M")
            self.assertEqual(idea["horizonCn"], "3-6个月")

    def test_build_ideas_does_not_chase_steepeners_after_curve_is_already_steep_and_qra_light(self):
        qra = QuarterlyRefunding(
            release_date=date(2026, 5, 1),
            quarter="Q2 2026",
            policy_statement_url="https://home.treasury.gov/qra",
            financing_estimates_url=None,
            next_policy_statement_date=date(2026, 8, 5),
            next_financing_estimates_date=None,
            next_quarter_borrowing_billions=300.0,
        )
        ideas = dashboard_builder.build_ideas(
            self.idea_indicators(s5s30=112.0),
            macro_liquidity={"score": 51.0, "regime": "中性"},
            quarterly_refunding=qra,
        )

        self.assertEqual(ideas[1]["tag"], "CURVE 观望")
        self.assertIn("不追", ideas[1]["text"])
        self.assertNotEqual(ideas[1]["title"], "做陡 5s30s 曲线")

    def test_build_ideas_marks_front_end_carry_as_less_feasible_when_cuts_are_priced(self):
        ideas = dashboard_builder.build_ideas(
            self.idea_indicators(two_year=3.10, dff=4.20, sofr=4.10, two_year_m1_change_bp=-48.0),
            macro_liquidity={"score": 58.0, "regime": "偏松"},
        )

        self.assertEqual(ideas[2]["tag"], "FRONT-END 谨慎")
        self.assertIn("降息预期", ideas[2]["text"])
        self.assertNotIn("现金替代", ideas[2]["text"])

    def test_build_ideas_reduces_breakeven_when_inflation_cools_and_bei_is_rich(self):
        ideas = dashboard_builder.build_ideas(
            self.idea_indicators(
                cpi_yoy=2.2,
                pce_yoy=2.1,
                core_pce_yoy=2.2,
                trimmed_mean_pce_yoy=2.1,
                ppi_yoy=1.7,
                breakeven_10y=2.68,
                wti=64.0,
                wti_shock=-0.16,
            ),
            macro_liquidity={"score": 60.0, "regime": "偏松"},
        )

        self.assertEqual(ideas[3]["tag"], "RV 降通胀补偿")
        self.assertIn("降温", ideas[3]["text"])
        self.assertNotEqual(ideas[3]["title"], "战术做多盈亏平衡通胀")

    def test_build_ideas_surfaces_conclusion_audit_confidence(self):
        ideas = dashboard_builder.build_ideas(
            self.idea_indicators(),
            macro_liquidity={"score": 43.4, "regime": "偏紧"},
            conclusion_audit={
                "confidence": {
                    "level": "low",
                    "label": "低",
                    "evidenceQuality": 0.58,
                    "proxyContributionShare": 0.42,
                    "concentration": 0.71,
                },
                "weightRecommendation": "代理或模型因子占比偏高,应降低观点强度。",
            },
        )

        self.assertTrue(all(idea["confidenceLevel"] == "low" for idea in ideas))
        self.assertTrue(all(idea["confidenceLabel"] == "低可信" for idea in ideas))
        self.assertIn("证据质量 0.58", ideas[0]["confidenceNote"])
        self.assertIn("代理/模型占比 42%", ideas[0]["confidenceNote"])
        self.assertIn("降低观点强度", ideas[0]["confidenceNote"])

    def test_build_ideas_adds_historical_spy_proxy_impact_from_similar_states(self):
        rows = []
        for index in range(18):
            rows.append(
                {
                    "date": f"2024-{index + 1:02d}-28" if index < 12 else f"2025-{index - 11:02d}-28",
                    "liquidityScore": 35 + index,
                    "score3mChange": -6 + index,
                    "forward1m": [-1.0, 0.0, 1.0, 2.0, 3.0, 4.0][index] if index < 6 else 0.5,
                    "forward3m": [-3.0, -1.0, 0.5, 2.5, 4.0, 6.0][index] if index < 6 else 1.0,
                    "forward6m": [-4.0, -2.0, 2.0, 4.0, 6.0, 8.0][index] if index < 6 else 2.0,
                    "forward3mMaxDrawdown": [-8.0, -7.0, -6.0, -5.0, -4.0, -3.0][index] if index < 6 else -2.0,
                }
            )
        ideas = dashboard_builder.build_ideas(
            self.idea_indicators(),
            macro_liquidity={"score": 43.4, "regime": "偏紧"},
            macro_liquidity_equity={
                "available": True,
                "currentSignal": {"levelBucket": "低评分", "changeBucket": "评分下行", "confidence": "medium"},
                "series": rows,
            },
        )

        impact = ideas[0]["equityImpact"]
        self.assertEqual(impact["proxy"], "S&P 500 price-index proxy for SPY")
        self.assertEqual(impact["basis"], "同类宏观评分水平 + 3M评分变化")
        self.assertEqual(impact["sampleSize"], 6)
        self.assertEqual(impact["forward1mMedian"], 1.5)
        self.assertEqual(impact["forward3mMedian"], 1.5)
        self.assertEqual(impact["forward6mMedian"], 3.0)
        self.assertEqual(impact["hitRate3m"], 67)
        self.assertEqual(impact["confidence"], "medium")
        self.assertIn("历史同类环境", impact["summary"])
        self.assertNotIn("预测", impact["summary"])

    def test_build_ideas_marks_spy_proxy_impact_unavailable_when_history_sample_is_small(self):
        ideas = dashboard_builder.build_ideas(
            self.idea_indicators(),
            macro_liquidity={"score": 43.4, "regime": "偏紧"},
            macro_liquidity_equity={
                "available": True,
                "currentSignal": {"levelBucket": "低评分", "changeBucket": "评分下行"},
                "series": [
                    {
                        "date": "2024-01-31",
                        "liquidityScore": 35.0,
                        "score3mChange": -5.0,
                        "forward1m": 1.0,
                        "forward3m": 2.0,
                        "forward6m": 3.0,
                    }
                ],
            },
        )

        impact = ideas[0]["equityImpact"]
        self.assertFalse(impact["available"])
        self.assertEqual(impact["sampleSize"], 0)
        self.assertIn("样本不足", impact["summary"])

    def test_build_spy_early_warning_de_risks_when_high_score_environment_rolls_over(self):
        macro_liquidity = {
            "score": 58.0,
            "components": [
                {"id": "fed_net_liquidity", "module": "Liquidity", "name": "净流动性", "score": 35.0, "value": "$5.60T"},
                {"id": "bank_reserves", "module": "Liquidity", "name": "银行准备金", "score": 42.0, "value": "$3.00T"},
                {"id": "cp_tbill_spread", "module": "Funding", "name": "商票-TBill利差", "score": 18.0, "value": "+55bp"},
                {"id": "dgs10_vol_21d", "module": "Treasury", "name": "10Y收益率波动率(21D)", "score": 25.0, "value": "120bp ann."},
                {"id": "real_rate_level", "module": "Rates", "name": "真实利率水平", "score": 30.0, "value": "2.10%"},
                {"id": "nfci", "module": "Credit", "name": "金融条件指数(NFCI)", "score": 12.0, "value": "+0.20"},
                {"id": "vix", "module": "Risk", "name": "VIX", "score": 20.0, "value": "31.0"},
                {"id": "dxy", "module": "External", "name": "美元广义指数", "score": 28.0, "value": "126.0"},
                {"id": "wti", "module": "External", "name": "WTI原油冲击", "score": 15.0, "value": "$108.0"},
            ],
        }
        macro_liquidity_equity = {
            "available": True,
            "observationCount": 54,
            "currentSignal": {
                "date": "2026-02-27",
                "score": 58.0,
                "score3mChange": -7.5,
                "levelBucket": "高评分",
                "changeBucket": "评分下行",
                "expectedForward3m": -4.73,
                "expectedDrawdown3m": -9.22,
                "hitRate": 14,
                "confidence": "medium",
            },
        }

        warning = dashboard_builder.build_spy_early_warning(macro_liquidity, macro_liquidity_equity)

        self.assertTrue(warning["available"])
        self.assertGreaterEqual(warning["score"], 75)
        self.assertEqual(warning["regime"], "De-risk")
        self.assertEqual(warning["allocation"]["stance"], "减仓/保护")
        self.assertIn("高评分环境转弱", warning["summary"])
        self.assertTrue(any(item["key"] == "macroDeterioration" and item["score"] >= 75 for item in warning["sleeves"]))
        self.assertTrue(any("VIX" in item["name"] for item in warning["drivers"]))
        self.assertEqual(warning["backtest"]["target"], "3M SPX drawdown and negative forward-return warning")

    def test_build_spy_early_warning_stays_neutral_when_low_score_environment_is_improving(self):
        macro_liquidity = {
            "score": 42.2,
            "components": [
                {"id": "fed_net_liquidity", "module": "Liquidity", "name": "净流动性", "score": 12.0, "value": "$5.87T"},
                {"id": "bank_reserves", "module": "Liquidity", "name": "银行准备金", "score": 17.0, "value": "$3.07T"},
                {"id": "cp_tbill_spread", "module": "Funding", "name": "商票-TBill利差", "score": 28.0, "value": "+15bp"},
                {"id": "dgs30_dgs10", "module": "Treasury", "name": "30Y-10Y期限溢价", "score": 5.0, "value": "52bp"},
                {"id": "real_curve", "module": "Rates", "name": "真实曲线(10Y-5Y)", "score": 29.0, "value": "-12bp"},
                {"id": "nfci", "module": "Credit", "name": "金融条件指数(NFCI)", "score": 74.0, "value": "-0.51"},
                {"id": "vix", "module": "Risk", "name": "VIX", "score": 77.0, "value": "15.32"},
                {"id": "dxy", "module": "External", "name": "美元广义指数", "score": 74.0, "value": "118.88"},
                {"id": "wti", "module": "External", "name": "WTI原油冲击", "score": 6.0, "value": "$97.63"},
                {"id": "ovx_dev", "module": "External", "name": "原油波动偏离", "score": 9.0, "value": "20.09"},
            ],
        }
        macro_liquidity_equity = {
            "available": True,
            "observationCount": 54,
            "currentSignal": {
                "date": "2026-06-01",
                "score": 42.2,
                "score3mChange": 6.7,
                "levelBucket": "中位评分",
                "changeBucket": "评分上行",
                "expectedForward3m": 5.24,
                "expectedDrawdown3m": -3.69,
                "hitRate": 89,
                "confidence": "medium",
            },
        }

        warning = dashboard_builder.build_spy_early_warning(macro_liquidity, macro_liquidity_equity)

        self.assertTrue(warning["available"])
        self.assertLess(warning["score"], 60)
        self.assertEqual(warning["regime"], "Neutral")
        self.assertEqual(warning["allocation"]["stance"], "持有/控仓")
        self.assertIn("改善", warning["summary"])
        self.assertTrue(any(item["key"] == "macroDeterioration" and item["score"] <= 25 for item in warning["sleeves"]))
        self.assertTrue(any(item["key"] == "externalShock" and item["score"] >= 60 for item in warning["sleeves"]))

    def test_build_spy_early_warning_amplifies_severe_three_month_rollover(self):
        macro_liquidity = {
            "score": 45.3,
            "components": [
                {"id": "fed_net_liquidity", "module": "Liquidity", "name": "净流动性", "score": 50.0, "value": "$6.00T"},
                {"id": "cp_tbill_spread", "module": "Funding", "name": "商票-TBill利差", "score": 50.0, "value": "+20bp"},
                {"id": "real_rate_level", "module": "Rates", "name": "真实利率水平", "score": 50.0, "value": "1.75%"},
                {"id": "vix", "module": "Risk", "name": "VIX", "score": 50.0, "value": "22.0"},
                {"id": "dxy", "module": "External", "name": "美元广义指数", "score": 50.0, "value": "120.0"},
            ],
        }
        macro_liquidity_equity = {
            "available": True,
            "observationCount": 54,
            "currentSignal": {
                "date": "2022-03-31",
                "score": 45.3,
                "score3mChange": -14.3,
                "levelBucket": "中位评分",
                "changeBucket": "评分下行",
                "expectedForward3m": None,
                "expectedDrawdown3m": None,
                "confidence": "history",
            },
        }

        warning = dashboard_builder.build_spy_early_warning(macro_liquidity, macro_liquidity_equity)

        self.assertTrue(warning["available"])
        self.assertGreaterEqual(warning["score"], 65)
        self.assertIn(warning["regime"], {"Caution", "De-risk"})
        self.assertIn("amplifiers", warning)
        self.assertTrue(any(item["key"] == "severeDeterioration" for item in warning["amplifiers"]))

    def test_spy_warning_history_buckets_ignore_future_rows(self):
        rows = [
            {"date": "2025-01-31", "liquidityScore": 40.0, "score3mChange": -1.0},
            {"date": "2025-02-28", "liquidityScore": 45.0, "score3mChange": -2.0},
            {"date": "2025-03-31", "liquidityScore": 50.0, "score3mChange": 1.0},
            {"date": "2025-04-30", "liquidityScore": 90.0, "score3mChange": 9.0},
            {"date": "2025-05-31", "liquidityScore": 95.0, "score3mChange": 10.0},
            {"date": "2025-06-30", "liquidityScore": 99.0, "score3mChange": 12.0},
        ]

        signal = dashboard_builder.spy_warning_signal_for_history_row(rows[2], rows)

        # As of 2025-03-31 the score 50 is the highest observed so far; if future
        # rows leaked into the rank it would fall back to the middle bucket.
        self.assertEqual(signal["levelBucket"], "高评分")
        self.assertEqual(signal["changeBucket"], "评分上行")

    def test_build_spy_early_warning_dampens_post_selloff_non_severe_low_score(self):
        macro_liquidity = {
            "score": 40.6,
            "components": [
                {"id": "fed_net_liquidity", "module": "Liquidity", "name": "净流动性", "score": 50.0, "value": "$6.00T"},
                {"id": "cp_tbill_spread", "module": "Funding", "name": "商票-TBill利差", "score": 50.0, "value": "+20bp"},
                {"id": "real_rate_level", "module": "Rates", "name": "真实利率水平", "score": 50.0, "value": "1.75%"},
                {"id": "vix", "module": "Risk", "name": "VIX", "score": 50.0, "value": "22.0"},
                {"id": "dxy", "module": "External", "name": "美元广义指数", "score": 50.0, "value": "120.0"},
            ],
        }
        macro_liquidity_equity = {
            "available": True,
            "observationCount": 54,
            "currentSignal": {
                "date": "2022-06-30",
                "score": 40.6,
                "score3mChange": -4.7,
                "sp500Trailing3m": -16.45,
                "levelBucket": "低评分",
                "changeBucket": "评分下行",
                "expectedForward3m": None,
                "expectedDrawdown3m": None,
                "confidence": "history",
            },
        }

        warning = dashboard_builder.build_spy_early_warning(macro_liquidity, macro_liquidity_equity)

        self.assertTrue(warning["available"])
        self.assertLess(warning["score"], 60)
        self.assertEqual(warning["regime"], "Neutral")
        self.assertIn("dampeners", warning)
        self.assertTrue(any(item["key"] == "postSelloffExhaustion" for item in warning["dampeners"]))
        # fragileLowScore was zeroed by the 2026-06-12 OOS audit (lift 0.59,
        # fired ahead of +5.39% avg forward 3M); it must no longer appear.
        self.assertFalse(any(item["key"] == "fragileLowScore" for item in warning["amplifiers"]))

    def test_build_spy_early_warning_keeps_severe_deterioration_after_selloff(self):
        macro_liquidity = {
            "score": 38.9,
            "components": [
                {"id": "fed_net_liquidity", "module": "Liquidity", "name": "净流动性", "score": 50.0, "value": "$6.00T"},
                {"id": "cp_tbill_spread", "module": "Funding", "name": "商票-TBill利差", "score": 50.0, "value": "+20bp"},
                {"id": "real_rate_level", "module": "Rates", "name": "真实利率水平", "score": 50.0, "value": "1.75%"},
                {"id": "vix", "module": "Risk", "name": "VIX", "score": 50.0, "value": "22.0"},
                {"id": "dxy", "module": "External", "name": "美元广义指数", "score": 50.0, "value": "120.0"},
            ],
        }
        macro_liquidity_equity = {
            "available": True,
            "observationCount": 54,
            "currentSignal": {
                "date": "2022-04-29",
                "score": 38.9,
                "score3mChange": -11.8,
                "sp500Trailing3m": -8.5,
                "levelBucket": "低评分",
                "changeBucket": "评分下行",
                "expectedForward3m": None,
                "expectedDrawdown3m": None,
                "confidence": "history",
            },
        }

        warning = dashboard_builder.build_spy_early_warning(macro_liquidity, macro_liquidity_equity)

        self.assertTrue(warning["available"])
        self.assertGreaterEqual(warning["score"], 75)
        self.assertEqual(warning["regime"], "De-risk")
        self.assertTrue(any(item["key"] == "severeDeterioration" for item in warning["amplifiers"]))
        self.assertFalse(any(item["key"] == "postSelloffExhaustion" for item in warning["dampeners"]))

    def test_build_spy_early_warning_amplifies_late_cycle_rally_rollover(self):
        macro_liquidity = {
            "score": 43.4,
            "components": [
                {"id": "fed_net_liquidity", "module": "Liquidity", "name": "净流动性", "score": 50.0, "value": "$6.00T"},
                {"id": "cp_tbill_spread", "module": "Funding", "name": "商票-TBill利差", "score": 50.0, "value": "+20bp"},
                {"id": "real_rate_level", "module": "Rates", "name": "真实利率水平", "score": 50.0, "value": "1.75%"},
                {"id": "vix", "module": "Risk", "name": "VIX", "score": 50.0, "value": "22.0"},
                {"id": "dxy", "module": "External", "name": "美元广义指数", "score": 50.0, "value": "120.0"},
            ],
        }
        macro_liquidity_equity = {
            "available": True,
            "observationCount": 54,
            "currentSignal": {
                "date": "2023-07-31",
                "score": 43.4,
                "score3mChange": -2.4,
                "sp500Trailing3m": 10.06,
                "levelBucket": "中位评分",
                "changeBucket": "评分下行",
                "expectedForward3m": None,
                "expectedDrawdown3m": None,
                "confidence": "history",
            },
        }

        warning = dashboard_builder.build_spy_early_warning(macro_liquidity, macro_liquidity_equity)

        self.assertTrue(warning["available"])
        # 2026-06-12 OOS audit: rallyFragility halved to +3 (kept for its negative
        # forward-return signal), lateCycleRallyRollover zeroed (3 fires, 0% hit).
        self.assertLess(warning["score"], 60)
        self.assertEqual(warning["regime"], "Neutral")
        rally_fragility = next(item for item in warning["amplifiers"] if item["key"] == "rallyFragility")
        self.assertEqual(rally_fragility["scoreBoost"], 3.0)
        self.assertFalse(any(item["key"] == "lateCycleRallyRollover" for item in warning["amplifiers"]))

    def test_build_spy_early_warning_amplifies_stalled_low_score_recovery(self):
        macro_liquidity = {
            "score": 40.3,
            "components": [
                {"id": "fed_net_liquidity", "module": "Liquidity", "name": "净流动性", "score": 50.0, "value": "$6.00T"},
                {"id": "cp_tbill_spread", "module": "Funding", "name": "商票-TBill利差", "score": 50.0, "value": "+20bp"},
                {"id": "real_rate_level", "module": "Rates", "name": "真实利率水平", "score": 50.0, "value": "1.75%"},
                {"id": "vix", "module": "Risk", "name": "VIX", "score": 50.0, "value": "22.0"},
                {"id": "dxy", "module": "External", "name": "美元广义指数", "score": 50.0, "value": "120.0"},
            ],
        }
        macro_liquidity_equity = {
            "available": True,
            "observationCount": 54,
            "currentSignal": {
                "date": "2025-01-31",
                "score": 40.3,
                "score3mChange": 0.4,
                "sp500Trailing3m": 5.87,
                "levelBucket": "低评分",
                "changeBucket": "变化不大",
                "expectedForward3m": None,
                "expectedDrawdown3m": None,
                "confidence": "history",
            },
        }

        warning = dashboard_builder.build_spy_early_warning(macro_liquidity, macro_liquidity_equity)

        self.assertTrue(warning["available"])
        # Both low-score amplifiers were zeroed by the 2026-06-12 OOS audit
        # (fragileLowScore lift 0.59; lowScoreStall fired once in five years).
        self.assertLess(warning["score"], 60)
        self.assertEqual(warning["regime"], "Neutral")
        self.assertFalse(any(item["key"] == "fragileLowScore" for item in warning["amplifiers"]))
        self.assertFalse(any(item["key"] == "lowScoreStall" for item in warning["amplifiers"]))

    def test_build_conclusion_audit_scales_factor_contribution_by_group_size_and_source_quality(self):
        groups = [
            {
                "id": "g1",
                "name": "货币政策",
                "en": "Policy",
                "weight": 60,
                "factors": [
                    {"n": "真实政策因子", "score": -2, "curve": 1, "v": "偏紧"},
                    {"n": "代理政策因子", "score": -2, "curve": 0, "v": "偏紧", "sourceMode": "proxy-public"},
                ],
            },
            {
                "id": "g2",
                "name": "宏观基本面",
                "en": "Macro",
                "weight": 40,
                "factors": [
                    {"n": "模型路径", "score": 2, "curve": -1, "v": "反向", "sourceMode": "modeled"},
                    {"n": "中性因子", "score": 0, "curve": 0, "v": "中性"},
                ],
            },
        ]

        audit = build_conclusion_audit(groups, source_status=[{"name": "TreasuryDirect", "status": "warning"}])

        self.assertAlmostEqual(audit["duration"]["score"], -0.8)
        self.assertAlmostEqual(audit["curve"]["score"], 0.1)
        self.assertEqual(audit["confidence"]["level"], "medium")
        self.assertLess(audit["confidence"]["evidenceQuality"], 0.9)
        self.assertEqual(audit["sourceWarningCount"], 1)
        drivers = {item["name"]: item for item in audit["drivers"]}
        self.assertAlmostEqual(drivers["真实政策因子"]["contribution"], -0.6)
        self.assertAlmostEqual(drivers["代理政策因子"]["contribution"], -0.6)
        self.assertAlmostEqual(drivers["模型路径"]["contribution"], 0.4)
        self.assertIn("代理", audit["weightRecommendation"])

    def test_build_dashboard_adds_bhadial_style_historical_percentiles(self):
        curve_records = [
            YieldCurveRecord(
                date=date(2026, 4, 18),
                values={"1M": 3.69, "3M": 3.70, "6M": 3.69, "1Y": 3.64, "2Y": 3.71, "3Y": 3.72, "5Y": 3.84, "7Y": 4.04, "10Y": 4.26, "20Y": 4.85, "30Y": 4.88},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 18),
                values={"1M": 3.69, "3M": 3.68, "6M": 3.77, "1Y": 3.81, "2Y": 4.07, "3Y": 4.14, "5Y": 4.27, "7Y": 4.43, "10Y": 4.61, "20Y": 5.14, "30Y": 5.14},
            ),
        ]
        fred = {
            "WALCL": TimeSeries("WALCL", [SeriesPoint(date(2021 + i, 5, 1), 6_000_000.0 + i * 100_000) for i in range(6)]),
            "WTREGEN": TimeSeries("WTREGEN", [SeriesPoint(date(2021 + i, 5, 1), 700_000.0) for i in range(6)]),
            "RRPONTSYD": TimeSeries("RRPONTSYD", [SeriesPoint(date(2021 + i, 5, 1), 100_000.0) for i in range(6)]),
            "WRESBAL": TimeSeries(
                "WRESBAL",
                [
                    SeriesPoint(date(2021, 5, 1), 2_000_000.0),
                    SeriesPoint(date(2022, 5, 1), 2_100_000.0),
                    SeriesPoint(date(2023, 5, 1), 2_050_000.0),
                    SeriesPoint(date(2024, 5, 1), 2_200_000.0),
                    SeriesPoint(date(2025, 5, 1), 2_080_000.0),
                    SeriesPoint(date(2026, 5, 1), 2_300_000.0),
                ],
            ),
            "SOFR": TimeSeries("SOFR", [SeriesPoint(date(2021 + i, 5, 1), 3.50 + i * 0.02) for i in range(6)]),
            "DFF": TimeSeries("DFF", [SeriesPoint(date(2021 + i, 5, 1), 3.45) for i in range(6)]),
        }
        auctions = [
            {"auctionDate": "2026-05-01", "securityTerm": "10-Year", "securityType": "Note", "bidToCoverRatio": "2.10"},
            {"auctionDate": "2026-05-08", "securityTerm": "10-Year", "securityType": "Note", "bidToCoverRatio": "2.50"},
            {"auctionDate": "2026-05-15", "securityTerm": "10-Year", "securityType": "Note", "bidToCoverRatio": "3.00"},
        ]

        dashboard = build_dashboard_from_inputs(
            curve_records=curve_records,
            fred=fred,
            auctions=auctions,
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )

        percentile_names = {item["name"] for item in dashboard["percentiles"]["items"]}
        self.assertIn("银行准备金", percentile_names)
        self.assertIn("净流动性", percentile_names)
        self.assertIn("SOFR-EFFR利差", percentile_names)
        self.assertIn("拍卖投标倍数", percentile_names)
        all_factors = [factor for group in dashboard["groups"] for factor in group["factors"]]
        factor_by_name = {factor["n"]: factor for factor in all_factors}
        self.assertIn("历史p", factor_by_name["银行准备金"]["tag"])
        self.assertIn("历史p", factor_by_name["净流动性"]["tag"])
        self.assertIn("历史p", factor_by_name["SOFR-EFFR利差"]["tag"])
        self.assertEqual(factor_by_name["拍卖需求"]["score"], 1)
        self.assertIn("历史p", factor_by_name["拍卖需求"]["tag"])
        trend_by_name = {trend["name"]: trend for trend in dashboard["percentiles"]["trends"]}
        self.assertIn("银行准备金", trend_by_name)
        self.assertIn("净流动性", trend_by_name)
        self.assertIn("SOFR-EFFR利差", trend_by_name)
        self.assertIn("拍卖投标倍数", trend_by_name)
        self.assertGreaterEqual(len(trend_by_name["银行准备金"]["points"]), 2)
        self.assertGreaterEqual(trend_by_name["银行准备金"]["points"][0]["date"], "2023-05-01")
        self.assertIn("percentile", trend_by_name["银行准备金"]["points"][-1])
        self.assertTrue(any(item["name"] == "银行准备金" and item["change"] > 0 for item in dashboard["percentiles"]["movers"]))
        self.assertTrue(any(item["name"] == "拍卖投标倍数" and item["percentile"] == 100 for item in dashboard["percentiles"]["alerts"]))

    def test_build_dashboard_fills_bhadial_module_factor_gaps_with_public_data(self):
        curve_records = [
            YieldCurveRecord(
                date=date(2026, 4, 27),
                values={"1M": 3.64, "3M": 3.63, "6M": 3.66, "1Y": 3.68, "2Y": 3.82, "3Y": 3.90, "5Y": 4.04, "7Y": 4.22, "10Y": 4.40, "20Y": 4.90, "30Y": 4.95},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 18),
                values={"1M": 3.69, "3M": 3.68, "6M": 3.77, "1Y": 3.81, "2Y": 4.07, "3Y": 4.14, "5Y": 4.27, "7Y": 4.43, "10Y": 4.61, "20Y": 5.14, "30Y": 5.14},
            ),
        ]
        dated = [date(2025, month, 1) for month in range(1, 13)] + [date(2026, month, 1) for month in range(1, 6)]
        fred = {
            "DFII5": TimeSeries("DFII5", [SeriesPoint(day, 1.10 + index * 0.04) for index, day in enumerate(dated)]),
            "DFII10": TimeSeries("DFII10", [SeriesPoint(day, 1.35 + index * 0.05) for index, day in enumerate(dated)]),
            "T10YIE": TimeSeries("T10YIE", [SeriesPoint(day, 2.15 + index * 0.01) for index, day in enumerate(dated)]),
            "DFF": TimeSeries("DFF", [SeriesPoint(day, 3.45 + index * 0.005) for index, day in enumerate(dated)]),
            "SOFR": TimeSeries("SOFR", [SeriesPoint(day, 3.50 + index * 0.008) for index, day in enumerate(dated)]),
            "OBFR": TimeSeries("OBFR", [SeriesPoint(day, 3.48 + index * 0.006) for index, day in enumerate(dated)]),
            "IORB": TimeSeries("IORB", [SeriesPoint(day, 3.55 + index * 0.004) for index, day in enumerate(dated)]),
            "RRPONTSYAWARD": TimeSeries("RRPONTSYAWARD", [SeriesPoint(day, 3.40 + index * 0.004) for index, day in enumerate(dated)]),
            "WTREGEN": TimeSeries("WTREGEN", [SeriesPoint(day, 500_000.0 + index * 25_000) for index, day in enumerate(dated)]),
            "WALCL": TimeSeries("WALCL", [SeriesPoint(day, 7_200_000.0 - index * 20_000) for index, day in enumerate(dated)]),
            "TREAST": TimeSeries("TREAST", [SeriesPoint(dated[-1], 4_210_000.0)]),
            "RRPONTSYD": TimeSeries("RRPONTSYD", [SeriesPoint(day, max(0.0, 260_000.0 - index * 20_000)) for index, day in enumerate(dated)]),
            "WRESBAL": TimeSeries("WRESBAL", [SeriesPoint(day, 3_250_000.0 - index * 12_000) for index, day in enumerate(dated)]),
            "DCPF3M": TimeSeries("DCPF3M", [SeriesPoint(day, 3.55 + index * 0.010) for index, day in enumerate(dated)]),
            "DTB3": TimeSeries("DTB3", [SeriesPoint(day, 3.45 + index * 0.006) for index, day in enumerate(dated)]),
            "NFCI": TimeSeries("NFCI", [SeriesPoint(day, -0.70 + index * 0.02) for index, day in enumerate(dated)]),
            "VIXCLS": TimeSeries("VIXCLS", [SeriesPoint(day, 14.0 + index * 0.3) for index, day in enumerate(dated)]),
            "VXVCLS": TimeSeries("VXVCLS", [SeriesPoint(day, 17.0 + index * 0.2) for index, day in enumerate(dated)]),
            "DTWEXBGS": TimeSeries("DTWEXBGS", [SeriesPoint(day, 116.0 + index * 0.25) for index, day in enumerate(dated)]),
            "BAMLH0A0HYM2": TimeSeries("BAMLH0A0HYM2", [SeriesPoint(day, 2.80 + index * 0.05) for index, day in enumerate(dated)]),
            "BAMLC0A0CM": TimeSeries("BAMLC0A0CM", [SeriesPoint(day, 0.80 + index * 0.015) for index, day in enumerate(dated)]),
            "DCOILWTICO": TimeSeries("DCOILWTICO", [SeriesPoint(day, 65.0 + index * 0.6) for index, day in enumerate(dated)]),
            "OVXCLS": TimeSeries("OVXCLS", [SeriesPoint(day, 31.0 + index * 0.4) for index, day in enumerate(dated)]),
            "DHHNGSP": TimeSeries("DHHNGSP", [SeriesPoint(day, 2.10 + index * 0.06) for index, day in enumerate(dated)]),
            "CPIAUCSL": TimeSeries("CPIAUCSL", [SeriesPoint(date(2025, 4, 1), 313.0), SeriesPoint(date(2026, 4, 1), 324.9)]),
            "PPIACO": TimeSeries("PPIACO", [SeriesPoint(date(2025, 4, 1), 255.0), SeriesPoint(date(2026, 4, 1), 270.3)]),
            "UNRATE": TimeSeries("UNRATE", [SeriesPoint(date(2026, 4, 1), 4.1)]),
            "PAYEMS": TimeSeries("PAYEMS", [SeriesPoint(date(2026, 3, 1), 159_500.0), SeriesPoint(date(2026, 4, 1), 159_650.0)]),
        }

        dashboard = build_dashboard_from_inputs(
            curve_records=curve_records,
            fred=fred,
            auctions=[],
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )

        factors = {factor["n"]: factor for group in dashboard["groups"] for factor in group["factors"]}
        expected_factor_names = {
            "SOFR-OBFR回购摩擦",
            "SOFR-IORB走廊摩擦",
            "SOFR-ON RRP走廊摩擦",
            "EFFR-IORB利差",
            "商票-TBill利差",
            "资金分裂度(21D)",
            "13周净流动性动量",
            "TGA偏离度",
            "ON RRP缓冲风险",
            "真实利率水平",
            "真实曲线(10Y-5Y)",
            "金融条件指数(NFCI)",
            "HY-IG利差",
            "VIX期限结构",
            "美元实现波动率",
            "原油波动偏离",
            "天然气",
        }
        self.assertTrue(expected_factor_names.issubset(factors))
        self.assertEqual(factors["SOFR-OBFR回购摩擦"]["sourceMode"], "derived-public")
        self.assertEqual(factors["ON RRP缓冲风险"]["sourceMode"], "derived-public")
        self.assertEqual(factors["金融条件指数(NFCI)"]["sourceMode"], "real-public")
        self.assertIn("Bhadial Funding", factors["资金分裂度(21D)"]["note"])
        self.assertIn("52周", factors["TGA偏离度"]["note"])
        self.assertIn("squared", factors["ON RRP缓冲风险"]["note"])

        percentile_names = {item["name"] for item in dashboard["percentiles"]["items"]}
        self.assertIn("13周净流动性动量", percentile_names)
        self.assertIn("TGA偏离度", percentile_names)
        self.assertIn("商票-TBill利差", percentile_names)
        self.assertIn("金融条件指数(NFCI)", percentile_names)
        trend_names = {trend["name"] for trend in dashboard["percentiles"]["trends"]}
        self.assertIn("13周净流动性动量", trend_names)
        self.assertIn("TGA偏离度", trend_names)
        self.assertIn("商票-TBill利差", trend_names)
        self.assertIn("金融条件指数(NFCI)", trend_names)

        component_names = {component["name"] for component in dashboard["macroLiquidity"]["components"]}
        self.assertIn("13周净流动性动量", component_names)
        self.assertIn("TGA偏离度", component_names)
        self.assertIn("SOFR-IORB走廊摩擦", component_names)
        self.assertIn("金融条件指数(NFCI)", component_names)
        # 去冗余簇c1: ON RRP缓冲风险已不计入综合分(RRP已含于净流动性)
        self.assertNotIn("ON RRP缓冲风险", component_names)
        self.assertEqual(dashboard["meta"]["bhadialCompatibility"]["sourceUrl"], "https://bhadial.com/")
        self.assertEqual(dashboard["meta"]["bhadialCompatibility"]["moduleCount"], 7)
        coverage = dashboard["meta"]["bhadialCompatibility"]["coverage"]
        self.assertEqual(coverage["totalFactors"], 47)
        self.assertEqual(coverage["scorecardFactorCount"], 21)
        self.assertEqual(len(coverage["modules"]), 7)
        self.assertEqual(coverage["coveredFactors"], coverage["totalFactors"])
        self.assertEqual(coverage["missingFactors"], 0)
        self.assertTrue(any(item["module"] == "Risk" and item["missing"] == 0 for item in coverage["modules"]))
        self.assertIn("Regional Banks vs SPY", coverage["proxyFactorNames"])
        self.assertIn("Risk vs Safe", coverage["proxyFactorNames"])
        self.assertIn("High-Beta Preference", coverage["proxyFactorNames"])

    def test_build_dashboard_tracks_cpi_pce_core_pce_and_dallas_trimmed_mean(self):
        curve_records = [
            YieldCurveRecord(
                date=date(2026, 4, 18),
                values={"1M": 3.69, "3M": 3.70, "6M": 3.69, "1Y": 3.64, "2Y": 3.71, "3Y": 3.72, "5Y": 3.84, "7Y": 4.04, "10Y": 4.26, "20Y": 4.85, "30Y": 4.88},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 18),
                values={"1M": 3.69, "3M": 3.68, "6M": 3.77, "1Y": 3.81, "2Y": 4.07, "3Y": 4.14, "5Y": 4.27, "7Y": 4.43, "10Y": 4.61, "20Y": 5.14, "30Y": 5.14},
            ),
        ]
        fred = {
            "DFII10": TimeSeries("DFII10", [SeriesPoint(date(2026, 5, 18), 2.13)]),
            "T10YIE": TimeSeries("T10YIE", [SeriesPoint(date(2026, 5, 18), 2.48)]),
            "DFF": TimeSeries("DFF", [SeriesPoint(date(2026, 5, 18), 3.63)]),
            "CPIAUCSL": TimeSeries("CPIAUCSL", [SeriesPoint(date(2025, 4, 1), 313.0), SeriesPoint(date(2026, 4, 1), 324.9)]),
            "PCEPI": TimeSeries("PCEPI", [SeriesPoint(date(2025, 4, 1), 122.0), SeriesPoint(date(2026, 4, 1), 126.0)]),
            "PCEPILFE": TimeSeries("PCEPILFE", [SeriesPoint(date(2025, 4, 1), 121.0), SeriesPoint(date(2026, 4, 1), 124.0)]),
            "PCETRIM12M159SFRBDAL": TimeSeries("PCETRIM12M159SFRBDAL", [SeriesPoint(date(2026, 4, 1), 2.4)]),
            "PPIACO": TimeSeries("PPIACO", [SeriesPoint(date(2025, 4, 1), 255.0), SeriesPoint(date(2026, 4, 1), 270.3)]),
            "UNRATE": TimeSeries("UNRATE", [SeriesPoint(date(2026, 4, 1), 4.1)]),
            "PAYEMS": TimeSeries("PAYEMS", [SeriesPoint(date(2026, 3, 1), 159_500.0), SeriesPoint(date(2026, 4, 1), 159_650.0)]),
        }

        dashboard = build_dashboard_from_inputs(
            curve_records=curve_records,
            fred=fred,
            auctions=[],
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )

        inflation_rows = {row[0]: row for row in dashboard["cross"]["inflation"]}
        self.assertEqual(inflation_rows["CPI通胀"][1], "3.8%")
        self.assertEqual(inflation_rows["PCE通胀"][1], "3.3%")
        self.assertEqual(inflation_rows["核心PCE"][1], "2.5%")
        self.assertEqual(inflation_rows["达拉斯联储Trimmed Mean PCE"][1], "2.4%")
        self.assertIn("PCETRIM12M159SFRBDAL", inflation_rows["达拉斯联储Trimmed Mean PCE"][2])
        macro_factors = {
            factor["n"]: factor
            for group in dashboard["groups"]
            if group["id"] == "g2"
            for factor in group["factors"]
        }
        self.assertIn("通胀跟踪", macro_factors)
        self.assertIn("核心PCE 2.5%", macro_factors["通胀跟踪"]["tag"])
        self.assertIn("Dallas Trimmed PCE 2.4%", macro_factors["通胀跟踪"]["tag"])
        self.assertIn("Dallas Fed Trimmed Mean PCE", macro_factors["通胀跟踪"]["note"])
        self.assertIn("政策反应函数", macro_factors["通胀跟踪"]["note"])
        duration_idea = next(item for item in dashboard["ideas"] if item["title"] == "战术减久期")
        self.assertIn("PCE 3.3%", duration_idea["text"])
        self.assertIn("核心PCE 2.5%", duration_idea["text"])
        self.assertIn("Dallas Trimmed PCE 2.4%", duration_idea["text"])

    def test_build_dashboard_adds_macro_liquidity_composite_score(self):
        curve_records = [
            YieldCurveRecord(
                date=date(2026, 4, 18),
                values={"1M": 3.69, "3M": 3.70, "6M": 3.69, "1Y": 3.64, "2Y": 3.71, "3Y": 3.72, "5Y": 3.84, "7Y": 4.04, "10Y": 4.26, "20Y": 4.85, "30Y": 4.88},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 18),
                values={"1M": 3.69, "3M": 3.68, "6M": 3.77, "1Y": 3.81, "2Y": 4.07, "3Y": 4.14, "5Y": 4.27, "7Y": 4.43, "10Y": 4.61, "20Y": 5.14, "30Y": 5.14},
            ),
        ]
        fred = {
            "WALCL": TimeSeries("WALCL", [SeriesPoint(date(2021 + i, 5, 1), 6_000_000.0 + i * 100_000) for i in range(6)]),
            "WTREGEN": TimeSeries("WTREGEN", [SeriesPoint(date(2021 + i, 5, 1), 600_000.0 + i * 50_000) for i in range(6)]),
            "RRPONTSYD": TimeSeries("RRPONTSYD", [SeriesPoint(date(2021 + i, 5, 1), 500_000.0 - i * 80_000) for i in range(6)]),
            "WRESBAL": TimeSeries("WRESBAL", [SeriesPoint(date(2021 + i, 5, 1), 2_000_000.0 + i * 60_000) for i in range(6)]),
            "SOFR": TimeSeries("SOFR", [SeriesPoint(date(2021 + i, 5, 1), 3.50 + i * 0.01) for i in range(6)]),
            "DFF": TimeSeries("DFF", [SeriesPoint(date(2021 + i, 5, 1), 3.50) for i in range(6)]),
            "VIXCLS": TimeSeries("VIXCLS", [SeriesPoint(date(2021 + i, 5, 1), 28.0 - i) for i in range(6)]),
            "BAMLH0A0HYM2": TimeSeries("BAMLH0A0HYM2", [SeriesPoint(date(2021 + i, 5, 1), 5.5 - i * 0.2) for i in range(6)]),
            # 2026-06-16 去冗余后 bank_reserves/onrrp 不再计分,补充存活因子数据序列以维持 >=5 observed 覆盖率门槛
            "NFCI": TimeSeries("NFCI", [SeriesPoint(date(2021 + i, 5, 1), -0.40 + i * 0.05) for i in range(6)]),
            "T10YIE": TimeSeries("T10YIE", [SeriesPoint(date(2021 + i, 5, 1), 2.10 + i * 0.04) for i in range(6)]),
            "DFII5": TimeSeries("DFII5", [SeriesPoint(date(2021 + i, 5, 1), 1.10 + i * 0.10) for i in range(6)]),
            "DFII10": TimeSeries("DFII10", [SeriesPoint(date(2021 + i, 5, 1), 1.40 + i * 0.09) for i in range(6)]),
        }

        dashboard = build_dashboard_from_inputs(
            curve_records=curve_records,
            fred=fred,
            auctions=[],
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )

        macro_liquidity = dashboard["macroLiquidity"]
        self.assertGreaterEqual(macro_liquidity["score"], 0)
        self.assertLessEqual(macro_liquidity["score"], 100)
        self.assertEqual(macro_liquidity["sourceUrl"], "https://bhadial.com/dashboard")
        self.assertEqual(macro_liquidity["moduleCount"], 7)
        self.assertEqual(macro_liquidity["totalFactorCount"], 47)
        self.assertEqual(macro_liquidity["scoredFactorCount"], 21)
        self.assertIn("Bhadial Conditions Score", macro_liquidity["method"])
        self.assertIn("module weights", macro_liquidity["method"])
        self.assertIn("EMA(5)", macro_liquidity["method"])
        self.assertEqual(
            [module["name"] for module in macro_liquidity["modules"]],
            ["Liquidity", "Funding", "Treasury", "Rates", "Credit", "Risk", "External"],
        )
        funding_module = next(module for module in macro_liquidity["modules"] if module["name"] == "Funding")
        self.assertIn("rawScore", funding_module)
        self.assertIn("ema5Score", funding_module)
        self.assertAlmostEqual(sum(module["weight"] for module in macro_liquidity["modules"]), 1.0, places=3)
        self.assertGreaterEqual(len(macro_liquidity["components"]), 21)
        component_names = {item["name"] for item in macro_liquidity["components"]}
        self.assertIn("13周净流动性动量", component_names)
        self.assertIn("净流动性", component_names)
        self.assertIn("TGA偏离度", component_names)
        self.assertIn("SOFR-IORB走廊摩擦", component_names)
        self.assertIn("10年盈亏平衡通胀", component_names)
        self.assertIn("真实曲线(10Y-5Y)", component_names)
        # 去冗余: 这些因子已不计入综合分(仍作原始指标展示)
        self.assertNotIn("银行准备金", component_names)
        self.assertNotIn("SOFR-OBFR回购摩擦", component_names)
        self.assertNotIn("银行股相对S&P500", component_names)
        self.assertNotIn("真实利率水平", component_names)
        self.assertTrue(macro_liquidity["drivers"])
        self.assertTrue(all("score" in item and "weight" in item for item in macro_liquidity["components"]))
        self.assertIn(macro_liquidity["constraint"]["name"], component_names)
        self.assertIn(macro_liquidity["offset"]["name"], component_names)
        self.assertIn("拖累", macro_liquidity["summary"])
        self.assertIn("缓冲", macro_liquidity["summary"])
        self.assertIn("历史分位", macro_liquidity["summary"])
        trend = macro_liquidity["trend"]
        self.assertIn("historicalPercentile", trend)
        self.assertIn("score3mChange", trend)
        self.assertIn("percentile3mChange", trend)
        self.assertIn(trend["direction"], {"上行", "下行", "震荡", "不足"})
        self.assertGreaterEqual(len(trend["points"]), 3)
        self.assertIn("percentile", trend["points"][-1])
        latest_trend_point = trend["points"][-1]
        self.assertAlmostEqual(latest_trend_point["score"], trend["score"], delta=0.2)
        trailing_scores = [float(point["score"]) for point in trend["points"]]
        self.assertEqual(trend["historicalPercentile"], historical_percentile(float(latest_trend_point["score"]), trailing_scores))
        bucket_labels = {item["label"] for item in macro_liquidity["balance"]}
        self.assertEqual(bucket_labels, {"拖累", "中性", "缓冲"})
        self.assertLessEqual(len(macro_liquidity["focusComponents"]), 5)
        self.assertGreaterEqual(macro_liquidity["hiddenComponentCount"], 0)
        self.assertEqual(
            [item["name"] for item in macro_liquidity["focusComponents"]],
            [item["name"] for item in sorted(macro_liquidity["components"], key=lambda item: abs(item["contribution"]), reverse=True)[:5]],
        )
        implication_labels = {item["label"] for item in macro_liquidity["implications"]}
        self.assertEqual(implication_labels, {"久期", "风险资产", "融资压力"})

    def test_build_dashboard_adds_macro_liquidity_sp500_lead_study(self):
        def month_add(start: date, offset: int) -> date:
            month_index = start.month - 1 + offset
            return date(start.year + month_index // 12, month_index % 12 + 1, 15)

        months = [month_add(date(2021, 5, 15), index) for index in range(62)]
        curve_records = [
            YieldCurveRecord(
                date=day,
                values={
                    "1M": 0.10 + index * 0.01,
                    "3M": 0.12 + index * 0.01,
                    "6M": 0.15 + index * 0.01,
                    "1Y": 0.20 + index * 0.01,
                    "2Y": 0.30 + index * 0.015,
                    "3Y": 0.45 + index * 0.016,
                    "5Y": 0.70 + index * 0.018,
                    "7Y": 0.90 + index * 0.018,
                    "10Y": 1.10 + index * 0.015,
                    "20Y": 1.60 + index * 0.012,
                    "30Y": 1.80 + index * 0.012,
                },
            )
            for index, day in enumerate(months)
        ]
        spx = 3_000.0
        spx_points: list[SeriesPoint] = []
        fred: dict[str, TimeSeries] = {}
        for index, day in enumerate(months):
            liquidity = index / (len(months) - 1)
            spx *= 1 + 0.002 + liquidity * 0.008
            spx_points.append(SeriesPoint(day, spx))
        fred["SP500"] = TimeSeries("SP500", spx_points)
        fred["WALCL"] = TimeSeries("WALCL", [SeriesPoint(day, 6_000_000.0 + index * 30_000) for index, day in enumerate(months)])
        fred["WTREGEN"] = TimeSeries("WTREGEN", [SeriesPoint(day, 900_000.0 - index * 5_000) for index, day in enumerate(months)])
        fred["RRPONTSYD"] = TimeSeries("RRPONTSYD", [SeriesPoint(day, 120_000.0 + index * 1_200) for index, day in enumerate(months)])
        fred["WRESBAL"] = TimeSeries("WRESBAL", [SeriesPoint(day, 2_600_000.0 + index * 15_000) for index, day in enumerate(months)])
        fred["SOFR"] = TimeSeries("SOFR", [SeriesPoint(day, 2.10 - index * 0.005) for index, day in enumerate(months)])
        fred["DFF"] = TimeSeries("DFF", [SeriesPoint(day, 2.00) for day in months])
        fred["DCPF3M"] = TimeSeries("DCPF3M", [SeriesPoint(day, 2.30 - index * 0.004) for index, day in enumerate(months)])
        fred["DTB3"] = TimeSeries("DTB3", [SeriesPoint(day, 2.00) for day in months])
        fred["NFCI"] = TimeSeries("NFCI", [SeriesPoint(day, 0.25 - index * 0.01) for index, day in enumerate(months)])
        fred["BAMLH0A0HYM2"] = TimeSeries("BAMLH0A0HYM2", [SeriesPoint(day, 5.80 - index * 0.035) for index, day in enumerate(months)])
        fred["VIXCLS"] = TimeSeries("VIXCLS", [SeriesPoint(day, 28.0 - index * 0.15) for index, day in enumerate(months)])
        fred["DGS10"] = TimeSeries("DGS10", [SeriesPoint(day, 2.80 - index * 0.01) for index, day in enumerate(months)])
        fred["NASDAQXNDX"] = TimeSeries("NASDAQXNDX", [SeriesPoint(day, 10_000.0 + index * 130) for index, day in enumerate(months)])
        fred["NASDAQNQUS500LCT"] = TimeSeries("NASDAQNQUS500LCT", [SeriesPoint(day, 3_000.0 + index * 35) for index, day in enumerate(months)])
        fred["NASDAQBANK"] = TimeSeries("NASDAQBANK", [SeriesPoint(day, 3_000.0 + index * 20) for index, day in enumerate(months)])
        fred["BAMLHYH0A0HYM2TRIV"] = TimeSeries("BAMLHYH0A0HYM2TRIV", [SeriesPoint(day, 1_100.0 + index * 6) for index, day in enumerate(months)])
        fred["BAMLCC0A0CMTRIV"] = TimeSeries("BAMLCC0A0CMTRIV", [SeriesPoint(day, 2_200.0 + index * 4) for index, day in enumerate(months)])

        dashboard = build_dashboard_from_inputs(
            curve_records=curve_records,
            fred=fred,
            auctions=[],
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )

        macro_trend = dashboard["macroLiquidity"]["trend"]
        self.assertGreaterEqual(len(macro_trend["points"]), 60)
        latest_macro_point = macro_trend["points"][-1]
        self.assertEqual(
            macro_trend["historicalPercentile"],
            historical_percentile(float(latest_macro_point["score"]), [float(point["score"]) for point in macro_trend["points"]]),
        )

        lead = dashboard["macroLiquidityEquity"]
        self.assertTrue(lead["available"])
        self.assertGreaterEqual(lead["observationCount"], 50)
        self.assertIn("S&P 500", lead["method"])
        self.assertIsNotNone(lead["correlations"]["forward3m"])
        self.assertEqual(len(lead["buckets"]), 3)
        self.assertIn("avgForward3m", lead["buckets"][0])
        self.assertIn("S&P 500", lead["conclusion"])
        self.assertIn("sp500Indexed", lead["series"][0])
        self.assertIn("score3mChange", lead["series"][-1])
        self.assertIn("forward3mMaxDrawdown", lead["series"][0])
        self.assertGreaterEqual(len(lead["leadLag"]), 2)
        self.assertEqual({row["signal"] for row in lead["leadLag"]}, {"评分水平", "3M评分变化"})
        self.assertEqual({bucket["label"] for bucket in lead["changeBuckets"]}, {"评分下行", "变化不大", "评分上行"})
        self.assertIn("latest", lead["rollingCorrelation"])
        self.assertGreater(len(lead["rollingCorrelation"]["points"]), 0)
        self.assertIn("maxDrawdown", lead["drawdownRisk"])
        signal = lead["currentSignal"]
        self.assertIn(signal["levelBucket"], {"低评分", "中位评分", "高评分"})
        self.assertIn(signal["changeBucket"], {"评分下行", "变化不大", "评分上行"})
        self.assertIn("verdict", signal)
        self.assertIn("expectedForward3m", signal)
        self.assertIn("expectedDrawdown3m", signal)
        self.assertGreaterEqual(len(signal["cards"]), 4)
        state_grid = lead["stateGrid"]
        self.assertEqual(len(state_grid), 9)
        self.assertEqual(
            {item["levelBucket"] for item in state_grid},
            {"低评分", "中位评分", "高评分"},
        )
        self.assertEqual(
            {item["changeBucket"] for item in state_grid},
            {"评分下行", "变化不大", "评分上行"},
        )
        current_cells = [item for item in state_grid if item["isCurrent"]]
        self.assertEqual(len(current_cells), 1)
        self.assertIn("avgForward3m", current_cells[0])
        self.assertIn("avgMaxDrawdown3m", current_cells[0])
        self.assertIn("hitRate", current_cells[0])
        warning = dashboard["spyEarlyWarning"]
        self.assertTrue(warning["available"])
        self.assertGreaterEqual(warning["score"], 0)
        self.assertLessEqual(warning["score"], 100)
        self.assertIn(warning["regime"], {"Constructive", "Neutral", "Caution", "De-risk"})
        self.assertIn("allocation", warning)
        self.assertIn("equityExposure", warning["allocation"])
        self.assertIn("sleeves", warning)
        self.assertTrue(any(item["key"] == "macroDeterioration" for item in warning["sleeves"]))
        self.assertEqual(warning["backtest"]["target"], "3M SPX drawdown and negative forward-return warning")
        self.assertIn("trend", warning)
        self.assertTrue(warning["trend"]["available"])
        self.assertGreaterEqual(len(warning["trend"]["points"]), 50)
        self.assertEqual(warning["trend"]["points"][-1]["score"], warning["score"])
        self.assertIn("regime", warning["trend"]["points"][-1])

    def test_equity_short_term_risk_flags_june4_before_next_day_selloff(self):
        market_bars = {
            "SPY": self.make_equity_bars("SPY", start_price=680, pre_event_return=0.103, june4_return=0.0038, june5_return=-0.0258, june4_volume_multiplier=0.72),
            "QQQ": self.make_equity_bars("QQQ", start_price=520, pre_event_return=0.218, june4_return=-0.0048, june5_return=-0.048),
            "SMH": self.make_equity_bars("SMH", start_price=190, pre_event_return=0.544, june4_return=-0.0163, june5_return=-0.092),
            "XLK": self.make_equity_bars("XLK", start_price=180, pre_event_return=0.384, june4_return=-0.0156, june5_return=-0.066),
            "TLT": self.make_equity_bars("TLT", start_price=88, pre_event_return=-0.021, june4_return=-0.002, june5_return=0.006),
            "RSP": self.make_equity_bars("RSP", start_price=170, pre_event_return=0.031, june4_return=0.0076, june5_return=-0.014),
            "IWM": self.make_equity_bars("IWM", start_price=210, pre_event_return=0.107, june4_return=0.0151, june5_return=-0.035),
            "XLV": self.make_equity_bars("XLV", start_price=140, pre_event_return=-0.041, june4_return=0.0307, june5_return=0.006),
            "AMD": self.make_equity_bars("AMD", start_price=80, pre_event_return=1.63, june4_return=-0.0356, june5_return=-0.108),
            "AVGO": self.make_equity_bars("AVGO", start_price=700, pre_event_return=0.314, june4_return=-0.1259, june5_return=-0.079),
            "TSLA": self.make_equity_bars("TSLA", start_price=320, pre_event_return=0.038, june4_return=-0.0124, june5_return=-0.066),
            "META": self.make_equity_bars("META", start_price=620, pre_event_return=-0.04, june4_return=0.0074, june5_return=-0.055),
            "MSFT": self.make_equity_bars("MSFT", start_price=460, pre_event_return=0.074, june4_return=0.0017, june5_return=-0.027),
        }
        events = [CalendarEvent(date=date(2026, 6, 5), title="BLS Employment Situation", source="FRED release calendar", importance="高")]

        risk = build_equity_short_term_risk_index(
            market_bars=market_bars,
            macro_liquidity_equity={
                "currentSignal": {
                    "date": "2026-06-04",
                    "score3mChange": 8.1,
                    "levelBucket": "中位评分",
                    "changeBucket": "评分上行",
                }
            },
            spy_early_warning={"available": True, "score": 41.1, "regime": "Neutral"},
            calendar_events=events,
        )

        self.assertTrue(risk["available"])
        self.assertEqual(risk["asOf"], "2026-06-04")
        self.assertEqual(risk["lookAheadGuard"]["dataThrough"], "2026-06-04")
        self.assertEqual(risk["regime"], "Strong Alert")
        self.assertGreaterEqual(risk["score"], 75)
        self.assertLessEqual(risk["nextSessionShock"]["returnPct"], -2.0)
        component_keys = {component["key"] for component in risk["components"]}
        self.assertTrue({"volTargetPressure", "qqqTltRotation", "marketFlow", "sectorRotation", "hotStockReversal", "turnover", "eventRisk"}.issubset(component_keys))
        driver_keys = {driver["key"] for driver in risk["drivers"]}
        self.assertTrue({"rallyExtension", "leaderConcentration", "lateRotationBreak", "hotStockReversal", "eventRisk"}.intersection(driver_keys))
        self.assertTrue(risk["backtest"]["available"])
        self.assertIn("thresholdTests", risk["backtest"])

    def test_equity_short_term_risk_uses_explainable_vol_target_and_qqq_tlt_rotation(self):
        base = [100 + index * 0.18 for index in range(78)]
        qqq_closes = base + [114.4, 113.6, 112.9, 111.8, 110.6, 109.7, 108.9, 108.1, 107.5, 107.0]
        spy_closes = [100 + index * 0.10 for index in range(78)] + [108.0, 107.6, 107.2, 106.6, 106.0, 105.6, 105.1, 104.8, 104.5, 104.2]
        tlt_closes = [100 - index * 0.03 for index in range(78)] + [97.5, 97.4, 97.1, 96.8, 96.6, 96.3, 96.2, 96.0, 95.9, 95.7]
        quiet_ranges = [0.006] * 78
        shock_ranges = [0.040, 0.044, 0.050, 0.047, 0.052, 0.045, 0.049, 0.046, 0.043, 0.041]
        target = date(2025, 6, 6)
        market_bars = {
            "SPY": self.make_equity_bars_from_closes_and_ranges("SPY", spy_closes, quiet_ranges + [value * 0.72 for value in shock_ranges]),
            "QQQ": self.make_equity_bars_from_closes_and_ranges("QQQ", qqq_closes, quiet_ranges + shock_ranges),
            "TLT": self.make_equity_bars_from_closes_and_ranges("TLT", tlt_closes, [0.007] * len(tlt_closes)),
            "SMH": self.make_equity_bars_from_closes_and_ranges("SMH", qqq_closes, quiet_ranges + shock_ranges),
            "XLK": self.make_equity_bars_from_closes_and_ranges("XLK", qqq_closes, quiet_ranges + shock_ranges),
            "RSP": self.make_equity_bars_from_closes_and_ranges("RSP", spy_closes, quiet_ranges + [0.012] * 10),
            "IWM": self.make_equity_bars_from_closes_and_ranges("IWM", spy_closes, quiet_ranges + [0.016] * 10),
            "NVDA": self.make_equity_bars_from_closes_and_ranges("NVDA", qqq_closes, quiet_ranges + shock_ranges),
            "AVGO": self.make_equity_bars_from_closes_and_ranges("AVGO", qqq_closes, quiet_ranges + shock_ranges),
            "AMD": self.make_equity_bars_from_closes_and_ranges("AMD", qqq_closes, quiet_ranges + shock_ranges),
        }
        normalized = dashboard_builder.normalize_market_bars(market_bars)

        vol = equity_vol_target_pressure_component(normalized, target, weight=0.24)
        rotation = equity_qqq_tlt_rotation_component(normalized, target, weight=0.18)
        risk = equity_short_term_signal_at(
            normalized,
            target,
            macro_liquidity_equity={"currentSignal": {"score3mChange": 2.0}},
            spy_early_warning={"score": 42.0},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertGreaterEqual(vol["score"], 75)
        self.assertIn("parkinsonVolBurst", {driver["key"] for driver in vol["drivers"]})
        self.assertGreaterEqual(rotation["score"], 70)
        self.assertIn("tltHedgeFailure", {driver["key"] for driver in rotation["drivers"]})
        components_by_key = {component["key"]: component for component in risk["components"]}
        self.assertEqual(components_by_key["volTargetPressure"]["weight"], 0.22)
        self.assertEqual(components_by_key["qqqTltRotation"]["weight"], 0.14)
        self.assertEqual(components_by_key["marketFlow"]["weight"], 0.22)
        self.assertEqual(components_by_key["sectorRotation"]["weight"], 0.06)
        self.assertEqual(components_by_key["hotStockReversal"]["weight"], 0.18)
        self.assertEqual(components_by_key["turnover"]["weight"], 0.14)
        self.assertEqual(components_by_key["eventRisk"]["weight"], 0.01)
        self.assertEqual(components_by_key["macroOverlay"]["weight"], 0.03)
        self.assertEqual(components_by_key["optionOI"]["weight"], 0.0)
        self.assertEqual(components_by_key["optionOI"]["scoreUse"], "missing")
        evidence_by_component = {item["component"]: item for item in risk["factorEvidence"]}
        self.assertEqual(evidence_by_component["volTargetPressure"]["sourceQuality"], "high")
        self.assertTrue(evidence_by_component["volTargetPressure"]["historicalReplay"])
        self.assertEqual(evidence_by_component["qqqTltRotation"]["sourceQuality"], "high")
        self.assertTrue(evidence_by_component["qqqTltRotation"]["historicalReplay"])

    def test_equity_qqq_tlt_rotation_flags_crowded_risk_on_rollover(self):
        qqq_closes = [100 + index * 0.35 for index in range(70)] + [125, 126, 127, 128, 129, 130, 130.5, 130.2]
        tlt_closes = [100 - index * 0.08 for index in range(70)] + [94.4, 94.1, 93.8, 93.5, 93.2, 93.0, 92.8, 93.0]
        market_bars = {
            "QQQ": self.make_equity_bars_from_closes("QQQ", qqq_closes),
            "TLT": self.make_equity_bars_from_closes("TLT", tlt_closes),
        }

        rotation = equity_qqq_tlt_rotation_component(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2025, 5, 22),
            weight=0.18,
        )

        self.assertGreaterEqual(rotation["score"], 75)
        self.assertIn("qqqTltCrowdedRollover", {driver["key"] for driver in rotation["drivers"]})

    def test_equity_short_term_risk_backtest_summarizes_forward_drawdowns_by_bucket(self):
        days = [date(2026, 1, 2) + dashboard_builder.timedelta(days=index) for index in range(20)]
        closes = [100, 101, 102, 103, 99, 98, 101, 103, 104, 105, 104, 102, 101, 103, 104, 105, 104, 103, 102, 101]
        spy_bars = [
            MarketDailyBar(
                symbol="SPY",
                date=day,
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=10_000_000,
                source="unit-test",
            )
            for day, close in zip(days, closes)
        ]
        trend_points = [
            {"date": days[0].isoformat(), "score": 35.0, "regime": "Normal"},
            {"date": days[1].isoformat(), "score": 82.0, "regime": "Strong Alert"},
            {"date": days[7].isoformat(), "score": 66.0, "regime": "Caution"},
            {"date": days[8].isoformat(), "score": 45.0, "regime": "Watch"},
        ]

        backtest = build_equity_short_term_risk_backtest(trend_points, spy_bars)

        self.assertTrue(backtest["available"])
        self.assertEqual(backtest["sampleSize"], 4)
        strong_bucket = next(bucket for bucket in backtest["scoreBuckets"] if bucket["label"] == "Strong Alert")
        self.assertEqual(strong_bucket["count"], 1)
        self.assertLessEqual(strong_bucket["avgMaxDrawdown10d"], -2.0)
        threshold_75 = next(test for test in backtest["thresholdTests"] if test["threshold"] == 75)
        self.assertEqual(threshold_75["alertDays"], 1)
        self.assertEqual(threshold_75["truePositives"], 1)
        self.assertEqual(threshold_75["precision"], 100.0)
        tiered = {test["threshold"]: test for test in backtest["tieredThresholdTests"]}
        self.assertEqual(tiered[75]["key"], "strongAlert")
        self.assertEqual(tiered[75]["label"], "强告警")
        self.assertEqual(tiered[60]["key"], "cautionPlus")
        self.assertEqual(tiered[60]["label"], "警戒以上")
        self.assertGreaterEqual(tiered[60]["recall"], tiered[75]["recall"])
        self.assertIn("高精度", tiered[75]["useCase"])
        self.assertIn("覆盖", tiered[60]["useCase"])
        self.assertEqual([row["threshold"] for row in backtest["calibrationGrid"]], [50, 55, 60, 65, 70, 75])
        recommended = backtest["recommendedCautionThreshold"]
        self.assertIn(recommended["threshold"], {55, 60, 65, 70})
        self.assertIn("推荐观察", recommended["label"])
        self.assertIn("precision", recommended)
        self.assertEqual([row["threshold"] for row in backtest["precisionThresholdTests"]], [75, 78, 80, 82, 85, 88, 90])
        self.assertIn("高精度", backtest["highPrecisionThresholdTest"]["label"])
        self.assertIn("precision", backtest["highPrecisionThresholdTest"])
        self.assertIn("componentDiagnostics", backtest)
        self.assertGreaterEqual(len(backtest["worstWindows"]), 1)

    def test_equity_short_term_risk_backtest_audits_component_predictive_quality(self):
        days = [date(2026, 1, 2) + dashboard_builder.timedelta(days=index) for index in range(25)]
        closes = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 98, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100]
        spy_bars = [
            MarketDailyBar(
                symbol="SPY",
                date=day,
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=10_000_000,
                source="unit-test",
            )
            for day, close in zip(days, closes)
        ]
        trend_points = [
            {
                "date": days[0].isoformat(),
                "score": 80.0,
                "regime": "Strong Alert",
                "componentScores": {
                    "goodFactor": {"label": "有效因子", "score": 85.0, "weight": 0.20},
                    "weakFactor": {"label": "噪声因子", "score": 25.0, "weight": 0.10},
                },
            },
            {
                "date": days[1].isoformat(),
                "score": 82.0,
                "regime": "Strong Alert",
                "componentScores": {
                    "goodFactor": {"label": "有效因子", "score": 90.0, "weight": 0.20},
                    "weakFactor": {"label": "噪声因子", "score": 35.0, "weight": 0.10},
                },
            },
            {
                "date": days[16].isoformat(),
                "score": 45.0,
                "regime": "Watch",
                "componentScores": {
                    "goodFactor": {"label": "有效因子", "score": 25.0, "weight": 0.20},
                    "weakFactor": {"label": "噪声因子", "score": 88.0, "weight": 0.10},
                },
            },
            {
                "date": days[17].isoformat(),
                "score": 44.0,
                "regime": "Watch",
                "componentScores": {
                    "goodFactor": {"label": "有效因子", "score": 35.0, "weight": 0.20},
                    "weakFactor": {"label": "噪声因子", "score": 82.0, "weight": 0.10},
                },
            },
        ]

        backtest = build_equity_short_term_risk_backtest(trend_points, spy_bars)

        diagnostics = {row["component"]: row for row in backtest["componentDiagnostics"]}
        self.assertEqual(diagnostics["goodFactor"]["decision"], "core")
        self.assertEqual(diagnostics["goodFactor"]["precision"], 100.0)
        self.assertIn("保留", diagnostics["goodFactor"]["recommendation"])
        self.assertEqual(diagnostics["weakFactor"]["decision"], "trim")
        self.assertEqual(diagnostics["weakFactor"]["precision"], 0.0)
        self.assertIn("降权", diagnostics["weakFactor"]["recommendation"])

    def test_equity_short_term_risk_backtest_runs_historical_regressions(self):
        days = [date(2026, 1, 2) + dashboard_builder.timedelta(days=index) for index in range(20)]
        closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 108, 106, 104, 102, 100, 98, 96, 95, 94]
        spy_bars = [
            MarketDailyBar(
                symbol="SPY",
                date=day,
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=10_000_000,
                source="unit-test",
            )
            for day, close in zip(days, closes)
        ]
        trend_points = [
            {"date": days[0].isoformat(), "score": 10.0, "regime": "Normal"},
            {"date": days[4].isoformat(), "score": 30.0, "regime": "Normal"},
            {"date": days[8].isoformat(), "score": 70.0, "regime": "Caution"},
            {"date": days[9].isoformat(), "score": 90.0, "regime": "Strong Alert"},
        ]

        backtest = build_equity_short_term_risk_backtest(trend_points, spy_bars)

        regressions = {item["target"]: item for item in backtest["regressionTests"]}
        self.assertLess(regressions["forward10d"]["slopePer10Score"], 0)
        self.assertLess(regressions["maxDrawdown10d"]["slopePer10Score"], 0)
        self.assertGreater(regressions["drawdownEvent10d"]["slopePer10Score"], 0)
        self.assertGreater(regressions["drawdownEvent10d"]["rSquared"], 0)
        self.assertIn("score每升10分", regressions["maxDrawdown10d"]["summary"])

    def test_equity_short_term_risk_backtest_counts_relaxed_15d_prediction_window(self):
        days = [date(2026, 1, 2) + dashboard_builder.timedelta(days=index) for index in range(25)]
        closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 111, 110, 108, 106, 104, 99, 98, 97, 96, 95, 94, 93]
        spy_bars = [
            MarketDailyBar(
                symbol="SPY",
                date=day,
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=10_000_000,
                source="unit-test",
            )
            for day, close in zip(days, closes)
        ]
        trend_points = [
            {"date": days[3].isoformat(), "score": 82.0, "regime": "Strong Alert"},
            {"date": days[4].isoformat(), "score": 35.0, "regime": "Normal"},
        ]

        backtest = build_equity_short_term_risk_backtest(trend_points, spy_bars)

        threshold_10 = next(test for test in backtest["thresholdTests"] if test["threshold"] == 75)
        threshold_15 = next(test for test in backtest["horizonTests"] if test["threshold"] == 75 and test["horizon"] == 15)
        self.assertEqual(threshold_10["truePositives"], 0)
        self.assertEqual(threshold_15["truePositives"], 1)
        self.assertEqual(threshold_15["precision"], 100.0)
        self.assertEqual(backtest["preferredThresholdTest"]["horizon"], 15)

    def test_equity_short_term_risk_backtest_reports_alert_lead_time(self):
        days = [date(2026, 1, 5) + dashboard_builder.timedelta(days=index) for index in range(18)]
        closes = [100, 100.1, 99.8, 99.2, 97.8, 98.0, 98.4, 99.0, 99.4, 99.7, 100.0, 100.2, 100.4, 100.6, 100.8, 101.0, 101.2, 101.4]
        spy_bars = []
        for index, (day, close) in enumerate(zip(days, closes)):
            open_price = closes[index - 1] if index else close
            spy_bars.append(
                MarketDailyBar(
                    symbol="SPY",
                    date=day,
                    open=open_price,
                    high=max(open_price, close) * 1.001,
                    low=close,
                    close=close,
                    volume=10_000_000,
                    source="unit-test",
                )
            )
        trend_points = [
            {"date": days[0].isoformat(), "score": 82.0, "regime": "Strong Alert"},
            {"date": days[1].isoformat(), "score": 35.0, "regime": "Normal"},
        ]

        backtest = build_equity_short_term_risk_backtest(trend_points, spy_bars)

        preferred = backtest["preferredThresholdTest"]
        self.assertEqual(preferred["truePositives"], 1)
        self.assertEqual(preferred["avgDrawdownLeadDaysWhenHit"], 4.0)
        self.assertEqual(preferred["medianDrawdownLeadDaysWhenHit"], 4.0)
        self.assertEqual(backtest["alertClusterTest"]["avgLeadDays"], 4.0)
        self.assertEqual(backtest["alertClusterTest"]["clusters"][0]["leadDays"], 4)

    def test_equity_short_term_risk_backtest_exposes_alert_windows_for_chart_audit(self):
        days = [date(2026, 2, 2) + dashboard_builder.timedelta(days=index) for index in range(24)]
        closes = [100, 100.5, 101, 101.4, 101.8, 102.2, 101.7, 101.2, 100.8, 99.9, 99.0, 98.4, 98.0, 98.6, 99.2, 100.0, 100.5, 101.0, 101.4, 101.8, 102.1, 102.4, 102.6, 102.8]
        spy_bars = []
        for index, (day, close) in enumerate(zip(days, closes)):
            open_price = closes[index - 1] if index else close
            spy_bars.append(
                MarketDailyBar(
                    symbol="SPY",
                    date=day,
                    open=open_price,
                    high=max(open_price, close) * 1.002,
                    low=close,
                    close=close,
                    volume=10_000_000,
                    source="unit-test",
                )
            )
        trend_points = [
            {"date": days[0].isoformat(), "score": 34.0, "regime": "Normal", "regimeCn": "正常"},
            {"date": days[3].isoformat(), "score": 81.0, "regime": "Strong Alert", "regimeCn": "强告警"},
            {"date": days[4].isoformat(), "score": 88.0, "regime": "Strong Alert", "regimeCn": "强告警"},
            {"date": days[15].isoformat(), "score": 42.0, "regime": "Watch", "regimeCn": "观察"},
        ]

        backtest = build_equity_short_term_risk_backtest(trend_points, spy_bars)

        self.assertTrue(backtest["available"])
        self.assertIn("alertWindows", backtest)
        self.assertGreaterEqual(len(backtest["alertWindows"]), 2)
        first = backtest["alertWindows"][0]
        self.assertEqual(first["date"], days[4].isoformat())
        self.assertEqual(first["score"], 88.0)
        self.assertEqual(first["regimeCn"], "强告警")
        self.assertEqual(first["horizon"], 15)
        self.assertTrue(first["hit"])
        self.assertEqual(first["drawdownLeadDays15d"], 6)
        self.assertLessEqual(first["maxDrawdown15d"], -2.0)
        self.assertIn("spyClose", first)
        self.assertIn("forward15d", first)

    def test_equity_short_term_risk_backtest_dedupes_contiguous_alert_clusters(self):
        days = [date(2026, 1, 2) + dashboard_builder.timedelta(days=index) for index in range(22)]
        closes = [100, 101, 102, 103, 104, 105, 106, 105, 104, 103, 102, 100, 98, 96, 95, 94, 93, 92, 91, 90, 89, 88]
        spy_bars = [
            MarketDailyBar(
                symbol="SPY",
                date=day,
                open=close,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=10_000_000,
                source="unit-test",
            )
            for day, close in zip(days, closes)
        ]
        trend_points = [
            {"date": days[2].isoformat(), "score": 78.0, "regime": "Strong Alert"},
            {"date": days[3].isoformat(), "score": 82.0, "regime": "Strong Alert"},
            {"date": days[4].isoformat(), "score": 79.0, "regime": "Strong Alert"},
        ]

        backtest = build_equity_short_term_risk_backtest(trend_points, spy_bars)

        cluster = backtest["alertClusterTest"]
        self.assertEqual(cluster["threshold"], 75)
        self.assertEqual(cluster["horizon"], 15)
        self.assertEqual(cluster["clusterCount"], 1)
        self.assertEqual(cluster["hitClusters"], 1)
        self.assertEqual(cluster["precision"], 100.0)

    def test_global_lppl_risk_flags_synthetic_bubble_as_independent_indicator(self):
        def lppl_closes(days: int = 300) -> list[float]:
            tc = days + 45
            closes: list[float] = []
            for index in range(days):
                distance = max(1.0, tc - index)
                log_price = 5.2 - 0.58 * (distance ** 0.48) + 0.045 * (distance ** 0.48) * math.cos(8.5 * math.log(distance) + 0.7)
                closes.append(math.exp(log_price))
            scale = 100 / closes[0]
            return [close * scale for close in closes]

        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", lppl_closes()),
            "QQQ": self.make_equity_bars_from_closes("QQQ", [value * (1 + index * 0.0007) for index, value in enumerate(lppl_closes())]),
        }

        risk = dashboard_builder.build_global_lppl_risk_index(market_bars=market_bars)

        self.assertTrue(risk["available"])
        self.assertEqual(risk["title"], "Global LPPL Risk · 全球指数泡沫临界风险")
        self.assertIsNone(risk["score"])
        self.assertEqual(risk["regime"], "Per-Index")
        self.assertIn("independent", risk["scoreUse"])
        self.assertIn("逐市场", risk["summary"])
        self.assertGreaterEqual(len(risk["indices"]), 2)
        qqq = next(row for row in risk["indices"] if row["symbol"] == "QQQ")
        self.assertEqual(qqq["status"], "risk")
        self.assertGreaterEqual(qqq["score"], 60)
        self.assertGreaterEqual(qqq["confidence"], 0.35)
        self.assertRegex(qqq["criticalDate"], r"^2026-")
        self.assertGreaterEqual(qqq["daysToCritical"], 10)
        self.assertLessEqual(qqq["daysToCritical"], 180)
        self.assertFalse(risk["history"]["available"])
        self.assertFalse(risk["backtest"]["available"])
        for symbol in ("SPY", "QQQ"):
            row = next(item for item in risk["indices"] if item["symbol"] == symbol)
            self.assertTrue(row["history"]["available"])
            self.assertGreaterEqual(len(row["history"]["points"]), 20)
            self.assertTrue(all("indexedClose" in point for point in row["history"]["points"][:3]))
            self.assertTrue(row["backtest"]["available"])
            self.assertEqual([item["horizon"] for item in row["backtest"]["horizonTests"]], [5, 10, 15, 20])
        self.assertIn("perIndexHistory", risk)
        self.assertIn("perIndexBacktests", risk)
        self.assertTrue(risk["perIndexHistory"]["QQQ"]["available"])
        self.assertTrue(risk["perIndexBacktests"]["QQQ"]["available"])
        self.assertTrue(risk["indexValidation"]["available"])
        validation_rows = {row["symbol"]: row for row in risk["indexValidation"]["rows"]}
        self.assertIn("SPY", validation_rows)
        self.assertIn("QQQ", validation_rows)
        self.assertIn("precision15d", validation_rows["QQQ"])
        self.assertIn("effectiveWeightMultiplier", validation_rows["QQQ"])
        self.assertGreater(validation_rows["QQQ"]["sampleSize"], 20)
        self.assertLessEqual(validation_rows["QQQ"]["effectiveWeightMultiplier"], 1.0)
        self.assertIn("validation", qqq)
        self.assertEqual(qqq["validation"]["symbol"], "QQQ")
        self.assertIn("effectiveWeightMultiplier", qqq)

    def test_global_lppl_risk_marks_quiet_trend_low_confidence(self):
        closes = [100 + index * 0.08 for index in range(280)]
        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", closes),
            "QQQ": self.make_equity_bars_from_closes("QQQ", [value * 1.05 for value in closes]),
        }

        risk = dashboard_builder.build_global_lppl_risk_index(market_bars=market_bars)

        self.assertTrue(risk["available"])
        self.assertTrue(all(row["status"] in {"quiet", "watch"} for row in risk["indices"] if row["available"]))
        self.assertLessEqual(max(row["confidence"] for row in risk["indices"] if row["available"]), 0.45)
        self.assertIsNone(risk["score"])
        self.assertFalse(risk["history"]["available"])
        self.assertFalse(risk["backtest"]["available"])

    def test_global_lppl_risk_reports_missing_indices_without_fabricated_scores(self):
        risk = dashboard_builder.build_global_lppl_risk_index(market_bars={"SPY": self.make_equity_bars_from_closes("SPY", [100 + index for index in range(80)])})

        self.assertFalse(risk["available"])
        self.assertIsNone(risk["score"])
        self.assertGreaterEqual(len(risk["indices"]), 6)
        missing = [row for row in risk["indices"] if not row["available"]]
        self.assertTrue(missing)
        self.assertTrue(all(row["score"] is None for row in missing))

    def test_equity_short_term_risk_flags_downtrend_continuation(self):
        market_bars = {
            "SPY": self.make_equity_bars("SPY", start_price=620, pre_event_return=-0.07, june4_return=-0.014, june5_return=-0.028, june4_volume_multiplier=1.12),
            "QQQ": self.make_equity_bars("QQQ", start_price=510, pre_event_return=-0.11, june4_return=-0.021, june5_return=-0.041),
            "SMH": self.make_equity_bars("SMH", start_price=245, pre_event_return=-0.14, june4_return=-0.034, june5_return=-0.058),
            "XLK": self.make_equity_bars("XLK", start_price=230, pre_event_return=-0.10, june4_return=-0.020, june5_return=-0.040),
            "RSP": self.make_equity_bars("RSP", start_price=185, pre_event_return=-0.035, june4_return=-0.006, june5_return=-0.016),
            "IWM": self.make_equity_bars("IWM", start_price=215, pre_event_return=-0.09, june4_return=-0.018, june5_return=-0.036),
            "XLV": self.make_equity_bars("XLV", start_price=145, pre_event_return=0.01, june4_return=0.003, june5_return=-0.004),
            "XLU": self.make_equity_bars("XLU", start_price=74, pre_event_return=0.02, june4_return=0.004, june5_return=-0.003),
            "XLP": self.make_equity_bars("XLP", start_price=82, pre_event_return=0.015, june4_return=0.003, june5_return=-0.003),
            "AMD": self.make_equity_bars("AMD", start_price=110, pre_event_return=-0.18, june4_return=-0.041, june5_return=-0.078),
            "AVGO": self.make_equity_bars("AVGO", start_price=900, pre_event_return=-0.12, june4_return=-0.045, june5_return=-0.070),
            "TSLA": self.make_equity_bars("TSLA", start_price=320, pre_event_return=-0.15, june4_return=-0.036, june5_return=-0.064),
            "META": self.make_equity_bars("META", start_price=620, pre_event_return=-0.08, june4_return=-0.020, june5_return=-0.052),
            "MSFT": self.make_equity_bars("MSFT", start_price=460, pre_event_return=-0.06, june4_return=-0.018, june5_return=-0.030),
        }

        flow = equity_market_flow_component(dashboard_builder.normalize_market_bars(market_bars), date(2026, 6, 4), weight=0.22)
        risk = build_equity_short_term_risk_index(market_bars=market_bars)

        self.assertGreaterEqual(flow["score"], 75)
        self.assertTrue(any(driver["key"] == "downtrendContinuation" for driver in flow["drivers"]))
        self.assertEqual(risk["regime"], "Strong Alert")
        self.assertGreaterEqual(risk["score"], 75)
        self.assertTrue(risk["weightCalibration"]["available"])
        calibration_rows = {row["component"]: row for row in risk["weightCalibration"]["rows"]}
        self.assertIn("marketFlow", calibration_rows)
        self.assertEqual(calibration_rows["marketFlow"]["configuredWeight"], 0.22)
        self.assertIn(calibration_rows["marketFlow"]["calibratedRole"], {"validated", "context", "downweighted"})

    def test_equity_short_term_risk_keeps_warning_after_fragile_relief_rally(self):
        spy_closes = [100.0 + index * 0.04 for index in range(12)] + [100, 100.5, 101, 100.6, 99.8, 98.7, 97.5, 96.1, 94.0, 92.0, 93.4, 95.6, 96.3]
        qqq_closes = [100.0 + index * 0.03 for index in range(12)] + [100, 100.2, 100.5, 99.6, 98.0, 96.1, 94.0, 92.3, 90.4, 89.0, 90.1, 91.0, 91.5]
        smh_closes = [100.0 + index * 0.05 for index in range(12)] + [100, 101.0, 100.4, 98.2, 95.0, 92.0, 89.5, 87.7, 85.0, 83.0, 84.0, 85.2, 85.8]
        defensive_closes = [100.0 + index * 0.02 for index in range(12)] + [100, 100.4, 100.6, 100.9, 101.0, 101.4, 101.6, 101.8, 102.0, 102.2, 102.4, 102.6, 102.8]
        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", spy_closes, last_volume_multiplier=0.52),
            "QQQ": self.make_equity_bars_from_closes("QQQ", qqq_closes),
            "SMH": self.make_equity_bars_from_closes("SMH", smh_closes),
            "XLK": self.make_equity_bars_from_closes("XLK", qqq_closes),
            "RSP": self.make_equity_bars_from_closes("RSP", spy_closes),
            "IWM": self.make_equity_bars_from_closes("IWM", qqq_closes),
            "XLV": self.make_equity_bars_from_closes("XLV", defensive_closes),
            "XLU": self.make_equity_bars_from_closes("XLU", defensive_closes),
            "XLP": self.make_equity_bars_from_closes("XLP", defensive_closes),
            "NVDA": self.make_equity_bars_from_closes("NVDA", smh_closes),
            "AVGO": self.make_equity_bars_from_closes("AVGO", smh_closes),
            "AMD": self.make_equity_bars_from_closes("AMD", smh_closes),
            "TSLA": self.make_equity_bars_from_closes("TSLA", qqq_closes),
            "META": self.make_equity_bars_from_closes("META", qqq_closes),
            "MSFT": self.make_equity_bars_from_closes("MSFT", qqq_closes),
        }

        risk = build_equity_short_term_risk_index(market_bars=market_bars)

        self.assertGreaterEqual(risk["score"], 60)
        self.assertIn("reliefRallyTrap", {driver["key"] for driver in risk["drivers"]})

    def test_equity_short_term_risk_dampens_pure_extension_noise_without_event_or_breakdown(self):
        market_bars = {
            "SPY": self.make_equity_bars("SPY", start_price=520, pre_event_return=0.25, june4_return=0.001, june5_return=0.004, june4_volume_multiplier=0.42),
            "QQQ": self.make_equity_bars("QQQ", start_price=420, pre_event_return=0.40, june4_return=-0.011, june5_return=0.006),
            "SMH": self.make_equity_bars("SMH", start_price=180, pre_event_return=0.75, june4_return=-0.018, june5_return=0.008),
            "XLK": self.make_equity_bars("XLK", start_price=170, pre_event_return=0.45, june4_return=-0.012, june5_return=0.006),
            "RSP": self.make_equity_bars("RSP", start_price=155, pre_event_return=0.05, june4_return=0.002, june5_return=0.003),
            "IWM": self.make_equity_bars("IWM", start_price=205, pre_event_return=0.05, june4_return=0.002, june5_return=0.003),
            "NVDA": self.make_equity_bars("NVDA", start_price=820, pre_event_return=0.85, june4_return=-0.035, june5_return=0.014),
            "AVGO": self.make_equity_bars("AVGO", start_price=760, pre_event_return=0.75, june4_return=-0.034, june5_return=0.012),
            "AMD": self.make_equity_bars("AMD", start_price=130, pre_event_return=0.65, june4_return=-0.032, june5_return=0.012),
            "TSLA": self.make_equity_bars("TSLA", start_price=250, pre_event_return=0.40, june4_return=-0.030, june5_return=0.010),
            "META": self.make_equity_bars("META", start_price=540, pre_event_return=0.35, june4_return=-0.028, june5_return=0.008),
            "MSFT": self.make_equity_bars("MSFT", start_price=420, pre_event_return=0.30, june4_return=-0.026, june5_return=0.006),
            "AAPL": self.make_equity_bars("AAPL", start_price=190, pre_event_return=0.28, june4_return=-0.024, june5_return=0.006),
            "AMZN": self.make_equity_bars("AMZN", start_price=175, pre_event_return=0.32, june4_return=-0.024, june5_return=0.006),
            "GOOGL": self.make_equity_bars("GOOGL", start_price=150, pre_event_return=0.30, june4_return=-0.024, june5_return=0.006),
        }

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2026, 6, 4),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertEqual(risk["regime"], "Caution")

    def test_equity_short_term_risk_dampens_crowded_rollover_without_event_or_vol_confirmation(self):
        market_bars = {
            "SPY": self.make_equity_bars("SPY", start_price=680, pre_event_return=0.103, june4_return=0.0038, june5_return=0.006, june4_volume_multiplier=0.72),
            "QQQ": self.make_equity_bars("QQQ", start_price=520, pre_event_return=0.218, june4_return=-0.0048, june5_return=0.006),
            "SMH": self.make_equity_bars("SMH", start_price=190, pre_event_return=0.544, june4_return=-0.0163, june5_return=0.008),
            "XLK": self.make_equity_bars("XLK", start_price=180, pre_event_return=0.384, june4_return=-0.0156, june5_return=0.006),
            "TLT": self.make_equity_bars("TLT", start_price=88, pre_event_return=-0.021, june4_return=-0.002, june5_return=0.006),
            "RSP": self.make_equity_bars("RSP", start_price=170, pre_event_return=0.031, june4_return=0.0076, june5_return=0.003),
            "IWM": self.make_equity_bars("IWM", start_price=210, pre_event_return=0.107, june4_return=0.0151, june5_return=0.003),
            "XLV": self.make_equity_bars("XLV", start_price=140, pre_event_return=-0.041, june4_return=0.0307, june5_return=0.006),
            "AMD": self.make_equity_bars("AMD", start_price=80, pre_event_return=1.63, june4_return=-0.0356, june5_return=0.008),
            "AVGO": self.make_equity_bars("AVGO", start_price=700, pre_event_return=0.314, june4_return=-0.1259, june5_return=0.008),
            "TSLA": self.make_equity_bars("TSLA", start_price=320, pre_event_return=0.038, june4_return=-0.0124, june5_return=0.006),
            "META": self.make_equity_bars("META", start_price=620, pre_event_return=-0.04, june4_return=0.0074, june5_return=0.006),
            "MSFT": self.make_equity_bars("MSFT", start_price=460, pre_event_return=0.074, june4_return=0.0017, june5_return=0.006),
        }

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2026, 6, 4),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_equity_short_term_risk_dampens_post_washout_vol_without_sector_confirmation(self):
        def bars(symbol: str, closes: list[float], ranges: list[float]) -> list[MarketDailyBar]:
            return self.make_equity_bars_from_closes_and_ranges(symbol, closes, ranges)

        pre = [100.0 + index * 0.03 for index in range(44)]
        spy_closes = pre + [102, 101, 99, 97, 94, 91, 88, 89, 90, 91, 90, 89, 88, 87, 86, 85, 86, 87, 86, 85]
        qqq_closes = pre + [103, 101, 98, 95, 91, 87, 83, 84, 85, 86, 85, 84, 83, 82, 81, 80, 81, 82, 80, 79]
        tlt_closes = pre + [100, 99, 98, 97, 96, 95, 94, 93.5, 93, 92.5, 92, 91.5, 91, 90.5, 90, 89.5, 89, 88.7, 88.5, 88.3]
        defensive_closes = [100.0 + index * 0.02 for index in range(len(spy_closes))]
        hot_closes = pre + [120, 118, 114, 110, 105, 100, 96, 98, 100, 102, 104, 106, 108, 110, 112, 114, 113, 112, 108 / 0.96, 108]
        ranges = [0.006] * 44 + [0.055] * 20
        market_bars = {
            "SPY": bars("SPY", spy_closes, ranges),
            "QQQ": bars("QQQ", qqq_closes, ranges),
            "TLT": bars("TLT", tlt_closes, ranges),
            "SMH": bars("SMH", qqq_closes, ranges),
            "XLK": bars("XLK", qqq_closes, ranges),
            "RSP": bars("RSP", spy_closes, ranges),
            "IWM": bars("IWM", spy_closes, ranges),
            "XLV": bars("XLV", defensive_closes, ranges),
            "XLU": bars("XLU", defensive_closes, ranges),
            "XLP": bars("XLP", defensive_closes, ranges),
        }
        for symbol in ("NVDA", "AVGO", "AMD", "TSLA", "META", "MSFT"):
            market_bars[symbol] = bars(symbol, hot_closes, ranges)

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2025, 5, 1),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_equity_short_term_risk_attaches_source_quality_and_factor_evidence(self):
        market_bars = {
            "SPY": self.make_equity_bars("SPY", start_price=620, pre_event_return=0.10, june4_return=-0.006, june5_return=0.003, june4_volume_multiplier=0.82),
            "QQQ": self.make_equity_bars("QQQ", start_price=510, pre_event_return=0.16, june4_return=-0.015, june5_return=0.002),
            "SMH": self.make_equity_bars("SMH", start_price=245, pre_event_return=0.32, june4_return=-0.022, june5_return=0.003),
            "XLK": self.make_equity_bars("XLK", start_price=230, pre_event_return=0.18, june4_return=-0.014, june5_return=0.002),
            "TLT": self.make_equity_bars("TLT", start_price=88, pre_event_return=-0.02, june4_return=-0.003, june5_return=0.002),
            "RSP": self.make_equity_bars("RSP", start_price=185, pre_event_return=0.04, june4_return=0.001, june5_return=0.002),
            "IWM": self.make_equity_bars("IWM", start_price=215, pre_event_return=0.03, june4_return=-0.002, june5_return=0.002),
            "XLV": self.make_equity_bars("XLV", start_price=145, pre_event_return=0.02, june4_return=0.002, june5_return=0.001),
            "XLU": self.make_equity_bars("XLU", start_price=74, pre_event_return=0.02, june4_return=0.002, june5_return=0.001),
            "XLP": self.make_equity_bars("XLP", start_price=82, pre_event_return=0.02, june4_return=0.002, june5_return=0.001),
            "NVDA": self.make_equity_bars("NVDA", start_price=820, pre_event_return=0.55, june4_return=-0.030, june5_return=0.006),
            "AVGO": self.make_equity_bars("AVGO", start_price=760, pre_event_return=0.42, june4_return=-0.028, june5_return=0.006),
            "AMD": self.make_equity_bars("AMD", start_price=130, pre_event_return=0.36, june4_return=-0.026, june5_return=0.006),
            "TSLA": self.make_equity_bars("TSLA", start_price=250, pre_event_return=0.30, june4_return=-0.020, june5_return=0.005),
            "META": self.make_equity_bars("META", start_price=540, pre_event_return=0.24, june4_return=-0.018, june5_return=0.004),
            "MSFT": self.make_equity_bars("MSFT", start_price=420, pre_event_return=0.18, june4_return=-0.015, june5_return=0.003),
        }
        option_snapshot = OptionOpenInterestSnapshot(
            symbol="SPY",
            as_of=date(2026, 6, 5),
            timestamp=datetime(2026, 6, 5, 21, 0, tzinfo=timezone.utc),
            put_open_interest=1_300_000,
            call_open_interest=900_000,
            put_volume=820_000,
            call_volume=700_000,
            put_call_open_interest_ratio=1.44,
            put_call_volume_ratio=1.17,
            current_price=620.0,
            source="Cboe delayed option snapshot",
        )

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2026, 6, 4),
            macro_liquidity_equity={"currentSignal": {"score3mChange": 8.0}},
            spy_early_warning={"score": 64.0},
            calendar_events=[CalendarEvent(date(2026, 6, 8), "BLS Employment Situation", "BLS", "高")],
            option_open_interest=option_snapshot,
        )

        self.assertGreaterEqual(risk["sourceQuality"]["scoreEligibleWeightPct"], 90.0)
        self.assertGreaterEqual(risk["sourceQuality"]["historicalReplayableWeightPct"], 70.0)
        self.assertEqual(risk["forwardCatalystRisk"]["windowDays"], 5)
        self.assertEqual(risk["forwardCatalystRisk"]["eventCount"], 1)
        evidence_by_component = {item["component"]: item for item in risk["factorEvidence"]}
        self.assertEqual(evidence_by_component["volTargetPressure"]["sourceQuality"], "high")
        self.assertTrue(evidence_by_component["volTargetPressure"]["historicalReplay"])
        self.assertEqual(evidence_by_component["qqqTltRotation"]["sourceQuality"], "high")
        self.assertTrue(evidence_by_component["qqqTltRotation"]["historicalReplay"])
        self.assertEqual(evidence_by_component["marketFlow"]["sourceQuality"], "high")
        self.assertEqual(evidence_by_component["marketFlow"]["scoreUse"], "scored")
        self.assertTrue(evidence_by_component["marketFlow"]["historicalReplay"])
        self.assertEqual(evidence_by_component["optionOI"]["scoreUse"], "auditOnly")
        self.assertFalse(evidence_by_component["optionOI"]["historicalReplay"])

    def test_equity_short_term_risk_dampens_repair_rally_after_deep_washout(self):
        base = [100.0 + index * 0.08 for index in range(40)]
        spy_closes = base + [104, 103, 101, 98, 95, 92, 90, 91, 92, 93, 94, 95, 96, 97, 98, 97, 96, 97, 98, 99]
        leader_closes = base + [103, 101, 99, 96, 93, 90, 87, 87.5, 88, 88.5, 89, 89.5, 90, 90.5, 91, 90.5, 90, 90.5, 91, 92]
        defensive_closes = [100.0 + index * 0.08 for index in range(40)] + [104, 104.5, 105, 105.5, 106, 106.5, 107, 107.5, 108, 108.5, 109, 109.5, 110, 110.5, 111, 111.5, 112, 112.5, 113, 113.5]
        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", spy_closes, last_volume_multiplier=1.30),
            "QQQ": self.make_equity_bars_from_closes("QQQ", leader_closes),
            "SMH": self.make_equity_bars_from_closes("SMH", leader_closes),
            "XLK": self.make_equity_bars_from_closes("XLK", leader_closes),
            "RSP": self.make_equity_bars_from_closes("RSP", spy_closes),
            "IWM": self.make_equity_bars_from_closes("IWM", spy_closes),
            "XLV": self.make_equity_bars_from_closes("XLV", defensive_closes),
            "XLU": self.make_equity_bars_from_closes("XLU", defensive_closes),
            "XLP": self.make_equity_bars_from_closes("XLP", defensive_closes),
            "NVDA": self.make_equity_bars_from_closes("NVDA", leader_closes),
            "AVGO": self.make_equity_bars_from_closes("AVGO", leader_closes),
            "AMD": self.make_equity_bars_from_closes("AMD", leader_closes),
            "TSLA": self.make_equity_bars_from_closes("TSLA", leader_closes),
            "META": self.make_equity_bars_from_closes("META", leader_closes),
            "MSFT": self.make_equity_bars_from_closes("MSFT", leader_closes),
        }

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2025, 4, 25),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_equity_short_term_risk_dampens_narrow_leader_washout_without_catalyst(self):
        def phase(start: float, middle: float, end: float, first_leg: int = 44, second_leg: int = 20) -> list[float]:
            closes = [start + (middle - start) * index / (first_leg - 1) for index in range(first_leg)]
            closes.extend(middle + (end - middle) * index / second_leg for index in range(1, second_leg + 1))
            return closes

        spy_closes = phase(100, 108, 102)
        spy_closes[-2] = 102 / 0.985
        leader_closes = phase(100, 118, 110)
        leader_closes[-2] = 110 / 0.968
        defensive_closes = phase(100, 108, 113)
        rsp_closes = phase(100, 103, 101)
        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", spy_closes, last_volume_multiplier=1.60),
            "QQQ": self.make_equity_bars_from_closes("QQQ", leader_closes),
            "SMH": self.make_equity_bars_from_closes("SMH", leader_closes),
            "XLK": self.make_equity_bars_from_closes("XLK", leader_closes),
            "RSP": self.make_equity_bars_from_closes("RSP", rsp_closes),
            "IWM": self.make_equity_bars_from_closes("IWM", rsp_closes),
            "XLV": self.make_equity_bars_from_closes("XLV", defensive_closes),
            "XLU": self.make_equity_bars_from_closes("XLU", defensive_closes),
            "XLP": self.make_equity_bars_from_closes("XLP", defensive_closes),
        }
        for index, symbol in enumerate(("NVDA", "AVGO", "AMD", "TSLA", "META", "MSFT")):
            closes = phase(100, 160, 145)
            closes[-2] = 145 / (0.965 if index < 2 else 0.985)
            market_bars[symbol] = self.make_equity_bars_from_closes(symbol, closes)

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2025, 5, 1),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_equity_short_term_risk_dampens_aftershock_stabilization_without_fresh_sell_pressure(self):
        def phase(start: float, middle: float, end: float, first_leg: int = 44, second_leg: int = 20) -> list[float]:
            closes = [start + (middle - start) * index / (first_leg - 1) for index in range(first_leg)]
            closes.extend(middle + (end - middle) * index / second_leg for index in range(1, second_leg + 1))
            return closes

        spy_closes = phase(100, 108, 100.3)
        spy_closes[-2] = 100.3 / 0.9933
        leader_closes = phase(100, 116, 96)
        leader_closes[-2] = 96 / 0.976
        defensive_closes = phase(100, 106, 114)
        hot_closes = phase(100, 150, 128)
        hot_closes[-2] = 128 / 0.975
        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", spy_closes, last_volume_multiplier=1.40),
            "QQQ": self.make_equity_bars_from_closes("QQQ", leader_closes),
            "SMH": self.make_equity_bars_from_closes("SMH", leader_closes),
            "XLK": self.make_equity_bars_from_closes("XLK", leader_closes),
            "RSP": self.make_equity_bars_from_closes("RSP", phase(100, 103, 100)),
            "IWM": self.make_equity_bars_from_closes("IWM", phase(100, 103, 100)),
            "XLV": self.make_equity_bars_from_closes("XLV", defensive_closes),
            "XLU": self.make_equity_bars_from_closes("XLU", defensive_closes),
            "XLP": self.make_equity_bars_from_closes("XLP", defensive_closes),
            "NVDA": self.make_equity_bars_from_closes("NVDA", hot_closes),
            "AVGO": self.make_equity_bars_from_closes("AVGO", hot_closes),
            "AMD": self.make_equity_bars_from_closes("AMD", hot_closes),
            "TSLA": self.make_equity_bars_from_closes("TSLA", hot_closes),
            "META": self.make_equity_bars_from_closes("META", hot_closes),
            "MSFT": self.make_equity_bars_from_closes("MSFT", hot_closes),
        }

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2025, 5, 1),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_equity_short_term_risk_dampens_hot_rotation_without_market_flow_confirmation(self):
        market_bars = {
            "SPY": self.make_equity_bars("SPY", start_price=520, pre_event_return=0.10, june4_return=-0.012, june5_return=0.006, june4_volume_multiplier=0.45),
            "QQQ": self.make_equity_bars("QQQ", start_price=420, pre_event_return=0.24, june4_return=-0.022, june5_return=0.006),
            "SMH": self.make_equity_bars("SMH", start_price=180, pre_event_return=0.45, june4_return=-0.028, june5_return=0.008),
            "XLK": self.make_equity_bars("XLK", start_price=170, pre_event_return=0.25, june4_return=-0.022, june5_return=0.006),
            "RSP": self.make_equity_bars("RSP", start_price=155, pre_event_return=0.00, june4_return=-0.002, june5_return=0.003),
            "IWM": self.make_equity_bars("IWM", start_price=205, pre_event_return=0.00, june4_return=-0.002, june5_return=0.003),
        }
        for symbol in ("NVDA", "AVGO", "AMD", "TSLA", "META", "MSFT"):
            market_bars[symbol] = self.make_equity_bars(symbol, start_price=300, pre_event_return=0.60, june4_return=-0.030, june5_return=0.006)

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2026, 6, 4),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_equity_short_term_risk_dampens_shallow_distribution_without_catalyst(self):
        def phase(start: float, middle: float, end: float, first_leg: int = 44, second_leg: int = 20) -> list[float]:
            closes = [start + (middle - start) * index / (first_leg - 1) for index in range(first_leg)]
            closes.extend(middle + (end - middle) * index / second_leg for index in range(1, second_leg + 1))
            return closes

        spy_closes = phase(100, 108, 102)
        spy_closes[-2] = 102 / 0.9913
        leader_closes = phase(100, 112, 106)
        leader_closes[-2] = 106 / 0.970
        defensive_closes = phase(100, 106, 109)
        hot_closes = phase(100, 150, 140)
        hot_closes[-2] = 140 / 0.965
        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", spy_closes, last_volume_multiplier=1.60),
            "QQQ": self.make_equity_bars_from_closes("QQQ", leader_closes),
            "SMH": self.make_equity_bars_from_closes("SMH", leader_closes),
            "XLK": self.make_equity_bars_from_closes("XLK", leader_closes),
            "RSP": self.make_equity_bars_from_closes("RSP", phase(100, 103, 101)),
            "IWM": self.make_equity_bars_from_closes("IWM", phase(100, 103, 101)),
            "XLV": self.make_equity_bars_from_closes("XLV", defensive_closes),
            "XLU": self.make_equity_bars_from_closes("XLU", defensive_closes),
            "XLP": self.make_equity_bars_from_closes("XLP", defensive_closes),
            "NVDA": self.make_equity_bars_from_closes("NVDA", hot_closes),
            "AVGO": self.make_equity_bars_from_closes("AVGO", hot_closes),
            "AMD": self.make_equity_bars_from_closes("AMD", hot_closes),
            "TSLA": self.make_equity_bars_from_closes("TSLA", hot_closes),
            "META": self.make_equity_bars_from_closes("META", hot_closes),
            "MSFT": self.make_equity_bars_from_closes("MSFT", hot_closes),
        }

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2025, 5, 1),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_equity_short_term_risk_dampens_sector_specific_semiconductor_slump_when_spy20_positive(self):
        pre = [100.0 + index * 0.02 for index in range(44)]
        spy_closes = pre + [100, 101, 102, 103, 104, 105, 107, 106.5, 106, 105.5, 105, 104.5, 104, 103.5, 103, 103.5, 104, 105, 102 / 0.9832, 102]
        leader_closes = pre + [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 86, 87, 84 / 0.97, 84]
        defensive_closes = [100.0 + index * 0.02 for index in range(44)] + [101, 101.3, 101.6, 102, 102.4, 102.8, 103.2, 103.6, 104, 104.4, 104.8, 105, 105.2, 105.4, 105.6, 105.8, 106, 106.2, 106.4, 106.6]
        hot_closes = pre + [102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 118, 116, 114, 112, 110, 108, 107, 106, 104 / 0.965, 104]
        rsp_closes = pre + [100, 100.2, 100.4, 100.6, 100.8, 101, 101.2, 101.4, 101.6, 101.8, 102, 101.8, 101.6, 101.4, 101.2, 101, 100.8, 100.6, 100.4, 100.2]
        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", spy_closes, last_volume_multiplier=1.45),
            "QQQ": self.make_equity_bars_from_closes("QQQ", leader_closes),
            "SMH": self.make_equity_bars_from_closes("SMH", leader_closes),
            "XLK": self.make_equity_bars_from_closes("XLK", leader_closes),
            "RSP": self.make_equity_bars_from_closes("RSP", rsp_closes),
            "IWM": self.make_equity_bars_from_closes("IWM", rsp_closes),
            "XLV": self.make_equity_bars_from_closes("XLV", defensive_closes),
            "XLU": self.make_equity_bars_from_closes("XLU", defensive_closes),
            "XLP": self.make_equity_bars_from_closes("XLP", defensive_closes),
            "NVDA": self.make_equity_bars_from_closes("NVDA", hot_closes),
            "AVGO": self.make_equity_bars_from_closes("AVGO", hot_closes),
            "AMD": self.make_equity_bars_from_closes("AMD", hot_closes),
            "TSLA": self.make_equity_bars_from_closes("TSLA", hot_closes),
            "META": self.make_equity_bars_from_closes("META", hot_closes),
            "MSFT": self.make_equity_bars_from_closes("MSFT", hot_closes),
        }

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2025, 5, 1),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_equity_short_term_risk_dampens_light_hot_damage_without_broad_confirmation(self):
        pre = [100.0 + index * 0.04 for index in range(44)]
        spy_closes = pre + [101, 102, 103, 104, 105, 106, 105.5, 105, 104.5, 104, 103.5, 103, 102.5, 102, 101.5, 101, 100.5, 101.5, 101 / 0.9861, 101]
        leader_closes = pre + [101, 102, 103, 104, 105, 106, 105, 104, 103, 102, 101, 100, 99.5, 99, 98.5, 98, 97.5, 98, 97 / 0.976, 97]
        defensive_closes = pre + [101, 102, 103, 104, 105, 105.5, 105, 104.5, 104, 103.5, 103, 102.5, 102, 101.5, 101, 100.8, 100.6, 101, 100.8, 100.6]
        rsp_closes = pre + [101, 102, 103, 104, 105, 105.5, 105, 104.5, 104, 103.5, 103, 102.5, 102, 101.5, 101, 100.8, 100.6, 101, 100.8, 100.5]
        hot_base = pre + [101, 103, 105, 107, 109, 111, 113, 115, 116, 117, 118, 119, 120, 119, 118, 117, 116, 115, 114 / 0.98, 114]
        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", spy_closes, last_volume_multiplier=1.20),
            "QQQ": self.make_equity_bars_from_closes("QQQ", leader_closes),
            "SMH": self.make_equity_bars_from_closes("SMH", leader_closes),
            "XLK": self.make_equity_bars_from_closes("XLK", leader_closes),
            "RSP": self.make_equity_bars_from_closes("RSP", rsp_closes),
            "IWM": self.make_equity_bars_from_closes("IWM", rsp_closes),
            "XLV": self.make_equity_bars_from_closes("XLV", defensive_closes),
            "XLU": self.make_equity_bars_from_closes("XLU", defensive_closes),
            "XLP": self.make_equity_bars_from_closes("XLP", defensive_closes),
        }
        for index, symbol in enumerate(("NVDA", "AVGO", "AMD", "TSLA", "META", "MSFT")):
            closes = list(hot_base)
            closes[-2] = 114 / (0.965 if index == 0 else 0.986)
            market_bars[symbol] = self.make_equity_bars_from_closes(symbol, closes)

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2025, 5, 1),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=[],
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_equity_short_term_risk_dampens_event_watch_without_market_confirmation(self):
        market_bars = {
            "SPY": self.make_equity_bars("SPY", start_price=520, pre_event_return=0.10, june4_return=-0.002, june5_return=0.006, june4_volume_multiplier=0.80),
            "QQQ": self.make_equity_bars("QQQ", start_price=420, pre_event_return=0.24, june4_return=-0.017, june5_return=0.006),
            "SMH": self.make_equity_bars("SMH", start_price=180, pre_event_return=0.45, june4_return=-0.022, june5_return=0.008),
            "XLK": self.make_equity_bars("XLK", start_price=170, pre_event_return=0.25, june4_return=-0.017, june5_return=0.006),
            "RSP": self.make_equity_bars("RSP", start_price=155, pre_event_return=0.00, june4_return=0.001, june5_return=0.003),
            "IWM": self.make_equity_bars("IWM", start_price=205, pre_event_return=0.00, june4_return=0.001, june5_return=0.003),
        }
        for symbol in ("NVDA", "AVGO", "AMD", "TSLA", "META", "MSFT"):
            market_bars[symbol] = self.make_equity_bars(symbol, start_price=300, pre_event_return=0.60, june4_return=-0.014, june5_return=0.006)
        events = [CalendarEvent(date=date(2026, 6, 5), title="BLS Producer Price Index", source="unit-test", importance="高")]

        risk = equity_short_term_signal_at(
            dashboard_builder.normalize_market_bars(market_bars),
            date(2026, 6, 4),
            macro_liquidity_equity={},
            spy_early_warning={},
            calendar_events=events,
            option_open_interest=None,
        )

        self.assertLess(risk["score"], 75)
        self.assertNotEqual(risk["regime"], "Strong Alert")

    def test_build_live_dashboard_treats_announced_auction_outage_as_warning(self):
        patches = {
            "fetch_treasury_yield_curves": [],
            "fetch_fred_series_bulk": {},
            "fetch_treasury_auctions": [],
            "fetch_fomc_calendar_events": [],
            "fetch_fred_macro_release_events": [],
            "fetch_bea_release_events": [],
            "fetch_fomc_projection": None,
            "fetch_acm_term_premium": None,
            "fetch_cftc_treasury_positions": [],
            "fetch_tic_major_holders": None,
            "fetch_primary_dealer_stats": None,
            "fetch_quarterly_refunding": None,
            "fetch_debt_limit_status": None,
            "fetch_fed_funds_futures_quote": None,
            "fetch_gold_spot_quote": None,
            "fetch_cboe_option_open_interest": None,
            "fetch_federal_reserve_press_releases": [],
            "fetch_treasury_press_releases": [],
            "load_content_overrides": {},
            "fetch_bhadial_public_score": 43.4,
        }
        with ExitStack() as stack:
            for name, return_value in patches.items():
                stack.enter_context(patch.object(dashboard_builder, name, return_value=return_value))
            stack.enter_context(patch.object(dashboard_builder, "fetch_announced_auctions", side_effect=RuntimeError("HTTP 500")))
            stack.enter_context(patch.object(dashboard_builder, "fetch_daily_bars_with_stooq_fallback", side_effect=RuntimeError("skip market fetch")))
            stack.enter_context(patch.object(dashboard_builder, "build_dashboard_from_inputs", return_value={"sourceStatus": []}))

            dashboard = dashboard_builder.build_live_dashboard()

        status_by_name = {item["name"]: item["status"] for item in dashboard["sourceStatus"]}
        self.assertEqual(status_by_name["TreasuryDirect announced securities"], "warning")

    def test_build_live_dashboard_falls_back_to_cached_auction_history(self):
        captured: dict[str, object] = {}

        def fake_build_dashboard_from_inputs(**kwargs):
            captured["auctions"] = kwargs["auctions"]
            return {"sourceStatus": [], "macroLiquidity": {"score": 43.4}}

        patches = {
            "fetch_treasury_yield_curves": [],
            "fetch_fred_series_bulk": {},
            "fetch_announced_auctions": [],
            "fetch_fomc_calendar_events": [],
            "fetch_fred_macro_release_events": [],
            "fetch_bea_release_events": [],
            "fetch_fomc_projection": None,
            "fetch_acm_term_premium": None,
            "fetch_cftc_treasury_positions": [],
            "fetch_tic_major_holders": None,
            "fetch_primary_dealer_stats": None,
            "fetch_quarterly_refunding": None,
            "fetch_debt_limit_status": None,
            "fetch_fed_funds_futures_quote": None,
            "fetch_gold_spot_quote": None,
            "fetch_cboe_option_open_interest": None,
            "fetch_federal_reserve_press_releases": [],
            "fetch_treasury_press_releases": [],
            "load_content_overrides": {},
        }
        cached_auctions = [{"auctionDate": "2026-05-21", "securityTerm": "9-Year 8-Month", "securityType": "Note", "bidToCoverRatio": "2.52"}]
        with ExitStack() as stack:
            for name, return_value in patches.items():
                stack.enter_context(patch.object(dashboard_builder, name, return_value=return_value))
            stack.enter_context(patch.object(dashboard_builder, "fetch_treasury_auctions", side_effect=RuntimeError("curl timeout")))
            stack.enter_context(patch.object(dashboard_builder, "load_historical_auction_fallback", return_value=cached_auctions))
            stack.enter_context(patch.object(dashboard_builder, "fetch_bhadial_public_score", return_value=43.4))
            stack.enter_context(patch.object(dashboard_builder, "fetch_daily_bars_with_stooq_fallback", side_effect=RuntimeError("skip market fetch")))
            stack.enter_context(patch.object(dashboard_builder, "build_dashboard_from_inputs", side_effect=fake_build_dashboard_from_inputs))

            dashboard = dashboard_builder.build_live_dashboard()

        self.assertEqual(captured["auctions"], cached_auctions)
        auction_status = next(item for item in dashboard["sourceStatus"] if item["name"] == "TreasuryDirect auctioned securities")
        self.assertEqual(auction_status["status"], "warning")
        self.assertIn("cached observations", auction_status["latest"])
        self.assertEqual(dashboard["macroLiquidity"]["benchmark"]["score"], 43.4)

    def test_build_live_dashboard_falls_back_to_fred_dgs_curve_when_treasury_xml_fails(self):
        captured: dict[str, object] = {}
        dgs_points = {
            "DGS1MO": 3.60,
            "DGS3MO": 3.61,
            "DGS6MO": 3.62,
            "DGS1": 3.70,
            "DGS2": 3.82,
            "DGS3": 3.88,
            "DGS5": 4.01,
            "DGS7": 4.14,
            "DGS10": 4.30,
            "DGS20": 4.75,
            "DGS30": 4.82,
        }

        def fake_fred_bulk(series_ids, **_kwargs):
            requested = list(series_ids)
            return {
                series_id: TimeSeries(series_id, [SeriesPoint(date(2026, 6, 10), value)])
                for series_id, value in dgs_points.items()
                if series_id in requested
            }

        def fake_build_dashboard_from_inputs(**kwargs):
            captured["curve_records"] = kwargs["curve_records"]
            return {"sourceStatus": [], "macroLiquidity": {"score": 43.4}}

        patches = {
            "fetch_treasury_auctions": [],
            "fetch_announced_auctions": [],
            "fetch_fomc_calendar_events": [],
            "fetch_fred_macro_release_events": [],
            "fetch_bea_release_events": [],
            "fetch_fomc_projection": None,
            "fetch_acm_term_premium": None,
            "fetch_cftc_treasury_positions": [],
            "fetch_tic_major_holders": None,
            "fetch_primary_dealer_stats": None,
            "fetch_quarterly_refunding": None,
            "fetch_debt_limit_status": None,
            "fetch_fed_funds_futures_quote": None,
            "fetch_gold_spot_quote": None,
            "fetch_cboe_option_open_interest": None,
            "fetch_federal_reserve_press_releases": [],
            "fetch_treasury_press_releases": [],
            "load_content_overrides": {},
            "fetch_bhadial_public_score": 43.4,
        }
        with ExitStack() as stack:
            for name, return_value in patches.items():
                stack.enter_context(patch.object(dashboard_builder, name, return_value=return_value))
            stack.enter_context(patch.object(dashboard_builder, "fetch_treasury_yield_curves", side_effect=RuntimeError("Treasury XML timeout")))
            stack.enter_context(patch.object(dashboard_builder, "fetch_fred_series_bulk", side_effect=fake_fred_bulk))
            stack.enter_context(patch.object(dashboard_builder, "fetch_nasdaq_daily_bars", side_effect=RuntimeError("skip market fetch")))
            stack.enter_context(patch.object(dashboard_builder, "fetch_stooq_daily_bars", side_effect=RuntimeError("skip fallback")))
            stack.enter_context(patch.object(dashboard_builder, "build_dashboard_from_inputs", side_effect=fake_build_dashboard_from_inputs))

            dashboard = dashboard_builder.build_live_dashboard()

        curve_records = captured["curve_records"]
        self.assertEqual(len(curve_records), 1)
        self.assertEqual(curve_records[0].date, date(2026, 6, 10))
        self.assertEqual(curve_records[0].values["10Y"], 4.30)
        curve_status = next(item for item in dashboard["sourceStatus"] if item["name"] == "U.S. Treasury yield curve XML")
        self.assertEqual(curve_status["status"], "warning")
        self.assertIn("FRED DGS fallback", curve_status["latest"])

    def test_build_live_dashboard_falls_back_to_stooq_when_nasdaq_daily_bars_fail(self):
        captured: dict[str, object] = {}

        # Pin the wall clock so the equity-OHLCV freshness check (2-day cadence) is
        # deterministic regardless of when the suite runs; the stooq bars end 2026-06-10.
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 6, 11, tzinfo=tz)

        def fake_stooq(symbol: str, *, start: date, end: date, timeout: int = 14):
            return [
                MarketDailyBar(symbol=symbol.upper(), date=date(2026, 6, 9), open=100.0, high=101.0, low=99.0, close=100.5, volume=10_000, source=f"stooq:{symbol}"),
                MarketDailyBar(symbol=symbol.upper(), date=date(2026, 6, 10), open=100.5, high=102.0, low=100.0, close=101.5, volume=12_000, source=f"stooq:{symbol}"),
            ]

        def fake_build_dashboard_from_inputs(**kwargs):
            captured["equity_market_bars"] = kwargs["equity_market_bars"]
            captured["global_lppl_market_bars"] = kwargs["global_lppl_market_bars"]
            return {"sourceStatus": [], "macroLiquidity": {"score": 43.4}}

        patches = {
            "fetch_treasury_yield_curves": [],
            "fetch_fred_series_bulk": {},
            "fetch_treasury_auctions": [],
            "fetch_announced_auctions": [],
            "fetch_fomc_calendar_events": [],
            "fetch_fred_macro_release_events": [],
            "fetch_bea_release_events": [],
            "fetch_fomc_projection": None,
            "fetch_acm_term_premium": None,
            "fetch_cftc_treasury_positions": [],
            "fetch_tic_major_holders": None,
            "fetch_primary_dealer_stats": None,
            "fetch_quarterly_refunding": None,
            "fetch_debt_limit_status": None,
            "fetch_fed_funds_futures_quote": None,
            "fetch_gold_spot_quote": None,
            "fetch_cboe_option_open_interest": None,
            "fetch_federal_reserve_press_releases": [],
            "fetch_treasury_press_releases": [],
            "load_content_overrides": {},
            "fetch_bhadial_public_score": 43.4,
        }
        with ExitStack() as stack:
            for name, return_value in patches.items():
                stack.enter_context(patch.object(dashboard_builder, name, return_value=return_value))
            stack.enter_context(patch.object(dashboard_builder, "fetch_nasdaq_daily_bars", side_effect=RuntimeError("Nasdaq blocked")))
            stack.enter_context(patch.object(dashboard_builder, "fetch_stooq_daily_bars", side_effect=fake_stooq))
            stack.enter_context(patch.object(dashboard_builder, "build_dashboard_from_inputs", side_effect=fake_build_dashboard_from_inputs))
            stack.enter_context(patch.object(dashboard_builder, "datetime", FixedDatetime))

            dashboard = dashboard_builder.build_live_dashboard()

        self.assertIn("SPY", captured["equity_market_bars"])
        self.assertIn("SPY", captured["global_lppl_market_bars"])
        spy_status = next(item for item in dashboard["sourceStatus"] if item["name"] == "Nasdaq SPY OHLCV")
        self.assertEqual(spy_status["status"], "ok")
        self.assertEqual(spy_status["latest"], "2026-06-10")
        self.assertEqual(spy_status["source"], "stooq-fallback")
        self.assertIn("Nasdaq blocked", spy_status["note"])

    def test_source_freshness_marks_slow_public_sources_stale(self):
        rows = [
            {"name": "NY Fed ACM term premium", "status": "ok", "latest": "2026-03-01"},
            {"name": "CFTC financial futures COT", "status": "ok", "latest": "2026-06-05"},
        ]

        annotated = dashboard_builder.annotate_source_status_freshness(rows, as_of=date(2026, 6, 11))

        acm = next(row for row in annotated if row["name"] == "NY Fed ACM term premium")
        cftc = next(row for row in annotated if row["name"] == "CFTC financial futures COT")
        self.assertEqual(acm["status"], "stale")
        self.assertEqual(acm["ageDays"], 102)
        self.assertEqual(acm["expectedMaxAgeDays"], 45)
        self.assertEqual(cftc["status"], "ok")
        self.assertEqual(cftc["ageDays"], 6)

    def test_lppl_candidate_selection_prefers_fit_quality_over_risk_score(self):
        selected = dashboard_builder.select_lppl_fit_candidate(
            [
                {"available": True, "score": 92.0, "confidence": 0.90, "fitR2": 0.71, "daysToCritical": 15, "windowDays": 180},
                {"available": True, "score": 63.0, "confidence": 0.62, "fitR2": 0.94, "daysToCritical": 60, "windowDays": 252},
            ]
        )

        self.assertEqual(selected["daysToCritical"], 60)
        self.assertEqual(selected["daysToCriticalRange"]["min"], 15)
        self.assertEqual(selected["daysToCriticalRange"]["max"], 60)
        self.assertEqual(selected["selectionBasis"], "fit_quality")

    def test_lppl_signal_reports_documented_multi_window_ensemble(self):
        bars = self.make_equity_bars_from_closes(
            "SPY",
            [100 + index * 0.22 for index in range(780)],
        )
        windows: list[int] = []

        def fake_fit_lppl_window(sample, *, fast=False):
            window = len(sample)
            windows.append(window)
            return {
                "available": True,
                "score": 60.0 + len(windows),
                "confidence": 0.55 + len(windows) * 0.01,
                "fitR2": 0.80 + len(windows) * 0.01,
                "fitSse": 10.0 - len(windows),
                "daysToCritical": 20 + len(windows) * 10,
                "windowDays": window,
                "passesLpplDiagnostics": len(windows) <= 4,
            }

        with patch.object(dashboard_builder, "fit_lppl_window", side_effect=fake_fit_lppl_window):
            fit = dashboard_builder.fit_global_lppl_signal(bars)

        self.assertEqual(windows, [120, 180, 252, 375, 500, 750])
        ensemble = fit["fitEnsemble"]
        self.assertEqual(ensemble["totalFitCount"], 6)
        self.assertEqual(ensemble["validFitCount"], 6)
        self.assertEqual(ensemble["windowDays"], [120, 180, 252, 375, 500, 750])
        self.assertEqual(ensemble["tcLeadDaysQ20"], 40)
        self.assertEqual(ensemble["tcLeadDaysMedian"], 55)
        self.assertEqual(ensemble["tcLeadDaysQ80"], 70)
        self.assertEqual(ensemble["residualPassRatioPct"], 66.7)
        self.assertIn(ensemble["windowAgreement"], {"tight", "moderate", "scattered"})

    def test_lppl_window_reports_power_law_improvement_and_oscillation_count(self):
        n = dashboard_builder.GLOBAL_LPPL_DEFAULT_WINDOW
        tc = n - 1 + 60
        closes = []
        for t in range(n):
            distance = tc - t
            y = (
                5.10
                - 0.012 * (distance ** 0.55)
                + 0.0018 * (distance ** 0.55) * math.cos(10.0 * math.log(distance))
                + 0.0011 * (distance ** 0.55) * math.sin(10.0 * math.log(distance))
            )
            closes.append(math.exp(y))
        bars = self.make_equity_bars_from_closes("SPY", closes)

        fit = dashboard_builder.fit_lppl_window(bars)

        self.assertTrue(fit["available"])
        self.assertGreater(fit["lpplImprovementPct"], 5.0)
        self.assertGreaterEqual(fit["oscillationCount"], 2.0)
        self.assertLessEqual(fit["oscillationCount"], 10.0)
        self.assertTrue(fit["passesLpplDiagnostics"])
        self.assertEqual(fit["residualDiagnostics"]["meanReverting"], True)
        self.assertIn("adfProxyPass", fit["residualDiagnostics"])
        self.assertIn("kpssProxyPass", fit["residualDiagnostics"])
        self.assertIn("ljungBoxProxyPass", fit["residualDiagnostics"])
        self.assertIn("power-law", fit["reason"])

    def test_lppl_tc_refinement_recovers_off_grid_critical_day(self):
        n = dashboard_builder.GLOBAL_LPPL_DEFAULT_WINDOW
        true_offset = 46
        tc = n - 1 + true_offset
        closes = []
        for t in range(n):
            distance = tc - t
            y = (
                5.10
                - 0.012 * (distance ** 0.55)
                + 0.0018 * (distance ** 0.55) * math.cos(10.0 * math.log(distance))
                + 0.0011 * (distance ** 0.55) * math.sin(10.0 * math.log(distance))
            )
            closes.append(math.exp(y))
        bars = self.make_equity_bars_from_closes("SPY", closes)

        fit = dashboard_builder.fit_lppl_window(bars)

        self.assertTrue(fit["available"])
        # The coarse grid only contains {15,25,40,60,...}; the local refinement
        # should land within one step of the true off-grid critical day.
        self.assertLessEqual(abs(fit["daysToCritical"] - true_offset), 6)
        self.assertIn("powerExponent", fit)
        self.assertIn("omega", fit)
        self.assertGreaterEqual(fit["fitR2"], 0.95)

    def test_global_lppl_validation_reports_oos_metrics(self):
        closes = []
        level = 100.0
        for index in range(220):
            if 150 <= index <= 156 or 195 <= index <= 200:
                level *= 0.99
            else:
                level *= 1.0015
            closes.append(level)
        bars = self.make_equity_bars_from_closes("SPY", closes)
        history_points = []
        for index, bar in enumerate(bars):
            in_pre_crash = 140 <= index < 150 or 185 <= index < 195
            history_points.append({"date": bar.date.isoformat(), "score": 85.0 if in_pre_crash else 30.0})

        validation = dashboard_builder.build_global_lppl_single_index_validation(
            {"symbol": "SPY", "sourceSymbol": "SPY"},
            bars,
            history_points=history_points,
        )

        self.assertIsNotNone(validation)
        self.assertTrue(validation["oosAvailable"])
        self.assertIn("precision15dOos", validation)
        self.assertIn("recall15dOos", validation)
        self.assertIn("baseRate15dOos", validation)
        self.assertIn("oosThreshold", validation)
        self.assertGreaterEqual(validation["oosSampleSize"], 10)

    def test_global_lppl_risk_exposes_tc_aggregation_and_breadth_confirmation(self):
        def fake_global_lppl_index_row(spec, source_bars, *, as_of=None, fast=False):
            symbol = str(spec.get("symbol") or "").upper()
            score = 72.0 if symbol in {"SPY", "QQQ"} else 52.0
            return {
                "available": True,
                "symbol": symbol,
                "name": symbol,
                "region": "test",
                "score": score,
                "confidence": 0.72,
                "status": "risk" if score >= 65 else "watch",
                "statusCn": "风险" if score >= 65 else "观察",
                "criticalDate": "2026-08-15",
                "asOf": "2026-06-02",
                "daysToCritical": 60,
                "fitR2": 0.91,
                "lpplImprovementPct": 12.0,
                "oscillationCount": 2.6,
                "passesLpplCoreDiagnostics": True,
                "passesLpplDiagnostics": True,
                "residualDiagnostics": {
                    "available": True,
                    "meanReverting": True,
                    "adfProxyPass": True,
                    "kpssProxyPass": True,
                    "ljungBoxProxyPass": True,
                },
                "windowDays": 252,
                "fitEnsemble": {
                    "available": True,
                    "totalFitCount": 6,
                    "validFitCount": 6,
                    "validFitRatioPct": 100.0,
                    "residualPassRatioPct": 100.0,
                    "windowDays": [120, 180, 252, 375, 500, 750],
                    "tcLeadDaysQ20": 40,
                    "tcLeadDaysMedian": 60,
                    "tcLeadDaysQ80": 80,
                    "tcWindowDays": 40,
                    "windowAgreement": "moderate",
                    "optimizerAgreement": "not-modeled",
                    "summary": "test ensemble",
                },
                "observations": len(source_bars),
                "source": "unit-test",
                "sourceSymbol": symbol,
                "sourceQuality": "high",
                "reason": "test fit",
            }

        def fake_history(index_row, bars):
            symbol = str(index_row.get("symbol") or "").upper()
            return {
                "available": True,
                "symbol": symbol,
                "points": [
                    {"date": "2026-06-01", "score": 62, "close": 100, "indexedClose": 100, "criticalDate": "2026-08-10", "daysToCritical": 70, "passesLpplCoreDiagnostics": True},
                    {"date": "2026-06-02", "score": 66, "close": 101, "indexedClose": 101, "criticalDate": "2026-08-15", "daysToCritical": 74, "passesLpplCoreDiagnostics": True},
                ],
                "clipState": {"available": True, "clipLock": True, "status": "locked"},
            }

        def fake_backtest(points, bars, *, symbol, threshold=65):
            return {
                "available": True,
                "sampleSize": 30,
                "threshold": threshold,
                "horizonTests": [{"horizon": h, "alertDays": 3, "truePositives": 2, "falsePositives": 1} for h in (5, 10, 15, 20)],
                "calibrationGrid": [{"threshold": t, "horizon": 15, "alertDays": 3, "truePositives": 2, "falsePositives": 1} for t in (60, 65, 70)],
                "recommendedThreshold": {"threshold": threshold},
                "alertClusterTest": {"clusterCount": 1, "hitClusters": 1, "falseClusters": 0, "maxFalseClusterDays": 0},
            }

        market_bars = {
            symbol: self.make_equity_bars_from_closes(symbol, [100 + index for index in range(140)])
            for symbol in ("SPY", "QQQ", "KOSPI", "HSI", "TWII", "NIKKEI")
        }
        with patch.object(dashboard_builder, "global_lppl_index_row", side_effect=fake_global_lppl_index_row), patch.object(
            dashboard_builder,
            "build_global_lppl_single_index_history",
            side_effect=fake_history,
        ), patch.object(dashboard_builder, "build_global_lppl_backtest", side_effect=fake_backtest):
            risk = dashboard_builder.build_global_lppl_risk_index(market_bars=market_bars)

        self.assertTrue(risk["breadthConfirmation"]["available"])
        self.assertEqual(risk["breadthConfirmation"]["riskCount"], 2)
        self.assertEqual(risk["breadthConfirmation"]["sampleSize"], 6)
        self.assertGreater(risk["breadthConfirmation"]["riskSharePct"], 30)
        self.assertIn("breadth", risk["breadthConfirmation"]["summary"])
        qqq = next(row for row in risk["indices"] if row["symbol"] == "QQQ")
        self.assertEqual(qqq["tcAggregation"]["tcMedian"], "2026-08-01")
        self.assertEqual(qqq["tcAggregation"]["validFitCount"], 6)

    def test_lppl_signal_downgrades_random_walk_without_diagnostics(self):
        close = 100.0
        closes: list[float] = []
        for index in range(380):
            close *= 1 + (0.0012 if index % 9 in {0, 1, 2} else -0.00045)
            close += math.sin(index * 1.7) * 0.015
            closes.append(close)
        bars = self.make_equity_bars_from_closes("SPY", closes)

        fit = dashboard_builder.fit_global_lppl_signal(bars)

        self.assertTrue(fit["available"])
        self.assertFalse(fit["passesLpplDiagnostics"])
        self.assertLessEqual(fit["score"], 40.0)
        self.assertIn("lpplImprovementPct", fit)
        self.assertIn("residualDiagnostics", fit)

    def test_lppl_history_points_replay_each_available_trading_day(self):
        closes = [100 + index * 0.12 for index in range(dashboard_builder.GLOBAL_LPPL_MIN_OBSERVATIONS + 6)]
        bars = self.make_equity_bars_from_closes("SPY", closes)
        calls: list[date] = []

        def fake_global_lppl_index_row(spec, source_bars, *, as_of=None, fast=False):
            calls.append(as_of)
            return {"available": True, "score": 50.0 + len(calls)}

        with patch.object(dashboard_builder, "global_lppl_index_row", side_effect=fake_global_lppl_index_row):
            points = dashboard_builder.build_single_index_lppl_history_points("SPY", bars)

        expected_dates = [bar.date for bar in bars[dashboard_builder.GLOBAL_LPPL_MIN_OBSERVATIONS - 1:]]
        self.assertEqual(calls, expected_dates)
        self.assertEqual([point["date"] for point in points], [day.isoformat() for day in expected_dates])

    def test_lppl_history_points_preserve_critical_date_and_diagnostics(self):
        closes = [100 + index * 0.15 for index in range(dashboard_builder.GLOBAL_LPPL_MIN_OBSERVATIONS + 3)]
        bars = self.make_equity_bars_from_closes("SPY", closes)

        def fake_global_lppl_index_row(spec, source_bars, *, as_of=None, fast=False):
            critical_date = as_of + dashboard_builder.timedelta(days=42)
            return {
                "available": True,
                "score": 67.0,
                "daysToCritical": 42,
                "criticalDate": critical_date.isoformat(),
                "passesLpplCoreDiagnostics": True,
                "passesLpplDiagnostics": False,
                "lpplImprovementPct": 14.2,
                "oscillationCount": 2.7,
            }

        with patch.object(dashboard_builder, "global_lppl_index_row", side_effect=fake_global_lppl_index_row):
            points = dashboard_builder.build_single_index_lppl_history_points("SPY", bars)

        self.assertGreaterEqual(len(points), 3)
        latest = points[-1]
        self.assertEqual(latest["daysToCritical"], 42)
        self.assertRegex(latest["criticalDate"], r"^2025-")
        self.assertTrue(latest["passesLpplCoreDiagnostics"])
        self.assertFalse(latest["passesLpplDiagnostics"])
        self.assertEqual(latest["lpplImprovementPct"], 14.2)
        self.assertEqual(latest["oscillationCount"], 2.7)

    def test_lppl_clip_state_locks_when_critical_dates_converge(self):
        start = date(2026, 5, 1)
        points = []
        for index in range(20):
            observation_date = start + dashboard_builder.timedelta(days=index)
            critical_date = date(2026, 7, 15) + dashboard_builder.timedelta(days=(index % 5) - 2)
            points.append(
                {
                    "date": observation_date.isoformat(),
                    "score": 62.0 + index * 0.4,
                    "criticalDate": critical_date.isoformat(),
                    "daysToCritical": (critical_date - observation_date).days,
                    "passesLpplCoreDiagnostics": True,
                }
            )

        clip_state = dashboard_builder.build_lppl_clip_state(points)

        self.assertTrue(clip_state["available"])
        self.assertTrue(clip_state["clipLock"])
        self.assertEqual(clip_state["status"], "locked")
        self.assertLessEqual(clip_state["tcWindowDays"], 10)
        self.assertEqual(clip_state["tcMedian"], "2026-07-15")

        row = {
            "symbol": "SPY",
            "available": True,
            "score": 62.0,
            "confidence": 0.72,
            "daysToCritical": 58,
            "effectiveWeightMultiplier": 1.0,
            "validation": {"effectiveWeightMultiplier": 1.0},
            "history": {"available": True, "points": points, "clipState": clip_state},
            "backtest": {"threshold": 65},
            "clipState": clip_state,
        }
        signal = dashboard_builder.build_global_lppl_forward_signal(row)

        self.assertTrue(signal["clipLock"])
        self.assertIn("clip_lock", signal["drivers"])
        self.assertGreaterEqual(signal["score"], 60)

    def test_global_lppl_risk_reuses_daily_history_for_validation(self):
        closes = [100 + index * 0.1 for index in range(dashboard_builder.GLOBAL_LPPL_MIN_OBSERVATIONS + 35)]
        market_bars = {
            "SPY": self.make_equity_bars_from_closes("SPY", closes),
            "QQQ": self.make_equity_bars_from_closes("QQQ", [value * 1.01 for value in closes]),
        }
        history_calls: list[str] = []

        def fake_global_lppl_index_row(spec, source_bars, *, as_of=None, fast=False):
            symbol = str(spec.get("symbol") or "").upper()
            if not source_bars:
                return {"available": False, "symbol": symbol, "score": None, "reason": "missing test bars"}
            return {
                "available": True,
                "symbol": symbol,
                "name": symbol,
                "sourceSymbol": symbol,
                "score": 70.0,
                "confidence": 0.8,
                "status": "risk",
                "statusCn": "风险",
                "date": source_bars[-1].date.isoformat(),
            }

        def fake_history_points(symbol, bars):
            history_calls.append(symbol)
            return [
                {"date": bar.date.isoformat(), "score": 70.0}
                for bar in bars[dashboard_builder.GLOBAL_LPPL_MIN_OBSERVATIONS - 1:]
            ]

        with patch.object(dashboard_builder, "global_lppl_index_row", side_effect=fake_global_lppl_index_row), patch.object(
            dashboard_builder,
            "build_single_index_lppl_history_points",
            side_effect=fake_history_points,
        ):
            risk = dashboard_builder.build_global_lppl_risk_index(market_bars=market_bars)

        self.assertEqual(history_calls.count("SPY"), 1)
        self.assertEqual(history_calls.count("QQQ"), 1)
        self.assertTrue(risk["indexValidation"]["available"])
        self.assertTrue(risk["perIndexHistory"]["SPY"]["available"])
        self.assertTrue(risk["perIndexHistory"]["QQQ"]["available"])

    def test_fast_lppl_signal_uses_single_replay_window(self):
        bars = self.make_equity_bars_from_closes(
            "SPY",
            [100 + index * 0.08 for index in range(dashboard_builder.GLOBAL_LPPL_MIN_OBSERVATIONS + 20)],
        )
        windows: list[int] = []

        def fake_fit_lppl_window(sample, *, fast=False):
            windows.append(len(sample))
            return {"available": True, "score": 42.0, "confidence": 0.5, "fitR2": 0.9, "fitSse": 1.0, "daysToCritical": 60, "windowDays": len(sample)}

        with patch.object(dashboard_builder, "fit_lppl_window", side_effect=fake_fit_lppl_window):
            fit = dashboard_builder.fit_global_lppl_signal(bars, fast=True)

        self.assertTrue(fit["available"])
        self.assertEqual(windows, [len(bars)])

    def test_global_lppl_forward_signal_flags_rising_pre_threshold_pressure(self):
        history = {
            "available": True,
            "points": [
                {"date": f"2026-05-{day:02d}", "score": 42.0 + day * 0.7}
                for day in range(1, 22)
            ],
        }
        row = {
            "symbol": "SPY",
            "available": True,
            "score": 58.0,
            "confidence": 0.72,
            "daysToCritical": 60,
            "effectiveWeightMultiplier": 1.0,
            "validation": {"effectiveWeightMultiplier": 1.0},
            "history": history,
            "backtest": {"threshold": 65},
        }

        signal = dashboard_builder.build_global_lppl_forward_signal(row)

        self.assertTrue(signal["available"])
        self.assertGreaterEqual(signal["score"], 55)
        self.assertEqual(signal["regime"], "Rising Watch")
        self.assertGreater(signal["scoreMomentum20d"], 10)
        self.assertEqual(signal["thresholdDistance"], -7.0)
        self.assertIn("rising", signal["drivers"])

    def test_global_lppl_forward_signal_penalizes_weak_validation_and_falling_score(self):
        history = {
            "available": True,
            "points": [
                {"date": f"2026-05-{day:02d}", "score": 86.0 - day * 0.8}
                for day in range(1, 22)
            ],
        }
        row = {
            "symbol": "SPY",
            "available": True,
            "score": 70.0,
            "confidence": 0.50,
            "daysToCritical": 170,
            "effectiveWeightMultiplier": 0.60,
            "validation": {"effectiveWeightMultiplier": 0.60, "validationRole": "weak"},
            "history": history,
            "backtest": {"threshold": 65},
        }

        signal = dashboard_builder.build_global_lppl_forward_signal(row)

        self.assertTrue(signal["available"])
        self.assertLess(signal["score"], 55)
        self.assertEqual(signal["regime"], "Fading")
        self.assertLess(signal["scoreMomentum20d"], -10)
        self.assertIn("weak_validation", signal["drivers"])

    def test_global_lppl_forward_signal_penalizes_scattered_ensemble(self):
        history = {
            "available": True,
            "points": [
                {"date": f"2026-05-{day:02d}", "score": 58.0 + day * 0.6}
                for day in range(1, 22)
            ],
        }
        row = {
            "symbol": "SPY",
            "available": True,
            "score": 82.0,
            "confidence": 0.80,
            "daysToCritical": 45,
            "effectiveWeightMultiplier": 1.0,
            "validation": {"effectiveWeightMultiplier": 1.0},
            "history": history,
            "backtest": {"threshold": 65},
            "fitEnsemble": {
                "available": True,
                "validFitRatioPct": 100.0,
                "residualPassRatioPct": 33.3,
                "windowAgreement": "scattered",
                "tcWindowDays": 145,
            },
        }

        signal = dashboard_builder.build_global_lppl_forward_signal(row)

        self.assertTrue(signal["available"])
        self.assertLess(signal["score"], 70)
        self.assertLess(signal["ensembleMultiplier"], 0.80)
        self.assertIn("weak_ensemble", signal["drivers"])

    def test_equity_backtest_reports_walk_forward_and_lift_against_base_rate(self):
        bars: list[MarketDailyBar] = []
        trend_points: list[dict[str, object]] = []
        close = 100.0
        cursor = date(2026, 1, 2)
        while len(bars) < 70:
            if cursor.weekday() < 5:
                index = len(bars)
                close = 100.0 + index * 0.05
                low = close * (0.965 if index % 9 == 4 else 0.995)
                bars.append(MarketDailyBar("SPY", cursor, close, close * 1.006, low, close, 1_000_000 + index, "unit-test"))
                if index < 60:
                    trend_points.append({"date": cursor.isoformat(), "score": 82.0 if index % 9 in {0, 1} else 35.0, "regime": "test", "regimeCn": "测试"})
            cursor += dashboard_builder.timedelta(days=1)

        backtest = build_equity_short_term_risk_backtest(trend_points, bars, horizon=10)

        self.assertTrue(backtest["available"])
        self.assertIn("walkForward", backtest)
        self.assertIn("outOfSampleThresholdTests", backtest)
        self.assertGreater(backtest["walkForward"]["outOfSample"]["sampleSize"], 0)
        preferred = backtest["preferredThresholdTest"]
        self.assertIn("baseRate", preferred)
        self.assertIn("liftVsBaseRate", preferred)

    def test_turnover_score_transitions_smoothly_around_thin_breakout_volume_boundary(self):
        target = date(2026, 6, 5)
        bar = MarketDailyBar("SPY", target, 100.0, 102.0, 99.8, 101.8, 1_000_000, "unit-test")
        bars = {"SPY": [bar]}

        with ExitStack() as stack:
            stack.enter_context(patch.object(dashboard_builder, "volume_percentile_at", return_value=45.0))
            stack.enter_context(patch.object(dashboard_builder, "trailing_return", return_value=0.12))
            score_45 = dashboard_builder.equity_turnover_component(bars, target, weight=0.14)["score"]
        with ExitStack() as stack:
            stack.enter_context(patch.object(dashboard_builder, "volume_percentile_at", return_value=46.0))
            stack.enter_context(patch.object(dashboard_builder, "trailing_return", return_value=0.12))
            score_46 = dashboard_builder.equity_turnover_component(bars, target, weight=0.14)["score"]

        self.assertLess(abs(score_45 - score_46), 12.0)

    def test_turnover_distribution_score_ramps_instead_of_stepping_at_volume_boundary(self):
        target = date(2026, 6, 5)
        bar = MarketDailyBar("SPY", target, 101.0, 102.0, 99.8, 100.5, 1_000_000, "unit-test")
        bars = {"SPY": [bar]}

        scores = {}
        for volume_pct in (69.0, 71.0, 75.0, 80.0):
            with ExitStack() as stack:
                stack.enter_context(patch.object(dashboard_builder, "volume_percentile_at", return_value=volume_pct))
                stack.enter_context(patch.object(dashboard_builder, "trailing_return", return_value=0.02))
                scores[volume_pct] = dashboard_builder.equity_turnover_component(bars, target, weight=0.14)["score"]

        self.assertLess(abs(scores[69.0] - scores[71.0]), 8.0)
        self.assertLess(scores[71.0], scores[75.0])
        self.assertLess(scores[75.0], scores[80.0])
        self.assertGreaterEqual(scores[80.0], 80.0)

    def test_hot_stock_reversal_shrinks_extreme_score_when_hot_sample_is_tiny(self):
        target = date(2026, 6, 5)
        closes = [100.0 * (1.003 ** index) for index in range(70)]
        closes[-1] = closes[-2] * 0.985
        bars = self.make_equity_bars_from_closes("NVDA", closes, start=date(2026, 3, 2))

        component = dashboard_builder.equity_hot_stock_reversal_component({"NVDA": bars}, target, weight=0.18)

        self.assertEqual(component["metrics"]["hotCount"], 1)
        self.assertEqual(component["metrics"]["reversalCount"], 1)
        self.assertLess(component["score"], 75.0)
        self.assertTrue(component["metrics"]["smallSampleAdjusted"])

    def test_parse_bhadial_public_score_prefers_visible_hero_gauge(self):
        html = '<script>window.__DIAL_BOOTSTRAP__ = {"marketingTeaser":{"score":50.8}}</script><text class="hero-gauge-score" text-anchor="middle">43.4</text>'

        self.assertEqual(parse_bhadial_public_score(html), 43.4)

    def test_compute_tenor_realized_volatility_uses_public_curve_history(self):
        records = []
        for index in range(21):
            value = 4.00 if index % 2 == 0 else 4.01
            records.append(YieldCurveRecord(date=date(2026, 4, index + 1), values={"10Y": value}))

        vol = compute_tenor_realized_volatility(records, "10Y", window=20)

        self.assertAlmostEqual(vol, 16.29, places=2)

    def test_build_dashboard_outputs_frontend_contract(self):
        curve_records = [
            YieldCurveRecord(
                date=date(2026, 4, 18),
                values={"1M": 3.69, "3M": 3.70, "6M": 3.69, "1Y": 3.64, "2Y": 3.71, "3Y": 3.72, "5Y": 3.84, "7Y": 4.04, "10Y": 4.26, "20Y": 4.85, "30Y": 4.88},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 11),
                values={"1M": 3.71, "3M": 3.70, "6M": 3.77, "1Y": 3.79, "2Y": 3.95, "3Y": 3.96, "5Y": 4.07, "7Y": 4.24, "10Y": 4.42, "20Y": 4.97, "30Y": 4.98},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 18),
                values={"1M": 3.69, "3M": 3.68, "6M": 3.77, "1Y": 3.81, "2Y": 4.07, "3Y": 4.14, "5Y": 4.27, "7Y": 4.43, "10Y": 4.61, "20Y": 5.14, "30Y": 5.14},
            ),
        ]
        fred = {
            "DFII10": TimeSeries("DFII10", [SeriesPoint(date(2026, 5, 18), 2.13)]),
            "T10YIE": TimeSeries("T10YIE", [SeriesPoint(date(2026, 5, 18), 2.48)]),
            "SOFR": TimeSeries("SOFR", [SeriesPoint(date(2026, 5, 18), 3.53)]),
            "WTREGEN": TimeSeries("WTREGEN", [SeriesPoint(date(2026, 5, 13), 838_584.0)]),
            "WALCL": TimeSeries("WALCL", [SeriesPoint(date(2026, 5, 13), 6_731_000.0)]),
            "TREAST": TimeSeries("TREAST", [SeriesPoint(date(2026, 5, 13), 4_210_000.0)]),
            "RRPONTSYD": TimeSeries("RRPONTSYD", [SeriesPoint(date(2026, 5, 18), 4_000.0)]),
            "CPIAUCSL": TimeSeries("CPIAUCSL", [SeriesPoint(date(2025, 4, 1), 313.0), SeriesPoint(date(2026, 4, 1), 324.9)]),
            "PPIACO": TimeSeries("PPIACO", [SeriesPoint(date(2025, 4, 1), 255.0), SeriesPoint(date(2026, 4, 1), 270.3)]),
            "UNRATE": TimeSeries("UNRATE", [SeriesPoint(date(2026, 4, 1), 4.1)]),
            "PAYEMS": TimeSeries("PAYEMS", [SeriesPoint(date(2026, 3, 1), 159_500.0), SeriesPoint(date(2026, 4, 1), 159_650.0)]),
        }

        dashboard = build_dashboard_from_inputs(
            curve_records=curve_records,
            fred=fred,
            auctions=[],
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            fed_funds_futures=MarketQuote(symbol="ZQ.F", date=date(2026, 5, 19), close=96.37, source="Stooq"),
            official_news=[
                NewsItem(
                    date=date(2026, 5, 18),
                    source="U.S. Treasury",
                    title="Treasury International Capital Data for March",
                    url="https://home.treasury.gov/news/press-releases/sb0499",
                )
            ],
        )

        self.assertEqual(dashboard["asOf"], "2026-05-18")
        self.assertEqual(dashboard["curve"]["today"][8], 4.61)
        self.assertEqual(dashboard["curve"]["w1"][8], 4.42)
        self.assertIn("sourceStatus", dashboard)
        self.assertEqual(dashboard["generatedAt"], "2026-05-20T00:00:00+00:00")
        self.assertEqual(len(dashboard["groups"]), 6)
        self.assertEqual(dashboard["meta"]["dataMode"], "real-public-sources")
        self.assertIn("30-Day Fed Funds futures", dashboard["decomposition"]["sources"][1]["name"])
        self.assertIn("3.63%", dashboard["decomposition"]["sources"][1]["value"])
        self.assertEqual(dashboard["news"][0], ["05/18", "U.S. Treasury", "Treasury International Capital Data for March"])
        self.assertTrue(any("official public news headlines" in note for note in dashboard["meta"]["notes"]))

    def test_build_dashboard_adds_updated_remote_analysis_logic(self):
        curve_records = [
            YieldCurveRecord(
                date=date(2026, 4, 18),
                values={"1M": 3.69, "3M": 3.70, "6M": 3.69, "1Y": 3.64, "2Y": 3.71, "3Y": 3.72, "5Y": 3.84, "7Y": 4.04, "10Y": 4.26, "20Y": 4.85, "30Y": 4.88},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 11),
                values={"1M": 3.71, "3M": 3.70, "6M": 3.77, "1Y": 3.79, "2Y": 3.95, "3Y": 3.96, "5Y": 4.07, "7Y": 4.24, "10Y": 4.42, "20Y": 4.97, "30Y": 4.98},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 18),
                values={"1M": 3.69, "3M": 3.68, "6M": 3.77, "1Y": 3.81, "2Y": 4.07, "3Y": 4.14, "5Y": 4.27, "7Y": 4.43, "10Y": 4.61, "20Y": 5.14, "30Y": 5.14},
            ),
        ]
        fred = {
            "DFII10": TimeSeries("DFII10", [SeriesPoint(date(2026, 5, 18), 2.13)]),
            "T10YIE": TimeSeries("T10YIE", [SeriesPoint(date(2026, 5, 18), 2.48)]),
            "DFF": TimeSeries("DFF", [SeriesPoint(date(2026, 5, 18), 3.63)]),
            "SOFR": TimeSeries("SOFR", [SeriesPoint(date(2026, 5, 18), 3.53)]),
            "WTREGEN": TimeSeries("WTREGEN", [SeriesPoint(date(2026, 5, 13), 838_584.0)]),
            "WALCL": TimeSeries("WALCL", [SeriesPoint(date(2026, 5, 13), 6_731_000.0)]),
            "TREAST": TimeSeries("TREAST", [SeriesPoint(date(2026, 5, 13), 4_210_000.0)]),
            "RRPONTSYD": TimeSeries("RRPONTSYD", [SeriesPoint(date(2026, 5, 18), 4_000.0)]),
            "WRESBAL": TimeSeries("WRESBAL", [SeriesPoint(date(2026, 5, 14), 3_130_000.0)]),
            "CPIAUCSL": TimeSeries("CPIAUCSL", [SeriesPoint(date(2025, 4, 1), 313.0), SeriesPoint(date(2026, 4, 1), 324.9)]),
            "PPIACO": TimeSeries("PPIACO", [SeriesPoint(date(2025, 4, 1), 255.0), SeriesPoint(date(2026, 4, 1), 270.3)]),
            "UNRATE": TimeSeries("UNRATE", [SeriesPoint(date(2026, 4, 1), 4.1)]),
            "PAYEMS": TimeSeries("PAYEMS", [SeriesPoint(date(2026, 3, 1), 159_500.0), SeriesPoint(date(2026, 4, 1), 159_650.0)]),
            "DCOILWTICO": TimeSeries("DCOILWTICO", [SeriesPoint(date(2026, 5, 18), 72.5)]),
        }

        dashboard = build_dashboard_from_inputs(
            curve_records=curve_records,
            fred=fred,
            auctions=[],
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            fed_funds_futures=MarketQuote(symbol="ZQ.F", date=date(2026, 5, 19), close=96.37, source="Stooq"),
            fomc_projection=FomcProjection(
                release_date=date(2026, 3, 18),
                median_fed_funds={"2026": 3.4, "2027": 3.1, "Longer run": 3.1},
            ),
            quarterly_refunding=QuarterlyRefunding(
                release_date=date(2026, 5, 6),
                quarter="2026 - 2nd Quarter",
                policy_statement_url="https://home.treasury.gov/news/press-releases/sb0489",
                financing_estimates_url="https://home.treasury.gov/news/press-releases/sb0485",
                next_policy_statement_date=date(2026, 8, 5),
                next_financing_estimates_date=date(2026, 8, 3),
                current_quarter_borrowing_billions=189.0,
                next_quarter_borrowing_billions=671.0,
            ),
        )

        decomposition = dashboard["decomposition"]
        self.assertIn("Clarida", decomposition["frameworkNote"])
        self.assertIn("叙事变化", decomposition["frameworkNote"])
        self.assertIn("真实利率", decomposition["regimeRead"])
        self.assertIn("通胀补偿", decomposition["regimeRead"])
        self.assertIn("市场先跑", decomposition["policyRead"])
        self.assertIn("官方后确认", decomposition["policyRead"])

        idea_titles = [idea["title"] for idea in dashboard["ideas"]]
        self.assertEqual(
            idea_titles[:4],
            ["战术减久期", "做陡 5s30s 曲线", "前端持有 · 吃 carry", "战术做多盈亏平衡通胀"],
        )
        self.assertIn("宏观环境评分", dashboard["ideas"][0]["text"])
        self.assertIn("QRA", dashboard["ideas"][1]["text"])
        self.assertIn("SOFR", dashboard["ideas"][2]["text"])
        self.assertIn("WTI", dashboard["ideas"][3]["text"])

    def test_build_dashboard_adds_remote_narrative_compatibility_factors_with_source_modes(self):
        curve_records = [
            YieldCurveRecord(
                date=date(2026, 4, 18),
                values={"1M": 3.69, "3M": 3.70, "6M": 3.69, "1Y": 3.64, "2Y": 3.71, "3Y": 3.72, "5Y": 3.84, "7Y": 4.04, "10Y": 4.26, "20Y": 4.85, "30Y": 4.88},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 18),
                values={"1M": 3.69, "3M": 3.68, "6M": 3.77, "1Y": 3.81, "2Y": 4.07, "3Y": 4.14, "5Y": 4.27, "7Y": 4.43, "10Y": 4.61, "20Y": 5.14, "30Y": 5.14},
            ),
        ]
        fred = {
            "DFII10": TimeSeries("DFII10", [SeriesPoint(date(2026, 5, 18), 2.13)]),
            "T10YIE": TimeSeries("T10YIE", [SeriesPoint(date(2026, 5, 18), 2.48)]),
            "DFF": TimeSeries("DFF", [SeriesPoint(date(2026, 5, 18), 3.63)]),
            "SOFR": TimeSeries("SOFR", [SeriesPoint(date(2026, 5, 18), 3.53)]),
            "WTREGEN": TimeSeries("WTREGEN", [SeriesPoint(date(2026, 5, 13), 838_584.0)]),
            "WALCL": TimeSeries("WALCL", [SeriesPoint(date(2026, 5, 13), 6_731_000.0)]),
            "TREAST": TimeSeries("TREAST", [SeriesPoint(date(2026, 5, 13), 4_210_000.0)]),
            "RRPONTSYD": TimeSeries("RRPONTSYD", [SeriesPoint(date(2026, 5, 18), 4_000.0)]),
            "WRESBAL": TimeSeries("WRESBAL", [SeriesPoint(date(2026, 5, 14), 3_130_000.0)]),
            "CPIAUCSL": TimeSeries("CPIAUCSL", [SeriesPoint(date(2025, 4, 1), 313.0), SeriesPoint(date(2026, 4, 1), 324.9)]),
            "PPIACO": TimeSeries("PPIACO", [SeriesPoint(date(2025, 4, 1), 255.0), SeriesPoint(date(2026, 4, 1), 270.3)]),
            "UNRATE": TimeSeries("UNRATE", [SeriesPoint(date(2026, 4, 1), 4.1)]),
            "PAYEMS": TimeSeries("PAYEMS", [SeriesPoint(date(2026, 3, 1), 159_500.0), SeriesPoint(date(2026, 4, 1), 159_650.0)]),
            "VIXCLS": TimeSeries("VIXCLS", [SeriesPoint(date(2026, 5, 18), 17.82)]),
            "BAMLH0A0HYM2": TimeSeries("BAMLH0A0HYM2", [SeriesPoint(date(2026, 5, 18), 2.83)]),
        }

        dashboard = build_dashboard_from_inputs(
            curve_records=curve_records,
            fred=fred,
            auctions=[],
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            fed_funds_futures=MarketQuote(symbol="ZQ.F", date=date(2026, 5, 19), close=96.37, source="Stooq"),
            primary_dealer_stats=PrimaryDealerStats(
                as_of=date(2026, 5, 6),
                seriesbreak="SBN2024",
                metrics_millions={"PDPOSGST-TOT": 500420.0},
            ),
            official_news=[
                NewsItem(
                    date=date(2026, 5, 22),
                    source="Federal Reserve",
                    title="Kevin Warsh takes oath of office as chairman and a member of the Board of Governors",
                    url="https://www.federalreserve.gov/newsevents/pressreleases/other20260522a.htm",
                )
            ],
        )

        factors = {factor["n"]: factor for group in dashboard["groups"] for factor in group["factors"]}
        expected_names = {
            "隐含政策路径",
            "新任主席倾向",
            "增长动能",
            "30年期拍卖",
            "一级交易商持仓",
            "互换利差",
            "市场流动性",
            "新老券利差",
        }
        self.assertTrue(expected_names.issubset(factors))
        self.assertEqual(factors["隐含政策路径"]["sourceMode"], "modeled")
        self.assertIn("加息", factors["隐含政策路径"]["tag"])
        self.assertIn("+150k", factors["非农就业"]["tag"])
        self.assertIn("+150k", factors["增长动能"]["tag"])
        self.assertEqual(factors["新任主席倾向"]["sourceMode"], "official-news")
        self.assertEqual(factors["新任主席倾向"]["score"], 0)
        self.assertIn("手动", factors["新任主席倾向"]["note"])
        self.assertEqual(factors["一级交易商持仓"]["sourceMode"], "real-public")
        self.assertIn("$500.4B", factors["一级交易商持仓"]["tag"])
        self.assertEqual(factors["互换利差"]["sourceMode"], "manual-placeholder")
        self.assertEqual(factors["新老券利差"]["sourceMode"], "manual-placeholder")
        self.assertEqual(factors["市场流动性"]["sourceMode"], "proxy-public")
        self.assertTrue(all(factors[name]["compatibilityWith"] == "us-treasury-bonds-monitor-luffa" for name in expected_names))
        self.assertEqual(set(dashboard["meta"]["remoteCompatibility"]["factorNames"]), expected_names)

    def test_build_dashboard_uses_low_frequency_public_sources_when_available(self):
        curve_records = [
            YieldCurveRecord(
                date=date(2026, 4, 18),
                values={"1M": 3.69, "3M": 3.70, "6M": 3.69, "1Y": 3.64, "2Y": 3.71, "3Y": 3.72, "5Y": 3.84, "7Y": 4.04, "10Y": 4.26, "20Y": 4.85, "30Y": 4.88},
            ),
            YieldCurveRecord(
                date=date(2026, 5, 18),
                values={"1M": 3.69, "3M": 3.68, "6M": 3.77, "1Y": 3.81, "2Y": 4.07, "3Y": 4.14, "5Y": 4.27, "7Y": 4.43, "10Y": 4.61, "20Y": 5.14, "30Y": 5.14},
            ),
        ]
        fred = {
            "DFII10": TimeSeries("DFII10", [SeriesPoint(date(2026, 5, 18), 2.13)]),
            "T10YIE": TimeSeries("T10YIE", [SeriesPoint(date(2026, 5, 18), 2.48)]),
            "DFF": TimeSeries("DFF", [SeriesPoint(date(2026, 5, 18), 3.63)]),
            "SOFR": TimeSeries("SOFR", [SeriesPoint(date(2026, 5, 18), 3.53)]),
            "WTREGEN": TimeSeries("WTREGEN", [SeriesPoint(date(2026, 5, 13), 838_584.0)]),
            "WALCL": TimeSeries("WALCL", [SeriesPoint(date(2026, 5, 13), 6_731_000.0)]),
            "TREAST": TimeSeries("TREAST", [SeriesPoint(date(2026, 5, 13), 4_210_000.0)]),
            "RRPONTSYD": TimeSeries("RRPONTSYD", [SeriesPoint(date(2026, 5, 18), 4_000.0)]),
            "CPIAUCSL": TimeSeries("CPIAUCSL", [SeriesPoint(date(2025, 4, 1), 313.0), SeriesPoint(date(2026, 4, 1), 324.9)]),
            "PPIACO": TimeSeries("PPIACO", [SeriesPoint(date(2025, 4, 1), 255.0), SeriesPoint(date(2026, 4, 1), 270.3)]),
            "UNRATE": TimeSeries("UNRATE", [SeriesPoint(date(2026, 4, 1), 4.1)]),
            "PAYEMS": TimeSeries("PAYEMS", [SeriesPoint(date(2026, 3, 1), 159_500.0), SeriesPoint(date(2026, 4, 1), 159_650.0)]),
            "SP500": TimeSeries("SP500", [SeriesPoint(date(2026, 5, 18), 7403.05), SeriesPoint(date(2026, 5, 19), 7353.61)]),
            "VIXCLS": TimeSeries("VIXCLS", [SeriesPoint(date(2026, 5, 18), 17.82)]),
            "DTWEXBGS": TimeSeries("DTWEXBGS", [SeriesPoint(date(2026, 5, 15), 119.28)]),
            "BAMLH0A0HYM2": TimeSeries("BAMLH0A0HYM2", [SeriesPoint(date(2026, 5, 18), 2.83)]),
            "BAMLC0A0CM": TimeSeries("BAMLC0A0CM", [SeriesPoint(date(2026, 5, 18), 0.75)]),
            "IRLTLT01DEM156N": TimeSeries("IRLTLT01DEM156N", [SeriesPoint(date(2026, 4, 1), 3.0)]),
            "IRLTLT01GBM156N": TimeSeries("IRLTLT01GBM156N", [SeriesPoint(date(2026, 4, 1), 4.82)]),
            "IRLTLT01JPM156N": TimeSeries("IRLTLT01JPM156N", [SeriesPoint(date(2026, 4, 1), 2.52)]),
            "DCOILWTICO": TimeSeries("DCOILWTICO", [SeriesPoint(date(2026, 5, 18), 72.5)]),
            "OVXCLS": TimeSeries("OVXCLS", [SeriesPoint(date(2026, 5, 18), 72.07)]),
            "GVZCLS": TimeSeries("GVZCLS", [SeriesPoint(date(2026, 5, 18), 26.2)]),
        }
        acm = AcmRecord(date=date(2026, 5, 18), term_premium_10y=0.37, expected_rate_10y=4.24)
        cftc = [
            CftcTreasuryPosition(
                report_date=date(2026, 5, 12),
                market="ULTRA UST 10Y",
                open_interest=2_500,
                dealer_net=-200,
                asset_manager_net=300,
                leveraged_net=-250,
                leveraged_net_pct_oi=-10.0,
            )
        ]
        tic = TicHoldings(
            period="2026-03",
            holdings=[
                TicHolding("Japan", 1191.6, -47.7),
                TicHolding("China, Mainland", 652.3, -13.3),
            ],
            total=TicHolding("Grand Total", 9348.7, -138.4),
            official=TicHolding("Of Which: Foreign Official", 3902.2, -47.8),
        )

        dashboard = build_dashboard_from_inputs(
            curve_records=curve_records,
            fred=fred,
            auctions=[],
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            acm=acm,
            cftc_positions=cftc,
            tic_holdings=tic,
            fomc_projection=FomcProjection(
                release_date=date(2026, 3, 18),
                median_fed_funds={"2026": 3.4, "2027": 3.1, "2028": 3.1, "Longer run": 3.1},
            ),
            primary_dealer_stats=PrimaryDealerStats(
                as_of=date(2026, 5, 6),
                seriesbreak="SBN2024",
                metrics_millions={
                    "PDPOSGST-TOT": 500420.0,
                    "PDGSWOEXTTOT": 872623.0,
                    "PDSORA-UTSETTOT": 3190705.0,
                    "PDSIOSB-UTSETTOT": 431867.0,
                },
            ),
            quarterly_refunding=QuarterlyRefunding(
                release_date=date(2026, 5, 6),
                quarter="2026 - 2nd Quarter",
                policy_statement_url="https://home.treasury.gov/news/press-releases/sb0489",
                financing_estimates_url="https://home.treasury.gov/news/press-releases/sb0485",
                next_policy_statement_date=date(2026, 8, 5),
                next_financing_estimates_date=date(2026, 8, 3),
                current_quarter_borrowing_billions=189.0,
                next_quarter_borrowing_billions=671.0,
                current_quarter_cash_balance_billions=900.0,
                next_quarter_cash_balance_billions=950.0,
                refunding_amount_billions=125.0,
                refunding_new_cash_billions=41.7,
                coupon_stance="Treasury anticipates maintaining nominal coupon and FRN auction sizes for at least the next several quarters.",
                bill_issuance="Treasury expects to further increase offering sizes of shorter-dated benchmark bills over the coming weeks.",
                buyback_total_billions=63.0,
                tga_peak="TGA could peak at $1 trillion (plus or minus $50 billion) in late July.",
            ),
            debt_limit_status=DebtLimitStatus(
                record_date=date(2026, 5, 18),
                statutory_limit_millions=41_103_996.0,
                debt_subject_to_limit_millions=38_831_998.0,
                headroom_millions=2_271_998.0,
                public_debt_millions=31_317_917.0,
                intragov_holdings_millions=7_691_083.0,
                debt_not_subject_millions=177_002.0,
            ),
            gold_quote=MarketQuote(symbol="XAUUSD", date=date(2026, 5, 20), close=4536.7, source="Stooq"),
            calendar_events=[
                CalendarEvent(
                    date=date(2026, 6, 17),
                    title="FOMC decision + SEP",
                    source="Federal Reserve FOMC calendar",
                    importance="高",
                )
            ],
            announced_auctions=[
                {
                    "auctionDate": "2026-05-21T00:00:00",
                    "securityTerm": "4-Week",
                    "securityType": "Bill",
                    "offeringAmount": "100000000000",
                }
            ],
        )

        self.assertEqual(dashboard["decomposition"]["components"][2]["driver"], "NY Fed ACM")
        self.assertEqual(dashboard["decomposition"]["marketMeasures"]["real10y"], "2.13%")
        self.assertEqual(dashboard["decomposition"]["sources"][0]["name"], "美联储 SEP · 点阵图")
        self.assertIn("2026 median 3.40%", dashboard["decomposition"]["sources"][0]["value"])
        self.assertIn("ULTRA UST 10Y", dashboard["positioning"]["cftc"][0][0])
        self.assertIn("净空", dashboard["positioning"]["cftc"][0][1])
        self.assertEqual(dashboard["positioning"]["tic"][0][0], "Japan")
        self.assertEqual(dashboard["positioning"]["dealers"][0][0], "Primary dealers · UST ex-TIPS")
        self.assertEqual(dashboard["positioning"]["dealers"][0][1], "$500.4B")
        self.assertIn("2026-05-06", dashboard["positioning"]["dealers"][0][2])
        self.assertIn(["SOMA Treasury持仓", "$4.21T", "FRED TREAST"], dashboard["policy"]["plumbing"])
        self.assertTrue(any(factor["n"] == "SOMA Treasury持仓" for factor in dashboard["groups"][0]["factors"]))
        vol_factor = next(factor for factor in dashboard["groups"][5]["factors"] if factor["n"] == "10Y实现波动率")
        self.assertIn("Treasury curve", vol_factor["note"])
        self.assertIn("20D", vol_factor["tag"])
        self.assertEqual(dashboard["cross"]["yields"][1], ["德国 Bund", 3.0])
        cross_history_groups = {group["id"]: group for group in dashboard["cross"]["historySeries"]}
        self.assertEqual(set(cross_history_groups), {"global", "risk", "inflation"})
        global_targets = {(item["category"], item["name"], item.get("label", "")) for item in cross_history_groups["global"]["series"]}
        risk_targets = {(item["category"], item["name"], item.get("label", "")) for item in cross_history_groups["risk"]["series"]}
        inflation_targets = {(item["category"], item["name"], item.get("label", "")) for item in cross_history_groups["inflation"]["series"]}
        self.assertIn(("curve_yield", "10Y收益率", "10Y"), global_targets)
        self.assertIn(("global_yield", "德国10Y", "IRLTLT01DEM156N"), global_targets)
        self.assertIn(("risk", "S&P 500", "SP500"), risk_targets)
        self.assertIn(("risk", "VIX", "VIXCLS"), risk_targets)
        self.assertIn(("fx", "美元广义指数", "DTWEXBGS"), risk_targets)
        self.assertIn(("inflation", "达拉斯联储Trimmed Mean PCE", "PCETRIM12M159SFRBDAL"), inflation_targets)
        self.assertIn(("commodity", "WTI原油", "DCOILWTICO"), inflation_targets)
        self.assertEqual(dashboard["fiscal"][0][0], "季度再融资 (QRA)")
        self.assertIn("$671B", dashboard["fiscal"][0][1])
        self.assertIn(["债务上限空间", "$2.27T", "Fiscal Data 2026-05-18"], dashboard["fiscal"])
        self.assertTrue(any(factor["n"] == "债务上限空间" for factor in dashboard["groups"][2]["factors"]))
        self.assertTrue(any(factor["n"] == "发行节奏 / QRA" for factor in dashboard["groups"][2]["factors"]))
        self.assertIn(["黄金现货", "$4536.70", "Stooq XAUUSD"], dashboard["cross"]["inflation"])
        self.assertIn(["2026-06-17", "FOMC decision + SEP", "高"], dashboard["events"])
        self.assertIn(["2026-08-05", "Treasury quarterly refunding statement", "高"], dashboard["events"])
        self.assertIn(["2026-08-03", "Treasury borrowing estimates / QRA pre-release", "中"], dashboard["events"])
        self.assertTrue(any(row[0] == "2026-05-21" and row[1].startswith("Treasury auction") for row in dashboard["events"]))
        self.assertNotIn("CFTC/TIC/news", {item["name"] for item in dashboard["sourceStatus"]})
        self.assertNotIn("U.S. Treasury quarterly refunding documents", {item["name"] for item in dashboard["sourceStatus"]})

    def test_apply_content_overrides_replaces_narrative_and_factor_scores(self):
        dashboard = {
            "ideas": [{"title": "旧观点", "tag": "OLD", "text": "旧文本", "source": "old"}],
            "groups": [{"id": "g1", "factors": [{"n": "因子", "score": 0, "note": "旧说明"}]}],
        }
        overrides = {
            "ideas": [{"title": "新观点", "tag": "NEW", "text": "新文本", "source": "manual"}],
            "factorOverrides": {"g1": {"因子": {"score": 2, "note": "人工确认"}}},
        }

        updated = apply_content_overrides(dashboard, overrides)

        self.assertEqual(updated["ideas"][0]["title"], "新观点")
        self.assertEqual(updated["groups"][0]["factors"][0]["score"], 2)
        self.assertEqual(updated["groups"][0]["factors"][0]["note"], "人工确认")

    def test_build_events_keeps_qra_dates_when_auctions_are_dense(self):
        qra = QuarterlyRefunding(
            release_date=date(2026, 5, 6),
            quarter="2026 - 2nd Quarter",
            policy_statement_url="https://home.treasury.gov/news/press-releases/sb0489",
            financing_estimates_url="https://home.treasury.gov/news/press-releases/sb0485",
            next_policy_statement_date=date(2026, 8, 5),
            next_financing_estimates_date=date(2026, 8, 3),
        )
        auctions = [
            {
                "auctionDate": f"2026-05-{day:02d}T00:00:00",
                "securityTerm": "4-Week",
                "securityType": "Bill",
                "offeringAmount": "100000000000",
            }
            for day in range(19, 29)
        ]

        events = build_events(
            date(2026, 5, 19),
            calendar_events=[
                CalendarEvent(date=date(2026, 6, 17), title="FOMC decision + SEP", source="Federal Reserve FOMC calendar", importance="高"),
                CalendarEvent(date=date(2026, 6, 10), title="BLS Consumer Price Index", source="FRED release calendar", importance="高"),
                CalendarEvent(date=date(2026, 5, 28), title="BEA GDP (Second Estimate) and Corporate Profits, 1st Quarter 2026", source="BEA release schedule", importance="高"),
                CalendarEvent(date=date(2026, 5, 28), title="BEA Personal Income and Outlays, April 2026", source="BEA release schedule", importance="高"),
                CalendarEvent(date=date(2026, 9, 16), title="FOMC decision + SEP", source="Federal Reserve FOMC calendar", importance="高"),
                CalendarEvent(date=date(2026, 12, 9), title="FOMC decision + SEP", source="Federal Reserve FOMC calendar", importance="高"),
            ],
            announced_auctions=auctions,
            quarterly_refunding=qra,
        )

        self.assertEqual(len(events), 10)
        self.assertGreaterEqual(sum(1 for row in events if "Treasury auction" in row[1]), 3)
        self.assertIn(["2026-05-28", "BEA GDP (Second Estimate) and Corporate Profits, 1st Quarter 2026", "高"], events)
        self.assertIn(["2026-05-28", "BEA Personal Income and Outlays, April 2026", "高"], events)
        self.assertIn(["2026-06-10", "BLS Consumer Price Index", "高"], events)
        self.assertIn(["2026-06-17", "FOMC decision + SEP", "高"], events)
        self.assertIn(["2026-08-03", "Treasury borrowing estimates / QRA pre-release", "中"], events)
        self.assertIn(["2026-08-05", "Treasury quarterly refunding statement", "高"], events)

    def test_build_events_keeps_qra_dates_when_macro_calendar_is_dense(self):
        qra = QuarterlyRefunding(
            release_date=date(2026, 5, 6),
            quarter="2026 - 2nd Quarter",
            policy_statement_url="https://home.treasury.gov/news/press-releases/sb0489",
            financing_estimates_url="https://home.treasury.gov/news/press-releases/sb0485",
            next_policy_statement_date=date(2026, 8, 5),
            next_financing_estimates_date=date(2026, 8, 3),
        )
        calendar_events = [
            CalendarEvent(date=date(2026, 5, 28), title="BEA GDP", source="BEA release schedule", importance="高"),
            CalendarEvent(date=date(2026, 5, 28), title="BEA Personal Income and Outlays", source="BEA release schedule", importance="高"),
            CalendarEvent(date=date(2026, 6, 5), title="BLS Employment Situation", source="FRED release calendar", importance="高"),
            CalendarEvent(date=date(2026, 6, 10), title="BLS Consumer Price Index", source="FRED release calendar", importance="高"),
            CalendarEvent(date=date(2026, 6, 11), title="BLS Producer Price Index", source="FRED release calendar", importance="高"),
            CalendarEvent(date=date(2026, 6, 17), title="FOMC decision + SEP", source="Federal Reserve FOMC calendar", importance="高"),
            CalendarEvent(date=date(2026, 6, 25), title="BEA GDP final", source="BEA release schedule", importance="高"),
            CalendarEvent(date=date(2026, 6, 25), title="BEA Personal Income and Outlays May", source="BEA release schedule", importance="高"),
            CalendarEvent(date=date(2026, 7, 2), title="BLS Employment Situation", source="FRED release calendar", importance="高"),
            CalendarEvent(date=date(2026, 7, 14), title="BLS Consumer Price Index", source="FRED release calendar", importance="高"),
            CalendarEvent(date=date(2026, 7, 15), title="BLS Producer Price Index", source="FRED release calendar", importance="高"),
            CalendarEvent(date=date(2026, 7, 29), title="FOMC decision", source="Federal Reserve FOMC calendar", importance="高"),
        ]

        events = build_events(date(2026, 5, 19), calendar_events=calendar_events, announced_auctions=[], quarterly_refunding=qra)

        self.assertEqual(len(events), 10)
        self.assertIn(["2026-08-05", "Treasury quarterly refunding statement", "高"], events)


class RegionalMonitorTests(unittest.TestCase):
    def synthetic_global_lppl(self):
        def row(symbol, region_key, region_name_cn, proxy_cn, status, score, days):
            return {
                "symbol": symbol,
                "name": symbol,
                "regionKey": region_key,
                "regionName": region_name_cn,
                "regionNameCn": region_name_cn,
                "proxyNoteCn": proxy_cn,
                "available": True,
                "status": status,
                "statusCn": {"risk": "泡沫风险", "watch": "观察", "quiet": "低风险"}[status],
                "score": score,
                "daysToCritical": days,
            }
        return {
            "asOf": "2026-06-12",
            "indices": [
                row("SPY", "us", "美国", "标普500 · SPY", "watch", 55.0, 90),
                row("QQQ", "us", "美国", "纳斯达克100 · QQQ", "risk", 78.0, 30),
                row("KOSPI", "korea", "韩国", "美上市ETF代理 · EWY", "quiet", 30.0, None),
                row("HSI", "hongkong", "香港", "美上市ETF代理 · EWH", "risk", 80.0, 20),
                row("TWII", "taiwan", "台湾", "美上市ETF代理 · EWT", "watch", 50.0, 120),
                row("NIKKEI", "japan", "日本", "美上市ETF代理 · EWJ", "quiet", 25.0, None),
            ],
        }

    def test_groups_six_indices_into_five_regions_with_us_merged(self):
        rm = dashboard_builder.build_regional_monitor(self.synthetic_global_lppl())
        self.assertTrue(rm["available"])
        self.assertEqual(rm["regionOrder"], ["us", "korea", "hongkong", "taiwan", "japan"])
        by_key = {region["key"]: region for region in rm["regions"]}
        # US groups SPY + QQQ into one region.
        self.assertEqual(len(by_key["us"]["indices"]), 2)
        self.assertEqual(by_key["us"]["nameCn"], "美国")
        self.assertEqual({r["symbol"] for r in by_key["us"]["indices"]}, {"SPY", "QQQ"})
        self.assertEqual(len(by_key["korea"]["indices"]), 1)

    def test_region_aggregate_takes_worst_status_and_nearest_window(self):
        rm = dashboard_builder.build_regional_monitor(self.synthetic_global_lppl())
        by_key = {region["key"]: region for region in rm["regions"]}
        # US: SPY watch + QQQ risk → worst is risk; nearest flagged window = 30 (QQQ)
        us_agg = by_key["us"]["aggregate"]
        self.assertEqual(us_agg["status"], "risk")
        self.assertEqual(us_agg["maxScore"], 78.0)
        self.assertEqual(us_agg["minDaysToCritical"], 30)
        self.assertEqual(us_agg["availableCount"], 2)
        # Korea: quiet only → no flagged window
        self.assertEqual(by_key["korea"]["aggregate"]["status"], "quiet")
        self.assertIsNone(by_key["korea"]["aggregate"]["minDaysToCritical"])

    def test_alerting_regions_listed_and_proxy_note_preserved(self):
        rm = dashboard_builder.build_regional_monitor(self.synthetic_global_lppl())
        self.assertEqual(set(rm["alertingRegions"]), {"us", "hongkong"})
        by_key = {region["key"]: region for region in rm["regions"]}
        hk_row = by_key["hongkong"]["indices"][0]
        self.assertEqual(hk_row["proxyNoteCn"], "美上市ETF代理 · EWH")
        self.assertNotIn("proxy", by_key["hongkong"]["nameCn"].lower())

    @staticmethod
    def _bars(symbol, closes, start=date(2024, 1, 2)):
        bars = []
        cursor = start
        for close in closes:
            while cursor.weekday() >= 5:
                cursor += dashboard_builder.timedelta(days=1)
            bars.append(MarketDailyBar(symbol=symbol, date=cursor, open=close, high=close * 1.005, low=close * 0.995, close=close, volume=1_000_000, source="unit-test"))
            cursor += dashboard_builder.timedelta(days=1)
        return bars

    def test_price_factors_uptrend_is_constructive_with_positive_momentum(self):
        closes = [100.0 * (1.0008 ** i) for i in range(260)]
        bars = self._bars("EWX", closes)
        spy = self._bars("SPY", [100.0 * (1.0004 ** i) for i in range(260)])
        pf = dashboard_builder.global_lppl_price_factors(bars, benchmark_bars=spy, as_of=bars[-1].date)
        self.assertTrue(pf["available"])
        self.assertGreater(pf["return3m"], 0)
        self.assertGreater(pf["ma200Gap"], 0)
        self.assertEqual(pf["marketState"], "constructive")
        # Index compounds faster than SPY → positive 3M relative strength.
        self.assertGreater(pf["relativeStrength3m"], 0)

    def test_price_factors_downtrend_with_deep_drawdown_is_stressed(self):
        closes = [100.0] * 130 + [100.0 * (0.995 ** i) for i in range(130)]
        bars = self._bars("EWX", closes)
        spy = self._bars("SPY", [100.0] * 260)
        pf = dashboard_builder.global_lppl_price_factors(bars, benchmark_bars=spy, as_of=bars[-1].date)
        self.assertTrue(pf["available"])
        self.assertLess(pf["ma200Gap"], 0)
        self.assertLessEqual(pf["drawdownFromHigh"], -10.0)
        self.assertEqual(pf["marketState"], "stressed")

    def test_benchmark_relative_strength_is_none(self):
        spy = self._bars("SPY", [100.0 * (1.0005 ** i) for i in range(260)])
        pf = dashboard_builder.global_lppl_price_factors(spy, benchmark_bars=spy, as_of=spy[-1].date, is_benchmark=True)
        self.assertTrue(pf["isBenchmark"])
        self.assertIsNone(pf["relativeStrength3m"])

    def test_price_factors_unavailable_for_short_sample(self):
        bars = self._bars("EWX", [100.0, 101.0, 102.0])
        pf = dashboard_builder.global_lppl_price_factors(bars, benchmark_bars=[], as_of=bars[-1].date)
        self.assertFalse(pf["available"])

    def test_attach_price_factors_and_region_rollup(self):
        spy = self._bars("SPY", [100.0 * (1.0004 ** i) for i in range(260)])
        ewj = self._bars("EWJ", [100.0 * (1.0009 ** i) for i in range(260)])
        rows = [
            {"symbol": "SPY", "regionKey": "us", "regionName": "United States", "regionNameCn": "美国", "available": True, "status": "watch", "statusCn": "观察", "score": 55.0, "daysToCritical": 90, "asOf": spy[-1].date.isoformat()},
            {"symbol": "EWJ", "regionKey": "japan", "regionName": "Japan", "regionNameCn": "日本", "available": True, "status": "quiet", "statusCn": "低风险", "score": 30.0, "daysToCritical": None, "asOf": ewj[-1].date.isoformat()},
        ]
        enriched = dashboard_builder.attach_global_lppl_price_factors(rows, {"SPY": spy, "EWJ": ewj})
        spy_row = next(r for r in enriched if r["symbol"] == "SPY")
        ewj_row = next(r for r in enriched if r["symbol"] == "EWJ")
        self.assertTrue(spy_row["priceFactors"]["available"])
        self.assertTrue(spy_row["priceFactors"]["isBenchmark"])
        self.assertGreater(ewj_row["priceFactors"]["relativeStrength3m"], 0)
        rm = dashboard_builder.build_regional_monitor({"asOf": "2026-06-12", "indices": enriched})
        japan = next(region for region in rm["regions"] if region["key"] == "japan")
        rollup = japan["aggregate"]["priceFactors"]
        self.assertTrue(rollup["available"])
        self.assertIn(rollup["marketState"], {"constructive", "neutral", "stressed"})

    @staticmethod
    def _lppl_history(bars, score_fn):
        return {"points": [{"date": bar.date.isoformat(), "score": score_fn(i, bar)} for i, bar in enumerate(bars)]}

    def test_factor_validation_schema_and_benchmark_handling(self):
        closes = [100.0 * (1.0006 ** i) for i in range(520)]
        spy = self._bars("SPY", [100.0 * (1.0004 ** i) for i in range(520)])
        ewy = self._bars("EWY", closes)
        hist_spy = self._lppl_history(spy, lambda i, b: 30.0 + (i % 20))
        hist_ewy = self._lppl_history(ewy, lambda i, b: 30.0 + (i % 25))

        spy_val = dashboard_builder.build_index_factor_validation("SPY", spy, spy, hist_spy, is_benchmark=True)
        ewy_val = dashboard_builder.build_index_factor_validation("EWY", ewy, spy, hist_ewy, is_benchmark=False)

        self.assertTrue(spy_val["available"])
        self.assertTrue(ewy_val["available"])
        spy_ids = {f["id"] for f in spy_val["factors"]}
        ewy_ids = {f["id"] for f in ewy_val["factors"]}
        # Benchmark (US) has no relative-strength-vs-US factor; other regions do.
        self.assertNotIn("relativeStrength3m", spy_ids)
        self.assertIn("relativeStrength3m", ewy_ids)
        self.assertIn("lpplScore", ewy_ids)
        self.assertIn("momentum3m", ewy_ids)
        self.assertIn("realizedVol", ewy_ids)
        sample = ewy_val["factors"][0]
        for field in ("id", "oosIc3m", "hitRateOos", "baseRate", "lift", "classification", "leadTimeDays"):
            self.assertIn(field, sample)
        self.assertIn(ewy_val["bestFactor"], ewy_ids)

    def test_factor_validation_detects_predictive_lppl_signal(self):
        # Price path with repeated drawdowns; LPPL score spikes in the run-up to each.
        closes = []
        level = 100.0
        crash = []
        for i in range(520):
            in_crash = (i % 104) >= 98
            level *= (0.975 if in_crash else 1.0018)
            closes.append(level)
            crash.append(in_crash)
        ewt = self._bars("EWT", closes)
        spy = self._bars("SPY", [100.0 * (1.0004 ** i) for i in range(520)])

        def predictive_score(i, bar):
            # high score in the ~12 bars before a crash window starts
            window = crash[i + 1: i + 13]
            return 88.0 if any(window) else 28.0
        hist = self._lppl_history(ewt, predictive_score)

        val = dashboard_builder.build_index_factor_validation("EWT", ewt, spy, hist, is_benchmark=False)
        self.assertTrue(val["available"])
        lppl = next(f for f in val["factors"] if f["id"] == "lpplScore")
        # The synthetic LPPL signal leads drawdowns → positive oriented full-sample IC.
        self.assertIsNotNone(lppl["ic3m"])
        self.assertGreater(lppl["ic3m"], 0)
        # A composite is produced and carries evidence-weighted factor weights summing to ~1.
        composite = val.get("composite", {})
        if composite.get("available"):
            self.assertIn("oosIc3m", composite)
            self.assertIn("weights", composite)
            self.assertIn("beatsBestSingleFactor", composite)
            weight_sum = sum(w["weight"] for w in composite["weights"])
            self.assertTrue(abs(weight_sum - 1.0) < 0.05 or weight_sum == 0.0)

    def test_region_composite_weights_calibration_predictive_factors(self):
        # Build a region whose LPPL is strongly predictive and momentum is noise.
        closes = []
        level = 100.0
        crash = []
        for i in range(520):
            in_crash = (i % 104) >= 98
            level *= (0.975 if in_crash else 1.0018)
            closes.append(level)
            crash.append(in_crash)
        ewt = self._bars("EWT", closes)
        spy = self._bars("SPY", [100.0 * (1.0004 ** i) for i in range(520)])
        hist = self._lppl_history(ewt, lambda i, b: 88.0 if any(crash[i + 1: i + 13]) else 28.0)

        val = dashboard_builder.build_index_factor_validation("EWT", ewt, spy, hist, is_benchmark=False)
        composite = val["composite"]
        self.assertTrue(composite["available"])
        # The composite should be validated and carry a lppl weight (it was predictive in calibration).
        weights = {w["id"]: w["weight"] for w in composite["weights"]}
        self.assertIn("lpplScore", weights)
        self.assertGreater(weights["lpplScore"], 0.0)
        self.assertIn(composite["classification"], {"leading", "coincident", "lagging", "none"})

    def test_factor_validation_unavailable_for_short_sample(self):
        bars = self._bars("EWT", [100.0 + i for i in range(40)])
        val = dashboard_builder.build_index_factor_validation("EWT", bars, bars, {"points": []})
        self.assertFalse(val["available"])
        self.assertEqual(val["factors"], [])

    def test_attach_factor_validation_flows_into_regions(self):
        spy = self._bars("SPY", [100.0 * (1.0004 ** i) for i in range(520)])
        ewh = self._bars("EWH", [100.0 * (1.0005 ** i) for i in range(520)])
        rows = [
            {"symbol": "SPY", "regionKey": "us", "regionNameCn": "美国", "available": True, "status": "watch", "statusCn": "观察", "score": 55.0, "daysToCritical": 90, "asOf": spy[-1].date.isoformat()},
            {"symbol": "EWH", "regionKey": "hongkong", "regionNameCn": "香港", "available": True, "status": "quiet", "statusCn": "低风险", "score": 30.0, "daysToCritical": None, "asOf": ewh[-1].date.isoformat()},
        ]
        history = {
            "SPY": self._lppl_history(spy, lambda i, b: 30.0 + (i % 20)),
            "EWH": self._lppl_history(ewh, lambda i, b: 30.0 + (i % 18)),
        }
        enriched = dashboard_builder.attach_global_lppl_factor_validation(rows, {"SPY": spy, "EWH": ewh}, history)
        ewh_row = next(r for r in enriched if r["symbol"] == "EWH")
        self.assertTrue(ewh_row["factorValidation"]["available"])
        self.assertTrue(ewh_row["factorValidation"]["factors"])

    @staticmethod
    def _region(key, name_cn, bubble, market_state, rs, validated_factor=None,
                vol_current=18.0, vol_threshold=24.0):
        agg = {
            "status": bubble,
            "statusCn": {"risk": "泡沫风险", "watch": "观察", "quiet": "低风险"}[bubble],
            "availableCount": 1,
            "indexCount": 1,
            "maxScore": {"risk": 90.0, "watch": 55.0, "quiet": 30.0}[bubble],
            "priceFactors": {
                "available": True,
                "marketState": market_state,
                "marketStateCn": {"stressed": "承压", "neutral": "中性", "constructive": "偏强"}[market_state],
                "relativeStrength3m": rs,
            },
        }
        factors = []
        if validated_factor:
            factors = [{"id": validated_factor, "labelCn": "已实现波动" if validated_factor == "realizedVol" else "LPPL泡沫评分",
                        "classification": "leading", "lift": 1.7, "oosIc3m": -0.5, "leadTimeDays": 23.0,
                        "hitRateOos": 0.4, "baseRate": 0.23, "alertThreshold": vol_threshold}]
        index = {
            "symbol": "EWX",
            "score": agg["maxScore"],
            "priceFactors": {"available": True, "realizedVol": vol_current},
            "factorValidation": {"available": bool(factors), "factors": factors},
        }
        return {"key": key, "name": name_cn, "nameCn": name_cn, "indices": [index], "aggregate": agg}

    def test_factor_alert_breached_when_current_exceeds_threshold(self):
        region = self._region("korea", "韩国", "risk", "neutral", 10.0, validated_factor="realizedVol",
                              vol_current=30.0, vol_threshold=24.0)
        alert = dashboard_builder.build_region_factor_alert(region)
        self.assertTrue(alert["available"])
        self.assertEqual(alert["state"], "breached")
        self.assertEqual(alert["factorId"], "realizedVol")
        self.assertEqual(alert["current"], 30.0)
        self.assertEqual(alert["threshold"], 24.0)
        self.assertIn("历史命中", alert["evidence"])

    def test_factor_alert_approaching_and_normal_states(self):
        approaching = dashboard_builder.build_region_factor_alert(
            self._region("taiwan", "台湾", "risk", "neutral", 5.0, validated_factor="realizedVol", vol_current=22.5, vol_threshold=24.0))
        self.assertEqual(approaching["state"], "approaching")
        normal = dashboard_builder.build_region_factor_alert(
            self._region("japan", "日本", "watch", "neutral", 0.0, validated_factor="realizedVol", vol_current=15.0, vol_threshold=24.0))
        self.assertEqual(normal["state"], "normal")

    def test_factor_alert_unavailable_without_validated_risk_factor(self):
        region = self._region("hongkong", "香港", "quiet", "stressed", -12.0, validated_factor=None)
        self.assertFalse(dashboard_builder.build_region_factor_alert(region)["available"])

    def test_factor_alert_prefers_composite_when_it_beats_best_single(self):
        # Region whose composite is validated AND beats the best single factor → composite drives the alert.
        region = self._region("hongkong", "香港", "watch", "neutral", 0.0, validated_factor="realizedVol", vol_current=15.0, vol_threshold=24.0)
        rep = region["indices"][0]
        rep["factorValidation"]["composite"] = {
            "available": True, "beatsBestSingleFactor": True, "classification": "leading",
            "lift": 1.3, "hitRateOos": 0.5, "baseRate": 0.3, "leadTimeDays": 40.0,
            "currentValue": 1.8, "alertThreshold": 1.2,
        }
        alert = dashboard_builder.build_region_factor_alert(region)
        self.assertEqual(alert["source"], "composite")
        self.assertEqual(alert["factorId"], "regionComposite")
        self.assertEqual(alert["state"], "breached")  # 1.8 >= 1.2
        self.assertIn("综合信号", alert["factorLabelCn"])

    def test_factor_alert_falls_back_to_single_factor_when_composite_weak(self):
        region = self._region("korea", "韩国", "watch", "neutral", 0.0, validated_factor="realizedVol", vol_current=30.0, vol_threshold=24.0)
        rep = region["indices"][0]
        rep["factorValidation"]["composite"] = {"available": True, "beatsBestSingleFactor": False, "classification": "lagging", "lift": 0.8, "currentValue": 0.5, "alertThreshold": 1.2}
        alert = dashboard_builder.build_region_factor_alert(region)
        self.assertEqual(alert["source"], "factor")
        self.assertEqual(alert["factorId"], "realizedVol")

    def test_factor_alert_carries_full_history_breach_track_record(self):
        region = {
            "key": "korea", "nameCn": "韩国", "name": "韩国",
            "aggregate": {"availableCount": 1, "indexCount": 1, "status": "risk", "statusCn": "泡沫风险"},
            "indices": [{
                "symbol": "EWY", "score": 90.0,
                "priceFactors": {"available": True, "realizedVol": 40.0},
                "factorValidation": {"available": True, "factors": [
                    {"id": "realizedVol", "labelCn": "已实现波动", "classification": "leading", "lift": 1.7,
                     "oosIc3m": -0.5, "leadTimeDays": 23.0, "hitRateOos": 0.4, "baseRate": 0.23,
                     "alertThreshold": 24.0, "alertCountTotal": 11, "hitRateTotal": 0.55},
                ]},
            }],
        }
        alert = dashboard_builder.build_region_factor_alert(region)
        self.assertEqual(alert["source"], "factor")
        self.assertEqual(alert["state"], "breached")
        self.assertEqual(alert["breachCountTotal"], 11)
        self.assertAlmostEqual(alert["breachHitRateTotal"], 0.55)
        self.assertIn("历史共突破11次", alert["trackRecord"])
        self.assertIn("历史共突破11次", alert["message"])

    def test_breached_alert_raises_allocation_caution(self):
        breached = self._region("korea", "韩国", "watch", "neutral", 0.0, validated_factor="realizedVol", vol_current=30.0, vol_threshold=24.0)
        breached["factorAlert"] = dashboard_builder.build_region_factor_alert(breached)
        calm = self._region("korea", "韩国", "watch", "neutral", 0.0, validated_factor="realizedVol", vol_current=15.0, vol_threshold=24.0)
        calm["factorAlert"] = dashboard_builder.build_region_factor_alert(calm)
        breached_alloc = dashboard_builder.build_region_allocation(breached)
        calm_alloc = dashboard_builder.build_region_allocation(calm)
        self.assertGreater(breached_alloc["cautionScore"], calm_alloc["cautionScore"])
        self.assertTrue(any("突破验证阈值" in d for d in breached_alloc["drivers"]))

    def test_allocation_underweights_bubble_and_stressed_region(self):
        region = self._region("korea", "韩国", "risk", "stressed", -8.0, validated_factor="realizedVol")
        alloc = dashboard_builder.build_region_allocation(region)
        self.assertEqual(alloc["stance"], "underweight")
        self.assertEqual(alloc["stanceCn"], "减持")
        self.assertGreaterEqual(alloc["cautionScore"], 55.0)
        self.assertEqual(alloc["confidence"], "high")  # backed by a validated leading factor
        self.assertTrue(alloc["validatedLeadingFactors"])
        self.assertIn("已验证领先因子", alloc["rationale"])

    def test_allocation_overweights_constructive_outperformer(self):
        region = self._region("taiwan", "台湾", "quiet", "constructive", 18.0)
        alloc = dashboard_builder.build_region_allocation(region)
        self.assertEqual(alloc["stance"], "overweight")
        self.assertEqual(alloc["exposureBandPct"][1], 115)
        self.assertLess(alloc["cautionScore"], 30.0)

    def test_allocation_neutral_without_validated_factor_is_lower_confidence(self):
        region = self._region("japan", "日本", "watch", "neutral", 0.0)
        alloc = dashboard_builder.build_region_allocation(region)
        self.assertEqual(alloc["stance"], "neutral")
        self.assertIn(alloc["confidence"], {"medium", "low"})
        self.assertFalse(alloc["validatedLeadingFactors"])
        self.assertIn("尚无 OOS 验证领先因子", alloc["rationale"])

    def test_rotation_lists_favor_and_reduce_regions(self):
        regions = [
            {**self._region("korea", "韩国", "risk", "stressed", -8.0, "realizedVol"),
             "allocation": dashboard_builder.build_region_allocation(self._region("korea", "韩国", "risk", "stressed", -8.0, "realizedVol"))},
            {**self._region("taiwan", "台湾", "quiet", "constructive", 18.0),
             "allocation": dashboard_builder.build_region_allocation(self._region("taiwan", "台湾", "quiet", "constructive", 18.0))},
        ]
        rotation = dashboard_builder.build_regional_rotation(regions)
        self.assertTrue(rotation["available"])
        self.assertIn("taiwan", rotation["favorRegions"])
        self.assertIn("korea", rotation["reduceRegions"])
        self.assertEqual(rotation["ranking"][0], "taiwan")  # lowest caution ranked first

    def test_rotation_merges_correlated_reduce_regions_into_one_risk_budget(self):
        def reducing(key, name):
            r = self._region(key, name, "risk", "stressed", -8.0, "realizedVol")
            r["allocation"] = dashboard_builder.build_region_allocation(r)
            return r
        regions = [reducing("korea", "韩国"), reducing("taiwan", "台湾"), reducing("japan", "日本")]
        # Korea/Taiwan highly correlated; Japan independent.
        diversification = {
            "available": True,
            "matrix": [
                {"a": "korea", "b": "taiwan", "corr": 0.82},
                {"a": "korea", "b": "japan", "corr": 0.30},
                {"a": "taiwan", "b": "japan", "corr": 0.28},
            ],
        }
        rotation = dashboard_builder.build_regional_rotation(regions, diversification)
        self.assertEqual(set(rotation["reduceRegions"]), {"korea", "taiwan", "japan"})
        # 3 reduces collapse to 2 independent risk budgets (korea+taiwan merged).
        self.assertEqual(rotation["independentReduceCount"], 2)
        merged = [c for c in rotation["reduceClusters"] if c["merged"]]
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0]["regions"]), {"korea", "taiwan"})
        self.assertIn("同一风险敞口", rotation["summary"])
        # The correlated cluster shares ONE exposure band (tightest member band), and the
        # summary tells the user not to stack reductions.
        self.assertEqual(merged[0]["exposureBandPct"], [50, 75])
        self.assertIn("共享一个减仓额度", rotation["summary"])
        self.assertIn("共享仓位带", rotation["summary"])

    def test_merged_cluster_band_takes_elementwise_min(self):
        self.assertEqual(dashboard_builder.merged_cluster_band([[50, 75], [60, 90]]), [50, 75])
        self.assertEqual(dashboard_builder.merged_cluster_band([[50, 80]]), [50, 80])
        self.assertIsNone(dashboard_builder.merged_cluster_band([None, "x"]))

    @staticmethod
    def _us_index(symbol, status, score, vol):
        return {
            "symbol": symbol, "status": status,
            "statusCn": {"risk": "泡沫风险", "watch": "观察", "quiet": "低风险"}[status],
            "score": score,
            "priceFactors": {"available": True, "realizedVol": vol, "marketStateCn": "偏强"},
        }

    def test_us_internal_rotation_tilts_to_broad_when_tech_riskier(self):
        us = {"key": "us", "indices": [
            self._us_index("SPY", "watch", 55.0, 14.0),
            self._us_index("QQQ", "risk", 78.0, 22.0),  # tech higher on all three
        ]}
        rot = dashboard_builder.build_us_internal_rotation(us)
        self.assertTrue(rot["available"])
        self.assertEqual(rot["tilt"], "broad")
        self.assertGreater(rot["techPoints"], rot["broadPoints"])
        self.assertIn("偏宽基", rot["tiltCn"])
        self.assertTrue(rot["drivers"])

    def test_us_internal_rotation_tilts_to_tech_when_broad_riskier(self):
        us = {"key": "us", "indices": [
            self._us_index("SPY", "risk", 80.0, 25.0),
            self._us_index("QQQ", "quiet", 30.0, 16.0),
        ]}
        rot = dashboard_builder.build_us_internal_rotation(us)
        self.assertEqual(rot["tilt"], "tech")
        self.assertIn("偏科技", rot["tiltCn"])

    def test_ohlcv_staleness_is_trading_day_aware_over_weekend(self):
        from datetime import date as _date
        # Friday close viewed on Monday = 1 trading day old → NOT stale despite 3 calendar days.
        rows = [{"name": "Nasdaq SPY OHLCV", "status": "ok", "latest": "2026-06-12"}]
        annotated = dashboard_builder.annotate_source_status_freshness(rows, as_of=_date(2026, 6, 15))
        self.assertEqual(annotated[0]["ageDays"], 1)
        self.assertEqual(annotated[0]["status"], "ok")
        # A genuinely stale feed (>2 trading days) is still flagged.
        rows2 = [{"name": "Nasdaq SPY OHLCV", "status": "ok", "latest": "2026-06-08"}]
        annotated2 = dashboard_builder.annotate_source_status_freshness(rows2, as_of=_date(2026, 6, 15))
        self.assertEqual(annotated2[0]["status"], "stale")
        # Non-market sources keep calendar-day age.
        rows3 = [{"name": "NY Fed ACM term premium", "status": "ok", "latest": "2026-06-12"}]
        annotated3 = dashboard_builder.annotate_source_status_freshness(rows3, as_of=_date(2026, 6, 15))
        self.assertEqual(annotated3[0]["ageDays"], 3)

    def test_us_internal_rotation_balanced_and_unavailable(self):
        us_bal = {"key": "us", "indices": [
            self._us_index("SPY", "watch", 55.0, 18.0),
            self._us_index("QQQ", "watch", 55.0, 18.0),
        ]}
        self.assertEqual(dashboard_builder.build_us_internal_rotation(us_bal)["tilt"], "balanced")
        us_one = {"key": "us", "indices": [self._us_index("SPY", "watch", 55.0, 18.0)]}
        self.assertFalse(dashboard_builder.build_us_internal_rotation(us_one)["available"])

    def test_cluster_correlated_regions_without_diversification_is_singletons(self):
        clusters = dashboard_builder.cluster_correlated_regions(["korea", "taiwan"], None)
        self.assertEqual(clusters, [["korea"], ["taiwan"]])

    def test_build_regional_monitor_attaches_allocation_and_rotation(self):
        spy = self._bars("SPY", [100.0 * (1.0004 ** i) for i in range(520)])
        ewh = self._bars("EWH", [100.0 * (1.0005 ** i) for i in range(520)])
        rows = [
            {"symbol": "SPY", "regionKey": "us", "regionNameCn": "美国", "available": True, "status": "watch", "statusCn": "观察", "score": 55.0, "daysToCritical": 90, "asOf": spy[-1].date.isoformat()},
            {"symbol": "EWH", "regionKey": "hongkong", "regionNameCn": "香港", "available": True, "status": "quiet", "statusCn": "低风险", "score": 30.0, "daysToCritical": None, "asOf": ewh[-1].date.isoformat()},
        ]
        enriched = dashboard_builder.attach_global_lppl_price_factors(rows, {"SPY": spy, "EWH": ewh})
        rm = dashboard_builder.build_regional_monitor({"asOf": "2026-06-12", "indices": enriched})
        self.assertTrue(rm["rotation"]["available"])
        for region in rm["regions"]:
            self.assertIn("allocation", region)
            self.assertIn(region["allocation"]["stance"], {"overweight", "neutral", "underweight"})

    @staticmethod
    def _region_with_history(key, name_cn, closes, start=date(2024, 1, 2)):
        bars = RegionalMonitorTests._bars(key.upper(), closes, start=start)
        points = [{"date": b.date.isoformat(), "close": b.close} for b in bars]
        index = {"symbol": key.upper(), "history": {"available": True, "points": points},
                 "factorValidation": {"available": True, "factors": [{"id": "x"}]}}
        return {
            "key": key, "nameCn": name_cn, "name": name_cn,
            "indices": [index],
            "aggregate": {"availableCount": 1, "indexCount": 1, "status": "quiet", "statusCn": "低风险"},
        }

    def test_diversification_detects_correlated_and_diversifying_regions(self):
        import random
        rng = random.Random(7)
        base = [100.0]
        for _ in range(400):
            base.append(base[-1] * (1 + rng.uniform(-0.015, 0.016)))
        # korea = base; taiwan = base + small noise (highly correlated); japan = independent.
        taiwan = [c * (1 + rng.uniform(-0.001, 0.001)) for c in base]
        indep = [100.0]
        for _ in range(400):
            indep.append(indep[-1] * (1 + rng.uniform(-0.015, 0.016)))
        regions = [
            self._region_with_history("korea", "韩国", base),
            self._region_with_history("taiwan", "台湾", taiwan),
            self._region_with_history("japan", "日本", indep),
        ]
        div = dashboard_builder.build_regional_diversification(regions)
        self.assertTrue(div["available"])
        self.assertTrue(div["matrix"])
        # Korea/Taiwan should be the most correlated pair.
        pair = {div["mostCorrelatedPair"]["a"], div["mostCorrelatedPair"]["b"]}
        self.assertEqual(pair, {"korea", "taiwan"})
        self.assertGreater(div["mostCorrelatedPair"]["corr"], 0.9)
        # Japan should be the best diversifier (lowest avg correlation).
        self.assertEqual(div["bestDiversifier"]["key"], "japan")

    def test_diversification_unavailable_with_one_region(self):
        regions = [self._region_with_history("korea", "韩国", [100.0 + i for i in range(400)])]
        self.assertFalse(dashboard_builder.build_regional_diversification(regions)["available"])

    def test_health_payload_surfaces_regional_breach_alerts(self):
        from treasury_data.api import build_health_payload
        dashboard = {
            "asOf": "2026-06-12",
            "generatedAt": "2026-06-13T00:00:00+00:00",
            "sourceStatus": [{"name": "FRED", "status": "ok"}],
            "regionalMonitor": {
                "available": True,
                "asOf": "2026-06-12",
                "rotation": {"available": True, "reduceRegions": ["korea"], "favorRegions": [], "summary": "减持韩国"},
                "regions": [
                    {"key": "korea", "nameCn": "韩国",
                     "factorAlert": {"available": True, "state": "breached", "factorLabelCn": "已实现波动", "current": 43.0, "threshold": 12.0}},
                    {"key": "japan", "nameCn": "日本", "factorAlert": {"available": True, "state": "normal"}},
                ],
            },
        }
        payload = build_health_payload(dashboard)
        ra = payload["regionalAlerts"]
        self.assertTrue(ra["available"])
        self.assertEqual(ra["breachCount"], 1)
        self.assertEqual(ra["breached"][0]["key"], "korea")
        self.assertEqual(ra["reduceRegions"], ["korea"])

    def test_health_payload_regional_alerts_unavailable_without_monitor(self):
        from treasury_data.api import build_health_payload
        payload = build_health_payload({"asOf": "x", "generatedAt": "y", "sourceStatus": []})
        self.assertFalse(payload["regionalAlerts"]["available"])

    def test_unavailable_without_indices(self):
        self.assertFalse(dashboard_builder.build_regional_monitor({"indices": []})["available"])
        self.assertFalse(dashboard_builder.build_regional_monitor(None)["available"])

    def test_specs_carry_region_metadata_and_clean_names(self):
        by_symbol = {spec["symbol"]: spec for spec in dashboard_builder.GLOBAL_LPPL_INDEX_SPECS}
        self.assertEqual(by_symbol["SPY"]["regionKey"], "us")
        self.assertEqual(by_symbol["QQQ"]["regionKey"], "us")
        self.assertEqual(by_symbol["HSI"]["regionNameCn"], "香港")
        for spec in dashboard_builder.GLOBAL_LPPL_INDEX_SPECS:
            self.assertNotIn("proxy", str(spec["name"]).lower())


if __name__ == "__main__":
    unittest.main()
