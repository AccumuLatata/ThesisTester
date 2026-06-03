from pathlib import Path

from thesistester.data.loader import load_ohlcv, validate_ohlcv
from thesistester.data.sessions import tag_session

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "ES_sample_1m.csv"


def test_sample_loads_clean():
    df = load_ohlcv(SAMPLE)
    assert len(df) > 0
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert validate_ohlcv(df) == []


def test_timestamps_are_tz_aware_and_sorted():
    df = load_ohlcv(SAMPLE)
    assert df["timestamp"].dt.tz is not None
    assert df["timestamp"].is_monotonic_increasing


def test_session_tagging_rth():
    df = tag_session(load_ohlcv(SAMPLE), "ES")
    assert "session" in df.columns
    # 09:30\u201316:00 ET sample is entirely RTH
    assert set(df["session"].unique()) == {"RTH"}
