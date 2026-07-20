# MarcoMonitor Project Status

## Canonical Line

`the-dial-treasury-v1/` is the only active runnable line for this workspace.
It is the US Treasury factor dashboard, with a single-page frontend, public
data updater, local REST API, SQLite history store, and optional daily local
scheduler.

The headline 0-100 macro score is aligned to the public bhadial Conditions
Score shape: 21 active public-data factors across 7 modules after proxy and
redundancy pruning. It is an explicit fixed-weight compatibility approximation,
not a reproduction of the current public 30-scored-factor, dynamically de-
correlated headline. Funding EMA(5) means five daily availability observations,
not five month-end samples, and ETF-relative factors retain explicit public-
proxy boundaries. Freshness, warm-up, effective-weight coverage, observed-only,
and reliability diagnostics expose the currently eligible subset. Downstream
decisions require at least 25% effective-weight coverage and 5 scored factors;
the zero-coverage shrinkage value of 50 is treated as unknown, not neutral.

Factor availability is audited separately from observation age. NFCI uses its
Friday-observation to Wednesday-release lag, net-liquidity inputs retain their
H.4.1 release lag, and each scored factor exposes observation/availability
dates plus the lag basis. Funding-fragmentation robust z-scores use prior-only
median/MAD baselines with a 1bp scale floor, so the current corridor shock does
not dilute its own signal.

The equity-risk surface has three separate contracts:

- `spyEarlyWarning`: monthly/medium-horizon macro drawdown-risk overlay. Its v3
  score requires usable macro coverage and excludes explicitly ineligible
  factors; numeric allocation additionally requires a complete surface and
  aggregate holdout audit whose surface, validation and aggregate
  `rulesVersion` all match the current code version. Missing, mismatched or
  stale validation moves the band and action-oriented summary to context.
- `equityShortTermRisk`: daily SPY tactical risk score from replayable OHLCV
  market structure on the exact `equity-risk-ohlcv-core-v2` scale. Only six
  replayable OHLCV factors can affect its base score or rule-level
  `scoreAdjustments`; event, macro, and option data are context/audit-only and
  cannot indirectly alter amplifiers or dampeners. Live, replay and cache paths
  must also match the canonical normalized six-factor weights, not only the
  scale ID and component names. Each score
  is final only after the completed signal-date close; its executable 15-session
  label starts at the next trading-session open, treats that session as session
  1, and measures return to session-15 close plus maximum adverse excursion
  from that open through the session-15 minimum low (not path peak-to-trough
  drawdown). Numeric production allocation is
  fail-closed: the replay-comparable core must be complete, the pre-registered
  score>=75 rule must be triggered, and the purged final holdout must contain at
  least 30 complete labels and three independent alert episodes whose precision
  95% Wilson lower bound exceeds the event base rate by at least 5 percentage
  points. Its
  `volatilityEstimatorAudit` shadow-tests standard Parkinson RMS aggregation on
  the identical OOS label fingerprint and episode rule. Full-sample changes are
  descriptive only; even an OOS-validated RMS candidate needs at least five
  independent episodes, a 2-point episode-precision improvement, and no worse
  lift or false positives to be marked promising, and never switches production
  automatically.
- `globalLpplRisk`: independent global LPPL research indicator for SPY, QQQ,
  KOSPI/EWY, Hang Seng/EWH, Taiwan/EWT, and Nikkei/EWJ. It is not included in
  `equityShortTermRisk`; each index carries its own current LPPL fit,
  `historyRef`, `backtestRef`, `indexValidation`, and validation-weighted
  `forwardSignal`, with canonical history/backtest maps stored once. Raw LPPL
  status remains a research diagnostic; production credit additionally
  requires an exact live/replay model fingerprint plus own-market, non-
  overlapping OOS alert evidence after the fixed six-market correction. The
  top-level score stays `null` so markets are not blended into a composite.

Equity-only cache and last-known-good paths require a complete current
`scoreScale` / `actionable` / `productionValidation` contract. Borrowed,
refresh-ineligible, or pre-contract equity roots remain descriptive context,
expose no actionable numeric allocation band, and require a fresh recomputation
before action can resume. A v2 cache missing the canonical weight audit is also
stale and must be recomputed. Even a valid cache hit rebuilds the dependent
signal-validation, SPY robustness, regional, and portfolio surfaces before
publication, so an invalidated root cannot leave an old derived action behind.

Decision propagation is independently fail-closed. Equity/SPY overview layers,
LPPL status, regional rotation, cross-layer conflicts, and investment ideas may
bind a stance only when the originating surface and allocation both pass their
production evidence contract and are currently triggered. Otherwise numeric
bands and directional views remain `contextAllocation` or research background,
with no executable sizing. The dashboard contract recomputes those gates from
the underlying evidence rather than trusting serialized summary flags: equity
must reconcile its live scale and weights with replay/OOS evidence, SPY must
reconcile its rule version and aggregate holdout, LPPL-derived actions must
match the live/replay model fingerprint and current own-market threshold, and
regional actions must match the validated current factor or LPPL trigger.

`/api/health` audits that decision contract through `dashboardContract`. A
legacy snapshot that exposes a numeric allocation band without the required
evidence is degraded, and a health response that lacks the audit is treated by
the command-line checker as a stale service process that must be reloaded.

