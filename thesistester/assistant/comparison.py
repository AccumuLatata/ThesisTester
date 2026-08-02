"""Schema-versioned comparison records for explicitly selected research runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

COMPARISON_SCHEMA_VERSION = 1


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, dict) or isinstance(value, MappingProxyType):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class Comparison:
    """Immutable comparison evidence linked to exact run and bundle identities."""

    comparison_id: str
    thesis_id: str
    left_run_id: str
    right_run_id: str
    left_bundle_hash: str
    right_bundle_hash: str
    evidence: dict[str, Any]

    def __post_init__(self) -> None:
        if self.left_run_id == self.right_run_id:
            raise ValueError("Comparison requires two distinct run IDs.")
        object.__setattr__(
            self, "evidence", _freeze(json.loads(json.dumps(self.evidence, sort_keys=True)))
        )

    @classmethod
    def create(
        cls,
        *,
        thesis_id: str,
        left_run_id: str,
        right_run_id: str,
        left_bundle_hash: str,
        right_bundle_hash: str,
        evidence: dict[str, Any],
    ) -> Comparison:
        return cls(
            comparison_id=f"cmp_{uuid4().hex}",
            thesis_id=thesis_id,
            left_run_id=left_run_id,
            right_run_id=right_run_id,
            left_bundle_hash=left_bundle_hash,
            right_bundle_hash=right_bundle_hash,
            evidence=evidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": COMPARISON_SCHEMA_VERSION,
            "kind": "assistant_comparison",
            "comparison_id": self.comparison_id,
            "thesis_id": self.thesis_id,
            "left_run_id": self.left_run_id,
            "right_run_id": self.right_run_id,
            "left_bundle_hash": self.left_bundle_hash,
            "right_bundle_hash": self.right_bundle_hash,
            "evidence": _thaw(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Comparison:
        required = {
            "schema_version",
            "kind",
            "comparison_id",
            "thesis_id",
            "left_run_id",
            "right_run_id",
            "left_bundle_hash",
            "right_bundle_hash",
            "evidence",
        }
        if set(payload) != required or payload.get("schema_version") != COMPARISON_SCHEMA_VERSION:
            raise ValueError("Invalid comparison record.")
        if payload.get("kind") != "assistant_comparison" or not isinstance(
            payload.get("evidence"), dict
        ):
            raise ValueError("Invalid comparison record.")
        return cls(
            comparison_id=payload["comparison_id"],
            thesis_id=payload["thesis_id"],
            left_run_id=payload["left_run_id"],
            right_run_id=payload["right_run_id"],
            left_bundle_hash=payload["left_bundle_hash"],
            right_bundle_hash=payload["right_bundle_hash"],
            evidence=payload["evidence"],
        )
