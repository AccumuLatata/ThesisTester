"""B-15 / QI-11-05: pytest marker set is registered; CI stays the full suite.

Warn-first: unmarked tests become ``unit`` at collection. Unknown marker
names fail (``--strict-markers``). Do not add ``-m unit`` to G-1 cells or
xdist before AppTest ``serial`` (already required by the harness lock).
"""

from __future__ import annotations

import ast
import importlib
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
        return _is_mark(node.value, name) or _list_has_mark(node.value, name)
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
    if not isinstance(node, ast.List):
        return False
    return any(_is_mark(elt, name) for elt in node.elts)


def _function_has_mark(tree: ast.Module, func_name: str, mark_name: str) -> bool:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return any(_is_mark(decorator, mark_name) for decorator in node.decorator_list)
    return False


def _parse(rel: str) -> ast.Module:
    path = TESTS / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


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
    assert "-m unit" not in text
    assert "-m integration" not in text
    assert "pytest-xdist" not in text


def test_collection_hook_defaults_unmarked_to_unit() -> None:
    src = (TESTS / "conftest.py").read_text(encoding="utf-8")
    assert "def pytest_collection_modifyitems" in src
    assert "item.add_marker(pytest.mark.unit)" in src
    assert "item.add_marker(pytest.mark.integration)" in src


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
