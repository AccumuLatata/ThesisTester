"""Phase 1 — prev30mVWAP tests (plan §10.1–10.6)."""

from __future__ import annotations

import datetime
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from thesistester.assistant.page_summaries import summarize_levels_state
from thesistester.config import INSTRUMENTS
from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_prev30m_vwap_levels
from thesistester.setup import (
    NON_LEVEL_OUTPUT_COLUMNS,
    available_level_columns,
    validate_setup_config,
)
from thesistester.visualization.backtest_chart import _BASE_COLUMNS


TZ = "America/New_York"


def _bar(
    ts: pd.Timestamp,
    *,
    high: float,
    low: float,
    close: float,
    volume: float,
    open_: float | None = None,
) -> dict:
    return {
        "timestamp": ts,
        "open": float(close if open_ is None else open_),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": float(volume),
    }


def _bars_1min(
    start: str,
    n: int,
    *,
    high: float = 100.0,
    low: float = 99.0,
    close: float = 99.5,
    volume: float = 10.0,
    step_minutes: int = 1,
) -> list[dict]:
    start_ts = pd.Timestamp(start, tz=TZ)
    rows = []
    for i in range(n):
        ts = start_ts + pd.Timedelta(minutes=i * step_minutes)
        rows.append(_bar(ts, high=high, low=low, close=close, volume=volume))
    return rows


def _df(rows: list[dict]) -> pd.DataFrame:
    return tag_session(pd.DataFrame(rows), instrument="ES")


def _naive_df() -> pd.DataFrame:
    df = _df(_bars_1min("2026-06-01 18:00", 5))
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    return df


def _two_bracket_fixture() -> pd.DataFrame:
    """Session open 18:00: two full 30m brackets with distinct VWAP inputs."""
    rows: list[dict] = []
    # Bracket 0: 18:00–18:30 — two bars, easy hand VWAP.
    # bar0: tp=(101+99+100)/3=100, vol=10 → pv=1000
    # bar1: tp=(103+101+102)/3=102, vol=10 → pv=1020
    # VWAP = 2020/20 = 101.0
    rows.append(
        _bar(
            pd.Timestamp("2026-06-01 18:00", tz=TZ),
            high=101,
            low=99,
            close=100,
            volume=10,
        )
    )
    rows.append(
        _bar(
            pd.Timestamp("2026-06-01 18:15", tz=TZ),
            high=103,
            low=101,
            close=102,
            volume=10,
        )
    )
    # Bracket 1: 18:30–19:00
    # tp bars: 200, 204 → VWAP 202 with equal volume
    rows.append(
        _bar(
            pd.Timestamp("2026-06-01 18:30", tz=TZ),
            high=201,
            low=199,
            close=200,
            volume=10,
        )
    )
    rows.append(
        _bar(
            pd.Timestamp("2026-06-01 18:45", tz=TZ),
            high=205,
            low=203,
            close=204,
            volume=10,
        )
    )
    # Bracket 2 open (completes bracket 1)
    rows.append(
        _bar(
            pd.Timestamp("2026-06-01 19:00", tz=TZ),
            high=210,
            low=208,
            close=209,
            volume=10,
        )
    )
    return _df(rows)


# ---------------------------------------------------------------------------
# §10.1 Gate / contract
# ---------------------------------------------------------------------------


def test_disabled_returns_empty_no_columns():
    df = _df(_bars_1min("2026-06-01 18:00", 5))
    out = compute_prev30m_vwap_levels(df, enabled=False)
    assert list(out.columns) == []
    assert len(out) == len(df)


def test_disabled_skips_validation():
    out = compute_prev30m_vwap_levels(_naive_df(), enabled=False)
    assert list(out.columns) == []
    out2 = compute_prev30m_vwap_levels(
        _df(_bars_1min("2026-06-01 18:00", 2)), enabled=False, validity_periods=0
    )
    assert list(out2.columns) == []
    out3 = compute_prev30m_vwap_levels(
        _df(_bars_1min("2026-06-01 18:00", 2)), instrument="NOPE", enabled=False
    )
    assert list(out3.columns) == []


def test_enabled_naive_timestamp_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_prev30m_vwap_levels(_naive_df(), enabled=True)


def test_enabled_bad_instrument_raises():
    with pytest.raises(ValueError, match="Unsupported instrument"):
        compute_prev30m_vwap_levels(
            _df(_bars_1min("2026-06-01 18:00", 2)), instrument="ZZ", enabled=True
        )


