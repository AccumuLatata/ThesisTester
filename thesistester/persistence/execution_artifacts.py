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
    _fs_path,
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
    if store_root is not None:
        root = _fs_path(Path(store_root).expanduser().resolve())
    else:
        root = get_store_root()
    # Re-apply extended-length prefix after resolve(): on Windows, Path.resolve()
    # may strip \\?\ which would re-expose nested artifact paths to MAX_PATH.
    return _fs_path(
        (root / EXECUTION_ARTIFACTS_DIRNAME / f"v{DATA_ARTIFACT_SCHEMA_VERSION}").resolve()
    )


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
    """Return ``path`` if it resolves inside ``root``; else ``None``.

    On Windows, ``Path.resolve()`` may strip the ``\\\\?\\`` extended-length
    prefix. Re-apply :func:`_fs_path` so nested artifact verify/read/delete/
    evict I/O stays under the Win32 long-path limit.
    """
    try:
        resolved_root = _fs_path(root.resolve())
        resolved = _fs_path(path.resolve())
        resolved.relative_to(resolved_root)
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
    """Update access timestamp and per-artifact hit counter (CAI-10)."""
    manifest = _read_json(manifest_path)
    manifest["accessed_at"] = _utcnow_iso()
    hit_count = _try_int(manifest.get("hit_count"))
    manifest["hit_count"] = 0 if hit_count is None else hit_count + 1
    _write_json(manifest_path, manifest)
    _fsync_file(manifest_path)
    return manifest


def _cache_stats_path(artifacts_root: Path) -> Path:
    return artifacts_root / "cache_stats.json"


