"""SW2 tests: simulate_trades entry_window admission + C7 Focus≡Admit."""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.entry_window import (
    entry_window_from_bucket,
    filter_trades_by_entry_window,
)
from thesistester.analytics.time_analysis import RTH_SEGMENTS as TIME_ANALYSIS_SEGMENTS
from thesistester.engine.backtest import simulate_trades
from thesistester.entry_window_policy import RTH_SEGMENTS as POLICY_SEGMENTS

TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 20.0


def _bar(
    ts: str,
    o: float = 21000.0,
    h: float | None = None,
    l: float | None = None,
    c: float | None = None,
) -> dict:
    open_ = o
    high = h if h is not None else open_ + 2.0
    low = l if l is not None else open_ - 2.0
    close = c if c is not None else open_ + 0.5
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000.0,
    }


def _signal(signal_id: int, bar_index: int, direction: str = "long") -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
        "bar_index": bar_index,
        "trigger": "touch",
        "direction": direction,
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


def _rth_morning_frame() -> pd.DataFrame:
    # 09:29 through 10:20 inclusive — covers open 30m and morning.
    stamps = pd.date_range("2026-06-02 09:29", periods=52, freq="1min", tz=TZ)
    rows = []
    price = 21000.0
    for ts in stamps:
        rows.append(_bar(str(ts), o=price))
        price += 0.25
    return pd.DataFrame(rows)


def _base_kwargs(**overrides):
    cfg = {
        "tick_size": TICK,
        "point_value": POINT_VALUE,
        "stop_loss_ticks": 8,
        "take_profit_ticks": 16,
        "max_holding_bars": 5,
        "allow_same_bar_exit": True,
        "commission_per_side": 0.0,
        "slippage_ticks": 0.0,
        "session_timezone": TZ,
        "exposure_policy": "allow_all",
        "cooldown_bars_after_exit": 0,
    }
    cfg.update(overrides)
    return cfg


def test_c1_shared_rth_vocabulary():
    assert POLICY_SEGMENTS == TIME_ANALYSIS_SEGMENTS


def test_disabled_entry_window_matches_omit():
    df = _rth_morning_frame()
    # Signal at 09:45 → entry 09:46 (open); signal at 10:10 → entry 10:11 (morning)
    idx_open = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:45", tz=TZ)][0])
    idx_morn = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 10:10", tz=TZ)][0])
    signals = pd.DataFrame(
        [
            _signal(1, idx_open),
            _signal(2, idx_morn),
        ]
    )
    legacy = simulate_trades(df, signals, **_base_kwargs())
    disabled = simulate_trades(df, signals, **_base_kwargs(entry_window=None))
    explicit_off = simulate_trades(df, signals, **_base_kwargs(entry_window={"enabled": False}))
    pd.testing.assert_frame_equal(legacy, disabled)
    pd.testing.assert_frame_equal(legacy, explicit_off)
    assert len(legacy) == 2


def test_rth_open_30m_admits_only_in_window():
    df = _rth_morning_frame()
    idx_open = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:45", tz=TZ)][0])
    idx_morn = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 10:10", tz=TZ)][0])
    signals = pd.DataFrame([_signal(1, idx_open), _signal(2, idx_morn)])
    window = entry_window_from_bucket("entry_rth_segment", "rth_open_30m", exchange_tz=TZ)
    result = simulate_trades(df, signals, **_base_kwargs(entry_window=window, return_result=True))
    assert list(result.trades["signal_id"]) == [1]
    skips = result.skipped_signals
    assert list(skips["signal_id"]) == [2]
    assert list(skips["skip_reason"]) == ["outside_entry_window"]


def test_boundary_0930_inclusive_1000_exclusive():
    df = _rth_morning_frame()
    # Signal 09:29 → entry 09:30 (inclusive open)
    # Signal 09:59 → entry 10:00 (exclusive; morning)
    idx_pre = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:29", tz=TZ)][0])
    idx_last_open = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:59", tz=TZ)][0])
    signals = pd.DataFrame([_signal(10, idx_pre), _signal(11, idx_last_open)])
    window = {
        "enabled": True,
        "mode": "rth_segments",
        "rth_segments": ["rth_open_30m"],
        "timezone": TZ,
    }
    result = simulate_trades(df, signals, **_base_kwargs(entry_window=window, return_result=True))
    assert list(result.trades["signal_id"]) == [10]
    assert list(result.skipped_signals["signal_id"]) == [11]
    assert result.trades.iloc[0]["entry_timestamp"] == pd.Timestamp("2026-06-02 09:30", tz=TZ)