def test_enabled_validity_zero_raises():
    with pytest.raises(ValueError, match="validity_periods"):
        compute_prev30m_vwap_levels(
            _df(_bars_1min("2026-06-01 18:00", 2)), enabled=True, validity_periods=0
        )


def test_enabled_validity_numpy_int64_accepted():
    """API validate_run_spec accepts Integral; compute must not diverge."""
    df = _df(_bars_1min("2026-06-01 18:00", 40, high=100, low=99, close=99.5, volume=10))
    out = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=np.int64(1))
    assert "prev30mVWAP" in out.columns
    assert out["prev30mVWAP"].notna().any()


def test_enabled_nat_timestamp_raises_clear_error():
    df = _df(_bars_1min("2026-06-01 18:00", 3))
    df.loc[1, "timestamp"] = pd.NaT
    with pytest.raises(ValueError, match="non-NaT"):
        compute_prev30m_vwap_levels(df, enabled=True)


def test_session_open_preserves_eth_start_seconds():
    from thesistester.levels.prev30m_vwap import _parse_eth_start, _session_open_ts

    eth_time = _parse_eth_start("18:00:30")
    open_ts = _session_open_ts(datetime.date(2026, 6, 2), eth_time, TZ)
    assert open_ts == pd.Timestamp("2026-06-01 18:00:30", tz=TZ)


def test_compute_all_levels_disabled_adds_no_prev30m_columns():
    df = _df(_bars_1min("2026-06-01 18:00", 40))
    out = compute_all_levels(df, instrument="ES", prev30m_vwap_enabled=False)
    assert "prev30mVWAP" not in out.columns
    assert "prev30mVWAP_hit_m1" not in out.columns
    assert "prev30mVWAP_hit_m5" not in out.columns


def test_enabling_adds_exact_columns():
    df = _two_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True)
    assert list(out.columns) == ["prev30mVWAP", "prev30mVWAP_hit_m1", "prev30mVWAP_hit_m5"]


def test_existing_families_unchanged_when_prev30m_enabled():
    df = tag_session(_df(_bars_1min("2026-06-02 09:30", 40)), "ES")
    base = compute_all_levels(
        df,
        instrument="ES",
        pivots_enabled=True,
        session_vwap_enabled=True,
        single_prints_enabled=True,
        apoc_enabled=True,
        prev30m_vwap_enabled=False,
    )
    with_prev = compute_all_levels(
        df,
        instrument="ES",
        pivots_enabled=True,
        session_vwap_enabled=True,
        single_prints_enabled=True,
        apoc_enabled=True,
        prev30m_vwap_enabled=True,
    )
    for col in base.columns:
        pd.testing.assert_series_equal(base[col], with_prev[col], check_names=True)
    assert "prev30mVWAP" in with_prev.columns


# ---------------------------------------------------------------------------
# §10.2 Bracket math / freeze
# ---------------------------------------------------------------------------


def test_exact_bracket_vwap_and_emission_timing():
    df = _two_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True)
    # Bracket 0 incomplete on first two bars
    assert np.isnan(out["prev30mVWAP"].iloc[0])
    assert np.isnan(out["prev30mVWAP"].iloc[1])
    # First bar of bracket 1 emits V0 = 101.0
    assert out["prev30mVWAP"].iloc[2] == pytest.approx(101.0)
    assert out["prev30mVWAP"].iloc[3] == pytest.approx(101.0)
    # Bracket 2 open emits V1 = 202.0
    assert out["prev30mVWAP"].iloc[4] == pytest.approx(202.0)


def test_value_constant_inside_validity_window():
    df = _two_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True)
    assert out["prev30mVWAP"].iloc[2] == out["prev30mVWAP"].iloc[3]


def test_incomplete_current_bracket_excluded():
    # Only one incomplete bracket — no freeze yet
    df = _df(
        [
            _bar(pd.Timestamp("2026-06-01 18:00", tz=TZ), high=101, low=99, close=100, volume=10),
            _bar(pd.Timestamp("2026-06-01 18:10", tz=TZ), high=102, low=100, close=101, volume=10),
        ]
    )
    out = compute_prev30m_vwap_levels(df, enabled=True)
    assert out["prev30mVWAP"].isna().all()


