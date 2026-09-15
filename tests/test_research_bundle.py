from __future__ import annotations

import ast
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

import thesistester.research_bundle as research_bundle
from thesistester.reporting import build_otf_filter_metadata, build_research_artifact
from thesistester.research_bundle import (
    BUNDLE_IMPORT_OMITTED_DATA_KEY,
    BUNDLE_KEY_REGISTRY,
    BUNDLE_KEY_REGISTRY_NAMES,
    BUNDLE_SECTION_IO,
    BUNDLE_SECTION_IO_NAMES,
    DATA_PAGE_INVALIDATE_SOURCE_KEY,
    _CANONICAL_HASH_EXCLUDED_FILES,
    _KNOWN_FILES,
    _MANAGED_RESEARCH_KEYS,
    _SECTION_REQUIRED_FILES,
    apply_research_bundle_to_session,
    build_research_bundle,
    canonical_bundle_hash,
    load_research_bundle,
    peek_research_identity,
    should_skip_dataset_bootstrap,
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
    assert restored_state[DATA_PAGE_INVALIDATE_SOURCE_KEY] is True


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
        "subtimeframe_format_profile": "quantower_history_exporter",
        "ingestion_provenance": {"ingestion_mode": "15s_primary_derive_1m"},
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
        "confluence_combo_summary": {"available": True, "trade_count": 3},
        "confluence_by_exact_combo": pd.DataFrame({"exact_combo_key": ["A|B"], "trade_count": [2]}),
        "confluence_by_level_count": pd.DataFrame(
            {"level_count_bucket": ["2"], "trade_count": [2]}
        ),
        "confluence_by_membership": pd.DataFrame({"level_name": ["A"], "trade_count": [2]}),
        "confluence_by_pairs": pd.DataFrame({"pair_key": ["A|B"], "trade_count": [2]}),
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
        "subtimeframe_format_profile",
        "ingestion_provenance",
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
        "confluence_combo_summary",
        "confluence_by_exact_combo",
        "confluence_by_level_count",
        "confluence_by_membership",
        "confluence_by_pairs",
    ):
        assert key not in existing_state


def test_full_bundle_roundtrip_restores_all_supported_artifacts():
    base = _dataset_df()
    source_state = {
        "data": base,
        "subtimeframe_data": base.copy(),
        "subtimeframe_interval": "15s",
        "subtimeframe_format_profile": "quantower_history_exporter",
        "ingestion_provenance": {
            "ingestion_mode": "15s_primary_derive_1m",
            "derivation_policy": "complete_aligned_15s_to_1m_v1",
            "dropped_parent_bucket_count": 0,
        },
        "subtimeframe_fallback_parent_bars": [
            {
                "bar_index": 1,
                "timestamp": "2026-01-05 09:31:00-05:00",
                "reason": "incomplete coverage: expected 4, observed 3",
            }
        ],
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
    assert restored_state["subtimeframe_interval"] == "15s"
    assert restored_state["subtimeframe_format_profile"] == "quantower_history_exporter"
    assert restored_state["ingestion_provenance"] == {
        "ingestion_mode": "15s_primary_derive_1m",
        "derivation_policy": "complete_aligned_15s_to_1m_v1",
        "dropped_parent_bucket_count": 0,
    }
    assert restored_state["subtimeframe_fallback_parent_bars"] == [
        {
            "bar_index": 1,
            "timestamp": "2026-01-05 09:31:00-05:00",
            "reason": "incomplete coverage: expected 4, observed 3",
        }
    ]
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


def _confluence_combo_session_state() -> dict:
    """Session trades with nonempty level_names for on-export combo recompute.

    Includes equity_curve so the backtest section is present — combo siblings
    are gated on backtest inclusion (no orphan combo without trades.parquet).
    """
    trades = pd.DataFrame(
        {
            "trade_id": [1, 2, 3, 4, 5],
            "entry_timestamp": pd.to_datetime(
                [
                    "2024-01-02 09:31",
                    "2024-01-02 09:40",
                    "2024-01-02 10:05",
                    "2024-01-02 10:20",
                    "2024-01-02 11:00",
                ]
            ),
            "r_multiple": [1.0, -1.0, 0.5, None, 0.25],
            "level_names": [
                "pdHigh|VWAP_rolling_1h",
                "VWAP_rolling_1h|pdHigh",
                "pdHigh|VWAP_rolling_1h|pdPOC",
                "",
                "pdHigh",
            ],
            "trigger": ["touch", "touch", "touch", "touch", "3c"],
        }
    )
    return {
        "trades": trades,
        "equity_curve": pd.DataFrame({"trade_id": [1, 2, 3, 5], "cum_r": [1.0, 0.0, 0.5, 0.75]}),
        "trade_summary": {"trade_count": 4},
        "signal_settings": {
            "confluence_mode": "anchor_rules",
            "anchor_level": "pdHigh",
        },
        # Intentionally stale vs signal_settings — export must prefer signal_settings.
        "setup_config": {
            "confluence_mode": "global_cluster",
            "anchor_level": "WRONG",
        },
    }


def test_confluence_combo_bundle_omitted_without_level_names():
    """Old / non-combo backtests must not attach the optional section."""
    state = {
        "trades": pd.DataFrame({"trade_id": [1], "r_multiple": [1.0]}),
        "equity_curve": pd.DataFrame({"trade_id": [1], "cum_r": [1.0]}),
        "trade_summary": {"trade_count": 1},
    }
    bundle = build_research_bundle(state)
    names = _bundle_names(bundle)
    manifest = _manifest(bundle)
    assert "confluence_combo_summary.json" not in names
    assert manifest["included"].get("confluence_combo") is not True
    assert manifest["bundle_schema_version"] == 1


def test_confluence_combo_bundle_roundtrip_json_and_parquets():
    """Export recomputes from trades; import restores managed research keys."""
    state = _confluence_combo_session_state()
    bundle = build_research_bundle(state)
    names = _bundle_names(bundle)
    manifest = _manifest(bundle)

    assert manifest["bundle_schema_version"] == 1
    assert manifest["included"].get("confluence_combo") is True
    assert "confluence_combo_summary.json" in names
    assert "confluence_by_exact_combo.parquet" in names
    assert "confluence_by_level_count.parquet" in names
    assert "confluence_by_membership.parquet" in names
    assert "confluence_by_pairs.parquet" in names

    loaded = load_research_bundle(bundle)
    summary = loaded["session_values"]["confluence_combo_summary"]
    assert summary["available"] is True
    assert summary["kind"] == "confluence_combo_summary"
    assert summary["schema_version"] == 1
    assert summary["confluence_mode"] == "anchor_rules"
    assert summary["anchor_level"] == "pdHigh"
    assert summary["pair_mode"] == "anchor_partner"
    assert summary["nonempty_combo_trade_count"] == 4

    exact = loaded["session_values"]["confluence_by_exact_combo"]
    assert isinstance(exact, pd.DataFrame)
    assert not exact.empty
    assert "exact_combo_key" in exact.columns

    restored: dict = {}
    apply_research_bundle_to_session(loaded, restored)
    assert restored["confluence_combo_summary"]["available"] is True
    assert "confluence_by_exact_combo" in restored


def test_confluence_combo_missing_optional_parquet_does_not_fail_load():
    """Included section requires JSON only; missing parquet siblings are OK."""
    state = _confluence_combo_session_state()
    bundle = build_research_bundle(state)
    # Drop optional parquet siblings; keep required JSON + manifest.
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle), "r") as src, zipfile.ZipFile(output, "w") as dst:
        for name in src.namelist():
            if name.endswith(".parquet") and name.startswith("confluence_by_"):
                continue
            dst.writestr(name, src.read(name))

    loaded = load_research_bundle(output.getvalue())
    assert loaded["manifest"]["included"]["confluence_combo"] is True
    assert loaded["session_values"]["confluence_combo_summary"]["available"] is True
    assert "confluence_by_exact_combo" not in loaded["session_values"]
    assert "confluence_by_pairs" not in loaded["session_values"]


