"""Phase 5 — Bar-by-bar backtest engine.

Converts Phase 4 candidate signals into simulated trades using a single
fixed SL/TP configuration.

Design notes
------------
- Simple triggers (touch / reject / break / reclaim) enter at next-bar open
  to avoid look-ahead bias.
- ``3c`` signals with ``status="filled"`` enter at ``retrace_entry_price`` on
  ``entry_bar_index``. ``status="void"`` rows are skipped.
- When both SL and TP are reachable within the same OHLC bar the engine
  exits at SL (SL-first / pessimistic rule), because intrabar event order
  is unknowable from OHLC data alone.
- Phase 5 is a single-risk-config backtest only; SL/TP grid search belongs
  to Phase 6.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time
from typing import Any
from zoneinfo import ZoneInfoNotFoundError

import pandas as pd

from .intrabar import (
    prepare_subtimeframe_context,
    resolve_ohlc_bar,
    resolve_subtimeframe_bar,
    validate_intrabar_model,
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


@dataclass(frozen=True)
class SimulationResult:
    """Detailed opt-in result preserving the legacy DataFrame/tuple API."""

    trades: pd.DataFrame
    skipped_signals: pd.DataFrame
    intrabar_diagnostic: dict[str, Any]


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
        "subtimeframe_interval": (
            str(subtimeframe_interval) if subtimeframe_interval is not None else None
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
    intrabar_model: str = "sl_first",
    subtimeframe_data: pd.DataFrame | None = None,
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
        for the entry date; otherwise preserve legacy dataset-end behavior.
    session_close_time:
        Session close clock time (HH:MM or HH:MM:SS). Required when
        ``flat_by_session_close=True``.
    session_timezone:
        Timezone used to interpret session-close and entry-cutoff times.
        Naive timestamps are localized; aware timestamps are converted.
    no_new_entries_after:
        Optional local-time cutoff (HH:MM or HH:MM:SS). Entries whose local
        entry timestamp is later than this cutoff are skipped.

    exposure_policy:
        Exposure gate applied to executable signals. One of:
        ``allow_all``, ``single_position``, ``single_direction``,
        ``single_setup``.
    cooldown_bars_after_exit:
        Optional cooldown bars after a blocking trade exit. Must be >= 0.
    return_skipped_signals:
        If ``True``, returns ``(trades_df, skipped_signals_df)`` where skipped
        signals include exposure-policy rejections only.
    intrabar_model:
        ``"sl_first"`` preserves legacy pessimistic behavior.
        ``"path_open_proximity"`` walks a deterministic OHLC path beginning
        with the extreme nearest the open. ``"subtimeframe"`` walks validated
        lower-timeframe bars supplied through ``subtimeframe_data``.
    subtimeframe_data:
        Strictly finer OHLC data covering and reconciling every parent bar.
        Required only by ``intrabar_model="subtimeframe"``.
    return_result:
        Return :class:`SimulationResult` with skipped signals and a run-level
        intrabar diagnostic. Default ``False`` preserves the legacy return API.

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
    parsed_session_close = _parse_time_input(session_close_time, field_name="session_close_time")
    if flat_by_session_close and parsed_session_close is None:
        raise ValueError("flat_by_session_close=True requires a valid session_close_time.")
    parsed_no_new_entries_after = _parse_time_input(
        no_new_entries_after, field_name="no_new_entries_after"
    )

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
                    subtimeframe_interval=None,
                ),
            )
        if return_skipped_signals:
            return empty_trades, empty_skipped
        return empty_trades

    df_reset = df.reset_index(drop=True)
    n_bars = len(df_reset)
    local_timestamps = _timestamps_in_session_timezone(
        df_reset["timestamp"], session_timezone=session_timezone
    )
    subtimeframe_context = (
        prepare_subtimeframe_context(
            df_reset,
            subtimeframe_data,
            tick_size=float(tick_size),
        )
        if intrabar_model == "subtimeframe"
        else None
    )

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
        if (
            parsed_no_new_entries_after is not None
            and entry_local_ts.time() > parsed_no_new_entries_after
        ):
            continue

        candidate_rows.append(
            {
                "sig": sig,
                "trigger": trigger,
                "direction": direction,
                "bar_idx": bar_idx,
                "entry_bar_index": entry_bar_index,
                "entry_ts": entry_ts,
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
                continue
            session_cap_bar = int(bars_until_close.index[-1])
            max_bar = min(max_bar, session_cap_bar)
            last_available_ts = local_timestamps.iloc[n_bars - 1]
            data_end_before_session_close = (
                session_cap_bar == n_bars - 1 and last_available_ts < session_close_ts
            )

        for b in range(start_bar, max_bar + 1):
            bar = df_reset.iloc[b]
            bar_low = float(bar["low"])
            bar_high = float(bar["high"])

            # Track MAE / MFE
            if direction == "long":
                excursion_adverse = entry_price - bar_low
                excursion_favorable = bar_high - entry_price
            else:
                excursion_adverse = bar_high - entry_price
                excursion_favorable = entry_price - bar_low

            mae_pts = max(mae_pts, excursion_adverse)
            mfe_pts = max(mfe_pts, excursion_favorable)

            entry_activation_price = (
                theoretical_entry_price
                if b == entry_bar_index and trigger in {"3c", "confirm_3bar"}
                else None
            )
            if intrabar_model == "subtimeframe":
                resolution = resolve_subtimeframe_bar(
                    subtimeframe_context.groups[b],
                    stop_price=stop_price,
                    target_price=target_price,
                    direction=direction,
                    parent_low=bar_low,
                    parent_high=bar_high,
                    entry_price=entry_activation_price,
                )
            else:
                resolution = resolve_ohlc_bar(
                    open_price=float(bar["open"]),
                    high=bar_high,
                    low=bar_low,
                    close=float(bar["close"]),
                    stop_price=stop_price,
                    target_price=target_price,
                    direction=direction,
                    model=intrabar_model,
                    entry_price=entry_activation_price,
                )

            if resolution.exit_kind is not None:
                exit_bar_index = b
                theoretical_exit_price = (
                    stop_price if resolution.exit_kind == "SL" else target_price
                )
                if intrabar_model == "sl_first":
                    exit_reason = resolution.exit_kind
                elif intrabar_model == "path_open_proximity":
                    exit_reason = f"{resolution.exit_kind}_intrabar_path"
                else:
                    exit_reason = f"{resolution.exit_kind}_subtimeframe"
                intrabar_resolution = resolution.resolution
                intrabar_parent_both_hit = resolution.parent_both_hit
                intrabar_ambiguous = resolution.ambiguous
                exit_subbar_timestamp = resolution.exit_subbar_timestamp
                bracket_exit_count += 1
                if resolution.parent_both_hit:
                    both_hit_count += 1
                    affected_bars.add(b)
                if resolution.ambiguous:
                    ambiguous_count += 1
                if resolution.proximity_tie:
                    proximity_tie_count += 1
                if intrabar_model == "subtimeframe":
                    subtimeframe_resolved_count += 1
                break

        if exit_bar_index is None:
            # No SL/TP hit — TIME or EOD
            if (
                max_holding_bars is not None
                and time_cap_bar is not None
                and max_bar == time_cap_bar
            ):
                exit_bar_index = max_bar
                theoretical_exit_price = float(df_reset["close"].iloc[max_bar])
                exit_reason = "TIME"
                intrabar_resolution = "forced_time"
            elif flat_by_session_close:
                exit_bar_index = max_bar
                theoretical_exit_price = float(df_reset["close"].iloc[max_bar])
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
                theoretical_exit_price = float(df_reset["close"].iloc[n_bars - 1])
                exit_reason = "EOD"
                intrabar_resolution = "forced_eod"

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
                subtimeframe_interval=(
                    subtimeframe_context.sub_interval if subtimeframe_context is not None else None
                ),
            ),
        )
    if return_skipped_signals:
        return trades_df, skipped_df
    return trades_df
