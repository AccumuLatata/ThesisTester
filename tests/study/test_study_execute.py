"""RS3 study expand/run — confirm, ledger, resume, workers, index parity."""

from __future__ import annotations

import io
import json
import math
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest
import yaml

from thesistester.cli import main as cli_main
from thesistester.research_bundle import canonical_bundle_hash
from thesistester.research_identity import normalize_execution_origin
from thesistester.study.execute import (
    DA_DIRECTION_INDEX_KEYS,
    R18_INDEX_METRIC_KEYS,
    STUDY_INDEX_KEYS,
    _failed_index_row,
    _study_dir_lock,
    build_index_row_from_state,
    direction_index_fields,
    execute_study_cell,
    prepare_study_expansion,
    rebuild_direction_index,
    run_study,
)
from thesistester.study.ledger import load_ledger
from thesistester.study.schema import STUDY_SCHEMA_VERSION, StudySpecError


def _fake_bundle_bytes(
    name: str,
    *,
    profit_factor: float | None = 1.5,
    win_rate: float | None = 0.6,
) -> bytes:
    buffer = io.BytesIO()
    summary = {
        "trade_count": 3,
        "expectancy_r": 0.25,
        "total_r": 0.75,
        "max_drawdown_r": -0.5,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
    }
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"run_name": name}))
        archive.writestr(
            "dataset_meta.json",
            json.dumps({"dataset_id": "ds-test", "instrument": "ES"}),
        )
        archive.writestr(
            "trade_summary.json",
            json.dumps({"trade_summary": summary}),
        )
    return buffer.getvalue()


def _mini_study_yaml(
    path: Path,
    *,
    confirm_above_runs: int = 200,
    name: str = "pdPOC_rs3",
) -> Path:
    spec = {
        "schema_version": STUDY_SCHEMA_VERSION,
        "study": {
            "name": name,
            "confirm_above_runs": confirm_above_runs,
            "workers": 1,
            "dataset": {
                "path": "bars.csv",
                "instrument": "ES",
                "source_timezone": "America/New_York",
            },
            "levels": {
                "sma_lengths": [50],
                "ema_lengths": [21],
                "sma_timeframes": ["1min"],
                "ema_timeframes": ["5min"],
            },
            "constants": {
                "direction": "both",
                "tolerance_ticks": 0,
                "min_confluences": 2,
                "max_confluences": 2,
                "min_valid_confluences": 1,
                "naked_only": False,
                "naked_requirement": "any",
                "trigger_params": {},
                "backtest": {
                    "stop_loss_ticks": 8,
                    "take_profit_ticks": 16,
                    "exposure_policy": "single_position",
                },
                "grid": {"enabled": False},
                "validation": {"enabled": False},
                "walk_forward": {"enabled": False},
            },
            "factors": {
                "core_level": ["ONH"],
                "partner_levels": [["SMA_50_1min"], ["EMA_21_5min"]],
                "confluence_mode": ["global_cluster", "anchor_rules"],
                "trigger": ["touch"],
                "trigger_timeframe": ["base"],
                "otf": [{"enabled": False}],
            },
            "mode_rules": {
                "global_cluster": {
                    "selected_levels": ["${core_level}", "${partner_levels...}"],
                },
                "anchor_rules": {
                    "selected_levels": [],
                    "anchor_level": "${core_level}",
                    "confluence_rules": {"from_partners": "required"},
                },
            },
        },
    }
    path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return path


def _fake_executor_factory(fail_names: set[str] | None = None):
    fail_names = fail_names or set()

    def _executor(task):
        run_spec, _base = task
        name = str(run_spec["name"])
        if name in fail_names:
            return {
                "status": "failed",
                "name": name,
                "bundle": None,
                "index_row": {
                    **{key: None for key in R18_INDEX_METRIC_KEYS},
                    "run_name": name,
                    "execution_origin": "study",
                },
                "error": "InjectedFailure: boom",
            }
        state = {
            "dataset_id": "ds-test",
            "instrument": "ES",
            "execution_origin": "study",
            "cache_provenance": {"outcome": "miss"},
            "trade_summary": {
                "trade_count": 3,
                "expectancy_r": 0.25,
                "total_r": 0.75,
                "max_drawdown_r": -0.5,
                "profit_factor": 1.5,
                "win_rate": 0.6,
            },
            "best_grid_result": {},
            "validation_summary": {},
            "walk_forward_summary": {},
        }
        bundle = _fake_bundle_bytes(name)
        row = build_index_row_from_state(name=name, state=state, bundle=bundle)
        return {
            "status": "ok",
            "name": name,
            "bundle": bundle,
            "index_row": row,
            "error": None,
        }

    return _executor


