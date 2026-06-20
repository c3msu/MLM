"""Pure LPPL-fit math core extracted from build_dashboard.py
(behavior-unchanged, 2026-06-19 全面重构 Phase 1). The log-periodic power-law bubble-fit
primitives: windowing constants, grid + local-refine candidate search, the bounded
least-squares solver, residual diagnostics, and ensemble/percentile helpers. Depends
only on stdlib + sources types + dashboard_core scalars. The LPPL *orchestration*
(per-index histories, backtests, regional/advice bridges) stays in build_dashboard.
Re-exported by build_dashboard via `from .scoring_lppl import *`."""
from __future__ import annotations

import math
from typing import Any

from .sources import MarketDailyBar
from .dashboard_core import bounded_score, optional_float, risk_linear


GLOBAL_LPPL_MIN_OBSERVATIONS = 120
GLOBAL_LPPL_DEFAULT_WINDOW = 252
GLOBAL_LPPL_SIGNAL_WINDOWS = (120, 180, GLOBAL_LPPL_DEFAULT_WINDOW, 375, 500, 750)


def fit_global_lppl_signal(bars: list[MarketDailyBar], *, fast: bool = False) -> dict[str, Any]:
    clean = [bar for bar in bars if bar.close > 0 and math.isfinite(bar.close)]
    if len(clean) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {"available": False, "reason": "sample shorter than LPPL minimum window"}
    windows = (
        [min(GLOBAL_LPPL_DEFAULT_WINDOW, len(clean))]
        if fast
        else [window for window in GLOBAL_LPPL_SIGNAL_WINDOWS if len(clean) >= window]
    )
    fits = []
    for window in windows:
        sample = clean[-window:]
        fit = fit_lppl_window(sample, fast=fast)
        if fit.get("available"):
            fits.append(fit)
    if not fits:
        return {"available": False, "reason": "bounded LPPL fit did not converge"}
    selected = select_lppl_fit_candidate(fits)
    selected["fitEnsemble"] = build_lppl_fit_ensemble(fits, total_fit_count=len(windows), attempted_windows=windows)
    return selected


def select_lppl_fit_candidate(fits: list[dict[str, Any]]) -> dict[str, Any]:
    available = [fit for fit in fits if fit.get("available")]
    if not available:
        return {"available": False, "reason": "bounded LPPL fit did not converge"}
    best = dict(
        max(
            available,
            key=lambda item: (
                bool(item.get("passesLpplCoreDiagnostics")),
                bool(item.get("passesLpplDiagnostics")),
                float(item.get("fitR2") or 0.0),
                -(float(item.get("fitSse") or 0.0)),
                float(item.get("confidence") or 0.0),
                float(item.get("score") or 0.0),
            ),
        )
    )
    days_values = sorted({
        int(days)
        for fit in available
        for days in [optional_float(fit.get("daysToCritical"))]
        if days is not None
    })
    if days_values:
        best["daysToCriticalRange"] = {"min": min(days_values), "max": max(days_values), "values": days_values}
    window_values = sorted({
        int(window)
        for fit in available
        for window in [optional_float(fit.get("windowDays"))]
        if window is not None
    })
    if window_values:
        best["windowDaysRange"] = {"min": min(window_values), "max": max(window_values), "values": window_values}
    best["selectionBasis"] = "fit_quality"
    return best