def test_zero_volume_bracket_produces_no_freeze():
    rows = _bars_1min("2026-06-01 18:00", 30, volume=0.0)
    rows.extend(_bars_1min("2026-06-01 18:30", 5, high=110, low=109, close=109.5, volume=10))
    df = _df(rows).sort_values("timestamp").reset_index(drop=True)
    out = compute_prev30m_vwap_levels(df, enabled=True)
    # Bracket 0 zero-volume → no freeze at 18:30+
    after = df["timestamp"] >= pd.Timestamp("2026-06-01 18:30", tz=TZ)
    assert out.loc[after, "prev30mVWAP"].isna().all()


# ---------------------------------------------------------------------------
# §10.3 Full-session ETH + RTH
# ---------------------------------------------------------------------------


def test_eth_emits_when_freeze_exists_unlike_dvwap():
    df = _two_bracket_fixture()
    out = compute_all_levels(
        df,
        instrument="ES",
        session_vwap_enabled=True,
        prev30m_vwap_enabled=True,
    )
    eth_mask = out["session"].eq("ETH")
    assert eth_mask.any()
    # prev30mVWAP non-NaN on ETH after freeze; dVWAP_RTH stays NaN on ETH
    assert (
        out.loc[
            eth_mask & out["timestamp"].ge(pd.Timestamp("2026-06-01 18:30", tz=TZ)), "prev30mVWAP"
        ]
        .notna()
        .all()
    )
    assert out.loc[eth_mask, "dVWAP_RTH"].isna().all()


def test_no_reset_at_rth_open():
    rows = []
    # Pre-RTH brackets on the session-open clock (still ETH until 09:30).
    rows.extend(_bars_1min("2026-06-02 08:30", 30, high=100, low=99, close=99.5, volume=10))
    rows.extend(_bars_1min("2026-06-02 09:00", 30, high=110, low=109, close=109.5, volume=10))
    # RTH open is a session-open bracket boundary, not a reset.
    rows.extend(_bars_1min("2026-06-02 09:30", 5, high=120, low=119, close=119.5, volume=10))
    df = _df(rows).sort_values("timestamp").reset_index(drop=True)
    out = compute_prev30m_vwap_levels(df, enabled=True)
    merged = df.join(out)
    rth = merged[merged["session"].eq("RTH")]
    assert not rth.empty
    assert rth["prev30mVWAP"].notna().all()
    # At 09:30, emit VWAP of 09:00–09:30 (= 109.5 with flat bars)
    assert rth["prev30mVWAP"].iloc[0] == pytest.approx(109.5)


def test_session_boundary_halt_finalization_seeds_next_session():
    """Final 16:30–17:00 bracket freezes at next session open (no in-session >=17:00)."""
    rows = []
    # Prior session final bracket 16:30–17:00 (halt) — no bar at/after 17:00 in-session.
    rows.append(
        _bar(
            pd.Timestamp("2026-06-02 16:30", tz=TZ),
            high=101,
            low=99,
            close=100,
            volume=10,
        )
    )
    rows.append(
        _bar(
            pd.Timestamp("2026-06-02 16:45", tz=TZ),
            high=103,
            low=101,
            close=102,
            volume=10,
        )
    )
    # Next session open 18:00 (session date 2026-06-03)
    rows.append(
        _bar(
            pd.Timestamp("2026-06-02 18:00", tz=TZ),
            high=110,
            low=109,
            close=109.5,
            volume=10,
        )
    )
    df = _df(rows)
    out = compute_prev30m_vwap_levels(df, enabled=True)
    # During final bracket: no freeze yet (no prior)
    assert np.isnan(out["prev30mVWAP"].iloc[0])
    assert np.isnan(out["prev30mVWAP"].iloc[1])
    # Next session open seeded with V = 101.0
    assert out["prev30mVWAP"].iloc[2] == pytest.approx(101.0)


def test_missing_eth_start_raises(monkeypatch):
    empty_eth = replace(INSTRUMENTS["ES"], eth_start="")
    monkeypatch.setitem(INSTRUMENTS, "ES", empty_eth)
    with pytest.raises(ValueError, match="eth_start"):
        compute_prev30m_vwap_levels(_df(_bars_1min("2026-06-01 18:00", 2)), enabled=True)


