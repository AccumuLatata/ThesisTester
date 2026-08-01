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

__all__ = [
    "ASSISTANT_CONTRACT_SCHEMA_VERSION",
    "ASSISTANT_REPOSITORY_SCHEMA_VERSION",
    "AssistantContractError",
    "AssistantRepositoryError",
    "AssistantToolError",
    "AssistantTools",
    "AssistantRequest",
    "Capability",
    "CapabilityMode",
    "ConfirmationLevel",
    "Conversation",
    "FEATURE_PARITY_REGISTRY",
    "InvalidStateTransitionError",
    "LocalThesisRepository",
    "RepositoryConflictError",
    "RepositoryCorruptionError",
    "RepositoryReadOnlyError",
    "ResearchRun",
    "ResourceEnvelope",
    "SpecVersion",
    "Thesis",
    "ToolLimits",
    "UnknownCapabilityError",
    "get_capability",
    "validate_capability_request",
]
