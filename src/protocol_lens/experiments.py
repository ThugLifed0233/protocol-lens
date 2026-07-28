"""Personal intervention periods and reviewable outcome snapshots."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta

import duckdb
import pandas as pd

from .analysis import daily_metrics
from .spreadsheet import canonical_metric, metric_label

INTERVENTION_CATEGORIES = {"supplement", "nootropic", "nutrition", "other"}
INTERVENTION_COLUMNS = {
    "intervention",
    "compound",
    "name",
    "category",
    "start_date",
    "end_date",
    "dose_note",
    "purpose",
    "confidence",
    "visibility",
    "notes",
}


def add_compound_period(
    connection: duckdb.DuckDBPyConnection,
    *,
    display_name: str,
    category: str,
    start_date: date,
    end_date: date | None,
    dose_note: str = "",
    purpose: str = "",
    confidence: str = "confirmed",
    visibility: str = "personal_only",
    notes: str = "",
) -> str:
    if not display_name.strip():
        raise ValueError("Add a compound or intervention name")
    if end_date and end_date < start_date:
        raise ValueError("End date cannot be before the start date")
    if category not in INTERVENTION_CATEGORIES:
        raise ValueError("Unsupported intervention category")
    if confidence not in {"confirmed", "approximate", "unverified"}:
        raise ValueError("Unsupported confidence value")
    if visibility not in {"personal_only", "publishable"}:
        raise ValueError("Unsupported visibility value")

    period_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO compound_periods (
            period_id, compound_key, display_name, category, start_date, end_date,
            dose_note, purpose, confidence, visibility, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            period_id,
            canonical_metric(display_name),
            display_name.strip(),
            category,
            start_date,
            end_date,
            dose_note.strip(),
            purpose.strip(),
            confidence,
            visibility,
            notes.strip(),
        ],
    )
    return period_id


def list_compound_periods(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT period_id, display_name, category, start_date, end_date, dose_note,
               purpose, confidence, visibility, notes
        FROM compound_periods
        ORDER BY start_date DESC, display_name
        """
    ).df()


def import_compound_periods(
    connection: duckdb.DuckDBPyConnection,
    frame: pd.DataFrame,
) -> int:
    """Bulk-import reviewed intervention periods from CSV/XLSX data."""
    normalized = frame.copy()
    normalized.columns = [str(column).strip().lower() for column in normalized.columns]
    unexpected = set(normalized.columns) - INTERVENTION_COLUMNS
    if unexpected:
        raise ValueError(f"Unsupported intervention columns: {', '.join(sorted(unexpected))}")
    name_column = next(
        (column for column in ("intervention", "compound", "name") if column in normalized),
        None,
    )
    if not name_column or "start_date" not in normalized:
        raise ValueError("Add intervention (or compound/name) and start_date columns")

    imported = 0
    for row in normalized.to_dict(orient="records"):
        display_name = _text(row.get(name_column))
        if not display_name:
            continue
        start = pd.to_datetime(row.get("start_date"), errors="coerce")
        if pd.isna(start):
            raise ValueError(f"Invalid start_date for {display_name}")
        raw_end = row.get("end_date")
        end = pd.to_datetime(raw_end, errors="coerce") if _text(raw_end) else None
        if end is not None and pd.isna(end):
            raise ValueError(f"Invalid end_date for {display_name}")
        add_compound_period(
            connection,
            display_name=display_name,
            category=_text(row.get("category")) or "supplement",
            start_date=start.date(),
            end_date=end.date() if end is not None else None,
            dose_note=_text(row.get("dose_note")),
            purpose=_text(row.get("purpose")),
            confidence=_text(row.get("confidence")) or "approximate",
            visibility=_text(row.get("visibility")) or "personal_only",
            notes=_text(row.get("notes")),
        )
        imported += 1
    if not imported:
        raise ValueError("No valid intervention periods were found")
    return imported


