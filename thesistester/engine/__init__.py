"""Phase 4–5 engine: confluence detection, naked levels, signal generation, backtest."""
from __future__ import annotations

from .backtest import simulate_trades
from .anchor_confluence import detect_anchor_confluence_zones
from .candidate_level import CandidateLevel, from_anchor_zones, from_global_cluster_zones
from .confluence import detect_confluence_zones
from .naked import flag_naked_levels
from .signals import generate_signals

__all__ = [
    "detect_anchor_confluence_zones",
    "CandidateLevel",
    "detect_confluence_zones",
    "flag_naked_levels",
    "from_anchor_zones",
    "from_global_cluster_zones",
    "generate_signals",
    "simulate_trades",
]
