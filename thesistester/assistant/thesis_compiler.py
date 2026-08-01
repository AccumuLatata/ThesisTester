"""Deterministic thesis drafting and ambiguity detection.

This module intentionally does not execute experiments or call a language model.
It turns explicit structured choices plus user prose into a reviewable draft.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

COMPILER_VERSION = "1"


@dataclass(frozen=True)
class ThesisDraft:
    """A non-executable research-plan draft awaiting user confirmation."""

    prompt: str
    normalized_run_spec: dict[str, Any]
    unresolved_assumptions: tuple[str, ...]

    @property
    def ready_for_confirmation(self) -> bool:
        return not self.unresolved_assumptions


def compile_thesis(prompt: str, *, choices: Mapping[str, Any] | None = None) -> ThesisDraft:
    """Create a deterministic draft and name missing executable definitions."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Thesis prompt must be a non-empty string.")
    selected = dict(choices or {})
    text = prompt.lower()
    unresolved: list[str] = []
    required = {
        "trend_rule": "Define the measurable trend rule.",
        "trigger": "Define the entry trigger and tick tolerance.",
        "session_window": "Define the exact exchange-time session window.",
        "success_criteria": "Define performance, sample-size, and OOS success criteria.",
    }
    for key, question in required.items():
        if not selected.get(key):
            unresolved.append(question)
    if "dvw" in text and not selected.get("session_vwap_anchor"):
        unresolved.append("Confirm dVWAP_RTH and its RTH-only availability.")
    if ("sma" in text or "moving average" in text) and not selected.get(
        "confluence_tolerance_ticks"
    ):
        unresolved.append("Define the SMA confluence tolerance in ticks.")
    if ("stop" in text or "target" in text or "sl" in text) and not selected.get(
        "selection_protocol"
    ):
        unresolved.append("Define SL/TP candidate grid and OOS selection protocol.")
    return ThesisDraft(
        prompt=prompt.strip(),
        normalized_run_spec=selected,
        unresolved_assumptions=tuple(unresolved),
    )
