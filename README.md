# MarcoMonitor

Current active app: `the-dial-treasury-v1/`, the US Treasury factor dashboard.
The headline 0-100 macro score now follows the public bhadial Conditions Score
shape: 47 tracked factors, 30 scored factors across 7 modules, module weights
based on public factor coverage plus overlap adjustment, Funding EMA(5), and
explicit proxy boundaries for ETF-relative inputs.
The scorecard conclusion layer includes a credibility audit: factor-driver
contributions are scaled by module weight and factor count, while proxy,
modeled, and manual-placeholder inputs are discounted before the dashboard
states whether the inference is high, medium, or low confidence.
The dashboard now also includes a SPY Early Warning Index, an equity-specific
0-100 drawdown-warning overlay that reuses existing Conditions Score
components plus 3-month score deterioration to guide SPY/SPX exposure from
constructive through de-risk.
It also includes a daily `equityShortTermRisk` tactical layer and an
independent `globalLpplRisk` research indicator. `equityShortTermRisk` uses
replayable Nasdaq OHLCV market-structure factors and event context for
short-horizon SPY risk control. `globalLpplRisk` is intentionally separate: it
fits constrained LPPL curves for SPY, QQQ, and global ETF proxies, records
index-level historical validation under `indexValidation`, and applies
`effectiveWeightMultiplier` so weaker historical evidence cannot dominate the
global score. LPPL is a research temperature gauge, not an input to the
short-term equity score.
Section 07, cross-market, includes a dynamic historical chart backed by the
SQLite history API for global rates, risk/dollar, and inflation/commodity
series.

Historical implementations are archived under `archive/legacy/2026-05-25/`.
Do not use archived directories as the runtime or documentation source of
truth.

## Repository

This workspace is published on `main` at:

```text
https://github.com/c3msu/MLM
```

`the-dial-treasury-v1/data/dashboard.json` is tracked because it is the
HTTP/static serving snapshot and the smoke-check fixture. Direct `file://`
opening uses the embedded static fallback in `app.js`. Local SQLite history,
rejected refresh candidates, logs, Playwright scratch output, and analyst
overrides are ignored.

## Run Locally

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/serve.py --skip-start-update --port 8451
```

Open:

```text
http://127.0.0.1:8451/
```

## Verify

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 -m unittest discover -s the-dial-treasury-v1/tests

node --check the-dial-treasury-v1/i18n.js
node --check the-dial-treasury-v1/app.js

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/smoke_check.py \
  --path the-dial-treasury-v1/data/dashboard.json
```

The smoke check treats any `sourceStatus` error as a failure. If the only
failure is Treasury Fiscal Data `Debt Subject to Limit` returning a transient
curl/network error, the dashboard contract can still be inspected, but the
source-status issue should remain visible until the public endpoint recovers.
Required equity OHLCV rows must also be `ok`; transient Nasdaq quote timeouts
are reported with the concrete symbol name.

For server-backed verification:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/smoke_check.py \
  --url http://127.0.0.1:8451

python3 the-dial-treasury-v1/scripts/check_health.py \
  --url http://127.0.0.1:8451/api/health
```

## Documentation

- `PROJECT_STATUS.md`: workspace orientation and active/archived boundary.
- `the-dial-treasury-v1/README.md`: active app scope, data boundary, API, and
  operation details.
- `docs/treasury-deployment.md`: local deployment and daily update workflow.
- `docs/treasury-authoring-guide.md`: analyst/developer workflow for source,
  scorecard, and narrative changes.
- `docs/investment-view-rule-audit.md`: section 09 investment-view rule map,
  scenario coverage, historical SPY impact overlay, and remaining feasibility
  boundaries.
- `docs/spy-early-warning-index.md`: SPY Early Warning Index construction,
  initial historical diagnostics, current reading, and boundaries.
- `docs/treasury-plan-implementation-checklist.md`: implementation coverage
  against the original replication plan.
