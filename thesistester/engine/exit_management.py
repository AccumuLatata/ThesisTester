"""Break-even and trailing-stop state for R13."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class ExitManagementState:
    """Effective stop state active for the next bar."""

    effective_stop: float
    active_reason: str
    breakeven_armed: bool = False
    trailing_armed: bool = False
    best_favorable_price: float | None = None
    breakeven_activated_bar_index: int | None = None
    trailing_activated_bar_index: int | None = None
    adjustment_count: int = 0
    adjustment_path: tuple[str, ...] = ()


def validate_exit_management_config(
    *,
    breakeven_after_r: float | None = None,
    trailing_after_r: float | None = None,
    trailing_distance_ticks: float | None = None,
) -> None:
    """Fail closed on invalid dynamic-stop settings."""
    for name, value in (
        ("breakeven_after_r", breakeven_after_r),
        ("trailing_after_r", trailing_after_r),
        ("trailing_distance_ticks", trailing_distance_ticks),
    ):
        if value is None:
            continue
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a finite number > 0 or None.")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a finite number > 0 or None.") from exc
        if not math.isfinite(numeric) or numeric <= 0:
            raise ValueError(f"{name} must be a finite number > 0 or None.")
    if trailing_after_r is None and trailing_distance_ticks is not None:
        raise ValueError("trailing_distance_ticks requires trailing_after_r.")
    if trailing_after_r is not None and trailing_distance_ticks is None:
        raise ValueError("trailing_after_r requires trailing_distance_ticks.")


def exit_management_enabled(
    *,
    breakeven_after_r: float | None = None,
    trailing_after_r: float | None = None,
    trailing_distance_ticks: float | None = None,
) -> bool:
    """Return whether any R13 dynamic-stop behavior is enabled."""
    return (
        breakeven_after_r is not None
        or trailing_after_r is not None
        or trailing_distance_ticks is not None
    )


def initial_exit_management_state(
    *,
    initial_stop: float,
    entry_price: float,
    direction: str,
) -> ExitManagementState:
    """Initialize dynamic-stop state at the fixed bracket stop."""
    return ExitManagementState(
        effective_stop=float(initial_stop),
        active_reason="SL",
        best_favorable_price=float(entry_price),
    )


def update_exit_management_after_bar(
    *,
    state: ExitManagementState,
    direction: str,
    entry_price: float,
    initial_stop: float,
    tick_size: float,
    risk_points: float,
    bar_high: float,
    bar_low: float,
    bar_index: int,
    breakeven_after_r: float | None,
    trailing_after_r: float | None,
    trailing_distance_ticks: float | None,
) -> ExitManagementState:
    """Commit BE/trailing stop adjustments after the current bar closes.

    The returned stop is active on the next parent bar. This avoids optimistic
    OHLC-only same-bar arming and stop-out sequences.
    """
    effective_stop = float(state.effective_stop)
    active_reason = state.active_reason
    breakeven_armed = state.breakeven_armed
    trailing_armed = state.trailing_armed
    best = float(
        state.best_favorable_price if state.best_favorable_price is not None else entry_price
    )
    be_bar = state.breakeven_activated_bar_index
    trail_bar = state.trailing_activated_bar_index
    adjustment_count = int(state.adjustment_count)
    adjustment_path = list(state.adjustment_path)

    if direction == "long":
        best = max(best, float(bar_high))
        favorable_r = max(0.0, best - float(entry_price)) / float(risk_points)
        if breakeven_after_r is not None and favorable_r >= float(breakeven_after_r):
            if effective_stop < float(entry_price):
                effective_stop = float(entry_price)
                active_reason = "BE"
                adjustment_count += 1
                adjustment_path.append(f"b{int(bar_index)}:BE@{effective_stop:.10g}")
            breakeven_armed = True
            if be_bar is None:
                be_bar = int(bar_index)
        if trailing_after_r is not None and favorable_r >= float(trailing_after_r):
            candidate = best - float(trailing_distance_ticks) * float(tick_size)
            if candidate > effective_stop:
                effective_stop = candidate
                active_reason = "TRAIL"
                adjustment_count += 1
                adjustment_path.append(f"b{int(bar_index)}:TRAIL@{effective_stop:.10g}")
            trailing_armed = True
            if trail_bar is None:
                trail_bar = int(bar_index)
    else:
        best = min(best, float(bar_low))
        favorable_r = max(0.0, float(entry_price) - best) / float(risk_points)
        if breakeven_after_r is not None and favorable_r >= float(breakeven_after_r):
            if effective_stop > float(entry_price):
                effective_stop = float(entry_price)
                active_reason = "BE"
                adjustment_count += 1
                adjustment_path.append(f"b{int(bar_index)}:BE@{effective_stop:.10g}")
            breakeven_armed = True
            if be_bar is None:
                be_bar = int(bar_index)
        if trailing_after_r is not None and favorable_r >= float(trailing_after_r):
            candidate = best + float(trailing_distance_ticks) * float(tick_size)
            if candidate < effective_stop:
                effective_stop = candidate
                active_reason = "TRAIL"
                adjustment_count += 1
                adjustment_path.append(f"b{int(bar_index)}:TRAIL@{effective_stop:.10g}")
            trailing_armed = True
            if trail_bar is None:
                trail_bar = int(bar_index)

    return ExitManagementState(
        effective_stop=effective_stop,
        active_reason=active_reason,
        breakeven_armed=breakeven_armed,
        trailing_armed=trailing_armed,
        best_favorable_price=best,
        breakeven_activated_bar_index=be_bar,
        trailing_activated_bar_index=trail_bar,
        adjustment_count=adjustment_count,
        adjustment_path=tuple(adjustment_path),
    )


def policy_dict(
    *,
    breakeven_after_r: float | None,
    trailing_after_r: float | None,
    trailing_distance_ticks: float | None,
) -> dict[str, Any]:
    """Return a JSON-safe policy snapshot."""
    return {
        "schema_version": 1,
        "breakeven_after_r": breakeven_after_r,
        "trailing_after_r": trailing_after_r,
        "trailing_distance_ticks": trailing_distance_ticks,
        "enabled": exit_management_enabled(
            breakeven_after_r=breakeven_after_r,
            trailing_after_r=trailing_after_r,
            trailing_distance_ticks=trailing_distance_ticks,
        ),
    }
