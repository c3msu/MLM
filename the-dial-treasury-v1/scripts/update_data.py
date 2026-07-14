from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import fcntl
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from treasury_data.build_dashboard import (  # noqa: E402
    EQUITY_RISK_SYMBOLS,
    FRED_SERIES,
    annotate_spy_warning_robustness,
    build_live_dashboard,
)
from treasury_data.dashboard_contract import dashboard_contract_issues, stamp_dashboard_contract  # noqa: E402
from treasury_data.history_store import history_db_for_output, save_dashboard_history  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "dashboard.json"
BuildFunc = Callable[[], dict[str, Any]]
FULL_REFRESH_DATA_MODE = "real-public-sources"
REQUIRED_EQUITY_SOURCE_STATUS_NAMES = tuple(f"Nasdaq {symbol} OHLCV" for symbol in EQUITY_RISK_SYMBOLS)
REQUIRED_FRED_SOURCE_STATUS_NAMES = tuple(f"FRED {series_id}" for series_id in FRED_SERIES)
MIN_MACRO_SCORED_FACTORS = 5
MIN_MACRO_EFFECTIVE_WEIGHT_COVERAGE_PCT = 25.0
MAX_REQUIRED_DAILY_SOURCE_LAG_BUSINESS_DAYS = 2
SOURCE_MONITORING_STATUSES = {
    "ok",
    "warning",
    "error",
    "stale",
    "stale-cache",
    "modeled",
    "manual-placeholder",
}
ISO_DATE_PATTERN = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
LAST_KNOWN_GOOD_BLOCKS = (
    "auctions",
    "announcedAuctions",
    "events",
    "news",
    "globalLpplRisk",
    "regionalMonitor",
    "signalValidation",
    "portfolioOverview",
)
LAST_KNOWN_GOOD_SOURCE_NAMES = {
    "auctions": ("TreasuryDirect auctioned securities",),
    "announcedAuctions": ("TreasuryDirect announced securities",),
    "events": (
        "Federal Reserve FOMC calendar",
        "FRED economic release calendar",
        "BEA release schedule",
    ),
    "news": (
        "Federal Reserve press release RSS",
        "U.S. Treasury press releases",
    ),
}
OPTIONAL_LKG_SOURCE_STATUS_NAMES = tuple(
    dict.fromkeys(
        name
        for names in LAST_KNOWN_GOOD_SOURCE_NAMES.values()
        for name in names
    )
)


@contextmanager
def dashboard_update_file_lock(output: Path):
    """Serialize full and partial refreshes across processes.

    The lock file is stable while the published JSON uses unique temporary
    files, so two schedulers cannot race the expensive fetch/build/history
    sequence or replace each other's snapshot.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.parent / f".{output.name}.update.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_dashboard_json(dashboard: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temp_output = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(dashboard, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_output.replace(output)
        try:
            directory_descriptor = os.open(output.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except OSError:
            # Some filesystems do not support fsync on directories. The file itself
            # has already been flushed and atomically replaced.
            pass
    finally:
        temp_output.unlink(missing_ok=True)


def read_dashboard_json(output: Path) -> dict[str, Any] | None:
    if not output.exists():
        return None
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def parse_snapshot_generated_at(value: Any) -> datetime | None:
    """Parse one snapshot timestamp onto a common UTC timeline."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def snapshot_regression_issues(
    candidate: dict[str, Any],
    existing: dict[str, Any] | None,
) -> list[str]:
    """Reject an out-of-order job before it can replace a newer snapshot.

    The cross-process file lock serializes publication, but a job may have been
    built under a skewed clock or queued behind a newer job.  Publication must
    therefore also be monotonic in both build time and top-level observation
    date.
    """

    if not isinstance(existing, dict):
        return []
    issues: list[str] = []
    candidate_generated_at = parse_snapshot_generated_at(candidate.get("generatedAt"))
    existing_generated_at = parse_snapshot_generated_at(existing.get("generatedAt"))
    if (
        candidate_generated_at is not None
        and existing_generated_at is not None
        and candidate_generated_at <= existing_generated_at
    ):
        relation = "equals" if candidate_generated_at == existing_generated_at else "precedes"
        issues.append(
            f"candidate generatedAt {candidate.get('generatedAt')} {relation} "
            f"served generatedAt {existing.get('generatedAt')}"
        )

    candidate_as_of = parse_source_observation_date(candidate.get("asOf"))
    existing_as_of = parse_source_observation_date(existing.get("asOf"))
    if candidate_as_of is not None and existing_as_of is not None and candidate_as_of < existing_as_of:
        issues.append(
            f"candidate asOf {candidate_as_of.isoformat()} precedes served asOf {existing_as_of.isoformat()}"
        )
    return issues


