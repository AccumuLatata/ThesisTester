"""Phase 5 — Backtest page.

Converts Phase 4 candidate signals into simulated trades using a single
fixed SL/TP configuration and displays KPIs, equity curve, and trade table.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from thesistester.app_state import bootstrap_active_saved_dataset
from thesistester.assistant import AssistantOrchestrator
from thesistester.classic_context import get_active_thesis_id, render_classic_thesis_chrome
from thesistester.classic_ledger import (
    begin_classic_execution_ledger,
    complete_classic_execution_ledger,
    fail_classic_execution_ledger,
    render_classic_execution_ledger,
    should_record_all_executions,
)
from thesistester.classic_nav import (
    render_classic_nav_prefill_caption,
    render_discuss_this_run,
)
from thesistester.classic_proposal import render_classic_proposal_card
from thesistester.classic_record import render_record_and_discuss
from thesistester.analytics import equity_curve, summarize_trades, summarize_trades_by_direction
from thesistester.analytics.entry_window import (
    ADMIT_APPLIED_STATUS_BADGE,
    ADMIT_ARMED_STATUS_BADGE,
    ADMIT_HONESTY_BANNER,
    FOCUS_EQUITY_CAVEAT,
    FOCUS_HONESTY_BANNER,
    FOCUS_STATUS_BADGE,
    PROMOTE_ARMED_BANNER,
    clear_armed_entry_window,
    consume_armed_entry_window_after_run,
    format_entry_window_label,
    partition_skip_counts,
)
from thesistester.analytics.confluence_attribution import (
    EMPTY_LEVEL_NAMES_KEY,
    EXACT_COMBO_KEY_COL,
    EXAMPLE_RAW_COL,
    LEVEL_COUNT_BUCKET_COL,
    LEVEL_NAME_COL,
    MEMBERSHIP_DOUBLE_COUNT_WARNING,
    PAIR_KEY_COL,
    PAIR_MODE_ANCHOR_PARTNER,
    PAIR_MODE_COL,
    PAIRWISE_DOUBLE_COUNT_WARNING,
    TRIGGER_3C_LEVEL_NAMES_WARNING,
    apply_sample_warning_filter,
    confluence_attribution_summary,
    pairs_empty_info_message,
    prepare_exact_combo_display,
    resolve_confluence_mode,
    resolve_signal_setup_for_attribution,
)
from thesistester.analytics.metrics import summarize_by_group as summarize_trade_groups
from thesistester.analytics.prev30m_vwap_hit import prev30m_hit_r_summary
from thesistester.levels.prev30m_vwap import COL_HIT_M1, COL_HIT_M5
from thesistester.config import INSTRUMENTS, TIMEZONE_OPTIONS
from thesistester.engine.backtest import simulate_trades
from thesistester.engine.otf_integration import apply_configured_otf_filter
from thesistester.entry_window_policy import RTH_SEGMENT_LABELS, normalize_entry_window
from thesistester.execution_defaults import (
    ENTRY_WINDOW_MODE_OPTIONS,
    INTRABAR_MODEL_OPTIONS,
    apply_backtest_defaults,
    collect_backtest_defaults,
    reset_backtest_session_keys,
)
from thesistester.persistence import (
    clear_backtest_defaults,
    get_backtest_defaults,
    save_backtest_defaults,
)
from thesistester.timezone_display import ensure_display_timezone, timezone_contract_caption
from thesistester.visualization import (
    buffered_rows_window,
    build_backtest_candlestick_chart,
    clip_by_time_window,
    coerce_timestamp_series,
    recent_rows_window,
    selected_trade_time_window,
    timestamp_bounds,
    trade_time_window,
    build_trade_review_chart,
    export_worst_loser_review_pngs,
    trade_review_export_signature,
)

st.title("📊 Backtest")
bootstrap_active_saved_dataset()
render_classic_thesis_chrome(
    page_key="backtest",
    dataset_id=st.session_state.get("dataset_id"),
)
# Prefill / proposal / Discuss must render before any st.stop() guard so empty
# Backtest pages still surface Assistant navigation and thesis-run discussion.
render_classic_nav_prefill_caption(target_page="pages/7_Backtest.py")
render_classic_proposal_card(target_page="pages/7_Backtest.py")
render_discuss_this_run(page_key="backtest")


def _signal_setup_context(signals, signal_context: dict | None) -> str | None:
    setup_names: list[str] = []
    if "setup_name" in signals.columns:
        setup_names = [
            str(name).strip()
            for name in signals["setup_name"].dropna().unique().tolist()
            if str(name).strip()
        ]

    context = signal_context or {}
    if len(setup_names) > 1:
        return f"Backtesting signals from multiple saved setups: {', '.join(setup_names)}"

    setup_name = setup_names[0] if len(setup_names) == 1 else context.get("setup_name")
    setup_caption = context.get("setup_caption")

    if setup_name and setup_caption:
        return f"Backtesting signals from saved setup: {setup_name} • {setup_caption}"
    if setup_name:
        return f"Backtesting signals from saved setup: {setup_name}"
    if setup_caption:
        return f"Backtesting generated signals • {setup_caption}"
    return None


def _clip_trades_for_chart(trades_df, *, start, end):
    if trades_df is None:
        return None

    out = trades_df.copy(deep=True)
    if out.empty or (start is None and end is None):
        return out
    if "entry_timestamp" not in out.columns or "exit_timestamp" not in out.columns:
        return out

    start_ts = pd.to_datetime(start, errors="coerce") if start is not None else None
    end_ts = pd.to_datetime(end, errors="coerce") if end is not None else None
    if pd.isna(start_ts):
        start_ts = None
    if pd.isna(end_ts):
        end_ts = None
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts
    if start_ts is None and end_ts is None:
        return out

    entry_ts = coerce_timestamp_series(out["entry_timestamp"])
    exit_ts = coerce_timestamp_series(out["exit_timestamp"])
    effective_entry = entry_ts.fillna(exit_ts)
    effective_exit = exit_ts.fillna(entry_ts)
    mask = effective_entry.notna() & effective_exit.notna()
    if start_ts is not None:
        mask &= effective_exit >= start_ts
    if end_ts is not None:
        mask &= effective_entry <= end_ts
    return out.loc[mask].copy(deep=True)


# ── Require signals ───────────────────────────────────────────────────────────
if "signals" not in st.session_state:
    st.warning(
        "No signals found. Please load data on the **Data** page, compute "
        "levels on the **Levels** page, and generate signals on the **Signals** page first."
    )
    st.stop()

signals = st.session_state["signals"]
signal_context = st.session_state.get("signal_context")
if signals is None or signals.empty:
    st.warning("Signal table is empty. Please generate signals on the **Signals** page first.")
    st.stop()

# ── Prefer levels df for full timeline; fall back to data ─────────────────────
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
exchange_tz = st.session_state.get("exchange_timezone") or (
    inst.exchange_tz if inst else "America/New_York"
)
ensure_display_timezone(st.session_state, exchange_timezone=exchange_tz)

setup_context_caption = _signal_setup_context(signals, signal_context)
if setup_context_caption:
    st.caption(setup_context_caption)

# ── Load saved execution defaults (once per session) ──────────────────────────
if "_backtest_defaults_applied" not in st.session_state:
    _saved = get_backtest_defaults()
    if _saved:
        apply_backtest_defaults(st.session_state, _saved)
    st.session_state["_backtest_defaults_applied"] = True

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Backtest settings")
    st.caption(f"Instrument: **{instrument}** · tick={tick_size} · point_value=${point_value:,.0f}")
    st.selectbox(
        "Display/export timezone",
        options=TIMEZONE_OPTIONS,
        key="display_timezone",
        help="Affects user-facing timestamp display/export only. Backtest engine remains in exchange/session time.",
    )

    sl_ticks = st.number_input(
        "Stop loss (ticks)",
        min_value=1.0,
        max_value=500.0,
        value=8.0,
        step=1.0,
        key="backtest_sl_ticks",
        help="Fixed stop-loss distance from entry in ticks.",
    )

    tp_ticks = st.number_input(
        "Take profit (ticks)",
        min_value=1.0,
        max_value=1000.0,
        value=16.0,
        step=1.0,
        key="backtest_tp_ticks",
        help="Fixed take-profit distance from entry in ticks.",
    )

    commission_per_side = st.number_input(
        "Commission per side (currency/contract)",
        min_value=0.0,
        max_value=1_000.0,
        value=0.0,
        step=0.1,
        key="backtest_commission_per_side",
        help="Round-turn commission cost is 2 × this value.",
    )

    slippage_ticks = st.number_input(
        "Slippage (ticks per side)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.25,
        key="backtest_slippage_ticks",
        help="Adverse slippage applied at both entry and exit.",
    )

    use_max_bars = st.toggle("Limit holding bars", value=False, key="backtest_use_max_bars")
    max_bars: int | None = None
    if use_max_bars:
        max_bars = int(
            st.number_input(
                "Max holding bars",
                min_value=1,
                max_value=500,
                value=20,
                step=1,
                key="backtest_max_bars",
            )
        )

    allow_same_bar = st.toggle(
        "Allow same-bar exit",
        value=True,
        key="backtest_allow_same_bar",
        help=(
            "If enabled, SL/TP checks begin on the entry bar (recommended for "
            "filled 3c entries). When both SL and TP are reachable in the same bar, "
            "resolution follows the selected Intrabar resolution model "
            "(SL-first only when that model is selected)."
        ),
    )
    intrabar_model = st.selectbox(
        "Intrabar resolution",
        options=INTRABAR_MODEL_OPTIONS,
        index=0,
        key="backtest_intrabar_model",
        format_func=lambda value: {
            "sl_first": "SL-first (legacy pessimistic)",
            "path_open_proximity": "OHLC open-proximity path",
            "subtimeframe": "Observed lower-timeframe replay",
            "subtimeframe_conservative": "Observed replay + SL-first fallback",
        }[value],
        help=(
            "Observed replay requires strictly finer data. The conservative "
            "model replays validated lower bars and uses SL-first only where "
            "lower bars are unavailable."
        ),
    )
    subtimeframe_data = st.session_state.get("subtimeframe_data")
    if intrabar_model in {"subtimeframe", "subtimeframe_conservative"} and not isinstance(
        subtimeframe_data, pd.DataFrame
    ):
        st.warning(
            "Subtimeframe replay requires lower-timeframe data. Upload it on the "
            "Data page or load it through a research bundle. "
            "Headless runs can also set `dataset.subtimeframe_path`."
        )
    with st.expander("Exit management (break-even / trailing)", expanded=False):
        enable_breakeven = st.toggle(
            "Enable break-even move", value=False, key="backtest_enable_be"
        )
        breakeven_after_r = None
        if enable_breakeven:
            breakeven_after_r = float(
                st.number_input(
                    "Move stop to break-even after R",
                    min_value=0.1,
                    max_value=20.0,
                    value=1.0,
                    step=0.1,
                    key="backtest_breakeven_after_r",
                )
            )
        enable_trailing = st.toggle(
            "Enable trailing stop", value=False, key="backtest_enable_trail"
        )
        trailing_after_r = None
        trailing_distance_ticks = None
        if enable_trailing:
            trailing_after_r = float(
                st.number_input(
                    "Start trailing after R",
                    min_value=0.1,
                    max_value=20.0,
                    value=1.5,
                    step=0.1,
                    key="backtest_trailing_after_r",
                )
            )
            trailing_distance_ticks = float(
                st.number_input(
                    "Trailing distance (ticks)",
                    min_value=1.0,
                    max_value=500.0,
                    value=8.0,
                    step=1.0,
                    key="backtest_trailing_distance_ticks",
                )
            )
        st.caption(
            "Break-even/trailing adjustments are committed after completed bars "
            "and become active on the next bar."
        )

    st.subheader("Session exit policy")
    flat_by_session_close = st.toggle(
        "Flat by session close", value=False, key="backtest_flat_by_session_close"
    )
    session_close_time = st.text_input(
        "Session close time",
        value="16:00",
        key="backtest_session_close_time",
        disabled=not flat_by_session_close,
        help="Local session close time in HH:MM or HH:MM:SS.",
    )
    session_timezone = st.selectbox(
        "Session timezone",
        options=TIMEZONE_OPTIONS,
        index=(TIMEZONE_OPTIONS.index(exchange_tz) if exchange_tz in TIMEZONE_OPTIONS else 0),
        key="backtest_session_timezone",
        disabled=not flat_by_session_close,
    )
    no_new_entries_after = st.text_input(
        "No new entries after (optional)",
        value="",
        key="backtest_no_new_entries_after",
        disabled=not flat_by_session_close,
        help="Optional local cutoff in HH:MM or HH:MM:SS.",
    )
    effective_no_new_entries_after = (
        (no_new_entries_after.strip() or None) if flat_by_session_close else None
    )

    st.subheader("Entry window (Admit)")
    st.caption(
        "Opt-in admission constraint. When enabled, only signals whose "
        "**entry bar** falls in the window are simulated. Distinct from "
        "Time Analysis Focus (post-hoc subset)."
    )
    if bool(st.session_state.get("entry_window_armed")):
        st.caption(f"**{ADMIT_ARMED_STATUS_BADGE}**")
        st.warning(PROMOTE_ARMED_BANNER)
    enable_entry_window = st.toggle(
        "Constrain entries to time window",
        value=False,
        key="backtest_entry_window_enabled",
        help=(
            "Re-simulates under an entry-time constraint (Admit). "
            "Default off = legacy all-day admission."
        ),
    )
    entry_window_config: dict | None = None
    if enable_entry_window:
        entry_window_mode = st.selectbox(
            "Window mode",
            options=list(ENTRY_WINDOW_MODE_OPTIONS),
            index=0,
            key="backtest_entry_window_mode",
            format_func=lambda value: {
                "rth_segments": "RTH segments (exchange/session TZ)",
                "clock_range": "Clock range [start, end)",
            }[value],
        )
        if entry_window_mode == "rth_segments":
            selected_segments = st.multiselect(
                "RTH segments",
                options=list(RTH_SEGMENT_LABELS),
                default=["rth_open_30m"],
                key="backtest_entry_window_rth_segments",
                help="Multi-segment selection is OR (C3). Membership uses exchange/session TZ (C5).",
            )
            entry_window_config = {
                "enabled": True,
                "mode": "rth_segments",
                "rth_segments": list(selected_segments),
                "timezone": exchange_tz,
            }
            if not selected_segments:
                st.warning("Select at least one RTH segment, or disable the entry window.")
        else:
            ew_start = st.text_input(
                "Start time",
                value="09:30",
                key="backtest_entry_window_start_time",
                help="Half-open range start HH:MM or HH:MM:SS (C4).",
            )
            ew_end = st.text_input(
                "End time",
                value="10:00",
                key="backtest_entry_window_end_time",
                help="Half-open range end (exclusive). Use 24:00 for end-of-day.",
            )
            ew_tz = st.selectbox(
                "Window timezone",
                options=TIMEZONE_OPTIONS,
                index=(
                    TIMEZONE_OPTIONS.index(exchange_tz) if exchange_tz in TIMEZONE_OPTIONS else 0
                ),
                key="backtest_entry_window_timezone",
                help="Clock-range membership uses this TZ (C5). RTH segments always use exchange TZ.",
            )
            entry_window_config = {
                "enabled": True,
                "mode": "clock_range",
                "start_time": ew_start.strip(),
                "end_time": ew_end.strip(),
                "timezone": ew_tz,
            }

    st.subheader("Exposure policy")
    exposure_policy = st.selectbox(
        "Policy",
        options=[
            "allow_all",
            "single_position",
            "single_direction",
            "single_setup",
        ],
        index=0,
        key="backtest_exposure_policy",
    )
    cooldown_bars_after_exit = int(
        st.number_input(
            "Cooldown bars after exit",
            min_value=0,
            max_value=10_000,
            value=0,
            step=1,
            key="backtest_cooldown_bars",
        )
    )

    st.divider()
    _save_col, _reset_col = st.columns(2)
    _save_btn = _save_col.button(
        "💾 Save execution settings as default",
        help="Save current execution settings as default for future sessions.",
        use_container_width=True,
    )
    _reset_btn = _reset_col.button(
        "↩ Reset to built-in defaults",
        help="Clear saved execution defaults and revert to built-in widget values.",
        use_container_width=True,
    )
    if _save_btn:
        save_backtest_defaults(collect_backtest_defaults(st.session_state))
        st.success("Execution settings saved as default.")
    if _reset_btn:
        clear_backtest_defaults()
        reset_backtest_session_keys(st.session_state)
        # SW4: widget reset must also drop a pending Promote handoff; otherwise
        # Admit widgets revert while entry_window_armed / provenance linger.
        clear_armed_entry_window(st.session_state)
        st.info("Built-in defaults restored.")
        st.rerun()

    run_btn = st.button("▶ Run backtest", type="primary", width="stretch")

# ── Run ───────────────────────────────────────────────────────────────────────
if run_btn:
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
            _otf_result = apply_configured_otf_filter(
                source_df=ohlcv_df,
                candidate_signals=signals,
                setup_config=st.session_state.get("setup_config"),
                session_timezone=exchange_tz,
                eth_start=(inst.eth_start if inst else None),
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

# ── Display ───────────────────────────────────────────────────────────────────
trades = st.session_state.get("trades")
summary = st.session_state.get("trade_summary")
curve = st.session_state.get("equity_curve")
skipped_signals = st.session_state.get("skipped_signals")

if trades is None:
    st.info("Configure settings in the sidebar and click **▶ Run backtest**.")
    st.stop()

render_record_and_discuss(page_key="backtest")
render_classic_execution_ledger(page_key="backtest")

st.caption(timezone_contract_caption(st.session_state))
costs = st.session_state.get("backtest_execution_costs") or {}
if costs.get("commission_per_side", 0.0) > 0.0 or costs.get("slippage_ticks", 0.0) > 0.0:
    st.caption(
        "Execution costs active — KPIs use net-of-cost pnl_currency and net R (commission/slippage applied)."
    )
else:
    st.caption("Execution costs disabled — KPIs are gross (zero commission/slippage).")
intrabar_diagnostic = st.session_state.get("backtest_intrabar_diagnostic") or {}
if intrabar_diagnostic:
    st.caption(
        "Intrabar model: "
        f"`{intrabar_diagnostic.get('intrabar_model', 'sl_first')}` · "
        f"both-hit exits: {intrabar_diagnostic.get('same_bar_both_hit_count', 0)} · "
        f"residual ambiguities: {intrabar_diagnostic.get('ambiguous_resolution_count', 0)}. "
        "Deterministic OHLC paths are assumptions, not recovered market paths."
    )
exit_mgmt = st.session_state.get("backtest_exit_management_diagnostic") or {}
if exit_mgmt and exit_mgmt.get("enabled"):
    st.caption(
        "Exit management: "
        f"BE after {exit_mgmt.get('breakeven_after_r') or 'off'}R · "
        f"trail after {exit_mgmt.get('trailing_after_r') or 'off'}R · "
        f"BE exits: {exit_mgmt.get('be_exit_count', 0)} · "
        f"TRAIL exits: {exit_mgmt.get('trail_exit_count', 0)}."
    )

# ── OTF filter status ─────────────────────────────────────────────────────────
_otf_summary = st.session_state.get("otf_filter_summary") or {}
_otf_enabled = bool(_otf_summary.get("otf_filter_enabled", False))
_otf_candidate_count = _otf_summary.get("candidate_signal_count", len(signals))
_otf_accepted_count = _otf_summary.get("otf_accepted_signal_count", len(signals))
_otf_rejected_count = _otf_summary.get("otf_rejected_signal_count", 0)
_otf_eth_start = _otf_summary.get("eth_start")
_otf_session_tz = _otf_summary.get("session_timezone")
st.caption(
    "OTF is applied **before** trade simulation. "
    "Candidate signals in session state are never overwritten. "
    "Config resolution precedence: signal-run `otf_filter` → setup snapshot → "
    "last signal setup → active setup → disabled defaults. "
    "Rejected rows are distinct from exposure-policy skips and 3c voids."
)

if _otf_enabled:
    _otf_config = _otf_summary.get("otf_filter_config") or {}
    _otf_tfs = _otf_config.get("timeframes", []) if isinstance(_otf_config, dict) else []
    _otf_min_bars = (
        _otf_config.get("minimum_consecutive_bars", 3) if isinstance(_otf_config, dict) else 3
    )
    st.info(
        f"🔎 **OTF filter enabled** — timeframes: {', '.join(_otf_tfs) or '—'} · "
        f"min consecutive completed HTF bars: {_otf_min_bars} · "
        f"session tz: {_otf_session_tz or '—'} · eth_start: {_otf_eth_start or '—'} · "
        f"candidates: {_otf_candidate_count} · accepted: {_otf_accepted_count} · "
        f"rejected: {_otf_rejected_count}"
    )
else:
    st.caption(
        f"OTF filter: **disabled** — all {_otf_candidate_count} candidate signals passed through."
    )

_skip_counts = partition_skip_counts(
    skipped_signals if isinstance(skipped_signals, pd.DataFrame) else None
)
_entry_window_state = st.session_state.get("entry_window") or {}
_entry_window_enabled = bool(
    isinstance(_entry_window_state, dict) and _entry_window_state.get("enabled")
)
_entry_window_armed = bool(st.session_state.get("entry_window_armed"))
if _entry_window_armed and _entry_window_enabled:
    # Pending Promote: do not claim constrained re-sim until Run completes.
    st.caption(f"**{ADMIT_ARMED_STATUS_BADGE}**")
    st.warning(
        f"{PROMOTE_ARMED_BANNER} Window: **{format_entry_window_label(_entry_window_state)}**."
    )
elif _entry_window_enabled:
    st.caption(f"**{ADMIT_APPLIED_STATUS_BADGE}**")
    st.info(f"{ADMIT_HONESTY_BANNER} Window: **{format_entry_window_label(_entry_window_state)}**.")
st.caption(
    f"Accepted trades: {summary.get('trade_count', 0) if isinstance(summary, dict) else len(trades)} · "
    f"Skipped (total): {_skip_counts['total']} · "
    f"outside entry window: {_skip_counts['outside_entry_window']} · "
    f"after entry cutoff: {_skip_counts['after_entry_cutoff']} · "
    f"exposure / other: {_skip_counts['other']}"
)
if isinstance(skipped_signals, pd.DataFrame) and not skipped_signals.empty:
    st.subheader("Skipped signals")
    st.caption(
        "Skip reasons include exposure-policy rejects, `after_entry_cutoff` "
        "(when `no_new_entries_after` rejects with skip capture on), and "
        "`outside_entry_window` when Admit is enabled. Distinct from OTF rejects "
        "and 3c voids."
    )
    skip_cols = [
        c
        for c in [
            "signal_id",
            "entry_bar_index",
            "trigger",
            "direction",
            "skip_reason",
            "blocking_trade_id",
            "blocking_exit_bar_index",
            "exposure_group_key",
        ]
        if c in skipped_signals.columns
    ]
    st.dataframe(skipped_signals[skip_cols], width="stretch", hide_index=True)

# OTF rejected signals (distinct from exposure skips and 3c void)
_otf_rejected = st.session_state.get("otf_rejected_signals")
if isinstance(_otf_rejected, pd.DataFrame) and not _otf_rejected.empty:
    with st.expander(f"🚫 OTF rejected signals ({len(_otf_rejected)})"):
        st.caption(
            "Signals below were rejected by the OTF eligibility filter before simulation. "
            "These are distinct from exposure-policy skipped signals and 3c void signal status."
        )
        _rej_cols = [
            c
            for c in [
                "signal_id",
                "timestamp",
                "trigger",
                "direction",
                "status",
                "otf_filter_reason",
                "otf_signal_decision_timestamp",
                *[
                    c
                    for c in _otf_rejected.columns
                    if c.startswith("otf_")
                    and c
                    not in (
                        "otf_filter_enabled",
                        "otf_filter_passed",
                        "otf_filter_reason",
                        "otf_signal_decision_timestamp",
                    )
                ],
            ]
            if c in _otf_rejected.columns
        ]
        st.dataframe(_otf_rejected[_rej_cols], width="stretch", hide_index=True)

# KPI cards
st.subheader("Performance summary")

# SW1 Focus overlay — never mutate full-run session keys.
_focus_window = st.session_state.get("focus_entry_window")
_focus_summary = st.session_state.get("focused_trade_summary")
_focus_curve = st.session_state.get("focused_equity_curve")
_focus_trades = st.session_state.get("focused_trades")
_focus_prov = st.session_state.get("focus_provenance") or {}
_has_focus = (
    isinstance(_focus_window, dict)
    and bool(_focus_window.get("enabled"))
    and isinstance(_focus_summary, dict)
)
_show_focused = False
if _has_focus:
    st.caption(f"**{FOCUS_STATUS_BADGE}**")
    st.warning(FOCUS_HONESTY_BANNER)
    st.info(FOCUS_EQUITY_CAVEAT)
    st.caption(
        f"Focused window from Time Analysis: "
        f"**{format_entry_window_label(_focus_window)}** · "
        f"{_focus_prov.get('trade_count_after', 0)} / "
        f"{_focus_prov.get('trade_count_before', 0)} trades. "
        "Clear Focus on the Time Analysis page to remove this overlay."
    )
    if _focus_prov.get("sample_warning"):
        st.warning(
            f"Sample-size warning: focused trade_count "
            f"({_focus_prov.get('trade_count_after', 0)}) is below the "
            f"{_focus_prov.get('min_trades', 10)} threshold."
        )
    _show_focused = st.toggle(
        "Show Focused summary overlay",
        value=True,
        key="backtest_show_focused_overlay",
        help="Post-hoc subset only. Full-run trades/summary in session state are unchanged.",
    )

_display_summary = _focus_summary if _show_focused and isinstance(_focus_summary, dict) else summary
_display_curve = _focus_curve if _show_focused and _focus_curve is not None else curve
_display_trades = (
    _focus_trades if _show_focused and isinstance(_focus_trades, pd.DataFrame) else trades
)
if not isinstance(_display_summary, dict):
    _display_summary = summary if isinstance(summary, dict) else {}


def _fmt(v, fmt=".2f", fallback="—"):
    if v is None:
        return fallback
    try:
        v_float = float(v)
        if math.isnan(v_float):
            return fallback
        return format(v_float, fmt)
    except (TypeError, ValueError):
        return fallback


def _fmt_int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _fmt_win_rate(v):
    return _fmt(v, ".1%") if v is not None else "—"


if _show_focused:
    st.caption("Showing **Focused** KPIs (post-hoc subset).")
else:
    st.caption("Showing **full-run** KPIs.")

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Trades", _display_summary.get("trade_count", 0))
col2.metric("Win rate", _fmt_win_rate(_display_summary.get("win_rate")))
col3.metric("Avg R", _fmt(_display_summary.get("avg_r")))
col4.metric("Total R", _fmt(_display_summary.get("total_r")))
col5.metric("Profit factor", _fmt(_display_summary.get("profit_factor")))
col6.metric("Max DD (R)", _fmt(_display_summary.get("max_drawdown_r")))

st.subheader("Advanced risk metrics")
adv_row_1 = st.columns(5)
adv_row_1[0].metric("Median R", _fmt(_display_summary.get("median_r")))
adv_row_1[1].metric("Std R", _fmt(_display_summary.get("std_r")))
adv_row_1[2].metric("Sharpe-like R", _fmt(_display_summary.get("sharpe_like_r")))
adv_row_1[3].metric("Sortino-like R", _fmt(_display_summary.get("sortino_like_r")))
adv_row_1[4].metric("Ulcer index R", _fmt(_display_summary.get("ulcer_index_r")))

adv_row_2 = st.columns(4)
adv_row_2[0].metric("Recovery factor", _fmt(_display_summary.get("recovery_factor")))
adv_row_2[1].metric("Tail ratio", _fmt(_display_summary.get("tail_ratio")))
adv_row_2[2].metric("Outlier dependency", _fmt(_display_summary.get("outlier_dependency_ratio")))
adv_row_2[3].metric(
    "Max consecutive losses", _fmt_int(_display_summary.get("max_consecutive_losses", 0))
)

direction_summary = summarize_trades_by_direction(_display_trades)
st.subheader("Long vs Short KPIs")
long_col, short_col = st.columns(2)

with long_col:
    long_summary = direction_summary.get("long", {})
    st.markdown("**Long trades**")
    st.metric("Trades", _fmt_int(long_summary.get("trade_count", 0)))
    st.metric("Win rate", _fmt_win_rate(long_summary.get("win_rate")))
    st.metric("Average R", _fmt(long_summary.get("avg_r")))
    st.metric("Total R", _fmt(long_summary.get("total_r")))
    st.metric("Profit factor", _fmt(long_summary.get("profit_factor")))

with short_col:
    short_summary = direction_summary.get("short", {})
    st.markdown("**Short trades**")
    st.metric("Trades", _fmt_int(short_summary.get("trade_count", 0)))
    st.metric("Win rate", _fmt_win_rate(short_summary.get("win_rate")))
    st.metric("Average R", _fmt(short_summary.get("avg_r")))
    st.metric("Total R", _fmt(short_summary.get("total_r")))
    st.metric("Profit factor", _fmt(short_summary.get("profit_factor")))

if trades.empty:
    st.info("No trades were generated with the current signals and SL/TP settings.")
elif _show_focused and isinstance(_display_trades, pd.DataFrame) and _display_trades.empty:
    st.info("Focused subset is empty for the selected time window.")

has_trades = not trades.empty
_display_has_trades = isinstance(_display_trades, pd.DataFrame) and not _display_trades.empty

if has_trades:
    group_cols = [
        c for c in ["trigger_variant", "level_source_mode", "direction"] if c in trades.columns
    ]
    if group_cols and "trigger" in trades.columns:
        trades_3c = trades[trades["trigger"] == "3c"]
        grouped = summarize_trade_groups(trades_3c, group_cols)
        if not grouped.empty:
            st.subheader("3c outcome summary by variant/source")
            st.dataframe(grouped, width="stretch", hide_index=True)

# Optional prev30mVWAP early-window hit R diagnostics (Phase 2; read-only).
_levels_for_prev30m = st.session_state.get("levels")
if (
    has_trades
    and isinstance(_levels_for_prev30m, pd.DataFrame)
    and (COL_HIT_M1 in _levels_for_prev30m.columns or COL_HIT_M5 in _levels_for_prev30m.columns)
):
    try:
        prev30m_summary = prev30m_hit_r_summary(
            trades,
            _levels_for_prev30m,
            instrument=str(instrument),
        )
    except (ValueError, TypeError, KeyError):
        prev30m_summary = {"available": False, "trade_count": 0}
    if prev30m_summary.get("available") and int(prev30m_summary.get("trade_count", 0)) > 0:
        with st.expander("prev30mVWAP early-window hit R diagnostics", expanded=False):
            st.caption(
                "R-multiples conditioned on finalized first-1m / first-5m touches of "
                "`prev30mVWAP` in the trade's entry 30m bracket. Only trades with a "
                "finalized hit flag are counted. Diagnostic only — does not change fills."
            )
            st.metric("Analyzable trades", int(prev30m_summary["trade_count"]))
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**By hit_m1**")
                st.dataframe(prev30m_summary["by_hit_m1"], width="stretch", hide_index=True)
            with c2:
                st.markdown("**By hit_m5**")
                st.dataframe(prev30m_summary["by_hit_m5"], width="stretch", hide_index=True)
            contingency = prev30m_summary["contingency"]
            if not contingency.empty:
                st.markdown("**Joint (hit_m1, hit_m5) contingency**")
                st.dataframe(contingency, width="stretch", hide_index=True)

# Equity curve
st.subheader("Equity curve (cumulative R)")
if _show_focused:
    st.caption(FOCUS_EQUITY_CAVEAT)
if _display_curve is not None and not _display_curve.empty:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=_display_curve["exit_timestamp"],
            y=_display_curve["cum_r"],
            mode="lines+markers",
            name="Cum R",
            line=dict(color="steelblue", width=2),
            marker=dict(size=4),
        )
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=30, b=10),
        yaxis_title="Cumulative R",
        xaxis_title="",
    )
    st.plotly_chart(fig, width="stretch")

# Breakdown tabs
if _display_has_trades:
    st.subheader("Breakdown")
    tab_trigger, tab_dir, tab_reason = st.tabs(["By trigger", "By direction", "By exit reason"])

    with tab_trigger:
        if "trigger" in _display_trades.columns:
            st.dataframe(
                _display_trades.groupby("trigger")
                .agg(
                    count=("trade_id", "count"),
                    win_rate=("r_multiple", lambda x: (x > 0).mean()),
                    avg_r=("r_multiple", "mean"),
                    total_r=("r_multiple", "sum"),
                )
                .reset_index(),
                width="stretch",
                hide_index=True,
            )

    with tab_dir:
        if "direction" in _display_trades.columns:
            st.dataframe(
                _display_trades.groupby("direction")
                .agg(
                    count=("trade_id", "count"),
                    win_rate=("r_multiple", lambda x: (x > 0).mean()),
                    avg_r=("r_multiple", "mean"),
                    total_r=("r_multiple", "sum"),
                )
                .reset_index(),
                width="stretch",
                hide_index=True,
            )

    with tab_reason:
        if "exit_reason" in _display_trades.columns:
            st.dataframe(
                _display_trades.groupby("exit_reason")
                .agg(
                    count=("trade_id", "count"),
                    avg_r=("r_multiple", "mean"),
                    total_r=("r_multiple", "sum"),
                )
                .reset_index(),
                width="stretch",
                hide_index=True,
            )

# Confluence combo attribution (analytics-only; collapsed by default).
if _display_has_trades:
    with st.expander("Confluence combo attribution", expanded=False):
        # Prefer signal-run identity over a possibly stale Setup Builder config
        # (same order as OTF/Validation: signal_settings → last_signal_setup → …).
        _setup_for_cca = resolve_signal_setup_for_attribution(
            signal_settings=st.session_state.get("signal_settings"),
            last_signal_setup=st.session_state.get("last_signal_setup"),
            setup_config=st.session_state.get("setup_config"),
            signal_context=st.session_state.get("signal_context"),
        )

        _confluence_mode = resolve_confluence_mode(_setup_for_cca, _display_trades)
        if _confluence_mode == "anchor_rules":
            st.caption(
                "Combinations are anchor + currently valid confluence rules on the "
                "signal bar. Min valid confluences controls threshold, not pairwise "
                "splitting."
            )
        elif _confluence_mode == "global_cluster":
            st.caption(
                "Combinations are unsupervised peer clusters within tolerance. "
                "Order is canonicalized; raw price-order strings may differ."
            )
        else:
            st.caption("Combinations are derived from each trade's recorded `level_names`.")

        st.caption(
            "Diagnostic only — rows are combinations that actually traded in this "
            "run, not all possible subsets. Sorting many combinations by total R "
            "invites selection effects; thin samples are hidden by default. Not "
            "proof of future edge."
        )
        st.caption(MEMBERSHIP_DOUBLE_COUNT_WARNING)
        st.caption(PAIRWISE_DOUBLE_COUNT_WARNING)

        _cca_min_trades = st.number_input(
            "Minimum trades for sample warning",
            min_value=1,
            max_value=10_000,
            value=10,
            step=1,
            key="backtest_cca_min_trades",
        )
        _cca_hide_thin = st.checkbox(
            "Hide samples below min trades",
            value=True,
            key="backtest_cca_hide_below_min",
        )

        _anchor_level = None
        if _confluence_mode == "anchor_rules":
            _raw_anchor = _setup_for_cca.get("anchor_level")
            if isinstance(_raw_anchor, str) and _raw_anchor.strip():
                _anchor_level = _raw_anchor.strip()

        try:
            _cca_summary = confluence_attribution_summary(
                _display_trades,
                min_trades=int(_cca_min_trades),
                anchor_level=_anchor_level,
                confluence_mode=_confluence_mode,
            )
        except (TypeError, ValueError, KeyError):
            _cca_summary = {"available": False, "trade_count": 0, "warnings": []}

        if TRIGGER_3C_LEVEL_NAMES_WARNING in list(_cca_summary.get("warnings") or []):
            st.caption(TRIGGER_3C_LEVEL_NAMES_WARNING)

        if not _cca_summary.get("available"):
            _empty_count = int(_cca_summary.get("empty_level_names_count") or 0)
            if "level_names" not in _display_trades.columns:
                st.info(
                    "Confluence combo attribution unavailable: displayed trades have "
                    "no `level_names` column."
                )
            elif _empty_count > 0 and int(_cca_summary.get("nonempty_combo_trade_count") or 0) == 0:
                st.info(
                    "Confluence combo attribution unavailable: analyzable trades only "
                    f"have empty `level_names` ({_empty_count})."
                )
            else:
                st.info(
                    "Confluence combo attribution unavailable for the current displayed "
                    "trades (need non-null `r_multiple` and at least one non-empty "
                    "`level_names` combo)."
                )
        else:
            st.caption(
                f"Analyzable trades: {int(_cca_summary.get('trade_count') or 0)} · "
                f"Non-empty combos: {int(_cca_summary.get('nonempty_combo_trade_count') or 0)}"
            )

            _tab_exact, _tab_member, _tab_count, _tab_pairs = st.tabs(
                ["Exact combo", "Membership", "Level count", "Pairs"]
            )

            with _tab_exact:
                _exact = prepare_exact_combo_display(
                    apply_sample_warning_filter(
                        _cca_summary.get("by_exact_combo"),
                        hide_below_min=bool(_cca_hide_thin),
                    ),
                    anchor_level=_anchor_level,
                    confluence_mode=_confluence_mode,
                )
                if _exact.empty:
                    st.info("No exact-combo rows to display under the current filter.")
                else:
                    _exact_view = _exact.copy()
                    if "display_combo" in _exact_view.columns:
                        _exact_view = _exact_view.rename(columns={"display_combo": "combo"})
                    _exact_cols = [
                        c
                        for c in [
                            "combo",
                            EXACT_COMBO_KEY_COL,
                            EXAMPLE_RAW_COL,
                            "trade_count",
                            "win_rate",
                            "avg_r",
                            "median_r",
                            "total_r",
                            "sample_warning",
                        ]
                        if c in _exact_view.columns
                    ]
                    # Prefer friendly combo label; keep canonical key only when it differs.
                    if (
                        "combo" in _exact_view.columns
                        and EXACT_COMBO_KEY_COL in _exact_cols
                        and (
                            _exact_view["combo"].astype(str)
                            == _exact_view[EXACT_COMBO_KEY_COL]
                            .replace(EMPTY_LEVEL_NAMES_KEY, "(no level names)")
                            .astype(str)
                        ).all()
                    ):
                        _exact_cols = [c for c in _exact_cols if c != EXACT_COMBO_KEY_COL]
                    st.dataframe(_exact_view[_exact_cols], width="stretch", hide_index=True)

            with _tab_member:
                st.caption(MEMBERSHIP_DOUBLE_COUNT_WARNING)
                _member = apply_sample_warning_filter(
                    _cca_summary.get("by_membership"),
                    hide_below_min=bool(_cca_hide_thin),
                )
                if _member.empty:
                    st.info("No membership rows to display under the current filter.")
                else:
                    _member_view = _member.rename(columns={LEVEL_NAME_COL: "level"})
                    _member_cols = [
                        c
                        for c in [
                            "level",
                            "trade_count",
                            "win_rate",
                            "avg_r",
                            "median_r",
                            "total_r",
                            "sample_warning",
                        ]
                        if c in _member_view.columns
                    ]
                    st.dataframe(_member_view[_member_cols], width="stretch", hide_index=True)

            with _tab_count:
                st.caption(
                    "Level count uses the parsed distinct token count from "
                    "`level_names` (not stored zone `level_count`)."
                )
                _counts = apply_sample_warning_filter(
                    _cca_summary.get("by_level_count"),
                    hide_below_min=bool(_cca_hide_thin),
                )
                if _counts.empty:
                    st.info("No level-count rows to display under the current filter.")
                else:
                    _count_view = _counts.rename(
                        columns={LEVEL_COUNT_BUCKET_COL: "parsed_level_count"}
                    )
                    _count_cols = [
                        c
                        for c in [
                            "parsed_level_count",
                            "trade_count",
                            "win_rate",
                            "avg_r",
                            "median_r",
                            "total_r",
                            "sample_warning",
                        ]
                        if c in _count_view.columns
                    ]
                    st.dataframe(_count_view[_count_cols], width="stretch", hide_index=True)

            with _tab_pairs:
                st.caption(PAIRWISE_DOUBLE_COUNT_WARNING)
                if (
                    _confluence_mode == "anchor_rules"
                    and _anchor_level
                    and _cca_summary.get("pair_mode") == PAIR_MODE_ANCHOR_PARTNER
                ):
                    st.caption(
                        f"Anchor-partner mode: pairs are `{_anchor_level}|support` for each "
                        "support present with the anchor on a trade. Trades missing the "
                        "anchor fall back to generic unordered pairs. Anchor is never "
                        "guessed from token order."
                    )
                else:
                    st.caption(
                        "Generic pair mode: all unordered distinct level pairs on each "
                        "trade (`A|B` canonical). Anchor-partner mode requires "
                        "`anchor_rules` plus a known session/signal-run anchor level."
                    )
                _pairs_raw = _cca_summary.get("by_pairs")
                _pairs = apply_sample_warning_filter(
                    _pairs_raw,
                    hide_below_min=bool(_cca_hide_thin),
                )
                if _pairs is None or (isinstance(_pairs, pd.DataFrame) and _pairs.empty):
                    st.info(pairs_empty_info_message(_pairs_raw))
                else:
                    _pairs_view = _pairs.rename(
                        columns={PAIR_KEY_COL: "pair", PAIR_MODE_COL: "pair_mode"}
                    )
                    _pair_cols = [
                        c
                        for c in [
                            "pair",
                            "pair_mode",
                            "trade_count",
                            "win_rate",
                            "avg_r",
                            "median_r",
                            "total_r",
                            "sample_warning",
                        ]
                        if c in _pairs_view.columns
                    ]
                    st.dataframe(_pairs_view[_pair_cols], width="stretch", hide_index=True)

# Full trade table
if _display_has_trades:
    st.subheader("Trade table")
    display_cols = [
        c
        for c in [
            "trade_id",
            "signal_id",
            "trigger",
            "direction",
            "entry_timestamp",
            "entry_price",
            "entry_model",
            "exit_timestamp",
            "exit_price",
            "exit_reason",
            "stop_price",
            "target_price",
            "stop_loss_ticks",
            "take_profit_ticks",
            "gross_pnl_points",
            "gross_pnl_currency",
            "commission_cost",
            "slippage_cost",
            "net_pnl_currency",
            "pnl_points",
            "pnl_currency",
            "r_multiple",
            "bars_held",
            "zone_low",
            "zone_high",
            "level_count",
            "level_names",
            "setup_name",
            "mae_points",
            "mfe_points",
        ]
        if c in _display_trades.columns
    ]
    st.dataframe(_display_trades[display_cols], width="stretch", hide_index=True)

    with st.expander("Trade review (per-trade inspection)", expanded=False):
        st.caption(
            "Visualization only. MAE/MFE shading is the terminal parent-bar excursion envelope, "
            "not a reconstructed intrabar path or proof of fill ordering."
        )
        review_labels = {
            index: (
                f"#{row.get('trade_id', index)} | {row.get('direction', '—')} | "
                f"{float(row.get('r_multiple', 0.0)):+.2f}R | {row.get('exit_reason', '—')}"
            )
            for index, (_, row) in enumerate(_display_trades.iterrows())
        }
        selected_review_index = st.selectbox(
            "Completed trade",
            options=list(review_labels),
            format_func=lambda index: review_labels[index],
            key="trade_review_trade_id",
        )
        review_buffer_rows = int(
            st.slider(
                "Bars before/after trade",
                min_value=10,
                max_value=500,
                value=100,
                step=10,
                key="trade_review_buffer_rows",
            )
        )
        review_options = st.columns(4)
        review_show_sessions = review_options[0].toggle("Sessions", value=True)
        review_show_levels = review_options[1].toggle("Levels", value=True)
        review_show_zones = review_options[2].toggle("Zones", value=True)
        review_show_final_stop = review_options[3].toggle("Final managed stop", value=False)
        selected_trade = _display_trades.iloc[int(selected_review_index)].copy(deep=True)
        review_start, review_end = selected_trade_time_window(
            selected_trade,
            ohlcv_df=ohlcv_df,
            buffer_rows=review_buffer_rows,
        )
        if review_start is None or review_end is None:
            st.warning("The selected trade has no usable entry/exit timestamps.")
        else:
            review_ohlcv = clip_by_time_window(ohlcv_df, start=review_start, end=review_end)
            review_levels = clip_by_time_window(
                st.session_state.get("levels"),
                start=review_start,
                end=review_end,
            )
            review_zones = clip_by_time_window(
                st.session_state.get("confluence_zones"),
                start=review_start,
                end=review_end,
            )
            review_chart = build_trade_review_chart(
                review_ohlcv,
                selected_trade,
                levels=review_levels,
                confluence_zones=review_zones,
                show_sessions=review_show_sessions,
                show_levels=review_show_levels,
                show_confluence_zones=review_show_zones,
                show_final_stop=review_show_final_stop,
            )
            st.plotly_chart(review_chart, width="stretch")
            st.caption(
                f"Bounded payload: {len(review_ohlcv):,} OHLC rows "
                f"({review_buffer_rows} bars before/after the trade)."
            )

        loss_count = int(
            st.number_input(
                "Worst losing trades to export",
                min_value=1,
                max_value=20,
                value=5,
                step=1,
            )
        )
        export_signature = trade_review_export_signature(
            trades,
            count=loss_count,
            buffer_rows=review_buffer_rows,
            show_sessions=review_show_sessions,
            show_levels=review_show_levels,
            show_confluence_zones=review_show_zones,
            show_final_stop=review_show_final_stop,
            ohlcv_df=ohlcv_df,
            levels=st.session_state.get("levels"),
            confluence_zones=st.session_state.get("confluence_zones"),
        )
        if st.button("Prepare worst-loser PNG export", type="secondary"):
            try:
                with st.spinner("Rendering bounded trade-review PNGs…"):
                    export_bytes = export_worst_loser_review_pngs(
                        trades,
                        ohlcv_df,
                        count=loss_count,
                        buffer_rows=review_buffer_rows,
                        levels=st.session_state.get("levels"),
                        confluence_zones=st.session_state.get("confluence_zones"),
                        show_sessions=review_show_sessions,
                        show_levels=review_show_levels,
                        show_confluence_zones=review_show_zones,
                        show_final_stop=review_show_final_stop,
                    )
                st.session_state["trade_review_export_zip"] = export_bytes
                st.session_state["trade_review_export_signature"] = export_signature
            except (ValueError, RuntimeError) as exc:
                st.error(f"Could not render PNG export: {exc}")
        export_bytes = st.session_state.get("trade_review_export_zip")
        if (
            isinstance(export_bytes, bytes)
            and st.session_state.get("trade_review_export_signature") == export_signature
        ):
            st.download_button(
                "Download worst-loser trade reviews (.zip)",
                data=export_bytes,
                file_name="worst_loser_trade_reviews.zip",
                mime="application/zip",
            )

# Optional execution chart
st.subheader("Backtest execution visualizer")
show_chart = st.toggle("Show candlestick trade visualizer", value=False)
if show_chart:
    chart_range_options = [
        "First trade ± 100 bars",
        "All trades range",
        "Last 10,000 rows",
        "Custom date range",
        "Full dataset",
    ]
    default_chart_range = "First trade ± 100 bars" if has_trades else "Last 10,000 rows"
    chart_range = st.selectbox(
        "Chart range",
        options=chart_range_options,
        index=chart_range_options.index(default_chart_range),
    )
    st.caption(
        "Chart range affects visualization only. Tables, saved artifacts, and backtest metrics remain unchanged."
    )

    show_sessions = st.toggle("Show session context", value=True)
    show_levels = st.toggle("Show levels", value=True)
    show_confluence_zones = st.toggle("Show confluence zones", value=True)
    show_sl_tp = st.toggle("Show SL/TP lines", value=True)
    if ohlcv_df is None or ohlcv_df.empty:
        st.info("No OHLCV data available to render the candlestick chart.")
    else:
        levels_df = st.session_state.get("levels")
        confluence_zones = st.session_state.get("confluence_zones")

        chart_start = None
        chart_end = None
        if chart_range == "First trade ± 100 bars" and has_trades:
            chart_start, chart_end = trade_time_window(trades, ohlcv_df=ohlcv_df, buffer_rows=100)
            if chart_start is None or chart_end is None:
                chart_start, chart_end = recent_rows_window(ohlcv_df, rows=10_000)
        elif chart_range == "All trades range" and has_trades:
            entry_start, entry_end = timestamp_bounds(trades, timestamp_col="entry_timestamp")
            exit_start, exit_end = timestamp_bounds(trades, timestamp_col="exit_timestamp")
            trade_start_candidates = [ts for ts in [entry_start, exit_start] if ts is not None]
            trade_end_candidates = [ts for ts in [entry_end, exit_end] if ts is not None]
            if trade_start_candidates and trade_end_candidates:
                chart_start, chart_end = buffered_rows_window(
                    ohlcv_df,
                    start=min(trade_start_candidates),
                    end=max(trade_end_candidates),
                    buffer_rows=100,
                )
            if chart_start is None or chart_end is None:
                chart_start, chart_end = recent_rows_window(ohlcv_df, rows=10_000)
        elif chart_range == "Last 10,000 rows":
            chart_start, chart_end = recent_rows_window(ohlcv_df, rows=10_000)
        elif chart_range == "Custom date range":
            min_ts, max_ts = timestamp_bounds(ohlcv_df)
            if min_ts is not None and max_ts is not None:
                custom_cols = st.columns(2)
                custom_start_date = custom_cols[0].date_input(
                    "Custom chart start",
                    value=min_ts.date(),
                    min_value=min_ts.date(),
                    max_value=max_ts.date(),
                )
                custom_end_date = custom_cols[1].date_input(
                    "Custom chart end",
                    value=max_ts.date(),
                    min_value=min_ts.date(),
                    max_value=max_ts.date(),
                )
                chart_start = pd.Timestamp(custom_start_date)
                chart_end = (
                    pd.Timestamp(custom_end_date)
                    + pd.Timedelta(days=1)
                    - pd.Timedelta(nanoseconds=1)
                )

        chart_ohlcv_df = (
            ohlcv_df.copy(deep=True)
            if chart_range == "Full dataset"
            else clip_by_time_window(ohlcv_df, start=chart_start, end=chart_end)
        )
        chart_trades = (
            trades.copy(deep=True)
            if chart_range == "Full dataset"
            else _clip_trades_for_chart(trades, start=chart_start, end=chart_end)
        )
        chart_levels_df = (
            levels_df.copy(deep=True)
            if chart_range == "Full dataset" and levels_df is not None
            else clip_by_time_window(levels_df, start=chart_start, end=chart_end)
        )
        chart_confluence_zones = (
            confluence_zones.copy(deep=True)
            if chart_range == "Full dataset" and confluence_zones is not None
            else clip_by_time_window(confluence_zones, start=chart_start, end=chart_end)
        )

        chart = build_backtest_candlestick_chart(
            ohlcv_df=chart_ohlcv_df,
            trades=chart_trades,
            levels=chart_levels_df,
            confluence_zones=chart_confluence_zones,
            show_sessions=show_sessions,
            show_levels=show_levels,
            show_confluence_zones=show_confluence_zones,
            show_sl_tp=show_sl_tp,
        )
        st.plotly_chart(chart, width="stretch")
        if show_sessions:
            st.caption(
                "Session context: ETH regions are shaded and RTH starts are marked with dotted vertical lines."
            )
        st.info(
            "Execution visualization is based on OHLC bars. If SL and TP are both touched within one bar, "
            "engine assumptions determine the recorded outcome; the true intrabar path is unknown without tick data."
        )
