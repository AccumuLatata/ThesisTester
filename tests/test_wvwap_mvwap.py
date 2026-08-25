"""WMV1 — developing wVWAP / mVWAP tests (plan §11.1–11.4)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thesistester.assistant.workspace import SESSION_LEVEL_CATALOG
from thesistester.data.sessions import tag_session
from thesistester.levels import (
    compute_all_levels,
    compute_session_levels,
    compute_session_vwap_levels,
)
from thesistester.levels.catalog import PRIOR_PROFILE_LEVEL_NAMES, STATIC_STUDY_LEVEL_NAMES
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.session_vwap import (
    COL_DVWAP,
    COL_DVWAP_RTH,
    COL_MVWAP,
    COL_WVWAP,
    SESSION_VWAP_COLUMNS,
)
from thesistester.persistence import LEVEL_ENGINE_VERSION
from thesistester.setup import (
    NON_LEVEL_OUTPUT_COLUMNS,
    SUGGESTED_DEFAULT_LEVELS,
    available_level_columns,
    validate_setup_config,
)
from thesistester.study.schema import (
    STUDY_SCHEMA_VERSION,
    STUDY_STATIC_LEVEL_NAMES,
    StudySpecError,
    closed_level_token_set,
    normalize_study_spec,
    validate_study_spec,
)
from tests.test_setup_config import _anchor_config, _base_config


TZ = "America/New_York"


def _bar(
    ts: pd.Timestamp,
    high: float,
    low: float,
    close: float,
    volume: float,
    *,
    session: str,
) -> dict:
    return {
        "timestamp": ts,
        "open": (high + low) / 2.0,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "session": session,
    }


def _eth(ts: pd.Timestamp, high: float, low: float, close: float, volume: float) -> dict:
    return _bar(ts, high, low, close, volume, session="ETH")


def _rth(ts: pd.Timestamp, high: float, low: float, close: float, volume: float) -> dict:
    return _bar(ts, high, low, close, volume, session="RTH")


def _expected_cum_vwap(rows: list[dict]) -> list[float]:
    expected: list[float] = []
    cum_pv = 0.0
    cum_v = 0.0
    for row in rows:
        tp = (row["high"] + row["low"] + row["close"]) / 3.0
        cum_pv += tp * row["volume"]
        cum_v += row["volume"]
        expected.append(cum_pv / cum_v if cum_v > 0 else np.nan)
    return expected


def _cme_session_fixture() -> pd.DataFrame:
    rows = [
        _eth(pd.Timestamp("2026-06-01 18:00", tz=TZ), 101.0, 99.0, 100.0, 10.0),
        _eth(pd.Timestamp("2026-06-01 18:01", tz=TZ), 102.0, 100.0, 101.0, 20.0),
        _eth(pd.Timestamp("2026-06-02 08:00", tz=TZ), 103.0, 101.0, 102.0, 30.0),
        _rth(pd.Timestamp("2026-06-02 09:30", tz=TZ), 104.0, 102.0, 103.0, 40.0),
        _rth(pd.Timestamp("2026-06-02 09:31", tz=TZ), 105.0, 103.0, 104.0, 50.0),
    ]
    return pd.DataFrame(rows)


def _intra_week_fixture() -> pd.DataFrame:
    """Two bars in the same trading week (hand-computed VWAP)."""
    return pd.DataFrame(
        [
            _rth(pd.Timestamp("2026-06-02 09:30", tz=TZ), 101.0, 99.0, 100.0, 10.0),
            _rth(pd.Timestamp("2026-06-02 09:31", tz=TZ), 104.0, 102.0, 103.0, 30.0),
        ]
    )


def _week_roll_fixture() -> pd.DataFrame:
    """Friday RTH then Sunday 18:00 ETH open (locked wOpen week roll)."""
    return pd.DataFrame(
        [
            _rth(pd.Timestamp("2026-06-05 09:30", tz=TZ), 301.0, 299.0, 300.0, 10.0),
            _rth(pd.Timestamp("2026-06-05 15:59", tz=TZ), 321.0, 319.0, 320.0, 20.0),
            _eth(pd.Timestamp("2026-06-07 18:00", tz=TZ), 401.0, 399.0, 400.0, 5.0),
            _rth(pd.Timestamp("2026-06-08 09:30", tz=TZ), 421.0, 419.0, 420.0, 15.0),
        ]
    )


def _month_roll_fixture() -> pd.DataFrame:
    """June 30 RTH then 18:00 ETH open (locked mOpen month roll)."""
    return pd.DataFrame(
        [
            _rth(pd.Timestamp("2026-06-30 09:30", tz=TZ), 501.0, 499.0, 500.0, 10.0),
            _rth(pd.Timestamp("2026-06-30 15:59", tz=TZ), 521.0, 519.0, 520.0, 20.0),
            _eth(pd.Timestamp("2026-06-30 18:00", tz=TZ), 601.0, 599.0, 600.0, 5.0),
            _rth(pd.Timestamp("2026-07-01 09:30", tz=TZ), 621.0, 619.0, 620.0, 15.0),
        ]
    )


def _wopen_alignment_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-06-05 09:30:00",
                    "2026-06-05 15:59:00",
                    "2026-06-07 18:00:00",
                    "2026-06-08 09:30:00",
                ]
            ).tz_localize(TZ),
            "open": [300.0, 320.0, 400.0, 420.0],
            "high": [350.0, 360.0, 410.0, 430.0],
            "low": [290.0, 280.0, 390.0, 415.0],
            "close": [340.0, 330.0, 405.0, 425.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        }
    )


def _mopen_alignment_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-06-30 09:30:00",
                    "2026-06-30 15:59:00",
                    "2026-06-30 18:00:00",
                    "2026-07-01 09:30:00",
                ]
            ).tz_localize(TZ),
            "open": [500.0, 520.0, 600.0, 620.0],
            "high": [550.0, 560.0, 610.0, 630.0],
            "low": [490.0, 480.0, 590.0, 615.0],
            "close": [540.0, 530.0, 605.0, 625.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        }
    )


def _naive_df() -> pd.DataFrame:
    df = _intra_week_fixture().copy()
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    return df


def _minimal_study(**overrides):
    study = {
        "name": "wvwap_mini",
        "dataset": {"path": "data/es_1m.csv", "instrument": "ES"},
        "levels": {
            "sma_lengths": [50],
            "ema_lengths": [21],
            "sma_timeframes": ["1min"],
            "ema_timeframes": ["1min"],
        },
        "constants": {
            "direction": "both",
            "tolerance_ticks": 0,
            "min_confluences": 1,
            "max_confluences": 2,
            "min_valid_confluences": 1,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger_params": {},
            "backtest": {
                "stop_loss_ticks": 8,
                "take_profit_ticks": 16,
                "exposure_policy": "single_position",
            },
            "grid": {"enabled": False},
            "validation": {"enabled": False},
            "walk_forward": {"enabled": False},
        },
        "factors": {
            "core_level": ["ONH"],
            "partner_levels": [["SMA_50_1min"]],
            "confluence_mode": ["global_cluster"],
            "trigger": ["touch"],
            "trigger_timeframe": ["base"],
            "otf": [{"enabled": False}],
        },
        "mode_rules": {
            "global_cluster": {
                "selected_levels": ["${core_level}", "${partner_levels...}"],
            },
        },
        "report": {
            "primary_metric": "expectancy_r",
            "secondary_metrics": ["profit_factor", "trade_count"],
            "min_trades": 30,
            "group_by": ["partner_levels"],
            "otf_baseline": {"enabled": False},
            "multiple_testing": "warn",
        },
    }
    study.update(overrides)
    return {"schema_version": STUDY_SCHEMA_VERSION, "study": study}


# ---------------------------------------------------------------------------
# 11.1 Gate / isolation
# ---------------------------------------------------------------------------


def test_disabled_returns_empty_frame_without_validation():
    result = compute_session_vwap_levels(_naive_df(), enabled=False)
    assert list(result.columns) == []
    assert COL_WVWAP not in result.columns
    assert COL_MVWAP not in result.columns


def test_compute_all_levels_disabled_emits_no_session_vwap_columns():
    df = tag_session(_intra_week_fixture(), "ES")
    out = compute_all_levels(df, instrument="ES", session_vwap_enabled=False)
    for col in SESSION_VWAP_COLUMNS:
        assert col not in out.columns


def test_enabled_column_order_is_four_tuple():
    result = compute_session_vwap_levels(_intra_week_fixture(), enabled=True)
    assert list(result.columns) == ["dVWAP_RTH", "dVWAP", "wVWAP", "mVWAP"]
    assert SESSION_VWAP_COLUMNS == (COL_DVWAP_RTH, COL_DVWAP, COL_WVWAP, COL_MVWAP)


def test_dvwap_values_unchanged_on_cme_session_fixture():
    df = _cme_session_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    expected_session = _expected_cum_vwap(df.to_dict("records"))
    assert result[COL_DVWAP].tolist() == pytest.approx(expected_session, rel=1e-9)
    rth_rows = df[df["session"].eq("RTH")].to_dict("records")
    expected_rth = _expected_cum_vwap(rth_rows)
    assert result.loc[df["session"].eq("RTH"), COL_DVWAP_RTH].tolist() == pytest.approx(
        expected_rth, rel=1e-9
    )
    assert result.loc[df["session"].eq("ETH"), COL_DVWAP_RTH].isna().all()


def test_other_families_unchanged_when_session_vwap_enabled():
    df = tag_session(_wopen_alignment_df(), "ES")
    out_off = compute_all_levels(
        df, instrument="ES", opening_range_minutes=5, session_vwap_enabled=False
    )
    out_on = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        session_vwap_enabled=True,
        session_vwap_anchor="RTH",
    )
    for col in out_off.columns:
        pd.testing.assert_series_equal(
            out_off[col].reset_index(drop=True),
            out_on[col].reset_index(drop=True),
            check_names=False,
        )
    assert COL_WVWAP in out_on.columns
    assert COL_MVWAP in out_on.columns
    assert "wOpen" in out_on.columns
    assert "pdPOC" not in out_on.columns
    assert "pdVAH" not in out_on.columns


def test_level_engine_version_bumped_for_additive_htf_vwap():
    assert LEVEL_ENGINE_VERSION >= 10


# ---------------------------------------------------------------------------
# 11.2 Math / boundaries
# ---------------------------------------------------------------------------


def test_wvwap_mvwap_exact_values_intra_period():
    df = _intra_week_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    expected = _expected_cum_vwap(df.to_dict("records"))
    assert result[COL_WVWAP].tolist() == pytest.approx(expected, rel=1e-9)
    assert result[COL_MVWAP].tolist() == pytest.approx(expected, rel=1e-9)
    assert result[COL_WVWAP].iloc[0] == pytest.approx(100.0, rel=1e-9)
    assert result[COL_WVWAP].iloc[1] == pytest.approx(102.25, rel=1e-9)


def test_wvwap_resets_at_sunday_eth_open():
    df = _week_roll_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    v = result[COL_WVWAP]
    prior_week_last = v.iloc[1]
    first_new = v.iloc[2]
    tp_new = (401.0 + 399.0 + 400.0) / 3.0
    assert first_new == pytest.approx(tp_new, rel=1e-9)
    assert first_new != pytest.approx(prior_week_last, rel=1e-3)
    week2 = df.iloc[2:].to_dict("records")
    assert v.iloc[2:].tolist() == pytest.approx(_expected_cum_vwap(week2), rel=1e-9)


def test_period_keys_match_plan_verified_w_sun_fixtures():
    """Lock plan §3.3 timestamps. Friday→Sunday-18:00 also passes under W-MON.

    Monday 2026-06-01 and Sunday 2026-06-07 17:59 share W-SUN (2026-06-01/07)
    but not W-MON. June 30 18:00 resets mVWAP only — same W-SUN week continues.
    """
    df = pd.DataFrame(
        [
            _rth(pd.Timestamp("2026-06-01 09:30", tz=TZ), 101.0, 99.0, 100.0, 10.0),
            _eth(pd.Timestamp("2026-06-07 17:59", tz=TZ), 201.0, 199.0, 200.0, 20.0),
            _eth(pd.Timestamp("2026-06-07 18:00", tz=TZ), 301.0, 299.0, 300.0, 5.0),
            _rth(pd.Timestamp("2026-06-30 17:59", tz=TZ), 401.0, 399.0, 400.0, 10.0),
            _eth(pd.Timestamp("2026-06-30 18:00", tz=TZ), 501.0, 499.0, 500.0, 15.0),
        ]
    )
    tagged = tag_session(df, "ES")
    sessions = compute_session_levels(tagged, instrument="ES")
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    w = result[COL_WVWAP]
    m = result[COL_MVWAP]

    monday_and_sun_1759 = _expected_cum_vwap(df.iloc[:2].to_dict("records"))
    assert w.iloc[:2].tolist() == pytest.approx(monday_and_sun_1759, rel=1e-9)
    assert w.iloc[1] != pytest.approx((201.0 + 199.0 + 200.0) / 3.0, rel=1e-9)

    tp_week_roll = (301.0 + 299.0 + 300.0) / 3.0
    assert w.iloc[2] == pytest.approx(tp_week_roll, rel=1e-9)
    assert w.iloc[2] != pytest.approx(w.iloc[1], rel=1e-3)

    tp_month_roll = (501.0 + 499.0 + 500.0) / 3.0
    assert m.iloc[4] == pytest.approx(tp_month_roll, rel=1e-9)
    assert m.iloc[4] != pytest.approx(m.iloc[3], rel=1e-3)
    assert w.iloc[4] != pytest.approx(tp_month_roll, rel=1e-9)
    assert w.iloc[3] != pytest.approx(w.iloc[4], rel=1e-9)

    week_roll = sessions["timestamp"] >= pd.Timestamp("2026-06-07 18:00:00", tz=TZ)
    month_roll = sessions["timestamp"] >= pd.Timestamp("2026-06-30 18:00:00", tz=TZ)
    assert sessions.loc[~week_roll, "wOpen"].nunique() == 1
    assert float(sessions.loc[~week_roll, "wOpen"].iloc[0]) != float(
        sessions.loc[week_roll, "wOpen"].iloc[0]
    )
    assert float(sessions.loc[~month_roll, "mOpen"].iloc[-1]) != float(
        sessions.loc[month_roll, "mOpen"].iloc[0]
    )


def test_mvwap_resets_at_month_session_open():
    df = _month_roll_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    v = result[COL_MVWAP]
    prior_month_last = v.iloc[1]
    first_new = v.iloc[2]
    tp_new = (601.0 + 599.0 + 600.0) / 3.0
    assert first_new == pytest.approx(tp_new, rel=1e-9)
    assert first_new != pytest.approx(prior_month_last, rel=1e-3)
    month2 = df.iloc[2:].to_dict("records")
    assert v.iloc[2:].tolist() == pytest.approx(_expected_cum_vwap(month2), rel=1e-9)


def test_wvwap_period_membership_matches_wopen():
    df = tag_session(_wopen_alignment_df(), "ES")
    sessions = compute_session_levels(df, instrument="ES")
    vwaps = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    new_week = sessions["timestamp"] >= pd.Timestamp("2026-06-07 18:00:00", tz=TZ)
    wopen_old = sessions.loc[~new_week, "wOpen"]
    wopen_new = sessions.loc[new_week, "wOpen"]
    assert wopen_old.nunique() == 1
    assert wopen_new.nunique() == 1
    assert float(wopen_old.iloc[0]) != float(wopen_new.iloc[0])
    assert vwaps.loc[~new_week, COL_WVWAP].notna().all()
    assert vwaps.loc[new_week, COL_WVWAP].notna().all()
    tp_new = (
        df.loc[new_week, "high"].iloc[0]
        + df.loc[new_week, "low"].iloc[0]
        + df.loc[new_week, "close"].iloc[0]
    ) / 3.0
    assert vwaps.loc[new_week, COL_WVWAP].iloc[0] == pytest.approx(tp_new, rel=1e-9)
    assert vwaps.loc[new_week, COL_WVWAP].iloc[0] != pytest.approx(
        vwaps.loc[~new_week, COL_WVWAP].iloc[-1], rel=1e-3
    )


def test_mvwap_period_membership_matches_mopen():
    df = tag_session(_mopen_alignment_df(), "ES")
    sessions = compute_session_levels(df, instrument="ES")
    vwaps = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    new_month = sessions["timestamp"] >= pd.Timestamp("2026-06-30 18:00:00", tz=TZ)
    mopen_old = sessions.loc[~new_month, "mOpen"]
    mopen_new = sessions.loc[new_month, "mOpen"]
    assert mopen_old.nunique() == 1
    assert mopen_new.nunique() == 1
    assert float(mopen_old.iloc[0]) != float(mopen_new.iloc[0])
    tp_new = (
        df.loc[new_month, "high"].iloc[0]
        + df.loc[new_month, "low"].iloc[0]
        + df.loc[new_month, "close"].iloc[0]
    ) / 3.0
    assert vwaps.loc[new_month, COL_MVWAP].iloc[0] == pytest.approx(tp_new, rel=1e-9)
    assert vwaps.loc[new_month, COL_MVWAP].iloc[0] != pytest.approx(
        vwaps.loc[~new_month, COL_MVWAP].iloc[-1], rel=1e-3
    )


def test_eth_bars_emit_non_nan_when_volume_positive():
    df = _week_roll_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    eth = df["session"].eq("ETH")
    assert result.loc[eth, COL_WVWAP].notna().all()
    assert result.loc[eth, COL_MVWAP].notna().all()


def test_zero_volume_prefix_emits_nan_then_defined():
    rows = [
        _eth(pd.Timestamp("2026-06-01 18:00", tz=TZ), 101.0, 99.0, 100.0, 0.0),
        _eth(pd.Timestamp("2026-06-01 18:01", tz=TZ), 102.0, 100.0, 101.0, 10.0),
    ]
    df = pd.DataFrame(rows)
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    assert np.isnan(result[COL_WVWAP].iloc[0])
    assert np.isnan(result[COL_MVWAP].iloc[0])
    tp = (102.0 + 100.0 + 101.0) / 3.0
    assert result[COL_WVWAP].iloc[1] == pytest.approx(tp, rel=1e-9)
    assert result[COL_MVWAP].iloc[1] == pytest.approx(tp, rel=1e-9)


# ---------------------------------------------------------------------------
# 11.3 PIT
# ---------------------------------------------------------------------------


def test_wvwap_future_shock_within_week():
    base = _intra_week_fixture()
    before = compute_session_vwap_levels(base, instrument="ES", enabled=True)
    extended = pd.concat(
        [
            base,
            pd.DataFrame(
                [_rth(pd.Timestamp("2026-06-03 09:30", tz=TZ), 999.0, 1.0, 500.0, 10000.0)]
            ),
        ],
        ignore_index=True,
    )
    after = compute_session_vwap_levels(extended, instrument="ES", enabled=True)
    pd.testing.assert_series_equal(
        before[COL_WVWAP].reset_index(drop=True),
        after[COL_WVWAP].iloc[: len(base)].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


def test_wvwap_future_shock_across_week_boundary():
    base = _week_roll_fixture().iloc[:2].reset_index(drop=True)
    before = compute_session_vwap_levels(base, instrument="ES", enabled=True)
    after = compute_session_vwap_levels(_week_roll_fixture(), instrument="ES", enabled=True)
    pd.testing.assert_series_equal(
        before[COL_WVWAP].reset_index(drop=True),
        after[COL_WVWAP].iloc[:2].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


def test_mvwap_future_shock_within_month():
    base = _intra_week_fixture()
    before = compute_session_vwap_levels(base, instrument="ES", enabled=True)
    extended = pd.concat(
        [
            base,
            pd.DataFrame(
                [_rth(pd.Timestamp("2026-06-15 09:30", tz=TZ), 999.0, 1.0, 500.0, 10000.0)]
            ),
        ],
        ignore_index=True,
    )
    after = compute_session_vwap_levels(extended, instrument="ES", enabled=True)
    pd.testing.assert_series_equal(
        before[COL_MVWAP].reset_index(drop=True),
        after[COL_MVWAP].iloc[: len(base)].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


def test_mvwap_future_shock_across_month_boundary():
    base = _month_roll_fixture().iloc[:2].reset_index(drop=True)
    before = compute_session_vwap_levels(base, instrument="ES", enabled=True)
    after = compute_session_vwap_levels(_month_roll_fixture(), instrument="ES", enabled=True)
    pd.testing.assert_series_equal(
        before[COL_MVWAP].reset_index(drop=True),
        after[COL_MVWAP].iloc[:2].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


def test_mid_period_truncation_does_not_rewrite_prefix():
    full = _week_roll_fixture()
    full_out = compute_session_vwap_levels(full, instrument="ES", enabled=True)
    truncated = full.iloc[:3].reset_index(drop=True)
    trunc_out = compute_session_vwap_levels(truncated, instrument="ES", enabled=True)
    pd.testing.assert_series_equal(
        full_out[COL_WVWAP].iloc[:3].reset_index(drop=True),
        trunc_out[COL_WVWAP].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )
    pd.testing.assert_series_equal(
        full_out[COL_MVWAP].iloc[:3].reset_index(drop=True),
        trunc_out[COL_MVWAP].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


# ---------------------------------------------------------------------------
# 11.4 Setup + Study
# ---------------------------------------------------------------------------


def test_available_level_columns_include_wvwap_mvwap():
    df = pd.DataFrame(
        columns=["timestamp", "open", "high", "low", "close", "volume", "wVWAP", "mVWAP"]
    )
    cols = available_level_columns(df)
    assert "wVWAP" in cols
    assert "mVWAP" in cols
    assert "wVWAP" not in NON_LEVEL_OUTPUT_COLUMNS
    assert "mVWAP" not in NON_LEVEL_OUTPUT_COLUMNS


@pytest.mark.parametrize("level", ["wVWAP", "mVWAP"])
def test_validate_setup_config_accepts_htf_vwap_selected_levels(level):
    config = _base_config(selected_levels=[level])
    assert validate_setup_config(config) == []


def test_validate_setup_config_accepts_htf_vwap_anchor_rules():
    config = _anchor_config(
        selected_levels=[],
        anchor_level="wVWAP",
        confluence_rules=[{"level": "mVWAP", "tolerance_ticks": 4.0, "required": True}],
        min_valid_confluences=1,
    )
    assert validate_setup_config(config) == []


def test_suggested_defaults_unchanged_and_still_closed_subset():
    assert "wVWAP" not in SUGGESTED_DEFAULT_LEVELS
    assert "mVWAP" not in SUGGESTED_DEFAULT_LEVELS
    assert set(SUGGESTED_DEFAULT_LEVELS) <= closed_level_token_set(DEFAULT_LEVELS_SETTINGS)


def test_static_study_names_include_htf_vwap():
    assert {"wVWAP", "mVWAP"} <= STUDY_STATIC_LEVEL_NAMES
    assert {"wVWAP", "mVWAP"} <= STATIC_STUDY_LEVEL_NAMES


def test_closed_level_token_set_includes_htf_vwap_when_gate_off():
    tokens_omitted = closed_level_token_set(
        {
            "vwap_windows": [],
            "poc_windows": [],
            "pivots_enabled": False,
            "prev30m_vwap_enabled": False,
        }
    )
    tokens_explicit_off = closed_level_token_set({"session_vwap_enabled": False})
    assert {"wVWAP", "mVWAP"} <= tokens_omitted
    assert {"wVWAP", "mVWAP"} <= tokens_explicit_off


def test_study_spec_accepts_wvwap_core_and_mvwap_partner():
    raw_core = _minimal_study()
    raw_core["study"]["factors"]["core_level"] = ["wVWAP"]
    validated_core = validate_study_spec(normalize_study_spec(raw_core))
    assert validated_core["study"]["factors"]["core_level"] == ["wVWAP"]

    raw_partner = _minimal_study()
    raw_partner["study"]["factors"]["partner_levels"] = [["mVWAP"]]
    validated_partner = validate_study_spec(normalize_study_spec(raw_partner))
    assert validated_partner["study"]["factors"]["partner_levels"] == [["mVWAP"]]

    raw_bad = _minimal_study()
    raw_bad["study"]["factors"]["core_level"] = ["notAVWAP"]
    with pytest.raises(StudySpecError, match="Unknown core_level token"):
        validate_study_spec(normalize_study_spec(raw_bad))


def test_assistant_catalog_session_vwap_slice_is_four():
    catalog = list(SESSION_LEVEL_CATALOG)
    start = catalog.index("dVWAP_RTH")
    assert catalog[start : start + len(SESSION_VWAP_COLUMNS)] == list(SESSION_VWAP_COLUMNS)
    pm_eq = catalog.index("pmEQ")
    assert tuple(catalog[pm_eq + 1 : start]) == PRIOR_PROFILE_LEVEL_NAMES
