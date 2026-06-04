"""Phase 5/6/7 analytics: trade performance metrics, grid search, and time analysis."""
from __future__ import annotations

from .grid import best_grid_result, run_sl_tp_grid
from .metrics import equity_curve, summarize_trades
from .time_analysis import add_time_buckets, pivot_time_metric, summarize_by_group

__all__ = [
    "summarize_trades",
    "equity_curve",
    "run_sl_tp_grid",
    "best_grid_result",
    "add_time_buckets",
    "summarize_by_group",
    "pivot_time_metric",
]
