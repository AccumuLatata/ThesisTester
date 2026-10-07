"""Cross-study parent-table cache for stitch-on studies (§4.5).

Keyed by plan digest + tick-file digest set + bins + burst + every other
input that changes the two parent tables. Lives under
``THESISTESTER_STORE_DIR/tick_stitch_parent`` unless
``THESISTESTER_TICK_STITCH_CACHE_DIR`` is set. Never called when
``tick_stitch_plan`` is absent.
"""

from __future__ import annotations

import json
import os
import shutil
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
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION, get_store_root

CACHE_ENV_VAR = "THESISTESTER_TICK_STITCH_CACHE_DIR"
CACHE_STORE_DIRNAME = "tick_stitch_parent"
STITCH_PARENT_CACHE_VERSION = 1
PRIOR_CACHE_NAME = "study.prior_profile.parquet"
APOC_CACHE_NAME = "study.apoc_tick_profile.parquet"
MANIFEST_NAME = "manifest.json"
SIDECAR_NAME = "tick_stitch_plan.sha256"


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


def _tick_digest_token(plan_path: Path, root: Path) -> str:
    sidecar = plan_path.with_name(SIDECAR_NAME)
    if sidecar.is_file():
        return f"sidecar:{file_sha256(sidecar)}"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    names: list[str] = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, Mapping):
        rows = list(payload.get("plan") or payload.get("segments") or [])
    else:
        rows = []
    for row in rows:
        if isinstance(row, Mapping) and row.get("filename"):
            names.append(str(row["filename"]))
    hasher = sha256()
    for name in sorted(set(names)):
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
        "bars_sha256": file_sha256(bars_path),
        "instrument": instrument,
        "exchange_tz": inst.exchange_tz,
        "rth_start": inst.rth_start,
        "rth_end": inst.rth_end,
        "eth_start": inst.eth_start,
        "source_timezone": source_timezone,
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
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(blob).hexdigest()


def _entry_dir(key: str) -> Path:
    return get_tick_stitch_parent_cache_root() / key


def _install_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    try:
        os.link(src, tmp)
    except OSError:
        shutil.copy2(src, tmp)
    os.replace(tmp, dest)


def try_load_parent_cache(key: str, dest_dir: Path) -> dict[str, Any] | None:
    """Copy or link cached tables into *dest_dir*. None on miss or hash mismatch."""
    entry = _entry_dir(key)
    manifest_path = entry / MANIFEST_NAME
    prior_src = entry / PRIOR_CACHE_NAME
    apoc_src = entry / APOC_CACHE_NAME
    if not (manifest_path.is_file() and prior_src.is_file() and apoc_src.is_file()):
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    expected_prior = manifest.get("prior_sha256")
    expected_apoc = manifest.get("apoc_sha256")
    if expected_prior != file_sha256(prior_src) or expected_apoc != file_sha256(apoc_src):
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    _install_file(prior_src, dest_dir / PRIOR_CACHE_NAME)
    _install_file(apoc_src, dest_dir / APOC_CACHE_NAME)
    return dict(manifest)


def store_parent_cache(
    key: str,
    *,
    prior_path: Path,
    apoc_path: Path,
    fields: Mapping[str, Any],
) -> None:
    """Atomically write tables + manifest. Safe if two processes race."""
    entry = _entry_dir(key)
    entry.mkdir(parents=True, exist_ok=True)
    _install_file(prior_path, entry / PRIOR_CACHE_NAME)
    _install_file(apoc_path, entry / APOC_CACHE_NAME)
    manifest = {
        **dict(fields),
        "cache_key": key,
        "prior_sha256": file_sha256(prior_path),
        "apoc_sha256": file_sha256(apoc_path),
        "cache_version": STITCH_PARENT_CACHE_VERSION,
    }
    tmp = entry / f".{MANIFEST_NAME}.tmp"
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, entry / MANIFEST_NAME)
