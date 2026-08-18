"""SAF1 Admit follow-up — window stamp, lineage, refuse paths, no execute."""

from __future__ import annotations

import ast
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest
import yaml

from thesistester.cli import main as cli_main
from thesistester.study.admit_followup import (
    ADMIT_TOD_GROUP,
    AdmitFollowupError,
    select_admit_bucket,
)
from thesistester.study.builder import default_study_draft, emit_study_spec, hydrate_study_draft
from thesistester.study.expand import expand_study
from thesistester.study.promote import StudyPromoteError, promote_study
from thesistester.study.report import report_study
from thesistester.study.schema import load_study_spec
from tests.study.test_study_report import _write_report_fixture


def _trades_zip_bytes(
    *,
    open_r: list[float],
    morning_r: list[float] | None = None,
    midday_r: list[float] | None = None,
) -> bytes:
    stamps: list[str] = []
    rs: list[float] = []
    for i, value in enumerate(open_r):
        stamps.append(f"2026-06-02 09:35:{i:02d}")
        rs.append(value)
    for i, value in enumerate(morning_r or []):
        stamps.append(f"2026-06-02 10:15:{i:02d}")
        rs.append(value)
    for i, value in enumerate(midday_r or []):
        stamps.append(f"2026-06-02 12:00:{i:02d}")
        rs.append(value)
    trades = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(stamps).tz_localize("America/New_York"),
            "r_multiple": rs,
        }
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"included": {"backtest": True}}))
        trades_buf = io.BytesIO()
        trades.to_parquet(trades_buf, index=False)
        archive.writestr("trades.parquet", trades_buf.getvalue())
    return buffer.getvalue()


def _write_admit_fixture(
    tmp_path: Path,
    *,
    open_r: list[float] | None = None,
    morning_r: list[float] | None = None,
    midday_r: list[float] | None = None,
    min_trades: int = 30,
    overwrite_run: str | None = None,
) -> Path:
    """Completed study with ``trades.parquet`` on the selected ranked cell."""
    study_dir = _write_report_fixture(tmp_path, min_trades=min_trades)
    report = report_study(study_dir)
    if open_r is None:
        open_r = [1.0] * 35
    payload = _trades_zip_bytes(open_r=open_r, morning_r=morning_r, midday_r=midday_r)
    names = [overwrite_run] if overwrite_run else [str(name) for name in report.ranked["run_name"]]
    for run_name in names:
        row = report.overview.loc[report.overview["run_name"] == run_name].iloc[0]
        zip_path = study_dir / str(row["bundle_path"])
        zip_path.write_bytes(payload)
    return study_dir


