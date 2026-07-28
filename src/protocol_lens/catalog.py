"""Canonical Apple Health metric definitions used by the first release."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    apple_type: str
    key: str
    label: str
    aggregation: str
    color: str


METRICS = (
    Metric(
        "HKQuantityTypeIdentifierRestingHeartRate",
        "resting_heart_rate",
        "Resting heart rate",
        "mean",
        "#ff453a",
    ),
    Metric(
        "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
        "hrv_sdnn",
        "Heart-rate variability",
        "mean",
        "#bf5af2",
    ),
    Metric(
        "HKQuantityTypeIdentifierWalkingHeartRateAverage",
        "walking_heart_rate",
        "Walking heart rate",
        "mean",
        "#ff9f0a",
    ),
    Metric(
        "HKQuantityTypeIdentifierStepCount",
        "steps",
        "Steps",
        "sum",
        "#32d74b",
    ),
    Metric(
        "HKQuantityTypeIdentifierActiveEnergyBurned",
        "active_energy",
        "Active energy",
        "sum",
        "#ff375f",
    ),
    Metric(
        "HKQuantityTypeIdentifierDistanceWalkingRunning",
        "walking_running_distance",
        "Walking + running distance",
        "sum",
        "#64d2ff",
    ),
    Metric(
        "HKQuantityTypeIdentifierBodyMass",
        "body_mass",
        "Body mass",
        "mean",
        "#0a84ff",
    ),
    Metric(
        "HKQuantityTypeIdentifierVO2Max",
        "vo2_max",
        "Cardio fitness",
        "mean",
        "#30d158",
    ),
)

BY_APPLE_TYPE = {metric.apple_type: metric for metric in METRICS}
BY_KEY = {metric.key: metric for metric in METRICS}

SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
ASLEEP_VALUES = {
    "HKCategoryValueSleepAnalysisAsleep",
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
    "Asleep",
    "AsleepCore",
    "AsleepDeep",
    "AsleepREM",
}