def analyze_compound_periods(
    connection: duckdb.DuckDBPyConnection,
    window_days: int = 14,
) -> pd.DataFrame:
    """Compare each recorded period with equal before and after windows."""
    frame = daily_metrics(connection)
    periods = list_compound_periods(connection)
    if frame.empty or periods.empty:
        return pd.DataFrame()

    frame.index = pd.to_datetime(frame.index).normalize()
    last_observation = frame.index.max().date()
    results: list[dict] = []

    for period in periods.itertuples(index=False):
        start = _as_date(period.start_date)
        end = _as_date(period.end_date) if not pd.isna(period.end_date) else last_observation
        if end < start:
            continue
        baseline_start = start - timedelta(days=window_days)
        after_end = end + timedelta(days=window_days)

        baseline = _slice(frame, baseline_start, start - timedelta(days=1))
        during = _slice(frame, start, end)
        after = _slice(frame, end + timedelta(days=1), after_end)

        for metric in frame.columns:
            if metric == "workout_count":
                continue
            baseline_values = baseline[metric].dropna()
            during_values = during[metric].dropna()
            after_values = after[metric].dropna()
            if baseline_values.empty or during_values.empty:
                continue
            baseline_mean = float(baseline_values.mean())
            during_mean = float(during_values.mean())
            delta = during_mean - baseline_mean
            relative = (delta / abs(baseline_mean) * 100) if baseline_mean else None
            coverage = min(
                len(baseline_values) / max(window_days, 1),
                len(during_values) / max((end - start).days + 1, 1),
            )
            results.append(
                {
                    "period_id": period.period_id,
                    "compound": period.display_name,
                    "category": period.category,
                    "start_date": start,
                    "end_date": end,
                    "dose_note": period.dose_note,
                    "purpose": period.purpose,
                    "source_confidence": period.confidence,
                    "visibility": period.visibility,
                    "metric": metric,
                    "metric_label": metric_label(metric),
                    "baseline_mean": baseline_mean,
                    "during_mean": during_mean,
                    "after_mean": (
                        float(after_values.mean()) if not after_values.empty else None
                    ),
                    "absolute_change": delta,
                    "relative_change_percent": relative,
                    "baseline_days": len(baseline_values),
                    "during_days": len(during_values),
                    "after_days": len(after_values),
                    "coverage": coverage,
                    "direction": _direction(delta),
                    "analysis_confidence": _analysis_confidence(
                        len(baseline_values), len(during_values), coverage
                    ),
                }
            )
    return pd.DataFrame(results)


def public_snapshot(
    connection: duckdb.DuckDBPyConnection,
    window_days: int = 14,
) -> dict:
    """Return a deliberately limited snapshot safe for manual public review."""
    analysis = analyze_compound_periods(connection, window_days=window_days)
    if analysis.empty:
        public_rows = []
    else:
        public = analysis[
            (analysis["visibility"] == "publishable")
            & analysis["category"].isin(INTERVENTION_CATEGORIES)
        ].copy()
        public_rows = []
        for row in public.itertuples(index=False):
            public_rows.append(
                {
                    "experiment_id": _public_id(row.period_id),
                    "intervention": row.compound,
                    "category": row.category,
                    "metric": row.metric,
                    "metric_label": row.metric_label,
                    "direction": row.direction,
                    "relative_change_percent": (
                        round(row.relative_change_percent, 2)
                        if row.relative_change_percent is not None
                        and not pd.isna(row.relative_change_percent)
                        else None
                    ),
                    "baseline_days": int(row.baseline_days),
                    "during_days": int(row.during_days),
                    "after_days": int(row.after_days),
                    "data_coverage": round(float(row.coverage), 3),
                    "confidence": row.analysis_confidence,
                    "interpretation": "descriptive_within_person_association",
                }
            )

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "project": "Protocol Lens",
        "data_sources": ["Apple Health", "user-recorded intervention periods"],
        "sharing": {
            "contains_raw_health_data": False,
            "contains_exact_dates": False,
            "contains_doses_or_notes": False,
        },
        "limitations": [
            "Results are descriptive within-person associations.",
            "They do not establish causation, efficacy, or safety.",
            "Unmeasured confounders may explain observed changes.",
        ],
        "results": public_rows,
    }


def public_snapshot_json(
    connection: duckdb.DuckDBPyConnection,
    window_days: int = 14,
) -> str:
    return json.dumps(public_snapshot(connection, window_days), indent=2)


def public_snapshot_csv(
    connection: duckdb.DuckDBPyConnection,
    window_days: int = 14,
) -> str:
    snapshot = public_snapshot(connection, window_days)
    return pd.DataFrame(snapshot["results"]).to_csv(index=False)


def _slice(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if end < start:
        return frame.iloc[0:0]
    return frame.loc[pd.Timestamp(start) : pd.Timestamp(end)]


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _direction(delta: float) -> str:
    if abs(delta) < 1e-9:
        return "no_observed_change"
    return "higher_during" if delta > 0 else "lower_during"


def _analysis_confidence(baseline_days: int, during_days: int, coverage: float) -> str:
    if min(baseline_days, during_days) >= 10 and coverage >= 0.7:
        return "moderate"
    if min(baseline_days, during_days) >= 4 and coverage >= 0.35:
        return "low"
    return "insufficient"


def _public_id(period_id: str) -> str:
    digest = hashlib.sha256(period_id.encode()).hexdigest()[:10]
    return f"experiment-{digest}"


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()
