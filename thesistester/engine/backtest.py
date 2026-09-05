"""Phase 5 — Bar-by-bar backtest engine.

Converts Phase 4 candidate signals into simulated trades using a single
fixed SL/TP configuration.

Design notes
------------
- Simple triggers (touch / reject / break / reclaim) enter at next-bar open
  to avoid look-ahead bias.
- ``3c`` signals with ``status="filled"`` enter at ``retrace_entry_price`` on
  ``entry_bar_index``. ``status="void"`` rows are skipped.
- The default resolves same-bar SL/TP ambiguity at SL (legacy pessimism).
  Opt-in deterministic OHLC-path and observed lower-timeframe models retain
  explicit residual-ambiguity diagnostics.
- Phase 5 is a single-risk-config backtest only; SL/TP grid search belongs
  to Phase 6.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import time
from typing import Any
from zoneinfo import ZoneInfoNotFoundError

import pandas as pd

from thesistester.entry_window_policy import (
    entry_window_contains,
    normalize_entry_window,
)

from .intrabar import (
    prepare_subtimeframe_context,
    prepare_subtimeframe_conservative_context,
    validate_intrabar_model,
)
from .sim_core import BarData, resolve_trade_bar
from .exit_management import (
    exit_management_enabled,
    initial_exit_management_state,
    policy_dict as exit_management_policy_dict,
    update_exit_management_after_bar,
    validate_exit_management_config,
)

# ---------------------------------------------------------------------------
# Trade output schema
# ---------------------------------------------------------------------------

_TRADE_COLUMNS: list[str] = [
    "trade_id",
    "signal_id",
    "trigger",
    "direction",
    "entry_timestamp",
    "entry_bar_index",
    "theoretical_entry_price",
    "entry_price",
    "entry_model",
    "exit_timestamp",
    "exit_bar_index",
    "theoretical_exit_price",
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
    "zone_mid",
    "level_count",
    "level_names",
    "trigger_variant",
    "is_muted",
    "is_sfp",
    "inside_candle_count",
    "level_source_mode",
    "mae_points",
    "mfe_points",
    "exposure_policy",
    "exposure_group_key",
    "cooldown_bars_after_exit",
    "status",
]

_SKIPPED_SIGNAL_COLUMNS: list[str] = [
    "signal_id",
    "bar_index",
    "entry_bar_index",
    "trigger",
    "direction",
    "exposure_policy",
    "exposure_group_key",
    "skip_reason",
    "blocking_trade_id",
    "blocking_exit_bar_index",
    "cooldown_bars_after_exit",
]

_VALID_EXPOSURE_POLICIES = {
    "allow_all",
    "single_position",
    "single_direction",
    "single_setup",
}

_INTRABAR_TRADE_COLUMNS = [
    "intrabar_model",
    "intrabar_resolution",
    "intrabar_parent_both_hit",
    "intrabar_ambiguous",
    "exit_subbar_timestamp",
]
_EXIT_MANAGEMENT_TRADE_COLUMNS = [
    "breakeven_after_r",
    "trailing_after_r",
    "trailing_distance_ticks",
    "initial_stop_price",
    "active_stop_price_at_exit",
    "final_stop_price",
    "stop_management_mode",
    "breakeven_activated_bar_index",
    "trailing_activated_bar_index",
    "stop_adjustment_count",
    "stop_adjustment_path",
    "exit_management_armed",
]


@dataclass(frozen=True)
class SimulationResult:
    """Detailed opt-in result preserving the legacy DataFrame/tuple API."""

    trades: pd.DataFrame
    skipped_signals: pd.DataFrame
    intrabar_diagnostic: dict[str, Any]
    exit_management_diagnostic: dict[str, Any]
    direction_collision_diagnostic: dict[str, Any] = field(default_factory=dict)


def _empty_trades_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_TRADE_COLUMNS)


def _empty_skipped_signals_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_SKIPPED_SIGNAL_COLUMNS)


def _intrabar_diagnostic(
    *,
    model: str,
    trade_count: int,
    bracket_exit_count: int,
    both_hit_count: int,
    ambiguous_count: int,
    affected_bars: set[int],
    proximity_tie_count: int,
    subtimeframe_resolved_count: int,
    subtimeframe_fallback_exit_count: int,
    subtimeframe_fallback_bars: list[dict[str, object]],
    subtimeframe_interval: pd.Timedelta | None,
) -> dict[str, Any]:
    denominator = bracket_exit_count
    return {
        "schema_version": 1,
        "intrabar_model": model,
        "trade_count": int(trade_count),
        "bracket_exit_trade_count": int(bracket_exit_count),
        "same_bar_both_hit_count": int(both_hit_count),
        "same_bar_both_hit_pct": (float(both_hit_count / denominator) if denominator > 0 else 0.0),
        "same_bar_both_hit_denominator": "bracket_exit_trade_count",
        "ambiguous_resolution_count": int(ambiguous_count),
        "bars_affected_count": int(len(affected_bars)),
        "bars_affected": sorted(affected_bars),
        "path_proximity_tie_count": int(proximity_tie_count),
        "subtimeframe_resolved_count": int(subtimeframe_resolved_count),
        "subtimeframe_fallback_exit_count": int(subtimeframe_fallback_exit_count),
        "subtimeframe_fallback_parent_bars": subtimeframe_fallback_bars,
        "subtimeframe_fallback_parent_count": int(len(subtimeframe_fallback_bars)),
        "subtimeframe_interval": (
            str(subtimeframe_interval) if subtimeframe_interval is not None else None
        ),
    }


def _exit_management_diagnostic(
    *,
    breakeven_after_r: float | None,
    trailing_after_r: float | None,
    trailing_distance_ticks: float | None,
    trade_count: int,
    trades_with_exit_mgmt_count: int,
    be_exit_count: int,
    trail_exit_count: int,
    stop_adjustment_count: int,
) -> dict[str, Any]:
    return {
        **exit_management_policy_dict(
            breakeven_after_r=breakeven_after_r,
            trailing_after_r=trailing_after_r,
            trailing_distance_ticks=trailing_distance_ticks,
        ),
        "trade_count": int(trade_count),
        "trades_with_exit_mgmt_count": int(trades_with_exit_mgmt_count),
        "trades_with_exit_mgmt_pct": (
            float(trades_with_exit_mgmt_count / trade_count) if trade_count > 0 else 0.0
        ),
        "be_exit_count": int(be_exit_count),
        "trail_exit_count": int(trail_exit_count),
        "stop_adjustment_count": int(stop_adjustment_count),
        "average_stop_adjustments_per_trade": (
            float(stop_adjustment_count / trade_count) if trade_count > 0 else 0.0
        ),
    }


def _empty_direction_collision_diagnostic(*, policy: str = "legacy") -> dict[str, Any]:
    return {
        "policy": policy,
        "candidate_pairs": 0,
        "resolved_long": 0,
        "resolved_short": 0,
        "resolved_none": 0,
        "accepted_trade_share_from_pairs": 0.0,
    }


def _direction_collision_diagnostic(
    *,
    ordered_candidates: list[dict[str, Any]],
    accepted_trades: list[dict[str, Any]],
    policy: str = "legacy",
) -> dict[str, Any]:
    """Count same-entry-bar opposite-direction candidate groups and their admission.

    Grouping is ``(entry_bar_index, bar_idx)`` (bar-level, not per-zone).
    ``resolved_long`` and ``resolved_short`` are not a partition: both sides
    of a pair may fill under ``allow_all`` / ``single_direction``.
    Computed from candidates + accepted trades so the counts do not depend
    on skip-capture flags.
    """
    empty = _empty_direction_collision_diagnostic(policy=policy)
    if not ordered_candidates:
        return empty

    groups: dict[tuple[int, int], set[str]] = defaultdict(set)
    candidate_key_by_signal: dict[int, tuple[int, int]] = {}
    for row in ordered_candidates:
        key = (int(row["entry_bar_index"]), int(row["bar_idx"]))
        groups[key].add(str(row["direction"]))
        candidate_key_by_signal[int(row["sig"]["signal_id"])] = key

    pair_keys = {key for key, directions in groups.items() if {"long", "short"} <= directions}
    if not pair_keys:
        return {
            **empty,
            "accepted_trade_share_from_pairs": 0.0,
        }

    accepted_dirs_by_pair: dict[tuple[int, int], set[str]] = defaultdict(set)
    accepted_from_pairs = 0
    for trade in accepted_trades:
        key = candidate_key_by_signal.get(int(trade["signal_id"]))
        if key is None or key not in pair_keys:
            continue
        accepted_dirs_by_pair[key].add(str(trade["direction"]))
        accepted_from_pairs += 1

    resolved_long = sum(1 for key in pair_keys if "long" in accepted_dirs_by_pair[key])
    resolved_short = sum(1 for key in pair_keys if "short" in accepted_dirs_by_pair[key])
    resolved_none = sum(1 for key in pair_keys if not accepted_dirs_by_pair[key])
    trade_count = len(accepted_trades)
    return {
        "policy": policy,
        "candidate_pairs": len(pair_keys),
        "resolved_long": resolved_long,
        "resolved_short": resolved_short,
        "resolved_none": resolved_none,
        "accepted_trade_share_from_pairs": (
            float(accepted_from_pairs / trade_count) if trade_count > 0 else 0.0
        ),
    }


_TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")


def _parse_time_input(value: str | None, *, field_name: str) -> time | None:
    """Parse HH:MM or HH:MM:SS time input."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if _TIME_RE.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be HH:MM or HH:MM:SS, got {value!r}")
    try:
        parsed = time.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be HH:MM or HH:MM:SS, got {value!r}") from exc
    return parsed.replace(tzinfo=None)


