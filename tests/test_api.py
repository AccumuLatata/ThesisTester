from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics import equity_curve, summarize_trades
from thesistester.api import (
    build_setup,
    compute_levels,
    generate_signals,
    load_dataset,
    run_backtest,
    run_grid,
    run_walk_forward,
    run_validation,
)
from thesistester.engine import apply_configured_otf_filter, simulate_trades


def _write_dataset(path) -> None:
    timestamps = pd.date_range("2026-06-01 09:30", periods=14, freq="1min")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * len(timestamps),
            "high": [100.5] * len(timestamps),
            "low": [99.5] * len(timestamps),
            "close": [100.25 if i % 2 == 0 else 99.75 for i in range(len(timestamps))],
            "volume": [100 + i for i in range(len(timestamps))],
        }
    )
    frame.to_csv(path, index=False)


def _setup() -> dict:
    return build_setup(
        {
            "name": "R18 fixture",
            "description": "Headless parity fixture",
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
        }
    )


def _levels_config() -> dict:
    return {
        "sma_lengths": [],
        "ema_lengths": [],
        "sma_timeframes": [],
        "ema_timeframes": [],
        "vwap_windows": [],
        "poc_windows": [],
    }


def test_headless_facade_matches_ui_backtest_composition(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path, instrument="ES")
    level_result = compute_levels(data, instrument="ES", config=_levels_config())
    setup = _setup()
    signal_result = generate_signals(level_result["levels"], setup)
    assert not signal_result["signals"].empty
    assert signal_result["signal_settings"]["otf_algorithm_version"]
    assert signal_result["signal_settings"]["otf_config_hash"]
    normalized_snapshot = signal_result["signal_settings"]["setup_snapshot"]
    assert normalized_snapshot["name"] == setup["name"]
    assert normalized_snapshot["otf_filter"] == setup["otf_filter"]
    assert normalized_snapshot["otf_algorithm_version"]
    assert normalized_snapshot["otf_config_hash"]

    config = {
        "stop_loss_ticks": 2,
        "take_profit_ticks": 2,
        "exposure_policy": "single_position",
    }
    facade = run_backtest(
        level_result["levels"],
        signal_result["signals"],
        instrument="ES",
        config=config,
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
    )

    otf = apply_configured_otf_filter(
        source_df=level_result["levels"],
        candidate_signals=signal_result["signals"],
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
        last_signal_setup=setup,
        session_timezone="America/New_York",
        eth_start="18:00",
    )
    expected_trades, expected_skipped = simulate_trades(
        df=level_result["levels"],
        signals=otf.accepted_signals,
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks=2,
        take_profit_ticks=2,
        exposure_policy="single_position",
        return_skipped_signals=True,
    )
    assert facade["exit_management_diagnostic"]["enabled"] is False
    assert "active_stop_price_at_exit" not in facade["trades"].columns
    pd.testing.assert_frame_equal(facade["skipped_signals"], expected_skipped)
    pd.testing.assert_frame_equal(facade["equity_curve"], equity_curve(expected_trades))
    assert facade["trade_summary"] == summarize_trades(expected_trades)
    assert facade["intrabar_diagnostic"]["intrabar_model"] == "sl_first"


def test_headless_backtest_surfaces_exit_management_diagnostics(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path, instrument="ES")
    levels = compute_levels(data, instrument="ES", config=_levels_config())["levels"]
    setup = _setup()
    signals = generate_signals(levels, setup)
    result = run_backtest(
        levels,
        signals["signals"],
        instrument="ES",
        config={
            "stop_loss_ticks": 2,
            "take_profit_ticks": 2,
            "breakeven_after_r": 1.0,
        },
        setup_config=setup,
        signal_settings=signals["signal_settings"],
    )
    assert result["exit_management_diagnostic"]["breakeven_after_r"] == 1.0
    assert "active_stop_price_at_exit" in result["trades"].columns


