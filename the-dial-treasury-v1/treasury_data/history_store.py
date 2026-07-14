from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import zlib
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_DB = PROJECT_ROOT / "data" / "history.sqlite3"
DEFAULT_BUSY_TIMEOUT_MS = 5_000
DEFAULT_PAYLOAD_RETENTION = 30
PAYLOAD_ENCODING_JSON = "json"
PAYLOAD_ENCODING_ZLIB = "zlib-json-v1"
PAYLOAD_ENCODING_DISCARDED = "discarded-v1"


@dataclass(frozen=True)
class HistoryPayloadPolicy:
    """Storage policy for optional full dashboard snapshot bodies.

    Metric observations and snapshot metadata are always retained.  ``retain``
    only controls how many newest *full* payloads remain recoverable; older rows
    keep their IDs, timestamps, source status, and extracted metrics.
    """

    compression: str = "zlib"
    retain: int | None = DEFAULT_PAYLOAD_RETENTION
    compression_level: int = 6

    def __post_init__(self) -> None:
        if self.compression not in {"zlib", "none"}:
            raise ValueError("history payload compression must be 'zlib' or 'none'")
        if self.retain is not None and self.retain < 0:
            raise ValueError("history payload retention must be non-negative or None")
        if not 0 <= self.compression_level <= 9:
            raise ValueError("history payload compression_level must be between 0 and 9")


def history_db_for_output(output: Path) -> Path:
    return output.with_name("history.sqlite3")


