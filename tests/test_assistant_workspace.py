"""Workspace façade and Research Assistant presentation-helper tests (C2-4)."""

from __future__ import annotations

import pathlib
import sys
import types
from pathlib import Path

import pytest

from thesistester.assistant import (
    ASSISTANT_SESSION_KEYS,
    THESIS_SCOPED_STAGING_KEYS,
    AssistantOrchestrator,
    LocalThesisRepository,
    build_plan_review,
    clear_thesis_scoped_state,
    init_assistant_session_state,
    select_thesis,
)
from thesistester.assistant.tools import AssistantTools
from thesistester.assistant.workspace import (
    ASSISTANT_ADVANCED_EXPANDER_KEY,
    apply_consumed_classic_focus,
    build_provenance_card,
    force_results_qa_expanders_open,
    linked_run_expander_key,
    merge_execution_controls,
    merge_grid_controls,
    merge_level_controls,
    merge_setup_controls,
    merge_validation_controls,
    merge_walk_forward_controls,
    parse_json_choices,
    parse_positive_number_list,
)
from thesistester.research_bundle import canonical_bundle_hash


def _make_streamlit_stub() -> types.ModuleType:
    st = types.ModuleType("streamlit")

    def _noop(*args, **kwargs):
        return None

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    for name in (
        "title",
        "caption",
        "subheader",
        "warning",
        "info",
        "error",
        "success",
        "markdown",
        "stop",
        "rerun",
        "button",
        "checkbox",
        "toggle",
        "radio",
        "selectbox",
        "multiselect",
        "number_input",
        "slider",
        "text_input",
        "text_area",
        "columns",
        "write",
        "json",
        "page_link",
        "download_button",
        "chat_input",
        "chat_message",
        "form_submit_button",
        "audio_input",
        "audio",
    ):
        setattr(st, name, _noop)
    st.expander = lambda *args, **kwargs: _Ctx()
    st.form = lambda *args, **kwargs: _Ctx()
    st.sidebar = _Ctx()
    st.session_state = {}
    return st


def _load_research_assistant_page():
    stub = _make_streamlit_stub()
    sys.modules["streamlit"] = stub
    page_path = pathlib.Path(__file__).parent.parent / "pages" / "14_Research_Assistant.py"
    source = page_path.read_text(encoding="utf-8")
    # Avoid executing the full Streamlit page body; import helpers via AST-free
    # source contract checks instead.
    return source


def test_page_is_orchestrator_only_and_keeps_json_advanced():
    source = _load_research_assistant_page()
    assert "LocalThesisRepository(" not in source
    assert "AssistantTools(" not in source
    assert "Path.read_bytes" not in source
    assert "compile_thesis(" not in source
    assert "map_thesis_choices_to_run_spec(" not in source
    assert "explain_evidence(" not in source
    assert "compare_evidence(" not in source
    assert "apply_research_bundle_to_session(" not in source
    assert "for_local_workspace(" in source
    assert "Advanced: edit complete research choices as JSON" in source
    assert "Apply JSON audit edits" in source
    assert "Restore bundle into research pages" in source
    assert "Plan review" in source
    assert "Build research artifact" in source
    assert "active_bundle_handoff(" in source
    assert "latest_unresolved_assumptions(" in source
    assert 'or "allow_all"' in source
    assert "assistant_bundle_handoff" in THESIS_SCOPED_STAGING_KEYS
    assert "dict(spec.normalized_run_spec)" in source
    assert "safe_int(" in source
    assert "safe_float(" in source
    assert 'plan["ready_for_confirmation"]' in source
    assert "WFA matrix is available only for session fold mode." in source
    assert "set_assistant_flash(" in source
    assert "consume_assistant_flash(" in source
    assert "How to start a research run" in source
    assert "format_spec_status(" in source
    assert "spec_status_next_step(" in source
    assert "plan['next_action']" in source or 'plan["next_action"]' in source
    assert "_apply_draft_and_rerun(" in source
    assert "build_confluence_level_options(" in source
    assert "TIMEZONE_OPTIONS" in source
    assert '"Confluence levels"' in source
    assert "st.multiselect(" in source
    assert "VWAP_WINDOW_OPTIONS" in source
    assert "available_level_columns(" in source
    restore_idx = source.index("Restore bundle into research pages")
    # CAI-8 adds Open-exact controls beside restore; keep a durable window for
    # the restore path's post-success st.rerun().
    assert "st.rerun()" in source[restore_idx : restore_idx + 1200]
    assert "restore_run_bundle_to_session(" in source[restore_idx : restore_idx + 1200]


def test_assistant_session_keys_cover_documented_staging_surface():
    assert "assistant_selected_thesis_id" in ASSISTANT_SESSION_KEYS
    assert "assistant_validated_run_spec" in ASSISTANT_SESSION_KEYS
    assert "assistant_llm_run_explanations" in ASSISTANT_SESSION_KEYS
    assert "assistant_bundle_handoff" in ASSISTANT_SESSION_KEYS
    assert "assistant_flash" in ASSISTANT_SESSION_KEYS
    assert "assistant_run_comparisons" in ASSISTANT_SESSION_KEYS
    assert "assistant_portfolio_analyses" in ASSISTANT_SESSION_KEYS
    assert "assistant_results_qa_drafts" not in ASSISTANT_SESSION_KEYS
    assert "assistant_product_help_draft" not in ASSISTANT_SESSION_KEYS
    assert "assistant_voice_results_sessions" in ASSISTANT_SESSION_KEYS
    assert "assistant_voice_help_session_id" in ASSISTANT_SESSION_KEYS
    assert "assistant_voice_last_turn" in ASSISTANT_SESSION_KEYS
    assert "assistant_voice_playback" in ASSISTANT_SESSION_KEYS
    assert "assistant_ux_mode" in ASSISTANT_SESSION_KEYS
    assert "assistant_discuss_run_picker" in ASSISTANT_SESSION_KEYS
    assert "assistant_bundle_handoff" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_flash" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_results_qa_drafts" not in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_product_help_draft" not in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_focused_run_id" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_results_qa_deep_link" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_results_qa_force_expand" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_voice_results_sessions" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_voice_help_session_id" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_voice_last_turn" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_voice_playback" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_ux_mode" in THESIS_SCOPED_STAGING_KEYS
    assert "assistant_discuss_run_picker" in THESIS_SCOPED_STAGING_KEYS
    assert set(THESIS_SCOPED_STAGING_KEYS).issubset(ASSISTANT_SESSION_KEYS)


