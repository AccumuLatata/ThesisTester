"""R15 multiple-testing diagnostics: CSCV/PBO, PSR/DSR, and vs-random."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from thesistester.analytics.grid import _directional_grid_metrics
from thesistester.analytics.metrics import summarize_trades
from thesistester.engine.backtest import simulate_trades

CellKey = tuple[float, float, float | None, float | None, float | None]
_NORMAL_EULER_GAMMA = 0.5772156649015329
_SIMULATION_KWARGS = {
    "max_holding_bars",
    "allow_same_bar_exit",
    "commission_per_side",
    "slippage_ticks",
    "flat_by_session_close",
    "session_close_time",
    "session_timezone",
    "no_new_entries_after",
    "exposure_policy",
    "cooldown_bars_after_exit",
    "intrabar_model",
    "subtimeframe_data",
    "parent_interval",
    "sub_interval",
    # SW5: fixed Admit constraint (not a swept axis)
    "entry_window",
    "entry_window_exchange_tz",
}


@dataclass(frozen=True)
class GridSequenceResult:
    """Opt-in grid summaries plus ordered per-cell trade sequences."""

    grid_results: pd.DataFrame
    cell_trades: dict[CellKey, pd.DataFrame]
    schema_version: int = 1


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_ppf(probability: float) -> float:
    """Acklam inverse-normal approximation; adequate for diagnostic thresholds."""
    if not 0.0 < probability < 1.0:
        raise ValueError("probability must be in (0, 1)")
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    if probability < 0.02425:
        q = math.sqrt(-2.0 * math.log(probability))
        numerator = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q) + c[5]
        denominator = ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q) + 1.0
        return numerator / denominator
    if probability > 1.0 - 0.02425:
        q = math.sqrt(-2.0 * math.log(1.0 - probability))
        numerator = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q) + c[5]
        denominator = ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q) + 1.0
        return -(numerator / denominator)
    q = probability - 0.5
    r = q * q
    numerator = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r) + a[5]
    denominator = (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r) + 1.0
    return numerator * q / denominator


def _r_values(trades: pd.DataFrame | None) -> np.ndarray:
    if trades is None or trades.empty or "r_multiple" not in trades:
        return np.array([], dtype=float)
    values = pd.to_numeric(trades["r_multiple"], errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]


def _cell_key(row: Mapping[str, Any]) -> CellKey:
    def optional(key: str) -> float | None:
        value = row.get(key)
        return None if value is None or pd.isna(value) else float(value)

    return (
        float(row["stop_loss_ticks"]),
        float(row["take_profit_ticks"]),
        optional("breakeven_after_r"),
        optional("trailing_after_r"),
        optional("trailing_distance_ticks"),
    )


def grid_trade_sequences(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    tick_size: float,
    point_value: float,
    grid: pd.DataFrame,
    execution_kwargs: Mapping[str, Any] | None = None,
) -> GridSequenceResult:
    """Re-simulate grid cells with the Grid Search metric schema and trade sequences."""
    if grid is None or grid.empty:
        return GridSequenceResult(pd.DataFrame(), {})
    kwargs = {
        key: value
        for key, value in dict(execution_kwargs or {}).items()
        if key in _SIMULATION_KWARGS
    }
    sequences: dict[CellKey, pd.DataFrame] = {}
    rows: list[dict[str, Any]] = []
    for _, row in grid.sort_values(
        [
            "stop_loss_ticks",
            "take_profit_ticks",
            "breakeven_after_r",
            "trailing_after_r",
            "trailing_distance_ticks",
        ],
        na_position="first",
    ).iterrows():
        key = _cell_key(row)
        trades = simulate_trades(
            df=df,
            signals=signals,
            tick_size=tick_size,
            point_value=point_value,
            stop_loss_ticks=key[0],
            take_profit_ticks=key[1],
            breakeven_after_r=key[2],
            trailing_after_r=key[3],
            trailing_distance_ticks=key[4],
            **kwargs,
        )
        ordered = trades.sort_values(
            ["exit_timestamp", "entry_timestamp", "signal_id", "trade_id"],
            kind="mergesort",
        ).reset_index(drop=True)
        sequences[key] = ordered
        rows.append(
            {
                "stop_loss_ticks": key[0],
                "take_profit_ticks": key[1],
                "breakeven_after_r": key[2],
                "trailing_after_r": key[3],
                "trailing_distance_ticks": key[4],
                **summarize_trades(ordered),
                **_directional_grid_metrics(ordered),
            }
        )
    return GridSequenceResult(pd.DataFrame(rows), sequences)


def _partition_returns(values: np.ndarray, partitions: int) -> list[np.ndarray]:
    return [
        values[(np.arange(len(values)) * partitions // len(values)) == partition]
        for partition in range(partitions)
    ]


def _sortable_cell_key(key: CellKey) -> tuple[float, ...]:
    return tuple(-1.0 if value is None else float(value) for value in key)


def cscv_pbo(
    cell_trades: Mapping[CellKey, pd.DataFrame],
    *,
    partitions: int = 8,
    min_trades: int = 1,
) -> dict[str, Any]:
    """Estimate PBO with deterministic contiguous trade-sequence CSCV."""
    if partitions < 4 or partitions % 2:
        raise ValueError("partitions must be an even integer >= 4.")
    eligible: dict[CellKey, pd.DataFrame] = {
        key: trades.copy()
        for key, trades in cell_trades.items()
        if len(_r_values(trades)) >= int(min_trades)
    }
    base = {
        "available": False,
        "pbo": None,
        "n_partitions": int(partitions),
        "n_strategies": len(eligible),
        "n_combinations": 0,
        "split_results": [],
        "median_logit_lambda": None,
        "caveat": "CSCV partitions contiguous realized trade R sequences; it is not purged CV.",
    }
    if len(eligible) < 2:
        return base
    universe = pd.concat(
        [
            pd.to_datetime(trades["exit_timestamp"], errors="coerce", utc=True)
            for trades in eligible.values()
        ],
        ignore_index=True,
    ).dropna()
    timestamps = pd.Index(universe.unique()).sort_values()
    if len(timestamps) < partitions:
        return base
    timestamp_partitions = {
        timestamp: int(index * partitions // len(timestamps))
        for index, timestamp in enumerate(timestamps)
    }
    partitioned: dict[CellKey, list[np.ndarray]] = {}
    for key, trades in eligible.items():
        work = trades.copy()
        work["_r15_timestamp"] = pd.to_datetime(work["exit_timestamp"], errors="coerce", utc=True)
        work["_r15_r"] = pd.to_numeric(work["r_multiple"], errors="coerce")
        work = work.dropna(subset=["_r15_timestamp", "_r15_r"])
        partitioned[key] = [
            work.loc[
                work["_r15_timestamp"].map(timestamp_partitions).eq(partition),
                "_r15_r",
            ].to_numpy(dtype=float)
            for partition in range(partitions)
        ]
    splits: list[dict[str, Any]] = []
    lambdas: list[float] = []
    for is_blocks in combinations(range(partitions), partitions // 2):
        oos_blocks = tuple(index for index in range(partitions) if index not in is_blocks)
        candidates: list[tuple[float, CellKey, float]] = []
        for key, block_values in partitioned.items():
            is_r = np.concatenate([block_values[index] for index in is_blocks])
            oos_r = np.concatenate([block_values[index] for index in oos_blocks])
            if len(is_r) < min_trades or len(oos_r) < min_trades:
                continue
            candidates.append((float(is_r.mean()), key, float(oos_r.mean())))
        if len(candidates) < 2:
            continue
        candidates.sort(key=lambda item: (-item[0], _sortable_cell_key(item[1])))
        selected_is, selected_key, selected_oos = candidates[0]
        oos_scores = np.array([item[2] for item in candidates], dtype=float)
        rank_worst_one = 1.0 + float((oos_scores < selected_oos).sum())
        rank_worst_one += float((oos_scores == selected_oos).sum() - 1) / 2.0
        omega = rank_worst_one / (len(candidates) + 1.0)
        logit = math.log(omega / (1.0 - omega))
        lambdas.append(logit)
        splits.append(
            {
                "is_blocks": list(is_blocks),
                "oos_blocks": list(oos_blocks),
                "selected_cell": list(selected_key),
                "selected_is_mean_r": selected_is,
                "selected_oos_mean_r": selected_oos,
                "oos_rank_worst_one": rank_worst_one,
                "eligible_strategies": len(candidates),
                "omega": omega,
                "logit_lambda": logit,
            }
        )
    if not splits:
        return base
    return {
        **base,
        "available": True,
        "pbo": float(np.mean(np.array(lambdas) <= 0.0)),
        "n_combinations": len(splits),
        "split_results": splits,
        "median_logit_lambda": float(np.median(lambdas)),
    }


def probabilistic_sharpe(
    trades: pd.DataFrame,
    *,
    benchmark_sharpe: float = 0.0,
) -> dict[str, Any]:
    """Compute unannualized PSR from realized per-trade R multiples."""
    values = _r_values(trades)
    empty = {
        "available": False,
        "n_trades": int(len(values)),
        "sharpe_like_r": None,
        "psr": None,
        "benchmark_sharpe": float(benchmark_sharpe),
        "skew": None,
        "kurtosis": None,
        "annualized": False,
    }
    if len(values) < 4:
        return empty
    std = float(np.std(values, ddof=1))
    if not math.isfinite(std) or std <= 0:
        return empty
    sr = float(np.mean(values) / std)
    centered = (values - np.mean(values)) / std
    skew = float(np.mean(centered**3))
    kurtosis = float(np.mean(centered**4))
    denominator_squared = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr**2
    if denominator_squared <= 0 or not math.isfinite(denominator_squared):
        return empty
    z = (sr - float(benchmark_sharpe)) * math.sqrt(len(values) - 1) / math.sqrt(denominator_squared)
    return {
        **empty,
        "available": True,
        "sharpe_like_r": sr,
        "psr": _normal_cdf(z),
        "skew": skew,
        "kurtosis": kurtosis,
    }


def deflated_sharpe(
    selected_trades: pd.DataFrame,
    trial_sharpes: Iterable[float],
    *,
    effective_trials: int | None = None,
) -> dict[str, Any]:
    """Deflate PSR using declared/effective grid trial count."""
    sharpe_values = np.array(
        [float(value) for value in trial_sharpes if value is not None and np.isfinite(value)],
        dtype=float,
    )
    n_trials = int(effective_trials or len(sharpe_values))
    base = probabilistic_sharpe(selected_trades)
    result = {
        **base,
        "dsr": None,
        "effective_trials": n_trials,
        "tested_trial_sharpes": int(len(sharpe_values)),
        "expected_max_sharpe": None,
    }
    if not base["available"] or len(sharpe_values) < 2 or n_trials < 2:
        return result
    sigma_sr = float(np.std(sharpe_values, ddof=1))
    if sigma_sr <= 0 or not math.isfinite(sigma_sr):
        return result
    expected_max = sigma_sr * (
        (1.0 - _NORMAL_EULER_GAMMA) * _normal_ppf(1.0 - 1.0 / n_trials)
        + _NORMAL_EULER_GAMMA * _normal_ppf(1.0 - 1.0 / (n_trials * math.e))
    )
    psr_deflated = probabilistic_sharpe(
        selected_trades,
        benchmark_sharpe=expected_max,
    )
    return {
        **result,
        "dsr": psr_deflated["psr"] if psr_deflated["available"] else None,
        "expected_max_sharpe": expected_max,
    }


def random_entry_signals(
    reference_trades: pd.DataFrame,
    *,
    n_bars: int,
    random_state: int,
) -> pd.DataFrame:
    """Create deterministic, direction-matched random next-open candidate signals."""
    if reference_trades is None or reference_trades.empty or n_bars < 2:
        return pd.DataFrame()
    directions = reference_trades["direction"].astype(str).to_numpy()
    n = min(len(directions), n_bars - 1)
    rng = np.random.default_rng(random_state)
    indices = np.sort(rng.choice(np.arange(n_bars - 1), size=n, replace=False))
    sampled_directions = rng.choice(directions, size=n, replace=True)
    return pd.DataFrame(
        {
            "signal_id": np.arange(1, n + 1),
            "bar_index": indices,
            "trigger": ["touch"] * n,
            "direction": sampled_directions,
            "status": ["candidate"] * n,
        }
    )


def vs_random_benchmark(
    df: pd.DataFrame,
    reference_trades: pd.DataFrame,
    *,
    tick_size: float,
    point_value: float,
    stop_loss_ticks: float,
    take_profit_ticks: float,
    execution_kwargs: Mapping[str, Any] | None = None,
    n_replicas: int = 500,
    random_state: int = 42,
) -> dict[str, Any]:
    """Compare observed expectancy to seeded random next-open entry schedules."""
    observed = _r_values(reference_trades)
    base = {
        "available": False,
        "n_replicas": int(n_replicas),
        "observed_expectancy_r": None,
        "null_expectancy_mean": None,
        "null_expectancy_std": None,
        "percentile": None,
        "p_value_greater_or_equal": None,
        "replica_expectancies": [],
    }
    if len(observed) == 0 or n_replicas <= 0 or len(df) < 2:
        return base
    observed_mean = float(observed.mean())
    seed_sequence = np.random.SeedSequence(random_state)
    expectancies: list[float] = []
    kwargs = dict(execution_kwargs or {})
    for child in seed_sequence.spawn(int(n_replicas)):
        seed = int(child.generate_state(1)[0])
        signals = random_entry_signals(
            reference_trades,
            n_bars=len(df),
            random_state=seed,
        )
        trades = simulate_trades(
            df=df,
            signals=signals,
            tick_size=tick_size,
            point_value=point_value,
            stop_loss_ticks=stop_loss_ticks,
            take_profit_ticks=take_profit_ticks,
            **kwargs,
        )
        values = _r_values(trades)
        expectancies.append(float(values.mean()) if len(values) else 0.0)
    null_values = np.array(expectancies, dtype=float)
    return {
        **base,
        "available": True,
        "observed_expectancy_r": observed_mean,
        "null_expectancy_mean": float(null_values.mean()),
        "null_expectancy_std": float(null_values.std(ddof=1)) if len(null_values) > 1 else 0.0,
        "percentile": float((null_values < observed_mean).mean() * 100.0),
        "p_value_greater_or_equal": float(
            (1 + (null_values >= observed_mean).sum()) / (len(null_values) + 1)
        ),
        "replica_expectancies": expectancies,
    }


def overfitting_summary(
    *,
    selected_trades: pd.DataFrame,
    cell_trades: Mapping[CellKey, pd.DataFrame],
    grid_results: pd.DataFrame,
    df: pd.DataFrame | None,
    tick_size: float,
    point_value: float,
    execution_kwargs: Mapping[str, Any] | None = None,
    selected_grid_metric: str = "expectancy_r",
    selected_min_trades: int = 1,
    pbo_partitions: int = 8,
    pbo_min_trades: int = 1,
    vs_random_n_replicas: int = 500,
    random_state: int = 42,
) -> dict[str, Any]:
    """Build the schema-versioned R15 diagnostic artifact."""
    pbo = cscv_pbo(
        cell_trades,
        partitions=pbo_partitions,
        min_trades=pbo_min_trades,
    )
    trial_sharpes = pd.to_numeric(
        grid_results.get("sharpe_like_r", pd.Series(dtype=float)),
        errors="coerce",
    ).dropna()
    dsr = deflated_sharpe(
        selected_trades,
        trial_sharpes,
        effective_trials=int(len(grid_results)),
    )
    selected_execution = dict(execution_kwargs or {})
    if selected_trades is not None and not selected_trades.empty:
        for key in (
            "breakeven_after_r",
            "trailing_after_r",
            "trailing_distance_ticks",
        ):
            value = selected_trades[key].iloc[0] if key in selected_trades else None
            selected_execution[key] = None if pd.isna(value) else value
    random = (
        vs_random_benchmark(
            df,
            selected_trades,
            tick_size=tick_size,
            point_value=point_value,
            stop_loss_ticks=float(selected_trades["stop_loss_ticks"].iloc[0]),
            take_profit_ticks=float(selected_trades["take_profit_ticks"].iloc[0]),
            execution_kwargs=selected_execution,
            n_replicas=vs_random_n_replicas,
            random_state=random_state,
        )
        if df is not None and selected_trades is not None and not selected_trades.empty
        else {"available": False}
    )
    return {
        "schema_version": 1,
        "available": bool(pbo["available"] or dsr["available"] or random["available"]),
        "config": {
            "pbo_partitions": int(pbo_partitions),
            "pbo_min_trades": int(pbo_min_trades),
            "vs_random_n_replicas": int(vs_random_n_replicas),
            "random_state": int(random_state),
            "sharpe_annualized": False,
            "selected_grid_metric": selected_grid_metric,
            "selected_min_trades": int(selected_min_trades),
        },
        "pbo": pbo,
        "deflated_sharpe": dsr,
        "vs_random": random,
        "caveat": (
            "Diagnostic only. CSCV uses contiguous realized trade-R blocks, DSR only "
            "deflates declared grid trials, and vs-random tests a random-entry timing null."
        ),
    }
