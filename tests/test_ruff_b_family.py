"""B-17 / QI-12-09: ruff ``B`` is the first widening family.

QI-12 §2.5: 44 hits at probe (19 B905 · 18 B009 · 4 B023). One family per
PR; never ``S`` on ``tests/``; never ``PLR2004`` first. Tests ignore noisy
``B`` codes; ``B023`` (C1 loop-variable) stays enforced.

Fail-closed: exact select / test-ignore lists (a ``B`` prefix would swallow
``B023``); no ``extend-select``; product ``zip(..., strict=False)`` only on
ragged or sliding-window sites; the two remaining B023 closures bind loop
vars as defaults and the sidecar mock keeps urllib ``read(amt=None)``.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

tomllib = importlib.import_module("tomllib" if sys.version_info >= (3, 11) else "tomli")

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SELECT = ["E4", "E7", "E9", "F", "W", "B"]
REQUIRED_TEST_IGNORES = ["E741", "B009", "B905", "B017", "B904"]
PRODUCT_ROOTS = (ROOT / "thesistester", ROOT / "pages")
# Sliding-window ``zip(xs, xs[1:])`` or ragged ``split("|")`` name/price pairs.
ALLOWED_STRICT_FALSE_COUNTS = {
    "thesistester/engine/intrabar.py": 2,
    "thesistester/analytics/walk_forward.py": 1,
    "thesistester/analytics/excursions.py": 1,
    "thesistester/engine/candidate_level.py": 1,
    "thesistester/engine/signals.py": 1,
}
INVARIANT_STRICT_TRUE = (
    ("thesistester/levels/tpo.py", 1),
    ("thesistester/study/observatory.py", 2),
    ("thesistester/analytics/metrics.py", 1),
    ("thesistester/analytics/time_analysis.py", 1),
    ("pages/16_Study_Observatory.py", 1),
)


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _swallows_b023(code: str) -> bool:
    return "B023".startswith(code)


def _is_zip_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "zip"
    )


def _zip_strict_value(node: ast.Call) -> bool | None:
    for keyword in node.keywords:
        if keyword.arg != "strict":
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, bool):
            return keyword.value.value
        return None
    return None


def _product_py_files() -> list[Path]:
    files: list[Path] = []
    for root in PRODUCT_ROOTS:
        files.extend(path for path in root.rglob("*.py") if path.is_file())
    return sorted(files)


def _zip_strict_counts(path: Path) -> tuple[int, int, list[int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    true_n = 0
    false_n = 0
    missing: list[int] = []
    for node in ast.walk(tree):
        if not _is_zip_call(node):
            continue
        strict = _zip_strict_value(node)
        if strict is True:
            true_n += 1
        elif strict is False:
            false_n += 1
        else:
            missing.append(node.lineno)
    return true_n, false_n, missing


def test_ruff_select_is_r9_plus_b_only() -> None:
    lint = _pyproject()["tool"]["ruff"]["lint"]
    assert lint["select"] == REQUIRED_SELECT
    assert "extend-select" not in lint
    assert "ignore" not in lint
    joined = ",".join(lint["select"])
    assert "S" not in lint["select"]
    assert "PLR2004" not in joined
    assert "PL" not in lint["select"]


def test_tests_ignore_noisy_b_but_keep_b023() -> None:
    ignores = _pyproject()["tool"]["ruff"]["lint"]["per-file-ignores"]
    assert ignores["tests/**"] == REQUIRED_TEST_IGNORES
    for key, codes in ignores.items():
        assert "S" not in codes, key
        assert "S101" not in codes, key
        assert "PLR2004" not in codes, key
        swallowed = [code for code in codes if _swallows_b023(code)]
        assert swallowed == [], f"{key} swallows B023 via {swallowed}"


def test_product_zip_strict_false_is_allowlisted() -> None:
    """B905 silence via strict=False is only for sliding/ragged zips.

    Equal-length invariants (groupby keys, TPO bucket↔bar, cohort tokens)
    must stay ``strict=True`` so a length drift raises instead of dropping
    bars, group columns, or Active-cohort labels.
    """
    found_false: dict[str, int] = {}
    found_true: dict[str, int] = {}
    missing_strict: list[str] = []
    for path in _product_py_files():
        rel = path.relative_to(ROOT).as_posix()
        true_n, false_n, missing = _zip_strict_counts(path)
        if false_n:
            found_false[rel] = false_n
        if true_n:
            found_true[rel] = true_n
        missing_strict.extend(f"{rel}:{lineno}" for lineno in missing)
    assert missing_strict == [], missing_strict
    assert found_false == ALLOWED_STRICT_FALSE_COUNTS
    for rel, expected in INVARIANT_STRICT_TRUE:
        assert found_true.get(rel, 0) >= expected, rel


def test_benchmark_simulate_trades_lambda_binds_loop_vars() -> None:
    path = ROOT / "tests" / "benchmarks" / "run.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[ast.Lambda] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Lambda) or not isinstance(node.body, ast.Call):
            continue
        func = node.body.func
        if isinstance(func, ast.Name) and func.id == "simulate_trades":
            found.append(node)
    assert len(found) == 1, found
    names = [arg.arg for arg in found[0].args.args]
    assert names == ["data", "signals", "max_holding_bars"]
    defaults = found[0].args.defaults
    assert len(defaults) == 3
    for name, default in zip(names, defaults, strict=True):
        assert isinstance(default, ast.Name) and default.id == name, name


def test_voice_health_mock_read_binds_payload_and_keeps_amt() -> None:
    path = ROOT / "tests" / "test_assistant_voice_realtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    host = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_probe_sidecar_health_rejects_truthy_non_bool_ok"
    )
    reads = [
        node
        for node in ast.walk(host)
        if isinstance(node, ast.FunctionDef) and node.name == "read"
    ]
    assert len(reads) == 1, reads
    names = [arg.arg for arg in reads[0].args.args]
    assert names == ["self", "amt", "payload"]
    defaults = reads[0].args.defaults
    assert len(defaults) == 2
    assert isinstance(defaults[0], ast.Constant) and defaults[0].value is None
    assert isinstance(defaults[1], ast.Name) and defaults[1].id == "payload"
