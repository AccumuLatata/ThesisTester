"""B-10 / QI-12-07: import-linter contract file and C10 page-scoped gate."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORTLINTER = ROOT / ".importlinter"
STUDIES_PAGE = ROOT / "pages" / "15_Studies.py"

REQUIRED_CONTRACT_IDS = (
    "c1-preview-no-execute",
    "c2-viewer-independence",
    "c3-observatory-independence",
    "c4-launch-no-viewer-execute",
    "c5-admit-followup-independence",
    "c7-journal-no-engine-core",
    "c8-library-streamlit-allowlist",
    "c9-sim-core-no-admission",
)


def test_importlinter_declares_qi15_contracts():
    text = IMPORTLINTER.read_text(encoding="utf-8")
    assert "root_package = thesistester" in text
    assert "include_external_packages = True" in text
    assert "allow_indirect_imports = True" in text
    assert "expand → cli → cli_study" in text or "expand -> cli -> cli_study" in text
    for contract_id in REQUIRED_CONTRACT_IDS:
        assert f"[importlinter:contract:{contract_id}]" in text, contract_id
    # C6 is a call-ban; C10 is page-scoped (not a library source module).
    assert "c6-" not in text
    assert "C10" in text
    assert "pages/15_Studies.py" in text
    assert "FORMAT_PROFILE_LABELS" in text


def test_c10_studies_page_does_not_import_builder_labels():
    """QI-15 C10 / R17: page binds loader labels; stale builder must not brick it."""
    page = STUDIES_PAGE.read_text(encoding="utf-8")
    assert "from thesistester.study.builder import (" in page
    builder_import = page.split("from thesistester.study.builder import (")[1].split(")")[0]
    assert "FORMAT_PROFILE_LABELS" not in builder_import
    assert "normalize_builder_format_profile" not in builder_import
    assert "INGESTION_MODE_PRIMARY" not in builder_import
    assert "WIDGET_KEY_INGESTION_MODE" not in builder_import
    assert "from thesistester.data import loader as _data_loader" in page
    assert "Do not import FORMAT_PROFILE_LABELS" in page
