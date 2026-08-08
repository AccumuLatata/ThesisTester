"""Digit-token grounding helpers for spoken voice text (VA-3/VA-4).

Reuses C2-6 / RQ number-token normalization from ``llm_explainer``. Does not
trust raw model speech; returns a schema-versioned ``GroundingVerdict``.

Allowlist policy mirrors C2 ``assert_llm_explanation_grounded``:
- claim **values**: int/float plus pure numeric strings; cited ``HH:MM``
  clock labels ground matching spoken clock spans as wholes (component
  digits are not allowlisted) — not free-text claim/caveat/hash digits
- European decimal commas (``0,25``) and ``Prozent`` / spaced ``%`` forms
  follow the same C2 / RQ normalizers; thousands groups (``25,000``) do not
  launder smaller cited integers
- tool results contribute int/float leaves only (not hash/run_id strings)

VA-4 also formats speakable text (summary + short caveats; no claim-path
markup) and templates deterministic fallback tool replies.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping, Sequence

from thesistester.assistant.explainer import EvidenceClaim, EvidencePacket
from thesistester.assistant.llm_explainer import (
    _allowed_number_tokens,
    _cited_clock_labels,
    _extract_number_tokens,
    _normalize_number_token,
    _ungrounded_number_tokens,
)
from thesistester.assistant.voice.contracts import GroundingVerdict

_CLAIM_PATH_MARKUP_RE = re.compile(r"`[^`]+`\s*=\s*")
_MAX_SPOKEN_CAVEATS = 3

UNGROUNDED_SPOKEN_REMEDIATION = (
    "I could not ground every number in that spoken answer from the bound "
    "evidence or help corpus. Please use the text Discuss or Help panel for "
    "the full cited reply."
)

HELP_NO_OPENAI_REMEDIATION = (
    "Spoken Help needs an OpenAI API key for documentation answers. "
    "Set OPENAI_API_KEY, or use the text Help panel. "
    "I will not invent product documentation."
)


def normalize_number_token(token: str) -> str:
    """Public wrapper for the shared C2-6 / RQ numeric token normalizer."""
    return _normalize_number_token(token)


def extract_digit_tokens(text: str) -> tuple[str, ...]:
    """Return normalized digit tokens found in ``text`` (order preserved)."""
    if not isinstance(text, str) or not text:
        return ()
    return tuple(_extract_number_tokens(text))


def allowed_tokens_from_values(values: Iterable[Any]) -> set[str]:
    """Build an allowlist from cited claim/tool values (C2 / RQ parity).

    Delegates to ``llm_explainer._allowed_number_tokens`` so spoken grounding
    accepts pure numeric strings while still ignoring hashes, paths,
    column-name strings, and clock-component digit splits.
    """
    return _allowed_number_tokens(list(values))


def allowed_tokens_from_packet(packet: EvidencePacket) -> set[str]:
    """Allowlist numbers from typed packet claim values only (not caveat text)."""
    return allowed_tokens_from_values(claim.value for claim in packet.claims)


def allowed_tokens_from_tool_result(result: Mapping[str, Any] | None) -> set[str]:
    """Collect int/float digit tokens from a JSON-safe voice tool result.

    Prefers an explicit scalar ``value`` (``get_metric``). Otherwise walks the
    payload for numeric leaves only — never extracts digits from strings
    (hashes, run ids, caveat messages).
    """
    if not isinstance(result, Mapping):
        return set()
    if "value" in result:
        value = result.get("value")
        if isinstance(value, bool):
            return set()
        if isinstance(value, (int, float)):
            return {_normalize_number_token(str(value))}
        # Non-numeric metric values contribute no spoken digit allowlist.
        return set()

    allowed: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            allowed.add(_normalize_number_token(str(value)))
            return
        if isinstance(value, Mapping):
            for item in value.values():
                walk(item)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    # Prefer claim values when present (overview payloads).
    claims = result.get("claims")
    if isinstance(claims, list):
        for claim in claims:
            if isinstance(claim, Mapping):
                walk(claim.get("value"))
        if allowed:
            return allowed
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
    clock_source_values: list[Any] = []
    if allowed_tokens is not None:
        for token in allowed_tokens:
            if isinstance(token, str) and token.strip():
                allowed.add(_normalize_number_token(token))
    if allowed_values is not None:
        clock_source_values.extend(list(allowed_values))
        allowed |= allowed_tokens_from_values(allowed_values)
    if claims is not None:
        claim_values = [claim.value for claim in claims]
        clock_source_values.extend(claim_values)
        allowed |= allowed_tokens_from_values(claim_values)
    if packet is not None:
        packet_values = [claim.value for claim in packet.claims]
        clock_source_values.extend(packet_values)
        allowed |= allowed_tokens_from_values(packet_values)
    if tool_result is not None:
        allowed |= allowed_tokens_from_tool_result(tool_result)

    cited_clocks = _cited_clock_labels(clock_source_values)
    uncited: list[str] = []
    seen: set[str] = set()
    for normalized in _ungrounded_number_tokens(
        audited, allowed=allowed, cited_clocks=cited_clocks
    ):
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


def strip_claim_path_markup(text: str) -> str:
    """Remove backtick path citations so speech does not read raw claim paths."""
    cleaned = _CLAIM_PATH_MARKUP_RE.sub("", text)
    return " ".join(cleaned.split())


# Backward-compatible private alias for in-module call sites.
_strip_claim_path_markup = strip_claim_path_markup


def _join_caveats(caveats: Sequence[Any], *, limit: int = _MAX_SPOKEN_CAVEATS) -> str:
    lines: list[str] = []
    for item in caveats:
        if len(lines) >= limit:
            break
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, Mapping):
            text = str(item.get("message") or item.get("text") or "").strip()
        else:
            text = str(getattr(item, "message", "") or getattr(item, "text", "") or "").strip()
        if text:
            lines.append(_strip_claim_path_markup(text))
    return "; ".join(lines)


def format_speakable_results_reply(reply: Any) -> str:
    """Prefer summary + short caveats; strip claim-path markup for speech."""
    summary = _strip_claim_path_markup(str(getattr(reply, "summary", "") or "").strip())
    caveats = getattr(reply, "caveats", ()) or ()
    caveat_text = _join_caveats(tuple(caveats))
    if summary and caveat_text:
        return f"{summary} Caveats: {caveat_text}."
    if summary:
        return summary
    if caveat_text:
        return f"Caveats: {caveat_text}."
    return "I could not form a speakable summary from that results reply."


def format_speakable_help_reply(reply: Any) -> str:
    """Prefer Help summary + short caveats; omit citation path markup."""
    summary = _strip_claim_path_markup(str(getattr(reply, "summary", "") or "").strip())
    caveats = getattr(reply, "caveats", ()) or ()
    caveat_text = _join_caveats(tuple(caveats))
    if summary and caveat_text:
        return f"{summary} Caveats: {caveat_text}."
    if summary:
        return summary
    if caveat_text:
        return f"Caveats: {caveat_text}."
    return "I could not form a speakable summary from that help reply."


def allowed_tokens_from_help_corpus(
    corpus_chunks: Sequence[Mapping[str, Any] | Any] | None,
    registry_digest: Any = None,
) -> set[str]:
    """Allowlist digit tokens present in attached Help corpus / registry text."""
    parts: list[str] = []
    for chunk in corpus_chunks or ():
        if isinstance(chunk, Mapping):
            parts.append(str(chunk.get("text") or ""))
            parts.append(str(chunk.get("section") or ""))
            parts.append(str(chunk.get("doc_id") or ""))
        else:
            parts.append(str(getattr(chunk, "text", "") or ""))
            parts.append(str(getattr(chunk, "section", "") or ""))
            parts.append(str(getattr(chunk, "doc_id", "") or ""))
    if registry_digest is not None:
        try:
            parts.append(json.dumps(registry_digest, sort_keys=True, default=str))
        except (TypeError, ValueError):
            parts.append(str(registry_digest))
    return set(extract_digit_tokens("\n".join(parts)))


def format_speakable_tool_result(
    tool_name: str,
    result: Mapping[str, Any] | None,
    *,
    spoken_note: str | None = None,
) -> str:
    """Deterministic speakable template for one VA-3 fallback tool result."""
    payload = result if isinstance(result, Mapping) else {}
    prefix = (spoken_note or "").strip()
    body: str
    if tool_name == "get_metric":
        path = str(payload.get("path") or "metric")
        value = payload.get("value")
        body = f"The value of {path} is {value}."
    elif tool_name == "list_caveats":
        # Caveat *messages* are free text — do not speak their digit tokens
        # (VA-3 allowlist is typed values only). Speak a grounded count instead.
        caveats = payload.get("caveats") or []
        warnings = payload.get("warnings") or []
        caveat_n = len(caveats) if isinstance(caveats, list) else 0
        warning_n = len(warnings) if isinstance(warnings, list) else 0
        if caveat_n == 0 and warning_n == 0:
            body = "No caveats were listed for this run."
        else:
            body = (
                f"This run lists {caveat_n} honesty caveats and {warning_n} warnings "
                "on the bound evidence packet. Open text Discuss results to read them."
            )
    elif tool_name == "compare_two_runs":
        comparison = payload.get("comparison")
        metric_bits: list[str] = []
        if isinstance(comparison, Mapping):
            metrics = comparison.get("metrics")
            if isinstance(metrics, Mapping):
                for key, value in metrics.items():
                    if not isinstance(value, Mapping):
                        continue
                    left_v = value.get("left")
                    right_v = value.get("right")
                    if isinstance(left_v, (int, float)) and not isinstance(left_v, bool):
                        metric_bits.append(f"{key} left {left_v}")
                    if isinstance(right_v, (int, float)) and not isinstance(right_v, bool):
                        metric_bits.append(f"{key} right {right_v}")
                    if len(metric_bits) >= 6:
                        break
        if metric_bits:
            body = (
                "Comparison of the bound run versus the other completed run: "
                + "; ".join(metric_bits)
                + ". This comparison is not persisted."
            )
        else:
            body = (
                "Compared the bound run with the other completed run using pure "
                "evidence compare. This comparison is not persisted."
            )
    else:
        # get_run_overview — DX-1: prefer DI summary (+ digit-free overlay);
        # else legacy overview. Caveat free-text digits are not typed claim
        # values and must not be laundered into trusted speech.
        summary = str(payload.get("summary") or "").strip()
        if summary:
            body = _strip_claim_path_markup(summary)
            overlay = payload.get("expert_overlay") or ()
            overlay_lines: list[str] = []
            if isinstance(overlay, (list, tuple)):
                for item in overlay:
                    text = str(item or "").strip()
                    if text:
                        overlay_lines.append(_strip_claim_path_markup(text))
            if overlay_lines:
                body = f"{body} {' '.join(overlay_lines)}"
        else:
            overview = str(payload.get("overview") or "").strip()
            if overview:
                body = _strip_claim_path_markup(overview)
            else:
                body = "Here is the grounded run overview from the bound evidence packet."
    if prefix:
        return f"{prefix} {body}".strip()
    return body.strip()
