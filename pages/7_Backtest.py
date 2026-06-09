"""Phase 5 — Backtest page.

Converts Phase 4 candidate signals into simulated trades using a single
fixed SL/TP configuration and displays KPIs, equity curve, and trade table.
"""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from thesistester.app_state import bootstrap_active_saved_dataset
from thesistester.analytics import equity_curve, summarize_trades, summarize_trades_by_direction
from thesistester.analytics.metrics import summarize_by_group as summarize_trade_groups
from thesistester.config import INSTRUMENTS, TIMEZONE_OPTIONS
from thesistester.engine.backtest import simulate_trades
from thesistester.timezone_display import ensure_display_timezone, timezone_contract_caption
from thesistester.visualization import (
    buffered_rows_window,
    build_backtest_candlestick_chart,
    clip_by_time_window,
    coerce_timestamp_series,
    recent_rows_window,
    timestamp_bounds,
    trade_time_window,
)

st.title("📊 Backtest")
bootstrap_active_saved_dataset()


def _signal_setup_context(signals, signal_context: dict | None) -> str | None:
    setup_names: list[str] = []
    if "setup_name" in signals.columns:
        setup_names = [
            str(name).strip()
            for name in signals["setup_name"].dropna().unique().tolist()
            if str(name).strip()
        ]

    context = signal_context or {}
    if len(setup_names) > 1:
        return f"Backtesting signals from multiple saved setups: {', '.join(setup_names)}"

    setup_name = setup_names[0] if len(setup_names) == 1 else context.get("setup_name")
    setup_caption = context.get("setup_caption")

    if setup_name and setup_caption:
        return f"Backtesting signals from saved setup: {setup_name} • {setup_caption}"
    if setup_name:
        return f"Backtesting signals from saved setup: {setup_name}"
    if setup_caption:
        return f"Backtesting generated signals • {setup_caption}"
    return None


def _clip_trades_for_chart(trades_df, *, start, end):
    if trades_df is None:
        return None

    out = trades_df.copy(deep=True)
    if out.empty or (start is None and end is None):
        return out
    if "entry_timestamp" not in out.columns or "exit_timestamp" not in out.columns:
        return out

    start_ts = pd.to_datetime(start, errors="coerce") if start is not None else None
    end_ts = pd.to_datetime(end, errors="coerce") if end is not None else None
    if pd.isna(start_ts):
        start_ts = None
    if pd.isna(end_ts):
        end_ts = None
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts
    if start_ts is None and end_ts is None:
        return out

    entry_ts = coerce_timestamp_series(out["entry_timestamp"])
    exit_ts = coerce_timestamp_series(out["exit_timestamp"])
    effective_entry = entry_ts.fillna(exit_ts)
    effective_exit = exit_ts.fillna(entry_ts)
    mask = effective_entry.notna() & effective_exit.notna()
    if start_ts is not None:
        mask &= effective_exit >= start_ts
    if end_ts is not None:
        mask &= effective_entry <= end_ts
    return out.loc[mask].copy(deep=True)

# ── Require signals ───────────────────────────────────────────────────────────
if "signals" not in st.session_state:
    st.warning(
        "No signals found. Please load data on the **Data** page, compute "
        "levels on the **Levels** page, and generate signals on the **Signals** page first."
    )
    st.stop()

signals = st.session_state["signals"]
signal_context = st.session_state.get("signal_context")
if signals is None or signals.empty:
    st.warning("Signal table is empty. Please generate signals on the **Signals** page first.")
    st.stop()

# ── Prefer levels df for full timeline; fall back to data ─────────────────────
if "levels" in st.session_state:
    ohlcv_df = st.session_state["levels"]
elif "data" in st.session_state:
    ohlcv_df = st.session_state["data"]
else:
    st.error("No OHLCV data available. Please load data on the **Data** page.")
    st.stop()

instrument = st.session_state.get("instrument", "ES")
inst = INSTRUMENTS.get(instrument)
tick_size = inst.tick_size if inst else 0.25
point_value = inst.point_value if inst else 50.0
exchange_tz = st.session_state.get("exchange_timezone") or (inst.exchange_tz if inst else "America/New_York")
ensure_display_timezone(st.session_state, exchange_timezone=exchange_tz)

