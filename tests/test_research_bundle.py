from __future__ import annotations

import io
import json
import zipfile

import pandas as pd
import pytest

from thesistester.research_bundle import (
    apply_research_bundle_to_session,
    build_research_bundle,
    canonical_bundle_hash,
    load_research_bundle,
)


def _dataset_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-06-01 09:30:00", periods=3, freq="1min", tz="America/New_York"
            ),
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
        "excursion": False,
        "monte_carlo": False,
    }


def test_canonical_hash_ignores_created_at_but_detects_logical_changes():
    first_empty = build_research_bundle({})
    second_empty = build_research_bundle({})
    assert first_empty != second_empty
    assert canonical_bundle_hash(first_empty) == canonical_bundle_hash(second_empty)

    base = _dataset_df()
    es_bundle = build_research_bundle(
        {
            "data": base,
            "dataset_id": "same",
            "instrument": "ES",
            "base_interval": "1min",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
        }
    )
    nq_bundle = build_research_bundle(
        {
            "data": base,
            "dataset_id": "same",
            "instrument": "NQ",
            "base_interval": "1min",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
        }
    )
    changed_frame_bundle = build_research_bundle(
        {
            "data": base.assign(close=[1.5, 2.5, 99.0]),
            "dataset_id": "same",
            "instrument": "ES",
            "base_interval": "1min",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
        }
    )
    assert canonical_bundle_hash(es_bundle) != canonical_bundle_hash(nq_bundle)
    assert canonical_bundle_hash(es_bundle) != canonical_bundle_hash(changed_frame_bundle)


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


def test_dataset_only_import_clears_stale_downstream_artifacts():
    bundle_bytes = build_research_bundle(
        {
            "data": _dataset_df(),
            "dataset_id": "dataset-2",
            "instrument": "NQ",
            "base_interval": "1min",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
        }
    )
    loaded = load_research_bundle(bundle_bytes)
    existing_state: dict = {
        "levels": pd.DataFrame({"level": [1.0]}),
        "subtimeframe_data": _dataset_df(),
        "subtimeframe_interval": "1min",
        "signals": pd.DataFrame({"signal_id": [1]}),
        "trades": pd.DataFrame({"trade_id": [1]}),
        "backtest_intrabar_policy": {"intrabar_model": "path_open_proximity"},
        "backtest_intrabar_diagnostic": {"same_bar_both_hit_count": 1},
        "backtest_exit_management_policy": {"breakeven_after_r": 1.0},
        "backtest_exit_management_diagnostic": {"be_exit_count": 1},
        "grid_results": pd.DataFrame({"expectancy_r": [0.1]}),
        "grid_intrabar_policy": {"intrabar_model": "path_open_proximity"},
        "grid_exit_management_policy": {"breakeven_after_r_values": [1.0]},
        "validation_summary": {"trade_count": {"status": "limited"}},
        "walk_forward_results": pd.DataFrame({"fold_id": [0]}),
        "walk_forward_summary": {"fold_count": 1},
        "walk_forward_config": {"fold_mode": "sessions"},
        "walk_forward_oos_trades": pd.DataFrame({"trade_id": [0]}),
        "walk_forward_stitched_equity": pd.DataFrame({"cum_r": [1.0]}),
        "walk_forward_warnings": ["stale"],
        "wfa_matrix": pd.DataFrame({"matrix_value": [0.1]}),
        "wfa_matrix_config": {"train_session_values": [2]},
        "excursion_summary": {
            "schema_version": 1,
            "available": True,
            "trade_count": 1,
            "edge_ratio": {"mean_edge_ratio_r": 2.0},
        },
        "excursion_config": {"both_hit_rule": "stop_first"},
        "excursion_grouped_summary": pd.DataFrame(
            {"direction": ["long"], "trade_count": [1], "mean_mae_r": [0.5]}
        ),
        "excursion_calibration_grid": pd.DataFrame(
            {"stop_r": [1.0], "target_r": [2.0], "target_hit_probability": [0.5]}
        ),
        "excursion_quadrant_summary": pd.DataFrame(
            {"quadrant": ["target_without_full_stop"], "count": [1]}
        ),
        "monte_carlo_summary": {"schema_version": 1, "available": True},
        "monte_carlo_config": {"n_simulations": 100},
        "noise_summary": {"schema_version": 1, "available": True},
        "noise_config": {"n_replicas": 100},
        "overfitting_summary": {"schema_version": 1, "available": True},
        "overfitting_config": {"pbo_partitions": 4},
        "sensitivity_summary": {"schema_version": 1, "available": True},
        "sensitivity_config": {"perturbation_fraction": 0.2},
    }

    apply_research_bundle_to_session(loaded, existing_state)

    assert "data" in existing_state
    assert existing_state["dataset_id"] == "dataset-2"
    assert existing_state["instrument"] == "NQ"
    assert existing_state["base_interval"] == "1min"
    assert existing_state["source_timezone"] == "America/New_York"
    assert existing_state["exchange_timezone"] == "America/New_York"

    for key in (
        "levels",
        "subtimeframe_data",
        "subtimeframe_interval",
        "signals",
        "trades",
        "backtest_intrabar_policy",
        "backtest_intrabar_diagnostic",
        "backtest_exit_management_policy",
        "backtest_exit_management_diagnostic",
        "grid_results",
        "grid_intrabar_policy",
        "grid_exit_management_policy",
        "validation_summary",
        "walk_forward_results",
        "walk_forward_summary",
        "walk_forward_config",
        "walk_forward_oos_trades",
        "walk_forward_stitched_equity",
        "walk_forward_warnings",
        "wfa_matrix",
        "wfa_matrix_config",
        "excursion_summary",
        "excursion_config",
        "excursion_grouped_summary",
        "excursion_calibration_grid",
        "excursion_quadrant_summary",
        "monte_carlo_summary",
        "monte_carlo_config",
        "noise_summary",
        "noise_config",
        "overfitting_summary",
        "overfitting_config",
        "sensitivity_summary",
        "sensitivity_config",
    ):
        assert key not in existing_state


