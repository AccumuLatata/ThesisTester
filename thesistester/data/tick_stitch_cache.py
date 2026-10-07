"""Cross-study parent-table cache for stitch-on studies (§4.5).

Keyed by plan digest + tick-file digest set + bins + burst + every other
input that changes the two parent tables. Lives under
``THESISTESTER_STORE_DIR/tick_stitch_parent`` unless
``THESISTESTER_TICK_STITCH_CACHE_DIR`` is set. Never called when
``tick_stitch_plan`` is absent.

Tick identity: a complete ``tick_stitch_plan.sha256`` sidecar (farm lock)
contributes the listed per-file digests for plan filenames. Hashing the
sidecar blob is not an identity — an incomplete sidecar, or a comment-only
edit, must not silently pin stale tables. Missing or incomplete sidecars
fall through to content hashes of the unique tick files. Hits never open
those CSVs; the sidecar (or a prior miss that hashed them) is the lock.

Installs are copies, never hardlinks: a later study must not be able to
mutate the shared cache through a dest path. Writes use unique temps +
``os.replace``.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

from thesistester.config import INSTRUMENTS
from thesistester.data.tick_stitch import (
    CLIP_POLICY_TOKEN,
    HOURLY_GUARD_POLICY_TOKEN,
    X1_FILL_POLICY_TOKEN,
)
from thesistester.levels.apoc_tick import APOC_A_PERIOD_POLICY_ID
from thesistester.levels.tick_vap import SESSION_CUT_POLICY_ID
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION, get_store_root

CACHE_ENV_VAR = "THESISTESTER_TICK_STITCH_CACHE_DIR"
CACHE_STORE_DIRNAME = "tick_stitch_parent"
STITCH_PARENT_CACHE_VERSION = 2
PRIOR_CACHE_NAME = "study.prior_profile.parquet"
APOC_CACHE_NAME = "study.apoc_tick_profile.parquet"
MANIFEST_NAME = "manifest.json"
SIDECAR_NAME = "tick_stitch_plan.sha256"
_MANIFEST_REQUIRED = (
    "tick_source_id",
    "apoc_tick_source_id",
    "data_quality",
    "prior_sha256",
    "apoc_sha256",
)
_SHA256_HEX_LEN = 64


def get_tick_stitch_parent_cache_root() -> Path:
    """Shared parent-table cache root.

    ``THESISTESTER_TICK_STITCH_CACHE_DIR`` wins when set. Otherwise
    ``{THESISTESTER_STORE_DIR}/tick_stitch_parent``.
    """
    raw = os.environ.get(CACHE_ENV_VAR, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return get_store_root() / CACHE_STORE_DIRNAME


def file_sha256(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parquet_hashes_match(
    prior: Path,
    apoc: Path,
    expected_prior: object,
    expected_apoc: object,
) -> bool:
    """True when both parquets exist and match the expected hex digests."""
    if not isinstance(expected_prior, str) or not isinstance(expected_apoc, str):
        return False
    if len(expected_prior) != _SHA256_HEX_LEN or len(expected_apoc) != _SHA256_HEX_LEN:
        return False
    if not prior.is_file() or not apoc.is_file():
        return False
    return expected_prior == file_sha256(prior) and expected_apoc == file_sha256(apoc)


def _plan_filenames(plan_path: Path) -> list[str]:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, Mapping):
        rows = list(payload.get("plan") or payload.get("segments") or [])
    else:
        rows = []
    names: list[str] = []
    for row in rows:
        if isinstance(row, Mapping) and row.get("filename"):
            names.append(str(row["filename"]))
    return sorted(set(names))


def _parse_sidecar_digests(sidecar: Path) -> dict[str, str] | None:
    """Parse a ``sha256sum`` sidecar. None if missing, empty, or malformed."""
    try:
        text = sidecar.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "  " not in raw_line:
            return None
        digest, name = raw_line.split("  ", 1)
        digest = digest.strip()
        name = name.strip()
        if len(digest) != _SHA256_HEX_LEN or not name:
            return None
        try:
            int(digest, 16)
        except ValueError:
            return None
        out[name] = digest
    return out or None


def _tick_digest_token(plan_path: Path, root: Path) -> str:
    """Tick-file identity for the cache key.

    A complete sidecar is the farm lock (listed per-file digests for every
    plan filename). That avoids hashing 34 GiB on every study to compute
    the key. An incomplete or malformed sidecar is not trusted — fall
    through to actual file bytes. Hashing the sidecar blob itself is not
    used: comments / extra lines must not change identity, and a sidecar
    that omits a plan file must not hide that file's content change.
    """
    names = _plan_filenames(plan_path)
    sidecar = plan_path.with_name(SIDECAR_NAME)
    if sidecar.is_file():
        listed = _parse_sidecar_digests(sidecar)
        if listed is not None and all(name in listed for name in names):
            hasher = sha256()
            for name in names:
                hasher.update(name.encode("utf-8"))
                hasher.update(b"\0")
                hasher.update(listed[name].encode("utf-8"))
                hasher.update(b"\0")
            return f"sidecar:{hasher.hexdigest()}"
    hasher = sha256()
    for name in names:
        path = root / name
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        if path.is_file():
            hasher.update(file_sha256(path).encode("utf-8"))
        hasher.update(b"\0")
    return f"files:{hasher.hexdigest()}"


def parent_cache_key(
    *,
    plan_path: Path,
    root: Path,
    bars_path: Path,
    instrument: str,
    burst: bool,
    value_area_pct: float,
    day_bins: int,
    week_bins: int,
    month_bins: int,
    source_timezone: str,
    format_profile: str,
) -> str:
    inst = INSTRUMENTS[instrument]
    payload = {
        "cache_version": STITCH_PARENT_CACHE_VERSION,
        "level_engine_version": LEVEL_ENGINE_VERSION,
        "plan_sha256": file_sha256(plan_path),
        "tick_digests": _tick_digest_token(plan_path, root),
        # Raw 15s CSV bytes (dataset.path). Same digest algorithm as
        # source_content_hash; clip / X1 read this file via load_ohlcv.
        "bars_sha256": file_sha256(bars_path),
        "instrument": instrument,
        "tick_size": float(inst.tick_size),
        "exchange_tz": inst.exchange_tz,
        "rth_start": inst.rth_start,
        "rth_end": inst.rth_end,
        "eth_start": inst.eth_start,
        "source_timezone": source_timezone,
        "target_timezone": "UTC",
        "format_profile": format_profile,
        "value_area_pct": float(value_area_pct),
        "day_bins": int(day_bins),
        "week_bins": int(week_bins),
        "month_bins": int(month_bins),
        "tick_stitch_x1_burst_included": bool(burst),
        "x1_fill_policy": X1_FILL_POLICY_TOKEN,
        "clip_policy": CLIP_POLICY_TOKEN,
        "hourly_guard_policy": HOURLY_GUARD_POLICY_TOKEN,
        "apoc_a_period_policy": APOC_A_PERIOD_POLICY_ID,
        "session_cut_policy": SESSION_CUT_POLICY_ID,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(blob).hexdigest()


def _entry_dir(key: str) -> Path:
    return get_tick_stitch_parent_cache_root() / key


def _atomic_copy(src: Path, dest: Path, *, mode: int) -> None:
    """Copy *src* onto *dest* via a unique temp + ``os.replace``. Never link."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.",
        suffix=".tmp",
        dir=str(dest.parent),
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle, Path(src).open("rb") as incoming:
            shutil.copyfileobj(incoming, handle, 1024 * 1024)
        tmp.chmod(mode)
        os.replace(tmp, dest)
    except Exception:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        raise


