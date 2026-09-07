"""APOC source/version provenance for study artifacts (AP3).

Sidecar metadata only. It does not enter ``study_identity_hash``. Historical
``study.expansion.json`` files and research ZIPs are not rewritten; a missing
sidecar is inferred as legacy typical-price.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from thesistester.levels.apoc_candidates import TICK_LAST_VOLUME_V1, TYPICAL_MVP_V1

APOC_OBJECT_LEGACY_TYPICAL = "legacy_typical_price"
APOC_OBJECT_TICK_LAST_VOLUME = "tick_last_volume"

RECORDED_INFERRED = "inferred"
RECORDED_EXPLICIT = "explicit"
RECORDED_INFERRED_HISTORICAL = "inferred_historical"

WAVE7_HISTORICAL_PROVENANCE: dict[str, str] = {
    "apoc_profile_source": TYPICAL_MVP_V1,
    "apoc_algorithm_version": TYPICAL_MVP_V1,
    "apoc_object": APOC_OBJECT_LEGACY_TYPICAL,
    "recorded": RECORDED_INFERRED_HISTORICAL,
}


def is_wave7_study_file(filename: str) -> bool:
    """True for Program B Wave 7 YAML names (Run 1 and Run 2 file stems)."""
    return "w7_apoc" in str(filename)


def apoc_provenance_from_levels(levels: Mapping[str, Any] | None) -> dict[str, str]:
    """Derive APOC provenance from written ``study.levels``.

    Omitted ``apoc_profile_source`` is implicit ``typical_mvp_v1`` (legacy
    typical-price). An explicit key is recorded as explicit, including the
    AP1/AP2 selected Quantower source ``tick_last_volume_v1``.
    """
    raw = None if levels is None else levels.get("apoc_profile_source")
    if raw is None:
        return {
            "apoc_profile_source": TYPICAL_MVP_V1,
            "apoc_algorithm_version": TYPICAL_MVP_V1,
            "apoc_object": APOC_OBJECT_LEGACY_TYPICAL,
            "recorded": RECORDED_INFERRED,
        }
    source = str(raw)
    if source == TICK_LAST_VOLUME_V1:
        return {
            "apoc_profile_source": source,
            "apoc_algorithm_version": source,
            "apoc_object": APOC_OBJECT_TICK_LAST_VOLUME,
            "recorded": RECORDED_EXPLICIT,
        }
    if source == TYPICAL_MVP_V1:
        return {
            "apoc_profile_source": source,
            "apoc_algorithm_version": source,
            "apoc_object": APOC_OBJECT_LEGACY_TYPICAL,
            "recorded": RECORDED_EXPLICIT,
        }
    return {
        "apoc_profile_source": source,
        "apoc_algorithm_version": source,
        "apoc_object": "unknown",
        "recorded": RECORDED_EXPLICIT,
    }


def should_write_apoc_provenance(levels: Mapping[str, Any] | None) -> bool:
    """Write the expansion sidecar when the spec names APOC enablement or source.

    Golden expansion fixtures omit both keys and stay byte-stable. Program B
    Wave 7 writes ``apoc_enabled: true`` and therefore records inferred typical.
    """
    if not isinstance(levels, Mapping) or not levels:
        return False
    if "apoc_profile_source" in levels:
        return True
    return levels.get("apoc_enabled") is True


def read_apoc_provenance(
    expansion: Mapping[str, Any] | None = None,
    *,
    levels: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Return recorded provenance, or infer typical from levels / a missing sidecar."""
    if expansion is not None and "apoc_provenance" in expansion:
        raw = expansion["apoc_provenance"]
        if isinstance(raw, Mapping):
            return {
                "apoc_profile_source": str(raw.get("apoc_profile_source") or TYPICAL_MVP_V1),
                "apoc_algorithm_version": str(
                    raw.get("apoc_algorithm_version") or TYPICAL_MVP_V1
                ),
                "apoc_object": str(raw.get("apoc_object") or APOC_OBJECT_LEGACY_TYPICAL),
                "recorded": str(raw.get("recorded") or RECORDED_INFERRED),
            }
    return apoc_provenance_from_levels(levels or {})
