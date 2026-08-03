"""Internal execution-artifact store for canonical data and levels (CAI-2/3).

This namespace is separate from user-facing datasets/ and levels/ snapshots.
CAI-3 wires verified reuse into ``run_experiment`` / ``compute_levels`` behind
an explicit cache policy (default off).

Read APIs never raise for corrupt or incompatible artifacts — they return
:class:`ArtifactMiss` so callers can fall through to a cold computation.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

import pandas as pd

from thesistester import __version__
from thesistester.persistence.local_store import (
    LEVEL_ENGINE_VERSION,
    _canonicalize_dataframe,
    _hash_dataframe,
    _stable_json_bytes,
    compute_levels_settings_hash,
    get_store_root,
)
from thesistester.research_identity import (
    LEVELS_ARTIFACT_SCHEMA_VERSION,
    RESEARCH_IDENTITY_SCHEMA_VERSION,
    DataIdentity,
    LevelsIdentity,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]

DATA_ARTIFACT_SCHEMA_VERSION = 1
EXECUTION_ARTIFACTS_DIRNAME = "execution_artifacts"
MANIFEST_FILENAME = "manifest.json"
IDENTITY_FILENAME = "identity.json"
DATA_PARQUET_FILENAME = "data.parquet"
LEVELS_PARQUET_FILENAME = "levels.parquet"
SESSION_LEVELS_PARQUET_FILENAME = "session_levels.parquet"
LEVELS_SETTINGS_FILENAME = "levels_settings.json"
INGESTION_META_FILENAME = "ingestion_meta.json"
SOURCE_BINDING_KIND = "execution_source_binding"

_DATA_KIND = "execution_data_artifact"
_LEVELS_KIND = "execution_levels_artifact"
CACHE_POLICIES = frozenset({"off", "read", "read_write"})
CACHE_OUTCOMES = frozenset({"bypassed", "cold", "data_hit", "levels_hit"})

_MISS_MISSING = "missing"
_MISS_CORRUPT_MANIFEST = "corrupt_manifest"
_MISS_INCOMPLETE = "incomplete"
_MISS_SCHEMA_DRIFT = "schema_drift"
_MISS_ENGINE_INCOMPATIBLE = "engine_incompatible"
_MISS_IDENTITY_MISMATCH = "identity_mismatch"
_MISS_CONTENT_MISMATCH = "content_mismatch"
_MISS_PATH_ESCAPE = "path_escape"


@dataclass(frozen=True, slots=True)
class ArtifactMiss:
    """Verified-read miss; safe signal to compute cold."""

    reason: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class DataArtifact:
    """Verified canonical data artifact."""

    identity: DataIdentity
    data: pd.DataFrame
    manifest: Mapping[str, Any]
    path: Path

    @property
    def artifact_key(self) -> str:
        return str(self.manifest.get("artifact_key") or data_artifact_key(self.identity))


@dataclass(frozen=True, slots=True)
class LevelsArtifact:
    """Verified levels + session-levels artifact."""

    identity: LevelsIdentity
    levels: pd.DataFrame
    session_levels: pd.DataFrame
    levels_settings: Mapping[str, Any]
    manifest: Mapping[str, Any]
    path: Path

    @property
    def artifact_key(self) -> str:
        return str(self.manifest.get("artifact_key") or levels_artifact_key(self.identity))


def get_execution_artifacts_root(store_root: str | Path | None = None) -> Path:
    """Return the internal execution-artifact root (schema-versioned)."""
    root = Path(store_root).expanduser().resolve() if store_root is not None else get_store_root()
    return (root / EXECUTION_ARTIFACTS_DIRNAME / f"v{DATA_ARTIFACT_SCHEMA_VERSION}").resolve()


def data_artifact_key(identity: DataIdentity) -> str:
    """Content-addressed key for a data artifact (includes format_profile)."""
    payload = {
        "kind": _DATA_KIND,
        "artifact_schema_version": DATA_ARTIFACT_SCHEMA_VERSION,
        "identity_schema_version": identity.identity_schema_version,
        "persistence_schema_version": identity.persistence_schema_version,
        "data_content_hash": identity.data_content_hash,
        "instrument": identity.instrument,
        "base_interval": identity.base_interval,
        "source_timezone": identity.source_timezone,
        "exchange_timezone": identity.exchange_timezone,
        "format_profile": identity.format_profile,
    }
    return hashlib.sha256(_stable_json_bytes(payload)).hexdigest()


def levels_artifact_key(identity: LevelsIdentity) -> str:
    """Content-addressed key for a levels artifact."""
    payload = {
        "kind": _LEVELS_KIND,
        "artifact_schema_version": identity.artifact_schema_version,
        "level_engine_version": identity.level_engine_version,
        "levels_settings_hash": identity.levels_settings_hash,
        "data_artifact_key": data_artifact_key(identity.data_identity),
        "identity_schema_version": identity.identity_schema_version,
    }
    return hashlib.sha256(_stable_json_bytes(payload)).hexdigest()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def _fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _hash_file_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _identity_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _contain_path(path: Path, *, root: Path) -> Path | None:
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def _try_int(value: Any) -> int | None:
    """Coerce a manifest version field without raising.

    Verified reads must return :class:`ArtifactMiss` for corrupt manifests, so
    bare ``int(...)`` on JSON null / non-numeric strings is not allowed.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _data_dir(key: str, *, artifacts_root: Path) -> Path:
    return artifacts_root / "data" / key


