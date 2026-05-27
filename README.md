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
- `docs/treasury-plan-implementation-checklist.md`: implementation coverage
  against the original replication plan.