def test_study_expand_cli_writes_artifacts_and_cost_hints(tmp_path: Path, capsys):
    study = _mini_study_yaml(tmp_path / "study.yaml")
    out = tmp_path / "out"
    code = cli_main(["study", "expand", str(study), "--output-dir", str(out)])
    assert code == 0
    assert (out / "study.spec.yaml").is_file()
    assert (out / "study.expansion.json").is_file()
    assert (out / "experiment.yaml").is_file()
    captured = capsys.readouterr().out
    assert "run_count=4" in captured
    assert "batteries:" in captured


def test_study_run_requires_confirm_above_threshold(tmp_path: Path):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=2)
    out = tmp_path / "out"
    with pytest.raises(StudySpecError, match="confirm_above_runs"):
        run_study(
            study,
            output_dir=out,
            confirm=False,
            cell_executor=_fake_executor_factory(),
        )


def test_study_run_confirm_executes_with_study_origin(tmp_path: Path):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=2)
    out = tmp_path / "out"
    result = run_study(
        study,
        output_dir=out,
        confirm=True,
        cell_executor=_fake_executor_factory(),
    )
    assert result["executed"] == 4
    ledger = load_ledger(out)
    assert ledger is not None
    assert ledger["confirm"]["confirmed"] is True
    assert all(cell["status"] == "ok" for cell in ledger["cells"].values())
    index = pd.read_csv(out / "results_index.csv")
    assert list(index.columns) == list(STUDY_INDEX_KEYS)
    assert set(index["execution_origin"].unique()) == {"study"}
    assert normalize_execution_origin("study") == "study"
    assert index["profit_factor"].notna().all()
    assert index["win_rate"].notna().all()
    for name in index["run_name"]:
        assert (out / f"{name}.research.zip").is_file()


def test_one_failing_cell_leaves_prior_ok_intact(tmp_path: Path):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    # Discover names via expand first.
    _spec, expansion, _out, _base = prepare_study_expansion(study, output_dir=out)
    names = [run["name"] for run in expansion.experiment["runs"]]
    fail = {names[1]}
    result = run_study(
        study,
        output_dir=out,
        confirm=False,
        cell_executor=_fake_executor_factory(fail_names=fail),
    )
    assert result["executed"] == 4
    ledger = load_ledger(out)
    assert ledger["cells"][names[0]]["status"] == "ok"
    assert ledger["cells"][names[1]]["status"] == "failed"
    assert "InjectedFailure" in (ledger["cells"][names[1]]["error"] or "")
    assert (out / f"{names[0]}.research.zip").is_file()
    assert not (out / f"{names[1]}.research.zip").is_file()
    index = pd.read_csv(out / "results_index.csv")
    assert len(index) == 4
    assert (index["status"] == "ok").sum() == 3
    assert (index["status"] == "failed").sum() == 1
    assert list(index.columns) == list(STUDY_INDEX_KEYS)
    failed_row = index.loc[index["run_name"] == names[1]].iloc[0]
    assert pd.isna(failed_row["profit_factor"])
    assert pd.isna(failed_row["win_rate"])
    for key in DA_DIRECTION_INDEX_KEYS:
        assert pd.isna(failed_row[key])
    ok_row = index.loc[index["run_name"] == names[0]].iloc[0]
    assert float(ok_row["profit_factor"]) == pytest.approx(1.5)
    assert float(ok_row["win_rate"]) == pytest.approx(0.6)


def test_soft_resume_skips_ok_force_reruns(tmp_path: Path):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    first = run_study(
        study,
        output_dir=out,
        cell_executor=_fake_executor_factory(),
    )
    assert first["executed"] == 4
    second = run_study(
        study,
        output_dir=out,
        cell_executor=_fake_executor_factory(),
    )
    assert second["executed"] == 0
    forced = run_study(
        study,
        output_dir=out,
        force=True,
        cell_executor=_fake_executor_factory(),
    )
    assert forced["executed"] == 4