def test_old_bundle_without_confluence_combo_still_imports():
    """Bundles that never had the section continue to load unchanged."""
    bundle = build_research_bundle({"data": _dataset_df(), "dataset_id": "old"})
    loaded = load_research_bundle(bundle)
    assert loaded["manifest"]["included"].get("confluence_combo") is not True
    assert "confluence_combo_summary" not in loaded["session_values"]
    assert "data" in loaded["session_values"]


def test_confluence_combo_siblings_excluded_from_canonical_bundle_hash():
    """Derived combo siblings must not force a GOLDEN_REGEN bundle-hash bump."""
    base_state = _confluence_combo_session_state()
    with_combo = build_research_bundle(base_state)
    assert _manifest(with_combo)["included"].get("confluence_combo") is True
    assert "confluence_combo_summary.json" in _bundle_names(with_combo)

    # Same logical backtest without optional combo files (rewrite zip).
    # Only strip combo siblings — never confluence_zones.parquet.
    combo_files = {
        "confluence_combo_summary.json",
        "confluence_by_exact_combo.parquet",
        "confluence_by_level_count.parquet",
        "confluence_by_membership.parquet",
        "confluence_by_pairs.parquet",
    }
    stripped = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(with_combo), "r") as src, zipfile.ZipFile(stripped, "w") as dst:
        for name in src.namelist():
            if name in combo_files:
                continue
            if name == "manifest.json":
                manifest = json.loads(src.read(name).decode("utf-8"))
                manifest.get("included", {}).pop("confluence_combo", None)
                keys = [
                    key
                    for key in manifest.get("session_keys", [])
                    if key
                    not in {
                        "confluence_combo_summary",
                        "confluence_by_exact_combo",
                        "confluence_by_level_count",
                        "confluence_by_membership",
                        "confluence_by_pairs",
                    }
                ]
                manifest["session_keys"] = keys
                dst.writestr(name, json.dumps(manifest))
            else:
                dst.writestr(name, src.read(name))

    assert canonical_bundle_hash(with_combo) == canonical_bundle_hash(stripped.getvalue())


def test_confluence_combo_level_count_unknown_bucket_parquet_safe():
    """Mixed int/(unknown) View-C buckets must not crash parquet export."""
    state = _confluence_combo_session_state()
    # Empty names with valid R → "(unknown)" alongside integer buckets.
    state["trades"] = pd.DataFrame(
        {
            "trade_id": [1, 2, 3],
            "entry_timestamp": pd.to_datetime(
                ["2024-01-02 09:31", "2024-01-02 09:40", "2024-01-02 10:00"]
            ),
            "r_multiple": [1.0, -0.5, 0.25],
            "level_names": ["A|B", "", "A"],
            "trigger": ["touch", "touch", "3c"],
        }
    )
    state["equity_curve"] = pd.DataFrame({"trade_id": [1, 2, 3], "cum_r": [1.0, 0.5, 0.75]})
    bundle = build_research_bundle(state)
    assert "confluence_by_level_count.parquet" in _bundle_names(bundle)
    loaded = load_research_bundle(bundle)
    buckets = set(loaded["session_values"]["confluence_by_level_count"]["level_count_bucket"])
    assert "(unknown)" in buckets
    assert "2" in buckets or 2 in buckets


def test_confluence_combo_omitted_without_backtest_section():
    """Trades without equity must not orphan combo siblings (no trades.parquet)."""
    state = _confluence_combo_session_state()
    del state["equity_curve"]
    bundle = build_research_bundle(state)
    names = _bundle_names(bundle)
    assert "trades.parquet" not in names
    assert "confluence_combo_summary.json" not in names
    assert _manifest(bundle)["included"].get("confluence_combo") is not True


def test_confluence_combo_restored_summary_preserves_mode_on_recompute():
    """After import without signal_settings, recompute uses baked summary identity."""
    from thesistester.reporting import build_confluence_combo_report_block

    state = _confluence_combo_session_state()
    bundle = build_research_bundle(state)
    loaded = load_research_bundle(bundle)
    restored: dict = {}
    apply_research_bundle_to_session(loaded, restored)
    # Simulate a session that kept trades but lost ephemeral signal_settings.
    restored.pop("signal_settings", None)
    restored.pop("setup_config", None)
    block = build_confluence_combo_report_block(restored)
    assert block is not None
    assert block["confluence_mode"] == "anchor_rules"
    assert block["anchor_level"] == "pdHigh"
    assert block["pair_mode"] == "anchor_partner"


