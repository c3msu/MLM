"""Per-index LPPL row, history, CLIP, and backtest orchestration.

The row builder is injectable so the dashboard facade can preserve its existing
patch/test seam without this lower layer importing the facade.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from .dashboard_core import bounded_score, optional_float, pct_metric
from .scoring_equity import normalize_market_bars
from .scoring_lppl import GLOBAL_LPPL_MIN_OBSERVATIONS, fit_global_lppl_signal, lppl_percentile
from .scoring_lppl_validation import build_global_lppl_backtest, global_lppl_status
from .series_math import bar_index_at_or_before
from .sources import MarketDailyBar


GLOBAL_LPPL_HISTORY_STEP = 1
GLOBAL_LPPL_CRITICAL_DATE_APPROXIMATION = (
    "US business-day approximation (Mon-Fri; exchange holidays are not modeled)"
)
LpplIndexRowBuilder = Callable[..., dict[str, Any]]
LpplHistoryPointsBuilder = Callable[[str, list[MarketDailyBar]], list[dict[str, Any]]]


def approximate_us_session_date(start: date, sessions: int) -> date:
    """Advance by weekday sessions without pretending they are calendar days.

    The LPPL fit is indexed by market observations, so its ``tc`` offset is a
    session count. This stdlib-only approximation excludes weekends; the
    payload explicitly discloses that exchange holidays are not modeled.
    """
    if sessions < 0:
        raise ValueError("sessions must be non-negative")
    current = start
    remaining = sessions
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def global_lppl_index_row(
    spec: dict[str, Any],
    bars: list[MarketDailyBar],
    *,
    as_of: date | None = None,
    fast: bool = False,
) -> dict[str, Any]:
    symbol = str(spec.get("symbol") or "").upper()
    clean = normalize_market_bars({symbol: bars}).get(symbol, [])
    target_index = bar_index_at_or_before(clean, as_of) if as_of else (len(clean) - 1 if clean else None)
    common = {
        "symbol": symbol,
        "name": str(spec.get("name") or symbol),
        "region": str(spec.get("region") or ""),
        "regionKey": str(spec.get("regionKey") or ""),
        "regionName": str(spec.get("regionName") or spec.get("region") or ""),
        "regionNameCn": str(spec.get("regionNameCn") or ""),
        "proxyNote": str(spec.get("proxyNote") or ""),
        "proxyNoteCn": str(spec.get("proxyNoteCn") or ""),
        "source": str(spec.get("source") or ""),
        "sourceSymbol": str(spec.get("sourceSymbol") or symbol),
        "sourceQuality": str(spec.get("sourceQuality") or "low"),
    }
    if target_index is None or target_index + 1 < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {
            **common,
            "available": False,
            "score": None,
            "confidence": 0.0,
            "status": "missing",
            "statusCn": "缺失",
            "criticalDate": None,
            "daysToCritical": None,
            "sessionsToCritical": None,
            "calendarDaysToCritical": None,
            "criticalDateApproximation": None,
            "fitR2": None,
            "windowDays": None,
            "observations": len(clean),
            "reason": "source unavailable or sample shorter than LPPL minimum window",
        }
    fit = fit_global_lppl_signal(clean[: target_index + 1], fast=fast)
    latest = clean[target_index]
    if not fit.get("available"):
        return {
            **common,
            "available": False,
            "score": None,
            "confidence": 0.0,
            "status": "missing",
            "statusCn": "缺失",
            "criticalDate": None,
            "daysToCritical": None,
            "sessionsToCritical": None,
            "calendarDaysToCritical": None,
            "criticalDateApproximation": None,
            "fitR2": None,
            "windowDays": None,
            "observations": target_index + 1,
            "asOf": latest.date.isoformat(),
            "reason": str(fit.get("reason") or "LPPL fit unavailable"),
        }
    score = bounded_score(float(fit["score"]))
    confidence = max(0.0, min(1.0, float(fit.get("confidence") or 0.0)))
    status, status_cn = global_lppl_status(score, confidence)
    sessions_to_critical = int(fit["daysToCritical"])
    critical_date = approximate_us_session_date(latest.date, sessions_to_critical)
    calendar_days_to_critical = (critical_date - latest.date).days
    return {
        **common,
        "available": True,
        "score": round(score, 1),
        "confidence": round(confidence, 2),
        "status": status,
        "statusCn": status_cn,
        "criticalDate": critical_date.isoformat(),
        # Compatibility alias: historically named "days", but the LPPL model
        # advances in observed market sessions, not calendar days.
        "daysToCritical": sessions_to_critical,
        "sessionsToCritical": sessions_to_critical,
        "calendarDaysToCritical": calendar_days_to_critical,
        "criticalDateApproximation": GLOBAL_LPPL_CRITICAL_DATE_APPROXIMATION,
        "daysToCriticalRange": fit.get("daysToCriticalRange"),
        "sessionsToCriticalRange": fit.get("daysToCriticalRange"),
        "fitR2": round(float(fit["fitR2"]), 3),
        "fitSse": round(float(fit.get("fitSse") or 0.0), 6),
        "lpplImprovementPct": round(float(fit.get("lpplImprovementPct") or 0.0), 1),
        "oscillationCount": round(float(fit.get("oscillationCount") or 0.0), 2),
        "passesLpplCoreDiagnostics": bool(fit.get("passesLpplCoreDiagnostics")),
        "passesLpplDiagnostics": bool(fit.get("passesLpplDiagnostics")),
        "residualDiagnostics": fit.get("residualDiagnostics"),
        "fitEnsemble": fit.get("fitEnsemble"),
        "windowDays": int(fit["windowDays"]),
        "windowDaysRange": fit.get("windowDaysRange"),
        "selectionBasis": str(fit.get("selectionBasis") or "fit_quality"),
        "observations": target_index + 1,
        "asOf": latest.date.isoformat(),
        "weight": float(spec.get("weight") or 0.0),
        "trailingReturn63d": pct_metric(fit.get("trailingReturn63d")),
        "acceleration": pct_metric(fit.get("acceleration")),
        "bubbleCoefficient": round(float(fit.get("bubbleCoefficient") or 0.0), 4),
        "oscillationAmplitude": round(float(fit.get("oscillationAmplitude") or 0.0), 4),
        "reason": str(fit.get("reason") or ""),
    }


def build_single_index_lppl_history_points(
    symbol: str,
    bars: list[MarketDailyBar],
    *,
    row_builder: LpplIndexRowBuilder = global_lppl_index_row,
) -> list[dict[str, Any]]:
    if len(bars) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return []
    points: list[dict[str, Any]] = []
    start_index = GLOBAL_LPPL_MIN_OBSERVATIONS - 1
    replay_indices = list(range(start_index, len(bars), max(1, GLOBAL_LPPL_HISTORY_STEP)))
    if replay_indices[-1] != len(bars) - 1:
        replay_indices.append(len(bars) - 1)
    spec = {
        "symbol": symbol,
        "name": symbol,
        "region": symbol,
        "sourceQuality": "validation",
        "sourceSymbol": symbol,
    }
    for index in replay_indices:
        target = bars[index].date
        row = row_builder(spec, bars, as_of=target, fast=True)
        score = optional_float(row.get("score"))
        if row.get("available") and score is not None:
            point = {"date": target.isoformat(), "score": round(bounded_score(score), 1)}
            for key in (
                "criticalDate",
                "daysToCritical",
                "sessionsToCritical",
                "calendarDaysToCritical",
                "criticalDateApproximation",
                "sessionsToCriticalRange",
                "passesLpplCoreDiagnostics",
                "passesLpplDiagnostics",
                "lpplImprovementPct",
                "oscillationCount",
            ):
                if key in row:
                    point[key] = row[key]
            points.append(point)
    return points


def build_global_lppl_per_index_histories(
    index_rows: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
    *,
    row_builder: LpplIndexRowBuilder = global_lppl_index_row,
    history_points_builder: LpplHistoryPointsBuilder | None = None,
) -> dict[str, Any]:
    histories: dict[str, Any] = {}
    for row in index_rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        histories[symbol] = build_global_lppl_single_index_history(
            row,
            bars_by_symbol.get(symbol, []),
            row_builder=row_builder,
            history_points_builder=history_points_builder,
        )
    return histories


def build_global_lppl_single_index_history(
    index_row: dict[str, Any],
    bars: list[MarketDailyBar],
    *,
    row_builder: LpplIndexRowBuilder = global_lppl_index_row,
    history_points_builder: LpplHistoryPointsBuilder | None = None,
) -> dict[str, Any]:
    symbol = str(index_row.get("symbol") or "").upper()
    clean = normalize_market_bars({symbol: bars}).get(symbol, [])
    if len(clean) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {
            "available": False,
            "symbol": symbol,
            "points": [],
            "summary": "source unavailable or sample shorter than LPPL minimum window",
        }
    score_points = (
        history_points_builder(symbol, clean)
        if history_points_builder is not None
        else build_single_index_lppl_history_points(symbol, clean, row_builder=row_builder)
    )
    if not score_points:
        return {
            "available": False,
            "symbol": symbol,
            "points": [],
            "summary": "LPPL history replay produced no valid fit points",
        }
    first_index = bar_index_at_or_before(clean, parse_lppl_point_date(score_points[0].get("date")) or clean[0].date)
    base_close = clean[first_index if first_index is not None else 0].close
    points: list[dict[str, Any]] = []
    for point in score_points:
        point_date = parse_lppl_point_date(point.get("date"))
        bar_index = bar_index_at_or_before(clean, point_date) if point_date else None
        if bar_index is None:
            continue
        close = clean[bar_index].close
        enriched = {
            "date": clean[bar_index].date.isoformat(),
            "score": point["score"],
            "close": round(close, 2),
            "indexedClose": round(100 * close / base_close, 2) if base_close > 0 else None,
        }
        for key in (
            "criticalDate",
            "daysToCritical",
            "sessionsToCritical",
            "calendarDaysToCritical",
            "criticalDateApproximation",
            "sessionsToCriticalRange",
            "passesLpplCoreDiagnostics",
            "passesLpplDiagnostics",
            "lpplImprovementPct",
            "oscillationCount",
        ):
            if key in point:
                enriched[key] = point[key]
        points.append(enriched)
    if len(points) < 2:
        return {
            "available": False,
            "symbol": symbol,
            "points": points,
            "summary": "LPPL history replay has fewer than two chartable points",
        }
    return {
        "available": True,
        "symbol": symbol,
        "name": str(index_row.get("name") or symbol),
        "sourceSymbol": str(index_row.get("sourceSymbol") or symbol),
        "summary": f"{symbol} LPPL replay; risk score and indexed own-market price are shown on separate axes.",
        "points": points,
        "dateRange": {"start": points[0]["date"], "end": points[-1]["date"]},
        "clipState": build_lppl_clip_state(points),
    }


def parse_lppl_point_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def build_lppl_clip_state(points: list[dict[str, Any]], *, lookback: int = 20) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        point_date = parse_lppl_point_date(point.get("date"))
        critical_date = parse_lppl_point_date(point.get("criticalDate"))
        if point_date is None or critical_date is None:
            continue
        observations.append(
            {
                "date": point_date,
                "criticalDate": critical_date,
                "score": optional_float(point.get("score")),
                "passesCore": bool(point.get("passesLpplCoreDiagnostics")),
            }
        )
    if len(observations) < 5:
        return {
            "available": False,
            "clipLock": False,
            "status": "insufficient",
            "statusCn": "样本不足",
            "sampleSize": len(observations),
            "summary": "CLIP requires at least five replay points with critical dates.",
        }
    recent = observations[-max(5, lookback):]
    critical_ordinals = sorted(item["criticalDate"].toordinal() for item in recent)
    q20 = lppl_percentile(critical_ordinals, 0.20)
    q50 = lppl_percentile(critical_ordinals, 0.50)
    q80 = lppl_percentile(critical_ordinals, 0.80)
    tc_window_days = max(0, int(round(q80 - q20)))
    latest_observation = max(item["date"] for item in recent)
    median_lead_days = int(round(q50 - latest_observation.toordinal()))
    core_pass_ratio = sum(1 for item in recent if item["passesCore"]) / len(recent)
    clip_lock = tc_window_days <= 30 and 5 <= median_lead_days <= 180 and core_pass_ratio >= 0.50
    converging = tc_window_days <= 60 and 5 <= median_lead_days <= 252 and core_pass_ratio >= 0.35
    if clip_lock:
        status, status_cn = "locked", "CLIP锁定"
    elif converging:
        status, status_cn = "converging", "CLIP收敛"
    elif median_lead_days < 0:
        status, status_cn = "expired", "临界已过"
    else:
        status, status_cn = "scattered", "临界分散"
    return {
        "available": True,
        "clipLock": clip_lock,
        "status": status,
        "statusCn": status_cn,
        "sampleSize": len(recent),
        "lookback": max(5, lookback),
        "tcMedian": date.fromordinal(int(round(q50))).isoformat(),
        "tcQ20": date.fromordinal(int(round(q20))).isoformat(),
        "tcQ80": date.fromordinal(int(round(q80))).isoformat(),
        "tcWindowDays": tc_window_days,
        "medianLeadDays": median_lead_days,
        "corePassRatio": round(core_pass_ratio, 3),
        "summary": (
            f"CLIP {status_cn}: recent tc 20-80% window {tc_window_days} days, "
            f"median lead {median_lead_days} days, core pass {core_pass_ratio:.0%}."
        ),
    }


def build_global_lppl_per_index_backtests(
    histories: dict[str, Any],
    bars_by_symbol: dict[str, list[MarketDailyBar]],
) -> dict[str, Any]:
    backtests: dict[str, Any] = {}
    for symbol, history in histories.items():
        points = history.get("points", []) if isinstance(history, dict) else []
        backtests[symbol] = build_global_lppl_backtest(points, bars_by_symbol.get(symbol, []), symbol=symbol)
    return backtests


def attach_global_lppl_per_index_payloads(
    index_rows: list[dict[str, Any]],
    histories: dict[str, Any],
    backtests: dict[str, Any],
) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in index_rows:
        enriched = dict(row)
        symbol = str(enriched.get("symbol") or "").upper()
        enriched["history"] = histories.get(symbol, {"available": False, "symbol": symbol, "points": []})
        enriched["backtest"] = backtests.get(symbol, {"available": False, "sampleSize": 0, "horizonTests": []})
        history_clip = enriched["history"].get("clipState") if isinstance(enriched.get("history"), dict) else None
        if isinstance(history_clip, dict):
            enriched["clipState"] = history_clip
        enriched_rows.append(enriched)
    return enriched_rows


def compact_global_lppl_index_payloads(index_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove repeated per-index history/backtest bodies from serialized rows.

    History and backtest payloads are canonical under ``perIndexHistory`` and
    ``perIndexBacktests`` on the enclosing global-LPPL object.  The full bodies
    stay attached while the model builds CLIP, forward signals, validation, and
    regional summaries; this function is deliberately called only at the final
    payload boundary.  Stable refs make the migration explicit without
    duplicating the large arrays in every index row.
    """
    compact_rows: list[dict[str, Any]] = []
    for row in index_rows:
        compact = dict(row)
        symbol = str(compact.get("symbol") or "").upper()
        history = compact.pop("history", None)
        backtest = compact.pop("backtest", None)
        if symbol and isinstance(history, dict):
            compact["historyRef"] = {
                "symbol": symbol,
                "path": f"globalLpplRisk.perIndexHistory.{symbol}",
            }
        if symbol and isinstance(backtest, dict):
            compact["backtestRef"] = {
                "symbol": symbol,
                "path": f"globalLpplRisk.perIndexBacktests.{symbol}",
            }
        compact_rows.append(compact)
    return compact_rows
