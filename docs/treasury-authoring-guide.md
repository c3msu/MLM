# Treasury Dashboard Authoring Guide

Target app: `the-dial-treasury-v1/`, the only active MarcoMonitor runtime.
Historical implementations are archived under `archive/legacy/2026-05-25/`.

This guide covers local operation, narrative edits, and adding new factors
without breaking the real-data pipeline.

## Daily Use

Open the local dashboard:

```text
http://127.0.0.1:8451/
```

Check service health:

```bash
python3 the-dial-treasury-v1/scripts/check_health.py --url http://127.0.0.1:8451/api/health
```

Refresh data manually:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/update_data.py \
  --output the-dial-treasury-v1/data/dashboard.json
```

## Editing Narrative Text

Prefer `the-dial-treasury-v1/content/overrides.json` for analyst-editable
content. Start from:

```bash
cp the-dial-treasury-v1/content/overrides.example.json \
  the-dial-treasury-v1/content/overrides.json
```

Supported override areas:

- `ideas`: replace investment-view cards.
- `events`: add manual events when no public calendar source exists.
- `news`: add curated headlines when redistribution rights are clear.
- `groupWeights`: override scorecard group weights.
- `factorOverrides`: override individual factor scores or notes.

Keep manual entries clearly separated from public-source data. If a value is
not pulled from a public endpoint, describe it as manual, modeled, or curated.

## Adding a Public Data Source

1. Add a parser/fetcher in `the-dial-treasury-v1/treasury_data/sources.py`.
2. Add parser tests in `the-dial-treasury-v1/tests/test_sources.py` using a
   minimal saved HTML/CSV/JSON fragment.
3. Wire the source into `build_live_dashboard()` in
   `the-dial-treasury-v1/treasury_data/build_dashboard.py`.
4. Add a `sourceStatus` row with `status: ok` or `status: error`.
5. Use the value in `build_dashboard_from_inputs()` and add a focused test in
   `the-dial-treasury-v1/tests/test_build_dashboard.py`.
6. Document the source in `the-dial-treasury-v1/README.md`,
   `docs/treasury-deployment.md` when the API/runtime changes, and
   `docs/treasury-plan-implementation-checklist.md`.

Rules:

- Prefer official government, central-bank, exchange, or FRED public endpoints.
- Keep paid/licensed feeds out of the default pipeline unless credentials and
  redistribution rights are provided.
- Preserve source dates. Do not relabel stale monthly/weekly data as daily.
- If a factor is modeled, surface it as `modeled` or explain the proxy in the
  factor note.

## Adding a Scorecard Factor

Factors live in the `groups` list assembled by
`build_dashboard_from_inputs()`:

```python
{
    "n": "Factor name",
    "tag": "latest value / source date",
    "v": "qualitative state",
    "score": -2,
    "curve": 1,
    "note": "Why this matters and what source supports it.",
}
```

Score convention:

- `+2`: strongly bullish duration.
- `+1`: mildly bullish duration.
- `0`: neutral or mixed.
- `-1`: mildly bearish duration.
- `-2`: strongly bearish duration.

`curve` is optional:

- Positive values support steepeners.
- Negative values support flatteners.
- Omit it when the factor has no clear curve implication.

Before adding a factor, add a test that proves the factor appears with the
right latest value, source note, and score sign.

## Adding a Cross-Market History Series

Section 07 reads its selectable history list from `cross.historySeries` in
`build_cross_market_history_series()`. Add the target there with its
`category`, SQLite metric `name`, API `label`, display name, unit, and public
source. The frontend then uses `/api/history/series` and `/api/history/stats`
instead of a separate bespoke endpoint.

If the series is essential to the cross-market view, extend
`scripts/smoke_check.py` and `tests/test_smoke_check.py` so missing history
coverage fails verification. Keep category/name/label aligned with the rows
written by `backfill_history.py` or the refresh snapshot persistence.

## Maintaining Equity And LPPL Risk Blocks

`spyEarlyWarning`, `equityShortTermRisk`, and `globalLpplRisk` are separate
payload contracts:

- `spyEarlyWarning` is the macro/SPY medium-horizon overlay.
- `equityShortTermRisk` is the daily tactical SPY risk score.
- `globalLpplRisk` is an independent LPPL research indicator and must not be
  folded into `equityShortTermRisk` unless a later backtest explicitly proves a
  low-weight integration.

When changing `globalLpplRisk`:

1. Keep `scoreUse: "independent"` and preserve the top-level
   `summary`, `indices`, `history`, `backtest`, `indexValidation`, and
   `lookAheadGuard` fields.
2. Label ETF proxies explicitly. Current public proxies are `EWY` for
   KOSPI/Korea, `EWH` for Hang Seng/Hong Kong, `EWT` for Taiwan Weighted, and
   `EWJ` for Nikkei/Japan.
3. Do not fabricate missing direct index histories. Missing sources should
   produce unavailable rows, not synthetic scores.
4. Keep `indexValidation.rows` aligned with visible index cards. Each available
   index should carry `validation` and `effectiveWeightMultiplier` so the UI
   can show own-market 15D historical precision beside the LPPL fit.
5. Update `scripts/smoke_check.py` and `tests/test_smoke_check.py` whenever the
   LPPL contract changes.

Use `scripts/update_equity_risk.py` for a lightweight refresh when only
`equityShortTermRisk` and `globalLpplRisk` need new daily OHLCV inputs.

## Maintaining Investment View Rules

Section 09 investment-view cards are generated by deterministic rules in
`build_ideas()`, then optionally edited in-browser or replaced through
`content/overrides.json`. Keep the rules scenario-aware: duration, curve,
front-end carry, and breakeven views should change when inflation, 2Y policy
pricing, QRA supply, curve level, energy, or BEI valuation move into a different
environment.

Cards also carry a compact confidence overlay from `conclusionAudit`. If you
change scorecard source modes, weights, or idea generation, verify that
`confidenceLevel`, `confidenceLabel`, and `confidenceNote` still describe the
evidence quality behind the visible view.

Cards also carry an `equityImpact` block. It summarizes historical S&P 500
price-index proxy behavior for past observations with the same Conditions
Score level bucket and 3-month score-change bucket. Keep this block historical:
use the stored `macroLiquidityEquity.series` sample, preserve the minimum
sample gate, and avoid wording that presents the result as a prediction.
Manual `ideas` overrides replace generated cards as supplied. If an override
omits confidence or `equityImpact`, the API reflects that manual shape; the
frontend displays an explicit low-confidence placeholder instead of generating
historical statistics from override text.

When changing this layer, add or update scenario tests in
`tests/test_build_dashboard.py`. See `docs/investment-view-rule-audit.md` for
the current rule map, feasibility gates, and remaining boundaries.

## Local Verification

Run this set before treating a change as ready:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 -m unittest discover -s the-dial-treasury-v1/tests

node --check the-dial-treasury-v1/i18n.js
node --check the-dial-treasury-v1/app.js

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/update_data.py \
  --output the-dial-treasury-v1/data/dashboard.json

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=the-dial-treasury-v1 \
  python3 the-dial-treasury-v1/scripts/smoke_check.py \
  --path the-dial-treasury-v1/data/dashboard.json

python3 the-dial-treasury-v1/scripts/check_health.py \
  --url http://127.0.0.1:8451/api/health
```

