"""C-19 / QI-04-01: simulate_trades P7 extract behind R22; P4/P6 admission helpers."""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
import types
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from thesistester.engine import sim_core as sim_core_mod
from thesistester.engine.backtest import (
    SimulationResult,
    _simulate_trade_exit,
    simulate_trades,
)
from thesistester.engine.sim_core import BarData


_BACKTEST = Path("thesistester/engine/backtest.py")
_SIM_CORE = Path("thesistester/engine/sim_core.py")
_TZ = "America/New_York"
_TICK = 0.25
_POINT = 50.0

_PUBLIC_SIMULATE_TRADES_PARAMS = (
    ("df", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
    ("signals", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
    ("tick_size", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
    ("point_value", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
    ("stop_loss_ticks", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
    ("take_profit_ticks", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
    ("max_holding_bars", inspect.Parameter.POSITIONAL_OR_KEYWORD, None),
    ("allow_same_bar_exit", inspect.Parameter.POSITIONAL_OR_KEYWORD, True),
    ("commission_per_side", inspect.Parameter.POSITIONAL_OR_KEYWORD, 0.0),
    ("slippage_ticks", inspect.Parameter.POSITIONAL_OR_KEYWORD, 0.0),
    ("flat_by_session_close", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
    ("session_close_time", inspect.Parameter.POSITIONAL_OR_KEYWORD, None),
    ("session_timezone", inspect.Parameter.POSITIONAL_OR_KEYWORD, None),
    ("no_new_entries_after", inspect.Parameter.POSITIONAL_OR_KEYWORD, None),
    ("exposure_policy", inspect.Parameter.POSITIONAL_OR_KEYWORD, "allow_all"),
    ("cooldown_bars_after_exit", inspect.Parameter.POSITIONAL_OR_KEYWORD, 0),
    ("return_skipped_signals", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
    ("entry_window", inspect.Parameter.KEYWORD_ONLY, None),
    ("entry_window_exchange_tz", inspect.Parameter.KEYWORD_ONLY, None),
    ("intrabar_model", inspect.Parameter.KEYWORD_ONLY, "sl_first"),
    ("subtimeframe_data", inspect.Parameter.KEYWORD_ONLY, None),
    ("parent_interval", inspect.Parameter.KEYWORD_ONLY, None),
    ("sub_interval", inspect.Parameter.KEYWORD_ONLY, None),
    ("breakeven_after_r", inspect.Parameter.KEYWORD_ONLY, None),
    ("trailing_after_r", inspect.Parameter.KEYWORD_ONLY, None),
    ("trailing_distance_ticks", inspect.Parameter.KEYWORD_ONLY, None),
    ("return_result", inspect.Parameter.KEYWORD_ONLY, False),
    ("same_bar_opposite_direction", inspect.Parameter.KEYWORD_ONLY, "legacy"),
)

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
    params = inspect.signature(simulate_trades).parameters
    assert tuple((name, p.kind, p.default) for name, p in params.items()) == (
        _PUBLIC_SIMULATE_TRADES_PARAMS
    )


def test_c19_flatten_without_clock_raises_before_r22_call():
    """Helper must fail-closed with the public ValueError, not session_close.hour."""
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 15:50", periods=2, freq="min", tz=_TZ),
            "open": [100.0, 100.1],
            "high": [100.2, 100.3],
            "low": [99.8, 99.9],
            "close": [100.0, 100.1],
            "volume": [100.0, 100.0],
        }
    )
    local = pd.Series(frame["timestamp"])
    with pytest.raises(ValueError, match="requires a valid session_close_time"):
        _simulate_trade_exit(
            bars=BarData.from_frame(frame),
            n_bars=len(frame),
            local_timestamps=local,
            direction="long",
            entry_price=100.0,
            theoretical_entry_price=100.0,
            entry_bar_index=0,
            entry_local_ts=local.iloc[0],
            entry_model="next_bar_open",
            trigger="touch",
            sl_pts=1.0,
            tp_pts=2.0,
            allow_same_bar_exit=True,
            max_holding_bars=None,
            flat_by_session_close=True,
            parsed_session_close=None,
            exit_management_active=False,
            tick_size=_TICK,
            breakeven_after_r=None,
            trailing_after_r=None,
            trailing_distance_ticks=None,
            intrabar_model="sl_first",
            subtimeframe_context=None,
        )


def _origin_main_simulate_trades():
    """Load ``simulate_trades`` from the PR base (origin/main).

    Hex digests are computed live in-process. Do not freeze them as CI goldens.
    """
    from tests.test_journal_triggers import _regression_base_ref

    name = "thesistester.engine._backtest_origin_main"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached.simulate_trades
    ref = _regression_base_ref()
    src = subprocess.check_output(
        ["git", "show", f"{ref}:thesistester/engine/backtest.py"],
        text=True,
    )
    module = types.ModuleType(name)
    module.__file__ = f"<{ref} thesistester/engine/backtest.py>"
    module.__package__ = "thesistester.engine"
    sys.modules[name] = module
    try:
        exec(compile(src, module.__file__, "exec"), module.__dict__)
    except Exception:
        del sys.modules[name]
        raise
    return module.simulate_trades


def _identity_bar(ts: str, o: float = 100.0, h: float = 100.25, l: float = 99.75, c: float = 100.0):
    return {
        "timestamp": pd.Timestamp(ts, tz=_TZ),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": 100.0,
    }


def _identity_touch(bar_index: int, signal_id: int, direction: str = "long", **extra):
    row = {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=_TZ),
        "bar_index": bar_index,
        "trigger": "touch",
        "direction": direction,
        "zone_low": 99.5,
        "zone_high": 100.5,
        "zone_mid": 100.0,
        "level_count": 2,
        "level_names": "A|B",
        "entry_reference_price": 100.0,
        "entry_model": "candidate_next_bar_open",
        "status": "candidate",
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }
    row.update(extra)
    return row


def _identity_three_c(*, signal_id: int, status: str, entry_bar: int):
    return {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=_TZ),
        "bar_index": 0,
        "trigger": "3c",
        "direction": "long",
        "status": status,
        "entry_bar_index": entry_bar,
        "retrace_entry_price": 100.0,
        "zone_low": 99.5,
        "zone_high": 100.5,
        "zone_mid": 100.0,
        "level_count": 2,
        "level_names": "A|B",
        "entry_reference_price": 100.0,
        "entry_model": "3c_retrace_market",
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }


def test_c19_simulate_trades_identity_vs_origin_main():
    """Live vs origin/main — do not freeze hash_dataframe hexes as CI goldens."""
    baseline = _origin_main_simulate_trades()
    wide = dict(stop_loss_ticks=100, take_profit_ticks=100)
    tight = dict(stop_loss_ticks=2, take_profit_ticks=4)
    narrow = pd.DataFrame(
        [
            _identity_bar("2026-01-02 09:30", 100.0, 100.1, 99.9, 100.0),
            _identity_bar("2026-01-02 09:31", 100.05, 100.15, 99.95, 100.05),
            _identity_bar("2026-01-02 09:32", 100.1, 100.2, 100.0, 100.1),
            _identity_bar("2026-01-02 09:33", 100.15, 100.25, 100.05, 100.15),
        ]
    )
    wide_range = pd.DataFrame(
        [
            _identity_bar("2026-01-02 09:30", 100.0, 105.0, 95.0, 100.5),
            _identity_bar("2026-01-02 09:31", 100.5, 105.5, 95.5, 101.0),
            _identity_bar("2026-01-02 09:32", 101.0, 106.0, 96.0, 101.5),
            _identity_bar("2026-01-02 09:33", 101.5, 106.5, 96.5, 102.0),
        ]
    )
    flatten = pd.DataFrame(
        [
            _identity_bar("2026-01-05 15:50"),
            _identity_bar("2026-01-05 15:51"),
            _identity_bar("2026-01-05 16:00"),
            _identity_bar("2026-01-06 09:30"),
        ]
    )
    empty_cap = pd.DataFrame(
        [
            _identity_bar("2026-01-05 17:00"),
            _identity_bar("2026-01-05 17:01"),
            _identity_bar("2026-01-06 09:30"),
        ]
    )
    cases: list[tuple[str, pd.DataFrame, pd.DataFrame, dict]] = [
        ("empty", narrow, pd.DataFrame(), dict(tight, return_result=True)),
        (
            "sl_first both-hit",
            wide_range,
            pd.DataFrame([_identity_touch(0, 1)]),
            dict(tight, return_result=True),
        ),
        (
            "3c void silent + filled",
            wide_range,
            pd.DataFrame(
                [
                    _identity_three_c(signal_id=1, status="void", entry_bar=0),
                    _identity_three_c(signal_id=2, status="filled", entry_bar=1),
                ]
            ),
            dict(tight, return_result=True),
        ),
        (
            "time exit",
            narrow,
            pd.DataFrame([_identity_touch(0, 1)]),
            dict(wide, max_holding_bars=2, return_result=True),
        ),
        (
            "AH1 flatten clock",
            flatten,
            pd.DataFrame([_identity_touch(0, 1)]),
            dict(
                wide,
                flat_by_session_close=True,
                session_close_time="16:00",
                session_timezone=_TZ,
                return_result=True,
            ),
        ),
        (
            "empty session close cap",
            empty_cap,
            pd.DataFrame([_identity_touch(0, 1)]),
            dict(
                wide,
                flat_by_session_close=True,
                session_close_time="16:00",
                session_timezone=_TZ,
                return_result=True,
            ),
        ),
        (
            "exposure + cooldown",
            wide_range,
            pd.DataFrame(
                [
                    _identity_touch(0, 1, direction="long"),
                    _identity_touch(1, 2, direction="long"),
                    _identity_touch(1, 3, direction="short"),
                ]
            ),
            dict(
                tight,
                exposure_policy="single_position",
                cooldown_bars_after_exit=1,
                return_result=True,
            ),
        ),
        (
            "window then cutoff label",
            pd.DataFrame(
                [
                    _identity_bar("2026-01-02 15:50"),
                    _identity_bar("2026-01-02 15:51"),
                    _identity_bar("2026-01-02 15:52"),
                ]
            ),
            pd.DataFrame([_identity_touch(0, 1)]),
            dict(
                tight,
                entry_window={
                    "enabled": True,
                    "mode": "clock_range",
                    "start_time": "09:30",
                    "end_time": "11:00",
                    "timezone": _TZ,
                },
                entry_window_exchange_tz=_TZ,
                no_new_entries_after="15:00",
                session_timezone=_TZ,
                return_result=True,
            ),
        ),
        (
            "BE/trail next-bar",
            narrow,
            pd.DataFrame([_identity_touch(0, 1)]),
            dict(
                stop_loss_ticks=8,
                take_profit_ticks=40,
                breakeven_after_r=0.5,
                trailing_after_r=1.0,
                trailing_distance_ticks=2,
                allow_same_bar_exit=False,
                return_result=True,
            ),
        ),
    ]

    def _unpack(result):
        if isinstance(result, SimulationResult) or type(result).__name__ == "SimulationResult":
            return (
                result.trades,
                result.skipped_signals,
                result.intrabar_diagnostic,
                result.exit_management_diagnostic,
                result.direction_collision_diagnostic,
            )
        return result, None, None, None, None

    for name, df, signals, kwargs in cases:
        owned = simulate_trades(df, signals, _TICK, _POINT, **kwargs)
        prior = baseline(df.copy(), signals.copy(), _TICK, _POINT, **kwargs)
        ot, os_, oi, oe, od = _unpack(owned)
        pt, ps, pi, pe, pdg = _unpack(prior)
        assert_frame_equal(ot.reset_index(drop=True), pt.reset_index(drop=True), check_dtype=False)
        if os_ is not None:
            assert_frame_equal(
                os_.reset_index(drop=True), ps.reset_index(drop=True), check_dtype=False
            )
            assert oi == pi
            assert oe == pe
            assert od == pdg
        else:
            raise AssertionError(f"{name}: expected SimulationResult")
