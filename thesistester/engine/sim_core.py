"""Internal array-backed primitives for the serial trade-simulation hot path.

This module intentionally has no public execution API. It narrows the future
optimization boundary (R22) while preserving `simulate_trades` orchestration
in `backtest.py`. C-19 (QI-04-01) owns the serial P7 walk here: session-close
cap math and the per-bar SL/TP + flatten + R13 walk. C-20 (QI-14-09) stores
parent OHLC as write-protected ``float64`` arrays. Admission, skip-row
schema, costs, and P&L stay in `backtest.py`. ``resolve_ohlc_bar`` math is
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import time
from typing import Any

import numpy as np
import pandas as pd

from .exit_management import (
    ExitManagementState,
    initial_exit_management_state,
    update_exit_management_after_bar,
)
from .intrabar import IntrabarResolution, resolve_ohlc_bar, resolve_subtimeframe_bar


@dataclass(frozen=True)
class BarValues:
    """Numeric OHLC values for one parent bar."""

    open: float
    high: float
    low: float
    close: float


def _legacy_float64(column: pd.Series) -> np.ndarray:
    """C-19 fail-closed ``float(value)`` coercion into a new float64 buffer."""
    return np.fromiter((float(value) for value in column), dtype=np.float64, count=len(column))


def _frozen_float64(column: pd.Series) -> np.ndarray:
    """Copy one OHLC column to a write-protected C-contiguous float64 array.

    Numpy-backed integer/float columns use a vectorized copy. All other
    dtypes keep C-19 ``float(value)`` coercion so ``pd.NA``, ``None``, and
    datetime columns still raise instead of becoming NaN or epoch floats.
    """
    dtype = column.dtype
    if isinstance(dtype, np.dtype) and dtype.kind in {"f", "i", "u"}:
        array = np.ascontiguousarray(column.to_numpy(dtype=np.float64, copy=True))
    else:
        array = np.ascontiguousarray(_legacy_float64(column))
    if not array.flags.owndata:
        array = np.array(array, dtype=np.float64, copy=True, order="C")
    array.setflags(write=False)
    return array


@dataclass(frozen=True, eq=False)
class BarData:
    """Immutable parent-bar float64 arrays shared by every trade exit walk.

    C-20 (QI-14-09): storage is ``numpy.float64``, not boxed Python tuples.
    ``at()`` still returns Python ``float`` scalars so ``resolve_ohlc_bar``
    math is unchanged. Equality is value-based (``np.array_equal``) because
    the default dataclass tuple compare is ambiguous for ndarrays.
    """

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BarData):
            return NotImplemented
        return (
            np.array_equal(self.open, other.open)
            and np.array_equal(self.high, other.high)
            and np.array_equal(self.low, other.low)
            and np.array_equal(self.close, other.close)
        )

    def __hash__(self) -> int:
        return hash(
            (self.open.tobytes(), self.high.tobytes(), self.low.tobytes(), self.close.tobytes())
        )

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "BarData":
        """Snapshot validated parent OHLC values without mutating the frame."""
        return cls(
            open=_frozen_float64(frame["open"]),
            high=_frozen_float64(frame["high"]),
            low=_frozen_float64(frame["low"]),
            close=_frozen_float64(frame["close"]),
        )

    def at(self, index: int) -> BarValues:
        """Return one parent bar's values at the existing integer bar index."""
        return BarValues(
            open=float(self.open[index]),
            high=float(self.high[index]),
            low=float(self.low[index]),
            close=float(self.close[index]),
        )


