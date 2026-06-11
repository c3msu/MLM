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

from scripts.update_data import DEFAULT_OUTPUT, write_dashboard_json  # noqa: E402
from treasury_data.build_dashboard import (  # noqa: E402
    EQUITY_RISK_SYMBOLS,
    GLOBAL_LPPL_INDEX_SPECS,
    build_equity_short_term_risk_index,
    build_global_lppl_risk_index,
)
from treasury_data.history_store import history_db_for_output, save_dashboard_history  # noqa: E402
from treasury_data.sources import CalendarEvent, MarketDailyBar, fetch_nasdaq_daily_bars, fetch_stooq_daily_bars  # noqa: E402

DailyBarFetcher = Callable[..., list[MarketDailyBar]]


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


def build_source_status_rows(market_bars: dict[str, list[MarketDailyBar]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
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


def merge_source_status(existing: Any, equity_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    existing_rows = [row for row in existing if isinstance(row, dict)] if isinstance(existing, list) else []
    equity_names = {row["name"] for row in equity_rows}
    retained = [row for row in existing_rows if row.get("name") not in equity_names]
    return retained + equity_rows


def build_updated_dashboard(
    dashboard: dict[str, Any],
    market_bars: dict[str, list[MarketDailyBar]],
    *,
    generated_at: datetime | None = None,
    source_status_rows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    updated = copy.deepcopy(dashboard)
    risk = build_equity_short_term_risk_index(
        market_bars=market_bars,
        macro_liquidity_equity=dashboard.get("macroLiquidityEquity") if isinstance(dashboard.get("macroLiquidityEquity"), dict) else {},
        spy_early_warning=dashboard.get("spyEarlyWarning") if isinstance(dashboard.get("spyEarlyWarning"), dict) else {},
        calendar_events=dashboard_events_to_calendar_events(dashboard),
    )
    updated["equityShortTermRisk"] = risk
    updated["globalLpplRisk"] = build_global_lppl_risk_index(market_bars=market_bars)
    updated["generatedAt"] = (generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    updated["sourceStatus"] = merge_source_status(
        dashboard.get("sourceStatus", []),
        source_status_rows or build_source_status_rows(market_bars),
    )
    return updated


def fetch_equity_market_bars(
    *,
    end: date | None = None,
    years: int = 3,
    timeout: int = 14,
    limit: int = 900,
    fetcher: DailyBarFetcher = fetch_nasdaq_daily_bars,
) -> tuple[dict[str, list[MarketDailyBar]], list[dict[str, str]]]:
    equity_end = end or datetime.now(timezone.utc).date()
    equity_start = equity_end - timedelta(days=365 * years + 10)
    market_bars: dict[str, list[MarketDailyBar]] = {}
    source_rows: list[dict[str, str]] = []
    for symbol, asset_class in EQUITY_RISK_SYMBOLS.items():
        try:
            bars = fetcher(symbol, start=equity_start, end=equity_end, asset_class=asset_class, timeout=timeout, limit=limit)
            market_bars[symbol] = bars
            latest = bars[-1].date.isoformat() if bars else "none"
            source_rows.append({"name": f"Nasdaq {symbol} OHLCV", "status": "ok", "latest": latest})
        except Exception as exc:  # noqa: BLE001
            source_rows.append({"name": f"Nasdaq {symbol} OHLCV", "status": "warning", "latest": str(exc)})
    for spec in GLOBAL_LPPL_INDEX_SPECS:
        symbol = str(spec["symbol"]).upper()
        if symbol in market_bars:
            bars = market_bars[symbol]
            latest = bars[-1].date.isoformat() if bars else "none"
            source_rows.append({"name": f"Global LPPL {symbol} OHLCV", "status": "ok", "latest": latest})
            continue
        if spec.get("source") == "nasdaq":
            try:
                bars = fetcher(
                    str(spec["sourceSymbol"]),
                    start=equity_start,
                    end=equity_end,
                    asset_class=str(spec.get("assetClass") or "etf"),
                    timeout=timeout,
                    limit=limit,
                )
                market_bars[symbol] = [
                    MarketDailyBar(symbol=symbol, date=bar.date, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume, source=bar.source)
                    for bar in bars
                ]
                latest = bars[-1].date.isoformat() if bars else "none"
                source_rows.append({"name": f"Global LPPL {symbol} OHLCV", "status": "ok", "latest": latest})
            except Exception as exc:  # noqa: BLE001
                source_rows.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})
            continue
        if spec.get("source") != "stooq":
            continue
        try:
            bars = fetch_stooq_daily_bars(str(spec["sourceSymbol"]), start=equity_start, end=equity_end, timeout=timeout)
            market_bars[symbol] = [
                MarketDailyBar(symbol=symbol, date=bar.date, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume, source=bar.source)
                for bar in bars
            ]
            latest = bars[-1].date.isoformat() if bars else "none"
            source_rows.append({"name": f"Global LPPL {symbol} OHLCV", "status": "ok", "latest": latest})
        except Exception as exc:  # noqa: BLE001
            source_rows.append({"name": f"Global LPPL {symbol} OHLCV", "status": "warning", "latest": str(exc)})
    return market_bars, source_rows


def run_equity_update(
    output: Path = DEFAULT_OUTPUT,
    *,
    history_path: Path | None = None,
    save_history: bool = True,
    years: int = 3,
    timeout: int = 14,
    limit: int = 900,
) -> dict[str, Any]:
    dashboard = read_dashboard_json(output)
    market_bars, source_rows = fetch_equity_market_bars(years=years, timeout=timeout, limit=limit)
    updated = build_updated_dashboard(dashboard, market_bars, source_status_rows=source_rows)
    write_dashboard_json(updated, output)
    if save_history:
        save_dashboard_history(updated, history_path or history_db_for_output(output))
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh only the equityShortTermRisk block in dashboard.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--history-db", type=Path, default=None, help="SQLite history database path; defaults beside output")
    parser.add_argument("--no-history", action="store_true", help="Do not persist this partial refresh into SQLite history")
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=14)
    parser.add_argument("--limit", type=int, default=900)
    args = parser.parse_args(argv)
    dashboard = run_equity_update(
        args.output,
        history_path=args.history_db,
        save_history=not args.no_history,
        years=args.years,
        timeout=args.timeout,
        limit=args.limit,
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
