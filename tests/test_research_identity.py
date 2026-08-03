"""CAI-1 — shared levels normalization and research identity contracts."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from thesistester.api import compute_levels, run_experiment
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.persistence.local_store import (
    LEVEL_ENGINE_VERSION,
    compute_dataset_id,
    compute_levels_settings_hash,
)
from thesistester.research_bundle import (
    apply_research_bundle_to_session,
    build_research_bundle,
    canonical_bundle_hash,
    load_research_bundle,
)
from thesistester.research_identity import (
    LEVELS_ARTIFACT_SCHEMA_VERSION,
    DataIdentity,
    ExperimentIdentity,
    LevelsIdentity,
    assert_dataset_id_parity,
    normalize_execution_origin,
    normalize_levels_config,
)
from tests.fixtures.assistant_parity import parity_run_spec, write_parity_bars


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-06-01 09:30:00", periods=8, freq="1min", tz="America/New_York"
            ),
            "open": [100.0] * 8,
            "high": [100.5] * 8,
            "low": [99.5] * 8,
            "close": [100.25] * 8,
            "volume": list(range(8)),
        }
    )


def test_normalize_levels_config_merges_defaults_sets_instrument_and_sorts():
    normalized = normalize_levels_config(
        {
            "sma_lengths": [200, 50],
            "ema_lengths": [21, 9],
            "vwap_windows": ["4h", "30min"],
            "poc_windows": [],
        },
        instrument="NQ",
    )
    assert normalized["instrument"] == "NQ"
    assert normalized["sma_lengths"] == [50, 200]
    assert normalized["ema_lengths"] == [9, 21]
    assert normalized["vwap_windows"] == ["30min", "4h"]
    assert normalized["opening_range_minutes"] == DEFAULT_LEVELS_SETTINGS["opening_range_minutes"]
    assert normalized["pivots_enabled"] is True


def test_normalize_levels_config_hash_independent_of_input_order():
    left = normalize_levels_config(
        {"sma_lengths": [200, 50], "ema_timeframes": ["30min", "1min"]},
        instrument="ES",
    )
    right = normalize_levels_config(
        {"ema_timeframes": ["1min", "30min"], "sma_lengths": [50, 200]},
        instrument="ES",
    )
    assert left == right
    assert compute_levels_settings_hash(left) == compute_levels_settings_hash(right)


def test_normalize_levels_config_rejects_unknown_keys():
    with pytest.raises(ValueError, match="Unknown levels configuration keys"):
        normalize_levels_config({"lookahead": True}, instrument="ES")


def test_compute_levels_uses_shared_normalizer():
    result = compute_levels(
        _bars(),
        instrument="ES",
        config={"sma_lengths": [200, 50], "poc_windows": []},
    )
    assert result["levels_settings"] == normalize_levels_config(
        {"sma_lengths": [200, 50], "poc_windows": []},
        instrument="ES",
    )


def test_data_identity_dataset_id_matches_compute_dataset_id():
    data = _bars()
    identity = DataIdentity.from_loaded_data(
        data,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="ninjatrader",
    )
    expected = compute_dataset_id(
        data,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
    )
    assert identity.dataset_id() == expected
    assert_dataset_id_parity(data, identity)
    # format_profile is additive metadata and must not alter dataset_id.
    assert identity.format_profile == "ninjatrader"
    twin = DataIdentity.from_loaded_data(
        data,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="canonical",
    )
    assert twin.dataset_id() == identity.dataset_id()


def test_levels_identity_from_equivalent_api_and_page_inputs():
    data = _bars()
    data_identity = DataIdentity.from_loaded_data(
        data,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
    )
    unordered = {
        "sma_lengths": [200, 50],
        "ema_lengths": [21, 9],
        "vwap_windows": ["4h", "30min"],
        "poc_windows": [],
    }
    api_identity = LevelsIdentity.from_config(data_identity, unordered)
    page_identity = LevelsIdentity.from_page_state(
        {
            "data": data,
            "instrument": "ES",
            "base_interval": "1min",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
            "levels_settings": dict(unordered),
        }
    )
    assert api_identity.levels_settings_hash == page_identity.levels_settings_hash
    assert api_identity.to_dict() == page_identity.to_dict()
    assert api_identity.level_engine_version == LEVEL_ENGINE_VERSION
    assert api_identity.artifact_schema_version == LEVELS_ARTIFACT_SCHEMA_VERSION


def test_experiment_identity_from_run_spec_is_stable():
    data = _bars()
    data_identity = DataIdentity.from_loaded_data(
        data,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
    )
    levels_identity = LevelsIdentity.from_config(data_identity, {"poc_windows": []})
    spec = {"name": "x", "levels": {"poc_windows": []}, "setup": {"name": "s"}}
    left = ExperimentIdentity.from_run_spec(levels_identity, spec)
    right = ExperimentIdentity.from_run_spec(levels_identity, dict(spec))
    assert left.run_spec_hash == right.run_spec_hash
    assert ExperimentIdentity.from_dict(left.to_dict()) == left


def test_old_identity_payloads_load_as_none_when_incomplete():
    assert DataIdentity.from_dict(None) is None
    assert DataIdentity.from_dict({"instrument": "ES"}) is None
    assert LevelsIdentity.from_dict({"levels_settings_hash": "abc"}) is None
    assert ExperimentIdentity.from_dict({"run_spec_hash": "abc"}) is None


def test_normalize_execution_origin():
    assert normalize_execution_origin("assistant") == "assistant"
    assert normalize_execution_origin("CLI") == "cli"
    assert normalize_execution_origin(None) == "unknown"
    assert normalize_execution_origin("web") == "unknown"


def test_run_experiment_adds_additive_identity_and_origin(tmp_path: Path):
    write_parity_bars(tmp_path / "bars.csv")
    state = run_experiment(
        parity_run_spec(dataset_path="bars.csv"),
        base_directory=tmp_path,
        execution_origin="cli",
    )
    assert state["execution_origin"] == "cli"
    assert isinstance(state["data_identity"], dict)
    assert isinstance(state["levels_identity"], dict)
    assert isinstance(state["experiment_identity"], dict)
    assert state["data_identity"]["dataset_id"] == state["dataset_id"]
    assert state["levels_identity"]["levels_settings_hash"] == compute_levels_settings_hash(
        state["levels_settings"]
    )


def test_bundle_roundtrip_restores_identities_and_old_bundles_omit_them(tmp_path: Path):
    write_parity_bars(tmp_path / "bars.csv")
    state = run_experiment(parity_run_spec(dataset_path="bars.csv"), base_directory=tmp_path)
    bundle = build_research_bundle(state)
    with zipfile.ZipFile(io.BytesIO(bundle), "r") as zf:
        assert "research_identity.json" in zf.namelist()
        identity_meta = json.loads(zf.read("research_identity.json").decode("utf-8"))
    assert "data_identity" in identity_meta
    assert "levels_identity" in identity_meta
    # Origin and experiment_identity must not affect canonical bundle membership.
    assert "execution_origin" not in identity_meta
    assert "experiment_identity" not in identity_meta

    loaded = load_research_bundle(bundle)
    restored: dict = {}
    apply_research_bundle_to_session(loaded, restored)
    assert restored["data_identity"]["dataset_id"] == state["dataset_id"]
    assert restored["levels_identity"]["levels_settings_hash"] == state["levels_identity"][
        "levels_settings_hash"
    ]

    legacy_state = {
        "data": state["data"],
        "dataset_id": state["dataset_id"],
        "instrument": state["instrument"],
        "base_interval": state["base_interval"],
        "source_timezone": state["source_timezone"],
        "exchange_timezone": state["exchange_timezone"],
        "levels": state["levels"],
        "session_levels": state["session_levels"],
        "levels_settings": state["levels_settings"],
        "levels_data_fingerprint": state["levels_data_fingerprint"],
    }
    legacy_bundle = build_research_bundle(legacy_state)
    with zipfile.ZipFile(io.BytesIO(legacy_bundle), "r") as zf:
        assert "research_identity.json" not in zf.namelist()
    legacy_loaded = load_research_bundle(legacy_bundle)
    legacy_restored: dict = {"data_identity": {"stale": True}, "levels_identity": {"stale": True}}
    apply_research_bundle_to_session(legacy_loaded, legacy_restored)
    assert "data_identity" not in legacy_restored
    assert "levels_identity" not in legacy_restored


def test_execution_origin_does_not_change_canonical_bundle_hash(tmp_path: Path):
    write_parity_bars(tmp_path / "bars.csv")
    spec = parity_run_spec(dataset_path="bars.csv")
    api_state = run_experiment(spec, base_directory=tmp_path, execution_origin="api")
    cli_state = run_experiment(spec, base_directory=tmp_path, execution_origin="cli")
    assert api_state["execution_origin"] != cli_state["execution_origin"]
    assert canonical_bundle_hash(build_research_bundle(api_state)) == canonical_bundle_hash(
        build_research_bundle(cli_state)
    )
