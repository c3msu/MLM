# 2026-06-07 Equity Short-Term Risk Evidence + Forward Window Plan

## Objective

Improve `equityShortTermRisk` so the score is driven by real, historically replayable equity-market evidence where possible, while keeping forward-looking but non-replayable inputs visible as audit context. The metric should preserve the historical curve, report prediction accuracy, and relax the warning window from strict T+1 to 1-5 trading/calendar days where that improves reliability.

## Scope

- Add component-level evidence metadata: source, quality, historical replayability, coverage, scoring use, and timestamp policy.
- Gate scoring so weak/current-only sources do not silently dominate the headline score.
- Extend event/catalyst logic to a 5-day forward window and expose the known-before-signal policy.
- Add backtest lead-time statistics for score thresholds and alert clusters.
- Show source quality, forward catalyst window, and lead-time accuracy on the dashboard.
- Refresh `data/dashboard.json`, run tests and smoke checks, and verify the local page at `http://127.0.0.1:8451/`.

## Non-Goals

- Do not add direct short/inverse-ETF trading rules.
- Do not claim live option OI history if only a current delayed snapshot is available.
- Do not replace the existing monthly macro liquidity study; keep this as the tactical equity risk layer.

## Verification

- Unit tests for factor evidence, source-quality gating, and backtest lead-time metrics.
- Frontend static tests for the new evidence/quality render path.
- `scripts/smoke_check.py` path and URL validation.
- Browser-visible verification of the equity short-term risk panel.