def test_failed_llm_regen_clears_stale_explanation_cache():
    from thesistester.assistant.workspace import clear_failed_llm_run_explanation

    state = {}
    init_assistant_session_state(state)
    state["assistant_llm_run_explanations"]["run_a"] = object()
    state["assistant_llm_run_explanations"]["run_b"] = object()
    state["assistant_llm_attempts"]["run_a"] = 2
    state["assistant_llm_attempts"]["run_b"] = 1
    clear_failed_llm_run_explanation(state, "run_a")
    assert "run_a" not in state["assistant_llm_run_explanations"]
    assert "run_a" not in state["assistant_llm_attempts"]
    assert "run_b" in state["assistant_llm_run_explanations"]
    assert state["assistant_llm_attempts"]["run_b"] == 1
    page_path = pathlib.Path(__file__).parent.parent / "pages" / "14_Research_Assistant.py"
    source = page_path.read_text(encoding="utf-8")
    assert "clear_failed_llm_run_explanation(" in source


def test_thesis_switch_clears_draft_validation_and_hydration():
    state = {}
    init_assistant_session_state(state)
    state["assistant_selected_thesis_id"] = "th_a"
    state["assistant_draft_prompt"] = "old prompt"
    state["assistant_draft_choices"] = {"dataset": {"path": "a.csv"}}
    state["assistant_validated_run_spec"] = {"spec": {"name": "x"}}
    state["assistant_hydrated_conversation_id"] = "conv_old"
    state["assistant_bundle_handoff"] = {
        "thesis_id": "th_a",
        "run_id": "run_old",
        "restored_count": 3,
    }
    state["assistant_flash"] = {"level": "success", "message": "stale"}
    state["assistant_run_comparisons"] = {"th_a": {"run_ids": ["r1", "r2"]}}
    state["assistant_portfolio_analyses"] = {
        "th_a": {"run_ids": ["r1", "r2"], "instrument": "ES", "payload": {}}
    }

    changed = select_thesis(state, "th_b")
    assert changed is True
    assert state["assistant_selected_thesis_id"] == "th_b"
    assert state["assistant_draft_prompt"] == ""
    assert state["assistant_draft_choices"] == {}
    assert state["assistant_validated_run_spec"] is None
    assert state["assistant_hydrated_conversation_id"] is None
    assert state["assistant_bundle_handoff"] is None
    assert state["assistant_flash"] is None
    # Persisted comparison/portfolio caches are thesis-keyed and retained.
    assert state["assistant_run_comparisons"]["th_a"]["run_ids"] == ["r1", "r2"]
    assert state["assistant_portfolio_analyses"]["th_a"]["instrument"] == "ES"
    assert select_thesis(state, "th_b") is False


def test_active_bundle_handoff_requires_matching_thesis():
    from thesistester.assistant.workspace import active_bundle_handoff

    state = {
        "assistant_bundle_handoff": {
            "thesis_id": "th_a",
            "run_id": "run_1",
            "restored_count": 2,
        }
    }
    assert active_bundle_handoff(state, thesis_id="th_a")["run_id"] == "run_1"
    assert active_bundle_handoff(state, thesis_id="th_b") is None
    assert active_bundle_handoff({}, thesis_id="th_a") is None


