"""Phase 6 — SL/TP Grid Search page.

Sweeps stop-loss × take-profit combinations over the Phase 4 candidate
signals and displays expectancy heatmaps plus a full results table.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from thesistester.app_state import bootstrap_active_saved_dataset
from thesistester.analytics import best_grid_result, run_sl_tp_grid
from thesistester.config import INSTRUMENTS

st.title("🔲 SL/TP Grid Search")
bootstrap_active_saved_dataset()

# ── Require signals ──────────────────────────────────────────────────────────
if "signals" not in st.session_state:
    st.warning(
        "No signals found. Please load data on the **Data** page, compute "
        "levels on the **Levels** page, and generate signals on the **Signals** page first."
    )
    st.stop()

signals = st.session_state["signals"]
if signals is None or signals.empty:
    st.warning("Signal table is empty. Please generate signals on the **Signals** page first.")
    st.stop()

# ── OHLCV source ─────────────────────────────────────────────────────────────
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

# ── Sidebar controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Grid search settings")
    st.caption(
        f"Instrument: **{instrument}** · tick={tick_size} · "
        f"point_value=${point_value:,.0f}"
    )

    st.subheader("Stop-loss range (ticks)")
    sl_start = st.number_input("SL start", min_value=1.0, max_value=500.0, value=4.0, step=1.0)
    sl_stop = st.number_input("SL stop", min_value=1.0, max_value=500.0, value=20.0, step=1.0)
    sl_step = st.number_input("SL step", min_value=1.0, max_value=100.0, value=4.0, step=1.0)

    st.subheader("Take-profit range (ticks)")
    tp_start = st.number_input("TP start", min_value=1.0, max_value=1000.0, value=8.0, step=1.0)
    tp_stop = st.number_input("TP stop", min_value=1.0, max_value=1000.0, value=40.0, step=1.0)
    tp_step = st.number_input("TP step", min_value=1.0, max_value=200.0, value=8.0, step=1.0)

    st.subheader("Options")
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
            "SL/TP checks begin on the entry bar. "
            "Uses SL-first pessimistic rule when both are reachable in the same bar."
        ),
    )

    ranking_metric = st.selectbox(
        "Ranking metric",
        options=["expectancy_r", "total_r", "profit_factor", "win_rate"],
        index=0,
        help="Metric used to find the best SL/TP pair.",
    )

    min_trades = int(
        st.number_input(
            "Min trade count",
            min_value=1,
            max_value=1000,
            value=1,
            step=1,
            help="Grid cells with fewer trades are ignored when ranking.",
        )
    )

    st.subheader("Advanced directional ranking")
    enable_directional = st.toggle(
        "Enable directional ranking",
        value=False,
        help=(
            "Rank by long/short or balanced directional metrics instead of "
            "aggregate metrics.  Requires a minimum number of trades on each side."
        ),
    )

    directional_metric = "expectancy_r"
    min_long_trades = 1
    min_short_trades = 1

    if enable_directional:
        directional_metric = st.selectbox(
            "Directional ranking metric",
            options=[
                "expectancy_r",
                "total_r",
                "profit_factor",
                "win_rate",
                "long_expectancy_r",
                "short_expectancy_r",
                "long_profit_factor",
                "short_profit_factor",
                "min_direction_expectancy_r",
                "min_direction_profit_factor",
            ],
            index=8,  # default: min_direction_expectancy_r
            help=(
                "Directional metrics reward the weaker side being positive.  "
                "min_direction_expectancy_r is more conservative than Profit Factor."
            ),
        )
        min_long_trades = int(
            st.number_input(
                "Min long trades",
                min_value=1,
                max_value=1000,
                value=1,
                step=1,
                help=(
                    "Grid cells with fewer long trades are excluded.  "
                    "For real research, consider values ≥ 10–30."
                ),
            )
        )
        min_short_trades = int(
            st.number_input(
                "Min short trades",
                min_value=1,
                max_value=1000,
                value=1,
                step=1,
                help=(
                    "Grid cells with fewer short trades are excluded.  "
                    "For real research, consider values ≥ 10–30."
                ),
            )
        )

    run_btn = st.button("▶ Run grid search", type="primary", use_container_width=True)

# ── Build SL / TP value lists ────────────────────────────────────────────────
def _range_list(start: float, stop: float, step: float) -> list[float]:
    """Inclusive arange as a Python list, rounded to avoid float drift."""
    values = np.arange(start, stop + step * 0.5, step).tolist()
    return [round(v, 10) for v in values if v > 0]


# ── Run ───────────────────────────────────────────────────────────────────────
if run_btn:
    sl_list = _range_list(sl_start, sl_stop, sl_step)
    tp_list = _range_list(tp_start, tp_stop, tp_step)

    if not sl_list:
        st.error("Stop-loss range produced no valid values. Check start/stop/step.")
        st.stop()
    if not tp_list:
        st.error("Take-profit range produced no valid values. Check start/stop/step.")
        st.stop()

    n_combos = len(sl_list) * len(tp_list)
    with st.spinner(f"Running {n_combos} combinations…"):
        try:
            grid = run_sl_tp_grid(
                df=ohlcv_df,
                signals=signals,
                tick_size=tick_size,
                point_value=point_value,
                stop_loss_ticks_values=sl_list,
                take_profit_ticks_values=tp_list,
                max_holding_bars=max_bars,
                allow_same_bar_exit=allow_same_bar,
            )
        except ValueError as e:
            st.error(f"Grid search error: {e}")
            st.stop()

    best = best_grid_result(grid, metric=ranking_metric, min_trades=min_trades)

    # Directional ranking: pre-filter by side-specific trade counts then rank.
    if enable_directional:
        dir_filtered = grid.copy()
        if "long_trade_count" in dir_filtered.columns:
            dir_filtered = dir_filtered[
                dir_filtered["long_trade_count"] >= min_long_trades
            ]
        if "short_trade_count" in dir_filtered.columns:
            dir_filtered = dir_filtered[
                dir_filtered["short_trade_count"] >= min_short_trades
            ]
        best = best_grid_result(dir_filtered, metric=directional_metric, min_trades=min_trades)

    st.session_state["grid_results"] = grid
    st.session_state["best_grid_result"] = best

# ── Display ───────────────────────────────────────────────────────────────────
grid = st.session_state.get("grid_results")
best = st.session_state.get("best_grid_result")

if grid is None:
    st.info("Configure settings in the sidebar and click **▶ Run grid search**.")
    st.stop()


def _fmt(v, fmt=".2f", fallback="—"):
    if v is None:
        return fallback
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return fallback


# Resolve the metric shown in the best-cell header
active_metric = directional_metric if enable_directional else ranking_metric

# Summary header
n_combos = len(grid)
st.write(f"**{n_combos}** combinations tested.")

if best is not None:
    st.subheader("Best SL/TP pair")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("SL (ticks)", _fmt(best.get("stop_loss_ticks"), ".4g"))
    c2.metric("TP (ticks)", _fmt(best.get("take_profit_ticks"), ".4g"))
    c3.metric(f"Best {active_metric}", _fmt(best.get(active_metric)))
    c4.metric("Trades", int(best.get("trade_count", 0)))
    c5.metric("Win rate", _fmt(best.get("win_rate"), ".1%") if best.get("win_rate") is not None else "—")
    c6.metric("Max DD (R)", _fmt(best.get("max_drawdown_r")))

    col_pf, col_tot = st.columns(2)
    col_pf.metric("Profit factor", _fmt(best.get("profit_factor")))
    col_tot.metric("Total R", _fmt(best.get("total_r")))

    # Directional breakdown for the best cell (shown when columns exist)
    if "long_trade_count" in grid.columns:
        st.subheader("Best cell directional breakdown")
        long_col, short_col = st.columns(2)
        with long_col:
            st.markdown("**Long**")
            st.metric("Trades", int(best.get("long_trade_count", 0)))
            st.metric("Win rate", _fmt(best.get("long_win_rate"), ".1%") if best.get("long_win_rate") is not None else "—")
            st.metric("Avg R", _fmt(best.get("long_avg_r")))
            st.metric("Total R", _fmt(best.get("long_total_r")))
            st.metric("Profit factor", _fmt(best.get("long_profit_factor")))
        with short_col:
            st.markdown("**Short**")
            st.metric("Trades", int(best.get("short_trade_count", 0)))
            st.metric("Win rate", _fmt(best.get("short_win_rate"), ".1%") if best.get("short_win_rate") is not None else "—")
            st.metric("Avg R", _fmt(best.get("short_avg_r")))
            st.metric("Total R", _fmt(best.get("short_total_r")))
            st.metric("Profit factor", _fmt(best.get("short_profit_factor")))
else:
    if enable_directional:
        st.warning(
            "No grid cell meets the directional trade-count requirements. "
            "Reduce min long/short trades or widen the SL/TP range."
        )
    else:
        st.info(
            f"No grid cell meets the minimum trade count of {min_trades}. "
            "Try reducing the min trade count or widening the SL/TP ranges."
        )


# ---------------------------------------------------------------------------
# Heatmap helper
# ---------------------------------------------------------------------------

def _heatmap(grid: pd.DataFrame, metric: str, title: str) -> go.Figure:
    pivot = grid.pivot(
        index="stop_loss_ticks",
        columns="take_profit_ticks",
        values=metric,
    )
    pivot = pivot.sort_index().sort_index(axis=1)

    fig = go.Figure(
        go.Heatmap(
            z=pivot.values.tolist(),
            x=[str(c) for c in pivot.columns.tolist()],
            y=[str(r) for r in pivot.index.tolist()],
            colorscale="RdYlGn",
            colorbar=dict(title=metric),
            hoverongaps=False,
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Take-profit (ticks)",
        yaxis_title="Stop-loss (ticks)",
        height=420,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig


# Heatmaps — single metric selector
st.subheader("Heatmaps")

_heatmap_options_aggregate = [
    "expectancy_r", "total_r", "profit_factor", "win_rate", "max_drawdown_r",
]
_heatmap_options_directional = [
    "long_expectancy_r", "short_expectancy_r",
    "long_profit_factor", "short_profit_factor",
    "min_direction_expectancy_r", "min_direction_profit_factor",
]
_heatmap_all_options = _heatmap_options_aggregate + [
    c for c in _heatmap_options_directional if c in grid.columns
]

heatmap_metric = st.selectbox(
    "Heatmap metric",
    options=[c for c in _heatmap_all_options if c in grid.columns],
    index=0,
    help="Select the metric to visualise across SL/TP combinations.",
)

st.plotly_chart(
    _heatmap(grid, heatmap_metric, heatmap_metric.replace("_", " ").title()),
    use_container_width=True,
)

# Full results table
st.subheader("Full grid results")
display_cols = [c for c in [
    "stop_loss_ticks", "take_profit_ticks", "tp_sl_ratio",
    "risk_points", "target_points",
    "trade_count", "win_rate", "loss_rate",
    "avg_r", "expectancy_r", "median_r", "total_r",
    "profit_factor", "avg_win_r", "avg_loss_r",
    "max_drawdown_r", "best_trade_r", "worst_trade_r",
    # Directional columns
    "long_trade_count", "long_win_rate", "long_avg_r",
    "long_expectancy_r", "long_total_r", "long_profit_factor",
    "short_trade_count", "short_win_rate", "short_avg_r",
    "short_expectancy_r", "short_total_r", "short_profit_factor",
    "min_direction_trade_count", "min_direction_expectancy_r",
    "min_direction_profit_factor",
] if c in grid.columns]
st.dataframe(grid[display_cols], use_container_width=True, hide_index=True)
