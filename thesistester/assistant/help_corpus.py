"""Frozen Help corpus allowlist and pure loaders (RQ-0 / HC amends).

Encodes ``docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`` §7.1 exactly
(including HC-1 ``user_guide`` §7.1.4). No orchestrator wiring, network I/O,
or OpenAI calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PREFACE_SECTION = "__preface__"
REGISTRY_DOC_ID = "registry"
REGISTRY_SECTION = "digest"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


class HelpCorpusError(ValueError):
    """Raised when a Help corpus path/section request violates the §7.1 freeze."""


@dataclass(frozen=True)
class CorpusDocSpec:
    """One allowlisted Help source from §7.1."""

    doc_id: str
    relative_path: str | None
    mode: str  # whole_file | sections | digest
    sections: frozenset[str]


@dataclass(frozen=True)
class CorpusChunk:
    """One allowlisted markdown chunk ready for a Help turn."""

    doc_id: str
    section: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"doc_id": self.doc_id, "section": self.section, "text": self.text}


# Exact H2 titles from §7.1.1–§7.1.3 (case-sensitive; backticks are significant).
_ARCHITECTURE_SECTIONS = frozenset(
    {
        "AI Research Assistant contract boundary (AIA-0)",
        "Classic ↔ Assistant navigation and identity badges (CAI-8)",
        "Evidence-backed page capabilities (CAI-9)",
        "End-to-end data flow",
        "`st.session_state` contract (current)",
    }
)

_ASSUMPTIONS_SECTIONS = frozenset(
    {
        "Verified engine assumptions (current implementation)",
        "6) Point-in-time correctness (R3 audit)",
        "Validation implications",
        "Futures roll methodology (R7)",
        "AI Research Assistant / optional LLM (PR6 release gate)",
        "Voice agent (VA-series — proposed, not shipped)",
        "OTF filter (One Timeframing)",
        "Practical interpretation",
    }
)

_OTF_SECTIONS = frozenset(
    {
        "Purpose",
        "§1 — Concept",
        "§2 — State vocabulary",
        "§3 — State-transition rules",
        "§4 — Configuration parameters",
        "§5 — Supported higher timeframes",
        "§6 — Completed-bar availability and look-ahead safety",
        "§7 — Timezone and session alignment",
        "§8 — Directional eligibility",
        "§9 — Rejected signals",
        "§13b — PR 5 Research-Mode Integration",
        "§15 — Release-Gate Documentation",
    }
)

# HC-1…HC-3 filled USER_GUIDE H2s (full §6.1 skeleton allowlisted).
_USER_GUIDE_SECTIONS = frozenset(
    {
        "Purpose and honesty",
        "Classic workflow overview",
        "Data",
        "Levels",
        "Setup Builder",
        "Signals",
        "Backtest",
        "Grid Search",
        "Time Analysis",
        "Validation and robustness",
        "Report Export",
        "Research Bundles",
        "Portfolio",
        "Research Assistant (draft, Discuss, Help)",
        "Research mode on classic pages",
        "When to use Help vs Discuss results",
    }
)

# How-to / workflow cues for HC §1.1 intent-aware user_guide boost.
# Keep aligned with HELP_CORPUS_COVERAGE_IMPLEMENTATION.md §1.1 cue table —
# avoid ultra-common tokens (`use`, bare `setup`) that flip definition queries
# into how-to mode.
_HOW_TO_QUERY_TOKENS = frozenset(
    {
        "how",
        "configure",
        "import",
        "generate",
        "export",
        "link",
        "record",
        "steps",
        "where",
        "upload",
        "build",
        "run",
        "enable",
        "save",
        "load",
    }
)
_DEFINITION_QUERY_TOKENS = frozenset(
    {
        "what",
        "define",
        "definition",
        "meaning",
        "mean",
    }
)
_COST_QUERY_TOKENS = frozenset(
    {
        "cost",
        "costs",
        "commission",
        "commission_per_side",
        "slippage",
        "slippage_ticks",
        # Note: ``exposure`` is intentionally omitted — Backtest exposure policy
        # lives in USER_GUIDE, not the Execution cost inputs glossary H2.
    }
)
# Stopwords ignored when matching query tokens to USER_GUIDE H2 titles so
# titles like "Purpose and honesty" do not get a strong boost from bare "and".
_SECTION_TITLE_STOPWORDS = frozenset(
    {
        "and",
        "or",
        "the",
        "to",
        "of",
        "a",
        "an",
        "in",
        "on",
        "for",
        "vs",
        "with",
        "via",
    }
)
# Intent/function words excluded from substring lexical scoring. They still
# participate in how-to / definitional cue detection via the sets above.
# Without this, ``is`` matches inside ``Assistant`` section titles and crowds
# out glossary definitions under max_corpus_chars.
_LEXICAL_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "did",
        "do",
        "does",
        "for",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "the",
        "to",
        "use",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "why",
        "you",
    }
)

HELP_CORPUS_MANIFEST: tuple[CorpusDocSpec, ...] = (
    CorpusDocSpec("readme", "README.md", "whole_file", frozenset()),
    CorpusDocSpec("metrics", "docs/METRICS_GLOSSARY.md", "whole_file", frozenset()),
    CorpusDocSpec(
        "research_methodology",
        "docs/research-methodology.md",
        "whole_file",
        frozenset(),
    ),
    CorpusDocSpec(
        "architecture",
        "docs/ARCHITECTURE.md",
        "sections",
        _ARCHITECTURE_SECTIONS,
    ),
    CorpusDocSpec(
        "assumptions",
        "docs/ASSUMPTIONS_AND_LIMITATIONS.md",
        "sections",
        _ASSUMPTIONS_SECTIONS,
    ),
    CorpusDocSpec("otf", "docs/otf-filter.md", "sections", _OTF_SECTIONS),
    CorpusDocSpec(
        "user_guide",
        "docs/USER_GUIDE.md",
        "sections",
        _USER_GUIDE_SECTIONS,
    ),
    CorpusDocSpec(REGISTRY_DOC_ID, None, "digest", frozenset()),
)

_MANIFEST_BY_ID: dict[str, CorpusDocSpec] = {spec.doc_id: spec for spec in HELP_CORPUS_MANIFEST}

# Explicitly excluded operator/agent surface (fail closed).
_EXCLUDED_RELATIVE_PATHS = frozenset({"docs/AGENT_GUIDE.md"})


def manifest_doc_ids() -> tuple[str, ...]:
    return tuple(spec.doc_id for spec in HELP_CORPUS_MANIFEST)


def get_corpus_doc_spec(doc_id: str) -> CorpusDocSpec:
    try:
        return _MANIFEST_BY_ID[doc_id]
    except KeyError as exc:
        raise HelpCorpusError(f"Unknown Help corpus doc_id: {doc_id!r}") from exc


def resolve_corpus_path(relative_path: str, *, repo_root: str | Path) -> Path:
    """Resolve an allowlisted relative path under ``repo_root``; reject traversal.

    After ``Path.resolve()`` (symlink-aware), the canonical relative path must
    still be the requested allowlisted path — a symlink at an allowlisted
    location cannot smuggle excluded content (e.g. ``AGENT_GUIDE``).
    """
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise HelpCorpusError("Corpus path must be a non-empty relative string.")
    cleaned = relative_path.strip().replace("\\", "/")
    if cleaned.startswith("/") or cleaned.startswith("~"):
        raise HelpCorpusError(f"Corpus path must be relative: {relative_path!r}")
    parts = Path(cleaned).parts
    if ".." in parts:
        raise HelpCorpusError(f"Corpus path must not contain '..': {relative_path!r}")
    if cleaned in _EXCLUDED_RELATIVE_PATHS or cleaned.endswith("AGENT_GUIDE.md"):
        raise HelpCorpusError(f"Corpus path is excluded from v1 Help: {relative_path!r}")
    allowlisted = {
        spec.relative_path for spec in HELP_CORPUS_MANIFEST if spec.relative_path is not None
    }
    if cleaned not in allowlisted:
        raise HelpCorpusError(f"Corpus path is not allowlisted: {relative_path!r}")
    root = Path(repo_root).resolve()
    candidate = (root / cleaned).resolve()
    try:
        resolved_relative = candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise HelpCorpusError(f"Corpus path escapes repository root: {relative_path!r}") from exc
    if resolved_relative in _EXCLUDED_RELATIVE_PATHS or resolved_relative.endswith(
        "AGENT_GUIDE.md"
    ):
        raise HelpCorpusError(f"Corpus path is excluded from v1 Help: {relative_path!r}")
    if resolved_relative != cleaned:
        raise HelpCorpusError(
            f"Corpus path resolves outside its allowlisted location: {relative_path!r} -> "
            f"{resolved_relative!r}"
        )
    return candidate


def _parse_atx_sections(markdown: str) -> list[tuple[int, str, str]]:
    """Return ``(level, section_title, body_including_heading)`` chunks.

    H2 sections include nested H3+ until the next H2 or higher. Per §7.1 rule 5,
    ``__preface__`` is everything before the first H2 (including an H1 title and
    its body). When the file has no H2s, the entire document is ``__preface__``.
    """
    lines = markdown.splitlines(keepends=True)
    entries: list[tuple[int, int, str]] = []  # (line_index, level, title)
    for idx, line in enumerate(lines):
        match = _HEADING_RE.match(line.rstrip("\n"))
        if match is None:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        entries.append((idx, level, title))

    chunks: list[tuple[int, str, str]] = []
    if not entries:
        text = "".join(lines).strip()
        if text:
            chunks.append((0, PREFACE_SECTION, text))
        return chunks

    # Build H2-oriented chunks. Nested deeper headings stay inside the enclosing
    # H2 body. Preface is strictly "before first H2" (not "before first heading").
    h2_entries = [(i, level, title) for i, level, title in entries if level == 2]
    if not h2_entries:
        text = "".join(lines).strip()
        if text:
            chunks.append((0, PREFACE_SECTION, text))
        return chunks

    first_h2_idx = h2_entries[0][0]
    if first_h2_idx > 0:
        preface = "".join(lines[:first_h2_idx]).strip()
        if preface:
            chunks.append((0, PREFACE_SECTION, preface))

    for start_idx, _level, title in h2_entries:
        # §7.1 rule 4: body runs until the next H2 *or higher* (level <= 2).
        end_idx = len(lines)
        for later_idx, later_level, _later_title in entries:
            if later_idx > start_idx and later_level <= 2:
                end_idx = later_idx
                break
        body = "".join(lines[start_idx:end_idx]).strip()
        if body:
            chunks.append((2, title, body))
    return chunks


def load_corpus_chunks(
    doc_id: str,
    *,
    repo_root: str | Path,
    sections: Sequence[str] | None = None,
) -> tuple[CorpusChunk, ...]:
    """Load allowlisted chunks for ``doc_id``.

    ``sections`` optional filter: when provided, every requested section must be
    allowlisted for that doc (or ``__preface__`` / any H2 under ``whole_file``).
    """
    spec = get_corpus_doc_spec(doc_id)
    if spec.mode == "digest":
        raise HelpCorpusError(
            "registry digest is generated via build_registry_digest(); it has no file path."
        )
    assert spec.relative_path is not None
    path = resolve_corpus_path(spec.relative_path, repo_root=repo_root)
    if not path.is_file():
        raise HelpCorpusError(f"Corpus file is missing: {spec.relative_path}")
    markdown = path.read_text(encoding="utf-8")
    parsed = _parse_atx_sections(markdown)
    present_titles = {title for _level, title, _text in parsed}
    if spec.mode == "whole_file":
        allowed_titles = present_titles
    else:
        allowed_titles = set(spec.sections)

    requested = list(sections) if sections is not None else None
    if requested is not None:
        for section in requested:
            if not isinstance(section, str) or not section.strip():
                raise HelpCorpusError("Corpus section must be a non-empty string.")
            if section not in allowed_titles:
                raise HelpCorpusError(
                    f"Section {section!r} is not allowlisted for doc_id={doc_id!r}"
                )

    selected: list[CorpusChunk] = []
    for _level, title, text in parsed:
        if title not in allowed_titles:
            continue
        if requested is not None and title not in requested:
            continue
        selected.append(CorpusChunk(doc_id=doc_id, section=title, text=text))

    if requested is not None:
        found = {chunk.section for chunk in selected}
        missing = [section for section in requested if section not in found]
        if missing:
            raise HelpCorpusError(f"Section(s) not available for doc_id={doc_id!r}: {missing!r}")
    return tuple(selected)


def load_allowlisted_corpus(
    *,
    repo_root: str | Path,
    doc_ids: Sequence[str] | None = None,
    max_chars: int | None = None,
) -> tuple[CorpusChunk, ...]:
    """Load chunks for file-backed allowlisted docs (excludes registry digest)."""
    ids = (
        list(doc_ids)
        if doc_ids is not None
        else [spec.doc_id for spec in HELP_CORPUS_MANIFEST if spec.mode != "digest"]
    )
    chunks: list[CorpusChunk] = []
    total = 0
    for doc_id in ids:
        spec = get_corpus_doc_spec(doc_id)
        if spec.mode == "digest":
            continue
        for chunk in load_corpus_chunks(doc_id, repo_root=repo_root):
            if max_chars is not None:
                if total + len(chunk.text) > max_chars:
                    # Do not skip past an oversized chunk to attach later ones —
                    # that silently drops allowlisted §7.1 content. Fail closed
                    # when even the first chunk cannot fit; otherwise stop.
                    if total == 0:
                        raise HelpCorpusError(
                            f"Corpus chunk exceeds max_corpus_chars ({max_chars}): "
                            f"{chunk.doc_id!r}/{chunk.section!r} "
                            f"({len(chunk.text)} chars)"
                        )
                    return tuple(chunks)
            chunks.append(chunk)
            total += len(chunk.text)
    return tuple(chunks)


def build_registry_digest(
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build the JSON-safe registry digest for Help turns (§7.1 ``registry``)."""
    if rows is None:
        from thesistester.assistant.registry import FEATURE_PARITY_REGISTRY

        source: Iterable[Any] = FEATURE_PARITY_REGISTRY
        digest: list[dict[str, Any]] = []
        for capability in source:
            item: dict[str, Any] = {
                "capability_id": capability.capability_id,
                "status": capability.mode.value,
            }
            if capability.public_symbol:
                item["public_symbol"] = capability.public_symbol
            item["confirmation"] = capability.confirmation.value
            if capability.limitation:
                item["limitation"] = capability.limitation
            digest.append(item)
        return digest

    digest = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        capability_id = row.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id.strip():
            continue
        item = {
            "capability_id": capability_id,
            "status": str(row.get("status", row.get("mode", ""))),
        }
        public_symbol = row.get("public_symbol")
        if isinstance(public_symbol, str) and public_symbol.strip():
            item["public_symbol"] = public_symbol
        confirmation = row.get("confirmation")
        if isinstance(confirmation, str) and confirmation.strip():
            item["confirmation"] = confirmation
        limitation = row.get("limitation")
        if isinstance(limitation, str) and limitation.strip():
            item["limitation"] = limitation
        digest.append(item)
    return digest


