"""Public-safe supplement and nootropic knowledge profiles.

This module contains descriptive research context only. It deliberately excludes
usage dates, doses, personal notes, and raw health measurements. Personal outcome
windows stay in the local intervention tables and are joined only after review.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

HISTORY_STATUSES = {
    "confirmed_profile",
    "period_confirmation_needed",
    "researched_only",
}
METRIC_FITS = {"strong", "moderate", "limited", "manual"}
METRIC_SOURCES = {"apple_health", "manual"}

_NIH_PERFORMANCE = (
    "https://ods.od.nih.gov/factsheets/"
    "ExerciseAndAthleticPerformance-HealthProfessional/"
)


def _metric(
    key: str,
    fit: str,
    source: str,
    interpretation: str,
) -> dict[str, str]:
    return {
        "key": key,
        "fit": fit,
        "source": source,
        "interpretation": interpretation,
    }


def _read(title: str, publisher: str, url: str) -> dict[str, str]:
    return {"title": title, "publisher": publisher, "url": url}


SUPPLEMENT_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "key": "creatine",
        "display_name": "Creatine",
        "aliases": ["creatine monohydrate"],
        "category": "performance",
        "history_status": "confirmed_profile",
        "expected_role": (
            "Support repeated high-intensity work and adaptation to resistance training."
        ),
        "evidence_caveat": (
            "Responses vary, endurance benefits are limited, and short-term body-mass "
            "changes can reflect water rather than tissue change."
        ),
        "metric_map": [
            _metric(
                "workout_minutes",
                "strong",
                "apple_health",
                "Useful training-exposure context, but not a direct strength measure.",
            ),
            _metric(
                "active_energy",
                "moderate",
                "apple_health",
                "Describes recorded activity around a period; wearable energy is an estimate.",
            ),
            _metric(
                "body_mass",
                "moderate",
                "apple_health",
                "Can reveal concurrent mass change without identifying its composition.",
            ),
            _metric(
                "strength_performance",
                "manual",
                "manual",
                "Loads, repetitions, and effort are needed to assess the primary performance role.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Dietary Supplements for Exercise and Athletic Performance",
                "NIH Office of Dietary Supplements",
                _NIH_PERFORMANCE,
            )
        ],
    },
    {
        "key": "whey_protein",
        "display_name": "Whey and protein supplements",
        "aliases": ["whey", "protein powder", "yeast protein"],
        "category": "nutrition",
        "history_status": "confirmed_profile",
        "expected_role": (
            "Provide a convenient way to meet protein needs that support muscle repair "
            "and adaptation."
        ),
        "evidence_caveat": (
            "Benefit depends on total dietary intake, training, and whether the supplement "
            "corrects a protein shortfall; Apple Health does not measure protein intake."
        ),
        "metric_map": [
            _metric(
                "workout_minutes",
                "moderate",
                "apple_health",
                "Provides training context for interpreting a protein-support period.",
            ),
            _metric(
                "body_mass",
                "limited",
                "apple_health",
                "Body mass alone cannot separate muscle, fat, water, or food mass.",
            ),
            _metric(
                "protein",
                "manual",
                "manual",
                "Daily protein intake is the key exposure and must come from food logging.",
            ),
            _metric(
                "strength_performance",
                "manual",
                "manual",
                "Training records are more informative than passive activity totals.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Dietary Supplements for Exercise and Athletic Performance",
                "NIH Office of Dietary Supplements",
                _NIH_PERFORMANCE,
            )
        ],
    },
    {
        "key": "l_theanine",
        "display_name": "L-theanine",
        "aliases": ["LTNN", "theanine"],
        "category": "nootropic",
        "history_status": "period_confirmation_needed",
        "expected_role": (
            "Explore relaxation, perceived stress, sleep quality, and attention, either "
            "alone or alongside caffeine."
        ),
        "evidence_caveat": (
            "Trials are generally small and heterogeneous; subjective calm and attention "
            "are not captured by Apple Health, and combined use with caffeine is a distinct exposure."
        ),
        "metric_map": [
            _metric(
                "sleep_hours",
                "moderate",
                "apple_health",
                "A useful objective context signal, but duration does not equal sleep quality.",
            ),
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "May add autonomic context but is not a validated marker of a calming effect.",
            ),
            _metric(
                "hrv_sdnn",
                "limited",
                "apple_health",
                "Exploratory context only because consumer HRV is noisy and highly confounded.",
            ),
            _metric(
                "focus",
                "manual",
                "manual",
                "Attention is a central proposed outcome and needs a repeatable task or rating.",
            ),
            _metric(
                "tension",
                "manual",
                "manual",
                "Perceived physical tension requires a consistent self-report measure.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Effects of L-Theanine on Stress-Related Symptoms and Cognitive Functions",
                "PubMed",
                "https://pubmed.ncbi.nlm.nih.gov/31623400/",
            ),
            _read(
                "L-theanine, cognition, sleep, and mood: systematic review and meta-analysis",
                "PubMed",
                "https://pubmed.ncbi.nlm.nih.gov/40314930/",
            ),
        ],
    },
    {
        "key": "magnesium",
        "display_name": "Magnesium",
        "aliases": ["magnesium glycinate"],
        "category": "recovery",
        "history_status": "period_confirmation_needed",
        "expected_role": (
            "Meet magnesium needs and support normal muscle, nerve, and energy-metabolism function."
        ),
        "evidence_caveat": (
            "Sleep or recovery effects are not assured when magnesium status is adequate, "
            "and product labels differ in elemental magnesium."
        ),
        "metric_map": [
            _metric(
                "sleep_hours",
                "moderate",
                "apple_health",
                "Can describe sleep timing and duration during a reviewed usage period.",
            ),
            _metric(
                "hrv_sdnn",
                "limited",
                "apple_health",
                "Exploratory recovery context rather than a direct magnesium outcome.",
            ),
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "Useful for context but not a stand-alone indicator of benefit.",
            ),
            _metric(
                "sleep_quality",
                "manual",
                "manual",
                "Perceived sleep quality is not available in a standard Apple export.",
            ),
            _metric(
                "muscle_tension",
                "manual",
                "manual",
                "A repeatable rating is needed to evaluate the intended personal outcome.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Magnesium: Fact Sheet for Health Professionals",
                "NIH Office of Dietary Supplements",
                "https://ods.od.nih.gov/factsheets/Magnesium-HealthProfessional/",
            )
        ],
    },
    {
        "key": "melatonin",
        "display_name": "Melatonin",
        "aliases": [],
        "category": "sleep",
        "history_status": "confirmed_profile",
        "expected_role": (
            "Provide a timing signal for the biological night and support selected sleep-timing goals."
        ),
        "evidence_caveat": (
            "Evidence depends on the sleep problem and timing; supplement content can vary, "
            "and longer sleep duration does not prove improved sleep quality."
        ),
        "metric_map": [
            _metric(
                "sleep_hours",
                "strong",
                "apple_health",
                "Directly describes recorded sleep duration during comparison windows.",
            ),
            _metric(
                "sleep_timing",
                "strong",
                "apple_health",
                "Bedtime and wake-time shifts align with melatonin's intended timing role.",
            ),
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "A contextual recovery signal, not a primary melatonin outcome.",
            ),
            _metric(
                "morning_sleepiness",
                "manual",
                "manual",
                "Next-day sleepiness requires a consistent subjective check-in.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Melatonin: What You Need To Know",
                "National Center for Complementary and Integrative Health",
                "https://www.nccih.nih.gov/health/melatonin-what-you-need-to-know",
            )
        ],
    },
    {
        "key": "ashwagandha",
        "display_name": "Ashwagandha",
        "aliases": ["KSM-66"],
        "category": "botanical",
        "history_status": "confirmed_profile",
        "expected_role": (
            "Explore perceived stress, sleep, and recovery in a structured observation period."
        ),
        "evidence_caveat": (
            "Studies use different extracts and are often small; safety concerns and "
            "interactions make product form and individual context important."
        ),
        "metric_map": [
            _metric(
                "sleep_hours",
                "moderate",
                "apple_health",
                "Provides objective sleep-duration context around a reviewed period.",
            ),
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "Exploratory autonomic context, not proof of reduced stress.",
            ),
            _metric(
                "hrv_sdnn",
                "limited",
                "apple_health",
                "Highly variable and best interpreted as supportive context only.",
            ),
            _metric(
                "stress",
                "manual",
                "manual",
                "Perceived stress is central to the expected role and needs self-report.",
            ),
            _metric(
                "recovery",
                "manual",
                "manual",
                "Training recovery requires soreness, performance, or readiness observations.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Ashwagandha: Usefulness and Safety",
                "National Center for Complementary and Integrative Health",
                "https://www.nccih.nih.gov/health/ashwagandha",
            )
        ],
    },
    {
        "key": "vegetarian_omega_3",
        "display_name": "Vegetarian omega-3",
        "aliases": ["algal omega-3", "omega-3", "EPA and DHA"],
        "category": "nutrition",
        "history_status": "confirmed_profile",
        "expected_role": (
            "Provide long-chain omega-3 fatty acids within a vegetarian diet and support "
            "general nutritional and cardiovascular goals."
        ),
        "evidence_caveat": (
            "Expected effects depend on the actual EPA and DHA content, baseline diet, "
            "and the outcome measured; Apple heart metrics are not substitutes for clinical markers."
        ),
        "metric_map": [
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "A longitudinal context signal, not a validated efficacy endpoint.",
            ),
            _metric(
                "hrv_sdnn",
                "limited",
                "apple_health",
                "Consumer HRV is too variable to establish a supplement effect by itself.",
            ),
            _metric(
                "active_energy",
                "limited",
                "apple_health",
                "Useful only for controlling changes in activity across periods.",
            ),
            _metric(
                "blood_lipids",
                "manual",
                "manual",
                "Laboratory values, if available, are more relevant than passive wearable metrics.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Omega-3 Fatty Acids: Fact Sheet for Health Professionals",
                "NIH Office of Dietary Supplements",
                "https://ods.od.nih.gov/factsheets/Omega3FattyAcids-HealthProfessional/",
            )
        ],
    },
    {
        "key": "l_arginine",
        "display_name": "L-arginine",
        "aliases": ["arginine"],
        "category": "performance",
        "history_status": "confirmed_profile",
        "expected_role": (
            "Explore nitric-oxide-related blood-flow and workout-support hypotheses."
        ),
        "evidence_caveat": (
            "Research for exercise performance is limited and conflicting, with little "
            "support for consistent benefit in healthy active adults."
        ),
        "metric_map": [
            _metric(
                "workout_minutes",
                "moderate",
                "apple_health",
                "Describes workout exposure but not muscular blood flow or performance.",
            ),
            _metric(
                "workout_heart_rate",
                "limited",
                "apple_health",
                "Heart rate is strongly affected by exercise selection, intensity, heat, and hydration.",
            ),
            _metric(
                "active_energy",
                "limited",
                "apple_health",
                "An activity estimate that cannot establish a performance effect.",
            ),
            _metric(
                "training_performance",
                "manual",
                "manual",
                "Loads, repetitions, effort, and workout density are the relevant outcomes.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Dietary Supplements for Exercise and Athletic Performance",
                "NIH Office of Dietary Supplements",
                _NIH_PERFORMANCE,
            )
        ],
    },
    {
        "key": "l_carnitine",
        "display_name": "L-carnitine",
        "aliases": ["carnitine"],
        "category": "performance",
        "history_status": "period_confirmation_needed",
        "expected_role": (
            "Explore a nutrient involved in fatty-acid transport and energy metabolism."
        ),
        "evidence_caveat": (
            "Healthy adults usually synthesize enough carnitine, and evidence for exercise, "
            "weight, or performance outcomes is inconsistent."
        ),
        "metric_map": [
            _metric(
                "active_energy",
                "limited",
                "apple_health",
                "Wearable energy expenditure is an estimate and not a metabolic efficacy test.",
            ),
            _metric(
                "body_mass",
                "limited",
                "apple_health",
                "Body-mass change is nonspecific and highly confounded.",
            ),
            _metric(
                "workout_minutes",
                "limited",
                "apple_health",
                "Useful as exposure context rather than an expected direct outcome.",
            ),
            _metric(
                "fatigue",
                "manual",
                "manual",
                "A repeatable fatigue or perceived-exertion measure is required.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Carnitine: Fact Sheet for Health Professionals",
                "NIH Office of Dietary Supplements",
                "https://ods.od.nih.gov/factsheets/Carnitine-HealthProfessional/",
            )
        ],
    },
    {
        "key": "probiotics",
        "display_name": "Probiotics",
        "aliases": ["probiotic"],
        "category": "gut_health",
        "history_status": "confirmed_profile",
        "expected_role": (
            "Explore strain- and condition-specific digestive outcomes during defined periods."
        ),
        "evidence_caveat": (
            "Effects are strain-, product-, and condition-specific; a generic probiotic label "
            "does not predict benefit, and Apple Health has no direct gut-outcome metric."
        ),
        "metric_map": [
            _metric(
                "sleep_hours",
                "limited",
                "apple_health",
                "Potential context only; it is not a direct digestive outcome.",
            ),
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "Can help identify concurrent illness or recovery changes, not probiotic efficacy.",
            ),
            _metric(
                "gut_comfort",
                "manual",
                "manual",
                "A consistent symptom score is needed for the intended outcome.",
            ),
            _metric(
                "bowel_pattern",
                "manual",
                "manual",
                "Frequency and stool form require structured manual recording.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Probiotics: Fact Sheet for Health Professionals",
                "NIH Office of Dietary Supplements",
                "https://ods.od.nih.gov/factsheets/Probiotics-HealthProfessional/",
            )
        ],
    },
    {
        "key": "fibre_psyllium",
        "display_name": "Fibre and psyllium",
        "aliases": ["psyllium", "isabgol", "fibre supplement"],
        "category": "gut_health",
        "history_status": "confirmed_profile",
        "expected_role": (
            "Support stool regularity and provide a structured soluble-fibre intervention."
        ),
        "evidence_caveat": (
            "Hydration, food intake, product composition, and gastrointestinal context are "
            "major confounders; Apple Health does not record the primary outcomes."
        ),
        "metric_map": [
            _metric(
                "body_mass",
                "limited",
                "apple_health",
                "Useful only as background context for nutrition or satiety periods.",
            ),
            _metric(
                "steps",
                "limited",
                "apple_health",
                "Activity can confound appetite and gut patterns but is not an efficacy measure.",
            ),
            _metric(
                "bowel_pattern",
                "manual",
                "manual",
                "Frequency and stool form are the most relevant repeatable outcomes.",
            ),
            _metric(
                "satiety",
                "manual",
                "manual",
                "Perceived fullness requires a consistent self-report measure.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Psyllium: Drug Information",
                "MedlinePlus, U.S. National Library of Medicine",
                "https://medlineplus.gov/druginfo/meds/a601104.html",
            )
        ],
    },
    {
        "key": "caffeine",
        "display_name": "Caffeine",
        "aliases": ["coffee"],
        "category": "nootropic",
        "history_status": "confirmed_profile",
        "expected_role": (
            "Support alertness and reduce perceived exertion while observing sleep and "
            "cardiovascular context."
        ),
        "evidence_caveat": (
            "Response and tolerance vary; timing, total intake, sleep debt, and other products "
            "can dominate the observed result."
        ),
        "metric_map": [
            _metric(
                "sleep_hours",
                "strong",
                "apple_health",
                "Directly describes the sleep-duration context around caffeine periods.",
            ),
            _metric(
                "sleep_timing",
                "strong",
                "apple_health",
                "Useful for examining whether later intake coincides with later sleep.",
            ),
            _metric(
                "resting_heart_rate",
                "moderate",
                "apple_health",
                "A relevant context signal, though many non-caffeine factors affect it.",
            ),
            _metric(
                "workout_heart_rate",
                "moderate",
                "apple_health",
                "Useful only when workout type and intensity are comparable.",
            ),
            _metric(
                "focus",
                "manual",
                "manual",
                "Alertness and focus require a rating or repeatable performance task.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Spilling the Beans: How Much Caffeine is Too Much?",
                "U.S. Food and Drug Administration",
                "https://www.fda.gov/consumers/consumer-updates/"
                "spilling-beans-how-much-caffeine-too-much",
            ),
            _read(
                "Dietary Supplements for Exercise and Athletic Performance",
                "NIH Office of Dietary Supplements",
                _NIH_PERFORMANCE,
            ),
        ],
    },
    {
        "key": "l_citrulline",
        "display_name": "L-citrulline",
        "aliases": ["citrulline"],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Research a nitric-oxide-related blood-flow and exercise-performance hypothesis."
        ),
        "evidence_caveat": (
            "Human performance trials remain few and conflicting, so a community or mechanistic "
            "signal should not be treated as an expected personal result."
        ),
        "metric_map": [
            _metric(
                "workout_minutes",
                "limited",
                "apple_health",
                "Describes exercise exposure, not performance quality.",
            ),
            _metric(
                "workout_heart_rate",
                "limited",
                "apple_health",
                "Too confounded to establish a blood-flow or performance effect.",
            ),
            _metric(
                "training_performance",
                "manual",
                "manual",
                "Comparable loads, repetitions, and effort would be needed for an experiment.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Dietary Supplements for Exercise and Athletic Performance",
                "NIH Office of Dietary Supplements",
                _NIH_PERFORMANCE,
            )
        ],
    },
    {
        "key": "curcumin",
        "display_name": "Curcumin",
        "aliases": ["turmeric extract"],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Research inflammation-, discomfort-, and recovery-related hypotheses."
        ),
        "evidence_caveat": (
            "Formulations and bioavailability differ substantially, evidence is not definitive "
            "for most promoted uses, and some enhanced-bioavailability products raise safety concerns."
        ),
        "metric_map": [
            _metric(
                "workout_minutes",
                "limited",
                "apple_health",
                "Provides training-load context, not a direct recovery outcome.",
            ),
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "An indirect context signal with no specific interpretation here.",
            ),
            _metric(
                "soreness",
                "manual",
                "manual",
                "A structured soreness or discomfort score would be required.",
            ),
            _metric(
                "training_performance",
                "manual",
                "manual",
                "Comparable sessions are needed to evaluate recovery-related hypotheses.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Turmeric: Usefulness and Safety",
                "National Center for Complementary and Integrative Health",
                "https://www.nccih.nih.gov/health/turmeric",
            )
        ],
    },
)


def supplement_catalog() -> list[dict[str, Any]]:
    """Return an independent, JSON-ready copy of every public knowledge profile."""
    return copy.deepcopy(list(SUPPLEMENT_CATALOG))


def supplement_profile(key: str) -> dict[str, Any] | None:
    """Find a public profile by canonical key, display name, or alias."""
    query = _canonical_key(key)
    if not query:
        return None

    for profile in SUPPLEMENT_CATALOG:
        candidates = [
            profile["key"],
            profile["display_name"],
            *profile.get("aliases", []),
        ]
        if query in {_canonical_key(str(candidate)) for candidate in candidates}:
            return copy.deepcopy(profile)
    return None


def public_supplement_catalog_json() -> str:
    """Serialize only the public-safe descriptive catalog."""
    return json.dumps(supplement_catalog(), indent=2, sort_keys=True)


def _canonical_key(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower())).strip("_")
