"""R11 analytics — Monte Carlo path robustness diagnostics.

All functions operate on the realized ``r_multiple`` sequence from completed
Phase 5 trades.  No trade re-simulation is performed.

Caveats
-------
- Reshuffle tests path/order risk only; it preserves the exact multiset of
  realized trade outcomes.
- Skip treats missed trades as independent random omissions by replacing those
  trade slots with 0R.  It does not model calendar clustering, liquidity, or
  execution-state dependence.
- Block resampling preserves local streak structure better than iid sampling,
  but it remains a bootstrap approximation, not a proof of future robustness.
- Outputs are diagnostics, not proof of edge.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

_DEFAULT_PERCENTILES = (5.0, 25.0, 50.0, 75.0, 95.0)
_DEFAULT_DRAWDOWN_THRESHOLDS_R = (3.0, 5.0, 10.0)
_METHODS = ("reshuffle", "skip", "block_resample")


def _percentile_key(percentile: float) -> str:
    return f"p{int(percentile):02d}" if float(percentile).is_integer() else f"p{percentile:g}"


def _coerce_percentiles(percentiles: Iterable[float]) -> tuple[float, ...]:
    values: list[float] = []
    for percentile in percentiles:
        p = float(percentile)
        if not 0 <= p <= 100:
            raise ValueError("percentiles must be between 0 and 100.")
        values.append(p)
    if not values:
        raise ValueError("percentiles must contain at least one value.")
    return tuple(sorted(dict.fromkeys(values)))


def _coerce_thresholds(thresholds: Iterable[float]) -> tuple[float, ...]:
    values: list[float] = []
    for threshold in thresholds:
        t = float(threshold)
        if np.isfinite(t) and t > 0:
            values.append(round(t, 10))
    return tuple(sorted(dict.fromkeys(values)))


def _ordered_r_multiples(trades: pd.DataFrame | None) -> np.ndarray:
    if trades is None or trades.empty or "r_multiple" not in trades.columns:
        return np.array([], dtype=float)
    ordered = trades.copy()
    if "exit_timestamp" in ordered.columns:
        ordered = ordered.sort_values("exit_timestamp")
    return pd.to_numeric(ordered["r_multiple"], errors="coerce").dropna().to_numpy(dtype=float)


def _max_loss_streak(r: np.ndarray) -> int:
    max_run = 0
    current = 0
    for value in r:
        if value < 0:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return int(max_run)


def _cumulative_r(r: np.ndarray) -> np.ndarray:
    return np.cumsum(np.asarray(r, dtype=float))


def _max_drawdown_r(cum_r: np.ndarray) -> float:
    if cum_r.size == 0:
        return 0.0
    running_max = np.maximum.accumulate(np.maximum(cum_r, 0.0))
    return float(np.max(running_max - cum_r))


def path_metrics_from_r(r: Iterable[float] | np.ndarray) -> dict[str, Any]:
    """Return path metrics for one R-multiple sequence."""
    values = np.asarray(list(r), dtype=float)
    values = values[~np.isnan(values)]
    if values.size == 0:
        return {"final_r": 0.0, "max_drawdown_r": 0.0, "max_loss_streak": 0}
    cum_r = _cumulative_r(values)
    return {
        "final_r": float(cum_r[-1]),
        "max_drawdown_r": _max_drawdown_r(cum_r),
        "max_loss_streak": _max_loss_streak(values),
    }


def _observed_equity(r: np.ndarray) -> dict[str, list[float] | list[int]]:
    return {
        "trade_index": list(range(1, len(r) + 1)),
        "cum_r": [float(v) for v in _cumulative_r(r)],
    }


def _metric_percentiles(
    metric_values: np.ndarray, percentiles: tuple[float, ...]
) -> dict[str, float]:
    return {
        _percentile_key(p): float(np.percentile(metric_values, p))
        for p in percentiles
        if metric_values.size > 0
    }


def _equity_fan(
    paths: np.ndarray,
    observed_r: np.ndarray,
    percentiles: tuple[float, ...],
) -> dict[str, list[float] | list[int]]:
    if paths.size == 0:
        return {"trade_index": [], "observed_cum_r": []}
    path_cum = np.cumsum(paths, axis=1)
    fan: dict[str, list[float] | list[int]] = {
        "trade_index": list(range(1, paths.shape[1] + 1)),
        "observed_cum_r": [float(v) for v in _cumulative_r(observed_r)],
    }
    for p in percentiles:
        fan[_percentile_key(p)] = [float(v) for v in np.percentile(path_cum, p, axis=0)]
    return fan


def _probability_drawdown_exceeds(
    max_drawdowns: np.ndarray,
    thresholds: tuple[float, ...],
) -> list[dict[str, float]]:
    return [
        {
            "threshold_r": float(threshold),
            "probability": float((max_drawdowns > threshold).mean())
            if max_drawdowns.size > 0
            else 0.0,
        }
        for threshold in thresholds
    ]


def _empty_method_result(
    *,
    method: str,
    n_simulations: int,
    percentiles: tuple[float, ...],
    drawdown_thresholds_r: tuple[float, ...],
    observed_r: np.ndarray,
) -> dict[str, Any]:
    observed = path_metrics_from_r(observed_r)
    return {
        "method": method,
        "trade_count": int(len(observed_r)),
        "n_simulations": int(n_simulations),
        "observed": observed,
        "simulated": {
            "final_r": {},
            "max_drawdown_r": {},
            "max_loss_streak": {},
        },
        "probability_drawdown_exceeds": [
            {"threshold_r": float(threshold), "probability": None}
            for threshold in drawdown_thresholds_r
        ],
        "equity_fan": {"trade_index": [], "observed_cum_r": []},
        "percentiles": [float(p) for p in percentiles],
    }


def _build_method_result(
    *,
    method: str,
    observed_r: np.ndarray,
    paths: np.ndarray,
    percentiles: tuple[float, ...],
    drawdown_thresholds_r: tuple[float, ...],
    include_paths: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if paths.size == 0:
        return _empty_method_result(
            method=method,
            n_simulations=0,
            percentiles=percentiles,
            drawdown_thresholds_r=drawdown_thresholds_r,
            observed_r=observed_r,
        )

    final_r = paths.sum(axis=1)
    path_cum = np.cumsum(paths, axis=1)
    max_drawdown_r = np.array([_max_drawdown_r(row) for row in path_cum], dtype=float)
    max_loss_streak = np.array([_max_loss_streak(row) for row in paths], dtype=float)
    result: dict[str, Any] = {
        "method": method,
        "trade_count": int(len(observed_r)),
        "n_simulations": int(paths.shape[0]),
        "observed": path_metrics_from_r(observed_r),
        "simulated": {
            "final_r": _metric_percentiles(final_r, percentiles),
            "max_drawdown_r": _metric_percentiles(max_drawdown_r, percentiles),
            "max_loss_streak": _metric_percentiles(max_loss_streak, percentiles),
        },
        "probability_drawdown_exceeds": _probability_drawdown_exceeds(
            max_drawdown_r, drawdown_thresholds_r
        ),
        "equity_fan": _equity_fan(paths, observed_r, percentiles),
        "percentiles": [float(p) for p in percentiles],
    }
    if extra:
        result.update(extra)
    if include_paths:
        result["simulation_paths"] = paths.tolist()
    return result


def monte_carlo_reshuffle(
    trades: pd.DataFrame | None,
    *,
    n_simulations: int = 2000,
    percentiles: Iterable[float] = _DEFAULT_PERCENTILES,
    drawdown_thresholds_r: Iterable[float] = _DEFAULT_DRAWDOWN_THRESHOLDS_R,
    random_state: int | None = 42,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Monte Carlo path risk by permuting realized trade order."""
    observed_r = _ordered_r_multiples(trades)
    pct = _coerce_percentiles(percentiles)
    thresholds = _coerce_thresholds(drawdown_thresholds_r)
    if observed_r.size == 0 or n_simulations <= 0:
        return _empty_method_result(
            method="reshuffle",
            n_simulations=n_simulations,
            percentiles=pct,
            drawdown_thresholds_r=thresholds,
            observed_r=observed_r,
        )
    rng = np.random.default_rng(random_state)
    paths = np.vstack([rng.permutation(observed_r) for _ in range(int(n_simulations))])
    return _build_method_result(
        method="reshuffle",
        observed_r=observed_r,
        paths=paths,
        percentiles=pct,
        drawdown_thresholds_r=thresholds,
        include_paths=include_paths,
    )


