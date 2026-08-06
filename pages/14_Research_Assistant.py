"""AI Research Assistant thesis workspace.

Presentation-only Streamlit consumer of ``AssistantOrchestrator``. Default UX is
chat-first (thesis hub + discuss); Advanced draft/run controls and Debug JSON
are collapsed. The page never mutates the thesis repository, calls tools, reads
bundle bytes, or compiles RunSpecs directly.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

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
    is_draft_channel_message,
    load_llm_settings,
    load_product_help_settings,
    load_results_qa_settings,
)
from thesistester.assistant.llm_explainer import LLMEvidenceError
from thesistester.assistant.product_help import (
    PRODUCT_HELP_CHANNEL,
    HelpEvidenceError,
)
from thesistester.assistant.results_qa import RESULTS_QA_CHANNEL
from thesistester.assistant.voice.sidecar import (
    DEFAULT_SIDECAR_HOST,
    DEFAULT_SIDECAR_PORT,
    SidecarError,
    assert_localhost_bind,
)
from thesistester.assistant.voice.settings import (
    resolve_voice_settings,
    save_voice_ui_overrides,
)
from thesistester.assistant.voice.xai_realtime import (
    VoiceConfigurationError,
    VoiceProviderError,
)
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
    ASSISTANT_ADVANCED_EXPANDER_KEY,
    active_bundle_handoff,
    apply_consumed_classic_focus,
    build_confluence_level_options,
    force_results_qa_expanders_open,
    linked_run_expander_key,
    build_plan_review,
    build_provenance_card,
    chat_message_display_role,
    clear_failed_llm_run_explanation,
    coerce_multiselect_defaults,
    consume_assistant_flash,
    format_chat_message_body,
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
    coerce_window_label,
    option_index,
    options_with_current,
    options_with_currents,
    parse_json_choices,
    read_audio_input_bytes,
    require_run_bundle_hash,
    safe_float,
    safe_int,
    select_thesis,
    set_assistant_flash,
    spec_status_next_step,
    thesis_has_running_run,
)
from thesistester.classic_ledger import is_classic_ledger_run, ledger_run_label
from thesistester.classic_nav import (
    CLASSIC_FOCUS_CHANNEL_RESULTS_QA,
    clarification_target_page,
    consume_classic_focus,
    identity_badge_label,
    navigate_clarification_to_classic,
    open_exact_run_in_backtest,
    page_vs_run_identity_relation,
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


def _stage_voice_turn(turn) -> None:
    """Persist last PTT diagnostics + optional playback bytes (not store_audio)."""
    st.session_state["assistant_voice_last_turn"] = turn.to_public_dict()
    if turn.channel == "product_help":
        st.session_state["assistant_voice_help_session_id"] = turn.session_id
    if turn.audio_bytes:
        st.session_state["assistant_voice_playback"] = {
            "mime": turn.audio_mime,
            "bytes": turn.audio_bytes,
            "channel": turn.channel,
            "session_id": turn.session_id,
        }
    else:
        st.session_state["assistant_voice_playback"] = None


def _render_voice_last_turn(*, channel: str) -> None:
    last = st.session_state.get("assistant_voice_last_turn")
    if not isinstance(last, dict) or last.get("channel") != channel:
        return
    st.caption(
        f"Voice STT: {last.get('stt_text') or '—'} · path={last.get('answer_path')} · "
        f"grounded={last.get('grounded')} · trusted={last.get('trusted')}"
    )
    if last.get("speakable_text"):
        st.write(last["speakable_text"])
    if last.get("remediation") and not last.get("trusted"):
        st.info(str(last["remediation"]))
    playback = st.session_state.get("assistant_voice_playback")
    if (
        isinstance(playback, dict)
        and playback.get("channel") == channel
        and isinstance(playback.get("bytes"), (bytes, bytearray))
        and playback.get("bytes")
    ):
        st.audio(bytes(playback["bytes"]), format=str(playback.get("mime") or "audio/mpeg"))


def _sidecar_base_url() -> str:
    host = str(st.session_state.get("assistant_voice_sidecar_host") or DEFAULT_SIDECAR_HOST)
    try:
        host = assert_localhost_bind(host)
    except SidecarError:
        host = DEFAULT_SIDECAR_HOST
        st.session_state["assistant_voice_sidecar_host"] = host
    port = st.session_state.get("assistant_voice_sidecar_port") or DEFAULT_SIDECAR_PORT
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        port_i = DEFAULT_SIDECAR_PORT
    if port_i < 1 or port_i > 65535:
        port_i = DEFAULT_SIDECAR_PORT
    return f"http://{host}:{port_i}"


def _client_url_is_localhost(client_url: str) -> bool:
    """Refuse non-loopback sidecar client links (defense in depth)."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(client_url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "::1"}


def _register_realtime_session(
    *,
    run_id: str,
    expected_hash: str,
) -> dict | None:
    """POST a results realtime session to the localhost sidecar (no xAI key in page)."""
    payload = {
        "thesis_id": thesis_id,
        "run_id": run_id,
        "expected_hash": expected_hash,
        "conversation_id": conversation_id,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        f"{_sidecar_base_url()}/v1/sessions",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=5.0) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        st.error(
            "Unable to reach the localhost voice sidecar. Start it with "
            "`python -m thesistester.assistant.voice.sidecar` (binds 127.0.0.1 only). "
            f"Detail: {exc}"
        )
        return None
    if not isinstance(decoded, dict) or not decoded.get("session_id"):
        st.error("Sidecar returned an invalid session payload.")
        return None
    if any(key in decoded for key in ("api_key", "token", "client_secret", "authorization")):
        st.error("Refusing sidecar response that appears to include secrets.")
        return None
    client_url = decoded.get("client_url")
    if (
        isinstance(client_url, str)
        and client_url.strip()
        and not _client_url_is_localhost(client_url)
    ):
        st.error("Refusing non-localhost sidecar client_url.")
        return None
    return decoded


def _effective_voice_settings():
    """Tracked TOML + local Voice UI override (sidebar enable/mode)."""
    return resolve_voice_settings()


