"""Shared Observatory constants and scalar helpers (C-24 / QI-07-07).

Join, desk, and lens modules import from here so the façade stays thin.
Does not import Streamlit, Plotly, ``execute``, or ``cli_study``.
Does not write study directories.
"""

from __future__ import annotations

import math
import numbers
import re
from typing import Any, Mapping

import pandas as pd

from thesistester.levels.catalog import PRIOR_PROFILE_LEVEL_NAMES
from thesistester.study.report import RESULTS_INDEX
from thesistester.study.viewer_catalog import STUDY_SPEC_FILENAME


EXPANSION_JSON = "study.expansion.json"

LEDGER_JSON = "study.ledger.json"

OBSERVATORY_HONESTY = (
    "Descriptive screen of completed study cells. Ranking many cells is "
    "multiple-testing, not a validated edge. Sort is within a comparability "
    "cohort unless you break the lock. Catalog membership is not a quality score."
)

SORT_ALLOW_LIST: frozenset[str] = frozenset(
    {
        "expectancy_r",
        "profit_factor",
        "win_rate",
        "trade_count",
        "max_drawdown_r",
        "study_name",
        "run_name",
        "status",
    }
)

_SORT_DESC_DEFAULT: frozenset[str] = frozenset(
    {"expectancy_r", "profit_factor", "win_rate", "trade_count"}
)

_SORT_ASC_DEFAULT: frozenset[str] = frozenset(
    {"max_drawdown_r", "study_name", "run_name", "status"}
)

COHORT_FIELDS: tuple[str, ...] = (
    "instrument",
    "dataset_id",
    "ingestion_mode",
    "commission_per_side",
    "slippage_ticks",
    "stop_loss_ticks",
    "take_profit_ticks",
    "trigger",
    "trigger_timeframe",
    "tolerance_ticks",
    "flat_by_session_close",
    "confluence_mode",
    "min_valid_confluences",
    "exposure_policy",
)

CLI_COLUMNS: tuple[str, ...] = (
    "study_name",
    "run_name",
    "instrument",
    "setup_kind",
    "trade_count",
    "expectancy_r",
    "profit_factor",
    "status",
    "sample_class",
)

LOCKED_FRAME_COLUMNS: tuple[str, ...] = (
    "study_dir",
    "study_name",
    "study_identity_hash",
    "run_name",
    "bundle_path",
    "status",
    "instrument",
    "dataset_id",
    "ingestion_mode",
    "trigger",
    "trigger_timeframe",
    "confluence_mode",
    "direction",
    "tolerance_ticks",
    "min_valid_confluences",
    "stop_loss_ticks",
    "take_profit_ticks",
    "commission_per_side",
    "slippage_ticks",
    "flat_by_session_close",
    "exposure_policy",
    "min_trades",
    "primary_metric",
    "lineage_parent",
    "lineage_admit_value",
    "factor_core_level",
    "factor_partner_levels",
    "trade_count",
    "long_trade_count",
    "short_trade_count",
    "long_share",
    "long_expectancy_r",
    "short_expectancy_r",
    "directional_integrity",
    "collision_pairs",
    "collision_resolved_long",
    "expectancy_r",
    "random_null_expectancy_r",
    "random_null_std_r",
    "random_p_value_ge",
    "expectancy_minus_null_r",
    "drift_class",
    "profit_factor",
    "win_rate",
    "max_drawdown_r",
    "total_r",
    "profit_factor_source",
    "factors_joined",
    "setup_kind",
    "sample_class",
    "cohort_key",
    "lens_hint",
)

STUDIES_COLUMNS: tuple[str, ...] = (
    "study_dir",
    "study_name",
    "study_identity_hash",
    "run_count",
    "ok",
    "failed",
    "skipped",
    "running",
    "pending",
    "ledger_present",
    "index_present",
    "error",
    "mtime",
)

STUDIES_TABLE_COLUMNS: tuple[str, ...] = (
    "study_name",
    "ok",
    "failed",
    "skipped",
    "running",
    "pending",
    "index_present",
    "ledger_present",
    "error",
    "study_dir",
)

_STAMP_FILES: tuple[str, ...] = (
    STUDY_SPEC_FILENAME,
    EXPANSION_JSON,
    RESULTS_INDEX,
    LEDGER_JSON,
)