def connect(db_path: Path = DEFAULT_HISTORY_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=DEFAULT_BUSY_TIMEOUT_MS / 1000)
    connection.execute(f"pragma busy_timeout = {DEFAULT_BUSY_TIMEOUT_MS}")
    connection.execute("pragma foreign_keys = on")
    connection.execute("pragma journal_mode = wal")
    connection.execute("pragma synchronous = normal")
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table if not exists dashboard_snapshots (
          id integer primary key autoincrement,
          as_of text not null,
          generated_at text not null,
          created_at text not null,
          payload_json text not null,
          payload_blob blob,
          payload_encoding text not null default 'json',
          payload_bytes integer,
          payload_hash text,
          source_status_json text not null,
          unique(as_of, generated_at)
        );

        create table if not exists metric_observations (
          id integer primary key autoincrement,
          snapshot_id integer not null references dashboard_snapshots(id) on delete cascade,
          as_of text not null,
          generated_at text not null,
          category text not null,
          name text not null,
          label text,
          value real,
          text_value text,
          unit text,
          source text,
          unique(snapshot_id, category, name, label)
        );

        create index if not exists idx_dashboard_snapshots_as_of
          on dashboard_snapshots(as_of, generated_at);
        create index if not exists idx_metric_observations_lookup
          on metric_observations(category, name, as_of);

        create table if not exists historical_observations (
          id integer primary key autoincrement,
          date text not null,
          category text not null,
          name text not null,
          label text not null default '',
          value real not null,
          unit text,
          source text,
          updated_at text not null,
          unique(date, category, name, label)
        );

        create index if not exists idx_historical_observations_lookup
          on historical_observations(category, name, date);

        create table if not exists history_backfill_runs (
          id integer primary key autoincrement,
          completed_at text not null,
          status text not null,
          years integer not null,
          start_date text,
          end_date text,
          observation_count integer not null default 0,
          saved_observation_count integer not null default 0,
          source_errors_json text not null default '[]'
        );

        create index if not exists idx_history_backfill_runs_completed_at
          on history_backfill_runs(completed_at);
        """
    )
    ensure_column(connection, "dashboard_snapshots", "payload_blob", "blob")
    ensure_column(connection, "dashboard_snapshots", "payload_encoding", "text not null default 'json'")
    ensure_column(connection, "dashboard_snapshots", "payload_bytes", "integer")
    ensure_column(connection, "dashboard_snapshots", "payload_hash", "text")


def ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {str(row[1]) for row in connection.execute(f"pragma table_info({table})")}
    if column not in columns:
        try:
            connection.execute(f"alter table {table} add column {column} {definition}")
        except sqlite3.OperationalError as exc:
            # Another refresher may have completed the same additive migration
            # after our table-info read but before this ALTER acquired its lock.
            if "duplicate column name" not in str(exc).lower():
                raise


def history_payload_policy_from_env() -> HistoryPayloadPolicy:
    """Read optional MARCO_HISTORY_PAYLOAD_* operational overrides."""
    compression = os.environ.get("MARCO_HISTORY_PAYLOAD_COMPRESSION", "zlib").strip().lower() or "zlib"
    retain_text = os.environ.get("MARCO_HISTORY_PAYLOAD_RETAIN", str(DEFAULT_PAYLOAD_RETENTION)).strip().lower()
    retain = None if retain_text in {"all", "unlimited", "none"} else int(retain_text)
    level = int(os.environ.get("MARCO_HISTORY_PAYLOAD_COMPRESSION_LEVEL", "6"))
    return HistoryPayloadPolicy(compression=compression, retain=retain, compression_level=level)


def payload_envelope(as_of: str, generated_at: str, encoding: str) -> str:
    return json.dumps(
        {"asOf": as_of, "generatedAt": generated_at, "payloadEncoding": encoding},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def encode_dashboard_payload(
    dashboard: dict[str, Any],
    policy: HistoryPayloadPolicy,
) -> tuple[str, bytes | None, str, int]:
    payload_json = json.dumps(
        dashboard,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    payload_bytes = payload_json.encode("utf-8")
    if policy.compression == "none":
        return payload_json, None, PAYLOAD_ENCODING_JSON, len(payload_bytes)
    compressed = zlib.compress(payload_bytes, level=policy.compression_level)
    return (
        payload_envelope(required_text(dashboard, "asOf"), required_text(dashboard, "generatedAt"), PAYLOAD_ENCODING_ZLIB),
        compressed,
        PAYLOAD_ENCODING_ZLIB,
        len(payload_bytes),
    )


def dashboard_payload_hash(dashboard: dict[str, Any]) -> str:
    canonical = json.dumps(
        dashboard,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decode_dashboard_payload(payload_json: str, payload_blob: bytes | None, encoding: str | None) -> dict[str, Any] | None:
    normalized = str(encoding or PAYLOAD_ENCODING_JSON)
    if normalized == PAYLOAD_ENCODING_DISCARDED:
        return None
    if normalized == PAYLOAD_ENCODING_ZLIB:
        if payload_blob is None:
            return None
        raw = zlib.decompress(payload_blob).decode("utf-8")
    else:
        raw = payload_json
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else None


def save_dashboard_history(
    dashboard: dict[str, Any],
    db_path: Path = DEFAULT_HISTORY_DB,
    *,
    payload_policy: HistoryPayloadPolicy | None = None,
) -> int:
    as_of = required_text(dashboard, "asOf")
    generated_at = required_text(dashboard, "generatedAt")
    policy = payload_policy or history_payload_policy_from_env()
    payload_json, payload_blob, payload_encoding, payload_bytes = encode_dashboard_payload(dashboard, policy)
    payload_hash = dashboard_payload_hash(dashboard)
    source_status_json = json.dumps(dashboard.get("sourceStatus", []), ensure_ascii=False, sort_keys=True)
    created_at = datetime.now(timezone.utc).isoformat()

    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        with connection:
            existing = connection.execute(
                """
                select id, payload_json, payload_blob, payload_encoding, payload_hash
                from dashboard_snapshots
                where as_of = ? and generated_at = ?
                """,
                (as_of, generated_at),
            ).fetchone()
            if existing is not None:
                existing_hash = str(existing[4] or "")
                existing_payload = None if existing_hash else decode_dashboard_payload(existing[1], existing[2], existing[3])
                if (
                    (existing_hash and existing_hash != payload_hash)
                    or (not existing_hash and (existing_payload is None or existing_payload != dashboard))
                ):
                    raise ValueError(
                        "dashboard snapshot identity collision: the same asOf/generatedAt key has different content"
                    )
            connection.execute(
                """
                insert or ignore into dashboard_snapshots
                  (as_of, generated_at, created_at, payload_json, payload_blob, payload_encoding, payload_bytes, payload_hash, source_status_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    as_of,
                    generated_at,
                    created_at,
                    payload_json,
                    payload_blob,
                    payload_encoding,
                    payload_bytes,
                    payload_hash,
                    source_status_json,
                ),
            )
            connection.execute(
                """
                update dashboard_snapshots
                set created_at = ?, payload_json = ?, payload_blob = ?, payload_encoding = ?, payload_bytes = ?,
                    payload_hash = ?, source_status_json = ?
                where as_of = ? and generated_at = ?
                """,
                (
                    created_at,
                    payload_json,
                    payload_blob,
                    payload_encoding,
                    payload_bytes,
                    payload_hash,
                    source_status_json,
                    as_of,
                    generated_at,
                ),
            )
            row = connection.execute(
                "select id from dashboard_snapshots where as_of = ? and generated_at = ?",
                (as_of, generated_at),
            ).fetchone()
            if row is None:
                raise RuntimeError("failed to persist dashboard snapshot")
            snapshot_id = int(row[0])
            connection.execute("delete from metric_observations where snapshot_id = ?", (snapshot_id,))
            connection.executemany(
                """
                insert into metric_observations
                  (snapshot_id, as_of, generated_at, category, name, label, value, text_value, unit, source)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_id,
                        as_of,
                        generated_at,
                        metric["category"],
                        metric["name"],
                        metric.get("label"),
                        metric.get("value"),
                        metric.get("text_value"),
                        metric.get("unit"),
                        metric.get("source"),
                    )
                    for metric in extract_metric_observations(dashboard)
                ],
            )
            apply_payload_policy(connection, policy)
        return snapshot_id


def apply_payload_policy(connection: sqlite3.Connection, policy: HistoryPayloadPolicy) -> None:
    if policy.retain is not None:
        connection.execute(
            """
            update dashboard_snapshots
            set payload_json = ?, payload_blob = null, payload_encoding = ?,
                payload_bytes = coalesce(payload_bytes, length(cast(payload_json as blob)))
            where id not in (
              select id from dashboard_snapshots
              order by coalesce(julianday(generated_at), -1) desc, id desc
              limit ?
            )
              and (payload_encoding != ? or payload_blob is not null)
            """,
            (
                json.dumps({"payloadEncoding": PAYLOAD_ENCODING_DISCARDED}, separators=(",", ":")),
                PAYLOAD_ENCODING_DISCARDED,
                policy.retain,
                PAYLOAD_ENCODING_DISCARDED,
            ),
        )

    target_encoding = PAYLOAD_ENCODING_JSON if policy.compression == "zlib" else PAYLOAD_ENCODING_ZLIB
    if policy.retain is None:
        rows = connection.execute(
            """
            select id, as_of, generated_at, payload_json, payload_blob
            from dashboard_snapshots
            where payload_encoding = ?
            """,
            (target_encoding,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            select id, as_of, generated_at, payload_json, payload_blob
            from dashboard_snapshots
            where payload_encoding = ?
              and id in (
                select id from dashboard_snapshots
                order by coalesce(julianday(generated_at), -1) desc, id desc
                limit ?
              )
            """,
            (target_encoding, policy.retain),
        ).fetchall()

    for snapshot_id, as_of, generated_at, payload_json, payload_blob in rows:
        if policy.compression == "zlib":
            raw = str(payload_json).encode("utf-8")
            connection.execute(
                """
                update dashboard_snapshots
                set payload_json = ?, payload_blob = ?, payload_encoding = ?, payload_bytes = ?
                where id = ?
                """,
                (
                    payload_envelope(str(as_of), str(generated_at), PAYLOAD_ENCODING_ZLIB),
                    zlib.compress(raw, level=policy.compression_level),
                    PAYLOAD_ENCODING_ZLIB,
                    len(raw),
                    snapshot_id,
                ),
            )
        elif payload_blob is not None:
            raw = zlib.decompress(payload_blob).decode("utf-8")
            connection.execute(
                """
                update dashboard_snapshots
                set payload_json = ?, payload_blob = null, payload_encoding = ?, payload_bytes = ?
                where id = ?
                """,
                (raw, PAYLOAD_ENCODING_JSON, len(raw.encode("utf-8")), snapshot_id),
            )


