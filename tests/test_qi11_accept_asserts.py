"""B-16 / QI-11-06: the 12 accept-path tests must assert tokens or state.

QI-11 §2.5: a loosened validator or a no-op helper stays invisible if the
test is bare no-raise. C-1 / C-3 may land only while these bodies contain
a non-tautological ``assert`` plus the named contract needles. ``assert True``
does not satisfy QI-11 §6.8. Fixture consolidation is a separate PR.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

# (relpath, test name, needles that must appear in that function's source)
ACCEPT_TESTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "study/test_study_schema.py",
        "test_fade_and_continuation_triggers_accepted",
        (
            'validated["study"]["factors"]["trigger"] == ["fade", "continuation"]',
            'validated["study"]["stage"]["include"]["trigger"] == ["fade", "continuation"]',
        ),
    ),
    (
        "study/test_study_schema.py",
        "test_direction_in_constants_allowed",
        (
            'validated["study"]["constants"]["direction"] == "long"',
            "VALID_DIRECTIONS",
        ),
    ),
    (
        "study/test_study_schema.py",
        "test_direction_factor_axis_allowed",
        (
            'validated["study"]["factors"]["direction"] == ["long", "short"]',
            "VALID_DIRECTIONS",
        ),
    ),
    (
        "study/test_study_schema.py",
        "test_same_bar_opposite_direction_tokens_accepted",
        (
            'validated["study"]["constants"]["backtest"]["same_bar_opposite_direction"] == token',
            "_VALID_SAME_BAR_OPPOSITE_DIRECTION",
        ),
    ),
    (
        "study/test_study_execute.py",
        "test_study_dir_lock_released_after_context",
        (
            'entered == ["first", "second"]',
            "lock_path.is_file()",
        ),
    ),
    (
        "test_backtest_grid_defaults.py",
        "test_clear_backtest_when_absent_is_safe",
        (
            "get_grid_defaults() == sibling",
            '"backtest_defaults" not in _load_ui_state()',
        ),
    ),
    (
        "test_backtest_grid_defaults.py",
        "test_clear_grid_when_absent_is_safe",
        (
            "get_backtest_defaults() == sibling",
            '"grid_defaults" not in _load_ui_state()',
        ),
    ),
    (
        "test_signals_fade.py",
        "test_validate_run_spec_accepts_fade_require_close_confirmation",
        (
            "validate_run_spec(spec) is None",
            "SETUP_VALID_TRIGGERS",
            'trigger_params"]["require_close_confirmation"] is token',
        ),
    ),
    (
        "test_entry_window_sw3.py",
        "test_validate_run_spec_accepts_entry_window",
        (
            "validate_run_spec(spec) is None",
            '["rth_segments"] == ["rth_open_30m"]',
        ),
    ),
    (
        "test_15s_primary_persistence.py",
        "test_validate_run_spec_accepts_one_file_15s_primary_for_r12",
        (
            "validate_run_spec(spec) is None",
            '["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M',
        ),
    ),
    (
        "test_execution_artifacts.py",
        "test_fsync_file_swallows_ebadf",
        (
            'calls == ["fsync"]',
            'path.read_text(encoding="utf-8") == "{}"',
        ),
    ),
    (
        "test_execution_artifacts.py",
        "test_fsync_file_swallows_close_oserror",
        (
            'calls == ["close", "close"]',
            "path.stat().st_size == len(before)",
        ),
    ),
)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"missing {name}")


def _is_tautological_assert(node: ast.Assert) -> bool:
    test = node.test
    return isinstance(test, ast.Constant) and test.value in (True, False, None, Ellipsis)


def _has_meaningful_assert(fn: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Assert) and not _is_tautological_assert(node)
        for node in ast.walk(fn)
    )


def test_qi11_06_lock_rejects_tautological_assert() -> None:
    tautology = ast.parse("def f():\n    assert True\n")
    meaningful = ast.parse("def f():\n    assert validated['trigger'] == 'fade'\n")
    assert not _has_meaningful_assert(tautology.body[0])
    assert _has_meaningful_assert(meaningful.body[0])


def test_qi11_06_accept_tests_assert_tokens_or_state() -> None:
    missing: list[str] = []
    for rel, name, needles in ACCEPT_TESTS:
        path = TESTS / rel
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        fn = _function(tree, name)
        src = ast.get_source_segment(text, fn)
        if src is None:
            missing.append(f"{rel}::{name}:no-source")
            continue
        if not _has_meaningful_assert(fn):
            missing.append(f"{rel}::{name}:no-meaningful-assert")
        for needle in needles:
            if needle not in src:
                missing.append(f"{rel}::{name}:missing {needle!r}")
    assert missing == [], f"QI-11-06 accept tests still no-raise: {missing}"
    assert len(ACCEPT_TESTS) == 12
