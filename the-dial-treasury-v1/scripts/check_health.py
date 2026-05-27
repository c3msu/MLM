from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any, Callable
from urllib.request import urlopen


DEFAULT_URL = "http://127.0.0.1:8451/api/health"

Fetcher = Callable[[str, float], dict[str, Any]]
Notifier = Callable[[str, str], None]


def fetch_health(url: str, timeout: float) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("health endpoint did not return a JSON object")
    return payload


def source_counts_text(source_counts: dict[str, Any]) -> str:
    return " ".join(f"{key}={source_counts[key]}" for key in sorted(source_counts))


def format_health(payload: dict[str, Any]) -> tuple[int, str]:
    status = str(payload.get("status", "unknown"))
    source_counts = payload.get("sourceCounts", {})
    if not isinstance(source_counts, dict):
        source_counts = {}
    generated_at = payload.get("generatedAt", "unknown")
    as_of = payload.get("asOf", "unknown")
    history = payload.get("history", {})
    history_text = history_backfill_text(history if isinstance(history, dict) else {})
    headline = f"{status.upper()} asOf={as_of} generatedAt={generated_at} sources {source_counts_text(source_counts)} {history_text}".strip()
    errors = payload.get("errors", [])
    warnings = payload.get("warnings", [])
    if status == "ok" and not errors and not warnings:
        return 0, headline
    lines = [headline]
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name', 'unknown')}: {item.get('latest', '')}")
    if isinstance(warnings, list):
        for item in warnings:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name', 'unknown')}: {item.get('latest', '')}")
    return 2, "\n".join(lines)


def history_backfill_text(history: dict[str, Any]) -> str:
    latest_backfill = history.get("latestBackfill")
    if not isinstance(latest_backfill, dict):
        return ""
    status = latest_backfill.get("status", "unknown")
    saved = latest_backfill.get("savedObservationCount", "unknown")
    end_date = latest_backfill.get("endDate", "unknown")
    return f"historyBackfill={status} saved={saved} endDate={end_date}"


def notify_macos(title: str, message: str) -> None:
    script = f'display notification {json.dumps(message)} with title {json.dumps(title)}'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def main(
    argv: list[str] | None = None,
    *,
    fetcher: Fetcher = fetch_health,
    notifier: Notifier = notify_macos,
) -> int:
    parser = argparse.ArgumentParser(description="Check the local Treasury dashboard health endpoint")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--notify", action="store_true", help="Show a macOS notification when health is not OK")
    args = parser.parse_args(argv)

    try:
        payload = fetcher(args.url, args.timeout)
    except Exception as exc:  # noqa: BLE001
        message = f"UNREACHABLE {args.url}: {exc}"
        print(message)
        if args.notify:
            notifier("Treasury dashboard unreachable", message)
        return 3

    exit_code, message = format_health(payload)
    print(message)
    if exit_code and args.notify:
        notifier("Treasury dashboard degraded", message)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