def dashboard_block_is_usable(value: Any) -> bool:
    if isinstance(value, dict) and "available" in value:
        return value.get("available") is True
    return bool(value)


def dashboard_block_needs_last_known_good(dashboard: dict[str, Any], key: str, value: Any) -> bool:
    if isinstance(value, dict) and "available" in value:
        return value.get("available") is not True
    if value is None:
        return True
    if isinstance(value, list):
        expected_names = LAST_KNOWN_GOOD_SOURCE_NAMES.get(key, ())
        if not expected_names:
            return False
        statuses = {
            str(row.get("name") or ""): str(row.get("status") or "").lower()
            for row in dashboard.get("sourceStatus", [])
            if isinstance(row, dict)
        }
        matching = [statuses[name] for name in expected_names if name in statuses]
        monitoring_incomplete = any(name not in statuses for name in expected_names)
        return monitoring_incomplete or any(
            status in {"error", "warning", "stale", "stale-cache"}
            for status in matching
        )
    return isinstance(value, dict) and not value


def available_lppl_symbols(value: Any) -> set[str]:
    if not isinstance(value, dict) or not isinstance(value.get("indices"), list):
        return set()
    return {
        str(row.get("symbol") or "").upper()
        for row in value["indices"]
        if isinstance(row, dict) and row.get("available") is True and row.get("symbol")
    }


def signal_validation_factor_ids(value: Any) -> set[str]:
    if not isinstance(value, dict) or not isinstance(value.get("factors"), list):
        return set()
    return {
        str(row.get("id") or "")
        for row in value["factors"]
        if isinstance(row, dict) and row.get("id")
    }


def signal_validation_source_degraded(dashboard: dict[str, Any]) -> bool:
    degraded = {"error", "warning", "stale", "stale-cache"}
    return any(
        str(row.get("name") or "").startswith("FRED ")
        and str(row.get("status") or "").lower() in degraded
        for row in dashboard.get("sourceStatus", [])
        if isinstance(row, dict)
    )


