"""Phase 4 — Signals page.

Detects confluence zones, flags naked levels, and generates candidate
entry signals from the levels computed on the Levels page.
"""

from __future__ import annotations

import json
import math

import pandas as pd
import streamlit as st

from thesistester.app_state import bootstrap_active_saved_dataset
from thesistester.classic_context import render_classic_thesis_chrome
from thesistester.config import INSTRUMENTS
from thesistester.engine import (
    detect_anchor_confluence_zones,
    detect_confluence_zones,
    flag_naked_levels,
    generate_signals,
)
from thesistester.persistence import (
    compute_levels_settings_hash,
    compute_otf_config_hash,
    compute_signal_settings_hash,
    delete_signal_run,
    find_matching_signal_run,
    list_saved_setups,
    list_saved_signal_runs,
    load_setup,
    load_signal_run,
    save_signal_run,
)
from thesistester.setup import (
    DEFAULT_TRIGGER_TIMEFRAME,
    TRIGGER_TIMEFRAME_CHOICES,
    VALID_TRIGGER_TIMEFRAMES,
    available_level_columns,
    default_selected_levels,
    get_effective_otf_filter_config,
    normalize_otf_filter_config,
    normalize_trigger_timeframe,
    validate_setup_config,
)
from thesistester.engine.otf import OTF_ALGORITHM_VERSION
from thesistester.visualization import (
    buffered_rows_window,
    build_signals_chart,
    clip_by_time_window,
    recent_rows_window,
    timestamp_bounds,
)

st.title("🎯 Signals")
st.caption(
    "Detect confluence zones and generate candidate entry signals. "
    "OTF admission is applied later in Backtest, Grid, and Walk-forward — not on this page."
)
bootstrap_active_saved_dataset()
render_classic_thesis_chrome(
    page_key="signals",
    dataset_id=st.session_state.get("dataset_id"),
)


ANCHOR_DIAGNOSTIC_COLUMNS = [
    "timestamp",
    "bar_index",
    "anchor_level",
    "anchor_price",
    "valid_confluence_count",
    "level_names",
    "level_prices",
    "rule_results",
]

CONFLUENCE_MODE_OPTIONS = {
    "Global cluster": "global_cluster",
    "Anchor-based rules": "anchor_rules",
}
TRIGGER_TIMEFRAME_LABELS = {
    "Base/current timeframe": "base",
    "1 minute": "1min",
    "5 minutes": "5min",
    "15 minutes": "15min",
}
TRIGGER_TIMEFRAME_DISPLAY = {value: key for key, value in TRIGGER_TIMEFRAME_LABELS.items()}
SETUP_SOURCE_MANUAL = "Configure manually"
SETUP_SOURCE_ACTIVE = "Use active setup"
SETUP_SOURCE_LIBRARY = "Use saved setup from library"

_RULE_AUDIT_COLUMNS = [
    "zone_row",
    "timestamp",
    "bar_index",
    "anchor_level",
    "anchor_price",
    "rule_level",
    "rule_price",
    "distance_ticks",
    "tolerance_ticks",
    "required",
    "valid",
    "reason",
]

_OTF_INVALID_SAVE_BLOCKER = (
    "OTF configuration is invalid and signal identity cannot be established. "
    "Update the setup in Setup Builder before saving signals."
)

_IDENTITY_STATUS_TRUSTED = "trusted"
_IDENTITY_STATUS_INVALID = "invalid"
_IDENTITY_STATUS_UNAVAILABLE = "unavailable"
_SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY = "signal_artifact_identity_status"
_SIGNAL_ARTIFACT_IDENTITY_ERROR_KEY = "signal_artifact_identity_error"
_OTF_INVALID_ARTIFACT_BLOCKER = (
    "These signal artifacts do not have a trusted settings identity and cannot be saved. "
    "Regenerate signals using a valid setup."
)
_SIGNAL_CONTROLS_CHANGED_WARNING = (
    "Signal controls changed after these signals were generated. "
    "Please regenerate signals before saving."
)


def _widget_key_part(value: object) -> str:
    """Sanitize a value for widget keys by replacing non-alphanumerics with underscores."""
    return "".join(ch if ch.isalnum() else "_" for ch in str(value))


def _parse_anchor_rule_results(zones: pd.DataFrame) -> pd.DataFrame:
    """Parse ``rule_results`` JSON column into a flat per-rule DataFrame."""
    if zones.empty or "rule_results" not in zones.columns:
        return pd.DataFrame(columns=_RULE_AUDIT_COLUMNS)

    rows: list[dict] = []
    for i, zone_row in zones.iterrows():
        raw = zone_row.get("rule_results")
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, list):
            continue
        for result in parsed:
            if not isinstance(result, dict):
                continue
            rows.append(
                {
                    "zone_row": i,
                    "timestamp": zone_row.get("timestamp"),
                    "bar_index": zone_row.get("bar_index"),
                    "anchor_level": zone_row.get("anchor_level"),
                    "anchor_price": zone_row.get("anchor_price"),
                    "rule_level": result.get("level"),
                    "rule_price": result.get("price"),
                    "distance_ticks": result.get("distance_ticks"),
                    "tolerance_ticks": result.get("tolerance_ticks"),
                    "required": result.get("required"),
                    "valid": result.get("valid"),
                    "reason": result.get("reason"),
                }
            )

    if not rows:
        return pd.DataFrame(columns=_RULE_AUDIT_COLUMNS)
    return pd.DataFrame(rows)[_RULE_AUDIT_COLUMNS]


