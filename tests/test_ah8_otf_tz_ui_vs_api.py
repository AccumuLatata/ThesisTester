"""B-1 / QI-04-07: lock H15 OTF/Admit TZ wiring (do not invert the fork).

QI-4 §3 / Appendix A: UI records session ``exchange_tz``; ``api.run_backtest``
records ``inst.exchange_tz``. Admission may match on a fixture; wiring is the lock.

Every OTF/Admit/simulate call is AST-bound (comment / omitted kw / inverted
Name fail closed). Runtime locks the recorded ``session_timezone`` per composer.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from thesistester.api import run_backtest
from thesistester.config import INSTRUMENTS
from thesistester.engine.otf_integration import apply_configured_otf_filter

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKTEST = (REPO_ROOT / "pages" / "7_Backtest.py").read_text(encoding="utf-8")
API = (REPO_ROOT / "thesistester" / "api.py").read_text(encoding="utf-8")

_H15_CALLS = (
    ("apply_configured_otf_filter", "session_timezone"),
    ("normalize_entry_window", "exchange_tz"),
    ("simulate_trades", "entry_window_exchange_tz"),
)


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
    raise AssertionError(f"unexpected kw expression: {ast.unparse(node)}")


def _is_session_state_get_exchange_timezone(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "get"):
        return False
    owner = func.value
    if not (isinstance(owner, ast.Attribute) and owner.attr == "session_state"):
        return False
    if not (isinstance(owner.value, ast.Name) and owner.value.id == "st"):
        return False
    return (
        bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "exchange_timezone"
    )


def _is_inst_exchange_tz_ifexp(node: ast.AST) -> bool:
    """``inst.exchange_tz if inst else "America/New_York"``."""
    if not isinstance(node, ast.IfExp):
        return False
    if not (isinstance(node.test, ast.Name) and node.test.id == "inst"):
        return False
    if ast.unparse(node.body) != "inst.exchange_tz":
        return False
    return isinstance(node.orelse, ast.Constant) and node.orelse.value == "America/New_York"


def assert_exchange_tz_is_data_page_or_instrument(source: str) -> None:
    """Bind ``exchange_tz = session_state.get(...) or inst.exchange_tz`` (H15 UI)."""
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "exchange_tz":
            continue
        val = node.value
        if not (
            isinstance(val, ast.BoolOp) and isinstance(val.op, ast.Or) and len(val.values) == 2
        ):
            raise AssertionError(
                "exchange_tz must be st.session_state.get('exchange_timezone') "
                "or inst.exchange_tz (H15 UI)"
            )
        if not _is_session_state_get_exchange_timezone(val.values[0]):
            raise AssertionError("exchange_tz must read session_state.exchange_timezone first")
        if not _is_inst_exchange_tz_ifexp(val.values[1]):
            raise AssertionError("exchange_tz fallback must be inst.exchange_tz if inst else NY")
        found = True
    if not found:
        raise AssertionError("missing exchange_tz assignment")


def assert_every_call_kw(tree: ast.AST, func_name: str, kw_name: str, expected: str) -> None:
    """Every ``func_name`` call must bind ``kw_name=expected`` (omit/invert fail-closed)."""
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) != func_name:
            continue
        found = True
        bound = False
        for kw in node.keywords:
            if kw.arg != kw_name:
                continue
            got = _kw_expr(kw.value)
            if got != expected:
                raise AssertionError(f"{func_name} {kw_name}={got!r} inverts H15 (want {expected})")
            bound = True
            break
        if not bound:
            raise AssertionError(
                f"{func_name} missing {kw_name}= (positional/omitted inverts the H15 lock)"
            )
    if not found:
        raise AssertionError(f"missing {func_name} call")


def assert_h15_ui_wiring(source: str) -> None:
    assert_exchange_tz_is_data_page_or_instrument(source)
    tree = ast.parse(source)
    for func_name, kw_name in _H15_CALLS:
        assert_every_call_kw(tree, func_name, kw_name, "exchange_tz")


def assert_h15_api_wiring(source: str) -> None:
    fn = _module_function_def(source, "run_backtest")
    for func_name, kw_name in _H15_CALLS:
        assert_every_call_kw(fn, func_name, kw_name, "inst.exchange_tz")


def test_h15_ui_otf_and_admit_use_session_or_instrument_exchange_tz() -> None:
    """Classic Backtest OTF/Admit clocks use session ``exchange_tz`` (H15 UI)."""
    assert_h15_ui_wiring(BACKTEST)


def test_h15_api_otf_and_admit_use_instrument_exchange_tz() -> None:
    """``api.run_backtest`` OTF/Admit clocks are ``inst.exchange_tz`` (H15 API)."""
    assert_h15_api_wiring(API)


def test_h15_wiring_guard_rejects_inverted_or_comment_tz() -> None:
    """Comment / omitted kw / swapped composer expression fail-closed."""
    inverted_assign = (
        "import streamlit as st\n"
        "exchange_tz = inst.exchange_tz\n"
        "apply_configured_otf_filter(session_timezone=exchange_tz)\n"
        "normalize_entry_window(exchange_tz=exchange_tz)\n"
        "simulate_trades(entry_window_exchange_tz=exchange_tz)\n"
    )
    try:
        assert_h15_ui_wiring(inverted_assign)
    except AssertionError:
        pass
    else:
        raise AssertionError("exchange_tz = inst.exchange_tz must invert H15 UI")

    comment_only = (
        "import streamlit as st\n"
        "exchange_tz = inst.exchange_tz\n"
        "# st.session_state.get('exchange_timezone')\n"
        "apply_configured_otf_filter(session_timezone=exchange_tz)\n"
        "normalize_entry_window(exchange_tz=exchange_tz)\n"
        "simulate_trades(entry_window_exchange_tz=exchange_tz)\n"
    )
    try:
        assert_exchange_tz_is_data_page_or_instrument(comment_only)
    except AssertionError:
        pass
    else:
        raise AssertionError("comment-only exchange_timezone get must not bind")

    inverted_otf = (
        "import streamlit as st\n"
        "exchange_tz = st.session_state.get('exchange_timezone') or (\n"
        "    inst.exchange_tz if inst else 'America/New_York'\n"
        ")\n"
        "apply_configured_otf_filter(session_timezone=inst.exchange_tz)\n"
        "normalize_entry_window(exchange_tz=exchange_tz)\n"
        "simulate_trades(entry_window_exchange_tz=exchange_tz)\n"
    )
    try:
        assert_h15_ui_wiring(inverted_otf)
    except AssertionError:
        pass
    else:
        raise AssertionError("OTF session_timezone=inst.exchange_tz must invert H15 UI")

    omitted = (
        "import streamlit as st\n"
        "exchange_tz = st.session_state.get('exchange_timezone') or (\n"
        "    inst.exchange_tz if inst else 'America/New_York'\n"
        ")\n"
        "apply_configured_otf_filter()\n"
        "normalize_entry_window(exchange_tz=exchange_tz)\n"
        "simulate_trades(entry_window_exchange_tz=exchange_tz)\n"
    )
    try:
        assert_h15_ui_wiring(omitted)
    except AssertionError:
        pass
    else:
        raise AssertionError("omitted session_timezone must not bind H15 UI")

    inverted_api = (
        "def run_backtest():\n"
        "    apply_configured_otf_filter(session_timezone=exchange_tz)\n"
        "    normalize_entry_window(exchange_tz=inst.exchange_tz)\n"
        "    simulate_trades(entry_window_exchange_tz=inst.exchange_tz)\n"
    )
    try:
        assert_h15_api_wiring(inverted_api)
    except AssertionError:
        pass
    else:
        raise AssertionError("API OTF session_timezone=exchange_tz must invert H15")


def _h15_probe_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.date_range("2024-01-02 09:30", periods=30, freq="1min", tz="America/New_York")
    close = pd.Series([100.0] * 30)
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
                "bar_index": 10,
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


def test_h15_recorded_session_timezone_differs_per_composer() -> None:
    """Recorded OTF ``session_timezone`` follows each composer when Data-page ≠ instrument."""
    df, signals = _h15_probe_frame()
    inst = INSTRUMENTS["ES"]
    data_page_exchange = "UTC"
    ui_tz = data_page_exchange or inst.exchange_tz
    assert ui_tz != inst.exchange_tz

    ui_otf = apply_configured_otf_filter(
        source_df=df,
        candidate_signals=signals,
        setup_config={},
        session_timezone=ui_tz,
        eth_start=inst.eth_start,
    )
    api = run_backtest(
        df,
        signals,
        instrument="ES",
        config={
            "session_timezone": data_page_exchange,
            "flat_by_session_close": False,
            "stop_loss_ticks": 40,
            "take_profit_ticks": 40,
        },
    )
    api_tz = api["otf_filter_summary"]["session_timezone"]
    assert ui_otf.session_timezone == ui_tz
    assert api_tz == inst.exchange_tz
    assert ui_otf.session_timezone != api_tz
