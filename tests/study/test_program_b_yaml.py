"""Program B operator packet — inventory, expand locks, validator fail-closed."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import yaml

from thesistester.levels.catalog import PRIOR_PROFILE_LEVEL_NAMES, STATIC_STUDY_LEVEL_NAMES
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.study.schema import closed_level_token_set

PROGRAM_B = Path("examples/studies/program_b")


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
    va = yaml.safe_load((PROGRAM_B / "progB_w0_va.yaml").read_text(encoding="utf-8"))
    assert va["study"]["factors"]["core_level"] == list(_generate().VA_ANCHORS)


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
