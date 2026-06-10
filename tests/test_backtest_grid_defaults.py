"""Tests for Backtest and Grid Search execution-settings defaults.

Covers:
- Backtest defaults roundtrip (save / load / schema version)
- Grid defaults roundtrip (save / load / schema version)
- Namespace isolation (Backtest ↔ Grid)
- Existing UI state preservation
- Schema drift (wrong defaults_schema_version returns None)
- Clear / reset behaviour
- Validation / sanitisation of invalid values
- Engine isolation (simulate_trades / run_sl_tp_grid remain unaffected)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import thesistester.persistence.local_store as local_store
from thesistester.execution_defaults import (
    EXPOSURE_POLICY_OPTIONS,
    RANKING_METRIC_OPTIONS,
    DIRECTIONAL_METRIC_OPTIONS,
    sanitize_backtest_defaults,
    sanitize_grid_defaults,
    apply_backtest_defaults,
    apply_grid_defaults,
    collect_backtest_defaults,
    collect_grid_defaults,
    reset_backtest_session_keys,
    reset_grid_session_keys,
    _BACKTEST_FIELD_SPECS,
    _GRID_FIELD_SPECS,
)
from thesistester.persistence.local_store import (
    BACKTEST_DEFAULTS_SCHEMA_VERSION,
    GRID_DEFAULTS_SCHEMA_VERSION,
    get_backtest_defaults,
    save_backtest_defaults,
    clear_backtest_defaults,
    get_grid_defaults,
    save_grid_defaults,
    clear_grid_defaults,
    get_active_dataset_id,
    set_active_dataset_id,
    _load_ui_state,
    _write_ui_state,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Redirect the persistence store to a fresh temp directory for each test."""
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    yield


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sample_backtest_defaults() -> dict:
    return {
        "sl_ticks": 12.0,
        "tp_ticks": 24.0,
        "commission_per_side": 2.5,
        "slippage_ticks": 0.5,
        "use_max_bars": True,
        "max_bars": 30,
        "allow_same_bar": False,
        "flat_by_session_close": True,
        "session_close_time": "16:00",
        "session_timezone": "America/New_York",
        "no_new_entries_after": "15:30",
        "exposure_policy": "single_direction",
        "cooldown_bars_after_exit": 2,
    }


def _sample_grid_defaults() -> dict:
    return {
        "sl_start": 4.0,
        "sl_stop": 20.0,
        "sl_step": 4.0,
        "tp_start": 8.0,
        "tp_stop": 40.0,
        "tp_step": 8.0,
        "commission_per_side": 1.5,
        "slippage_ticks": 0.25,
        "use_max_bars": False,
        "max_bars": 20,
        "allow_same_bar": True,
        "flat_by_session_close": False,
        "session_close_time": "16:00",
        "session_timezone": "UTC",
        "no_new_entries_after": "",
        "exposure_policy": "allow_all",
        "cooldown_bars_after_exit": 0,
        "ranking_metric": "expectancy_r",
        "min_trades": 5,
        "enable_directional": False,
        "directional_metric": "min_direction_expectancy_r",
        "min_long_trades": 3,
        "min_short_trades": 3,
    }


# ── 1. Backtest defaults roundtrip ────────────────────────────────────────────

def test_backtest_defaults_roundtrip():
    """Save, load, and verify schema version is present."""
    data = _sample_backtest_defaults()
    save_backtest_defaults(data)
    loaded = get_backtest_defaults()

    assert loaded is not None
    assert loaded["defaults_schema_version"] == BACKTEST_DEFAULTS_SCHEMA_VERSION
    assert loaded["sl_ticks"] == 12.0
    assert loaded["tp_ticks"] == 24.0
    assert loaded["commission_per_side"] == 2.5
    assert loaded["exposure_policy"] == "single_direction"
    assert loaded["cooldown_bars_after_exit"] == 2


def test_backtest_defaults_absent_returns_none():
    assert get_backtest_defaults() is None


