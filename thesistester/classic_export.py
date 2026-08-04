"""Classic workspace → public RunSpec export (CAI-4).

Streamlit-free helpers that turn canonical page-produced research state into a
validated draft RunSpec. Incomplete or inconsistent state yields explicit gaps;
missing parameters are never invented.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from thesistester.api import load_dataset, validate_run_spec
from thesistester.data.loader import DataValidationError, format_interval, validate_ohlcv
from thesistester.engine.exit_management import validate_exit_management_config
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.persistence.execution_artifacts import (
    ArtifactMiss,
    DataArtifact,
    read_verified_data_artifact,
)
from thesistester.research_identity import DataIdentity

CLASSIC_EXPORT_SCHEMA_VERSION = 1

# Additive dataset keys allowed on exported RunSpecs (CAI-4).
DATASET_ARTIFACT_KEY = "data_artifact_key"
DATASET_IDENTITY_KEY = "data_identity"

_SETUP_KEYS = (
    "name",
    "description",
    "instrument",
    "selected_levels",
    "tolerance_ticks",
    "min_confluences",
    "max_confluences",
    "naked_only",
    "naked_requirement",
    "trigger",
    "trigger_timeframe",
    "direction",
    "confluence_mode",
    "anchor_level",
    "confluence_rules",
    "min_valid_confluences",
    "trigger_params",
    "otf_filter",
)

_BACKTEST_REQUIRED = (
    "stop_loss_ticks",
    "take_profit_ticks",
    "commission_per_side",
    "slippage_ticks",
    "exposure_policy",
    "intrabar_model",
    "flat_by_session_close",
    "session_close_time",
    "session_timezone",
    "no_new_entries_after",
)


@dataclass(frozen=True, slots=True)
class ClassicExportGap:
    """One blocking clarification required before a classic export is executable."""

    code: str
    message: str
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "field": self.field}


def _gap(code: str, message: str, field: str | None = None) -> ClassicExportGap:
    return ClassicExportGap(code=code, message=message, field=field)


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _data_identity_from_state(state: Mapping[str, Any]) -> DataIdentity | ClassicExportGap:
    """Derive DataIdentity from classic page state.

    CAI-4 requires the canonical in-memory ``data`` frame. A stored
    ``data_identity`` mapping alone is not enough — without the frame, stale
    fingerprint checks cannot run and export would skip the page-produced
    dataset contract.
    """
    existing = DataIdentity.from_dict(
        state.get("data_identity") if isinstance(state.get("data_identity"), Mapping) else None
    )
    data = state.get("data")
    if not isinstance(data, pd.DataFrame):
        return _gap("missing_data", "Classic state requires a canonical data DataFrame.", "data")

    instrument = state.get("instrument")
    if not isinstance(instrument, str) or not instrument.strip():
        return _gap(
            "missing_instrument",
            "Classic state requires instrument provenance.",
            "instrument",
        )

    base_interval = state.get("base_interval")
    if base_interval is None:
        base_interval = format_interval(validate_ohlcv(data).inferred_interval)

    identity = DataIdentity.from_loaded_data(
        data,
        instrument=str(instrument),
        base_interval=str(base_interval) if base_interval is not None else None,
        source_timezone=(
            str(state["source_timezone"]) if state.get("source_timezone") is not None else None
        ),
        exchange_timezone=(
            str(state["exchange_timezone"]) if state.get("exchange_timezone") is not None else None
        ),
        format_profile=str(state.get("format_profile") or "canonical"),
    )
    if existing is not None and existing.data_content_hash != identity.data_content_hash:
        return _gap(
            "data_identity_mismatch",
            "Stored data_identity does not match the canonical data frame.",
            "data_identity",
        )
    dataset_id = state.get("dataset_id")
    if isinstance(dataset_id, str) and dataset_id and dataset_id != identity.dataset_id():
        return _gap(
            "dataset_id_mismatch",
            "dataset_id does not match the canonical data identity.",
            "dataset_id",
        )
    return identity


def _levels_section(state: Mapping[str, Any]) -> dict[str, Any] | ClassicExportGap:
    raw = _as_mapping(state.get("levels_settings"))
    if raw is None:
        return _gap(
            "missing_levels_settings",
            "Classic state requires levels_settings; defaults are not injected.",
            "levels_settings",
        )
    levels = {key: deepcopy(value) for key, value in raw.items() if key != "instrument"}
    unknown = sorted(set(levels) - set(DEFAULT_LEVELS_SETTINGS))
    if unknown:
        return _gap(
            "unknown_levels_keys",
            f"levels_settings contains unsupported keys: {unknown}.",
            "levels_settings",
        )
    fingerprint = _as_mapping(state.get("levels_data_fingerprint"))
    data = state.get("data")
    if fingerprint is not None:
        if not isinstance(data, pd.DataFrame):
            return _gap(
                "missing_data",
                "levels_data_fingerprint is present, but classic state has no "
                "canonical data DataFrame to verify against.",
                "data",
            )
        expected_rows = fingerprint.get("rows")
        if expected_rows is not None:
            try:
                expected_rows_int = int(expected_rows)
            except (TypeError, ValueError):
                return _gap(
                    "stale_levels",
                    "levels_data_fingerprint.rows is not a valid integer.",
                    "levels_data_fingerprint",
                )
            if expected_rows_int != len(data):
                return _gap(
                    "stale_levels",
                    "levels_data_fingerprint does not match the current data frame.",
                    "levels_data_fingerprint",
                )
        for key in ("instrument", "base_interval", "source_timezone", "exchange_timezone"):
            if key not in fingerprint or state.get(key) is None:
                continue
            if str(state.get(key)) != str(fingerprint.get(key)):
                return _gap(
                    "stale_levels",
                    f"levels_data_fingerprint.{key} does not match classic provenance.",
                    "levels_data_fingerprint",
                )
    return levels


def _setup_section(state: Mapping[str, Any]) -> dict[str, Any] | ClassicExportGap:
    raw = _as_mapping(state.get("last_signal_setup")) or _as_mapping(state.get("setup_config"))
    if raw is None:
        return _gap(
            "missing_setup",
            "Classic state requires setup_config or last_signal_setup.",
            "setup_config",
        )
    setup = {key: deepcopy(raw[key]) for key in _SETUP_KEYS if key in raw}
    required = ("name", "instrument", "selected_levels", "trigger", "tolerance_ticks")
    missing = [key for key in required if key not in setup]
    if missing:
        return _gap(
            "incomplete_setup",
            "Setup is missing required fields: " + ", ".join(missing) + ".",
            "setup_config",
        )
    instrument = state.get("instrument")
    if isinstance(instrument, str) and instrument and setup.get("instrument") != instrument:
        return _gap(
            "setup_instrument_mismatch",
            "setup.instrument must match classic instrument provenance.",
            "setup.instrument",
        )
    return setup


_MISSING = object()


def _widget_or_snapshot(
    state: Mapping[str, Any],
    *,
    widget_key: str,
    snapshot: Mapping[str, Any] | None,
    snapshot_key: str,
    empty_as_none: bool = False,
) -> Any:
    """Prefer live Backtest widget keys over post-run policy snapshots.

    Mixing live SL/TP widgets with stale cost/session snapshots produced RunSpecs
    that matched neither the current UI nor the last completed backtest. Widgets
    win when present; snapshots are fallback for restored/bundle state.
    """
    if widget_key in state:
        value = state[widget_key]
        if empty_as_none and value == "":
            return None
        return value
    if snapshot is not None and snapshot_key in snapshot:
        return snapshot[snapshot_key]
    return _MISSING


def _normalize_session_exit_fields(backtest: dict[str, Any]) -> None:
    """Match Backtest page persistence when session-flat is disabled."""
    if backtest.get("flat_by_session_close") is False:
        backtest["session_timezone"] = None
        backtest["no_new_entries_after"] = None


def _backtest_section(state: Mapping[str, Any]) -> dict[str, Any] | ClassicExportGap:
    explicit = _as_mapping(state.get("backtest_config"))
    if explicit is not None:
        backtest = deepcopy(dict(explicit))
    else:
        costs = _as_mapping(state.get("backtest_execution_costs"))
        session = _as_mapping(state.get("backtest_session_exit_policy"))
        intrabar = _as_mapping(state.get("backtest_intrabar_policy"))
        exit_mgmt = _as_mapping(state.get("backtest_exit_management_policy"))
        exposure = _as_mapping(state.get("exposure_policy"))

        backtest: dict[str, Any] = {}
        for dest, widget_key in (
            ("stop_loss_ticks", "backtest_sl_ticks"),
            ("take_profit_ticks", "backtest_tp_ticks"),
        ):
            value = _widget_or_snapshot(
                state, widget_key=widget_key, snapshot=None, snapshot_key=dest
            )
            if value is not _MISSING:
                backtest[dest] = value

        for dest, widget_key, snap_key in (
            ("commission_per_side", "backtest_commission_per_side", "commission_per_side"),
            ("slippage_ticks", "backtest_slippage_ticks", "slippage_ticks"),
        ):
            value = _widget_or_snapshot(
                state, widget_key=widget_key, snapshot=costs, snapshot_key=snap_key
            )
            if value is not _MISSING:
                backtest[dest] = value

        for dest, widget_key, snap_key in (
            ("exposure_policy", "backtest_exposure_policy", "exposure_policy"),
            ("cooldown_bars_after_exit", "backtest_cooldown_bars", "cooldown_bars_after_exit"),
        ):
            value = _widget_or_snapshot(
                state, widget_key=widget_key, snapshot=exposure, snapshot_key=snap_key
            )
            if value is not _MISSING:
                backtest[dest] = value

        value = _widget_or_snapshot(
            state,
            widget_key="backtest_intrabar_model",
            snapshot=intrabar,
            snapshot_key="intrabar_model",
        )
        if value is not _MISSING:
            backtest["intrabar_model"] = value

        for key in (
            "flat_by_session_close",
            "session_close_time",
            "session_timezone",
            "no_new_entries_after",
        ):
            value = _widget_or_snapshot(
                state,
                widget_key=f"backtest_{key}",
                snapshot=session,
                snapshot_key=key,
                empty_as_none=True,
            )
            if value is not _MISSING:
                backtest[key] = value

        # Exit management: live enable toggles override snapshot values.
        if "backtest_enable_be" in state:
            if state.get("backtest_enable_be") and "backtest_breakeven_after_r" in state:
                backtest["breakeven_after_r"] = state["backtest_breakeven_after_r"]
        elif exit_mgmt is not None and exit_mgmt.get("breakeven_after_r") is not None:
            backtest["breakeven_after_r"] = exit_mgmt["breakeven_after_r"]

        if "backtest_enable_trail" in state:
            if state.get("backtest_enable_trail"):
                if "backtest_trailing_after_r" in state:
                    backtest["trailing_after_r"] = state["backtest_trailing_after_r"]
                if "backtest_trailing_distance_ticks" in state:
                    backtest["trailing_distance_ticks"] = state["backtest_trailing_distance_ticks"]
        elif exit_mgmt is not None:
            for key in ("trailing_after_r", "trailing_distance_ticks"):
                if exit_mgmt.get(key) is not None:
                    backtest[key] = exit_mgmt[key]

        if "backtest_allow_same_bar" in state:
            backtest["allow_same_bar_exit"] = state["backtest_allow_same_bar"]
        if state.get("backtest_use_max_bars") is True and "backtest_max_bars" in state:
            backtest["max_holding_bars"] = state["backtest_max_bars"]
        elif state.get("backtest_use_max_bars") is False:
            backtest["max_holding_bars"] = None

    # Apply to explicit backtest_config and assembled widgets/snapshots alike.
    _normalize_session_exit_fields(backtest)

    missing = [key for key in _BACKTEST_REQUIRED if key not in backtest]
    if missing:
        return _gap(
            "incomplete_backtest",
            "Backtest execution policy is incomplete; missing: "
            + ", ".join(missing)
            + ". Defaults are not injected.",
            "backtest",
        )

    # Trailing fields must be paired (and BE/trail values valid) before export;
    # surface as a structured gap instead of failing only inside validate_run_spec.
    try:
        validate_exit_management_config(
            breakeven_after_r=backtest.get("breakeven_after_r"),
            trailing_after_r=backtest.get("trailing_after_r"),
            trailing_distance_ticks=backtest.get("trailing_distance_ticks"),
        )
    except ValueError as exc:
        return _gap(
            "incomplete_exit_management",
            str(exc),
            "backtest",
        )
    return backtest


def _resolve_source_path(
    state: Mapping[str, Any],
    *,
    source_path: str | Path | None,
) -> str | None:
    # Blank/whitespace source_path args must fall through to classic state keys.
    if source_path is not None:
        text = str(source_path).strip()
        if text:
            return text
    for key in ("dataset_source_path", "source_csv_path"):
        value = state.get(key)
        if isinstance(value, (str, Path)) and str(value).strip():
            return str(value).strip()
    return None


def _verify_source_path(
    path: str,
    *,
    identity: DataIdentity,
) -> ClassicExportGap | None:
    file_path = Path(path)
    if not file_path.is_file():
        return _gap(
            "source_path_missing",
            f"Source path does not exist: {path}",
            "dataset.path",
        )
    try:
        loaded = load_dataset(
            file_path,
            instrument=identity.instrument,
            source_timezone=identity.source_timezone,
            exchange_timezone=identity.exchange_timezone,
            format_profile=identity.format_profile,
        )
    except (OSError, ValueError, DataValidationError) as exc:
        return _gap(
            "source_path_unreadable",
            f"Unable to load source path for identity verification: {exc}",
            "dataset.path",
        )
    loaded_identity = DataIdentity.from_loaded_data(
        loaded,
        instrument=identity.instrument,
        base_interval=identity.base_interval,
        source_timezone=identity.source_timezone,
        exchange_timezone=identity.exchange_timezone,
        format_profile=identity.format_profile,
    )
    if loaded_identity.data_content_hash != identity.data_content_hash:
        return _gap(
            "source_path_identity_mismatch",
            "Source CSV content does not match the classic DataIdentity.",
            "dataset.path",
        )
    return None


def _dataset_section(
    state: Mapping[str, Any],
    *,
    identity: DataIdentity,
    source_path: str | None,
    store_root: str | Path | None,
) -> tuple[dict[str, Any] | None, list[ClassicExportGap]]:
    gaps: list[ClassicExportGap] = []
    dataset: dict[str, Any] = {
        "instrument": identity.instrument,
        "format_profile": identity.format_profile,
    }
    if identity.source_timezone is not None:
        dataset["source_timezone"] = identity.source_timezone
    if identity.exchange_timezone is not None:
        dataset["exchange_timezone"] = identity.exchange_timezone

    artifact = read_verified_data_artifact(identity, store_root=store_root)
    artifact_unusable: ArtifactMiss | None = None
    if isinstance(artifact, DataArtifact):
        dataset[DATASET_ARTIFACT_KEY] = artifact.artifact_key
        dataset[DATASET_IDENTITY_KEY] = identity.to_dict()
    elif isinstance(artifact, ArtifactMiss) and artifact.reason not in {"missing"}:
        # Corrupt/incomplete preferred artifacts must not block export when a
        # verified CSV source_path can satisfy CAI-4's required path fallback.
        artifact_unusable = artifact

    if source_path is None:
        if DATASET_ARTIFACT_KEY in dataset:
            gaps.append(
                _gap(
                    "missing_source_path",
                    "A verified data artifact is available, but dataset.path is still "
                    "required for an executable RunSpec. Provide dataset_source_path "
                    "or source_path.",
                    "dataset.path",
                )
            )
        else:
            if artifact_unusable is not None:
                gaps.append(
                    _gap(
                        "data_artifact_unusable",
                        "Preferred data artifact is present but not verified "
                        f"({artifact_unusable.reason}), and no source CSV path was provided.",
                        DATASET_ARTIFACT_KEY,
                    )
                )
            gaps.append(
                _gap(
                    "missing_source_reference",
                    "Classic export requires a verified data artifact or an explicit "
                    "source CSV path verified against DataIdentity.",
                    "dataset.path",
                )
            )
        return None, gaps

    path_gap = _verify_source_path(source_path, identity=identity)
    if path_gap is not None:
        gaps.append(path_gap)
        return None, gaps

    # Valid CSV path: export proceeds. Omit unusable artifact metadata rather
    # than failing the whole classic→RunSpec handoff.
    dataset["path"] = source_path
    dataset[DATASET_IDENTITY_KEY] = identity.to_dict()

    sub_path = state.get("subtimeframe_source_path")
    if isinstance(sub_path, (str, Path)) and str(sub_path).strip():
        dataset["subtimeframe_path"] = str(sub_path).strip()
        if state.get("subtimeframe_format_profile") is not None:
            dataset["subtimeframe_format_profile"] = str(state["subtimeframe_format_profile"])

    return dataset, gaps


def _optional_section_gaps(
    state: Mapping[str, Any],
    *,
    include_grid: bool,
    include_validation: bool,
    include_walk_forward: bool,
) -> list[ClassicExportGap]:
    """Blocking gaps for optional RunSpec sections requested at export time."""
    gaps: list[ClassicExportGap] = []
    if include_grid and _as_mapping(state.get("grid_config")) is None:
        gaps.append(
            _gap(
                "incomplete_grid",
                "include_grid requires explicit grid_config; defaults are not injected.",
                "grid",
            )
        )
    if include_validation and _as_mapping(state.get("validation_config")) is None:
        gaps.append(
            _gap(
                "incomplete_validation",
                "include_validation requires explicit validation_config; "
                "defaults are not injected.",
                "validation",
            )
        )
    if include_walk_forward and _as_mapping(state.get("walk_forward_config")) is None:
        gaps.append(
            _gap(
                "incomplete_walk_forward",
                "include_walk_forward requires explicit walk_forward_config; "
                "defaults are not injected.",
                "walk_forward",
            )
        )
    return gaps


def classic_state_export_gaps(
    state: Mapping[str, Any],
    *,
    name: str | None = None,
    source_path: str | Path | None = None,
    store_root: str | Path | None = None,
    include_grid: bool = False,
    include_validation: bool = False,
    include_walk_forward: bool = False,
) -> list[ClassicExportGap]:
    """Return blocking gaps for exporting classic page state to a RunSpec."""
    if not isinstance(state, Mapping):
        return [
            _gap("invalid_state", "Classic state must be a mapping.", None),
        ]

    gaps: list[ClassicExportGap] = []
    if name is not None and (not isinstance(name, str) or not name.strip()):
        gaps.append(_gap("invalid_name", "Run name must be a non-empty string.", "name"))

    identity_or_gap = _data_identity_from_state(state)
    if isinstance(identity_or_gap, ClassicExportGap):
        gaps.append(identity_or_gap)
        identity = None
    else:
        identity = identity_or_gap

    levels = _levels_section(state)
    if isinstance(levels, ClassicExportGap):
        gaps.append(levels)

    setup = _setup_section(state)
    if isinstance(setup, ClassicExportGap):
        gaps.append(setup)

    backtest = _backtest_section(state)
    if isinstance(backtest, ClassicExportGap):
        gaps.append(backtest)

    if identity is not None:
        resolved_path = _resolve_source_path(state, source_path=source_path)
        _dataset, dataset_gaps = _dataset_section(
            state,
            identity=identity,
            source_path=resolved_path,
            store_root=store_root,
        )
        gaps.extend(dataset_gaps)
    else:
        gaps.append(
            _gap(
                "missing_source_reference",
                "Classic export requires data identity before resolving a source reference.",
                "dataset.path",
            )
        )

    gaps.extend(
        _optional_section_gaps(
            state,
            include_grid=include_grid,
            include_validation=include_validation,
            include_walk_forward=include_walk_forward,
        )
    )
    return gaps


def classic_state_to_run_spec(
    state: Mapping[str, Any],
    *,
    name: str,
    source_path: str | Path | None = None,
    store_root: str | Path | None = None,
    include_grid: bool = False,
    include_validation: bool = False,
    include_walk_forward: bool = False,
) -> dict[str, Any]:
    """Export classic canonical state to one validated public RunSpec.

    Raises ``ValueError`` when export gaps remain. Never invents missing
    executable parameters.
    """
    gaps = classic_state_export_gaps(
        state,
        name=name,
        source_path=source_path,
        store_root=store_root,
        include_grid=include_grid,
        include_validation=include_validation,
        include_walk_forward=include_walk_forward,
    )
    if gaps:
        rendered = "; ".join(f"{gap.code}: {gap.message}" for gap in gaps)
        raise ValueError(f"Classic state is not exportable: {rendered}")

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Run name must be a non-empty string.")

    identity = _data_identity_from_state(state)
    assert isinstance(identity, DataIdentity)
    levels = _levels_section(state)
    setup = _setup_section(state)
    backtest = _backtest_section(state)
    assert not isinstance(levels, ClassicExportGap)
    assert not isinstance(setup, ClassicExportGap)
    assert not isinstance(backtest, ClassicExportGap)

    resolved_path = _resolve_source_path(state, source_path=source_path)
    dataset, dataset_gaps = _dataset_section(
        state,
        identity=identity,
        source_path=resolved_path,
        store_root=store_root,
    )
    if dataset is None or dataset_gaps:
        rendered = "; ".join(f"{gap.code}: {gap.message}" for gap in dataset_gaps)
        raise ValueError(f"Classic state is not exportable: {rendered}")

    spec: dict[str, Any] = {
        "name": name.strip(),
        "dataset": dataset,
        "levels": levels,
        "setup": setup,
        "backtest": backtest,
    }

    if include_grid:
        grid = _as_mapping(state.get("grid_config"))
        assert grid is not None
        spec["grid"] = deepcopy(dict(grid))
    if include_validation:
        validation = _as_mapping(state.get("validation_config"))
        assert validation is not None
        spec["validation"] = deepcopy(dict(validation))
    if include_walk_forward:
        walk_forward = _as_mapping(state.get("walk_forward_config"))
        assert walk_forward is not None
        spec["walk_forward"] = deepcopy(dict(walk_forward))

    validate_run_spec(spec)
    return spec


def format_classic_export_gaps(gaps: Sequence[ClassicExportGap]) -> list[dict[str, Any]]:
    """Return JSON-safe gap dictionaries for UI/clarification surfaces."""
    return [gap.to_dict() for gap in gaps]
