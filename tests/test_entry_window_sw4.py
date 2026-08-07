"""SW4 tests: Promote Focus→Admit handoff (no auto-run / no engine)."""

from __future__ import annotations

import pytest

from thesistester.analytics.entry_window import (
    ADMIT_APPLIED_STATUS_BADGE,
    ADMIT_ARMED_STATUS_BADGE,
    FOCUS_STATUS_BADGE,
    PROMOTE_ARMED_BANNER,
    apply_promote_to_session_state,
    backtest_widget_state_from_entry_window,
    clear_armed_entry_window,
    entry_window_from_bucket,
    promote_entry_window,
)

TZ = "America/New_York"


def test_status_badges_are_distinct():
    assert "Focus" in FOCUS_STATUS_BADGE
    assert "post-hoc" in FOCUS_STATUS_BADGE
    assert "Admit" in ADMIT_ARMED_STATUS_BADGE
    assert "pending" in ADMIT_ARMED_STATUS_BADGE
    assert "Admit" in ADMIT_APPLIED_STATUS_BADGE
    assert ADMIT_ARMED_STATUS_BADGE != ADMIT_APPLIED_STATUS_BADGE
    assert "armed" in PROMOTE_ARMED_BANNER.lower()
    assert "re-simulate" in PROMOTE_ARMED_BANNER.lower()


def test_promote_writes_explicit_timezone_c5():
    window = entry_window_from_bucket(
        "entry_rth_segment", "rth_open_30m", exchange_tz=TZ
    )
    payload = promote_entry_window(
        window,
        exchange_tz=TZ,
        trade_count_after=25,
        trade_count_before=100,
        min_trades=10,
        source="focus",
    )
    assert payload["entry_window"]["enabled"] is True
    assert payload["entry_window"]["timezone"] == TZ
    assert payload["entry_window_armed"] is True
    assert payload["entry_window_promote_provenance"]["status"] == "armed"
    assert payload["entry_window_promote_provenance"]["sample_warning"] is False
    assert payload["backtest_widget_state"]["backtest_entry_window_enabled"] is True
    assert payload["backtest_widget_state"]["backtest_entry_window_mode"] == "rth_segments"
    assert payload["backtest_widget_state"]["backtest_entry_window_rth_segments"] == [
        "rth_open_30m"
    ]


def test_promote_clock_range_widget_state():
    window = entry_window_from_bucket(
        "entry_hour_bucket",
        "09:00",
        exchange_tz=TZ,
        bucket_tz="America/Chicago",
    )
    payload = promote_entry_window(
        window,
        exchange_tz=TZ,
        trade_count_after=12,
        min_trades=10,
        source="bucket",
    )
    state = payload["backtest_widget_state"]
    assert state["backtest_entry_window_mode"] == "clock_range"
    assert state["backtest_entry_window_start_time"] == "09:00"
    assert state["backtest_entry_window_end_time"] == "10:00"
    assert state["backtest_entry_window_timezone"] == "America/Chicago"


def test_thin_sample_requires_confirmation():
    window = entry_window_from_bucket(
        "entry_rth_segment", "rth_open_30m", exchange_tz=TZ
    )
    with pytest.raises(ValueError, match="Thin-sample Promote requires confirmation"):
        promote_entry_window(
            window,
            exchange_tz=TZ,
            trade_count_after=3,
            min_trades=10,
            thin_sample_confirmed=False,
        )
    payload = promote_entry_window(
        window,
        exchange_tz=TZ,
        trade_count_after=3,
        min_trades=10,
        thin_sample_confirmed=True,
    )
    assert payload["entry_window_promote_provenance"]["sample_warning"] is True
    assert payload["entry_window_promote_provenance"]["thin_sample_confirmed"] is True


def test_cannot_promote_disabled_window():
    with pytest.raises(ValueError, match="disabled"):
        promote_entry_window({"enabled": False}, exchange_tz=TZ, trade_count_after=20)


def test_apply_and_clear_armed_session_state():
    window = entry_window_from_bucket(
        "entry_rth_segment", "rth_open_30m", exchange_tz=TZ
    )
    payload = promote_entry_window(
        window,
        exchange_tz=TZ,
        trade_count_after=20,
        min_trades=10,
    )
    session: dict = {
        "focus_entry_window": {"enabled": True, "mode": "rth_segments"},
        "focused_trade_summary": {"trade_count": 20},
    }
    apply_promote_to_session_state(session, payload)
    assert session["entry_window_armed"] is True
    assert session["entry_window"]["enabled"] is True
    assert session["backtest_entry_window_enabled"] is True
    # Focus overlay untouched
    assert session["focus_entry_window"]["enabled"] is True
    assert session["focused_trade_summary"]["trade_count"] == 20

    clear_armed_entry_window(session)
    assert session.get("entry_window_armed") in (False, None)
    assert session["entry_window"]["enabled"] is False
    assert session["backtest_entry_window_enabled"] is False
    assert session["focus_entry_window"]["enabled"] is True


def test_clear_armed_noop_when_not_armed():
    session = {
        "entry_window": {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
            "timezone": TZ,
        },
        "entry_window_armed": False,
        "backtest_entry_window_enabled": True,
    }
    clear_armed_entry_window(session)
    assert session["entry_window"]["enabled"] is True
    assert session["backtest_entry_window_enabled"] is True


def test_backtest_widget_state_disabled():
    state = backtest_widget_state_from_entry_window({"enabled": False}, exchange_tz=TZ)
    assert state == {"backtest_entry_window_enabled": False}
