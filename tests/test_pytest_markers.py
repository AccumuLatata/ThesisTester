"""B-15 / QI-11-05: pytest marker set is registered; CI stays the full suite.

Warn-first: unmarked tests become ``unit`` at collection. Unknown marker
names fail (``--strict-markers``). Do not add ``-m unit`` to G-1 cells or
xdist before AppTest ``serial`` (already required by the harness lock).

Fail-closed: hook defaults are exercised on fake items; mixed oracle files
must not carry a module-level class mark; CI pytest invocations stay
unfiltered.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

tomllib = importlib.import_module("tomllib" if sys.version_info >= (3, 11) else "tomli")

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_MARKERS = (
    "unit",
    "integration",
    "golden",
    "eval",
    "benchmark",
    "oracle",
    "serial",
)
CLASS_MARKERS = frozenset({"unit", "integration", "golden", "eval", "benchmark", "oracle"})
BUILTIN_MARKS = frozenset(
    {"parametrize", "skip", "skipif", "xfail", "filterwarnings", "usefixtures"}
)

GOLDEN_MODULES = (
    "test_golden_master.py",
    "test_default_on_golden.py",
    "test_otf_golden.py",
    "test_fade_golden.py",
    "test_entry_window_golden.py",
)
EVAL_MODULES = (
    "test_assistant_llm_evaluations.py",
    "test_assistant_voice_evaluations.py",
)
BENCHMARK_MODULES = (
    "benchmarks/test_simulate_baseline.py",
    "benchmarks/test_cai_cold_path.py",
    "benchmarks/test_cai_warm_path.py",
)
INTEGRATION_MODULES = (
    "test_otf_integration.py",
    "test_3c_mode_integration.py",
    "test_assistant_lifecycle_integration.py",
)
ORACLE_FUNCTION_MARKS = (
    ("test_apoc_tick_source.py", "test_optional_desk_tick_oracle_is_exact"),
    ("test_apoc_candidates.py", "test_optional_desk_oracle_reports_named_candidate_error"),
    (
        "test_rolling_poc_candidates.py",
        "test_optional_desk_oracle_reports_errors_without_failing_on_miss",
    ),
)

_PYTEST_INVOCATION = re.compile(r"^\s*(?:run:\s+)?pytest\b")
_MARKER_FILTER = re.compile(r"(^|[\s\"'])-m([\s=]|$)")
_XDIST_N = re.compile(r"(^|[\s\"'])-n([\s=]|$)")


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _marker_names(raw: list[str]) -> list[str]:
    return [entry.split(":", 1)[0].strip() for entry in raw]


def _module_pytestmark_is(tree: ast.Module, name: str) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        ):
            continue
        if _is_mark(node.value, name) or _list_has_mark(node.value, name):
            return True
    return False


def _is_mark(node: ast.AST, name: str) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if not isinstance(target, ast.Attribute) or target.attr != name:
        return False
    mark = target.value
    return (
        isinstance(mark, ast.Attribute)
        and mark.attr == "mark"
        and isinstance(mark.value, ast.Name)
        and mark.value.id == "pytest"
    )


def _list_has_mark(node: ast.AST, name: str) -> bool:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return False
    return any(_is_mark(elt, name) for elt in node.elts)


def _function_has_mark(tree: ast.Module, func_name: str, mark_name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return any(_is_mark(decorator, mark_name) for decorator in node.decorator_list)
    return False


def _test_function_names(tree: ast.Module) -> list[str]:
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _parse(rel: str) -> ast.Module:
    path = TESTS / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class _FakeMark:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeItem:
    def __init__(self, names: tuple[str, ...] = ()) -> None:
        self._marks = [_FakeMark(name) for name in names]

    def iter_markers(self):
        return list(self._marks)

    def add_marker(self, mark: object) -> None:
        name = getattr(mark, "name", None)
        if not isinstance(name, str):
            raise AssertionError(f"add_marker expected a named mark, got {mark!r}")
        self._marks.append(_FakeMark(name))


def test_pyproject_registers_the_seven_markers() -> None:
    opts = _pyproject()["tool"]["pytest"]["ini_options"]
    names = _marker_names(opts["markers"])
    assert names == list(REQUIRED_MARKERS)
    addopts = opts.get("addopts", [])
    if isinstance(addopts, str):
        addopts = addopts.split()
    assert "--strict-markers" in addopts
    joined = " ".join(str(item) for item in addopts)
    assert "-m " not in f"{joined} "
    assert "-n" not in addopts
    assert "xdist" not in joined


def test_ci_pytest_cells_stay_full_suite() -> None:
    text = CI_YML.read_text(encoding="utf-8")
    assert "pytest -q --cov=thesistester" in text
    assert "pytest-xdist" not in text
    invocations = 0
    for raw in text.splitlines():
        code = raw.split("#", 1)[0]
        if not _PYTEST_INVOCATION.search(code):
            continue
        invocations += 1
        assert _MARKER_FILTER.search(code) is None, raw
        assert _XDIST_N.search(code) is None, raw
    assert invocations >= 1


def test_collection_hook_defaults_and_preserves_class() -> None:
    src = (TESTS / "conftest.py").read_text(encoding="utf-8")
    assert "def pytest_collection_modifyitems" in src
    assert "item.add_marker(pytest.mark.unit)" in src
    assert "item.add_marker(pytest.mark.integration)" in src

    from tests.conftest import pytest_collection_modifyitems

    unmarked = _FakeItem()
    serial = _FakeItem(("serial",))
    golden = _FakeItem(("golden",))
    serial_golden = _FakeItem(("serial", "golden"))
    already_unit = _FakeItem(("unit",))
    pytest_collection_modifyitems([unmarked, serial, golden, serial_golden, already_unit])
    assert {mark.name for mark in unmarked.iter_markers()} == {"unit"}
    assert {mark.name for mark in serial.iter_markers()} == {"serial", "integration"}
    assert {mark.name for mark in golden.iter_markers()} == {"golden"}
    assert {mark.name for mark in serial_golden.iter_markers()} == {"serial", "golden"}
    assert [mark.name for mark in already_unit.iter_markers()] == ["unit"]


def test_named_suites_carry_class_decorators() -> None:
    for rel in GOLDEN_MODULES:
        assert _module_pytestmark_is(_parse(rel), "golden"), rel
    for rel in EVAL_MODULES:
        assert _module_pytestmark_is(_parse(rel), "eval"), rel
    for rel in BENCHMARK_MODULES:
        assert _module_pytestmark_is(_parse(rel), "benchmark"), rel
    for rel in INTEGRATION_MODULES:
        assert _module_pytestmark_is(_parse(rel), "integration"), rel
    assert _module_pytestmark_is(_parse("test_tick_vap_session20.py"), "oracle")
    for rel, func in ORACLE_FUNCTION_MARKS:
        assert _function_has_mark(_parse(rel), func, "oracle"), f"{rel}:{func}"


def test_mixed_oracle_files_keep_unit_siblings() -> None:
    """Function-level oracle only. Module-level oracle would drop unit from ``-m unit``."""
    for rel, func in ORACLE_FUNCTION_MARKS:
        tree = _parse(rel)
        for name in CLASS_MARKERS:
            assert not _module_pytestmark_is(tree, name), f"{rel} module pytestmark {name}"
        assert _function_has_mark(tree, func, "oracle"), f"{rel}:{func}"
        siblings = [name for name in _test_function_names(tree) if name != func]
        assert siblings, rel
        for sibling in siblings:
            assert not _function_has_mark(tree, sibling, "oracle"), f"{rel}:{sibling}"


def test_ast_helpers_accept_list_and_tuple_pytestmark() -> None:
    listed = ast.parse(
        "import pytest\npytestmark = [pytest.mark.oracle, pytest.mark.skipif(True)]\n"
    )
    tupled = ast.parse("import pytest\npytestmark = (pytest.mark.golden, pytest.mark.skip)\n")
    scalar = ast.parse("import pytest\npytestmark = pytest.mark.eval\n")
    other = ast.parse(
        "import pytest\npytestmark = pytest.mark.skip\npytestmark = pytest.mark.golden\n"
    )
    assert _module_pytestmark_is(listed, "oracle")
    assert not _module_pytestmark_is(listed, "golden")
    assert _module_pytestmark_is(tupled, "golden")
    assert _module_pytestmark_is(scalar, "eval")
    assert _module_pytestmark_is(other, "golden")
    assert not _module_pytestmark_is(other, "eval")


def test_suite_uses_only_registered_or_builtin_marks() -> None:
    allowed = set(REQUIRED_MARKERS) | BUILTIN_MARKS
    unknown: list[str] = []
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr in allowed:
                continue
            mark = node.value
            if (
                isinstance(mark, ast.Attribute)
                and mark.attr == "mark"
                and isinstance(mark.value, ast.Name)
                and mark.value.id == "pytest"
            ):
                unknown.append(f"{path.relative_to(TESTS).as_posix()}:{node.lineno}:{node.attr}")
    assert unknown == []
