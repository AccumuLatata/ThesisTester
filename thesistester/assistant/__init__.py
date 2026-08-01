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

__all__ = [
    "ASSISTANT_CONTRACT_SCHEMA_VERSION",
    "AssistantContractError",
    "AssistantRequest",
    "Capability",
    "CapabilityMode",
    "ConfirmationLevel",
    "FEATURE_PARITY_REGISTRY",
    "ResourceEnvelope",
    "UnknownCapabilityError",
    "get_capability",
    "validate_capability_request",
]
