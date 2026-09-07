"""APOC source/version provenance for study artifacts (AP3).

Sidecar metadata only. It does not enter ``study_identity_hash``. Historical
``study.expansion.json`` files and research ZIPs are not rewritten; a missing
sidecar is inferred as legacy typical-price.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from thesistester.levels.apoc_tick import (
    APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
    APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
)

APOC_OBJECT_LEGACY_TYPICAL = "legacy_typical_price"
APOC_OBJECT_TICK_LAST_VOLUME = "tick_last_volume"
APOC_OBJECT_UNKNOWN = "unknown"

RECORDED_INFERRED = "inferred"
RECORDED_EXPLICIT = "explicit"
RECORDED_INFERRED_HISTORICAL = "inferred_historical"

# Program B Wave 7 file stems (Run 1 and Run 2 share filenames).
WAVE7_STUDY_STEMS: frozenset[str] = frozenset(
    {
        "progB_w7_apoc_ma",
        "progB_w7_apoc_rvwap",
        "progB_w7_apoc_pivot",
    }
)

_RECORDED_VALUES: frozenset[str] = frozenset(
    {RECORDED_INFERRED, RECORDED_EXPLICIT, RECORDED_INFERRED_HISTORICAL}
)

WAVE7_HISTORICAL_PROVENANCE: dict[str, str] = {
    "apoc_profile_source": APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
    "apoc_algorithm_version": APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
    "apoc_object": APOC_OBJECT_LEGACY_TYPICAL,
    "recorded": RECORDED_INFERRED_HISTORICAL,
}


def is_wave7_study_file(filename: str) -> bool:
    """True for the three Program B Wave 7 YAML stems (Run 1 and Run 2)."""
    return Path(filename).stem in WAVE7_STUDY_STEMS


def _explicit_source(levels: Mapping[str, Any] | None) -> str | None:
    """Return a non-blank ``apoc_profile_source``, or None when omitted/empty."""
    if levels is None or "apoc_profile_source" not in levels:
        return None
    raw = levels.get("apoc_profile_source")
    if raw is None:
        return None
    source = str(raw).strip()
    return source or None


def _inferred_typical() -> dict[str, str]:
    return {
        "apoc_profile_source": APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
        "apoc_algorithm_version": APOC_PROFILE_SOURCE_TYPICAL_MVP_V1,
        "apoc_object": APOC_OBJECT_LEGACY_TYPICAL,
        "recorded": RECORDED_INFERRED,
    }


def apoc_provenance_from_levels(levels: Mapping[str, Any] | None) -> dict[str, str]:
    """Derive APOC provenance from written ``study.levels``.

    Omitted ``apoc_profile_source`` is implicit ``typical_mvp_v1`` (legacy
    typical-price). An explicit key is recorded as explicit, including the
    AP1/AP2 selected Quantower source ``tick_last_volume_v1``.
    """
    source = _explicit_source(levels)
    if source is None:
        return _inferred_typical()
    if source == APOC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1:
        return {
            "apoc_profile_source": source,
            "apoc_algorithm_version": source,
            "apoc_object": APOC_OBJECT_TICK_LAST_VOLUME,
            "recorded": RECORDED_EXPLICIT,
        }
    if source == APOC_PROFILE_SOURCE_TYPICAL_MVP_V1:
        return {
            "apoc_profile_source": source,
            "apoc_algorithm_version": source,
            "apoc_object": APOC_OBJECT_LEGACY_TYPICAL,
            "recorded": RECORDED_EXPLICIT,
        }
    return {
        "apoc_profile_source": source,
        "apoc_algorithm_version": source,
        "apoc_object": APOC_OBJECT_UNKNOWN,
        "recorded": RECORDED_EXPLICIT,
    }


def should_write_apoc_provenance(levels: Mapping[str, Any] | None) -> bool:
    """Write the expansion sidecar when APOC is enabled or a source is named.

    Golden expansion fixtures omit both keys and stay byte-stable. Program B
    Wave 7 writes ``apoc_enabled: true`` and therefore records inferred typical.
    Explicit ``apoc_enabled: false`` is a no-op and must not claim an APOC
    object, even if a source key is also present.
    """
    if not isinstance(levels, Mapping) or not levels:
        return False
    if levels.get("apoc_enabled") is False:
        return False
    if _explicit_source(levels) is not None:
        return True
    return levels.get("apoc_enabled") is True


def read_apoc_provenance(
    expansion: Mapping[str, Any] | None = None,
    *,
    levels: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Return recorded provenance, or infer typical from levels / a missing sidecar.

    A present sidecar must be a mapping. Object/algorithm are derived from the
    recorded source so a tick sidecar cannot be relabeled typical by a missing
    ``apoc_object``. Source/object contradictions and unknown ``recorded``
    tokens fail closed.
    """
    if expansion is not None and "apoc_provenance" in expansion:
        raw = expansion["apoc_provenance"]
        if not isinstance(raw, Mapping):
            raise ValueError("apoc_provenance must be a mapping")
        source = raw.get("apoc_profile_source")
        if source is None or (isinstance(source, str) and not source.strip()):
            derived = apoc_provenance_from_levels(levels or {})
        else:
            derived = apoc_provenance_from_levels({"apoc_profile_source": source})
        object_raw = raw.get("apoc_object")
        if object_raw not in (None, "") and str(object_raw) != derived["apoc_object"]:
            raise ValueError("apoc_provenance.apoc_object does not match apoc_profile_source")
        algo_raw = raw.get("apoc_algorithm_version")
        if algo_raw not in (None, "") and str(algo_raw) != derived["apoc_algorithm_version"]:
            raise ValueError(
                "apoc_provenance.apoc_algorithm_version does not match apoc_profile_source"
            )
        recorded = raw.get("recorded")
        if recorded is None or recorded == "":
            return derived
        recorded_text = str(recorded)
        if recorded_text not in _RECORDED_VALUES:
            raise ValueError(f"apoc_provenance.recorded is not a known token: {recorded!r}")
        out = dict(derived)
        out["recorded"] = recorded_text
        return out
    return apoc_provenance_from_levels(levels or {})
