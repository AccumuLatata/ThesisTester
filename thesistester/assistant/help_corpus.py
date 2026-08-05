"""Frozen Help corpus allowlist and pure loaders (RQ-0).

Encodes ``docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`` §7.1 exactly.
No orchestrator wiring, network I/O, or OpenAI calls.
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
    """Resolve an allowlisted relative path under ``repo_root``; reject traversal."""
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
    root = Path(repo_root).resolve()
    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HelpCorpusError(f"Corpus path escapes repository root: {relative_path!r}") from exc
    allowlisted = {
        spec.relative_path for spec in HELP_CORPUS_MANIFEST if spec.relative_path is not None
    }
    if cleaned not in allowlisted:
        raise HelpCorpusError(f"Corpus path is not allowlisted: {relative_path!r}")
    return candidate


def _parse_atx_sections(markdown: str) -> list[tuple[int, str, str]]:
    """Return ``(level, section_title, body_including_heading)`` chunks.

    H2 sections include nested H3+ until the next H2 or higher. Preface before
    the first heading is returned as level 0 with ``PREFACE_SECTION``.
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

    first_idx = entries[0][0]
    if first_idx > 0:
        preface = "".join(lines[:first_idx]).strip()
        if preface:
            chunks.append((0, PREFACE_SECTION, preface))

    # Build H2-oriented chunks (or whole-file H2s). Nested deeper headings stay
    # inside the enclosing H2 body.
    h2_entries = [(i, level, title) for i, level, title in entries if level == 2]
    if not h2_entries:
        # No H2s: expose only preface (if any); do not invent section keys.
        return chunks

    for position, (start_idx, _level, title) in enumerate(h2_entries):
        end_idx = len(lines)
        if position + 1 < len(h2_entries):
            end_idx = h2_entries[position + 1][0]
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
                if len(chunk.text) > max_chars:
                    # Never attach a single chunk larger than the budget.
                    continue
                if total + len(chunk.text) > max_chars:
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
