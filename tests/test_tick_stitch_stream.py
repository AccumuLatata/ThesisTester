"""TS2 stitch session streamer — plan §5 TS2 / §4.3."""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from thesistester.data import loader as loader_mod
from thesistester.data import tick_stitch
from thesistester.data.quantower_ticks import TickChunk, iter_tick_files
from thesistester.data.tick_stitch import TickStitchError, iter_stitch_sessions
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION
from thesistester.study import execute as execute_mod

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tick_stitch"
FIXTURE_PLAN = FIXTURES / "plan.json"


def _write_ticks(path: Path, rows: list[tuple[str, str, str, str]]) -> int:
    lines = ["Aggressor flag;Price;Volume;Time left;"]
    for aggressor, price, volume, stamp in rows:
        lines.append(f"{aggressor};{price};{volume};{stamp};")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path.stat().st_size


def _segment(
    filename: str,
    size_bytes: int,
    *,
    effective_first: str,
    effective_last: str,
    file_first: str,
    file_last: str,
) -> dict:
    return {
        "filename": filename,
        "size_bytes": size_bytes,
        "effective_first_utc": effective_first,
        "effective_last_utc": effective_last,
        "file_first_utc": file_first,
        "file_last_utc": file_last,
        "mtime": 0,
    }


def test_inclusive_trim_keeps_effective_last_drops_plus_one_us(tmp_path):
    path = tmp_path / "trim.csv"
    size = _write_ticks(
        path,
        [
            ("", "100.0", "1", "2026-01-15 10:00:00.000000"),
            ("", "101.0", "2", "2026-01-15 10:00:01.000000"),
            ("", "102.0", "3", "2026-01-15 10:00:01.000001"),
        ],
    )
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 10:00:00.000000",
            effective_last="2026-01-15 10:00:01.000000",
            file_first="2026-01-15 10:00:00.000000",
            file_last="2026-01-15 10:00:01.000001",
        )
    ]
    chunks = list(iter_stitch_sessions(plan, tmp_path))
    assert len(chunks) == 1
    assert isinstance(chunks[0], TickChunk)
    assert chunks[0].ticks["price"].tolist() == [100.0, 101.0]
    assert chunks[0].ticks["volume"].tolist() == [1.0, 2.0]


def test_handover_boundary_row_is_in_exactly_one_segment(tmp_path):
    path = tmp_path / "handover.csv"
    size = _write_ticks(
        path,
        [
            ("", "10.0", "1", "2026-01-15 10:00:00.000000"),
            ("", "11.0", "1", "2026-01-15 10:00:01.000000"),
            ("", "12.0", "1", "2026-01-15 10:00:01.000001"),
        ],
    )
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 10:00:00.000000",
            effective_last="2026-01-15 10:00:01.000000",
            file_first="2026-01-15 10:00:00.000000",
            file_last="2026-01-15 10:00:01.000001",
        ),
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 10:00:01.000001",
            effective_last="2026-01-15 10:00:01.000001",
            file_first="2026-01-15 10:00:00.000000",
            file_last="2026-01-15 10:00:01.000001",
        ),
    ]
    chunks = list(iter_stitch_sessions(plan, tmp_path))
    prices = [price for chunk in chunks for price in chunk.ticks["price"].tolist()]
    assert prices == [10.0, 11.0, 12.0]


def test_same_ms_pair_and_aggressor_none_kept_nonpositive_volume_dropped(tmp_path):
    path = tmp_path / "prints.csv"
    size = _write_ticks(
        path,
        [
            ("", "100.0", "1", "2026-01-15 10:00:00.000000"),
            ("", "100.0", "4", "2026-01-15 10:00:00.000000"),
            ("", "101.0", "0", "2026-01-15 10:00:00.000001"),
            ("", "102.0", "", "2026-01-15 10:00:00.000002"),
            ("", "103.0", "2", "2026-01-15 10:00:00.000003"),
        ],
    )
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 10:00:00.000000",
            effective_last="2026-01-15 10:00:00.000003",
            file_first="2026-01-15 10:00:00.000000",
            file_last="2026-01-15 10:00:00.000003",
        )
    ]
    chunks = list(iter_stitch_sessions(plan, tmp_path))
    assert chunks[0].ticks["price"].tolist() == [100.0, 100.0, 103.0]
    assert chunks[0].ticks["volume"].tolist() == [1.0, 4.0, 2.0]


