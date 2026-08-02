"""AI Research Assistant thesis workspace.

This page is intentionally a thin Streamlit consumer of the assistant library.
It does not implement backtesting semantics or execute arbitrary model output.
"""

from __future__ import annotations

import json

import streamlit as st

from thesistester.assistant import LocalThesisRepository, compile_thesis


def _repository() -> LocalThesisRepository:
    return LocalThesisRepository()


def _init_state() -> None:
    st.session_state.setdefault("assistant_selected_thesis_id", None)
    st.session_state.setdefault("assistant_draft_prompt", "")
    st.session_state.setdefault("assistant_draft_choices", {})


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
        thesis = repository.create_thesis(name=new_name)
        _select_thesis(thesis.thesis_id)
        st.rerun()
    theses = repository.list_theses(include_archived=True)
    thesis_options = {
        f"{thesis.name} ({thesis.lifecycle}, {thesis.thesis_id[-8:]})": thesis.thesis_id
        for thesis in theses
    }
    selected_label = st.selectbox("Select thesis", list(thesis_options), index=None)
    if selected_label:
        _select_thesis(thesis_options[selected_label])

thesis_id = st.session_state["assistant_selected_thesis_id"]
if not thesis_id:
    st.info("Create or select a thesis to begin.")
    st.stop()

thesis = repository.get_thesis(thesis_id)
st.subheader(thesis.name)
st.caption(f"Revision {thesis.revision} · {thesis.lifecycle}")

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
    except (ValueError, json.JSONDecodeError) as exc:
        st.error(str(exc))

specifications = repository.list_spec_versions(thesis_id)
confirmed_parents = {spec.parent_version for spec in specifications if spec.status == "confirmed"}
for spec in reversed(specifications):
    with st.expander(f"Specification v{spec.version} · {spec.status}", expanded=spec.version == 1):
        st.json(spec.normalized_run_spec)
        if spec.unresolved_assumptions:
            st.warning("Clarifications required")
            for assumption in spec.unresolved_assumptions:
                st.write(f"- {assumption}")
        if (
            spec.status != "confirmed"
            and spec.version not in confirmed_parents
            and not spec.unresolved_assumptions
        ):
            if st.button("Confirm specification", key=f"confirm-{spec.version}"):
                repository.confirm_spec_version(
                    thesis_id, spec.version, confirmation_note="Confirmed in UI"
                )
                st.rerun()
