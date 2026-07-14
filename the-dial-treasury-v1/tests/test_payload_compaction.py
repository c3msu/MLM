import json
import unittest
from datetime import date, timedelta

from treasury_data.build_dashboard import compact_dashboard_payload
from treasury_data.scoring_lppl_history import compact_global_lppl_index_payloads
from treasury_data.scoring_regional import build_regional_monitor


class PayloadCompactionTests(unittest.TestCase):
    def test_lppl_history_and_backtest_have_one_canonical_body(self):
        history = {
            "available": True,
            "points": [
                {"date": (date(2024, 1, 2) + timedelta(days=index)).isoformat(), "score": 50 + index % 20, "close": 100 + index}
                for index in range(500)
            ],
        }
        backtest = {
            "available": True,
            "sampleSize": 500,
            "horizonTests": [{"horizon": horizon, "alertDays": 30} for horizon in (5, 10, 15, 20)],
            "calibrationGrid": [{"threshold": threshold, "observations": list(range(100))} for threshold in range(50, 81, 5)],
        }
        rows = [
            {"symbol": symbol, "available": True, "score": 70, "history": history, "backtest": backtest}
            for symbol in ("SPY", "QQQ")
        ]
        full_payload = {
            "indices": rows,
            "perIndexHistory": {symbol: history for symbol in ("SPY", "QQQ")},
            "perIndexBacktests": {symbol: backtest for symbol in ("SPY", "QQQ")},
        }

        compact_rows = compact_global_lppl_index_payloads(rows)
        compact_payload = {**full_payload, "indices": compact_rows}

        self.assertTrue(all("history" not in row and "backtest" not in row for row in compact_rows))
        self.assertEqual(compact_rows[0]["historyRef"]["path"], "globalLpplRisk.perIndexHistory.SPY")
        self.assertIs(compact_payload["perIndexHistory"]["SPY"], history)
        self.assertLess(len(json.dumps(compact_payload)), len(json.dumps(full_payload)) * 0.65)

    def test_regional_monitor_hydrates_canonical_history_then_serializes_summaries(self):
        start = date(2024, 1, 2)

        def history(symbol: str, drift: float) -> dict:
            return {
                "available": True,
                "symbol": symbol,
                "points": [
                    {
                        "date": (start + timedelta(days=index)).isoformat(),
                        "score": 45.0,
                        "close": round(100 * (1 + drift) ** index, 4),
                        "indexedClose": round(100 * (1 + drift) ** index, 4),
                    }
                    for index in range(220)
                ],
            }

        rows = [
            {
                "symbol": "SPY",
                "name": "S&P 500",
                "regionKey": "us",
                "regionNameCn": "美国",
                "available": True,
                "score": 45.0,
                "confidence": 0.6,
                "status": "quiet",
                "statusCn": "低风险",
                "priceFactors": {"available": True, "marketState": "constructive", "marketStateCn": "偏强", "return3m": 3.0, "realizedVol": 12.0},
                "factorValidation": {"available": True, "factors": []},
                "historyRef": {"symbol": "SPY", "path": "globalLpplRisk.perIndexHistory.SPY"},
            },
            {
                "symbol": "EWJ",
                "name": "Japan ETF",
                "regionKey": "japan",
                "regionNameCn": "日本",
                "available": True,
                "score": 42.0,
                "confidence": 0.5,
                "status": "quiet",
                "statusCn": "低风险",
                "priceFactors": {"available": True, "marketState": "constructive", "marketStateCn": "偏强", "return3m": 2.0, "realizedVol": 11.0, "relativeStrength3m": -1.0},
                "factorValidation": {"available": True, "factors": []},
                "historyRef": {"symbol": "EWJ", "path": "globalLpplRisk.perIndexHistory.EWJ"},
            },
        ]
        payload = {
            "asOf": "2026-07-13",
            "indices": rows,
            "perIndexHistory": {"SPY": history("SPY", 0.0005), "EWJ": history("EWJ", 0.0003)},
            "perIndexBacktests": {"SPY": {"available": True}, "EWJ": {"available": True}},
        }

        monitor = build_regional_monitor(payload)

        self.assertTrue(monitor["available"])
        self.assertTrue(monitor["diversification"]["available"])
        for region in monitor["regions"]:
            for row in region["indices"]:
                self.assertNotIn("history", row)
                self.assertNotIn("backtest", row)
                self.assertIn("globalIndexRef", row)
                self.assertIn("historyRef", row)

    def test_equity_component_scores_are_build_only(self):
        component_scores = {
            f"component-{index}": {"score": 40 + index, "weight": 0.1, "audit": list(range(40))}
            for index in range(10)
        }
        dashboard = {
            "equityShortTermRisk": {
                "trend": {
                    "available": True,
                    "points": [
                        {"date": f"2026-07-{day:02d}", "score": 65.0, "componentScores": component_scores}
                        for day in range(1, 21)
                    ],
                },
                "backtest": {"available": True, "componentDiagnostics": [{"component": "marketFlow", "precision": 0.7}]},
            }
        }

        compact = compact_dashboard_payload(dashboard)

        self.assertTrue(compact["equityShortTermRisk"]["backtest"]["available"])
        self.assertNotIn("componentScores", compact["equityShortTermRisk"]["trend"]["points"][0])
        self.assertIn("componentScores", dashboard["equityShortTermRisk"]["trend"]["points"][0])
        self.assertLess(len(json.dumps(compact)), len(json.dumps(dashboard)) * 0.2)


if __name__ == "__main__":
    unittest.main()
