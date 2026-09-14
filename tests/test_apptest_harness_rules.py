"""B-12 / QI-11-03: AppTest files stay proto-free and never disable-set_value."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPTEST_FILES = (
    ROOT / "tests" / "test_assistant_page_render.py",
    ROOT / "tests" / "study" / "test_study_observatory.py",
)
HELPER = ROOT / "tests" / "apptest_helpers.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_apptest_files_have_zero_proto_reads() -> None:
    for path in APPTEST_FILES:
        tree = ast.parse(_source(path))
        proto_attrs = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "proto"
        ]
        assert proto_attrs == [], f"{path.name} proto. reads at lines {proto_attrs}"
        assert "proto." not in _source(path), path.name


def test_apptest_files_call_set_value_only_via_helper() -> None:
    for path in APPTEST_FILES:
        tree = ast.parse(_source(path))
        direct = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "set_value":
                direct.append(node.lineno)
        assert direct == [], f"{path.name} direct set_value at lines {direct}"
        if "set_value(" in _source(path):
            assert "set_enabled_value" in _source(path), path.name


def test_set_enabled_value_helper_rejects_disabled() -> None:
    from tests.apptest_helpers import set_enabled_value, widget_disabled

    class _Disabled:
        type = "chat_input"
        key = "probe"
        disabled = True

        def set_value(self, value):  # pragma: no cover - must not run
            raise AssertionError("set_value must not run on a disabled widget")

    widget = _Disabled()
    assert widget_disabled(widget) is True
    try:
        set_enabled_value(widget, "nope")
    except AssertionError as exc:
        assert "disabled chat_input" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected AssertionError for disabled set_value")


def test_assistant_module_and_observatory_apptests_are_serial() -> None:
    assistant = ast.parse(_source(APPTEST_FILES[0]))
    assert any(
        isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "pytestmark" for t in node.targets)
        for node in assistant.body
    )
    observatory = _source(APPTEST_FILES[1])
    for name in (
        "test_observatory_page_renders_studies_pane",
        "test_observatory_empty_facets_do_not_claim_shared_cohort",
        "test_observatory_page_lens_facets_and_heatmap_cell",
    ):
        assert f"def {name}" in observatory
    # Three AppTest functions carry serial; the rest of the file stays unmarked.
    assert observatory.count("@pytest.mark.serial") == 3
    helper = _source(HELPER)
    assert "Never read" in helper or "never read" in helper.lower()
    assert "proto.*" in helper
