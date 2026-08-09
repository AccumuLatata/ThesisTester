"""Phase 7 — Time-of-Day and Session-Window Performance Breakdown.

Analyses completed trades from Phase 5 by time bucket and session segment.
No trade re-simulation is performed; this page is purely descriptive.
"""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from thesistester.analytics import summarize_trades
from thesistester.analytics.confluence_attribution import (
    append_confluence_time_analysis_group_options,
    attach_level_count_bucket,
    confluence_combo_grouping_available,
    time_analysis_combo_group_caption,
)
from thesistester.analytics.entry_window import (
    ADMIT_ARMED_STATUS_BADGE,
    FOCUSABLE_GROUP_COLS,
    FOCUS_EQUITY_CAVEAT,
    FOCUS_HONESTY_BANNER,
    FOCUS_STATUS_BADGE,
    PROMOTE_ARMED_BANNER,
    apply_promote_to_session_state,
    clear_armed_entry_window,
    entry_focus_bucket_values,
    entry_window_from_bucket,
    filter_trades_by_entry_window,
    format_entry_window_label,
    promote_entry_window,
    summarize_focused_trades,
)
from thesistester.analytics.time_analysis import (
    add_time_buckets,
    pivot_time_metric,
    summarize_by_group,
)
from thesistester.config import INSTRUMENTS, TIMEZONE_OPTIONS
from thesistester.timezone_display import ensure_display_timezone

st.title("🕐 Time Analysis")
st.caption(
    "Descriptive time-of-day and session-window breakdown of completed trades. "
    "No trade re-simulation is performed."
)

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
        options=[c for c in ["entry_timestamp", "exit_timestamp"] if c in trades_raw.columns],
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

bucket_tz = exchange_tz if bucket_basis == "Exchange/session timezone" else display_tz

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

# PR 5a: attach combo/count columns when level_names exist; offer as opt-in
# group dims only when attribution available=True (nonempty analyzable combos).
_combo_group_available = False
if "level_names" in trades.columns:
    trades = attach_level_count_bucket(trades)
    _combo_group_available = confluence_combo_grouping_available(trades)

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
primary_options = append_confluence_time_analysis_group_options(
    primary_options,
    available=_combo_group_available,
    columns=trades.columns,
)
secondary_options = ["None"] + append_confluence_time_analysis_group_options(
    [c for c in _SECONDARY_OPTIONS[1:] if c in trades.columns],
    available=_combo_group_available,
    columns=trades.columns,
)

with st.sidebar:
    primary_group = st.selectbox(
        "Primary grouping",
        options=primary_options,
        index=0 if primary_options else None,
        help=(
            "Primary dimension for grouping trades. "
            "exact_combo_key / level_count_bucket appear only when confluence "
            "combo attribution is available; default remains a time bucket."
        ),
    )

    secondary_group_raw = st.selectbox(
        "Secondary grouping (optional)",
        options=secondary_options,
        index=0,
        help="Add a second dimension for a cross-tab breakdown (optional).",
    )
    secondary_group: str | None = None if secondary_group_raw == "None" else secondary_group_raw

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

_combo_caption = time_analysis_combo_group_caption(trades, group_cols)
if _combo_caption:
    st.caption(_combo_caption)

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
                lambda v: (
                    f"{v:.1%}"
                    if v is not None and not (isinstance(v, float) and __import__("math").isnan(v))
                    else "—"
                )
            )

    for r_col in (
        "avg_r",
        "median_r",
        "total_r",
        "profit_factor",
        "avg_win_r",
        "avg_loss_r",
        "max_drawdown_r",
        "best_trade_r",
        "worst_trade_r",
    ):
        if r_col in display_df.columns:
            display_df[r_col] = display_df[r_col].map(
                lambda v: (
                    f"{v:.3f}"
                    if v is not None and not (isinstance(v, float) and __import__("math").isnan(v))
                    else "—"
                )
            )

    st.dataframe(display_df, width="stretch", hide_index=True)

st.divider()

# ── Focus summary (SW1 — post-hoc subset; no re-sim) ──────────────────────────
_FOCUSABLE_COLS = FOCUSABLE_GROUP_COLS
_FOCUS_TIMESTAMP_COL = "entry_timestamp"
st.subheader("Focus summary (post-hoc)")
st.caption(
    "Recompute the full Performance Summary on one time bucket without re-running "
    "the backtest. This is exploratory only — not a live trading schedule."
)

