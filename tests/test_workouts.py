import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from protocol_lens.apple_health import WorkoutRecord
from protocol_lens.database import connect, ingest_records
from protocol_lens.workouts import public_workout_snapshot, public_workout_snapshot_json


def _workout(
    activity_type: str,
    started_at: datetime,
    minutes: float,
) -> WorkoutRecord:
    return WorkoutRecord(
        activity_type=activity_type,
        start_at=started_at,
        end_at=started_at + timedelta(minutes=max(minutes, 0)),
        duration_minutes=minutes,
        energy_kcal=None,
        distance_km=None,
        source_name="Synthetic fixture",
        device="Synthetic device",
    )


def test_public_workout_snapshot_aggregates_without_workout_level_details(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic-source"
    source.write_text("synthetic")
    connection = connect(tmp_path / "workouts.duckdb")
    records = [
        _workout("TraditionalStrengthTraining", datetime(2025, 12, 29, 9, tzinfo=UTC), 60),
        _workout("Walking", datetime(2026, 1, 5, 10, tzinfo=UTC), 30),
        _workout("TraditionalStrengthTraining", datetime(2026, 1, 12, 11, tzinfo=UTC), 45),
        _workout("Walking", datetime(2026, 3, 2, 12, tzinfo=UTC), 25),
    ]
    ingest_records(connection, records, source, "test")

    snapshot = public_workout_snapshot(connection)
    encoded = public_workout_snapshot_json(connection)
    connection.close()

    assert snapshot["overview"] == {
        "workout_count": 4,
        "total_minutes": 160.0,
        "median_duration_minutes": 37.5,
        "active_weeks": 4,
        "activity_type_count": 2,
        "longest_consistency_streak_weeks": 3,
    }
    assert snapshot["by_year"] == [
        {
            "year": 2025,
            "workout_count": 1,
            "total_minutes": 60.0,
            "median_duration_minutes": 60.0,
            "active_weeks": 1,
        },
        {
            "year": 2026,
            "workout_count": 3,
            "total_minutes": 100.0,
            "median_duration_minutes": 30.0,
            "active_weeks": 3,
        },
    ]
    assert snapshot["activity_types"][0]["activity_type"] == "TraditionalStrengthTraining"
    assert snapshot["activity_types"][0]["workout_count"] == 2
    assert [row["month"] for row in snapshot["monthly"]] == [
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
    ]
    assert snapshot["monthly"][2] == {
        "month": "2026-02",
        "workout_count": 0,
        "total_minutes": 0.0,
        "median_duration_minutes": None,
        "active_weeks": 0,
    }

    public_values = json.loads(encoded)
    assert public_values == snapshot
    assert "2026-01-05T10:00:00" not in encoded
    assert "Synthetic fixture" not in encoded
    assert "Synthetic device" not in encoded
    assert records[1].start_at.isoformat() not in encoded


def test_public_workout_snapshot_handles_empty_and_invalid_durations(tmp_path: Path) -> None:
    connection = connect(tmp_path / "empty.duckdb")
    empty = public_workout_snapshot(connection)

    source = tmp_path / "synthetic-invalid-source"
    source.write_text("synthetic")
    started_at = datetime(2026, 4, 6, 9, tzinfo=UTC)
    ingest_records(
        connection,
        [
            _workout("", started_at, -5),
            _workout("Walking", started_at + timedelta(days=1), 35),
        ],
        source,
        "test",
    )
    populated = public_workout_snapshot(connection)
    connection.close()

    assert empty["overview"] == {
        "workout_count": 0,
        "total_minutes": 0.0,
        "median_duration_minutes": None,
        "active_weeks": 0,
        "activity_type_count": 0,
        "longest_consistency_streak_weeks": 0,
    }
    assert empty["by_year"] == []
    assert empty["activity_types"] == []
    assert empty["monthly"] == []

    assert populated["overview"]["workout_count"] == 2
    assert populated["overview"]["total_minutes"] == 35.0
    assert populated["overview"]["median_duration_minutes"] == 35.0
    assert {row["activity_type"] for row in populated["activity_types"]} == {
        "Other",
        "Walking",
    }
