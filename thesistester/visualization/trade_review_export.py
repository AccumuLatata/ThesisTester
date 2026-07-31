"""Bounded batch export of worst completed trade-review charts."""

from __future__ import annotations

import io
import re
import zipfile
from hashlib import sha256

import pandas as pd
import plotly.io as pio

from .chart_window import clip_by_time_window, selected_trade_time_window
from .trade_review_chart import build_trade_review_chart


def select_worst_losers(trades: pd.DataFrame, *, count: int) -> pd.DataFrame:
    """Return at most count losing trades, ordered by R then stable trade ID."""
    if trades is None or trades.empty or count < 1 or "r_multiple" not in trades:
        return pd.DataFrame(columns=[] if trades is None else trades.columns)
    work = trades.copy(deep=True)
    work["_r20_r"] = pd.to_numeric(work["r_multiple"], errors="coerce")
    work = work.loc[work["_r20_r"] < 0].copy()
    if work.empty:
        return work.drop(columns="_r20_r")
    sort_columns = ["_r20_r"]
    if "trade_id" in work:
        sort_columns.append("trade_id")
    return work.sort_values(sort_columns, kind="mergesort").head(int(count)).drop(columns="_r20_r")


def _filename(trade: pd.Series) -> str:
    trade_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(trade.get("trade_id", "unknown")))
    r_multiple = pd.to_numeric(pd.Series([trade.get("r_multiple")]), errors="coerce").iloc[0]
    r_label = "unknown" if pd.isna(r_multiple) else f"{float(r_multiple):+.2f}R"
    return f"trade_{trade_id}_{r_label}.png"


def _dataframe_digest(frame: pd.DataFrame | None) -> str:
    """Hash chart-input values and schema without retaining the source frame."""
    if frame is None:
        return "none"
    work = frame.copy(deep=True)
    hasher = sha256()
    hasher.update(repr(tuple(work.columns)).encode("utf-8"))
    hasher.update(repr(tuple(str(dtype) for dtype in work.dtypes)).encode("utf-8"))
    hasher.update(pd.util.hash_pandas_object(work, index=True).to_numpy().tobytes())
    return hasher.hexdigest()


def trade_review_export_signature(
    trades: pd.DataFrame,
    *,
    count: int,
    buffer_rows: int,
    show_sessions: bool,
    show_levels: bool,
    show_confluence_zones: bool,
    show_final_stop: bool,
    ohlcv_df: pd.DataFrame | None = None,
    levels: pd.DataFrame | None = None,
    confluence_zones: pd.DataFrame | None = None,
) -> str:
    """Return a stable identity for the export inputs and display configuration."""
    selected = select_worst_losers(trades, count=count)
    payload = selected.to_json(orient="split", date_format="iso", default_handler=str)
    settings = (
        int(count),
        int(buffer_rows),
        bool(show_sessions),
        bool(show_levels),
        bool(show_confluence_zones),
        bool(show_final_stop),
    )
    inputs = (
        _dataframe_digest(ohlcv_df),
        _dataframe_digest(levels),
        _dataframe_digest(confluence_zones),
    )
    return sha256(repr((payload, settings, inputs)).encode("utf-8")).hexdigest()


def _image_safe_chart(chart):
    """Round-trip through Plotly JSON to normalize pandas timestamps for Kaleido."""
    return pio.from_json(chart.to_json())


def export_worst_loser_review_pngs(
    trades: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    *,
    count: int,
    buffer_rows: int,
    levels: pd.DataFrame | None = None,
    confluence_zones: pd.DataFrame | None = None,
    show_sessions: bool = True,
    show_levels: bool = True,
    show_confluence_zones: bool = True,
    show_final_stop: bool = False,
) -> bytes:
    """Return a ZIP of bounded PNG charts for the worst-N losing trades.

    Plotly's Kaleido backend is required by `Figure.to_image`; callers should
    surface its installation error rather than silently emitting a different
    artifact format.
    """
    if ohlcv_df is None or ohlcv_df.empty:
        raise ValueError("OHLCV data is required for trade-review export.")
    selected = select_worst_losers(trades, count=count)
    if selected.empty:
        raise ValueError("No losing trades are available for export.")
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for _, trade in selected.iterrows():
            start, end = selected_trade_time_window(
                trade,
                ohlcv_df=ohlcv_df,
                buffer_rows=buffer_rows,
            )
            if start is None or end is None:
                raise ValueError(
                    f"Trade {trade.get('trade_id', '—')} has no usable timestamps for a bounded review."
                )
            chart = build_trade_review_chart(
                clip_by_time_window(ohlcv_df, start=start, end=end),
                trade,
                levels=clip_by_time_window(levels, start=start, end=end),
                confluence_zones=clip_by_time_window(confluence_zones, start=start, end=end),
                show_sessions=show_sessions,
                show_levels=show_levels,
                show_confluence_zones=show_confluence_zones,
                show_final_stop=show_final_stop,
            )
            archive.writestr(
                _filename(trade),
                _image_safe_chart(chart).to_image(format="png", scale=2),
            )
    return output.getvalue()
