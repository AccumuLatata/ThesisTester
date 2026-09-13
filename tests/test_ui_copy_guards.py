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


def _is_st_attr_call(node: ast.AST, attr: str) -> bool:
    """True for ``st.attr(...)`` or ``st.sidebar.attr(...)`` only."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != attr:
        return False
    value = node.func.value
    if isinstance(value, ast.Name) and value.id == "st":
        return True
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "sidebar"
        and isinstance(value.value, ast.Name)
        and value.value.id == "st"
    )


def _literal_str(node: ast.AST) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _call_label(call: ast.Call) -> str | None:
    if call.args:
        return _literal_str(call.args[0])
    return _kw_str(call, "label")


def _selectbox_calls(source: str, label: str) -> list[ast.Call]:
    """All ``st.selectbox`` calls whose label equals ``label`` (QI-4 H5 extract)."""
    tree = ast.parse(source)
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not _is_st_attr_call(node, "selectbox"):
            continue
        if _call_label(node) == label:
            found.append(node)
    return found


def _selectbox_call(source: str, label: str) -> ast.Call:
    """Return the unique ``st.selectbox(label, …)`` call."""
    found = _selectbox_calls(source, label)
    if not found:
        raise AssertionError(f"no st.selectbox({label!r}) in source")
    if len(found) != 1:
        raise AssertionError(f"expected exactly one st.selectbox({label!r}), got {len(found)}")
    return found[0]


def _kw_str(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg != name:
            continue
        value = _literal_str(kw.value)
        if value is None:
            raise AssertionError(f"selectbox {name}= is not a string literal")
        return value
    return None


def _caption_texts(source: str) -> list[str]:
    """Literal first-arg strings of ``st.caption(...)`` (not ``help=`` / comments)."""
    tree = ast.parse(source)
    texts: list[str] = []
    for node in ast.walk(tree):
        if not _is_st_attr_call(node, "caption") or not node.args:
            continue
        text = _literal_str(node.args[0])
        if text is not None:
            texts.append(text)
    return texts


def _joined_text(node: ast.AST) -> str | None:
    """String literal or f-string / implicit-concat constant parts (QI-05-05)."""
    literal = _literal_str(node)
    if literal is not None:
        return literal
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("{}")
            else:
                return None
        return "".join(parts)
    return None


def _first_arg_text(call: ast.Call) -> str | None:
    if not call.args:
        return None
    return _joined_text(call.args[0])


def _metric_label(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "metric":
        return None
    return _first_arg_text(call)


def _st_calls(tree: ast.AST, attr: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_st_attr_call(node, attr)
    ]


def _subheader_lineno(tree: ast.AST, title: str) -> int | None:
    for call in _st_calls(tree, "subheader"):
        if _literal_str(call.args[0]) == title if call.args else False:
            return call.lineno
    return None


def _md_h2_body(markdown: str, title: str) -> str:
    """Body of an ATX H2 through the next H2 (A-3 / QI-13-03 section bind)."""
    marker = f"## {title}\n"
    start = markdown.find(marker)
    if start < 0:
        raise AssertionError(f"missing H2 {title!r}")
    rest = markdown[start + len(marker) :]
    nxt = rest.find("\n## ")
    return rest if nxt < 0 else rest[:nxt]


_PHASE8_METRIC_LABEL = "Share of bootstrap means > 0"
_PHASE8_OLD_METRIC_LABEL = "P(mean R > 0)"
_PHASE8_PERM_SUBHEADER = "Sign-flip permutation test"
_PHASE8_GRID_SUBHEADER = "Grid-search overfit risk"
_PHASE8_INFO_NEEDLES = (
    "Diagnostic only",
    "not a significance test",
    "not proof of edge",
)
_PHASE8_CAPTION_NEEDLES = (
    "sign symmetry",
    "serial dependence",
)
_PHASE8_CELEBRATORY = (
    "statistically significant",
    "proven",
    "confirms edge",
    "has edge",
)
_VD_HEADING = "## Validation Diagnostics"
_VD_BANNER = "⚠️ Diagnostic only — not a significance test and not proof of edge."
_PHASE8_GLOSSARY_H2 = "Phase 8 validation diagnostics"


def _assert_phase8_permutation_copy(source: str) -> None:
    """AST-bind H13 permutation chrome + bootstrap metric (A-1 / A-3 class).

    File-level ``st.caption`` / ``st.info`` / label search false-greens on the
    method caption, comments, and ``help=`` — same class as QI-05-09 Policy.
    """
    tree = ast.parse(source)
    metric_labels = [
        label
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for label in (_metric_label(node),)
        if label is not None
    ]
    assert _PHASE8_OLD_METRIC_LABEL not in metric_labels, (
        f"confirmatory metric label still present: {metric_labels!r}"
    )
    assert metric_labels.count(_PHASE8_METRIC_LABEL) == 1, (
        f"expected one {_PHASE8_METRIC_LABEL!r} metric, got {metric_labels!r}"
    )

    perm_start = _subheader_lineno(tree, _PHASE8_PERM_SUBHEADER)
    perm_end = _subheader_lineno(tree, _PHASE8_GRID_SUBHEADER)
    assert perm_start is not None, f"missing st.subheader({_PHASE8_PERM_SUBHEADER!r})"
    assert perm_end is not None, f"missing st.subheader({_PHASE8_GRID_SUBHEADER!r})"
    assert perm_start < perm_end, "permutation block must precede grid-overfit"

    success = [call for call in _st_calls(tree, "success") if perm_start <= call.lineno < perm_end]
    assert success == [], (
        f"st.success still on permutation path: line {[c.lineno for c in success]}"
    )

    info_texts = [
        text
        for call in _st_calls(tree, "info")
        if perm_start <= call.lineno < perm_end
        for text in (_first_arg_text(call),)
        if text is not None
    ]
    matching_info = [t for t in info_texts if all(n in t for n in _PHASE8_INFO_NEEDLES)]
    assert matching_info, (
        f"p≤0.05 st.info missing diagnostic needles {_PHASE8_INFO_NEEDLES}: {info_texts!r}"
    )
    celebratory = [
        word for text in matching_info for word in _PHASE8_CELEBRATORY if word in text.lower()
    ]
    assert celebratory == [], f"permutation info is celebratory: {celebratory}"

    caption_texts = [
        text
        for call in _st_calls(tree, "caption")
        if perm_start <= call.lineno < perm_end
        for text in (_first_arg_text(call),)
        if text is not None
    ]
    matching_caption = [t for t in caption_texts if all(n in t for n in _PHASE8_CAPTION_NEEDLES)]
    assert matching_caption, f"H13 st.caption missing {_PHASE8_CAPTION_NEEDLES}: {caption_texts!r}"

    low_branch: list[ast.stmt] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        if not (isinstance(node.test.left, ast.Name) and node.test.left.id == "p_val"):
            continue
        if not any(isinstance(op, ast.Gt) for op in node.test.ops):
            continue
        comps = node.test.comparators
        if len(comps) != 1 or not isinstance(comps[0], ast.Constant):
            continue
        if comps[0].value != 0.05:
            continue
        low_branch = node.orelse
        break
    assert low_branch, "missing else branch of p_val > 0.05 (permutation pass path)"
    low_calls = [
        stmt.value
        for stmt in low_branch
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
    ]
    assert any(_is_st_attr_call(call, "info") for call in low_calls), (
        "p≤0.05 path must st.info (not st.success)"
    )
    assert not any(_is_st_attr_call(call, "success") for call in low_calls), (
        "p≤0.05 path must not st.success"
    )
    assert any(
        _is_st_attr_call(call, "caption")
        and (text := _first_arg_text(call))
        and all(n in text for n in _PHASE8_CAPTION_NEEDLES)
        for call in low_calls
    ), "p≤0.05 path must st.caption H13 needles (method caption is not enough)"


def _assert_validation_diagnostics_banner(source: str) -> None:
    """Banner must be the next non-empty string after the VD heading (AST list)."""
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        texts = [_literal_str(elt) for elt in node.elts]
        if _VD_HEADING not in texts:
            continue
        found = True
        idx = texts.index(_VD_HEADING)
        for text in texts[idx + 1 :]:
            if text is None:
                raise AssertionError("Validation Diagnostics banner must precede metric f-strings")
            if text == "":
                continue
            assert text == _VD_BANNER, (
                f"first line under {_VD_HEADING!r} must be banner, got {text!r}"
            )
            break
        else:
            raise AssertionError(f"no banner string after {_VD_HEADING!r}")
    assert found, f"no list containing {_VD_HEADING!r} in reporting.py"


def _assert_allow_all_policy_disclosure(source: str) -> None:
    """Two-candidate overlap recipe (docs/quality/README.md; QI-4 §3) → copy only.

    Probe observed allow_all N=2 / skips=0 vs single_position N=1 +
    overlapping_position. This guard locks widget disclosure, not engine fills.
    Caption needles are AST-bound to ``st.caption`` — a file-level search
    false-greens when ``help=`` already names overlap (QI-05-09 class).
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
    captions = _caption_texts(source)
    matching = [c for c in captions if all(n in c for n in _ALLOW_ALL_POLICY_CAPTION_NEEDLES)]
    assert matching, (
        "Policy st.caption missing H5 needles "
        f"{list(_ALLOW_ALL_POLICY_CAPTION_NEEDLES)}: {captions!r}"
    )


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


