"""B-1 / QI-04-07: lock H15 OTF/Admit TZ wiring (do not invert the fork)."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKTEST = (REPO_ROOT / "pages" / "7_Backtest.py").read_text(encoding="utf-8")
API = (REPO_ROOT / "thesistester" / "api.py").read_text(encoding="utf-8")


def _call_kwargs(source: str, func_name: str) -> list[dict[str, str]]:
    tree = ast.parse(source)
    found: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name != func_name:
            continue
        kwargs: dict[str, str] = {}
        for kw in node.keywords:
            if kw.arg is None:
                continue
            if isinstance(kw.value, ast.Name):
                kwargs[kw.arg] = kw.value.id
            elif isinstance(kw.value, ast.Attribute):
                kwargs[kw.arg] = ast.unparse(kw.value)
        if kwargs:
            found.append(kwargs)
    return found


def test_h15_ui_otf_and_admit_use_session_or_instrument_exchange_tz():
    """Classic Backtest OTF/Admit clocks use session ``exchange_tz`` (H15 UI)."""
    assert 'st.session_state.get("exchange_timezone")' in BACKTEST
    otf = [
        kw
        for kw in _call_kwargs(BACKTEST, "apply_configured_otf_filter")
        if "session_timezone" in kw
    ]
    admit = [kw for kw in _call_kwargs(BACKTEST, "normalize_entry_window") if "exchange_tz" in kw]
    simulate = [
        kw for kw in _call_kwargs(BACKTEST, "simulate_trades") if "entry_window_exchange_tz" in kw
    ]
    assert otf and all(item["session_timezone"] == "exchange_tz" for item in otf)
    assert admit and all(item["exchange_tz"] == "exchange_tz" for item in admit)
    assert simulate and all(item["entry_window_exchange_tz"] == "exchange_tz" for item in simulate)
    assert not any(item.get("session_timezone") == "inst.exchange_tz" for item in otf)


def test_h15_api_otf_and_admit_use_instrument_exchange_tz():
    """``api.run_backtest`` OTF/Admit clocks are ``inst.exchange_tz`` (H15 API)."""
    otf = [
        kw for kw in _call_kwargs(API, "apply_configured_otf_filter") if "session_timezone" in kw
    ]
    simulate = [
        kw for kw in _call_kwargs(API, "simulate_trades") if "entry_window_exchange_tz" in kw
    ]
    assert otf
    assert any(item.get("session_timezone") == "inst.exchange_tz" for item in otf)
    assert simulate
    assert any(item.get("entry_window_exchange_tz") == "inst.exchange_tz" for item in simulate)
    assert not any(item.get("session_timezone") == "exchange_tz" for item in otf)
