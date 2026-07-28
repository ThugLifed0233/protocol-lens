import json

from protocol_lens.supplement_catalog import (
    HISTORY_STATUSES,
    METRIC_FITS,
    METRIC_SOURCES,
    public_supplement_catalog_json,
    supplement_catalog,
    supplement_profile,
)

EXPECTED_KEYS = {
    "creatine",
    "whey_protein",
    "l_theanine",
    "magnesium",
    "melatonin",
    "ashwagandha",
    "vegetarian_omega_3",
    "l_arginine",
    "l_carnitine",
    "probiotics",
    "fibre_psyllium",
    "multinutrient_support",
    "electrolyte_rehydration",
    "stress_support_blend",
    "digestive_gas_blend",
    "caffeine",
    "saffron",
    "bacopa",
    "citicoline",
    "phosphatidylserine",
    "l_tyrosine",
    "piracetam",
    "alpha_gpc",
    "rhodiola",
    "l_citrulline",
    "curcumin",
}

RESEARCHED_ONLY_KEYS = {
    "saffron",
    "bacopa",
    "citicoline",
    "phosphatidylserine",
    "l_tyrosine",
    "piracetam",
    "alpha_gpc",
    "rhodiola",
    "l_citrulline",
    "curcumin",
}

PERIOD_CONFIRMATION_KEYS = {
    "multinutrient_support",
    "electrolyte_rehydration",
    "stress_support_blend",
    "digestive_gas_blend",
}


def test_catalog_has_complete_public_profiles() -> None:
    catalog = supplement_catalog()

    assert {profile["key"] for profile in catalog} == EXPECTED_KEYS
    assert len(catalog) == len(EXPECTED_KEYS)

    for profile in catalog:
        assert profile["display_name"]
        assert profile["category"]
        assert profile["history_status"] in HISTORY_STATUSES
        assert profile["expected_role"]
        assert profile["evidence_caveat"]
        assert profile["metric_map"]
        assert profile["go_to_reads"]

        for metric in profile["metric_map"]:
            assert metric["key"]
            assert metric["fit"] in METRIC_FITS
            assert metric["source"] in METRIC_SOURCES
            assert metric["interpretation"]
            if metric["fit"] == "manual":
                assert metric["source"] == "manual"

        for reference in profile["go_to_reads"]:
            assert reference["title"]
            assert reference["publisher"]
            assert reference["url"].startswith("https://")


def test_researched_profiles_are_not_presented_as_personal_use() -> None:
    for key in RESEARCHED_ONLY_KEYS:
        assert supplement_profile(key)["history_status"] == "researched_only"

    assert supplement_profile("creatine")["history_status"] == "confirmed_profile"


def test_grouped_history_requires_period_confirmation() -> None:
    for key in PERIOD_CONFIRMATION_KEYS:
        profile = supplement_profile(key)
        assert profile["history_status"] == "period_confirmation_needed"
        assert any(metric["source"] == "apple_health" for metric in profile["metric_map"])
        assert any(metric["source"] == "manual" for metric in profile["metric_map"])


def test_new_profiles_support_conservative_alias_lookup() -> None:
    assert supplement_profile("ORS")["key"] == "electrolyte_rehydration"
    assert supplement_profile("Brahmi")["key"] == "bacopa"
    assert supplement_profile("CDP-choline")["key"] == "citicoline"
    assert supplement_profile("alpha glycerylphosphorylcholine")["key"] == "alpha_gpc"


def test_profile_lookup_supports_names_and_aliases_without_sharing_mutable_state() -> None:
    by_key = supplement_profile("l_theanine")
    by_name = supplement_profile("L-theanine")
    by_alias = supplement_profile("LTNN")

    assert by_key == by_name == by_alias
    assert supplement_profile("not in the catalog") is None

    by_key["aliases"].append("changed by caller")
    assert "changed by caller" not in supplement_profile("l_theanine")["aliases"]


def test_public_json_contains_results_context_not_personal_records() -> None:
    encoded = public_supplement_catalog_json()
    decoded = json.loads(encoded)

    assert decoded == supplement_catalog()
    assert '"start_date"' not in encoded
    assert '"end_date"' not in encoded
    assert '"dose"' not in encoded
    assert '"personal_note"' not in encoded
    assert '"raw_value"' not in encoded
