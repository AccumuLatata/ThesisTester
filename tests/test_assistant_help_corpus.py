"""RQ-0 Help corpus allowlist and loader tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from thesistester.assistant.help_corpus import (
    HELP_CORPUS_MANIFEST,
    PREFACE_SECTION,
    HelpCorpusError,
    build_registry_digest,
    get_corpus_doc_spec,
    load_allowlisted_corpus,
    load_corpus_chunks,
    manifest_doc_ids,
    resolve_corpus_path,
    select_help_corpus_chunks,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_manifest_doc_ids_match_section_7_1_freeze():
    assert manifest_doc_ids() == (
        "readme",
        "metrics",
        "research_methodology",
        "architecture",
        "assumptions",
        "otf",
        "user_guide",
        "registry",
    )
    by_id = {spec.doc_id: spec for spec in HELP_CORPUS_MANIFEST}
    assert by_id["readme"].mode == "whole_file"
    assert by_id["metrics"].mode == "whole_file"
    assert by_id["research_methodology"].mode == "whole_file"
    assert by_id["architecture"].mode == "sections"
    assert by_id["assumptions"].mode == "sections"
    assert by_id["otf"].mode == "sections"
    assert by_id["user_guide"].mode == "sections"
    assert by_id["user_guide"].relative_path == "docs/USER_GUIDE.md"
    assert by_id["registry"].mode == "digest"
    assert "`st.session_state` contract (current)" in by_id["architecture"].sections
    assert "§10 — Regression safety" not in by_id["otf"].sections
    assert "Packaging and tooling boundary (R9)" not in by_id["architecture"].sections
    assert by_id["user_guide"].sections == frozenset(
        {
            "Purpose and honesty",
            "Classic workflow overview",
            "Data",
            "Levels",
            "Setup Builder",
            "Signals",
            "Backtest",
            "Exposure policy",
            "Intrabar resolution",
            "Exit management (break-even and trailing)",
            "Session close and entry cutoff",
            "Grid Search",
            "Time Analysis",
            "Focus vs Admit",
            "Validation and robustness",
            "Report Export",
            "Research Bundles",
            "Portfolio",
            "Research Assistant (draft, Discuss, Help)",
            "Research mode on classic pages",
            "Research Study Runner (headless)",
            "Studies viewer (read-only)",
            "Study Observatory",
            "When to use Help vs Discuss results",
        }
    )
    assert "Voice agent (VA-series — complete; default off)" in by_id["assumptions"].sections
    assert "Voice agent (VA-series — proposed, not shipped)" not in by_id["assumptions"].sections


def test_user_guide_rejects_unknown_h2_and_accepts_allowlisted_h2():
    with pytest.raises(HelpCorpusError, match="not allowlisted"):
        load_corpus_chunks(
            "user_guide",
            repo_root=REPO_ROOT,
            sections=["Not A Real USER_GUIDE Section"],
        )
    chunks = load_corpus_chunks(
        "user_guide",
        repo_root=REPO_ROOT,
        sections=[
            "Data",
            "Grid Search",
            "Research Assistant (draft, Discuss, Help)",
            "When to use Help vs Discuss results",
        ],
    )
    assert {chunk.section for chunk in chunks} == {
        "Data",
        "Grid Search",
        "Research Assistant (draft, Discuss, Help)",
        "When to use Help vs Discuss results",
    }
    by_section = {chunk.section: chunk.text for chunk in chunks}
    assert "CSV format profile" in by_section["Data"]
    assert "Ranking metric" in by_section["Grid Search"]
    assert "Confirm validated RunSpec" in by_section["Research Assistant (draft, Discuss, Help)"]
    assert "Help / how it works" in by_section["When to use Help vs Discuss results"]


def test_resolve_corpus_path_rejects_traversal_and_agent_guide():
    with pytest.raises(HelpCorpusError, match=r"\.\."):
        resolve_corpus_path("../README.md", repo_root=REPO_ROOT)
    with pytest.raises(HelpCorpusError, match="excluded"):
        resolve_corpus_path("docs/AGENT_GUIDE.md", repo_root=REPO_ROOT)
    with pytest.raises(HelpCorpusError, match="not allowlisted"):
        resolve_corpus_path("docs/ENGINEERING_ROADMAP.md", repo_root=REPO_ROOT)
    path = resolve_corpus_path("README.md", repo_root=REPO_ROOT)
    assert path == (REPO_ROOT / "README.md").resolve()


def test_resolve_corpus_path_rejects_symlink_to_excluded_doc(tmp_path):
    """Allowlisted path must not resolve through a symlink to excluded content."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "AGENT_GUIDE.md").write_text("# secret\n", encoding="utf-8")
    (tmp_path / "README.md").symlink_to(tmp_path / "docs" / "AGENT_GUIDE.md")
    with pytest.raises(HelpCorpusError, match="excluded|allowlisted location"):
        resolve_corpus_path("README.md", repo_root=tmp_path)


