"""AH2 probes: Study dataset path identity (C2 + H2).

P1–P3 fail on cwd-first / unpinned expand when both files exist and pass
once expand pins the spec-parent file. See
``docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md`` §6.2.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from thesistester.cli import EXPERIMENT_SCHEMA_VERSION
from thesistester.study.execute import prepare_study_expansion
from thesistester.study.expand import (
    dataset_path_search_roots,
    expand_study,
    expand_study_to_directory,
)
from thesistester.study.launch import build_launch_plan
from thesistester.study.preview import example_study_spec_path
from thesistester.study.promote import promote_study
from thesistester.study.schema import STUDY_SCHEMA_VERSION
from test_study_report import _write_report_fixture

_CSV_HEADER = "ts,open,high,low,close,volume\n"


def _write_csv(path: Path, tag: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{_CSV_HEADER}# {tag}\n", encoding="utf-8")
    return path


def _one_cell_spec(
    *,
    dataset_path: str = "data/a.csv",
    subtimeframe_path: str | None = None,
) -> dict:
    dataset: dict[str, object] = {
        "path": dataset_path,
        "instrument": "ES",
        "source_timezone": "America/New_York",
    }
    if subtimeframe_path is not None:
        dataset["subtimeframe_path"] = subtimeframe_path
    return {
        "schema_version": STUDY_SCHEMA_VERSION,
        "study": {
            "name": "ah2_pin",
            "dataset": dataset,
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
                "partner_levels": [["SMA_50_1min"]],
                "confluence_mode": ["global_cluster"],
                "trigger": ["touch"],
                "trigger_timeframe": ["base"],
            },
            "mode_rules": {
                "global_cluster": {
                    "selected_levels": ["${core_level}", "${partner_levels...}"],
                },
            },
            "report": {
                "primary_metric": "expectancy_r",
                "min_trades": 30,
            },
        },
    }


def _api_style_dataset_path(raw: str, *, base_directory: Path) -> Path:
    """Mirror ``api.run_experiment``: absolute paths skip ``base_directory`` join."""
    path = Path(raw)
    if not path.is_absolute():
        path = base_directory / path
    return path


def test_ah2_p1_expand_pins_spec_parent_not_cwd(tmp_path: Path, monkeypatch):
    spec_home = tmp_path / "spec_home"
    cwd_home = tmp_path / "cwd_home"
    out = tmp_path / "out"
    spec_csv = _write_csv(spec_home / "data" / "a.csv", "SPEC")
    cwd_csv = _write_csv(cwd_home / "data" / "a.csv", "CWD")
    spec_sub = _write_csv(spec_home / "data" / "a_15s.csv", "SPEC15")
    _write_csv(cwd_home / "data" / "a_15s.csv", "CWD15")
    spec = _one_cell_spec(subtimeframe_path="data/a_15s.csv")
    spec_path = spec_home / "study.yaml"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    monkeypatch.chdir(cwd_home)

    _loaded, expansion, out_dir, base = prepare_study_expansion(spec_path, output_dir=out)
    assert base == spec_home.resolve()
    run_dataset = expansion.experiment["runs"][0]["dataset"]
    assert Path(run_dataset["path"]) == spec_csv.resolve()
    assert Path(run_dataset["subtimeframe_path"]) == spec_sub.resolve()
    resolved = _api_style_dataset_path(run_dataset["path"], base_directory=out_dir)
    assert resolved.read_bytes() == spec_csv.read_bytes()
    assert resolved.read_bytes() != cwd_csv.read_bytes()

    written = yaml.safe_load((out / "experiment.yaml").read_text(encoding="utf-8"))
    assert Path(written["runs"][0]["dataset"]["path"]) == spec_csv.resolve()
    copied = yaml.safe_load((out / "study.spec.yaml").read_text(encoding="utf-8"))
    assert Path(copied["study"]["dataset"]["path"]) == spec_csv.resolve()
    payload = json.loads((out / "study.expansion.json").read_text(encoding="utf-8"))
    assert payload["source_spec_parent"] == str(spec_home.resolve())
    unpinned = expand_study(spec)
    assert expansion.study_identity_hash == unpinned.study_identity_hash
    assert unpinned.experiment["runs"][0]["dataset"]["path"] == "data/a.csv"


def test_ah2_p2_promote_prefers_spec_parent_over_cwd(tmp_path: Path, monkeypatch):
    study_dir = _write_report_fixture(tmp_path)
    spec_home = tmp_path / "orig_spec"
    cwd_home = tmp_path / "cwd_home"
    spec_csv = _write_csv(spec_home / "data" / "a.csv", "SPEC")
    cwd_csv = _write_csv(cwd_home / "data" / "a.csv", "CWD")
    spec_path = study_dir / "study.spec.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    spec["study"]["dataset"]["path"] = "data/a.csv"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    expansion_path = study_dir / "study.expansion.json"
    payload = json.loads(expansion_path.read_text(encoding="utf-8"))
    payload["source_spec_parent"] = str(spec_home.resolve())
    expansion_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    monkeypatch.chdir(cwd_home)

    draft_path = tmp_path / "drafts" / "draft.yaml"
    promote_study(study_dir, output=draft_path, top_n=1)
    draft = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
    pinned = Path(draft["study"]["dataset"]["path"])
    assert pinned == spec_csv.resolve()
    assert pinned.read_bytes() == spec_csv.read_bytes()
    assert pinned.read_bytes() != cwd_csv.read_bytes()


def test_ah2_p3_launch_prefers_spec_parent_over_cwd(tmp_path: Path, monkeypatch):
    spec_home = tmp_path / "spec_home"
    cwd_home = tmp_path / "cwd_home"
    spec_csv = _write_csv(spec_home / "data" / "es_15s.csv", "SPEC")
    cwd_csv = _write_csv(cwd_home / "data" / "es_15s.csv", "CWD")
    yaml_text = example_study_spec_path().read_text(encoding="utf-8")
    monkeypatch.chdir(cwd_home)
    plan = build_launch_plan(
        yaml_text,
        cached_yaml=yaml_text,
        expanded=True,
        run_count=40,
        output_dir_raw=str(tmp_path / "out" / "study1"),
        roots=(tmp_path,),
        source_spec_parent=spec_home,
    )
    pinned = Path(plan.pinned_spec["study"]["dataset"]["path"])
    assert pinned == spec_csv.resolve()
    assert pinned.read_bytes() == spec_csv.read_bytes()
    assert pinned.read_bytes() != cwd_csv.read_bytes()


def test_ah2_p4_missing_spec_parent_file_stays_relative(tmp_path: Path, monkeypatch):
    spec_home = tmp_path / "spec_home"
    cwd_home = tmp_path / "cwd_home"
    spec_home.mkdir()
    cwd_home.mkdir()
    spec = _one_cell_spec(dataset_path="data/missing.csv")
    monkeypatch.chdir(cwd_home)
    expansion = expand_study(spec, source_spec_parent=spec_home)
    assert expansion.experiment["runs"][0]["dataset"]["path"] == "data/missing.csv"
    out = tmp_path / "out"
    expand_study_to_directory(spec, out, source_spec_parent=spec_home)
    copied = yaml.safe_load((out / "study.spec.yaml").read_text(encoding="utf-8"))
    assert copied["study"]["dataset"]["path"] == "data/missing.csv"
    assert not (cwd_home / "data" / "missing.csv").exists()
    assert not (spec_home / "data" / "missing.csv").exists()
    payload = json.loads((out / "study.expansion.json").read_text(encoding="utf-8"))
    assert payload["source_spec_parent"] == str(spec_home.resolve())


def test_ah2_p5_unpinned_write_keeps_v1_schema(tmp_path: Path):
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "study"
    raw = yaml.safe_load((fixtures / "golden_study.yaml").read_text(encoding="utf-8"))
    expansion = expand_study_to_directory(raw, tmp_path)
    assert expansion.experiment["schema_version"] == EXPERIMENT_SCHEMA_VERSION
    assert EXPERIMENT_SCHEMA_VERSION == 1
    payload = json.loads((tmp_path / "study.expansion.json").read_text(encoding="utf-8"))
    assert "source_spec_parent" not in payload
    copied = yaml.safe_load((tmp_path / "study.spec.yaml").read_text(encoding="utf-8"))
    assert copied["schema_version"] == STUDY_SCHEMA_VERSION
    assert copied["study"]["dataset"]["path"] == "data/es_1m.csv"


def test_ah2_search_roots_keep_study_output_before_draft_when_cwd_is_output(
    tmp_path: Path, monkeypatch
):
    spec_home = tmp_path / "orig_spec"
    study_out = tmp_path / "study_out"
    drafts = tmp_path / "drafts"
    spec_home.mkdir()
    study_out.mkdir()
    drafts.mkdir()
    monkeypatch.chdir(study_out)
    roots = dataset_path_search_roots(
        source_spec_parent=spec_home,
        extra_roots=(study_out, drafts),
        cwd=study_out,
    )
    assert roots == [spec_home.resolve(), study_out.resolve(), drafts.resolve()]


def test_ah2_launch_without_parent_keeps_cwd_root_ahead_of_store(tmp_path: Path, monkeypatch):
    cwd_home = tmp_path / "cwd_home"
    store_home = tmp_path / "store_home"
    cwd_csv = _write_csv(cwd_home / "data" / "es_15s.csv", "CWD")
    store_csv = _write_csv(store_home / "data" / "es_15s.csv", "STORE")
    yaml_text = example_study_spec_path().read_text(encoding="utf-8")
    monkeypatch.chdir(cwd_home)
    plan = build_launch_plan(
        yaml_text,
        cached_yaml=yaml_text,
        expanded=True,
        run_count=40,
        output_dir_raw=str(cwd_home / "out" / "study1"),
        roots=(cwd_home, store_home),
    )
    pinned = Path(plan.pinned_spec["study"]["dataset"]["path"])
    assert pinned == cwd_csv.resolve()
    assert pinned.read_bytes() == cwd_csv.read_bytes()
    assert pinned.read_bytes() != store_csv.read_bytes()


def test_ah2_blank_source_spec_parent_does_not_pin_cwd(tmp_path: Path, monkeypatch):
    cwd_home = tmp_path / "cwd_home"
    _write_csv(cwd_home / "data" / "a.csv", "CWD")
    spec = _one_cell_spec()
    monkeypatch.chdir(cwd_home)
    expansion = expand_study(spec, source_spec_parent="")
    assert expansion.experiment["runs"][0]["dataset"]["path"] == "data/a.csv"
    out = tmp_path / "out"
    expand_study_to_directory(spec, out, source_spec_parent="   ")
    payload = json.loads((out / "study.expansion.json").read_text(encoding="utf-8"))
    assert "source_spec_parent" not in payload
    copied = yaml.safe_load((out / "study.spec.yaml").read_text(encoding="utf-8"))
    assert copied["study"]["dataset"]["path"] == "data/a.csv"


def test_ah2_promote_from_study_dir_prefers_output_over_draft(tmp_path: Path, monkeypatch):
    study_dir = _write_report_fixture(tmp_path)
    output_csv = _write_csv(study_dir / "data" / "a.csv", "OUTPUT")
    draft_csv = _write_csv(tmp_path / "drafts" / "data" / "a.csv", "DRAFT")
    spec_path = study_dir / "study.spec.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    spec["study"]["dataset"]["path"] = "data/a.csv"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    monkeypatch.chdir(study_dir)
    draft_path = tmp_path / "drafts" / "draft.yaml"
    promote_study(study_dir, output=draft_path, top_n=1)
    draft = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
    pinned = Path(draft["study"]["dataset"]["path"])
    assert pinned == output_csv.resolve()
    assert pinned.read_bytes() == output_csv.read_bytes()
    assert pinned.read_bytes() != draft_csv.read_bytes()
