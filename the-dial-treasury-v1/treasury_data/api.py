from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any


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
    return {
        "status": "degraded" if errors else "ok",
        "asOf": dashboard.get("asOf"),
        "generatedAt": dashboard.get("generatedAt"),
        "sourceCounts": counts,
        "errors": errors,
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
