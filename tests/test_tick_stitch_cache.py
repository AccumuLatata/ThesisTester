"""Unit tests for the §4.5 shared parent-table cache."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from thesistester.config import INSTRUMENTS
from thesistester.data.tick_stitch_cache import (
    PRIOR_CACHE_NAME,
    SIDECAR_NAME,
    STITCH_PARENT_CACHE_VERSION,
    file_sha256,
    parent_cache_key,
    store_parent_cache,
    try_load_parent_cache,
)
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION


def _write_plan(tmp_path: Path, filename: str = "ticks.csv") -> Path:
    plan = [
        {
            "filename": filename,
            "size_bytes": 1,
            "effective_first_utc": "2026-01-15 10:00:00.000",
            "effective_last_utc": "2026-01-15 10:00:01.000",
            "file_first_utc": "2026-01-15 10:00:00.000",
            "file_last_utc": "2026-01-15 10:00:01.000",
            "mtime": 0,
        }
    ]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def _key(tmp_path: Path, **overrides) -> str:
    plan = tmp_path / "plan.json"
    bars = tmp_path / "bars.csv"
    if not bars.is_file():
        bars.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    kwargs = {
        "plan_path": plan,
        "root": tmp_path,
        "bars_path": bars,
        "instrument": "MNQ",
        "burst": False,
        "value_area_pct": 0.70,
        "day_bins": 4,
        "week_bins": 8,
        "month_bins": 10,
        "source_timezone": "UTC",
        "format_profile": "canonical",
    }
    kwargs.update(overrides)
    return parent_cache_key(**kwargs)


def test_parent_cache_key_changes_on_burst_bins_and_value_area_pct(tmp_path: Path) -> None:
    (tmp_path / "ticks.csv").write_text("x", encoding="utf-8")
    _write_plan(tmp_path)
    base = _key(tmp_path)
    assert _key(tmp_path, burst=True) != base
    assert _key(tmp_path, day_bins=8) != base
    assert _key(tmp_path, week_bins=4) != base
    assert _key(tmp_path, month_bins=4) != base
    assert _key(tmp_path, value_area_pct=0.68) != base
    assert STITCH_PARENT_CACHE_VERSION == 2
    assert LEVEL_ENGINE_VERSION == 11


def test_parent_cache_key_changes_on_tick_size_and_bars_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ticks.csv").write_text("x", encoding="utf-8")
    _write_plan(tmp_path)
    base = _key(tmp_path)
    inst = INSTRUMENTS["MNQ"]
    monkeypatch.setitem(INSTRUMENTS, "MNQ", replace(inst, tick_size=0.5))
    assert _key(tmp_path) != base
    monkeypatch.undo()
    bars = tmp_path / "bars.csv"
    bars.write_text("timestamp,open,high,low,close,volume\nchanged\n", encoding="utf-8")
    assert _key(tmp_path, bars_path=bars) != base


def test_sidecar_listed_digests_not_blob_and_incomplete_falls_through(tmp_path: Path) -> None:
    ticks = tmp_path / "ticks.csv"
    ticks.write_text("alpha", encoding="utf-8")
    plan = _write_plan(tmp_path)
    digest = file_sha256(ticks)
    sidecar = plan.with_name(SIDECAR_NAME)
    sidecar.write_text(f"{digest}  ticks.csv\n", encoding="utf-8")
    with_sidecar = _key(tmp_path)
    sidecar.write_text(f"# comment\n{digest}  ticks.csv\n", encoding="utf-8")
    assert _key(tmp_path) == with_sidecar

    other = "ab" * 32
    sidecar.write_text(f"{other}  ticks.csv\n", encoding="utf-8")
    assert _key(tmp_path) != with_sidecar

    sidecar.write_text(f"{digest}  not-the-plan-file.csv\n", encoding="utf-8")
    incomplete = _key(tmp_path)
    sidecar.unlink()
    no_sidecar = _key(tmp_path)
    assert incomplete == no_sidecar
    assert incomplete != with_sidecar
    ticks.write_text("beta", encoding="utf-8")
    assert _key(tmp_path) != no_sidecar


def test_store_load_is_copy_not_hardlink_and_dest_cannot_mutate_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THESISTESTER_TICK_STITCH_CACHE_DIR", str(tmp_path / "cache"))
    prior = tmp_path / "prior.parquet"
    apoc = tmp_path / "apoc.parquet"
    prior.write_bytes(b"PRIOR-TABLE")
    apoc.write_bytes(b"APOC-TABLE")
    stored = store_parent_cache(
        "abc123",
        prior_path=prior,
        apoc_path=apoc,
        fields={
            "tick_source_id": "stitch-id",
            "apoc_tick_source_id": "apoc-id",
            "data_quality": {"data_quality.x1_burst_included": False},
        },
    )
    dest = tmp_path / "study_out"
    loaded = try_load_parent_cache("abc123", dest)
    assert loaded is not None
    assert loaded["tick_source_id"] == "stitch-id"
    assert loaded["prior_sha256"] == stored["prior_sha256"]
    dest_prior = dest / PRIOR_CACHE_NAME
    cache_prior = tmp_path / "cache" / "abc123" / PRIOR_CACHE_NAME
    assert dest_prior.stat().st_ino != cache_prior.stat().st_ino
    dest_prior.write_bytes(b"mutated")
    assert cache_prior.read_bytes() == b"PRIOR-TABLE"


def test_corrupt_manifest_or_missing_fields_is_a_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THESISTESTER_TICK_STITCH_CACHE_DIR", str(tmp_path / "cache"))
    prior = tmp_path / "prior.parquet"
    apoc = tmp_path / "apoc.parquet"
    prior.write_bytes(b"PRIOR-TABLE")
    apoc.write_bytes(b"APOC-TABLE")
    store_parent_cache(
        "abc123",
        prior_path=prior,
        apoc_path=apoc,
        fields={
            "tick_source_id": "stitch-id",
            "apoc_tick_source_id": "apoc-id",
            "data_quality": {"data_quality.x1_burst_included": False},
        },
    )
    manifest = tmp_path / "cache" / "abc123" / "manifest.json"
    manifest.write_text("{not-json", encoding="utf-8")
    assert try_load_parent_cache("abc123", tmp_path / "out_bad") is None
    store_parent_cache(
        "abc123",
        prior_path=prior,
        apoc_path=apoc,
        fields={
            "tick_source_id": "stitch-id",
            "apoc_tick_source_id": "apoc-id",
            "data_quality": {"data_quality.x1_burst_included": False},
        },
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload.pop("tick_source_id")
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert try_load_parent_cache("abc123", tmp_path / "out_missing") is None
