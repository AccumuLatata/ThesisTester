"""Phase 4 — Signals page.

Detects confluence zones, flags naked levels, and generates candidate
entry signals from the levels computed on the Levels page.
"""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from thesistester.app_state import bootstrap_active_saved_dataset
from thesistester.config import INSTRUMENTS
from thesistester.engine import (
    detect_anchor_confluence_zones,
    detect_confluence_zones,
    flag_naked_levels,
    generate_signals,
)
from thesistester.persistence import (
    compute_levels_settings_hash,
    compute_signal_settings_hash,
    delete_signal_run,
    find_matching_signal_run,
    list_saved_signal_runs,
    load_signal_run,
    save_signal_run,
)
from thesistester.setup import (
    DEFAULT_TRIGGER_TIMEFRAME,
    TRIGGER_TIMEFRAME_CHOICES,
    VALID_DIRECTIONS,
    VALID_TRIGGER_TIMEFRAMES,
    VALID_TRIGGERS,
    available_level_columns,
    default_selected_levels,
    normalize_trigger_timeframe,
)

st.title("🎯 Signals")
bootstrap_active_saved_dataset()


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
    "Global Cluster": "global_cluster",
    "Anchor Rules / User Anchor": "anchor_rules",
}
TRIGGER_TIMEFRAME_LABELS = {
    "Base/current timeframe": "base",
    "1 minute": "1min",
    "5 minutes": "5min",
    "15 minutes": "15min",
}
TRIGGER_TIMEFRAME_DISPLAY = {value: key for key, value in TRIGGER_TIMEFRAME_LABELS.items()}

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
        use_container_width=True,
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
            use_container_width=True,
            hide_index=True,
        )


def _normalize_3c_params(params: dict | None) -> dict:
    trigger_params = params or {}
    return {
        # arrival_tolerance_ticks may appear in legacy configs, but its value is
        # intentionally ignored and normalized to 0.0.
        "arrival_tolerance_ticks": 0.0,
        "entry_retrace_ticks": float(trigger_params.get("entry_retrace_ticks", 4.0)),
        "max_entry_wait_bars_after_reversal": int(trigger_params.get("max_entry_wait_bars_after_reversal", 5)),
        "_source_mode": str(trigger_params.get("_source_mode", "global_cluster")),
    }


def _saved_setup_caption(config: dict) -> str:
    confluence_mode = str(config.get("confluence_mode", "global_cluster"))
    trigger = str(config.get("trigger", "touch"))
    trigger_timeframe = (
        DEFAULT_TRIGGER_TIMEFRAME
        if trigger == "3c"
        else normalize_trigger_timeframe(config.get("trigger_timeframe"))
    )
    if confluence_mode == "anchor_rules":
        return (
            f"Mode=anchor_rules • Anchor={config.get('anchor_level') or '-'} • "
            f"Rules={len(config.get('confluence_rules', []))} • "
            f"Min valid={int(config.get('min_valid_confluences', 1))} • "
            f"Trigger TF={trigger_timeframe}"
        )
    return (
        f"Trigger={config.get('trigger')} • Direction={config.get('direction')} • "
        f"Confluences={config.get('min_confluences')}–{config.get('max_confluences')} • "
        f"Trigger TF={trigger_timeframe}"
    )


def _no_zones_message(confluence_mode: str) -> str:
    if confluence_mode == "anchor_rules":
        return (
            "No confluence zones found with the current settings. "
            "For anchor setups, review the anchor level, confluence rules, "
            "and per-rule tolerances."
        )
    return (
        "No confluence zones found with the current settings. "
        "Try increasing tolerance or selecting more levels."
    )


def _selected_anchor_levels(anchor_level: str | None, confluence_rules: list[dict], available_columns: list[str]) -> list[str]:
    selected_levels: list[str] = []
    if anchor_level:
        selected_levels.append(anchor_level)
    for rule in confluence_rules:
        level = str(rule.get("level", "")).strip()
        if level and level not in selected_levels:
            selected_levels.append(level)
    return [level for level in selected_levels if level in available_columns]


