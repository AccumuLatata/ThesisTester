from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.grid import run_sl_tp_grid
from thesistester.engine.backtest import SimulationResult, simulate_trades

TZ = "America/New_York"


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=len(rows), freq="1min", tz=TZ),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
            "volume": [100] * len(rows),
        }
    )


def _signal(direction: str = "long") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_id": [1],
            "bar_index": [0],
            "trigger": ["touch"],
            "direction": [direction],
        }
    )


def _three_c_signal() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_id": [1],
            "bar_index": [1],
            "entry_bar_index": [1],
            "retrace_entry_price": [100.0],
            "trigger": ["3c"],
            "direction": ["long"],
            "status": ["filled"],
        }
    )


def _simulate(
    bars: pd.DataFrame,
    direction: str = "long",
    **kwargs,
) -> SimulationResult:
    result = simulate_trades(
        bars,
        _signal(direction),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        return_result=True,
        **kwargs,
    )
    assert isinstance(result, SimulationResult)
    return result


def test_long_breakeven_arms_after_completed_bar_and_exits_next_bar():
    result = _simulate(
        _bars(
            [
                (100, 100, 100, 100),
                (100, 102.5, 99.5, 100.5),
                (100.5, 101.5, 100.0, 100.5),
            ]
        ),
        breakeven_after_r=1.0,
    )
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "BE"
    assert trade["theoretical_exit_price"] == 100.0
    assert trade["r_multiple"] == 0.0
    assert trade["stop_price"] == 98.0
    assert trade["active_stop_price_at_exit"] == 100.0
    assert trade["breakeven_activated_bar_index"] == 1
    assert result.exit_management_diagnostic["be_exit_count"] == 1


def test_breakeven_with_slippage_can_be_slightly_negative():
    result = simulate_trades(
        _bars(
            [
                (100, 100, 100, 100),
                (100, 101.0, 99.5, 100.5),
                (100.5, 101.5, 100.5, 101.0),
                (101, 101.5, 100.25, 100.5),
            ]
        ),
        _signal("long"),
        tick_size=0.25,
        point_value=1.0,
        stop_loss_ticks=4,
        take_profit_ticks=8,
        slippage_ticks=1,
        breakeven_after_r=1.0,
    )
    trade = result.iloc[0]
    assert trade["exit_reason"] == "BE"
    assert trade["r_multiple"] == pytest.approx(-0.25)


def test_short_breakeven_is_symmetric():
    result = _simulate(
        _bars(
            [
                (100, 100, 100, 100),
                (100, 100.5, 99.0, 99.5),
                (99.5, 99.5, 97.5, 98.5),
                (98.5, 100.0, 98.5, 99.5),
            ]
        ),
        direction="short",
        breakeven_after_r=1.0,
    )
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "BE"
    assert trade["theoretical_exit_price"] == 100.0
    assert trade["active_stop_price_at_exit"] == 100.0


def test_trailing_stop_ratchets_and_exits_long():
    result = _simulate(
        _bars(
            [
                (100, 100, 100, 100),
                (100, 103.0, 99.5, 102.0),
                (102, 102.5, 101.0, 101.5),
            ]
        ),
        trailing_after_r=1.0,
        trailing_distance_ticks=2,
    )
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "TRAIL"
    assert trade["theoretical_exit_price"] == 101.0
    assert trade["r_multiple"] == pytest.approx(0.5)
    assert trade["trailing_activated_bar_index"] == 1
    assert result.exit_management_diagnostic["trail_exit_count"] == 1


def test_trailing_stop_ratchets_and_exits_short():
    result = _simulate(
        _bars(
            [
                (100, 100, 100, 100),
                (100, 100.5, 99.0, 99.5),
                (99.5, 99.5, 97.0, 98.0),
                (98, 99.0, 97.5, 98.5),
            ]
        ),
        direction="short",
        trailing_after_r=1.0,
        trailing_distance_ticks=2,
    )
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "TRAIL"
    assert trade["theoretical_exit_price"] == 99.0
    assert trade["r_multiple"] == pytest.approx(0.5)


