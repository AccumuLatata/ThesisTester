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
from .sim_core import BarData, TradeExitWalk, compute_session_close_cap, walk_trade_exit
from .exit_management import (
    exit_management_enabled,
    policy_dict as exit_management_policy_dict,
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

# Skip / exit tokens (C-18 / QI-04-09). String values are frozen for goldens.
SKIP_OUTSIDE_ENTRY_WINDOW = "outside_entry_window"
SKIP_AFTER_ENTRY_CUTOFF = "after_entry_cutoff"
SKIP_DIRECTION_CONFLICT = "direction_conflict"
SKIP_COOLDOWN_ACTIVE = "cooldown_active"
SKIP_OVERLAPPING_POSITION = "overlapping_position"
SKIP_OVERLAPPING_DIRECTION = "overlapping_direction"
SKIP_OVERLAPPING_SETUP = "overlapping_setup"
SKIP_EMPTY_SESSION_CLOSE_CAP = "empty_session_close_cap"

SKIP_REASONS: frozenset[str] = frozenset(
    {
        SKIP_OUTSIDE_ENTRY_WINDOW,
        SKIP_AFTER_ENTRY_CUTOFF,
        SKIP_DIRECTION_CONFLICT,
        SKIP_COOLDOWN_ACTIVE,
        SKIP_OVERLAPPING_POSITION,
        SKIP_OVERLAPPING_DIRECTION,
        SKIP_OVERLAPPING_SETUP,
        SKIP_EMPTY_SESSION_CLOSE_CAP,
    }
)

EXIT_SL = "SL"
EXIT_TP = "TP"
EXIT_BE = "BE"
EXIT_TRAIL = "TRAIL"
EXIT_TIME = "TIME"
EXIT_DATA_END = "DATA_END"
EXIT_SESSION_CLOSE = "SESSION_CLOSE"
EXIT_EOD = "EOD"
EXIT_INTRABAR_PATH_SUFFIX = "_intrabar_path"
EXIT_SUBTIMEFRAME_SUFFIX = "_subtimeframe"
EXIT_SUBTIMEFRAME_FALLBACK_SUFFIX = "_subtimeframe_fallback"
EXIT_MANAGED_STOP_REASONS: frozenset[str] = frozenset({EXIT_BE, EXIT_TRAIL})

EXIT_REASONS: frozenset[str] = frozenset(
    {
        EXIT_SL,
        EXIT_TP,
        EXIT_BE,
        EXIT_TRAIL,
        EXIT_TIME,
        EXIT_DATA_END,
        EXIT_SESSION_CLOSE,
        EXIT_EOD,
        f"{EXIT_SL}{EXIT_INTRABAR_PATH_SUFFIX}",
        f"{EXIT_TP}{EXIT_INTRABAR_PATH_SUFFIX}",
        f"{EXIT_SL}{EXIT_SUBTIMEFRAME_SUFFIX}",
        f"{EXIT_TP}{EXIT_SUBTIMEFRAME_SUFFIX}",
        f"{EXIT_SL}{EXIT_SUBTIMEFRAME_FALLBACK_SUFFIX}",
        f"{EXIT_TP}{EXIT_SUBTIMEFRAME_FALLBACK_SUFFIX}",
    }
)


def _exit_reason_with_suffix(kind: str, suffix: str) -> str:
    """Compose an SL/TP path label. Result must be a member of ``EXIT_REASONS``."""
    reason = f"{kind}{suffix}"
    if reason not in EXIT_REASONS:
        raise ValueError(f"exit reason {reason!r} is not in EXIT_REASONS")
    return reason


_VALID_EXPOSURE_POLICIES = {
    "allow_all",
    "single_position",
    "single_direction",
    "single_setup",
}

VALID_SAME_BAR_OPPOSITE_DIRECTION = frozenset({"legacy", "skip_both", "raise"})

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
    skipped_signals: list[dict[str, Any]] | None = None,
    policy: str = "legacy",
) -> dict[str, Any]:
    """Count same-entry-bar opposite-direction candidate groups and their admission.

    Grouping is ``(entry_bar_index, bar_idx)`` (bar-level, not per-zone).
    Built after admission from ``ordered_candidates`` + accepted trades +
    skip-capture rows. Window/cutoff rejects never enter
    ``ordered_candidates``; they are recovered from ``skipped_signals`` so
    those pairs appear as ``resolved_none``. Occupancy / cooldown / later
    DA3 ``skip_both`` already sit in ``ordered_candidates``.
    ``resolved_long`` and ``resolved_short`` are not a partition: both sides
    of a pair may fill under ``allow_all`` / ``single_direction``.
    """
    empty = _empty_direction_collision_diagnostic(policy=policy)
    groups: dict[tuple[int, int], set[str]] = defaultdict(set)
    candidate_key_by_signal: dict[int, tuple[int, int]] = {}
    for row in ordered_candidates:
        key = (int(row["entry_bar_index"]), int(row["bar_idx"]))
        groups[key].add(str(row["direction"]))
        candidate_key_by_signal[int(row["sig"]["signal_id"])] = key
    for skip in skipped_signals or ():
        key = (int(skip["entry_bar_index"]), int(skip["bar_index"]))
        groups[key].add(str(skip["direction"]))
        candidate_key_by_signal[int(skip["signal_id"])] = key

    if not groups:
        return empty

    pair_keys = {key for key, directions in groups.items() if {"long", "short"} <= directions}
    if not pair_keys:
        return empty

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


