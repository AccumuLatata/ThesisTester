from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from thesistester.engine import sim_core as sim_core_mod
from thesistester.engine.backtest import simulate_trades
from thesistester.engine.exit_management import (
    initial_exit_management_state,
    update_exit_management_after_bar,
)
from thesistester.engine.intrabar import SubtimeframeContext, resolve_ohlc_bar
from thesistester.engine.sim_core import (
    BarData,
    _can_vectorize_fixed_sl_first_walk,
    _exit_walk_bounds,
    _fixed_bracket_prices,
    _walk_trade_exit_serial,
    compute_session_close_cap,
    resolve_trade_bar,
    walk_trade_exit,
)
from tests.benchmarks.fixtures import benchmark_ohlcv, benchmark_signals


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=2, freq="1min"),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
        }
    )


def test_bar_data_snapshots_ohlc_without_mutating_source():
    source = _bars()
    before = source.copy(deep=True)

    bars = BarData.from_frame(source)

    assert bars.at(1).open == 101.0
    assert bars.at(1).high == 103.0
    assert type(bars.at(1).open) is float
    assert_frame_equal(source, before)
    source.loc[1, "open"] = 0.0
    assert bars.at(1).open == 101.0
    assert float(bars.open[1]) == 101.0


def test_bar_data_stores_write_protected_float64_arrays():
    bars = BarData.from_frame(_bars())
    for column in (bars.open, bars.high, bars.low, bars.close):
        assert isinstance(column, np.ndarray)
        assert column.dtype == np.float64
        assert column.flags.writeable is False
        assert column.flags.c_contiguous
        assert column.ndim == 1
        assert column.shape == (2,)
    with pytest.raises((ValueError, RuntimeError)):
        bars.open[0] = 0.0


def _float_bits(value: float) -> int:
    return int(np.float64(value).view(np.uint64))


def test_bar_data_at_is_bit_identical_to_legacy_float_coercion():
    source = _bars()
    bars = BarData.from_frame(source)
    other = BarData.from_frame(source)

    assert bars == other
    assert bars is not other
    assert hash(bars) == hash(other)

    mutated = source.copy()
    mutated.loc[0, "open"] = 0.0
    assert bars != BarData.from_frame(mutated)

    for index, row in source.iterrows():
        actual = bars.at(int(index))
        for name in ("open", "high", "low", "close"):
            legacy = float(row[name])
            current = getattr(actual, name)
            assert type(current) is float
            assert _float_bits(legacy) == _float_bits(current)


def test_bar_data_keeps_legacy_fail_closed_coercion():
    source = _bars()

    datetime_open = source.copy()
    datetime_open["open"] = pd.to_datetime(["2026-01-05 09:30", "2026-01-05 09:31"])
    with pytest.raises(TypeError):
        BarData.from_frame(datetime_open)

    nullable = source.copy()
    nullable["open"] = pd.Series([100.0, pd.NA], dtype="Float64")
    with pytest.raises(TypeError):
        BarData.from_frame(nullable)

    object_none = source.copy()
    object_none["open"] = pd.Series([100.0, None], dtype=object)
    with pytest.raises(TypeError):
        BarData.from_frame(object_none)


def test_serial_core_resolution_matches_legacy_ohlc_resolver():
    bars = BarData.from_frame(_bars())
    bar, actual = resolve_trade_bar(
        bars,
        bar_index=0,
        intrabar_model="sl_first",
        subtimeframe_context=None,
        stop_price=99.5,
        target_price=101.5,
        direction="long",
        entry_activation_price=None,
    )
    expected = resolve_ohlc_bar(
        open_price=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        stop_price=99.5,
        target_price=101.5,
        direction="long",
        model="sl_first",
        entry_price=None,
    )

    assert actual == expected


def test_strict_subtimeframe_never_uses_a_missing_group_as_fallback():
    with pytest.raises(KeyError):
        resolve_trade_bar(
            BarData.from_frame(_bars()),
            bar_index=0,
            intrabar_model="subtimeframe",
            subtimeframe_context=SubtimeframeContext(
                pd.Timedelta("1min"),
                pd.Timedelta("15s"),
                {},
            ),
            stop_price=99.5,
            target_price=101.5,
            direction="long",
            entry_activation_price=None,
        )


