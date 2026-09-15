"""Classic Validation Phase 8 display (QR D-4 / QI-05-02).

Streamlit-free: callers pass ``st``. H13 permutation AST (`p_val > 0.05`
else ``st.info`` + H13 caption) stays in this module as string literals
(copy-guards / A-4). ``assemble_permutation_copy`` is the unit-tested twin;
``fmt_value`` is the shared formatter.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from thesistester.validation_page_helpers import fmt_value as _fmt


def render_phase8_results(
    st: Any,
    *,
    summary: dict[str, Any],
    grid_raw: Any,
    confidence: float,
) -> None:
    """Bootstrap / permutation / grid-overfit / chart display."""
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
        "Share of bootstrap means > 0",
        _fmt(bs.get("probability_positive"), ".1%")
        if bs.get("probability_positive") is not None
        else "—",
    )

    trade_summary = st.session_state.get("trade_summary") or {}
    if isinstance(trade_summary, dict):
        st.subheader("Backtest tail / pain diagnostics")
        vcol1, vcol2, vcol3, vcol4 = st.columns(4)
        vcol1.metric("Outlier dependency", _fmt(trade_summary.get("outlier_dependency_ratio")))
        vcol2.metric("Tail ratio", _fmt(trade_summary.get("tail_ratio")))
        vcol3.metric("Max consecutive losses", trade_summary.get("max_consecutive_losses", 0))
        vcol4.metric("Ulcer index R", _fmt(trade_summary.get("ulcer_index_r")))

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
            st.info(
                f"p = {p_val:.4f} — Observed mean R is in the tail of the "
                "sign-flip null. Diagnostic only — not a significance test "
                "and not proof of edge."
            )
            st.caption("Sign-flip assumes sign symmetry and ignores serial dependence (H13).")

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
                "⚠️ Grid search tested many combinations; best result may be overfit to in-sample data."
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
            "bootstrap": {k: v for k, v in bs.items() if k != "bootstrap_means"},
            "permutation": {k: v for k, v in perm.items() if k != "permuted_means"},
            "trade_count": tc,
            "grid_overfit": go_diag,
        }
        st.json(display_summary)
