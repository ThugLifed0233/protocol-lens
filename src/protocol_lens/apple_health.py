"""Streaming reader for the subset of Apple Health used by Protocol Lens."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree
from zipfile import ZipFile

from .catalog import BY_APPLE_TYPE, SLEEP_TYPE

APPLE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


def parse_apple_date(value: str) -> datetime:
    # APPLE_DATE_FORMAT includes %z; Ruff cannot infer that through the constant.
    return datetime.strptime(value, APPLE_DATE_FORMAT)  # noqa: DTZ007


@dataclass(frozen=True)
class SignalRecord:
    metric_key: str
    value: float
    unit: str
    start_at: datetime
    end_at: datetime
    source_name: str
    source_version: str
    device: str


@dataclass(frozen=True)
class IntervalRecord:
    kind: str
    value: str
    start_at: datetime
    end_at: datetime
    source_name: str


@dataclass(frozen=True)
class WorkoutRecord:
    activity_type: str
    start_at: datetime
    end_at: datetime
    duration_minutes: float
    energy_kcal: float | None
    distance_km: float | None
    source_name: str
    device: str


@contextmanager
def open_export(path: Path) -> Iterator[BinaryIO]:
    """Open export.xml from either a raw XML file or an Apple Health ZIP."""
    if path.suffix.lower() == ".zip":
        with ZipFile(path) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if name == "export.xml" or name.endswith("/export.xml")
            ]
            if not candidates:
                raise ValueError("The ZIP does not contain Apple Health export.xml")
            with archive.open(candidates[0]) as stream:
                yield stream
    else:
        with path.open("rb") as stream:
            yield stream


def iter_export(path: Path) -> Iterator[SignalRecord | IntervalRecord | WorkoutRecord]:
    """Yield normalized records while clearing XML elements to keep memory bounded."""
    with open_export(path) as stream:
        for _, element in ElementTree.iterparse(stream, events=("end",)):
            attributes = element.attrib
            if element.tag == "Record":
                apple_type = attributes.get("type", "")
                if apple_type in BY_APPLE_TYPE:
                    metric = BY_APPLE_TYPE[apple_type]
                    try:
                        yield SignalRecord(
                            metric_key=metric.key,
                            value=float(attributes["value"]),
                            unit=attributes.get("unit", ""),
                            start_at=parse_apple_date(attributes["startDate"]),
                            end_at=parse_apple_date(attributes["endDate"]),
                            source_name=attributes.get("sourceName", ""),
                            source_version=attributes.get("sourceVersion", ""),
                            device=attributes.get("device", ""),
                        )
                    except (KeyError, ValueError):
                        pass
                elif apple_type == SLEEP_TYPE:
                    try:
                        yield IntervalRecord(
                            kind="sleep",
                            value=attributes.get("value", ""),
                            start_at=parse_apple_date(attributes["startDate"]),
                            end_at=parse_apple_date(attributes["endDate"]),
                            source_name=attributes.get("sourceName", ""),
                        )
                    except (KeyError, ValueError):
                        pass
            elif element.tag == "Workout":
                try:
                    yield WorkoutRecord(
                        activity_type=attributes.get(
                            "workoutActivityType", "HKWorkoutActivityTypeOther"
                        ).removeprefix("HKWorkoutActivityType"),
                        start_at=parse_apple_date(attributes["startDate"]),
                        end_at=parse_apple_date(attributes["endDate"]),
                        duration_minutes=float(attributes.get("duration", 0)),
                        energy_kcal=_optional_float(attributes.get("totalEnergyBurned")),
                        distance_km=_distance_km(
                            attributes.get("totalDistance"),
                            attributes.get("totalDistanceUnit", ""),
                        ),
                        source_name=attributes.get("sourceName", ""),
                        device=attributes.get("device", ""),
                    )
                except (KeyError, ValueError):
                    pass
            element.clear()


def _optional_float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _distance_km(value: str | None, unit: str) -> float | None:
    distance = _optional_float(value)
    if distance is None:
        return None
    if unit == "mi":
        return distance * 1.609344
    if unit == "m":
        return distance / 1000
    return distance
