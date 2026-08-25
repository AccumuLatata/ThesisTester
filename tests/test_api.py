from __future__ import annotations

from pathlib import Path

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
    run_portfolio_analysis,
    run_walk_forward,
    run_validation,
)
from thesistester.engine import apply_configured_otf_filter, simulate_trades
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.tick_vap import TICK_SOURCE_NONE, attach_tick_identity


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


def test_load_dataset_preserves_ninjatrader_utc_default():
    path = Path(__file__).parent / "fixtures" / "vendor" / "ninjatrader_minute.txt"

    default = load_dataset(path, instrument="ES", format_profile="ninjatrader")
    explicit_exchange = load_dataset(
        path,
        instrument="ES",
        source_timezone="America/New_York",
        format_profile="ninjatrader",
    )

    assert default["timestamp"].iloc[0].isoformat() == "2026-06-02T09:30:00-04:00"
    assert explicit_exchange["timestamp"].iloc[0].isoformat() == "2026-06-02T13:30:00-04:00"


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


def test_run_validation_wires_opt_in_sensitivity_profile(monkeypatch):
    expected = {
        "schema_version": 1,
        "available": True,
        "config": {"perturbation_fraction": 0.2},
        "parameters": [],
    }

    def fake_profile(*args, **kwargs):
        assert kwargs["selected_grid_metric"] == "expectancy_r"
        assert kwargs["sensitivity_config"] == {"perturbation_fraction": 0.2}
        return expected

    monkeypatch.setattr("thesistester.api.run_sensitivity_profile", fake_profile)
    result = run_validation(
        pd.DataFrame(),
        df=pd.DataFrame(),
        signals=pd.DataFrame(),
        tick_size=0.25,
        point_value=5.0,
        grid=pd.DataFrame(
            {
                "stop_loss_ticks": [8.0],
                "take_profit_ticks": [16.0],
                "expectancy_r": [0.5],
                "trade_count": [10],
            }
        ),
        config={"sensitivity": {"enabled": True, "perturbation_fraction": 0.2}},
    )

    assert result["sensitivity_summary"] == expected
    assert result["sensitivity_config"] == expected["config"]


def test_run_portfolio_analysis_returns_bundle_ready_outputs():
    timestamps = pd.date_range("2026-01-05 09:30", periods=4, freq="1min")

    def trades(trade_id, entry, exit_, r_multiple):
        return pd.DataFrame(
            {
                "trade_id": [trade_id],
                "entry_bar_index": [entry],
                "exit_bar_index": [exit_],
                "entry_timestamp": [timestamps[entry]],
                "exit_timestamp": [timestamps[exit_]],
                "direction": ["long"],
                "r_multiple": [r_multiple],
            }
        )

    result = run_portfolio_analysis(
        {"A": trades(1, 0, 1, 1.0), "B": trades(2, 2, 3, 2.0)},
        instrument="ES",
        bar_count=4,
    )

    assert result["portfolio_summary"]["portfolio_metrics"]["total_r"] == 3.0
    assert result["portfolio_config"]["setup_ids"] == ["A", "B"]
    assert len(result["portfolio_trades"]) == 2


def _levels_config() -> dict:
    return {
        "sma_lengths": [],
        "ema_lengths": [],
        "sma_timeframes": [],
        "ema_timeframes": [],
        "vwap_windows": [],
        "poc_windows": [],
    }


def test_compute_levels_uses_shared_product_defaults(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path, instrument="ES")

    result = compute_levels(data, instrument="ES")

    expected = dict(DEFAULT_LEVELS_SETTINGS)
    for key in (
        "sma_timeframes",
        "ema_timeframes",
        "vwap_windows",
        "poc_windows",
        "pivot_timeframes",
    ):
        expected[key] = sorted(expected[key])
    expected["instrument"] = "ES"
    expected = attach_tick_identity(expected, tick_source_id=TICK_SOURCE_NONE)
    assert result["levels_settings"] == expected
    assert "dVWAP_RTH" in result["levels"]
    assert "APOC" in result["levels"]
    assert "dSinglePrint_30m_NearestAbove" in result["levels"]
    assert any(column.startswith("Pivot_") for column in result["levels"])


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
    assert facade["otf_filter_summary"]["eth_start"] == "18:00"
    assert facade["otf_filter_summary"]["session_timezone"] == "America/New_York"
    assert otf.eth_start == "18:00"
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


