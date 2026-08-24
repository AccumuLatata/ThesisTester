"""TV2 tick VAP prior-profile table — plan §10.2."""

from __future__ import annotations

from datetime import date
import inspect

import numpy as np
import pandas as pd
import pytest

from thesistester.data.quantower_ticks import TickChunk
from thesistester.levels.profile import _compute_profile, compute_profile_levels
from thesistester.levels.session_date import trading_session_date
from thesistester.levels.tick_vap import (
    PRIOR_PROFILE_TABLE_COLUMNS,
    VA_SOURCE_TICK_LAST,
    PriorProfileTable,
    build_prior_profile_table,
    map_shifted_prior_profile,
)

TZ = "America/New_York"
ES_TICK = 0.25


def _chunk(session: date, prints: list[tuple[str, float, float]]) -> TickChunk:
    stamps = pd.to_datetime([row[0] for row in prints], utc=True)
    ticks = pd.DataFrame(
        {
            "timestamp": stamps,
            "price": [row[1] for row in prints],
            "volume": [row[2] for row in prints],
        }
    )
    return TickChunk(
        session_date=session,
        ticks=ticks,
        source_paths=("synthetic",),
        filename_window_mismatch=False,
        warnings=(),
        first_row_utc=pd.Timestamp(stamps.min()),
        last_row_utc=pd.Timestamp(stamps.max()),
    )


def _empty_chunk(session: date) -> TickChunk:
    ticks = pd.DataFrame(columns=["timestamp", "price", "volume"])
    dummy = pd.Timestamp("2026-06-02 13:30:00", tz="UTC")
    return TickChunk(
        session_date=session,
        ticks=ticks,
        source_paths=("empty",),
        filename_window_mismatch=False,
        warnings=(),
        first_row_utc=dummy,
        last_row_utc=dummy,
    )


# Hand-computed 1-tick ES prints (tick 0.25, 70% expander).
# Session 2026-06-02: 100.00×10, 100.25×30, 100.50×5 → POC 100.25, VAL 100.00, VAH 100.25
# Session 2026-06-03: 101.00×8, 101.25×9 → POC 101.25, VAL 101.00, VAH 101.25
SESSION_A = date(2026, 6, 2)
SESSION_B = date(2026, 6, 3)
PRINTS_A = [
    ("2026-06-02 13:30:00", 100.00, 10.0),
    ("2026-06-02 13:31:00", 100.25, 30.0),
    ("2026-06-02 13:32:00", 100.50, 5.0),
]
PRINTS_B = [
    ("2026-06-03 13:30:00", 101.00, 8.0),
    ("2026-06-03 13:31:00", 101.25, 9.0),
]


def _two_session_table(**kwargs) -> PriorProfileTable:
    return build_prior_profile_table(
        [_chunk(SESSION_A, PRINTS_A), _chunk(SESSION_B, PRINTS_B)],
        instrument="ES",
        **kwargs,
    )


def test_hand_computed_one_tick_two_session_table_and_shift():
    table = _two_session_table()
    pd_rows = table.family_rows("pd").sort_values("period_key")
    assert list(pd_rows["period_key"]) == ["2026-06-02", "2026-06-03"]
    assert pd_rows["va_source"].eq(VA_SOURCE_TICK_LAST).all()
    assert pd_rows["aggregation_ticks"].tolist() == [1, 1]
    np.testing.assert_allclose(pd_rows["VAH"].to_numpy(), [100.25, 101.25])
    np.testing.assert_allclose(pd_rows["VAL"].to_numpy(), [100.00, 101.00])
    np.testing.assert_allclose(pd_rows["POC"].to_numpy(), [100.25, 101.25])

    mapped = map_shifted_prior_profile(
        pd.Series([SESSION_A, SESSION_B], name="period"),
        table,
        family="pd",
    )
    assert pd.isna(mapped["pdVAH"].iloc[0])
    assert pd.isna(mapped["pdVAL"].iloc[0])
    assert pd.isna(mapped["pdPOC"].iloc[0])
    np.testing.assert_allclose(mapped["pdVAH"].iloc[1], 100.25)
    np.testing.assert_allclose(mapped["pdVAL"].iloc[1], 100.00)
    np.testing.assert_allclose(mapped["pdPOC"].iloc[1], 100.25)