_PHASE8_GLOSSARY_NEEDLES = (
    "probability_positive",
    "P(mean R > 0)",
    "p-value (positive)",
    "p_value_positive",
    "Best − Median",
    "grid_overfit",
    "Grid-search overfit",
    "best_vs_median",
)


_WFA_OVERLAP_HELP_NEEDLES = (
    "aggregate_test_total_r",
    "fold-sum",
    "stitched equity",
)
_WFA_AGGREGATE_CAPTION_NEEDLES = (
    "aggregate_test_total_r",
    "fold-sum",
    "double-count",
    "stitched equity",
    "does not deduplicate",
)
_WFA_AGGREGATE_METRIC_LABEL = "Aggregate test total R"
_WFA_HELP_OVERCLAIM = "avoids double-counting"
_WFA_USER_GUIDE_H2 = "Validation and robustness"
_WFA_GLOSSARY_H2 = "Walk-forward / OOS diagnostics metrics"


def _assert_wfa_m9_copy(source: str) -> None:
    """QI-05-07 / M9: overlap help + caption name fold-sum; reject withholds stitch.

    Caption is AST-bound to ``st.caption`` *after* the Aggregate test total R
    metric (``st.metric`` or column ``.metric``). File-level / ``help=`` needles
    false-green — same class as QI-05-09 Policy and A-3 H12. Help must not
    restore the pre-A-5 overclaim that reject avoids double-counting.
    """
    call = _selectbox_call(source, "Overlapping OOS ownership")
    help_text = _kw_str(call, "help")
    assert help_text, "Overlapping OOS ownership selectbox must have help="
    missing_help = [n for n in _WFA_OVERLAP_HELP_NEEDLES if n not in help_text]
    assert missing_help == [], f"overlap help missing {missing_help}: {help_text!r}"
    assert _WFA_HELP_OVERCLAIM not in help_text.lower(), (
        "overlap help must not claim reject avoids double-counting "
        f"(reject withholds stitch only): {help_text!r}"
    )

    tree = ast.parse(source)
    metric_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _metric_label(node) == _WFA_AGGREGATE_METRIC_LABEL
    ]
    assert metric_lines, f"missing metric({_WFA_AGGREGATE_METRIC_LABEL!r})"

    caption_lines: list[int] = []
    matching: list[str] = []
    for node in ast.walk(tree):
        if not _is_st_attr_call(node, "caption") or not node.args:
            continue
        text = _literal_str(node.args[0])
        if text is None:
            continue
        if all(n in text for n in _WFA_AGGREGATE_CAPTION_NEEDLES):
            caption_lines.append(node.lineno)
            matching.append(text)
    assert matching, (
        f"WFA st.caption missing aggregate fold-sum needles {list(_WFA_AGGREGATE_CAPTION_NEEDLES)}"
    )
    assert min(caption_lines) > min(metric_lines), (
        "WFA st.caption must follow Aggregate test total R metric"
    )


