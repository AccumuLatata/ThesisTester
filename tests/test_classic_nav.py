"""CAI-8 — bidirectional navigation and identity-aware UI."""

from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path

import pytest

from thesistester.api import run_experiment
from thesistester.assistant import AssistantOrchestrator, AssistantTools, LocalThesisRepository
from thesistester.classic_context import (
    clear_classic_thesis_context,
    init_classic_session_state,
    link_thesis,
)
from thesistester.classic_nav import (
    clarification_target_page,
    consume_classic_focus_run,
    discuss_run,
    get_classic_active_run_id,
    identity_badge_label,
    latest_discussable_run,
    navigate_clarification_to_classic,
    open_exact_run_in_backtest,
    page_vs_run_identity_relation,
    resolve_run_identities,
    set_classic_active_run,
)
from thesistester.classic_record import record_classic_session_run
from thesistester.research_bundle import build_research_bundle, peek_research_identity
from thesistester.research_identity import (
    DataIdentity,
    LevelsIdentity,
    classify_identity_relation,
)
from tests.fixtures.assistant_parity import absolute_parity_run_spec, write_parity_bars


def _completed_state(tmp_path: Path) -> dict:
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


def test_classify_identity_relation_uses_immutable_identities(tmp_path: Path):
    state = _completed_state(tmp_path)
    page_levels = LevelsIdentity.from_page_state(state)
    assert classify_identity_relation(page_levels, page_levels) == "exact_match"
    assert identity_badge_label("exact_match") == "exact match"

    other_settings = dict(state["levels_settings"])
    other_settings["sma_lengths"] = [9]
    other_levels = LevelsIdentity.from_config(
        page_levels.data_identity, other_settings, instrument="ES"
    )
    assert classify_identity_relation(page_levels, other_levels) == "same_data_different_levels"

    other_data = DataIdentity(
        instrument="NQ",
        base_interval=page_levels.data_identity.base_interval,
        source_timezone=page_levels.data_identity.source_timezone,
        exchange_timezone=page_levels.data_identity.exchange_timezone,
        format_profile=page_levels.data_identity.format_profile,
        data_content_hash="0" * 64,
    )
    other_levels_data = LevelsIdentity.from_normalized(other_data, dict(state["levels_settings"]))
    assert classify_identity_relation(page_levels, other_levels_data) == "different_data"
    assert classify_identity_relation(None, page_levels) == "identity_unavailable"
    assert classify_identity_relation(page_levels, None) == "identity_unavailable"


def test_peek_research_identity_no_full_load(tmp_path: Path):
    state = _completed_state(tmp_path)
    raw = build_research_bundle(state)
    peeked = peek_research_identity(raw)
    assert isinstance(peeked, dict)
    assert "data_identity" in peeked or "levels_identity" in peeked
    path = tmp_path / "peek.research.zip"
    path.write_bytes(raw)
    assert peek_research_identity(path) == peeked
    assert peek_research_identity(tmp_path / "missing.zip") is None


def test_discuss_and_thesis_switch_clears_run_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="nav thesis")
    init_classic_session_state(state)
    link_thesis(
        state,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id=state["dataset_id"],
    )
    result = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=tmp_path / "store",
    )
    run_id = result.payload["run_id"]
    set_classic_active_run(state, run_id=run_id, thesis_id=thesis.thesis_id)
    assert get_classic_active_run_id(state) == run_id
    relation = page_vs_run_identity_relation(state, repository.get_run(thesis.thesis_id, run_id))
    assert relation in {
        "exact_match",
        "same_data_different_levels",
        "identity_unavailable",
    }

    focused = discuss_run(state, orchestrator=orchestrator, run_id=run_id)
    assert focused == run_id
    assert consume_classic_focus_run(state) == run_id
    assert state["classic_pending_navigation"] == "pages/14_Research_Assistant.py"
    assert state["assistant_selected_thesis_id"] == thesis.thesis_id

    other = repository.create_thesis(name="other")
    link_thesis(
        state,
        thesis_id=other.thesis_id,
        thesis_name=other.name,
        dataset_id=state["dataset_id"],
    )
    assert get_classic_active_run_id(state) is None
    with pytest.raises(
        ValueError, match="another thesis|not available on this thesis|No thesis-recorded"
    ):
        discuss_run(state, orchestrator=orchestrator, run_id=run_id)

    clear_classic_thesis_context(state)
    assert get_classic_active_run_id(state) is None


def test_discuss_syncs_assistant_thesis_and_skips_stale_active_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="discuss sync")
    other = repository.create_thesis(name="assistant picker")
    init_classic_session_state(state)
    link_thesis(
        state,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id=state["dataset_id"],
    )
    result = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=tmp_path / "store",
    )
    run_id = result.payload["run_id"]
    # Divergent Assistant picker must be realigned by Discuss.
    state["assistant_selected_thesis_id"] = other.thesis_id
    set_classic_active_run(state, run_id="run_missing_stale", thesis_id=thesis.thesis_id)

    focused = discuss_run(state, orchestrator=orchestrator)
    assert focused == run_id
    assert state["assistant_selected_thesis_id"] == thesis.thesis_id
    assert get_classic_active_run_id(state) == run_id
    assert consume_classic_focus_run(state) == run_id