def test_mid_session_dataset_end_does_not_finalize_future_shock():
    full_rows = _bars_1min("2026-06-01 18:00", 45, high=100, low=99, close=99.5, volume=10)
    full = _df(full_rows)
    truncated = full.iloc[:20].copy()  # stops inside first bracket / early second
    # Ensure truncation is mid-bracket relative to 30m clock: 20 minutes into session
    out_trunc = compute_prev30m_vwap_levels(truncated, enabled=True)
    # No completed freeze should exist yet if still inside first bracket...
    # 20 one-minute bars from 18:00 → last ts 18:19, still bracket 0 → all NaN
    assert out_trunc["prev30mVWAP"].isna().all()

    out_full = compute_prev30m_vwap_levels(full, enabled=True)
    # Prior truncated rows must match full compute prefix (future-shock)
    pd.testing.assert_frame_equal(
        out_trunc.reset_index(drop=True),
        out_full.iloc[:20].reset_index(drop=True),
    )


# ---------------------------------------------------------------------------
# §10.4 TTL
# ---------------------------------------------------------------------------


def test_ttl_n1_replace_each_period():
    df = _two_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=1)
    assert out["prev30mVWAP"].iloc[2] == pytest.approx(101.0)
    assert out["prev30mVWAP"].iloc[4] == pytest.approx(202.0)


def test_ttl_survives_zero_volume_intermediate():
    rows = []
    # Bracket 0 with volume → freeze 100-ish
    rows.extend(
        [
            _bar(pd.Timestamp("2026-06-01 18:00", tz=TZ), high=101, low=99, close=100, volume=10),
            _bar(pd.Timestamp("2026-06-01 18:15", tz=TZ), high=101, low=99, close=100, volume=10),
        ]
    )
    # Bracket 1 zero volume
    rows.extend(
        [
            _bar(pd.Timestamp("2026-06-01 18:30", tz=TZ), high=120, low=119, close=119.5, volume=0),
            _bar(pd.Timestamp("2026-06-01 18:45", tz=TZ), high=120, low=119, close=119.5, volume=0),
        ]
    )
    # Bracket 2 open
    rows.append(
        _bar(pd.Timestamp("2026-06-01 19:00", tz=TZ), high=130, low=129, close=129.5, volume=10)
    )
    df = _df(rows)
    out_n1 = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=1)
    out_n2 = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=2)
    # At 18:30: V0 active for both
    assert out_n1["prev30mVWAP"].iloc[2] == pytest.approx(100.0)
    # At 19:00 (bracket 2): N=1 expired (formed=0, valid through bracket 1 only)
    assert np.isnan(out_n1["prev30mVWAP"].iloc[4])
    # N=2 still valid through bracket 2
    assert out_n2["prev30mVWAP"].iloc[4] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# §10.5 Early-window hits
# ---------------------------------------------------------------------------


def _hit_fixture(*, touch_minute: int | None) -> pd.DataFrame:
    """Bracket0 then bracket1 where optional touch occurs at minute offset in bracket1."""
    rows = _bars_1min("2026-06-01 18:00", 30, high=100, low=99, close=99.5, volume=10)
    # V0 ≈ 99.5. Build bracket1 bars 18:30..18:40
    for i in range(11):
        ts = pd.Timestamp("2026-06-01 18:30", tz=TZ) + pd.Timedelta(minutes=i)
        if touch_minute is not None and i == touch_minute:
            rows.append(_bar(ts, high=100, low=99, close=99.5, volume=10))  # touches ~99.5
        else:
            rows.append(_bar(ts, high=110, low=109, close=109.5, volume=10))  # miss
    return _df(rows)


def test_hit_m1_timing_and_no_rewrite():
    df = _hit_fixture(touch_minute=0).sort_values("timestamp").reset_index(drop=True)
    out = df.join(compute_prev30m_vwap_levels(df, enabled=True))
    b1 = out[out["timestamp"] >= pd.Timestamp("2026-06-01 18:30", tz=TZ)].reset_index(drop=True)
    # 18:30 row stays NaN on hit_m1
    assert np.isnan(b1["prev30mVWAP_hit_m1"].iloc[0])
    # From 18:31 onward finalized 1.0
    assert b1["prev30mVWAP_hit_m1"].iloc[1] == pytest.approx(1.0)
    assert (b1["prev30mVWAP_hit_m1"].iloc[1:] == 1.0).all()


def test_hit_m1_miss():
    df = _hit_fixture(touch_minute=None).sort_values("timestamp").reset_index(drop=True)
    out = df.join(compute_prev30m_vwap_levels(df, enabled=True))
    b1 = out[out["timestamp"] >= pd.Timestamp("2026-06-01 18:30", tz=TZ)].reset_index(drop=True)
    assert np.isnan(b1["prev30mVWAP_hit_m1"].iloc[0])
    assert b1["prev30mVWAP_hit_m1"].iloc[1] == pytest.approx(0.0)


