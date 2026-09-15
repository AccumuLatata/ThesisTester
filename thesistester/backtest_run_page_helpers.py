"""Classic Backtest run/persist (QR D-3 / QI-04-05).

Streamlit-free: callers pass ``st``. H7/H15 call-site Names unchanged.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.analytics import equity_curve, summarize_trades
from thesistester.analytics.entry_window import consume_armed_entry_window_after_run
from thesistester.assistant import AssistantOrchestrator
from thesistester.backtest_page_helpers import (
    assemble_otf_filter_clocks,
    persist_direction_collision_diagnostic,
)
from thesistester.classic_context import get_active_thesis_id
from thesistester.classic_ledger import (
    begin_classic_execution_ledger,
    complete_classic_execution_ledger,
    fail_classic_execution_ledger,
    should_record_all_executions,
)
from thesistester.engine.backtest import simulate_trades
from thesistester.engine.otf_integration import apply_configured_otf_filter
from thesistester.entry_window_policy import normalize_entry_window


def run_and_persist_backtest(
    st: Any,
    *,
    settings: dict[str, Any],
    ohlcv_df: Any,
    signals: Any,
    exchange_tz: str,
    inst: Any,
    tick_size: float,
    point_value: float,
) -> None:
    """Run OTF + simulate + persist. Session key names unchanged."""
    sl_ticks = settings["sl_ticks"]
    tp_ticks = settings["tp_ticks"]
    commission_per_side = settings["commission_per_side"]
    slippage_ticks = settings["slippage_ticks"]
    max_bars = settings["max_bars"]
    allow_same_bar = settings["allow_same_bar"]
    intrabar_model = settings["intrabar_model"]
    subtimeframe_data = settings["subtimeframe_data"]
    breakeven_after_r = settings["breakeven_after_r"]
    trailing_after_r = settings["trailing_after_r"]
    trailing_distance_ticks = settings["trailing_distance_ticks"]
    flat_by_session_close = settings["flat_by_session_close"]
    session_close_time = settings["session_close_time"]
    session_timezone = settings["session_timezone"]
    effective_no_new_entries_after = settings["effective_no_new_entries_after"]
    entry_window_config = settings["entry_window_config"]
    exposure_policy = settings["exposure_policy"]
    cooldown_bars_after_exit = settings["cooldown_bars_after_exit"]
    same_bar_opposite_direction = settings["same_bar_opposite_direction"]

    _ledger_handle = None
    if should_record_all_executions(st.session_state):
        _thesis_id = get_active_thesis_id(st.session_state)
        if not isinstance(_thesis_id, str) or not _thesis_id.strip():
            st.error("all_executions recording requires an active thesis.")
            st.stop()
        try:
            _ledger_handle = begin_classic_execution_ledger(
                AssistantOrchestrator.for_local_workspace(),
                thesis_id=_thesis_id,
                session_state=st.session_state,
                origin_page="backtest",
            )
        except ValueError as exc:
            st.error(f"Thesis ledger could not start before execution: {exc}")
            st.stop()

    with st.spinner("Simulating trades…"):
        # Any post-begin failure must terminalize the ledger (never leave
        # ResearchRun stuck in ``running``). Track phase for fail provenance.
        _ledger_phase = "execution"
        try:
            _ledger_phase = "otf_filter"
            # Apply OTF filter before simulation
            _otf_clocks = assemble_otf_filter_clocks(exchange_tz, inst)
            _otf_result = apply_configured_otf_filter(
                source_df=ohlcv_df,
                candidate_signals=signals,
                setup_config=st.session_state.get("setup_config"),
                session_timezone=exchange_tz,
                eth_start=_otf_clocks["eth_start"],
                signal_settings=st.session_state.get("signal_settings"),
                last_signal_setup=st.session_state.get("last_signal_setup"),
            )
            signals_for_backtest = _otf_result.accepted_signals

            _ledger_phase = "simulate"
            try:
                normalized_entry_window = normalize_entry_window(
                    entry_window_config,
                    exchange_tz=exchange_tz,
                )
            except ValueError as exc:
                raise ValueError(f"Invalid entry_window: {exc}") from exc
            simulate_entry_window = (
                normalized_entry_window if normalized_entry_window.get("enabled") else None
            )
            simulation = simulate_trades(
                df=ohlcv_df,
                signals=signals_for_backtest,
                tick_size=tick_size,
                point_value=point_value,
                stop_loss_ticks=sl_ticks,
                take_profit_ticks=tp_ticks,
                max_holding_bars=max_bars,
                allow_same_bar_exit=allow_same_bar,
                commission_per_side=float(commission_per_side),
                slippage_ticks=float(slippage_ticks),
                flat_by_session_close=flat_by_session_close,
                session_close_time=session_close_time or None,
                session_timezone=session_timezone if flat_by_session_close else None,
                no_new_entries_after=effective_no_new_entries_after,
                exposure_policy=exposure_policy,
                cooldown_bars_after_exit=cooldown_bars_after_exit,
                intrabar_model=intrabar_model,
                subtimeframe_data=subtimeframe_data,
                parent_interval=st.session_state.get("base_interval"),
                sub_interval=st.session_state.get("subtimeframe_interval"),
                breakeven_after_r=breakeven_after_r,
                trailing_after_r=trailing_after_r,
                trailing_distance_ticks=trailing_distance_ticks,
                entry_window=simulate_entry_window,
                entry_window_exchange_tz=exchange_tz,
                same_bar_opposite_direction=same_bar_opposite_direction,
                return_result=True,
            )
            trades = simulation.trades
            skipped_signals = simulation.skipped_signals

            _ledger_phase = "session_persist"
            summary = summarize_trades(trades)
            curve = equity_curve(trades)

            st.session_state["trades"] = trades
            st.session_state["trade_summary"] = summary
            st.session_state["equity_curve"] = curve
            st.session_state["skipped_signals"] = skipped_signals
            consume_armed_entry_window_after_run(st.session_state, normalized_entry_window)
            st.session_state["exposure_policy"] = {
                "exposure_policy": exposure_policy,
                "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
                "same_bar_opposite_direction": same_bar_opposite_direction,
            }
            st.session_state["backtest_execution_costs"] = {
                "commission_per_side": float(commission_per_side),
                "slippage_ticks": float(slippage_ticks),
                "metrics_basis": (
                    "net-of-cost"
                    if (float(commission_per_side) > 0.0 or float(slippage_ticks) > 0.0)
                    else "gross==net (zero costs)"
                ),
            }
            st.session_state["backtest_session_exit_policy"] = {
                "flat_by_session_close": bool(flat_by_session_close),
                "session_close_time": session_close_time or None,
                "session_timezone": session_timezone if flat_by_session_close else None,
                "no_new_entries_after": effective_no_new_entries_after,
            }
            # OTF filter session state — preserve originals, store filter results
            st.session_state["otf_filter_result"] = _otf_result
            st.session_state["otf_filter_summary"] = _otf_result.to_summary_dict()
            st.session_state["otf_candidate_signals"] = _otf_result.candidate_signals
            st.session_state["otf_accepted_signals"] = _otf_result.accepted_signals
            st.session_state["otf_rejected_signals"] = _otf_result.rejected_signals
            st.session_state["backtest_otf_filter"] = _otf_result.to_summary_dict()
            st.session_state["backtest_intrabar_policy"] = {
                "schema_version": 1,
                "intrabar_model": intrabar_model,
                "subtimeframe_data_supplied": isinstance(subtimeframe_data, pd.DataFrame),
            }
            st.session_state["backtest_intrabar_diagnostic"] = simulation.intrabar_diagnostic
            st.session_state["backtest_exit_management_policy"] = {
                "schema_version": 1,
                "breakeven_after_r": breakeven_after_r,
                "trailing_after_r": trailing_after_r,
                "trailing_distance_ticks": trailing_distance_ticks,
            }
            st.session_state["backtest_exit_management_diagnostic"] = (
                simulation.exit_management_diagnostic
            )
            persist_direction_collision_diagnostic(st.session_state, simulation)

            if _ledger_handle is not None:
                _ledger_phase = "complete"
                _ledger_run = complete_classic_execution_ledger(
                    AssistantOrchestrator.for_local_workspace(),
                    _ledger_handle,
                    session_state=st.session_state,
                )
                # complete_* terminalizes (completed or failed); clear handle so
                # the broad except below does not double-fail a finished run.
                _ledger_handle = None
                if _ledger_run.status == "completed":
                    st.caption(f"Thesis ledger: recorded completed run …{_ledger_run.run_id[-8:]}.")
                else:
                    _err = (
                        _ledger_run.error.get("message")
                        if isinstance(_ledger_run.error, dict)
                        else None
                    )
                    st.warning(
                        "Thesis ledger: execution attempt retained as "
                        f"`{_ledger_run.status}`" + (f" — {_err}" if _err else ".")
                    )
        except Exception as e:
            if _ledger_handle is not None:
                fail_classic_execution_ledger(
                    AssistantOrchestrator.for_local_workspace(),
                    _ledger_handle,
                    message=str(e),
                    phase=_ledger_phase,
                )
            if isinstance(e, ValueError) and _ledger_phase == "otf_filter":
                st.error(f"OTF filter configuration error: {e}")
                st.stop()
            if isinstance(e, ValueError) and _ledger_phase == "simulate":
                st.error(f"Backtest error: {e}")
                st.stop()
            raise
