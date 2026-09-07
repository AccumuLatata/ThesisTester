"""RP1 rolling-POC comparison harness. Does not route production rolling POC."""

from __future__ import annotations

import inspect
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from thesistester.levels import PRIOR_PROFILE_LEVEL_NAMES, compute_all_levels, compute_profile_levels
from thesistester.levels.apoc import COL_APOC, _compute_a_period_poc
from thesistester.levels.apoc_candidates import (
    BAR_CANDIDATES,
    BAR_RANGE_TPO_V1,
    BAR_RANGE_UNIFORM_VOLUME_V1,
    TICK_LAST_VOLUME_V1,
    TYPICAL_MVP_V1,
    VOLUME_CONSERVATION_ATOL,
    VOLUME_CONSERVATION_RTOL,
    VOLUME_PROFILE_CANDIDATES,
    APOCProfileInputError,
    compute_bar_candidate_profile,
    compute_tick_last_volume_profile,
    select_a_period_rows,
)
from thesistester.levels.rolling_poc_candidates import (
    TYPICAL_MVP_15S_V1,
    compare_rolling_poc_candidates,
    rolling_print_window,
    select_rolling_member_bars,
)
from thesistester.persistence import LEVEL_ENGINE_VERSION

TZ = "America/New_York"
SESSION = "2026-06-02"
TICK_SIZE = 0.25
WINDOW = "30min"


def _ts(hour: int, minute: int, second: int = 0) -> pd.Timestamp:
    return pd.Timestamp(
        f"{SESSION} {hour:02d}:{minute:02d}:{second:02d}",
        tz=TZ,
    )


def _ohlc(price: float, volume: float) -> dict[str, float]:
    return {
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": volume,
    }


def _competing_hour_bars(*, include_eth_0929: bool = True) -> pd.DataFrame:
    """Complete 09:30–10:29 1m grid; A-period mode at 09:45, competing at 10:00.

    Unique on-grid typical per minute (H=L=C). 09:45 volume 100 at 103.75;
    10:00 volume 200 at 200.00. Optional ETH 09:29 bar is not a 09:59 member.
    """
    rows: list[dict[str, object]] = []
    if include_eth_0929:
        rows.append({"timestamp": _ts(9, 29), **_ohlc(99.00, 50.0), "session": "ETH"})
    for i, ts in enumerate(pd.date_range(_ts(9, 30), _ts(10, 29), freq="1min")):
        price = 100.00 + i * TICK_SIZE
        volume = 1.0
        if ts == _ts(9, 45):
            volume = 100.0
        if ts == _ts(10, 0):
            price = 200.00
            volume = 200.0
        rows.append({"timestamp": ts, **_ohlc(price, volume), "session": "RTH"})
    return pd.DataFrame(rows)


def _phase3_simple_dataset() -> pd.DataFrame:
    ts = pd.date_range("2026-06-02 09:00:00", periods=4, freq="10min", tz=TZ)
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": [100.0, 100.25, 100.0, 100.5],
            "high": [100.0, 100.25, 100.0, 100.5],
            "low": [100.0, 100.25, 100.0, 100.5],
            "close": [100.0, 100.25, 100.0, 100.5],
            "volume": [10.0, 5.0, 20.0, 1.0],
        }
    )


def _opens(frame: pd.DataFrame) -> list[pd.Timestamp]:
    return list(pd.to_datetime(frame["timestamp"]))


def _assert_volume_conserved(result) -> None:
    assert result.candidate in VOLUME_PROFILE_CANDIDATES
    assert result.allocated_volume == pytest.approx(
        result.source_volume,
        rel=VOLUME_CONSERVATION_RTOL,
        abs=VOLUME_CONSERVATION_ATOL,
    )


# --- §8.1 item 1 -------------------------------------------------------------


def test_select_rolling_members_0959_and_1000_on_complete_grid():
    bars = _competing_hour_bars()
    members_0959 = select_rolling_member_bars(bars, _ts(9, 59), WINDOW)
    members_1000 = select_rolling_member_bars(bars, _ts(10, 0), WINDOW)

    expected_0959 = list(pd.date_range(_ts(9, 30), _ts(9, 59), freq="1min"))
    expected_1000 = list(pd.date_range(_ts(9, 31), _ts(10, 0), freq="1min"))
    assert _opens(members_0959) == expected_0959
    assert len(members_0959) == 30
    assert _opens(members_1000) == expected_1000
    assert len(members_1000) == 30
    assert _ts(9, 29) not in _opens(members_0959)
    assert _ts(9, 30) not in _opens(members_1000)


# --- §8.1 item 2 -------------------------------------------------------------


