"""Regression contracts for Research Assistant page controls.

The page executes Streamlit UI code at import time, so these tests inspect its
syntax tree instead of importing it outside a Streamlit runtime.
"""

from __future__ import annotations

import ast
from pathlib import Path


PAGE_PATH = Path(__file__).parent.parent / "pages" / "14_Research_Assistant.py"


def test_structured_setup_trigger_options_include_3c_and_are_used_by_the_widget():
    """Applying unchanged controls must preserve a valid 3c draft trigger."""
    tree = ast.parse(PAGE_PATH.read_text(encoding="utf-8"))
    trigger_options = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "SETUP_TRIGGER_OPTIONS"
            for target in node.targets
        )
    )

    assert ast.literal_eval(trigger_options) == ["touch", "reject", "break", "reclaim", "3c"]

    trigger_widgets = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "selectbox"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "Trigger"
    ]
    assert any(
        len(widget.args) >= 2
        and isinstance(widget.args[1], ast.Name)
        and widget.args[1].id == "SETUP_TRIGGER_OPTIONS"
        for widget in trigger_widgets
    )


def test_structured_setup_controls_clamp_confluence_bounds_to_selected_levels():
    """Applying a shorter level list must not preserve impossible prior bounds."""
    tree = ast.parse(PAGE_PATH.read_text(encoding="utf-8"))
    submit_handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Call)
        and isinstance(node.test.func, ast.Attribute)
        and node.test.func.attr == "form_submit_button"
        and node.test.args
        and isinstance(node.test.args[0], ast.Constant)
        and node.test.args[0].value == "Apply setup controls"
    )

    handler_source = ast.unparse(submit_handler)
    assert "level_count = max(1, len(levels))" in handler_source
    assert "min_confluences = min(max(1, previous_min_confluences), level_count)" in handler_source
    assert (
        "max_confluences = min(max(min_confluences, previous_max_confluences), level_count)"
        in handler_source
    )
