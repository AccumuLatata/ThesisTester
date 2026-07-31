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

from thesistester.analytics import (
    add_excursion_r_columns,
    add_time_buckets,
    excursion_summary,
    monte_carlo_summary,
    run_walk_forward_sl_tp,
    run_wfa_matrix,
)
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


def _parse_positive_int_values(raw: str) -> list[int]:
    values = sorted(
        {
            int(token.strip())
            for token in str(raw).split(",")
            if token.strip() and int(token.strip()) > 0
        }
    )
    if not values:
        raise ValueError("Provide at least one positive integer.")
    return values


# ── Require trades ────────────────────────────────────────────────────────────
trades_raw = st.session_state.get("trades")
if trades_raw is None or trades_raw.empty:
    st.warning("No trades found. Please run a backtest first.")
    st.stop()

backtest_exposure_policy = (st.session_state.get("exposure_policy") or {}).get("exposure_policy")
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
        max_window_bars = max(5, int(len(data_source)))
        mode1, mode2 = st.columns(2)
        fold_mode = mode1.selectbox(
            "Fold units",
            options=["bars", "sessions"],
            format_func=lambda value: "Bars (legacy)" if value == "bars" else "Trading sessions",
        )
        window_mode = mode2.selectbox(
            "Window mode",
            options=["rolling", "anchored"],
        )
        train_sessions = test_sessions = step_sessions = None
        if fold_mode == "bars":
            c1, c2, c3 = st.columns(3)
            train_bars = int(
                c1.number_input(
                    "Train bars",
                    min_value=5,
                    max_value=max_window_bars,
                    value=min(500, max_window_bars),
                    step=5,
                )
            )
            test_bars = int(
                c2.number_input(
                    "Test bars",
                    min_value=5,
                    max_value=max_window_bars,
                    value=min(100, max_window_bars),
                    step=5,
                )
            )
            step_bars_input = c3.number_input(
                "Step bars (0 = default)",
                min_value=0,
                max_value=max_window_bars,
                value=0,
                step=1,
            )
            step_bars = None if int(step_bars_input) == 0 else int(step_bars_input)
        else:
            train_bars = test_bars = 1
            step_bars = None
            c1, c2, c3 = st.columns(3)
            train_sessions = int(c1.number_input("Train sessions", min_value=1, value=5, step=1))
            test_sessions = int(c2.number_input("Test sessions", min_value=1, value=2, step=1))
            step_sessions_input = int(
                c3.number_input(
                    "Step sessions (0 = test size)",
                    min_value=0,
                    value=0,
                    step=1,
                )
            )
            step_sessions = None if step_sessions_input == 0 else step_sessions_input
        overlap_policy = st.selectbox(
            "Overlapping OOS ownership",
            options=["reject", "first", "last"],
            help="Reject avoids double-counting by withholding stitched equity.",
        )
        run_matrix = fold_mode == "sessions" and st.toggle(
            "Also run WFA matrix",
            value=False,
        )
        matrix_train_raw = matrix_test_raw = ""
        if run_matrix:
            m1, m2 = st.columns(2)
            matrix_train_raw = m1.text_input(
                "Matrix train sessions",
                value=f"{train_sessions},{train_sessions + 1}",
            )
            matrix_test_raw = m2.text_input(
                "Matrix test sessions",
                value=f"{test_sessions},{test_sessions + 1}",
            )

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
            sl_values = sorted(
                pd.to_numeric(grid_results["stop_loss_ticks"], errors="coerce")
                .dropna()
                .unique()
                .tolist()
            )
            tp_values = sorted(
                pd.to_numeric(grid_results["take_profit_ticks"], errors="coerce")
                .dropna()
                .unique()
                .tolist()
            )
            st.caption(
                f"Using SL/TP values from Grid Search ({len(sl_values)} SL × {len(tp_values)} TP)."
            )
        else:
            gc1, gc2, gc3 = st.columns(3)
            sl_start = float(
                gc1.number_input("SL start", min_value=1.0, max_value=500.0, value=4.0, step=1.0)
            )
            sl_stop = float(
                gc2.number_input("SL stop", min_value=1.0, max_value=500.0, value=20.0, step=1.0)
            )
            sl_step = float(
                gc3.number_input("SL step", min_value=1.0, max_value=100.0, value=4.0, step=1.0)
            )
            gc4, gc5, gc6 = st.columns(3)
            tp_start = float(
                gc4.number_input("TP start", min_value=1.0, max_value=1000.0, value=8.0, step=1.0)
            )
            tp_stop = float(
                gc5.number_input("TP stop", min_value=1.0, max_value=1000.0, value=40.0, step=1.0)
            )
            tp_step = float(
                gc6.number_input("TP step", min_value=1.0, max_value=200.0, value=8.0, step=1.0)
            )
            sl_values = [
                round(v, 10)
                for v in np.arange(sl_start, sl_stop + sl_step * 0.5, sl_step).tolist()
                if v > 0
            ]
            tp_values = [
                round(v, 10)
                for v in np.arange(tp_start, tp_stop + tp_step * 0.5, tp_step).tolist()
                if v > 0
            ]

        grid_costs = (
            st.session_state.get("grid_execution_costs")
            or st.session_state.get("backtest_execution_costs")
            or {}
        )
        session_policy = (
            st.session_state.get("grid_session_exit_policy")
            or st.session_state.get("backtest_session_exit_policy")
            or {}
        )
        exposure_policy_state = (
            st.session_state.get("grid_exposure_policy")
            or st.session_state.get("exposure_policy")
            or {}
        )
        intrabar_policy = (
            st.session_state.get("grid_intrabar_policy")
            or st.session_state.get("backtest_intrabar_policy")
            or {"intrabar_model": "sl_first"}
        )
        exit_management_policy = st.session_state.get("grid_exit_management_policy") or {
            "breakeven_after_r_values": [
                (st.session_state.get("backtest_exit_management_policy") or {}).get(
                    "breakeven_after_r"
                )
            ],
            "trailing_after_r_values": [
                (st.session_state.get("backtest_exit_management_policy") or {}).get(
                    "trailing_after_r"
                )
            ],
            "trailing_distance_ticks_values": [
                (st.session_state.get("backtest_exit_management_policy") or {}).get(
                    "trailing_distance_ticks"
                )
            ],
        }

        if st.button("▶ Run walk-forward diagnostics", type="secondary"):
            if not sl_values or not tp_values:
                st.error("SL/TP grid values are empty; adjust the ranges.")
            else:
                with st.spinner("Running walk-forward diagnostics…"):
                    # Resolve OTF config inside try so an invalid explicit
                    # config shows a clear error and does not install stale results.
                    from thesistester.engine.otf_integration import resolve_otf_config

                    try:
                        _wfo_otf_config = resolve_otf_config(
                            signal_settings=st.session_state.get("signal_settings"),
                            last_signal_setup=st.session_state.get("last_signal_setup"),
                            setup_config=st.session_state.get("setup_config"),
                        )
                    except ValueError as e:
                        st.error(f"OTF filter configuration error: {e}")
                    else:
                        try:
                            detailed_wfo = run_walk_forward_sl_tp(
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
                                commission_per_side=float(
                                    grid_costs.get("commission_per_side", 0.0) or 0.0
                                ),
                                slippage_ticks=float(grid_costs.get("slippage_ticks", 0.0) or 0.0),
                                flat_by_session_close=bool(
                                    session_policy.get("flat_by_session_close", False)
                                ),
                                session_close_time=session_policy.get("session_close_time"),
                                session_timezone=session_policy.get("session_timezone"),
                                no_new_entries_after=session_policy.get("no_new_entries_after"),
                                exposure_policy=str(
                                    exposure_policy_state.get("exposure_policy", "allow_all")
                                ),
                                cooldown_bars_after_exit=int(
                                    exposure_policy_state.get("cooldown_bars_after_exit", 0) or 0
                                ),
                                otf_config=_wfo_otf_config,
                                intrabar_model=str(
                                    intrabar_policy.get("intrabar_model", "sl_first")
                                ),
                                subtimeframe_data=st.session_state.get("subtimeframe_data"),
                                breakeven_after_r_values=exit_management_policy.get(
                                    "breakeven_after_r_values", [None]
                                ),
                                trailing_after_r_values=exit_management_policy.get(
                                    "trailing_after_r_values", [None]
                                ),
                                trailing_distance_ticks_values=exit_management_policy.get(
                                    "trailing_distance_ticks_values", [None]
                                ),
                                fold_mode=fold_mode,
                                window_mode=window_mode,
                                train_sessions=train_sessions,
                                test_sessions=test_sessions,
                                step_sessions=step_sessions,
                                exchange_timezone=(
                                    st.session_state.get("exchange_timezone") or "America/New_York"
                                ),
                                eth_start=(inst.eth_start if inst else "18:00"),
                                overlap_policy=overlap_policy,
                                return_result=True,
                            )
                        except ValueError as e:
                            st.error(f"Walk-forward diagnostics error: {e}")
                        else:
                            results_df = detailed_wfo.folds
                            wfo_summary = detailed_wfo.summary
                            _wfo_otf_enabled = bool(_wfo_otf_config.get("enabled", False))
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
                                "commission_per_side": float(
                                    grid_costs.get("commission_per_side", 0.0) or 0.0
                                ),
                                "slippage_ticks": float(
                                    grid_costs.get("slippage_ticks", 0.0) or 0.0
                                ),
                                "flat_by_session_close": bool(
                                    session_policy.get("flat_by_session_close", False)
                                ),
                                "session_close_time": session_policy.get("session_close_time"),
                                "session_timezone": session_policy.get("session_timezone"),
                                "no_new_entries_after": session_policy.get("no_new_entries_after"),
                                "exposure_policy": str(
                                    exposure_policy_state.get("exposure_policy", "allow_all")
                                ),
                                "cooldown_bars_after_exit": int(
                                    exposure_policy_state.get("cooldown_bars_after_exit", 0) or 0
                                ),
                                "otf_filter_enabled": _wfo_otf_enabled,
                                "intrabar_model": str(
                                    intrabar_policy.get("intrabar_model", "sl_first")
                                ),
                                "exit_management_policy": exit_management_policy,
                                "fold_mode": fold_mode,
                                "window_mode": window_mode,
                                "train_sessions": train_sessions,
                                "test_sessions": test_sessions,
                                "step_sessions": step_sessions,
                                "overlap_policy": overlap_policy,
                                "otf_filter_config": _wfo_otf_config,
                            }
                            st.session_state["walk_forward_results"] = results_df
                            st.session_state["walk_forward_summary"] = wfo_summary
                            st.session_state["walk_forward_config"] = wfo_config
                            st.session_state["walk_forward_oos_trades"] = detailed_wfo.oos_trades
                            st.session_state["walk_forward_stitched_equity"] = (
                                detailed_wfo.stitched_equity
                            )
                            st.session_state["walk_forward_warnings"] = list(detailed_wfo.warnings)
                            if run_matrix:
                                matrix_df = run_wfa_matrix(
                                    df=data_source,
                                    signals=signals_raw,
                                    tick_size=tick_size,
                                    point_value=point_value,
                                    stop_loss_ticks_values=sl_values,
                                    take_profit_ticks_values=tp_values,
                                    train_session_values=_parse_positive_int_values(
                                        matrix_train_raw
                                    ),
                                    test_session_values=_parse_positive_int_values(matrix_test_raw),
                                    window_mode=window_mode,
                                    exchange_timezone=(
                                        st.session_state.get("exchange_timezone")
                                        or "America/New_York"
                                    ),
                                    eth_start=(inst.eth_start if inst else "18:00"),
                                    ranking_metric=wfo_ranking_metric,
                                    min_train_trades=wfo_min_train_trades,
                                    commission_per_side=float(
                                        grid_costs.get("commission_per_side", 0.0) or 0.0
                                    ),
                                    slippage_ticks=float(
                                        grid_costs.get("slippage_ticks", 0.0) or 0.0
                                    ),
                                    exposure_policy=str(
                                        exposure_policy_state.get("exposure_policy", "allow_all")
                                    ),
                                    intrabar_model=str(
                                        intrabar_policy.get("intrabar_model", "sl_first")
                                    ),
                                    breakeven_after_r_values=exit_management_policy.get(
                                        "breakeven_after_r_values", [None]
                                    ),
                                    trailing_after_r_values=exit_management_policy.get(
                                        "trailing_after_r_values", [None]
                                    ),
                                    trailing_distance_ticks_values=exit_management_policy.get(
                                        "trailing_distance_ticks_values", [None]
                                    ),
                                )
                                st.session_state["wfa_matrix"] = matrix_df
                                st.session_state["wfa_matrix_config"] = {
                                    "train_session_values": _parse_positive_int_values(
                                        matrix_train_raw
                                    ),
                                    "test_session_values": _parse_positive_int_values(
                                        matrix_test_raw
                                    ),
                                    "matrix_metric": "median_test_expectancy_r",
                                }
                            # Store OTF summary for reporting
                            from thesistester.persistence.local_store import compute_otf_config_hash
                            from thesistester.engine.otf import OTF_ALGORITHM_VERSION

                            st.session_state["walk_forward_otf_filter"] = {
                                "otf_filter_enabled": _wfo_otf_enabled,
                                "otf_filter_config": _wfo_otf_config,
                                "otf_algorithm_version": OTF_ALGORITHM_VERSION,
                                "otf_config_hash": compute_otf_config_hash(_wfo_otf_config),
                            }
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
for warning in st.session_state.get("walk_forward_warnings", []):
    st.warning(warning)
