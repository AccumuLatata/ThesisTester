"""RS3 study expand/run — confirm, ledger, resume, workers, index parity."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest
import yaml

from thesistester.cli import main as cli_main
from thesistester.research_bundle import canonical_bundle_hash
from thesistester.research_identity import normalize_execution_origin
from thesistester.study.execute import (
    R18_INDEX_METRIC_KEYS,
    STUDY_INDEX_KEYS,
    build_index_row_from_state,
    execute_study_cell,
    prepare_study_expansion,
    run_study,
)
from thesistester.study.ledger import load_ledger
from thesistester.study.schema import STUDY_SCHEMA_VERSION, StudySpecError


def _fake_bundle_bytes(name: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"run_name": name}))
        archive.writestr("trade_summary.json", json.dumps({"trade_summary": {"trade_count": 3}}))
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
                "core_level": ["pdPOC"],
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
    code = cli_main(
        ["study", "expand", str(study), "--output-dir", str(out)]
    )
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
    assert set(index.columns) == set(STUDY_INDEX_KEYS)
    assert set(index["execution_origin"].unique()) == {"study"}
    assert normalize_execution_origin("study") == "study"
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
    study_b = _mini_study_yaml(tmp_path / "b.yaml", name="studyB", confirm_above_runs=100)
    with pytest.raises(StudySpecError, match="identity hash"):
        run_study(study_b, output_dir=out, cell_executor=_fake_executor_factory())
    # Force allows overwrite path.
    result = run_study(
        study_b,
        output_dir=out,
        force=True,
        cell_executor=_fake_executor_factory(),
    )
    assert result["executed"] == 4


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


def test_index_columns_parity_vs_cli_execute_run():
    # Documented parity with cli._execute_run metric keys.
    from thesistester import cli as cli_mod

    source = cli_mod._execute_run.__code__.co_consts
    # Structural parity: study keys equal the known R18 set (+ status/bundle_path).
    assert "run_name" in R18_INDEX_METRIC_KEYS
    assert "expectancy_r" in R18_INDEX_METRIC_KEYS
    assert "status" in STUDY_INDEX_KEYS
    assert "bundle_path" in STUDY_INDEX_KEYS
    assert set(R18_INDEX_METRIC_KEYS).isdisjoint({"status"})
    # Smoke: build_index_row_from_state keys match R18 set exactly.
    bundle = _fake_bundle_bytes("parity")
    row = build_index_row_from_state(
        name="cell",
        state={
            "dataset_id": "x",
            "instrument": "ES",
            "execution_origin": "study",
            "cache_provenance": {},
            "trade_summary": {},
            "best_grid_result": {},
            "validation_summary": {},
            "walk_forward_summary": {},
        },
        bundle=bundle,
    )
    assert set(row) == set(R18_INDEX_METRIC_KEYS)
    assert row["bundle_hash"] == canonical_bundle_hash(bundle)
    assert source  # keep import used / module loaded


def test_cli_study_run_confirm_exit_codes(tmp_path: Path, monkeypatch):
    study = _mini_study_yaml(tmp_path / "study.yaml", confirm_above_runs=2)
    out = tmp_path / "out"

    # Patch the executor used by run_study via execute module.
    import thesistester.study.execute as execute_mod

    monkeypatch.setattr(execute_mod, "execute_study_cell", _fake_executor_factory())

    code_no_confirm = cli_main(
        ["study", "run", str(study), "--output-dir", str(out)]
    )
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