setup_context_caption = _signal_setup_context(signals, signal_context)
if setup_context_caption:
    st.caption(setup_context_caption)

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Backtest settings")
    st.caption(f"Instrument: **{instrument}** · tick={tick_size} · point_value=${point_value:,.0f}")
    st.selectbox(
        "Display/export timezone",
        options=TIMEZONE_OPTIONS,
        key="display_timezone",
        help="Affects user-facing timestamp display/export only. Backtest engine remains in exchange/session time.",
    )

    sl_ticks = st.number_input(
        "Stop loss (ticks)",
        min_value=1.0,
        max_value=500.0,
        value=8.0,
        step=1.0,
        help="Fixed stop-loss distance from entry in ticks.",
    )

    tp_ticks = st.number_input(
        "Take profit (ticks)",
        min_value=1.0,
        max_value=1000.0,
        value=16.0,
        step=1.0,
        help="Fixed take-profit distance from entry in ticks.",
    )

    commission_per_side = st.number_input(
        "Commission per side (currency/contract)",
        min_value=0.0,
        max_value=1_000.0,
        value=0.0,
        step=0.1,
        help="Round-turn commission cost is 2 × this value.",
    )

    slippage_ticks = st.number_input(
        "Slippage (ticks per side)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.25,
        help="Adverse slippage applied at both entry and exit.",
    )

    use_max_bars = st.toggle("Limit holding bars", value=False)
    max_bars: int | None = None
    if use_max_bars:
        max_bars = int(
            st.number_input(
                "Max holding bars",
                min_value=1,
                max_value=500,
                value=20,
                step=1,
            )
        )

    allow_same_bar = st.toggle(
        "Allow same-bar exit",
        value=True,
        help=(
            "If enabled, SL/TP checks begin on the entry bar (recommended for "
            "confirm_3bar filled entries). Uses SL-first pessimistic rule when "
            "both are reachable in the same bar."
        ),
    )

    run_btn = st.button("▶ Run backtest", type="primary", width="stretch")

# ── Run ───────────────────────────────────────────────────────────────────────
if run_btn:
    with st.spinner("Simulating trades…"):
        try:
            trades = simulate_trades(
                df=ohlcv_df,
                signals=signals,
                tick_size=tick_size,
                point_value=point_value,
                stop_loss_ticks=sl_ticks,
                take_profit_ticks=tp_ticks,
                max_holding_bars=max_bars,
                allow_same_bar_exit=allow_same_bar,
                commission_per_side=float(commission_per_side),
                slippage_ticks=float(slippage_ticks),
            )
        except ValueError as e:
            st.error(f"Backtest error: {e}")
            st.stop()

        summary = summarize_trades(trades)
        curve = equity_curve(trades)

        st.session_state["trades"] = trades
        st.session_state["trade_summary"] = summary
        st.session_state["equity_curve"] = curve
        st.session_state["backtest_execution_costs"] = {
            "commission_per_side": float(commission_per_side),
            "slippage_ticks": float(slippage_ticks),
            "metrics_basis": (
                "net-of-cost"
                if (float(commission_per_side) > 0.0 or float(slippage_ticks) > 0.0)
                else "gross==net (zero costs)"
            ),
        }

# ── Display ───────────────────────────────────────────────────────────────────
trades = st.session_state.get("trades")
summary = st.session_state.get("trade_summary")
curve = st.session_state.get("equity_curve")

if trades is None:
    st.info("Configure settings in the sidebar and click **▶ Run backtest**.")
    st.stop()

st.caption(timezone_contract_caption(st.session_state))
costs = st.session_state.get("backtest_execution_costs") or {}
if costs.get("commission_per_side", 0.0) > 0.0 or costs.get("slippage_ticks", 0.0) > 0.0:
    st.caption(
        "Execution costs active — KPIs use net-of-cost pnl_currency and net R (commission/slippage applied)."
    )
else:
    st.caption("Execution costs disabled — KPIs are gross (zero commission/slippage).")

# KPI cards
st.subheader("Performance summary")

def _fmt(v, fmt=".2f", fallback="—"):
    if v is None:
        return fallback
    try:
        v_float = float(v)
        if math.isnan(v_float):
            return fallback
        return format(v_float, fmt)
    except (TypeError, ValueError):
        return fallback


def _fmt_int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _fmt_win_rate(v):
    return _fmt(v, ".1%") if v is not None else "—"


col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Trades", summary.get("trade_count", 0))
col2.metric("Win rate", _fmt_win_rate(summary.get("win_rate")))
col3.metric("Avg R", _fmt(summary.get("avg_r")))
col4.metric("Total R", _fmt(summary.get("total_r")))
col5.metric("Profit factor", _fmt(summary.get("profit_factor")))
col6.metric("Max DD (R)", _fmt(summary.get("max_drawdown_r")))

