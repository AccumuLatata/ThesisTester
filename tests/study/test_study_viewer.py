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
from thesistester.study.builder import (
    STUDIES_BUILDER_DRAFT_KEY,
    STUDIES_BUILDER_PENDING_SYNC_KEY,
)
from thesistester.study.report import RESULTS_INDEX
from thesistester.study.viewer import (
    CLASSIC_RESEARCH_SESSION_KEYS,
    STUDIES_VIEWER_CACHED_MODEL_DIR_KEY,
    STUDIES_VIEWER_CACHED_MODEL_KEY,
    STUDIES_VIEWER_DIR_KEY,
    StudyViewerError,
    load_study_view,
    resolve_study_dir,
    summarize_ledger_progress,
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
    assert model.report_present is True
    assert model.ledger_summary.get("ok") == 4
    assert model.ledger_progress.done == 4
    assert model.ledger_progress.total == 4
    assert model.ledger_progress.in_flight is False
    assert model.ledger_progress.fraction == 1.0
    assert model.ledger_progress.running_ids == ()
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


def test_summarize_ledger_progress_in_flight_and_empty():
    empty = summarize_ledger_progress({}, run_count=None)
    assert empty.done == 0
    assert empty.total == 0
    assert empty.fraction == 0.0
    assert empty.in_flight is False

    mid = summarize_ledger_progress(
        {"ok": 2, "failed": 1, "skipped": 0, "running": 1, "pending": 8},
        run_count=12,
        running_ids=("cell_b", "cell_a"),
    )
    assert mid.done == 3
    assert mid.total == 12
    assert mid.pending == 8
    assert mid.running_count == 2
    assert mid.running_ids == ("cell_b", "cell_a")
    assert mid.in_flight is True
    assert mid.fraction == 0.25


def test_load_study_view_progress_from_mixed_ledger(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    ledger["cells"][names[0]]["status"] = "ok"
    ledger["cells"][names[1]]["status"] = "failed"
    ledger["cells"][names[2]]["status"] = "running"
    ledger["cells"][names[3]]["status"] = "pending"
    save_ledger(study_dir, ledger)

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert model.report_present is True
    assert model.ledger_progress.done == 2
    assert model.ledger_progress.total == 4
    assert model.ledger_progress.pending == 1
    assert model.ledger_progress.running_ids == (names[2],)
    assert model.ledger_progress.in_flight is True
    assert model.ledger_progress.fraction == 0.5


def test_load_study_view_ledger_only_when_index_missing(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    ledger["cells"][names[0]]["status"] = "running"
    save_ledger(study_dir, ledger)
    (study_dir / RESULTS_INDEX).unlink()

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert model.ledger_present is True
    assert model.report_present is False
    assert model.ledger_progress.running_ids == (names[0],)
    assert model.ledger_progress.pending == 3
    assert model.ledger_progress.total == 4
    assert model.ranked_display.empty
    assert not (study_dir / "study.overview.csv").exists()


def test_load_study_view_missing_index_without_ledger_still_errors(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    (study_dir / RESULTS_INDEX).unlink()
    with pytest.raises(StudyViewerError, match=RESULTS_INDEX):
        load_study_view(study_dir, roots=(tmp_path.resolve(),))


def test_load_study_view_invalid_index_with_ledger_still_errors(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    ledger["cells"][names[0]]["status"] = "running"
    save_ledger(study_dir, ledger)
    (study_dir / RESULTS_INDEX).write_text("status,trade_count\nok,10\n", encoding="utf-8")
    with pytest.raises(StudyViewerError, match="run_name"):
        load_study_view(study_dir, roots=(tmp_path.resolve(),))


def test_load_study_view_unreadable_index_with_ledger_still_errors(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    save_ledger(study_dir, ledger)
    (study_dir / RESULTS_INDEX).write_text("not a csv\x00\x00", encoding="utf-8")
    with pytest.raises(StudyViewerError, match=RESULTS_INDEX):
        load_study_view(study_dir, roots=(tmp_path.resolve(),))


def test_load_study_view_ledger_only_uses_spec_report_settings(tmp_path: Path):
    import yaml

    study_dir = _write_report_fixture(tmp_path, min_trades=5, multiple_testing="error")
    spec_path = study_dir / "study.spec.yaml"
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    payload["study"]["report"]["primary_metric"] = "profit_factor"
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    ledger["cells"][names[0]]["status"] = "running"
    save_ledger(study_dir, ledger)
    (study_dir / RESULTS_INDEX).unlink()

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert model.report_present is False
    assert model.report.primary_metric == "profit_factor"
    assert model.report.min_trades == 5
    assert model.report.multiple_testing == "error"
    assert model.report.best_cell_suppressed is True


def test_load_study_view_index_directory_with_ledger_still_errors(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    save_ledger(study_dir, ledger)
    index_path = study_dir / RESULTS_INDEX
    index_path.unlink()
    index_path.mkdir()
    with pytest.raises(StudyViewerError, match=RESULTS_INDEX):
        load_study_view(study_dir, roots=(tmp_path.resolve(),))


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
    assert "st.progress" in source
    assert "Ranked tables stay empty until Refresh after" in source
    assert "results_index.csv` is absent" in source
    assert "not written yet (first cell still running)" not in source
    assert "run_every" not in source
    assert "st.fragment" not in source
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
            elif isinstance(slice_node, ast.Name) and slice_node.id == "STUDIES_BUILDER_DRAFT_KEY":
                written_keys.add(STUDIES_BUILDER_DRAFT_KEY)
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_BUILDER_PENDING_SYNC_KEY"
            ):
                written_keys.add(STUDIES_BUILDER_PENDING_SYNC_KEY)
            elif isinstance(slice_node, ast.Name) and slice_node.id.startswith("WIDGET_KEY_"):
                continue
            elif (
                isinstance(slice_node, ast.Call)
                and isinstance(slice_node.func, ast.Name)
                and slice_node.func.id == "_partner_set_widget_key"
            ):
                continue
            elif (
                isinstance(slice_node, ast.Call)
                and isinstance(slice_node.func, ast.Name)
                and slice_node.func.id == "_stage_include_widget_key"
            ):
                continue
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
        STUDIES_BUILDER_DRAFT_KEY,
        STUDIES_BUILDER_PENDING_SYNC_KEY,
    }
    assert STUDIES_BUILDER_DRAFT_KEY in written_keys
    assert STUDIES_BUILDER_PENDING_SYNC_KEY in written_keys
    assert not (written_keys & CLASSIC_RESEARCH_SESSION_KEYS)


def test_viewer_module_does_not_touch_classic_keys():
    source = Path("thesistester/study/viewer.py").read_text(encoding="utf-8")
    for key in CLASSIC_RESEARCH_SESSION_KEYS:
        # Keys appear only in the deny-list constant definition.
        assert source.count(f'"{key}"') == 1
