"""Program B operator packet — inventory, expand locks, validator fail-closed."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import yaml

from thesistester.levels.catalog import STATIC_STUDY_LEVEL_NAMES
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
    assert len(confirms) == 22
    assert "dVWAP" not in confirms
    leftover = closed - anchors - confirms
    assert leftover == {"POC_rolling_30min"}


def test_program_b_manifest_validates_without_false_ok():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(PROGRAM_B)
    assert failures == []
    assert n_studies == 26
    assert n_cells == 1151
    assert len(ok_lines) == 26
    assert all(line.startswith("ok ") for line in ok_lines)


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
    failures = validate.validate_study_file(drifted, {"file": drifted.name, "cells": 1, "min_valid": 1})
    assert any("dVWAP must not appear in partner_levels" in item for item in failures)

    spec["study"]["factors"]["partner_levels"] = [["SMA_50_5min"]]
    spec["study"]["mode_rules"]["anchor_rules"]["confluence_rules"]["from_partners"] = "optional"
    optional = tmp_path / "smoke_optional.yaml"
    optional.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(optional, {"file": optional.name, "cells": 1, "min_valid": 1})
    assert any("from_partners" in item for item in failures)