def load_dashboard_snapshot(snapshot_id: int, db_path: Path = DEFAULT_HISTORY_DB) -> dict[str, Any] | None:
    if not db_path.exists():
        return None
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        row = connection.execute(
            "select payload_json, payload_blob, payload_encoding from dashboard_snapshots where id = ?",
            (int(snapshot_id),),
        ).fetchone()
    if row is None:
        return None
    return decode_dashboard_payload(str(row[0]), row[1], row[2])


def extract_metric_observations(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(curve_metrics(dashboard.get("curve")))
    rows.extend(scorecard_metrics(dashboard.get("groups")))
    rows.extend(percentile_metrics(dashboard.get("percentiles")))
    return rows


def curve_metrics(curve: Any) -> list[dict[str, Any]]:
    if not isinstance(curve, dict) or not isinstance(curve.get("tenors"), list):
        return []
    rows: list[dict[str, Any]] = []
    tenors = curve.get("tenors", [])
    for field, category, unit in (("today", "curve_yield", "%"), ("d1", "curve_daily_change", "pct_point")):
        values = curve.get(field)
        if not isinstance(values, list):
            continue
        for index, tenor in enumerate(tenors):
            if index >= len(values):
                continue
            value = safe_float(values[index])
            if value is None:
                continue
            rows.append({"category": category, "name": str(tenor), "value": value, "unit": unit})
    return rows


def scorecard_metrics(groups: Any) -> list[dict[str, Any]]:
    if not isinstance(groups, list):
        return []
    rows: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("id") or group.get("name") or "group")
        group_name = str(group.get("name") or group_id)
        factors = [factor for factor in group.get("factors", []) if isinstance(factor, dict)]
        scores = [safe_float(factor.get("score")) for factor in factors]
        numeric_scores = [score for score in scores if score is not None]
        if numeric_scores:
            rows.append({
                "category": "score_group",
                "name": group_id,
                "label": group_name,
                "value": sum(numeric_scores) / len(numeric_scores),
            })
        for factor in factors:
            score = safe_float(factor.get("score"))
            if score is None:
                continue
            rows.append({
                "category": "factor_score",
                "name": str(factor.get("n") or "factor"),
                "label": group_id,
                "value": score,
                "text_value": str(factor.get("v")) if factor.get("v") is not None else None,
            })
    return rows


