"""PR3 — durable/headless 15s-primary derive reproducibility."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from thesistester.api import run_experiment, validate_run_spec
from thesistester.data.derive import (
    DERIVATION_POLICY_DEFAULT,
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
)
from thesistester.persistence.execution_artifacts import (
    read_source_data_binding,
    source_binding_key,
    source_content_hash,
)
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash

VENDOR_15S = Path(__file__).parent / "fixtures" / "vendor" / "quantower_history_exporter_15s.csv"


def _minimal_derive_spec(dataset_path: str, *, intrabar_model: str = "subtimeframe") -> dict:
    return {
        "name": "es_15s_primary",
        "dataset": {
            "path": dataset_path,
            "instrument": "ES",
            "source_timezone": "America/New_York",
            "format_profile": "quantower_history_exporter",
            "ingestion_mode": INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        },
        "levels": {
            "sma_lengths": [2],
            "ema_lengths": [2],
            "sma_timeframes": ["1min"],
            "ema_timeframes": ["1min"],
            "vwap_windows": [],
            "poc_windows": [],
        },
        "setup": {
            "name": "es_15s_primary",
            "description": "One-file 15s-primary R12 fixture",
            "instrument": "ES",
            "selected_levels": ["dOpen", "RTH_Open"],
            "tolerance_ticks": 0,
            "min_confluences": 2,
            "max_confluences": 2,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger": "touch",
            "trigger_timeframe": "base",
            "direction": "both",
            "confluence_mode": "global_cluster",
            "anchor_level": None,
            "confluence_rules": [],
            "min_valid_confluences": 1,
            "trigger_params": {},
            "otf_filter": None,
        },
        "backtest": {
            "stop_loss_ticks": 2,
            "take_profit_ticks": 3,
            "exposure_policy": "single_position",
            "intrabar_model": intrabar_model,
        },
        "grid": {"enabled": False},
        "validation": {"enabled": False},
    }


def test_validate_run_spec_accepts_one_file_15s_primary_for_r12():
    spec = _minimal_derive_spec("nq_15s.csv")
    validate_run_spec(spec)


def test_validate_run_spec_rejects_subtimeframe_path_with_derive_mode():
    spec = _minimal_derive_spec("nq_15s.csv")
    spec["dataset"]["subtimeframe_path"] = "other_15s.csv"
    with pytest.raises(ValueError, match="subtimeframe_path cannot be combined"):
        validate_run_spec(spec)


def test_validate_run_spec_rejects_unsupported_profile_for_derive_mode():
    spec = _minimal_derive_spec("nq_15s.csv")
    spec["dataset"]["format_profile"] = "canonical"
    with pytest.raises(ValueError, match="format_profile must be one of"):
        validate_run_spec(spec)


def test_api_one_file_15s_primary_reaches_strict_r12_without_subtimeframe_path(
    tmp_path: Path,
):
    csv_path = tmp_path / "es_15s.csv"
    shutil.copy(VENDOR_15S, csv_path)
    state = run_experiment(
        _minimal_derive_spec("es_15s.csv"),
        base_directory=tmp_path,
        cache_policy="off",
    )

    assert state["base_interval"] == "1min"
    assert state["subtimeframe_interval"] == "15s"
    assert state["subtimeframe_format_profile"] == "quantower_history_exporter"
    assert state["ingestion_provenance"]["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert state["ingestion_provenance"]["derivation_policy"] == DERIVATION_POLICY_DEFAULT
    assert state["backtest_intrabar_policy"]["intrabar_model"] == "subtimeframe"
    assert state["backtest_intrabar_policy"]["subtimeframe_data_supplied"] is True
    assert len(state["data"]) == 2
    assert len(state["subtimeframe_data"]) == 8


def test_api_sparse_15s_primary_persists_declared_subtimeframe_interval(tmp_path: Path):
    """One print/minute gap-infers as 1min; state must still expose declared 15s."""
    path = tmp_path / "sparse_15s.csv"
    rows = ["Time left;Time right;Open;High;Low;Close;Volume;"]
    for minute in range(30, 40):
        rows.append(
            f"2026-06-02 09:{minute}:00.000;2026-06-02 09:{minute}:14.999;"
            f"{100 + minute};{101 + minute};{99 + minute};{100.5 + minute};1;"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    state = run_experiment(
        _minimal_derive_spec(
            "sparse_15s.csv",
            intrabar_model="subtimeframe_conservative",
        ),
        base_directory=tmp_path,
        cache_policy="off",
    )

    assert state["base_interval"] == "1min"
    assert state["subtimeframe_interval"] == "15s"
    assert state["ingestion_provenance"]["source_interval"] == "15s"
    assert state["ingestion_provenance"]["sparse_parent_bucket_count"] == 10
    assert len(state["data"]) == 10
    assert len(state["subtimeframe_data"]) == 10


def test_api_15s_primary_cache_write_does_not_warm_cross_primary_mode(tmp_path: Path):
    csv_path = tmp_path / "es_15s.csv"
    shutil.copy(VENDOR_15S, csv_path)
    store = tmp_path / "store"

    cold = run_experiment(
        _minimal_derive_spec("es_15s.csv"),
        base_directory=tmp_path,
        cache_policy="read_write",
        store_root=store,
    )
    assert cold["cache_provenance"]["data"]["status"] == "written"

    warm = run_experiment(
        _minimal_derive_spec("es_15s.csv"),
        base_directory=tmp_path,
        cache_policy="read_write",
        store_root=store,
    )
    assert warm["cache_provenance"]["data"]["status"] == "hit"
    assert canonical_bundle_hash(build_research_bundle(cold)) == canonical_bundle_hash(
        build_research_bundle(warm)
    )
    pd.testing.assert_frame_equal(cold["data"], warm["data"], check_dtype=False)
    pd.testing.assert_frame_equal(
        cold["subtimeframe_data"], warm["subtimeframe_data"], check_dtype=False
    )

    content_hash = source_content_hash(csv_path)
    derive_key = source_binding_key(
        source_content_hash_value=content_hash,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="quantower_history_exporter",
        ingestion_mode=INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        derivation_policy=DERIVATION_POLICY_DEFAULT,
    )
    primary_key = source_binding_key(
        source_content_hash_value=content_hash,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="quantower_history_exporter",
        ingestion_mode="primary",
        derivation_policy=None,
    )
    assert derive_key != primary_key
    assert derive_key == warm["cache_provenance"]["data"]["binding_key"]

    from thesistester.persistence.execution_artifacts import ArtifactMiss

    primary_binding = read_source_data_binding(
        source_path=csv_path,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="quantower_history_exporter",
        ingestion_mode="primary",
        derivation_policy=None,
        store_root=store,
    )
    assert isinstance(primary_binding, ArtifactMiss)
    assert primary_binding.reason == "missing"


def test_research_bundle_roundtrip_preserves_derived_provenance(tmp_path: Path):
    csv_path = tmp_path / "es_15s.csv"
    shutil.copy(VENDOR_15S, csv_path)
    state = run_experiment(
        _minimal_derive_spec("es_15s.csv"),
        base_directory=tmp_path,
        cache_policy="off",
    )
    from thesistester.research_bundle import (
        apply_research_bundle_to_session,
        load_research_bundle,
    )

    loaded = load_research_bundle(build_research_bundle(state))
    restored: dict = {}
    apply_research_bundle_to_session(loaded, restored)

    assert restored["ingestion_provenance"] == state["ingestion_provenance"]
    assert restored["subtimeframe_format_profile"] == "quantower_history_exporter"
    assert restored["subtimeframe_interval"] == "15s"
    pd.testing.assert_frame_equal(
        restored["subtimeframe_data"], state["subtimeframe_data"], check_dtype=False
    )
    pd.testing.assert_frame_equal(restored["data"], state["data"], check_dtype=False)


def test_api_15s_primary_resolves_ohlc_identical_source_duplicates(tmp_path: Path):
    rows = VENDOR_15S.read_text(encoding="utf-8").splitlines()
    # Repeat the first 15s open with a higher volume; lowest volume is kept.
    rows.append(
        "2026-06-02 09:30:00.000;2026-06-02 09:30:14.999;100;101;100;99;100;100;99;0;100;"
    )
    path = tmp_path / "es_15s_dup.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    state = run_experiment(
        _minimal_derive_spec("es_15s_dup.csv"),
        base_directory=tmp_path,
        cache_policy="off",
    )

    assert len(state["data"]) == 2
    assert len(state["subtimeframe_data"]) == 8
    assert float(state["data"]["volume"].iloc[0]) == 10.0
    provenance = state["ingestion_provenance"]
    assert provenance["source_duplicate_resolution"] == "ohlc_identical_keep_lowest_volume"
    assert provenance["source_duplicate_groups_resolved"] == 1
    assert provenance["source_duplicate_rows_discarded"] == 1
    assert provenance["source_duplicate_audit"][0]["retained_volume"] == 2.0
    assert provenance["source_duplicate_audit"][0]["discarded_volumes"] == [99.0]


def test_api_15s_primary_ohlc_conflict_source_duplicates_fail_closed(tmp_path: Path):
    rows = VENDOR_15S.read_text(encoding="utf-8").splitlines()
    rows.append(
        "2026-06-02 09:30:00.000;2026-06-02 09:30:14.999;100;101;100;99;100.5;100;2;0;100;"
    )
    path = tmp_path / "es_15s_conflict.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="conflicting OHLC"):
        run_experiment(
            _minimal_derive_spec("es_15s_conflict.csv"),
            base_directory=tmp_path,
            cache_policy="off",
        )