def build_lppl_fit_ensemble(
    fits: list[dict[str, Any]],
    *,
    total_fit_count: int,
    attempted_windows: list[int],
) -> dict[str, Any]:
    available = [fit for fit in fits if fit.get("available")]
    valid_fit_count = len(available)
    if not available:
        return {
            "available": False,
            "totalFitCount": total_fit_count,
            "validFitCount": 0,
            "validFitRatioPct": 0.0,
            "residualPassRatioPct": 0.0,
            "windowDays": attempted_windows,
            "windowAgreement": "unavailable",
            "optimizerAgreement": "not-modeled",
            "summary": "LPPL ensemble produced no valid fits.",
        }
    lead_days = sorted(
        int(days)
        for fit in available
        for days in [optional_float(fit.get("daysToCritical"))]
        if days is not None
    )
    window_days = sorted(
        int(window)
        for fit in available
        for window in [optional_float(fit.get("windowDays"))]
        if window is not None
    )
    q20 = int(round(lppl_percentile(lead_days, 0.20))) if lead_days else None
    q50 = int(round(lppl_percentile(lead_days, 0.50))) if lead_days else None
    q80 = int(round(lppl_percentile(lead_days, 0.80))) if lead_days else None
    tc_window_days = (q80 - q20) if q20 is not None and q80 is not None else None
    residual_pass_count = sum(1 for fit in available if fit.get("passesLpplDiagnostics") is True)
    residual_pass_ratio = 100 * residual_pass_count / max(1, valid_fit_count)
    if tc_window_days is None:
        agreement = "unavailable"
    elif tc_window_days <= 30:
        agreement = "tight"
    elif tc_window_days <= 75:
        agreement = "moderate"
    else:
        agreement = "scattered"
    return {
        "available": True,
        "totalFitCount": int(total_fit_count),
        "validFitCount": int(valid_fit_count),
        "validFitRatioPct": round(100 * valid_fit_count / max(1, total_fit_count), 1),
        "residualPassRatioPct": round(residual_pass_ratio, 1),
        "windowDays": window_days,
        "attemptedWindowDays": list(attempted_windows),
        "tcLeadDaysQ20": q20,
        "tcLeadDaysMedian": q50,
        "tcLeadDaysQ80": q80,
        "tcWindowDays": tc_window_days,
        "windowAgreement": agreement,
        "optimizerAgreement": "not-modeled",
        "summary": (
            f"{valid_fit_count}/{total_fit_count} LPPL windows valid; "
            f"tc lead 20/50/80% = {q20}/{q50}/{q80}D; residual pass {residual_pass_ratio:.0f}%."
        ),
    }


def fit_lppl_window(sample: list[MarketDailyBar], *, fast: bool = False) -> dict[str, Any]:
    closes = [bar.close for bar in sample if bar.close > 0]
    if len(closes) != len(sample) or len(sample) < GLOBAL_LPPL_MIN_OBSERVATIONS:
        return {"available": False, "reason": "invalid close values"}
    ys = [math.log(value) for value in closes]
    n = len(sample)
    tc_offsets = (25, 60, 130) if fast else (15, 25, 40, 60, 90, 130, 170)
    m_values = (0.35, 0.55, 0.75) if fast else (0.2, 0.35, 0.5, 0.65, 0.8)
    omega_values = (7.0, 10.0, 12.0) if fast else (6.0, 8.0, 10.0, 12.0)
    candidates: list[dict[str, Any]] = []
    for tc_offset in tc_offsets:
        for m in m_values:
            for omega in omega_values:
                candidate = lppl_candidate(ys, closes, n, tc_offset=tc_offset, m=m, omega=omega)
                if candidate is not None:
                    candidates.append(candidate)
    if not candidates:
        return {"available": False, "reason": "bounded LPPL grid produced no stable fit"}
    best = select_lppl_fit_candidate(candidates)
    if best.get("available") and not fast:
        refined = lppl_refine_tc_candidates(ys, closes, n, best)
        if refined:
            best = select_lppl_fit_candidate([best, *refined])
    return best


def lppl_refine_tc_candidates(ys: list[float], closes: list[float], n: int, best: dict[str, Any]) -> list[dict[str, Any]]:
    """Local tc search around the grid winner (±50%, step 5) so daysToCritical is
    not snapped to the coarse grid; selection still ranks by fit quality."""
    base_tc = optional_float(best.get("daysToCritical"))
    m = optional_float(best.get("powerExponent"))
    omega = optional_float(best.get("omega"))
    if base_tc is None or m is None or omega is None:
        return []
    base_tc = int(round(base_tc))
    low = max(5, int(round(base_tc * 0.5)))
    high = int(round(base_tc * 1.5))
    refined: list[dict[str, Any]] = []
    for tc_offset in range(low, high + 1, 5):
        if tc_offset == base_tc:
            continue
        candidate = lppl_candidate(ys, closes, n, tc_offset=tc_offset, m=m, omega=omega)
        if candidate is not None:
            refined.append(candidate)
    return refined