def _render_voice_controls() -> None:
    """Sidebar: toggle voice on/off and switch push-to-talk vs realtime."""
    current = _effective_voice_settings()
    st.session_state.setdefault("assistant_voice_ui_enabled", current.enabled)
    st.session_state.setdefault("assistant_voice_ui_mode", current.mode)
    # Keep widgets aligned with the override file when first shown this session.
    if "assistant_voice_ui_hydrated" not in st.session_state:
        st.session_state["assistant_voice_ui_enabled"] = current.enabled
        st.session_state["assistant_voice_ui_mode"] = current.mode
        st.session_state["assistant_voice_ui_hydrated"] = True

    st.subheader("Voice")
    st.caption(
        "Opt-in spoken Discuss/Help. Requires an xAI key (STT/TTS/sidecar) "
        "and an OpenAI key for channel answers. Tracked config stays "
        "default-off; choices save to a local override file."
    )
    enabled = st.toggle(
        "Enable voice",
        key="assistant_voice_ui_enabled",
        help="Shows mic controls in Discuss results and Help when on.",
    )
    mode = st.radio(
        "Mode",
        options=["push_to_talk", "realtime"],
        format_func=lambda value: (
            "Push-to-talk" if value == "push_to_talk" else "Realtime (sidecar)"
        ),
        key="assistant_voice_ui_mode",
        disabled=not enabled,
        horizontal=True,
    )
    if enabled != current.enabled or mode != current.mode:
        save_voice_ui_overrides(enabled=bool(enabled), mode=str(mode))
        st.rerun()
    if enabled and mode == "realtime":
        st.caption(
            "Realtime needs the localhost sidecar: `python -m thesistester.assistant.voice.sidecar`"
        )


def _run_voice_ptt(
    *,
    channel: str,
    audio_value,
    run_id: str | None = None,
    expected_hash: str | None = None,
    max_history_messages: int = 12,
) -> None:
    """STT → RQ channel / fallback → TTS via orchestrator façade (VA-4)."""
    audio_bytes = read_audio_input_bytes(audio_value)
    if not audio_bytes:
        st.error("Record a short push-to-talk clip before sending.")
        return
    openai_client = None
    try:
        openai_client = create_openai_client(load_llm_settings())
    except LLMConfigurationError:
        openai_client = None
    filename = "audio.wav"
    content_type = None
    name = getattr(audio_value, "name", None)
    if isinstance(name, str) and name.strip():
        filename = name.strip()
    ctype = getattr(audio_value, "type", None)
    if isinstance(ctype, str) and ctype.strip():
        content_type = ctype.strip()
    try:
        turn = orchestrator.handle_voice_ptt_turn(
            audio_bytes=audio_bytes,
            channel=channel,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            run_id=run_id,
            expected_hash=expected_hash,
            openai_client=openai_client,
            repo_root=Path(__file__).resolve().parents[1],
            max_history_messages=max_history_messages,
            filename=filename,
            content_type=content_type,
            settings=_effective_voice_settings(),
        )
    except (VoiceConfigurationError, VoiceProviderError, ValueError) as exc:
        st.error(f"Unable to complete voice turn: {exc}")
        return
    if channel == "results_qa" and run_id:
        sessions = st.session_state.setdefault("assistant_voice_results_sessions", {})
        if isinstance(sessions, dict):
            sessions[run_id] = turn.session_id
    _stage_voice_turn(turn)
    flash_level = "success" if turn.trusted else "info"
    flash_message = (
        "Voice reply ready."
        if turn.trusted
        else "Voice replied with remediation (ungrounded or fallback)."
    )
    set_assistant_flash(st.session_state, level=flash_level, message=flash_message)
    st.rerun()


init_assistant_session_state(st.session_state)
orchestrator = AssistantOrchestrator.for_local_workspace()

st.title("Research Assistant")
st.caption(
    "Manage and discuss research theses here. Run research via the normal page "
    "navigation (Data, Levels, Signals, Backtest, Grid, Validation, …). Optional "
    "Assistant draft → validate → confirm → run is under Advanced."
)
# Before the sidebar selectbox binds: if a classic Discuss deep-link is staged,
# align Assistant onto the classic active thesis (then picker). Prefer classic
# thesis over a stale assistant_selected_thesis_id so Record-and-discuss and
# discuss_run both land under the linked classic thesis.
_pending_focus_run = st.session_state.get("classic_focus_run_id")
if isinstance(_pending_focus_run, str) and _pending_focus_run.strip():
    _classic_thesis = st.session_state.get("classic_active_thesis_id")
    _assistant_thesis = st.session_state.get("assistant_selected_thesis_id")
    _target_thesis = (
        _classic_thesis.strip()
        if isinstance(_classic_thesis, str) and _classic_thesis.strip()
        else (
            _assistant_thesis.strip()
            if isinstance(_assistant_thesis, str) and _assistant_thesis.strip()
            else None
        )
    )
    if _target_thesis is not None:
        if st.session_state.get("assistant_selected_thesis_id") != _target_thesis:
            select_thesis(st.session_state, _target_thesis)
        st.session_state["assistant_thesis_picker"] = _target_thesis
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
    st.divider()
    _render_voice_controls()

thesis_id = st.session_state["assistant_selected_thesis_id"]
if not thesis_id:
    st.info("Create or select a thesis to begin.")
    st.stop()

_render_assistant_flash()

thesis = orchestrator.get_thesis(thesis_id)
st.subheader(thesis.name)
st.caption(f"Revision {thesis.revision} · {thesis.lifecycle}")
_classic_focus = consume_classic_focus(st.session_state)
focus_run_id = _classic_focus.get("run_id")
focus_channel = _classic_focus.get("channel")
# RQ-4: results_qa stages a sticky Advanced → Linked-run expansion that survives
# later st.rerun() (classic focus keys are one-shot). Absent/None channel keeps
# legacy info-banner-only behavior for this render only.
one_shot_results_qa = (
    focus_channel == CLASSIC_FOCUS_CHANNEL_RESULTS_QA
    and isinstance(focus_run_id, str)
    and bool(focus_run_id)
)
if focus_run_id and not one_shot_results_qa:
    st.info(f"Focused classic-discussed run: …{focus_run_id[-8:]}")