def test_structured_merges_cover_setup_levels_execution_grid_validation_wfa():
    choices = {}
    choices = merge_execution_controls(
        choices,
        dataset_path="bars.csv",
        instrument="ES",
        source_timezone="America/New_York",
        subtimeframe_path="",
        stop_loss_ticks=8,
        take_profit_ticks=16,
        commission_per_side=0.0,
        slippage_ticks=0.0,
        exposure_policy="single_position",
        intrabar_model="sl_first",
        flat_by_session_close=True,
        session_close_time="16:00",
        session_timezone="America/New_York",
        no_new_entries_after="15:45",
        max_holding_bars=None,
        allow_same_bar_exit=True,
        cooldown_bars_after_exit=0,
    )
    choices = merge_setup_controls(
        choices,
        setup_name="Touch",
        description="dVWAP touch",
        selected_levels_raw=["dVWAP_RTH", "SMA_50_30min"],
        trigger="touch",
        direction="both",
        tolerance_ticks=0.0,
        min_confluences=2,
        max_confluences=2,
        naked_only=False,
        naked_requirement="any",
        trigger_timeframe="base",
        confluence_mode="global_cluster",
        anchor_level="",
        min_valid_confluences=1,
    )
    choices = merge_level_controls(
        choices,
        session_vwap_enabled=True,
        opening_range_minutes=30,
        sma_lengths_raw=[50, 200],
        sma_timeframes=["30min"],
        ema_lengths_raw=[20],
        ema_timeframes=["5min"],
        vwap_windows_raw=["30min", "4h"],
        poc_windows_raw=["30min"],
    )
    choices = merge_validation_controls(
        choices,
        n_bootstrap=100,
        n_permutations=100,
        random_state=7,
        monte_carlo_enabled=True,
        monte_carlo_simulations=25,
        excursion_enabled=True,
        overfitting_enabled=False,
        noise_enabled=False,
        sensitivity_enabled=False,
        min_trades_soft=20,
        min_trades_hard=5,
    )
    choices = merge_grid_controls(
        choices,
        enabled=True,
        stop_values_raw="4,8",
        target_values_raw="8,16",
        ranking_metric="expectancy_r",
        min_trades=10,
        max_grid_cells=50,
    )
    choices = merge_walk_forward_controls(
        choices,
        enabled=True,
        fold_mode="bars",
        window_mode="rolling",
        overlap_policy="reject",
        train_size=100,
        test_size=20,
        step_size=20,
        ranking_metric="expectancy_r",
        min_train_trades=5,
        stop_values_raw="8",
        target_values_raw="16",
        matrix_enabled=True,
        matrix_train_raw="20,40",
        matrix_test_raw="5",
        matrix_metric="median_test_expectancy_r",
        max_matrix_cells=20,
    )

    assert choices["setup"]["selected_levels"] == ["dVWAP_RTH", "SMA_50_30min"]
    assert choices["levels"]["ema_lengths"] == [20]
    assert choices["levels"]["vwap_windows"] == ["30min", "4h"]
    assert choices["levels"]["poc_windows"] == ["30min"]
    assert choices["validation"]["monte_carlo"]["enabled"] is True
    assert choices["grid"]["max_grid_cells"] == 50
    assert choices["walk_forward"]["fold_mode"] == "bars"
    assert choices["walk_forward"]["train_bars"] == 100
    # Bars fold mode cannot enable the session-scoped WFA matrix.
    assert choices["walk_forward"]["matrix"]["enabled"] is False
    sessions = merge_walk_forward_controls(
        choices,
        enabled=True,
        fold_mode="sessions",
        window_mode="rolling",
        overlap_policy="reject",
        train_size=20,
        test_size=5,
        step_size=5,
        ranking_metric="expectancy_r",
        min_train_trades=5,
        stop_values_raw="8",
        target_values_raw="16",
        matrix_enabled=True,
        matrix_train_raw="20,40",
        matrix_test_raw="5",
        matrix_metric="median_test_expectancy_r",
        max_matrix_cells=20,
    )
    assert sessions["walk_forward"]["matrix"]["enabled"] is True
    assert sessions["walk_forward"]["matrix"]["train_session_values"] == [20, 40]
    assert parse_positive_number_list("1, 2.5") == [1.0, 2.5]
    assert parse_json_choices('{"dataset": {"path": "x.csv"}}')["dataset"]["path"] == "x.csv"


