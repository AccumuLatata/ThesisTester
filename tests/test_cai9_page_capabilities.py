"""CAI-9 — evidence-backed page capability expansion."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from thesistester.api import run_experiment
from thesistester.assistant import (
    AssistantOrchestrator,
    AssistantRequest,
    AssistantTools,
    CapabilityMode,
    FEATURE_PARITY_REGISTRY,
    HANDLER_REGISTRY,
    LocalThesisRepository,
    assert_claims_grounded,
    build_evidence_packet,
    explain_evidence_report,
)
from thesistester.assistant.page_summaries import (
    summarize_backtest_state,
    summarize_grid_state,
    summarize_levels_state,
    summarize_signals_state,
    summarize_validation_state,
)
from thesistester.classic_context import init_classic_session_state, link_thesis
from thesistester.classic_proposal import (
    apply_classic_proposal,
    get_classic_proposal,
    stage_classic_proposal,
    validate_classic_proposal,
)
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from thesistester.research_identity import DataIdentity
from tests.fixtures.assistant_parity import absolute_parity_run_spec, write_parity_bars


def _completed_state(tmp_path: Path) -> dict:
    write_parity_bars(tmp_path / "bars.csv")
    spec = absolute_parity_run_spec(tmp_path)
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    state["dataset_source_path"] = str(tmp_path / "bars.csv")
    state["dataset_id"] = DataIdentity.from_loaded_data(
        state["data"],
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="canonical",
    ).dataset_id()
    return state


def _bundle_on_disk(tmp_path: Path, state: dict) -> tuple[Path, str]:
    raw = build_research_bundle(state)
    path = tmp_path / "cai9.research.zip"
    path.write_bytes(raw)
    return path, canonical_bundle_hash(raw)


def _assert_json_safe_no_frames(payload: object) -> None:
    serialized = json.dumps(payload)
    assert "DataFrame" not in serialized
    assert isinstance(json.loads(serialized), (dict, list, str, int, float, bool, type(None)))


def test_page_summaries_are_bounded_and_available(tmp_path: Path):
    state = _completed_state(tmp_path)
    levels = summarize_levels_state(state)
    signals = summarize_signals_state(state)
    backtest = summarize_backtest_state(state)
    grid = summarize_grid_state(state)
    validation = summarize_validation_state(state)
    assert levels["available"] is True
    assert levels["level_column_count"] >= 1
    assert "families" in levels
    assert signals["available"] is True
    assert signals["signal_count"] >= 1
    assert "trigger_distribution" in signals
    assert backtest["available"] is True
    assert "kpis" in backtest
    assert grid["available"] is True
    assert validation["available"] is True
    for payload in (levels, signals, backtest, grid, validation):
        _assert_json_safe_no_frames(payload)


def test_inspect_capabilities_routed_and_hash_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _completed_state(tmp_path)
    bundle_path, digest = _bundle_on_disk(tmp_path, state)
    tools = AssistantTools(data_roots=(tmp_path, Path.cwd()))
    repository = LocalThesisRepository(tmp_path / "assistant")
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)
    thesis = repository.create_thesis(name="cai9")

    capabilities = (
        "LEVELS.inspect_and_chart",
        "SIGNALS.inspect_and_chart",
        "BACKTEST.inspect_results",
        "GRID.inspect_results",
        "VALIDATION.inspect_results",
    )
    for capability_id in capabilities:
        capability = next(c for c in FEATURE_PARITY_REGISTRY if c.capability_id == capability_id)
        assert capability.mode is CapabilityMode.INSPECT_ONLY
        assert capability_id in HANDLER_REGISTRY
        ok = orchestrator.dispatch(
            AssistantRequest(
                capability_id=capability_id,
                payload={"bundle_path": str(bundle_path), "expected_hash": digest},
            ),
            thesis_id=thesis.thesis_id,
        )
        assert ok.status == "completed"
        _assert_json_safe_no_frames(ok.payload)
        # Inspect payload keys must match evidence-packet results.* paths.
        expected_keys = {
            "LEVELS.inspect_and_chart": "levels_summary",
            "SIGNALS.inspect_and_chart": "signals_summary",
            "BACKTEST.inspect_results": "backtest_page_summary",
            "GRID.inspect_results": "grid_summary",
            "VALIDATION.inspect_results": "validation_page_summary",
        }
        assert expected_keys[capability_id] in ok.payload
        bad = orchestrator.dispatch(
            AssistantRequest(
                capability_id=capability_id,
                payload={"bundle_path": str(bundle_path), "expected_hash": "0" * 64},
            ),
            thesis_id=thesis.thesis_id,
        )
        assert bad.status == "failed"


def test_evidence_packet_includes_page_summaries_and_grounded_claims(tmp_path: Path):
    state = _completed_state(tmp_path)
    packet = build_evidence_packet(state, provenance={"bundle_path": "x"})
    assert packet.results.get("levels_summary", {}).get("available") is True
    assert packet.results.get("signals_summary", {}).get("available") is True
    assert packet.results.get("backtest_page_summary", {}).get("available") is True
    report = explain_evidence_report(packet)
    assert_claims_grounded(packet, report)
    paths = {claim["path"] for claim in report["claims"]}
    assert any(path.startswith("results.levels_summary.") for path in paths)
    assert any(path.startswith("results.signals_summary.") for path in paths)


def test_classic_proposal_stages_without_mutation_until_apply(tmp_path: Path):
    session: dict = {
        "setup_config": {"tolerance_ticks": 4.0, "trigger": "touch"},
        "backtest_sl_ticks": 8.0,
        "backtest_tp_ticks": 16.0,
    }
    init_classic_session_state(session)
    # Proposals are thesis-scoped: link first, then stage. First link must not
    # wipe a proposal once the same thesis is already active.
    link_thesis(
        session,
        thesis_id="thesis-a",
        thesis_name="A",
        dataset_id="ds-1",
    )
    stage_classic_proposal(
        session,
        validate_classic_proposal(
            target_page="pages/7_Backtest.py",
            draft_patch={"stop_loss_ticks": 12.0, "take_profit_ticks": 24.0},
            note="Widen stops from evidence",
            evidence_paths=["results.backtest_page_summary.kpis.trade_count"],
        ),
        navigate=False,
    )
    # Re-link same thesis must preserve the staged proposal.
    link_thesis(
        session,
        thesis_id="thesis-a",
        thesis_name="A",
        dataset_id="ds-1",
    )
    assert get_classic_proposal(session) is not None
    assert get_classic_proposal(session)["thesis_id"] == "thesis-a"
    assert session["backtest_sl_ticks"] == 8.0  # not applied yet

    # Re-stage with navigation for the apply path.
    staged = stage_classic_proposal(
        session,
        validate_classic_proposal(
            target_page="pages/7_Backtest.py",
            draft_patch={"stop_loss_ticks": 12.0, "take_profit_ticks": 24.0},
            note="Widen stops from evidence",
            evidence_paths=["results.backtest_page_summary.kpis.trade_count"],
        ),
        navigate=True,
    )
    assert staged["target_page"] == "pages/7_Backtest.py"
    assert staged["thesis_id"] == "thesis-a"
    assert session["classic_pending_navigation"] == "pages/7_Backtest.py"

    applied = apply_classic_proposal(session, target_page="pages/7_Backtest.py")
    assert applied["applied"]["stop_loss_ticks"] == 12.0
    assert session["backtest_sl_ticks"] == 12.0
    assert session["backtest_tp_ticks"] == 24.0
    assert get_classic_proposal(session) is None

    # Thesis switch clears staged proposals.
    stage_classic_proposal(
        session,
        validate_classic_proposal(
            target_page="pages/3_Setup_Builder.py",
            draft_patch={"tolerance_ticks": 6.0},
            note="Tighten tolerance",
        ),
        navigate=False,
    )
    link_thesis(
        session,
        thesis_id="thesis-b",
        thesis_name="B",
        dataset_id="ds-1",
    )
    assert get_classic_proposal(session) is None


def test_proposal_apply_rejects_cross_thesis_scope():
    session: dict = {
        "backtest_sl_ticks": 8.0,
        "backtest_tp_ticks": 16.0,
    }
    init_classic_session_state(session)
    link_thesis(session, thesis_id="thesis-a", thesis_name="A", dataset_id="ds-1")
    stage_classic_proposal(
        session,
        validate_classic_proposal(
            target_page="pages/7_Backtest.py",
            draft_patch={"stop_loss_ticks": 12.0, "take_profit_ticks": 24.0},
            note="From thesis A",
        ),
        navigate=False,
        thesis_id="thesis-a",
    )
    # Simulate a stale payload that still points at thesis A after a soft switch
    # that did not clear (get_classic_proposal must fail closed).
    session["classic_active_thesis_id"] = "thesis-b"
    assert get_classic_proposal(session) is None
    session["classic_active_thesis_id"] = "thesis-a"
    assert get_classic_proposal(session)["thesis_id"] == "thesis-a"
    with pytest.raises(ValueError, match="active thesis"):
        stage_classic_proposal(
            session,
            validate_classic_proposal(
                target_page="pages/7_Backtest.py",
                draft_patch={"stop_loss_ticks": 14.0, "take_profit_ticks": 28.0},
                note="Wrong thesis",
            ),
            navigate=False,
            thesis_id="thesis-other",
        )


def test_proposal_survives_relink_to_its_own_thesis():
    session: dict = {"backtest_sl_ticks": 8.0, "backtest_tp_ticks": 16.0}
    init_classic_session_state(session)
    # Stage for A before classic research mode is linked.
    stage_classic_proposal(
        session,
        validate_classic_proposal(
            target_page="pages/7_Backtest.py",
            draft_patch={"stop_loss_ticks": 12.0, "take_profit_ticks": 24.0},
            note="From thesis A",
        ),
        navigate=False,
        thesis_id="thesis-a",
    )
    link_thesis(session, thesis_id="thesis-b", thesis_name="B", dataset_id="ds-1")
    assert get_classic_proposal(session) is None  # hidden while B is active
    assert session["classic_page_proposal"]["thesis_id"] == "thesis-a"  # still staged
    link_thesis(session, thesis_id="thesis-a", thesis_name="A", dataset_id="ds-1")
    assert get_classic_proposal(session)["thesis_id"] == "thesis-a"
    link_thesis(session, thesis_id="thesis-c", thesis_name="C", dataset_id="ds-1")
    assert get_classic_proposal(session) is None
    assert session.get("classic_page_proposal") is None


def test_proposal_rejects_zero_stop_loss_ticks():
    with pytest.raises(ValueError, match="stop_loss_ticks must be >= 1"):
        validate_classic_proposal(
            target_page="pages/7_Backtest.py",
            draft_patch={"stop_loss_ticks": 0.0, "take_profit_ticks": 2.0},
            note="Invalid zero stop",
        )
    with pytest.raises(ValueError, match="take_profit_ticks must be >= 1"):
        validate_classic_proposal(
            target_page="pages/7_Backtest.py",
            draft_patch={"stop_loss_ticks": 2.0, "take_profit_ticks": 0},
            note="Invalid zero target",
        )


def test_backtest_inspect_matches_evidence_cost_assumptions(tmp_path: Path):
    state = _completed_state(tmp_path)
    # Strip session cost keys so only provenance effective_configuration carries them.
    state = dict(state)
    state["backtest_execution_costs"] = {}
    state["backtest_config"] = {}
    bundle_path, digest = _bundle_on_disk(tmp_path, state)
    provenance = {
        "bundle_path": str(bundle_path),
        "canonical_bundle_hash": digest,
        "effective_configuration": {
            "backtest": {
                "commission_per_side": 1.5,
                "slippage_ticks": 0.25,
                "stop_loss_ticks": 8.0,
                "take_profit_ticks": 16.0,
            }
        },
    }
    packet = build_evidence_packet(state, provenance=provenance)
    tools = AssistantTools(data_roots=(tmp_path,))
    inspected = tools.summarize_bundle_backtest(
        bundle_path, expected_hash=digest, provenance=provenance
    )
    evidence_costs = packet.results["backtest_page_summary"]["costs"]
    inspect_costs = inspected["backtest_page_summary"]["costs"]
    assert inspect_costs["commission_per_side"] == evidence_costs["commission_per_side"] == 1.5
    assert inspect_costs["slippage_ticks"] == evidence_costs["slippage_ticks"] == 0.25
    assert "zero_costs" not in inspected["backtest_page_summary"]["caveats"]
    assert "zero_costs" not in packet.results["backtest_page_summary"]["caveats"]


def test_backtest_summary_cost_caveat_matches_assumptions():
    state = {
        "trade_summary": {"trade_count": 50, "win_rate": 0.5},
        # Session keys look zeroed / missing — provenance assumptions win.
        "backtest_execution_costs": {},
        "backtest_config": {},
    }
    summary_missing = summarize_backtest_state(state)
    assert "zero_costs" not in summary_missing["caveats"]
    summary_nonzero = summarize_backtest_state(
        state,
        cost_assumptions={"commission_per_side": 1.25, "slippage_ticks": 0.5},
    )
    assert summary_nonzero["costs"]["commission_per_side"] == 1.25
    assert "zero_costs" not in summary_nonzero["caveats"]
    summary_zero = summarize_backtest_state(
        state,
        cost_assumptions={"commission_per_side": 0.0, "slippage_ticks": 0.0},
    )
    assert "zero_costs" in summary_zero["caveats"]
    nested = {
        "trade_summary": {"trade_count": 50},
        "backtest": {"commission_per_side": 2.0, "slippage_ticks": 1.0},
    }
    nested_summary = summarize_backtest_state(nested)
    assert nested_summary["costs"]["commission_per_side"] == 2.0
    assert "zero_costs" not in nested_summary["caveats"]


def test_backtest_apply_syncs_backtest_config_and_costs():
    session: dict = {
        "backtest_sl_ticks": 8.0,
        "backtest_tp_ticks": 16.0,
        "backtest_commission_per_side": 0.0,
        "backtest_slippage_ticks": 0.0,
        "backtest_config": {
            "stop_loss_ticks": 8.0,
            "take_profit_ticks": 16.0,
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
            "exposure_policy": "single_position",
        },
        "backtest_execution_costs": {
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
        },
    }
    init_classic_session_state(session)
    link_thesis(session, thesis_id="thesis-a", thesis_name="A", dataset_id="ds-1")
    stage_classic_proposal(
        session,
        validate_classic_proposal(
            target_page="pages/7_Backtest.py",
            draft_patch={
                "stop_loss_ticks": 12.0,
                "take_profit_ticks": 24.0,
                "commission_per_side": 1.25,
                "slippage_ticks": 0.5,
            },
            note="Sync producer keys",
        ),
        navigate=False,
    )
    apply_classic_proposal(session, target_page="pages/7_Backtest.py")
    assert session["backtest_sl_ticks"] == 12.0
    assert session["backtest_config"]["stop_loss_ticks"] == 12.0
    assert session["backtest_config"]["take_profit_ticks"] == 24.0
    assert session["backtest_config"]["commission_per_side"] == 1.25
    assert session["backtest_execution_costs"]["commission_per_side"] == 1.25
    assert session["backtest_execution_costs"]["slippage_ticks"] == 0.5


def test_setup_proposal_maps_anchor_rules_label():
    session: dict = {"setup_config": {"confluence_mode": "global_cluster"}}
    init_classic_session_state(session)
    link_thesis(session, thesis_id="thesis-a", thesis_name="A", dataset_id="ds-1")
    stage_classic_proposal(
        session,
        validate_classic_proposal(
            target_page="pages/3_Setup_Builder.py",
            draft_patch={"confluence_mode": "anchor_rules"},
            note="Switch to anchor rules",
        ),
        navigate=False,
    )
    apply_classic_proposal(session, target_page="pages/3_Setup_Builder.py")
    assert session["_setup_builder_confluence_mode"] == "Anchor-based rules"
    assert session["setup_config"]["confluence_mode"] == "anchor_rules"
    with pytest.raises(ValueError, match="confluence_mode must be one of"):
        validate_classic_proposal(
            target_page="pages/3_Setup_Builder.py",
            draft_patch={"confluence_mode": "anchor_confluence"},
            note="Legacy bad mode",
        )


def test_propose_capability_via_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    tools = AssistantTools(data_roots=(tmp_path,))
    repository = LocalThesisRepository(tmp_path / "assistant")
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)
    thesis = repository.create_thesis(name="propose")
    session: dict = {}
    init_classic_session_state(session)
    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id="ds-1",
    )
    result = orchestrator.propose_classic_page_change(
        thesis_id=thesis.thesis_id,
        target_page="pages/7_Backtest.py",
        draft_patch={"stop_loss_ticks": 10.0, "take_profit_ticks": 20.0},
        note="From run evidence",
        evidence_paths=["results.grid_summary.best_cell.stop_loss_ticks"],
        session_state=session,
        navigate=True,
    )
    assert result.status == "completed"
    assert result.payload["staged"] is True
    assert result.payload["applied"] is False
    assert session["classic_page_proposal"]["draft_patch"]["stop_loss_ticks"] == 10.0
    assert session["classic_page_proposal"]["thesis_id"] == thesis.thesis_id


def test_classic_context_forbids_proposal_apply_calls():
    root = Path(__file__).resolve().parents[1]
    context = (root / "thesistester" / "classic_context.py").read_text(encoding="utf-8")
    tree = ast.parse(context)
    forbidden = {"apply_classic_proposal", "stage_classic_proposal", "record_classic_session_run"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden:
                found.add(func.id)
            elif isinstance(func, ast.Attribute) and func.attr in forbidden:
                found.add(func.attr)
    assert found == set()


def test_pages_wire_proposal_and_summaries():
    root = Path(__file__).resolve().parents[1]
    assistant = (root / "pages" / "14_Research_Assistant.py").read_text(encoding="utf-8")
    setup = (root / "pages" / "3_Setup_Builder.py").read_text(encoding="utf-8")
    backtest = (root / "pages" / "7_Backtest.py").read_text(encoding="utf-8")
    assert "inspect_run_page_summary" in assistant
    assert "except ValueError as exc" in assistant
    assert "propose_classic_page_change" in assistant
    assert "render_classic_proposal_card" in setup
    assert "render_classic_proposal_card" in backtest
    nav = (root / "thesistester" / "classic_nav.py").read_text(encoding="utf-8")
    assert "clear_classic_proposal" in nav
