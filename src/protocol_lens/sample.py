"""Deterministic synthetic Apple-like data for the public demo."""

from __future__ import annotations

import math
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from .apple_health import IntervalRecord, SignalRecord, WorkoutRecord
from .database import connect, ingest_records


def build_sample_database(path: Path, days: int = 120) -> None:
    records: list[SignalRecord | IntervalRecord | WorkoutRecord] = []
    start = datetime(2026, 1, 1, tzinfo=UTC)

    for day in range(days):
        date = start + timedelta(days=day)
        workout_day = day % 3 in (0, 1)
        sleep = 6.5 + 0.75 * math.sin(day / 8) + (0.3 if not workout_day else 0)
        resting_hr = 72 - (day * 0.025) - (sleep - 6.5) * 1.8 + 0.8 * math.sin(day / 5)
        hrv = 42 + (sleep - 6.5) * 3.2 + 1.7 * math.cos(day / 7)
        steps = 5600 + (3300 if workout_day else 900) + 800 * math.sin(day / 6)

        records.extend(
            [
                _signal("resting_heart_rate", resting_hr, "count/min", date),
                _signal("hrv_sdnn", hrv, "ms", date),
                _signal("steps", steps, "count", date),
                _signal("active_energy", 380 + steps * 0.035, "kcal", date),
            ]
        )
        sleep_end = datetime.combine(date.date(), time(7, 30), tzinfo=UTC)
        records.append(
            IntervalRecord(
                kind="sleep",
                value="HKCategoryValueSleepAnalysisAsleepCore",
                start_at=sleep_end - timedelta(hours=sleep),
                end_at=sleep_end,
                source_name="Synthetic Apple Watch",
            )
        )
        if workout_day:
            workout_start = datetime.combine(date.date(), time(18), tzinfo=UTC)
            records.append(
                WorkoutRecord(
                    activity_type="TraditionalStrengthTraining" if day % 3 == 0 else "Walking",
                    start_at=workout_start,
                    end_at=workout_start + timedelta(minutes=48),
                    duration_minutes=48,
                    energy_kcal=310,
                    distance_km=None if day % 3 == 0 else 3.8,
                    source_name="Synthetic Apple Watch",
                    device="Public demo",
                )
            )

    source = path.parent / ".sample-source"
    source.write_text("Protocol Lens deterministic public sample v1")
    connection = connect(path)
    try:
        ingest_records(connection, records, source, "sample-v1")
    finally:
        connection.close()
        source.unlink(missing_ok=True)


def _signal(metric: str, value: float, unit: str, date: datetime) -> SignalRecord:
    return SignalRecord(
        metric_key=metric,
        value=round(value, 2),
        unit=unit,
        start_at=date,
        end_at=date + timedelta(minutes=1),
        source_name="Synthetic Apple Watch",
        source_version="demo",
        device="Public demo",
    )