def test_grid_and_validation_battery_are_seeded_and_plain_data(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path)
    levels = compute_levels(data, config=_levels_config())["levels"]
    setup = _setup()
    signal_result = generate_signals(levels, setup)
    backtest = run_backtest(
        levels,
        signal_result["signals"],
        config={"stop_loss_ticks": 2, "take_profit_ticks": 3},
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
    )
    grid = run_grid(
        levels,
        signal_result["signals"],
        config={
            "stop_loss_ticks_values": [2, 3],
            "take_profit_ticks_values": [3, 4],
        },
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
    )
    assert len(grid["grid_results"]) == 4

    config = {
        "n_bootstrap": 25,
        "n_permutations": 25,
        "random_state": 7,
        "excursion": {"enabled": True, "min_trades": 1},
        "monte_carlo": {"enabled": True, "n_simulations": 25, "random_state": 7},
    }
    first = run_validation(
        backtest["trades"],
        grid=grid["grid_results"],
        tick_size=0.25,
        config=config,
    )
    second = run_validation(
        backtest["trades"],
        grid=grid["grid_results"],
        tick_size=0.25,
        config=config,
    )
    assert first["validation_summary"] == second["validation_summary"]
    assert first["monte_carlo_summary"] == second["monte_carlo_summary"]
    pd.testing.assert_frame_equal(
        first["excursion_calibration_grid"],
        second["excursion_calibration_grid"],
    )


def test_validation_r16_noise_is_opt_in_and_seeded(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path)
    levels = compute_levels(data, config=_levels_config())["levels"]
    setup = _setup()
    signals = generate_signals(levels, setup)
    backtest = run_backtest(
        levels,
        signals["signals"],
        config={"stop_loss_ticks": 2, "take_profit_ticks": 3},
        setup_config=setup,
        signal_settings=signals["signal_settings"],
    )
    config = {
        "n_bootstrap": 25,
        "n_permutations": 25,
        "noise": {
            "enabled": True,
            "n_replicas": 5,
            "noise_fraction": 0.05,
            "scale_basis": "atr",
            "atr_period": 3,
            "random_state": 7,
        },
    }
    kwargs = {
        "raw_data": data,
        "levels_config": {**_levels_config(), "instrument": "ES"},
        "setup_config": {**setup, "dataset_id": "saved-setup-metadata"},
        "backtest_config": {"stop_loss_ticks": 2, "take_profit_ticks": 3},
    }
    first = run_validation(backtest["trades"], config=config, **kwargs)
    second = run_validation(backtest["trades"], config=config, **kwargs)
    assert first["noise_summary"] == second["noise_summary"]
    assert first["noise_config"]["random_state"] == 7


def test_headless_walk_forward_returns_bundle_ready_r14_artifacts(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path)
    levels = compute_levels(data, config=_levels_config())["levels"]
    setup = _setup()
    signal_result = generate_signals(levels, setup)
    result = run_walk_forward(
        levels,
        signal_result["signals"],
        config={
            "fold_mode": "bars",
            "window_mode": "rolling",
            "train_bars": 6,
            "test_bars": 4,
            "step_bars": 4,
            "stop_loss_ticks_values": [2],
            "take_profit_ticks_values": [3],
        },
        execution_config={"intrabar_model": "sl_first"},
    )
    assert isinstance(result["walk_forward_results"], pd.DataFrame)
    assert result["walk_forward_summary"]["schema_version"] == 2
    assert isinstance(result["walk_forward_oos_trades"], pd.DataFrame)
    assert isinstance(result["walk_forward_stitched_equity"], pd.DataFrame)


def test_headless_walk_forward_matrix_requires_dimensions(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path)
    levels = compute_levels(data, config=_levels_config())["levels"]
    setup = _setup()
    signal_result = generate_signals(levels, setup)
    try:
        run_walk_forward(
            levels,
            signal_result["signals"],
            config={
                "fold_mode": "sessions",
                "train_sessions": 2,
                "test_sessions": 1,
                "stop_loss_ticks_values": [2],
                "take_profit_ticks_values": [3],
                "matrix": {"enabled": True, "train_session_values": [2]},
            },
        )
    except ValueError as exc:
        assert "test_session_values" in str(exc)
    else:
        raise AssertionError("Expected missing matrix dimensions to fail")


