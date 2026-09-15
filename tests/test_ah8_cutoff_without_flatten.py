"""B-1 / QI-04-07: lock H7 cutoff-without-flatten (do not invert the fork).

QI-4 §3 / Appendix A: UI helper flatten-off + cutoff ``None`` fills; headless
``api.run_backtest`` flatten-off + YAML cutoff skips ``after_entry_cutoff``.

Wiring is AST-bound (comment / unused-formula / other-widget ``disabled=``
needles fail closed). Runtime recipes stay the Appendix A fixture.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from thesistester.api import run_backtest
from thesistester.engine.backtest import simulate_trades

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES = REPO_ROOT / "pages"
HELPERS = REPO_ROOT / "thesistester"
CLASSIC_EXPORT = REPO_ROOT / "thesistester" / "classic_export.py"

_BACKTEST = "7_Backtest.py"
_GRID = "8_Grid_Search.py"
_PAGE_ENGINE = {
    _BACKTEST: ("simulate_trades", "backtest_no_new_entries_after"),
    _GRID: ("run_sl_tp_grid", "grid_no_new_entries_after"),
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _module_function_def(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing module-level def {name}")


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _kw_expr(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return ast.unparse(node)
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Name)
    ):
        return f"not {node.operand.id}"
    raise AssertionError(f"unexpected kw expression: {ast.unparse(node)}")


def _is_st_attr_call(node: ast.AST, attr: str) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != attr:
        return False
    value = node.func.value
    if isinstance(value, ast.Name) and value.id == "st":
        return True
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "sidebar"
        and isinstance(value.value, ast.Name)
        and value.value.id == "st"
    )


def _const_kw(call: ast.Call, name: str) -> object:
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def _is_strip_or_none(node: ast.AST) -> bool:
    """``no_new_entries_after.strip() or None``."""
    if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or):
        return False
    if len(node.values) != 2:
        return False
    call, none = node.values
    if not (isinstance(none, ast.Constant) and none.value is None):
        return False
    if not isinstance(call, ast.Call) or call.args or call.keywords:
        return False
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "strip"
        and isinstance(func.value, ast.Name)
        and func.value.id == "no_new_entries_after"
    )


def _is_flatten_gated_none(node: ast.AST) -> bool:
    """``(no_new_entries_after.strip() or None) if flat_by_session_close else None``."""
    if not isinstance(node, ast.IfExp):
        return False
    if not (isinstance(node.test, ast.Name) and node.test.id == "flat_by_session_close"):
        return False
    if not (isinstance(node.orelse, ast.Constant) and node.orelse.value is None):
        return False
    return _is_strip_or_none(node.body)


def assert_effective_cutoff_forces_none_when_flatten_off(source: str) -> None:
    """Bind ``effective_no_new_entries_after`` (comment / unused Name fail-closed)."""
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "effective_no_new_entries_after":
            continue
        if not _is_flatten_gated_none(node.value):
            raise AssertionError(
                "effective_no_new_entries_after must be "
                "(no_new_entries_after.strip() or None) if flat_by_session_close else None"
            )
        found = True
    if not found:
        raise AssertionError("missing effective_no_new_entries_after assignment")


def assert_effective_cutoff_helper_function(source: str) -> None:
    """D-3: H7 IfExp lives in ``effective_no_new_entries_after`` (not a comment)."""
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "effective_no_new_entries_after":
            continue
        returns = [stmt for stmt in node.body if isinstance(stmt, ast.Return)]
        if not returns:
            raise AssertionError("effective_no_new_entries_after missing return")
        if not _is_flatten_gated_none(returns[0].value):
            raise AssertionError(
                "effective_no_new_entries_after must return "
                "(no_new_entries_after.strip() or None) if flat_by_session_close else None"
            )
        return
    raise AssertionError("missing effective_no_new_entries_after helper")


def assert_cutoff_widget_disabled_when_flatten_off(source: str, widget_key: str) -> None:
    """Bind ``disabled=not flat_by_session_close`` on the cutoff text_input only."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not _is_st_attr_call(node, "text_input"):
            continue
        if _const_kw(node, "key") != widget_key:
            continue
        for kw in node.keywords:
            if kw.arg != "disabled":
                continue
            if _kw_expr(kw.value) != "not flat_by_session_close":
                raise AssertionError(
                    f"{widget_key} disabled= must be not flat_by_session_close, "
                    f"got {_kw_expr(kw.value)}"
                )
            return
        raise AssertionError(f"{widget_key} text_input missing disabled=")
    raise AssertionError(f"missing st.text_input key={widget_key!r}")