def test_identity_mismatch_refuses_without_force(tmp_path: Path):
    study_a = _mini_study_yaml(tmp_path / "a.yaml", name="studyA", confirm_above_runs=100)
    out = tmp_path / "out"
    run_study(study_a, output_dir=out, cell_executor=_fake_executor_factory())
    prior_spec = (out / "study.spec.yaml").read_text(encoding="utf-8")
    study_b = _mini_study_yaml(tmp_path / "b.yaml", name="studyB", confirm_above_runs=100)
    with pytest.raises(StudySpecError, match="identity hash"):
        run_study(study_b, output_dir=out, cell_executor=_fake_executor_factory())
    assert (out / "study.spec.yaml").read_text(encoding="utf-8") == prior_spec
    # Force allows overwrite path.
    result = run_study(
        study_b,
        output_dir=out,
        force=True,
        cell_executor=_fake_executor_factory(),
    )
    assert result["executed"] == 4
    assert "studyB" in (out / "study.spec.yaml").read_text(encoding="utf-8")


def test_workers_continue_on_per_cell_failure(tmp_path: Path):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    _spec, expansion, _o, _b = prepare_study_expansion(study, output_dir=out)
    names = [run["name"] for run in expansion.experiment["runs"]]
    result = run_study(
        study,
        output_dir=out,
        workers=2,
        cell_executor=_fake_executor_factory(fail_names={names[0]}),
    )
    assert result["workers"] == 2
    assert result["executed"] == 4
    ledger = load_ledger(out)
    assert ledger["cells"][names[0]]["status"] == "failed"
    assert sum(1 for c in ledger["cells"].values() if c["status"] == "ok") == 3


def test_execute_study_cell_returns_failed_payload_not_raise(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated engine failure")

    monkeypatch.setattr("thesistester.study.execute.run_experiment", _boom)
    payload = execute_study_cell(({"name": "cell_x"}, "."))
    assert payload["status"] == "failed"
    assert payload["bundle"] is None
    assert "RuntimeError" in (payload["error"] or "")
    assert payload["index_row"]["run_name"] == "cell_x"


def test_index_columns_parity_vs_cli_execute_run(monkeypatch):
    """Ordered CLI ↔ study R18_INDEX_METRIC_KEYS parity (RS-D7)."""
    from thesistester import cli as cli_mod

    assert "status" in STUDY_INDEX_KEYS
    assert "bundle_path" in STUDY_INDEX_KEYS
    assert set(R18_INDEX_METRIC_KEYS).isdisjoint({"status", "bundle_path"})
    dd_idx = R18_INDEX_METRIC_KEYS.index("max_drawdown_r")
    assert R18_INDEX_METRIC_KEYS[dd_idx + 1] == "profit_factor"
    assert R18_INDEX_METRIC_KEYS[dd_idx + 2] == "win_rate"

    bundle = _fake_bundle_bytes("parity")
    state = {
        "dataset_id": "x",
        "instrument": "ES",
        "execution_origin": "cli",
        "cache_provenance": {"outcome": "miss"},
        "trade_summary": {
            "trade_count": 3,
            "expectancy_r": 0.25,
            "total_r": 0.75,
            "max_drawdown_r": -0.5,
            "profit_factor": 1.5,
            "win_rate": 0.6,
        },
        "best_grid_result": {},
        "validation_summary": {},
        "walk_forward_summary": {},
    }
    monkeypatch.setattr(cli_mod, "run_experiment", lambda *_a, **_k: state)
    monkeypatch.setattr(cli_mod, "build_research_bundle", lambda _state: bundle)
    _name, _bundle_out, cli_row = cli_mod._execute_run(({"name": "cell"}, "."))
    assert tuple(cli_row.keys()) == R18_INDEX_METRIC_KEYS

    study_row = build_index_row_from_state(
        name="cell",
        state={**state, "execution_origin": "study"},
        bundle=bundle,
    )
    assert tuple(study_row.keys()) == R18_INDEX_METRIC_KEYS
    assert study_row["bundle_hash"] == canonical_bundle_hash(bundle)
    assert study_row["profit_factor"] == pytest.approx(1.5)
    assert study_row["win_rate"] == pytest.approx(0.6)


def test_cli_study_run_confirm_exit_codes(tmp_path: Path, monkeypatch):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=2)
    out = tmp_path / "out"

    # Patch the executor used by run_study via execute module.
    import thesistester.study.execute as execute_mod

    monkeypatch.setattr(execute_mod, "execute_study_cell", _fake_executor_factory())

    code_no_confirm = cli_main(["study", "run", str(study), "--output-dir", str(out)])
    assert code_no_confirm == 2

    code_ok = cli_main(
        [
            "study",
            "run",
            str(study),
            "--output-dir",
            str(out),
            "--confirm",
        ]
    )
    assert code_ok == 0
    assert (out / "study.ledger.json").is_file()
    ledger = json.loads((out / "study.ledger.json").read_text(encoding="utf-8"))
    assert ledger["confirm"]["run_count"] == 4


