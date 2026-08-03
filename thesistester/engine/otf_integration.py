"""OTF research-mode integration helper (PR 5).

This module provides a single shared, deterministic integration path that
resolves an effective OTF configuration from available session context and
applies the pure ``apply_otf_filter()`` engine once to candidate signals.

Usage
-----
Call :func:`apply_configured_otf_filter` from backtest, grid-search, and
walk-forward execution paths.  The returned :class:`OtfFilterResult` exposes
all required audit fields.

Config resolution precedence
-----------------------------
1. ``signal_settings["otf_filter"]`` if the key is explicitly present.
2. ``signal_settings["setup_snapshot"]`` effective OTF config, if present.
3. ``last_signal_setup`` effective OTF config, if provided and exists.
4. ``setup_config`` effective OTF config, if provided and exists.
5. Canonical disabled defaults.

An explicit but invalid OTF config (e.g. enabled=True with no timeframes)
always raises ``ValueError`` — it is never silently treated as disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .otf import OTF_ALGORITHM_VERSION
from .otf_filter import apply_otf_filter
from ..setup import (
    get_effective_otf_filter_config,
    normalize_otf_filter_config,
    _default_otf_filter_config,
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OtfFilterResult:
    """Frozen result returned by :func:`apply_configured_otf_filter`.

    Attribute reassignment is prevented (``frozen=True``).  Note that
    DataFrame attributes remain internally mutable objects; only the
    reference slots on this dataclass are frozen.

    Attributes
    ----------
    candidate_signals:
        Original candidate signals, unmodified (deep copy of input).
    accepted_signals:
        Signals that passed the OTF filter (all candidates when disabled).
    rejected_signals:
        Signals that failed the OTF filter (empty DataFrame when disabled).
    otf_filter_config:
        The resolved canonical OTF filter config that was applied.
    otf_filter_enabled:
        Whether OTF filtering was active.
    otf_algorithm_version:
        Version identifier for the OTF state machine (``OTF_ALGORITHM_VERSION``).
    otf_config_hash:
        Deterministic SHA-256 hash of the resolved OTF config.
    candidate_signal_count:
        Row count of ``candidate_signals``.
    otf_accepted_signal_count:
        Row count of ``accepted_signals``.
    otf_rejected_signal_count:
        Row count of ``rejected_signals``.
    session_timezone:
        Effective session timezone forwarded to the OTF engine (may be
        ``None`` when not supplied by the caller).
    eth_start:
        Effective ETH session-start string forwarded to the OTF engine
        (may be ``None`` when not supplied; ``None`` means calendar-date
        session boundaries in the pure engine).
    """

    candidate_signals: pd.DataFrame
    accepted_signals: pd.DataFrame
    rejected_signals: pd.DataFrame
    otf_filter_config: dict[str, Any]
    otf_filter_enabled: bool
    otf_algorithm_version: int
    otf_config_hash: str
    candidate_signal_count: int
    otf_accepted_signal_count: int
    otf_rejected_signal_count: int
    session_timezone: str | None = None
    eth_start: str | None = None

    @property
    def rejection_rate(self) -> float | None:
        """Fraction of candidates rejected; ``None`` when no candidates."""
        if self.candidate_signal_count == 0:
            return None
        return self.otf_rejected_signal_count / self.candidate_signal_count

    def to_summary_dict(self) -> dict[str, Any]:
        """Return a JSON-safe summary dict suitable for session state storage."""
        return {
            "otf_filter_enabled": self.otf_filter_enabled,
            "otf_algorithm_version": self.otf_algorithm_version,
            "otf_config_hash": self.otf_config_hash,
            "otf_filter_config": self.otf_filter_config,
            "candidate_signal_count": self.candidate_signal_count,
            "otf_accepted_signal_count": self.otf_accepted_signal_count,
            "otf_rejected_signal_count": self.otf_rejected_signal_count,
            "rejection_rate": self.rejection_rate,
            "session_timezone": self.session_timezone,
            "eth_start": self.eth_start,
        }


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def resolve_otf_config(
    *,
    signal_settings: dict[str, Any] | None = None,
    last_signal_setup: dict[str, Any] | None = None,
    setup_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve effective OTF filter config with documented precedence.

    Precedence (highest wins):

    1. ``signal_settings["otf_filter"]`` — if the key is explicitly present
       (not absent) in *signal_settings*, normalize and use it.  Raises
       ``ValueError`` if the explicit value is invalid.
    2. ``signal_settings["setup_snapshot"]`` effective OTF config — if
       *signal_settings* contains a ``"setup_snapshot"`` dict.
    3. ``last_signal_setup`` effective OTF config — if provided as a non-empty
       dict.
    4. ``setup_config`` effective OTF config — if provided as a non-empty dict.
    5. Canonical disabled defaults.

    Parameters
    ----------
    signal_settings:
        Loaded signal-run metadata from session state
        (``st.session_state["signal_settings"]``).
    last_signal_setup:
        The setup config associated with the last signal generation run
        (``st.session_state["last_signal_setup"]``).
    setup_config:
        The currently active setup config
        (``st.session_state["setup_config"]``).

    Returns
    -------
    dict
        Canonical normalized OTF filter config dict.

    Raises
    ------
    ValueError
        If an explicit (non-absent) OTF config is present but invalid.
    """
    # 1. signal_settings["otf_filter"] — key must be present (not just truthy)
    if isinstance(signal_settings, dict) and "otf_filter" in signal_settings:
        raw = signal_settings["otf_filter"]
        # normalize_otf_filter_config handles None → disabled defaults,
        # and raises on explicit invalid dicts.
        return normalize_otf_filter_config(raw)

    # 2. signal_settings["setup_snapshot"] effective OTF config
    if isinstance(signal_settings, dict):
        snapshot = signal_settings.get("setup_snapshot")
        if isinstance(snapshot, dict):
            # get_effective_otf_filter_config raises on explicitly invalid raw
            return get_effective_otf_filter_config(snapshot)

    # 3. last_signal_setup effective OTF config
    if isinstance(last_signal_setup, dict) and last_signal_setup:
        return get_effective_otf_filter_config(last_signal_setup)

    # 4. setup_config effective OTF config
    if isinstance(setup_config, dict) and setup_config:
        return get_effective_otf_filter_config(setup_config)

    # 5. Canonical disabled defaults
    return _default_otf_filter_config()


