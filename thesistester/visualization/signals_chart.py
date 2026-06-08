"""Plotly chart builder for Signals page visualization."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_signals_chart(
    levels_df: pd.DataFrame,
    signals: pd.DataFrame | None,
    selected_levels: list[str],
) -> go.Figure:
    """Build signal preview chart; when signals is None/empty only price and selected levels are drawn."""

    required_levels = ["timestamp", "close"]
    missing_levels = [col for col in required_levels if col not in levels_df.columns]
    if missing_levels:
        raise ValueError(f"levels_df is missing required columns: {', '.join(missing_levels)}")

    if signals is not None and not signals.empty:
        required_signals = ["timestamp", "direction", "status", "entry_reference_price"]
        missing_signals = [col for col in required_signals if col not in signals.columns]
        if missing_signals:
            raise ValueError(f"signals is missing required columns: {', '.join(missing_signals)}")

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=levels_df["timestamp"],
            y=levels_df["close"],
            mode="lines",
            name="close",
            line=dict(color="steelblue", width=1),
        )
    )

    for column in selected_levels[:5]:
        if column not in levels_df.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=levels_df["timestamp"],
                y=levels_df[column],
                mode="lines",
                name=column,
                line=dict(width=1, dash="dot"),
                opacity=0.6,
            )
        )

    if signals is not None and not signals.empty:
        long_filled = signals[(signals["direction"] == "long") & (signals["status"].isin(["candidate", "filled"]))]
        short_filled = signals[(signals["direction"] == "short") & (signals["status"].isin(["candidate", "filled"]))]
        long_void = signals[(signals["direction"] == "long") & (signals["status"] == "void")]
        short_void = signals[(signals["direction"] == "short") & (signals["status"] == "void")]

        if not long_filled.empty:
            fig.add_trace(
                go.Scatter(
                    x=long_filled["timestamp"],
                    y=long_filled["entry_reference_price"],
                    mode="markers",
                    name="long (candidate/filled)",
                    marker=dict(symbol="triangle-up", color="limegreen", size=10),
                )
            )

        if not short_filled.empty:
            fig.add_trace(
                go.Scatter(
                    x=short_filled["timestamp"],
                    y=short_filled["entry_reference_price"],
                    mode="markers",
                    name="short (candidate/filled)",
                    marker=dict(symbol="triangle-down", color="tomato", size=10),
                )
            )

        if not long_void.empty:
            fig.add_trace(
                go.Scatter(
                    x=long_void["timestamp"],
                    y=long_void["entry_reference_price"],
                    mode="markers",
                    name="long void",
                    marker=dict(symbol="x", color="mediumseagreen", size=8, opacity=0.4),
                )
            )

        if not short_void.empty:
            fig.add_trace(
                go.Scatter(
                    x=short_void["timestamp"],
                    y=short_void["entry_reference_price"],
                    mode="markers",
                    name="short void",
                    marker=dict(symbol="x", color="salmon", size=8, opacity=0.4),
                )
            )

    fig.update_layout(
        height=560,
        margin=dict(l=10, r=10, t=35, b=10),
        legend=dict(orientation="h"),
    )
    return fig
