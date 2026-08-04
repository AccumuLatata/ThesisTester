"""CAI-7 — research-mode all_executions classic ledger."""

from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path

import pytest

from thesistester.api import run_experiment
from thesistester.assistant import AssistantOrchestrator, AssistantTools, LocalThesisRepository
from thesistester.classic_context import (
    init_classic_session_state,
    link_thesis,
    set_recording_policy,
)
from thesistester.classic_ledger import (
    CLASSIC_LEDGER_ACTION,
    begin_classic_execution_ledger,
    complete_classic_execution_ledger,
    fail_classic_execution_ledger,
    is_classic_ledger_run,
    ledger_run_label,
    should_record_all_executions,
)
from thesistester.research_identity import DataIdentity
from tests.fixtures.assistant_parity import absolute_parity_run_spec, write_parity_bars


def _classic_pre_exec_state(tmp_path: Path) -> dict:
    """Session state before a Backtest click (no trades yet)."""
    write_parity_bars(tmp_path / "bars.csv")
    spec = absolute_parity_run_spec(tmp_path)
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    # Drop post-run artifacts so begin mirrors a pre-execution classic page.
    for key in ("trades", "equity_curve", "trade_summary", "skipped_signals"):
        state.pop(key, None)
    state["dataset_source_path"] = str(tmp_path / "bars.csv")
    state["backtest_config"] = deepcopy(spec["backtest"])
    # Widget keys mirror the Backtest sidebar contract.
    state["backtest_sl_ticks"] = spec["backtest"]["stop_loss_ticks"]
    state["backtest_tp_ticks"] = spec["backtest"]["take_profit_ticks"]
    state["dataset_id"] = DataIdentity.from_loaded_data(
        state["data"],
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="canonical",
    ).dataset_id()
    return state


def _classic_completed_state(tmp_path: Path) -> dict:
    write_parity_bars(tmp_path / "bars.csv")
    spec = absolute_parity_run_spec(tmp_path)
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    state["dataset_source_path"] = str(tmp_path / "bars.csv")
    state["backtest_config"] = deepcopy(spec["backtest"])
    state["dataset_id"] = DataIdentity.from_loaded_data(
        state["data"],
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="canonical",
    ).dataset_id()
    return state


def _orchestrator(tmp_path: Path) -> tuple[AssistantOrchestrator, LocalThesisRepository]:
    repository = LocalThesisRepository(tmp_path / "assistant")
    tools = AssistantTools(data_roots=(tmp_path, Path.cwd()))
    return AssistantOrchestrator(tools=tools, repository=repository), repository


def test_should_record_requires_research_mode_and_policy():
    session: dict = {}
    init_classic_session_state(session)
    assert should_record_all_executions(session) is False
    set_recording_policy(session, "all_executions")
    assert should_record_all_executions(session) is False
    link_thesis(
        session,
        thesis_id="th" + ("a" * 32),
        thesis_name="T",
        dataset_id="ds",
    )
    assert should_record_all_executions(session) is True
    set_recording_policy(session, "manual")
    assert should_record_all_executions(session) is False


def test_begin_ledger_materializes_quantower_session_as_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """CAI-7 begin must not verify materialized lineage CSV with a vendor profile."""
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    pre = _classic_pre_exec_state(tmp_path)
    pre["format_profile"] = "quantower_history_exporter"
    pre.pop("dataset_source_path", None)
    pre.pop("source_csv_path", None)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="quantower ledger")

    handle = begin_classic_execution_ledger(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=pre,
        origin_page="backtest",
        store_root=tmp_path / "store",
    )
    running = repository.get_run(thesis.thesis_id, handle.run_id)
    run_spec = running.request.get("run_spec") or {}
    dataset = run_spec.get("dataset") if isinstance(run_spec, dict) else {}
    assert dataset.get("format_profile") == "canonical"
    assert Path(str(dataset.get("path", ""))).name == "classic_source.csv"


def test_begin_fail_complete_ledger_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    pre = _classic_pre_exec_state(tmp_path)
    completed = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="ledger thesis")

    handle = begin_classic_execution_ledger(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=pre,
        origin_page="backtest",
        store_root=tmp_path / "store",
    )
    running = repository.get_run(thesis.thesis_id, handle.run_id)
    assert running.status == "running"
    assert running.provenance is None
    assert running.request["action"] == CLASSIC_LEDGER_ACTION
    assert running.request["origin_page"] == "backtest"
    assert running.request["classic_config_hash"]
    assert is_classic_ledger_run(running)
    assert ledger_run_label(running) == "ledger:backtest"

    failed = fail_classic_execution_ledger(
        orchestrator,
        handle,
        message="forced simulate failure",
        phase="simulate",
    )
    assert failed.status == "failed"
    assert failed.status != "completed"
    assert failed.error["phase"] == "simulate"
    assert failed.request["classic_config_hash"] == handle.config_hash
    assert failed.provenance is None

    # Fresh attempt that completes with a bundle.
    handle2 = begin_classic_execution_ledger(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=pre,
        origin_page="backtest",
        store_root=tmp_path / "store",
    )
    done = complete_classic_execution_ledger(
        orchestrator,
        handle2,
        session_state=completed,
        store_root=tmp_path / "store",
    )
    assert done.status == "completed"
    assert done.provenance["execution_origin"] == "classic"
    assert done.provenance["canonical_bundle_hash"]
    assert Path(done.provenance["bundle_path"]).is_file()
    assert done.provenance["classic_config_hash"] == handle2.config_hash


