from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.update_data import DEFAULT_OUTPUT, failed_output_path, parse_snapshot_generated_at, run_update  # noqa: E402
from scripts.update_equity_risk import run_equity_update as run_equity_update_only  # noqa: E402
from treasury_data.build_dashboard import window_start  # noqa: E402
from treasury_data.history_backfill import backfill_public_history  # noqa: E402
from treasury_data.history_store import (  # noqa: E402
    historical_series_payload,
    history_db_for_output,
    history_summary,
    list_dashboard_snapshots,
    list_historical_series_stats,
)
from treasury_data.api import api_response_for_path, build_health_payload  # noqa: E402

UpdateFunc = Callable[[Path], dict[str, Any]]
EquityUpdateFunc = Callable[..., dict[str, Any]]
_manual_update_lock = threading.Lock()
_manual_update_thread: threading.Thread | None = None
_manual_equity_update_lock = threading.Lock()
_manual_equity_update_thread: threading.Thread | None = None
_dashboard_update_lock = threading.Lock()
NEW_YORK_TZ = ZoneInfo("America/New_York")
DEFAULT_EQUITY_INTERVAL_MINUTES = 30.0
DEFAULT_EQUITY_CATCHUP_INTERVAL_MINUTES = 5.0
DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES = 20


def seconds_until_next_run(run_at: str, now: datetime | None = None) -> int:
    now = now or datetime.now()
    hour_text, minute_text = run_at.split(":", 1)
    target = now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int((target - now).total_seconds())


def previous_weekday(day: date) -> date:
    cursor = day - timedelta(days=1)
    while cursor.weekday() >= 5:
        cursor -= timedelta(days=1)
    return cursor


