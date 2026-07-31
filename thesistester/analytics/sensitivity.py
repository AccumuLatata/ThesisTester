"""R19 deterministic one-at-a-time parameter sensitivity diagnostics."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Mapping

import pandas as pd

from thesistester.analytics.metrics import summarize_trades
from thesistester.analytics.overfitting import _SIMULATION_KWARGS
from thesistester.engine.backtest import simulate_trades

_PARAMETER_ORDER = (
    "stop_loss_ticks",
    "take_profit_ticks",
    "breakeven_after_r",
    "trailing_after_r",
    "trailing_distance_ticks",
)
_TICK_PARAMETERS = {"stop_loss_ticks", "take_profit_ticks", "trailing_distance_ticks"}


def _sign(value: float | None) -> int:
    if value is None or not math.isfinite(float(value)):
        return 0
    return (float(value) > 0) - (float(value) < 0)


def _perturbation_values(
    baseline: float,
    *,
    perturbation_fraction: float,
    n_steps_per_side: int,
    tick_parameter: bool,
) -> list[tuple[float, float]]:
    """Return sorted, unique deterministic (relative_step, candidate) pairs."""
    candidates: dict[float, float] = {}
    for step in range(-n_steps_per_side, n_steps_per_side + 1):
        relative_step = step * perturbation_fraction / n_steps_per_side
        value = baseline * (1.0 + relative_step)
        if tick_parameter:
            value = float(max(1, round(value)))
        if value <= 0:
            continue
        candidates[value] = relative_step
    return sorted(
        ((relative_step, value) for value, relative_step in candidates.items()), key=lambda x: x[1]
    )


def sensitivity_summary(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    tick_size: float,
    point_value: float,
    selected_cell: Mapping[str, Any],
    execution_kwargs: Mapping[str, Any] | None = None,
    perturbation_fraction: float = 0.20,
    n_steps_per_side: int = 5,
    parameters: list[str] | None = None,
    random_state: int = 42,
    include_rows: bool = True,
) -> dict[str, Any]:
    """Profile local OAT sensitivity around one selected execution grid cell.

    Tick-valued parameters use nearest-integer tick rounding and duplicate
    candidates are collapsed. R thresholds remain continuous. This is a local
    diagnostic: it deliberately does not perturb level or signal settings.
    """
    if not 0 < float(perturbation_fraction) <= 1:
        raise ValueError("perturbation_fraction must be in (0, 1]")
    if int(n_steps_per_side) < 1:
        raise ValueError("n_steps_per_side must be >= 1")
    if not isinstance(random_state, int) or isinstance(random_state, bool) or random_state < 0:
        raise ValueError("random_state must be a non-negative integer")

    selected = {
        key: (None if pd.isna(selected_cell.get(key)) else selected_cell.get(key))
        for key in _PARAMETER_ORDER
    }
    if any(
        not isinstance(selected[key], Real) or float(selected[key]) <= 0
        for key in _PARAMETER_ORDER[:2]
    ):
        raise ValueError("selected_cell requires positive stop_loss_ticks and take_profit_ticks")
    requested = list(parameters) if parameters is not None else list(_PARAMETER_ORDER)
    unknown = sorted(set(requested) - set(_PARAMETER_ORDER))
    if unknown:
        raise ValueError(f"Unsupported sensitivity parameters: {', '.join(unknown)}")
    active = [
        key
        for key in _PARAMETER_ORDER
        if key in requested and isinstance(selected[key], Real) and float(selected[key]) > 0
    ]
    kwargs = {
        key: value
        for key, value in dict(execution_kwargs or {}).items()
        if key in _SIMULATION_KWARGS
    }

    def replay(values: Mapping[str, Any]) -> pd.DataFrame:
        return simulate_trades(
            df=df,
            signals=signals,
            tick_size=tick_size,
            point_value=point_value,
            stop_loss_ticks=float(values["stop_loss_ticks"]),
            take_profit_ticks=float(values["take_profit_ticks"]),
            breakeven_after_r=values["breakeven_after_r"],
            trailing_after_r=values["trailing_after_r"],
            trailing_distance_ticks=values["trailing_distance_ticks"],
            **kwargs,
        )

    baseline_trades = replay(selected)
    baseline_metrics = summarize_trades(baseline_trades)
    baseline_expectancy = baseline_metrics.get("expectancy_r")
    profiles: list[dict[str, Any]] = []
    for parameter in active:
        rows: list[dict[str, Any]] = []
        for relative_step, value in _perturbation_values(
            float(selected[parameter]),
            perturbation_fraction=float(perturbation_fraction),
            n_steps_per_side=int(n_steps_per_side),
            tick_parameter=parameter in _TICK_PARAMETERS,
        ):
            trial = {**selected, parameter: value}
            metrics = summarize_trades(replay(trial))
            rows.append(
                {
                    "relative_step": relative_step,
                    "parameter_value": value,
                    "expectancy_r": metrics.get("expectancy_r"),
                    "profit_factor": metrics.get("profit_factor"),
                    "trade_count": metrics.get("trade_count", 0),
                }
            )
        expectancy_signs = {_sign(row["expectancy_r"]) for row in rows}
        profiles.append(
            {
                "parameter": parameter,
                "baseline_value": float(selected[parameter]),
                "tick_rounded": parameter in _TICK_PARAMETERS,
                "fragile": -1 in expectancy_signs and 1 in expectancy_signs,
                "curve": rows if include_rows else [],
                "n_unique_values": len(rows),
            }
        )
    return {
        "schema_version": 1,
        "available": bool(active),
        "config": {
            "perturbation_fraction": float(perturbation_fraction),
            "n_steps_per_side": int(n_steps_per_side),
            "parameters": active,
            "random_state": int(random_state),
            "include_rows": bool(include_rows),
            "tick_rounding": "nearest integer tick; duplicate candidates collapsed",
        },
        "selected_cell": {key: selected[key] for key in _PARAMETER_ORDER},
        "baseline": {
            "expectancy_r": baseline_expectancy,
            "profit_factor": baseline_metrics.get("profit_factor"),
            "trade_count": baseline_metrics.get("trade_count", 0),
        },
        "parameters": profiles,
        "fragile_parameter_count": sum(profile["fragile"] for profile in profiles),
        "caveat": (
            "Diagnostic only. One-at-a-time local perturbations hold all other execution "
            "parameters and signals fixed; they do not measure parameter interactions, "
            "sampling uncertainty, multiple-testing bias, or future edge."
        ),
    }