# ── 2. Grid defaults roundtrip ────────────────────────────────────────────────

def test_grid_defaults_roundtrip():
    """Save, load, and verify schema version is present."""
    data = _sample_grid_defaults()
    save_grid_defaults(data)
    loaded = get_grid_defaults()

    assert loaded is not None
    assert loaded["defaults_schema_version"] == GRID_DEFAULTS_SCHEMA_VERSION
    assert loaded["sl_start"] == 4.0
    assert loaded["tp_stop"] == 40.0
    assert loaded["ranking_metric"] == "expectancy_r"
    assert loaded["enable_directional"] is False


def test_grid_defaults_absent_returns_none():
    assert get_grid_defaults() is None


# ── 3. Namespace isolation ────────────────────────────────────────────────────

def test_saving_backtest_does_not_affect_grid():
    """Saving Backtest defaults must not create or overwrite Grid defaults."""
    save_backtest_defaults(_sample_backtest_defaults())
    assert get_grid_defaults() is None


def test_saving_grid_does_not_affect_backtest():
    """Saving Grid defaults must not create or overwrite Backtest defaults."""
    save_grid_defaults(_sample_grid_defaults())
    assert get_backtest_defaults() is None


def test_namespaces_coexist_independently():
    """Both namespaces can be saved and remain independent."""
    bt = _sample_backtest_defaults()
    gr = _sample_grid_defaults()

    save_backtest_defaults(bt)
    save_grid_defaults(gr)

    loaded_bt = get_backtest_defaults()
    loaded_gr = get_grid_defaults()

    assert loaded_bt is not None
    assert loaded_gr is not None
    assert loaded_bt["sl_ticks"] == bt["sl_ticks"]
    assert loaded_gr["sl_start"] == gr["sl_start"]

    # Mutate backtest defaults; grid must be unchanged
    bt2 = dict(bt)
    bt2["sl_ticks"] = 99.0
    save_backtest_defaults(bt2)

    assert get_backtest_defaults()["sl_ticks"] == 99.0
    assert get_grid_defaults()["sl_start"] == gr["sl_start"]


# ── 4. Existing UI state preservation ────────────────────────────────────────

def test_writing_backtest_defaults_preserves_other_ui_keys():
    """Writing Backtest defaults must not remove existing keys like active_dataset_id."""
    set_active_dataset_id("abc123")
    assert get_active_dataset_id() == "abc123"

    save_backtest_defaults(_sample_backtest_defaults())
    assert get_active_dataset_id() == "abc123"


def test_writing_grid_defaults_preserves_other_ui_keys():
    """Writing Grid defaults must not remove existing keys."""
    set_active_dataset_id("xyz789")
    save_grid_defaults(_sample_grid_defaults())
    assert get_active_dataset_id() == "xyz789"


def test_both_defaults_and_active_dataset_coexist():
    set_active_dataset_id("dataset1")
    save_backtest_defaults(_sample_backtest_defaults())
    save_grid_defaults(_sample_grid_defaults())

    assert get_active_dataset_id() == "dataset1"
    assert get_backtest_defaults() is not None
    assert get_grid_defaults() is not None


# ── 5. Schema drift ───────────────────────────────────────────────────────────

def test_backtest_wrong_schema_version_returns_none():
    """A future/different schema version must cause defaults to be ignored."""
    payload = _load_ui_state()
    payload["backtest_defaults"] = {
        "defaults_schema_version": 99,  # wrong version
        "sl_ticks": 10.0,
    }
    _write_ui_state(payload)
    assert get_backtest_defaults() is None


def test_grid_wrong_schema_version_returns_none():
    payload = _load_ui_state()
    payload["grid_defaults"] = {
        "defaults_schema_version": 0,  # wrong version
        "sl_start": 2.0,
    }
    _write_ui_state(payload)
    assert get_grid_defaults() is None