def test_admit_followup_stamps_engine_windows_and_lineage(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    parent = report_study(study_dir)
    top = str(parent.ranked.iloc[0]["run_name"])
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    out = tmp_path / "drafts" / "admit.yaml"
    result = promote_study(study_dir, output=out, top_n=1, admit_tod="auto")

    assert out.is_file()
    draft = load_study_spec(out)
    study = draft["study"]
    assert "lineage" in study
    assert study["name"] == f"{parent.study_name}_admit_rth_open_30m"
    assert study["output_dir"] == f"results/studies/{study['name']}"
    assert Path(study["output_dir"]).resolve() != study_dir.resolve()
    assert result.selected_run_names == [top]
    assert result.cell_count == 1

    window = study["constants"]["entry_window"]
    backtest_window = study["constants"]["backtest"]["entry_window"]
    grid_window = study["constants"]["grid"]["entry_window"]
    assert window["enabled"] is True
    assert window["mode"] == "rth_segments"
    assert window["rth_segments"] == ["rth_open_30m"]
    assert backtest_window == window
    assert grid_window == window
    assert study["constants"]["grid"]["enabled"] is False
    assert "entry_window" not in study["constants"].get("validation", {})
    assert "entry_window" not in study["constants"].get("walk_forward", {})
    assert study["constants"]["validation"]["enabled"] is False
    assert study["constants"]["walk_forward"]["enabled"] is False

    lineage = study["lineage"]
    assert lineage["parent_output_dir"] == study_dir.resolve().as_posix()
    assert lineage["parent_identity_hash"] == expansion["study_identity_hash"]
    assert lineage["parent_run_name"] == top
    assert lineage["admit"]["group"] == ADMIT_TOD_GROUP
    assert lineage["admit"]["value"] == "rth_open_30m"
    assert lineage["admit"]["rule"] == "briefing_best_avg_r"
    assert lineage["admit"]["min_trades"] == parent.min_trades
    assert lineage["admit"]["thin"] is False

    expansion_result = expand_study(draft)
    assert expansion_result.run_count == 1
    run = expansion_result.experiment["runs"][0]
    assert run["backtest"]["entry_window"]["enabled"] is True
    assert run["backtest"]["entry_window"]["rth_segments"] == ["rth_open_30m"]
    assert run["setup"]["entry_window"]["enabled"] is True
    assert not any(tmp_path.glob("*.research.zip"))


def test_admit_followup_admit_run_name(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    ranked = list(report_study(study_dir).ranked["run_name"])
    assert len(ranked) >= 2
    chosen = ranked[1]
    out = tmp_path / "admit_named.yaml"
    result = promote_study(
        study_dir,
        output=out,
        top_n=10,
        admit_tod="auto",
        admit_run_name=chosen,
    )
    draft = load_study_spec(out)
    assert result.selected_run_names == [chosen]
    assert draft["study"]["lineage"]["parent_run_name"] == chosen


def test_admit_followup_refuses_top_n_without_run_name(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    out = tmp_path / "nope.yaml"
    with pytest.raises(StudyPromoteError, match="--top-n 1|--admit-run-name"):
        promote_study(study_dir, output=out, top_n=2, admit_tod="auto")
    assert not out.exists()


def test_admit_followup_refuses_unranked_name(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    low_n = str(report_study(study_dir).low_n.iloc[0]["run_name"])
    out = tmp_path / "unranked.yaml"
    with pytest.raises(StudyPromoteError, match="ranked"):
        promote_study(
            study_dir,
            output=out,
            top_n=1,
            admit_tod="auto",
            admit_run_name=low_n,
        )
    assert not out.exists()


def test_admit_followup_refuses_missing_zip(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    top = str(report_study(study_dir).ranked.iloc[0]["run_name"])
    zip_path = study_dir / f"{top}.research.zip"
    zip_path.unlink()
    out = tmp_path / "missing.yaml"
    with pytest.raises(StudyPromoteError, match="zip"):
        promote_study(study_dir, output=out, top_n=1, admit_tod="auto")
    assert not out.exists()


def test_admit_followup_refuses_thin_bucket(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path, open_r=[1.0] * 5, min_trades=30)
    out = tmp_path / "thin.yaml"
    with pytest.raises(StudyPromoteError, match="thin"):
        promote_study(study_dir, output=out, top_n=1, admit_tod="auto")
    assert not out.exists()


def test_admit_followup_refuses_avg_r_tie(tmp_path: Path):
    study_dir = _write_admit_fixture(
        tmp_path,
        open_r=[1.0] * 35,
        morning_r=[1.0] * 35,
    )
    out = tmp_path / "tie.yaml"
    with pytest.raises(StudyPromoteError, match="tied"):
        promote_study(study_dir, output=out, top_n=1, admit_tod="auto")
    assert not out.exists()


def test_admit_tod_replaces_stale_parent_lineage(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    spec_path = study_dir / "study.spec.yaml"
    spec = load_study_spec(spec_path)
    spec["study"]["lineage"] = {
        "parent_output_dir": "/tmp/grandparent",
        "parent_identity_hash": "stalehash",
        "parent_run_name": "cell_old",
        "admit": {
            "group": "entry_rth_segment",
            "value": "rth_midday",
            "rule": "briefing_best_avg_r",
            "min_trades": 30,
            "thin": False,
        },
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    out = tmp_path / "admit_replace.yaml"
    promote_study(study_dir, output=out, top_n=1, admit_tod="auto")
    draft = load_study_spec(out)
    lineage = draft["study"]["lineage"]
    assert lineage["parent_output_dir"] == study_dir.resolve().as_posix()
    assert lineage["parent_run_name"] != "cell_old"
    assert lineage["admit"]["value"] == "rth_open_30m"
    assert lineage["parent_identity_hash"] != "stalehash"


def test_default_promote_strips_parent_lineage(tmp_path: Path):
    """RS5 promote must not copy a parent Admit child's study.lineage."""
    study_dir = _write_admit_fixture(tmp_path)
    spec_path = study_dir / "study.spec.yaml"
    spec = load_study_spec(spec_path)
    spec["study"]["lineage"] = {
        "parent_output_dir": "/tmp/grandparent",
        "parent_identity_hash": "stalehash",
        "parent_run_name": "cell_old",
        "admit": {
            "group": "entry_rth_segment",
            "value": "rth_open_30m",
            "rule": "briefing_best_avg_r",
            "min_trades": 30,
            "thin": False,
        },
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    out = tmp_path / "survivors.yaml"
    promote_study(study_dir, output=out, top_n=1)
    draft = load_study_spec(out)
    assert "lineage" not in draft["study"]
    assert "entry_window" not in draft["study"]["constants"]
    assert "entry_window" not in draft["study"]["constants"].get("backtest", {})


def test_admit_run_name_without_admit_tod_refused(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    top = str(report_study(study_dir).ranked.iloc[0]["run_name"])
    out = tmp_path / "flag.yaml"
    with pytest.raises(StudyPromoteError, match="--admit-tod"):
        promote_study(study_dir, output=out, top_n=1, admit_run_name=top)
    assert not out.exists()


def test_cli_study_promote_admit_tod_default_top_n_refused(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    out = tmp_path / "cli_default_topn.yaml"
    code = cli_main(
        ["study", "promote", str(study_dir), "--output", str(out), "--admit-tod", "auto"]
    )
    assert code == 2
    assert not out.exists()


def test_cli_study_promote_admit_tod(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    out = tmp_path / "cli_admit.yaml"
    code = cli_main(
        [
            "study",
            "promote",
            str(study_dir),
            "--output",
            str(out),
            "--top-n",
            "1",
            "--admit-tod",
        ]
    )
    assert code == 0
    draft = load_study_spec(out)
    assert draft["study"]["constants"]["backtest"]["entry_window"]["enabled"] is True
    assert draft["study"]["lineage"]["admit"]["value"] == "rth_open_30m"


def test_cli_promote_help_mentions_admit_flags():
    from thesistester.cli import _parser

    parser = _parser()
    study = None
    for action in parser._subparsers._group_actions:
        study = action.choices.get("study")
    assert study is not None
    promote = None
    expand = run = report = listing = None
    for action in study._subparsers._group_actions:
        promote = action.choices.get("promote")
        expand = action.choices.get("expand")
        run = action.choices.get("run")
        report = action.choices.get("report")
        listing = action.choices.get("list")
    assert promote is not None
    promote_help = promote.format_help()
    assert "--admit-tod" in promote_help
    assert "--admit-run-name" in promote_help
    assert "--tod-group" in promote_help
    assert "--allow-thin" in promote_help
    for cmd in (expand, run, report, listing):
        assert cmd is not None
        text = cmd.format_help()
        assert "--admit-tod" not in text
        assert "--admit-run-name" not in text
        assert "--tod-group" not in text
        assert "--allow-thin" not in text


def test_select_admit_bucket_prefers_non_warning_and_refuses_tie():
    frame = pd.DataFrame(
        {
            "entry_rth_segment": ["rth_open_30m", "rth_morning"],
            "avg_r": [0.4, 0.9],
            "trade_count": [40, 40],
            "sample_warning": [False, False],
        }
    )
    picked = select_admit_bucket(frame, min_trades=30)
    assert picked["value"] == "rth_morning"
    prefer_solid = pd.DataFrame(
        {
            "entry_rth_segment": ["rth_open_30m", "rth_morning"],
            "avg_r": [0.4, 0.9],
            "trade_count": [40, 10],
            "sample_warning": [False, True],
        }
    )
    solid = select_admit_bucket(prefer_solid, min_trades=30)
    assert solid["value"] == "rth_open_30m"
    tied = frame.copy()
    tied.loc[:, "avg_r"] = 0.5
    with pytest.raises(AdmitFollowupError, match="tied"):
        select_admit_bucket(tied, min_trades=30)


def test_builder_hydrate_emit_preserves_admit_windows(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    out = tmp_path / "admit_hydrate.yaml"
    promote_study(study_dir, output=out, top_n=1, admit_tod="auto")
    raw = load_study_spec(out)
    hydrated = hydrate_study_draft(raw)
    re_emitted = emit_study_spec(hydrated)
    assert re_emitted["study"]["lineage"]["admit"]["value"] == "rth_open_30m"
    window = re_emitted["study"]["constants"]["backtest"]["entry_window"]
    assert window["enabled"] is True
    assert window["rth_segments"] == ["rth_open_30m"]
    assert re_emitted["study"]["constants"]["grid"]["entry_window"] == window
    assert re_emitted["study"]["constants"]["entry_window"] == window


def test_builder_default_omits_lineage_and_hydrates_when_present():
    default = default_study_draft()
    assert default.lineage is None
    emitted = emit_study_spec(default)
    assert "lineage" not in emitted["study"]

    study_dir_name = "pdPOC_mini_admit_rth_open_30m"
    raw = emit_study_spec(default)
    raw["study"]["name"] = study_dir_name
    raw["study"]["output_dir"] = f"results/studies/{study_dir_name}"
    raw["study"]["lineage"] = {
        "parent_output_dir": "/tmp/parent",
        "parent_identity_hash": "deadbeef",
        "parent_run_name": "cell_000",
        "admit": {
            "group": "entry_rth_segment",
            "value": "rth_open_30m",
            "rule": "briefing_best_avg_r",
            "min_trades": 30,
            "thin": False,
        },
    }
    hydrated = hydrate_study_draft(raw)
    assert hydrated.lineage is not None
    assert hydrated.lineage["parent_run_name"] == "cell_000"
    re_emitted = emit_study_spec(hydrated)
    assert re_emitted["study"]["lineage"]["admit"]["value"] == "rth_open_30m"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def test_admit_followup_import_allow_list():
    imported = _imported_modules(Path("thesistester/study/admit_followup.py"))
    banned = (
        "thesistester.study.execute",
        "thesistester.study.launch",
        "thesistester.study.viewer",
        "thesistester.study.cli_study",
        "thesistester.cli",
        "thesistester.study.promote",
        "streamlit",
        "pages",
        "thesistester.api",
    )
    for name in banned:
        assert name not in imported
    calls = {
        node.func.id
        for node in ast.walk(ast.parse(Path("thesistester/study/admit_followup.py").read_text()))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "run_batch" not in calls
    assert "run_study" not in calls


def test_viewer_and_briefing_do_not_import_admit_followup():
    for path in (
        Path("thesistester/study/viewer.py"),
        Path("thesistester/study/briefing.py"),
    ):
        imported = _imported_modules(path)
        assert "thesistester.study.admit_followup" not in imported
        assert "thesistester.study.promote" not in imported
