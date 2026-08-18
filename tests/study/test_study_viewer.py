"""RS-D2 Studies viewer — load fixtures, path sandbox, no classic session mutation."""

from __future__ import annotations

import ast
import io
import json
import zipfile
from pathlib import Path
from typing import Any

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
    FAILED_ERROR_PRINT_CAP,
    LAUNCH_LOG_NAME,
    LAUNCH_LOG_TAIL_BYTES,
    ROLLUP_CSV_NAME,
    ROLLUP_MD_NAME,
    STUDIES_CATALOG_ENTRIES_KEY,
    STUDIES_CATALOG_ROOTS_KEY,
    STUDIES_VIEWER_CACHED_MODEL_DIR_KEY,
    STUDIES_VIEWER_CACHED_MODEL_KEY,
    STUDIES_VIEWER_CATALOG_SELECT_KEY,
    STUDIES_VIEWER_DIR_KEY,
    STUDIES_VIEWER_PENDING_PATH_KEY,
    STUDIES_VIEWER_SELECTED_RUN_KEY,
    StudyViewerError,
    catalog_load_path,
    discover_study_dirs,
    failed_cell_error_lines,
    failed_cells_frame,
    format_study_catalog_table,
    load_study_view,
    peek_run_names,
    peek_study_cell,
    peek_zip_bytes,
    preview_error_text,
    read_rollup_files,
    resolve_catalog_roots,
    resolve_study_dir,
    study_viewer_model_is_current,
    summarize_ledger_progress,
    tail_launch_log,
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
    assert "best_grid_stop_loss_ticks" in model.ranked_display.columns
    assert "best_grid_take_profit_ticks" in model.ranked_display.columns
    assert list(model.ranked_display.columns) == list(dict.fromkeys(model.ranked_display.columns))
    assert model.briefing.run_name is not None
    assert "Highest" in model.briefing.headline
    assert model.briefing.source == "ranked"
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
    assert not (study_dir / ROLLUP_CSV_NAME).exists()
    assert not (study_dir / ROLLUP_MD_NAME).exists()


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
    assert model.briefing.source == "none"
    assert "Ledger-only" in model.briefing.headline


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
    assert "discover_study_dirs" in source
    assert "Refresh catalog" in source
    assert "Load selected" in source
    assert "st.progress" in source
    assert "Ranked tables stay empty until Refresh after" in source
    assert "results_index.csv` is absent" in source
    assert "not written yet (first cell still running)" not in source
    assert "run_every" not in source
    assert "st.fragment" not in source
    assert "run_study" not in source
    assert "expand_study" not in source
    assert "promote_study" not in source
    assert "rollup_study" not in source
    assert "build_group_summaries" not in source
    assert "apply_research_bundle_to_session" not in source
    assert "report_study(" not in source
    assert "### Failed cells" in source
    assert "### Group summaries" in source
    assert "### Rollup" in source
    assert "### Overview charts" in source
    assert "### Cell peek" in source
    assert "import plotly.express" in source
    assert "st.plotly_chart" in source
    assert "st.switch_page" not in source
    assert "peek_study_cell" in source
    assert "model.report.group_summaries" in source
    assert "study_viewer_model_is_current" in source
    assert "st.code" in source
    assert 'st.caption("\\n\\n".join(model.unique_error_lines))' not in source
    assert "Full failed-cell error text" in source
    assert "Show study.launch.log (tail)" in source
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
            elif (
                isinstance(slice_node, ast.Name) and slice_node.id == "STUDIES_CATALOG_ENTRIES_KEY"
            ):
                written_keys.add(STUDIES_CATALOG_ENTRIES_KEY)
            elif isinstance(slice_node, ast.Name) and slice_node.id == "STUDIES_CATALOG_ROOTS_KEY":
                written_keys.add(STUDIES_CATALOG_ROOTS_KEY)
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_VIEWER_PENDING_PATH_KEY"
            ):
                written_keys.add(STUDIES_VIEWER_PENDING_PATH_KEY)
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_VIEWER_CATALOG_SELECT_KEY"
            ):
                written_keys.add(STUDIES_VIEWER_CATALOG_SELECT_KEY)
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_VIEWER_SELECTED_RUN_KEY"
            ):
                written_keys.add(STUDIES_VIEWER_SELECTED_RUN_KEY)
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_ADMIT_FOLLOWUP_ERROR_KEY"
            ):
                written_keys.add("studies_admit_followup_error")
            elif (
                isinstance(slice_node, ast.Name)
                and slice_node.id == "STUDIES_ADMIT_FOLLOWUP_NOTICE_KEY"
            ):
                written_keys.add("studies_admit_followup_notice")
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
        STUDIES_CATALOG_ENTRIES_KEY,
        STUDIES_CATALOG_ROOTS_KEY,
        STUDIES_VIEWER_PENDING_PATH_KEY,
        STUDIES_VIEWER_CATALOG_SELECT_KEY,
        STUDIES_VIEWER_SELECTED_RUN_KEY,
        "studies_admit_followup_error",
        "studies_admit_followup_notice",
    }
    assert STUDIES_BUILDER_DRAFT_KEY in written_keys
    assert STUDIES_BUILDER_PENDING_SYNC_KEY in written_keys
    assert STUDIES_CATALOG_ENTRIES_KEY in written_keys
    assert STUDIES_VIEWER_PENDING_PATH_KEY in written_keys
    assert not (written_keys & CLASSIC_RESEARCH_SESSION_KEYS)


