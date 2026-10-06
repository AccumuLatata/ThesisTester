"""TS3 15s clip + hourly hole guard — plan §5 TS3 / §4.4."""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from thesistester.data import loader as loader_mod
from thesistester.data.tick_stitch import (
    TickStitchError,
    clip_ticks_to_15s_bars,
    guard_hourly_tick_holes,
)
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION
from thesistester.study import execute as execute_mod


def _utc(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz="UTC")


def _ticks(*stamps: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [_utc(stamp) for stamp in stamps],
            "price": [100.0] * len(stamps),
            "volume": [1.0] * len(stamps),
        }
    )


def _bars(start: str, end: str, *, volume: float = 1.0) -> pd.DataFrame:
    stamps = pd.date_range(_utc(start), _utc(end), freq="15s")
    return pd.DataFrame({"timestamp": stamps, "volume": [volume] * len(stamps)})


def _dense_ticks(start: str, end: str, *, freq: str = "4s") -> pd.DataFrame:
    stamps = pd.date_range(_utc(start), _utc(end), freq=freq)
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "price": [100.0] * len(stamps),
            "volume": [1.0] * len(stamps),
        }
    )


def test_halt_one_lot_print_at_2200_is_clipped_away():
    ticks = _ticks("2026-03-17 21:59:45.010", "2026-03-17 22:00:00.050")
    bars = pd.DataFrame({"timestamp": [_utc("2026-03-17 21:59:45")], "volume": [10.0]})
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert clipped["timestamp"].tolist() == [_utc("2026-03-17 21:59:45.010")]
    guard_hourly_tick_holes(clipped, bars)


def test_cut_short_hour_fails():
    ticks = _ticks("2026-03-17 14:00:00", "2026-03-17 14:51:52")
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:59:45")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="cut short"):
        guard_hourly_tick_holes(clipped, bars)


