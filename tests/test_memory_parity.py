"""MW0 tooling: hook audit, compare gates, §8.1 rules, synthetic golden."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.memory_parity.bits import (
    DA5_KEYS,
    float64_hex,
    hex_to_float64,
    replica_hex_list,
)
from tests.fixtures.memory_parity.cells import (
    CI_CELL6_SHAPE,
    CI_PREPARE_REPLICA,
    FULL_CELL,
    FULL_CELL_KNOWN_TRADE_COUNT,
    SHORT_CELLS,
    parse_cell_selector,
)
from tests.fixtures.memory_parity.compat import HOOK_POINTS, resolve_all_hooks
from tests.fixtures.memory_parity.canonical import (
    CANONICAL_DATETIME_UNIT,
    CanonicalizeError,
    canonicalize_datetime_series,
    canonicalize_frame_datetimes,
    portable_canonical_bundle_hash,
    portable_dtype_label,
    portable_hash_dataframe,
)
from tests.fixtures.memory_parity.compat import (
    CompatError,
    assert_imported_thesistester_follows_pythonpath,
    prefer_pythonpath_thesistester,
    pythonpath_thesistester_roots,
)
from tests.fixtures.memory_parity.compare import compare_captures, compare_trades, format_report
from tests.fixtures.memory_parity.generate_synthetic import (
    default_synthetic_path,
    write_synthetic_csv,
)
from tests.fixtures.memory_parity.gitref import (
    GitRefError,
    diff_vs_main,
    show_at_farm,
)
from tests.fixtures.memory_parity.io import (
    DA5_NAME,
    DTYPES_NAME,
    HASH_NAME,
    LEDGER_NAME,
    META_NAME,
    REPLICA_NAME,
    SUMMARY_NAME,
    TRADES_NAME,
    cell_dir,
    describe_series_dtype,
    list_cell_ids,
    load_capture,
    write_capture,
)
from tests.fixtures.memory_parity.slice_csv import (
    SHORT_WINDOW_END_UTC,
    SHORT_WINDOW_START_UTC,
    parse_quantower_time_left_utc,
    slice_quantower_csv_utc,
)
from tests.fixtures.memory_parity.stage_trace import compute_b, evaluate_rule_8_1

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "memory_parity"
GOLDEN = FIXTURE / "synthetic_golden"
FARM_REF = FIXTURE / "farm_reference"
FARM_FULL = FARM_REF / "full"
FARM_SHORT = FARM_REF / "short"

# §9.1 files every official cell must have. Missing sidecar (e.g. dtypes)
# is a gate failure even though load_capture treats some as optional.
FARM_REQUIRED_CELL_FILES: tuple[str, ...] = (
    TRADES_NAME,
    DTYPES_NAME,
    REPLICA_NAME,
    SUMMARY_NAME,
    DA5_NAME,
    LEDGER_NAME,
    HASH_NAME,
    META_NAME,
)

# Documented farm results (README / §9). Not derived from the files at
# compare time — compare_captures(dir, dir) is tautological.
FARM_FULL_EXPECTANCY_HEX = "3fb49c34115b1e60"
FARM_FULL_EXPECTANCY = 0.0805084745762712
FARM_FULL_PORTABLE_HASH = "b8ff79824c686b1ad16010ff9fbd682d005cd0275b3fc3b16bc3c30e24ec5be7"
FARM_SHORT_TRADE_COUNTS: dict[str, int] = {
    "cell_01_fade_onh_sma50_5min": 17,
    "cell_02_touch_pdhigh_ema9_1min": 75,
    "cell_03_break_orhigh_rvwap30": 21,
    "cell_04_continuation_london_pivot5m": 16,
    "cell_05_3c_onl_ema21_1min": 14,
    "cell_06_fade_onh_sma200_30min_zero": 0,
}

# GNU sha256sum lockfile (paths relative to farm_reference/). Outside the
# official capture tree. Pandas-independent. A missing, extra, or altered
# fixture (including parquet / manifest) fails.
FARM_REFERENCE_SHA256_PATH = FIXTURE / "farm_reference.sha256"


def _manifest_cell_ids(root: Path) -> list[str]:
    payload = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    cells = payload.get("cells")
    if not isinstance(cells, list):
        raise AssertionError(f"{root}/manifest.json missing cells list")
    return [str(item) for item in cells]


def _expected_farm_reference_paths() -> set[str]:
    paths = {"full/manifest.json", "short/manifest.json"}
    for name in FARM_REQUIRED_CELL_FILES:
        paths.add(f"full/cells/{FULL_CELL.cell_id}/{name}")
    for spec in SHORT_CELLS:
        for name in FARM_REQUIRED_CELL_FILES:
            paths.add(f"short/cells/{spec.cell_id}/{name}")
    return paths


def _farm_reference_file_sha256s(root: Path) -> dict[str, str]:
    files = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    return dict(sorted(files.items()))


def _load_farm_reference_sha256_lock(path: Path = FARM_REFERENCE_SHA256_PATH) -> dict[str, str]:
    """Parse GNU sha256sum text (``digest  path`` or ``digest *path``)."""
    if not path.is_file():
        raise AssertionError(f"missing farm_reference sha256 lock: {path}")
    mapping: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest, rel = line.split(None, 1)
        if rel.startswith("*"):
            rel = rel[1:]
        mapping[rel] = digest
    if not mapping:
        raise AssertionError(f"empty farm_reference sha256 lock: {path}")
    return mapping


def test_farm_reference_bytes_match_official_pins() -> None:
    """Cheap CI: official farm bytes, manifests, and documented results.

    No CSV. No replay. SHA-256 is pandas-independent (py3.10/3.11/3.12).
    Self-compare is not the gate — it cannot see an altered fixture.
    """
    assert FARM_FULL.is_dir() and FARM_SHORT.is_dir()
    csv_files = list(FARM_REF.rglob("*.csv"))
    assert csv_files == [], csv_files

    expected_paths = _expected_farm_reference_paths()
    pinned = _load_farm_reference_sha256_lock()
    assert set(pinned) == expected_paths
    actual = _farm_reference_file_sha256s(FARM_REF)
    missing = expected_paths - set(actual)
    extra = set(actual) - expected_paths
    assert missing == set(), f"missing farm_reference files: {sorted(missing)}"
    assert extra == set(), f"unexpected farm_reference files: {sorted(extra)}"
    assert actual == pinned

    expected_full = [FULL_CELL.cell_id]
    expected_short = [spec.cell_id for spec in SHORT_CELLS]
    assert expected_short == list(FARM_SHORT_TRADE_COUNTS)
    assert _manifest_cell_ids(FARM_FULL) == expected_full
    assert _manifest_cell_ids(FARM_SHORT) == expected_short
    assert list_cell_ids(FARM_FULL) == expected_full
    assert list_cell_ids(FARM_SHORT) == expected_short

    full = load_capture(cell_dir(FARM_FULL, FULL_CELL.cell_id))
    assert int(full["summary"]["trade_count"]) == FULL_CELL_KNOWN_TRADE_COUNT
    assert len(full["trades"]) == FULL_CELL_KNOWN_TRADE_COUNT
    assert full["summary"]["expectancy_r"]["hex"] == FARM_FULL_EXPECTANCY_HEX
    assert hex_to_float64(FARM_FULL_EXPECTANCY_HEX) == FARM_FULL_EXPECTANCY
    assert full["canonical_bundle_hash"] == FARM_FULL_PORTABLE_HASH
    assert full["replica"]["count"] == 50
    assert full["ledger"]["status"] == "ok"

    for spec in SHORT_CELLS:
        loaded = load_capture(cell_dir(FARM_SHORT, spec.cell_id))
        expected_n = FARM_SHORT_TRADE_COUNTS[spec.cell_id]
        assert int(loaded["summary"]["trade_count"]) == expected_n
        assert len(loaded["trades"]) == expected_n
        assert loaded["cell_id"] == spec.cell_id
        assert loaded["ledger"]["status"] == "ok"
        if expected_n == 0:
            assert loaded["replica"]["count"] == 0
            assert loaded["replica"]["hex_bits"] == []
            assert all(loaded["da5"][key].get("is_null") for key in DA5_KEYS)
        else:
            assert loaded["replica"]["count"] == 50
            assert len(loaded["replica"]["hex_bits"]) == 50
            assert not loaded["da5"]["random_null_expectancy_r"].get("is_null")


def test_farm_reference_sha256_gate_catches_missing_or_altered_file(
    tmp_path: Path,
) -> None:
    """Prove the CI pin is not a self-compare: one flipped byte or drop fails."""
    pinned = _load_farm_reference_sha256_lock()
    clone = tmp_path / "farm_reference"
    shutil.copytree(FARM_REF, clone)
    assert _farm_reference_file_sha256s(clone) == pinned

    target = clone / "short" / "manifest.json"
    target.write_bytes(target.read_bytes() + b"#")
    altered = _farm_reference_file_sha256s(clone)
    assert altered != pinned
    assert altered["short/manifest.json"] != pinned["short/manifest.json"]

    target.unlink()
    dropped = _farm_reference_file_sha256s(clone)
    assert "short/manifest.json" not in dropped
    assert set(dropped) != set(pinned)


def test_hook_points_resolve_on_imported_package() -> None:
    resolved = resolve_all_hooks()
    assert set(resolved) == {f"{module}.{attr}" for module, attr in HOOK_POINTS}


def test_hook_points_exist_at_farm_production_commit() -> None:
    """Every capture/trace hook name exists at 59a4652 (read-only git show)."""
    missing: list[str] = []
    try:
        for module_name, attr in HOOK_POINTS:
            rel = module_name.replace(".", "/") + ".py"
            source = show_at_farm(rel)
            needle = f"def {attr}("
            if needle not in source and f"{attr} =" not in source:
                # Module-level re-export (from x import attr) is also a hit.
                if f"import {attr}" not in source and f" {attr}," not in source:
                    missing.append(f"{rel} {attr}")
    except GitRefError as exc:
        pytest.fail(str(exc))
    assert missing == []


def test_mw1_runtime_surface_is_limited_vs_main() -> None:
    """MW1 may edit only the §10.3 runtime files under thesistester/."""
    try:
        diff = diff_vs_main("thesistester/")
    except GitRefError as exc:
        pytest.fail(str(exc))
    allowed = {
        "thesistester/engine/intrabar.py",
        "thesistester/study/execute.py",
    }
    files: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            right = line.split()[-1]
            files.add(right[2:] if right.startswith("b/") else right)
    unexpected = files - allowed
    assert unexpected == set(), sorted(unexpected)


def test_legacy_golden_readme_not_touched() -> None:
    try:
        diff = diff_vs_main("tests/fixtures/golden/")
    except GitRefError as exc:
        pytest.fail(str(exc))
    assert diff == ""


def test_plan_status_line_records_mw1() -> None:
    text = (REPO / "docs" / "WORKER_MEMORY_IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert "**Status:** **MW1 shipping**" in text
    assert "deviation from §8.1 rule 1" in text
    assert "MW1 first" in text
    assert "farm_reference/" in text


def test_parse_cell_selector_short_and_full() -> None:
    short = parse_cell_selector("short")
    assert [spec.number for spec in short] == [1, 2, 3, 4, 5, 6]
    assert parse_cell_selector("full")[0].cell_id == "full_reference"
    mixed = parse_cell_selector("1,6,full")
    assert [spec.cell_id for spec in mixed] == [
        "cell_01_fade_onh_sma50_5min",
        "cell_06_fade_onh_sma200_30min_zero",
        "full_reference",
    ]


def test_short_cell_policies_match_plan() -> None:
    policies = {spec.number: spec.same_bar_opposite_direction for spec in SHORT_CELLS}
    assert policies[1] == policies[3] == policies[4] == policies[6] == "raise"
    assert policies[2] == policies[5] == "legacy"
    assert SHORT_CELLS[5].expect_zero_trades is True
    cell5 = SHORT_CELLS[4]
    assert cell5.cell_id == "cell_05_3c_onl_ema21_1min"
    assert cell5.partner_level == "EMA_21_1min"
    assert cell5.core_level == "ONL"
    assert cell5.trigger == "3c"
    assert cell5.expect_zero_trades is False


def test_slice_quantower_csv_keeps_utc_bounds(tmp_path: Path) -> None:
    source = tmp_path / "src.csv"
    source.write_text(
        "Time left;Time right;Open;High;Low;Close;Volume;\n"
        "2024-07-31 23:59:45.000;2024-07-31 23:59:59.999;1;1;1;1;1;\n"
        "2024-08-01 00:00:00.000;2024-08-01 00:00:14.999;2;2;2;2;1;\n"
        "2024-09-30 23:59:45.000;2024-09-30 23:59:59.999;3;3;3;3;1;\n"
        "2024-10-01 00:00:00.000;2024-10-01 00:00:14.999;4;4;4;4;1;\n",
        encoding="utf-8",
    )
    dest = tmp_path / "slice.csv"
    stats = slice_quantower_csv_utc(
        source,
        dest,
        start_utc=SHORT_WINDOW_START_UTC,
        end_utc=SHORT_WINDOW_END_UTC,
    )
    assert stats["kept"] == 2
    lines = dest.read_text(encoding="utf-8").splitlines()
    assert lines[1].startswith("2024-08-01 00:00:00.000")
    assert lines[2].startswith("2024-09-30 23:59:45.000")
    assert parse_quantower_time_left_utc("2024-08-01 00:00:00.000") == SHORT_WINDOW_START_UTC


def test_float64_hex_nan_equals_nan() -> None:
    assert float64_hex(np.nan) == float64_hex(float("nan"))
    assert replica_hex_list([0.0805, float("nan")])[1] == float64_hex(np.nan)


def _tiny_trades(*, n: int, extra: float) -> pd.DataFrame:
    stamps = pd.date_range("2024-08-01 14:00:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "trade_id": list(range(1, n + 1)),
            "r_multiple": np.array([0.5 + extra, -0.25][:n], dtype="float64"),
            "exit_subbar_timestamp": stamps,
        }
    )


def _write_tiny_capture(root: Path, cell_id: str, *, extra: float, hash_text: str) -> None:
    trades = _tiny_trades(n=2, extra=extra)
    write_capture(
        cell_dir(root, cell_id),
        cell_id=cell_id,
        trades=trades,
        replica_expectancies=[0.0805, extra],
        summary={
            "trade_count": 2,
            "expectancy_r": 0.0805 + extra,
            "total_r": 0.25,
            "max_drawdown_r": -0.25,
            "profit_factor": 2.0,
            "win_rate": 0.5,
        },
        da5={
            "random_null_expectancy_r": 0.01,
            "random_null_std_r": 0.02,
            "random_p_value_ge": 0.3,
            "expectancy_minus_null_r": 0.07,
        },
        ledger={
            "status": "ok",
            "error": None,
            "bundle_path": f"{cell_id}.research.zip",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T01:00:00+00:00",
        },
        canonical_hash=hash_text,
        meta={"run_label": "unit"},
    )


def test_compare_full_fails_on_trade_and_hash(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write_tiny_capture(left, "full_reference", extra=0.0, hash_text="aaa")
    _write_tiny_capture(right, "full_reference", extra=0.001, hash_text="bbb")
    report = compare_captures(left, right, pre_step=False)
    assert report.ok is False
    fields = {diff.field for diff in report.gate_failures}
    assert "trades" in fields
    assert "canonical_bundle_hash" in fields
    assert "replica_expectancies" in fields


def test_compare_pre_step_reports_hash_but_does_not_gate_it(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write_tiny_capture(left, "full_reference", extra=0.0, hash_text="aaa")
    _write_tiny_capture(right, "full_reference", extra=0.0, hash_text="bbb")
    # Same trades/replicas/E; only hash and wall-clock differ.
    right_ledger = json.loads(
        (cell_dir(right, "full_reference") / "ledger.json").read_text(encoding="utf-8")
    )
    right_ledger["started_at"] = "2099-01-01T00:00:00+00:00"
    (cell_dir(right, "full_reference") / "ledger.json").write_text(
        json.dumps(right_ledger, indent=2) + "\n", encoding="utf-8"
    )
    report = compare_captures(left, right, pre_step=True)
    assert report.ok is True
    info = {diff.field for diff in report.diffs if not diff.gate}
    assert "canonical_bundle_hash" in info
    text = format_report(report)
    assert "pre-step gates" in text
    assert "[INFO] full_reference canonical_bundle_hash" in text


def test_compare_trades_requires_exit_subbar_timestamp_tz() -> None:
    left = _tiny_trades(n=2, extra=0.0)
    right = left.copy()
    right["exit_subbar_timestamp"] = right["exit_subbar_timestamp"].dt.tz_convert(
        "America/New_York"
    )
    diffs = compare_trades(left, right)
    assert any("exit_subbar_timestamp" in item for item in diffs)


def _ny_stamps(*, unit: str) -> pd.Series:
    values = pd.to_datetime(
        ["2024-08-01T14:00:00.123456", "2024-08-01T15:30:00.000000"],
        format="%Y-%m-%dT%H:%M:%S.%f",
    ).tz_localize("America/New_York")
    return pd.Series(values.astype(pd.DatetimeTZDtype(unit=unit, tz="America/New_York")))


def test_compare_trades_normalizes_datetime_unit() -> None:
    left = pd.DataFrame(
        {
            "trade_id": [1, 2],
            "r_multiple": np.array([0.5, -0.25], dtype="float64"),
            "entry_timestamp": _ny_stamps(unit="us"),
        }
    )
    right = left.copy()
    right["entry_timestamp"] = _ny_stamps(unit="ns")
    assert str(left["entry_timestamp"].dtype) != str(right["entry_timestamp"].dtype)
    assert compare_trades(left, right) == []
    canonical = canonicalize_frame_datetimes(left)
    assert describe_series_dtype(canonical["entry_timestamp"])["unit"] == CANONICAL_DATETIME_UNIT


def test_canonicalize_datetime_rejects_precision_loss() -> None:
    series = pd.Series(pd.to_datetime(["2024-08-01T14:00:00.000000001Z"], utc=True)).astype(
        pd.DatetimeTZDtype(unit="ns", tz="UTC")
    )
    with pytest.raises(CanonicalizeError, match="precision|not invertible"):
        canonicalize_datetime_series(series, unit="us", column="entry_timestamp")


def test_portable_hash_ignores_datetime_unit_and_string_label() -> None:
    from thesistester.persistence.local_store import hash_dataframe

    us_frame = pd.DataFrame(
        {
            "entry_timestamp": _ny_stamps(unit="us"),
            "direction": pd.Series(["long", "short"], dtype="string"),
            "r_multiple": np.array([0.5, -0.25], dtype="float64"),
        }
    )
    ns_frame = us_frame.copy()
    ns_frame["entry_timestamp"] = _ny_stamps(unit="ns")
    ns_frame["direction"] = pd.Series(["long", "short"], dtype=object)
    assert hash_dataframe(us_frame) != hash_dataframe(ns_frame)
    assert portable_hash_dataframe(us_frame) == portable_hash_dataframe(ns_frame)
    assert portable_dtype_label(us_frame["entry_timestamp"]) == portable_dtype_label(
        ns_frame["entry_timestamp"]
    )
    moved = ns_frame.copy()
    moved.loc[0, "entry_timestamp"] = moved.loc[0, "entry_timestamp"] + pd.Timedelta(microseconds=1)
    assert portable_hash_dataframe(us_frame) != portable_hash_dataframe(moved)


def test_portable_bundle_hash_matches_across_datetime_units() -> None:
    us_frame = pd.DataFrame({"entry_timestamp": _ny_stamps(unit="us"), "x": [1, 2]})
    ns_frame = pd.DataFrame({"entry_timestamp": _ny_stamps(unit="ns"), "x": [1, 2]})

    def _zip_bytes(frame: pd.DataFrame, *, created_at: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            inner = io.BytesIO()
            frame.to_parquet(inner, index=False)
            archive.writestr("trades.parquet", inner.getvalue())
            archive.writestr(
                "manifest.json",
                json.dumps({"created_at": created_at, "ok": True}),
            )
            archive.writestr("notes.txt", b"hello")
        return buffer.getvalue()

    left = _zip_bytes(us_frame, created_at="2026-01-01T00:00:00+00:00")
    right = _zip_bytes(ns_frame, created_at="2099-01-01T00:00:00+00:00")
    assert portable_canonical_bundle_hash(left) == portable_canonical_bundle_hash(right)
    changed = ns_frame.copy()
    changed.loc[0, "x"] = 99
    assert portable_canonical_bundle_hash(left) != portable_canonical_bundle_hash(
        _zip_bytes(changed, created_at="2026-01-01T00:00:00+00:00")
    )


def test_portable_hash_empty_frame_ignores_ghost_dtypes() -> None:
    typed = pd.DataFrame(
        {
            "trade_id": pd.Series(dtype="int64"),
            "entry_timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
            "direction": pd.Series(dtype="string"),
        }
    )
    ghost = pd.DataFrame(
        {
            "trade_id": pd.Series(dtype=object),
            "entry_timestamp": pd.Series(dtype=object),
            "direction": pd.Series(dtype=object),
        }
    )
    assert list(typed.columns) == list(ghost.columns)
    assert portable_hash_dataframe(typed) == portable_hash_dataframe(ghost)
    extra = ghost.copy()
    extra["extra"] = pd.Series(dtype=object)
    assert portable_hash_dataframe(typed) != portable_hash_dataframe(extra)


def test_portable_bundle_hash_rewrites_product_identity_json() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": _ny_stamps(unit="us"),
            "close": np.array([1.0, 2.0], dtype="float64"),
        }
    )
    source = pd.DataFrame(
        {
            "timestamp": _ny_stamps(unit="ns"),
            "close": np.array([1.0, 2.0], dtype="float64"),
        }
    )

    def _zip_bytes(*, data_hash: str, dataset_id: str, source_hash: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, payload_frame in (
                ("dataset.parquet", frame),
                ("subtimeframe_data.parquet", source),
            ):
                inner = io.BytesIO()
                payload_frame.to_parquet(inner, index=False)
                archive.writestr(name, inner.getvalue())
            archive.writestr(
                "dataset_meta.json",
                json.dumps(
                    {
                        "instrument": "MNQ",
                        "base_interval": "1min",
                        "source_timezone": "UTC",
                        "exchange_timezone": "America/New_York",
                        "dataset_id": dataset_id,
                    }
                ),
            )
            archive.writestr(
                "research_identity.json",
                json.dumps(
                    {
                        "data_identity": {
                            "data_content_hash": data_hash,
                            "dataset_id": dataset_id,
                            "instrument": "MNQ",
                            "base_interval": "1min",
                            "source_timezone": "UTC",
                            "exchange_timezone": "America/New_York",
                        }
                    }
                ),
            )
            archive.writestr(
                "subtimeframe_meta.json",
                json.dumps({"ingestion_provenance": {"source_content_hash": source_hash}}),
            )
        return buffer.getvalue()

    left = _zip_bytes(data_hash="aa" * 32, dataset_id="bb" * 32, source_hash="cc" * 32)
    right = _zip_bytes(data_hash="dd" * 32, dataset_id="ee" * 32, source_hash="ff" * 32)
    assert portable_canonical_bundle_hash(left) == portable_canonical_bundle_hash(right)
    mutated = frame.copy()
    mutated.loc[0, "close"] = 99.0
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        inner = io.BytesIO()
        mutated.to_parquet(inner, index=False)
        archive.writestr("dataset.parquet", inner.getvalue())
        inner = io.BytesIO()
        source.to_parquet(inner, index=False)
        archive.writestr("subtimeframe_data.parquet", inner.getvalue())
        archive.writestr(
            "dataset_meta.json",
            json.dumps(
                {
                    "instrument": "MNQ",
                    "base_interval": "1min",
                    "source_timezone": "UTC",
                    "exchange_timezone": "America/New_York",
                    "dataset_id": "aa" * 32,
                }
            ),
        )
    assert portable_canonical_bundle_hash(left) != portable_canonical_bundle_hash(buffer.getvalue())


def test_stage_trace_rule_table() -> None:
    rule1 = evaluate_rule_8_1(
        r_load_rss_gib=4.2,
        r_signals_rss_gib=4.0,
        r_ctx_rss_gib=4.3,
        map_step_gib=0.3,
    )
    assert rule1["rule"] == 1
    rule2 = evaluate_rule_8_1(
        r_load_rss_gib=4.2,
        r_signals_rss_gib=4.0,
        r_ctx_rss_gib=6.0,
        map_step_gib=1.8,
    )
    assert rule2["rule"] == 2
    rule3 = evaluate_rule_8_1(
        r_load_rss_gib=1.0,
        r_signals_rss_gib=4.0,
        r_ctx_rss_gib=6.5,
        map_step_gib=2.4,
    )
    assert rule3["rule"] == 3
    assert rule3["capacity_result"] == "capacity_check_passed"
    rule3_cap = evaluate_rule_8_1(
        r_load_rss_gib=1.0,
        r_signals_rss_gib=4.6,
        r_ctx_rss_gib=6.5,
        map_step_gib=2.4,
    )
    assert rule3_cap["capacity_result"] == "stop_and_revise_before_MW1"
    rule4 = evaluate_rule_8_1(
        r_load_rss_gib=1.5,
        r_signals_rss_gib=3.0,
        r_ctx_rss_gib=6.5,
        map_step_gib=2.0,
    )
    assert rule4["rule"] == 4
    assert compute_b(r_pre_prepare_hwm_gib=2.0, r_signals_hwm_gib=1.5) == 2.0


def test_synthetic_golden_matches_live_capture_flag_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§10.4 test 6 CI subset: flag on vs the recorded MW0 synthetic outputs."""
    if not GOLDEN.is_dir():
        pytest.fail(
            "STOP AND REPORT: synthetic golden is missing; "
            "do not skip — re-run with --regenerate only at the MW0 base commit"
        )
    monkeypatch.setenv("THESISTESTER_MEMORY_PATH", "array")
    from tests.fixtures.memory_parity.record_memory_parity import record_synthetic

    candidate = record_synthetic(tmp_path / "live-flag-on", run_label="ci-live-array")
    report = compare_captures(GOLDEN, candidate, pre_step=False)
    assert report.ok, format_report(report)


