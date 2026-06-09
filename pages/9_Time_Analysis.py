"""Phase 7 — Time-of-Day and Session-Window Performance Breakdown.

Analyses completed trades from Phase 5 by time bucket and session segment.
No trade re-simulation is performed; this page is purely descriptive.
"""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from thesistester.analytics import summarize_trades
from thesistester.analytics.time_analysis import (
    add_time_buckets,
    pivot_time_metric,
    summarize_by_group,
)
from thesistester.config import INSTRUMENTS, TIMEZONE_OPTIONS
from thesistester.timezone_display import ensure_display_timezone

st.title("🕐 Time Analysis")

# ── Require trades ────────────────────────────────────────────────────────────
trades_raw = st.session_state.get("trades")
if trades_raw is None or trades_raw.empty:
    st.warning("No trades found. Please run a backtest first.")
    st.stop()

# ── Instrument / timezone ─────────────────────────────────────────────────────
instrument = st.session_state.get("instrument", "ES")
inst = INSTRUMENTS.get(instrument)
exchange_tz = inst.exchange_tz if inst else "America/New_York"
ensure_display_timezone(st.session_state, exchange_timezone=exchange_tz)
display_tz = st.session_state.get("display_timezone")

# ── KPI summary (full trade set) ──────────────────────────────────────────────
st.subheader("Overall performance summary")

summary = st.session_state.get("trade_summary") or summarize_trades(trades_raw)


def _fmt(v, fmt: str = ".2f", fallback: str = "—") -> str:
    if v is None:
        return fallback
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return fallback


col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Trades", summary.get("trade_count", 0))
col2.metric(
    "Win rate",
    _fmt(summary.get("win_rate"), ".1%") if summary.get("win_rate") is not None else "—",
)
col3.metric("Avg R", _fmt(summary.get("avg_r")))
col4.metric("Total R", _fmt(summary.get("total_r")))
col5.metric("Profit factor", _fmt(summary.get("profit_factor")))
col6.metric("Max DD (R)", _fmt(summary.get("max_drawdown_r")))

st.divider()

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Time Analysis settings")
    st.caption(f"Instrument: **{instrument}** · exchange/session tz: {exchange_tz}")
    st.selectbox(
        "Display/export timezone",
        options=TIMEZONE_OPTIONS,
        key="display_timezone",
        help="Affects display/export only. Time bucket calculations remain unchanged unless you explicitly change the bucket timezone below.",
    )

    bucket_basis = st.selectbox(
        "Time bucket timezone",
        options=[
            "Exchange/session timezone",
            "Display/export timezone",
        ],
        index=0,
        help="Controls only hourly/30-minute Time Analysis buckets and charts. Futures session logic remains exchange-time by default.",
    )

    timestamp_basis = st.selectbox(
        "Timestamp basis",
        options=[
            c for c in ["entry_timestamp", "exit_timestamp"]
            if c in trades_raw.columns
        ],
        index=0,
        help="Which timestamp to use for time bucketing.",
    )

    min_trades_warn = int(
        st.number_input(
            "Minimum trades warning threshold",
            min_value=1,
            max_value=1000,
            value=10,
            step=1,
            help="Groups with fewer trades display a sample-size warning.",
        )
    )

bucket_tz = (
    exchange_tz
    if bucket_basis == "Exchange/session timezone"
    else display_tz
)

st.caption(f"Exchange/session timezone: {exchange_tz}")
st.caption(f"Display/export timezone: {display_tz}")
st.caption(f"Time bucket timezone: {bucket_tz}")
if bucket_tz != exchange_tz:
    st.info(
        f"Hourly and 30-minute buckets are grouped in {bucket_tz}. "
        "RTH segment remains exchange/session-time based."
    )

# ── Add time buckets ──────────────────────────────────────────────────────────
trades = add_time_buckets(
    trades_raw,
    timestamp_col=timestamp_basis,
    exchange_tz=exchange_tz,
    bucket_tz=bucket_tz,
    session_tz=exchange_tz,
)
st.session_state["time_bucketed_trades"] = trades

# ── Determine available grouping columns ─────────────────────────────────────
_PRIMARY_OPTIONS = [
    "entry_rth_segment",
    "entry_hour_bucket",
    "entry_30min_bucket",
    "trigger",
    "direction",
    "setup_name",
    "exit_reason",
]
_SECONDARY_OPTIONS = [
    "None",
    "trigger",
    "direction",
    "setup_name",
    "entry_rth_segment",
    "entry_hour_bucket",
    "exit_reason",
]
_METRIC_OPTIONS = [
    "trade_count",
    "win_rate",
    "avg_r",
    "median_r",
    "total_r",
    "profit_factor",
    "max_drawdown_r",
    "best_trade_r",
    "worst_trade_r",
]

primary_options = [c for c in _PRIMARY_OPTIONS if c in trades.columns]
secondary_options = ["None"] + [
    c for c in _SECONDARY_OPTIONS[1:] if c in trades.columns
]

with st.sidebar:
    primary_group = st.selectbox(
        "Primary grouping",
        options=primary_options,
        index=0 if primary_options else None,
        help="Primary dimension for grouping trades.",
    )

    secondary_group_raw = st.selectbox(
        "Secondary grouping (optional)",
        options=secondary_options,
        index=0,
        help="Add a second dimension for a cross-tab breakdown (optional).",
    )
    secondary_group: str | None = (
        None if secondary_group_raw == "None" else secondary_group_raw
    )

    chart_metric = st.selectbox(
        "Metric for chart / heatmap",
        options=_METRIC_OPTIONS,
        index=2,  # avg_r
        help="Metric displayed in bar chart and heatmap.",
    )

if not primary_options:
    st.error("No suitable grouping columns found in the trade data.")
    st.stop()

