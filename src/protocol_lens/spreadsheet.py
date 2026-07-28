"""Privacy-conscious spreadsheet import for long and wide health data."""

from __future__ import annotations

import re
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests

from .apple_health import SignalRecord
from .catalog import BY_KEY

DATE_ALIASES = ("date", "datetime", "timestamp", "time", "recorded_at")
METRIC_ALIASES = ("metric", "measurement", "type", "name")
VALUE_ALIASES = ("value", "amount", "reading", "result")
UNIT_ALIASES = ("unit", "units")

COMMON_METRICS = {
    "resting hr": "resting_heart_rate",
    "resting heart rate": "resting_heart_rate",
    "heart rate variability": "hrv_sdnn",
    "hrv": "hrv_sdnn",
    "sleep": "sleep_hours",
    "sleep hours": "sleep_hours",
    "weight": "body_mass",
    "body weight": "body_mass",
    "body mass": "body_mass",
    "active calories": "active_energy",
    "active energy": "active_energy",
    "step count": "steps",
    "steps": "steps",
    "vo2 max": "vo2_max",
    "vo₂ max": "vo2_max",
}


def read_spreadsheet(content: bytes, filename: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    stream = BytesIO(content)
    if suffix == ".csv":
        return pd.read_csv(stream)
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(stream, engine="openpyxl")
    raise ValueError("Use a CSV or XLSX file")


def spreadsheet_records(frame: pd.DataFrame, source_name: str) -> list[SignalRecord]:
    """Normalize long-form or wide-form sheet data to timestamped signals."""
    if frame.empty:
        raise ValueError("The sheet is empty")

    normalized = frame.copy()
    normalized.columns = [str(column).strip() for column in normalized.columns]
    columns = {column.lower(): column for column in normalized.columns}
    date_column = _find_column(columns, DATE_ALIASES)
    if not date_column:
        raise ValueError("Add a date, datetime, timestamp, time, or recorded_at column")

    metric_column = _find_column(columns, METRIC_ALIASES)
    value_column = _find_column(columns, VALUE_ALIASES)
    unit_column = _find_column(columns, UNIT_ALIASES)

    if metric_column and value_column:
        long = pd.DataFrame(
            {
                "date": normalized[date_column],
                "metric": normalized[metric_column],
                "value": normalized[value_column],
                "unit": normalized[unit_column] if unit_column else "",
            }
        )
    else:
        value_columns = [
            column
            for column in normalized.columns
            if column != date_column and pd.to_numeric(normalized[column], errors="coerce").notna().any()
        ]
        if not value_columns:
            raise ValueError(
                "Use long format (date, metric, value) or put dates beside numeric metric columns"
            )
        long = normalized.melt(
            id_vars=[date_column],
            value_vars=value_columns,
            var_name="metric",
            value_name="value",
        ).rename(columns={date_column: "date"})
        long["unit"] = ""

    long["date"] = pd.to_datetime(long["date"], errors="coerce", utc=True)
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["date", "metric", "value"])
    if long.empty:
        raise ValueError("No rows contained a valid date, metric, and numeric value")

    records: list[SignalRecord] = []
    for row in long.itertuples(index=False):
        timestamp = row.date.to_pydatetime()
        records.append(
            SignalRecord(
                metric_key=canonical_metric(str(row.metric)),
                value=float(row.value),
                unit="" if pd.isna(row.unit) else str(row.unit),
                start_at=timestamp,
                end_at=timestamp + timedelta(seconds=1),
                source_name=source_name,
                source_version="sheet-v1",
                device="",
            )
        )
    return records


def fetch_google_sheet(url: str, timeout: int = 30) -> tuple[bytes, str]:
    """Download a Google Sheet as XLSX. Only docs.google.com links are accepted."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname != "docs.google.com":
        raise ValueError("Paste a https://docs.google.com/spreadsheets/… link")
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", parsed.path)
    if not match:
        raise ValueError("That does not look like a Google Sheets link")
    sheet_id = match.group(1)
    query = parse_qs(parsed.query)
    fragment = parse_qs(parsed.fragment)
    gid = query.get("gid", fragment.get("gid", ["0"]))[0]
    export_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
        f"?format=xlsx&gid={gid}"
    )
    response = requests.get(export_url, timeout=timeout)
    if response.status_code in {401, 403}:
        raise ValueError("The sheet is not viewable. Set access to “Anyone with the link”")
    response.raise_for_status()
    return response.content, f"google-sheet-{sheet_id}.xlsx"


def canonical_metric(value: str) -> str:
    readable = re.sub(r"[_-]+", " ", value.strip().lower())
    readable = re.sub(r"\s+", " ", readable)
    if readable in COMMON_METRICS:
        return COMMON_METRICS[readable]
    slug = re.sub(r"[^a-z0-9]+", "_", readable).strip("_")
    return slug or "custom_metric"


def _find_column(columns: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        if alias in columns:
            return columns[alias]
    return None


def metric_label(metric_key: str) -> str:
    if metric_key in BY_KEY:
        return BY_KEY[metric_key].label
    if metric_key == "sleep_hours":
        return "Sleep"
    if metric_key == "workout_minutes":
        return "Workout minutes"
    if metric_key == "workout_count":
        return "Workout count"
    return metric_key.replace("_", " ").title()