def test_backtest_missing_schema_version_returns_none():
    """Namespace without defaults_schema_version is treated as invalid."""
    payload = _load_ui_state()
    payload["backtest_defaults"] = {"sl_ticks": 8.0}  # no schema version
    _write_ui_state(payload)
    assert get_backtest_defaults() is None


# ── 6. Clear / reset ─────────────────────────────────────────────────────────

def test_clear_backtest_removes_only_backtest():
    """clear_backtest_defaults must not remove Grid defaults or other keys."""
    set_active_dataset_id("ds1")
    save_backtest_defaults(_sample_backtest_defaults())
    save_grid_defaults(_sample_grid_defaults())

    clear_backtest_defaults()

    assert get_backtest_defaults() is None
    assert get_grid_defaults() is not None
    assert get_active_dataset_id() == "ds1"


def test_clear_grid_removes_only_grid():
    """clear_grid_defaults must not remove Backtest defaults or other keys."""
    set_active_dataset_id("ds2")
    save_backtest_defaults(_sample_backtest_defaults())
    save_grid_defaults(_sample_grid_defaults())

    clear_grid_defaults()

    assert get_grid_defaults() is None
    assert get_backtest_defaults() is not None
    assert get_active_dataset_id() == "ds2"


def test_clear_backtest_when_absent_is_safe():
    """Clearing non-existent defaults must not crash."""
    clear_backtest_defaults()  # no error


def test_clear_grid_when_absent_is_safe():
    clear_grid_defaults()  # no error


# ── 7. Validation / sanitisation ─────────────────────────────────────────────

def test_sanitize_backtest_invalid_exposure_policy_dropped():
    raw = {"sl_ticks": 8.0, "exposure_policy": "invalid_policy", "defaults_schema_version": 1}
    sanitized = sanitize_backtest_defaults(raw)
    assert "backtest_exposure_policy" not in sanitized
    assert sanitized.get("backtest_sl_ticks") == 8.0


def test_sanitize_backtest_invalid_timezone_dropped():
    raw = {"session_timezone": "Mars/Olympus", "defaults_schema_version": 1}
    sanitized = sanitize_backtest_defaults(raw)
    assert "backtest_session_timezone" not in sanitized


def test_sanitize_backtest_invalid_time_string_dropped():
    raw = {"session_close_time": "not-a-time", "defaults_schema_version": 1}
    sanitized = sanitize_backtest_defaults(raw)
    assert "backtest_session_close_time" not in sanitized


def test_sanitize_backtest_valid_time_string_accepted():
    for t in ["16:00", "09:30", "16:00:00"]:
        raw = {"session_close_time": t}
        sanitized = sanitize_backtest_defaults(raw)
        assert sanitized.get("backtest_session_close_time") == t


def test_sanitize_backtest_optional_time_empty_accepted():
    raw = {"no_new_entries_after": ""}
    sanitized = sanitize_backtest_defaults(raw)
    assert sanitized.get("backtest_no_new_entries_after") == ""


def test_sanitize_backtest_optional_time_invalid_dropped():
    raw = {"no_new_entries_after": "nope"}
    sanitized = sanitize_backtest_defaults(raw)
    assert "backtest_no_new_entries_after" not in sanitized


def test_sanitize_backtest_numeric_out_of_bounds_dropped():
    raw = {"sl_ticks": 600.0, "tp_ticks": -1.0}  # sl > 500, tp < 1
    sanitized = sanitize_backtest_defaults(raw)
    assert "backtest_sl_ticks" not in sanitized
    assert "backtest_tp_ticks" not in sanitized


def test_sanitize_backtest_numeric_in_bounds_accepted():
    raw = {"sl_ticks": 8.0, "tp_ticks": 16.0, "commission_per_side": 2.5, "slippage_ticks": 1.0}
    sanitized = sanitize_backtest_defaults(raw)
    assert sanitized["backtest_sl_ticks"] == 8.0
    assert sanitized["backtest_tp_ticks"] == 16.0
    assert sanitized["backtest_commission_per_side"] == 2.5
    assert sanitized["backtest_slippage_ticks"] == 1.0


