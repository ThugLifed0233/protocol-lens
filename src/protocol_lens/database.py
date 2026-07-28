"""Embedded DuckDB storage and idempotent Apple Health imports."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

import duckdb

from .apple_health import IntervalRecord, SignalRecord, WorkoutRecord

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS imports (
    file_hash VARCHAR PRIMARY KEY,
    filename VARCHAR NOT NULL,
    imported_at TIMESTAMPTZ DEFAULT now(),
    parser_version VARCHAR NOT NULL,
    record_count BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    record_id VARCHAR PRIMARY KEY,
    metric_key VARCHAR NOT NULL,
    value DOUBLE NOT NULL,
    unit VARCHAR,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    source_name VARCHAR,
    source_version VARCHAR,
    device VARCHAR
);

CREATE TABLE IF NOT EXISTS intervals (
    record_id VARCHAR PRIMARY KEY,
    kind VARCHAR NOT NULL,
    value VARCHAR,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    source_name VARCHAR
);

CREATE TABLE IF NOT EXISTS workouts (
    record_id VARCHAR PRIMARY KEY,
    activity_type VARCHAR NOT NULL,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    duration_minutes DOUBLE,
    energy_kcal DOUBLE,
    distance_km DOUBLE,
    source_name VARCHAR,
    device VARCHAR
);

CREATE TABLE IF NOT EXISTS compound_periods (
    period_id VARCHAR PRIMARY KEY,
    compound_key VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    dose_note VARCHAR,
    purpose VARCHAR,
    confidence VARCHAR NOT NULL,
    visibility VARCHAR NOT NULL,
    notes VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    connection.execute(SCHEMA_SQL)
    return connection


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_records(
    connection: duckdb.DuckDBPyConnection,
    records: Iterable[SignalRecord | IntervalRecord | WorkoutRecord],
    source_path: Path,
    parser_version: str,
    display_filename: str | None = None,
    batch_size: int = 10_000,
) -> tuple[int, int]:
    """Insert records in batches. Returns (seen, inserted-or-new-file count)."""
    digest = file_hash(source_path)
    existing = connection.execute(
        "SELECT record_count FROM imports WHERE file_hash = ?", [digest]
    ).fetchone()
    if existing:
        return int(existing[0]), 0

    signal_rows: list[tuple] = []
    interval_rows: list[tuple] = []
    workout_rows: list[tuple] = []
    seen = 0

    def flush() -> None:
        if signal_rows:
            connection.executemany(
                "INSERT OR IGNORE INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                signal_rows,
            )
            signal_rows.clear()
        if interval_rows:
            connection.executemany(
                "INSERT OR IGNORE INTO intervals VALUES (?, ?, ?, ?, ?, ?)",
                interval_rows,
            )
            interval_rows.clear()
        if workout_rows:
            connection.executemany(
                "INSERT OR IGNORE INTO workouts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                workout_rows,
            )
            workout_rows.clear()

    for record in records:
        seen += 1
        if isinstance(record, SignalRecord):
            payload = (
                record.metric_key,
                record.value,
                record.unit,
                record.start_at.isoformat(),
                record.end_at.isoformat(),
                record.source_name,
                record.source_version,
                record.device,
            )
            signal_rows.append((_record_id("signal", payload), *payload))
        elif isinstance(record, IntervalRecord):
            payload = (
                record.kind,
                record.value,
                record.start_at.isoformat(),
                record.end_at.isoformat(),
                record.source_name,
            )
            interval_rows.append((_record_id("interval", payload), *payload))
        else:
            payload = (
                record.activity_type,
                record.start_at.isoformat(),
                record.end_at.isoformat(),
                record.duration_minutes,
                record.energy_kcal,
                record.distance_km,
                record.source_name,
                record.device,
            )
            workout_rows.append((_record_id("workout", payload), *payload))
        if seen % batch_size == 0:
            flush()
    flush()

    connection.execute(
        "INSERT INTO imports (file_hash, filename, parser_version, record_count) "
        "VALUES (?, ?, ?, ?)",
        [digest, display_filename or source_path.name, parser_version, seen],
    )
    return seen, seen


def _record_id(kind: str, payload: tuple) -> str:
    encoded = "\x1f".join("" if item is None else str(item) for item in payload)
    return hashlib.sha256(f"{kind}\x1e{encoded}".encode()).hexdigest()