def assert_engine_uses_effective_cutoff(source: str, engine_name: str) -> None:
    """Every engine call must pass the gated Name (raw widget / omit fail-closed)."""
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) != engine_name:
            continue
        found = True
        bound = False
        for kw in node.keywords:
            if kw.arg != "no_new_entries_after":
                continue
            if _kw_expr(kw.value) != "effective_no_new_entries_after":
                raise AssertionError(
                    f"{engine_name} no_new_entries_after={_kw_expr(kw.value)!r} "
                    "inverts H7 (want effective_no_new_entries_after)"
                )
            bound = True
            break
        if not bound:
            raise AssertionError(
                f"{engine_name} missing no_new_entries_after= "
                "(positional/omitted inverts the H7 lock)"
            )
    if not found:
        raise AssertionError(f"missing {engine_name} call")


def _is_flatten_off_compare(test: ast.AST) -> bool:
    """``backtest.get("flat_by_session_close") is False``."""
    if not isinstance(test, ast.Compare):
        return False
    if not (len(test.ops) == 1 and isinstance(test.ops[0], ast.Is)):
        return False
    if not (
        len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value is False
    ):
        return False
    call = test.left
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "get"):
        return False
    if not (isinstance(func.value, ast.Name) and func.value.id == "backtest"):
        return False
    return (
        bool(call.args)
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "flat_by_session_close"
    )


def _assigns_cutoff_none(stmts: list[ast.stmt]) -> bool:
    for stmt in stmts:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "backtest"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "no_new_entries_after"
                and isinstance(stmt.value, ast.Constant)
                and stmt.value.value is None
            ):
                return True
        if isinstance(stmt, ast.If) and _assigns_cutoff_none(stmt.body):
            return True
    return False


def assert_classic_export_forces_none_when_flatten_off(source: str) -> None:
    """Bind classic_export None-force to flatten-off (unconditional None fail-closed)."""
    fn = _module_function_def(source, "_normalize_session_exit_fields")
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and _is_flatten_off_compare(node.test):
            if _assigns_cutoff_none(node.body):
                return
    raise AssertionError(
        "_normalize_session_exit_fields must set no_new_entries_after=None "
        "only when flat_by_session_close is False"
    )