def resolve_trade_bar(
    bars: BarData,
    *,
    bar_index: int,
    intrabar_model: str,
    subtimeframe_context: Any,
    stop_price: float,
    target_price: float,
    direction: str,
    entry_activation_price: float | None,
):
    """Resolve one trade's bracket event against an immutable parent bar.

    The returned intrabar resolution is intentionally the existing engine
    object. Future acceleration can replace only this boundary after proving
    serial parity for every supported model.
    """
    bar = bars.at(bar_index)
    if intrabar_model == "subtimeframe":
        resolution = resolve_subtimeframe_bar(
            subtimeframe_context.groups[bar_index],
            stop_price=stop_price,
            target_price=target_price,
            direction=direction,
            parent_low=bar.low,
            parent_high=bar.high,
            entry_price=entry_activation_price,
        )
    elif intrabar_model == "subtimeframe_conservative":
        sub_bars = subtimeframe_context.groups.get(bar_index)
        if sub_bars is not None:
            resolution = resolve_subtimeframe_bar(
                sub_bars,
                stop_price=stop_price,
                target_price=target_price,
                direction=direction,
                parent_low=bar.low,
                parent_high=bar.high,
                entry_price=entry_activation_price,
            )
        else:
            fallback = resolve_ohlc_bar(
                open_price=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                stop_price=stop_price,
                target_price=target_price,
                direction=direction,
                model="sl_first",
            )
            entry_reached = (
                entry_activation_price is None
                or bar.low <= float(entry_activation_price) <= bar.high
            )
            if not entry_reached:
                fallback = IntrabarResolution(
                    None,
                    "subtimeframe_conservative_entry_not_reached",
                    fallback.parent_both_hit,
                )
            elif entry_activation_price is not None and fallback.exit_kind == "TP":
                fallback = IntrabarResolution(
                    None,
                    "subtimeframe_conservative_entry_parent_unresolved",
                    fallback.parent_both_hit,
                    ambiguous=True,
                )
            resolution = replace(
                fallback,
                resolution=(
                    fallback.resolution
                    if fallback.exit_kind is None
                    else "subtimeframe_conservative_fallback_sl_first"
                ),
                subtimeframe_fallback=True,
            )
    else:
        resolution = resolve_ohlc_bar(
            open_price=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            stop_price=stop_price,
            target_price=target_price,
            direction=direction,
            model=intrabar_model,
            entry_price=entry_activation_price,
        )
    return bar, resolution


@dataclass(frozen=True)
class SessionCloseCap:
    """AH1 / C1 flatten window for one candidate. No skip-row schema."""

    empty: bool
    session_cap_bar: int | None
    data_end_before_session_close: bool


@dataclass(frozen=True)
class TradeExitWalk:
    """Serial P7 walk result. No admission, skip rows, costs, or P&L."""

    stop_price: float
    target_price: float
    stop_state: ExitManagementState
    exit_bar_index: int | None
    theoretical_exit_price: float | None
    resolution: IntrabarResolution | None
    mae_pts: float
    mfe_pts: float
    pending_intrabar_ambiguity: bool
    start_bar: int
    max_bar: int
    time_cap_bar: int | None
    bracket_exit: bool
    parent_both_hit: bool
    bracket_ambiguous: bool
    proximity_tie: bool
    subtimeframe_resolved: bool
    subtimeframe_fallback: bool


def compute_session_close_cap(
    local_timestamps: pd.Series,
    *,
    entry_bar_index: int,
    entry_local_ts: pd.Timestamp,
    session_close: time,
    n_bars: int,
) -> SessionCloseCap:
    """Cap the exit walk at this trade's entry-date session close (AH1 / C1).

    Flatten clock is ``entry_local_ts.normalize() + session_close``. Empty
    windows are a sentinel only — skip-row emission stays in ``backtest.py``.
    """
    session_close_ts = entry_local_ts.normalize() + pd.Timedelta(
        hours=session_close.hour,
        minutes=session_close.minute,
        seconds=session_close.second,
    )
    bars_until_close = local_timestamps[
        (local_timestamps.index >= entry_bar_index) & (local_timestamps <= session_close_ts)
    ]
    if bars_until_close.empty:
        return SessionCloseCap(
            empty=True,
            session_cap_bar=None,
            data_end_before_session_close=False,
        )
    session_cap_bar = int(bars_until_close.index[-1])
    last_available_ts = local_timestamps.iloc[n_bars - 1]
    data_end_before_session_close = (
        session_cap_bar == n_bars - 1 and last_available_ts < session_close_ts
    )
    return SessionCloseCap(
        empty=False,
        session_cap_bar=session_cap_bar,
        data_end_before_session_close=data_end_before_session_close,
    )


def _fixed_bracket_prices(
    *,
    direction: str,
    entry_price: float,
    sl_pts: float,
    tp_pts: float,
) -> tuple[float, float]:
    if direction == "long":
        return entry_price - sl_pts, entry_price + tp_pts
    return entry_price + sl_pts, entry_price - tp_pts


