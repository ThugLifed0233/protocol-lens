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
_NIH_CHOLINE = "https://ods.od.nih.gov/factsheets/Choline-HealthProfessional/"
_NIH_MAGNESIUM = "https://ods.od.nih.gov/factsheets/Magnesium-HealthProfessional/"
_NIH_MVMS = "https://ods.od.nih.gov/factsheets/MVMS-HealthProfessional/"


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


def _cognitive_research_metrics(
    primary_key: str,
    primary_interpretation: str,
) -> list[dict[str, str]]:
    return [
        _metric(
            "sleep_hours",
            "limited",
            "apple_health",
            "Provides essential cognitive-performance context, not a compound outcome.",
        ),
        _metric(
            "resting_heart_rate",
            "limited",
            "apple_health",
            "A general tolerability and context signal rather than evidence of cognitive benefit.",
        ),
        _metric(
            primary_key,
            "manual",
            "manual",
            primary_interpretation,
        ),
    ]


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
        "key": "multinutrient_support",
        "display_name": "Multinutrient and B-vitamin support",
        "aliases": [
            "calcium and vitamin D",
            "vitamin B12",
            "B12",
            "B-complex",
            "zinc",
            "Calverich XT",
            "Bicozinc",
        ],
        "category": "nutrition",
        "history_status": "period_confirmation_needed",
        "expected_role": (
            "Document several nutrient-support products used to provide calcium, vitamin D, "
            "B vitamins, or zinc when those nutrients were of interest."
        ),
        "evidence_caveat": (
            "This profile groups distinct products rather than one continuous intervention. "
            "Labels, overlapping ingredients, nutritional need, and usage periods must be "
            "confirmed before any outcome comparison."
        ),
        "metric_map": [
            _metric(
                "sleep_hours",
                "limited",
                "apple_health",
                "Provides general recovery context but is not a marker of nutrient status.",
            ),
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "Can describe the surrounding period but cannot establish a nutrient effect.",
            ),
            _metric(
                "nutrient_intake",
                "manual",
                "manual",
                "Diet and every overlapping product are needed to estimate total nutrient intake.",
            ),
            _metric(
                "laboratory_status",
                "manual",
                "manual",
                "Relevant laboratory measurements are more informative than passive wearable data.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Multivitamin/mineral Supplements: Fact Sheet for Health Professionals",
                "NIH Office of Dietary Supplements",
                _NIH_MVMS,
            ),
            _read(
                "Vitamin B12: Fact Sheet for Health Professionals",
                "NIH Office of Dietary Supplements",
                "https://ods.od.nih.gov/factsheets/VitaminB12-HealthProfessional/",
            ),
        ],
    },
    {
        "key": "electrolyte_rehydration",
        "display_name": "Electrolytes and oral rehydration",
        "aliases": ["ORS", "Electral", "Fast&Up", "electrolyte tablets"],
        "category": "hydration",
        "history_status": "period_confirmation_needed",
        "expected_role": (
            "Support short-term rehydration by replacing fluid and electrolytes during "
            "relevant illness, heat, or exercise contexts."
        ),
        "evidence_caveat": (
            "Oral rehydration solution and sports electrolyte products are not equivalent. "
            "The exact product, reason for use, and surrounding hydration or illness period "
            "must be confirmed before interpreting Apple data."
        ),
        "metric_map": [
            _metric(
                "resting_heart_rate",
                "moderate",
                "apple_health",
                "Can provide rehydration and illness context but is affected by many other factors.",
            ),
            _metric(
                "workout_heart_rate",
                "limited",
                "apple_health",
                "Useful only when heat, workout type, intensity, and duration are comparable.",
            ),
            _metric(
                "body_mass",
                "limited",
                "apple_health",
                "Short-term change may reflect fluid shifts, but sparse measurements limit use.",
            ),
            _metric(
                "hydration_symptoms",
                "manual",
                "manual",
                "Thirst, dizziness, gastrointestinal loss, and fluid intake require manual context.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Oral Rehydration Salts",
                "World Health Organization and UNICEF",
                "https://www.who.int/publications/i/item/WHO-FCH-CAH-06.1",
            ),
            _read(
                "Dietary Supplements for Exercise and Athletic Performance",
                "NIH Office of Dietary Supplements",
                _NIH_PERFORMANCE,
            ),
        ],
    },
    {
        "key": "stress_support_blend",
        "display_name": "Low-dose stress-support blend",
        "aliases": ["Happy Cultures Stress Who", "Stress Who"],
        "category": "multi_ingredient",
        "history_status": "period_confirmation_needed",
        "expected_role": (
            "Explore perceived relaxation, sleep, and digestive context from a low-dose "
            "multi-ingredient stress-support product."
        ),
        "evidence_caveat": (
            "A multi-ingredient blend cannot show which ingredient contributed to a result. "
            "The product label, usage period, and subjective outcomes still need confirmation, "
            "and ingredient-level evidence does not establish a product-level effect."
        ),
        "metric_map": [
            _metric(
                "sleep_hours",
                "moderate",
                "apple_health",
                "Can describe sleep duration during a confirmed product period.",
            ),
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "Exploratory autonomic context only, not a validated relaxation outcome.",
            ),
            _metric(
                "hrv_sdnn",
                "limited",
                "apple_health",
                "Highly variable and not interpretable without comparable sleep and activity.",
            ),
            _metric(
                "stress",
                "manual",
                "manual",
                "The intended personal outcome needs a consistent subjective rating.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Ashwagandha: Usefulness and Safety",
                "National Center for Complementary and Integrative Health",
                "https://www.nccih.nih.gov/health/ashwagandha",
            ),
            _read(
                "Magnesium: Fact Sheet for Health Professionals",
                "NIH Office of Dietary Supplements",
                _NIH_MAGNESIUM,
            ),
        ],
    },
    {
        "key": "digestive_gas_blend",
        "display_name": "Occasional digestive and gas blend",
        "aliases": ["Happy Cultures Q-Gazz", "Q-Gazz"],
        "category": "gut_health",
        "history_status": "period_confirmation_needed",
        "expected_role": (
            "Explore short-term relief of gas, pressure, fullness, or bloating from an "
            "occasional multi-ingredient digestive product."
        ),
        "evidence_caveat": (
            "The exact formulation and usage events need confirmation. Evidence for one "
            "component cannot be generalized to the full blend, and Apple Health does not "
            "measure the primary digestive outcomes."
        ),
        "metric_map": [
            _metric(
                "resting_heart_rate",
                "limited",
                "apple_health",
                "May add illness or discomfort context but is not a digestive efficacy measure.",
            ),
            _metric(
                "sleep_hours",
                "limited",
                "apple_health",
                "Provides contextual recovery information only.",
            ),
            _metric(
                "gut_comfort",
                "manual",
                "manual",
                "Gas, pressure, and bloating require a consistent symptom rating.",
            ),
            _metric(
                "use_event",
                "manual",
                "manual",
                "Occasional use needs an event timestamp to support a short-window comparison.",
            ),
        ],
        "go_to_reads": [
            _read(
                "Simethicone: Drug Information",
                "MedlinePlus, U.S. National Library of Medicine",
                "https://medlineplus.gov/druginfo/meds/a682683.html",
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
        "key": "saffron",
        "display_name": "Standardized saffron extract",
        "aliases": ["saffron extract"],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Research mood, perceived stress, sleep, and attention hypotheses for a "
            "standardized saffron extract."
        ),
        "evidence_caveat": (
            "Small trials use specific extracts and populations, with mixed endpoints. "
            "Those findings do not establish a general cognitive or mood effect and do not "
            "represent personal use."
        ),
        "metric_map": _cognitive_research_metrics(
            "mood_and_attention",
            "Mood and attention require validated questionnaires or repeatable tasks.",
        ),
        "go_to_reads": [
            _read(
                "Effects of Saffron Extract Supplementation on Mood and Well-Being",
                "PubMed, U.S. National Library of Medicine",
                "https://pubmed.ncbi.nlm.nih.gov/33598475/",
            )
        ],
    },
    {
        "key": "bacopa",
        "display_name": "Bacopa monnieri",
        "aliases": ["Bacopa", "Brahmi"],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Research longer-horizon memory, attention, perceived stress, and fatigue hypotheses."
        ),
        "evidence_caveat": (
            "Extracts, populations, and trial outcomes vary. A recent controlled trial did "
            "not improve its primary cognitive outcomes, and this profile does not represent "
            "personal use."
        ),
        "metric_map": _cognitive_research_metrics(
            "memory_and_attention",
            "Memory and attention need validated, repeated tasks over a suitable study period.",
        ),
        "go_to_reads": [
            _read(
                "Effects of a Bacopa monnieri Extract on Cognition, Stress, and Fatigue",
                "PubMed, U.S. National Library of Medicine",
                "https://pubmed.ncbi.nlm.nih.gov/41091332/",
            )
        ],
    },
    {
        "key": "citicoline",
        "display_name": "Citicoline",
        "aliases": ["CDP-choline"],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Research choline-related attention and memory hypotheses using a defined product."
        ),
        "evidence_caveat": (
            "Human trials are limited and often study selected older or impaired populations. "
            "General choline biology does not establish a citicoline nootropic effect, and "
            "this profile does not represent personal use."
        ),
        "metric_map": _cognitive_research_metrics(
            "memory_and_attention",
            "Comparable memory and attention tasks are needed; Apple Health cannot measure them.",
        ),
        "go_to_reads": [
            _read(
                "Choline: Fact Sheet for Health Professionals",
                "NIH Office of Dietary Supplements",
                _NIH_CHOLINE,
            ),
            _read(
                "Citicoline and Memory Function in Healthy Older Adults",
                "PubMed, U.S. National Library of Medicine",
                "https://pubmed.ncbi.nlm.nih.gov/33978188/",
            ),
        ],
    },
    {
        "key": "phosphatidylserine",
        "display_name": "Phosphatidylserine",
        "aliases": ["PS"],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Research memory, attention, and perceived-stress hypotheses for a defined formulation."
        ),
        "evidence_caveat": (
            "Trials are limited, often involve older adults with memory complaints, and do "
            "not establish benefit in healthy younger users. This profile does not represent "
            "personal use."
        ),
        "metric_map": _cognitive_research_metrics(
            "memory_and_attention",
            "A validated repeated cognitive task is required for the proposed outcome.",
        ),
        "go_to_reads": [
            _read(
                "Soybean-Derived Phosphatidylserine and Memory Function",
                "PubMed, U.S. National Library of Medicine",
                "https://pubmed.ncbi.nlm.nih.gov/21103034/",
            )
        ],
    },
    {
        "key": "l_tyrosine",
        "display_name": "L-tyrosine",
        "aliases": ["tyrosine"],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Research whether tyrosine supports attention during acute, demanding stressors "
            "such as extended wakefulness."
        ),
        "evidence_caveat": (
            "Any signal appears context-specific, and older sleep-deprivation studies do not "
            "justify routine cognitive-enhancement claims. This profile does not represent "
            "personal use."
        ),
        "metric_map": _cognitive_research_metrics(
            "attention_under_stress",
            "A repeatable attention task and a predefined stress context are required.",
        ),
        "go_to_reads": [
            _read(
                "The Effects of Tyrosine on Cognitive Performance During Extended Wakefulness",
                "PubMed, U.S. National Library of Medicine",
                "https://pubmed.ncbi.nlm.nih.gov/7794222/",
            )
        ],
    },
    {
        "key": "piracetam",
        "display_name": "Piracetam",
        "aliases": [],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Document a researched memory and cognition hypothesis without presenting it as "
            "a supplement protocol or personal exposure."
        ),
        "evidence_caveat": (
            "Evidence for memory benefit is inconclusive, regulatory status differs by country, "
            "and the U.S. FDA has challenged its marketing as a dietary supplement. This profile "
            "does not represent personal use."
        ),
        "metric_map": _cognitive_research_metrics(
            "memory",
            "A validated repeated memory task would be required for any structured evaluation.",
        ),
        "go_to_reads": [
            _read(
                "Cognitive Effects of Piracetam in Adults With Memory Impairment",
                "PubMed, U.S. National Library of Medicine",
                "https://pubmed.ncbi.nlm.nih.gov/38878641/",
            ),
            _read(
                "Peak Nootropics Warning Letter",
                "U.S. Food and Drug Administration",
                "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/"
                "warning-letters/peak-nootropics-llc-aka-advanced-nootropics-557887-02052019",
            ),
        ],
    },
    {
        "key": "alpha_gpc",
        "display_name": "Alpha-GPC",
        "aliases": ["alpha glycerylphosphorylcholine", "choline alfoscerate"],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Research choline-related cognition or motivation hypotheses using a defined product."
        ),
        "evidence_caveat": (
            "General choline physiology is not evidence of a nootropic effect. Relevant human "
            "studies are small or use selected clinical populations, and this profile does not "
            "represent personal use."
        ),
        "metric_map": _cognitive_research_metrics(
            "cognition_and_motivation",
            "Validated cognitive tasks and a consistent motivation rating are required.",
        ),
        "go_to_reads": [
            _read(
                "Choline: Fact Sheet for Health Professionals",
                "NIH Office of Dietary Supplements",
                _NIH_CHOLINE,
            ),
            _read(
                "Alpha-Glycerylphosphorylcholine and Motivation in Healthy Volunteers",
                "PubMed, U.S. National Library of Medicine",
                "https://pubmed.ncbi.nlm.nih.gov/34207484/",
            ),
        ],
    },
    {
        "key": "rhodiola",
        "display_name": "Rhodiola rosea",
        "aliases": ["Rhodiola", "golden root"],
        "category": "research_candidate",
        "history_status": "researched_only",
        "expected_role": (
            "Research fatigue, stress, mood, and performance hypotheses for a standardized extract."
        ),
        "evidence_caveat": (
            "NCCIH concludes that reliable evidence is insufficient for any health-related "
            "purpose, and products vary. This profile does not represent personal use."
        ),
        "metric_map": _cognitive_research_metrics(
            "fatigue_and_stress",
            "Fatigue and stress require predefined, repeatable subjective measures.",
        ),
        "go_to_reads": [
            _read(
                "Rhodiola: Usefulness and Safety",
                "National Center for Complementary and Integrative Health",
                "https://www.nccih.nih.gov/health/rhodiola",
            )
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