if primary_group is None:
    st.info("Select a primary grouping from the sidebar.")
    st.stop()

# ── Compute grouped summaries ─────────────────────────────────────────────────
group_cols = (
    [primary_group, secondary_group]
    if secondary_group and secondary_group != primary_group
    else [primary_group]
)

grouped = summarize_by_group(trades, group_cols=group_cols, min_trades=min_trades_warn)
st.session_state["time_grouped_summary"] = grouped

st.subheader("Grouped performance table")

if grouped.empty:
    st.info("No grouped results to display.")
else:
    # Sample warning banner
    if grouped["sample_warning"].any():
        warn_count = grouped["sample_warning"].sum()
        st.warning(
            f"⚠️ Some groups have fewer than {min_trades_warn} trades "
            f"({warn_count} group(s) flagged). Results may not be meaningful."
        )

    # Friendly format for display
    display_df = grouped.copy()

    for pct_col in ("win_rate", "loss_rate"):
        if pct_col in display_df.columns:
            display_df[pct_col] = display_df[pct_col].map(
                lambda v: f"{v:.1%}" if v is not None and not (isinstance(v, float) and __import__('math').isnan(v)) else "—"
            )

    for r_col in (
        "avg_r", "median_r", "total_r", "profit_factor",
        "avg_win_r", "avg_loss_r", "max_drawdown_r",
        "best_trade_r", "worst_trade_r",
    ):
        if r_col in display_df.columns:
            display_df[r_col] = display_df[r_col].map(
                lambda v: f"{v:.3f}" if v is not None and not (isinstance(v, float) and __import__('math').isnan(v)) else "—"
            )

    st.dataframe(display_df, width="stretch", hide_index=True)

st.divider()

# ── Chart section ─────────────────────────────────────────────────────────────
st.subheader(f"Chart: {chart_metric} by {primary_group}")

if grouped.empty or chart_metric not in grouped.columns:
    st.info("No data available for the selected grouping and metric.")
else:
    if secondary_group is None:
        # Simple bar chart
        chart_data = grouped[[primary_group, chart_metric, "trade_count"]].copy()
        chart_data = chart_data.dropna(subset=[chart_metric])
        if chart_data.empty:
            st.info("No non-null values to plot.")
        else:
            fig = px.bar(
                chart_data,
                x=primary_group,
                y=chart_metric,
                text="trade_count",
                color=chart_metric,
                color_continuous_scale="RdYlGn",
                labels={chart_metric: chart_metric, primary_group: primary_group},
                title=f"{chart_metric} by {primary_group}",
            )
            fig.update_traces(texttemplate="n=%{text}", textposition="outside")
            fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
            fig.update_layout(
                height=380,
                margin=dict(l=10, r=10, t=50, b=10),
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig, width="stretch")
    else:
        # Grouped bar chart
        chart_data = grouped[
            [primary_group, secondary_group, chart_metric, "trade_count"]
        ].copy().dropna(subset=[chart_metric])
        if chart_data.empty:
            st.info("No non-null values to plot.")
        else:
            fig = px.bar(
                chart_data,
                x=primary_group,
                y=chart_metric,
                color=secondary_group,
                barmode="group",
                labels={chart_metric: chart_metric, primary_group: primary_group},
                title=f"{chart_metric} by {primary_group} / {secondary_group}",
            )
            fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
            fig.update_layout(
                height=380,
                margin=dict(l=10, r=10, t=50, b=10),
            )
            st.plotly_chart(fig, width="stretch")

# ── Heatmap section (only when secondary grouping is active) ──────────────────
if secondary_group is not None and not grouped.empty:
    st.subheader(f"Heatmap: {chart_metric}")

    pivot = pivot_time_metric(
        grouped,
        index_col=primary_group,
        metric=chart_metric,
        column_col=secondary_group,
    )

    if pivot.empty:
        st.info("Pivot produced no data for the selected grouping.")
    else:
        fig_heat = go.Figure(
            go.Heatmap(
                z=pivot.values.tolist(),
                x=[str(c) for c in pivot.columns.tolist()],
                y=[str(r) for r in pivot.index.tolist()],
                colorscale="RdYlGn",
                colorbar=dict(title=chart_metric),
                hoverongaps=False,
            )
        )
        fig_heat.update_layout(
            xaxis_title=secondary_group,
            yaxis_title=primary_group,
            height=420,
            margin=dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig_heat, width="stretch")

# ── Trade count by time bucket ────────────────────────────────────────────────
st.divider()
st.subheader("Trade count distribution")

if primary_group in trades.columns:
    counts = (
        trades.groupby(primary_group, observed=True)
        .size()
        .reset_index(name="trade_count")
        .sort_values(primary_group)
    )
    fig_counts = px.bar(
        counts,
        x=primary_group,
        y="trade_count",
        labels={"trade_count": "Trades", primary_group: primary_group},
        title=f"Trade count by {primary_group}",
        text="trade_count",
        color="trade_count",
        color_continuous_scale="Blues",
    )
    fig_counts.update_traces(textposition="outside")
    fig_counts.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=50, b=10),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig_counts, width="stretch")

# ── Detailed raw trade view ───────────────────────────────────────────────────
with st.expander("Raw trades with time buckets"):
    bucket_cols = [
        "entry_date", "entry_time", "entry_hour", "entry_minute",
        "entry_hour_bucket", "entry_30min_bucket", "entry_rth_segment",
    ]
    display_trade_cols = [
        c for c in (
            ["trade_id"] + bucket_cols + [
                "trigger", "direction", "exit_reason",
                "r_multiple", "entry_timestamp", "exit_timestamp",
            ]
        )
        if c in trades.columns
    ]
    st.dataframe(trades[display_trade_cols], width="stretch", hide_index=True)
