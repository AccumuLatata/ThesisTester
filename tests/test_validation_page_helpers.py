"""QR D-4 / QI-05-02: Validation page-helper unit tests (H13 / M9)."""

from __future__ import annotations

import ast
from pathlib import Path

from thesistester.validation_page_helpers import (
    PERMUTATION_H13_CAPTION,
    assemble_overlap_help,
    assemble_permutation_copy,
    fmt_value,
    parse_positive_int_values,
    parse_thresholds,
)

REPO = Path(__file__).resolve().parents[1]
WFA = REPO / "thesistester" / "validation_wfa_page_helpers.py"
DISPLAY = REPO / "thesistester" / "validation_display_page_helpers.py"
BATTERIES = REPO / "thesistester" / "validation_batteries_page_helpers.py"
PAGE = REPO / "pages" / "10_Validation.py"


def test_assemble_overlap_help_names_fold_sum_and_withholds_stitch() -> None:
    help_text = assemble_overlap_help()
    assert "aggregate_test_total_r" in help_text
    assert "fold-sum" in help_text
    assert "stitched equity" in help_text
    assert "avoids double-counting" not in help_text.lower()


def test_assemble_overlap_help_matches_wfa_selectbox_literal() -> None:
    """M9 selectbox help= stays a string literal equal to the helper."""
    tree = ast.parse(WFA.read_text(encoding="utf-8"))
    help_text = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "selectbox"):
            continue
        label = None
        if node.args and isinstance(node.args[0], ast.Constant):
            label = node.args[0].value
        if label != "Overlapping OOS ownership":
            continue
        for kw in node.keywords:
            if kw.arg == "help":
                help_text = ast.literal_eval(kw.value)
    assert help_text == assemble_overlap_help()


def test_assemble_permutation_copy_high_p_is_info_without_caption() -> None:
    copy = assemble_permutation_copy(0.20)
    assert copy["caption"] is None
    assert "not unusually high" in (copy["info"] or "")
    assert "success" not in (copy["info"] or "").lower()


def test_assemble_permutation_copy_marginal_is_info_without_caption() -> None:
    copy = assemble_permutation_copy(0.08)
    assert copy["caption"] is None
    assert "Marginal evidence" in (copy["info"] or "")


def test_assemble_permutation_copy_low_p_is_info_plus_h13_caption() -> None:
    copy = assemble_permutation_copy(0.01)
    assert copy["caption"] == PERMUTATION_H13_CAPTION
    assert "sign symmetry" in (copy["caption"] or "")
    assert "serial dependence" in (copy["caption"] or "")
    info = copy["info"] or ""
    assert "Diagnostic only" in info
    assert "not a significance test" in info
    assert "not proof of edge" in info
    assert "success" not in info.lower()
    assert "🎉" not in info


def test_display_helper_keeps_p_val_gt_005_else_info_caption() -> None:
    """H13 AST lock walks the display helper after D-4 extract."""
    tree = ast.parse(DISPLAY.read_text(encoding="utf-8"))
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
    assert low_branch, "missing else branch of p_val > 0.05"
    low_calls = [
        stmt.value
        for stmt in low_branch
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
    ]

    def _is_st(call: ast.Call, attr: str) -> bool:
        return (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == attr
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "st"
        )

    assert any(_is_st(call, "info") for call in low_calls)
    assert not any(_is_st(call, "success") for call in low_calls)
    assert any(_is_st(call, "caption") for call in low_calls)


def test_fmt_value_and_parsers() -> None:
    assert fmt_value(None) == "—"
    assert fmt_value(1.23456) == "1.2346"
    assert parse_positive_int_values("3, 1, 2, 1") == [1, 2, 3]
    assert parse_thresholds("3,5,x,10") == [3.0, 5.0, 10.0]
    assert parse_thresholds("bad") == [3.0, 5.0, 10.0]


def _joined_template(node: ast.AST) -> str | None:
    """String literal or f-string constant parts with ``{}`` for formatted values."""
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        value = None
    if isinstance(value, str):
        return value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for child in node.values:
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                parts.append(child.value)
            elif isinstance(child, ast.FormattedValue):
                parts.append("{}")
            else:
                return None
        return "".join(parts)
    return None


def _st_first_arg_templates(source: str, attr: str) -> list[str]:
    tree = ast.parse(source)
    templates: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != attr:
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "st"):
            continue
        if not node.args:
            continue
        text = _joined_template(node.args[0])
        if text is not None:
            templates.append(text)
    return templates


def test_assemble_permutation_copy_matches_display_literals() -> None:
    """H13 assembler stays the display-helper source of truth (overlap-help class)."""
    source = DISPLAY.read_text(encoding="utf-8")
    info_templates = _st_first_arg_templates(source, "info")
    caption_templates = _st_first_arg_templates(source, "caption")
    for p_val in (0.20, 0.08, 0.01):
        copy = assemble_permutation_copy(p_val)
        expected_info = (copy["info"] or "").replace(f"{p_val:.4f}", "{}")
        assert expected_info in info_templates, (p_val, expected_info, info_templates)
    assert PERMUTATION_H13_CAPTION in caption_templates


def test_batteries_uses_extracted_parse_thresholds() -> None:
    """MC drawdown parse must call the extracted helper, not a nested copy."""
    tree = ast.parse(BATTERIES.read_text(encoding="utf-8"))
    imported = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "thesistester.validation_page_helpers"
        ):
            imported = any(alias.name == "parse_thresholds" for alias in node.names)
        if isinstance(node, ast.FunctionDef) and node.name == "render_validation_batteries":
            nested = [
                child.name
                for child in ast.walk(node)
                if isinstance(child, ast.FunctionDef) and child.name == "_parse_thresholds"
            ]
            assert nested == [], "batteries must not keep a nested _parse_thresholds"
    assert imported, "batteries must import parse_thresholds from validation_page_helpers"
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_parse_thresholds"
    ]
    assert calls, "Monte Carlo path must call _parse_thresholds"


def test_validation_page_keeps_wfa_before_batteries_and_phase8_before_otf() -> None:
    """M10/H13 page order: WFA → batteries → Phase 8 → OTF (st.stop still after batteries)."""
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    order: list[tuple[int, str]] = []
    wanted = {
        "render_wfa_otf_diagnostics",
        "render_validation_batteries",
        "render_phase8_results",
        "render_otf_validation_matrix",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = None
        if isinstance(node.func, ast.Name) and node.func.id in wanted:
            name = node.func.id
        if name is None:
            continue
        order.append((node.lineno, name))
    names = [name for _, name in sorted(order)]
    assert names == [
        "render_wfa_otf_diagnostics",
        "render_validation_batteries",
        "render_phase8_results",
        "render_otf_validation_matrix",
    ]