def test_full_bundle_roundtrip_restores_all_supported_artifacts():
    base = _dataset_df()
    source_state = {
        "data": base,
        "subtimeframe_data": base.copy(),
        "subtimeframe_interval": "1min",
        "dataset_id": "dataset-xyz",
        "instrument": "NQ",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
        "levels": base.assign(RTH_Open=[1.0, 1.0, 1.0]),
        "session_levels": base[["timestamp", "open", "high", "low", "close"]].copy(),
        "levels_settings": {"opening_range_minutes": 30},
        "levels_data_fingerprint": {"rows": 3},
        "signals": pd.DataFrame(
            {"signal_id": [1], "timestamp": [base["timestamp"].iloc[0]], "direction": ["long"]}
        ),
        "confluence_zones": pd.DataFrame({"bar_index": [0], "zone_low": [1.0], "zone_high": [1.5]}),
        "naked_flags": pd.DataFrame({"RTH_Open": [True]}),
        "signal_context": {"setup_name": "A"},
        "last_signal_setup": {"name": "A"},
        "signal_settings": {"trigger": "touch"},
        "signal_settings_hash": "sig-hash",
        "trades": pd.DataFrame({"trade_id": [1], "r_multiple": [1.0]}),
        "trade_summary": {"trade_count": 1},
        "backtest_intrabar_policy": {
            "schema_version": 1,
            "intrabar_model": "subtimeframe",
        },
        "backtest_intrabar_diagnostic": {
            "schema_version": 1,
            "same_bar_both_hit_count": 1,
        },
        "backtest_exit_management_policy": {
            "schema_version": 1,
            "breakeven_after_r": 1.0,
            "trailing_after_r": None,
            "trailing_distance_ticks": None,
        },
        "backtest_exit_management_diagnostic": {
            "schema_version": 1,
            "be_exit_count": 1,
            "trail_exit_count": 0,
        },
        "equity_curve": pd.DataFrame({"trade_id": [1], "cum_r": [1.0]}),
        "grid_results": pd.DataFrame(
            {"stop_loss_ticks": [4.0], "take_profit_ticks": [8.0], "expectancy_r": [0.2]}
        ),
        "best_grid_result": {"stop_loss_ticks": 4.0, "take_profit_ticks": 8.0},
        "grid_intrabar_policy": {
            "schema_version": 1,
            "intrabar_model": "path_open_proximity",
        },
        "grid_exit_management_policy": {
            "schema_version": 1,
            "breakeven_after_r_values": [None, 1.0],
            "trailing_after_r_values": [None],
        },
        "validation_summary": {"trade_count": {"status": "limited"}},
        "walk_forward_results": pd.DataFrame(
            {
                "fold_id": [0],
                "fold_mode": ["sessions"],
                "test_expectancy_r": [0.2],
            }
        ),
        "walk_forward_summary": {
            "schema_version": 2,
            "fold_count": 1,
            "stitched_oos_status": "ok",
        },
        "walk_forward_config": {
            "fold_mode": "sessions",
            "train_sessions": 2,
            "test_sessions": 1,
        },
        "walk_forward_oos_trades": pd.DataFrame(
            {"trade_id": [0], "fold_id": [0], "r_multiple": [1.0]}
        ),
        "walk_forward_stitched_equity": pd.DataFrame({"trade_id": [0], "cum_r": [1.0]}),
        "walk_forward_warnings": [],
        "wfa_matrix": pd.DataFrame(
            {
                "train_sessions": [2],
                "test_sessions": [1],
                "matrix_value": [0.2],
            }
        ),
        "wfa_matrix_config": {
            "train_session_values": [2],
            "test_session_values": [1],
        },
        "excursion_summary": {
            "schema_version": 1,
            "available": True,
            "trade_count": 1,
            "edge_ratio": {"mean_edge_ratio_r": 2.0},
        },
        "excursion_config": {"both_hit_rule": "stop_first"},
        "excursion_grouped_summary": pd.DataFrame(
            {"direction": ["long"], "trade_count": [1], "mean_mae_r": [0.5]}
        ),
        "excursion_calibration_grid": pd.DataFrame(
            {"stop_r": [1.0], "target_r": [2.0], "target_hit_probability": [0.5]}
        ),
        "excursion_quadrant_summary": pd.DataFrame(
            {"quadrant": ["target_without_full_stop"], "count": [1]}
        ),
        "monte_carlo_summary": {
            "schema_version": 1,
            "available": True,
            "trade_count": 1,
            "methods": {
                "reshuffle": {
                    "observed": {"final_r": 1.0},
                    "simulated": {"max_drawdown_r": {"p95": 0.5}},
                }
            },
        },
        "monte_carlo_config": {"n_simulations": 50, "random_state": 42},
        "noise_summary": {
            "schema_version": 1,
            "available": True,
            "replicas": {"n_completed": 50},
        },
        "noise_config": {"n_replicas": 50, "random_state": 42},
        "overfitting_summary": {
            "schema_version": 1,
            "available": True,
            "pbo": {"pbo": 0.25},
        },
        "overfitting_config": {"pbo_partitions": 4, "random_state": 42},
        "sensitivity_summary": {
            "schema_version": 1,
            "available": True,
            "fragile_parameter_count": 1,
        },
        "sensitivity_config": {"perturbation_fraction": 0.2, "n_steps_per_side": 5},
    }

    bundle_bytes = build_research_bundle(source_state)
    loaded = load_research_bundle(bundle_bytes)
    restored_state: dict = {}
    apply_research_bundle_to_session(loaded, restored_state)

    for key in (
        "data",
        "subtimeframe_data",
        "levels",
        "session_levels",
        "signals",
        "confluence_zones",
        "naked_flags",
        "trades",
        "equity_curve",
        "grid_results",
        "walk_forward_results",
        "walk_forward_oos_trades",
        "walk_forward_stitched_equity",
        "wfa_matrix",
        "excursion_grouped_summary",
        "excursion_calibration_grid",
        "excursion_quadrant_summary",
    ):
        pd.testing.assert_frame_equal(restored_state[key], source_state[key])

    assert restored_state["levels_settings"] == {"opening_range_minutes": 30}
    assert restored_state["levels_data_fingerprint"] == {"rows": 3}
    assert restored_state["signal_context"] == {"setup_name": "A"}
    assert restored_state["last_signal_setup"] == {"name": "A"}
    assert restored_state["signal_settings"] == {"trigger": "touch"}
    assert restored_state["signal_settings_hash"] == "sig-hash"
    assert restored_state["trade_summary"] == {"trade_count": 1}
    assert restored_state["subtimeframe_interval"] == "1min"
    assert restored_state["backtest_intrabar_policy"]["intrabar_model"] == "subtimeframe"
    assert restored_state["backtest_intrabar_diagnostic"]["same_bar_both_hit_count"] == 1
    assert restored_state["backtest_exit_management_policy"]["breakeven_after_r"] == 1.0
    assert restored_state["backtest_exit_management_diagnostic"]["be_exit_count"] == 1
    assert restored_state["best_grid_result"] == {"stop_loss_ticks": 4.0, "take_profit_ticks": 8.0}
    assert restored_state["grid_intrabar_policy"]["intrabar_model"] == "path_open_proximity"
    assert restored_state["grid_exit_management_policy"]["breakeven_after_r_values"] == [None, 1.0]
    assert restored_state["validation_summary"] == {"trade_count": {"status": "limited"}}
    assert restored_state["walk_forward_summary"]["schema_version"] == 2
    assert restored_state["walk_forward_config"]["fold_mode"] == "sessions"
    assert restored_state["wfa_matrix_config"]["train_session_values"] == [2]
    assert restored_state["excursion_summary"]["schema_version"] == 1
    assert restored_state["excursion_summary"]["trade_count"] == 1
    assert restored_state["excursion_config"] == {"both_hit_rule": "stop_first"}
    assert restored_state["monte_carlo_summary"]["schema_version"] == 1
    assert restored_state["monte_carlo_summary"]["trade_count"] == 1
    assert restored_state["monte_carlo_config"] == {"n_simulations": 50, "random_state": 42}
    assert restored_state["noise_summary"]["schema_version"] == 1
    assert restored_state["noise_config"] == {"n_replicas": 50, "random_state": 42}
    assert restored_state["overfitting_summary"]["schema_version"] == 1
    assert restored_state["overfitting_config"]["pbo_partitions"] == 4
    assert restored_state["sensitivity_summary"]["fragile_parameter_count"] == 1
    assert restored_state["sensitivity_config"]["perturbation_fraction"] == 0.2


