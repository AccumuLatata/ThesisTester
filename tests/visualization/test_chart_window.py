from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from thesistester.visualization.chart_window import (
    clip_by_time_window,
    recent_rows_window,
    timestamp_bounds,
    trade_time_window,
)


def test_timestamp_bounds_returns_min_and_max():
    df = pd.DataFrame(
        {"timestamp": ["2026-01-01 09:31:00", "2026-01-01 09:30:00", "2026-01-01 09:32:00"]}
    )

    start, end = timestamp_bounds(df)

    assert start == pd.Timestamp("2026-01-01 09:30:00")
    assert end == pd.Timestamp("2026-01-01 09:32:00")


def test_timestamp_bounds_returns_none_for_missing_timestamp_column():
    start, end = timestamp_bounds(pd.DataFrame({"close": [1, 2, 3]}))

    assert start is None
    assert end is None


def test_clip_by_time_window_clips_rows_by_bounds():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:30:00", periods=5, freq="min"),
            "close": [1, 2, 3, 4, 5],
        }
    )

    clipped = clip_by_time_window(
        df,
        start=pd.Timestamp("2026-01-01 09:31:00"),
        end=pd.Timestamp("2026-01-01 09:33:00"),
    )

    assert clipped["close"].tolist() == [2, 3, 4]


def test_clip_by_time_window_returns_copy_and_does_not_mutate_input():
    df = pd.DataFrame({"timestamp": ["2026-01-01 09:30:00"], "close": [1]})
    before = df.copy(deep=True)

    clipped = clip_by_time_window(df, start=None, end=None)

    assert_frame_equal(df, before)
    assert_frame_equal(clipped, before)
    assert clipped is not df


def test_clip_by_time_window_handles_none_dataframe():
    assert clip_by_time_window(None, start=None, end=None) is None


def test_clip_by_time_window_handles_invalid_timestamps_safely():
    df = pd.DataFrame(
        {
            "timestamp": ["bad", "2026-01-01 09:30:00", "also_bad"],
            "close": [1, 2, 3],
        }
    )

    clipped = clip_by_time_window(
        df,
        start=pd.Timestamp("2026-01-01 09:00:00"),
        end=pd.Timestamp("2026-01-01 10:00:00"),
    )

    assert clipped["close"].tolist() == [2]


def test_recent_rows_window_returns_last_n_row_bounds():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 09:30:00", periods=6, freq="min"),
            "close": [1, 2, 3, 4, 5, 6],
        }
    )

    start, end = recent_rows_window(df, rows=3)

    assert start == pd.Timestamp("2026-01-01 09:33:00")
    assert end == pd.Timestamp("2026-01-01 09:35:00")


def test_recent_rows_window_handles_rows_larger_than_dataframe():
    df = pd.DataFrame({"timestamp": pd.date_range("2026-01-01 09:30:00", periods=2, freq="min")})

    start, end = recent_rows_window(df, rows=10)

    assert start == pd.Timestamp("2026-01-01 09:30:00")
    assert end == pd.Timestamp("2026-01-01 09:31:00")


def test_trade_time_window_returns_window_around_first_trade():
    ohlcv_df = pd.DataFrame({"timestamp": pd.date_range("2026-01-01 09:30:00", periods=10, freq="min")})
    trades = pd.DataFrame(
        [
            {"entry_timestamp": "2026-01-01 09:33:00", "exit_timestamp": "2026-01-01 09:35:00"},
            {"entry_timestamp": "2026-01-01 09:37:00", "exit_timestamp": "2026-01-01 09:38:00"},
        ]
    )

    start, end = trade_time_window(trades, ohlcv_df=ohlcv_df, buffer_rows=2)

    assert start == pd.Timestamp("2026-01-01 09:31:00")
    assert end == pd.Timestamp("2026-01-01 09:37:00")


def test_trade_time_window_handles_empty_trades():
    ohlcv_df = pd.DataFrame({"timestamp": pd.date_range("2026-01-01 09:30:00", periods=10, freq="min")})
    start, end = trade_time_window(pd.DataFrame(columns=["entry_timestamp", "exit_timestamp"]), ohlcv_df=ohlcv_df)

    assert start is None
    assert end is None


def test_clip_by_time_window_preserves_original_row_order():
    df = pd.DataFrame(
        {
            "timestamp": [
                "2026-01-01 09:33:00",
                "2026-01-01 09:31:00",
                "2026-01-01 09:32:00",
            ],
            "close": [3, 1, 2],
        }
    )

    clipped = clip_by_time_window(
        df,
        start=pd.Timestamp("2026-01-01 09:31:00"),
        end=pd.Timestamp("2026-01-01 09:32:00"),
    )

    assert clipped["close"].tolist() == [1, 2]