direction_summary = summarize_trades_by_direction(trades)
st.subheader("Long vs Short KPIs")
long_col, short_col = st.columns(2)

with long_col:
    long_summary = direction_summary.get("long", {})
    st.markdown("**Long trades**")
    st.metric("Trades", _fmt_int(long_summary.get("trade_count", 0)))
    st.metric("Win rate", _fmt_win_rate(long_summary.get("win_rate")))
    st.metric("Average R", _fmt(long_summary.get("avg_r")))
    st.metric("Total R", _fmt(long_summary.get("total_r")))
    st.metric("Profit factor", _fmt(long_summary.get("profit_factor")))

with short_col:
    short_summary = direction_summary.get("short", {})
    st.markdown("**Short trades**")
    st.metric("Trades", _fmt_int(short_summary.get("trade_count", 0)))
    st.metric("Win rate", _fmt_win_rate(short_summary.get("win_rate")))
    st.metric("Average R", _fmt(short_summary.get("avg_r")))
    st.metric("Total R", _fmt(short_summary.get("total_r")))
    st.metric("Profit factor", _fmt(short_summary.get("profit_factor")))

if trades.empty:
    st.info("No trades were generated with the current signals and SL/TP settings.")

has_trades = not trades.empty

if has_trades:
    group_cols = [c for c in ["trigger_variant", "level_source_mode", "direction"] if c in trades.columns]
    if group_cols and "trigger" in trades.columns:
        trades_3c = trades[trades["trigger"] == "3c"]
        grouped = summarize_trade_groups(trades_3c, group_cols)
        if not grouped.empty:
            st.subheader("3c outcome summary by variant/source")
            st.dataframe(grouped, width="stretch", hide_index=True)

# Equity curve
st.subheader("Equity curve (cumulative R)")
if curve is not None and not curve.empty:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=curve["exit_timestamp"],
            y=curve["cum_r"],
            mode="lines+markers",
            name="Cum R",
            line=dict(color="steelblue", width=2),
            marker=dict(size=4),
        )
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=30, b=10),
        yaxis_title="Cumulative R",
        xaxis_title="",
    )
    st.plotly_chart(fig, width="stretch")

# Breakdown tabs
if has_trades:
    st.subheader("Breakdown")
    tab_trigger, tab_dir, tab_reason = st.tabs(["By trigger", "By direction", "By exit reason"])

    with tab_trigger:
        if "trigger" in trades.columns:
            st.dataframe(
                trades.groupby("trigger").agg(
                    count=("trade_id", "count"),
                    win_rate=("r_multiple", lambda x: (x > 0).mean()),
                    avg_r=("r_multiple", "mean"),
                    total_r=("r_multiple", "sum"),
                ).reset_index(),
                width="stretch",
                hide_index=True,
            )

    with tab_dir:
        if "direction" in trades.columns:
            st.dataframe(
                trades.groupby("direction").agg(
                    count=("trade_id", "count"),
                    win_rate=("r_multiple", lambda x: (x > 0).mean()),
                    avg_r=("r_multiple", "mean"),
                    total_r=("r_multiple", "sum"),
                ).reset_index(),
                width="stretch",
                hide_index=True,
            )

    with tab_reason:
        if "exit_reason" in trades.columns:
            st.dataframe(
                trades.groupby("exit_reason").agg(
                    count=("trade_id", "count"),
                    avg_r=("r_multiple", "mean"),
                    total_r=("r_multiple", "sum"),
                ).reset_index(),
                width="stretch",
                hide_index=True,
            )

# Full trade table
if has_trades:
    st.subheader("Trade table")
    display_cols = [c for c in [
        "trade_id", "signal_id", "trigger", "direction",
        "entry_timestamp", "entry_price", "entry_model",
        "exit_timestamp", "exit_price", "exit_reason",
        "stop_price", "target_price",
        "stop_loss_ticks", "take_profit_ticks",
        "gross_pnl_points", "gross_pnl_currency", "commission_cost", "slippage_cost",
        "net_pnl_currency", "pnl_points", "pnl_currency", "r_multiple", "bars_held",
        "zone_low", "zone_high", "level_count", "level_names", "setup_name",
        "mae_points", "mfe_points",
    ] if c in trades.columns]
    st.dataframe(trades[display_cols], width="stretch", hide_index=True)