def test_touch_only_after_minute1_not_m1_but_m5():
    df = _hit_fixture(touch_minute=2).sort_values("timestamp").reset_index(drop=True)
    out = df.join(compute_prev30m_vwap_levels(df, enabled=True))
    b1 = out[out["timestamp"] >= pd.Timestamp("2026-06-01 18:30", tz=TZ)].reset_index(drop=True)
    assert b1["prev30mVWAP_hit_m1"].iloc[1] == pytest.approx(0.0)
    # m5 still NaN before 18:35
    assert np.isnan(b1["prev30mVWAP_hit_m5"].iloc[4])
    assert b1["prev30mVWAP_hit_m5"].iloc[5] == pytest.approx(1.0)


def test_hit_nan_when_level_nan_at_open():
    df = _df(_bars_1min("2026-06-01 18:00", 10))
    out = compute_prev30m_vwap_levels(df, enabled=True)
    assert out["prev30mVWAP_hit_m1"].isna().all()
    assert out["prev30mVWAP_hit_m5"].isna().all()


def test_nesting_invariant():
    for touch in (0, 2, None):
        out = compute_prev30m_vwap_levels(_hit_fixture(touch_minute=touch), enabled=True)
        both = out.dropna(subset=["prev30mVWAP_hit_m1", "prev30mVWAP_hit_m5"])
        if both.empty:
            continue
        m1 = both["prev30mVWAP_hit_m1"].to_numpy()
        m5 = both["prev30mVWAP_hit_m5"].to_numpy()
        assert np.all(~((m1 == 1.0) & (m5 == 0.0)))
        assert np.all(~((m5 == 0.0) & (m1 == 1.0)))


def test_coarse_base_5min_disables_m1_keeps_m5():
    rows = _bars_1min(
        "2026-06-01 18:00", 6, step_minutes=5, high=100, low=99, close=99.5, volume=10
    )
    # 18:00, 18:05, ... 18:25 (bracket0), then 18:30, 18:35 (bracket1)
    rows.append(
        _bar(pd.Timestamp("2026-06-01 18:30", tz=TZ), high=100, low=99, close=99.5, volume=10)
    )
    rows.append(
        _bar(pd.Timestamp("2026-06-01 18:35", tz=TZ), high=110, low=109, close=109.5, volume=10)
    )
    df = _df(rows)
    out = compute_prev30m_vwap_levels(df, enabled=True)
    assert out["prev30mVWAP_hit_m1"].isna().all()
    # m5 finalizes at/after 18:35
    last = out.iloc[-1]
    assert last["prev30mVWAP_hit_m5"] == pytest.approx(1.0)


def test_coarse_base_2min_disables_both_hits():
    rows = _bars_1min(
        "2026-06-01 18:00", 20, step_minutes=2, high=100, low=99, close=99.5, volume=10
    )
    df = _df(rows)
    out = compute_prev30m_vwap_levels(df, enabled=True)
    assert "prev30mVWAP" in out.columns
    assert out["prev30mVWAP_hit_m1"].isna().all()
    assert out["prev30mVWAP_hit_m5"].isna().all()


def test_hit_columns_not_setup_or_chart_eligible():
    df = _two_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True)
    merged = df.join(out)
    cols = available_level_columns(merged)
    assert "prev30mVWAP" in cols
    assert "prev30mVWAP_hit_m1" not in cols
    assert "prev30mVWAP_hit_m5" not in cols
    assert "prev30mVWAP_hit_m1" in NON_LEVEL_OUTPUT_COLUMNS
    assert "prev30mVWAP_hit_m5" in NON_LEVEL_OUTPUT_COLUMNS
    # Chart candidate filter mirrors backtest_chart exclusion
    chart_candidates = [
        c
        for c in merged.columns
        if c not in _BASE_COLUMNS
        and c not in NON_LEVEL_OUTPUT_COLUMNS
        and pd.api.types.is_numeric_dtype(merged[c])
    ]
    assert "prev30mVWAP" in chart_candidates
    assert "prev30mVWAP_hit_m1" not in chart_candidates
    # Headless setup validation must reject diagnostic columns too.
    errors = validate_setup_config(
        {
            "name": "hit diagnostic misuse",
            "description": "",
            "instrument": "ES",
            "selected_levels": ["prev30mVWAP", "prev30mVWAP_hit_m1"],
            "tolerance_ticks": 4.0,
            "min_confluences": 1,
            "max_confluences": 2,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger": "touch",
            "direction": "both",
            "confluence_mode": "global_cluster",
        }
    )
    assert any("diagnostic" in err.lower() for err in errors)
    # Assistant levels summary must not list diagnostics as price levels.
    summary = summarize_levels_state({"levels": merged, "levels_settings": {}})
    assert "prev30mVWAP" in summary["level_columns"]
    assert "prev30mVWAP_hit_m1" not in summary["level_columns"]
    assert "prev30mVWAP_hit_m5" not in summary["level_columns"]


