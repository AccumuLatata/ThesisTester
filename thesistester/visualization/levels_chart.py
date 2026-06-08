"""Plotly chart builder for Levels page visualization."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_levels_chart(
    levels_df: pd.DataFrame,
    selected_levels: list[str],
) -> go.Figure:
    """Build levels preview chart from levels DataFrame and selected level names."""
    fig = go.Figure()
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
