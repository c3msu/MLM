# Real Data Source Map

This document lists the concrete source mapping used by the `the-dial-v3` real-data pipeline.

## Source layers

- `fred` (CSV endpoint, no API key): macro time series and rates.
- `cboe` (public CSV): volatility indices (`VIX`, `VXV`, `OVX`).
- `stooq` (public CSV): ETF proxies (`SPY`, `TLT`, `IWM`, `KRE`, `LQD`, `IEF`, `HYG`, `IEI`).

## Factor dependency format

Dependencies are encoded as `source:symbol` in `backend/factor_catalog.py`.

Examples:

- `fred:WALCL`
- `cboe:VIX`
- `stooq:spy.us`

## Storage

Raw data lands in `raw_series` with:

- `source`
- `symbol`
- `date`
- `value`
- `frequency`
- `fetched_at`
- `status`

Computed factors land in:

- `factor_series` (history)
- `factor_latest` (latest snapshot)

## Notes

- The pipeline writes stale/missing status instead of fabricating values.
- `sp500_data` is synced from `stooq:spy.us` and exposed for dashboard chart overlay.
