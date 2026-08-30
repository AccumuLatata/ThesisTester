"""SO1–SO2 Study Observatory — fact table, CLI, page AST. No report_study."""

from __future__ import annotations

import ast
import csv
import io
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from thesistester.cli import main as cli_main
from thesistester.study.ledger import empty_ledger, save_ledger
from thesistester.study.observatory import (
    CLI_COLUMNS,
    OBSERVATORY_HONESTY,
    SORT_ALLOW_LIST,
    ObservatoryError,
    apply_facets,
    cohort_key_from_values,
    displayed_min_trades,
    format_observatory_table,
    load_observatory_frame,
    majority_cohort_key,
    sample_class_for,
    sort_observatory_frame,
    unique_facet_values,
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
) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    study_dir = parent / name
    study_dir.mkdir()
    spec: dict = {
        "schema_version": 1,
        "study": {
            "name": name,
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
                "core_level": ["ONH"],
                "partner_levels": [["SMA_50_1min"]],
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
                "core_level": "ONH",
                "partner_levels": ["SMA_50_1min"],
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
    assert "desk_class" not in source
    assert "delta_e" not in source
    assert "st.plotly_chart" in source
    assert "import plotly.express" in source
    assert 'st.switch_page("pages/15_Studies.py")' in source
    assert "pages/12_Research_Bundles" not in source
    assert "pages/7_Backtest" not in source
    assert "pages/13_Portfolio" not in source
    assert "pages/1_Data" not in source
    assert "Break comparability" in source
    assert "trade_count × expectancy_r" in source
    assert "No cells with trade_count × expectancy_r to chart." in source
    assert "Paste a path on Studies" in source
    assert "Open in Inspect" in source
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
    assert "observatory_active_lens" not in source
    assert "observatory_saved_desk_id" not in source
