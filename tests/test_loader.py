from pathlib import Path

import pandas as pd
import pytest

from thesistester.data.loader import (
    DataValidationError,
    format_interval,
    infer_base_interval,
    load_ohlcv,
    validate_ohlcv,
)
from thesistester.data.resample import resample_ohlcv
from thesistester.data.sessions import tag_session

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "ES_sample_1m.csv"


def test_sample_loads_clean():
    df = load_ohlcv(SAMPLE)
    assert len(df) > 0
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    report = validate_ohlcv(df)
    assert report.is_clean
    assert report.messages() == []
    assert format_interval(report.inferred_interval) == "1min"


def test_timestamps_are_tz_aware_and_sorted():
    df = load_ohlcv(SAMPLE)
    assert df["timestamp"].dt.tz is not None
    assert df["timestamp"].is_monotonic_increasing


def test_load_ohlcv_tz_backward_compatible(tmp_path):
    path = tmp_path / "naive.csv"
    path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2026-06-02 09:30:00,1,2,0.5,1.5,10",
                "2026-06-02 09:31:00,1.5,2.5,1,2,20",
            ]
        )
    )
    df = load_ohlcv(path, tz="America/New_York")
    assert str(df["timestamp"].dt.tz) == "America/New_York"
    assert str(df["timestamp"].iloc[0]) == "2026-06-02 09:30:00-04:00"


def test_naive_source_timezone_converts_to_target_timezone(tmp_path):
    path = tmp_path / "berlin.csv"
    path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2026-06-02 15:30:00,1,2,0.5,1.5,10",
                "2026-06-02 15:31:00,1.5,2.5,1,2,20",
            ]
        )
    )
    df = load_ohlcv(
        path,
        source_tz="Europe/Berlin",
        target_tz="America/New_York",
    )
    assert str(df["timestamp"].dt.tz) == "America/New_York"
    assert str(df["timestamp"].iloc[0]) == "2026-06-02 09:30:00-04:00"


def test_timezone_aware_timestamps_ignore_source_timezone(tmp_path):
    path = tmp_path / "aware.csv"
    path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2026-06-02T13:30:00+00:00,1,2,0.5,1.5,10",
                "2026-06-02T13:31:00+00:00,1.5,2.5,1,2,20",
            ]
        )
    )
    df = load_ohlcv(
        path,
        source_tz="Europe/Berlin",
        target_tz="America/New_York",
    )
    assert str(df["timestamp"].dt.tz) == "America/New_York"
    assert str(df["timestamp"].iloc[0]) == "2026-06-02 09:30:00-04:00"


def test_quantower_headers_load_and_normalize(tmp_path):
    path = tmp_path / "quantower.csv"
    path.write_text(
        "\n".join(
            [
                "Date Time,Open,High,Low,Close,Volume(from bar)",
                "2026-06-02 09:30:00,1,2,0.5,1.5,10",
                "2026-06-02 09:31:00,1.5,2.5,1,2,20",
            ]
        )
    )
    df = load_ohlcv(
        path,
        source_tz="America/New_York",
        target_tz="America/New_York",
    )
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df["volume"].tolist() == [10, 20]
    assert df["timestamp"].dt.tz is not None


def test_duplicate_alias_collision_raises_data_validation_error(tmp_path):
    path = tmp_path / "duplicate_alias.csv"
    path.write_text(
        "\n".join(
            [
                "timestamp,Date Time,open,high,low,close,volume",
                "2026-06-02 09:30:00,2026-06-02 09:30:00,1,2,0.5,1.5,10",
            ]
        )
    )
    with pytest.raises(
        DataValidationError, match="Duplicate columns after alias normalization"
    ):
        load_ohlcv(path, source_tz="America/New_York", target_tz="America/New_York")


def test_infer_interval_from_irregular_series():
    ts = pd.Series(
        pd.to_datetime(
            [
                "2026-06-02 09:30:00-04:00",
                "2026-06-02 09:31:00-04:00",
                "2026-06-02 09:32:00-04:00",
                "2026-06-02 09:37:00-04:00",
            ]
        )
    )
    assert infer_base_interval(ts) == pd.Timedelta(minutes=1)


def test_session_tagging_rth():
    df = tag_session(load_ohlcv(SAMPLE), "ES")
    assert "session" in df.columns
    assert set(df["session"].unique()) == {"RTH"}


def test_resample_ohlcv_correctness():
    timestamps = pd.date_range(
        "2026-06-02 09:30:00", periods=5, freq="1min", tz="America/New_York"
    )
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [10, 11, 12, 13, 14],
            "high": [11, 12, 13, 14, 15],
            "low": [9, 10, 11, 12, 13],
            "close": [10.5, 11.5, 12.5, 13.5, 14.5],
            "volume": [100, 200, 300, 400, 500],
        }
    )
    out = resample_ohlcv(df, "5min")
    assert len(out) == 1
    first = out.iloc[0]
    assert first["open"] == 10
    assert first["high"] == 15
    assert first["low"] == 9
    assert first["close"] == 14.5
    assert first["volume"] == 1500
    assert out["timestamp"].dt.tz is not None


def test_validation_catches_duplicates_and_bad_high_low():
    df = load_ohlcv(SAMPLE)
    bad = pd.concat([df.iloc[[0]], df.iloc[[0]], df.iloc[[1]]], ignore_index=True)
    bad.loc[1, "high"] = bad.loc[1, "low"] - 1
    report = validate_ohlcv(bad)
    codes = {issue.code for issue in report.issues}
    assert "duplicate_timestamps" in codes
    assert "high_below_low" in codes


def test_default_load_behavior_remains_clean_and_new_york():
    df = load_ohlcv(SAMPLE)
    report = validate_ohlcv(df)
    assert df["timestamp"].dt.tz is not None
    assert str(df["timestamp"].dt.tz) == "America/New_York"
    assert report.is_clean
