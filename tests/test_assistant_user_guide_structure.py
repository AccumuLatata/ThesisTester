"""USER_GUIDE structure gate: §6.1 H2 skeleton + HC-1 filled vs remaining stubs."""

from __future__ import annotations

import re
from pathlib import Path

from thesistester.assistant.help_corpus import HELP_CORPUS_MANIFEST, get_corpus_doc_spec

REPO_ROOT = Path(__file__).resolve().parents[1]
USER_GUIDE_PATH = REPO_ROOT / "docs" / "USER_GUIDE.md"

# Exact H2 titles from docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md §6.1.
REQUIRED_USER_GUIDE_H2S = (
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
)

# HC-1 filled + allowlisted (must match RQ §7.1.4 / HELP_CORPUS_MANIFEST).
HC1_FILLED_H2S = (
    "Purpose and honesty",
    "Classic workflow overview",
    "Data",
    "Levels",
    "Setup Builder",
    "Signals",
    "Backtest",
)

_STUB_MARKER = "_Stub (HC-0)._"
_H2_RE = re.compile(r"^##\s+(.*\S)\s*$", re.MULTILINE)


def _user_guide_h2_titles() -> list[str]:
    text = USER_GUIDE_PATH.read_text(encoding="utf-8")
    return _H2_RE.findall(text)


def _user_guide_h2_bodies() -> dict[str, str]:
    """Map each H2 title to the markdown body until the next H2 (or EOF)."""
    text = USER_GUIDE_PATH.read_text(encoding="utf-8")
    matches = list(_H2_RE.finditer(text))
    bodies: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        bodies[title] = text[start:end]
    return bodies


def test_user_guide_exists_with_exact_h2_skeleton():
    """§6.1 freeze: exact H2 set and order — no extras, no omissions."""
    assert USER_GUIDE_PATH.is_file(), "docs/USER_GUIDE.md must exist"
    titles = _user_guide_h2_titles()
    assert titles == list(REQUIRED_USER_GUIDE_H2S), (
        "USER_GUIDE H2 titles must match §6.1 exactly (presence, order, no extras).\n"
        f"expected={list(REQUIRED_USER_GUIDE_H2S)!r}\n"
        f"actual={titles!r}"
    )


def test_user_guide_hc1_sections_filled_remaining_stubs():
    """HC-1 how-tos are real prose; HC-2/HC-3 surfaces stay explicit stubs."""
    bodies = _user_guide_h2_bodies()
    for title in HC1_FILLED_H2S:
        assert _STUB_MARKER not in bodies[title], (
            f"USER_GUIDE H2 {title!r} must be filled (no {_STUB_MARKER!r}) after HC-1"
        )
        assert len(bodies[title].strip()) > 80, f"USER_GUIDE H2 {title!r} looks empty"
    for title in REQUIRED_USER_GUIDE_H2S:
        if title in HC1_FILLED_H2S:
            continue
        assert _STUB_MARKER in bodies[title], (
            f"USER_GUIDE H2 {title!r} must remain {_STUB_MARKER!r} until HC-2/HC-3"
        )


def test_user_guide_manifest_matches_hc1_filled_sections_only():
    """Allowlist includes only filled HC-1 H2s — never stub Grid→Assistant titles."""
    spec = get_corpus_doc_spec("user_guide")
    assert spec.relative_path == "docs/USER_GUIDE.md"
    assert spec.mode == "sections"
    assert spec.sections == frozenset(HC1_FILLED_H2S)
    assert all(
        entry.doc_id != "user_guide" or entry.sections == frozenset(HC1_FILLED_H2S)
        for entry in HELP_CORPUS_MANIFEST
    )
