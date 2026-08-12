"""RS-D2 Studies viewer — load fixtures, path sandbox, no classic session mutation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from thesistester.study.ledger import empty_ledger, save_ledger
from thesistester.study.viewer import (
    CLASSIC_RESEARCH_SESSION_KEYS,
    StudyViewerError,
    load_study_view,
    resolve_study_dir,
)
from tests.study.test_study_report import _write_report_fixture


def test_load_study_view_from_fixture(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    expansion = (study_dir / "study.expansion.json").read_text(encoding="utf-8")
    import json

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
    assert not model.low_n_display.empty
    assert "Honesty" in model.overview_md or "descriptive" in model.overview_md.lower()
    assert model.report.min_trades == 30


def test_resolve_study_dir_refuses_outside_roots(tmp_path: Path):
    inside = tmp_path / "study"
    inside.mkdir()
    outside = tmp_path.parent / "outside_study_d2"
    outside.mkdir(exist_ok=True)
    with pytest.raises(StudyViewerError, match="trusted local roots"):
        resolve_study_dir(outside, roots=(tmp_path.resolve(),))
    resolved = resolve_study_dir(inside, roots=(tmp_path.resolve(),))
    assert resolved == inside.resolve()


def test_pages_studies_is_read_only_source():
    page = Path("pages/15_Studies.py")
    assert page.is_file()
    source = page.read_text(encoding="utf-8")
    assert "load_study_view" in source
    assert "run_study" not in source
    assert "expand_study" not in source
    assert "promote_study" not in source
    assert "st.session_state" not in source
    tree = ast.parse(source)
    assigned: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if (
                isinstance(node.value.value, ast.Name)
                and node.value.value.id == "st"
                and node.value.attr == "session_state"
            ):
                assigned.add("session_state_write")
    assert not assigned


def test_viewer_module_does_not_touch_classic_keys():
    source = Path("thesistester/study/viewer.py").read_text(encoding="utf-8")
    for key in CLASSIC_RESEARCH_SESSION_KEYS:
        # Keys appear only in the deny-list constant definition.
        assert source.count(f'"{key}"') == 1