def _atomic_write_text(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.",
        suffix=".tmp",
        dir=str(dest.parent),
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, dest)
    except Exception:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        raise


def _manifest_usable(manifest: object) -> dict[str, Any] | None:
    if not isinstance(manifest, dict):
        return None
    for key in _MANIFEST_REQUIRED:
        if key not in manifest:
            return None
    if not isinstance(manifest.get("data_quality"), dict):
        return None
    if not isinstance(manifest.get("tick_source_id"), str) or not manifest["tick_source_id"]:
        return None
    if not isinstance(manifest.get("apoc_tick_source_id"), str) or not manifest[
        "apoc_tick_source_id"
    ]:
        return None
    return manifest


def try_load_parent_cache(key: str, dest_dir: Path) -> dict[str, Any] | None:
    """Copy cached tables into *dest_dir*. None on miss or hash mismatch.

    Dest copies are writable (0644). Cache files stay independent inodes.
    """
    entry = _entry_dir(key)
    manifest_path = entry / MANIFEST_NAME
    prior_src = entry / PRIOR_CACHE_NAME
    apoc_src = entry / APOC_CACHE_NAME
    if not (manifest_path.is_file() and prior_src.is_file() and apoc_src.is_file()):
        return None
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    manifest = _manifest_usable(loaded)
    if manifest is None:
        return None
    if not parquet_hashes_match(
        prior_src,
        apoc_src,
        manifest.get("prior_sha256"),
        manifest.get("apoc_sha256"),
    ):
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    _atomic_copy(prior_src, dest_dir / PRIOR_CACHE_NAME, mode=0o644)
    _atomic_copy(apoc_src, dest_dir / APOC_CACHE_NAME, mode=0o644)
    return dict(manifest)


def store_parent_cache(
    key: str,
    *,
    prior_path: Path,
    apoc_path: Path,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    """Atomically write tables + manifest. Safe if two processes race.

    Cache parquets are 0444 copies (not hardlinks) so a later dest write
    cannot truncate the shared inode. Manifest is written last. A reader
    that sees new parquets + an old manifest fails hash-verify and misses.
    """
    entry = _entry_dir(key)
    entry.mkdir(parents=True, exist_ok=True)
    _atomic_copy(prior_path, entry / PRIOR_CACHE_NAME, mode=0o444)
    _atomic_copy(apoc_path, entry / APOC_CACHE_NAME, mode=0o444)
    manifest = {
        **dict(fields),
        "cache_key": key,
        "prior_sha256": file_sha256(prior_path),
        "apoc_sha256": file_sha256(apoc_path),
        "cache_version": STITCH_PARENT_CACHE_VERSION,
    }
    _atomic_write_text(
        entry / MANIFEST_NAME,
        json.dumps(manifest, indent=2, sort_keys=True),
    )
    return manifest