_GRID_RANKING_HELP_NEEDLES = (
    "In-sample",
    "Does not prove",
    "Do not treat ranking",
)
_GRID_RANKING_OVERCLAIM = "best SL/TP"
_GRID_USER_GUIDE_H2 = "Grid Search"
_WFA_HEATMAP_CAPTION_NEEDLES = (
    "do not pick",
    "greenest cell",
)
_WFA_OVERFIT_SUBHEADER = "Overfitting-detection battery"
_OTF_MATRIX_SUBHEADER = "OTF filter validation matrix"
_OTF_INFO_LABEL = "Train-selected configuration"
_OTF_NOT_CONTEST = "not a contest win"


def _is_go_heatmap(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Heatmap"
    )


def _heatmap_colorscale(call: ast.Call) -> str | None:
    for kw in call.keywords:
        if kw.arg == "colorscale":
            return _literal_str(kw.value)
    return None


def _assert_grid_ranking_m10_help(source: str) -> None:
    """QI-05-08 / M10: Ranking metric help is in-sample sort, not a proven best.

    AST-bound to the Ranking metric ``st.selectbox`` ``help=``. File-level /
    comment needles false-green — same class as QI-05-09 Policy.
    """
    call = _selectbox_call(source, "Ranking metric")
    help_text = _kw_str(call, "help")
    assert help_text, "Ranking metric selectbox must have help="
    missing = [n for n in _GRID_RANKING_HELP_NEEDLES if n not in help_text]
    assert missing == [], f"Ranking help missing {missing}: {help_text!r}"
    assert _GRID_RANKING_OVERCLAIM not in help_text, (
        f"Ranking help must not restore contest 'best SL/TP': {help_text!r}"
    )


