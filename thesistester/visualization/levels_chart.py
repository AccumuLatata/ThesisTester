"""Plotly chart builder for Levels page visualization."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_levels_chart(
    levels_df: pd.DataFrame,
    selected_levels: list[str],
    *,
    use_candles: bool = True,
) -> go.Figure:
    """Build levels preview chart, skipping selected level names not present in levels_df."""

    required = ["timestamp", "close"]
    missing = [col for col in required if col not in levels_df.columns]
    if missing:
        raise ValueError(f"levels_df is missing required columns: {', '.join(missing)}")

    fig = go.Figure()
    ohlc_columns = ["open", "high", "low", "close"]
    has_ohlc = set(ohlc_columns).issubset(levels_df.columns)
    has_complete_ohlc = has_ohlc and not levels_df[ohlc_columns].isna().any().any()
    if use_candles and has_complete_ohlc:
        fig.add_trace(
            go.Candlestick(
                x=levels_df["timestamp"],
                open=levels_df["open"],
                high=levels_df["high"],
                low=levels_df["low"],
                close=levels_df["close"],
                name="OHLC",
            )
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=levels_df["timestamp"],
                y=levels_df["close"],
                mode="lines",
                name="close",
            )
        )

    for column in selected_levels:
        if column not in levels_df.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=levels_df["timestamp"],
                y=levels_df[column],
                mode="lines",
                name=column,
            )
        )

    fig.update_layout(height=520, margin=dict(l=10, r=10, t=35, b=10), legend=dict(orientation="h"))
    return fig
