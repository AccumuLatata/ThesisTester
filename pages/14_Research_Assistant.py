"""AI Research Assistant thesis workspace.

This page is intentionally a thin Streamlit consumer of the assistant library.
It does not implement backtesting semantics or execute arbitrary model output.
"""

from __future__ import annotations

import json
import hashlib
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
    LLMProviderError,
    create_openai_client,
    load_llm_settings,
)
from thesistester.assistant.llm_explainer import explain_packet_with_llm
from thesistester.assistant.tools import AssistantTools
from thesistester.persistence.local_store import (
    get_store_root,
    list_saved_setups,
    load_setup,
    save_setup,
)
from thesistester.reporting import build_research_artifact, to_jsonable
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
    st.session_state.setdefault("assistant_llm_run_explanations", {})
    st.session_state.setdefault("assistant_llm_attempts", {})
    st.session_state.setdefault("assistant_run_reports", {})
    st.session_state.setdefault("assistant_run_artifacts", {})
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
with st.expander("Open detailed research views"):
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
            max_history_messages=settings.max_history_messages,
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
    except (LLMConfigurationError, LLMProviderError) as exc:
        st.error(str(exc))

with st.expander("Structured research clarifications"):
    with st.form(f"assistant_clarifications_{thesis_id}"):
        current = st.session_state["assistant_draft_choices"]
        trend_rule = st.text_input("Trend rule", value=str(current.get("trend_rule", "")))
        trigger = st.text_input("Entry trigger", value=str(current.get("trigger", "")))
        session_window = st.text_input(
            "Session window", value=str(current.get("session_window", ""))
        )
        success_criteria = st.text_input(
            "Success criteria", value=str(current.get("success_criteria", ""))
        )
        if st.form_submit_button("Apply clarifications"):
            st.session_state["assistant_draft_choices"] = {
                **current,
                "trend_rule": trend_rule,
                "trigger": trigger,
                "session_window": session_window,
                "success_criteria": success_criteria,
            }
            st.session_state["assistant_validated_run_spec"] = None
            st.rerun()

