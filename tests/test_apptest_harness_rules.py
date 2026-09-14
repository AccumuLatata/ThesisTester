"""B-12 / QI-11-03: AppTest files stay proto-free and never disable-set_value.

Gate is fail-closed: AST-bound proto / ``set_value`` / ``serial`` / helper
import, plus discovery of every test module that imports ``AppTest``.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tests" / "apptest_helpers.py"
REQUIRED_APPTEST_FILES = (
    ROOT / "tests" / "test_assistant_page_render.py",
    ROOT / "tests" / "study" / "test_study_observatory.py",
)
OBSERVATORY_SERIAL_TESTS = (
    "test_observatory_page_renders_studies_pane",
    "test_observatory_empty_facets_do_not_claim_shared_cohort",
    "test_observatory_page_lens_facets_and_heatmap_cell",
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _imports_apptest(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "streamlit.testing.v1":
            continue
        if any(alias.name == "AppTest" for alias in node.names):
            return True
    return False


def _discover_apptest_files() -> tuple[Path, ...]:
    found: list[Path] = []
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        if _imports_apptest(ast.parse(_source(path))):
            found.append(path)
    return tuple(found)


def _proto_read_lines(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "proto":
            lines.append(node.lineno)
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_getattr = (isinstance(func, ast.Name) and func.id == "getattr") or (
            isinstance(func, ast.Attribute) and func.attr == "getattr"
        )
        if not is_getattr or len(node.args) < 2:
            continue
        name = node.args[1]
        if isinstance(name, ast.Constant) and name.value == "proto":
            lines.append(node.lineno)
    return lines


def _set_value_attr_lines(tree: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "set_value"
    ]


def _helper_imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "tests.apptest_helpers":
            continue
        for alias in node.names:
            names.add(alias.asname or alias.name)
    return names


def _calls_set_enabled_value(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "set_enabled_value":
            return True
    return False


def _is_serial_mark(node: ast.AST) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if not isinstance(target, ast.Attribute) or target.attr != "serial":
        return False
    mark = target.value
    return (
        isinstance(mark, ast.Attribute)
        and mark.attr == "mark"
        and isinstance(mark.value, ast.Name)
        and mark.value.id == "pytest"
    )


def _module_pytestmark_is_serial(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in node.targets
        ):
            continue
        return _is_serial_mark(node.value)
    return False


def _function_has_serial(tree: ast.Module, name: str) -> bool:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return any(_is_serial_mark(decorator) for decorator in node.decorator_list)
    return False


def test_discovered_apptest_files_include_page14_and_page16() -> None:
    discovered = _discover_apptest_files()
    missing = [path for path in REQUIRED_APPTEST_FILES if path not in discovered]
    assert missing == [], f"AppTest discovery missed { [p.name for p in missing] }"
    assert set(discovered) >= set(REQUIRED_APPTEST_FILES)


def test_apptest_files_have_zero_proto_reads() -> None:
    for path in _discover_apptest_files():
        tree = ast.parse(_source(path))
        proto_lines = _proto_read_lines(tree)
        assert proto_lines == [], f"{path.name} proto reads at lines {proto_lines}"
        assert "proto." not in _source(path), path.name


def test_helper_has_zero_proto_attribute_reads() -> None:
    tree = ast.parse(_source(HELPER))
    assert _proto_read_lines(tree) == []
    assert _set_value_attr_lines(tree)  # the one allowed .set_value lives here


def test_apptest_files_call_set_value_only_via_helper() -> None:
    for path in _discover_apptest_files():
        tree = ast.parse(_source(path))
        direct = _set_value_attr_lines(tree)
        assert direct == [], f"{path.name} direct set_value at lines {direct}"
        if _calls_set_enabled_value(tree):
            assert "set_enabled_value" in _helper_imported_names(tree), path.name


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


def test_set_enabled_value_helper_rejects_missing_disabled() -> None:
    from tests.apptest_helpers import set_enabled_value, widget_disabled

    class _NoFlag:
        type = "selectbox"

        def set_value(self, value):  # pragma: no cover - must not run
            raise AssertionError("set_value must not run without .disabled")

    try:
        widget_disabled(_NoFlag())
    except AssertionError as exc:
        assert "public .disabled" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected AssertionError for missing .disabled")

    try:
        set_enabled_value(_NoFlag(), "nope")
    except AssertionError as exc:
        assert "public .disabled" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected AssertionError for missing .disabled")


def test_set_enabled_value_helper_sets_enabled() -> None:
    from tests.apptest_helpers import set_enabled_value, widget_disabled

    class _Enabled:
        type = "chat_input"
        disabled = False
        seen: object = None

        def set_value(self, value):
            self.seen = value
            return self

    widget = _Enabled()
    assert widget_disabled(widget) is False
    assert set_enabled_value(widget, "ok") is widget
    assert widget.seen == "ok"


def test_assistant_module_and_observatory_apptests_are_serial() -> None:
    assistant = ast.parse(_source(REQUIRED_APPTEST_FILES[0]))
    assert _module_pytestmark_is_serial(assistant)
    observatory = ast.parse(_source(REQUIRED_APPTEST_FILES[1]))
    for name in OBSERVATORY_SERIAL_TESTS:
        assert _function_has_serial(observatory, name), name
    serial_fns = [
        node.name
        for node in observatory.body
        if isinstance(node, ast.FunctionDef)
        and any(_is_serial_mark(decorator) for decorator in node.decorator_list)
    ]
    assert serial_fns == list(OBSERVATORY_SERIAL_TESTS)
    helper = _source(HELPER)
    assert "Never read" in helper or "never read" in helper.lower()
    assert "proto.*" in helper
    assert "fails closed" in helper


def test_serial_marker_registered_in_pyproject() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "markers = [" in text
    assert "serial: AppTest" in text


def test_serial_gate_rejects_non_serial_pytestmark() -> None:
    tree = ast.parse("import pytest\npytestmark = pytest.mark.skip\n")
    assert _module_pytestmark_is_serial(tree) is False
    tree = ast.parse("import pytest\npytestmark = pytest.mark.serial\n")
    assert _module_pytestmark_is_serial(tree) is True


def test_serial_gate_rejects_unmarked_or_wrong_function() -> None:
    tree = ast.parse(
        "import pytest\n"
        "@pytest.mark.serial\n"
        "def test_other():\n"
        "    return\n"
        "def test_observatory_page_renders_studies_pane():\n"
        "    return\n"
    )
    assert _function_has_serial(tree, "test_observatory_page_renders_studies_pane") is False
    assert _function_has_serial(tree, "test_other") is True


def test_proto_gate_rejects_getattr_proto() -> None:
    tree = ast.parse('value = getattr(widget, "proto")\n')
    assert _proto_read_lines(tree) == [1]


def test_set_value_gate_rejects_bound_method() -> None:
    tree = ast.parse("fn = widget.set_value\n")
    assert _set_value_attr_lines(tree) == [1]