def registry_digest_json(rows: Iterable[Mapping[str, Any]] | None = None) -> str:
    """Serialize the registry digest for Help numeric grounding / prompts."""
    return json.dumps(build_registry_digest(rows), sort_keys=True, ensure_ascii=True)


def _tokenize_query(text: str) -> set[str]:
    # Exclude `/` so compounds like ``costs/exposure`` become separate tokens
    # (needed for HC §1.1 cost-noun boosts). Paths are not query syntax here.
    # Also expand ``snake_case`` identifiers so ``expectancy_r`` / ``commission_per_side``
    # match glossary prose that uses the stem nouns.
    tokens = {part.lower() for part in re.findall(r"[A-Za-z0-9_.`§-]{2,}", text)}
    cleaned = {
        token.strip("`'\".,:;!?()[]{}") for token in tokens if token.strip("`'\".,:;!?()[]{}")
    }
    expanded: set[str] = set()
    for token in cleaned:
        expanded.add(token)
        if "_" in token:
            for part in token.split("_"):
                if len(part) >= 2:
                    expanded.add(part)
    return expanded


def score_corpus_chunk(chunk: CorpusChunk, *, query_tokens: set[str]) -> int:
    """Cheap lexical score for Help retrieval (local docs only).

    HC §1.1: additive intent-aware ``user_guide`` how-to boost. Existing
    metrics/OTF/architecture boosts remain; definition queries are not forced
    onto USER_GUIDE.
    """
    if not query_tokens:
        return 0
    haystack = f"{chunk.doc_id} {chunk.section} {chunk.text}".lower()
    score = 0
    for token in query_tokens:
        if token in _LEXICAL_STOPWORDS:
            continue
        if token in haystack:
            score += 1
            if token in chunk.doc_id.lower() or token in chunk.section.lower():
                score += 2
    # Prefer glossary/architecture for ranking/metric questions.
    if {"grid", "ranking", "metric", "expectancy", "sl", "tp"} & query_tokens:
        if chunk.doc_id in {"metrics", "architecture", "assumptions"}:
            score += 3
    if query_tokens & _COST_QUERY_TOKENS and chunk.doc_id == "metrics":
        # Mixed how-to + cost nouns (Q-H5): keep glossary in the selected set.
        score += 3
        section_l = chunk.section.lower()
        if any(marker in section_l for marker in ("cost", "commission", "slippage")):
            # Prefer the dedicated Execution cost inputs H2 over incidental
            # cost mentions inside Core formulas / other metrics sections.
            score += 4
    if {"otf", "one", "timeframing", "timeframe"} & query_tokens and chunk.doc_id == "otf":
        score += 3
    if {"assistant", "capability", "registry", "confirm"} & query_tokens:
        if chunk.doc_id in {"architecture", "assumptions"}:
            score += 2
    # HC-1 §1.1: how-to cues prefer user_guide without removing other boosts.
    # Boost only title-overlapping sections (non-stopword tokens) so template
    # phrases like "How to use" do not flood max_corpus_chars with every H2.
    how_to = bool(query_tokens & _HOW_TO_QUERY_TOKENS)
    definitional = bool(query_tokens & _DEFINITION_QUERY_TOKENS)
    if how_to and chunk.doc_id == "user_guide":
        section_tokens = _tokenize_query(chunk.section) - _SECTION_TITLE_STOPWORDS
        if query_tokens & section_tokens:
            score += 5
    elif definitional and not how_to and chunk.doc_id == "user_guide":
        # Soft preference away from forcing USER_GUIDE on pure definitions.
        score -= 1
    return score


