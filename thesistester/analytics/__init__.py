"""Phase 5/6 analytics: trade performance metrics and grid search."""
from __future__ import annotations

from .grid import best_grid_result, run_sl_tp_grid
from .metrics import equity_curve, summarize_trades

__all__ = [
    "summarize_trades",
    "equity_curve",
    "run_sl_tp_grid",
    "best_grid_result",
]
