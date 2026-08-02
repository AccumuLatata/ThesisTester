"""Versioned contracts and capability registry for the AI Research Assistant."""

from thesistester.assistant.contracts import (
    ASSISTANT_CONTRACT_SCHEMA_VERSION,
    AssistantContractError,
    AssistantRequest,
    Capability,
    CapabilityMode,
    ConfirmationLevel,
    ResourceEnvelope,
    UnknownCapabilityError,
)
from thesistester.assistant.registry import (
    FEATURE_PARITY_REGISTRY,
    get_capability,
    validate_capability_request,
)
from thesistester.assistant.repository import (
    ASSISTANT_REPOSITORY_SCHEMA_VERSION,
    AssistantRepositoryError,
    Conversation,
    InvalidStateTransitionError,
    LocalThesisRepository,
    RepositoryConflictError,
    RepositoryCorruptionError,
    RepositoryReadOnlyError,
    ResearchRun,
    SpecVersion,
    Thesis,
)
from thesistester.assistant.tools import AssistantToolError, AssistantTools, ToolLimits
from thesistester.assistant.thesis_compiler import (
    COMPILER_VERSION,
    ThesisDraft,
    compile_run_spec,
    compile_thesis,
)
from thesistester.assistant.explainer import (
    EvidencePacket,
    build_evidence_packet,
    compare_evidence,
    explain_evidence,
)
from thesistester.assistant.orchestrator import AssistantOrchestrator, OrchestrationResult
from thesistester.assistant.comparison import COMPARISON_SCHEMA_VERSION, Comparison

__all__ = [
    "ASSISTANT_CONTRACT_SCHEMA_VERSION",
    "ASSISTANT_REPOSITORY_SCHEMA_VERSION",
    "AssistantContractError",
    "AssistantRepositoryError",
    "AssistantOrchestrator",
    "AssistantToolError",
    "AssistantTools",
    "AssistantRequest",
    "Capability",
    "CapabilityMode",
    "COMPILER_VERSION",
    "COMPARISON_SCHEMA_VERSION",
    "Comparison",
    "EvidencePacket",
    "ConfirmationLevel",
    "Conversation",
    "FEATURE_PARITY_REGISTRY",
    "InvalidStateTransitionError",
    "LocalThesisRepository",
    "OrchestrationResult",
    "RepositoryConflictError",
    "RepositoryCorruptionError",
    "RepositoryReadOnlyError",
    "ResearchRun",
    "ResourceEnvelope",
    "SpecVersion",
    "Thesis",
    "ThesisDraft",
    "ToolLimits",
    "UnknownCapabilityError",
    "get_capability",
    "validate_capability_request",
    "compile_thesis",
    "compile_run_spec",
    "build_evidence_packet",
    "compare_evidence",
    "explain_evidence",
]
