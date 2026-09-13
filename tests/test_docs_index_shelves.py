"""F-3 / QI-13-05: docs index shelves — no orphans, no dual-list.

Link checks resolve destinations from the source file. Basename-only matching
and whole-file / later-section mentions are not enough (same class of
false-green as README Phase 4 later-token mentions).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
INDEX = DOCS / "README.md"
QUALITY_README = DOCS / "quality" / "README.md"

# Skip images (`![alt](url)`). Destination is the first token (title stripped).
LINK_RE = re.compile(r"(?<!!)\[(?:[^\]]*)\]\(([^)]+)\)")

# Frozen QI-0…QI-15 report set. Deleting a file must fail (not shrink the glob).
EXPECTED_QI_REPORTS = (
    "QI-00_BASELINE.md",
    "QI-01_DATA_INGESTION.md",
    "QI-02_LEVELS_ENGINE_PIT.md",
    "QI-03_SETUP_SIGNALS_OTF.md",
    "QI-04_EXECUTION_ENGINE.md",
    "QI-05_ANALYTICS_VALIDATION_BATTERIES.md",
    "QI-06_HEADLESS_FACADE.md",
    "QI-07_STUDY_SYSTEM.md",
    "QI-08_TRADE_JOURNAL.md",
    "QI-09_RESEARCH_ASSISTANT_VOICE.md",
    "QI-10_UI_SESSION_STATE.md",
    "QI-11_TEST_SUITE_QUALITY.md",
    "QI-12_TOOLING_CI_SECURITY.md",
    "QI-13_DOCS_CONTRACTS_DRIFT.md",
    "QI-14_PERFORMANCE_ENVELOPE.md",
    "QI-15_SYNTHESIS.md",
)

# Completed series that QI-13-05 dual-listed in Primary and Contracts.
CONTRACT_ONLY = (
    "DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md",
    "TRADE_JOURNAL_IMPLEMENTATION_PLAN.md",
    "JOURNAL_TO_STUDY_IMPLEMENTATION_PLAN.md",
)

COMBO_NAME = "CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md"
ARCHIVE_ROLLOUT = "docs/archive/anchor_confluence_regression_safe_plan.md"
STALE_ROLLOUT = "docs/anchor_confluence_regression_safe_plan.md"


def _link_destinations(text: str) -> list[str]:
    dests: list[str] = []
    for raw in LINK_RE.findall(text):
        token = raw.strip().split("#", 1)[0].strip()
        if not token or token[0] in "\"'":
            continue
        dest = token.split()[0].strip("<>")
        if dest:
            dests.append(dest)
    return dests


def _resolved_files(text: str, source: Path) -> set[Path]:
    """Local markdown targets that exist on disk, resolved from *source*."""
    found: set[Path] = set()
    base = source.parent
    for dest in _link_destinations(text):
        if dest.startswith(("http://", "https://", "mailto:")):
            continue
        path = (base / dest).resolve()
        if path.is_file():
            found.add(path)
    return found


def _has_stale_rollout_path(text: str) -> bool:
    return STALE_ROLLOUT in text.replace(ARCHIVE_ROLLOUT, "")


def _section(text: str, start_h2: str, end_h2: str, *, source_name: str) -> str:
    if not start_h2.startswith("## ") or not end_h2.startswith("## "):
        raise AssertionError(f"headings must be H2 prefixes: {start_h2!r} / {end_h2!r}")
    lines = text.splitlines()
    start_i: int | None = None
    end_i: int | None = None
    for i, line in enumerate(lines):
        if start_i is None and line.startswith(start_h2):
            start_i = i
            continue
        if start_i is not None and line.startswith(end_h2):
            end_i = i
            break
    if start_i is None:
        raise AssertionError(f"{source_name} missing heading {start_h2!r}")
    if end_i is None:
        raise AssertionError(f"{source_name} missing heading {end_h2!r} after {start_h2!r}")
    return "\n".join(lines[start_i + 1 : end_i])


def test_top_level_docs_are_indexed() -> None:
    index = INDEX.read_text(encoding="utf-8")
    indexed = _resolved_files(index, INDEX)
    living = {p.resolve() for p in DOCS.glob("*.md") if p.name != "README.md"}
    orphans = sorted(p.name for p in living if p not in indexed)
    assert orphans == [], f"docs/README.md omitted living/contract files: {orphans}"


def test_quality_reports_are_listed() -> None:
    index = INDEX.read_text(encoding="utf-8")
    quality_readme = QUALITY_README.resolve()
    assert quality_readme in _resolved_files(index, INDEX), (
        "docs/README.md must link docs/quality/README.md"
    )

    on_disk = tuple(sorted(p.name for p in (DOCS / "quality").glob("QI-*.md")))
    assert on_disk == EXPECTED_QI_REPORTS, (
        f"docs/quality/ QI-*.md set drifted: {on_disk}"
    )

    quality_index = QUALITY_README.read_text(encoding="utf-8")
    reports = _section(
        quality_index, "## Reports", "## Report naming", source_name=QUALITY_README.name
    )
    linked = {p.name for p in _resolved_files(reports, QUALITY_README)}
    missing = [name for name in EXPECTED_QI_REPORTS if name not in linked]
    assert missing == [], f"docs/quality/README.md Reports omitted: {missing}"

    findings = (DOCS / "quality" / "findings.csv").resolve()
    assert findings in _resolved_files(reports, QUALITY_README)
    header = findings.read_text(encoding="utf-8").splitlines()[0]
    assert "disposition" in header, "Reports table claims QR disposition columns"


def test_da_tj_js_live_in_exactly_one_shelf() -> None:
    text = INDEX.read_text(encoding="utf-8")
    primary = _resolved_files(
        _section(text, "## Primary", "## Normative", source_name=INDEX.name), INDEX
    )
    contracts = _resolved_files(
        _section(text, "## Normative", "## Research", source_name=INDEX.name), INDEX
    )
    overlap = sorted(p.name for p in primary & contracts)
    assert not overlap, f"dual-listed in Primary and Contracts: {overlap}"
    for name in CONTRACT_ONLY:
        path = (DOCS / name).resolve()
        assert path.is_file(), f"missing contract file {name}"
        assert path not in primary, f"{name} must not stay in Primary"
        assert path in contracts, f"{name} must remain in Contracts"


def test_confluence_combo_is_contract_complete() -> None:
    text = INDEX.read_text(encoding="utf-8")
    contracts_src = _section(text, "## Normative", "## Research", source_name=INDEX.name)
    primary = _resolved_files(
        _section(text, "## Primary", "## Normative", source_name=INDEX.name), INDEX
    )
    contracts = _resolved_files(contracts_src, INDEX)
    combo_path = (DOCS / COMBO_NAME).resolve()
    assert combo_path in contracts, "CONFLUENCE_COMBO must be indexed as contract-complete"
    assert combo_path not in primary, "CONFLUENCE_COMBO must not also sit in Primary"

    combo_bullets = [ln for ln in contracts_src.splitlines() if COMBO_NAME in ln]
    assert combo_bullets, "Contracts shelf missing CONFLUENCE_COMBO bullet"
    assert all("successor of" not in ln.lower() for ln in combo_bullets), (
        "CONFLUENCE_COMBO is the retrospective companion, not the archived-rollout successor"
    )
    assert any("Phase 6" in ln and "implemented" in ln for ln in combo_bullets)

    combo = combo_path.read_text(encoding="utf-8")
    status = next((ln for ln in combo.splitlines() if ln.startswith("**Status:**")), "")
    assert status and "Phase 6" in status and "implemented" in status.lower()
    shelf = next((ln for ln in combo.splitlines() if ln.startswith("**Shelf:**")), "")
    assert "contract-complete" in shelf

    archive_rollout = (DOCS / "archive" / "anchor_confluence_regression_safe_plan.md").resolve()
    assert archive_rollout in _resolved_files(combo, combo_path)
    assert not _has_stale_rollout_path(combo)


def test_archive_and_research_readmes_list_their_files() -> None:
    for subdir in ("archive", "research"):
        folder = DOCS / subdir
        readme = folder / "README.md"
        indexed = _resolved_files(readme.read_text(encoding="utf-8"), readme)
        orphans = sorted(
            p.name
            for p in folder.glob("*.md")
            if p.name != "README.md" and p.resolve() not in indexed
        )
        assert orphans == [], f"docs/{subdir}/README.md omitted: {orphans}"


def test_section_parser_requires_end_heading() -> None:
    with pytest.raises(AssertionError, match="missing heading"):
        _section("## Primary\n- [x](x.md)\n", "## Primary", "## Normative", source_name="x")


def test_resolved_links_ignore_same_basename_in_another_folder() -> None:
    """`../QI-01_DATA_INGESTION.md` from quality/ does not exist — basename must not pass."""
    fake = "[report](../QI-01_DATA_INGESTION.md)"
    assert not any(
        p.name == "QI-01_DATA_INGESTION.md" for p in _resolved_files(fake, QUALITY_README)
    )
    real = "[report](QI-01_DATA_INGESTION.md)"
    assert (DOCS / "quality" / "QI-01_DATA_INGESTION.md").resolve() in _resolved_files(
        real, QUALITY_README
    )


def test_quality_listing_ignores_mentions_outside_reports_section() -> None:
    fake = (
        "## Reports (QI-0…QI-15)\n"
        "| [`QI-00_BASELINE.md`](QI-00_BASELINE.md) |\n"
        "## Report naming\n"
        "See [`QI-15_SYNTHESIS.md`](QI-15_SYNTHESIS.md) later.\n"
    )
    section = _section(fake, "## Reports", "## Report naming", source_name="quality")
    linked = set(_link_destinations(section))
    assert "QI-00_BASELINE.md" in linked
    assert "QI-15_SYNTHESIS.md" not in linked


def test_stale_rollout_path_detector_ignores_archive_prefix() -> None:
    assert not _has_stale_rollout_path(f"See {ARCHIVE_ROLLOUT}")
    assert _has_stale_rollout_path(f"See {STALE_ROLLOUT} and {ARCHIVE_ROLLOUT}")


def test_dual_list_detector_flags_da_in_both_shelves() -> None:
    fake = (
        "## Primary (living)\n"
        f"- [{CONTRACT_ONLY[0]}]({CONTRACT_ONLY[0]})\n"
        "## Normative contracts\n"
        f"- [{CONTRACT_ONLY[0]}]({CONTRACT_ONLY[0]})\n"
        "## Research\n"
    )
    primary = _resolved_files(
        _section(fake, "## Primary", "## Normative", source_name="x"), INDEX
    )
    contracts = _resolved_files(
        _section(fake, "## Normative", "## Research", source_name="x"), INDEX
    )
    assert (DOCS / CONTRACT_ONLY[0]).resolve() in primary & contracts
