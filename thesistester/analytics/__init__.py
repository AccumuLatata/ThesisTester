"""Phase 5/6/7/8 analytics: trade performance metrics, grid search, time analysis,
and statistical validation."""
from __future__ import annotations

from .grid import best_grid_result, run_sl_tp_grid
from .metrics import equity_curve, summarize_trades
from .time_analysis import add_time_buckets, pivot_time_metric, summarize_by_group
from .validation import (
    bootstrap_expectancy_ci,
    grid_overfit_diagnostics,
    permutation_test_expectancy,
    trade_count_diagnostics,
    validation_summary,
)

__all__ = [
    "summarize_trades",
    "equity_curve",
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
]
