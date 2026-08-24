"""TV1 Quantower Tick–Tick–Last loader — plan §10.1."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import inspect

import pandas as pd
import pytest

from thesistester.data.quantower_ticks import (
    TICK_FORMAT_PROFILE,
    TickIngestError,
    iter_tick_files,
    parse_quantower_tick_filename_window,
)
from thesistester.data.loader import DataValidationError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ticks"
MISMATCH_NAME = (
    "MNQ AMP Futures (Rithmic), Tick - Tick - Last, "
    "8_19_2026 100000 PM-8_20_2026 100000 PM_b9bd9777-fixture.csv"
)
NY = "America/New_York"


def _chunks(paths, **kwargs):
    return list(iter_tick_files(paths, **kwargs))


def test_rth_open_stub_utc_1330_is_0930_new_york_membership():
    chunks = _chunks(FIXTURES / "rth_open_stub.csv")
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.format_profile == TICK_FORMAT_PROFILE
    assert chunk.session_date == date(2026, 8, 20)
    assert chunk.ticks["timestamp"].iloc[0].isoformat() == "2026-08-20T13:30:00+00:00"
    local = chunk.ticks["timestamp"].dt.tz_convert(NY)
    assert local.iloc[0].isoformat() == "2026-08-20T09:30:00-04:00"
    assert chunk.ticks["price"].tolist() == [29350.0]
    assert chunk.ticks["volume"].tolist() == [4.0]


def test_two_monthly_files_concatenate_in_first_row_time_order():
    later = FIXTURES / "a_month_later.csv"
    earlier = FIXTURES / "z_month_earlier.csv"
    # Path order is the opposite of first-row time.
    chunks = _chunks([later, earlier])
    assert [chunk.session_date for chunk in chunks] == [date(2026, 8, 2), date(2026, 8, 20)]
    assert chunks[0].ticks["price"].tolist() == [24100.0]
    assert chunks[1].ticks["price"].tolist() == [29350.0]


def test_session_iterator_cuts_at_1800_new_york_not_filename():
    chunks = _chunks(FIXTURES / "session_cut.csv")
    assert [chunk.session_date for chunk in chunks] == [date(2026, 8, 19), date(2026, 8, 20)]
    assert chunks[0].ticks["timestamp"].iloc[0].isoformat() == "2026-08-19T21:59:00+00:00"
    assert chunks[1].ticks["timestamp"].iloc[0].isoformat() == "2026-08-19T22:00:00+00:00"
    assert not chunks[0].filename_window_mismatch
    assert not chunks[1].filename_window_mismatch


def test_filename_window_mismatch_rows_still_load():
    path = FIXTURES / MISMATCH_NAME
    parsed = parse_quantower_tick_filename_window(path.name)
    assert parsed is not None
    assert parsed[0].isoformat() == "2026-08-19T22:00:00+00:00"
    assert parsed[1].isoformat() == "2026-08-20T22:00:00+00:00"

    chunks = _chunks(path)
    assert len(chunks) == 2
    assert all(chunk.filename_window_mismatch for chunk in chunks)
    assert chunks[0].first_row_utc.isoformat() == "2026-08-19T20:00:00+00:00"
    assert chunks[1].last_row_utc.isoformat() == "2026-08-20T20:00:00+00:00"
    mismatch_text = "filename window does not match"
    assert any(mismatch_text in warning for chunk in chunks for warning in chunk.warnings)
    assert chunks[0].session_date == date(2026, 8, 19)
    assert chunks[1].session_date == date(2026, 8, 20)


def test_nonpositive_volume_and_nan_price_are_dropped():
    chunks = _chunks(FIXTURES / "drop_invalid_rows.csv")
    assert len(chunks) == 1
    assert chunks[0].ticks["price"].tolist() == [29350.0, 29360.0]
    assert chunks[0].ticks["volume"].tolist() == [4.0, 5.0]


def test_missing_price_column_raises(tmp_path):
    path = tmp_path / "missing_price.csv"
    path.write_text("Aggressor flag;Volume;Time left;\nBuy;4;2026-08-20 13:30:00.000;\n")
    with pytest.raises(TickIngestError, match="missing required columns: \\['price'\\]"):
        _chunks(path)


def test_missing_time_left_column_raises(tmp_path):
    path = tmp_path / "missing_time.csv"
    path.write_text("Aggressor flag;Price;Volume;\nBuy;29350.0;4;\n")
    with pytest.raises(TickIngestError, match="missing required columns: \\['timestamp'\\]"):
        _chunks(path)


def test_unparseable_timestamp_raises(tmp_path):
    path = tmp_path / "bad_time.csv"
    path.write_text("Aggressor flag;Price;Volume;Time left;\nBuy;29350.0;4;not-a-time;\n")
    with pytest.raises(TickIngestError, match="Unparseable values in tick timestamp column"):
        _chunks(path)


def test_empty_file_raises(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(TickIngestError, match="Tick file is empty"):
        _chunks(path)


def test_exact_duplicate_file_is_rejected(tmp_path):
    src = FIXTURES / "rth_open_stub.csv"
    copy = tmp_path / "rth_open_stub_copy.csv"
    copy.write_text(src.read_text())
    with pytest.raises(TickIngestError, match="Exact duplicate tick file"):
        _chunks([src, copy])


def test_tick_ingest_error_is_data_validation_error():
    assert issubclass(TickIngestError, DataValidationError)


def test_loader_does_not_import_pages_streamlit_or_call_ohlcv_aggregation():
    import thesistester.data.quantower_ticks as module

    source = inspect.getsource(module)
    assert "load_ohlcv" not in source
    assert "_aggregate_capture_rows" not in source
    assert "import streamlit" not in source
    assert "from pages" not in source
    assert "import pages" not in source
