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


# QI-04-10 / A-20 (M8): trade-table caption names the pnl_points gross alias.
_PNL_POINTS_CAPTION_NEEDLES = (
    "pnl_points",
    "gross alias",
    "gross_pnl_points",
    "net R",
)
_TRADE_TABLE_DISPLAY_COL_CANDIDATES = (
    "trade_id",
    "signal_id",
    "trigger",
    "direction",
    "entry_timestamp",
    "entry_price",
    "entry_model",
    "exit_timestamp",
    "exit_price",
    "exit_reason",
    "stop_price",
    "target_price",
    "stop_loss_ticks",
    "take_profit_ticks",
    "gross_pnl_points",
    "gross_pnl_currency",
    "commission_cost",
    "slippage_cost",
    "net_pnl_currency",
    "pnl_points",
    "pnl_currency",
    "r_multiple",
    "bars_held",
    "zone_low",
    "zone_high",
    "level_count",
    "level_names",
    "setup_name",
    "mae_points",
    "mfe_points",
)
_BACKTEST_USER_GUIDE_H2 = "Backtest"


def _trade_table_subheader_lineno(tree: ast.AST) -> int:
    """Earliest ``Trade table`` subheader (source order, not ``ast.walk``)."""
    lines = [
        call.lineno
        for call in _st_calls(tree, "subheader")
        if call.args and _literal_str(call.args[0]) == "Trade table"
    ]
    if not lines:
        raise AssertionError("missing st.subheader('Trade table')")
    return min(lines)


def _trade_table_display_cols_assignment(
    tree: ast.AST, trade_at: int
) -> tuple[int, tuple[str, ...]]:
    """Earliest ``display_cols`` list-comp after Trade table (source order)."""
    found: list[tuple[int, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or node.lineno < trade_at:
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "display_cols" for target in node.targets
        ):
            continue
        value = node.value
        if not isinstance(value, ast.ListComp) or not value.generators:
            raise AssertionError("display_cols is not a list comprehension")
        candidates = value.generators[0].iter
        if not isinstance(candidates, ast.List):
            raise AssertionError("display_cols candidates are not a list literal")
        cols: list[str] = []
        for elt in candidates.elts:
            text = _literal_str(elt)
            if text is None:
                raise AssertionError("display_cols candidate is not a string literal")
            cols.append(text)
        found.append((node.lineno, tuple(cols)))
    if not found:
        raise AssertionError("display_cols assignment not found after Trade table")
    found.sort(key=lambda item: item[0])
    return found[0]


def _fake_trade_table_display_cols() -> str:
    return (
        "display_cols = [c for c in [\n"
        + ",\n".join(f'    "{col}"' for col in _TRADE_TABLE_DISPLAY_COL_CANDIDATES)
        + "\n] if True]\n"
    )


def _fake_pnl_points_caption() -> str:
    return (
        "st.caption(\n"
        '    "`pnl_points` is the gross alias of `gross_pnl_points`. KPIs use net R."\n'
        ")\n"
    )


def _assert_backtest_pnl_points_caption(source: str) -> None:
    """AST-bind QI-04-10 caption between ``Trade table`` and ``display_cols``.

    File-level / ``help=`` / comments false-green (A-1 / A-5 class). A matching
    caption before the Trade table subheader or after ``display_cols`` fails
    closed. An earlier page-level match must not hide a window caption.
    """
    tree = ast.parse(source)
    trade_at = _trade_table_subheader_lineno(tree)
    cols_at, cols = _trade_table_display_cols_assignment(tree, trade_at)
    matching: list[tuple[int, str]] = []
    in_window: list[tuple[int, str]] = []
    for call in _st_calls(tree, "caption"):
        text = _first_arg_text(call)
        if text is None:
            continue
        if all(needle in text for needle in _PNL_POINTS_CAPTION_NEEDLES):
            matching.append((call.lineno, text))
            if trade_at < call.lineno < cols_at:
                in_window.append((call.lineno, text))
    if not matching:
        raise AssertionError(f"Trade table st.caption missing {_PNL_POINTS_CAPTION_NEEDLES}")
    if not in_window:
        raise AssertionError(
            "pnl_points st.caption must follow Trade table subheader (before display_cols)"
        )
    assert cols == _TRADE_TABLE_DISPLAY_COL_CANDIDATES


def test_backtest_trade_table_captions_pnl_points_gross_alias():
    """QI-04-10 / A-20: Trade table caption names gross alias; columns unchanged."""
    _assert_backtest_pnl_points_caption(_read(PAGES / "7_Backtest.py"))


def test_backtest_pnl_points_caption_guard_requires_st_caption_not_help():
    """Comment / help= needles must not satisfy the Trade table caption."""
    fake = (
        "import streamlit as st\n"
        'st.subheader("Trade table")\n'
        "st.selectbox(\n"
        '    "Policy",\n'
        '    options=["allow_all"],\n'
        '    help="pnl_points is the gross alias of gross_pnl_points; KPIs use net R",\n'
        ")\n"
        "# pnl_points gross alias of gross_pnl_points net R\n" + _fake_trade_table_display_cols()
    )
    try:
        _assert_backtest_pnl_points_caption(fake)
    except AssertionError as exc:
        assert "st.caption" in str(exc)
    else:
        raise AssertionError("help=/comment pnl_points needles must not false-green st.caption")


def test_backtest_pnl_points_caption_guard_requires_caption_after_subheader():
    """A matching caption before Trade table must not bind."""
    before = (
        _fake_pnl_points_caption()
        + 'st.subheader("Trade table")\n'
        + _fake_trade_table_display_cols()
    )
    try:
        _assert_backtest_pnl_points_caption(before)
    except AssertionError as exc:
        assert "must follow" in str(exc)
    else:
        raise AssertionError("caption before Trade table subheader must not pass")


def test_backtest_pnl_points_caption_guard_requires_caption_before_display_cols():
    """A matching caption after display_cols must not bind as the Trade table caption."""
    after = (
        'st.subheader("Trade table")\n'
        + _fake_trade_table_display_cols()
        + _fake_pnl_points_caption()
    )
    try:
        _assert_backtest_pnl_points_caption(after)
    except AssertionError as exc:
        assert "must follow" in str(exc) and "display_cols" in str(exc)
    else:
        raise AssertionError("caption after display_cols must not bind as Trade table caption")


def test_backtest_pnl_points_caption_guard_ignores_earlier_matching_caption():
    """A page-level matching caption must not hide the Trade table window caption."""
    source = (
        _fake_pnl_points_caption()
        + 'st.subheader("Trade table")\n'
        + _fake_pnl_points_caption()
        + _fake_trade_table_display_cols()
    )
    _assert_backtest_pnl_points_caption(source)


def test_user_guide_backtest_h2_names_pnl_points_gross_alias():
    """QI-04-10 / A-20: USER_GUIDE Backtest H2 names the trade-table alias."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _BACKTEST_USER_GUIDE_H2)
    body_cf = body.casefold()
    missing = [n for n in _PNL_POINTS_CAPTION_NEEDLES if n.casefold() not in body_cf]
    assert missing == [], f"Backtest H2 missing A-20 needles {missing}"
    assert len(body) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Backtest H2 exceeds USER_GUIDE soft budget: {len(body)}"
    )
    fake = (
        "## Notes\n"
        "| Trade table `pnl_points` | Gross alias of `gross_pnl_points`. KPIs use net R. |\n"
        "## Grid Search\nunrelated\n"
    )
    try:
        _md_h2_body(fake, _BACKTEST_USER_GUIDE_H2)
    except AssertionError as exc:
        assert "Backtest" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Backtest H2")

    empty_then_notes = (
        "## Backtest\n"
        "unrelated backtest copy without the alias contract\n"
        "## Notes\n"
        "| Trade table `pnl_points` | Gross alias of `gross_pnl_points`. KPIs use net R. |\n"
        "## Grid Search\nunrelated\n"
    )
    leaked = [
        n
        for n in _PNL_POINTS_CAPTION_NEEDLES
        if n.casefold() in _md_h2_body(empty_then_notes, _BACKTEST_USER_GUIDE_H2).casefold()
    ]
    assert leaked == [], f"Notes-only needles must not bind as Backtest H2: {leaked}"


# QI-10-04 / A-21: Validation one-liner on KPI pages; Data captions the 400 MB cap.
_DIAGNOSTIC_NOT_PROOF = "Diagnostic only — not proof of edge."
_A21_KPI_PAGES = (
    "7_Backtest.py",
    "8_Grid_Search.py",
    "9_Time_Analysis.py",
    "12_Research_Bundles.py",
)
_DATA_WEBSOCKET_CAP_NEEDLES = (
    "MessageSizeError",
    "400 MB",
    "websocket",
    "maxMessageSize",
)


def _is_direct_st_attr_call(node: ast.AST, attr: str) -> bool:
    """True for ``st.attr(...)`` only — not ``st.sidebar.attr``."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
    )


