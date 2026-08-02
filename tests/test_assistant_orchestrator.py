from pathlib import Path

from thesistester.assistant import (
    AssistantOrchestrator,
    AssistantRequest,
    LocalThesisRepository,
)
from thesistester.assistant.tools import AssistantTools


def test_explicit_compute_requires_confirmation(tmp_path, monkeypatch):
    tools = AssistantTools(data_roots=(tmp_path,))
    repository = LocalThesisRepository(tmp_path / "assistant")
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)
    request = AssistantRequest(capability_id="PIPELINE.run_experiment", payload={"run_spec": {}})

    result = orchestrator.dispatch(request)

    assert result.status == "approval_required"


def test_validated_request_routes_only_through_declared_tool(tmp_path, monkeypatch):
    tools = AssistantTools(data_roots=(Path(tmp_path),))
    repository = LocalThesisRepository(tmp_path / "assistant")
    monkeypatch.setattr(tools, "validate_experiment", lambda spec: {"valid": True})
    orchestrator = AssistantOrchestrator(tools=tools, repository=repository)

    result = orchestrator.dispatch(
        AssistantRequest(capability_id="PIPELINE.validate_run_spec", payload={"run_spec": {}})
    )

    assert result.status == "completed"
    assert result.payload == {"valid": True}


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
