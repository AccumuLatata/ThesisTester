"""SIA3 ingest-identity parity: Studies emit → expand → run_experiment."""

from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd

from thesistester.api import run_experiment
from thesistester.data.derive import (
    DERIVATION_POLICY_OBSERVED_ALIGNED_15S_TO_1M_V2,
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
)
from thesistester.study.builder import StudyDraft, default_study_draft, emit_study_spec
from thesistester.study.expand import expand_study

VENDOR_15S = Path("tests/fixtures/vendor/quantower_history_exporter_15s.csv")


def _one_cell_15s_draft() -> StudyDraft:
    draft = default_study_draft()
    draft.dataset_path = str(VENDOR_15S.resolve())
    draft.instrument = "ES"
    draft.source_timezone = "America/New_York"
    draft.format_profile = "quantower_history_exporter"
    draft.ingestion_mode = INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    draft.confluence_mode = ["global_cluster"]
    draft.trigger = ["touch"]
    draft.trigger_timeframe = ["base"]
    draft.otf = None
    draft.backtest["intrabar_model"] = "subtimeframe_conservative"
    return draft


def test_study_emit_expand_run_experiment_is_15s_primary(tmp_path: Path):
    spec = emit_study_spec(_one_cell_15s_draft())
    expansion = expand_study(spec)
    assert expansion.run_count == 1
    assert not hasattr(expansion, "runs")
    run = expansion.experiment["runs"][0]
    assert run["dataset"]["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert run["dataset"]["format_profile"] == "quantower_history_exporter"
    assert "subtimeframe_path" not in run["dataset"]
    assert run["backtest"]["intrabar_model"] == "subtimeframe_conservative"

    state = run_experiment(
        run,
        base_directory=tmp_path,
        execution_origin="study",
        cache_policy="off",
    )
    provenance = state["ingestion_provenance"]
    assert provenance["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert provenance["derivation_policy"] == DERIVATION_POLICY_OBSERVED_ALIGNED_15S_TO_1M_V2
    assert state["base_interval"] == "1min"
    assert isinstance(state["subtimeframe_data"], pd.DataFrame)
    assert len(state["subtimeframe_data"]) == 8
    assert len(state["data"]) == 2
    assert len(state["subtimeframe_data"]) > len(state["data"])
    assert state["backtest_intrabar_policy"]["intrabar_model"] == (
        "subtimeframe_conservative"
    )
    assert state["backtest_intrabar_policy"]["subtimeframe_data_supplied"] is True

    replay = run_experiment(
        copy.deepcopy(expansion.experiment["runs"][0]),
        base_directory=tmp_path,
        execution_origin="study",
        cache_policy="off",
    )
    assert replay["dataset_id"] == state["dataset_id"]
    assert replay["ingestion_provenance"] == state["ingestion_provenance"]


def test_same_15s_bytes_without_ingestion_mode_are_a_different_experiment(tmp_path: Path):
    positive = emit_study_spec(_one_cell_15s_draft())
    positive_run = expand_study(positive).experiment["runs"][0]
    positive_state = run_experiment(
        positive_run,
        base_directory=tmp_path,
        execution_origin="study",
        cache_policy="off",
    )

    omitted = copy.deepcopy(positive_run)
    omitted["dataset"].pop("ingestion_mode", None)
    omitted["backtest"]["intrabar_model"] = "sl_first"
    omitted_state = run_experiment(
        omitted,
        base_directory=tmp_path,
        execution_origin="study",
        cache_policy="off",
    )
    provenance = omitted_state.get("ingestion_provenance")
    assert provenance is None or provenance.get("ingestion_mode") != (
        INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    )
    assert omitted_state["base_interval"] != "1min"
    assert omitted_state["base_interval"] == "15s"
    assert omitted_state["dataset_id"] != positive_state["dataset_id"]
