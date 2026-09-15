"""Classic Validation OTF matrix persist/display (QR D-4 / QI-05-02).

Streamlit-free: callers pass ``st``. ``otf_validation_*`` keys unchanged.
"""

from __future__ import annotations

from typing import Any

from thesistester.config import INSTRUMENTS
from thesistester.validation_page_helpers import fmt_value as _fmt_value


def render_otf_validation_matrix(st: Any) -> None:
    """OTF filter validation matrix persist + display."""
    # ── OTF validation matrix ─────────────────────────────────────────────────────
    st.subheader("OTF filter validation matrix")
    st.caption(
        "⚠️ **Diagnostic only — not proof of edge.** "
        "OTF validation evaluates the fixed five-configuration comparison matrix on a "
        "chronological train/OOS split.  Results must not be used to select an OTF "
        "configuration for production use, and lower trade count alone is not an "
        "improvement.  OOS performance is the evaluation view; train results drive "
        "ranking/selection only.  Multiple-comparison caution applies: comparing five "
        "configurations inflates the risk of spurious results.  Minimum sample-size "
        "caution applies: very few trades in either period make all metrics unreliable."
    )

    _signals_for_otf = st.session_state.get("signals")
    _source_for_otf = st.session_state.get("levels")
    if _source_for_otf is None or (hasattr(_source_for_otf, "empty") and _source_for_otf.empty):
        _source_for_otf = st.session_state.get("data")

    if _signals_for_otf is None or (hasattr(_signals_for_otf, "empty") and _signals_for_otf.empty):
        st.info(
            "No signals found in session state.  Generate signals before running OTF validation."
        )
    elif _source_for_otf is None or (hasattr(_source_for_otf, "empty") and _source_for_otf.empty):
        st.info(
            "No OHLCV source data found in session state.  Load data before running OTF validation."
        )
    else:
        _instrument = st.session_state.get("instrument", "ES")
        _inst = INSTRUMENTS.get(_instrument)
        _tick_size = _inst.tick_size if _inst else 0.25
        _point_value = _inst.point_value if _inst else 50.0

        _otf_col1, _otf_col2 = st.columns(2)
        _train_fraction = _otf_col1.slider(
            "Train fraction",
            min_value=0.5,
            max_value=0.9,
            value=0.7,
            step=0.05,
            help="Fraction of signals (chronological) used as the train period. Default 0.70 (70%).",
        )

        _backtest_exec = st.session_state.get("backtest_execution_costs") or {}
        _sl_ticks = st.session_state.get("stop_loss_ticks") or 8
        _tp_ticks = st.session_state.get("take_profit_ticks") or 16
        _session_tz = st.session_state.get("exchange_timezone") or "America/New_York"

        # Match the Validation WFO surface: known instruments use configured
        # eth_start; unknown instruments use the existing explicit "18:00" fallback.
        _eth_start = _inst.eth_start if _inst else "18:00"

        st.caption(
            f"Using SL={_sl_ticks} ticks, TP={_tp_ticks} ticks, "
            f"session timezone={_session_tz}, eth_start={_eth_start}, "
            f"train/OOS split={_train_fraction:.0%}/{1 - _train_fraction:.0%}."
        )

        if st.button("▶ Run OTF validation matrix", key="run_otf_validation", type="secondary"):
            from thesistester.analytics.otf_validation import run_otf_validation_matrix

            with st.spinner("Running OTF validation matrix (5 configurations × train + OOS)…"):
                try:
                    _otf_matrix_result = run_otf_validation_matrix(
                        source_df=_source_for_otf,
                        candidate_signals=_signals_for_otf,
                        tick_size=_tick_size,
                        point_value=_point_value,
                        stop_loss_ticks=float(_sl_ticks),
                        take_profit_ticks=float(_tp_ticks),
                        train_fraction=_train_fraction,
                        session_timezone=_session_tz,
                        eth_start=_eth_start,
                        execution_kwargs={
                            "commission_per_side": float(
                                _backtest_exec.get("commission_per_side", 0.0) or 0.0
                            ),
                            "slippage_ticks": float(
                                _backtest_exec.get("slippage_ticks", 0.0) or 0.0
                            ),
                        },
                    )
                    st.session_state["otf_validation_matrix"] = _otf_matrix_result
                    st.session_state["otf_validation_config"] = {
                        "train_fraction": _train_fraction,
                        "oos_fraction": round(1 - _train_fraction, 10),
                        "sl_ticks": float(_sl_ticks),
                        "tp_ticks": float(_tp_ticks),
                        "session_timezone": _session_tz,
                        "eth_start": _eth_start,
                        "tick_size": float(_tick_size),
                        "point_value": float(_point_value),
                    }
                    # Summary: train-selected row label and OOS expectancy
                    _selected_rows = _otf_matrix_result[_otf_matrix_result["is_train_selected"]]
                    _selected_label = (
                        _selected_rows.iloc[0]["configuration_label"]
                        if not _selected_rows.empty
                        else None
                    )
                    _selected_oos_exp = (
                        _selected_rows.iloc[0]["oos_expectancy_r"]
                        if not _selected_rows.empty
                        else None
                    )
                    st.session_state["otf_validation_summary"] = {
                        "selected_by_train_metric": "train_expectancy_r",
                        "selected_train_config": _selected_label,
                        "selected_oos_expectancy_r": _selected_oos_exp,
                        "train_fraction": _train_fraction,
                        "oos_fraction": round(1 - _train_fraction, 10),
                        "caveat": (
                            "OTF validation is diagnostic only.  The train-selected configuration "
                            "is selected by train metrics only.  OOS performance is provided for "
                            "evaluation purposes and is not proof of edge."
                        ),
                    }
                    st.success("OTF validation matrix complete.")
                except ValueError as e:
                    st.error(f"OTF validation error: {e}")

        _otf_matrix = st.session_state.get("otf_validation_matrix")
        if _otf_matrix is not None and not _otf_matrix.empty:
            _otf_val_cfg = st.session_state.get("otf_validation_config", {})
            _tf = _otf_val_cfg.get("train_fraction", 0.7)
            st.caption(
                f"Train fraction: {_tf:.0%} | OOS fraction: {1 - _tf:.0%} | "
                f"SL={_otf_val_cfg.get('sl_ticks', '—')} ticks | "
                f"TP={_otf_val_cfg.get('tp_ticks', '—')} ticks"
            )

            # Highlight train-selected row with a column
            _display_df = _otf_matrix.copy()

            # Select which columns to show prominently
            _display_cols = [
                "configuration_label",
                "is_train_selected",
                "train_rank",
                "train_accepted_signal_count",
                "train_trade_count",
                "train_expectancy_r",
                "train_win_rate",
                "train_profit_factor",
                "oos_accepted_signal_count",
                "oos_trade_count",
                "oos_expectancy_r",
                "oos_win_rate",
                "oos_profit_factor",
                "rejection_rate",
                "rejection_rate_delta_vs_no_otf",
                "oos_expectancy_delta_vs_no_otf",
            ]
            _show_cols = [c for c in _display_cols if c in _display_df.columns]
            st.dataframe(
                _display_df[_show_cols],
                width="stretch",
                hide_index=True,
            )

            _summary = st.session_state.get("otf_validation_summary", {})
            _selected_label = _summary.get("selected_train_config")
            if _selected_label:
                st.info(
                    f"**Train-selected configuration:** `{_selected_label}` "
                    f"(selected by train_expectancy_r only; not a contest win). "
                    f"OOS expectancy for selected config: "
                    f"{_fmt_value(_summary.get('selected_oos_expectancy_r'))} R. "
                    "⚠️ This is diagnostic — not a production recommendation."
                )

            with st.expander("Full OTF matrix (all columns)"):
                st.dataframe(_otf_matrix, width="stretch", hide_index=True)

            st.warning(
                "⚠️ **OTF validation caveats:** "
                "(1) Results are diagnostic only — not proof of edge. "
                "(2) Do not select an OTF configuration based on full-dataset results. "
                "(3) Lower trade count alone is not an improvement. "
                "(4) OOS performance is the evaluation view; do not use it for selection. "
                "(5) Multiple-comparison caution: comparing 5 configurations increases the "
                "risk of spurious results. "
                "(6) Minimum sample-size caution: small trade counts make all metrics unreliable."
            )
