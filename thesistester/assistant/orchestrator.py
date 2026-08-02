"""Registry-gated coordination for assistant requests.

The orchestrator owns confirmation decisions and audit recording. It does not
interpret prose, run engine internals, or grant arbitrary tool access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from thesistester.assistant.contracts import AssistantRequest, ConfirmationLevel
from thesistester.assistant.registry import validate_capability_request
from thesistester.assistant.repository import LocalThesisRepository
from thesistester.assistant.tools import AssistantTools


@dataclass(frozen=True)
class OrchestrationResult:
    status: str
    capability_id: str
    payload: dict[str, Any]


class AssistantOrchestrator:
    """Coordinate only declared assistant capabilities."""

    def __init__(self, *, tools: AssistantTools, repository: LocalThesisRepository) -> None:
        self.tools = tools
        self.repository = repository

    def dispatch(
        self,
        request: AssistantRequest,
        *,
        confirmed: bool = False,
        thesis_id: str | None = None,
        conversation_id: str | None = None,
    ) -> OrchestrationResult:
        """Validate, gate, execute one supported request, and record its outcome."""
        capability = validate_capability_request(request)
        if capability.confirmation is ConfirmationLevel.EXPLICIT_CONFIRMATION and not confirmed:
            return OrchestrationResult(
                status="approval_required",
                capability_id=request.capability_id,
                payload={"reason": "Explicit confirmation is required before this action."},
            )
        result = self._execute(request)
        if thesis_id is not None and conversation_id is not None:
            conversation = self.repository.get_conversation(thesis_id, conversation_id)
            self.repository.append_conversation_message(
                thesis_id,
                conversation_id,
                expected_revision=conversation.revision,
                message={"role": "tool", "content": f"Executed {request.capability_id}."},
                tool_entry={
                    "capability_id": request.capability_id,
                    "request": request.to_dict(),
                    "status": "completed",
                },
            )
        return OrchestrationResult(
            status="completed", capability_id=request.capability_id, payload=result
        )

    def _execute(self, request: AssistantRequest) -> dict[str, Any]:
        if request.capability_id == "PIPELINE.validate_run_spec":
            return self.tools.validate_experiment(request.payload["run_spec"])
        if request.capability_id == "PIPELINE.run_experiment":
            return self.tools.run_experiment(request.payload["run_spec"])
        raise ValueError(f"No orchestrator handler for {request.capability_id}.")