def test_confirm_refuse_does_not_overwrite_expansion_artifacts(tmp_path: Path):
    study_a = _mini_study_yaml(tmp_path / "a.yaml", name="studyA", confirm_above_runs=100)
    out = tmp_path / "out"
    run_study(study_a, output_dir=out, cell_executor=_fake_executor_factory())
    prior_spec = (out / "study.spec.yaml").read_text(encoding="utf-8")
    study_big = _mini_study_yaml(tmp_path / "big.yaml", name="studyBig", confirm_above_runs=2)
    with pytest.raises(StudySpecError, match="confirm_above_runs"):
        run_study(
            study_big,
            output_dir=out,
            confirm=False,
            cell_executor=_fake_executor_factory(),
        )
    # Refuse path must not rewrite expansion artifacts over the prior study.
    assert (out / "study.spec.yaml").read_text(encoding="utf-8") == prior_spec


def test_force_identity_swap_prunes_orphan_cells(tmp_path: Path):
    study_a = _mini_study_yaml(tmp_path / "a.yaml", name="studyA", confirm_above_runs=100)
    out = tmp_path / "out"
    # Force one failure on A so an orphan failed cell would poison exit codes.
    _spec, expansion, _o, _b = prepare_study_expansion(study_a, output_dir=out)
    names_a = [run["name"] for run in expansion.experiment["runs"]]
    run_study(
        study_a,
        output_dir=out,
        cell_executor=_fake_executor_factory(fail_names={names_a[0]}),
    )
    study_b = _mini_study_yaml(tmp_path / "b.yaml", name="studyB", confirm_above_runs=100)
    result = run_study(
        study_b,
        output_dir=out,
        force=True,
        cell_executor=_fake_executor_factory(),
    )
    ledger = load_ledger(out)
    assert ledger is not None
    assert set(ledger["cells"]) == set(result["run_names"])
    assert all(cell["status"] == "ok" for cell in ledger["cells"].values())
    # CLI exit aggregation scoped to current names → success.

    # Smoke: failed count among current names is 0.
    cells = ledger["cells"]
    failed = sum(
        1 for name in result["run_names"] if (cells.get(name) or {}).get("status") == "failed"
    )
    assert failed == 0


def test_soft_resume_requeues_missing_bundle(tmp_path: Path):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    first = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    assert first["executed"] == 4
    # Delete one ok zip — soft resume must re-queue that cell.
    name = first["run_names"][0]
    zip_path = out / f"{name}.research.zip"
    assert zip_path.is_file()
    zip_path.unlink()
    second = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    assert second["executed"] == 1
    assert zip_path.is_file()


def test_soft_resume_rehydrates_metrics_when_index_row_missing(tmp_path: Path):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    first = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    name = first["run_names"][0]
    assert (out / f"{name}.research.zip").is_file()
    # Drop the ok row from the index while leaving ledger+zip intact.
    index = pd.read_csv(out / "results_index.csv")
    index = index.loc[index["run_name"] != name].copy()
    index.to_csv(out / "results_index.csv", index=False)
    second = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    assert second["executed"] == 0
    repaired = pd.read_csv(out / "results_index.csv")
    row = repaired.loc[repaired["run_name"] == name].iloc[0]
    assert row["status"] == "ok"
    assert int(row["trade_count"]) == 3
    assert float(row["expectancy_r"]) == pytest.approx(0.25)
    assert float(row["total_r"]) == pytest.approx(0.75)
    assert float(row["profit_factor"]) == pytest.approx(1.5)
    assert float(row["win_rate"]) == pytest.approx(0.6)
    assert row["dataset_id"] == "ds-test"
    assert row["instrument"] == "ES"
    assert pd.notna(row["bundle_hash"])


