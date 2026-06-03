import unittest

from scripts.smoke_check import has_spy_early_warning_contract, validate_dashboard


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
