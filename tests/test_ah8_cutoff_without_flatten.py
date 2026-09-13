"""B-1 / QI-04-07: lock H7 cutoff-without-flatten (do not invert the fork)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from thesistester.api import run_backtest

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES = REPO_ROOT / "pages"
TZ = "America/New_York"
_UI_FORCE_NONE = "(no_new_entries_after.strip() or None) if flat_by_session_close else None"


def _bar(ts: str, o: float = 21000.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": o,
        "high": o + 2.0,
        "low": o - 2.0,
        "close": o + 0.5,
        "volume": 1000.0,
    }


def _signal(signal_id: int, bar_index: int) -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
        "bar_index": bar_index,
        "trigger": "touch",
        "direction": "long",
        "zone_low": 20990.0,
        "zone_high": 21010.0,
        "zone_mid": 21000.0,
        "level_count": 1,
        "level_names": "A",
        "entry_reference_price": 21000.0,
        "entry_model": "candidate_next_bar_open",
        "status": "candidate",
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }


def _frame() -> pd.DataFrame:
    stamps = pd.date_range("2026-06-02 09:29", periods=30, freq="1min", tz=TZ)
    rows = []
    price = 21000.0
    for ts in stamps:
        rows.append(_bar(str(ts), o=price))
        price += 0.25
    return pd.DataFrame(rows)


def test_h7_ui_and_grid_force_cutoff_none_when_flatten_off():
    """Classic composers gate cutoff on flatten (H7 UI side)."""
    backtest = (PAGES / "7_Backtest.py").read_text(encoding="utf-8")
    grid = (PAGES / "8_Grid_Search.py").read_text(encoding="utf-8")
    assert _UI_FORCE_NONE in backtest
    assert _UI_FORCE_NONE in grid


def test_h7_api_applies_cutoff_when_flatten_is_off():
    """Headless composer applies YAML cutoff with flatten off (H7 API side)."""
    df = _frame()
    late = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:50", tz=TZ)][0])
    signals = pd.DataFrame([_signal(1, late)])
    ui_kwargs = {
        "flat_by_session_close": False,
        "no_new_entries_after": None,
        "stop_loss_ticks": 8,
        "take_profit_ticks": 16,
    }
    api_kwargs = {**ui_kwargs, "no_new_entries_after": "09:50"}
    ui_result = run_backtest(df, signals, instrument="ES", config=ui_kwargs)
    api_result = run_backtest(df, signals, instrument="ES", config=api_kwargs)
    assert len(ui_result["trades"]) >= 1
    skipped = api_result["skipped_signals"]
    assert skipped is not None and not skipped.empty
    assert "after_entry_cutoff" in set(skipped["skip_reason"])
    assert len(api_result["trades"]) == 0