def _record_cache_event(artifacts_root: Path, *, hit: bool = False, miss: bool = False) -> None:
    """Best-effort store-level hit/miss counters (CAI-10 inspection)."""
    if not hit and not miss:
        return
    stats_path = _cache_stats_path(artifacts_root)
    try:
        artifacts_root.mkdir(parents=True, exist_ok=True)
        lock = artifacts_root / "locks" / "cache_stats.lock"
        with _identity_lock(lock):
            if stats_path.exists():
                try:
                    stats = _read_json(stats_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    stats = {}
            else:
                stats = {}
            if not isinstance(stats, dict):
                stats = {}
            hits = _try_int(stats.get("hit_count")) or 0
            misses = _try_int(stats.get("miss_count")) or 0
            if hit:
                hits += 1
            if miss:
                misses += 1
            payload = {
                "kind": "execution_cache_stats",
                "hit_count": hits,
                "miss_count": misses,
                "updated_at": _utcnow_iso(),
                "app_version": __version__,
            }
            _write_json(stats_path, payload)
            _fsync_file(stats_path)
    except OSError:
        return


def _directory_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return int(path.stat().st_size)
        except OSError:
            return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += int((Path(root) / name).stat().st_size)
            except OSError:
                continue
    return total


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
            _record_cache_event(artifacts_root, miss=True)
            return ArtifactMiss(_MISS_MISSING)
        result = _verify_data_dir(artifact_dir, expected=identity, artifacts_root=artifacts_root)
    if isinstance(result, ArtifactMiss):
        _record_cache_event(artifacts_root, miss=True)
    else:
        _record_cache_event(artifacts_root, hit=True)
    return result


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
            _record_cache_event(artifacts_root, miss=True)
            return ArtifactMiss(_MISS_MISSING)
        result = _verify_levels_dir(artifact_dir, expected=identity, artifacts_root=artifacts_root)
    if isinstance(result, ArtifactMiss):
        _record_cache_event(artifacts_root, miss=True)
    else:
        _record_cache_event(artifacts_root, hit=True)
    return result


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
                "hit_count": 0,
                "producer": "execution_artifacts.write_data_artifact",
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
                "hit_count": 0,
                "producer": "execution_artifacts.write_levels_artifact",
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
    ingestion_mode: str = "primary",
    derivation_policy: str | None = None,
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
        "ingestion_mode": str(ingestion_mode or "primary"),
        "derivation_policy": derivation_policy,
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
    ingestion_mode: str = "primary",
    derivation_policy: str | None = None,
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
        ingestion_mode=ingestion_mode,
        derivation_policy=derivation_policy,
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
        # Best-effort per-binding access accounting. Do not record a store-level
        # cache hit here — warm loads also call read_verified_data_artifact, and
        # double-counting would inflate CAI-10 hit_rate.
        try:
            payload["accessed_at"] = _utcnow_iso()
            hit_count = _try_int(payload.get("hit_count"))
            payload["hit_count"] = 0 if hit_count is None else hit_count + 1
            _write_json(contained, payload)
            _fsync_file(contained)
        except OSError:
            pass
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
    ingestion_mode: str = "primary",
    derivation_policy: str | None = None,
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
        ingestion_mode=ingestion_mode,
        derivation_policy=derivation_policy,
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
        "ingestion_mode": str(ingestion_mode or "primary"),
        "derivation_policy": derivation_policy,
        "data_artifact_key": artifact_key,
        "identity": identity.to_dict(),
        "last_source_path": str(path.resolve()),
        "created_at": _utcnow_iso(),
        "accessed_at": _utcnow_iso(),
        "hit_count": 0,
        "producer": "execution_artifacts.write_source_data_binding",
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
    ingestion_mode: str = "primary",
    derivation_policy: str | None = None,
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
        ingestion_mode=ingestion_mode,
        derivation_policy=derivation_policy,
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


# ── CAI-10: inspection, safe deletion, eviction, source relocation ───────────

EXECUTION_ARTIFACT_KINDS = frozenset({"data", "levels", "source_binding"})
# User-facing / thesis namespaces that eviction must never touch.
_PROTECTED_STORE_DIRNAMES = frozenset({"datasets", "levels", "signals", "setups", "assistant"})


def get_execution_cache_stats(store_root: str | Path | None = None) -> dict[str, Any]:
    """Return store-level hit/miss counters and total execution-artifact bytes."""
    artifacts_root = get_execution_artifacts_root(store_root)
    stats: dict[str, Any] = {
        "kind": "execution_cache_stats",
        "hit_count": 0,
        "miss_count": 0,
        "updated_at": None,
        "total_bytes": _directory_size_bytes(artifacts_root),
        "artifacts_root": str(artifacts_root),
    }
    stats_path = _cache_stats_path(artifacts_root)
    if stats_path.is_file():
        try:
            payload = _read_json(stats_path)
            if isinstance(payload, dict):
                stats["hit_count"] = _try_int(payload.get("hit_count")) or 0
                stats["miss_count"] = _try_int(payload.get("miss_count")) or 0
                stats["updated_at"] = payload.get("updated_at")
                stats["app_version"] = payload.get("app_version")
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return stats


def _inspect_dir_artifact(
    artifact_dir: Path,
    *,
    kind: str,
    artifacts_root: Path,
) -> dict[str, Any] | None:
    contained = _contain_path(artifact_dir, root=artifacts_root)
    if contained is None or not contained.is_dir():
        return None
    # Skip incomplete temp publish directories.
    if contained.name.startswith("."):
        return None
    manifest_path = contained / MANIFEST_FILENAME
    identity_path = contained / IDENTITY_FILENAME
    if not manifest_path.is_file():
        return None
    try:
        manifest = _read_json(manifest_path)
        identity = _read_json(identity_path) if identity_path.is_file() else None
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "kind": kind,
            "artifact_key": contained.name,
            "path": str(contained),
            "size_bytes": _directory_size_bytes(contained),
            "corrupt": True,
        }
    created = manifest.get("created_at")
    accessed = manifest.get("accessed_at")
    age_seconds = None
    created_dt = _parse_iso_timestamp(created)
    if created_dt is not None:
        age_seconds = max(
            0,
            int((datetime.now(timezone.utc) - created_dt.astimezone(timezone.utc)).total_seconds()),
        )
    return {
        "kind": kind,
        "artifact_key": str(manifest.get("artifact_key") or contained.name),
        "path": str(contained),
        "size_bytes": _directory_size_bytes(contained),
        "created_at": created,
        "accessed_at": accessed,
        "age_seconds": age_seconds,
        "hit_count": _try_int(manifest.get("hit_count")) or 0,
        "producer": manifest.get("producer") or manifest.get("kind"),
        "app_version": manifest.get("app_version"),
        "artifact_schema_version": manifest.get("artifact_schema_version"),
        "level_engine_version": manifest.get("level_engine_version"),
        "identity": identity if isinstance(identity, dict) else manifest.get("identity"),
        "corrupt": False,
    }