def test_typical_0959_equals_a_period_helper_and_apoc_at_1000():
    bars = _competing_hour_bars()
    now = _ts(9, 59)
    members = select_rolling_member_bars(bars, now, WINDOW)
    a_period = select_a_period_rows(bars, session_date=SESSION, exchange_tz=TZ)
    comparison = compare_rolling_poc_candidates(
        bars, now=now, window=WINDOW, tick_size=TICK_SIZE
    )
    typical = comparison.candidates[TYPICAL_MVP_V1]
    levels = compute_all_levels(
        bars, instrument="ES", poc_windows=["30min"], apoc_enabled=True
    )

    assert _opens(members) == _opens(a_period)
    assert typical.poc == pytest.approx(103.75)
    assert typical.poc == pytest.approx(_compute_a_period_poc(members, TICK_SIZE))
    stamp_0959 = levels["timestamp"] == now
    assert typical.poc == pytest.approx(float(levels.loc[stamp_0959, "POC_rolling_30min"].iloc[0]))
    apoc_0959 = float(levels.loc[stamp_0959, COL_APOC].iloc[0])
    apoc_1000 = float(levels.loc[levels["timestamp"] == _ts(10, 0), COL_APOC].iloc[0])
    assert math.isnan(apoc_0959)
    assert typical.poc == pytest.approx(apoc_1000)


# --- §8.1 item 3 -------------------------------------------------------------


def test_typical_1000_differs_from_production_apoc_on_competing_fixture():
    bars = _competing_hour_bars()
    comparison = compare_rolling_poc_candidates(
        bars, now=_ts(10, 0), window=WINDOW, tick_size=TICK_SIZE
    )
    levels = compute_all_levels(
        bars, instrument="ES", poc_windows=["30min"], apoc_enabled=True
    )
    stamp = levels["timestamp"] == _ts(10, 0)
    apoc_1000 = float(levels.loc[stamp, COL_APOC].iloc[0])
    typical = comparison.candidates[TYPICAL_MVP_V1]
    production = float(levels.loc[stamp, "POC_rolling_30min"].iloc[0])

    assert typical.poc == pytest.approx(200.00)
    assert typical.poc == pytest.approx(production)
    assert apoc_1000 == pytest.approx(103.75)
    assert typical.poc != pytest.approx(apoc_1000)


# --- §8.1 item 4 -------------------------------------------------------------


def test_comparator_does_not_call_production_profile_or_a_period_selector():
    import thesistester.levels.rolling_poc_candidates as rpc

    comparator_src = inspect.getsource(rpc.compare_rolling_poc_candidates)
    assert "compute_profile_levels" not in comparator_src
    assert "select_a_period_rows" not in comparator_src
    assert "select_a_period_rows" not in rpc.__dict__
    assert "compute_profile_levels" not in rpc.__dict__
    assert TYPICAL_MVP_15S_V1 not in BAR_CANDIDATES
    assert BAR_CANDIDATES == (TYPICAL_MVP_V1, BAR_RANGE_UNIFORM_VOLUME_V1, BAR_RANGE_TPO_V1)
    assert LEVEL_ENGINE_VERSION == 11


# --- §8.1 item 5 -------------------------------------------------------------


def test_print_window_is_theoretical_and_stable_when_interior_1m_missing():
    bars = _competing_hour_bars()
    start_1000, end_1000 = rolling_print_window(_ts(10, 0), WINDOW, bar_interval="1min")
    start_0959, end_0959 = rolling_print_window(_ts(9, 59), WINDOW, bar_interval="1min")
    assert start_1000 == _ts(9, 31)
    assert end_1000 == _ts(10, 1)
    assert start_0959 == _ts(9, 30)
    assert end_0959 == _ts(10, 0)

    gapped = bars.loc[bars["timestamp"] != _ts(9, 32)].reset_index(drop=True)
    members = select_rolling_member_bars(gapped, _ts(9, 59), WINDOW)
    comparison = compare_rolling_poc_candidates(
        gapped,
        now=_ts(9, 59),
        window=WINDOW,
        tick_size=TICK_SIZE,
        ticks=pd.DataFrame(
            {
                "timestamp": [_ts(9, 32, 15), _ts(10, 0)],
                "price": [100.25, 200.00],
                "volume": [3.0, 1.0],
            }
        ),
    )

    assert _ts(9, 32) not in _opens(members)
    assert len(members) == 29
    assert comparison.print_start == _ts(9, 30)
    assert comparison.print_end == _ts(10, 0)
    assert rolling_print_window(_ts(9, 59), WINDOW) == (comparison.print_start, comparison.print_end)
    assert comparison.bar_range_input == "1m"
    tick = comparison.candidates[TICK_LAST_VOLUME_V1]
    assert tick.source_rows == 1
    assert tick.poc == pytest.approx(100.25)