def test_soft_resume_rehydrate_preserves_identity_from_prior_and_bundle(tmp_path: Path):
    from thesistester.study.execute import _index_row_from_existing_bundle

    name = "cell_id"
    bundle_name = f"{name}.research.zip"
    (tmp_path / bundle_name).write_bytes(_fake_bundle_bytes(name))
    prior = {
        "run_name": name,
        "dataset_id": "prior-ds",
        "instrument": "NQ",
        "execution_origin": "study",
        "cache_outcome": "hit",
        "trade_count": None,
        "expectancy_r": None,
        "profit_factor": None,
        "win_rate": None,
    }
    row = _index_row_from_existing_bundle(
        name,
        output_dir=tmp_path,
        bundle_rel=bundle_name,
        prior_row=prior,
    )
    assert row["dataset_id"] == "prior-ds"
    assert row["instrument"] == "NQ"
    assert row["cache_outcome"] == "hit"
    assert float(row["profit_factor"]) == pytest.approx(1.5)

    # No prior row → fall back to dataset_meta.json inside the zip.
    row2 = _index_row_from_existing_bundle(name, output_dir=tmp_path, bundle_rel=bundle_name)
    assert row2["dataset_id"] == "ds-test"
    assert row2["instrument"] == "ES"


def test_soft_resume_repairs_poisoned_null_metric_ok_row(tmp_path: Path):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    first = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    name = first["run_names"][0]
    index = pd.read_csv(out / "results_index.csv")
    # Simulate historically poisoned soft-resume synthesis.
    for col in (
        "trade_count",
        "expectancy_r",
        "total_r",
        "max_drawdown_r",
        "profit_factor",
        "win_rate",
        "bundle_hash",
    ):
        index.loc[index["run_name"] == name, col] = None
    index.to_csv(out / "results_index.csv", index=False)
    second = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    assert second["executed"] == 0
    repaired = pd.read_csv(out / "results_index.csv")
    row = repaired.loc[repaired["run_name"] == name].iloc[0]
    assert int(row["trade_count"]) == 3
    assert float(row["expectancy_r"]) == pytest.approx(0.25)
    assert float(row["profit_factor"]) == pytest.approx(1.5)
    assert float(row["win_rate"]) == pytest.approx(0.6)


def test_soft_resume_rehydrates_pending_stub_after_ledger_ok_interrupt(tmp_path: Path):
    """Ledger ok + zip, index still pending null stub (mid-loop interrupt)."""
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    first = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    name = first["run_names"][1]
    assert (out / f"{name}.research.zip").is_file()
    index = pd.read_csv(out / "results_index.csv")
    # Plant the interrupt shape: pending stub with null metrics, no bundle_path on index.
    for col in (
        "trade_count",
        "expectancy_r",
        "total_r",
        "max_drawdown_r",
        "profit_factor",
        "win_rate",
        "bundle_hash",
        "bundle_path",
    ):
        index.loc[index["run_name"] == name, col] = None
    index.loc[index["run_name"] == name, "status"] = "pending"
    index.to_csv(out / "results_index.csv", index=False)
    second = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    assert second["executed"] == 0
    repaired = pd.read_csv(out / "results_index.csv")
    row = repaired.loc[repaired["run_name"] == name].iloc[0]
    assert row["status"] == "ok"
    assert row["bundle_path"] == f"{name}.research.zip"
    assert int(row["trade_count"]) == 3
    assert float(row["expectancy_r"]) == pytest.approx(0.25)
    assert float(row["profit_factor"]) == pytest.approx(1.5)
    assert float(row["win_rate"]) == pytest.approx(0.6)


def test_mark_cell_can_clear_bundle_path():
    from thesistester.study.ledger import empty_ledger, mark_cell

    ledger = empty_ledger(study_identity_hash="h", run_names=["c1"])
    ledger = mark_cell(ledger, "c1", status="ok", bundle_path="c1.research.zip", finished=True)
    assert ledger["cells"]["c1"]["bundle_path"] == "c1.research.zip"
    ledger = mark_cell(ledger, "c1", status="failed", error="x", bundle_path=None, finished=True)
    assert ledger["cells"]["c1"]["bundle_path"] is None


def test_index_nan_pf_wr_become_null():
    bundle = _fake_bundle_bytes("nan_cell")
    row = build_index_row_from_state(
        name="nan_cell",
        state={
            "dataset_id": "x",
            "instrument": "ES",
            "execution_origin": "study",
            "cache_provenance": {},
            "trade_summary": {
                "trade_count": 2,
                "expectancy_r": 0.1,
                "total_r": 0.2,
                "max_drawdown_r": -0.1,
                "profit_factor": float("nan"),
                "win_rate": float("nan"),
            },
            "best_grid_result": {},
            "validation_summary": {},
            "walk_forward_summary": {},
        },
        bundle=bundle,
    )
    assert row["profit_factor"] is None
    assert row["win_rate"] is None


