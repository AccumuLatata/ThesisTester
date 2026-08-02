"""Schema-versioned comparison records for explicitly selected research runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

COMPARISON_SCHEMA_VERSION = 2
_SUPPORTED_COMPARISON_SCHEMA_VERSIONS = frozenset({1, 2})


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


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    created_at: str
    conclusions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.left_run_id == self.right_run_id:
            raise ValueError("Comparison requires two distinct run IDs.")
        # Thaw nested mapping proxies before canonical JSON round-trip so
        # evidence built from frozen EvidencePackets remains persistable.
        thawed = _thaw(self.evidence)
        object.__setattr__(
            self, "evidence", _freeze(json.loads(json.dumps(thawed, sort_keys=True)))
        )
        object.__setattr__(self, "conclusions", tuple(self.conclusions))

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
        conclusions: tuple[str, ...] | list[str] | None = None,
        created_at: str | None = None,
    ) -> Comparison:
        resolved_conclusions = tuple(
            conclusions if conclusions is not None else list(evidence.get("conclusions") or ())
        )
        return cls(
            comparison_id=f"cmp_{uuid4().hex}",
            thesis_id=thesis_id,
            left_run_id=left_run_id,
            right_run_id=right_run_id,
            left_bundle_hash=left_bundle_hash,
            right_bundle_hash=right_bundle_hash,
            evidence=evidence,
            created_at=created_at or _utcnow_iso(),
            conclusions=resolved_conclusions,
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
            "created_at": self.created_at,
            "conclusions": list(self.conclusions),
            "evidence": _thaw(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Comparison:
        schema_version = payload.get("schema_version")
        if (
            payload.get("kind") != "assistant_comparison"
            or schema_version not in _SUPPORTED_COMPARISON_SCHEMA_VERSIONS
            or not isinstance(payload.get("evidence"), dict)
        ):
            raise ValueError("Invalid comparison record.")
        base_required = {
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
        if schema_version == 1:
            if set(payload) != base_required:
                raise ValueError("Invalid comparison record.")
            evidence = dict(payload["evidence"])
            conclusions = tuple(str(item) for item in evidence.get("conclusions") or ())
            created_at = str(evidence.get("created_at") or "1970-01-01T00:00:00Z")
        else:
            required = base_required | {"created_at", "conclusions"}
            if set(payload) != required:
                raise ValueError("Invalid comparison record.")
            conclusions_raw = payload.get("conclusions")
            if not isinstance(conclusions_raw, list) or any(
                not isinstance(item, str) for item in conclusions_raw
            ):
                raise ValueError("Invalid comparison record.")
            conclusions = tuple(conclusions_raw)
            created_at = str(payload["created_at"])
            evidence = dict(payload["evidence"])
        return cls(
            comparison_id=payload["comparison_id"],
            thesis_id=payload["thesis_id"],
            left_run_id=payload["left_run_id"],
            right_run_id=payload["right_run_id"],
            left_bundle_hash=payload["left_bundle_hash"],
            right_bundle_hash=payload["right_bundle_hash"],
            evidence=evidence,
            created_at=created_at,
            conclusions=conclusions,
        )