def test_sanitize_backtest_non_bool_dropped():
    raw = {"use_max_bars": 1, "allow_same_bar": "yes"}  # not real bools
    sanitized = sanitize_backtest_defaults(raw)
    assert "backtest_use_max_bars" not in sanitized
    assert "backtest_allow_same_bar" not in sanitized


def test_sanitize_backtest_real_bool_accepted():
    raw = {"use_max_bars": True, "allow_same_bar": False}
    sanitized = sanitize_backtest_defaults(raw)
    assert sanitized["backtest_use_max_bars"] is True
    assert sanitized["backtest_allow_same_bar"] is False


def test_sanitize_grid_invalid_ranking_metric_dropped():
    raw = {"ranking_metric": "nonexistent_metric"}
    sanitized = sanitize_grid_defaults(raw)
    assert "grid_ranking_metric_widget" not in sanitized


def test_sanitize_grid_invalid_directional_metric_dropped():
    raw = {"directional_metric": "not_a_metric"}
    sanitized = sanitize_grid_defaults(raw)
    assert "grid_directional_metric" not in sanitized


def test_sanitize_grid_valid_metrics_accepted():
    for metric in RANKING_METRIC_OPTIONS:
        raw = {"ranking_metric": metric}
        sanitized = sanitize_grid_defaults(raw)
        assert sanitized.get("grid_ranking_metric_widget") == metric

    for metric in DIRECTIONAL_METRIC_OPTIONS:
        raw = {"directional_metric": metric}
        sanitized = sanitize_grid_defaults(raw)
        assert sanitized.get("grid_directional_metric") == metric


def test_sanitize_grid_numeric_bounds():
    # Out-of-bounds values dropped
    raw = {"sl_start": 0.5, "sl_stop": 600.0, "sl_step": 0.0, "tp_step": 300.0}
    sanitized = sanitize_grid_defaults(raw)
    assert "grid_sl_start" not in sanitized
    assert "grid_sl_stop" not in sanitized
    assert "grid_sl_step" not in sanitized
    assert "grid_tp_step" not in sanitized

    # Valid values accepted
    raw2 = {"sl_start": 4.0, "sl_stop": 20.0, "sl_step": 4.0}
    sanitized2 = sanitize_grid_defaults(raw2)
    assert sanitized2["grid_sl_start"] == 4.0
    assert sanitized2["grid_sl_stop"] == 20.0
    assert sanitized2["grid_sl_step"] == 4.0


def test_sanitize_all_exposure_policies_accepted():
    for policy in EXPOSURE_POLICY_OPTIONS:
        raw = {"exposure_policy": policy}
        bt = sanitize_backtest_defaults(raw)
        gr = sanitize_grid_defaults(raw)
        assert bt.get("backtest_exposure_policy") == policy
        assert gr.get("grid_exposure_policy_widget") == policy


# ── 8. apply_backtest_defaults / apply_grid_defaults ─────────────────────────

def test_apply_backtest_does_not_overwrite_existing_keys():
    """apply_backtest_defaults must not overwrite keys already in session_state."""
    session = {"backtest_sl_ticks": 5.0}  # user has already set this
    raw = {"sl_ticks": 12.0, "tp_ticks": 24.0, "defaults_schema_version": 1}
    apply_backtest_defaults(session, raw)
    # sl_ticks was already present → must not change
    assert session["backtest_sl_ticks"] == 5.0
    # tp_ticks was absent → injected
    assert session["backtest_tp_ticks"] == 24.0


def test_apply_grid_does_not_overwrite_existing_keys():
    session = {"grid_sl_start": 2.0}
    raw = {"sl_start": 8.0, "tp_start": 12.0, "defaults_schema_version": 1}
    apply_grid_defaults(session, raw)
    assert session["grid_sl_start"] == 2.0   # unchanged
    assert session["grid_tp_start"] == 12.0   # injected