def test_walk_forward_rejects_invalid_otf_history_policy(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path, instrument="ES")
    levels = compute_levels(data, instrument="ES", config=_levels_config())["levels"]
    setup = _setup()
    signals = generate_signals(levels, setup)["signals"]
    with pytest.raises(ValueError, match="otf_history_policy"):
        run_walk_forward(
            levels,
            signals,
            instrument="ES",
            config={
                "fold_mode": "bars",
                "window_mode": "rolling",
                "train_bars": 30,
                "test_bars": 10,
                "step_bars": 10,
                "ranking_metric": "expectancy_r",
                "min_train_trades": 1,
                "stop_loss_ticks_values": [2],
                "take_profit_ticks_values": [2],
                "overlap_policy": "reject",
                "otf_history_policy": "not_a_policy",
            },
            otf_config=setup.get("otf_filter"),
        )


def test_walk_forward_defaults_otf_history_policy_to_fold_local(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path, instrument="ES")
    levels = compute_levels(data, instrument="ES", config=_levels_config())["levels"]
    setup = _setup()
    signals = generate_signals(levels, setup)["signals"]
    result = run_walk_forward(
        levels,
        signals,
        instrument="ES",
        config={
            "fold_mode": "bars",
            "window_mode": "rolling",
            "train_bars": 30,
            "test_bars": 10,
            "step_bars": 10,
            "ranking_metric": "expectancy_r",
            "min_train_trades": 1,
            "stop_loss_ticks_values": [2],
            "take_profit_ticks_values": [2],
            "overlap_policy": "reject",
        },
        otf_config=setup.get("otf_filter"),
    )
    assert result["walk_forward_config"]["otf_history_policy"] == "fold_local"
    assert result["walk_forward_summary"]["otf_history_policy"] == "fold_local"


def test_walk_forward_matrix_forwards_otf_history_policy(tmp_path, monkeypatch):
    """WFA matrix cells must inherit the primary WFO otf_history_policy."""
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path, instrument="ES")
    levels = compute_levels(data, instrument="ES", config=_levels_config())["levels"]
    setup = _setup()
    signals = generate_signals(levels, setup)["signals"]

    captured: dict = {}

    def _fake_matrix(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame(
            [
                {
                    "train_sessions": 2,
                    "test_sessions": 1,
                    "fold_count": 0,
                    "valid_fold_count": 0,
                    "median_test_expectancy_r": None,
                    "median_retention_ratio_expectancy": None,
                    "stitched_oos_trade_count": 0,
                    "stitched_oos_total_r": None,
                    "matrix_metric": "median_test_expectancy_r",
                    "matrix_value": None,
                    "status": "empty",
                }
            ]
        )

    monkeypatch.setattr("thesistester.api.run_wfa_matrix", _fake_matrix)
    result = run_walk_forward(
        levels,
        signals,
        instrument="ES",
        config={
            "fold_mode": "sessions",
            "window_mode": "rolling",
            "train_sessions": 2,
            "test_sessions": 1,
            "step_sessions": 1,
            "ranking_metric": "expectancy_r",
            "min_train_trades": 1,
            "stop_loss_ticks_values": [2],
            "take_profit_ticks_values": [2],
            "overlap_policy": "reject",
            "otf_history_policy": "causal_prefix",
            "matrix": {
                "enabled": True,
                "train_session_values": [2],
                "test_session_values": [1],
                "matrix_metric": "median_test_expectancy_r",
            },
        },
        otf_config=setup.get("otf_filter"),
    )
    assert captured.get("otf_history_policy") == "causal_prefix"
    assert result["wfa_matrix_config"]["otf_history_policy"] == "causal_prefix"
    assert result["walk_forward_summary"]["otf_history_policy"] == "causal_prefix"


def test_anchor_only_setup_generate_signals_emits_point_zone():
    setup = build_setup(
        {
            "name": "ONH_anchor_only",
            "description": "AO1",
            "instrument": "ES",
            "selected_levels": [],
            "tolerance_ticks": 10,
            "min_confluences": 1,
            "max_confluences": 1,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger": "touch",
            "trigger_timeframe": "1min",
            "direction": "both",
            "confluence_mode": "anchor_rules",
            "anchor_level": "ONH",
            "confluence_rules": [],
            "min_valid_confluences": 0,
        }
    )
    levels = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=1, freq="1min"),
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "ONH": [100.5],
        }
    )
    result = generate_signals(levels, setup)
    zones = result["confluence_zones"]
    assert len(zones) == 1
    assert zones.iloc[0]["level_names"] == "ONH"
    assert zones.iloc[0]["valid_confluence_count"] == 0
    assert zones.iloc[0]["zone_low"] == zones.iloc[0]["zone_high"] == 100.5
    backtest = run_backtest(levels, result["signals"], instrument="ES")
    assert "trades" in backtest