def merge_last_known_good_blocks(
    dashboard: dict[str, Any],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    """Preserve optional blocks across transient source failures.

    Core score and curve blocks retain their stricter all-snapshot gate.  This
    layer only prevents soft/independent surfaces from disappearing when their
    upstream source has a short outage, and records every borrowed block.
    """
    if not isinstance(existing, dict):
        return dashboard
    borrowed: list[dict[str, Any]] = []
    borrowed_keys: set[str] = set()

    def borrow(key: str) -> None:
        if key in borrowed_keys or not dashboard_block_is_usable(existing.get(key)):
            return
        dashboard[key] = existing[key]
        borrowed_keys.add(key)
        borrowed.append(
            {
                "key": key,
                "sourceGeneratedAt": existing.get("generatedAt"),
                "status": "stale-cache",
            }
        )

    for key in LAST_KNOWN_GOOD_BLOCKS:
        candidate = dashboard.get(key)
        previous = existing.get(key)
        needs_last_known_good = dashboard_block_needs_last_known_good(dashboard, key, candidate)
        if key == "globalLpplRisk" and dashboard_block_is_usable(previous):
            needs_last_known_good = needs_last_known_good or bool(
                available_lppl_symbols(previous) - available_lppl_symbols(candidate)
            )
        if (
            key == "signalValidation"
            and dashboard_block_is_usable(previous)
            and signal_validation_source_degraded(dashboard)
        ):
            needs_last_known_good = needs_last_known_good or bool(
                signal_validation_factor_ids(previous) - signal_validation_factor_ids(candidate)
            )
        if not needs_last_known_good:
            continue
        borrow(key)

    # A full refresh constructs these surfaces from one another.  If an
    # upstream root is borrowed, retain its prior dependents as a coherent set
    # instead of mixing old roots with candidate-derived views.
    if "globalLpplRisk" in borrowed_keys:
        borrow("regionalMonitor")
        borrow("portfolioOverview")
    if "signalValidation" in borrowed_keys:
        borrow("spyEarlyWarning")
    if "signalValidation" in borrowed_keys or "regionalMonitor" in borrowed_keys:
        borrow("portfolioOverview")
    if borrowed:
        dashboard.setdefault("meta", {})["lastKnownGoodBlocks"] = borrowed
    return dashboard


def source_error_rows(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    source_status = dashboard.get("sourceStatus", [])
    if not isinstance(source_status, list):
        return []
    return [
        item
        for item in source_status
        if isinstance(item, dict) and str(item.get("status") or "").strip().lower() == "error"
    ]


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
        if str(row.get("status") or "").strip().lower() != "ok":
            return False
        latest = row.get("latest")
        if not isinstance(latest, str):
            return False
        try:
            date.fromisoformat(latest)
        except ValueError:
            return False
    return True


def parse_dashboard_reference_date(dashboard: dict[str, Any], issues: list[str]) -> date | None:
    """Return the candidate build date used to judge source observations.

    Source freshness is evaluated at the time the snapshot claims it was built,
    rather than against the wall clock alone.  This keeps archived fixtures
    reproducible while preventing a newly generated payload from presenting
    future-dated observations as current.
    """

    raw_generated_at = dashboard.get("generatedAt")
    if not isinstance(raw_generated_at, str):
        issues.append("generatedAt must be an ISO datetime for a full refresh")
        return None
    generated_at_text = raw_generated_at.strip()
    if "T" not in generated_at_text and " " not in generated_at_text:
        issues.append("generatedAt must include an ISO time for a full refresh")
    try:
        parsed = datetime.fromisoformat(generated_at_text.replace("Z", "+00:00"))
    except ValueError:
        issues.append("generatedAt must be an ISO datetime for a full refresh")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        issues.append("generatedAt must include a timezone for a full refresh")
    reference_date = parsed.date()
    if reference_date > date.today():
        issues.append(f"generatedAt date {reference_date.isoformat()} is in the future")

    raw_as_of = dashboard.get("asOf")
    as_of = parse_source_observation_date(raw_as_of)
    if as_of is None:
        issues.append("asOf must be an ISO date for a full refresh")
    else:
        if as_of > reference_date:
            issues.append(
                f"asOf date {as_of.isoformat()} is after generatedAt date {reference_date.isoformat()}"
            )
    return reference_date


def parse_source_observation_date(value: Any, *, embedded: bool = False) -> date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not embedded:
        if ISO_DATE_PATTERN.fullmatch(text) is None:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    match = ISO_DATE_PATTERN.search(text)
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def business_days_between(start: date, end: date) -> int:
    """Count weekdays strictly after ``start`` through ``end``."""

    if end <= start:
        return 0
    count = 0
    cursor = start + timedelta(days=1)
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def required_daily_source_date_issue(
    name: str,
    row: dict[str, Any],
    *,
    reference_date: date | None,
    embedded_date: bool = False,
) -> str | None:
    observation_date = parse_source_observation_date(row.get("latest"), embedded=embedded_date)
    if observation_date is None:
        return f"{name} latest observation is not a valid ISO date"
    if reference_date is None:
        return None
    if observation_date > reference_date:
        return (
            f"{name} latest observation {observation_date.isoformat()} is after "
            f"generatedAt date {reference_date.isoformat()}"
        )
    lag = business_days_between(observation_date, reference_date)
    if lag > MAX_REQUIRED_DAILY_SOURCE_LAG_BUSINESS_DAYS:
        return (
            f"{name} latest observation {observation_date.isoformat()} is {lag} business days old; "
            f"maximum is {MAX_REQUIRED_DAILY_SOURCE_LAG_BUSINESS_DAYS}"
        )
    return None


def full_refresh_source_issues(
    dashboard: dict[str, Any],
    *,
    enforce: bool = False,
) -> list[str]:
    """Validate the required data-plane evidence for a real full refresh.

    Optional public sources may remain warning/error and use their explicit
    last-known-good blocks.  The curve, equity inputs, source-monitoring rows,
    and minimum Conditions Score coverage are different: publishing a new
    timestamp without them would make a degraded build look current.

    Synthetic/unit-test payloads without the real-public-sources data mode keep
    the small generic dashboard contract used by callers outside full refresh.
    """

    meta = dashboard.get("meta")
    if not enforce and (not isinstance(meta, dict) or meta.get("dataMode") != FULL_REFRESH_DATA_MODE):
        return []

    source_status = dashboard.get("sourceStatus")
    if not isinstance(source_status, list) or not source_status:
        return ["sourceStatus must contain full-refresh source rows"]

    issues: list[str] = []
    reference_date = parse_dashboard_reference_date(dashboard, issues)
    rows: dict[str, dict[str, Any]] = {}
    required_names = {
        "U.S. Treasury yield curve XML",
        *REQUIRED_FRED_SOURCE_STATUS_NAMES,
        *REQUIRED_EQUITY_SOURCE_STATUS_NAMES,
        *OPTIONAL_LKG_SOURCE_STATUS_NAMES,
    }
    required_name_counts: dict[str, int] = {}
    for index, row in enumerate(source_status):
        if not isinstance(row, dict):
            issues.append(f"sourceStatus[{index}] must be an object")
            continue
        name = str(row.get("name") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        if not name or not status:
            issues.append(f"sourceStatus[{index}] must include name and status")
            continue
        if status not in SOURCE_MONITORING_STATUSES:
            issues.append(f"sourceStatus[{index}] has unsupported status={status}")
        if name in required_names:
            required_name_counts[name] = required_name_counts.get(name, 0) + 1
        rows.setdefault(name, row)
    for name, count in required_name_counts.items():
        if count > 1:
            issues.append(f"{name} source monitoring row is duplicated")

    curve_name = "U.S. Treasury yield curve XML"
    curve_row = rows.get(curve_name)
    if curve_row is None:
        issues.append(f"{curve_name} status missing")
    else:
        curve_status = str(curve_row.get("status") or "").lower()
        curve_is_fred_fallback = (
            curve_status == "warning"
            and str(curve_row.get("source") or "").lower() == "fred-fallback"
        )
        if curve_status != "ok" and not curve_is_fred_fallback:
            issues.append(f"{curve_name} status={curve_status or 'missing'}")
        curve_date_issue = required_daily_source_date_issue(
            curve_name,
            curve_row,
            reference_date=reference_date,
            embedded_date=curve_is_fred_fallback,
        )
        if curve_date_issue:
            issues.append(curve_date_issue)

    missing_fred_rows = [name for name in REQUIRED_FRED_SOURCE_STATUS_NAMES if name not in rows]
    if missing_fred_rows:
        preview = ", ".join(missing_fred_rows[:4])
        suffix = "..." if len(missing_fred_rows) > 4 else ""
        issues.append(f"FRED source monitoring incomplete: {preview}{suffix}")

    missing_optional_rows = [name for name in OPTIONAL_LKG_SOURCE_STATUS_NAMES if name not in rows]
    if missing_optional_rows:
        preview = ", ".join(missing_optional_rows[:4])
        suffix = "..." if len(missing_optional_rows) > 4 else ""
        issues.append(f"optional source monitoring incomplete: {preview}{suffix}")

    # Individual FRED series are intentionally not all publication blockers:
    # the score's observed-factor coverage gate below decides whether enough
    # current evidence exists.  An "ok" monitoring row must still carry a
    # truthful, non-future observation date.
    for name in REQUIRED_FRED_SOURCE_STATUS_NAMES:
        row = rows.get(name)
        if not isinstance(row, dict) or str(row.get("status") or "").strip().lower() != "ok":
            continue
        observation_date = parse_source_observation_date(row.get("latest"))
        if observation_date is None:
            issues.append(f"{name} latest observation is not a valid ISO date")
        elif reference_date is not None and observation_date > reference_date:
            issues.append(
                f"{name} latest observation {observation_date.isoformat()} is after "
                f"generatedAt date {reference_date.isoformat()}"
            )

    equity_issues: list[str] = []
    for name in REQUIRED_EQUITY_SOURCE_STATUS_NAMES:
        row = rows.get(name)
        if not isinstance(row, dict):
            equity_issues.append(f"{name} status missing")
            continue
        status = str(row.get("status") or "").strip().lower()
        if status != "ok":
            equity_issues.append(f"{name} status={status or 'missing'}")
            continue
        date_issue = required_daily_source_date_issue(name, row, reference_date=reference_date)
        if date_issue:
            equity_issues.append(date_issue)
    if equity_issues:
        issues.append("required equity OHLCV source monitoring is incomplete or degraded: " + "; ".join(equity_issues))

    macro_liquidity = dashboard.get("macroLiquidity")
    if not isinstance(macro_liquidity, dict):
        issues.append("macroLiquidity missing")
    else:
        scored_factor_count = macro_liquidity.get("scoredFactorCount")
        if not isinstance(scored_factor_count, int) or scored_factor_count < MIN_MACRO_SCORED_FACTORS:
            issues.append(
                f"macroLiquidity scoredFactorCount={scored_factor_count!r}; "
                f"minimum is {MIN_MACRO_SCORED_FACTORS}"
            )
        coverage = macro_liquidity.get("effectiveWeightCoveragePct")
        if not isinstance(coverage, (int, float)) or float(coverage) < MIN_MACRO_EFFECTIVE_WEIGHT_COVERAGE_PCT:
            issues.append(
                f"macroLiquidity effectiveWeightCoveragePct={coverage!r}; "
                f"minimum is {MIN_MACRO_EFFECTIVE_WEIGHT_COVERAGE_PCT:g}"
            )
    return issues


def failed_output_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}.failed{output.suffix}")


def write_failed_dashboard_json(dashboard: dict[str, Any], output: Path) -> Path:
    """Keep the newest rejected candidate when queued jobs finish out of order."""

    path = failed_output_path(output)
    previous = read_dashboard_json(path)
    candidate_generated_at = parse_snapshot_generated_at(dashboard.get("generatedAt"))
    previous_generated_at = parse_snapshot_generated_at(previous.get("generatedAt")) if previous else None
    if previous_generated_at is not None and (
        candidate_generated_at is None or candidate_generated_at < previous_generated_at
    ):
        return path
    write_dashboard_json(dashboard, path)
    return path


def _run_update_unlocked(
    output: Path = DEFAULT_OUTPUT,
    build_func: BuildFunc = build_live_dashboard,
    history_path: Path | None = None,
    save_history: bool = True,
) -> dict[str, Any]:
    dashboard = build_func()
    stamp_dashboard_contract(dashboard)
    existing = read_dashboard_json(output)
    contract_issues = dashboard_contract_issues(dashboard)
    if contract_issues:
        write_failed_dashboard_json(dashboard, output)
        if existing is not None:
            return existing
        raise ValueError("dashboard contract failed: " + "; ".join(contract_issues))
    regression_issues = snapshot_regression_issues(dashboard, existing)
    if regression_issues and dashboard != existing:
        dashboard.setdefault("meta", {})["refreshGate"] = {
            "status": "rejected",
            "issues": regression_issues,
        }
        write_failed_dashboard_json(dashboard, output)
        return existing if existing is not None else dashboard
    if dashboard == existing:
        return existing
    merge_last_known_good_blocks(dashboard, existing)
    annotate_spy_warning_robustness(dashboard.get("spyEarlyWarning"), dashboard.get("signalValidation"))
    merged_contract_issues = dashboard_contract_issues(dashboard)
    if merged_contract_issues:
        write_failed_dashboard_json(dashboard, output)
        if existing is not None:
            return existing
        raise ValueError("dashboard contract failed after last-known-good merge: " + "; ".join(merged_contract_issues))
    source_issues = full_refresh_source_issues(
        dashboard,
        enforce=build_func is build_live_dashboard,
    )
    if source_issues:
        dashboard.setdefault("meta", {})["refreshGate"] = {
            "status": "rejected",
            "issues": source_issues,
        }
        write_failed_dashboard_json(dashboard, output)
        if existing is not None:
            return existing
        raise ValueError("full refresh source gate failed: " + "; ".join(source_issues))
    if existing is not None and dashboard_has_core_content(existing) and not dashboard_has_core_content(dashboard):
        write_failed_dashboard_json(dashboard, output)
        return existing
    if (
        existing is not None
        and dashboard_has_equity_source_monitoring(existing)
        and not dashboard_has_equity_source_monitoring(dashboard)
    ):
        write_failed_dashboard_json(dashboard, output)
        return existing
    if source_error_rows(dashboard) and existing is not None and not source_error_rows(existing):
        write_failed_dashboard_json(dashboard, output)
        if not dashboard_has_core_content(dashboard):
            return existing
    if save_history:
        try:
            save_dashboard_history(dashboard, history_path or history_db_for_output(output))
        except Exception as exc:
            dashboard.setdefault("meta", {})["refreshGate"] = {
                "status": "rejected",
                "issues": [f"history persistence failed: {exc}"],
            }
            try:
                write_failed_dashboard_json(dashboard, output)
            except Exception:  # noqa: BLE001 - preserve the original persistence failure
                pass
            raise
    write_dashboard_json(dashboard, output)
    return dashboard


def run_update(
    output: Path = DEFAULT_OUTPUT,
    build_func: BuildFunc = build_live_dashboard,
    history_path: Path | None = None,
    save_history: bool = True,
) -> dict[str, Any]:
    with dashboard_update_file_lock(output):
        return _run_update_unlocked(
            output,
            build_func=build_func,
            history_path=history_path,
            save_history=save_history,
        )


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
