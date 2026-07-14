"""Versioned dashboard payload contract.

The dashboard intentionally remains a broad JSON document, but producers and
consumers still need a small, stable envelope.  This module keeps that envelope
dependency-free so refresh jobs can reject malformed snapshots before the
atomic publish step.
"""
from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any


CURRENT_SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({CURRENT_SCHEMA_VERSION})

_OPTIONAL_TOP_LEVEL_TYPES: dict[str, type | tuple[type, ...]] = {
    "curve": dict,
    "groups": list,
    "ideas": list,
    "macroLiquidity": dict,
    "macroLiquidityEquity": dict,
    "spyEarlyWarning": dict,
    "equityShortTermRisk": dict,
    "globalLpplRisk": dict,
    "regionalMonitor": dict,
    "sourceStatus": list,
}


def stamp_dashboard_contract(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Stamp the current envelope version in-place and return ``dashboard``."""
    dashboard.setdefault("schemaVersion", CURRENT_SCHEMA_VERSION)
    return dashboard


def dashboard_contract_issues(dashboard: Any) -> list[str]:
    """Return structural envelope violations without duplicating smoke checks."""
    if not isinstance(dashboard, dict):
        return ["dashboard must be an object"]

    issues: list[str] = []
    version = dashboard.get("schemaVersion")
    if not isinstance(version, str) or not version:
        issues.append("schemaVersion must be a non-empty string")
    elif version not in SUPPORTED_SCHEMA_VERSIONS:
        issues.append(f"unsupported schemaVersion: {version}")

    raw_as_of = dashboard.get("asOf")
    parsed_as_of: date | None = None
    if not isinstance(raw_as_of, str) or not raw_as_of.strip():
        issues.append("asOf must be a non-empty string")
    else:
        try:
            parsed_as_of = date.fromisoformat(raw_as_of.strip())
        except ValueError:
            issues.append("asOf must be an ISO date")

    raw_generated_at = dashboard.get("generatedAt")
    parsed_generated_at: datetime | None = None
    if not isinstance(raw_generated_at, str) or not raw_generated_at.strip():
        issues.append("generatedAt must be a non-empty string")
    else:
        try:
            parsed_generated_at = datetime.fromisoformat(raw_generated_at.strip().replace("Z", "+00:00"))
        except ValueError:
            issues.append("generatedAt must be an ISO datetime")
        else:
            if parsed_generated_at.tzinfo is None or parsed_generated_at.utcoffset() is None:
                issues.append("generatedAt must include a timezone")

    if parsed_as_of is not None and parsed_generated_at is not None and parsed_as_of > parsed_generated_at.date():
        issues.append("asOf must not be after generatedAt date")

    source_status = dashboard.get("sourceStatus")
    if source_status is not None and not isinstance(source_status, list):
        issues.append("sourceStatus must be an array when present")

    for key, expected_type in _OPTIONAL_TOP_LEVEL_TYPES.items():
        value = dashboard.get(key)
        if value is not None and not isinstance(value, expected_type):
            issues.append(f"{key} has invalid type {type(value).__name__}")

    curve = dashboard.get("curve")
    if isinstance(curve, dict):
        tenors = curve.get("tenors")
        if tenors is not None and not isinstance(tenors, list):
            issues.append("curve.tenors must be an array")

    try:
        json.dumps(dashboard, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        issues.append(f"dashboard must be strict JSON serializable: {exc}")

    return issues


def require_dashboard_contract(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Stamp and validate a payload, raising before it can be published."""
    stamp_dashboard_contract(dashboard)
    issues = dashboard_contract_issues(dashboard)
    if issues:
        raise ValueError("dashboard contract failed: " + "; ".join(issues))
    return dashboard