def test_consecutive_same_file_windows_are_one_chunked_read(tmp_path, monkeypatch):
    path = tmp_path / "mega.csv"
    size = _write_ticks(
        path,
        [
            ("", "1.0", "1", "2026-01-15 15:00:00.000000"),
            ("", "2.0", "1", "2026-01-15 15:00:01.000000"),
            ("", "9.0", "1", "2026-01-15 16:00:00.000000"),
            ("", "10.0", "1", "2026-01-15 16:00:01.000000"),
        ],
    )
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 15:00:00.000000",
            effective_last="2026-01-15 15:00:01.000000",
            file_first="2026-01-15 15:00:00.000000",
            file_last="2026-01-15 16:00:01.000000",
        ),
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 16:00:00.000000",
            effective_last="2026-01-15 16:00:01.000000",
            file_first="2026-01-15 15:00:00.000000",
            file_last="2026-01-15 16:00:01.000000",
        ),
    ]
    chunked_reads: list[Path] = []
    real_read_csv = pd.read_csv

    def wrapped(*args, **kwargs):
        if kwargs.get("chunksize") is not None:
            chunked_reads.append(Path(args[0]).name)
        return real_read_csv(*args, **kwargs)

    monkeypatch.setattr(tick_stitch.pd, "read_csv", wrapped)
    chunks = list(iter_stitch_sessions(plan, tmp_path))
    assert chunked_reads == [path.name]
    assert chunks[0].ticks["price"].tolist() == [1.0, 2.0, 9.0, 10.0]


def test_intervening_fill_yields_in_plan_order_not_mega_first(tmp_path, monkeypatch):
    mega = tmp_path / "mega.csv"
    fill = tmp_path / "fill.csv"
    mega_size = _write_ticks(
        mega,
        [
            ("", "1.0", "1", "2026-01-15 15:00:00.000000"),
            ("", "2.0", "1", "2026-01-15 15:00:01.000000"),
            ("", "9.0", "1", "2026-01-15 16:00:00.000000"),
            ("", "10.0", "1", "2026-01-15 16:00:01.000000"),
        ],
    )
    fill_size = _write_ticks(fill, [("", "5.0", "1", "2026-01-15 15:30:00.000000")])
    plan = [
        _segment(
            mega.name,
            mega_size,
            effective_first="2026-01-15 15:00:00.000000",
            effective_last="2026-01-15 15:00:01.000000",
            file_first="2026-01-15 15:00:00.000000",
            file_last="2026-01-15 16:00:01.000000",
        ),
        _segment(
            fill.name,
            fill_size,
            effective_first="2026-01-15 15:30:00.000000",
            effective_last="2026-01-15 15:30:00.000000",
            file_first="2026-01-15 15:30:00.000000",
            file_last="2026-01-15 15:30:00.000000",
        ),
        _segment(
            mega.name,
            mega_size,
            effective_first="2026-01-15 16:00:00.000000",
            effective_last="2026-01-15 16:00:01.000000",
            file_first="2026-01-15 15:00:00.000000",
            file_last="2026-01-15 16:00:01.000000",
        ),
    ]
    chunked_reads: list[str] = []
    real_read_csv = pd.read_csv

    def wrapped(*args, **kwargs):
        if kwargs.get("chunksize") is not None:
            chunked_reads.append(Path(args[0]).name)
        return real_read_csv(*args, **kwargs)

    monkeypatch.setattr(tick_stitch.pd, "read_csv", wrapped)
    chunks = list(iter_stitch_sessions(plan, tmp_path))
    assert chunked_reads == [mega.name, fill.name, mega.name]
    assert chunks[0].ticks["price"].tolist() == [1.0, 2.0, 5.0, 9.0, 10.0]


def test_session_date_summer_dst_uses_eth_start_not_hardcoded_utc(tmp_path):
    """Winter 23:00 UTC is 18:00 ET; summer session cut is 22:00 UTC."""
    path = tmp_path / "summer.csv"
    size = _write_ticks(
        path,
        [
            ("", "10.0", "1", "2026-07-15 21:59:00.000"),
            ("", "11.0", "2", "2026-07-15 22:00:00.000"),
        ],
    )
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-07-15 21:59:00.000",
            effective_last="2026-07-15 22:00:00.000",
            file_first="2026-07-15 21:59:00.000",
            file_last="2026-07-15 22:00:00.000",
        )
    ]
    chunks = list(iter_stitch_sessions(plan, tmp_path))
    assert [chunk.session_date for chunk in chunks] == [date(2026, 7, 15), date(2026, 7, 16)]


def test_session_date_uses_trading_session_date_not_utc_midnight(tmp_path):
    path = tmp_path / "winter.csv"
    size = _write_ticks(
        path,
        [
            ("", "10.0", "1", "2026-01-15 22:59:00.000"),
            ("", "11.0", "2", "2026-01-15 23:00:00.000"),
        ],
    )
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 22:59:00.000",
            effective_last="2026-01-15 23:00:00.000",
            file_first="2026-01-15 22:59:00.000",
            file_last="2026-01-15 23:00:00.000",
        )
    ]
    chunks = list(iter_stitch_sessions(plan, tmp_path))
    assert [chunk.session_date for chunk in chunks] == [date(2026, 1, 15), date(2026, 1, 16)]
    assert chunks[0].ticks["timestamp"].iloc[0].isoformat() == "2026-01-15T22:59:00+00:00"
    assert chunks[1].ticks["timestamp"].iloc[0].isoformat() == "2026-01-15T23:00:00+00:00"