def _inspect_source_binding(binding_path: Path, *, artifacts_root: Path) -> dict[str, Any] | None:
    contained = _contain_path(binding_path, root=artifacts_root)
    if contained is None or not contained.is_file():
        return None
    if contained.name.startswith(".") or not contained.name.endswith(".json"):
        return None
    try:
        payload = _read_json(contained)
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "kind": "source_binding",
            "artifact_key": contained.stem,
            "path": str(contained),
            "size_bytes": _directory_size_bytes(contained),
            "corrupt": True,
        }
    created = payload.get("created_at")
    created_dt = _parse_iso_timestamp(created)
    age_seconds = None
    if created_dt is not None:
        age_seconds = max(
            0,
            int((datetime.now(timezone.utc) - created_dt.astimezone(timezone.utc)).total_seconds()),
        )
    return {
        "kind": "source_binding",
        "artifact_key": str(payload.get("binding_key") or contained.stem),
        "path": str(contained),
        "size_bytes": _directory_size_bytes(contained),
        "created_at": created,
        "accessed_at": payload.get("accessed_at"),
        "age_seconds": age_seconds,
        "hit_count": _try_int(payload.get("hit_count")) or 0,
        "producer": payload.get("producer") or SOURCE_BINDING_KIND,
        "app_version": payload.get("app_version"),
        "artifact_schema_version": payload.get("artifact_schema_version"),
        "level_engine_version": None,
        "identity": payload.get("identity"),
        "source_content_hash": payload.get("source_content_hash"),
        "last_source_path": payload.get("last_source_path"),
        "data_artifact_key": payload.get("data_artifact_key"),
        "corrupt": False,
    }


def list_execution_artifacts(
    store_root: str | Path | None = None,
    *,
    kind: str | None = None,
    limit: int | None = 200,
) -> list[dict[str, Any]]:
    """List inspection records for internal execution artifacts (CAI-10).

    ``limit`` defaults to 200 and is capped at 1000 for inspect UIs. Pass
    ``limit=None`` for an unbounded scan (eviction / retention only).
    """
    if kind is not None and kind not in EXECUTION_ARTIFACT_KINDS:
        raise ValueError(f"kind must be one of {sorted(EXECUTION_ARTIFACT_KINDS)} or None.")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise ValueError("limit must be a positive integer or None.")
    capped = None if limit is None else min(limit, 1000)
    artifacts_root = get_execution_artifacts_root(store_root)
    records: list[dict[str, Any]] = []
    kinds = (kind,) if kind is not None else ("data", "levels", "source_binding")
    for artifact_kind in kinds:
        if artifact_kind == "data":
            root = artifacts_root / "data"
            if root.is_dir():
                for child in sorted(root.iterdir()):
                    record = _inspect_dir_artifact(
                        child, kind="data", artifacts_root=artifacts_root
                    )
                    if record is not None:
                        records.append(record)
        elif artifact_kind == "levels":
            root = artifacts_root / "levels"
            if root.is_dir():
                for child in sorted(root.iterdir()):
                    record = _inspect_dir_artifact(
                        child, kind="levels", artifacts_root=artifacts_root
                    )
                    if record is not None:
                        records.append(record)
        else:
            root = artifacts_root / "source_index"
            if root.is_dir():
                for child in sorted(root.iterdir()):
                    record = _inspect_source_binding(child, artifacts_root=artifacts_root)
                    if record is not None:
                        records.append(record)
    # Newest accessed/created first for operability.
    records.sort(
        key=lambda item: str(item.get("accessed_at") or item.get("created_at") or ""),
        reverse=True,
    )
    if capped is None:
        return records
    return records[:capped]