def test_conservative_fallback_respects_parent_bar_entry_gating():
    _, resolution = resolve_trade_bar(
        BarData.from_frame(_bars()),
        bar_index=0,
        intrabar_model="subtimeframe_conservative",
        subtimeframe_context=SubtimeframeContext(
            pd.Timedelta("1min"),
            pd.Timedelta("15s"),
            {},
            fallback_reasons={0: "incomplete coverage"},
        ),
        stop_price=98.0,
        target_price=101.5,
        direction="long",
        entry_activation_price=100.0,
    )

    assert resolution.exit_kind is None
    assert resolution.ambiguous is True
    assert resolution.subtimeframe_fallback is True


def test_session_close_cap_uses_entry_date_clock():
    stamps = pd.DatetimeIndex(
        [
            "2026-01-05 15:50:00",
            "2026-01-05 15:51:00",
            "2026-01-05 16:00:00",
            "2026-01-06 09:30:00",
        ]
    )
    local = pd.Series(pd.to_datetime(stamps))
    cap = compute_session_close_cap(
        local,
        entry_bar_index=0,
        entry_local_ts=local.iloc[0],
        session_close=time(16, 0, 0),
        n_bars=len(local),
    )
    assert cap.empty is False
    assert cap.session_cap_bar == 2
    assert cap.data_end_before_session_close is False


def test_walk_trade_exit_hits_fixed_stop_on_entry_bar():
    bars = BarData.from_frame(_bars())
    walk = walk_trade_exit(
        bars,
        direction="long",
        entry_price=100.0,
        theoretical_entry_price=100.0,
        entry_bar_index=0,
        entry_model="next_bar_open",
        trigger="touch",
        sl_pts=1.0,
        tp_pts=10.0,
        n_bars=2,
        allow_same_bar_exit=True,
        max_holding_bars=None,
        session_cap_bar=None,
        exit_management_active=False,
        tick_size=0.25,
        breakeven_after_r=None,
        trailing_after_r=None,
        trailing_distance_ticks=None,
        intrabar_model="sl_first",
        subtimeframe_context=None,
    )
    assert walk.bracket_exit is True
    assert walk.exit_bar_index == 0
    assert walk.resolution is not None
    assert walk.resolution.exit_kind == "SL"
    assert walk.stop_price == 99.0
    assert walk.target_price == 110.0


def _ohlc_frame(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=len(rows), freq="1min"),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
        }
    )


def _public_walk_kwargs(**overrides):
    kwargs = dict(
        direction="long",
        entry_price=100.0,
        theoretical_entry_price=100.0,
        entry_bar_index=0,
        entry_model="next_bar_open",
        trigger="touch",
        sl_pts=1.0,
        tp_pts=1.0,
        n_bars=2,
        allow_same_bar_exit=True,
        max_holding_bars=None,
        session_cap_bar=None,
        exit_management_active=False,
        tick_size=0.25,
        breakeven_after_r=None,
        trailing_after_r=None,
        trailing_distance_ticks=None,
        intrabar_model="sl_first",
        subtimeframe_context=None,
    )
    kwargs.update(overrides)
    return kwargs


def _serial_walk_from_public_kwargs(bars: BarData, **kwargs):
    """Replay the C-19 loop with the same brackets/bounds as ``walk_trade_exit``."""
    stop_price, target_price = _fixed_bracket_prices(
        direction=kwargs["direction"],
        entry_price=kwargs["entry_price"],
        sl_pts=kwargs["sl_pts"],
        tp_pts=kwargs["tp_pts"],
    )
    stop_state = initial_exit_management_state(
        initial_stop=stop_price,
        entry_price=kwargs["entry_price"],
        direction=kwargs["direction"],
    )
    start_bar, max_bar, time_cap_bar = _exit_walk_bounds(
        n_bars=kwargs["n_bars"],
        entry_bar_index=kwargs["entry_bar_index"],
        allow_same_bar_exit=kwargs["allow_same_bar_exit"],
        max_holding_bars=kwargs["max_holding_bars"],
        session_cap_bar=kwargs["session_cap_bar"],
    )
    if (
        kwargs["exit_management_active"]
        and not kwargs["allow_same_bar_exit"]
        and kwargs["entry_model"] == "next_bar_open"
        and kwargs["entry_bar_index"] < max_bar
    ):
        entry_bar = bars.at(kwargs["entry_bar_index"])
        stop_state = update_exit_management_after_bar(
            state=stop_state,
            direction=kwargs["direction"],
            entry_price=kwargs["entry_price"],
            initial_stop=stop_price,
            tick_size=kwargs["tick_size"],
            risk_points=kwargs["sl_pts"],
            bar_high=entry_bar.high,
            bar_low=entry_bar.low,
            bar_index=kwargs["entry_bar_index"],
            breakeven_after_r=kwargs["breakeven_after_r"],
            trailing_after_r=kwargs["trailing_after_r"],
            trailing_distance_ticks=kwargs["trailing_distance_ticks"],
        )
    return _walk_trade_exit_serial(
        bars,
        direction=kwargs["direction"],
        entry_price=kwargs["entry_price"],
        theoretical_entry_price=kwargs["theoretical_entry_price"],
        entry_bar_index=kwargs["entry_bar_index"],
        entry_model=kwargs["entry_model"],
        trigger=kwargs["trigger"],
        stop_price=stop_price,
        target_price=target_price,
        stop_state=stop_state,
        start_bar=start_bar,
        max_bar=max_bar,
        time_cap_bar=time_cap_bar,
        exit_management_active=kwargs["exit_management_active"],
        tick_size=kwargs["tick_size"],
        sl_pts=kwargs["sl_pts"],
        breakeven_after_r=kwargs["breakeven_after_r"],
        trailing_after_r=kwargs["trailing_after_r"],
        trailing_distance_ticks=kwargs["trailing_distance_ticks"],
        intrabar_model=kwargs["intrabar_model"],
        subtimeframe_context=kwargs["subtimeframe_context"],
    )


