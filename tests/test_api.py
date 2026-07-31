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
    pd.testing.assert_frame_equal(facade["trades"], expected_trades)
    pd.testing.assert_frame_equal(facade["skipped_signals"], expected_skipped)
    pd.testing.assert_frame_equal(facade["equity_curve"], equity_curve(expected_trades))
    assert facade["trade_summary"] == summarize_trades(expected_trades)


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


def test_facade_rejects_unknown_configuration_keys(tmp_path):
    csv_path = tmp_path / "bars.csv"
    _write_dataset(csv_path)
    data = load_dataset(csv_path)
    with pytest.raises(ValueError, match="Unknown levels configuration keys"):
        compute_levels(data, config={"lookahead": True})
