"""F-3 / QI-13-05: docs index shelves — no orphans, no dual-list."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
INDEX = DOCS / "README.md"
QUALITY_README = DOCS / "quality" / "README.md"

LINK_RE = re.compile(r"\]\(([^)]+)\)")

# Completed series that QI-13-05 dual-listed in Primary and Contracts.
CONTRACT_ONLY = (
    "DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md",
    "TRADE_JOURNAL_IMPLEMENTATION_PLAN.md",
    "JOURNAL_TO_STUDY_IMPLEMENTATION_PLAN.md",
)


def _link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for raw in LINK_RE.findall(text):
        target = raw.split("#", 1)[0].strip()
        if target:
            targets.append(target)
    return targets


def _linked_basenames(text: str) -> set[str]:
    return {Path(t).name for t in _link_targets(text)}


def _section(text: str, start_h2: str, end_h2: str) -> str:
    lines = text.splitlines()
    start: int | None = None
    out: list[str] = []
    for line in lines:
        if line.startswith(start_h2):
            start = 0
            continue
        if start is not None and line.startswith("## ") and line.startswith(end_h2):
            break
        if start is not None:
            out.append(line)
    if start is None:
        raise AssertionError(f"{INDEX.name} missing heading {start_h2!r}")
    return "\n".join(out)


def test_top_level_docs_are_indexed_once() -> None:
    index = INDEX.read_text(encoding="utf-8")
    linked = _linked_basenames(index)
    orphans = sorted(
        p.name for p in DOCS.glob("*.md") if p.name != "README.md" and p.name not in linked
    )
    assert orphans == [], f"docs/README.md omitted living/contract files: {orphans}"


def test_quality_reports_are_listed() -> None:
    index = INDEX.read_text(encoding="utf-8")
    assert any(
        t.rstrip("/") in {"quality/README.md", "./quality/README.md"}
        or Path(t).as_posix() == "quality/README.md"
        for t in _link_targets(index)
    ), "docs/README.md must link quality/README.md"

    quality_index = QUALITY_README.read_text(encoding="utf-8")
    linked = _linked_basenames(quality_index)
    reports = sorted(p.name for p in (DOCS / "quality").glob("QI-*.md"))
    assert reports, "expected docs/quality/QI-*.md reports"
    missing = [name for name in reports if name not in linked]
    assert missing == [], f"docs/quality/README.md omitted reports: {missing}"
    assert "findings.csv" in linked


def test_da_tj_js_live_in_exactly_one_shelf() -> None:
    text = INDEX.read_text(encoding="utf-8")
    primary = _linked_basenames(_section(text, "## Primary", "## Normative"))
    contracts = _linked_basenames(_section(text, "## Normative", "## Research"))
    overlap = primary & contracts
    assert not overlap, f"dual-listed in Primary and Contracts: {sorted(overlap)}"
    for name in CONTRACT_ONLY:
        assert name not in primary, f"{name} must not stay in Primary"
        assert name in contracts, f"{name} must remain in Contracts"


def test_confluence_combo_is_contract_complete() -> None:
    text = INDEX.read_text(encoding="utf-8")
    primary = _linked_basenames(_section(text, "## Primary", "## Normative"))
    contracts = _linked_basenames(_section(text, "## Normative", "## Research"))
    name = "CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md"
    assert name in contracts, "CONFLUENCE_COMBO must be indexed as contract-complete"
    assert name not in primary, "CONFLUENCE_COMBO must not also sit in Primary"

    combo = (DOCS / name).read_text(encoding="utf-8")
    assert "archive/anchor_confluence_regression_safe_plan.md" in combo
    assert "docs/anchor_confluence_regression_safe_plan.md" not in combo.replace(
        "docs/archive/anchor_confluence_regression_safe_plan.md", ""
    )


def test_archive_and_research_readmes_list_their_files() -> None:
    for subdir in ("archive", "research"):
        folder = DOCS / subdir
        readme = (folder / "README.md").read_text(encoding="utf-8")
        linked = _linked_basenames(readme)
        orphans = sorted(
            p.name for p in folder.glob("*.md") if p.name != "README.md" and p.name not in linked
        )
        assert orphans == [], f"docs/{subdir}/README.md omitted: {orphans}"
