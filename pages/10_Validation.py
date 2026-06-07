"""Phase 8 — Statistical Validation and Robustness Diagnostics.

Analyses completed trades from Phase 5 using bootstrap confidence intervals,
sign-flip permutation tests, trade-count diagnostics, and grid-search overfit
warnings.  No trade re-simulation is performed.

⚠️  All outputs are diagnostic only — not proof of edge.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from thesistester.analytics.validation import validation_summary

st.title("📊 Statistical Validation")
st.caption("Diagnostic only — not proof of edge.")

# ── Require trades ────────────────────────────────────────────────────────────
trades_raw = st.session_state.get("trades")
if trades_raw is None or trades_raw.empty:
    st.warning("No trades found. Please run a backtest first.")
    st.stop()

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
    st.plotly_chart(fig_bs, use_container_width=True)
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
    st.plotly_chart(fig_perm, use_container_width=True)
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
