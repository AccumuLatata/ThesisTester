"""Closed tag → engine-token map (TJ6). Data in ``tag_map.yaml``, not code.

Unknown tags are ``unmapped`` and kept. Exact-tag rows win before qualifier
stripping. Does not call ``compute_all_levels``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from thesistester.journal.schema import (
    TAG_CLASS_CONFIRM,
    TAG_CLASS_CONTEXT,
    TAG_CLASS_LEVEL,
    TAG_CLASS_UNMAPPED,
    JournalIngestError,
)

_MAP_PATH: Final[Path] = Path(__file__).resolve().parent / "tag_map.yaml"
_LEVEL_CLASSES: Final[frozenset[str]] = frozenset(
    {TAG_CLASS_LEVEL, TAG_CLASS_CONFIRM, TAG_CLASS_CONTEXT, TAG_CLASS_UNMAPPED}
)


@dataclass(frozen=True)
class TagMapping:
    """One resolved journal tag."""

    raw: str
    token: str | None
    tag_class: str
    qualifier: str | None = None


def load_tag_map(path: str | Path | None = None) -> dict[str, object]:
    """Load the frozen YAML map. ``path`` is keyword-only via the default file."""
    source = Path(_MAP_PATH if path is None else path)
    if not source.is_file():
        raise JournalIngestError(f"tag map not found: {source}")
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise JournalIngestError(f"tag map is not valid YAML: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise JournalIngestError("tag map must be a mapping")
    return dict(payload)


def resolve_tag(tag: str, *, tag_map: Mapping[str, object] | None = None) -> TagMapping:
    """Resolve one tag. Exact rows win; then qualifier suffixes are stripped.

    Qualifier strip applies to ``level`` and ``confirm`` exact rows. Context
    tags keep class ``context``. ``_RTH`` remaps only via the exact ``pdH_RTH``
    row; other ``*_RTH`` tags keep the base token.
    """
    raw = str(tag).strip()
    if not raw:
        return TagMapping(raw=tag, token=None, tag_class=TAG_CLASS_UNMAPPED)
    payload = tag_map if tag_map is not None else load_tag_map()
    exact = payload.get("exact")
    if not isinstance(exact, Mapping):
        raise JournalIngestError("tag map missing exact table")
    context = {str(item) for item in (payload.get("context") or ())}
    qualifiers = [str(item) for item in (payload.get("qualifiers") or ())]
    hit = _exact_row(raw, exact)
    if hit is not None:
        return hit
    if raw in context:
        return TagMapping(raw=raw, token=None, tag_class=TAG_CLASS_CONTEXT)
    for suffix in sorted(qualifiers, key=len, reverse=True):
        if raw.endswith(suffix) and len(raw) > len(suffix):
            base = raw[: -len(suffix)]
            mapped = _exact_row(base, exact)
            if mapped is not None and mapped.tag_class in {TAG_CLASS_LEVEL, TAG_CLASS_CONFIRM}:
                return TagMapping(
                    raw=raw,
                    token=mapped.token,
                    tag_class=mapped.tag_class,
                    qualifier=suffix,
                )
            if base in context:
                return TagMapping(
                    raw=raw, token=None, tag_class=TAG_CLASS_CONTEXT, qualifier=suffix
                )
    return TagMapping(raw=raw, token=None, tag_class=TAG_CLASS_UNMAPPED)


def mapped_engine_tokens(*, tag_map: Mapping[str, object] | None = None) -> frozenset[str]:
    """Engine tokens named by the map (excludes ``unmapped`` / context)."""
    payload = tag_map if tag_map is not None else load_tag_map()
    exact = payload.get("exact")
    if not isinstance(exact, Mapping):
        raise JournalIngestError("tag map missing exact table")
    tokens: set[str] = set()
    for row in exact.values():
        if not isinstance(row, Mapping):
            continue
        token = row.get("token")
        tag_class = str(row.get("class") or "")
        if token and tag_class in {TAG_CLASS_LEVEL, TAG_CLASS_CONFIRM}:
            tokens.add(str(token))
    return frozenset(tokens)


def _exact_row(tag: str, exact: Mapping[str, object]) -> TagMapping | None:
    row = exact.get(tag)
    if not isinstance(row, Mapping):
        return None
    tag_class = str(row.get("class") or "")
    if tag_class not in _LEVEL_CLASSES:
        raise JournalIngestError(f"tag map class {tag_class!r} is not closed")
    token_raw = row.get("token")
    token = None if token_raw in (None, "", "null") else str(token_raw)
    if tag_class == TAG_CLASS_UNMAPPED:
        token = None
    return TagMapping(raw=tag, token=token, tag_class=tag_class)