def percentile_metrics(percentiles: Any) -> list[dict[str, Any]]:
    if not isinstance(percentiles, dict) or not isinstance(percentiles.get("items"), list):
        return []
    rows: list[dict[str, Any]] = []
    for item in percentiles.get("items", []):
        if not isinstance(item, dict):
            continue
        value = safe_float(item.get("percentile"))
        if value is None:
            continue
        rows.append({
            "category": "factor_percentile",
            "name": str(item.get("name") or "factor"),
            "value": value,
            "text_value": str(item.get("value")) if item.get("value") is not None else None,
            "unit": "percentile",
            "source": str(item.get("source")) if item.get("source") is not None else None,
        })
    return rows


def history_summary(db_path: Path = DEFAULT_HISTORY_DB) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "database": str(db_path),
            "snapshotCount": 0,
            "metricCount": 0,
            "latest": None,
            "historicalObservationCount": 0,
            "historicalSeriesCount": 0,
            "historicalStartDate": None,
            "historicalEndDate": None,
            "latestBackfill": None,
            "payloadStorage": {"compressedCount": 0, "jsonCount": 0, "discardedCount": 0, "storedBytes": 0},
        }
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        snapshot_count = scalar_int(connection, "select count(*) from dashboard_snapshots")
        metric_count = scalar_int(connection, "select count(*) from metric_observations")
        historical_observation_count = scalar_int(connection, "select count(*) from historical_observations")
        historical_series_count = scalar_int(
            connection,
            "select count(*) from (select 1 from historical_observations group by category, name, label)",
        )
        historical_range = connection.execute("select min(date), max(date) from historical_observations").fetchone()
        latest = connection.execute(
            """
            select as_of, generated_at
            from dashboard_snapshots
            order by coalesce(julianday(generated_at), -1) desc, id desc
            limit 1
            """
        ).fetchone()
        payload_storage = connection.execute(
            """
            select
              sum(case when payload_encoding = ? then 1 else 0 end),
              sum(case when payload_encoding = ? then 1 else 0 end),
              sum(case when payload_encoding = ? then 1 else 0 end),
              coalesce(sum(length(cast(payload_json as blob)) + coalesce(length(payload_blob), 0)), 0)
            from dashboard_snapshots
            """,
            (PAYLOAD_ENCODING_ZLIB, PAYLOAD_ENCODING_JSON, PAYLOAD_ENCODING_DISCARDED),
        ).fetchone()
        latest_backfill = latest_history_backfill_run_from_connection(connection)
    return {
        "database": str(db_path),
        "snapshotCount": snapshot_count,
        "metricCount": metric_count,
        "latest": {"asOf": latest[0], "generatedAt": latest[1]} if latest else None,
        "historicalObservationCount": historical_observation_count,
        "historicalSeriesCount": historical_series_count,
        "historicalStartDate": historical_range[0] if historical_range else None,
        "historicalEndDate": historical_range[1] if historical_range else None,
        "latestBackfill": latest_backfill,
        "payloadStorage": {
            "compressedCount": int(payload_storage[0] or 0),
            "jsonCount": int(payload_storage[1] or 0),
            "discardedCount": int(payload_storage[2] or 0),
            "storedBytes": int(payload_storage[3] or 0),
        },
    }


