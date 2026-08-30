"""SO1–SO4 / SO7 Study Observatory — fact table, CLI, page AST, lens, desks, studies pane."""

from __future__ import annotations

import ast
import csv
import io
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from thesistester.cli import main as cli_main
from thesistester.study.ledger import empty_ledger, save_ledger
from thesistester.study.observatory import (
    CLI_COLUMNS,
    DESK_SCHEMA_VERSION,
    HEATMAP_SOLO_PARTNER,
    HEATMAP_Z_MISSING,
    OBSERVATORY_HONESTY,
    PROGRAM_B_LENS_PACKET_CHROME,
    SORT_ALLOW_LIST,
    ObservatoryError,
    apply_facets,
    attach_program_b_projections,
    canonical_facet_value,
    cell_choice_labels,
    cohort_key_from_values,
    constrain_facet_selection,
    corpus_progress_counts,
    delete_observatory_desk,
    desk_class_counts,
    desk_class_for,
    displayed_min_trades,
    format_observatory_table,
    heatmap_class_z,
    list_observatory_desks,
    load_observatory_frame,
    majority_cohort_key,
    observatory_desk_from_payload,
    observatory_desk_query_state,
    observatory_desks_dir,
    observatory_studies_table,
    parse_observatory_desk,
    program_b_heatmap_cells,
    resolve_program_b_lens,
    sample_class_for,
    save_observatory_desk,
    sort_observatory_frame,
    sort_observatory_studies,
    study_choice_labels,
    unique_facet_values,
    useful_confluence_for,
    wave0_study_name_for_core,
)
from thesistester.study.viewer import CLASSIC_RESEARCH_SESSION_KEYS, STUDY_SPEC_FILENAME


def _write_study(
    parent: Path,
    name: str,
    *,
    instrument: str = "ES",
    min_trades: int = 30,
    cells: list[dict] | None = None,
    ledger_only: bool = False,
    ingest: str = "15s_primary_derive_1m",
    sl: int = 80,
    tp: int = 80,
    commission: float = 0.5,
    slippage: float = 1.0,
    trigger: str = "touch",
    trigger_tf: str = "1min",
    mode: str = "anchor_rules",
    min_valid: int = 1,
    lineage_admit: bool = False,
    dataset_id: str = "ds-a",
    study_name: str | None = None,
    core: str = "ONH",
    partners: list[str] | None = None,
) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    study_dir = parent / name
    study_dir.mkdir()
    partner_tokens = ["SMA_50_1min"] if partners is None else list(partners)
    spec_name = study_name or name
    spec: dict = {
        "schema_version": 1,
        "study": {
            "name": spec_name,
            "dataset": {
                "path": "bars.csv",
                "instrument": instrument,
                "ingestion_mode": ingest,
            },
            "constants": {
                "direction": "both",
                "tolerance_ticks": 10,
                "min_valid_confluences": min_valid,
                "backtest": {
                    "stop_loss_ticks": sl,
                    "take_profit_ticks": tp,
                    "exposure_policy": "single_position",
                    "commission_per_side": commission,
                    "slippage_ticks": slippage,
                    "flat_by_session_close": True,
                },
            },
            "factors": {
                "core_level": [core],
                "partner_levels": [partner_tokens],
                "confluence_mode": [mode],
                "trigger": [trigger],
                "trigger_timeframe": [trigger_tf],
            },
            "report": {
                "primary_metric": "expectancy_r",
                "min_trades": min_trades,
            },
        },
    }
    if lineage_admit:
        spec["study"]["lineage"] = {
            "parent_output_dir": "results/studies/parent_study",
            "admit": {
                "group": "entry_rth_segment",
                "value": "rth_open_30m",
                "rule": "briefing_best_avg_r",
                "min_trades": 30,
                "thin": False,
            },
        }
    (study_dir / STUDY_SPEC_FILENAME).write_text(
        yaml.safe_dump(spec, sort_keys=False), encoding="utf-8"
    )
    run_names = [str(row["run_name"]) for row in (cells or [])]
    if not run_names:
        run_names = ["cell_000"]
    expansion = {
        "study_identity_hash": f"hash-{name}",
        "run_count": len(run_names),
        "factor_map": {
            run_name: {
                "core_level": core,
                "partner_levels": list(partner_tokens),
                "confluence_mode": mode,
                "trigger": trigger,
                "trigger_timeframe": trigger_tf,
            }
            for run_name in run_names
        },
    }
    (study_dir / "study.expansion.json").write_text(json.dumps(expansion), encoding="utf-8")
    ledger = empty_ledger(study_identity_hash=f"hash-{name}", run_names=run_names)
    for run_name in run_names:
        ledger["cells"][run_name]["status"] = "ok" if not ledger_only else "pending"
    save_ledger(study_dir, ledger)
    if ledger_only:
        return study_dir
    rows = []
    for row in cells or []:
        rows.append(
            {
                "run_name": row["run_name"],
                "bundle_hash": "abc",
                "dataset_id": row.get("dataset_id", dataset_id),
                "instrument": row.get("instrument", instrument),
                "execution_origin": "study",
                "cache_outcome": "miss",
                "trade_count": row.get("trade_count", 40),
                "expectancy_r": row.get("expectancy_r", 0.1),
                "total_r": row.get("total_r", 4.0),
                "max_drawdown_r": row.get("max_drawdown_r", 1.0),
                "profit_factor": row.get("profit_factor", 1.2),
                "win_rate": row.get("win_rate", 0.5),
                "bundle_path": f"{row['run_name']}.research.zip",
                "status": row.get("status", "ok"),
            }
        )
    pd.DataFrame(rows).to_csv(study_dir / "results_index.csv", index=False)
    return study_dir


def test_two_studies_index_and_ledger_only(tmp_path: Path):
    indexed = _write_study(
        tmp_path / "results" / "studies",
        "alpha",
        cells=[{"run_name": "alpha_c0", "trade_count": 40, "expectancy_r": 0.12}],
    )
    ledger_only = _write_study(
        tmp_path / "results" / "studies",
        "beta_inflight",
        ledger_only=True,
    )
    (tmp_path / "results" / "studies" / "not_a_study").mkdir()
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    names = set(model.studies["study_name"])
    assert names == {"alpha", "beta_inflight"}
    assert "not_a_study" not in names
    assert list(model.frame["run_name"]) == ["alpha_c0"]
    assert str(indexed) in set(model.frame["study_dir"])
    assert str(ledger_only) in set(model.studies["study_dir"])
    assert not bool(
        model.studies.loc[model.studies["study_name"] == "beta_inflight", "index_present"].iloc[0]
    )
    progress = corpus_progress_counts(model.studies)
    assert progress["studies"] == 2
    assert progress["ok"] == 1
    assert progress["pending"] == 1
    assert progress["failed"] == 0
    assert progress["running"] == 0
    table = observatory_studies_table(model.studies)
    assert list(table["study_name"]) == ["beta_inflight", "alpha"]
    assert "run_name" not in table.columns