def _assert_wfa_m10_copy(source: str) -> None:
    """QI-05-08 / M10: WFA RdYlGn caption after heatmap + OTF info, no trophy.

    Caption is AST-bound to ``st.caption`` after the RdYlGn ``st.plotly_chart``
    and before Overfitting-detection battery. File-level / ``help=`` / comment
    needles false-green — same class as QI-05-09 Policy and A-5 M9. OTF
    ``st.info`` must pair train-selected with “not a contest win”; 🏆 anywhere
    on the page restores contest chrome.
    """
    tree = ast.parse(source)
    rdylgn_lines = [
        node.lineno
        for node in ast.walk(tree)
        if _is_go_heatmap(node) and _heatmap_colorscale(node) == "RdYlGn"
    ]
    assert rdylgn_lines, "missing go.Heatmap colorscale='RdYlGn' (WFA matrix)"

    plotly_after = [
        call.lineno for call in _st_calls(tree, "plotly_chart") if call.lineno >= min(rdylgn_lines)
    ]
    assert plotly_after, "missing st.plotly_chart after WFA RdYlGn heatmap"
    wfa_plotly = min(plotly_after)

    overfit_start = _subheader_lineno(tree, _WFA_OVERFIT_SUBHEADER)
    assert overfit_start is not None, f"missing st.subheader({_WFA_OVERFIT_SUBHEADER!r})"
    assert wfa_plotly < overfit_start, "WFA heatmap must precede Overfitting battery"

    matching: list[str] = []
    caption_lines: list[int] = []
    for call in _st_calls(tree, "caption"):
        text = _first_arg_text(call)
        if text is None or not all(n in text for n in _WFA_HEATMAP_CAPTION_NEEDLES):
            continue
        matching.append(text)
        caption_lines.append(call.lineno)
    assert matching, (
        f"WFA st.caption missing greenest-cell needles {list(_WFA_HEATMAP_CAPTION_NEEDLES)}"
    )
    assert min(caption_lines) > wfa_plotly, "WFA st.caption must follow RdYlGn st.plotly_chart"
    assert min(caption_lines) < overfit_start, (
        "WFA st.caption must precede Overfitting-detection battery"
    )

    otf_start = _subheader_lineno(tree, _OTF_MATRIX_SUBHEADER)
    assert otf_start is not None, f"missing st.subheader({_OTF_MATRIX_SUBHEADER!r})"
    otf_infos = [
        text
        for call in _st_calls(tree, "info")
        if call.lineno >= otf_start
        for text in (_first_arg_text(call),)
        if text is not None and _OTF_INFO_LABEL in text
    ]
    assert otf_infos, f"OTF st.info missing {_OTF_INFO_LABEL!r} after {_OTF_MATRIX_SUBHEADER!r}"
    missing_contest = [t for t in otf_infos if _OTF_NOT_CONTEST not in t]
    assert missing_contest == [], (
        f"OTF Train-selected st.info must pair {_OTF_NOT_CONTEST!r}: {missing_contest!r}"
    )
    trophy_infos = [t for t in otf_infos if "🏆" in t]
    assert trophy_infos == [], f"OTF Train-selected st.info must not use 🏆: {trophy_infos!r}"
    assert "🏆" not in source, "page 10 must not restore OTF contest trophy chrome"


def test_grid_ranking_help_is_diagnostic_not_contest():
    """QI-05-08 / M10: Ranking metric help is in-sample sort, not a proven best."""
    _assert_grid_ranking_m10_help(_read(PAGES / "8_Grid_Search.py"))


def test_wfa_heatmap_caption_and_otf_trophy_are_not_contest():
    """QI-05-08 / M10: WFA heatmap caption + no OTF trophy prefix."""
    _assert_wfa_m10_copy(_read(PAGES / "10_Validation.py"))


def test_grid_ranking_help_guard_ignores_comment_and_file_needles():
    """Comment / file-level M10 needles must not satisfy Ranking metric help."""
    fake = (
        "import streamlit as st\n"
        "# In-sample Does not prove Do not treat ranking\n"
        "st.selectbox(\n"
        '    "Ranking metric",\n'
        '    options=["expectancy_r"],\n'
        "    index=0,\n"
        '    help="Metric used to find the best SL/TP pair.",\n'
        ")\n"
    )
    try:
        _assert_grid_ranking_m10_help(fake)
    except AssertionError as exc:
        assert "missing" in str(exc) or "best SL/TP" in str(exc)
    else:
        raise AssertionError("old Ranking help must not pass via comment needles")