def test_index_inf_pf_round_trips_csv_and_report(tmp_path: Path):
    from thesistester.study.report import report_study

    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    index = pd.read_csv(out / "results_index.csv")
    index["profit_factor"] = float("inf")
    index.to_csv(out / "results_index.csv", index=False)
    # pandas emits inf/-inf; reload and report must prefer index.
    reloaded = pd.read_csv(out / "results_index.csv")
    assert all(math.isinf(float(v)) for v in reloaded["profit_factor"])
    result = report_study(out)
    assert result.overview["profit_factor_source"].eq("index").all()
    assert all(math.isinf(float(v)) for v in result.overview["profit_factor"])


def test_soft_resume_field_backfills_pre_d7_ok_rows(tmp_path: Path):
    """Pre-D7 ok rows have trade metrics but lack PF/WR — backfill without re-run."""
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=100)
    out = tmp_path / "out"
    first = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    assert first["executed"] == 4
    index = pd.read_csv(out / "results_index.csv")
    # Drop PF/WR columns entirely (pre-D7 shape) while keeping core metrics.
    index = index.drop(columns=["profit_factor", "win_rate"])
    index.to_csv(out / "results_index.csv", index=False)
    second = run_study(study, output_dir=out, cell_executor=_fake_executor_factory())
    assert second["executed"] == 0
    repaired = pd.read_csv(out / "results_index.csv")
    assert "profit_factor" in repaired.columns
    assert "win_rate" in repaired.columns
    assert repaired["profit_factor"].notna().all()
    assert repaired["win_rate"].notna().all()
    assert float(repaired["profit_factor"].iloc[0]) == pytest.approx(1.5)
    assert float(repaired["win_rate"].iloc[0]) == pytest.approx(0.6)


def test_study_dir_lock_fail_closed_when_held(tmp_path: Path):
    with _study_dir_lock(tmp_path):
        with pytest.raises(StudySpecError, match="holds the lock"):
            with _study_dir_lock(tmp_path):
                pass


def test_study_dir_lock_released_after_context(tmp_path: Path):
    with _study_dir_lock(tmp_path):
        pass
    with _study_dir_lock(tmp_path):
        pass


def test_study_dir_lock_msvcrt_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import thesistester.study.execute as execute

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def locking(self, _fd: int, mode: int, nbytes: int) -> None:
            self.calls.append((mode, nbytes))

    fake = FakeMsvcrt()
    monkeypatch.setattr(execute, "fcntl", None)
    monkeypatch.setattr(execute, "msvcrt", fake)
    with execute._study_dir_lock(tmp_path):
        assert fake.calls == [(fake.LK_NBLCK, 1)]
    assert fake.calls == [(fake.LK_NBLCK, 1), (fake.LK_UNLCK, 1)]


def test_study_dir_lock_msvcrt_contention_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import errno

    import thesistester.study.execute as execute

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        def locking(self, _fd: int, mode: int, _nbytes: int) -> None:
            if mode == self.LK_NBLCK:
                raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(execute, "fcntl", None)
    monkeypatch.setattr(execute, "msvcrt", FakeMsvcrt())
    with pytest.raises(StudySpecError, match="holds the lock"):
        with execute._study_dir_lock(tmp_path):
            pass


def test_study_dir_lock_non_contention_oserror_is_not_phantom_holder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import errno

    import thesistester.study.execute as execute

    class FakeFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 8

        def flock(self, _fd: int, _flags: int) -> None:
            raise OSError(errno.ENOSYS, "Function not implemented")

    monkeypatch.setattr(execute, "fcntl", FakeFcntl())
    monkeypatch.setattr(execute, "msvcrt", None)
    with pytest.raises(StudySpecError, match="Unable to acquire exclusive study lock"):
        with execute._study_dir_lock(tmp_path):
            pass


def test_study_dir_lock_msvcrt_non_contention_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import errno

    import thesistester.study.execute as execute

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        def locking(self, _fd: int, mode: int, _nbytes: int) -> None:
            if mode == self.LK_NBLCK:
                raise OSError(errno.EINVAL, "Invalid argument")

    monkeypatch.setattr(execute, "fcntl", None)
    monkeypatch.setattr(execute, "msvcrt", FakeMsvcrt())
    with pytest.raises(StudySpecError, match="Unable to acquire exclusive study lock"):
        with execute._study_dir_lock(tmp_path):
            pass