def _exit_walk_bounds(
    *,
    n_bars: int,
    entry_bar_index: int,
    allow_same_bar_exit: bool,
    max_holding_bars: int | None,
    session_cap_bar: int | None,
) -> tuple[int, int, int | None]:
    start_bar = entry_bar_index if allow_same_bar_exit else entry_bar_index + 1
    max_bar = n_bars - 1
    time_cap_bar: int | None = None
    if max_holding_bars is not None:
        time_cap_bar = entry_bar_index + max_holding_bars - 1
        max_bar = min(max_bar, time_cap_bar)
    if session_cap_bar is not None:
        max_bar = min(max_bar, session_cap_bar)
    return start_bar, max_bar, time_cap_bar


def walk_trade_exit(
    bars: BarData,
    *,
    direction: str,
    entry_price: float,
    theoretical_entry_price: float,
    entry_bar_index: int,
    entry_model: str,
    trigger: str,
    sl_pts: float,
    tp_pts: float,
    n_bars: int,
    allow_same_bar_exit: bool,
    max_holding_bars: int | None,
    session_cap_bar: int | None,
    exit_management_active: bool,
    tick_size: float,
    breakeven_after_r: float | None,
    trailing_after_r: float | None,
    trailing_distance_ticks: float | None,
    intrabar_model: str,
    subtimeframe_context: Any,
) -> TradeExitWalk:
    """Walk SL/TP + R13 until a bracket hit or the flatten/time/data cap.

    Exit-reason tokens, skip rows, and P&L stay in ``backtest.py``.
    """
    stop_price, target_price = _fixed_bracket_prices(
        direction=direction,
        entry_price=entry_price,
        sl_pts=sl_pts,
        tp_pts=tp_pts,
    )
    stop_state = initial_exit_management_state(
        initial_stop=stop_price,
        entry_price=entry_price,
        direction=direction,
    )
    start_bar, max_bar, time_cap_bar = _exit_walk_bounds(
        n_bars=n_bars,
        entry_bar_index=entry_bar_index,
        allow_same_bar_exit=allow_same_bar_exit,
        max_holding_bars=max_holding_bars,
        session_cap_bar=session_cap_bar,
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

    exit_bar_index: int | None = None
    theoretical_exit_price: float | None = None
    hit_resolution: IntrabarResolution | None = None
    pending_intrabar_ambiguity = False
    mae_pts = 0.0
    mfe_pts = 0.0
    parent_both_hit = False
    bracket_ambiguous = False
    proximity_tie = False
    subtimeframe_resolved = False
    subtimeframe_fallback = False

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
            hit_resolution = resolution
            parent_both_hit = resolution.parent_both_hit
            bracket_ambiguous = pending_intrabar_ambiguity
            proximity_tie = bool(resolution.proximity_tie)
            if intrabar_model in {"subtimeframe", "subtimeframe_conservative"}:
                subtimeframe_fallback = bool(resolution.subtimeframe_fallback)
                subtimeframe_resolved = not subtimeframe_fallback
            break
        can_update_exit_management = (entry_model == "next_bar_open" and b >= entry_bar_index) or (
            entry_model != "next_bar_open" and b > entry_bar_index
        )
        if exit_management_active and can_update_exit_management and b < max_bar:
            stop_state = update_exit_management_after_bar(
                state=stop_state,
                direction=direction,
                entry_price=entry_price,
                initial_stop=stop_price,
                tick_size=tick_size,
                risk_points=sl_pts,
                bar_high=bar.high,
                bar_low=bar.low,
                bar_index=b,
                breakeven_after_r=breakeven_after_r,
                trailing_after_r=trailing_after_r,
                trailing_distance_ticks=trailing_distance_ticks,
            )

    return TradeExitWalk(
        stop_price=stop_price,
        target_price=target_price,
        stop_state=stop_state,
        exit_bar_index=exit_bar_index,
        theoretical_exit_price=theoretical_exit_price,
        resolution=hit_resolution,
        mae_pts=mae_pts,
        mfe_pts=mfe_pts,
        pending_intrabar_ambiguity=pending_intrabar_ambiguity,
        start_bar=start_bar,
        max_bar=max_bar,
        time_cap_bar=time_cap_bar,
        bracket_exit=hit_resolution is not None,
        parent_both_hit=parent_both_hit,
        bracket_ambiguous=bracket_ambiguous,
        proximity_tie=proximity_tie,
        subtimeframe_resolved=subtimeframe_resolved,
        subtimeframe_fallback=subtimeframe_fallback,
    )