def _same_bar_collision_groups(
    ordered_candidates: list[dict[str, Any]],
    *,
    exposure_policy: str,
) -> list[list[dict[str, Any]]]:
    """Opposite-direction groups that restrictive policies would collide on.

    ``allow_all`` and ``single_direction`` never collide, so this returns [].
    ``single_position`` groups by ``(entry_bar_index, bar_idx)`` (bar-level,
    matching DA1). ``single_setup`` additionally requires the same
    ``exposure_group_key`` so only same-setup opposite pairs are collisions.
    Groups are returned in first-seen ``ordered_candidates`` order.
    """
    if exposure_policy not in {"single_position", "single_setup"}:
        return []

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    order: list[tuple[Any, ...]] = []
    for row in ordered_candidates:
        if exposure_policy == "single_setup":
            key: tuple[Any, ...] = (
                int(row["entry_bar_index"]),
                int(row["bar_idx"]),
                str(row["exposure_group_key"]),
            )
        else:
            key = (int(row["entry_bar_index"]), int(row["bar_idx"]))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    collisions: list[list[dict[str, Any]]] = []
    for key in order:
        members = groups[key]
        directions = {str(member["direction"]) for member in members}
        if "long" in directions and "short" in directions:
            collisions.append(members)
    return collisions


def _candidate_conflict_id(row: dict[str, Any]) -> tuple[int, int, int]:
    """Stable identity for a DA3 conflicted candidate (not ``id(row)``)."""
    return (
        int(row["entry_bar_index"]),
        int(row["bar_idx"]),
        int(row["sig"]["signal_id"]),
    )


@dataclass(frozen=True)
class _SimulatePrep:
    """P0 validate/normalize outputs used by the public orchestrator."""

    exit_management_active: bool
    parsed_session_close: time | None
    parsed_no_new_entries_after: time | None
    normalized_entry_window: dict[str, Any]
    exchange_tz_for_window: str


@dataclass(frozen=True)
class _ExitOutcome:
    """P7 finalize: labeled exit + diagnostic increments. No P&L."""

    exit_bar_index: int
    theoretical_exit_price: float
    exit_reason: str
    intrabar_resolution: str
    intrabar_parent_both_hit: bool
    intrabar_ambiguous: bool
    exit_subbar_timestamp: pd.Timestamp | None
    stop_price: float
    target_price: float
    stop_state: Any
    mae_pts: float
    mfe_pts: float
    bracket_exit_count: int
    both_hit_count: int
    ambiguous_count: int
    affected_bar: int | None
    proximity_tie_count: int
    subtimeframe_resolved_count: int
    subtimeframe_fallback_exit_count: int


def _validate_simulate_trades(
    *,
    stop_loss_ticks: int | float,
    tick_size: float,
    point_value: float,
    commission_per_side: float,
    slippage_ticks: float,
    exposure_policy: str,
    same_bar_opposite_direction: str,
    cooldown_bars_after_exit: int,
    intrabar_model: str,
    breakeven_after_r: float | None,
    trailing_after_r: float | None,
    trailing_distance_ticks: float | None,
    session_close_time: str | None,
    flat_by_session_close: bool,
    no_new_entries_after: str | None,
    entry_window: dict[str, Any] | None,
    entry_window_exchange_tz: str | None,
    session_timezone: str | None,
) -> _SimulatePrep:
    """P0: fail-closed inputs and Admit normalize (C-19 / QI-04-01)."""
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
    if same_bar_opposite_direction not in VALID_SAME_BAR_OPPOSITE_DIRECTION:
        raise ValueError(
            "same_bar_opposite_direction must be one of "
            f"{sorted(VALID_SAME_BAR_OPPOSITE_DIRECTION)!r}, "
            f"got {same_bar_opposite_direction!r}"
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
    exchange_tz_for_window = entry_window_exchange_tz or session_timezone or "America/New_York"
    try:
        normalized_entry_window = normalize_entry_window(
            entry_window, exchange_tz=exchange_tz_for_window
        )
    except ValueError as exc:
        raise ValueError(f"Invalid entry_window: {exc}") from exc
    return _SimulatePrep(
        exit_management_active=exit_management_active,
        parsed_session_close=parsed_session_close,
        parsed_no_new_entries_after=parsed_no_new_entries_after,
        normalized_entry_window=normalized_entry_window,
        exchange_tz_for_window=exchange_tz_for_window,
    )


def _empty_simulation_return(
    *,
    return_result: bool,
    return_skipped_signals: bool,
    intrabar_model: str,
    breakeven_after_r: float | None,
    trailing_after_r: float | None,
    trailing_distance_ticks: float | None,
    same_bar_opposite_direction: str,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame] | SimulationResult:
    """P2: empty-signals payload. Schema only; no admission change."""
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
            direction_collision_diagnostic=_empty_direction_collision_diagnostic(
                policy=same_bar_opposite_direction
            ),
        )
    if return_skipped_signals:
        return empty_trades, empty_skipped
    return empty_trades


