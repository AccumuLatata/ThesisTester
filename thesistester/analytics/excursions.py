"""R10 analytics — MAE/MFE excursion diagnostics and SL/TP calibration.

All functions operate on completed trades from the Phase 5 backtest engine.
No trade simulation is performed here.  The module turns the engine's existing
``mae_points`` / ``mfe_points`` columns into deterministic, post-trade research
diagnostics.

Caveats
-------
- Excursions are bar-level bounds.  OHLC data cannot prove whether MAE or MFE
  happened first inside a bar.
- Counterfactual stop/target calibration therefore uses an explicit
  ``both_hit_rule``.  The default, ``"stop_first"``, matches the engine's
  pessimistic same-bar ambiguity rule.
- Edge-ratio decay is approximated by completed-trade ``bars_held`` buckets.
  True per-bar decay requires storing the intratrade excursion path.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

_REQUIRED_NORMALIZE_COLS = ("mae_points", "mfe_points", "stop_loss_ticks")
_BOTH_HIT_RULES = {"stop_first", "target_first", "exclude_ambiguous"}

_DISTRIBUTION_METRIC_COLS = [
    "trade_count",
    "mean_mae_r",
    "median_mae_r",
    "p25_mae_r",
    "p75_mae_r",
    "p95_mae_r",
    "mean_mfe_r",
    "median_mfe_r",
    "p25_mfe_r",
    "p75_mfe_r",
    "p95_mfe_r",
    "mean_edge_ratio_r",
    "median_edge_ratio_r",
    "avg_r",
    "avg_bars_held",
]

_QUADRANT_COLS = [
    "quadrant",
    "count",
    "pct",
    "avg_mae_r",
    "avg_mfe_r",
    "avg_r",
]

_CALIBRATION_COLS = [
    "stop_r",
    "target_r",
    "evaluated_trade_count",
    "target_hit_count",
    "stop_hit_count",
    "ambiguous_count",
    "unresolved_count",
    "target_hit_probability",
]


def _empty_distribution(group_cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=group_cols + _DISTRIBUTION_METRIC_COLS)


def _empty_quadrants() -> pd.DataFrame:
    return pd.DataFrame(columns=_QUADRANT_COLS)


def _empty_calibration() -> pd.DataFrame:
    return pd.DataFrame(columns=_CALIBRATION_COLS)


def _float_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _finite_mean(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None
    return float(clean.mean())


def _finite_median(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None
    return float(clean.median())


def _quantile(series: pd.Series, q: float) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None
    return float(clean.quantile(q))


def _normalize_group_cols(
    group_cols: Iterable[str] | str | None, trades: pd.DataFrame
) -> list[str]:
    if group_cols is None:
        return []
    if isinstance(group_cols, str):
        group_cols = [group_cols]
    return [col for col in group_cols if col in trades.columns]


def _coerce_positive_grid(values: Iterable[float]) -> list[float]:
    cleaned: list[float] = []
    for value in values:
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(v) and v > 0:
            cleaned.append(round(v, 10))
    return sorted(dict.fromkeys(cleaned))


def add_excursion_r_columns(trades: pd.DataFrame | None, tick_size: float) -> pd.DataFrame:
    """Return a trade copy with MAE/MFE normalized into R units.

    ``mae_points`` and ``mfe_points`` are price-point excursions.  R-normalized
    excursions use each trade's realized stop distance:

    ``risk_points = stop_loss_ticks * tick_size``.

    The returned frame adds ``risk_points``, ``mae_r``, ``mfe_r``,
    ``edge_ratio_r`` and ``giveback_r``.  Invalid/missing risk distances yield
    missing normalized values instead of raising, so empty or partially migrated
    trade tables remain safe to inspect.
    """
    if tick_size <= 0:
        raise ValueError("tick_size must be positive.")

    base = trades.copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame()
    for col in ("risk_points", "mae_r", "mfe_r", "edge_ratio_r", "giveback_r"):
        if col not in base.columns:
            base[col] = pd.Series(dtype=float)

    if base.empty or any(col not in base.columns for col in _REQUIRED_NORMALIZE_COLS):
        return base

    risk_points = pd.to_numeric(base["stop_loss_ticks"], errors="coerce") * float(tick_size)
    mae_points = pd.to_numeric(base["mae_points"], errors="coerce")
    mfe_points = pd.to_numeric(base["mfe_points"], errors="coerce")

    valid_risk = risk_points > 0
    base["risk_points"] = risk_points.where(valid_risk)
    base["mae_r"] = (mae_points / risk_points).where(valid_risk)
    base["mfe_r"] = (mfe_points / risk_points).where(valid_risk)
    realized_r = (
        pd.to_numeric(base["r_multiple"], errors="coerce")
        if "r_multiple" in base.columns
        else pd.Series(np.nan, index=base.index, dtype=float)
    )
    base["giveback_r"] = (base["mfe_r"] - realized_r).where(valid_risk)

    mae_r = pd.to_numeric(base["mae_r"], errors="coerce")
    mfe_r = pd.to_numeric(base["mfe_r"], errors="coerce")
    base["edge_ratio_r"] = np.where(mae_r > 0, mfe_r / mae_r, np.nan)
    return base


def excursion_distribution(
    trades: pd.DataFrame | None,
    tick_size: float,
    group_cols: Iterable[str] | str | None = None,
    *,
    min_trades: int = 1,
) -> pd.DataFrame:
    """Summarize MAE/MFE distributions overall or by existing trade columns.

    Missing group columns are ignored.  When no group columns remain, the
    returned DataFrame contains a single ``group="all"`` row.
    """
    normalized = add_excursion_r_columns(trades, tick_size)
    resolved_group_cols = _normalize_group_cols(group_cols, normalized)
    output_group_cols = resolved_group_cols or ["group"]
    empty = _empty_distribution(output_group_cols)
    if normalized.empty or "mae_r" not in normalized.columns or "mfe_r" not in normalized.columns:
        return empty

    rows: list[dict[str, Any]] = []
    if resolved_group_cols:
        iterator = normalized.groupby(resolved_group_cols, sort=True, dropna=False, observed=True)
    else:
        iterator = [("all", normalized)]

    for keys, group in iterator:
        valid = group.dropna(subset=["mae_r", "mfe_r"])
        trade_count = int(len(valid))
        if trade_count == 0:
            continue
        row: dict[str, Any] = {}
        if resolved_group_cols:
            if len(resolved_group_cols) == 1:
                keys = (keys,)
            for col, value in zip(resolved_group_cols, keys, strict=True):
                row[col] = value
        else:
            row["group"] = "all"
        row.update(
            {
                "trade_count": trade_count,
                "mean_mae_r": _finite_mean(valid["mae_r"]),
                "median_mae_r": _finite_median(valid["mae_r"]),
                "p25_mae_r": _quantile(valid["mae_r"], 0.25),
                "p75_mae_r": _quantile(valid["mae_r"], 0.75),
                "p95_mae_r": _quantile(valid["mae_r"], 0.95),
                "mean_mfe_r": _finite_mean(valid["mfe_r"]),
                "median_mfe_r": _finite_median(valid["mfe_r"]),
                "p25_mfe_r": _quantile(valid["mfe_r"], 0.25),
                "p75_mfe_r": _quantile(valid["mfe_r"], 0.75),
                "p95_mfe_r": _quantile(valid["mfe_r"], 0.95),
                "mean_edge_ratio_r": _finite_mean(valid["edge_ratio_r"]),
                "median_edge_ratio_r": _finite_median(valid["edge_ratio_r"]),
                "avg_r": _finite_mean(valid["r_multiple"])
                if "r_multiple" in valid.columns
                else None,
                "avg_bars_held": _finite_mean(valid["bars_held"])
                if "bars_held" in valid.columns
                else None,
            }
        )
        row["sample_warning"] = trade_count < int(min_trades)
        rows.append(row)

    if not rows:
        return empty
    result = pd.DataFrame(rows)
    metric_cols = _DISTRIBUTION_METRIC_COLS + ["sample_warning"]
    return result[output_group_cols + metric_cols].reset_index(drop=True)


def excursion_quadrant_counts(
    trades: pd.DataFrame | None,
    tick_size: float,
    *,
    mae_r_threshold: float = 1.0,
    mfe_r_threshold: float = 1.0,
) -> pd.DataFrame:
    """Classify trades into MAE×MFE threshold quadrants.

    The default thresholds answer: did the trade experience at least 1R
    adverse excursion and/or at least 1R favorable excursion?
    """
    if mae_r_threshold <= 0 or mfe_r_threshold <= 0:
        raise ValueError("mae_r_threshold and mfe_r_threshold must be positive.")

    normalized = add_excursion_r_columns(trades, tick_size).dropna(subset=["mae_r", "mfe_r"])
    if normalized.empty:
        return _empty_quadrants()

    labels = {
        (False, False): "neither_threshold_reached",
        (False, True): "target_without_full_stop",
        (True, False): "stop_without_target",
        (True, True): "both_stop_and_target_reached",
    }
    total = len(normalized)
    rows: list[dict[str, Any]] = []
    adverse = normalized["mae_r"] >= float(mae_r_threshold)
    favorable = normalized["mfe_r"] >= float(mfe_r_threshold)
    for key, label in labels.items():
        mask = (adverse == key[0]) & (favorable == key[1])
        group = normalized[mask]
        count = int(len(group))
        rows.append(
            {
                "quadrant": label,
                "count": count,
                "pct": float(count / total) if total else None,
                "avg_mae_r": _finite_mean(group["mae_r"]) if count else None,
                "avg_mfe_r": _finite_mean(group["mfe_r"]) if count else None,
                "avg_r": _finite_mean(group["r_multiple"])
                if count and "r_multiple" in group.columns
                else None,
            }
        )
    return pd.DataFrame(rows, columns=_QUADRANT_COLS)


def sl_tp_hit_probability_grid(
    trades: pd.DataFrame | None,
    tick_size: float,
    stop_r_grid: Iterable[float],
    target_r_grid: Iterable[float],
    *,
    both_hit_rule: str = "stop_first",
) -> pd.DataFrame:
    """Estimate counterfactual target-hit probabilities from terminal excursions.

    The grid is deterministic and uses only each trade's terminal MAE/MFE.  It
    cannot reconstruct intrabar ordering.  When both the candidate stop and
    target were touched by a trade's observed excursion, ``both_hit_rule``
    decides classification:

    - ``"stop_first"`` (default): ambiguous trades count as stop hits.
    - ``"target_first"``: ambiguous trades count as target hits.
    - ``"exclude_ambiguous"``: ambiguous trades leave the denominator.
    """
    if both_hit_rule not in _BOTH_HIT_RULES:
        raise ValueError(f"both_hit_rule must be one of {sorted(_BOTH_HIT_RULES)}.")

    stop_values = _coerce_positive_grid(stop_r_grid)
    target_values = _coerce_positive_grid(target_r_grid)
    if not stop_values or not target_values:
        return _empty_calibration()

    normalized = add_excursion_r_columns(trades, tick_size).dropna(subset=["mae_r", "mfe_r"])
    if normalized.empty:
        return _empty_calibration()

    rows: list[dict[str, Any]] = []
    mae_r = pd.to_numeric(normalized["mae_r"], errors="coerce")
    mfe_r = pd.to_numeric(normalized["mfe_r"], errors="coerce")

    for stop_r in stop_values:
        for target_r in target_values:
            stop_reached = mae_r >= stop_r
            target_reached = mfe_r >= target_r
            ambiguous = stop_reached & target_reached
            if both_hit_rule == "target_first":
                target_hit = target_reached
                stop_hit = stop_reached & ~target_reached
                evaluated = pd.Series(True, index=normalized.index)
            elif both_hit_rule == "exclude_ambiguous":
                target_hit = target_reached & ~stop_reached
                stop_hit = stop_reached & ~target_reached
                evaluated = ~ambiguous
            else:
                target_hit = target_reached & ~stop_reached
                stop_hit = stop_reached
                evaluated = pd.Series(True, index=normalized.index)

            evaluated_count = int(evaluated.sum())
            target_count = int((target_hit & evaluated).sum())
            stop_count = int((stop_hit & evaluated).sum())
            ambiguous_count = int(ambiguous.sum())
            unresolved_count = int((~target_reached & ~stop_reached & evaluated).sum())
            rows.append(
                {
                    "stop_r": stop_r,
                    "target_r": target_r,
                    "evaluated_trade_count": evaluated_count,
                    "target_hit_count": target_count,
                    "stop_hit_count": stop_count,
                    "ambiguous_count": ambiguous_count,
                    "unresolved_count": unresolved_count,
                    "target_hit_probability": float(target_count / evaluated_count)
                    if evaluated_count
                    else None,
                }
            )

    return pd.DataFrame(rows, columns=_CALIBRATION_COLS)


def edge_ratio_summary(
    trades: pd.DataFrame | None,
    tick_size: float,
    *,
    bars_held_bins: Iterable[int] = (1, 3, 5, 10, 20),
) -> dict[str, Any]:
    """Return overall edge-ratio diagnostics and a bars-held decay proxy."""
    normalized = add_excursion_r_columns(trades, tick_size).dropna(subset=["mae_r", "mfe_r"])
    if normalized.empty:
        return {
            "trade_count": 0,
            "mean_mae_r": None,
            "mean_mfe_r": None,
            "mean_edge_ratio_r": None,
            "median_edge_ratio_r": None,
            "decay_by_bars_held": [],
        }

    decay_rows: list[dict[str, Any]] = []
    if "bars_held" in normalized.columns:
        bars = pd.to_numeric(normalized["bars_held"], errors="coerce")
        bins = sorted({int(v) for v in bars_held_bins if int(v) > 0})
        edges = [0, *bins, np.inf]
        labels = [f"1-{bins[0]}"] if bins else []
        if bins:
            for left, right in zip(bins[:-1], bins[1:], strict=False):
                labels.append(f"{left + 1}-{right}")
            labels.append(f">{bins[-1]}")
            bucketed = normalized.assign(
                bars_held_bucket=pd.cut(bars, bins=edges, labels=labels, include_lowest=True)
            )
            for bucket, group in bucketed.groupby("bars_held_bucket", sort=True, observed=True):
                if group.empty:
                    continue
                decay_rows.append(
                    {
                        "bars_held_bucket": str(bucket),
                        "trade_count": int(len(group)),
                        "mean_mfe_r": _finite_mean(group["mfe_r"]),
                        "mean_mae_r": _finite_mean(group["mae_r"]),
                        "mean_edge_ratio_r": _finite_mean(group["edge_ratio_r"]),
                    }
                )

    return {
        "trade_count": int(len(normalized)),
        "mean_mae_r": _finite_mean(normalized["mae_r"]),
        "mean_mfe_r": _finite_mean(normalized["mfe_r"]),
        "mean_edge_ratio_r": _finite_mean(normalized["edge_ratio_r"]),
        "median_edge_ratio_r": _finite_median(normalized["edge_ratio_r"]),
        "decay_by_bars_held": decay_rows,
    }


def excursion_summary(
    trades: pd.DataFrame | None,
    tick_size: float,
    *,
    group_cols: Iterable[str] | str | None = ("direction", "trigger"),
    stop_r_grid: Iterable[float] = (0.5, 0.75, 1.0, 1.25, 1.5),
    target_r_grid: Iterable[float] = (0.5, 1.0, 1.5, 2.0, 3.0),
    both_hit_rule: str = "stop_first",
    min_trades: int = 10,
    mae_r_threshold: float = 1.0,
    mfe_r_threshold: float = 1.0,
) -> dict[str, Any]:
    """Build the R10 export contract from completed trades."""
    normalized = add_excursion_r_columns(trades, tick_size)
    grouped = excursion_distribution(
        normalized, tick_size, group_cols=group_cols, min_trades=min_trades
    )
    quadrants = excursion_quadrant_counts(
        normalized,
        tick_size,
        mae_r_threshold=mae_r_threshold,
        mfe_r_threshold=mfe_r_threshold,
    )
    calibration = sl_tp_hit_probability_grid(
        normalized,
        tick_size,
        stop_r_grid=stop_r_grid,
        target_r_grid=target_r_grid,
        both_hit_rule=both_hit_rule,
    )
    edge = edge_ratio_summary(normalized, tick_size)
    valid_trade_count = int(normalized.dropna(subset=["mae_r", "mfe_r"]).shape[0])
    return {
        "schema_version": 1,
        "available": valid_trade_count > 0,
        "trade_count": valid_trade_count,
        "config": {
            "tick_size": float(tick_size),
            "group_cols": list(_normalize_group_cols(group_cols, normalized)),
            "stop_r_grid": _coerce_positive_grid(stop_r_grid),
            "target_r_grid": _coerce_positive_grid(target_r_grid),
            "both_hit_rule": both_hit_rule,
            "min_trades": int(min_trades),
            "mae_r_threshold": float(mae_r_threshold),
            "mfe_r_threshold": float(mfe_r_threshold),
        },
        "overall": excursion_distribution(normalized, tick_size).to_dict(orient="records"),
        "grouped": grouped.to_dict(orient="records"),
        "quadrants": quadrants.to_dict(orient="records"),
        "calibration_grid": calibration.to_dict(orient="records"),
        "edge_ratio": edge,
        "caveat": (
            "Excursion analytics use terminal bar-level MAE/MFE. Counterfactual SL/TP "
            "probabilities cannot prove intrabar event order; ambiguous both-hit cases "
            f"use both_hit_rule={both_hit_rule!r}."
        ),
    }