def _h7_probe_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Appendix A H7 recipe: bars from 15:00; candidate at bar 30 (15:30)."""
    idx = pd.date_range("2024-01-02 15:00", periods=40, freq="1min", tz="America/New_York")
    close = pd.Series([100.0] * 40)
    df = pd.DataFrame(
        {
            "timestamp": idx,
            "open": close,
            "high": close + 0.25,
            "low": close - 0.25,
            "close": close,
            "volume": 100,
        }
    )
    signals = pd.DataFrame(
        [
            {
                "signal_id": 1,
                "bar_index": 30,
                "trigger": "touch",
                "direction": "long",
                "zone_low": 99.0,
                "zone_high": 101.0,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "x",
            }
        ]
    )
    return df, signals


def _skip_reasons(skipped: pd.DataFrame | None) -> list[str]:
    if skipped is None or skipped.empty:
        return []
    return list(skipped["skip_reason"])


def test_h7_ui_and_grid_force_cutoff_none_when_flatten_off() -> None:
    """Classic composers gate cutoff on flatten (H7 UI side)."""
    for page, (engine_name, widget_key) in _PAGE_ENGINE.items():
        if page == _BACKTEST:
            assert_effective_cutoff_helper_function(_read(HELPERS / "backtest_page_helpers.py"))
            assert_cutoff_widget_disabled_when_flatten_off(
                _read(HELPERS / "backtest_sidebar_page_helpers.py"), widget_key
            )
            assert_engine_uses_effective_cutoff(
                _read(HELPERS / "backtest_run_page_helpers.py"), engine_name
            )
            continue
        source = _read(PAGES / page)
        assert_effective_cutoff_forces_none_when_flatten_off(source)
        assert_cutoff_widget_disabled_when_flatten_off(source, widget_key)
        assert_engine_uses_effective_cutoff(source, engine_name)
    assert_classic_export_forces_none_when_flatten_off(_read(CLASSIC_EXPORT))


def test_h7_wiring_guard_rejects_comment_unused_and_other_widget() -> None:
    """File-level / comment / unused formula / sibling disabled= fail-closed."""
    comment_only = (
        "effective_no_new_entries_after = no_new_entries_after\n"
        "# (no_new_entries_after.strip() or None) if flat_by_session_close else None\n"
        "simulate_trades(no_new_entries_after=effective_no_new_entries_after)\n"
    )
    try:
        assert_effective_cutoff_forces_none_when_flatten_off(comment_only)
    except AssertionError:
        pass
    else:
        raise AssertionError("comment-only H7 formula must not bind")

    unused_formula = (
        "effective_no_new_entries_after = (\n"
        "    (no_new_entries_after.strip() or None) if flat_by_session_close else None\n"
        ")\n"
        "simulate_trades(no_new_entries_after=no_new_entries_after)\n"
    )
    try:
        assert_engine_uses_effective_cutoff(unused_formula, "simulate_trades")
    except AssertionError:
        pass
    else:
        raise AssertionError("unused effective_no_new_entries_after must not bind simulate_trades")

    sibling_disabled = (
        "import streamlit as st\n"
        'st.text_input("Session close time", key="backtest_session_close_time", '
        "disabled=not flat_by_session_close)\n"
        'st.text_input("No new entries after (optional)", '
        'key="backtest_no_new_entries_after")\n'
    )
    try:
        assert_cutoff_widget_disabled_when_flatten_off(
            sibling_disabled, "backtest_no_new_entries_after"
        )
    except AssertionError:
        pass
    else:
        raise AssertionError("sibling-widget disabled= must not bind the cutoff input")

    unconditional_none = (
        "def _normalize_session_exit_fields(backtest):\n"
        '    backtest["no_new_entries_after"] = None\n'
    )
    try:
        assert_classic_export_forces_none_when_flatten_off(unconditional_none)
    except AssertionError:
        pass
    else:
        raise AssertionError("unconditional classic_export None must not bind flatten-off")


def test_h7_ui_style_none_cutoff_fills_when_flatten_off() -> None:
    """UI helper: flatten off forces cutoff None → 1 fill (Appendix A)."""
    df, signals = _h7_probe_frame()
    ui = simulate_trades(
        df,
        signals,
        tick_size=0.25,
        point_value=2.0,
        stop_loss_ticks=40,
        take_profit_ticks=40,
        flat_by_session_close=False,
        no_new_entries_after=None,
        return_result=True,
    )
    assert len(ui.trades) == 1
    assert "after_entry_cutoff" not in _skip_reasons(ui.skipped_signals)


def test_h7_api_applies_cutoff_when_flatten_is_off() -> None:
    """Headless composer applies YAML cutoff with flatten off (H7 API side)."""
    df, signals = _h7_probe_frame()
    api = run_backtest(
        df,
        signals,
        instrument="MNQ",
        config={
            "flat_by_session_close": False,
            "no_new_entries_after": "15:00",
            "stop_loss_ticks": 40,
            "take_profit_ticks": 40,
        },
    )
    assert len(api["trades"]) == 0
    assert _skip_reasons(api["skipped_signals"]) == ["after_entry_cutoff"]
