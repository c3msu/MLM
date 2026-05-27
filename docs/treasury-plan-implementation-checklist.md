# Treasury Dashboard Plan Checklist

Source plan: `docs/网站复现项目计划.pdf`

Target system: `the-dial-treasury-v1/`, the active MarcoMonitor runtime.

## Implementation Status

| Plan area | Status | Current implementation |
| --- | --- | --- |
| Single active Treasury runtime | Done | `the-dial-treasury-v1/` is the only active runtime; older implementations are archived under `archive/legacy/2026-05-25/`. |
| Original-site compact UI | Done | Single-page dashboard with summary, curve, decomposition, scorecard, policy, supply, positioning, cross-market, events/news, and investment views. |
| Internationalisation | Done | Static UI shell and dynamic labels support Chinese/English switching through `i18n.js`; source/data payload text stays faithful when no deterministic translation is available. |
| Editable factor scorecard | Done | Browser-side score and group-weight edits persist through `localStorage`. |
| Treasury curve data | Done | U.S. Treasury daily yield curve XML. |
| Treasury volatility proxy | Done | 20-day annualized 10Y realized volatility computed from U.S. Treasury daily curve history; MOVE index itself remains a licensed-data boundary. |
| FRED macro/liquidity data | Done | TIPS, breakevens, DFF, SOFR, TGA, WALCL, TREAST/SOMA Treasury holdings, WRESBAL bank reserves, RRP, CPI, PCE, core PCE, Dallas Fed Trimmed Mean PCE, PPI, unemployment, payrolls, GDP. |
| NY Fed ACM term premium | Done | `ACMTermPremium.xls`, daily sheet, `ACMTP10` and `ACMRNY10`. |
| Fed SEP projections | Done | Federal Reserve projection-materials HTML, latest official federal-funds-rate median path; transient Board-site failures are surfaced as warnings because this source is low frequency. |
| Fed Funds futures proxy | Done | Stooq public `ZQ.F` quote CSV supplies a real 30-Day Fed Funds futures proxy; dashboard probabilities remain transparently model-converted rather than official CME FedWatch. |
| TreasuryDirect auctions | Done | Auctioned securities endpoint with recent size, yield, bid-to-cover, rating, and bid-to-cover historical percentile over the available endpoint sample; live auctioned endpoint timeouts fall back to SQLite backfilled bid-to-cover observations. |
| Treasury QRA / quarterly refunding | Done | Official Treasury most-recent QRA documents, policy statement, financing estimates, next QRA dates, borrowing/cash-balance assumptions, coupon/bill stance, TGA peak, and buyback size. |
| Debt ceiling situation | Done | Treasury Fiscal Data DTS `Debt Subject to Limit` table computes statutory debt limit, debt subject to limit, and remaining headroom. |
| Official event calendar | Done | Federal Reserve FOMC calendar with Chicago Fed official-system fallback, FRED BLS macro release calendar for CPI/PPI/Employment Situation, BEA release schedule for GDP/PCE, TreasuryDirect announced auctions, and Treasury QRA dates feed the event timeline. |
| Official news flow | Done | U.S. Treasury press-release page and Federal Reserve press-release RSS feed official public headlines into the news panel when reachable; data-derived market snapshots remain the fallback. |
| NY Fed primary dealer stats | Done | NY Fed Markets API provides weekly UST dealer positions, transactions, repo financing, borrowed securities, and lent securities where disclosed. |
| CFTC positioning | Done | CFTC financial futures COT zip, latest Treasury futures leveraged/asset-manager/dealer net positioning. |
| TIC foreign demand | Done | TIC table 5 text, latest major foreign holders, total and official holdings. |
| Cross-market panel | Done | FRED public proxies for global yields, SPX, VIX, dollar, credit OAS, CPI, PCE, core PCE, Dallas Fed Trimmed Mean PCE, WTI, OVX, GVZ, plus Stooq public `XAUUSD` gold spot. Section 07 also includes a dynamic history chart with group/series/range controls backed by SQLite history and `/api/history/series`. |
| Historical percentiles and Conditions Score | Done | The Dial-style percentile block plus a bhadial-compatible 47 tracked factor / 30 scored factor / 7 module Conditions Score. Module roll-up weights follow public factor coverage with overlap adjustment; Funding uses EMA(5); target-distance, shock-only, deviation, and bounded risk-signal methods are explicit. ETF-exact factors remain documented public proxies. |
| Conclusion credibility and weight audit | Done | Scorecard duration/curve conclusions scale each factor by normalized module weight and module factor count. The audit discounts proxy, modeled, and manual-placeholder evidence and surfaces whether weight changes are justified. |
| REST API | Done | Local Python server exposes dashboard slices for curve, decomposition, Fed path, scorecard, policy, auctions, positioning, cross-market, events, news, ideas, and source status. It supports ISO date-range filters on dated list endpoints and `format=csv` exports for dashboard slice routes. Health, history, and update endpoints remain JSON-only. |
| Historical persistence | Done | Successful refreshes persist full dashboard snapshots plus normalized curve, scorecard, percentile, and cross-market metrics to local SQLite `data/history.sqlite3`; `/api/history`, `/api/history/snapshots`, `/api/history/stats`, and `/api/history/series` expose read-only status and series views. Latest 5-year history backfill runs are recorded and surfaced through `/api/health`. |
| Static deployment API mirror | Deferred | Local deployment is the current target; static hosting and Vercel files were removed from this pass. |
| Content/admin override | Done | Optional `content/overrides.json`; sample in `content/overrides.example.json`. |
| Daily background update | Done | `scripts/serve.py --daily-at HH:MM` and macOS LaunchAgent installer. Startup refresh and manual `POST /api/update` refreshes run in the background, data-file writes are atomic, source-error candidates are copied to `dashboard.failed.json`, and candidates missing core content do not overwrite the last healthy dashboard. |
| Local monitoring | Done | `/api/health` reports update timestamps, source-status counts, real error sources, and latest history-backfill status. Critical or degraded backfill errors make health non-zero; warning-severity source errors remain in backfill metadata. `scripts/check_health.py` and `scripts/install_health_agent.py` provide a daily local health check and optional macOS notification after the update window. |
| CI scheduled update template | Deferred | Not needed for local deployment; macOS LaunchAgent is the active scheduler. |
| Deployment documentation | Done | `docs/treasury-deployment.md`. |
| User/developer authoring guide | Done | `docs/treasury-authoring-guide.md` explains daily use, local health checks, narrative overrides, adding public sources, adding scorecard factors, verification, and data-boundary rules. |

