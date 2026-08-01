from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from thesistester.config import INSTRUMENTS
from thesistester.data.loader import DataValidationError, load_ohlcv
from thesistester.engine.intrabar import prepare_subtimeframe_context

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "ES_sample_1m.csv"
VENDOR_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vendor"


def test_canonical_profile_is_byte_identical_to_legacy_default():
    legacy = load_ohlcv(SAMPLE)
    explicit = load_ohlcv(SAMPLE, format_profile="canonical")
    pd.testing.assert_frame_equal(legacy, explicit, check_exact=True)


def test_ninjatrader_minute_profile_uses_explicit_semicolon_contract():
    path = VENDOR_FIXTURES / "ninjatrader_minute.txt"
    bars, raw = load_ohlcv(
        path,
        format_profile="ninjatrader",
        target_tz="America/New_York",
        return_raw=True,
    )
    assert bars["timestamp"].iloc[0].isoformat() == "2026-06-02T09:30:00-04:00"
    assert bars["volume"].tolist() == [10, 20]
    assert len(raw) == 2


def test_sierra_intraday_profile_combines_date_time_and_last():
    path = VENDOR_FIXTURES / "sierra_intraday.csv"
    bars = load_ohlcv(
        path,
        format_profile="sierra_intraday",
        source_tz="America/New_York",
        target_tz="America/New_York",
    )
    assert bars["close"].tolist() == [100.5, 101.5]


def test_quantower_history_exporter_profile_parses_semicolon_bars_and_reconciles():
    parent = load_ohlcv(
        VENDOR_FIXTURES / "quantower_history_exporter_1m.csv",
        format_profile="quantower_history_exporter",
        source_tz="America/New_York",
        target_tz="America/New_York",
    )
    lower = load_ohlcv(
        VENDOR_FIXTURES / "quantower_history_exporter_15s.csv",
        format_profile="quantower_history_exporter",
        source_tz="America/New_York",
        target_tz="America/New_York",
    )

    assert parent["timestamp"].iloc[0].isoformat() == "2026-06-02T09:30:00-04:00"
    assert parent["volume"].tolist() == [10, 12]
    assert lower["timestamp"].diff().dropna().eq(pd.Timedelta(seconds=15)).all()
    prepare_subtimeframe_context(parent, lower, tick_size=0.25)


def test_quantower_history_exporter_profile_requires_time_left(tmp_path):
    path = tmp_path / "missing_time_left.csv"
    path.write_text("Open;High;Low;Close;Volume\n100;101;99;100;10\n")

    with pytest.raises(DataValidationError, match="missing required columns: \\['timestamp'\\]"):
        load_ohlcv(path, format_profile="quantower_history_exporter")


@pytest.mark.parametrize(
    ("contents", "missing_column"),
    [
        ("Open,High,Low,Last,Volume\n100,101,99,100.5,10\n", "timestamp"),
        (
            "Date,Time,Open,High,Low,Last\n2026/06/02,09:30:00,100,101,99,100.5\n",
            "volume",
        ),
    ],
)
def test_sierra_intraday_profile_rejects_missing_canonical_columns(
    tmp_path, contents, missing_column
):
    path = tmp_path / "incomplete_sierra.csv"
    path.write_text(contents)

    with pytest.raises(
        DataValidationError, match=f"missing required columns: \\['{missing_column}'\\]"
    ):
        load_ohlcv(path, format_profile="sierra_intraday")


def test_databento_trades_aggregate_fixed_point_prices_and_preserve_quotes():
    path = VENDOR_FIXTURES / "databento_trades.csv"
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
    assert raw[["price", "bid_price", "ask_price"]].to_dict("records") == [
        {"price": 100.0, "bid_price": 99.9, "ask_price": 100.1},
        {"price": 101.0, "bid_price": 100.9, "ask_price": 101.1},
        {"price": 102.0, "bid_price": 101.9, "ask_price": 102.1},
        {"price": 99.0, "bid_price": 98.9, "ask_price": 99.1},
    ]


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


@pytest.mark.parametrize(
    ("timestamp", "message"),
    [
        ("2026-03-08 02:30:00", "Nonexistent local timestamps"),
        ("2026-11-01 01:30:00", "Ambiguous local timestamps"),
    ],
)
def test_profile_timestamps_translate_dst_failures_to_data_validation_error(
    tmp_path, timestamp, message
):
    path = tmp_path / "ticks.csv"
    path.write_text(f"timestamp,price,volume\n{timestamp},100,1\n")
    with pytest.raises(DataValidationError, match=message):
        load_ohlcv(
            path,
            format_profile="tick_capture",
            source_tz="America/New_York",
            target_tz="America/New_York",
        )
