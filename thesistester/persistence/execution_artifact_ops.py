"""Verify / publish / evict helpers for the execution-artifact store.

C-11 (QI-06-10): extracted from ``execution_artifacts.py`` so path-containment
guards stay at the store boundary. The facade applies ``_contain_path`` /
``_assert_path_under_execution_artifacts`` before verify/publish/evict
mutate or delete. Cache-policy defaults are unchanged. Cache is not
identity — ``source_binding_key`` vs ``dataset_id`` stays H9.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from thesistester import __version__
from thesistester.persistence.local_store import (
    LEVEL_ENGINE_VERSION,
    _canonicalize_dataframe,
    compute_levels_settings_hash,
    hash_dataframe,
)
from thesistester.research_identity import (
    LEVELS_ARTIFACT_SCHEMA_VERSION,
    RESEARCH_IDENTITY_SCHEMA_VERSION,
    DataIdentity,
    LevelsIdentity,
)


def _ea():
    from thesistester.persistence import execution_artifacts as module

    return module


def publish_directory(temp_dir: Path, final_dir: Path) -> None:
    ea = _ea()
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    if final_dir.exists():
        shutil.rmtree(final_dir)
    os.rename(temp_dir, final_dir)
    ea._fsync_dir(final_dir)
    ea._fsync_dir(final_dir.parent)


def cleanup_temp(temp_dir: Path) -> None:
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def verify_data_dir(
    artifact_dir: Path,
    *,
    expected: DataIdentity,
    artifacts_root: Path,
):
    ea = _ea()
    contained = ea._contain_path(artifact_dir, root=artifacts_root)
    if contained is None:
        return ea.ArtifactMiss(ea._MISS_PATH_ESCAPE, detail=str(artifact_dir))

    manifest_path = contained / ea.MANIFEST_FILENAME
    data_path = contained / ea.DATA_PARQUET_FILENAME
    identity_path = contained / ea.IDENTITY_FILENAME
    if not manifest_path.exists():
        return ea.ArtifactMiss(ea._MISS_MISSING, detail="manifest")
    if not data_path.exists() or not identity_path.exists():
        return ea.ArtifactMiss(ea._MISS_INCOMPLETE, detail="missing required files")

    try:
        manifest = ea._read_json(manifest_path)
        stored_identity = DataIdentity.from_dict(ea._read_json(identity_path))
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        return ea.ArtifactMiss(ea._MISS_CORRUPT_MANIFEST, detail=str(exc))

    if stored_identity is None:
        return ea.ArtifactMiss(ea._MISS_CORRUPT_MANIFEST, detail="identity")
    if manifest.get("kind") != ea._DATA_KIND:
        return ea.ArtifactMiss(ea._MISS_CORRUPT_MANIFEST, detail="kind")
    schema_version = ea._try_int(manifest.get("artifact_schema_version", -1))
    if schema_version is None:
        return ea.ArtifactMiss(
            ea._MISS_CORRUPT_MANIFEST,
            detail=f"artifact_schema_version={manifest.get('artifact_schema_version')!r}",
        )
    if schema_version != ea.DATA_ARTIFACT_SCHEMA_VERSION:
        return ea.ArtifactMiss(
            ea._MISS_SCHEMA_DRIFT,
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
        return ea.ArtifactMiss(ea._MISS_IDENTITY_MISMATCH)

    try:
        data = pd.read_parquet(data_path)
    except Exception as exc:  # pragma: no cover - pyarrow/pandas variance
        return ea.ArtifactMiss(ea._MISS_INCOMPLETE, detail=f"parquet:{exc}")

    content_hash = hash_dataframe(data)
    if content_hash != expected.data_content_hash:
        return ea.ArtifactMiss(ea._MISS_CONTENT_MISMATCH, detail="data_content_hash")

    try:
        manifest = ea._touch_accessed_at(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        pass

    return ea.DataArtifact(
        identity=expected,
        data=data,
        manifest=manifest,
        path=contained,
    )


def verify_levels_dir(
    artifact_dir: Path,
    *,
    expected: LevelsIdentity,
    artifacts_root: Path,
):
    ea = _ea()
    contained = ea._contain_path(artifact_dir, root=artifacts_root)
    if contained is None:
        return ea.ArtifactMiss(ea._MISS_PATH_ESCAPE, detail=str(artifact_dir))

    manifest_path = contained / ea.MANIFEST_FILENAME
    levels_path = contained / ea.LEVELS_PARQUET_FILENAME
    session_path = contained / ea.SESSION_LEVELS_PARQUET_FILENAME
    identity_path = contained / ea.IDENTITY_FILENAME
    settings_path = contained / ea.LEVELS_SETTINGS_FILENAME
    required = (manifest_path, levels_path, session_path, identity_path, settings_path)
    if not manifest_path.exists():
        return ea.ArtifactMiss(ea._MISS_MISSING, detail="manifest")
    if any(not path.exists() for path in required[1:]):
        return ea.ArtifactMiss(ea._MISS_INCOMPLETE, detail="missing required files")

    try:
        manifest = ea._read_json(manifest_path)
        stored_identity = LevelsIdentity.from_dict(ea._read_json(identity_path))
        levels_settings = ea._read_json(settings_path)
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        return ea.ArtifactMiss(ea._MISS_CORRUPT_MANIFEST, detail=str(exc))

    if stored_identity is None:
        return ea.ArtifactMiss(ea._MISS_CORRUPT_MANIFEST, detail="identity")
    if manifest.get("kind") != ea._LEVELS_KIND:
        return ea.ArtifactMiss(ea._MISS_CORRUPT_MANIFEST, detail="kind")
    schema_version = ea._try_int(manifest.get("artifact_schema_version", -1))
    if schema_version is None:
        return ea.ArtifactMiss(
            ea._MISS_CORRUPT_MANIFEST,
            detail=f"artifact_schema_version={manifest.get('artifact_schema_version')!r}",
        )
    if schema_version != LEVELS_ARTIFACT_SCHEMA_VERSION:
        return ea.ArtifactMiss(
            ea._MISS_SCHEMA_DRIFT,
            detail=f"artifact_schema_version={manifest.get('artifact_schema_version')}",
        )
    engine_version = ea._try_int(manifest.get("level_engine_version", -1))
    if engine_version is None:
        return ea.ArtifactMiss(
            ea._MISS_CORRUPT_MANIFEST,
            detail=f"level_engine_version={manifest.get('level_engine_version')!r}",
        )
    if engine_version != LEVEL_ENGINE_VERSION:
        return ea.ArtifactMiss(
            ea._MISS_ENGINE_INCOMPATIBLE,
            detail=f"level_engine_version={manifest.get('level_engine_version')}",
        )
    if stored_identity.level_engine_version != expected.level_engine_version:
        return ea.ArtifactMiss(
            ea._MISS_ENGINE_INCOMPATIBLE,
            detail="identity.level_engine_version",
        )
    if stored_identity.levels_settings_hash != expected.levels_settings_hash:
        return ea.ArtifactMiss(ea._MISS_IDENTITY_MISMATCH, detail="levels_settings_hash")
    if ea.data_artifact_key(stored_identity.data_identity) != ea.data_artifact_key(
        expected.data_identity
    ):
        return ea.ArtifactMiss(ea._MISS_IDENTITY_MISMATCH, detail="data_identity")

    settings_hash = compute_levels_settings_hash(levels_settings)
    if settings_hash != expected.levels_settings_hash:
        return ea.ArtifactMiss(ea._MISS_CONTENT_MISMATCH, detail="levels_settings_hash")

    try:
        levels = pd.read_parquet(levels_path)
        session_levels = pd.read_parquet(session_path)
    except Exception as exc:  # pragma: no cover
        return ea.ArtifactMiss(ea._MISS_INCOMPLETE, detail=f"parquet:{exc}")

    try:
        manifest = ea._touch_accessed_at(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        pass

    return ea.LevelsArtifact(
        identity=expected,
        levels=levels,
        session_levels=session_levels,
        levels_settings=levels_settings,
        manifest=manifest,
        path=contained,
    )


def stage_data_artifact(
    temp_dir: Path,
    *,
    identity: DataIdentity,
    data: pd.DataFrame,
    key: str,
    ingestion_meta: Mapping[str, Any] | None,
) -> None:
    ea = _ea()
    canonical = _canonicalize_dataframe(data)
    data_path = temp_dir / ea.DATA_PARQUET_FILENAME
    canonical.to_parquet(data_path, index=False)
    identity_payload = identity.to_dict()
    ea._write_json(temp_dir / ea.IDENTITY_FILENAME, identity_payload)
    ingestion = dict(ingestion_meta or {})
    ingestion.setdefault("rows", int(len(canonical)))
    ingestion.setdefault("columns", [str(column) for column in canonical.columns])
    ea._write_json(temp_dir / ea.INGESTION_META_FILENAME, ingestion)
    created_at = ea._utcnow_iso()
    manifest = {
        "kind": ea._DATA_KIND,
        "artifact_schema_version": ea.DATA_ARTIFACT_SCHEMA_VERSION,
        "identity_schema_version": RESEARCH_IDENTITY_SCHEMA_VERSION,
        "persistence_schema_version": identity.persistence_schema_version,
        "artifact_key": key,
        "identity": identity_payload,
        "files": {
            ea.DATA_PARQUET_FILENAME: {
                "sha256": ea._hash_file_bytes(data_path),
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
    ea._write_json(temp_dir / ea.MANIFEST_FILENAME, manifest)
    for path in (
        data_path,
        temp_dir / ea.IDENTITY_FILENAME,
        temp_dir / ea.INGESTION_META_FILENAME,
        temp_dir / ea.MANIFEST_FILENAME,
    ):
        ea._fsync_file(path)
    ea._fsync_dir(temp_dir)


def stage_levels_artifact(
    temp_dir: Path,
    *,
    identity: LevelsIdentity,
    levels: pd.DataFrame,
    session_levels: pd.DataFrame,
    settings: Mapping[str, Any],
    key: str,
) -> None:
    ea = _ea()
    levels_path = temp_dir / ea.LEVELS_PARQUET_FILENAME
    session_path = temp_dir / ea.SESSION_LEVELS_PARQUET_FILENAME
    _canonicalize_dataframe(levels).to_parquet(levels_path, index=False)
    _canonicalize_dataframe(session_levels).to_parquet(session_path, index=False)
    identity_payload = identity.to_dict()
    ea._write_json(temp_dir / ea.IDENTITY_FILENAME, identity_payload)
    ea._write_json(temp_dir / ea.LEVELS_SETTINGS_FILENAME, settings)
    created_at = ea._utcnow_iso()
    manifest = {
        "kind": ea._LEVELS_KIND,
        "artifact_schema_version": LEVELS_ARTIFACT_SCHEMA_VERSION,
        "level_engine_version": identity.level_engine_version,
        "identity_schema_version": RESEARCH_IDENTITY_SCHEMA_VERSION,
        "artifact_key": key,
        "data_artifact_key": ea.data_artifact_key(identity.data_identity),
        "levels_settings_hash": identity.levels_settings_hash,
        "identity": identity_payload,
        "files": {
            ea.LEVELS_PARQUET_FILENAME: {
                "sha256": ea._hash_file_bytes(levels_path),
                "rows": int(len(levels)),
            },
            ea.SESSION_LEVELS_PARQUET_FILENAME: {
                "sha256": ea._hash_file_bytes(session_path),
                "rows": int(len(session_levels)),
            },
        },
        "created_at": created_at,
        "accessed_at": created_at,
        "hit_count": 0,
        "producer": "execution_artifacts.write_levels_artifact",
        "app_version": __version__,
    }
    ea._write_json(temp_dir / ea.MANIFEST_FILENAME, manifest)
    for path in (
        levels_path,
        session_path,
        temp_dir / ea.IDENTITY_FILENAME,
        temp_dir / ea.LEVELS_SETTINGS_FILENAME,
        temp_dir / ea.MANIFEST_FILENAME,
    ):
        ea._fsync_file(path)
    ea._fsync_dir(temp_dir)


def validate_eviction_limits(
    *,
    max_entries: int | None,
    max_total_bytes: int | None,
    max_age_seconds: int | None,
) -> None:
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


def select_eviction_victims(
    records: list[dict[str, Any]],
    *,
    max_entries: int | None,
    max_total_bytes: int | None,
    max_age_seconds: int | None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    ea = _ea()
    ordered = list(records)
    ordered.sort(key=lambda item: str(item.get("accessed_at") or item.get("created_at") or ""))
    clock = now if now is not None else datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    to_delete: list[dict[str, Any]] = []
    if max_age_seconds is not None:
        for record in ordered:
            age_dt = ea._parse_iso_timestamp(record.get("accessed_at")) or ea._parse_iso_timestamp(
                record.get("created_at")
            )
            if age_dt is None:
                continue
            age = (clock - age_dt.astimezone(timezone.utc)).total_seconds()
            if age > max_age_seconds:
                to_delete.append(record)

    remaining = [record for record in ordered if record not in to_delete]
    if max_entries is not None and len(remaining) > max_entries:
        overflow = len(remaining) - max_entries
        to_delete.extend(remaining[:overflow])
        remaining = remaining[overflow:]

    if max_total_bytes is not None:
        total = sum(int(record.get("size_bytes") or 0) for record in remaining)
        idx = 0
        while total > max_total_bytes and idx < len(remaining):
            victim = remaining[idx]
            to_delete.append(victim)
            total -= int(victim.get("size_bytes") or 0)
            idx += 1
    return to_delete
