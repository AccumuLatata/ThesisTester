"""RS-D2 Studies viewer — load fixtures, path sandbox, no classic session mutation."""

from __future__ import annotations

import ast
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from thesistester.study.ledger import empty_ledger, save_ledger
from thesistester.study.report import OVERVIEW_CSV, OVERVIEW_MD, OTF_DELTA_CSV, report_study
from thesistester.study.viewer import (
    CLASSIC_RESEARCH_SESSION_KEYS,
    STUDIES_VIEWER_CACHED_MODEL_DIR_KEY,
    STUDIES_VIEWER_CACHED_MODEL_KEY,
    STUDIES_VIEWER_DIR_KEY,
    StudyViewerError,
    load_study_view,
    resolve_study_dir,
)
from tests.study.test_study_report import _write_report_fixture


def test_load_study_view_from_fixture(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = (study_dir / "study.expansion.json").read_text(encoding="utf-8")
    payload = json.loads(expansion)
    ledger = empty_ledger(
        study_identity_hash=str(payload["study_identity_hash"]),
        run_names=sorted(payload["factor_map"]),
    )
    for name in payload["factor_map"]:
        ledger["cells"][name]["status"] = "ok"
        ledger["cells"][name]["bundle_path"] = f"{name}.research.zip"
    save_ledger(study_dir, ledger)

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert model.study_name == "pdPOC_rs4"
    assert model.run_count == 4
    assert model.ledger_present is True
    assert model.ledger_summary.get("ok") == 4
    assert not model.ranked_display.empty
    assert "bundle_path" in model.ranked_display.columns
    assert list(model.ranked_display.columns) == list(dict.fromkeys(model.ranked_display.columns))
    assert not model.low_n_display.empty
    assert "Honesty" in model.overview_md or "descriptive" in model.overview_md.lower()
    assert model.report.min_trades == 30
    assert "run_name" in model.overview_csv_text


def test_display_columns_dedupe_when_primary_is_profit_factor(tmp_path: Path):
    import yaml

    study_dir = _write_report_fixture(tmp_path, min_trades=1)
    spec_path = study_dir / "study.spec.yaml"
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    payload["study"]["report"]["primary_metric"] = "profit_factor"
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert model.report.primary_metric == "profit_factor"
    assert list(model.ranked_display.columns).count("profit_factor") <= 1
    assert list(model.low_n_display.columns).count("profit_factor") <= 1


def test_load_study_view_does_not_write_or_clobber_overview(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    sentinel = "# HAND_AUTHORED_OVERVIEW\n"
    (study_dir / OVERVIEW_MD).write_text(sentinel, encoding="utf-8")
    assert not (study_dir / OVERVIEW_CSV).exists()
    assert not (study_dir / OTF_DELTA_CSV).exists()

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert model.study_name == "pdPOC_rs4"
    assert (study_dir / OVERVIEW_MD).read_text(encoding="utf-8") == sentinel
    assert not (study_dir / OVERVIEW_CSV).exists()
    assert not (study_dir / OTF_DELTA_CSV).exists()


def test_resolve_study_dir_refuses_outside_roots(tmp_path: Path):
    inside = tmp_path / "study"
    inside.mkdir()
    outside = tmp_path.parent / "outside_study_d2"
    outside.mkdir(exist_ok=True)
    with pytest.raises(StudyViewerError, match="trusted local roots"):
        resolve_study_dir(outside, roots=(tmp_path.resolve(),))
    resolved = resolve_study_dir(inside, roots=(tmp_path.resolve(),))
    assert resolved == inside.resolve()


def test_load_study_view_tolerates_corrupt_ledger(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    (study_dir / "study.ledger.json").write_text("{not-json", encoding="utf-8")
    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert model.study_name == "pdPOC_rs4"
    assert model.ledger_present is False
    # Falls back to overview/index status counts when ledger is unreadable.
    assert isinstance(model.ledger_summary, dict)


def test_report_ignores_bundle_path_outside_study_dir(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=1)
    secret = tmp_path / "secret.research.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "trade_summary.json",
            json.dumps({"trade_summary": {"profit_factor": 99.0, "win_rate": 0.99}}),
        )
    secret.write_bytes(buffer.getvalue())

    index_path = study_dir / "results_index.csv"
    frame = pd.read_csv(index_path)
    # Drop index PF/WR so bundle resolution is attempted; point outside study_dir.
    if "profit_factor" in frame.columns:
        frame["profit_factor"] = pd.NA
    if "win_rate" in frame.columns:
        frame["win_rate"] = pd.NA
    frame["bundle_path"] = str(secret.resolve())
    frame.to_csv(index_path, index=False)

    result = report_study(study_dir, write_artifacts=False)
    # Escaped absolute bundle must not contribute PF from the outside zip.
    assert not (result.overview["profit_factor"].fillna(-1) == 99.0).any()
    assert (result.overview["profit_factor_source"] == "missing").all()


def test_pages_studies_is_read_only_source():
    page = Path("pages/15_Studies.py")
    assert page.is_file()
    source = page.read_text(encoding="utf-8")
    assert "load_study_view" in source
    assert "run_study" not in source
    assert "expand_study" not in source
    assert "promote_study" not in source
    assert "write_artifacts=False" in Path("thesistester/study/viewer.py").read_text(
        encoding="utf-8"
    )
    assert "STUDIES_VIEWER_DIR_KEY" in source
    tree = ast.parse(source)
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
            # st.session_state[STUDIES_VIEWER_DIR_KEY] = ...
            slice_node = target.slice
            if isinstance(slice_node, ast.Name) and slice_node.id == "STUDIES_VIEWER_DIR_KEY":
                written_keys.add(STUDIES_VIEWER_DIR_KEY)
            elif isinstance(slice_node, ast.Name) and slice_node.id == "STUDIES_PREVIEW_YAML_KEY":
                written_keys.add("studies_preview_yaml")
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_VIEWER_CACHED_MODEL_KEY"
            ):
                written_keys.add(STUDIES_VIEWER_CACHED_MODEL_KEY)
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_VIEWER_CACHED_MODEL_DIR_KEY"
            ):
                written_keys.add(STUDIES_VIEWER_CACHED_MODEL_DIR_KEY)
            elif isinstance(slice_node, ast.Name) and slice_node.id == "STUDIES_PREVIEW_CACHED_KEY":
                written_keys.add("studies_preview_cached")
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_PREVIEW_CACHED_YAML_KEY"
            ):
                written_keys.add("studies_preview_cached_yaml")
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_LAUNCH_OUTPUT_DIR_KEY"
            ):
                written_keys.add("studies_launch_output_dir")
            elif (
                isinstance(slice_node, ast.Name) and slice_node.id == "STUDIES_LAUNCH_APPROVAL_KEY"
            ):
                written_keys.add("studies_launch_approval")
            elif isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                written_keys.add(slice_node.value)
            else:
                written_keys.add("<dynamic>")
    assert STUDIES_VIEWER_DIR_KEY in written_keys
    assert STUDIES_VIEWER_CACHED_MODEL_KEY in written_keys
    assert written_keys <= {
        STUDIES_VIEWER_DIR_KEY,
        "studies_viewer_path_input",
        STUDIES_VIEWER_CACHED_MODEL_KEY,
        STUDIES_VIEWER_CACHED_MODEL_DIR_KEY,
        "studies_preview_yaml",
        "studies_preview_cached",
        "studies_preview_cached_yaml",
        "studies_launch_output_dir",
        "studies_launch_approval",
    }
    assert not (written_keys & CLASSIC_RESEARCH_SESSION_KEYS)


def test_viewer_module_does_not_touch_classic_keys():
    source = Path("thesistester/study/viewer.py").read_text(encoding="utf-8")
    for key in CLASSIC_RESEARCH_SESSION_KEYS:
        # Keys appear only in the deny-list constant definition.
        assert source.count(f'"{key}"') == 1