## Boundaries

- Fed SEP medians are official low-frequency data. Fed path probabilities remain model estimates, now informed by public `ZQ.F` Fed Funds futures plus curve/macro data. Official CME FedWatch or OIS-implied probabilities need CME/licensed market-data access.
- Official Treasury/Fed headlines are fetched from public sources. Full-text real-time market news remains manual/curated through `content/overrides.json`; reliable redistribution usually requires licensed feeds.
- Fed/FOMC, BLS CPI/PPI/employment release dates via FRED, BEA GDP/PCE release dates, Treasury auction, and Treasury QRA events are official/public-source fields; broader private market event calendars are not connected in this local version.
- MOVE index itself, bond-market depth, bid-ask, swaps, futures basis, and on/off-the-run spread data are left as documented paid-data boundaries unless a licensed source is provided. A public 10Y realized-volatility proxy is connected for the sentiment/liquidity scorecard.
- NY Fed primary dealer statistics are real weekly public data but are voluntarily reported by dealers and are not intraday/real-time.

## Verification Checklist

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 python3 -m unittest discover -s the-dial-treasury-v1/tests`
- `node --check the-dial-treasury-v1/i18n.js`
- `node --check the-dial-treasury-v1/app.js`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 python3 the-dial-treasury-v1/scripts/update_data.py --output the-dial-treasury-v1/data/dashboard.json`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 python3 the-dial-treasury-v1/scripts/smoke_check.py --path the-dial-treasury-v1/data/dashboard.json`
- Browser check at `http://127.0.0.1:8451/#crossmarket`, including section-07
  group switching and 1Y/3Y/5Y range controls.
