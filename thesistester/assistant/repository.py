"""Atomic, schema-versioned local persistence for assistant research history.

This repository stores assistant metadata only. It never executes a backtest,
opens a research bundle, calls an LLM, or mutates existing local-store schemas.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from thesistester.assistant.comparison import Comparison
from thesistester.persistence.local_store import get_store_root

ASSISTANT_REPOSITORY_SCHEMA_VERSION = 1
_ID_RE = re.compile(r"^(?:th|run|conv)_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_THESIS_FIELDS = {
    "schema_version",
    "kind",
    "thesis_id",
    "name",
    "tags",
    "lifecycle",
    "created_at",
    "updated_at",
    "revision",
    "cloned_from_thesis_id",
}
_SPEC_FIELDS = {
    "schema_version",
    "kind",
    "thesis_id",
    "version",
    "parent_version",
    "status",
    "normalized_run_spec",
    "unresolved_assumptions",
    "compiler_version",
    "confirmed_at",
    "confirmation_note",
    "created_at",
    "content_sha256",
}
_RUN_FIELDS = {
    "schema_version",
    "kind",
    "run_id",
    "thesis_id",
    "spec_version",
    "request",
    "status",
    "provenance",
    "warnings",
    "error",
    "created_at",
    "updated_at",
    "revision",
}
_CONVERSATION_FIELDS = {
    "schema_version",
    "kind",
    "conversation_id",
    "thesis_id",
    "selected_spec_version",
    "selected_run_id",
    "messages",
    "tool_transcript",
    "created_at",
    "updated_at",
    "revision",
}
_SPEC_STATUSES = {"draft", "needs_clarification", "ready_for_confirmation", "confirmed"}
_RUN_STATUSES = {"running", "completed", "failed", "cancelled"}


class AssistantRepositoryError(ValueError):
    """Base error for assistant repository operations."""


class RepositoryCorruptionError(AssistantRepositoryError):
    """Raised when a persisted document is malformed or internally inconsistent."""


class UnsupportedRepositorySchemaError(AssistantRepositoryError):
    """Raised when a document belongs to a newer repository schema."""


class RepositoryReadOnlyError(AssistantRepositoryError):
    """Raised when a future root marker prevents safe mutation."""


class RepositoryConflictError(AssistantRepositoryError):
    """Raised when a caller's optimistic-concurrency revision is stale."""


class InvalidStateTransitionError(AssistantRepositoryError):
    """Raised when a lifecycle transition is not allowed."""


def get_assistant_store_root() -> Path:
    """Return the additive assistant namespace below the configured store root."""
    return get_store_root() / "assistant"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _validate_id(value: str, *, prefix: str | None = None) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise AssistantRepositoryError("Invalid assistant record identifier.")
    if prefix is not None and not value.startswith(f"{prefix}_"):
        raise AssistantRepositoryError(f"Expected a {prefix}_ identifier.")
    return value