def test_synthetic_golden_matches_live_capture(tmp_path: Path) -> None:
    if not GOLDEN.is_dir():
        pytest.fail(
            "STOP AND REPORT: synthetic golden is missing; "
            "do not skip — re-run with --regenerate only at the MW0 base commit"
        )
    from tests.fixtures.memory_parity.record_memory_parity import record_synthetic

    candidate = record_synthetic(tmp_path / "live", run_label="ci-live")
    report = compare_captures(GOLDEN, candidate, pre_step=False)
    assert report.ok, format_report(report)
    prepare = json.loads(
        (GOLDEN / "cells" / CI_PREPARE_REPLICA.cell_id / "summary.json").read_text()
    )
    assert int(prepare["trade_count"]) >= 1
    zero = json.loads((GOLDEN / "cells" / CI_CELL6_SHAPE.cell_id / "summary.json").read_text())
    assert int(zero["trade_count"]) == 0


def test_synthetic_two_runs_canonical_hash_equal(tmp_path: Path) -> None:
    if not GOLDEN.is_dir():
        pytest.fail(
            "STOP AND REPORT: synthetic golden is missing; "
            "do not skip — re-run with --regenerate only at the MW0 base commit"
        )
    from tests.fixtures.memory_parity.record_memory_parity import record_synthetic

    first = record_synthetic(tmp_path / "a", run_label="det-a")
    second = record_synthetic(tmp_path / "b", run_label="det-b")
    for cell_id in (CI_PREPARE_REPLICA.cell_id, CI_CELL6_SHAPE.cell_id):
        left = (first / "cells" / cell_id / "canonical_bundle_hash.txt").read_text().strip()
        right = (second / "cells" / cell_id / "canonical_bundle_hash.txt").read_text().strip()
        assert left == right


