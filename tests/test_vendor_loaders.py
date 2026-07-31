from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from thesistester.config import INSTRUMENTS
from thesistester.data.loader import DataValidationError, load_ohlcv

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "ES_sample_1m.csv"


def test_canonical_profile_is_byte_identical_to_legacy_default():
    legacy = load_ohlcv(SAMPLE)
    explicit = load_ohlcv(SAMPLE, format_profile="canonical")
    pd.testing.assert_frame_equal(legacy, explicit, check_exact=True)


def test_ninjatrader_minute_profile_uses_explicit_semicolon_contract(tmp_path):
    path = tmp_path / "nt.txt"
    path.write_text("20260602 133000;100;101;99;100.5;10\n20260602 133100;100.5;102;100;101.5;20\n")
    bars, raw = load_ohlcv(
        path,
        format_profile="ninjatrader",
        target_tz="America/New_York",
        return_raw=True,
    )
    assert bars["timestamp"].iloc[0].isoformat() == "2026-06-02T09:30:00-04:00"
    assert bars["volume"].tolist() == [10, 20]
    assert len(raw) == 2


def test_sierra_intraday_profile_combines_date_time_and_last(tmp_path):
    path = tmp_path / "sierra.csv"
    path.write_text(
        "Date,Time,Open,High,Low,Last,Volume,NumberOfTrades\n"
        "2026/06/02,09:30:00,100,101,99,100.5,10,4\n"
        "2026/06/02,09:31:00,100.5,102,100,101.5,20,5\n"
    )
    bars = load_ohlcv(
        path,
        format_profile="sierra_intraday",
        source_tz="America/New_York",
        target_tz="America/New_York",
    )
    assert bars["close"].tolist() == [100.5, 101.5]


def test_databento_trades_aggregate_fixed_point_prices_and_preserve_quotes(tmp_path):
    path = tmp_path / "databento.csv"
    path.write_text(
        "ts_event,action,price,size,bid_price,ask_price\n"
        "1780417800000000000,T,100000000000,2,99900000000,100100000000\n"
        "1780417810000000000,T,101000000000,3,100900000000,101100000000\n"
        "1780417860000000000,T,102000000000,4,101900000000,102100000000\n"
        "1780417870000000000,T,99000000000,5,98900000000,99100000000\n"
    )
    bars, raw = load_ohlcv(
        path,
        format_profile="databento_trades",
        target_tz="UTC",
        return_raw=True,
    )
    assert bars[["open", "high", "low", "close", "volume"]].to_dict("records") == [
        {"open": 100.0, "high": 101.0, "low": 100.0, "close": 101.0, "volume": 5},
        {"open": 102.0, "high": 102.0, "low": 99.0, "close": 99.0, "volume": 9},
    ]
    assert {"bid_price", "ask_price"} <= set(raw.columns)


def test_generic_tick_capture_resamples_to_one_minute_and_returns_raw(tmp_path):
    path = tmp_path / "ticks.csv"
    path.write_text(
        "timestamp,price,volume\n"
        "2026-06-02 09:30:01,100,2\n"
        "2026-06-02 09:30:20,101,3\n"
        "2026-06-02 09:31:01,99,4\n"
    )
    bars, raw = load_ohlcv(
        path,
        format_profile="tick_capture",
        source_tz="America/New_York",
        target_tz="America/New_York",
        return_raw=True,
    )
    assert len(raw) == 3
    assert len(bars) == 2
    assert bars.loc[0, ["open", "high", "low", "close", "volume"]].to_dict() == {
        "open": 100,
        "high": 101,
        "low": 100,
        "close": 101,
        "volume": 5,
    }


@pytest.mark.parametrize(
    ("symbol", "point_value"),
    [("MES", 5.0), ("MNQ", 2.0)],
)
def test_micro_futures_presets_match_cme_contract_point_values(symbol, point_value):
    assert INSTRUMENTS[symbol].tick_size == 0.25
    assert INSTRUMENTS[symbol].point_value == point_value


def test_vendor_profile_must_be_explicit(tmp_path):
    path = tmp_path / "nt.txt"
    path.write_text("20260602 133000;100;101;99;100.5;10\n")
    with pytest.raises(DataValidationError, match="Missing required columns"):
        load_ohlcv(path)