_PROGB_NAME = re.compile(r"^progB_")

_PRIOR_PROFILE_CORES = frozenset(PRIOR_PROFILE_LEVEL_NAMES)

_WAVE0_SOLO = "progB_w0_solo"

_WAVE0_VA = "progB_w0_va"

_WAVE0_APOC = "progB_w0_apoc"

_WAVE0_STUDIES = frozenset({_WAVE0_SOLO, _WAVE0_VA, _WAVE0_APOC})

_RUN2_STUDY_PREFIX = "progB_r2_"

_APOC_CORES = frozenset({"APOC", "pAPOC"})

DESK_CLASS_ORDER: tuple[str, ...] = (
    "plus_e",
    "hold",
    "dead",
    "other",
    "noisy",
    "unidentified",
    "failed",
)

# Heatmap z: 0 = missing/pending (grey). failed is 1 so it is not grey.
HEATMAP_Z_MISSING = 0

HEATMAP_CLASS_Z: dict[str, int] = {
    "failed": 1,
    "unidentified": 2,
    "noisy": 3,
    "other": 4,
    "dead": 5,
    "hold": 6,
    "plus_e": 7,
}

HEATMAP_Z_MAX = 7

HEATMAP_SOLO_PARTNER = "(solo)"

# Lens chrome only — not ingest inventory (plan §4.6 / §6.4).
PROGRAM_B_LENS_PACKET_CHROME = (
    "15s operator packet: 20 files. Parked tick packet: 8 files "
    "(VA + APOC). These counts are lens chrome, not catalog membership."
)

_WAVE0_LOCK_FIELDS: tuple[str, ...] = tuple(
    field for field in COHORT_FIELDS if field != "min_valid_confluences"
)

_PF_HOLD_LO = 0.95

_PF_HOLD_HI = 1.05

_PLUS_E_MIN = 0.03

_USEFUL_DELTA_E = 0.03

_NOISY_MIN_TRADES = 15.0

DESK_SCHEMA_VERSION = 1

DESK_STORE_NAMESPACE = "study_observatory"

DESK_STORE_DIRNAME = "desks"

DESK_LENS_MODES: frozenset[str] = frozenset({"auto", "program_b", "generic"})

DESK_FACET_COLUMNS: tuple[str, ...] = (
    "instrument",
    "setup_kind",
    "factor_core_level",
    "factor_partner_levels",
    "study_name",
    "status",
    "sample_class",
    "directional_integrity",
    "drift_class",
    "stop_loss_ticks",
    "take_profit_ticks",
    "ingestion_mode",
    "desk_class",
    "useful_confluence",
)

LENS_FACET_COLUMNS: tuple[str, ...] = ("desk_class", "useful_confluence")

_DESK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,80}$")


class ObservatoryError(ValueError):
    """Raised when an Observatory helper receives an illegal argument."""


def cohort_key_from_values(values: Mapping[str, Any]) -> str:
    """Deterministic ``|``-joined cohort key (plan §4.5). Missing → empty token."""
    return "|".join(_cohort_token(values.get(field)) for field in COHORT_FIELDS)


def sample_class_for(trade_count: Any, min_trades: Any) -> str:
    """``missing_n`` / ``below_min_trades`` / ``interpretable`` (plan §4.4)."""
    count = _coerce_number(trade_count)
    if count is None:
        return "missing_n"
    gate = _coerce_number(min_trades)
    threshold = 30.0 if gate is None else float(gate)
    if count < threshold:
        return "below_min_trades"
    return "interpretable"


def setup_kind_for(*, trigger: Any, trigger_timeframe: Any, confluence_mode: Any) -> str:
    """Display/facet chip. Empty tokens stay empty (not inferred)."""
    return (
        f"{_display_token(trigger)}@{_display_token(trigger_timeframe)}/"
        f"{_display_token(confluence_mode)}"
    )


def lens_hint_for(*, study_name: str, has_admit_lineage: bool) -> str:
    """Best-effort program tag. Not a quality score."""
    if _PROGB_NAME.match(study_name or ""):
        return "program_b"
    if has_admit_lineage:
        return "admit_child"
    return "generic"


def _status_token(value: Any) -> str:
    if value is None or _is_na(value):
        return ""
    return str(value).strip().lower()


