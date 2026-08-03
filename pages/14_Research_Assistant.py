"""AI Research Assistant thesis workspace.

Presentation-only Streamlit consumer of ``AssistantOrchestrator``. The page
never mutates the thesis repository, calls tools, reads bundle bytes, or
compiles RunSpecs directly.
"""

from __future__ import annotations

import hashlib
import json

import streamlit as st

from thesistester.assistant import (
    AssistantOrchestrator,
    confirmed_run_feedback,
    list_payload_or_error,
)
from thesistester.assistant.contracts import AssistantRequest
from thesistester.assistant.llm import (
    LLMConfigurationError,
    LLMProviderError,
    create_openai_client,
    load_llm_settings,
)
from thesistester.assistant.llm_explainer import LLMEvidenceError
from thesistester.assistant.workspace import (
    CONFLUENCE_MODES,
    DIRECTIONS,
    EXPOSURE_POLICIES,
    FOLD_MODES,
    INDICATOR_LENGTH_OPTIONS,
    INSTRUMENTS,
    INTRABAR_MODELS,
    NAKED_REQUIREMENTS,
    OPENING_RANGE_MINUTES_OPTIONS,
    OVERLAP_POLICIES,
    POC_WINDOW_OPTIONS,
    RANKING_METRICS,
    RESEARCH_WORKFLOW_STEPS,
    SETUP_TRIGGER_OPTIONS,
    SMA_TIMEFRAMES,
    TIMEZONE_OPTIONS,
    TRIGGER_TIMEFRAMES,
    VWAP_WINDOW_OPTIONS,
    WFA_MATRIX_METRICS,
    WINDOW_MODES,
    active_bundle_handoff,
    build_confluence_level_options,
    build_plan_review,
    build_provenance_card,
    clear_failed_llm_run_explanation,
    coerce_multiselect_defaults,
    consume_assistant_flash,
    format_spec_status,
    init_assistant_session_state,
    invalidate_validation,
    latest_unresolved_assumptions,
    merge_execution_controls,
    merge_grid_controls,
    merge_level_controls,
    merge_setup_controls,
    merge_validation_controls,
    merge_walk_forward_controls,
    option_index,
    options_with_current,
    options_with_currents,
    parse_json_choices,
    safe_float,
    safe_int,
    select_thesis,
    set_assistant_flash,
    spec_status_next_step,
)
from thesistester.setup import available_level_columns


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]


def _render_assistant_flash() -> None:
    flash = consume_assistant_flash(st.session_state)
    if flash is None:
        return
    level = flash["level"]
    message = flash["message"]
    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    elif level == "error":
        st.error(message)
    else:
        st.info(message)


def _apply_draft_and_rerun(*, message: str) -> None:
    """Invalidate staged validation, flash success, and rerun so Apply feels responsive."""
    invalidate_validation(st.session_state)
    set_assistant_flash(st.session_state, level="success", message=message)
    st.rerun()


init_assistant_session_state(st.session_state)
orchestrator = AssistantOrchestrator.for_local_workspace()

st.title("Research Assistant")
st.caption("Draft explicit research theses. Execution remains confirmation- and schema-gated.")
with st.expander("Open research pages"):
    st.page_link("pages/1_Data.py", label="Data")
    st.page_link("pages/2_Levels.py", label="Levels")
    st.page_link("pages/3_Setup_Builder.py", label="Setup Builder")
    st.page_link("pages/6_Signals.py", label="Signals")
    st.page_link("pages/7_Backtest.py", label="Backtest")
    st.page_link("pages/8_Grid_Search.py", label="Grid Search")
    st.page_link("pages/9_Time_Analysis.py", label="Time Analysis")
    st.page_link("pages/10_Validation.py", label="Validation")
    st.page_link("pages/11_Report_Export.py", label="Report / Export")
    st.page_link("pages/12_Research_Bundles.py", label="Research Bundles")
    st.page_link("pages/13_Portfolio.py", label="Portfolio")

with st.sidebar:
    st.subheader("Theses")
    new_name = st.text_input("New thesis name", key="assistant_new_thesis_name")
    if st.button("Create thesis", use_container_width=True):
        try:
            thesis = orchestrator.create_thesis(name=new_name)
            select_thesis(st.session_state, thesis.thesis_id)
            st.session_state["assistant_thesis_picker"] = thesis.thesis_id
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    theses = orchestrator.list_theses(include_archived=True)
    thesis_ids = [thesis.thesis_id for thesis in theses]
    labels = {
        thesis.thesis_id: f"{thesis.name} ({thesis.lifecycle}, {thesis.thesis_id[-8:]})"
        for thesis in theses
    }
    selected_id = st.selectbox(
        "Select thesis",
        thesis_ids,
        format_func=labels.get,
        index=None,
        key="assistant_thesis_picker",
    )
    if selected_id:
        if select_thesis(st.session_state, selected_id):
            st.rerun()

thesis_id = st.session_state["assistant_selected_thesis_id"]
if not thesis_id:
    st.info("Create or select a thesis to begin.")
    st.stop()

_render_assistant_flash()

thesis = orchestrator.get_thesis(thesis_id)
st.subheader(thesis.name)
st.caption(f"Revision {thesis.revision} · {thesis.lifecycle}")
with st.expander("How to start a research run", expanded=False):
    for index, step in enumerate(RESEARCH_WORKFLOW_STEPS, start=1):
        st.write(f"{index}. {step}")
    st.caption(
        "Apply controls never start compute. Only Run confirmed research on a Confirmed "
        "specification version executes the pipeline."
    )
handoff = active_bundle_handoff(st.session_state, thesis_id=thesis_id)
if handoff is not None:
    st.caption(
        "Active handoff: "
        f"run {str(handoff['run_id'])[-8:]} · "
        f"restored {handoff.get('restored_count', 0)} session keys."
    )
