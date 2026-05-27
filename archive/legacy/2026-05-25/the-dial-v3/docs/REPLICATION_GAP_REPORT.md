# Replication Gap Report (Initial)

This is the initial implementation gap report for the real-data pipeline in `the-dial-v3`.

## Delivered in this pass

- 47-factor canonical catalog (`30 scored + 17 display-only`).
- Multi-source raw ingestion (`FRED`, `CBOE`, `Stooq`).
- Raw/factor/pipeline database tables and snapshot tables.
- Deterministic factor scoring (5-year percentile + direction mapping).
- `/api/v1` dashboard/modules/factor endpoints with legacy `/api/*` compatibility.
- Dashboard page now prefers backend API and falls back to mock only on failure.

## Known gaps vs full bhadial parity

- Factor formulas are implemented as a practical proxy set, not a byte-for-byte replica of the production bhadial formulas.
- Some public symbols may be intermittently unavailable (especially `CBOE` endpoints), which can produce `stale`/`missing` factors.
- Distribution and driver endpoints provide stable utility output, but may differ from the production API’s exact ranking logic.
- Module detail pages in `frontend/module-*.html` are still mostly static/mock and are not fully wired to the new factor APIs.

## Recommended next verification steps

1. Run `/api/v1/update` in a network-enabled environment and inspect `pipeline_runs`.
2. Compare `/api/v1/dashboard` and `/api/v1/modules/{id}` payloads against the target production schema.
3. Replace proxy formulas with exact bhadial formulas once the canonical definitions are provided.
