"""The Dial - real data and scoring service."""

from __future__ import annotations

import csv
import math
import os
import sqlite3
import statistics
from bisect import bisect_right
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from factor_catalog import FACTOR_CATALOG, MODULE_META, FactorDef, factor_map, module_factors
from data_sources import fetch_cboe_history, fetch_fred_csv, fetch_stooq_daily

try:
    from config import MODULE_WEIGHTS as CONFIG_MODULE_WEIGHTS
except Exception:  # pragma: no cover - defensive fallback
    CONFIG_MODULE_WEIGHTS = {
        "liquidity": 0.20,
        "funding": 0.15,
        "treasury": 0.15,
        "rates": 0.15,
        "credit": 0.15,
        "risk": 0.10,
        "external": 0.10,
    }


MODULE_IDS: Tuple[str, ...] = tuple(MODULE_META.keys())
PERCENTILE_WINDOW_DAYS = 1825
HISTORY_DEFAULT_DAYS = 1825

FREQUENCY_STALE_DAYS = {
    "d": 7,
    "w": 21,
    "m": 45,
    "q": 120,
}

RAW_FREQUENCY_HINTS = {
    "WALCL": "w",
    "RESBALNS": "w",
    "M2SL": "m",
    "FEDFUNDS": "m",
    "MPRIME": "m",
    "CPIAUCSL": "m",
    "OBFR": "d",
}


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _score_to_color(score: Optional[float]) -> str:
    if score is None:
        return "gray"
    if score >= 66:
        return "green"
    if score <= 33:
        return "red"
    return "yellow"


