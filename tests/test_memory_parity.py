"""MW0 tooling: hook audit, compare gates, §8.1 rules, synthetic golden."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.memory_parity.bits import float64_hex, replica_hex_list
from tests.fixtures.memory_parity.cells import (
    CI_CELL6_SHAPE,
    CI_PREPARE_REPLICA,
    SHORT_CELLS,
    parse_cell_selector,
)
from tests.fixtures.memory_parity.compat import (
    FARM_PRODUCTION_COMMIT,
    HOOK_POINTS,
    resolve_all_hooks,
)
from tests.fixtures.memory_parity.compare import compare_captures, compare_trades, format_report
from tests.fixtures.memory_parity.generate_synthetic import (
    default_synthetic_path,
    write_synthetic_csv,
)
from tests.fixtures.memory_parity.io import cell_dir, write_capture
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


def test_hook_points_resolve_on_imported_package() -> None:
    resolved = resolve_all_hooks()
    assert set(resolved) == {f"{module}.{attr}" for module, attr in HOOK_POINTS}


def test_hook_points_exist_at_farm_production_commit() -> None:
    """Every capture/trace hook name exists at 59a4652 (read-only git show)."""
    missing: list[str] = []
    for module_name, attr in HOOK_POINTS:
        rel = module_name.replace(".", "/") + ".py"
        source = subprocess.check_output(
            ["git", "show", f"{FARM_PRODUCTION_COMMIT}:{rel}"],
            cwd=REPO,
            text=True,
        )
        needle = f"def {attr}("
        if needle not in source and f"{attr} =" not in source:
            # Module-level re-export (from x import attr) is also a hit.
            if f"import {attr}" not in source and f" {attr}," not in source:
                missing.append(f"{rel} {attr}")
    assert missing == []


def test_thesistester_package_untouched_vs_main() -> None:
    diff = subprocess.check_output(
        ["git", "diff", "main", "--", "thesistester/"],
        cwd=REPO,
        text=True,
    )
    assert diff == ""


def test_legacy_golden_readme_not_touched() -> None:
    diff = subprocess.check_output(
        ["git", "diff", "main", "--", "tests/fixtures/golden/"],
        cwd=REPO,
        text=True,
    )
    assert diff == ""


def test_plan_status_line_unchanged() -> None:
    text = (REPO / "docs" / "WORKER_MEMORY_IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert "**Status:** **Plan only.**" in text


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


@pytest.mark.skipif(not GOLDEN.is_dir(), reason="synthetic golden not recorded yet")
def test_synthetic_golden_matches_live_capture(tmp_path: Path) -> None:
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


@pytest.mark.skipif(not GOLDEN.is_dir(), reason="synthetic golden not recorded yet")
def test_synthetic_two_runs_canonical_hash_equal(tmp_path: Path) -> None:
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
