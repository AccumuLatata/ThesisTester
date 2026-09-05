"""Program B operator packet — inventory, expand locks, validator fail-closed."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml

from thesistester.levels.catalog import PRIOR_PROFILE_LEVEL_NAMES, STATIC_STUDY_LEVEL_NAMES
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.study.schema import closed_level_token_set

PROGRAM_B = Path("examples/studies/program_b")
PROGRAM_B_RUN2 = Path("examples/studies/program_b_run2")


def _load_module(name: str):
    path = PROGRAM_B / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"program_b_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validator():
    return _load_module("validate_program_b_yaml")


def _generate():
    return _load_module("generate_program_b_yaml")


def test_program_b_inventory_matches_default_closed_set():
    gen = _generate()
    validate = _validator()
    validate.assert_inventory_matches_catalog(gen)
    closed = closed_level_token_set(DEFAULT_LEVELS_SETTINGS)
    anchors = STATIC_STUDY_LEVEL_NAMES | {"prev30mVWAP"}
    confirms = {row[0] for family in gen.CONFIRMS.values() for row in family}
    assert set(gen.ALL_ANCHORS) == anchors
    assert len(gen.ALL_ANCHORS) == 50
    assert set(gen.VA_ANCHORS) == set(PRIOR_PROFILE_LEVEL_NAMES)
    assert len(gen.FIFTEEN_S_ANCHORS) == 41
    assert set(gen.FIFTEEN_S_ANCHORS).isdisjoint(gen.VA_ANCHORS)
    assert set(gen.FIFTEEN_S_ANCHORS) | set(gen.VA_ANCHORS) == set(gen.ALL_ANCHORS)
    assert len(confirms) == 22
    assert "dVWAP" not in confirms
    leftover = closed - anchors - confirms
    assert leftover == {"POC_rolling_30min"}


def test_program_b_manifest_validates_without_false_ok():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(PROGRAM_B)
    assert failures == []
    assert n_studies == 23
    assert n_cells == 944
    assert len(ok_lines) == 23
    assert all(line.startswith("ok ") for line in ok_lines)


def test_program_b_va_manifest_validates_separately():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(
        PROGRAM_B, manifest_name="manifest_va.yaml"
    )
    assert failures == []
    assert n_studies == 4
    assert n_cells == 207
    assert len(ok_lines) == 4
    fifteen_s = yaml.safe_load((PROGRAM_B / "manifest.yaml").read_text(encoding="utf-8"))
    tick = yaml.safe_load((PROGRAM_B / "manifest_va.yaml").read_text(encoding="utf-8"))
    fifteen_files = {row["file"] for row in fifteen_s["studies"]}
    tick_files = {row["file"] for row in tick["studies"]}
    assert fifteen_files.isdisjoint(tick_files)
    assert fifteen_s["packet"] == "15s"
    assert tick["packet"] == "tick"


def test_program_b_w0_solo_excludes_va_tokens():
    spec = yaml.safe_load((PROGRAM_B / "progB_w0_solo.yaml").read_text(encoding="utf-8"))
    cores = spec["study"]["factors"]["core_level"]
    assert cores
    assert set(cores).isdisjoint(PRIOR_PROFILE_LEVEL_NAMES)
    assert "tick_paths" not in spec["study"]["dataset"]
    va = yaml.safe_load((PROGRAM_B / "progB_w0_va.yaml").read_text(encoding="utf-8"))
    gen = _generate()
    assert va["study"]["factors"]["core_level"] == list(gen.VA_ANCHORS)
    assert va["study"]["dataset"]["tick_paths"] == gen.VA_TICK_PATHS


def test_program_b_fifteen_s_yamls_omit_tick_paths():
    fifteen_s = yaml.safe_load((PROGRAM_B / "manifest.yaml").read_text(encoding="utf-8"))
    for row in fifteen_s["studies"]:
        spec = yaml.safe_load((PROGRAM_B / row["file"]).read_text(encoding="utf-8"))
        assert "tick_paths" not in spec["study"]["dataset"], row["file"]


def test_program_b_va_yamls_have_placeholder_tick_paths():
    gen = _generate()
    tick = yaml.safe_load((PROGRAM_B / "manifest_va.yaml").read_text(encoding="utf-8"))
    for row in tick["studies"]:
        spec = yaml.safe_load((PROGRAM_B / row["file"]).read_text(encoding="utf-8"))
        assert spec["study"]["dataset"]["tick_paths"] == gen.VA_TICK_PATHS, row["file"]
        cores = spec["study"]["factors"]["core_level"]
        assert cores
        assert set(cores) <= set(PRIOR_PROFILE_LEVEL_NAMES)


def test_program_b_validator_rejects_tick_paths_on_15s_yaml(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    spec["study"]["dataset"]["tick_paths"] = list(_generate().VA_TICK_PATHS)
    drifted = tmp_path / "progB_smoke_ONH_SMA50_5min.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted, {"file": drifted.name, "cells": 1, "min_valid": 1}, packet="15s"
    )
    assert any("15s packet must omit tick_paths" in item for item in failures)


def test_program_b_validator_rejects_va_yaml_without_tick_paths(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_w0_va.yaml").read_text())
    spec["study"]["dataset"].pop("tick_paths", None)
    drifted = tmp_path / "progB_w0_va.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted, {"file": drifted.name, "cells": 9, "min_valid": 0}, packet="tick"
    )
    assert any("VA requires ticks" in item or "tick_paths" in item for item in failures)


def test_program_b_validator_rejects_va_core_on_15s_packet(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    spec["study"]["factors"]["core_level"] = ["pdPOC"]
    spec["study"]["dataset"]["tick_paths"] = list(_generate().VA_TICK_PATHS)
    drifted = tmp_path / "progB_smoke_ONH_SMA50_5min.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted, {"file": drifted.name, "cells": 1, "min_valid": 1}, packet="15s"
    )
    assert any("15s packet must omit tick_paths" in item for item in failures)
    assert any("cannot name VA cores" in item for item in failures)


def test_program_b_validator_rejects_timezone_and_omits_ok(tmp_path):
    validate = _validator()
    copied = tmp_path / "program_b"
    shutil.copytree(PROGRAM_B, copied)
    target = copied / "progB_smoke_ONH_SMA50_5min.yaml"
    target.write_text(
        target.read_text(encoding="utf-8").replace("America/New_York", "America/Chicago"),
        encoding="utf-8",
    )
    ok_lines, failures, _, _ = validate.validate_manifest(copied)
    assert any("backtest locks drifted" in item for item in failures)
    assert not any("progB_smoke_ONH_SMA50_5min.yaml" in line for line in ok_lines)
    assert any("progB_w0_solo.yaml" in line for line in ok_lines)


def test_program_b_validator_rejects_dvwap_partner_and_optional_from_partners(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    spec["study"]["factors"]["partner_levels"] = [["dVWAP"]]
    drifted = tmp_path / "smoke_dvwap.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted, {"file": drifted.name, "cells": 1, "min_valid": 1}
    )
    assert any("dVWAP must not appear in partner_levels" in item for item in failures)

    spec["study"]["factors"]["partner_levels"] = [["SMA_50_5min"]]
    spec["study"]["mode_rules"]["anchor_rules"]["confluence_rules"]["from_partners"] = "optional"
    optional = tmp_path / "smoke_optional.yaml"
    optional.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        optional, {"file": optional.name, "cells": 1, "min_valid": 1}
    )
    assert any("from_partners" in item for item in failures)


def test_program_b_run2_manifest_expands_944_with_run2_locks():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(
        PROGRAM_B_RUN2, manifest_name="manifest.yaml"
    )
    assert failures == []
    assert n_studies == 23
    assert n_cells == 944
    assert len(ok_lines) == 23
    manifest = yaml.safe_load((PROGRAM_B_RUN2 / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["packet"] == "15s"
    assert manifest["locks"] == "run2"
    for row in manifest["studies"]:
        spec = yaml.safe_load((PROGRAM_B_RUN2 / row["file"]).read_text(encoding="utf-8"))
        study = spec["study"]
        assert study["factors"]["trigger"] == ["fade"], row["file"]
        assert study["constants"]["trigger_params"]["require_close_confirmation"] is False
        assert study["constants"]["backtest"]["same_bar_opposite_direction"] == "raise"
        baseline = study["report"]["random_baseline"]
        assert baseline["enabled"] is True
        assert baseline["n_replicas"] == 50
        assert study["name"].startswith("progB_r2_")
        assert "tick_paths" not in study["dataset"]


def test_program_b_run1_yamls_keep_touch_legacy_and_no_null():
    spec = yaml.safe_load((PROGRAM_B / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    assert spec["study"]["factors"]["trigger"] == ["touch"]
    assert "same_bar_opposite_direction" not in spec["study"]["constants"]["backtest"]
    assert "random_baseline" not in spec["study"]["report"]
    assert spec["study"]["constants"]["trigger_params"] == {}


def test_program_b_default_generate_keeps_run1_locks(tmp_path):
    gen = _generate()
    gen.generate_packet(tmp_path)
    spec = yaml.safe_load((tmp_path / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    assert spec["study"]["name"] == "progB_smoke_ONH_SMA50_5min"
    assert spec["study"]["factors"]["trigger"] == ["touch"]
    assert "same_bar_opposite_direction" not in spec["study"]["constants"]["backtest"]
    assert "random_baseline" not in spec["study"]["report"]
    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text())
    assert "locks" not in manifest
    assert manifest["total_cells"] == 944


def test_program_b_validator_accepts_manifest_path():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(
        PROGRAM_B_RUN2, manifest_name="manifest.yaml"
    )
    assert failures == []
    assert n_studies == 23
    assert n_cells == 944
    assert all(line.startswith("ok ") for line in ok_lines)


def test_program_b_validator_rejects_run2_yaml_under_run1_locks(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B_RUN2 / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    drifted = tmp_path / "progB_smoke_ONH_SMA50_5min.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted, {"file": drifted.name, "cells": 1, "min_valid": 1}, packet="15s", locks="run1"
    )
    assert any("trigger drifted" in item for item in failures)


def test_program_b_fade_cli_defaults_emit_valid_run2_packet(tmp_path):
    gen = _generate()
    gen.main(["--trigger", "fade", "--output-dir", str(tmp_path)])
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(tmp_path)
    assert failures == []
    assert n_studies == 23
    assert n_cells == 944
    assert len(ok_lines) == 23
    spec = yaml.safe_load((tmp_path / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    assert spec["study"]["factors"]["trigger"] == ["fade"]
    assert spec["study"]["constants"]["backtest"]["same_bar_opposite_direction"] == "raise"
    assert spec["study"]["report"]["random_baseline"]["n_replicas"] == 50
    assert spec["study"]["name"].startswith("progB_r2_")
    assert not (tmp_path / "manifest_va.yaml").exists()
    assert not (tmp_path / "progB_w0_va.yaml").exists()
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Run 2" in readme


def test_program_b_fade_cli_refuses_run1_output_dir():
    gen = _generate()
    with pytest.raises(SystemExit):
        gen.main(["--trigger", "fade"])
    spec = yaml.safe_load((PROGRAM_B / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    assert spec["study"]["factors"]["trigger"] == ["touch"]
    assert spec["study"]["name"] == "progB_smoke_ONH_SMA50_5min"


def test_program_b_validator_rejects_run2_name_without_r2_prefix(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B_RUN2 / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    spec["study"]["name"] = "progB_smoke_ONH_SMA50_5min"
    spec["study"]["output_dir"] = "results/studies/progB_smoke_ONH_SMA50_5min"
    drifted = tmp_path / "progB_smoke_ONH_SMA50_5min.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted, {"file": drifted.name, "cells": 1, "min_valid": 1}, packet="15s", locks="run2"
    )
    assert any("progB_r2_" in item for item in failures)


def test_program_b_validator_rejects_long_only_direction(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    spec["study"]["constants"]["direction"] = "long"
    drifted = tmp_path / "progB_smoke_ONH_SMA50_5min.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted, {"file": drifted.name, "cells": 1, "min_valid": 1}, packet="15s"
    )
    assert any("direction must be both" in item for item in failures)


def test_program_b_validator_main_accepts_run2_manifest_path(capsys):
    validate = _validator()
    validate.main([str(PROGRAM_B_RUN2 / "manifest.yaml")])
    captured = capsys.readouterr()
    assert "ok 23 studies / 944 cells" in captured.out
