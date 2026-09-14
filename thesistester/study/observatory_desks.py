"""SO4 Observatory desks — query-only persistence under the store (C-24 / QI-07-07).

Writes only ``{store}/study_observatory/desks/*.json``. Never writes study dirs.
Does not import Streamlit, Plotly, ``execute``, or ``cli_study``.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from thesistester.persistence.local_store import get_store_root
from thesistester.study.observatory_support import (
    DESK_FACET_COLUMNS,
    DESK_LENS_MODES,
    DESK_SCHEMA_VERSION,
    DESK_STORE_DIRNAME,
    DESK_STORE_NAMESPACE,
    SORT_ALLOW_LIST,
    _DESK_ID_RE,
    ObservatoryError,
    _is_na,
    canonical_facet_value,
)


@dataclass(frozen=True)
class ObservatoryDesk:
    """Saved Observatory query. Not a fact table and not a validated edge."""

    id: str
    name: str
    facets: Mapping[str, tuple[Any, ...]]
    cohort_lock: bool
    break_comparability: bool
    active_cohort: str | None
    lens: str
    sort_column: str
    schema_version: int = DESK_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "id": self.id,
            "name": self.name,
            "facets": {key: list(values) for key, values in self.facets.items()},
            "cohort_lock": bool(self.cohort_lock),
            "break_comparability": bool(self.break_comparability),
            "active_cohort": self.active_cohort,
            "lens": self.lens,
            "sort_column": self.sort_column,
        }


def observatory_desks_dir(*, store_root: Path | None = None) -> Path:
    """``{store}/study_observatory/desks``. Never a study ``output_dir``."""
    root = Path(store_root).resolve() if store_root is not None else get_store_root()
    return root / DESK_STORE_NAMESPACE / DESK_STORE_DIRNAME


def observatory_desk_query_state(desk: ObservatoryDesk) -> dict[str, Any]:
    """Map a desk onto query fields the page restores. Not a fact table."""
    facets = {column: list(desk.facets.get(column, ())) for column in DESK_FACET_COLUMNS}
    return {
        "saved_desk_id": desk.id,
        "name": desk.name,
        "facets": facets,
        "cohort_lock": bool(desk.cohort_lock),
        "break_comparability": bool(desk.break_comparability),
        "active_cohort": desk.active_cohort,
        "lens": desk.lens,
        "sort_column": desk.sort_column,
    }


def list_observatory_desks(
    *,
    store_root: Path | None = None,
) -> tuple[tuple[ObservatoryDesk, ...], tuple[str, ...]]:
    """Load schema-v1 desks. Missing dir is empty. Corrupt / v2 files ignored."""
    directory = observatory_desks_dir(store_root=store_root)
    if not directory.is_dir():
        return (), ()
    try:
        paths = sorted(directory.glob("*.json"), key=lambda item: item.name)
    except OSError:
        return (), ()
    desks: list[ObservatoryDesk] = []
    ignored: list[str] = []
    for path in paths:
        try:
            desk = parse_observatory_desk(path)
        except (OSError, TypeError, ValueError, KeyError):
            ignored.append(path.name)
            continue
        if desk is None:
            ignored.append(path.name)
            continue
        desks.append(desk)
    desks.sort(key=lambda item: (item.name.lower(), item.id))
    return tuple(desks), tuple(ignored)


def save_observatory_desk(
    *,
    name: str,
    facets: Mapping[str, Sequence[Any]] | None = None,
    cohort_lock: bool = True,
    break_comparability: bool = False,
    active_cohort: str | None = None,
    lens: str = "auto",
    sort_column: str = "expectancy_r",
    desk_id: str | None = None,
    store_root: Path | None = None,
) -> ObservatoryDesk:
    """Persist query state only. Creates the store sidecar on first save."""
    directory = observatory_desks_dir(store_root=store_root)
    ident = _resolve_save_desk_id(desk_id, name)
    desk = ObservatoryDesk(
        id=ident,
        name=_normalize_desk_name(name),
        facets=_normalize_desk_facets(facets),
        cohort_lock=bool(cohort_lock),
        break_comparability=bool(break_comparability),
        active_cohort=_normalize_optional_token(active_cohort),
        lens=_normalize_desk_lens(lens),
        sort_column=_normalize_desk_sort(sort_column),
        schema_version=DESK_SCHEMA_VERSION,
    )
    _atomic_write_desk_json(directory / f"{desk.id}.json", desk.to_payload())
    return desk


def delete_observatory_desk(desk_id: str, *, store_root: Path | None = None) -> bool:
    """Delete one desk JSON. Unknown / unsafe ids are a no-op."""
    ident = _normalize_desk_id(desk_id)
    if ident is None:
        return False
    directory = observatory_desks_dir(store_root=store_root)
    path = directory / f"{ident}.json"
    try:
        resolved_dir = directory.resolve()
        resolved = path.resolve()
    except OSError:
        return False
    if resolved.parent != resolved_dir or not resolved.is_file():
        return False
    resolved.unlink()
    return True


def parse_observatory_desk(path: Path) -> ObservatoryDesk | None:
    """Return a v1 desk or ``None`` when the file is corrupt / unknown schema.

    Must not raise — a bad sidecar cannot fail Observatory page load.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return observatory_desk_from_payload(payload, file_stem=path.stem)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ObservatoryError,
        TypeError,
        ValueError,
    ):
        return None


