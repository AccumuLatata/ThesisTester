"""Phase 8 — Statistical Validation and Robustness Diagnostics.

Analyses completed trades from Phase 5 using bootstrap confidence intervals,
sign-flip permutation tests, trade-count diagnostics, and grid-search overfit
warnings.  No trade re-simulation is performed.

⚠️  All outputs are diagnostic only — not proof of edge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from thesistester.analytics import run_walk_forward_sl_tp, summarize_walk_forward
from thesistester.analytics.validation import validation_summary
from thesistester.config import INSTRUMENTS

st.title("📊 Statistical Validation")
st.caption("Diagnostic only — not proof of edge.")


def _fmt_value(v, fmt=".4f", fallback="—"):
    if v is None:
        return fallback
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return fallback

# ── Require trades ────────────────────────────────────────────────────────────
trades_raw = st.session_state.get("trades")
if trades_raw is None or trades_raw.empty:
    st.warning("No trades found. Please run a backtest first.")
    st.stop()

backtest_exposure_policy = (
    (st.session_state.get("exposure_policy") or {}).get("exposure_policy")
)
if backtest_exposure_policy == "allow_all":
    st.warning(
        "Exposure policy is `allow_all`: overlapping trades may inflate trade count "
        "and understate uncertainty. For validation-grade results, consider "
        "`single_position` or another restrictive policy."
    )

# ── Optional grid results ─────────────────────────────────────────────────────
grid_raw = st.session_state.get("grid_results")

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Validation settings")

    n_bootstrap = int(
        st.number_input(
            "Bootstrap samples",
            min_value=500,
            max_value=50_000,
            value=2000,
            step=500,
            help="Number of bootstrap resamples for the CI estimate.",
        )
    )

    n_permutations = int(
        st.number_input(
            "Permutations",
            min_value=500,
            max_value=50_000,
            value=5000,
            step=500,
            help="Number of sign-flip permutations for the null distribution.",
        )
    )

    confidence = (
        st.selectbox(
            "Confidence level",
            options=[0.90, 0.95, 0.99],
            index=1,
            format_func=lambda v: f"{v:.0%}",
            help="Confidence level for the bootstrap CI.",
        )
        or 0.95
    )

    random_seed = int(
        st.number_input(
            "Random seed",
            min_value=0,
            max_value=99_999,
            value=42,
            step=1,
            help="Seed for reproducible bootstrap and permutation results.",
        )
    )

    min_trades_soft = int(
        st.number_input(
            "Min trades (soft)",
            min_value=1,
            max_value=10_000,
            value=30,
            step=1,
            help="Below this count results are flagged as insufficient.",
        )
    )

    min_trades_hard = int(
        st.number_input(
            "Min trades (hard)",
            min_value=1,
            max_value=10_000,
            value=100,
            step=1,
            help="At or above this count results are considered reasonable.",
        )
    )

    grid_metric_options = ["expectancy_r", "avg_r", "total_r", "win_rate"]
    if grid_raw is not None and not grid_raw.empty:
        # Use an explicit allowlist to avoid polluting the selector with
        # structural columns, trade counts, and every directional variant.
        _grid_metric_allowlist = [
            "expectancy_r",
            "avg_r",
            "total_r",
            "profit_factor",
            "win_rate",
            "max_drawdown_r",
            "long_expectancy_r",
            "short_expectancy_r",
            "long_profit_factor",
            "short_profit_factor",
            "min_direction_expectancy_r",
            "min_direction_profit_factor",
        ]
        _available = [c for c in _grid_metric_allowlist if c in grid_raw.columns]
        grid_metric_options = _available or grid_metric_options

    grid_metric = st.selectbox(
        "Grid metric",
        options=grid_metric_options,
        index=grid_metric_options.index("expectancy_r")
        if "expectancy_r" in grid_metric_options
        else 0,
        help="Metric used for grid overfit diagnostics.",
    )

# ── Run validation ────────────────────────────────────────────────────────────
if st.button("▶ Run Validation", type="primary"):
    with st.spinner("Running validation diagnostics…"):
        summary = validation_summary(
            trades_raw,
            grid=grid_raw,
            n_bootstrap=n_bootstrap,
            n_permutations=n_permutations,
            confidence=confidence,
            random_state=random_seed,
            min_trades_soft=min_trades_soft,
            min_trades_hard=min_trades_hard,
            selected_grid_metric=grid_metric,
        )
    st.session_state["validation_summary"] = summary
    st.success("Validation complete.")

st.divider()
st.subheader("Walk-forward / OOS diagnostics")
st.caption("Diagnostic only — walk-forward can still overfit.")

run_wfo = st.toggle("Run walk-forward diagnostics", value=False)
if run_wfo:
    data_source = st.session_state.get("levels")
    if data_source is None or data_source.empty:
        data_source = st.session_state.get("data")
    signals_raw = st.session_state.get("signals")
    if data_source is None or data_source.empty:
        st.warning("No OHLCV data found for walk-forward diagnostics.")
    elif signals_raw is None or signals_raw.empty:
        st.warning("No signals found for walk-forward diagnostics.")
    else:
        instrument = st.session_state.get("instrument", "ES")
        inst = INSTRUMENTS.get(instrument)
        tick_size = inst.tick_size if inst else 0.25
        point_value = inst.point_value if inst else 50.0

        c1, c2, c3 = st.columns(3)
        train_bars = int(c1.number_input("Train bars", min_value=5, max_value=1_000_000, value=500, step=5))
        test_bars = int(c2.number_input("Test bars", min_value=5, max_value=1_000_000, value=100, step=5))
        step_bars_input = c3.number_input(
            "Step bars (0 = default)",
            min_value=0,
            max_value=1_000_000,
            value=0,
            step=1,
        )
        step_bars = None if int(step_bars_input) == 0 else int(step_bars_input)

        c4, c5 = st.columns(2)
        wfo_ranking_metric = c4.selectbox(
            "WFO ranking metric",
            options=["expectancy_r", "total_r", "profit_factor", "win_rate"],
            index=0,
        )
        wfo_min_train_trades = int(
            c5.number_input(
                "WFO min train trades",
                min_value=1,
                max_value=100_000,
                value=1,
                step=1,
            )
        )

        grid_results = st.session_state.get("grid_results")
        if grid_results is not None and not grid_results.empty:
            sl_values = sorted(pd.to_numeric(grid_results["stop_loss_ticks"], errors="coerce").dropna().unique().tolist())
            tp_values = sorted(pd.to_numeric(grid_results["take_profit_ticks"], errors="coerce").dropna().unique().tolist())
            st.caption(f"Using SL/TP values from Grid Search ({len(sl_values)} SL × {len(tp_values)} TP).")
        else:
            gc1, gc2, gc3 = st.columns(3)
            sl_start = float(gc1.number_input("SL start", min_value=1.0, max_value=500.0, value=4.0, step=1.0))
            sl_stop = float(gc2.number_input("SL stop", min_value=1.0, max_value=500.0, value=20.0, step=1.0))
            sl_step = float(gc3.number_input("SL step", min_value=1.0, max_value=100.0, value=4.0, step=1.0))
            gc4, gc5, gc6 = st.columns(3)
            tp_start = float(gc4.number_input("TP start", min_value=1.0, max_value=1000.0, value=8.0, step=1.0))
            tp_stop = float(gc5.number_input("TP stop", min_value=1.0, max_value=1000.0, value=40.0, step=1.0))
            tp_step = float(gc6.number_input("TP step", min_value=1.0, max_value=200.0, value=8.0, step=1.0))
            sl_values = [round(v, 10) for v in np.arange(sl_start, sl_stop + sl_step * 0.5, sl_step).tolist() if v > 0]
            tp_values = [round(v, 10) for v in np.arange(tp_start, tp_stop + tp_step * 0.5, tp_step).tolist() if v > 0]

        grid_costs = st.session_state.get("grid_execution_costs") or st.session_state.get("backtest_execution_costs") or {}
        session_policy = st.session_state.get("grid_session_exit_policy") or st.session_state.get("backtest_session_exit_policy") or {}
        exposure_policy_state = st.session_state.get("grid_exposure_policy") or st.session_state.get("exposure_policy") or {}

        if st.button("▶ Run walk-forward diagnostics", type="secondary"):
            if not sl_values or not tp_values:
                st.error("SL/TP grid values are empty; adjust the ranges.")
            else:
                with st.spinner("Running walk-forward diagnostics…"):
                    try:
                        results_df = run_walk_forward_sl_tp(
                            df=data_source,
                            signals=signals_raw,
                            tick_size=tick_size,
                            point_value=point_value,
                            stop_loss_ticks_values=sl_values,
                            take_profit_ticks_values=tp_values,
                            train_bars=train_bars,
                            test_bars=test_bars,
                            step_bars=step_bars,
                            ranking_metric=wfo_ranking_metric,
                            min_train_trades=wfo_min_train_trades,
                            max_holding_bars=None,
                            allow_same_bar_exit=True,
                            commission_per_side=float(grid_costs.get("commission_per_side", 0.0) or 0.0),
                            slippage_ticks=float(grid_costs.get("slippage_ticks", 0.0) or 0.0),
                            flat_by_session_close=bool(session_policy.get("flat_by_session_close", False)),
                            session_close_time=session_policy.get("session_close_time"),
                            session_timezone=session_policy.get("session_timezone"),
                            no_new_entries_after=session_policy.get("no_new_entries_after"),
                            exposure_policy=str(exposure_policy_state.get("exposure_policy", "allow_all")),
                            cooldown_bars_after_exit=int(exposure_policy_state.get("cooldown_bars_after_exit", 0) or 0),
                        )
                    except ValueError as e:
                        st.error(f"Walk-forward diagnostics error: {e}")
                    else:
                        wfo_summary = summarize_walk_forward(results_df)
                        wfo_config = {
                            "train_bars": int(train_bars),
                            "test_bars": int(test_bars),
                            "step_bars": int(step_bars if step_bars is not None else test_bars),
                            "ranking_metric": wfo_ranking_metric,
                            "min_train_trades": int(wfo_min_train_trades),
                            "stop_loss_ticks_values": sl_values,
                            "take_profit_ticks_values": tp_values,
                            "tick_size": float(tick_size),
                            "point_value": float(point_value),
                            "commission_per_side": float(grid_costs.get("commission_per_side", 0.0) or 0.0),
                            "slippage_ticks": float(grid_costs.get("slippage_ticks", 0.0) or 0.0),
                            "flat_by_session_close": bool(session_policy.get("flat_by_session_close", False)),
                            "session_close_time": session_policy.get("session_close_time"),
                            "session_timezone": session_policy.get("session_timezone"),
                            "no_new_entries_after": session_policy.get("no_new_entries_after"),
                            "exposure_policy": str(exposure_policy_state.get("exposure_policy", "allow_all")),
                            "cooldown_bars_after_exit": int(exposure_policy_state.get("cooldown_bars_after_exit", 0) or 0),
                        }
                        st.session_state["walk_forward_results"] = results_df
                        st.session_state["walk_forward_summary"] = wfo_summary
                        st.session_state["walk_forward_config"] = wfo_config
                        st.success("Walk-forward diagnostics complete.")

wfo_results = st.session_state.get("walk_forward_results")
wfo_summary = st.session_state.get("walk_forward_summary")
if isinstance(wfo_summary, dict):
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Folds", wfo_summary.get("fold_count", 0))
    s2.metric("Valid OOS folds", wfo_summary.get("valid_fold_count", 0))
    s3.metric("OOS profitable rate", _fmt_value(wfo_summary.get("oos_profitable_fold_rate"), ".1%"))
    s4.metric("Median test expectancy", _fmt_value(wfo_summary.get("median_test_expectancy_r")))
if hasattr(wfo_results, "empty") and not wfo_results.empty:
    st.dataframe(wfo_results, width="stretch", hide_index=True)

# ── Display results if available ──────────────────────────────────────────────
summary = st.session_state.get("validation_summary")
if summary is None:
    st.info("Configure settings in the sidebar and click **Run Validation**.")
    st.stop()

bs = summary["bootstrap"]
perm = summary["permutation"]
tc = summary["trade_count"]
go_diag = summary["grid_overfit"]

# ── Trade-count diagnostic ────────────────────────────────────────────────────
st.subheader("Trade count")
status_emoji = {"insufficient": "🔴", "limited": "🟡", "reasonable": "🟢"}.get(
    tc["status"], "⚪"
)
st.markdown(f"{status_emoji} **{tc['status'].capitalize()}** — {tc['message']}")

if tc["status"] == "insufficient":
    st.warning(
        f"⚠️ Only {tc['trade_count']} trade(s). Statistical results below "
        "are not meaningful with this sample size."
    )

st.divider()

# ── Top-level metrics ─────────────────────────────────────────────────────────
st.subheader("Bootstrap expectancy CI")

col1, col2, col3, col4, col5 = st.columns(5)

def _fmt(v, fmt=".4f", fallback="—"):
    if v is None:
        return fallback
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return fallback


col1.metric("Trades", tc["trade_count"])
col2.metric("Observed avg R", _fmt(bs.get("observed_avg_r")))
col3.metric(
    f"CI lower ({confidence:.0%})",
    _fmt(bs.get("ci_lower")),
)
col4.metric(
    f"CI upper ({confidence:.0%})",
    _fmt(bs.get("ci_upper")),
)
col5.metric(
    "P(mean R > 0)",
    _fmt(bs.get("probability_positive"), ".1%") if bs.get("probability_positive") is not None else "—",
)

# CI includes zero warning
ci_lower = bs.get("ci_lower")
ci_upper = bs.get("ci_upper")
if ci_lower is not None and ci_upper is not None:
    if ci_lower <= 0 <= ci_upper:
        st.info(
            "ℹ️ Bootstrap CI includes zero; expectancy estimate is uncertain. "
            "This does not confirm positive edge."
        )

st.divider()

# ── Permutation test ──────────────────────────────────────────────────────────
st.subheader("Sign-flip permutation test")
st.caption(
    "Null hypothesis: trade signs are random around zero. "
    "One-sided p-value = fraction of permuted means ≥ observed mean R."
)

col_p1, col_p2, col_p3 = st.columns(3)
col_p1.metric("Observed avg R", _fmt(perm.get("observed_avg_r")))
col_p2.metric("p-value (positive)", _fmt(perm.get("p_value_positive"), ".4f"))
col_p3.metric("Permutations", perm.get("n_permutations", "—"))

p_val = perm.get("p_value_positive")
if p_val is not None:
    if p_val > 0.10:
        st.info(
            f"p = {p_val:.4f} — Observed mean R is not unusually high "
            "relative to a zero-expectancy null (sign-flip test)."
        )
    elif p_val > 0.05:
        st.info(
            f"p = {p_val:.4f} — Marginal evidence against the zero-expectancy null. "
            "Interpret with caution."
        )
    else:
        st.success(
            f"p = {p_val:.4f} — Observed mean R is in the tail of the null "
            "distribution. Note: this test assumes sign symmetry and ignores "
            "serial dependence. It is a diagnostic, not a significance test."
        )

st.divider()

# ── Grid overfit diagnostics ──────────────────────────────────────────────────
if grid_raw is not None and not grid_raw.empty:
    st.subheader("Grid-search overfit risk")

    risk_emoji = {"none": "⚪", "low": "🟢", "medium": "🟡", "high": "🔴"}.get(
        go_diag["risk_level"], "⚪"
    )
    st.markdown(
        f"{risk_emoji} **Risk: {go_diag['risk_level'].upper()}** — {go_diag['message']}"
    )

    gcol1, gcol2, gcol3, gcol4, gcol5 = st.columns(5)
    gcol1.metric("Grid cells", go_diag["grid_cell_count"])
    gcol2.metric("Valid cells", go_diag["valid_cell_count"])
    gcol3.metric("Best", _fmt(go_diag.get("best_metric")))
    gcol4.metric("Median", _fmt(go_diag.get("median_metric")))
    gcol5.metric("Best − Median", _fmt(go_diag.get("best_vs_median_delta")))

    if go_diag["risk_level"] in ("medium", "high"):
        st.warning(
            "⚠️ Grid search tested many combinations; best result may be "
            "overfit to in-sample data."
        )

    st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
st.subheader("Bootstrap distribution of mean R")

bootstrap_means = bs.get("bootstrap_means") or []
if bootstrap_means:
    obs_r = bs.get("observed_avg_r")
    ci_lo = bs.get("ci_lower")
    ci_hi = bs.get("ci_upper")

    fig_bs = go.Figure()
    fig_bs.add_trace(
        go.Histogram(
            x=bootstrap_means,
            nbinsx=60,
            name="Bootstrap mean R",
            marker_color="steelblue",
            opacity=0.75,
        )
    )
    if obs_r is not None:
        fig_bs.add_vline(
            x=obs_r,
            line_dash="solid",
            line_color="orange",
            annotation_text=f"Observed avg R = {obs_r:.4f}",
            annotation_position="top right",
        )
    fig_bs.add_vline(
        x=0,
        line_dash="dash",
        line_color="gray",
        annotation_text="0",
        annotation_position="top left",
    )
    if ci_lo is not None:
        fig_bs.add_vline(
            x=ci_lo,
            line_dash="dot",
            line_color="red",
            annotation_text=f"CI lower {ci_lo:.4f}",
            annotation_position="bottom left",
        )
    if ci_hi is not None:
        fig_bs.add_vline(
            x=ci_hi,
            line_dash="dot",
            line_color="green",
            annotation_text=f"CI upper {ci_hi:.4f}",
            annotation_position="bottom right",
        )
    fig_bs.update_layout(
        xaxis_title="Bootstrap mean R",
        yaxis_title="Count",
        height=360,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig_bs, width="stretch")
else:
    st.info("No bootstrap results to display.")

st.subheader("Permutation null distribution")

permuted_means = perm.get("permuted_means") or []
if permuted_means:
    obs_r_p = perm.get("observed_avg_r")

    fig_perm = go.Figure()
    fig_perm.add_trace(
        go.Histogram(
            x=permuted_means,
            nbinsx=60,
            name="Permuted mean R (null)",
            marker_color="slategray",
            opacity=0.75,
        )
    )
    fig_perm.add_vline(
        x=0,
        line_dash="dash",
        line_color="gray",
        annotation_text="0",
        annotation_position="top left",
    )
    if obs_r_p is not None:
        fig_perm.add_vline(
            x=obs_r_p,
            line_dash="solid",
            line_color="orange",
            annotation_text=f"Observed avg R = {obs_r_p:.4f}",
            annotation_position="top right",
        )
    fig_perm.update_layout(
        xaxis_title="Permuted mean R",
        yaxis_title="Count",
        height=360,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig_perm, width="stretch")
else:
    st.info("No permutation results to display.")

# ── Full diagnostics expander ─────────────────────────────────────────────────
with st.expander("Full diagnostics (JSON)"):
    # Omit large arrays from the JSON display for readability
    display_summary = {
        "bootstrap": {
            k: v for k, v in bs.items() if k != "bootstrap_means"
        },
        "permutation": {
            k: v for k, v in perm.items() if k != "permuted_means"
        },
        "trade_count": tc,
        "grid_overfit": go_diag,
    }
    st.json(display_summary)
