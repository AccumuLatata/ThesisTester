from __future__ import annotations

import pandas as pd

from thesistester.engine.anchor_confluence import detect_anchor_confluence_zones
from thesistester.engine.confluence import detect_confluence_zones
from thesistester.engine.signals import generate_signals


TZ = "America/New_York"
TICK = 0.25


def _levels_df() -> pd.DataFrame:
    ts = pd.date_range("2026-01-02 09:30", periods=4, freq="1min", tz=TZ)
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": [101.0, 100.6, 101.0, 100.9],
            "high": [101.0, 101.3, 101.1, 101.0],
            "low": [100.0, 100.2, 100.5, 100.6],
            "close": [100.5, 101.1, 100.9, 100.8],
            "volume": [100.0] * 4,
            "L1": [100.0] * 4,
            "L2": [100.0] * 4,
        }
    )


def test_3c_global_cluster_mode_sets_level_source_mode():
    df = _levels_df()
    zones = detect_confluence_zones(
        df,
        level_columns=["L1", "L2"],
        tick_size=TICK,
        tolerance_ticks=0,
        min_confluences=2,
        max_confluences=2,
    )
    sigs = generate_signals(
        df,
        zones,
        trigger="3c",
        direction="long",
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3, "_source_mode": "global_cluster"},
    )
    assert not sigs.empty
    assert set(sigs["level_source_mode"]) == {"global_cluster"}


def test_3c_anchor_rules_mode_sets_user_anchor_label():
    df = _levels_df()
    zones = detect_anchor_confluence_zones(
        df,
        anchor_level="L1",
        confluence_rules=[{"level": "L2", "tolerance_ticks": 0.0, "required": True}],
        tick_size=TICK,
        min_valid_confluences=1,
    )
    sigs = generate_signals(
        df,
        zones,
        trigger="3c",
        direction="long",
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3, "_source_mode": "anchor_rules"},
    )
    assert not sigs.empty
    assert set(sigs["level_source_mode"]) == {"user_anchor"}
