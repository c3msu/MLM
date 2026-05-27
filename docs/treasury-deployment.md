# Treasury Dashboard Local Deployment

Active app: `the-dial-treasury-v1/`.

This project is currently optimized for local deployment. Vercel/static hosting
is intentionally out of scope for this pass. Historical MarcoMonitor variants
are archived under `archive/legacy/2026-05-25/` and are not deployment targets.

## Local Real-Data Run

Install dependencies:

```bash
python3 -m pip install -r the-dial-treasury-v1/requirements.txt
```

Build the latest dashboard JSON:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/update_data.py \
  --output the-dial-treasury-v1/data/dashboard.json
```

This writes both the latest serving snapshot and the local history store:

- `the-dial-treasury-v1/data/dashboard.json`
- `the-dial-treasury-v1/data/history.sqlite3`

Serve with local REST API endpoints:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/serve.py --port 8451 --daily-at 16:30
```

Open:

```text
http://127.0.0.1:8451/
```

## API Contract

The local Python server exposes:

- `/api/dashboard`
- `/api/health`
- `/api/curve`
- `/api/decomposition`
- `/api/fed_path`
- `/api/scorecard`
- `/api/policy`
- `/api/auctions`
- `/api/positioning`
- `/api/cross`
- `/api/percentiles`
- `/api/events`
- `/api/news`
- `/api/ideas`
- `/api/source_status`
- `/api/source-status`
- `/api/history`
- `/api/history/snapshots`
- `/api/history/stats`
- `/api/history/series`
- `POST /api/update`

The dashboard slice endpoints are dynamic views over `data/dashboard.json`;
the history endpoints read `data/history.sqlite3`. The update script does not
generate static API files.

`/api/dashboard` includes `macroLiquidity`, which is the bhadial-compatible
Conditions Score layer: 47 tracked factors, 30 scored factors, 7 modules,
public factor-coverage/overlap module weights, Funding EMA(5), and the public
scoring methods (`level_percentile`, `deviation`, `target_distance`,
`shock_only`, `risk_signal`). `macroLiquidity.benchmark` records the public
bhadial dashboard score and local delta when the page is reachable. Keep this
contract intact when redeploying or changing the score.

`/api/dashboard` also includes `conclusionAudit` for the editable scorecard
stance. It reports normalized duration/curve scores, top factor drivers,
evidence quality, source warnings/errors, and whether proxy or modeled inputs
make the conclusion unsuitable for a high-confidence narrative.
The `/api/cross` slice includes the section-07 `historySeries` registry used by
the UI to request global-rate, risk/dollar, and inflation/commodity history
through `/api/history/series`.

List endpoints with ISO dates, such as `/api/events`, support
`from=YYYY-MM-DD` and `to=YYYY-MM-DD`. Add `format=csv` to any route to export
CSV; `/api/curve?format=csv` returns one row per tenor.
`POST /api/update` starts the public-data refresh in a background thread and
returns `202 accepted` with the currently served snapshot metadata, so the UI
does not block while public sources are fetched. If a manual refresh is already
running, it returns `running` and reuses the active thread instead of starting
a duplicate fetch.
`/api/history` returns snapshot and metric counts plus latest stored metadata;
`/api/history/snapshots` returns recent stored snapshot metadata.
`/api/history/stats` returns per-series counts, ranges, latest values, and
basic quantiles. `/api/history/series` returns sampled chronological points
for an individual historical series.
`/api/health` also includes the SQLite history summary and latest 5-year
history backfill run. Backfill source errors are exposed as health warnings,
so `scripts/check_health.py` exits non-zero and can notify on background
history issues.

## Daily Background Update

For a macOS login service:

```bash
python3 the-dial-treasury-v1/scripts/install_launch_agent.py --daily-at 16:30 --port 8451 --load
```

The LaunchAgent starts the local server immediately, serves the existing
`data/dashboard.json`, refreshes in the background at startup, and refreshes
once per day at the configured local `HH:MM`. Successful refreshes write the
current JSON snapshot and append/update SQLite history in
`data/history.sqlite3`. The JSON write is atomic. If a refresh produces
real-source `error` rows while the current dashboard is healthy, the updater
preserves the healthy dashboard and stores the rejected candidate as
`data/dashboard.failed.json` without adding it to history.
Daily history backfill runs are recorded in SQLite as `history_backfill_runs`.
Single-source backfill failures are recorded in that run metadata and do not
block saving the remaining public history series.
The page-level `刷新` button uses the same server process and endpoint for
manual background refreshes between scheduled runs.

For local monitoring and alerting, install the health checker after the update
window:

```bash
python3 the-dial-treasury-v1/scripts/install_health_agent.py --daily-at 16:45 --port 8451 --load
```

Manual check:

```bash
python3 the-dial-treasury-v1/scripts/check_health.py --url http://127.0.0.1:8451/api/health
```

LaunchAgent logs are written under `~/Library/Logs/treasury-factor-desk/`:

- `launchd.out.log` / `launchd.err.log` for the dashboard service.
- `health.out.log` / `health.err.log` for the health checker.

## Live Public Data Sources

The local refresh pulls real public data from U.S. Treasury yield-curve XML,
FRED CSV endpoints including CPI, PCE, core PCE, Dallas Fed Trimmed Mean PCE,
TreasuryDirect auctioned and announced securities JSON,
U.S. Treasury Quarterly Refunding documents and press releases, Federal Reserve
FOMC calendar HTML with Federal Reserve Bank of Chicago schedule fallback,
Treasury Fiscal Data Daily Treasury Statement debt-limit tables, FRED economic
release-calendar pages for CPI/PPI/employment dates, BEA release schedule pages
for GDP and Personal Income/Outlays dates, NY Fed ACM Excel, NY Fed Markets API
primary dealer statistics, Federal Reserve SEP projection-materials HTML, Stooq
public `ZQ.F` Fed Funds futures quote CSV, Stooq public `XAUUSD` gold spot quote
CSV, Federal Reserve press-release RSS, CFTC COT financial futures zip files,
and Treasury TIC table 5 text. The dashboard also computes local historical
percentile ranks from these public histories for bank reserves, net liquidity,
liquidity momentum, SOFR-EFFR spread, VIX, HY OAS, the broad dollar, and auction
bid-to-cover.
The same SQLite history store powers the section-07 dynamic cross-market chart,
including global 10Y yields, S&P 500, VIX, dollar, credit OAS, CPI/PCE/core
PCE, Dallas Fed Trimmed Mean PCE, WTI, OVX, and GVZ where public history is
available.

The remaining non-real fields are explicit: Fed path probabilities are still
model-converted rather than official CME FedWatch probabilities, although the
model now uses a public Fed Funds futures proxy plus curve/macro inputs.
Official Treasury/Fed headlines are connected as public news; full-text
real-time market-news redistribution remains manual unless an authorized news
feed is provided.

## Content Overrides

Copy `the-dial-treasury-v1/content/overrides.example.json` to `the-dial-treasury-v1/content/overrides.json` to override manual narrative fields:

- `ideas`
- `events`
- `news`
- `groupWeights`
- `factorOverrides`

This is the intended replacement for an admin CMS until a real authenticated admin layer is needed.

For analyst and developer authoring workflows, including how to add public
sources or new scorecard factors, see `docs/treasury-authoring-guide.md`.