# ---------------------------------------------------------------------------
# §10.6 Future-shock / determinism
# ---------------------------------------------------------------------------


def test_future_shock_append_in_session():
    full = _df(_bars_1min("2026-06-01 18:00", 90, high=100, low=99, close=99.5, volume=10))
    head = full.iloc[:50].copy()
    out_head = compute_prev30m_vwap_levels(head, enabled=True)
    out_full = compute_prev30m_vwap_levels(full, enabled=True)
    pd.testing.assert_frame_equal(
        out_head.reset_index(drop=True),
        out_full.iloc[:50].reset_index(drop=True),
    )


def test_future_shock_append_next_session():
    rows = _bars_1min("2026-06-01 18:00", 60, high=100, low=99, close=99.5, volume=10)
    rows.extend(_bars_1min("2026-06-02 18:00", 30, high=120, low=119, close=119.5, volume=10))
    full = _df(rows)
    head = full.iloc[:60].copy()
    out_head = compute_prev30m_vwap_levels(head, enabled=True)
    out_full = compute_prev30m_vwap_levels(full, enabled=True)
    pd.testing.assert_frame_equal(
        out_head.reset_index(drop=True),
        out_full.iloc[:60].reset_index(drop=True),
    )


def test_unsorted_input_equals_sorted():
    df = _two_bracket_fixture()
    shuffled = df.sample(frac=1.0, random_state=0).reset_index(drop=True)
    out_sorted = compute_prev30m_vwap_levels(df, enabled=True)
    out_shuf = compute_prev30m_vwap_levels(shuffled, enabled=True)
    # Module returns sorted-timeline RangeIndex (same contract as other level families).
    pd.testing.assert_frame_equal(out_sorted, out_shuf)


def test_nq_instrument_supported():
    df = _two_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, instrument="NQ", enabled=True)
    assert out["prev30mVWAP"].iloc[2] == pytest.approx(101.0)


# ---------------------------------------------------------------------------
# Phase 3 — multi-period stack (plan §11 Phase 3)
# ---------------------------------------------------------------------------


def _three_bracket_fixture() -> pd.DataFrame:
    """Three completed brackets with distinct VWAPs: 101, 202, then open of 4th."""
    rows: list[dict] = []
    # Bracket 0 → VWAP 101
    rows.append(
        _bar(pd.Timestamp("2026-06-01 18:00", tz=TZ), high=101, low=99, close=100, volume=10)
    )
    rows.append(
        _bar(pd.Timestamp("2026-06-01 18:15", tz=TZ), high=103, low=101, close=102, volume=10)
    )
    # Bracket 1 → VWAP 202
    rows.append(
        _bar(pd.Timestamp("2026-06-01 18:30", tz=TZ), high=201, low=199, close=200, volume=10)
    )
    rows.append(
        _bar(pd.Timestamp("2026-06-01 18:45", tz=TZ), high=205, low=203, close=204, volume=10)
    )
    # Bracket 2 → VWAP 303
    rows.append(
        _bar(pd.Timestamp("2026-06-01 19:00", tz=TZ), high=302, low=300, close=301, volume=10)
    )
    rows.append(
        _bar(pd.Timestamp("2026-06-01 19:15", tz=TZ), high=306, low=304, close=305, volume=10)
    )
    # Bracket 3 open (completes bracket 2)
    rows.append(
        _bar(pd.Timestamp("2026-06-01 19:30", tz=TZ), high=310, low=308, close=309, volume=10)
    )
    return _df(rows)


def test_phase3_n1_column_parity_no_stack_columns():
    df = _three_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=1)
    assert list(out.columns) == ["prev30mVWAP", "prev30mVWAP_hit_m1", "prev30mVWAP_hit_m5"]
    assert "prev30mVWAP_2" not in out.columns


