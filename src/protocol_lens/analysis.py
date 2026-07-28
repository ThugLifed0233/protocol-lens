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


@dataclass(frozen=True)
class MetricWindow:
    metric: str
    start: pd.Timestamp
    end: pd.Timestamp
    mean: float
    median: float
    minimum: float
    maximum: float
    observations: int
    coverage: float
    previous_mean: float | None
    change_percent: float | None


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


def metric_window_summary(
    frame: pd.DataFrame,
    metric: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> MetricWindow | None:
    """Describe one visible graph window and compare it with the equal preceding window."""
    if metric not in frame or end < start:
        return None
    normalized_start = pd.Timestamp(start).normalize()
    normalized_end = pd.Timestamp(end).normalize()
    visible = frame.loc[normalized_start:normalized_end, metric].dropna()
    if visible.empty:
        return None

    calendar_days = max((normalized_end - normalized_start).days + 1, 1)
    previous_end = normalized_start - pd.DateOffset(days=1)
    previous_start = previous_end - pd.DateOffset(days=calendar_days - 1)
    previous = frame.loc[previous_start:previous_end, metric].dropna()
    current_mean = float(visible.mean())
    previous_mean = float(previous.mean()) if not previous.empty else None
    change = None
    if previous_mean is not None and previous_mean != 0:
        change = (current_mean - previous_mean) / abs(previous_mean) * 100

    return MetricWindow(
        metric=metric,
        start=normalized_start,
        end=normalized_end,
        mean=current_mean,
        median=float(visible.median()),
        minimum=float(visible.min()),
        maximum=float(visible.max()),
        observations=len(visible),
        coverage=min(len(visible) / calendar_days, 1.0),
        previous_mean=previous_mean,
        change_percent=change,
    )
