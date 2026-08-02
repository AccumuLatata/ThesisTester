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