def test_portfolio_bundle_roundtrip_restores_portfolio_artifacts():
    state = {
        "portfolio_summary": {
            "schema_version": 1,
            "available": True,
            "portfolio_metrics": {"total_r": 3.0},
        },
        "portfolio_config": {"instrument": "ES", "setup_ids": ["A", "B"]},
        "portfolio_setup_inputs": ["A", "B"],
        "portfolio_trades": pd.DataFrame({"setup_id": ["A", "B"], "r_multiple": [1.0, 2.0]}),
        "portfolio_skipped_trades": pd.DataFrame({"setup_id": ["C"], "skip_reason": ["x"]}),
        "portfolio_equity_curve": pd.DataFrame({"cum_r": [1.0, 3.0]}),
        "portfolio_correlation": pd.DataFrame([[1.0, 0.5], [0.5, 1.0]], columns=["A", "B"]),
        "portfolio_drawdown_correlation": pd.DataFrame(
            [[1.0, 0.25], [0.25, 1.0]], columns=["A", "B"]
        ),
        "portfolio_marginal_contribution": pd.DataFrame(
            {"setup_id": ["A", "B"], "total_r_contribution": [1.0, 2.0]}
        ),
    }

    loaded = load_research_bundle(build_research_bundle(state))

    assert loaded["manifest"]["included"]["portfolio"] is True
    assert loaded["session_values"]["portfolio_summary"]["portfolio_metrics"]["total_r"] == 3.0
    pd.testing.assert_frame_equal(
        loaded["session_values"]["portfolio_trades"], state["portfolio_trades"]
    )


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