def _module_title_chrome_captions(source: str) -> list[ast.Call]:
    """Module-level ``st.caption`` calls immediately after ``st.title``.

    Stops at the first non-caption statement so helper / later captions cannot
    bind (A-20 window class). ``st.sidebar.caption`` is ignored.
    """
    tree = ast.parse(source)
    chrome: list[ast.Call] = []
    collecting = False
    saw_title = False
    for stmt in tree.body:
        if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
            if collecting:
                break
            continue
        call = stmt.value
        if _is_direct_st_attr_call(call, "title"):
            saw_title = True
            chrome = []
            collecting = True
            continue
        if collecting and _is_direct_st_attr_call(call, "caption"):
            chrome.append(call)
            continue
        if collecting:
            break
    if not saw_title:
        raise AssertionError("missing module-level st.title")
    return chrome


def _assert_title_caption_contains(source: str, *, needle: str) -> None:
    """AST-bind ``needle`` to a title-chrome ``st.caption``.

    File-level / ``help=`` / comments / later helper captions false-green
    (A-1 / A-20 class).
    """
    matching = [
        call
        for call in _module_title_chrome_captions(source)
        if (text := _first_arg_text(call)) is not None and needle in text
    ]
    if not matching:
        raise AssertionError(f"st.caption missing {needle!r}")


def _assert_data_websocket_cap_caption(source: str) -> None:
    matching = []
    for call in _module_title_chrome_captions(source):
        text = _first_arg_text(call)
        if text is None:
            continue
        if all(needle in text for needle in _DATA_WEBSOCKET_CAP_NEEDLES):
            matching.append(call)
    if not matching:
        raise AssertionError(f"Data st.caption missing {_DATA_WEBSOCKET_CAP_NEEDLES}")


def test_kpi_pages_reuse_validation_diagnostic_not_proof():
    """QI-10-04 / A-21: Backtest / Grid / Time / Bundles reuse Validation one-liner."""
    for name in _A21_KPI_PAGES:
        source = _read(PAGES / name)
        _assert_title_caption_contains(source, needle=_DIAGNOSTIC_NOT_PROOF)
        chrome = _module_title_chrome_captions(source)
        assert chrome, f"{name} missing title-chrome st.caption"
        first = _first_arg_text(chrome[0])
        assert first == _DIAGNOSTIC_NOT_PROOF, f"{name} first chrome caption {first!r}"
    _assert_title_caption_contains(_read(PAGES / "10_Validation.py"), needle=_DIAGNOSTIC_NOT_PROOF)


def test_diagnostic_not_proof_guard_requires_st_caption_not_help():
    """Comment / help= needles must not satisfy the diagnostic caption."""
    fake = (
        "import streamlit as st\n"
        'st.title("Backtest")\n'
        "st.selectbox(\n"
        '    "Policy",\n'
        f'    options=["allow_all"],\n'
        f'    help="{_DIAGNOSTIC_NOT_PROOF}",\n'
        ")\n"
        f"# {_DIAGNOSTIC_NOT_PROOF}\n"
    )
    try:
        _assert_title_caption_contains(fake, needle=_DIAGNOSTIC_NOT_PROOF)
    except AssertionError as exc:
        assert "st.caption" in str(exc)
    else:
        raise AssertionError("help=/comment diagnostic needles must not false-green st.caption")