with st.expander("Manage thesis"):
    renamed = st.text_input("Rename thesis", value=thesis.name, key=f"assistant_rename_{thesis_id}")
    if st.button("Save thesis name", key=f"rename-{thesis_id}"):
        try:
            orchestrator.rename_thesis(thesis_id, name=renamed, expected_revision=thesis.revision)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if st.button("Clone thesis", key=f"clone-{thesis_id}"):
        clone = orchestrator.clone_thesis(thesis_id)
        select_thesis(st.session_state, clone.thesis_id)
        st.session_state["assistant_thesis_picker"] = clone.thesis_id
        st.rerun()
    if thesis.lifecycle == "active":
        if st.button("Archive thesis", key=f"archive-{thesis_id}"):
            orchestrator.archive_thesis(thesis_id, expected_revision=thesis.revision)
            st.rerun()
    elif st.button("Restore thesis", key=f"restore-{thesis_id}"):
        orchestrator.restore_thesis(thesis_id, expected_revision=thesis.revision)
        st.rerun()

conversation_ids = st.session_state["assistant_conversation_ids"]
active_conversation = orchestrator.ensure_conversation(
    thesis_id,
    preferred_conversation_id=conversation_ids.get(thesis_id),
)
conversation_ids[thesis_id] = active_conversation.conversation_id
conversation_id = active_conversation.conversation_id
if st.session_state["assistant_hydrated_conversation_id"] != conversation_id:
    st.session_state["assistant_draft_choices"] = {}
    st.session_state["assistant_draft_prompt"] = "\n".join(
        str(message.get("content", ""))
        for message in active_conversation.messages
        if message.get("role") == "user"
    )
    for message in reversed(active_conversation.messages):
        if message.get("role") == "assistant" and isinstance(message.get("choices"), dict):
            st.session_state["assistant_draft_choices"] = message["choices"]
            break
    st.session_state["assistant_hydrated_conversation_id"] = conversation_id
    invalidate_validation(st.session_state)

st.subheader("Assistant chat")
for message in active_conversation.messages:
    with st.chat_message(message.get("role", "assistant")):
        st.write(message.get("content", ""))

if chat_message := st.chat_input("Describe or refine this thesis"):
    try:
        settings = load_llm_settings()
        client = create_openai_client(settings)
        draft = orchestrator.handle_chat_turn(
            client,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            user_message=chat_message,
            max_history_messages=settings.max_history_messages,
        )
        refreshed = orchestrator.get_conversation(thesis_id, conversation_id)
        st.session_state["assistant_draft_prompt"] = "\n".join(
            str(message.get("content", ""))
            for message in refreshed.messages
            if message.get("role") == "user"
        )
        st.session_state["assistant_draft_choices"] = draft.normalized_run_spec
        invalidate_validation(st.session_state)
        st.rerun()
    except (LLMConfigurationError, LLMProviderError) as exc:
        st.error(str(exc))

current = st.session_state["assistant_draft_choices"]
dataset = current.get("dataset") if isinstance(current.get("dataset"), dict) else {}
backtest = current.get("backtest") if isinstance(current.get("backtest"), dict) else {}
setup = current.get("setup") if isinstance(current.get("setup"), dict) else {}
levels = current.get("levels") if isinstance(current.get("levels"), dict) else {}
validation = current.get("validation") if isinstance(current.get("validation"), dict) else {}
grid = current.get("grid") if isinstance(current.get("grid"), dict) else {}
walk_forward = current.get("walk_forward") if isinstance(current.get("walk_forward"), dict) else {}

with st.expander("Structured execution controls", expanded=True):
    with st.form(f"assistant_execution_{thesis_id}_{_fingerprint(current)}"):
        dataset_path = st.text_input("Dataset CSV path", value=str(dataset.get("path", "")))
        instrument = st.selectbox(
            "Instrument",
            list(INSTRUMENTS),
            index=option_index(
                INSTRUMENTS,
                (setup or {}).get("instrument") or dataset.get("instrument") or "ES",
            ),
        )
        draft_source_timezone = str(dataset.get("source_timezone") or "America/New_York").strip()
        source_timezone_options = options_with_current(
            TIMEZONE_OPTIONS, draft_source_timezone or None
        )
        source_timezone = st.selectbox(
            "Source timezone",
            source_timezone_options,
            index=option_index(
                source_timezone_options,
                draft_source_timezone or "America/New_York",
            ),
            help="Same searchable timezone catalog as the Data page.",
        )
        subtimeframe_path = st.text_input(
            "Subtimeframe CSV path (optional)",
            value=str(dataset.get("subtimeframe_path") or ""),
        )
        stop_loss_ticks = st.number_input(
            "Stop loss ticks",
            min_value=1,
            value=safe_int(backtest.get("stop_loss_ticks"), 8),
        )
        take_profit_ticks = st.number_input(
            "Take profit ticks",
            min_value=1,
            value=safe_int(backtest.get("take_profit_ticks"), 16),
        )
        commission_per_side = st.number_input(
            "Commission per side",
            min_value=0.0,
            value=safe_float(backtest.get("commission_per_side"), 0.0),
        )
        slippage_ticks = st.number_input(
            "Slippage ticks",
            min_value=0.0,
            value=safe_float(backtest.get("slippage_ticks"), 0.0),
        )
        exposure_policy = st.selectbox(
            "Exposure policy",
            list(EXPOSURE_POLICIES),
            index=option_index(
                EXPOSURE_POLICIES,
                backtest.get("exposure_policy") or "allow_all",
            ),
        )
        intrabar_model = st.selectbox(
            "Intrabar model",
            list(INTRABAR_MODELS),
            index=option_index(INTRABAR_MODELS, backtest.get("intrabar_model")),
        )
        flat_by_session_close = st.checkbox(
            "Flatten at session close",
            value=bool(backtest.get("flat_by_session_close", False)),
        )
        session_close_time = st.text_input(
            "Session close time (exchange time)",
            value=str(backtest.get("session_close_time") or "16:00"),
        )
        draft_session_timezone = str(backtest.get("session_timezone") or "America/New_York").strip()
        session_timezone_options = options_with_current(
            TIMEZONE_OPTIONS, draft_session_timezone or None
        )
        session_timezone = st.selectbox(
            "Session timezone",
            session_timezone_options,
            index=option_index(
                session_timezone_options,
                draft_session_timezone or "America/New_York",
            ),
            help="Same searchable timezone catalog as Backtest / Grid Search.",
        )
        no_new_entries_after = st.text_input(
            "No new entries after (exchange time)",
            value=str(backtest.get("no_new_entries_after") or "15:45"),
        )
        max_holding_bars = st.number_input(
            "Max holding bars (0 = unlimited)",
            min_value=0,
            value=safe_int(backtest.get("max_holding_bars"), 0),
        )
        allow_same_bar_exit = st.checkbox(
            "Allow same-bar exit",
            value=bool(backtest.get("allow_same_bar_exit", True)),
        )
        cooldown_bars_after_exit = st.number_input(
            "Cooldown bars after exit",
            min_value=0,
            value=safe_int(backtest.get("cooldown_bars_after_exit"), 0),
        )
        if st.form_submit_button("Apply execution controls"):
            st.session_state["assistant_draft_choices"] = merge_execution_controls(
                current,
                dataset_path=dataset_path,
                instrument=instrument,
                source_timezone=source_timezone,
                subtimeframe_path=subtimeframe_path,
                stop_loss_ticks=int(stop_loss_ticks),
                take_profit_ticks=int(take_profit_ticks),
                commission_per_side=float(commission_per_side),
                slippage_ticks=float(slippage_ticks),
                exposure_policy=exposure_policy,
                intrabar_model=intrabar_model,
                flat_by_session_close=flat_by_session_close,
                session_close_time=session_close_time,
                session_timezone=session_timezone,
                no_new_entries_after=no_new_entries_after,
                max_holding_bars=int(max_holding_bars) or None,
                allow_same_bar_exit=allow_same_bar_exit,
                cooldown_bars_after_exit=int(cooldown_bars_after_exit),
            )
            _apply_draft_and_rerun(
                message=(
                    "Execution controls applied to the session draft. "
                    "This does not create a specification version or start a run."
                )
            )