def test_streamer_does_not_call_hash_or_peek(tmp_path, monkeypatch):
    path = tmp_path / "ok.csv"
    size = _write_ticks(path, [("", "1.0", "1", "2026-01-15 10:00:00.000")])
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 10:00:00.000",
            effective_last="2026-01-15 10:00:00.000",
            file_first="2026-01-15 10:00:00.000",
            file_last="2026-01-15 10:00:00.000",
        )
    ]

    def boom(*_args, **_kwargs):
        raise AssertionError("hash/peek/identity must not run on the stitch yield path")

    monkeypatch.setattr("thesistester.data.quantower_ticks._file_sha256", boom)
    monkeypatch.setattr("thesistester.data.quantower_ticks._peek_tick_file", boom)
    monkeypatch.setattr("thesistester.levels.tick_vap.compute_tick_source_id", boom)
    monkeypatch.setattr("thesistester.levels.apoc_tick.attach_apoc_identity", boom)
    monkeypatch.setattr("thesistester.levels.rolling_poc_tick.attach_rolling_poc_identity", boom)
    list(iter_stitch_sessions(plan, tmp_path))
    import_block = (
        inspect.getsource(tick_stitch)
        .split("from thesistester.data.quantower_ticks import", 1)[1]
        .split(")", 1)[0]
    )
    assert "_file_sha256" not in import_block
    assert "_peek_tick_file" not in import_block
    assert "compute_tick_source_id" not in import_block


def test_iter_tick_files_is_not_replaced_and_engine_version_stays_11(tmp_path):
    path = tmp_path / "ok.csv"
    size = _write_ticks(path, [("", "1.0", "1", "2026-01-15 10:00:00.000")])
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 10:00:00.000",
            effective_last="2026-01-15 10:00:00.000",
            file_first="2026-01-15 10:00:00.000",
            file_last="2026-01-15 10:00:00.000",
        )
    ]
    stitched = list(iter_stitch_sessions(plan, tmp_path))
    legacy = list(iter_tick_files(path))
    assert stitched[0].ticks["price"].tolist() == legacy[0].ticks["price"].tolist()
    assert LEVEL_ENGINE_VERSION == 11
    assert "iter_stitch_sessions" not in inspect.getsource(execute_mod)
    assert "iter_stitch_sessions" not in inspect.getsource(loader_mod)


def test_missing_file_fails_closed(tmp_path):
    plan = [
        _segment(
            "missing.csv",
            1,
            effective_first="2026-01-15 10:00:00.000",
            effective_last="2026-01-15 10:00:00.000",
            file_first="2026-01-15 10:00:00.000",
            file_last="2026-01-15 10:00:00.000",
        )
    ]
    with pytest.raises(TickStitchError, match="does not exist"):
        list(iter_stitch_sessions(plan, tmp_path))


def test_missing_later_file_fails_before_any_yield(tmp_path):
    path = tmp_path / "ok.csv"
    size = _write_ticks(
        path,
        [
            ("", "10.0", "1", "2026-01-15 22:59:00.000"),
            ("", "11.0", "1", "2026-01-15 23:00:00.000"),
        ],
    )
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 22:59:00.000",
            effective_last="2026-01-15 23:00:00.000",
            file_first="2026-01-15 22:59:00.000",
            file_last="2026-01-15 23:00:00.000",
        ),
        _segment(
            "missing.csv",
            1,
            effective_first="2026-01-16 10:00:00.000",
            effective_last="2026-01-16 10:00:00.000",
            file_first="2026-01-16 10:00:00.000",
            file_last="2026-01-16 10:00:00.000",
        ),
    ]
    yielded: list[date] = []
    with pytest.raises(TickStitchError, match="does not exist"):
        for chunk in iter_stitch_sessions(plan, tmp_path):
            yielded.append(chunk.session_date)
    assert yielded == []


def test_unparseable_timestamp_is_tick_stitch_error(tmp_path):
    path = tmp_path / "bad.csv"
    size = _write_ticks(
        path,
        [
            ("", "10.0", "1", "2026-01-15 10:00:00.000"),
            ("", "11.0", "1", "NOT_A_TIME"),
        ],
    )
    plan = [
        _segment(
            path.name,
            size,
            effective_first="2026-01-15 10:00:00.000",
            effective_last="2026-01-15 10:00:00.000",
            file_first="2026-01-15 10:00:00.000",
            file_last="2026-01-15 10:00:00.000",
        )
    ]
    with pytest.raises(TickStitchError, match="Unparseable"):
        list(iter_stitch_sessions(plan, tmp_path))


def test_ts1_fixture_plan_streams_in_plan_order():
    chunks = list(iter_stitch_sessions(FIXTURE_PLAN, FIXTURES))
    prices = [price for chunk in chunks for price in chunk.ticks["price"].tolist()]
    assert prices == [100.0, 101.0, 200.0, 201.0, 202.0, 203.0]
