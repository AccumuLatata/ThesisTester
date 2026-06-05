"""Phase 5 backtest engine tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thesistester.engine.backtest import simulate_trades
from thesistester.engine.signals import generate_signals


TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 50.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bar(ts: str, o: float, h: float, l: float, c: float, vol: float = 100.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": o, "high": h, "low": l, "close": c, "volume": vol,
    }


def _df(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _signal(
    bar_index: int,
    trigger: str = "touch",
    direction: str = "long",
    status: str = "candidate",
    entry_ref: float = 100.0,
    zone_low: float = 99.5,
    zone_high: float = 100.5,
    signal_id: int = 0,
    **extra,
) -> pd.DataFrame:
    row = {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
        "bar_index": bar_index,
        "trigger": trigger,
        "direction": direction,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "zone_mid": (zone_low + zone_high) / 2.0,
        "level_count": 2,
        "level_names": "A|B",
        "entry_reference_price": entry_ref,
        "entry_model": "candidate_next_bar_open",
        "status": status,
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }
    row.update(extra)
    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# Entry tests
# ---------------------------------------------------------------------------


def test_simple_long_enters_next_bar_open():
    """Simple trigger long enters at next-bar open (no look-ahead)."""
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0),
        _bar("2026-01-02 09:31", 102.0, 110.0, 101.0, 109.0),  # entry bar, wide TP hit
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="long")
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)
    assert len(trades) == 1
    assert trades.iloc[0]["entry_price"] == 102.0
    assert trades.iloc[0]["entry_model"] == "next_bar_open"
    assert trades.iloc[0]["entry_bar_index"] == 1


def test_simple_short_enters_next_bar_open():
    """Simple trigger short enters at next-bar open."""
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0),
        _bar("2026-01-02 09:31", 98.0, 99.0, 90.0, 91.0),  # entry bar, wide TP hit
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="short")
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)
    assert len(trades) == 1
    assert trades.iloc[0]["entry_price"] == 98.0
    assert trades.iloc[0]["entry_bar_index"] == 1
    assert trades.iloc[0]["direction"] == "short"


def test_3c_filled_enters_on_entry_bar():
    """3c filled signal enters on entry_bar_index at retrace_entry_price."""
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0),
        _bar("2026-01-02 09:31", 100.0, 101.0, 99.0, 100.0),
        _bar("2026-01-02 09:32", 100.0, 101.0, 99.0, 100.0),  # signal bar
        _bar("2026-01-02 09:33", 100.0, 110.0, 99.0, 109.0),  # TP bar
    )
    sigs = _signal(
        bar_index=2, trigger="3c", direction="long",
        status="filled", entry_ref=99.0, entry_bar_index=2, retrace_entry_price=99.0,
    )
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)
    assert len(trades) == 1
    assert trades.iloc[0]["entry_price"] == 99.0
    assert trades.iloc[0]["entry_bar_index"] == 2
    assert trades.iloc[0]["entry_model"] == "3c_retrace_market"


def test_3c_void_is_skipped():
    """3c void signals must be skipped — no trade produced."""
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0),
        _bar("2026-01-02 09:31", 100.0, 101.0, 99.0, 100.0),
        _bar("2026-01-02 09:32", 100.0, 101.0, 99.0, 100.0),
    )
    sigs = _signal(
        bar_index=2, trigger="3c", direction="long",
        status="void", entry_ref=99.0, entry_bar_index=None, retrace_entry_price=None,
    )
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)
    assert trades.empty


def test_3c_generated_filled_signal_enters_and_void_skips():
    df = _df(
        _bar("2026-01-02 09:30", 101.0, 101.2, 99.9, 100.3),
        _bar("2026-01-02 09:31", 100.4, 100.9, 99.9, 100.7),
        _bar("2026-01-02 09:32", 101.0, 101.3, 100.0, 101.1),
        _bar("2026-01-02 09:33", 101.1, 102.5, 100.9, 102.0),
    )
    zones = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
                "bar_index": 0,
                "zone_low": 100.0,
                "zone_high": 100.0,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "A",
                "level_prices": "100.0",
            }
        ]
    )
    signals = generate_signals(
        df,
        zones,
        trigger="3c",
        direction="long",
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(signals) == 1
    sig = signals.iloc[0]
    assert sig["status"] == "filled"

    trades = simulate_trades(df, signals, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)
    assert len(trades) == 1
    assert trades.iloc[0]["entry_price"] == pytest.approx(sig["retrace_entry_price"])

    void_signals = signals.copy()
    void_signals.loc[:, "status"] = "void"
    void_trades = simulate_trades(df, void_signals, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)
    assert void_trades.empty


# ---------------------------------------------------------------------------
# Exit tests
# ---------------------------------------------------------------------------


def test_long_tp_hit():
    """Long TP hit returns positive R and exit_reason='TP'."""
    entry_open = 100.0
    sl_ticks = 4
    tp_ticks = 8
    tp_price = entry_open + tp_ticks * TICK  # 101.0

    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),   # signal bar
        _bar("2026-01-02 09:31", entry_open, tp_price + 1, 99.8, tp_price + 0.5),  # TP hit
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="long")
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=sl_ticks, take_profit_ticks=tp_ticks)
    t = trades.iloc[0]
    assert t["exit_reason"] == "TP"
    assert t["r_multiple"] > 0


def test_long_sl_hit():
    """Long SL hit returns negative R and exit_reason='SL'."""
    entry_open = 100.0
    sl_ticks = 4
    sl_price = entry_open - sl_ticks * TICK  # 99.0

    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", entry_open, 100.5, sl_price - 1, 99.2),  # SL hit
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="long")
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=sl_ticks, take_profit_ticks=8)
    t = trades.iloc[0]
    assert t["exit_reason"] == "SL"
    assert t["r_multiple"] < 0


def test_short_tp_hit():
    """Short TP hit returns positive R."""
    entry_open = 100.0
    sl_ticks = 4
    tp_ticks = 8
    tp_price = entry_open - tp_ticks * TICK  # 98.0

    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", entry_open, 100.2, tp_price - 1, tp_price - 0.5),  # TP hit
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="short")
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=sl_ticks, take_profit_ticks=tp_ticks)
    t = trades.iloc[0]
    assert t["exit_reason"] == "TP"
    assert t["r_multiple"] > 0


def test_short_sl_hit():
    """Short SL hit returns negative R."""
    entry_open = 100.0
    sl_ticks = 4
    sl_price = entry_open + sl_ticks * TICK  # 101.0

    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", entry_open, sl_price + 1, 99.5, 101.5),  # SL hit
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="short")
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=sl_ticks, take_profit_ticks=8)
    t = trades.iloc[0]
    assert t["exit_reason"] == "SL"
    assert t["r_multiple"] < 0


def test_sl_first_when_both_hit_same_bar():
    """When SL and TP are both reachable in one bar, SL wins (pessimistic rule)."""
    entry_open = 100.0
    sl_ticks = 4
    tp_ticks = 8
    sl_price = entry_open - sl_ticks * TICK   # 99.0 for long
    tp_price = entry_open + tp_ticks * TICK   # 102.0

    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        # Both SL (low=98.5 < 99.0) and TP (high=102.5 > 102.0) reachable
        _bar("2026-01-02 09:31", entry_open, tp_price + 0.5, sl_price - 0.5, 101.0),
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="long")
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=sl_ticks, take_profit_ticks=tp_ticks)
    t = trades.iloc[0]
    assert t["exit_reason"] == "SL"
    assert t["exit_price"] == pytest.approx(sl_price)
    assert t["r_multiple"] < 0


def test_max_holding_bars_time_exit():
    """max_holding_bars forces TIME exit when SL/TP not hit."""
    entry_open = 100.0
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.3, 99.7, 100.0),
        _bar("2026-01-02 09:31", entry_open, 100.3, 99.8, 100.1),
        _bar("2026-01-02 09:32", 100.1, 100.4, 99.9, 100.2),
        _bar("2026-01-02 09:33", 100.2, 100.5, 100.0, 100.3),
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="long")
    # Very tight SL/TP that won't be hit; force exit after 2 holding bars
    trades = simulate_trades(
        df, sigs, TICK, POINT_VALUE,
        stop_loss_ticks=100,   # far away
        take_profit_ticks=100,  # far away
        max_holding_bars=2,
    )
    t = trades.iloc[0]
    assert t["exit_reason"] == "TIME"
    # entry_bar=1, max_bar = 1 + 2 - 1 = 2 → exit at bar 2
    assert t["exit_bar_index"] == 2


def test_end_of_data_eod_exit():
    """When no SL/TP hit and no max_holding_bars, exit at end of data (EOD)."""
    entry_open = 100.0
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.3, 99.7, 100.0),
        _bar("2026-01-02 09:31", entry_open, 100.2, 99.9, 100.1),
        _bar("2026-01-02 09:32", 100.1, 100.3, 100.0, 100.2),
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="long")
    trades = simulate_trades(
        df, sigs, TICK, POINT_VALUE,
        stop_loss_ticks=200,   # far away
        take_profit_ticks=200,  # far away
    )
    t = trades.iloc[0]
    assert t["exit_reason"] == "EOD"
    assert t["exit_bar_index"] == len(df) - 1


def test_zero_stop_loss_raises():
    """stop_loss_ticks <= 0 must raise ValueError."""
    df = _df(_bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0))
    sigs = _signal(bar_index=0)
    with pytest.raises(ValueError):
        simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=0, take_profit_ticks=8)


def test_negative_stop_loss_raises():
    """Negative stop_loss_ticks must also raise ValueError."""
    df = _df(_bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0))
    sigs = _signal(bar_index=0)
    with pytest.raises(ValueError):
        simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=-4, take_profit_ticks=8)


def test_signal_beyond_data_skipped():
    """Signal at last bar has no next bar — must be skipped (no trade)."""
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0),
    )
    sigs = _signal(bar_index=0, trigger="touch", direction="long")
    # bar_index=0, entry_bar_index would be 1 which is >= len(df)=1
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)
    assert trades.empty


def test_empty_signals_returns_empty():
    """Empty signals produces empty trades DataFrame."""
    df = _df(_bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0))
    sigs = pd.DataFrame()
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)
    assert trades.empty
