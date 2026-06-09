"""Tests for execution-cost modelling in the Phase 5 backtest engine (R1).

Covers:
- Zero-cost regression: new params default to prior behavior.
- Long trade cost calculation with known inputs.
- Short trade cost calculation with known inputs.
- Validation: negative commission and negative slippage raise ValueError.
"""
from __future__ import annotations

import pandas as pd
import pytest

from thesistester.engine.backtest import simulate_trades


TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 50.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bar(ts: str, o: float, h: float, l: float, c: float, vol: float = 100.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": vol,
    }


def _df(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _signal(
    bar_index: int = 0,
    trigger: str = "touch",
    direction: str = "long",
    signal_id: int = 0,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "signal_id": signal_id,
                "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
                "bar_index": bar_index,
                "trigger": trigger,
                "direction": direction,
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "A",
                "entry_reference_price": 100.0,
                "entry_model": "candidate_next_bar_open",
                "status": "candidate",
                "naked_level_count": 0,
                "naked_requirement": "any",
                "notes": "",
            }
        ]
    )


# ---------------------------------------------------------------------------
# Zero-cost regression
# ---------------------------------------------------------------------------


def test_zero_cost_long_tp_matches_prior_behavior():
    """Zero-cost defaults reproduce prior behavior for all key columns."""
    entry_open = 100.0
    sl_ticks = 4
    tp_ticks = 8
    tp_price = entry_open + tp_ticks * TICK  # 101.0

    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", entry_open, tp_price + 1, 99.8, tp_price + 0.5),
    )
    sigs = _signal(bar_index=0, direction="long")

    # With explicit zero costs
    trades = simulate_trades(
        df, sigs, TICK, POINT_VALUE,
        stop_loss_ticks=sl_ticks,
        take_profit_ticks=tp_ticks,
        commission_per_side=0.0,
        slippage_ticks=0.0,
    )
    t = trades.iloc[0]

    # entry_price unchanged (no slippage)
    assert t["entry_price"] == pytest.approx(entry_open)
    assert t["theoretical_entry_price"] == pytest.approx(entry_open)

    # exit at TP
    assert t["exit_price"] == pytest.approx(tp_price)
    assert t["theoretical_exit_price"] == pytest.approx(tp_price)

    # pnl_points == gross_pnl_points
    expected_pnl_pts = tp_price - entry_open  # 1.0
    assert t["pnl_points"] == pytest.approx(expected_pnl_pts)
    assert t["gross_pnl_points"] == pytest.approx(expected_pnl_pts)

    # pnl_currency == net_pnl_currency (no commission)
    expected_pnl_currency = expected_pnl_pts * POINT_VALUE
    assert t["pnl_currency"] == pytest.approx(expected_pnl_currency)
    assert t["net_pnl_currency"] == pytest.approx(expected_pnl_currency)

    # commission and slippage costs are zero
    assert t["commission_cost"] == pytest.approx(0.0)
    assert t["slippage_cost"] == pytest.approx(0.0)

    # r_multiple unchanged
    sl_pts = sl_ticks * TICK
    expected_r = expected_pnl_pts / sl_pts
    assert t["r_multiple"] == pytest.approx(expected_r)


def test_zero_cost_short_sl_matches_prior_behavior():
    """Zero-cost short SL: all legacy columns identical to prior behavior."""
    entry_open = 100.0
    sl_ticks = 4
    sl_price = entry_open + sl_ticks * TICK  # 101.0

    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", entry_open, sl_price + 1, 99.5, 101.5),
    )
    sigs = _signal(bar_index=0, direction="short")

    trades = simulate_trades(
        df, sigs, TICK, POINT_VALUE,
        stop_loss_ticks=sl_ticks,
        take_profit_ticks=8,
        commission_per_side=0.0,
        slippage_ticks=0.0,
    )
    t = trades.iloc[0]

    assert t["entry_price"] == pytest.approx(entry_open)
    assert t["exit_price"] == pytest.approx(sl_price)
    assert t["exit_reason"] == "SL"

    pnl_pts = entry_open - sl_price  # -1.0
    assert t["pnl_points"] == pytest.approx(pnl_pts)
    assert t["pnl_currency"] == pytest.approx(pnl_pts * POINT_VALUE)
    assert t["r_multiple"] < 0


# ---------------------------------------------------------------------------
# Long trade cost calculation
# ---------------------------------------------------------------------------


