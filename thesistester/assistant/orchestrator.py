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
from thesistester.assistant.thesis_compiler import (
    ThesisDraft,
    map_persisted_confirmed_run_spec,
)
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
        max_history_messages: int = 12,
    ) -> ThesisDraft:
        """Persist a non-executing chat turn and return its deterministic draft."""
        conversation = self.repository.get_conversation(thesis_id, conversation_id)
        if not isinstance(max_history_messages, int) or max_history_messages < 0:
            raise ValueError("max_history_messages must be a non-negative integer.")
        history_messages = (
            conversation.messages[-max_history_messages:] if max_history_messages else ()
        )
        history = "\n".join(json.dumps(message, sort_keys=True) for message in history_messages)
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
        conversation_id: str | None = None,
    ) -> OrchestrationResult:
        """Execute one confirmed spec and persist its terminal provenance."""
        spec = self.repository.get_spec_version(thesis_id, spec_version)
        if spec.status != "confirmed":
            raise ValueError("Only confirmed specifications may execute.")
        thesis = self.repository.get_thesis(thesis_id)
        # Recompile and validate immutable persisted content immediately before
        # execution. The compatibility mapper makes historical API defaults
        # explicit only for legacy confirmed records that predate the canonical
        # session-control contract.
        run_spec = map_persisted_confirmed_run_spec(
            name=thesis.name,
            choices=spec.normalized_run_spec,
        )
        request = AssistantRequest(
            capability_id="PIPELINE.run_experiment",
            payload={"run_spec": run_spec},
        )
        capability = validate_capability_request(request)
        if capability.confirmation is not ConfirmationLevel.EXPLICIT_CONFIRMATION:
            raise ValueError("Run capability must require explicit confirmation.")
        run = self.repository.start_run(
            thesis_id,
            spec_version=spec_version,
            request={"run_spec": run_spec},
        )
        try:
            result = self.tools.run_experiment_to_bundle(
                run_spec,
                output_path=output_path,
            )
            warning_data = result.get("summary", {}).get("warnings", {})
            warnings = (
                tuple(
                    f"{key}: {value}"
                    for key, value in warning_data.items()
                    if value not in (None, [], {}, "")
                )
                if isinstance(warning_data, dict)
                else ()
            )
            completed = self.repository.complete_run(
                thesis_id,
                run.run_id,
                expected_revision=run.revision,
                provenance={
                    "bundle_path": result["bundle_path"],
                    "canonical_bundle_hash": result["canonical_bundle_hash"],
                    "dataset_fingerprint": result["dataset_fingerprint"],
                    "tool_version": result["tool_version"],
                    "summary": result["summary"],
                    "warnings": list(warnings),
                },
                warnings=warnings,
            )
        except BaseException as exc:
            self.repository.fail_run(
                thesis_id,
                run.run_id,
                expected_revision=run.revision,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise
        if conversation_id is not None:
            try:
                conversation = self.repository.get_conversation(thesis_id, conversation_id)
                self.repository.append_conversation_message(
                    thesis_id,
                    conversation_id,
                    expected_revision=conversation.revision,
                    message={"role": "tool", "content": "Executed confirmed research run."},
                    tool_entry={
                        "capability_id": "PIPELINE.run_experiment",
                        "run_id": completed.run_id,
                        "canonical_bundle_hash": result["canonical_bundle_hash"],
                        "status": "completed",
                    },
                )
            except Exception:
                pass
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
        if request.capability_id == "BACKTEST.manage_execution_defaults":
            action = request.payload.get("action", "save")
            if action == "get":
                return {"defaults": self.tools.get_execution_defaults()["backtest"]}
            if action == "clear":
                self.tools.clear_backtest_execution_defaults()
                return {"cleared": True}
            defaults = request.payload.get("defaults")
            if not isinstance(defaults, dict):
                raise ValueError("Backtest defaults request requires an object.")
            self.tools.save_backtest_execution_defaults(defaults)
            return {"saved": True}
        if request.capability_id == "GRID.manage_execution_defaults":
            action = request.payload.get("action", "save")
            if action == "get":
                return {"defaults": self.tools.get_execution_defaults()["grid"]}
            if action == "clear":
                self.tools.clear_grid_execution_defaults()
                return {"cleared": True}
            defaults = request.payload.get("defaults")
            if not isinstance(defaults, dict):
                raise ValueError("Grid defaults request requires an object.")
            self.tools.save_grid_execution_defaults(defaults)
            return {"saved": True}
        raise ValueError(f"No orchestrator handler for {request.capability_id}.")
