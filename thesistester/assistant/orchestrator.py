"""Registry-gated coordination for assistant requests.

The orchestrator owns confirmation decisions and audit recording. It does not
interpret prose, run engine internals, or grant arbitrary tool access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thesistester.assistant.contracts import AssistantRequest, ConfirmationLevel
from thesistester.assistant.llm import StructuredLLMClient
from thesistester.assistant.llm_intent import propose_thesis_draft
from thesistester.assistant.registry import validate_capability_request
from thesistester.assistant.repository import LocalThesisRepository
from thesistester.assistant.thesis_compiler import ThesisDraft
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
        conversation = None
        if thesis_id is not None and conversation_id is not None:
            conversation = self.repository.get_conversation(thesis_id, conversation_id)
        try:
            result = self._execute(request)
        except ValueError as exc:
            return OrchestrationResult(
                status="unavailable",
                capability_id=request.capability_id,
                payload={"reason": str(exc)},
            )
        if thesis_id is not None and conversation_id is not None:
            assert conversation is not None
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

    def handle_chat_turn(
        self,
        client: StructuredLLMClient,
        *,
        thesis_id: str,
        conversation_id: str,
        user_message: str,
    ) -> ThesisDraft:
        """Persist a non-executing chat turn and return its deterministic draft."""
        conversation = self.repository.get_conversation(thesis_id, conversation_id)
        history = "\n".join(
            json.dumps(message, sort_keys=True) for message in conversation.messages
        )
        prompt = f"{history}\nuser: {user_message}" if history else user_message
        draft = propose_thesis_draft(client, prompt=prompt)
        user_record = self.repository.append_conversation_message(
            thesis_id,
            conversation_id,
            expected_revision=conversation.revision,
            message={"role": "user", "content": user_message},
        )
        self.repository.append_conversation_message(
            thesis_id,
            conversation_id,
            expected_revision=user_record.revision,
            message={
                "role": "assistant",
                "content": "Drafted non-executing research choices.",
                "choices": draft.normalized_run_spec,
                "clarifications": list(draft.unresolved_assumptions),
            },
        )
        return draft

    def execute_confirmed_run(
        self,
        *,
        thesis_id: str,
        spec_version: int,
        output_path: str | Path,
    ) -> OrchestrationResult:
        """Execute one confirmed spec and persist its terminal provenance."""
        spec = self.repository.get_spec_version(thesis_id, spec_version)
        if spec.status != "confirmed":
            raise ValueError("Only confirmed specifications may execute.")
        run = self.repository.start_run(
            thesis_id,
            spec_version=spec_version,
            request={"run_spec": spec.normalized_run_spec},
        )
        try:
            result = self.tools.run_experiment_to_bundle(
                spec.normalized_run_spec,
                output_path=output_path,
            )
        except Exception as exc:
            self.repository.fail_run(
                thesis_id,
                run.run_id,
                expected_revision=run.revision,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise
        completed = self.repository.complete_run(
            thesis_id,
            run.run_id,
            expected_revision=run.revision,
            provenance={
                "bundle_path": result["bundle_path"],
                "canonical_bundle_hash": result["canonical_bundle_hash"],
                "dataset_fingerprint": result["dataset_fingerprint"],
                "tool_version": result["tool_version"],
            },
        )
        return OrchestrationResult(
            status="completed",
            capability_id="PIPELINE.run_experiment",
            payload={"run_id": completed.run_id, **result},
        )

    def _execute(self, request: AssistantRequest) -> dict[str, Any]:
        if request.capability_id == "PIPELINE.validate_run_spec":
            return self.tools.validate_experiment(request.payload["run_spec"])
        if request.capability_id == "PIPELINE.run_experiment":
            return self.tools.run_experiment(request.payload["run_spec"])
        raise ValueError(f"No orchestrator handler for {request.capability_id}.")
