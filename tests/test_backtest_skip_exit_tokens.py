"""C-18 / QI-04-09: skip/exit emit sites stay inside the frozen vocabulary."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from thesistester.analytics.entry_window import (
    AFTER_ENTRY_CUTOFF_REASON,
    OUTSIDE_ENTRY_WINDOW_REASON,
    partition_skip_counts,
)
from thesistester.engine.backtest import (
    EXIT_BE,
    EXIT_DATA_END,
    EXIT_EOD,
    EXIT_INTRABAR_PATH_SUFFIX,
    EXIT_MANAGED_STOP_REASONS,
    EXIT_REASONS,
    EXIT_SESSION_CLOSE,
    EXIT_SL,
    EXIT_SUBTIMEFRAME_FALLBACK_SUFFIX,
    EXIT_SUBTIMEFRAME_SUFFIX,
    EXIT_TIME,
    EXIT_TP,
    EXIT_TRAIL,
    SKIP_AFTER_ENTRY_CUTOFF,
    SKIP_COOLDOWN_ACTIVE,
    SKIP_DIRECTION_CONFLICT,
    SKIP_EMPTY_SESSION_CLOSE_CAP,
    SKIP_OUTSIDE_ENTRY_WINDOW,
    SKIP_OVERLAPPING_DIRECTION,
    SKIP_OVERLAPPING_POSITION,
    SKIP_OVERLAPPING_SETUP,
    SKIP_REASONS,
    _exit_reason_with_suffix,
)


_BACKTEST = Path("thesistester/engine/backtest.py")
_ENTRY_WINDOW = Path("thesistester/analytics/entry_window.py")

_EXIT_SUFFIX_NAMES = frozenset(
    {
        "EXIT_INTRABAR_PATH_SUFFIX",
        "EXIT_SUBTIMEFRAME_SUFFIX",
        "EXIT_SUBTIMEFRAME_FALLBACK_SUFFIX",
    }
)
_EXIT_ASSIGN_TOKEN_NAMES = frozenset(
    {
        "EXIT_TIME",
        "EXIT_DATA_END",
        "EXIT_SESSION_CLOSE",
        "EXIT_EOD",
    }
)
_EXIT_SUFFIX_CONSTANTS = (
    EXIT_INTRABAR_PATH_SUFFIX,
    EXIT_SUBTIMEFRAME_SUFFIX,
    EXIT_SUBTIMEFRAME_FALLBACK_SUFFIX,
)


def _module_tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text())


def _imported_module_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _is_skip_reason_target(target: ast.AST) -> bool:
    if isinstance(target, ast.Name) and target.id == "skip_reason":
        return True
    if isinstance(target, ast.Subscript):
        sl = target.slice
        return isinstance(sl, ast.Constant) and sl.value == "skip_reason"
    return False


def _skip_emit_nodes(tree: ast.AST) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "skip_reason":
                    nodes.append(value)
        if isinstance(node, ast.Assign):
            if any(_is_skip_reason_target(target) for target in node.targets):
                nodes.append(node.value)
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            if _is_skip_reason_target(node.target):
                nodes.append(node.value)
    return nodes


def _exit_assign_nodes(tree: ast.AST) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "exit_reason"
                for target in node.targets
            ):
                nodes.append(node.value)
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name) and node.target.id == "exit_reason":
                nodes.append(node.value)
    return nodes


def test_skip_and_exit_token_values_unchanged():
    assert SKIP_OUTSIDE_ENTRY_WINDOW == "outside_entry_window"
    assert SKIP_AFTER_ENTRY_CUTOFF == "after_entry_cutoff"
    assert SKIP_DIRECTION_CONFLICT == "direction_conflict"
    assert SKIP_COOLDOWN_ACTIVE == "cooldown_active"
    assert SKIP_OVERLAPPING_POSITION == "overlapping_position"
    assert SKIP_OVERLAPPING_DIRECTION == "overlapping_direction"
    assert SKIP_OVERLAPPING_SETUP == "overlapping_setup"
    assert SKIP_EMPTY_SESSION_CLOSE_CAP == "empty_session_close_cap"
    assert EXIT_SL == "SL"
    assert EXIT_TP == "TP"
    assert EXIT_BE == "BE"
    assert EXIT_TRAIL == "TRAIL"
    assert EXIT_TIME == "TIME"
    assert EXIT_DATA_END == "DATA_END"
    assert EXIT_SESSION_CLOSE == "SESSION_CLOSE"
    assert EXIT_EOD == "EOD"
    assert EXIT_INTRABAR_PATH_SUFFIX == "_intrabar_path"
    assert EXIT_SUBTIMEFRAME_SUFFIX == "_subtimeframe"
    assert EXIT_SUBTIMEFRAME_FALLBACK_SUFFIX == "_subtimeframe_fallback"
    assert OUTSIDE_ENTRY_WINDOW_REASON == SKIP_OUTSIDE_ENTRY_WINDOW
    assert AFTER_ENTRY_CUTOFF_REASON == SKIP_AFTER_ENTRY_CUTOFF
    assert EXIT_MANAGED_STOP_REASONS == frozenset({EXIT_BE, EXIT_TRAIL})
    assert EXIT_MANAGED_STOP_REASONS <= EXIT_REASONS


def test_entry_window_does_not_import_engine_backtest():
    """Focus helpers must not load ``thesistester.engine`` for two aliases."""
    imported = _imported_module_names(_module_tree(_ENTRY_WINDOW))
    leaked = {
        name
        for name in imported
        if name == "thesistester.engine.backtest"
        or name.startswith("thesistester.engine.backtest.")
        or name == "thesistester.engine"
        or name.startswith("thesistester.engine.")
    }
    assert leaked == []


def test_every_skip_emit_site_uses_frozen_skip_reason():
    tree = _module_tree(_BACKTEST)
    names: list[str] = []
    for node in _skip_emit_nodes(tree):
        if isinstance(node, ast.Name) and node.id == "skip_reason":
            continue
        if isinstance(node, ast.Name) and node.id.startswith("SKIP_"):
            names.append(node.id)
            continue
        raise AssertionError(f"unhandled skip_reason emit {ast.dump(node)}")
    assert names
    from thesistester.engine import backtest as backtest_mod

    emitted = {getattr(backtest_mod, name) for name in names}
    assert emitted == set(SKIP_REASONS)


def test_every_exit_assign_is_token_or_composed_suffix():
    tree = _module_tree(_BACKTEST)
    from thesistester.engine import backtest as backtest_mod

    for node in _exit_assign_nodes(tree):
        if isinstance(node, ast.Name):
            assert node.id in _EXIT_ASSIGN_TOKEN_NAMES, ast.dump(node)
            assert getattr(backtest_mod, node.id) in EXIT_REASONS
            continue
        if isinstance(node, ast.Attribute):
            assert node.attr in {"exit_kind", "active_reason"}, ast.dump(node)
            continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id == "_exit_reason_with_suffix", ast.dump(node)
            assert len(node.args) == 2
            suffix_node = node.args[1]
            assert isinstance(suffix_node, ast.Name), ast.dump(node)
            assert suffix_node.id in _EXIT_SUFFIX_NAMES
            suffix = getattr(backtest_mod, suffix_node.id)
            for kind in (EXIT_SL, EXIT_TP):
                composed = _exit_reason_with_suffix(kind, suffix)
                assert composed in EXIT_REASONS
            continue
        raise AssertionError(f"unhandled exit_reason emit {ast.dump(node)}")


def test_exit_reasons_cover_every_sl_tp_suffix_composition():
    for kind in (EXIT_SL, EXIT_TP):
        for suffix in _EXIT_SUFFIX_CONSTANTS:
            composed = f"{kind}{suffix}"
            assert composed in EXIT_REASONS
            assert _exit_reason_with_suffix(kind, suffix) == composed
    bare = {
        EXIT_SL,
        EXIT_TP,
        EXIT_BE,
        EXIT_TRAIL,
        EXIT_TIME,
        EXIT_DATA_END,
        EXIT_SESSION_CLOSE,
        EXIT_EOD,
    }
    composed = {
        f"{kind}{suffix}" for kind in (EXIT_SL, EXIT_TP) for suffix in _EXIT_SUFFIX_CONSTANTS
    }
    assert EXIT_REASONS == bare | composed


def test_exit_reason_with_suffix_rejects_unknown_composition():
    with pytest.raises(ValueError, match="not in EXIT_REASONS"):
        _exit_reason_with_suffix(EXIT_SL, "_not_a_path")
    with pytest.raises(ValueError, match="not in EXIT_REASONS"):
        _exit_reason_with_suffix(EXIT_TIME, EXIT_INTRABAR_PATH_SUFFIX)


def test_partition_skip_counts_covers_every_skip_reason():
    for reason in sorted(SKIP_REASONS):
        counts = partition_skip_counts(pd.DataFrame({"skip_reason": [reason]}))
        assert counts["total"] == 1
        if reason == SKIP_OUTSIDE_ENTRY_WINDOW:
            assert counts[OUTSIDE_ENTRY_WINDOW_REASON] == 1
            assert counts[AFTER_ENTRY_CUTOFF_REASON] == 0
            assert counts["other"] == 0
        elif reason == SKIP_AFTER_ENTRY_CUTOFF:
            assert counts[AFTER_ENTRY_CUTOFF_REASON] == 1
            assert counts[OUTSIDE_ENTRY_WINDOW_REASON] == 0
            assert counts["other"] == 0
        else:
            assert counts["other"] == 1
            assert counts[OUTSIDE_ENTRY_WINDOW_REASON] == 0
            assert counts[AFTER_ENTRY_CUTOFF_REASON] == 0


def test_partition_skip_counts_keys_are_vocabulary_tokens():
    tree = _module_tree(_ENTRY_WINDOW)
    found_window = False
    found_cutoff = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "partition_skip_counts":
            names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
            found_window = "OUTSIDE_ENTRY_WINDOW_REASON" in names
            found_cutoff = "AFTER_ENTRY_CUTOFF_REASON" in names
    assert found_window and found_cutoff
    empty = partition_skip_counts(None)
    assert set(empty) == {
        "total",
        OUTSIDE_ENTRY_WINDOW_REASON,
        AFTER_ENTRY_CUTOFF_REASON,
        "other",
    }