with st.expander("Structured setup and confluence controls", expanded=True):
    with st.form(f"assistant_setup_{thesis_id}_{_fingerprint(setup)}"):
        setup_name = st.text_input("Setup name", value=str(setup.get("name") or thesis.name))
        description = st.text_input("Setup description", value=str(setup.get("description") or ""))
        levels_df = st.session_state.get("levels")
        live_level_columns = (
            available_level_columns(levels_df) if hasattr(levels_df, "columns") else None
        )
        current_selected_levels = list(
            setup.get("selected_levels") or ["dVWAP_RTH", "SMA_50_30min"]
        )
        confluence_options = build_confluence_level_options(
            selected_levels=current_selected_levels,
            levels_settings=levels if isinstance(levels, dict) else {},
            available_columns=live_level_columns,
        )
        selected_levels = st.multiselect(
            "Confluence levels",
            options=confluence_options,
            default=coerce_multiselect_defaults(current_selected_levels, confluence_options)
            or coerce_multiselect_defaults(
                ["dVWAP_RTH", "SMA_50_30min"],
                confluence_options,
            ),
            help=(
                "Searchable multiselect, same interaction pattern as Setup Builder / Signals. "
                "Includes live Levels columns when present, plus the common catalog."
            ),
        )
        trigger = st.selectbox(
            "Trigger",
            list(SETUP_TRIGGER_OPTIONS),
            index=option_index(SETUP_TRIGGER_OPTIONS, setup.get("trigger")),
        )
        direction = st.selectbox(
            "Direction",
            list(DIRECTIONS),
            index=option_index(DIRECTIONS, setup.get("direction")),
        )
        tolerance_ticks = st.number_input(
            "Confluence tolerance ticks",
            min_value=0.0,
            value=safe_float(setup.get("tolerance_ticks"), 0.0),
        )
        min_confluences = st.number_input(
            "Minimum confluences",
            min_value=1,
            value=safe_int(setup.get("min_confluences"), 1),
        )
        max_confluences = st.number_input(
            "Maximum confluences",
            min_value=1,
            value=safe_int(setup.get("max_confluences"), 1),
        )
        naked_only = st.checkbox("Naked levels only", value=bool(setup.get("naked_only", False)))
        naked_requirement = st.selectbox(
            "Naked requirement",
            list(NAKED_REQUIREMENTS),
            index=option_index(NAKED_REQUIREMENTS, setup.get("naked_requirement")),
        )
        trigger_timeframe = st.selectbox(
            "Trigger timeframe",
            list(TRIGGER_TIMEFRAMES),
            index=option_index(TRIGGER_TIMEFRAMES, setup.get("trigger_timeframe")),
        )
        confluence_mode = st.selectbox(
            "Confluence mode",
            list(CONFLUENCE_MODES),
            index=option_index(CONFLUENCE_MODES, setup.get("confluence_mode")),
        )
        current_anchor = str(setup.get("anchor_level") or "")
        anchor_options = [""] + list(confluence_options)
        if current_anchor and current_anchor not in anchor_options:
            anchor_options.append(current_anchor)
        anchor_level = st.selectbox(
            "Anchor level (anchor_rules mode)",
            options=anchor_options,
            index=option_index(anchor_options, current_anchor),
            format_func=lambda value: "—" if value == "" else value,
            help="Searchable selectbox over the same confluence catalog.",
        )
        min_valid_confluences = st.number_input(
            "Minimum valid confluences",
            min_value=1,
            value=safe_int(setup.get("min_valid_confluences"), 1),
        )
        if st.form_submit_button("Apply setup controls"):
            try:
                st.session_state["assistant_draft_choices"] = merge_setup_controls(
                    current,
                    setup_name=setup_name,
                    description=description,
                    selected_levels_raw=selected_levels,
                    trigger=trigger,
                    direction=direction,
                    tolerance_ticks=float(tolerance_ticks),
                    min_confluences=int(min_confluences),
                    max_confluences=int(max_confluences),
                    naked_only=naked_only,
                    naked_requirement=naked_requirement,
                    trigger_timeframe=trigger_timeframe,
                    confluence_mode=confluence_mode,
                    anchor_level=anchor_level,
                    min_valid_confluences=int(min_valid_confluences),
                )
                _apply_draft_and_rerun(
                    message=(
                        "Setup controls applied to the session draft. "
                        "This does not create a specification version or start a run."
                    )
                )
            except ValueError as exc:
                st.error(str(exc))