def test_apply_backtest_invalid_values_not_injected():
    """Invalid saved values must not reach session_state."""
    session: dict = {}
    raw = {
        "exposure_policy": "TOTALLY_INVALID",
        "session_timezone": "Mordor/Shire",
        "sl_ticks": 8.0,
        "defaults_schema_version": 1,
    }
    apply_backtest_defaults(session, raw)
    assert "backtest_exposure_policy" not in session
    assert "backtest_session_timezone" not in session
    assert session["backtest_sl_ticks"] == 8.0


# ── 9. collect_backtest_defaults / collect_grid_defaults ─────────────────────

def test_collect_backtest_defaults_extracts_known_keys():
    session = {
        "backtest_sl_ticks": 10.0,
        "backtest_tp_ticks": 20.0,
        "backtest_exposure_policy": "allow_all",
        "backtest_cooldown_bars": 3,
        "some_unrelated_key": "ignored",
    }
    collected = collect_backtest_defaults(session)
    assert collected["sl_ticks"] == 10.0
    assert collected["tp_ticks"] == 20.0
    assert collected["exposure_policy"] == "allow_all"
    assert collected["cooldown_bars_after_exit"] == 3
    assert "some_unrelated_key" not in collected


def test_collect_grid_defaults_extracts_known_keys():
    session = {
        "grid_sl_start": 4.0,
        "grid_ranking_metric_widget": "profit_factor",
        "grid_enable_directional": True,
        "unrelated": "skip",
    }
    collected = collect_grid_defaults(session)
    assert collected["sl_start"] == 4.0
    assert collected["ranking_metric"] == "profit_factor"
    assert collected["enable_directional"] is True
    assert "unrelated" not in collected


# ── 10. reset_backtest_session_keys / reset_grid_session_keys ─────────────────

def test_reset_backtest_removes_widget_keys_not_result_keys():
    session = {
        "backtest_sl_ticks": 10.0,
        "backtest_execution_costs": {"commission_per_side": 1.0},
        "backtest_session_exit_policy": {"flat_by_session_close": False},
        "_backtest_defaults_applied": True,
    }
    reset_backtest_session_keys(session)

    # Widget keys removed
    assert "backtest_sl_ticks" not in session
    assert "_backtest_defaults_applied" not in session
    # Result keys preserved
    assert "backtest_execution_costs" in session
    assert "backtest_session_exit_policy" in session


def test_reset_grid_removes_widget_keys_not_result_keys():
    session = {
        "grid_sl_start": 4.0,
        "grid_results": object(),  # result
        "grid_execution_costs": {"commission_per_side": 0.0},
        "_grid_defaults_applied": True,
    }
    reset_grid_session_keys(session)

    assert "grid_sl_start" not in session
    assert "_grid_defaults_applied" not in session
    assert "grid_results" in session
    assert "grid_execution_costs" in session


def test_reset_grid_preserves_exposure_policy_result_dict():
    """reset_grid_session_keys must not delete the post-run grid_exposure_policy dict."""
    session = {
        "grid_exposure_policy_widget": "allow_all",
        "grid_exposure_policy": {
            "exposure_policy": "single_position",
            "cooldown_bars_after_exit": 2,
        },
    }
    reset_grid_session_keys(session)

    assert "grid_exposure_policy_widget" not in session
    assert "grid_exposure_policy" in session
    assert isinstance(session["grid_exposure_policy"], dict)
    assert session["grid_exposure_policy"]["exposure_policy"] == "single_position"