def test_diagnostic_not_proof_guard_requires_title_chrome_caption():
    """Caption before title, after an intervening call, or only in a helper must fail."""
    before = (
        f'import streamlit as st\nst.caption("{_DIAGNOSTIC_NOT_PROOF}")\nst.title("Backtest")\n'
    )
    after = (
        "import streamlit as st\n"
        'st.title("Backtest")\n'
        "bootstrap()\n"
        f'st.caption("{_DIAGNOSTIC_NOT_PROOF}")\n'
    )
    helper = (
        "import streamlit as st\n"
        'st.title("Backtest")\n'
        "def _later():\n"
        f'    st.caption("{_DIAGNOSTIC_NOT_PROOF}")\n'
    )
    for fake in (before, after, helper):
        try:
            _assert_title_caption_contains(fake, needle=_DIAGNOSTIC_NOT_PROOF)
        except AssertionError as exc:
            assert "st.caption" in str(exc)
        else:
            raise AssertionError(
                "non-chrome diagnostic caption must not false-green title-chrome bind"
            )


def test_data_page_captions_400mb_websocket_cap():
    """QI-10-04 / A-21: Data captions the 400 MB websocket cap (cap unchanged)."""
    _assert_data_websocket_cap_caption(_read(PAGES / "1_Data.py"))


def test_data_websocket_cap_guard_requires_st_caption_not_help():
    """Comment / help= 400 MB needles must not satisfy the Data caption."""
    fake = (
        "import streamlit as st\n"
        'st.title("Data")\n'
        "st.selectbox(\n"
        '    "Instrument",\n'
        '    options=["ES"],\n'
        '    help="MessageSizeError is the 400 MB websocket maxMessageSize cap",\n'
        ")\n"
        "# MessageSizeError 400 MB websocket maxMessageSize\n"
    )
    try:
        _assert_data_websocket_cap_caption(fake)
    except AssertionError as exc:
        assert "st.caption" in str(exc)
    else:
        raise AssertionError("help=/comment websocket-cap needles must not false-green st.caption")


def test_data_websocket_cap_guard_requires_title_chrome_caption():
    """A late / helper MessageSizeError caption must not bind as Data chrome."""
    late = (
        "import streamlit as st\n"
        'st.title("Data")\n'
        "bootstrap()\n"
        'st.caption("MessageSizeError is the 400 MB websocket maxMessageSize cap")\n'
    )
    helper = (
        "import streamlit as st\n"
        'st.title("Data")\n'
        "def _later():\n"
        '    st.caption("MessageSizeError is the 400 MB websocket maxMessageSize cap")\n'
    )
    for fake in (late, helper):
        try:
            _assert_data_websocket_cap_caption(fake)
        except AssertionError as exc:
            assert "st.caption" in str(exc)
        else:
            raise AssertionError(
                "non-chrome Data cap caption must not false-green title-chrome bind"
            )


def test_user_guide_honesty_names_diagnostic_not_proof_and_data_cap():
    """QI-10-04 / A-21: Purpose and honesty + Data H2 name the shared caveats."""
    honesty = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), "Purpose and honesty")
    missing_honesty = [
        n for n in (_DIAGNOSTIC_NOT_PROOF, "400 MB", "websocket", "Data") if n not in honesty
    ]
    assert missing_honesty == [], f"Purpose and honesty missing A-21 needles {missing_honesty}"
    assert len(honesty) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Purpose and honesty H2 exceeds USER_GUIDE soft budget: {len(honesty)}"
    )
    data = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), "Data")
    missing_data = [n for n in ("MessageSizeError", "400 MB", "websocket") if n not in data]
    assert missing_data == [], f"Data H2 missing cap needles {missing_data}"
    assert len(data) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Data H2 exceeds USER_GUIDE soft budget: {len(data)}"
    )
    fake = (
        "## Notes\n"
        f"{_DIAGNOSTIC_NOT_PROOF} 400 MB websocket Data\n"
        "## Classic workflow overview\nunrelated\n"
    )
    try:
        _md_h2_body(fake, "Purpose and honesty")
    except AssertionError as exc:
        assert "Purpose and honesty" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Purpose and honesty H2")
    fake_data = "## Notes\nMessageSizeError 400 MB websocket\n## Levels\nunrelated\n"
    try:
        _md_h2_body(fake_data, "Data")
    except AssertionError as exc:
        assert "Data" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Data H2")


_H10_CAPTION_NEEDLES = (
    "legacy one-minute primary",
    "fatal OHLCV",
    "api.load_dataset",
    "fail-closed",
)
_H7_CAPTION_NEEDLES = (
    "no_new_entries_after",
    "forced None",
    "api.run_backtest",
    "after_entry_cutoff",
)
_H15_CAPTION_NEEDLES = (
    "OTF",
    "exchange_timezone",
    "api.run_backtest",
    "instrument exchange TZ",
)
_SESSION_CLOSE_H2 = "Session close and entry cutoff"
_SESSION_CLOSE_F6_NEEDLES = (
    "no_new_entries_after",
    "api.run_backtest",
    "after_entry_cutoff",
    "exchange_timezone",
)


def _ingestion_mode_radio_lineno(source: str) -> int:
    """Line of the Data-page ``st.radio`` labeled Ingestion mode."""
    tree = ast.parse(source)
    for call in _st_calls(tree, "radio"):
        if _call_label(call) == "Ingestion mode":
            return call.lineno
    raise AssertionError("Data page missing st.radio('Ingestion mode')")


def test_data_page_captions_h10_legacy_primary_fork():
    """QI-01-03 / A-22: caption after Ingestion mode names the locked fatal fork.

    Not title-chrome: A-21 binds chrome captions to ``st.title``. H10 sits
    next to the legacy-primary radio (plan: legacy-primary caption).
    """
    source = _read(PAGES / "1_Data.py")
    radio_line = _ingestion_mode_radio_lineno(source)
    tree = ast.parse(source)
    matching = [
        (call.lineno, text)
        for call in _st_calls(tree, "caption")
        if (text := _first_arg_text(call)) and all(n in text for n in _H10_CAPTION_NEEDLES)
    ]
    assert matching, f"Data st.caption missing H10 needles {_H10_CAPTION_NEEDLES}"
    assert min(lineno for lineno, _ in matching) > radio_line, (
        "H10 caption must follow st.radio('Ingestion mode'), not title chrome"
    )


