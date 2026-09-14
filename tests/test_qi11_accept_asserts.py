"""B-16 / QI-11-06: the 12 accept-path tests must assert tokens or state.

QI-11 §2.5: a loosened validator or a no-op helper stays invisible if the
test is bare no-raise. C-1 / C-3 may land only while these bodies contain
``assert``. Fixture consolidation is a separate PR.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

ACCEPT_TESTS = (
    ("study/test_study_schema.py", "test_fade_and_continuation_triggers_accepted"),
    ("study/test_study_schema.py", "test_direction_in_constants_allowed"),
    ("study/test_study_schema.py", "test_direction_factor_axis_allowed"),
    ("study/test_study_schema.py", "test_same_bar_opposite_direction_tokens_accepted"),
    ("study/test_study_execute.py", "test_study_dir_lock_released_after_context"),
    ("test_backtest_grid_defaults.py", "test_clear_backtest_when_absent_is_safe"),
    ("test_backtest_grid_defaults.py", "test_clear_grid_when_absent_is_safe"),
    (
        "test_signals_fade.py",
        "test_validate_run_spec_accepts_fade_require_close_confirmation",
    ),
    ("test_entry_window_sw3.py", "test_validate_run_spec_accepts_entry_window"),
    (
        "test_15s_primary_persistence.py",
        "test_validate_run_spec_accepts_one_file_15s_primary_for_r12",
    ),
    ("test_execution_artifacts.py", "test_fsync_file_swallows_ebadf"),
    ("test_execution_artifacts.py", "test_fsync_file_swallows_close_oserror"),
)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing {name}")


def _has_assert(fn: ast.FunctionDef) -> bool:
    return any(isinstance(node, ast.Assert) for node in ast.walk(fn))


def test_qi11_06_accept_tests_assert_tokens_or_state() -> None:
    missing: list[str] = []
    for rel, name in ACCEPT_TESTS:
        path = TESTS / rel
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if not _has_assert(_function(tree, name)):
            missing.append(f"{rel}::{name}")
    assert missing == [], f"QI-11-06 accept tests still no-raise: {missing}"
    assert len(ACCEPT_TESTS) == 12