def test_phase3_n1_age1_matches_mvp_values():
    """Stack refactor must not change age-1 values vs prior single-freeze MVP."""
    df = _three_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=1)
    # Bracket1: V0; bracket2: V1; bracket3: V2
    assert out["prev30mVWAP"].iloc[2] == pytest.approx(101.0)
    assert out["prev30mVWAP"].iloc[4] == pytest.approx(202.0)
    assert out["prev30mVWAP"].iloc[6] == pytest.approx(303.0)


def test_phase3_stack_ages_and_ttl_expiry():
    df = _three_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=2)
    assert list(out.columns)[:3] == ["prev30mVWAP", "prev30mVWAP_2", "prev30mVWAP_hit_m1"]
    assert "prev30mVWAP_3" not in out.columns

    # Bracket 1 open: only age-1 = V0; age-2 still empty
    assert out["prev30mVWAP"].iloc[2] == pytest.approx(101.0)
    assert np.isnan(out["prev30mVWAP_2"].iloc[2])

    # Bracket 2 open: age-1 = V1, age-2 = V0
    assert out["prev30mVWAP"].iloc[4] == pytest.approx(202.0)
    assert out["prev30mVWAP_2"].iloc[4] == pytest.approx(101.0)

    # Bracket 3 open: age-1 = V2, age-2 = V1; V0 expired (TTL=2)
    assert out["prev30mVWAP"].iloc[6] == pytest.approx(303.0)
    assert out["prev30mVWAP_2"].iloc[6] == pytest.approx(202.0)


def test_phase3_stack_depth_n3():
    df = _three_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=3)
    assert "prev30mVWAP_2" in out.columns
    assert "prev30mVWAP_3" in out.columns
    # Bracket 3: ages V2, V1, V0
    assert out["prev30mVWAP"].iloc[6] == pytest.approx(303.0)
    assert out["prev30mVWAP_2"].iloc[6] == pytest.approx(202.0)
    assert out["prev30mVWAP_3"].iloc[6] == pytest.approx(101.0)


def test_phase3_age1_identical_to_n1_when_continuous():
    """With continuous freezes, age-1 under N>1 equals the N=1 MVP column."""
    df = _three_bracket_fixture()
    out_n1 = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=1)
    out_n3 = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=3)
    pd.testing.assert_series_equal(out_n1["prev30mVWAP"], out_n3["prev30mVWAP"], check_names=True)


def test_phase3_cross_session_seeds_stack():
    rows = []
    # Session A: two brackets then halt-style final incomplete period
    rows.append(
        _bar(pd.Timestamp("2026-06-02 15:30", tz=TZ), high=101, low=99, close=100, volume=10)
    )
    rows.append(
        _bar(pd.Timestamp("2026-06-02 15:45", tz=TZ), high=103, low=101, close=102, volume=10)
    )
    # VWAP_A0 = 101
    rows.append(
        _bar(pd.Timestamp("2026-06-02 16:00", tz=TZ), high=201, low=199, close=200, volume=10)
    )
    rows.append(
        _bar(pd.Timestamp("2026-06-02 16:15", tz=TZ), high=205, low=203, close=204, volume=10)
    )
    # VWAP_A1 = 202; final 16:30–17:00 open bracket finalized at session transition
    rows.append(
        _bar(pd.Timestamp("2026-06-02 16:30", tz=TZ), high=302, low=300, close=301, volume=10)
    )
    rows.append(
        _bar(pd.Timestamp("2026-06-02 16:45", tz=TZ), high=306, low=304, close=305, volume=10)
    )
    # VWAP_A2 = 303 (session-boundary finalize)
    # Session B open
    rows.append(
        _bar(pd.Timestamp("2026-06-02 18:00", tz=TZ), high=110, low=109, close=109.5, volume=10)
    )
    df = _df(rows)
    out = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=2)
    seed_row = out.iloc[-1]
    assert seed_row["prev30mVWAP"] == pytest.approx(303.0)
    assert seed_row["prev30mVWAP_2"] == pytest.approx(202.0)