def test_chat_message_helpers_surface_clarifications_and_hide_tool_noise():
    from thesistester.assistant.workspace import (
        chat_message_display_role,
        format_assistant_draft_reply,
        format_chat_message_body,
    )

    with_questions = format_assistant_draft_reply(
        ("Select a dataset and instrument.", "Define setup levels.")
    )
    assert "clarifications before this thesis draft can run" in with_questions
    assert "- Select a dataset and instrument." in with_questions
    assert format_assistant_draft_reply(()).startswith("Drafted non-executing")

    legacy = {
        "role": "assistant",
        "content": "Drafted non-executing research choices.",
        "clarifications": ["What test would you like explained?"],
    }
    body = format_chat_message_body(legacy)
    assert "Drafted non-executing research choices." in body
    assert "What test would you like explained?" in body
    assert chat_message_display_role(legacy) == "assistant"
    assert chat_message_display_role({"role": "user", "content": "hi"}) == "user"
    assert (
        chat_message_display_role({"role": "tool", "content": "completed BUNDLE.import."}) is None
    )
    assert (
        chat_message_display_role(
            {
                "role": "assistant",
                "content": "results reply",
                "channel": "results_qa",
                "run_id": "run_x",
            }
        )
        is None
    )

    # A short clarification that is a substring of the opaque status line must
    # not suppress merging the remaining structured questions into chat.
    overlapping = {
        "role": "assistant",
        "content": "Drafted non-executing research choices.",
        "clarifications": [
            "research choices",
            "What instrument and dataset should this thesis use?",
        ],
    }
    overlapping_body = format_chat_message_body(overlapping)
    assert "- research choices" in overlapping_body
    assert "- What instrument and dataset should this thesis use?" in overlapping_body
    assert "Clarifications still needed:" in overlapping_body

    # New turns already embed every clarification in content — do not duplicate.
    embedded = format_assistant_draft_reply(
        ("Select a dataset and instrument.", "Define setup levels.")
    )
    assert (
        format_chat_message_body(
            {
                "role": "assistant",
                "content": embedded,
                "clarifications": [
                    "Select a dataset and instrument.",
                    "Define setup levels.",
                ],
            }
        )
        == embedded
    )

    page_path = pathlib.Path(__file__).parent.parent / "pages" / "14_Research_Assistant.py"
    source = page_path.read_text(encoding="utf-8")
    assert "format_chat_message_body(" in source
    assert "chat_message_display_role(" in source
    assert "Thesis drafting only" in source
    assert "Discuss results" in source
    assert "handle_results_turn(" in source
    assert "Help / how it works" in source
    assert "handle_help_turn(" in source
    assert "repo_root=Path(__file__).resolve().parents[1]" in source
    assert "load_product_help_settings(" in source
    assert "chat_input_placeholder(" in source
    assert "chat_input_key(" in source
    assert "st.chat_input(" in source
    assert source.count("st.chat_input(") == 1
    assert "Send help question" not in source
    assert "Send results question" not in source
    assert "assistant_product_help_draft" not in source
    assert "product-help-input" not in source
    assert "assistant_clear_product_help_input" not in source
    assert "results-qa-input-" not in source
    assert "is_draft_channel_message(" in source
    assert "load_results_qa_settings(" in source
    assert "st.text_input(" in source  # Advanced structured controls still use text_input
    # RUX-1: nav fragments live in assistant.ux; page imports the constants.
    assert "DISCUSS_NAV_HINT" in source
    assert "DISCUSS_NAV_SHORT" in source
    assert "from thesistester.assistant.ux import" in source
    from thesistester.assistant.ux import DISCUSS_NAV_SHORT

    assert DISCUSS_NAV_SHORT == "Discuss runs"
    assert "st.segmented_control(" in source
    assert "ASSISTANT_MODE_DISCUSS" in source
    assert 'st.expander("Help / how it works"' not in source
    assert 'st.subheader("Help / how it works")' in source
    # Movement map: Discuss/Explain before Advanced; LLM explain stays in Advanced.
    discuss_mode_pos = source.index("if mode == ASSISTANT_MODE_DISCUSS:")
    help_mode_pos = source.index("elif mode == ASSISTANT_MODE_HELP:")
    draft_mode_pos = source.index("elif mode == ASSISTANT_MODE_DRAFT:")
    chat_input_pos = source.index("st.chat_input(")
    advanced_pos = source.index('with st.expander(\n    "Advanced: draft, runs & compare"')
    explain_pos = source.index('st.button("Explain run"')
    llm_explain_pos = source.index("Generate evidence-only AI explanation")
    assert discuss_mode_pos < help_mode_pos < draft_mode_pos < chat_input_pos < advanced_pos
    assert discuss_mode_pos < explain_pos < advanced_pos < llm_explain_pos
    assert source.count('key=f"explain-{run.run_id}"') == 1
    assert source.count('key=f"llm-explain-{run.run_id}"') == 1
    assert "Raw transcripts and JSON for audit only" in source
    assert "Open research pages" not in source
    assert "st.page_link(" not in source
    assert "expanded=expand_results_qa_focus" in source
    assert "apply_consumed_classic_focus(" in source
    assert "force_results_qa_expanders_open(" in source
    assert "apply_discuss_mode_deep_link(" in source
    assert "ASSISTANT_ADVANCED_EXPANDER_KEY" in source
    assert "linked_run_expander_key(" in source
    assert 'with st.expander("Debug: raw JSON & conversation audit", expanded=False)' in source
    assert 'with st.expander("Structured execution controls", expanded=False)' in source
    assert 'with st.expander("Structured setup and confluence controls", expanded=False)' in source
    assert 'with st.expander("Validated executable RunSpec", expanded=False)' in source
    assert "Debug: provenance" in source
    assert "Debug: specification JSON" in source
    assert "Page summaries (JSON)" in source
    assert "Linked research runs" in source
    # Compare/portfolio success feedback must stay visible (not Debug-only).
    assert 'st.success("Comparison ready.")' in source
    assert "Portfolio analysis ready for" in source
    assert 'with st.expander("Debug: comparison JSON", expanded=False)' in source
    assert 'with st.expander("Debug: portfolio JSON", expanded=False)' in source
    assert "assistant_portfolio_analyses" in source
    success_pos = source.index('st.success("Comparison ready.")')
    debug_compare_pos = source.index('with st.expander("Debug: comparison JSON", expanded=False)')
    assert success_pos < debug_compare_pos
    # Validate/Cancel/Draft-error/Compare/Portfolio must hub-flash so discuss-first
    # reruns (Advanced defaults closed) do not hide outcomes.
    validate_idx = source.index('if st.button("Validate executable RunSpec")')
    validate_chunk = source[validate_idx : validate_idx + 2200]
    assert "set_assistant_flash(" in validate_chunk
    assert "st.rerun()" in validate_chunk
    assert "Executable RunSpec is valid." in validate_chunk
    cancel_idx = source.index('st.button("Cancel run"')
    cancel_chunk = source[cancel_idx : cancel_idx + 1200]
    assert "set_assistant_flash(" in cancel_chunk
    assert 'message="Research run cancelled."' in cancel_chunk
    assert "st.rerun()" in cancel_chunk
    draft_idx = source.index('if st.button("Draft research plan", type="primary")')
    draft_chunk = source[draft_idx : draft_idx + 1600]
    assert "except ValueError as exc:" in draft_chunk
    draft_error = draft_chunk[draft_chunk.index("except ValueError") :]
    assert "set_assistant_flash(" in draft_error
    assert "st.rerun()" in draft_error
    compare_idx = source.index('if st.button("Compare runs")')
    compare_chunk = source[compare_idx : compare_idx + 2200]
    assert "set_assistant_flash(" in compare_chunk
    assert "st.rerun()" in compare_chunk
    assert 'st.error(result.payload.get("error"' not in compare_chunk
    assert 'assistant_run_comparisons"].pop(thesis_id, None)' in compare_chunk
    assert 'cached.get("run_ids") == [left_id, right_id]' in compare_chunk
    portfolio_idx = source.index('if st.button("Analyze portfolio")')
    portfolio_chunk = source[portfolio_idx : portfolio_idx + 3200]
    assert "set_assistant_flash(" in portfolio_chunk
    assert "assistant_portfolio_analyses" in portfolio_chunk
    assert "st.rerun()" in portfolio_chunk
    assert 'assistant_portfolio_analyses"].pop(thesis_id, None)' in portfolio_chunk
    assert 'cached.get("run_ids") == list(portfolio_ids)' in portfolio_chunk
    assert "portfolio_state =" in source[portfolio_idx:]
    # Hot JSON surfaces must not open by default on the hub.
    assert 'with st.expander("Structured execution controls", expanded=True)' not in source
    assert 'with st.expander("Validated executable RunSpec", expanded=True)' not in source


