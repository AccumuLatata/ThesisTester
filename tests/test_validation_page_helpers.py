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

WFA = Path(__file__).resolve().parents[1] / "thesistester" / "validation_wfa_page_helpers.py"
DISPLAY = (
    Path(__file__).resolve().parents[1] / "thesistester" / "validation_display_page_helpers.py"
)


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
