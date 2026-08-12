"""RS5 study promote — draft explicit_cells survivors; no execution."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from thesistester.cli import main as cli_main
from thesistester.study.expand import expand_study, expand_study_to_directory
from thesistester.study.promote import StudyPromoteError, promote_study
from thesistester.study.report import report_study
from thesistester.study.schema import load_study_spec

# Reuse the RS4 synthetic completed-study fixture builder.
from test_study_report import _write_report_fixture


def test_promote_writes_draft_explicit_cells_without_executing(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    ranked_before = list(report_study(study_dir).ranked["run_name"])
    out = tmp_path / "draft_survivors.yaml"
    result = promote_study(study_dir, output=out, top_n=2)

    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# DRAFT StudySpec")
    assert "auto-execution" in text.lower()

    draft = load_study_spec(out)
    assert draft["study"]["stage"]["mode"] == "explicit_cells"
    cells = draft["study"]["stage"]["cells"]
    assert len(cells) == 2
    assert result.cell_count == 2
    assert result.selected_run_names == ranked_before[:2]

    # Draft expands exactly to survivor count (no cartesian leakage).
    expansion = expand_study(draft)
    assert expansion.run_count == 2

    # Promote must not execute / write new bundles beside the draft.
    assert not any(tmp_path.glob("*.research.zip"))


def test_promote_empty_ranked_fails(tmp_path: Path):
    # min_trades high enough that every cell is low-N → no ranked survivors.
    study_dir = _write_report_fixture(tmp_path, min_trades=10_000)
    out = tmp_path / "draft.yaml"
    try:
        promote_study(study_dir, output=out, top_n=5)
        raise AssertionError("expected StudyPromoteError")
    except StudyPromoteError as exc:
        assert "ranked" in str(exc).lower() or "survivor" in str(exc).lower()
    assert not out.exists()


def test_cli_study_promote(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    out = tmp_path / "cli_draft.yaml"
    code = cli_main(
        ["study", "promote", str(study_dir), "--output", str(out), "--top-n", "1"]
    )
    assert code == 0
    assert out.is_file()
    draft = load_study_spec(out)
    assert len(draft["study"]["stage"]["cells"]) == 1


def test_example_stage_filter_expands_to_40_and_full_800():
    example = Path("examples/studies/pdPOC_ma_confluence_battery.yaml")
    assert example.is_file()
    staged = load_study_spec(example)
    assert staged["study"]["stage"]["mode"] == "filter"
    assert expand_study(staged).run_count == 40

    full = copy.deepcopy(staged)
    full["study"].pop("stage", None)
    assert expand_study(full).run_count == 800


def test_example_promoted_draft_round_trip(tmp_path: Path):
    """Tiny CI path: expand example stage-40 is heavy for execute; promote uses RS4 fixture."""
    study_dir = _write_report_fixture(tmp_path)
    out = tmp_path / "survivors.yaml"
    promote_study(study_dir, output=out, top_n=2)
    draft = load_study_spec(out)
    dest = tmp_path / "promoted_expand"
    expansion = expand_study_to_directory(draft, dest)
    assert expansion.run_count == 2
    assert (dest / "experiment.yaml").is_file()
    # Explicit cells only — factors narrowed but cartesian skipped.
    reloaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert reloaded["study"]["stage"]["mode"] == "explicit_cells"