if primary_group in _FOCUSABLE_COLS:
    # C2: Focus/Promote options always come from entry-time buckets — never from
    # an exit_timestamp chart partition (columns stay named entry_* either way).
    focus_values = entry_focus_bucket_values(
        trades_raw,
        primary_group,
        exchange_tz=exchange_tz,
        bucket_tz=bucket_tz,
    )
    active_focus = st.session_state.get("focus_entry_window") or {}
    active_label = None
    if active_focus.get("enabled"):
        if active_focus.get("mode") == "rth_segments":
            segs = active_focus.get("rth_segments") or []
            active_label = str(segs[0]) if len(segs) == 1 else None
        elif active_focus.get("mode") == "clock_range":
            active_label = str(active_focus.get("start_time") or "")
            # Prefer matching the selectbox value (hour/30m label).
            for candidate in focus_values:
                if candidate == active_label or candidate.startswith(active_label):
                    active_label = candidate
                    break

    if timestamp_basis != _FOCUS_TIMESTAMP_COL:
        st.caption(
            "Focus / Promote buckets and membership use **entry** timestamps (C2), "
            f"not the chart basis `{timestamp_basis}`. "
            "Exit-grouped table rows are not Focus options."
        )

    if not focus_values:
        st.info("No entry-time buckets available to Focus for this primary grouping.")
        selected_focus_value = None
        apply_focus = False
        if st.button("Clear Focus", key="time_analysis_clear_focus_empty"):
            for key in (
                "focus_entry_window",
                "focused_trades",
                "focused_trade_summary",
                "focused_equity_curve",
                "focus_provenance",
                "focused_direction_summary",
            ):
                st.session_state.pop(key, None)
            st.rerun()
    else:
        focus_col, btn_col, clear_col = st.columns([3, 1, 1])
        with focus_col:
            selected_focus_value = st.selectbox(
                f"Bucket ({primary_group}, entry time)",
                options=focus_values,
                index=(focus_values.index(active_label) if active_label in focus_values else 0),
                key="time_analysis_focus_bucket_value",
                help=(
                    "Select an **entry-time** bucket to Focus (post-hoc) or Promote "
                    "to Admit (arms Backtest entry_window; does not auto-run)."
                ),
            )
        with btn_col:
            st.write("")
            st.write("")
            apply_focus = st.button(
                "Focus summary", type="primary", key="time_analysis_apply_focus"
            )
        with clear_col:
            st.write("")
            st.write("")
            clear_focus = st.button("Clear Focus", key="time_analysis_clear_focus")

        if clear_focus:
            for key in (
                "focus_entry_window",
                "focused_trades",
                "focused_trade_summary",
                "focused_equity_curve",
                "focus_provenance",
                "focused_direction_summary",
            ):
                st.session_state.pop(key, None)
            st.rerun()

    if apply_focus and selected_focus_value is not None:
        try:
            window = entry_window_from_bucket(
                primary_group,
                selected_focus_value,
                exchange_tz=exchange_tz,
                bucket_tz=bucket_tz,
            )
            focused = summarize_focused_trades(
                trades_raw,
                window,
                exchange_tz=exchange_tz,
                timestamp_col=_FOCUS_TIMESTAMP_COL,
                bucket_tz=bucket_tz,
                min_trades=min_trades_warn,
            )
            st.session_state["focus_entry_window"] = focused["focus_entry_window"]
            st.session_state["focused_trades"] = focused["focused_trades"]
            st.session_state["focused_trade_summary"] = focused["focused_trade_summary"]
            st.session_state["focused_equity_curve"] = focused["focused_equity_curve"]
            st.session_state["focus_provenance"] = focused["focus_provenance"]
            st.session_state["focused_direction_summary"] = focused.get("focused_direction_summary")
            st.rerun()
        except ValueError as exc:
            st.error(f"Focus failed: {exc}")
else:
    st.info(
        "Focus is available when primary grouping is "
        "`entry_rth_segment`, `entry_hour_bucket`, or `entry_30min_bucket`."
    )
    selected_focus_value = None

_focus_summary = st.session_state.get("focused_trade_summary")
_focus_prov = st.session_state.get("focus_provenance") or {}
_focus_window = st.session_state.get("focus_entry_window")
_has_focus = bool(
    isinstance(_focus_summary, dict) and _focus_window and _focus_window.get("enabled")
)
if _has_focus:
    st.caption(f"**{FOCUS_STATUS_BADGE}**")
    st.warning(FOCUS_HONESTY_BANNER)
    st.info(FOCUS_EQUITY_CAVEAT)
    st.caption(
        f"Focused window: **{format_entry_window_label(_focus_window)}** · "
        f"{_focus_prov.get('trade_count_after', 0)} / "
        f"{_focus_prov.get('trade_count_before', 0)} trades"
    )
    if _focus_prov.get("sample_warning"):
        st.warning(
            f"Sample-size warning: focused trade_count "
            f"({_focus_prov.get('trade_count_after', 0)}) is below the "
            f"{_focus_prov.get('min_trades', min_trades_warn)} threshold. "
            "Treat as a hypothesis, not an edge."
        )

    f1, f2, f3, f4, f5, f6 = st.columns(6)
    f1.metric("Trades", _focus_summary.get("trade_count", 0))
    f2.metric(
        "Win rate",
        (
            _fmt(_focus_summary.get("win_rate"), ".1%")
            if _focus_summary.get("win_rate") is not None
            else "—"
        ),
    )
    f3.metric("Avg R", _fmt(_focus_summary.get("avg_r")))
    f4.metric("Total R", _fmt(_focus_summary.get("total_r")))
    f5.metric("Profit factor", _fmt(_focus_summary.get("profit_factor")))
    f6.metric("Max DD (R)", _fmt(_focus_summary.get("max_drawdown_r")))

    _focus_curve = st.session_state.get("focused_equity_curve")
    if _focus_curve is not None and not getattr(_focus_curve, "empty", True):
        st.caption("Focused equity curve (subset replay)")
        st.line_chart(_focus_curve.set_index("exit_timestamp")["cum_r"])

