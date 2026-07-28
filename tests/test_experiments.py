from datetime import date
from pathlib import Path

import pandas as pd

from protocol_lens.database import connect
from protocol_lens.experiments import (
    add_compound_period,
    analyze_compound_periods,
    import_compound_periods,
    import_intervention_profiles,
    list_intervention_profiles,
    public_snapshot,
    save_intervention_profile,
)
from protocol_lens.sample import build_sample_database
from protocol_lens.stories import save_review


def test_compound_analysis_and_public_summary(tmp_path: Path) -> None:
    database = tmp_path / "sample.duckdb"
    build_sample_database(database, days=90)
    connection = connect(database)
    save_intervention_profile(
        connection,
        display_name="Example supplement",
        category="supplement",
        visibility="publishable",
    )
    period_id = add_compound_period(
        connection,
        display_name="Example supplement",
        category="supplement",
        start_date=date(2026, 1, 20),
        end_date=date(2026, 2, 2),
        dose_note="personal dose",
        purpose="personal purpose",
        visibility="publishable",
    )
    save_review(
        connection,
        period_id=period_id,
        decision="measure_more",
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
        assert row["review_decision"] == "measure_more"


def test_public_summary_requires_confirmed_reviewed_profile_and_period(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gated.duckdb"
    build_sample_database(database, days=90)
    connection = connect(database)
    save_intervention_profile(
        connection,
        display_name="Example supplement",
        category="supplement",
        visibility="publishable",
    )
    period_id = add_compound_period(
        connection,
        display_name="Example supplement",
        category="supplement",
        start_date=date(2026, 1, 20),
        end_date=date(2026, 2, 2),
        confidence="approximate",
        visibility="publishable",
    )

    assert public_snapshot(connection)["results"] == []
    save_review(connection, period_id=period_id, decision="measure_more")
    assert public_snapshot(connection)["results"] == []

    connection.execute(
        "UPDATE compound_periods SET confidence = 'confirmed' WHERE period_id = ?",
        [period_id],
    )
    assert public_snapshot(connection)["results"]
    connection.close()

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


def test_intervention_profiles_can_be_updated_and_imported(tmp_path: Path) -> None:
    connection = connect(tmp_path / "profiles.duckdb")
    key = save_intervention_profile(
        connection,
        display_name="Example supplement",
        category="supplement",
        description="Initial description",
        expected_outcomes="Sleep; recovery",
        personal_goal="Understand recovery",
        color="#BF5AF2",
    )
    save_intervention_profile(
        connection,
        display_name="Example supplement",
        category="supplement",
        description="Updated description",
        color="#64D2FF",
    )
    imported = import_intervention_profiles(
        connection,
        pd.DataFrame(
            [
                {
                    "intervention": "Second example",
                    "category": "nootropic",
                    "description": "A second profile",
                    "confidence": "approximate",
                }
            ]
        ),
    )
    profiles = list_intervention_profiles(connection)
    connection.close()

    assert key == "example_supplement"
    assert imported == 1
    assert len(profiles) == 2
    first = profiles.loc[profiles["intervention_key"] == key].iloc[0]
    assert first["description"] == "Updated description"
    assert first["color"] == "#64D2FF"