def _skipped_signal_row(
    *,
    sig: pd.Series,
    bar_idx: int,
    entry_bar_index: int,
    trigger: str,
    direction: str,
    exposure_policy: str,
    exposure_group_key: str,
    skip_reason: str,
    cooldown_bars_after_exit: int,
    blocking_trade_id: object = pd.NA,
    blocking_exit_bar_index: object = pd.NA,
) -> dict[str, Any]:
    return {
        "signal_id": int(sig["signal_id"]),
        "bar_index": bar_idx,
        "entry_bar_index": entry_bar_index,
        "trigger": trigger,
        "direction": direction,
        "exposure_policy": exposure_policy,
        "exposure_group_key": exposure_group_key,
        "skip_reason": skip_reason,
        "blocking_trade_id": blocking_trade_id,
        "blocking_exit_bar_index": blocking_exit_bar_index,
        "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
    }


def _admit_entry_candidates(
    signals: pd.DataFrame,
    *,
    df_reset: pd.DataFrame,
    n_bars: int,
    local_timestamps: pd.Series,
    slip_pts: float,
    exposure_policy: str,
    cooldown_bars_after_exit: int,
    capture_skips: bool,
    normalized_entry_window: dict[str, Any],
    exchange_tz_for_window: str,
    parsed_no_new_entries_after: time | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """P4: entry bar/price + window-then-cutoff (C9). 3c void stays silent."""
    candidate_rows: list[dict[str, Any]] = []
    skipped_signals: list[dict[str, Any]] = []
    for _, sig in signals.iterrows():
        trigger = str(sig["trigger"])
        direction = str(sig["direction"])
        bar_idx = int(sig["bar_index"])

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
        exposure_group_key = _exposure_group_key(
            sig,
            exposure_policy=exposure_policy,
            trigger=trigger,
            direction=direction,
        )

        if normalized_entry_window["enabled"] and not entry_window_contains(
            entry_ts,
            normalized_entry_window,
            exchange_tz=exchange_tz_for_window,
        ):
            skip_reason = SKIP_OUTSIDE_ENTRY_WINDOW
            if capture_skips:
                skipped_signals.append(
                    _skipped_signal_row(
                        sig=sig,
                        bar_idx=bar_idx,
                        entry_bar_index=entry_bar_index,
                        trigger=trigger,
                        direction=direction,
                        exposure_policy=exposure_policy,
                        exposure_group_key=exposure_group_key,
                        skip_reason=skip_reason,
                        cooldown_bars_after_exit=cooldown_bars_after_exit,
                    )
                )
            continue

        if (
            parsed_no_new_entries_after is not None
            and entry_local_ts.time() > parsed_no_new_entries_after
        ):
            skip_reason = SKIP_AFTER_ENTRY_CUTOFF
            if capture_skips:
                skipped_signals.append(
                    _skipped_signal_row(
                        sig=sig,
                        bar_idx=bar_idx,
                        entry_bar_index=entry_bar_index,
                        trigger=trigger,
                        direction=direction,
                        exposure_policy=exposure_policy,
                        exposure_group_key=exposure_group_key,
                        skip_reason=skip_reason,
                        cooldown_bars_after_exit=cooldown_bars_after_exit,
                    )
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
                "exposure_group_key": exposure_group_key,
            }
        )
    return candidate_rows, skipped_signals


def _order_candidates_and_da3(
    candidate_rows: list[dict[str, Any]],
    *,
    exposure_policy: str,
    same_bar_opposite_direction: str,
) -> tuple[list[dict[str, Any]], set[tuple[int, int, int]]]:
    """P5: restrictive sort + DA3 skip_both / raise."""
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
    conflict_candidate_ids: set[tuple[int, int, int]] = set()
    if same_bar_opposite_direction == "legacy":
        return ordered_candidates, conflict_candidate_ids
    collision_groups = _same_bar_collision_groups(
        ordered_candidates, exposure_policy=exposure_policy
    )
    if collision_groups and same_bar_opposite_direction == "raise":
        first_group = collision_groups[0]
        first_entry = int(first_group[0]["entry_bar_index"])
        signal_ids = sorted(int(row["sig"]["signal_id"]) for row in first_group)
        raise ValueError(
            "same_bar_opposite_direction='raise' refused the run: "
            f"opposite-direction collision at entry_bar_index={first_entry} "
            f"with signal_ids={signal_ids}"
        )
    if same_bar_opposite_direction == "skip_both":
        conflict_candidate_ids = {
            _candidate_conflict_id(row) for group in collision_groups for row in group
        }
    return ordered_candidates, conflict_candidate_ids


