"""F-1 / QI-13-01: ROADMAP QI row names every slice report on disk."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "docs" / "ENGINEERING_ROADMAP.md"
QI_PLAN = REPO_ROOT / "docs" / "QUALITY_INVESTIGATION_PLAN.md"
QR_PLAN = REPO_ROOT / "docs" / "QUALITY_REMEDIATION_PLAN.md"
QI_DIR = REPO_ROOT / "docs" / "quality"


def _qi_status_row(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("| Quality investigation (code + application) |"):
            return line
    raise AssertionError("ENGINEERING_ROADMAP.md has no Quality investigation status row")


def _section_83_slice_rows(text: str) -> list[str]:
    start = None
    for i, line in enumerate(text.splitlines()):
        if line.startswith("### 8.3 Status tracker"):
            start = i
            break
    if start is None:
        raise AssertionError("QUALITY_INVESTIGATION_PLAN.md has no §8.3 Status tracker")
    rows: list[str] = []
    for line in text.splitlines()[start:]:
        if line.startswith("| QI-"):
            rows.append(line)
        elif rows and not line.startswith("|"):
            break
    return rows


def test_roadmap_qi_row_names_each_slice_report() -> None:
    reports = sorted(p.name for p in QI_DIR.glob("QI-*.md"))
    assert reports, "expected docs/quality/QI-*.md reports"
    row = _qi_status_row(ROADMAP.read_text(encoding="utf-8"))
    missing = [name for name in reports if f"docs/quality/{name}" not in row]
    assert missing == [], f"ROADMAP QI row omitted {missing}"
    assert "Completed" in row
    assert "CI red since" not in row
    assert "Not started" not in row


def test_roadmap_qr_row_is_in_progress() -> None:
    text = ROADMAP.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln.startswith("| Quality remediation (QR) |")]
    assert rows, "ENGINEERING_ROADMAP.md has no Quality remediation status row"
    assert "In progress" in rows[0]
    assert "QUALITY_REMEDIATION_PLAN.md" in rows[0]


def test_qi_plan_tracker_marks_every_slice_completed() -> None:
    rows = _section_83_slice_rows(QI_PLAN.read_text(encoding="utf-8"))
    assert len(rows) == 16, f"expected 16 QI-0…QI-15 tracker rows, got {len(rows)}"
    stale = [row for row in rows if "Not started" in row]
    assert stale == [], f"§8.3 still has Not started: {stale}"
    incomplete = [row for row in rows if "Completed" not in row]
    assert incomplete == [], f"§8.3 rows missing Completed: {incomplete}"


def test_qr_f1_recipe_keeps_blocking_after_g1() -> None:
    f1 = next(
        (ln for ln in QR_PLAN.read_text(encoding="utf-8").splitlines() if ln.startswith("| F-1 |")),
        "",
    )
    assert f1, "QUALITY_REMEDIATION_PLAN.md has no F-1 recipe row"
    assert "merge is not blocked until required checks" not in f1
    assert "blocking on red" in f1