def test_backtest_captions_h7_and_h15_locked_forks():
    """QI-04-03 / QI-04-04 / A-22: cutoff + OTF TZ captions after Session exit."""
    source = _read(PAGES / "7_Backtest.py")
    tree = ast.parse(source)
    session_at = _subheader_lineno(tree, "Session exit policy")
    assert session_at is not None
    h7 = [
        (call.lineno, text)
        for call in _st_calls(tree, "caption")
        if (text := _first_arg_text(call)) and all(n in text for n in _H7_CAPTION_NEEDLES)
    ]
    h15 = [
        (call.lineno, text)
        for call in _st_calls(tree, "caption")
        if (text := _first_arg_text(call)) and all(n in text for n in _H15_CAPTION_NEEDLES)
    ]
    assert h7, f"Backtest st.caption missing H7 needles {_H7_CAPTION_NEEDLES}"
    assert h15, f"Backtest st.caption missing H15 needles {_H15_CAPTION_NEEDLES}"
    assert min(lineno for lineno, _ in h7) > session_at
    assert min(lineno for lineno, _ in h15) > session_at


def test_api_docstrings_name_h7_h10_h15():
    """A-22 composer B: api.load_dataset / run_backtest docstrings name the forks."""
    api = _read(REPO_ROOT / "thesistester" / "api.py")
    assert "H10 locked fork" in api
    assert "H7 locked fork" in api
    assert "H15 locked fork" in api


def test_user_guide_session_close_names_h7_h15_forks():
    """QI-13-07 / F-6: Session close H2 names the locked UI vs API cutoff/TZ fork."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _SESSION_CLOSE_H2)
    missing = [n for n in _SESSION_CLOSE_F6_NEEDLES if n not in body]
    assert missing == [], f"Session close H2 missing F-6 needles {missing}"
    assert len(body) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Session close H2 exceeds USER_GUIDE soft budget: {len(body)}"
    )
    data = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), "Data")
    for needle in ("fatal OHLCV", "dataset_id", "Mixed-offset"):
        assert needle in data, f"Data H2 missing A-22/F-6 needle {needle!r}"
    assert len(data) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Data H2 exceeds USER_GUIDE soft budget: {len(data)}"
    )


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


_H8_CONFIRM_RUN_BUTTON = "Run confirmed research"
_H8_CONFIRM_RUN_CAPTION_NEEDLES = (
    "omitted battery enabled means on",
    "grid / walk_forward / validation",
    "study emit stays explicit false",
    "otf matrix is default-off",
)
_H8_PURPOSE_H2 = "Purpose and honesty"
_H8_ASSISTANT_H2 = "Research Assistant (draft, Discuss, Help)"
_H8_STUDY_H2 = "Research Study Runner (headless)"
_USER_GUIDE_H2_SOFT_BUDGET = 4500


def _assert_h8_confirm_run_caption(source: str) -> None:
    """AST-bind H8 caption as a sibling immediately before the confirm-run button.

    File-level ``st.caption`` / ``help=`` / comments false-green (A-1 / A-5 class).
    Caption after the button, or on a different ``if`` than the button, fails closed.
    """
    tree = ast.parse(source)
    buttons = [
        call for call in _st_calls(tree, "button") if _call_label(call) == _H8_CONFIRM_RUN_BUTTON
    ]
    if len(buttons) != 1:
        raise AssertionError(
            f"expected exactly one st.button({_H8_CONFIRM_RUN_BUTTON!r}), got {len(buttons)}"
        )
    button_lineno = buttons[0].lineno
    bound: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        caption_text: str | None = None
        caption_lineno: int | None = None
        has_button = False
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and _is_st_attr_call(stmt.value, "caption"):
                text = _first_arg_text(stmt.value)
                if text and all(n in text.lower() for n in _H8_CONFIRM_RUN_CAPTION_NEEDLES):
                    caption_text = text
                    caption_lineno = stmt.lineno
            if (
                isinstance(stmt, ast.If)
                and isinstance(stmt.test, ast.Call)
                and _is_st_attr_call(stmt.test, "button")
                and _call_label(stmt.test) == _H8_CONFIRM_RUN_BUTTON
            ):
                has_button = True
        if has_button and caption_text is not None:
            if caption_lineno is None or caption_lineno >= button_lineno:
                raise AssertionError("H8 st.caption must precede Run confirmed research")
            bound.append(caption_text)
    if not bound:
        raise AssertionError(
            "Run confirmed research must have an H8 omit-means-on st.caption "
            "immediately before the button"
        )


def test_assistant_confirm_run_caption_discloses_omit_means_on():
    """QI-06-08 / A-9: confirm-run ``st.caption`` (comment / help= fail-closed)."""
    _assert_h8_confirm_run_caption(_read(PAGES / "14_Research_Assistant.py"))


def test_assistant_confirm_run_caption_ignores_comment_and_help_needles():
    """File-level / help= H8 needles must not satisfy the confirm-run caption."""
    fake = (
        "import streamlit as st\n"
        "# omitted battery enabled means on grid / walk_forward / validation\n"
        "# study emit stays explicit false otf matrix is default-off\n"
        'st.selectbox("x", options=["a"], help="omitted battery enabled means on '
        "grid / walk_forward / validation study emit stays explicit false "
        'otf matrix is default-off")\n'
        "if True:\n"
        f'    if st.button("{_H8_CONFIRM_RUN_BUTTON}"):\n'
        "        pass\n"
    )
    try:
        _assert_h8_confirm_run_caption(fake)
    except AssertionError as exc:
        assert "st.caption" in str(exc) or "immediately before" in str(exc)
    else:
        raise AssertionError("help=/comment H8 needles must not false-green st.caption")


def test_assistant_confirm_run_caption_guard_requires_caption_before_button():
    """Caption after the button, or on another if, must fail closed."""
    needles = (
        "Omitted battery enabled means on grid / walk_forward / validation "
        "study emit stays explicit false otf matrix is default-off"
    )
    after_button = (
        "import streamlit as st\n"
        "if True:\n"
        f'    if st.button("{_H8_CONFIRM_RUN_BUTTON}"):\n'
        "        pass\n"
        f'    st.caption("{needles}")\n'
    )
    try:
        _assert_h8_confirm_run_caption(after_button)
    except AssertionError as exc:
        assert "precede" in str(exc) or "immediately before" in str(exc)
    else:
        raise AssertionError("caption after Run confirmed research must not pass")

    other_if = (
        "import streamlit as st\n"
        "if False:\n"
        f'    st.caption("{needles}")\n'
        "if True:\n"
        f'    if st.button("{_H8_CONFIRM_RUN_BUTTON}"):\n'
        "        pass\n"
    )
    try:
        _assert_h8_confirm_run_caption(other_if)
    except AssertionError as exc:
        assert "immediately before" in str(exc)
    else:
        raise AssertionError("off-block H8 caption must not bind to the confirm-run button")


def test_user_guide_purpose_h2_names_classic_headless_omit_means_on():
    """QI-13-09 / A-9: Purpose H2 (Help-allowlisted) names classic omit-means-on."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _H8_PURPOSE_H2)
    missing = [
        n
        for n in (
            "python -m thesistester run",
            "omitted battery `enabled`",
            "Study expand still emits explicit `enabled: false`",
            "Nested OTF",
            "default-off",
            "Bare `{}` in R18 YAML",
        )
        if n not in body
    ]
    assert missing == [], f"Purpose and honesty H2 missing H8 needles {missing}"
    assert len(body) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Purpose and honesty H2 exceeds USER_GUIDE soft budget: {len(body)}"
    )
    fake = (
        "## Notes\n"
        "python -m thesistester run omitted battery `enabled` "
        "Study expand still emits explicit `enabled: false` Nested OTF default-off "
        "Bare `{}` in R18 YAML\n"
        "## Classic workflow overview\nunrelated\n"
    )
    try:
        _md_h2_body(fake, _H8_PURPOSE_H2)
    except AssertionError as exc:
        assert "Purpose" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Purpose and honesty H2")