expand_results_qa_focus, expand_focus_run_id = apply_consumed_classic_focus(
    st.session_state,
    run_id=focus_run_id if isinstance(focus_run_id, str) else None,
    channel=focus_channel if isinstance(focus_channel, str) else None,
)
# Keyed expanders (Streamlit >= 1.55): force-open once on fresh results_qa
# consume so a previously collapsed Advanced cannot hide Discuss results.
force_results_qa_expanders_open(
    st.session_state,
    run_id=expand_focus_run_id,
)

handoff = active_bundle_handoff(st.session_state, thesis_id=thesis_id)
if handoff is not None:
    st.caption(
        "Active handoff: "
        f"run {str(handoff['run_id'])[-8:]} · "
        f"restored {handoff.get('restored_count', 0)} session keys."
    )
    try:
        handoff_run = orchestrator.get_run(thesis_id, str(handoff["run_id"]))
        relation = page_vs_run_identity_relation(st.session_state, handoff_run)
        st.caption(f"Identity vs handoff run: **{identity_badge_label(relation)}** (`{relation}`)")
    except Exception:
        st.caption("Identity vs handoff run: **identity unavailable**")
    if st.button(
        "Open exact run in Backtest",
        key="assistant_open_handoff_backtest",
        type="primary",
    ):
        try:
            open_exact_run_in_backtest(
                st.session_state,
                thesis_id=thesis_id,
                run_id=str(handoff["run_id"]),
                orchestrator=orchestrator,
            )
            st.switch_page("pages/7_Backtest.py")
        except Exception as exc:
            st.error(f"Unable to open exact run: {exc}")
with st.expander("Manage thesis", expanded=False):
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
        if message.get("role") == "user" and is_draft_channel_message(message)
    )
    for message in reversed(active_conversation.messages):
        if (
            is_draft_channel_message(message)
            and message.get("role") == "assistant"
            and isinstance(message.get("choices"), dict)
        ):
            st.session_state["assistant_draft_choices"] = message["choices"]
            break
    # Help draft/widget are conversation-local presentation staging — clear on
    # conversation switch so an unsent prior Help question cannot leak into a
    # different conversation's Help thread.
    st.session_state["assistant_product_help_draft"] = ""
    st.session_state.pop("product-help-input", None)
    st.session_state.pop("assistant_clear_product_help_input", None)
    st.session_state["assistant_hydrated_conversation_id"] = conversation_id
    invalidate_validation(st.session_state)

st.subheader("Assistant chat")
st.caption(
    "Thesis drafting only — extracts research choices and clarification questions. "
    "It does not discuss completed backtests/grids/validation or product docs. "
    "For run narratives, open Advanced → Linked runs → Discuss results. "
    "For feature/how-it-works questions, use Help / how it works below."
)
for message in active_conversation.messages:
    display_role = chat_message_display_role(message)
    if display_role is None:
        continue
    body = format_chat_message_body(message)
    if not body:
        continue
    with st.chat_message(display_role):
        st.write(body)

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
            if message.get("role") == "user" and is_draft_channel_message(message)
        )
        st.session_state["assistant_draft_choices"] = draft.normalized_run_spec
        invalidate_validation(st.session_state)
        if draft.unresolved_assumptions:
            set_assistant_flash(
                st.session_state,
                level="info",
                message=(
                    "Chat updated with clarification questions above. "
                    "This input drafts thesis choices — use Explain run or "
                    "Discuss results under Advanced → Linked runs for test results."
                ),
            )
        else:
            set_assistant_flash(
                st.session_state,
                level="success",
                message=(
                    "Chat updated draft choices. Open Advanced to review Structured "
                    "execution controls, then Draft research plan."
                ),
            )
        st.rerun()
    except (LLMConfigurationError, LLMProviderError) as exc:
        st.error(str(exc))

help_settings = load_product_help_settings()
if help_settings.enabled:
    with st.expander("Help / how it works", expanded=False):
        st.caption(
            "Documentation-grounded product help (USER_GUIDE-backed allowlisted "
            "docs + capability registry). Ask how-tos such as import data, "
            "Setup Builder, grid ranking, validation, or Help vs Discuss. "
            "Not a second results explainer — use Discuss results for "
            "completed-run metrics."
        )
        help_thread = [
            message
            for message in active_conversation.messages
            if message.get("channel") == PRODUCT_HELP_CHANNEL
            and str(message.get("role") or "").strip().lower()
            in {"user", "human", "assistant", "ai"}
        ]
        for message in help_thread:
            role = str(message.get("role") or "").strip().lower()
            display = "user" if role in {"user", "human"} else "assistant"
            body = str(message.get("content") or "").strip()
            if not body:
                continue
            with st.chat_message(display):
                st.write(body)
        help_input_key = "product-help-input"
        # Clear only before the widget is bound — Streamlit forbids writing a
        # widget key after st.text_input(..., key=...) in the same run.
        if st.session_state.pop("assistant_clear_product_help_input", False):
            st.session_state[help_input_key] = ""
            st.session_state["assistant_product_help_draft"] = ""
        if help_input_key not in st.session_state:
            st.session_state[help_input_key] = str(
                st.session_state.get("assistant_product_help_draft", "")
            )
        st.text_input(
            "Ask how ThesisTester works",
            key=help_input_key,
            placeholder="e.g. How does grid ranking work?",
        )
        st.session_state["assistant_product_help_draft"] = str(
            st.session_state.get(help_input_key, "")
        )
        if st.button("Send help question", key="product-help-send"):
            question = str(st.session_state.get(help_input_key, "")).strip()
            if not question:
                st.error("Enter a product or workflow question.")
            else:
                try:
                    client = create_openai_client(load_llm_settings())
                    result = orchestrator.handle_help_turn(
                        client,
                        thesis_id=thesis_id,
                        message=question,
                        conversation_id=conversation_id,
                        max_history_messages=help_settings.max_history_messages,
                        max_corpus_chars=help_settings.max_corpus_chars,
                        repo_root=Path(__file__).resolve().parents[1],
                    )
                    if result.status != "completed":
                        raise ValueError(
                            result.payload.get("error", {}).get(
                                "message", "Unable to answer this help question."
                            )
                        )
                    st.session_state["assistant_clear_product_help_input"] = True
                    st.session_state["assistant_product_help_draft"] = ""
                    flash_level = "info" if result.payload.get("remediation") else "success"
                    flash_message = (
                        "Help redirected to Discuss results for run performance."
                        if result.payload.get("remediation")
                        else "Help answer updated."
                    )
                    set_assistant_flash(
                        st.session_state,
                        level=flash_level,
                        message=flash_message,
                    )
                    st.rerun()
                except (
                    LLMConfigurationError,
                    LLMProviderError,
                    HelpEvidenceError,
                    ValueError,
                ) as exc:
                    st.error(f"Unable to answer help question: {exc}")
        voice_settings = _effective_voice_settings()
        if voice_settings.enabled:
            st.markdown("**Voice help (push-to-talk)**")
            st.caption(
                "Spoken product Help over the same corpus path. Requires an "
                "xAI key for STT/TTS and an OpenAI key for Help answers. "
                "Mic is disabled while a research run is in progress."
            )
            help_voice_blocked = thesis_has_running_run(orchestrator.list_runs(thesis_id))
            if help_voice_blocked:
                st.warning("Voice is paused while a research run is running.")
            else:
                help_audio = st.audio_input(
                    "Ask Help by voice",
                    key="voice-help-audio",
                )
                if st.button("Send voice help question", key="voice-help-send"):
                    _run_voice_ptt(
                        channel=PRODUCT_HELP_CHANNEL,
                        audio_value=help_audio,
                        max_history_messages=help_settings.max_history_messages,
                    )
            _render_voice_last_turn(channel=PRODUCT_HELP_CHANNEL)


