"""Classic Backtest sidebar settings (QR D-3 / QI-04-05).

Streamlit-free: callers pass ``st``. Widget keys and H7/H15 captions unchanged.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.analytics.entry_window import (
    ADMIT_ARMED_STATUS_BADGE,
    PROMOTE_ARMED_BANNER,
    clear_armed_entry_window,
)
from thesistester.backtest_page_helpers import (
    effective_no_new_entries_after as compute_effective_no_new_entries_after,
)
from thesistester.config import TIMEZONE_OPTIONS
from thesistester.entry_window_policy import RTH_SEGMENT_LABELS
from thesistester.execution_defaults import (
    ENTRY_WINDOW_MODE_OPTIONS,
    INTRABAR_MODEL_OPTIONS,
    collect_backtest_defaults,
    reset_backtest_session_keys,
)
from thesistester.persistence import (
    clear_backtest_defaults,
    save_backtest_defaults,
)


def render_backtest_sidebar(
    st: Any,
    *,
    instrument: str,
    tick_size: float,
    point_value: float,
    exchange_tz: str,
) -> dict[str, Any]:
    """Render Backtest sidebar widgets. Session keys unchanged."""
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
    effective_no_new_entries_after = compute_effective_no_new_entries_after(
        flat_by_session_close, no_new_entries_after
    )
    st.caption(
        "Locked composer fork: this page and Grid apply `no_new_entries_after` "
        "only when Flat by session close is on (disabled widget is forced None). "
        "`api.run_backtest` still applies a YAML cutoff when flatten is off "
        "(skip `after_entry_cutoff`)."
    )
    st.caption(
        "Locked composer fork: OTF and Admit clocks here use Data-page "
        "`exchange_timezone` (not this Session timezone widget) or the "
        "instrument exchange TZ. `api.run_backtest` always passes the "
        "instrument exchange TZ for OTF and Admit."
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
        help=(
            "Default `allow_all` counts overlapping signals independently, so "
            "trade count can exceed a one-position book. Under `allow_all` the "
            "skip table is empty by design for overlap — overlap is not recorded "
            "as skips (window/cutoff skips can still appear)."
        ),
    )
    st.caption(
        "`allow_all` (default) treats overlapping signals as independent fills. "
        "Skip table is empty by design for overlap — not a sign that nothing "
        "overlapped."
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
    with st.expander("Same-bar opposite direction (advanced)", expanded=False):
        same_bar_opposite_direction = st.selectbox(
            "Same-bar opposite-direction policy",
            options=["legacy", "skip_both", "raise"],
            index=0,
            key="backtest_same_bar_opposite_direction",
            help=(
                "Opt-in DA3 guard. Default `legacy` keeps today's signal_id "
                "tie-break. `skip_both` refuses both sides of a same-bar "
                "opposite pair under single_position / single_setup (same "
                "group key). `raise` fails the run on the first collision. "
                "No-op under allow_all and single_direction."
            ),
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

    return {
        "sl_ticks": sl_ticks,
        "tp_ticks": tp_ticks,
        "commission_per_side": commission_per_side,
        "slippage_ticks": slippage_ticks,
        "max_bars": max_bars,
        "allow_same_bar": allow_same_bar,
        "intrabar_model": intrabar_model,
        "subtimeframe_data": subtimeframe_data,
        "breakeven_after_r": breakeven_after_r,
        "trailing_after_r": trailing_after_r,
        "trailing_distance_ticks": trailing_distance_ticks,
        "flat_by_session_close": flat_by_session_close,
        "session_close_time": session_close_time,
        "session_timezone": session_timezone,
        "no_new_entries_after": no_new_entries_after,
        "effective_no_new_entries_after": effective_no_new_entries_after,
        "entry_window_config": entry_window_config,
        "exposure_policy": exposure_policy,
        "cooldown_bars_after_exit": cooldown_bars_after_exit,
        "same_bar_opposite_direction": same_bar_opposite_direction,
        "run_btn": run_btn,
    }