def _missing_anchor_columns(levels_df, anchor_level: str | None, confluence_rules: list[dict]) -> list[str]:
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
    if str(normalized.get("trigger")) == "3c":
        normalized["trigger_timeframe"] = DEFAULT_TRIGGER_TIMEFRAME
    setup_snapshot = normalized.get("setup_snapshot")
    if isinstance(setup_snapshot, dict):
        normalized["setup_snapshot"] = dict(setup_snapshot)
    return normalized


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

    normalized_settings = _normalize_signal_settings_for_hash(settings)
    settings_hash = st.session_state.get("signal_settings_hash")
    if not isinstance(settings_hash, str) or not settings_hash:
        settings_hash = compute_signal_settings_hash(normalized_settings)
    return normalized_settings, settings_hash

# ── Require levels ────────────────────────────────────────────────────────────
if "levels" not in st.session_state:
    st.warning("No levels computed. Please load data on the **Data** page and compute levels on the **Levels** page first.")
    st.stop()

levels_df = st.session_state["levels"]
instrument = st.session_state.get("instrument", "ES")
tick_size = INSTRUMENTS[instrument].tick_size if instrument in INSTRUMENTS else 0.25

all_level_columns = available_level_columns(levels_df)

if not all_level_columns:
    st.warning("No level columns found. Please compute levels on the Levels page first.")
    st.stop()

raw_saved_setup = st.session_state.get("setup_config")
saved_setup = raw_saved_setup if isinstance(raw_saved_setup, dict) and raw_saved_setup else None
if saved_setup:
    st.info(f"Using setup: {saved_setup.get('name', 'Untitled setup')}")
    st.caption(_saved_setup_caption(saved_setup))

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Signal generation")

    use_saved_default = saved_setup is not None
    use_saved_setup = st.toggle("Use saved setup", value=use_saved_default)

    if saved_setup is None:
        st.info("No saved setup found. Configure manually here or create one in Setup Builder.")

    if use_saved_setup and saved_setup is not None:
        confluence_mode = str(saved_setup.get("confluence_mode", "global_cluster"))
        configured_levels = saved_setup.get("selected_levels", [])
        anchor_level = saved_setup.get("anchor_level")
        confluence_rules = list(saved_setup.get("confluence_rules", []))
        min_valid_confluences = int(saved_setup.get("min_valid_confluences", 1))
        if confluence_mode == "anchor_rules":
            selected_levels = _selected_anchor_levels(anchor_level, confluence_rules, all_level_columns)
        else:
            selected_levels = [col for col in configured_levels if col in all_level_columns]
            anchor_level = None
            confluence_rules = []
            min_valid_confluences = 1
        tolerance_ticks = float(saved_setup.get("tolerance_ticks", 4.0))
        min_conf = int(saved_setup.get("min_confluences", 2))
        max_conf = int(saved_setup.get("max_confluences", 5))
        naked_only = bool(saved_setup.get("naked_only", False))
        naked_requirement = str(saved_setup.get("naked_requirement", "any"))
        trigger = str(saved_setup.get("trigger", "touch"))
        trigger_timeframe = normalize_trigger_timeframe(
            saved_setup.get("trigger_timeframe", DEFAULT_TRIGGER_TIMEFRAME)
        )
        direction = str(saved_setup.get("direction", "both"))
        trigger_params = dict(saved_setup.get("trigger_params", {}))
        if trigger == "3c":
            trigger_timeframe = DEFAULT_TRIGGER_TIMEFRAME
            trigger_params = _normalize_3c_params(trigger_params)
            st.info(
                "3c currently uses the base/current timeframe only. "
                "Multi-timeframe 3c confirmation will be implemented separately."
            )

        st.success(f"Using saved setup: {saved_setup.get('name', 'Untitled setup')}")
        st.caption(f"Levels: {', '.join(selected_levels) if selected_levels else '(none)'}")

        if trigger not in VALID_TRIGGERS:
            st.error(
                f"Saved setup trigger '{trigger}' is invalid. "
                f"Valid options are: {sorted(VALID_TRIGGERS)}. "
                "Disable saved setup mode and configure manually."
            )
            st.stop()
        if direction not in VALID_DIRECTIONS:
            st.error(
                f"Saved setup direction '{direction}' is invalid. "
                f"Valid options are: {sorted(VALID_DIRECTIONS)}. "
                "Disable saved setup mode and configure manually."
            )
            st.stop()
        if trigger_timeframe not in VALID_TRIGGER_TIMEFRAMES:
            st.error(
                f"Saved setup trigger timeframe '{trigger_timeframe}' is invalid. "
                f"Valid options are: {sorted(VALID_TRIGGER_TIMEFRAMES)}. "
                "Disable saved setup mode and configure manually."
            )
            st.stop()
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
            confluence_level_options = [level for level in all_level_columns if level != anchor_level]
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
                        min_value=1,
                        max_value=len(selected_confluence_levels),
                        value=1,
                        step=1,
                    )
                )
            else:
                st.info("Select at least one confluence level.")
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
        if trigger == "3c":
            st.selectbox(
                "Trigger timeframe",
                options=[TRIGGER_TIMEFRAME_DISPLAY[DEFAULT_TRIGGER_TIMEFRAME]],
                index=0,
                disabled=True,
                help="3c currently uses the base/current timeframe only.",
            )
            trigger_timeframe = DEFAULT_TRIGGER_TIMEFRAME
            st.info(
                "3c currently uses the base/current timeframe only. "
                "Multi-timeframe 3c confirmation will be implemented separately."
            )
        else:
            trigger_timeframe_label_options = [
                TRIGGER_TIMEFRAME_DISPLAY[value] for value in trigger_timeframe_options
            ]
            trigger_timeframe_label = st.selectbox(
                "Trigger timeframe",
                options=trigger_timeframe_label_options,
                index=default_trigger_timeframe_index,
                help=(
                    "Candle-close trigger logic is evaluated on the selected trigger timeframe. "
                    "The default preserves current behavior."
                ),
            )
            trigger_timeframe = TRIGGER_TIMEFRAME_LABELS[trigger_timeframe_label]

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

    generate_btn = st.button("Generate signals", type="primary", use_container_width=True)

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