def test_head_of_hour_hole_fails():
    """First whole volume bar of the hour has no tick (Accumu option A)."""
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:59:45")
    ticks = _dense_ticks("2026-03-17 14:00:15", "2026-03-17 14:59:59")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="head-of-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_mid_hour_gap_spanning_volume_bars_fails():
    ticks = _ticks("2026-03-17 14:10:00", "2026-03-17 14:10:30")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2026-03-17 14:10:00"),
                _utc("2026-03-17 14:10:15"),
                _utc("2026-03-17 14:10:30"),
            ],
            "volume": [4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_sparse_7s_gaps_with_a_tick_in_every_volume_bar_pass():
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:59:45")
    ticks = _dense_ticks("2026-03-17 14:00:00", "2026-03-17 14:59:59", freq="7s")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert not clipped.empty
    guard_hourly_tick_holes(clipped, bars)


def test_volume_bar_with_no_tick_fails_mid_hour():
    ticks = _ticks("2026-03-17 14:10:00.100", "2026-03-17 14:10:30.050")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2026-03-17 14:10:00"),
                _utc("2026-03-17 14:10:15"),
                _utc("2026-03-17 14:10:30"),
            ],
            "volume": [4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_filled_x1_style_1800_hour_one_print_per_bar_at_7_5s_passes():
    bars = _bars("2025-11-07 18:00:00", "2025-11-07 18:59:45")
    ticks = pd.DataFrame(
        {
            "timestamp": bars["timestamp"] + pd.Timedelta(milliseconds=7500),
            "price": [100.0] * len(bars),
            "volume": [1.0] * len(bars),
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert len(clipped) == len(bars)
    guard_hourly_tick_holes(clipped, bars)


def test_filled_hour_plus_7_5s_only_passes_whole_guard():
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:59:45")
    ticks = pd.DataFrame(
        {
            "timestamp": bars["timestamp"] + pd.Timedelta(milliseconds=7500),
            "price": [100.0] * len(bars),
            "volume": [1.0] * len(bars),
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    guard_hourly_tick_holes(clipped, bars)


def test_1128_allowlisted_hole_does_not_fail():
    bars = _bars("2025-11-28 08:00:00", "2025-11-28 08:59:45")
    guard_hourly_tick_holes(pd.DataFrame(columns=["timestamp", "price", "volume"]), bars)


def test_hour_with_ticks_but_no_15s_does_not_fail_after_clip():
    ticks = _ticks("2026-03-17 21:00:00.050")
    bars = pd.DataFrame({"timestamp": [_utc("2026-03-17 20:59:45")], "volume": [8.0]})
    bars["volume"] = 8.0
    # Cover the 20:59 bar so the adjacent hour is valid; 21:00 print is clipped.
    ticks = pd.concat(
        [_ticks("2026-03-17 20:59:45.010"), ticks],
        ignore_index=True,
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert clipped["timestamp"].dt.hour.tolist() == [20]
    guard_hourly_tick_holes(clipped, bars)


def test_unfilled_x1_hour_fails():
    bars = _bars("2025-11-07 18:00:00", "2025-11-07 18:59:45")
    with pytest.raises(TickStitchError, match="no stitched\\+clipped ticks"):
        guard_hourly_tick_holes(pd.DataFrame(columns=["timestamp", "price", "volume"]), bars)


def test_empty_in_both_weekend_hour_does_not_fail():
    guard_hourly_tick_holes(
        pd.DataFrame(columns=["timestamp", "price", "volume"]),
        pd.DataFrame(columns=["timestamp", "volume"]),
    )


def test_1128_cut_short_after_1330_still_fails():
    """Allowlist (1) is [02:00, 13:30), not the whole 13:00 hour."""
    ticks = _dense_ticks("2025-11-28 13:30:00", "2025-11-28 13:40:00")
    bars = _bars("2025-11-28 13:30:00", "2025-11-28 13:59:45")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="cut short"):
        guard_hourly_tick_holes(clipped, bars)


def test_1128_healthy_resume_after_1330_passes():
    bars = _bars("2025-11-28 13:30:00", "2025-11-28 13:59:45")
    ticks = _dense_ticks("2025-11-28 13:30:00", "2025-11-28 13:59:59")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    guard_hourly_tick_holes(clipped, bars)


def test_1128_head_of_hour_after_1330_still_fails():
    bars = _bars("2025-11-28 13:30:00", "2025-11-28 13:59:45")
    ticks = _dense_ticks("2025-11-28 13:30:15", "2025-11-28 13:59:59")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="head-of-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_allowlist_excuses_empty_bars_not_whole_hole():
    """Accumu option A: hole [18:00:54.037, 18:01:37.500) is not contained in
    [18:00:45, 18:01:30), but its whole empty 15s bars are."""
    ticks = _ticks("2025-11-07 18:00:54.037", "2025-11-07 18:01:37.500")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
            ],
            "volume": [4.0, 4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[(_utc("2025-11-07 18:00:45"), _utc("2025-11-07 18:01:30"))],
    )


def test_1128_whole_empty_bar_after_1330_still_fails():
    """11-28 allowlist stays [02:00, 13:30): empty bar [13:30:00, 13:30:15) is not excused."""
    ticks = _ticks("2025-11-28 13:29:50.100", "2025-11-28 13:30:20.050")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-28 13:29:45"),
                _utc("2025-11-28 13:30:00"),
                _utc("2025-11-28 13:30:15"),
            ],
            "volume": [4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_bar_inside_only_if_half_open_span_fully_in_interval():
    """[t, t+15s) ⊆ interval. Straddle start/end fail; exact edges pass."""
    ticks = _ticks("2025-11-07 18:00:10.000", "2025-11-07 18:00:35.000")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:00"),
                _utc("2025-11-07 18:00:15"),
                _utc("2025-11-07 18:00:30"),
            ],
            "volume": [4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    # Sole empty whole bar is [18:00:15, 18:00:30). Interval starts at 18:00:20 → straddle.
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[(_utc("2025-11-07 18:00:20"), _utc("2025-11-07 18:00:30"))],
        )
    # Interval ends at 18:00:20 → bar extends past the end.
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[(_utc("2025-11-07 18:00:15"), _utc("2025-11-07 18:00:20"))],
        )
    # Exact [18:00:15, 18:00:30) is fully inside.
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[(_utc("2025-11-07 18:00:15"), _utc("2025-11-07 18:00:30"))],
    )


def test_partly_allowed_empty_bars_in_one_hole_fail():
    """Same hole: [18:01:00, 18:01:15) inside X1 window, [18:01:30, 18:01:45) not."""
    ticks = _ticks("2025-11-07 18:00:54.037", "2025-11-07 18:01:50.000")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
                _utc("2025-11-07 18:01:45"),
            ],
            "volume": [4.0, 4.0, 4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[(_utc("2025-11-07 18:00:45"), _utc("2025-11-07 18:01:30"))],
        )