def _assert_walks_equal(actual, expected) -> None:
    assert actual.stop_price == expected.stop_price
    assert actual.target_price == expected.target_price
    assert actual.stop_state == expected.stop_state
    assert actual.exit_bar_index == expected.exit_bar_index
    assert actual.theoretical_exit_price == expected.theoretical_exit_price
    assert actual.resolution == expected.resolution
    assert actual.mae_pts == expected.mae_pts
    assert actual.mfe_pts == expected.mfe_pts
    assert actual.pending_intrabar_ambiguity == expected.pending_intrabar_ambiguity
    assert actual.start_bar == expected.start_bar
    assert actual.max_bar == expected.max_bar
    assert actual.time_cap_bar == expected.time_cap_bar
    assert actual.bracket_exit == expected.bracket_exit
    assert actual.parent_both_hit == expected.parent_both_hit
    assert actual.bracket_ambiguous == expected.bracket_ambiguous
    assert actual.proximity_tie == expected.proximity_tie
    assert actual.subtimeframe_resolved == expected.subtimeframe_resolved
    assert actual.subtimeframe_fallback == expected.subtimeframe_fallback


def test_fixed_sl_first_walk_is_eligible_for_e10_vectorization():
    assert (
        _can_vectorize_fixed_sl_first_walk(
            intrabar_model="sl_first",
            exit_management_active=False,
            trigger="touch",
            start_bar=0,
            entry_bar_index=0,
        )
        is True
    )
    assert (
        _can_vectorize_fixed_sl_first_walk(
            intrabar_model="sl_first",
            exit_management_active=False,
            trigger="3c",
            start_bar=0,
            entry_bar_index=0,
        )
        is False
    )
    assert (
        _can_vectorize_fixed_sl_first_walk(
            intrabar_model="sl_first",
            exit_management_active=False,
            trigger="confirm_3bar",
            start_bar=0,
            entry_bar_index=0,
        )
        is False
    )
    assert (
        _can_vectorize_fixed_sl_first_walk(
            intrabar_model="sl_first",
            exit_management_active=False,
            trigger="3c",
            start_bar=1,
            entry_bar_index=0,
        )
        is True
    )
    assert (
        _can_vectorize_fixed_sl_first_walk(
            intrabar_model="sl_first",
            exit_management_active=True,
            trigger="touch",
            start_bar=0,
            entry_bar_index=0,
        )
        is False
    )
    assert (
        _can_vectorize_fixed_sl_first_walk(
            intrabar_model="path_open_proximity",
            exit_management_active=False,
            trigger="touch",
            start_bar=0,
            entry_bar_index=0,
        )
        is False
    )