def _timestamps_in_session_timezone(
    timestamps: pd.Series, session_timezone: str | None
) -> pd.Series:
    """Return timestamps converted/localized to session timezone when provided."""
    ts = pd.to_datetime(timestamps, errors="coerce")
    if ts.isna().any():
        raise ValueError("df['timestamp'] contains invalid timestamps.")

    if ts.dt.tz is None:
        if session_timezone:
            try:
                return ts.dt.tz_localize(session_timezone)
            except (TypeError, ValueError, KeyError, ZoneInfoNotFoundError) as exc:
                raise ValueError(f"Invalid session_timezone {session_timezone!r}") from exc
        return ts

    if session_timezone:
        try:
            return ts.dt.tz_convert(session_timezone)
        except (TypeError, ValueError, KeyError, ZoneInfoNotFoundError) as exc:
            raise ValueError(f"Invalid session_timezone {session_timezone!r}") from exc
    return ts


def _stringify_setup_value(value: object) -> str:
    if isinstance(value, (list, tuple, set)):
        return "|".join(str(v) for v in value)
    return str(value).strip()


def _is_nonempty(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return True


def _exposure_group_key(
    sig: pd.Series,
    *,
    exposure_policy: str,
    trigger: str,
    direction: str,
) -> str:
    if exposure_policy == "single_position":
        return "position"
    if exposure_policy == "single_direction":
        return direction
    if exposure_policy == "single_setup":
        setup_candidates = [
            ("setup_name", sig.get("setup_name")),
            ("zone_id", sig.get("zone_id")),
            ("level_source_label", sig.get("level_source_label")),
            ("level_names", sig.get("level_names")),
        ]
        for label, raw_value in setup_candidates:
            if _is_nonempty(raw_value):
                return f"{label}:{_stringify_setup_value(raw_value)}"
        return f"trigger_direction:{trigger}|{direction}"
    return "allow_all"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def simulate_trades(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    tick_size: float,
    point_value: float,
    stop_loss_ticks: int | float,
    take_profit_ticks: int | float,
    max_holding_bars: int | None = None,
    allow_same_bar_exit: bool = True,
    commission_per_side: float = 0.0,
    slippage_ticks: float = 0.0,
    flat_by_session_close: bool = False,
    session_close_time: str | None = None,
    session_timezone: str | None = None,
    no_new_entries_after: str | None = None,
    exposure_policy: str = "allow_all",
    cooldown_bars_after_exit: int = 0,
    return_skipped_signals: bool = False,
    *,
    entry_window: dict[str, Any] | None = None,
    entry_window_exchange_tz: str | None = None,
    intrabar_model: str = "sl_first",
    subtimeframe_data: pd.DataFrame | None = None,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
    breakeven_after_r: float | None = None,
    trailing_after_r: float | None = None,
    trailing_distance_ticks: float | None = None,
    return_result: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame] | SimulationResult:
    """Simulate bar-by-bar trades from Phase 4 candidate signals.

    Parameters
    ----------
    df:
        Canonical OHLCV DataFrame (``timestamp``, ``open``, ``high``,
        ``low``, ``close``, ``volume``).  Will be reset-indexed internally.
    signals:
        Phase 4 signal DataFrame from ``generate_signals``.
    tick_size:
        Instrument tick size (e.g. 0.25 for ES/NQ).
    point_value:
        Dollar value per point (e.g. 50 for ES, 20 for NQ).
    stop_loss_ticks:
        Fixed stop-loss distance in ticks from entry.  Must be > 0.
    take_profit_ticks:
        Fixed take-profit distance in ticks from entry.
    max_holding_bars:
        If provided, force-close at this many bars after entry (TIME exit).
        ``None`` means hold until SL/TP or end of data.
    allow_same_bar_exit:
        If ``True`` (default), SL/TP checks begin on the entry bar itself.
        This matters for ``confirm_3bar`` filled entries where the bar is
        already closed.  Uses the SL-first pessimistic rule when both are
        reachable in the same bar.
    commission_per_side:
        Optional per-side commission in account currency. Must be >= 0.
    slippage_ticks:
        Optional adverse slippage in ticks applied at both entry and exit.
        Must be >= 0.
    flat_by_session_close:
        If ``True``, cap each trade's exit walk at the configured session close
        for **that** trade's entry calendar date (per-candidate
        ``entry_local_ts``); otherwise preserve legacy dataset-end behavior.
    session_close_time:
        Session close clock time (HH:MM or HH:MM:SS). Required when
        ``flat_by_session_close=True``.
    session_timezone:
        Timezone used to interpret session-close and entry-cutoff times.
        Naive timestamps are localized; aware timestamps are converted.
    no_new_entries_after:
        Optional local-time cutoff (HH:MM or HH:MM:SS). Entries whose local
        entry timestamp is later than this cutoff are skipped (strict ``>``;
        entry **at** cutoff still admits). When skip capture is on, rejects
        are recorded as ``after_entry_cutoff`` (SW2b). Combined with
        ``entry_window`` via AND (C9); window is evaluated first for labeling.

    exposure_policy:
        Exposure gate applied to executable signals. One of:
        ``allow_all``, ``single_position``, ``single_direction``,
        ``single_setup``.
    cooldown_bars_after_exit:
        Optional cooldown bars after a blocking trade exit. Must be >= 0.
    return_skipped_signals:
        If ``True``, returns ``(trades_df, skipped_signals_df)`` where skipped
        signals include exposure-policy rejections and, when capture is on,
        ``outside_entry_window`` / ``after_entry_cutoff`` admission rejects and
        ``empty_session_close_cap`` when flatten finds no bar at or before the
        per-entry close.
    entry_window:
        Optional opt-in entry-time admission window (SW2). ``None`` /
        disabled preserves legacy all-day admission. When enabled, membership
        uses **entry-bar** local time (C2) via
        :func:`~thesistester.entry_window_policy.normalize_entry_window`
        (also re-exported from :mod:`thesistester.analytics.entry_window`).
        Rejected candidates never enter exposure competition (C6).
    entry_window_exchange_tz:
        Instrument exchange/session timezone used for RTH-segment membership
        and naive-timestamp localization (C5). Distinct from
        ``session_timezone`` (session-close / cutoff clocks). When omitted,
        falls back to ``session_timezone`` or ``America/New_York``.
    intrabar_model:
        ``"sl_first"`` preserves legacy pessimistic behavior.
        ``"path_open_proximity"`` walks a deterministic OHLC path beginning
        with the extreme nearest the open. ``"subtimeframe"`` walks validated
        lower-timeframe bars supplied through ``subtimeframe_data``.
    subtimeframe_data:
        Strictly finer OHLC data covering and reconciling every parent bar.
        Required only by ``intrabar_model="subtimeframe"``.
    parent_interval / sub_interval:
        Optional declared bar intervals (``Timedelta`` or compact labels like
        ``1min`` / ``15s``). When omitted, intervals are inferred from
        timestamp gaps. Sparse 15s-primary sources should pass the derivation
        intervals so quiet minutes do not coarsen the sub-bar grid.
    breakeven_after_r:
        Optional completed-bar favorable excursion threshold that moves the
        active stop to the slipped entry price on the next bar.
    trailing_after_r:
        Optional completed-bar favorable excursion threshold that arms a
        monotonic trailing stop on the next bar.
    trailing_distance_ticks:
        Required when ``trailing_after_r`` is provided. Distance from the
        best favorable parent-bar extreme, in ticks.
    return_result:
        Return :class:`SimulationResult` with skipped signals, a run-level
        intrabar diagnostic, and an in-memory direction-collision diagnostic.
        Default ``False`` preserves the legacy return API.

    Returns
    -------
    pd.DataFrame, tuple, or SimulationResult
        Trades DataFrame by default; optional tuple when
        ``return_skipped_signals=True``; detailed result when
        ``return_result=True``.

    Raises
    ------
    ValueError
        If ``stop_loss_ticks <= 0``, price/risk inputs are invalid, cost inputs
        are negative, time/session policy inputs are invalid, exposure policy
        is invalid, or cooldown is negative.

    Notes
    -----
    - Default SL/TP precedence is unchanged: SL-first pessimism applies when
      both are reachable in the same bar.
    - Default mode keeps legacy ``EOD`` semantics (last bar in loaded data).
    - Session-aware mode can produce ``SESSION_CLOSE``; ``DATA_END`` means data
      ended before a configured session-close bar was available.
    - R1 execution costs (slippage/commission) still apply to ``SESSION_CLOSE``,
      ``TIME``, ``DATA_END``, and ``EOD`` exits.
    """
    if stop_loss_ticks <= 0:
        raise ValueError(f"stop_loss_ticks must be > 0, got {stop_loss_ticks!r}")
    if tick_size <= 0:
        raise ValueError(f"tick_size must be > 0, got {tick_size!r}")
    if point_value <= 0:
        raise ValueError(f"point_value must be > 0, got {point_value!r}")
    if commission_per_side < 0:
        raise ValueError(f"commission_per_side must be >= 0, got {commission_per_side!r}")
    if slippage_ticks < 0:
        raise ValueError(f"slippage_ticks must be >= 0, got {slippage_ticks!r}")
    if exposure_policy not in _VALID_EXPOSURE_POLICIES:
        raise ValueError(
            f"exposure_policy must be one of {sorted(_VALID_EXPOSURE_POLICIES)!r}, "
            f"got {exposure_policy!r}"
        )
    if cooldown_bars_after_exit < 0:
        raise ValueError(f"cooldown_bars_after_exit must be >= 0, got {cooldown_bars_after_exit!r}")
    validate_intrabar_model(intrabar_model)
    validate_exit_management_config(
        breakeven_after_r=breakeven_after_r,
        trailing_after_r=trailing_after_r,
        trailing_distance_ticks=trailing_distance_ticks,
    )
    exit_management_active = exit_management_enabled(
        breakeven_after_r=breakeven_after_r,
        trailing_after_r=trailing_after_r,
        trailing_distance_ticks=trailing_distance_ticks,
    )
    parsed_session_close = _parse_time_input(session_close_time, field_name="session_close_time")
    if flat_by_session_close and parsed_session_close is None:
        raise ValueError("flat_by_session_close=True requires a valid session_close_time.")
    parsed_no_new_entries_after = _parse_time_input(
        no_new_entries_after, field_name="no_new_entries_after"
    )
    # C5: RTH / naive basis is instrument exchange TZ, not session-close TZ.
    exchange_tz_for_window = entry_window_exchange_tz or session_timezone or "America/New_York"
    try:
        normalized_entry_window = normalize_entry_window(
            entry_window, exchange_tz=exchange_tz_for_window
        )
    except ValueError as exc:
        raise ValueError(f"Invalid entry_window: {exc}") from exc

    if signals is None or signals.empty:
        empty_trades = _empty_trades_df()
        empty_skipped = _empty_skipped_signals_df()
        if return_result:
            return SimulationResult(
                trades=empty_trades,
                skipped_signals=empty_skipped,
                intrabar_diagnostic=_intrabar_diagnostic(
                    model=intrabar_model,
                    trade_count=0,
                    bracket_exit_count=0,
                    both_hit_count=0,
                    ambiguous_count=0,
                    affected_bars=set(),
                    proximity_tie_count=0,
                    subtimeframe_resolved_count=0,
                    subtimeframe_fallback_exit_count=0,
                    subtimeframe_fallback_bars=[],
                    subtimeframe_interval=None,
                ),
                exit_management_diagnostic=_exit_management_diagnostic(
                    breakeven_after_r=breakeven_after_r,
                    trailing_after_r=trailing_after_r,
                    trailing_distance_ticks=trailing_distance_ticks,
                    trade_count=0,
                    trades_with_exit_mgmt_count=0,
                    be_exit_count=0,
                    trail_exit_count=0,
                    stop_adjustment_count=0,
                ),
                direction_collision_diagnostic=_empty_direction_collision_diagnostic(),
            )
        if return_skipped_signals:
            return empty_trades, empty_skipped
        return empty_trades

    df_reset = df.reset_index(drop=True)
    n_bars = len(df_reset)
    bars = BarData.from_frame(df_reset)
    local_timestamps = _timestamps_in_session_timezone(
        df_reset["timestamp"], session_timezone=session_timezone
    )
    if intrabar_model == "subtimeframe":
        subtimeframe_context = prepare_subtimeframe_context(
            df_reset,
            subtimeframe_data,
            tick_size=float(tick_size),
            parent_interval=parent_interval,
            sub_interval=sub_interval,
        )
    elif intrabar_model == "subtimeframe_conservative":
        subtimeframe_context = prepare_subtimeframe_conservative_context(
            df_reset,
            subtimeframe_data,
            tick_size=float(tick_size),
            parent_interval=parent_interval,
            sub_interval=sub_interval,
        )
    else:
        subtimeframe_context = None

    sl_pts = float(stop_loss_ticks) * float(tick_size)
    tp_pts = float(take_profit_ticks) * float(tick_size)
    slip_pts = float(slippage_ticks) * float(tick_size)
    total_commission_cost = 2.0 * float(commission_per_side)
    risk_currency = float(stop_loss_ticks) * float(tick_size) * float(point_value)

    trades: list[dict] = []
    skipped_signals: list[dict] = []
    trade_id = 0
    candidate_rows: list[dict] = []
    bracket_exit_count = 0
    both_hit_count = 0
    ambiguous_count = 0
    affected_bars: set[int] = set()
    proximity_tie_count = 0
    subtimeframe_resolved_count = 0
    subtimeframe_fallback_exit_count = 0
    be_exit_count = 0
    trail_exit_count = 0
    trades_with_exit_mgmt_count = 0
    total_stop_adjustment_count = 0

    for _, sig in signals.iterrows():
        trigger = str(sig["trigger"])
        direction = str(sig["direction"])
        bar_idx = int(sig["bar_index"])

        # ------------------------------------------------------------------
        # Determine entry bar and price
        # ------------------------------------------------------------------
        if trigger == "3c":
            if str(sig.get("status", "")) != "filled":
                # Void 3c signals are skipped.
                continue
            entry_bar_index = int(sig["entry_bar_index"])
            if entry_bar_index >= n_bars:
                continue
            theoretical_entry_price = float(sig["retrace_entry_price"])
            entry_model = "3c_retrace_market"
        elif trigger == "confirm_3bar":
            if str(sig.get("status", "")) != "filled":
                continue
            entry_bar_index = bar_idx
            theoretical_entry_price = float(sig["entry_reference_price"])
            entry_model = "bar3_stop_limit_fill"
        else:
            # Simple triggers enter at next-bar open (no look-ahead).
            entry_bar_index = bar_idx + 1
            if entry_bar_index >= n_bars:
                continue
            theoretical_entry_price = float(df_reset["open"].iloc[entry_bar_index])
            entry_model = "next_bar_open"

        if direction == "long":
            entry_price = theoretical_entry_price + slip_pts
        else:
            entry_price = theoretical_entry_price - slip_pts

        entry_ts = df_reset["timestamp"].iloc[entry_bar_index]
        entry_local_ts = local_timestamps.iloc[entry_bar_index]

        # C9 AND admission: both entry_window and no_new_entries_after apply.
        # Evaluate window before cutoff so dual-failures label as
        # outside_entry_window (C9: prefer entry_window for new UX). Trades are
        # identical either order — only skip_reason labeling differs.
        #
        # C5: classify window membership on the raw entry-bar timestamp with
        # exchange-TZ naive semantics. Do not reuse session-localized clocks —
        # those are reserved for session-close / no_new_entries_after only.
        if normalized_entry_window["enabled"] and not entry_window_contains(
            entry_ts,
            normalized_entry_window,
            exchange_tz=exchange_tz_for_window,
        ):
            if return_skipped_signals or return_result:
                skipped_signals.append(
                    {
                        "signal_id": int(sig["signal_id"]),
                        "bar_index": bar_idx,
                        "entry_bar_index": entry_bar_index,
                        "trigger": trigger,
                        "direction": direction,
                        "exposure_policy": exposure_policy,
                        "exposure_group_key": _exposure_group_key(
                            sig,
                            exposure_policy=exposure_policy,
                            trigger=trigger,
                            direction=direction,
                        ),
                        "skip_reason": "outside_entry_window",
                        "blocking_trade_id": pd.NA,
                        "blocking_exit_bar_index": pd.NA,
                        "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
                    }
                )
            continue

        if (
            parsed_no_new_entries_after is not None
            and entry_local_ts.time() > parsed_no_new_entries_after
        ):
            # SW2b: audit cutoff rejects when skip capture is on. Admission
            # outcome is unchanged (still not a trade); golden/default path
            # with return_result=False stays trades-identical.
            if return_skipped_signals or return_result:
                skipped_signals.append(
                    {
                        "signal_id": int(sig["signal_id"]),
                        "bar_index": bar_idx,
                        "entry_bar_index": entry_bar_index,
                        "trigger": trigger,
                        "direction": direction,
                        "exposure_policy": exposure_policy,
                        "exposure_group_key": _exposure_group_key(
                            sig,
                            exposure_policy=exposure_policy,
                            trigger=trigger,
                            direction=direction,
                        ),
                        "skip_reason": "after_entry_cutoff",
                        "blocking_trade_id": pd.NA,
                        "blocking_exit_bar_index": pd.NA,
                        "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
                    }
                )
            continue

        candidate_rows.append(
            {
                "sig": sig,
                "trigger": trigger,
                "direction": direction,
                "bar_idx": bar_idx,
                "entry_bar_index": entry_bar_index,
                "entry_ts": entry_ts,
                "entry_local_ts": entry_local_ts,
                "theoretical_entry_price": theoretical_entry_price,
                "entry_price": entry_price,
                "entry_model": entry_model,
                "exposure_group_key": _exposure_group_key(
                    sig,
                    exposure_policy=exposure_policy,
                    trigger=trigger,
                    direction=direction,
                ),
            }
        )

    if exposure_policy == "allow_all":
        ordered_candidates = candidate_rows
    else:
        ordered_candidates = sorted(
            candidate_rows,
            key=lambda row: (
                int(row["entry_bar_index"]),
                int(row["bar_idx"]),
                int(row["sig"]["signal_id"]),
            ),
        )

    accepted_for_blocking: list[dict] = []
    for candidate in ordered_candidates:
        sig = candidate["sig"]
        trigger = candidate["trigger"]
        direction = candidate["direction"]
        bar_idx = int(candidate["bar_idx"])
        entry_bar_index = int(candidate["entry_bar_index"])
        entry_ts = candidate["entry_ts"]
        entry_local_ts = candidate["entry_local_ts"]
        theoretical_entry_price = float(candidate["theoretical_entry_price"])
        entry_price = float(candidate["entry_price"])
        entry_model = str(candidate["entry_model"])
        exposure_group_key = str(candidate["exposure_group_key"])

        if exposure_policy == "single_position":
            relevant_prior = accepted_for_blocking
        elif exposure_policy == "single_direction":
            relevant_prior = [
                prior for prior in accepted_for_blocking if prior["direction"] == direction
            ]
        elif exposure_policy == "single_setup":
            relevant_prior = [
                prior
                for prior in accepted_for_blocking
                if prior["exposure_group_key"] == exposure_group_key
            ]
        else:
            relevant_prior = []

        blockers = [
            prior
            for prior in relevant_prior
            if entry_bar_index <= (int(prior["exit_bar_index"]) + cooldown_bars_after_exit)
        ]
        if blockers:
            blocker = sorted(
                blockers,
                key=lambda prior: (-int(prior["exit_bar_index"]), int(prior["trade_id"])),
            )[0]
            blocker_exit_bar_index = int(blocker["exit_bar_index"])
            if entry_bar_index > blocker_exit_bar_index:
                skip_reason = "cooldown_active"
            elif exposure_policy == "single_position":
                skip_reason = "overlapping_position"
            elif exposure_policy == "single_direction":
                skip_reason = "overlapping_direction"
            else:
                skip_reason = "overlapping_setup"

            if return_skipped_signals or return_result:
                skipped_signals.append(
                    {
                        "signal_id": int(sig["signal_id"]),
                        "bar_index": bar_idx,
                        "entry_bar_index": entry_bar_index,
                        "trigger": trigger,
                        "direction": direction,
                        "exposure_policy": exposure_policy,
                        "exposure_group_key": exposure_group_key,
                        "skip_reason": skip_reason,
                        "blocking_trade_id": int(blocker["trade_id"]),
                        "blocking_exit_bar_index": blocker_exit_bar_index,
                        "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
                    }
                )
            continue

        # ------------------------------------------------------------------
        # Fixed SL / TP prices
        # ------------------------------------------------------------------
        if direction == "long":
            stop_price = entry_price - sl_pts
            target_price = entry_price + tp_pts
        else:
            stop_price = entry_price + sl_pts
            target_price = entry_price - tp_pts
        stop_state = initial_exit_management_state(
            initial_stop=stop_price,
            entry_price=entry_price,
            direction=direction,
        )

        # ------------------------------------------------------------------
        # Bar-by-bar exit walk
        # ------------------------------------------------------------------
        exit_bar_index: int | None = None
        theoretical_exit_price: float | None = None
        exit_price: float | None = None
        exit_reason: str | None = None
        intrabar_resolution = "not_evaluated"
        intrabar_parent_both_hit = False
        intrabar_ambiguous = False
        pending_intrabar_ambiguity = False
        exit_subbar_timestamp: pd.Timestamp | None = None

        # MAE / MFE tracking (adverse / favorable excursion in points)
        mae_pts = 0.0  # worst excursion against position
        mfe_pts = 0.0  # best excursion in favour of position

        start_bar = entry_bar_index if allow_same_bar_exit else entry_bar_index + 1

        max_bar = n_bars - 1
        time_cap_bar: int | None = None
        if max_holding_bars is not None:
            time_cap_bar = entry_bar_index + max_holding_bars - 1
            max_bar = min(max_bar, time_cap_bar)

        session_cap_bar: int | None = None
        data_end_before_session_close = False
        if flat_by_session_close:
            session_close_ts = entry_local_ts.normalize() + pd.Timedelta(
                hours=parsed_session_close.hour,
                minutes=parsed_session_close.minute,
                seconds=parsed_session_close.second,
            )
            bars_until_close = local_timestamps[
                (local_timestamps.index >= entry_bar_index) & (local_timestamps <= session_close_ts)
            ]
            if bars_until_close.empty:
                if return_skipped_signals or return_result:
                    skipped_signals.append(
                        {
                            "signal_id": int(sig["signal_id"]),
                            "bar_index": bar_idx,
                            "entry_bar_index": entry_bar_index,
                            "trigger": trigger,
                            "direction": direction,
                            "exposure_policy": exposure_policy,
                            "exposure_group_key": exposure_group_key,
                            "skip_reason": "empty_session_close_cap",
                            "blocking_trade_id": pd.NA,
                            "blocking_exit_bar_index": pd.NA,
                            "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
                        }
                    )
                continue
            session_cap_bar = int(bars_until_close.index[-1])
            max_bar = min(max_bar, session_cap_bar)
            last_available_ts = local_timestamps.iloc[n_bars - 1]
            data_end_before_session_close = (
                session_cap_bar == n_bars - 1 and last_available_ts < session_close_ts
            )

        if (
            exit_management_active
            and not allow_same_bar_exit
            and entry_model == "next_bar_open"
            and entry_bar_index < max_bar
        ):
            entry_bar = bars.at(entry_bar_index)
            stop_state = update_exit_management_after_bar(
                state=stop_state,
                direction=direction,
                entry_price=entry_price,
                initial_stop=stop_price,
                tick_size=tick_size,
                risk_points=sl_pts,
                bar_high=entry_bar.high,
                bar_low=entry_bar.low,
                bar_index=entry_bar_index,
                breakeven_after_r=breakeven_after_r,
                trailing_after_r=trailing_after_r,
                trailing_distance_ticks=trailing_distance_ticks,
            )

        for b in range(start_bar, max_bar + 1):
            bar, resolution = resolve_trade_bar(
                bars,
                bar_index=b,
                intrabar_model=intrabar_model,
                subtimeframe_context=subtimeframe_context,
                stop_price=stop_state.effective_stop,
                target_price=target_price,
                direction=direction,
                entry_activation_price=(
                    theoretical_entry_price
                    if b == entry_bar_index and trigger in {"3c", "confirm_3bar"}
                    else None
                ),
            )
            bar_low = bar.low
            bar_high = bar.high

            # Track MAE / MFE
            if direction == "long":
                excursion_adverse = entry_price - bar_low
                excursion_favorable = bar_high - entry_price
            else:
                excursion_adverse = bar_high - entry_price
                excursion_favorable = entry_price - bar_low

            mae_pts = max(mae_pts, excursion_adverse)
            mfe_pts = max(mfe_pts, excursion_favorable)

            pending_intrabar_ambiguity = pending_intrabar_ambiguity or resolution.ambiguous
            if resolution.exit_kind is not None:
                exit_bar_index = b
                theoretical_exit_price = (
                    stop_state.effective_stop if resolution.exit_kind == "SL" else target_price
                )
                if resolution.exit_kind == "SL" and stop_state.active_reason in {"BE", "TRAIL"}:
                    exit_reason = stop_state.active_reason
                elif intrabar_model == "sl_first":
                    exit_reason = resolution.exit_kind
                elif intrabar_model == "path_open_proximity":
                    exit_reason = f"{resolution.exit_kind}_intrabar_path"
                elif (
                    intrabar_model == "subtimeframe_conservative"
                    and resolution.subtimeframe_fallback
                ):
                    exit_reason = f"{resolution.exit_kind}_subtimeframe_fallback"
                else:
                    exit_reason = f"{resolution.exit_kind}_subtimeframe"
                intrabar_resolution = resolution.resolution
                intrabar_parent_both_hit = resolution.parent_both_hit
                intrabar_ambiguous = pending_intrabar_ambiguity
                exit_subbar_timestamp = resolution.exit_subbar_timestamp
                bracket_exit_count += 1
                if resolution.parent_both_hit:
                    both_hit_count += 1
                    affected_bars.add(b)
                if intrabar_ambiguous:
                    ambiguous_count += 1
                if resolution.proximity_tie:
                    proximity_tie_count += 1
                if intrabar_model in {"subtimeframe", "subtimeframe_conservative"}:
                    if resolution.subtimeframe_fallback:
                        subtimeframe_fallback_exit_count += 1
                    else:
                        subtimeframe_resolved_count += 1
                break
            can_update_exit_management = (
                entry_model == "next_bar_open" and b >= entry_bar_index
            ) or (entry_model != "next_bar_open" and b > entry_bar_index)
            if exit_management_active and can_update_exit_management and b < max_bar:
                stop_state = update_exit_management_after_bar(
                    state=stop_state,
                    direction=direction,
                    entry_price=entry_price,
                    initial_stop=stop_price,
                    tick_size=tick_size,
                    risk_points=sl_pts,
                    bar_high=bar_high,
                    bar_low=bar_low,
                    bar_index=b,
                    breakeven_after_r=breakeven_after_r,
                    trailing_after_r=trailing_after_r,
                    trailing_distance_ticks=trailing_distance_ticks,
                )

        if exit_bar_index is None:
            # No SL/TP hit — TIME or EOD
            if (
                max_holding_bars is not None
                and time_cap_bar is not None
                and max_bar == time_cap_bar
            ):
                exit_bar_index = max_bar
                theoretical_exit_price = bars.close[max_bar]
                exit_reason = "TIME"
                intrabar_resolution = "forced_time"
            elif flat_by_session_close:
                exit_bar_index = max_bar
                theoretical_exit_price = bars.close[max_bar]
                if (
                    data_end_before_session_close
                    and session_cap_bar is not None
                    and max_bar == session_cap_bar
                ):
                    exit_reason = "DATA_END"
                    intrabar_resolution = "forced_data_end"
                else:
                    exit_reason = "SESSION_CLOSE"
                    intrabar_resolution = "forced_session_close"
            else:
                exit_bar_index = n_bars - 1
                theoretical_exit_price = bars.close[n_bars - 1]
                exit_reason = "EOD"
                intrabar_resolution = "forced_eod"
            if pending_intrabar_ambiguity:
                intrabar_ambiguous = True
                ambiguous_count += 1

        if direction == "long":
            exit_price = float(theoretical_exit_price) - slip_pts
        else:
            exit_price = float(theoretical_exit_price) + slip_pts

        exit_ts = df_reset["timestamp"].iloc[exit_bar_index]

        # ------------------------------------------------------------------
        # P&L and R calculation
        # ------------------------------------------------------------------
        if direction == "long":
            theoretical_pnl_points = float(theoretical_exit_price) - theoretical_entry_price
            gross_pnl_points = float(exit_price) - entry_price
        else:
            theoretical_pnl_points = theoretical_entry_price - float(theoretical_exit_price)
            gross_pnl_points = entry_price - float(exit_price)

        gross_pnl_currency = gross_pnl_points * float(point_value)
        # Cost modeling is adverse-only: any favorable rounding/noise is floored at 0.
        slippage_cost = max(
            0.0,
            (theoretical_pnl_points - gross_pnl_points) * float(point_value),
        )
        # gross_pnl_currency already reflects entry+exit slippage via slipped fills.
        # Net P&L subtracts round-turn commissions on top of that gross value.
        net_pnl_currency = gross_pnl_currency - total_commission_cost
        r_multiple = net_pnl_currency / risk_currency  # risk_currency is > 0

        bars_held = exit_bar_index - entry_bar_index + 1

        trade = {
            "trade_id": trade_id,
            "signal_id": int(sig["signal_id"]),
            "trigger": trigger,
            "direction": direction,
            "entry_timestamp": entry_ts,
            "entry_bar_index": entry_bar_index,
            "theoretical_entry_price": theoretical_entry_price,
            "entry_price": entry_price,
            "entry_model": entry_model,
            "exit_timestamp": exit_ts,
            "exit_bar_index": exit_bar_index,
            "theoretical_exit_price": float(theoretical_exit_price),
            "exit_price": float(exit_price),
            "exit_reason": exit_reason,
            "stop_price": stop_price,
            "target_price": target_price,
            "stop_loss_ticks": stop_loss_ticks,
            "take_profit_ticks": take_profit_ticks,
            "gross_pnl_points": gross_pnl_points,
            "gross_pnl_currency": gross_pnl_currency,
            "commission_cost": total_commission_cost,
            "slippage_cost": slippage_cost,
            "net_pnl_currency": net_pnl_currency,
            "pnl_points": gross_pnl_points,
            "pnl_currency": net_pnl_currency,
            "r_multiple": r_multiple,
            "bars_held": bars_held,
            "zone_low": sig.get("zone_low"),
            "zone_high": sig.get("zone_high"),
            "zone_mid": sig.get("zone_mid"),
            "level_count": sig.get("level_count"),
            "level_names": sig.get("level_names"),
            "trigger_variant": sig.get("trigger_variant"),
            "is_muted": sig.get("is_muted"),
            "is_sfp": sig.get("is_sfp"),
            "inside_candle_count": sig.get("inside_candle_count"),
            "level_source_mode": sig.get("level_source_mode"),
            "mae_points": mae_pts,
            "mfe_points": mfe_pts,
            "exposure_policy": exposure_policy,
            "exposure_group_key": exposure_group_key,
            "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
            "status": "closed",
        }
        if intrabar_model != "sl_first":
            trade.update(
                {
                    "intrabar_model": intrabar_model,
                    "intrabar_resolution": intrabar_resolution,
                    "intrabar_parent_both_hit": intrabar_parent_both_hit,
                    "intrabar_ambiguous": intrabar_ambiguous,
                    "exit_subbar_timestamp": exit_subbar_timestamp,
                }
            )
        if exit_management_active:
            stop_management_mode = "fixed"
            if breakeven_after_r is not None and trailing_after_r is not None:
                stop_management_mode = "breakeven_trailing"
            elif breakeven_after_r is not None:
                stop_management_mode = "breakeven"
            elif trailing_after_r is not None:
                stop_management_mode = "trailing"
            exit_management_armed = stop_state.breakeven_armed or stop_state.trailing_armed
            trade.update(
                {
                    "breakeven_after_r": breakeven_after_r,
                    "trailing_after_r": trailing_after_r,
                    "trailing_distance_ticks": trailing_distance_ticks,
                    "initial_stop_price": stop_price,
                    "active_stop_price_at_exit": stop_state.effective_stop,
                    "final_stop_price": stop_state.effective_stop,
                    "stop_management_mode": stop_management_mode,
                    "breakeven_activated_bar_index": stop_state.breakeven_activated_bar_index,
                    "trailing_activated_bar_index": stop_state.trailing_activated_bar_index,
                    "stop_adjustment_count": stop_state.adjustment_count,
                    "stop_adjustment_path": "|".join(stop_state.adjustment_path),
                    "exit_management_armed": bool(exit_management_armed),
                }
            )
            if exit_management_armed:
                trades_with_exit_mgmt_count += 1
            if exit_reason == "BE":
                be_exit_count += 1
            if exit_reason == "TRAIL":
                trail_exit_count += 1
            total_stop_adjustment_count += int(stop_state.adjustment_count)
        trades.append(trade)
        accepted_for_blocking.append(
            {
                "trade_id": trade_id,
                "exit_bar_index": exit_bar_index,
                "direction": direction,
                "exposure_group_key": exposure_group_key,
            }
        )
        trade_id += 1

    trades_df = pd.DataFrame(trades) if trades else _empty_trades_df()
    if intrabar_model != "sl_first" and trades_df.empty:
        for column in _INTRABAR_TRADE_COLUMNS:
            trades_df[column] = pd.Series(dtype="object")
    if exit_management_active and trades_df.empty:
        for column in _EXIT_MANAGEMENT_TRADE_COLUMNS:
            trades_df[column] = pd.Series(dtype="object")
    skipped_df = pd.DataFrame(skipped_signals) if skipped_signals else _empty_skipped_signals_df()
    if return_result:
        return SimulationResult(
            trades=trades_df,
            skipped_signals=skipped_df,
            intrabar_diagnostic=_intrabar_diagnostic(
                model=intrabar_model,
                trade_count=len(trades_df),
                bracket_exit_count=bracket_exit_count,
                both_hit_count=both_hit_count,
                ambiguous_count=ambiguous_count,
                affected_bars=affected_bars,
                proximity_tie_count=proximity_tie_count,
                subtimeframe_resolved_count=subtimeframe_resolved_count,
                subtimeframe_fallback_exit_count=subtimeframe_fallback_exit_count,
                subtimeframe_fallback_bars=(
                    subtimeframe_context.fallback_diagnostics(df_reset)
                    if subtimeframe_context is not None
                    else []
                ),
                subtimeframe_interval=(
                    subtimeframe_context.sub_interval if subtimeframe_context is not None else None
                ),
            ),
            exit_management_diagnostic=_exit_management_diagnostic(
                breakeven_after_r=breakeven_after_r,
                trailing_after_r=trailing_after_r,
                trailing_distance_ticks=trailing_distance_ticks,
                trade_count=len(trades_df),
                trades_with_exit_mgmt_count=trades_with_exit_mgmt_count,
                be_exit_count=be_exit_count,
                trail_exit_count=trail_exit_count,
                stop_adjustment_count=total_stop_adjustment_count,
            ),
            direction_collision_diagnostic=_direction_collision_diagnostic(
                ordered_candidates=ordered_candidates,
                accepted_trades=trades,
                policy="legacy",
            ),
        )
    if return_skipped_signals:
        return trades_df, skipped_df
    return trades_df