def test_synthetic_generator_is_deterministic(tmp_path: Path) -> None:
    first = write_synthetic_csv(tmp_path / "a.csv")
    second = write_synthetic_csv(tmp_path / "b.csv")
    assert first.read_bytes() == second.read_bytes()
    committed = default_synthetic_path()
    if committed.is_file():
        assert committed.read_bytes() == first.read_bytes()


def test_resolve_main_ref_prefers_origin_main_over_local_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.fixtures.memory_parity import gitref

    monkeypatch.setattr(
        gitref, "ref_exists", lambda ref, *, cwd=None: ref in {"origin/main", "main"}
    )
    assert gitref.resolve_main_ref() == "origin/main"


def test_resolve_main_ref_fetches_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.fixtures.memory_parity import gitref

    fetched = {"done": False}

    def exists(ref: str, *, cwd: Path | None = None) -> bool:
        return fetched["done"] and ref == "origin/main"

    def git_ok(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        fetched["done"] = True
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(gitref, "ref_exists", exists)
    monkeypatch.setattr(gitref, "_git_ok", git_ok)
    assert gitref.resolve_main_ref() == "origin/main"


def test_resolve_main_ref_fails_closed_when_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.fixtures.memory_parity import gitref

    monkeypatch.setattr(gitref, "ref_exists", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        gitref,
        "_git_ok",
        lambda args, *, cwd=None: subprocess.CompletedProcess(
            args, 128, "", "not a valid object name"
        ),
    )
    with pytest.raises(GitRefError, match="STOP AND REPORT"):
        gitref.resolve_main_ref()


def test_resolve_farm_commit_fails_closed_when_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.fixtures.memory_parity import gitref

    monkeypatch.setattr(gitref, "ref_exists", lambda *args, **kwargs: False)
    monkeypatch.setattr(gitref, "_is_shallow", lambda *, cwd=None: False)
    monkeypatch.setattr(
        gitref,
        "_git_ok",
        lambda args, *, cwd=None: subprocess.CompletedProcess(args, 128, "", "missing"),
    )
    with pytest.raises(GitRefError, match="STOP AND REPORT"):
        gitref.resolve_farm_production_commit()


def test_isolate_store_restores_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.fixtures.memory_parity.capture import STORE_ENV, isolate_store

    monkeypatch.delenv(STORE_ENV, raising=False)
    with isolate_store(tmp_path):
        assert Path(os.environ[STORE_ENV]) == (tmp_path / "store").resolve()
    assert STORE_ENV not in os.environ


def test_load_time_prepare_resets_vmhwm_after_map_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import weakref

    from tests.fixtures.memory_parity.stage_trace import (
        TraceState,
        make_prepare_wrapper,
    )

    class Probe:
        pass

    held_at_reset: list[bool] = []
    refs: list[weakref.ref[Probe]] = []

    def fake_prepare(*args: object, **kwargs: object) -> Probe:
        payload = Probe()
        refs.append(weakref.ref(payload))
        return payload

    def fake_reset() -> None:
        held_at_reset.append(refs[-1]() is not None)

    monkeypatch.setattr(
        "tests.fixtures.memory_parity.stage_trace.collect_and_reset_vmhwm", fake_reset
    )
    monkeypatch.setattr(
        "tests.fixtures.memory_parity.stage_trace.sample",
        lambda *args, **kwargs: None,
    )
    state = TraceState()
    wrapped = make_prepare_wrapper(fake_prepare, state)
    outside = wrapped()
    assert outside is not None
    assert held_at_reset == []
    assert state.reset_after_load_prepare is False
    state.inside_load = True
    assert wrapped() is None
    assert held_at_reset == [False]
    assert state.reset_after_load_prepare is True
    assert state.load_prepare_seen is True


def _flip_float64_ulp(value: float) -> float:
    bits = np.float64(value).view(np.uint64)
    return float((bits + np.uint64(1)).view(np.float64))


def _member_zip(
    *,
    dataset: pd.DataFrame | None = None,
    source: pd.DataFrame | None = None,
    levels: pd.DataFrame | None = None,
    naked: pd.DataFrame | None = None,
    trades: pd.DataFrame | None = None,
    extra_json: dict[str, Any] | None = None,
    extra_bytes: dict[str, bytes] | None = None,
    identity_hashes: tuple[str, str, str] = ("aa" * 32, "bb" * 32, "cc" * 32),
) -> bytes:
    stamps = _ny_stamps(unit="ns")
    if dataset is None:
        dataset = pd.DataFrame(
            {"timestamp": stamps, "close": np.array([100.0, 101.0], dtype="float64")}
        )
    if source is None:
        source = pd.DataFrame(
            {"timestamp": stamps, "close": np.array([100.0, 101.0], dtype="float64")}
        )
    if levels is None:
        levels = pd.DataFrame(
            {
                "timestamp": stamps,
                "EMA_9_1min": np.array([1.23456789012345, 2.5], dtype="float64"),
            }
        )
    if naked is None:
        naked = pd.DataFrame(
            {
                "timestamp": stamps,
                "EMA_21_5min": np.array([3.14159265358979, 4.0], dtype="float64"),
            }
        )
    if trades is None:
        trades = pd.DataFrame(
            {
                "trade_id": [1, 2],
                "r_multiple": np.array([0.5, -0.25], dtype="float64"),
                "exit_subbar_timestamp": stamps,
            }
        )
    data_hash, dataset_id, source_hash = identity_hashes
    members: dict[str, bytes] = {}
    for name, frame in (
        ("dataset.parquet", dataset),
        ("subtimeframe_data.parquet", source),
        ("levels.parquet", levels),
        ("naked_flags.parquet", naked),
        ("trades.parquet", trades),
    ):
        inner = io.BytesIO()
        frame.to_parquet(inner, index=False)
        members[name] = inner.getvalue()
    members["dataset_meta.json"] = json.dumps(
        {
            "instrument": "MNQ",
            "base_interval": "1min",
            "source_timezone": "UTC",
            "exchange_timezone": "America/New_York",
            "dataset_id": dataset_id,
        }
    ).encode("utf-8")
    members["research_identity.json"] = json.dumps(
        {
            "data_identity": {
                "data_content_hash": data_hash,
                "dataset_id": dataset_id,
                "instrument": "MNQ",
            }
        }
    ).encode("utf-8")
    members["subtimeframe_meta.json"] = json.dumps(
        {"ingestion_provenance": {"source_content_hash": source_hash}}
    ).encode("utf-8")
    members["trade_summary.json"] = json.dumps({"trade_count": 2, "expectancy_r": 0.0805}).encode(
        "utf-8"
    )
    members["signals_meta.json"] = json.dumps({"signal_settings_hash": "sig"}).encode("utf-8")
    members["manifest.json"] = json.dumps(
        {"created_at": "2026-01-01T00:00:00+00:00", "ok": True}
    ).encode("utf-8")
    members["notes.txt"] = b"hello"
    for name, payload in (extra_json or {}).items():
        members[name] = json.dumps(payload).encode("utf-8")
    for name, payload in (extra_bytes or {}).items():
        members[name] = payload
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_portable_hash_last_bit_ema_fails() -> None:
    """Farm Mac/Linux last-bit EMA split must fail; do not paper over it."""
    left = pd.DataFrame(
        {
            "timestamp": _ny_stamps(unit="ns"),
            "EMA_9_1min": np.array([1.23456789012345, 2.5], dtype="float64"),
        }
    )
    right = left.copy()
    right.loc[0, "EMA_9_1min"] = _flip_float64_ulp(float(left.loc[0, "EMA_9_1min"]))
    assert portable_hash_dataframe(left) != portable_hash_dataframe(right)
    left_hash = portable_canonical_bundle_hash(_member_zip(levels=left))
    right_hash = portable_canonical_bundle_hash(_member_zip(levels=right))
    assert left_hash != right_hash


def test_portable_hash_fails_on_each_member_type() -> None:
    baseline = _member_zip()
    baseline_hash = portable_canonical_bundle_hash(baseline)

    dataset = pd.DataFrame(
        {"timestamp": _ny_stamps(unit="ns"), "close": np.array([100.0, 101.0], dtype="float64")}
    )
    dataset.loc[0, "close"] = 99.5
    assert portable_canonical_bundle_hash(_member_zip(dataset=dataset)) != baseline_hash

    source = pd.DataFrame(
        {"timestamp": _ny_stamps(unit="ns"), "close": np.array([100.0, 101.0], dtype="float64")}
    )
    source.loc[1, "close"] = 102.0
    assert portable_canonical_bundle_hash(_member_zip(source=source)) != baseline_hash

    levels = pd.DataFrame(
        {
            "timestamp": _ny_stamps(unit="ns"),
            "EMA_9_1min": np.array([1.23456789012345, 2.5], dtype="float64"),
        }
    )
    levels.loc[0, "EMA_9_1min"] = _flip_float64_ulp(1.23456789012345)
    assert portable_canonical_bundle_hash(_member_zip(levels=levels)) != baseline_hash

    naked = pd.DataFrame(
        {
            "timestamp": _ny_stamps(unit="ns"),
            "EMA_21_5min": np.array([3.14159265358979, 4.0], dtype="float64"),
        }
    )
    naked.loc[0, "EMA_21_5min"] = _flip_float64_ulp(3.14159265358979)
    assert portable_canonical_bundle_hash(_member_zip(naked=naked)) != baseline_hash

    trades = pd.DataFrame(
        {
            "trade_id": [1, 2],
            "r_multiple": np.array([0.5, -0.25], dtype="float64"),
            "exit_subbar_timestamp": _ny_stamps(unit="ns"),
        }
    )
    trades.loc[0, "r_multiple"] = _flip_float64_ulp(0.5)
    assert portable_canonical_bundle_hash(_member_zip(trades=trades)) != baseline_hash

    mutated_summary = _member_zip(extra_json={"trade_summary.json": {"trade_count": 3}})
    assert portable_canonical_bundle_hash(mutated_summary) != baseline_hash

    mutated_signals = _member_zip(
        extra_json={"signals_meta.json": {"signal_settings_hash": "nope"}}
    )
    assert portable_canonical_bundle_hash(mutated_signals) != baseline_hash

    mutated_notes = _member_zip(extra_bytes={"notes.txt": b"hello!"})
    assert portable_canonical_bundle_hash(mutated_notes) != baseline_hash

    mutated_instrument = json.loads(
        zipfile.ZipFile(io.BytesIO(baseline)).read("dataset_meta.json").decode("utf-8")
    )
    mutated_instrument["instrument"] = "NQ"
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(baseline), "r") as src, zipfile.ZipFile(buffer, "w") as dest:
        for name in src.namelist():
            payload = src.read(name)
            if name == "dataset_meta.json":
                payload = json.dumps(mutated_instrument).encode("utf-8")
            dest.writestr(name, payload)
    assert portable_canonical_bundle_hash(buffer.getvalue()) != baseline_hash


