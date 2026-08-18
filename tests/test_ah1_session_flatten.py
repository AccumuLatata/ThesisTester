"""AH1 probes: per-candidate flatten clock (C1).

P1/P2 fail on the leaked ``entry_local_ts`` loop variable and pass once
each candidate stores its own flatten clock. P3–P5 are identity / skip-schema
guards. See ``docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md`` §6.1.
"""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.engine.backtest import SimulationResult, simulate_trades

TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 50.0
WIDE = dict(stop_loss_ticks=100, take_profit_ticks=100)
EMPTY_SESSION_CLOSE_CAP = "empty_session_close_cap"
# Same skip-row schema as ``after_entry_cutoff`` (AH1 §6.1 change 4).
_SKIP_ROW_COLUMNS = frozenset(
    {
        "signal_id",
        "bar_index",
        "entry_bar_index",
        "trigger",
        "direction",
        "exposure_policy",
        "exposure_group_key",
        "skip_reason",
        "blocking_trade_id",
        "blocking_exit_bar_index",
        "cooldown_bars_after_exit",
    }
)


def _bar(ts: str, price: float = 100.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": price,
        "high": price + 0.25,
        "low": price - 0.25,
        "close": price,
        "volume": 100.0,
    }


def _df(*timestamps: str) -> pd.DataFrame:
    return pd.DataFrame([_bar(ts) for ts in timestamps])


def _signal(bar_index: int, signal_id: int, timestamp: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "signal_id": signal_id,
                "timestamp": pd.Timestamp(timestamp, tz=TZ),
                "bar_index": bar_index,
                "trigger": "touch",
                "direction": "long",
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 2,
                "level_names": "A|B",
                "entry_reference_price": 100.0,
                "entry_model": "candidate_next_bar_open",
                "status": "candidate",
                "naked_level_count": 0,
                "naked_requirement": "any",
                "notes": "",
            }
        ]
    )


def _p1_frame() -> pd.DataFrame:
    """Mon 18:30 entry then Tue 02:00 entry; last first-loop clock is Tuesday."""
    return _df(
        "2026-01-05 18:29",
        "2026-01-05 18:30",
        "2026-01-06 01:59",
        "2026-01-06 02:00",
        "2026-01-06 15:59",
        "2026-01-06 16:00",
    )


def _p1_signals() -> pd.DataFrame:
    return pd.concat(
        [
            _signal(bar_index=0, signal_id=1, timestamp="2026-01-05 18:29"),
            _signal(bar_index=2, signal_id=2, timestamp="2026-01-06 01:59"),
        ],
        ignore_index=True,
    )


def _assert_empty_cap_skip(skipped: pd.DataFrame, *, signal_id: int) -> None:
    assert _SKIP_ROW_COLUMNS <= set(skipped.columns)
    assert list(skipped["skip_reason"]) == [EMPTY_SESSION_CLOSE_CAP]
    assert list(skipped["signal_id"]) == [signal_id]


def test_ah1_p1_mon_eth_does_not_inherit_tuesday_flatten_clock():
    """AH1-P1: last first-loop entry Tue 02:00 must not flatten Mon 18:30 to Tuesday."""
    kwargs = dict(
        flat_by_session_close=True,
        session_close_time="16:00",
        session_timezone=TZ,
    )
    result = simulate_trades(
        _p1_frame(),
        _p1_signals(),
        TICK,
        POINT_VALUE,
        **WIDE,
        **kwargs,
        return_result=True,
    )
    assert isinstance(result, SimulationResult)
    trades = result.trades
    skipped = result.skipped_signals
    _assert_empty_cap_skip(skipped, signal_id=1)
    assert len(trades) == 1
    assert int(trades.iloc[0]["signal_id"]) == 2
    assert trades.iloc[0]["exit_reason"] == "SESSION_CLOSE"
    assert int(trades.iloc[0]["exit_bar_index"]) == 5
    assert pd.Timestamp(trades.iloc[0]["entry_timestamp"]) == pd.Timestamp(
        "2026-01-06 02:00", tz=TZ
    )
    assert pd.Timestamp(trades.iloc[0]["exit_timestamp"]) == pd.Timestamp("2026-01-06 16:00", tz=TZ)

    trades_tuple, skipped_tuple = simulate_trades(
        _p1_frame(),
        _p1_signals(),
        TICK,
        POINT_VALUE,
        **WIDE,
        **kwargs,
        return_skipped_signals=True,
    )
    pd.testing.assert_frame_equal(trades.reset_index(drop=True), trades_tuple.reset_index(drop=True))
    _assert_empty_cap_skip(skipped_tuple, signal_id=1)


