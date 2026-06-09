import unittest
from datetime import date, timedelta

from scripts.smoke_check import (
    REQUIRED_EQUITY_COMPONENT_KEYS,
    REQUIRED_EQUITY_SOURCE_STATUS_NAMES,
    has_equity_short_term_risk_contract,
    has_spy_early_warning_contract,
    validate_dashboard,
)


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
                *[
                    {"name": name, "status": "ok", "latest": "2026-06-05"}
                    for name in REQUIRED_EQUITY_SOURCE_STATUS_NAMES
                ],
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
            "ideas": [
                {
                    "title": "战术减久期",
                    "tag": "SHORT 久期",
                    "text": "通胀偏热时维持低于基准久期。",
                    "source": "宏观基本面",
                    "confidenceLevel": "high",
                    "confidenceLabel": "高可信",
                    "confidenceNote": "证据质量 0.96",
                    "equityImpact": {
                        "available": True,
                        "proxy": "S&P 500 price-index proxy for SPY",
                        "basis": "同类宏观评分水平 + 3M评分变化",
                        "sampleSize": 9,
                        "summary": "历史同类环境下,S&P 500价格指数代理SPY未来3M中位回报+1.44%,胜率67%,样本9; 仅为历史统计,不构成方向承诺。",
                    },
                }
            ],
            "spyEarlyWarning": {
                "available": True,
                "score": 52.4,
                "baseScore": 48.0,
                "regime": "Neutral",
                "summary": "SPY预警52.4,处于中性: 宏观评分改善,但外部冲击仍需跟踪。",
                "allocation": {
                    "stance": "持有/控仓",
                    "equityExposure": "维持核心仓位,避免追高",
                    "hedgeAction": "等待信用/波动或评分转弱确认",
                },
                "amplifiers": [
                    {"key": "rallyFragility", "label": "上涨后宏观转弱", "scoreBoost": 6.0},
                ],
                "dampeners": [
                    {"key": "postSelloffExhaustion", "label": "深跌后降噪", "scoreOffset": -10.0},
                ],
                "sleeves": [{"key": "macroDeterioration", "score": 12.0}],
                "drivers": [{"name": "WTI原油冲击", "riskScore": 94.0}],
                "trend": {
                    "available": True,
                    "points": [
                        {"date": "2026-04-30", "score": 48.2, "regime": "Neutral"},
                        {"date": "2026-05-29", "score": 52.4, "regime": "Neutral"},
                    ],
                },
                "backtest": {
                    "target": "3M SPX drawdown and negative forward-return warning",
                    "sampleSize": 54,
                },
            },
            "equityShortTermRisk": {
                "available": True,
                "score": 82.4,
                "baseScore": 79.1,
                "regime": "Strong Alert",
                "regimeCn": "强告警",
                "asOf": "2026-06-04",
                "method": "0-100 short-horizon equity risk index from daily OHLCV market structure.",
                "summary": "2026-06-04收盘前短周期风险为强告警。",
                "allocation": {
                    "stance": "短线降风险",
                    "equityExposure": "高Beta/AI拥挤仓位降到低配",
                    "hedgeAction": "收盘前优先减仓或买入1-2周保护性对冲",
                },
                "components": [
                    {"key": "volTargetPressure", "label": "多尺度波动目标压力", "available": True, "score": 82.0, "detail": "vol pressure", "scoreUse": "scored", "sourceQuality": "high"},
                    {"key": "qqqTltRotation", "label": "QQQ/TLT风险切换", "available": True, "score": 81.0, "detail": "QQQ/TLT", "scoreUse": "scored", "sourceQuality": "high"},
                    {"key": "marketFlow", "label": "股市资金/趋势", "available": True, "score": 88.0, "detail": "SPY 63D +10.3%", "scoreUse": "scored", "sourceQuality": "high"},
                    {"key": "sectorRotation", "label": "板块轮动断裂", "available": True, "score": 92.0, "detail": "SMH跑输SPY", "scoreUse": "scored", "sourceQuality": "high"},
                    {"key": "hotStockReversal", "label": "热点股集体回落", "available": True, "score": 90.0, "detail": "热点股回落", "scoreUse": "scored", "sourceQuality": "high"},
                    {"key": "turnover", "label": "成交承接", "available": True, "score": 78.0, "detail": "缩量冲高", "scoreUse": "scored", "sourceQuality": "high"},
                    {"key": "macroOverlay", "label": "已有宏观因子叠加", "available": True, "score": 52.0, "detail": "macro overlay", "scoreUse": "scored", "sourceQuality": "medium"},
                    {"key": "eventRisk", "label": "新闻/事件风险", "available": True, "score": 90.0, "detail": "BLS Employment Situation", "scoreUse": "scored", "sourceQuality": "medium"},
                    {"key": "optionOI", "label": "期权OI趋势", "available": False, "score": None, "detail": "audit only", "scoreUse": "missing", "sourceQuality": "low"},
                ],
                "drivers": [{"key": "lateRotationBreak", "name": "高热板块当日跑输", "riskScore": 92.0}],
                "factorEvidence": [
                    {"component": "marketFlow", "label": "股市资金/趋势", "weight": 0.22, "source": "Nasdaq daily OHLCV", "sourceQuality": "high", "historicalReplay": True, "scoreUse": "scored", "coverageStart": "2025-10-28", "coverageEnd": "2026-06-04", "observations": 660, "timestampPolicy": "same-day or earlier bars", "reason": "daily bars can be replayed"},
                    {"component": "sectorRotation", "label": "板块轮动断裂", "weight": 0.24, "source": "Nasdaq daily OHLCV", "sourceQuality": "high", "historicalReplay": True, "scoreUse": "scored", "coverageStart": "2025-10-28", "coverageEnd": "2026-06-04", "observations": 880, "timestampPolicy": "same-day or earlier bars", "reason": "ETF bars can be replayed"},
                    {"component": "hotStockReversal", "label": "热点股集体回落", "weight": 0.20, "source": "Nasdaq daily OHLCV", "sourceQuality": "high", "historicalReplay": True, "scoreUse": "scored", "coverageStart": "2025-10-28", "coverageEnd": "2026-06-04", "observations": 1320, "timestampPolicy": "same-day or earlier bars", "reason": "stock bars can be replayed"},
                    {"component": "turnover", "label": "成交承接", "weight": 0.10, "source": "Nasdaq daily OHLCV", "sourceQuality": "high", "historicalReplay": True, "scoreUse": "scored", "coverageStart": "2025-10-28", "coverageEnd": "2026-06-04", "observations": 220, "timestampPolicy": "same-day or earlier bars", "reason": "SPY volume can be replayed"},
                    {"component": "eventRisk", "label": "新闻/事件风险", "weight": 0.14, "source": "Official macro release calendar", "sourceQuality": "medium", "historicalReplay": False, "scoreUse": "scored", "coverageStart": "", "coverageEnd": "2026-06-04", "observations": 1, "timestampPolicy": "events known before signal", "reason": "forward calendar is decision relevant"},
                ],
                "sourceQuality": {
                    "verdict": "高可信",
                    "detail": "主分数主要由可历史回放的日线OHLCV分项驱动。",
                    "dataThrough": "2026-06-04",
                    "scoreEligibleWeightPct": 96.0,
                    "historicalReplayableWeightPct": 76.0,
                    "highQualityWeightPct": 76.0,
                    "scoredComponentCount": 5,
                    "auditOnlyComponentCount": 1,
                },
                "forwardCatalystRisk": {
                    "available": True,
                    "score": 90.0,
                    "windowDays": 5,
                    "eventCount": 1,
                    "events": [{"date": "2026-06-08", "title": "BLS Employment Situation", "source": "BLS", "importance": "高"}],
                    "nextEventDate": "2026-06-08",
                    "daysToNextEvent": 4,
                    "knownBeforeSignal": True,
                    "scoreUse": "scored",
                    "summary": "未来5天有1个高重要性事件。",
                },
                "trend": {
                    "available": True,
                    "points": [
                        {
                            "date": (date(2025, 10, 28) + timedelta(days=offset)).isoformat(),
                            "score": 54.0 if offset < 219 else 82.4,
                            "regime": "Watch" if offset < 219 else "Strong Alert",
                        }
                        for offset in range(220)
                    ],
                },
                "backtest": {
                    "available": True,
                    "target": "1-10 trading-day SPY drawdown warning",
                    "sampleSize": 220,
                    "scoreBuckets": [
                        {"label": "Watch", "count": 30, "avgMaxDrawdown10d": -1.4},
                        {"label": "Strong Alert", "count": 4, "avgMaxDrawdown10d": -3.8},
                    ],
                    "thresholdTests": [
                        {"threshold": 75, "alertDays": 4, "truePositives": 3, "precision": 75.0},
                    ],
                    "preferredThresholdTest": {
                        "threshold": 75,
                        "horizon": 15,
                        "alertDays": 4,
                        "truePositives": 3,
                        "precision": 75.0,
                        "avgDrawdownLeadDaysWhenHit": 3.7,
                        "medianDrawdownLeadDaysWhenHit": 4.0,
                    },
                    "alertClusterTest": {
                        "threshold": 75,
                        "horizon": 15,
                        "clusterCount": 3,
                        "hitClusters": 2,
                        "precision": 66.7,
                        "avgLeadDays": 4.0,
                    },
                    "regressionTests": [
                        {"target": "forward10d", "available": True, "sampleSize": 220, "slopePer10Score": -0.25, "rSquared": 0.04},
                        {"target": "maxDrawdown10d", "available": True, "sampleSize": 220, "slopePer10Score": -0.31, "rSquared": 0.06},
                    ],
                    "worstWindows": [
                        {"date": "2026-06-04", "score": 82.4, "maxDrawdown10d": -3.1},
                    ],
                    "alertWindows": [
                        {
                            "date": "2026-06-04",
                            "score": 82.4,
                            "regime": "Strong Alert",
                            "regimeCn": "强告警",
                            "spyClose": 640.2,
                            "forward15d": -1.2,
                            "maxDrawdown10d": -3.1,
                            "maxDrawdown15d": -3.8,
                            "drawdownLeadDays10d": 2,
                        "drawdownLeadDays15d": 2,
                        "threshold": 75,
                        "horizon": 15,
                        "hit": True,
                    },
                ],
                    "componentDiagnostics": [
                        {
                            "component": component,
                            "label": component,
                            "decision": "support",
                            "decisionCn": "辅助保留",
                            "recommendation": "保留低到中权重。",
                            "threshold": 75,
                            "horizon": 15,
                            "sampleSize": 220,
                            "alertDays": 8,
                            "falsePositives": 2,
                            "precision": 75.0,
                            "recall": 12.0,
                        }
                        for component in REQUIRED_EQUITY_COMPONENT_KEYS
                    ],
                },
                "lookAheadGuard": {
                    "dataThrough": "2026-06-04",
                    "scoreInputs": "same-day or earlier",
                    "auditOnly": "next-session shock is audit-only",
                },
            },
        }

        self.assertEqual(validate_dashboard(dashboard), [])

    def test_validate_dashboard_reports_missing_equity_daily_source_monitoring(self):
        dashboard = {
            "asOf": "2026-05-19",
            "generatedAt": "2026-05-20T15:30:34+00:00",
            "meta": {"dataMode": "real-public-sources"},
            "sourceStatus": [{"name": "Fed path", "status": "modeled", "latest": "public futures proxy + curve/macro model"}],
            "events": [["2026-06-10", "BLS Consumer Price Index", "高"], ["2026-06-17", "FOMC decision + SEP", "高"], ["2026-05-28", "BEA GDP", "高"], ["2026-08-05", "Treasury quarterly refunding statement", "高"]],
            "news": [["05/18", "U.S. Treasury", "Treasury International Capital Data for March"]],
            "cross": {"inflation": [["黄金现货", "$4536.70", "Stooq XAUUSD"]], "historySeries": [{"series": [{"category": "risk", "name": "S&P 500"}]}, {"series": [{"category": "commodity", "name": "WTI原油"}]}]},
            "ideas": [],
            "spyEarlyWarning": {},
            "equityShortTermRisk": {},
        }

        issues = validate_dashboard(dashboard)

        self.assertIn("missing equity daily OHLCV source monitoring", issues)

    def test_equity_short_term_risk_contract_requires_component_diagnostics(self):
        payload = {
            "available": True,
            "score": 80.0,
            "regime": "Strong Alert",
            "regimeCn": "强告警",
            "summary": "短期风险强告警。",
            "asOf": "2026-06-04",
            "method": "daily OHLCV",
            "allocation": {"stance": "短线降风险", "equityExposure": "低配", "hedgeAction": "买保护"},
            "components": [
                {"key": key, "label": key, "available": True, "score": 80.0, "detail": key, "scoreUse": "scored", "sourceQuality": "high"}
                for key in REQUIRED_EQUITY_COMPONENT_KEYS
            ],
            "factorEvidence": [
                {"component": key, "label": key, "source": "Nasdaq daily OHLCV", "sourceQuality": "high", "historicalReplay": True, "scoreUse": "scored", "weight": 0.1, "timestampPolicy": "same-day", "reason": "replayable"}
                for key in REQUIRED_EQUITY_COMPONENT_KEYS
            ],
            "sourceQuality": {"verdict": "高可信", "detail": "replayable", "dataThrough": "2026-06-04", "scoreEligibleWeightPct": 100.0, "historicalReplayableWeightPct": 90.0, "highQualityWeightPct": 90.0},
            "forwardCatalystRisk": {"windowDays": 5, "eventCount": 1, "scoreUse": "scored"},
            "drivers": [],
            "trend": {"available": True, "points": [{"date": "2026-01-01", "score": 50.0} for _ in range(220)]},
            "backtest": {
                "available": True,
                "sampleSize": 220,
                "scoreBuckets": [{"label": "Strong Alert"}],
                "thresholdTests": [{"threshold": 75}],
                "regressionTests": [{"target": "maxDrawdown15d"}],
                "worstWindows": [],
                "alertWindows": [],
                "preferredThresholdTest": {"threshold": 75, "avgDrawdownLeadDaysWhenHit": 3.0, "medianDrawdownLeadDaysWhenHit": 3.0},
                "alertClusterTest": {"avgLeadDays": 3.0},
            },
            "lookAheadGuard": {"dataThrough": "2026-06-04"},
        }

        self.assertFalse(has_equity_short_term_risk_contract(payload))

    def test_validate_dashboard_reports_missing_core_requirements(self):
        dashboard = {
            "asOf": "2026-05-19",
            "generatedAt": "2026-05-20T15:30:34+00:00",
            "meta": {"dataMode": "static"},
            "sourceStatus": [{"name": "FRED", "status": "error", "latest": "timeout"}],
            "events": [],
            "news": [["05/19", "FRED", "10Y 4.67%"]],
            "cross": {"inflation": []},
            "ideas": [{"title": "观点缺字段"}],
        }

        issues = validate_dashboard(dashboard)

        self.assertIn("meta.dataMode is not real-public-sources", issues)
        self.assertIn("sourceStatus contains error rows", issues)
        self.assertIn("missing BEA event", issues)
        self.assertIn("missing official news headline", issues)
        self.assertIn("missing gold spot cross-market row", issues)
        self.assertIn("missing cross-market history series", issues)
        self.assertIn("investment ideas missing confidence/equityImpact contract", issues)
        self.assertIn("missing SPY early-warning contract", issues)
        self.assertIn("missing equity short-term risk contract", issues)

    def test_has_equity_short_term_risk_contract_rejects_forward_dated_guard(self):
        payload = {
            "available": True,
            "score": 82.4,
            "regime": "Strong Alert",
            "regimeCn": "强告警",
            "asOf": "2026-06-04",
            "method": "test",
            "summary": "test",
            "allocation": {"stance": "test", "equityExposure": "test", "hedgeAction": "test"},
            "components": [
                {"key": "marketFlow", "label": "股市资金/趋势", "available": True, "score": 88.0, "detail": "ok"},
                {"key": "sectorRotation", "label": "板块轮动断裂", "available": True, "score": 92.0, "detail": "ok"},
                {"key": "hotStockReversal", "label": "热点股集体回落", "available": True, "score": 90.0, "detail": "ok"},
                {"key": "turnover", "label": "成交承接", "available": True, "score": 78.0, "detail": "ok"},
                {"key": "eventRisk", "label": "新闻/事件风险", "available": True, "score": 90.0, "detail": "ok"},
            ],
            "drivers": [],
            "trend": {
                "available": True,
                "points": [
                    {"date": (date(2025, 10, 28) + timedelta(days=offset)).isoformat(), "score": 82.4}
                    for offset in range(220)
                ],
            },
            "backtest": {
                "available": True,
                "target": "1-10 trading-day SPY drawdown warning",
                "sampleSize": 220,
                "scoreBuckets": [{"label": "Strong Alert", "count": 1}],
                "thresholdTests": [{"threshold": 75, "alertDays": 1}],
                "regressionTests": [{"target": "forward10d", "available": True, "sampleSize": 220}],
                "worstWindows": [{"date": "2026-06-04", "score": 82.4}],
            },
            "lookAheadGuard": {"dataThrough": "2026-06-05"},
        }

        self.assertFalse(has_equity_short_term_risk_contract(payload))

    def test_has_equity_short_term_risk_contract_rejects_short_history_replay(self):
        start = date(2026, 3, 1)
        points = [{"date": (start + timedelta(days=offset)).isoformat(), "score": 78.0} for offset in range(63)]
        payload = {
            "available": True,
            "score": 82.4,
            "regime": "Strong Alert",
            "regimeCn": "强告警",
            "asOf": "2026-05-05",
            "method": "test",
            "summary": "test",
            "allocation": {"stance": "test", "equityExposure": "test", "hedgeAction": "test"},
            "components": [
                {"key": "marketFlow", "label": "股市资金/趋势", "available": True, "score": 88.0, "detail": "ok"},
                {"key": "sectorRotation", "label": "板块轮动断裂", "available": True, "score": 92.0, "detail": "ok"},
                {"key": "hotStockReversal", "label": "热点股集体回落", "available": True, "score": 90.0, "detail": "ok"},
                {"key": "turnover", "label": "成交承接", "available": True, "score": 78.0, "detail": "ok"},
                {"key": "eventRisk", "label": "新闻/事件风险", "available": True, "score": 90.0, "detail": "ok"},
            ],
            "drivers": [],
            "trend": {"available": True, "points": points},
            "backtest": {
                "available": True,
                "target": "1-15 trading-day SPY drawdown warning",
                "sampleSize": 62,
                "scoreBuckets": [{"label": "Strong Alert", "count": 5}],
                "thresholdTests": [{"threshold": 75, "alertDays": 5}],
                "regressionTests": [{"target": "maxDrawdown15d", "available": True, "sampleSize": 62}],
                "worstWindows": [{"date": "2026-05-05", "score": 82.4}],
            },
            "lookAheadGuard": {"dataThrough": "2026-05-05"},
        }

        self.assertFalse(has_equity_short_term_risk_contract(payload))

    def test_spy_early_warning_contract_requires_chart_trend(self):
        payload = {
            "available": True,
            "score": 52.4,
            "baseScore": 48.0,
            "regime": "Neutral",
            "summary": "SPY预警52.4,处于中性。",
            "allocation": {
                "stance": "持有/控仓",
                "equityExposure": "维持核心仓位",
                "hedgeAction": "等待确认",
            },
            "amplifiers": [],
            "dampeners": [],
            "sleeves": [{"key": "macroDeterioration", "score": 12.0}],
            "drivers": [],
            "backtest": {
                "target": "3M SPX drawdown and negative forward-return warning",
                "sampleSize": 54,
            },
        }

        self.assertFalse(has_spy_early_warning_contract(payload))

    def test_spy_early_warning_contract_requires_calibration_layer(self):
        payload = {
            "available": True,
            "score": 52.4,
            "regime": "Neutral",
            "summary": "SPY预警52.4,处于中性。",
            "allocation": {
                "stance": "持有/控仓",
                "equityExposure": "维持核心仓位",
                "hedgeAction": "等待确认",
            },
            "sleeves": [{"key": "macroDeterioration", "score": 12.0}],
            "drivers": [],
            "trend": {
                "available": True,
                "points": [
                    {"date": "2026-05-29", "score": 52.4, "regime": "Neutral"},
                ],
            },
            "backtest": {
                "target": "3M SPX drawdown and negative forward-return warning",
                "sampleSize": 54,
            },
        }

        self.assertFalse(has_spy_early_warning_contract(payload))

        payload["baseScore"] = 48.0
        payload["amplifiers"] = [{"key": "rallyFragility", "label": "上涨后宏观转弱", "scoreBoost": 6.0}]
        payload["dampeners"] = [{"key": "postSelloffExhaustion", "label": "深跌后降噪", "scoreOffset": -10.0}]

        self.assertTrue(has_spy_early_warning_contract(payload))

    def test_spy_early_warning_contract_requires_dampeners_layer(self):
        payload = {
            "available": True,
            "score": 52.4,
            "baseScore": 48.0,
            "regime": "Neutral",
            "summary": "SPY预警52.4,处于中性。",
            "allocation": {
                "stance": "持有/控仓",
                "equityExposure": "维持核心仓位",
                "hedgeAction": "等待确认",
            },
            "amplifiers": [],
            "sleeves": [{"key": "macroDeterioration", "score": 12.0}],
            "drivers": [],
            "trend": {
                "available": True,
                "points": [
                    {"date": "2026-05-29", "score": 52.4, "regime": "Neutral"},
                ],
            },
            "backtest": {
                "target": "3M SPX drawdown and negative forward-return warning",
                "sampleSize": 54,
            },
        }

        self.assertFalse(has_spy_early_warning_contract(payload))

        payload["dampeners"] = []

        self.assertTrue(has_spy_early_warning_contract(payload))


if __name__ == "__main__":
    unittest.main()