def test_portable_hash_identity_strings_are_not_a_second_source() -> None:
    left = _member_zip(identity_hashes=("aa" * 32, "bb" * 32, "cc" * 32))
    right = _member_zip(identity_hashes=("dd" * 32, "ee" * 32, "ff" * 32))
    assert portable_canonical_bundle_hash(left) == portable_canonical_bundle_hash(right)


def test_portable_hash_does_not_rewrite_dataset_id_outside_identity_files() -> None:
    baseline = _member_zip()
    mutated = _member_zip(
        extra_json={"trade_summary.json": {"trade_count": 2, "dataset_id": "other" * 8}}
    )
    assert portable_canonical_bundle_hash(baseline) != portable_canonical_bundle_hash(mutated)


def test_compare_fails_on_isolated_replica_bit(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write_tiny_capture(left, "full_reference", extra=0.0, hash_text="aaa")
    _write_tiny_capture(right, "full_reference", extra=0.0, hash_text="aaa")
    replica_path = cell_dir(right, "full_reference") / "replica_expectancies.json"
    payload = json.loads(replica_path.read_text(encoding="utf-8"))
    payload["hex_bits"][0] = f"{int(payload['hex_bits'][0], 16) ^ 1:016x}"
    replica_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report = compare_captures(left, right, pre_step=False)
    assert report.ok is False
    assert {diff.field for diff in report.gate_failures} == {"replica_expectancies"}


def test_compare_fails_on_isolated_da5_bit(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write_tiny_capture(left, "full_reference", extra=0.0, hash_text="aaa")
    _write_tiny_capture(right, "full_reference", extra=0.0, hash_text="aaa")
    da5_path = cell_dir(right, "full_reference") / "da5.json"
    payload = json.loads(da5_path.read_text(encoding="utf-8"))
    payload["random_p_value_ge"]["hex"] = f"{int(payload['random_p_value_ge']['hex'], 16) ^ 1:016x}"
    da5_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    full = compare_captures(left, right, pre_step=False)
    assert full.ok is False
    assert {diff.field for diff in full.gate_failures} == {"random_p_value_ge"}
    pre = compare_captures(left, right, pre_step=True)
    assert pre.ok is True
    assert any(diff.field == "random_p_value_ge" and not diff.gate for diff in pre.diffs)


def test_compare_fails_on_isolated_summary_and_ledger(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write_tiny_capture(left, "full_reference", extra=0.0, hash_text="aaa")
    _write_tiny_capture(right, "full_reference", extra=0.0, hash_text="aaa")
    summary_path = cell_dir(right, "full_reference") / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["win_rate"]["hex"] = f"{int(summary['win_rate']['hex'], 16) ^ 1:016x}"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    report = compare_captures(left, right, pre_step=False)
    assert report.ok is False
    assert "win_rate" in {diff.field for diff in report.gate_failures}

    _write_tiny_capture(right, "full_reference", extra=0.0, hash_text="aaa")
    ledger_path = cell_dir(right, "full_reference") / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["status"] = "failed"
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    ledger_report = compare_captures(left, right, pre_step=False)
    assert ledger_report.ok is False
    assert "ledger.status" in {diff.field for diff in ledger_report.gate_failures}


def test_replica_hook_records_without_changing_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import thesistester.analytics.overfitting as ov
    import thesistester.study.execute as ex

    from tests.fixtures.memory_parity.hooks import replica_expectancies_hook

    def fake(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"available": True, "replica_expectancies": [0.0805, 0.1]}

    monkeypatch.setattr(ov, "vs_random_benchmark", fake)
    monkeypatch.setattr(ex, "vs_random_benchmark", fake)
    with replica_expectancies_hook() as sink:
        result = ex.vs_random_benchmark()
        assert result == {"available": True, "replica_expectancies": [0.0805, 0.1]}
        assert sink.last == [0.0805, 0.1]
        assert sink.calls == [[0.0805, 0.1]]
    assert ex.vs_random_benchmark is fake
    assert ov.vs_random_benchmark is fake


def test_prefer_pythonpath_thesistester_beats_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    farm = tmp_path / "farm59"
    mw0 = tmp_path / "mw0"
    (farm / "thesistester").mkdir(parents=True)
    (mw0 / "thesistester").mkdir(parents=True)
    (farm / "thesistester" / "__init__.py").write_text("NAME = 'farm59'\n", encoding="utf-8")
    (mw0 / "thesistester" / "__init__.py").write_text("NAME = 'mw0'\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(farm), str(mw0)]))
    original = list(sys.path)
    try:
        sys.path[:] = [str(mw0), str(farm), str(mw0)] + original
        chosen = prefer_pythonpath_thesistester()
        assert chosen == farm.resolve()
        assert Path(sys.path[0]).resolve() == farm.resolve()
        assert pythonpath_thesistester_roots()[0] == farm.resolve()
    finally:
        sys.path[:] = original


def test_pythonpath_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    farm = tmp_path / "farm59"
    (farm / "thesistester").mkdir(parents=True)
    (farm / "thesistester" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(farm))
    with pytest.raises(CompatError, match="STOP AND REPORT"):
        assert_imported_thesistester_follows_pythonpath()


def test_python_dash_m_from_checkout_uses_pythonpath_thesistester(tmp_path: Path) -> None:
    """Farm invocation: cwd is MW0; PYTHONPATH lists 59a4652 first."""
    farm = tmp_path / "farm59"
    mw0 = tmp_path / "mw0"
    (farm / "thesistester").mkdir(parents=True)
    (mw0 / "thesistester").mkdir(parents=True)
    (farm / "thesistester" / "__init__.py").write_text("NAME = 'farm59'\n", encoding="utf-8")
    (mw0 / "thesistester" / "__init__.py").write_text("NAME = 'mw0'\n", encoding="utf-8")
    probe = (
        "import sys\n"
        "from tests.fixtures.memory_parity.compat import prefer_pythonpath_thesistester\n"
        "prefer_pythonpath_thesistester()\n"
        "import thesistester\n"
        "print(getattr(thesistester, 'NAME', 'missing'))\n"
        "print(thesistester.__file__)\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(farm), str(mw0), str(REPO)])
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(mw0),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    assert lines[0] == "farm59"
    assert str(farm) in lines[1]
