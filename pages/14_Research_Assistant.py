"""AI Research Assistant thesis workspace.

This page is intentionally a thin Streamlit consumer of the assistant library.
It does not implement backtesting semantics or execute arbitrary model output.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import streamlit as st

from thesistester.assistant import (
    AssistantOrchestrator,
    Comparison,
    LocalThesisRepository,
    compile_run_spec,
    compile_thesis,
)
from thesistester.assistant.explainer import (
    build_evidence_packet,
    compare_evidence,
    explain_evidence,
)
from thesistester.assistant.llm import (
    LLMConfigurationError,
    create_openai_client,
    load_llm_settings,
)
from thesistester.assistant.tools import AssistantTools
from thesistester.persistence.local_store import get_store_root
from thesistester.research_bundle import canonical_bundle_hash, load_research_bundle


def _repository() -> LocalThesisRepository:
    return LocalThesisRepository()


def _init_state() -> None:
    st.session_state.setdefault("assistant_selected_thesis_id", None)
    st.session_state.setdefault("assistant_draft_prompt", "")
    st.session_state.setdefault("assistant_draft_choices", {})
    st.session_state.setdefault("assistant_conversation_ids", {})
    st.session_state.setdefault("assistant_hydrated_conversation_id", None)
    st.session_state.setdefault("assistant_validated_run_spec", None)
    st.session_state.setdefault("assistant_run_explanations", {})
    st.session_state.setdefault("assistant_run_comparisons", {})


def _select_thesis(thesis_id: str) -> None:
    if st.session_state["assistant_selected_thesis_id"] != thesis_id:
        st.session_state["assistant_selected_thesis_id"] = thesis_id
        st.session_state["assistant_draft_prompt"] = ""
        st.session_state["assistant_draft_choices"] = {}


def _choices_from_editor(raw: str) -> dict:
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Choices must be a JSON object.")
    return parsed


_init_state()
repository = _repository()

st.title("Research Assistant")
st.caption("Draft explicit research theses. Execution remains confirmation- and schema-gated.")

with st.sidebar:
    st.subheader("Theses")
    new_name = st.text_input("New thesis name", key="assistant_new_thesis_name")
    if st.button("Create thesis", use_container_width=True):
        try:
            thesis = repository.create_thesis(name=new_name)
            _select_thesis(thesis.thesis_id)
            st.session_state["assistant_thesis_picker"] = thesis.thesis_id
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    theses = repository.list_theses(include_archived=True)
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
        _select_thesis(selected_id)

thesis_id = st.session_state["assistant_selected_thesis_id"]
if not thesis_id:
    st.info("Create or select a thesis to begin.")
    st.stop()

thesis = repository.get_thesis(thesis_id)
st.subheader(thesis.name)
st.caption(f"Revision {thesis.revision} · {thesis.lifecycle}")
with st.expander("Manage thesis"):
    renamed = st.text_input("Rename thesis", value=thesis.name, key=f"assistant_rename_{thesis_id}")
    if st.button("Save thesis name", key=f"rename-{thesis_id}"):
        try:
            repository.rename_thesis(thesis_id, name=renamed, expected_revision=thesis.revision)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if st.button("Clone thesis", key=f"clone-{thesis_id}"):
        clone = repository.clone_thesis(thesis_id)
        _select_thesis(clone.thesis_id)
        st.session_state["assistant_thesis_picker"] = clone.thesis_id
        st.rerun()
    if thesis.lifecycle == "active":
        if st.button("Archive thesis", key=f"archive-{thesis_id}"):
            repository.archive_thesis(thesis_id, expected_revision=thesis.revision)
            st.rerun()
    elif st.button("Restore thesis", key=f"restore-{thesis_id}"):
        repository.restore_thesis(thesis_id, expected_revision=thesis.revision)
        st.rerun()

conversations = repository.list_conversations(thesis_id)
conversation_ids = st.session_state["assistant_conversation_ids"]
if conversation_ids.get(thesis_id) not in {
    conversation.conversation_id for conversation in conversations
}:
    conversation = conversations[-1] if conversations else repository.create_conversation(thesis_id)
    conversation_ids[thesis_id] = conversation.conversation_id
conversation_id = conversation_ids[thesis_id]
active_conversation = repository.get_conversation(thesis_id, conversation_id)
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

st.subheader("Assistant chat")
for message in active_conversation.messages:
    with st.chat_message(message.get("role", "assistant")):
        st.write(message.get("content", ""))

if chat_message := st.chat_input("Describe or refine this thesis"):
    try:
        settings = load_llm_settings()
        client = create_openai_client(settings)
        orchestrator = AssistantOrchestrator(
            tools=AssistantTools(data_roots=(Path.cwd(),)),
            repository=repository,
        )
        draft = orchestrator.handle_chat_turn(
            client,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            user_message=chat_message,
        )
        st.session_state["assistant_draft_prompt"] = "\n".join(
            [
                *(
                    str(message.get("content", ""))
                    for message in active_conversation.messages
                    if message.get("role") == "user"
                ),
                chat_message,
            ]
        )
        st.session_state["assistant_draft_choices"] = draft.normalized_run_spec
        st.rerun()
    except LLMConfigurationError as exc:
        st.error(str(exc))

prompt = st.text_area(
    "Describe the setup thesis",
    value=st.session_state["assistant_draft_prompt"],
    placeholder="Example: Uptrend retraces to dVWAP with 30m SMA confluence in NY B session.",
)
choices_raw = st.text_area(
    "Explicit research choices (JSON)",
    value=json.dumps(st.session_state["assistant_draft_choices"], indent=2),
    help="Define trend_rule, trigger, session_window, success_criteria, and any applicable details.",
)
if st.button("Draft research plan", type="primary"):
    try:
        choices = _choices_from_editor(choices_raw)
        draft = compile_thesis(prompt, choices=choices)
        st.session_state["assistant_draft_prompt"] = draft.prompt
        st.session_state["assistant_draft_choices"] = draft.normalized_run_spec
        spec = repository.create_spec_version(
            thesis_id,
            normalized_run_spec=draft.normalized_run_spec,
            status="ready_for_confirmation"
            if draft.ready_for_confirmation
            else "needs_clarification",
            unresolved_assumptions=draft.unresolved_assumptions,
            compiler_version="1",
        )
        st.success(f"Saved specification version {spec.version}.")
        st.rerun()
    except (ValueError, json.JSONDecodeError) as exc:
        st.error(str(exc))

if st.button("Validate executable RunSpec"):
    try:
        current_choices = _choices_from_editor(choices_raw)
        validated = compile_run_spec(name=thesis.name, choices=current_choices)
        st.session_state["assistant_draft_choices"] = current_choices
        st.session_state["assistant_validated_run_spec"] = {
            "choices": current_choices,
            "spec": validated,
        }
        st.success("Executable RunSpec is valid and ready for explicit confirmation.")
    except ValueError as exc:
        st.session_state["assistant_validated_run_spec"] = None
        st.error(str(exc))

validated_state = st.session_state["assistant_validated_run_spec"]
if (
    isinstance(validated_state, dict)
    and validated_state.get("choices") == st.session_state["assistant_draft_choices"]
):
    with st.expander("Validated executable RunSpec"):
        st.json(validated_state["spec"])
    if st.button("Confirm validated RunSpec", type="primary"):
        executable = repository.create_spec_version(
            thesis_id,
            normalized_run_spec=validated_state["spec"],
            status="ready_for_confirmation",
            unresolved_assumptions=(),
            compiler_version="runspec-1",
        )
        repository.confirm_spec_version(
            thesis_id,
            executable.version,
            confirmation_note="Confirmed validated executable RunSpec in UI",
        )
        st.session_state["assistant_validated_run_spec"] = None
        st.rerun()

specifications = repository.list_spec_versions(thesis_id)
confirmed_parents = {spec.parent_version for spec in specifications if spec.status == "confirmed"}
for spec in reversed(specifications):
    with st.expander(f"Specification v{spec.version} · {spec.status}", expanded=spec.version == 1):
        st.json(spec.normalized_run_spec)
        if spec.unresolved_assumptions:
            st.warning("Clarifications required")
            for assumption in spec.unresolved_assumptions:
                st.write(f"- {assumption}")
        if spec.status == "confirmed" and {"dataset", "setup", "backtest"}.issubset(
            spec.normalized_run_spec
        ):
            if st.button("Run confirmed research", key=f"run-{spec.version}"):
                try:
                    output_path = (
                        get_store_root()
                        / "assistant"
                        / "theses"
                        / thesis_id
                        / "bundles"
                        / f"{uuid4().hex}.research.zip"
                    )
                    orchestrator = AssistantOrchestrator(
                        tools=AssistantTools(data_roots=(Path.cwd(), get_store_root())),
                        repository=repository,
                    )
                    orchestrator.execute_confirmed_run(
                        thesis_id=thesis_id,
                        spec_version=spec.version,
                        output_path=output_path,
                    )
                    st.success("Research run completed and provenance was recorded.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Research run failed: {exc}")

st.subheader("Research runs")
runs = repository.list_runs(thesis_id)
if not runs:
    st.info("No research runs are recorded for this thesis yet.")
else:
    for run in reversed(runs):
        with st.expander(f"Run {run.run_id[-8:]} · {run.status}"):
            st.caption(f"Specification v{run.spec_version} · revision {run.revision}")
            st.json(
                {
                    "request": run.request,
                    "provenance": run.provenance,
                    "warnings": list(run.warnings),
                    "error": run.error,
                }
            )
            if run.status == "completed" and isinstance(run.provenance, dict):
                bundle_path = run.provenance.get("bundle_path")
                if isinstance(bundle_path, str) and st.button(
                    "Explain run", key=f"explain-{run.run_id}"
                ):
                    try:
                        raw_bundle = Path(bundle_path).read_bytes()
                        if canonical_bundle_hash(raw_bundle) != run.provenance.get(
                            "canonical_bundle_hash"
                        ):
                            raise ValueError("Bundle hash does not match recorded run provenance.")
                        bundle = load_research_bundle(raw_bundle)
                        packet = build_evidence_packet(
                            bundle["session_values"],
                            provenance=run.provenance,
                        )
                        st.session_state["assistant_run_explanations"][run.run_id] = (
                            explain_evidence(packet)
                        )
                    except (OSError, ValueError) as exc:
                        st.error(f"Unable to load run evidence: {exc}")
                explanation = st.session_state["assistant_run_explanations"].get(run.run_id)
                if explanation:
                    st.write(explanation)

completed_runs = [
    run
    for run in runs
    if run.status == "completed"
    and isinstance(run.provenance, dict)
    and isinstance(run.provenance.get("bundle_path"), str)
    and isinstance(run.provenance.get("canonical_bundle_hash"), str)
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
        try:
            selected = {run.run_id: run for run in completed_runs}
            packets = []
            for run_id in (left_id, right_id):
                run = selected[run_id]
                raw = Path(run.provenance["bundle_path"]).read_bytes()
                if canonical_bundle_hash(raw) != run.provenance["canonical_bundle_hash"]:
                    raise ValueError("Bundle hash does not match recorded run provenance.")
                packets.append(
                    build_evidence_packet(
                        load_research_bundle(raw)["session_values"], provenance=run.provenance
                    )
                )
            comparison = compare_evidence(*packets)
            record = repository.save_comparison(
                Comparison.create(
                    thesis_id=thesis_id,
                    left_run_id=left_id,
                    right_run_id=right_id,
                    left_bundle_hash=selected[left_id].provenance["canonical_bundle_hash"],
                    right_bundle_hash=selected[right_id].provenance["canonical_bundle_hash"],
                    evidence=comparison,
                )
            )
            st.session_state["assistant_run_comparisons"][thesis_id] = {
                "run_ids": [left_id, right_id],
                "comparison": record.to_dict(),
            }
        except (OSError, ValueError) as exc:
            st.error(f"Unable to compare runs: {exc}")
    comparison_state = st.session_state["assistant_run_comparisons"].get(thesis_id)
    if comparison_state and comparison_state.get("run_ids") == [left_id, right_id]:
        st.json(comparison_state["comparison"])
    with st.expander("Saved comparisons"):
        for record in repository.list_comparisons(thesis_id):
            st.json(record.to_dict())

st.subheader("Conversation audit")
conversations = repository.list_conversations(thesis_id)
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
