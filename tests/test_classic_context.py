"""CAI-5 — classic thesis research context lifecycle."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from thesistester.assistant import AssistantOrchestrator, LocalThesisRepository
from thesistester.assistant.workspace import THESIS_SCOPED_STAGING_KEYS
from thesistester.classic_context import (
    CLASSIC_PENDING_NAVIGATION_PAGES,
    CLASSIC_SESSION_KEYS,
    CLASSIC_THESIS_SCOPED_KEYS,
    DEFAULT_RECORDING_POLICY,
    PROTECTED_CLASSIC_SESSION_KEYS,
    RECORDING_POLICIES,
    assert_protected_classic_keys_unchanged,
    clear_classic_thesis_context,
    consume_classic_flash,
    consume_pending_navigation,
    exit_research_mode,
    get_active_thesis_id,
    get_active_thesis_name,
    get_recording_policy,
    init_classic_session_state,
    is_research_mode,
    link_thesis,
    resolve_pending_navigation_target,
    set_classic_flash,
    set_pending_navigation,
    set_recording_policy,
    snapshot_protected_classic_keys,
    sync_classic_context_for_dataset,
)


def _seed_classic_page_state() -> dict:
    levels = pd.DataFrame({"timestamp": [1], "ONH": [100.0]})
    data = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-02 09:30:00"]),
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [10],
        }
    )
    return {
        "data": data,
        "dataset_id": "ds_test_aaa",
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
        "format_profile": "canonical",
        "levels": levels,
        "session_levels": levels.copy(),
        "levels_settings": {"opening_range_minutes": 30},
        "levels_data_fingerprint": {"rows": 1, "instrument": "ES"},
        "setup_config": {"setup_name": "demo", "direction": "both"},
        "signals": pd.DataFrame({"timestamp": [1]}),
        "confluence_zones": pd.DataFrame({"timestamp": [1]}),
        "naked_flags": pd.DataFrame({"timestamp": [1]}),
        "last_signal_setup": {"setup_name": "demo"},
        "signal_settings": {"tolerance_ticks": 2},
        "trades": pd.DataFrame({"r_multiple": [1.0]}),
        "equity_curve": pd.DataFrame({"equity": [1.0]}),
        "backtest_config": {"sl_ticks": 10, "tp_ticks": 20},
        "backtest_summary": {"n_trades": 1},
        # Assistant staging that must clear on thesis switch via select_thesis.
        "assistant_draft_prompt": "keep me only until thesis changes",
        "assistant_draft_choices": {"setup": {"direction": "long"}},
        "assistant_validated_run_spec": {"spec": {"name": "x"}},
        "assistant_bundle_handoff": {"run_id": "run_old"},
        "assistant_flash": {"level": "info", "message": "stale"},
        "assistant_selected_thesis_id": "th_old_should_change",
        "assistant_hydrated_conversation_id": "conv_old",
    }


def test_init_defaults_and_key_contract():
    session: dict = {}
    init_classic_session_state(session)
    assert set(CLASSIC_SESSION_KEYS) == set(session)
    assert session["classic_recording_policy"] == DEFAULT_RECORDING_POLICY
    assert DEFAULT_RECORDING_POLICY == "manual"
    assert "manual" in RECORDING_POLICIES
    assert set(CLASSIC_THESIS_SCOPED_KEYS).issubset(CLASSIC_SESSION_KEYS)


def test_link_thesis_sets_context_and_syncs_assistant_without_mutating_page_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = LocalThesisRepository(tmp_path / "assistant")
    thesis = repo.create_thesis(name="OR reclaim")
    session = _seed_classic_page_state()
    before = snapshot_protected_classic_keys(session)

    recorded: list[str] = []

    def _forbid_record(*_args, **_kwargs):
        recorded.append("record")
        raise AssertionError("linking must not record a run")

    for attr in ("execute_confirmed_run", "start_run", "cancel_run"):
        if hasattr(AssistantOrchestrator, attr):
            monkeypatch.setattr(AssistantOrchestrator, attr, _forbid_record)

    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id="ds_test_aaa",
    )

    assert recorded == []
    assert is_research_mode(session)
    assert get_active_thesis_id(session) == thesis.thesis_id
    assert get_active_thesis_name(session) == "OR reclaim"
    assert session["classic_bound_dataset_id"] == "ds_test_aaa"
    assert get_recording_policy(session) == "manual"
    assert session["assistant_selected_thesis_id"] == thesis.thesis_id
    for key in THESIS_SCOPED_STAGING_KEYS:
        if key == "assistant_draft_prompt":
            assert session[key] == ""
        elif key in {"assistant_draft_choices"}:
            assert session[key] == {}
        else:
            assert session[key] in (None, {})
    assert_protected_classic_keys_unchanged(before, session)
    # Same object identity for DataFrames (no copy/replace on link).
    assert session["data"] is before["data"]
    assert session["levels"] is before["levels"]
    assert session["setup_config"] is before["setup_config"]


def test_link_thesis_does_not_call_repository_run_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = LocalThesisRepository(tmp_path / "assistant")
    thesis = repo.create_thesis(name="No run")
    session = _seed_classic_page_state()
    calls: list[str] = []

    monkeypatch.setattr(
        LocalThesisRepository,
        "start_run",
        lambda *a, **k: (
            calls.append("start_run") or (_ for _ in ()).throw(AssertionError("start_run"))
        ),
    )
    monkeypatch.setattr(
        LocalThesisRepository,
        "create_spec_version",
        lambda *a, **k: (
            calls.append("create_spec_version")
            or (_ for _ in ()).throw(AssertionError("create_spec_version"))
        ),
    )

    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id=session["dataset_id"],
    )
    assert calls == []
    thesis_dir = tmp_path / "assistant" / "theses" / thesis.thesis_id
    assert (thesis_dir / "meta.json").is_file()
    assert not (thesis_dir / "runs").exists()
    assert not (thesis_dir / "specs").exists()


def test_exit_and_dataset_switch_clear_context_without_leaking(tmp_path: Path):
    repo = LocalThesisRepository(tmp_path / "assistant")
    thesis = repo.create_thesis(name="Leak check")
    session = _seed_classic_page_state()
    before = snapshot_protected_classic_keys(session)

    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id="ds_test_aaa",
    )
    set_pending_navigation(session, "pages/7_Backtest.py")
    set_classic_flash(session, level="success", message="linked")

    assert sync_classic_context_for_dataset(session, "ds_other") is True
    assert not is_research_mode(session)
    assert get_active_thesis_id(session) is None
    assert session["classic_bound_dataset_id"] is None
    assert consume_pending_navigation(session) is None
    assert consume_classic_flash(session) is None
    assert_protected_classic_keys_unchanged(before, session)

    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id="ds_test_aaa",
    )
    exit_research_mode(session)
    assert not is_research_mode(session)
    assert get_recording_policy(session) == "manual"
    assert_protected_classic_keys_unchanged(before, session)


def test_same_dataset_sync_is_noop(tmp_path: Path):
    repo = LocalThesisRepository(tmp_path / "assistant")
    thesis = repo.create_thesis(name="Stable")
    session = _seed_classic_page_state()
    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id="ds_test_aaa",
    )
    assert sync_classic_context_for_dataset(session, "ds_test_aaa") is False
    assert get_active_thesis_id(session) == thesis.thesis_id


def test_unset_bound_adopts_first_dataset_without_clearing(tmp_path: Path):
    """Linking before data loads must not drop research mode on first dataset."""
    repo = LocalThesisRepository(tmp_path / "assistant")
    thesis = repo.create_thesis(name="Pre-data link")
    session = _seed_classic_page_state()
    before = snapshot_protected_classic_keys(session)
    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id=None,
    )
    assert session["classic_bound_dataset_id"] is None
    assert sync_classic_context_for_dataset(session, "ds_test_aaa") is False
    assert is_research_mode(session)
    assert get_active_thesis_id(session) == thesis.thesis_id
    assert session["classic_bound_dataset_id"] == "ds_test_aaa"
    # A later real switch still clears.
    assert sync_classic_context_for_dataset(session, "ds_other") is True
    assert not is_research_mode(session)
    assert_protected_classic_keys_unchanged(before, session)


def test_recording_policy_validation():
    session: dict = {}
    init_classic_session_state(session)
    set_recording_policy(session, "all_executions")
    assert get_recording_policy(session) == "all_executions"
    with pytest.raises(ValueError, match="recording policy"):
        set_recording_policy(session, "auto")
    # Unknown stored value falls back to manual for readers.
    session["classic_recording_policy"] = "bogus"
    assert get_recording_policy(session) == "manual"


def test_flash_and_pending_navigation_helpers():
    session: dict = {}
    set_classic_flash(session, level="info", message=" hello ")
    assert consume_classic_flash(session) == {"level": "info", "message": "hello"}
    assert consume_classic_flash(session) is None
    set_pending_navigation(session, "pages/3_Setup_Builder.py")
    assert consume_pending_navigation(session) == "pages/3_Setup_Builder.py"
    assert consume_pending_navigation(session) is None
    with pytest.raises(ValueError):
        set_classic_flash(session, level="nope", message="x")
    with pytest.raises(ValueError):
        set_pending_navigation(session, "  ")


def test_resolve_pending_navigation_target_allowlist():
    assert resolve_pending_navigation_target("pages/7_Backtest.py") == "pages/7_Backtest.py"
    assert resolve_pending_navigation_target("  pages/6_Signals.py  ") == "pages/6_Signals.py"
    assert resolve_pending_navigation_target("pages/not_a_page.py") is None
    assert resolve_pending_navigation_target("../secrets") is None
    assert resolve_pending_navigation_target(None) is None
    assert "pages/3_Setup_Builder.py" in CLASSIC_PENDING_NAVIGATION_PAGES


def test_clear_preserves_recording_policy():
    session: dict = {}
    init_classic_session_state(session)
    set_recording_policy(session, "all_executions")
    session["classic_active_thesis_id"] = "th_x"
    session["classic_active_thesis_name"] = "X"
    clear_classic_thesis_context(session)
    assert get_recording_policy(session) == "all_executions"
    assert not is_research_mode(session)


def test_clear_and_dataset_switch_reset_relink_flags(tmp_path: Path):
    repo = LocalThesisRepository(tmp_path / "assistant")
    thesis = repo.create_thesis(name="Relink flag")
    session = _seed_classic_page_state()
    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id="ds_test_aaa",
    )
    session["_classic_relink_open_signals"] = True
    session["_classic_relink_open_backtest"] = True
    assert sync_classic_context_for_dataset(session, "ds_other") is True
    assert session["_classic_relink_open_signals"] is False
    assert session["_classic_relink_open_backtest"] is False

    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id="ds_test_aaa",
    )
    session["_classic_relink_open_signals"] = True
    exit_research_mode(session)
    assert session["_classic_relink_open_signals"] is False


def test_pages_wire_classic_chrome_and_setup_allows_create_link():
    root = Path(__file__).resolve().parents[1]
    setup = (root / "pages" / "3_Setup_Builder.py").read_text(encoding="utf-8")
    signals = (root / "pages" / "6_Signals.py").read_text(encoding="utf-8")
    backtest = (root / "pages" / "7_Backtest.py").read_text(encoding="utf-8")
    bundles = (root / "pages" / "12_Research_Bundles.py").read_text(encoding="utf-8")
    for source in (setup, signals, backtest, bundles):
        assert "render_classic_thesis_chrome" in source
        assert "thesistester.classic_context import" in source
        assert "render_classic_thesis_chrome" in source
    assert "allow_create_link=True" in setup
    assert "allow_create_link" not in signals
    assert "allow_create_link" not in backtest
    assert "allow_create_link" not in bundles
    assert "sync_classic_context_for_dataset" in bundles
    assert "st.rerun()" in bundles


def test_bundle_import_syncs_classic_context_after_dataset_change(tmp_path: Path):
    """Import path must re-check bound dataset after session keys are restored."""
    repo = LocalThesisRepository(tmp_path / "assistant")
    thesis = repo.create_thesis(name="Bundle sync")
    session = _seed_classic_page_state()
    link_thesis(
        session,
        thesis_id=thesis.thesis_id,
        thesis_name=thesis.name,
        dataset_id="ds_test_aaa",
    )
    # Simulate post-import session with a different dataset_id (chrome already ran).
    session["dataset_id"] = "ds_imported_bbb"
    assert sync_classic_context_for_dataset(session, session["dataset_id"]) is True
    assert not is_research_mode(session)


def test_link_thesis_source_has_no_run_recording_calls():
    """Static gate: linking helpers must not invoke run/spec persistence APIs."""
    path = Path(__file__).resolve().parents[1] / "thesistester" / "classic_context.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {
        "execute_confirmed_run",
        "start_run",
        "create_spec_version",
        "register_external_bundle_run",
        "run_experiment",
        "build_research_bundle",
        "cancel_run",
        "begin_classic_execution_ledger",
        "complete_classic_execution_ledger",
        "fail_classic_execution_ledger",
        "record_classic_session_run",
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden:
                found.add(func.id)
            elif isinstance(func, ast.Attribute) and func.attr in forbidden:
                found.add(func.attr)
    assert found == set()


def test_protected_key_list_covers_core_producers():
    required = {
        "data",
        "levels",
        "setup_config",
        "signals",
        "trades",
        "dataset_id",
    }
    assert required.issubset(PROTECTED_CLASSIC_SESSION_KEYS)
