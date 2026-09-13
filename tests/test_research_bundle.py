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
    DATA_PAGE_INVALIDATE_SOURCE_KEY,
    _CANONICAL_HASH_EXCLUDED_FILES,
    _KNOWN_FILES,
    _MANAGED_RESEARCH_KEYS,
    apply_research_bundle_to_session,
    build_research_bundle,
    canonical_bundle_hash,
    load_research_bundle,
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


def _assert_qi0603_not_exported_or_hashed(bundle_bytes: bytes) -> None:
    """QI-06-03 / A-7: residual keys are not zip members, META keys, or hashed."""
    assert "display_timezone" not in _MANAGED_RESEARCH_KEYS
    for key in _QI0603_CLEAR_ONLY_KEYS:
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
        for key in _QI0603_CLEAR_ONLY_KEYS:
            assert all(key not in name for name in names), f"{key} leaked into zip member names"
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        session_keys = manifest.get("session_keys") or []
        for key in _QI0603_CLEAR_ONLY_KEYS:
            assert key not in session_keys, f"{key} leaked into hashed manifest session_keys"
        for name in names:
            if not name.endswith(".json"):
                continue
            payload = json.loads(archive.read(name).decode("utf-8"))
            for key in _QI0603_CLEAR_ONLY_KEYS:
                assert not _json_contains_key(payload, key), f"{key} leaked into {name}"

    loaded = load_research_bundle(bundle_bytes)
    for key in _QI0603_CLEAR_ONLY_KEYS:
        assert key not in loaded["session_values"], f"{key} restored from zip session_values"


def _assert_qi0603_leftovers_cleared(session: dict) -> None:
    for key in _QI0603_CLEAR_ONLY_KEYS:
        assert key not in session, f"{key} leftover survived apply"
    assert session["display_timezone"] == "UTC"


def _managed_set_string_literals(source: str) -> set[str]:
    """String literals in the ``_MANAGED_RESEARCH_KEYS`` set display (AST, not comments)."""
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "_MANAGED_RESEARCH_KEYS" for t in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Set):
            raise AssertionError("_MANAGED_RESEARCH_KEYS must be a set display")
        literals = {
            elt.value
            for elt in node.value.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        return literals
    raise AssertionError("missing _MANAGED_RESEARCH_KEYS assignment")


def _assert_qi0603_managed_set_literals(source: str) -> None:
    """AST-bind the five residual keys to the managed-set literals.

    File-level / comment needles false-green — A-1/A-6 class.
    """
    literals = _managed_set_string_literals(source)
    missing = [key for key in _QI0603_CLEAR_ONLY_KEYS if key not in literals]
    assert missing == [], f"_MANAGED_RESEARCH_KEYS set missing literals {missing}"
    assert "display_timezone" not in literals


def _function_def(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing def {name}")


def _assert_apply_pops_managed_set(source: str) -> None:
    """Apply must ``pop`` keys from ``_MANAGED_RESEARCH_KEYS`` (not a comment / other set)."""
    tree = ast.parse(source)
    fn = _function_def(tree, "apply_research_bundle_to_session")
    for node in ast.walk(fn):
        if not isinstance(node, ast.For):
            continue
        if not isinstance(node.iter, ast.Name) or node.iter.id != "_MANAGED_RESEARCH_KEYS":
            continue
        for child in ast.walk(node):
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
        "display_timezone": "UTC",
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


def test_ah4_p6_managed_set_literals_and_apply_pop_are_ast_bound():
    """QI-06-03 / A-7: comment needles must not satisfy managed-set membership or apply pop."""
    _assert_qi0603_managed_set_literals(_RESEARCH_BUNDLE_SOURCE)
    _assert_apply_pops_managed_set(_RESEARCH_BUNDLE_SOURCE)


def test_ah4_p6_managed_set_guard_ignores_comment_needles():
    """File-level / comment residual-key needles must not bind the managed set."""
    fake = (
        "_MANAGED_RESEARCH_KEYS = {\n"
        '    "data",\n'
        '    "trades",\n'
        "    # otf_validation_matrix otf_validation_config otf_validation_summary\n"
        "    # skipped_signals direction_collision_diagnostic\n"
        "}\n"
    )
    try:
        _assert_qi0603_managed_set_literals(fake)
    except AssertionError as exc:
        assert "missing literals" in str(exc)
    else:
        raise AssertionError("comment leftover keys must not satisfy _MANAGED_RESEARCH_KEYS")


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
