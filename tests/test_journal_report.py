"""TJ9 journal report + page 17 + CLI ``journal report``."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import ast
import inspect
import json

import pandas as pd
import pytest

from thesistester.cli import main as cli_main
from thesistester.journal.report import (
    REPORT_HONESTY,
    REPORT_MIN_N,
    JournalArtifacts,
    build_journal_report,
    journal_store_dir,
    load_journal_artifacts,
    report_files,
    report_from_artifacts,
)
from thesistester.journal.schema import (
    HOLD_15_60S,
    HOLD_LT_15S,
    JournalIngestError,
    MATCH_EXECUTED_CELL,
    MATCH_SYSTEMATIC_UNFILLED,
    RECON_RECONCILED,
    REPORT_SLICE_DIRECTION,
    REPORT_SLICE_HOLD,
    RESOLUTION_UNJOINED,
)
from thesistester.persistence.execution_artifacts import get_execution_artifacts_root
from thesistester.persistence.local_store import get_store_root


def _ts(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz="UTC")


def _trade(
    *,
    trade_id: str = "jt:1:0",
    instrument: str = "MNQ",
    direction: str = "long",
    session: date = date(2026, 5, 14),
    entry: str = "2026-05-14T14:00:10",
    net_ticks: float = 2.0,
    fee_ticks: float = 2.48,
    gross_ticks: float = 4.48,
    hold_seconds: float = 24.0,
    recon: str = RECON_RECONCILED,
    resolution: str | None = "15s",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": trade_id,
        "instrument": instrument,
        "direction": direction,
        "session_date": session,
        "entry_timestamp": _ts(entry),
        "net_ticks": net_ticks,
        "fee_ticks": fee_ticks,
        "gross_ticks": gross_ticks,
        "hold_seconds": hold_seconds,
        "recon_status": recon,
        "status": "closed",
    }
    if resolution is not None:
        payload["resolution"] = resolution
    return payload


def test_build_journal_report_is_keyword_only() -> None:
    params = inspect.signature(build_journal_report).parameters
    assert params["trades"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params["include_small_n"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["include_small_n"].default is False


def test_report_module_does_not_import_engine_or_index_keys() -> None:
    source = Path("thesistester/journal/report.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported.add(node.module)
    assert "thesistester.engine" not in imported
    assert "thesistester.study.execute" not in imported
    assert "simulate_trades(" not in source
    assert "compute_all_levels(" not in source
    assert "STUDY_INDEX_KEYS" not in source
    assert "R18_INDEX_METRIC_KEYS" not in source
    assert "run_experiment(" not in source
    assert "run_study(" not in source


def test_q1_derives_gross_from_pnl_currency() -> None:
    raw = _trade()
    del raw["gross_ticks"]
    raw["gross_pnl_currency"] = 2.24  # MNQ tick value $0.50 → 4.48 ticks
    report = build_journal_report(pd.DataFrame([raw]))
    assert report.q1_days.iloc[0]["mean_gross_ticks"] == pytest.approx(4.48)
    assert report.q1_days.iloc[0]["break_even_gross_ticks"] == pytest.approx(2.48)


def test_q1_derives_gross_from_net_plus_fee() -> None:
    raw = _trade(net_ticks=2.0, fee_ticks=2.48)
    del raw["gross_ticks"]
    report = build_journal_report(pd.DataFrame([raw]))
    assert report.q1_days.iloc[0]["mean_gross_ticks"] == pytest.approx(4.48)


def test_q1_instrument_day_and_break_even() -> None:
    trades = pd.DataFrame(
        [
            _trade(trade_id="a", net_ticks=4.0, fee_ticks=2.48, gross_ticks=6.48),
            _trade(trade_id="b", net_ticks=-2.0, fee_ticks=2.48, gross_ticks=0.48),
        ]
    )
    report = build_journal_report(trades)
    assert report.honesty == REPORT_HONESTY
    assert "not a study cell" in report.honesty
    day = report.q1_days.iloc[0]
    assert day["instrument"] == "MNQ"
    assert day["session_date"] == "2026-05-14"
    assert day["n"] == 2
    assert day["mean_net_ticks"] == pytest.approx(1.0)
    assert day["mean_fee_ticks"] == pytest.approx(2.48)
    assert day["break_even_gross_ticks"] == pytest.approx(2.48)
    assert day["resolution"] == "15s"
    assert day["recon_status"] == RECON_RECONCILED


def test_q2_hides_n_below_30_unless_toggled() -> None:
    trades = pd.DataFrame(
        [_trade(trade_id=f"jt:{index}:0", hold_seconds=10.0) for index in range(5)]
        + [_trade(trade_id=f"jt:h:{index}:0", hold_seconds=40.0) for index in range(REPORT_MIN_N)]
    )
    hidden = build_journal_report(trades)
    hold_hidden = hidden.q2_slices.loc[hidden.q2_slices["slice_kind"] == REPORT_SLICE_HOLD]
    assert HOLD_LT_15S not in set(hold_hidden["slice_value"])
    assert HOLD_15_60S in set(hold_hidden["slice_value"])
    assert hidden.hidden_slice_count >= 1
    shown = build_journal_report(trades, include_small_n=True)
    hold_shown = shown.q2_slices.loc[shown.q2_slices["slice_kind"] == REPORT_SLICE_HOLD]
    assert HOLD_LT_15S in set(hold_shown["slice_value"])
    small = hold_shown.loc[hold_shown["slice_value"] == HOLD_LT_15S].iloc[0]
    assert small["n"] == 5
    assert small["resolution"] == "15s"
    assert small["recon_status"] == RECON_RECONCILED
    artifacts = JournalArtifacts(
        journal_dir=Path("."),
        trades=trades,
        attribution=None,
        counterfactuals=None,
        counterfactual_payload=None,
        matches=None,
        match_payload=None,
    )
    rebuilt = report_from_artifacts(artifacts, include_small_n=True)
    hold_rebuilt = rebuilt.q2_slices.loc[rebuilt.q2_slices["slice_kind"] == REPORT_SLICE_HOLD]
    assert HOLD_LT_15S in set(hold_rebuilt["slice_value"])


def test_q2_direction_slice_has_meta_columns() -> None:
    trades = pd.DataFrame(
        [_trade(trade_id=f"l:{index}", direction="long") for index in range(REPORT_MIN_N)]
        + [_trade(trade_id=f"s:{index}", direction="short") for index in range(REPORT_MIN_N)]
    )
    report = build_journal_report(trades)
    direction = report.q2_slices.loc[report.q2_slices["slice_kind"] == REPORT_SLICE_DIRECTION]
    assert set(direction["slice_value"]) == {"long", "short"}
    assert set(direction["n"]) == {REPORT_MIN_N}
    assert list(direction["resolution"].unique()) == ["15s"]


def test_missing_later_artifacts_are_omitted() -> None:
    report = build_journal_report(pd.DataFrame([_trade()]))
    assert report.present["trades"] is True
    assert report.present["attribution"] is False
    assert report.present["counterfactual"] is False
    assert report.present["match"] is False
    assert report.q3_levels.empty
    assert report.q4_brackets.empty
    assert report.q5_null["direction_null_pct"] is None
    assert report.q6_rules.empty
    assert report.q7_matches.empty
    assert report.q8_ledger.empty


def test_q3_q8_surface_ingested_artifacts() -> None:
    trades = pd.DataFrame([_trade(), _trade(trade_id="jt:2:0")])
    attribution = pd.DataFrame(
        [
            {
                "trade_id": "jt:1:0",
                "nearest_level_token": "pdVAL",
                "level_context": "at_level",
                "tag_alignment": "none_aligned",
                "intent_mismatch": True,
            },
            {
                "trade_id": "jt:2:0",
                "nearest_level_token": "pdVAL",
                "level_context": "between_levels",
                "tag_alignment": "all_aligned",
                "intent_mismatch": False,
            },
        ]
    )
    payload = {
        "resolution": "15s",
        "null": {"seed": 0, "k": 1000, "n": 2, "direction_null_pct": 61.5},
        "brackets": {
            "brackets": {
                "10/10@15s": {
                    "cf_id": "10/10",
                    "sl_ticks": 10,
                    "tp_ticks": 10,
                    "n": 2,
                    "exit_rule_delta": 4.0,
                    "mean_cf_net_ticks": 1.0,
                    "resolution": "15s",
                }
            },
            "caption": "three brackets were looked at (not a single pre-registered test)",
        },
        "rules": [
            {
                "name": "cap",
                "declared_on": "2026-05-01",
                "split": "in_sample",
                "n_kept": 1,
                "trades_removed": 1,
                "rule_delta_ticks": -1.0,
            },
            {
                "name": "cap",
                "declared_on": "2026-05-01",
                "split": "forward",
                "n_kept": 1,
                "trades_removed": 0,
                "rule_delta_ticks": 0.5,
            },
        ],
    }
    matches = pd.DataFrame(
        [
            {"match_class": MATCH_EXECUTED_CELL, "side": "journal"},
            {"match_class": MATCH_SYSTEMATIC_UNFILLED, "side": "systematic"},
        ]
    )
    match_payload = {
        "ledger": [
            {
                "session_date": "2026-05-14",
                "executed_cell": 1,
                "systematic_unfilled": 1,
                "product_mismatch": 0,
                "adherence": 0.5,
                "live_net_ticks": 2.0,
                "cell_expectancy_ticks": 1.5,
            }
        ]
    }
    report = build_journal_report(
        trades,
        attribution=attribution,
        counterfactual_payload=payload,
        matches=matches,
        match_payload=match_payload,
    )
    assert report.q3_levels.iloc[0]["nearest_level_token"] == "pdVAL"
    assert report.q3_levels.iloc[0]["n"] == 2
    assert "resolution" in report.q3_levels.columns
    assert "recon_status" in report.q3_levels.columns
    assert set(report.q3_context["level_context"]) == {"at_level", "between_levels"}
    assert (
        int(
            report.q3_tags.loc[
                report.q3_tags["tag_alignment"] == "none_aligned", "intent_mismatch_n"
            ].iloc[0]
        )
        == 1
    )
    assert report.q4_brackets.iloc[0]["exit_rule_delta"] == pytest.approx(4.0)
    assert report.q4_brackets.iloc[0]["n"] == 2
    assert report.q5_null["direction_null_pct"] == pytest.approx(61.5)
    assert report.q5_null["seed"] == 0
    assert set(report.q6_rules["split"]) == {"in_sample", "forward"}
    assert "blended" not in "".join(report.q6_rules["split"].astype(str))
    assert set(report.q7_matches["match_class"]) == {MATCH_EXECUTED_CELL, MATCH_SYSTEMATIC_UNFILLED}
    ledger = report.q8_ledger.iloc[0]
    assert ledger["adherence"] == pytest.approx(0.5)
    assert ledger["n"] == 2
    assert ledger["resolution"] == RESOLUTION_UNJOINED


def test_unjoined_resolution_stamped_when_column_missing() -> None:
    raw = _trade()
    del raw["resolution"]
    report = build_journal_report(pd.DataFrame([raw]))
    assert report.q1_days.iloc[0]["resolution"] == RESOLUTION_UNJOINED


def test_include_small_n_fails_closed() -> None:
    with pytest.raises(JournalIngestError, match="include_small_n"):
        build_journal_report(pd.DataFrame([_trade()]), include_small_n="yes")  # type: ignore[arg-type]


def test_nan_null_percentile_serializes_as_null(tmp_path: Path) -> None:
    journal_dir = tmp_path / "in"
    journal_dir.mkdir()
    raw = pd.DataFrame([_trade()])
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(journal_dir / "journal_trades.parquet", index=False)
    (journal_dir / "counterfactual.json").write_text(
        json.dumps({"null": {"seed": 0, "k": 1000, "n": 0, "direction_null_pct": float("nan")}}),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    paths = report_files(journal_dir=journal_dir, output_dir=out)
    payload = json.loads(paths["report.json"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == "journal/v1"
    assert payload["honesty"] == REPORT_HONESTY
    assert payload["q5_null"]["direction_null_pct"] is None


def test_journal_store_dir_is_not_under_execution_artifacts() -> None:
    store = journal_store_dir()
    root = get_store_root()
    artifacts = get_execution_artifacts_root()
    assert store == root / "journal" / "v1"
    assert store.parent.name == "journal"
    assert "execution_artifacts" not in store.parts
    assert artifacts.is_relative_to(root)
    assert not store.is_relative_to(artifacts)


def test_load_tolerates_missing_optional_files(tmp_path: Path) -> None:
    raw = pd.DataFrame([_trade()])
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(tmp_path / "journal_trades.parquet", index=False)
    artifacts = load_journal_artifacts(tmp_path)
    assert artifacts.trades is not None
    assert artifacts.attribution is None
    assert artifacts.counterfactual_payload is None
    assert artifacts.match_payload is None


def test_cli_writes_report_and_refuses_studies_dir(tmp_path: Path) -> None:
    journal_dir = tmp_path / "in"
    journal_dir.mkdir()
    raw = pd.DataFrame([_trade()])
    raw["session_date"] = raw["session_date"].map(lambda value: value.isoformat())
    raw.to_parquet(journal_dir / "journal_trades.parquet", index=False)
    out = tmp_path / "journal_out"
    code = cli_main(
        ["journal", "report", "--journal-dir", str(journal_dir), "--output-dir", str(out)]
    )
    assert code == 0
    payload = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert payload["present"]["trades"] is True
    assert payload["q1_days"][0]["n"] == 1
    forbidden = tmp_path / "results" / "studies" / "oops"
    code_bad = cli_main(
        [
            "journal",
            "report",
            "--journal-dir",
            str(journal_dir),
            "--output-dir",
            str(forbidden),
        ]
    )
    assert code_bad == 2
    assert not (forbidden / "report.json").exists()


def test_journal_page_ast_and_contract() -> None:
    page = Path("pages/17_Journal.py")
    assert page.is_file()
    source = page.read_text(encoding="utf-8")
    assert "run_experiment(" not in source
    assert "run_study(" not in source
    assert "simulate_trades(" not in source
    assert "compute_all_levels(" not in source
    assert "apply_research_bundle_to_session(" not in source
    assert "st.switch_page" not in source
    assert "pages/1_Data" not in source
    assert "pages/7_Backtest" not in source
    assert "pages/15_Studies" not in source
    assert "pages/16_Study_Observatory" not in source
    assert "Q1 · Costs and reconciled net" in source
    assert "Q8 · Forward ledger" in source
    assert "Show slices with n < 30" in source
    assert "REPORT_HONESTY" in source
    assert "journal_store_dir" in source
    assert "journal_cached_artifacts" in source
    assert "journal_cached_report" not in source
    assert "report_from_artifacts" in source
    assert source.index("if load:") < source.rindex("report_from_artifacts(")
    assert "execution_artifacts" in source
    assert JOURNAL_PAGE_SORT_TOKEN in page.name


JOURNAL_PAGE_SORT_TOKEN = "17_Journal"
