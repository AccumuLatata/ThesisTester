"""SV6 follow-on draft — one cell + Admit window; no execution."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from thesistester.cli import main as cli_main
from thesistester.entry_window_policy import RTH_SEGMENT_LABELS
from thesistester.study.expand import expand_study
from thesistester.study.follow_on import (
    FOLLOW_ON_SEGMENTS,
    StudyFollowOnError,
    build_follow_on_spec,
    follow_on_study,
    suggested_follow_on_path,
)
from thesistester.study.schema import load_study_spec
from test_study_briefing import _grid_zip_bytes, _write_grid_enabled_spec
from test_study_report import _write_report_fixture


def _winner_run(study_dir: Path) -> str:
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    for name, factors in expansion["factor_map"].items():
        if factors["partner_levels"] == ["SMA_50_1min"] and factors["otf"]["enabled"]:
            return str(name)
    raise AssertionError("expected SMA + OTF-on winner in fixture")


def test_follow_on_segments_match_canonical_rth_labels():
    assert FOLLOW_ON_SEGMENTS == RTH_SEGMENT_LABELS
    assert "rth_open_30m" in FOLLOW_ON_SEGMENTS


def test_follow_on_narrows_cell_and_sets_admit_window(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    run_name = _winner_run(study_dir)
    result = follow_on_study(
        study_dir,
        run_name=run_name,
        segment="rth_open_30m",
        pin_grid=False,
        write=False,
    )
    draft = result.draft_spec
    study = draft["study"]
    assert study["name"] == "pdPOC_rs4__fo_rth_open_30m"
    assert study["output_dir"].endswith("pdPOC_rs4__fo_rth_open_30m")
    assert "FOLLOW-ON confirmation" in study["description"]
    assert run_name in study["description"]
    assert str(study_dir.as_posix()) in study["description"]
    assert "entry_rth_segment" not in study["factors"]
    assert "time_of_day" not in study["factors"]
    assert "stage" not in study
    assert study["factors"]["partner_levels"] == [["SMA_50_1min"]]
    assert study["factors"]["otf"][0]["enabled"] is True
    window = study["constants"]["entry_window"]
    assert window["enabled"] is True
    assert window["mode"] == "rth_segments"
    assert window["rth_segments"] == ["rth_open_30m"]
    assert window["timezone"] == "America/New_York"
    assert result.entry_window == window
    expansion = expand_study(draft)
    assert expansion.run_count == 1
    setup = expansion.experiment["runs"][0]["setup"]
    assert setup["entry_window"]["enabled"] is True
    assert setup["entry_window"]["rth_segments"] == ["rth_open_30m"]
    assert result.output_path is None
    assert "DRAFT StudySpec" in result.yaml_text
    assert "does not execute" in result.yaml_text.lower()


def test_follow_on_pins_grid_winner_and_disables_grid(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    _write_grid_enabled_spec(study_dir)
    run_name = _winner_run(study_dir)
    index = pd.read_csv(study_dir / "results_index.csv")
    index.loc[index["run_name"] == run_name, "best_grid_stop_loss_ticks"] = 40
    index.loc[index["run_name"] == run_name, "best_grid_take_profit_ticks"] = 80
    index.to_csv(study_dir / "results_index.csv", index=False)

    result = follow_on_study(
        study_dir,
        run_name=run_name,
        segment="rth_morning",
        pin_grid=True,
        write=False,
    )
    constants = result.draft_spec["study"]["constants"]
    assert constants["backtest"]["stop_loss_ticks"] == 40
    assert constants["backtest"]["take_profit_ticks"] == 80
    assert constants["grid"]["enabled"] is False
    assert "Pinned SL/TP 40/80" in result.draft_spec["study"]["description"]


def test_follow_on_thin_bucket_requires_allow_thin(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    run_name = _winner_run(study_dir)
    (study_dir / f"{run_name}.research.zip").write_bytes(_grid_zip_bytes())

    with pytest.raises(StudyFollowOnError, match="thin"):
        follow_on_study(
            study_dir,
            run_name=run_name,
            segment="rth_open_30m",
            write=False,
        )
    result = follow_on_study(
        study_dir,
        run_name=run_name,
        segment="rth_open_30m",
        allow_thin=True,
        write=False,
    )
    assert result.thin_sample is True
    assert "thin" in result.draft_spec["study"]["description"].lower()


def test_follow_on_refuses_tod_factor_axis(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    spec = load_study_spec(study_dir / "study.spec.yaml")
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    run_name = _winner_run(study_dir)
    factors = dict(expansion["factor_map"][run_name])
    factors["entry_rth_segment"] = "rth_open_30m"
    with pytest.raises(StudyFollowOnError, match="time-of-day"):
        build_follow_on_spec(
            spec,
            factors=factors,
            segment="rth_open_30m",
            run_name=run_name,
            parent_study_dir=study_dir,
        )


def test_follow_on_writes_beside_parent_and_refuses_spec_overwrite(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    run_name = _winner_run(study_dir)
    out = suggested_follow_on_path(study_dir, "rth_afternoon")
    result = follow_on_study(
        study_dir,
        run_name=run_name,
        segment="rth_afternoon",
        pin_grid=False,
        write=True,
    )
    assert result.output_path == out
    assert out.is_file()
    parent_spec = (study_dir / "study.spec.yaml").read_text(encoding="utf-8")
    loaded = load_study_spec(out)
    assert loaded["study"]["constants"]["entry_window"]["rth_segments"] == ["rth_afternoon"]
    assert (study_dir / "study.spec.yaml").read_text(encoding="utf-8") == parent_spec

    with pytest.raises(StudyFollowOnError, match="overwrite"):
        follow_on_study(
            study_dir,
            run_name=run_name,
            segment="rth_afternoon",
            pin_grid=False,
            write=True,
        )
    follow_on_study(
        study_dir,
        run_name=run_name,
        segment="rth_afternoon",
        pin_grid=False,
        write=True,
        force=True,
    )
    with pytest.raises(StudyFollowOnError, match="protected|overwrite"):
        follow_on_study(
            study_dir,
            run_name=run_name,
            segment="rth_afternoon",
            pin_grid=False,
            output=study_dir / "study.spec.yaml",
            write=True,
            force=True,
        )


def test_follow_on_defaults_to_briefing_cell_and_segment(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    _write_grid_enabled_spec(study_dir)
    run_name = _winner_run(study_dir)
    (study_dir / f"{run_name}.research.zip").write_bytes(_grid_zip_bytes())
    index = pd.read_csv(study_dir / "results_index.csv")
    index.loc[index["run_name"] == run_name, "best_grid_stop_loss_ticks"] = 40
    index.loc[index["run_name"] == run_name, "best_grid_take_profit_ticks"] = 80
    index.to_csv(study_dir / "results_index.csv", index=False)

    result = follow_on_study(study_dir, allow_thin=True, write=False)
    assert result.run_name == run_name
    assert result.segment == "rth_open_30m"
    assert result.thin_sample is True
    assert result.draft_spec["study"]["constants"]["backtest"]["stop_loss_ticks"] == 40
    assert result.draft_spec["study"]["constants"]["grid"]["enabled"] is False


def test_follow_on_unknown_segment_fails_closed(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    with pytest.raises(StudyFollowOnError, match="Unknown RTH segment"):
        follow_on_study(
            study_dir,
            run_name=_winner_run(study_dir),
            segment="london_open",
            write=False,
        )


def test_follow_on_pins_dataset_path_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    study_dir = _write_report_fixture(tmp_path)
    bars = tmp_path / "bars.csv"
    bars.write_text("ts,open,high,low,close,volume\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = follow_on_study(
        study_dir,
        run_name=_winner_run(study_dir),
        segment="rth_midday",
        pin_grid=False,
        write=False,
    )
    assert Path(result.draft_spec["study"]["dataset"]["path"]) == bars.resolve()


def test_cli_study_follow_on(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    run_name = _winner_run(study_dir)
    out = tmp_path / "cli_follow_on.yaml"
    code = cli_main(
        [
            "study",
            "follow-on",
            str(study_dir),
            "--run-name",
            run_name,
            "--segment",
            "rth_power_hour",
            "--output",
            str(out),
            "--no-pin-grid",
        ]
    )
    assert code == 0
    assert out.is_file()
    draft = load_study_spec(out)
    assert draft["study"]["constants"]["entry_window"]["rth_segments"] == ["rth_power_hour"]
    code2 = cli_main(
        [
            "study",
            "follow-on",
            str(study_dir),
            "--run-name",
            run_name,
            "--segment",
            "rth_power_hour",
            "--output",
            str(out),
            "--no-pin-grid",
        ]
    )
    assert code2 == 2
    from thesistester.cli import _parser

    parsed = _parser().parse_args(["study", "expand", "spec.yaml", "--output-dir", "out/x"])
    assert parsed.study_command == "expand"
    assert parsed.output_dir == Path("out/x")


def test_follow_on_module_import_allow_list():
    source = Path("thesistester/study/follow_on.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "thesistester.study.execute" not in imported
    assert "thesistester.study.launch" not in imported
    assert "thesistester.study.cli_study" not in imported
    assert "thesistester.cli" not in imported
    assert "streamlit" not in imported
    assert "plotly" not in imported
    assert "thesistester.engine.backtest" not in imported


def test_studies_page_follow_on_is_getattr_safe():
    source = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    assert "from thesistester.study.follow_on import" not in source
    assert "except ImportError" in source
    assert 'getattr(module, "follow_on_study"' in source
    follow_src = source[
        source.index("def _render_inspect_follow_on") : source.index("def _render_inspect()")
    ]
    assert "run_study" not in follow_src
    assert "write=False" in follow_src
    assert "STUDIES_PREVIEW_YAML_KEY" in follow_src
    assert "Send follow-on YAML to Preview" in follow_src