def test_corrupt_index_does_not_fail_sibling(tmp_path: Path):
    _write_study(
        tmp_path / "results" / "studies",
        "good",
        cells=[{"run_name": "good_c0", "trade_count": 40}],
    )
    bad = _write_study(
        tmp_path / "results" / "studies",
        "bad",
        cells=[{"run_name": "bad_c0", "trade_count": 40}],
    )
    (bad / "results_index.csv").write_text("this is not,csv\n<<<", encoding="utf-8")
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    assert list(model.frame["run_name"]) == ["good_c0"]
    bad_row = model.studies.loc[model.studies["study_name"] == "bad"].iloc[0]
    assert bad_row["error"]
    assert str(bad_row["error"]).startswith("index:")
    ranked = sort_observatory_studies(model.studies)
    assert list(ranked["study_name"]) == ["bad", "good"]


def test_load_does_not_call_report_run_rollup_or_zip(tmp_path: Path, monkeypatch):
    _write_study(
        tmp_path / "results" / "studies",
        "alpha",
        cells=[{"run_name": "alpha_c0", "trade_count": 40, "profit_factor": None}],
    )
    zip_path = tmp_path / "results" / "studies" / "alpha" / "alpha_c0.research.zip"
    zip_path.write_bytes(b"PK\x03\x04not-a-real-zip")

    def boom(*_args, **_kwargs):
        raise AssertionError("forbidden call")

    monkeypatch.setattr("thesistester.study.report.report_study", boom)
    monkeypatch.setattr("thesistester.study.report.build_overview_frame", boom)
    monkeypatch.setattr("thesistester.study.report._resolve_bundle_metrics", boom)
    monkeypatch.setattr("thesistester.study.execute.run_study", boom)
    monkeypatch.setattr("thesistester.study.rollup.rollup_study", boom)

    class _ForbiddenZip:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("zipfile opened")

    monkeypatch.setattr("zipfile.ZipFile", _ForbiddenZip)
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    assert model.frame.iloc[0]["profit_factor_source"] == "missing"
    assert model.frame.iloc[0]["profit_factor"] is None or pd.isna(
        model.frame.iloc[0]["profit_factor"]
    )


def test_cohort_key_identity_and_instrument_split():
    left = {
        "instrument": "MNQ",
        "dataset_id": "ds-a",
        "ingestion_mode": "15s_primary_derive_1m",
        "commission_per_side": 0.5,
        "slippage_ticks": 1.0,
        "stop_loss_ticks": 80,
        "take_profit_ticks": 80,
        "trigger": "touch",
        "trigger_timeframe": "1min",
        "tolerance_ticks": 10,
        "flat_by_session_close": True,
    }
    right = dict(left)
    assert cohort_key_from_values(left) == cohort_key_from_values(right)
    right["instrument"] = "ES"
    assert cohort_key_from_values(left) != cohort_key_from_values(right)
    wave0 = dict(left)
    wave0["min_valid_confluences"] = 0
    pair = dict(left)
    pair["min_valid_confluences"] = 1
    assert cohort_key_from_values(wave0) != cohort_key_from_values(pair)


def test_majority_cohort_key_lexicographic_tie():
    frame = pd.DataFrame({"cohort_key": ["z|a", "a|z", "z|a", "a|z"]})
    assert majority_cohort_key(frame) == "a|z"


def test_load_splits_cohort_when_min_valid_confluences_differs(tmp_path: Path):
    _write_study(
        tmp_path / "results" / "studies",
        "wave0",
        min_valid=0,
        cells=[{"run_name": "w0_c0", "trade_count": 40}],
    )
    _write_study(
        tmp_path / "results" / "studies",
        "pair",
        min_valid=1,
        cells=[{"run_name": "pair_c0", "trade_count": 40}],
    )
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    keys = set(model.frame["cohort_key"])
    assert len(keys) == 2
    by_name = {
        row["run_name"]: row["min_valid_confluences"] for row in model.frame.to_dict("records")
    }
    assert by_name["w0_c0"] == 0
    assert by_name["pair_c0"] == 1


def test_sample_class_uses_study_min_trades(tmp_path: Path):
    assert sample_class_for(None, 30) == "missing_n"
    assert sample_class_for(10, 30) == "below_min_trades"
    assert sample_class_for(30, 30) == "interpretable"
    _write_study(
        tmp_path / "results" / "studies",
        "tight",
        min_trades=50,
        cells=[{"run_name": "tight_c0", "trade_count": 40, "expectancy_r": 0.2}],
    )
    _write_study(
        tmp_path / "results" / "studies",
        "loose",
        min_trades=10,
        cells=[{"run_name": "loose_c0", "trade_count": 40, "expectancy_r": 0.2}],
    )
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    by_name = {row["run_name"]: row["sample_class"] for row in model.frame.to_dict("records")}
    assert by_name["tight_c0"] == "below_min_trades"
    assert by_name["loose_c0"] == "interpretable"


def test_sort_refuses_total_r_and_locks_cohort(tmp_path: Path):
    _write_study(
        tmp_path / "results" / "studies",
        "mnq",
        instrument="MNQ",
        cells=[{"run_name": "mnq_low", "expectancy_r": 0.01, "instrument": "MNQ"}],
        dataset_id="ds-a",
    )
    # Second cell in same study with higher E so majority cohort is MNQ.
    mnq_dir = tmp_path / "results" / "studies" / "mnq"
    frame = pd.read_csv(mnq_dir / "results_index.csv")
    extra = frame.iloc[0].to_dict()
    extra["run_name"] = "mnq_high"
    extra["expectancy_r"] = 0.40
    pd.concat([frame, pd.DataFrame([extra])], ignore_index=True).to_csv(
        mnq_dir / "results_index.csv", index=False
    )
    expansion = json.loads((mnq_dir / "study.expansion.json").read_text(encoding="utf-8"))
    expansion["factor_map"]["mnq_high"] = expansion["factor_map"]["mnq_low"]
    (mnq_dir / "study.expansion.json").write_text(json.dumps(expansion), encoding="utf-8")
    _write_study(
        tmp_path / "results" / "studies",
        "es",
        instrument="ES",
        cells=[{"run_name": "es_mid", "expectancy_r": 0.20, "instrument": "ES"}],
        dataset_id="ds-b",
    )
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    with pytest.raises(ObservatoryError, match="total_r"):
        sort_observatory_frame(model.frame, column="total_r")
    assert "total_r" not in SORT_ALLOW_LIST
    ranked = sort_observatory_frame(model.frame, column="expectancy_r", cohort_lock=True)
    mnq_keys = set(model.frame.loc[model.frame["instrument"] == "MNQ", "cohort_key"])
    assert len(mnq_keys) == 1
    assert list(ranked["run_name"][:2]) == ["mnq_high", "mnq_low"]
    broken = sort_observatory_frame(
        model.frame, column="expectancy_r", cohort_lock=True, break_comparability=True
    )
    assert list(broken["run_name"]) == ["mnq_high", "es_mid", "mnq_low"]