def test_user_guide_assistant_h2_names_confirm_run_omit_means_on():
    """USER_GUIDE Assistant H2 names confirm-run omit-means-on; Notes-only must not bind."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _H8_ASSISTANT_H2)
    missing = [
        n
        for n in (
            "Run confirmed research",
            "Omitted battery `enabled`",
            "Nested OTF",
            "default-off",
        )
        if n not in body
    ]
    assert missing == [], f"Research Assistant H2 missing H8 needles {missing}"
    assert len(body) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Research Assistant H2 exceeds USER_GUIDE soft budget: {len(body)}"
    )
    fake = (
        "## Notes\n"
        "Run confirmed research Omitted battery `enabled` Nested OTF default-off\n"
        "## Research mode on classic pages\nunrelated\n"
    )
    try:
        _md_h2_body(fake, _H8_ASSISTANT_H2)
    except AssertionError as exc:
        assert "Research Assistant" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Research Assistant H2")


_H16_STUDIES_VIEWER_H2 = "Studies viewer (read-only)"
_H16_STUDIES_VIEWER_NEEDLES = (
    "Inspect",
    "study report",
    "study rollup",
    "Failed",
    "not ranked",
)


def test_user_guide_studies_viewer_h2_names_inspect_vs_report_failed():
    """QI-07-04 / A-10: Studies viewer H2 names Inspect vs report Failed."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _H16_STUDIES_VIEWER_H2)
    missing = [n for n in _H16_STUDIES_VIEWER_NEEDLES if n not in body]
    assert missing == [], f"Studies viewer H2 missing A-10 needles {missing}"
    assert len(body) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Studies viewer H2 exceeds USER_GUIDE soft budget: {len(body)}"
    )
    fake = (
        "## Notes\n"
        "Inspect study report study rollup Failed not ranked\n"
        "## Study Observatory\nunrelated\n"
    )
    try:
        _md_h2_body(fake, _H16_STUDIES_VIEWER_H2)
    except AssertionError as exc:
        assert "Studies viewer" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Studies viewer H2")


_H16_RANKING_ASSUMPTIONS_H2 = "Research Study Runner ranking (RS4)"
_H16_RANKING_STUDY_RUNNER_H2 = "RS4 — Overview report"
_H16_RANKING_RS1_H2 = "RS1 — StudySpec schema (`schema_version: 1`)"
_H16_RANKING_RS5_H2 = "RS5 — Promote + stage-first examples"
_H16_RANKING_NEEDLES = (
    "H16",
    "wfa_median_test_expectancy_r",
    "not rankable",
    "primary_metric",
    "stored",
)
_ASSUMPTIONS_H2_SOFT_BUDGET = 4500


def _assert_a11_h2_needles(
    markdown: str,
    title: str,
    needles: tuple[str, ...],
    *,
    notes_next_h2: str,
    label: str,
    budget: int | None = None,
) -> None:
    """H2-bind A-11 needles; Notes-only copy after the same H2 must not satisfy."""
    body = _md_h2_body(markdown, title)
    missing = [needle for needle in needles if needle not in body]
    assert missing == [], f"{label} missing A-11 needles {missing}"
    if budget is not None:
        assert len(body) <= budget, f"{label} exceeds soft budget: {len(body)}"
    fake = (
        f"## {title}\n"
        "unrelated ranking copy without the contract needles\n"
        "## Notes\n"
        f"{' '.join(needles)}\n"
        f"## {notes_next_h2}\nunrelated\n"
    )
    leaked = [needle for needle in needles if needle in _md_h2_body(fake, title)]
    assert leaked == [], f"Notes-only needles must not bind as {label}: {leaked}"


def test_assumptions_rs4_h2_names_wfa_oos_not_rankable():
    """QI-05-06 / A-11: ASSUMPTIONS RS4 H2 names H16 stored-not-rankable."""
    _assert_a11_h2_needles(
        _read(REPO_ROOT / "docs" / "ASSUMPTIONS_AND_LIMITATIONS.md"),
        _H16_RANKING_ASSUMPTIONS_H2,
        _H16_RANKING_NEEDLES,
        notes_next_h2="Research Study Runner diagnostic rollup (RS-D4)",
        label="ASSUMPTIONS RS4 H2",
        budget=_ASSUMPTIONS_H2_SOFT_BUDGET,
    )


def test_study_runner_rs1_h2_names_primary_metric_allowlist():
    """STUDY_RUNNER RS1 H2 names in-sample primary_metric; WFA token not rankable."""
    _assert_a11_h2_needles(
        _read(REPO_ROOT / "docs" / "STUDY_RUNNER.md"),
        _H16_RANKING_RS1_H2,
        _H16_RANKING_NEEDLES,
        notes_next_h2="RS2 — Deterministic expansion",
        label="STUDY_RUNNER RS1 H2",
    )


def test_study_runner_rs4_h2_names_h16_wfa_not_rankable():
    """STUDY_RUNNER RS4 H2 names H16 stored-not-rankable ranking."""
    _assert_a11_h2_needles(
        _read(REPO_ROOT / "docs" / "STUDY_RUNNER.md"),
        _H16_RANKING_STUDY_RUNNER_H2,
        _H16_RANKING_NEEDLES,
        notes_next_h2="RS5 — Promote + stage-first examples",
        label="STUDY_RUNNER RS4 H2",
    )


