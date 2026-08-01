from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.grid import run_sl_tp_grid
from thesistester.engine.backtest import SimulationResult, simulate_trades
from thesistester.engine.intrabar import prepare_subtimeframe_conservative_context

TZ = "America/New_York"


def _signal(direction: str = "long") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_id": [1],
            "bar_index": [0],
            "trigger": ["touch"],
            "direction": [direction],
        }
    )


def _three_c_signal(entry_price: float = 99.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_id": [1],
            "bar_index": [1],
            "entry_bar_index": [1],
            "retrace_entry_price": [entry_price],
            "trigger": ["3c"],
            "direction": ["long"],
            "status": ["filled"],
        }
    )


def _parent_bar(*, high: float, low: float, close: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=2, freq="5min", tz=TZ),
            "open": [100.0, 100.0],
            "high": [101.0, high],
            "low": [99.0, low],
            "close": [100.0, close],
            "volume": [1000, 1000],
        }
    )


def _simulate_path(parent: pd.DataFrame, direction: str = "long") -> SimulationResult:
    result = simulate_trades(
        parent,
        _signal(direction),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="path_open_proximity",
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    return result


@pytest.mark.parametrize(
    ("high", "low", "direction", "expected"),
    [
        (104.0, 94.0, "long", "TP_intrabar_path"),
        (104.0, 94.0, "short", "SL_intrabar_path"),
        (106.0, 96.0, "long", "SL_intrabar_path"),
        (106.0, 96.0, "short", "TP_intrabar_path"),
    ],
)
def test_open_proximity_path_orders_long_and_short_both_hits(
    high,
    low,
    direction,
    expected,
):
    result = _simulate_path(_parent_bar(high=high, low=low), direction)
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == expected
    assert trade["intrabar_parent_both_hit"] == True  # noqa: E712
    assert trade["intrabar_ambiguous"] == False  # noqa: E712
    assert result.intrabar_diagnostic["same_bar_both_hit_count"] == 1
    assert result.intrabar_diagnostic["ambiguous_resolution_count"] == 0


def test_open_proximity_tie_is_deterministically_sl_first():
    result = _simulate_path(_parent_bar(high=104.0, low=96.0))
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "SL_intrabar_path"
    assert trade["intrabar_resolution"] == "intrabar_path_proximity_tie_sl_first"
    assert result.intrabar_diagnostic["path_proximity_tie_count"] == 1
    assert result.intrabar_diagnostic["ambiguous_resolution_count"] == 1


def test_open_proximity_does_not_exit_on_single_target_hit_before_entry():
    parent = _parent_bar(high=104.0, low=98.0, close=100.0)
    parent.loc[1, "open"] = 102.0
    result = simulate_trades(
        parent,
        _three_c_signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="path_open_proximity",
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    assert result.trades.iloc[0]["exit_reason"] == "EOD"


def test_open_proximity_tie_requires_target_after_entry_on_both_candidate_paths():
    parent = _parent_bar(high=104.0, low=100.0, close=102.0)
    parent.loc[1, "open"] = 102.0
    result = simulate_trades(
        parent,
        _three_c_signal(entry_price=101.0),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=2,
        intrabar_model="path_open_proximity",
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    assert result.trades.iloc[0]["exit_reason"] == "EOD"
    assert result.intrabar_diagnostic["ambiguous_resolution_count"] == 1


def _subtimeframe_data(*, residual_both_hit: bool = False) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-05 09:30", periods=10, freq="1min", tz=TZ)
    rows = [
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 101.0, 99.0, 100.0),
        (100.0, 104.5, 99.5 if not residual_both_hit else 97.0, 103.0),
        (103.0, 103.5, 97.0, 98.0),
        (98.0, 101.0, 97.5, 100.0),
        (100.0, 101.0, 99.0, 100.0),
    ]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
            "volume": [200] * len(rows),
        }
    )


def _preentry_subtimeframe_data(*, target_on_entry_subbar: bool = False) -> pd.DataFrame:
    frame = _subtimeframe_data()
    frame.loc[5:, ["open", "high", "low", "close"]] = [
        [102.0, 104.0, 102.0, 103.0],
        [100.0, 104.0 if target_on_entry_subbar else 102.0, 98.0, 100.0],
        [100.0, 102.0, 99.0, 100.0],
        [100.0, 101.0, 99.0, 100.0],
        [100.0, 101.0, 99.0, 100.0],
    ]
    return frame


