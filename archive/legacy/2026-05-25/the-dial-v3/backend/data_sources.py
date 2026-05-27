"""Raw data fetchers for FRED, CBOE, and Stooq."""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests


USER_AGENT = "TheDial/3.0"
DEFAULT_TIMEOUT = 25
DEFAULT_RETRIES = 3


def _request_text(url: str, timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES) -> str:
    headers = {"User-Agent": USER_AGENT}
    last_error: Optional[Exception] = None

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            return response.text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < retries - 1:
                time.sleep(0.6 * (2 ** attempt))

    if last_error:
        raise last_error
    raise RuntimeError("request failed without explicit error")


def _normalize_date(raw: str) -> Optional[str]:
    if not raw:
        return None

    value = raw.strip()
    if not value:
        return None

    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%Y%m%d",
        "%d-%b-%Y",
        "%b %d %Y",
    ):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _to_float(raw: Any) -> Optional[float]:
    if raw is None:
        return None

    value = str(raw).strip()
    if value in {"", ".", "NA", "N/A", "null", "None"}:
        return None

    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _normalize_rows(rows: List[Dict[str, Any]], source: str, symbol: str) -> List[Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        date = _normalize_date(str(row.get("date", "")))
        value = _to_float(row.get("value"))
        if not date or value is None:
            continue
        normalized[date] = {
            "date": date,
            "value": value,
            "source": source,
            "symbol": symbol,
        }

    return [normalized[key] for key in sorted(normalized.keys())]


def fetch_fred_csv(series_id: str) -> List[Dict[str, Any]]:
    """Fetch a FRED series via CSV endpoint without API key."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    text = _request_text(url)

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or len(reader.fieldnames) < 2:
        return []

    date_col = reader.fieldnames[0]
    value_col = reader.fieldnames[1]
    rows = [{"date": row.get(date_col), "value": row.get(value_col)} for row in reader]
    return _normalize_rows(rows, source="fred", symbol=series_id)


def fetch_cboe_history(symbol: str) -> List[Dict[str, Any]]:
    """Fetch CBOE index history (supports VIX/VXV/OVX) from public CSV endpoints."""
    symbol = symbol.upper()
    candidates = [
        f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv",
        f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol.lower()}_History.csv",
    ]

    text = ""
    for url in candidates:
        try:
            text = _request_text(url)
            if "Date" in text or "DATE" in text:
                break
        except Exception:  # noqa: BLE001
            continue

    if not text:
        return []

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []

    date_keys = ("Date", "DATE", "Trade Date")
    value_keys = ("Close", "CLOSE", "PX_LAST", "VIX Close", symbol)

    rows: List[Dict[str, Any]] = []
    for row in reader:
        date_raw = ""
        for key in date_keys:
            if key in row and row[key]:
                date_raw = row[key]
                break

        value_raw = None
        for key in value_keys:
            if key in row and row[key] not in {"", None}:
                value_raw = row[key]
                break

        if not value_raw:
            # fallback: pick the right-most non-empty numeric column
            numeric_candidates = [cell for cell in row.values() if _to_float(cell) is not None]
            value_raw = numeric_candidates[-1] if numeric_candidates else None

        rows.append({"date": date_raw, "value": value_raw})

    return _normalize_rows(rows, source="cboe", symbol=symbol)


def fetch_stooq_daily(symbol: str) -> List[Dict[str, Any]]:
    """Fetch daily OHLC data from stooq and return close series."""
    normalized_symbol = symbol.lower()
    url = f"https://stooq.com/q/d/l/?s={normalized_symbol}&i=d"
    text = _request_text(url)

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []

    rows = [
        {
            "date": row.get("Date") or row.get("date"),
            "value": row.get("Close") or row.get("close"),
        }
        for row in reader
    ]

    return _normalize_rows(rows, source="stooq", symbol=normalized_symbol)
