from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any

from .dashboard_contract import (
    dashboard_contract_issues,
    dashboard_decision_contract_issues,
)
from .scoring_regional import (
    regional_allocation_qualifies_as_actionable,
    regional_factor_alert_qualifies_as_actionable,
)


API_ROUTES = {
    "/api/dashboard": None,
    "/api/health": "__health__",
    "/api/curve": "curve",
    "/api/decomposition": "decomposition",
    "/api/fed_path": "fedPath",
    "/api/scorecard": "groups",
    "/api/policy": "policy",
    "/api/auctions": "auctions",
    "/api/positioning": "positioning",
    "/api/cross": "cross",
    "/api/percentiles": "percentiles",
    "/api/events": "events",
    "/api/news": "news",
    "/api/ideas": "ideas",
    "/api/spy_early_warning": "spyEarlyWarning",
    "/api/equity_short_term_risk": "equityShortTermRisk",
    "/api/source_status": "sourceStatus",
    "/api/source-status": "sourceStatus",
}

LIST_HEADERS = {
    "events": ["date", "title", "importance"],
    "news": ["date", "source", "text"],
}


def api_payload_for_path(dashboard: dict[str, Any], path: str, params: dict[str, list[str]] | None = None) -> tuple[int, Any]:
    normalized = path.rstrip("/") or path
    if normalized not in API_ROUTES:
        return 404, {"error": "unknown api route"}
    key = API_ROUTES[normalized]
    if key is None:
        return 200, dashboard
    if key == "__health__":
        return 200, build_health_payload(dashboard)
    payload = dashboard.get(key, [])
    return 200, apply_query_params(payload, params or {})


def build_health_payload(dashboard: dict[str, Any]) -> dict[str, Any]:
    source_status = dashboard.get("sourceStatus", [])
    counts: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    if isinstance(source_status, list):
        for item in source_status:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
            if status == "error":
                errors.append(item)
    full_contract_available = isinstance(dashboard.get("schemaVersion"), str)
    contract_issues = (
        dashboard_contract_issues(dashboard)
        if full_contract_available
        else dashboard_decision_contract_issues(dashboard)
    )
    return {
        "status": "degraded" if errors or contract_issues else "ok",
        "schemaVersion": dashboard.get("schemaVersion"),
        "asOf": dashboard.get("asOf"),
        "generatedAt": dashboard.get("generatedAt"),
        "sourceCounts": counts,
        "errors": errors,
        "dashboardContract": {
            "valid": not contract_issues,
            "scope": "full" if full_contract_available else "decision-only",
            "issues": contract_issues,
        },
        "regionalAlerts": regional_alerts_health(dashboard.get("regionalMonitor")),
    }


def regional_alerts_health(regional_monitor: Any) -> dict[str, Any]:
    """Compact regional breach + rotation digest for /api/health polling/push."""
    if not isinstance(regional_monitor, dict) or not regional_monitor.get("available"):
        return {"available": False, "breached": [], "reduceRegions": [], "favorRegions": []}
    regions = regional_monitor.get("regions", []) if isinstance(regional_monitor.get("regions"), list) else []
    breached: list[dict[str, Any]] = []
    actionable_regions: dict[str, dict[str, Any]] = {}
    for region in regions:
        if not isinstance(region, dict):
            continue
        key = str(region.get("key") or "")
        if regional_allocation_qualifies_as_actionable(region):
            actionable_regions[key] = region
        alert = region.get("factorAlert") if isinstance(region.get("factorAlert"), dict) else {}
        if (
            key in actionable_regions
            and regional_factor_alert_qualifies_as_actionable(region)
        ):
            breached.append(
                {
                    "key": key,
                    "nameCn": str(region.get("nameCn") or region.get("name") or region.get("key")),
                    "factorLabelCn": str(alert.get("factorLabelCn") or ""),
                    "current": alert.get("current"),
                    "threshold": alert.get("threshold"),
                }
            )
    rotation = regional_monitor.get("rotation", {}) if isinstance(regional_monitor.get("rotation"), dict) else {}
    reduce_regions = [
        key
        for key, region in actionable_regions.items()
        if (region.get("allocation") or {}).get("stance") == "underweight"
    ]
    favor_regions = [
        key
        for key, region in actionable_regions.items()
        if (region.get("allocation") or {}).get("stance") == "overweight"
    ]
    raw_declared_reduce = rotation.get("reduceRegions")
    raw_declared_favor = rotation.get("favorRegions")
    declared_reduce = [str(key) for key in raw_declared_reduce] if isinstance(raw_declared_reduce, list) else []
    declared_favor = [str(key) for key in raw_declared_favor] if isinstance(raw_declared_favor, list) else []
    legacy_actions_present = bool(declared_reduce or declared_favor)
    declared_actions_match = bool(
        set(declared_reduce) == set(reduce_regions)
        and set(declared_favor) == set(favor_regions)
    )
    summary = str(rotation.get("summary") or "")
    if legacy_actions_present and not declared_actions_match:
        if reduce_regions or favor_regions:
            name_by_key = {
                key: str(region.get("nameCn") or region.get("name") or key)
                for key, region in actionable_regions.items()
            }
            parts: list[str] = []
            if favor_regions:
                parts.append("增持" + "、".join(name_by_key[key] for key in favor_regions))
            if reduce_regions:
                parts.append("减持" + "、".join(name_by_key[key] for key in reduce_regions))
            summary = "区域生产动作: " + "; ".join(parts) + "。仅包含完整当前触发审计。"
        else:
            summary = "区域研究读数存在,但缺少完整生产动作审计; 不发布轮动或突破指令。"
    return {
        "available": True,
        "actionable": bool(reduce_regions or favor_regions or breached),
        "scoreUse": "production_signal" if (reduce_regions or favor_regions or breached) else "research_only",
        "asOf": regional_monitor.get("asOf"),
        "breachCount": len(breached),
        "breached": breached,
        "reduceRegions": reduce_regions,
        "favorRegions": favor_regions,
        "summary": summary,
    }


