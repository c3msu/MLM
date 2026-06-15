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


def format_regional_alerts(payload: dict[str, Any]) -> tuple[int, str]:
    """Exit 0 when no region's validated leading signal has breached its threshold;
    exit 1 when one or more have, with a one-line digest per breached region."""
    regional = payload.get("regionalAlerts")
    if not isinstance(regional, dict) or not regional.get("available"):
        return 0, "REGIONAL OK (no regional monitor data)"
    breached = regional.get("breached", [])
    breached = breached if isinstance(breached, list) else []
    as_of = payload.get("asOf", "unknown")
    if not breached:
        reduce_regions = regional.get("reduceRegions", []) or []
        tail = f" reduce={','.join(str(k) for k in reduce_regions)}" if reduce_regions else ""
        return 0, f"REGIONAL OK asOf={as_of} no factor breaches{tail}"
    lines = [f"REGIONAL BREACH asOf={as_of} {len(breached)} region(s)"]
    for item in breached:
        if not isinstance(item, dict):
            continue
        name = item.get("nameCn") or item.get("key") or "?"
        factor = item.get("factorLabelCn", "")
        current = item.get("current")
        threshold = item.get("threshold")
        lines.append(f"- {name}: {factor} {current} > 阈值 {threshold}")
    return 1, "\n".join(lines)


def notify_macos(title: str, message: str) -> None:
    script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def main(
    argv: list[str] | None = None,
    *,
    fetcher: Fetcher = fetch_health,
    notifier: Notifier = notify_macos,
) -> int:
    parser = argparse.ArgumentParser(description="Check regional validated-factor breach alerts from the health endpoint")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--notify", action="store_true", help="Show a macOS notification when a region breaches")
    args = parser.parse_args(argv)

    try:
        payload = fetcher(args.url, args.timeout)
    except Exception as exc:  # noqa: BLE001
        message = f"UNREACHABLE {args.url}: {exc}"
        print(message)
        if args.notify:
            notifier("Regional alerts unreachable", message)
        return 3

    exit_code, message = format_regional_alerts(payload)
    print(message)
    if exit_code == 1 and args.notify:
        notifier("地区因子突破告警", message)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