# ---------------------------------------------------------------------------
# Main integration function
# ---------------------------------------------------------------------------


def apply_configured_otf_filter(
    *,
    source_df: pd.DataFrame,
    candidate_signals: pd.DataFrame,
    setup_config: dict[str, Any] | None = None,
    session_timezone: str | None = None,
    eth_start: str | None = None,
    signal_settings: dict[str, Any] | None = None,
    last_signal_setup: dict[str, Any] | None = None,
) -> OtfFilterResult:
    """Resolve OTF config and apply the pure filter once to candidate signals.

    This is the single shared integration point for backtest, grid-search,
    and walk-forward execution paths.  It:

    1. Resolves effective OTF config via :func:`resolve_otf_config`.
    2. Applies :func:`apply_otf_filter` (the pure eligibility engine).
    3. Returns an :class:`OtfFilterResult` with all audit fields populated.

    Parameters
    ----------
    source_df:
        Canonical OHLCV DataFrame used for OTF state calculation.  For
        walk-forward, this must be the fold-local source slice to prevent
        future-data leakage.
    candidate_signals:
        Candidate signals to filter.  Not mutated.
    setup_config:
        Active setup config for config resolution (precedence level 4).
    session_timezone:
        Exchange/session timezone label (e.g. ``"America/New_York"``).
        Passed to the OTF engine for timestamp alignment.
    eth_start:
        ETH session start time string (e.g. ``"18:00"``).  Passed to the
        OTF engine for session-reset alignment.  ``None`` uses engine
        defaults.
    signal_settings:
        Loaded signal-run metadata for config resolution (levels 1–2).
    last_signal_setup:
        Setup config from last signal generation (precedence level 3).

    Returns
    -------
    OtfFilterResult
        Immutable result with accepted/rejected signals and audit metadata.

    Raises
    ------
    ValueError
        If an explicit (non-absent) OTF config present in any resolution
        source is invalid.
    """
    # Resolve config — may raise on explicit invalid config
    otf_config = resolve_otf_config(
        signal_settings=signal_settings,
        last_signal_setup=last_signal_setup,
        setup_config=setup_config,
    )

    # Compute config hash for audit
    otf_config_hash = _compute_hash(otf_config)

    enabled = bool(otf_config.get("enabled", False))

    # Preserve candidate signals unchanged (deep copy for immutability)
    candidates_copy = candidate_signals.copy(deep=True)
    candidate_count = int(len(candidates_copy))

    if enabled:
        # Apply the pure OTF filter
        accepted, rejected = apply_otf_filter(
            source_df,
            candidate_signals,
            enabled=True,
            timeframes=list(otf_config.get("timeframes", [])),
            alignment_mode=str(otf_config.get("alignment_mode", "all")),
            minimum_consecutive_bars=int(otf_config.get("minimum_consecutive_bars", 3)),
            session_timezone=session_timezone,
            eth_start=eth_start,
            session_reset=str(otf_config.get("session_reset", "session")),
        )
    else:
        # Disabled: pass-through — identical to calling apply_otf_filter(enabled=False)
        accepted, rejected = apply_otf_filter(
            source_df,
            candidate_signals,
            enabled=False,
        )

    accepted_count = int(len(accepted))
    rejected_count = int(len(rejected))

    return OtfFilterResult(
        candidate_signals=candidates_copy,
        accepted_signals=accepted,
        rejected_signals=rejected,
        otf_filter_config=otf_config,
        otf_filter_enabled=enabled,
        otf_algorithm_version=OTF_ALGORITHM_VERSION,
        otf_config_hash=otf_config_hash,
        candidate_signal_count=candidate_count,
        otf_accepted_signal_count=accepted_count,
        otf_rejected_signal_count=rejected_count,
        session_timezone=session_timezone,
        eth_start=eth_start,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _compute_hash(otf_config: dict[str, Any]) -> str:
    """Return deterministic SHA-256 hash for an OTF config dict."""
    # Import here to avoid circular imports at module load time
    from ..persistence.local_store import compute_otf_config_hash

    return compute_otf_config_hash(otf_config)