with st.expander("Structured level controls"):
    with st.form(f"assistant_levels_{thesis_id}_{_fingerprint(levels)}"):
        session_vwap_enabled = st.checkbox(
            "Enable developing RTH VWAP",
            value=bool(levels.get("session_vwap_enabled", True)),
        )
        draft_opening_range = safe_int(levels.get("opening_range_minutes"), 30)
        opening_range_options = options_with_current(
            OPENING_RANGE_MINUTES_OPTIONS,
            draft_opening_range if draft_opening_range > 0 else None,
        )
        opening_range_minutes = st.selectbox(
            "Opening range minutes",
            opening_range_options,
            index=option_index(opening_range_options, draft_opening_range),
            help="Common Levels sizes are 5 / 15 / 30; draft values outside that set stay selectable.",
        )
        length_options = list(INDICATOR_LENGTH_OPTIONS)
        for value in list(levels.get("sma_lengths") or []) + list(levels.get("ema_lengths") or []):
            parsed = safe_int(value, 0)
            if parsed > 0 and parsed not in length_options:
                length_options.append(parsed)
        sma_lengths = st.multiselect(
            "SMA lengths",
            options=length_options,
            default=coerce_multiselect_defaults(
                [safe_int(v, 0) for v in (levels.get("sma_lengths") or [50, 200])],
                length_options,
            )
            or [50, 200],
        )
        draft_sma_timeframes = [
            str(value).strip()
            for value in (levels.get("sma_timeframes") or ["30min"])
            if str(value).strip()
        ]
        sma_timeframe_options = options_with_currents(SMA_TIMEFRAMES, draft_sma_timeframes)
        sma_timeframes = st.multiselect(
            "SMA timeframes",
            options=sma_timeframe_options,
            default=coerce_multiselect_defaults(draft_sma_timeframes, sma_timeframe_options)
            or coerce_multiselect_defaults(["30min"], sma_timeframe_options),
        )
        ema_lengths = st.multiselect(
            "EMA lengths",
            options=length_options,
            default=coerce_multiselect_defaults(
                [safe_int(v, 0) for v in (levels.get("ema_lengths") or [])],
                length_options,
            ),
        )
        draft_ema_timeframes = [
            str(value).strip()
            for value in (levels.get("ema_timeframes") or [])
            if str(value).strip()
        ]
        ema_timeframe_options = options_with_currents(SMA_TIMEFRAMES, draft_ema_timeframes)
        ema_timeframes = st.multiselect(
            "EMA timeframes",
            options=ema_timeframe_options,
            default=coerce_multiselect_defaults(draft_ema_timeframes, ema_timeframe_options),
        )
        draft_vwap_windows = [
            str(value).strip() for value in (levels.get("vwap_windows") or []) if str(value).strip()
        ]
        vwap_window_options = options_with_currents(VWAP_WINDOW_OPTIONS, draft_vwap_windows)
        vwap_windows = st.multiselect(
            "VWAP windows",
            options=vwap_window_options,
            default=coerce_multiselect_defaults(draft_vwap_windows, vwap_window_options),
            help="Same searchable window catalog as the Levels page; draft values outside the catalog stay selectable.",
        )
        draft_poc_windows = [
            str(value).strip() for value in (levels.get("poc_windows") or []) if str(value).strip()
        ]
        poc_window_options = options_with_currents(POC_WINDOW_OPTIONS, draft_poc_windows)
        poc_windows = st.multiselect(
            "POC windows",
            options=poc_window_options,
            default=coerce_multiselect_defaults(draft_poc_windows, poc_window_options),
            help="Same searchable window catalog as the Levels page; draft values outside the catalog stay selectable.",
        )
        if st.form_submit_button("Apply level controls"):
            try:
                st.session_state["assistant_draft_choices"] = merge_level_controls(
                    current,
                    session_vwap_enabled=session_vwap_enabled,
                    opening_range_minutes=int(opening_range_minutes),
                    sma_lengths_raw=sma_lengths,
                    sma_timeframes=sma_timeframes,
                    ema_lengths_raw=ema_lengths,
                    ema_timeframes=ema_timeframes,
                    vwap_windows_raw=vwap_windows,
                    poc_windows_raw=poc_windows,
                )
                _apply_draft_and_rerun(
                    message=(
                        "Level controls applied to the session draft. "
                        "This does not create a specification version or start a run."
                    )
                )
            except ValueError as exc:
                st.error(str(exc))

with st.expander("Structured validation controls"):
    monte_carlo = (
        validation.get("monte_carlo") if isinstance(validation.get("monte_carlo"), dict) else {}
    )
    with st.form(f"assistant_validation_{thesis_id}_{_fingerprint(validation)}"):
        bootstrap = st.number_input(
            "Bootstrap samples",
            min_value=1,
            value=safe_int(validation.get("n_bootstrap"), 2000),
        )
        permutations = st.number_input(
            "Permutation samples",
            min_value=1,
            value=safe_int(validation.get("n_permutations"), 5000),
        )
        random_state = st.number_input(
            "Validation random seed",
            min_value=0,
            value=safe_int(validation.get("random_state"), 42),
        )
        min_trades_soft = st.number_input(
            "Soft minimum trades",
            min_value=1,
            value=safe_int(validation.get("min_trades_soft"), 30),
        )
        min_trades_hard = st.number_input(
            "Hard minimum trades",
            min_value=1,
            value=safe_int(validation.get("min_trades_hard"), 10),
        )
        monte_carlo_enabled = st.checkbox(
            "Enable Monte Carlo", value=bool(monte_carlo.get("enabled", False))
        )
        monte_carlo_simulations = st.number_input(
            "Monte Carlo simulations",
            min_value=1,
            value=safe_int(monte_carlo.get("n_simulations"), 200),
        )
        excursion_enabled = st.checkbox(
            "Enable excursion diagnostics",
            value=bool((validation.get("excursion") or {}).get("enabled", False)),
        )
        overfitting_enabled = st.checkbox(
            "Enable overfitting diagnostics",
            value=bool((validation.get("overfitting") or {}).get("enabled", False)),
        )
        noise_enabled = st.checkbox(
            "Enable noise diagnostics",
            value=bool((validation.get("noise") or {}).get("enabled", False)),
        )
        sensitivity_enabled = st.checkbox(
            "Enable sensitivity diagnostics",
            value=bool((validation.get("sensitivity") or {}).get("enabled", False)),
        )
        if st.form_submit_button("Apply validation controls"):
            st.session_state["assistant_draft_choices"] = merge_validation_controls(
                current,
                n_bootstrap=int(bootstrap),
                n_permutations=int(permutations),
                random_state=int(random_state),
                monte_carlo_enabled=monte_carlo_enabled,
                monte_carlo_simulations=int(monte_carlo_simulations),
                excursion_enabled=excursion_enabled,
                overfitting_enabled=overfitting_enabled,
                noise_enabled=noise_enabled,
                sensitivity_enabled=sensitivity_enabled,
                min_trades_soft=int(min_trades_soft),
                min_trades_hard=int(min_trades_hard),
            )
            _apply_draft_and_rerun(
                message=(
                    "Validation controls applied to the session draft. "
                    "This does not create a specification version or start a run."
                )
            )