The regional layer cannot promote raw LPPL status or same-sample regional
factor diagnostics into a numeric allocation. Raw bubble states remain
context; high-confidence regional action requires a production-eligible LPPL
model whose own-market threshold is currently triggered, or a future frozen-
spec independent factor holdout whose current factor reading has breached its
validated threshold. Health alerts and cross-region rotation recheck that full
trigger chain and ignore legacy serialized breach/favor/reduce flags. Regional
factor selection is corrected over a
fixed 23-hypothesis market-factor family and a fixed 6-hypothesis market-
composite family, with unavailable members retained as `p=1`. Regional
composite calibration purges every 91-day label whose actual rolled market
endpoint reaches the OOS boundary. Unvalidated numeric bands and rotation tilts
are retained only as `contextBand` / `contextTilt`; binding allocation fields
remain empty or balanced.

Forward-IC validation treats overlapping labels as dependent observations.
The 3-month confidence interval uses a deterministic circular moving-block
bootstrap, its p-value uses an order-preserving circular-shift test, and
Benjamini-Hochberg uses the unrounded randomization p-value across pre-
registered factor families. Alert streaks count as first-alert, fixed-horizon
episodes; fold stability requires at least two non-overlapping horizon windows
per fold; lead/lag classification uses the pre-registered 91-day endpoint on a
common OOS sample with no full-history fallback. Underpowered inference remains
visible for research but cannot set `robust` or `actionable`.

Source ingestion rejects future observations, future Treasury records, missing
or future Cboe timestamps, incomplete current monthly/quarterly reference
periods, and current-day OHLC rows without an exchange-close guarantee. Public
FRED history is explicitly tagged as latest-vintage and
`validationEligible=false`; it remains usable for descriptive charts but not
as point-in-time validation evidence without ALFRED-style vintages.

Equity freshness uses the shared U.S. session calendar in
`treasury_data/equity_calendar.py` for both runtime health and the lightweight
updater, including exchange holidays and the post-close availability lag.
Required OHLCV inputs must not only align with SPY; each must also reach the
expected completed U.S. session, so a uniformly old but internally aligned
cache fails the absolute freshness gate. Forward event calendars use
`freshnessBasis=calendar-horizon`: their latest date is a coverage endpoint,
not a future observation, and the source becomes stale only when that horizon
no longer covers the dashboard as-of date.

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
- Factor-group domain: `the-dial-treasury-v1/treasury_data/factor_groups.py`,
  with shared parsing/formatting in `treasury_data/dashboard_format.py`; both
  are re-exported by the data builder facade.
- Investment-view domain: `the-dial-treasury-v1/treasury_data/investment_views.py`,
  re-exported by the data builder facade.
- Public-source parsers: `the-dial-treasury-v1/treasury_data/sources.py`.
- Local server/API: `the-dial-treasury-v1/scripts/serve.py`.
- Manual refresh entrypoint: `the-dial-treasury-v1/scripts/update_data.py`.
- Equity/LPPL lightweight refresh entrypoint:
  `the-dial-treasury-v1/scripts/update_equity_risk.py`.
- Smoke check: `the-dial-treasury-v1/scripts/smoke_check.py`.
- Dashboard contract: `the-dial-treasury-v1/treasury_data/dashboard_contract.py`
  and `the-dial-treasury-v1/schema/dashboard-v1.schema.json`.
- Bounded source orchestration: `the-dial-treasury-v1/treasury_data/live_sources.py`.

The local server exposes the existing dashboard slice APIs, history APIs, and
`POST /api/update`. JSON GETs support ETag revalidation, publication is atomic
and cross-process locked, partial market refreshes use an incremental cache,
and SQLite retains compressed recent payloads plus long-lived normalized
metrics. The refactor does not rename the active directory.

## Repository State

The workspace root is now a git repository on `main`, tracking:

```text
https://github.com/c3msu/MLM
```

Tracked source includes the active runtime, docs, archive metadata and legacy
reference files, plus `the-dial-treasury-v1/data/dashboard.json` as the
HTTP/static serving snapshot used by the local server and smoke checks. Direct
`file://` opening uses the embedded static fallback in `app.js`.

Runtime-local artifacts are intentionally not tracked: SQLite history stores,
database sidecars, rejected refresh candidates, logs, Playwright scratch
output, Python caches, `.DS_Store`, and local content overrides.

## Known Limits

- The default runtime is local. Static/Vercel deployment remains out of scope
  for the current codebase.
- Paid or licensed feeds such as MOVE, swaps, futures basis, and market depth
  remain documented boundaries unless credentials and redistribution rights are
  provided.
- `the-dial-treasury-v1/data/dashboard.json` is intentionally tracked as a
  serving snapshot. `the-dial-treasury-v1/data/history.sqlite3` and other
  SQLite/DB files are not tracked.
- `scripts/smoke_check.py` fails on any real-source `error` row. At the moment
  Treasury Fiscal Data `Debt Subject to Limit` can intermittently return curl
  exit 7; keep that visible rather than suppressing the source-status failure.
  Required Nasdaq equity OHLCV rows must also be `ok`; symbol-specific
  warnings are reported explicitly by the smoke check.
