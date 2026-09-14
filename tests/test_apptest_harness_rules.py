"""B-12 / B-13 AppTest harness gates (QI-11-03 / QI-10-05).

Fail-closed: AST-bound proto / ``set_value`` / ``serial`` / helper import /
``list(session_state)``, plus discovery of every test module that imports
``AppTest``. Shared isolate fixture lives in ``tests/conftest.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tests" / "apptest_helpers.py"
REQUIRED_APPTEST_FILES = (
    ROOT / "tests" / "test_assistant_page_render.py",
    ROOT / "tests" / "study" / "test_study_observatory.py",
    ROOT / "tests" / "test_classic_pages_apptest.py",
)
CONFTEST = ROOT / "tests" / "conftest.py"
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
    """True if any module ``pytestmark`` is ``serial`` (scalar, list, or tuple)."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        ):
            continue
        if _is_serial_mark(node.value):
            return True
        if isinstance(node.value, (ast.List, ast.Tuple)) and any(
            _is_serial_mark(elt) for elt in node.value.elts
        ):
            return True
    return False


def _function_has_serial(tree: ast.Module, name: str) -> bool:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return any(_is_serial_mark(decorator) for decorator in node.decorator_list)
    return False


def test_discovered_apptest_files_include_page14_page16_and_classic_smoke() -> None:
    discovered = _discover_apptest_files()
    missing = [path for path in REQUIRED_APPTEST_FILES if path not in discovered]
    assert missing == [], f"AppTest discovery missed {[p.name for p in missing]}"
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
    tree = ast.parse("import pytest\npytestmark = [pytest.mark.serial]\n")
    assert _module_pytestmark_is_serial(tree) is True
    tree = ast.parse("import pytest\npytestmark = (pytest.mark.serial, pytest.mark.skip)\n")
    assert _module_pytestmark_is_serial(tree) is True
    tree = ast.parse("import pytest\npytestmark = [pytest.mark.skip]\n")
    assert _module_pytestmark_is_serial(tree) is False


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


def _is_session_state_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "session_state":
        return True
    return isinstance(node, ast.Name) and node.id == "session_state"


def _lists_session_state(tree: ast.AST) -> list[int]:
    """Lines that iterate a session_state mapping (Streamlit 1.63 KeyError 0)."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and _is_session_state_expr(node.iter):
            lines.append(node.lineno)
        if isinstance(node, ast.Starred) and _is_session_state_expr(node.value):
            lines.append(node.lineno)
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in {"list", "tuple", "set", "dict"}):
            continue
        if not node.args:
            continue
        if _is_session_state_expr(node.args[0]):
            lines.append(node.lineno)
    return lines


def test_apptest_files_never_list_session_state() -> None:
    """QI-10-05 / B-13: Streamlit 1.63 ``list(session_state)`` raises KeyError 0."""
    for path in _discover_apptest_files():
        tree = ast.parse(_source(path))
        hits = _lists_session_state(tree)
        assert hits == [], f"{path.name} list(session_state) at lines {hits}"
        assert "list(session_state)" not in _source(path), path.name
        assert "list(app.session_state)" not in _source(path), path.name


def _fixture_autouse_true(decorator: ast.AST) -> bool:
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    is_fixture = (isinstance(func, ast.Attribute) and func.attr == "fixture") or (
        isinstance(func, ast.Name) and func.id == "fixture"
    )
    if not is_fixture:
        return False
    return any(
        isinstance(kw, ast.keyword)
        and kw.arg == "autouse"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is True
        for kw in decorator.keywords
    )


def _assigns_modules_streamlit(node: ast.AST) -> bool:
    if not isinstance(node, ast.Assign) or not node.targets:
        return False
    target = node.targets[0]
    if not isinstance(target, ast.Subscript):
        return False
    slc = target.slice
    if not (isinstance(slc, ast.Constant) and slc.value == "streamlit"):
        return False
    value = target.value
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "modules"
        and isinstance(value.value, ast.Name)
        and value.value.id == "sys"
    )


def _call_restores_real_streamlit(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "_restore_real_streamlit"
    )


def _restore_helper_assigns_streamlit(tree: ast.Module) -> bool:
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name == "_restore_real_streamlit"):
            continue
        return any(_assigns_modules_streamlit(stmt) for stmt in ast.walk(node))
    return False


def _isolate_restores_streamlit_before_and_after(tree: ast.Module) -> bool:
    if not _restore_helper_assigns_streamlit(tree):
        return False
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name == "isolate_apptest_globals"):
            continue
        if not any(_fixture_autouse_true(dec) for dec in node.decorator_list):
            return False
        before_yield = False
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Yield):
                return False
            if not isinstance(stmt, ast.Try):
                if _call_restores_real_streamlit(stmt) or _assigns_modules_streamlit(stmt):
                    before_yield = True
                continue
            if not any(
                isinstance(item, ast.Expr) and isinstance(item.value, ast.Yield)
                for item in stmt.body
            ):
                continue
            after_yield = any(
                _call_restores_real_streamlit(item) or _assigns_modules_streamlit(item)
                for item in stmt.finalbody
            )
            return before_yield and after_yield
    return False


def _function_uses_apptest(fn: ast.FunctionDef) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id == "AppTest":
            return True
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "streamlit.testing.v1":
            continue
        if any(alias.name == "AppTest" for alias in node.names):
            return True
    return False


def test_isolate_apptest_globals_lives_in_conftest() -> None:
    tree = ast.parse(_source(CONFTEST))
    names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "isolate_apptest_globals"
    }
    assert names == {"isolate_apptest_globals"}
    assert _isolate_restores_streamlit_before_and_after(tree)
    assistant = _source(REQUIRED_APPTEST_FILES[0])
    observatory = _source(REQUIRED_APPTEST_FILES[1])
    assert "def isolate_apptest_globals" not in assistant
    assert "def isolate_observatory_apptest_globals" not in observatory


def test_isolate_gate_rejects_teardown_only_streamlit_restore() -> None:
    tree = ast.parse(
        "import pytest\n"
        "import sys\n"
        "def _restore_real_streamlit():\n"
        "    sys.modules['streamlit'] = object()\n"
        "@pytest.fixture(autouse=True)\n"
        "def isolate_apptest_globals():\n"
        "    try:\n"
        "        yield\n"
        "    finally:\n"
        "        _restore_real_streamlit()\n"
    )
    assert _isolate_restores_streamlit_before_and_after(tree) is False


def test_classic_smoke_module_is_serial() -> None:
    tree = ast.parse(_source(REQUIRED_APPTEST_FILES[2]))
    assert _module_pytestmark_is_serial(tree)


def test_every_discovered_apptest_file_is_serial() -> None:
    """AGENT_GUIDE: discover every AppTest import and AST-bind serial."""
    for path in _discover_apptest_files():
        tree = ast.parse(_source(path))
        if _module_pytestmark_is_serial(tree):
            continue
        unmarked = [
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and _function_uses_apptest(node)
            and not any(_is_serial_mark(dec) for dec in node.decorator_list)
        ]
        assert unmarked == [], f"{path.name} AppTest functions missing serial: {unmarked}"


def test_list_session_state_gate_rejects_tuple_and_for() -> None:
    tree = ast.parse("keys = tuple(app.session_state)\nfor key in st.session_state:\n    pass\n")
    assert sorted(_lists_session_state(tree)) == [1, 2]