with st.expander(
    "Advanced: draft, runs & compare",
    expanded=expand_results_qa_focus,
    key=ASSISTANT_ADVANCED_EXPANDER_KEY,
    on_change="rerun",
):
    st.caption(
        "Optional Assistant path. Classic pages remain primary via normal navigation. "
        "Validate → Confirm → Run stays confirmation- and schema-gated."
    )
    with st.expander("How to start a research run", expanded=False):
        for index, step in enumerate(RESEARCH_WORKFLOW_STEPS, start=1):
            st.write(f"{index}. {step}")
        st.caption(
            "Apply controls never start compute. Only Run confirmed research on a Confirmed "
            "specification version executes the pipeline."
        )

    current = st.session_state["assistant_draft_choices"]
    dataset = current.get("dataset") if isinstance(current.get("dataset"), dict) else {}
    backtest = current.get("backtest") if isinstance(current.get("backtest"), dict) else {}
    setup = current.get("setup") if isinstance(current.get("setup"), dict) else {}
    levels = current.get("levels") if isinstance(current.get("levels"), dict) else {}
    validation = current.get("validation") if isinstance(current.get("validation"), dict) else {}
    grid = current.get("grid") if isinstance(current.get("grid"), dict) else {}
    walk_forward = (
        current.get("walk_forward") if isinstance(current.get("walk_forward"), dict) else {}
    )

    with st.expander("Structured execution controls", expanded=False):
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
            draft_source_timezone = str(
                dataset.get("source_timezone") or "America/New_York"
            ).strip()
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
            draft_session_timezone = str(
                backtest.get("session_timezone") or "America/New_York"
            ).strip()
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

    with st.expander("Structured setup and confluence controls", expanded=False):
        with st.form(f"assistant_setup_{thesis_id}_{_fingerprint(setup)}"):
            setup_name = st.text_input("Setup name", value=str(setup.get("name") or thesis.name))
            description = st.text_input(
                "Setup description", value=str(setup.get("description") or "")
            )
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
            naked_only = st.checkbox(
                "Naked levels only", value=bool(setup.get("naked_only", False))
            )
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
                "Enable developing session VWAPs (dVWAP_RTH + dVWAP)",
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
            for value in list(levels.get("sma_lengths") or []) + list(
                levels.get("ema_lengths") or []
            ):
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
                label
                for label in (
                    coerce_window_label(value) for value in (levels.get("vwap_windows") or [])
                )
                if label
            ]
            vwap_window_options = options_with_currents(VWAP_WINDOW_OPTIONS, draft_vwap_windows)
            vwap_windows = st.multiselect(
                "VWAP windows",
                options=vwap_window_options,
                default=coerce_multiselect_defaults(draft_vwap_windows, vwap_window_options),
                help="Same searchable window catalog as the Levels page; draft values outside the catalog stay selectable.",
            )
            draft_poc_windows = [
                label
                for label in (
                    coerce_window_label(value) for value in (levels.get("poc_windows") or [])
                )
                if label
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
                value=", ".join(
                    str(v) for v in (grid.get("take_profit_ticks_values") or [8, 16, 24])
                ),
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
            enabled = st.checkbox(
                "Enable walk-forward", value=bool(walk_forward.get("enabled", False))
            )
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
                value=", ".join(
                    str(v) for v in (walk_forward.get("stop_loss_ticks_values") or [8])
                ),
            )
            wfa_targets = st.text_input(
                "Walk-forward target ticks",
                value=", ".join(
                    str(v) for v in (walk_forward.get("take_profit_ticks_values") or [16])
                ),
            )
            matrix_enabled = False
            matrix_train_raw = ", ".join(
                str(v) for v in (matrix.get("train_session_values") or [20, 40])
            )
            matrix_test_raw = ", ".join(
                str(v) for v in (matrix.get("test_session_values") or [5, 10])
            )
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
                # Hub-flash: Advanced defaults closed after rerun.
                set_assistant_flash(st.session_state, level="error", message=str(exc))
                st.rerun()
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
                set_assistant_flash(
                    st.session_state,
                    level="error",
                    message=str(
                        validation_result.payload.get("error", {}).get(
                            "message", "Validation failed."
                        )
                    ),
                )
            else:
                st.session_state["assistant_validated_run_spec"] = {
                    "choices": validation_result.payload["choices"],
                    "spec": validation_result.payload["spec"],
                }
                set_assistant_flash(
                    st.session_state,
                    level="success",
                    message=(
                        "Executable RunSpec is valid. Open Advanced → Plan review and "
                        "Confirm validated RunSpec when clarifications are clear."
                    ),
                )
            st.rerun()

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
        for index, item in enumerate(plan["unresolved_assumptions"]):
            st.write(f"- {item}")
            target = clarification_target_page(str(item))
            if target and st.button(
                f"Open on classic page ({target.split('/')[-1]})",
                key=f"clarify-nav-plan-{index}",
            ):
                try:
                    navigate_clarification_to_classic(st.session_state, clarification=str(item))
                    st.switch_page(target)
                except ValueError as exc:
                    st.error(str(exc))
    if plan["validated_spec"] is not None:
        with st.expander("Validated executable RunSpec", expanded=False):
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
            with st.expander("Debug: specification JSON", expanded=False):
                st.json(spec.normalized_run_spec)
            if spec.unresolved_assumptions:
                st.warning("Clarifications required")
                for assumption_index, assumption in enumerate(spec.unresolved_assumptions):
                    st.write(f"- {assumption}")
                    target = clarification_target_page(str(assumption))
                    if target and st.button(
                        f"Open on classic page ({target.split('/')[-1]})",
                        key=f"clarify-nav-spec-{spec.version}-{assumption_index}",
                    ):
                        try:
                            navigate_clarification_to_classic(
                                st.session_state, clarification=str(assumption)
                            )
                            st.switch_page(target)
                        except ValueError as exc:
                            st.error(str(exc))
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

    st.subheader("Linked research runs")
    st.caption(
        "Thesis-recorded runs only. Classic exploration without research mode is never "
        "listed. CAI-7 ledger attempts (`all_executions`) appear alongside manual "
        "Record-and-discuss and Assistant executions."
    )
    runs = orchestrator.list_runs(thesis_id)
    if not runs:
        st.info("No research runs are recorded for this thesis yet.")
    else:
        for run in reversed(runs):
            provenance_card = build_provenance_card(run.to_dict())
            kind = ledger_run_label(run)
            title = f"Run {run.run_id[-8:]} · {run.status} · {kind}"
            run_focus_expanded = bool(expand_results_qa_focus and expand_focus_run_id == run.run_id)
            with st.expander(
                title,
                expanded=run_focus_expanded,
                key=linked_run_expander_key(run.run_id),
                on_change="rerun",
            ):
                if is_classic_ledger_run(run):
                    st.caption(
                        "Classic execution ledger attempt (opt-in all_executions). "
                        "Failed/cancelled rows are retained for statistically honest history."
                    )
                st.caption(
                    f"Specification v{run.spec_version} · revision {run.revision} · "
                    f"origin `{provenance_card.get('origin_page') or '—'}` · "
                    f"config `{str(provenance_card.get('classic_config_hash') or '—')[:16]}` · "
                    f"bundle `{str(provenance_card.get('canonical_bundle_hash') or '—')[:16]}`"
                )
                if run.status == "running" and st.button("Cancel run", key=f"cancel-{run.run_id}"):
                    cancelled = orchestrator.cancel_run(
                        thesis_id=thesis_id,
                        run_id=run.run_id,
                        conversation_id=conversation_id,
                    )
                    if cancelled.status == "cancelled":
                        set_assistant_flash(
                            st.session_state,
                            level="warning",
                            message="Research run cancelled.",
                        )
                    else:
                        set_assistant_flash(
                            st.session_state,
                            level="error",
                            message=str(
                                cancelled.payload.get("error", {}).get(
                                    "message",
                                    "Unable to cancel this run because it is no longer running.",
                                )
                            ),
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
                            st.session_state["assistant_run_explanations"][run.run_id] = (
                                result.payload["explanation"]
                            )
                    explanation = st.session_state["assistant_run_explanations"].get(run.run_id)
                    if explanation:
                        st.write(explanation)
                    with st.expander("Page summaries (JSON)", expanded=False):
                        st.caption("Page summaries (bounded JSON; charts stay on classic pages)")
                        summary_caps = (
                            ("Levels", "LEVELS.inspect_and_chart"),
                            ("Signals", "SIGNALS.inspect_and_chart"),
                            ("Backtest", "BACKTEST.inspect_results"),
                            ("Grid", "GRID.inspect_results"),
                            ("Validation", "VALIDATION.inspect_results"),
                        )
                        summary_cols = st.columns(len(summary_caps))
                        for col, (label, capability_id) in zip(
                            summary_cols, summary_caps, strict=True
                        ):
                            with col:
                                if st.button(label, key=f"page-sum-{capability_id}-{run.run_id}"):
                                    try:
                                        result = orchestrator.inspect_run_page_summary(
                                            thesis_id=thesis_id,
                                            conversation_id=conversation_id,
                                            run=run,
                                            capability_id=capability_id,
                                        )
                                    except ValueError as exc:
                                        st.error(str(exc))
                                    else:
                                        if result.status != "completed":
                                            st.error(
                                                result.payload.get("error", {}).get(
                                                    "message", "Unable to load page summary."
                                                )
                                            )
                                        else:
                                            st.session_state.setdefault(
                                                "assistant_page_summaries", {}
                                            )[f"{run.run_id}:{capability_id}"] = result.payload
                        for label, capability_id in summary_caps:
                            cached = st.session_state.get("assistant_page_summaries", {}).get(
                                f"{run.run_id}:{capability_id}"
                            )
                            if cached:
                                with st.expander(f"{label} summary", expanded=False):
                                    st.json(cached)
                    with st.expander("Propose classic page change", expanded=False):
                        propose_target = st.selectbox(
                            "Target page",
                            options=[
                                "pages/7_Backtest.py",
                                "pages/3_Setup_Builder.py",
                            ],
                            key=f"propose-target-{run.run_id}",
                        )
                        propose_note = st.text_input(
                            "Proposal note",
                            value="Review suggested settings from this run.",
                            key=f"propose-note-{run.run_id}",
                        )
                        if propose_target == "pages/7_Backtest.py":
                            sl = st.number_input(
                                "Proposed stop loss (ticks)",
                                min_value=1.0,
                                value=8.0,
                                key=f"propose-sl-{run.run_id}",
                            )
                            tp = st.number_input(
                                "Proposed take profit (ticks)",
                                min_value=1.0,
                                value=16.0,
                                key=f"propose-tp-{run.run_id}",
                            )
                            draft_patch = {
                                "stop_loss_ticks": float(sl),
                                "take_profit_ticks": float(tp),
                            }
                            evidence_paths = [
                                "results.backtest_page_summary.kpis.trade_count",
                                "results.grid_summary.best_cell.stop_loss_ticks",
                            ]
                        else:
                            tol = st.number_input(
                                "Proposed tolerance ticks",
                                min_value=0.0,
                                value=4.0,
                                key=f"propose-tol-{run.run_id}",
                            )
                            draft_patch = {"tolerance_ticks": float(tol)}
                            evidence_paths = [
                                "results.signals_summary.signal_count",
                                "assumptions.setup_config.tolerance_ticks",
                            ]
                        if st.button(
                            "Stage proposal for classic review",
                            key=f"propose-stage-{run.run_id}",
                            type="primary",
                        ):
                            try:
                                result = orchestrator.propose_classic_page_change(
                                    thesis_id=thesis_id,
                                    conversation_id=conversation_id,
                                    target_page=propose_target,
                                    draft_patch=draft_patch,
                                    note=propose_note,
                                    evidence_paths=evidence_paths,
                                    session_state=st.session_state,
                                    navigate=True,
                                )
                                if result.status != "completed":
                                    st.error(
                                        result.payload.get("error", {}).get(
                                            "message", "Unable to stage proposal."
                                        )
                                    )
                                else:
                                    st.success(
                                        "Proposal staged. Open the owning classic page and Apply."
                                    )
                                    if st.session_state.get("classic_pending_navigation"):
                                        st.switch_page(
                                            st.session_state["classic_pending_navigation"]
                                        )
                            except Exception as exc:
                                st.error(f"Unable to stage proposal: {exc}")
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
                            st.session_state["assistant_llm_attempts"][run.run_id] = (
                                result.payload.get("provider_attempts")
                            )
                        except (
                            LLMConfigurationError,
                            LLMProviderError,
                            LLMEvidenceError,
                            ValueError,
                        ) as exc:
                            clear_failed_llm_run_explanation(st.session_state, run.run_id)
                            st.error(f"Unable to generate AI explanation: {exc}")
                    llm_explanation = st.session_state["assistant_llm_run_explanations"].get(
                        run.run_id
                    )
                    if llm_explanation:
                        st.write(llm_explanation.summary)
                        for caveat in llm_explanation.caveats:
                            st.caption(f"Caveat: {caveat}")
                        for claim in getattr(llm_explanation, "claims", ()) or ():
                            st.caption(f"Claim `{claim.path}` = {claim.value}")
                        attempts = st.session_state["assistant_llm_attempts"].get(run.run_id)
                        if attempts:
                            st.caption(f"Provider attempts: {attempts}")
                    results_qa_settings = load_results_qa_settings()
                    if results_qa_settings.enabled:
                        st.markdown("**Discuss results**")
                        st.caption(
                            "Multi-turn Q&A on this completed run only. "
                            "Grounded in hash-verified evidence — not thesis drafting."
                        )
                        results_thread = [
                            message
                            for message in active_conversation.messages
                            if message.get("channel") == RESULTS_QA_CHANNEL
                            and message.get("run_id") == run.run_id
                            and str(message.get("role") or "").strip().lower()
                            in {"user", "human", "assistant", "ai"}
                        ]
                        for message in results_thread:
                            role = str(message.get("role") or "").strip().lower()
                            display = "user" if role in {"user", "human"} else "assistant"
                            body = str(message.get("content") or "").strip()
                            if not body:
                                continue
                            with st.chat_message(display):
                                # Path-cited claims are embedded in persisted
                                # content via format_results_qa_reply_content.
                                st.write(body)
                        input_key = f"results-qa-input-{run.run_id}"
                        clear_flag = f"assistant_clear_{input_key}"
                        drafts = st.session_state.setdefault("assistant_results_qa_drafts", {})
                        # Clear only before the widget is bound — same rule as Help.
                        if st.session_state.pop(clear_flag, False):
                            st.session_state[input_key] = ""
                            drafts[run.run_id] = ""
                        if input_key not in st.session_state:
                            st.session_state[input_key] = str(drafts.get(run.run_id, ""))
                        st.text_input(
                            "Ask about this run",
                            key=input_key,
                            placeholder="e.g. What was expectancy? Best SL/TP?",
                        )
                        drafts[run.run_id] = str(st.session_state.get(input_key, ""))
                        if st.button(
                            "Send results question",
                            key=f"results-qa-send-{run.run_id}",
                        ):
                            question = str(st.session_state.get(input_key, "")).strip()
                            if not question:
                                st.error("Enter a question about this run.")
                            else:
                                try:
                                    client = create_openai_client(load_llm_settings())
                                    result = orchestrator.handle_results_turn(
                                        client,
                                        thesis_id=thesis_id,
                                        run_id=run.run_id,
                                        message=question,
                                        conversation_id=conversation_id,
                                        max_history_messages=(
                                            results_qa_settings.max_history_messages
                                        ),
                                    )
                                    if result.status != "completed":
                                        raise ValueError(
                                            result.payload.get("error", {}).get(
                                                "message",
                                                "Unable to discuss this run.",
                                            )
                                        )
                                    st.session_state[clear_flag] = True
                                    drafts[run.run_id] = ""
                                    set_assistant_flash(
                                        st.session_state,
                                        level="success",
                                        message="Results discussion updated.",
                                    )
                                    st.rerun()
                                except (
                                    LLMConfigurationError,
                                    LLMProviderError,
                                    LLMEvidenceError,
                                    ValueError,
                                ) as exc:
                                    st.error(f"Unable to discuss results: {exc}")
                        voice_settings = _effective_voice_settings()
                        if voice_settings.enabled:
                            st.markdown("**Voice discuss (push-to-talk)**")
                            st.caption(
                                "Spoken Discuss results for this completed run. "
                                "Requires an xAI key for STT/TTS; OpenAI powers "
                                "the primary channel path (VA-3 tool fallback if missing)."
                            )
                            results_voice_blocked = thesis_has_running_run(runs)
                            if results_voice_blocked:
                                st.warning("Voice is paused while a research run is running.")
                            else:
                                results_audio = st.audio_input(
                                    "Ask about this run by voice",
                                    key=f"voice-results-audio-{run.run_id}",
                                )
                                if st.button(
                                    "Send voice results question",
                                    key=f"voice-results-send-{run.run_id}",
                                ):
                                    try:
                                        expected_hash = (
                                            require_run_bundle_hash(run.provenance)
                                            if isinstance(run.provenance, dict)
                                            else None
                                        )
                                    except ValueError as exc:
                                        st.error(str(exc))
                                        expected_hash = None
                                    if expected_hash:
                                        _run_voice_ptt(
                                            channel=RESULTS_QA_CHANNEL,
                                            audio_value=results_audio,
                                            run_id=run.run_id,
                                            expected_hash=expected_hash,
                                            max_history_messages=(
                                                results_qa_settings.max_history_messages
                                            ),
                                        )
                            last = st.session_state.get("assistant_voice_last_turn")
                            if (
                                isinstance(last, dict)
                                and last.get("channel") == RESULTS_QA_CHANNEL
                                and st.session_state.get(
                                    "assistant_voice_results_sessions", {}
                                ).get(run.run_id)
                                == last.get("session_id")
                            ):
                                _render_voice_last_turn(channel=RESULTS_QA_CHANNEL)
                            # VA-5 realtime duplex (sidecar). PTT remains the fallback.
                            if voice_settings.mode == "realtime":
                                st.markdown("**Voice discuss (realtime)**")
                                st.caption(
                                    "Full-duplex review via the localhost sidecar "
                                    "(browser ↔ sidecar ↔ xAI). The page never opens "
                                    "the xAI socket or embeds the API key. Help realtime "
                                    "is deferred — use push-to-talk Help."
                                )
                                st.session_state.setdefault(
                                    "assistant_voice_sidecar_host", DEFAULT_SIDECAR_HOST
                                )
                                st.session_state.setdefault(
                                    "assistant_voice_sidecar_port", DEFAULT_SIDECAR_PORT
                                )
                                st.text_input(
                                    "Sidecar host",
                                    key="assistant_voice_sidecar_host",
                                    disabled=True,
                                    help="Realtime sidecar must bind 127.0.0.1 only.",
                                )
                                st.number_input(
                                    "Sidecar port",
                                    min_value=1,
                                    max_value=65535,
                                    key="assistant_voice_sidecar_port",
                                )
                                if results_voice_blocked:
                                    st.warning(
                                        "Realtime voice is paused while a research run is running."
                                    )
                                elif st.button(
                                    "Start realtime voice session",
                                    key=f"voice-realtime-start-{run.run_id}",
                                ):
                                    try:
                                        expected_hash = (
                                            require_run_bundle_hash(run.provenance)
                                            if isinstance(run.provenance, dict)
                                            else None
                                        )
                                    except ValueError as exc:
                                        st.error(str(exc))
                                        expected_hash = None
                                    if expected_hash:
                                        registered = _register_realtime_session(
                                            run_id=run.run_id,
                                            expected_hash=expected_hash,
                                        )
                                        if registered is not None:
                                            st.session_state[
                                                f"assistant_voice_realtime_{run.run_id}"
                                            ] = registered
                                            set_assistant_flash(
                                                st.session_state,
                                                level="success",
                                                message="Realtime voice session registered.",
                                            )
                                            st.rerun()
                                registered = st.session_state.get(
                                    f"assistant_voice_realtime_{run.run_id}"
                                )
                                if isinstance(registered, dict) and registered.get("client_url"):
                                    client_url = str(registered["client_url"])
                                    if not _client_url_is_localhost(client_url):
                                        st.error("Stored realtime client_url is not localhost.")
                                    else:
                                        st.markdown(f"[Open realtime voice client]({client_url})")
                                        st.caption(
                                            f"session `{registered.get('session_id', '')}` · "
                                            "close the client tab to end/flush the session."
                                        )
                                        try:
                                            import streamlit.components.v1 as components

                                            components.iframe(client_url, height=280)
                                        except Exception:
                                            pass
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
                            st.session_state["assistant_run_artifacts"][run.run_id] = (
                                result.payload["artifact"]
                            )
                    artifact = st.session_state["assistant_run_artifacts"].get(run.run_id)
                    if artifact:
                        st.download_button(
                            "Download research artifact JSON",
                            data=json.dumps(artifact, indent=2, sort_keys=True),
                            file_name=f"assistant_run_{run.run_id[-8:]}.research.json",
                            mime="application/json",
                            key=f"download-artifact-{run.run_id}",
                        )
                    try:
                        relation = page_vs_run_identity_relation(st.session_state, run)
                        st.caption(
                            f"Identity vs session: **{identity_badge_label(relation)}** (`{relation}`)"
                        )
                    except Exception:
                        st.caption("Identity vs session: **identity unavailable**")
                    open_col, restore_col = st.columns(2)
                    with open_col:
                        if st.button(
                            "Open exact run in Backtest",
                            key=f"open-backtest-{run.run_id}",
                        ):
                            try:
                                open_exact_run_in_backtest(
                                    st.session_state,
                                    thesis_id=thesis_id,
                                    run_id=run.run_id,
                                    orchestrator=orchestrator,
                                )
                                st.switch_page("pages/7_Backtest.py")
                            except Exception as exc:
                                st.error(f"Unable to open exact run: {exc}")
                    with restore_col:
                        if st.button(
                            "Restore bundle into research pages",
                            key=f"handoff-{run.run_id}",
                        ):
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
                with st.expander("Debug: provenance", expanded=False):
                    st.json(provenance_card)

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
            run.run_id: f"Run {run.run_id[-8:]} · spec v{run.spec_version}"
            for run in completed_runs
        }
        left_id = st.selectbox(
            "Left run",
            list(labels),
            format_func=labels.get,
            key=f"assistant_compare_left_{thesis_id}",
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
                # Only clear cache that would re-render as success for this pair.
                cached = st.session_state["assistant_run_comparisons"].get(thesis_id)
                if cached and cached.get("run_ids") == [left_id, right_id]:
                    st.session_state["assistant_run_comparisons"].pop(thesis_id, None)
                set_assistant_flash(
                    st.session_state,
                    level="error",
                    message=str(
                        result.payload.get("error", {}).get("message", "Unable to compare runs.")
                    ),
                )
            else:
                st.session_state["assistant_run_comparisons"][thesis_id] = {
                    "run_ids": result.payload["run_ids"],
                    "comparison": result.payload["comparison"],
                }
                if result.payload.get("persistence_error"):
                    set_assistant_flash(
                        st.session_state,
                        level="warning",
                        message=(
                            "Comparison computed but could not be persisted: "
                            f"{result.payload['persistence_error']}. "
                            "Open Advanced → Compare completed runs for conclusions."
                        ),
                    )
                else:
                    set_assistant_flash(
                        st.session_state,
                        level="success",
                        message=(
                            "Comparison ready. Open Advanced → Compare completed runs "
                            "for conclusions."
                        ),
                    )
            st.rerun()
        comparison_state = st.session_state["assistant_run_comparisons"].get(thesis_id)
        if comparison_state and comparison_state.get("run_ids") == [left_id, right_id]:
            comparison = comparison_state.get("comparison")
            # Keep conclusions visible — raw JSON stays under Debug so Compare
            # does not look like a no-op inside the collapsed Advanced section.
            st.success("Comparison ready.")
            if isinstance(comparison, dict):
                conclusions = comparison.get("conclusions")
                if isinstance(conclusions, list) and conclusions:
                    st.markdown("**Conclusions**")
                    for item in conclusions:
                        text = str(item).strip()
                        if text:
                            st.write(f"- {text}")
                warnings = comparison.get("warnings")
                if isinstance(warnings, list) and warnings:
                    st.markdown("**Warnings**")
                    for item in warnings:
                        text = str(item).strip()
                        if text:
                            st.caption(text)
            with st.expander("Debug: comparison JSON", expanded=False):
                st.json(comparison)

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
                # Only clear cache that would re-render as success for this selection.
                cached = st.session_state["assistant_portfolio_analyses"].get(thesis_id)
                if (
                    cached
                    and cached.get("run_ids") == list(portfolio_ids)
                    and cached.get("instrument") == instrument
                ):
                    st.session_state["assistant_portfolio_analyses"].pop(thesis_id, None)
                set_assistant_flash(
                    st.session_state,
                    level="error",
                    message=str(
                        result.payload.get("error", {}).get(
                            "message", "Unable to analyze portfolio."
                        )
                    ),
                )
            else:
                payload_view = {
                    key: value for key, value in result.payload.items() if key != "resource_limits"
                }
                st.session_state["assistant_portfolio_analyses"][thesis_id] = {
                    "run_ids": list(portfolio_ids),
                    "instrument": instrument,
                    "payload": payload_view,
                }
                set_assistant_flash(
                    st.session_state,
                    level="success",
                    message=(
                        f"Portfolio analysis ready for {len(portfolio_ids)} runs "
                        f"({instrument}). Open Advanced → Portfolio analysis for the summary."
                    ),
                )
            st.rerun()
        portfolio_state = st.session_state["assistant_portfolio_analyses"].get(thesis_id)
        if (
            portfolio_state
            and portfolio_state.get("run_ids") == list(portfolio_ids)
            and portfolio_state.get("instrument") == instrument
        ):
            payload_view = portfolio_state.get("payload")
            # Persist + re-render outside the button handler so later hub
            # reruns (chat, thesis sidebar) do not erase portfolio feedback.
            st.success(f"Portfolio analysis ready for {len(portfolio_ids)} runs ({instrument}).")
            if isinstance(payload_view, dict):
                summary = payload_view.get("portfolio")
                if summary is None:
                    summary = payload_view.get("portfolio_summary")
                if isinstance(summary, dict) and summary:
                    st.markdown("**Portfolio summary**")
                    for key, value in summary.items():
                        st.write(f"- `{key}`: {value}")
                with st.expander("Debug: portfolio JSON", expanded=False):
                    st.json(payload_view)

    with st.expander("Saved comparisons", expanded=False):
        for record in orchestrator.list_comparisons(thesis_id):
            with st.expander(f"Debug: comparison {record.comparison_id[-8:]}", expanded=False):
                st.json(record.to_dict())


with st.expander("Debug: raw JSON & conversation audit", expanded=False):
    st.caption(
        "Raw transcripts and JSON for audit only — not the chat UI. Tool lines "
        "(`completed BUNDLE.import`, `failed PIPELINE.run_experiment`) are lifecycle "
        "audits, not agent answers."
    )
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

    st.markdown("##### Conversation audit")
    st.caption(
        "Append-only transcript (user/assistant/tool messages and tool_transcript). "
        "Readable replies stay in Assistant chat above."
    )
    conversations = orchestrator.list_conversations(thesis_id)
    if not conversations:
        st.caption("No conversation transcript has been recorded yet.")
    else:
        for conversation in reversed(conversations):
            with st.expander(
                f"Raw transcript {conversation.conversation_id[-8:]}",
                expanded=False,
            ):
                st.json(
                    {
                        "messages": list(conversation.messages),
                        "tool_transcript": list(conversation.tool_transcript),
                    }
                )
