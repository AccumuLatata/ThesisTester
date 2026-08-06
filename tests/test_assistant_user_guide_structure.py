"""HC-0 structure gate: USER_GUIDE skeleton H2 titles (not Help-allowlisted yet)."""

from __future__ import annotations

import re
from pathlib import Path

from thesistester.assistant.help_corpus import HELP_CORPUS_MANIFEST, manifest_doc_ids

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

# Filled in HC-0; remaining surfaces stay explicit stubs until HC-1+.
_PURPOSE_H2 = "Purpose and honesty"
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
    assert USER_GUIDE_PATH.is_file(), "docs/USER_GUIDE.md must exist (HC-0)"
    titles = _user_guide_h2_titles()
    assert titles == list(REQUIRED_USER_GUIDE_H2S), (
        "USER_GUIDE H2 titles must match §6.1 exactly (presence, order, no extras).\n"
        f"expected={list(REQUIRED_USER_GUIDE_H2S)!r}\n"
        f"actual={titles!r}"
    )


def test_user_guide_feature_h2s_remain_explicit_stubs():
    """HC-0 stubs must stay marked so they are never mistaken for shipped how-tos."""
    bodies = _user_guide_h2_bodies()
    assert _PURPOSE_H2 in bodies
    assert _STUB_MARKER not in bodies[_PURPOSE_H2], (
        "Purpose and honesty is the HC-0 preface — not a stub placeholder"
    )
    for title in REQUIRED_USER_GUIDE_H2S:
        if title == _PURPOSE_H2:
            continue
        assert _STUB_MARKER in bodies[title], (
            f"USER_GUIDE H2 {title!r} must contain {_STUB_MARKER!r} until filled in HC-1+"
        )


def test_user_guide_not_in_help_corpus_manifest_yet():
    """HC-0 must not widen Help allowlist; user_guide lands in HC-1+."""
    assert "user_guide" not in manifest_doc_ids()
    assert all(spec.relative_path != "docs/USER_GUIDE.md" for spec in HELP_CORPUS_MANIFEST)
