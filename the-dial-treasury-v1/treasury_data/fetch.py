"""Data-fetch + source-freshness layer extracted from build_dashboard.py
(behavior-unchanged, 2026-06-19 全面重构 Phase 1). Network/source plumbing; depends only
on stdlib + sources types. Re-exported by build_dashboard via `from .fetch import *`."""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .sources import (
    FRED_MONTHLY_PERIOD_SERIES_IDS,
    FRED_QUARTERLY_PERIOD_SERIES_IDS,
    MarketDailyBar,
    TENORS,
    TimeSeries,
    YieldCurveRecord,
)


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
    "U.S. Treasury yield curve XML": 7,
    "NY Fed ACM term premium": 45,
    "CFTC financial futures COT": 10,
    "Treasury TIC major foreign holders": 75,
    "NY Fed primary dealer statistics": 21,
    "Federal Reserve SEP projections": 120,
    "U.S. Treasury quarterly refunding documents": 120,
    "Treasury Fiscal Data debt subject to limit": 10,
    "Stooq 30-Day Fed Funds futures ZQ.F": 5,
    "Stooq gold spot XAUUSD": 5,
    "Cboe SPY option open interest": 7,
}

# Source-status freshness must use the same broad cadence contract as the
# scoring layer.  Previously only the non-FRED feeds above had an expected
# age, so an old FRED row stayed ``ok`` even after the corresponding Bhadial
# factor had correctly failed closed as stale.  Explicit groups keep the
# slower economic reference periods separate from business-daily markets.
FRED_BUSINESS_DAILY_SERIES_IDS = {
    "DFII5",
    "DFII10",
    "T10YIE",
    "DFF",
    "SOFR",
    "OBFR",
    "IORB",
    "RRPONTSYAWARD",
    "RPONTSYD",
    "RRPONTSYD",
    "SP500",
    "VIXCLS",
    "VXVCLS",
    "DTWEXBGS",
    "DCPF3M",
    "DTB3",
    "BAMLH0A0HYM2",
    "BAMLC0A0CM",
    "DCOILWTICO",
    "DHHNGSP",
    "OVXCLS",
    "GVZCLS",
    "DGS10",
    "NASDAQXNDX",
    "NASDAQNQUS500LCT",
    "NASDAQBANK",
    "BAMLHYH0A0HYM2TRIV",
    "BAMLCC0A0CMTRIV",
}
FRED_WEEKLY_SERIES_IDS = {
    "WTREGEN",
    "WALCL",
    "TREAST",
    "WRESBAL",
    "NFCI",
}
FRED_MONTHLY_SERIES_IDS = {
    "CPIAUCSL",
    "PCEPI",
    "PCEPILFE",
    "PCETRIM12M159SFRBDAL",
    "PPIACO",
    "UNRATE",
    "PAYEMS",
    "IRLTLT01JPM156N",
    "IRLTLT01DEM156N",
    "IRLTLT01GBM156N",
}
FRED_QUARTERLY_SERIES_IDS = {"GDPC1"}

for _series_id in FRED_BUSINESS_DAILY_SERIES_IDS:
    EXPECTED_SOURCE_CADENCE_DAYS[f"FRED {_series_id}"] = 7
for _series_id in FRED_WEEKLY_SERIES_IDS:
    EXPECTED_SOURCE_CADENCE_DAYS[f"FRED {_series_id}"] = 14
for _series_id in FRED_MONTHLY_SERIES_IDS:
    # Monthly FRED dates represent the first day of the economic period.  The
    # period-end normalization below means 65 days safely spans the normal
    # next-month release cycle without tolerating an entire missed release.
    EXPECTED_SOURCE_CADENCE_DAYS[f"FRED {_series_id}"] = 65
for _series_id in FRED_QUARTERLY_SERIES_IDS:
    # Likewise, 130 days from quarter end spans the advance-release calendar
    # but marks a series stale once the following quarter's release is missed.
    EXPECTED_SOURCE_CADENCE_DAYS[f"FRED {_series_id}"] = 130