def test_setup_kind_factors_and_lens_hint(tmp_path: Path):
    _write_study(
        tmp_path / "results" / "studies",
        "progB_w1_ext_ma",
        cells=[{"run_name": "p_c0", "trade_count": 40}],
    )
    _write_study(
        tmp_path / "results" / "studies",
        "child_admit",
        cells=[{"run_name": "c_c0", "trade_count": 40}],
        lineage_admit=True,
    )
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    prog = model.frame.loc[model.frame["study_name"] == "progB_w1_ext_ma"].iloc[0]
    admit = model.frame.loc[model.frame["study_name"] == "child_admit"].iloc[0]
    assert prog["setup_kind"] == "touch@1min/anchor_rules"
    assert prog["lens_hint"] == "program_b"
    assert admit["lens_hint"] == "admit_child"
    assert admit["lineage_parent"] == "parent_study"
    assert admit["lineage_admit_value"] == "rth_open_30m"
    filtered = apply_facets(model.frame, {"instrument": ["ES"]})
    assert set(filtered["study_name"]) == {"progB_w1_ext_ma", "child_admit"}


def test_mtime_cache_reuses_unchanged_slice(tmp_path: Path):
    _write_study(
        tmp_path / "results" / "studies",
        "alpha",
        cells=[{"run_name": "alpha_c0", "expectancy_r": 0.10}],
    )
    first = load_observatory_frame(roots=(tmp_path.resolve(),))
    second = load_observatory_frame(roots=(tmp_path.resolve(),), prior=first)
    key = str(tmp_path.resolve() / "results" / "studies" / "alpha")
    assert first.stamp[key] == second.stamp[key]
    assert list(second.frame["expectancy_r"]) == [0.10]
    index = tmp_path / "results" / "studies" / "alpha" / "results_index.csv"
    frame = pd.read_csv(index)
    frame.loc[0, "expectancy_r"] = 0.99
    frame.to_csv(index, index=False)
    third = load_observatory_frame(roots=(tmp_path.resolve(),), prior=second)
    assert third.stamp[key] != second.stamp[key]
    assert float(third.frame.iloc[0]["expectancy_r"]) == pytest.approx(0.99)


def test_load_does_not_write_study_dir(tmp_path: Path):
    study_dir = _write_study(
        tmp_path / "results" / "studies",
        "alpha",
        cells=[{"run_name": "alpha_c0"}],
    )
    before = {path.name: path.stat().st_mtime for path in study_dir.iterdir()}
    load_observatory_frame(roots=(tmp_path.resolve(),))
    after = {path.name: path.stat().st_mtime for path in study_dir.iterdir()}
    assert before == after


