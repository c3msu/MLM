# MarcoMonitor Project Status

## Canonical Line

`the-dial-treasury-v1/` is the only active runnable line for this workspace.
It is the US Treasury factor dashboard, with a single-page frontend, public
data updater, local REST API, SQLite history store, and optional daily local
scheduler.

The headline 0-100 macro score is aligned to the public bhadial Conditions
Score shape: 30 scored factors, 7 modules, Funding EMA(5), and explicit
public-proxy boundaries for ETF-relative factors.

Run locally:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/serve.py --skip-start-update --port 8451
```

Dashboard:

```text
http://127.0.0.1:8451/
```

Core verification:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 -m unittest discover -s the-dial-treasury-v1/tests

node --check the-dial-treasury-v1/i18n.js
node --check the-dial-treasury-v1/app.js

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/smoke_check.py \
  --path the-dial-treasury-v1/data/dashboard.json
```

## Archived Legacy Code

Historical variants and old root-level reference artifacts were moved to
`archive/legacy/2026-05-25/`.

Archived code directories:

- `my-app/`: older Next.js product-style prototype.
- `static-site/`: older standalone static pages.
- `the-dial-personal/`: older personal static version with CSV import scripts.
- `the-dial-optimized/`: optimized static HTML/CSS/JS snapshot.
- `the-dial-v3/`: previous macro dashboard mainline.

Archived root artifacts:

- `TechSpec.md`
- `design.md`
- `CHANGES.md`
- `fix.md`
- `The Dial.pdf`
- `sp500_history.csv`
- `output/`
- `test-results/`

Treat archived files as historical references only. New development, local
operation, testing, and documentation should target `the-dial-treasury-v1/`.

## Current Runtime Surface

- Frontend: `the-dial-treasury-v1/index.html`, `app.js`, `i18n.js`, and
  `styles.css`.
- Data builder: `the-dial-treasury-v1/treasury_data/build_dashboard.py`.
- Public-source parsers: `the-dial-treasury-v1/treasury_data/sources.py`.
- Local server/API: `the-dial-treasury-v1/scripts/serve.py`.
- Manual refresh entrypoint: `the-dial-treasury-v1/scripts/update_data.py`.
- Smoke check: `the-dial-treasury-v1/scripts/smoke_check.py`.

The local server exposes the existing dashboard slice APIs, history APIs, and
`POST /api/update`. The refactor does not rename the active directory or change
the API contract.

## Known Limits

- This workspace root is not a git repository. Commit/branch workflows do not
  apply here unless a repo is initialized later.
- The default runtime is local. Static/Vercel deployment remains out of scope
  for the current codebase.
- Paid or licensed feeds such as MOVE, swaps, futures basis, and market depth
  remain documented boundaries unless credentials and redistribution rights are
  provided.
- `data/dashboard.json` is intentionally kept as a serving snapshot for direct
  file fallback and smoke checks. Do not refresh it unless the task explicitly
  calls for a data update.
