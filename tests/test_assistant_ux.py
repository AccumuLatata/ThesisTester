"""RUX-1 UX foundation: mode helpers, nav fragments, settings loader."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from thesistester.assistant.llm import load_assistant_ux_settings
from thesistester.assistant.ux import (
    ADVANCED_COMPARE_NAV_HINT,
    ADVANCED_PLAN_NAV_HINT,
    ADVANCED_PORTFOLIO_NAV_HINT,
    ASSISTANT_MODE_DISCUSS,
    ASSISTANT_MODE_DRAFT,
    ASSISTANT_MODE_HELP,
    ASSISTANT_MODE_SESSION_KEY,
    ASSISTANT_MODES,
    DISCUSS_NAV_HINT,
    DISCUSS_NAV_SHORT,
    DISCUSS_RUN_PICKER_KEY,
    HELP_NAV_HINT,
    default_discuss_run_id,
    discussable_runs,
    reset_ux_mode_and_picker,
    resolve_mode,
    run_picker_label,
)
from thesistester.assistant.workspace import (
    ASSISTANT_SESSION_KEYS,
    THESIS_SCOPED_STAGING_KEYS,
    clear_thesis_scoped_state,
    init_assistant_session_state,
)

TRACKED = Path("config/assistant.toml")


def test_nav_fragments_match_rux0_inventory():
    """Byte-identical to the §1.3 inventory frozen at RUX-0."""
    assert DISCUSS_NAV_HINT == "Advanced → Linked runs → Discuss results"
    assert DISCUSS_NAV_SHORT == "Advanced → Linked runs"
    assert HELP_NAV_HINT == "Help / how it works below"
    assert ADVANCED_PLAN_NAV_HINT == "Advanced → Plan review"
    assert ADVANCED_COMPARE_NAV_HINT == "Advanced → Compare completed runs"
    assert ADVANCED_PORTFOLIO_NAV_HINT == "Advanced → Portfolio analysis"


def test_resolve_mode_never_raises_and_falls_back():
    assert resolve_mode({}, default_mode="discuss") == ASSISTANT_MODE_DISCUSS
    assert resolve_mode({}, default_mode="help") == ASSISTANT_MODE_HELP
    assert resolve_mode({}, default_mode="nope") == ASSISTANT_MODE_DISCUSS
    assert (
        resolve_mode({ASSISTANT_MODE_SESSION_KEY: "draft"}, default_mode="discuss")
        == ASSISTANT_MODE_DRAFT
    )
    assert (
        resolve_mode(
            {ASSISTANT_MODE_SESSION_KEY: "junk"},
            default_mode="help",
            requested="discuss",
        )
        == ASSISTANT_MODE_DISCUSS
    )
    assert resolve_mode({}, default_mode="help", requested="bogus") == ASSISTANT_MODE_HELP
    assert set(ASSISTANT_MODES) == {
        ASSISTANT_MODE_DISCUSS,
        ASSISTANT_MODE_HELP,
        ASSISTANT_MODE_DRAFT,
    }


def test_discussable_runs_frozen_predicate_preserves_order():
    runs = (
        SimpleNamespace(run_id="run_a", status="failed", provenance={}),
        SimpleNamespace(run_id="run_b", status="completed", provenance={"bundle": "x"}),
        SimpleNamespace(run_id="run_c", status="completed", provenance=None),
        SimpleNamespace(run_id="run_d", status="completed", provenance={"h": 1}),
        SimpleNamespace(run_id="run_e", status="running", provenance={}),
    )
    assert discussable_runs(runs, results_qa_enabled=False) == ()
    eligible = discussable_runs(runs, results_qa_enabled=True)
    assert [run.run_id for run in eligible] == ["run_b", "run_d"]


def test_default_discuss_run_id_prefers_focus_then_newest():
    runs = (
        SimpleNamespace(run_id="run_old", status="completed", provenance={}),
        SimpleNamespace(run_id="run_new", status="completed", provenance={}),
    )
    eligible = discussable_runs(runs, results_qa_enabled=True)
    assert default_discuss_run_id(eligible, focused_run_id=None) == "run_new"
    assert default_discuss_run_id(eligible, focused_run_id="run_old") == "run_old"
    assert default_discuss_run_id(eligible, focused_run_id="run_missing") == "run_new"
    assert default_discuss_run_id((), focused_run_id="run_old") is None


def test_run_picker_label_mirrors_expander_kind_formatting():
    from thesistester.classic_ledger import ledger_run_label

    cases = (
        SimpleNamespace(
            run_id="run_abcdefghijklmnop",
            status="completed",
            request={"action": "classic_execution_ledger", "origin_page": "7_Backtest"},
            provenance={"execution_origin": "classic"},
        ),
        SimpleNamespace(
            run_id="run_12345678xxxxxxxx",
            status="completed",
            request={"action": "register_external_bundle"},
            provenance={"execution_origin": "classic"},
        ),
        SimpleNamespace(
            run_id="run_aaaaaaaa",
            status="completed",
            request={},
            provenance={"execution_origin": "assistant"},
        ),
        # Non-classic/non-assistant origins must use action (ledger_run_label),
        # not execution_origin — otherwise Discuss picker drifts from expanders.
        SimpleNamespace(
            run_id="run_bbbbbbbb",
            status="completed",
            request={"action": "run_backtest"},
            provenance={"execution_origin": "api"},
        ),
        SimpleNamespace(
            run_id="run_cccccccc",
            status="completed",
            request={"action": "run_grid"},
            provenance={"execution_origin": "cli"},
        ),
        SimpleNamespace(
            run_id="run_dddddddd",
            status="completed",
            request={"action": "run_walk_forward"},
            provenance={"execution_origin": "unknown"},
        ),
    )
    for run in cases:
        kind = ledger_run_label(run)
        expected = f"Run {run.run_id[-8:]} · {run.status} · {kind}"
        assert run_picker_label(run) == expected


def test_tracked_config_loads_ux_default_mode():
    settings = load_assistant_ux_settings(TRACKED)
    assert settings.default_mode == "discuss"


def test_ux_settings_missing_section_and_unknown_mode(tmp_path):
    missing = tmp_path / "missing.toml"
    missing.write_text(
        "[assistant]\nprovider = 'openai'\nmodel = 'gpt-test'\n",
        encoding="utf-8",
    )
    assert load_assistant_ux_settings(missing).default_mode == "discuss"

    unknown = tmp_path / "unknown.toml"
    unknown.write_text(
        "[assistant]\n"
        "provider = 'openai'\n"
        "model = 'gpt-test'\n"
        "\n"
        "[assistant.ux]\n"
        "default_mode = 'nope'\n",
        encoding="utf-8",
    )
    assert load_assistant_ux_settings(unknown).default_mode == "discuss"

    valid = tmp_path / "valid.toml"
    valid.write_text(
        "[assistant]\n"
        "provider = 'openai'\n"
        "model = 'gpt-test'\n"
        "\n"
        "[assistant.ux]\n"
        "default_mode = 'help'\n",
        encoding="utf-8",
    )
    assert load_assistant_ux_settings(valid).default_mode == "help"


def test_session_keys_registered_and_clear_resets_ux_defaults():
    assert "assistant_ux_mode" in ASSISTANT_SESSION_KEYS
    assert "assistant_discuss_run_picker" in ASSISTANT_SESSION_KEYS
    assert "assistant_ux_mode" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_discuss_run_picker" in THESIS_SCOPED_STAGING_KEYS

    state: dict = {
        ASSISTANT_MODE_SESSION_KEY: ASSISTANT_MODE_DRAFT,
        DISCUSS_RUN_PICKER_KEY: "run_stale",
        "assistant_draft_prompt": "keep-clearing",
    }
    init_assistant_session_state(state)
    # init uses setdefault — existing draft mode stays until clear.
    assert state[ASSISTANT_MODE_SESSION_KEY] == ASSISTANT_MODE_DRAFT
    clear_thesis_scoped_state(state)
    assert state[ASSISTANT_MODE_SESSION_KEY] == load_assistant_ux_settings().default_mode
    assert state[DISCUSS_RUN_PICKER_KEY] is None
    assert state["assistant_draft_prompt"] == ""


def test_reset_ux_mode_and_picker_pops_then_rewrites():
    state = {
        ASSISTANT_MODE_SESSION_KEY: "help",
        DISCUSS_RUN_PICKER_KEY: "run_x",
        "other": 1,
    }
    reset_ux_mode_and_picker(state, default_mode="draft")
    assert state[ASSISTANT_MODE_SESSION_KEY] == "draft"
    assert state[DISCUSS_RUN_PICKER_KEY] is None
    assert state["other"] == 1
    reset_ux_mode_and_picker(state, default_mode="bogus")
    assert state[ASSISTANT_MODE_SESSION_KEY] == ASSISTANT_MODE_DISCUSS
