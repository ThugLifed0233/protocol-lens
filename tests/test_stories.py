from datetime import date
from pathlib import Path

from protocol_lens.database import connect
from protocol_lens.experiments import add_compound_period, save_intervention_profile
from protocol_lens.stories import (
    intervention_story,
    review_queue,
    save_expectation,
    save_reference,
    save_review,
)


def test_intervention_story_preserves_experiment_loop(tmp_path: Path) -> None:
    connection = connect(tmp_path / "stories.duckdb")
    key = save_intervention_profile(
        connection,
        display_name="Example supplement",
        category="supplement",
        description="Example profile",
        expected_outcomes="Recovery",
        personal_goal="Observe recovery",
        visibility="publishable",
    )
    period_id = add_compound_period(
        connection,
        display_name="Example supplement",
        category="supplement",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 14),
        visibility="publishable",
    )
    save_expectation(
        connection,
        intervention_key=key,
        metric_key="sleep_hours",
        expected_direction="higher",
        rationale="Expected sleep support",
    )
    save_reference(
        connection,
        intervention_key=key,
        title="Example source",
        publisher="Example publisher",
        url="https://example.com/source",
    )
    save_review(
        connection,
        period_id=period_id,
        decision="measure_more",
        observed_summary="No conclusion yet",
        confounders="Short period",
    )

    story = intervention_story(connection, key)
    queue = review_queue(connection)
    connection.close()

    assert story["profile"]["display_name"] == "Example supplement"
    assert story["expectations"][0]["metric_key"] == "sleep_hours"
    assert story["references"][0]["url"] == "https://example.com/source"
    assert story["reviews"][0]["decision"] == "measure_more"
    assert queue.empty
