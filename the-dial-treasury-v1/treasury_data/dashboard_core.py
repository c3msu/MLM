"""Shared leaf utilities extracted from build_dashboard.py (behavior-unchanged,
2026-06-19 全面重构 Phase 1). Pure formatting/coercion helpers with no domain logic.
Re-exported by build_dashboard via `from .dashboard_core import *`."""
from __future__ import annotations

import math


def _float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_optional_percent_value(value: object) -> str:
    numeric = optional_float(value)
    return "--" if numeric is None else f"{numeric:.1f}%"


def pct_metric(value: float | None) -> float | None:
    return round(float(value) * 100, 2) if value is not None and math.isfinite(float(value)) else None


def bounded_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def optional_float(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def format_signed_number(value: float | None, *, digits: int = 2) -> str:
    if value is None:
        return "--"
    return f"{value:+.{digits}f}"


def bucket_label_by_rank(rows: list[dict[str, Any]], key: str, value: float | None, labels: list[str]) -> str:
    if value is None or not rows:
        return labels[1]
    values = [optional_float(row.get(key)) for row in rows]
    values = sorted(item for item in values if item is not None)
    if not values:
        return labels[1]
    rank = sum(1 for item in values if item <= value) / len(values)
    if rank <= 1 / 3:
        return labels[0]
    if rank <= 2 / 3:
        return labels[1]
    return labels[2]


# Shared signal-validation config scalars (2026-06-19 Phase 1: moved down from the monolith;
# used by the spy-warning backtest, signal validation, regional, and equity layers).
SIGNAL_VALIDATION_MIN_WEEKS = 60
SIGNAL_VALIDATION_DRAWDOWN_PCT = -5.0
SIGNAL_VALIDATION_DRAWDOWN_DAYS = 91
SIGNAL_VALIDATION_EQUITY_DRAWDOWN_PCT = -2.0
SIGNAL_VALIDATION_EQUITY_DRAWDOWN_DAYS = 10
SIGNAL_VALIDATION_OOS_SPLIT = 0.65