with st.expander("Structured grid controls"):
    with st.form(f"assistant_grid_{thesis_id}_{_fingerprint(grid)}"):
        grid_enabled = st.checkbox("Enable grid search", value=bool(grid.get("enabled", True)))
        stop_values = st.text_input(
            "Grid stop ticks",
            value=", ".join(str(v) for v in (grid.get("stop_loss_ticks_values") or [4, 8, 12])),
        )
        target_values = st.text_input(
            "Grid target ticks",
            value=", ".join(str(v) for v in (grid.get("take_profit_ticks_values") or [8, 16, 24])),
        )
        ranking_metric = st.selectbox(
            "Grid ranking metric",
            list(RANKING_METRICS),
            index=option_index(RANKING_METRICS, grid.get("ranking_metric")),
        )
        min_trades = st.number_input(
            "Grid minimum trades",
            min_value=1,
            value=safe_int(grid.get("min_trades"), 30),
        )
        max_grid_cells = st.number_input(
            "Max grid cells",
            min_value=1,
            value=safe_int(grid.get("max_grid_cells"), 500),
        )
        if st.form_submit_button("Apply grid controls"):
            try:
                st.session_state["assistant_draft_choices"] = merge_grid_controls(
                    current,
                    enabled=grid_enabled,
                    stop_values_raw=stop_values,
                    target_values_raw=target_values,
                    ranking_metric=ranking_metric,
                    min_trades=int(min_trades),
                    max_grid_cells=int(max_grid_cells),
                )
                _apply_draft_and_rerun(
                    message=(
                        "Grid controls applied to the session draft. "
                        "This does not create a specification version or start a run."
                    )
                )
            except ValueError as exc:
                st.error(str(exc))

with st.expander("Structured walk-forward controls"):
    matrix = walk_forward.get("matrix") if isinstance(walk_forward.get("matrix"), dict) else {}
    with st.form(f"assistant_walk_forward_{thesis_id}_{_fingerprint(walk_forward)}"):
        enabled = st.checkbox("Enable walk-forward", value=bool(walk_forward.get("enabled", False)))
        fold_mode = st.selectbox(
            "Fold mode",
            list(FOLD_MODES),
            index=option_index(FOLD_MODES, walk_forward.get("fold_mode")),
        )
        window_mode = st.selectbox(
            "Window mode",
            list(WINDOW_MODES),
            index=option_index(WINDOW_MODES, walk_forward.get("window_mode")),
        )
        overlap_policy = st.selectbox(
            "Overlapping OOS ownership",
            list(OVERLAP_POLICIES),
            index=option_index(OVERLAP_POLICIES, walk_forward.get("overlap_policy")),
        )
        otf_history_policies = ("fold_local", "causal_prefix")
        otf_history_policy = st.selectbox(
            "OTF history policy",
            list(otf_history_policies),
            index=option_index(otf_history_policies, walk_forward.get("otf_history_policy")),
            help=(
                "fold_local (default): OTF uses only each fold’s OHLCV. "
                "causal_prefix: earlier bars may establish OTF state; only fold-local "
                "signals are scored. Never uses future bars."
            ),
        )
        train_default = (
            walk_forward.get("train_sessions")
            if fold_mode == "sessions"
            else walk_forward.get("train_bars")
        )
        test_default = (
            walk_forward.get("test_sessions")
            if fold_mode == "sessions"
            else walk_forward.get("test_bars")
        )
        step_default = (
            walk_forward.get("step_sessions")
            if fold_mode == "sessions"
            else walk_forward.get("step_bars")
        )
        train_size = st.number_input(
            "Train size",
            min_value=1,
            value=safe_int(train_default, 20 if fold_mode == "sessions" else 500),
        )
        test_size = st.number_input(
            "Test size",
            min_value=1,
            value=safe_int(test_default, 5 if fold_mode == "sessions" else 100),
        )
        step_size = st.number_input(
            "Step size",
            min_value=1,
            value=safe_int(step_default, 5 if fold_mode == "sessions" else 100),
        )
        wfa_ranking = st.selectbox(
            "Walk-forward ranking metric",
            list(RANKING_METRICS),
            index=option_index(RANKING_METRICS, walk_forward.get("ranking_metric")),
        )
        min_train_trades = st.number_input(
            "Minimum train trades",
            min_value=1,
            value=safe_int(walk_forward.get("min_train_trades"), 10),
        )
        wfa_stops = st.text_input(
            "Walk-forward stop ticks",
            value=", ".join(str(v) for v in (walk_forward.get("stop_loss_ticks_values") or [8])),
        )
        wfa_targets = st.text_input(
            "Walk-forward target ticks",
            value=", ".join(str(v) for v in (walk_forward.get("take_profit_ticks_values") or [16])),
        )
        matrix_enabled = False
        matrix_train_raw = ", ".join(
            str(v) for v in (matrix.get("train_session_values") or [20, 40])
        )
        matrix_test_raw = ", ".join(str(v) for v in (matrix.get("test_session_values") or [5, 10]))
        matrix_metric = str(matrix.get("matrix_metric") or WFA_MATRIX_METRICS[0])
        max_matrix_cells = safe_int(matrix.get("max_matrix_cells"), 100)
        if fold_mode == "sessions":
            matrix_enabled = st.checkbox(
                "Enable WFA matrix",
                value=bool(matrix.get("enabled", False)),
            )
            matrix_train_raw = st.text_input(
                "Matrix train session values",
                value=matrix_train_raw,
            )
            matrix_test_raw = st.text_input(
                "Matrix test session values",
                value=matrix_test_raw,
            )
            matrix_metric = st.selectbox(
                "Matrix metric",
                list(WFA_MATRIX_METRICS),
                index=option_index(WFA_MATRIX_METRICS, matrix_metric),
            )
            max_matrix_cells = st.number_input(
                "Max matrix cells",
                min_value=1,
                value=safe_int(max_matrix_cells, 100),
            )
        else:
            st.caption("WFA matrix is available only for session fold mode.")
        if st.form_submit_button("Apply walk-forward controls"):
            try:
                st.session_state["assistant_draft_choices"] = merge_walk_forward_controls(
                    current,
                    enabled=enabled,
                    fold_mode=fold_mode,
                    window_mode=window_mode,
                    overlap_policy=overlap_policy,
                    train_size=int(train_size),
                    test_size=int(test_size),
                    step_size=int(step_size),
                    ranking_metric=wfa_ranking,
                    min_train_trades=int(min_train_trades),
                    stop_values_raw=wfa_stops,
                    target_values_raw=wfa_targets,
                    matrix_enabled=matrix_enabled,
                    matrix_train_raw=matrix_train_raw,
                    matrix_test_raw=matrix_test_raw,
                    matrix_metric=matrix_metric,
                    max_matrix_cells=int(max_matrix_cells),
                    otf_history_policy=str(otf_history_policy),
                )
                _apply_draft_and_rerun(
                    message=(
                        "Walk-forward controls applied to the session draft. "
                        "This does not create a specification version or start a run."
                    )
                )
            except ValueError as exc:
                st.error(str(exc))