def test_reset_grid_preserves_ranking_and_trade_count_result_keys():
    """reset_grid_session_keys must not delete post-run result keys for ranking/trades."""
    session = {
        "grid_ranking_metric_widget": "profit_factor",
        "grid_ranking_metric": "profit_factor",  # post-run result
        "grid_min_trades_widget": 5,
        "grid_min_trades": 5,                    # post-run result
        "grid_min_long_trades_widget": 3,
        "grid_min_long_trades": 3,               # post-run result
        "grid_min_short_trades_widget": 3,
        "grid_min_short_trades": 3,              # post-run result
    }
    reset_grid_session_keys(session)

    # Widget keys removed
    assert "grid_ranking_metric_widget" not in session
    assert "grid_min_trades_widget" not in session
    assert "grid_min_long_trades_widget" not in session
    assert "grid_min_short_trades_widget" not in session
    # Post-run result keys preserved
    assert "grid_ranking_metric" in session
    assert "grid_min_trades" in session
    assert "grid_min_long_trades" in session
    assert "grid_min_short_trades" in session


# ── 11. Missing / corrupt ui_state.json is handled gracefully ─────────────────

def test_corrupt_ui_state_does_not_crash(tmp_path, monkeypatch):
    store = tmp_path / "corrupt_store"
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(store))
    store.mkdir()
    (store / "ui_state.json").write_text("NOT VALID JSON", encoding="utf-8")

    assert get_backtest_defaults() is None
    assert get_grid_defaults() is None

    # Writing should recover gracefully by overwriting
    save_backtest_defaults({"sl_ticks": 8.0})
    assert get_backtest_defaults() is not None


def test_missing_ui_state_does_not_crash():
    # Store dir doesn't exist yet → reading returns None, writing creates it
    assert get_backtest_defaults() is None
    save_backtest_defaults({"sl_ticks": 8.0})
    assert get_backtest_defaults()["sl_ticks"] == 8.0


# ── 12. Engine isolation ─────────────────────────────────────────────────────

def _make_df():
    import pandas as pd
    timestamps = pd.date_range("2026-01-02 09:30", periods=20, freq="1min",
                               tz="America/New_York")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open":   [100.0] * 20,
        "high":   [101.0] * 20,
        "low":    [99.5]  * 20,
        "close":  [100.5] * 20,
        "volume": [100.0] * 20,
    })


def _make_signals():
    import pandas as pd
    return pd.DataFrame([{
        "signal_id": 1,
        "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz="America/New_York"),
        "bar_index": 2,
        "trigger": "touch",
        "direction": "long",
        "zone_low": 99.5,
        "zone_high": 100.5,
        "zone_mid": 100.0,
        "level_count": 1,
        "level_names": "A",
        "entry_reference_price": 100.0,
        "entry_model": "candidate_next_bar_open",
        "status": "candidate",
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }])


def test_simulate_trades_not_affected_by_saved_backtest_defaults():
    """simulate_trades must behave identically regardless of saved defaults."""
    from thesistester.engine.backtest import simulate_trades

    # Save some defaults that differ from the explicit call args below
    save_backtest_defaults({"sl_ticks": 100.0, "tp_ticks": 200.0, "exposure_policy": "single_position"})

    trades, _ = simulate_trades(
        df=_make_df(),
        signals=_make_signals(),
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks=8.0,
        take_profit_ticks=16.0,
        return_skipped_signals=True,
    )
    import pandas as pd
    assert isinstance(trades, pd.DataFrame)


def test_run_sl_tp_grid_not_affected_by_saved_grid_defaults():
    """run_sl_tp_grid must behave identically regardless of saved defaults."""
    from thesistester.analytics.grid import run_sl_tp_grid
    import pandas as pd

    save_grid_defaults({"sl_start": 99.0, "tp_start": 199.0})

    grid = run_sl_tp_grid(
        df=_make_df(),
        signals=_make_signals(),
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks_values=[4.0, 8.0],
        take_profit_ticks_values=[8.0, 16.0],
    )
    assert isinstance(grid, pd.DataFrame)
    assert len(grid) == 4


# ── 13. Strict time validation ────────────────────────────────────────────────

