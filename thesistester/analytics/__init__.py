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
from .time_analysis import add_time_buckets, pivot_time_metric, summarize_by_group
from .validation import (
    bootstrap_expectancy_ci,
    grid_overfit_diagnostics,
    permutation_test_expectancy,
    trade_count_diagnostics,
    validation_summary,
)
from .walk_forward import run_walk_forward_sl_tp, summarize_walk_forward

__all__ = [
    "summarize_trades",
    "summarize_trades_by_direction",
    "equity_curve",
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
    "summarize_walk_forward",
]