def test_viewer_module_does_not_touch_classic_keys():
    source = Path("thesistester/study/viewer.py").read_text(encoding="utf-8")
    for key in CLASSIC_RESEARCH_SESSION_KEYS:
        # Keys appear only in the deny-list constant definition.
        assert source.count(f'"{key}"') == 1


def _write_catalog_study(
    parent: Path,
    name: str,
    *,
    ledger_ok: int = 0,
    ledger_failed: int = 0,
    corrupt_ledger: bool = False,
    corrupt_spec: bool = False,
    run_count: int | None = 2,
    parent_output_dir: str | None = None,
) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    study_dir = parent / name
    study_dir.mkdir()
    if corrupt_spec:
        (study_dir / "study.spec.yaml").write_text(
            "schema_version: 1\nstudy: [\n  name: broken\n",
            encoding="utf-8",
        )
    else:
        lineage = ""
        if parent_output_dir:
            lineage = (
                "  lineage:\n"
                f"    parent_output_dir: {parent_output_dir}\n"
                "    parent_identity_hash: hash-parent\n"
                "    parent_run_name: cell_000\n"
                "    admit:\n"
                "      group: entry_rth_segment\n"
                "      value: rth_open_30m\n"
                "      rule: briefing_best_avg_r\n"
                "      min_trades: 30\n"
                "      thin: false\n"
            )
        (study_dir / "study.spec.yaml").write_text(
            f"schema_version: 1\nstudy:\n  name: {name}\n{lineage}",
            encoding="utf-8",
        )
    if run_count is not None:
        (study_dir / "study.expansion.json").write_text(
            json.dumps({"study_identity_hash": f"hash-{name}", "run_count": run_count}),
            encoding="utf-8",
        )
    if corrupt_ledger:
        (study_dir / "study.ledger.json").write_text("{not-json", encoding="utf-8")
        return study_dir
    if ledger_ok or ledger_failed:
        cells = {}
        for index in range(ledger_ok):
            cells[f"ok_{index}"] = {"status": "ok"}
        for index in range(ledger_failed):
            cells[f"failed_{index}"] = {"status": "failed", "error": "boom"}
        (study_dir / "study.ledger.json").write_text(
            json.dumps({"cells": cells}),
            encoding="utf-8",
        )
    return study_dir


def test_discover_study_dirs_scans_prefixes_only(tmp_path: Path):
    listed_a = _write_catalog_study(tmp_path / "results" / "studies", "alpha", ledger_ok=2)
    listed_b = _write_catalog_study(tmp_path / "out", "beta", ledger_ok=1, ledger_failed=1)
    skipped = tmp_path / "results" / "studies" / "not_a_study"
    skipped.mkdir(parents=True)
    (skipped / "readme.txt").write_text("no spec", encoding="utf-8")
    nested = tmp_path / "results" / "studies" / "alpha" / "nested"
    _write_catalog_study(nested, "too_deep")
    fixtures = tmp_path / "tests" / "fixtures" / "study"
    _write_catalog_study(fixtures, "golden_hit")

    entries = discover_study_dirs((tmp_path.resolve(),))
    names = {entry.study_name for entry in entries}
    assert names == {"alpha", "beta"}
    by_name = {entry.study_name: entry for entry in entries}
    assert by_name["alpha"].study_dir == listed_a.resolve()
    assert by_name["alpha"].ok == 2
    assert by_name["alpha"].run_count == 2
    assert by_name["beta"].study_dir == listed_b.resolve()
    assert by_name["beta"].failed == 1
    assert all(entry.study_name != "too_deep" for entry in entries)
    assert all(entry.study_name != "golden_hit" for entry in entries)


def test_discover_study_dirs_tolerates_corrupt_ledger_and_skips_report(tmp_path: Path, monkeypatch):
    _write_catalog_study(tmp_path / "out", "gamma", corrupt_ledger=True)
    extra = _write_catalog_study(tmp_path / "scratch", "extra_loaded", run_count=3)

    def _boom(*_args, **_kwargs):
        raise AssertionError("discover must not call report_study")

    def _boom_promote(*_args, **_kwargs):
        raise AssertionError("discover must not call promote")

    monkeypatch.setattr("thesistester.study.viewer.report_study", _boom)
    monkeypatch.setattr("thesistester.study.viewer.promote_study", _boom_promote, raising=False)
    monkeypatch.setattr(
        "thesistester.study.promote.promote_study",
        _boom_promote,
        raising=False,
    )
    entries = discover_study_dirs(
        (tmp_path.resolve(),),
        extra_dirs=(str(extra),),
    )
    names = {entry.study_name: entry for entry in entries}
    assert "gamma" in names
    assert names["gamma"].ledger_present is False
    assert names["gamma"].ok == 0
    assert names["extra_loaded"].run_count == 3
    assert names["extra_loaded"].study_identity_hash == "hash-extra_loaded"