def test_expander_matches_phase3_typical_vectors():
    vah, val, poc = _compute_profile(
        [99.75, 100.0, 100.25, 100.5],
        [20.0, 40.0, 30.0, 10.0],
        tick_size=ES_TICK,
        value_area_pct=0.70,
    )
    assert (vah, val, poc) == (100.25, 100.0, 100.0)

    vah, val, poc = _compute_profile(
        [100.0, 100.25, 100.5],
        [10.0, 30.0, 5.0],
        tick_size=ES_TICK,
        value_area_pct=0.70,
    )
    assert poc == pytest.approx(100.25)

    vah, val, poc = _compute_profile(
        [100.0, 101.0, 102.0],
        [10.0, 30.0, 5.0],
        tick_size=ES_TICK,
        value_area_pct=0.70,
    )
    assert (vah, val, poc) == (101.0, 100.0, 101.0)


def test_week_table_equals_merged_day_histograms_not_a_second_tick_pass():
    table = _two_session_table()
    pw = table.family_rows("pw")
    assert len(pw) == 1
    all_prices = [row[1] for row in PRINTS_A + PRINTS_B]
    all_volumes = [row[2] for row in PRINTS_A + PRINTS_B]
    vah, val, poc = _compute_profile(
        all_prices, all_volumes, tick_size=ES_TICK, value_area_pct=0.70
    )
    np.testing.assert_allclose(pw["VAH"].iloc[0], vah)
    np.testing.assert_allclose(pw["VAL"].iloc[0], val)
    np.testing.assert_allclose(pw["POC"].iloc[0], poc)
    assert pw["n_ticks"].iloc[0] == 5
    assert pw["sum_volume"].iloc[0] == pytest.approx(62.0)

    pm = table.family_rows("pm")
    assert list(pm["period_key"]) == ["2026-06"]
    np.testing.assert_allclose(pm["POC"].iloc[0], poc)


def test_period_keys_match_compute_profile_levels_calendar():
    table = _two_session_table()
    bars = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-06-02 09:30:00", "2026-06-03 09:30:00"]
            ).tz_localize(TZ),
            "open": [100.0, 101.0],
            "high": [100.0, 101.0],
            "low": [100.0, 101.0],
            "close": [100.0, 101.0],
            "volume": [1.0, 1.0],
        }
    )
    local_ts = bars["timestamp"].dt.tz_convert(TZ)
    day_key = trading_session_date(local_ts, "18:00")
    day_key_ts = pd.to_datetime(day_key)
    week_key = day_key_ts.dt.to_period("W-SUN")
    month_key = day_key_ts.dt.to_period("M")
    assert set(table.family_rows("pd")["period_key"]) == {str(key) for key in day_key}
    assert set(table.family_rows("pw")["period_key"]) == {str(key) for key in week_key}
    assert set(table.family_rows("pm")["period_key"]) == {str(key) for key in month_key}


def test_parquet_round_trip_preserves_locked_columns(tmp_path):
    table = _two_session_table()
    path = tmp_path / "prior_profile.parquet"
    table.to_parquet(path)
    loaded = PriorProfileTable.from_parquet(path)
    assert list(loaded.frame.columns) == list(PRIOR_PROFILE_TABLE_COLUMNS)
    pd.testing.assert_frame_equal(table.frame, loaded.frame, check_dtype=True)


def test_empty_chunk_emits_no_period_row():
    table = build_prior_profile_table(
        [_empty_chunk(SESSION_A), _chunk(SESSION_B, PRINTS_B)],
        instrument="ES",
    )
    assert list(table.family_rows("pd")["period_key"]) == ["2026-06-03"]
    empty_only = build_prior_profile_table([_empty_chunk(SESSION_A)], instrument="ES")
    assert empty_only.frame.empty
    assert list(empty_only.frame.columns) == list(PRIOR_PROFILE_TABLE_COLUMNS)


def test_compute_profile_levels_still_emits_typical_pdva_without_table():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01 09:30:00", periods=3, freq="1h", tz=TZ),
            "open": [100.0, 100.25, 100.5],
            "high": [100.0, 100.25, 100.5],
            "low": [100.0, 100.25, 100.5],
            "close": [100.0, 100.25, 100.5],
            "volume": [10.0, 30.0, 5.0],
        }
    )
    out = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"])
    assert "pdVAH" in out.columns
    assert "pdPOC" in out.columns


def test_tick_vap_module_does_not_import_streamlit_or_open_15s():
    import thesistester.levels.tick_vap as module

    source = inspect.getsource(module)
    assert "import streamlit" not in source
    assert "from pages" not in source
    assert "15s" not in source
    assert "load_ohlcv" not in source
    assert "_compute_profile(" in source