def monte_carlo_skip(
    trades: pd.DataFrame | None,
    *,
    skip_fraction: float = 0.10,
    n_simulations: int = 2000,
    percentiles: Iterable[float] = _DEFAULT_PERCENTILES,
    drawdown_thresholds_r: Iterable[float] = _DEFAULT_DRAWDOWN_THRESHOLDS_R,
    random_state: int | None = 42,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Monte Carlo missed-fill robustness by randomly omitting trades.

    Omitted trades are represented as 0R at their original chronological slot,
    keeping equity fan charts aligned to the observed trade index.
    """
    if not 0 <= skip_fraction < 1:
        raise ValueError("skip_fraction must be in [0, 1).")
    observed_r = _ordered_r_multiples(trades)
    pct = _coerce_percentiles(percentiles)
    thresholds = _coerce_thresholds(drawdown_thresholds_r)
    if observed_r.size == 0 or n_simulations <= 0:
        return _empty_method_result(
            method="skip",
            n_simulations=n_simulations,
            percentiles=pct,
            drawdown_thresholds_r=thresholds,
            observed_r=observed_r,
        )
    rng = np.random.default_rng(random_state)
    keep_probability = 1.0 - float(skip_fraction)
    masks = rng.random((int(n_simulations), observed_r.size)) < keep_probability
    paths = masks * observed_r
    return _build_method_result(
        method="skip",
        observed_r=observed_r,
        paths=paths,
        percentiles=pct,
        drawdown_thresholds_r=thresholds,
        include_paths=include_paths,
        extra={"skip_fraction": float(skip_fraction)},
    )


def _stationary_block_path(
    r: np.ndarray, rng: np.random.Generator, block_length: int
) -> np.ndarray:
    chunks: list[np.ndarray] = []
    n = len(r)
    while sum(len(chunk) for chunk in chunks) < n:
        start = int(rng.integers(0, n))
        idx = (start + np.arange(block_length)) % n
        chunks.append(r[idx])
    return np.concatenate(chunks)[:n]


def monte_carlo_block_resample(
    trades: pd.DataFrame | None,
    *,
    block_length: int | None = None,
    n_simulations: int = 2000,
    percentiles: Iterable[float] = _DEFAULT_PERCENTILES,
    drawdown_thresholds_r: Iterable[float] = _DEFAULT_DRAWDOWN_THRESHOLDS_R,
    random_state: int | None = 42,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Monte Carlo path risk via circular fixed-block bootstrap."""
    observed_r = _ordered_r_multiples(trades)
    pct = _coerce_percentiles(percentiles)
    thresholds = _coerce_thresholds(drawdown_thresholds_r)
    if observed_r.size == 0 or n_simulations <= 0:
        return _empty_method_result(
            method="block_resample",
            n_simulations=n_simulations,
            percentiles=pct,
            drawdown_thresholds_r=thresholds,
            observed_r=observed_r,
        )
    n = observed_r.size
    resolved_block_length = int(block_length or max(2, round(np.sqrt(n))))
    if resolved_block_length <= 0:
        raise ValueError("block_length must be positive.")
    rng = np.random.default_rng(random_state)
    paths = np.vstack(
        [
            _stationary_block_path(observed_r, rng, resolved_block_length)
            for _ in range(int(n_simulations))
        ]
    )
    return _build_method_result(
        method="block_resample",
        observed_r=observed_r,
        paths=paths,
        percentiles=pct,
        drawdown_thresholds_r=thresholds,
        include_paths=include_paths,
        extra={"block_length": resolved_block_length},
    )


def _strip_simulation_paths(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "simulation_paths"}


def monte_carlo_summary(
    trades: pd.DataFrame | None,
    *,
    methods: Iterable[str] = _METHODS,
    n_simulations: int = 2000,
    skip_fraction: float = 0.10,
    block_length: int | None = None,
    percentiles: Iterable[float] = _DEFAULT_PERCENTILES,
    drawdown_thresholds_r: Iterable[float] = _DEFAULT_DRAWDOWN_THRESHOLDS_R,
    random_state: int | None = 42,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Build the R11 Monte Carlo export contract from completed trades."""
    method_list = [method for method in methods if method in _METHODS]
    pct = _coerce_percentiles(percentiles)
    thresholds = _coerce_thresholds(drawdown_thresholds_r)
    observed_r = _ordered_r_multiples(trades)
    block_len = (
        int(block_length or max(2, round(np.sqrt(len(observed_r))))) if len(observed_r) else None
    )
    config = {
        "methods": method_list,
        "n_simulations": int(n_simulations),
        "skip_fraction": float(skip_fraction),
        "block_length": block_len,
        "drawdown_thresholds_r": [float(v) for v in thresholds],
        "percentiles": [float(v) for v in pct],
        "random_state": random_state,
    }
    if observed_r.size == 0:
        return {
            "schema_version": 1,
            "available": False,
            "trade_count": 0,
            "config": config,
            "observed_equity": {"trade_index": [], "cum_r": []},
            "methods": {},
            "caveat": "Monte Carlo diagnostics require completed trades with r_multiple values.",
        }

    results: dict[str, Any] = {}
    if "reshuffle" in method_list:
        results["reshuffle"] = monte_carlo_reshuffle(
            trades,
            n_simulations=n_simulations,
            percentiles=pct,
            drawdown_thresholds_r=thresholds,
            random_state=random_state,
            include_paths=include_paths,
        )
    if "skip" in method_list:
        results["skip"] = monte_carlo_skip(
            trades,
            skip_fraction=skip_fraction,
            n_simulations=n_simulations,
            percentiles=pct,
            drawdown_thresholds_r=thresholds,
            random_state=random_state,
            include_paths=include_paths,
        )
    if "block_resample" in method_list:
        results["block_resample"] = monte_carlo_block_resample(
            trades,
            block_length=block_len,
            n_simulations=n_simulations,
            percentiles=pct,
            drawdown_thresholds_r=thresholds,
            random_state=random_state,
            include_paths=include_paths,
        )

    if not include_paths:
        results = {name: _strip_simulation_paths(result) for name, result in results.items()}

    return {
        "schema_version": 1,
        "available": True,
        "trade_count": int(observed_r.size),
        "config": config,
        "observed_equity": _observed_equity(observed_r),
        "methods": results,
        "caveat": (
            "Monte Carlo outputs are diagnostics on the realized trade sequence. "
            "They do not prove future edge or replace out-of-sample validation."
        ),
    }