def observatory_desk_from_payload(
    payload: Any,
    *,
    file_stem: str | None = None,
) -> ObservatoryDesk | None:
    """Parse an in-memory desk payload. Filename stem must match ``id`` when given."""
    if not isinstance(payload, Mapping):
        return None
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != DESK_SCHEMA_VERSION:
        return None
    ident = _normalize_desk_id(payload.get("id") or file_stem)
    if ident is None:
        return None
    if file_stem is not None and file_stem != ident:
        return None
    raw_name = payload.get("name")
    if raw_name is not None and not isinstance(raw_name, str):
        return None
    facets = payload.get("facets")
    if facets is not None and not isinstance(facets, Mapping):
        return None
    try:
        return ObservatoryDesk(
            id=ident,
            name=_normalize_desk_name(raw_name or ident),
            facets=_normalize_desk_facets(facets if isinstance(facets, Mapping) else None),
            cohort_lock=_coerce_desk_bool(payload.get("cohort_lock", True), default=True),
            break_comparability=_coerce_desk_bool(
                payload.get("break_comparability", False),
                default=False,
            ),
            active_cohort=_normalize_optional_token(payload.get("active_cohort")),
            lens=_normalize_desk_lens(payload.get("lens")),
            sort_column=_normalize_desk_sort(payload.get("sort_column")),
            schema_version=DESK_SCHEMA_VERSION,
        )
    except (ObservatoryError, TypeError, ValueError):
        return None


def _normalize_desk_name(name: Any) -> str:
    text = str(name or "").strip()
    return text[:80] if text else "Desk"


def _new_desk_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_desk_name(name).lower()).strip("-")
    token = slug[:40] or "desk"
    return f"{token}-{uuid.uuid4().hex[:8]}"


def _resolve_save_desk_id(desk_id: Any, name: str) -> str:
    if desk_id is None or (isinstance(desk_id, str) and not desk_id.strip()):
        return _new_desk_id(name)
    if not isinstance(desk_id, str):
        raise ObservatoryError("saved-desk id must be a string")
    ident = _normalize_desk_id(desk_id)
    if ident is None:
        raise ObservatoryError(f"Invalid saved-desk id: {desk_id!r}")
    return ident


def _normalize_desk_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    if not _DESK_ID_RE.match(token):
        return None
    return token


def _normalize_optional_token(value: Any) -> str | None:
    if value is None or _is_na(value):
        return None
    if not isinstance(value, str):
        raise ObservatoryError("desk token field must be a string or null")
    text = value.strip()
    if not text or text in {"<NA>", "nan", "None", "null"}:
        return None
    return text


def _coerce_desk_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ObservatoryError("desk boolean field must be true, false, or omitted")


def _normalize_desk_lens(value: Any) -> str:
    if value is None:
        return "auto"
    if not isinstance(value, str):
        raise ObservatoryError("desk lens must be a string")
    token = value.strip().lower()
    return token if token in DESK_LENS_MODES else "auto"


def _normalize_desk_sort(value: Any) -> str:
    if value is None:
        return "expectancy_r"
    if not isinstance(value, str):
        raise ObservatoryError("desk sort_column must be a string")
    token = value.strip()
    return token if token in SORT_ALLOW_LIST else "expectancy_r"


def _as_facet_sequence(raw: Any) -> Sequence[Any]:
    if isinstance(raw, (str, bytes, bytearray)) or not isinstance(raw, Sequence):
        raise ObservatoryError("desk facet values must be a list")
    return raw


def _normalize_desk_facets(
    facets: Mapping[str, Sequence[Any]] | None,
) -> MappingProxyType:
    cleaned: dict[str, tuple[Any, ...]] = {}
    if not facets:
        return MappingProxyType(cleaned)
    if not isinstance(facets, Mapping):
        raise ObservatoryError("desk facets must be an object")
    for column in DESK_FACET_COLUMNS:
        raw = facets.get(column)
        if raw is None:
            continue
        values: list[Any] = []
        seen: set[Any] = set()
        for item in _as_facet_sequence(raw):
            canonical = canonical_facet_value(item)
            if canonical is None or canonical in seen:
                continue
            seen.add(canonical)
            values.append(canonical)
        if values:
            cleaned[column] = tuple(values)
    return MappingProxyType(cleaned)


def _atomic_write_desk_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write ``<id>.json`` inside the desks dir. Never follows a symlink out."""
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    resolved_dir = directory.resolve()
    resolved = (resolved_dir / path.name).resolve()
    if resolved.parent != resolved_dir:
        raise ObservatoryError("saved-desk path escaped the desks directory")
    tmp = resolved.with_name(f".{resolved.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(resolved)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
