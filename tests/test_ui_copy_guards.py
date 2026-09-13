"""Regression guards for stale or incorrect Streamlit UI copy."""

from __future__ import annotations

import ast
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGES = REPO_ROOT / "pages"
APP = REPO_ROOT / "app.py"

# QI-04-02 / QI-05-09 (H5): Policy help must name overlap + empty skip table.
# AST-only — a file-level `help=` regex false-matches Grid Ranking metric (QI-05-09).
_ALLOW_ALL_POLICY_HELP_NEEDLES = (
    "allow_all",
    "overlapping signals independently",
    "skip table is empty by design",
)
_ALLOW_ALL_POLICY_CAPTION_NEEDLES = (
    "allow_all",
    "independent fills",
    "empty by design",
)

# Phase 4 bullet through the next top-level Phase 5 bullet (not the later 3c
# four-rule block, which also names `3c` as a standalone token).
_README_PHASE4_RE = re.compile(
    r"^- \*\*Phase 4\b.*?(?=^- \*\*Phase 5\b)",
    flags=re.MULTILINE | re.DOTALL,
)
# "N trigger types — `tok`, `tok` — exposed"
_README_TRIGGER_LIST_RE = re.compile(
    r"trigger types\s+[—–-]\s*(.*?)\s+[—–-]\s+exposed",
    flags=re.DOTALL,
)


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _selectbox_call(source: str, label: str) -> ast.Call:
    """Return the `st.selectbox(label, …)` call; QI-4 H5 probe used this extract."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "selectbox"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and first.value == label:
            return node
    raise AssertionError(f"no st.selectbox({label!r}) in source")


def _kw_str(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg != name:
            continue
        try:
            value = ast.literal_eval(kw.value)
        except (ValueError, TypeError) as exc:
            raise AssertionError(f"selectbox {name}= is not a string literal") from exc
        if not isinstance(value, str):
            raise AssertionError(f"selectbox {name}= must be a str, got {type(value)}")
        return value
    return None


def _assert_allow_all_policy_disclosure(source: str) -> None:
    """Two-candidate overlap recipe (docs/quality/README.md; QI-4 §3) → copy only.

    Probe observed allow_all N=2 / skips=0 vs single_position N=1 +
    overlapping_position. This guard locks widget disclosure, not engine fills.
    """
    call = _selectbox_call(source, "Policy")
    options = ast.literal_eval(call.args[1]) if len(call.args) > 1 else None
    if options is None:
        for kw in call.keywords:
            if kw.arg == "options":
                options = ast.literal_eval(kw.value)
                break
    assert options, "Policy selectbox has no options"
    assert options[0] == "allow_all", "AH §2.1 default must stay allow_all (index 0)"
    index_val = None
    for kw in call.keywords:
        if kw.arg == "index":
            index_val = ast.literal_eval(kw.value)
    assert index_val == 0, "Policy default index must stay 0 (allow_all)"
    help_text = _kw_str(call, "help")
    assert help_text, "Policy selectbox must have help= (QI-04-02 / QI-05-09)"
    missing = [n for n in _ALLOW_ALL_POLICY_HELP_NEEDLES if n not in help_text]
    assert missing == [], f"Policy help missing {missing}: {help_text!r}"
    missing_cap = [n for n in _ALLOW_ALL_POLICY_CAPTION_NEEDLES if n not in source]
    assert missing_cap == [], f"Policy caption missing {missing_cap}"


def _phase4_listed_triggers(readme: str) -> set[str]:
    """Exact backticked tokens in the Phase 4 "trigger types — … — exposed" list."""
    phase4_match = _README_PHASE4_RE.search(readme)
    assert phase4_match is not None, "README.md has no Phase 4 bullet"
    list_match = _README_TRIGGER_LIST_RE.search(phase4_match.group(0))
    assert list_match is not None, "README Phase 4 has no backticked trigger-types list"
    return set(re.findall(r"`([^`]+)`", list_match.group(1)))


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


def test_readme_phase4_trigger_list_covers_valid_triggers():
    """QI-13-02 / QR F-2: Help-allowlisted README lists every VALID_TRIGGERS token.

    Parse the Phase 4 enumerated list, not any later `` `token` `` mention.
    Whole-file / whole-bullet search still passes if Phase 4 drops `3c` from
    the list but keeps "including `3c`" or the four-rule block.
    """
    from thesistester.engine.signals import VALID_TRIGGERS

    readme = _read(REPO_ROOT / "README.md")
    assert "five trigger types" not in readme
    listed = _phase4_listed_triggers(readme)
    missing = sorted(token for token in VALID_TRIGGERS if token not in listed)
    assert missing == [], f"README Phase 4 omitted VALID_TRIGGERS {missing}"

    # F-2: 3c four-rule / 8-variant block stays (separate bullet, not the list).
    assert "**4 rules (long):**" in readme
    assert "Arrival candle must touch or pass through the key level." in readme
    assert "Reversal candle must close above the arrival candle high." in readme


def test_backtest_policy_help_discloses_allow_all_overlap():
    """QI-04-02 / A-1: Backtest Policy help+caption name H5 overlap + empty skips."""
    _assert_allow_all_policy_disclosure(_read(PAGES / "7_Backtest.py"))


def test_grid_policy_help_discloses_allow_all_overlap():
    """QI-05-09 / A-1: Grid Policy help+caption match Backtest (AST, not file regex)."""
    _assert_allow_all_policy_disclosure(_read(PAGES / "8_Grid_Search.py"))
    ranking = _selectbox_call(_read(PAGES / "8_Grid_Search.py"), "Ranking metric")
    ranking_help = _kw_str(ranking, "help")
    assert ranking_help is not None
    assert "skip table is empty by design" not in ranking_help


def test_readme_phase4_list_parser_ignores_later_token_mentions():
    """List ⊇ VALID_TRIGGERS; later `` `3c` `` / `` `fade` `` must not hide a drop."""
    fake = (
        "- **Phase 4 (x):** seven trigger types — `touch`, `reject`, `break`, "
        "`reclaim`, `fade`, `continuation` — exposed via Signals. "
        "Trigger timeframe applies to all triggers including `3c`. "
        "For non-base simple triggers (`touch`, `reject`, `break`, `reclaim`, "
        "`fade`, `continuation`), timestamps stay base-aligned.\n"
        "- **Phase 5 (y):**\n"
        "- **3c trigger — authoritative 4-rule / 8-variant model:**\n"
        "  The `3c` trigger. Variants: `3c_long`.\n"
    )
    listed = _phase4_listed_triggers(fake)
    assert "3c" not in listed
    assert "`3c`" in fake  # whole-file `` `3c` `` would false-pass
