"""AP3 APOC provenance helpers — sidecar only, no identity-hash change."""

from __future__ import annotations

import pytest

from thesistester.levels.apoc_tick import (
    APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
    APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
)
from thesistester.study.apoc_provenance import (
    APOC_OBJECT_LEGACY_TYPICAL,
    APOC_OBJECT_TICK_LAST_VOLUME,
    RECORDED_EXPLICIT,
    RECORDED_INFERRED,
    WAVE7_HISTORICAL_PROVENANCE,
    apoc_provenance_from_levels,
    is_wave7_study_file,
    read_apoc_provenance,
    should_write_apoc_provenance,
)


def test_wave7_file_stems():
    assert is_wave7_study_file("progB_w7_apoc_ma.yaml")
    assert is_wave7_study_file("progB_w7_apoc_rvwap.yaml")
    assert is_wave7_study_file("progB_w7_apoc_pivot.yaml")
    assert is_wave7_study_file("examples/studies/program_b/progB_w7_apoc_ma.yaml")
    assert not is_wave7_study_file("progB_w0_solo.yaml")
    assert not is_wave7_study_file("progB_w6_sp_ma.yaml")
    assert not is_wave7_study_file("progB_w8_prev30m_ma.yaml")
    assert not is_wave7_study_file("progB_w4_profile_ma.yaml")
    assert not is_wave7_study_file("notes_about_w7_apoc.yaml")
    assert not is_wave7_study_file("progB_w7_apoc_ma.yaml.bak")


def test_implicit_typical_is_inferred_legacy():
    provenance = apoc_provenance_from_levels({"apoc_enabled": True})
    assert provenance["apoc_profile_source"] == APOC_PROFILE_SOURCE_TYPICAL_MVP_V1
    assert provenance["apoc_algorithm_version"] == APOC_PROFILE_SOURCE_TYPICAL_MVP_V1
    assert provenance["apoc_object"] == APOC_OBJECT_LEGACY_TYPICAL
    assert provenance["recorded"] == RECORDED_INFERRED


def test_explicit_tick_source_is_recorded():
    provenance = apoc_provenance_from_levels(
        {"apoc_profile_source": APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1}
    )
    assert provenance["apoc_profile_source"] == APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1
    assert provenance["apoc_algorithm_version"] == APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1
    assert provenance["apoc_object"] == APOC_OBJECT_TICK_LAST_VOLUME
    assert provenance["recorded"] == RECORDED_EXPLICIT


def test_explicit_typical_is_recorded_not_inferred():
    provenance = apoc_provenance_from_levels(
        {"apoc_profile_source": APOC_PROFILE_SOURCE_TYPICAL_MVP_V1}
    )
    assert provenance["apoc_object"] == APOC_OBJECT_LEGACY_TYPICAL
    assert provenance["recorded"] == RECORDED_EXPLICIT


def test_write_gate_keeps_golden_expansion_byte_stable():
    assert should_write_apoc_provenance({}) is False
    assert should_write_apoc_provenance({"sma_lengths": [50]}) is False
    assert should_write_apoc_provenance({"apoc_enabled": True}) is True
    assert (
        should_write_apoc_provenance(
            {"apoc_profile_source": APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1}
        )
        is True
    )


def test_write_gate_skips_explicit_apoc_disabled():
    assert should_write_apoc_provenance({"apoc_enabled": False}) is False
    assert (
        should_write_apoc_provenance(
            {
                "apoc_enabled": False,
                "apoc_profile_source": APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
            }
        )
        is False
    )


def test_missing_sidecar_reads_as_inferred_typical():
    provenance = read_apoc_provenance({"run_count": 1})
    assert provenance["apoc_object"] == APOC_OBJECT_LEGACY_TYPICAL
    assert provenance["recorded"] == RECORDED_INFERRED
    assert WAVE7_HISTORICAL_PROVENANCE["apoc_object"] == APOC_OBJECT_LEGACY_TYPICAL
    assert WAVE7_HISTORICAL_PROVENANCE["recorded"] == "inferred_historical"


def test_read_derives_object_from_source_when_object_omitted():
    provenance = read_apoc_provenance(
        {
            "apoc_provenance": {
                "apoc_profile_source": APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
                "recorded": RECORDED_EXPLICIT,
            }
        }
    )
    assert provenance["apoc_object"] == APOC_OBJECT_TICK_LAST_VOLUME
    assert provenance["apoc_algorithm_version"] == APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1
    assert provenance["recorded"] == RECORDED_EXPLICIT


def test_read_rejects_non_mapping_sidecar():
    with pytest.raises(ValueError, match="must be a mapping"):
        read_apoc_provenance({"apoc_provenance": "tick_last_volume_v1"})


def test_read_rejects_source_object_contradiction():
    with pytest.raises(ValueError, match="does not match"):
        read_apoc_provenance(
            {
                "apoc_provenance": {
                    "apoc_profile_source": APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
                    "apoc_object": APOC_OBJECT_LEGACY_TYPICAL,
                    "recorded": RECORDED_EXPLICIT,
                }
            }
        )


def test_read_rejects_unknown_recorded_token():
    with pytest.raises(ValueError, match="recorded"):
        read_apoc_provenance(
            {
                "apoc_provenance": {
                    "apoc_profile_source": APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
                    "recorded": "maybe",
                }
            }
        )