def test_study_runner_rs5_h2_names_metric_override_not_allowlist():
    """STUDY_RUNNER RS5 H2: --metric does not make the WFA token rankable."""
    _assert_a11_h2_needles(
        _read(REPO_ROOT / "docs" / "STUDY_RUNNER.md"),
        _H16_RANKING_RS5_H2,
        (
            "--metric",
            "wfa_median_test_expectancy_r",
            "not rankable",
            "primary_metric",
        ),
        notes_next_h2="RS6 — Default-off `STUDY.*` assistant capabilities",
        label="STUDY_RUNNER RS5 H2",
    )


def test_user_guide_study_runner_h2_stays_under_soft_budget():
    """A-9 H8 contrast lives on Purpose; Study Runner must stay ≤ Help chunk budget."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _H8_STUDY_H2)
    assert "Study cell" not in body
    assert len(body) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Research Study Runner H2 exceeds USER_GUIDE soft budget: {len(body)}"
    )
    fake = (
        "## Notes\n"
        "Study emit explicit `false` thesistester run omit means **on** "
        "Bare `{}` in R18 YAML\n"
        "## Studies viewer (read-only)\nunrelated\n"
    )
    try:
        _md_h2_body(fake, _H8_STUDY_H2)
    except AssertionError as exc:
        assert "Research Study Runner" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Research Study Runner H2")


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


_DA0_DIRECTION_HELP_NEEDLES = (
    "touch",
    "both",
    "single_position",
    "accepted",
    "long-only",
    "same-bar",
    "§4b",
)
_DA0_SETUP_BUILDER_H2 = "Setup Builder"
_DA0_HELP_LITERAL = (
    "touch + both + single_position accepted trades are long-only "
    "(same-bar short skipped). See ASSUMPTIONS §4b."
)


def _selectbox_options(source: str, call: ast.Call) -> list:
    """Literal ``options=`` list, or the last assigned list bound to a Name.

    First-assignment wins would false-green a later drifted Name (A-11 class).
    """
    node: ast.AST | None = call.args[1] if len(call.args) > 1 else None
    for kw in call.keywords:
        if kw.arg == "options":
            node = kw.value
            break
    if node is None:
        raise AssertionError("Direction selectbox has no options")
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        value = None
    if isinstance(value, list):
        return value
    if isinstance(node, ast.Name):
        tree = ast.parse(source)
        best: tuple[int, list] | None = None
        for stmt in ast.walk(tree):
            if not isinstance(stmt, ast.Assign) or stmt.lineno > call.lineno:
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == node.id for target in stmt.targets
            ):
                continue
            try:
                assigned = ast.literal_eval(stmt.value)
            except (ValueError, TypeError):
                continue
            if isinstance(assigned, list) and (best is None or stmt.lineno >= best[0]):
                best = (stmt.lineno, assigned)
        if best is not None:
            return best[1]
    raise AssertionError("Direction options is not a list literal")


def _assert_da0_direction_help(source: str) -> None:
    """AST-bind DA0 to the unique Direction ``st.selectbox`` ``help=``.

    File-level / comment / other-widget ``help=`` needles fail-closed (A-1 class).
    """
    call = _selectbox_call(source, "Direction")
    options = _selectbox_options(source, call)
    assert options == ["long", "short", "both"], f"Direction options drifted: {options!r}"
    help_text = _kw_str(call, "help")
    assert help_text, "Direction selectbox must have help= (QI-03-08)"
    missing = [n for n in _DA0_DIRECTION_HELP_NEEDLES if n not in help_text]
    assert missing == [], f"Direction help missing {missing}: {help_text!r}"


def _setup_builder_direction_pitfall(body: str) -> str:
    """Common-pitfall cell (column 3) of the Setup Builder ``Direction`` row."""
    for line in body.splitlines():
        if "| `Direction` |" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0] == "`Direction`":
            return cells[2]
    raise AssertionError("Setup Builder H2 missing `Direction` key-settings row")


def test_setup_builder_direction_help_discloses_da0_long_only():
    """QI-03-08 / A-12: Setup Builder Direction help= names DA0 long-only."""
    _assert_da0_direction_help(_read(PAGES / "3_Setup_Builder.py"))


def test_signals_direction_help_discloses_da0_long_only():
    """QI-03-08 / A-12: Signals Direction help= names DA0 long-only."""
    _assert_da0_direction_help(_read(PAGES / "6_Signals.py"))


def test_direction_help_guard_ignores_comment_and_other_widget():
    """Comment / Trigger help= needles must not satisfy Direction DA0."""
    fake = (
        "import streamlit as st\n"
        "st.selectbox(\n"
        '    "Direction",\n'
        '    options=["long", "short", "both"],\n'
        "    index=2,\n"
        ")\n"
        "st.selectbox(\n"
        '    "Trigger",\n'
        '    options=["touch"],\n'
        "    index=0,\n"
        f'    help="{_DA0_HELP_LITERAL}",\n'
        ")\n"
        f"# {_DA0_HELP_LITERAL}\n"
    )
    try:
        _assert_da0_direction_help(fake)
    except AssertionError as exc:
        assert "help=" in str(exc)
    else:
        raise AssertionError("Direction without help= must not pass via Trigger/comment needles")


def test_direction_help_resolves_options_name():
    """Setup Builder binds ``options=direction_options``; resolve the Name."""
    fake = (
        "import streamlit as st\n"
        'direction_options = ["long", "short", "both"]\n'
        "st.selectbox(\n"
        '    "Direction",\n'
        "    options=direction_options,\n"
        "    index=2,\n"
        f'    help="{_DA0_HELP_LITERAL}",\n'
        ")\n"
    )
    _assert_da0_direction_help(fake)


def test_direction_help_guard_rejects_stale_options_assignment():
    """Earlier correct list-literal must not bind a later drifted Name (A-11)."""
    fake = (
        "import streamlit as st\n"
        'direction_options = ["long", "short", "both"]\n'
        'direction_options = ["hedge"]\n'
        "st.selectbox(\n"
        '    "Direction",\n'
        "    options=direction_options,\n"
        "    index=0,\n"
        f'    help="{_DA0_HELP_LITERAL}",\n'
        ")\n"
    )
    try:
        _assert_da0_direction_help(fake)
    except AssertionError as exc:
        assert "drifted" in str(exc)
    else:
        raise AssertionError("stale first assignment must not bind Direction options")


def test_user_guide_setup_builder_direction_pitfall_names_da0():
    """QI-13-08 / F-7: Setup Builder Direction pitfall cell names DA0 (Help H2)."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _DA0_SETUP_BUILDER_H2)
    pitfall = _setup_builder_direction_pitfall(body)
    assert pitfall != "—", "Direction pitfall must not stay empty (QI-13-08)"
    missing = [n for n in _DA0_DIRECTION_HELP_NEEDLES if n not in pitfall]
    assert missing == [], f"Setup Builder Direction pitfall missing DA0 needles {missing}"
    assert len(body) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Setup Builder H2 exceeds USER_GUIDE soft budget: {len(body)}"
    )
    fake = (
        "## Notes\n"
        "| `Direction` | long short both | "
        "touch both single_position accepted long-only same-bar §4b |\n"
        "## Signals\nunrelated\n"
    )
    try:
        _md_h2_body(fake, _DA0_SETUP_BUILDER_H2)
    except AssertionError as exc:
        assert "Setup Builder" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Setup Builder H2")

    empty_then_notes = (
        "## Setup Builder\n"
        "| Control | Meaning | Common pitfall |\n"
        "| `Direction` | long short both | — |\n"
        "## Notes\n"
        "| `Direction` | long short both | "
        "touch both single_position accepted long-only same-bar §4b |\n"
    )
    notes_body = _md_h2_body(empty_then_notes, _DA0_SETUP_BUILDER_H2)
    notes_pitfall = _setup_builder_direction_pitfall(notes_body)
    assert notes_pitfall == "—", "Notes-table needles must not bind as Setup Builder pitfall"
    assert any(n not in notes_pitfall for n in _DA0_DIRECTION_HELP_NEEDLES)