def delete_execution_artifact(
    *,
    kind: str,
    artifact_key: str,
    store_root: str | Path | None = None,
) -> dict[str, Any]:
    """Safely delete one internal execution artifact by kind + key.

    Never deletes user datasets, saved levels snapshots, signal runs, setups,
    thesis records, or research bundles. After deletion, the next cache read
    misses and the pipeline recomputes cold.
    """
    if kind not in EXECUTION_ARTIFACT_KINDS:
        raise ValueError(f"kind must be one of {sorted(EXECUTION_ARTIFACT_KINDS)}.")
    if not isinstance(artifact_key, str) or not artifact_key.strip():
        raise ValueError("artifact_key must be a non-empty string.")
    key = artifact_key.strip()
    if "/" in key or "\\" in key or key in {".", ".."}:
        raise ValueError("artifact_key must be a flat store key.")
    artifacts_root = get_execution_artifacts_root(store_root)
    deleted = False
    if kind == "data":
        target = _data_dir(key, artifacts_root=artifacts_root)
        contained = _contain_path(target, root=artifacts_root)
        if contained is not None:
            lock = _lock_path("data", key, artifacts_root=artifacts_root)
            with _identity_lock(lock):
                if contained.exists():
                    shutil.rmtree(contained)
                    deleted = True
    elif kind == "levels":
        target = _levels_dir(key, artifacts_root=artifacts_root)
        contained = _contain_path(target, root=artifacts_root)
        if contained is not None:
            lock = _lock_path("levels", key, artifacts_root=artifacts_root)
            with _identity_lock(lock):
                if contained.exists():
                    shutil.rmtree(contained)
                    deleted = True
    else:
        target = _source_binding_path(key, artifacts_root=artifacts_root)
        contained = _contain_path(target, root=artifacts_root)
        if contained is not None:
            lock = _lock_path("source", key, artifacts_root=artifacts_root)
            with _identity_lock(lock):
                if contained.exists():
                    contained.unlink()
                    deleted = True
    return {
        "kind": kind,
        "artifact_key": key,
        "deleted": deleted,
        "cold_recompute_required": True,
    }


def _assert_path_under_execution_artifacts(path: Path, *, artifacts_root: Path) -> Path:
    contained = _contain_path(path, root=artifacts_root)
    if contained is None:
        raise ValueError("Refusing to mutate a path outside execution_artifacts.")
    # Extra fail-closed guard against store-root siblings.
    store_root = artifacts_root.parent.parent  # .../execution_artifacts/v1 → store
    for name in _PROTECTED_STORE_DIRNAMES:
        protected = _fs_path((store_root / name).resolve())
        try:
            _fs_path(contained.resolve()).relative_to(protected)
        except ValueError:
            continue
        raise ValueError(f"Refusing to mutate protected store namespace: {name}")
    return contained


def evict_execution_artifacts(
    *,
    store_root: str | Path | None = None,
    max_entries: int | None = None,
    max_total_bytes: int | None = None,
    max_age_seconds: int | None = None,
) -> dict[str, Any]:
    """Bounded LRU/age eviction for internal execution artifacts only (CAI-10).

    Never touches user-saved snapshots, bundles, thesis records, or datasets.
    Research bundles independently contain required data, so eviction is
    cold-recompute-safe for retained completed runs.
    """
    if max_entries is None and max_total_bytes is None and max_age_seconds is None:
        raise ValueError(
            "Provide at least one of max_entries, max_total_bytes, or max_age_seconds."
        )
    if max_entries is not None and (not isinstance(max_entries, int) or max_entries < 0):
        raise ValueError("max_entries must be a non-negative integer.")
    if max_total_bytes is not None and (
        not isinstance(max_total_bytes, int) or max_total_bytes < 0
    ):
        raise ValueError("max_total_bytes must be a non-negative integer.")
    if max_age_seconds is not None and (
        not isinstance(max_age_seconds, int) or max_age_seconds < 0
    ):
        raise ValueError("max_age_seconds must be a non-negative integer.")

    artifacts_root = get_execution_artifacts_root(store_root)
    # Unbounded scan so max_entries / bytes / age can bound the full store.
    records = list_execution_artifacts(store_root=store_root, limit=None)
    # Evict oldest accessed first (LRU); missing accessed_at falls back to created_at.
    records.sort(key=lambda item: str(item.get("accessed_at") or item.get("created_at") or ""))
    now = datetime.now(timezone.utc)
    to_delete: list[dict[str, Any]] = []
    if max_age_seconds is not None:
        for record in records:
            # LRU age: prefer last access so hot artifacts are retained.
            age_dt = _parse_iso_timestamp(record.get("accessed_at")) or _parse_iso_timestamp(
                record.get("created_at")
            )
            if age_dt is None:
                continue
            age = (now - age_dt.astimezone(timezone.utc)).total_seconds()
            if age > max_age_seconds:
                to_delete.append(record)

    remaining = [r for r in records if r not in to_delete]
    if max_entries is not None and len(remaining) > max_entries:
        overflow = len(remaining) - max_entries
        to_delete.extend(remaining[:overflow])
        remaining = remaining[overflow:]

    if max_total_bytes is not None:
        total = sum(int(r.get("size_bytes") or 0) for r in remaining)
        idx = 0
        while total > max_total_bytes and idx < len(remaining):
            victim = remaining[idx]
            to_delete.append(victim)
            total -= int(victim.get("size_bytes") or 0)
            idx += 1
        remaining = remaining[idx:]

    deleted: list[dict[str, Any]] = []
    for record in to_delete:
        kind = str(record.get("kind"))
        key = str(record.get("artifact_key"))
        # Containment guard before delete.
        path = Path(str(record.get("path")))
        _assert_path_under_execution_artifacts(path, artifacts_root=artifacts_root)
        result = delete_execution_artifact(kind=kind, artifact_key=key, store_root=store_root)
        if result["deleted"]:
            deleted.append(result)

    remaining_after = list_execution_artifacts(store_root=store_root, limit=None)
    return {
        "deleted_count": len(deleted),
        "deleted": deleted,
        "remaining_count": len(remaining_after),
        "total_bytes": get_execution_cache_stats(store_root)["total_bytes"],
        "cold_recompute_required": True,
        "protected_namespaces": sorted(_PROTECTED_STORE_DIRNAMES),
    }


