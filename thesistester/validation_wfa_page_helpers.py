"""Classic Validation WFA/OTF persist + WFA display (QR D-4 / QI-05-02).

Streamlit-free: callers pass ``st``. Session keys and M9/M10 copy unchanged.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from thesistester.analytics import run_walk_forward_sl_tp, run_wfa_matrix
from thesistester.config import INSTRUMENTS
from thesistester.validation_page_helpers import (
    fmt_value as _fmt_value,
    parse_positive_int_values as _parse_positive_int_values,
)


def render_wfa_otf_diagnostics(st: Any, *, validation_ew: dict[str, Any]) -> None:
    """Walk-forward / OOS persist + display. Session keys unchanged."""
    _validation_ew = validation_ew
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
                format_func=lambda value: (
                    "Bars (legacy)" if value == "bars" else "Trading sessions"
                ),
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
                train_sessions = int(
                    c1.number_input("Train sessions", min_value=1, value=5, step=1)
                )
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
                help=(
                    "Reject withholds stitched equity when OOS windows overlap. "
                    "`aggregate_test_total_r` is a fold-sum of `test_total_r` and can "
                    "double-count overlapping OOS trades. first/last assign overlapping "
                    "stitch trades to one fold; they do not change the fold-sum."
                ),
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

            c4, c5, c6 = st.columns(3)
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
            wfo_otf_history_policy = c6.selectbox(
                "OTF history policy",
                options=["fold_local", "causal_prefix"],
                index=0,
                help=(
                    "fold_local (default): OTF uses only each fold’s OHLCV. "
                    "causal_prefix: prior bars before the fold start may establish OTF state; "
                    "only fold-local signals are scored. Never uses future bars."
                ),
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
                    gc1.number_input(
                        "SL start", min_value=1.0, max_value=500.0, value=4.0, step=1.0
                    )
                )
                sl_stop = float(
                    gc2.number_input(
                        "SL stop", min_value=1.0, max_value=500.0, value=20.0, step=1.0
                    )
                )
                sl_step = float(
                    gc3.number_input("SL step", min_value=1.0, max_value=100.0, value=4.0, step=1.0)
                )
                gc4, gc5, gc6 = st.columns(3)
                tp_start = float(
                    gc4.number_input(
                        "TP start", min_value=1.0, max_value=1000.0, value=8.0, step=1.0
                    )
                )
                tp_stop = float(
                    gc5.number_input(
                        "TP stop", min_value=1.0, max_value=1000.0, value=40.0, step=1.0
                    )
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
                                    slippage_ticks=float(
                                        grid_costs.get("slippage_ticks", 0.0) or 0.0
                                    ),
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
                                        exposure_policy_state.get("cooldown_bars_after_exit", 0)
                                        or 0
                                    ),
                                    otf_config=_wfo_otf_config,
                                    otf_history_policy=wfo_otf_history_policy,
                                    intrabar_model=str(
                                        intrabar_policy.get("intrabar_model", "sl_first")
                                    ),
                                    subtimeframe_data=st.session_state.get("subtimeframe_data"),
                                    parent_interval=st.session_state.get("base_interval"),
                                    sub_interval=st.session_state.get("subtimeframe_interval"),
                                    breakeven_after_r_values=exit_management_policy.get(
                                        "breakeven_after_r_values", [None]
                                    ),
                                    trailing_after_r_values=exit_management_policy.get(
                                        "trailing_after_r_values", [None]
                                    ),
                                    trailing_distance_ticks_values=exit_management_policy.get(
                                        "trailing_distance_ticks_values", [None]
                                    ),
                                    max_grid_cells=int(
                                        exit_management_policy.get("max_grid_cells", 500)
                                    ),
                                    fold_mode=fold_mode,
                                    window_mode=window_mode,
                                    train_sessions=train_sessions,
                                    test_sessions=test_sessions,
                                    step_sessions=step_sessions,
                                    exchange_timezone=(
                                        st.session_state.get("exchange_timezone")
                                        or "America/New_York"
                                    ),
                                    eth_start=(inst.eth_start if inst else "18:00"),
                                    overlap_policy=overlap_policy,
                                    return_result=True,
                                    entry_window=_validation_ew["entry_window"],
                                    entry_window_exchange_tz=_validation_ew[
                                        "entry_window_exchange_tz"
                                    ],
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
                                    "step_bars": int(
                                        step_bars if step_bars is not None else test_bars
                                    ),
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
                                    "no_new_entries_after": session_policy.get(
                                        "no_new_entries_after"
                                    ),
                                    "exposure_policy": str(
                                        exposure_policy_state.get("exposure_policy", "allow_all")
                                    ),
                                    "cooldown_bars_after_exit": int(
                                        exposure_policy_state.get("cooldown_bars_after_exit", 0)
                                        or 0
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
                                    "otf_history_policy": wfo_otf_history_policy,
                                    "entry_window_enabled": bool(_validation_ew["enabled"]),
                                    "entry_window_label": _validation_ew["label"],
                                }
                                st.session_state["walk_forward_results"] = results_df
                                st.session_state["walk_forward_summary"] = wfo_summary
                                st.session_state["walk_forward_config"] = wfo_config
                                st.session_state["walk_forward_oos_trades"] = (
                                    detailed_wfo.oos_trades
                                )
                                st.session_state["walk_forward_stitched_equity"] = (
                                    detailed_wfo.stitched_equity
                                )
                                st.session_state["walk_forward_warnings"] = list(
                                    detailed_wfo.warnings
                                )
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
                                        test_session_values=_parse_positive_int_values(
                                            matrix_test_raw
                                        ),
                                        window_mode=window_mode,
                                        exchange_timezone=(
                                            st.session_state.get("exchange_timezone")
                                            or "America/New_York"
                                        ),
                                        eth_start=(inst.eth_start if inst else "18:00"),
                                        ranking_metric=wfo_ranking_metric,
                                        min_train_trades=wfo_min_train_trades,
                                        max_holding_bars=None,
                                        allow_same_bar_exit=True,
                                        commission_per_side=float(
                                            grid_costs.get("commission_per_side", 0.0) or 0.0
                                        ),
                                        slippage_ticks=float(
                                            grid_costs.get("slippage_ticks", 0.0) or 0.0
                                        ),
                                        flat_by_session_close=bool(
                                            session_policy.get("flat_by_session_close", False)
                                        ),
                                        session_close_time=session_policy.get("session_close_time"),
                                        session_timezone=session_policy.get("session_timezone"),
                                        no_new_entries_after=session_policy.get(
                                            "no_new_entries_after"
                                        ),
                                        exposure_policy=str(
                                            exposure_policy_state.get(
                                                "exposure_policy", "allow_all"
                                            )
                                        ),
                                        cooldown_bars_after_exit=int(
                                            exposure_policy_state.get("cooldown_bars_after_exit", 0)
                                            or 0
                                        ),
                                        otf_config=_wfo_otf_config,
                                        otf_history_policy=wfo_otf_history_policy,
                                        intrabar_model=str(
                                            intrabar_policy.get("intrabar_model", "sl_first")
                                        ),
                                        subtimeframe_data=st.session_state.get("subtimeframe_data"),
                                        parent_interval=st.session_state.get("base_interval"),
                                        sub_interval=st.session_state.get("subtimeframe_interval"),
                                        breakeven_after_r_values=exit_management_policy.get(
                                            "breakeven_after_r_values", [None]
                                        ),
                                        trailing_after_r_values=exit_management_policy.get(
                                            "trailing_after_r_values", [None]
                                        ),
                                        trailing_distance_ticks_values=exit_management_policy.get(
                                            "trailing_distance_ticks_values", [None]
                                        ),
                                        max_grid_cells=int(
                                            exit_management_policy.get("max_grid_cells", 500)
                                        ),
                                        overlap_policy=overlap_policy,
                                        entry_window=_validation_ew["entry_window"],
                                        entry_window_exchange_tz=_validation_ew[
                                            "entry_window_exchange_tz"
                                        ],
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
                                        "otf_history_policy": wfo_otf_history_policy,
                                    }
                                else:
                                    st.session_state.pop("wfa_matrix", None)
                                    st.session_state.pop("wfa_matrix_config", None)
                                # Store OTF summary for reporting. Timezone must match
                                # fold-level OTF resolution (session-exit tz, else exchange).
                                from thesistester.analytics.walk_forward import (
                                    resolve_otf_session_timezone,
                                )
                                from thesistester.persistence.local_store import (
                                    compute_otf_config_hash,
                                )
                                from thesistester.engine.otf import OTF_ALGORITHM_VERSION

                                _wfo_exchange_tz = (
                                    st.session_state.get("exchange_timezone") or "America/New_York"
                                )
                                _wfo_session_tz = resolve_otf_session_timezone(
                                    session_policy.get("session_timezone"),
                                    _wfo_exchange_tz,
                                )
                                _wfo_eth_start = inst.eth_start if inst else "18:00"
                                st.session_state["walk_forward_otf_filter"] = {
                                    "otf_filter_enabled": _wfo_otf_enabled,
                                    "otf_filter_config": _wfo_otf_config,
                                    "otf_algorithm_version": OTF_ALGORITHM_VERSION,
                                    "otf_config_hash": compute_otf_config_hash(_wfo_otf_config),
                                    "session_timezone": _wfo_session_tz,
                                    "eth_start": _wfo_eth_start,
                                    "otf_history_policy": wfo_otf_history_policy,
                                }
                                st.success("Walk-forward diagnostics complete.")

    wfo_results = st.session_state.get("walk_forward_results")
    wfo_summary = st.session_state.get("walk_forward_summary")
    if isinstance(wfo_summary, dict):
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Folds", wfo_summary.get("fold_count", 0))
        s2.metric("Valid OOS folds", wfo_summary.get("valid_fold_count", 0))
        s3.metric(
            "OOS profitable rate", _fmt_value(wfo_summary.get("oos_profitable_fold_rate"), ".1%")
        )
        s4.metric("Median test expectancy", _fmt_value(wfo_summary.get("median_test_expectancy_r")))
        a1, _ = st.columns(2)
        a1.metric(
            "Aggregate test total R",
            _fmt_value(wfo_summary.get("aggregate_test_total_r")),
        )
        st.caption(
            "`aggregate_test_total_r` is a fold-sum of per-fold `test_total_r`. "
            "Overlapping OOS windows can double-count the same trade R. "
            "`reject` withholds stitched equity; it does not deduplicate this sum (M9)."
        )
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
        st.caption(
            "Diagnostic robustness surface — do not pick the greenest cell as a "
            "production train/test length (M10)."
        )
        st.dataframe(wfa_matrix, width="stretch", hide_index=True)
