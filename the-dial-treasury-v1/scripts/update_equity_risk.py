from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.update_data import (  # noqa: E402
    DEFAULT_OUTPUT,
    dashboard_block_is_usable,
    dashboard_update_file_lock,
    snapshot_regression_issues,
    write_failed_dashboard_json,
    write_dashboard_json,
)
from treasury_data.build_dashboard import (  # noqa: E402
    EQUITY_RISK_SYMBOLS,
    GLOBAL_LPPL_INDEX_SPECS,
    annotate_spy_warning_robustness,
    annotate_source_status_freshness,
    build_equity_short_term_risk_index,
    build_equity_signal_validation_row,
    build_global_lppl_risk_index,
    build_portfolio_overview,
    build_regional_monitor,
    compact_dashboard_payload,
    fetch_daily_bars_with_stooq_fallback,
)
from treasury_data.history_store import history_db_for_output, save_dashboard_history  # noqa: E402
from treasury_data.dashboard_contract import require_dashboard_contract, stamp_dashboard_contract  # noqa: E402
from treasury_data.signal_validation import DEFAULT_FDR_ALPHA, apply_benjamini_hochberg  # noqa: E402
from treasury_data.sources import CalendarEvent, MarketDailyBar, fetch_nasdaq_daily_bars, fetch_stooq_daily_bars  # noqa: E402
from treasury_data.validation_build import EQUITY_SHORT_TERM_VALIDATION_EXCLUSION  # noqa: E402

DailyBarFetcher = Callable[..., list[MarketDailyBar]]
MARKET_CACHE_VERSION = 1
DEFAULT_MARKET_CACHE_OVERLAP_DAYS = 10
MAX_EQUITY_SYMBOL_LAG_TRADING_DAYS = 2


