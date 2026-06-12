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
- `/api/spy_early_warning`
- `/api/equity_short_term_risk`
- `/api/source_status`
- `/api/source-status`
- `/api/history`
- `/api/history/snapshots`
- `/api/history/stats`
- `/api/history/series`
- `POST /api/update`
- `POST /api/update-equity`

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
The same payload includes three separate equity-risk contracts:
`spyEarlyWarning`, `equityShortTermRisk`, and `globalLpplRisk`. `globalLpplRisk`
is independent from `equityShortTermRisk`; it exposes current LPPL fits plus
separate `history`, `backtest`, and validation-weighted `forwardSignal`
payloads for each available market. The top-level LPPL score/history/backtest
are deliberately unavailable so SPY, QQQ, Korea/EWY, Hong Kong/EWH,
Taiwan/EWT, and Japan/EWJ are not blended into one composite.
The `/api/cross` slice includes the section-07 `historySeries` registry used by
the UI to request global-rate, risk/dollar, and inflation/commodity history
through `/api/history/series`.

List endpoints with ISO dates, such as `/api/events`, support
`from=YYYY-MM-DD` and `to=YYYY-MM-DD`. Add `format=csv` to dashboard slice
routes handled by `treasury_data.api` to export CSV; `/api/curve?format=csv`
returns one row per tenor. CSV export does not apply to `/api/health`,
`/api/history*`, or `POST /api/update`.
`POST /api/update` starts the public-data refresh in a background thread and
returns `202 accepted` with the currently served snapshot metadata, so the UI
does not block while public sources are fetched. If a manual refresh is already
running, it returns `running` and reuses the active thread instead of starting
a duplicate fetch.
`POST /api/update-equity` runs the lightweight daily-market refresh path for
`equityShortTermRisk` and `globalLpplRisk` without rebuilding the whole macro
snapshot.
`/api/history` returns snapshot and metric counts plus latest stored metadata;
`/api/history/snapshots` returns recent stored snapshot metadata.
`/api/history/stats` returns per-series counts, ranges, latest values, and
basic quantiles. `/api/history/series` returns sampled chronological points
for an individual historical series and accepts `category`, `name`, optional
`label`, `years`, `from`, `limit`, and the `max_points` alias.
`/api/health` also includes the SQLite history summary and latest 5-year
history backfill run. Critical or degraded backfill source errors are exposed
as health warnings, so `scripts/check_health.py` exits non-zero and can notify
on background history issues. Warning-severity source errors remain visible in
`history.latestBackfill.sourceErrors` but do not make health fail.

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
stores the candidate as `data/dashboard.failed.json` for inspection. A
candidate with core curve, scorecard, and Conditions Score trend content still
becomes the served snapshot and is saved to history; a candidate missing that
core content is rejected in favor of the last healthy dashboard and is not
added to history.
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
Short-term equity and LPPL refreshes try Nasdaq public historical quote rows
first. Nasdaq is a non-official public endpoint, so both the full refresh and
`POST /api/update-equity` fall back to Stooq daily CSV symbols such as
`spy.us`, `qqq.us`, and the ETF proxy equivalents when Nasdaq fails. Fallback
success keeps the monitored OHLCV row usable for smoke checks but marks
`source: stooq-fallback` and includes the Nasdaq failure in `note`, so degraded
source quality is visible in `/api/source_status` and the data-source modal.
The LPPL global proxy set is `SPY`, `QQQ`, `EWY`, `EWH`, `EWT`, and `EWJ`; the
Asia entries are clearly labeled as ETF proxies rather than direct index feeds.

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
