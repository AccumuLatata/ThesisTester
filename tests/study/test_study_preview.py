"""RS-D8 StudySpec preview — compose-only, no execute import."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from thesistester.study.expand import expand_study
from thesistester.study.preview import (
    PREVIEW_EXPAND_CAP,
    STUDIES_PREVIEW_YAML_KEY,
    example_study_spec_path,
    preview_study_spec,
    preview_study_yaml,
)
from thesistester.study.schema import StudySpecError
from thesistester.study.viewer import CLASSIC_RESEARCH_SESSION_KEYS, STUDIES_VIEWER_DIR_KEY


def _example_spec() -> dict:
    path = example_study_spec_path()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_preview_stage_first_example_is_40_vs_800():
    preview = preview_study_spec(_example_spec())
    assert preview.expanded is True
    assert preview.run_count == 40
    assert preview.cartesian_product == 800
    assert preview.effective_run_count_estimate == 40
    assert preview.needs_confirm is False
    assert preview.confirm_above_runs == 200
    assert preview.workers == 1
    assert preview.axis_sizes == {
        "core_level": 1,
        "partner_levels": 4,
        "confluence_mode": 2,
        "trigger": 5,
        "trigger_timeframe": 4,
        "otf": 5,
    }
    assert preview.battery_enabled == {
        "grid": False,
        "validation": False,
        "walk_forward": False,
    }
    assert preview.study_identity_hash
    expansion = expand_study(_example_spec())
    assert preview.run_count == expansion.run_count
    assert preview.study_identity_hash == expansion.study_identity_hash


def test_filter_duplicate_include_does_not_inflate_estimate():
    spec = _example_spec()
    spec["study"]["stage"]["include"]["trigger"] = ["touch", "touch"]
    preview = preview_study_spec(spec)
    assert preview.effective_run_count_estimate == 40
    assert preview.run_count == 40
    assert preview.cartesian_product == 800


def test_preview_yaml_rejects_invalid_and_shorthand():
    with pytest.raises(StudySpecError, match="empty"):
        preview_study_yaml("  \n")
    with pytest.raises(StudySpecError, match="Invalid StudySpec YAML"):
        preview_study_yaml("study: [unterminated")
    with pytest.raises(StudySpecError, match="mapping"):
        preview_study_yaml("- just a list\n")
    with pytest.raises(StudySpecError):
        preview_study_yaml("schema_version: 1\nstudy:\n  name: x\n  factors:\n    core: [pdPOC]\n")


def test_missing_mode_rules_fails_closed():
    spec = _example_spec()
    del spec["study"]["mode_rules"]
    with pytest.raises(StudySpecError, match="mode_rules"):
        preview_study_spec(spec)


def test_over_cap_skips_expand(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("thesistester.study.preview.PREVIEW_EXPAND_CAP", 1)
    preview = preview_study_spec(_example_spec())
    assert preview.expanded is False
    assert preview.run_count is None
    assert preview.effective_run_count_estimate == 40
    assert preview.cartesian_product == 800
    assert preview.cap_warning is not None
    assert "PREVIEW_EXPAND_CAP" in preview.cap_warning
    assert preview.needs_confirm is False


def test_preview_module_import_allow_list():
    source = Path("thesistester/study/preview.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned = {
        "thesistester.study.execute",
        "thesistester.cli",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in banned
            assert not node.module.startswith("thesistester.study.execute")
            names = {alias.name for alias in node.names}
            assert "run_experiment" not in names
            assert "run_batch" not in names
            assert "expand_study_to_directory" not in names
            assert "promote_study" not in names
            assert "cost_hint_lines" not in names
            assert "run_study" not in names
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in banned
                assert "run_experiment" not in alias.name
    assert "cost_hint_lines" not in source
    assert PREVIEW_EXPAND_CAP == 2_000


def test_pages_studies_preview_has_no_execute_controls():
    page = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    assert "preview_study_yaml" in page
    assert "Refresh" in page
    assert "run_study" not in page
    assert "promote_study" not in page
    assert "expand_study_to_directory" not in page
    assert "STUDY.run" not in page
    assert "STUDIES_PREVIEW_YAML_KEY" in page
    tree = ast.parse(page)
    written_keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Subscript):
                continue
            value = target.value
            if not (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == "st"
                and value.attr == "session_state"
            ):
                continue
            slice_node = target.slice
            if isinstance(slice_node, ast.Name) and slice_node.id == "STUDIES_VIEWER_DIR_KEY":
                written_keys.add(STUDIES_VIEWER_DIR_KEY)
            elif isinstance(slice_node, ast.Name) and slice_node.id == "STUDIES_PREVIEW_YAML_KEY":
                written_keys.add(STUDIES_PREVIEW_YAML_KEY)
            elif isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                written_keys.add(slice_node.value)
            else:
                written_keys.add("<dynamic>")
    assert written_keys <= {
        STUDIES_VIEWER_DIR_KEY,
        "studies_viewer_path_input",
        STUDIES_PREVIEW_YAML_KEY,
    }
    assert not (written_keys & CLASSIC_RESEARCH_SESSION_KEYS)


def test_preview_does_not_require_dataset_csv(tmp_path: Path):
    spec = _example_spec()
    spec["study"]["dataset"]["path"] = str(tmp_path / "missing_bars.csv")
    preview = preview_study_spec(spec)
    assert preview.run_count == 40