_H14_SIGNALS_H2 = "Signals"
_H14_TRIGGER_TF_LABEL = "Trigger timeframe"
_H14_HELP_NEEDLES = (
    "H14",
    "dVWAP",
    "early-window",
    "completed HTF OHLC",
    "HTF close",
)
_H14_CAPTION_NEEDLES = _H14_HELP_NEEDLES
_H14_SIGNALS_PITFALL_NEEDLES = (
    "dVWAP",
    "early-window",
    "completed HTF OHLC",
    "HTF close",
    "H14",
)
_H14_3C_INFO_NEEDLE = "non-base trigger timeframe"
_H14_HELP_LITERAL = (
    "H14: developing partners (dVWAP / SMA / rolling VWAP) keep the early-window "
    "value tested against completed HTF OHLC; decision T is HTF close. "
    "Not a snap of those prices to base_end."
)


def _last_assigned_value(source: str, name: str, before_lineno: int) -> ast.AST | None:
    """Last assignment of ``name`` at or before ``before_lineno`` (A-12 last-wins)."""
    tree = ast.parse(source)
    best: tuple[int, ast.AST] | None = None
    for stmt in ast.walk(tree):
        if not isinstance(stmt, ast.Assign) or stmt.lineno > before_lineno:
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in stmt.targets):
            continue
        if best is None or stmt.lineno >= best[0]:
            best = (stmt.lineno, stmt.value)
    return None if best is None else best[1]


def _ifexp_branch_when_name_eq(ifexp: ast.IfExp, name: str, value: str) -> ast.AST:
    """Return the branch taken when ``name == value`` (fail-closed on other tests)."""
    test = ifexp.test
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
        left, right = test.left, test.comparators[0]
        op = test.ops[0]
        left_name = isinstance(left, ast.Name) and left.id == name
        right_name = isinstance(right, ast.Name) and right.id == name
        matches = (left_name and _literal_str(right) == value) or (
            right_name and _literal_str(left) == value
        )
        if matches:
            if isinstance(op, ast.Eq):
                return ifexp.body
            if isinstance(op, ast.NotEq):
                return ifexp.orelse
    raise AssertionError(f"help IfExp is not `{name} == {value!r}`")


def _string_from_help_node(source: str, node: ast.AST, before_lineno: int) -> str:
    """Literal ``help=`` or last Name assignment; IfExp uses the ``trigger == '3c'`` branch."""
    text = _joined_text(node) or _literal_str(node)
    if text is not None:
        return text
    if isinstance(node, ast.Name):
        assigned = _last_assigned_value(source, node.id, before_lineno)
        if assigned is None:
            raise AssertionError("Trigger timeframe help= Name has no assignment")
        if isinstance(assigned, ast.IfExp):
            branch = _ifexp_branch_when_name_eq(assigned, "trigger", "3c")
            text = _joined_text(branch) or _literal_str(branch)
            if text is None:
                raise AssertionError("3c help IfExp branch is not a string")
            return text
        text = _joined_text(assigned) or _literal_str(assigned)
        if text is None:
            raise AssertionError("Trigger timeframe help assignment is not a string")
        return text
    raise AssertionError("Trigger timeframe help= is not a string literal or Name")


def _assert_h14_trigger_timeframe_help(source: str) -> None:
    """AST-bind H14 to Trigger timeframe ``help=`` (3c branch).

    File-level / comment / caption / simple-TF else-branch needles fail-closed.
    """
    call = _selectbox_call(source, _H14_TRIGGER_TF_LABEL)
    help_node = None
    for kw in call.keywords:
        if kw.arg == "help":
            help_node = kw.value
            break
    if help_node is None:
        raise AssertionError("Trigger timeframe selectbox must have help=")
    help_text = _string_from_help_node(source, help_node, call.lineno)
    missing = [n for n in _H14_HELP_NEEDLES if n not in help_text]
    assert missing == [], f"Trigger timeframe 3c help missing {missing}: {help_text!r}"


def _assert_h14_htf_3c_caption(source: str) -> None:
    """AST-bind H14 ``st.caption`` after the 3c non-base ``st.info``.

    ``help=`` / comments / a caption before that info fail-closed (A-6 class).
    """
    tree = ast.parse(source)
    info_lines = [
        call.lineno
        for call in _st_calls(tree, "info")
        if (text := _first_arg_text(call)) and _H14_3C_INFO_NEEDLE in text
    ]
    if not info_lines:
        raise AssertionError("missing 3c non-base trigger timeframe st.info")
    info_at = min(info_lines)
    matching: list[tuple[int, str]] = []
    for call in _st_calls(tree, "caption"):
        text = _first_arg_text(call)
        if text and all(n in text for n in _H14_CAPTION_NEEDLES):
            matching.append((call.lineno, text))
    if not matching:
        raise AssertionError(
            f"Signals HTF+3c st.caption missing H14 needles {list(_H14_CAPTION_NEEDLES)}"
        )
    caption_at = min(lineno for lineno, _ in matching)
    if caption_at <= info_at:
        raise AssertionError("H14 st.caption must follow 3c non-base st.info")