def test_phase3_seed_does_not_resurrect_expired_stack_ages():
    """Expired ages at session end must not reappear as stack columns at S+1 open."""
    from thesistester.levels.prev30m_vwap import MAX_VALIDITY_PERIODS

    rows = []
    # Bracket 0 freeze ~101
    for i in range(30):
        ts = pd.Timestamp("2026-06-01 18:00", tz=TZ) + pd.Timedelta(minutes=i)
        rows.append(_bar(ts, high=101, low=100, close=100.5, volume=10))
    # Bracket 1 freeze ~202
    for i in range(30):
        ts = pd.Timestamp("2026-06-01 18:30", tz=TZ) + pd.Timedelta(minutes=i)
        rows.append(_bar(ts, high=202, low=201, close=201.5, volume=10))
    # Zero-volume gap through brackets 2..6 (no freezes; ages expire for N=3)
    for b in range(2, 7):
        for i in range(30):
            ts = pd.Timestamp("2026-06-01 18:00", tz=TZ) + pd.Timedelta(minutes=b * 30 + i)
            rows.append(_bar(ts, high=50, low=49, close=49.5, volume=0))
    # Bracket 7 freeze ~303
    for i in range(30):
        ts = pd.Timestamp("2026-06-01 18:00", tz=TZ) + pd.Timedelta(minutes=7 * 30 + i)
        rows.append(_bar(ts, high=303, low=302, close=302.5, volume=10))
    # Enter bracket 8 so ages 2/3 are expired in-session
    for i in range(5):
        ts = pd.Timestamp("2026-06-01 18:00", tz=TZ) + pd.Timedelta(minutes=8 * 30 + i)
        rows.append(_bar(ts, high=10, low=9, close=9.5, volume=0))
    # Session B open
    for i in range(5):
        ts = pd.Timestamp("2026-06-02 18:00", tz=TZ) + pd.Timedelta(minutes=i)
        rows.append(_bar(ts, high=10, low=9, close=9.5, volume=10))

    df = _df(rows)
    out = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=3)
    sess1_end = out.loc[df["timestamp"] < pd.Timestamp("2026-06-02 18:00", tz=TZ)].iloc[-1]
    assert sess1_end["prev30mVWAP"] == pytest.approx(302.5)
    assert np.isnan(sess1_end["prev30mVWAP_2"])
    assert np.isnan(sess1_end["prev30mVWAP_3"])

    seed_row = out.loc[df["timestamp"] >= pd.Timestamp("2026-06-02 18:00", tz=TZ)].iloc[0]
    assert seed_row["prev30mVWAP"] == pytest.approx(302.5)
    assert np.isnan(seed_row["prev30mVWAP_2"])
    assert np.isnan(seed_row["prev30mVWAP_3"])

    with pytest.raises(ValueError, match="validity_periods"):
        compute_prev30m_vwap_levels(
            df.iloc[:2], enabled=True, validity_periods=MAX_VALIDITY_PERIODS + 1
        )


def test_phase3_stack_columns_setup_eligible_hits_not():
    df = _three_bracket_fixture()
    out = compute_prev30m_vwap_levels(df, enabled=True, validity_periods=3)
    merged = df.join(out)
    cols = available_level_columns(merged)
    assert "prev30mVWAP" in cols
    assert "prev30mVWAP_2" in cols
    assert "prev30mVWAP_3" in cols
    assert "prev30mVWAP_hit_m1" not in cols
    assert "prev30mVWAP_hit_m5" not in cols


def test_phase3_future_shock_with_stack():
    full = _df(_bars_1min("2026-06-01 18:00", 100, high=100, low=99, close=99.5, volume=10))
    head = full.iloc[:55].copy()
    out_head = compute_prev30m_vwap_levels(head, enabled=True, validity_periods=3)
    out_full = compute_prev30m_vwap_levels(full, enabled=True, validity_periods=3)
    pd.testing.assert_frame_equal(
        out_head.reset_index(drop=True),
        out_full.iloc[:55].reset_index(drop=True),
    )


def test_phase3_helper_column_names():
    from thesistester.levels.prev30m_vwap import (
        is_prev30m_price_level_column,
        prev30m_price_column_names,
        prev30m_stack_column_name,
    )

    assert prev30m_stack_column_name(1) == "prev30mVWAP"
    assert prev30m_stack_column_name(2) == "prev30mVWAP_2"
    assert prev30m_price_column_names(3) == ["prev30mVWAP", "prev30mVWAP_2", "prev30mVWAP_3"]
    assert is_prev30m_price_level_column("prev30mVWAP")
    assert is_prev30m_price_level_column("prev30mVWAP_2")
    assert not is_prev30m_price_level_column("prev30mVWAP_hit_m1")
    assert not is_prev30m_price_level_column("prev30mVWAP_hit_m5")
