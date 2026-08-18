"""AH5 probes: sl_first honors 3c entry-parent activation (H6).

P1 fails when ``resolve_ohlc_bar`` ``sl_first`` ignores ``entry_price`` and
stops on the pre-retrace parent extreme. P2 locks next-bar-open identity
(``entry_price is None``). P3 is the golden-family / no-new-model gate.
See ``docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md`` §6.5.
"""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.engine.backtest import SimulationResult, simulate_trades
from thesistester.engine.intrabar import VALID_INTRABAR_MODELS, resolve_ohlc_bar

TZ = "America/New_York"
_LOCKED_INTRABAR_MODELS = frozenset(
    {
        "sl_first",
        "path_open_proximity",
        "subtimeframe",
        "subtimeframe_conservative",
    }
)


def _three_c_signal(entry_price: float = 100.0) -> pd.DataFrame:
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


def _touch_signal() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_id": [1],
            "bar_index": [0],
            "trigger": ["touch"],
            "direction": ["long"],
        }
    )


def _parent(
    *,
    entry_open: float,
    entry_high: float,
    entry_low: float,
    entry_close: float,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=2, freq="5min", tz=TZ),
            "open": [100.0, entry_open],
            "high": [101.0, entry_high],
            "low": [99.0, entry_low],
            "close": [100.0, entry_close],
            "volume": [1000, 1000],
        }
    )


def test_ah5_p1_three_c_entry_parent_does_not_sl_on_pre_retrace_low():
    """AH5-P1: 3c long fill at 100; parent low 97 is before the retrace."""
    parent = _parent(entry_open=97.0, entry_high=103.0, entry_low=97.0, entry_close=101.0)
    raw = resolve_ohlc_bar(
        open_price=97.0,
        high=103.0,
        low=97.0,
        close=101.0,
        stop_price=98.0,
        target_price=104.0,
        direction="long",
        model="sl_first",
        entry_price=100.0,
    )
    assert raw.exit_kind is None
    assert raw.resolution == "no_hit"

    result = simulate_trades(
        parent,
        _three_c_signal(100.0),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="sl_first",
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] != "SL"
    assert trade["theoretical_exit_price"] != pytest.approx(98.0)
    assert trade["exit_reason"] == "EOD"
    assert trade["theoretical_exit_price"] == pytest.approx(101.0)


def test_ah5_p1_still_sl_when_post_entry_extreme_hits():
    """AH5-P1: SL remains when every post-entry OHLC suffix still tags the stop."""
    raw = resolve_ohlc_bar(
        open_price=102.0,
        high=103.0,
        low=97.0,
        close=99.0,
        stop_price=98.0,
        target_price=104.0,
        direction="long",
        model="sl_first",
        entry_price=100.0,
    )
    assert raw.exit_kind == "SL"
    assert raw.resolution == "single_hit"

    result = simulate_trades(
        _parent(entry_open=102.0, entry_high=103.0, entry_low=97.0, entry_close=99.0),
        _three_c_signal(100.0),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="sl_first",
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "SL"
    assert trade["theoretical_exit_price"] == pytest.approx(98.0)


def test_ah5_p2_next_bar_open_sl_first_both_hit_unchanged():
    """AH5-P2: next-bar-open ``sl_first`` both-hit is identical (no entry_price)."""
    raw = resolve_ohlc_bar(
        open_price=100.0,
        high=104.5,
        low=97.0,
        close=100.0,
        stop_price=98.0,
        target_price=104.0,
        direction="long",
        model="sl_first",
        entry_price=None,
    )
    assert raw.exit_kind == "SL"
    assert raw.resolution == "legacy_sl_first"
    assert raw.parent_both_hit is True
    assert raw.ambiguous is True

    result = simulate_trades(
        _parent(entry_open=100.0, entry_high=104.5, entry_low=97.0, entry_close=100.0),
        _touch_signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2,
        take_profit_ticks=4,
        intrabar_model="sl_first",
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "SL"
    assert trade["theoretical_exit_price"] == pytest.approx(98.0)
    assert "intrabar_model" not in result.trades.columns


def test_ah5_p3_no_new_intrabar_model():
    """AH5-P3: default model name stays ``sl_first``; no new R12 keyword.

    Golden families (``test_golden_master`` / ``test_otf_golden`` /
    ``test_entry_window_golden``) are the identity hard-stop and are run
    outside this file. Do not regen if they go red.
    """
    assert VALID_INTRABAR_MODELS == _LOCKED_INTRABAR_MODELS
    parent = _parent(entry_open=100.0, entry_high=101.0, entry_low=99.0, entry_close=100.0)
    implicit = simulate_trades(
        parent,
        _touch_signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=20,
        take_profit_ticks=20,
    )
    explicit = simulate_trades(
        parent,
        _touch_signal(),
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=20,
        take_profit_ticks=20,
        intrabar_model="sl_first",
    )
    pd.testing.assert_frame_equal(implicit, explicit)
    assert "intrabar_model" not in implicit.columns
