"""Phase 7 analytics — time-of-day and session-window performance breakdown.

All functions are pure pandas transformations that operate on the trade
DataFrame produced by :func:`~thesistester.engine.backtest.simulate_trades`.
No trade simulation is performed here; this module is purely descriptive.

RTH segment definitions (America/New_York):

+-------------------+------------------+
| Segment           | Time range ET    |
+===================+==================+
| pre_rth           | before 09:30     |
+-------------------+------------------+
| rth_open_30m      | 09:30 – 09:59    |
+-------------------+------------------+
| rth_morning       | 10:00 – 11:29    |
+-------------------+------------------+
| rth_midday        | 11:30 – 13:29    |
+-------------------+------------------+
| rth_afternoon     | 13:30 – 14:59    |
+-------------------+------------------+
| rth_power_hour    | 15:00 – 15:59    |
+-------------------+------------------+
| post_rth          | 16:00 and later  |
+-------------------+------------------+
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Ordered segment definitions as (start_minute_of_day, end_minute_of_day,
# label) tuples.  ``end_minute_of_day`` is exclusive.
_RTH_SEGMENTS: list[tuple[int, int, str]] = [
    (0, 570, "pre_rth"),          # < 09:30
    (570, 600, "rth_open_30m"),   # 09:30 – 09:59
    (600, 690, "rth_morning"),    # 10:00 – 11:29
    (690, 810, "rth_midday"),     # 11:30 – 13:29
    (810, 900, "rth_afternoon"),  # 13:30 – 14:59
    (900, 960, "rth_power_hour"), # 15:00 – 15:59
    (960, 1440, "post_rth"),      # 16:00+
]

# New columns added by add_time_buckets (used for empty-DataFrame guarantees)
_TIME_BUCKET_COLS: list[str] = [
    "entry_date",
    "entry_time",
    "entry_hour",
    "entry_minute",
    "entry_hour_bucket",
    "entry_30min_bucket",
    "entry_rth_segment",
]

# Columns returned by summarize_by_group (in display order)
_GROUP_SUMMARY_COLS: list[str] = [
    "trade_count",
    "win_rate",
    "loss_rate",
    "avg_r",
    "median_r",
    "total_r",
    "profit_factor",
    "avg_win_r",
    "avg_loss_r",
    "max_drawdown_r",
    "best_trade_r",
    "worst_trade_r",
    "sample_warning",
]


def _minute_of_day(t: pd.Series) -> pd.Series:
    """Return hour * 60 + minute for a Series of time objects."""
    return t.dt.hour * 60 + t.dt.minute


def _rth_segment(minute: int) -> str:
    for start, end, label in _RTH_SEGMENTS:
        if start <= minute < end:
            return label
    return "post_rth"


def _group_max_drawdown(r: pd.Series) -> float:
    """Max drawdown of cumulative R within a group, anchored at 0R."""
    if r.empty:
        return 0.0
    cum = r.cumsum()
    running_max = cum.cummax().clip(lower=0.0)
    return float((running_max - cum).max())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_time_buckets(
    trades: pd.DataFrame,
    timestamp_col: str = "entry_timestamp",
    exchange_tz: str = "America/New_York",
    *,
    bucket_tz: str | None = None,
    session_tz: str | None = None,
) -> pd.DataFrame:
    """Return a copy of *trades* with time-bucket columns added.

    Parameters
    ----------
    trades:
        Trade DataFrame from Phase 5; may be empty.
    timestamp_col:
        Name of the timestamp column to bucket.  Column names of the
        added columns are always ``entry_``-prefixed regardless of which
        source column is used.
    exchange_tz:
        IANA timezone string for the exchange/canonical engine timezone
        (default ``"America/New_York"``). Also used to localize tz-naive
        timestamps for backward compatibility.
    bucket_tz:
        IANA timezone string used for ``entry_date``, ``entry_time``,
        ``entry_hour``, ``entry_minute``, ``entry_hour_bucket``, and
        ``entry_30min_bucket``. Defaults to *exchange_tz*.
    session_tz:
        IANA timezone string used for ``entry_rth_segment``. Defaults to
        *exchange_tz*.

    Returns
    -------
    pd.DataFrame
        Copy of *trades* with columns:

        ``entry_date``, ``entry_time``, ``entry_hour``, ``entry_minute``,
        ``entry_hour_bucket``, ``entry_30min_bucket``, ``entry_rth_segment``.

        If *trades* is empty the extra columns are added but all rows are
        empty.
    """
    result = trades.copy()
    bucket_tz = bucket_tz or exchange_tz
    session_tz = session_tz or exchange_tz

    if result.empty or timestamp_col not in result.columns:
        for col in _TIME_BUCKET_COLS:
            result[col] = pd.Series(dtype=object)
        return result

    ts = result[timestamp_col]

    # Ensure timezone-aware timestamps in exchange_tz for canonical handling.
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(exchange_tz)
    else:
        ts = ts.dt.tz_convert(exchange_tz)

    bucket_ts = ts.dt.tz_convert(bucket_tz)
    session_ts = ts.dt.tz_convert(session_tz)

    result["entry_date"] = bucket_ts.dt.date
    result["entry_time"] = bucket_ts.dt.time
    result["entry_hour"] = bucket_ts.dt.hour
    result["entry_minute"] = bucket_ts.dt.minute

    # Hour bucket: "09:00", "10:00", …
    result["entry_hour_bucket"] = bucket_ts.dt.strftime("%H:00").astype(str)

    # 30-minute bucket: "09:30", "10:00", …
    half_hour = (bucket_ts.dt.minute // 30) * 30
    result["entry_30min_bucket"] = (
        bucket_ts.dt.strftime("%H:") + half_hour.astype(str).str.zfill(2)
    ).astype(str)

    # RTH segment stays aligned with session/exchange time.
    mod = _minute_of_day(session_ts)
    result["entry_rth_segment"] = mod.map(_rth_segment)

    return result


def summarize_by_group(
    trades: pd.DataFrame,
    group_cols: list[str] | str,
    min_trades: int = 1,
) -> pd.DataFrame:
    """Group trades and compute per-group performance metrics.

    Parameters
    ----------
    trades:
        Trade DataFrame (typically the output of :func:`add_time_buckets`).
        Must contain an ``r_multiple`` column.
    group_cols:
        Column name(s) to group by.  May be a single string or a list.
    min_trades:
        Groups with fewer trades than this threshold get
        ``sample_warning = True``.

    Returns
    -------
    pd.DataFrame
        One row per group.  Columns: group columns followed by
        ``trade_count``, ``win_rate``, ``loss_rate``, ``avg_r``,
        ``median_r``, ``total_r``, ``profit_factor``, ``avg_win_r``,
        ``avg_loss_r``, ``max_drawdown_r``, ``best_trade_r``,
        ``worst_trade_r``, ``sample_warning``.

        Returns an empty DataFrame with those columns when *trades* is
        empty or ``r_multiple`` is absent.
    """
    if isinstance(group_cols, str):
        group_cols = [group_cols]

    all_cols = list(group_cols) + _GROUP_SUMMARY_COLS
    empty = pd.DataFrame(columns=all_cols)

    if trades is None or trades.empty:
        return empty
    if "r_multiple" not in trades.columns:
        return empty

    # Use exit_timestamp for ordering within each group where available
    has_exit_ts = "exit_timestamp" in trades.columns

    rows: list[dict] = []
    for keys, group in trades.groupby(group_cols, sort=True, observed=True):
        if has_exit_ts:
            group = group.sort_values("exit_timestamp")

        r = group["r_multiple"].dropna()
        n = len(r)

        wins = r[r > 0]
        losses = r[r < 0]
        gross_win = float(wins.sum()) if len(wins) > 0 else 0.0
        gross_loss = float(losses.sum()) if len(losses) > 0 else 0.0

        if gross_loss < 0:
            profit_factor = gross_win / abs(gross_loss)
        elif gross_win > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        row: dict = {}
        # pandas groupby with a list always returns tuples; normalise
        if len(group_cols) == 1:
            row[group_cols[0]] = keys if not isinstance(keys, tuple) else keys[0]
        else:
            for col, val in zip(group_cols, keys):
                row[col] = val

        row["trade_count"] = n
        row["win_rate"] = float(len(wins) / n) if n > 0 else None
        row["loss_rate"] = float(len(losses) / n) if n > 0 else None
        row["avg_r"] = float(r.mean()) if n > 0 else None
        row["median_r"] = float(r.median()) if n > 0 else None
        row["total_r"] = float(r.sum()) if n > 0 else None
        row["profit_factor"] = profit_factor if n > 0 else None
        row["avg_win_r"] = float(wins.mean()) if len(wins) > 0 else None
        row["avg_loss_r"] = float(losses.mean()) if len(losses) > 0 else None
        row["max_drawdown_r"] = _group_max_drawdown(r) if n > 0 else None
        row["best_trade_r"] = float(r.max()) if n > 0 else None
        row["worst_trade_r"] = float(r.min()) if n > 0 else None
        row["sample_warning"] = n < min_trades

        rows.append(row)

    if not rows:
        return empty

    result = pd.DataFrame(rows)
    # Ensure consistent column order
    present_group_cols = [c for c in group_cols if c in result.columns]
    metric_cols = [c for c in _GROUP_SUMMARY_COLS if c in result.columns]
    result = result[present_group_cols + metric_cols]
    return result.sort_values(group_cols).reset_index(drop=True)


def pivot_time_metric(
    grouped: pd.DataFrame,
    index_col: str,
    metric: str,
    column_col: str | None = None,
) -> pd.DataFrame:
    """Pivot a grouped performance table into a heatmap-ready form.

    Parameters
    ----------
    grouped:
        Output of :func:`summarize_by_group`.
    index_col:
        Column to use as the pivot index (rows).
    metric:
        Metric column to use as values.
    column_col:
        Column to use as pivot columns.  When ``None``, a one-dimensional
        DataFrame indexed by *index_col* is returned instead.

    Returns
    -------
    pd.DataFrame
        Pivoted DataFrame sorted by index and columns.  Empty input
        returns an empty DataFrame.
    """
    if grouped is None or grouped.empty:
        return pd.DataFrame()

    if index_col not in grouped.columns or metric not in grouped.columns:
        return pd.DataFrame()

    if column_col is None:
        result = (
            grouped[[index_col, metric]]
            .set_index(index_col)
            .sort_index()
        )
        return result

    if column_col not in grouped.columns:
        return pd.DataFrame()

    pivot = grouped.pivot(index=index_col, columns=column_col, values=metric)
    pivot = pivot.sort_index().sort_index(axis=1)
    return pivot