def canonical_facet_value(value: Any) -> Any:
    """Stable facet token. ``80`` / ``80.0`` / ``np.int64(80)`` → ``80``.

    Streamlit stringifies bool widget options; ``"True"`` / ``"False"``
    must match the Python bools ``useful_confluence`` stores.
    """
    if value is None or _is_na(value):
        return None
    if isinstance(value, bool):
        return value
    boxed = _box_scalar(value)
    if boxed is not value:
        return canonical_facet_value(boxed)
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number):
            return None
        if math.isfinite(number) and number.is_integer():
            return int(number)
        return number
    text = str(value).strip()
    if text in {"True", "False"}:
        return text == "True"
    return text if text else None


def classify_drift_class(p_value: Any) -> str:
    """DA5 desk facet. Derived at load; not persisted on the study index."""
    number = _coerce_number(p_value)
    if number is None:
        return "unknown"
    if number < 0.05:
        return "above_null"
    return "at_null"


def _error_text_present(value: Any) -> bool:
    if value is None or _is_na(value):
        return False
    token = str(value).strip()
    return token not in {"", "<NA>", "nan", "None"}


def _facet_sort_key(value: Any) -> tuple[int, float | str]:
    if isinstance(value, bool):
        return (2, "true" if value else "false")
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return (0, float(value))
    return (1, str(value))


def _singleton_factor(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            return None
        item = value[0]
        if isinstance(item, (list, tuple, dict)):
            return None
        return item
    if isinstance(value, dict) or value is None or _is_na(value):
        return None
    return value


def _joined_or_lock(flat: Mapping[str, Any], key: str, lock_value: Any) -> Any:
    """§4.4: joined ``factor_*`` if present, else exclusive spec value."""
    if key in flat:
        return flat.get(key)
    return lock_value


def _index_run_name(value: Any) -> Any:
    """Keep factor_map joins stable when pandas upcasts numeric run names."""
    if value is None or _is_na(value):
        return pd.NA
    boxed = _box_scalar(value)
    if boxed is None or _is_na(boxed):
        return pd.NA
    if isinstance(boxed, bool):
        return str(boxed)
    if isinstance(boxed, numbers.Real) and not isinstance(boxed, bool):
        number = float(boxed)
        if math.isnan(number):
            return pd.NA
        if number.is_integer():
            return str(int(number))
        return format(number, ".15g")
    text = str(boxed).strip()
    return text or pd.NA


def _box_scalar(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (bytes, str)):
        try:
            boxed = item()
            if boxed is not value:
                return boxed
        except (ValueError, TypeError, OverflowError, RecursionError):
            return value
    return value


def _coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if value is pd.NA or pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        number = float(value)
        if math.isnan(number):
            return None
        return number
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return None
        if text.lower() in {"inf", "+inf", "infinity"}:
            return float("inf")
        if text.lower() in {"-inf", "-infinity"}:
            return float("-inf")
        try:
            return float(text)
        except ValueError:
            return None
    boxed = _box_scalar(value)
    if boxed is not value:
        return _coerce_number(boxed)
    return None


def _is_na(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _cohort_token(value: Any) -> str:
    if value is None or _is_na(value):
        return ""
    boxed = _box_scalar(value)
    if boxed is not value:
        return _cohort_token(boxed)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        number = float(value)
        if math.isnan(number):
            return ""
        if number.is_integer():
            return str(int(number))
        return format(number, ".15g")
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _display_token(value: Any) -> str:
    if value is None or _is_na(value):
        return ""
    return str(value).strip()


def _cli_cell(value: Any) -> str:
    if value is None or _is_na(value):
        return "—"
    return str(value)


def _default_descending(column: str) -> bool:
    if column in _SORT_DESC_DEFAULT:
        return True
    if column in _SORT_ASC_DEFAULT:
        return False
    return False


def _sort_subset(
    frame: pd.DataFrame,
    columns: str | list[str],
    descending: bool,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    if isinstance(columns, list):
        keys = list(columns)
        ascending: bool | list[bool] = [True] * len(keys)
    else:
        keys = [columns]
        ascending = not descending
    return frame.sort_values(keys, ascending=ascending, na_position="last", kind="mergesort")
