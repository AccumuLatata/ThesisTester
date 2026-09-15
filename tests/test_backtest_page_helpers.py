"""QR D-3 / QI-04-05: Backtest page-helper unit tests (H7 cutoff + H15 OTF TZ)."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from thesistester.backtest_page_helpers import (
    assemble_otf_filter_clocks,
    effective_no_new_entries_after,
)
from thesistester.config import INSTRUMENTS

HELPERS = Path(__file__).resolve().parents[1] / "thesistester" / "backtest_page_helpers.py"


def _effective_cutoff_function() -> ast.FunctionDef:
    tree = ast.parse(HELPERS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "effective_no_new_entries_after":
            return node
    raise AssertionError("missing effective_no_new_entries_after")


def _is_strip_or_none(node: ast.AST) -> bool:
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
    if not isinstance(node, ast.IfExp):
        return False
    if not (isinstance(node.test, ast.Name) and node.test.id == "flat_by_session_close"):
        return False
    if not (isinstance(node.orelse, ast.Constant) and node.orelse.value is None):
        return False
    return _is_strip_or_none(node.body)


def test_effective_no_new_entries_after_forces_none_when_flatten_off() -> None:
    """H7: flatten off always None, even when a cutoff string is present."""
    assert effective_no_new_entries_after(False, "15:45") is None
    assert effective_no_new_entries_after(False, "  15:45  ") is None
    assert effective_no_new_entries_after(False, "") is None


def test_effective_no_new_entries_after_strips_when_flatten_on() -> None:
    """H7: flatten on keeps a non-empty cutoff and treats whitespace as None."""
    assert effective_no_new_entries_after(True, "15:45") == "15:45"
    assert effective_no_new_entries_after(True, "  15:45  ") == "15:45"
    assert effective_no_new_entries_after(True, "") is None
    assert effective_no_new_entries_after(True, "   ") is None


def test_effective_no_new_entries_after_body_is_h7_ifexp() -> None:
    """Lock the helper return to the H7 IfExp (comment-only must not bind)."""
    fn = _effective_cutoff_function()
    returns = [n for n in fn.body if isinstance(n, ast.Return)]
    assert returns, "effective_no_new_entries_after must return the H7 formula"
    assert _is_flatten_gated_none(returns[0].value)


@pytest.mark.parametrize(
    ("exchange_timezone", "eth_start", "expected_eth"),
    [
        ("Europe/Berlin", "18:00", "18:00"),
        ("America/New_York", "18:00", "18:00"),
        ("UTC", "", ""),
    ],
)
def test_assemble_otf_filter_clocks_uses_data_page_tz_not_instrument_exchange(
    exchange_timezone: str, eth_start: str, expected_eth: str
) -> None:
    """H15: session_timezone is the Data-page TZ; eth_start comes from instrument."""
    instrument = SimpleNamespace(exchange_tz="America/Chicago", eth_start=eth_start)
    clocks = assemble_otf_filter_clocks(exchange_timezone, instrument)
    assert clocks["session_timezone"] == exchange_timezone
    assert clocks["session_timezone"] != instrument.exchange_tz
    assert clocks["eth_start"] == expected_eth


def test_assemble_otf_filter_clocks_none_instrument() -> None:
    clocks = assemble_otf_filter_clocks("Europe/Berlin", None)
    assert clocks == {"session_timezone": "Europe/Berlin", "eth_start": None}


def test_assemble_otf_filter_clocks_es_preset() -> None:
    clocks = assemble_otf_filter_clocks("Europe/Berlin", INSTRUMENTS["ES"])
    assert clocks["session_timezone"] == "Europe/Berlin"
    assert clocks["eth_start"] == "18:00"
    assert clocks["session_timezone"] != INSTRUMENTS["ES"].exchange_tz
