"""Phase 5/6/7/8 analytics: trade performance metrics, grid search, time analysis,
and statistical validation."""

from __future__ import annotations

from .excursions import (
    add_excursion_r_columns,
    edge_ratio_summary,
    excursion_distribution,
    excursion_quadrant_counts,
    excursion_summary,
    sl_tp_hit_probability_grid,
)
from .grid import best_grid_result, run_sl_tp_grid
from .metrics import equity_curve, summarize_trades, summarize_trades_by_direction
from .monte_carlo import (
    monte_carlo_block_resample,
    monte_carlo_reshuffle,
    monte_carlo_skip,
    monte_carlo_summary,
    path_metrics_from_r,
)
from .noise import (
    assert_valid_ohlc,
    noise_summary,
    perturb_ohlc,
    rolling_atr,
    trade_persistence_rate,
)
from .overfitting import (
    GridSequenceResult,
    cscv_pbo,
    deflated_sharpe,
    grid_trade_sequences,
    overfitting_summary,
    probabilistic_sharpe,
    vs_random_benchmark,
)
from .sensitivity import sensitivity_summary
from .time_analysis import add_time_buckets, pivot_time_metric, summarize_by_group
from .validation import (
    bootstrap_expectancy_ci,
    grid_overfit_diagnostics,
    permutation_test_expectancy,
    trade_count_diagnostics,
    validation_summary,
)
from .walk_forward import (
    WalkForwardResult,
    run_walk_forward_sl_tp,
    run_wfa_matrix,
    summarize_walk_forward,
)

__all__ = [
    "summarize_trades",
    "summarize_trades_by_direction",
    "equity_curve",
    "path_metrics_from_r",
    "monte_carlo_reshuffle",
    "monte_carlo_skip",
    "monte_carlo_block_resample",
    "monte_carlo_summary",
    "rolling_atr",
    "assert_valid_ohlc",
    "perturb_ohlc",
    "trade_persistence_rate",
    "noise_summary",
    "GridSequenceResult",
    "grid_trade_sequences",
    "cscv_pbo",
    "probabilistic_sharpe",
    "deflated_sharpe",
    "vs_random_benchmark",
    "overfitting_summary",
    "sensitivity_summary",
    "add_excursion_r_columns",
    "edge_ratio_summary",
    "excursion_distribution",
    "excursion_quadrant_counts",
    "excursion_summary",
    "sl_tp_hit_probability_grid",
    "run_sl_tp_grid",
    "best_grid_result",
    "add_time_buckets",
    "summarize_by_group",
    "pivot_time_metric",
    "bootstrap_expectancy_ci",
    "permutation_test_expectancy",
    "trade_count_diagnostics",
    "grid_overfit_diagnostics",
    "validation_summary",
    "run_walk_forward_sl_tp",
    "run_wfa_matrix",
    "summarize_walk_forward",
    "WalkForwardResult",
]
