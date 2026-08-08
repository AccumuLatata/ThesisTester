"""Regression guards for stale or incorrect Streamlit UI copy."""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGES = REPO_ROOT / "pages"
APP = REPO_ROOT / "app.py"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_home_workflow_puts_levels_before_setup():
    text = _read(APP)
    levels_pos = text.index("Compute levels")
    setup_pos = text.index("Configure a setup")
    assert levels_pos < setup_pos
    assert "Research Assistant" in text
    assert "Portfolio" in text
    assert "Research Bundles" in text
    assert "OTF" in text
    assert "MES" in text or "MNQ" in text


def test_sidebar_page_order_files_exist():
    assert (PAGES / "2_Levels.py").is_file()
    assert (PAGES / "3_Setup_Builder.py").is_file()
    assert not (PAGES / "5_Levels.py").exists()
    assert not (PAGES / "2_Setup_Builder.py").exists()


def test_backtest_help_uses_3c_not_confirm_3bar():
    text = _read(PAGES / "7_Backtest.py")
    assert "confirm_3bar" not in text
    assert "filled 3c entries" in text
    assert "selected Intrabar resolution model" in text


def test_grid_same_bar_help_defers_to_intrabar_model():
    text = _read(PAGES / "8_Grid_Search.py")
    assert "selected Intrabar resolution model" in text
    assert "Uses SL-first pessimistic rule when both are reachable in the same bar." not in text


def test_validation_has_no_stale_r22_parallel_claim():
    text = _read(PAGES / "10_Validation.py")
    assert "R22 parallel acceleration is not yet available" not in text
    assert "no parallel acceleration is available" in text
    assert "Overfitting-detection battery" in text
    assert "Price-series noise test" in text
    assert "Parameter sensitivity (one-at-a-time)" in text


def test_research_bundles_import_preview_matches_export_artifacts():
    text = _read(PAGES / "12_Research_Bundles.py")
    for artifact in (
        "Overfitting diagnostics",
        "Parameter sensitivity",
        "Portfolio",
    ):
        assert text.count(f'"Artifact": "{artifact}"') >= 2
    assert "Setup Builder" in text
    assert "Grid Search" in text
    assert "Validation" in text


def test_signals_confluence_labels_match_setup_builder():
    signals = _read(PAGES / "6_Signals.py")
    setup = _read(PAGES / "3_Setup_Builder.py")
    assert '"Global cluster"' in signals
    assert '"Anchor-based rules"' in signals
    assert "Global Cluster" not in signals
    assert "Anchor Rules / User Anchor" not in signals
    assert "Global cluster" in setup
    assert "Anchor-based rules" in setup


def test_no_user_facing_milestone_titles_on_pages():
    forbidden = (
        "Lower-timeframe R12 replay",
        "Exit management (R13)",
        "Trade review (R20 replay-lite)",
        "R15 overfitting-detection battery",
        "R16 price-series noise test",
        "R19 parameter sensitivity",
        "Run completeness checklist",
    )
    for path in sorted(PAGES.glob("*.py")):
        text = _read(path)
        for snippet in forbidden:
            assert snippet not in text, f"{path.name} still contains {snippet!r}"


def test_report_export_uses_session_artifacts_checklist():
    text = _read(PAGES / "11_Report_Export.py")
    assert "Session artifacts checklist" in text
    assert "optional diagnostics" in text


def test_assistant_page_is_discuss_first_without_duplicate_nav_strip():
    """Research Assistant relies on Streamlit nav; no Open-research-pages strip."""
    text = _read(PAGES / "14_Research_Assistant.py")
    assert "Open research pages" not in text
    assert "st.page_link(" not in text
    assert "st.segmented_control(" in text
    assert 'Advanced: draft, runs & compare"' in text or "Advanced: draft, runs & compare" in text
    assert "Debug: raw JSON & conversation audit" in text
    assert "Assistant chat" in text
    assert "Discuss results" in text