with st.expander("Reuse saved setup"):
    listed = orchestrator.dispatch(
        AssistantRequest(capability_id="SETUP.manage_saved_setups", payload={"action": "list"})
    )
    saved_setups, list_error = list_payload_or_error(
        listed,
        items_key="setups",
        default_error="Unable to list saved setups.",
    )
    if list_error is not None:
        st.error(list_error)
    setup_options = {
        item["setup_id"]: f"{item.get('name', 'Unnamed')} ({item['setup_id'][-8:]})"
        for item in saved_setups
        if isinstance(item, dict) and isinstance(item.get("setup_id"), str)
    }
    selected_setup_id = st.selectbox(
        "Saved setup",
        list(setup_options),
        format_func=setup_options.get,
        index=None,
        key=f"assistant_saved_setup_{thesis_id}",
        disabled=list_error is not None,
    )
    if selected_setup_id and st.button("Apply saved setup"):
        loaded = orchestrator.dispatch(
            AssistantRequest(
                capability_id="SETUP.manage_saved_setups",
                payload={"action": "load", "setup_id": selected_setup_id},
            ),
            thesis_id=thesis_id,
            conversation_id=conversation_id,
        )
        if loaded.status != "completed":
            st.error(loaded.payload.get("error", {}).get("message", "Unable to load setup."))
        else:
            setup_config = loaded.payload.get("setup", {}).get("setup_config")
            if not isinstance(setup_config, dict):
                st.error("Saved setup does not contain a valid setup configuration.")
            else:
                st.session_state["assistant_draft_choices"] = {
                    **st.session_state["assistant_draft_choices"],
                    "setup": setup_config,
                }
                _apply_draft_and_rerun(
                    message=(
                        "Saved setup applied to the session draft. "
                        "This does not create a specification version or start a run."
                    )
                )

prompt = st.text_area(
    "Describe the setup thesis",
    value=st.session_state["assistant_draft_prompt"],
    placeholder="Example: Uptrend retraces to dVWAP with 30m SMA confluence in NY B session.",
)
st.session_state["assistant_draft_prompt"] = prompt

with st.expander("Advanced: edit complete research choices as JSON"):
    choices_raw = st.text_area(
        "Explicit research choices (JSON)",
        value=json.dumps(st.session_state["assistant_draft_choices"], indent=2),
        help="Audit-only. Apply JSON edits explicitly; structured controls own the default path.",
    )
    if st.button("Apply JSON audit edits"):
        try:
            st.session_state["assistant_draft_choices"] = parse_json_choices(choices_raw)
            _apply_draft_and_rerun(
                message=(
                    "JSON audit edits applied to the session draft. "
                    "This does not create a specification version or start a run."
                )
            )
        except (ValueError, json.JSONDecodeError) as exc:
            st.error(str(exc))

draft_col, validate_col = st.columns(2)
with draft_col:
    if st.button("Draft research plan", type="primary"):
        try:
            spec = orchestrator.draft_specification(
                thesis_id=thesis_id,
                prompt=st.session_state["assistant_draft_prompt"],
                choices=st.session_state["assistant_draft_choices"],
            )
            # Keep staged session choices aligned with the persisted compiler output.
            st.session_state["assistant_draft_choices"] = dict(spec.normalized_run_spec)
            invalidate_validation(st.session_state)
            set_assistant_flash(
                st.session_state,
                level="success",
                message=(
                    f"Saved specification version {spec.version} "
                    f"({format_spec_status(spec.status)}). "
                    "Next: Validate executable RunSpec, then Confirm under Plan review."
                ),
            )
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
with validate_col:
    if st.button("Validate executable RunSpec"):
        validation_result = orchestrator.validate_choices(
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            thesis_name=thesis.name,
            choices=st.session_state["assistant_draft_choices"],
        )
        if validation_result.status != "completed":
            st.session_state["assistant_validated_run_spec"] = None
            st.error(
                validation_result.payload.get("error", {}).get("message", "Validation failed.")
            )
        else:
            st.session_state["assistant_validated_run_spec"] = {
                "choices": validation_result.payload["choices"],
                "spec": validation_result.payload["spec"],
            }
            st.success(
                "Executable RunSpec is valid. "
                "Confirm validated RunSpec appears under Plan review when clarifications are clear."
            )

validated_state = st.session_state["assistant_validated_run_spec"]
spec_versions = orchestrator.list_spec_versions(thesis_id)
plan = build_plan_review(
    thesis_name=thesis.name,
    choices=st.session_state["assistant_draft_choices"],
    validated_spec=validated_state["spec"]
    if isinstance(validated_state, dict)
    and validated_state.get("choices") == st.session_state["assistant_draft_choices"]
    else None,
    unresolved_assumptions=latest_unresolved_assumptions(spec_versions),
)
st.subheader("Plan review")
st.write(
    f"**{plan['thesis_name']}** · instrument `{plan['instrument']}` · "
    f"trigger `{plan['trigger']}` · levels `{', '.join(plan['selected_levels']) or '—'}`"
)
st.caption(
    f"Dataset `{plan['dataset_path'] or '—'}` · exposure `{plan['exposure_policy']}` · "
    f"intrabar `{plan['intrabar_model']}` · "
    f"grid={'on' if plan['has_grid'] else 'off'} · "
    f"validation={'on' if plan['has_validation'] else 'off'} · "
    f"WFA={'on' if plan['has_walk_forward'] else 'off'}"
)
st.info(f"Next: {plan['next_action']}")
if plan["unresolved_assumptions"]:
    st.warning("Clarifications still required before confirmation.")
    for item in plan["unresolved_assumptions"]:
        st.write(f"- {item}")