def lppl_candidate(
    ys: list[float],
    closes: list[float],
    n: int,
    *,
    tc_offset: int,
    m: float,
    omega: float,
) -> dict[str, Any] | None:
    tc = (n - 1) + tc_offset
    rows = []
    for t in range(n):
        distance = tc - t
        if distance <= 0:
            return None
        power = distance ** m
        log_distance = math.log(distance)
        rows.append([1.0, power, power * math.cos(omega * log_distance), power * math.sin(omega * log_distance)])
    coefficients = linear_least_squares(rows, ys)
    if coefficients is None:
        return None
    fitted = [sum(coef * value for coef, value in zip(coefficients, row)) for row in rows]
    fit_r2 = regression_r_squared(ys, fitted)
    if fit_r2 is None:
        return None
    fit_sse = sum((actual - predicted) ** 2 for actual, predicted in zip(ys, fitted))
    power_rows = [[1.0, row[1]] for row in rows]
    power_coefficients = linear_least_squares(power_rows, ys)
    if power_coefficients is None:
        return None
    power_fitted = [sum(coef * value for coef, value in zip(power_coefficients, row)) for row in power_rows]
    power_sse = sum((actual - predicted) ** 2 for actual, predicted in zip(ys, power_fitted))
    lppl_improvement_pct = 0.0 if power_sse <= 1e-12 else max(0.0, 100.0 * (power_sse - fit_sse) / power_sse)
    oscillation_count = lppl_oscillation_count(
        tc=tc,
        omega=omega,
        start_index=0,
        end_index=n - 1,
    )
    residuals = [actual - predicted for actual, predicted in zip(ys, fitted)]
    residual_diagnostics = lppl_residual_diagnostics(residuals)
    bubble_coefficient = coefficients[1]
    oscillation = math.sqrt(coefficients[2] ** 2 + coefficients[3] ** 2)
    trailing_63 = closes[-1] / closes[max(0, n - 64)] - 1 if n >= 65 else 0.0
    recent_63 = closes[-1] / closes[-64] - 1 if n >= 128 else trailing_63
    prior_63 = closes[-64] / closes[-127] - 1 if n >= 128 else 0.0
    acceleration = recent_63 - prior_63
    fit_score = bounded_score(100 * fit_r2)
    critical_score = bounded_score(100 * (1 - (tc_offset - 10) / 170))
    trend_score = risk_linear(trailing_63, 0.04, 0.35)
    acceleration_score = risk_linear(acceleration, 0.0, 0.12)
    coherent_bubble = bubble_coefficient < 0 and acceleration > 0 and trailing_63 > 0.03
    valid_oscillation_count = 2.0 <= oscillation_count <= 10.0
    passes_lppl_core_diagnostics = (
        coherent_bubble
        and lppl_improvement_pct >= 5.0
        and valid_oscillation_count
    )
    passes_lppl_diagnostics = passes_lppl_core_diagnostics and bool(residual_diagnostics.get("meanReverting"))
    raw_score = 0.38 * fit_score + 0.24 * critical_score + 0.18 * trend_score + 0.20 * acceleration_score
    if not passes_lppl_core_diagnostics:
        raw_score = min(raw_score, 35.0)
    oscillation_denominator = abs(oscillation) + abs(bubble_coefficient)
    oscillation_balance = abs(oscillation) / oscillation_denominator if oscillation_denominator > 1e-6 else 0.0
    confidence = (
        0.45 * max(0.0, min(1.0, fit_r2))
        + 0.25 * (critical_score / 100)
        + 0.20 * (acceleration_score / 100)
        + 0.10 * min(1.0, oscillation_balance)
    )
    if not passes_lppl_diagnostics:
        confidence = min(confidence, 0.45)
    return {
        "available": True,
        "score": bounded_score(raw_score),
        "confidence": max(0.0, min(1.0, confidence)),
        "fitR2": fit_r2,
        "fitSse": fit_sse,
        "powerLawSse": power_sse,
        "lpplImprovementPct": lppl_improvement_pct,
        "oscillationCount": oscillation_count,
        "passesLpplCoreDiagnostics": passes_lppl_core_diagnostics,
        "residualDiagnostics": residual_diagnostics,
        "passesLpplDiagnostics": passes_lppl_diagnostics,
        "daysToCritical": tc_offset,
        "windowDays": n,
        "powerExponent": m,
        "omega": omega,
        "bubbleCoefficient": bubble_coefficient,
        "oscillationAmplitude": oscillation,
        "trailingReturn63d": trailing_63,
        "acceleration": acceleration,
        "reason": (
            f"coherent LPPL acceleration; power-law improvement {lppl_improvement_pct:.1f}%, "
            f"{oscillation_count:.1f} log-periodic oscillations, residual mean reversion supported"
            if passes_lppl_diagnostics
            else f"LPPL core shape strong but residual mean reversion is weak: power-law improvement {lppl_improvement_pct:.1f}%, "
            f"{oscillation_count:.1f} oscillations"
            if passes_lppl_core_diagnostics
            else f"LPPL diagnostics weak: power-law improvement {lppl_improvement_pct:.1f}%, "
            f"{oscillation_count:.1f} oscillations, residual mean-reverting={bool(residual_diagnostics.get('meanReverting'))}"
        ),
    }