with st.expander("Structured execution controls"):
    current = st.session_state["assistant_draft_choices"]
    dataset = current.get("dataset") if isinstance(current.get("dataset"), dict) else {}
    backtest = current.get("backtest") if isinstance(current.get("backtest"), dict) else {}
    setup = current.get("setup") if isinstance(current.get("setup"), dict) else None
    controls_fingerprint = hashlib.sha256(
        json.dumps(current, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    with st.form(f"assistant_execution_{thesis_id}_{controls_fingerprint}"):
        dataset_path = st.text_input("Dataset CSV path", value=str(dataset.get("path", "")))
        instruments = ["ES", "NQ", "MES", "MNQ"]
        current_instrument = str(
            (setup or {}).get("instrument") or dataset.get("instrument") or "ES"
        )
        instrument = st.selectbox(
            "Instrument",
            instruments,
            index=instruments.index(current_instrument) if current_instrument in instruments else 0,
        )
        raw_stop = backtest.get("stop_loss_ticks", 8)
        raw_target = backtest.get("take_profit_ticks", 16)
        stop_default = int(raw_stop) if isinstance(raw_stop, (int, float)) and raw_stop > 0 else 8
        target_default = (
            int(raw_target) if isinstance(raw_target, (int, float)) and raw_target > 0 else 16
        )
        stop_loss_ticks = st.number_input("Stop loss ticks", min_value=1, value=stop_default)
        take_profit_ticks = st.number_input("Take profit ticks", min_value=1, value=target_default)
        commission_per_side = st.number_input(
            "Commission per side",
            min_value=0.0,
            value=float(backtest.get("commission_per_side") or 0.0),
        )
        slippage_ticks = st.number_input(
            "Slippage ticks",
            min_value=0.0,
            value=float(backtest.get("slippage_ticks") or 0.0),
        )
        exposure_policy = st.selectbox(
            "Exposure policy",
            ["allow_all", "single_position", "single_direction", "single_setup"],
            index=["allow_all", "single_position", "single_direction", "single_setup"].index(
                str(backtest.get("exposure_policy") or "allow_all")
            )
            if str(backtest.get("exposure_policy") or "allow_all")
            in ["allow_all", "single_position", "single_direction", "single_setup"]
            else 0,
        )
        intrabar_model = st.selectbox(
            "Intrabar model",
            ["sl_first", "path_open_proximity", "subtimeframe", "subtimeframe_conservative"],
            index=[
                "sl_first",
                "path_open_proximity",
                "subtimeframe",
                "subtimeframe_conservative",
            ].index(str(backtest.get("intrabar_model") or "sl_first"))
            if str(backtest.get("intrabar_model") or "sl_first")
            in ["sl_first", "path_open_proximity", "subtimeframe", "subtimeframe_conservative"]
            else 0,
        )
        if st.form_submit_button("Apply execution controls"):
            st.session_state["assistant_draft_choices"] = {
                **current,
                "dataset": {**dataset, "path": dataset_path, "instrument": instrument},
                **({"setup": {**setup, "instrument": instrument}} if setup is not None else {}),
                "backtest": {
                    **backtest,
                    "stop_loss_ticks": stop_loss_ticks,
                    "take_profit_ticks": take_profit_ticks,
                    "commission_per_side": commission_per_side,
                    "slippage_ticks": slippage_ticks,
                    "exposure_policy": exposure_policy,
                    "intrabar_model": intrabar_model,
                },
            }
            st.session_state["assistant_validated_run_spec"] = None
            st.rerun()

with st.expander("Reuse saved setup"):
    saved_setups = list_saved_setups()
    setup_options = {
        setup["setup_id"]: f"{setup.get('name', 'Unnamed')} ({setup['setup_id'][-8:]})"
        for setup in saved_setups
    }
    selected_setup_id = st.selectbox(
        "Saved setup",
        list(setup_options),
        format_func=setup_options.get,
        index=None,
        key=f"assistant_saved_setup_{thesis_id}",
    )
    if selected_setup_id and st.button("Apply saved setup"):
        setup = load_setup(selected_setup_id)
        setup_config = setup.get("setup_config")
        if not isinstance(setup_config, dict):
            st.error("Saved setup does not contain a valid setup configuration.")
            st.stop()
        st.session_state["assistant_draft_choices"] = {
            **st.session_state["assistant_draft_choices"],
            "setup": setup_config,
        }
        st.session_state["assistant_validated_run_spec"] = None
        st.rerun()

prompt = st.text_area(
    "Describe the setup thesis",
    value=st.session_state["assistant_draft_prompt"],
    placeholder="Example: Uptrend retraces to dVWAP with 30m SMA confluence in NY B session.",
)
with st.expander("Advanced: edit complete research choices as JSON"):
    choices_raw = st.text_area(
        "Explicit research choices (JSON)",
        value=json.dumps(st.session_state["assistant_draft_choices"], indent=2),
        help="Use structured clarifications above for common fields.",
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
    if st.button("Save validated setup to library"):
        saved = save_setup(
            validated_state["spec"]["setup"],
            instrument=validated_state["spec"]["setup"].get("instrument"),
        )
        st.success(f"Saved setup {saved['setup_id']}.")
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
                        conversation_id=conversation_id,
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
                if isinstance(bundle_path, str) and st.button(
                    "Generate evidence-only AI explanation", key=f"llm-explain-{run.run_id}"
                ):
                    try:
                        raw = Path(bundle_path).read_bytes()
                        if canonical_bundle_hash(raw) != run.provenance.get(
                            "canonical_bundle_hash"
                        ):
                            raise ValueError("Bundle hash does not match recorded run provenance.")
                        packet = build_evidence_packet(
                            load_research_bundle(raw)["session_values"], provenance=run.provenance
                        )
                        client = create_openai_client(load_llm_settings())
                        st.session_state["assistant_llm_run_explanations"][run.run_id] = (
                            explain_packet_with_llm(client, packet=packet)
                        )
                        st.session_state["assistant_llm_attempts"][run.run_id] = (
                            client.last_attempt_count
                        )
                    except (LLMConfigurationError, LLMProviderError, OSError, ValueError) as exc:
                        st.error(f"Unable to generate AI explanation: {exc}")
                llm_explanation = st.session_state["assistant_llm_run_explanations"].get(run.run_id)
                if llm_explanation:
                    st.write(llm_explanation.summary)
                    for caveat in llm_explanation.caveats:
                        st.caption(f"Caveat: {caveat}")
                    attempts = st.session_state["assistant_llm_attempts"].get(run.run_id)
                    if attempts:
                        st.caption(f"Provider attempts: {attempts}")
                if isinstance(bundle_path, str) and st.button(
                    "Render markdown report", key=f"report-{run.run_id}"
                ):
                    try:
                        raw = Path(bundle_path).read_bytes()
                        if canonical_bundle_hash(raw) != run.provenance.get(
                            "canonical_bundle_hash"
                        ):
                            raise ValueError("Bundle hash does not match recorded run provenance.")
                        st.session_state["assistant_run_reports"][run.run_id] = AssistantTools(
                            data_roots=(Path.cwd(), get_store_root())
                        ).render_bundle_markdown_report(bundle_path)
                    except (OSError, ValueError) as exc:
                        st.error(f"Unable to render report: {exc}")
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
                if isinstance(bundle_path, str) and st.button(
                    "Build research artifact", key=f"artifact-{run.run_id}"
                ):
                    try:
                        raw = Path(bundle_path).read_bytes()
                        if canonical_bundle_hash(raw) != run.provenance.get(
                            "canonical_bundle_hash"
                        ):
                            raise ValueError("Bundle hash does not match recorded run provenance.")
                        state = load_research_bundle(raw)["session_values"]
                        st.session_state["assistant_run_artifacts"][run.run_id] = to_jsonable(
                            build_research_artifact(state)
                        )
                    except (OSError, ValueError) as exc:
                        st.error(f"Unable to build research artifact: {exc}")
                artifact = st.session_state["assistant_run_artifacts"].get(run.run_id)
                if artifact:
                    st.download_button(
                        "Download research artifact JSON",
                        data=json.dumps(artifact, indent=2, sort_keys=True),
                        file_name=f"assistant_run_{run.run_id[-8:]}.research.json",
                        mime="application/json",
                        key=f"download-artifact-{run.run_id}",
                    )

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
            st.session_state["assistant_run_comparisons"][thesis_id] = {
                "run_ids": [left_id, right_id],
                "comparison": comparison,
            }
            try:
                repository.save_comparison(
                    Comparison.create(
                        thesis_id=thesis_id,
                        left_run_id=left_id,
                        right_run_id=right_id,
                        left_bundle_hash=selected[left_id].provenance["canonical_bundle_hash"],
                        right_bundle_hash=selected[right_id].provenance["canonical_bundle_hash"],
                        evidence=comparison,
                    )
                )
            except ValueError as exc:
                st.warning(f"Comparison was calculated but could not be saved: {exc}")
        except (OSError, ValueError) as exc:
            st.error(f"Unable to compare runs: {exc}")
    comparison_state = st.session_state["assistant_run_comparisons"].get(thesis_id)
    if comparison_state and comparison_state.get("run_ids") == [left_id, right_id]:
        st.json(comparison_state["comparison"])

if len(completed_runs) >= 2:
    st.subheader("Portfolio analysis")
    portfolio_ids = st.multiselect(
        "Completed runs",
        [run.run_id for run in completed_runs],
        format_func=labels.get,
        key=f"assistant_portfolio_runs_{thesis_id}",
    )
    instrument = st.selectbox(
        "Portfolio instrument",
        ["ES", "NQ", "MES", "MNQ"],
        key=f"assistant_portfolio_instrument_{thesis_id}",
    )
    if st.button("Analyze portfolio") and len(portfolio_ids) >= 2:
        try:
            selected = {run.run_id: run for run in completed_runs}
            bundle_paths = []
            for run_id in portfolio_ids:
                run = selected[run_id]
                raw = Path(run.provenance["bundle_path"]).read_bytes()
                if canonical_bundle_hash(raw) != run.provenance["canonical_bundle_hash"]:
                    raise ValueError("Bundle hash does not match recorded run provenance.")
                bundle_paths.append(run.provenance["bundle_path"])
            st.json(
                AssistantTools(data_roots=(Path.cwd(), get_store_root())).analyze_bundle_portfolio(
                    bundle_paths,
                    instrument=instrument,
                )
            )
        except (OSError, ValueError) as exc:
            st.error(f"Unable to analyze portfolio: {exc}")

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