def test_cli_observatory_table_csv_and_extra_root(tmp_path: Path, monkeypatch, capsys):
    _write_study(
        tmp_path / "results" / "studies",
        "cli_alpha",
        cells=[
            {"run_name": "cli_c0", "trade_count": 40, "expectancy_r": 0.11, "profit_factor": 1.3}
        ],
    )
    monkeypatch.setattr(
        "thesistester.study.viewer.default_study_viewer_roots",
        lambda: (tmp_path.resolve(),),
    )
    assert cli_main(["study", "observatory", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert OBSERVATORY_HONESTY in out.splitlines()[0]
    assert "cli_alpha" in out
    assert "cli_c0" in out
    assert "sample_class" in out

    assert cli_main(["study", "observatory", "--root", str(tmp_path), "--csv"]) == 0
    csv_out = capsys.readouterr().out
    assert OBSERVATORY_HONESTY not in csv_out
    reader = csv.DictReader(io.StringIO(csv_out))
    assert reader.fieldnames == list(CLI_COLUMNS)
    rows = list(reader)
    assert rows[0]["study_name"] == "cli_alpha"
    assert rows[0]["run_name"] == "cli_c0"

    outside = tmp_path.parent / "outside_so1_cli"
    outside.mkdir(exist_ok=True)
    assert cli_main(["study", "observatory", "--root", str(outside)]) == 2
    err = capsys.readouterr().err
    assert "trusted local roots" in err

    from thesistester.cli import _parser

    parsed = _parser().parse_args(["study", "expand", "spec.yaml", "--output-dir", "out/x"])
    assert parsed.study_command == "expand"
    assert parsed.output_dir == Path("out/x")
    listed = _parser().parse_args(["study", "list"])
    assert listed.study_command == "list"


def test_format_empty_table(tmp_path: Path):
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    assert model.frame.empty
    assert model.studies.empty
    assert format_observatory_table(model.frame) == (
        "No study cells found under results/studies/ or out/."
    )


def test_corrupt_otf_does_not_fail_sibling(tmp_path: Path):
    _write_study(
        tmp_path / "results" / "studies",
        "good",
        cells=[{"run_name": "good_c0", "trade_count": 40}],
    )
    bad = _write_study(
        tmp_path / "results" / "studies",
        "bad_otf",
        cells=[{"run_name": "bad_c0", "trade_count": 40}],
    )
    expansion = json.loads((bad / "study.expansion.json").read_text(encoding="utf-8"))
    expansion["factor_map"]["bad_c0"]["otf"] = "not-a-dict"
    (bad / "study.expansion.json").write_text(json.dumps(expansion), encoding="utf-8")
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    assert set(model.frame["run_name"]) == {"good_c0", "bad_c0"}
    assert not bool(model.studies["error"].notna().any())
    bad_row = model.frame.loc[model.frame["run_name"] == "bad_c0"].iloc[0]
    assert bad_row["factor_otf"] == "not-a-dict"
    assert bool(bad_row["factor_otf_enabled"]) is False


def test_setup_kind_falls_back_to_exclusive_factors(tmp_path: Path):
    study_dir = _write_study(
        tmp_path / "results" / "studies",
        "exclusive",
        cells=[{"run_name": "ex_c0", "trade_count": 40}],
    )
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    expansion["factor_map"]["ex_c0"] = {
        "core_level": "ONH",
        "partner_levels": ["SMA_50_1min"],
    }
    (study_dir / "study.expansion.json").write_text(json.dumps(expansion), encoding="utf-8")
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    row = model.frame.iloc[0]
    assert row["factors_joined"]
    assert row["trigger"] == "touch"
    assert row["trigger_timeframe"] == "1min"
    assert row["confluence_mode"] == "anchor_rules"
    assert row["setup_kind"] == "touch@1min/anchor_rules"


def test_numeric_run_name_join_survives_pandas_float_upcast(tmp_path: Path):
    study_dir = _write_study(
        tmp_path / "results" / "studies",
        "numeric_names",
        cells=[{"run_name": "123", "trade_count": 40, "expectancy_r": 0.2}],
    )
    expansion = json.loads((study_dir / "study.expansion.json").read_text(encoding="utf-8"))
    expansion["factor_map"] = {
        "123": expansion["factor_map"].pop("123"),
        "456": {
            "core_level": "ONH",
            "partner_levels": ["SMA_50_1min"],
            "confluence_mode": "anchor_rules",
            "trigger": "touch",
            "trigger_timeframe": "1min",
        },
    }
    (study_dir / "study.expansion.json").write_text(json.dumps(expansion), encoding="utf-8")
    frame = pd.read_csv(study_dir / "results_index.csv")
    extra = frame.iloc[0].to_dict()
    extra["run_name"] = 456
    extra["expectancy_r"] = 0.05
    # A blank run_name forces pandas to float-upcast 123 → 123.0 on the next read.
    blank = extra.copy()
    blank["run_name"] = None
    pd.concat([frame, pd.DataFrame([extra, blank])], ignore_index=True).to_csv(
        study_dir / "results_index.csv", index=False
    )
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    by_name = {str(row["run_name"]): row for row in model.frame.to_dict("records")}
    assert set(by_name) == {"123", "456"}
    assert bool(by_name["123"]["factors_joined"])
    assert bool(by_name["456"]["factors_joined"])
    assert by_name["123"]["setup_kind"] == "touch@1min/anchor_rules"


def test_coerce_and_cohort_tokens_accept_numpy_scalars():
    np = pytest.importorskip("numpy")
    assert sample_class_for(np.int64(40), np.int64(30)) == "interpretable"
    assert sample_class_for(np.int64(10), 30) == "below_min_trades"
    assert cohort_key_from_values(
        {
            "flat_by_session_close": np.bool_(True),
            "stop_loss_ticks": np.int64(80),
        }
    ) == cohort_key_from_values(
        {
            "flat_by_session_close": True,
            "stop_loss_ticks": 80,
        }
    )


def test_scalar_exclusive_factor_in_spec(tmp_path: Path):
    study_dir = _write_study(
        tmp_path / "results" / "studies",
        "scalar_trig",
        cells=[{"run_name": "sc_c0", "trade_count": 40}],
        ledger_only=True,
    )
    spec = yaml.safe_load((study_dir / STUDY_SPEC_FILENAME).read_text(encoding="utf-8"))
    spec["study"]["factors"]["trigger"] = "touch"
    spec["study"]["factors"]["trigger_timeframe"] = "1min"
    spec["study"]["factors"]["confluence_mode"] = "anchor_rules"
    (study_dir / STUDY_SPEC_FILENAME).write_text(
        yaml.safe_dump(spec, sort_keys=False), encoding="utf-8"
    )
    pd.DataFrame(
        [
            {
                "run_name": "orphan",
                "dataset_id": "ds-a",
                "instrument": "ES",
                "trade_count": 40,
                "expectancy_r": 0.1,
                "total_r": 4.0,
                "max_drawdown_r": 1.0,
                "profit_factor": 1.2,
                "win_rate": 0.5,
                "bundle_path": "orphan.research.zip",
                "status": "ok",
            }
        ]
    ).to_csv(study_dir / "results_index.csv", index=False)
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    row = model.frame.iloc[0]
    assert row["run_name"] == "orphan"
    assert not bool(row["factors_joined"])
    assert row["setup_kind"] == "touch@1min/anchor_rules"


def test_observatory_and_viewer_import_guards():
    observatory = Path("thesistester/study/observatory.py").read_text(encoding="utf-8")
    viewer = Path("thesistester/study/viewer.py").read_text(encoding="utf-8")
    obs_tree = ast.parse(observatory)
    imported: set[str] = set()
    for node in ast.walk(obs_tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "streamlit" not in imported
    assert "plotly" not in imported
    assert "zipfile" not in imported
    assert "thesistester.study.execute" not in imported
    assert "thesistester.study.cli_study" not in imported
    assert "thesistester.cli" not in imported
    assert "thesistester.study.launch" not in imported
    assert "thesistester.study.builder" not in imported
    assert "thesistester.study.promote" not in imported
    assert "thesistester.study.tools" not in imported
    assert "thesistester.study.rollup" not in imported
    assert "report_study(" not in observatory
    assert "build_overview_frame(" not in observatory
    assert "_resolve_bundle_metrics(" not in observatory
    assert "rollup_study(" not in observatory
    assert "run_study(" not in observatory
    assert "thesistester.study.observatory" not in viewer
    assert "import observatory" not in viewer
    assert "plotly" not in observatory
    assert "streamlit" not in observatory


def test_facet_instrument_hides_other_symbols(tmp_path: Path):
    _write_study(
        tmp_path / "results" / "studies",
        "mnq_study",
        instrument="MNQ",
        cells=[{"run_name": "mnq_c0", "instrument": "MNQ"}],
    )
    _write_study(
        tmp_path / "results" / "studies",
        "es_study",
        instrument="ES",
        cells=[{"run_name": "es_c0", "instrument": "ES"}],
    )
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    filtered = apply_facets(model.frame, {"instrument": ["MNQ"]})
    assert set(filtered["instrument"]) == {"MNQ"}
    assert set(filtered["run_name"]) == {"mnq_c0"}
    assert unique_facet_values(model.frame, "instrument") == ["ES", "MNQ"]


def test_displayed_min_trades_majority_then_smaller_tie():
    frame = pd.DataFrame({"min_trades": [30, 30, 50, 10]})
    assert displayed_min_trades(frame) == 30.0
    tied = pd.DataFrame({"min_trades": [50, 30, 50, 30]})
    assert displayed_min_trades(tied) == 30.0
    assert displayed_min_trades(pd.DataFrame()) is None


def test_numeric_facets_match_int_and_float_and_drop_numpy():
    np = pytest.importorskip("numpy")
    frame = pd.DataFrame(
        {
            "stop_loss_ticks": [80, 80.0, 100, np.int64(80)],
            "instrument": ["ES", "ES", "MNQ", "ES"],
        }
    )
    values = unique_facet_values(frame, "stop_loss_ticks")
    assert values == [80, 100]
    assert all(type(value) is int for value in values)
    assert canonical_facet_value(np.int64(80)) == 80
    assert canonical_facet_value(80.0) == 80
    filtered = apply_facets(frame, {"stop_loss_ticks": [80]})
    assert set(filtered["instrument"]) == {"ES"}
    assert len(filtered) == 3
    assert constrain_facet_selection([np.int64(80), 999, 80.0], values) == [80]
    assert constrain_facet_selection(["MNQ"], unique_facet_values(frame, "instrument")) == ["MNQ"]
    assert constrain_facet_selection(["NQ"], unique_facet_values(frame, "instrument")) == []


def test_cell_choice_labels_disambiguate_duplicate_names():
    rows = [
        {"study_name": "alpha", "run_name": "c0", "study_dir": "/tmp/a/alpha"},
        {"study_name": "alpha", "run_name": "c0", "study_dir": "/tmp/b/alpha"},
        {"study_name": "beta", "run_name": "c1", "study_dir": "/tmp/b/beta"},
    ]
    labels = cell_choice_labels(rows)
    assert labels[2] == "beta / c1"
    assert labels[0] != labels[1]
    assert "/tmp/a/alpha" in labels[0]
    assert "/tmp/b/alpha" in labels[1]
    assert len(set(labels)) == 3


def test_study_choice_labels_disambiguate_duplicate_names():
    rows = [
        {"study_name": "alpha", "study_dir": "/tmp/a/alpha"},
        {"study_name": "alpha", "study_dir": "/tmp/b/alpha"},
        {"study_name": "beta", "study_dir": "/tmp/c/beta"},
    ]
    labels = study_choice_labels(rows)
    assert labels[2] == "beta"
    assert labels[0] != labels[1]
    assert "/tmp/a/alpha" in labels[0]
    assert "/tmp/b/alpha" in labels[1]
    assert len(set(labels)) == 3


def test_corpus_progress_counts_empty_and_missing_columns():
    assert corpus_progress_counts(pd.DataFrame()) == {
        "studies": 0,
        "ok": 0,
        "failed": 0,
        "skipped": 0,
        "running": 0,
        "pending": 0,
    }
    bare = pd.DataFrame({"study_name": ["x"]})
    counts = corpus_progress_counts(bare)
    assert counts["studies"] == 1
    assert counts["ok"] == 0
    inf = pd.DataFrame({"ok": [float("inf")], "failed": [1]})
    assert corpus_progress_counts(inf)["ok"] == 0
    assert corpus_progress_counts(inf)["failed"] == 1
    assert list(sort_observatory_studies(pd.DataFrame()).columns) == []
    assert list(observatory_studies_table(pd.DataFrame()).columns) == []
    with_na = pd.DataFrame(
        {
            "study_name": ["keep", "err"],
            "study_dir": ["a", "b"],
            "error": [pd.NA, "index:bad"],
            "running": [0, 0],
            "pending": [0, 0],
            "failed": [0, 0],
        }
    )
    assert list(sort_observatory_studies(with_na)["study_name"]) == ["err", "keep"]


def test_observatory_page_ast_and_contract():
    page = Path("pages/16_Study_Observatory.py")
    assert page.is_file()
    source = page.read_text(encoding="utf-8")
    observatory = Path("thesistester/study/observatory.py").read_text(encoding="utf-8")
    assert "st.fragment" not in source
    assert "run_every" not in source
    assert "run_study(" not in source
    assert "rollup_study(" not in source
    assert "report_study(" not in source
    assert "apply_research_bundle_to_session" not in source
    assert "desk_class" in source
    assert "delta_e" in source
    assert "attach_program_b_projections" in source
    assert "st.plotly_chart" in source
    assert "import plotly.express" in source
    assert 'st.switch_page("pages/15_Studies.py")' in source
    assert "pages/12_Research_Bundles" not in source
    assert "pages/7_Backtest" not in source
    assert "pages/13_Portfolio" not in source
    assert "pages/1_Data" not in source
    assert "Break comparability" in source
    assert "Comparability lock is not in effect." in source
    assert "constrain_facet_selection" in source
    assert "cell_choice_labels" in source
    assert "not part of the ranked sort" in source
    assert "trade_count × expectancy_r" in source
    assert "No cells with trade_count × expectancy_r to chart." in source
    assert "Paste a path on Studies" in source
    assert "Open in Inspect" in source
    assert "Open study in Inspect" in source
    assert "observatory_selected_study" in source
    assert "STUDIES_VIEWER_SELECTED_RUN_KEY" in source
    assert "leftover cell from another dir" in source
    assert "corpus_progress_counts" in source
    assert "observatory_studies_table" in source
    assert "study_choice_labels" in source
    assert "ledger-only dirs stay on this strip" in source
    assert "not as invented cell rows" in source
    assert "STUDIES_VIEWER_DIR_KEY" in source
    assert "STUDIES_VIEWER_PENDING_PATH_KEY" in source
    assert "STUDIES_VIEWER_CACHED_MODEL_KEY" in source
    assert "from thesistester.study.observatory import" not in source
    assert "import thesistester.study.observatory as" in source
    assert OBSERVATORY_HONESTY.split(".")[0] in source
    assert "import plotly" not in observatory
    assert "import streamlit" not in observatory
    for key in CLASSIC_RESEARCH_SESSION_KEYS:
        assert f'st.session_state["{key}"]' not in source
        assert f"st.session_state['{key}']" not in source
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "thesistester.study.execute" not in imported
    assert "thesistester.study.rollup" not in imported
    assert "thesistester.classic_record" not in imported
    assert "observatory_cached_model" in source
    assert "observatory_active_lens" in source
    assert "observatory_saved_desk_id" in source
    assert "_observatory_pending_desk" in source
    assert "_observatory_pending_saved_desk_id" in source
    assert "observatory_desk_query_state" in source
    assert "observatory_desk_from_payload" in source
    assert "Save desk" in source
    assert "Load desk" in source
    assert "Delete desk" in source
    assert "not a validated edge" in source
    assert "not under results/studies/" in source
    assert "not a pure confluence effect" in source
    assert "+E is not Admit" in source
    assert "Program A scalp map" in source
    assert "desk_class heatmap" in source
    assert "n<15 is unidentified" in source
    assert "15≤n<30 is noisy" in source
    assert "n<30 is unidentified" not in source
    assert "15s operator packet: 23" in source
    assert "Parked VA packet: 4" in source
    assert "lens chrome, not catalog membership" in source
    assert "heatmap_class_z" in source
    assert "_HEATMAP_CLASS_INDEX" not in source
    assert "import plotly" not in observatory
    assert "st.fragment" not in observatory
    assert "23 files" in PROGRAM_B_LENS_PACKET_CHROME
    assert "4 files" in PROGRAM_B_LENS_PACKET_CHROME


def test_delta_e_vs_wave0_solo_and_missing_solo(tmp_path: Path):
    studies = tmp_path / "results" / "studies"
    _write_study(
        studies,
        "progB_w0_solo",
        partners=[],
        min_valid=0,
        cells=[{"run_name": "w0_onh", "trade_count": 40, "expectancy_r": 0.00}],
    )
    _write_study(
        studies,
        "progB_w1_onh_sma",
        core="ONH",
        partners=["SMA"],
        cells=[
            {
                "run_name": "pair_onh",
                "trade_count": 40,
                "expectancy_r": 0.10,
                "profit_factor": 1.2,
            }
        ],
    )
    model = load_observatory_frame(roots=(tmp_path.resolve(),))
    attached = attach_program_b_projections(model.frame)
    pair = attached.loc[attached["run_name"] == "pair_onh"].iloc[0]
    assert pair["delta_e"] == pytest.approx(0.10)
    assert pair["thinning"] == pytest.approx(1.0)
    assert bool(pair["useful_confluence"]) is True
    faceted = apply_facets(attached, {"study_name": ["progB_w1_onh_sma"]})
    assert faceted.iloc[0]["delta_e"] == pytest.approx(0.10)

    missing_root = tmp_path / "missing_solo"
    _write_study(
        missing_root / "results" / "studies",
        "progB_w1_onh_sma",
        core="ONH",
        partners=["SMA"],
        cells=[{"run_name": "orphan_pair", "trade_count": 40, "expectancy_r": 0.10}],
    )
    missing = attach_program_b_projections(
        load_observatory_frame(roots=(missing_root.resolve(),)).frame
    )
    assert pd.isna(missing.iloc[0]["delta_e"])
    assert pd.isna(missing.iloc[0]["thinning"])
    assert bool(missing.iloc[0]["useful_confluence"]) is False


def test_delta_e_pdpoc_uses_w0_va_and_duplicate_w0_nulls(tmp_path: Path):
    assert wave0_study_name_for_core("pdPOC") == "progB_w0_va"
    assert wave0_study_name_for_core("ONH") == "progB_w0_solo"
    studies = tmp_path / "va" / "results" / "studies"
    _write_study(
        studies,
        "progB_w0_va",
        core="pdPOC",
        partners=[],
        min_valid=0,
        cells=[{"run_name": "w0_va", "trade_count": 40, "expectancy_r": 0.02}],
    )
    _write_study(
        studies,
        "progB_w0_solo",
        core="pdPOC",
        partners=[],
        min_valid=0,
        cells=[{"run_name": "w0_solo_wrong", "trade_count": 40, "expectancy_r": 0.99}],
    )
    _write_study(
        studies,
        "progB_w1_pdpoc",
        core="pdPOC",
        partners=["SMA"],
        cells=[{"run_name": "pair_pdpoc", "trade_count": 40, "expectancy_r": 0.12}],
    )
    attached = attach_program_b_projections(
        load_observatory_frame(roots=((tmp_path / "va").resolve(),)).frame
    )
    pair = attached.loc[attached["run_name"] == "pair_pdpoc"].iloc[0]
    assert pair["delta_e"] == pytest.approx(0.10)

    dup = tmp_path / "dup" / "results" / "studies"
    _write_study(
        dup,
        "progB_w0_solo_a",
        study_name="progB_w0_solo",
        partners=[],
        min_valid=0,
        cells=[{"run_name": "w0_a", "trade_count": 40, "expectancy_r": 0.00}],
    )
    _write_study(
        dup,
        "progB_w0_solo_b",
        study_name="progB_w0_solo",
        partners=[],
        min_valid=0,
        cells=[{"run_name": "w0_b", "trade_count": 40, "expectancy_r": 0.01}],
    )
    _write_study(
        dup,
        "progB_w1_onh_sma",
        core="ONH",
        partners=["SMA"],
        cells=[{"run_name": "pair_dup", "trade_count": 40, "expectancy_r": 0.10}],
    )
    dup_attached = attach_program_b_projections(
        load_observatory_frame(roots=((tmp_path / "dup").resolve(),)).frame
    )
    dup_pair = dup_attached.loc[dup_attached["run_name"] == "pair_dup"].iloc[0]
    assert pd.isna(dup_pair["delta_e"])


def test_desk_class_matches_section_4_7():
    plus = desk_class_for(
        status="ok",
        sample_class="interpretable",
        trade_count=30,
        expectancy_r=0.10,
        profit_factor=1.20,
    )
    noisy = desk_class_for(
        status="ok",
        sample_class="below_min_trades",
        trade_count=20,
        expectancy_r=0.10,
        profit_factor=1.20,
    )
    unidentified = desk_class_for(
        status="ok",
        sample_class="below_min_trades",
        trade_count=10,
        expectancy_r=0.10,
        profit_factor=1.20,
    )
    hold = desk_class_for(
        status="ok",
        sample_class="interpretable",
        trade_count=30,
        expectancy_r=0.10,
        profit_factor=1.0,
    )
    other = desk_class_for(
        status="ok",
        sample_class="interpretable",
        trade_count=30,
        expectancy_r=0.05,
        profit_factor=0.90,
    )
    failed = desk_class_for(
        status="failed",
        sample_class="interpretable",
        trade_count=30,
        expectancy_r=0.10,
        profit_factor=1.20,
    )
    skipped = desk_class_for(
        status="skipped",
        sample_class="interpretable",
        trade_count=30,
        expectancy_r=0.10,
        profit_factor=1.20,
    )
    noisy_edge = desk_class_for(
        status="ok",
        sample_class="below_min_trades",
        trade_count=15,
        expectancy_r=0.10,
        profit_factor=1.20,
    )
    unidentified_edge = desk_class_for(
        status="ok",
        sample_class="below_min_trades",
        trade_count=14,
        expectancy_r=0.10,
        profit_factor=1.20,
    )
    hold_pf_only = desk_class_for(
        status="ok",
        sample_class="interpretable",
        trade_count=30,
        expectancy_r=None,
        profit_factor=1.0,
    )
    assert plus == "plus_e"
    assert noisy == "noisy"
    assert unidentified == "unidentified"
    assert hold == "hold"
    assert other == "other"
    assert failed == "failed"
    assert skipped == "unidentified"
    assert noisy_edge == "noisy"
    assert unidentified_edge == "unidentified"
    assert hold_pf_only == "hold"
    assert heatmap_class_z(None) == HEATMAP_Z_MISSING
    assert heatmap_class_z("failed") != HEATMAP_Z_MISSING
    assert heatmap_class_z("failed") == 1
    assert heatmap_class_z("plus_e") == 7
    assert useful_confluence_for(
        sample_class="interpretable",
        delta_e=0.03,
        profit_factor=1.20,
        thinning=0.5,
    )
    assert not useful_confluence_for(
        sample_class="interpretable",
        delta_e=0.03,
        profit_factor=1.0,
        thinning=0.5,
    )


def test_heatmap_absent_on_generic_corpus_and_manifest_not_required(tmp_path: Path):
    study_dir = _write_study(
        tmp_path / "results" / "studies",
        "alpha",
        cells=[{"run_name": "alpha_c0", "trade_count": 40, "expectancy_r": 0.10}],
    )
    assert not (study_dir / "manifest.yaml").exists()
    assert not (tmp_path / "results" / "studies" / "manifest.yaml").exists()
    attached = attach_program_b_projections(
        load_observatory_frame(roots=(tmp_path.resolve(),)).frame
    )
    assert attached.iloc[0]["lens_hint"] == "generic"
    assert pd.isna(attached.iloc[0]["desk_class"])
    assert program_b_heatmap_cells(attached).empty
    assert resolve_program_b_lens("auto", attached) is False
    assert resolve_program_b_lens("generic", attached) is False
    assert resolve_program_b_lens("program_b", attached) is True
    counts = desk_class_counts(attached)
    assert counts["plus_e"] == 0
    assert counts["failed"] == 0


def test_heatmap_cartesian_marks_absent_program_b_cells(tmp_path: Path):
    studies = tmp_path / "results" / "studies"
    _write_study(
        studies,
        "progB_w1_onh_sma",
        core="ONH",
        partners=["SMA"],
        cells=[{"run_name": "onh_sma", "trade_count": 40, "expectancy_r": 0.10}],
    )
    _write_study(
        studies,
        "progB_w1_onl_ema",
        core="ONL",
        partners=["EMA"],
        cells=[{"run_name": "onl_ema", "trade_count": 40, "expectancy_r": 0.04}],
    )
    attached = attach_program_b_projections(
        load_observatory_frame(roots=(tmp_path.resolve(),)).frame
    )
    assert resolve_program_b_lens("auto", attached) is True
    grid = program_b_heatmap_cells(attached)
    assert not grid.empty
    by_cell = {
        (row["factor_core_level"], row["factor_partner_levels"]): row["desk_class"]
        for row in grid.to_dict("records")
    }
    assert set(by_cell) == {("ONH", "SMA"), ("ONH", "EMA"), ("ONL", "SMA"), ("ONL", "EMA")}
    assert by_cell[("ONH", "SMA")] == "plus_e"
    assert pd.isna(by_cell[("ONH", "EMA")]) or by_cell[("ONH", "EMA")] is None
    assert pd.isna(by_cell[("ONL", "SMA")]) or by_cell[("ONL", "SMA")] is None


def test_delta_e_does_not_cross_instrument_or_null_when_each_has_wave0(tmp_path: Path):
    studies = tmp_path / "results" / "studies"
    _write_study(
        studies,
        "progB_w0_solo",
        instrument="ES",
        partners=[],
        min_valid=0,
        cells=[{"run_name": "w0_es", "trade_count": 40, "expectancy_r": 0.00, "instrument": "ES"}],
    )
    _write_study(
        studies,
        "progB_w1_mnq",
        instrument="MNQ",
        core="ONH",
        partners=["SMA"],
        cells=[
            {
                "run_name": "pair_mnq",
                "trade_count": 40,
                "expectancy_r": 0.10,
                "instrument": "MNQ",
            }
        ],
        dataset_id="ds-mnq",
    )
    crossed = attach_program_b_projections(
        load_observatory_frame(roots=(tmp_path.resolve(),)).frame
    )
    mnq = crossed.loc[crossed["run_name"] == "pair_mnq"].iloc[0]
    assert pd.isna(mnq["delta_e"])

    both = tmp_path / "both" / "results" / "studies"
    _write_study(
        both,
        "progB_w0_solo_es",
        study_name="progB_w0_solo",
        instrument="ES",
        partners=[],
        min_valid=0,
        cells=[{"run_name": "w0_es", "trade_count": 40, "expectancy_r": 0.00, "instrument": "ES"}],
        dataset_id="ds-es",
    )
    _write_study(
        both,
        "progB_w0_solo_mnq",
        study_name="progB_w0_solo",
        instrument="MNQ",
        partners=[],
        min_valid=0,
        cells=[
            {"run_name": "w0_mnq", "trade_count": 40, "expectancy_r": 0.02, "instrument": "MNQ"}
        ],
        dataset_id="ds-mnq",
    )
    _write_study(
        both,
        "progB_w1_es",
        instrument="ES",
        core="ONH",
        partners=["SMA"],
        cells=[
            {
                "run_name": "pair_es",
                "trade_count": 40,
                "expectancy_r": 0.10,
                "instrument": "ES",
            }
        ],
        dataset_id="ds-es",
    )
    _write_study(
        both,
        "progB_w1_mnq",
        instrument="MNQ",
        core="ONH",
        partners=["SMA"],
        cells=[
            {
                "run_name": "pair_mnq_own",
                "trade_count": 40,
                "expectancy_r": 0.12,
                "instrument": "MNQ",
            }
        ],
        dataset_id="ds-mnq",
    )
    attached = attach_program_b_projections(
        load_observatory_frame(roots=((tmp_path / "both").resolve(),)).frame
    )
    es_pair = attached.loc[attached["run_name"] == "pair_es"].iloc[0]
    mnq_pair = attached.loc[attached["run_name"] == "pair_mnq_own"].iloc[0]
    assert es_pair["delta_e"] == pytest.approx(0.10)
    assert mnq_pair["delta_e"] == pytest.approx(0.10)


def test_heatmap_wave0_only_uses_solo_column(tmp_path: Path):
    _write_study(
        tmp_path / "results" / "studies",
        "progB_w0_solo",
        partners=[],
        min_valid=0,
        cells=[{"run_name": "w0_onh", "trade_count": 40, "expectancy_r": 0.00}],
    )
    attached = attach_program_b_projections(
        load_observatory_frame(roots=(tmp_path.resolve(),)).frame
    )
    grid = program_b_heatmap_cells(attached)
    assert not grid.empty
    assert list(grid["factor_partner_levels"]) == [HEATMAP_SOLO_PARTNER]
    assert list(grid["factor_core_level"]) == ["ONH"]


def test_saved_desk_round_trip_and_schema_v1(tmp_path: Path):
    store = tmp_path / "store"
    study_dir = _write_study(
        tmp_path / "results" / "studies",
        "alpha",
        cells=[{"run_name": "alpha_c0", "trade_count": 40}],
    )
    before = {path.name: path.stat().st_mtime for path in study_dir.iterdir()}
    assert not observatory_desks_dir(store_root=store).exists()
    empty, ignored = list_observatory_desks(store_root=store)
    assert empty == ()
    assert ignored == ()
    saved = save_observatory_desk(
        name="MNQ 15s",
        facets={"instrument": ["MNQ", 80, "MNQ"], "status": ["ok"]},
        cohort_lock=True,
        break_comparability=False,
        active_cohort="mnq|ds-a",
        lens="program_b",
        sort_column="profit_factor",
        store_root=store,
    )
    payload = json.loads(
        (observatory_desks_dir(store_root=store) / f"{saved.id}.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == DESK_SCHEMA_VERSION == 1
    assert payload["lens"] == "program_b"
    assert payload["sort_column"] == "profit_factor"
    assert payload["facets"]["instrument"] == ["MNQ", 80]
    desks, ignored_after = list_observatory_desks(store_root=store)
    assert ignored_after == ()
    assert len(desks) == 1
    loaded = desks[0]
    assert loaded.facets["instrument"] == ("MNQ", 80)
    assert loaded.lens == "program_b"
    assert loaded.sort_column == "profit_factor"
    assert loaded.cohort_lock is True
    assert loaded.active_cohort == "mnq|ds-a"
    state = observatory_desk_query_state(loaded)
    assert state["facets"]["instrument"] == ["MNQ", 80]
    assert state["lens"] == "program_b"
    assert state["sort_column"] == "profit_factor"
    assert state["saved_desk_id"] == saved.id
    assert observatory_desk_from_payload(saved.to_payload()) == loaded
    updated = save_observatory_desk(
        name="MNQ 15s",
        facets={"instrument": ["ES"]},
        lens="generic",
        sort_column="win_rate",
        desk_id=saved.id,
        store_root=store,
    )
    assert updated.id == saved.id
    assert len(list_observatory_desks(store_root=store)[0]) == 1
    after = {path.name: path.stat().st_mtime for path in study_dir.iterdir()}
    assert before == after
    assert not (study_dir / "study_observatory").exists()
    assert delete_observatory_desk(saved.id, store_root=store) is True
    assert list_observatory_desks(store_root=store)[0] == ()


def test_saved_desk_ignores_corrupt_and_v2(tmp_path: Path):
    store = tmp_path / "store"
    desks_dir = observatory_desks_dir(store_root=store)
    desks_dir.mkdir(parents=True)
    (desks_dir / "broken.json").write_text("{not-json", encoding="utf-8")
    (desks_dir / "future.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "id": "future-desk",
                "name": "Future",
                "facets": {"instrument": ["ES"]},
                "lens": "auto",
                "sort_column": "expectancy_r",
            }
        ),
        encoding="utf-8",
    )
    valid = save_observatory_desk(
        name="Keep",
        facets={"instrument": ["ES"]},
        lens="generic",
        sort_column="win_rate",
        store_root=store,
    )
    desks, ignored = list_observatory_desks(store_root=store)
    assert valid.id in {desk.id for desk in desks}
    assert len(desks) == 1
    assert set(ignored) == {"broken.json", "future.json"}
    assert desks[0].lens == "generic"
    assert desks[0].sort_column == "win_rate"


def test_saved_desk_ignores_malformed_payloads_without_raising(tmp_path: Path):
    store = tmp_path / "store"
    desks_dir = observatory_desks_dir(store_root=store)
    desks_dir.mkdir(parents=True)
    (desks_dir / "scalar-facet.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "scalar-facet",
                "name": "Scalar",
                "facets": {"instrument": "MNQ", "stop_loss_ticks": 80},
                "cohort_lock": True,
                "lens": "auto",
                "sort_column": "expectancy_r",
            }
        ),
        encoding="utf-8",
    )
    (desks_dir / "string-bool.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "string-bool",
                "name": "String bool",
                "facets": {"instrument": ["ES"]},
                "cohort_lock": "false",
                "lens": "auto",
                "sort_column": "expectancy_r",
            }
        ),
        encoding="utf-8",
    )
    (desks_dir / "id-mismatch.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "other-id",
                "name": "Mismatch",
                "facets": {"instrument": ["ES"]},
                "lens": "auto",
                "sort_column": "expectancy_r",
            }
        ),
        encoding="utf-8",
    )
    (desks_dir / "token-object.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "token-object",
                "name": "Token",
                "active_cohort": {"key": "bad"},
                "lens": "auto",
                "sort_column": "expectancy_r",
            }
        ),
        encoding="utf-8",
    )
    desks, ignored = list_observatory_desks(store_root=store)
    assert desks == ()
    assert set(ignored) == {
        "scalar-facet.json",
        "string-bool.json",
        "id-mismatch.json",
        "token-object.json",
    }
    assert parse_observatory_desk(desks_dir / "scalar-facet.json") is None
    assert parse_observatory_desk(desks_dir / "id-mismatch.json") is None
    assert observatory_desk_from_payload(["not", "an", "object"]) is None


