"""Plotly candlestick chart builder for backtest execution visualization."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


_BASE_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume", "session", "settlement"}
_DEFAULT_LEVEL_COUNT = 4
_MAX_PLOTTED_LEVELS = 8
_MAX_PLOTTED_ZONES = 24
_LEVEL_LINE_STYLE = dict(width=1, dash="dot")
_ZONE_LINE_STYLE = dict(color="mediumpurple", width=3)
_STOP_LINE_STYLE = dict(color="crimson", width=1.2, dash="dot")
_TARGET_LINE_STYLE = dict(color="seagreen", width=1.2, dash="dot")


def _prepare_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"OHLCV data is missing required columns: {', '.join(missing)}")

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp")
    return out.reset_index(drop=True)


def _parse_level_names(raw_names: pd.Series) -> list[str]:
    names: list[str] = []
    for raw in raw_names.dropna().astype(str):
        for name in raw.split("|"):
            cleaned = name.strip()
            if cleaned and cleaned not in names:
                names.append(cleaned)
    return names


def _add_session_context(fig: go.Figure, ohlcv: pd.DataFrame) -> None:
    if "session" not in ohlcv.columns:
        return

    tagged = ohlcv[["timestamp", "session"]].dropna(subset=["session"]).copy()
    if tagged.empty:
        return

    tagged["session"] = tagged["session"].astype(str)
    tagged["segment"] = tagged["session"].ne(tagged["session"].shift()).cumsum()

    for _, segment in tagged.groupby("segment", sort=False):
        label = str(segment["session"].iloc[0]).upper()
        if label != "ETH":
            continue
        fig.add_vrect(
            x0=segment["timestamp"].iloc[0],
            x1=segment["timestamp"].iloc[-1],
            fillcolor="rgba(211, 211, 211, 0.18)",
            line_width=0,
            layer="below",
        )

    rth_starts = tagged[(tagged["session"].str.upper() == "RTH") & (tagged["session"].shift().str.upper() != "RTH")]
    for ts in rth_starts["timestamp"]:
        fig.add_vline(
            x=ts,
            line_width=1,
            line_dash="dot",
            line_color="rgba(70, 130, 180, 0.8)",
        )


def _select_confluence_zones(zones: pd.DataFrame, trades: pd.DataFrame | None) -> pd.DataFrame:
    if trades is None or trades.empty:
        return zones.head(_MAX_PLOTTED_ZONES)

    link_columns = ["zone_low", "zone_high"]
    if "level_names" in zones.columns and "level_names" in trades.columns:
        link_columns.append("level_names")

    if not {"zone_low", "zone_high"}.issubset(trades.columns):
        return zones.head(_MAX_PLOTTED_ZONES)

    trade_keys = trades[link_columns].dropna(subset=["zone_low", "zone_high"]).drop_duplicates()
    if trade_keys.empty:
        return zones.head(_MAX_PLOTTED_ZONES)

    related_zones = zones.merge(trade_keys, on=link_columns, how="inner").drop_duplicates()
    if not related_zones.empty:
        return related_zones

    return zones.head(_MAX_PLOTTED_ZONES)


def build_backtest_candlestick_chart(
    ohlcv_df: pd.DataFrame,
    trades: pd.DataFrame,
    levels: pd.DataFrame | None = None,
    confluence_zones: pd.DataFrame | None = None,
    show_sessions: bool = True,
) -> go.Figure:
    """Build a candlestick chart with backtest overlays."""
    ohlcv = _prepare_ohlcv(ohlcv_df)

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=ohlcv["timestamp"],
            open=ohlcv["open"],
            high=ohlcv["high"],
            low=ohlcv["low"],
            close=ohlcv["close"],
            name="OHLC",
        )
    )

    if show_sessions:
        _add_session_context(fig, ohlcv)

    if levels is not None and not levels.empty and "timestamp" in levels.columns:
        levels_df = levels
        level_timeline = levels_df.copy()
        level_timeline["timestamp"] = pd.to_datetime(level_timeline["timestamp"], errors="coerce")
        level_timeline = level_timeline.dropna(subset=["timestamp"]).sort_values("timestamp")

        candidate_level_columns = [
            column
            for column in level_timeline.columns
            if column not in _BASE_COLUMNS and pd.api.types.is_numeric_dtype(level_timeline[column])
        ]
        plotted_level_columns: list[str] = []
        if trades is not None and not trades.empty and "level_names" in trades.columns:
            for level_name in _parse_level_names(trades["level_names"]):
                if level_name in candidate_level_columns:
                    plotted_level_columns.append(level_name)
        if not plotted_level_columns:
            plotted_level_columns = candidate_level_columns[:_DEFAULT_LEVEL_COUNT]

        for level_name in plotted_level_columns[:_MAX_PLOTTED_LEVELS]:
            fig.add_trace(
                go.Scatter(
                    x=level_timeline["timestamp"],
                    y=level_timeline[level_name],
                    mode="lines",
                    name=f"Level: {level_name}",
                    line=_LEVEL_LINE_STYLE,
                    opacity=0.55,
                )
            )

    if confluence_zones is not None and not confluence_zones.empty:
        required_zone_columns = {"timestamp", "zone_low", "zone_high"}
        if required_zone_columns.issubset(confluence_zones.columns):
            zones = confluence_zones.copy()
            zones["timestamp"] = pd.to_datetime(zones["timestamp"], errors="coerce")
            zones = zones.dropna(subset=["timestamp", "zone_low", "zone_high"])
            zones = zones.sort_values("timestamp")
            zones = _select_confluence_zones(zones, trades)
            if not zones.empty:
                zone_x_coords: list[object] = []
                zone_y_coords: list[float | None] = []
                for row in zones.itertuples(index=False):
                    zone_x_coords.extend([row.timestamp, row.timestamp, None])
                    zone_y_coords.extend([float(row.zone_low), float(row.zone_high), None])
                fig.add_trace(
                    go.Scatter(
                        x=zone_x_coords,
                        y=zone_y_coords,
                        mode="lines",
                        line=_ZONE_LINE_STYLE,
                        name="Confluence zones",
                        opacity=0.55,
                    )
                )

    if trades is not None and not trades.empty:
        chart_trades = trades.copy()
        chart_trades["entry_timestamp"] = pd.to_datetime(chart_trades["entry_timestamp"], errors="coerce")
        chart_trades["exit_timestamp"] = pd.to_datetime(chart_trades["exit_timestamp"], errors="coerce")
        chart_trades = chart_trades.dropna(subset=["entry_timestamp", "entry_price"])

        long_trades = chart_trades[chart_trades["direction"] == "long"]
        short_trades = chart_trades[chart_trades["direction"] == "short"]

        if not long_trades.empty:
            fig.add_trace(
                go.Scatter(
                    x=long_trades["entry_timestamp"],
                    y=long_trades["entry_price"],
                    mode="markers",
                    name="Long entries",
                    marker=dict(symbol="triangle-up", size=11, color="limegreen"),
                )
            )
        if not short_trades.empty:
            fig.add_trace(
                go.Scatter(
                    x=short_trades["entry_timestamp"],
                    y=short_trades["entry_price"],
                    mode="markers",
                    name="Short entries",
                    marker=dict(symbol="triangle-down", size=11, color="tomato"),
                )
            )

        exit_rows = chart_trades.dropna(subset=["exit_timestamp", "exit_price"])
        if not exit_rows.empty:
            fig.add_trace(
                go.Scatter(
                    x=exit_rows["exit_timestamp"],
                    y=exit_rows["exit_price"],
                    mode="markers",
                    name="Exits",
                    marker=dict(symbol="x", size=9, color="black"),
                )
            )

        for row in exit_rows.itertuples(index=False):
            if pd.isna(row.stop_price) or pd.isna(row.target_price):
                continue
            fig.add_shape(
                type="line",
                x0=row.entry_timestamp,
                x1=row.exit_timestamp,
                y0=float(row.stop_price),
                y1=float(row.stop_price),
                line=_STOP_LINE_STYLE,
                opacity=0.7,
            )
            fig.add_shape(
                type="line",
                x0=row.entry_timestamp,
                x1=row.exit_timestamp,
                y0=float(row.target_price),
                y1=float(row.target_price),
                line=_TARGET_LINE_STYLE,
                opacity=0.7,
            )

    fig.update_layout(
        height=680,
        margin=dict(l=10, r=10, t=35, b=10),
        legend=dict(orientation="h"),
        xaxis_title="Date / time",
        yaxis_title="Price",
        xaxis=dict(type="date", rangeslider=dict(visible=False), tickformat="%Y-%m-%d\n%H:%M"),
    )
    return fig
