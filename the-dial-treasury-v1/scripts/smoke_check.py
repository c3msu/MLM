from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DASHBOARD = PROJECT_ROOT / "data" / "dashboard.json"


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-check the Treasury dashboard runtime contract")
    parser.add_argument("--path", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--url", help="Base URL such as http://127.0.0.1:8451")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    dashboard = load_dashboard(path=args.path, url=args.url, timeout=args.timeout)
    issues = validate_dashboard(dashboard)
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