def test_wfa_heatmap_caption_guard_requires_st_caption_not_comment():
    """Comment / help= 'greenest' needles must not satisfy the heatmap caption."""
    fake = (
        "import plotly.graph_objects as go\n"
        "import streamlit as st\n"
        "# do not pick the greenest cell\n"
        'st.selectbox("x", options=["a"], help="do not pick the greenest cell")\n'
        "go.Heatmap(z=[[1]], colorscale='RdYlGn')\n"
        "st.plotly_chart(None)\n"
        f'st.subheader("{_WFA_OVERFIT_SUBHEADER}")\n'
        f'st.subheader("{_OTF_MATRIX_SUBHEADER}")\n'
        'st.info("**Train-selected configuration:** `x` (not a contest win).")\n'
    )
    try:
        _assert_wfa_m10_copy(fake)
    except AssertionError as exc:
        assert "st.caption" in str(exc)
    else:
        raise AssertionError("help=/comment greenest needles must not false-green st.caption")


def test_wfa_heatmap_caption_guard_requires_caption_after_rdylgn_plotly():
    """Caption before the RdYlGn chart, or after Overfitting, must fail closed."""
    select_otf = (
        "import plotly.graph_objects as go\n"
        "import streamlit as st\n"
        "go.Heatmap(z=[[1]], colorscale='RdYlGn')\n"
    )
    caption = (
        "st.caption(\n"
        '    "Diagnostic robustness surface — do not pick the greenest cell as a "\n'
        '    "production train/test length (M10)."\n'
        ")\n"
    )
    tail = (
        f'st.subheader("{_WFA_OVERFIT_SUBHEADER}")\n'
        f'st.subheader("{_OTF_MATRIX_SUBHEADER}")\n'
        'st.info("**Train-selected configuration:** `x` (not a contest win).")\n'
    )
    before_plotly = select_otf + caption + "st.plotly_chart(None)\n" + tail
    try:
        _assert_wfa_m10_copy(before_plotly)
    except AssertionError as exc:
        assert "must follow" in str(exc)
    else:
        raise AssertionError("caption before WFA plotly must not pass")

    after_overfit = (
        select_otf
        + "st.plotly_chart(None)\n"
        + f'st.subheader("{_WFA_OVERFIT_SUBHEADER}")\n'
        + caption
        + f'st.subheader("{_OTF_MATRIX_SUBHEADER}")\n'
        + 'st.info("**Train-selected configuration:** `x` (not a contest win).")\n'
    )
    try:
        _assert_wfa_m10_copy(after_overfit)
    except AssertionError as exc:
        assert "Overfitting" in str(exc)
    else:
        raise AssertionError("caption after Overfitting battery must not pass")


def test_otf_train_selected_guard_requires_st_info_not_comment():
    """File-level 'not a contest win' / leftover 🏆 must not false-green OTF info."""
    heatmap = (
        "import plotly.graph_objects as go\n"
        "import streamlit as st\n"
        "go.Heatmap(z=[[1]], colorscale='RdYlGn')\n"
        "st.plotly_chart(None)\n"
        "st.caption(\n"
        '    "Diagnostic robustness surface — do not pick the greenest cell as a "\n'
        '    "production train/test length (M10)."\n'
        ")\n"
        f'st.subheader("{_WFA_OVERFIT_SUBHEADER}")\n'
        f'st.subheader("{_OTF_MATRIX_SUBHEADER}")\n'
    )
    comment_only = heatmap + (
        "# not a contest win\n"
        'st.info("**Train-selected configuration:** `x` (selected by train_expectancy_r only).")\n'
    )
    try:
        _assert_wfa_m10_copy(comment_only)
    except AssertionError as exc:
        assert _OTF_NOT_CONTEST in str(exc)
    else:
        raise AssertionError("comment 'not a contest win' must not satisfy OTF st.info")

    trophy = heatmap + (
        'st.info("🏆 **Train-selected configuration:** `x` (not a contest win).")\n'
    )
    try:
        _assert_wfa_m10_copy(trophy)
    except AssertionError as exc:
        assert "🏆" in str(exc)
    else:
        raise AssertionError("OTF trophy prefix must fail closed")


