"""SW5 tests: Grid / WFA / sensitivity inherit fixed entry_window."""

from __future__ import annotations

import pandas as pd

from thesistester.analytics.entry_window import (
    ENTRY_WINDOW_FIXED_CONSTRAINT_WARNING,
    resolve_inherited_entry_window,
)
from thesistester.analytics.grid import run_sl_tp_grid
from thesistester.analytics.overfitting import _SIMULATION_KWARGS, grid_trade_sequences
from thesistester.analytics.sensitivity import sensitivity_summary
from thesistester.api import run_grid
from thesistester.entry_window_policy import normalize_entry_window

TZ = "America/New_York"


def _bar(ts: str, o: float = 21000.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": o,
        "high": o + 2.0,
        "low": o - 2.0,
        "close": o + 0.5,
        "volume": 1000.0,
    }


def _signal(signal_id: int, bar_index: int) -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
        "bar_index": bar_index,
        "trigger": "touch",
        "direction": "long",
        "zone_low": 20990.0,
        "zone_high": 21010.0,
        "zone_mid": 21000.0,
        "level_count": 1,
        "level_names": "A",
        "entry_reference_price": 21000.0,
        "entry_model": "candidate_next_bar_open",
        "status": "candidate",
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }


def _frame_and_signals():
    stamps = pd.date_range("2026-06-02 09:29", periods=52, freq="1min", tz=TZ)
    rows = []
    price = 21000.0
    for ts in stamps:
        rows.append(_bar(str(ts), o=price))
        price += 0.25
    df = pd.DataFrame(rows)
    idx_open = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:45", tz=TZ)][0])
    idx_morn = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 10:10", tz=TZ)][0])
    signals = pd.DataFrame([_signal(1, idx_open), _signal(2, idx_morn)])
    return df, signals


def test_simulation_kwargs_includes_entry_window():
    assert "entry_window" in _SIMULATION_KWARGS
    assert "entry_window_exchange_tz" in _SIMULATION_KWARGS


def test_resolve_inherited_entry_window_default_off():
    resolved = resolve_inherited_entry_window(None, exchange_tz=TZ)
    assert resolved["enabled"] is False
    assert resolved["entry_window"] is None
    assert resolved["warning"] is None
    assert "fixed Admit constraint" in ENTRY_WINDOW_FIXED_CONSTRAINT_WARNING


def test_resolve_inherited_entry_window_enabled():
    window = normalize_entry_window(
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
            "timezone": TZ,
        },
        exchange_tz=TZ,
    )
    resolved = resolve_inherited_entry_window(window, exchange_tz=TZ, armed=True)
    assert resolved["enabled"] is True
    assert resolved["armed"] is True
    assert resolved["entry_window"]["rth_segments"] == ["rth_open_30m"]
    assert resolved["warning"] == ENTRY_WINDOW_FIXED_CONSTRAINT_WARNING


def test_run_sl_tp_grid_default_off_matches_omit():
    df, signals = _frame_and_signals()
    baseline = run_sl_tp_grid(
        df,
        signals,
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks_values=[8],
        take_profit_ticks_values=[16],
        max_holding_bars=5,
        exposure_policy="allow_all",
        cooldown_bars_after_exit=0,
    )
    explicit = run_sl_tp_grid(
        df,
        signals,
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks_values=[8],
        take_profit_ticks_values=[16],
        max_holding_bars=5,
        exposure_policy="allow_all",
        cooldown_bars_after_exit=0,
        entry_window={"enabled": False},
        entry_window_exchange_tz=TZ,
    )
    pd.testing.assert_frame_equal(baseline, explicit)
    assert int(baseline.iloc[0]["trade_count"]) == 2


def test_run_sl_tp_grid_enabled_window_constrains_all_cells():
    df, signals = _frame_and_signals()
    window = {
        "enabled": True,
        "mode": "rth_segments",
        "rth_segments": ["rth_open_30m"],
        "timezone": TZ,
    }
    grid = run_sl_tp_grid(
        df,
        signals,
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks_values=[8, 12],
        take_profit_ticks_values=[16],
        max_holding_bars=5,
        exposure_policy="allow_all",
        cooldown_bars_after_exit=0,
        entry_window=window,
        entry_window_exchange_tz=TZ,
    )
    assert len(grid) == 2
    assert set(grid["trade_count"].astype(int)) == {1}


def test_api_run_grid_passes_entry_window():
    df, signals = _frame_and_signals()
    window = {
        "enabled": True,
        "mode": "rth_segments",
        "rth_segments": ["rth_open_30m"],
        "timezone": TZ,
    }
    result = run_grid(
        df,
        signals,
        instrument="ES",
        config={
            "stop_loss_ticks_values": [8],
            "take_profit_ticks_values": [16],
            "max_holding_bars": 5,
            "entry_window": window,
        },
    )
    assert result["entry_window"]["enabled"] is True
    assert int(result["grid_results"].iloc[0]["trade_count"]) == 1


def test_sensitivity_and_sequences_honor_entry_window_via_kwargs():
    df, signals = _frame_and_signals()
    window = normalize_entry_window(
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
            "timezone": TZ,
        },
        exchange_tz=TZ,
    )
    grid = run_sl_tp_grid(
        df,
        signals,
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks_values=[8],
        take_profit_ticks_values=[16],
        max_holding_bars=5,
        exposure_policy="allow_all",
        cooldown_bars_after_exit=0,
        entry_window=window,
        entry_window_exchange_tz=TZ,
    )
    sequences = grid_trade_sequences(
        df,
        signals,
        tick_size=0.25,
        point_value=50.0,
        grid=grid,
        execution_kwargs={
            "max_holding_bars": 5,
            "exposure_policy": "allow_all",
            "cooldown_bars_after_exit": 0,
            "entry_window": window,
            "entry_window_exchange_tz": TZ,
        },
    )
    key = next(iter(sequences.cell_trades))
    assert len(sequences.cell_trades[key]) == 1

    summary = sensitivity_summary(
        df,
        signals,
        tick_size=0.25,
        point_value=50.0,
        selected_cell=grid.iloc[0],
        execution_kwargs={
            "max_holding_bars": 5,
            "exposure_policy": "allow_all",
            "cooldown_bars_after_exit": 0,
            "entry_window": window,
            "entry_window_exchange_tz": TZ,
        },
        parameters=["stop_loss_ticks"],
        n_steps_per_side=1,
        perturbation_fraction=0.25,
    )
    assert summary["available"] is True
    assert summary["baseline"]["trade_count"] == 1