def test_discover_study_dirs_tolerates_corrupt_spec_yaml(tmp_path: Path):
    good = _write_catalog_study(tmp_path / "out", "good_spec", run_count=None)
    bad = _write_catalog_study(
        tmp_path / "out",
        "bad_spec",
        corrupt_spec=True,
        run_count=None,
    )
    entries = discover_study_dirs((tmp_path.resolve(),))
    by_dir = {entry.study_dir: entry for entry in entries}
    assert good.resolve() in by_dir
    assert bad.resolve() in by_dir
    assert by_dir[good.resolve()].study_name == "good_spec"
    assert by_dir[bad.resolve()].study_name == "bad_spec"
    assert by_dir[bad.resolve()].parent == "—"
    assert by_dir[bad.resolve()].run_count is None
    assert by_dir[bad.resolve()].ledger_present is False


def test_discover_study_dirs_lists_spec_only_dir(tmp_path: Path):
    spec_only = _write_catalog_study(tmp_path / "out", "spec_only", run_count=None)
    assert not (spec_only / "study.ledger.json").exists()
    assert not (spec_only / "study.expansion.json").exists()
    assert not (spec_only / "results_index.csv").exists()
    entries = discover_study_dirs((tmp_path.resolve(),))
    match = next(entry for entry in entries if entry.study_dir == spec_only.resolve())
    assert match.study_name == "spec_only"
    assert match.run_count is None
    assert match.ledger_present is False
    assert match.index_present is False


def test_discover_and_catalog_load_refuse_extra_root(tmp_path: Path):
    inside = _write_catalog_study(tmp_path / "out", "inside")
    outside = tmp_path.parent / "outside_sv1_catalog"
    outside.mkdir(exist_ok=True)
    (outside / "study.spec.yaml").write_text("schema_version: 1\nstudy:\n  name: leak\n")
    with pytest.raises(StudyViewerError, match="trusted local roots"):
        resolve_catalog_roots((outside,))
    with pytest.raises(StudyViewerError, match="trusted local roots"):
        catalog_load_path(outside, roots=(tmp_path.resolve(),))
    path = catalog_load_path(inside, roots=(tmp_path.resolve(),))
    assert Path(path).name == "inside"


def test_format_study_catalog_table_stable_headers(tmp_path: Path):
    _write_catalog_study(tmp_path / "out", "delta", ledger_ok=1)
    entries = discover_study_dirs((tmp_path.resolve(),))
    table = format_study_catalog_table(entries)
    assert table.startswith("study_name")
    header = table.splitlines()[0]
    assert "parent" in header
    assert "ok/failed/skipped/running/pending" in header
    assert "delta" in table
    assert format_study_catalog_table(()) == (
        "No study directories found under results/studies/ or out/."
    )


def test_catalog_parent_from_lineage_basename(tmp_path: Path):
    child = _write_catalog_study(
        tmp_path / "out",
        "child_admit",
        parent_output_dir=str((tmp_path / "results" / "studies" / "parent_screen").resolve()),
    )
    entries = discover_study_dirs((tmp_path.resolve(),))
    match = next(entry for entry in entries if entry.study_dir == child.resolve())
    assert match.parent == "parent_screen"
    table = format_study_catalog_table(entries)
    header = table.splitlines()[0]
    assert header.split()[1] == "parent" or "parent" in header
    assert "parent_screen" in table


def test_catalog_parent_failure_does_not_discard_identity(tmp_path: Path, monkeypatch):
    child = _write_catalog_study(
        tmp_path / "out",
        "child_keep_identity",
        ledger_ok=2,
        run_count=4,
        parent_output_dir=str(tmp_path / "results" / "studies" / "parent_screen"),
    )

    def _boom(_study_dir):
        raise RuntimeError("parent read exploded")

    monkeypatch.setattr("thesistester.study.viewer._read_catalog_parent", _boom)
    entries = discover_study_dirs((tmp_path.resolve(),))
    match = next(entry for entry in entries if entry.study_dir == child.resolve())
    assert match.parent == "—"
    assert match.study_name == "child_keep_identity"
    assert match.study_identity_hash == "hash-child_keep_identity"
    assert match.run_count == 4
    assert match.ok == 2
    assert match.ledger_present is True


