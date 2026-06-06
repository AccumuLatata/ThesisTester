from __future__ import annotations

import io
import json
import zipfile

import pandas as pd
import pytest

from thesistester.research_bundle import (
    apply_research_bundle_to_session,
    build_research_bundle,
    load_research_bundle,
)


def _dataset_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01 09:30:00", periods=3, freq="1min", tz="America/New_York"),
            "open": [1.0, 2.0, 3.0],
            "high": [2.0, 3.0, 4.0],
            "low": [0.5, 1.5, 2.5],
            "close": [1.5, 2.5, 3.5],
            "volume": [10, 20, 30],
        }
    )


def _bundle_names(bundle_bytes: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as zf:
        return sorted(zf.namelist())


def _manifest(bundle_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


def _rewrite_bundle_manifest(bundle_bytes: bytes, updated_manifest: dict) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as src, zipfile.ZipFile(output, "w") as dst:
        for name in src.namelist():
            if name == "manifest.json":
                dst.writestr("manifest.json", json.dumps(updated_manifest))
            else:
                dst.writestr(name, src.read(name))
    return output.getvalue()


def test_empty_session_exports_manifest_only():
    bundle = build_research_bundle({})
    names = _bundle_names(bundle)
    manifest = _manifest(bundle)

    assert names == ["manifest.json"]
    assert manifest["kind"] == "thesistester_research_bundle"
    assert manifest["bundle_schema_version"] == 1
    assert manifest["included"] == {
        "dataset": False,
        "levels": False,
        "signals": False,
        "backtest": False,
        "grid": False,
        "validation": False,
    }


def test_dataset_only_roundtrip_restores_data_and_metadata():
    source_state = {
        "data": _dataset_df(),
        "dataset_id": "dataset-1",
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
    }
    bundle_bytes = build_research_bundle(source_state)
    loaded = load_research_bundle(bundle_bytes)
    restored_state: dict = {}
    apply_research_bundle_to_session(loaded, restored_state)

    pd.testing.assert_frame_equal(restored_state["data"], source_state["data"])
    assert restored_state["dataset_id"] == "dataset-1"
    assert restored_state["instrument"] == "ES"
    assert restored_state["base_interval"] == "1min"
    assert restored_state["source_timezone"] == "America/New_York"
    assert restored_state["exchange_timezone"] == "America/New_York"


def test_full_bundle_roundtrip_restores_all_supported_artifacts():
    base = _dataset_df()
    source_state = {
        "data": base,
        "dataset_id": "dataset-xyz",
        "instrument": "NQ",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
        "levels": base.assign(RTH_Open=[1.0, 1.0, 1.0]),
        "session_levels": base[["timestamp", "open", "high", "low", "close"]].copy(),
        "levels_settings": {"opening_range_minutes": 30},
        "levels_data_fingerprint": {"rows": 3},
        "signals": pd.DataFrame({"signal_id": [1], "timestamp": [base["timestamp"].iloc[0]], "direction": ["long"]}),
        "confluence_zones": pd.DataFrame({"bar_index": [0], "zone_low": [1.0], "zone_high": [1.5]}),
        "naked_flags": pd.DataFrame({"RTH_Open": [True]}),
        "signal_context": {"setup_name": "A"},
        "last_signal_setup": {"name": "A"},
        "signal_settings": {"trigger": "touch"},
        "signal_settings_hash": "sig-hash",
        "trades": pd.DataFrame({"trade_id": [1], "r_multiple": [1.0]}),
        "trade_summary": {"trade_count": 1},
        "equity_curve": pd.DataFrame({"trade_id": [1], "cum_r": [1.0]}),
        "grid_results": pd.DataFrame({"stop_loss_ticks": [4.0], "take_profit_ticks": [8.0], "expectancy_r": [0.2]}),
        "best_grid_result": {"stop_loss_ticks": 4.0, "take_profit_ticks": 8.0},
        "validation_summary": {"trade_count": {"status": "limited"}},
    }

    bundle_bytes = build_research_bundle(source_state)
    loaded = load_research_bundle(bundle_bytes)
    restored_state: dict = {}
    apply_research_bundle_to_session(loaded, restored_state)

    for key in (
        "data",
        "levels",
        "session_levels",
        "signals",
        "confluence_zones",
        "naked_flags",
        "trades",
        "equity_curve",
        "grid_results",
    ):
        pd.testing.assert_frame_equal(restored_state[key], source_state[key])

    assert restored_state["levels_settings"] == {"opening_range_minutes": 30}
    assert restored_state["levels_data_fingerprint"] == {"rows": 3}
    assert restored_state["signal_context"] == {"setup_name": "A"}
    assert restored_state["last_signal_setup"] == {"name": "A"}
    assert restored_state["signal_settings"] == {"trigger": "touch"}
    assert restored_state["signal_settings_hash"] == "sig-hash"
    assert restored_state["trade_summary"] == {"trade_count": 1}
    assert restored_state["best_grid_result"] == {"stop_loss_ticks": 4.0, "take_profit_ticks": 8.0}
    assert restored_state["validation_summary"] == {"trade_count": {"status": "limited"}}


def test_unknown_zip_files_are_ignored():
    bundle_bytes = build_research_bundle({"data": _dataset_df()})
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as src, zipfile.ZipFile(output, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr("random.txt", "ignore me")

    loaded = load_research_bundle(output.getvalue())
    assert "data" in loaded["session_values"]


def test_missing_manifest_raises_clear_error():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as zf:
        zf.writestr("dataset.parquet", b"not a parquet")

    with pytest.raises(ValueError, match="manifest.json"):
        load_research_bundle(raw.getvalue())


def test_invalid_bundle_schema_raises_clear_error():
    bundle_bytes = build_research_bundle({"data": _dataset_df()})
    manifest = _manifest(bundle_bytes)
    manifest["bundle_schema_version"] = 999
    broken_bundle = _rewrite_bundle_manifest(bundle_bytes, manifest)

    with pytest.raises(ValueError, match="schema version"):
        load_research_bundle(broken_bundle)