def test_simple_next_open_can_arm_breakeven_after_entry_bar_close():
    result = _simulate(
        _bars(
            [
                (100, 100, 100, 100),
                (100, 103.0, 100.0, 102.0),
                (102, 102.5, 100.0, 100.0),
            ]
        ),
        breakeven_after_r=1.0,
    )
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "BE"
    assert trade["exit_bar_index"] == 2
    assert trade["breakeven_activated_bar_index"] == 1


def test_intrabar_entry_does_not_arm_breakeven_on_entry_parent_bar():
    result = simulate_trades(
        _bars(
            [
                (100, 100, 100, 100),
                (100, 103.0, 100.0, 102.0),
                (102, 103.0, 101.0, 102.5),
                (102, 102.5, 100.0, 100.5),
            ]
        ),
        _three_c_signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        breakeven_after_r=1.0,
    )
    trade = result.iloc[0]
    assert trade["exit_reason"] == "BE"
    assert trade["exit_bar_index"] == 3
    assert trade["breakeven_activated_bar_index"] == 2


def test_dynamic_stop_interacts_with_intrabar_model_for_tp_vs_breakeven_order():
    bars = _bars(
        [
            (100, 100, 100, 100),
            (100, 101.0, 99.5, 100.5),
            (100.5, 102.5, 100.5, 101.0),
            (103, 104.5, 100.0, 103.0),
        ]
    )
    sl_first = _simulate(
        bars,
        breakeven_after_r=1.0,
        intrabar_model="sl_first",
    )
    path = _simulate(
        bars,
        breakeven_after_r=1.0,
        intrabar_model="path_open_proximity",
    )
    assert sl_first.trades.iloc[0]["exit_reason"] == "BE"
    assert path.trades.iloc[0]["exit_reason"] == "TP_intrabar_path"


def test_exit_management_config_validation():
    with pytest.raises(ValueError, match="trailing_distance_ticks"):
        _simulate(_bars([(100, 100, 100, 100), (100, 101, 99, 100)]), trailing_after_r=1.0)
    with pytest.raises(ValueError, match="breakeven_after_r"):
        _simulate(
            _bars([(100, 100, 100, 100), (100, 101, 99, 100)]),
            breakeven_after_r=0,
        )


def test_disabled_exit_management_preserves_legacy_output_and_schema():
    bars = _bars([(100, 100, 100, 100), (100, 104.0, 98.0, 101.0)])
    default = simulate_trades(
        bars,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
    )
    explicit_disabled = simulate_trades(
        bars,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        breakeven_after_r=None,
        trailing_after_r=None,
        trailing_distance_ticks=None,
    )
    pd.testing.assert_frame_equal(default, explicit_disabled)
    assert "active_stop_price_at_exit" not in default.columns


def test_grid_sweeps_exit_management_with_cell_cap():
    grid = run_sl_tp_grid(
        _bars(
            [(100, 100, 100, 100), (100, 101, 99, 100), (100, 103, 100, 102), (102, 102, 100, 101)]
        ),
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks_values=[2],
        take_profit_ticks_values=[4],
        breakeven_after_r_values=[None, 1.0],
        trailing_after_r_values=[None, 1.0],
        trailing_distance_ticks_values=[None, 2],
        max_grid_cells=4,
    )
    assert len(grid) == 4
    assert {"breakeven_after_r", "trailing_after_r", "trailing_distance_ticks"}.issubset(
        grid.columns
    )
    with pytest.raises(ValueError, match="exceeding max_grid_cells"):
        run_sl_tp_grid(
            _bars([(100, 100, 100, 100), (100, 101, 99, 100)]),
            _signal(),
            tick_size=1.0,
            point_value=1.0,
            stop_loss_ticks_values=[1, 2],
            take_profit_ticks_values=[3, 4],
            breakeven_after_r_values=[None, 1.0],
            max_grid_cells=3,
        )