# ── Promote → Admit (SW4 — arms entry_window; no auto-run) ────────────────────
st.subheader("Promote to Admit")
st.caption(
    "Arm the selected/Focused bucket as a Backtest **entry_window** constraint. "
    "Does **not** re-simulate — open Backtest and Run to apply Admit."
)
_armed = bool(st.session_state.get("entry_window_armed"))
_armed_window = st.session_state.get("entry_window") or {}
_armed_prov = st.session_state.get("entry_window_promote_provenance") or {}
if _armed and isinstance(_armed_window, dict) and _armed_window.get("enabled"):
    st.caption(f"**{ADMIT_ARMED_STATUS_BADGE}**")
    st.warning(PROMOTE_ARMED_BANNER)
    st.caption(
        f"Armed window: **{format_entry_window_label(_armed_window)}**"
        + (
            f" · sample n={_armed_prov.get('trade_count_after')}"
            if _armed_prov.get("trade_count_after") is not None
            else ""
        )
    )

_can_promote = primary_group in _FOCUSABLE_COLS and selected_focus_value is not None
if _can_promote:
    # Prefer active Focus window; else map the selected bucket (C1/C5).
    # C2: Admit classifies by entry-bar time — Promote sample counts / thin-sample
    # gate always use entry_timestamp, even when Time Analysis charts use exit.
    # (Exit-basis caption is shared with Focus above.)
    _PROMOTE_TIMESTAMP_COL = _FOCUS_TIMESTAMP_COL
    if _has_focus and isinstance(_focus_window, dict) and _focus_window.get("enabled"):
        _promote_source_window = _focus_window
        _promote_source = "focus"
    else:
        try:
            _promote_source_window = entry_window_from_bucket(
                primary_group,
                selected_focus_value,
                exchange_tz=exchange_tz,
                bucket_tz=bucket_tz,
            )
            _promote_source = "bucket"
        except ValueError as exc:
            _promote_source_window = None
            st.error(f"Promote source unavailable: {exc}")

    if _promote_source_window is not None:
        _promote_filtered = filter_trades_by_entry_window(
            trades_raw,
            _promote_source_window,
            exchange_tz=exchange_tz,
            timestamp_col=_PROMOTE_TIMESTAMP_COL,
            bucket_tz=bucket_tz,
        )
        _promote_count_after = int(len(_promote_filtered))
        _promote_count_before = int(len(trades_raw))
        _thin = _promote_count_after < int(min_trades_warn)
        if _thin:
            st.warning(
                f"Thin sample: {_promote_count_after} trades "
                f"(threshold {min_trades_warn}). Confirm before Promoting."
            )
        thin_confirm = st.checkbox(
            "Promote anyway — I understand this sample is thin",
            value=False,
            key="time_analysis_promote_thin_confirm",
            disabled=not _thin,
        )
        promote_col, clear_armed_col = st.columns(2)
        with promote_col:
            promote_btn = st.button(
                "Promote to Admit",
                type="primary",
                key="time_analysis_promote_admit",
                disabled=_thin and not thin_confirm,
                help="Arms Backtest entry_window widgets. Does not auto-run simulation.",
            )
        with clear_armed_col:
            clear_armed_btn = st.button(
                "Clear armed Admit",
                key="time_analysis_clear_armed_admit",
                disabled=not _armed,
            )

        if clear_armed_btn:
            clear_armed_entry_window(st.session_state)
            st.rerun()

        if promote_btn:
            try:
                payload = promote_entry_window(
                    _promote_source_window,
                    exchange_tz=exchange_tz,
                    trade_count_after=_promote_count_after,
                    trade_count_before=_promote_count_before,
                    min_trades=min_trades_warn,
                    source=_promote_source,
                    thin_sample_confirmed=bool(thin_confirm) if _thin else False,
                )
                apply_promote_to_session_state(st.session_state, payload)
                st.rerun()
            except ValueError as exc:
                st.error(f"Promote failed: {exc}")
else:
    st.info(
        "Promote is available when primary grouping is "
        "`entry_rth_segment`, `entry_hour_bucket`, or `entry_30min_bucket`."
    )

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
        chart_data = (
            grouped[[primary_group, secondary_group, chart_metric, "trade_count"]]
            .copy()
            .dropna(subset=[chart_metric])
        )
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
        "entry_date",
        "entry_time",
        "entry_hour",
        "entry_minute",
        "entry_hour_bucket",
        "entry_30min_bucket",
        "entry_rth_segment",
    ]
    display_trade_cols = [
        c
        for c in (
            ["trade_id"]
            + bucket_cols
            + [
                "trigger",
                "direction",
                "exit_reason",
                "r_multiple",
                "entry_timestamp",
                "exit_timestamp",
            ]
        )
        if c in trades.columns
    ]
    st.dataframe(trades[display_trade_cols], width="stretch", hide_index=True)