def test_architecture_rejects_non_allowlisted_h2_and_accepts_frozen_h2():
    with pytest.raises(HelpCorpusError, match="not allowlisted"):
        load_corpus_chunks(
            "architecture",
            repo_root=REPO_ROOT,
            sections=["Packaging and tooling boundary (R9)"],
        )
    chunks = load_corpus_chunks(
        "architecture",
        repo_root=REPO_ROOT,
        sections=["AI Research Assistant contract boundary (AIA-0)"],
    )
    assert len(chunks) == 1
    assert chunks[0].doc_id == "architecture"
    assert chunks[0].section == "AI Research Assistant contract boundary (AIA-0)"
    assert "Research Assistant" in chunks[0].text


def test_otf_rejects_regression_safety_section():
    with pytest.raises(HelpCorpusError, match="not allowlisted"):
        load_corpus_chunks(
            "otf",
            repo_root=REPO_ROOT,
            sections=["§10 — Regression safety"],
        )
    chunks = load_corpus_chunks("otf", repo_root=REPO_ROOT, sections=["Purpose"])
    assert chunks[0].section == "Purpose"


def test_whole_file_includes_preface_and_h2s():
    chunks = load_corpus_chunks("readme", repo_root=REPO_ROOT)
    sections = {chunk.section for chunk in chunks}
    assert PREFACE_SECTION in sections or "Run locally" in sections
    assert "Documentation" in sections


def test_whole_file_preface_includes_h1_before_first_h2():
    """§7.1 rule 5: __preface__ is content before the first H2, including H1."""
    chunks = load_corpus_chunks("readme", repo_root=REPO_ROOT)
    by_section = {chunk.section: chunk.text for chunk in chunks}
    assert PREFACE_SECTION in by_section
    preface = by_section[PREFACE_SECTION]
    assert "# ThesisTester" in preface
    assert "intraday strategy research" in preface
    assert "## Run locally" not in preface


def test_h2_chunk_stops_at_later_h1():
    """§7.1 rule 4: H2 body ends at the next H2 or higher heading."""
    from thesistester.assistant.help_corpus import _parse_atx_sections

    parsed = _parse_atx_sections("## Sec A\nbody a\n# Later H1\nbody h1\n## Sec B\nbody b\n")
    by_title = {title: text for _level, title, text in parsed}
    assert "Later H1" not in by_title["Sec A"]
    assert "body h1" not in by_title["Sec A"]
    assert "body a" in by_title["Sec A"]
    assert "body b" in by_title["Sec B"]


def test_section_mode_omits_preface():
    chunks = load_corpus_chunks("architecture", repo_root=REPO_ROOT)
    assert all(chunk.section != PREFACE_SECTION for chunk in chunks)
    assert "`st.session_state` contract (current)" in {c.section for c in chunks}


def test_load_allowlisted_corpus_excludes_registry_and_respects_max_chars():
    chunks = load_allowlisted_corpus(repo_root=REPO_ROOT, max_chars=50_000)
    assert chunks
    assert all(chunk.doc_id != "registry" for chunk in chunks)
    assert sum(len(chunk.text) for chunk in chunks) <= 50_000
    capped = load_allowlisted_corpus(repo_root=REPO_ROOT, max_chars=2_000)
    assert capped
    assert sum(len(chunk.text) for chunk in capped) <= 2_000
    with pytest.raises(HelpCorpusError, match="exceeds max_corpus_chars"):
        load_allowlisted_corpus(repo_root=REPO_ROOT, max_chars=1)