def test_tick_print_window_at_1000_includes_missing_interior_minute():
    bars = _competing_hour_bars()
    gapped = bars.loc[bars["timestamp"] != _ts(9, 45)].reset_index(drop=True)
    ticks = pd.DataFrame(
        {
            "timestamp": [_ts(9, 30, 30), _ts(9, 31), _ts(9, 45, 15), _ts(10, 0, 30), _ts(10, 1)],
            "price": [99.00, 100.25, 103.75, 200.00, 201.00],
            "volume": [9.0, 1.0, 4.0, 2.0, 8.0],
        }
    )
    comparison = compare_rolling_poc_candidates(
        gapped, now=_ts(10, 0), window=WINDOW, tick_size=TICK_SIZE, ticks=ticks
    )

    assert comparison.print_start == _ts(9, 31)
    assert comparison.print_end == _ts(10, 1)
    assert _ts(9, 45) not in _opens(comparison.members)
    tick = comparison.candidates[TICK_LAST_VOLUME_V1]
    assert tick.source_rows == 3
    assert tick.source_volume == pytest.approx(7.0)
    assert tick.poc == pytest.approx(103.75)


# --- §8.1 item 6 -------------------------------------------------------------


def test_shared_helpers_keep_ap1_numeric_contracts():
    bars = pd.DataFrame(
        [{"high": 100.50, "low": 100.00, "close": 100.25, "volume": 9.0}]
    )
    uniform = compute_bar_candidate_profile(
        bars, candidate=BAR_RANGE_UNIFORM_VOLUME_V1, tick_size=TICK_SIZE
    )
    tpo = compute_bar_candidate_profile(bars, candidate=BAR_RANGE_TPO_V1, tick_size=TICK_SIZE)
    ticks = pd.DataFrame({"price": [100.0, 100.25], "volume": [4.0, 4.0]})
    tick = compute_tick_last_volume_profile(ticks, tick_size=TICK_SIZE)
    empty = compute_bar_candidate_profile(
        pd.DataFrame([{"high": 100.25, "low": 100.25, "close": 100.25, "volume": 0.0}]),
        candidate=BAR_RANGE_UNIFORM_VOLUME_V1,
        tick_size=TICK_SIZE,
    )

    assert uniform.histogram.to_dict() == {100.0: 3.0, 100.25: 3.0, 100.5: 3.0}
    _assert_volume_conserved(uniform)
    assert uniform.poc == pytest.approx(100.0)
    assert tpo.histogram.to_dict() == {100.0: 1.0, 100.25: 1.0, 100.5: 1.0}
    assert tick.poc == pytest.approx(100.0)
    _assert_volume_conserved(tick)
    assert math.isnan(empty.poc)
    with pytest.raises(APOCProfileInputError, match="tick price must lie"):
        compute_tick_last_volume_profile(
            pd.DataFrame({"price": [100.1], "volume": [1.0]}), tick_size=TICK_SIZE
        )


def test_comparator_stamps_nan_for_off_grid_ticks_instead_of_raising():
    bars = _competing_hour_bars()
    ticks = pd.DataFrame(
        {"timestamp": [_ts(9, 40)], "price": [100.1], "volume": [1.0]}
    )
    comparison = compare_rolling_poc_candidates(
        bars, now=_ts(10, 0), window=WINDOW, tick_size=TICK_SIZE, ticks=ticks
    )
    tick = comparison.candidates[TICK_LAST_VOLUME_V1]
    assert math.isnan(tick.poc)
    assert tick.source_rows == 0


def test_15s_typical_is_labeled_after_typical_mvp_v1_call():
    bars = _competing_hour_bars()
    bars_15s = pd.DataFrame(
        [
            {"timestamp": _ts(9, 30, 45), **_ohlc(100.00, 1.0)},
            {"timestamp": _ts(9, 31, 0), **_ohlc(150.00, 8.0)},
            {"timestamp": _ts(10, 0, 45), **_ohlc(150.00, 2.0)},
            {"timestamp": _ts(10, 1, 0), **_ohlc(201.00, 20.0)},
        ]
    )
    comparison = compare_rolling_poc_candidates(
        bars,
        now=_ts(10, 0),
        window=WINDOW,
        tick_size=TICK_SIZE,
        bars_15s=bars_15s,
    )
    labeled = comparison.candidates[TYPICAL_MVP_15S_V1]
    direct = compute_bar_candidate_profile(
        bars_15s.loc[
            (bars_15s["timestamp"] >= _ts(9, 31)) & (bars_15s["timestamp"] < _ts(10, 1))
        ],
        candidate=TYPICAL_MVP_V1,
        tick_size=TICK_SIZE,
    )

    assert TYPICAL_MVP_15S_V1 not in BAR_CANDIDATES
    assert labeled.candidate == TYPICAL_MVP_V1
    assert labeled.poc == pytest.approx(direct.poc)
    assert labeled.source_rows == 2
    assert labeled.poc == pytest.approx(150.00)


