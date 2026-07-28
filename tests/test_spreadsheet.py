from io import BytesIO
from pathlib import Path

import pandas as pd

from protocol_lens.analysis import daily_metrics
from protocol_lens.database import connect, ingest_records
from protocol_lens.spreadsheet import canonical_metric, read_spreadsheet, spreadsheet_records


def test_long_sheet_is_normalized() -> None:
    content = b"date,metric,value,unit\n2026-07-01,weight,101,kg\n"
    frame = read_spreadsheet(content, "health.csv")
    records = spreadsheet_records(frame, "health.csv")

    assert len(records) == 1
    assert records[0].metric_key == "body_mass"
    assert records[0].value == 101
    assert records[0].unit == "kg"


def test_wide_sheet_is_melted() -> None:
    original = pd.DataFrame(
        {
            "Date": ["2026-07-01", "2026-07-02"],
            "Protein": [130, 145],
            "Focus": [7, 8],
        }
    )
    output = BytesIO()
    original.to_excel(output, index=False)
    frame = read_spreadsheet(output.getvalue(), "health.xlsx")
    records = spreadsheet_records(frame, "health.xlsx")

    assert len(records) == 4
    assert {record.metric_key for record in records} == {"protein", "focus"}


def test_metric_names_are_canonical() -> None:
    assert canonical_metric("Resting HR") == "resting_heart_rate"
    assert canonical_metric("My Custom Score") == "my_custom_score"


def test_custom_sheet_metric_is_available_for_exploration(tmp_path: Path) -> None:
    content = b"date,metric,value,unit\n2026-07-01,focus,7,score\n2026-07-02,focus,8,score\n"
    source = tmp_path / "focus.csv"
    source.write_bytes(content)
    records = spreadsheet_records(read_spreadsheet(content, source.name), source.name)
    connection = connect(tmp_path / "health.duckdb")
    ingest_records(connection, records, source, "test")

    frame = daily_metrics(connection)
    connection.close()

    assert list(frame["focus"]) == [7, 8]
