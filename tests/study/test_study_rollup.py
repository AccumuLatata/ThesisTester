"""RS-D4 per-cell diagnostic rollup — compose-only, not_run when batteries absent."""

from __future__ import annotations

import ast
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from thesistester.cli import main as cli_main
from thesistester.study.rollup import (
    NOT_RUN,
    PRESENT,
    ROLLUP_COLUMNS,
    StudyRollupError,
    build_rollup_frame,
    rollup_study,
)
from tests.study.test_study_report import _write_report_fixture


def _inject_bundle_json(study_dir: Path, run_name: str, members: dict[str, dict]) -> None:
    """Rewrite one research zip with additional JSON members (keep trade_summary)."""
    path = study_dir / f"{run_name}.research.zip"
    assert path.is_file()
    with zipfile.ZipFile(path, "r") as archive:
        existing = {name: archive.read(name) for name in archive.namelist()}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in existing.items():
            archive.writestr(name, payload)
        for name, payload in members.items():
            archive.writestr(name, json.dumps(payload).encode("utf-8"))
    path.write_bytes(buffer.getvalue())


def test_default_fixture_batteries_are_not_run(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    result = rollup_study(study_dir)
    assert result.cell_count == 4
    assert list(result.frame.columns) == list(ROLLUP_COLUMNS)
    assert (result.frame["wfa_battery"] == NOT_RUN).all()
    assert (result.frame["validation_battery"] == NOT_RUN).all()
    assert (result.frame["overfitting_battery"] == NOT_RUN).all()
    assert result.frame["overfitting_pbo"].isna().all()
    assert result.frame["overfitting_dsr"].isna().all()
    assert "compose" in result.markdown.lower() or "composes" in result.markdown.lower()
    assert "cross-cell" in result.markdown.lower()
    assert (study_dir / "study.rollup.csv").is_file()
    assert (study_dir / "study.rollup.md").is_file()


def test_composes_index_wfa_and_bundle_overfitting(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    index = pd.read_csv(study_dir / "results_index.csv")
    name = str(index.iloc[0]["run_name"])
    index.loc[index["run_name"] == name, "wfa_fold_count"] = 3
    index.loc[index["run_name"] == name, "wfa_valid_fold_count"] = 2
    index.loc[index["run_name"] == name, "wfa_median_test_expectancy_r"] = 0.12
    # Column may be float64 when all-null from CSV; allow string status.
    index["validation_trade_count_status"] = index["validation_trade_count_status"].astype(object)
    index.loc[index["run_name"] == name, "validation_trade_count_status"] = "reasonable"
    index.to_csv(study_dir / "results_index.csv", index=False)

    _inject_bundle_json(
        study_dir,
        name,
        {
            "walk_forward_meta.json": {
                "walk_forward_summary": {
                    "fold_count": 3,
                    "valid_fold_count": 2,
                    "median_test_expectancy_r": 0.12,
                    "stitched_oos_total_r": 0.4,
                    "status": "ok",
                    "stitched_oos_status": "ok",
                }
            },
            "validation_summary.json": {
                "validation_summary": {
                    "trade_count": {"status": "reasonable"},
                    "grid_overfit": {"risk_level": "low"},
                }
            },
            "overfitting_summary.json": {
                "overfitting_summary": {
                    "schema_version": 1,
                    "available": True,
                    "pbo": {"available": True, "pbo": 0.25},
                    "deflated_sharpe": {"dsr": 0.1},
                }
            },
        },
    )

    frame = build_rollup_frame(study_dir)
    row = frame.loc[frame["run_name"] == name].iloc[0]
    assert row["wfa_battery"] == PRESENT
    assert int(row["wfa_fold_count"]) == 3
    assert row["wfa_status"] == "ok"
    assert row["validation_battery"] == PRESENT
    assert row["validation_grid_overfit_risk"] == "low"
    assert row["overfitting_battery"] == PRESENT
    assert row["overfitting_available"] is True or row["overfitting_available"] == True
    assert float(row["overfitting_pbo"]) == pytest.approx(0.25)
    assert float(row["overfitting_dsr"]) == pytest.approx(0.1)

    # Other cells remain not_run for overfitting.
    others = frame.loc[frame["run_name"] != name]
    assert (others["overfitting_battery"] == NOT_RUN).all()


def test_rollup_does_not_invent_cross_cell_pbo():
    source = Path("thesistester/study/rollup.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned_calls = {"cscv_pbo", "deflated_sharpe_ratio", "run_batch", "run_experiment"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in banned_calls:
                pytest.fail(f"rollup must not call {func.id}")
            if isinstance(func, ast.Attribute) and func.attr in banned_calls:
                pytest.fail(f"rollup must not call .{func.attr}")
    assert "cross-cell" in source.lower() or "cross_cell" in source


def test_cli_study_rollup(tmp_path: Path, capsys):
    study_dir = _write_report_fixture(tmp_path)
    code = cli_main(["study", "rollup", str(study_dir)])
    assert code == 0
    captured = capsys.readouterr().out
    assert "Study rollup" in captured
    assert "not_run" in captured
    assert (study_dir / "study.rollup.csv").is_file()


def test_rollup_missing_index_fails(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(StudyRollupError, match="results_index"):
        rollup_study(empty)
