"""Program B operator packet — inventory, expand locks, validator fail-closed."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml

from thesistester.levels.catalog import PRIOR_PROFILE_LEVEL_NAMES, STATIC_STUDY_LEVEL_NAMES
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.study.apoc_provenance import (
    WAVE7_TICK_PROVENANCE,
    is_wave7_study_file,
)
from thesistester.study.expand import expand_study_to_directory, study_identity_hash
from thesistester.study.schema import (
    StudySpecError,
    closed_level_token_set,
    normalize_study_spec,
    validate_study_spec,
)

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
    assert set(gen.APOC_ANCHORS) == {"APOC", "pAPOC"}
    assert len(gen.FIFTEEN_S_ANCHORS) == 39
    assert set(gen.FIFTEEN_S_ANCHORS).isdisjoint(gen.TICK_GATED_SET)
    assert set(gen.FIFTEEN_S_ANCHORS) | set(gen.TICK_GATED_SET) == set(gen.ALL_ANCHORS)
    assert set(gen.TICK_GATED_ANCHORS) == set(gen.VA_ANCHORS) | set(gen.APOC_ANCHORS)
    assert len(confirms) == 22
    assert "dVWAP" not in confirms
    leftover = closed - anchors - confirms
    assert leftover == {"POC_rolling_30min"}


def test_program_b_manifest_validates_without_false_ok():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(PROGRAM_B)
    assert failures == []
    assert n_studies == 20
    assert n_cells == 898
    assert len(ok_lines) == 20
    assert all(line.startswith("ok ") for line in ok_lines)


def test_program_b_tick_manifest_validates_separately():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(
        PROGRAM_B, manifest_name="manifest_tick.yaml"
    )
    assert failures == []
    assert n_studies == 8
    assert n_cells == 253
    assert len(ok_lines) == 8
    fifteen_s = yaml.safe_load((PROGRAM_B / "manifest.yaml").read_text(encoding="utf-8"))
    tick = yaml.safe_load((PROGRAM_B / "manifest_tick.yaml").read_text(encoding="utf-8"))
    fifteen_files = {row["file"] for row in fifteen_s["studies"]}
    tick_files = {row["file"] for row in tick["studies"]}
    assert fifteen_files.isdisjoint(tick_files)
    assert fifteen_s["packet"] == "15s"
    assert tick["packet"] == "tick"
    assert not (PROGRAM_B / "manifest_va.yaml").exists()


def test_program_b_validator_rejects_stale_manifest_va(tmp_path):
    validate = _validator()
    copied = tmp_path / "program_b"
    shutil.copytree(PROGRAM_B, copied)
    (copied / "manifest_va.yaml").write_text("packet: va\n", encoding="utf-8")
    _, failures, _, _ = validate.validate_manifest(copied, manifest_name="manifest_tick.yaml")
    assert any("manifest_va.yaml" in item and "stale live path" in item for item in failures)


def test_program_b_w0_solo_excludes_tick_gated_tokens():
    spec = yaml.safe_load((PROGRAM_B / "progB_w0_solo.yaml").read_text(encoding="utf-8"))
    cores = spec["study"]["factors"]["core_level"]
    gen = _generate()
    assert cores
    assert set(cores).isdisjoint(PRIOR_PROFILE_LEVEL_NAMES)
    assert set(cores).isdisjoint(gen.APOC_ANCHOR_SET)
    assert "tick_paths" not in spec["study"]["dataset"]
    assert spec["study"]["levels"]["apoc_enabled"] is False
    assert spec["study"]["levels"]["poc_windows"] == []
    va = yaml.safe_load((PROGRAM_B / "progB_w0_va.yaml").read_text(encoding="utf-8"))
    assert va["study"]["factors"]["core_level"] == list(gen.VA_ANCHORS)
    assert va["study"]["dataset"]["tick_paths"] == gen.TICK_PATHS
    apoc = yaml.safe_load((PROGRAM_B / "progB_w0_apoc.yaml").read_text(encoding="utf-8"))
    assert apoc["study"]["factors"]["core_level"] == list(gen.APOC_ANCHORS)
    assert apoc["study"]["dataset"]["tick_paths"] == gen.TICK_PATHS
    assert apoc["study"]["levels"]["apoc_enabled"] is True


def test_program_b_fifteen_s_packet_validates_without_ticks():
    for root in (PROGRAM_B, PROGRAM_B_RUN2):
        spec = yaml.safe_load((root / "progB_w0_solo.yaml").read_text(encoding="utf-8"))
        assert "APOC" not in spec["study"]["factors"]["core_level"]
        assert "pAPOC" not in spec["study"]["factors"]["core_level"]
        validate_study_spec(normalize_study_spec(spec))
        smoke = yaml.safe_load((root / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
        validate_study_spec(normalize_study_spec(smoke))


def test_program_b_fifteen_s_yamls_omit_tick_paths():
    fifteen_s = yaml.safe_load((PROGRAM_B / "manifest.yaml").read_text(encoding="utf-8"))
    for row in fifteen_s["studies"]:
        spec = yaml.safe_load((PROGRAM_B / row["file"]).read_text(encoding="utf-8"))
        assert "tick_paths" not in spec["study"]["dataset"], row["file"]


def test_program_b_tick_yamls_have_placeholder_tick_paths():
    gen = _generate()
    tick = yaml.safe_load((PROGRAM_B / "manifest_tick.yaml").read_text(encoding="utf-8"))
    for row in tick["studies"]:
        spec = yaml.safe_load((PROGRAM_B / row["file"]).read_text(encoding="utf-8"))
        assert spec["study"]["dataset"]["tick_paths"] == gen.TICK_PATHS, row["file"]
        cores = spec["study"]["factors"]["core_level"]
        assert cores
        assert set(cores) <= set(gen.TICK_GATED_SET)


def test_program_b_validator_rejects_tick_paths_on_15s_yaml(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    spec["study"]["dataset"]["tick_paths"] = list(_generate().TICK_PATHS)
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
    spec["study"]["dataset"]["tick_paths"] = list(_generate().TICK_PATHS)
    drifted = tmp_path / "progB_smoke_ONH_SMA50_5min.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted, {"file": drifted.name, "cells": 1, "min_valid": 1}, packet="15s"
    )
    assert any("15s packet must omit tick_paths" in item for item in failures)
    assert any("cannot name tick-gated cores" in item for item in failures)


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


def test_program_b_run2_manifest_expands_898_with_run2_locks():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(
        PROGRAM_B_RUN2, manifest_name="manifest.yaml"
    )
    assert failures == []
    assert n_studies == 20
    assert n_cells == 898
    assert len(ok_lines) == 20
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
    assert manifest["total_cells"] == 898


def test_program_b_validator_accepts_manifest_path():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(
        PROGRAM_B_RUN2, manifest_name="manifest.yaml"
    )
    assert failures == []
    assert n_studies == 20
    assert n_cells == 898
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
    assert n_studies == 20
    assert n_cells == 898
    assert len(ok_lines) == 20
    spec = yaml.safe_load((tmp_path / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    assert spec["study"]["factors"]["trigger"] == ["fade"]
    assert spec["study"]["constants"]["backtest"]["same_bar_opposite_direction"] == "raise"
    assert spec["study"]["report"]["random_baseline"]["n_replicas"] == 50
    assert spec["study"]["name"].startswith("progB_r2_")
    tick_ok, tick_fail, tick_n, tick_cells = validate.validate_manifest(
        tmp_path, manifest_name="manifest_tick.yaml"
    )
    assert tick_fail == []
    assert tick_n == 8
    assert tick_cells == 253
    assert (tmp_path / "progB_w0_va.yaml").exists()
    assert (tmp_path / "progB_w0_apoc.yaml").exists()
    assert not (tmp_path / "manifest_va.yaml").exists()
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Run 2" in readme
    assert "898" in readme
    assert "253" in readme


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
    assert "ok 20 studies / 898 cells" in captured.out


def _assert_wave7_tick_provenance(root: Path) -> None:
    manifest = yaml.safe_load((root / "manifest_tick.yaml").read_text(encoding="utf-8"))
    wave7_files = []
    for row in manifest["studies"]:
        if is_wave7_study_file(row["file"]):
            wave7_files.append(row["file"])
            assert row["apoc_provenance"] == WAVE7_TICK_PROVENANCE, row["file"]
            spec = yaml.safe_load((root / row["file"]).read_text(encoding="utf-8"))
            levels = spec["study"]["levels"]
            assert "apoc_profile_source" not in levels, row["file"]
            assert levels["apoc_enabled"] is True, row["file"]
            assert spec["study"]["dataset"]["tick_paths"] == _generate().TICK_PATHS
            header = (root / row["file"]).read_text(encoding="utf-8")
            assert "tick Last×Volume" in header
            assert "typical_mvp historical" in header
        else:
            assert "apoc_provenance" not in row, row["file"]
    assert wave7_files == [
        "progB_w7_apoc_ma.yaml",
        "progB_w7_apoc_rvwap.yaml",
        "progB_w7_apoc_pivot.yaml",
    ]
    fifteen_s = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
    assert not any(is_wave7_study_file(row["file"]) for row in fifteen_s["studies"])


def test_program_b_wave7_manifest_records_tick_provenance():
    _assert_wave7_tick_provenance(PROGRAM_B)
    _assert_wave7_tick_provenance(PROGRAM_B_RUN2)


def test_program_b_run2_tick_manifest_validates():
    validate = _validator()
    ok_lines, failures, n_studies, n_cells = validate.validate_manifest(
        PROGRAM_B_RUN2, manifest_name="manifest_tick.yaml"
    )
    assert failures == []
    assert n_studies == 8
    assert n_cells == 253
    assert len(ok_lines) == 8


def test_program_b_generate_wave7_provenance_is_deterministic(tmp_path):
    gen = _generate()
    gen.generate_packet(tmp_path)
    _assert_wave7_tick_provenance(tmp_path)
    committed = yaml.safe_load((PROGRAM_B / "manifest.yaml").read_text(encoding="utf-8"))
    generated = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert generated == committed
    for name in (
        "progB_w7_apoc_ma.yaml",
        "progB_w7_apoc_rvwap.yaml",
        "progB_w7_apoc_pivot.yaml",
        "progB_w0_solo.yaml",
        "progB_w0_apoc.yaml",
        "progB_w8_prev30m_ma.yaml",
    ):
        assert yaml.safe_load((tmp_path / name).read_text(encoding="utf-8")) == yaml.safe_load(
            (PROGRAM_B / name).read_text(encoding="utf-8")
        )
    tick_generated = yaml.safe_load((tmp_path / "manifest_tick.yaml").read_text(encoding="utf-8"))
    tick_committed = yaml.safe_load((PROGRAM_B / "manifest_tick.yaml").read_text(encoding="utf-8"))
    assert tick_generated == tick_committed


def test_program_b_run2_generate_matches_committed(tmp_path):
    gen = _generate()
    gen.main(["--trigger", "fade", "--output-dir", str(tmp_path)])
    for name in (
        "manifest.yaml",
        "manifest_tick.yaml",
        "progB_w0_solo.yaml",
        "progB_w0_va.yaml",
        "progB_w0_apoc.yaml",
        "progB_w7_apoc_ma.yaml",
        "README.md",
    ):
        generated = (tmp_path / name).read_text(encoding="utf-8")
        committed = (PROGRAM_B_RUN2 / name).read_text(encoding="utf-8")
        if name.endswith(".yaml"):
            assert yaml.safe_load(generated) == yaml.safe_load(committed), name
        else:
            assert generated == committed, name


def test_program_b_wave7_expand_succeeds_with_placeholder_paths():
    spec = yaml.safe_load((PROGRAM_B / "progB_w7_apoc_ma.yaml").read_text(encoding="utf-8"))
    normalized = normalize_study_spec(spec)
    assert "apoc_profile_source" not in normalized["study"]["levels"]
    assert normalized["study"]["dataset"]["tick_paths"] == _generate().TICK_PATHS
    validate_study_spec(normalized)


def test_program_b_wave7_refuses_when_tick_paths_stripped(tmp_path):
    spec = yaml.safe_load((PROGRAM_B / "progB_w7_apoc_ma.yaml").read_text(encoding="utf-8"))
    spec["study"]["dataset"].pop("tick_paths", None)
    normalized = normalize_study_spec(spec)
    with pytest.raises(StudySpecError, match="APOC requires ticks"):
        validate_study_spec(normalized)
    with pytest.raises(StudySpecError, match="APOC requires ticks"):
        expand_study_to_directory(spec, tmp_path)


def test_program_b_validator_rejects_wave7_without_manifest_provenance(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_w7_apoc_ma.yaml").read_text(encoding="utf-8"))
    drifted = tmp_path / "progB_w7_apoc_ma.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted, {"file": drifted.name, "cells": 24, "min_valid": 1}, packet="tick"
    )
    assert any("apoc_provenance" in item for item in failures)


def test_program_b_wave7_identity_hashes_are_pinned():
    """Fresh Wave 7 identity includes placeholder ticks + explicit 4/8/10 levels."""
    pins = {
        PROGRAM_B / "progB_w7_apoc_ma.yaml": (
            "6176b2819d2f0812b82cb4d54731e7e775064a722842f02cb3a05121c613d5cf"
        ),
        PROGRAM_B / "progB_w7_apoc_rvwap.yaml": (
            "4fb693ef51a2eb632ffe4ca8e1f10da7506dba206d9f7f64f50dfbf867580a03"
        ),
        PROGRAM_B / "progB_w7_apoc_pivot.yaml": (
            "7ecbf374033940f658414e6dc2cc91396b76713ad26dda40fec8762f83cb484a"
        ),
        PROGRAM_B_RUN2 / "progB_w7_apoc_ma.yaml": (
            "6664517a6b60ca6930e1168f09e1ffe32638dc9d39494d3f71af52252e2cc688"
        ),
        PROGRAM_B_RUN2 / "progB_w7_apoc_rvwap.yaml": (
            "c61bde203fd8d283ffd4cfb64d7a4210bb4cda4d6a03d1b03c162ccc3bddbe49"
        ),
        PROGRAM_B_RUN2 / "progB_w7_apoc_pivot.yaml": (
            "57240eeecb28284520ae35cb660c919964a70dba3b4a7e1410d1935667b488e2"
        ),
    }
    for path, expected in pins.items():
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        levels = spec["study"]["levels"]
        assert "apoc_profile_source" not in levels, path.name
        assert levels["apoc_enabled"] is True, path.name
        assert levels["prior_day_profile_aggregation_ticks"] == 4, path.name
        normalized = normalize_study_spec(spec)
        identity = study_identity_hash(normalized)
        assert identity == expected, f"{path}: {identity}"
        validate_study_spec(normalized)


def test_program_b_validator_rejects_wave7_disabled_apoc(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_w7_apoc_ma.yaml").read_text(encoding="utf-8"))
    spec["study"]["levels"]["apoc_enabled"] = False
    drifted = tmp_path / "progB_w7_apoc_ma.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted,
        {
            "file": drifted.name,
            "cells": 24,
            "min_valid": 1,
            "apoc_provenance": dict(WAVE7_TICK_PROVENANCE),
        },
        packet="tick",
    )
    assert any("apoc_enabled: true" in item for item in failures)


def test_program_b_validator_rejects_wave7_explicit_source_in_levels(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_w7_apoc_ma.yaml").read_text(encoding="utf-8"))
    spec["study"]["levels"]["apoc_profile_source"] = "typical_mvp_v1"
    drifted = tmp_path / "progB_w7_apoc_ma.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted,
        {
            "file": drifted.name,
            "cells": 24,
            "min_valid": 1,
            "apoc_provenance": dict(WAVE7_TICK_PROVENANCE),
        },
        packet="tick",
    )
    assert any("omit apoc_profile_source" in item for item in failures)


def test_program_b_validator_rejects_provenance_on_non_wave7(tmp_path):
    validate = _validator()
    spec = yaml.safe_load((PROGRAM_B / "progB_smoke_ONH_SMA50_5min.yaml").read_text())
    drifted = tmp_path / "progB_smoke_ONH_SMA50_5min.yaml"
    drifted.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    failures = validate.validate_study_file(
        drifted,
        {
            "file": drifted.name,
            "cells": 1,
            "min_valid": 1,
            "apoc_provenance": dict(WAVE7_TICK_PROVENANCE),
        },
        packet="15s",
    )
    assert any("Wave 7 only" in item for item in failures)


def test_program_b_fifteen_s_levels_disable_apoc_and_rolling():
    for root in (PROGRAM_B, PROGRAM_B_RUN2):
        fifteen_s = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
        for row in fifteen_s["studies"]:
            spec = yaml.safe_load((root / row["file"]).read_text(encoding="utf-8"))
            levels = spec["study"]["levels"]
            assert levels["apoc_enabled"] is False, f"{root}/{row['file']}"
            assert levels["poc_windows"] == [], f"{root}/{row['file']}"
            assert levels["prior_day_profile_aggregation_ticks"] == 4, f"{root}/{row['file']}"
            assert levels["prior_week_profile_aggregation_ticks"] == 8, f"{root}/{row['file']}"
            assert levels["prior_month_profile_aggregation_ticks"] == 10, f"{root}/{row['file']}"


def test_program_b_tick_levels_keep_aggregation_and_rolling():
    gen = _generate()
    for root in (PROGRAM_B, PROGRAM_B_RUN2):
        tick = yaml.safe_load((root / "manifest_tick.yaml").read_text(encoding="utf-8"))
        for row in tick["studies"]:
            spec = yaml.safe_load((root / row["file"]).read_text(encoding="utf-8"))
            levels = spec["study"]["levels"]
            cores = spec["study"]["factors"]["core_level"]
            assert levels["poc_windows"] == ["30min"], f"{root}/{row['file']}"
            assert levels["prior_day_profile_aggregation_ticks"] == 4, f"{root}/{row['file']}"
            assert levels["prior_week_profile_aggregation_ticks"] == 8, f"{root}/{row['file']}"
            assert levels["prior_month_profile_aggregation_ticks"] == 10, f"{root}/{row['file']}"
            assert "apoc_profile_source" not in levels, f"{root}/{row['file']}"
            if set(cores) & set(gen.APOC_ANCHOR_SET):
                assert levels["apoc_enabled"] is True, f"{root}/{row['file']}"
            else:
                assert levels["apoc_enabled"] is False, f"{root}/{row['file']}"