def _signals_3c_htf_pitfall(body: str) -> str:
    """Common-pitfall cell of the Signals ``3c`` + ``Trigger timeframe`` row."""
    for line in body.splitlines():
        if "| `3c` + `Trigger timeframe` |" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] == "`3c` + `Trigger timeframe`":
            return cells[2]
    raise AssertionError("Signals H2 missing `3c` + `Trigger timeframe` key-settings row")


def test_signals_trigger_timeframe_help_discloses_h14():
    """QI-03-06 / A-13: Trigger timeframe 3c help= names H14 (Name → IfExp)."""
    _assert_h14_trigger_timeframe_help(_read(PAGES / "6_Signals.py"))


def test_signals_htf_3c_caption_discloses_h14():
    """QI-03-06 / A-13: HTF+3c st.caption follows non-base info."""
    _assert_h14_htf_3c_caption(_read(PAGES / "6_Signals.py"))


def test_h14_help_guard_ignores_comment_caption_and_else_branch():
    """Comment / caption / simple-TF else-branch needles must not satisfy 3c help."""
    fake = (
        "import streamlit as st\n"
        f"# {_H14_HELP_LITERAL}\n"
        "trigger_timeframe_help = (\n"
        '    "Candle-close trigger logic."\n'
        '    if trigger == "3c"\n'
        "    else (\n"
        f'        "{_H14_HELP_LITERAL}"\n'
        "    )\n"
        ")\n"
        "st.selectbox(\n"
        f'    "{_H14_TRIGGER_TF_LABEL}",\n'
        '    options=["5min"],\n'
        "    help=trigger_timeframe_help,\n"
        ")\n"
        f'st.info("3c with {_H14_3C_INFO_NEEDLE}: arrival on HTF.")\n'
        f'st.caption("{_H14_HELP_LITERAL}")\n'
    )
    try:
        _assert_h14_trigger_timeframe_help(fake)
    except AssertionError as exc:
        assert "missing" in str(exc) or "help=" in str(exc)
    else:
        raise AssertionError("else-branch/comment/caption H14 needles must not bind 3c help")


def test_h14_help_resolves_name_ifexp_true_branch():
    """Name + ``trigger == '3c'`` IfExp must bind the true branch."""
    fake = (
        "import streamlit as st\n"
        "trigger_timeframe_help = (\n"
        f'    "{_H14_HELP_LITERAL}"\n'
        '    if trigger == "3c"\n'
        "    else (\n"
        '        "Candle-close trigger logic."\n'
        "    )\n"
        ")\n"
        "st.selectbox(\n"
        f'    "{_H14_TRIGGER_TF_LABEL}",\n'
        '    options=["5min"],\n'
        "    help=trigger_timeframe_help,\n"
        ")\n"
    )
    _assert_h14_trigger_timeframe_help(fake)


def test_h14_caption_guard_requires_st_caption_after_nonbase_info():
    """help=/comment needles, or a caption before the 3c info, fail-closed."""
    head = "import streamlit as st\n"
    caption = f'st.caption("{_H14_HELP_LITERAL}")\n'
    info = f'st.info("3c with {_H14_3C_INFO_NEEDLE}: arrival on HTF.")\n'
    help_only = (
        head
        + "st.selectbox(\n"
        + f'    "{_H14_TRIGGER_TF_LABEL}",\n'
        + '    options=["5min"],\n'
        + f'    help="{_H14_HELP_LITERAL}",\n'
        + ")\n"
        + f"# {_H14_HELP_LITERAL}\n"
        + info
    )
    try:
        _assert_h14_htf_3c_caption(help_only)
    except AssertionError as exc:
        assert "st.caption" in str(exc)
    else:
        raise AssertionError("help=/comment H14 needles must not satisfy st.caption")

    before_info = head + caption + info
    try:
        _assert_h14_htf_3c_caption(before_info)
    except AssertionError as exc:
        assert "must follow" in str(exc)
    else:
        raise AssertionError("H14 caption before 3c non-base info must not pass")


def test_user_guide_signals_h2_names_h14_3c_htf():
    """QI-03-06 / A-13: Signals 3c HTF pitfall cell names H14 (Help H2)."""
    body = _md_h2_body(_read(REPO_ROOT / "docs" / "USER_GUIDE.md"), _H14_SIGNALS_H2)
    pitfall = _signals_3c_htf_pitfall(body)
    missing = [n for n in _H14_SIGNALS_PITFALL_NEEDLES if n not in pitfall]
    assert missing == [], f"Signals 3c HTF pitfall missing A-13 needles {missing}"
    assert len(body) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Signals H2 exceeds USER_GUIDE soft budget: {len(body)}"
    )
    fake = (
        "## Notes\n"
        "| `3c` + `Trigger timeframe` | HTF | "
        "dVWAP early-window completed HTF OHLC HTF close H14 |\n"
        "## Backtest\nunrelated\n"
    )
    try:
        _md_h2_body(fake, _H14_SIGNALS_H2)
    except AssertionError as exc:
        assert "Signals" in str(exc)
    else:
        raise AssertionError("Notes-only needles must not bind as Signals H2")

    empty_then_notes = (
        "## Signals\n"
        "| Control | Meaning | Common pitfall |\n"
        "| `3c` + `Trigger timeframe` | HTF | — |\n"
        "## Notes\n"
        "| `3c` + `Trigger timeframe` | HTF | "
        "dVWAP early-window completed HTF OHLC HTF close H14 |\n"
    )
    notes_body = _md_h2_body(empty_then_notes, _H14_SIGNALS_H2)
    notes_pitfall = _signals_3c_htf_pitfall(notes_body)
    assert notes_pitfall == "—", "Notes-table needles must not bind as Signals 3c HTF pitfall"
    assert any(n not in notes_pitfall for n in _H14_SIGNALS_PITFALL_NEEDLES)