def _validate_timestamp(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise RepositoryCorruptionError(f"{field} must be a UTC timestamp string.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RepositoryCorruptionError(f"{field} must be a valid ISO timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise RepositoryCorruptionError(f"{field} must use UTC.")
    return value


def _validate_json(value: Any, *, field: str) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise AssistantRepositoryError(f"{field} must not contain non-finite floats.")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, field=f"{field}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AssistantRepositoryError(f"{field} keys must be strings.")
            _validate_json(item, field=f"{field}.{key}")
        return
    raise AssistantRepositoryError(f"{field} must contain JSON-safe values.")


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    _validate_json(dict(payload), field="document")
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _content_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _require_fields(payload: Mapping[str, Any], *, fields: set[str], kind: str) -> None:
    if not isinstance(payload, Mapping):
        raise RepositoryCorruptionError(f"{kind} must be an object.")
    actual = set(payload)
    if actual != fields:
        raise RepositoryCorruptionError(
            f"{kind} fields differ from schema: missing={sorted(fields - actual)}, "
            f"unknown={sorted(actual - fields)}."
        )
    if payload["schema_version"] != ASSISTANT_REPOSITORY_SCHEMA_VERSION:
        if isinstance(payload["schema_version"], int) and payload["schema_version"] > 1:
            raise UnsupportedRepositorySchemaError(f"Unsupported {kind} schema version.")
        raise RepositoryCorruptionError(f"Unsupported {kind} schema version.")
    if payload["kind"] != kind:
        raise RepositoryCorruptionError(f"Expected persisted kind {kind}.")


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 160):
        raise AssistantRepositoryError(
            "Thesis name must contain 1 to 160 non-whitespace characters."
        )
    return name.strip()


def _validate_tags(tags: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if not isinstance(tags, (tuple, list)) or any(
        not isinstance(tag, str) or not tag.strip() for tag in tags
    ):
        raise AssistantRepositoryError("Tags must be non-empty strings.")
    normalized = tuple(tag.strip() for tag in tags)
    if len(set(normalized)) != len(normalized):
        raise AssistantRepositoryError("Tags must be unique.")
    return normalized


@dataclass(frozen=True)
class Thesis:
    """Immutable thesis metadata; changes produce a higher revision."""

    thesis_id: str
    name: str
    tags: tuple[str, ...]
    lifecycle: str
    created_at: str
    updated_at: str
    revision: int
    cloned_from_thesis_id: str | None = None

    def __post_init__(self) -> None:
        _validate_id(self.thesis_id, prefix="th")
        _validate_name(self.name)
        _validate_tags(self.tags)
        if self.lifecycle not in {"active", "archived"}:
            raise AssistantRepositoryError("Thesis lifecycle must be active or archived.")
        _validate_timestamp(self.created_at, field="created_at")
        _validate_timestamp(self.updated_at, field="updated_at")
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 1
        ):
            raise AssistantRepositoryError("Thesis revision must be a positive integer.")
        if self.cloned_from_thesis_id is not None:
            _validate_id(self.cloned_from_thesis_id, prefix="th")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ASSISTANT_REPOSITORY_SCHEMA_VERSION,
            "kind": "thesis",
            "thesis_id": self.thesis_id,
            "name": self.name,
            "tags": list(self.tags),
            "lifecycle": self.lifecycle,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision": self.revision,
            "cloned_from_thesis_id": self.cloned_from_thesis_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Thesis:
        _require_fields(payload, fields=_THESIS_FIELDS, kind="thesis")
        try:
            return cls(
                thesis_id=payload["thesis_id"],
                name=payload["name"],
                tags=tuple(payload["tags"]),
                lifecycle=payload["lifecycle"],
                created_at=payload["created_at"],
                updated_at=payload["updated_at"],
                revision=payload["revision"],
                cloned_from_thesis_id=payload["cloned_from_thesis_id"],
            )
        except (AssistantRepositoryError, TypeError) as exc:
            raise RepositoryCorruptionError("Invalid thesis document.") from exc


@dataclass(frozen=True)
class SpecVersion:
    """Immutable normalized research specification."""

    thesis_id: str
    version: int
    parent_version: int | None
    status: str
    normalized_run_spec: dict[str, Any]
    unresolved_assumptions: tuple[str, ...]
    compiler_version: str | None
    confirmed_at: str | None
    confirmation_note: str | None
    created_at: str
    content_sha256: str

    def __post_init__(self) -> None:
        _validate_id(self.thesis_id, prefix="th")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise AssistantRepositoryError("Spec version must be a positive integer.")
        if self.parent_version is not None and (
            not isinstance(self.parent_version, int) or self.parent_version < 1
        ):
            raise AssistantRepositoryError("parent_version must be a positive integer or None.")
        if self.parent_version is not None and self.parent_version >= self.version:
            raise AssistantRepositoryError("parent_version must precede version.")
        if self.status not in _SPEC_STATUSES:
            raise AssistantRepositoryError("Invalid specification status.")
        _validate_json(self.normalized_run_spec, field="normalized_run_spec")
        if any(
            not isinstance(item, str) or not item.strip() for item in self.unresolved_assumptions
        ):
            raise AssistantRepositoryError("Unresolved assumptions must be non-empty strings.")
        if self.compiler_version is not None and not isinstance(self.compiler_version, str):
            raise AssistantRepositoryError("compiler_version must be a string or None.")
        if self.status == "confirmed":
            if self.confirmed_at is None:
                raise AssistantRepositoryError("Confirmed specifications require confirmed_at.")
            _validate_timestamp(self.confirmed_at, field="confirmed_at")
        elif self.confirmed_at is not None:
            raise AssistantRepositoryError("Only confirmed specifications may set confirmed_at.")
        _validate_timestamp(self.created_at, field="created_at")
        if not isinstance(self.content_sha256, str) or not _SHA256_RE.fullmatch(
            self.content_sha256
        ):
            raise AssistantRepositoryError("content_sha256 must be a lowercase SHA-256 digest.")

    def _without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": ASSISTANT_REPOSITORY_SCHEMA_VERSION,
            "kind": "spec_version",
            "thesis_id": self.thesis_id,
            "version": self.version,
            "parent_version": self.parent_version,
            "status": self.status,
            "normalized_run_spec": self.normalized_run_spec,
            "unresolved_assumptions": list(self.unresolved_assumptions),
            "compiler_version": self.compiler_version,
            "confirmed_at": self.confirmed_at,
            "confirmation_note": self.confirmation_note,
            "created_at": self.created_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._without_hash(), "content_sha256": self.content_sha256}

    @classmethod
    def create(
        cls,
        *,
        thesis_id: str,
        version: int,
        parent_version: int | None,
        status: str,
        normalized_run_spec: dict[str, Any],
        unresolved_assumptions: tuple[str, ...],
        compiler_version: str | None,
        confirmed_at: str | None = None,
        confirmation_note: str | None = None,
        created_at: str | None = None,
    ) -> SpecVersion:
        timestamp = created_at or _utcnow()
        base = {
            "schema_version": ASSISTANT_REPOSITORY_SCHEMA_VERSION,
            "kind": "spec_version",
            "thesis_id": thesis_id,
            "version": version,
            "parent_version": parent_version,
            "status": status,
            "normalized_run_spec": normalized_run_spec,
            "unresolved_assumptions": list(unresolved_assumptions),
            "compiler_version": compiler_version,
            "confirmed_at": confirmed_at,
            "confirmation_note": confirmation_note,
            "created_at": timestamp,
        }
        return cls(
            thesis_id=thesis_id,
            version=version,
            parent_version=parent_version,
            status=status,
            normalized_run_spec=normalized_run_spec,
            unresolved_assumptions=unresolved_assumptions,
            compiler_version=compiler_version,
            confirmed_at=confirmed_at,
            confirmation_note=confirmation_note,
            created_at=timestamp,
            content_sha256=_content_hash(base),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SpecVersion:
        _require_fields(payload, fields=_SPEC_FIELDS, kind="spec_version")
        try:
            record = cls(
                thesis_id=payload["thesis_id"],
                version=payload["version"],
                parent_version=payload["parent_version"],
                status=payload["status"],
                normalized_run_spec=payload["normalized_run_spec"],
                unresolved_assumptions=tuple(payload["unresolved_assumptions"]),
                compiler_version=payload["compiler_version"],
                confirmed_at=payload["confirmed_at"],
                confirmation_note=payload["confirmation_note"],
                created_at=payload["created_at"],
                content_sha256=payload["content_sha256"],
            )
        except (AssistantRepositoryError, TypeError) as exc:
            raise RepositoryCorruptionError("Invalid specification document.") from exc
        if _content_hash(record._without_hash()) != record.content_sha256:
            raise RepositoryCorruptionError("Specification content hash does not match document.")
        return record


@dataclass(frozen=True)
class ResearchRun:
    """Persisted requested and terminal run state without bundle access."""

    run_id: str
    thesis_id: str
    spec_version: int
    request: dict[str, Any]
    status: str
    provenance: dict[str, Any] | None
    warnings: tuple[str, ...]
    error: dict[str, Any] | None
    created_at: str
    updated_at: str
    revision: int

    def __post_init__(self) -> None:
        _validate_id(self.run_id, prefix="run")
        _validate_id(self.thesis_id, prefix="th")
        if not isinstance(self.spec_version, int) or self.spec_version < 1:
            raise AssistantRepositoryError("spec_version must be a positive integer.")
        if self.status not in _RUN_STATUSES:
            raise AssistantRepositoryError("Invalid research run status.")
        _validate_json(self.request, field="request")
        _validate_json(self.provenance, field="provenance")
        _validate_json(self.error, field="error")
        if any(not isinstance(warning, str) or not warning.strip() for warning in self.warnings):
            raise AssistantRepositoryError("Warnings must be non-empty strings.")
        if self.status == "completed" and self.provenance is None:
            raise AssistantRepositoryError("Completed runs require provenance.")
        if self.status in {"failed", "cancelled"} and self.error is None:
            raise AssistantRepositoryError("Failed or cancelled runs require an error record.")
        if self.status == "running" and (self.provenance is not None or self.error is not None):
            raise AssistantRepositoryError("Running runs cannot contain terminal result data.")
        _validate_timestamp(self.created_at, field="created_at")
        _validate_timestamp(self.updated_at, field="updated_at")
        if not isinstance(self.revision, int) or self.revision < 1:
            raise AssistantRepositoryError("Run revision must be a positive integer.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ASSISTANT_REPOSITORY_SCHEMA_VERSION,
            "kind": "research_run",
            "run_id": self.run_id,
            "thesis_id": self.thesis_id,
            "spec_version": self.spec_version,
            "request": self.request,
            "status": self.status,
            "provenance": self.provenance,
            "warnings": list(self.warnings),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResearchRun:
        _require_fields(payload, fields=_RUN_FIELDS, kind="research_run")
        try:
            return cls(
                run_id=payload["run_id"],
                thesis_id=payload["thesis_id"],
                spec_version=payload["spec_version"],
                request=payload["request"],
                status=payload["status"],
                provenance=payload["provenance"],
                warnings=tuple(payload["warnings"]),
                error=payload["error"],
                created_at=payload["created_at"],
                updated_at=payload["updated_at"],
                revision=payload["revision"],
            )
        except (AssistantRepositoryError, TypeError) as exc:
            raise RepositoryCorruptionError("Invalid research run document.") from exc


@dataclass(frozen=True)
class Conversation:
    """Append-only conversation and model-independent tool transcript."""

    conversation_id: str
    thesis_id: str
    selected_spec_version: int | None
    selected_run_id: str | None
    messages: tuple[dict[str, Any], ...]
    tool_transcript: tuple[dict[str, Any], ...]
    created_at: str
    updated_at: str
    revision: int

    def __post_init__(self) -> None:
        _validate_id(self.conversation_id, prefix="conv")
        _validate_id(self.thesis_id, prefix="th")
        if self.selected_spec_version is not None and (
            not isinstance(self.selected_spec_version, int) or self.selected_spec_version < 1
        ):
            raise AssistantRepositoryError("selected_spec_version must be positive or None.")
        if self.selected_run_id is not None:
            _validate_id(self.selected_run_id, prefix="run")
        _validate_json(list(self.messages), field="messages")
        _validate_json(list(self.tool_transcript), field="tool_transcript")
        _validate_timestamp(self.created_at, field="created_at")
        _validate_timestamp(self.updated_at, field="updated_at")
        if not isinstance(self.revision, int) or self.revision < 1:
            raise AssistantRepositoryError("Conversation revision must be a positive integer.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ASSISTANT_REPOSITORY_SCHEMA_VERSION,
            "kind": "conversation",
            "conversation_id": self.conversation_id,
            "thesis_id": self.thesis_id,
            "selected_spec_version": self.selected_spec_version,
            "selected_run_id": self.selected_run_id,
            "messages": list(self.messages),
            "tool_transcript": list(self.tool_transcript),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Conversation:
        _require_fields(payload, fields=_CONVERSATION_FIELDS, kind="conversation")
        try:
            return cls(
                conversation_id=payload["conversation_id"],
                thesis_id=payload["thesis_id"],
                selected_spec_version=payload["selected_spec_version"],
                selected_run_id=payload["selected_run_id"],
                messages=tuple(payload["messages"]),
                tool_transcript=tuple(payload["tool_transcript"]),
                created_at=payload["created_at"],
                updated_at=payload["updated_at"],
                revision=payload["revision"],
            )
        except (AssistantRepositoryError, TypeError) as exc:
            raise RepositoryCorruptionError("Invalid conversation document.") from exc


class LocalThesisRepository:
    """Repository for local thesis metadata, immutable specs, runs, and chats."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or get_assistant_store_root()).resolve()

    @property
    def _marker_path(self) -> Path:
        return self.root / "schema_version.json"

    def _thesis_dir(self, thesis_id: str) -> Path:
        return self.root / "theses" / _validate_id(thesis_id, prefix="th")

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryCorruptionError(f"Unable to read {path.name}.") from exc
        if not isinstance(payload, dict):
            raise RepositoryCorruptionError(f"{path.name} must contain an object.")
        return payload

    def _assert_mutable_root(self) -> None:
        if not self._marker_path.exists():
            self._write_json_atomic(
                self._marker_path,
                {"schema_version": ASSISTANT_REPOSITORY_SCHEMA_VERSION, "kind": "assistant_store"},
            )
            return
        marker = self._read_json(self._marker_path)
        version = marker.get("schema_version")
        if marker.get("kind") != "assistant_store" or not isinstance(version, int):
            raise RepositoryCorruptionError("Assistant store marker is invalid.")
        if version > ASSISTANT_REPOSITORY_SCHEMA_VERSION:
            raise RepositoryReadOnlyError("Assistant store uses a newer schema.")
        if version != ASSISTANT_REPOSITORY_SCHEMA_VERSION:
            raise RepositoryCorruptionError("Assistant store schema is unsupported.")

    def _assert_readable_root(self) -> bool:
        if not self._marker_path.exists():
            return False
        marker = self._read_json(self._marker_path)
        version = marker.get("schema_version")
        if marker.get("kind") != "assistant_store" or not isinstance(version, int):
            raise RepositoryCorruptionError("Assistant store marker is invalid.")
        if version > ASSISTANT_REPOSITORY_SCHEMA_VERSION:
            raise UnsupportedRepositorySchemaError("Assistant store uses a newer schema.")
        if version != ASSISTANT_REPOSITORY_SCHEMA_VERSION:
            raise RepositoryCorruptionError("Assistant store schema is unsupported.")
        return True

    def _write_json_atomic(
        self, path: Path, payload: Mapping[str, Any], *, exclusive: bool = False
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(_canonical_json(payload) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            if exclusive and path.exists():
                raise RepositoryConflictError(f"Immutable record already exists: {path.name}")
            os.replace(temporary_path, path)
            directory_fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _load_thesis(self, thesis_id: str) -> Thesis:
        path = self._thesis_dir(thesis_id) / "meta.json"
        if not path.exists():
            raise AssistantRepositoryError("Thesis does not exist.")
        return Thesis.from_dict(self._read_json(path))

    def create_thesis(self, *, name: str, tags: tuple[str, ...] = ()) -> Thesis:
        self._assert_mutable_root()
        timestamp = _utcnow()
        thesis = Thesis(
            thesis_id=_id("th"),
            name=name,
            tags=_validate_tags(tags),
            lifecycle="active",
            created_at=timestamp,
            updated_at=timestamp,
            revision=1,
        )
        self._write_json_atomic(
            self._thesis_dir(thesis.thesis_id) / "meta.json", thesis.to_dict(), exclusive=True
        )
        return thesis

    def get_thesis(self, thesis_id: str) -> Thesis:
        self._assert_readable_root()
        return self._load_thesis(thesis_id)

    def list_theses(self, *, include_archived: bool = False) -> tuple[Thesis, ...]:
        self._assert_readable_root()
        root = self.root / "theses"
        if not root.exists():
            return ()
        theses = [self._load_thesis(path.name) for path in root.iterdir() if path.is_dir()]
        if not include_archived:
            theses = [thesis for thesis in theses if thesis.lifecycle == "active"]
        return tuple(
            sorted(theses, key=lambda thesis: (thesis.updated_at, thesis.thesis_id), reverse=True)
        )

    def _update_thesis(
        self,
        thesis_id: str,
        *,
        expected_revision: int,
        name: str | None = None,
        lifecycle: str | None = None,
    ) -> Thesis:
        self._assert_mutable_root()
        thesis = self._load_thesis(thesis_id)
        if thesis.revision != expected_revision:
            raise RepositoryConflictError("Thesis revision is stale.")
        updated = Thesis(
            thesis_id=thesis.thesis_id,
            name=name if name is not None else thesis.name,
            tags=thesis.tags,
            lifecycle=lifecycle if lifecycle is not None else thesis.lifecycle,
            created_at=thesis.created_at,
            updated_at=_utcnow(),
            revision=thesis.revision + 1,
            cloned_from_thesis_id=thesis.cloned_from_thesis_id,
        )
        self._write_json_atomic(self._thesis_dir(thesis_id) / "meta.json", updated.to_dict())
        return updated

    def rename_thesis(self, thesis_id: str, *, name: str, expected_revision: int) -> Thesis:
        return self._update_thesis(
            thesis_id, expected_revision=expected_revision, name=_validate_name(name)
        )

    def archive_thesis(self, thesis_id: str, *, expected_revision: int) -> Thesis:
        return self._update_thesis(
            thesis_id, expected_revision=expected_revision, lifecycle="archived"
        )

    def restore_thesis(self, thesis_id: str, *, expected_revision: int) -> Thesis:
        return self._update_thesis(
            thesis_id, expected_revision=expected_revision, lifecycle="active"
        )

    def clone_thesis(self, thesis_id: str, *, name: str | None = None) -> Thesis:
        self._assert_mutable_root()
        source = self._load_thesis(thesis_id)
        timestamp = _utcnow()
        clone = Thesis(
            thesis_id=_id("th"),
            name=_validate_name(name) if name is not None else f"{source.name} (copy)",
            tags=source.tags,
            lifecycle="active",
            created_at=timestamp,
            updated_at=timestamp,
            revision=1,
            cloned_from_thesis_id=source.thesis_id,
        )
        self._write_json_atomic(
            self._thesis_dir(clone.thesis_id) / "meta.json", clone.to_dict(), exclusive=True
        )
        return clone

    def _spec_path(self, thesis_id: str, version: int) -> Path:
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise AssistantRepositoryError("Spec version must be a positive integer.")
        return self._thesis_dir(thesis_id) / "specs" / f"{version}.json"

    def get_spec_version(self, thesis_id: str, version: int) -> SpecVersion:
        self._assert_readable_root()
        path = self._spec_path(thesis_id, version)
        if not path.exists():
            raise AssistantRepositoryError("Specification version does not exist.")
        return SpecVersion.from_dict(self._read_json(path))

    def list_spec_versions(self, thesis_id: str) -> tuple[SpecVersion, ...]:
        self._assert_readable_root()
        root = self._thesis_dir(thesis_id) / "specs"
        if not root.exists():
            return ()
        versions = [
            self.get_spec_version(thesis_id, int(path.stem)) for path in root.glob("*.json")
        ]
        return tuple(sorted(versions, key=lambda spec: spec.version))

    def create_spec_version(
        self,
        thesis_id: str,
        *,
        normalized_run_spec: dict[str, Any],
        status: str = "draft",
        unresolved_assumptions: tuple[str, ...] = (),
        compiler_version: str | None = None,
        parent_version: int | None = None,
    ) -> SpecVersion:
        self._assert_mutable_root()
        thesis = self._load_thesis(thesis_id)
        if thesis.lifecycle != "active":
            raise InvalidStateTransitionError(
                "Cannot create a specification for an archived thesis."
            )
        existing = self.list_spec_versions(thesis_id)
        version = len(existing) + 1
        if parent_version is None and existing:
            parent_version = existing[-1].version
        if parent_version is not None:
            self.get_spec_version(thesis_id, parent_version)
        spec = SpecVersion.create(
            thesis_id=thesis_id,
            version=version,
            parent_version=parent_version,
            status=status,
            normalized_run_spec=normalized_run_spec,
            unresolved_assumptions=unresolved_assumptions,
            compiler_version=compiler_version,
        )
        self._write_json_atomic(self._spec_path(thesis_id, version), spec.to_dict(), exclusive=True)
        return spec

    def confirm_spec_version(
        self, thesis_id: str, version: int, *, confirmation_note: str | None = None
    ) -> SpecVersion:
        self._assert_mutable_root()
        source = self.get_spec_version(thesis_id, version)
        if source.status == "confirmed":
            raise InvalidStateTransitionError("Specification version is already confirmed.")
        return self._create_confirmed_copy(source, confirmation_note=confirmation_note)

    def _create_confirmed_copy(
        self, source: SpecVersion, *, confirmation_note: str | None
    ) -> SpecVersion:
        existing = self.list_spec_versions(source.thesis_id)
        confirmed = SpecVersion.create(
            thesis_id=source.thesis_id,
            version=len(existing) + 1,
            parent_version=source.version,
            status="confirmed",
            normalized_run_spec=source.normalized_run_spec,
            unresolved_assumptions=source.unresolved_assumptions,
            compiler_version=source.compiler_version,
            confirmed_at=_utcnow(),
            confirmation_note=confirmation_note,
        )
        self._write_json_atomic(
            self._spec_path(source.thesis_id, confirmed.version),
            confirmed.to_dict(),
            exclusive=True,
        )
        return confirmed

    def _run_path(self, thesis_id: str, run_id: str) -> Path:
        return self._thesis_dir(thesis_id) / "runs" / f"{_validate_id(run_id, prefix='run')}.json"

    def get_run(self, thesis_id: str, run_id: str) -> ResearchRun:
        self._assert_readable_root()
        path = self._run_path(thesis_id, run_id)
        if not path.exists():
            raise AssistantRepositoryError("Research run does not exist.")
        record = ResearchRun.from_dict(self._read_json(path))
        if record.thesis_id != thesis_id:
            raise RepositoryCorruptionError("Research run is stored under the wrong thesis.")
        return record

    def list_runs(self, thesis_id: str) -> tuple[ResearchRun, ...]:
        self._assert_readable_root()
        root = self._thesis_dir(thesis_id) / "runs"
        if not root.exists():
            return ()
        return tuple(
            sorted(
                (self.get_run(thesis_id, path.stem) for path in root.glob("run_*.json")),
                key=lambda run: (run.created_at, run.run_id),
            )
        )

    def start_run(
        self, thesis_id: str, *, spec_version: int, request: dict[str, Any]
    ) -> ResearchRun:
        self._assert_mutable_root()
        thesis = self._load_thesis(thesis_id)
        if thesis.lifecycle != "active":
            raise InvalidStateTransitionError("Cannot start a run for an archived thesis.")
        spec = self.get_spec_version(thesis_id, spec_version)
        if spec.status != "confirmed":
            raise InvalidStateTransitionError("Research runs require a confirmed specification.")
        timestamp = _utcnow()
        run = ResearchRun(
            run_id=_id("run"),
            thesis_id=thesis_id,
            spec_version=spec_version,
            request=request,
            status="running",
            provenance=None,
            warnings=(),
            error=None,
            created_at=timestamp,
            updated_at=timestamp,
            revision=1,
        )
        self._write_json_atomic(
            self._run_path(thesis_id, run.run_id), run.to_dict(), exclusive=True
        )
        return run

    def _finish_run(
        self,
        thesis_id: str,
        run_id: str,
        *,
        status: str,
        expected_revision: int,
        provenance: dict[str, Any] | None,
        warnings: tuple[str, ...] = (),
        error: dict[str, Any] | None = None,
    ) -> ResearchRun:
        self._assert_mutable_root()
        run = self.get_run(thesis_id, run_id)
        if run.revision != expected_revision:
            raise RepositoryConflictError("Research run revision is stale.")
        if run.status != "running":
            raise InvalidStateTransitionError("Only running research runs may transition.")
        updated = ResearchRun(
            run_id=run.run_id,
            thesis_id=run.thesis_id,
            spec_version=run.spec_version,
            request=run.request,
            status=status,
            provenance=provenance,
            warnings=warnings,
            error=error,
            created_at=run.created_at,
            updated_at=_utcnow(),
            revision=run.revision + 1,
        )
        self._write_json_atomic(self._run_path(thesis_id, run_id), updated.to_dict())
        return updated

    def complete_run(
        self,
        thesis_id: str,
        run_id: str,
        *,
        expected_revision: int,
        provenance: dict[str, Any],
        warnings: tuple[str, ...] = (),
    ) -> ResearchRun:
        return self._finish_run(
            thesis_id,
            run_id,
            status="completed",
            expected_revision=expected_revision,
            provenance=provenance,
            warnings=warnings,
        )

    def fail_run(
        self, thesis_id: str, run_id: str, *, expected_revision: int, error: dict[str, Any]
    ) -> ResearchRun:
        return self._finish_run(
            thesis_id,
            run_id,
            status="failed",
            expected_revision=expected_revision,
            provenance=None,
            error=error,
        )

    def cancel_run(
        self, thesis_id: str, run_id: str, *, expected_revision: int, reason: str
    ) -> ResearchRun:
        return self._finish_run(
            thesis_id,
            run_id,
            status="cancelled",
            expected_revision=expected_revision,
            provenance=None,
            error={"reason": reason},
        )

    def _conversation_path(self, thesis_id: str, conversation_id: str) -> Path:
        return (
            self._thesis_dir(thesis_id)
            / "conversations"
            / f"{_validate_id(conversation_id, prefix='conv')}.json"
        )

    def create_conversation(
        self,
        thesis_id: str,
        *,
        selected_spec_version: int | None = None,
        selected_run_id: str | None = None,
    ) -> Conversation:
        self._assert_mutable_root()
        self._load_thesis(thesis_id)
        if selected_spec_version is not None:
            self.get_spec_version(thesis_id, selected_spec_version)
        if selected_run_id is not None:
            self.get_run(thesis_id, selected_run_id)
        timestamp = _utcnow()
        conversation = Conversation(
            conversation_id=_id("conv"),
            thesis_id=thesis_id,
            selected_spec_version=selected_spec_version,
            selected_run_id=selected_run_id,
            messages=(),
            tool_transcript=(),
            created_at=timestamp,
            updated_at=timestamp,
            revision=1,
        )
        self._write_json_atomic(
            self._conversation_path(thesis_id, conversation.conversation_id),
            conversation.to_dict(),
            exclusive=True,
        )
        return conversation

    def get_conversation(self, thesis_id: str, conversation_id: str) -> Conversation:
        self._assert_readable_root()
        path = self._conversation_path(thesis_id, conversation_id)
        if not path.exists():
            raise AssistantRepositoryError("Conversation does not exist.")
        conversation = Conversation.from_dict(self._read_json(path))
        if conversation.thesis_id != thesis_id:
            raise RepositoryCorruptionError("Conversation is stored under the wrong thesis.")
        return conversation

    def list_conversations(self, thesis_id: str) -> tuple[Conversation, ...]:
        self._assert_readable_root()
        root = self._thesis_dir(thesis_id) / "conversations"
        if not root.exists():
            return ()
        return tuple(
            sorted(
                (self.get_conversation(thesis_id, path.stem) for path in root.glob("conv_*.json")),
                key=lambda conversation: (conversation.created_at, conversation.conversation_id),
            )
        )

    def append_conversation_message(
        self,
        thesis_id: str,
        conversation_id: str,
        *,
        expected_revision: int,
        message: dict[str, Any],
        tool_entry: dict[str, Any] | None = None,
    ) -> Conversation:
        self._assert_mutable_root()
        conversation = self.get_conversation(thesis_id, conversation_id)
        if conversation.revision != expected_revision:
            raise RepositoryConflictError("Conversation revision is stale.")
        _validate_json(message, field="message")
        if tool_entry is not None:
            _validate_json(tool_entry, field="tool_entry")
        updated = Conversation(
            conversation_id=conversation.conversation_id,
            thesis_id=conversation.thesis_id,
            selected_spec_version=conversation.selected_spec_version,
            selected_run_id=conversation.selected_run_id,
            messages=conversation.messages + (message,),
            tool_transcript=conversation.tool_transcript
            + ((tool_entry,) if tool_entry is not None else ()),
            created_at=conversation.created_at,
            updated_at=_utcnow(),
            revision=conversation.revision + 1,
        )
        self._write_json_atomic(
            self._conversation_path(thesis_id, conversation_id), updated.to_dict()
        )
        return updated

    def save_comparison(self, comparison: Comparison) -> Comparison:
        """Persist immutable selected-run comparison evidence for one thesis."""
        self._assert_mutable_root()
        self._load_thesis(comparison.thesis_id)
        path = (
            self._thesis_dir(comparison.thesis_id)
            / "comparisons"
            / f"{comparison.comparison_id}.json"
        )
        self._write_json_atomic(path, comparison.to_dict(), exclusive=True)
        return comparison

    def list_comparisons(self, thesis_id: str) -> tuple[Comparison, ...]:
        """List persisted comparison records for one thesis."""
        self._assert_readable_root()
        root = self._thesis_dir(thesis_id) / "comparisons"
        if not root.exists():
            return ()
        records = []
        for path in root.glob("cmp_*.json"):
            try:
                record = Comparison.from_dict(self._read_json(path))
            except ValueError as exc:
                raise RepositoryCorruptionError("Invalid comparison record.") from exc
            if record.thesis_id != thesis_id:
                raise RepositoryCorruptionError("Comparison is stored under the wrong thesis.")
            records.append(record)
        return tuple(sorted(records, key=lambda record: record.comparison_id))
