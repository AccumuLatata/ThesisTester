"""QI-05-04 / A-3 — H12 Focus ≠ Admit under single_position (copy + fixture)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from thesistester.analytics.entry_window import (
    FOCUS_HONESTY_BANNER,
    filter_trades_by_entry_window,
    normalize_entry_window,
)
from thesistester.engine.backtest import simulate_trades

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES = REPO_ROOT / "pages"
ENTRY_WINDOW_PY = REPO_ROOT / "thesistester" / "analytics" / "entry_window.py"

TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 50.0
H12_CAPTION_NEEDLE = "Focus fills may differ from an Admit re-sim"
H12_N_NEEDLE = "Focus N is not an Admit N"

# QI-5 §3 / findings.csv H12 recipe: 180-bar 1m; signals 09:05/10:05/10:30/10:55;
# single_position max_holding_bars=80; Focus clock 10:00–11:30 America/New_York.
SIGNAL_CLOCKS = ("09:05", "10:05", "10:30", "10:55")


def _h12_bars() -> pd.DataFrame:
    stamps = pd.date_range("2026-06-02 09:00", periods=180, freq="1min", tz=TZ)
    price = 21000.0
    rows = []
    for ts in stamps:
        rows.append(
            {
                "timestamp": ts,
                "open": price,
                "high": price + 2.0,
                "low": price - 2.0,
                "close": price + 0.25,
                "volume": 1000.0,
            }
        )
        price += 0.25
    return pd.DataFrame(rows)


def _h12_signals(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i, clock in enumerate(SIGNAL_CLOCKS, start=1):
        ts = pd.Timestamp(f"2026-06-02 {clock}", tz=TZ)
        bar_index = int(df.index[df["timestamp"] == ts][0])
        rows.append(
            {
                "signal_id": i,
                "timestamp": ts,
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
        )
    return pd.DataFrame(rows)


def _h12_window() -> dict:
    return normalize_entry_window(
        {
            "enabled": True,
            "mode": "clock_range",
            "start_time": "10:00",
            "end_time": "11:30",
            "timezone": TZ,
        },
        exchange_tz=TZ,
    )


def _sim(df: pd.DataFrame, signals: pd.DataFrame, **overrides) -> pd.DataFrame:
    kwargs = {
        "tick_size": TICK,
        "point_value": POINT_VALUE,
        "stop_loss_ticks": 400,
        "take_profit_ticks": 400,
        "max_holding_bars": 80,
        "allow_same_bar_exit": True,
        "commission_per_side": 0.0,
        "slippage_ticks": 0.0,
        "session_timezone": TZ,
        "entry_window_exchange_tz": TZ,
        "cooldown_bars_after_exit": 0,
    }
    kwargs.update(overrides)
    return simulate_trades(df, signals, **kwargs)


def test_h12_single_position_focus_fill_set_differs_from_admit():
    """QI-5 §3: occupancy substitution — Focus {3} vs Admit {2}; all-day {1,3}."""
    df = _h12_bars()
    signals = _h12_signals(df)
    window = _h12_window()
    all_day = _sim(df, signals, exposure_policy="single_position")
    focused = filter_trades_by_entry_window(
        all_day, window, exchange_tz=TZ, timestamp_col="entry_timestamp"
    )
    admit = _sim(df, signals, exposure_policy="single_position", entry_window=window)
    all_ids = set(all_day["signal_id"].astype(int))
    focus_ids = set(focused["signal_id"].astype(int))
    admit_ids = set(admit["signal_id"].astype(int))
    assert all_ids == {1, 3}
    assert focus_ids == {3}
    assert admit_ids == {2}
    assert focus_ids != admit_ids
    assert len(focus_ids) == len(admit_ids)  # N=1=1; substitution, not N inflation


def test_h12_c7_identity_under_allow_all_zero_cooldown():
    """AH §2 item 5 / C7: allow_all + 0 cooldown → Focus ≡ Admit {2,3,4}."""
    df = _h12_bars()
    signals = _h12_signals(df)
    window = _h12_window()
    all_day = _sim(df, signals, exposure_policy="allow_all", cooldown_bars_after_exit=0)
    focused = filter_trades_by_entry_window(
        all_day, window, exchange_tz=TZ, timestamp_col="entry_timestamp"
    )
    admit = _sim(
        df,
        signals,
        exposure_policy="allow_all",
        cooldown_bars_after_exit=0,
        entry_window=window,
    )
    focus_ids = set(focused["signal_id"].astype(int))
    admit_ids = set(admit["signal_id"].astype(int))
    assert focus_ids == admit_ids == {2, 3, 4}


def test_h12_pages_caption_admit_divergence_without_editing_banner_constant():
    """Consumer text only — FOCUS_HONESTY_BANNER and entry_window.py stay put."""
    assert "Admit" not in FOCUS_HONESTY_BANNER
    assert FOCUS_HONESTY_BANNER == (
        "Post-hoc subset — not re-simulated. Exposure/cooldown still reflect the all-day run."
    )
    source = ENTRY_WINDOW_PY.read_text(encoding="utf-8")
    assert H12_CAPTION_NEEDLE not in source
    for name in ("9_Time_Analysis.py", "10_Validation.py"):
        text = (PAGES / name).read_text(encoding="utf-8")
        assert "FOCUS_HONESTY_BANNER" in text
        assert H12_CAPTION_NEEDLE in text
        assert H12_N_NEEDLE in text
