"""Pure helper utilities for visualization-only chart windowing."""
from __future__ import annotations

import pandas as pd


def _coerce_scalar_timestamp(value: object) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    if isinstance(ts, pd.Timestamp) and ts.tzinfo is not None:
        return ts.tz_localize(None)
    return ts


def coerce_timestamp_series(series: pd.Series) -> pd.Series:
    """Return datetime-coerced timestamps without mutating the input."""
    coerced = pd.to_datetime(series.copy(deep=True), errors="coerce")
    if isinstance(getattr(coerced, "dtype", None), pd.DatetimeTZDtype):
        return coerced.dt.tz_localize(None)
    return coerced


def timestamp_bounds(
    df: pd.DataFrame,
    timestamp_col: str = "timestamp",
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Return min/max timestamp bounds, or (None, None) if unavailable."""
    if df is None or df.empty or timestamp_col not in df.columns:
        return None, None
    timestamps = coerce_timestamp_series(df[timestamp_col]).dropna()
    if timestamps.empty:
        return None, None
    return timestamps.min(), timestamps.max()


def clip_by_time_window(
    df: pd.DataFrame | None,
    *,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame | None:
    """Return a clipped copy of df by timestamp_col without mutating input."""
    if df is None:
        return None

    start_ts = _coerce_scalar_timestamp(start)
    end_ts = _coerce_scalar_timestamp(end)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts

    out = df.copy(deep=True)
    if (start_ts is None and end_ts is None) or timestamp_col not in out.columns or out.empty:
        return out

    timestamps = coerce_timestamp_series(out[timestamp_col])
    mask = timestamps.notna()
    if start_ts is not None:
        mask &= timestamps >= start_ts
    if end_ts is not None:
        mask &= timestamps <= end_ts
    return out.loc[mask].copy(deep=True)


def recent_rows_window(
    df: pd.DataFrame,
    *,
    rows: int,
    timestamp_col: str = "timestamp",
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Return timestamp bounds covering the last N rows."""
    if df is None or df.empty or rows <= 0 or timestamp_col not in df.columns:
        return None, None
    return timestamp_bounds(df.tail(rows), timestamp_col=timestamp_col)


def trade_time_window(
    trades: pd.DataFrame,
    *,
    ohlcv_df: pd.DataFrame,
    buffer_rows: int = 100,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """
    Return a default backtest chart window around the first available trade:
    entry_timestamp - buffer rows to exit_timestamp + buffer rows.
    """
    if (
        trades is None
        or trades.empty
        or ohlcv_df is None
        or ohlcv_df.empty
        or "timestamp" not in ohlcv_df.columns
        or "entry_timestamp" not in trades.columns
        or "exit_timestamp" not in trades.columns
    ):
        return None, None

    trade_times = trades.copy(deep=True)
    trade_times["entry_timestamp"] = coerce_timestamp_series(trade_times["entry_timestamp"])
    trade_times["exit_timestamp"] = coerce_timestamp_series(trade_times["exit_timestamp"])
    valid_trades = trade_times[
        trade_times["entry_timestamp"].notna() | trade_times["exit_timestamp"].notna()
    ]
    if valid_trades.empty:
        return None, None

    first_trade = valid_trades.iloc[0]
    trade_start = first_trade["entry_timestamp"]
    trade_end = first_trade["exit_timestamp"]
    if pd.isna(trade_start):
        trade_start = trade_end
    if pd.isna(trade_end):
        trade_end = trade_start
    if pd.isna(trade_start) or pd.isna(trade_end):
        return None, None
    if trade_start > trade_end:
        trade_start, trade_end = trade_end, trade_start

    timeline = coerce_timestamp_series(ohlcv_df["timestamp"]).dropna().sort_values().reset_index(drop=True)
    if timeline.empty:
        return None, None

    start_idx = int(timeline.searchsorted(trade_start, side="left"))
    end_idx = int(timeline.searchsorted(trade_end, side="right")) - 1
    if end_idx < 0:
        end_idx = 0
    if start_idx >= len(timeline):
        start_idx = len(timeline) - 1
    if end_idx < start_idx:
        end_idx = start_idx

    window_start_idx = max(0, start_idx - max(buffer_rows, 0))
    window_end_idx = min(len(timeline) - 1, end_idx + max(buffer_rows, 0))
    return timeline.iloc[window_start_idx], timeline.iloc[window_end_idx]