def test_failed_bundle_write_preserves_request_not_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    pre = _classic_pre_exec_state(tmp_path)
    completed = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="bundle fail")

    handle = begin_classic_execution_ledger(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=pre,
        origin_page="backtest",
        store_root=tmp_path / "store",
    )
    request_before = deepcopy(repository.get_run(thesis.thesis_id, handle.run_id).request)

    def _boom(_session):
        raise OSError("disk full")

    monkeypatch.setattr(
        "thesistester.classic_ledger.build_research_bundle",
        _boom,
    )
    terminal = complete_classic_execution_ledger(
        orchestrator,
        handle,
        session_state=completed,
        store_root=tmp_path / "store",
    )
    assert terminal.status == "failed"
    assert terminal.status != "completed"
    assert terminal.error["phase"] == "bundle_write"
    assert terminal.error.get("simulation_succeeded") is True
    assert terminal.request == request_before
    assert terminal.provenance is None


def test_cancelled_ledger_run_is_not_completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    pre = _classic_pre_exec_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="cancel ledger")
    handle = begin_classic_execution_ledger(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=pre,
        origin_page="backtest",
        store_root=tmp_path / "store",
    )
    cancelled = repository.cancel_run(
        thesis.thesis_id,
        handle.run_id,
        expected_revision=handle.revision,
        reason="Cancelled during classic execution.",
    )
    assert cancelled.status == "cancelled"
    assert cancelled.status != "completed"
    assert cancelled.request["action"] == CLASSIC_LEDGER_ACTION
    assert cancelled.error["reason"]


def test_complete_run_failure_fails_ledger_not_left_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """complete_run errors must terminalize via fail_run (never stay running)."""
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    pre = _classic_pre_exec_state(tmp_path)
    completed = _classic_completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="complete fail")
    handle = begin_classic_execution_ledger(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=pre,
        origin_page="backtest",
        store_root=tmp_path / "store",
    )
    request_before = deepcopy(repository.get_run(thesis.thesis_id, handle.run_id).request)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("repository unavailable")

    monkeypatch.setattr(repository, "complete_run", _boom)
    terminal = complete_classic_execution_ledger(
        orchestrator,
        handle,
        session_state=completed,
        store_root=tmp_path / "store",
    )
    assert terminal.status == "failed"
    assert terminal.status != "completed"
    assert terminal.status != "running"
    assert terminal.error["phase"] == "complete_run"
    assert terminal.error.get("simulation_succeeded") is True
    assert terminal.request == request_before
    assert terminal.provenance is None


def test_manual_policy_does_not_require_ledger_helpers():
    """Sanity: Backtest path gates on should_record_all_executions only."""
    from thesistester.classic_context import get_recording_policy

    session = {"classic_active_thesis_id": "th" + ("b" * 32)}
    init_classic_session_state(session)
    assert get_recording_policy(session) == "manual"
    assert should_record_all_executions(session) is False


def test_pages_wire_ledger_and_context_forbids_ledger_calls():
    root = Path(__file__).resolve().parents[1]
    backtest = (root / "pages" / "7_Backtest.py").read_text(encoding="utf-8")
    assistant = (root / "pages" / "14_Research_Assistant.py").read_text(encoding="utf-8")
    assert "begin_classic_execution_ledger" in backtest
    assert "render_classic_execution_ledger" in backtest
    assert "ledger_run_label" in assistant
    # Post-begin failures must hit a broad except that calls fail_* (CAI-7).
    assert "except Exception" in backtest
    assert "fail_classic_execution_ledger" in backtest
    assert "_ledger_phase" in backtest
    context = (root / "thesistester" / "classic_context.py").read_text(encoding="utf-8")
    assert "begin_classic_execution_ledger" not in context
    assert "complete_classic_execution_ledger" not in context
    tree = ast.parse(context)
    forbidden = {
        "begin_classic_execution_ledger",
        "complete_classic_execution_ledger",
        "fail_classic_execution_ledger",
    }
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in forbidden:
                found.add(node.func.id)
    assert found == set()


def test_provenance_card_includes_ledger_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from thesistester.assistant.workspace import build_provenance_card

    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    pre = _classic_pre_exec_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="card")
    handle = begin_classic_execution_ledger(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=pre,
        origin_page="backtest",
        store_root=tmp_path / "store",
    )
    failed = fail_classic_execution_ledger(
        orchestrator,
        handle,
        message="x",
        phase="otf_filter",
    )
    card = build_provenance_card(failed.to_dict())
    assert card["request_action"] == CLASSIC_LEDGER_ACTION
    assert card["origin_page"] == "backtest"
    assert card["classic_config_hash"]
    assert card["execution_origin"] == "classic"
    assert card["status"] == "failed"