# Optional execution chart
st.subheader("Backtest execution visualizer")
show_chart = st.toggle("Show candlestick trade visualizer", value=False)
if show_chart:
    chart_range_options = [
        "First trade ± 100 bars",
        "All trades range",
        "Last 10,000 rows",
        "Custom date range",
        "Full dataset",
    ]
    default_chart_range = "First trade ± 100 bars" if has_trades else "Last 10,000 rows"
    chart_range = st.selectbox(
        "Chart range",
        options=chart_range_options,
        index=chart_range_options.index(default_chart_range),
    )
    st.caption(
        "Chart range affects visualization only. Tables, saved artifacts, and backtest metrics remain unchanged."
    )

    show_sessions = st.toggle("Show session context", value=True)
    show_levels = st.toggle("Show levels", value=True)
    show_confluence_zones = st.toggle("Show confluence zones", value=True)
    show_sl_tp = st.toggle("Show SL/TP lines", value=True)
    if ohlcv_df is None or ohlcv_df.empty:
        st.info("No OHLCV data available to render the candlestick chart.")
    else:
        levels_df = st.session_state.get("levels")
        confluence_zones = st.session_state.get("confluence_zones")

        chart_start = None
        chart_end = None
        if chart_range == "First trade ± 100 bars" and has_trades:
            chart_start, chart_end = trade_time_window(trades, ohlcv_df=ohlcv_df, buffer_rows=100)
            if chart_start is None or chart_end is None:
                chart_start, chart_end = recent_rows_window(ohlcv_df, rows=10_000)
        elif chart_range == "All trades range" and has_trades:
            entry_start, entry_end = timestamp_bounds(trades, timestamp_col="entry_timestamp")
            exit_start, exit_end = timestamp_bounds(trades, timestamp_col="exit_timestamp")
            trade_start_candidates = [ts for ts in [entry_start, exit_start] if ts is not None]
            trade_end_candidates = [ts for ts in [entry_end, exit_end] if ts is not None]
            if trade_start_candidates and trade_end_candidates:
                chart_start, chart_end = buffered_rows_window(
                    ohlcv_df,
                    start=min(trade_start_candidates),
                    end=max(trade_end_candidates),
                    buffer_rows=100,
                )
            if chart_start is None or chart_end is None:
                chart_start, chart_end = recent_rows_window(ohlcv_df, rows=10_000)
        elif chart_range == "Last 10,000 rows":
            chart_start, chart_end = recent_rows_window(ohlcv_df, rows=10_000)
        elif chart_range == "Custom date range":
            min_ts, max_ts = timestamp_bounds(ohlcv_df)
            if min_ts is not None and max_ts is not None:
                custom_cols = st.columns(2)
                custom_start_date = custom_cols[0].date_input(
                    "Custom chart start",
                    value=min_ts.date(),
                    min_value=min_ts.date(),
                    max_value=max_ts.date(),
                )
                custom_end_date = custom_cols[1].date_input(
                    "Custom chart end",
                    value=max_ts.date(),
                    min_value=min_ts.date(),
                    max_value=max_ts.date(),
                )
                chart_start = pd.Timestamp(custom_start_date)
                chart_end = pd.Timestamp(custom_end_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)

        chart_ohlcv_df = (
            ohlcv_df.copy(deep=True)
            if chart_range == "Full dataset"
            else clip_by_time_window(ohlcv_df, start=chart_start, end=chart_end)
        )
        chart_trades = (
            trades.copy(deep=True)
            if chart_range == "Full dataset"
            else _clip_trades_for_chart(trades, start=chart_start, end=chart_end)
        )
        chart_levels_df = (
            levels_df.copy(deep=True)
            if chart_range == "Full dataset" and levels_df is not None
            else clip_by_time_window(levels_df, start=chart_start, end=chart_end)
        )
        chart_confluence_zones = (
            confluence_zones.copy(deep=True)
            if chart_range == "Full dataset" and confluence_zones is not None
            else clip_by_time_window(confluence_zones, start=chart_start, end=chart_end)
        )

        chart = build_backtest_candlestick_chart(
            ohlcv_df=chart_ohlcv_df,
            trades=chart_trades,
            levels=chart_levels_df,
            confluence_zones=chart_confluence_zones,
            show_sessions=show_sessions,
            show_levels=show_levels,
            show_confluence_zones=show_confluence_zones,
            show_sl_tp=show_sl_tp,
        )
        st.plotly_chart(chart, width="stretch")
        if show_sessions:
            st.caption("Session context: ETH regions are shaded and RTH starts are marked with dotted vertical lines.")
        st.info(
            "Execution visualization is based on OHLC bars. If SL and TP are both touched within one bar, "
            "engine assumptions determine the recorded outcome; the true intrabar path is unknown without tick data."
        )