if plan["validated_spec"] is not None:
    with st.expander("Validated executable RunSpec", expanded=True):
        st.json(plan["validated_spec"])
    if st.button("Save validated setup to library"):
        saved = orchestrator.dispatch(
            AssistantRequest(
                capability_id="SETUP.manage_saved_setups",
                payload={
                    "action": "save",
                    "setup": plan["validated_spec"]["setup"],
                    "instrument": plan["validated_spec"]["setup"].get("instrument"),
                },
            ),
            confirmed=True,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
        )
        if saved.status != "completed":
            st.error(saved.payload.get("error", {}).get("message", "Unable to save setup."))
        else:
            st.success(f"Saved setup {saved.payload['setup']['setup_id']}.")
    if plan["ready_for_confirmation"]:
        if st.button("Confirm validated RunSpec", type="primary"):
            confirmed = orchestrator.confirm_validated_spec(
                thesis_id=thesis_id,
                validated_spec=plan["validated_spec"],
            )
            st.session_state["assistant_validated_run_spec"] = None
            set_assistant_flash(
                st.session_state,
                level="success",
                message=(
                    f"Confirmed specification version {confirmed.version}. "
                    "Open it under Specifications and click Run confirmed research."
                ),
            )
            st.rerun()
    elif plan["unresolved_assumptions"]:
        st.caption("Resolve clarifications before confirming the validated RunSpec.")
else:
    st.caption(
        "Confirm validated RunSpec appears here only after Validate succeeds on the current draft."
    )

st.subheader("Specifications")
st.caption(
    "Each version is an immutable snapshot created by Draft research plan or Confirm — "
    "not by Apply controls. Apply only stages the session draft."
)
if not spec_versions:
    st.info("No specification versions yet. Draft research plan to create the first version.")
for spec in reversed(spec_versions):
    status_label = format_spec_status(spec.status)
    expanded = spec.status == "confirmed" and spec.version == max(
        item.version for item in spec_versions
    )
    with st.expander(
        f"Specification v{spec.version} · {status_label}",
        expanded=expanded,
    ):
        st.caption(spec_status_next_step(spec.status))
        if spec.parent_version is not None:
            st.caption(f"Parent version: v{spec.parent_version}")
        st.json(spec.normalized_run_spec)
        if spec.unresolved_assumptions:
            st.warning("Clarifications required")
            for assumption in spec.unresolved_assumptions:
                st.write(f"- {assumption}")
        if spec.status == "confirmed" and {"dataset", "setup", "backtest"}.issubset(
            spec.normalized_run_spec
        ):
            if st.button("Run confirmed research", type="primary", key=f"run-{spec.version}"):
                try:
                    run_result = orchestrator.execute_confirmed_run(
                        thesis_id=thesis_id,
                        spec_version=spec.version,
                        output_path=orchestrator.default_bundle_output_path(thesis_id),
                        conversation_id=conversation_id,
                    )
                    level, message = confirmed_run_feedback(run_result)
                    set_assistant_flash(st.session_state, level=level, message=message)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Research run failed: {exc}")
        elif spec.status == "ready_for_confirmation":
            st.warning(
                "Ready to confirm means the draft compiled cleanly. "
                "There is no confirm button inside this list — use Plan review above: "
                "Validate executable RunSpec, then Confirm validated RunSpec."
            )

st.subheader("Research runs")
runs = orchestrator.list_runs(thesis_id)
if not runs:
    st.info("No research runs are recorded for this thesis yet.")