def test_validation_r15_is_opt_in_and_seeded(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path)
    levels = compute_levels(data, config=_levels_config())["levels"]
    setup = _setup()
    signal_result = generate_signals(levels, setup)
    grid = run_grid(
        levels,
        signal_result["signals"],
        config={
            "stop_loss_ticks_values": [2, 3],
            "take_profit_ticks_values": [3, 4],
        },
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
    )
    backtest = run_backtest(
        levels,
        signal_result["signals"],
        config={"stop_loss_ticks": 2, "take_profit_ticks": 3},
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
    )
    config = {
        "n_bootstrap": 10,
        "n_permutations": 10,
        "overfitting": {
            "enabled": True,
            "pbo_partitions": 4,
            "pbo_min_trades": 1,
            "vs_random_n_replicas": 10,
            "random_state": 42,
        },
    }
    first = run_validation(
        backtest["trades"],
        grid=grid["grid_results"],
        tick_size=0.25,
        config=config,
        df=levels,
        signals=signal_result["signals"],
        point_value=50.0,
    )
    second = run_validation(
        backtest["trades"],
        grid=grid["grid_results"],
        tick_size=0.25,
        config=config,
        df=levels,
        signals=signal_result["signals"],
        point_value=50.0,
    )
    assert first["overfitting_summary"] == second["overfitting_summary"]
    assert first["overfitting_summary"]["schema_version"] == 1


def test_validation_r15_rejects_nonempty_grid_without_eligible_replayed_cell(tmp_path):
    """R15 must never substitute Phase 5 trades for an ineligible grid cell."""
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path)
    levels = compute_levels(data, config=_levels_config())["levels"]
    setup = _setup()
    signal_result = generate_signals(levels, setup)
    grid = run_grid(
        levels,
        signal_result["signals"],
        config={
            "stop_loss_ticks_values": [2, 3],
            "take_profit_ticks_values": [3, 4],
        },
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
    )
    backtest = run_backtest(
        levels,
        signal_result["signals"],
        config={"stop_loss_ticks": 2, "take_profit_ticks": 3},
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
    )
    assert not grid["grid_results"].empty
    assert not backtest["trades"].empty

    with pytest.raises(ValueError, match="No replayed grid cell passes the R15 selection rule"):
        run_validation(
            backtest["trades"],
            grid=grid["grid_results"],
            tick_size=0.25,
            config={
                "overfitting": {
                    "enabled": True,
                    "pbo_partitions": 4,
                    "pbo_min_trades": 1,
                    "vs_random_n_replicas": 10,
                    "random_state": 42,
                }
            },
            df=levels,
            signals=signal_result["signals"],
            point_value=50.0,
            selected_min_trades=int(grid["grid_results"]["trade_count"].max()) + 1,
        )


def test_facade_rejects_unknown_configuration_keys(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path)
    with pytest.raises(ValueError, match="Unknown levels configuration keys"):
        compute_levels(data, config={"lookahead": True})


def test_backtest_preserves_ui_otf_precedence_for_signal_producing_setup(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path)
    levels = compute_levels(data, config=_levels_config())["levels"]
    producing_setup = _setup()
    signals = generate_signals(levels, producing_setup)["signals"]
    active_setup = {
        **producing_setup,
        "otf_filter": {
            "enabled": True,
            "timeframes": ["5m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 1,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        },
    }
    result = run_backtest(
        levels,
        signals,
        setup_config=active_setup,
        last_signal_setup=producing_setup,
        signal_settings={},
    )
    assert result["otf_filter_summary"]["otf_filter_enabled"] is False
