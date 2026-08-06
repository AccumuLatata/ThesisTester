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

_H2_RE = re.compile(r"^##\s+(.*\S)\s*$", re.MULTILINE)


def _user_guide_h2_titles() -> list[str]:
    text = USER_GUIDE_PATH.read_text(encoding="utf-8")
    return _H2_RE.findall(text)


def test_user_guide_exists_with_required_h2_skeleton():
    assert USER_GUIDE_PATH.is_file(), "docs/USER_GUIDE.md must exist (HC-0)"
    titles = _user_guide_h2_titles()
    missing = [title for title in REQUIRED_USER_GUIDE_H2S if title not in titles]
    assert missing == [], f"USER_GUIDE missing required H2 titles: {missing}"
    # Order matches §6.1 so later content PRs fill without reshuffling structure.
    positions = [titles.index(title) for title in REQUIRED_USER_GUIDE_H2S]
    assert positions == sorted(positions), "USER_GUIDE required H2s must keep §6.1 order"


def test_user_guide_not_in_help_corpus_manifest_yet():
    """HC-0 must not widen Help allowlist; user_guide lands in HC-1+."""
    assert "user_guide" not in manifest_doc_ids()
    assert all(spec.relative_path != "docs/USER_GUIDE.md" for spec in HELP_CORPUS_MANIFEST)