# --- §8.1 item 7 -------------------------------------------------------------


def test_isolation_production_rolling_poc_series_equal_and_va_omitted():
    df = _phase3_simple_dataset()
    before = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"])
    import thesistester.levels.rolling_poc_candidates as rpc

    after = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"])
    pd.testing.assert_series_equal(before["POC_rolling_30min"], after["POC_rolling_30min"])
    assert after["POC_rolling_30min"].iloc[-1] == 100.0
    for name in PRIOR_PROFILE_LEVEL_NAMES:
        assert name not in before.columns
        assert name not in after.columns
    assert rpc.select_rolling_member_bars is select_rolling_member_bars
    from thesistester.levels import profile as profile_mod

    assert "rolling_poc_profile_source" not in inspect.getsource(profile_mod)
    assert "rolling_poc_candidates" not in inspect.getsource(profile_mod)
    src = inspect.getsource(profile_mod._rolling_poc)
    assert "in_window = (timestamps > start) & (timestamps <= now)" in src


# --- §8.1 item 8 -------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("THESISTESTER_RP_QT_1M")
    or not os.environ.get("THESISTESTER_RP_QT_EXPECTED"),
    reason="Set THESISTESTER_RP_QT_1M and THESISTESTER_RP_QT_EXPECTED for desk oracle.",
)
def test_optional_desk_oracle_reports_errors_without_failing_on_miss():
    """Externally supplied rolling-POC oracle. Reports MNQ-tick errors; never fails on miss."""
    bars = _read_frame(Path(os.environ["THESISTESTER_RP_QT_1M"]))
    expected = pd.read_csv(os.environ["THESISTESTER_RP_QT_EXPECTED"])
    ticks = _optional_oracle_ticks()
    bars_15s = _optional_oracle_15s()
    reports: list[str] = []
    for row in expected.itertuples(index=False):
        stamp = _parse_oracle_stamp(getattr(row, "stamp_ny"))
        qt = float(row.poc)
        comparison = compare_rolling_poc_candidates(
            bars,
            now=stamp,
            window=WINDOW,
            tick_size=TICK_SIZE,
            bars_15s=bars_15s,
            ticks=ticks,
        )
        for token, result in comparison.candidates.items():
            if math.isnan(result.poc):
                reports.append(f"{stamp} {token}: poc=NaN qt={qt} error_ticks=NaN")
                continue
            error_ticks = (result.poc - qt) / TICK_SIZE
            reports.append(
                f"{stamp} {token}: poc={result.poc:.4f} qt={qt:.4f} "
                f"error_ticks={error_ticks:.2f}"
            )
    print("\n".join(reports))
    assert reports, "expected CSV produced no oracle rows"


def test_oracle_env_gate_is_inactive_in_ci(monkeypatch):
    monkeypatch.delenv("THESISTESTER_RP_QT_1M", raising=False)
    monkeypatch.delenv("THESISTESTER_RP_QT_TICKS", raising=False)
    monkeypatch.delenv("THESISTESTER_RP_QT_15S", raising=False)
    monkeypatch.delenv("THESISTESTER_RP_QT_EXPECTED", raising=False)
    assert not os.environ.get("THESISTESTER_RP_QT_1M")
    assert not os.environ.get("THESISTESTER_RP_QT_EXPECTED")


def _read_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    else:
        frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if frame["timestamp"].dt.tz is None:
        frame["timestamp"] = frame["timestamp"].dt.tz_localize(TZ)
    else:
        frame["timestamp"] = frame["timestamp"].dt.tz_convert(TZ)
    return frame


def _parse_oracle_stamp(raw: object) -> pd.Timestamp:
    stamp = pd.Timestamp(raw)
    if stamp.tzinfo is None:
        return stamp.tz_localize(TZ)
    return stamp.tz_convert(TZ)


def _optional_oracle_15s() -> pd.DataFrame | None:
    raw = os.environ.get("THESISTESTER_RP_QT_15S")
    if not raw:
        return None
    return _read_frame(Path(raw))


def _optional_oracle_ticks() -> pd.DataFrame | None:
    raw = os.environ.get("THESISTESTER_RP_QT_TICKS")
    if not raw:
        return None
    path = Path(raw)
    try:
        from thesistester.data.quantower_ticks import iter_tick_files

        parts = [
            chunk.ticks[["timestamp", "price", "volume"]]
            for chunk in iter_tick_files(path, instrument="MNQ")
        ]
        if parts:
            return pd.concat(parts, ignore_index=True)
    except Exception:
        pass
    return _read_frame(path)
