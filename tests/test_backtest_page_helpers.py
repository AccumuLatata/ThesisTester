"""QR D-3 / QI-04-05: Backtest page-helper unit tests (H7 / H15 / display)."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from thesistester.backtest_page_helpers import (
    assemble_otf_filter_clocks,
    clip_trades_for_chart,
    effective_no_new_entries_after,
    format_metric,
    format_metric_int,
    format_win_rate,
    signal_setup_context,
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


def test_format_metric_nan_and_non_numeric() -> None:
    assert format_metric(None) == "—"
    assert format_metric(float("nan")) == "—"
    assert format_metric("x") == "—"
    assert format_metric(1.5) == "1.50"
    assert format_metric_int(None) == 0
    assert format_metric_int("bad") == 0
    assert format_metric_int(3.9) == 3
    assert format_win_rate(None) == "—"
    assert format_win_rate(0.5) == "50.0%"


def test_signal_setup_context_prefers_single_column_name() -> None:
    signals = pd.DataFrame({"setup_name": ["Open drive", "Open drive"]})
    assert (
        signal_setup_context(signals, {"setup_name": "other", "setup_caption": "cap"})
        == "Backtesting signals from saved setup: Open drive • cap"
    )
    multi = pd.DataFrame({"setup_name": ["A", "B"]})
    assert (
        signal_setup_context(multi, None) == "Backtesting signals from multiple saved setups: A, B"
    )
    empty = pd.DataFrame({"direction": ["long"]})
    assert signal_setup_context(empty, {"setup_caption": "only cap"}) == (
        "Backtesting generated signals • only cap"
    )
    assert signal_setup_context(empty, None) is None


def test_clip_trades_for_chart_inclusive_overlap() -> None:
    trades = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(["2024-01-02 09:30", "2024-01-02 11:00"]),
            "exit_timestamp": pd.to_datetime(["2024-01-02 09:45", "2024-01-02 11:15"]),
        }
    )
    clipped = clip_trades_for_chart(
        trades,
        start="2024-01-02 09:40",
        end="2024-01-02 10:00",
    )
    assert list(clipped["entry_timestamp"]) == [pd.Timestamp("2024-01-02 09:30")]
    assert clip_trades_for_chart(None, start=None, end=None) is None
