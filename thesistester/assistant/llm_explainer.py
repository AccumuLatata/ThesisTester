"""Evidence-only LLM narration for completed research packets.

Provider output is untrusted. Structured claims must cite evidence paths; any
numeric token that is not grounded in a cited packet value is rejected before
rendering. Percent-suffixed narration maps to fractional claim values; packet
caveat numbers are scoped to echoing caveat lines only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

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


def _llm_caveat_echoes_packet_message(llm_caveat: str, packet_message: str) -> bool:
    """True when an LLM caveat line echoes (or is echoed by) a packet caveat."""
    if not packet_message or not llm_caveat:
        return False
    return packet_message in llm_caveat or llm_caveat in packet_message


def merge_mandatory_packet_caveats(
    packet: EvidencePacket,
    caveats: Sequence[str],
) -> tuple[str, ...]:
    """Append any missing packet caveat messages so honesty framing cannot drop them.

    RQ contract §3.7: sample-size / costs / intrabar / OOS / selection caveats
    from the packet remain mandatory. Callers must run this before persist/render.
    """
    merged = [item.strip() for item in caveats if isinstance(item, str) and item.strip()]
    for caveat in packet.caveats:
        message = caveat.message.strip() if isinstance(caveat.message, str) else ""
        if not message:
            continue
        if not any(_llm_caveat_echoes_packet_message(item, message) for item in merged):
            merged.append(message)
    return tuple(merged)


# Soften language that contradicts missing/failed OOS packet caveats.
_OOS_SOFTEN_RE = re.compile(
    r"\b("
    r"(?:oos|out[\s-]*of[\s-]*sample|walk[\s-]*forward|wfa)\b[\s\S]{0,40}\b"
    r"(?:confirm(?:ed|s)?|robust|proven|validated|successful)"
    r"|"
    r"(?:confirm(?:ed|s)?|robust|proven|validated|successful)\b[\s\S]{0,40}\b"
    r"(?:oos|out[\s-]*of[\s-]*sample|walk[\s-]*forward|wfa)"
    r")\b",
    re.IGNORECASE,
)
_OOS_SOFTEN_NEGATION_RE = re.compile(
    r"\b(?:not|no|never|without|lacks?|missing|absent|unconfirmed|cannot|can't|"
    r"isn't|aren't|wasn't|weren't|unless)\b",
    re.IGNORECASE,
)


def _has_oos_soften_language(text: str) -> bool:
    """True when text asserts OOS/WFA confirmation without nearby negation."""
    for match in _OOS_SOFTEN_RE.finditer(text):
        start = max(0, match.start() - 28)
        end = min(len(text), match.end() + 12)
        if _OOS_SOFTEN_NEGATION_RE.search(text[start:end]):
            continue
        return True
    return False


def assert_llm_explanation_grounded(
    packet: EvidencePacket,
    *,
    summary: str,
    caveats: tuple[str, ...],
    claims: tuple[EvidenceClaim, ...],
    followups: tuple[str, ...] = (),
) -> None:
    """Reject uncited numerical claims and OOS-soften contradictions.

    ``followups`` (RQ-1 results Q&A) use the same cited-claim allowlist as
    ``summary`` / claim text. Prefer number-free followups.

    Callers must pass caveats through ``merge_mandatory_packet_caveats`` first so
    packet honesty caveats cannot be omitted. When the packet carries
    ``missing_oos`` / ``failed_oos``, summary/claim/followup text must not claim
    OOS/WFA confirmation.
    """
    allowed_from_claims = _allowed_number_tokens([claim.value for claim in claims])
    # Summary and claim text may only use numbers from cited claim values.
    _assert_tokens_grounded(summary, allowed=allowed_from_claims)
    for claim in claims:
        _assert_tokens_grounded(claim.text, allowed=allowed_from_claims)
    for followup in followups:
        _assert_tokens_grounded(followup, allowed=allowed_from_claims)
    # Packet caveat numbers are allowlisted only for LLM caveat lines that
    # actually echo that packet caveat message — never for the whole narrative.
    packet_caveat_messages = tuple(
        caveat.message.strip()
        for caveat in packet.caveats
        if isinstance(caveat.message, str) and caveat.message.strip()
    )
    for llm_caveat in caveats:
        allowed = set(allowed_from_claims)
        for message in packet_caveat_messages:
            if _llm_caveat_echoes_packet_message(llm_caveat, message):
                allowed |= set(_extract_number_tokens(message))
        _assert_tokens_grounded(llm_caveat, allowed=allowed)

    oos_codes = {
        caveat.code
        for caveat in packet.caveats
        if isinstance(caveat.code, str) and caveat.code in {"missing_oos", "failed_oos"}
    }
    if oos_codes:
        fields: list[tuple[str, str]] = [
            ("summary", summary),
            *((f"claim[{index}]", claim.text) for index, claim in enumerate(claims)),
            *((f"followup[{index}]", item) for index, item in enumerate(followups)),
        ]
        # Scan LLM caveat lines too. Skip only *exact* packet-echo lines so
        # honesty text is not false-positive, while "echo + OOS is confirmed"
        # mashups remain gated.
        for index, llm_caveat in enumerate(caveats):
            if any(llm_caveat.strip() == message for message in packet_caveat_messages):
                continue
            fields.append((f"caveat[{index}]", llm_caveat))
        for field_name, text in fields:
            if _has_oos_soften_language(text):
                raise LLMEvidenceError(
                    f"OOS/WFA soften language in {field_name} contradicts packet "
                    f"caveat code(s) {sorted(oos_codes)}."
                )


def explain_packet_with_llm(
    client: StructuredLLMClient, *, packet: EvidencePacket
) -> LLMExplanation:
    """Request narrative only; the immutable packet remains the sole fact source."""
    packet_dict = packet.to_dict()
    payload = client.complete_structured(
        system=(
            "Explain only the supplied evidence JSON using structured claims. "
            "Each claim.text that includes a number must cite claim.path to an existing "
            "packet field. claim.path must be an exact dotted key path already present "
            "in the supplied JSON; do not invent nested keys. Do not add calculations, "
            "forecasts, trade advice, tools, or facts absent from the packet. "
            "Preserve uncertainty and caveats."
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
    caveat_texts = merge_mandatory_packet_caveats(
        packet, tuple(caveat.strip() for caveat in caveats)
    )
    assert_llm_explanation_grounded(
        packet, summary=summary_text, caveats=caveat_texts, claims=grounded
    )
    return LLMExplanation(summary=summary_text, caveats=caveat_texts, claims=grounded)