def test_ah1_p2_tue_rth_does_not_inherit_monday_flatten_clock():
    """AH1-P2: last first-loop entry Mon 18:30 must not empty-cap Tue RTH."""
    df = _df(
        "2026-01-05 18:29",
        "2026-01-05 18:30",
        "2026-01-06 09:30",
        "2026-01-06 09:31",
        "2026-01-06 15:59",
        "2026-01-06 16:00",
    )
    # First-loop order: Tue RTH first, Mon ETH last (leaked clock = Mon 18:30).
    signals = pd.concat(
        [
            _signal(bar_index=2, signal_id=2, timestamp="2026-01-06 09:30"),
            _signal(bar_index=0, signal_id=1, timestamp="2026-01-05 18:29"),
        ],
        ignore_index=True,
    )
    result = simulate_trades(
        df,
        signals,
        TICK,
        POINT_VALUE,
        **WIDE,
        flat_by_session_close=True,
        session_close_time="16:00",
        session_timezone=TZ,
        return_result=True,
    )
    trades = result.trades
    skipped = result.skipped_signals
    _assert_empty_cap_skip(skipped, signal_id=1)
    assert len(trades) == 1
    assert int(trades.iloc[0]["signal_id"]) == 2
    assert trades.iloc[0]["exit_reason"] == "SESSION_CLOSE"
    assert int(trades.iloc[0]["exit_bar_index"]) == 5
    assert pd.Timestamp(trades.iloc[0]["entry_timestamp"]) == pd.Timestamp(
        "2026-01-06 09:31", tz=TZ
    )
    assert pd.Timestamp(trades.iloc[0]["exit_timestamp"]) == pd.Timestamp("2026-01-06 16:00", tz=TZ)


def test_ah1_p3_single_signal_rth_flatten_unchanged():
    """AH1-P3: identity clone of phase5 single-signal RTH flatten."""
    df = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp(ts, tz=TZ),
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "volume": 100.0,
            }
            for ts, o, h, low, c in (
                ("2026-01-02 15:58", 100.0, 100.4, 99.9, 100.2),
                ("2026-01-02 15:59", 100.2, 100.4, 100.0, 100.3),
                ("2026-01-02 16:00", 100.3, 100.5, 100.1, 100.4),
                ("2026-01-02 16:01", 100.4, 102.0, 100.3, 101.8),
            )
        ]
    )
    trades = simulate_trades(
        df,
        _signal(bar_index=0, signal_id=0, timestamp="2026-01-02 15:58"),
        TICK,
        POINT_VALUE,
        stop_loss_ticks=100,
        take_profit_ticks=100,
        slippage_ticks=1.0,
        flat_by_session_close=True,
        session_close_time="16:00",
        session_timezone=TZ,
    )
    t = trades.iloc[0]
    assert t["exit_reason"] == "SESSION_CLOSE"
    assert int(t["exit_bar_index"]) == 2
    assert t["theoretical_exit_price"] == pytest.approx(100.4)
    assert t["exit_price"] == pytest.approx(100.15)


def test_ah1_p4_flatten_off_multi_date_has_no_session_close():
    """AH1-P4: flatten-off multi-date identity — no SESSION_CLOSE exits."""
    trades = simulate_trades(
        _p1_frame(),
        _p1_signals(),
        TICK,
        POINT_VALUE,
        **WIDE,
        session_timezone=TZ,
    )
    captured = simulate_trades(
        _p1_frame(),
        _p1_signals(),
        TICK,
        POINT_VALUE,
        **WIDE,
        session_timezone=TZ,
        return_result=True,
    )
    assert len(trades) == 2
    assert set(trades["exit_reason"]) == {"EOD"}
    assert set(trades["signal_id"].astype(int)) == {1, 2}
    pd.testing.assert_frame_equal(
        trades.reset_index(drop=True), captured.trades.reset_index(drop=True)
    )
    assert captured.skipped_signals.empty


def test_ah1_p5_empty_cap_default_return_is_trades_only():
    """AH1-P5: golden default ``return_result=False`` stays a trades DataFrame."""
    df = _df("2026-01-05 18:29", "2026-01-05 18:30")
    out = simulate_trades(
        df,
        _signal(bar_index=0, signal_id=1, timestamp="2026-01-05 18:29"),
        TICK,
        POINT_VALUE,
        **WIDE,
        flat_by_session_close=True,
        session_close_time="16:00",
        session_timezone=TZ,
    )
    assert isinstance(out, pd.DataFrame)
    assert not isinstance(out, SimulationResult)
    assert out.empty
    assert "skip_reason" not in out.columns