def test_strict_time_validation_accepts_zero_padded():
    """Zero-padded HH:MM and HH:MM:SS must be accepted."""
    from thesistester.execution_defaults import _valid_time_str, _valid_optional_time_str
    for t in ["09:30", "16:00", "16:00:00"]:
        assert _valid_time_str(t) == t
        assert _valid_optional_time_str(t) == t


def test_strict_time_validation_rejects_single_digit_hour():
    """Non-zero-padded single-digit hour must be rejected."""
    from thesistester.execution_defaults import _valid_time_str, _valid_optional_time_str
    assert _valid_time_str("9:30") is None
    assert _valid_optional_time_str("9:30") is None


def test_strict_time_validation_rejects_out_of_range():
    """Times with out-of-range hour, minute, or second must be rejected."""
    from thesistester.execution_defaults import _valid_time_str, _valid_optional_time_str
    for t in ["99:99", "24:00", "12:99", "16:00:99"]:
        assert _valid_time_str(t) is None, f"Expected None for {t!r}"
        assert _valid_optional_time_str(t) is None, f"Expected None for {t!r}"


def test_strict_time_validation_rejects_arbitrary_text():
    from thesistester.execution_defaults import _valid_time_str, _valid_optional_time_str
    assert _valid_time_str("not-a-time") is None
    assert _valid_optional_time_str("not-a-time") is None


def test_strict_time_validation_rejects_non_string():
    from thesistester.execution_defaults import _valid_time_str, _valid_optional_time_str
    assert _valid_time_str(1600) is None
    assert _valid_optional_time_str(None) == ""  # None → empty string (no-time)
    assert _valid_optional_time_str(1600) is None


def test_sanitize_backtest_strict_time_rejects_invalid():
    """Stricter time validation must reject single-digit and out-of-range values."""
    for bad_time in ["9:30", "99:99", "24:00", "12:99", "16:00:99"]:
        raw = {"session_close_time": bad_time}
        sanitized = sanitize_backtest_defaults(raw)
        assert "backtest_session_close_time" not in sanitized, f"Should reject {bad_time!r}"


def test_sanitize_grid_strict_time_rejects_invalid():
    for bad_time in ["9:30", "99:99", "24:00", "12:99", "16:00:99"]:
        raw = {"session_close_time": bad_time}
        sanitized = sanitize_grid_defaults(raw)
        assert "grid_session_close_time" not in sanitized, f"Should reject {bad_time!r}"


# ── 14. Numeric validators reject bools ──────────────────────────────────────

def test_numeric_validators_reject_bools():
    """_valid_float and _valid_int must reject bool values explicitly."""
    from thesistester.execution_defaults import _valid_float, _valid_int
    assert _valid_float(True, lo=0.0, hi=10.0) is None
    assert _valid_float(False, lo=0.0, hi=10.0) is None
    assert _valid_int(True, lo=0, hi=10) is None
    assert _valid_int(False, lo=0, hi=10) is None


def test_sanitize_backtest_rejects_bool_for_sl_ticks():
    """sl_ticks=True must be dropped (bool is not a valid float)."""
    raw = {"sl_ticks": True}
    sanitized = sanitize_backtest_defaults(raw)
    assert "backtest_sl_ticks" not in sanitized


def test_sanitize_backtest_rejects_bool_for_cooldown():
    """cooldown_bars_after_exit=False must be dropped."""
    raw = {"cooldown_bars_after_exit": False}
    sanitized = sanitize_backtest_defaults(raw)
    assert "backtest_cooldown_bars" not in sanitized


def test_sanitize_grid_rejects_bool_for_numerics():
    """Grid numeric fields must also reject bools."""
    raw = {"sl_start": True, "max_bars": False, "min_trades": True, "cooldown_bars_after_exit": False}
    sanitized = sanitize_grid_defaults(raw)
    assert "grid_sl_start" not in sanitized
    assert "grid_max_bars" not in sanitized
    assert "grid_min_trades_widget" not in sanitized
    assert "grid_cooldown_bars" not in sanitized