def test_study_dir_lock_unavailable_without_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import thesistester.study.execute as execute

    monkeypatch.setattr(execute, "fcntl", None)
    monkeypatch.setattr(execute, "msvcrt", None)
    with pytest.raises(StudySpecError, match="unavailable"):
        with execute._study_dir_lock(tmp_path):
            pass


def test_study_package_imports_when_fcntl_missing():
    """Windows CPython has no fcntl; Studies page imports viewer via package init."""
    script = (
        "import builtins, sys\n"
        "_real = builtins.__import__\n"
        "def _import(name, globals=None, locals=None, fromlist=(), level=0):\n"
        "    if name == 'fcntl':\n"
        "        raise ImportError(\"No module named 'fcntl'\")\n"
        "    return _real(name, globals, locals, fromlist, level)\n"
        "builtins.__import__ = _import\n"
        "sys.modules.pop('fcntl', None)\n"
        "from thesistester.study.viewer import load_study_view, StudyViewerError\n"
        "from thesistester.study.execute import run_study\n"
        "print('import-ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "import-ok" in result.stdout


def test_failed_cell_error_lines_dedupes_and_caps():
    from thesistester.study.cli_study import failed_cell_error_lines

    cells = {
        "a": {"status": "failed", "error": "DataValidationError: missing columns"},
        "b": {"status": "ok", "error": None},
        "c": {"status": "failed", "error": "DataValidationError: missing columns"},
        "d": {"status": "failed", "error": "FileNotFoundError: bars.csv"},
        "e": {"status": "failed", "error": "ValueError: boom"},
    }
    lines = failed_cell_error_lines(cells, ["a", "b", "c", "d", "e"], max_unique=2)
    assert lines[0] == "Failed cell errors (unique):"
    assert lines[1].startswith("  a: DataValidationError: missing columns")
    assert lines[2].startswith("  d: FileNotFoundError: bars.csv")
    assert lines[3] == "  … +1 more unique error(s) in study.ledger.json"
    assert failed_cell_error_lines(cells, ["b"]) == []

    six = {name: {"status": "failed", "error": f"err-{name}"} for name in "abcdef"}
    default_lines = failed_cell_error_lines(six, list("abcdef"))
    examples = [
        line for line in default_lines if line.startswith("  ") and not line.startswith("  …")
    ]
    assert len(examples) == 5
    assert default_lines[-1] == "  … +1 more unique error(s) in study.ledger.json"


def _trades_df(*, directions: list[str], r_values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"direction": directions, "r_multiple": r_values})


def test_direction_index_fields_mixed_and_long_only():
    mixed = direction_index_fields(
        _trades_df(directions=["long", "short"], r_values=[1.0, -0.5]),
        trade_count=2,
        collision={"candidate_pairs": 3, "resolved_long": 2},
    )
    assert mixed["directional_integrity"] == "mixed"
    assert mixed["long_trade_count"] == 1
    assert mixed["short_trade_count"] == 1
    assert mixed["long_share"] == pytest.approx(0.5)
    assert mixed["collision_pairs"] == 3
    assert mixed["collision_resolved_long"] == 2

    long_only = direction_index_fields(
        _trades_df(directions=["long", "long"], r_values=[1.0, 0.5]),
        trade_count=2,
    )
    assert long_only["directional_integrity"] == "long_only"
    assert long_only["short_trade_count"] == 0
    assert long_only["long_share"] == pytest.approx(1.0)
    assert long_only["collision_pairs"] is None

    empty = direction_index_fields(pd.DataFrame(), trade_count=0)
    assert empty["directional_integrity"] == "empty"
    assert empty["long_share"] is None


def test_failed_index_row_seeds_da_keys_as_none():
    row = _failed_index_row("cell_x")
    for key in DA_DIRECTION_INDEX_KEYS:
        assert key in row
        assert row[key] is None
    assert row["run_name"] == "cell_x"