def _levels_dir(key: str, *, artifacts_root: Path) -> Path:
    return artifacts_root / "levels" / key


def _lock_path(kind: str, key: str, *, artifacts_root: Path) -> Path:
    return artifacts_root / "locks" / f"{kind}-{key}.lock"


def _touch_accessed_at(manifest_path: Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    manifest["accessed_at"] = _utcnow_iso()
    _write_json(manifest_path, manifest)
    _fsync_file(manifest_path)
    return manifest


def _publish_directory(temp_dir: Path, final_dir: Path) -> None:
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    if final_dir.exists():
        shutil.rmtree(final_dir)
    os.rename(temp_dir, final_dir)
    _fsync_dir(final_dir)
    _fsync_dir(final_dir.parent)


def _cleanup_temp(temp_dir: Path) -> None:
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def _verify_data_dir(
    artifact_dir: Path,
    *,
    expected: DataIdentity,
    artifacts_root: Path,
) -> DataArtifact | ArtifactMiss:
    contained = _contain_path(artifact_dir, root=artifacts_root)
    if contained is None:
        return ArtifactMiss(_MISS_PATH_ESCAPE, detail=str(artifact_dir))

    manifest_path = contained / MANIFEST_FILENAME
    data_path = contained / DATA_PARQUET_FILENAME
    identity_path = contained / IDENTITY_FILENAME
    if not manifest_path.exists():
        return ArtifactMiss(_MISS_MISSING, detail="manifest")
    if not data_path.exists() or not identity_path.exists():
        return ArtifactMiss(_MISS_INCOMPLETE, detail="missing required files")

    try:
        manifest = _read_json(manifest_path)
        stored_identity = DataIdentity.from_dict(_read_json(identity_path))
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        return ArtifactMiss(_MISS_CORRUPT_MANIFEST, detail=str(exc))

    if stored_identity is None:
        return ArtifactMiss(_MISS_CORRUPT_MANIFEST, detail="identity")
    if manifest.get("kind") != _DATA_KIND:
        return ArtifactMiss(_MISS_CORRUPT_MANIFEST, detail="kind")
    schema_version = _try_int(manifest.get("artifact_schema_version", -1))
    if schema_version is None:
        return ArtifactMiss(
            _MISS_CORRUPT_MANIFEST,
            detail=f"artifact_schema_version={manifest.get('artifact_schema_version')!r}",
        )
    if schema_version != DATA_ARTIFACT_SCHEMA_VERSION:
        return ArtifactMiss(
            _MISS_SCHEMA_DRIFT,
            detail=f"artifact_schema_version={manifest.get('artifact_schema_version')}",
        )
    if (
        stored_identity.data_content_hash != expected.data_content_hash
        or stored_identity.instrument != expected.instrument
        or stored_identity.base_interval != expected.base_interval
        or stored_identity.source_timezone != expected.source_timezone
        or stored_identity.exchange_timezone != expected.exchange_timezone
        or stored_identity.format_profile != expected.format_profile
    ):
        return ArtifactMiss(_MISS_IDENTITY_MISMATCH)

    try:
        data = pd.read_parquet(data_path)
    except Exception as exc:  # pragma: no cover - pyarrow/pandas variance
        return ArtifactMiss(_MISS_INCOMPLETE, detail=f"parquet:{exc}")

    content_hash = _hash_dataframe(data)
    if content_hash != expected.data_content_hash:
        return ArtifactMiss(_MISS_CONTENT_MISMATCH, detail="data_content_hash")

    try:
        manifest = _touch_accessed_at(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        pass

    return DataArtifact(
        identity=expected,
        data=data,
        manifest=manifest,
        path=contained,
    )


def _verify_levels_dir(
    artifact_dir: Path,
    *,
    expected: LevelsIdentity,
    artifacts_root: Path,
) -> LevelsArtifact | ArtifactMiss:
    contained = _contain_path(artifact_dir, root=artifacts_root)
    if contained is None:
        return ArtifactMiss(_MISS_PATH_ESCAPE, detail=str(artifact_dir))

    manifest_path = contained / MANIFEST_FILENAME
    levels_path = contained / LEVELS_PARQUET_FILENAME
    session_path = contained / SESSION_LEVELS_PARQUET_FILENAME
    identity_path = contained / IDENTITY_FILENAME
    settings_path = contained / LEVELS_SETTINGS_FILENAME
    required = (manifest_path, levels_path, session_path, identity_path, settings_path)
    if not manifest_path.exists():
        return ArtifactMiss(_MISS_MISSING, detail="manifest")
    if any(not path.exists() for path in required[1:]):
        return ArtifactMiss(_MISS_INCOMPLETE, detail="missing required files")

    try:
        manifest = _read_json(manifest_path)
        stored_identity = LevelsIdentity.from_dict(_read_json(identity_path))
        levels_settings = _read_json(settings_path)
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        return ArtifactMiss(_MISS_CORRUPT_MANIFEST, detail=str(exc))

    if stored_identity is None:
        return ArtifactMiss(_MISS_CORRUPT_MANIFEST, detail="identity")
    if manifest.get("kind") != _LEVELS_KIND:
        return ArtifactMiss(_MISS_CORRUPT_MANIFEST, detail="kind")
    schema_version = _try_int(manifest.get("artifact_schema_version", -1))
    if schema_version is None:
        return ArtifactMiss(
            _MISS_CORRUPT_MANIFEST,
            detail=f"artifact_schema_version={manifest.get('artifact_schema_version')!r}",
        )
    if schema_version != LEVELS_ARTIFACT_SCHEMA_VERSION:
        return ArtifactMiss(
            _MISS_SCHEMA_DRIFT,
            detail=f"artifact_schema_version={manifest.get('artifact_schema_version')}",
        )
    engine_version = _try_int(manifest.get("level_engine_version", -1))
    if engine_version is None:
        return ArtifactMiss(
            _MISS_CORRUPT_MANIFEST,
            detail=f"level_engine_version={manifest.get('level_engine_version')!r}",
        )
    if engine_version != LEVEL_ENGINE_VERSION:
        return ArtifactMiss(
            _MISS_ENGINE_INCOMPATIBLE,
            detail=f"level_engine_version={manifest.get('level_engine_version')}",
        )
    if stored_identity.level_engine_version != expected.level_engine_version:
        return ArtifactMiss(
            _MISS_ENGINE_INCOMPATIBLE,
            detail="identity.level_engine_version",
        )
    if stored_identity.levels_settings_hash != expected.levels_settings_hash:
        return ArtifactMiss(_MISS_IDENTITY_MISMATCH, detail="levels_settings_hash")
    if data_artifact_key(stored_identity.data_identity) != data_artifact_key(
        expected.data_identity
    ):
        return ArtifactMiss(_MISS_IDENTITY_MISMATCH, detail="data_identity")

    settings_hash = compute_levels_settings_hash(levels_settings)
    if settings_hash != expected.levels_settings_hash:
        return ArtifactMiss(_MISS_CONTENT_MISMATCH, detail="levels_settings_hash")

    try:
        levels = pd.read_parquet(levels_path)
        session_levels = pd.read_parquet(session_path)
    except Exception as exc:  # pragma: no cover
        return ArtifactMiss(_MISS_INCOMPLETE, detail=f"parquet:{exc}")

    try:
        manifest = _touch_accessed_at(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        pass

    return LevelsArtifact(
        identity=expected,
        levels=levels,
        session_levels=session_levels,
        levels_settings=levels_settings,
        manifest=manifest,
        path=contained,
    )


def read_verified_data_artifact(
    identity: DataIdentity,
    *,
    store_root: str | Path | None = None,
) -> DataArtifact | ArtifactMiss:
    """Return a verified data artifact or a miss reason."""
    artifacts_root = get_execution_artifacts_root(store_root)
    key = data_artifact_key(identity)
    artifact_dir = _data_dir(key, artifacts_root=artifacts_root)
    lock = _lock_path("data", key, artifacts_root=artifacts_root)
    with _identity_lock(lock):
        if not artifact_dir.exists():
            return ArtifactMiss(_MISS_MISSING)
        return _verify_data_dir(artifact_dir, expected=identity, artifacts_root=artifacts_root)


def read_verified_levels_artifact(
    identity: LevelsIdentity,
    *,
    store_root: str | Path | None = None,
) -> LevelsArtifact | ArtifactMiss:
    """Return a verified levels artifact or a miss reason."""
    artifacts_root = get_execution_artifacts_root(store_root)
    key = levels_artifact_key(identity)
    artifact_dir = _levels_dir(key, artifacts_root=artifacts_root)
    lock = _lock_path("levels", key, artifacts_root=artifacts_root)
    with _identity_lock(lock):
        if not artifact_dir.exists():
            return ArtifactMiss(_MISS_MISSING)
        return _verify_levels_dir(artifact_dir, expected=identity, artifacts_root=artifacts_root)


def write_data_artifact(
    identity: DataIdentity,
    data: pd.DataFrame,
    *,
    ingestion_meta: Mapping[str, Any] | None = None,
    store_root: str | Path | None = None,
) -> DataArtifact:
    """Atomically publish a data artifact, reusing a verified equivalent if present."""
    if _hash_dataframe(data) != identity.data_content_hash:
        raise ValueError("data content hash does not match DataIdentity.data_content_hash")

    artifacts_root = get_execution_artifacts_root(store_root)
    key = data_artifact_key(identity)
    artifact_dir = _data_dir(key, artifacts_root=artifacts_root)
    lock = _lock_path("data", key, artifacts_root=artifacts_root)

    with _identity_lock(lock):
        if artifact_dir.exists():
            existing = _verify_data_dir(
                artifact_dir, expected=identity, artifacts_root=artifacts_root
            )
            if isinstance(existing, DataArtifact):
                return existing
            shutil.rmtree(artifact_dir, ignore_errors=True)

        artifact_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{key}.tmp.", dir=str(artifact_dir.parent)))
        try:
            canonical = _canonicalize_dataframe(data)
            data_path = temp_dir / DATA_PARQUET_FILENAME
            canonical.to_parquet(data_path, index=False)
            identity_payload = identity.to_dict()
            _write_json(temp_dir / IDENTITY_FILENAME, identity_payload)
            ingestion = dict(ingestion_meta or {})
            ingestion.setdefault("rows", int(len(canonical)))
            ingestion.setdefault("columns", [str(column) for column in canonical.columns])
            _write_json(temp_dir / INGESTION_META_FILENAME, ingestion)
            created_at = _utcnow_iso()
            manifest = {
                "kind": _DATA_KIND,
                "artifact_schema_version": DATA_ARTIFACT_SCHEMA_VERSION,
                "identity_schema_version": RESEARCH_IDENTITY_SCHEMA_VERSION,
                "persistence_schema_version": identity.persistence_schema_version,
                "artifact_key": key,
                "identity": identity_payload,
                "files": {
                    DATA_PARQUET_FILENAME: {
                        "sha256": _hash_file_bytes(data_path),
                        "rows": int(len(canonical)),
                        "content_hash": identity.data_content_hash,
                    }
                },
                "ingestion": ingestion,
                "created_at": created_at,
                "accessed_at": created_at,
                "app_version": __version__,
            }
            _write_json(temp_dir / MANIFEST_FILENAME, manifest)
            for path in (
                data_path,
                temp_dir / IDENTITY_FILENAME,
                temp_dir / INGESTION_META_FILENAME,
                temp_dir / MANIFEST_FILENAME,
            ):
                _fsync_file(path)
            _fsync_dir(temp_dir)
            _publish_directory(temp_dir, artifact_dir)
        except Exception:
            _cleanup_temp(temp_dir)
            raise

        verified = _verify_data_dir(artifact_dir, expected=identity, artifacts_root=artifacts_root)
        if isinstance(verified, ArtifactMiss):
            raise RuntimeError(f"Published data artifact failed verification: {verified.reason}")
        return verified


def write_levels_artifact(
    identity: LevelsIdentity,
    levels: pd.DataFrame,
    session_levels: pd.DataFrame,
    *,
    levels_settings: Mapping[str, Any] | None = None,
    store_root: str | Path | None = None,
) -> LevelsArtifact:
    """Atomically publish a levels artifact, reusing a verified equivalent if present."""
    settings = dict(levels_settings) if levels_settings is not None else None
    if settings is None and identity.levels_settings is not None:
        settings = dict(identity.levels_settings)
    if settings is None:
        raise ValueError("levels_settings are required to publish a levels artifact")
    if compute_levels_settings_hash(settings) != identity.levels_settings_hash:
        raise ValueError("levels_settings hash does not match LevelsIdentity")

    artifacts_root = get_execution_artifacts_root(store_root)
    key = levels_artifact_key(identity)
    artifact_dir = _levels_dir(key, artifacts_root=artifacts_root)
    lock = _lock_path("levels", key, artifacts_root=artifacts_root)

    with _identity_lock(lock):
        if artifact_dir.exists():
            existing = _verify_levels_dir(
                artifact_dir, expected=identity, artifacts_root=artifacts_root
            )
            if isinstance(existing, LevelsArtifact):
                return existing
            shutil.rmtree(artifact_dir, ignore_errors=True)

        artifact_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{key}.tmp.", dir=str(artifact_dir.parent)))
        try:
            levels_path = temp_dir / LEVELS_PARQUET_FILENAME
            session_path = temp_dir / SESSION_LEVELS_PARQUET_FILENAME
            _canonicalize_dataframe(levels).to_parquet(levels_path, index=False)
            _canonicalize_dataframe(session_levels).to_parquet(session_path, index=False)
            identity_payload = identity.to_dict()
            _write_json(temp_dir / IDENTITY_FILENAME, identity_payload)
            _write_json(temp_dir / LEVELS_SETTINGS_FILENAME, settings)
            created_at = _utcnow_iso()
            manifest = {
                "kind": _LEVELS_KIND,
                "artifact_schema_version": LEVELS_ARTIFACT_SCHEMA_VERSION,
                "level_engine_version": identity.level_engine_version,
                "identity_schema_version": RESEARCH_IDENTITY_SCHEMA_VERSION,
                "artifact_key": key,
                "data_artifact_key": data_artifact_key(identity.data_identity),
                "levels_settings_hash": identity.levels_settings_hash,
                "identity": identity_payload,
                "files": {
                    LEVELS_PARQUET_FILENAME: {
                        "sha256": _hash_file_bytes(levels_path),
                        "rows": int(len(levels)),
                    },
                    SESSION_LEVELS_PARQUET_FILENAME: {
                        "sha256": _hash_file_bytes(session_path),
                        "rows": int(len(session_levels)),
                    },
                },
                "created_at": created_at,
                "accessed_at": created_at,
                "app_version": __version__,
            }
            _write_json(temp_dir / MANIFEST_FILENAME, manifest)
            for path in (
                levels_path,
                session_path,
                temp_dir / IDENTITY_FILENAME,
                temp_dir / LEVELS_SETTINGS_FILENAME,
                temp_dir / MANIFEST_FILENAME,
            ):
                _fsync_file(path)
            _fsync_dir(temp_dir)
            _publish_directory(temp_dir, artifact_dir)
        except Exception:
            _cleanup_temp(temp_dir)
            raise

        verified = _verify_levels_dir(
            artifact_dir, expected=identity, artifacts_root=artifacts_root
        )
        if isinstance(verified, ArtifactMiss):
            raise RuntimeError(f"Published levels artifact failed verification: {verified.reason}")
        return verified


def invalidate_data_artifact(
    identity: DataIdentity,
    *,
    store_root: str | Path | None = None,
) -> bool:
    """Remove a data artifact directory when present. Returns whether it existed."""
    artifacts_root = get_execution_artifacts_root(store_root)
    key = data_artifact_key(identity)
    artifact_dir = _data_dir(key, artifacts_root=artifacts_root)
    contained = _contain_path(artifact_dir, root=artifacts_root)
    if contained is None:
        return False
    lock = _lock_path("data", key, artifacts_root=artifacts_root)
    with _identity_lock(lock):
        if not contained.exists():
            return False
        shutil.rmtree(contained)
        return True


def invalidate_levels_artifact(
    identity: LevelsIdentity,
    *,
    store_root: str | Path | None = None,
) -> bool:
    """Remove a levels artifact directory when present. Returns whether it existed."""
    artifacts_root = get_execution_artifacts_root(store_root)
    key = levels_artifact_key(identity)
    artifact_dir = _levels_dir(key, artifacts_root=artifacts_root)
    contained = _contain_path(artifact_dir, root=artifacts_root)
    if contained is None:
        return False
    lock = _lock_path("levels", key, artifacts_root=artifacts_root)
    with _identity_lock(lock):
        if not contained.exists():
            return False
        shutil.rmtree(contained)
        return True


# Test/helper seam for path-containment coverage without inventing hex escapes.
def resolve_contained_artifact_path(
    relative_parts: tuple[str, ...],
    *,
    store_root: str | Path | None = None,
) -> Path | ArtifactMiss:
    """Resolve ``relative_parts`` under the artifacts root or return a path miss."""
    artifacts_root = get_execution_artifacts_root(store_root)
    candidate = artifacts_root.joinpath(*relative_parts)
    contained = _contain_path(candidate, root=artifacts_root)
    if contained is None:
        return ArtifactMiss(_MISS_PATH_ESCAPE, detail=str(candidate))
    return contained


def normalize_cache_policy(policy: str | None) -> str:
    """Return a supported cache policy; unknown values become ``off``."""
    if policy is None:
        return "off"
    text = str(policy).strip().lower()
    if text in {"legacy", "none", "bypass", "disabled"}:
        return "off"
    if text in CACHE_POLICIES:
        return text
    return "off"


def source_content_hash(path: str | Path) -> str:
    """Return a SHA-256 digest of raw source file bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def source_binding_key(
    *,
    source_content_hash_value: str,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str | None,
    format_profile: str,
) -> str:
    """Key for mapping source bytes + ingest contract → data artifact."""
    payload = {
        "kind": SOURCE_BINDING_KIND,
        "artifact_schema_version": DATA_ARTIFACT_SCHEMA_VERSION,
        "source_content_hash": source_content_hash_value,
        "instrument": instrument,
        "source_timezone": source_timezone,
        "exchange_timezone": exchange_timezone,
        "format_profile": format_profile,
    }
    return hashlib.sha256(_stable_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceDataBinding:
    """Resolved source-file binding to a canonical data artifact identity."""

    binding_key: str
    source_content_hash: str
    identity: DataIdentity
    data_artifact_key: str


def _source_binding_path(binding_key: str, *, artifacts_root: Path) -> Path:
    return artifacts_root / "source_index" / f"{binding_key}.json"


def read_source_data_binding(
    *,
    source_path: str | Path,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str | None,
    format_profile: str = "canonical",
    store_root: str | Path | None = None,
) -> SourceDataBinding | ArtifactMiss:
    """Resolve a verified source binding, or miss when absent/corrupt/stale."""
    path = Path(source_path)
    if not path.is_file():
        return ArtifactMiss(_MISS_MISSING, detail="source_path")
    try:
        content_hash = source_content_hash(path)
    except OSError as exc:
        return ArtifactMiss(_MISS_INCOMPLETE, detail=str(exc))

    artifacts_root = get_execution_artifacts_root(store_root)
    key = source_binding_key(
        source_content_hash_value=content_hash,
        instrument=instrument,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        format_profile=format_profile,
    )
    binding_path = _source_binding_path(key, artifacts_root=artifacts_root)
    contained = _contain_path(binding_path, root=artifacts_root)
    if contained is None:
        return ArtifactMiss(_MISS_PATH_ESCAPE, detail=str(binding_path))
    if not contained.exists():
        return ArtifactMiss(_MISS_MISSING, detail="source_binding")

    lock = _lock_path("source", key, artifacts_root=artifacts_root)
    with _identity_lock(lock):
        try:
            payload = _read_json(contained)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return ArtifactMiss(_MISS_CORRUPT_MANIFEST, detail=str(exc))
        if payload.get("kind") != SOURCE_BINDING_KIND:
            return ArtifactMiss(_MISS_CORRUPT_MANIFEST, detail="kind")
        schema_version = _try_int(payload.get("artifact_schema_version", -1))
        if schema_version is None:
            return ArtifactMiss(
                _MISS_CORRUPT_MANIFEST,
                detail=f"artifact_schema_version={payload.get('artifact_schema_version')!r}",
            )
        if schema_version != DATA_ARTIFACT_SCHEMA_VERSION:
            return ArtifactMiss(
                _MISS_SCHEMA_DRIFT,
                detail=f"artifact_schema_version={payload.get('artifact_schema_version')}",
            )
        if payload.get("source_content_hash") != content_hash:
            return ArtifactMiss(_MISS_CONTENT_MISMATCH, detail="source_content_hash")
        identity = DataIdentity.from_dict(payload.get("identity"))
        artifact_key = payload.get("data_artifact_key")
        if identity is None or not isinstance(artifact_key, str) or not artifact_key:
            return ArtifactMiss(_MISS_CORRUPT_MANIFEST, detail="identity")
        if data_artifact_key(identity) != artifact_key:
            return ArtifactMiss(_MISS_IDENTITY_MISMATCH, detail="data_artifact_key")
        return SourceDataBinding(
            binding_key=key,
            source_content_hash=content_hash,
            identity=identity,
            data_artifact_key=artifact_key,
        )


def write_source_data_binding(
    *,
    source_path: str | Path,
    identity: DataIdentity,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str | None,
    format_profile: str = "canonical",
    store_root: str | Path | None = None,
) -> SourceDataBinding:
    """Persist a source-bytes → data-artifact binding for warm CSV skip."""
    path = Path(source_path)
    content_hash = source_content_hash(path)
    artifacts_root = get_execution_artifacts_root(store_root)
    key = source_binding_key(
        source_content_hash_value=content_hash,
        instrument=instrument,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        format_profile=format_profile,
    )
    artifact_key = data_artifact_key(identity)
    binding_path = _source_binding_path(key, artifacts_root=artifacts_root)
    contained_parent = _contain_path(binding_path.parent, root=artifacts_root)
    if contained_parent is None:
        raise ValueError(f"Source binding path escapes artifact root: {binding_path}")

    payload = {
        "kind": SOURCE_BINDING_KIND,
        "artifact_schema_version": DATA_ARTIFACT_SCHEMA_VERSION,
        "binding_key": key,
        "source_content_hash": content_hash,
        "instrument": instrument,
        "source_timezone": source_timezone,
        "exchange_timezone": exchange_timezone,
        "format_profile": format_profile,
        "data_artifact_key": artifact_key,
        "identity": identity.to_dict(),
        "created_at": _utcnow_iso(),
        "app_version": __version__,
    }
    lock = _lock_path("source", key, artifacts_root=artifacts_root)
    with _identity_lock(lock):
        binding_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = binding_path.with_suffix(f".tmp.{os.getpid()}.json")
        try:
            _write_json(temp_path, payload)
            _fsync_file(temp_path)
            os.replace(temp_path, binding_path)
            _fsync_dir(binding_path.parent)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
    return SourceDataBinding(
        binding_key=key,
        source_content_hash=content_hash,
        identity=identity,
        data_artifact_key=artifact_key,
    )


def invalidate_source_data_binding(
    *,
    source_path: str | Path,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str | None,
    format_profile: str = "canonical",
    store_root: str | Path | None = None,
) -> bool:
    """Remove a source binding when present."""
    path = Path(source_path)
    if not path.is_file():
        return False
    try:
        content_hash = source_content_hash(path)
    except OSError:
        return False
    artifacts_root = get_execution_artifacts_root(store_root)
    key = source_binding_key(
        source_content_hash_value=content_hash,
        instrument=instrument,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        format_profile=format_profile,
    )
    binding_path = _source_binding_path(key, artifacts_root=artifacts_root)
    contained = _contain_path(binding_path, root=artifacts_root)
    if contained is None:
        return False
    lock = _lock_path("source", key, artifacts_root=artifacts_root)
    with _identity_lock(lock):
        if not contained.exists():
            return False
        contained.unlink()
        return True


def summarize_cache_outcome(
    *,
    policy: str,
    data_status: str,
    levels_status: str,
) -> str:
    """Aggregate per-stage cache statuses into a provenance outcome."""
    if normalize_cache_policy(policy) == "off":
        return "bypassed"
    if levels_status == "hit":
        return "levels_hit"
    if data_status == "hit":
        return "data_hit"
    return "cold"