def test_next_bar_open_classifies_by_entry_not_signal_bar_c2():
    """Signal in open, entry in morning → rejected by rth_open_30m (C2)."""
    df = _rth_morning_frame()
    idx_signal = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:59", tz=TZ)][0])
    signals = pd.DataFrame([_signal(21, idx_signal)])
    window = entry_window_from_bucket("entry_rth_segment", "rth_open_30m", exchange_tz=TZ)
    result = simulate_trades(df, signals, **_base_kwargs(entry_window=window, return_result=True))
    assert result.trades.empty
    assert list(result.skipped_signals["skip_reason"]) == ["outside_entry_window"]
    assert int(result.skipped_signals.iloc[0]["entry_bar_index"]) == idx_signal + 1


def test_multi_segment_or_c3():
    df = _rth_morning_frame()
    idx_open = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:45", tz=TZ)][0])
    idx_morn = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 10:10", tz=TZ)][0])
    signals = pd.DataFrame([_signal(1, idx_open), _signal(2, idx_morn)])
    window = {
        "enabled": True,
        "mode": "rth_segments",
        "rth_segments": ["rth_open_30m", "rth_morning"],
        "timezone": TZ,
    }
    trades = simulate_trades(df, signals, **_base_kwargs(entry_window=window))
    assert set(trades["signal_id"]) == {1, 2}


def test_clock_range_half_open():
    df = _rth_morning_frame()
    idx_a = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:45", tz=TZ)][0])
    idx_b = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:59", tz=TZ)][0])
    signals = pd.DataFrame([_signal(1, idx_a), _signal(2, idx_b)])
    # Entries at 09:46 and 10:00; window [09:30, 10:00) keeps only 09:46.
    window = {
        "enabled": True,
        "mode": "clock_range",
        "start_time": "09:30",
        "end_time": "10:00",
        "timezone": TZ,
    }
    result = simulate_trades(df, signals, **_base_kwargs(entry_window=window, return_result=True))
    assert list(result.trades["signal_id"]) == [1]
    assert list(result.skipped_signals["signal_id"]) == [2]


def test_invalid_entry_window_raises():
    df = _rth_morning_frame()
    signals = pd.DataFrame([_signal(1, 0)])
    with pytest.raises(ValueError, match="Invalid entry_window"):
        simulate_trades(
            df,
            signals,
            **_base_kwargs(
                entry_window={
                    "enabled": True,
                    "mode": "rth_segments",
                    "rth_segments": [],
                }
            ),
        )


def test_invalid_entry_window_timezone_raises_value_error():
    df = _rth_morning_frame()
    signals = pd.DataFrame([_signal(1, 0)])
    with pytest.raises(ValueError, match="Invalid entry_window"):
        simulate_trades(
            df,
            signals,
            **_base_kwargs(
                entry_window={
                    "enabled": True,
                    "mode": "clock_range",
                    "start_time": "09:00",
                    "end_time": "10:00",
                    "timezone": "Not/AZone",
                }
            ),
        )


def test_entry_window_exchange_tz_overrides_session_timezone_for_rth():
    """C5: session-close TZ must not redefine RTH segment membership."""
    df = _rth_morning_frame()
    idx_open = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:45", tz=TZ)][0])
    signals = pd.DataFrame([_signal(1, idx_open)])
    window = entry_window_from_bucket("entry_rth_segment", "rth_open_30m", exchange_tz=TZ)
    # Without override, Chicago session TZ misclassifies 09:45 NY as pre_rth.
    wrong = simulate_trades(
        df,
        signals,
        **_base_kwargs(
            entry_window=window,
            flat_by_session_close=True,
            session_close_time="16:00",
            session_timezone="America/Chicago",
        ),
    )
    assert wrong.empty
    fixed = simulate_trades(
        df,
        signals,
        **_base_kwargs(
            entry_window=window,
            flat_by_session_close=True,
            session_close_time="16:00",
            session_timezone="America/Chicago",
            entry_window_exchange_tz=TZ,
        ),
    )
    assert list(fixed["signal_id"]) == [1]


def test_c7_naive_bars_ignore_session_timezone_for_admit():
    """Naive bars + Chicago session-close TZ must still Focus≡Admit (C5/C7)."""
    stamps = pd.date_range("2026-06-02 09:40", periods=40, freq="1min")  # naive
    rows = []
    price = 21000.0
    for ts in stamps:
        rows.append(
            {
                "timestamp": pd.Timestamp(ts),
                "open": price,
                "high": price + 2.0,
                "low": price - 2.0,
                "close": price + 0.5,
                "volume": 1000.0,
            }
        )
        price += 0.25
    df = pd.DataFrame(rows)
    idx_open = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:45")][0])
    idx_morn = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 10:10")][0])
    signals = pd.DataFrame(
        [
            {**_signal(1, idx_open), "timestamp": pd.Timestamp("2026-06-02 09:45")},
            {**_signal(2, idx_morn), "timestamp": pd.Timestamp("2026-06-02 10:10")},
        ]
    )
    window = entry_window_from_bucket("entry_rth_segment", "rth_open_30m", exchange_tz=TZ)
    kwargs = _base_kwargs(
        flat_by_session_close=True,
        session_close_time="16:00",
        session_timezone="America/Chicago",
        entry_window_exchange_tz=TZ,
    )
    all_day = simulate_trades(df, signals, **kwargs)
    admit = simulate_trades(df, signals, **kwargs, entry_window=window)
    focused = filter_trades_by_entry_window(
        all_day, window, exchange_tz=TZ, timestamp_col="entry_timestamp"
    )
    assert set(admit["signal_id"]) == set(focused["signal_id"]) == {1}
    assert all_day["entry_timestamp"].dt.tz is None


