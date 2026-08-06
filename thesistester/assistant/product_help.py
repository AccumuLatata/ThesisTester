"""Multi-turn product/help Q&A over the §7.1 Help corpus (RQ-3)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from thesistester.assistant.help_corpus import (
    REGISTRY_DOC_ID,
    REGISTRY_SECTION,
    CorpusChunk,
)
from thesistester.assistant.llm import StructuredLLMClient
from thesistester.assistant.llm_explainer import (
    _NUMBER_RE,
    _extract_number_tokens,
    _normalize_number_token,
)

PRODUCT_HELP_CHANNEL = "product_help"

_HELP_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "caveats", "citations", "followups"],
    "properties": {
        "summary": {"type": "string"},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["doc_id", "section"],
                "properties": {
                    "doc_id": {"type": "string"},
                    "section": {"type": "string"},
                },
            },
        },
        "followups": {"type": "array", "items": {"type": "string"}},
    },
}

_SYSTEM_PROMPT = (
    "Answer only from the supplied help corpus chunks and registry digest. "
    "Cite every used source with citations[{doc_id, section}] that match "
    'attached chunks. For the capability registry, cite doc_id="registry" and '
    'section="digest" (never doc_id="registry_digest"). Do not invent product '
    "features, capabilities, or run metrics. Do not answer the user's backtest "
    "or grid performance for a specific completed run — if asked, say to use "
    "Discuss results under Advanced → Linked runs. Prefer number-free followups. "
    "Any number you include in summary/caveats/followups must appear as the same "
    "number token in the attached corpus texts or registry digest JSON "
    "(e.g. reply token 3 is not grounded by corpus 30)."
)

# Phrases that indicate the user wants *their* completed-run performance.
# Avoid bare product nouns like "grid" / "run" after possessives — those are
# legitimate Help questions ("how does my grid ranking work?", "how does this
# run get confirmed?"). Prefer metric/result nouns and past-tense run asks.
#
# Definition / docs asks about the *same* metric nouns must stay in Help
# ("How is my expectancy computed?", "What does this performance metric mean?").
# Only definition/computation collocates — not bare "docs"/"metric", which
# would suppress legitimate run-performance asks that mention those words.
# Applied only when no strong run-performance anchor is present (see below).
_DOC_DEFINITION_ESCAPE = re.compile(
    r"(?:"
    r"\b(?:comput(?:e|ed|ing|ation)|calculat(?:e|ed|ing|ion)|"
    r"defin(?:e|ed|ing|ition))\b|"
    r"\bwhat\s+does\b[\s\S]{0,48}\bmean\b|"
    r"\bhow\s+(?:is|are)\b[\s\S]{0,48}\b(?:computed|calculated|defined|measured)\b"
    r")",
    re.IGNORECASE,
)

# Past-tense / run-anchored asks win over incidental compute/define vocabulary
# ("What was my calculated expectancy on this run?").
_STRONG_RUN_PERF_ANCHOR = re.compile(
    r"(?:"
    r"\bwhat\s+(?:was|were)\s+my\b|"
    r"\bhow\s+did\s+(?:this|my|that)\s+run\b|"
    r"\b(?:on|in|for|from)\s+(?:this|my|that)\s+run\b|"
    r"\bperformance\s+of\s+(?:this|my|that)\s+run\b|"
    r"\b(?:this|my|that)\s+(?:completed\s+)?run(?:'?s)?\s+"
    r")",
    re.IGNORECASE,
)

# Optional adjectives between possessive and metric ("my calculated expectancy").
_METRIC_MODIFIERS = r"(?:(?:best|worst|calculated|computed|defined|overall|final|latest|net)\s+)*"

_RUN_PERF_PATTERNS = (
    # Concrete personal metrics (definition escape still applies above).
    re.compile(
        rf"\b(my|this|that|our)\s+{_METRIC_MODIFIERS}"
        r"(sl|tp|stop(\s+loss)?|take[\s-]?profit|expectancy|win[\s-]?rate|"
        r"drawdown|pnl|cell)\b",
        re.IGNORECASE,
    ),
    # Vague nouns (results/performance/trades) need best/worst or a run anchor —
    # otherwise export/workflow Help ("where are my results?") remediates wrongly.
    re.compile(
        r"\b(my|this|that|our)\s+(best\s+|worst\s+)"
        r"(trades?|results?|performance)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(my|this|that|our)\s+(trades?|results?|performance)\b"
        r"[\s\S]{0,48}\b(?:on|in|for|from)\s+(?:this|my|that)\s+run\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bwhat\s+(?:was|were)\s+my\s+{_METRIC_MODIFIERS}"
        r"(sl|tp|stop(\s+loss)?|take[\s-]?profit|expectancy|win[\s-]?rate|"
        r"drawdown|pnl|trades?|results?|performance|cell)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(best|worst)\s+(sl|tp|stop|take[\s-]?profit|entry\s+time|window|"
        r"expectancy|cell)\b.*\b(for\s+(this|my|that)\s+run|in\s+this\s+run|"
        r"on\s+this\s+run)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(this|my|that)\s+(completed\s+)?run('?s)?\s+"
        r"(expectancy|win[\s-]?rate|sl|tp|trades?|results?|performance)\b",
        re.IGNORECASE,
    ),
    # Past-tense performance of a specific run. Present "how does this run…"
    # is treated as product/workflow Help (confirmation, lifecycle, etc.).
    re.compile(
        r"\bhow\s+did\s+(this|my|that)\s+run\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bperformance\s+of\s+(this|my|that)\s+run\b",
        re.IGNORECASE,
    ),
)

_REMEDIATION_SUMMARY = (
    "Help answers how ThesisTester features work from documentation and the "
    "capability registry. Questions about a completed run's performance "
    "(best SL/TP, expectancy, entry windows, trade counts) belong in "
    "Discuss results under Advanced → Linked runs for that run."
)


class HelpEvidenceError(ValueError):
    """Raised when a Help reply violates corpus/registry grounding rules."""


@dataclass(frozen=True)
class HelpCitation:
    """One citation into an attached corpus chunk or registry digest."""

    doc_id: str
    section: str

    def to_dict(self) -> dict[str, str]:
        return {"doc_id": self.doc_id, "section": self.section}


@dataclass(frozen=True)
class HelpReply:
    """Grounded product-help reply; citations reference attached chunks only."""

    summary: str
    caveats: tuple[str, ...]
    citations: tuple[HelpCitation, ...] = ()
    followups: tuple[str, ...] = ()
    remediation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "caveats": list(self.caveats),
            "citations": [item.to_dict() for item in self.citations],
            "followups": list(self.followups),
            "remediation": self.remediation,
        }


def is_run_performance_question(message: str) -> bool:
    """Return True when the user asks for *this/my* completed-run performance."""
    if not isinstance(message, str) or not message.strip():
        return False
    text = message.strip()
    if not any(pattern.search(text) for pattern in _RUN_PERF_PATTERNS):
        return False
    # Definition/computation wording stays in Help unless a strong run-performance
    # anchor is also present (past-tense my-metrics or explicit run phrasing).
    if _DOC_DEFINITION_ESCAPE.search(text) and not _STRONG_RUN_PERF_ANCHOR.search(text):
        return False
    return True


def remediation_help_reply() -> HelpReply:
    """Structured redirect to Discuss results (no fabricated metrics)."""
    return HelpReply(
        summary=_REMEDIATION_SUMMARY,
        caveats=("Help does not load run evidence packets or invent performance numbers.",),
        citations=(),
        followups=("Open Advanced → Linked runs → Discuss results for a completed run.",),
        remediation=True,
    )


def format_help_reply_content(reply: HelpReply) -> str:
    """Build persisted assistant ``content`` for a product-help turn."""
    lines = [reply.summary.strip()]
    if reply.citations:
        lines.append("")
        lines.append("Citations:")
        for citation in reply.citations:
            lines.append(f"- `{citation.doc_id}` / `{citation.section}`")
    if reply.caveats:
        lines.append("")
        lines.append("Caveats:")
        lines.extend(f"- {item}" for item in reply.caveats)
    if reply.followups:
        lines.append("")
        lines.append("Follow-ups:")
        lines.extend(f"- {item}" for item in reply.followups)
    return "\n".join(lines).strip()


def filter_product_help_history(
    messages: Sequence[Mapping[str, Any]],
    *,
    max_history_messages: int,
) -> tuple[dict[str, Any], ...]:
    """Return the last N product_help messages (excluding tools)."""
    if not isinstance(max_history_messages, int) or max_history_messages < 0:
        raise ValueError("max_history_messages must be a non-negative integer.")
    selected: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        if message.get("channel") != PRODUCT_HELP_CHANNEL:
            continue
        role = str(message.get("role") or "").strip().lower()
        if role not in {"user", "human", "assistant", "ai"}:
            continue
        selected.append(dict(message))
    if max_history_messages == 0:
        return ()
    return tuple(selected[-max_history_messages:])


def _grounding_haystack(
    corpus_chunks: Sequence[CorpusChunk | Mapping[str, Any]],
    registry_digest: Sequence[Mapping[str, Any]] | str,
) -> str:
    parts: list[str] = []
    for chunk in corpus_chunks:
        if isinstance(chunk, CorpusChunk):
            parts.append(chunk.text)
        elif isinstance(chunk, Mapping):
            text = chunk.get("text")
            if isinstance(text, str):
                parts.append(text)
    if isinstance(registry_digest, str):
        parts.append(registry_digest)
    else:
        parts.append(json.dumps(list(registry_digest), sort_keys=True, ensure_ascii=True))
    return "\n".join(parts)


def assert_help_reply_grounded(
    *,
    summary: str,
    caveats: Sequence[str],
    followups: Sequence[str],
    corpus_chunks: Sequence[CorpusChunk | Mapping[str, Any]],
    registry_digest: Sequence[Mapping[str, Any]] | str,
) -> None:
    """Reject digit tokens absent as number tokens in corpus/registry text.

    Uses the same numeric tokenizer as LLM evidence grounding so a reply token
    like ``1`` cannot ride on a different number such as ``10`` / ``30``.
    """
    haystack = _grounding_haystack(corpus_chunks, registry_digest)
    allowed = set(_extract_number_tokens(haystack))
    for field_name, text in (
        ("summary", summary),
        *((f"caveat[{index}]", item) for index, item in enumerate(caveats)),
        *((f"followup[{index}]", item) for index, item in enumerate(followups)),
    ):
        for match in _NUMBER_RE.finditer(text):
            token = _normalize_number_token(match.group(0))
            if token not in allowed:
                raise HelpEvidenceError(
                    f"Uncited numerical token {token!r} in Help {field_name} "
                    "is not present as a number token in the attached corpus "
                    "or registry digest."
                )


def _attached_citation_keys(
    corpus_chunks: Sequence[CorpusChunk | Mapping[str, Any]],
) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = {(REGISTRY_DOC_ID, REGISTRY_SECTION)}
    for chunk in corpus_chunks:
        if isinstance(chunk, CorpusChunk):
            keys.add((chunk.doc_id, chunk.section))
        elif isinstance(chunk, Mapping):
            doc_id = chunk.get("doc_id")
            section = chunk.get("section")
            if isinstance(doc_id, str) and isinstance(section, str):
                keys.add((doc_id, section))
    return keys


def propose_help_reply(
    client: StructuredLLMClient,
    *,
    corpus_chunks: Sequence[CorpusChunk | Mapping[str, Any]],
    registry_digest: Sequence[Mapping[str, Any]] | str,
    history: Sequence[Mapping[str, Any]],
    user_message: str,
) -> HelpReply:
    """Request a corpus-grounded Help reply; fail closed on uncited digits/citations."""
    if not isinstance(user_message, str) or not user_message.strip():
        raise HelpEvidenceError("Help user message must be a non-empty string.")
    if is_run_performance_question(user_message):
        return remediation_help_reply()

    chunk_payload = [
        chunk.to_dict() if isinstance(chunk, CorpusChunk) else dict(chunk)
        for chunk in corpus_chunks
    ]
    digest_payload: Any
    if isinstance(registry_digest, str):
        try:
            digest_payload = json.loads(registry_digest)
        except json.JSONDecodeError:
            digest_payload = registry_digest
    else:
        digest_payload = list(registry_digest)

    history_lines = [
        {"role": message.get("role"), "content": message.get("content")}
        for message in history
        if isinstance(message, Mapping)
    ]
    user_payload = {
        "corpus_chunks": chunk_payload,
        "registry_digest": digest_payload,
        "history": history_lines,
        "user_message": user_message.strip(),
    }
    payload = client.complete_structured(
        system=_SYSTEM_PROMPT,
        user=json.dumps(user_payload, sort_keys=True),
        schema=_HELP_SCHEMA,
    )
    if set(payload) != {"summary", "caveats", "citations", "followups"}:
        raise HelpEvidenceError(
            "Help reply must contain only summary, caveats, citations, and followups."
        )
    summary = payload["summary"]
    caveats = payload["caveats"]
    citations_raw = payload["citations"]
    followups_raw = payload["followups"]
    if (
        not isinstance(summary, str)
        or not summary.strip()
        or not isinstance(caveats, list)
        or not isinstance(citations_raw, list)
        or not isinstance(followups_raw, list)
    ):
        raise HelpEvidenceError("Help reply has invalid field types.")
    if any(not isinstance(caveat, str) or not caveat.strip() for caveat in caveats):
        raise HelpEvidenceError("Help caveats must be non-empty strings.")
    if any(not isinstance(followup, str) or not followup.strip() for followup in followups_raw):
        raise HelpEvidenceError("Help followups must be non-empty strings.")

    attached = _attached_citation_keys(corpus_chunks)
    citations: list[HelpCitation] = []
    for item in citations_raw:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"doc_id", "section"}
            or not isinstance(item.get("doc_id"), str)
            or not item["doc_id"].strip()
            or not isinstance(item.get("section"), str)
            or not item["section"].strip()
        ):
            raise HelpEvidenceError("Help citations must be non-empty doc_id/section objects.")
        doc_id = item["doc_id"].strip()
        section = item["section"].strip()
        # Models sometimes echo the user-payload key ``registry_digest`` instead
        # of the attached corpus doc_id ``registry`` (same section ``digest``).
        if doc_id == "registry_digest":
            doc_id = REGISTRY_DOC_ID
        if (doc_id, section) not in attached:
            raise HelpEvidenceError(
                f"Help citation {doc_id!r}/{section!r} was not attached to this turn."
            )
        citations.append(HelpCitation(doc_id=doc_id, section=section))

    summary_text = summary.strip()
    caveat_texts = tuple(caveat.strip() for caveat in caveats)
    followup_texts = tuple(followup.strip() for followup in followups_raw)
    assert_help_reply_grounded(
        summary=summary_text,
        caveats=caveat_texts,
        followups=followup_texts,
        corpus_chunks=corpus_chunks,
        registry_digest=registry_digest,
    )
    return HelpReply(
        summary=summary_text,
        caveats=caveat_texts,
        citations=tuple(citations),
        followups=followup_texts,
        remediation=False,
    )