def _render_anchor_diagnostics(zones: pd.DataFrame) -> None:
    """Render anchor-zone summary metrics and per-rule audit table."""
    required_cols = {"anchor_level", "anchor_price", "valid_confluence_count", "rule_results"}
    if zones.empty or not required_cols.issubset(zones.columns):
        return

    st.subheader("Anchor confluence diagnostics")

    # ── Summary metrics ───────────────────────────────────────────────────────
    required_valid_count: int | None = None
    if "required_valid" in zones.columns:
        required_valid_count = int(zones["required_valid"].sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("Anchor zones", len(zones))
    col2.metric("Avg valid confluences", f"{zones['valid_confluence_count'].mean():.2f}")
    if required_valid_count is not None:
        col3.metric("Required-valid zones", f"{required_valid_count}/{len(zones)}")

    # ── Zone summary table ────────────────────────────────────────────────────
    summary_cols = [
        "timestamp",
        "bar_index",
        "anchor_level",
        "anchor_price",
        "valid_confluence_count",
        "level_count",
        "zone_low",
        "zone_high",
        "zone_mid",
        "level_names",
    ]
    st.subheader("Anchor zone summary")
    st.dataframe(
        zones[[c for c in summary_cols if c in zones.columns]].head(500),
        width="stretch",
        hide_index=True,
    )

    # ── Per-rule audit table ──────────────────────────────────────────────────
    rule_audit = _parse_anchor_rule_results(zones)
    if not rule_audit.empty:
        st.subheader("Per-rule confluence audit")
        show_invalid_only = st.checkbox("Show invalid rules only", value=False)
        if show_invalid_only:
            rule_audit = rule_audit[rule_audit["valid"] == False]  # noqa: E712
        display_audit_cols = [
            "timestamp",
            "bar_index",
            "anchor_level",
            "rule_level",
            "rule_price",
            "distance_ticks",
            "tolerance_ticks",
            "required",
            "valid",
            "reason",
        ]
        st.dataframe(
            rule_audit[[c for c in display_audit_cols if c in rule_audit.columns]].head(1000),
            width="stretch",
            hide_index=True,
        )


def _safe_float(value: object, default: float) -> float:
    """Return ``float(value)`` or *default* if conversion fails or yields NaN."""
    if value is None:
        return default
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return default if pd.isna(result) else result


def _safe_int(value: object, default: int) -> int:
    """Return ``int(value)`` or *default* if conversion fails or yields non-finite."""
    if value is None:
        return default
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if pd.isna(result) or math.isinf(result):
        return default
    return int(result)


def _safe_bool(value: object, default: bool = False) -> bool:
    """Return a bool from *value* without raising; fall back to *default*."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _safe_dict(value: object) -> dict:
    """Return *value* if it is a dict, otherwise ``{}``."""
    return value if isinstance(value, dict) else {}


def _safe_list(value: object) -> list:
    """Return *value* if it is a list, otherwise ``[]``."""
    return value if isinstance(value, list) else []


def _normalize_3c_params(params: object) -> dict:
    if not isinstance(params, dict):
        params = {}
    return {
        # arrival_tolerance_ticks may appear in legacy configs, but its value is
        # intentionally ignored and normalized to 0.0.
        "arrival_tolerance_ticks": 0.0,
        "entry_retrace_ticks": _safe_float(params.get("entry_retrace_ticks", 4.0), default=4.0),
        "max_entry_wait_bars_after_reversal": _safe_int(
            params.get("max_entry_wait_bars_after_reversal", 5), default=5
        ),
        "_source_mode": str(params.get("_source_mode", "global_cluster")),
    }


def _saved_setup_caption(config: dict) -> str:
    confluence_mode = str(config.get("confluence_mode", "global_cluster"))
    trigger_timeframe = normalize_trigger_timeframe(config.get("trigger_timeframe"))
    otf_config = get_effective_otf_filter_config(config)
    otf_caption = (
        f"OTF=enabled({','.join(otf_config['timeframes'])}; min={otf_config['minimum_consecutive_bars']})"
        if otf_config["enabled"]
        else "OTF=disabled"
    )
    if confluence_mode == "anchor_rules":
        return (
            f"Mode=anchor_rules • Anchor={config.get('anchor_level') or '-'} • "
            f"Rules={len(_safe_list(config.get('confluence_rules')))} • "
            f"Min valid={_safe_int(config.get('min_valid_confluences'), 1)} • "
            f"Trigger TF={trigger_timeframe} • {otf_caption}"
        )
    return (
        f"Trigger={config.get('trigger')} • Direction={config.get('direction')} • "
        f"Confluences={config.get('min_confluences')}–{config.get('max_confluences')} • "
        f"Trigger TF={trigger_timeframe} • {otf_caption}"
    )


def _dataset_relation_label(setup_dataset_id: object, current_dataset_id: str | None) -> str:
    if setup_dataset_id in (None, ""):
        return "global/no dataset"
    if (
        isinstance(current_dataset_id, str)
        and current_dataset_id
        and setup_dataset_id == current_dataset_id
    ):
        return "current dataset"
    return "other dataset"


def _prioritize_saved_setups(
    setups: list[dict],
    *,
    current_dataset_id: str | None,
) -> list[dict]:
    def _bucket(item: dict) -> int:
        return {
            "current dataset": 0,
            "global/no dataset": 1,
            "other dataset": 2,
        }[_dataset_relation_label(item.get("dataset_id"), current_dataset_id)]

    return sorted(setups, key=_bucket)


def _saved_setup_option_label(meta: dict, current_dataset_id: str | None) -> str:
    updated_raw = meta.get("updated_at") or meta.get("created_at") or ""
    updated = str(updated_raw)[:10] if updated_raw else "unknown date"
    setup_config = meta.get("setup_config")
    if not isinstance(setup_config, dict):
        setup_config = {}
    return (
        f"{meta.get('name', 'Untitled setup')} · {meta.get('instrument', '—')} · "
        f"{updated} · mode={setup_config.get('confluence_mode', 'global_cluster')} · "
        f"trigger={setup_config.get('trigger', 'touch')} · "
        f"direction={setup_config.get('direction', 'both')} · "
        f"{_dataset_relation_label(meta.get('dataset_id'), current_dataset_id)}"
    )


def _filter_saved_setups_for_signals(
    setups: list[dict],
    *,
    current_dataset_id: str | None,
    include_other_datasets: bool,
) -> list[dict]:
    prioritized = _prioritize_saved_setups(setups, current_dataset_id=current_dataset_id)
    if include_other_datasets:
        return prioritized
    return [
        item
        for item in prioritized
        if _dataset_relation_label(item.get("dataset_id"), current_dataset_id) != "other dataset"
    ]


def _saved_setup_compatibility_issues(
    config: dict, available_columns: list[str]
) -> dict[str, list[str]]:
    confluence_mode = str(config.get("confluence_mode", "global_cluster"))
    if confluence_mode == "anchor_rules":
        missing_anchor = []
        anchor_level = config.get("anchor_level")
        if isinstance(anchor_level, str) and anchor_level and anchor_level not in available_columns:
            missing_anchor.append(anchor_level)
        missing_rules: list[str] = []
        for rule in _safe_list(config.get("confluence_rules")):
            if not isinstance(rule, dict):
                continue
            level = str(rule.get("level", "")).strip()
            if level and level not in available_columns:
                missing_rules.append(level)
        return {
            "selected_levels": [],
            "anchor_level": sorted(set(missing_anchor)),
            "confluence_rules": sorted(set(missing_rules)),
        }

    selected_levels = config.get("selected_levels", [])
    if not isinstance(selected_levels, list):
        selected_levels = []
    missing_selected = [
        str(level) for level in selected_levels if str(level) not in available_columns
    ]
    return {
        "selected_levels": sorted(set(missing_selected)),
        "anchor_level": [],
        "confluence_rules": [],
    }


def _saved_setup_generation_blockers(config: dict, available_columns: list[str]) -> list[str]:
    """Return user-facing blocker strings for a saved or active setup.

    Combines structural validation (``validate_setup_config``) with
    dataset-level compatibility checks (``_saved_setup_compatibility_issues``).
    """
    blockers: list[str] = []

    for error in validate_setup_config(config):
        blockers.append(
            f"Saved setup configuration error: {error} "
            "Switch setup source or update the setup in Setup Builder."
        )

    compatibility_issues = _saved_setup_compatibility_issues(config, available_columns)
    if compatibility_issues["selected_levels"]:
        blockers.append(
            "Saved setup references unavailable selected levels for global cluster mode: "
            + ", ".join(compatibility_issues["selected_levels"])
            + ". Switch setup source or update the setup in Setup Builder."
        )
    if compatibility_issues["anchor_level"]:
        blockers.append(
            "Saved setup anchor level is unavailable in current levels: "
            + ", ".join(compatibility_issues["anchor_level"])
            + ". Switch setup source or update the setup in Setup Builder."
        )
    if compatibility_issues["confluence_rules"]:
        blockers.append(
            "Saved setup confluence-rule levels are unavailable in current levels: "
            + ", ".join(compatibility_issues["confluence_rules"])
            + ". Switch setup source or update the setup in Setup Builder."
        )

    return blockers


def _extract_setup_snapshot_from_signal_run(meta: dict) -> dict | None:
    signal_settings = meta.get("signal_settings")
    if isinstance(signal_settings, dict):
        setup_snapshot = signal_settings.get("setup_snapshot")
        if isinstance(setup_snapshot, dict) and setup_snapshot:
            return dict(setup_snapshot)
    fallback = meta.get("last_signal_setup")
    if isinstance(fallback, dict) and fallback:
        return dict(fallback)
    return None


def _no_zones_message(confluence_mode: str) -> str:
    if confluence_mode == "anchor_rules":
        return (
            "No confluence zones found with the current settings. "
            "For anchor setups, review the anchor level, confluence rules, "
            "and per-rule tolerances. A missing finite anchor price also "
            "yields no zones."
        )
    return (
        "No confluence zones found with the current settings. "
        "Try increasing tolerance or selecting more levels."
    )


def _selected_anchor_levels(
    anchor_level: str | None, confluence_rules: list[dict], available_columns: list[str]
) -> list[str]:
    selected_levels: list[str] = []
    if anchor_level:
        selected_levels.append(anchor_level)
    for rule in confluence_rules:
        level = str(rule.get("level", "")).strip()
        if level and level not in selected_levels:
            selected_levels.append(level)
    return [level for level in selected_levels if level in available_columns]


def _missing_anchor_columns(
    levels_df, anchor_level: str | None, confluence_rules: list[dict]
) -> list[str]:
    missing_columns: list[str] = []
    if anchor_level and anchor_level not in levels_df.columns:
        missing_columns.append(anchor_level)
    for rule in confluence_rules:
        level = str(rule.get("level", "")).strip()
        if level and level not in levels_df.columns:
            missing_columns.append(level)
    return sorted(set(missing_columns))


def _normalize_signal_settings_for_hash(settings: dict) -> dict:
    def _safe_float(value: object, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            result = float(value)
        except (TypeError, ValueError):
            return default
        return default if pd.isna(result) else result

    normalized = dict(settings)
    selected_levels = normalized.get("selected_levels")
    if isinstance(selected_levels, list):
        normalized["selected_levels"] = sorted(str(level) for level in selected_levels)
    rules = normalized.get("confluence_rules")
    if isinstance(rules, list):
        normalized_rules = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            normalized_rules.append(
                {
                    "level": str(rule.get("level", "")),
                    "tolerance_ticks": _safe_float(rule.get("tolerance_ticks", 0.0), default=0.0),
                    "required": bool(rule.get("required", False)),
                }
            )
        normalized["confluence_rules"] = sorted(
            normalized_rules,
            key=lambda item: (item["level"], item["tolerance_ticks"], item["required"]),
        )
    trigger_params = normalized.get("trigger_params")
    if isinstance(trigger_params, dict):
        normalized["trigger_params"] = dict(trigger_params)
    normalized["trigger_timeframe"] = normalize_trigger_timeframe(
        normalized.get("trigger_timeframe")
    )
    if "otf_filter" in normalized:
        otf_filter_config = normalize_otf_filter_config(normalized.get("otf_filter"))
    else:
        setup_snapshot = normalized.get("setup_snapshot")
        if isinstance(setup_snapshot, dict):
            otf_filter_config = get_effective_otf_filter_config(setup_snapshot)
        else:
            otf_filter_config = normalize_otf_filter_config(None)
    normalized["otf_filter"] = otf_filter_config
    normalized["otf_algorithm_version"] = OTF_ALGORITHM_VERSION
    normalized["otf_config_hash"] = compute_otf_config_hash(otf_filter_config)
    setup_snapshot = normalized.get("setup_snapshot")
    if isinstance(setup_snapshot, dict):
        normalized_setup_snapshot = dict(setup_snapshot)
        normalized_setup_snapshot["otf_filter"] = get_effective_otf_filter_config(setup_snapshot)
        normalized_setup_snapshot["otf_algorithm_version"] = OTF_ALGORITHM_VERSION
        normalized_setup_snapshot["otf_config_hash"] = compute_otf_config_hash(
            normalized_setup_snapshot["otf_filter"]
        )
        normalized["setup_snapshot"] = normalized_setup_snapshot
    return normalized


def _try_normalize_signal_settings_for_hash(
    settings: dict,
) -> tuple[dict | None, str | None]:
    """Return (normalized, None) on success or (None, error_message) on invalid OTF config.

    The strict ``_normalize_signal_settings_for_hash`` helper remains unchanged
    for valid data and direct tests. This wrapper is for UI call sites that must
    show a blocker rather than crash.
    """
    try:
        return _normalize_signal_settings_for_hash(settings), None
    except ValueError as exc:
        return None, str(exc)


def _resolve_loaded_signal_identity(
    loaded_settings: object,
    loaded_hash: object,
) -> dict:
    """Validate loaded signal settings and return a complete identity resolution.

    Returns a dict with keys:
      status: "trusted" | "invalid" | "unavailable"
      settings: normalized dict or None
      hash: trusted hash str or None
      error: human-readable error str or None

    Rules:
    - ``loaded_settings`` is not a dict → unavailable.
    - OTF normalization fails → invalid.
    - ``loaded_hash`` present and does not match recomputed hash → invalid.
    - All checks pass → trusted (hash is always recomputed, never blindly trusted).
    """
    if not isinstance(loaded_settings, dict):
        return {
            "status": _IDENTITY_STATUS_UNAVAILABLE,
            "settings": None,
            "hash": None,
            "error": "Loaded signal run has no settings record.",
        }

    normalized, err = _try_normalize_signal_settings_for_hash(loaded_settings)
    if normalized is None:
        return {
            "status": _IDENTITY_STATUS_INVALID,
            "settings": None,
            "hash": None,
            "error": f"Loaded signal settings contain invalid OTF configuration: {err}",
        }

    recomputed_hash = compute_signal_settings_hash(normalized)

    if isinstance(loaded_hash, str) and loaded_hash:
        if loaded_hash != recomputed_hash:
            return {
                "status": _IDENTITY_STATUS_INVALID,
                "settings": None,
                "hash": None,
                "error": (
                    "Persisted signal settings hash does not match the recomputed hash; "
                    "identity is untrustworthy."
                ),
            }

    return {
        "status": _IDENTITY_STATUS_TRUSTED,
        "settings": normalized,
        "hash": recomputed_hash,
        "error": None,
    }


def _validate_signal_artifact_identity_for_save(
    session_state: dict,
    current_settings: dict | None,
) -> tuple[bool, str | None]:
    """Return (can_save, error_message) for saving current signal artifacts.

    Both "Save current signals" UI paths call this single shared helper.

    Returns (True, None) only when all of the following hold:
    - ``signal_artifact_identity_status`` is "trusted".
    - Stored ``signal_settings`` are present and normalizable.
    - Stored ``signal_settings_hash`` is present and matches the recomputed hash.
    - ``current_settings`` is a valid dict whose hash matches the stored hash.

    Returns (False, message) for any other case.  The message for current-controls
    drift uses ``_SIGNAL_CONTROLS_CHANGED_WARNING`` so the caller can surface it as
    a warning; all other failures use ``_OTF_INVALID_ARTIFACT_BLOCKER``.
    """
    status = session_state.get(_SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY)
    if status != _IDENTITY_STATUS_TRUSTED:
        return False, _OTF_INVALID_ARTIFACT_BLOCKER

    stored_settings = session_state.get("signal_settings")
    if not isinstance(stored_settings, dict):
        return False, _OTF_INVALID_ARTIFACT_BLOCKER

    normalized_stored, _err = _try_normalize_signal_settings_for_hash(stored_settings)
    if normalized_stored is None:
        return False, _OTF_INVALID_ARTIFACT_BLOCKER

    stored_hash = session_state.get("signal_settings_hash")
    if not isinstance(stored_hash, str) or not stored_hash:
        return False, _OTF_INVALID_ARTIFACT_BLOCKER

    recomputed_stored_hash = compute_signal_settings_hash(normalized_stored)
    if recomputed_stored_hash != stored_hash:
        return False, _OTF_INVALID_ARTIFACT_BLOCKER

    if current_settings is None:
        return False, _OTF_INVALID_ARTIFACT_BLOCKER

    current_hash = compute_signal_settings_hash(current_settings)
    if current_hash != stored_hash:
        return False, _SIGNAL_CONTROLS_CHANGED_WARNING

    return True, None


def _build_signal_settings(
    *,
    confluence_mode: str,
    selected_levels: list[str],
    anchor_level: str | None,
    confluence_rules: list[dict],
    min_valid_confluences: int,
    tolerance_ticks: float,
    min_confluences: int,
    max_confluences: int,
    naked_only: bool,
    naked_requirement: str,
    trigger: str,
    trigger_timeframe: str,
    direction: str,
    trigger_params: dict,
    use_saved_setup: bool,
    setup_snapshot: dict | None,
) -> dict:
    return _normalize_signal_settings_for_hash(
        {
            "confluence_mode": confluence_mode,
            "selected_levels": selected_levels,
            "anchor_level": anchor_level,
            "confluence_rules": confluence_rules,
            "min_valid_confluences": min_valid_confluences,
            "tolerance_ticks": tolerance_ticks,
            "min_confluences": min_confluences,
            "max_confluences": max_confluences,
            "naked_only": naked_only,
            "naked_requirement": naked_requirement,
            "trigger": trigger,
            "trigger_timeframe": trigger_timeframe,
            "direction": direction,
            "trigger_params": trigger_params,
            "use_saved_setup": use_saved_setup,
            "setup_snapshot": setup_snapshot if use_saved_setup else None,
        }
    )


def _saved_signal_run_label(meta: dict) -> str:
    settings = meta.get("signal_settings")
    if not isinstance(settings, dict):
        settings = {}
    rows = meta.get("rows")
    row_count = rows.get("signals") if isinstance(rows, dict) else "—"
    created_at_raw = meta.get("created_at")
    created = str(created_at_raw)[:10] if created_at_raw else "unknown date"
    selected_levels = settings.get("selected_levels")
    selected_count = len(selected_levels) if isinstance(selected_levels, list) else 0
    return (
        f"{created} · {str(meta.get('signal_settings_hash', 'unknown'))[:12]}… · "
        f"trigger={settings.get('trigger', '—')} · direction={settings.get('direction', '—')} · "
        f"tf={normalize_trigger_timeframe(settings.get('trigger_timeframe'))} · "
        f"mode={settings.get('confluence_mode', '—')} · levels={selected_count} · rows={row_count}"
    )


def _can_save_signal_artifacts(
    signals_df: object,
    zones_df: object,
    naked_flags_df: object,
) -> bool:
    return (
        isinstance(signals_df, pd.DataFrame)
        and isinstance(zones_df, pd.DataFrame)
        and isinstance(naked_flags_df, pd.DataFrame)
    )


def _get_current_signal_artifacts() -> tuple[object, object, object]:
    return (
        st.session_state.get("signals"),
        st.session_state.get("confluence_zones"),
        st.session_state.get("naked_flags"),
    )


def _get_stored_signal_settings() -> tuple[dict | None, str | None]:
    settings = st.session_state.get("signal_settings")
    if not isinstance(settings, dict):
        return None, None

    normalized_settings, err = _try_normalize_signal_settings_for_hash(settings)
    if normalized_settings is None:
        return None, None  # malformed stored OTF state — unavailable

    settings_hash = st.session_state.get("signal_settings_hash")
    if not isinstance(settings_hash, str) or not settings_hash:
        settings_hash = compute_signal_settings_hash(normalized_settings)
    return normalized_settings, settings_hash


_SAVED_SETUPS_CACHE_KEY = "_signals_saved_setups_cache"
_SAVED_SETUPS_DIRTY_KEY = "_signals_saved_setups_dirty"
_SAVED_SIGNAL_RUNS_CACHE_KEY = "_signals_saved_signal_runs_cache"
_SAVED_SIGNAL_RUNS_DIRTY_KEY = "_signals_saved_signal_runs_dirty"


def _get_cached_saved_setups(*, force_refresh: bool = False) -> list[dict]:
    if force_refresh:
        st.session_state[_SAVED_SETUPS_DIRTY_KEY] = True
    cached = st.session_state.get(_SAVED_SETUPS_CACHE_KEY)
    if bool(st.session_state.get(_SAVED_SETUPS_DIRTY_KEY, True)) or not isinstance(cached, list):
        cached = list_saved_setups()
        st.session_state[_SAVED_SETUPS_CACHE_KEY] = cached
        st.session_state[_SAVED_SETUPS_DIRTY_KEY] = False
    return list(cached)


def _saved_signal_runs_cache_token(dataset_id: str, levels_settings_hash: str) -> str:
    return f"{dataset_id}::{levels_settings_hash}"


def _get_cached_saved_signal_runs(
    *,
    dataset_id: str,
    levels_settings_hash: str,
    force_refresh: bool = False,
) -> list[dict]:
    cache = st.session_state.get(_SAVED_SIGNAL_RUNS_CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
    dirty_tokens = st.session_state.get(_SAVED_SIGNAL_RUNS_DIRTY_KEY)
    if not isinstance(dirty_tokens, set):
        dirty_tokens = set()

    cache_token = _saved_signal_runs_cache_token(dataset_id, levels_settings_hash)
    if force_refresh:
        dirty_tokens.add(cache_token)

    if cache_token not in cache or cache_token in dirty_tokens:
        cache[cache_token] = [
            item
            for item in list_saved_signal_runs(
                dataset_id=dataset_id, levels_settings_hash=levels_settings_hash
            )
            if isinstance(item.get("signal_settings_hash"), str) and item["signal_settings_hash"]
        ]
        dirty_tokens.discard(cache_token)
        st.session_state[_SAVED_SIGNAL_RUNS_CACHE_KEY] = cache
        st.session_state[_SAVED_SIGNAL_RUNS_DIRTY_KEY] = dirty_tokens

    cached_runs = cache.get(cache_token, [])
    return list(cached_runs) if isinstance(cached_runs, list) else []


def _mark_saved_signal_runs_dirty(dataset_id: object, levels_settings_hash: object) -> None:
    if not isinstance(dataset_id, str) or not dataset_id:
        return
    if not isinstance(levels_settings_hash, str) or not levels_settings_hash:
        return
    dirty_tokens = st.session_state.get(_SAVED_SIGNAL_RUNS_DIRTY_KEY)
    if not isinstance(dirty_tokens, set):
        dirty_tokens = set()
    dirty_tokens.add(_saved_signal_runs_cache_token(dataset_id, levels_settings_hash))
    st.session_state[_SAVED_SIGNAL_RUNS_DIRTY_KEY] = dirty_tokens


# ── Require levels ────────────────────────────────────────────────────────────
if "levels" not in st.session_state:
    st.warning(
        "No levels computed. Please load data on the **Data** page and compute levels on the **Levels** page first."
    )
    st.stop()

levels_df = st.session_state["levels"]
instrument = st.session_state.get("instrument", "ES")
tick_size = INSTRUMENTS[instrument].tick_size if instrument in INSTRUMENTS else 0.25

all_level_columns = available_level_columns(levels_df)

if not all_level_columns:
    st.warning("No level columns found. Please compute levels on the Levels page first.")
    st.stop()

raw_active_setup = st.session_state.get("setup_config")
active_setup = raw_active_setup if isinstance(raw_active_setup, dict) and raw_active_setup else None
current_dataset_id = st.session_state.get("dataset_id")
all_saved_setups = _get_cached_saved_setups()

# ── Sidebar controls ──────────────────────────────────────────────────────────
saved_setup: dict | None = None
use_saved_setup = False
generation_blockers: list[str] = []
with st.sidebar:
    st.header("Signal generation")

    default_source = SETUP_SOURCE_MANUAL
    preferred_saved_setups = _filter_saved_setups_for_signals(
        all_saved_setups,
        current_dataset_id=current_dataset_id if isinstance(current_dataset_id, str) else None,
        include_other_datasets=False,
    )
    if active_setup is not None:
        default_source = SETUP_SOURCE_ACTIVE
    elif preferred_saved_setups:
        default_source = SETUP_SOURCE_LIBRARY

    st.subheader("Setup source")
    source_options = [SETUP_SOURCE_MANUAL, SETUP_SOURCE_ACTIVE, SETUP_SOURCE_LIBRARY]
    setup_source = st.radio(
        "Setup source",
        options=source_options,
        index=source_options.index(default_source),
    )

    if setup_source == SETUP_SOURCE_ACTIVE and active_setup is None:
        st.info("No active setup found. Configure manually or select a saved setup from library.")
        setup_source = SETUP_SOURCE_MANUAL

    if setup_source == SETUP_SOURCE_LIBRARY:
        has_other_dataset_setups = any(
            _dataset_relation_label(
                item.get("dataset_id"),
                current_dataset_id if isinstance(current_dataset_id, str) else None,
            )
            == "other dataset"
            for item in all_saved_setups
        )
        if st.button("Refresh saved setups", key="refresh_saved_setups", width="stretch"):
            all_saved_setups = _get_cached_saved_setups(force_refresh=True)
            has_other_dataset_setups = any(
                _dataset_relation_label(
                    item.get("dataset_id"),
                    current_dataset_id if isinstance(current_dataset_id, str) else None,
                )
                == "other dataset"
                for item in all_saved_setups
            )
        include_other_datasets = st.checkbox(
            "Include setups from other datasets",
            value=False,
            disabled=not has_other_dataset_setups,
        )
        setup_options = _filter_saved_setups_for_signals(
            all_saved_setups,
            current_dataset_id=current_dataset_id if isinstance(current_dataset_id, str) else None,
            include_other_datasets=include_other_datasets,
        )
        option_map = {
            item["setup_id"]: item
            for item in setup_options
            if isinstance(item.get("setup_id"), str) and item["setup_id"]
        }
        if not option_map:
            st.info(
                "No saved setups available for this selection. Configure manually or set an active setup."
            )
            setup_source = SETUP_SOURCE_MANUAL
        else:
            setup_ids = list(option_map)
            selected_setup_id = st.selectbox(
                "Saved setup",
                options=setup_ids,
                format_func=lambda setup_id: _saved_setup_option_label(
                    option_map[setup_id],
                    current_dataset_id if isinstance(current_dataset_id, str) else None,
                ),
            )
            try:
                selected_setup_meta = load_setup(selected_setup_id)
            except (FileNotFoundError, OSError, ValueError) as exc:
                st.warning(f"Unable to load selected setup ({selected_setup_id[:12]}...): {exc}")
                setup_source = SETUP_SOURCE_MANUAL
            else:
                saved_setup = dict(selected_setup_meta.get("setup_config", {}))
                if (
                    _dataset_relation_label(
                        selected_setup_meta.get("dataset_id"),
                        current_dataset_id if isinstance(current_dataset_id, str) else None,
                    )
                    == "other dataset"
                ):
                    st.warning(
                        "Selected setup belongs to a different dataset. Verify level compatibility before generating signals."
                    )
    elif setup_source == SETUP_SOURCE_ACTIVE and active_setup is not None:
        saved_setup = dict(active_setup)

    use_saved_setup = (
        setup_source in {SETUP_SOURCE_ACTIVE, SETUP_SOURCE_LIBRARY} and saved_setup is not None
    )

    if use_saved_setup and saved_setup is not None:
        # Compute blockers first — before any type coercion — so malformed/legacy
        # configs surface as user-facing warnings instead of page crashes.
        for blocker in _saved_setup_generation_blockers(saved_setup, all_level_columns):
            generation_blockers.append(blocker)

        confluence_mode = str(saved_setup.get("confluence_mode", "global_cluster"))
        confluence_rules = _safe_list(saved_setup.get("confluence_rules"))
        min_valid_confluences = _safe_int(saved_setup.get("min_valid_confluences"), 1)
        anchor_level = saved_setup.get("anchor_level")
        if confluence_mode == "anchor_rules":
            selected_levels = []
            if isinstance(anchor_level, str) and anchor_level:
                selected_levels.append(anchor_level)
            for rule in confluence_rules:
                if not isinstance(rule, dict):
                    continue
                level = str(rule.get("level", "")).strip()
                if level and level not in selected_levels:
                    selected_levels.append(level)
        else:
            configured_levels = saved_setup.get("selected_levels", [])
            if isinstance(configured_levels, list):
                selected_levels = [str(col) for col in configured_levels]
            else:
                selected_levels = []
            anchor_level = None
            confluence_rules = []
            min_valid_confluences = 1
        tolerance_ticks = _safe_float(saved_setup.get("tolerance_ticks"), 4.0)
        min_conf = _safe_int(saved_setup.get("min_confluences"), 2)
        max_conf = _safe_int(saved_setup.get("max_confluences"), 5)
        naked_only = _safe_bool(saved_setup.get("naked_only"), False)
        # Empty/None strings for enum-like fields normalize to defaults;
        # validate_setup_config will flag genuinely invalid values.
        naked_requirement = str(saved_setup.get("naked_requirement") or "any")
        trigger = str(saved_setup.get("trigger") or "touch")
        trigger_timeframe = normalize_trigger_timeframe(
            saved_setup.get("trigger_timeframe", DEFAULT_TRIGGER_TIMEFRAME)
        )
        direction = str(saved_setup.get("direction") or "both")
        trigger_params = _safe_dict(saved_setup.get("trigger_params"))
        if trigger == "3c":
            trigger_params = _normalize_3c_params(trigger_params)

        st.success(f"Using saved setup: {saved_setup.get('name', 'Untitled setup')}")
        st.caption(f"Levels: {', '.join(selected_levels) if selected_levels else '(none)'}")
        try:
            otf_config = get_effective_otf_filter_config(saved_setup)
            st.caption(
                "Signals keep the complete candidate population. "
                "OTF admission is applied later in Backtest, Grid, and Walk-forward. "
                "Config provenance: a saved signal run’s OTF settings win over later "
                "Setup Builder edits — regenerate signals to pick up changed OTF settings."
            )
            st.caption(
                f"OTF v{OTF_ALGORITHM_VERSION} · hash={compute_otf_config_hash(otf_config)[:12]}… · "
                f"enabled={otf_config['enabled']} · timeframes={otf_config['timeframes']}"
            )
        except ValueError:
            generation_blockers.append(
                "Saved setup OTF configuration is invalid. "
                "Update the setup in Setup Builder before generating or saving signals."
            )
    else:
        selected_mode_label = st.selectbox(
            "Confluence mode",
            options=list(CONFLUENCE_MODE_OPTIONS.keys()),
            index=0,
            help="Choose whether to detect global level clusters or anchor-based confluence rules.",
        )
        confluence_mode = CONFLUENCE_MODE_OPTIONS[selected_mode_label]
        anchor_level = None
        confluence_rules = []
        min_valid_confluences = 1
        st.header("Confluence settings")

        if confluence_mode == "global_cluster":
            selected_levels = st.multiselect(
                "Level columns",
                options=all_level_columns,
                default=default_selected_levels(all_level_columns),
                help="Level columns to include in confluence detection.",
            )

            tolerance_ticks = st.number_input(
                "Tolerance (ticks)",
                min_value=0.0,
                max_value=100.0,
                value=4.0,
                step=0.5,
                help=f"Cluster tolerance in ticks. 1 tick = {tick_size} price units.",
            )

            min_conf = st.slider("Min confluences", min_value=1, max_value=5, value=2)
            max_conf = st.slider("Max confluences", min_value=1, max_value=5, value=5)
            if max_conf < min_conf:
                max_conf = min_conf
        else:
            anchor_level = st.selectbox(
                "Anchor level",
                options=all_level_columns,
                index=0,
                help="Primary level around which anchor confluence is evaluated.",
            )
            confluence_level_options = [
                level for level in all_level_columns if level != anchor_level
            ]
            selected_confluence_levels = st.multiselect(
                "Confluence levels",
                options=confluence_level_options,
                default=[],
                help="Levels evaluated against the anchor with per-rule tolerance and required flags.",
            )
            for idx, level in enumerate(selected_confluence_levels):
                level_key = _widget_key_part(level)
                key_base = f"manual_anchor_rule_{idx}_{level_key}"
                st.markdown(f"**{level}**")
                rule_tolerance = st.number_input(
                    f"Tolerance ticks — {level}",
                    min_value=0.0,
                    max_value=100.0,
                    value=4.0,
                    step=0.5,
                    key=f"{key_base}_tolerance",
                )
                rule_required = st.checkbox(
                    f"Required — {level}",
                    value=False,
                    key=f"{key_base}_required",
                )
                confluence_rules.append(
                    {
                        "level": level,
                        "tolerance_ticks": float(rule_tolerance),
                        "required": bool(rule_required),
                    }
                )
            if selected_confluence_levels:
                min_valid_confluences = int(
                    st.number_input(
                        "Minimum valid confluences",
                        min_value=0,
                        max_value=len(selected_confluence_levels),
                        value=1,
                        step=1,
                    )
                )
            else:
                min_valid_confluences = 0
                st.caption("Anchor only — no confluence required. Zone is the live anchor price.")
            selected_levels = [anchor_level, *selected_confluence_levels]

        st.header("Signal settings")

        trigger = st.selectbox(
            "Trigger",
            options=["touch", "reject", "break", "reclaim", "3c"],
            index=0,
        )

        direction = st.selectbox(
            "Direction",
            options=["long", "short", "both"],
            index=2,
        )
        trigger_timeframe_options = [
            value for value in TRIGGER_TIMEFRAME_CHOICES if value in VALID_TRIGGER_TIMEFRAMES
        ]
        default_trigger_timeframe_index = trigger_timeframe_options.index(DEFAULT_TRIGGER_TIMEFRAME)
        trigger_timeframe_label_options = [
            TRIGGER_TIMEFRAME_DISPLAY[value] for value in trigger_timeframe_options
        ]
        trigger_timeframe_help = (
            "Arrival, inside/muted, SFP, and reversal are evaluated on the selected trigger timeframe. "
            "Retrace entry fill is evaluated on canonical/base bars after reversal candle completes. "
            "max_entry_wait_bars_after_reversal counts trigger-timeframe bars."
            if trigger == "3c"
            else (
                "Candle-close trigger logic is evaluated on the selected trigger timeframe. "
                "The default preserves current behavior."
            )
        )
        trigger_timeframe_label = st.selectbox(
            "Trigger timeframe",
            options=trigger_timeframe_label_options,
            index=default_trigger_timeframe_index,
            help=trigger_timeframe_help,
        )
        trigger_timeframe = TRIGGER_TIMEFRAME_LABELS[trigger_timeframe_label]
        if trigger == "3c" and trigger_timeframe != DEFAULT_TRIGGER_TIMEFRAME:
            st.info(
                "3c with non-base trigger timeframe: arrival, muted, SFP, and reversal "
                "are evaluated on trigger-timeframe candles. "
                "Retrace entry fill is evaluated on canonical/base bars."
            )

        naked_only = st.toggle("Naked / untested levels only", value=False)
        naked_requirement = "any"
        if naked_only:
            naked_requirement = st.radio(
                "Naked requirement",
                options=["any", "all"],
                horizontal=True,
                help="'any': at least one level in the zone must be naked. 'all': every level must be naked.",
            )

        if trigger == "3c":
            st.subheader("3c parameters")
            entry_retrace = st.number_input(
                "Entry retrace ticks",
                min_value=0.0,
                max_value=50.0,
                value=4.0,
                step=0.5,
                help="Ticks price must retrace after reversal close before 3c entry triggers.",
            )
            max_wait_bars = st.number_input(
                "Max entry wait bars after reversal",
                min_value=0,
                max_value=200,
                value=5,
                step=1,
                help="Number of bars to wait for retracement after reversal.",
            )
            trigger_params = {
                "entry_retrace_ticks": entry_retrace,
                "max_entry_wait_bars_after_reversal": int(max_wait_bars),
            }
        else:
            trigger_params = {}

    for blocker in generation_blockers:
        st.warning(blocker)
    generate_btn = st.button(
        "Generate signals",
        type="primary",
        width="stretch",
        disabled=bool(generation_blockers),
    )

signal_settings: dict | None = None
signal_settings_otf_error: str | None = None
try:
    signal_settings = _build_signal_settings(
        confluence_mode=confluence_mode,
        selected_levels=selected_levels,
        anchor_level=anchor_level,
        confluence_rules=confluence_rules,
        min_valid_confluences=min_valid_confluences,
        tolerance_ticks=tolerance_ticks,
        min_confluences=min_conf,
        max_confluences=max_conf,
        naked_only=naked_only,
        naked_requirement=naked_requirement,
        trigger=trigger,
        trigger_timeframe=trigger_timeframe,
        direction=direction,
        trigger_params=trigger_params,
        use_saved_setup=use_saved_setup,
        setup_snapshot=saved_setup if use_saved_setup else None,
    )
except ValueError as exc:
    signal_settings_otf_error = str(exc)

if signal_settings_otf_error:
    st.error(
        "OTF configuration is invalid and cannot be hashed. "
        "Update the setup in Setup Builder before generating or saving signals. "
        f"Detail: {signal_settings_otf_error}"
    )

dataset_id = st.session_state.get("dataset_id")
levels_settings = st.session_state.get("levels_settings")
levels_settings_hash: str | None = None
if not isinstance(dataset_id, str) or not dataset_id:
    st.warning(
        "Signal persistence is unavailable because dataset context is missing. Load or save a dataset first."
    )
elif not isinstance(levels_settings, dict) or not levels_settings:
    st.warning(
        "Signal persistence is unavailable because levels settings are missing. "
        "Load saved levels or recalculate levels first."
    )
else:
    levels_settings_hash = compute_levels_settings_hash(levels_settings)

# ── Generate ──────────────────────────────────────────────────────────────────
if generate_btn:
    try:
        levels_for_naked_flags = selected_levels

        if confluence_mode == "anchor_rules":
            if not anchor_level:
                st.error("Anchor mode requires an anchor level.")
                st.stop()
            if not confluence_rules and min_valid_confluences >= 1:
                st.error("Anchor mode requires at least one confluence rule.")
                st.stop()
            missing_columns = _missing_anchor_columns(levels_df, anchor_level, confluence_rules)
            if missing_columns:
                st.error(
                    "Anchor mode references level columns that are not available in the current levels DataFrame: "
                    + ", ".join(missing_columns)
                )
                st.stop()
            levels_for_naked_flags = _selected_anchor_levels(
                anchor_level, confluence_rules, list(levels_df.columns)
            )
        elif not selected_levels:
            st.error("Please select at least one level column.")
            st.stop()

        with st.spinner("Detecting confluence zones…"):
            if confluence_mode == "global_cluster":
                zones = detect_confluence_zones(
                    levels_df,
                    level_columns=selected_levels,
                    tick_size=tick_size,
                    tolerance_ticks=tolerance_ticks,
                    min_confluences=min_conf,
                    max_confluences=max_conf,
                )
            elif confluence_mode == "anchor_rules":
                zones = detect_anchor_confluence_zones(
                    levels_df,
                    anchor_level=anchor_level,
                    confluence_rules=confluence_rules,
                    tick_size=tick_size,
                    min_valid_confluences=min_valid_confluences,
                )
            else:
                st.error(f"Unsupported confluence mode: {confluence_mode}")
                st.stop()
            st.session_state["confluence_zones"] = zones

        with st.spinner("Flagging naked levels…"):
            naked_flags = flag_naked_levels(
                levels_df,
                level_columns=levels_for_naked_flags,
                tick_size=tick_size,
                touch_tolerance_ticks=0,
            )
            st.session_state["naked_flags"] = naked_flags

        with st.spinner("Generating signals…"):
            if trigger == "3c":
                trigger_params = dict(trigger_params or {})
                trigger_params["_source_mode"] = confluence_mode
            signals = generate_signals(
                levels_df,
                zones=zones,
                trigger=trigger,
                direction=direction,
                tick_size=tick_size,
                trigger_timeframe=trigger_timeframe,
                trigger_params=trigger_params,
                naked_only=naked_only,
                naked_flags=naked_flags if naked_only else None,
                naked_requirement=naked_requirement,
            )
            if use_saved_setup and saved_setup is not None:
                signals = signals.copy()
                signals["setup_name"] = saved_setup.get("name", "Untitled setup")
                st.session_state["last_signal_setup"] = saved_setup
                st.session_state["signal_context"] = {
                    "setup_name": saved_setup.get("name", "Untitled setup"),
                    "confluence_mode": confluence_mode,
                    "setup_caption": _saved_setup_caption(saved_setup),
                }
            else:
                st.session_state.pop("last_signal_setup", None)
                st.session_state["signal_context"] = {
                    "setup_name": None,
                    "confluence_mode": confluence_mode,
                    "setup_caption": None,
                }
            st.session_state["signals"] = signals
            if signal_settings is not None:
                st.session_state[_SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY] = _IDENTITY_STATUS_TRUSTED
                st.session_state.pop(_SIGNAL_ARTIFACT_IDENTITY_ERROR_KEY, None)
                st.session_state["signal_settings"] = signal_settings
                st.session_state["signal_settings_hash"] = compute_signal_settings_hash(
                    signal_settings
                )
    except Exception as exc:
        st.error(
            "Signal generation failed. Review the traceback below and adjust the setup or dataset."
        )
        st.exception(exc)
        st.stop()

saved_signal_runs: list[dict] = []
matching_saved_signal_run: dict | None = None

if isinstance(dataset_id, str) and dataset_id and isinstance(levels_settings_hash, str):
    st.divider()
    st.subheader("Saved signal runs")
    refresh_saved_signal_runs = st.button(
        "Refresh saved signal runs",
        key="refresh_saved_signal_runs",
        width="stretch",
    )
    saved_signal_runs = _get_cached_saved_signal_runs(
        dataset_id=dataset_id,
        levels_settings_hash=levels_settings_hash,
        force_refresh=refresh_saved_signal_runs,
    )
    matching_saved_signal_run = (
        find_matching_signal_run(
            dataset_id=dataset_id,
            levels_settings_hash=levels_settings_hash,
            signal_settings=signal_settings,
        )
        if signal_settings is not None
        else None
    )

    if matching_saved_signal_run is not None:
        st.info("Matching saved signals found.")

    if saved_signal_runs:
        run_options = {item["signal_settings_hash"]: item for item in saved_signal_runs}
        run_ids = list(run_options)
        default_selected_run = (
            matching_saved_signal_run["signal_settings_hash"]
            if matching_saved_signal_run is not None
            and matching_saved_signal_run.get("signal_settings_hash") in run_options
            else run_ids[0]
        )
        selected_run_hash = st.selectbox(
            "Saved signal runs",
            options=run_ids,
            index=run_ids.index(default_selected_run),
            format_func=lambda signal_hash: _saved_signal_run_label(run_options[signal_hash]),
            key="saved_signal_runs_selector",
        )
        selected_run_meta = run_options[selected_run_hash]
        selected_settings = selected_run_meta.get("signal_settings")
        if isinstance(selected_settings, dict) and signal_settings is not None:
            _selected_norm, _selected_err = _try_normalize_signal_settings_for_hash(
                selected_settings
            )
            if _selected_norm is None:
                st.caption("Settings comparison unavailable: saved run OTF settings are invalid.")
            elif _selected_norm != signal_settings:
                st.caption("Selected saved signal settings differ from current controls.")

        signal_actions = st.columns(3)
        if signal_actions[0].button(
            "Load selected saved signals",
            key="load_selected_saved_signals",
            width="stretch",
        ):
            try:
                loaded_signals, loaded_zones, loaded_naked_flags, loaded_meta = load_signal_run(
                    dataset_id,
                    levels_settings_hash,
                    selected_run_hash,
                )
            except (FileNotFoundError, ValueError, OSError) as exc:
                st.error(f"Unable to load saved signals ({selected_run_hash[:12]}...): {exc}")
            else:
                # Resolve identity BEFORE touching session state so the transition is atomic.
                # If we modified artifacts first and validation failed midway, new artifacts
                # could end up associated with stale settings from a previous run.
                identity = _resolve_loaded_signal_identity(
                    loaded_meta.get("signal_settings"),
                    loaded_meta.get("signal_settings_hash"),
                )
                # Always install artifacts (available for inspection regardless of identity).
                st.session_state["signals"] = loaded_signals
                st.session_state["confluence_zones"] = loaded_zones
                st.session_state["naked_flags"] = loaded_naked_flags
                st.session_state["signal_context"] = loaded_meta.get("signal_context", {})
                st.session_state["last_signal_setup"] = loaded_meta.get("last_signal_setup", {})
                # Apply identity state atomically — no mixture of new artifacts and old identity.
                if identity["status"] == _IDENTITY_STATUS_TRUSTED:
                    st.session_state["signal_settings"] = identity["settings"]
                    st.session_state["signal_settings_hash"] = identity["hash"]
                    st.session_state[_SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY] = (
                        _IDENTITY_STATUS_TRUSTED
                    )
                    st.session_state.pop(_SIGNAL_ARTIFACT_IDENTITY_ERROR_KEY, None)
                else:
                    st.session_state.pop("signal_settings", None)
                    st.session_state.pop("signal_settings_hash", None)
                    st.session_state[_SIGNAL_ARTIFACT_IDENTITY_STATUS_KEY] = identity["status"]
                    st.session_state[_SIGNAL_ARTIFACT_IDENTITY_ERROR_KEY] = identity["error"]
                    st.warning(
                        "Loaded signal artifacts have invalid or unavailable OTF identity. "
                        "They may be inspected, but cannot be saved or treated as matching "
                        "current controls. Update the setup and regenerate signals."
                    )
                st.success(f"Loaded saved signals ({selected_run_hash[:12]}...).")
                st.rerun()
        if signal_actions[1].button(
            "Save current signals",
            key="save_current_signals_locally",
            width="stretch",
        ):
            current_signals, current_zones, current_naked_flags = _get_current_signal_artifacts()
            if not _can_save_signal_artifacts(current_signals, current_zones, current_naked_flags):
                st.warning("Generate or load signals first, then save.")
            else:
                can_save, save_err = _validate_signal_artifact_identity_for_save(
                    st.session_state, signal_settings
                )
                if can_save:
                    saved_meta = save_signal_run(
                        dataset_id=dataset_id,
                        levels_settings_hash=levels_settings_hash,
                        signal_settings=st.session_state["signal_settings"],
                        signals=current_signals,
                        confluence_zones=current_zones,
                        naked_flags=current_naked_flags,
                        signal_context=st.session_state.get("signal_context"),
                        last_signal_setup=st.session_state.get("last_signal_setup"),
                    )
                    _mark_saved_signal_runs_dirty(dataset_id, levels_settings_hash)
                    st.success(
                        f"Saved signals locally ({saved_meta['signal_settings_hash'][:12]}...)."
                    )
                    st.rerun()
                else:
                    st.warning(save_err)
        if signal_actions[2].button(
            "Delete selected saved signals",
            key="delete_selected_saved_signals",
            width="stretch",
        ):
            delete_signal_run(dataset_id, levels_settings_hash, selected_run_hash)
            _mark_saved_signal_runs_dirty(dataset_id, levels_settings_hash)
            st.success("Deleted selected saved signals.")
            st.rerun()
        if st.button(
            "Copy setup to Setup Builder",
            key="copy_setup_snapshot_to_setup_builder",
            width="stretch",
        ):
            setup_snapshot = _extract_setup_snapshot_from_signal_run(selected_run_meta)
            if setup_snapshot is None:
                st.warning("Selected saved signal run does not include a setup snapshot to copy.")
            else:
                st.session_state["setup_config"] = dict(setup_snapshot)
                st.session_state["_setup_builder_editor_config"] = dict(setup_snapshot)
                st.success(
                    "Copied setup snapshot to Setup Builder. Open Setup Builder to review, edit, and save."
                )
    else:
        st.caption("No saved signal runs for this dataset and levels snapshot.")
        if st.button("Save current signals", key="save_current_signals_empty", width="stretch"):
            current_signals, current_zones, current_naked_flags = _get_current_signal_artifacts()
            if not _can_save_signal_artifacts(current_signals, current_zones, current_naked_flags):
                st.warning("Generate or load signals first, then save.")
            else:
                can_save, save_err = _validate_signal_artifact_identity_for_save(
                    st.session_state, signal_settings
                )
                if can_save:
                    saved_meta = save_signal_run(
                        dataset_id=dataset_id,
                        levels_settings_hash=levels_settings_hash,
                        signal_settings=st.session_state["signal_settings"],
                        signals=current_signals,
                        confluence_zones=current_zones,
                        naked_flags=current_naked_flags,
                        signal_context=st.session_state.get("signal_context"),
                        last_signal_setup=st.session_state.get("last_signal_setup"),
                    )
                    _mark_saved_signal_runs_dirty(dataset_id, levels_settings_hash)
                    st.success(
                        f"Saved signals locally ({saved_meta['signal_settings_hash'][:12]}...)."
                    )
                    st.rerun()
                else:
                    st.warning(save_err)

# ── Display results ───────────────────────────────────────────────────────────
zones = st.session_state.get("confluence_zones")
signals = st.session_state.get("signals")

if zones is None:
    st.info("Configure settings in the sidebar and click **Generate signals**.")
    st.stop()

col1, col2 = st.columns(2)
col1.metric("Confluence zones detected", len(zones))
col2.metric("Signals generated", len(signals) if signals is not None else 0)

if zones.empty:
    st.warning(_no_zones_message(confluence_mode))
    st.stop()

if all(col in zones.columns for col in ["anchor_level", "valid_confluence_count", "rule_results"]):
    _render_anchor_diagnostics(zones)

# Signal breakdown
if signals is not None and not signals.empty:
    st.subheader("Signal breakdown")
    breakdown_cols = [c for c in ["trigger", "direction", "status"] if c in signals.columns]
    if "trigger_variant" in signals.columns:
        breakdown_cols.append("trigger_variant")
    if breakdown_cols:
        st.dataframe(
            signals.groupby(breakdown_cols).size().reset_index(name="count"),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Signal table")
    display_cols = [
        c
        for c in [
            "signal_id",
            "timestamp",
            "bar_index",
            "trigger",
            "direction",
            "zone_low",
            "zone_high",
            "zone_mid",
            "level_count",
            "level_names",
            "entry_reference_price",
            "entry_model",
            "status",
            "trigger_variant",
            "level_source_mode",
            "setup_name",
            "naked_level_count",
            "notes",
        ]
        if c in signals.columns
    ]
    st.dataframe(signals[display_cols], width="stretch", hide_index=True)
else:
    st.info("No signals generated with the current settings.")

# ── Chart ─────────────────────────────────────────────────────────────────────
st.subheader("Price chart with signals")
show_confluence_zones = st.toggle("Show confluence zones", value=True)
has_signals = signals is not None and not signals.empty
chart_range_options = [
    "Signal range ± 500 rows",
    "Last 2,000 rows",
    "Last 10,000 rows",
    "Custom date range",
    "Full dataset",
]
default_chart_range = "Signal range ± 500 rows" if has_signals else "Last 2,000 rows"
chart_range = st.selectbox(
    "Chart range",
    options=chart_range_options,
    index=chart_range_options.index(default_chart_range),
)
st.caption(
    "Chart range affects visualization only. Signal tables, saved signal artifacts, and generated signals remain unchanged."
)

chart_start = None
chart_end = None
if chart_range == "Signal range ± 500 rows" and has_signals:
    signal_start, signal_end = timestamp_bounds(signals)
    chart_start, chart_end = buffered_rows_window(
        levels_df,
        start=signal_start,
        end=signal_end,
        buffer_rows=500,
    )
    if chart_start is None or chart_end is None:
        chart_start, chart_end = recent_rows_window(levels_df, rows=2_000)
elif chart_range == "Last 2,000 rows":
    chart_start, chart_end = recent_rows_window(levels_df, rows=2_000)
elif chart_range == "Last 10,000 rows":
    chart_start, chart_end = recent_rows_window(levels_df, rows=10_000)
elif chart_range == "Custom date range":
    min_ts, max_ts = timestamp_bounds(levels_df)
    if min_ts is not None and max_ts is not None:
        custom_cols = st.columns(2)
        custom_start_date = custom_cols[0].date_input(
            "Custom chart start",
            value=min_ts.date(),
            min_value=min_ts.date(),
            max_value=max_ts.date(),
        )
        custom_end_date = custom_cols[1].date_input(
            "Custom chart end",
            value=max_ts.date(),
            min_value=min_ts.date(),
            max_value=max_ts.date(),
        )
        chart_start = pd.Timestamp(custom_start_date)
        chart_end = (
            pd.Timestamp(custom_end_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        )

chart_levels_df = (
    levels_df.copy(deep=True)
    if chart_range == "Full dataset"
    else clip_by_time_window(levels_df, start=chart_start, end=chart_end)
)
chart_signals_df = (
    signals.copy(deep=True)
    if chart_range == "Full dataset" and signals is not None
    else clip_by_time_window(signals, start=chart_start, end=chart_end)
)
chart_zones_df = (
    zones.copy(deep=True)
    if chart_range == "Full dataset"
    else clip_by_time_window(zones, start=chart_start, end=chart_end)
)

try:
    fig = build_signals_chart(
        levels_df=chart_levels_df,
        signals=chart_signals_df,
        selected_levels=selected_levels,
        confluence_zones=chart_zones_df,
        show_confluence_zones=show_confluence_zones,
    )
    st.plotly_chart(fig, width="stretch")
except Exception as exc:
    st.error("Signal chart rendering failed. Signal tables above remain available.")
    st.exception(exc)