def test_long_trade_cost_calculation():
    """Long trade: verify adverse slippage, gross P&L, commission, net P&L, net R."""
    sl_ticks = 4
    tp_ticks = 8
    commission = 2.50   # per side
    slip_ticks = 1      # tick

    slip_pts = slip_ticks * TICK  # 0.25

    # Entry bar open = 100.0; next-bar (bar 1) open is the entry.
    entry_open = 100.0
    # Adverse entry: long fills higher
    expected_entry = entry_open + slip_pts  # 100.25
    # SL/TP based on slipped entry
    sl_price = expected_entry - sl_ticks * TICK  # 100.25 - 1.0 = 99.25
    tp_price = expected_entry + tp_ticks * TICK  # 100.25 + 2.0 = 102.25

    # Bar 1: TP is hit (high well above tp_price, low above sl)
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", entry_open, tp_price + 1, entry_open, tp_price + 0.5),
    )
    sigs = _signal(bar_index=0, direction="long")

    trades = simulate_trades(
        df, sigs, TICK, POINT_VALUE,
        stop_loss_ticks=sl_ticks,
        take_profit_ticks=tp_ticks,
        commission_per_side=commission,
        slippage_ticks=slip_ticks,
    )
    t = trades.iloc[0]

    # Entry slippage is adverse (long: higher)
    assert t["theoretical_entry_price"] == pytest.approx(entry_open)
    assert t["entry_price"] == pytest.approx(expected_entry)

    # TP level is computed from slipped entry
    assert t["target_price"] == pytest.approx(tp_price)
    assert t["exit_reason"] == "TP"

    # Exit slippage is adverse (long exit: lower)
    assert t["theoretical_exit_price"] == pytest.approx(tp_price)
    expected_exit = tp_price - slip_pts  # 102.0
    assert t["exit_price"] == pytest.approx(expected_exit)

    # Gross P&L is based on actual slipped fills
    expected_gross_pts = expected_exit - expected_entry  # 102.0 - 100.25 = 1.75
    assert t["gross_pnl_points"] == pytest.approx(expected_gross_pts)
    expected_gross_currency = expected_gross_pts * POINT_VALUE
    assert t["gross_pnl_currency"] == pytest.approx(expected_gross_currency)

    # Commission cost = 2 * per_side
    assert t["commission_cost"] == pytest.approx(2.0 * commission)

    # Slippage cost = 2 * slip_pts * point_value
    assert t["slippage_cost"] == pytest.approx(2.0 * slip_pts * POINT_VALUE)

    # Net P&L
    expected_net = expected_gross_currency - 2.0 * commission
    assert t["net_pnl_currency"] == pytest.approx(expected_net)
    assert t["pnl_currency"] == pytest.approx(expected_net)

    # Net R = net_pnl_currency / risk_currency
    risk_currency = sl_ticks * TICK * POINT_VALUE
    assert t["r_multiple"] == pytest.approx(expected_net / risk_currency)


# ---------------------------------------------------------------------------
# Short trade cost calculation
# ---------------------------------------------------------------------------


def test_short_trade_cost_calculation():
    """Short trade: verify adverse slippage direction and net P&L."""
    sl_ticks = 4
    tp_ticks = 8
    commission = 2.50
    slip_ticks = 1

    slip_pts = slip_ticks * TICK  # 0.25

    # Entry bar open = 100.0 (short)
    entry_open = 100.0
    # Adverse entry: short fills lower
    expected_entry = entry_open - slip_pts  # 99.75
    # SL/TP based on slipped entry (short)
    sl_price = expected_entry + sl_ticks * TICK   # 99.75 + 1.0 = 100.75
    tp_price = expected_entry - tp_ticks * TICK   # 99.75 - 2.0 = 97.75

    # Bar 1: TP is hit (low well below tp_price, high below sl)
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", entry_open, entry_open, tp_price - 1, tp_price - 0.5),
    )
    sigs = _signal(bar_index=0, direction="short")

    trades = simulate_trades(
        df, sigs, TICK, POINT_VALUE,
        stop_loss_ticks=sl_ticks,
        take_profit_ticks=tp_ticks,
        commission_per_side=commission,
        slippage_ticks=slip_ticks,
    )
    t = trades.iloc[0]

    # Entry slippage is adverse (short: lower)
    assert t["theoretical_entry_price"] == pytest.approx(entry_open)
    assert t["entry_price"] == pytest.approx(expected_entry)

    assert t["target_price"] == pytest.approx(tp_price)
    assert t["exit_reason"] == "TP"

    # Exit slippage is adverse (short exit: higher — costs more to close)
    assert t["theoretical_exit_price"] == pytest.approx(tp_price)
    expected_exit = tp_price + slip_pts  # 98.0
    assert t["exit_price"] == pytest.approx(expected_exit)

    # Gross P&L (short: entry - exit)
    expected_gross_pts = expected_entry - expected_exit  # 99.75 - 98.0 = 1.75
    assert t["gross_pnl_points"] == pytest.approx(expected_gross_pts)
    expected_gross_currency = expected_gross_pts * POINT_VALUE
    assert t["gross_pnl_currency"] == pytest.approx(expected_gross_currency)

    assert t["commission_cost"] == pytest.approx(2.0 * commission)
    assert t["slippage_cost"] == pytest.approx(2.0 * slip_pts * POINT_VALUE)

    expected_net = expected_gross_currency - 2.0 * commission
    assert t["net_pnl_currency"] == pytest.approx(expected_net)
    assert t["pnl_currency"] == pytest.approx(expected_net)

    risk_currency = sl_ticks * TICK * POINT_VALUE
    assert t["r_multiple"] == pytest.approx(expected_net / risk_currency)


