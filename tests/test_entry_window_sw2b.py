"""SW2b tests: audit no_new_entries_after as after_entry_cutoff (skip capture on)."""

from __future__ import annotations

import pandas as pd

from thesistester.analytics.entry_window import (
    AFTER_ENTRY_CUTOFF_REASON,
    OUTSIDE_ENTRY_WINDOW_REASON,
    entry_window_from_bucket,
    partition_skip_counts,
)
from thesistester.engine.backtest import simulate_trades

TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 20.0


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
    # Through ~10:20 so joint window+cutoff dual-fail cases have morning bars.
    stamps = pd.date_range("2026-06-02 09:29", periods=52, freq="1min", tz=TZ)
    rows = []
    price = 21000.0
    for ts in stamps:
        rows.append(_bar(str(ts), o=price))
        price += 0.25
    return pd.DataFrame(rows)


def _base_kwargs(**overrides):
    cfg = {
        "tick_size": TICK,
        "point_value": POINT_VALUE,
        "stop_loss_ticks": 8,
        "take_profit_ticks": 16,
        "max_holding_bars": 5,
        "allow_same_bar_exit": True,
        "commission_per_side": 0.0,
        "slippage_ticks": 0.0,
        "session_timezone": TZ,
        "exposure_policy": "allow_all",
        "cooldown_bars_after_exit": 0,
    }
    cfg.update(overrides)
    return cfg


def test_after_entry_cutoff_audited_when_skip_capture_on():
    df = _frame()
    idx_before = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:44", tz=TZ)][0])
    idx_at = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:49", tz=TZ)][0])
    idx_after = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:50", tz=TZ)][0])
    signals = pd.DataFrame([_signal(1, idx_before), _signal(2, idx_at), _signal(3, idx_after)])
    result = simulate_trades(
        df,
        signals,
        **_base_kwargs(no_new_entries_after="09:50", return_result=True),
    )
    assert set(result.trades["signal_id"]) == {1, 2}
    assert list(result.skipped_signals["signal_id"]) == [3]
    assert list(result.skipped_signals["skip_reason"]) == [AFTER_ENTRY_CUTOFF_REASON]
    counts = partition_skip_counts(result.skipped_signals)
    assert counts == {
        "total": 1,
        "outside_entry_window": 0,
        "after_entry_cutoff": 1,
        "other": 0,
    }


def test_cutoff_audit_does_not_change_trades_vs_default_return():
    """Regression: skip capture only grows skipped_signals; trades stay identical."""
    df = _frame()
    idx_before = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:44", tz=TZ)][0])
    idx_after = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:50", tz=TZ)][0])
    signals = pd.DataFrame([_signal(1, idx_before), _signal(3, idx_after)])
    kwargs = _base_kwargs(no_new_entries_after="09:50")
    legacy = simulate_trades(df, signals, **kwargs)
    captured = simulate_trades(df, signals, **kwargs, return_result=True)
    pd.testing.assert_frame_equal(
        legacy.reset_index(drop=True), captured.trades.reset_index(drop=True)
    )
    assert list(captured.skipped_signals["skip_reason"]) == [AFTER_ENTRY_CUTOFF_REASON]


def test_no_cutoff_leaves_skip_frame_empty_under_allow_all():
    df = _frame()
    idx = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:44", tz=TZ)][0])
    result = simulate_trades(
        df,
        pd.DataFrame([_signal(1, idx)]),
        **_base_kwargs(no_new_entries_after=None, return_result=True),
    )
    assert len(result.trades) == 1
    assert result.skipped_signals.empty


def test_partition_skip_counts_splits_cutoff_from_exposure():
    skipped = pd.DataFrame(
        {
            "skip_reason": [
                "after_entry_cutoff",
                "outside_entry_window",
                "overlapping_position",
            ]
        }
    )
    assert partition_skip_counts(skipped) == {
        "total": 3,
        "outside_entry_window": 1,
        "after_entry_cutoff": 1,
        "other": 1,
    }


def test_c9_dual_fail_labels_outside_entry_window_not_cutoff():
    """C9: when both window and cutoff fail, prefer outside_entry_window label."""
    df = _frame()
    # Entry 10:11 is outside rth_open_30m AND after a 10:00 cutoff.
    idx_out = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 10:10", tz=TZ)][0])
    window = entry_window_from_bucket("entry_rth_segment", "rth_open_30m", exchange_tz=TZ)
    result = simulate_trades(
        df,
        pd.DataFrame([_signal(4, idx_out)]),
        **_base_kwargs(
            entry_window=window,
            no_new_entries_after="10:00",
            return_result=True,
        ),
    )
    assert result.trades.empty
    assert list(result.skipped_signals["signal_id"]) == [4]
    assert list(result.skipped_signals["skip_reason"]) == [OUTSIDE_ENTRY_WINDOW_REASON]
    counts = partition_skip_counts(result.skipped_signals)
    assert counts["outside_entry_window"] == 1
    assert counts["after_entry_cutoff"] == 0


def test_cutoff_only_still_audited_when_inside_window():
    """In-window entry past cutoff must still audit as after_entry_cutoff."""
    df = _frame()
    # Entry 09:51 is inside rth_open_30m but after 09:50 cutoff.
    idx_after = int(df.index[df["timestamp"] == pd.Timestamp("2026-06-02 09:50", tz=TZ)][0])
    window = entry_window_from_bucket("entry_rth_segment", "rth_open_30m", exchange_tz=TZ)
    result = simulate_trades(
        df,
        pd.DataFrame([_signal(3, idx_after)]),
        **_base_kwargs(
            entry_window=window,
            no_new_entries_after="09:50",
            return_result=True,
        ),
    )
    assert result.trades.empty
    assert list(result.skipped_signals["skip_reason"]) == [AFTER_ENTRY_CUTOFF_REASON]
