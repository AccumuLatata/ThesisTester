"""Classic Backtest persist/display helpers (QR A-2 / QI-04-06).

Kept out of ``pages/7_Backtest.py`` so tests can persist a ``return_result``
diagnostic without importing the Streamlit page. D-3 may grow this module.
The session key is additive and unhashed (AH §2 item 8). AH4: clear-only when
it joins ``_MANAGED_RESEARCH_KEYS`` (A-7); sticky on bundle apply until then.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

DIRECTION_COLLISION_SESSION_KEY = "direction_collision_diagnostic"


def _as_diagnostic_mapping(source: Any) -> Mapping[str, Any]:
    """Prefer ``.direction_collision_diagnostic`` / nested key over ``source``."""
    attr = getattr(source, "direction_collision_diagnostic", None)
    if isinstance(attr, Mapping):
        return attr
    if isinstance(source, Mapping):
        nested = source.get(DIRECTION_COLLISION_SESSION_KEY)
        if isinstance(nested, Mapping):
            return nested
        if "candidate_pairs" in source:
            return source
    return {}


def persist_direction_collision_diagnostic(
    session_state: MutableMapping[str, Any],
    source: Any,
) -> dict[str, Any]:
    """Store DA1 ``direction_collision_diagnostic`` after a ``return_result`` run."""
    diagnostic = dict(_as_diagnostic_mapping(source))
    session_state[DIRECTION_COLLISION_SESSION_KEY] = diagnostic
    return diagnostic


def format_direction_collision_caption(diagnostic: Mapping[str, Any] | None) -> str:
    """Skip-table caption for the stored DA1 pair counts. Not a P&L claim."""
    if not isinstance(diagnostic, Mapping) or "candidate_pairs" not in diagnostic:
        return "DA1 same-bar opposite-direction diagnostic was not stored for this run."
    pairs = diagnostic.get("candidate_pairs", 0)
    policy = diagnostic.get("policy", "legacy")
    share = diagnostic.get("accepted_trade_share_from_pairs", 0.0)
    return (
        f"DA1 same-bar opposite pairs: {pairs} candidate pair(s) · "
        f"resolved long/short/none: "
        f"{diagnostic.get('resolved_long', 0)}/"
        f"{diagnostic.get('resolved_short', 0)}/"
        f"{diagnostic.get('resolved_none', 0)} · "
        f"accepted-trade share from pairs: {share} · "
        f"policy `{policy}`. "
        "Same-bar opposite-direction counts only — not an admission gate "
        "and not proof of fill quality. "
        "Visible under `allow_all` even when the skip table is empty. "
        "Diagnostic only — not a hashed bundle member."
    )
