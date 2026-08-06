"""Evidence-only LLM narration for completed research packets.

Provider output is untrusted. Structured claims must cite evidence paths; any
numeric token that is not grounded in a cited packet value is rejected before
rendering. Percent-suffixed narration maps to fractional claim values; packet
caveat numbers are scoped to echoing caveat lines only. Cited string values
contribute digits only for pure numeric tokens. Cited ``HH:MM`` / ``H:MM``
clock bucket labels ground matching clock spans in narration as wholes (so
``\"08:30\"`` can be narrated) without allowlisting their component digits;
hashes/paths/column names do not launder digits.
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
# Safe string claim values that may contribute digit tokens (not hashes/paths).
_CLOCK_BUCKET_RE = re.compile(r"^\d{1,2}:\d{2}$")
# Clock spans inside free text (same shape as bucket labels).
_CLOCK_IN_TEXT_RE = re.compile(r"(?<![A-Za-z0-9_/])(\d{1,2}:\d{2})(?![A-Za-z0-9_/])")
_NUMERIC_STRING_RE = re.compile(r"^[-+]?(?:\d+\.\d+|\.\d+|\d+)(?:[eE][-+]?\d+)?%?$")


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


def _extract_number_tokens(text: str) -> list[str]:
    return [_normalize_number_token(match.group(0)) for match in _NUMBER_RE.finditer(text)]


def _clock_label_variants(label: str) -> set[str]:
    """Return equivalent ``H:MM`` / ``HH:MM`` spellings for one clock label."""
    text = label.strip()
    if not _CLOCK_BUCKET_RE.fullmatch(text):
        return set()
    hour_text, minute = text.split(":", 1)
    try:
        hour = int(hour_text)
    except ValueError:
        return {text}
    return {text, f"{hour}:{minute}", f"{hour:02d}:{minute}"}


def _cited_clock_labels(values: list[Any]) -> set[str]:
    """Collect normalized clock-label variants from cited claim values."""
    clocks: set[str] = set()
    for value in values:
        if isinstance(value, str):
            clocks |= _clock_label_variants(value)
    return clocks


def _mask_cited_clock_spans(text: str, cited_clocks: set[str]) -> str:
    """Blank out narrated clock spans that match cited bucket labels.

    Component digits inside a grounded ``HH:MM`` span must not be re-checked as
    free numeric tokens (that would launder ``8`` / ``30`` from ``\"08:30\"``).
    """
    if not text or not cited_clocks:
        return text

    pieces: list[str] = []
    cursor = 0
    for match in _CLOCK_IN_TEXT_RE.finditer(text):
        label = match.group(1)
        if _clock_label_variants(label).isdisjoint(cited_clocks):
            continue
        pieces.append(text[cursor : match.start()])
        pieces.append(" " * (match.end() - match.start()))
        cursor = match.end()
    pieces.append(text[cursor:])
    return "".join(pieces)


def _allowed_number_tokens(values: list[Any]) -> set[str]:
    """Build normalized numeric tokens accepted for cited packet values.

    Int/float claim values contribute directly. String claim values contribute
    only when they are pure numeric tokens. ``HH:MM`` clock labels are handled
    separately as whole spans (see ``_mask_cited_clock_spans``) so citing
    ``\"08:30\"`` does not allowlist bare ``8`` / ``30``. Hash, path, and
    column-name strings do not launder digits.
    """
    allowed: set[str] = set()
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            allowed.add(_normalize_number_token(str(value)))
            continue
        if isinstance(value, str):
            text = value.strip()
            if not text or _CLOCK_BUCKET_RE.fullmatch(text):
                continue
            if _NUMERIC_STRING_RE.fullmatch(text):
                allowed.update(_extract_number_tokens(text))
    return allowed


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


def _ungrounded_number_tokens(
    text: str,
    *,
    allowed: set[str],
    cited_clocks: set[str] | None = None,
) -> list[str]:
    """Return normalized digit tokens in *text* that are not grounded."""
    working = _mask_cited_clock_spans(text, cited_clocks or set())
    uncited: list[str] = []
    for match in _NUMBER_RE.finditer(working):
        raw = match.group(0)
        if _token_grounded(raw, allowed=allowed):
            continue
        uncited.append(_normalize_number_token(raw))
    return uncited


def _assert_tokens_grounded(
    text: str,
    *,
    allowed: set[str],
    cited_clocks: set[str] | None = None,
) -> None:
    for token in _ungrounded_number_tokens(text, allowed=allowed, cited_clocks=cited_clocks):
        raise LLMEvidenceError(
            f"Uncited numerical claim {token!r} is not grounded in cited evidence."
        )


def _llm_caveat_echoes_packet_message(llm_caveat: str, packet_message: str) -> bool:
    """True when an LLM caveat line contains the full packet caveat message.

    Partial/trivial substrings (e.g. ``\"missing.\"``) do **not** count — the
    mandatory honesty sentence must actually appear in the LLM line.
    """
    if not packet_message or not llm_caveat:
        return False
    return packet_message in llm_caveat


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


# Soften language that asserts OOS/WFA confirmation (not mere proximity of
# "robust" to an honesty disclaimer about missing walk-forward evidence).
_OOS_SOFTEN_RE = re.compile(
    r"\b("
    r"(?:oos|out[\s-]*of[\s-]*sample|wfa|walk[\s-]*forward)\s+is\s+"
    r"(?:confirm(?:ed)?|robust|proven|validated|successful)"
    r"|"
    r"(?:confirm(?:ed)?|proven|validated)\s+by\s+"
    r"(?:oos|out[\s-]*of[\s-]*sample|wfa|walk[\s-]*forward)"
    r"|"
    r"robust\s+out[\s-]*of[\s-]*sample"
    r"|"
    r"(?:oos|out[\s-]*of[\s-]*sample)\s+robust"
    r"|"
    r"successful\s+(?:oos|out[\s-]*of[\s-]*sample|wfa|walk[\s-]*forward)\s+folds?"
    r")\b",
    re.IGNORECASE,
)
# Hedge/negation may sit inside the soften span or in the preceding clause.
# Deliberately omit "missing"/"absent" so an earlier honesty clause cannot
# launder a later confirmation ("evidence is missing; OOS is confirmed").
_OOS_SOFTEN_NEGATION_RE = re.compile(
    r"\b(?:not|never|without|unless|unconfirmed|cannot|can't|"
    r"isn't|aren't|wasn't|weren't|no longer|don't|do not|"
    r"assume|assuming|whether|verify|check|ask(?:ing)?)\b",
    re.IGNORECASE,
)


def _has_oos_soften_language(text: str) -> bool:
    """True when text asserts OOS/WFA confirmation without local negation/hedge."""
    for match in _OOS_SOFTEN_RE.finditer(text):
        span = match.group(0)
        prefix = text[max(0, match.start() - 48) : match.start()]
        if _OOS_SOFTEN_NEGATION_RE.search(span) or _OOS_SOFTEN_NEGATION_RE.search(prefix):
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
    claim_values = [claim.value for claim in claims]
    allowed_from_claims = _allowed_number_tokens(claim_values)
    cited_clocks = _cited_clock_labels(claim_values)
    # Summary and claim text may only use numbers from cited claim values.
    _assert_tokens_grounded(summary, allowed=allowed_from_claims, cited_clocks=cited_clocks)
    for claim in claims:
        _assert_tokens_grounded(claim.text, allowed=allowed_from_claims, cited_clocks=cited_clocks)
    for followup in followups:
        _assert_tokens_grounded(followup, allowed=allowed_from_claims, cited_clocks=cited_clocks)
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
        _assert_tokens_grounded(llm_caveat, allowed=allowed, cited_clocks=cited_clocks)

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