def test_bundle_export_handles_best_grid_result_series():
    source_state = {
        "grid_results": pd.DataFrame(
            {
                "stop_loss_ticks": [4.0],
                "take_profit_ticks": [8.0],
                "expectancy_r": [0.25],
            }
        ),
        "best_grid_result": pd.Series(
            {
                "stop_loss_ticks": 4.0,
                "take_profit_ticks": 8.0,
                "expectancy_r": 0.25,
            }
        ),
    }

    bundle_bytes = build_research_bundle(source_state)
    loaded = load_research_bundle(bundle_bytes)
    restored_state = {}
    apply_research_bundle_to_session(loaded, restored_state)

    assert restored_state["best_grid_result"] == {
        "stop_loss_ticks": 4.0,
        "take_profit_ticks": 8.0,
        "expectancy_r": 0.25,
    }


def test_bundle_best_grid_result_series_nan_normalizes_to_none():
    source_state = {
        "grid_results": pd.DataFrame(
            {
                "stop_loss_ticks": [4.0],
                "take_profit_ticks": [float("nan")],
                "expectancy_r": [0.25],
            }
        ),
        "best_grid_result": pd.Series(
            {
                "stop_loss_ticks": 4.0,
                "take_profit_ticks": float("nan"),
                "expectancy_r": pd.NA,
            }
        ),
    }

    bundle_bytes = build_research_bundle(source_state)
    loaded = load_research_bundle(bundle_bytes)
    restored_state = {}
    apply_research_bundle_to_session(loaded, restored_state)

    result = restored_state["best_grid_result"]
    assert result["stop_loss_ticks"] == 4.0
    assert result["take_profit_ticks"] is None
    assert result["expectancy_r"] is None