def test_user_guide_grid_h2_names_m10_ranking():
    """USER_GUIDE Grid Search H2 (Help-allowlisted) names in-sample ranking, not greenest."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _GRID_USER_GUIDE_H2)
    missing = [
        n for n in ("In-sample sort", "not a proven", "top ranked cell", "M10") if n not in body
    ]
    assert missing == [], f"Grid Search H2 missing M10 needles {missing}"
    assert "top/greenest cell" not in body
    assert len(body) <= 4500, f"Grid Search H2 exceeds USER_GUIDE soft budget: {len(body)}"


def test_user_guide_validation_h2_names_m10_greenest_cell():
    """USER_GUIDE Validation H2 names WFA greenest-cell caveat; Notes-only must not bind."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _WFA_USER_GUIDE_H2)
    missing = [n for n in ("greenest cell", "M10") if n not in body]
    assert missing == [], f"Validation H2 missing M10 needles {missing}"
    assert len(body) <= 4500, f"Validation H2 exceeds USER_GUIDE soft budget: {len(body)}"
    fake = "## Notes\ngreenest cell M10 do not pick the greenest cell\n## Grid Search\nunrelated\n"
    try:
        _md_h2_body(fake, _WFA_USER_GUIDE_H2)
    except AssertionError as exc:
        assert "Validation" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Validation H2")


def test_wfa_overlap_help_and_aggregate_caption_name_fold_sum():
    """QI-05-07 / M9: overlap help + caption name fold-sum, not stitch-only."""
    _assert_wfa_m9_copy(_read(PAGES / "10_Validation.py"))


def test_wfa_aggregate_caption_guard_requires_st_caption_not_help_text():
    """Caption needles inside overlap help= must not satisfy the caption assert."""
    fake = (
        "import streamlit as st\n"
        "st.selectbox(\n"
        '    "Overlapping OOS ownership",\n'
        '    options=["reject", "first", "last"],\n'
        '    help="Reject withholds stitched equity. `aggregate_test_total_r` is a '
        'fold-sum and can double-count overlapping OOS trades.",\n'
        ")\n"
        'a1.metric("Aggregate test total R", "1.0")\n'
    )
    try:
        _assert_wfa_m9_copy(fake)
    except AssertionError as exc:
        assert "st.caption" in str(exc)
    else:
        raise AssertionError("help= caption needles must not false-green st.caption")


def test_wfa_aggregate_caption_guard_requires_metric_before_caption():
    """Caption without the Aggregate metric, or before it, must fail closed."""
    caption = (
        "st.caption(\n"
        '    "`aggregate_test_total_r` is a fold-sum of per-fold `test_total_r`. "\n'
        '    "Overlapping OOS windows can double-count the same trade R. "\n'
        '    "`reject` withholds stitched equity; it does not deduplicate this sum (M9)."\n'
        ")\n"
    )
    select = (
        "import streamlit as st\n"
        "st.selectbox(\n"
        '    "Overlapping OOS ownership",\n'
        '    options=["reject", "first", "last"],\n'
        '    help="Reject withholds stitched equity. `aggregate_test_total_r` is a '
        'fold-sum of `test_total_r`.",\n'
        ")\n"
    )
    try:
        _assert_wfa_m9_copy(select + caption)
    except AssertionError as exc:
        assert "metric" in str(exc)
    else:
        raise AssertionError("caption without Aggregate metric must not pass")

    reversed_order = select + caption + 'a1.metric("Aggregate test total R", "1.0")\n'
    try:
        _assert_wfa_m9_copy(reversed_order)
    except AssertionError as exc:
        assert "must follow" in str(exc)
    else:
        raise AssertionError("caption before Aggregate metric must not pass")


def test_wfa_overlap_help_guard_rejects_avoids_double_counting_overclaim():
    """Pre-A-5 'Reject avoids double-counting' must not pass with fold-sum needles."""
    fake = (
        "import streamlit as st\n"
        "st.selectbox(\n"
        '    "Overlapping OOS ownership",\n'
        '    options=["reject", "first", "last"],\n'
        '    help="Reject avoids double-counting by withholding stitched equity. '
        '`aggregate_test_total_r` is a fold-sum of `test_total_r`.",\n'
        ")\n"
        'a1.metric("Aggregate test total R", "1.0")\n'
        "st.caption(\n"
        '    "`aggregate_test_total_r` is a fold-sum of per-fold `test_total_r`. "\n'
        '    "Overlapping OOS windows can double-count the same trade R. "\n'
        '    "`reject` withholds stitched equity; it does not deduplicate this sum (M9)."\n'
        ")\n"
    )
    try:
        _assert_wfa_m9_copy(fake)
    except AssertionError as exc:
        assert "avoids double-counting" in str(exc)
    else:
        raise AssertionError("reject-avoids-double-counting help must fail closed")


