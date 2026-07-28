from datetime import date
from pathlib import Path

import pandas as pd

from protocol_lens.database import connect
from protocol_lens.experiments import (
    add_compound_period,
    analyze_compound_periods,
    import_compound_periods,
    public_snapshot,
)
from protocol_lens.sample import build_sample_database


def test_compound_analysis_and_public_summary(tmp_path: Path) -> None:
    database = tmp_path / "sample.duckdb"
    build_sample_database(database, days=90)
    connection = connect(database)
    add_compound_period(
        connection,
        display_name="Example supplement",
        category="supplement",
        start_date=date(2026, 1, 20),
        end_date=date(2026, 2, 2),
        dose_note="personal dose",
        purpose="personal purpose",
        visibility="publishable",
    )

    analysis = analyze_compound_periods(connection)
    snapshot = public_snapshot(connection)
    connection.close()

    assert not analysis.empty
    assert set(analysis["compound"]) == {"Example supplement"}
    assert snapshot["results"]
    assert {row["intervention"] for row in snapshot["results"]} == {"Example supplement"}
    assert snapshot["sharing"]["contains_raw_health_data"] is False
    for row in snapshot["results"]:
        assert "start_date" not in row
        assert "end_date" not in row
        assert "dose_note" not in row
        assert "baseline_mean" not in row
        assert "during_mean" not in row
def test_bulk_intervention_history_defaults_to_personal(tmp_path: Path) -> None:
    connection = connect(tmp_path / "history.duckdb")
    frame = pd.DataFrame(
        [
            {
                "intervention": "L-theanine",
                "category": "nootropic",
                "start_date": "2026-01-10",
                "end_date": "2026-01-20",
                "confidence": "approximate",
            }
        ]
    )
    imported = import_compound_periods(connection, frame)
    period = connection.execute(
        "SELECT display_name, visibility, confidence FROM compound_periods"
    ).fetchone()
    connection.close()

    assert imported == 1
    assert period == ("L-theanine", "personal_only", "approximate")
