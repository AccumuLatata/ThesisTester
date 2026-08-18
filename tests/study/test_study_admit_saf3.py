"""SAF3: --tod-group, --allow-thin, catalog parent. Inspect stays RTH + thin-refuse."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from thesistester.cli import main as cli_main
from thesistester.study.admit_followup import ADMIT_TOD_GROUP, select_admit_bucket
from thesistester.study.briefing import TOD_GROUP_COL, extract_cell_time_of_day
from thesistester.study.promote import (
    StudyPromoteError,
    draft_admit_followup_yaml,
    promote_study,
)
from thesistester.study.report import report_study
from thesistester.study.schema import load_study_spec
from tests.study.test_study_admit_followup import _write_admit_fixture


def test_tod_group_hour_emits_clock_range(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    out = tmp_path / "hour.yaml"
    promote_study(
        study_dir,
        output=out,
        top_n=1,
        admit_tod="auto",
        tod_group="entry_hour_bucket",
    )
    draft = load_study_spec(out)
    window = draft["study"]["constants"]["backtest"]["entry_window"]
    assert window["enabled"] is True
    assert window["mode"] == "clock_range"
    assert window["start_time"] == "09:00"
    assert window["end_time"] == "10:00"
    lineage = draft["study"]["lineage"]
    assert lineage["admit"]["group"] == "entry_hour_bucket"
    assert lineage["admit"]["value"] == "09:00"
    assert lineage["admit"]["thin"] is False
    assert draft["study"]["name"].endswith("_admit_0900")
    assert draft["study"]["constants"]["grid"]["entry_window"] == window
    assert draft["study"]["constants"]["entry_window"] == window


def test_tod_group_and_allow_thin_require_admit_tod(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    out = tmp_path / "flags.yaml"
    with pytest.raises(StudyPromoteError, match="--tod-group / --allow-thin require --admit-tod"):
        promote_study(study_dir, output=out, top_n=1, tod_group="entry_hour_bucket")
    assert not out.exists()
    with pytest.raises(StudyPromoteError, match="--tod-group / --allow-thin require --admit-tod"):
        promote_study(study_dir, output=out, top_n=1, allow_thin=True)
    assert not out.exists()


def test_allow_thin_drafts_thin_bucket_and_sets_lineage_flag(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path, open_r=[1.0] * 5, min_trades=30)
    out = tmp_path / "thin_ok.yaml"
    with pytest.raises(StudyPromoteError, match="thin"):
        promote_study(study_dir, output=out, top_n=1, admit_tod="auto")
    assert not out.exists()
    promote_study(study_dir, output=out, top_n=1, admit_tod="auto", allow_thin=True)
    draft = load_study_spec(out)
    assert draft["study"]["lineage"]["admit"]["thin"] is True
    assert draft["study"]["constants"]["backtest"]["entry_window"]["enabled"] is True


def test_admit_tod_without_new_flags_still_rth_and_refuses_thin(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    out = tmp_path / "default_rth.yaml"
    promote_study(study_dir, output=out, top_n=1, admit_tod="auto")
    draft = load_study_spec(out)
    assert draft["study"]["lineage"]["admit"]["group"] == ADMIT_TOD_GROUP
    assert draft["study"]["constants"]["backtest"]["entry_window"]["mode"] == "rth_segments"


def test_inspect_helper_stays_rth_and_refuses_thin(tmp_path: Path):
    thin = tmp_path / "thin"
    thin.mkdir()
    thin_dir = _write_admit_fixture(thin, open_r=[1.0] * 5, min_trades=30)
    top = str(report_study(thin_dir).ranked.iloc[0]["run_name"])
    with pytest.raises(StudyPromoteError, match="thin"):
        draft_admit_followup_yaml(thin_dir, admit_run_name=top)


def test_extract_cell_time_of_day_default_remains_rth(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    top = str(report_study(study_dir).ranked.iloc[0]["run_name"])
    zip_path = study_dir / f"{top}.research.zip"
    display, best, _caption = extract_cell_time_of_day(zip_path, min_trades=1)
    assert TOD_GROUP_COL in display.columns
    assert "entry_hour_bucket" not in display.columns
    assert best is not None
    assert best["segment"] == "rth_open_30m"
    hour, hour_best, _ = extract_cell_time_of_day(
        zip_path,
        min_trades=1,
        group_col="entry_hour_bucket",
    )
    assert "entry_hour_bucket" in hour.columns
    assert hour_best is not None
    assert hour_best["segment"] == "09:00"


def test_cli_tod_group_hour_and_flags_without_admit_tod(tmp_path: Path):
    study_dir = _write_admit_fixture(tmp_path)
    out = tmp_path / "cli_hour.yaml"
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
            "--tod-group",
            "entry_hour_bucket",
        ]
    )
    assert code == 0
    payload = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert payload["study"]["constants"]["backtest"]["entry_window"]["mode"] == "clock_range"

    refused = tmp_path / "cli_no_admit.yaml"
    code = cli_main(
        [
            "study",
            "promote",
            str(study_dir),
            "--output",
            str(refused),
            "--tod-group",
            "entry_hour_bucket",
        ]
    )
    assert code == 2
    assert not refused.exists()


def test_select_admit_bucket_allow_thin_keeps_thin_true():
    frame = pd.DataFrame(
        {
            "entry_rth_segment": ["rth_open_30m"],
            "avg_r": [1.2],
            "trade_count": [4],
            "sample_warning": [True],
        }
    )
    with pytest.raises(Exception, match="thin"):
        select_admit_bucket(frame, min_trades=30)
    picked = select_admit_bucket(frame, min_trades=30, allow_thin=True)
    assert picked["thin"] is True
    assert picked["value"] == "rth_open_30m"


def test_page_inspect_stays_dumb_no_tod_group_ui():
    page = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    assert "Draft Admit follow-up" in page
    assert "--tod-group" not in page
    assert "allow-thin" not in page
    assert "entry_hour_bucket" not in page
    assert '"parent"' in page or "'parent'" in page