def _exposure_skip_for_candidate(
    candidate: dict[str, Any],
    *,
    accepted_for_blocking: list[dict[str, Any]],
    exposure_policy: str,
    cooldown_bars_after_exit: int,
) -> dict[str, Any] | None:
    """P6: occupancy / cooldown skip row, or None when the candidate is free."""
    direction = candidate["direction"]
    entry_bar_index = int(candidate["entry_bar_index"])
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
    if not blockers:
        return None
    blocker = sorted(
        blockers,
        key=lambda prior: (-int(prior["exit_bar_index"]), int(prior["trade_id"])),
    )[0]
    blocker_exit_bar_index = int(blocker["exit_bar_index"])
    if entry_bar_index > blocker_exit_bar_index:
        skip_reason = SKIP_COOLDOWN_ACTIVE
    elif exposure_policy == "single_position":
        skip_reason = SKIP_OVERLAPPING_POSITION
    elif exposure_policy == "single_direction":
        skip_reason = SKIP_OVERLAPPING_DIRECTION
    else:
        skip_reason = SKIP_OVERLAPPING_SETUP
    return _skipped_signal_row(
        sig=candidate["sig"],
        bar_idx=int(candidate["bar_idx"]),
        entry_bar_index=entry_bar_index,
        trigger=candidate["trigger"],
        direction=direction,
        exposure_policy=exposure_policy,
        exposure_group_key=exposure_group_key,
        skip_reason=skip_reason,
        cooldown_bars_after_exit=cooldown_bars_after_exit,
        blocking_trade_id=int(blocker["trade_id"]),
        blocking_exit_bar_index=blocker_exit_bar_index,
    )


def _finalize_exit_walk(
    walk: TradeExitWalk,
    *,
    bars: BarData,
    n_bars: int,
    max_holding_bars: int | None,
    flat_by_session_close: bool,
    data_end_before_session_close: bool,
    session_cap_bar: int | None,
    intrabar_model: str,
) -> _ExitOutcome:
    """Map a serial P7 walk onto C-18 exit tokens. No P&L."""
    exit_reason: str
    intrabar_resolution = "not_evaluated"
    intrabar_parent_both_hit = False
    intrabar_ambiguous = False
    exit_subbar_timestamp: pd.Timestamp | None = None
    bracket_exit_count = 0
    both_hit_count = 0
    ambiguous_count = 0
    affected_bar: int | None = None
    proximity_tie_count = 0
    subtimeframe_resolved_count = 0
    subtimeframe_fallback_exit_count = 0
    resolution = walk.resolution
    if resolution is not None and resolution.exit_kind is not None:
        if walk.exit_bar_index is None or walk.theoretical_exit_price is None:
            raise RuntimeError("P7 walk reported a bracket hit without exit coordinates")
        exit_bar_index = walk.exit_bar_index
        theoretical_exit_price = walk.theoretical_exit_price
        if (
            resolution.exit_kind == EXIT_SL
            and walk.stop_state.active_reason in EXIT_MANAGED_STOP_REASONS
        ):
            exit_reason = walk.stop_state.active_reason
        elif intrabar_model == "sl_first":
            exit_reason = resolution.exit_kind
        elif intrabar_model == "path_open_proximity":
            exit_reason = _exit_reason_with_suffix(resolution.exit_kind, EXIT_INTRABAR_PATH_SUFFIX)
        elif intrabar_model == "subtimeframe_conservative" and resolution.subtimeframe_fallback:
            exit_reason = _exit_reason_with_suffix(
                resolution.exit_kind, EXIT_SUBTIMEFRAME_FALLBACK_SUFFIX
            )
        else:
            exit_reason = _exit_reason_with_suffix(resolution.exit_kind, EXIT_SUBTIMEFRAME_SUFFIX)
        intrabar_resolution = resolution.resolution
        intrabar_parent_both_hit = resolution.parent_both_hit
        intrabar_ambiguous = walk.bracket_ambiguous
        exit_subbar_timestamp = resolution.exit_subbar_timestamp
        bracket_exit_count = 1
        if resolution.parent_both_hit:
            both_hit_count = 1
            affected_bar = exit_bar_index
        if intrabar_ambiguous:
            ambiguous_count = 1
        if resolution.proximity_tie:
            proximity_tie_count = 1
        if walk.subtimeframe_fallback:
            subtimeframe_fallback_exit_count = 1
        elif walk.subtimeframe_resolved:
            subtimeframe_resolved_count = 1
    else:
        if (
            max_holding_bars is not None
            and walk.time_cap_bar is not None
            and walk.max_bar == walk.time_cap_bar
        ):
            exit_bar_index = walk.max_bar
            theoretical_exit_price = bars.close[walk.max_bar]
            exit_reason = EXIT_TIME
            intrabar_resolution = "forced_time"
        elif flat_by_session_close:
            exit_bar_index = walk.max_bar
            theoretical_exit_price = bars.close[walk.max_bar]
            if (
                data_end_before_session_close
                and session_cap_bar is not None
                and walk.max_bar == session_cap_bar
            ):
                exit_reason = EXIT_DATA_END
                intrabar_resolution = "forced_data_end"
            else:
                exit_reason = EXIT_SESSION_CLOSE
                intrabar_resolution = "forced_session_close"
        else:
            exit_bar_index = n_bars - 1
            theoretical_exit_price = bars.close[n_bars - 1]
            exit_reason = EXIT_EOD
            intrabar_resolution = "forced_eod"
        if walk.pending_intrabar_ambiguity:
            intrabar_ambiguous = True
            ambiguous_count = 1

    return _ExitOutcome(
        exit_bar_index=exit_bar_index,
        theoretical_exit_price=theoretical_exit_price,
        exit_reason=exit_reason,
        intrabar_resolution=intrabar_resolution,
        intrabar_parent_both_hit=intrabar_parent_both_hit,
        intrabar_ambiguous=intrabar_ambiguous,
        exit_subbar_timestamp=exit_subbar_timestamp,
        stop_price=walk.stop_price,
        target_price=walk.target_price,
        stop_state=walk.stop_state,
        mae_pts=walk.mae_pts,
        mfe_pts=walk.mfe_pts,
        bracket_exit_count=bracket_exit_count,
        both_hit_count=both_hit_count,
        ambiguous_count=ambiguous_count,
        affected_bar=affected_bar,
        proximity_tie_count=proximity_tie_count,
        subtimeframe_resolved_count=subtimeframe_resolved_count,
        subtimeframe_fallback_exit_count=subtimeframe_fallback_exit_count,
    )


