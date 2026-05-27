from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from treasury_data.history_backfill import backfill_public_history  # noqa: E402
from treasury_data.history_store import DEFAULT_HISTORY_DB  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill public Treasury/FRED history into SQLite")
    parser.add_argument("--history-db", type=Path, default=DEFAULT_HISTORY_DB)
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args(argv)

    summary = backfill_public_history(args.history_db, years=args.years)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