def test_cli_study_list_additive_and_refuses_extra_root(tmp_path: Path, monkeypatch, capsys):
    from thesistester.cli import main as cli_main

    _write_catalog_study(tmp_path / "results" / "studies", "cli_alpha")
    monkeypatch.setattr(
        "thesistester.study.viewer.default_study_viewer_roots",
        lambda: (tmp_path.resolve(),),
    )
    assert cli_main(["study", "list"]) == 0
    out = capsys.readouterr().out
    assert "cli_alpha" in out
    assert "study_name" in out
    assert "parent" in out.splitlines()[0]

    outside = tmp_path.parent / "outside_sv1_cli"
    outside.mkdir(exist_ok=True)
    assert cli_main(["study", "list", "--root", str(outside)]) == 2
    err = capsys.readouterr().err
    assert "trusted local roots" in err

    study_only = _write_catalog_study(tmp_path / "scratch", "solo")
    assert cli_main(["study", "list", "--root", str(study_only)]) == 0
    solo_out = capsys.readouterr().out
    assert "solo" in solo_out
    assert "cli_alpha" not in solo_out

    assert cli_main(["study", "list", "--root", str(tmp_path / "results" / "studies")]) == 0
    prefix_out = capsys.readouterr().out
    assert "cli_alpha" in prefix_out

    assert cli_main(["study", "list", "--root", str(tmp_path)]) == 0
    root_out = capsys.readouterr().out
    assert "cli_alpha" in root_out

    missing = tmp_path / "does_not_exist"
    assert cli_main(["study", "list", "--root", str(missing)]) == 2
    assert "does not exist" in capsys.readouterr().err

    not_a_dir = tmp_path / "a_file.txt"
    not_a_dir.write_text("nope", encoding="utf-8")
    assert cli_main(["study", "list", "--root", str(not_a_dir)]) == 2
    assert "not a directory" in capsys.readouterr().err

    _write_catalog_study(tmp_path / "out", "cli_out")
    assert cli_main(["study", "list", "--root", str(tmp_path / "out")]) == 0
    out_prefix = capsys.readouterr().out
    assert "cli_out" in out_prefix
    assert "cli_alpha" not in out_prefix
    assert "solo" not in out_prefix

    assert cli_main(["study", "list", "--root", str(tmp_path / "scratch")]) == 0
    parent_out = capsys.readouterr().out
    assert "solo" in parent_out
    assert "cli_alpha" not in parent_out

    from thesistester.cli import _parser

    parsed = _parser().parse_args(["study", "expand", "spec.yaml", "--output-dir", "out/x"])
    assert parsed.study_command == "expand"
    assert parsed.output_dir == Path("out/x")