def rebind_source_path(
    *,
    new_source_path: str | Path,
    expected_identity: DataIdentity | Mapping[str, Any],
    instrument: str | None = None,
    source_timezone: str | None = None,
    exchange_timezone: str | None = None,
    format_profile: str | None = None,
    ingestion_mode: str = "primary",
    derivation_policy: str | None = None,
    store_root: str | Path | None = None,
) -> SourceDataBinding:
    """Rebind a source CSV path after content-identity verification (CAI-10).

    Loads the new path with the expected ingest contract and fails closed unless
    the resulting ``DataIdentity.data_content_hash`` matches. Then writes/updates
    the source binding with ``last_source_path``.
    """
    if isinstance(expected_identity, DataIdentity):
        identity = expected_identity
    else:
        parsed = DataIdentity.from_dict(expected_identity)
        if parsed is None:
            raise ValueError("expected_identity must be a DataIdentity or mapping.")
        identity = parsed

    path = Path(new_source_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"new_source_path does not exist: {path}")

    inst = instrument or identity.instrument
    src_tz = source_timezone if source_timezone is not None else identity.source_timezone
    exch_tz = exchange_timezone if exchange_timezone is not None else identity.exchange_timezone
    profile = format_profile or identity.format_profile

    # Lazy import avoids api ↔ persistence import cycles at module load.
    from thesistester.api import load_dataset

    try:
        loaded = load_dataset(
            path,
            instrument=inst,
            source_timezone=src_tz,
            exchange_timezone=exch_tz,
            format_profile=profile,
        )
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"Unable to load new_source_path for identity verification: {exc}"
        ) from exc

    loaded_identity = DataIdentity.from_loaded_data(
        loaded,
        instrument=inst,
        base_interval=identity.base_interval,
        source_timezone=src_tz,
        exchange_timezone=exch_tz,
        format_profile=profile,
    )
    if loaded_identity.data_content_hash != identity.data_content_hash:
        raise ValueError(
            "Source CSV content does not match expected DataIdentity; refusing rebind."
        )
    if loaded_identity.dataset_id() != identity.dataset_id():
        raise ValueError(
            "Source CSV dataset_id does not match expected DataIdentity; refusing rebind."
        )

    # Ensure the data artifact exists or can be published for warm reuse.
    existing = read_verified_data_artifact(identity, store_root=store_root)
    if isinstance(existing, ArtifactMiss):
        write_data_artifact(identity, loaded, store_root=store_root)

    return write_source_data_binding(
        source_path=path,
        identity=identity,
        instrument=inst,
        source_timezone=src_tz,
        exchange_timezone=exch_tz,
        format_profile=profile,
        ingestion_mode=ingestion_mode,
        derivation_policy=derivation_policy,
        store_root=store_root,
    )
