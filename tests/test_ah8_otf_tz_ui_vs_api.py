"""B-1 / QI-04-07: lock H15 OTF/Admit TZ wiring (do not invert the fork).

QI-4 §3 / Appendix A: UI records session ``exchange_tz``; ``api.run_backtest``
records ``inst.exchange_tz``. Admission may match on a fixture; wiring is the lock.
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


def _function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function {name}")


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


def test_h15_ui_otf_and_admit_use_session_or_instrument_exchange_tz() -> None:
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


def test_h15_api_otf_and_admit_use_instrument_exchange_tz() -> None:
    """``api.run_backtest`` OTF/Admit clocks are ``inst.exchange_tz`` (H15 API)."""
    run_backtest_src = _function_source(API, "run_backtest")
    otf = [
        kw
        for kw in _call_kwargs(run_backtest_src, "apply_configured_otf_filter")
        if "session_timezone" in kw
    ]
    simulate = [
        kw
        for kw in _call_kwargs(run_backtest_src, "simulate_trades")
        if "entry_window_exchange_tz" in kw
    ]
    admit = [
        kw for kw in _call_kwargs(run_backtest_src, "normalize_entry_window") if "exchange_tz" in kw
    ]
    assert otf and all(item.get("session_timezone") == "inst.exchange_tz" for item in otf)
    assert simulate and all(
        item.get("entry_window_exchange_tz") == "inst.exchange_tz" for item in simulate
    )
    assert admit and all(item.get("exchange_tz") == "inst.exchange_tz" for item in admit)
    assert not any(item.get("session_timezone") == "exchange_tz" for item in otf)


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
    """Recorded OTF ``session_timezone`` follows each composer when session ≠ instrument."""
    df, signals = _h15_probe_frame()
    inst = INSTRUMENTS["ES"]
    session_exchange = "UTC"
    ui_tz = session_exchange or inst.exchange_tz
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
            "session_timezone": session_exchange,
            "flat_by_session_close": False,
            "stop_loss_ticks": 40,
            "take_profit_ticks": 40,
        },
    )
    api_tz = api["otf_filter_summary"]["session_timezone"]
    assert ui_otf.session_timezone == ui_tz
    assert api_tz == inst.exchange_tz
    assert ui_otf.session_timezone != api_tz