def _simulate_trade_exit(
    *,
    bars: BarData,
    n_bars: int,
    local_timestamps: pd.Series,
    direction: str,
    entry_price: float,
    theoretical_entry_price: float,
    entry_bar_index: int,
    entry_local_ts: pd.Timestamp,
    entry_model: str,
    trigger: str,
    sl_pts: float,
    tp_pts: float,
    allow_same_bar_exit: bool,
    max_holding_bars: int | None,
    flat_by_session_close: bool,
    parsed_session_close: time | None,
    exit_management_active: bool,
    tick_size: float,
    breakeven_after_r: float | None,
    trailing_after_r: float | None,
    trailing_distance_ticks: float | None,
    intrabar_model: str,
    subtimeframe_context: Any,
) -> _ExitOutcome | None:
    """P7 orchestrator: flatten cap + R22 walk + C-18 reason labels.

    Returns ``None`` when flatten finds no bar at or before the per-entry
    close (caller emits ``empty_session_close_cap``).
    """
    session_cap_bar: int | None = None
    data_end_before_session_close = False
    if flat_by_session_close:
        # Narrow before the R22 call. Public simulate_trades already rejects
        # flatten-without-clock; do not AttributeError on session_close.hour.
        if parsed_session_close is None:
            raise ValueError("flat_by_session_close=True requires a valid session_close_time.")
        cap = compute_session_close_cap(
            local_timestamps,
            entry_bar_index=entry_bar_index,
            entry_local_ts=entry_local_ts,
            session_close=parsed_session_close,
            n_bars=n_bars,
        )
        if cap.empty:
            return None
        session_cap_bar = cap.session_cap_bar
        data_end_before_session_close = cap.data_end_before_session_close
    walk = walk_trade_exit(
        bars,
        direction=direction,
        entry_price=entry_price,
        theoretical_entry_price=theoretical_entry_price,
        entry_bar_index=entry_bar_index,
        entry_model=entry_model,
        trigger=trigger,
        sl_pts=sl_pts,
        tp_pts=tp_pts,
        n_bars=n_bars,
        allow_same_bar_exit=allow_same_bar_exit,
        max_holding_bars=max_holding_bars,
        session_cap_bar=session_cap_bar,
        exit_management_active=exit_management_active,
        tick_size=tick_size,
        breakeven_after_r=breakeven_after_r,
        trailing_after_r=trailing_after_r,
        trailing_distance_ticks=trailing_distance_ticks,
        intrabar_model=intrabar_model,
        subtimeframe_context=subtimeframe_context,
    )
    return _finalize_exit_walk(
        walk,
        bars=bars,
        n_bars=n_bars,
        max_holding_bars=max_holding_bars,
        flat_by_session_close=flat_by_session_close,
        data_end_before_session_close=data_end_before_session_close,
        session_cap_bar=session_cap_bar,
        intrabar_model=intrabar_model,
    )


