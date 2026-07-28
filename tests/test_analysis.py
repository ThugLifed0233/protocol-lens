from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from protocol_lens.analysis import correlations, daily_metrics, metric_window_summary
from protocol_lens.apple_health import IntervalRecord, SignalRecord, WorkoutRecord
from protocol_lens.database import connect, ingest_records


def test_daily_metrics_and_correlations(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_text("fixture")
    database = tmp_path / "test.duckdb"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    records = []
    for day in range(10):
        date = start + timedelta(days=day)
        records.extend(
            [
                SignalRecord(
                    "resting_heart_rate", 75 - day, "count/min", date, date, "test", "", ""
                ),
                SignalRecord("steps", 5000 + day * 500, "count", date, date, "test", "", ""),
                IntervalRecord(
                    "sleep",
                    "HKCategoryValueSleepAnalysisAsleepCore",
                    date,
                    date + timedelta(hours=7),
                    "test",
                ),
            ]
        )
        if day % 2 == 0:
            records.append(
                WorkoutRecord(
                    "Walking",
                    date,
                    date + timedelta(minutes=30),
                    30,
                    100,
                    2,
                    "test",
                    "",
                )
            )

    connection = connect(database)
    ingest_records(connection, records, source, "test")
    frame = daily_metrics(connection)
    results = correlations(frame)
    connection.close()

    assert len(frame) == 10
    assert frame["sleep_hours"].iloc[0] == 7
    strongest = results[0]
    assert {strongest.left, strongest.right} == {"resting_heart_rate", "steps"}
    assert strongest.coefficient < -0.99


def test_metric_window_summary_compares_equal_previous_period() -> None:
    index = pd.date_range("2026-01-01", periods=20, freq="D")
    frame = pd.DataFrame({"steps": [100.0] * 10 + [120.0] * 10}, index=index)

    summary = metric_window_summary(
        frame,
        "steps",
        pd.Timestamp("2026-01-11"),
        pd.Timestamp("2026-01-20"),
    )

    assert summary is not None
    assert summary.mean == 120
    assert summary.previous_mean == 100
    assert summary.change_percent == 20
    assert summary.observations == 10
    assert summary.coverage == 1
