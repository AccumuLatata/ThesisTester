"""Phase 4 — Signals page.

Detects confluence zones, flags naked levels, and generates candidate
entry signals from the levels computed on the Levels page.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from thesistester.config import INSTRUMENTS
from thesistester.engine import detect_confluence_zones, flag_naked_levels, generate_signals

st.title("🎯 Signals")

# ── Require levels ────────────────────────────────────────────────────────────
if "levels" not in st.session_state:
    st.warning("No levels computed. Please load data on the **Data** page and compute levels on the **Levels** page first.")
    st.stop()

levels_df = st.session_state["levels"]
instrument = st.session_state.get("instrument", "ES")
tick_size = INSTRUMENTS[instrument].tick_size if instrument in INSTRUMENTS else 0.25

# Determine level columns (exclude canonical OHLCV and session columns)
_BASE_COLS = {"timestamp", "open", "high", "low", "close", "volume", "session", "settlement"}
all_level_columns = [c for c in levels_df.columns if c not in _BASE_COLS]

if not all_level_columns:
    st.warning("No level columns found. Please compute levels on the Levels page first.")
    st.stop()

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Confluence settings")

    selected_levels = st.multiselect(
        "Level columns",
        options=all_level_columns,
        default=[c for c in ["ONH", "ONL", "OR_High", "OR_Low", "pdHigh", "pdLow"] if c in all_level_columns] or all_level_columns[:4],
        help="Level columns to include in confluence detection.",
    )

    tolerance_ticks = st.number_input(
        "Tolerance (ticks)",
        min_value=0.0,
        max_value=100.0,
        value=4.0,
        step=0.5,
        help=f"Cluster tolerance in ticks. 1 tick = {tick_size} price units.",
    )

    min_conf = st.slider("Min confluences", min_value=1, max_value=5, value=2)
    max_conf = st.slider("Max confluences", min_value=1, max_value=5, value=5)
    if max_conf < min_conf:
        max_conf = min_conf

    st.header("Signal settings")

    trigger = st.selectbox(
        "Trigger",
        options=["touch", "reject", "break", "reclaim", "confirm_3bar"],
        index=0,
    )

    direction = st.selectbox(
        "Direction",
        options=["long", "short", "both"],
        index=2,
    )

    naked_only = st.toggle("Naked / untested levels only", value=False)
    naked_requirement = "any"
    if naked_only:
        naked_requirement = st.radio(
            "Naked requirement",
            options=["any", "all"],
            horizontal=True,
            help="'any': at least one level in the zone must be naked. 'all': every level must be naked.",
        )

    if trigger == "confirm_3bar":
        st.subheader("confirm_3bar parameters")
        arrival_tol = st.number_input(
            "Arrival tolerance (ticks)",
            min_value=0.0,
            max_value=20.0,
            value=0.0,
            step=0.5,
            help="Ticks around the zone within which bar 1 must trade to qualify as arrival.",
        )
        retrace_entry = st.number_input(
            "Retrace entry (ticks)",
            min_value=0.0,
            max_value=50.0,
            value=4.0,
            step=0.5,
            help="Ticks bar 3 must retrace from bar 3 open before limit entry fills.",
        )
        allow_equal_close = st.toggle(
            "Allow equal close (bar 2 reversal)",
            value=False,
            help="If enabled, bar 2 close >= bar 1 close is sufficient for long (and <= for short).",
        )
        trigger_params: dict = {
            "arrival_tolerance_ticks": arrival_tol,
            "retrace_entry_ticks": retrace_entry,
            "allow_equal_close": allow_equal_close,
        }
    else:
        trigger_params = {}

    generate_btn = st.button("Generate signals", type="primary", use_container_width=True)

# ── Generate ──────────────────────────────────────────────────────────────────
if generate_btn:
    if not selected_levels:
        st.error("Please select at least one level column.")
        st.stop()

    with st.spinner("Detecting confluence zones…"):
        zones = detect_confluence_zones(
            levels_df,
            level_columns=selected_levels,
            tick_size=tick_size,
            tolerance_ticks=tolerance_ticks,
            min_confluences=min_conf,
            max_confluences=max_conf,
        )
        st.session_state["confluence_zones"] = zones

    with st.spinner("Flagging naked levels…"):
        naked_flags = flag_naked_levels(
            levels_df,
            level_columns=selected_levels,
            tick_size=tick_size,
            touch_tolerance_ticks=0,
        )
        st.session_state["naked_flags"] = naked_flags

    with st.spinner("Generating signals…"):
        signals = generate_signals(
            levels_df,
            zones=zones,
            trigger=trigger,
            direction=direction,
            tick_size=tick_size,
            trigger_params=trigger_params,
            naked_only=naked_only,
            naked_flags=naked_flags if naked_only else None,
            naked_requirement=naked_requirement,
        )
        st.session_state["signals"] = signals

# ── Display results ───────────────────────────────────────────────────────────
zones = st.session_state.get("confluence_zones")
signals = st.session_state.get("signals")

if zones is None:
    st.info("Configure settings in the sidebar and click **Generate signals**.")
    st.stop()

col1, col2 = st.columns(2)
col1.metric("Confluence zones detected", len(zones))
col2.metric("Signals generated", len(signals) if signals is not None else 0)

if zones.empty:
    st.warning("No confluence zones found with the current settings. Try increasing tolerance or selecting more levels.")
    st.stop()

# Signal breakdown
if signals is not None and not signals.empty:
    st.subheader("Signal breakdown")
    breakdown_cols = [c for c in ["trigger", "direction", "status"] if c in signals.columns]
    if breakdown_cols:
        st.dataframe(
            signals.groupby(breakdown_cols).size().reset_index(name="count"),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Signal table")
    display_cols = [c for c in ["signal_id", "timestamp", "bar_index", "trigger", "direction",
                                 "zone_low", "zone_high", "zone_mid", "level_count", "level_names",
                                 "entry_reference_price", "entry_model", "status",
                                 "naked_level_count", "notes"] if c in signals.columns]
    st.dataframe(signals[display_cols], use_container_width=True, hide_index=True)
else:
    st.info("No signals generated with the current settings.")

# ── Chart ─────────────────────────────────────────────────────────────────────
st.subheader("Price chart with signals")

fig = go.Figure()

# Close price
fig.add_trace(
    go.Scatter(
        x=levels_df["timestamp"],
        y=levels_df["close"],
        mode="lines",
        name="close",
        line=dict(color="steelblue", width=1),
    )
)

# Selected level lines (first 5 to avoid clutter)
for col in selected_levels[:5]:
    if col in levels_df.columns:
        fig.add_trace(
            go.Scatter(
                x=levels_df["timestamp"],
                y=levels_df[col],
                mode="lines",
                name=col,
                line=dict(width=1, dash="dot"),
                opacity=0.6,
            )
        )

# Signal markers
if signals is not None and not signals.empty:
    long_filled = signals[(signals["direction"] == "long") & (signals["status"].isin(["candidate", "filled"]))]
    short_filled = signals[(signals["direction"] == "short") & (signals["status"].isin(["candidate", "filled"]))]
    long_void = signals[(signals["direction"] == "long") & (signals["status"] == "void")]
    short_void = signals[(signals["direction"] == "short") & (signals["status"] == "void")]

    # Long active signals — triangle-up below the bar
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

    # Short active signals — triangle-down above the bar
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

    # Void signals — crosses, muted
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
st.plotly_chart(fig, use_container_width=True)