def test_viewer_module_import_allow_list():
    source = Path("thesistester/study/viewer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "thesistester.study.execute" not in imported
    assert "thesistester.study.launch" not in imported
    assert "thesistester.study.builder" not in imported
    assert "thesistester.study.promote" not in imported
    assert "thesistester.study.tools" not in imported
    assert "thesistester.study.cli_study" not in imported
    assert "thesistester.cli" not in imported
    assert "plotly" not in imported
    assert "streamlit" not in imported
    assert "thesistester.study.rollup" not in imported
    assert "rollup_study(" not in source


_PAGE_LOCAL_VIEWER_KEYS = {
    "STUDIES_VIEWER_DIR_KEY": "studies_viewer_study_dir",
    "STUDIES_VIEWER_CACHED_MODEL_KEY": "studies_viewer_cached_model",
    "STUDIES_VIEWER_CACHED_MODEL_DIR_KEY": "studies_viewer_cached_model_dir",
    "STUDIES_CATALOG_ENTRIES_KEY": "studies_catalog_entries",
    "STUDIES_CATALOG_ROOTS_KEY": "studies_catalog_roots_key",
    "STUDIES_VIEWER_PENDING_PATH_KEY": "studies_viewer_pending_path",
    "STUDIES_VIEWER_CATALOG_SELECT_KEY": "studies_viewer_catalog_select",
    "STUDIES_VIEWER_SELECTED_RUN_KEY": "studies_viewer_selected_run",
    "CATALOG_DISPLAY_CAP": 50,
}


def test_studies_page_does_not_from_import_viewer_names():
    """A stale/mid-init viewer bricks Studies if the page from-imports names."""
    source = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    from_names: list[str] = []
    imported_viewer_module = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "thesistester.study.viewer":
            from_names.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module == "thesistester.study":
            imported_viewer_module = imported_viewer_module or any(
                alias.name == "viewer" for alias in node.names
            )
        if isinstance(node, ast.Import):
            imported_viewer_module = imported_viewer_module or any(
                alias.name == "thesistester.study.viewer" for alias in node.names
            )
    assert from_names == []
    assert imported_viewer_module
    for name in _PAGE_LOCAL_VIEWER_KEYS:
        assert name not in from_names
    current_src = source[
        source.index("def study_viewer_model_is_current") : source.index(
            "# Do not import FORMAT_PROFILE_LABELS"
        )
    ]
    assert "return False" in current_src
    assert "return True" not in current_src
    preview_src = source[
        source.index("def preview_error_text") : source.index("def study_viewer_model_is_current")
    ]
    assert 'return raw[: limit - 3] + "..."' in preview_src


def test_studies_page_viewer_keys_are_page_local():
    source = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assigned: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in _PAGE_LOCAL_VIEWER_KEYS:
                assigned[target.id] = node.value.value
    assert assigned == _PAGE_LOCAL_VIEWER_KEYS
    import thesistester.study.viewer as viewer_mod

    for name, value in _PAGE_LOCAL_VIEWER_KEYS.items():
        assert getattr(viewer_mod, name) == value


def test_launch_trusted_roots_match_viewer():
    from thesistester.study.launch import _default_trusted_roots
    from thesistester.study.viewer import default_study_viewer_roots

    assert _default_trusted_roots() == default_study_viewer_roots()


def test_inspect_catalog_handler_does_not_call_load_study_view():
    source = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    start = source.index("def _render_inspect_catalog")
    end = source.index("def _render_inspect_quality(")
    catalog_src = source[start:end]
    assert "discover_study_dirs" in catalog_src
    assert "catalog_load_path" in catalog_src
    assert "STUDIES_VIEWER_DIR_KEY" in catalog_src
    assert "STUDIES_VIEWER_PENDING_PATH_KEY" in catalog_src
    assert "STUDIES_VIEWER_CACHED_MODEL_KEY" in catalog_src
    assert "st.rerun" in catalog_src
    assert "load_study_view" not in catalog_src
    assert "run_study" not in catalog_src
    assert "rollup_study" not in catalog_src
    assert "report_study" not in catalog_src
    assert "promote_study" not in catalog_src
    assert "admit_followup" not in catalog_src


def test_inspect_charts_use_ranked_frames_and_honesty():
    source = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    start = source.index("_CHART_HONESTY")
    end = source.index("def _render_inspect(")
    chart_src = source[start:end]
    assert "st.plotly_chart" in chart_src
    assert "px.histogram" in chart_src
    assert "px.scatter" in chart_src
    assert "px.bar" in chart_src
    assert "No ranked cells to chart" in chart_src
    assert "No group-summary axes to chart" in chart_src
    assert "No group-bar series" in chart_src
    assert "Descriptive screening, not a validated edge" in chart_src
    assert "_CHART_HONESTY" in chart_src
    assert "_is_chart_frame" in chart_src
    assert "ranked_display" in chart_src
    assert "group_summaries" in chart_src
    assert "median_" in chart_src
    assert "mean_" in chart_src
    assert "low_n_display" not in chart_src
    assert "unresolved_display" not in chart_src
    assert "zipfile" not in chart_src
    assert "ZipFile" not in chart_src
    assert "fillna(0)" not in chart_src
    assert "run_study" not in chart_src
    assert "rollup_study" not in chart_src
    assert "apply_research_bundle_to_session" not in chart_src


class _FakeStreamlit:
    """Record Inspect chart calls without importing the Studies page module."""

    def __init__(self) -> None:
        self.captions: list[str] = []
        self.markdowns: list[str] = []
        self.charts: list[object] = []

    def caption(self, text: object, **_kwargs: object) -> None:
        self.captions.append(str(text))

    def markdown(self, text: object, **_kwargs: object) -> None:
        self.markdowns.append(str(text))

    def plotly_chart(self, fig: object, **_kwargs: object) -> None:
        self.charts.append(fig)


def _load_inspect_chart_helpers(st: object, px: object) -> dict[str, object]:
    """Exec the page chart helpers. Importing ``pages/15_Studies.py`` runs tabs."""
    source = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    start = source.index("_CHART_HONESTY")
    end = source.index("def _render_inspect(")
    namespace: dict[str, object] = {
        "Any": Any,
        "StudyViewerModel": object,
        "px": px,
        "st": st,
    }
    exec("from __future__ import annotations\n" + source[start:end], namespace)
    return namespace


def test_inspect_charts_empty_ranked_does_not_crash(tmp_path: Path):
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
    assert model.ranked_display.empty
    assert model.report.group_summaries == {}

    import plotly.express as px

    fake = _FakeStreamlit()
    helpers = _load_inspect_chart_helpers(fake, px)
    helpers["_render_inspect_charts"](model)
    assert fake.charts == []
    assert "No ranked cells to chart." in fake.captions
    assert "No group-summary axes to chart." in fake.captions
    assert any("Descriptive screening" in text for text in fake.captions)


def test_inspect_charts_render_locked_set_from_loaded_model(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=sorted(expansion["factor_map"]),
    )
    for name in expansion["factor_map"]:
        ledger["cells"][name]["status"] = "ok"
        ledger["cells"][name]["bundle_path"] = f"{name}.research.zip"
    save_ledger(study_dir, ledger)
    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))

    import plotly.express as px

    fake = _FakeStreamlit()
    helpers = _load_inspect_chart_helpers(fake, px)
    frame = helpers["_ranked_chart_frame"](model)
    assert frame is model.ranked_display
    assert model.report.primary_metric in frame.columns
    helpers["_render_inspect_charts"](model)
    assert len(fake.charts) == 2 + len(model.report.group_summaries)
    assert "No ranked cells to chart." not in fake.captions
    assert any("Descriptive screening" in text for text in fake.captions)


def test_inspect_charts_skip_non_frame_group_summaries():
    import plotly.express as px

    metric = "expectancy_r"
    ranked_frame = pd.DataFrame(
        {
            "run_name": ["a", "b"],
            "trade_count": [40, 50],
            metric: [0.1, 0.2],
        }
    )

    class _Report:
        primary_metric = metric
        ranked = ranked_frame
        group_summaries = {"partner_levels": "not-a-frame", "otf": None}

    class _Model:
        report = _Report()
        ranked_display = ranked_frame

    fake = _FakeStreamlit()
    helpers = _load_inspect_chart_helpers(fake, px)
    helpers["_render_inspect_charts"](_Model())
    assert len(fake.charts) == 2
    assert fake.captions.count("No group-bar series for `partner_levels`.") == 1
    assert fake.captions.count("No group-bar series for `otf`.") == 1


