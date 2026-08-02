"""Registry-gated coordination for assistant requests.

The orchestrator owns confirmation decisions, resource-envelope enforcement, and
audit recording. It does not interpret prose, run engine internals, or grant
arbitrary tool access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from thesistester.assistant.contracts import (
    AssistantContractError,
    AssistantRequest,
    ConfirmationLevel,
    OrchestrationStatus,
    UnknownCapabilityError,
    structured_error,
)
from thesistester.assistant.handlers import (
    HANDLER_REGISTRY,
    HandlerContext,
    get_handler,
    tool_limits_from_envelope,
)
from thesistester.assistant.llm import StructuredLLMClient
from thesistester.assistant.llm_intent import propose_thesis_draft
from thesistester.assistant.registry import FEATURE_PARITY_REGISTRY, validate_capability_request
from thesistester.assistant.repository import (
    InvalidStateTransitionError,
    LocalThesisRepository,
    RepositoryConflictError,
)
from thesistester.assistant.thesis_compiler import (
    ThesisDraft,
    map_persisted_confirmed_run_spec,
)
from thesistester.assistant.tools import AssistantToolError, AssistantTools, ToolLimits
from thesistester.research_bundle import canonical_bundle_hash


_READ_ONLY_ACTIONS = frozenset({"get", "list", "describe", "load", "summary", "evidence"})


def _assert_readable_bundle_provenance(result: Mapping[str, Any]) -> None:
    """Fail closed unless the written bundle exists and matches its hash."""
    bundle_path = result.get("bundle_path")
    expected_hash = result.get("canonical_bundle_hash")
    if not isinstance(bundle_path, str) or not bundle_path.strip():
        raise AssistantToolError("Completed runs require a readable bundle_path.")
    if not isinstance(expected_hash, str) or not expected_hash.strip():
        raise AssistantToolError("Completed runs require a canonical_bundle_hash.")
    path = Path(bundle_path)
    if not path.is_file():
        raise AssistantToolError("Research bundle was not written before completion.")
    digest = canonical_bundle_hash(path.read_bytes())
    if digest != expected_hash:
        raise AssistantToolError("Written research bundle hash does not match reported provenance.")


@dataclass(frozen=True)
class OrchestrationResult:
    status: str
    capability_id: str
    payload: dict[str, Any]


def confirmed_run_feedback(result: OrchestrationResult) -> tuple[str, str]:
    """Map a confirmed-run orchestration result to UI level and message.

    Returns ``(level, message)`` where level is ``success``, ``warning``, or
    ``error``. Callers must not assume success merely because no exception was
    raised: cancel races return ``status="cancelled"``.
    """
    if result.status == OrchestrationStatus.COMPLETED.value:
        return "success", "Research run completed and provenance was recorded."
    error = result.payload.get("error") if isinstance(result.payload, dict) else None
    message = None
    if isinstance(error, Mapping):
        message = error.get("message")
    if not isinstance(message, str) or not message.strip():
        message = f"Research run ended with status {result.status}."
    if result.status == OrchestrationStatus.CANCELLED.value:
        return "warning", message
    return "error", message


def list_payload_or_error(
    result: OrchestrationResult,
    *,
    items_key: str,
    default_error: str,
) -> tuple[list[Any], str | None]:
    """Return list items from a completed dispatch, else an error message.

    Failed/gated outcomes must not be coerced into an empty success list.
    """
    if result.status == OrchestrationStatus.COMPLETED.value:
        items = result.payload.get(items_key, []) if isinstance(result.payload, dict) else []
        if not isinstance(items, list):
            return [], default_error
        return items, None
    error = result.payload.get("error") if isinstance(result.payload, dict) else None
    message = error.get("message") if isinstance(error, Mapping) else None
    if not isinstance(message, str) or not message.strip():
        message = default_error
    return [], message


def _assert_handler_coverage() -> None:
    missing = sorted(
        capability.capability_id
        for capability in FEATURE_PARITY_REGISTRY
        if capability.mode.value != "unsupported"
        and capability.capability_id not in HANDLER_REGISTRY
    )
    if missing:
        raise RuntimeError(
            "Executable or routed registry capabilities lack handlers: " + ", ".join(missing)
        )


_assert_handler_coverage()


class AssistantOrchestrator:
    """Coordinate only declared assistant capabilities."""

    def __init__(self, *, tools: AssistantTools, repository: LocalThesisRepository) -> None:
        self.tools = tools
        self.repository = repository

    def _tools_for_envelope(self, limits: ToolLimits):
        """Return tools constrained by the capability envelope.

        Custom tool doubles used in tests keep their own methods. Production
        AssistantTools instances are cloned only when the envelope tightens
        their default limits.
        """
        if not isinstance(self.tools, AssistantTools):
            return self.tools
        if limits == self.tools.limits:
            return self.tools
        return AssistantTools(data_roots=self.tools.data_roots, limits=limits)

    def dispatch(
        self,
        request: AssistantRequest,
        *,
        confirmed: bool = False,
        thesis_id: str | None = None,
        conversation_id: str | None = None,
    ) -> OrchestrationResult:
        """Validate, gate, execute one supported request, and record its outcome."""
        try:
            capability = validate_capability_request(request)
        except UnknownCapabilityError as exc:
            result = OrchestrationResult(
                status=OrchestrationStatus.UNAVAILABLE.value,
                capability_id=request.capability_id,
                payload={
                    "error": structured_error(
                        category="unknown_capability",
                        retryable=False,
                        remediation="Request a capability declared in FEATURE_PARITY_REGISTRY.",
                        message=str(exc),
                    ).to_dict()
                },
            )
            self._record_audit(
                result,
                request=request,
                thesis_id=thesis_id,
                conversation_id=conversation_id,
            )
            return result
        except AssistantContractError as exc:
            result = OrchestrationResult(
                status=OrchestrationStatus.UNAVAILABLE.value,
                capability_id=request.capability_id,
                payload={
                    "error": structured_error(
                        category="contract",
                        retryable=False,
                        remediation="Correct the request or choose a supported capability.",
                        message=str(exc),
                    ).to_dict()
                },
            )
            self._record_audit(
                result,
                request=request,
                thesis_id=thesis_id,
                conversation_id=conversation_id,
            )
            return result

        if self._requires_confirmation(capability.confirmation, request) and not confirmed:
            result = OrchestrationResult(
                status=OrchestrationStatus.APPROVAL_REQUIRED.value,
                capability_id=request.capability_id,
                payload={
                    "error": structured_error(
                        category="confirmation",
                        retryable=True,
                        remediation="Confirm the action explicitly, then retry the request.",
                        message="Confirmation is required before this action.",
                    ).to_dict()
                },
            )
            self._record_audit(
                result,
                request=request,
                thesis_id=thesis_id,
                conversation_id=conversation_id,
            )
            return result

        handler = get_handler(request.capability_id)
        if handler is None:
            result = OrchestrationResult(
                status=OrchestrationStatus.UNAVAILABLE.value,
                capability_id=request.capability_id,
                payload={
                    "error": structured_error(
                        category="missing_handler",
                        retryable=False,
                        remediation="Mark the capability unsupported or register a typed handler.",
                        message=f"No orchestrator handler for {request.capability_id}.",
                    ).to_dict()
                },
            )
            self._record_audit(
                result,
                request=request,
                thesis_id=thesis_id,
                conversation_id=conversation_id,
            )
            return result

        base_limits = self.tools.limits if isinstance(self.tools.limits, ToolLimits) else None
        limits = tool_limits_from_envelope(capability.resource_envelope, base=base_limits)
        bounded_tools = self._tools_for_envelope(limits)
        context = HandlerContext(tools=bounded_tools, capability=capability, limits=limits)
        try:
            payload = handler(request, context)
            payload = {
                **payload,
                "resource_limits": {
                    "max_grid_cells": limits.max_grid_cells,
                    "max_simulations": limits.max_simulations,
                    "max_walk_forward_matrix_cells": limits.max_walk_forward_matrix_cells,
                },
            }
            result = OrchestrationResult(
                status=OrchestrationStatus.COMPLETED.value,
                capability_id=request.capability_id,
                payload=payload,
            )
        except (AssistantToolError, ValueError, TypeError, KeyError) as exc:
            result = OrchestrationResult(
                status=OrchestrationStatus.FAILED.value,
                capability_id=request.capability_id,
                payload={
                    "error": structured_error(
                        category="tool",
                        retryable=isinstance(exc, AssistantToolError),
                        remediation="Correct the request payload, paths, or resource limits.",
                        message=str(exc),
                    ).to_dict()
                },
            )
        except Exception as exc:  # noqa: BLE001 - audit any unexpected failure closed
            result = OrchestrationResult(
                status=OrchestrationStatus.FAILED.value,
                capability_id=request.capability_id,
                payload={
                    "error": structured_error(
                        category="internal",
                        retryable=False,
                        remediation="Inspect the tool transcript and retry after correcting the cause.",
                        message=f"{type(exc).__name__}: {exc}",
                    ).to_dict()
                },
            )
        self._record_audit(
            result,
            request=request,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
        )
        return result

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
        """Execute one confirmed spec through the audited run lifecycle."""
        spec = self.repository.get_spec_version(thesis_id, spec_version)
        if spec.status != "confirmed":
            raise ValueError("Only confirmed specifications may execute.")
        thesis = self.repository.get_thesis(thesis_id)
        run_spec = map_persisted_confirmed_run_spec(
            name=thesis.name,
            choices=spec.normalized_run_spec,
        )
        request = AssistantRequest(
            capability_id="PIPELINE.run_experiment",
            payload={"run_spec": run_spec, "output_path": str(output_path)},
        )
        capability = validate_capability_request(request)
        if capability.confirmation is not ConfirmationLevel.EXPLICIT_CONFIRMATION:
            raise ValueError("Run capability must require explicit confirmation.")
        base_limits = self.tools.limits if isinstance(self.tools.limits, ToolLimits) else None
        limits = tool_limits_from_envelope(capability.resource_envelope, base=base_limits)
        bounded_tools = self._tools_for_envelope(limits)
        run = self.repository.start_run(
            thesis_id,
            spec_version=spec_version,
            request={
                "run_spec": run_spec,
                "output_path": str(output_path),
                "resource_limits": {
                    "max_grid_cells": limits.max_grid_cells,
                    "max_simulations": limits.max_simulations,
                    "max_walk_forward_matrix_cells": limits.max_walk_forward_matrix_cells,
                },
            },
        )
        result: dict[str, Any] | None = None
        warnings: tuple[str, ...] = ()
        provenance: dict[str, Any] | None = None
        try:
            result = bounded_tools.run_experiment_to_bundle(run_spec, output_path=output_path)
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
            provenance = {
                "bundle_path": result["bundle_path"],
                "canonical_bundle_hash": result["canonical_bundle_hash"],
                "dataset_fingerprint": result["dataset_fingerprint"],
                "tool_version": result["tool_version"],
                "summary": result["summary"],
                "warnings": list(warnings),
                "effective_configuration": result.get("effective_configuration"),
                "resolved_paths": result.get("resolved_paths"),
                "resource_limits": result.get("resource_limits"),
                "seeds": result.get("seeds"),
            }
            # Never mark a run completed before its portable bundle is readable
            # and the reported canonical hash verifies against those bytes.
            _assert_readable_bundle_provenance(result)
            completed = self.repository.complete_run(
                thesis_id,
                run.run_id,
                expected_revision=run.revision,
                provenance=provenance,
                warnings=warnings,
            )
        except BaseException as exc:
            return self._finalize_raced_or_failed_run(
                exc,
                request=request,
                thesis_id=thesis_id,
                run_id=run.run_id,
                conversation_id=conversation_id,
                result=result,
                provenance=provenance,
                warnings=warnings,
            )
        completed_result = OrchestrationResult(
            status=OrchestrationStatus.COMPLETED.value,
            capability_id="PIPELINE.run_experiment",
            payload={"run_id": completed.run_id, **result},
        )
        # Terminal run provenance is already persisted. A conversation-audit
        # race must not convert a completed execution into a UI failure.
        self._record_audit(
            completed_result,
            request=request,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            extra={
                "run_id": completed.run_id,
                "canonical_bundle_hash": result["canonical_bundle_hash"],
            },
            best_effort=True,
        )
        return completed_result

    def cancel_run(
        self,
        *,
        thesis_id: str,
        run_id: str,
        reason: str = "Cancelled by user.",
        conversation_id: str | None = None,
    ) -> OrchestrationResult:
        """Cancel one running research run and record a terminal audit entry.

        If the run is no longer cancellable (for example it completed between
        UI render and click), return a structured failure instead of raising.
        """
        request = AssistantRequest(
            capability_id="PIPELINE.run_experiment",
            payload={"run_id": run_id, "action": "cancel"},
        )
        try:
            run = self.repository.get_run(thesis_id, run_id)
            cancelled = self.repository.cancel_run(
                thesis_id,
                run_id,
                expected_revision=run.revision,
                reason=reason,
            )
        except (InvalidStateTransitionError, RepositoryConflictError) as exc:
            result = OrchestrationResult(
                status=OrchestrationStatus.FAILED.value,
                capability_id="PIPELINE.run_experiment",
                payload={
                    "run_id": run_id,
                    "error": structured_error(
                        category="lifecycle",
                        retryable=True,
                        remediation=(
                            "Refresh the run list; only currently running research "
                            "runs can be cancelled."
                        ),
                        message=str(exc),
                    ).to_dict(),
                },
            )
            self._record_audit(
                result,
                request=request,
                thesis_id=thesis_id,
                conversation_id=conversation_id,
                extra={"run_id": run_id},
                best_effort=True,
            )
            return result
        result = OrchestrationResult(
            status=OrchestrationStatus.CANCELLED.value,
            capability_id="PIPELINE.run_experiment",
            payload={
                "run_id": cancelled.run_id,
                "error": structured_error(
                    category="cancellation",
                    retryable=False,
                    remediation="Start a new confirmed run if the research should continue.",
                    message=reason,
                ).to_dict(),
            },
        )
        self._record_audit(
            result,
            request=request,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            extra={"run_id": cancelled.run_id},
            best_effort=True,
        )
        return result

    def _finalize_raced_or_failed_run(
        self,
        exc: BaseException,
        *,
        request: AssistantRequest,
        thesis_id: str,
        run_id: str,
        conversation_id: str | None,
        result: dict[str, Any] | None,
        provenance: dict[str, Any] | None,
        warnings: tuple[str, ...],
    ) -> OrchestrationResult:
        """Resolve cancel/complete races without overturning terminal cancel state."""
        current = self.repository.get_run(thesis_id, run_id)
        if current.status == "cancelled":
            if provenance is not None and current.provenance is None:
                try:
                    current = self.repository.attach_cancelled_run_provenance(
                        thesis_id,
                        run_id,
                        expected_revision=current.revision,
                        provenance=provenance,
                        warnings=warnings,
                    )
                except (InvalidStateTransitionError, RepositoryConflictError):
                    current = self.repository.get_run(thesis_id, run_id)
            reason = "Cancelled during execution."
            if isinstance(current.error, dict) and current.error.get("reason"):
                reason = str(current.error["reason"])
            payload: dict[str, Any] = {
                "run_id": current.run_id,
                "error": structured_error(
                    category="cancellation",
                    retryable=False,
                    remediation="Start a new confirmed run if the research should continue.",
                    message=reason,
                ).to_dict(),
            }
            if result is not None:
                payload.update(result)
            cancelled_result = OrchestrationResult(
                status=OrchestrationStatus.CANCELLED.value,
                capability_id="PIPELINE.run_experiment",
                payload=payload,
            )
            self._record_audit(
                cancelled_result,
                request=request,
                thesis_id=thesis_id,
                conversation_id=conversation_id,
                extra={
                    "run_id": current.run_id,
                    **(
                        {"canonical_bundle_hash": result["canonical_bundle_hash"]}
                        if result is not None
                        else {}
                    ),
                },
                best_effort=True,
            )
            return cancelled_result

        error = structured_error(
            category="execution",
            retryable=False,
            remediation="Inspect the failed run error, correct the specification, and retry.",
            message=f"{type(exc).__name__}: {exc}",
        ).to_dict()
        if current.status == "running":
            try:
                self.repository.fail_run(
                    thesis_id,
                    run_id,
                    expected_revision=current.revision,
                    error=error,
                )
            except (InvalidStateTransitionError, RepositoryConflictError):
                current = self.repository.get_run(thesis_id, run_id)
                if current.status == "cancelled":
                    return self._finalize_raced_or_failed_run(
                        exc,
                        request=request,
                        thesis_id=thesis_id,
                        run_id=run_id,
                        conversation_id=conversation_id,
                        result=result,
                        provenance=provenance,
                        warnings=warnings,
                    )
        failed = OrchestrationResult(
            status=OrchestrationStatus.FAILED.value,
            capability_id="PIPELINE.run_experiment",
            payload={"run_id": run_id, "error": error},
        )
        self._record_audit(
            failed,
            request=request,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            best_effort=True,
        )
        raise exc

    def _requires_confirmation(self, level: ConfirmationLevel, request: AssistantRequest) -> bool:
        if level is ConfirmationLevel.NONE:
            return False
        action = request.payload.get("action")
        if isinstance(action, str) and action in _READ_ONLY_ACTIONS:
            return False
        return level in {
            ConfirmationLevel.USER_REQUEST,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        }

    def _record_audit(
        self,
        result: OrchestrationResult,
        *,
        request: AssistantRequest,
        thesis_id: str | None,
        conversation_id: str | None,
        extra: dict[str, Any] | None = None,
        best_effort: bool = False,
    ) -> None:
        if thesis_id is None or conversation_id is None:
            return
        try:
            conversation = self.repository.get_conversation(thesis_id, conversation_id)
            tool_entry = {
                "capability_id": result.capability_id,
                "request": request.to_dict(),
                "status": result.status,
            }
            if extra:
                tool_entry.update(extra)
            if "error" in result.payload:
                tool_entry["error"] = result.payload["error"]
            self.repository.append_conversation_message(
                thesis_id,
                conversation_id,
                expected_revision=conversation.revision,
                message={
                    "role": "tool",
                    "content": f"{result.status} {result.capability_id}.",
                },
                tool_entry=tool_entry,
            )
        except Exception:
            if not best_effort:
                raise