def test_plan_review_ready_flag_requires_validated_spec():
    plan = build_plan_review(
        thesis_name="Demo",
        choices={"dataset": {"path": "bars.csv", "instrument": "ES"}},
        validated_spec=None,
        unresolved_assumptions=("Define costs.",),
    )
    assert plan["ready_for_confirmation"] is False
    assert plan["unresolved_assumptions"] == ["Define costs."]
    assert "Resolve clarifications" in plan["next_action"]

    blocked = build_plan_review(
        thesis_name="Demo",
        choices={"dataset": {"path": "bars.csv", "instrument": "ES"}},
        validated_spec={"name": "Demo", "setup": {}},
        unresolved_assumptions=("Define costs.",),
    )
    assert blocked["validated_spec"] is not None
    assert blocked["ready_for_confirmation"] is False

    needs_validate = build_plan_review(
        thesis_name="Demo",
        choices={"dataset": {"path": "bars.csv", "instrument": "ES"}},
        validated_spec=None,
        unresolved_assumptions=(),
    )
    assert needs_validate["ready_for_confirmation"] is False
    assert "Validate executable RunSpec" in needs_validate["next_action"]

    ready = build_plan_review(
        thesis_name="Demo",
        choices={"dataset": {"path": "bars.csv", "instrument": "ES"}},
        validated_spec={"name": "Demo", "setup": {}},
        unresolved_assumptions=(),
    )
    assert ready["ready_for_confirmation"] is True
    assert "Confirm validated RunSpec" in ready["next_action"]


def test_assistant_flash_survives_until_consumed():
    from thesistester.assistant.workspace import (
        consume_assistant_flash,
        set_assistant_flash,
    )

    state = {}
    init_assistant_session_state(state)
    set_assistant_flash(state, level="success", message="Execution controls applied.")
    assert state["assistant_flash"]["level"] == "success"
    flash = consume_assistant_flash(state)
    assert flash == {"level": "success", "message": "Execution controls applied."}
    assert consume_assistant_flash(state) is None


def test_spec_status_labels_and_next_steps_are_explicit():
    from thesistester.assistant.workspace import (
        RESEARCH_WORKFLOW_STEPS,
        format_spec_status,
        spec_status_next_step,
    )

    assert format_spec_status("ready_for_confirmation") == "Ready to confirm"
    assert format_spec_status("confirmed") == "Confirmed — can run"
    assert "Plan review" in spec_status_next_step("ready_for_confirmation")
    assert "Run confirmed research" in spec_status_next_step("confirmed")
    assert any("Apply structured controls" in step for step in RESEARCH_WORKFLOW_STEPS)


def test_confluence_and_timezone_catalogs_support_searchable_widgets():
    from thesistester.assistant.workspace import (
        POC_WINDOW_OPTIONS,
        TIMEZONE_OPTIONS,
        VWAP_WINDOW_OPTIONS,
        build_confluence_level_options,
        coerce_multiselect_defaults,
        coerce_window_label,
        merge_level_controls,
        option_index,
        options_with_current,
        options_with_currents,
    )

    assert "America/New_York" in TIMEZONE_OPTIONS
    assert "30min" in VWAP_WINDOW_OPTIONS
    options = build_confluence_level_options(
        selected_levels=["Custom_Level_X"],
        levels_settings={
            "sma_lengths": [50],
            "sma_timeframes": ["30min"],
            "vwap_windows": ["1h"],
        },
        available_columns=["Live_From_Levels"],
    )
    assert "dVWAP_RTH" in options
    assert "dVWAP" in options
    assert "SMA_50_30min" in options
    assert "VWAP_rolling_1h" in options
    assert "Live_From_Levels" in options
    assert "Custom_Level_X" in options
    assert coerce_multiselect_defaults(["dVWAP_RTH", "missing"], options) == ["dVWAP_RTH"]
    assert option_index((5, 15, 30), 30) == 2
    assert option_index((5, 15, 30), "15") == 1
    # Explicit empty windows/lengths must not expand into the full catalogs.
    # (Static SUGGESTED_DEFAULT_LEVELS may still include VWAP_rolling_1h.)
    cleared = build_confluence_level_options(
        selected_levels=["dVWAP_RTH"],
        levels_settings={
            "sma_lengths": [],
            "ema_lengths": [],
            "vwap_windows": [],
            "poc_windows": [],
        },
    )
    assert "dVWAP_RTH" in cleared
    assert "VWAP_rolling_15min" not in cleared
    assert "VWAP_rolling_30min" not in cleared
    assert "VWAP_rolling_4h" not in cleared
    assert "POC_rolling_30min" not in cleared
    assert not any(name.startswith("SMA_") for name in cleared)
    assert not any(name.startswith("EMA_") for name in cleared)
    # Draft values outside fixed catalogs must remain selectable.
    tz_options = options_with_current(TIMEZONE_OPTIONS, "America/Los_Angeles")
    assert "America/Los_Angeles" in tz_options
    assert option_index(tz_options, "America/Los_Angeles") == tz_options.index(
        "America/Los_Angeles"
    )
    or_options = options_with_current((5, 15, 30), 20)
    assert 20 in or_options
    assert option_index(or_options, 20) == or_options.index(20)
    # Draft VWAP/POC windows outside the fixed catalogs must remain selectable.
    vwap_options = options_with_currents(VWAP_WINDOW_OPTIONS, ["2h", "30min"])
    assert "2h" in vwap_options
    assert coerce_multiselect_defaults(["2h", "30min"], vwap_options) == ["2h", "30min"]
    poc_options = options_with_currents(POC_WINDOW_OPTIONS, ["90min"])
    assert "90min" in poc_options
    # Legacy numeric minute drafts must coerce to Levels labels, not "30".
    assert coerce_window_label(30) == "30min"
    assert coerce_window_label("30") == "30min"
    assert coerce_window_label(60) == "1h"
    assert coerce_window_label("30min") == "30min"
    legacy = merge_level_controls(
        {},
        session_vwap_enabled=True,
        opening_range_minutes=30,
        sma_lengths_raw=[50],
        sma_timeframes=["30min"],
        ema_lengths_raw=[],
        ema_timeframes=[],
        vwap_windows_raw=[30, 60],
        poc_windows_raw=["30"],
    )
    assert legacy["levels"]["vwap_windows"] == ["30min", "1h"]
    assert legacy["levels"]["poc_windows"] == ["30min"]
    legacy_confluence = build_confluence_level_options(
        levels_settings={"vwap_windows": [30], "sma_lengths": [], "ema_lengths": []}
    )
    assert "VWAP_rolling_30min" in legacy_confluence
    assert "VWAP_rolling_30" not in legacy_confluence
    page_path = pathlib.Path(__file__).parent.parent / "pages" / "14_Research_Assistant.py"
    source = page_path.read_text(encoding="utf-8")
    assert "options_with_current(" in source
    assert "options_with_currents(" in source
    assert "coerce_window_label(" in source
    assert "vwap_window_options" in source
    assert "poc_window_options" in source


