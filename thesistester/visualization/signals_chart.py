"""Plotly chart builder for Signals page visualization."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def _build_hover_text(rows: pd.DataFrame, fields: list[tuple[str, str]]) -> list[str]:
    hover_text: list[str] = []
    for _, row in rows.iterrows():
        parts: list[str] = []
        for column, label in fields:
            if column not in rows.columns:
                continue
            value = row[column]
            if pd.isna(value):
                continue
            if isinstance(value, pd.Timestamp):
                rendered = value.isoformat()
            else:
                rendered = str(value)
            parts.append(f"{label}: {rendered}")
        hover_text.append("<br>".join(parts))
    return hover_text


def build_signals_chart(
    levels_df: pd.DataFrame,
    signals: pd.DataFrame | None,
    selected_levels: list[str],
    *,
    confluence_zones: pd.DataFrame | None = None,
    show_confluence_zones: bool = True,
    use_candles: bool = True,
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
    if confluence_zones is not None and not confluence_zones.empty:
        required_zone_cols = ["timestamp", "zone_low", "zone_high"]
        missing_zone_cols = [col for col in required_zone_cols if col not in confluence_zones.columns]
        if missing_zone_cols:
            raise ValueError(
                f"confluence_zones is missing required columns: {', '.join(missing_zone_cols)}"
            )

    fig = go.Figure()

    ohlc_columns = {"open", "high", "low", "close"}
    has_ohlc = ohlc_columns.issubset(levels_df.columns)
    if use_candles and has_ohlc:
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

        marker_hover_fields = [
            ("timestamp", "timestamp"),
            ("direction", "direction"),
            ("status", "status"),
            ("trigger", "trigger"),
            ("entry_reference_price", "entry reference price"),
            ("zone_low", "zone low"),
            ("zone_high", "zone high"),
            ("zone_mid", "zone mid"),
            ("level_count", "level count"),
            ("level_names", "level names"),
            ("setup_name", "setup name"),
        ]

        if not long_filled.empty:
            fig.add_trace(
                go.Scatter(
                    x=long_filled["timestamp"],
                    y=long_filled["entry_reference_price"],
                    mode="markers",
                    name="long (candidate/filled)",
                    marker=dict(symbol="triangle-up", color="limegreen", size=10),
                    text=_build_hover_text(long_filled, marker_hover_fields),
                    hovertemplate="%{text}<extra></extra>",
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
                    text=_build_hover_text(short_filled, marker_hover_fields),
                    hovertemplate="%{text}<extra></extra>",
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
                    text=_build_hover_text(long_void, marker_hover_fields),
                    hovertemplate="%{text}<extra></extra>",
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
                    text=_build_hover_text(short_void, marker_hover_fields),
                    hovertemplate="%{text}<extra></extra>",
                )
            )

    if show_confluence_zones and confluence_zones is not None and not confluence_zones.empty:
        zone_hover_fields = [
            ("timestamp", "timestamp"),
            ("zone_low", "zone low"),
            ("zone_high", "zone high"),
            ("zone_mid", "zone mid"),
            ("level_count", "level count"),
            ("level_names", "level names"),
        ]
        x_values: list[object] = []
        y_values: list[object] = []
        text_values: list[object] = []
        for _, zone in confluence_zones.iterrows():
            hover_text = "<br>".join(
                [
                    f"{label}: {zone[col].isoformat() if isinstance(zone[col], pd.Timestamp) else zone[col]}"
                    for col, label in zone_hover_fields
                    if col in confluence_zones.columns and not pd.isna(zone[col])
                ]
            )
            x_values.extend([zone["timestamp"], zone["timestamp"], None])
            y_values.extend([zone["zone_low"], zone["zone_high"], None])
            text_values.extend([hover_text, hover_text, None])

        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines",
                name="Confluence zones",
                line=dict(color="mediumpurple", width=3),
                opacity=0.55,
                text=text_values,
                hovertemplate="%{text}<extra></extra>",
            )
        )

    fig.update_layout(
        height=560,
        margin=dict(l=10, r=10, t=35, b=10),
        legend=dict(orientation="h"),
    )
    return fig