@pytest.mark.parametrize(
    "label,rows,overrides,expect_vectorized,expect_kind",
    [
        (
            "long_sl_only",
            [(100.0, 102.0, 99.0, 101.0), (101.0, 103.0, 100.0, 102.0)],
            dict(sl_pts=1.0, tp_pts=10.0, n_bars=2),
            True,
            "SL",
        ),
        (
            "long_tp_only",
            [(100.0, 102.0, 99.5, 101.0), (101.0, 103.0, 100.0, 102.0)],
            dict(sl_pts=10.0, tp_pts=1.5, n_bars=2),
            True,
            "TP",
        ),
        (
            "long_both_hit",
            [(100.0, 102.0, 98.0, 101.0), (101.0, 103.0, 100.0, 102.0)],
            dict(sl_pts=1.5, tp_pts=1.5, n_bars=2),
            True,
            "SL",
        ),
        (
            "long_later_sl_after_mfe",
            [
                (100.0, 101.0, 99.8, 100.5),
                (100.5, 103.0, 100.2, 102.0),
                (102.0, 102.5, 98.5, 99.0),
            ],
            dict(sl_pts=1.2, tp_pts=10.0, n_bars=3),
            True,
            "SL",
        ),
        (
            "short_both_hit",
            [(100.0, 102.0, 98.0, 99.0), (99.0, 100.0, 97.0, 98.0)],
            dict(direction="short", sl_pts=1.5, tp_pts=1.5, n_bars=2),
            True,
            "SL",
        ),
        (
            "short_tp_only",
            [(100.0, 100.4, 98.0, 99.0), (99.0, 100.0, 97.0, 98.0)],
            dict(direction="short", sl_pts=10.0, tp_pts=1.5, n_bars=2),
            True,
            "TP",
        ),
        (
            "session_cap_before_sl",
            [
                (100.0, 100.2, 99.8, 100.0),
                (100.0, 100.2, 99.8, 100.0),
                (100.0, 100.2, 98.0, 99.0),
            ],
            dict(sl_pts=1.5, tp_pts=10.0, n_bars=3, session_cap_bar=1),
            True,
            None,
        ),
        (
            "empty_window_last_bar",
            [(100.0, 102.0, 98.0, 101.0)],
            dict(n_bars=1, allow_same_bar_exit=False, sl_pts=1.0, tp_pts=1.0),
            True,
            None,
        ),
        (
            "three_c_entry_bar_stays_serial",
            [(100.0, 102.0, 98.0, 101.0)],
            dict(trigger="3c", sl_pts=1.5, tp_pts=1.5, n_bars=1),
            False,
            "SL",
        ),
        (
            "three_c_after_entry_vectorizes",
            [(100.0, 100.2, 99.8, 100.0), (100.0, 102.0, 98.0, 101.0)],
            dict(trigger="3c", allow_same_bar_exit=False, sl_pts=1.5, tp_pts=1.5, n_bars=2),
            True,
            "SL",
        ),
    ],
)
def test_vectorized_sl_first_walk_matches_serial_on_hit_paths(
    label, rows, overrides, expect_vectorized, expect_kind
):
    bars = BarData.from_frame(_ohlc_frame(rows))
    kwargs = _public_walk_kwargs(**overrides)
    start_bar, _, _ = _exit_walk_bounds(
        n_bars=kwargs["n_bars"],
        entry_bar_index=kwargs["entry_bar_index"],
        allow_same_bar_exit=kwargs["allow_same_bar_exit"],
        max_holding_bars=kwargs["max_holding_bars"],
        session_cap_bar=kwargs["session_cap_bar"],
    )
    assert (
        _can_vectorize_fixed_sl_first_walk(
            intrabar_model=kwargs["intrabar_model"],
            exit_management_active=kwargs["exit_management_active"],
            trigger=kwargs["trigger"],
            start_bar=start_bar,
            entry_bar_index=kwargs["entry_bar_index"],
        )
        is expect_vectorized
    )
    actual = walk_trade_exit(bars, **kwargs)
    _assert_walks_equal(actual, _serial_walk_from_public_kwargs(bars, **kwargs))
    kind = None if actual.resolution is None else actual.resolution.exit_kind
    assert kind == expect_kind, label