def test_c7_focus_equals_admit_under_allow_all():
    df = _rth_morning_frame()
    idxs = [
        int(df.index[df["timestamp"] == pd.Timestamp(ts, tz=TZ)][0])
        for ts in (
            "2026-06-02 09:40",
            "2026-06-02 09:55",
            "2026-06-02 09:59",
            "2026-06-02 10:05",
            "2026-06-02 10:15",
        )
    ]
    signals = pd.DataFrame([_signal(i + 1, bar_index) for i, bar_index in enumerate(idxs)])
    window = entry_window_from_bucket("entry_rth_segment", "rth_open_30m", exchange_tz=TZ)

    all_day = simulate_trades(df, signals, **_base_kwargs())
    admit = simulate_trades(df, signals, **_base_kwargs(entry_window=window))
    focused = filter_trades_by_entry_window(
        all_day, window, exchange_tz=TZ, timestamp_col="entry_timestamp"
    )

    assert set(admit["signal_id"]) == set(focused["signal_id"])
    assert set(admit["signal_id"])  # non-empty sanity


def test_c7_clock_range_naive_timestamps_use_exchange_tz():
    """C5/C7: naive bars + session_timezone + non-exchange bucket TZ must agree.

    Trade rows keep the original (possibly naive) ``entry_timestamp``. Admit
    localizes via ``session_timezone`` before membership; Focus must treat
    naive stamps as exchange/session wall clocks, not as the bucket TZ.
    """
    stamps = pd.date_range("2026-06-02 09:40", periods=90, freq="1min")  # naive
    rows = []
    price = 21000.0
    for ts in stamps:
        rows.append(
            {
                "timestamp": pd.Timestamp(ts),
                "open": price,
                "high": price + 2.0,
                "low": price - 2.0,
                "close": price + 0.5,
                "volume": 1000.0,
            }
        )
        price += 0.25
    df = pd.DataFrame(rows)

    idxs = [
        int(df.index[df["timestamp"] == pd.Timestamp(ts)][0])
        for ts in (
            "2026-06-02 09:44",  # entry 09:45 NY → 08:45 Chicago → outside [09:00,10:00) CHI
            "2026-06-02 09:59",  # entry 10:00 NY → 09:00 Chicago → inside
            "2026-06-02 10:14",  # entry 10:15 NY → 09:15 Chicago → inside
            "2026-06-02 10:59",  # entry 11:00 NY → 10:00 Chicago → exclusive end
        )
    ]
    signals = pd.DataFrame(
        [
            {
                **_signal(i + 1, bar_index),
                "timestamp": pd.Timestamp(df["timestamp"].iloc[bar_index]),
            }
            for i, bar_index in enumerate(idxs)
        ]
    )
    window = entry_window_from_bucket(
        "entry_hour_bucket",
        "09:00",
        exchange_tz=TZ,
        bucket_tz="America/Chicago",
    )

    all_day = simulate_trades(df, signals, **_base_kwargs())
    admit = simulate_trades(df, signals, **_base_kwargs(entry_window=window))
    focused = filter_trades_by_entry_window(
        all_day, window, exchange_tz=TZ, timestamp_col="entry_timestamp"
    )

    assert set(admit["signal_id"]) == set(focused["signal_id"]) == {2, 3}
    assert all_day["entry_timestamp"].dt.tz is None


def test_window_rejects_never_block_exposure():
    """Outside-window candidates must not act as exposure blockers."""
    df = _rth_morning_frame()
    # Two signals that would overlap if both admitted; first is outside window.
    idx_morn = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 10:05", tz=TZ)][0])
    idx_open = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:40", tz=TZ)][0])
    # Process morning signal first in frame order, then open — with single_position,
    # if morning were admitted first it could block. Window rejects morning first.
    signals = pd.DataFrame([_signal(1, idx_morn), _signal(2, idx_open)])
    window = entry_window_from_bucket("entry_rth_segment", "rth_open_30m", exchange_tz=TZ)
    result = simulate_trades(
        df,
        signals,
        **_base_kwargs(
            entry_window=window,
            exposure_policy="single_position",
            return_result=True,
        ),
    )
    assert list(result.trades["signal_id"]) == [2]
    assert "outside_entry_window" in set(result.skipped_signals["skip_reason"])
    assert "overlapping_position" not in set(result.skipped_signals["skip_reason"])
