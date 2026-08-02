from pathlib import Path

from thesistester.assistant import (
    AssistantOrchestrator,
    AssistantRequest,
    CapabilityMode,
    FEATURE_PARITY_REGISTRY,
    LocalThesisRepository,
)
from thesistester.assistant.handlers import HANDLER_REGISTRY
from thesistester.assistant.tools import AssistantTools


def test_explicit_compute_requires_confirmation(tmp_path, monkeypatch):
    tools = AssistantTools(data_roots=(tmp_path,))
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Gate")
    conversation = repository.create_conversation(thesis.thesis_id)
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)
    request = AssistantRequest(capability_id="PIPELINE.run_experiment", payload={"run_spec": {}})

    result = orchestrator.dispatch(
        request,
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
    )

    assert result.status == "approval_required"
    assert result.payload["error"]["category"] == "confirmation"
    assert result.payload["error"]["retryable"] is True
    transcript = repository.get_conversation(
        thesis.thesis_id, conversation.conversation_id
    ).tool_transcript
    assert len(transcript) == 1
    assert transcript[0]["status"] == "approval_required"


def test_validated_request_routes_only_through_declared_tool(tmp_path, monkeypatch):
    tools = AssistantTools(data_roots=(Path(tmp_path),))
    repository = LocalThesisRepository(tmp_path / "assistant")
    monkeypatch.setattr(tools, "validate_experiment", lambda spec: {"valid": True})
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)

    result = orchestrator.dispatch(
        AssistantRequest(capability_id="PIPELINE.validate_run_spec", payload={"run_spec": {}})
    )

    assert result.status == "completed"
    assert result.payload["valid"] is True
    assert "resource_limits" in result.payload


def test_read_only_validate_is_idempotent_with_matching_audit(tmp_path, monkeypatch):
    tools = AssistantTools(data_roots=(Path(tmp_path),))
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Idempotent")
    conversation = repository.create_conversation(thesis.thesis_id)
    monkeypatch.setattr(tools, "validate_experiment", lambda spec: {"valid": True})
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)
    request = AssistantRequest(capability_id="PIPELINE.validate_run_spec", payload={"run_spec": {}})

    first = orchestrator.dispatch(
        request,
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
    )
    second = orchestrator.dispatch(
        request,
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
    )

    assert first.status == second.status == "completed"
    assert first.payload["valid"] == second.payload["valid"]
    transcript = repository.get_conversation(
        thesis.thesis_id, conversation.conversation_id
    ).tool_transcript
    assert [entry["status"] for entry in transcript] == ["completed", "completed"]


def test_unsupported_capability_is_unavailable_and_audited(tmp_path):
    tools = AssistantTools(data_roots=(Path(tmp_path),))
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Unsupported")
    conversation = repository.create_conversation(thesis.thesis_id)
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)

    result = orchestrator.dispatch(
        AssistantRequest(capability_id="BACKTEST.configure_and_run", payload={}),
        confirmed=True,
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
    )

    assert result.status == "unavailable"
    assert result.payload["error"]["category"] == "contract"
    transcript = repository.get_conversation(
        thesis.thesis_id, conversation.conversation_id
    ).tool_transcript
    assert len(transcript) == 1
    assert transcript[0]["status"] == "unavailable"


def test_every_routed_registry_capability_has_a_handler():
    routed = [
        capability.capability_id
        for capability in FEATURE_PARITY_REGISTRY
        if capability.mode is not CapabilityMode.UNSUPPORTED
    ]
    assert routed
    assert all(capability_id in HANDLER_REGISTRY for capability_id in routed)


def test_cancel_run_records_terminal_state_and_audit(tmp_path):
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Cancel")
    conversation = repository.create_conversation(thesis.thesis_id)
    draft = repository.create_spec_version(
        thesis.thesis_id,
        normalized_run_spec={
            "dataset": {"path": "bars.csv", "instrument": "ES"},
            "levels": {},
            "setup": {
                "name": "Cancel",
                "description": "",
                "instrument": "ES",
                "selected_levels": ["dVWAP_RTH"],
                "tolerance_ticks": 0,
                "min_confluences": 1,
                "max_confluences": 1,
                "naked_only": False,
                "naked_requirement": "any",
                "trigger": "touch",
                "direction": "both",
            },
            "backtest": {
                "commission_per_side": 0,
                "slippage_ticks": 0,
                "exposure_policy": "single_position",
                "intrabar_model": "sl_first",
                "flat_by_session_close": True,
                "session_close_time": "16:00",
                "session_timezone": "America/New_York",
                "no_new_entries_after": "15:45",
            },
        },
        status="ready_for_confirmation",
    )
    confirmed = repository.confirm_spec_version(thesis.thesis_id, draft.version)
    run = repository.start_run(
        thesis.thesis_id,
        spec_version=confirmed.version,
        request={"run_spec": confirmed.normalized_run_spec},
    )
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(Path(tmp_path),)), repository=repository
    )

    result = orchestrator.cancel_run(
        thesis_id=thesis.thesis_id,
        run_id=run.run_id,
        conversation_id=conversation.conversation_id,
        reason="Stopped by operator.",
    )

    restored = repository.get_run(thesis.thesis_id, run.run_id)
    assert result.status == "cancelled"
    assert restored.status == "cancelled"
    assert restored.error["reason"] == "Stopped by operator."
    transcript = repository.get_conversation(
        thesis.thesis_id, conversation.conversation_id
    ).tool_transcript
    assert transcript[-1]["status"] == "cancelled"


def test_chat_turn_persists_user_and_nonexecuting_assistant_draft(tmp_path):
    class Client:
        def complete_structured(self, **kwargs):
            return {
                "choices": [
                    {"key": "trend_rule", "value": "slope"},
                    {"key": "trigger", "value": "touch"},
                    {"key": "session_window", "value": "10:00 ET"},
                    {"key": "success_criteria", "value": "30 trades"},
                ],
                "clarifications": [],
            }

    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Chat")
    conversation = repository.create_conversation(thesis.thesis_id)
    orchestrator = AssistantOrchestrator(
        tools=AssistantTools(data_roots=(Path(tmp_path),)), repository=repository
    )

    draft = orchestrator.handle_chat_turn(
        Client(),
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
        user_message="Test",
    )

    assert not draft.ready_for_confirmation
    assert (
        len(repository.get_conversation(thesis.thesis_id, conversation.conversation_id).messages)
        == 2
    )


def test_failed_tool_dispatch_records_structured_error(tmp_path, monkeypatch):
    tools = AssistantTools(data_roots=(Path(tmp_path),))
    repository = LocalThesisRepository(tmp_path / "assistant")
    thesis = repository.create_thesis(name="Fail")
    conversation = repository.create_conversation(thesis.thesis_id)

    def boom(spec):
        raise ValueError("invalid path")

    monkeypatch.setattr(tools, "validate_experiment", boom)
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)

    result = orchestrator.dispatch(
        AssistantRequest(capability_id="PIPELINE.validate_run_spec", payload={"run_spec": {}}),
        thesis_id=thesis.thesis_id,
        conversation_id=conversation.conversation_id,
    )

    assert result.status == "failed"
    assert result.payload["error"]["category"] == "tool"
    assert result.payload["error"]["remediation"]
    transcript = repository.get_conversation(
        thesis.thesis_id, conversation.conversation_id
    ).tool_transcript
    assert transcript[-1]["status"] == "failed"