# FRED encodes monthly and quarterly observations at the first day of the
# reference period.  That is useful as a series key, but it is the wrong date
# for freshness: May PCE is not already one month old on May 31, and Q1 GDP is
# not already three months old on March 31.  Keep the raw observation date for
# traceability and derive a period-end date only for freshness reporting.
MONTHLY_PERIOD_SOURCE_NAMES = {f"FRED {series_id}" for series_id in FRED_MONTHLY_PERIOD_SERIES_IDS}
QUARTERLY_PERIOD_SOURCE_NAMES = {f"FRED {series_id}" for series_id in FRED_QUARTERLY_PERIOD_SERIES_IDS}
FORWARD_CALENDAR_SOURCE_NAMES = {
    "Federal Reserve FOMC calendar",
    "FRED economic release calendar",
    "BEA release schedule",
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
    full_date = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if full_date:
        try:
            return date(int(full_date.group(1)), int(full_date.group(2)), int(full_date.group(3)))
        except ValueError:
            return None
    match = re.search(r"\b(\d{4})-(\d{2})\b", text)
    if match:
        try:
            year = int(match.group(1))
            month = int(match.group(2))
            return date(year, month, monthrange(year, month)[1])
        except ValueError:
            return None
    return None


def source_observation_period_end(name: str, observed_at: date) -> date:
    """Return the economic reference-period end used for freshness only."""
    if name in MONTHLY_PERIOD_SOURCE_NAMES and observed_at.day == 1:
        return observed_at.replace(day=monthrange(observed_at.year, observed_at.month)[1])
    if name in QUARTERLY_PERIOD_SOURCE_NAMES and observed_at.day == 1:
        end_month = observed_at.month + 2
        end_year = observed_at.year + (end_month - 1) // 12
        end_month = (end_month - 1) % 12 + 1
        return date(end_year, end_month, monthrange(end_year, end_month)[1])
    return observed_at


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
            if name in FORWARD_CALENDAR_SOURCE_NAMES:
                coverage_active = latest_date >= target
                prior_note = str(item.get("note") or "")
                if (
                    item.get("status") == "error"
                    and "Source date/period ends after dashboard as-of" in prior_note
                ):
                    # Repair rows serialized by the former generic future-date
                    # rule without masking a genuine calendar fetch error.
                    item["status"] = "ok"
                    item.pop("note", None)
                item["observationDate"] = latest_date.isoformat()
                item["observationPeriodEnd"] = latest_date.isoformat()
                item["coverageThrough"] = latest_date.isoformat()
                item["freshnessBasis"] = "calendar-horizon"
                item["periodComplete"] = True
                item["calendarCoverageActive"] = coverage_active
                item["releaseDateKnown"] = True
                item["ageDays"] = max(0, (target - latest_date).days)
                if not coverage_active and item.get("status") == "ok":
                    item["status"] = "stale"
                    item["note"] = (
                        f"Calendar coverage ended {item['ageDays']} days before dashboard as-of; "
                        "refresh the planned-event horizon."
                    )
                annotated.append(item)
                continue
            period_end = source_observation_period_end(name, latest_date)
            item["observationDate"] = latest_date.isoformat()
            item["observationPeriodEnd"] = period_end.isoformat()
            item["freshnessBasis"] = "observation-period-end" if period_end != latest_date else "observation-date"
            item["periodComplete"] = period_end <= target and latest_date <= target
            item["releaseDateKnown"] = False
            # Weekday markets are only fresh on trading days, so a Friday close is NOT stale on
            # a Monday — measure trading-day age for daily OHLCV, calendar age otherwise.
            if not item["periodComplete"]:
                item["ageDays"] = 0
                item["futureDays"] = max(0, (max(period_end, latest_date) - target).days)
                item["status"] = "error"
                item["note"] = (
                    f"Source date/period ends after dashboard as-of by {item['futureDays']} days; "
                    "row is not eligible for scoring."
                )
            elif is_market_daily_source(name):
                item["ageDays"] = business_days_between(period_end, target)
            else:
                item["ageDays"] = max(0, (target - period_end).days)
        if (
            cadence is not None
            and latest_date is not None
            and item.get("periodComplete") is True
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