def test_several_allowed_intervals_excuse_only_when_every_empty_bar_fits():
    ticks = _ticks("2025-11-07 18:00:10.000", "2025-11-07 18:01:40.000")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:00"),
                _utc("2025-11-07 18:00:15"),
                _utc("2025-11-07 18:00:30"),
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
            ],
            "volume": [4.0] * 7,
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    # Gap at [18:00:45, 18:01:00) is not in either interval.
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[
                (_utc("2025-11-07 18:00:15"), _utc("2025-11-07 18:00:45")),
                (_utc("2025-11-07 18:01:00"), _utc("2025-11-07 18:01:30")),
            ],
        )
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[
            (_utc("2025-11-07 18:00:15"), _utc("2025-11-07 18:00:45")),
            (_utc("2025-11-07 18:00:45"), _utc("2025-11-07 18:01:30")),
        ],
    )


def test_head_of_hour_and_session_start_use_per_bar_allowlist():
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                _utc("2025-11-07 18:00:00"), _utc("2025-11-07 18:02:00"), freq="15s"
            ),
            "volume": 1.0,
        }
    )
    ticks = _ticks(
        "2025-11-07 18:01:30.100",
        "2025-11-07 18:01:45.100",
        "2025-11-07 18:02:00.100",
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="head-of-hour"):
        guard_hourly_tick_holes(clipped, bars)
    with pytest.raises(TickStitchError, match="head-of-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[(_utc("2025-11-07 18:00:00"), _utc("2025-11-07 18:01:00"))],
        )
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[(_utc("2025-11-07 18:00:00"), _utc("2025-11-07 18:01:30"))],
    )


def test_zero_volume_bar_in_gap_is_not_a_whole_empty_volume_bar():
    """TS3: a mid-hour gap with no volume>0 bar still passes (empty volume-bar set)."""
    ticks = _ticks("2026-03-17 14:10:00", "2026-03-17 14:10:30")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2026-03-17 14:10:00"),
                _utc("2026-03-17 14:10:15"),
                _utc("2026-03-17 14:10:30"),
            ],
            "volume": [4.0, 0.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    guard_hourly_tick_holes(clipped, bars)


def test_tz_aware_chicago_interval_and_naive_utc_match():
    ticks = _ticks("2025-11-07 18:00:54.037", "2025-11-07 18:01:37.500")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
            ],
            "volume": [4.0, 4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    chicago = (
        pd.Timestamp("2025-11-07 12:00:45", tz="America/Chicago"),
        pd.Timestamp("2025-11-07 12:01:30", tz="America/Chicago"),
    )
    guard_hourly_tick_holes(clipped, bars, allowed_intervals=[chicago])
    naive = (
        pd.Timestamp("2025-11-07 18:00:45"),
        pd.Timestamp("2025-11-07 18:01:30"),
    )
    guard_hourly_tick_holes(clipped, bars, allowed_intervals=[naive])


def test_exact_15s_tick_boundary_empty_bar_is_the_open_right_span():
    """Tick at 18:01:00 is the left edge of that bar; [18:01:15, 18:01:30) is empty."""
    ticks = _ticks(
        "2025-11-07 18:00:50.000",
        "2025-11-07 18:01:00.000",
        "2025-11-07 18:01:30.000",
    )
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
            ],
            "volume": [4.0, 4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[(_utc("2025-11-07 18:00:45"), _utc("2025-11-07 18:01:30"))],
    )


