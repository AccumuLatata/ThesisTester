"""Deterministic VA-4 fallback intent router (results channel only).

Maps STT text to exactly one VA-3 tool. Not the primary answer path — primary
is STT → handle_results_turn / handle_help_turn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_RUN_ID_RE = re.compile(r"\brun_[0-9a-f]{32}\b", re.IGNORECASE)

# Ordered metric aliases → packet paths (first match wins).
_METRIC_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("win rate", "winrate", "win_rate"), "results.trade_summary.win_rate"),
    (("expectancy", "expectancy_r"), "results.trade_summary.expectancy_r"),
    (("profit factor", "profit_factor"), "results.trade_summary.profit_factor"),
    (("drawdown", "max drawdown", "max_drawdown"), "results.trade_summary.max_drawdown_r"),
    (("trade count", "trades", "sample size"), "results.trade_summary.trade_count"),
    (("total r", "total_r"), "results.trade_summary.total_r"),
    (("signal count", "signals"), "results.signal_count"),
)

_CAVEAT_HINTS = (
    "caveat",
    "caveats",
    "warning",
    "warnings",
    "limitation",
    "limitations",
    "honesty",
)
_OVERVIEW_HINTS = (
    "overview",
    "summarize",
    "summary",
    "summarise",
    "recap",
    "what happened",
    "tell me about",
)
_COMPARE_HINTS = ("compare", "versus", "vs ", " vs.", "difference between")

_UNRECOGNIZED_NOTE = (
    "I could not match a specific metric intent, so here is the run overview. "
    "For freer questions, use text Discuss results or realtime voice mode."
)


@dataclass(frozen=True)
class VoiceIntent:
    """One VA-3 tool invocation chosen by the deterministic fallback router."""

    tool_name: str
    arguments: dict[str, Any]
    recognized: bool = True
    spoken_note: str | None = None


class VoiceIntentRouter:
    """Map spoken text to exactly one allowlisted voice tool."""

    def route(self, text: str) -> VoiceIntent:
        raw = text if isinstance(text, str) else ""
        normalized = " ".join(raw.strip().lower().split())
        if not normalized:
            return VoiceIntent(
                tool_name="get_run_overview",
                arguments={},
                recognized=False,
                spoken_note=_UNRECOGNIZED_NOTE,
            )

        if any(hint in normalized for hint in _COMPARE_HINTS):
            match = _RUN_ID_RE.search(raw)
            if match:
                return VoiceIntent(
                    tool_name="compare_two_runs",
                    arguments={"other_run_id": match.group(0).lower()},
                    recognized=True,
                )

        if any(hint in normalized for hint in _CAVEAT_HINTS):
            return VoiceIntent(tool_name="list_caveats", arguments={}, recognized=True)

        for aliases, path in _METRIC_ALIASES:
            if any(alias in normalized for alias in aliases):
                return VoiceIntent(
                    tool_name="get_metric",
                    arguments={"path": path},
                    recognized=True,
                )

        # Explicit results.* path spoken as text (rare but useful in tests).
        path_match = re.search(
            r"\b((?:results|assumptions|provenance)\.[a-z0-9_.]+)\b",
            normalized,
        )
        if path_match:
            return VoiceIntent(
                tool_name="get_metric",
                arguments={"path": path_match.group(1)},
                recognized=True,
            )

        if any(hint in normalized for hint in _OVERVIEW_HINTS):
            return VoiceIntent(tool_name="get_run_overview", arguments={}, recognized=True)

        return VoiceIntent(
            tool_name="get_run_overview",
            arguments={},
            recognized=False,
            spoken_note=_UNRECOGNIZED_NOTE,
        )
