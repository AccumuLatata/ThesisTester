"""Classic Validation batteries persist/display (QR D-4 / QI-05-02).

Streamlit-free: callers pass ``st``. Battery session keys unchanged.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from thesistester.analytics import (
    add_excursion_r_columns,
    add_time_buckets,
    excursion_summary,
    monte_carlo_summary,
    overfitting_summary,
    best_grid_result,
    grid_trade_sequences,
)
from thesistester.api import run_noise_test, run_sensitivity_profile
from thesistester.config import INSTRUMENTS
from thesistester.validation_page_helpers import fmt_value as _fmt_value


def render_validation_batteries(
    st: Any,
    *,
    trades_raw: Any,
    grid_raw: Any,
    validation_ew: dict[str, Any],
    random_seed: int,
) -> None:
    """Overfitting / noise / sensitivity / excursion / Monte Carlo blocks."""
    _validation_ew = validation_ew
    st.divider()
    st.subheader("Overfitting-detection battery")
    st.caption(
        "Diagnostic only — CSCV/PBO, DSR, and vs-random quantify specified historical "
        "selection risks; they do not prove a future edge."
    )
    if grid_raw is None or grid_raw.empty:
        st.info("Run Grid Search first. This battery needs multiple grid cells.")
    else:
        r15c1, r15c2, r15c3 = st.columns(3)
        r15_partitions = int(
            r15c1.number_input(
                "CSCV partitions",
                min_value=4,
                max_value=12,
                value=4,
                step=2,
                help="Even contiguous trade-sequence partitions.",
            )
        )
        r15_random_replicas = int(
            r15c2.number_input(
                "Vs-random replicas",
                min_value=10,
                max_value=2_000,
                value=100,
                step=10,
            )
        )
        r15_min_trades = int(
            r15c3.number_input(
                "Min trades per cell",
                min_value=1,
                max_value=1_000,
                value=1,
                step=1,
            )
        )
        st.warning(
            f"Cost estimate: {len(grid_raw)} grid replays + {r15_random_replicas} "
            "random-entry replays. This is opt-in and can be computationally expensive."
        )
        if st.button("▶ Run overfitting battery", type="secondary"):
            instrument_r15 = st.session_state.get("instrument", "ES")
            inst_r15 = INSTRUMENTS.get(instrument_r15)
            data_r15 = st.session_state.get("levels")
            if data_r15 is None or data_r15.empty:
                data_r15 = st.session_state.get("data")
            signals_r15 = st.session_state.get("grid_accepted_signals")
            if signals_r15 is None or signals_r15.empty:
                signals_r15 = st.session_state.get("signals")
            if data_r15 is None or signals_r15 is None or inst_r15 is None:
                st.error("Data, signals, and a supported instrument are required.")
            else:
                backtest_costs = (
                    st.session_state.get("grid_execution_costs")
                    or st.session_state.get("backtest_execution_costs")
                    or {}
                )
                backtest_policy = (
                    st.session_state.get("grid_session_exit_policy")
                    or st.session_state.get("backtest_session_exit_policy")
                    or {}
                )
                exposure = (
                    st.session_state.get("grid_exposure_policy")
                    or st.session_state.get("exposure_policy")
                    or {}
                )
                execution_r15 = {
                    "commission_per_side": float(backtest_costs.get("commission_per_side", 0.0)),
                    "slippage_ticks": float(backtest_costs.get("slippage_ticks", 0.0)),
                    "flat_by_session_close": bool(
                        backtest_policy.get("flat_by_session_close", False)
                    ),
                    "session_close_time": backtest_policy.get("session_close_time"),
                    "session_timezone": backtest_policy.get("session_timezone"),
                    "no_new_entries_after": backtest_policy.get("no_new_entries_after"),
                    "exposure_policy": exposure.get("exposure_policy", "allow_all"),
                    "cooldown_bars_after_exit": int(
                        exposure.get("cooldown_bars_after_exit", 0) or 0
                    ),
                    "intrabar_model": (
                        st.session_state.get("grid_intrabar_policy")
                        or st.session_state.get("backtest_intrabar_policy")
                        or {}
                    ).get("intrabar_model", "sl_first"),
                    "subtimeframe_data": st.session_state.get("subtimeframe_data"),
                    "parent_interval": st.session_state.get("base_interval"),
                    "sub_interval": st.session_state.get("subtimeframe_interval"),
                    "entry_window": _validation_ew["entry_window"],
                    "entry_window_exchange_tz": _validation_ew["entry_window_exchange_tz"],
                }
                grid_context_r15 = st.session_state.get("grid_execution_context") or {}
                with st.spinner("Running CSCV/PBO, DSR, and vs-random diagnostics…"):
                    sequences = grid_trade_sequences(
                        data_r15,
                        signals_r15,
                        tick_size=inst_r15.tick_size,
                        point_value=inst_r15.point_value,
                        grid=grid_raw,
                        execution_kwargs=execution_r15,
                    )
                    selection_metric = grid_context_r15.get("ranking_metric", "expectancy_r")
                    selection_min_trades = int(grid_context_r15.get("min_trades", 1))
                    eligible_sequences = sequences.grid_results[
                        sequences.grid_results["trade_count"] >= selection_min_trades
                    ].dropna(subset=[selection_metric])
                    if grid_context_r15.get("directional_ranking_enabled", False):
                        eligible_sequences = eligible_sequences[
                            eligible_sequences["long_trade_count"]
                            >= int(grid_context_r15.get("min_long_trades", 1))
                        ]
                        eligible_sequences = eligible_sequences[
                            eligible_sequences["short_trade_count"]
                            >= int(grid_context_r15.get("min_short_trades", 1))
                        ]
                    if eligible_sequences.empty:
                        st.error("No grid cell passes the recorded selection rule.")
                        st.stop()
                    selected = best_grid_result(
                        eligible_sequences,
                        metric=selection_metric,
                        min_trades=selection_min_trades,
                    )
                    if selected is None:
                        st.error("No grid cell passes the recorded selection rule.")
                        st.stop()
                    key = (
                        float(selected["stop_loss_ticks"]),
                        float(selected["take_profit_ticks"]),
                        None
                        if pd.isna(selected.get("breakeven_after_r"))
                        else float(selected.get("breakeven_after_r")),
                        None
                        if pd.isna(selected.get("trailing_after_r"))
                        else float(selected.get("trailing_after_r")),
                        None
                        if pd.isna(selected.get("trailing_distance_ticks"))
                        else float(selected.get("trailing_distance_ticks")),
                    )
                    summary_r15 = overfitting_summary(
                        selected_trades=sequences.cell_trades[key],
                        cell_trades=sequences.cell_trades,
                        grid_results=sequences.grid_results,
                        df=data_r15,
                        tick_size=inst_r15.tick_size,
                        point_value=inst_r15.point_value,
                        execution_kwargs=execution_r15,
                        selected_grid_metric=selection_metric,
                        selected_min_trades=selection_min_trades,
                        pbo_partitions=r15_partitions,
                        pbo_min_trades=r15_min_trades,
                        vs_random_n_replicas=r15_random_replicas,
                        random_state=random_seed,
                    )
                st.session_state["overfitting_summary"] = summary_r15
                st.session_state["overfitting_config"] = summary_r15["config"]
                st.success("Overfitting battery complete.")
    overfit_summary = st.session_state.get("overfitting_summary")
    if isinstance(overfit_summary, dict):
        pbo = overfit_summary.get("pbo") or {}
        dsr = overfit_summary.get("deflated_sharpe") or {}
        random_benchmark = overfit_summary.get("vs_random") or {}
        oc1, oc2, oc3 = st.columns(3)
        oc1.metric("PBO", _fmt_value(pbo.get("pbo"), ".1%"))
        oc2.metric("Deflated Sharpe probability", _fmt_value(dsr.get("dsr"), ".1%"))
        oc3.metric(
            "Vs-random p-value", _fmt_value(random_benchmark.get("p_value_greater_or_equal"), ".4f")
        )
        st.caption(overfit_summary.get("caveat", ""))
        split_rows = pbo.get("split_results", [])
        if split_rows:
            st.dataframe(pd.DataFrame(split_rows), width="stretch", hide_index=True)

    st.divider()
    st.subheader("Price-series noise test")
    st.caption(
        "Diagnostic only — perturbs parent OHLC bars, then recomputes levels, signals, and trades. "
        "It measures local input sensitivity, not future edge."
    )
    noise_data = st.session_state.get("data")
    noise_setup = st.session_state.get("setup_config") or st.session_state.get("last_signal_setup")
    if (
        not isinstance(noise_data, pd.DataFrame)
        or noise_data.empty
        or not isinstance(noise_setup, dict)
    ):
        st.info("Noise test requires the loaded OHLC dataset and a saved setup configuration.")
    else:
        n1, n2, n3, n4 = st.columns(4)
        noise_replicas = int(
            n1.number_input("Noise replicas", min_value=5, max_value=1_000, value=100, step=5)
        )
        noise_fraction = float(
            n2.slider(
                "Noise fraction",
                min_value=0.005,
                max_value=0.25,
                value=0.05,
                step=0.005,
                help="Symmetric OHLC noise as a fraction of rolling ATR or bar range.",
            )
        )
        noise_basis = n3.selectbox("Noise scale", options=["atr", "range"])
        noise_atr_period = int(
            n4.number_input("ATR period", min_value=1, max_value=200, value=14, step=1)
        )
        st.warning(
            f"Cost estimate: {noise_replicas} complete levels → signals → backtest replays. "
            "This noise test is opt-in; 1,000 replicas can be expensive on long datasets."
        )
        if st.button("▶ Run noise test", type="secondary"):
            backtest_policy_noise = st.session_state.get("backtest_session_exit_policy") or {}
            backtest_costs_noise = st.session_state.get("backtest_execution_costs") or {}
            exposure_noise = st.session_state.get("exposure_policy") or {}
            intrabar_noise = st.session_state.get("backtest_intrabar_policy") or {}
            exit_noise = st.session_state.get("backtest_exit_management_policy") or {}
            try:
                with st.spinner("Running full-pipeline OHLC noise replicas…"):
                    noise_result = run_noise_test(
                        noise_data,
                        trades_raw,
                        instrument=st.session_state.get("instrument", "ES"),
                        levels_config=st.session_state.get("levels_settings"),
                        setup_config=noise_setup,
                        backtest_config={
                            "stop_loss_ticks": float(
                                st.session_state.get("backtest_sl_ticks", 8.0)
                            ),
                            "take_profit_ticks": float(
                                st.session_state.get("backtest_tp_ticks", 16.0)
                            ),
                            "max_holding_bars": (
                                int(st.session_state["backtest_max_bars"])
                                if st.session_state.get("backtest_use_max_bars")
                                else None
                            ),
                            "allow_same_bar_exit": bool(
                                st.session_state.get("backtest_allow_same_bar", True)
                            ),
                            "commission_per_side": float(
                                backtest_costs_noise.get("commission_per_side", 0.0)
                            ),
                            "slippage_ticks": float(
                                backtest_costs_noise.get("slippage_ticks", 0.0)
                            ),
                            "flat_by_session_close": bool(
                                backtest_policy_noise.get("flat_by_session_close", False)
                            ),
                            "session_close_time": backtest_policy_noise.get("session_close_time"),
                            "session_timezone": backtest_policy_noise.get("session_timezone"),
                            "no_new_entries_after": backtest_policy_noise.get(
                                "no_new_entries_after"
                            ),
                            "exposure_policy": exposure_noise.get("exposure_policy", "allow_all"),
                            "cooldown_bars_after_exit": int(
                                exposure_noise.get("cooldown_bars_after_exit", 0) or 0
                            ),
                            "intrabar_model": intrabar_noise.get("intrabar_model", "sl_first"),
                            "breakeven_after_r": exit_noise.get("breakeven_after_r"),
                            "trailing_after_r": exit_noise.get("trailing_after_r"),
                            "trailing_distance_ticks": exit_noise.get("trailing_distance_ticks"),
                            "entry_window": _validation_ew["entry_window_normalized"]
                            if _validation_ew["enabled"]
                            else None,
                        },
                        noise_config={
                            "n_replicas": noise_replicas,
                            "noise_fraction": noise_fraction,
                            "scale_basis": noise_basis,
                            "atr_period": noise_atr_period,
                            "random_state": random_seed,
                        },
                        subtimeframe_data=st.session_state.get("subtimeframe_data"),
                        parent_interval=st.session_state.get("base_interval"),
                        sub_interval=st.session_state.get("subtimeframe_interval"),
                    )
                st.session_state["noise_summary"] = noise_result
                st.session_state["noise_config"] = noise_result["config"]
                st.success("Noise test complete.")
            except ValueError as exc:
                st.error(str(exc))
    noise_result = st.session_state.get("noise_summary")
    if isinstance(noise_result, dict) and noise_result.get("available"):
        noise_replicas_result = noise_result.get("replicas") or {}
        nr1, nr2, nr3 = st.columns(3)
        nr1.metric(
            "P50 expectancy R",
            _fmt_value((noise_replicas_result.get("expectancy_r") or {}).get("p50")),
        )
        nr2.metric(
            "P50 profit factor",
            _fmt_value((noise_replicas_result.get("profit_factor") or {}).get("p50")),
        )
        nr3.metric(
            "P50 trade persistence",
            _fmt_value(
                (noise_replicas_result.get("trade_persistence_rate") or {}).get("p50"),
                ".1%",
            ),
        )
        st.caption(noise_result.get("caveat", ""))

    st.divider()
    st.subheader("Parameter sensitivity (one-at-a-time)")
    st.caption(
        "Diagnostic only — changes one selected execution parameter at a time while holding "
        "signals and every other parameter fixed. It measures local flatness, not future edge."
    )
    if grid_raw is None or grid_raw.empty:
        st.info("Run Grid Search first. Sensitivity profiles the selected grid cell.")
    else:
        sensitivity_columns = [
            column
            for column in (
                "stop_loss_ticks",
                "take_profit_ticks",
                "breakeven_after_r",
                "trailing_after_r",
                "trailing_distance_ticks",
            )
            if column in grid_raw and grid_raw[column].notna().any()
        ]
        s1, s2, s3 = st.columns(3)
        sensitivity_fraction = float(
            s1.slider("Perturbation fraction (±)", 0.05, 0.50, 0.20, 0.05, format="%.2f")
        )
        sensitivity_steps = int(
            s2.number_input("Steps per side", min_value=1, max_value=20, value=5, step=1)
        )
        sensitivity_parameters = s3.multiselect(
            "Parameters",
            options=sensitivity_columns,
            default=sensitivity_columns,
        )
        replay_count = len(sensitivity_parameters) * (2 * sensitivity_steps + 1) + 1
        st.warning(
            f"Cost estimate: {replay_count} `simulate_trades` replays. "
            "This sensitivity profile is opt-in and can be computationally expensive; "
            "no parallel acceleration is available."
        )
        if st.button("▶ Run sensitivity profile", type="secondary"):
            instrument_r19 = st.session_state.get("instrument", "ES")
            inst_r19 = INSTRUMENTS.get(instrument_r19)
            data_r19 = st.session_state.get("levels")
            if data_r19 is None or data_r19.empty:
                data_r19 = st.session_state.get("data")
            signals_r19 = st.session_state.get("grid_accepted_signals")
            if signals_r19 is None or signals_r19.empty:
                signals_r19 = st.session_state.get("signals")
            if data_r19 is None or signals_r19 is None or inst_r19 is None:
                st.error("Data, signals, and a supported instrument are required.")
            elif not sensitivity_parameters:
                st.error("Select at least one active numeric grid parameter.")
            else:
                costs_r19 = st.session_state.get("grid_execution_costs") or {}
                policy_r19 = st.session_state.get("grid_session_exit_policy") or {}
                exposure_r19 = st.session_state.get("grid_exposure_policy") or {}
                context_r19 = st.session_state.get("grid_execution_context") or {}
                with st.spinner("Replaying one-at-a-time parameter perturbations…"):
                    summary_r19 = run_sensitivity_profile(
                        data_r19,
                        signals_r19,
                        tick_size=inst_r19.tick_size,
                        point_value=inst_r19.point_value,
                        grid=grid_raw,
                        execution_kwargs={
                            "commission_per_side": float(costs_r19.get("commission_per_side", 0.0)),
                            "slippage_ticks": float(costs_r19.get("slippage_ticks", 0.0)),
                            "flat_by_session_close": bool(
                                policy_r19.get("flat_by_session_close", False)
                            ),
                            "session_close_time": policy_r19.get("session_close_time"),
                            "session_timezone": policy_r19.get("session_timezone"),
                            "no_new_entries_after": policy_r19.get("no_new_entries_after"),
                            "exposure_policy": exposure_r19.get("exposure_policy", "allow_all"),
                            "cooldown_bars_after_exit": int(
                                exposure_r19.get("cooldown_bars_after_exit", 0) or 0
                            ),
                            "intrabar_model": (
                                st.session_state.get("grid_intrabar_policy") or {}
                            ).get("intrabar_model", "sl_first"),
                            "subtimeframe_data": st.session_state.get("subtimeframe_data"),
                            "parent_interval": st.session_state.get("base_interval"),
                            "sub_interval": st.session_state.get("subtimeframe_interval"),
                            "entry_window": _validation_ew["entry_window"],
                            "entry_window_exchange_tz": _validation_ew["entry_window_exchange_tz"],
                        },
                        selected_grid_metric=context_r19.get("ranking_metric", "expectancy_r"),
                        selected_min_trades=int(context_r19.get("min_trades", 1)),
                        sensitivity_config={
                            "perturbation_fraction": sensitivity_fraction,
                            "n_steps_per_side": sensitivity_steps,
                            "parameters": sensitivity_parameters,
                            "random_state": random_seed,
                        },
                    )
                st.session_state["sensitivity_summary"] = summary_r19
                st.session_state["sensitivity_config"] = summary_r19["config"]
                st.success("Sensitivity profile complete.")
    sensitivity_result = st.session_state.get("sensitivity_summary")
    if isinstance(sensitivity_result, dict) and sensitivity_result.get("available"):
        r19a, r19b = st.columns(2)
        r19a.metric("Fragile parameters", sensitivity_result.get("fragile_parameter_count", 0))
        r19b.metric(
            "Baseline expectancy R",
            _fmt_value((sensitivity_result.get("baseline") or {}).get("expectancy_r")),
        )
        st.caption(sensitivity_result.get("caveat", ""))
        for profile in sensitivity_result.get("parameters", []):
            curve = profile.get("curve") or []
            if not curve:
                continue
            curve_frame = pd.DataFrame(curve)
            figure = go.Figure()
            figure.add_trace(
                go.Scatter(
                    x=curve_frame["parameter_value"],
                    y=curve_frame["expectancy_r"],
                    mode="lines+markers",
                    name="Expectancy R",
                )
            )
            figure.add_trace(
                go.Scatter(
                    x=curve_frame["parameter_value"],
                    y=curve_frame["profit_factor"],
                    mode="lines+markers",
                    name="Profit factor",
                    yaxis="y2",
                )
            )
            figure.update_layout(
                title=f"{profile.get('parameter')} — {'fragile' if profile.get('fragile') else 'no sign flip'}",
                xaxis_title="Perturbed parameter value",
                yaxis_title="Expectancy R",
                yaxis2=dict(title="Profit factor", overlaying="y", side="right"),
                margin=dict(l=10, r=10, t=35, b=10),
            )
            st.plotly_chart(figure, width="stretch")
            st.dataframe(curve_frame, width="stretch", hide_index=True)

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
        for v in np.arange(
            target_r_start, target_r_stop + target_r_step * 0.5, target_r_step
        ).tolist()
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
                st.session_state["excursion_quadrant_summary"] = pd.DataFrame(
                    exc_summary["quadrants"]
                )
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