For UI changes, open the local server and verify both Chinese and English
states:

```text
http://127.0.0.1:8451/
```

## Data Boundary Checklist

Before marking a source as real:

- The URL is public and stable enough for daily local refresh.
- The parser stores the latest source date.
- The dashboard shows the source name or proxy explanation.
- Historical percentile ranks state their window and sample source.
- `sourceStatus` reports failures instead of silently falling back.
- Required equity OHLCV rows used by `equityShortTermRisk` must be `ok`; smoke
  verification reports the affected symbol if a transient Nasdaq quote timeout
  leaves a warning row.
- `/api/health` becomes degraded when a required real source fails.
- `/api/health` includes latest history-backfill status. Critical or degraded
  backfill source errors appear as health warnings; warning-severity source
  errors remain in `history.latestBackfill.sourceErrors` without making health
  fail.
- A refresh candidate with source errors is copied to
  `data/dashboard.failed.json` for inspection. It still becomes the served
  snapshot and is saved to history when core curve, scorecard, and Conditions
  Score trend content are present; candidates missing that core content do not
  overwrite the last healthy `data/dashboard.json`.
- Successful refreshes are persisted into `data/history.sqlite3`; inspect
  `/api/history` or `/api/history/snapshots` to confirm the local history store
  is growing.
- Cross-market historical charts are declared in `cross.historySeries`; any
  added section-07 series must already exist in SQLite history or be clearly
  unavailable in the UI.
- Independent risk overlays such as `globalLpplRisk` must state whether they
  affect another score. The current LPPL block is research-only and independent
  from `equityShortTermRisk`.

If any item fails, keep the item in the documented boundary list instead of
presenting it as a live public source.

## Conditions Score Alignment

The headline 0-100 score is a bhadial-compatible Conditions Score, not the old
13-component liquidity-only composite. Keep the active factors at 30 scored
factors across the seven public modules: Liquidity, Funding, Treasury, Rates,
Credit, Risk, and External.

When changing this layer:

- Preserve the public scoring semantics: `level_percentile`, `deviation`,
  `target_distance`, `shock_only`, and `risk_signal`.
- Keep Funding smoothed with EMA(5).
- Keep module roll-up weights aligned with the public factor-coverage/overlap
  method, and surface `macroLiquidity.benchmark` when the public bhadial score
  can be fetched.
- Keep `macroLiquidity.scoredFactorCount == 30`,
  `macroLiquidity.totalFactorCount == 47`,
  `macroLiquidity.moduleCount == 7`, and
  `meta.bhadialCompatibility.coverage.scorecardFactorCount == 30`.
- Mark ETF-relative factors as public proxies unless exact ETF history is added.

## Conclusion And Weight Audit

The visible duration/curve stance is separate from the 0-100 Conditions Score.
It is derived from editable scorecard factors with this contribution rule:
`factor score * normalized group weight / factor count`. Use this same
normalization for top-driver explanations so large modules do not overstate a
single factor.

The dashboard also writes `conclusionAudit`. It discounts `proxy-public`,
`modeled`, and `manual-placeholder` inputs when calculating evidence quality and
flags concentration when one factor carries too much of the conclusion. Treat a
medium or low audit result as a narrative constraint: weaken conclusion wording
or improve the source before increasing that factor's weight.

For licensed indicators such as MOVE, swaps, futures basis, or market depth,
prefer a clearly named public proxy only when the proxy can be computed from
public data. Example: the sentiment/liquidity scorecard uses 20-day annualized
10Y realized volatility from Treasury curve history, while still documenting
MOVE itself as a licensed-data boundary.