dataset_id = st.session_state.get("dataset_id")
levels_settings = st.session_state.get("levels_settings")
levels_settings_hash: str | None = None
if not isinstance(dataset_id, str) or not dataset_id:
    st.warning("Signal persistence is unavailable because dataset context is missing. Load or save a dataset first.")
elif not isinstance(levels_settings, dict) or not levels_settings:
    st.warning(
        "Signal persistence is unavailable because levels settings are missing. "
        "Load saved levels or recalculate levels first."
    )
else:
    levels_settings_hash = compute_levels_settings_hash(levels_settings)

# ── Generate ──────────────────────────────────────────────────────────────────
if generate_btn:
    levels_for_naked_flags = selected_levels

    if confluence_mode == "anchor_rules":
        if not anchor_level:
            st.error("Anchor mode requires an anchor level.")
            st.stop()
        if not confluence_rules:
            st.error("Anchor mode requires at least one confluence rule.")
            st.stop()
        missing_columns = _missing_anchor_columns(levels_df, anchor_level, confluence_rules)
        if missing_columns:
            st.error(
                "Anchor mode references level columns that are not available in the current levels DataFrame: "
                + ", ".join(missing_columns)
            )
            st.stop()
        levels_for_naked_flags = _selected_anchor_levels(anchor_level, confluence_rules, list(levels_df.columns))
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
        st.session_state["signal_settings"] = signal_settings
        st.session_state["signal_settings_hash"] = compute_signal_settings_hash(signal_settings)

saved_signal_runs: list[dict] = []
matching_saved_signal_run: dict | None = None