def test_user_guide_validation_h2_names_m9_fold_sum():
    """USER_GUIDE Validation H2 (Help-allowlisted) names fold-sum + reject stitch-only."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _WFA_USER_GUIDE_H2)
    missing = [
        n for n in ("aggregate_test_total_r", "fold-sum", "reject", "stitch only") if n not in body
    ]
    assert missing == [], f"Validation H2 missing M9 needles {missing}"
    assert len(body) <= 4500, f"Validation H2 exceeds USER_GUIDE soft budget: {len(body)}"


def test_metrics_glossary_wfa_h2_names_m9_fold_sum():
    """Glossary Walk-forward H2 names fold-sum; Notes-only needles must not bind."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "METRICS_GLOSSARY.md"), _WFA_GLOSSARY_H2)
    missing = [n for n in ("aggregate_test_total_r", "fold-sum", "double-count") if n not in body]
    assert missing == [], f"Walk-forward H2 missing M9 needles {missing}"
    fake = (
        "## Notes\n"
        "aggregate_test_total_r fold-sum double-count does not deduplicate\n"
        "## Grid Search directional metrics\n"
        "unrelated\n"
    )
    try:
        _md_h2_body(fake, _WFA_GLOSSARY_H2)
    except AssertionError as exc:
        assert "Walk-forward" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Walk-forward H2")


def test_phase8_permutation_copy_is_diagnostic_not_confirmatory():
    """QI-05-05 / H13: no success chrome on permutation p; no confirmatory P(mean R > 0)."""
    _assert_phase8_permutation_copy(_read(PAGES / "10_Validation.py"))
    _assert_validation_diagnostics_banner(_read(REPO_ROOT / "thesistester" / "reporting.py"))