def lppl_oscillation_count(*, tc: float, omega: float, start_index: int, end_index: int) -> float:
    start_distance = tc - start_index
    end_distance = tc - end_index
    if start_distance <= 0 or end_distance <= 0 or omega <= 0:
        return 0.0
    return max(0.0, omega / (2 * math.pi) * math.log(start_distance / end_distance))


def lppl_residual_diagnostics(residuals: list[float]) -> dict[str, Any]:
    clean = [value for value in residuals if math.isfinite(value)]
    if len(clean) < 20:
        return {"available": False, "meanReverting": False, "lag1Autocorrelation": None, "residualStd": None}
    mean_value = sum(clean) / len(clean)
    centered = [value - mean_value for value in clean]
    variance = sum(value * value for value in centered)
    residual_std = math.sqrt(variance / max(1, len(centered) - 1))
    if residual_std <= 7.5e-4:
        return {
            "available": True,
            "meanReverting": True,
            "adfProxyPass": True,
            "kpssProxyPass": True,
            "ljungBoxProxyPass": True,
            "passRatioPct": 100.0,
            "method": "low-variance residual proxy for ADF/KPSS/Ljung-Box checks",
            "lag1Autocorrelation": 0.0,
            "residualStd": round(residual_std, 6),
            "lowResidualVariance": True,
        }
    lag_num = sum(centered[index - 1] * centered[index] for index in range(1, len(centered)))
    lag_den = sum(value * value for value in centered[:-1])
    lag1 = lag_num / lag_den if lag_den > 1e-12 else 0.0
    sign_changes = sum(1 for index in range(1, len(centered)) if centered[index - 1] * centered[index] < 0)
    sign_change_ratio = sign_changes / max(1, len(centered) - 1)
    adf_proxy_pass = abs(lag1) < 0.98 and sign_change_ratio >= 0.03
    kpss_proxy_pass = abs(lag1) < 0.95 or residual_std <= 0.01
    ljung_box_proxy_pass = abs(lag1) < 0.90
    pass_ratio = 100 * sum((adf_proxy_pass, kpss_proxy_pass, ljung_box_proxy_pass)) / 3
    mean_reverting = adf_proxy_pass and kpss_proxy_pass
    return {
        "available": True,
        "meanReverting": mean_reverting,
        "adfProxyPass": adf_proxy_pass,
        "kpssProxyPass": kpss_proxy_pass,
        "ljungBoxProxyPass": ljung_box_proxy_pass,
        "passRatioPct": round(pass_ratio, 1),
        "method": "lag-1 autocorrelation and sign-change proxy for ADF/KPSS/Ljung-Box checks",
        "lag1Autocorrelation": round(lag1, 4),
        "residualStd": round(residual_std, 6),
        "signChangeRatio": round(sign_change_ratio, 4),
        "lowResidualVariance": False,
    }


def linear_least_squares(rows: list[list[float]], ys: list[float]) -> list[float] | None:
    if not rows or len(rows) != len(ys):
        return None
    width = len(rows[0])
    normal = [[0.0 for _ in range(width)] for _ in range(width)]
    target = [0.0 for _ in range(width)]
    for row, y in zip(rows, ys):
        if len(row) != width or not all(math.isfinite(value) for value in row):
            return None
        for i in range(width):
            target[i] += row[i] * y
            for j in range(width):
                normal[i][j] += row[i] * row[j]
    return solve_linear_system(normal, target)


def solve_linear_system(matrix: list[list[float]], target: list[float]) -> list[float] | None:
    n = len(target)
    augmented = [list(row) + [target[index]] for index, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row_index: abs(augmented[row_index][col]))
        if abs(augmented[pivot][col]) < 1e-10:
            return None
        if pivot != col:
            augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        for j in range(col, n + 1):
            augmented[col][j] /= pivot_value
        for row_index in range(n):
            if row_index == col:
                continue
            factor = augmented[row_index][col]
            if factor == 0:
                continue
            for j in range(col, n + 1):
                augmented[row_index][j] -= factor * augmented[col][j]
    return [augmented[row][n] for row in range(n)]


def regression_r_squared(actual: list[float], fitted: list[float]) -> float | None:
    if len(actual) != len(fitted) or len(actual) < 3:
        return None
    mean_y = sum(actual) / len(actual)
    total = sum((value - mean_y) ** 2 for value in actual)
    if total <= 0:
        return None
    residual = sum((value - fit) ** 2 for value, fit in zip(actual, fitted))
    return max(0.0, min(1.0, 1 - residual / total))


def lppl_percentile(sorted_values: list[int], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pct = max(0.0, min(1.0, percentile))
    position = (len(sorted_values) - 1) * pct
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return float(sorted_values[lower_index])
    weight = position - lower_index
    return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight
