"""Single source of truth for static StudySpec / Assistant level token names.

Engine modules remain the source of *emitted column strings*. This module
lists the always-on session/profile/session-VWAP/single-print/APOC names.
Rolling VWAP/POC, MAs, ``prev30mVWAP*``, and ``Pivot_*`` are not static —
they are implied only by ``study.levels`` (see ``closed_level_token_set``).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .pivots import _PIVOT_COLUMN_LABELS
from .session_vwap import SESSION_VWAP_COLUMNS
from .tpo import SINGLE_PRINT_COLUMNS

# Exact ``ordered`` tuple from ``compute_session_levels`` (sessions.py).
SESSION_STRUCTURAL_LEVEL_NAMES: tuple[str, ...] = (
    "ONH",
    "ONL",
    "pONH",
    "pONL",
    "AsiaHigh",
    "AsiaLow",
    "LondonHigh",
    "LondonLow",
    "OR_High",
    "OR_Low",
    "RTH_Open",
    "pRTH_Open",
    "pRTH_High",
    "pRTH_Low",
    "prevSettlement",
    "dOpen",
    "wOpen",
    "mOpen",
    "pdOpen",
    "pwOpen",
    "pmOpen",
    "pdHigh",
    "pdLow",
    "pwHigh",
    "pwLow",
    "pmHigh",
    "pmLow",
    "pdEQ",
    "pwEQ",
    "pmEQ",
)

# Catalog names for prior-profile VA. Emitted only when a tick
# ``PriorProfileTable`` is present (TV3). Tokens stay in the closed set so a
# named-VA study fails as "VA requires ticks", not "unknown token".
PRIOR_PROFILE_LEVEL_NAMES: tuple[str, ...] = (
    "pdVAH",
    "pdVAL",
    "pdPOC",
    "pwVAH",
    "pwVAL",
    "pwPOC",
    "pmVAH",
    "pmVAL",
    "pmPOC",
)

SESSION_VWAP_LEVEL_NAMES: tuple[str, ...] = SESSION_VWAP_COLUMNS
SINGLE_PRINT_LEVEL_NAMES: tuple[str, ...] = SINGLE_PRINT_COLUMNS
APOC_LEVEL_NAMES: tuple[str, ...] = ("APOC", "pAPOC")

STATIC_STUDY_LEVEL_NAMES: frozenset[str] = frozenset(
    {
        *SESSION_STRUCTURAL_LEVEL_NAMES,
        *PRIOR_PROFILE_LEVEL_NAMES,
        *SESSION_VWAP_LEVEL_NAMES,
        *SINGLE_PRINT_LEVEL_NAMES,
        *APOC_LEVEL_NAMES,
    }
)


def named_prior_profile_tokens(names: Sequence[object]) -> list[str]:
    """Return named tokens that are prior-profile VA (``pd*`` / ``pw*`` / ``pm*``)."""
    wanted = set(PRIOR_PROFILE_LEVEL_NAMES)
    found: list[str] = []
    seen: set[str] = set()
    for raw in names:
        token = str(raw)
        if token in wanted and token not in seen:
            seen.add(token)
            found.append(token)
    return found


def pivot_column_names(timeframes: Iterable[str]) -> tuple[str, ...]:
    """Return engine pivot column names for *timeframes* settings keys.

    Uses ``pivots._PIVOT_COLUMN_LABELS`` (``1min`` → ``1m``). Does not re-spell
    labels. Empty strings are skipped. Unknown timeframe keys raise ``KeyError``.
    A bare string is rejected (it is iterable character-wise).
    """
    if isinstance(timeframes, (str, bytes)):
        raise TypeError("pivot_column_names() expected an iterable of timeframe keys, not a string")
    names: list[str] = []
    for raw in timeframes:
        key = str(raw).strip()
        if not key:
            continue
        label = _PIVOT_COLUMN_LABELS[key]
        names.append(f"Pivot_{label}_High")
        names.append(f"Pivot_{label}_Low")
    return tuple(names)
