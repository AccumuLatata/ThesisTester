"""CAI-4 — classic workspace state → public RunSpec export."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from thesistester.api import compute_levels, load_dataset, run_experiment, validate_run_spec
from thesistester.classic_export import (
    classic_state_export_gaps,
    classic_state_to_run_spec,
    format_classic_export_gaps,
)
from thesistester.persistence.execution_artifacts import write_data_artifact
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from thesistester.research_identity import DataIdentity
from tests.fixtures.assistant_parity import parity_run_spec, write_parity_bars


def _classic_state_from_parity(tmp_path: Path, *, with_source_path: bool = True) -> dict:
    write_parity_bars(tmp_path / "bars.csv")
    path = tmp_path / "bars.csv"
    data = load_dataset(path, instrument="ES", source_timezone="America/New_York")
    levels = compute_levels(
        data,
        instrument="ES",
        config=parity_run_spec(dataset_path="bars.csv")["levels"],
    )
    spec = parity_run_spec(dataset_path="bars.csv")
    identity = DataIdentity.from_loaded_data(
        data,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="canonical",
    )
    state = {
        "data": data,
        "dataset_id": identity.dataset_id(),
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
        "format_profile": "canonical",
        "levels_settings": levels["levels_settings"],
        "levels_data_fingerprint": {
            "instrument": "ES",
            "rows": len(data),
            "base_interval": "1min",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
        },
        "setup_config": deepcopy(spec["setup"]),
        "last_signal_setup": deepcopy(spec["setup"]),
        "backtest_config": deepcopy(spec["backtest"]),
    }
    if with_source_path:
        state["dataset_source_path"] = str(path)
    return state


def test_export_gaps_for_missing_required_sections(tmp_path: Path):
    gaps = classic_state_export_gaps({})
    codes = {gap.code for gap in gaps}
    assert "missing_data" in codes
    assert "missing_levels_settings" in codes
    assert "missing_setup" in codes
    assert "incomplete_backtest" in codes
    assert format_classic_export_gaps(gaps)[0]["code"]


def test_export_is_deterministic(tmp_path: Path):
    state = _classic_state_from_parity(tmp_path)
    first = classic_state_to_run_spec(state, name="classic_export")
    second = classic_state_to_run_spec(state, name="classic_export")
    assert first == second
    validate_run_spec(first)


def test_missing_source_path_is_explicit_gap_even_with_artifact(tmp_path: Path):
    store = tmp_path / "store"
    state = _classic_state_from_parity(tmp_path, with_source_path=False)
    identity = DataIdentity.from_dict(
        DataIdentity.from_loaded_data(
            state["data"],
            instrument="ES",
            base_interval="1min",
            source_timezone="America/New_York",
            exchange_timezone="America/New_York",
        ).to_dict()
    )
    assert identity is not None
    write_data_artifact(identity, state["data"], store_root=store)
    gaps = classic_state_export_gaps(state, store_root=store)
    codes = {gap.code for gap in gaps}
    assert "missing_source_path" in codes
    with pytest.raises(ValueError, match="missing_source_path"):
        classic_state_to_run_spec(state, name="x", store_root=store)


def test_source_path_identity_mismatch_is_gap(tmp_path: Path):
    state = _classic_state_from_parity(tmp_path)
    other = tmp_path / "other.csv"
    write_parity_bars(other)
    frame = pd.read_csv(other)
    frame.loc[0, "volume"] = int(frame.loc[0, "volume"]) + 99
    frame.to_csv(other, index=False)
    gaps = classic_state_export_gaps(state, source_path=other)
    assert any(gap.code == "source_path_identity_mismatch" for gap in gaps)


def test_no_default_levels_or_backtest_injection(tmp_path: Path):
    state = _classic_state_from_parity(tmp_path)
    del state["levels_settings"]
    del state["backtest_config"]
    gaps = classic_state_export_gaps(state)
    codes = {gap.code for gap in gaps}
    assert "missing_levels_settings" in codes
    assert "incomplete_backtest" in codes


def test_stale_levels_fingerprint_is_gap(tmp_path: Path):
    state = _classic_state_from_parity(tmp_path)
    state["levels_data_fingerprint"] = {
        **state["levels_data_fingerprint"],
        "rows": 1,
    }
    gaps = classic_state_export_gaps(state)
    assert any(gap.code == "stale_levels" for gap in gaps)


def test_exported_spec_matches_hand_authored_bundle_hash(tmp_path: Path):
    store = tmp_path / "store"
    state = _classic_state_from_parity(tmp_path)
    identity = DataIdentity.from_loaded_data(
        state["data"],
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
    )
    write_data_artifact(identity, state["data"], store_root=store)

    exported = classic_state_to_run_spec(
        state,
        name="assistant_parity",
        store_root=store,
    )
    # Compare against an equivalent hand-authored RunSpec with the same executable
    # sections (no grid/validation). Additive artifact metadata must not change results.
    hand = {
        "name": "assistant_parity",
        "dataset": {
            "path": str(tmp_path / "bars.csv"),
            "instrument": "ES",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
            "format_profile": "canonical",
        },
        "levels": deepcopy(exported["levels"]),
        "setup": deepcopy(exported["setup"]),
        "backtest": deepcopy(exported["backtest"]),
    }
    hand_state = run_experiment(hand, base_directory=tmp_path, cache_policy="off")
    export_state = run_experiment(exported, base_directory=tmp_path, cache_policy="off")
    assert canonical_bundle_hash(build_research_bundle(hand_state)) == canonical_bundle_hash(
        build_research_bundle(export_state)
    )
    assert exported["dataset"]["data_artifact_key"]
    assert exported["dataset"]["data_identity"]["dataset_id"] == state["dataset_id"]


def test_backtest_assembled_from_policy_snapshots(tmp_path: Path):
    state = _classic_state_from_parity(tmp_path)
    backtest = state.pop("backtest_config")
    state.update(
        {
            "backtest_sl_ticks": backtest["stop_loss_ticks"],
            "backtest_tp_ticks": backtest["take_profit_ticks"],
            "backtest_execution_costs": {
                "commission_per_side": backtest["commission_per_side"],
                "slippage_ticks": backtest["slippage_ticks"],
            },
            "backtest_session_exit_policy": {
                "flat_by_session_close": backtest["flat_by_session_close"],
                "session_close_time": backtest["session_close_time"],
                "session_timezone": backtest["session_timezone"],
                "no_new_entries_after": backtest["no_new_entries_after"],
            },
            "backtest_intrabar_policy": {
                "schema_version": 1,
                "intrabar_model": backtest["intrabar_model"],
            },
            "exposure_policy": {
                "exposure_policy": backtest["exposure_policy"],
                "cooldown_bars_after_exit": 0,
            },
            "backtest_exit_management_policy": {
                "schema_version": 1,
                "breakeven_after_r": None,
                "trailing_after_r": None,
                "trailing_distance_ticks": None,
            },
        }
    )
    spec = classic_state_to_run_spec(state, name="from_policies")
    assert spec["backtest"]["stop_loss_ticks"] == backtest["stop_loss_ticks"]
    assert spec["backtest"]["exposure_policy"] == backtest["exposure_policy"]
    validate_run_spec(spec)


def test_include_grid_requires_explicit_config(tmp_path: Path):
    state = _classic_state_from_parity(tmp_path)
    with pytest.raises(ValueError, match="incomplete_grid"):
        classic_state_to_run_spec(state, name="x", include_grid=True)
    state["grid_config"] = deepcopy(parity_run_spec(dataset_path="bars.csv")["grid"])
    spec = classic_state_to_run_spec(state, name="with_grid", include_grid=True)
    assert "grid" in spec
    validate_run_spec(spec)
