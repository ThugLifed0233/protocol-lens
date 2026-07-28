from pathlib import Path

from protocol_lens.database import connect
from protocol_lens.sample import build_sample_database, ensure_sample_intervention


def test_sample_intervention_is_synthetic_and_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "sample.duckdb"
    build_sample_database(database)

    ensure_sample_intervention(database)
    ensure_sample_intervention(database)

    connection = connect(database)
    period = connection.execute(
        """
        SELECT display_name, confidence, visibility, notes
        FROM compound_periods
        """
    ).fetchall()
    review_count = connection.execute(
        "SELECT COUNT(*) FROM intervention_reviews"
    ).fetchone()
    connection.close()

    assert period == [
        (
            "L-theanine",
            "confirmed",
            "publishable",
            "Synthetic demonstration period",
        )
    ]
    assert review_count == (1,)
