"""Shared parsing and display formatting for dashboard builders.

Kept dependency-light so domain builders can reuse these helpers without importing
the build_dashboard compatibility facade.
"""
from __future__ import annotations

import math
from datetime import date, datetime

from .sources import QuarterlyRefunding


__all__ = [
    "compact_int",
    "direction_word",
    "format_yield",
    "money_billions_value",
    "money_from_millions",
    "money_trillions_from_billions",
    "parse_dashboard_date",
    "parse_number",
    "qra_supply_note",
]


def parse_number(raw: object) -> float | None:
    if raw is None:
        return None
    try:
        value = float(str(raw).replace(",", "").strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse_dashboard_date(raw: object) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None

def format_yield(raw: str) -> str:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return "--"
    return f"{value:.3f}%" if math.isfinite(value) else "--"

def money_billions_value(value: float | None) -> str:
    if value is None:
        return "--"
    return f"${value:.0f}B"


def qra_supply_note(refunding: QuarterlyRefunding) -> str:
    parts = [f"官方QRA {refunding.release_date.isoformat()}"]
    if refunding.current_quarter_borrowing_billions is not None:
        parts.append(f"本季借款 {money_billions_value(refunding.current_quarter_borrowing_billions)}")
    if refunding.next_quarter_borrowing_billions is not None:
        parts.append(f"下季借款 {money_billions_value(refunding.next_quarter_borrowing_billions)}")
    if refunding.refunding_new_cash_billions is not None:
        parts.append(f"refunding新现金 {money_billions_value(refunding.refunding_new_cash_billions)}")
    if refunding.coupon_stance:
        parts.append(refunding.coupon_stance)
    return "; ".join(parts)

def direction_word(value: float) -> str:
    return "多" if value >= 0 else "空"


def compact_int(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def money_trillions_from_billions(value: float) -> str:
    return f"${value / 1_000:.2f}T"


def money_from_millions(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}T"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}B"
    return f"${value:.0f}M"