# ---------------------------------------------------------------------------
# Slippage makes SL worse for long (SL exit)
# ---------------------------------------------------------------------------


def test_long_sl_exit_slippage_is_adverse():
    """Long SL exit fills below the stop level (adverse slippage)."""
    sl_ticks = 4
    slip_ticks = 1

    entry_open = 100.0
    slip_pts = slip_ticks * TICK
    expected_entry = entry_open + slip_pts  # 100.25
    sl_price = expected_entry - sl_ticks * TICK   # 99.25

    # Bar 1: SL hit
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", entry_open, entry_open, sl_price - 1, 99.0),
    )
    sigs = _signal(bar_index=0, direction="long")

    trades = simulate_trades(
        df, sigs, TICK, POINT_VALUE,
        stop_loss_ticks=sl_ticks,
        take_profit_ticks=100,
        slippage_ticks=slip_ticks,
    )
    t = trades.iloc[0]

    assert t["exit_reason"] == "SL"
    # theoretical_exit = sl_price; actual exit = sl_price - slip_pts
    assert t["theoretical_exit_price"] == pytest.approx(sl_price)
    assert t["exit_price"] == pytest.approx(sl_price - slip_pts)
    assert t["gross_pnl_points"] < 0


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


def test_negative_commission_raises():
    """Negative commission_per_side must raise ValueError."""
    df = _df(_bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0))
    sigs = _signal(bar_index=0)
    with pytest.raises(ValueError, match="commission_per_side"):
        simulate_trades(
            df, sigs, TICK, POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
            commission_per_side=-1.0,
        )


def test_negative_slippage_raises():
    """Negative slippage_ticks must raise ValueError."""
    df = _df(_bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0))
    sigs = _signal(bar_index=0)
    with pytest.raises(ValueError, match="slippage_ticks"):
        simulate_trades(
            df, sigs, TICK, POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
            slippage_ticks=-0.5,
        )


def test_zero_commission_zero_slippage_are_valid():
    """Exactly zero costs must not raise."""
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", 100.0, 102.0, 99.8, 101.0),
    )
    sigs = _signal(bar_index=0, direction="long")
    # Must not raise
    trades = simulate_trades(
        df, sigs, TICK, POINT_VALUE,
        stop_loss_ticks=4,
        take_profit_ticks=8,
        commission_per_side=0.0,
        slippage_ticks=0.0,
    )
    assert not trades.empty


# ---------------------------------------------------------------------------
# New columns are always present (even with zero costs)
# ---------------------------------------------------------------------------


def test_new_cost_columns_always_present():
    """Cost columns appear in output even when costs are zero."""
    df = _df(
        _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
        _bar("2026-01-02 09:31", 100.0, 102.0, 99.8, 101.0),
    )
    sigs = _signal(bar_index=0, direction="long")
    trades = simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)
    for col in [
        "theoretical_entry_price",
        "theoretical_exit_price",
        "gross_pnl_points",
        "gross_pnl_currency",
        "commission_cost",
        "slippage_cost",
        "net_pnl_currency",
    ]:
        assert col in trades.columns, f"Missing column: {col}"