def save_history_backfill_run(summary: dict[str, Any], db_path: Path = DEFAULT_HISTORY_DB, *, years: int) -> int:
    source_errors = summary.get("sourceErrors", [])
    if not isinstance(source_errors, list):
        source_errors = []
    status = "degraded" if has_critical_source_errors(source_errors) else "ok"
    completed_at = datetime.now(timezone.utc).isoformat()
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        with connection:
            cursor = connection.execute(
                """
                insert into history_backfill_runs
                  (completed_at, status, years, start_date, end_date, observation_count, saved_observation_count, source_errors_json)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    completed_at,
                    status,
                    int(years),
                    text_or_none(summary.get("startDate")),
                    text_or_none(summary.get("endDate")),
                    int(summary.get("observationCount") or 0),
                    int(summary.get("savedObservationCount") or 0),
                    json.dumps(source_errors, ensure_ascii=False, sort_keys=True),
                ),
            )
        return int(cursor.lastrowid)


def has_critical_source_errors(source_errors: list[Any]) -> bool:
    for item in source_errors:
        if not isinstance(item, dict):
            return True
        if item.get("severity") != "warning":
            return True
    return False


def latest_history_backfill_run(db_path: Path = DEFAULT_HISTORY_DB) -> dict[str, Any] | None:
    if not db_path.exists():
        return None
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        return latest_history_backfill_run_from_connection(connection)


def latest_history_backfill_run_from_connection(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        """
        select id, completed_at, status, years, start_date, end_date,
               observation_count, saved_observation_count, source_errors_json
        from history_backfill_runs
        order by completed_at desc, id desc
        limit 1
        """
    ).fetchone()
    if row is None:
        return None
    try:
        source_errors = json.loads(row[8])
    except json.JSONDecodeError:
        source_errors = []
    if not isinstance(source_errors, list):
        source_errors = []
    return {
        "id": int(row[0]),
        "completedAt": row[1],
        "status": row[2],
        "years": int(row[3]),
        "startDate": row[4],
        "endDate": row[5],
        "observationCount": int(row[6]),
        "savedObservationCount": int(row[7]),
        "sourceErrors": source_errors,
    }


def list_dashboard_snapshots(db_path: Path = DEFAULT_HISTORY_DB, limit: int = 30) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        rows = connection.execute(
            """
            select s.as_of, s.generated_at, count(m.id) as metric_count
            from dashboard_snapshots s
            left join metric_observations m on m.snapshot_id = s.id
            group by s.id
            order by coalesce(julianday(s.generated_at), -1) desc, s.id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    return [{"asOf": row[0], "generatedAt": row[1], "metricCount": int(row[2])} for row in rows]


def save_historical_observations(observations: list[dict[str, Any]], db_path: Path = DEFAULT_HISTORY_DB) -> int:
    # A backfill can receive overlapping source pages.  SQLite's upsert keeps
    # the last value, so mirror that grain explicitly and report the number of
    # unique observations actually offered to storage rather than the raw
    # duplicate-bearing input length.
    rows_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in observations:
        row = normalize_historical_observation(item)
        if row is None:
            continue
        key = (row["date"], row["category"], row["name"], row["label"])
        rows_by_key[key] = row
    rows = list(rows_by_key.values())
    if not rows:
        return 0
    updated_at = datetime.now(timezone.utc).isoformat()
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        with connection:
            connection.executemany(
                """
                insert into historical_observations
                  (date, category, name, label, value, unit, source, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(date, category, name, label) do update set
                  value = excluded.value,
                  unit = excluded.unit,
                  source = excluded.source,
                  updated_at = excluded.updated_at
                """,
                [
                    (
                        row["date"],
                        row["category"],
                        row["name"],
                        row["label"],
                        row["value"],
                        row["unit"],
                        row["source"],
                        updated_at,
                    )
                    for row in rows
                ],
            )
    return len(rows)


def list_historical_series_stats(db_path: Path = DEFAULT_HISTORY_DB, limit: int = 200) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        value_rows = connection.execute(
            """
            with selected as (
              select category, name, label, count(*) as sample_count,
                     min(date) as start_date, max(date) as end_date
              from historical_observations
              group by category, name, label
              order by sample_count desc, category, name, label
              limit ?
            )
            select o.category, o.name, o.label, o.date, o.value,
                   coalesce(o.unit, ''), coalesce(o.source, ''),
                   selected.sample_count, selected.start_date, selected.end_date
            from selected
            join historical_observations o
              on o.category = selected.category
             and o.name = selected.name
             and o.label = selected.label
            order by selected.sample_count desc, o.category, o.name, o.label, o.date, o.id
            """,
            (max(1, int(limit)),),
        ).fetchall()
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for category, name, label, point_date, value, unit, source, count, start_date, end_date in value_rows:
        key = (str(category), str(name), str(label))
        item = grouped.setdefault(
            key,
            {
                "category": category,
                "name": name,
                "label": label,
                "unit": unit,
                "source": source,
                "count": int(count),
                "startDate": start_date,
                "endDate": end_date,
                "latest": None,
                "_values": [],
            },
        )
        if is_finite_number(value):
            numeric = float(value)
            item["_values"].append(numeric)
            item["latest"] = round_float(numeric)
        item["unit"] = unit
        item["source"] = source
        item["endDate"] = point_date
    rows: list[dict[str, Any]] = []
    for item in grouped.values():
        values = item.pop("_values")
        item.update(
            {
                "min": round_float(min(values)) if values else None,
                "max": round_float(max(values)) if values else None,
                "mean": round_float(sum(values) / len(values)) if values else None,
                "p10": round_float(quantile(values, 0.1)) if values else None,
                "p50": round_float(quantile(values, 0.5)) if values else None,
                "p90": round_float(quantile(values, 0.9)) if values else None,
            }
        )
        rows.append(item)
    return rows


def historical_series_points(
    db_path: Path = DEFAULT_HISTORY_DB,
    *,
    category: str | None = None,
    name: str | None = None,
    label: str | None = None,
    start_date: str | None = None,
    limit: int = 1500,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if name:
        clauses.append("name = ?")
        params.append(name)
    if label is not None:
        clauses.append("label = ?")
        params.append(label)
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    where = f"where {' and '.join(clauses)}" if clauses else ""
    query = f"""
        select date, category, name, label, value, coalesce(unit, ''), coalesce(source, '')
        from historical_observations
        {where}
        order by date asc
    """
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        rows = connection.execute(query, params).fetchall()
    points = [
        {
            "date": row[0],
            "category": row[1],
            "name": row[2],
            "label": row[3],
            "value": round_float(float(row[4])),
            "unit": row[5],
            "source": row[6],
        }
        for row in rows
    ]
    return downsample_points(points, max(1, int(limit)))


def historical_series_payload(
    db_path: Path = DEFAULT_HISTORY_DB,
    *,
    category: str | None = None,
    name: str | None = None,
    label: str | None = None,
    start_date: str | None = None,
    limit: int = 1500,
) -> dict[str, Any]:
    points = historical_series_points(
        db_path,
        category=category,
        name=name,
        label=label,
        start_date=start_date,
        limit=limit,
    )
    series = None
    for item in list_historical_series_stats(db_path, limit=1000):
        if category and item["category"] != category:
            continue
        if name and item["name"] != name:
            continue
        if label is not None and item["label"] != label:
            continue
        series = item
        break
    if series is None and points:
        first = points[0]
        series = {
            "category": first["category"],
            "name": first["name"],
            "label": first["label"],
            "unit": first["unit"],
            "source": first["source"],
            "count": len(points),
            "startDate": points[0]["date"],
            "endDate": points[-1]["date"],
        }
    if series is None:
        series = {"category": category or "", "name": name or "", "label": label or ""}
    return {"series": series, "points": points}


def required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"dashboard.{key} is required for history persistence")
    return value


def safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_historical_observation(observation: dict[str, Any]) -> dict[str, Any] | None:
    date_value = normalize_date(observation.get("date"))
    category = normalize_required_text(observation.get("category"))
    name = normalize_required_text(observation.get("name"))
    value = safe_float(observation.get("value"))
    if date_value is None or category is None or name is None or value is None or not math.isfinite(value):
        return None
    return {
        "date": date_value,
        "category": category,
        "name": name,
        "label": str(observation.get("label") or ""),
        "value": value,
        "unit": str(observation.get("unit") or ""),
        "source": str(observation.get("source") or ""),
    }


def normalize_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def normalize_required_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_finite_number(value: Any) -> bool:
    numeric = safe_float(value)
    return numeric is not None and math.isfinite(numeric)


def quantile(values: list[float], q: float) -> float:
    sample = sorted(value for value in values if math.isfinite(value))
    if not sample:
        return math.nan
    if len(sample) == 1:
        return sample[0]
    position = (len(sample) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sample[int(position)]
    weight = position - lower
    return sample[lower] * (1 - weight) + sample[upper] * weight


def round_float(value: float, digits: int = 6) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == -0.0 else rounded


def downsample_points(points: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(points) <= limit:
        return points
    if limit <= 1:
        return points[-1:]
    last = len(points) - 1
    indices = sorted({round(index * last / (limit - 1)) for index in range(limit)})
    return [points[index] for index in indices]


def scalar_int(connection: sqlite3.Connection, query: str) -> int:
    row = connection.execute(query).fetchone()
    return int(row[0]) if row else 0
