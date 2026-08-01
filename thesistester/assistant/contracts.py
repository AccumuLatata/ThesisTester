"""JSON-safe, versioned contracts for the AI Research Assistant.

This module defines metadata only. It does not execute research, persist state,
import Streamlit, or import engine/analytics modules.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

ASSISTANT_CONTRACT_SCHEMA_VERSION = 1
_CAPABILITY_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class AssistantContractError(ValueError):
    """Raised when assistant metadata or requests violate the public contract."""


class UnknownCapabilityError(AssistantContractError):
    """Raised when a request names a capability absent from the registry."""


class CapabilityMode(str, Enum):
    """Assistant support classification for a user-visible product capability."""

    EXECUTABLE = "executable"
    INSPECT_ONLY = "inspect_only"
    IMPORT_EXPORT = "import_export"
    UNSUPPORTED = "unsupported"


class ConfirmationLevel(str, Enum):
    """User acknowledgement required before an assistant action."""

    NONE = "none"
    USER_REQUEST = "user_request"
    EXPLICIT_CONFIRMATION = "explicit_confirmation"


@dataclass(frozen=True)
class ResourceEnvelope:
    """Declared limits for a future assistant tool implementation."""

    max_grid_cells: int | None = None
    max_simulations: int | None = None
    max_walk_forward_folds: int | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("max_grid_cells", self.max_grid_cells),
            ("max_simulations", self.max_simulations),
            ("max_walk_forward_folds", self.max_walk_forward_folds),
        ):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 1
            ):
                raise AssistantContractError(f"{name} must be a positive integer or None.")

    def to_dict(self) -> dict[str, int | None]:
        """Return a JSON-safe representation."""
        return {
            "max_grid_cells": self.max_grid_cells,
            "max_simulations": self.max_simulations,
            "max_walk_forward_folds": self.max_walk_forward_folds,
        }


@dataclass(frozen=True)
class Capability:
    """One feature-parity row for a user-visible ThesisTester capability."""

    capability_id: str
    ui_location: str
    user_action: str
    public_symbol: str | None
    mode: CapabilityMode
    confirmation: ConfirmationLevel
    resource_envelope: ResourceEnvelope = ResourceEnvelope()
    limitation: str | None = None

    def __post_init__(self) -> None:
        if not _CAPABILITY_ID_RE.fullmatch(self.capability_id):
            raise AssistantContractError(
                "capability_id must use upper-case section and lower-case action segments."
            )
        if not self.ui_location.strip():
            raise AssistantContractError("ui_location must be non-empty.")
        if not self.user_action.strip():
            raise AssistantContractError("user_action must be non-empty.")
        if self.mode is CapabilityMode.UNSUPPORTED and not self.limitation:
            raise AssistantContractError("Unsupported capabilities must document a limitation.")

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-safe representation."""
        return {
            "schema_version": ASSISTANT_CONTRACT_SCHEMA_VERSION,
            "capability_id": self.capability_id,
            "ui_location": self.ui_location,
            "user_action": self.user_action,
            "public_symbol": self.public_symbol,
            "mode": self.mode.value,
            "confirmation": self.confirmation.value,
            "resource_envelope": self.resource_envelope.to_dict(),
            "limitation": self.limitation,
        }


def _validate_json_value(value: Any, *, field_name: str) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise AssistantContractError(f"{field_name} must not contain non-finite floats.")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, field_name=f"{field_name}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AssistantContractError(f"{field_name} keys must be strings.")
            _validate_json_value(item, field_name=f"{field_name}.{key}")
        return
    raise AssistantContractError(f"{field_name} must contain JSON-safe values.")


@dataclass(frozen=True)
class AssistantRequest:
    """A fail-closed request to a registered assistant capability.

    This contract intentionally does not execute capability actions. Future tool
    adapters must validate this request before routing to a supported operation.
    """

    capability_id: str
    payload: dict[str, Any]
    schema_version: int = ASSISTANT_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ASSISTANT_CONTRACT_SCHEMA_VERSION:
            raise AssistantContractError(
                f"Unsupported assistant request schema_version: {self.schema_version}."
            )
        if not _CAPABILITY_ID_RE.fullmatch(self.capability_id):
            raise AssistantContractError("capability_id has an invalid format.")
        if not isinstance(self.payload, dict):
            raise AssistantContractError("payload must be an object.")
        _validate_json_value(self.payload, field_name="payload")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AssistantRequest:
        """Parse a request and reject unknown fields."""
        if not isinstance(payload, Mapping):
            raise AssistantContractError("Assistant request must be an object.")
        allowed = {"schema_version", "capability_id", "payload"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise AssistantContractError(f"Unknown assistant request keys: {unknown}")
        missing = sorted({"capability_id", "payload"} - set(payload))
        if missing:
            raise AssistantContractError(f"Missing assistant request keys: {missing}")
        return cls(
            schema_version=payload.get("schema_version", ASSISTANT_CONTRACT_SCHEMA_VERSION),
            capability_id=payload["capability_id"],
            payload=payload["payload"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "payload": self.payload,
        }