else:
    for run in reversed(runs):
        provenance_card = build_provenance_card(run.to_dict())
        with st.expander(f"Run {run.run_id[-8:]} · {run.status}"):
            st.caption(
                f"Specification v{run.spec_version} · revision {run.revision} · "
                f"hash `{str(provenance_card.get('canonical_bundle_hash') or '—')[:16]}`"
            )
            st.json(provenance_card)
            if run.status == "running" and st.button("Cancel run", key=f"cancel-{run.run_id}"):
                cancelled = orchestrator.cancel_run(
                    thesis_id=thesis_id,
                    run_id=run.run_id,
                    conversation_id=conversation_id,
                )
                if cancelled.status == "cancelled":
                    st.warning("Research run cancelled.")
                else:
                    st.error(
                        cancelled.payload.get("error", {}).get(
                            "message",
                            "Unable to cancel this run because it is no longer running.",
                        )
                    )
                st.rerun()
            if run.status == "completed" and isinstance(run.provenance, dict):
                if st.button("Explain run", key=f"explain-{run.run_id}"):
                    result = orchestrator.explain_run(
                        thesis_id=thesis_id,
                        conversation_id=conversation_id,
                        run=run,
                    )
                    if result.status != "completed":
                        st.error(
                            result.payload.get("error", {}).get(
                                "message", "Unable to load evidence."
                            )
                        )
                    else:
                        st.session_state["assistant_run_explanations"][run.run_id] = result.payload[
                            "explanation"
                        ]
                explanation = st.session_state["assistant_run_explanations"].get(run.run_id)
                if explanation:
                    st.write(explanation)
                if st.button(
                    "Generate evidence-only AI explanation", key=f"llm-explain-{run.run_id}"
                ):
                    try:
                        client = create_openai_client(load_llm_settings())
                        result = orchestrator.explain_run_with_llm(
                            client,
                            thesis_id=thesis_id,
                            conversation_id=conversation_id,
                            run=run,
                        )
                        if result.status != "completed":
                            raise ValueError(
                                result.payload.get("error", {}).get(
                                    "message", "Unable to load evidence."
                                )
                            )
                        st.session_state["assistant_llm_run_explanations"][run.run_id] = (
                            result.payload["llm_explanation"]
                        )
                        st.session_state["assistant_llm_attempts"][run.run_id] = result.payload.get(
                            "provider_attempts"
                        )
                    except (
                        LLMConfigurationError,
                        LLMProviderError,
                        LLMEvidenceError,
                        ValueError,
                    ) as exc:
                        clear_failed_llm_run_explanation(st.session_state, run.run_id)
                        st.error(f"Unable to generate AI explanation: {exc}")
                llm_explanation = st.session_state["assistant_llm_run_explanations"].get(run.run_id)
                if llm_explanation:
                    st.write(llm_explanation.summary)
                    for caveat in llm_explanation.caveats:
                        st.caption(f"Caveat: {caveat}")
                    for claim in getattr(llm_explanation, "claims", ()) or ():
                        st.caption(f"Claim `{claim.path}` = {claim.value}")
                    attempts = st.session_state["assistant_llm_attempts"].get(run.run_id)
                    if attempts:
                        st.caption(f"Provider attempts: {attempts}")
                if st.button("Render markdown report", key=f"report-{run.run_id}"):
                    result = orchestrator.export_run(
                        thesis_id=thesis_id,
                        conversation_id=conversation_id,
                        run=run,
                    )
                    if result.status != "completed":
                        st.error(
                            result.payload.get("error", {}).get(
                                "message", "Unable to render report."
                            )
                        )
                    else:
                        st.session_state["assistant_run_reports"][run.run_id] = result.payload[
                            "markdown_report"
                        ]
                report = st.session_state["assistant_run_reports"].get(run.run_id)
                if report:
                    st.markdown(report)
                    st.download_button(
                        "Download markdown report",
                        data=report,
                        file_name=f"assistant_run_{run.run_id[-8:]}.md",
                        mime="text/markdown",
                        key=f"download-report-{run.run_id}",
                    )
                if st.button("Build research artifact", key=f"artifact-{run.run_id}"):
                    result = orchestrator.export_run(
                        thesis_id=thesis_id,
                        conversation_id=conversation_id,
                        run=run,
                    )
                    if result.status != "completed":
                        st.error(
                            result.payload.get("error", {}).get(
                                "message", "Unable to build research artifact."
                            )
                        )
                    else:
                        st.session_state["assistant_run_artifacts"][run.run_id] = result.payload[
                            "artifact"
                        ]
                artifact = st.session_state["assistant_run_artifacts"].get(run.run_id)
                if artifact:
                    st.download_button(
                        "Download research artifact JSON",
                        data=json.dumps(artifact, indent=2, sort_keys=True),
                        file_name=f"assistant_run_{run.run_id[-8:]}.research.json",
                        mime="application/json",
                        key=f"download-artifact-{run.run_id}",
                    )
                if st.button("Restore bundle into research pages", key=f"handoff-{run.run_id}"):
                    try:
                        handoff_result = orchestrator.restore_run_bundle_to_session(
                            thesis_id=thesis_id,
                            run_id=run.run_id,
                            session_state=st.session_state,
                        )
                        st.success(
                            "Restored "
                            f"{handoff_result['restored_count']} research keys from "
                            f"run {run.run_id[-8:]}."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Unable to restore bundle: {exc}")

completed_runs = [
    run
    for run in runs
    if run.status == "completed"
    and isinstance(run.provenance, dict)
    and isinstance(run.provenance.get("bundle_path"), str)
    and isinstance(run.provenance.get("canonical_bundle_hash"), str)
    and bool(str(run.provenance.get("canonical_bundle_hash")).strip())
]
if len(completed_runs) >= 2:
    st.subheader("Compare completed runs")
    labels = {
        run.run_id: f"Run {run.run_id[-8:]} · spec v{run.spec_version}" for run in completed_runs
    }
    left_id = st.selectbox(
        "Left run", list(labels), format_func=labels.get, key=f"assistant_compare_left_{thesis_id}"
    )
    right_id = st.selectbox(
        "Right run",
        list(labels),
        format_func=labels.get,
        key=f"assistant_compare_right_{thesis_id}",
    )
    if st.button("Compare runs") and left_id != right_id:
        selected = {run.run_id: run for run in completed_runs}
        result = orchestrator.compare_completed_runs(
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            left_run=selected[left_id],
            right_run=selected[right_id],
        )
        if result.status != "completed":
            st.error(result.payload.get("error", {}).get("message", "Unable to compare runs."))
        else:
            st.session_state["assistant_run_comparisons"][thesis_id] = {
                "run_ids": result.payload["run_ids"],
                "comparison": result.payload["comparison"],
            }
            if result.payload.get("persistence_error"):
                st.warning(
                    "Comparison computed but could not be persisted: "
                    f"{result.payload['persistence_error']}"
                )
    comparison_state = st.session_state["assistant_run_comparisons"].get(thesis_id)
    if comparison_state and comparison_state.get("run_ids") == [left_id, right_id]:
        st.json(comparison_state["comparison"])

    st.subheader("Portfolio analysis")
    portfolio_ids = st.multiselect(
        "Completed runs",
        [run.run_id for run in completed_runs],
        format_func=labels.get,
        key=f"assistant_portfolio_runs_{thesis_id}",
    )
    instrument = st.selectbox(
        "Portfolio instrument",
        list(INSTRUMENTS),
        key=f"assistant_portfolio_instrument_{thesis_id}",
    )
    if st.button("Analyze portfolio") and len(portfolio_ids) >= 2:
        selected = {run.run_id: run for run in completed_runs}
        result = orchestrator.analyze_portfolio_runs(
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            runs=[selected[run_id] for run_id in portfolio_ids],
            instrument=instrument,
        )
        if result.status != "completed":
            st.error(result.payload.get("error", {}).get("message", "Unable to analyze portfolio."))
        else:
            st.json(
                {key: value for key, value in result.payload.items() if key != "resource_limits"}
            )

with st.expander("Saved comparisons"):
    for record in orchestrator.list_comparisons(thesis_id):
        st.json(record.to_dict())

st.subheader("Conversation audit")
conversations = orchestrator.list_conversations(thesis_id)
if not conversations:
    st.caption("No conversation transcript has been recorded yet.")
else:
    for conversation in reversed(conversations):
        with st.expander(f"Conversation {conversation.conversation_id[-8:]}"):
            st.json(
                {
                    "messages": list(conversation.messages),
                    "tool_transcript": list(conversation.tool_transcript),
                }
            )