def test_saved_desk_rejects_invalid_id_and_does_not_write_none_json(tmp_path: Path):
    store = tmp_path / "store"
    with pytest.raises(ObservatoryError, match="Invalid saved-desk id"):
        save_observatory_desk(name="Bad", desk_id="not a valid id", store_root=store)
    with pytest.raises(ObservatoryError, match="must be a string"):
        save_observatory_desk(name="Bad", desk_id=True, store_root=store)  # type: ignore[arg-type]
    desks_dir = observatory_desks_dir(store_root=store)
    assert not desks_dir.exists()
    assert not (desks_dir / "None.json").exists()
    with pytest.raises(ObservatoryError, match="must be a list"):
        save_observatory_desk(
            name="Chars",
            facets={"instrument": "MNQ"},
            store_root=store,
        )
    assert not desks_dir.exists()


@pytest.fixture()
def isolate_observatory_apptest_globals():
    """Undo Streamlit ``__main__`` / ``sys.path`` mutation (same honesty as
    ``tests/test_assistant_page_render.py``). Required before a second AppTest
    module can coexist with spawn-context CLI tests.
    """
    main_module = sys.modules.get("__main__")
    path_snapshot = list(sys.path)
    try:
        yield
    finally:
        if main_module is None:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = main_module
        sys.path[:] = path_snapshot