class DataService:
    def __init__(self, db_path: str, data_dir: str):
        self.db_path = db_path
        self.data_dir = data_dir
        self._ensure_data_dir()
        self._factor_map = factor_map()
        self._raw_cache: Dict[str, List[Tuple[str, float]]] = {}

    # ---------------------------------------------------------------------
    # Storage / setup
    # ---------------------------------------------------------------------

    def _ensure_data_dir(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.execute("PRAGMA busy_timeout = 60000")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_column(self, cursor: sqlite3.Cursor, table: str, column_def: str) -> None:
        column_name = column_def.split()[0]
        cursor.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in cursor.fetchall()}
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")

    def init_database(self) -> None:
        """Initialize SQLite tables (backward compatible)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS indicators (
                series_id TEXT,
                date TEXT,
                value REAL,
                module TEXT,
                name TEXT,
                unit TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (series_id, date)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS module_scores (
                module TEXT,
                date TEXT,
                score REAL,
                percentile REAL,
                change_1w REAL,
                change_1m REAL,
                factors_count INTEGER DEFAULT 0,
                scored_factors_count INTEGER DEFAULT 0,
                last_updated TEXT,
                PRIMARY KEY (module, date)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS overall_scores (
                date TEXT PRIMARY KEY,
                score REAL,
                interpretation TEXT,
                trend TEXT,
                percentile REAL,
                healthy_modules INTEGER,
                critical_modules INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sp500_data (
                date TEXT PRIMARY KEY,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                normalized REAL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_series (
                source TEXT,
                symbol TEXT,
                date TEXT,
                value REAL,
                frequency TEXT,
                fetched_at TEXT,
                status TEXT,
                PRIMARY KEY (source, symbol, date)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS factor_series (
                factor_id TEXT,
                module_id TEXT,
                date TEXT,
                raw_value REAL,
                percentile_5y REAL,
                score REAL,
                color TEXT,
                data_status TEXT,
                display_only INTEGER,
                PRIMARY KEY (factor_id, date)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS factor_latest (
                factor_id TEXT PRIMARY KEY,
                module_id TEXT,
                date TEXT,
                raw_value REAL,
                percentile_5y REAL,
                score REAL,
                color TEXT,
                data_status TEXT,
                display_only INTEGER,
                updated_at TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                message TEXT
            )
            """
        )

        self._ensure_column(cursor, "module_scores", "factors_count INTEGER DEFAULT 0")
        self._ensure_column(cursor, "module_scores", "scored_factors_count INTEGER DEFAULT 0")
        self._ensure_column(cursor, "module_scores", "last_updated TEXT")
        # SQLite ALTER TABLE does not allow non-constant defaults.
        self._ensure_column(cursor, "overall_scores", "created_at TEXT")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_series_symbol_date ON raw_series(source, symbol, date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_factor_series_module_date ON factor_series(module_id, date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_factor_latest_module ON factor_latest(module_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_module_scores_date ON module_scores(date)")

        conn.commit()
        conn.close()

    def bootstrap_defaults(self) -> None:
        """Seed deterministic placeholders so APIs stay stable before first full update."""
        today = _today_str()
        now = _now_iso()

        conn = self._get_connection()
        cursor = conn.cursor()

        for factor in FACTOR_CATALOG:
            cursor.execute(
                """
                INSERT OR IGNORE INTO factor_latest
                (factor_id, module_id, date, raw_value, percentile_5y, score, color, data_status, display_only, updated_at)
                VALUES (?, ?, ?, NULL, NULL, NULL, 'gray', 'missing', ?, ?)
                """,
                (factor.id, factor.module, today, int(factor.display_only), now),
            )

        for module_id in MODULE_IDS:
            cursor.execute(
                """
                INSERT OR IGNORE INTO module_scores
                (module, date, score, percentile, change_1w, change_1m, factors_count, scored_factors_count, last_updated)
                VALUES (?, ?, 50.0, 50.0, 0.0, 0.0, ?, ?, ?)
                """,
                (
                    module_id,
                    today,
                    len(module_factors(module_id)),
                    len([f for f in module_factors(module_id) if not f.display_only]),
                    today,
                ),
            )

        cursor.execute(
            """
            INSERT OR IGNORE INTO overall_scores
            (date, score, interpretation, trend, percentile, healthy_modules, critical_modules, created_at)
            VALUES (?, 50.0, '中性', 'stable', 50.0, 0, 0, ?)
            """,
            (today, now),
        )

        conn.commit()
        conn.close()

    # ---------------------------------------------------------------------
    # Raw data ingestion
    # ---------------------------------------------------------------------

    def _infer_frequency(self, source: str, symbol: str) -> str:
        if source == "cboe":
            return "d"
        if source == "stooq":
            return "d"
        return RAW_FREQUENCY_HINTS.get(symbol, "d")

    def _required_dependencies(self) -> Dict[str, List[str]]:
        deps_by_source: Dict[str, set] = {}
        for factor in FACTOR_CATALOG:
            for dep in factor.deps:
                source, symbol = dep.split(":", 1)
                deps_by_source.setdefault(source, set()).add(symbol)

        return {source: sorted(symbols) for source, symbols in deps_by_source.items()}

    def _save_raw_records(
        self,
        conn: sqlite3.Connection,
        source: str,
        symbol: str,
        frequency: str,
        records: Sequence[Dict[str, Any]],
    ) -> int:
        if not records:
            return 0

        cursor = conn.cursor()
        fetched_at = _now_iso()
        saved = 0

        for row in records:
            date_str = row.get("date")
            value = _safe_float(row.get("value"))
            if not date_str or value is None:
                continue

            cursor.execute(
                """
                INSERT OR REPLACE INTO raw_series
                (source, symbol, date, value, frequency, fetched_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'ok')
                """,
                (source, symbol, date_str, value, frequency, fetched_at),
            )
            saved += 1

            if source == "fred":
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO indicators
                    (series_id, date, value, module, name, unit)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (symbol, date_str, value, source, symbol, ""),
                )

        return saved

    def _save_sp500_from_stooq(self, conn: sqlite3.Connection, records: Sequence[Dict[str, Any]]) -> int:
        if not records:
            return 0

        closes = [_safe_float(row.get("value")) for row in records]
        closes = [v for v in closes if v is not None]
        if not closes:
            return 0

        min_close = min(closes)
        max_close = max(closes)
        span = max(max_close - min_close, 1e-9)

        cursor = conn.cursor()
        saved = 0
        for row in records:
            date_str = row.get("date")
            close = _safe_float(row.get("value"))
            if not date_str or close is None:
                continue
            normalized = ((close - min_close) / span) * 100
            cursor.execute(
                """
                INSERT OR REPLACE INTO sp500_data
                (date, open, high, low, close, volume, normalized)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (date_str, close, close, close, close, 0, normalized),
            )
            saved += 1

        return saved

    def _refresh_raw_sources(self) -> Dict[str, Any]:
        dependencies = self._required_dependencies()
        fetchers = {
            "fred": fetch_fred_csv,
            "cboe": fetch_cboe_history,
            "stooq": fetch_stooq_daily,
        }

        report: Dict[str, Any] = {
            "sources": {},
            "saved_rows": 0,
            "errors": [],
        }

        conn = self._get_connection()
        try:
            for source, symbols in dependencies.items():
                source_report = {
                    "requested": len(symbols),
                    "success": 0,
                    "failed": 0,
                    "symbols": {},
                }
                fetcher = fetchers.get(source)
                if not fetcher:
                    continue

                for symbol in symbols:
                    try:
                        records = fetcher(symbol)
                        frequency = self._infer_frequency(source, symbol)
                        saved = self._save_raw_records(conn, source, symbol, frequency, records)
                        source_report["symbols"][symbol] = {
                            "fetched": len(records),
                            "saved": saved,
                        }
                        report["saved_rows"] += saved
                        if saved > 0:
                            source_report["success"] += 1
                        else:
                            source_report["failed"] += 1
                    except Exception as exc:  # noqa: BLE001
                        source_report["failed"] += 1
                        source_report["symbols"][symbol] = {"fetched": 0, "saved": 0, "error": str(exc)}
                        report["errors"].append(f"{source}:{symbol} -> {exc}")

                report["sources"][source] = source_report

            # keep SP500 helper table in sync with stooq spy.us
            try:
                spy_rows = fetch_stooq_daily("spy.us")
                sp500_saved = self._save_sp500_from_stooq(conn, spy_rows)
                report["sources"].setdefault("stooq", {}).setdefault("symbols", {})["spy.us"] = {
                    "fetched": len(spy_rows),
                    "saved": sp500_saved,
                }
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"stooq:spy.us -> {exc}")

            conn.commit()
        finally:
            conn.close()

        self._raw_cache.clear()
        return report

    # ---------------------------------------------------------------------
    # Factor calculations
    # ---------------------------------------------------------------------

    def _load_raw_series(self, dep: str) -> List[Tuple[str, float]]:
        if dep in self._raw_cache:
            return self._raw_cache[dep]

        source, symbol = dep.split(":", 1)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, value
            FROM raw_series
            WHERE source = ? AND symbol = ? AND value IS NOT NULL AND status = 'ok'
            ORDER BY date ASC
            """,
            (source, symbol),
        )
        rows = [(row[0], float(row[1])) for row in cursor.fetchall() if row[1] is not None]
        conn.close()

        self._raw_cache[dep] = rows
        return rows

    def _align_series_asof(self, dep_series: Sequence[List[Tuple[str, float]]]) -> Tuple[List[str], List[List[Optional[float]]]]:
        all_dates = sorted({d for series in dep_series for d, _ in series})
        if not all_dates:
            return [], [[] for _ in dep_series]

        aligned: List[List[Optional[float]]] = []
        for series in dep_series:
            if not series:
                aligned.append([None] * len(all_dates))
                continue

            series_dates = [d for d, _ in series]
            series_values = [v for _, v in series]

            current: List[Optional[float]] = []
            for current_date in all_dates:
                idx = bisect_right(series_dates, current_date) - 1
                current.append(series_values[idx] if idx >= 0 else None)
            aligned.append(current)

        return all_dates, aligned

    def _formula_value(
        self,
        formula_id: str,
        dep_values: Sequence[Optional[float]],
        dep_arrays: Sequence[List[Optional[float]]],
        idx: int,
        params: Dict[str, Any],
    ) -> Optional[float]:
        if not dep_values:
            return None

        def has_all(count: int) -> bool:
            return len(dep_values) >= count and all(dep_values[pos] is not None for pos in range(count))

        window = int(params.get("window", 21))
        scale = float(params.get("scale", 1.0))

        if formula_id == "direct":
            return dep_values[0]

        if formula_id == "spread":
            if has_all(2):
                return dep_values[0] - dep_values[1]
            return None

        if formula_id == "ratio":
            if has_all(2) and dep_values[1] not in (0, None):
                return dep_values[0] / dep_values[1]
            return None

        if formula_id == "ratio_pct":
            if has_all(2) and dep_values[1] not in (0, None):
                return (dep_values[0] / dep_values[1]) * 100
            return None

        if formula_id == "net_liquidity":
            if has_all(3):
                return dep_values[0] - dep_values[1] - dep_values[2]
            return None

        if formula_id == "pct_change":
            arr = dep_arrays[0]
            if idx - window >= 0 and arr[idx] is not None and arr[idx - window] not in (None, 0):
                return ((arr[idx] / arr[idx - window]) - 1) * 100 * scale
            return None

        if formula_id == "diff":
            arr = dep_arrays[0]
            if idx - window >= 0 and arr[idx] is not None and arr[idx - window] is not None:
                return (arr[idx] - arr[idx - window]) * scale
            return None

        if formula_id == "rolling_std":
            arr = dep_arrays[0]
            start = max(0, idx - window + 1)
            window_vals = [v for v in arr[start : idx + 1] if v is not None]
            if len(window_vals) >= max(5, window // 3):
                return statistics.pstdev(window_vals) * scale
            return None

        if formula_id == "relative_return":
            if len(dep_arrays) < 2:
                return None
            arr_a, arr_b = dep_arrays[0], dep_arrays[1]
            if idx - window < 0:
                return None
            a_now, a_prev = arr_a[idx], arr_a[idx - window]
            b_now, b_prev = arr_b[idx], arr_b[idx - window]
            if None in (a_now, a_prev, b_now, b_prev) or a_prev == 0 or b_prev == 0:
                return None
            ret_a = (a_now / a_prev) - 1
            ret_b = (b_now / b_prev) - 1
            return (ret_a - ret_b) * 100 * scale

        if formula_id == "drawdown":
            arr = dep_arrays[0]
            if arr[idx] is None:
                return None
            start = max(0, idx - window + 1)
            window_vals = [v for v in arr[start : idx + 1] if v is not None]
            if not window_vals:
                return None
            local_peak = max(window_vals)
            if local_peak == 0:
                return None
            return ((arr[idx] / local_peak) - 1) * 100

        return None

    def _calculate_factor_values(self, factor: FactorDef) -> List[Tuple[str, float]]:
        dep_series = [self._load_raw_series(dep) for dep in factor.deps]
        if not any(dep_series):
            return []

        dates, aligned_arrays = self._align_series_asof(dep_series)
        if not dates:
            return []

        result: List[Tuple[str, float]] = []
        for idx, current_date in enumerate(dates):
            dep_values = [arr[idx] if idx < len(arr) else None for arr in aligned_arrays]
            value = self._formula_value(factor.formula_id, dep_values, aligned_arrays, idx, factor.params)
            parsed = _safe_float(value)
            if parsed is None:
                continue
            result.append((current_date, parsed))

        return result

    def calculate_percentile(self, current_value: float, historical_values: List[float]) -> float:
        if current_value is None or not historical_values:
            return 50.0
        valid_values = [v for v in historical_values if v is not None]
        if not valid_values:
            return 50.0
        count_less = sum(1 for value in valid_values if value < current_value)
        return round((count_less / len(valid_values)) * 100, 2)

    def _score_from_percentile(self, percentile: Optional[float], direction: str) -> Optional[float]:
        if percentile is None:
            return None

        if direction == "higher_better":
            return round(percentile, 2)
        if direction == "lower_better":
            return round(100 - percentile, 2)
        # neutral
        return round(max(0.0, 100 - 2 * abs(percentile - 50)), 2)

    def _latest_status(self, frequency: str, latest_date: Optional[str]) -> str:
        if not latest_date:
            return "missing"

        try:
            lag_days = (_parse_date(_today_str()) - _parse_date(latest_date)).days
        except ValueError:
            return "missing"

        threshold = FREQUENCY_STALE_DAYS.get(frequency, 14)
        if lag_days <= threshold:
            return "current"
        return "stale"

    def _calculate_percentile_series(self, points: Sequence[Tuple[str, float]]) -> List[Tuple[str, float, float]]:
        if not points:
            return []

        dates = [_parse_date(d) for d, _ in points]
        values = [v for _, v in points]
        output: List[Tuple[str, float, float]] = []

        for idx, (date_str, value) in enumerate(points):
            cutoff = dates[idx] - timedelta(days=PERCENTILE_WINDOW_DAYS)
            window_vals = [values[pos] for pos in range(idx + 1) if dates[pos] >= cutoff]
            percentile = self.calculate_percentile(value, window_vals)
            output.append((date_str, value, percentile))

        return output

    def _persist_factor_results(self) -> Dict[str, Any]:
        computed = 0
        missing = 0
        today = _today_str()
        now = _now_iso()
        factor_points: Dict[str, List[Tuple[str, float, float]]] = {}

        # Phase 1: compute all factors from raw series before opening write transaction.
        for factor in FACTOR_CATALOG:
            points = self._calculate_factor_values(factor)
            scored_points = self._calculate_percentile_series(points)
            factor_points[factor.id] = scored_points
            if scored_points:
                computed += 1
            else:
                missing += 1

        # Phase 2: persist results in one write transaction.
        conn = self._get_connection()
        cursor = conn.cursor()

        for factor in FACTOR_CATALOG:
            scored_points = factor_points.get(factor.id, [])

            for date_str, raw_value, percentile in scored_points:
                score = self._score_from_percentile(percentile, factor.direction)
                color = _score_to_color(score)
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO factor_series
                    (factor_id, module_id, date, raw_value, percentile_5y, score, color, data_status, display_only)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'historical', ?)
                    """,
                    (
                        factor.id,
                        factor.module,
                        date_str,
                        raw_value,
                        percentile,
                        score,
                        color,
                        int(factor.display_only),
                    ),
                )

            if scored_points:
                latest_date, latest_value, latest_percentile = scored_points[-1]
                latest_score = self._score_from_percentile(latest_percentile, factor.direction)
                latest_status = self._latest_status(factor.frequency, latest_date)
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO factor_latest
                    (factor_id, module_id, date, raw_value, percentile_5y, score, color, data_status, display_only, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        factor.id,
                        factor.module,
                        latest_date,
                        latest_value,
                        latest_percentile,
                        latest_score,
                        _score_to_color(latest_score),
                        latest_status,
                        int(factor.display_only),
                        now,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO factor_latest
                    (factor_id, module_id, date, raw_value, percentile_5y, score, color, data_status, display_only, updated_at)
                    VALUES (?, ?, ?, NULL, NULL, NULL, 'gray', 'missing', ?, ?)
                    """,
                    (factor.id, factor.module, today, int(factor.display_only), now),
                )

        conn.commit()
        conn.close()

        self._update_module_and_overall_scores(today)
        return {"computed": computed, "missing": missing}

    def _module_score_from_rows(self, module_id: str, latest_rows: Dict[str, sqlite3.Row]) -> Tuple[float, Optional[str]]:
        scored = [factor for factor in module_factors(module_id) if not factor.display_only]
        weighted_sum = 0.0
        used_weight = 0.0
        latest_date: Optional[str] = None

        for factor in scored:
            row = latest_rows.get(factor.id)
            if not row:
                continue
            score = _safe_float(row["score"])
            if score is None:
                continue
            weighted_sum += score * factor.weight
            used_weight += factor.weight

            row_date = row["date"]
            if row_date and (latest_date is None or row_date > latest_date):
                latest_date = row_date

        if used_weight <= 0:
            return 50.0, latest_date

        return round(weighted_sum / used_weight, 2), latest_date

    def _update_module_and_overall_scores(self, score_date: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM factor_latest")
        latest_rows = {row["factor_id"]: row for row in cursor.fetchall()}

        module_scores: Dict[str, float] = {}
        module_changes: Dict[str, float] = {}

        for module_id in MODULE_IDS:
            module_score, last_updated = self._module_score_from_rows(module_id, latest_rows)

            cursor.execute(
                """
                SELECT score
                FROM module_scores
                WHERE module = ? AND date < ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (module_id, score_date),
            )
            prev_row = cursor.fetchone()
            prev_score = _safe_float(prev_row[0]) if prev_row else module_score
            change_1w = round(module_score - prev_score, 2)
            change_1m = change_1w

            scored_count = len([factor for factor in module_factors(module_id) if not factor.display_only])

            cursor.execute(
                """
                INSERT OR REPLACE INTO module_scores
                (module, date, score, percentile, change_1w, change_1m, factors_count, scored_factors_count, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    module_id,
                    score_date,
                    module_score,
                    module_score,
                    change_1w,
                    change_1m,
                    len(module_factors(module_id)),
                    scored_count,
                    last_updated or score_date,
                ),
            )

            module_scores[module_id] = module_score
            module_changes[module_id] = change_1w

        total_weight = sum(CONFIG_MODULE_WEIGHTS.get(module, 0.0) for module in MODULE_IDS)
        if total_weight <= 0:
            total_weight = float(len(MODULE_IDS))

        weighted_score = 0.0
        for module_id in MODULE_IDS:
            weight = CONFIG_MODULE_WEIGHTS.get(module_id, 1.0 / len(MODULE_IDS))
            weighted_score += module_scores[module_id] * weight

        overall_score = round(weighted_score / total_weight, 2)
        healthy = sum(1 for score in module_scores.values() if score >= 55)
        critical = sum(1 for score in module_scores.values() if score <= 45)

        if overall_score >= 55:
            interpretation = "支持性"
        elif overall_score <= 45:
            interpretation = "限制性"
        else:
            interpretation = "中性"

        avg_change = sum(module_changes.values()) / len(module_changes) if module_changes else 0.0
        trend = "improving" if avg_change > 0.05 else "declining" if avg_change < -0.05 else "stable"

        cursor.execute(
            """
            INSERT OR REPLACE INTO overall_scores
            (date, score, interpretation, trend, percentile, healthy_modules, critical_modules, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                score_date,
                overall_score,
                interpretation,
                trend,
                overall_score,
                healthy,
                critical,
                _now_iso(),
            ),
        )

        conn.commit()
        conn.close()

    # ---------------------------------------------------------------------
    # Pipeline
    # ---------------------------------------------------------------------

    def _create_pipeline_run(self, run_id: str) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO pipeline_runs
            (run_id, started_at, finished_at, status, message)
            VALUES (?, ?, NULL, 'running', '')
            """,
            (run_id, _now_iso()),
        )
        conn.commit()
        conn.close()

    def _finish_pipeline_run(self, run_id: str, status: str, message: str) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE pipeline_runs
            SET finished_at = ?, status = ?, message = ?
            WHERE run_id = ?
            """,
            (_now_iso(), status, message[:1000], run_id),
        )
        conn.commit()
        conn.close()

    def reconcile_interrupted_pipeline_runs(self, max_age_minutes: int = 60) -> Dict[str, Any]:
        """Mark old running pipeline rows as failed after a process restart."""
        cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
        now = _now_iso()
        marked = 0

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT run_id, started_at
            FROM pipeline_runs
            WHERE status = 'running'
            """
        )
        rows = cursor.fetchall()

        for row in rows:
            started_at = row["started_at"]
            try:
                started = datetime.fromisoformat(started_at)
            except (TypeError, ValueError):
                started = datetime.min

            if started > cutoff:
                continue

            cursor.execute(
                """
                UPDATE pipeline_runs
                SET finished_at = ?, status = 'failed', message = ?
                WHERE run_id = ?
                """,
                (
                    now,
                    "marked failed because the previous update process was interrupted before completion",
                    row["run_id"],
                ),
            )
            marked += 1

        conn.commit()
        conn.close()
        return {"marked_failed": marked, "checked": len(rows)}

    def get_factor_layer_status(self) -> Dict[str, Any]:
        """Return health metadata for raw data vs computed factor tables."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM raw_series")
        raw_rows = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM factor_series")
        factor_rows = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM factor_latest")
        latest_rows = int(cursor.fetchone()[0])

        cursor.execute("SELECT data_status, COUNT(*) FROM factor_latest GROUP BY data_status")
        status_counts = {row[0] or "unknown": int(row[1]) for row in cursor.fetchall()}

        cursor.execute("SELECT MAX(date) FROM factor_series")
        latest_factor_date = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(updated_at) FROM factor_latest")
        latest_factor_update = cursor.fetchone()[0]

        conn.close()

        missing_latest = int(status_counts.get("missing", 0))
        seeded_only = latest_rows > 0 and missing_latest == latest_rows
        needs_rebuild = raw_rows > 0 and (factor_rows == 0 or latest_rows == 0 or seeded_only)

        if raw_rows == 0:
            reason = "raw data is empty"
        elif needs_rebuild and factor_rows == 0:
            reason = "raw data exists but computed factor history is empty"
        elif needs_rebuild and seeded_only:
            reason = "factor_latest only contains bootstrap placeholders"
        elif needs_rebuild:
            reason = "computed factor latest rows are missing"
        else:
            reason = "factor layer is initialized"

        return {
            "raw_series_rows": raw_rows,
            "factor_series_rows": factor_rows,
            "factor_latest_rows": latest_rows,
            "factor_latest_missing": missing_latest,
            "factor_latest_status_counts": status_counts,
            "latest_factor_date": latest_factor_date,
            "latest_factor_update": latest_factor_update,
            "needs_rebuild": needs_rebuild,
            "reason": reason,
        }

    def ensure_factor_layer_ready(self) -> Dict[str, Any]:
        """Rebuild factor tables from existing raw data when only placeholders exist."""
        before = self.get_factor_layer_status()
        if not before["needs_rebuild"]:
            return {
                "rebuilt": False,
                "before": before,
                "after": before,
                "factors": {"computed": 0, "missing": 0},
                "message": before["reason"],
            }

        factor_report = self._persist_factor_results()
        after = self.get_factor_layer_status()
        return {
            "rebuilt": True,
            "before": before,
            "after": after,
            "factors": factor_report,
            "message": after["reason"],
        }

    def update_all_data(self) -> Dict[str, Any]:
        """Main update pipeline: fetch raw -> factor engine -> module/overall scores."""
        run_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        self._create_pipeline_run(run_id)

        try:
            raw_report = self._refresh_raw_sources()
            factor_report = self._persist_factor_results()
            message = (
                f"raw_saved={raw_report.get('saved_rows', 0)}, "
                f"factors_computed={factor_report.get('computed', 0)}, "
                f"factors_missing={factor_report.get('missing', 0)}"
            )
            self._finish_pipeline_run(run_id, "success", message)
            return {
                "run_id": run_id,
                "status": "success",
                "raw": raw_report,
                "factors": factor_report,
                "message": message,
            }
        except Exception as exc:  # noqa: BLE001
            self._finish_pipeline_run(run_id, "failed", str(exc))
            raise

    # ---------------------------------------------------------------------
    # Legacy helpers (kept for compatibility)
    # ---------------------------------------------------------------------

    def generate_mock_data(self, days: int = 730) -> None:
        """Deprecated compatibility shim. No-op by design."""
        _ = days
        self.bootstrap_defaults()

    def fetch_fred_series(
        self,
        series_id: str,
        observation_start: Optional[str] = None,
        observation_end: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        _ = (observation_start, observation_end)
        return fetch_fred_csv(series_id)

    def fetch_fred_csv(self, series_id: str) -> List[Dict[str, Any]]:
        return fetch_fred_csv(series_id)

    def save_fred_to_database(
        self,
        series_id: str,
        module: str,
        name: str,
        unit: str,
        observations: List[Dict[str, Any]],
    ) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        for row in observations:
            value = _safe_float(row.get("value"))
            date_str = row.get("date")
            if value is None or not date_str:
                continue
            cursor.execute(
                """
                INSERT OR REPLACE INTO indicators
                (series_id, date, value, module, name, unit)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (series_id, date_str, value, module, name, unit),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO raw_series
                (source, symbol, date, value, frequency, fetched_at, status)
                VALUES ('fred', ?, ?, ?, ?, ?, 'ok')
                """,
                (series_id, date_str, value, self._infer_frequency("fred", series_id), _now_iso()),
            )
        conn.commit()
        conn.close()
        self._raw_cache.clear()

    def update_fred_data(self, use_api: bool = False, days: int = HISTORY_DEFAULT_DAYS) -> Dict[str, Any]:
        _ = (use_api, days)
        report = self._refresh_raw_sources()
        return {"status": "ok", "raw": report}

    def get_indicator_latest(self, series_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, value
            FROM raw_series
            WHERE source = 'fred' AND symbol = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (series_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {"date": row[0], "value": row[1]}

    def get_indicator_history(self, series_id: str, days: int = HISTORY_DEFAULT_DAYS) -> List[float]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT value
            FROM raw_series
            WHERE source = 'fred' AND symbol = ? AND value IS NOT NULL
            ORDER BY date DESC
            LIMIT ?
            """,
            (series_id, days),
        )
        rows = [float(row[0]) for row in cursor.fetchall() if row[0] is not None]
        conn.close()
        return rows

    # ---------------------------------------------------------------------
    # S&P 500 data
    # ---------------------------------------------------------------------

    def load_sp500_from_csv(self, csv_path: str) -> bool:
        if not os.path.exists(csv_path):
            return False

        rows: List[Dict[str, Any]] = []
        with open(csv_path, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    date_str = datetime.strptime(row["Date"], "%Y-%m-%d").strftime("%Y-%m-%d")
                    close = float(row["Close"])
                    rows.append(
                        {
                            "date": date_str,
                            "open": float(row["Open"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                            "close": close,
                            "volume": int(float(row.get("Volume", 0) or 0)),
                        }
                    )
                except Exception:  # noqa: BLE001
                    continue

        if not rows:
            return False

        closes = [row["close"] for row in rows]
        min_close, max_close = min(closes), max(closes)
        span = max(max_close - min_close, 1e-9)

        conn = self._get_connection()
        cursor = conn.cursor()
        for row in rows:
            normalized = ((row["close"] - min_close) / span) * 100
            cursor.execute(
                """
                INSERT OR REPLACE INTO sp500_data
                (date, open, high, low, close, volume, normalized)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["date"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    normalized,
                ),
            )

        conn.commit()
        conn.close()
        return True

    def get_sp500_data(self, days: int = 365) -> Dict[str, List[Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, close, normalized
            FROM sp500_data
            ORDER BY date DESC
            LIMIT ?
            """,
            (days,),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {"dates": [], "raw_values": [], "values": []}

        rows = list(reversed(rows))
        return {
            "dates": [row[0] for row in rows],
            "raw_values": [round(float(row[1]), 4) for row in rows],
            "values": [round(float(row[2]), 4) for row in rows],
        }

    def get_current_sp500(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, close, normalized
            FROM sp500_data
            ORDER BY date DESC
            LIMIT 2
            """
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {"date": None, "value": None, "normalized": None, "change": None}

        current = rows[0]
        if len(rows) > 1 and rows[1][1] not in (None, 0):
            previous_close = float(rows[1][1])
            change = ((float(current[1]) - previous_close) / previous_close) * 100
        else:
            change = 0.0

        return {
            "date": current[0],
            "value": round(float(current[1]), 2),
            "normalized": round(float(current[2]), 2) if current[2] is not None else None,
            "change": round(change, 2),
        }

    # ---------------------------------------------------------------------
    # API views
    # ---------------------------------------------------------------------

    def _latest_overall_row(self) -> Optional[sqlite3.Row]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, score, interpretation, trend, percentile, healthy_modules, critical_modules
            FROM overall_scores
            ORDER BY date DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def get_current_overall_score(self) -> Dict[str, Any]:
        row = self._latest_overall_row()
        if not row:
            self.bootstrap_defaults()
            row = self._latest_overall_row()

        if not row:
            return {
                "date": _today_str(),
                "score": 50.0,
                "interpretation": "中性",
                "trend": "stable",
                "percentile": 50.0,
                "healthy_modules": 0,
                "critical_modules": 0,
            }

        return {
            "date": row[0],
            "score": round(float(row[1]), 2),
            "interpretation": row[2],
            "trend": row[3],
            "percentile": round(float(row[4]), 2) if row[4] is not None else None,
            "healthy_modules": int(row[5] or 0),
            "critical_modules": int(row[6] or 0),
        }

    def _latest_module_rows(self) -> Dict[str, sqlite3.Row]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ms.*
            FROM module_scores ms
            INNER JOIN (
                SELECT module, MAX(date) AS max_date
                FROM module_scores
                GROUP BY module
            ) latest
            ON latest.module = ms.module AND latest.max_date = ms.date
            """
        )
        rows = {row["module"]: row for row in cursor.fetchall()}
        conn.close()
        return rows

    def _module_payload_from_row(self, module_id: str, row: Optional[sqlite3.Row]) -> Dict[str, Any]:
        meta = MODULE_META[module_id]

        score = round(float(row["score"]), 2) if row and row["score"] is not None else 50.0
        change_1w = round(float(row["change_1w"]), 2) if row and row["change_1w"] is not None else 0.0
        change_1m = round(float(row["change_1m"]), 2) if row and row["change_1m"] is not None else 0.0

        trend = "上升" if change_1w > 0.1 else "下降" if change_1w < -0.1 else "稳定"

        factors_count = int(row["factors_count"]) if row and row["factors_count"] is not None else len(module_factors(module_id))
        scored_count = (
            int(row["scored_factors_count"])
            if row and row["scored_factors_count"] is not None
            else len([f for f in module_factors(module_id) if not f.display_only])
        )
        last_updated = row["last_updated"] if row and row["last_updated"] else _today_str()

        return {
            "id": module_id,
            "module": module_id,
            "name": meta["name_cn"],
            "name_cn": meta["name_cn"],
            "name_en": meta["name"],
            "score": score,
            "percentile": score,
            "change_1w": change_1w,
            "change_1m": change_1m,
            "trend": trend,
            "factor_count": factors_count,
            "factors_count": factors_count,
            "scored_factors_count": scored_count,
            "last_update": last_updated,
            "last_updated": last_updated,
        }

    def get_all_module_scores(self) -> List[Dict[str, Any]]:
        latest_rows = self._latest_module_rows()
        payload = [self._module_payload_from_row(module_id, latest_rows.get(module_id)) for module_id in MODULE_IDS]
        return sorted(payload, key=lambda item: item["score"], reverse=True)

    def get_modules_v1(self) -> List[Dict[str, Any]]:
        return self.get_all_module_scores()

    def get_module_score(self, module_id: str) -> Optional[Dict[str, Any]]:
        if module_id not in MODULE_META:
            return None
        latest_rows = self._latest_module_rows()
        return self._module_payload_from_row(module_id, latest_rows.get(module_id))

    def get_module_history(self, module_id: str, days: int = 365) -> Dict[str, List[Any]]:
        if module_id not in MODULE_META:
            return {"dates": [], "values": []}

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, score
            FROM module_scores
            WHERE module = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (module_id, days),
        )
        rows = cursor.fetchall()
        conn.close()

        rows = list(reversed(rows))
        return {
            "dates": [row[0] for row in rows],
            "values": [round(float(row[1]), 2) for row in rows],
        }

    def get_overall_history(self, days: int = 365) -> Dict[str, List[Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, score
            FROM overall_scores
            ORDER BY date DESC
            LIMIT ?
            """,
            (days,),
        )
        rows = cursor.fetchall()
        conn.close()

        rows = list(reversed(rows))
        return {
            "dates": [row[0] for row in rows],
            "values": [round(float(row[1]), 2) for row in rows],
        }

    def _factor_latest_rows_by_module(self, module_id: str) -> Dict[str, sqlite3.Row]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM factor_latest
            WHERE module_id = ?
            """,
            (module_id,),
        )
        rows = {row["factor_id"]: row for row in cursor.fetchall()}
        conn.close()
        return rows

    def _factor_change(self, factor_id: str, current_date: str, window_days: int) -> Optional[float]:
        try:
            target = (_parse_date(current_date) - timedelta(days=window_days)).strftime("%Y-%m-%d")
        except ValueError:
            return None

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT raw_value
            FROM factor_series
            WHERE factor_id = ? AND date = ?
            LIMIT 1
            """,
            (factor_id, current_date),
        )
        cur = cursor.fetchone()

        cursor.execute(
            """
            SELECT raw_value
            FROM factor_series
            WHERE factor_id = ? AND date <= ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (factor_id, target),
        )
        prev = cursor.fetchone()
        conn.close()

        if not cur or not prev:
            return None

        cur_val = _safe_float(cur[0])
        prev_val = _safe_float(prev[0])
        if cur_val is None or prev_val is None:
            return None

        return round(cur_val - prev_val, 6)

    def get_module_indicators(self, module_id: str) -> List[Dict[str, Any]]:
        if module_id not in MODULE_META:
            return []

        latest_rows = self._factor_latest_rows_by_module(module_id)
        factors = module_factors(module_id)

        indicators: List[Dict[str, Any]] = []
        for factor in factors:
            row = latest_rows.get(factor.id)
            latest_date = row["date"] if row else None
            value = _safe_float(row["raw_value"]) if row else None
            percentile = _safe_float(row["percentile_5y"]) if row else None

            change_1d = self._factor_change(factor.id, latest_date, 1) if latest_date else None
            change_1w = self._factor_change(factor.id, latest_date, 7) if latest_date else None

            indicators.append(
                {
                    "series_id": factor.id,
                    "name": factor.name_cn,
                    "module": module_id,
                    "value": value,
                    "date": latest_date,
                    "unit": factor.format_hint,
                    "change_1d": change_1d,
                    "change_1w": change_1w,
                    "percentile_5y": percentile,
                    "data_status": row["data_status"] if row else "missing",
                    "display_only": factor.display_only,
                }
            )

        return indicators

    def get_indicator_list(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for factor in FACTOR_CATALOG:
            entries.append(
                {
                    "code": factor.id,
                    "name": factor.name_cn,
                    "name_en": factor.name,
                    "module": factor.module,
                    "module_name": MODULE_META[factor.module]["name_cn"],
                    "display_only": factor.display_only,
                    "frequency": factor.frequency,
                    "direction": factor.direction,
                    "unit": factor.format_hint,
                }
            )
        return entries

    def get_factor_history(self, module_id: str, factor_id: str, days: int = HISTORY_DEFAULT_DAYS) -> Dict[str, Any]:
        factor = self._factor_map.get(factor_id)
        if not factor or factor.module != module_id:
            return {
                "module_id": module_id,
                "factor_id": factor_id,
                "dates": [],
                "values": [],
                "percentiles": [],
                "scores": [],
            }

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, raw_value, percentile_5y, score
            FROM factor_series
            WHERE factor_id = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (factor_id, days),
        )
        rows = list(reversed(cursor.fetchall()))
        conn.close()

        return {
            "module_id": module_id,
            "factor_id": factor_id,
            "dates": [row[0] for row in rows],
            "values": [row[1] for row in rows],
            "percentiles": [row[2] for row in rows],
            "scores": [row[3] for row in rows],
        }

    def get_factor_distribution(self, module_id: str, factor_id: str) -> Dict[str, Any]:
        history = self.get_factor_history(module_id, factor_id, days=HISTORY_DEFAULT_DAYS)
        values = [float(v) for v in history["values"] if v is not None]

        if not values:
            return {
                "module_id": module_id,
                "factor_id": factor_id,
                "count": 0,
                "min": None,
                "max": None,
                "p10": None,
                "p50": None,
                "p90": None,
                "histogram": [],
            }

        values_sorted = sorted(values)
        count = len(values_sorted)

        def q(p: float) -> float:
            idx = int(round((count - 1) * p))
            return values_sorted[idx]

        min_v, max_v = values_sorted[0], values_sorted[-1]
        bins = 10
        width = (max_v - min_v) / bins if max_v > min_v else 1.0
        histogram = [0 for _ in range(bins)]

        for value in values_sorted:
            if max_v == min_v:
                bin_idx = 0
            else:
                bin_idx = min(bins - 1, int((value - min_v) / width))
            histogram[bin_idx] += 1

        return {
            "module_id": module_id,
            "factor_id": factor_id,
            "count": count,
            "min": round(min_v, 6),
            "max": round(max_v, 6),
            "p10": round(q(0.10), 6),
            "p50": round(q(0.50), 6),
            "p90": round(q(0.90), 6),
            "histogram": histogram,
        }

    def get_module_detail(self, module_id: str) -> Optional[Dict[str, Any]]:
        if module_id not in MODULE_META:
            return None

        module_summary = self.get_module_score(module_id)
        if not module_summary:
            return None

        latest_rows = self._factor_latest_rows_by_module(module_id)
        factors_payload: List[Dict[str, Any]] = []

        for factor in module_factors(module_id):
            row = latest_rows.get(factor.id)
            factors_payload.append(
                {
                    "id": factor.id,
                    "module": factor.module,
                    "name": factor.name,
                    "name_cn": factor.name_cn,
                    "display_only": factor.display_only,
                    "weight": factor.weight,
                    "direction": factor.direction,
                    "frequency": factor.frequency,
                    "formula_id": factor.formula_id,
                    "deps": list(factor.deps),
                    "format_hint": factor.format_hint,
                    "latest": {
                        "date": row["date"] if row else None,
                        "value": row["raw_value"] if row else None,
                        "percentile": row["percentile_5y"] if row else None,
                        "score": row["score"] if row else None,
                        "color": row["color"] if row else "gray",
                        "data_status": row["data_status"] if row else "missing",
                    },
                }
            )

        module_summary["factors"] = factors_payload
        return module_summary

    def get_dashboard_drivers(self, period: str = "30d") -> Dict[str, Any]:
        day_map = {"7d": 7, "30d": 30, "90d": 90}
        window = day_map.get(period, 30)

        conn = self._get_connection()
        cursor = conn.cursor()

        module_changes: List[Dict[str, Any]] = []
        for module_id in MODULE_IDS:
            cursor.execute(
                """
                SELECT date, score
                FROM module_scores
                WHERE module = ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (module_id,),
            )
            latest = cursor.fetchone()
            if not latest:
                continue

            latest_date = latest[0]
            target_date = (_parse_date(latest_date) - timedelta(days=window)).strftime("%Y-%m-%d")
            cursor.execute(
                """
                SELECT score
                FROM module_scores
                WHERE module = ? AND date <= ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (module_id, target_date),
            )
            prev = cursor.fetchone()
            prev_score = float(prev[0]) if prev and prev[0] is not None else float(latest[1])
            delta = round(float(latest[1]) - prev_score, 4)

            module_changes.append(
                {
                    "module": module_id,
                    "name": MODULE_META[module_id]["name_cn"],
                    "delta": delta,
                    "current": round(float(latest[1]), 2),
                    "previous": round(prev_score, 2),
                }
            )

        factor_changes: List[Dict[str, Any]] = []
        for factor in FACTOR_CATALOG:
            cursor.execute(
                """
                SELECT date, score
                FROM factor_series
                WHERE factor_id = ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (factor.id,),
            )
            latest = cursor.fetchone()
            if not latest or latest[1] is None:
                continue

            latest_date = latest[0]
            target_date = (_parse_date(latest_date) - timedelta(days=window)).strftime("%Y-%m-%d")
            cursor.execute(
                """
                SELECT score
                FROM factor_series
                WHERE factor_id = ? AND date <= ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (factor.id, target_date),
            )
            prev = cursor.fetchone()
            prev_score = float(prev[0]) if prev and prev[0] is not None else float(latest[1])
            delta = round(float(latest[1]) - prev_score, 4)

            factor_changes.append(
                {
                    "factor_id": factor.id,
                    "module": factor.module,
                    "name": factor.name_cn,
                    "delta": delta,
                    "current": round(float(latest[1]), 2),
                    "previous": round(prev_score, 2),
                }
            )

        conn.close()

        module_changes_sorted = sorted(module_changes, key=lambda row: abs(row["delta"]), reverse=True)
        factor_changes_sorted = sorted(factor_changes, key=lambda row: abs(row["delta"]), reverse=True)

        return {
            "period": period if period in day_map else "30d",
            "generated_at": _now_iso(),
            "modules": module_changes_sorted[:7],
            "factors": factor_changes_sorted[:10],
        }

    def _freshness_meta(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT data_status, COUNT(*) AS count FROM factor_latest GROUP BY data_status")
        status_rows = {row[0]: int(row[1]) for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT MAX(fetched_at)
            FROM raw_series
            WHERE source = 'fred'
            """
        )
        last_fred = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT MAX(fetched_at)
            FROM raw_series
            WHERE source IN ('cboe', 'stooq')
            """
        )
        last_alt = cursor.fetchone()[0]

        conn.close()

        stale_factors = int(status_rows.get("stale", 0)) + int(status_rows.get("missing", 0))
        if status_rows.get("missing", 0):
            overall_status = "degraded"
        elif status_rows.get("stale", 0):
            overall_status = "stale"
        else:
            overall_status = "current"

        return {
            "overall_status": overall_status,
            "last_fred_sync": last_fred,
            "last_alt_sync": last_alt,
            "stale_factors": stale_factors,
        }

    def get_dashboard_data(self) -> Dict[str, Any]:
        overall = self.get_current_overall_score()
        modules = self.get_modules_v1()
        history = self.get_overall_history(HISTORY_DEFAULT_DAYS)
        sp500 = self.get_sp500_data(HISTORY_DEFAULT_DAYS)

        return {
            "overall": overall,
            "modules": modules,
            "history": history,
            "sp500": sp500,
            "sp500_current": self.get_current_sp500(),
            "data_freshness": self._freshness_meta(),
            "last_update": overall.get("date") or _today_str(),
        }

    def get_pipeline_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT run_id, started_at, finished_at, status, message
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
