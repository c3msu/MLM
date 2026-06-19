"""Data-fetch + source-freshness layer extracted from build_dashboard.py
(behavior-unchanged, 2026-06-19 全面重构 Phase 1). Network/source plumbing; depends only
on stdlib + sources types. Re-exported by build_dashboard via `from .fetch import *`."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .sources import MarketDailyBar, TENORS, TimeSeries, YieldCurveRecord


FRED_TREASURY_CURVE_SERIES: dict[str, str] = {
    "1M": "DGS1MO",
    "3M": "DGS3MO",
    "6M": "DGS6MO",
    "1Y": "DGS1",
    "2Y": "DGS2",
    "3Y": "DGS3",
    "5Y": "DGS5",
    "7Y": "DGS7",
    "10Y": "DGS10",
    "20Y": "DGS20",
    "30Y": "DGS30",
}
EXPECTED_SOURCE_CADENCE_DAYS: dict[str, int] = {
    "NY Fed ACM term premium": 45,
    "CFTC financial futures COT": 10,
    "Treasury TIC major foreign holders": 75,
    "NY Fed primary dealer statistics": 21,
    "Federal Reserve SEP projections": 120,
    "U.S. Treasury quarterly refunding documents": 120,
    "Treasury Fiscal Data debt subject to limit": 10,
    "Stooq 30-Day Fed Funds futures ZQ.F": 5,
    "Stooq gold spot XAUUSD": 5,
}
DailyBarFetcher = Callable[..., list[MarketDailyBar]]


def stooq_fallback_symbol(symbol: str, fallback_symbol: str | None = None) -> str:
    if fallback_symbol:
        return fallback_symbol
    return f"{symbol.strip().lower()}.us"


def remap_market_bars_symbol(bars: list[MarketDailyBar], symbol: str) -> list[MarketDailyBar]:
    output_symbol = symbol.upper()
    return [
        MarketDailyBar(
            symbol=output_symbol,
            date=bar.date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            source=bar.source,
        )
        for bar in bars
    ]


def build_fred_dgs_curve_records(fred: dict[str, TimeSeries]) -> list[YieldCurveRecord]:
    points_by_tenor: dict[str, dict[date, float]] = {}
    for tenor, series_id in FRED_TREASURY_CURVE_SERIES.items():
        series = fred.get(series_id)
        if not series:
            continue
        points_by_tenor[tenor] = {point.date: point.value for point in series.points}
    if set(points_by_tenor) != set(TENORS):
        return []
    common_dates = set.intersection(*(set(values) for values in points_by_tenor.values()))
    records = [
        YieldCurveRecord(date=record_date, values={tenor: points_by_tenor[tenor][record_date] for tenor in TENORS})
        for record_date in sorted(common_dates)
    ]
    return records


def parse_source_latest_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    match = re.search(r"\b(\d{4})-(\d{2})\b", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), 1)
        except ValueError:
            return None
    return None


def annotate_source_status_freshness(
    rows: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    target = as_of or datetime.now(timezone.utc).date()
    annotated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        name = str(item.get("name") or "")
        cadence = expected_source_cadence_days(name)
        latest_date = parse_source_latest_date(item.get("latest"))
        if cadence is not None:
            item["expectedMaxAgeDays"] = cadence
        if latest_date is not None:
            # Weekday markets are only fresh on trading days, so a Friday close is NOT stale on
            # a Monday — measure trading-day age for daily OHLCV, calendar age otherwise.
            if is_market_daily_source(name):
                item["ageDays"] = business_days_between(latest_date, target)
            else:
                item["ageDays"] = max(0, (target - latest_date).days)
        if (
            cadence is not None
            and latest_date is not None
            and item.get("status") == "ok"
            and item["ageDays"] > cadence
        ):
            item["status"] = "stale"
            unit = "trading days" if is_market_daily_source(name) else "days"
            item["note"] = f"Latest observation is {item['ageDays']} {unit} old; expected <= {cadence}."
        annotated.append(item)
    return annotated


def business_days_between(latest: date, target: date) -> int:
    """Count weekdays strictly after `latest` up to and including `target` (Mon-Fri)."""
    if target <= latest:
        return 0
    count = 0
    cursor = latest + timedelta(days=1)
    while cursor <= target:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def is_market_daily_source(name: str) -> bool:
    return (name.startswith("Nasdaq ") and name.endswith(" OHLCV")) or (
        name.startswith("Global LPPL ") and name.endswith(" OHLCV")
    )


def expected_source_cadence_days(name: str) -> int | None:
    configured = EXPECTED_SOURCE_CADENCE_DAYS.get(name)
    if configured is not None:
        return configured
    if is_market_daily_source(name):
        return 2
    return None
