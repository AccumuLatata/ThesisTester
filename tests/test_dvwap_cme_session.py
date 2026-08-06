"""CME-session developing VWAP (`dVWAP`) tests.

Covers:
- Exact cumulative VWAP across ETH + RTH bars in one CME session.
- Reset at CME session open (``eth_start`` / ``trading_session_date``).
- ETH bars emit non-NaN (contrast with ``dVWAP_RTH``).
- ``dVWAP_RTH`` values remain unchanged when ``dVWAP`` is also emitted.
- Zero-volume and future-shock / point-in-time guarantees.
- Regression: disabled gate emits neither column.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_session_vwap_levels
from thesistester.levels.session_vwap import COL_DVWAP, COL_DVWAP_RTH


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


def _cme_session_fixture() -> pd.DataFrame:
    """One CME session spanning prior-evening ETH through RTH.

    Session date for ES (eth_start=18:00):
    - 2026-06-01 18:00 ETH → session_date 2026-06-02
    - 2026-06-02 09:30 RTH → session_date 2026-06-02
    """
    rows = [
        _eth(pd.Timestamp("2026-06-01 18:00", tz=TZ), 101.0, 99.0, 100.0, 10.0),
        _eth(pd.Timestamp("2026-06-01 18:01", tz=TZ), 102.0, 100.0, 101.0, 20.0),
        _eth(pd.Timestamp("2026-06-02 08:00", tz=TZ), 103.0, 101.0, 102.0, 30.0),
        _rth(pd.Timestamp("2026-06-02 09:30", tz=TZ), 104.0, 102.0, 103.0, 40.0),
        _rth(pd.Timestamp("2026-06-02 09:31", tz=TZ), 105.0, 103.0, 104.0, 50.0),
    ]
    return pd.DataFrame(rows)


def _expected_cum_vwap(rows: list[dict]) -> list[float]:
    expected: list[float] = []
    cum_pv = 0.0
    cum_v = 0.0
    for row in rows:
        tp = (row["high"] + row["low"] + row["close"]) / 3.0
        cum_pv += tp * row["volume"]
        cum_v += row["volume"]
        expected.append(cum_pv / cum_v)
    return expected


# ---------------------------------------------------------------------------
# Exact values + ETH emission
# ---------------------------------------------------------------------------


def test_dvwap_exact_values_across_eth_and_rth():
    df = _cme_session_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    expected = _expected_cum_vwap(df.to_dict("records"))
    assert result[COL_DVWAP].tolist() == pytest.approx(expected, rel=1e-9)


def test_dvwap_emits_on_eth_bars():
    df = _cme_session_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    eth = df["session"].eq("ETH")
    assert result.loc[eth, COL_DVWAP].notna().all()


def test_dvwap_rth_still_nan_on_eth_when_both_enabled():
    """Regression: adding dVWAP must not change dVWAP_RTH ETH NaN semantics."""
    df = _cme_session_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    eth = df["session"].eq("ETH")
    rth = df["session"].eq("RTH")
    assert result.loc[eth, COL_DVWAP_RTH].isna().all()
    assert result.loc[rth, COL_DVWAP_RTH].notna().all()


def test_dvwap_differs_from_dvwap_rth_on_rth_bars_after_overnight():
    """Full-session VWAP includes overnight volume; RTH VWAP does not."""
    df = _cme_session_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    rth = df["session"].eq("RTH")
    assert not np.allclose(
        result.loc[rth, COL_DVWAP].to_numpy(),
        result.loc[rth, COL_DVWAP_RTH].to_numpy(),
    )


def test_dvwap_rth_values_unchanged_vs_rth_only_math():
    """dVWAP_RTH on RTH bars must equal RTH-only cumulative VWAP (regression)."""
    df = _cme_session_fixture()
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    rth_rows = df[df["session"].eq("RTH")].to_dict("records")
    expected_rth = _expected_cum_vwap(rth_rows)
    assert result.loc[df["session"].eq("RTH"), COL_DVWAP_RTH].tolist() == pytest.approx(
        expected_rth, rel=1e-9
    )


# ---------------------------------------------------------------------------
# Session reset at CME open
# ---------------------------------------------------------------------------


def test_dvwap_resets_at_next_cme_session_open():
    rows = [
        _eth(pd.Timestamp("2026-06-01 18:00", tz=TZ), 101.0, 99.0, 100.0, 10.0),
        _rth(pd.Timestamp("2026-06-02 09:30", tz=TZ), 104.0, 102.0, 103.0, 40.0),
        # Next CME session open
        _eth(pd.Timestamp("2026-06-02 18:00", tz=TZ), 201.0, 199.0, 200.0, 10.0),
        _rth(pd.Timestamp("2026-06-03 09:30", tz=TZ), 204.0, 202.0, 203.0, 40.0),
    ]
    df = pd.DataFrame(rows)
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    v = result[COL_DVWAP]

    # First bar of second session equals its own single-bar VWAP.
    tp_s2 = (201.0 + 199.0 + 200.0) / 3.0
    assert v.iloc[2] == pytest.approx(tp_s2, rel=1e-9)
    # Must not equal the prior session's last cumulative value.
    assert v.iloc[2] != pytest.approx(v.iloc[1], rel=1e-3)


def test_dvwap_prior_session_does_not_contaminate_next():
    rows = [
        _eth(pd.Timestamp("2026-06-01 18:00", tz=TZ), 101.0, 99.0, 100.0, 1000.0),
        _eth(pd.Timestamp("2026-06-02 18:00", tz=TZ), 50.0, 48.0, 49.0, 1.0),
    ]
    df = pd.DataFrame(rows)
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    tp_second = (50.0 + 48.0 + 49.0) / 3.0
    assert result[COL_DVWAP].iloc[1] == pytest.approx(tp_second, rel=1e-9)


# ---------------------------------------------------------------------------
# Zero volume
# ---------------------------------------------------------------------------


def test_dvwap_zero_volume_emits_nan_until_positive():
    rows = [
        _eth(pd.Timestamp("2026-06-01 18:00", tz=TZ), 101.0, 99.0, 100.0, 0.0),
        _eth(pd.Timestamp("2026-06-01 18:01", tz=TZ), 102.0, 100.0, 101.0, 10.0),
    ]
    df = pd.DataFrame(rows)
    result = compute_session_vwap_levels(df, instrument="ES", enabled=True)
    assert np.isnan(result[COL_DVWAP].iloc[0])
    tp = (102.0 + 100.0 + 101.0) / 3.0
    assert result[COL_DVWAP].iloc[1] == pytest.approx(tp, rel=1e-9)


# ---------------------------------------------------------------------------
# Point-in-time / future-shock
# ---------------------------------------------------------------------------


def test_dvwap_future_shock_within_session():
    base = pd.DataFrame(
        [
            _eth(pd.Timestamp("2026-06-01 18:00", tz=TZ), 101.0, 99.0, 100.0, 10.0),
            _eth(pd.Timestamp("2026-06-01 18:01", tz=TZ), 102.0, 100.0, 101.0, 20.0),
        ]
    )
    before = compute_session_vwap_levels(base, instrument="ES", enabled=True)
    extended = pd.concat(
        [
            base,
            pd.DataFrame(
                [_rth(pd.Timestamp("2026-06-02 09:30", tz=TZ), 999.0, 1.0, 500.0, 10000.0)]
            ),
        ],
        ignore_index=True,
    )
    after = compute_session_vwap_levels(extended, instrument="ES", enabled=True)
    pd.testing.assert_series_equal(
        before[COL_DVWAP].reset_index(drop=True),
        after[COL_DVWAP].iloc[: len(base)].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


def test_dvwap_future_shock_across_sessions():
    base = pd.DataFrame(
        [
            _eth(pd.Timestamp("2026-06-01 18:00", tz=TZ), 101.0, 99.0, 100.0, 10.0),
            _rth(pd.Timestamp("2026-06-02 09:30", tz=TZ), 104.0, 102.0, 103.0, 40.0),
        ]
    )
    before = compute_session_vwap_levels(base, instrument="ES", enabled=True)
    extended = pd.concat(
        [
            base,
            pd.DataFrame(
                [
                    _eth(pd.Timestamp("2026-06-02 18:00", tz=TZ), 10.0, 8.0, 9.0, 1000.0),
                    _rth(pd.Timestamp("2026-06-03 09:30", tz=TZ), 10.0, 8.0, 9.0, 1000.0),
                ]
            ),
        ],
        ignore_index=True,
    )
    after = compute_session_vwap_levels(extended, instrument="ES", enabled=True)
    pd.testing.assert_series_equal(
        before[COL_DVWAP].reset_index(drop=True),
        after[COL_DVWAP].iloc[: len(base)].reset_index(drop=True),
        check_names=False,
        rtol=1e-9,
    )


# ---------------------------------------------------------------------------
# Gate / wiring / catalog regression
# ---------------------------------------------------------------------------


def test_disabled_emits_neither_session_vwap_column():
    df = _cme_session_fixture()
    result = compute_session_vwap_levels(df, enabled=False)
    assert list(result.columns) == []


def test_compute_all_levels_emits_dvwap_when_enabled():
    df = tag_session(_cme_session_fixture().drop(columns=["session"]), "ES")
    out = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        session_vwap_enabled=True,
        session_vwap_anchor="RTH",
    )
    assert COL_DVWAP in out.columns
    assert COL_DVWAP_RTH in out.columns
    assert out[COL_DVWAP].notna().all()


def test_existing_columns_unchanged_when_session_vwap_enabled():
    """Additive column only — overlapping baseline columns stay value-identical."""
    df = tag_session(
        pd.DataFrame(
            {
                "timestamp": pd.date_range(
                    "2026-06-02 09:30", periods=10, freq="1min", tz=TZ
                ),
                "open": np.ones(10) * 100,
                "high": np.ones(10) * 101,
                "low": np.ones(10) * 99,
                "close": np.ones(10) * 100,
                "volume": np.ones(10) * 50,
            }
        ),
        "ES",
    )
    out_off = compute_all_levels(
        df, instrument="ES", opening_range_minutes=5, sma_lengths=[2], session_vwap_enabled=False
    )
    out_on = compute_all_levels(
        df,
        instrument="ES",
        opening_range_minutes=5,
        sma_lengths=[2],
        session_vwap_enabled=True,
        session_vwap_anchor="RTH",
    )
    for col in out_off.columns:
        pd.testing.assert_series_equal(
            out_off[col].reset_index(drop=True),
            out_on[col].reset_index(drop=True),
            check_names=False,
        )
    assert COL_DVWAP in out_on.columns
    assert COL_DVWAP_RTH in out_on.columns


def test_nq_instrument_emits_dvwap():
    df = _cme_session_fixture()
    result = compute_session_vwap_levels(df, instrument="NQ", enabled=True)
    assert COL_DVWAP in result.columns
    assert result[COL_DVWAP].notna().all()