def read_dashboard_json(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    with output.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{output} must contain a dashboard object")
    return payload


def dashboard_events_to_calendar_events(dashboard: dict[str, Any]) -> list[CalendarEvent]:
    events = dashboard.get("events")
    if not isinstance(events, list):
        return []
    parsed: list[CalendarEvent] = []
    for row in events:
        if not isinstance(row, list) or len(row) < 2:
            continue
        try:
            event_date = date.fromisoformat(str(row[0]))
        except ValueError:
            continue
        title = str(row[1] or "").strip()
        if not title:
            continue
        importance = str(row[2] or "中").strip() if len(row) >= 3 else "中"
        parsed.append(CalendarEvent(date=event_date, title=title, source="dashboard events", importance=importance))
    return parsed


def build_source_status_rows(market_bars: dict[str, list[MarketDailyBar]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in EQUITY_RISK_SYMBOLS:
        bars = market_bars.get(symbol, [])
        if bars:
            rows.append({"name": f"Nasdaq {symbol} OHLCV", "status": "ok", "latest": bars[-1].date.isoformat()})
        else:
            rows.append({"name": f"Nasdaq {symbol} OHLCV", "status": "warning", "latest": "equity-only refresh unavailable"})
    for spec in GLOBAL_LPPL_INDEX_SPECS:
        symbol = str(spec["symbol"]).upper()
        bars = market_bars.get(symbol, [])
        if bars:
            rows.append({"name": f"Global LPPL {symbol} OHLCV", "status": "ok", "latest": bars[-1].date.isoformat()})
        else:
            rows.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": "global LPPL refresh unavailable"})
    return rows


def merge_source_status(existing: Any, equity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_rows = [row for row in existing if isinstance(row, dict)] if isinstance(existing, list) else []
    equity_names = {row["name"] for row in equity_rows}
    retained = [row for row in existing_rows if row.get("name") not in equity_names]
    return retained + equity_rows


def _source_row_latest_date(row: dict[str, Any] | None) -> date | None:
    if not isinstance(row, dict):
        return None
    try:
        return date.fromisoformat(str(row.get("latest") or ""))
    except ValueError:
        return None


def assess_equity_refresh_alignment(
    market_bars: dict[str, list[MarketDailyBar]],
    source_status_rows: list[dict[str, Any]] | None = None,
    *,
    max_lag_trading_days: int = MAX_EQUITY_SYMBOL_LAG_TRADING_DAYS,
) -> dict[str, Any]:
    """Detect equity inputs that cannot safely participate in one score refresh.

    Relative age is measured on SPY's observed trading calendar, so exchange
    holidays do not create false lag. A stale-cache row blocks scoring even if
    its cached date equals SPY: the inputs were not atomically observed.
    """
    rows_by_name = {
        str(row.get("name") or ""): row
        for row in source_status_rows or []
        if isinstance(row, dict)
    }
    spy_dates = sorted(
        {
            bar_date
            for bar in market_bars.get("SPY", [])
            if isinstance((bar_date := getattr(bar, "date", None)), date)
        }
    )
    spy_latest = spy_dates[-1] if spy_dates else None
    missing_symbols: list[str] = []
    stale_cache_symbols: list[str] = []
    lagged_symbols: list[str] = []
    symbol_ages: dict[str, dict[str, Any]] = {}

    for symbol in EQUITY_RISK_SYMBOLS:
        bars = market_bars.get(symbol, [])
        row = rows_by_name.get(f"Nasdaq {symbol} OHLCV")
        if not bars:
            missing_symbols.append(symbol)
        latest = max(
            (
                bar_date
                for bar in bars
                if isinstance((bar_date := getattr(bar, "date", None)), date)
            ),
            default=None,
        ) or _source_row_latest_date(row)
        lag_trading_days = (
            sum(1 for spy_date in spy_dates if spy_date > latest)
            if spy_latest is not None and latest is not None
            else None
        )
        status = str((row or {}).get("status") or "").lower()
        cache_mode = str((row or {}).get("cacheMode") or "").lower()
        uses_stale_cache = status == "stale-cache" or cache_mode == "last-known-good"
        trails_spy = lag_trading_days is not None and lag_trading_days > max_lag_trading_days
        if uses_stale_cache:
            stale_cache_symbols.append(symbol)
        if trails_spy:
            lagged_symbols.append(symbol)
        is_missing = not bars
        if not is_missing and not uses_stale_cache and not trails_spy:
            continue
        reasons: list[str] = []
        if is_missing:
            reasons.append("missing")
        if uses_stale_cache:
            reasons.append("stale-cache")
        if trails_spy:
            reasons.append("lagged-vs-spy")
        symbol_ages[symbol] = {
            "latest": latest.isoformat() if latest is not None else None,
            "spyLatest": spy_latest.isoformat() if spy_latest is not None else None,
            "lagTradingDays": lag_trading_days,
            "staleCache": uses_stale_cache,
            "reasons": reasons,
        }

    stale_symbols = sorted(set(stale_cache_symbols) | set(lagged_symbols))
    blocked_symbols = sorted(set(missing_symbols) | set(stale_symbols))
    return {
        "blocked": bool(blocked_symbols),
        "maxLagTradingDays": max_lag_trading_days,
        "spyLatest": spy_latest.isoformat() if spy_latest is not None else None,
        "missingSymbols": sorted(missing_symbols),
        "staleCacheSymbols": sorted(stale_cache_symbols),
        "laggedSymbols": sorted(lagged_symbols),
        "staleSymbols": stale_symbols,
        "blockedSymbols": blocked_symbols,
        "symbolAges": {symbol: symbol_ages[symbol] for symbol in blocked_symbols},
    }


def annotate_equity_alignment_source_status(
    rows: list[dict[str, Any]],
    alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expose the exact inputs that caused the atomic equity refresh guard."""
    details = alignment.get("symbolAges") if isinstance(alignment.get("symbolAges"), dict) else {}
    if not alignment.get("blocked") or not details:
        return [dict(row) for row in rows]
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        item = dict(row)
        name = str(item.get("name") or "")
        symbol = next(
            (candidate for candidate in details if name == f"Nasdaq {candidate} OHLCV"),
            None,
        )
        if symbol is not None:
            seen.add(symbol)
            detail = details[symbol]
            item["equityRefreshBlocked"] = True
            item["stale"] = True
            item["lagTradingDays"] = detail.get("lagTradingDays")
            item["spyLatest"] = detail.get("spyLatest")
            if "missing" in detail.get("reasons", []):
                item["status"] = "missing"
            elif str(item.get("status") or "").lower() != "stale-cache":
                item["status"] = "stale"
            reason_text = ", ".join(str(value) for value in detail.get("reasons", []))
            lag = detail.get("lagTradingDays")
            lag_text = f"relative SPY lag is {lag} trading days" if lag is not None else "relative SPY lag is unavailable"
            alignment_note = f"Equity factor refresh blocked ({reason_text}); {lag_text}."
            prior_note = str(item.get("note") or "").strip()
            if alignment_note not in prior_note:
                item["note"] = f"{prior_note}; {alignment_note}" if prior_note else alignment_note
        output.append(item)
    for symbol in sorted(set(details) - seen):
        detail = details[symbol]
        output.append(
            {
                "name": f"Nasdaq {symbol} OHLCV",
                "status": (
                    "missing"
                    if "missing" in detail.get("reasons", [])
                    else "stale-cache"
                    if detail.get("staleCache")
                    else "stale"
                ),
                "latest": detail.get("latest") or "unavailable",
                "equityRefreshBlocked": True,
                "stale": True,
                "lagTradingDays": detail.get("lagTradingDays"),
                "spyLatest": detail.get("spyLatest"),
                "note": "Equity factor refresh blocked because this required input is not aligned with SPY.",
            }
        )
    return output


def record_equity_alignment_meta(refresh_meta: dict[str, Any], alignment: dict[str, Any]) -> None:
    if not alignment.get("blocked"):
        return
    refresh_meta.update(
        {
            "equityAlignmentBlocked": True,
            "maxEquitySymbolLagTradingDays": alignment.get("maxLagTradingDays"),
            "spyLatest": alignment.get("spyLatest"),
            "blockedEquitySymbols": alignment.get("blockedSymbols", []),
            "missingEquitySymbols": alignment.get("missingSymbols", []),
            "staleEquitySymbols": alignment.get("staleSymbols", []),
            "staleCacheEquitySymbols": alignment.get("staleCacheSymbols", []),
            "laggedEquitySymbols": alignment.get("laggedSymbols", []),
            "staleEquitySymbolAges": alignment.get("symbolAges", {}),
        }
    )


def build_updated_dashboard(
    dashboard: dict[str, Any],
    market_bars: dict[str, list[MarketDailyBar]],
    *,
    generated_at: datetime | None = None,
    source_status_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    updated = copy.deepcopy(dashboard)
    generated_at_value = generated_at or datetime.now(timezone.utc)
    effective_source_rows = source_status_rows if source_status_rows is not None else build_source_status_rows(market_bars)
    equity_alignment = assess_equity_refresh_alignment(market_bars, effective_source_rows)
    previous_equity = dashboard.get("equityShortTermRisk")
    if equity_alignment["blocked"]:
        if dashboard_block_is_usable(previous_equity):
            risk = copy.deepcopy(previous_equity)
        else:
            risk = {
                "available": False,
                "score": None,
                "asOf": equity_alignment.get("spyLatest"),
                "summary": "Equity factor refresh blocked because required market inputs are not time-aligned.",
            }
    else:
        risk = build_equity_short_term_risk_index(
            market_bars=market_bars,
            macro_liquidity_equity=dashboard.get("macroLiquidityEquity") if isinstance(dashboard.get("macroLiquidityEquity"), dict) else {},
            spy_early_warning=dashboard.get("spyEarlyWarning") if isinstance(dashboard.get("spyEarlyWarning"), dict) else {},
            calendar_events=dashboard_events_to_calendar_events(dashboard),
        )
    global_lppl_risk = build_global_lppl_risk_index(market_bars=market_bars)
    regional_monitor = build_regional_monitor(global_lppl_risk)
    signal_validation = refresh_equity_validation(
        dashboard.get("signalValidation"),
        risk,
    )
    annotate_spy_warning_robustness(updated.get("spyEarlyWarning"), signal_validation)
    portfolio_overview = build_portfolio_overview(
        spy_early_warning=updated.get("spyEarlyWarning") if isinstance(updated.get("spyEarlyWarning"), dict) else {},
        equity_short_term_risk=risk,
        global_lppl_risk=global_lppl_risk,
        macro_liquidity=dashboard.get("macroLiquidity") if isinstance(dashboard.get("macroLiquidity"), dict) else {},
        signal_validation=signal_validation,
        regional_monitor=regional_monitor,
    )
    updated["equityShortTermRisk"] = risk
    updated["globalLpplRisk"] = global_lppl_risk
    updated["regionalMonitor"] = regional_monitor
    updated["signalValidation"] = signal_validation
    updated["portfolioOverview"] = portfolio_overview
    updated["generatedAt"] = generated_at_value.isoformat()
    updated["sourceStatus"] = annotate_source_status_freshness(
        merge_source_status(
            dashboard.get("sourceStatus", []),
            effective_source_rows,
        ),
        as_of=generated_at_value.date(),
    )
    updated["sourceStatus"] = annotate_equity_alignment_source_status(updated["sourceStatus"], equity_alignment)
    stamp_dashboard_contract(updated)
    updated.setdefault("meta", {})["equityRefresh"] = {
        "mode": "recomputed",
        "scoringSkipped": bool(equity_alignment["blocked"]),
        "latestBars": market_bar_latest_dates(market_bars),
    }
    record_equity_alignment_meta(updated["meta"]["equityRefresh"], equity_alignment)
    preserve_partial_refresh_last_known_good(
        updated,
        dashboard,
        market_bars=market_bars,
        equity_alignment=equity_alignment,
    )
    return compact_dashboard_payload(updated)


def available_global_lppl_symbols(value: Any) -> set[str]:
    if not isinstance(value, dict) or not isinstance(value.get("indices"), list):
        return set()
    return {
        str(row.get("symbol") or "").upper()
        for row in value["indices"]
        if isinstance(row, dict) and row.get("available") is True and row.get("symbol")
    }


def _optional_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def dashboard_block_date_regressed(candidate: Any, previous: Any) -> bool:
    """Return true when a usable replacement loses or rewinds its as-of date."""

    if not isinstance(previous, dict):
        return False
    previous_date = _optional_iso_date(previous.get("asOf"))
    if previous_date is None:
        return False
    if not isinstance(candidate, dict):
        return True
    candidate_date = _optional_iso_date(candidate.get("asOf"))
    return candidate_date is None or candidate_date < previous_date


def global_lppl_dates_regressed(candidate: Any, previous: Any) -> bool:
    if not isinstance(previous, dict):
        return False
    previous_rows = previous.get("indices") if isinstance(previous.get("indices"), list) else []
    candidate_rows = candidate.get("indices") if isinstance(candidate, dict) and isinstance(candidate.get("indices"), list) else []
    candidate_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in candidate_rows
        if isinstance(row, dict) and row.get("symbol")
    }
    for previous_row in previous_rows:
        if not isinstance(previous_row, dict) or previous_row.get("available") is not True:
            continue
        symbol = str(previous_row.get("symbol") or "").upper()
        previous_date = _optional_iso_date(previous_row.get("asOf"))
        if not symbol or previous_date is None:
            continue
        candidate_row = candidate_by_symbol.get(symbol)
        candidate_date = _optional_iso_date(candidate_row.get("asOf")) if isinstance(candidate_row, dict) else None
        if candidate_date is None or candidate_date < previous_date:
            return True
    return False


def rebuild_partial_refresh_dependents(updated: dict[str, Any]) -> None:
    """Rebuild every surface derived from the two partial-refresh roots."""
    risk = updated.get("equityShortTermRisk") if isinstance(updated.get("equityShortTermRisk"), dict) else {}
    global_lppl_risk = updated.get("globalLpplRisk") if isinstance(updated.get("globalLpplRisk"), dict) else {}
    regional_monitor = build_regional_monitor(global_lppl_risk)
    signal_validation = refresh_equity_validation(updated.get("signalValidation"), risk)
    annotate_spy_warning_robustness(updated.get("spyEarlyWarning"), signal_validation)
    updated["regionalMonitor"] = regional_monitor
    updated["signalValidation"] = signal_validation
    updated["portfolioOverview"] = build_portfolio_overview(
        spy_early_warning=updated.get("spyEarlyWarning") if isinstance(updated.get("spyEarlyWarning"), dict) else {},
        equity_short_term_risk=risk,
        global_lppl_risk=global_lppl_risk,
        macro_liquidity=updated.get("macroLiquidity") if isinstance(updated.get("macroLiquidity"), dict) else {},
        signal_validation=signal_validation,
        regional_monitor=regional_monitor,
    )


def preserve_partial_refresh_last_known_good(
    updated: dict[str, Any],
    previous: dict[str, Any],
    *,
    market_bars: dict[str, list[MarketDailyBar]] | None = None,
    equity_alignment: dict[str, Any] | None = None,
) -> list[str]:
    """Do not replace healthy served risk blocks with a degraded partial build.

    Global LPPL is treated atomically.  A partial symbol set would otherwise
    silently remove one region and invalidate regional/portfolio derivatives.
    """
    borrowed: list[str] = []
    candidate_equity = updated.get("equityShortTermRisk")
    previous_equity = previous.get("equityShortTermRisk")
    missing_equity_symbols = sorted(
        symbol
        for symbol in EQUITY_RISK_SYMBOLS
        if market_bars is not None and not market_bars.get(symbol)
    )
    alignment = equity_alignment or assess_equity_refresh_alignment(
        market_bars or {},
        updated.get("sourceStatus") if isinstance(updated.get("sourceStatus"), list) else [],
    )
    equity_regressed = (
        bool(missing_equity_symbols)
        or bool(alignment.get("blocked"))
        or dashboard_block_date_regressed(candidate_equity, previous_equity)
    )
    if (
        (not dashboard_block_is_usable(candidate_equity) or equity_regressed)
        and dashboard_block_is_usable(previous_equity)
    ):
        updated["equityShortTermRisk"] = copy.deepcopy(previous_equity)
        borrowed.append("equityShortTermRisk")

    candidate_global = updated.get("globalLpplRisk")
    previous_global = previous.get("globalLpplRisk")
    previous_symbols = available_global_lppl_symbols(previous_global)
    candidate_symbols = available_global_lppl_symbols(candidate_global)
    global_regressed = bool(previous_symbols - candidate_symbols) or global_lppl_dates_regressed(
        candidate_global,
        previous_global,
    )
    if (
        (not dashboard_block_is_usable(candidate_global) or global_regressed)
        and dashboard_block_is_usable(previous_global)
    ):
        updated["globalLpplRisk"] = copy.deepcopy(previous_global)
        borrowed.append("globalLpplRisk")

    refresh_meta = updated.setdefault("meta", {}).setdefault("equityRefresh", {})
    if alignment.get("blocked"):
        refresh_meta["scoringSkipped"] = True
        record_equity_alignment_meta(refresh_meta, alignment)
        if isinstance(updated.get("sourceStatus"), list):
            updated["sourceStatus"] = annotate_equity_alignment_source_status(updated["sourceStatus"], alignment)

    if borrowed:
        rebuild_partial_refresh_dependents(updated)
        refresh_meta.update(
            {
                "mode": "partial-lkg",
                "lastKnownGoodBlocks": borrowed,
                "failedBlocks": borrowed,
            }
        )
    if missing_equity_symbols:
        refresh_meta["missingEquitySymbols"] = missing_equity_symbols
    return borrowed


def build_failed_fetch_dashboard(
    dashboard: dict[str, Any],
    source_rows: list[dict[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Publish failure visibility while retaining the last healthy calculations."""
    updated = copy.deepcopy(dashboard)
    generated_at_value = generated_at or datetime.now(timezone.utc)
    updated["generatedAt"] = generated_at_value.isoformat()
    updated["sourceStatus"] = annotate_source_status_freshness(
        merge_source_status(updated.get("sourceStatus", []), source_rows),
        as_of=generated_at_value.date(),
    )
    stamp_dashboard_contract(updated)
    updated.setdefault("meta", {})["equityRefresh"] = {
        "mode": "last-known-good",
        "scoringSkipped": True,
        "latestBars": {},
        "lastKnownGoodBlocks": ["equityShortTermRisk", "globalLpplRisk"],
        "failedBlocks": ["equityShortTermRisk", "globalLpplRisk"],
    }
    return updated


def refresh_equity_validation(existing: Any, equity_risk: dict[str, Any]) -> dict[str, Any]:
    """Keep the 91-day validation family intact during an equity-only refresh.

    ``equityShortTermRisk`` has a dedicated 15-trading-day walk-forward
    backtest.  It must never be inserted into the generic 91-calendar-day
    composite/BH family merely because its daily block was refreshed.
    """
    payload = copy.deepcopy(existing) if isinstance(existing, dict) else {
        "available": False,
        "factors": [],
        "composites": [],
    }
    composites = payload.get("composites") if isinstance(payload.get("composites"), list) else []
    retained = [
        row for row in composites
        if not isinstance(row, dict) or str(row.get("id") or "") != "equityShortTermRisk"
    ]
    equity_row = build_equity_signal_validation_row(equity_risk)
    multiple_testing = payload.get("multipleTesting")
    registered_family_size = len(retained)
    if isinstance(multiple_testing, dict) and isinstance(multiple_testing.get("families"), list):
        for family in multiple_testing["families"]:
            if not isinstance(family, dict) or family.get("name") != "composites":
                continue
            declared_size = family.get("size", family.get("familySize"))
            if isinstance(declared_size, int) and declared_size >= len(retained):
                registered_family_size = declared_size
            break
    # Unavailable pre-registered lenses remain in the denominator as p=1.
    # The padding rows are calculation-only and never enter the payload.
    bh_family = retained + [
        {
            "id": f"__unavailable_preregistered_composite_{index}",
            "pValue3m": None,
            "robust": False,
            "foldStability3m": {"stablePositive": False},
        }
        for index in range(registered_family_size - len(retained))
    ]
    apply_benjamini_hochberg(bh_family, alpha=DEFAULT_FDR_ALPHA)
    payload["composites"] = retained
    exclusions = payload.get("excludedModels") if isinstance(payload.get("excludedModels"), list) else []
    payload["excludedModels"] = [
        copy.deepcopy(row)
        for row in exclusions
        if not isinstance(row, dict) or str(row.get("id") or "") != "equityShortTermRisk"
    ] + [dict(EQUITY_SHORT_TERM_VALIDATION_EXCLUSION)]
    if isinstance(multiple_testing, dict) and isinstance(multiple_testing.get("families"), list):
        for family in multiple_testing["families"]:
            if isinstance(family, dict) and family.get("name") == "composites":
                if "size" in family or "familySize" not in family:
                    family["size"] = registered_family_size
                if "familySize" in family:
                    family["familySize"] = registered_family_size
    payload["partialRefresh"] = {
        "equityCompositeUpdated": False,
        "equityDedicatedBacktestUpdated": equity_row is not None,
        "equityExcludedFromGenericFamily": True,
        "macroFactorsReused": True,
    }
    return payload


def market_cache_path_for_output(output: Path) -> Path:
    return output.parent / "cache" / "market-bars-v1.json"


def market_bar_to_payload(bar: MarketDailyBar) -> dict[str, Any]:
    return {
        "date": bar.date.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "source": bar.source,
    }


def market_bar_from_payload(symbol: str, row: Any) -> MarketDailyBar | None:
    if not isinstance(row, dict):
        return None
    try:
        return MarketDailyBar(
            symbol=symbol.upper(),
            date=date.fromisoformat(str(row["date"])),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]) if row.get("volume") is not None else None,
            source=str(row.get("source") or "market-cache"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def load_market_bar_cache(path: Path) -> dict[str, list[MarketDailyBar]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("version") != MARKET_CACHE_VERSION:
        return {}
    raw_bars = payload.get("bars")
    if not isinstance(raw_bars, dict):
        return {}
    output: dict[str, list[MarketDailyBar]] = {}
    for raw_symbol, rows in raw_bars.items():
        if not isinstance(rows, list):
            continue
        symbol = str(raw_symbol).upper()
        parsed = [bar for row in rows if (bar := market_bar_from_payload(symbol, row)) is not None]
        if parsed:
            output[symbol] = merge_market_bars([], parsed)
    return output


def save_market_bar_cache(market_bars: dict[str, list[MarketDailyBar]], path: Path) -> None:
    payload = {
        "version": MARKET_CACHE_VERSION,
        "bars": {
            symbol: [market_bar_to_payload(bar) for bar in sorted(bars, key=lambda item: item.date)]
            for symbol, bars in sorted(market_bars.items())
            if bars
        },
    }
    write_dashboard_json(payload, path)


def merge_market_bars(
    cached: list[MarketDailyBar],
    fetched: list[MarketDailyBar],
    *,
    start: date | None = None,
) -> list[MarketDailyBar]:
    by_date = {bar.date: bar for bar in cached}
    by_date.update({bar.date: bar for bar in fetched})
    return [by_date[bar_date] for bar_date in sorted(by_date) if start is None or bar_date >= start]


def incremental_market_start(
    cached: list[MarketDailyBar],
    full_start: date,
    *,
    overlap_days: int = DEFAULT_MARKET_CACHE_OVERLAP_DAYS,
) -> date:
    if not cached:
        return full_start
    return max(full_start, cached[-1].date - timedelta(days=max(1, overlap_days)))


def market_bar_latest_dates(market_bars: dict[str, list[MarketDailyBar]]) -> dict[str, str]:
    return {
        symbol: bars[-1].date.isoformat()
        for symbol, bars in sorted(market_bars.items())
        if bars
    }


def dashboard_covers_market_bars(dashboard: dict[str, Any], market_bars: dict[str, list[MarketDailyBar]]) -> bool:
    spy_bars = market_bars.get("SPY", [])
    risk = dashboard.get("equityShortTermRisk") if isinstance(dashboard.get("equityShortTermRisk"), dict) else {}
    if not spy_bars or str(risk.get("asOf") or "") < spy_bars[-1].date.isoformat():
        return False
    global_risk = dashboard.get("globalLpplRisk") if isinstance(dashboard.get("globalLpplRisk"), dict) else {}
    indices = global_risk.get("indices") if isinstance(global_risk.get("indices"), list) else []
    by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in indices
        if isinstance(row, dict)
    }
    for spec in GLOBAL_LPPL_INDEX_SPECS:
        symbol = str(spec["symbol"]).upper()
        bars = market_bars.get(symbol, [])
        if not bars:
            continue
        row = by_symbol.get(symbol)
        if not row or str(row.get("asOf") or "") < bars[-1].date.isoformat():
            return False
    return True


def build_cache_hit_dashboard(
    dashboard: dict[str, Any],
    market_bars: dict[str, list[MarketDailyBar]],
    source_rows: list[dict[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    updated = copy.deepcopy(dashboard)
    generated_at_value = generated_at or datetime.now(timezone.utc)
    equity_alignment = assess_equity_refresh_alignment(market_bars, source_rows)
    updated["generatedAt"] = generated_at_value.isoformat()
    updated["sourceStatus"] = annotate_source_status_freshness(
        merge_source_status(updated.get("sourceStatus", []), source_rows),
        as_of=generated_at_value.date(),
    )
    updated["sourceStatus"] = annotate_equity_alignment_source_status(updated["sourceStatus"], equity_alignment)
    stamp_dashboard_contract(updated)
    updated.setdefault("meta", {})["equityRefresh"] = {
        "mode": "cache-hit",
        "scoringSkipped": True,
        "latestBars": market_bar_latest_dates(market_bars),
    }
    record_equity_alignment_meta(updated["meta"]["equityRefresh"], equity_alignment)
    if equity_alignment["blocked"] and dashboard_block_is_usable(updated.get("equityShortTermRisk")):
        updated["meta"]["equityRefresh"].update(
            {
                "lastKnownGoodBlocks": ["equityShortTermRisk"],
                "failedBlocks": ["equityShortTermRisk"],
            }
        )
    return updated


def fetch_equity_market_bars(
    *,
    end: date | None = None,
    years: int = 3,
    timeout: int = 14,
    limit: int = 900,
    fetcher: DailyBarFetcher = fetch_nasdaq_daily_bars,
    fallback_fetcher: DailyBarFetcher = fetch_stooq_daily_bars,
    cached_bars: dict[str, list[MarketDailyBar]] | None = None,
    overlap_days: int = DEFAULT_MARKET_CACHE_OVERLAP_DAYS,
) -> tuple[dict[str, list[MarketDailyBar]], list[dict[str, Any]]]:
    equity_end = end or datetime.now(timezone.utc).date()
    equity_start = equity_end - timedelta(days=365 * years + 10)
    market_bars: dict[str, list[MarketDailyBar]] = {}
    source_rows: list[dict[str, Any]] = []
    cached_bars = cached_bars or {}
    for symbol, asset_class in EQUITY_RISK_SYMBOLS.items():
        cached = cached_bars.get(symbol, [])
        fetch_start = incremental_market_start(cached, equity_start, overlap_days=overlap_days)
        try:
            bars, status = fetch_daily_bars_with_stooq_fallback(
                symbol,
                start=fetch_start,
                end=equity_end,
                asset_class=asset_class,
                timeout=timeout,
                limit=limit,
                fetcher=fetcher,
                fallback_fetcher=fallback_fetcher,
            )
            market_bars[symbol] = merge_market_bars(cached, bars, start=equity_start)
            status = {**status, "cacheMode": "incremental" if cached else "cold"}
            source_rows.append({"name": f"Nasdaq {symbol} OHLCV", **status})
        except Exception as exc:  # noqa: BLE001
            if cached:
                market_bars[symbol] = merge_market_bars(cached, [], start=equity_start)
                source_rows.append({
                    "name": f"Nasdaq {symbol} OHLCV",
                    "status": "stale-cache",
                    "latest": cached[-1].date.isoformat(),
                    "cacheMode": "last-known-good",
                    "note": str(exc),
                })
            else:
                source_rows.append({"name": f"Nasdaq {symbol} OHLCV", "status": "warning", "latest": str(exc)})
    for spec in GLOBAL_LPPL_INDEX_SPECS:
        symbol = str(spec["symbol"]).upper()
        if symbol in market_bars:
            bars = market_bars[symbol]
            latest = bars[-1].date.isoformat() if bars else "none"
            upstream = next(
                (
                    row for row in source_rows
                    if row.get("name") == f"Nasdaq {symbol} OHLCV"
                ),
                {},
            )
            inherited = {
                key: upstream[key]
                for key in ("status", "source", "note", "cacheMode")
                if key in upstream
            }
            source_rows.append({
                "name": f"Global LPPL {symbol} OHLCV",
                "status": inherited.pop("status", "ok"),
                "latest": latest,
                **inherited,
            })
            continue
        if spec.get("source") == "nasdaq":
            cached = cached_bars.get(symbol, [])
            fetch_start = incremental_market_start(cached, equity_start, overlap_days=overlap_days)
            try:
                bars, status = fetch_daily_bars_with_stooq_fallback(
                    str(spec["sourceSymbol"]),
                    start=fetch_start,
                    end=equity_end,
                    asset_class=str(spec.get("assetClass") or "etf"),
                    timeout=timeout,
                    limit=limit,
                    fallback_symbol=str(spec.get("fallbackSymbol") or ""),
                    output_symbol=symbol,
                    fetcher=fetcher,
                    fallback_fetcher=fallback_fetcher,
                )
                market_bars[symbol] = merge_market_bars(cached, bars, start=equity_start)
                status = {**status, "cacheMode": "incremental" if cached else "cold"}
                source_rows.append({"name": f"Global LPPL {symbol} OHLCV", **status})
            except Exception as exc:  # noqa: BLE001
                if cached:
                    market_bars[symbol] = merge_market_bars(cached, [], start=equity_start)
                    source_rows.append({
                        "name": f"Global LPPL {symbol} OHLCV",
                        "status": "stale-cache",
                        "latest": cached[-1].date.isoformat(),
                        "cacheMode": "last-known-good",
                        "note": str(exc),
                    })
                else:
                    source_rows.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})
            continue
        if spec.get("source") != "stooq":
            continue
        cached = cached_bars.get(symbol, [])
        fetch_start = incremental_market_start(cached, equity_start, overlap_days=overlap_days)
        try:
            bars = fetch_stooq_daily_bars(str(spec["sourceSymbol"]), start=fetch_start, end=equity_end, timeout=timeout)
            fetched = [
                MarketDailyBar(symbol=symbol, date=bar.date, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume, source=bar.source)
                for bar in bars
            ]
            market_bars[symbol] = merge_market_bars(cached, fetched, start=equity_start)
            latest = market_bars[symbol][-1].date.isoformat() if market_bars[symbol] else "none"
            source_rows.append({
                "name": f"Global LPPL {symbol} OHLCV",
                "status": "ok",
                "latest": latest,
                "cacheMode": "incremental" if cached else "cold",
            })
        except Exception as exc:  # noqa: BLE001
            if cached:
                market_bars[symbol] = merge_market_bars(cached, [], start=equity_start)
                source_rows.append({
                    "name": f"Global LPPL {symbol} OHLCV",
                    "status": "stale-cache",
                    "latest": cached[-1].date.isoformat(),
                    "cacheMode": "last-known-good",
                    "note": str(exc),
                })
            else:
                source_rows.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})
    return market_bars, source_rows


def _run_equity_update_unlocked(
    output: Path = DEFAULT_OUTPUT,
    *,
    history_path: Path | None = None,
    save_history: bool = True,
    years: int = 3,
    timeout: int = 14,
    limit: int = 900,
    cache_path: Path | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    dashboard = read_dashboard_json(output)
    resolved_cache_path = cache_path or market_cache_path_for_output(output)
    cached_bars = load_market_bar_cache(resolved_cache_path) if use_cache else {}
    market_bars, source_rows = fetch_equity_market_bars(
        years=years,
        timeout=timeout,
        limit=limit,
        cached_bars=cached_bars,
    )
    if use_cache and market_bars:
        save_market_bar_cache(market_bars, resolved_cache_path)
    if not market_bars:
        failed_candidate = build_failed_fetch_dashboard(dashboard, source_rows)
        require_dashboard_contract(failed_candidate)
        write_failed_dashboard_json(failed_candidate, output)
        return dashboard
    scoring_skipped = bool(cached_bars) and dashboard_covers_market_bars(dashboard, market_bars)
    if scoring_skipped:
        updated = build_cache_hit_dashboard(dashboard, market_bars, source_rows)
    else:
        updated = build_updated_dashboard(dashboard, market_bars, source_status_rows=source_rows)
    require_dashboard_contract(updated)
    regression_issues = snapshot_regression_issues(updated, dashboard)
    if regression_issues:
        updated.setdefault("meta", {}).setdefault("equityRefresh", {})["refreshGate"] = {
            "status": "rejected",
            "issues": regression_issues,
        }
        write_failed_dashboard_json(updated, output)
        return dashboard
    used_last_known_good = bool((updated.get("meta") or {}).get("equityRefresh", {}).get("lastKnownGoodBlocks"))
    if save_history and not scoring_skipped and not used_last_known_good:
        try:
            save_dashboard_history(updated, history_path or history_db_for_output(output))
        except Exception as exc:
            updated.setdefault("meta", {}).setdefault("equityRefresh", {})["refreshGate"] = {
                "status": "rejected",
                "issues": [f"history persistence failed: {exc}"],
            }
            try:
                write_failed_dashboard_json(updated, output)
            except Exception:  # noqa: BLE001 - preserve the original persistence failure
                pass
            raise
    write_dashboard_json(updated, output)
    return updated


def run_equity_update(
    output: Path = DEFAULT_OUTPUT,
    *,
    history_path: Path | None = None,
    save_history: bool = True,
    years: int = 3,
    timeout: int = 14,
    limit: int = 900,
    cache_path: Path | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    with dashboard_update_file_lock(output):
        return _run_equity_update_unlocked(
            output,
            history_path=history_path,
            save_history=save_history,
            years=years,
            timeout=timeout,
            limit=limit,
            cache_path=cache_path,
            use_cache=use_cache,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh only the equityShortTermRisk block in dashboard.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--history-db", type=Path, default=None, help="SQLite history database path; defaults beside output")
    parser.add_argument("--no-history", action="store_true", help="Do not persist this partial refresh into SQLite history")
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=14)
    parser.add_argument("--limit", type=int, default=900)
    parser.add_argument("--cache", type=Path, default=None, help="Market-bar cache path; defaults to data/cache/market-bars-v1.json")
    parser.add_argument("--no-cache", action="store_true", help="Disable incremental market-bar cache")
    args = parser.parse_args(argv)
    dashboard = run_equity_update(
        args.output,
        history_path=args.history_db,
        save_history=not args.no_history,
        years=args.years,
        timeout=args.timeout,
        limit=args.limit,
        cache_path=args.cache,
        use_cache=not args.no_cache,
    )
    risk = dashboard.get("equityShortTermRisk", {})
    lppl = dashboard.get("globalLpplRisk", {})
    backtest = risk.get("backtest", {}) if isinstance(risk, dict) else {}
    print(
        f"Wrote {args.output} with equityShortTermRisk={risk.get('score')} "
        f"globalLpplRisk={lppl.get('score') if isinstance(lppl, dict) else None} "
        f"trend={len((risk.get('trend') or {}).get('points') or [])} "
        f"backtest={backtest.get('sampleSize')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
