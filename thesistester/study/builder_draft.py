"""StudyDraft dataclass, defaults, and session ser-de (C-24 / QI-07-07).

No Streamlit. ``emit_study_spec`` / ``hydrate_study_draft`` live in sibling
modules and import ``StudyDraft`` from here.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Mapping

from thesistester.data.derive import INGESTION_MODE_15S_PRIMARY_DERIVE_1M
from thesistester.study.schema import _WARNING_QUANTOWER_PRIMARY


STUDIES_BUILDER_DRAFT_KEY = "studies_builder_draft"

STUDIES_BUILDER_PENDING_SYNC_KEY = "studies_builder_pending_sync"

WIDGET_KEY_NAME = "_study_builder_name"

WIDGET_KEY_DESCRIPTION = "_study_builder_description"

WIDGET_KEY_OUTPUT_DIR = "_study_builder_output_dir"

WIDGET_KEY_WORKERS = "_study_builder_workers"

WIDGET_KEY_CONFIRM_ABOVE_RUNS = "_study_builder_confirm_above_runs"

WIDGET_KEY_DATASET_PATH = "_study_builder_dataset_path"

WIDGET_KEY_INSTRUMENT = "_study_builder_instrument"

WIDGET_KEY_SOURCE_TIMEZONE = "_study_builder_source_timezone"

WIDGET_KEY_FORMAT_PROFILE = "_study_builder_format_profile"

WIDGET_KEY_INGESTION_MODE = "_study_builder_ingestion_mode"

WIDGET_KEY_TICK_PATHS = "_study_builder_tick_paths"

DEFAULT_FORMAT_PROFILE = "canonical"

INGESTION_MODE_PRIMARY = "primary"

DEFAULT_NEW_DRAFT_DATASET_PATH = "data/mnq_15s.csv"

DEFAULT_NEW_DRAFT_FORMAT_PROFILE = "quantower_history_exporter"

DEFAULT_NEW_DRAFT_INSTRUMENT = "MNQ"

DEFAULT_NEW_DRAFT_SOURCE_TIMEZONE = "UTC"

_DERIVE_15S_SUPPORTED_PROFILES = frozenset({"quantower_history_exporter"})

_WARNING_15S_SL_FIRST = (
    "15s-primary attaches 15s for R12, but backtest.intrabar_model is sl_first "
    "(or omitted → sl_first). Data-page recommended model is subtimeframe_conservative."
)

_WARNING_GRID_SL_FIRST = (
    "grid.intrabar_model is sl_first (or omitted → sl_first) while backtest uses "
    "observed replay. Grid cells will not use the 15s R12 path."
)

WIDGET_KEY_CORE_LEVEL = "_study_builder_core_level"

WIDGET_KEY_CONFLUENCE_MODE = "_study_builder_confluence_mode"

WIDGET_KEY_TRIGGER = "_study_builder_trigger"

WIDGET_KEY_TRIGGER_TIMEFRAME = "_study_builder_trigger_timeframe"

WIDGET_KEY_OTF = "_study_builder_otf"

WIDGET_KEY_DIRECTION_MODE = "_study_builder_direction_mode"

WIDGET_KEY_DIRECTION_CONSTANT = "_study_builder_direction_constant"

WIDGET_KEY_DIRECTION_VALUES = "_study_builder_direction_values"

WIDGET_KEY_CONFLUENCE_GLOBAL = "_study_builder_confluence_global"

WIDGET_KEY_CONFLUENCE_ANCHOR = "_study_builder_confluence_anchor"

WIDGET_KEY_SMA_LENGTHS = "_study_builder_sma_lengths"

WIDGET_KEY_EMA_LENGTHS = "_study_builder_ema_lengths"

WIDGET_KEY_SMA_ADD_LENGTH = "_study_builder_sma_add_length"

WIDGET_KEY_EMA_ADD_LENGTH = "_study_builder_ema_add_length"

WIDGET_KEY_SMA_TF_MODE = "_study_builder_sma_tf_mode"

WIDGET_KEY_EMA_TF_MODE = "_study_builder_ema_tf_mode"

WIDGET_KEY_SMA_TIMEFRAMES = "_study_builder_sma_timeframes"

WIDGET_KEY_EMA_TIMEFRAMES = "_study_builder_ema_timeframes"

WIDGET_KEY_LEVELS_ADVANCED = "_study_builder_levels_advanced"

WIDGET_KEY_VWAP_WINDOWS = "_study_builder_vwap_windows"

WIDGET_KEY_POC_WINDOWS = "_study_builder_poc_windows"

WIDGET_KEY_PREV30M_ENABLED = "_study_builder_prev30m_enabled"

WIDGET_KEY_PIVOTS_ENABLED = "_study_builder_pivots_enabled"

WIDGET_KEY_PIVOT_TIMEFRAMES = "_study_builder_pivot_timeframes"

WIDGET_KEY_TOLERANCE_TICKS = "_study_builder_tolerance_ticks"

WIDGET_KEY_NAKED_ONLY = "_study_builder_naked_only"

WIDGET_KEY_NAKED_REQUIREMENT = "_study_builder_naked_requirement"

WIDGET_KEY_STOP_LOSS = "_study_builder_stop_loss"

WIDGET_KEY_TAKE_PROFIT = "_study_builder_take_profit"

WIDGET_KEY_COMMISSION = "_study_builder_commission"

WIDGET_KEY_SLIPPAGE = "_study_builder_slippage"

WIDGET_KEY_EXPOSURE_POLICY = "_study_builder_exposure_policy"

WIDGET_KEY_INTRABAR_MODEL = "_study_builder_intrabar_model"

WIDGET_KEY_FLAT_BY_SESSION_CLOSE = "_study_builder_flat_by_session_close"

WIDGET_KEY_BATTERY_GRID = "_study_builder_battery_grid"

WIDGET_KEY_BATTERY_VALIDATION = "_study_builder_battery_validation"

WIDGET_KEY_BATTERY_WALK_FORWARD = "_study_builder_battery_walk_forward"

WIDGET_KEY_GRID_SL_VALUES = "_study_builder_grid_sl_values"

WIDGET_KEY_GRID_TP_VALUES = "_study_builder_grid_tp_values"

WIDGET_KEY_MIN_CONFLUENCES = "_study_builder_min_confluences"

WIDGET_KEY_MAX_CONFLUENCES = "_study_builder_max_confluences"

WIDGET_KEY_MIN_VALID_CONFLUENCES = "_study_builder_min_valid_confluences"

WIDGET_KEY_FROM_PARTNERS = "_study_builder_from_partners"

WIDGET_KEY_STAGE_MODE = "_study_builder_stage_mode"

WIDGET_KEY_EXPLICIT_DELETE = "_study_builder_explicit_delete"

WIDGET_KEY_PRIMARY_METRIC = "_study_builder_primary_metric"

WIDGET_KEY_MIN_TRADES = "_study_builder_min_trades"

WIDGET_KEY_MULTIPLE_TESTING = "_study_builder_multiple_testing"

WIDGET_KEY_GROUP_BY = "_study_builder_group_by"

WIDGET_KEY_OTF_BASELINE = "_study_builder_otf_baseline"

STAGE_MODE_FULL = "Full cartesian"

STAGE_MODE_FILTER = "Filter"

STAGE_MODE_EXPLICIT = "Explicit cells"

STAGE_MODE_OPTIONS = (STAGE_MODE_FULL, STAGE_MODE_FILTER, STAGE_MODE_EXPLICIT)

PRIMARY_METRIC_OPTIONS = (
    "expectancy_r",
    "total_r",
    "max_drawdown_r",
    "trade_count",
    "profit_factor",
)

MULTIPLE_TESTING_OPTIONS = ("warn", "error")

PREFERRED_REPORT_GROUP_BY = (
    "partner_levels",
    "confluence_mode",
    "trigger",
    "trigger_timeframe",
    "otf",
)

COMMON_MA_LENGTHS = (9, 21, 50, 200)

TF_MODE_PRODUCT_DEFAULT = "Product default TFs"

TF_MODE_NO_MA = "No MA tokens"

TF_MODE_EXPLICIT = "Explicit TFs"

TF_MODE_OPTIONS = (TF_MODE_PRODUCT_DEFAULT, TF_MODE_NO_MA, TF_MODE_EXPLICIT)

DIRECTION_MODE_CONSTANT = "Constant"

DIRECTION_MODE_FACTOR = "Factor"

DIRECTION_MODE_OPTIONS = (DIRECTION_MODE_CONSTANT, DIRECTION_MODE_FACTOR)

_LEVELS_ADVANCED_KEYS = (
    "vwap_windows",
    "poc_windows",
    "prev30m_vwap_enabled",
    "pivots_enabled",
    "pivot_timeframes",
)

_REQUIRED_FACTOR_AXES = (
    "core_level",
    "partner_levels",
    "confluence_mode",
    "trigger",
    "trigger_timeframe",
)

_DATASET_KNOWN = (
    "path",
    "instrument",
    "source_timezone",
    "format_profile",
    "subtimeframe_path",
    "ingestion_mode",
    "tick_paths",
)

_LEVELS_NULL_FORBIDDEN = ("sma_timeframes", "ema_timeframes")

_BATTERY_KEYS = ("grid", "validation", "walk_forward")

_DEFAULT_OUTPUT_DIR_PREFIX = "results/studies/"

OTF_PRESET_ORDER = ("off", "5m", "15m", "30m", "combo")

OTF_PRESET_LABELS = {
    "off": "Off",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "combo": "5m+15m+30m",
}

OTF_PRESETS: dict[str, dict[str, Any]] = {
    "off": {"enabled": False},
    "5m": {
        "enabled": True,
        "timeframes": ["5m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
    },
    "15m": {
        "enabled": True,
        "timeframes": ["15m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
    },
    "30m": {
        "enabled": True,
        "timeframes": ["30m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
    },
    "combo": {
        "enabled": True,
        "timeframes": ["5m", "15m", "30m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
    },
}


def _default_levels() -> dict[str, Any]:
    return {
        "sma_lengths": [50],
        "ema_lengths": [21],
        "sma_timeframes": ["1min"],
        "ema_timeframes": ["1min"],
    }


def _default_backtest() -> dict[str, Any]:
    return {
        "stop_loss_ticks": 8,
        "take_profit_ticks": 16,
        "exposure_policy": "single_position",
        "commission_per_side": 0.0,
        "slippage_ticks": 0.0,
        "flat_by_session_close": False,
        "intrabar_model": "sl_first",
    }


def _default_battery() -> dict[str, Any]:
    return {"enabled": False}


def _default_secondary_metrics() -> list[str]:
    return ["profit_factor", "max_drawdown_r", "trade_count", "total_r"]


def _default_otf_baseline() -> dict[str, Any]:
    return {"enabled": False}


@dataclass
class StudyDraft:
    """Authoring state for a canonical ``schema_version: 1`` StudySpec."""

    name: str = "untitled_study"
    description: str | None = ""
    output_dir: str | None = None
    workers: int = 1
    confirm_above_runs: int = 200
    dataset_path: str = "data/es_1m.csv"
    instrument: str = "ES"
    source_timezone: str | None = "America/New_York"
    format_profile: str = DEFAULT_FORMAT_PROFILE
    ingestion_mode: str = INGESTION_MODE_PRIMARY
    subtimeframe_path: str | None = None
    tick_paths: list[str] = field(default_factory=list)
    dataset_extra: dict[str, Any] = field(default_factory=dict)
    levels: dict[str, Any] = field(default_factory=_default_levels)
    core_level: list[str] = field(default_factory=lambda: ["pdPOC"])
    partner_levels: list[list[str]] = field(default_factory=lambda: [["SMA_50_1min"]])
    confluence_mode: list[str] = field(default_factory=lambda: ["global_cluster", "anchor_rules"])
    trigger: list[str] = field(default_factory=lambda: ["touch"])
    trigger_timeframe: list[str] = field(default_factory=lambda: ["base"])
    otf: list[dict[str, Any]] | None = None
    direction_as_factor: bool = False
    direction_values: list[str] = field(default_factory=lambda: ["long", "short"])
    direction_constant: str = "both"
    tolerance_ticks: int | float = 0
    naked_only: bool = False
    naked_requirement: str = "any"
    min_confluences: int = 2
    max_confluences: int = 2
    min_valid_confluences: int = 1
    trigger_params: dict[str, Any] = field(default_factory=dict)
    entry_window: dict[str, Any] | None = None
    emit_entry_window: bool = False
    backtest: dict[str, Any] = field(default_factory=_default_backtest)
    grid: dict[str, Any] = field(default_factory=_default_battery)
    validation: dict[str, Any] = field(default_factory=_default_battery)
    walk_forward: dict[str, Any] = field(default_factory=_default_battery)
    from_partners: str = "required"
    primary_metric: str = "expectancy_r"
    secondary_metrics: list[str] = field(default_factory=_default_secondary_metrics)
    min_trades: int = 30
    group_by: list[str] | None = None
    emit_group_by: bool = False
    otf_baseline: dict[str, Any] = field(default_factory=_default_otf_baseline)
    multiple_testing: str = "warn"
    stage_mode: str | None = None
    stage_include: dict[str, list[Any]] = field(default_factory=dict)
    stage_cells: list[dict[str, Any]] = field(default_factory=list)
    lineage: dict[str, Any] | None = None


def normalize_builder_format_profile(value: Any) -> str:
    """Omitted / blank → ``canonical``. Non-blank tokens are stripped only.

    ``run_experiment`` defaults **omitted** keys to ``canonical``; a present
    unknown token is fail-closed at load time. Do not rewrite unknown tokens
    to ``canonical`` (that would invent a profile and silently parse as
    comma OHLCV). Emit rejects unknown non-blank tokens.
    """
    if value is None:
        return DEFAULT_FORMAT_PROFILE
    if isinstance(value, str):
        token = value.strip()
        if not token:
            return DEFAULT_FORMAT_PROFILE
        return token
    return DEFAULT_FORMAT_PROFILE


def default_study_draft() -> StudyDraft:
    """Return a valid 2-cell new draft on the recommended 15s-primary contract.

    ``StudyDraft()`` / ``_default_backtest()`` stay legacy-safe. Only this
    factory applies path / Quantower / ``15s_primary_derive_1m`` /
    ``subtimeframe_conservative``, plus the operator HE identity (MNQ, UTC)
    and usual costs. Cartesian stays 2 cells; ``workers`` stays 1.
    Tick paths stay empty: the farm remains 15s-only unless the operator
    attaches Quantower Tick–Tick–Last files.
    """
    backtest = _default_backtest()
    backtest["intrabar_model"] = "subtimeframe_conservative"
    backtest["stop_loss_ticks"] = 40
    backtest["take_profit_ticks"] = 80
    backtest["commission_per_side"] = 0.5
    backtest["slippage_ticks"] = 1.0
    return StudyDraft(
        dataset_path=DEFAULT_NEW_DRAFT_DATASET_PATH,
        instrument=DEFAULT_NEW_DRAFT_INSTRUMENT,
        source_timezone=DEFAULT_NEW_DRAFT_SOURCE_TIMEZONE,
        format_profile=DEFAULT_NEW_DRAFT_FORMAT_PROFILE,
        ingestion_mode=INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        core_level=["pRTH_Open"],
        tolerance_ticks=15,
        backtest=backtest,
    )


def _pop_extra_ingestion_mode(extra: dict[str, Any]) -> Any:
    """Promote a pre-SIA ``dataset_extra.ingestion_mode`` and drop the duplicate."""
    return extra.pop("ingestion_mode", None)


def normalize_tick_paths(value: Any) -> list[str]:
    """Coerce extra / widget / YAML tick paths to a de-duplicated string list."""
    if value is None:
        return []
    if isinstance(value, str):
        tokens: list[str] = []
        for line in value.replace(",", "\n").splitlines():
            token = line.strip()
            if token:
                tokens.append(token)
        return list(dict.fromkeys(tokens))
    if isinstance(value, (list, tuple)):
        tokens = []
        for item in value:
            token = str(item).strip()
            if token:
                tokens.append(token)
        return list(dict.fromkeys(tokens))
    token = str(value).strip()
    return [token] if token else []


def format_tick_paths_widget(paths: Any) -> str:
    """One path per line for the Studies Build tick-path textarea."""
    return "\n".join(normalize_tick_paths(paths))


def parse_tick_paths_widget(raw: Any) -> list[str]:
    """Parse the Studies Build tick-path textarea (newlines or commas)."""
    return normalize_tick_paths(raw)


def _pop_extra_tick_paths(extra: dict[str, Any]) -> Any:
    """Promote a pre-TV4 ``dataset_extra.tick_paths`` and drop the duplicate."""
    return extra.pop("tick_paths", None)


def _blank_ingestion_mode(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _resolved_ingestion_mode(value: Any, *, fallback: str = INGESTION_MODE_PRIMARY) -> str:
    if _blank_ingestion_mode(value):
        return fallback
    if isinstance(value, str):
        return value.strip()
    return str(value)


def draft_to_mapping(draft: StudyDraft) -> dict[str, Any]:
    """Serialize a draft for ``STUDIES_BUILDER_DRAFT_KEY`` (no Streamlit)."""
    return copy.deepcopy(asdict(draft))


def coerce_partner_levels(raw: Any) -> list[list[str]]:
    """Always return list-of-lists. A flat token list becomes one set."""
    if raw is None:
        return []
    if isinstance(raw, list) and raw and all(not isinstance(item, list) for item in raw):
        tokens = list(dict.fromkeys(str(item) for item in raw if str(item).strip()))
        return [tokens] if tokens else [[]]
    out: list[list[str]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, list):
                tokens = list(dict.fromkeys(str(token) for token in item if str(token).strip()))
                out.append(tokens)
            elif isinstance(item, str) and item.strip():
                out.append([item.strip()])
    return out


def draft_from_mapping(payload: Mapping[str, Any] | None) -> StudyDraft:
    """Rehydrate a ``StudyDraft`` from a session mapping."""
    if not isinstance(payload, Mapping):
        return default_study_draft()
    known = {item.name for item in fields(StudyDraft)}
    # Field defaults, not default_study_draft(): omitted keys must not inherit
    # MNQ / UTC / HE / pRTH / 15s-primary / operator costs.
    merged = asdict(StudyDraft())
    for key, value in payload.items():
        if key in known:
            merged[key] = copy.deepcopy(value)
    merged["partner_levels"] = coerce_partner_levels(merged.get("partner_levels"))
    for list_field in (
        "core_level",
        "confluence_mode",
        "trigger",
        "trigger_timeframe",
        "direction_values",
        "secondary_metrics",
    ):
        raw = merged.get(list_field)
        if not isinstance(raw, list):
            merged[list_field] = []
        else:
            merged[list_field] = [str(item) for item in raw]
    merged["format_profile"] = normalize_builder_format_profile(merged.get("format_profile"))
    if merged.get("otf") is not None and not isinstance(merged["otf"], list):
        merged["otf"] = None
    if not isinstance(merged.get("levels"), dict):
        merged["levels"] = _default_levels()
    if not isinstance(merged.get("backtest"), dict):
        merged["backtest"] = _default_backtest()
    for battery in _BATTERY_KEYS:
        if not isinstance(merged.get(battery), dict):
            merged[battery] = _default_battery()
    extra = merged.get("dataset_extra")
    if not isinstance(extra, dict):
        extra = {}
        merged["dataset_extra"] = extra
    extra_mode = _pop_extra_ingestion_mode(extra)
    if "ingestion_mode" not in payload or _blank_ingestion_mode(merged.get("ingestion_mode")):
        merged["ingestion_mode"] = _resolved_ingestion_mode(
            extra_mode, fallback=INGESTION_MODE_PRIMARY
        )
    else:
        merged["ingestion_mode"] = _resolved_ingestion_mode(merged.get("ingestion_mode"))
    extra_ticks = _pop_extra_tick_paths(extra)
    first_class_ticks = (
        normalize_tick_paths(merged.get("tick_paths")) if "tick_paths" in payload else []
    )
    merged["tick_paths"] = first_class_ticks or normalize_tick_paths(extra_ticks)
    return StudyDraft(**merged)


def draft_warnings(draft: StudyDraft) -> tuple[str, ...]:
    """Non-fatal authoring warnings. Emit still validates; tokens are not dropped."""
    warnings: list[str] = []
    cores = {str(token) for token in draft.core_level}
    for index, partner_set in enumerate(draft.partner_levels):
        overlap = cores.intersection(str(token) for token in partner_set)
        if overlap:
            warnings.append(f"partner_levels[{index}] intersects core_level: {sorted(overlap)}")
    if any(len(partner_set) == 0 for partner_set in draft.partner_levels):
        modes = [str(mode) for mode in draft.confluence_mode]
        try:
            min_valid = int(draft.min_valid_confluences)
        except (TypeError, ValueError):
            min_valid = 1
        if "global_cluster" in modes or min_valid != 0:
            warnings.append(
                "Empty partner set [] requires exclusive anchor_rules and min_valid_confluences=0."
            )
    mode = _resolved_ingestion_mode(draft.ingestion_mode)
    backtest = draft.backtest if isinstance(draft.backtest, Mapping) else {}
    backtest_model = backtest.get("intrabar_model")
    if mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M and backtest_model in (
        None,
        "",
        "sl_first",
    ):
        warnings.append(_WARNING_15S_SL_FIRST)
    profile = normalize_builder_format_profile(draft.format_profile)
    if mode == INGESTION_MODE_PRIMARY and profile == "quantower_history_exporter":
        warnings.append(_WARNING_QUANTOWER_PRIMARY)
    grid = draft.grid if isinstance(draft.grid, Mapping) else {}
    grid_model = grid.get("intrabar_model")
    if (
        grid.get("enabled") is True
        and grid_model in (None, "", "sl_first")
        and backtest_model in {"subtimeframe", "subtimeframe_conservative"}
    ):
        warnings.append(_WARNING_GRID_SL_FIRST)
    return tuple(warnings)


def _with_enabled(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(dict(mapping or {}))
    if "enabled" not in out:
        out["enabled"] = False
    return out


def _default_output_dir(name: str) -> str:
    return f"{_DEFAULT_OUTPUT_DIR_PREFIX}{name}"
