"""SV5 study briefing — headline, per-cell SL/TP grid, NY RTH ToD."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from thesistester.study.briefing import (
    BRIEFING_HONESTY,
    build_study_briefing,
    extract_cell_grid,
    extract_cell_time_of_day,
    resolve_cell_bundle,
    spec_grid_enabled,
)
from thesistester.study.ledger import empty_ledger, save_ledger
from thesistester.study.report import RESULTS_INDEX, report_study
from thesistester.study.viewer import load_study_view, peek_study_cell
from tests.study.test_study_report import _write_report_fixture


def _grid_zip_bytes() -> bytes:
    trades = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(
                [
                    "2026-06-02 09:35:00",
                    "2026-06-02 09:48:00",
                    "2026-06-02 10:15:00",
                    "2026-06-02 12:00:00",
                ]
            ).tz_localize("America/New_York"),
            "exit_timestamp": pd.to_datetime(
                [
                    "2026-06-02 09:40:00",
                    "2026-06-02 09:55:00",
                    "2026-06-02 10:20:00",
                    "2026-06-02 12:10:00",
                ]
            ).tz_localize("America/New_York"),
            "r_multiple": [1.0, 0.5, -0.5, -1.0],
        }
    )
    grid = pd.DataFrame(
        {
            "stop_loss_ticks": [20.0, 40.0, 20.0],
            "take_profit_ticks": [40.0, 80.0, 80.0],
            "trade_count": [12, 12, 12],
            "expectancy_r": [0.10, 0.40, 0.20],
            "profit_factor": [1.2, 1.8, 1.4],
            "win_rate": [0.5, 0.6, 0.55],
        }
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "trade_summary.json",
            json.dumps(
                {
                    "trade_summary": {
                        "trade_count": 4,
                        "profit_factor": 1.8,
                        "win_rate": 0.5,
                        "expectancy_r": 0.0,
                    }
                }
            ),
        )
        archive.writestr(
            "best_grid_result.json",
            json.dumps(
                {
                    "stop_loss_ticks": 40.0,
                    "take_profit_ticks": 80.0,
                    "expectancy_r": 0.40,
                    "trade_count": 12,
                }
            ),
        )
        trades_buf = io.BytesIO()
        trades.to_parquet(trades_buf, index=False)
        archive.writestr("trades.parquet", trades_buf.getvalue())
        grid_buf = io.BytesIO()
        grid.to_parquet(grid_buf, index=False)
        archive.writestr("grid_results.parquet", grid_buf.getvalue())
    return buffer.getvalue()


def _write_grid_enabled_spec(study_dir: Path) -> None:
    import yaml

    spec_path = study_dir / "study.spec.yaml"
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    payload["study"]["constants"]["grid"] = {
        "enabled": True,
        "stop_loss_ticks_values": [20, 40],
        "take_profit_ticks_values": [40, 80],
    }
    spec_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_extract_grid_and_tod_from_zip(tmp_path: Path):
    zip_path = tmp_path / "cell.research.zip"
    zip_path.write_bytes(_grid_zip_bytes())
    best, display, caption = extract_cell_grid(zip_path)
    assert best is not None
    assert best["stop_loss_ticks"] == 40.0
    assert not display.empty
    assert float(display.iloc[0]["expectancy_r"]) == pytest.approx(0.40)
    assert "per-cell grid" in (caption or "")

    tod, tod_best, tod_caption = extract_cell_time_of_day(zip_path, min_trades=1)
    assert not tod.empty
    assert tod_best is not None
    assert tod_best["segment"] == "rth_open_30m"
    assert "Post-hoc" in (tod_caption or "")


def test_extract_missing_members_are_captions(tmp_path: Path):
    zip_path = tmp_path / "empty.research.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("manifest.json", "{}")
    best, display, grid_caption = extract_cell_grid(zip_path)
    assert best is None
    assert display.empty
    assert "No SL/TP grid" in (grid_caption or "")
    tod, tod_best, tod_caption = extract_cell_time_of_day(zip_path)
    assert tod.empty
    assert tod_best is None
    assert "trades.parquet is missing" in (tod_caption or "")


def test_resolve_cell_bundle_refuses_escape(tmp_path: Path):
    study_dir = tmp_path / "study"
    study_dir.mkdir()
    secret = tmp_path / "secret.research.zip"
    secret.write_bytes(_grid_zip_bytes())
    assert resolve_cell_bundle(study_dir, str(secret.resolve())) is None
    assert resolve_cell_bundle(study_dir, "../secret.research.zip") is None


def test_briefing_uses_ranked_cell_and_zip(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    _write_grid_enabled_spec(study_dir)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    winner = None
    for name, factors in expansion["factor_map"].items():
        if factors["partner_levels"] == ["SMA_50_1min"] and factors["otf"]["enabled"]:
            winner = name
            break
    assert winner is not None
    (study_dir / f"{winner}.research.zip").write_bytes(_grid_zip_bytes())
    index = pd.read_csv(study_dir / RESULTS_INDEX)
    index.loc[index["run_name"] == winner, "best_grid_stop_loss_ticks"] = 40
    index.loc[index["run_name"] == winner, "best_grid_take_profit_ticks"] = 80
    index.to_csv(study_dir / RESULTS_INDEX, index=False)

    report = report_study(study_dir, write_artifacts=False)
    briefing = build_study_briefing(report, study_dir=study_dir)
    assert briefing.source == "ranked"
    assert briefing.run_name == winner
    assert "SMA_50_1min" in briefing.headline
    assert "best SL/TP 40/80" in briefing.headline
    assert "rth_open_30m" in briefing.headline
    assert briefing.tod_best.get("segment") == "rth_open_30m"
    assert BRIEFING_HONESTY in briefing.caveats
    assert spec_grid_enabled(study_dir) is True


def test_briefing_falls_back_to_low_n_when_nothing_ranked(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=100)
    report = report_study(study_dir, write_artifacts=False)
    assert report.ranked.empty
    briefing = build_study_briefing(report, study_dir=study_dir)
    assert briefing.source == "low_n"
    assert briefing.below_min_trades is True
    assert "among finished cells" in briefing.headline
    assert "below min_trades=100" in briefing.headline


def test_load_study_view_briefing_and_peek_grid_tod(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=1)
    _write_grid_enabled_spec(study_dir)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    names = sorted(expansion["factor_map"])
    ledger = empty_ledger(
        study_identity_hash=str(expansion["study_identity_hash"]),
        run_names=names,
    )
    for name in names:
        ledger["cells"][name]["status"] = "ok"
        ledger["cells"][name]["bundle_path"] = f"{name}.research.zip"
        (study_dir / f"{name}.research.zip").write_bytes(_grid_zip_bytes())
    save_ledger(study_dir, ledger)

    model = load_study_view(study_dir, roots=(tmp_path.resolve(),))
    assert "rth_open_30m" in model.briefing.headline
    peek = peek_study_cell(model, names[0])
    assert peek.best_grid is not None
    assert peek.best_grid["stop_loss_ticks"] == 40.0
    assert not peek.grid_display.empty
    assert peek.time_of_day_best is not None
    assert peek.time_of_day_best["segment"] == "rth_open_30m"
    assert not peek.time_of_day.empty


def test_briefing_module_import_allow_list():
    import ast

    source = Path("thesistester/study/briefing.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "thesistester.study.execute" not in imported
    assert "thesistester.study.cli_study" not in imported
    assert "thesistester.cli" not in imported
    assert "plotly" not in imported
    assert "streamlit" not in imported


def test_page_briefing_and_ranked_caption_are_present():
    source = Path("pages/15_Studies.py").read_text(encoding="utf-8")
    assert "def _render_inspect_briefing" in source
    assert "Study briefing" in source
    assert "Factor cartesian" in source
    assert "_render_inspect_briefing(model)" in source
    assert "apply_research_bundle_to_session" not in source
    start = source.index("def _render_inspect_briefing")
    end = source.index("def _render_inspect(")
    briefing_src = source[start:end]
    assert "run_study" not in briefing_src
    assert "rollup_study" not in briefing_src
