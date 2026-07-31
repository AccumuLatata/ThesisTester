"""Phase 4–5 engine: confluence detection, naked levels, signal generation, backtest."""

from __future__ import annotations

from .backtest import SimulationResult, simulate_trades
from .anchor_confluence import detect_anchor_confluence_zones
from .candidate_level import CandidateLevel, from_anchor_zones, from_global_cluster_zones
from .confluence import detect_confluence_zones
from .naked import flag_naked_levels
from .otf import normalize_otf_timeframe
from .otf_filter import apply_otf_filter
from .otf_integration import OtfFilterResult, apply_configured_otf_filter, resolve_otf_config
from .signals import generate_signals
from .intrabar import VALID_INTRABAR_MODELS

__all__ = [
    "detect_anchor_confluence_zones",
    "CandidateLevel",
    "detect_confluence_zones",
    "flag_naked_levels",
    "from_anchor_zones",
    "from_global_cluster_zones",
    "generate_signals",
    "apply_otf_filter",
    "apply_configured_otf_filter",
    "normalize_otf_timeframe",
    "OtfFilterResult",
    "resolve_otf_config",
    "simulate_trades",
    "SimulationResult",
    "VALID_INTRABAR_MODELS",
]