if isinstance(dataset_id, str) and dataset_id and isinstance(levels_settings_hash, str):
    saved_signal_runs = [
        item
        for item in list_saved_signal_runs(dataset_id=dataset_id, levels_settings_hash=levels_settings_hash)
        if isinstance(item.get("signal_settings_hash"), str) and item["signal_settings_hash"]
    ]
    matching_saved_signal_run = find_matching_signal_run(
        dataset_id=dataset_id,
        levels_settings_hash=levels_settings_hash,
        signal_settings=signal_settings,
    )

    if matching_saved_signal_run is not None:
        st.info("Matching saved signals found.")

    if saved_signal_runs:
        st.divider()
        st.subheader("Saved signal runs")
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
        if (
            isinstance(selected_settings, dict)
            and _normalize_signal_settings_for_hash(selected_settings) != signal_settings
        ):
            st.caption("Selected saved signal settings differ from current controls.")

        signal_actions = st.columns(3)
        if signal_actions[0].button(
            "Load selected saved signals",
            key="load_selected_saved_signals",
            use_container_width=True,
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
                st.session_state["signals"] = loaded_signals
                st.session_state["confluence_zones"] = loaded_zones
                st.session_state["naked_flags"] = loaded_naked_flags
                st.session_state["signal_context"] = loaded_meta.get("signal_context", {})
                st.session_state["last_signal_setup"] = loaded_meta.get("last_signal_setup", {})
                loaded_settings = loaded_meta.get("signal_settings")
                if isinstance(loaded_settings, dict):
                    normalized_loaded_settings = _normalize_signal_settings_for_hash(loaded_settings)
                    st.session_state["signal_settings"] = normalized_loaded_settings
                    loaded_hash = loaded_meta.get("signal_settings_hash")
                    if isinstance(loaded_hash, str) and loaded_hash:
                        st.session_state["signal_settings_hash"] = loaded_hash
                    else:
                        st.session_state["signal_settings_hash"] = compute_signal_settings_hash(
                            normalized_loaded_settings
                        )
                st.success(f"Loaded saved signals ({selected_run_hash[:12]}...).")
                st.rerun()
        if signal_actions[1].button(
            "Save current signals",
            key="save_current_signals_locally",
            use_container_width=True,
        ):
            current_signals, current_zones, current_naked_flags = _get_current_signal_artifacts()
            if not _can_save_signal_artifacts(current_signals, current_zones, current_naked_flags):
                st.warning("Generate or load signals first, then save.")
            else:
                generated_signal_settings, generated_signal_settings_hash = _get_stored_signal_settings()
                current_signal_settings_hash = compute_signal_settings_hash(signal_settings)
                if generated_signal_settings is None:
                    st.warning("Signal settings for current artifacts are unavailable. Please regenerate signals before saving.")
                elif generated_signal_settings_hash != current_signal_settings_hash:
                    st.warning(
                        "Signal controls changed after these signals were generated. "
                        "Please regenerate signals before saving."
                    )
                else:
                    saved_meta = save_signal_run(
                        dataset_id=dataset_id,
                        levels_settings_hash=levels_settings_hash,
                        signal_settings=generated_signal_settings,
                        signals=current_signals,
                        confluence_zones=current_zones,
                        naked_flags=current_naked_flags,
                        signal_context=st.session_state.get("signal_context"),
                        last_signal_setup=st.session_state.get("last_signal_setup"),
                    )
                    st.success(f"Saved signals locally ({saved_meta['signal_settings_hash'][:12]}...).")
        if signal_actions[2].button(
            "Delete selected saved signals",
            key="delete_selected_saved_signals",
            use_container_width=True,
        ):
            delete_signal_run(dataset_id, levels_settings_hash, selected_run_hash)
            st.success("Deleted selected saved signals.")
            st.rerun()
    else:
        st.divider()
        st.subheader("Saved signal runs")
        st.caption("No saved signal runs for this dataset and levels snapshot.")
        if st.button("Save current signals", key="save_current_signals_empty", use_container_width=True):
            current_signals, current_zones, current_naked_flags = _get_current_signal_artifacts()
            if not _can_save_signal_artifacts(current_signals, current_zones, current_naked_flags):
                st.warning("Generate or load signals first, then save.")
            else:
                generated_signal_settings, generated_signal_settings_hash = _get_stored_signal_settings()
                current_signal_settings_hash = compute_signal_settings_hash(signal_settings)
                if generated_signal_settings is None:
                    st.warning("Signal settings for current artifacts are unavailable. Please regenerate signals before saving.")
                elif generated_signal_settings_hash != current_signal_settings_hash:
                    st.warning(
                        "Signal controls changed after these signals were generated. "
                        "Please regenerate signals before saving."
                    )
                else:
                    saved_meta = save_signal_run(
                        dataset_id=dataset_id,
                        levels_settings_hash=levels_settings_hash,
                        signal_settings=generated_signal_settings,
                        signals=current_signals,
                        confluence_zones=current_zones,
                        naked_flags=current_naked_flags,
                        signal_context=st.session_state.get("signal_context"),
                        last_signal_setup=st.session_state.get("last_signal_setup"),
                    )
                    st.success(f"Saved signals locally ({saved_meta['signal_settings_hash'][:12]}...).")
                    st.rerun()

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
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Signal table")
    display_cols = [c for c in [
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
    ] if c in signals.columns]
    st.dataframe(signals[display_cols], use_container_width=True, hide_index=True)
else:
    st.info("No signals generated with the current settings.")

# ── Chart ─────────────────────────────────────────────────────────────────────
st.subheader("Price chart with signals")

fig = go.Figure()

# Close price
fig.add_trace(
    go.Scatter(
        x=levels_df["timestamp"],
        y=levels_df["close"],
        mode="lines",
        name="close",
        line=dict(color="steelblue", width=1),
    )
)

# Selected level lines (first 5 to avoid clutter)
for col in selected_levels[:5]:
    if col in levels_df.columns:
        fig.add_trace(
            go.Scatter(
                x=levels_df["timestamp"],
                y=levels_df[col],
                mode="lines",
                name=col,
                line=dict(width=1, dash="dot"),
                opacity=0.6,
            )
        )

# Signal markers
if signals is not None and not signals.empty:
    long_filled = signals[(signals["direction"] == "long") & (signals["status"].isin(["candidate", "filled"]))]
    short_filled = signals[(signals["direction"] == "short") & (signals["status"].isin(["candidate", "filled"]))]
    long_void = signals[(signals["direction"] == "long") & (signals["status"] == "void")]
    short_void = signals[(signals["direction"] == "short") & (signals["status"] == "void")]

    # Long active signals — triangle-up below the bar
    if not long_filled.empty:
        fig.add_trace(
            go.Scatter(
                x=long_filled["timestamp"],
                y=long_filled["entry_reference_price"],
                mode="markers",
                name="long (candidate/filled)",
                marker=dict(symbol="triangle-up", color="limegreen", size=10),
            )
        )

    # Short active signals — triangle-down above the bar
    if not short_filled.empty:
        fig.add_trace(
            go.Scatter(
                x=short_filled["timestamp"],
                y=short_filled["entry_reference_price"],
                mode="markers",
                name="short (candidate/filled)",
                marker=dict(symbol="triangle-down", color="tomato", size=10),
            )
        )

    # Void signals — crosses, muted
    if not long_void.empty:
        fig.add_trace(
            go.Scatter(
                x=long_void["timestamp"],
                y=long_void["entry_reference_price"],
                mode="markers",
                name="long void",
                marker=dict(symbol="x", color="mediumseagreen", size=8, opacity=0.4),
            )
        )
    if not short_void.empty:
        fig.add_trace(
            go.Scatter(
                x=short_void["timestamp"],
                y=short_void["entry_reference_price"],
                mode="markers",
                name="short void",
                marker=dict(symbol="x", color="salmon", size=8, opacity=0.4),
            )
        )

fig.update_layout(
    height=560,
    margin=dict(l=10, r=10, t=35, b=10),
    legend=dict(orientation="h"),
)
st.plotly_chart(fig, use_container_width=True)
