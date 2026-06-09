from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from treasury_data.build_dashboard import EQUITY_RISK_SYMBOLS, build_live_dashboard  # noqa: E402
from treasury_data.history_store import history_db_for_output, save_dashboard_history  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "dashboard.json"
BuildFunc = Callable[[], dict[str, Any]]
REQUIRED_EQUITY_SOURCE_STATUS_NAMES = tuple(f"Nasdaq {symbol} OHLCV" for symbol in EQUITY_RISK_SYMBOLS)


def write_dashboard_json(dashboard: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(f".{output.name}.tmp")
    temp_output.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_output.replace(output)


def read_dashboard_json(output: Path) -> dict[str, Any] | None:
    if not output.exists():
        return None
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def source_error_rows(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    source_status = dashboard.get("sourceStatus", [])
    if not isinstance(source_status, list):
        return []
    return [item for item in source_status if isinstance(item, dict) and item.get("status") == "error"]


def dashboard_has_core_content(dashboard: dict[str, Any]) -> bool:
    curve = dashboard.get("curve")
    groups = dashboard.get("groups")
    macro_liquidity = dashboard.get("macroLiquidity")
    trend = macro_liquidity.get("trend") if isinstance(macro_liquidity, dict) else None
    trend_points = trend.get("points") if isinstance(trend, dict) else None
    equity_short_term_risk = dashboard.get("equityShortTermRisk")
    return (
        isinstance(curve, dict)
        and isinstance(curve.get("tenors"), list)
        and len(curve.get("tenors", [])) > 0
        and isinstance(groups, list)
        and len(groups) > 0
        and isinstance(macro_liquidity, dict)
        and isinstance(macro_liquidity.get("score"), (int, float))
        and isinstance(trend, dict)
        and trend.get("available") is True
        and isinstance(trend_points, list)
        and len(trend_points) >= 2
        and dashboard_has_equity_short_term_risk_content(equity_short_term_risk)
    )


def dashboard_has_equity_short_term_risk_content(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("available") is not True:
        return False
    score = payload.get("score")
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 100:
        return False
    trend = payload.get("trend")
    points = trend.get("points") if isinstance(trend, dict) else None
    if not isinstance(points, list) or len(points) < 2:
        return False
    backtest = payload.get("backtest")
    if not isinstance(backtest, dict) or backtest.get("available") is not True:
        return False
    if not isinstance(backtest.get("sampleSize"), int):
        return False
    for key in ("scoreBuckets", "thresholdTests", "regressionTests", "worstWindows"):
        if not isinstance(backtest.get(key), list):
            return False
    component_diagnostics = backtest.get("componentDiagnostics")
    if not isinstance(component_diagnostics, list) or not component_diagnostics:
        return False
    guard = payload.get("lookAheadGuard")
    return isinstance(guard, dict) and isinstance(guard.get("dataThrough"), str) and bool(guard.get("dataThrough"))


def dashboard_has_equity_source_monitoring(dashboard: dict[str, Any]) -> bool:
    source_status = dashboard.get("sourceStatus")
    if not isinstance(source_status, list):
        return False
    rows = {
        str(row.get("name") or ""): row
        for row in source_status
        if isinstance(row, dict)
    }
    for name in REQUIRED_EQUITY_SOURCE_STATUS_NAMES:
        row = rows.get(name)
        if not isinstance(row, dict):
            return False
        if row.get("status") != "ok":
            return False
        latest = row.get("latest")
        if not isinstance(latest, str) or not latest or latest == "none":
            return False
    return True


def failed_output_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}.failed{output.suffix}")


def run_update(
    output: Path = DEFAULT_OUTPUT,
    build_func: BuildFunc = build_live_dashboard,
    history_path: Path | None = None,
    save_history: bool = True,
) -> dict[str, Any]:
    dashboard = build_func()
    existing = read_dashboard_json(output)
    if existing is not None and dashboard_has_core_content(existing) and not dashboard_has_core_content(dashboard):
        write_dashboard_json(dashboard, failed_output_path(output))
        return existing
    if (
        existing is not None
        and dashboard_has_equity_source_monitoring(existing)
        and not dashboard_has_equity_source_monitoring(dashboard)
    ):
        write_dashboard_json(dashboard, failed_output_path(output))
        return existing
    if source_error_rows(dashboard) and existing is not None and not source_error_rows(existing):
        write_dashboard_json(dashboard, failed_output_path(output))
        if not dashboard_has_core_content(dashboard):
            return existing
    write_dashboard_json(dashboard, output)
    if save_history:
        save_dashboard_history(dashboard, history_path or history_db_for_output(output))
    return dashboard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch real public data and write dashboard.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--history-db", type=Path, default=None, help="SQLite history database path; defaults beside output")
    parser.add_argument("--no-history", action="store_true", help="Do not persist this refresh into SQLite history")
    args = parser.parse_args(argv)
    dashboard = run_update(args.output, history_path=args.history_db, save_history=not args.no_history)
    print(f"Wrote {args.output} with asOf={dashboard['asOf']} generatedAt={dashboard['generatedAt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
