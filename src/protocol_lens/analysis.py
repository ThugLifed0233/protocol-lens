"""Daily aggregation, correlations, and workout-aware comparisons."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

from .catalog import ASLEEP_VALUES, BY_KEY


@dataclass(frozen=True)
class Correlation:
    left: str
    right: str
    coefficient: float
    observations: int


def daily_metrics(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    signal_frames = []
    metric_keys = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT metric_key FROM signals ORDER BY metric_key"
        ).fetchall()
    ]
    for key in metric_keys:
        metric = BY_KEY.get(key)
        aggregate = "SUM" if metric and metric.aggregation == "sum" else "AVG"
        frame = connection.execute(
            f"""
            SELECT CAST(start_at AS DATE) AS date, '{key}' AS metric, {aggregate}(value) AS value
            FROM signals
            WHERE metric_key = ?
            GROUP BY 1
            """,
            [key],
        ).df()
        signal_frames.append(frame)

    asleep_placeholders = ", ".join("?" for _ in ASLEEP_VALUES)
    sleep = connection.execute(
        f"""
        SELECT
            CAST(end_at AS DATE) AS date,
            'sleep_hours' AS metric,
            SUM(date_diff('second', start_at, end_at)) / 3600.0 AS value
        FROM intervals
        WHERE kind = 'sleep' AND value IN ({asleep_placeholders})
        GROUP BY 1
        """,
        list(ASLEEP_VALUES),
    ).df()

    workouts = connection.execute(
        """
        SELECT CAST(start_at AS DATE) AS date, 'workout_minutes' AS metric,
               SUM(duration_minutes) AS value
        FROM workouts
        GROUP BY 1
        """
    ).df()
    workout_count = connection.execute(
        """
        SELECT CAST(start_at AS DATE) AS date, 'workout_count' AS metric, COUNT(*) AS value
        FROM workouts
        GROUP BY 1
        """
    ).df()

    long = pd.concat([*signal_frames, sleep, workouts, workout_count], ignore_index=True)
    if long.empty:
        return pd.DataFrame()
    long["date"] = pd.to_datetime(long["date"])
    return long.pivot_table(index="date", columns="metric", values="value", aggfunc="first")


def correlations(frame: pd.DataFrame, minimum_observations: int = 7) -> list[Correlation]:
    results: list[Correlation] = []
    for index, left in enumerate(frame.columns):
        for right in frame.columns[index + 1 :]:
            pair = frame[[left, right]].dropna()
            if len(pair) < minimum_observations:
                continue
            if pair[left].nunique() < 2 or pair[right].nunique() < 2:
                continue
            coefficient = pair[left].corr(pair[right])
            if pd.isna(coefficient):
                continue
            results.append(Correlation(left, right, float(coefficient), len(pair)))
    return sorted(results, key=lambda result: abs(result.coefficient), reverse=True)


def workout_comparison(frame: pd.DataFrame, metric: str) -> tuple[float, float, int, int] | None:
    if metric not in frame.columns or "workout_count" not in frame.columns:
        return None
    sample = frame[[metric, "workout_count"]].dropna(subset=[metric]).copy()
    workout_days = sample[sample["workout_count"].fillna(0) > 0][metric]
    rest_days = sample[sample["workout_count"].fillna(0) == 0][metric]
    if workout_days.empty or rest_days.empty:
        return None
    return (
        float(workout_days.mean()),
        float(rest_days.mean()),
        len(workout_days),
        len(rest_days),
    )