def test_latest_unresolved_assumptions_only_from_newest_spec():
    from types import SimpleNamespace

    from thesistester.assistant.workspace import latest_unresolved_assumptions

    stale_after_ready = (
        SimpleNamespace(version=1, status="needs_clarification", unresolved_assumptions=("old",)),
        SimpleNamespace(version=2, status="ready_for_confirmation", unresolved_assumptions=()),
    )
    assert latest_unresolved_assumptions(stale_after_ready) == ()

    newest_needs_help = (
        SimpleNamespace(version=1, status="ready_for_confirmation", unresolved_assumptions=()),
        SimpleNamespace(version=3, status="needs_clarification", unresolved_assumptions=("new",)),
        SimpleNamespace(version=2, status="needs_clarification", unresolved_assumptions=("mid",)),
    )
    assert latest_unresolved_assumptions(newest_needs_help) == ("new",)


def test_option_index_defaults_exposure_policy_to_allow_all():
    from thesistester.assistant.workspace import EXPOSURE_POLICIES, option_index

    assert EXPOSURE_POLICIES[0] == "allow_all"
    assert option_index(EXPOSURE_POLICIES, None) == 0
    assert option_index(EXPOSURE_POLICIES, "missing") == 0
    assert option_index(EXPOSURE_POLICIES, "single_position") == 1


def test_safe_numeric_defaults_tolerate_malformed_draft_values():
    from thesistester.assistant.workspace import safe_float, safe_int

    assert safe_int("8", 1) == 8
    assert safe_int("nope", 8) == 8
    assert safe_int(None, 8) == 8
    assert safe_int(True, 8) == 8
    assert safe_float("1.5", 0.0) == 1.5
    assert safe_float("bad", 0.25) == 0.25
    assert safe_float(None, 0.0) == 0.0


def test_orchestrator_facade_draft_validate_confirm_is_idempotent(tmp_path):
    repository = LocalThesisRepository(tmp_path / "assistant")
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    thesis = orchestrator.create_thesis(name="Workspace")
    conversation = orchestrator.ensure_conversation(thesis.thesis_id)
    choices = merge_execution_controls(
        {},
        dataset_path=str(tmp_path / "bars.csv"),
        instrument="ES",
        source_timezone="America/New_York",
        subtimeframe_path="",
        stop_loss_ticks=2,
        take_profit_ticks=3,
        commission_per_side=0.0,
        slippage_ticks=0.0,
        exposure_policy="single_position",
        intrabar_model="sl_first",
        flat_by_session_close=False,
        session_close_time="",
        session_timezone="",
        no_new_entries_after="",
        max_holding_bars=None,
        allow_same_bar_exit=True,
        cooldown_bars_after_exit=0,
    )
    choices = merge_setup_controls(
        choices,
        setup_name="Workspace",
        description="",
        selected_levels_raw="dOpen, RTH_Open",
        trigger="touch",
        direction="both",
        tolerance_ticks=0.0,
        min_confluences=2,
        max_confluences=2,
        naked_only=False,
        naked_requirement="any",
        trigger_timeframe="base",
        confluence_mode="global_cluster",
        anchor_level="",
        min_valid_confluences=1,
    )
    choices = merge_level_controls(
        choices,
        session_vwap_enabled=False,
        opening_range_minutes=30,
        sma_lengths_raw="2",
        sma_timeframes=["1min"],
        ema_lengths_raw="2",
        ema_timeframes=["1min"],
        vwap_windows_raw="",
        poc_windows_raw="",
    )

    dirty_choices = {**choices, "legacy_narrative_hint": "should be stripped by draft"}
    draft = orchestrator.draft_specification(
        thesis_id=thesis.thesis_id,
        prompt="Touch dOpen with RTH open confluence.",
        choices=dirty_choices,
    )
    assert draft.status in {"ready_for_confirmation", "needs_clarification"}
    assert "legacy_narrative_hint" not in draft.normalized_run_spec
    assert isinstance(draft.normalized_run_spec, dict)

    validated = orchestrator.validate_choices(
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
        thesis_name=thesis.name,
        choices=draft.normalized_run_spec,
    )
    assert validated.status == "completed"
    confirmed = orchestrator.confirm_validated_spec(
        thesis_id=thesis.thesis_id,
        validated_spec=validated.payload["spec"],
        confirmation_note="idempotent confirm",
    )
    again = orchestrator.confirm_validated_spec(
        thesis_id=thesis.thesis_id,
        validated_spec=validated.payload["spec"],
        confirmation_note="idempotent confirm again",
    )
    assert confirmed.status == "confirmed"
    assert again.status == "confirmed"
    assert again.version != confirmed.version
    listed = orchestrator.list_spec_versions(thesis.thesis_id)
    assert sum(1 for item in listed if item.status == "confirmed") >= 2


