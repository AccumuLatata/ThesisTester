"""B-1 / QI-04-07: lock H7 cutoff-without-flatten (do not invert the fork).

QI-4 §3 / Appendix A: UI helper flatten-off + cutoff ``None`` fills; headless
``api.run_backtest`` flatten-off + YAML cutoff skips ``after_entry_cutoff``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from thesistester.api import run_backtest
from thesistester.engine.backtest import simulate_trades

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES = REPO_ROOT / "pages"
CLASSIC_EXPORT = REPO_ROOT / "thesistester" / "classic_export.py"
_UI_FORCE_NONE = "(no_new_entries_after.strip() or None) if flat_by_session_close else None"
_WIDGET_DISABLE = "disabled=not flat_by_session_close"


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


def test_h7_ui_and_grid_force_cutoff_none_when_flatten_off() -> None:
    """Classic composers gate cutoff on flatten (H7 UI side)."""
    backtest = (PAGES / "7_Backtest.py").read_text(encoding="utf-8")
    grid = (PAGES / "8_Grid_Search.py").read_text(encoding="utf-8")
    assert _UI_FORCE_NONE in backtest
    assert _UI_FORCE_NONE in grid
    assert _WIDGET_DISABLE in backtest
    assert _WIDGET_DISABLE in grid
    classic = CLASSIC_EXPORT.read_text(encoding="utf-8")
    assert 'backtest["no_new_entries_after"] = None' in classic


def test_h7_ui_style_none_cutoff_fills_when_flatten_off() -> None:
    """UI helper: flatten off forces cutoff None → fill (Appendix A)."""
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
    assert len(ui.trades) >= 1
    skipped = ui.skipped_signals
    if skipped is not None and not skipped.empty:
        assert "after_entry_cutoff" not in set(skipped["skip_reason"])


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
    skipped = api["skipped_signals"]
    assert skipped is not None and not skipped.empty
    assert "after_entry_cutoff" in set(skipped["skip_reason"])
