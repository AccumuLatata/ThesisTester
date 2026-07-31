"""R21 — additive multi-setup portfolio diagnostics."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from thesistester.api import run_portfolio_analysis
from thesistester.app_state import bootstrap_active_saved_dataset

st.title("🧺 Portfolio")
bootstrap_active_saved_dataset()
st.caption(
    "Diagnostic only — combines completed, independently simulated setup trades. "
    "It is not a capital, margin, liquidity, or fill simulation."
)

current_trades = st.session_state.get("trades")
sources: dict[str, pd.DataFrame] = {}
if isinstance(current_trades, pd.DataFrame) and not current_trades.empty:
    current_name = st.text_input("Current setup label", value="current_setup")
    sources[current_name] = current_trades

uploads = st.file_uploader(
    "Additional completed-trade CSV exports",
    type=["csv"],
    accept_multiple_files=True,
    help="Each CSV must be a trade table from the same instrument and parent bar timeline.",
)
for upload in uploads or []:
    sources[upload.name.rsplit(".", maxsplit=1)[0]] = pd.read_csv(upload)

if len(sources) < 2:
    st.info(
        "Provide at least two completed setup trade tables: current Backtest trades plus CSV exports."
    )
    st.stop()

st.dataframe(
    pd.DataFrame(
        [{"setup_id": setup_id, "trade_count": len(trades)} for setup_id, trades in sources.items()]
    ),
    width="stretch",
    hide_index=True,
)
controls = st.columns(2)
exposure_policy = controls[0].selectbox(
    "Portfolio exposure policy",
    options=["allow_all", "single_position", "single_direction", "single_setup"],
    help="Apply this policy once after setup trades are merged. Per-setup source runs should use allow_all.",
)
cooldown = int(
    controls[1].number_input(
        "Cooldown bars after exit",
        min_value=0,
        max_value=1_000,
        value=0,
        step=1,
    )
)

if st.button("▶ Run portfolio analysis", type="primary"):
    try:
        result = run_portfolio_analysis(
            sources,
            instrument=st.session_state.get("instrument", "ES"),
            config={
                "exposure_policy": exposure_policy,
                "cooldown_bars_after_exit": cooldown,
            },
            bar_count=len(st.session_state.get("data", [])) or None,
        )
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.session_state.update(result)
        st.session_state["portfolio_setup_inputs"] = list(sources)
        st.success("Portfolio analysis complete.")

summary = st.session_state.get("portfolio_summary")
if not isinstance(summary, dict):
    st.stop()
metrics = summary.get("portfolio_metrics") or {}
admission = summary.get("admission") or {}
metric_cols = st.columns(4)
metric_cols[0].metric("Portfolio total R", f"{metrics.get('total_r', 0.0):.2f}")
metric_cols[1].metric("Portfolio max DD R", f"{metrics.get('max_drawdown_r', 0.0):.2f}")
metric_cols[2].metric("Admitted trades", admission.get("admitted_trade_count", 0))
metric_cols[3].metric("Skipped trades", admission.get("skipped_trade_count", 0))
st.caption(summary.get("caveat", ""))

equity = st.session_state.get("portfolio_equity_curve")
if isinstance(equity, pd.DataFrame) and not equity.empty:
    st.subheader("Combined equity")
    st.line_chart(equity.set_index("exit_timestamp")[["cum_r", "drawdown_r"]])

contribution = st.session_state.get("portfolio_marginal_contribution")
if isinstance(contribution, pd.DataFrame) and not contribution.empty:
    st.subheader("Marginal setup contribution")
    st.dataframe(contribution, width="stretch", hide_index=True)

correlation = st.session_state.get("portfolio_correlation")
if isinstance(correlation, pd.DataFrame) and not correlation.empty:
    st.subheader("Setup return correlation")
    figure = go.Figure(
        go.Heatmap(
            z=correlation.values,
            x=correlation.columns.tolist(),
            y=correlation.index.tolist(),
            colorscale="RdBu",
            zmin=-1,
            zmax=1,
        )
    )
    figure.update_layout(margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(figure, width="stretch")

skipped = st.session_state.get("portfolio_skipped_trades")
if isinstance(skipped, pd.DataFrame) and not skipped.empty:
    st.subheader("Portfolio admission skips")
    st.dataframe(skipped, width="stretch", hide_index=True)
