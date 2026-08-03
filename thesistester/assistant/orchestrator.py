"""Registry-gated coordination for assistant requests.

The orchestrator owns confirmation decisions, resource-envelope enforcement, and
audit recording. It does not interpret prose, run engine internals, or grant
arbitrary tool access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping
from uuid import uuid4

from thesistester.assistant.comparison import Comparison
from thesistester.assistant.contracts import (
    AssistantContractError,
    AssistantRequest,
    ConfirmationLevel,
    OrchestrationStatus,
    UnknownCapabilityError,
    structured_error,
)
from thesistester.assistant.explainer import (
    assert_claims_grounded,
    compare_evidence,
    explain_evidence_report,
)
from thesistester.assistant.handlers import (
    HANDLER_REGISTRY,
    HandlerContext,
    get_handler,
    tool_limits_from_envelope,
)
from thesistester.assistant.llm import StructuredLLMClient
from thesistester.assistant.llm_explainer import explain_packet_with_llm
from thesistester.assistant.llm_intent import propose_thesis_draft
from thesistester.assistant.registry import FEATURE_PARITY_REGISTRY, validate_capability_request
from thesistester.assistant.repository import (
    AssistantRepositoryError,
    Conversation,
    InvalidStateTransitionError,
    LocalThesisRepository,
    RepositoryConflictError,
    ResearchRun,
    SpecVersion,
    Thesis,
)
from thesistester.assistant.thesis_compiler import (
    ThesisDraft,
    compile_thesis,
    map_persisted_confirmed_run_spec,
    map_thesis_choices_to_run_spec,
)
from thesistester.assistant.tools import AssistantToolError, AssistantTools, ToolLimits
from thesistester.assistant.workspace import (
    evidence_packet_from_payload,
    require_run_bundle_hash,
)
from thesistester.persistence.local_store import get_store_root
from thesistester.research_bundle import (
    apply_research_bundle_to_session,
    canonical_bundle_hash,
)


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

    @classmethod
    def for_local_workspace(
        cls, *, repository: LocalThesisRepository | None = None
    ) -> AssistantOrchestrator:
        """Build the production Streamlit workspace orchestrator.

        The page must not construct tools or repository clients itself.
        """
        roots = (Path.cwd().resolve(), get_store_root().resolve())
        return cls(
            tools=AssistantTools(data_roots=roots),
            repository=repository or LocalThesisRepository(),
        )

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
                # CAI-3: persist cold/warm cache outcome for provenance cards.
                "cache_provenance": result.get("cache_provenance"),
                "execution_origin": result.get("execution_origin"),
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

    # --- Workspace façade (presentation pages must not call the repository) ---

    def create_thesis(self, *, name: str, tags: tuple[str, ...] = ()) -> Thesis:
        """Create one thesis through the repository façade."""
        return self.repository.create_thesis(name=name, tags=tags)

    def list_theses(self, *, include_archived: bool = True) -> tuple[Thesis, ...]:
        """List theses through the repository façade."""
        return self.repository.list_theses(include_archived=include_archived)

    def get_thesis(self, thesis_id: str) -> Thesis:
        """Load one thesis through the repository façade."""
        return self.repository.get_thesis(thesis_id)

    def rename_thesis(self, thesis_id: str, *, name: str, expected_revision: int) -> Thesis:
        """Rename one thesis through the repository façade."""
        return self.repository.rename_thesis(
            thesis_id, name=name, expected_revision=expected_revision
        )

    def clone_thesis(self, thesis_id: str, *, name: str | None = None) -> Thesis:
        """Clone one thesis through the repository façade."""
        return self.repository.clone_thesis(thesis_id, name=name)

    def archive_thesis(self, thesis_id: str, *, expected_revision: int) -> Thesis:
        """Archive one thesis through the repository façade."""
        return self.repository.archive_thesis(thesis_id, expected_revision=expected_revision)

    def restore_thesis(self, thesis_id: str, *, expected_revision: int) -> Thesis:
        """Restore one archived thesis through the repository façade."""
        return self.repository.restore_thesis(thesis_id, expected_revision=expected_revision)

    def ensure_conversation(
        self, thesis_id: str, *, preferred_conversation_id: str | None = None
    ) -> Conversation:
        """Return the preferred or latest conversation, creating one if needed."""
        conversations = self.repository.list_conversations(thesis_id)
        known = {item.conversation_id: item for item in conversations}
        if preferred_conversation_id in known:
            return known[preferred_conversation_id]
        if conversations:
            return conversations[-1]
        return self.repository.create_conversation(thesis_id)

    def list_conversations(self, thesis_id: str) -> tuple[Conversation, ...]:
        """List conversations through the repository façade."""
        return self.repository.list_conversations(thesis_id)

    def get_conversation(self, thesis_id: str, conversation_id: str) -> Conversation:
        """Load one conversation through the repository façade."""
        return self.repository.get_conversation(thesis_id, conversation_id)

    def list_spec_versions(self, thesis_id: str) -> tuple[SpecVersion, ...]:
        """List specification versions through the repository façade."""
        return self.repository.list_spec_versions(thesis_id)

    def list_runs(self, thesis_id: str) -> tuple[ResearchRun, ...]:
        """List research runs through the repository façade."""
        return self.repository.list_runs(thesis_id)

    def list_comparisons(self, thesis_id: str) -> tuple[Comparison, ...]:
        """List persisted comparisons through the repository façade."""
        return self.repository.list_comparisons(thesis_id)

    def draft_specification(
        self,
        *,
        thesis_id: str,
        prompt: str,
        choices: Mapping[str, Any],
    ) -> SpecVersion:
        """Compile staged choices into a persisted non-executing specification."""
        draft = compile_thesis(prompt, choices=choices)
        return self.repository.create_spec_version(
            thesis_id,
            normalized_run_spec=draft.normalized_run_spec,
            status="ready_for_confirmation"
            if draft.ready_for_confirmation
            else "needs_clarification",
            unresolved_assumptions=draft.unresolved_assumptions,
            compiler_version="1",
        )

    def validate_choices(
        self,
        *,
        thesis_id: str,
        conversation_id: str | None,
        thesis_name: str,
        choices: Mapping[str, Any],
    ) -> OrchestrationResult:
        """Map staged choices to a canonical RunSpec and validate through the registry."""
        try:
            validated = map_thesis_choices_to_run_spec(name=thesis_name, choices=choices)
        except ValueError as exc:
            return OrchestrationResult(
                status=OrchestrationStatus.FAILED.value,
                capability_id="PIPELINE.validate_run_spec",
                payload={
                    "error": structured_error(
                        category="validation",
                        retryable=True,
                        remediation="Correct structured controls and validate again.",
                        message=str(exc),
                    ).to_dict()
                },
            )
        result = self.dispatch(
            AssistantRequest(
                capability_id="PIPELINE.validate_run_spec",
                payload={"run_spec": validated},
            ),
            thesis_id=thesis_id,
            conversation_id=conversation_id,
        )
        if result.status == OrchestrationStatus.COMPLETED.value:
            return OrchestrationResult(
                status=result.status,
                capability_id=result.capability_id,
                payload={
                    **result.payload,
                    "choices": dict(choices),
                    "spec": validated,
                },
            )
        return result

    def confirm_validated_spec(
        self,
        *,
        thesis_id: str,
        validated_spec: Mapping[str, Any],
        confirmation_note: str = "Confirmed validated executable RunSpec in UI",
    ) -> SpecVersion:
        """Persist and confirm one already-validated executable RunSpec."""
        executable = self.repository.create_spec_version(
            thesis_id,
            normalized_run_spec=dict(validated_spec),
            status="ready_for_confirmation",
            unresolved_assumptions=(),
            compiler_version="runspec-2",
        )
        return self.repository.confirm_spec_version(
            thesis_id,
            executable.version,
            confirmation_note=confirmation_note,
        )

    def default_bundle_output_path(self, thesis_id: str) -> Path:
        """Return a thesis-scoped portable bundle path under the local store."""
        return (
            get_store_root()
            / "assistant"
            / "theses"
            / thesis_id
            / "bundles"
            / f"{uuid4().hex}.research.zip"
        )

    def explain_run(
        self,
        *,
        thesis_id: str,
        conversation_id: str | None,
        run: ResearchRun,
    ) -> OrchestrationResult:
        """Load hash-verified evidence and return a deterministic explanation."""
        if run.status != "completed" or not isinstance(run.provenance, Mapping):
            raise ValueError("Only completed runs with provenance can be explained.")
        bundle_path = run.provenance.get("bundle_path")
        expected_hash = require_run_bundle_hash(run.provenance)
        if not isinstance(bundle_path, str) or not bundle_path.strip():
            raise ValueError("Completed run is missing bundle_path provenance.")
        result = self.dispatch(
            AssistantRequest(
                capability_id="BUNDLE.import",
                payload={
                    "action": "evidence",
                    "bundle_path": bundle_path,
                    "expected_hash": expected_hash,
                    "provenance": dict(run.provenance),
                },
            ),
            thesis_id=thesis_id,
            conversation_id=conversation_id,
        )
        if result.status != OrchestrationStatus.COMPLETED.value:
            return result
        packet = evidence_packet_from_payload(result.payload)
        report = explain_evidence_report(packet)
        assert_claims_grounded(packet, report)
        return OrchestrationResult(
            status=result.status,
            capability_id=result.capability_id,
            payload={
                **result.payload,
                "explanation": report["narrative"],
                "explanation_report": report,
            },
        )

    def explain_run_with_llm(
        self,
        client: StructuredLLMClient,
        *,
        thesis_id: str,
        conversation_id: str | None,
        run: ResearchRun,
    ) -> OrchestrationResult:
        """Load hash-verified evidence and paraphrase it through a bounded LLM client."""
        evidence = self.explain_run(
            thesis_id=thesis_id,
            conversation_id=conversation_id,
            run=run,
        )
        if evidence.status != OrchestrationStatus.COMPLETED.value:
            return evidence
        packet = evidence_packet_from_payload(evidence.payload)
        explanation = explain_packet_with_llm(client, packet=packet)
        return OrchestrationResult(
            status=evidence.status,
            capability_id=evidence.capability_id,
            payload={
                **evidence.payload,
                "llm_explanation": explanation,
                "provider_attempts": getattr(client, "last_attempt_count", None),
            },
        )

    def export_run(
        self,
        *,
        thesis_id: str,
        conversation_id: str | None,
        run: ResearchRun,
    ) -> OrchestrationResult:
        """Build the markdown report and research artifact for one completed run."""
        if run.status != "completed" or not isinstance(run.provenance, Mapping):
            raise ValueError("Only completed runs with provenance can be exported.")
        bundle_path = run.provenance.get("bundle_path")
        expected_hash = require_run_bundle_hash(run.provenance)
        if not isinstance(bundle_path, str) or not bundle_path.strip():
            raise ValueError("Completed run is missing bundle_path provenance.")
        return self.dispatch(
            AssistantRequest(
                capability_id="EXPORT.build_research_artifact",
                payload={
                    "bundle_path": bundle_path,
                    "expected_hash": expected_hash,
                },
            ),
            confirmed=True,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
        )

    def compare_completed_runs(
        self,
        *,
        thesis_id: str,
        conversation_id: str | None,
        left_run: ResearchRun,
        right_run: ResearchRun,
    ) -> OrchestrationResult:
        """Compare two completed runs, persist the comparison, and return evidence."""
        packets = []
        for run in (left_run, right_run):
            if run.status != "completed" or not isinstance(run.provenance, Mapping):
                raise ValueError("Comparison requires completed runs with provenance.")
            bundle_path = run.provenance.get("bundle_path")
            expected_hash = require_run_bundle_hash(run.provenance)
            if not isinstance(bundle_path, str) or not bundle_path.strip():
                raise ValueError("Completed run is missing bundle_path provenance.")
            result = self.dispatch(
                AssistantRequest(
                    capability_id="BUNDLE.import",
                    payload={
                        "action": "evidence",
                        "bundle_path": bundle_path,
                        "expected_hash": expected_hash,
                        "provenance": dict(run.provenance),
                    },
                ),
                thesis_id=thesis_id,
                conversation_id=conversation_id,
            )
            if result.status != OrchestrationStatus.COMPLETED.value:
                return result
            packets.append(evidence_packet_from_payload(result.payload))
        comparison = compare_evidence(*packets)
        record = Comparison.create(
            thesis_id=thesis_id,
            left_run_id=left_run.run_id,
            right_run_id=right_run.run_id,
            left_bundle_hash=str(left_run.provenance["canonical_bundle_hash"]),
            right_bundle_hash=str(right_run.provenance["canonical_bundle_hash"]),
            evidence=comparison,
            conclusions=tuple(comparison.get("conclusions") or ()),
        )
        # Persistence is best-effort: computed comparison evidence must still
        # reach the UI when the immutable comparison write fails.
        try:
            saved = self.repository.save_comparison(record)
        except AssistantRepositoryError as exc:
            return OrchestrationResult(
                status=OrchestrationStatus.COMPLETED.value,
                capability_id="BUNDLE.import",
                payload={
                    "comparison": comparison,
                    "record": None,
                    "run_ids": [left_run.run_id, right_run.run_id],
                    "persistence_error": str(exc),
                },
            )
        return OrchestrationResult(
            status=OrchestrationStatus.COMPLETED.value,
            capability_id="BUNDLE.import",
            payload={
                "comparison": comparison,
                "record": saved.to_dict(),
                "run_ids": [left_run.run_id, right_run.run_id],
            },
        )

    def analyze_portfolio_runs(
        self,
        *,
        thesis_id: str,
        conversation_id: str | None,
        runs: list[ResearchRun],
        instrument: str,
    ) -> OrchestrationResult:
        """Analyze explicitly selected completed-run bundles as a portfolio."""
        if len(runs) < 2:
            raise ValueError("Portfolio analysis requires at least two completed runs.")
        bundle_paths: list[str] = []
        expected_hashes: list[str] = []
        for run in runs:
            if run.status != "completed" or not isinstance(run.provenance, Mapping):
                raise ValueError("Portfolio analysis requires completed runs with provenance.")
            bundle_path = run.provenance.get("bundle_path")
            expected_hash = require_run_bundle_hash(run.provenance)
            if not isinstance(bundle_path, str) or not bundle_path.strip():
                raise ValueError("Completed run is missing bundle_path provenance.")
            bundle_paths.append(bundle_path)
            expected_hashes.append(expected_hash)
        return self.dispatch(
            AssistantRequest(
                capability_id="PORTFOLIO.analyze",
                payload={
                    "bundle_paths": bundle_paths,
                    "expected_hashes": expected_hashes,
                    "instrument": instrument,
                },
            ),
            confirmed=True,
            thesis_id=thesis_id,
            conversation_id=conversation_id,
        )

    def restore_run_bundle_to_session(
        self,
        *,
        thesis_id: str,
        run_id: str,
        session_state: MutableMapping[str, Any],
    ) -> dict[str, Any]:
        """Hash-verify a completed run bundle and hand it to research pages."""
        run = self.repository.get_run(thesis_id, run_id)
        if run.status != "completed" or not isinstance(run.provenance, Mapping):
            raise ValueError("Only completed runs with provenance can be restored.")
        bundle_path = run.provenance.get("bundle_path")
        expected_hash = require_run_bundle_hash(run.provenance)
        if not isinstance(bundle_path, str) or not bundle_path.strip():
            raise ValueError("Completed run is missing bundle_path provenance.")
        if not isinstance(self.tools, AssistantTools):
            raise AssistantToolError("Bundle restoration requires AssistantTools.")
        loaded = self.tools.load_verified_bundle_session(bundle_path, expected_hash=expected_hash)
        applied = apply_research_bundle_to_session(
            {"session_values": loaded["session_values"]},
            session_state,
        )
        handoff = {
            "thesis_id": thesis_id,
            "run_id": run_id,
            "bundle_path": loaded["bundle_path"],
            "canonical_bundle_hash": loaded["canonical_bundle_hash"],
            **applied,
        }
        # Bundle session values are not the staged assistant RunSpec; drop any
        # prior validated confirmation candidate so Confirm cannot target stale
        # choices after a hash-verified research-page restore.
        session_state["assistant_validated_run_spec"] = None
        session_state["assistant_bundle_handoff"] = handoff
        return handoff

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