def test_1128_cut_short_last_bar_at_1330_fails_last_bar_before_passes():
    """Whole empty bar [13:30:00, 13:30:15) is after the 11-28 end; 13:29:45 is not."""
    ticks = _ticks("2025-11-28 13:20:00.000")
    inside = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                _utc("2025-11-28 13:20:00"), _utc("2025-11-28 13:29:45"), freq="15s"
            ),
            "volume": 1.0,
        }
    )
    guard_hourly_tick_holes(clip_ticks_to_15s_bars(ticks, inside["timestamp"]), inside)
    past = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                _utc("2025-11-28 13:20:00"), _utc("2025-11-28 13:30:00"), freq="15s"
            ),
            "volume": 1.0,
        }
    )
    with pytest.raises(TickStitchError, match="cut short"):
        guard_hourly_tick_holes(clip_ticks_to_15s_bars(ticks, past["timestamp"]), past)


def test_caller_inter_file_weekend_is_honored_and_not_invented():
    """§5 TS3 allowlist (4): caller supplies stitch-meta weekends; none are baked in."""
    bars = _bars("2026-03-21 10:00:00", "2026-03-21 10:59:45")
    empty = pd.DataFrame(columns=["timestamp", "price", "volume"])
    with pytest.raises(TickStitchError, match="no stitched\\+clipped ticks"):
        guard_hourly_tick_holes(empty, bars)
    guard_hourly_tick_holes(
        empty,
        bars,
        allowed_intervals=[(_utc("2026-03-21 10:00:00"), _utc("2026-03-21 11:00:00"))],
    )


def test_inverted_allowed_interval_fails_closed():
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:00:00")
    ticks = _ticks("2026-03-17 14:00:00")
    with pytest.raises(TickStitchError, match="inverted"):
        guard_hourly_tick_holes(
            ticks,
            bars,
            allowed_intervals=[(_utc("2026-03-21 11:00:00"), _utc("2026-03-21 10:00:00"))],
        )


def test_clip_and_guard_are_not_wired_into_execute_or_streamer():
    assert LEVEL_ENGINE_VERSION == 11
    assert "clip_ticks_to_15s_bars" not in inspect.getsource(execute_mod)
    assert "guard_hourly_tick_holes" not in inspect.getsource(execute_mod)
    assert "clip_ticks_to_15s_bars" not in inspect.getsource(loader_mod)
    from thesistester.data import tick_stitch as stitch_mod

    stream_src = inspect.getsource(stitch_mod.iter_stitch_sessions)
    assert "clip_ticks_to_15s_bars" not in stream_src
    assert "guard_hourly_tick_holes" not in stream_src
    # X1 burst window is not a locked member; 11-07 QC bars are (TS5c).
    assert (
        _utc("2025-11-07 18:00:45"),
        _utc("2025-11-07 18:01:30"),
    ) not in stitch_mod._ALLOWLIST_UTC


