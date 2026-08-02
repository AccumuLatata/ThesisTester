"""Evidence-only LLM narration for completed research packets.

Provider output is untrusted. Structured claims must cite evidence paths; any
numeric token that is not grounded in a cited packet value is rejected before
rendering.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from thesistester.assistant.explainer import EvidenceClaim, EvidencePacket
from thesistester.assistant.llm import StructuredLLMClient

_EXPLANATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "caveats", "claims"],
    "properties": {
        "summary": {"type": "string"},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "path"],
                "properties": {
                    "text": {"type": "string"},
                    "path": {"type": "string"},
                },
            },
        },
    },
}

# Capture standalone numeric tokens, including optional percent suffixes.
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_/])[-+]?(?:\d+\.\d+|\.\d+|\d+)(?:[eE][-+]?\d+)?%?")


class LLMEvidenceError(ValueError):
    """Raised when a provider violates the evidence-only explanation contract."""


@dataclass(frozen=True)
class LLMExplanation:
    """Grounded LLM paraphrase; claims carry server-resolved packet values."""

    summary: str
    caveats: tuple[str, ...]
    claims: tuple[EvidenceClaim, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "caveats": list(self.caveats),
            "claims": [claim.to_dict() for claim in self.claims],
        }


def _path_get(root: Mapping[str, Any], path: str) -> Any:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _path_exists(root: Mapping[str, Any], path: str) -> bool:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _normalize_number_token(token: str) -> str:
    text = token.strip().rstrip("%")
    try:
        value = float(text)
    except ValueError:
        return text
    if value.is_integer():
        return str(int(value))
    return format(value, ".12g")


def _allowed_number_tokens(values: list[Any]) -> set[str]:
    """Build normalized numeric tokens accepted for cited packet values."""
    allowed: set[str] = set()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        allowed.add(_normalize_number_token(str(value)))
    return allowed


def _extract_number_tokens(text: str) -> list[str]:
    return [_normalize_number_token(match.group(0)) for match in _NUMBER_RE.finditer(text)]


def _token_grounded(raw_token: str, *, allowed: set[str]) -> bool:
    """Return True when ``raw_token`` is grounded in cited values.

    Percent-suffixed narration (``50%``) is accepted when the matching fractional
    claim value (``0.5``) is allowlisted. Bare ``50`` is not inferred from ``0.5``.
    """
    token = _normalize_number_token(raw_token)
    if token in allowed:
        return True
    if not raw_token.rstrip().endswith("%"):
        return False
    try:
        percent_value = float(raw_token.strip().rstrip("%"))
    except ValueError:
        return False
    return _normalize_number_token(str(percent_value / 100.0)) in allowed


def _assert_tokens_grounded(text: str, *, allowed: set[str]) -> None:
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(0)
        if not _token_grounded(raw, allowed=allowed):
            raise LLMEvidenceError(
                f"Uncited numerical claim {_normalize_number_token(raw)!r} "
                "is not grounded in cited evidence."
            )


def assert_llm_explanation_grounded(
    packet: EvidencePacket,
    *,
    summary: str,
    caveats: tuple[str, ...],
    claims: tuple[EvidenceClaim, ...],
) -> None:
    """Reject uncited numerical claims before any UI rendering."""
    allowed_from_claims = _allowed_number_tokens([claim.value for claim in claims])
    # Summary and claim text may only use numbers from cited claim values.
    _assert_tokens_grounded(summary, allowed=allowed_from_claims)
    for claim in claims:
        _assert_tokens_grounded(claim.text, allowed=allowed_from_claims)
    # Packet caveat numbers are allowlisted only for LLM caveat lines that
    # actually echo that packet caveat message — never for the whole narrative.
    packet_caveat_messages = tuple(
        caveat.message for caveat in packet.caveats if isinstance(caveat.message, str)
    )
    for llm_caveat in caveats:
        allowed = set(allowed_from_claims)
        for message in packet_caveat_messages:
            if message and (message in llm_caveat or llm_caveat in message):
                allowed |= set(_extract_number_tokens(message))
        _assert_tokens_grounded(llm_caveat, allowed=allowed)


def explain_packet_with_llm(
    client: StructuredLLMClient, *, packet: EvidencePacket
) -> LLMExplanation:
    """Request narrative only; the immutable packet remains the sole fact source."""
    packet_dict = packet.to_dict()
    payload = client.complete_structured(
        system=(
            "Explain only the supplied evidence JSON using structured claims. "
            "Each claim.text that includes a number must cite claim.path to an existing "
            "packet field. Do not add calculations, forecasts, trade advice, tools, or "
            "facts absent from the packet. Preserve uncertainty and caveats."
        ),
        user=json.dumps(packet_dict, sort_keys=True),
        schema=_EXPLANATION_SCHEMA,
    )
    if set(payload) != {"summary", "caveats", "claims"}:
        raise LLMEvidenceError("LLM explanation must contain only summary, caveats, and claims.")
    summary = payload["summary"]
    caveats = payload["caveats"]
    claims_raw = payload["claims"]
    if (
        not isinstance(summary, str)
        or not summary.strip()
        or not isinstance(caveats, list)
        or not isinstance(claims_raw, list)
    ):
        raise LLMEvidenceError("LLM explanation has invalid field types.")
    if any(not isinstance(caveat, str) or not caveat.strip() for caveat in caveats):
        raise LLMEvidenceError("LLM caveats must be non-empty strings.")
    claims: list[EvidenceClaim] = []
    for item in claims_raw:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"text", "path"}
            or not isinstance(item.get("text"), str)
            or not item["text"].strip()
            or not isinstance(item.get("path"), str)
            or not item["path"].strip()
        ):
            raise LLMEvidenceError("LLM claims must be non-empty text/path objects.")
        path = item["path"].strip()
        if not _path_exists(packet_dict, path):
            raise LLMEvidenceError(f"LLM claim path {path!r} is missing from the evidence packet.")
        claims.append(
            EvidenceClaim(
                text=item["text"].strip(),
                path=path,
                value=_path_get(packet_dict, path),
            )
        )
    grounded = tuple(claims)
    summary_text = summary.strip()
    caveat_texts = tuple(caveat.strip() for caveat in caveats)
    assert_llm_explanation_grounded(
        packet, summary=summary_text, caveats=caveat_texts, claims=grounded
    )
    return LLMExplanation(summary=summary_text, caveats=caveat_texts, claims=grounded)