def test_unknown_doc_id_fails_closed():
    with pytest.raises(HelpCorpusError, match="Unknown Help corpus doc_id"):
        get_corpus_doc_spec("agent_guide")


def test_build_registry_digest_shape():
    digest = build_registry_digest()
    assert digest
    for row in digest:
        assert "capability_id" in row
        assert "status" in row
        assert "confirmation" in row
        assert set(row) <= {
            "capability_id",
            "status",
            "public_symbol",
            "confirmation",
            "limitation",
        }


def test_select_help_corpus_chunks_respects_budget_and_allowlist():
    chunks = select_help_corpus_chunks(
        "How does grid ranking and expectancy_r work?",
        repo_root=REPO_ROOT,
        max_chars=8_000,
    )
    assert chunks
    assert sum(len(chunk.text) for chunk in chunks) <= 8_000
    assert all(chunk.doc_id in set(manifest_doc_ids()) - {"registry"} for chunk in chunks)
    # Grid/metric queries should prefer glossary/architecture when scored.
    assert any(chunk.doc_id in {"metrics", "architecture", "assumptions"} for chunk in chunks)
    # Oversized individual chunks are skipped; tiny budgets that fit nothing fail.
    with pytest.raises(HelpCorpusError, match="No allowlisted Help chunk fits"):
        select_help_corpus_chunks("ranking", repo_root=REPO_ROOT, max_chars=1)


def test_select_help_corpus_chunks_fills_budget_after_nonfitting_rank(monkeypatch):
    """A non-fitting mid-rank chunk must not block later smaller chunks."""
    from thesistester.assistant.help_corpus import CorpusChunk

    fake = (
        CorpusChunk(doc_id="metrics", section="a", text="x" * 80),
        CorpusChunk(doc_id="metrics", section="b", text="y" * 60),
        CorpusChunk(doc_id="architecture", section="c", text="z" * 15),
    )
    monkeypatch.setattr(
        "thesistester.assistant.help_corpus.load_allowlisted_corpus",
        lambda **kwargs: fake,
    )
    monkeypatch.setattr(
        "thesistester.assistant.help_corpus.score_corpus_chunk",
        lambda chunk, query_tokens: {"a": 3, "b": 2, "c": 1}[chunk.section],
    )
    selected = select_help_corpus_chunks(
        "ranking",
        repo_root=REPO_ROOT,
        max_chars=100,
    )
    assert [chunk.section for chunk in selected] == ["a", "c"]
    assert sum(len(chunk.text) for chunk in selected) == 95


def test_select_help_corpus_chunks_zero_overlap_preserves_allowlist_order(monkeypatch):
    """Zero lexical overlap must pack the allowlist prefix, not alpha doc_id order."""
    from thesistester.assistant.help_corpus import CorpusChunk

    fake = (
        CorpusChunk(doc_id="readme", section="r", text="readme-chunk "),
        CorpusChunk(doc_id="metrics", section="m", text="metrics-chunk"),
        CorpusChunk(doc_id="architecture", section="a", text="arch-chunk "),
    )
    monkeypatch.setattr(
        "thesistester.assistant.help_corpus.load_allowlisted_corpus",
        lambda **kwargs: fake,
    )
    monkeypatch.setattr(
        "thesistester.assistant.help_corpus.score_corpus_chunk",
        lambda chunk, query_tokens: 0,
    )
    selected = select_help_corpus_chunks(
        "zzzz-no-overlap-token",
        repo_root=REPO_ROOT,
        max_chars=26,
    )
    # allowlist order: readme → metrics → architecture (not alpha: architecture first)
    assert [chunk.doc_id for chunk in selected] == ["readme", "metrics"]
    assert "architecture" not in {chunk.doc_id for chunk in selected}