_QC_EMPTY_BARS: tuple[tuple[str, str], ...] = (
    ("2025-11-07 16:33:15", "bar-assignment mismatch (214 lots)"),
    ("2025-11-07 16:39:30", "bar-assignment mismatch (43)"),
    ("2025-12-24 06:40:45", "bar-assignment mismatch (3)"),
    ("2025-12-24 06:41:30", "bar-assignment mismatch (5)"),
    ("2025-12-24 07:55:00", "bar-assignment mismatch (1)"),
    ("2025-12-24 11:02:30", "bar-assignment mismatch (2)"),
    ("2025-12-24 11:56:00", "bar-assignment mismatch (1)"),
    ("2025-12-26 06:49:45", "bar-assignment mismatch (1)"),
    ("2025-12-26 09:46:30", "bar-assignment mismatch (11)"),
    ("2025-12-26 11:23:15", "bar-assignment mismatch (1)"),
    ("2026-01-23 03:53:15", "bar-assignment mismatch (2)"),
    ("2026-03-24 17:55:30", "tick freeze (44.5 s tick gap mid-US session, 547 lots)"),
    ("2026-04-16 20:39:15", "bar-assignment mismatch (49)"),
    ("2026-04-16 20:46:15", "dual-feed outage (both feeds out 20:44–22:36; 1,511 lots)"),
)


def _qc_window(left: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = _utc(left)
    return start, start + pd.Timedelta(seconds=15)


def _hour_volume_bars(empty_left: pd.Timestamp) -> pd.DataFrame:
    hour = empty_left.floor("h")
    stamps = pd.date_range(hour, hour + pd.Timedelta(minutes=59, seconds=45), freq="15s")
    return pd.DataFrame({"timestamp": stamps, "volume": 1.0})


def _ticks_skipping(bars: pd.DataFrame, *skip: pd.Timestamp) -> pd.DataFrame:
    skip_set = set(skip)
    stamps = [
        ts + pd.Timedelta(milliseconds=7500)
        for ts in bars["timestamp"]
        if pd.Timestamp(ts) not in skip_set
    ]
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "price": [100.0] * len(stamps),
            "volume": [1.0] * len(stamps),
        }
    )


def test_locked_allowlist_is_exactly_1128_plus_14_qc_bars():
    from thesistester.data import tick_stitch as stitch_mod

    expected = (
        (_utc("2025-11-28 02:00:00"), _utc("2025-11-28 13:30:00")),
        *(_qc_window(left) for left, _reason in _QC_EMPTY_BARS),
    )
    assert stitch_mod._ALLOWLIST_UTC == expected
    assert len(stitch_mod._ALLOWLIST_UTC) == 15
    for start, end in stitch_mod._ALLOWLIST_UTC:
        assert start.tz is not None and str(start.tz) == "UTC"
        assert end.tz is not None and str(end.tz) == "UTC"
        assert start < end
    assert stitch_mod._ALLOWLIST_UTC[0][1] - stitch_mod._ALLOWLIST_UTC[0][0] == pd.Timedelta(
        hours=11, minutes=30
    )
    for start, end in stitch_mod._ALLOWLIST_UTC[1:]:
        assert end - start == pd.Timedelta(seconds=15)
    # 11-28 entry stays byte-for-byte the TS3 lock (not rewritten).
    src = inspect.getsource(stitch_mod)
    assert (
        'pd.Timestamp("2025-11-28 02:00:00", tz="UTC"),\n'
        '        pd.Timestamp("2025-11-28 13:30:00", tz="UTC"),'
    ) in src
    assert stitch_mod.hourly_guard_allowed_intervals(True) == stitch_mod._ALLOWLIST_UTC
    burst_off = stitch_mod.hourly_guard_allowed_intervals(False)
    assert set(stitch_mod._ALLOWLIST_UTC).issubset(burst_off)
    # Adjacent QC windows must not merge into a wider hole.
    assert len(stitch_mod._normalize_allowlist(None)) == 15


@pytest.mark.parametrize("left,reason", _QC_EMPTY_BARS, ids=[row[0] for row in _QC_EMPTY_BARS])
def test_qc_empty_bar_alone_in_its_hour_passes(left: str, reason: str):
    empty_left = _utc(left)
    bars = _hour_volume_bars(empty_left)
    ticks = _ticks_skipping(bars, empty_left)
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert empty_left not in set(clipped["timestamp"].dt.floor("15s"))
    guard_hourly_tick_holes(clipped, bars)