wfo_equity = st.session_state.get("walk_forward_stitched_equity")
if isinstance(wfo_equity, pd.DataFrame) and not wfo_equity.empty:
    st.markdown("**Stitched OOS equity**")
    st.line_chart(wfo_equity.set_index("exit_timestamp")["cum_r"])
wfa_matrix = st.session_state.get("wfa_matrix")
if isinstance(wfa_matrix, pd.DataFrame) and not wfa_matrix.empty:
    st.markdown("**Walk-Forward Analysis matrix**")
    matrix_pivot = wfa_matrix.pivot(
        index="train_sessions",
        columns="test_sessions",
        values="matrix_value",
    )
    matrix_fig = go.Figure(
        go.Heatmap(
            z=matrix_pivot.values,
            x=[str(value) for value in matrix_pivot.columns],
            y=[str(value) for value in matrix_pivot.index],
            colorscale="RdYlGn",
            colorbar=dict(title="Median OOS expectancy R"),
        )
    )
    matrix_fig.update_layout(
        xaxis_title="Test sessions",
        yaxis_title="Train sessions",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(matrix_fig, width="stretch")
    st.dataframe(wfa_matrix, width="stretch", hide_index=True)

st.divider()
st.subheader("MAE/MFE excursion analytics")
st.caption(
    "Diagnostic only — calibrates from completed-trade bar-level excursions, not intrabar path order."
)

instrument_for_excursions = st.session_state.get("instrument", "ES")
inst_for_excursions = INSTRUMENTS.get(instrument_for_excursions)
excursion_tick_size = inst_for_excursions.tick_size if inst_for_excursions else 0.25
excursion_exchange_tz = st.session_state.get("exchange_timezone") or "America/New_York"

try:
    excursion_trades = add_time_buckets(
        trades_raw,
        exchange_tz=excursion_exchange_tz,
        bucket_tz=excursion_exchange_tz,
        session_tz=excursion_exchange_tz,
    )
except (AttributeError, TypeError, ValueError):
    excursion_trades = trades_raw.copy()

available_group_cols = [
    col
    for col in (
        "direction",
        "trigger",
        "trigger_variant",
        "level_source_mode",
        "entry_rth_segment",
        "entry_hour_bucket",
    )
    if col in excursion_trades.columns
]
default_group_cols = [col for col in ("direction", "trigger") if col in available_group_cols]

ec1, ec2, ec3 = st.columns(3)
excursion_group_cols = ec1.multiselect(
    "Excursion grouping",
    options=available_group_cols,
    default=default_group_cols,
    help="Existing trade columns used for grouped MAE/MFE distributions.",
)
excursion_min_trades = int(
    ec2.number_input(
        "Excursion min trades",
        min_value=1,
        max_value=100_000,
        value=10,
        step=1,
        help="Groups below this count are flagged with sample_warning.",
    )
)
excursion_both_hit_rule = ec3.selectbox(
    "Calibration both-hit rule",
    options=["stop_first", "target_first", "exclude_ambiguous"],
    index=0,
    help="How to classify trades whose terminal MAE and MFE both reach a candidate SL/TP pair.",
)

gr1, gr2, gr3 = st.columns(3)
stop_r_start = float(
    gr1.number_input("Stop R start", min_value=0.1, max_value=20.0, value=0.5, step=0.25)
)
stop_r_stop = float(
    gr2.number_input("Stop R stop", min_value=0.1, max_value=20.0, value=1.5, step=0.25)
)
stop_r_step = float(
    gr3.number_input("Stop R step", min_value=0.1, max_value=5.0, value=0.25, step=0.25)
)

tg1, tg2, tg3 = st.columns(3)
target_r_start = float(
    tg1.number_input("Target R start", min_value=0.1, max_value=50.0, value=0.5, step=0.25)
)
target_r_stop = float(
    tg2.number_input("Target R stop", min_value=0.1, max_value=50.0, value=3.0, step=0.25)
)
target_r_step = float(
    tg3.number_input("Target R step", min_value=0.1, max_value=10.0, value=0.5, step=0.25)
)

stop_r_values = [
    round(v, 10)
    for v in np.arange(stop_r_start, stop_r_stop + stop_r_step * 0.5, stop_r_step).tolist()
    if v > 0
]
target_r_values = [
    round(v, 10)
    for v in np.arange(target_r_start, target_r_stop + target_r_step * 0.5, target_r_step).tolist()
    if v > 0
]

if st.button("▶ Run excursion analytics", type="secondary"):
    if not stop_r_values or not target_r_values:
        st.error("Stop/target R grids are empty; adjust the ranges.")
    else:
        with st.spinner("Computing MAE/MFE excursion diagnostics…"):
            exc_summary = excursion_summary(
                excursion_trades,
                excursion_tick_size,
                group_cols=excursion_group_cols,
                stop_r_grid=stop_r_values,
                target_r_grid=target_r_values,
                both_hit_rule=excursion_both_hit_rule,
                min_trades=excursion_min_trades,
            )
            st.session_state["excursion_summary"] = exc_summary
            st.session_state["excursion_grouped_summary"] = pd.DataFrame(exc_summary["grouped"])
            st.session_state["excursion_calibration_grid"] = pd.DataFrame(
                exc_summary["calibration_grid"]
            )
            st.session_state["excursion_quadrant_summary"] = pd.DataFrame(exc_summary["quadrants"])
            st.session_state["excursion_config"] = exc_summary["config"]
        st.success("Excursion analytics complete.")

exc_summary = st.session_state.get("excursion_summary")
if isinstance(exc_summary, dict) and exc_summary.get("available"):
    edge = exc_summary.get("edge_ratio", {})
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Trades with excursions", exc_summary.get("trade_count", 0))
    e2.metric("Mean MAE (R)", _fmt_value(edge.get("mean_mae_r")))
    e3.metric("Mean MFE (R)", _fmt_value(edge.get("mean_mfe_r")))
    e4.metric("Mean edge ratio", _fmt_value(edge.get("mean_edge_ratio_r")))

    st.caption(exc_summary.get("caveat", ""))

    normalized_excursions = add_excursion_r_columns(excursion_trades, excursion_tick_size)
    if not normalized_excursions.empty and {"mae_r", "mfe_r"}.issubset(
        normalized_excursions.columns
    ):
        fig_exc = go.Figure()
        fig_exc.add_trace(
            go.Scatter(
                x=normalized_excursions["mae_r"],
                y=normalized_excursions["mfe_r"],
                mode="markers",
                marker=dict(color="steelblue", opacity=0.65),
                text=normalized_excursions.get("trade_id"),
                name="Trades",
            )
        )
        fig_exc.add_hline(y=1.0, line_dash="dash", line_color="gray")
        fig_exc.add_vline(x=1.0, line_dash="dash", line_color="gray")
        fig_exc.update_layout(
            xaxis_title="MAE (R)",
            yaxis_title="MFE (R)",
            height=360,
            margin=dict(l=10, r=10, t=30, b=10),
            showlegend=False,
        )
        st.plotly_chart(fig_exc, width="stretch")

    grouped_exc = st.session_state.get("excursion_grouped_summary")
    if isinstance(grouped_exc, pd.DataFrame) and not grouped_exc.empty:
        st.markdown("**Grouped MAE/MFE distributions**")
        st.dataframe(grouped_exc, width="stretch", hide_index=True)

    quadrant_exc = st.session_state.get("excursion_quadrant_summary")
    if isinstance(quadrant_exc, pd.DataFrame) and not quadrant_exc.empty:
        st.markdown("**MAE×MFE quadrant counts**")
        st.dataframe(quadrant_exc, width="stretch", hide_index=True)

    calibration_exc = st.session_state.get("excursion_calibration_grid")
    if isinstance(calibration_exc, pd.DataFrame) and not calibration_exc.empty:
        st.markdown("**Counterfactual SL/TP hit-probability grid**")
        heat = calibration_exc.pivot(
            index="stop_r", columns="target_r", values="target_hit_probability"
        )
        fig_cal = go.Figure(
            data=go.Heatmap(
                z=heat.values,
                x=[str(c) for c in heat.columns],
                y=[str(i) for i in heat.index],
                colorscale="Blues",
                zmin=0,
                zmax=1,
                colorbar=dict(title="P(target)"),
            )
        )
        fig_cal.update_layout(
            xaxis_title="Target distance (R)",
            yaxis_title="Stop distance (R)",
            height=360,
            margin=dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig_cal, width="stretch")
        st.dataframe(calibration_exc, width="stretch", hide_index=True)
else:
    st.info("Run excursion analytics to inspect MAE/MFE distributions and SL/TP calibration.")

st.divider()
st.subheader("Monte Carlo path robustness")
st.caption(
    "Diagnostic only — resamples the realized R sequence; no trade re-simulation is performed."
)

mc_col1, mc_col2, mc_col3 = st.columns(3)
mc_methods = mc_col1.multiselect(
    "Monte Carlo methods",
    options=["reshuffle", "skip", "block_resample"],
    default=["reshuffle", "skip", "block_resample"],
    help="Reshuffle tests order risk; skip tests missed fills; block resample preserves local streaks.",
)
mc_n_simulations = int(
    mc_col2.number_input(
        "MC simulations",
        min_value=100,
        max_value=10_000,
        value=2000,
        step=100,
        help="Number of simulated paths per selected method.",
    )
)
mc_seed = int(
    mc_col3.number_input(
        "MC random seed",
        min_value=0,
        max_value=99_999,
        value=random_seed,
        step=1,
        help="Seed for deterministic Monte Carlo paths.",
    )
)

mc_col4, mc_col5, mc_col6 = st.columns(3)
mc_skip_fraction = float(
    mc_col4.slider(
        "Skip fraction",
        min_value=0.0,
        max_value=0.75,
        value=0.10,
        step=0.05,
        help="Fraction of trades randomly missed in the skip simulation.",
    )
)
mc_block_length_input = int(
    mc_col5.number_input(
        "Block length (0 = sqrt(n))",
        min_value=0,
        max_value=1_000,
        value=0,
        step=1,
        help="Fixed circular block length for block resampling. 0 uses sqrt(trade_count).",
    )
)
mc_drawdown_threshold_text = mc_col6.text_input(
    "Drawdown thresholds (R)",
    value="3,5,10",
    help="Comma-separated max-drawdown thresholds for probability estimates.",
)


def _parse_thresholds(text: str) -> list[float]:
    thresholds: list[float] = []
    for part in str(text).split(","):
        try:
            value = float(part.strip())
        except ValueError:
            continue
        if value > 0:
            thresholds.append(value)
    return sorted(dict.fromkeys(thresholds)) or [3.0, 5.0, 10.0]


if st.button("▶ Run Monte Carlo", type="secondary"):
    if not mc_methods:
        st.error("Select at least one Monte Carlo method.")
    else:
        with st.spinner("Running Monte Carlo path diagnostics…"):
            mc_summary = monte_carlo_summary(
                trades_raw,
                methods=mc_methods,
                n_simulations=mc_n_simulations,
                skip_fraction=mc_skip_fraction,
                block_length=None if mc_block_length_input == 0 else mc_block_length_input,
                drawdown_thresholds_r=_parse_thresholds(mc_drawdown_threshold_text),
                random_state=mc_seed,
            )
            st.session_state["monte_carlo_summary"] = mc_summary
            st.session_state["monte_carlo_config"] = mc_summary["config"]
        st.success("Monte Carlo diagnostics complete.")

mc_summary = st.session_state.get("monte_carlo_summary")
if isinstance(mc_summary, dict) and mc_summary.get("available"):
    st.caption(mc_summary.get("caveat", ""))
    mc_methods_result = mc_summary.get("methods", {})
    method_labels = {
        "reshuffle": "Reshuffle",
        "skip": "Skip",
        "block_resample": "Block resample",
    }
    for method_name, result in mc_methods_result.items():
        st.markdown(f"**{method_labels.get(method_name, method_name)}**")
        observed = result.get("observed", {})
        simulated = result.get("simulated", {})
        final_r = simulated.get("final_r", {})
        max_dd = simulated.get("max_drawdown_r", {})
        loss_streak = simulated.get("max_loss_streak", {})
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Observed final R", _fmt_value(observed.get("final_r")))
        m2.metric("P50 final R", _fmt_value(final_r.get("p50")))
        m3.metric("P95 max DD (R)", _fmt_value(max_dd.get("p95")))
        m4.metric("P95 loss streak", _fmt_value(loss_streak.get("p95"), ".0f"))

        dd_probs = pd.DataFrame(result.get("probability_drawdown_exceeds", []))
        if not dd_probs.empty:
            st.dataframe(dd_probs, width="stretch", hide_index=True)

        fan = result.get("equity_fan", {})
        if isinstance(fan, dict) and fan.get("trade_index"):
            fig_fan = go.Figure()
            if "p05" in fan and "p95" in fan:
                fig_fan.add_trace(
                    go.Scatter(
                        x=fan["trade_index"],
                        y=fan["p95"],
                        line=dict(width=0),
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )
                fig_fan.add_trace(
                    go.Scatter(
                        x=fan["trade_index"],
                        y=fan["p05"],
                        fill="tonexty",
                        fillcolor="rgba(70, 130, 180, 0.20)",
                        line=dict(width=0),
                        name="P05-P95 band",
                    )
                )
            if "p50" in fan:
                fig_fan.add_trace(
                    go.Scatter(
                        x=fan["trade_index"],
                        y=fan["p50"],
                        mode="lines",
                        name="P50 simulated",
                        line=dict(color="steelblue", dash="dash"),
                    )
                )
            fig_fan.add_trace(
                go.Scatter(
                    x=fan["trade_index"],
                    y=fan["observed_cum_r"],
                    mode="lines+markers",
                    name="Observed",
                    line=dict(color="orange"),
                )
            )
            fig_fan.update_layout(
                xaxis_title="Trade index",
                yaxis_title="Cumulative R",
                height=360,
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig_fan, width="stretch")
else:
    st.info("Run Monte Carlo diagnostics to inspect path risk and drawdown probabilities.")

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
status_emoji = {"insufficient": "🔴", "limited": "🟡", "reasonable": "🟢"}.get(tc["status"], "⚪")
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
    st.markdown(f"{risk_emoji} **Risk: {go_diag['risk_level'].upper()}** — {go_diag['message']}")

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

st.divider()

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
_source_for_otf = st.session_state.get("levels") or st.session_state.get("data")

if _signals_for_otf is None or (hasattr(_signals_for_otf, "empty") and _signals_for_otf.empty):
    st.info("No signals found in session state.  Generate signals before running OTF validation.")
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

    st.caption(
        f"Using SL={_sl_ticks} ticks, TP={_tp_ticks} ticks, "
        f"session timezone={_session_tz}, "
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
                    execution_kwargs={
                        "commission_per_side": float(
                            _backtest_exec.get("commission_per_side", 0.0) or 0.0
                        ),
                        "slippage_ticks": float(_backtest_exec.get("slippage_ticks", 0.0) or 0.0),
                    },
                )
                st.session_state["otf_validation_matrix"] = _otf_matrix_result
                st.session_state["otf_validation_config"] = {
                    "train_fraction": _train_fraction,
                    "oos_fraction": round(1 - _train_fraction, 10),
                    "sl_ticks": float(_sl_ticks),
                    "tp_ticks": float(_tp_ticks),
                    "session_timezone": _session_tz,
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
                    _selected_rows.iloc[0]["oos_expectancy_r"] if not _selected_rows.empty else None
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
                f"🏆 **Train-selected configuration:** `{_selected_label}` "
                f"(selected by train_expectancy_r only). "
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
