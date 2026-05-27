from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.update_data import DEFAULT_OUTPUT, run_update  # noqa: E402
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
_manual_update_lock = threading.Lock()
_manual_update_thread: threading.Thread | None = None


def seconds_until_next_run(run_at: str, now: datetime | None = None) -> int:
    now = now or datetime.now()
    hour_text, minute_text = run_at.split(":", 1)
    target = now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int((target - now).total_seconds())


class NoStoreHandler(http.server.SimpleHTTPRequestHandler):
    dashboard_output: Path = DEFAULT_OUTPUT
    history_db_path: Path | None = None
    update_func: UpdateFunc = staticmethod(run_update)

    def end_headers(self) -> None:
        if self.path.startswith("/data/") or self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/history"):
            try:
                status, payload = history_payload_for_path(parsed.path, self.resolved_history_db_path(), parse_qs(parsed.query))
            except Exception as exc:  # noqa: BLE001
                status = 500
                payload = {"error": str(exc)}
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/health":
            try:
                dashboard = read_dashboard_json(self.dashboard_output)
                payload = build_health_payload(dashboard)
                history = history_summary(self.resolved_history_db_path())
                payload["history"] = history
                warnings = history_backfill_warnings(history)
                if warnings:
                    payload["warnings"] = warnings
                    payload["status"] = "degraded"
            except Exception as exc:  # noqa: BLE001
                status = 500
                payload = {"error": str(exc)}
            else:
                status = 200
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path.startswith("/api/"):
            try:
                dashboard = read_dashboard_json(self.dashboard_output)
                status, body, content_type = api_response_for_path(dashboard, parsed.path, parse_qs(parsed.query))
            except Exception as exc:  # noqa: BLE001
                status = 500
                content_type = "application/json; charset=utf-8"
                body = json.dumps({"error": str(exc)}, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def resolved_history_db_path(self) -> Path:
        return self.history_db_path or history_db_for_output(self.dashboard_output)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/update":
            body = json.dumps({"error": "unknown api route"}, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

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
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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


def run_logged_update(label: str, output: Path, update_func: UpdateFunc = run_update) -> None:
    try:
        dashboard = update_func(output)
        print(f"[{label}] wrote {output} asOf={dashboard['asOf']} generatedAt={dashboard['generatedAt']}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] failed: {exc}", flush=True)


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


def start_manual_update(output: Path, update_func: UpdateFunc = run_update) -> threading.Thread:
    global _manual_update_thread
    with _manual_update_lock:
        if _manual_update_thread and _manual_update_thread.is_alive():
            return _manual_update_thread
        _manual_update_thread = threading.Thread(target=run_logged_update, args=("manual", output, update_func), daemon=True)
        _manual_update_thread.start()
        return _manual_update_thread


def update_loop(run_at: str, output: Path, update_func: UpdateFunc = run_update, history_years: int = 5) -> None:
    while True:
        sleep_seconds = seconds_until_next_run(run_at)
        time.sleep(sleep_seconds)
        run_logged_update("updater", output, update_func)
        if history_years > 0:
            run_logged_history_backfill("updater", history_db_for_output(output), years=history_years)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve Treasury dashboard and run a daily background data update")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8451)
    parser.add_argument("--daily-at", default="16:30", help="Local HH:MM time for daily update")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-start-update", action="store_true")
    parser.add_argument("--history-years", type=int, default=5, help="Years of public history to refresh after each daily update; use 0 to disable")
    parser.add_argument("--once", action="store_true", help="Run one update and exit without serving")
    args = parser.parse_args(argv)

    if args.once:
        run_logged_update("startup", args.output)
        return 0

    if not args.skip_start_update:
        start_startup_update(args.output)

    thread = threading.Thread(target=update_loop, args=(args.daily_at, args.output, run_update, args.history_years), daemon=True)
    thread.start()

    NoStoreHandler.dashboard_output = args.output
    NoStoreHandler.history_db_path = history_db_for_output(args.output)
    handler = functools.partial(NoStoreHandler, directory=str(PROJECT_ROOT))
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {PROJECT_ROOT} at http://{args.host}:{args.port}/", flush=True)
    print(f"Daily update scheduled at local time {args.daily_at}", flush=True)
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
