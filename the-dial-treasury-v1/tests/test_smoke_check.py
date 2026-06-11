import unittest
from datetime import date, timedelta

from scripts.smoke_check import (
    REQUIRED_EQUITY_COMPONENT_KEYS,
    REQUIRED_EQUITY_PANEL_COMPONENT_KEYS,
    REQUIRED_EQUITY_SOURCE_STATUS_NAMES,
    has_equity_short_term_risk_contract,
    has_global_lppl_risk_contract,
    has_spy_early_warning_contract,
    validate_health_payload,
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
                {"name": "Global LPPL SPY OHLCV", "status": "ok", "latest": "2026-06-05"},
                {"name": "Global LPPL QQQ OHLCV", "status": "ok", "latest": "2026-06-05"},
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
                "weightCalibration": {
                    "available": True,
                    "basis": "componentDiagnostics from the current historical replay backtest",
                    "summary": "按历史分项诊断重配: 验证保留90.0%权重,降权/审计7.0%,背景3.0%。",
                    "validatedWeightPct": 90.0,
                    "downweightedWeightPct": 7.0,
                    "contextWeightPct": 3.0,
                    "topValidatedComponents": ["marketFlow", "hotStockReversal"],
                    "downweightedComponents": ["sectorRotation", "eventRisk"],
                    "rows": [
                        {
                            "component": component,
                            "label": component,
                            "configuredWeight": 0.1,
                            "configuredWeightPct": 10.0,
                            "scoreUse": "missing" if component == "optionOI" else "scored",
                            "sourceQuality": "low" if component == "optionOI" else "high",
                            "historicalReplay": component != "optionOI",
                            "diagnosticDecision": "trim" if component in {"sectorRotation", "eventRisk", "optionOI"} else "support",
                            "diagnosticDecisionCn": "降权/审计" if component in {"sectorRotation", "eventRisk", "optionOI"} else "辅助保留",
                            "calibratedRole": "downweighted" if component in {"sectorRotation", "eventRisk", "optionOI"} else "validated",
                            "calibratedRoleCn": "降权/审计" if component in {"sectorRotation", "eventRisk", "optionOI"} else "验证保留",
                            "precision": 75.0,
                            "recall": 12.0,
                            "falsePositives": 2,
                            "recommendation": "保留低到中权重。",
                        }
                        for component in REQUIRED_EQUITY_PANEL_COMPONENT_KEYS
                    ],
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
                    "precisionThresholdTests": [
                        {"threshold": 75, "horizon": 15, "alertDays": 4, "precision": 75.0, "recall": 10.0, "falsePositives": 1},
                        {"threshold": 85, "horizon": 15, "alertDays": 2, "precision": 100.0, "recall": 6.0, "falsePositives": 0},
                    ],
                    "highPrecisionThresholdTest": {
                        "threshold": 85,
                        "horizon": 15,
                        "alertDays": 2,
                        "precision": 100.0,
                        "recall": 6.0,
                        "falsePositives": 0,
                        "label": "高精度强告警阈值",
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
            "globalLpplRisk": {
                "available": True,
                "title": "Global LPPL Risk · 全球指数泡沫临界风险",
                "score": None,
                "scoreUse": "independent",
                "regime": "Per-Index",
                "regimeCn": "逐市场",
                "asOf": "2026-06-05",
                "summary": "LPPL逐市场独立评估显示部分全球指数接近临界窗口。",
                "method": "LPPL grid search over tc/m/omega with linear least-squares fit.",
                "indices": [
                    {
                        "symbol": "SPY",
                        "name": "SPY",
                        "region": "US",
                        "available": True,
                        "score": 64.2,
                        "confidence": 0.58,
                        "status": "risk",
                        "statusCn": "泡沫风险",
                        "criticalDate": "2026-07-10",
                        "daysToCritical": 25,
                        "fitR2": 0.91,
                        "windowDays": 252,
                        "observations": 252,
                        "sourceQuality": "high",
                        "reason": "LPPL fit is coherent and critical window is near.",
                        "effectiveWeightMultiplier": 0.85,
                        "validation": {
                            "symbol": "SPY",
                            "sourceSymbol": "SPY",
                            "sampleSize": 40,
                            "threshold": 65,
                            "alertDays": 8,
                            "truePositives": 5,
                            "falsePositives": 3,
                            "precision15d": 62.5,
                            "recall15d": 10.0,
                            "effectiveWeightMultiplier": 0.85,
                            "validationRole": "mixed",
                            "validationRoleCn": "部分支持",
                            "summary": "SPY own-market 15D audit.",
                        },
                        "history": {
                            "available": True,
                            "points": [
                                {"date": "2026-06-03", "score": 52.1, "close": 600.0, "indexedClose": 100.0},
                                {"date": "2026-06-04", "score": 58.0, "close": 606.0, "indexedClose": 101.0},
                                {"date": "2026-06-05", "score": 64.2, "close": 597.0, "indexedClose": 99.5},
                            ],
                        },
                        "backtest": {
                            "available": True,
                            "sampleSize": 120,
                            "threshold": 65,
                            "horizonTests": [
                                {"horizon": 5, "alertDays": 8, "truePositives": 5, "precision": 62.5, "recall": 10.0, "falsePositives": 3},
                                {"horizon": 10, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                                {"horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                                {"horizon": 20, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            ],
                            "calibrationGrid": [
                                {"threshold": 60, "horizon": 15, "alertDays": 10, "truePositives": 6, "precision": 60.0, "recall": 12.0, "falsePositives": 4},
                                {"threshold": 65, "horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                                {"threshold": 70, "horizon": 15, "alertDays": 5, "truePositives": 4, "precision": 80.0, "recall": 8.0, "falsePositives": 1},
                            ],
                            "recommendedThreshold": {"threshold": 65, "horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            "alertClusterTest": {"clusterCount": 3, "hitClusters": 2, "falseClusters": 1, "maxFalseClusterDays": 2, "precision": 66.7},
                        },
                    },
                    {
                        "symbol": "QQQ",
                        "name": "Nasdaq / QQQ proxy",
                        "region": "US tech",
                        "available": True,
                        "score": 68.0,
                        "confidence": 0.61,
                        "status": "risk",
                        "statusCn": "泡沫风险",
                        "criticalDate": "2026-07-08",
                        "daysToCritical": 23,
                        "fitR2": 0.92,
                        "windowDays": 252,
                        "observations": 252,
                        "sourceQuality": "high",
                        "reason": "LPPL fit is coherent and critical window is near.",
                        "effectiveWeightMultiplier": 1.0,
                        "validation": {
                            "symbol": "QQQ",
                            "sourceSymbol": "QQQ",
                            "sampleSize": 40,
                            "threshold": 65,
                            "alertDays": 8,
                            "truePositives": 6,
                            "falsePositives": 2,
                            "precision15d": 75.0,
                            "recall15d": 12.0,
                            "effectiveWeightMultiplier": 1.0,
                            "validationRole": "validated",
                            "validationRoleCn": "验证支持",
                            "summary": "QQQ own-market 15D audit.",
                        },
                        "history": {
                            "available": True,
                            "points": [
                                {"date": "2026-06-03", "score": 55.0, "close": 500.0, "indexedClose": 100.0},
                                {"date": "2026-06-04", "score": 61.0, "close": 510.0, "indexedClose": 102.0},
                                {"date": "2026-06-05", "score": 68.0, "close": 494.0, "indexedClose": 98.8},
                            ],
                        },
                        "backtest": {
                            "available": True,
                            "sampleSize": 120,
                            "threshold": 65,
                            "horizonTests": [
                                {"horizon": 5, "alertDays": 8, "truePositives": 5, "precision": 62.5, "recall": 10.0, "falsePositives": 3},
                                {"horizon": 10, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                                {"horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                                {"horizon": 20, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            ],
                            "calibrationGrid": [
                                {"threshold": 60, "horizon": 15, "alertDays": 10, "truePositives": 6, "precision": 60.0, "recall": 12.0, "falsePositives": 4},
                                {"threshold": 65, "horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                                {"threshold": 70, "horizon": 15, "alertDays": 5, "truePositives": 4, "precision": 80.0, "recall": 8.0, "falsePositives": 1},
                            ],
                            "recommendedThreshold": {"threshold": 65, "horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            "alertClusterTest": {"clusterCount": 3, "hitClusters": 2, "falseClusters": 1, "maxFalseClusterDays": 2, "precision": 66.7},
                        },
                    },
                    {
                        "symbol": "KOSPI",
                        "name": "KOSPI Composite",
                        "region": "Korea",
                        "available": False,
                        "score": None,
                        "confidence": 0.0,
                        "status": "missing",
                        "statusCn": "缺失",
                        "reason": "source unavailable",
                        "sourceQuality": "medium",
                    },
                    {
                        "symbol": "HSI",
                        "name": "Hang Seng",
                        "region": "Hong Kong",
                        "available": False,
                        "score": None,
                        "confidence": 0.0,
                        "status": "missing",
                        "statusCn": "缺失",
                        "reason": "source unavailable",
                        "sourceQuality": "medium",
                    },
                    {
                        "symbol": "TWII",
                        "name": "Taiwan Weighted",
                        "region": "Taiwan",
                        "available": False,
                        "score": None,
                        "confidence": 0.0,
                        "status": "missing",
                        "statusCn": "缺失",
                        "reason": "source unavailable",
                        "sourceQuality": "medium",
                    },
                    {
                        "symbol": "NIKKEI",
                        "name": "Nikkei 225",
                        "region": "Japan",
                        "available": False,
                        "score": None,
                        "confidence": 0.0,
                        "status": "missing",
                        "statusCn": "缺失",
                        "reason": "source unavailable",
                        "sourceQuality": "medium",
                    },
                ],
                "indexValidation": {
                    "available": True,
                    "summary": "2 indices replayed; 1 validated, 0 weak by own-market 15D drawdown audit.",
                    "rows": [
                        {
                            "symbol": "SPY",
                            "sourceSymbol": "SPY",
                            "sampleSize": 40,
                            "threshold": 65,
                            "alertDays": 8,
                            "truePositives": 5,
                            "falsePositives": 3,
                            "precision15d": 62.5,
                            "recall15d": 10.0,
                            "effectiveWeightMultiplier": 0.85,
                            "validationRole": "mixed",
                            "validationRoleCn": "部分支持",
                            "summary": "SPY own-market 15D audit.",
                        },
                        {
                            "symbol": "QQQ",
                            "sourceSymbol": "QQQ",
                            "sampleSize": 40,
                            "threshold": 65,
                            "alertDays": 8,
                            "truePositives": 6,
                            "falsePositives": 2,
                            "precision15d": 75.0,
                            "recall15d": 12.0,
                            "effectiveWeightMultiplier": 1.0,
                            "validationRole": "validated",
                            "validationRoleCn": "验证支持",
                            "summary": "QQQ own-market 15D audit.",
                        },
                    ],
                },
                "history": {
                    "available": False,
                    "points": [],
                    "summary": "Top-level aggregate LPPL history is disabled; use per-index histories.",
                },
                "backtest": {
                    "available": False,
                    "sampleSize": 0,
                    "horizonTests": [],
                    "summary": "Top-level aggregate LPPL backtest is disabled; use per-index backtests.",
                },
                "perIndexHistory": {
                    "SPY": {
                        "available": True,
                        "points": [
                            {"date": "2026-06-03", "score": 52.1, "close": 600.0, "indexedClose": 100.0},
                            {"date": "2026-06-04", "score": 58.0, "close": 606.0, "indexedClose": 101.0},
                            {"date": "2026-06-05", "score": 64.2, "close": 597.0, "indexedClose": 99.5},
                        ],
                    },
                    "QQQ": {
                        "available": True,
                        "points": [
                            {"date": "2026-06-03", "score": 55.0, "close": 500.0, "indexedClose": 100.0},
                            {"date": "2026-06-04", "score": 61.0, "close": 510.0, "indexedClose": 102.0},
                            {"date": "2026-06-05", "score": 68.0, "close": 494.0, "indexedClose": 98.8},
                        ],
                    },
                },
                "perIndexBacktests": {
                    "SPY": {
                        "available": True,
                        "sampleSize": 120,
                        "threshold": 65,
                        "horizonTests": [
                            {"horizon": 5, "alertDays": 8, "truePositives": 5, "precision": 62.5, "recall": 10.0, "falsePositives": 3},
                            {"horizon": 10, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            {"horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            {"horizon": 20, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                        ],
                        "calibrationGrid": [
                            {"threshold": 60, "horizon": 15, "alertDays": 10, "truePositives": 6, "precision": 60.0, "recall": 12.0, "falsePositives": 4},
                            {"threshold": 65, "horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            {"threshold": 70, "horizon": 15, "alertDays": 5, "truePositives": 4, "precision": 80.0, "recall": 8.0, "falsePositives": 1},
                        ],
                        "recommendedThreshold": {"threshold": 65, "horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                        "alertClusterTest": {"clusterCount": 3, "hitClusters": 2, "falseClusters": 1, "maxFalseClusterDays": 2, "precision": 66.7},
                    },
                    "QQQ": {
                        "available": True,
                        "sampleSize": 120,
                        "threshold": 65,
                        "horizonTests": [
                            {"horizon": 5, "alertDays": 8, "truePositives": 5, "precision": 62.5, "recall": 10.0, "falsePositives": 3},
                            {"horizon": 10, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            {"horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            {"horizon": 20, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                        ],
                        "calibrationGrid": [
                            {"threshold": 60, "horizon": 15, "alertDays": 10, "truePositives": 6, "precision": 60.0, "recall": 12.0, "falsePositives": 4},
                            {"threshold": 65, "horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                            {"threshold": 70, "horizon": 15, "alertDays": 5, "truePositives": 4, "precision": 80.0, "recall": 8.0, "falsePositives": 1},
                        ],
                        "recommendedThreshold": {"threshold": 65, "horizon": 15, "alertDays": 8, "truePositives": 6, "precision": 75.0, "recall": 12.0, "falsePositives": 2},
                        "alertClusterTest": {"clusterCount": 3, "hitClusters": 2, "falseClusters": 1, "maxFalseClusterDays": 2, "precision": 66.7},
                    },
                },
            },
        }

        self.assertEqual(validate_dashboard(dashboard), [])

    def test_global_lppl_risk_contract_rejects_missing_scores_as_available(self):
        payload = {
            "available": True,
            "title": "Global LPPL Risk · 全球指数泡沫临界风险",
            "score": None,
            "scoreUse": "independent",
            "regime": "Unavailable",
            "regimeCn": "不可用",
            "asOf": "2026-06-05",
            "summary": "missing",
            "method": "LPPL",
            "indices": [],
            "history": {"available": False, "points": []},
            "backtest": {"available": False, "sampleSize": 0, "horizonTests": []},
        }

        self.assertFalse(has_global_lppl_risk_contract(payload))

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

        self.assertIn("equity daily OHLCV source monitoring incomplete", issues[0])

    def test_validate_dashboard_reports_non_ok_equity_daily_source_name(self):
        dashboard = {
            "asOf": "2026-05-19",
            "generatedAt": "2026-05-20T15:30:34+00:00",
            "meta": {"dataMode": "real-public-sources"},
            "sourceStatus": [
                {"name": "Fed path", "status": "modeled", "latest": "public futures proxy + curve/macro model"},
                *[
                    {"name": name, "status": "ok", "latest": "2026-06-05"}
                    for name in REQUIRED_EQUITY_SOURCE_STATUS_NAMES
                ],
            ],
            "events": [["2026-06-10", "BLS Consumer Price Index", "高"], ["2026-06-17", "FOMC decision", "高"], ["2026-05-28", "BEA GDP", "高"], ["2026-08-05", "Treasury quarterly refunding statement", "高"]],
            "news": [["05/18", "U.S. Treasury", "Treasury International Capital Data for March"]],
            "cross": {"inflation": [["黄金现货", "$4536.70", "Stooq XAUUSD"]], "historySeries": [{"series": [{"category": "risk", "name": "S&P 500"}]}, {"series": [{"category": "commodity", "name": "WTI原油"}]}]},
            "ideas": [],
            "spyEarlyWarning": {},
            "equityShortTermRisk": {},
            "globalLpplRisk": {},
        }
        dashboard["sourceStatus"][-1] = {"name": REQUIRED_EQUITY_SOURCE_STATUS_NAMES[-1], "status": "warning", "latest": "timeout"}

        issues = validate_dashboard(dashboard)

        self.assertTrue(any(REQUIRED_EQUITY_SOURCE_STATUS_NAMES[-1] in issue for issue in issues))

    def test_validate_health_payload_requires_equity_freshness_timing_fields(self):
        health = {
            "status": "degraded",
            "equityRiskFreshness": {
                "expectedDate": "2026-06-08",
                "sourceDate": "2026-06-05",
                "stale": True,
                "lagDays": 1,
            },
        }

        issues = validate_health_payload(health)

        self.assertIn("equityRiskFreshness missing phase", issues)
        self.assertIn("equityRiskFreshness missing timeliness", issues)

    def test_validate_health_payload_accepts_equity_freshness_timing_contract(self):
        health = {
            "status": "degraded",
            "equityRiskFreshness": {
                "expectedDate": "2026-06-08",
                "sourceDate": "2026-06-05",
                "stale": True,
                "lagDays": 1,
                "phase": "catchup",
                "timeliness": "catchup",
                "marketTime": "2026-06-08T16:40:00-04:00",
                "readyAt": "2026-06-08T16:20:00-04:00",
                "minutesSinceExpected": 20,
                "minutesUntilExpected": 0,
            },
        }

        self.assertEqual(validate_health_payload(health), [])

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
