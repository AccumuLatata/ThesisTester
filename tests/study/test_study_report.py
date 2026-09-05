"""RS4 study report — join, ranking, OTF Δ, honesty, PF from bundles."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from thesistester.cli import main as cli_main
from thesistester.setup import normalize_otf_filter_config
from thesistester.study.expand import expand_study_to_directory
from thesistester.study.report import (
    StudyReportError,
    otf_canonical_key,
    report_study,
)
from thesistester.study.schema import STUDY_SCHEMA_VERSION


def _bundle_bytes(*, profit_factor: float, win_rate: float = 0.5) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"included": {"backtest": True}}))
        archive.writestr(
            "trade_summary.json",
            json.dumps(
                {
                    "trade_summary": {
                        "trade_count": 40,
                        "profit_factor": profit_factor,
                        "win_rate": win_rate,
                        "expectancy_r": 0.1,
                    }
                }
            ),
        )
    return buffer.getvalue()


def _otf_off() -> dict:
    return normalize_otf_filter_config({"enabled": False})


def _write_report_fixture(
    tmp_path: Path, *, min_trades: int = 30, multiple_testing: str = "warn"
) -> Path:
    """Synthetic completed study dir: 4 cells (2 partners × 2 OTF)."""
    study_dir = tmp_path / "study_out"
    study_dir.mkdir()

    spec = {
        "schema_version": STUDY_SCHEMA_VERSION,
        "study": {
            "name": "pdPOC_rs4",
            "confirm_above_runs": 200,
            "workers": 1,
            "dataset": {
                "path": "bars.csv",
                "instrument": "ES",
                "source_timezone": "America/New_York",
            },
            "levels": {
                "sma_lengths": [50],
                "ema_lengths": [21],
                "sma_timeframes": ["1min"],
                "ema_timeframes": ["5min"],
            },
            "constants": {
                "direction": "both",
                "tolerance_ticks": 0,
                "min_confluences": 2,
                "max_confluences": 2,
                "min_valid_confluences": 1,
                "naked_only": False,
                "naked_requirement": "any",
                "trigger_params": {},
                "backtest": {
                    "stop_loss_ticks": 8,
                    "take_profit_ticks": 16,
                    "exposure_policy": "single_position",
                },
                "grid": {"enabled": False},
                "validation": {"enabled": False},
                "walk_forward": {"enabled": False},
            },
            "factors": {
                "core_level": ["ONH"],
                "partner_levels": [["SMA_50_1min"], ["EMA_21_5min"]],
                "confluence_mode": ["global_cluster"],
                "trigger": ["touch"],
                "trigger_timeframe": ["base"],
                "otf": [{"enabled": False}, {"enabled": True, "timeframes": ["5m"]}],
            },
            "mode_rules": {
                "global_cluster": {
                    "selected_levels": ["${core_level}", "${partner_levels...}"],
                },
            },
            "report": {
                "primary_metric": "expectancy_r",
                "secondary_metrics": [
                    "profit_factor",
                    "max_drawdown_r",
                    "trade_count",
                    "total_r",
                ],
                "min_trades": min_trades,
                "group_by": ["partner_levels", "otf"],
                "otf_baseline": {"enabled": False},
                "multiple_testing": multiple_testing,
            },
        },
    }
    expand_study_to_directory(spec, study_dir)
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    factor_map = expansion["factor_map"]
    assert len(factor_map) == 4

    # Assign metrics: one low-N cell; OTF-on beats baseline on SMA partner.
    rows = []
    for name, factors in factor_map.items():
        partners = factors["partner_levels"]
        otf_enabled = bool(factors["otf"]["enabled"])
        if partners == ["SMA_50_1min"] and not otf_enabled:
            trade_count, expectancy, pf = 40, 0.10, 1.2
        elif partners == ["SMA_50_1min"] and otf_enabled:
            trade_count, expectancy, pf = 40, 0.25, 1.8
        elif partners == ["EMA_21_5min"] and not otf_enabled:
            trade_count, expectancy, pf = 40, 0.05, 1.1
        else:
            # low-N OTF variant
            trade_count, expectancy, pf = 5, 0.90, 3.0
        bundle_name = f"{name}.research.zip"
        (study_dir / bundle_name).write_bytes(_bundle_bytes(profit_factor=pf))
        rows.append(
            {
                "run_name": name,
                "bundle_hash": "abc",
                "dataset_id": "ds",
                "instrument": "ES",
                "execution_origin": "study",
                "cache_outcome": "miss",
                "trade_count": trade_count,
                "expectancy_r": expectancy,
                "total_r": expectancy * trade_count,
                "max_drawdown_r": 1.0,
                "best_grid_stop_loss_ticks": None,
                "best_grid_take_profit_ticks": None,
                "validation_trade_count_status": None,
                "wfa_fold_count": None,
                "wfa_valid_fold_count": None,
                "wfa_median_test_expectancy_r": None,
                "wfa_stitched_oos_total_r": None,
                "bundle_path": bundle_name,
                "status": "ok",
            }
        )
    pd.DataFrame(rows).sort_values("run_name").to_csv(study_dir / "results_index.csv", index=False)
    return study_dir


def test_otf_canonical_key_alias_stable():
    assert otf_canonical_key({"enabled": True, "timeframes": ["5min"]}) == otf_canonical_key(
        {"enabled": True, "timeframes": ["5m"]}
    )
    assert otf_canonical_key({"enabled": False}) == otf_canonical_key(_otf_off())


def test_overview_join_deterministic_and_complete(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    result = report_study(study_dir)
    assert len(result.overview) == 4
    assert result.overview["factors_joined"].all()
    assert set(result.overview["run_name"]) == set(
        json.loads((study_dir / "study.expansion.json").read_text())["factor_map"]
    )
    # Deterministic sort by run_name
    assert list(result.overview["run_name"]) == sorted(result.overview["run_name"])
    # Round-trip CSV
    again = report_study(study_dir)
    assert again.overview.to_csv(index=False) == result.overview.to_csv(index=False)
    assert again.markdown == result.markdown


def test_min_trades_splits_ranked_and_low_n(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    result = report_study(study_dir)
    assert len(result.ranked) == 3
    assert len(result.low_n) == 1
    assert len(result.unresolved) == 0
    assert int(result.low_n.iloc[0]["trade_count"]) == 5
    # Ranked ordered by expectancy_r descending
    expectancies = list(result.ranked["expectancy_r"])
    assert expectancies == sorted(expectancies, reverse=True)
    # Low-N cell must not appear in ranked
    assert result.low_n.iloc[0]["run_name"] not in set(result.ranked["run_name"])


def test_null_primary_high_n_listed_as_unresolved(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, min_trades=30)
    # Force profit_factor primary with one cell missing PF (no bundle + null index).
    spec_text = (study_dir / "study.spec.yaml").read_text(encoding="utf-8")
    import yaml

    payload = yaml.safe_load(spec_text)
    payload["study"]["report"]["primary_metric"] = "profit_factor"
    (study_dir / "study.spec.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    index = pd.read_csv(study_dir / "results_index.csv")
    # Wipe bundles and leave no index PF → all PF missing; N still high for 3 cells.
    for bundle in study_dir.glob("*.research.zip"):
        bundle.unlink()
    index["bundle_path"] = None
    index.to_csv(study_dir / "results_index.csv", index=False)
    result = report_study(study_dir)
    assert len(result.ranked) == 0
    assert len(result.unresolved) == 3
    assert "Unresolved primary metric" in result.markdown
    assert "unresolved primary: **3**" in result.markdown
    # Group summaries must not count null-primary cells.
    for summary in result.group_summaries.values():
        assert int(summary["cell_count"].sum()) == 0


def test_otf_delta_vs_baseline_alias_stable(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    result = report_study(study_dir)
    # SMA partner has both baseline + OTF-on with N>=30 → one delta row.
    # EMA partner's OTF-on is low-N but still emits a delta row.
    assert len(result.otf_delta) == 2
    sma_rows = [
        row for _, row in result.otf_delta.iterrows() if "SMA_50_1min" in row["non_otf_key"]
    ]
    assert len(sma_rows) == 1
    assert sma_rows[0]["delta_expectancy_r"] == pytest.approx(0.15)
    assert sma_rows[0]["meets_min_trades"] in (True, True)
    # Baseline key is canonical disabled OTF
    assert sma_rows[0]["factor_otf_baseline"] == otf_canonical_key({"enabled": False})
    assert sma_rows[0]["factor_otf_variant"] == otf_canonical_key(
        {"enabled": True, "timeframes": ["5min"]}
    )


def test_markdown_includes_multiple_testing_honesty(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, multiple_testing="warn")
    result = report_study(study_dir)
    assert "multiple-testing" in result.markdown.lower() or "multiple-testing" in result.markdown
    assert "not a validated edge" in result.markdown.lower() or "validated edge" in result.markdown
    assert "Top descriptive cell" in result.markdown
    assert "best_grid_stop_loss_ticks" in result.markdown
    assert "Time-of-day is not a StudySpec factor" in result.markdown
    assert (study_dir / "study.overview.md").is_file()
    assert "multiple-testing" in (study_dir / "study.overview.md").read_text().lower() or (
        "validated edge" in (study_dir / "study.overview.md").read_text()
    )


def test_multiple_testing_error_suppresses_best_cell(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path, multiple_testing="error")
    result = report_study(study_dir)
    assert result.best_cell_suppressed is True
    assert "best-cell crowning suppressed" in result.markdown
    assert "Top descriptive cell" not in result.markdown


def test_profit_factor_from_bundle_trade_summary(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    result = report_study(study_dir)
    assert result.overview["profit_factor_source"].eq("bundle").all()
    # SMA baseline PF 1.2 from bundle
    expansion = json.loads((study_dir / "study.expansion.json").read_text())
    for name, factors in expansion["factor_map"].items():
        if factors["partner_levels"] == ["SMA_50_1min"] and not factors["otf"]["enabled"]:
            row = result.overview.loc[result.overview["run_name"] == name].iloc[0]
            assert row["profit_factor"] == pytest.approx(1.2)
            break
    else:
        pytest.fail("SMA baseline cell missing")


def test_profit_factor_prefers_index_when_present(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    index = pd.read_csv(study_dir / "results_index.csv")
    index["profit_factor"] = 9.9
    index.to_csv(study_dir / "results_index.csv", index=False)
    result = report_study(study_dir)
    assert result.overview["profit_factor_source"].eq("index").all()
    assert all(pf == pytest.approx(9.9) for pf in result.overview["profit_factor"])


def test_index_pf_still_fills_win_rate_from_bundle(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    index = pd.read_csv(study_dir / "results_index.csv")
    index["profit_factor"] = 9.9
    # No win_rate column on the index — must still resolve from bundle.
    index.to_csv(study_dir / "results_index.csv", index=False)
    result = report_study(study_dir)
    assert result.overview["profit_factor_source"].eq("index").all()
    assert all(pf == pytest.approx(9.9) for pf in result.overview["profit_factor"])
    assert all(wr == pytest.approx(0.5) for wr in result.overview["win_rate"])


def test_orphan_index_rows_not_ranked_or_crowned(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    index = pd.read_csv(study_dir / "results_index.csv")
    orphan = {
        "run_name": "orphan_not_in_expansion",
        "bundle_hash": "xyz",
        "dataset_id": "ds",
        "instrument": "ES",
        "execution_origin": "study",
        "cache_outcome": "miss",
        "trade_count": 999,
        "expectancy_r": 99.0,
        "total_r": 990.0,
        "max_drawdown_r": 0.01,
        "best_grid_stop_loss_ticks": None,
        "best_grid_take_profit_ticks": None,
        "validation_trade_count_status": None,
        "wfa_fold_count": None,
        "wfa_valid_fold_count": None,
        "wfa_median_test_expectancy_r": None,
        "wfa_stitched_oos_total_r": None,
        "bundle_path": None,
        "status": "ok",
    }
    index = pd.concat([index, pd.DataFrame([orphan])], ignore_index=True)
    index.to_csv(study_dir / "results_index.csv", index=False)
    result = report_study(study_dir)
    assert "orphan_not_in_expansion" in set(result.overview["run_name"])
    orphan_row = result.overview.loc[result.overview["run_name"] == "orphan_not_in_expansion"].iloc[
        0
    ]
    assert bool(orphan_row["factors_joined"]) is False
    assert "orphan_not_in_expansion" not in set(result.ranked["run_name"])
    assert "orphan_not_in_expansion" not in set(result.low_n["run_name"])
    assert "orphan_not_in_expansion" not in result.markdown
    assert result.ranked.iloc[0]["run_name"] != "orphan_not_in_expansion"


def test_duplicate_run_name_fails_closed(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    index = pd.read_csv(study_dir / "results_index.csv")
    index = pd.concat([index, index.iloc[[0]]], ignore_index=True)
    index.to_csv(study_dir / "results_index.csv", index=False)
    with pytest.raises(StudyReportError, match="duplicate run_name"):
        report_study(study_dir)


def test_coerce_float_accepts_numpy_scalars():
    import numpy as np

    from thesistester.study.report import _coerce_float

    assert _coerce_float(np.float64(1.25)) == pytest.approx(1.25)
    assert _coerce_float(np.int64(3)) == pytest.approx(3.0)
    assert _coerce_float(np.nan) is None
    assert _coerce_float(True) is None


def test_group_summaries_present(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    result = report_study(study_dir)
    assert "partner_levels" in result.group_summaries
    assert "otf" in result.group_summaries
    # Ranked-eligible only (3 cells) → SMA has 2, EMA has 1
    partners = result.group_summaries["partner_levels"]
    sma = partners.loc[partners["partner_levels"] == "SMA_50_1min"].iloc[0]
    assert int(sma["cell_count"]) == 2


def test_cli_study_report(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    index_before = (study_dir / "results_index.csv").read_bytes()
    code = cli_main(["study", "report", str(study_dir)])
    assert code == 0
    assert (study_dir / "study.overview.csv").is_file()
    assert (study_dir / "study.overview.md").is_file()
    assert (study_dir / "study.otf_delta.csv").is_file()
    assert (study_dir / "study.direction.csv").is_file()
    assert (study_dir / "results_index.csv").read_bytes() == index_before
    direction = pd.read_csv(study_dir / "study.direction.csv")
    assert "run_name" in direction.columns
    assert "directional_integrity" in direction.columns


def test_rebuild_direction_via_study_report_cli(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    trades = pd.DataFrame({"direction": ["long", "long"], "r_multiple": [0.2, 0.1]})
    parquet_buf = io.BytesIO()
    trades.to_parquet(parquet_buf, index=False)
    for bundle in study_dir.glob("*.research.zip"):
        with zipfile.ZipFile(bundle, "a") as archive:
            archive.writestr("trades.parquet", parquet_buf.getvalue())
    before = pd.read_csv(study_dir / "results_index.csv")
    before_cols = list(before.columns)
    code = cli_main(["study", "report", str(study_dir), "--rebuild-direction"])
    assert code == 0
    after = pd.read_csv(study_dir / "results_index.csv")
    assert after.loc[:, before_cols].to_csv(index=False) == before.to_csv(index=False)
    assert (after["directional_integrity"] == "long_only").all()
    assert (after["short_trade_count"] == 0).all()
    assert after["collision_pairs"].isna().all()
    direction = pd.read_csv(study_dir / "study.direction.csv")
    assert (direction["directional_integrity"] == "long_only").all()


def test_report_missing_index_fails(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    (study_dir / "results_index.csv").unlink()
    with pytest.raises(StudyReportError, match="results_index"):
        report_study(study_dir)


def test_report_rank_stays_primary_metric_not_null(tmp_path: Path):
    study_dir = _write_report_fixture(tmp_path)
    index = pd.read_csv(study_dir / "results_index.csv")
    ranked_names = list(
        index.loc[index["trade_count"] >= 30].sort_values("expectancy_r", ascending=False)[
            "run_name"
        ]
    )
    better_e, worse_e = ranked_names[0], ranked_names[-1]
    index.loc[index["run_name"] == worse_e, "random_p_value_ge"] = 0.01
    index.loc[index["run_name"] == worse_e, "expectancy_minus_null_r"] = 0.40
    index.loc[index["run_name"] == better_e, "random_p_value_ge"] = 0.40
    index.loc[index["run_name"] == better_e, "expectancy_minus_null_r"] = 0.01
    index.to_csv(study_dir / "results_index.csv", index=False)
    result = report_study(study_dir)
    assert result.ranked.iloc[0]["run_name"] == better_e
    assert float(result.ranked.iloc[0]["expectancy_r"]) > float(
        result.ranked.loc[result.ranked["run_name"] == worse_e, "expectancy_r"].iloc[0]
    )
    assert "expectancy_minus_null_r" in result.markdown
    assert "random_p_value_ge" in result.markdown
