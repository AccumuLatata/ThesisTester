"""Digit-token grounding helpers for spoken voice text (VA-3).

Reuses C2-6 / RQ number-token normalization from ``llm_explainer``. Does not
trust raw model speech; returns a schema-versioned ``GroundingVerdict``.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from thesistester.assistant.explainer import EvidenceClaim, EvidencePacket
from thesistester.assistant.llm_explainer import (
    _NUMBER_RE,
    _extract_number_tokens,
    _normalize_number_token,
    _token_grounded,
)
from thesistester.assistant.voice.contracts import GroundingVerdict


def normalize_number_token(token: str) -> str:
    """Public wrapper for the shared C2-6 / RQ numeric token normalizer."""
    return _normalize_number_token(token)


def extract_digit_tokens(text: str) -> tuple[str, ...]:
    """Return normalized digit tokens found in ``text`` (order preserved)."""
    if not isinstance(text, str) or not text:
        return ()
    return tuple(_extract_number_tokens(text))


def allowed_tokens_from_values(values: Iterable[Any]) -> set[str]:
    """Build an allowlist of normalized numeric tokens from claim/tool values."""
    allowed: set[str] = set()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            continue
        if isinstance(value, str):
            allowed.update(_extract_number_tokens(value))
            continue
        allowed.add(_normalize_number_token(str(value)))
    return allowed


def allowed_tokens_from_packet(packet: EvidencePacket) -> set[str]:
    """Allowlist numbers from packet claims, caveat messages, and typed claim values."""
    allowed = allowed_tokens_from_values(claim.value for claim in packet.claims)
    for claim in packet.claims:
        if isinstance(claim.text, str):
            allowed.update(_extract_number_tokens(claim.text))
    for caveat in packet.caveats:
        if isinstance(caveat.message, str):
            allowed.update(_extract_number_tokens(caveat.message))
    return allowed


def allowed_tokens_from_tool_result(result: Mapping[str, Any] | None) -> set[str]:
    """Collect digit tokens from a JSON-safe voice tool result payload."""
    if not isinstance(result, Mapping):
        return set()
    allowed: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            allowed.add(_normalize_number_token(str(value)))
            return
        if isinstance(value, str):
            allowed.update(_extract_number_tokens(value))
            return
        if isinstance(value, Mapping):
            for item in value.values():
                walk(item)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(result)
    return allowed


def audit_spoken_text(
    text: str,
    *,
    allowed_values: Sequence[Any] | None = None,
    allowed_tokens: Iterable[str] | None = None,
    packet: EvidencePacket | None = None,
    tool_result: Mapping[str, Any] | None = None,
    claims: Sequence[EvidenceClaim] | None = None,
) -> GroundingVerdict:
    """Audit digit tokens in spoken/trusted text against an allowlist.

    Spoken-word number phrases (“twelve”) are out of v1 scope — only digit
    tokens are checked, matching RQ / C2-6.
    """
    audited = text if isinstance(text, str) else ""
    allowed: set[str] = set()
    if allowed_tokens is not None:
        for token in allowed_tokens:
            if isinstance(token, str) and token.strip():
                allowed.add(_normalize_number_token(token))
    if allowed_values is not None:
        allowed |= allowed_tokens_from_values(allowed_values)
    if claims is not None:
        allowed |= allowed_tokens_from_values(claim.value for claim in claims)
        for claim in claims:
            if isinstance(claim.text, str):
                allowed.update(_extract_number_tokens(claim.text))
    if packet is not None:
        allowed |= allowed_tokens_from_packet(packet)
    if tool_result is not None:
        allowed |= allowed_tokens_from_tool_result(tool_result)

    uncited: list[str] = []
    seen: set[str] = set()
    for match in _NUMBER_RE.finditer(audited):
        raw = match.group(0)
        if _token_grounded(raw, allowed=allowed):
            continue
        normalized = _normalize_number_token(raw)
        if normalized in seen:
            continue
        seen.add(normalized)
        uncited.append(normalized)

    if uncited:
        return GroundingVerdict(
            grounded=False,
            audited_text=audited,
            allowed_digit_tokens=tuple(sorted(allowed)),
            uncited_digit_tokens=tuple(uncited),
            remediation=(
                "Spoken text contains digit tokens that are not grounded in the "
                "bound evidence packet, cited claims, or allowlisted tool returns."
            ),
        )
    return GroundingVerdict(
        grounded=True,
        audited_text=audited,
        allowed_digit_tokens=tuple(sorted(allowed)),
        uncited_digit_tokens=(),
        remediation=None,
    )