@pytest.mark.parametrize(
    "sl_pts,tp_pts,direction,allow_same_bar_exit,max_holding_bars",
    [
        (1.0, 10.0, "long", True, None),
        (10.0, 1.0, "long", True, None),
        (1.0, 1.0, "long", True, None),
        (1.0, 10.0, "short", True, None),
        (25.0, 25.0, "long", True, 50),
        (25.0, 25.0, "short", False, 50),
    ],
)
def test_vectorized_sl_first_walk_matches_serial_on_r22_no_hit_fixture(
    sl_pts, tp_pts, direction, allow_same_bar_exit, max_holding_bars
):
    """R22 ruler bars have a 0.04-pt range, so 1-pt+ brackets never hit."""
    bars = BarData.from_frame(benchmark_ohlcv(bars=80))
    kwargs = _public_walk_kwargs(
        direction=direction,
        sl_pts=sl_pts,
        tp_pts=tp_pts,
        n_bars=80,
        allow_same_bar_exit=allow_same_bar_exit,
        max_holding_bars=max_holding_bars,
    )
    actual = walk_trade_exit(bars, **kwargs)
    _assert_walks_equal(actual, _serial_walk_from_public_kwargs(bars, **kwargs))
    assert actual.bracket_exit is False


def test_r22_holding_cap_walk_matches_serial_on_benchmark_fixture():
    """QI-14-03: R22 ruler path stays serial-equal after E-10 vectorization."""
    frame = benchmark_ohlcv(bars=500)
    bars = BarData.from_frame(frame)
    kwargs = _public_walk_kwargs(
        direction="long",
        entry_price=float(frame["open"].iloc[1]),
        theoretical_entry_price=float(frame["open"].iloc[1]),
        entry_bar_index=1,
        sl_pts=25.0,
        tp_pts=25.0,
        n_bars=500,
        max_holding_bars=50,
    )
    actual = walk_trade_exit(bars, **kwargs)
    expected = _serial_walk_from_public_kwargs(bars, **kwargs)
    _assert_walks_equal(actual, expected)
    assert actual.bracket_exit is False
    assert actual.max_bar == 50


def test_vectorized_mae_mfe_match_serial_when_a_bar_is_nan():
    bars = BarData.from_frame(
        _ohlc_frame(
            [
                (100.0, 101.0, 99.5, 100.5),
                (100.5, float("nan"), 100.2, 100.4),
                (100.4, 100.6, 98.0, 99.0),
            ]
        )
    )
    kwargs = _public_walk_kwargs(sl_pts=1.5, tp_pts=10.0, n_bars=3)
    actual = walk_trade_exit(bars, **kwargs)
    expected = _serial_walk_from_public_kwargs(bars, **kwargs)
    _assert_walks_equal(actual, expected)
    assert actual.exit_bar_index == 2
    assert actual.mae_pts == 2.0
    assert actual.mfe_pts == 1.0


def test_simulate_trades_vectorized_matches_forced_serial(monkeypatch):
    """Full P7+P&L path: E-10 walk equals the C-19 loop on hitting + R22 bars."""
    hitting = _ohlc_frame(
        [
            (100.0, 105.0, 95.0, 100.5),
            (100.5, 105.5, 95.5, 101.0),
            (101.0, 106.0, 96.0, 101.5),
            (101.5, 106.5, 96.5, 102.0),
        ]
    )
    hitting["volume"] = 100.0
    signals = pd.DataFrame(
        {
            "signal_id": [1, 2],
            "bar_index": [0, 1],
            "trigger": ["touch", "touch"],
            "direction": ["long", "short"],
        }
    )
    common = dict(
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks=8,
        take_profit_ticks=8,
    )
    vectorized = simulate_trades(hitting, signals, **common)
    monkeypatch.setattr(sim_core_mod, "_can_vectorize_fixed_sl_first_walk", lambda **_: False)
    serial = simulate_trades(hitting, signals, **common)
    assert_frame_equal(vectorized.reset_index(drop=True), serial.reset_index(drop=True))
    assert not vectorized.empty
    assert set(vectorized["exit_reason"]) <= {"SL", "TP"}

    ruler = benchmark_ohlcv(bars=80)
    ruler_signals = benchmark_signals(bars=80, signal_count=6)
    ruler_kwargs = dict(
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks=100,
        take_profit_ticks=100,
        max_holding_bars=10,
    )
    monkeypatch.setattr(
        sim_core_mod,
        "_can_vectorize_fixed_sl_first_walk",
        _can_vectorize_fixed_sl_first_walk,
    )
    ruler_vectorized = simulate_trades(ruler, ruler_signals, **ruler_kwargs)
    monkeypatch.setattr(sim_core_mod, "_can_vectorize_fixed_sl_first_walk", lambda **_: False)
    ruler_serial = simulate_trades(ruler, ruler_signals, **ruler_kwargs)
    assert_frame_equal(
        ruler_vectorized.reset_index(drop=True), ruler_serial.reset_index(drop=True)
    )
