"""Canonical research identity and levels-config normalization (CAI-1).

Streamlit-free source of truth for deriving content-addressed data, levels, and
experiment identities shared by the headless API, CLI, classic pages, and the
Research Assistant. No production cache lookup occurs here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pandas as pd

from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.tick_vap import (
    LEVELS_TICK_IDENTITY_KEYS,
    TICK_SOURCE_NONE,
    attach_tick_identity,
    compute_table_path_source_id,
    compute_tick_source_id,
    resolve_tick_format_profile,
)
from thesistester.persistence.local_store import (
    LEVEL_ENGINE_VERSION,
    PERSISTENCE_SCHEMA_VERSION,
    _hash_dataframe,
    _stable_json_bytes,
    compute_dataset_id,
    compute_levels_settings_hash,
)

RESEARCH_IDENTITY_SCHEMA_VERSION = 1
LEVELS_ARTIFACT_SCHEMA_VERSION = 1

# Unordered list fields: order is not semantically meaningful for identity.
_LEVELS_SORT_KEYS = (
    "sma_lengths",
    "ema_lengths",
    "sma_timeframes",
    "ema_timeframes",
    "vwap_windows",
    "poc_windows",
    "pivot_timeframes",
)

EXECUTION_ORIGINS = frozenset({"api", "assistant", "cli", "classic", "study", "unknown"})

_IDENTITY_META_FILENAME = "research_identity.json"


def normalize_levels_config(
    config: Mapping[str, Any] | None,
    *,
    instrument: str,
) -> dict[str, Any]:
    """Merge product defaults, bind instrument, and canonicalize list fields.

    This is the API-path normalizer lifted for shared use. Unknown keys are
    rejected. Classic page sparse setdefaults remain a separate legacy UX path;
    identity derivation must call this function on equivalent inputs.
    """
    if not isinstance(instrument, str) or not instrument.strip():
        raise ValueError("instrument must be a non-empty string")
    raw = dict(config or {})
    # Classic page/bundle levels_settings and compute_levels outputs carry
    # instrument as bound metadata. Instrument is always taken from the
    # explicit parameter, so ignore any inbound copy before unknown-key checks.
    raw.pop("instrument", None)
    # Tick identity is injected after normalize; inbound copies must not fail
    # the product-key allowlist (classic page / artifact round-trip).
    for key in LEVELS_TICK_IDENTITY_KEYS:
        raw.pop(key, None)
    unknown = sorted(set(raw) - set(DEFAULT_LEVELS_SETTINGS))
    if unknown:
        raise ValueError(f"Unknown levels configuration keys: {unknown}")
    settings = {**DEFAULT_LEVELS_SETTINGS, **raw}
    settings["instrument"] = instrument
    for key in _LEVELS_SORT_KEYS:
        value = settings[key]
        settings[key] = sorted(list(value))
    return settings


def _tick_source_id_from_dataset(dataset: Mapping[str, Any] | None) -> str:
    """Resolve tick source id from dataset keys (explicit id, else hashed paths)."""
    if not dataset:
        return TICK_SOURCE_NONE
    explicit = dataset.get("tick_source_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    paths = dataset.get("tick_paths")
    if isinstance(paths, list) and any(str(item).strip() for item in paths):
        profile = resolve_tick_format_profile(dataset.get("tick_format_profile"))
        return compute_tick_source_id(paths, format_profile=profile)
    table_path = dataset.get("prior_profile_table_path")
    if isinstance(table_path, (str, Path)) and str(table_path).strip():
        resolved = Path(table_path)
        if resolved.is_file():
            return compute_table_path_source_id(resolved)
    return TICK_SOURCE_NONE


def compute_run_spec_hash(spec: Mapping[str, Any]) -> str:
    """Return a deterministic hash for an executable RunSpec mapping."""
    return hashlib.sha256(_stable_json_bytes(dict(spec))).hexdigest()


def _require_mapping(payload: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return payload


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


@dataclass(frozen=True, slots=True)
class DataIdentity:
    """Content identity for a canonical loaded dataset.

    ``dataset_id`` matches the existing ``compute_dataset_id`` contract and
    intentionally excludes ``format_profile``. ``format_profile`` is carried as
    additive metadata for future artifact keys (CAI-2+) without silently
    changing current dataset_id semantics.
    """

    instrument: str
    base_interval: str | None
    source_timezone: str | None
    exchange_timezone: str | None
    format_profile: str
    data_content_hash: str
    persistence_schema_version: int = PERSISTENCE_SCHEMA_VERSION
    identity_schema_version: int = RESEARCH_IDENTITY_SCHEMA_VERSION

    def dataset_id(self) -> str:
        """Legacy-compatible dataset id (excludes format_profile)."""
        # Recompute via the established helper using a 1-row stub is wrong;
        # mirror the payload composition of compute_dataset_id without needing
        # the DataFrame when the content hash is already known.
        hasher = hashlib.sha256()
        hasher.update(self.data_content_hash.encode("utf-8"))
        hasher.update(
            _stable_json_bytes(
                {
                    "instrument": self.instrument,
                    "base_interval": self.base_interval,
                    "source_timezone": self.source_timezone,
                    "exchange_timezone": self.exchange_timezone,
                }
            )
        )
        return hasher.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_schema_version": self.identity_schema_version,
            "persistence_schema_version": self.persistence_schema_version,
            "instrument": self.instrument,
            "base_interval": self.base_interval,
            "source_timezone": self.source_timezone,
            "exchange_timezone": self.exchange_timezone,
            "format_profile": self.format_profile,
            "data_content_hash": self.data_content_hash,
            "dataset_id": self.dataset_id(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> DataIdentity | None:
        if payload is None:
            return None
        data = _require_mapping(payload, label="data_identity")
        required = (
            "instrument",
            "data_content_hash",
        )
        if any(key not in data for key in required):
            return None
        return cls(
            instrument=str(data["instrument"]),
            base_interval=_optional_str(data.get("base_interval")),
            source_timezone=_optional_str(data.get("source_timezone")),
            exchange_timezone=_optional_str(data.get("exchange_timezone")),
            format_profile=str(data.get("format_profile") or "canonical"),
            data_content_hash=str(data["data_content_hash"]),
            persistence_schema_version=int(
                data.get("persistence_schema_version", PERSISTENCE_SCHEMA_VERSION)
            ),
            identity_schema_version=int(
                data.get("identity_schema_version", RESEARCH_IDENTITY_SCHEMA_VERSION)
            ),
        )

    @classmethod
    def from_loaded_data(
        cls,
        data: pd.DataFrame,
        *,
        instrument: str,
        base_interval: str | None,
        source_timezone: str | None,
        exchange_timezone: str | None,
        format_profile: str = "canonical",
    ) -> DataIdentity:
        return cls(
            instrument=str(instrument),
            base_interval=_optional_str(base_interval),
            source_timezone=_optional_str(source_timezone),
            exchange_timezone=_optional_str(exchange_timezone),
            format_profile=str(format_profile or "canonical"),
            data_content_hash=_hash_dataframe(data),
        )

    @classmethod
    def from_run_spec(
        cls,
        data: pd.DataFrame,
        *,
        dataset_config: Mapping[str, Any],
        base_interval: str | None,
        source_timezone: str | None,
        exchange_timezone: str | None,
    ) -> DataIdentity:
        config = _require_mapping(dataset_config, label="dataset")
        return cls.from_loaded_data(
            data,
            instrument=str(config.get("instrument", "ES")),
            base_interval=base_interval,
            source_timezone=source_timezone,
            exchange_timezone=exchange_timezone,
            format_profile=str(config.get("format_profile", "canonical")),
        )

    @classmethod
    def from_page_state(cls, state: Mapping[str, Any]) -> DataIdentity:
        mapping = _require_mapping(state, label="page state")
        data = mapping.get("data")
        if not isinstance(data, pd.DataFrame):
            raise ValueError("page state must include a data DataFrame")
        return cls.from_loaded_data(
            data,
            instrument=str(mapping.get("instrument", "ES")),
            base_interval=_optional_str(mapping.get("base_interval")),
            source_timezone=_optional_str(mapping.get("source_timezone")),
            exchange_timezone=_optional_str(mapping.get("exchange_timezone")),
            format_profile=str(mapping.get("format_profile", "canonical")),
        )

    @classmethod
    def from_bundle_meta(
        cls,
        dataset_meta: Mapping[str, Any] | None,
        *,
        data: pd.DataFrame | None = None,
        data_content_hash: str | None = None,
        identity_payload: Mapping[str, Any] | None = None,
    ) -> DataIdentity | None:
        """Construct from bundle identity payload or dataset meta + content hash."""
        if identity_payload is not None:
            nested = identity_payload.get("data_identity")
            if isinstance(nested, Mapping):
                return cls.from_dict(nested)
            if "data_content_hash" in identity_payload:
                return cls.from_dict(identity_payload)

        meta = dict(dataset_meta or {})
        content_hash = data_content_hash
        if content_hash is None and isinstance(data, pd.DataFrame):
            content_hash = _hash_dataframe(data)
        if content_hash is None or not meta.get("instrument"):
            return None
        return cls(
            instrument=str(meta["instrument"]),
            base_interval=_optional_str(meta.get("base_interval")),
            source_timezone=_optional_str(meta.get("source_timezone")),
            exchange_timezone=_optional_str(meta.get("exchange_timezone")),
            format_profile=str(meta.get("format_profile", "canonical")),
            data_content_hash=str(content_hash),
        )

    def matches_dataset_id(self, dataset_id: str) -> bool:
        return self.dataset_id() == dataset_id


@dataclass(frozen=True, slots=True)
class LevelsIdentity:
    """Identity for normalized levels settings over a DataIdentity."""

    data_identity: DataIdentity
    levels_settings_hash: str
    level_engine_version: int = LEVEL_ENGINE_VERSION
    artifact_schema_version: int = LEVELS_ARTIFACT_SCHEMA_VERSION
    identity_schema_version: int = RESEARCH_IDENTITY_SCHEMA_VERSION
    _levels_settings: Mapping[str, Any] | None = field(
        default=None,
        compare=False,
        hash=False,
        repr=False,
    )

    @property
    def levels_settings(self) -> Mapping[str, Any] | None:
        return self._levels_settings

    def to_dict(self) -> dict[str, Any]:
        # Settings bodies stay in levels_meta.json; identity carries the hash.
        return {
            "identity_schema_version": self.identity_schema_version,
            "level_engine_version": self.level_engine_version,
            "artifact_schema_version": self.artifact_schema_version,
            "levels_settings_hash": self.levels_settings_hash,
            "data_identity": self.data_identity.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> LevelsIdentity | None:
        if payload is None:
            return None
        data = _require_mapping(payload, label="levels_identity")
        data_identity = DataIdentity.from_dict(data.get("data_identity"))
        settings_hash = data.get("levels_settings_hash")
        if data_identity is None or not isinstance(settings_hash, str) or not settings_hash:
            return None
        settings = data.get("levels_settings")
        frozen_settings = None
        if isinstance(settings, Mapping):
            frozen_settings = MappingProxyType(dict(settings))
        return cls(
            data_identity=data_identity,
            levels_settings_hash=settings_hash,
            level_engine_version=int(data.get("level_engine_version", LEVEL_ENGINE_VERSION)),
            artifact_schema_version=int(
                data.get("artifact_schema_version", LEVELS_ARTIFACT_SCHEMA_VERSION)
            ),
            identity_schema_version=int(
                data.get("identity_schema_version", RESEARCH_IDENTITY_SCHEMA_VERSION)
            ),
            _levels_settings=frozen_settings,
        )

    @classmethod
    def from_normalized(
        cls,
        data_identity: DataIdentity,
        levels_settings: Mapping[str, Any],
        *,
        level_engine_version: int = LEVEL_ENGINE_VERSION,
        artifact_schema_version: int = LEVELS_ARTIFACT_SCHEMA_VERSION,
    ) -> LevelsIdentity:
        settings = dict(levels_settings)
        return cls(
            data_identity=data_identity,
            levels_settings_hash=compute_levels_settings_hash(settings),
            level_engine_version=level_engine_version,
            artifact_schema_version=artifact_schema_version,
            _levels_settings=MappingProxyType(settings),
        )

    @classmethod
    def from_config(
        cls,
        data_identity: DataIdentity,
        config: Mapping[str, Any] | None,
        *,
        instrument: str | None = None,
        tick_source_id: str | None = None,
    ) -> LevelsIdentity:
        resolved_instrument = instrument or data_identity.instrument
        inbound = None
        if isinstance(config, Mapping):
            raw_id = config.get("tick_source_id")
            if isinstance(raw_id, str) and raw_id.strip():
                inbound = raw_id
        normalized = attach_tick_identity(
            normalize_levels_config(config, instrument=resolved_instrument),
            tick_source_id=tick_source_id or inbound or TICK_SOURCE_NONE,
        )
        return cls.from_normalized(data_identity, normalized)

    @classmethod
    def from_run_spec(
        cls,
        data_identity: DataIdentity,
        spec: Mapping[str, Any],
    ) -> LevelsIdentity:
        run = _require_mapping(spec, label="run spec")
        dataset = run.get("dataset") if isinstance(run.get("dataset"), Mapping) else {}
        return cls.from_config(
            data_identity,
            run.get("levels"),
            tick_source_id=_tick_source_id_from_dataset(dataset),
        )

    @classmethod
    def from_page_state(cls, state: Mapping[str, Any]) -> LevelsIdentity:
        mapping = _require_mapping(state, label="page state")
        data_identity = DataIdentity.from_page_state(mapping)
        raw_settings = mapping.get("levels_settings")
        if not isinstance(raw_settings, Mapping):
            raise ValueError("page state must include levels_settings mapping")
        # Bind through the shared normalizer so identity ignores key/list order.
        return cls.from_config(data_identity, raw_settings, instrument=data_identity.instrument)

    @classmethod
    def from_bundle_meta(
        cls,
        identity_payload: Mapping[str, Any] | None,
        *,
        data_identity: DataIdentity | None = None,
        levels_settings: Mapping[str, Any] | None = None,
    ) -> LevelsIdentity | None:
        if identity_payload is not None:
            nested = identity_payload.get("levels_identity")
            if isinstance(nested, Mapping):
                return cls.from_dict(nested)
            if "levels_settings_hash" in identity_payload and "data_identity" in identity_payload:
                return cls.from_dict(identity_payload)
        if data_identity is None or levels_settings is None:
            return None
        return cls.from_config(data_identity, levels_settings)


@dataclass(frozen=True, slots=True)
class ExperimentIdentity:
    """Identity for one executable experiment over a LevelsIdentity."""

    levels_identity: LevelsIdentity
    run_spec_hash: str
    identity_schema_version: int = RESEARCH_IDENTITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_schema_version": self.identity_schema_version,
            "run_spec_hash": self.run_spec_hash,
            "levels_identity": self.levels_identity.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> ExperimentIdentity | None:
        if payload is None:
            return None
        data = _require_mapping(payload, label="experiment_identity")
        levels_identity = LevelsIdentity.from_dict(data.get("levels_identity"))
        run_spec_hash = data.get("run_spec_hash")
        if levels_identity is None or not isinstance(run_spec_hash, str) or not run_spec_hash:
            return None
        return cls(
            levels_identity=levels_identity,
            run_spec_hash=run_spec_hash,
            identity_schema_version=int(
                data.get("identity_schema_version", RESEARCH_IDENTITY_SCHEMA_VERSION)
            ),
        )

    @classmethod
    def from_run_spec(
        cls,
        levels_identity: LevelsIdentity,
        spec: Mapping[str, Any],
    ) -> ExperimentIdentity:
        return cls(
            levels_identity=levels_identity,
            run_spec_hash=compute_run_spec_hash(spec),
        )


def normalize_execution_origin(origin: str | None) -> str:
    """Return a known execution origin or ``unknown``."""
    if origin is None:
        return "unknown"
    text = str(origin).strip().lower()
    if text in EXECUTION_ORIGINS:
        return text
    return "unknown"


def build_identity_metadata(
    *,
    data_identity: DataIdentity | None = None,
    levels_identity: LevelsIdentity | None = None,
    experiment_identity: ExperimentIdentity | None = None,
) -> dict[str, Any]:
    """Serialize additive identity fields for bundle/run metadata.

    ``execution_origin`` is intentionally omitted: origin is run provenance and
    must not change canonical bundle hashes for equivalent RunSpecs.
    """
    payload: dict[str, Any] = {
        "identity_schema_version": RESEARCH_IDENTITY_SCHEMA_VERSION,
    }
    if data_identity is not None:
        payload["data_identity"] = data_identity.to_dict()
    if levels_identity is not None:
        payload["levels_identity"] = levels_identity.to_dict()
    if experiment_identity is not None:
        payload["experiment_identity"] = experiment_identity.to_dict()
    return payload


def assert_dataset_id_parity(
    data: pd.DataFrame,
    identity: DataIdentity,
) -> None:
    """Raise if DataIdentity.dataset_id diverges from compute_dataset_id."""
    expected = compute_dataset_id(
        data,
        instrument=identity.instrument,
        base_interval=identity.base_interval,
        source_timezone=identity.source_timezone,
        exchange_timezone=identity.exchange_timezone,
    )
    actual = identity.dataset_id()
    if actual != expected:
        raise AssertionError(
            f"DataIdentity.dataset_id mismatch: identity={actual} compute_dataset_id={expected}"
        )


def identity_meta_filename() -> str:
    """Return the optional research-bundle identity member name."""
    return _IDENTITY_META_FILENAME


# CAI-8 identity-relation codes (tests assert these, not display labels).
IDENTITY_RELATIONS: tuple[str, ...] = (
    "exact_match",
    "same_data_different_levels",
    "different_data",
    "identity_unavailable",
)

IDENTITY_RELATION_LABELS: dict[str, str] = {
    "exact_match": "exact match",
    "same_data_different_levels": "same data/different levels",
    "different_data": "different data",
    "identity_unavailable": "identity unavailable",
}


def classify_identity_relation(
    page_levels: LevelsIdentity | None,
    run_levels: LevelsIdentity | None,
    *,
    page_data: DataIdentity | None = None,
    run_data: DataIdentity | None = None,
) -> str:
    """Classify page vs run identity for CAI-8 badges.

    Uses immutable DataIdentity / LevelsIdentity equality only. Partial or
    missing identities are ``identity_unavailable`` — never a soft match.
    """
    page_data_id = page_data or (page_levels.data_identity if page_levels is not None else None)
    run_data_id = run_data or (run_levels.data_identity if run_levels is not None else None)

    if page_data_id is None or run_data_id is None:
        return "identity_unavailable"
    if page_data_id.dataset_id() != run_data_id.dataset_id():
        return "different_data"
    # Same dataset_id but full DataIdentity mismatch (e.g. format_profile) is
    # unavailable rather than a false exact/same-levels claim.
    if page_data_id != run_data_id:
        return "identity_unavailable"
    if page_levels is None or run_levels is None:
        return "identity_unavailable"
    if page_levels == run_levels:
        return "exact_match"
    if page_levels.data_identity != run_levels.data_identity:
        return "identity_unavailable"
    return "same_data_different_levels"


def try_page_levels_identity(state: Mapping[str, Any]) -> LevelsIdentity | None:
    """Best-effort LevelsIdentity from classic page state; None when unavailable."""
    try:
        return LevelsIdentity.from_page_state(state)
    except (TypeError, ValueError):
        return None


def try_page_data_identity(state: Mapping[str, Any]) -> DataIdentity | None:
    """Best-effort DataIdentity from classic page state; None when unavailable."""
    try:
        return DataIdentity.from_page_state(state)
    except (TypeError, ValueError):
        return None


def identities_from_payload(
    payload: Mapping[str, Any] | None,
) -> tuple[DataIdentity | None, LevelsIdentity | None]:
    """Extract data/levels identities from provenance or research_identity.json."""
    if not isinstance(payload, Mapping):
        return None, None
    levels = LevelsIdentity.from_dict(
        payload.get("levels_identity")
        if isinstance(payload.get("levels_identity"), Mapping)
        else None
    )
    data = DataIdentity.from_dict(
        payload.get("data_identity") if isinstance(payload.get("data_identity"), Mapping) else None
    )
    if data is None and levels is not None:
        data = levels.data_identity
    return data, levels