def test_unknown_zip_files_are_ignored():
    bundle_bytes = build_research_bundle({"data": _dataset_df()})
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as src, zipfile.ZipFile(output, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr("random.txt", "ignore me")

    loaded = load_research_bundle(output.getvalue())
    assert "data" in loaded["session_values"]


def test_path_traversal_member_is_ignored():
    """QI-06-09 / QI-6 §9: traversal members are not extracted; known names load."""
    bundle_bytes = build_research_bundle({"data": _dataset_df()})
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as src, zipfile.ZipFile(output, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr("../outside.parquet", b"PWN")
        dst.writestr("padding.bin", b"\x00" * 2048)

    loaded = load_research_bundle(output.getvalue())
    assert "data" in loaded["session_values"]
    restored: dict = {}
    apply_research_bundle_to_session(loaded, restored)
    assert "../outside.parquet" not in restored
    assert "padding.bin" not in restored
    assert "data" in restored


def _track_zip_reads(monkeypatch) -> list[str]:
    read_names: list[str] = []
    real_read = zipfile.ZipFile.read

    def _tracked_read(self, name, *args, **kwargs):
        read_names.append(str(name))
        return real_read(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", _tracked_read)
    return read_names


def test_oversized_named_member_rejected_before_read(monkeypatch):
    """QI-06-09: ZipInfo.file_size over cap → ValueError before ZipFile.read."""
    bundle_bytes = build_research_bundle({"data": _dataset_df()})
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as zf:
        manifest_size = zf.getinfo("manifest.json").file_size
        parquet_size = zf.getinfo("dataset.parquet").file_size
    assert parquet_size > manifest_size

    monkeypatch.setattr(research_bundle, "MAX_BUNDLE_MEMBER_BYTES", manifest_size)
    read_names = _track_zip_reads(monkeypatch)
    with pytest.raises(ValueError, match="size cap"):
        load_research_bundle(bundle_bytes)
    assert "dataset.parquet" not in read_names


def test_negative_declared_member_size_rejected_before_read(monkeypatch):
    """QI-06-09: attacker-controlled negative ZipInfo.file_size is fail-closed."""
    bundle_bytes = build_research_bundle({"data": _dataset_df()})
    real_getinfo = zipfile.ZipFile.getinfo

    def _lying_getinfo(self, name):
        info = real_getinfo(self, name)
        if name == "dataset.parquet":
            info.file_size = -1
        return info

    monkeypatch.setattr(zipfile.ZipFile, "getinfo", _lying_getinfo)
    read_names = _track_zip_reads(monkeypatch)
    with pytest.raises(ValueError, match="invalid size"):
        load_research_bundle(bundle_bytes)
    assert "dataset.parquet" not in read_names


def test_oversized_upload_rejected_before_zip_open(monkeypatch):
    monkeypatch.setattr(research_bundle, "MAX_BUNDLE_UPLOAD_BYTES", 16)

    def _boom(*_args, **_kwargs):
        raise AssertionError("ZipFile must not open an oversize upload")

    monkeypatch.setattr(research_bundle.zipfile, "ZipFile", _boom)
    with pytest.raises(ValueError, match="upload cap"):
        load_research_bundle(b"PK\x03\x04" + b"x" * 32)


def test_declared_upload_size_rejects_before_getvalue(monkeypatch):
    """Streamlit-style .size over cap must not copy bytes via getvalue()."""

    class _SizedUpload:
        size = 32

        def getvalue(self):
            raise AssertionError("getvalue must not run after size-cap reject")

    monkeypatch.setattr(research_bundle, "MAX_BUNDLE_UPLOAD_BYTES", 16)
    with pytest.raises(ValueError, match="upload cap"):
        load_research_bundle(_SizedUpload())


def test_getvalue_non_bytes_is_typed_error():
    class _NotBytes:
        def getvalue(self):
            return "not-bytes"

    with pytest.raises(ValueError, match="must be bytes"):
        load_research_bundle(_NotBytes())


def test_peek_path_respects_upload_cap_before_read_bytes(tmp_path, monkeypatch):
    """QI-06-09: peek Path must not read_bytes when st_size is over the cap."""
    path = tmp_path / "oversize.research.zip"
    path.write_bytes(b"PK\x03\x04" + b"x" * 32)
    monkeypatch.setattr(research_bundle, "MAX_BUNDLE_UPLOAD_BYTES", 16)

    def _boom(self):
        raise AssertionError("read_bytes must not run after size-cap reject")

    monkeypatch.setattr(Path, "read_bytes", _boom)
    assert peek_research_identity(path) is None
    assert peek_research_identity(b"PK\x03\x04" + b"x" * 32) is None


def test_honest_bundle_fixture_still_loads():
    """QI-06-09: honest export/import stays under the default caps."""
    bundle_bytes = build_research_bundle({"data": _dataset_df()})
    loaded = load_research_bundle(bundle_bytes)
    assert "data" in loaded["session_values"]
    assert len(loaded["session_values"]["data"]) == 3


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


# ---------------------------------------------------------------------------
# AH4 — leftover keys + dataset-less bootstrap (H1)
# ---------------------------------------------------------------------------


def _leftover_otf_summary(*, rejected: int = 12) -> dict:
    return {
        "otf_filter_enabled": True,
        "otf_algorithm_version": "otf-v1",
        "otf_config_hash": "a" * 64,
        "otf_filter_config": {"enabled": True, "timeframes": ["15m"]},
        "candidate_signal_count": 20,
        "otf_accepted_signal_count": 20 - rejected,
        "otf_rejected_signal_count": rejected,
        "rejection_rate": rejected / 20,
    }


def test_ah4_p1_leftover_otf_summary_cleared_on_cli_zip_without_otf():
    """Leftover 12-rejected summary must not survive a zip with no OTF section."""
    session = {
        "otf_filter_summary": _leftover_otf_summary(rejected=12),
        "otf_filter_result": object(),
        # Report falls through to grid when backtest keys are gone.
        "grid_otf_filter": _leftover_otf_summary(rejected=12),
        "otf_rejected_signals": pd.DataFrame({"signal_id": list(range(12))}),
        "otf_candidate_signals": pd.DataFrame({"signal_id": [1]}),
        "otf_accepted_signals": pd.DataFrame({"signal_id": [1]}),
    }
    bundle_bytes = build_research_bundle(
        {
            "trades": pd.DataFrame({"trade_id": [1], "r_multiple": [1.0]}),
            "equity_curve": pd.DataFrame({"trade_id": [1], "cum_r": [1.0]}),
            "trade_summary": {"trade_count": 1},
        }
    )
    apply_research_bundle_to_session(load_research_bundle(bundle_bytes), session)
    assert "otf_filter_summary" not in session
    assert "otf_filter_result" not in session
    assert "grid_otf_filter" not in session
    assert "otf_rejected_signals" not in session
    assert "otf_candidate_signals" not in session
    assert "otf_accepted_signals" not in session
    meta = build_otf_filter_metadata(session)
    assert meta["available"] is False
    assert meta["rejected_signal_count"] is None


def test_ah4_p1_bundle_owned_otf_export_outranks_leftover_summary():
    session = {"otf_filter_summary": _leftover_otf_summary(rejected=12)}
    apply_research_bundle_to_session(
        {
            "session_values": {
                "backtest_otf_filter": {
                    "otf_filter_enabled": False,
                    "otf_rejected_signal_count": 0,
                    "otf_accepted_signal_count": 0,
                    "candidate_signal_count": 0,
                }
            }
        },
        session,
    )
    assert "otf_filter_summary" not in session
    meta = build_otf_filter_metadata(session)
    assert meta["available"] is True
    assert meta["enabled"] is False
    assert meta["rejected_signal_count"] == 0


def test_ah4_p2_focused_trades_and_setup_config_cleared_when_absent():
    session = {
        "focused_trades": pd.DataFrame({"trade_id": [99]}),
        "focused_equity_curve": pd.DataFrame({"trade_id": [99], "cum_r": [1.0]}),
        "setup_config": {"name": "leftover-setup", "tolerance_ticks": 99},
        "data": _dataset_df(),
        "dataset_id": "dataset-keep",
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
    }
    bundle_bytes = build_research_bundle(
        {
            "data": _dataset_df(),
            "dataset_id": "dataset-keep",
            "instrument": "ES",
            "base_interval": "1min",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
        }
    )
    apply_research_bundle_to_session(load_research_bundle(bundle_bytes), session)
    assert "focused_trades" not in session
    assert "focused_equity_curve" not in session
    assert "setup_config" not in session
    assert "data" in session


def test_ah4_p3_dataset_less_import_skips_saved_dataset_bootstrap():
    saved_a = _dataset_df()
    session: dict = {
        "trades": pd.DataFrame({"trade_id": [2]}),
    }
    bundle_bytes = build_research_bundle(
        {
            "trades": pd.DataFrame({"trade_id": [1], "r_multiple": [0.5]}),
            "equity_curve": pd.DataFrame({"trade_id": [1], "cum_r": [0.5]}),
            "trade_summary": {"trade_count": 1},
        }
    )
    apply_research_bundle_to_session(load_research_bundle(bundle_bytes), session)
    assert "data" not in session
    assert session[BUNDLE_IMPORT_OMITTED_DATA_KEY] is True
    assert should_skip_dataset_bootstrap(session) is True

    def _bootstrap_would_refill_a() -> None:
        session["data"] = saved_a

    if not should_skip_dataset_bootstrap(session):
        _bootstrap_would_refill_a()
    assert "data" not in session

    complete = build_research_bundle(
        {
            "data": _dataset_df(),
            "dataset_id": "bundle-data",
            "instrument": "ES",
            "base_interval": "1min",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
        }
    )
    apply_research_bundle_to_session(load_research_bundle(complete), session)
    assert session[BUNDLE_IMPORT_OMITTED_DATA_KEY] is False
    assert should_skip_dataset_bootstrap(session) is False
    assert "data" in session
    pd.testing.assert_frame_equal(session["data"], _dataset_df())


def test_ah4_p4_nonce_invalidation_still_set():
    session: dict = {}
    apply_research_bundle_to_session(
        load_research_bundle(build_research_bundle({"data": _dataset_df()})),
        session,
    )
    assert session[DATA_PAGE_INVALIDATE_SOURCE_KEY] is True


def test_ah4_p5_page_12_stays_schema_only():
    source = Path("pages/12_Research_Bundles.py").read_text(encoding="utf-8")
    assert "canonical_bundle_hash" not in source
    assert "should_skip_dataset_bootstrap" in source
    assert "bootstrap_active_saved_dataset()" in source


def test_page_12_labels_three_integrity_bars_without_hash_gate():
    """QI-09-10 / QI-06-06 residual: page 12 names the three bars; no hash symbol."""
    source = Path("pages/12_Research_Bundles.py").read_text(encoding="utf-8")
    assert "schema-only" in source
    assert "hash-fail-closed" in source
    assert "open-exact" in source
    assert "canonical_bundle_hash" not in source


_QI0603_CLEAR_ONLY_KEYS = (
    "otf_validation_matrix",
    "otf_validation_config",
    "otf_validation_summary",
    "skipped_signals",
    "direction_collision_diagnostic",
)
_RESEARCH_BUNDLE_SOURCE = Path("thesistester/research_bundle.py").read_text(encoding="utf-8")


def _meta_key_collections() -> dict[str, object]:
    """Every ``_*_META_KEYS`` tuple/list on the bundle module (H1 parallel lists)."""
    return {
        name: getattr(research_bundle, name)
        for name in dir(research_bundle)
        if name.endswith("_META_KEYS")
    }


def _json_contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        if key in value:
            return True
        return any(_json_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_json_contains_key(item, key) for item in value)
    return False


_QI1001_CLEAR_ONLY_KEYS = ("display_timezone",)
_QI1001_LEFTOVER_DISPLAY_TZ = "UTC"
_AH4_RESIDUAL_CLEAR_ONLY_KEYS = (*_QI0603_CLEAR_ONLY_KEYS, *_QI1001_CLEAR_ONLY_KEYS)


def _assert_qi0603_not_exported_or_hashed(bundle_bytes: bytes) -> None:
    """QI-06-03 / A-7 + QI-10-01 / A-8: residual keys are not zip members, META keys, or hashed."""
    for key in _AH4_RESIDUAL_CLEAR_ONLY_KEYS:
        assert key in _MANAGED_RESEARCH_KEYS, f"{key} missing from _MANAGED_RESEARCH_KEYS"
        for name, collection in _meta_key_collections().items():
            assert key not in collection, f"{key} leaked into {name}"
        assert key not in _KNOWN_FILES
        assert f"{key}.json" not in _KNOWN_FILES
        assert f"{key}.parquet" not in _KNOWN_FILES
        for filename in _KNOWN_FILES:
            assert key not in filename, f"{key} leaked into _KNOWN_FILES member {filename}"
        for filename in _CANONICAL_HASH_EXCLUDED_FILES:
            assert key not in filename, f"{key} hash-excluded ({filename}) can hide an export"
        for section, required in research_bundle._SECTION_REQUIRED_FILES.items():
            assert key not in required, f"{key} leaked into _SECTION_REQUIRED_FILES[{section}]"
            assert all(key not in filename for filename in required)

    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as archive:
        names = archive.namelist()
        for key in _AH4_RESIDUAL_CLEAR_ONLY_KEYS:
            assert all(key not in name for name in names), f"{key} leaked into zip member names"
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        session_keys = manifest.get("session_keys") or []
        for key in _AH4_RESIDUAL_CLEAR_ONLY_KEYS:
            assert key not in session_keys, f"{key} leaked into hashed manifest session_keys"
        for name in names:
            if not name.endswith(".json"):
                continue
            payload = json.loads(archive.read(name).decode("utf-8"))
            for key in _AH4_RESIDUAL_CLEAR_ONLY_KEYS:
                assert not _json_contains_key(payload, key), f"{key} leaked into {name}"

    loaded = load_research_bundle(bundle_bytes)
    for key in _AH4_RESIDUAL_CLEAR_ONLY_KEYS:
        assert key not in loaded["session_values"], f"{key} restored from zip session_values"


def _assert_qi0603_leftovers_cleared(session: dict) -> None:
    from thesistester.config import TIMEZONE_OPTIONS

    for key in _QI0603_CLEAR_ONLY_KEYS:
        assert key not in session, f"{key} leftover survived apply"
    # QI-10-01 / A-8: leftover UTC is reset, not sticky. Backtest-only zips omit
    # exchange_timezone, so reset binds TIMEZONE_OPTIONS[0]. Leftover must not
    # already equal the fallback or this probe is vacuous.
    assert _QI1001_LEFTOVER_DISPLAY_TZ != TIMEZONE_OPTIONS[0]
    assert session["display_timezone"] == TIMEZONE_OPTIONS[0]


def _const_str_tuple(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.Tuple):
        return set()
    return {
        elt.value
        for elt in node.elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    }


def _is_name_target(node: ast.AST, name: str) -> bool:
    if isinstance(node, ast.Assign):
        return any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    return (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == name
    )


def _bundle_key_registry_assign(tree: ast.AST) -> ast.Assign | ast.AnnAssign | None:
    if not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        if _is_name_target(node, "BUNDLE_KEY_REGISTRY"):
            return node
    return None


def _bundle_key_spec_calls(tree: ast.AST) -> list[ast.Call]:
    """``BundleKeySpec`` calls on the ``BUNDLE_KEY_REGISTRY`` assignment only.

    A dead helper / unused call must not bind A-7 leftovers (A-1/A-6 class).
    """
    registry = _bundle_key_registry_assign(tree)
    if registry is None:
        return []
    return [
        node
        for node in ast.walk(registry)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "BundleKeySpec"
    ]


def _call_kw(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _managed_registry_session_key_literals(source: str) -> set[str]:
    """``session_keys`` string Constants on managed ``BundleKeySpec`` rows."""
    tree = ast.parse(source)
    literals: set[str] = set()
    for call in _bundle_key_spec_calls(tree):
        managed = _call_kw(call, "managed")
        if not (isinstance(managed, ast.Constant) and managed.value is True):
            continue
        literals.update(_const_str_tuple(_call_kw(call, "session_keys")))
    return literals


def _managed_set_string_literals(source: str) -> set[str]:
    """String literals that bind residuals to ``_MANAGED_RESEARCH_KEYS``.

    C-7 generates the set from ``BUNDLE_KEY_REGISTRY``. A set display still
    binds its Constants; a set-comp is allowed only when the registry rows
    carry the residual keys as AST string Constants (not comments).
    """
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "_MANAGED_RESEARCH_KEYS" for t in node.targets
        ):
            continue
        if isinstance(node.value, ast.Set):
            return {
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }
        if isinstance(node.value, ast.SetComp):
            return set()
        # D-1: frozenset(APPLY_CLEAR_KEYS). Residuals bind on the
        # research-key registry + C-7 BUNDLE_KEY_REGISTRY session_keys.
        if isinstance(node.value, ast.Call):
            func = node.value.func
            if (
                isinstance(func, ast.Name)
                and func.id == "frozenset"
                and node.value.args
                and isinstance(node.value.args[0], ast.Name)
                and node.value.args[0].id == "APPLY_CLEAR_KEYS"
            ):
                return set()
        raise AssertionError("_MANAGED_RESEARCH_KEYS must be a set display")
    raise AssertionError("missing _MANAGED_RESEARCH_KEYS assignment")


def _assert_qi0603_managed_set_literals(source: str) -> None:
    """AST-bind the residual keys to managed-set / registry literals.

    File-level / comment needles false-green — A-1/A-6 class.
    """
    literals = _managed_set_string_literals(source) | _managed_registry_session_key_literals(source)
    missing = [key for key in _AH4_RESIDUAL_CLEAR_ONLY_KEYS if key not in literals]
    assert missing == [], f"_MANAGED_RESEARCH_KEYS set missing literals {missing}"


def _function_def(tree: ast.AST, name: str) -> ast.FunctionDef:
    if not isinstance(tree, ast.Module):
        raise AssertionError("expected a module AST")
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing module-level def {name}")


def _iter_direct_stmts(stmts: list[ast.stmt]):
    """Walk statements excluding nested function/class defs (A-1/A-6 class)."""
    stack = list(reversed(stmts))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield node
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def _iter_direct_body(fn: ast.FunctionDef):
    yield from _iter_direct_stmts(fn.body)


def _is_reset_display_timezone_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "reset_display_timezone":
        return True
    return isinstance(func, ast.Attribute) and func.attr == "reset_display_timezone"


def _iterates_session_values_items(node: ast.For) -> bool:
    it = node.iter
    return (
        isinstance(it, ast.Call)
        and isinstance(it.func, ast.Attribute)
        and it.func.attr == "items"
        and isinstance(it.func.value, ast.Name)
        and it.func.value.id == "session_values"
    )


def _reset_binds_restored_exchange_timezone(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg != "exchange_timezone":
            continue
        val = kw.value
        if (
            isinstance(val, ast.Call)
            and isinstance(val.func, ast.Attribute)
            and val.func.attr == "get"
            and val.args
            and isinstance(val.args[0], ast.Constant)
            and val.args[0].value == "exchange_timezone"
        ):
            return True
    return False


def _assert_apply_resets_display_timezone(source: str) -> None:
    """Apply must reset leftover TZ after restore (comment / ensure / nested fail closed)."""
    tree = ast.parse(source)
    fn = _function_def(tree, "apply_research_bundle_to_session")
    restore_end: int | None = None
    reset_line: int | None = None
    reset_binds = False
    for node in _iter_direct_body(fn):
        if isinstance(node, ast.For) and _iterates_session_values_items(node):
            restore_end = getattr(node, "end_lineno", node.lineno)
        if _is_reset_display_timezone_call(node):
            reset_line = node.lineno
            reset_binds = _reset_binds_restored_exchange_timezone(node)
    if reset_line is None:
        raise AssertionError("apply_research_bundle_to_session must call reset_display_timezone")
    if not reset_binds:
        raise AssertionError("reset_display_timezone must bind restored exchange_timezone")
    if restore_end is None:
        raise AssertionError("apply must restore session_values before timezone reset")
    if reset_line <= restore_end:
        raise AssertionError("reset_display_timezone must run after session_values restore")


def _assert_apply_pops_managed_set(source: str) -> None:
    """Apply must ``pop`` keys from ``_MANAGED_RESEARCH_KEYS`` (not a comment / other set)."""
    tree = ast.parse(source)
    fn = _function_def(tree, "apply_research_bundle_to_session")
    for node in _iter_direct_body(fn):
        if not isinstance(node, ast.For):
            continue
        if not isinstance(node.iter, ast.Name) or node.iter.id != "_MANAGED_RESEARCH_KEYS":
            continue
        for child in _iter_direct_stmts(node.body):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr == "pop":
                return
        raise AssertionError("apply For _MANAGED_RESEARCH_KEYS must pop each key")
    raise AssertionError("apply_research_bundle_to_session must iterate _MANAGED_RESEARCH_KEYS")


def test_ah4_p6_qi0603_residual_leftovers_cleared_on_zip_without_those_sections():
    """QI-06-03 / A-7: leftover OTF-validation / skip / DA1 keys do not survive apply."""
    leftover_trades = pd.DataFrame({"trade_id": [99], "r_multiple": [9.9]})
    session = {
        "otf_validation_matrix": pd.DataFrame({"train_expectancy_r": [9.9]}),
        "otf_validation_config": {"train_fraction": 0.5, "leftover": True},
        "otf_validation_summary": {"selected_train_config": "leftover"},
        "skipped_signals": pd.DataFrame({"signal_id": [1], "skip_reason": ["leftover"]}),
        "direction_collision_diagnostic": {"candidate_pairs": 99, "policy": "legacy"},
        "trades": leftover_trades,
        "display_timezone": _QI1001_LEFTOVER_DISPLAY_TZ,
    }
    bundle_state = {
        "trades": pd.DataFrame({"trade_id": [1], "r_multiple": [1.0]}),
        "equity_curve": pd.DataFrame({"trade_id": [1], "cum_r": [1.0]}),
        "trade_summary": {"trade_count": 1},
    }
    with_leftovers = {
        **bundle_state,
        "otf_validation_matrix": session["otf_validation_matrix"],
        "otf_validation_config": session["otf_validation_config"],
        "otf_validation_summary": session["otf_validation_summary"],
        "skipped_signals": session["skipped_signals"],
        "direction_collision_diagnostic": session["direction_collision_diagnostic"],
        "display_timezone": _QI1001_LEFTOVER_DISPLAY_TZ,
    }
    leftover_bundle = build_research_bundle(with_leftovers)
    baseline_bundle = build_research_bundle(bundle_state)
    assert canonical_bundle_hash(leftover_bundle) == canonical_bundle_hash(baseline_bundle)
    _assert_qi0603_not_exported_or_hashed(leftover_bundle)
    _assert_qi0603_not_exported_or_hashed(baseline_bundle)

    pre_artifact = build_research_artifact(session)
    pre_matrix = (pre_artifact.get("tables") or {}).get("otf_validation_matrix") or []
    assert pre_matrix, "leftover probe is vacuous unless leftover matrix is on the report surface"
    assert any(isinstance(row, dict) and row.get("train_expectancy_r") == 9.9 for row in pre_matrix)
    assert (pre_artifact.get("otf_validation") or {}).get("available") is True

    apply_research_bundle_to_session(load_research_bundle(baseline_bundle), session)
    _assert_qi0603_leftovers_cleared(session)
    assert session["trades"]["trade_id"].tolist() == [1]

    post_artifact = build_research_artifact(session)
    post_matrix = (post_artifact.get("tables") or {}).get("otf_validation_matrix") or []
    assert post_matrix == []
    assert "otf_validation" not in post_artifact


# Frozen C-7 / QI-06-04 membership. Additive-only: a dropped key is a hash/H1 defect.
_FROZEN_MANAGED_RESEARCH_KEYS = frozenset(
    {
        "backtest_config",
        "backtest_execution_costs",
        "backtest_exit_management_diagnostic",
        "backtest_exit_management_policy",
        "backtest_intrabar_diagnostic",
        "backtest_intrabar_policy",
        "backtest_otf_filter",
        "backtest_session_exit_policy",
        "base_interval",
        "best_grid_result",
        "cache_provenance",
        "confluence_by_exact_combo",
        "confluence_by_level_count",
        "confluence_by_membership",
        "confluence_by_pairs",
        "confluence_combo_summary",
        "confluence_zones",
        "data",
        "data_identity",
        "dataset_id",
        "direction_collision_diagnostic",
        "display_timezone",
        "entry_window",
        "entry_window_armed",
        "entry_window_promote_provenance",
        "equity_curve",
        "exchange_timezone",
        "excursion_calibration_grid",
        "excursion_config",
        "excursion_grouped_summary",
        "excursion_quadrant_summary",
        "excursion_summary",
        "execution_origin",
        "experiment_identity",
        "exposure_policy",
        "focus_entry_window",
        "focus_provenance",
        "focused_equity_curve",
        "focused_trade_summary",
        "focused_trades",
        "format_profile",
        "grid_entry_window",
        "grid_exit_management_policy",
        "grid_intrabar_policy",
        "grid_otf_filter",
        "grid_results",
        "ingestion_provenance",
        "instrument",
        "last_signal_setup",
        "levels",
        "levels_data_fingerprint",
        "levels_identity",
        "levels_settings",
        "monte_carlo_config",
        "monte_carlo_summary",
        "naked_flags",
        "noise_config",
        "noise_summary",
        "otf_accepted_signals",
        "otf_candidate_signals",
        "otf_filter_result",
        "otf_filter_summary",
        "otf_rejected_signals",
        "otf_validation_config",
        "otf_validation_matrix",
        "otf_validation_summary",
        "overfitting_config",
        "overfitting_summary",
        "portfolio_config",
        "portfolio_correlation",
        "portfolio_drawdown_correlation",
        "portfolio_equity_curve",
        "portfolio_marginal_contribution",
        "portfolio_setup_inputs",
        "portfolio_skipped_trades",
        "portfolio_summary",
        "portfolio_trades",
        "sensitivity_config",
        "sensitivity_summary",
        "session_levels",
        "setup_config",
        "signal_context",
        "signal_settings",
        "signal_settings_hash",
        "signals",
        "skipped_signals",
        "source_timezone",
        "subtimeframe_data",
        "subtimeframe_fallback_parent_bars",
        "subtimeframe_format_profile",
        "subtimeframe_interval",
        "time_bucketed_trades",
        "time_grouped_summary",
        "trade_summary",
        "trades",
        "validation_summary",
        "walk_forward_config",
        "walk_forward_oos_trades",
        "walk_forward_otf_filter",
        "walk_forward_results",
        "walk_forward_stitched_equity",
        "walk_forward_summary",
        "walk_forward_warnings",
        "wfa_matrix",
        "wfa_matrix_config",
    }
)
_FROZEN_KNOWN_FILES = frozenset(
    {
        "best_grid_result.json",
        "confluence_by_exact_combo.parquet",
        "confluence_by_level_count.parquet",
        "confluence_by_membership.parquet",
        "confluence_by_pairs.parquet",
        "confluence_combo_summary.json",
        "confluence_zones.parquet",
        "dataset.parquet",
        "dataset_meta.json",
        "equity_curve.parquet",
        "excursion_calibration_grid.parquet",
        "excursion_grouped_summary.parquet",
        "excursion_quadrant_summary.parquet",
        "excursion_summary.json",
        "grid_results.parquet",
        "levels.parquet",
        "levels_meta.json",
        "manifest.json",
        "monte_carlo_summary.json",
        "naked_flags.parquet",
        "noise_summary.json",
        "overfitting_summary.json",
        "portfolio_correlation.parquet",
        "portfolio_drawdown_correlation.parquet",
        "portfolio_equity_curve.parquet",
        "portfolio_marginal_contribution.parquet",
        "portfolio_skipped_trades.parquet",
        "portfolio_summary.json",
        "portfolio_trades.parquet",
        "research_identity.json",
        "sensitivity_summary.json",
        "session_levels.parquet",
        "signals.parquet",
        "signals_meta.json",
        "subtimeframe_data.parquet",
        "subtimeframe_meta.json",
        "trade_summary.json",
        "trades.parquet",
        "validation_summary.json",
        "walk_forward_meta.json",
        "walk_forward_oos_trades.parquet",
        "walk_forward_results.parquet",
        "walk_forward_stitched_equity.parquet",
        "wfa_matrix.parquet",
    }
)
_FROZEN_HASH_EXCLUDED_FILES = frozenset(
    {
        "confluence_combo_summary.json",
        "confluence_by_exact_combo.parquet",
        "confluence_by_level_count.parquet",
        "confluence_by_membership.parquet",
        "confluence_by_pairs.parquet",
    }
)
_FROZEN_REQUIRED_SECTIONS = (
    "dataset",
    "levels",
    "signals",
    "backtest",
    "grid",
    "validation",
    "walk_forward",
    "excursion",
    "monte_carlo",
    "noise",
    "overfitting",
    "sensitivity",
    "portfolio",
    "confluence_combo",
)
_FROZEN_SECTION_REQUIRED_FILES = {
    "dataset": ("dataset.parquet", "dataset_meta.json"),
    "levels": ("levels.parquet", "session_levels.parquet", "levels_meta.json"),
    "signals": (
        "signals.parquet",
        "confluence_zones.parquet",
        "naked_flags.parquet",
        "signals_meta.json",
    ),
    "backtest": ("trades.parquet", "trade_summary.json", "equity_curve.parquet"),
    "grid": ("grid_results.parquet", "best_grid_result.json"),
    "validation": ("validation_summary.json",),
    "walk_forward": ("walk_forward_results.parquet", "walk_forward_meta.json"),
    "excursion": ("excursion_summary.json",),
    "monte_carlo": ("monte_carlo_summary.json",),
    "noise": ("noise_summary.json",),
    "overfitting": ("overfitting_summary.json",),
    "sensitivity": ("sensitivity_summary.json",),
    "portfolio": ("portfolio_summary.json", "portfolio_trades.parquet"),
    "confluence_combo": ("confluence_combo_summary.json",),
}


def _for_iterates_name(node: ast.For, name: str) -> bool:
    return isinstance(node.iter, ast.Name) and node.iter.id == name


def _loop_calls_section_io(loop: ast.For, attr: str) -> bool:
    for child in ast.walk(loop):
        if isinstance(child, ast.Attribute) and child.attr == attr:
            return True
    return False


def _loop_gates_included_section(loop: ast.For) -> bool:
    for child in ast.walk(loop):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if not (isinstance(func, ast.Attribute) and func.attr == "get"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "included"):
            continue
        if not child.args:
            continue
        arg0 = child.args[0]
        if (
            isinstance(arg0, ast.Attribute)
            and arg0.attr == "section"
            and isinstance(arg0.value, ast.Name)
        ):
            return True
    return False


def _canonical_hash_exclusion_assigns(source: str) -> list[ast.Assign]:
    tree = ast.parse(source)
    if not isinstance(tree, ast.Module):
        raise AssertionError("expected a module AST")
    return [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_CANONICAL_HASH_EXCLUDED_FILES"
            for target in node.targets
        )
    ]


def _assert_hash_exclusions_are_registry_generated(source: str) -> None:
    """Hash exclusions must be generated from the registry (not a leftover literal set)."""
    assigns = _canonical_hash_exclusion_assigns(source)
    assert len(assigns) == 1, "_CANONICAL_HASH_EXCLUDED_FILES must have exactly one assignment"
    node = assigns[0].value
    assert isinstance(node, ast.Call), "_CANONICAL_HASH_EXCLUDED_FILES must be a frozenset call"
    func = node.func
    assert isinstance(func, ast.Name) and func.id == "frozenset"
    assert node.args, "_CANONICAL_HASH_EXCLUDED_FILES frozenset needs a generator"
    gen = node.args[0]
    assert isinstance(gen, ast.GeneratorExp), (
        "_CANONICAL_HASH_EXCLUDED_FILES must be generated, not a set display"
    )
    names = {n.id for n in ast.walk(gen) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(gen) if isinstance(n, ast.Attribute)}
    assert "BUNDLE_KEY_REGISTRY" in names
    assert "hash_exclude_files" in attrs


def _assert_bundle_walks_section_io(source: str, name: str) -> None:
    """``build`` / ``load`` must walk ``BUNDLE_SECTION_IO`` (comment needles fail-closed)."""
    fn = _function_def(ast.parse(source), name)
    attr = "build" if name == "build_research_bundle" else "load"
    fors = [node for node in ast.walk(fn) if isinstance(node, ast.For)]
    assert fors, f"{name} must walk BUNDLE_SECTION_IO"
    walked = False
    for loop in fors:
        if not _for_iterates_name(loop, "BUNDLE_SECTION_IO"):
            continue
        assert _loop_calls_section_io(loop, attr), f"{name} must call spec.{attr}"
        if name == "load_research_bundle":
            assert _loop_gates_included_section(loop), (
                "load_research_bundle must gate the walk on included.get(spec.section)"
            )
        walked = True
        break
    assert walked, f"{name} must iterate BUNDLE_SECTION_IO"


def test_bundle_key_registry_completeness():
    """C-7 / QI-06-04: generated lists match the registry; frozen membership holds."""
    assert BUNDLE_KEY_REGISTRY_NAMES == (
        *_FROZEN_REQUIRED_SECTIONS,
        "identity",
        "clear_only",
    )
    assert len(set(BUNDLE_KEY_REGISTRY_NAMES)) == len(BUNDLE_KEY_REGISTRY_NAMES)
    assert BUNDLE_SECTION_IO_NAMES == _FROZEN_REQUIRED_SECTIONS
    assert tuple(spec.section for spec in BUNDLE_SECTION_IO) == _FROZEN_REQUIRED_SECTIONS

    for spec in BUNDLE_KEY_REGISTRY:
        if spec.hashed:
            assert spec.hash_exclude_files == ()
        else:
            assert set(spec.hash_exclude_files) == set(spec.known_files)

    generated_managed = {
        key for spec in BUNDLE_KEY_REGISTRY if spec.managed for key in spec.session_keys
    }
    assert _MANAGED_RESEARCH_KEYS == generated_managed == _FROZEN_MANAGED_RESEARCH_KEYS
    assert len(_MANAGED_RESEARCH_KEYS) == 105

    generated_known = {
        "manifest.json",
        *(name for spec in BUNDLE_KEY_REGISTRY for name in spec.known_files),
    }
    assert _KNOWN_FILES == generated_known == _FROZEN_KNOWN_FILES
    assert len(_KNOWN_FILES) == 44

    generated_required = {
        spec.section: spec.required_files for spec in BUNDLE_KEY_REGISTRY if spec.required_files
    }
    assert _SECTION_REQUIRED_FILES == generated_required == _FROZEN_SECTION_REQUIRED_FILES
    assert tuple(_SECTION_REQUIRED_FILES) == _FROZEN_REQUIRED_SECTIONS

    generated_excl = frozenset(
        name for spec in BUNDLE_KEY_REGISTRY for name in spec.hash_exclude_files
    )
    assert _CANONICAL_HASH_EXCLUDED_FILES == generated_excl == _FROZEN_HASH_EXCLUDED_FILES
    _assert_hash_exclusions_are_registry_generated(_RESEARCH_BUNDLE_SOURCE)

    clear_only = next(spec for spec in BUNDLE_KEY_REGISTRY if spec.section == "clear_only")
    assert clear_only.managed is True
    assert clear_only.hashed is False
    assert clear_only.known_files == ()
    assert clear_only.required_files == ()
    assert set(_AH4_RESIDUAL_CLEAR_ONLY_KEYS) <= set(clear_only.session_keys)

    confluence = next(spec for spec in BUNDLE_KEY_REGISTRY if spec.section == "confluence_combo")
    assert confluence.hashed is False
    assert set(confluence.hash_exclude_files) == _FROZEN_HASH_EXCLUDED_FILES

    backtest = next(spec for spec in BUNDLE_KEY_REGISTRY if spec.section == "backtest")
    assert "direction_collision_diagnostic" not in backtest.meta_keys
    assert "direction_collision_diagnostic" not in backtest.session_keys

    _assert_bundle_walks_section_io(_RESEARCH_BUNDLE_SOURCE, "build_research_bundle")
    _assert_bundle_walks_section_io(_RESEARCH_BUNDLE_SOURCE, "load_research_bundle")


def test_ah4_p6_managed_set_literals_and_apply_pop_are_ast_bound():
    """QI-06-03 / A-7 + QI-10-01 / A-8: comment needles must not satisfy managed-set or apply pop."""
    _assert_qi0603_managed_set_literals(_RESEARCH_BUNDLE_SOURCE)
    _assert_apply_pops_managed_set(_RESEARCH_BUNDLE_SOURCE)
    _assert_apply_resets_display_timezone(_RESEARCH_BUNDLE_SOURCE)


def test_apply_research_bundle_resets_leftover_display_timezone_qi1001():
    """QI-10-01 / A-8: leftover UTC display TZ resets to restored exchange TZ and is not hashed."""
    from thesistester.timezone_display import (
        ensure_display_timezone,
        reset_display_timezone,
    )

    leftover = {"display_timezone": _QI1001_LEFTOVER_DISPLAY_TZ}
    assert ensure_display_timezone(leftover, exchange_timezone="Europe/Berlin") == "UTC"
    assert reset_display_timezone(leftover, exchange_timezone="Europe/Berlin") == "Europe/Berlin"
    assert leftover["display_timezone"] == "Europe/Berlin"

    session = {
        "display_timezone": _QI1001_LEFTOVER_DISPLAY_TZ,
        "focused_trades": pd.DataFrame({"trade_id": [99]}),
        "exchange_timezone": "UTC",
    }
    bundle_state = {
        "data": _dataset_df(),
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "Europe/Berlin",
    }
    leftover_bundle = build_research_bundle(
        {**bundle_state, "display_timezone": _QI1001_LEFTOVER_DISPLAY_TZ}
    )
    baseline_bundle = build_research_bundle(bundle_state)
    assert canonical_bundle_hash(leftover_bundle) == canonical_bundle_hash(baseline_bundle)
    _assert_qi0603_not_exported_or_hashed(leftover_bundle)
    _assert_qi0603_not_exported_or_hashed(baseline_bundle)

    apply_research_bundle_to_session(load_research_bundle(baseline_bundle), session)
    assert session["display_timezone"] == "Europe/Berlin"
    assert session["exchange_timezone"] == "Europe/Berlin"
    assert "focused_trades" not in session


def test_ah4_p6_managed_set_guard_ignores_comment_needles():
    """File-level / comment residual-key needles must not bind the managed set."""
    fake = (
        "_MANAGED_RESEARCH_KEYS = {\n"
        '    "data",\n'
        '    "trades",\n'
        "    # otf_validation_matrix otf_validation_config otf_validation_summary\n"
        "    # skipped_signals direction_collision_diagnostic display_timezone\n"
        "}\n"
    )
    try:
        _assert_qi0603_managed_set_literals(fake)
    except AssertionError as exc:
        assert "missing literals" in str(exc)
    else:
        raise AssertionError("comment leftover keys must not satisfy _MANAGED_RESEARCH_KEYS")

    stray_spec = (
        "BUNDLE_KEY_REGISTRY = ()\n"
        "_MANAGED_RESEARCH_KEYS = {key for spec in BUNDLE_KEY_REGISTRY "
        "if spec.managed for key in spec.session_keys}\n"
        "def _unused():\n"
        "    BundleKeySpec(\n"
        '        section="clear_only", meta_attr="", meta_keys=(),\n'
        '        session_keys=("otf_validation_matrix", "display_timezone"),\n'
        "        required_files=(), known_files=(), managed=True, hashed=False,\n"
        "        hash_exclude_files=(),\n"
        "    )\n"
    )
    try:
        _assert_qi0603_managed_set_literals(stray_spec)
    except AssertionError as exc:
        assert "missing literals" in str(exc)
    else:
        raise AssertionError("dead BundleKeySpec must not bind A-7 leftovers")


def test_hash_exclusion_guard_rejects_leftover_literal_set():
    """C-7: a leftover frozenset display must not satisfy hash-exclusion generation."""
    leftover = (
        "_CANONICAL_HASH_EXCLUDED_FILES = frozenset(\n"
        "    {\n"
        '        "confluence_combo_summary.json",\n'
        '        "confluence_by_exact_combo.parquet",\n'
        "    }\n"
        ")\n"
    )
    try:
        _assert_hash_exclusions_are_registry_generated(leftover)
    except AssertionError as exc:
        assert "generated" in str(exc) or "set display" in str(exc)
    else:
        raise AssertionError("leftover hash-exclusion literal must not pass")

    double = leftover + (
        "_CANONICAL_HASH_EXCLUDED_FILES = frozenset(\n"
        "    name for spec in BUNDLE_KEY_REGISTRY for name in spec.hash_exclude_files\n"
        ")\n"
    )
    try:
        _assert_hash_exclusions_are_registry_generated(double)
    except AssertionError as exc:
        assert "exactly one assignment" in str(exc)
    else:
        raise AssertionError("redefined hash-exclusion set must not pass")


def test_load_walk_guard_requires_included_gate():
    """C-7: iterating BUNDLE_SECTION_IO without included.get must fail closed."""
    ungated = (
        "def load_research_bundle(uploaded_file):\n"
        "    for spec in BUNDLE_SECTION_IO:\n"
        "        spec.load(ctx)\n"
    )
    try:
        _assert_bundle_walks_section_io(ungated, "load_research_bundle")
    except AssertionError as exc:
        assert "included.get" in str(exc)
    else:
        raise AssertionError("ungated load walk must not pass")


def test_spec_meta_requires_unique_nonempty_attr():
    """Generated *_META_KEYS aliases fail closed on blank or duplicate meta_attr."""
    from thesistester.research_bundle import _spec_meta

    with pytest.raises(ValueError, match="non-empty"):
        _spec_meta("")
    with pytest.raises(ValueError, match="exactly one spec"):
        _spec_meta("_MISSING_META_KEYS")


def test_ah4_p6_apply_guard_requires_pop_of_managed_set():
    """Iterating another set, or iterating without pop, must fail closed."""
    header = "def apply_research_bundle_to_session(bundle, session_state):\n    cleared_keys = []\n"
    other_set = header + (
        "    # _MANAGED_RESEARCH_KEYS\n"
        '    for key in ("data", "trades"):\n'
        "        session_state.pop(key, None)\n"
    )
    try:
        _assert_apply_pops_managed_set(other_set)
    except AssertionError as exc:
        assert "iterate _MANAGED_RESEARCH_KEYS" in str(exc)
    else:
        raise AssertionError("apply pop of a different set must not pass")

    no_pop = header + ("    for key in _MANAGED_RESEARCH_KEYS:\n        cleared_keys.append(key)\n")
    try:
        _assert_apply_pops_managed_set(no_pop)
    except AssertionError as exc:
        assert "must pop" in str(exc)
    else:
        raise AssertionError("apply For without pop must not pass")


def test_ah4_p6_apply_guard_requires_reset_display_timezone():
    """QI-10-01 / A-8: ensure-only or comment needles must not satisfy apply reset."""
    header = "def apply_research_bundle_to_session(bundle, session_state):\n"
    ensure_only = header + (
        "    from thesistester.timezone_display import ensure_display_timezone\n"
        "    ensure_display_timezone(session_state, exchange_timezone=None)\n"
    )
    try:
        _assert_apply_resets_display_timezone(ensure_only)
    except AssertionError as exc:
        assert "reset_display_timezone" in str(exc)
    else:
        raise AssertionError("ensure_display_timezone must not satisfy the A-8 apply reset probe")

    comment_only = header + "    # reset_display_timezone\n    pass\n"
    try:
        _assert_apply_resets_display_timezone(comment_only)
    except AssertionError as exc:
        assert "reset_display_timezone" in str(exc)
    else:
        raise AssertionError(
            "comment reset_display_timezone must not satisfy the apply reset probe"
        )

    restore = (
        "    session_values = bundle['session_values']\n"
        "    for key, value in session_values.items():\n"
        "        session_state[key] = value\n"
    )
    nested = header + (
        restore
        + "    def helper():\n"
        + "        reset_display_timezone("
        + "session_state, exchange_timezone=session_state.get('exchange_timezone'))\n"
        + "    pass\n"
    )
    try:
        _assert_apply_resets_display_timezone(nested)
    except AssertionError as exc:
        assert "reset_display_timezone" in str(exc)
    else:
        raise AssertionError(
            "nested unused reset_display_timezone must not satisfy the apply probe"
        )

    before_restore = header + (
        "    reset_display_timezone("
        "session_state, exchange_timezone=session_state.get('exchange_timezone'))\n" + restore
    )
    try:
        _assert_apply_resets_display_timezone(before_restore)
    except AssertionError as exc:
        assert "after session_values restore" in str(exc)
    else:
        raise AssertionError("reset before restore must not satisfy the apply reset probe")

    none_tz = (
        header + restore + "    reset_display_timezone(session_state, exchange_timezone=None)\n"
    )
    try:
        _assert_apply_resets_display_timezone(none_tz)
    except AssertionError as exc:
        assert "exchange_timezone" in str(exc)
    else:
        raise AssertionError("reset with exchange_timezone=None must not satisfy the apply probe")


def test_ah4_p6_export_probe_fails_closed_when_keys_enter_session_keys():
    """Hash-equal export that lists a residual key in session_keys must fail closed."""
    baseline = build_research_bundle(
        {
            "trades": pd.DataFrame({"trade_id": [1], "r_multiple": [1.0]}),
            "equity_curve": pd.DataFrame({"trade_id": [1], "cum_r": [1.0]}),
            "trade_summary": {"trade_count": 1},
        }
    )
    manifest = _manifest(baseline)
    manifest["session_keys"] = sorted({*manifest.get("session_keys", []), "otf_validation_matrix"})
    poisoned = _rewrite_bundle_manifest(baseline, manifest)
    try:
        _assert_qi0603_not_exported_or_hashed(poisoned)
    except AssertionError as exc:
        assert "session_keys" in str(exc)
    else:
        raise AssertionError("hashed session_keys leak must not pass the export probe")