def test_open_exact_run_restores_and_blocks_cross_thesis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="open exact")
    result = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=tmp_path / "store",
    )
    run_id = result.payload["run_id"]
    session: dict = {"assistant_selected_thesis_id": None}
    init_classic_session_state(session)
    handoff = open_exact_run_in_backtest(
        session,
        thesis_id=thesis.thesis_id,
        run_id=run_id,
        orchestrator=orchestrator,
    )
    assert handoff["run_id"] == run_id
    assert get_classic_active_run_id(session) == run_id
    assert session["classic_active_thesis_id"] == thesis.thesis_id
    assert session["classic_pending_navigation"] == "pages/7_Backtest.py"
    assert isinstance(session.get("trades"), type(state["trades"]))

    other = repository.create_thesis(name="blocked")
    with pytest.raises(Exception):
        # Cross-thesis get_run / open must fail closed.
        open_exact_run_in_backtest(
            session,
            thesis_id=other.thesis_id,
            run_id=run_id,
            orchestrator=orchestrator,
        )


def test_clarification_navigation_prefill_only(tmp_path: Path):
    session: dict = {}
    init_classic_session_state(session)
    assert clarification_target_page("Select a dataset and instrument") == "pages/1_Data.py"
    assert clarification_target_page("Enable developing RTH VWAP") == "pages/2_Levels.py"
    assert (
        clarification_target_page("Define setup levels and tolerance") == "pages/3_Setup_Builder.py"
    )
    assert (
        clarification_target_page("Define costs, exposure, and intrabar model")
        == "pages/7_Backtest.py"
    )
    target = navigate_clarification_to_classic(
        session, clarification="Select a dataset and instrument"
    )
    assert target == "pages/1_Data.py"
    # Callers switch_page directly; pending must stay clear so Data/Levels
    # (no thesis chrome) cannot leave a stale redirect for later pages.
    assert session.get("classic_pending_navigation") in (None, "")
    assert session["classic_nav_prefill"]["target_page"] == "pages/1_Data.py"
    assert session["classic_nav_prefill"]["note"]
    # Prefill is caption-only staging — no widget keys mutated.
    assert "backtest_sl_ticks" not in session


def test_backtest_prefill_caption_before_trades_stop():
    """Empty Backtest must still surface Assistant clarification prefills."""
    root = Path(__file__).resolve().parents[1]
    source = (root / "pages" / "7_Backtest.py").read_text(encoding="utf-8")
    prefill_idx = source.index(
        'render_classic_nav_prefill_caption(target_page="pages/7_Backtest.py")'
    )
    discuss_idx = source.index('render_discuss_this_run(page_key="backtest")')
    trades_stop_idx = source.index(
        'st.info("Configure settings in the sidebar and click **▶ Run backtest**.")'
    )
    assert prefill_idx < trades_stop_idx
    assert discuss_idx < trades_stop_idx
    signals_stop_idx = source.index("No signals found.")
    assert prefill_idx < signals_stop_idx


def test_bundles_discuss_not_gated_on_live_backtest_artifacts():
    root = Path(__file__).resolve().parents[1]
    source = (root / "pages" / "12_Research_Bundles.py").read_text(encoding="utf-8")
    discuss_idx = source.index('render_discuss_this_run(page_key="research_bundles")')
    gated_prefix = source[source.index("if _will_include_backtest():") : discuss_idx]
    assert "render_discuss_this_run" not in gated_prefix
    assert discuss_idx > 0


def test_resolve_run_identities_from_provenance_or_peek(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("THESISTESTER_STORE_DIR", str(tmp_path / "store"))
    state = _completed_state(tmp_path)
    orchestrator, repository = _orchestrator(tmp_path)
    thesis = repository.create_thesis(name="ident")
    result = record_classic_session_run(
        orchestrator,
        thesis_id=thesis.thesis_id,
        session_state=state,
        store_root=tmp_path / "store",
    )
    run = repository.get_run(thesis.thesis_id, result.payload["run_id"])
    data, levels = resolve_run_identities(run)
    assert data is not None or levels is not None
    assert latest_discussable_run(orchestrator, thesis_id=thesis.thesis_id) is not None


def test_pages_wire_discuss_and_open_exact():
    root = Path(__file__).resolve().parents[1]
    backtest = (root / "pages" / "7_Backtest.py").read_text(encoding="utf-8")
    bundles = (root / "pages" / "12_Research_Bundles.py").read_text(encoding="utf-8")
    assistant = (root / "pages" / "14_Research_Assistant.py").read_text(encoding="utf-8")
    assert "render_discuss_this_run" in backtest
    assert "render_discuss_this_run" in bundles
    assert "Open exact run in Backtest" in assistant
    assert "navigate_clarification_to_classic" in assistant
    context = (root / "thesistester" / "classic_context.py").read_text(encoding="utf-8")
    tree = ast.parse(context)
    forbidden = {"record_classic_session_run", "register_external_bundle_run"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden:
                found.add(func.id)
            elif isinstance(func, ast.Attribute) and func.attr in forbidden:
                found.add(func.attr)
    assert found == set()