def test_observatory_page_renders_studies_pane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolate_observatory_apptest_globals: None,
) -> None:
    """SO7 AppTest: ledger strip + studies table; no invented ledger-only cells."""
    from streamlit.testing.v1 import AppTest

    store = tmp_path / "store"
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(store))

    def _isolated_roots() -> tuple[Path, ...]:
        return (store.resolve(),)

    # Page load uses default trusted roots (cwd + store). Pin both bound names
    # so a developer `results/studies/` under cwd cannot leak into AppTest.
    monkeypatch.setattr("thesistester.study.viewer.default_study_viewer_roots", _isolated_roots)
    monkeypatch.setattr(
        "thesistester.study.observatory.default_study_viewer_roots", _isolated_roots
    )
    root = store / "results" / "studies"
    _write_study(
        root,
        "alpha",
        cells=[{"run_name": "alpha_c0", "trade_count": 40, "expectancy_r": 0.12}],
    )
    _write_study(root, "beta_inflight", ledger_only=True)
    page = Path(__file__).resolve().parents[2] / "pages" / "16_Study_Observatory.py"
    app = AppTest.from_file(str(page), default_timeout=45)
    app.run()
    assert not app.exception
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Studies"] == "2"
    assert metrics["Cells"] == "1"
    assert metrics["Pending"] == "1"
    assert metrics["Ok"] == "1"
    assert metrics["Failed"] == "0"
    study_box = next(box for box in app.selectbox if box.label == "Study")
    assert list(study_box.options) == ["beta_inflight", "alpha"]
    cell_box = next(box for box in app.selectbox if box.label == "Cell")
    assert list(cell_box.options) == ["alpha / alpha_c0"]
    assert any(button.label == "Open study in Inspect" for button in app.button)
    assert any(button.label == "Open in Inspect" for button in app.button)
    captions = [item.value for item in app.caption]
    assert any("not as invented cell rows" in text for text in captions)