def api_response_for_path(
    dashboard: dict[str, Any],
    path: str,
    params: dict[str, list[str]] | None = None,
) -> tuple[int, bytes, str]:
    status, payload = api_payload_for_path(dashboard, path, params)
    if status == 200 and first_param(params or {}, "format") == "csv":
        return status, payload_to_csv(payload, route_key_for_path(path)).encode("utf-8"), "text/csv; charset=utf-8"
    return (
        status,
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        "application/json; charset=utf-8",
    )


def route_key_for_path(path: str) -> str | None:
    return API_ROUTES.get(path.rstrip("/") or path)


def apply_query_params(payload: Any, params: dict[str, list[str]]) -> Any:
    start = parse_date_param(params, "from")
    end = parse_date_param(params, "to")
    if (start or end) and isinstance(payload, list):
        return [record for record in payload if record_in_date_range(record, start, end)]
    return payload


def record_in_date_range(record: Any, start: date | None, end: date | None) -> bool:
    record_day = record_date(record)
    if record_day is None:
        return False
    if start and record_day < start:
        return False
    if end and record_day > end:
        return False
    return True


def record_date(record: Any) -> date | None:
    value: Any = None
    if isinstance(record, dict):
        value = record.get("date") or record.get("asOf")
    elif isinstance(record, (list, tuple)) and record:
        value = record[0]
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_date_param(params: dict[str, list[str]], name: str) -> date | None:
    value = first_param(params, name)
    if not value:
        return None
    return date.fromisoformat(value)


def first_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    if not values:
        return None
    return values[0]


def payload_to_csv(payload: Any, route_key: str | None = None) -> str:
    output = io.StringIO()
    if isinstance(payload, dict) and is_curve_payload(payload):
        write_curve_csv(output, payload)
    elif isinstance(payload, list):
        write_list_csv(output, payload, route_key)
    elif isinstance(payload, dict):
        writer = csv.writer(output)
        writer.writerow(["key", "value"])
        for key, value in payload.items():
            writer.writerow([key, json.dumps(value, ensure_ascii=False, sort_keys=True)])
    else:
        writer = csv.writer(output)
        writer.writerow(["value"])
        writer.writerow([payload])
    return output.getvalue()


def is_curve_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("tenors"), list)


def write_curve_csv(output: io.StringIO, payload: dict[str, Any]) -> None:
    fields = ["today", "w1", "m1", "d1"]
    writer = csv.writer(output)
    writer.writerow(["tenor", *fields])
    for index, tenor in enumerate(payload.get("tenors", [])):
        row = [tenor]
        for field in fields:
            values = payload.get(field, [])
            row.append(values[index] if isinstance(values, list) and index < len(values) else "")
        writer.writerow(row)


def write_list_csv(output: io.StringIO, payload: list[Any], route_key: str | None) -> None:
    if not payload:
        writer = csv.writer(output)
        writer.writerow(LIST_HEADERS.get(route_key or "", ["value"]))
        return
    first_row = payload[0]
    if isinstance(first_row, dict):
        fieldnames = list(first_row.keys())
        for row in payload[1:]:
            if isinstance(row, dict):
                for key in row:
                    if key not in fieldnames:
                        fieldnames.append(key)
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in payload:
            writer.writerow(row if isinstance(row, dict) else {"value": row})
        return
    headers = LIST_HEADERS.get(route_key or "")
    if not headers:
        width = len(first_row) if isinstance(first_row, (list, tuple)) else 1
        headers = [f"col{i + 1}" for i in range(width)]
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in payload:
        writer.writerow(row if isinstance(row, (list, tuple)) else [row])