@pytest.mark.parametrize("delta_s", [-15, 15], ids=["minus_15s", "plus_15s"])
@pytest.mark.parametrize("left,reason", _QC_EMPTY_BARS, ids=[row[0] for row in _QC_EMPTY_BARS])
def test_qc_neighbor_unlisted_empty_bar_still_fails(left: str, reason: str, delta_s: int):
    """Listed bar plus a ±15s unlisted empty bar is a larger hole and must fail."""
    empty_left = _utc(left)
    neighbor = empty_left + pd.Timedelta(seconds=delta_s)
    assert neighbor.floor("h") == empty_left.floor("h")
    bars = _hour_volume_bars(empty_left)
    ticks = _ticks_skipping(bars, empty_left, neighbor)
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError):
        guard_hourly_tick_holes(clipped, bars)


@pytest.mark.parametrize("delta_s", [-15, 15], ids=["minus_15s", "plus_15s"])
@pytest.mark.parametrize("left,reason", _QC_EMPTY_BARS, ids=[row[0] for row in _QC_EMPTY_BARS])
def test_qc_neighbor_alone_is_not_excused(left: str, reason: str, delta_s: int):
    """Half-open: a bar starting exactly at the window end (or the prior bar) fails."""
    empty_left = _utc(left)
    neighbor = empty_left + pd.Timedelta(seconds=delta_s)
    assert neighbor.floor("h") == empty_left.floor("h")
    bars = _hour_volume_bars(empty_left)
    ticks = _ticks_skipping(bars, neighbor)
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError):
        guard_hourly_tick_holes(clipped, bars)


@pytest.mark.parametrize("left,reason", _QC_EMPTY_BARS, ids=[row[0] for row in _QC_EMPTY_BARS])
def test_qc_same_clock_in_a_different_hour_still_fails(left: str, reason: str):
    """An allowlisted 15s window is an absolute UTC interval, not a clock-of-day match."""
    listed = {_utc(ts) for ts, _reason in _QC_EMPTY_BARS}
    other = _utc(left) + pd.Timedelta(hours=1)
    if other in listed:
        other = _utc(left) - pd.Timedelta(hours=1)
    assert other not in listed
    bars = _hour_volume_bars(other)
    ticks = _ticks_skipping(bars, other)
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError):
        guard_hourly_tick_holes(clipped, bars)


def test_20260416_2000_hour_with_listed_empty_bars_only():
    """Farm QC: last clipped tick 20:43:56.967; empty bars 20:39:15 and 20:46:15.

    20:47:11.877 has no 15s bar and is clipped away. Trailing volume bars
    after 20:46:15 were not in the 14-bar QC list.
    """
    empty_a = _utc("2026-04-16 20:39:15")
    empty_b = _utc("2026-04-16 20:46:15")
    last_tick = _utc("2026-04-16 20:43:56.967")
    orphan = _utc("2026-04-16 20:47:11.877")
    covered = pd.date_range(_utc("2026-04-16 20:00:00"), _utc("2026-04-16 20:43:45"), freq="15s")
    bars = pd.DataFrame(
        {
            "timestamp": list(covered) + [empty_b],
            "volume": [1.0] * (len(covered) + 1),
        }
    )
    tick_stamps = [ts + pd.Timedelta(milliseconds=7500) for ts in covered if ts != empty_a]
    tick_stamps.append(last_tick)
    tick_stamps.append(orphan)
    ticks = pd.DataFrame(
        {
            "timestamp": tick_stamps,
            "price": [100.0] * len(tick_stamps),
            "volume": [1.0] * len(tick_stamps),
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert orphan not in set(clipped["timestamp"])
    assert clipped["timestamp"].max() == last_tick
    guard_hourly_tick_holes(clipped, bars)