def select_help_corpus_chunks(
    user_message: str,
    *,
    repo_root: str | Path,
    max_chars: int,
    doc_ids: Sequence[str] | None = None,
) -> tuple[CorpusChunk, ...]:
    """Load §7.1 chunks and keep a query-relevant subset within ``max_chars``.

    Retrieval is lexical only (no network). Always fails closed through
    ``load_allowlisted_corpus`` path/section allowlists. When scoring finds no
    overlap, returns the budgeted prefix of the allowlisted corpus so Help can
    still answer general product questions.
    """
    if not isinstance(user_message, str) or not user_message.strip():
        raise HelpCorpusError("Help retrieval requires a non-empty user message.")
    if not isinstance(max_chars, int) or max_chars <= 0:
        raise HelpCorpusError("max_chars must be a positive integer.")
    all_chunks = load_allowlisted_corpus(repo_root=repo_root, doc_ids=doc_ids)
    if not all_chunks:
        return ()
    query_tokens = _tokenize_query(user_message)
    # Tie-break by allowlist load order (manifest order), not alphabetical
    # doc_id — zero-overlap fallback must be the budgeted allowlist prefix.
    ranked = [
        chunk
        for _score, _idx, chunk in sorted(
            (
                (
                    score_corpus_chunk(chunk, query_tokens=query_tokens),
                    idx,
                    chunk,
                )
                for idx, chunk in enumerate(all_chunks)
            ),
            key=lambda item: (-item[0], item[1]),
        )
    ]
    selected: list[CorpusChunk] = []
    total = 0
    for chunk in ranked:
        size = len(chunk.text)
        # Skip chunks that do not fit the remaining budget (including individually
        # oversized ones) so later, smaller allowlisted sections can still fill
        # unused capacity. Do not break early on the first non-fit.
        if size > max_chars or total + size > max_chars:
            continue
        selected.append(chunk)
        total += size
    if not selected:
        raise HelpCorpusError(f"No allowlisted Help chunk fits max_corpus_chars ({max_chars}).")
    return tuple(selected)
