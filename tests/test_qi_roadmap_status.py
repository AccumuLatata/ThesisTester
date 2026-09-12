"""F-1 / QI-13-01: ROADMAP QI row names every slice report on disk."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "docs" / "ENGINEERING_ROADMAP.md"
QI_DIR = REPO_ROOT / "docs" / "quality"


def _qi_status_row(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("| Quality investigation (code + application) |"):
            return line
    raise AssertionError("ENGINEERING_ROADMAP.md has no Quality investigation status row")


def test_roadmap_qi_row_names_each_slice_report() -> None:
    reports = sorted(p.name for p in QI_DIR.glob("QI-*.md"))
    assert reports, "expected docs/quality/QI-*.md reports"
    row = _qi_status_row(ROADMAP.read_text(encoding="utf-8"))
    missing = [name for name in reports if name not in row]
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
