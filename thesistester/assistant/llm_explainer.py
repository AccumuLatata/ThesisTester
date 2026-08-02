"""Evidence-only LLM narration for completed research packets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from thesistester.assistant.explainer import EvidencePacket
from thesistester.assistant.llm import StructuredLLMClient

_EXPLANATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "caveats"],
    "properties": {
        "summary": {"type": "string"},
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
}


class LLMEvidenceError(ValueError):
    """Raised when a provider violates the evidence-only explanation contract."""


@dataclass(frozen=True)
class LLMExplanation:
    summary: str
    caveats: tuple[str, ...]


def explain_packet_with_llm(
    client: StructuredLLMClient, *, packet: EvidencePacket
) -> LLMExplanation:
    """Request narrative only; the immutable packet remains the sole fact source."""
    payload = client.complete_structured(
        system=(
            "Explain only the supplied evidence JSON. Do not add calculations, forecasts, "
            "trade advice, or facts absent from the packet. Preserve uncertainty and caveats."
        ),
        user=json.dumps(packet.to_dict(), sort_keys=True),
        schema=_EXPLANATION_SCHEMA,
    )
    if set(payload) != {"summary", "caveats"}:
        raise LLMEvidenceError("LLM explanation must contain only summary and caveats.")
    summary = payload["summary"]
    caveats = payload["caveats"]
    if not isinstance(summary, str) or not summary.strip() or not isinstance(caveats, list):
        raise LLMEvidenceError("LLM explanation has invalid field types.")
    if any(not isinstance(caveat, str) or not caveat.strip() for caveat in caveats):
        raise LLMEvidenceError("LLM caveats must be non-empty strings.")
    return LLMExplanation(
        summary=summary.strip(), caveats=tuple(caveat.strip() for caveat in caveats)
    )