def _observed_fixed_holiday(month: int, day: int, year: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    cursor = date(year, month, 1)
    offset = (weekday - cursor.weekday()) % 7
    return cursor + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    cursor = next_month - timedelta(days=1)
    return cursor - timedelta(days=(cursor.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    """Gregorian Easter date (Anonymous Gregorian computus)."""

    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def us_equity_market_holidays(year: int) -> set[date]:
    holidays = {
        _observed_fixed_holiday(1, 1, year),
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed_fixed_holiday(7, 4, year),
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed_fixed_holiday(12, 25, year),
    }
    if year >= 2022:
        holidays.add(_observed_fixed_holiday(6, 19, year))
    return holidays


def is_us_equity_session(day: date) -> bool:
    if day.weekday() >= 5:
        return False
    # New Year's Day can be observed in the adjacent calendar year.
    holidays = set().union(*(us_equity_market_holidays(year) for year in (day.year - 1, day.year, day.year + 1)))
    return day not in holidays


def previous_us_equity_session(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_us_equity_session(cursor):
        cursor -= timedelta(days=1)
    return cursor


def _ceil_positive_minutes(delta: timedelta) -> int:
    return max(0, int((delta.total_seconds() + 59) // 60))


def _floor_positive_minutes(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() // 60))


def equity_bar_timing(
    now: datetime | None = None,
    *,
    after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    ny_now = current.astimezone(NEW_YORK_TZ)
    ny_today = ny_now.date()
    close_time = ny_now.replace(hour=16, minute=0, second=0, microsecond=0)
    ready_time = close_time + timedelta(minutes=after_close_lag_minutes)
    if not is_us_equity_session(ny_today):
        expected = previous_us_equity_session(ny_today)
        phase = "non_trading_day"
        minutes_until_expected = None
        minutes_since_expected = None
    elif ny_now < close_time:
        expected = previous_us_equity_session(ny_today)
        phase = "trading_session"
        minutes_until_expected = _ceil_positive_minutes(ready_time - ny_now)
        minutes_since_expected = None
    elif ny_now < ready_time:
        expected = previous_us_equity_session(ny_today)
        phase = "post_close_wait"
        minutes_until_expected = _ceil_positive_minutes(ready_time - ny_now)
        minutes_since_expected = None
    else:
        expected = ny_today
        phase = "daily_bar_due"
        minutes_until_expected = 0
        minutes_since_expected = _floor_positive_minutes(ny_now - ready_time)
    return {
        "expectedDate": expected,
        "marketDate": ny_today,
        "marketTime": ny_now.isoformat(),
        "readyAt": ready_time.isoformat() if is_us_equity_session(ny_today) else None,
        "phase": phase,
        "minutesUntilExpected": minutes_until_expected,
        "minutesSinceExpected": minutes_since_expected,
        "afterCloseLagMinutes": after_close_lag_minutes,
    }


def expected_equity_bar_date(
    now: datetime | None = None,
    *,
    after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
) -> date:
    timing = equity_bar_timing(now, after_close_lag_minutes=after_close_lag_minutes)
    expected = timing["expectedDate"]
    if not isinstance(expected, date):
        raise TypeError("equity_bar_timing expectedDate must be a date")
    return expected


class NoStoreHandler(http.server.SimpleHTTPRequestHandler):
    dashboard_output: Path = DEFAULT_OUTPUT
    history_db_path: Path | None = None
    update_func: UpdateFunc = staticmethod(run_update)
    equity_update_func: EquityUpdateFunc = staticmethod(lambda output, **kwargs: run_equity_update_for_server(output, **kwargs))
    equity_years: int = 3
    equity_timeout: int = 14
    equity_limit: int = 900
    equity_after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES
    equity_freshness_now: datetime | None = None

    def end_headers(self) -> None:
        if self.path.startswith("/data/") or self.path.startswith("/api/"):
            # Permit conditional validation while still requiring clients to
            # revalidate before using a snapshot.
            self.send_header("Cache-Control", "private, no-cache, max-age=0")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/data/dashboard.json":
            try:
                body = self.dashboard_output.read_bytes()
            except OSError as exc:
                self.write_json_response(500, {"error": str(exc)})
                return
            self.write_bytes_response(200, body, "application/json; charset=utf-8")
            return
        if parsed.path.startswith("/api/history"):
            try:
                status, payload = history_payload_for_path(parsed.path, self.resolved_history_db_path(), parse_qs(parsed.query))
            except Exception as exc:  # noqa: BLE001
                status = 500
                payload = {"error": str(exc)}
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.write_bytes_response(status, body, "application/json; charset=utf-8")
            return
        if parsed.path == "/api/health":
            try:
                dashboard = read_dashboard_json(self.dashboard_output)
                payload = build_health_payload(dashboard)
                normalize_health_source_status(payload, dashboard)
                history = history_summary(self.resolved_history_db_path())
                payload["history"] = history
                warnings = history_backfill_warnings(history)
                warnings.extend(last_known_good_refresh_warnings(dashboard))
                rejected_warning = rejected_refresh_warning(self.dashboard_output, dashboard)
                if rejected_warning is not None:
                    warnings.append(rejected_warning)
                risk = dashboard.get("equityShortTermRisk") if isinstance(dashboard.get("equityShortTermRisk"), dict) else {}
                if risk.get("asOf"):
                    freshness = equity_risk_freshness(
                        self.dashboard_output,
                        now=self.equity_freshness_now,
                        after_close_lag_minutes=self.equity_after_close_lag_minutes,
                    )
                    payload["equityRiskFreshness"] = freshness
                    if freshness.get("stale"):
                        warnings.append(
                            {
                                "name": "Equity Short-Term Risk",
                                "status": "warning",
                                "latest": f"source {freshness.get('sourceDate')} < expected {freshness.get('expectedDate')}",
                                "scope": "equity_risk_freshness",
                            }
                        )
                if warnings:
                    payload["warnings"] = warnings
                    payload["status"] = "degraded"
            except Exception as exc:  # noqa: BLE001
                status = 500
                payload = {"error": str(exc)}
            else:
                status = 200
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.write_bytes_response(status, body, "application/json; charset=utf-8")
            return
        if parsed.path.startswith("/api/"):
            try:
                dashboard = read_dashboard_json(self.dashboard_output)
                status, body, content_type = api_response_for_path(dashboard, parsed.path, parse_qs(parsed.query))
            except Exception as exc:  # noqa: BLE001
                status = 500
                content_type = "application/json; charset=utf-8"
                body = json.dumps({"error": str(exc)}, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.write_bytes_response(status, body, content_type)
            return
        super().do_GET()

    def resolved_history_db_path(self) -> Path:
        return self.history_db_path or history_db_for_output(self.dashboard_output)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/update":
            self.handle_manual_update_post()
            return
        if parsed.path == "/api/update-equity":
            self.handle_manual_equity_update_post()
            return

        self.write_json_response(404, {"error": "unknown api route"})

    def handle_manual_update_post(self) -> None:
        try:
            already_running = is_manual_update_running()
            start_manual_update(self.dashboard_output, self.update_func)
            dashboard = read_dashboard_json(self.dashboard_output)
            payload = {
                "status": "running" if already_running else "accepted",
                "message": "manual update already running" if already_running else "manual update started",
                "asOf": dashboard.get("asOf"),
                "generatedAt": dashboard.get("generatedAt"),
            }
            status = 202
        except Exception as exc:  # noqa: BLE001
            payload = {"status": "error", "error": str(exc)}
            status = 500
        self.write_json_response(status, payload)

    def handle_manual_equity_update_post(self) -> None:
        try:
            already_running = is_manual_equity_update_running()
            start_manual_equity_update(
                self.dashboard_output,
                equity_update_func=self.equity_update_func,
                years=self.equity_years,
                timeout=self.equity_timeout,
                limit=self.equity_limit,
            )
            dashboard = read_dashboard_json(self.dashboard_output)
            risk = dashboard.get("equityShortTermRisk") if isinstance(dashboard.get("equityShortTermRisk"), dict) else {}
            freshness = equity_risk_freshness(
                self.dashboard_output,
                now=self.equity_freshness_now,
                after_close_lag_minutes=self.equity_after_close_lag_minutes,
            )
            payload = {
                "status": "running" if already_running else "accepted",
                "message": "equity update already running" if already_running else "equity update started",
                "asOf": dashboard.get("asOf"),
                "generatedAt": dashboard.get("generatedAt"),
                "equityRiskAsOf": risk.get("asOf"),
                "equityRiskScore": risk.get("score"),
                "equityRiskFreshness": freshness,
            }
            status = 202
        except Exception as exc:  # noqa: BLE001
            payload = {"status": "error", "error": str(exc)}
            status = 500
        self.write_json_response(status, payload)

    def write_json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.write_bytes_response(status, body, "application/json; charset=utf-8")

    def write_bytes_response(self, status: int, body: bytes, content_type: str) -> None:
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        try:
            if status == 200 and self.command == "GET" and self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers can abandon an in-flight response during reload, tab close,
            # or server shutdown. Treat that as a normal client disconnect rather
            # than surfacing a noisy request-handler traceback.
            return


def read_dashboard_json(path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a dashboard object")
    return payload


def history_payload_for_path(path: str, db_path: Path, params: dict[str, list[str]] | None = None) -> tuple[int, Any]:
    params = params or {}
    normalized = path.rstrip("/") or path
    if normalized == "/api/history":
        return 200, history_summary(db_path)
    if normalized == "/api/history/snapshots":
        return 200, list_dashboard_snapshots(db_path, limit=int_param(params, "limit", 30))
    if normalized == "/api/history/stats":
        return 200, list_historical_series_stats(db_path, limit=int_param(params, "limit", 200))
    if normalized == "/api/history/series":
        years = int_param(params, "years", 5)
        start_date = first_param(params, "from") or default_history_start_date(db_path, years)
        return 200, historical_series_payload(
            db_path,
            category=first_param(params, "category"),
            name=first_param(params, "name"),
            label=first_param(params, "label") if "label" in params else None,
            start_date=start_date,
            limit=int_param(params, "limit", int_param(params, "max_points", 1200)),
        )
    return 404, {"error": "unknown api route"}


def history_backfill_warnings(history: dict[str, Any]) -> list[dict[str, Any]]:
    latest_backfill = history.get("latestBackfill")
    if not isinstance(latest_backfill, dict):
        return []
    if latest_backfill.get("status") == "ok":
        return []
    source_errors = latest_backfill.get("sourceErrors")
    if not isinstance(source_errors, list):
        return []
    warnings: list[dict[str, Any]] = []
    for item in source_errors:
        if not isinstance(item, dict):
            continue
        warnings.append(
            {
                "name": str(item.get("name") or "history backfill source"),
                "status": "warning",
                "latest": str(item.get("error") or ""),
                "scope": "history_backfill",
            }
        )
    return warnings


def normalize_health_source_status(payload: dict[str, Any], dashboard: dict[str, Any]) -> None:
    """Keep health classification case-insensitive and fail closed on error rows."""

    rows = dashboard.get("sourceStatus") if isinstance(dashboard.get("sourceStatus"), list) else []
    counts: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "unknown").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
        if status == "error":
            errors.append(row)
    payload["sourceCounts"] = counts
    payload["errors"] = errors
    if errors:
        payload["status"] = "degraded"


def last_known_good_refresh_warnings(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    meta = dashboard.get("meta") if isinstance(dashboard.get("meta"), dict) else {}
    full_blocks = meta.get("lastKnownGoodBlocks") if isinstance(meta.get("lastKnownGoodBlocks"), list) else []
    equity_meta = meta.get("equityRefresh") if isinstance(meta.get("equityRefresh"), dict) else {}
    equity_blocks = (
        equity_meta.get("lastKnownGoodBlocks")
        if isinstance(equity_meta.get("lastKnownGoodBlocks"), list)
        else []
    )
    block_names = sorted(
        {
            str(item.get("key") if isinstance(item, dict) else item)
            for item in [*full_blocks, *equity_blocks]
            if (item.get("key") if isinstance(item, dict) else item)
        }
    )
    if not block_names:
        return []
    return [
        {
            "name": "Last-known-good dashboard blocks",
            "status": "warning",
            "latest": ", ".join(block_names),
            "scope": "refresh_last_known_good",
        }
    ]


def rejected_refresh_warning(output: Path, dashboard: dict[str, Any]) -> dict[str, Any] | None:
    """Expose a newer rejected candidate without replacing the healthy snapshot."""

    rejected_path = failed_output_path(output)
    if not rejected_path.exists():
        return None
    try:
        rejected = read_dashboard_json(rejected_path)
    except Exception:  # noqa: BLE001 - a corrupt failure artifact is itself health evidence
        try:
            is_newer = rejected_path.stat().st_mtime > output.stat().st_mtime
        except OSError:
            is_newer = True
        if not is_newer:
            return None
        return {
            "name": "Latest dashboard refresh",
            "status": "warning",
            "latest": "rejected candidate is unreadable",
            "scope": "refresh_gate",
        }

    rejected_generated_at = parse_snapshot_generated_at(rejected.get("generatedAt"))
    served_generated_at = parse_snapshot_generated_at(dashboard.get("generatedAt"))
    if rejected_generated_at is not None and served_generated_at is not None:
        if rejected_generated_at <= served_generated_at:
            return None
    else:
        try:
            if rejected_path.stat().st_mtime <= output.stat().st_mtime:
                return None
        except OSError:
            pass

    meta = rejected.get("meta") if isinstance(rejected.get("meta"), dict) else {}
    refresh_gate = meta.get("refreshGate") if isinstance(meta.get("refreshGate"), dict) else {}
    equity_meta = meta.get("equityRefresh") if isinstance(meta.get("equityRefresh"), dict) else {}
    equity_gate = equity_meta.get("refreshGate") if isinstance(equity_meta.get("refreshGate"), dict) else {}
    issues = refresh_gate.get("issues") if isinstance(refresh_gate.get("issues"), list) else equity_gate.get("issues")
    issue_text = "; ".join(str(item) for item in issues[:3]) if isinstance(issues, list) else ""
    return {
        "name": "Latest dashboard refresh",
        "status": "warning",
        "latest": str(rejected.get("generatedAt") or "rejected candidate"),
        "scope": "refresh_gate",
        **({"detail": issue_text} if issue_text else {}),
    }


def default_history_start_date(db_path: Path, years: int) -> str:
    summary = history_summary(db_path)
    end_text = summary.get("historicalEndDate")
    if isinstance(end_text, str):
        try:
            return window_start(date.fromisoformat(end_text), years=years).isoformat()
        except ValueError:
            pass
    return window_start(date.today(), years=years).isoformat()


def first_param(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def int_param(params: dict[str, list[str]], key: str, default: int) -> int:
    value = first_param(params, key)
    if value is None:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


def equity_risk_freshness(
    output: Path,
    *,
    now: datetime | None = None,
    after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
) -> dict[str, Any]:
    timing = equity_bar_timing(now, after_close_lag_minutes=after_close_lag_minutes)
    expected = timing["expectedDate"]
    base = {
        "expectedDate": expected.isoformat(),
        "marketDate": timing["marketDate"].isoformat(),
        "marketTime": timing["marketTime"],
        "readyAt": timing["readyAt"],
        "minutesUntilExpected": timing["minutesUntilExpected"],
        "minutesSinceExpected": timing["minutesSinceExpected"],
        "afterCloseLagMinutes": timing["afterCloseLagMinutes"],
    }
    try:
        dashboard = read_dashboard_json(output)
        risk = dashboard.get("equityShortTermRisk") if isinstance(dashboard.get("equityShortTermRisk"), dict) else {}
        source_text = risk.get("asOf") or (risk.get("lookAheadGuard") or {}).get("dataThrough")
        source_date = date.fromisoformat(str(source_text)) if source_text else None
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "sourceDate": None,
            "stale": True,
            "lagDays": None,
            "phase": "error",
            "timeliness": "error",
            "error": str(exc),
        }
    lag_days = (expected - source_date).days if source_date else None
    stale = source_date is None or source_date < expected
    timing_phase = str(timing["phase"])
    if stale:
        phase = "catchup"
        timeliness = "catchup"
    elif timing_phase in {"trading_session", "post_close_wait"}:
        phase = timing_phase
        timeliness = "waiting"
    elif timing_phase == "non_trading_day":
        phase = "non_trading_day"
        timeliness = "fresh"
    else:
        phase = "fresh"
        timeliness = "fresh"
    return {
        **base,
        "sourceDate": source_date.isoformat() if source_date else None,
        "stale": stale,
        "lagDays": lag_days,
        "phase": phase,
        "timeliness": timeliness,
    }


def equity_risk_needs_catchup(
    output: Path,
    *,
    after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
) -> bool:
    return bool(equity_risk_freshness(output, after_close_lag_minutes=after_close_lag_minutes).get("stale"))


def run_equity_update_for_server(output: Path, *, years: int = 3, timeout: int = 14, limit: int = 900) -> dict[str, Any]:
    return run_equity_update_only(output, save_history=False, years=years, timeout=timeout, limit=limit)


def run_logged_update(label: str, output: Path, update_func: UpdateFunc = run_update) -> None:
    try:
        with _dashboard_update_lock:
            dashboard = update_func(output)
        print(f"[{label}] wrote {output} asOf={dashboard['asOf']} generatedAt={dashboard['generatedAt']}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] failed: {exc}", flush=True)


def run_logged_equity_update(
    label: str,
    output: Path,
    equity_update_func: EquityUpdateFunc = run_equity_update_for_server,
    *,
    years: int = 3,
    timeout: int = 14,
    limit: int = 900,
) -> None:
    try:
        with _dashboard_update_lock:
            dashboard = equity_update_func(output, years=years, timeout=timeout, limit=limit)
        risk = dashboard.get("equityShortTermRisk") if isinstance(dashboard.get("equityShortTermRisk"), dict) else {}
        print(
            f"[{label}] wrote {output} equityShortTermRisk={risk.get('score')} "
            f"riskAsOf={risk.get('asOf')} generatedAt={dashboard.get('generatedAt')}",
            flush=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] equity update failed: {exc}", flush=True)


def run_logged_history_backfill(label: str, db_path: Path, years: int = 5) -> None:
    try:
        summary = backfill_public_history(db_path, years=years)
        print(
            f"[{label}] backfilled {summary['savedObservationCount']} historical observations "
            f"from {summary['startDate']} to {summary['endDate']} into {db_path}",
            flush=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] history backfill failed: {exc}", flush=True)


def start_startup_update(output: Path, update_func: UpdateFunc = run_update) -> threading.Thread:
    thread = threading.Thread(target=run_logged_update, args=("startup", output, update_func), daemon=True)
    thread.start()
    return thread


def is_manual_update_running() -> bool:
    with _manual_update_lock:
        return bool(_manual_update_thread and _manual_update_thread.is_alive())


def is_manual_equity_update_running() -> bool:
    with _manual_equity_update_lock:
        return bool(_manual_equity_update_thread and _manual_equity_update_thread.is_alive())


def start_manual_update(output: Path, update_func: UpdateFunc = run_update) -> threading.Thread:
    global _manual_update_thread
    with _manual_update_lock:
        if _manual_update_thread and _manual_update_thread.is_alive():
            return _manual_update_thread
        _manual_update_thread = threading.Thread(target=run_logged_update, args=("manual", output, update_func), daemon=True)
        _manual_update_thread.start()
        return _manual_update_thread


def start_manual_equity_update(
    output: Path,
    equity_update_func: EquityUpdateFunc = run_equity_update_for_server,
    *,
    years: int = 3,
    timeout: int = 14,
    limit: int = 900,
) -> threading.Thread:
    global _manual_equity_update_thread
    with _manual_equity_update_lock:
        if _manual_equity_update_thread and _manual_equity_update_thread.is_alive():
            return _manual_equity_update_thread
        _manual_equity_update_thread = threading.Thread(
            target=run_logged_equity_update,
            args=("manual-equity", output, equity_update_func),
            kwargs={"years": years, "timeout": timeout, "limit": limit},
            daemon=True,
        )
        _manual_equity_update_thread.start()
        return _manual_equity_update_thread


def update_loop(run_at: str, output: Path, update_func: UpdateFunc = run_update, history_years: int = 5) -> None:
    while True:
        sleep_seconds = seconds_until_next_run(run_at)
        time.sleep(sleep_seconds)
        run_logged_update("updater", output, update_func)
        if history_years > 0:
            run_logged_history_backfill("updater", history_db_for_output(output), years=history_years)


def equity_update_loop(
    interval_minutes: float,
    output: Path,
    equity_update_func: EquityUpdateFunc = run_equity_update_for_server,
    *,
    years: int = 3,
    timeout: int = 14,
    limit: int = 900,
    catchup_interval_minutes: float = DEFAULT_EQUITY_CATCHUP_INTERVAL_MINUTES,
    after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
    stale_check_func: Callable[[Path], bool] | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
    max_runs: int | None = None,
    initial_delay_seconds: float | None = None,
) -> None:
    interval_seconds = max(60, int(interval_minutes * 60))
    catchup_seconds = max(60, int(catchup_interval_minutes * 60))
    runs = 0
    while max_runs is None or runs < max_runs:
        if runs == 0 and initial_delay_seconds is not None:
            delay = initial_delay_seconds
        else:
            needs_catchup = (
                stale_check_func(output)
                if stale_check_func
                else equity_risk_needs_catchup(output, after_close_lag_minutes=after_close_lag_minutes)
            )
            delay = catchup_seconds if needs_catchup else interval_seconds
        sleep_func(max(0, delay))
        run_logged_equity_update(
            "equity-updater",
            output,
            equity_update_func,
            years=years,
            timeout=timeout,
            limit=limit,
        )
        runs += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve Treasury dashboard and run a daily background data update")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8451)
    parser.add_argument("--daily-at", default="16:30", help="Local HH:MM time for daily update")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-start-update", action="store_true")
    parser.add_argument("--history-years", type=int, default=5, help="Years of public history to refresh after each daily update; use 0 to disable")
    parser.add_argument("--equity-interval-minutes", type=float, default=DEFAULT_EQUITY_INTERVAL_MINUTES, help="Minutes between equity-only risk refreshes; use 0 to disable")
    parser.add_argument("--equity-catchup-interval-minutes", type=float, default=DEFAULT_EQUITY_CATCHUP_INTERVAL_MINUTES, help="Minutes between equity-only retries when the latest expected US daily bar is missing")
    parser.add_argument("--equity-after-close-lag-minutes", type=int, default=DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES, help="Minutes after the 16:00 New York close before the latest daily bar is expected")
    parser.add_argument("--equity-years", type=int, default=3, help="Lookback years for equity-only risk refresh")
    parser.add_argument("--equity-timeout", type=int, default=14, help="Per-symbol timeout seconds for equity-only risk refresh")
    parser.add_argument("--equity-limit", type=int, default=900, help="Maximum Nasdaq bars per symbol for equity-only risk refresh")
    parser.add_argument("--once", action="store_true", help="Run one update and exit without serving")
    args = parser.parse_args(argv)

    if args.once:
        run_logged_update("startup", args.output)
        return 0

    if not args.skip_start_update:
        start_startup_update(args.output)

    thread = threading.Thread(target=update_loop, args=(args.daily_at, args.output, run_update, args.history_years), daemon=True)
    thread.start()

    if args.equity_interval_minutes > 0:
        equity_initial_delay = 60 if not args.skip_start_update else 0
        equity_thread = threading.Thread(
            target=equity_update_loop,
            args=(args.equity_interval_minutes, args.output, run_equity_update_for_server),
            kwargs={
                "years": args.equity_years,
                "timeout": args.equity_timeout,
                "limit": args.equity_limit,
                "catchup_interval_minutes": args.equity_catchup_interval_minutes,
                "after_close_lag_minutes": args.equity_after_close_lag_minutes,
                "initial_delay_seconds": equity_initial_delay,
            },
            daemon=True,
        )
        equity_thread.start()

    NoStoreHandler.dashboard_output = args.output
    NoStoreHandler.history_db_path = history_db_for_output(args.output)
    NoStoreHandler.equity_years = args.equity_years
    NoStoreHandler.equity_timeout = args.equity_timeout
    NoStoreHandler.equity_limit = args.equity_limit
    NoStoreHandler.equity_after_close_lag_minutes = args.equity_after_close_lag_minutes
    handler = functools.partial(NoStoreHandler, directory=str(PROJECT_ROOT))
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {PROJECT_ROOT} at http://{args.host}:{args.port}/", flush=True)
    print(f"Daily update scheduled at local time {args.daily_at}", flush=True)
    if args.equity_interval_minutes > 0:
        print(
            f"Equity-only refresh scheduled every {args.equity_interval_minutes:g} minutes "
            f"(catch-up {args.equity_catchup_interval_minutes:g} minutes after close lag {args.equity_after_close_lag_minutes}m)",
            flush=True,
        )
    if args.history_years > 0:
        print(f"Daily public history backfill enabled for {args.history_years} years", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