def test_ranked_chart_frame_falls_back_when_display_lacks_metric():
    import plotly.express as px

    metric = "expectancy_r"
    display = pd.DataFrame({"run_name": ["a"], "trade_count": [40]})
    ranked_frame = pd.DataFrame({"run_name": ["a"], "trade_count": [40], metric: [0.25]})

    class _Report:
        primary_metric = metric
        ranked = ranked_frame
        group_summaries = {}

    class _Model:
        report = _Report()
        ranked_display = display

    helpers = _load_inspect_chart_helpers(_FakeStreamlit(), px)
    frame = helpers["_ranked_chart_frame"](_Model())
    assert frame is ranked_frame
    assert metric in frame.columns


def test_failed_cell_error_lines_dedupes_and_caps_from_viewer():
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


def test_failed_cell_error_lines_default_cap_is_five():
    cells = {f"c{index}": {"status": "failed", "error": f"err-{index}"} for index in range(6)}
    names = [f"c{index}" for index in range(6)]
    lines = failed_cell_error_lines(cells, names)
    assert FAILED_ERROR_PRINT_CAP == 5
    examples = [line for line in lines if line.startswith("  ") and not line.startswith("  …")]
    assert len(examples) == 5
    assert lines[-1] == "  … +1 more unique error(s) in study.ledger.json"


def test_failed_cell_error_lines_skips_non_mapping_cells():
    cells = {
        "a": {"status": "failed", "error": "ValueError: boom"},
        "b": "not-a-mapping",
        "c": ["failed"],
    }
    lines = failed_cell_error_lines(cells, ["a", "b", "c"])
    assert lines[1] == "  a: ValueError: boom"
    frame = failed_cells_frame({"cells": cells})
    assert list(frame["run_name"]) == ["a"]


