"""Public-safe aggregate workout results.

The functions in this module read the local ``workouts`` table but deliberately
return only calendar buckets and aggregate values. Record identifiers, source
metadata, devices, and exact workout timestamps never enter the result.
"""

from __future__ import annotations

import json
from typing import Any

import duckdb

_NORMALIZED_WORKOUTS_SQL = """
SELECT
    COALESCE(NULLIF(TRIM(activity_type), ''), 'Other') AS activity_type,
    start_at,
    CASE
        WHEN duration_minutes IS NOT NULL
             AND isfinite(duration_minutes)
             AND duration_minutes >= 0
        THEN duration_minutes
        ELSE NULL
    END AS duration_minutes
FROM workouts
"""


def public_workout_snapshot(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Build a JSON-ready workout summary without workout-level records.

    A consistency streak means consecutive Monday-based calendar weeks with at
    least one recorded workout. It describes the records present in the local
    database; it does not claim that missing weeks represent inactivity.
    """
    overview_row = connection.execute(
        f"""
        WITH normalized AS ({_NORMALIZED_WORKOUTS_SQL})
        SELECT
            COUNT(*) AS workout_count,
            COALESCE(SUM(duration_minutes), 0) AS total_minutes,
            MEDIAN(duration_minutes) AS median_duration_minutes,
            COUNT(DISTINCT CAST(date_trunc('week', start_at) AS DATE)) AS active_weeks,
            COUNT(DISTINCT activity_type) AS activity_type_count
        FROM normalized
        """
    ).fetchone()
    assert overview_row is not None

    workout_count = int(overview_row[0])
    overview = {
        "workout_count": workout_count,
        "total_minutes": _rounded_minutes(overview_row[1]) or 0.0,
        "median_duration_minutes": _rounded_minutes(overview_row[2]),
        "active_weeks": int(overview_row[3]),
        "activity_type_count": int(overview_row[4]),
        "longest_consistency_streak_weeks": (
            _longest_active_week_streak(connection) if workout_count else 0
        ),
    }

    by_year = []
    activity_types = []
    monthly = []
    if workout_count:
        by_year = _yearly_results(connection)
        activity_types = _activity_results(connection)
        monthly = _monthly_results(connection)

    return {
        "schema_version": "1.0",
        "result_type": "aggregate_workout_history",
        "privacy": {
            "time_granularity": "month_or_coarser",
            "workout_level_rows_included": False,
            "source_or_device_metadata_included": False,
        },
        "methodology": {
            "active_week": "Monday-based calendar week with at least one recorded workout.",
            "consistency_streak": (
                "Consecutive observed active weeks; gaps may reflect missing records."
            ),
            "duration_handling": (
                "Missing, non-finite, or negative durations are omitted from duration "
                "totals and medians but remain in workout counts."
            ),
        },
        "overview": overview,
        "by_year": by_year,
        "activity_types": activity_types,
        "monthly": monthly,
        "limitations": [
            "Results describe only workouts present in the local database.",
            "Calendar aggregates do not establish training quality or health effects.",
            "A recorded consistency streak is not proof that unrecorded weeks were inactive.",
        ],
    }


def public_workout_snapshot_json(connection: duckdb.DuckDBPyConnection) -> str:
    """Serialize :func:`public_workout_snapshot` for a reviewed public artifact."""
    return json.dumps(public_workout_snapshot(connection), indent=2)


def _yearly_results(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"""
        WITH normalized AS ({_NORMALIZED_WORKOUTS_SQL})
        SELECT
            CAST(date_part('year', start_at) AS INTEGER) AS calendar_year,
            COUNT(*) AS workout_count,
            COALESCE(SUM(duration_minutes), 0) AS total_minutes,
            MEDIAN(duration_minutes) AS median_duration_minutes,
            COUNT(DISTINCT CAST(date_trunc('week', start_at) AS DATE)) AS active_weeks
        FROM normalized
        GROUP BY calendar_year
        ORDER BY calendar_year
        """
    ).fetchall()
    return [
        {
            "year": int(year),
            "workout_count": int(count),
            "total_minutes": _rounded_minutes(total) or 0.0,
            "median_duration_minutes": _rounded_minutes(median),
            "active_weeks": int(active_weeks),
        }
        for year, count, total, median, active_weeks in rows
    ]


def _activity_results(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"""
        WITH normalized AS ({_NORMALIZED_WORKOUTS_SQL})
        SELECT
            activity_type,
            COUNT(*) AS workout_count,
            COALESCE(SUM(duration_minutes), 0) AS total_minutes,
            MEDIAN(duration_minutes) AS median_duration_minutes,
            COUNT(DISTINCT CAST(date_trunc('week', start_at) AS DATE)) AS active_weeks
        FROM normalized
        GROUP BY activity_type
        ORDER BY workout_count DESC, total_minutes DESC, activity_type
        """
    ).fetchall()
    return [
        {
            "activity_type": str(activity_type),
            "workout_count": int(count),
            "total_minutes": _rounded_minutes(total) or 0.0,
            "median_duration_minutes": _rounded_minutes(median),
            "active_weeks": int(active_weeks),
        }
        for activity_type, count, total, median, active_weeks in rows
    ]


def _monthly_results(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"""
        WITH normalized AS ({_NORMALIZED_WORKOUTS_SQL}),
        bounds AS (
            SELECT
                CAST(MIN(date_trunc('month', start_at)) AS DATE) AS first_month,
                CAST(MAX(date_trunc('month', start_at)) AS DATE) AS last_month
            FROM normalized
        ),
        calendar AS (
            SELECT CAST(month_start AS DATE) AS month_start
            FROM bounds,
                 generate_series(first_month, last_month, INTERVAL '1 month')
                 AS series(month_start)
        ),
        actual AS (
            SELECT
                CAST(date_trunc('month', start_at) AS DATE) AS month_start,
                COUNT(*) AS workout_count,
                COALESCE(SUM(duration_minutes), 0) AS total_minutes,
                MEDIAN(duration_minutes) AS median_duration_minutes,
                COUNT(DISTINCT CAST(date_trunc('week', start_at) AS DATE)) AS active_weeks
            FROM normalized
            GROUP BY month_start
        )
        SELECT
            strftime(calendar.month_start, '%Y-%m') AS calendar_month,
            COALESCE(actual.workout_count, 0) AS workout_count,
            COALESCE(actual.total_minutes, 0) AS total_minutes,
            actual.median_duration_minutes,
            COALESCE(actual.active_weeks, 0) AS active_weeks
        FROM calendar
        LEFT JOIN actual USING (month_start)
        ORDER BY calendar.month_start
        """
    ).fetchall()
    return [
        {
            "month": str(month),
            "workout_count": int(count),
            "total_minutes": _rounded_minutes(total) or 0.0,
            "median_duration_minutes": _rounded_minutes(median),
            "active_weeks": int(active_weeks),
        }
        for month, count, total, median, active_weeks in rows
    ]


def _longest_active_week_streak(connection: duckdb.DuckDBPyConnection) -> int:
    row = connection.execute(
        f"""
        WITH normalized AS ({_NORMALIZED_WORKOUTS_SQL}),
        active_weeks AS (
            SELECT DISTINCT CAST(date_trunc('week', start_at) AS DATE) AS week_start
            FROM normalized
        ),
        previous_weeks AS (
            SELECT
                week_start,
                LAG(week_start) OVER (ORDER BY week_start) AS previous_week
            FROM active_weeks
        ),
        boundaries AS (
            SELECT
                week_start,
                CASE
                    WHEN previous_week IS NULL
                         OR date_diff('day', previous_week, week_start) <> 7
                    THEN 1
                    ELSE 0
                END AS begins_streak
            FROM previous_weeks
        ),
        grouped AS (
            SELECT
                week_start,
                SUM(begins_streak) OVER (ORDER BY week_start) AS streak_id
            FROM boundaries
        ),
        streaks AS (
            SELECT COUNT(*) AS active_week_count
            FROM grouped
            GROUP BY streak_id
        )
        SELECT COALESCE(MAX(active_week_count), 0)
        FROM streaks
        """
    ).fetchone()
    return int(row[0]) if row else 0


def _rounded_minutes(value: object) -> float | None:
    if value is None:
        return None
    return round(float(value), 1)