def test_orchestrator_facade_restores_failed_cancelled_and_bundle_handoff(tmp_path):
    from tests.fixtures.assistant_parity import absolute_parity_run_spec, write_parity_bars

    write_parity_bars(tmp_path / "bars.csv")
    repository = LocalThesisRepository(tmp_path / "assistant")
    tools = AssistantTools(data_roots=(tmp_path,))
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)
    thesis = orchestrator.create_thesis(name="assistant_parity")
    conversation = orchestrator.ensure_conversation(thesis.thesis_id)

    choices = {
        key: value for key, value in absolute_parity_run_spec(tmp_path).items() if key != "name"
    }
    validated = orchestrator.validate_choices(
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
        thesis_name=thesis.name,
        choices=choices,
    )
    assert validated.status == "completed"
    confirmed = orchestrator.confirm_validated_spec(
        thesis_id=thesis.thesis_id,
        validated_spec=validated.payload["spec"],
    )

    class _FailingTools(AssistantTools):
        def run_experiment_to_bundle(self, spec, *, output_path):
            raise RuntimeError("forced failure")

    failing = AssistantOrchestrator(
        tools=_FailingTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    with pytest.raises(RuntimeError, match="forced failure"):
        failing.execute_confirmed_run(
            thesis_id=thesis.thesis_id,
            spec_version=confirmed.version,
            output_path=tmp_path / "fail.research.zip",
            conversation_id=conversation.conversation_id,
        )
    failed = orchestrator.list_runs(thesis.thesis_id)[-1]
    assert failed.status == "failed"
    assert failed.provenance is None

    confirmed_b = orchestrator.confirm_validated_spec(
        thesis_id=thesis.thesis_id,
        validated_spec=validated.payload["spec"],
    )
    tools_ok = AssistantTools(data_roots=(tmp_path,))
    original = tools_ok.run_experiment_to_bundle

    def cancel_then_run(spec, *, output_path):
        running = repository.list_runs(thesis.thesis_id)[-1]
        repository.cancel_run(
            thesis.thesis_id,
            running.run_id,
            expected_revision=running.revision,
            reason="operator cancel",
        )
        return original(spec, output_path=output_path)

    tools_ok.run_experiment_to_bundle = cancel_then_run
    cancelled_orchestrator = AssistantOrchestrator(tools=tools_ok, repository=repository)
    cancelled = cancelled_orchestrator.execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed_b.version,
        output_path=tmp_path / "cancel.research.zip",
        conversation_id=conversation.conversation_id,
    )
    assert cancelled.status == "cancelled"

    confirmed_c = orchestrator.confirm_validated_spec(
        thesis_id=thesis.thesis_id,
        validated_spec=validated.payload["spec"],
    )
    completed = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    ).execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed_c.version,
        output_path=tmp_path / "ok.research.zip",
        conversation_id=conversation.conversation_id,
    )
    assert completed.status == "completed"
    run = repository.get_run(thesis.thesis_id, completed.payload["run_id"])
    assert isinstance(run.provenance, dict)
    assert isinstance(run.provenance.get("cache_provenance"), dict)
    assert run.provenance["cache_provenance"].get("outcome") in {
        "bypassed",
        "cold",
        "data_hit",
        "levels_hit",
    }
    card = build_provenance_card(run.to_dict())
    assert card["cache_provenance"] == run.provenance["cache_provenance"]
    assert card["cache_outcome"] == run.provenance["cache_provenance"]["outcome"]
    session_state: dict = {"stale": 1}
    session_state["assistant_validated_run_spec"] = {
        "choices": {"dataset": {"path": "stale.csv"}},
        "spec": {"name": "stale"},
    }
    handoff = orchestrator.restore_run_bundle_to_session(
        thesis_id=thesis.thesis_id,
        run_id=run.run_id,
        session_state=session_state,
    )
    assert handoff["canonical_bundle_hash"] == run.provenance["canonical_bundle_hash"]
    assert handoff["restored_count"] > 0
    assert session_state["assistant_bundle_handoff"]["run_id"] == run.run_id
    assert session_state["assistant_validated_run_spec"] is None
    assert "data" in session_state

    exported = orchestrator.export_run(
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
        run=run,
    )
    assert exported.status == "completed"
    assert "markdown_report" in exported.payload
    assert "artifact" in exported.payload

    # Second completed run for comparison restoration.
    confirmed_d = orchestrator.confirm_validated_spec(
        thesis_id=thesis.thesis_id,
        validated_spec=validated.payload["spec"],
    )
    second = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    ).execute_confirmed_run(
        thesis_id=thesis.thesis_id,
        spec_version=confirmed_d.version,
        output_path=tmp_path / "ok2.research.zip",
        conversation_id=conversation.conversation_id,
    )
    right = repository.get_run(thesis.thesis_id, second.payload["run_id"])
    comparison = orchestrator.compare_completed_runs(
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
        left_run=run,
        right_run=right,
    )
    assert comparison.status == "completed"
    restored_comparisons = orchestrator.list_comparisons(thesis.thesis_id)
    assert len(restored_comparisons) == 1
    assert restored_comparisons[0].left_bundle_hash == canonical_bundle_hash(
        Path(run.provenance["bundle_path"]).read_bytes()
    )


