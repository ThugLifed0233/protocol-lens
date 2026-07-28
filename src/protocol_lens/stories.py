"""Experiment-loop metadata and public intervention stories."""

from __future__ import annotations

import uuid

import duckdb
import pandas as pd

from .experiments import analyze_compound_periods, list_compound_periods

EXPECTED_DIRECTIONS = {"higher", "lower", "stable", "observe"}
REVIEW_DECISIONS = {"continue", "change", "stop", "measure_more", "inconclusive"}


def save_expectation(
    connection: duckdb.DuckDBPyConnection,
    *,
    intervention_key: str,
    metric_key: str,
    expected_direction: str,
    rationale: str = "",
) -> None:
    if expected_direction not in EXPECTED_DIRECTIONS:
        raise ValueError("Unsupported expected direction")
    connection.execute(
        """
        INSERT INTO intervention_expectations (
            intervention_key, metric_key, expected_direction, rationale
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT (intervention_key, metric_key) DO UPDATE SET
            expected_direction = excluded.expected_direction,
            rationale = excluded.rationale
        """,
        [intervention_key, metric_key, expected_direction, rationale.strip()],
    )


def save_reference(
    connection: duckdb.DuckDBPyConnection,
    *,
    intervention_key: str,
    title: str,
    publisher: str,
    url: str,
    note: str = "",
    sort_order: int = 0,
) -> str:
    if not title.strip() or not url.startswith("https://"):
        raise ValueError("Add a title and an https:// source URL")
    reference_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO intervention_references (
            reference_id, intervention_key, title, publisher, url, note, sort_order
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            reference_id,
            intervention_key,
            title.strip(),
            publisher.strip(),
            url.strip(),
            note.strip(),
            sort_order,
        ],
    )
    return reference_id


def save_review(
    connection: duckdb.DuckDBPyConnection,
    *,
    period_id: str,
    decision: str,
    observed_summary: str = "",
    confounders: str = "",
) -> None:
    if decision not in REVIEW_DECISIONS:
        raise ValueError("Unsupported review decision")
    connection.execute(
        """
        INSERT INTO intervention_reviews (
            period_id, decision, observed_summary, confounders
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT (period_id) DO UPDATE SET
            decision = excluded.decision,
            observed_summary = excluded.observed_summary,
            confounders = excluded.confounders,
            reviewed_at = now()
        """,
        [period_id, decision, observed_summary.strip(), confounders.strip()],
    )


def intervention_story(
    connection: duckdb.DuckDBPyConnection,
    intervention_key: str,
) -> dict:
    profile_row = connection.execute(
        """
        SELECT display_name, category, description, expected_outcomes, personal_goal,
               color, source_confidence, visibility
        FROM intervention_profiles
        WHERE intervention_key = ?
        """,
        [intervention_key],
    ).fetchone()
    if not profile_row:
        raise ValueError("Intervention profile not found")

    profile_columns = [
        "display_name",
        "category",
        "description",
        "expected_outcomes",
        "personal_goal",
        "color",
        "source_confidence",
        "visibility",
    ]
    profile = dict(zip(profile_columns, profile_row, strict=True))
    expectations = connection.execute(
        """
        SELECT metric_key, expected_direction, rationale
        FROM intervention_expectations
        WHERE intervention_key = ?
        ORDER BY metric_key
        """,
        [intervention_key],
    ).df()
    references = connection.execute(
        """
        SELECT title, publisher, url, note
        FROM intervention_references
        WHERE intervention_key = ?
        ORDER BY sort_order, title
        """,
        [intervention_key],
    ).df()
    periods = list_compound_periods(connection)
    periods = periods[periods["compound_key"] == intervention_key]
    analysis = analyze_compound_periods(connection)
    if not analysis.empty and not periods.empty:
        analysis = analysis[analysis["period_id"].isin(periods["period_id"])]
    else:
        analysis = pd.DataFrame()
    reviews = connection.execute(
        """
        SELECT r.period_id, r.decision, r.observed_summary, r.confounders
        FROM intervention_reviews r
        JOIN compound_periods p ON p.period_id = r.period_id
        WHERE p.compound_key = ?
        """,
        [intervention_key],
    ).df()

    return {
        "key": intervention_key,
        "profile": profile,
        "expectations": expectations.to_dict(orient="records"),
        "references": references.to_dict(orient="records"),
        "periods": periods,
        "analysis": analysis,
        "reviews": reviews.to_dict(orient="records"),
    }


def review_queue(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT p.period_id, p.display_name, p.start_date, p.end_date, p.confidence,
               p.visibility,
               CASE WHEN r.period_id IS NULL THEN false ELSE true END AS reviewed
        FROM compound_periods p
        LEFT JOIN intervention_reviews r ON r.period_id = p.period_id
        WHERE p.confidence != 'confirmed'
           OR p.visibility != 'publishable'
           OR r.period_id IS NULL
        ORDER BY p.display_name, p.start_date
        """
    ).df()
