"""SW3 tests: API run_backtest entry_window + skip partition honesty."""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.entry_window import (
    ADMIT_HONESTY_BANNER,
    partition_skip_counts,
)
from thesistester.api import run_backtest, validate_run_spec
from thesistester.entry_window_policy import normalize_entry_window
from thesistester.execution_defaults import (
    collect_backtest_defaults,
    sanitize_backtest_defaults,
)

TZ = "America/New_York"


def _bar(
    ts: str,
    o: float = 21000.0,
    h: float | None = None,
    l: float | None = None,
    c: float | None = None,
) -> dict:
    open_ = o
    high = h if h is not None else open_ + 2.0
    low = l if l is not None else open_ - 2.0
    close = c if c is not None else open_ + 0.5
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000.0,
    }


def _signal(signal_id: int, bar_index: int, direction: str = "long") -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
        "bar_index": bar_index,
        "trigger": "touch",
        "direction": direction,
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


def _rth_morning_frame() -> pd.DataFrame:
    stamps = pd.date_range("2026-06-02 09:29", periods=52, freq="1min", tz=TZ)
    rows = []
    price = 21000.0
    for ts in stamps:
        rows.append(_bar(str(ts), o=price))
        price += 0.25
    return pd.DataFrame(rows)


def _open_and_morning_signals(df: pd.DataFrame) -> pd.DataFrame:
    idx_open = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:45", tz=TZ)][0])
    idx_morn = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 10:10", tz=TZ)][0])
    return pd.DataFrame([_signal(1, idx_open), _signal(2, idx_morn)])


def _minimal_spec(*, entry_window: dict | None = None) -> dict:
    backtest = {
        "stop_loss_ticks": 8.0,
        "take_profit_ticks": 16.0,
        "exposure_policy": "allow_all",
    }
    if entry_window is not None:
        backtest["entry_window"] = entry_window
    return {
        "name": "sw3_entry_window",
        "dataset": {
            "path": "unused.csv",
            "instrument": "ES",
            "source_timezone": "America/New_York",
            "format_profile": "canonical",
        },
        "levels": {
            "sma_lengths": [2],
            "ema_lengths": [2],
            "sma_timeframes": ["1min"],
            "ema_timeframes": ["1min"],
            "vwap_windows": [],
            "poc_windows": [],
        },
        "setup": {
            "name": "sw3",
            "description": "SW3 validate_run_spec fixture",
            "instrument": "ES",
            "selected_levels": ["dOpen", "RTH_Open"],
            "tolerance_ticks": 0,
            "min_confluences": 2,
            "max_confluences": 2,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger": "touch",
            "trigger_timeframe": "base",
            "direction": "both",
            "confluence_mode": "global_cluster",
            "anchor_level": None,
            "confluence_rules": [],
            "min_valid_confluences": 1,
            "trigger_params": {},
            "otf_filter": None,
        },
        "backtest": backtest,
        "grid": {"enabled": False},
        "validation": {"enabled": False},
    }


def test_partition_skip_counts_splits_window_vs_other():
    skipped = pd.DataFrame(
        {
            "skip_reason": [
                "outside_entry_window",
                "outside_entry_window",
                "single_position",
            ]
        }
    )
    counts = partition_skip_counts(skipped)
    assert counts == {"total": 3, "outside_entry_window": 2, "other": 1}
    assert partition_skip_counts(None)["total"] == 0
    assert "Constrained re-simulation" in ADMIT_HONESTY_BANNER


def test_run_backtest_default_entry_window_disabled_matches_omit():
    df = _rth_morning_frame()
    signals = _open_and_morning_signals(df)
    config_base = {
        "stop_loss_ticks": 8,
        "take_profit_ticks": 16,
        "max_holding_bars": 5,
        "exposure_policy": "allow_all",
        "cooldown_bars_after_exit": 0,
    }
    baseline = run_backtest(df, signals, instrument="ES", config=config_base)
    explicit = run_backtest(
        df,
        signals,
        instrument="ES",
        config={**config_base, "entry_window": {"enabled": False}},
    )
    pd.testing.assert_frame_equal(baseline["trades"], explicit["trades"])
    assert baseline["entry_window"]["enabled"] is False
    assert explicit["entry_window"]["enabled"] is False
    assert len(baseline["trades"]) == 2


def test_run_backtest_enabled_entry_window_admits_and_skips():
    df = _rth_morning_frame()
    signals = _open_and_morning_signals(df)
    window = normalize_entry_window(
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
            "timezone": TZ,
        },
        exchange_tz=TZ,
    )
    result = run_backtest(
        df,
        signals,
        instrument="ES",
        config={
            "stop_loss_ticks": 8,
            "take_profit_ticks": 16,
            "max_holding_bars": 5,
            "exposure_policy": "allow_all",
            "cooldown_bars_after_exit": 0,
            "entry_window": window,
        },
    )
    assert result["entry_window"]["enabled"] is True
    assert list(result["trades"]["signal_id"]) == [1]
    skipped = result["skipped_signals"]
    assert not skipped.empty
    assert set(skipped["skip_reason"]) == {"outside_entry_window"}
    counts = partition_skip_counts(skipped)
    assert counts["outside_entry_window"] >= 1
    assert counts["other"] == 0


def test_validate_run_spec_accepts_entry_window():
    validate_run_spec(
        _minimal_spec(
            entry_window={
                "enabled": True,
                "mode": "rth_segments",
                "rth_segments": ["rth_open_30m"],
            }
        )
    )


def test_validate_run_spec_rejects_invalid_entry_window():
    with pytest.raises(ValueError, match="Invalid backtest.entry_window"):
        validate_run_spec(
            _minimal_spec(
                entry_window={
                    "enabled": True,
                    "mode": "rth_segments",
                    "rth_segments": [],
                }
            )
        )


def test_sanitize_collect_entry_window_defaults():
    raw = {
        "entry_window_enabled": True,
        "entry_window_mode": "rth_segments",
        "entry_window_rth_segments": ["rth_open_30m", "bogus"],
        "defaults_schema_version": 1,
    }
    sanitized = sanitize_backtest_defaults(raw)
    assert sanitized["backtest_entry_window_enabled"] is True
    assert sanitized["backtest_entry_window_mode"] == "rth_segments"
    assert "backtest_entry_window_rth_segments" not in sanitized

    raw_ok = {
        "entry_window_enabled": True,
        "entry_window_mode": "clock_range",
        "entry_window_start_time": "09:30",
        "entry_window_end_time": "24:00",
        "entry_window_timezone": "America/New_York",
        "entry_window_rth_segments": ["rth_open_30m"],
    }
    sanitized_ok = sanitize_backtest_defaults(raw_ok)
    assert sanitized_ok["backtest_entry_window_end_time"] == "24:00"
    assert sanitized_ok["backtest_entry_window_rth_segments"] == ["rth_open_30m"]

    session = {
        "backtest_entry_window_enabled": True,
        "backtest_entry_window_mode": "rth_segments",
        "backtest_entry_window_rth_segments": ["rth_open_30m"],
    }
    collected = collect_backtest_defaults(session)
    assert collected["entry_window_enabled"] is True
    assert collected["entry_window_rth_segments"] == ["rth_open_30m"]
