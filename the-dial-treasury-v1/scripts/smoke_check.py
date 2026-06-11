from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from treasury_data.build_dashboard import EQUITY_RISK_COMPONENT_WEIGHTS, EQUITY_RISK_SYMBOLS  # noqa: E402

DEFAULT_DASHBOARD = PROJECT_ROOT / "data" / "dashboard.json"
EQUITY_SHORT_TERM_RISK_MIN_HISTORY_POINTS = 200
REQUIRED_EQUITY_SOURCE_STATUS_NAMES = tuple(f"Nasdaq {symbol} OHLCV" for symbol in EQUITY_RISK_SYMBOLS)
REQUIRED_EQUITY_PANEL_COMPONENT_KEYS = tuple(EQUITY_RISK_COMPONENT_WEIGHTS.keys())
REQUIRED_EQUITY_COMPONENT_KEYS = tuple(key for key in EQUITY_RISK_COMPONENT_WEIGHTS if key != "optionOI")
EQUITY_COMPONENT_DIAGNOSTIC_DECISIONS = {"core", "support", "context", "trim"}


def load_dashboard(path: Path | None = None, url: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
    if url:
        endpoint = url.rstrip("/") + "/api/dashboard"
        with urlopen(endpoint, timeout=timeout) as response:
            payload = json.load(response)
    else:
        with (path or DEFAULT_DASHBOARD).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("dashboard payload is not a JSON object")
    return payload


def load_health(url: str, timeout: float = 10.0) -> dict[str, Any]:
    endpoint = url.rstrip("/") + "/api/health"
    with urlopen(endpoint, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("health payload is not a JSON object")
    return payload


def validate_dashboard(dashboard: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if dashboard.get("meta", {}).get("dataMode") != "real-public-sources":
        issues.append("meta.dataMode is not real-public-sources")
    if not parse_iso_date(dashboard.get("asOf")):
        issues.append("asOf is missing or invalid")
    if not parse_iso_datetime(dashboard.get("generatedAt")):
        issues.append("generatedAt is missing or invalid")

    source_status = dashboard.get("sourceStatus", [])
    if not isinstance(source_status, list):
        issues.append("sourceStatus is not a list")
    else:
        errors = [row for row in source_status if isinstance(row, dict) and row.get("status") == "error"]
        if errors:
            issues.append("sourceStatus contains error rows")
        if not any(isinstance(row, dict) and row.get("name") == "Fed path" and row.get("status") == "modeled" for row in source_status):
            issues.append("Fed path modeled boundary is not explicit")
        equity_issues = equity_source_status_issues(source_status)
        if equity_issues:
            issues.append("equity daily OHLCV source monitoring incomplete: " + "; ".join(equity_issues[:5]))

    event_titles = list_texts(dashboard.get("events", []), column=1)
    required_events = {
        "BEA": "missing BEA event",
        "BLS": "missing BLS event",
        "FOMC": "missing FOMC event",
        "quarterly refunding": "missing QRA event",
    }
    for needle, message in required_events.items():
        if not any(needle in title for title in event_titles):
            issues.append(message)

    news_sources = list_texts(dashboard.get("news", []), column=1)
    if not any(source in {"U.S. Treasury", "Federal Reserve"} for source in news_sources):
        issues.append("missing official news headline")

    inflation_rows = dashboard.get("cross", {}).get("inflation", [])
    inflation_labels = list_texts(inflation_rows, column=0)
    if "黄金现货" not in inflation_labels:
        issues.append("missing gold spot cross-market row")
    history_series = dashboard.get("cross", {}).get("historySeries", [])
    if not has_cross_history_target(history_series, "risk", "S&P 500") or not has_cross_history_target(history_series, "commodity", "WTI原油"):
        issues.append("missing cross-market history series")
    if not ideas_have_investment_contract(dashboard.get("ideas", [])):
        issues.append("investment ideas missing confidence/equityImpact contract")
    if not has_spy_early_warning_contract(dashboard.get("spyEarlyWarning")):
        issues.append("missing SPY early-warning contract")
    if not has_equity_short_term_risk_contract(dashboard.get("equityShortTermRisk")):
        issues.append("missing equity short-term risk contract")
    if not has_global_lppl_risk_contract(dashboard.get("globalLpplRisk")):
        issues.append("missing global LPPL risk contract")
    return issues


def validate_health_payload(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    freshness = payload.get("equityRiskFreshness")
    if not isinstance(freshness, dict):
        issues.append("missing equityRiskFreshness health payload")
        return issues
    for key in ("expectedDate", "sourceDate"):
        if freshness.get(key) is not None and not parse_iso_date(freshness.get(key)):
            issues.append(f"equityRiskFreshness invalid {key}")
    if not isinstance(freshness.get("stale"), bool):
        issues.append("equityRiskFreshness missing stale")
    if not isinstance(freshness.get("phase"), str) or not freshness.get("phase"):
        issues.append("equityRiskFreshness missing phase")
    if not isinstance(freshness.get("timeliness"), str) or not freshness.get("timeliness"):
        issues.append("equityRiskFreshness missing timeliness")
    if freshness.get("marketTime") is not None and not parse_iso_datetime(freshness.get("marketTime")):
        issues.append("equityRiskFreshness invalid marketTime")
    if freshness.get("readyAt") is not None and not parse_iso_datetime(freshness.get("readyAt")):
        issues.append("equityRiskFreshness invalid readyAt")
    for key in ("minutesUntilExpected", "minutesSinceExpected"):
        value = freshness.get(key)
        if value is not None and not isinstance(value, int):
            issues.append(f"equityRiskFreshness invalid {key}")
    return issues


def parse_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def parse_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def list_texts(rows: Any, column: int) -> list[str]:
    if not isinstance(rows, list):
        return []
    values: list[str] = []
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) > column and isinstance(row[column], str):
            values.append(row[column])
    return values


def has_cross_history_target(groups: Any, category: str, name: str) -> bool:
    if not isinstance(groups, list):
        return False
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("series"), list):
            continue
        for item in group["series"]:
            if isinstance(item, dict) and item.get("category") == category and item.get("name") == name:
                return True
    return False


def has_required_equity_source_status(source_status: Any) -> bool:
    return not equity_source_status_issues(source_status)


def equity_source_status_issues(source_status: Any) -> list[str]:
    if not isinstance(source_status, list):
        return ["sourceStatus is not a list"]
    rows = {
        str(row.get("name") or ""): row
        for row in source_status
        if isinstance(row, dict)
    }
    issues: list[str] = []
    for name in REQUIRED_EQUITY_SOURCE_STATUS_NAMES:
        row = rows.get(name)
        if not isinstance(row, dict):
            issues.append(f"{name} missing")
            continue
        if row.get("status") != "ok":
            issues.append(f"{name} status={row.get('status') or 'missing'}")
            continue
        latest = row.get("latest")
        if not isinstance(latest, str) or not parse_iso_date(latest):
            issues.append(f"{name} latest invalid")
    return issues


def ideas_have_investment_contract(ideas: Any) -> bool:
    if not isinstance(ideas, list) or not ideas:
        return False
    for idea in ideas:
        if not isinstance(idea, dict):
            return False
        for key in ("title", "tag", "text", "source", "confidenceLevel", "confidenceLabel", "confidenceNote"):
            if not isinstance(idea.get(key), str) or not idea.get(key):
                return False
        impact = idea.get("equityImpact")
        if not isinstance(impact, dict):
            return False
        if impact.get("proxy") != "S&P 500 price-index proxy for SPY":
            return False
        if not isinstance(impact.get("summary"), str) or "历史" not in impact.get("summary", ""):
            return False
        if "预测" in impact.get("summary", ""):
            return False
        if not isinstance(impact.get("sampleSize"), int):
            return False
    return True


def has_spy_early_warning_contract(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("available") is not True:
        return False
    score = payload.get("score")
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 100:
        return False
    base_score = payload.get("baseScore")
    if not isinstance(base_score, (int, float)) or not 0 <= float(base_score) <= 100:
        return False
    amplifiers = payload.get("amplifiers")
    if not isinstance(amplifiers, list):
        return False
    for amplifier in amplifiers:
        if not isinstance(amplifier, dict):
            return False
        if not isinstance(amplifier.get("key"), str) or not amplifier.get("key"):
            return False
        if not isinstance(amplifier.get("label"), str) or not amplifier.get("label"):
            return False
        if not isinstance(amplifier.get("scoreBoost"), (int, float)):
            return False
    dampeners = payload.get("dampeners")
    if not isinstance(dampeners, list):
        return False
    for dampener in dampeners:
        if not isinstance(dampener, dict):
            return False
        if not isinstance(dampener.get("key"), str) or not dampener.get("key"):
            return False
        if not isinstance(dampener.get("label"), str) or not dampener.get("label"):
            return False
        if not isinstance(dampener.get("scoreOffset"), (int, float)):
            return False
    for key in ("regime", "summary"):
        if not isinstance(payload.get(key), str) or not payload.get(key):
            return False
    allocation = payload.get("allocation")
    if not isinstance(allocation, dict):
        return False
    for key in ("stance", "equityExposure", "hedgeAction"):
        if not isinstance(allocation.get(key), str) or not allocation.get(key):
            return False
    if not isinstance(payload.get("sleeves"), list) or not payload["sleeves"]:
        return False
    if not isinstance(payload.get("drivers"), list):
        return False
    trend = payload.get("trend")
    if not isinstance(trend, dict) or trend.get("available") is not True:
        return False
    points = trend.get("points")
    if not isinstance(points, list) or not points:
        return False
    for point in points:
        if not isinstance(point, dict):
            return False
        if not parse_iso_date(point.get("date")):
            return False
        point_score = point.get("score")
        if not isinstance(point_score, (int, float)) or not 0 <= float(point_score) <= 100:
            return False
    backtest = payload.get("backtest")
    if not isinstance(backtest, dict):
        return False
    if backtest.get("target") != "3M SPX drawdown and negative forward-return warning":
        return False
    if not isinstance(backtest.get("sampleSize"), int):
        return False
    return True


def has_equity_short_term_risk_contract(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("available") is not True:
        return False
    score = payload.get("score")
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 100:
        return False
    for key in ("regime", "regimeCn", "summary", "asOf", "method"):
        if not isinstance(payload.get(key), str) or not payload.get(key):
            return False
    if not parse_iso_date(payload.get("asOf")):
        return False
    allocation = payload.get("allocation")
    if not isinstance(allocation, dict):
        return False
    for key in ("stance", "equityExposure", "hedgeAction"):
        if not isinstance(allocation.get(key), str) or not allocation.get(key):
            return False
    components = payload.get("components")
    if not isinstance(components, list) or len(components) < 5:
        return False
    component_keys = {
        str(component.get("key") or "")
        for component in components
        if isinstance(component, dict)
    }
    if not set(REQUIRED_EQUITY_PANEL_COMPONENT_KEYS).issubset(component_keys):
        return False
    for component in components:
        if not isinstance(component, dict):
            return False
        for key in ("key", "label", "detail"):
            if not isinstance(component.get(key), str) or not component.get(key):
                return False
        if component.get("scoreUse") not in {"scored", "auditOnly", "missing"}:
            return False
        if component.get("sourceQuality") not in {"high", "medium", "low"}:
            return False
        if component.get("available") is True:
            component_score = component.get("score")
            if not isinstance(component_score, (int, float)) or not 0 <= float(component_score) <= 100:
                return False
    factor_evidence = payload.get("factorEvidence")
    if not isinstance(factor_evidence, list) or len(factor_evidence) < 5:
        return False
    for evidence in factor_evidence:
        if not isinstance(evidence, dict):
            return False
        for key in ("component", "label", "source", "sourceQuality", "scoreUse", "timestampPolicy", "reason"):
            if not isinstance(evidence.get(key), str) or not evidence.get(key):
                return False
        if evidence.get("scoreUse") not in {"scored", "auditOnly", "missing"}:
            return False
        if not isinstance(evidence.get("historicalReplay"), bool):
            return False
        if not isinstance(evidence.get("weight"), (int, float)):
            return False
    source_quality = payload.get("sourceQuality")
    if not isinstance(source_quality, dict):
        return False
    for key in ("verdict", "detail", "dataThrough"):
        if not isinstance(source_quality.get(key), str) or not source_quality.get(key):
            return False
    if source_quality.get("dataThrough") != payload.get("asOf"):
        return False
    for key in ("scoreEligibleWeightPct", "historicalReplayableWeightPct", "highQualityWeightPct"):
        value = source_quality.get(key)
        if not isinstance(value, (int, float)) or not 0 <= float(value) <= 100:
            return False
    if float(source_quality.get("scoreEligibleWeightPct")) < 70:
        return False
    if float(source_quality.get("historicalReplayableWeightPct")) < 60:
        return False
    weight_calibration = payload.get("weightCalibration")
    if not isinstance(weight_calibration, dict) or weight_calibration.get("available") is not True:
        return False
    for key in ("basis", "summary"):
        if not isinstance(weight_calibration.get(key), str) or not weight_calibration.get(key):
            return False
    for key in ("validatedWeightPct", "downweightedWeightPct", "contextWeightPct"):
        value = weight_calibration.get(key)
        if not isinstance(value, (int, float)) or not 0 <= float(value) <= 100:
            return False
    calibration_rows = weight_calibration.get("rows")
    if not isinstance(calibration_rows, list):
        return False
    calibration_keys = {
        str(row.get("component") or "")
        for row in calibration_rows
        if isinstance(row, dict)
    }
    if not set(REQUIRED_EQUITY_PANEL_COMPONENT_KEYS).issubset(calibration_keys):
        return False
    for row in calibration_rows:
        if not isinstance(row, dict):
            return False
        for key in ("component", "label", "scoreUse", "sourceQuality", "diagnosticDecision", "calibratedRole", "calibratedRoleCn"):
            if not isinstance(row.get(key), str) or not row.get(key):
                return False
        if row.get("calibratedRole") not in {"validated", "downweighted", "context"}:
            return False
        if not isinstance(row.get("configuredWeight"), (int, float)):
            return False
    forward_catalyst = payload.get("forwardCatalystRisk")
    if not isinstance(forward_catalyst, dict):
        return False
    if not isinstance(forward_catalyst.get("windowDays"), int) or forward_catalyst.get("windowDays") < 1:
        return False
    if not isinstance(forward_catalyst.get("eventCount"), int):
        return False
    if forward_catalyst.get("scoreUse") not in {"scored", "auditOnly", "missing"}:
        return False
    if not isinstance(payload.get("drivers"), list):
        return False
    trend = payload.get("trend")
    if not isinstance(trend, dict) or trend.get("available") is not True:
        return False
    points = trend.get("points")
    if not isinstance(points, list) or len(points) < EQUITY_SHORT_TERM_RISK_MIN_HISTORY_POINTS:
        return False
    for point in points:
        if not isinstance(point, dict) or not parse_iso_date(point.get("date")):
            return False
        point_score = point.get("score")
        if not isinstance(point_score, (int, float)) or not 0 <= float(point_score) <= 100:
            return False
    backtest = payload.get("backtest")
    if not isinstance(backtest, dict) or backtest.get("available") is not True:
        return False
    if (
        not isinstance(backtest.get("sampleSize"), int)
        or backtest.get("sampleSize") < EQUITY_SHORT_TERM_RISK_MIN_HISTORY_POINTS
    ):
        return False
    if not isinstance(backtest.get("scoreBuckets"), list) or not backtest.get("scoreBuckets"):
        return False
    if not isinstance(backtest.get("thresholdTests"), list) or not backtest.get("thresholdTests"):
        return False
    if not isinstance(backtest.get("regressionTests"), list) or not backtest.get("regressionTests"):
        return False
    if not isinstance(backtest.get("worstWindows"), list):
        return False
    component_diagnostics = backtest.get("componentDiagnostics")
    if not isinstance(component_diagnostics, list) or not component_diagnostics:
        return False
    diagnostic_keys = {
        str(row.get("component") or "")
        for row in component_diagnostics
        if isinstance(row, dict)
    }
    if not set(REQUIRED_EQUITY_COMPONENT_KEYS).issubset(diagnostic_keys):
        return False
    for row in component_diagnostics:
        if not isinstance(row, dict):
            return False
        for key in ("component", "label", "decision", "decisionCn", "recommendation"):
            if not isinstance(row.get(key), str) or not row.get(key):
                return False
        if row.get("decision") not in EQUITY_COMPONENT_DIAGNOSTIC_DECISIONS:
            return False
        for key in ("threshold", "horizon", "sampleSize", "alertDays", "falsePositives"):
            if not isinstance(row.get(key), int):
                return False
        for key in ("precision", "recall"):
            value = row.get(key)
            if value is not None and not isinstance(value, (int, float)):
                return False
    alert_windows = backtest.get("alertWindows")
    if not isinstance(alert_windows, list):
        return False
    for window in alert_windows[:5]:
        if not isinstance(window, dict):
            return False
        if not parse_iso_date(window.get("date")):
            return False
        if not isinstance(window.get("score"), (int, float)) or not 0 <= float(window.get("score")) <= 100:
            return False
        if not isinstance(window.get("hit"), bool):
            return False
        if not isinstance(window.get("horizon"), int):
            return False
        if "maxDrawdown15d" not in window or "drawdownLeadDays15d" not in window:
            return False
    preferred = backtest.get("preferredThresholdTest")
    if not isinstance(preferred, dict) or preferred.get("threshold") != 75:
        return False
    if "avgDrawdownLeadDaysWhenHit" not in preferred or "medianDrawdownLeadDaysWhenHit" not in preferred:
        return False
    precision_tests = backtest.get("precisionThresholdTests")
    if not isinstance(precision_tests, list) or not precision_tests:
        return False
    high_precision = backtest.get("highPrecisionThresholdTest")
    if not isinstance(high_precision, dict):
        return False
    for key in ("threshold", "precision", "recall", "alertDays", "falsePositives"):
        if key not in high_precision:
            return False
    alert_cluster = backtest.get("alertClusterTest")
    if not isinstance(alert_cluster, dict) or "avgLeadDays" not in alert_cluster:
        return False
    guard = payload.get("lookAheadGuard")
    if not isinstance(guard, dict) or not parse_iso_date(guard.get("dataThrough")):
        return False
    if guard.get("dataThrough") != payload.get("asOf"):
        return False
    return True


def has_global_lppl_risk_contract(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("scoreUse") != "independent":
        return False
    for key in ("title", "regime", "regimeCn", "summary", "method"):
        if not isinstance(payload.get(key), str) or not payload.get(key):
            return False
    if "Global LPPL Risk" not in payload.get("title", ""):
        return False
    if payload.get("available") is True:
        if payload.get("score") is not None:
            return False
        if payload.get("regime") != "Per-Index" or payload.get("regimeCn") != "逐市场":
            return False
        if not parse_iso_date(payload.get("asOf")):
            return False
    elif payload.get("score") is not None:
        return False
    indices = payload.get("indices")
    if not isinstance(indices, list) or len(indices) < 6:
        return False
    for row in indices:
        if not isinstance(row, dict):
            return False
        for key in ("symbol", "name", "region", "status", "statusCn", "reason", "sourceQuality"):
            if not isinstance(row.get(key), str) or not row.get(key):
                return False
        if not isinstance(row.get("available"), bool):
            return False
        row_score = row.get("score")
        if row.get("available"):
            if not isinstance(row_score, (int, float)) or not 0 <= float(row_score) <= 100:
                return False
            if not isinstance(row.get("confidence"), (int, float)) or not 0 <= float(row.get("confidence")) <= 1:
                return False
            if not parse_iso_date(row.get("criticalDate")):
                return False
            if not isinstance(row.get("daysToCritical"), int):
                return False
            if not isinstance(row.get("fitR2"), (int, float)) or not 0 <= float(row.get("fitR2")) <= 1:
                return False
            if not isinstance(row.get("windowDays"), int):
                return False
            if not isinstance(row.get("effectiveWeightMultiplier"), (int, float)):
                return False
            validation = row.get("validation")
            if not isinstance(validation, dict) or validation.get("symbol") != row.get("symbol"):
                return False
            if not has_lppl_history_contract(row.get("history"), require_available=True):
                return False
            if not has_lppl_backtest_contract(row.get("backtest"), require_available=True):
                return False
        elif row_score is not None:
            return False
    index_validation = payload.get("indexValidation")
    if not isinstance(index_validation, dict):
        return False
    if payload.get("available") is True:
        if index_validation.get("available") is not True:
            return False
        validation_rows = index_validation.get("rows")
        if not isinstance(validation_rows, list) or len(validation_rows) < 2:
            return False
        for row in validation_rows:
            if not isinstance(row, dict):
                return False
            for key in ("symbol", "sourceSymbol", "validationRole", "validationRoleCn", "summary"):
                if not isinstance(row.get(key), str) or not row.get(key):
                    return False
            for key in ("sampleSize", "threshold", "alertDays", "truePositives", "falsePositives"):
                if not isinstance(row.get(key), int):
                    return False
            multiplier = row.get("effectiveWeightMultiplier")
            if not isinstance(multiplier, (int, float)) or not 0 < float(multiplier) <= 1:
                return False
    elif not isinstance(index_validation.get("rows"), list):
        return False
    history = payload.get("history")
    if not isinstance(history, dict):
        return False
    if history.get("available") is True or not isinstance(history.get("points"), list):
        return False
    backtest = payload.get("backtest")
    if not isinstance(backtest, dict):
        return False
    if backtest.get("available") is True or not isinstance(backtest.get("horizonTests"), list):
        return False
    per_index_history = payload.get("perIndexHistory")
    per_index_backtests = payload.get("perIndexBacktests")
    if not isinstance(per_index_history, dict) or not isinstance(per_index_backtests, dict):
        return False
    for row in indices:
        if not isinstance(row, dict) or not row.get("available"):
            continue
        symbol = str(row.get("symbol") or "")
        if not has_lppl_history_contract(per_index_history.get(symbol), require_available=True):
            return False
        if not has_lppl_backtest_contract(per_index_backtests.get(symbol), require_available=True):
            return False
    return True


def has_lppl_history_contract(payload: Any, *, require_available: bool = False) -> bool:
    if not isinstance(payload, dict):
        return False
    if require_available and payload.get("available") is not True:
        return False
    points = payload.get("points")
    if not isinstance(points, list):
        return False
    if payload.get("available") is not True:
        return not require_available
    if len(points) < 2:
        return False
    for point in points[:5]:
        if not isinstance(point, dict) or not parse_iso_date(point.get("date")):
            return False
        if not isinstance(point.get("score"), (int, float)) or not 0 <= float(point.get("score")) <= 100:
            return False
        close = point.get("close")
        indexed = point.get("indexedClose")
        if not isinstance(close, (int, float)) or float(close) <= 0:
            return False
        if not isinstance(indexed, (int, float)) or float(indexed) <= 0:
            return False
    return True


def has_lppl_backtest_contract(payload: Any, *, require_available: bool = False) -> bool:
    if not isinstance(payload, dict):
        return False
    if require_available and payload.get("available") is not True:
        return False
    horizon_tests = payload.get("horizonTests")
    if not isinstance(horizon_tests, list):
        return False
    if payload.get("available") is not True:
        return not require_available
    if not isinstance(payload.get("sampleSize"), int):
        return False
    if [row.get("horizon") for row in horizon_tests] != [5, 10, 15, 20]:
        return False
    for row in horizon_tests:
        if not isinstance(row, dict):
            return False
        for key in ("alertDays", "truePositives", "falsePositives"):
            if not isinstance(row.get(key), int):
                return False
    calibration_grid = payload.get("calibrationGrid")
    if not isinstance(calibration_grid, list) or len(calibration_grid) < 3:
        return False
    recommended = payload.get("recommendedThreshold")
    if not isinstance(recommended, dict) or not isinstance(recommended.get("threshold"), int):
        return False
    cluster = payload.get("alertClusterTest")
    if not isinstance(cluster, dict):
        return False
    for key in ("clusterCount", "hitClusters", "falseClusters", "maxFalseClusterDays"):
        if not isinstance(cluster.get(key), int):
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-check the Treasury dashboard runtime contract")
    parser.add_argument("--path", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--url", help="Base URL such as http://127.0.0.1:8451")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    dashboard = load_dashboard(path=args.path, url=args.url, timeout=args.timeout)
    issues = validate_dashboard(dashboard)
    if args.url:
        health = load_health(args.url, timeout=args.timeout)
        issues.extend(validate_health_payload(health))
    if issues:
        print("SMOKE FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 2
    print(
        "SMOKE OK "
        f"asOf={dashboard.get('asOf')} "
        f"generatedAt={dashboard.get('generatedAt')} "
        f"sources={len(dashboard.get('sourceStatus', []))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
