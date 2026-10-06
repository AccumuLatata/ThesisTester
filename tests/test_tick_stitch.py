"""TS1 stitch-plan schema + verify — plan §5 TS1 / §4.2."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from thesistester.data import tick_stitch
from thesistester.data.quantower_ticks import (
    _REQUIRED_TICK_COLUMNS,
    _peek_tick_file,
    parse_quantower_tick_filename_window,
)
from thesistester.data.tick_stitch import (
    TickStitchCensus,
    TickStitchError,
    load_tick_stitch_plan,
    verify_tick_stitch_plan,
)
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tick_stitch"
PLAN_PATH = FIXTURES / "plan.json"
SHARED_NAME = "MNQ Tick - Tick - Last, 1_1_2020 100000 AM-1_2_2020 100000 AM.csv"
FARM_PLAN = REPO / "examples" / "studies" / "program_b_run2" / "tick_stitch_plan.json"
FARM_PLAN_SHA256 = "0954eac3a53b2a3f9a964f5c284043a972ea2242b9468dac5a43c4354d5a8ada"
FARM_CENSUS = TickStitchCensus(
    unique_files=39,
    segments=46,
    unique_bytes=36_415_038_585,
)


def _plan_payload() -> list[dict]:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def test_same_file_two_disjoint_windows_passes_without_census_lock():
    result = verify_tick_stitch_plan(PLAN_PATH, FIXTURES)
    assert len(result.segments) == 3
    assert result.unique_files == 2
    assert result.segments[1].filename == result.segments[2].filename == SHARED_NAME
    assert result.segments[1].effective_last_utc < result.segments[2].effective_first_utc


def test_unique_file_byte_sum_on_fixture():
    result = verify_tick_stitch_plan(PLAN_PATH, FIXTURES)
    expected = (FIXTURES / "early.csv").stat().st_size + (FIXTURES / SHARED_NAME).stat().st_size
    assert result.unique_bytes == expected == 107 + 175
    assert result.unique_files == 2
    assert len(result.segments) == 3


def test_filename_window_is_ignored():
    window = parse_quantower_tick_filename_window(SHARED_NAME)
    assert window is not None
    assert window[0].year == 2020
    result = verify_tick_stitch_plan(PLAN_PATH, FIXTURES)
    assert result.segments[1].file_first_utc.year == 2026
    assert "parse_quantower_tick_filename_window" not in inspect.getsource(tick_stitch)


def test_size_mismatch_fails():
    payload = _plan_payload()
    payload[0]["size_bytes"] = payload[0]["size_bytes"] + 1
    with pytest.raises(TickStitchError, match="size_bytes"):
        verify_tick_stitch_plan(payload, FIXTURES)


def test_first_last_mismatch_fails():
    payload = _plan_payload()
    payload[0]["file_first_utc"] = "2026-01-15 09:59:59.000"
    with pytest.raises(TickStitchError, match="file_first/last"):
        verify_tick_stitch_plan(payload, FIXTURES)


def test_overlap_fails():
    payload = _plan_payload()
    # Keep the window inside the shared file range so the overlap check fires.
    payload[1]["effective_last_utc"] = "2026-01-15 12:00:00.500"
    with pytest.raises(TickStitchError, match="not strictly before"):
        verify_tick_stitch_plan(payload, FIXTURES)


def test_mis_order_fails():
    payload = _plan_payload()
    payload[0], payload[1] = payload[1], payload[0]
    with pytest.raises(TickStitchError, match="not strictly before"):
        verify_tick_stitch_plan(payload, FIXTURES)


def test_census_asserted_only_when_lock_passed():
    result = verify_tick_stitch_plan(PLAN_PATH, FIXTURES)
    matching = TickStitchCensus(
        unique_files=result.unique_files,
        segments=len(result.segments),
        unique_bytes=result.unique_bytes,
    )
    again = verify_tick_stitch_plan(PLAN_PATH, FIXTURES, expected_census=matching)
    assert again.unique_bytes == result.unique_bytes
    with pytest.raises(TickStitchError, match="census mismatch"):
        verify_tick_stitch_plan(PLAN_PATH, FIXTURES, expected_census=FARM_CENSUS)


def test_verify_does_not_call_peek_tick_file(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("_peek_tick_file must not be called on the stitch verify path")

    monkeypatch.setattr("thesistester.data.quantower_ticks._peek_tick_file", boom)
    assert _peek_tick_file is not None
    verify_tick_stitch_plan(PLAN_PATH, FIXTURES)


def test_verify_does_not_call_duplicate_file_guards(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("unique-path / duplicate-file guards must not run on stitch verify")

    monkeypatch.setattr("thesistester.data.quantower_ticks._reject_duplicate_files", boom)
    monkeypatch.setattr("thesistester.data.quantower_ticks._resolve_paths", boom)
    monkeypatch.setattr("thesistester.data.quantower_ticks.iter_tick_files", boom)
    verify_tick_stitch_plan(PLAN_PATH, FIXTURES)


def test_verify_reuses_loader_header_contract():
    source = inspect.getsource(tick_stitch)
    import_block = source.split("from thesistester.data.quantower_ticks import", 1)[1]
    import_block = import_block.split(")", 1)[0]
    assert "_require_tick_columns" in import_block
    assert "_REQUIRED_TICK_COLUMNS" in import_block
    assert tick_stitch._REQUIRED_TICK_COLUMNS is _REQUIRED_TICK_COLUMNS
    assert "_peek_tick_file" not in import_block
    assert "_reject_duplicate_files" not in import_block
    assert "_file_sha256" not in import_block
    assert not hasattr(tick_stitch, "_peek_tick_file")
    assert "36415038585" not in source
    assert "36_415_038_585" not in source


def test_missing_file_fails(tmp_path):
    with pytest.raises(TickStitchError, match="does not exist"):
        verify_tick_stitch_plan(PLAN_PATH, tmp_path)


def test_missing_price_column_fails(tmp_path):
    payload = _plan_payload()
    path = tmp_path / "early.csv"
    path.write_text("Aggressor flag;Volume;Time left;\nBuy;4;2026-01-15 10:00:00.000;\n")
    shared = tmp_path / SHARED_NAME
    shared.write_bytes((FIXTURES / SHARED_NAME).read_bytes())
    payload[0]["size_bytes"] = path.stat().st_size
    payload[0]["file_last_utc"] = "2026-01-15 10:00:00.000"
    payload[0]["effective_last_utc"] = "2026-01-15 10:00:00.000"
    with pytest.raises(TickStitchError, match="missing required columns"):
        verify_tick_stitch_plan(payload, tmp_path)


def test_bom_header_is_accepted(tmp_path):
    payload = _plan_payload()[:1]
    path = tmp_path / "early.csv"
    body = (
        "Aggressor flag;Price;Volume;Time left;\n"
        ";100.0;1;2026-01-15 10:00:00.000;\n"
        ";101.0;1;2026-01-15 10:00:01.000;\n"
    )
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    payload[0]["size_bytes"] = path.stat().st_size
    result = verify_tick_stitch_plan(payload, tmp_path)
    assert result.unique_files == 1


def test_module_verify_cli_succeeds():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "thesistester.data.tick_stitch",
            "verify",
            str(PLAN_PATH),
            str(FIXTURES),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == os.EX_OK
    assert "3 segment" in completed.stdout


def test_module_verify_cli_fails_closed_on_missing_root(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "thesistester.data.tick_stitch",
            "verify",
            str(PLAN_PATH),
            str(tmp_path / "missing"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == os.EX_DATAERR
    assert "not a directory" in completed.stderr


def test_load_plan_and_level_engine_version_unchanged():
    segments = load_tick_stitch_plan(PLAN_PATH)
    assert len(segments) == 3
    assert LEVEL_ENGINE_VERSION == 11


def test_committed_farm_plan_census_schema_order_without_tick_files():
    """Q1: committed 46-segment plan. Schema/census/order only; no verify, no ticks."""
    assert hashlib.sha256(FARM_PLAN.read_bytes()).hexdigest() == FARM_PLAN_SHA256
    segments = load_tick_stitch_plan(FARM_PLAN)
    unique_sizes: dict[str, int] = {}
    for segment in segments:
        assert Path(segment.filename).name == segment.filename
        assert "/" not in segment.filename and "\\" not in segment.filename
        prior = unique_sizes.get(segment.filename)
        if prior is not None:
            assert prior == segment.size_bytes
        unique_sizes[segment.filename] = segment.size_bytes
        assert segment.effective_first_utc <= segment.effective_last_utc
        assert segment.file_first_utc <= segment.file_last_utc
        assert segment.file_first_utc <= segment.effective_first_utc
        assert segment.effective_last_utc <= segment.file_last_utc
    assert len(segments) == FARM_CENSUS.segments
    assert len(unique_sizes) == FARM_CENSUS.unique_files
    assert sum(unique_sizes.values()) == FARM_CENSUS.unique_bytes
    for index in range(len(segments) - 1):
        assert segments[index].effective_last_utc < segments[index + 1].effective_first_utc
