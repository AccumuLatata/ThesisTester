"""C-19 / QI-04-01: simulate_trades P7 extract behind R22; P4/P6 admission helpers."""

from __future__ import annotations

import ast
from pathlib import Path

from thesistester.engine import sim_core as sim_core_mod
from thesistester.engine.backtest import simulate_trades


_BACKTEST = Path("thesistester/engine/backtest.py")
_SIM_CORE = Path("thesistester/engine/sim_core.py")

_ORCHESTRATOR_HELPERS = (
    "_validate_simulate_trades",
    "_empty_simulation_return",
    "_admit_entry_candidates",
    "_order_candidates_and_da3",
    "_exposure_skip_for_candidate",
    "_simulate_trade_exit",
    "_record_closed_trade",
    "_assemble_simulate_result",
)

_P7_CORE = (
    "compute_session_close_cap",
    "walk_trade_exit",
)

_FORBIDDEN_SIM_CORE_NAMES = frozenset(
    {
        "skip_reason",
        "r_multiple",
        "entry_window",
        "pnl",
        "gross_pnl_points",
        "net_pnl_currency",
        "SKIP_OUTSIDE_ENTRY_WINDOW",
        "SKIP_EMPTY_SESSION_CLOSE_CAP",
    }
)


def _module_tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text())


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing function {name}")


def _called_names(fn: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(fn):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            names.add(child.func.id)
    return names


def test_c19_orchestrator_calls_phase_helpers():
    tree = _module_tree(_BACKTEST)
    defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    calls = _called_names(_function(tree, "simulate_trades"))
    for name in _ORCHESTRATOR_HELPERS:
        assert name in defined, name
        assert name in calls, name


def test_c19_p7_walk_lives_in_sim_core():
    tree = _module_tree(_SIM_CORE)
    defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in _P7_CORE:
        assert name in defined, name
        assert hasattr(sim_core_mod, name)
    p7 = _function(_module_tree(_BACKTEST), "_simulate_trade_exit")
    calls = _called_names(p7)
    assert "compute_session_close_cap" in calls
    assert "walk_trade_exit" in calls
    walk_calls = _called_names(_function(tree, "walk_trade_exit"))
    assert "resolve_trade_bar" in walk_calls


def test_c19_sim_core_holds_no_admission_or_pnl():
    tree = _module_tree(_SIM_CORE)
    names = {child.id for child in ast.walk(tree) if isinstance(child, ast.Name)}
    leaked = names & _FORBIDDEN_SIM_CORE_NAMES
    assert leaked == set()
    source = _SIM_CORE.read_text()
    assert "entry_window_policy" not in source
    assert "skip_reason" not in source
    assert "r_multiple" not in source


def test_c19_flatten_clock_uses_entry_local_normalize():
    fn = _function(_module_tree(_SIM_CORE), "compute_session_close_cap")
    attrs = [child.attr for child in ast.walk(fn) if isinstance(child, ast.Attribute)]
    assert "normalize" in attrs
    source = ast.get_source_segment(_SIM_CORE.read_text(), fn)
    assert source is not None
    assert "entry_local_ts.normalize()" in source


def test_c19_3c_void_stays_silent_continue():
    fn = _function(_module_tree(_BACKTEST), "_admit_entry_candidates")
    src = ast.get_source_segment(_BACKTEST.read_text(), fn)
    assert src is not None
    assert 'trigger == "3c"' in src
    assert "status" in src
    assert "filled" in src
    # Void / OOB 3c must continue without a skip-row emit.
    assert "SKIP_EMPTY_SESSION_CLOSE_CAP" not in src
    continues = [child for child in ast.walk(fn) if isinstance(child, ast.Continue)]
    assert len(continues) >= 3


def test_c19_public_simulate_trades_signature_unchanged():
    import inspect

    params = list(inspect.signature(simulate_trades).parameters)
    assert params[:8] == [
        "df",
        "signals",
        "tick_size",
        "point_value",
        "stop_loss_ticks",
        "take_profit_ticks",
        "max_holding_bars",
        "allow_same_bar_exit",
    ]
    assert "entry_window" in params
    assert "same_bar_opposite_direction" in params