def test_quality_panes_from_loaded_model(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    long_error = "DataValidationError: " + ("missing column " * 20)
    ledger["cells"][names[0]]["status"] = "failed"
    ledger["cells"][names[0]]["error"] = long_error
    ledger["cells"][names[1]]["status"] = "failed"
    ledger["cells"][names[1]]["error"] = "FileNotFoundError: bars.csv"
    ledger["cells"][names[2]]["status"] = "ok"
    ledger["cells"][names[3]]["status"] = "ok"
    save_ledger(study_dir, ledger)

    rollup_csv = "run_name,status\ncell_a,ok\n"
    rollup_md = "# Rollup\ncompose-only\n"
    (study_dir / ROLLUP_CSV_NAME).write_text(rollup_csv, encoding="utf-8")
    (study_dir / ROLLUP_MD_NAME).write_text(rollup_md, encoding="utf-8")
    prefix = "HEAD\n" + ("x" * (LAUNCH_LOG_TAIL_BYTES + 200))
    (study_dir / LAUNCH_LOG_NAME).write_text(prefix + "TAILMARK\n", encoding="utf-8")
    overview_before = (
        (study_dir / OVERVIEW_MD).read_text(encoding="utf-8")
        if (study_dir / OVERVIEW_MD).exists()
        else None
    )
    rollup_mtime = (study_dir / ROLLUP_CSV_NAME).stat().st_mtime

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert list(model.failed_cells_display.columns) == ["run_name", "error"]
    assert set(model.failed_cells_display["run_name"]) == {names[0], names[1]}
    assert long_error in set(model.failed_cells_display["error"])
    assert model.unique_error_lines[0] == "Failed cell errors (unique):"
    assert any("FileNotFoundError: bars.csv" in line for line in model.unique_error_lines)
    assert preview_error_text(long_error) != long_error

    report = report_study(study_dir, write_artifacts=False)
    assert set(model.report.group_summaries) == set(report.group_summaries)
    for axis, frame in model.report.group_summaries.items():
        pd.testing.assert_frame_equal(frame, report.group_summaries[axis])

    assert model.rollup_present is True
    assert list(model.rollup_display["run_name"]) == ["cell_a"]
    assert model.rollup_md == rollup_md
    assert model.launch_log_present is True
    assert model.launch_log_tail.endswith("TAILMARK\n")
    assert "HEAD\n" not in model.launch_log_tail
    assert len(model.launch_log_tail.encode("utf-8")) <= LAUNCH_LOG_TAIL_BYTES

    assert (study_dir / ROLLUP_CSV_NAME).read_text(encoding="utf-8") == rollup_csv
    assert (study_dir / ROLLUP_MD_NAME).read_text(encoding="utf-8") == rollup_md
    assert (study_dir / ROLLUP_CSV_NAME).stat().st_mtime == rollup_mtime
    if overview_before is None:
        assert not (study_dir / OVERVIEW_MD).exists()
        assert not (study_dir / OVERVIEW_CSV).exists()
    else:
        assert (study_dir / OVERVIEW_MD).read_text(encoding="utf-8") == overview_before


def test_quality_panes_absent_rollup_and_ledger_only(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    ledger["cells"][names[0]]["status"] = "failed"
    ledger["cells"][names[0]]["error"] = "ValueError: boom"
    save_ledger(study_dir, ledger)

    complete = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert complete.rollup_present is False
    assert complete.rollup_display.empty
    assert complete.rollup_md == ""
    assert complete.launch_log_present is False
    assert list(complete.failed_cells_display["run_name"]) == [names[0]]
    assert isinstance(complete.report.group_summaries, dict)

    (study_dir / ROLLUP_CSV_NAME).write_text("run_name,status\norphan,ok\n", encoding="utf-8")
    (study_dir / RESULTS_INDEX).unlink()
    overview_csv_existed = (study_dir / OVERVIEW_CSV).exists()
    overview_md_existed = (study_dir / OVERVIEW_MD).exists()
    ledger_only = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert ledger_only.report_present is False
    assert list(ledger_only.failed_cells_display["run_name"]) == [names[0]]
    assert ledger_only.failed_cells_display.iloc[0]["error"] == "ValueError: boom"
    assert ledger_only.report.group_summaries == {}
    assert ledger_only.rollup_present is True
    assert list(ledger_only.rollup_display["run_name"]) == ["orphan"]
    assert (study_dir / ROLLUP_CSV_NAME).is_file()
    assert (study_dir / OVERVIEW_CSV).exists() is overview_csv_existed
    assert (study_dir / OVERVIEW_MD).exists() is overview_md_existed


def test_read_rollup_and_launch_log_helpers(tmp_path: Path):
    study_dir = tmp_path / "solo"
    study_dir.mkdir()
    absent = read_rollup_files(study_dir)
    assert absent.present is False
    assert tail_launch_log(study_dir) is None

    (study_dir / ROLLUP_CSV_NAME).write_text("run_name\nalpha\n", encoding="utf-8")
    (study_dir / ROLLUP_MD_NAME).write_text("# md\n", encoding="utf-8")
    present = read_rollup_files(study_dir)
    assert present.present is True
    assert list(present.frame["run_name"]) == ["alpha"]
    assert present.markdown == "# md\n"

    (study_dir / LAUNCH_LOG_NAME).write_bytes(b"ok \xff tail")
    text = tail_launch_log(study_dir)
    assert text is not None
    assert "ok" in text
    assert "tail" in text

    frame = failed_cells_frame(
        {"cells": {"z": {"status": "failed"}, "a": {"status": "failed", "error": "e"}}}
    )
    assert list(frame["run_name"]) == ["a", "z"]
    assert list(frame["error"]) == ["e", "unknown error"]


def test_load_study_view_does_not_call_rollup_study(tmp_path: Path, monkeypatch):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)

    def _boom(*_args, **_kwargs):
        raise AssertionError("load_study_view must not call rollup_study")

    monkeypatch.setattr("thesistester.study.rollup.rollup_study", _boom)
    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert model.rollup_present is False
    assert not (study_dir / ROLLUP_CSV_NAME).exists()


def test_load_study_view_tolerates_non_mapping_ledger_cell(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    ledger["cells"][names[0]] = "not-a-mapping"
    ledger["cells"][names[1]]["status"] = "failed"
    ledger["cells"][names[1]]["error"] = "ValueError: boom"
    save_ledger(study_dir, ledger)
    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert list(model.failed_cells_display["run_name"]) == [names[1]]
    assert model.unique_error_lines[1] == f"  {names[1]}: ValueError: boom"


def test_load_study_view_failed_table_lists_every_cell_caption_caps_unique(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    shared = "DataValidationError: missing columns"
    for name in names[:3]:
        ledger["cells"][name]["status"] = "failed"
        ledger["cells"][name]["error"] = shared
    extras = [f"unique-{index}" for index in range(5)]
    extra_names = [f"extra_{index}" for index in range(5)]
    for extra_name, error in zip(extra_names, extras, strict=True):
        ledger["cells"][extra_name] = {"status": "failed", "error": error}
    save_ledger(study_dir, ledger)
    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert len(model.failed_cells_display) == 8
    assert (model.failed_cells_display["error"] == shared).sum() == 3
    examples = [
        line
        for line in model.unique_error_lines
        if line.startswith("  ") and not line.startswith("  …")
    ]
    assert len(examples) == FAILED_ERROR_PRINT_CAP
    assert model.unique_error_lines[-1] == "  … +1 more unique error(s) in study.ledger.json"


def test_study_viewer_model_is_current_requires_sv2_fields():
    class _Legacy:
        ranked_display = None

    assert study_viewer_model_is_current(_Legacy()) is False

    class _Sv2:
        failed_cells_display = None
        unique_error_lines = None
        rollup_present = None
        rollup_display = None
        rollup_md = None
        launch_log_present = None
        launch_log_tail = None
        peek_run_names = ()
        ledger_cells = {}

    assert study_viewer_model_is_current(_Sv2()) is False


def test_peek_index_error_without_zip_and_in_dir_summary(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=1)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    ledger["cells"][names[0]]["status"] = "failed"
    ledger["cells"][names[0]]["error"] = "ValueError: boom"
    for name in names[1:]:
        ledger["cells"][name]["status"] = "ok"
        ledger["cells"][name]["bundle_path"] = f"{name}.research.zip"
    save_ledger(study_dir, ledger)

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert names[0] in model.peek_run_names
    peek = peek_study_cell(model, names[0])
    assert peek.present is True
    assert peek.ledger_error == "ValueError: boom"
    assert peek.kpis  # overview row still present on the completed fixture
    # Fixture index still has bundle_path; strip it to prove no-zip peek.
    index_path = study_dir / RESULTS_INDEX
    frame = pd.read_csv(index_path)
    frame.loc[frame["run_name"] == names[0], "bundle_path"] = ""
    frame.to_csv(index_path, index=False)
    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    bare = peek_study_cell(model, names[0])
    assert bare.ledger_error == "ValueError: boom"
    assert bare.trade_summary is None
    assert bare.zip_path is None
    assert "No bundle_path" in (bare.trade_summary_caption or "")

    zipped = peek_study_cell(model, names[1])
    assert zipped.trade_summary is not None
    assert "profit_factor" in zipped.trade_summary
    assert zipped.zip_path is not None
    assert zipped.zip_path.is_file()
    assert zipped.zip_path.is_relative_to(study_dir.resolve())
    before = sorted(path.name for path in study_dir.iterdir())
    payload = peek_zip_bytes(zipped, study_dir=study_dir)
    assert payload == zipped.zip_path.read_bytes()
    assert sorted(path.name for path in study_dir.iterdir()) == before

    (study_dir / RESULTS_INDEX).unlink()
    ledger_only = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    only = peek_study_cell(ledger_only, names[0])
    assert only.kpis == {}
    assert only.factors == {}
    assert only.ledger_error == "ValueError: boom"
    assert only.trade_summary is None
    assert only.zip_path is None


def test_peek_refuses_escape_and_missing_member(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=1)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    secret = tmp_path / "secret.research.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "trade_summary.json",
            json.dumps({"trade_summary": {"profit_factor": 99.0, "win_rate": 0.99}}),
        )
    secret.write_bytes(buffer.getvalue())
    index_path = study_dir / RESULTS_INDEX
    frame = pd.read_csv(index_path)
    frame.loc[frame["run_name"] == names[0], "bundle_path"] = str(secret.resolve())
    empty_zip = study_dir / "empty.research.zip"
    with zipfile.ZipFile(empty_zip, "w") as archive:
        archive.writestr("manifest.json", "{}")
    frame.loc[frame["run_name"] == names[1], "bundle_path"] = "empty.research.zip"
    frame.to_csv(index_path, index=False)

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    escaped = peek_study_cell(model, names[0])
    assert escaped.trade_summary is None
    assert escaped.zip_path is None
    assert "outside" in (escaped.trade_summary_caption or "").lower()
    assert peek_zip_bytes(escaped, study_dir=study_dir) is None

    missing = peek_study_cell(model, names[1])
    assert missing.trade_summary is None
    assert missing.zip_path is not None
    assert "missing" in (missing.trade_summary_caption or "")


def test_inspect_peek_does_not_hydrate_or_switch_page():
    source = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    start = source.index("def _render_inspect_peek")
    end = source.index("def _peek_summary_value")
    peek_src = source[start:end]
    assert "peek_study_cell" in peek_src
    assert "peek_zip_bytes" in peek_src
    assert "STUDIES_VIEWER_SELECTED_RUN_KEY" in peek_src
    assert "Prepare download" in peek_src
    assert "st.checkbox" in peek_src
    assert "studies_viewer_peek_zip_prepare:" in peek_src
    assert 'key="studies_viewer_peek_zip_prepare"' not in peek_src
    assert "apply_research_bundle_to_session" not in peek_src
    assert "st.switch_page" not in peek_src
    assert "equity_curve" not in peek_src
    assert "run_study" not in peek_src
    assert "rollup_study" not in peek_src
    assert "SL/TP grid (this cell)" in peek_src
    assert "Time of day (NY RTH segments)" in peek_src
    assert 'st.session_state["trades"]' not in peek_src
    assert "apply_research_bundle_to_session" not in peek_src


def test_peek_run_names_skips_non_mapping_cells_and_uses_cached_ledger(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=1)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    ledger["cells"][names[0]]["status"] = "failed"
    ledger["cells"][names[0]]["error"] = "ValueError: cached"
    ledger["cells"]["corrupt"] = "not-a-mapping"
    save_ledger(study_dir, ledger)

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert "corrupt" not in model.peek_run_names
    assert names[0] in model.peek_run_names
    assert names[0] in model.ledger_cells
    peek = peek_study_cell(model, names[0])
    assert peek.ledger_error == "ValueError: cached"

    ledger["cells"][names[0]]["error"] = "ValueError: disk-changed"
    save_ledger(study_dir, ledger)
    stale = peek_study_cell(model, names[0])
    assert stale.ledger_error == "ValueError: cached"


def test_peek_run_names_skips_null_overview_values():
    overview = pd.DataFrame({"run_name": ["alpha", float("nan"), None, ""]})
    assert peek_run_names(overview, None) == ("alpha",)