def test_execute_study_cell_attaches_direction_split(monkeypatch):
    trades = _trades_df(directions=["long", "short", "long"], r_values=[1.0, -0.5, 0.25])
    state = {
        "dataset_id": "ds-test",
        "instrument": "ES",
        "execution_origin": "study",
        "cache_provenance": {"outcome": "miss"},
        "trade_summary": {
            "trade_count": 3,
            "expectancy_r": 0.25,
            "total_r": 0.75,
            "max_drawdown_r": -0.5,
            "profit_factor": 1.5,
            "win_rate": 0.6,
        },
        "trades": trades,
        "direction_collision_diagnostic": {
            "candidate_pairs": 2,
            "resolved_long": 1,
        },
        "best_grid_result": {},
        "validation_summary": {},
        "walk_forward_summary": {},
    }
    monkeypatch.setattr("thesistester.study.execute.run_experiment", lambda *_a, **_k: state)
    monkeypatch.setattr(
        "thesistester.study.execute.build_research_bundle",
        lambda _state: _fake_bundle_bytes("cell_mixed"),
    )
    payload = execute_study_cell(({"name": "cell_mixed"}, "."))
    assert payload["status"] == "ok"
    row = payload["index_row"]
    assert row["directional_integrity"] == "mixed"
    assert row["long_trade_count"] == 2
    assert row["short_trade_count"] == 1
    assert row["collision_pairs"] == 2
    assert row["collision_resolved_long"] == 1
    assert "bundle_path" not in row
    assert (
        tuple(
            build_index_row_from_state(
                name="cell_mixed", state=state, bundle=_fake_bundle_bytes("cell_mixed")
            ).keys()
        )
        == R18_INDEX_METRIC_KEYS
    )


def test_execute_study_cell_long_only_state(monkeypatch):
    trades = _trades_df(directions=["long", "long"], r_values=[0.2, -0.1])
    state = {
        "dataset_id": "ds-test",
        "instrument": "ES",
        "execution_origin": "study",
        "cache_provenance": {"outcome": "miss"},
        "trade_summary": {
            "trade_count": 2,
            "expectancy_r": 0.05,
            "total_r": 0.1,
            "max_drawdown_r": -0.1,
            "profit_factor": 1.1,
            "win_rate": 0.5,
        },
        "trades": trades,
        "best_grid_result": {},
        "validation_summary": {},
        "walk_forward_summary": {},
    }
    monkeypatch.setattr("thesistester.study.execute.run_experiment", lambda *_a, **_k: state)
    monkeypatch.setattr(
        "thesistester.study.execute.build_research_bundle",
        lambda _state: _fake_bundle_bytes("cell_long"),
    )
    row = execute_study_cell(({"name": "cell_long"}, "."))["index_row"]
    assert row["directional_integrity"] == "long_only"
    assert row["short_trade_count"] == 0
    assert row["collision_pairs"] is None


def _zip_with_trades(trades: pd.DataFrame) -> bytes:
    parquet_buf = io.BytesIO()
    trades.to_parquet(parquet_buf, index=False)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("trades.parquet", parquet_buf.getvalue())
        archive.writestr(
            "trade_summary.json",
            json.dumps({"trade_summary": {"trade_count": int(len(trades))}}),
        )
    return buffer.getvalue()


def test_rebuild_direction_index_fills_only_da_keys(tmp_path: Path):
    study_dir = tmp_path / "study_out"
    study_dir.mkdir()
    trades = _trades_df(directions=["long", "long", "short"], r_values=[1.0, 0.5, -0.2])
    (study_dir / "a.research.zip").write_bytes(_zip_with_trades(trades))
    prior = pd.DataFrame(
        [
            {
                "run_name": "a",
                "bundle_hash": "abc",
                "dataset_id": "ds",
                "instrument": "ES",
                "execution_origin": "study",
                "cache_outcome": "miss",
                "trade_count": 3,
                "expectancy_r": 0.1,
                "total_r": 0.3,
                "max_drawdown_r": 1.0,
                "profit_factor": 1.2,
                "win_rate": 0.5,
                "bundle_path": "a.research.zip",
                "status": "ok",
            }
        ]
    )
    prior.to_csv(study_dir / "results_index.csv", index=False)
    before = pd.read_csv(study_dir / "results_index.csv")
    before_cols = list(before.columns)
    rebuilt = pd.read_csv(rebuild_direction_index(study_dir))
    assert rebuilt.loc[:, before_cols].to_csv(index=False) == before.to_csv(index=False)
    assert rebuilt.iloc[0]["directional_integrity"] == "mixed"
    assert int(rebuilt.iloc[0]["long_trade_count"]) == 2
    assert int(rebuilt.iloc[0]["short_trade_count"]) == 1
    assert pd.isna(rebuilt.iloc[0]["collision_pairs"])
    again = pd.read_csv(rebuild_direction_index(study_dir))
    assert again.to_csv(index=False) == rebuilt.to_csv(index=False)
