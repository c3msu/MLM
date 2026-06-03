# SPY Early Warning Index

## Purpose

`spyEarlyWarning` is an equity-risk overlay for SPY/SPX exposure. It is built
from existing dashboard factors rather than a new data feed. The score is
0-100, where higher values mean greater 1-3 month drawdown risk.

This indicator is separate from the headline Conditions Score. Conditions
Score reads higher as the macro backdrop becomes more supportive. The SPY Early
Warning Index reads higher as drawdown risk rises.

## Construction

Inputs:

- `macroLiquidity.score`: current Conditions Score level.
- `macroLiquidityEquity.currentSignal.score3mChange`: 3-month Conditions Score
  deterioration or improvement.
- `macroLiquidity.components`: existing 30 scored factor components.

Risk sleeves:

- Macro level: low Conditions Score creates a risk floor.
- Macro deterioration: falling 3-month Conditions Score raises warning risk,
  especially after a high-score state.
- Liquidity stress: net liquidity, bank reserves, 13-week net-liquidity
  momentum, TGA deviation, and ON RRP buffer risk.
- Funding stress: SOFR corridor, EFFR-IORB, CP-TBill, and fragmentation.
- Rates/curve stress: 30Y-10Y, 10Y realized volatility, curve curvature, real
  rates, real curve, and 10Y breakeven.
- Credit/volatility stress: NFCI, credit preference proxies, regional banks,
  VIX, VIX term structure, risk-vs-safe, and high-beta preference.
- External shock: dollar, dollar volatility, WTI, oil-volatility deviation, and
  natural gas.

Calibration layer:

- `baseScore` is the weighted sleeve score before nonlinear calibration.
- The displayed `score` applies a 1.08x risk scale to the base score, then adds
  explicit `amplifiers` when historically fragile patterns appear and
  subtracts explicit `dampeners` when a raw warning is likely to be stale
  post-selloff noise.
- Current amplifiers are severe 3-month deterioration, high-score rollover,
  low-score fragility without clear improvement, low-score improvement stall,
  and rally fragility when SPX has already advanced while macro momentum rolls
  over. A narrower strong-rally rollover confirmation adds another small boost
  when SPX has rallied at least 9% over 3 months, Conditions Score is still
  above 42, and the 3-month Conditions Score change is already negative enough
  to confirm deterioration.
- Current dampeners include post-selloff exhaustion: if SPX has already fallen
  more than 6% over the trailing 3 months while Conditions Score has not
  deteriorated by 10 points or more, the score receives a `-10` offset.

Allocation map:

- `0-39`: Constructive, normal or modestly higher equity exposure.
- `40-59`: Neutral, hold core exposure and avoid chasing.
- `60-74`: Caution, reduce new equity risk and consider protection.
- `75-100`: De-risk, cut beta or add protection.

## Initial Evidence

Diagnostics used the existing 5-year monthly S&P 500 price-index lead-study
sample in `macroLiquidityEquity.series`.

Key observations from the current local sample:

- Usable monthly rows: 54, from 2021-09-30 through 2026-02-27.
- Drawdown events: 24 rows had 3-month max drawdown at or below -5%, 14 rows at
  or below -8%, and 10 rows at or below -10%.
- A simple `score <= 45` rule was too broad for return warning. It caught many
  drawdowns but produced many false positives.
- `score > 45 and 3M score change <= -2.9` was more useful for negative
  3-month forward returns, with precision and recall both near 0.57 in the
  initial diagnostic.
- The first continuous-score version was too compressed, with 57 usable
  forward-tested rows ranging only from 37.1 to 58.9. The nonlinear calibration
  expands that range to 40.1-81.6, so 2022-03-31 and 2022-04-29 move into
  Caution/De-risk territory before the worst 3-month drawdowns.
- The second calibration pass adds a post-selloff dampener. On the same 57
  forward-tested rows, a `>=60` Caution threshold keeps 8 true drawdown warnings
  while reducing false positives from 16 to 12; precision improves from about
  0.33 to 0.40 while recall remains 0.57.
- The third calibration pass adds the narrow strong-rally rollover confirmation.
  It moves 2023-07-31 from `57.8` to `60.8` before the following -10.28% 3-month
  max drawdown. At the `>=60` Caution threshold, true warnings improve from 8 to
  9 and false positives stay at 12; precision is about 0.43 and recall about
  0.64 on the 57 usable forward-tested rows.
- The fourth calibration pass adds low-score improvement-stall confirmation.
  It moves 2025-01-31 and 2025-03-31 from `56.8` to `60.8` when Conditions
  Score remains at or below 42, the 3-month change is only 0 to +0.5, and SPX
  has not already fallen more than 5% over the trailing 3 months. At the `>=60`
  threshold, true warnings improve from 9 to 11 while false positives remain
  12; precision is about 0.48 and recall about 0.79.
- Top high-risk factor families for 3-month drawdown diagnostics included VIX,
  CP-TBill spread, curve inversion, NFCI, WTI/oil-volatility shock, and broad
  external stress.

The indicator therefore combines level, deterioration, and risk sleeves instead
of using the headline Conditions Score alone.

## Current Snapshot

The tracked `data/dashboard.json` snapshot dated 2026-06-01 produces:

- Score: `43.4`
- Base score: `40.2`
- Regime: `Neutral`
- Stance: `持有/控仓`
- Amplifiers: none.
- Dampeners: none.
- Summary: macro score is improving, so the nonlinear layer does not convert
  the current low/mid score into a de-risk signal.

This is intentionally not a strong de-risk signal: the current 3-month
Conditions Score change is positive, while credit/volatility stress is not the
dominant pressure sleeve.

## Boundaries

- This is a risk-control overlay, not a standalone return forecast.
- It uses FRED S&P 500 price index as a SPY proxy, without dividends, intraday
  drawdowns, taxes, trading costs, or ETF-specific frictions.
- The first calibration is based on the currently available 5-year monthly
  sample, so thresholds should be revisited as more history is persisted.
