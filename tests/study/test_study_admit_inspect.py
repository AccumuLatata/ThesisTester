"""SAF2 Inspect Draft Admit follow-up → Preview. No spawn, no drafts/ write."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from thesistester.study.briefing import empty_briefing
from thesistester.study.launch import (
    STUDIES_LAUNCH_APPROVAL_KEY,
    STUDIES_LAUNCH_OUTPUT_DIR_KEY,
    reset_launch_session_for_preview,
)
from thesistester.study.preview import (
    STUDIES_PREVIEW_CACHED_KEY,
    STUDIES_PREVIEW_CACHED_YAML_KEY,
    STUDIES_PREVIEW_YAML_KEY,
)
from thesistester.study.promote import (
    StudyPromoteError,
    draft_admit_followup_yaml,
    inspect_admit_followup_ready,
    inspect_cell_in_flight,
    run_inspect_admit_followup,
)
from thesistester.study.report import report_study
from tests.study.test_study_admit_followup import _write_admit_fixture

STUDIES_ADMIT_FOLLOWUP_ERROR_KEY = "studies_admit_followup_error"


def _write_preview_like_apply(session: dict, yaml_text: str) -> None:
    """Mirror pages/15_Studies.py ``_write_preview_yaml`` (Apply sequence)."""
    prev_cached_yaml = session.get(STUDIES_PREVIEW_CACHED_YAML_KEY)
    session[STUDIES_PREVIEW_YAML_KEY] = yaml_text
    session.pop(STUDIES_PREVIEW_CACHED_KEY, None)
    session.pop(STUDIES_PREVIEW_CACHED_YAML_KEY, None)
    reset_launch_session_for_preview(
        session,
        prev_cached_yaml=prev_cached_yaml if isinstance(prev_cached_yaml, str) else None,
        new_yaml=yaml_text,
    )


def test_inspect_admit_followup_ready_requires_ranked_tod():
    empty = empty_briefing()
    assert inspect_admit_followup_ready(empty) is False
    ranked_no_tod = SimpleNamespace(run_name="cell_000", source="ranked", tod_best={})
    assert inspect_admit_followup_ready(ranked_no_tod) is False
    low_n = SimpleNamespace(
        run_name="cell_000",
        source="low_n",
        tod_best={"segment": "rth_open_30m"},
    )
    assert inspect_admit_followup_ready(low_n) is False
    ready = SimpleNamespace(
        run_name="cell_000",
        source="ranked",
        tod_best={"segment": "rth_open_30m"},
    )
    assert inspect_admit_followup_ready(ready) is True


def test_inspect_cell_in_flight():
    assert inspect_cell_in_flight({"cell_000": {"status": "running"}}, "cell_000") is True
    assert inspect_cell_in_flight({"cell_000": {"status": "pending"}}, "cell_000") is True
    assert inspect_cell_in_flight({"cell_000": {"status": "ok"}}, "cell_000") is False
    assert inspect_cell_in_flight({}, "cell_000", running_ids=("cell_000",)) is True


def test_inspect_admit_success_yaml_does_not_write_launch_or_drafts(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    top = str(report_study(study_dir).ranked.iloc[0]["run_name"])
    text = run_inspect_admit_followup(
        study_dir,
        run_name=top,
        trusted_roots=(tmp_path.resolve(),),
    )
    payload = yaml.safe_load(text)
    assert payload["study"]["constants"]["backtest"]["entry_window"]["enabled"] is True
    assert payload["study"]["lineage"]["parent_run_name"] == top
    assert not (tmp_path / "drafts").exists()
    assert not list(study_dir.glob("study.launch.*"))
    in_memory = draft_admit_followup_yaml(study_dir, admit_run_name=top)
    assert yaml.safe_load(in_memory)["study"]["name"] == payload["study"]["name"]


def test_inspect_admit_writes_preview_and_clears_confirm(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    top = str(report_study(study_dir).ranked.iloc[0]["run_name"])
    yaml_text = run_inspect_admit_followup(
        study_dir,
        run_name=top,
        trusted_roots=(tmp_path.resolve(),),
    )
    session = {
        STUDIES_PREVIEW_YAML_KEY: "old yaml",
        STUDIES_PREVIEW_CACHED_KEY: object(),
        STUDIES_PREVIEW_CACHED_YAML_KEY: "old yaml",
        STUDIES_LAUNCH_APPROVAL_KEY: {"run_count": 1},
        STUDIES_LAUNCH_OUTPUT_DIR_KEY: "out/old",
        STUDIES_ADMIT_FOLLOWUP_ERROR_KEY: "stale",
    }
    session.pop(STUDIES_ADMIT_FOLLOWUP_ERROR_KEY, None)
    _write_preview_like_apply(session, yaml_text)
    assert session[STUDIES_PREVIEW_YAML_KEY] == yaml_text
    assert STUDIES_PREVIEW_CACHED_KEY not in session
    assert STUDIES_PREVIEW_CACHED_YAML_KEY not in session
    assert STUDIES_LAUNCH_APPROVAL_KEY not in session
    assert STUDIES_ADMIT_FOLLOWUP_ERROR_KEY not in session
    assert not list(study_dir.glob("study.launch.*"))


def test_inspect_admit_refuses_extra_root_without_yaml(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    top = str(report_study(study_dir).ranked.iloc[0]["run_name"])
    elsewhere = tmp_path / "trusted_only"
    elsewhere.mkdir()
    with pytest.raises(StudyPromoteError, match="trusted local roots"):
        run_inspect_admit_followup(
            study_dir,
            run_name=top,
            trusted_roots=(elsewhere.resolve(),),
        )
    assert not (tmp_path / "drafts").exists()


def test_inspect_admit_refuses_in_flight(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    top = str(report_study(study_dir).ranked.iloc[0]["run_name"])
    with pytest.raises(StudyPromoteError, match="running or pending"):
        run_inspect_admit_followup(
            study_dir,
            run_name=top,
            ledger_cells={top: {"status": "running"}},
            trusted_roots=(tmp_path.resolve(),),
        )


def test_inspect_admit_refuses_thin_and_missing_zip(tmp_path: Path):
    thin_dir = _write_admit_fixture(tmp_path / "thin", open_r=[1.0] * 5, min_trades=30)
    top = str(report_study(thin_dir).ranked.iloc[0]["run_name"])
    with pytest.raises(StudyPromoteError, match="thin"):
        run_inspect_admit_followup(
            thin_dir,
            run_name=top,
            trusted_roots=(tmp_path.resolve(),),
        )
    missing = _write_admit_fixture(tmp_path / "missing")
    miss_top = str(report_study(missing).ranked.iloc[0]["run_name"])
    (missing / f"{miss_top}.research.zip").unlink()
    with pytest.raises(StudyPromoteError, match="zip"):
        run_inspect_admit_followup(
            missing,
            run_name=miss_top,
            trusted_roots=(tmp_path.resolve(),),
        )


def test_page_inspect_admit_ast_and_no_execute():
    page = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    assert "Draft Admit follow-up" in page
    assert "STUDIES_ADMIT_FOLLOWUP_ERROR_KEY" in page
    assert "studies_admit_followup_error" in page
    assert "_apply_inspect_admit_followup" in page
    assert "run_inspect_admit_followup" in page
    assert "run_study(" not in page
    assert "promote_study" not in page
    assert "CLASSIC_RESEARCH_SESSION_KEYS" not in page
    assert "prior_yaml" in page
    build_src = page[page.index("def _render_builder_live_strip") :]
    assert "Draft Admit follow-up" not in build_src
    tree = ast.parse(page)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "run_study"
    assert "thesistester.study.execute" not in imported
    assert "thesistester.study.cli_study" not in imported


def test_viewer_still_does_not_import_promote_or_admit_followup():
    source = Path("thesistester/study/viewer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "thesistester.study.promote" not in imported
    assert "thesistester.study.admit_followup" not in imported
