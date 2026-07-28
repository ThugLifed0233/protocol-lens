from pathlib import Path

from protocol_lens.apple_health import IntervalRecord, SignalRecord, WorkoutRecord, iter_export

FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_IN">
 <Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="Apple Watch"
  unit="count/min" creationDate="2026-07-01 08:00:00 +0530"
  startDate="2026-07-01 08:00:00 +0530" endDate="2026-07-01 08:00:00 +0530"
  value="68"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch"
  startDate="2026-06-30 23:30:00 +0530" endDate="2026-07-01 06:30:00 +0530"
  value="HKCategoryValueSleepAnalysisAsleepCore"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeTraditionalStrengthTraining"
  duration="54" durationUnit="min" sourceName="Apple Watch"
  startDate="2026-07-01 18:00:00 +0530" endDate="2026-07-01 18:54:00 +0530"
  totalEnergyBurned="321" totalEnergyBurnedUnit="kcal"/>
</HealthData>
"""


def test_streaming_export_parses_supported_shapes(tmp_path: Path) -> None:
    export = tmp_path / "export.xml"
    export.write_text(FIXTURE)
    records = list(iter_export(export))

    assert len(records) == 3
    assert isinstance(records[0], SignalRecord)
    assert records[0].metric_key == "resting_heart_rate"
    assert records[0].value == 68
    assert isinstance(records[1], IntervalRecord)
    assert records[1].kind == "sleep"
    assert isinstance(records[2], WorkoutRecord)
    assert records[2].activity_type == "TraditionalStrengthTraining"
    assert records[2].energy_kcal == 321