def test_metrics_glossary_has_phase8_diagnostic_rows():
    """QI-13-03 / F-4: Phase 8 rows live under the dedicated H2, not Notes-only."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "METRICS_GLOSSARY.md"), _PHASE8_GLOSSARY_H2)
    missing = [needle for needle in _PHASE8_GLOSSARY_NEEDLES if needle not in body]
    assert missing == [], f"Phase 8 H2 missing needles {missing}"


def test_phase8_copy_guard_ignores_comment_help_and_method_caption():
    """File-level / method-caption / help= needles must not false-green H13."""
    fake = (
        "import streamlit as st\n"
        "col5 = st\n"
        'st.subheader("Sign-flip permutation test")\n'
        "# Share of bootstrap means > 0\n"
        "# Diagnostic only — not a significance test and not proof of edge.\n"
        "st.caption(\n"
        '    "Null hypothesis: trade signs are random around zero. "\n'
        '    "One-sided p-value = fraction of permuted means >= observed mean R."\n'
        ")\n"
        'st.selectbox("x", options=["a"], help="sign symmetry serial dependence")\n'
        "p_val = 0.01\n"
        "if p_val is not None:\n"
        "    if p_val > 0.10:\n"
        '        st.info("high")\n'
        "    elif p_val > 0.05:\n"
        '        st.info("mid")\n'
        "    else:\n"
        "        st.success(\n"
        '            "p = 0.01 — Observed mean R is in the tail. "\n'
        '            "Diagnostic only — not a significance test and not proof of edge."\n'
        "        )\n"
        'st.subheader("Grid-search overfit risk")\n'
        'col5.metric("P(mean R > 0)", "50%")\n'
    )
    try:
        _assert_phase8_permutation_copy(fake)
    except AssertionError as exc:
        assert "st.success" in str(exc) or "metric" in str(exc) or "st.info" in str(exc)
    else:
        raise AssertionError("comment/method-caption/success path must not pass H13 guard")


def test_phase8_copy_guard_requires_h13_caption_on_low_p_path():
    """Method caption + diagnostic st.info without the H13 caption must fail."""
    fake = (
        "import streamlit as st\n"
        "col5 = st\n"
        'st.subheader("Sign-flip permutation test")\n'
        "st.caption(\n"
        '    "Null hypothesis: trade signs are random around zero."\n'
        ")\n"
        'col5.metric("Share of bootstrap means > 0", "50%")\n'
        "p_val = 0.01\n"
        "if p_val is not None:\n"
        "    if p_val > 0.10:\n"
        '        st.info("high")\n'
        "    elif p_val > 0.05:\n"
        '        st.info("mid")\n'
        "    else:\n"
        "        st.info(\n"
        '            "p = 0.01 — Observed mean R is in the tail of the "\n'
        '            "sign-flip null. Diagnostic only — not a significance test "\n'
        '            "and not proof of edge."\n'
        "        )\n"
        'st.subheader("Grid-search overfit risk")\n'
    )
    try:
        _assert_phase8_permutation_copy(fake)
    except AssertionError as exc:
        assert "st.caption" in str(exc) or "H13" in str(exc)
    else:
        raise AssertionError("method caption must not satisfy p≤0.05 H13 caption")


def test_phase8_glossary_guard_ignores_notes_needles():
    """Needles in Notes / other H2s must not satisfy the Phase 8 row bind."""
    fake = (
        "## Notes\n"
        "probability_positive P(mean R > 0) p-value (positive) p_value_positive "
        "Best − Median grid_overfit Grid-search overfit best_vs_median\n"
        "## Grid Search directional metrics\n"
        "unrelated\n"
    )
    try:
        _md_h2_body(fake, _PHASE8_GLOSSARY_H2)
    except AssertionError as exc:
        assert "Phase 8" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Phase 8 H2")


def test_validation_diagnostics_banner_guard_rejects_late_or_comment_banner():
    """Banner after metric f-strings / heading-only list must fail closed."""
    late = (
        "lines = [\n"
        '    "## Validation Diagnostics",\n'
        '    f"- P(mean R > 0): {x}",\n'
        '    "⚠️ Diagnostic only — not a significance test and not proof of edge.",\n'
        "]\n"
    )
    try:
        _assert_validation_diagnostics_banner(late)
    except AssertionError as exc:
        assert "banner" in str(exc) or "f-string" in str(exc)
    else:
        raise AssertionError("banner after metric f-string must not pass")

    heading_only = 'lines = ["## Validation Diagnostics", ""]\n'
    try:
        _assert_validation_diagnostics_banner(heading_only)
    except AssertionError as exc:
        assert "banner" in str(exc)
    else:
        raise AssertionError("heading without banner must not pass")


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
    leaked = [n for n in _ALLOW_ALL_POLICY_HELP_NEEDLES if n in ranking_help]
    assert leaked == [], f"Ranking metric help must not carry Policy H5 copy: {leaked}"


def test_policy_help_guard_ignores_ranking_help_and_file_needles():
    """QI-05-09: Ranking ``help=`` / comment needles must not false-green Policy."""
    fake = (
        "import streamlit as st\n"
        "st.selectbox(\n"
        '    "Policy",\n'
        '    options=["allow_all", "single_position", "single_direction", "single_setup"],\n'
        "    index=0,\n"
        ")\n"
        "st.selectbox(\n"
        '    "Ranking metric",\n'
        '    options=["expectancy_r"],\n'
        "    index=0,\n"
        '    help="allow_all overlapping signals independently skip table is empty by design",\n'
        ")\n"
        "# allow_all independent fills empty by design\n"
        'st.caption("`allow_all` independent fills empty by design")\n'
    )
    try:
        _assert_allow_all_policy_disclosure(fake)
    except AssertionError as exc:
        assert "help=" in str(exc)
    else:
        raise AssertionError("Policy without help= must not pass via Ranking/file needles")


def test_policy_caption_guard_requires_st_caption_not_help_text():
    """Caption needles inside Policy help= must not satisfy the caption assert."""
    fake = (
        "import streamlit as st\n"
        "st.selectbox(\n"
        '    "Policy",\n'
        '    options=["allow_all", "single_position", "single_direction", "single_setup"],\n'
        "    index=0,\n"
        '    help="Default allow_all counts overlapping signals independently; '
        'skip table is empty by design independent fills",\n'
        ")\n"
    )
    try:
        _assert_allow_all_policy_disclosure(fake)
    except AssertionError as exc:
        assert "st.caption" in str(exc)
    else:
        raise AssertionError("help= caption needles must not false-green st.caption")


def test_policy_help_guard_rejects_second_undisclosed_policy_selectbox():
    """Exactly one Policy widget — a bare second selectbox must not hide behind the first."""
    fake = (
        "import streamlit as st\n"
        "st.selectbox(\n"
        '    "Policy",\n'
        '    options=["allow_all", "single_position", "single_direction", "single_setup"],\n'
        "    index=0,\n"
        '    help="Default allow_all counts overlapping signals independently; '
        'skip table is empty by design",\n'
        ")\n"
        'st.caption("`allow_all` independent fills empty by design")\n'
        "st.selectbox(\n"
        '    "Policy",\n'
        '    options=["allow_all", "single_position", "single_direction", "single_setup"],\n'
        "    index=0,\n"
        ")\n"
    )
    try:
        _assert_allow_all_policy_disclosure(fake)
    except AssertionError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("second Policy selectbox without help must fail uniqueness")


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