def test_clear_thesis_scoped_state_helper():
    state = {
        "assistant_draft_prompt": "x",
        "assistant_draft_choices": {"a": 1},
        "assistant_hydrated_conversation_id": "c",
        "assistant_validated_run_spec": {"spec": {}},
        "assistant_focused_run_id": "run_focus",
        "assistant_results_qa_deep_link": True,
        "assistant_results_qa_force_expand": True,
        ASSISTANT_ADVANCED_EXPANDER_KEY: True,
        linked_run_expander_key("run_focus"): True,
        "assistant-chat-input-discuss-run_a": "stale",
        "assistant-chat-input-help": "stale help",
        "voice-results-audio-run_a": b"x",
        "assistant_bundle_handoff": {"thesis_id": "th_a", "run_id": "r1"},
        "assistant_run_explanations": {"r1": "keep"},
    }
    clear_thesis_scoped_state(state)
    assert state["assistant_draft_prompt"] == ""
    assert state["assistant_draft_choices"] == {}
    assert state["assistant_hydrated_conversation_id"] is None
    assert state["assistant_validated_run_spec"] is None
    assert state["assistant_focused_run_id"] is None
    assert state["assistant_results_qa_deep_link"] is False
    assert state["assistant_results_qa_force_expand"] is False
    assert ASSISTANT_ADVANCED_EXPANDER_KEY not in state
    assert linked_run_expander_key("run_focus") not in state
    assert "assistant-chat-input-discuss-run_a" not in state
    assert "assistant-chat-input-help" not in state
    assert "voice-results-audio-run_a" not in state
    assert state["assistant_bundle_handoff"] is None
    assert state["assistant_run_explanations"] == {"r1": "keep"}
    assert state["assistant_ux_mode"] == "discuss"
    assert state["assistant_discuss_run_picker"] is None


def test_apply_consumed_classic_focus_persists_results_qa_deep_link():
    state: dict = {}
    expand, run_id = apply_consumed_classic_focus(state, run_id="run_abc", channel="results_qa")
    assert expand is True
    assert run_id == "run_abc"
    assert state["assistant_focused_run_id"] == "run_abc"
    assert state["assistant_results_qa_deep_link"] is True
    assert state["assistant_results_qa_force_expand"] is True
    force_results_qa_expanders_open(state, run_id="run_abc")
    assert state[ASSISTANT_ADVANCED_EXPANDER_KEY] is True
    assert state[linked_run_expander_key("run_abc")] is True
    assert state.get("assistant_results_qa_force_expand") in (False, None)
    # Subsequent "empty" consume (post one-shot clear) must keep expansion flag
    # but must not re-force expander widget keys every rerun.
    expand2, run_id2 = apply_consumed_classic_focus(state, run_id=None, channel=None)
    assert expand2 is True
    assert run_id2 == "run_abc"
    assert state.get("assistant_results_qa_force_expand") in (False, None)
    # Legacy banner focus does not force Advanced open.
    legacy: dict = {}
    expand_legacy, run_legacy = apply_consumed_classic_focus(
        legacy, run_id="run_banner", channel=None
    )
    assert expand_legacy is False
    assert run_legacy is None
    assert legacy["assistant_focused_run_id"] == "run_banner"
    assert legacy["assistant_results_qa_deep_link"] is False
    assert legacy["assistant_results_qa_force_expand"] is False


def test_compare_completed_runs_returns_evidence_when_save_fails(tmp_path):
    from tests.fixtures.assistant_parity import absolute_parity_run_spec, write_parity_bars
    from thesistester.assistant.repository import AssistantRepositoryError

    write_parity_bars(tmp_path / "bars.csv")
    repository = LocalThesisRepository(tmp_path / "assistant")
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(tmp_path,)),
        repository=repository,
    )
    thesis = orchestrator.create_thesis(name="compare-save")
    conversation = orchestrator.ensure_conversation(thesis.thesis_id)
    choices = {
        key: value for key, value in absolute_parity_run_spec(tmp_path).items() if key != "name"
    }
    validated = orchestrator.validate_choices(
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
        thesis_name=thesis.name,
        choices=choices,
    )
    runs = []
    for index in range(2):
        confirmed = orchestrator.confirm_validated_spec(
            thesis_id=thesis.thesis_id,
            validated_spec=validated.payload["spec"],
        )
        result = orchestrator.execute_confirmed_run(
            thesis_id=thesis.thesis_id,
            spec_version=confirmed.version,
            output_path=tmp_path / f"cmp-{index}.research.zip",
            conversation_id=conversation.conversation_id,
        )
        assert result.status == "completed"
        runs.append(repository.get_run(thesis.thesis_id, result.payload["run_id"]))

    def boom(comparison):
        raise AssistantRepositoryError("forced comparison save failure")

    repository.save_comparison = boom
    compared = orchestrator.compare_completed_runs(
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
        left_run=runs[0],
        right_run=runs[1],
    )
    assert compared.status == "completed"
    assert compared.payload["comparison"]
    assert compared.payload["record"] is None
    assert "forced comparison save failure" in compared.payload["persistence_error"]
    assert orchestrator.list_comparisons(thesis.thesis_id) == ()