def test_subtimeframe_sequence_orders_target_before_later_stop():
    parent = _parent_bar(high=104.5, low=97.0)
    result = simulate_trades(
        parent,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="subtimeframe",
        subtimeframe_data=_subtimeframe_data(),
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "TP_subtimeframe"
    assert trade["intrabar_resolution"] == "subtimeframe_sequence"
    assert trade["exit_subbar_timestamp"] == pd.Timestamp("2026-01-05 09:36", tz=TZ)
    assert result.intrabar_diagnostic["same_bar_both_hit_count"] == 1
    assert result.intrabar_diagnostic["ambiguous_resolution_count"] == 0
    assert result.intrabar_diagnostic["subtimeframe_interval"] == "0 days 00:01:00"


def test_subtimeframe_residual_same_subbar_is_pessimistic_and_audited():
    parent = _parent_bar(high=104.5, low=97.0)
    result = simulate_trades(
        parent,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="subtimeframe",
        subtimeframe_data=_subtimeframe_data(residual_both_hit=True),
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    assert result.trades.iloc[0]["exit_reason"] == "SL_subtimeframe"
    assert result.trades.iloc[0]["intrabar_resolution"] == "subtimeframe_residual_sl_first"
    assert result.intrabar_diagnostic["ambiguous_resolution_count"] == 1


@pytest.mark.parametrize("target_on_entry_subbar", [False, True])
def test_subtimeframe_never_credits_target_before_or_unordered_with_entry(
    target_on_entry_subbar,
):
    parent = _parent_bar(high=104.0, low=98.0, close=100.0)
    parent.loc[1, "open"] = 102.0
    result = simulate_trades(
        parent,
        _three_c_signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="subtimeframe",
        subtimeframe_data=_preentry_subtimeframe_data(
            target_on_entry_subbar=target_on_entry_subbar
        ),
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    assert result.trades.iloc[0]["exit_reason"] == "EOD"
    assert result.intrabar_diagnostic["ambiguous_resolution_count"] == int(target_on_entry_subbar)


def test_subtimeframe_requires_complete_reconciling_finer_data():
    parent = _parent_bar(high=104.5, low=97.0)
    with pytest.raises(ValueError, match="requires subtimeframe_data"):
        simulate_trades(
            parent,
            _signal(),
            tick_size=1.0,
            point_value=1.0,
            stop_loss_ticks=2,
            take_profit_ticks=4,
            intrabar_model="subtimeframe",
        )
    with pytest.raises(ValueError, match="incomplete subtimeframe coverage"):
        simulate_trades(
            parent,
            _signal(),
            tick_size=1.0,
            point_value=1.0,
            stop_loss_ticks=2,
            take_profit_ticks=4,
            intrabar_model="subtimeframe",
            subtimeframe_data=_subtimeframe_data().iloc[:-1],
        )


def test_conservative_subtimeframe_uses_sl_first_only_for_unavailable_parent_bar():
    parent = _parent_bar(high=104.5, low=97.0)
    incomplete = _subtimeframe_data().drop(index=6).reset_index(drop=True)

    with pytest.raises(ValueError, match="incomplete subtimeframe coverage"):
        simulate_trades(
            parent,
            _signal(),
            tick_size=1.0,
            point_value=1.0,
            stop_loss_ticks=2,
            take_profit_ticks=4,
            intrabar_model="subtimeframe",
            subtimeframe_data=incomplete,
        )

    result = simulate_trades(
        parent,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="subtimeframe_conservative",
        subtimeframe_data=incomplete,
        return_result=True,
    )

    assert isinstance(result, SimulationResult)
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "SL_subtimeframe_fallback"
    assert trade["intrabar_resolution"] == "subtimeframe_conservative_fallback_sl_first"
    assert result.intrabar_diagnostic["subtimeframe_resolved_count"] == 0
    assert result.intrabar_diagnostic["subtimeframe_fallback_exit_count"] == 1
    assert result.intrabar_diagnostic["subtimeframe_fallback_parent_count"] == 1
    assert result.intrabar_diagnostic["subtimeframe_fallback_parent_bars"] == [
        {
            "bar_index": 1,
            "timestamp": "2026-01-05 09:35:00-05:00",
            "reason": "incomplete coverage: expected 5, observed 4",
        }
    ]


def test_conservative_subtimeframe_replays_complete_parent_bars():
    parent = _parent_bar(high=104.5, low=97.0)
    result = simulate_trades(
        parent,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="subtimeframe_conservative",
        subtimeframe_data=_subtimeframe_data(),
        return_result=True,
    )

    assert isinstance(result, SimulationResult)
    assert result.trades.iloc[0]["exit_reason"] == "TP_subtimeframe"
    assert result.intrabar_diagnostic["subtimeframe_resolved_count"] == 1
    assert result.intrabar_diagnostic["subtimeframe_fallback_parent_count"] == 0


def test_conservative_context_skips_ohlc_validation_for_unreplayable_groups():
    parent = _parent_bar(high=104.5, low=97.0)
    incomplete = _subtimeframe_data().drop(index=6).reset_index(drop=True)
    parent.loc[1, "high"] = parent.loc[1, "low"] - 1
    incomplete.loc[6, "open"] = float("nan")

    context = prepare_subtimeframe_conservative_context(
        parent,
        incomplete,
        tick_size=1.0,
    )

    assert set(context.groups) == {0}
    assert context.fallback_reasons == {1: "incomplete coverage: expected 5, observed 4"}


def test_subtimeframe_rejects_offset_nonfinite_and_invalid_ohlc_rows():
    parent = _parent_bar(high=104.5, low=97.0)
    offset = _subtimeframe_data()
    offset["timestamp"] = offset["timestamp"] + pd.Timedelta(seconds=30)
    malformed_nan = _subtimeframe_data()
    malformed_nan.loc[2, "open"] = float("nan")
    malformed_range = _subtimeframe_data()
    malformed_range.loc[2, "high"] = malformed_range.loc[2, "low"] - 1
    with pytest.raises(ValueError, match="not exactly aligned"):
        simulate_trades(
            parent,
            _signal(),
            tick_size=1.0,
            point_value=1.0,
            stop_loss_ticks=2,
            take_profit_ticks=4,
            intrabar_model="subtimeframe",
            subtimeframe_data=offset,
        )
    conservative_offset = simulate_trades(
        parent,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="subtimeframe_conservative",
        subtimeframe_data=offset,
        return_result=True,
    )
    assert isinstance(conservative_offset, SimulationResult)
    assert conservative_offset.intrabar_diagnostic["subtimeframe_fallback_parent_count"] == 2

    for frame, message in ((malformed_nan, "non-finite"), (malformed_range, "invariants")):
        for model in ("subtimeframe", "subtimeframe_conservative"):
            with pytest.raises(ValueError, match=message):
                simulate_trades(
                    parent,
                    _signal(),
                    tick_size=1.0,
                    point_value=1.0,
                    stop_loss_ticks=2,
                    take_profit_ticks=4,
                    intrabar_model=model,
                    subtimeframe_data=frame,
                )


def test_default_and_explicit_sl_first_preserve_legacy_schema_and_values():
    parent = _parent_bar(high=104.5, low=97.0)
    implicit = simulate_trades(
        parent,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
    )
    explicit = simulate_trades(
        parent,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="sl_first",
    )
    pd.testing.assert_frame_equal(implicit, explicit)
    assert "intrabar_model" not in implicit.columns
    assert implicit.iloc[0]["exit_reason"] == "SL"


def test_grid_records_fixed_intrabar_assumption_and_diagnostics():
    grid = run_sl_tp_grid(
        _parent_bar(high=104.0, low=94.0),
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks_values=[2],
        take_profit_ticks_values=[4],
        intrabar_model="path_open_proximity",
    )
    assert grid.loc[0, "intrabar_model"] == "path_open_proximity"
    assert grid.loc[0, "intrabar_both_hit_count"] == 1
    assert grid.loc[0, "intrabar_ambiguous_count"] == 0


@pytest.mark.parametrize(
    "model",
    ["sl_first", "path_open_proximity", "subtimeframe", "subtimeframe_conservative"],
)
def test_intrabar_models_are_future_shock_safe(model):
    parent = _parent_bar(high=104.5, low=97.0)
    subtimeframe = _subtimeframe_data()
    kwargs = (
        {"subtimeframe_data": subtimeframe}
        if model in {"subtimeframe", "subtimeframe_conservative"}
        else {}
    )
    before = simulate_trades(
        parent,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model=model,
        **kwargs,
    )

    future_parent = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-05 09:40", tz=TZ)],
            "open": [100.0],
            "high": [200.0],
            "low": [1.0],
            "close": [150.0],
            "volume": [9999],
        }
    )
    extended_parent = pd.concat([parent, future_parent], ignore_index=True)
    if model in {"subtimeframe", "subtimeframe_conservative"}:
        future_sub = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-05 09:40", periods=5, freq="1min", tz=TZ),
                "open": [100.0, 150.0, 150.0, 150.0, 150.0],
                "high": [200.0] * 5,
                "low": [1.0] * 5,
                "close": [150.0] * 5,
                "volume": [200] * 5,
            }
        )
        kwargs = {
            "subtimeframe_data": pd.concat(
                [subtimeframe, future_sub],
                ignore_index=True,
            )
        }
    after = simulate_trades(
        extended_parent,
        _signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model=model,
        **kwargs,
    )
    pd.testing.assert_frame_equal(before, after)