def _record_closed_trade(
    *,
    trade_id: int,
    candidate: dict[str, Any],
    outcome: _ExitOutcome,
    df_reset: pd.DataFrame,
    slip_pts: float,
    stop_loss_ticks: int | float,
    take_profit_ticks: int | float,
    point_value: float,
    total_commission_cost: float,
    risk_currency: float,
    exposure_policy: str,
    cooldown_bars_after_exit: int,
    intrabar_model: str,
    exit_management_active: bool,
    breakeven_after_r: float | None,
    trailing_after_r: float | None,
    trailing_distance_ticks: float | None,
) -> dict[str, Any]:
    """P8/P9: costs, trade schema, optional diagnostic columns."""
    sig = candidate["sig"]
    direction = candidate["direction"]
    theoretical_entry_price = float(candidate["theoretical_entry_price"])
    entry_price = float(candidate["entry_price"])
    theoretical_exit_price = outcome.theoretical_exit_price
    if direction == "long":
        exit_price = float(theoretical_exit_price) - slip_pts
        theoretical_pnl_points = float(theoretical_exit_price) - theoretical_entry_price
        gross_pnl_points = float(exit_price) - entry_price
    else:
        exit_price = float(theoretical_exit_price) + slip_pts
        theoretical_pnl_points = theoretical_entry_price - float(theoretical_exit_price)
        gross_pnl_points = entry_price - float(exit_price)
    exit_bar_index = outcome.exit_bar_index
    exit_ts = df_reset["timestamp"].iloc[exit_bar_index]
    gross_pnl_currency = gross_pnl_points * float(point_value)
    slippage_cost = max(
        0.0,
        (theoretical_pnl_points - gross_pnl_points) * float(point_value),
    )
    net_pnl_currency = gross_pnl_currency - total_commission_cost
    r_multiple = net_pnl_currency / risk_currency
    entry_bar_index = int(candidate["entry_bar_index"])
    trade = {
        "trade_id": trade_id,
        "signal_id": int(sig["signal_id"]),
        "trigger": candidate["trigger"],
        "direction": direction,
        "entry_timestamp": candidate["entry_ts"],
        "entry_bar_index": entry_bar_index,
        "theoretical_entry_price": theoretical_entry_price,
        "entry_price": entry_price,
        "entry_model": candidate["entry_model"],
        "exit_timestamp": exit_ts,
        "exit_bar_index": exit_bar_index,
        "theoretical_exit_price": float(theoretical_exit_price),
        "exit_price": float(exit_price),
        "exit_reason": outcome.exit_reason,
        "stop_price": outcome.stop_price,
        "target_price": outcome.target_price,
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
        "bars_held": exit_bar_index - entry_bar_index + 1,
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
        "mae_points": outcome.mae_pts,
        "mfe_points": outcome.mfe_pts,
        "exposure_policy": exposure_policy,
        "exposure_group_key": str(candidate["exposure_group_key"]),
        "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
        "status": "closed",
    }
    if intrabar_model != "sl_first":
        trade.update(
            {
                "intrabar_model": intrabar_model,
                "intrabar_resolution": outcome.intrabar_resolution,
                "intrabar_parent_both_hit": outcome.intrabar_parent_both_hit,
                "intrabar_ambiguous": outcome.intrabar_ambiguous,
                "exit_subbar_timestamp": outcome.exit_subbar_timestamp,
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
        stop_state = outcome.stop_state
        exit_management_armed = stop_state.breakeven_armed or stop_state.trailing_armed
        trade.update(
            {
                "breakeven_after_r": breakeven_after_r,
                "trailing_after_r": trailing_after_r,
                "trailing_distance_ticks": trailing_distance_ticks,
                "initial_stop_price": outcome.stop_price,
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
    return trade


def _assemble_simulate_result(
    *,
    trades: list[dict[str, Any]],
    skipped_signals: list[dict[str, Any]],
    ordered_candidates: list[dict[str, Any]],
    return_result: bool,
    return_skipped_signals: bool,
    intrabar_model: str,
    exit_management_active: bool,
    df_reset: pd.DataFrame,
    subtimeframe_context: Any,
    bracket_exit_count: int,
    both_hit_count: int,
    ambiguous_count: int,
    affected_bars: set[int],
    proximity_tie_count: int,
    subtimeframe_resolved_count: int,
    subtimeframe_fallback_exit_count: int,
    breakeven_after_r: float | None,
    trailing_after_r: float | None,
    trailing_distance_ticks: float | None,
    trades_with_exit_mgmt_count: int,
    be_exit_count: int,
    trail_exit_count: int,
    total_stop_adjustment_count: int,
    same_bar_opposite_direction: str,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame] | SimulationResult:
    """P10: trades / skips / three diagnostics."""
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
                skipped_signals=skipped_signals,
                policy=same_bar_opposite_direction,
            ),
        )
    if return_skipped_signals:
        return trades_df, skipped_df
    return trades_df


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
    same_bar_opposite_direction: str = "legacy",
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
    same_bar_opposite_direction:
        Opt-in DA3 guard for same-bar opposite-direction candidates.
        ``legacy`` (default) keeps today's ``signal_id`` tie-break.
        ``skip_both`` skips every member of a colliding group under
        ``single_position`` / ``single_setup`` (same group key) with
        ``skip_reason="direction_conflict"``. ``raise`` refuses the run
        with the first colliding ``(entry_bar_index, signal_ids)``.
        No-op under ``allow_all`` and ``single_direction``.

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
        is invalid, cooldown is negative, ``same_bar_opposite_direction`` is
        invalid, or the policy is ``raise`` and a collision is present.

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
    prep = _validate_simulate_trades(
        stop_loss_ticks=stop_loss_ticks,
        tick_size=tick_size,
        point_value=point_value,
        commission_per_side=commission_per_side,
        slippage_ticks=slippage_ticks,
        exposure_policy=exposure_policy,
        same_bar_opposite_direction=same_bar_opposite_direction,
        cooldown_bars_after_exit=cooldown_bars_after_exit,
        intrabar_model=intrabar_model,
        breakeven_after_r=breakeven_after_r,
        trailing_after_r=trailing_after_r,
        trailing_distance_ticks=trailing_distance_ticks,
        session_close_time=session_close_time,
        flat_by_session_close=flat_by_session_close,
        no_new_entries_after=no_new_entries_after,
        entry_window=entry_window,
        entry_window_exchange_tz=entry_window_exchange_tz,
        session_timezone=session_timezone,
    )
    if signals is None or signals.empty:
        return _empty_simulation_return(
            return_result=return_result,
            return_skipped_signals=return_skipped_signals,
            intrabar_model=intrabar_model,
            breakeven_after_r=breakeven_after_r,
            trailing_after_r=trailing_after_r,
            trailing_distance_ticks=trailing_distance_ticks,
            same_bar_opposite_direction=same_bar_opposite_direction,
        )

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
    capture_skips = return_skipped_signals or return_result

    trades: list[dict[str, Any]] = []
    skipped_signals: list[dict[str, Any]] = []
    trade_id = 0
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

    candidate_rows, window_skips = _admit_entry_candidates(
        signals,
        df_reset=df_reset,
        n_bars=n_bars,
        local_timestamps=local_timestamps,
        slip_pts=slip_pts,
        exposure_policy=exposure_policy,
        cooldown_bars_after_exit=cooldown_bars_after_exit,
        capture_skips=capture_skips,
        normalized_entry_window=prep.normalized_entry_window,
        exchange_tz_for_window=prep.exchange_tz_for_window,
        parsed_no_new_entries_after=prep.parsed_no_new_entries_after,
    )
    skipped_signals.extend(window_skips)
    ordered_candidates, conflict_candidate_ids = _order_candidates_and_da3(
        candidate_rows,
        exposure_policy=exposure_policy,
        same_bar_opposite_direction=same_bar_opposite_direction,
    )

    accepted_for_blocking: list[dict[str, Any]] = []
    for candidate in ordered_candidates:
        sig = candidate["sig"]
        if (
            same_bar_opposite_direction == "skip_both"
            and _candidate_conflict_id(candidate) in conflict_candidate_ids
        ):
            skip_reason = SKIP_DIRECTION_CONFLICT
            if capture_skips:
                skipped_signals.append(
                    _skipped_signal_row(
                        sig=sig,
                        bar_idx=int(candidate["bar_idx"]),
                        entry_bar_index=int(candidate["entry_bar_index"]),
                        trigger=candidate["trigger"],
                        direction=candidate["direction"],
                        exposure_policy=exposure_policy,
                        exposure_group_key=str(candidate["exposure_group_key"]),
                        skip_reason=skip_reason,
                        cooldown_bars_after_exit=cooldown_bars_after_exit,
                    )
                )
            continue

        occupancy_skip = _exposure_skip_for_candidate(
            candidate,
            accepted_for_blocking=accepted_for_blocking,
            exposure_policy=exposure_policy,
            cooldown_bars_after_exit=cooldown_bars_after_exit,
        )
        if occupancy_skip is not None:
            if capture_skips:
                skipped_signals.append(occupancy_skip)
            continue

        outcome = _simulate_trade_exit(
            bars=bars,
            n_bars=n_bars,
            local_timestamps=local_timestamps,
            direction=str(candidate["direction"]),
            entry_price=float(candidate["entry_price"]),
            theoretical_entry_price=float(candidate["theoretical_entry_price"]),
            entry_bar_index=int(candidate["entry_bar_index"]),
            entry_local_ts=candidate["entry_local_ts"],
            entry_model=str(candidate["entry_model"]),
            trigger=str(candidate["trigger"]),
            sl_pts=sl_pts,
            tp_pts=tp_pts,
            allow_same_bar_exit=allow_same_bar_exit,
            max_holding_bars=max_holding_bars,
            flat_by_session_close=flat_by_session_close,
            parsed_session_close=prep.parsed_session_close,
            exit_management_active=prep.exit_management_active,
            tick_size=tick_size,
            breakeven_after_r=breakeven_after_r,
            trailing_after_r=trailing_after_r,
            trailing_distance_ticks=trailing_distance_ticks,
            intrabar_model=intrabar_model,
            subtimeframe_context=subtimeframe_context,
        )
        if outcome is None:
            skip_reason = SKIP_EMPTY_SESSION_CLOSE_CAP
            if capture_skips:
                skipped_signals.append(
                    _skipped_signal_row(
                        sig=sig,
                        bar_idx=int(candidate["bar_idx"]),
                        entry_bar_index=int(candidate["entry_bar_index"]),
                        trigger=candidate["trigger"],
                        direction=candidate["direction"],
                        exposure_policy=exposure_policy,
                        exposure_group_key=str(candidate["exposure_group_key"]),
                        skip_reason=skip_reason,
                        cooldown_bars_after_exit=cooldown_bars_after_exit,
                    )
                )
            continue

        trade = _record_closed_trade(
            trade_id=trade_id,
            candidate=candidate,
            outcome=outcome,
            df_reset=df_reset,
            slip_pts=slip_pts,
            stop_loss_ticks=stop_loss_ticks,
            take_profit_ticks=take_profit_ticks,
            point_value=point_value,
            total_commission_cost=total_commission_cost,
            risk_currency=risk_currency,
            exposure_policy=exposure_policy,
            cooldown_bars_after_exit=cooldown_bars_after_exit,
            intrabar_model=intrabar_model,
            exit_management_active=prep.exit_management_active,
            breakeven_after_r=breakeven_after_r,
            trailing_after_r=trailing_after_r,
            trailing_distance_ticks=trailing_distance_ticks,
        )
        bracket_exit_count += outcome.bracket_exit_count
        both_hit_count += outcome.both_hit_count
        ambiguous_count += outcome.ambiguous_count
        if outcome.affected_bar is not None:
            affected_bars.add(outcome.affected_bar)
        proximity_tie_count += outcome.proximity_tie_count
        subtimeframe_resolved_count += outcome.subtimeframe_resolved_count
        subtimeframe_fallback_exit_count += outcome.subtimeframe_fallback_exit_count
        if prep.exit_management_active:
            if trade.get("exit_management_armed"):
                trades_with_exit_mgmt_count += 1
            if outcome.exit_reason == EXIT_BE:
                be_exit_count += 1
            if outcome.exit_reason == EXIT_TRAIL:
                trail_exit_count += 1
            total_stop_adjustment_count += int(outcome.stop_state.adjustment_count)
        trades.append(trade)
        accepted_for_blocking.append(
            {
                "trade_id": trade_id,
                "exit_bar_index": outcome.exit_bar_index,
                "direction": candidate["direction"],
                "exposure_group_key": str(candidate["exposure_group_key"]),
            }
        )
        trade_id += 1

    return _assemble_simulate_result(
        trades=trades,
        skipped_signals=skipped_signals,
        ordered_candidates=ordered_candidates,
        return_result=return_result,
        return_skipped_signals=return_skipped_signals,
        intrabar_model=intrabar_model,
        exit_management_active=prep.exit_management_active,
        df_reset=df_reset,
        subtimeframe_context=subtimeframe_context,
        bracket_exit_count=bracket_exit_count,
        both_hit_count=both_hit_count,
        ambiguous_count=ambiguous_count,
        affected_bars=affected_bars,
        proximity_tie_count=proximity_tie_count,
        subtimeframe_resolved_count=subtimeframe_resolved_count,
        subtimeframe_fallback_exit_count=subtimeframe_fallback_exit_count,
        breakeven_after_r=breakeven_after_r,
        trailing_after_r=trailing_after_r,
        trailing_distance_ticks=trailing_distance_ticks,
        trades_with_exit_mgmt_count=trades_with_exit_mgmt_count,
        be_exit_count=be_exit_count,
        trail_exit_count=trail_exit_count,
        total_stop_adjustment_count=total_stop_adjustment_count,
        same_bar_opposite_direction=same_bar_opposite_direction,
    )
