"""Research bundle export/import helpers."""

from __future__ import annotations

import io
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any, Mapping, NamedTuple

import pandas as pd

from thesistester import __version__
from thesistester.persistence.local_store import hash_dataframe
from thesistester.reporting import build_confluence_combo_bundle_artifacts
from thesistester.research_identity import (
    DataIdentity,
    LevelsIdentity,
    build_identity_metadata,
    identity_meta_filename,
)

BUNDLE_SCHEMA_VERSION = 1
BUNDLE_KIND = "thesistester_research_bundle"
MANIFEST_FILENAME = "manifest.json"
IDENTITY_META_FILENAME = identity_meta_filename()
# One-shot Data-page signal: drop leftover primary-CSV widget state so a
# prior Upload CSV value cannot replace the just-imported session dataset.
DATA_PAGE_INVALIDATE_SOURCE_KEY = "_data_page_invalidate_source"
# Skip saved-dataset bootstrap / sample auto-load after a dataset-less import
# so leftover active dataset A (or the Data-page sample) cannot refill
# ``data`` beside restored trades B. Cleared on Data-page successful load.
BUNDLE_IMPORT_OMITTED_DATA_KEY = "bundle_import_omitted_data"
# QI-06-09 / QR A-18: untrusted zip bound. Reject named members before
# ``ZipFile.read``. Not a hash gate (AH §2 item 8 — page 12 stays schema-only).
MAX_BUNDLE_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_BUNDLE_MEMBER_BYTES = 256 * 1024 * 1024


class BundleKeySpec(NamedTuple):
    """One bundle section: session keys, files, managed/hashed flags."""

    section: str
    meta_attr: str
    meta_keys: tuple[str, ...]
    session_keys: tuple[str, ...]
    required_files: tuple[str, ...]
    known_files: tuple[str, ...]
    managed: bool
    hashed: bool
    hash_exclude_files: tuple[str, ...]


_CONFLUENCE_COMBO_SUMMARY_KEY = "confluence_combo_summary"
_CONFLUENCE_COMBO_FRAME_KEYS = (
    "confluence_by_exact_combo",
    "confluence_by_level_count",
    "confluence_by_membership",
    "confluence_by_pairs",
)
_CONFLUENCE_COMBO_PARQUET_FILES = {
    "confluence_by_exact_combo": "confluence_by_exact_combo.parquet",
    "confluence_by_level_count": "confluence_by_level_count.parquet",
    "confluence_by_membership": "confluence_by_membership.parquet",
    "confluence_by_pairs": "confluence_by_pairs.parquet",
}
_CONFLUENCE_COMBO_FRAME_FROM_ARTIFACT = {
    "exact_combo": "confluence_by_exact_combo",
    "level_count": "confluence_by_level_count",
    "membership": "confluence_by_membership",
    "pairs": "confluence_by_pairs",
}

# Backtest page builds Admit from these Streamlit widget keys (not session
# ``entry_window`` alone). Cleared + rehydrated on bundle import (SW6).
_BACKTEST_ENTRY_WINDOW_WIDGET_KEYS = (
    "backtest_entry_window_enabled",
    "backtest_entry_window_mode",
    "backtest_entry_window_rth_segments",
    "backtest_entry_window_start_time",
    "backtest_entry_window_end_time",
    "backtest_entry_window_timezone",
)

BUNDLE_KEY_REGISTRY: tuple[BundleKeySpec, ...] = (
    BundleKeySpec(
        section="dataset",
        meta_attr="_DATASET_META_KEYS",
        meta_keys=(
            "dataset_id",
            "instrument",
            "base_interval",
            "source_timezone",
            "exchange_timezone",
            "format_profile",
        ),
        session_keys=(
            "data",
            "subtimeframe_data",
            "subtimeframe_interval",
            "subtimeframe_format_profile",
            "subtimeframe_fallback_parent_bars",
            "ingestion_provenance",
            "dataset_id",
            "instrument",
            "base_interval",
            "source_timezone",
            "exchange_timezone",
            "format_profile",
        ),
        required_files=("dataset.parquet", "dataset_meta.json"),
        known_files=(
            "dataset.parquet",
            "dataset_meta.json",
            "subtimeframe_data.parquet",
            "subtimeframe_meta.json",
        ),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="levels",
        meta_attr="_LEVELS_META_KEYS",
        meta_keys=("levels_settings", "levels_data_fingerprint"),
        session_keys=("levels", "session_levels", "levels_settings", "levels_data_fingerprint"),
        required_files=("levels.parquet", "session_levels.parquet", "levels_meta.json"),
        known_files=("levels.parquet", "session_levels.parquet", "levels_meta.json"),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="signals",
        meta_attr="_SIGNALS_META_KEYS",
        meta_keys=(
            "signal_context",
            "last_signal_setup",
            "signal_settings",
            "signal_settings_hash",
        ),
        session_keys=(
            "signals",
            "confluence_zones",
            "naked_flags",
            "signal_context",
            "last_signal_setup",
            "signal_settings",
            "signal_settings_hash",
        ),
        required_files=(
            "signals.parquet",
            "confluence_zones.parquet",
            "naked_flags.parquet",
            "signals_meta.json",
        ),
        known_files=(
            "signals.parquet",
            "confluence_zones.parquet",
            "naked_flags.parquet",
            "signals_meta.json",
        ),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="backtest",
        meta_attr="_BACKTEST_META_KEYS",
        meta_keys=(
            "trade_summary",
            "backtest_intrabar_policy",
            "backtest_intrabar_diagnostic",
            "backtest_exit_management_policy",
            "backtest_exit_management_diagnostic",
            "backtest_execution_costs",
            "exposure_policy",
            "backtest_session_exit_policy",
            "backtest_config",
            "entry_window",
            "entry_window_armed",
            "entry_window_promote_provenance",
            "focus_entry_window",
            "focus_provenance",
            "focused_trade_summary",
        ),
        session_keys=(
            "trades",
            "equity_curve",
            "trade_summary",
            "backtest_intrabar_policy",
            "backtest_intrabar_diagnostic",
            "backtest_exit_management_policy",
            "backtest_exit_management_diagnostic",
            "backtest_execution_costs",
            "exposure_policy",
            "backtest_session_exit_policy",
            "backtest_config",
            "entry_window",
            "entry_window_armed",
            "entry_window_promote_provenance",
            "focus_entry_window",
            "focus_provenance",
            "focused_trade_summary",
        ),
        required_files=("trades.parquet", "trade_summary.json", "equity_curve.parquet"),
        known_files=("trades.parquet", "trade_summary.json", "equity_curve.parquet"),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="grid",
        meta_attr="_GRID_META_KEYS",
        meta_keys=(
            "best_grid_result",
            "grid_intrabar_policy",
            "grid_exit_management_policy",
            "grid_entry_window",
        ),
        session_keys=(
            "grid_results",
            "best_grid_result",
            "grid_intrabar_policy",
            "grid_exit_management_policy",
            "grid_entry_window",
        ),
        required_files=("grid_results.parquet", "best_grid_result.json"),
        known_files=("grid_results.parquet", "best_grid_result.json"),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="validation",
        meta_attr="_VALIDATION_META_KEYS",
        meta_keys=("validation_summary",),
        session_keys=("validation_summary",),
        required_files=("validation_summary.json",),
        known_files=("validation_summary.json",),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="walk_forward",
        meta_attr="_WFA_META_KEYS",
        meta_keys=(
            "walk_forward_summary",
            "walk_forward_config",
            "walk_forward_otf_filter",
            "walk_forward_warnings",
            "wfa_matrix_config",
        ),
        session_keys=(
            "walk_forward_results",
            "walk_forward_summary",
            "walk_forward_config",
            "walk_forward_otf_filter",
            "walk_forward_oos_trades",
            "walk_forward_stitched_equity",
            "walk_forward_warnings",
            "wfa_matrix",
            "wfa_matrix_config",
        ),
        required_files=("walk_forward_results.parquet", "walk_forward_meta.json"),
        known_files=(
            "walk_forward_results.parquet",
            "walk_forward_oos_trades.parquet",
            "walk_forward_stitched_equity.parquet",
            "wfa_matrix.parquet",
            "walk_forward_meta.json",
        ),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="excursion",
        meta_attr="_EXCURSION_META_KEYS",
        meta_keys=("excursion_summary", "excursion_config"),
        session_keys=(
            "excursion_summary",
            "excursion_config",
            "excursion_grouped_summary",
            "excursion_calibration_grid",
            "excursion_quadrant_summary",
        ),
        required_files=("excursion_summary.json",),
        known_files=(
            "excursion_summary.json",
            "excursion_grouped_summary.parquet",
            "excursion_calibration_grid.parquet",
            "excursion_quadrant_summary.parquet",
        ),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="monte_carlo",
        meta_attr="_MONTE_CARLO_META_KEYS",
        meta_keys=("monte_carlo_summary", "monte_carlo_config"),
        session_keys=("monte_carlo_summary", "monte_carlo_config"),
        required_files=("monte_carlo_summary.json",),
        known_files=("monte_carlo_summary.json",),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="noise",
        meta_attr="_NOISE_META_KEYS",
        meta_keys=("noise_summary", "noise_config"),
        session_keys=("noise_summary", "noise_config"),
        required_files=("noise_summary.json",),
        known_files=("noise_summary.json",),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="overfitting",
        meta_attr="_OVERFITTING_META_KEYS",
        meta_keys=("overfitting_summary", "overfitting_config"),
        session_keys=("overfitting_summary", "overfitting_config"),
        required_files=("overfitting_summary.json",),
        known_files=("overfitting_summary.json",),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="sensitivity",
        meta_attr="_SENSITIVITY_META_KEYS",
        meta_keys=("sensitivity_summary", "sensitivity_config"),
        session_keys=("sensitivity_summary", "sensitivity_config"),
        required_files=("sensitivity_summary.json",),
        known_files=("sensitivity_summary.json",),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="portfolio",
        meta_attr="_PORTFOLIO_META_KEYS",
        meta_keys=("portfolio_summary", "portfolio_config", "portfolio_setup_inputs"),
        session_keys=(
            "portfolio_summary",
            "portfolio_config",
            "portfolio_setup_inputs",
            "portfolio_trades",
            "portfolio_skipped_trades",
            "portfolio_equity_curve",
            "portfolio_correlation",
            "portfolio_drawdown_correlation",
            "portfolio_marginal_contribution",
        ),
        required_files=("portfolio_summary.json", "portfolio_trades.parquet"),
        known_files=(
            "portfolio_summary.json",
            "portfolio_trades.parquet",
            "portfolio_skipped_trades.parquet",
            "portfolio_equity_curve.parquet",
            "portfolio_correlation.parquet",
            "portfolio_drawdown_correlation.parquet",
            "portfolio_marginal_contribution.parquet",
        ),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="confluence_combo",
        meta_attr="",
        meta_keys=(),
        session_keys=(_CONFLUENCE_COMBO_SUMMARY_KEY, *_CONFLUENCE_COMBO_FRAME_KEYS),
        required_files=("confluence_combo_summary.json",),
        known_files=(
            "confluence_combo_summary.json",
            "confluence_by_exact_combo.parquet",
            "confluence_by_level_count.parquet",
            "confluence_by_membership.parquet",
            "confluence_by_pairs.parquet",
        ),
        managed=True,
        hashed=False,
        hash_exclude_files=(
            "confluence_combo_summary.json",
            "confluence_by_exact_combo.parquet",
            "confluence_by_level_count.parquet",
            "confluence_by_membership.parquet",
            "confluence_by_pairs.parquet",
        ),
    ),
    BundleKeySpec(
        section="identity",
        meta_attr="",
        meta_keys=(),
        session_keys=("data_identity", "levels_identity"),
        required_files=(),
        known_files=(IDENTITY_META_FILENAME,),
        managed=True,
        hashed=True,
        hash_exclude_files=(),
    ),
    BundleKeySpec(
        section="clear_only",
        meta_attr="",
        meta_keys=(),
        session_keys=(
            "otf_filter_summary",
            "otf_filter_result",
            "backtest_otf_filter",
            "grid_otf_filter",
            "otf_rejected_signals",
            "otf_candidate_signals",
            "otf_accepted_signals",
            "setup_config",
            "focused_trades",
            "focused_equity_curve",
            "otf_validation_matrix",
            "otf_validation_config",
            "otf_validation_summary",
            "skipped_signals",
            "direction_collision_diagnostic",
            "display_timezone",
            "time_bucketed_trades",
            "time_grouped_summary",
            "experiment_identity",
            "execution_origin",
            "cache_provenance",
        ),
        required_files=(),
        known_files=(),
        managed=True,
        hashed=False,
        hash_exclude_files=(),
    ),
)
BUNDLE_KEY_REGISTRY_NAMES: tuple[str, ...] = tuple(spec.section for spec in BUNDLE_KEY_REGISTRY)


def _spec_meta(attr: str) -> tuple[str, ...]:
    return next(spec.meta_keys for spec in BUNDLE_KEY_REGISTRY if spec.meta_attr == attr)


_DATASET_META_KEYS = _spec_meta("_DATASET_META_KEYS")
_LEVELS_META_KEYS = _spec_meta("_LEVELS_META_KEYS")
_SIGNALS_META_KEYS = _spec_meta("_SIGNALS_META_KEYS")
_BACKTEST_META_KEYS = _spec_meta("_BACKTEST_META_KEYS")
_GRID_META_KEYS = _spec_meta("_GRID_META_KEYS")
_VALIDATION_META_KEYS = _spec_meta("_VALIDATION_META_KEYS")
_WFA_META_KEYS = _spec_meta("_WFA_META_KEYS")
_EXCURSION_META_KEYS = _spec_meta("_EXCURSION_META_KEYS")
_MONTE_CARLO_META_KEYS = _spec_meta("_MONTE_CARLO_META_KEYS")
_NOISE_META_KEYS = _spec_meta("_NOISE_META_KEYS")
_OVERFITTING_META_KEYS = _spec_meta("_OVERFITTING_META_KEYS")
_SENSITIVITY_META_KEYS = _spec_meta("_SENSITIVITY_META_KEYS")
_PORTFOLIO_META_KEYS = _spec_meta("_PORTFOLIO_META_KEYS")

_MANAGED_RESEARCH_KEYS = {
    key for spec in BUNDLE_KEY_REGISTRY if spec.managed for key in spec.session_keys
}
_KNOWN_FILES = {
    MANIFEST_FILENAME,
    *(name for spec in BUNDLE_KEY_REGISTRY for name in spec.known_files),
}
_SECTION_REQUIRED_FILES = {
    spec.section: spec.required_files for spec in BUNDLE_KEY_REGISTRY if spec.required_files
}
# Optional confluence combo siblings are deterministic projections of trades.
# Exclude them from the canonical hash so legacy golden bundle hashes stay
# stable without a GOLDEN_REGEN.
_CANONICAL_HASH_EXCLUDED_FILES = frozenset(
    name for spec in BUNDLE_KEY_REGISTRY for name in spec.hash_exclude_files
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return [
            {str(k): _normalize_json_value(v) for k, v in row.items()}
            for row in value.to_dict(orient="records")
        ]

    if isinstance(value, pd.Series):
        return {str(k): _normalize_json_value(v) for k, v in value.to_dict().items()}

    if isinstance(value, pd.Index):
        return [_normalize_json_value(item) for item in value.tolist()]

    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            value = value.item()
        except (AttributeError, ValueError, TypeError):
            pass

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, dict):
        return {str(k): _normalize_json_value(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_normalize_json_value(item) for item in value]

    if value is None or isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        return None if pd.isna(value) else value

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return str(value)


def _to_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        _normalize_json_value(payload),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")


def _to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    return buffer.getvalue()


def _parquet_safe_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy whose object columns are pyarrow-writable.

    View-C ``level_count_bucket`` mixes ints with ``"(unknown)"``; pyarrow
    rejects that object column. Stringify mixed / non-str object values so
    optional confluence parquet siblings cannot take down bundle export.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        series = out[col]
        if series.dtype != object:
            continue

        def _is_null(value: Any) -> bool:
            if value is None or value is pd.NA or value is pd.NaT:
                return True
            try:
                result = pd.isna(value)
            except (TypeError, ValueError):
                return False
            return bool(result) if isinstance(result, bool) else False

        non_null_values = [value for value in series.tolist() if not _is_null(value)]
        if not non_null_values:
            continue
        types = {type(value) for value in non_null_values}
        if types <= {str}:
            continue
        out[col] = series.map(lambda value: value if _is_null(value) else str(value))
    return out


# Optional confluence combo siblings are deterministic projections of trades (+
# signal-run identity). Exclude them from the canonical hash so legacy golden
# bundle hashes stay stable without a GOLDEN_REGEN, while still shipping the
# optional files for import/preview. Manifest ``included.confluence_combo`` is
# also stripped from the hashed manifest projection for the same reason.
_CANONICAL_HASH_EXCLUDED_FILES = frozenset(
    {
        "confluence_combo_summary.json",
        *_CONFLUENCE_COMBO_PARQUET_FILES.values(),
    }
)


def canonical_bundle_hash(bundle_bytes: bytes) -> str:
    """Hash logical bundle contents while excluding archive/time metadata.

    Parquet members are projected through the repository's deterministic
    DataFrame hash. JSON members are normalized with sorted keys, and the
    nondeterministic manifest ``created_at`` field is omitted.
    """
    member_hashes: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as archive:
        for name in sorted(archive.namelist()):
            if name in _CANONICAL_HASH_EXCLUDED_FILES:
                continue
            payload = archive.read(name)
            if name.endswith(".parquet"):
                frame = pd.read_parquet(io.BytesIO(payload))
                digest = hash_dataframe(frame)
            elif name.endswith(".json"):
                value = json.loads(payload.decode("utf-8"))
                if name == MANIFEST_FILENAME and isinstance(value, dict):
                    value = dict(value)
                    value.pop("created_at", None)
                    included = value.get("included")
                    if isinstance(included, dict) and "confluence_combo" in included:
                        included = dict(included)
                        included.pop("confluence_combo", None)
                        value["included"] = included
                    session_keys = value.get("session_keys")
                    if isinstance(session_keys, list):
                        value["session_keys"] = sorted(
                            key
                            for key in session_keys
                            if key != _CONFLUENCE_COMBO_SUMMARY_KEY
                            and key not in _CONFLUENCE_COMBO_FRAME_KEYS
                        )
                normalized = json.dumps(
                    value,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                digest = hashlib.sha256(normalized).hexdigest()
            else:
                digest = hashlib.sha256(payload).hexdigest()
            member_hashes[name] = digest
    projection = json.dumps(
        member_hashes,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(projection).hexdigest()


def _is_dataframe(value: Any) -> bool:
    return isinstance(value, pd.DataFrame)


def _manifest_base() -> dict[str, Any]:
    return {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "created_at": _utcnow_iso(),
        "app_version": __version__,
        "included": {
            "dataset": False,
            "levels": False,
            "signals": False,
            "backtest": False,
            "grid": False,
            "validation": False,
            "excursion": False,
            "monte_carlo": False,
        },
        "session_keys": [],
    }


class _BundleBuildCtx:
    __slots__ = ("session_state", "files", "manifest", "included_keys")

    def __init__(self, session_state: Mapping[str, Any]) -> None:
        self.session_state = session_state
        self.files: dict[str, bytes] = {}
        self.manifest = _manifest_base()
        self.included_keys: set[str] = set()


class _BundleLoadCtx:
    __slots__ = ("zf", "names", "included", "session_values")

    def __init__(
        self,
        zf: zipfile.ZipFile,
        names: set[str],
        included: Mapping[str, Any],
    ) -> None:
        self.zf = zf
        self.names = names
        self.included = included
        self.session_values: dict[str, Any] = {}


class BundleSectionIO(NamedTuple):
    """Build/load pair for one exportable bundle section."""

    section: str
    build: Callable[[_BundleBuildCtx], None]
    load: Callable[[_BundleLoadCtx], None]


def _mark_included(ctx: _BundleBuildCtx, section: str) -> None:
    ctx.manifest["included"][section] = True


def _copy_present_meta(session_state: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: session_state.get(key) for key in keys if key in session_state}


def _restore_present_meta(
    session_values: dict[str, Any], meta: Mapping[str, Any], keys: tuple[str, ...]
) -> None:
    for key in keys:
        if key in meta:
            session_values[key] = meta[key]


def _build_dataset_section(ctx: _BundleBuildCtx) -> None:
    session_state = ctx.session_state
    data = session_state.get("data")
    if not _is_dataframe(data):
        return
    ctx.files["dataset.parquet"] = _to_parquet_bytes(data)
    # format_profile is additive: omit when absent so pre-CAI-1 / golden
    # dataset_meta projections (and their canonical hashes) stay unchanged.
    dataset_meta = {
        key: session_state.get(key)
        for key in _DATASET_META_KEYS
        if key != "format_profile" or session_state.get("format_profile") is not None
    }
    ctx.files["dataset_meta.json"] = _to_json_bytes(dataset_meta)
    _mark_included(ctx, "dataset")
    ctx.included_keys.update({"data", *dataset_meta.keys()})
    subtimeframe_data = session_state.get("subtimeframe_data")
    if not _is_dataframe(subtimeframe_data):
        return
    ctx.files["subtimeframe_data.parquet"] = _to_parquet_bytes(subtimeframe_data)
    subtimeframe_meta: dict[str, Any] = {
        "subtimeframe_interval": session_state.get("subtimeframe_interval"),
        "subtimeframe_fallback_parent_bars": session_state.get("subtimeframe_fallback_parent_bars"),
        "subtimeframe_duplicate_resolution": session_state.get("subtimeframe_duplicate_resolution"),
    }
    if session_state.get("subtimeframe_format_profile") is not None:
        subtimeframe_meta["subtimeframe_format_profile"] = session_state.get(
            "subtimeframe_format_profile"
        )
    provenance = session_state.get("ingestion_provenance")
    if isinstance(provenance, Mapping):
        subtimeframe_meta["ingestion_provenance"] = dict(provenance)
    ctx.files["subtimeframe_meta.json"] = _to_json_bytes(subtimeframe_meta)
    ctx.included_keys.update(
        {
            "subtimeframe_data",
            "subtimeframe_interval",
            "subtimeframe_format_profile",
            "ingestion_provenance",
        }
    )


def _load_dataset_section(ctx: _BundleLoadCtx) -> None:
    session_values = ctx.session_values
    session_values["data"] = _read_parquet_from_zip(ctx.zf, "dataset.parquet")
    dataset_meta = _read_json_from_zip(ctx.zf, "dataset_meta.json")
    _restore_present_meta(session_values, dataset_meta, _DATASET_META_KEYS)
    if "subtimeframe_data.parquet" not in ctx.names:
        return
    session_values["subtimeframe_data"] = _read_parquet_from_zip(
        ctx.zf, "subtimeframe_data.parquet"
    )
    subtimeframe_meta = _read_json_from_zip(ctx.zf, "subtimeframe_meta.json")
    if "subtimeframe_interval" in subtimeframe_meta:
        session_values["subtimeframe_interval"] = subtimeframe_meta["subtimeframe_interval"]
    if "subtimeframe_fallback_parent_bars" in subtimeframe_meta:
        session_values["subtimeframe_fallback_parent_bars"] = subtimeframe_meta[
            "subtimeframe_fallback_parent_bars"
        ]
    if "subtimeframe_duplicate_resolution" in subtimeframe_meta:
        session_values["subtimeframe_duplicate_resolution"] = subtimeframe_meta[
            "subtimeframe_duplicate_resolution"
        ]
    if "subtimeframe_format_profile" in subtimeframe_meta:
        session_values["subtimeframe_format_profile"] = subtimeframe_meta[
            "subtimeframe_format_profile"
        ]
    provenance = subtimeframe_meta.get("ingestion_provenance")
    if isinstance(provenance, Mapping):
        session_values["ingestion_provenance"] = dict(provenance)


def _build_levels_section(ctx: _BundleBuildCtx) -> None:
    session_state = ctx.session_state
    levels = session_state.get("levels")
    session_levels = session_state.get("session_levels")
    if not (_is_dataframe(levels) and _is_dataframe(session_levels)):
        return
    ctx.files["levels.parquet"] = _to_parquet_bytes(levels)
    ctx.files["session_levels.parquet"] = _to_parquet_bytes(session_levels)
    ctx.files["levels_meta.json"] = _to_json_bytes(
        {key: session_state.get(key) for key in _LEVELS_META_KEYS}
    )
    _mark_included(ctx, "levels")
    ctx.included_keys.update({"levels", "session_levels", *_LEVELS_META_KEYS})


def _load_levels_section(ctx: _BundleLoadCtx) -> None:
    ctx.session_values["levels"] = _read_parquet_from_zip(ctx.zf, "levels.parquet")
    ctx.session_values["session_levels"] = _read_parquet_from_zip(ctx.zf, "session_levels.parquet")
    levels_meta = _read_json_from_zip(ctx.zf, "levels_meta.json")
    _restore_present_meta(ctx.session_values, levels_meta, _LEVELS_META_KEYS)


def _build_signals_section(ctx: _BundleBuildCtx) -> None:
    session_state = ctx.session_state
    signals = session_state.get("signals")
    confluence_zones = session_state.get("confluence_zones")
    naked_flags = session_state.get("naked_flags")
    if not (
        _is_dataframe(signals) and _is_dataframe(confluence_zones) and _is_dataframe(naked_flags)
    ):
        return
    ctx.files["signals.parquet"] = _to_parquet_bytes(signals)
    ctx.files["confluence_zones.parquet"] = _to_parquet_bytes(confluence_zones)
    ctx.files["naked_flags.parquet"] = _to_parquet_bytes(naked_flags)
    ctx.files["signals_meta.json"] = _to_json_bytes(
        {key: session_state.get(key) for key in _SIGNALS_META_KEYS}
    )
    _mark_included(ctx, "signals")
    ctx.included_keys.update({"signals", "confluence_zones", "naked_flags", *_SIGNALS_META_KEYS})


def _load_signals_section(ctx: _BundleLoadCtx) -> None:
    ctx.session_values["signals"] = _read_parquet_from_zip(ctx.zf, "signals.parquet")
    ctx.session_values["confluence_zones"] = _read_parquet_from_zip(
        ctx.zf, "confluence_zones.parquet"
    )
    ctx.session_values["naked_flags"] = _read_parquet_from_zip(ctx.zf, "naked_flags.parquet")
    signals_meta = _read_json_from_zip(ctx.zf, "signals_meta.json")
    _restore_present_meta(ctx.session_values, signals_meta, _SIGNALS_META_KEYS)


def _build_backtest_section(ctx: _BundleBuildCtx) -> None:
    session_state = ctx.session_state
    trades = session_state.get("trades")
    equity_curve = session_state.get("equity_curve")
    if not (_is_dataframe(trades) and _is_dataframe(equity_curve)):
        return
    ctx.files["trades.parquet"] = _to_parquet_bytes(trades)
    ctx.files["equity_curve.parquet"] = _to_parquet_bytes(equity_curve)
    ctx.files["trade_summary.json"] = _to_json_bytes(
        _copy_present_meta(session_state, _BACKTEST_META_KEYS)
    )
    _mark_included(ctx, "backtest")
    ctx.included_keys.update({"trades", "equity_curve"})
    ctx.included_keys.update(key for key in _BACKTEST_META_KEYS if key in session_state)


def _load_backtest_section(ctx: _BundleLoadCtx) -> None:
    ctx.session_values["trades"] = _read_parquet_from_zip(ctx.zf, "trades.parquet")
    ctx.session_values["equity_curve"] = _read_parquet_from_zip(ctx.zf, "equity_curve.parquet")
    backtest_meta = _read_json_from_zip(ctx.zf, "trade_summary.json")
    _restore_present_meta(ctx.session_values, backtest_meta, _BACKTEST_META_KEYS)


def _build_grid_section(ctx: _BundleBuildCtx) -> None:
    session_state = ctx.session_state
    grid_results = session_state.get("grid_results")
    if not _is_dataframe(grid_results):
        return
    ctx.files["grid_results.parquet"] = _to_parquet_bytes(grid_results)
    ctx.files["best_grid_result.json"] = _to_json_bytes(
        _copy_present_meta(session_state, _GRID_META_KEYS)
    )
    _mark_included(ctx, "grid")
    ctx.included_keys.add("grid_results")
    ctx.included_keys.update(key for key in _GRID_META_KEYS if key in session_state)


def _load_grid_section(ctx: _BundleLoadCtx) -> None:
    ctx.session_values["grid_results"] = _read_parquet_from_zip(ctx.zf, "grid_results.parquet")
    grid_meta = _read_json_from_zip(ctx.zf, "best_grid_result.json")
    _restore_present_meta(ctx.session_values, grid_meta, _GRID_META_KEYS)


def _build_validation_section(ctx: _BundleBuildCtx) -> None:
    session_state = ctx.session_state
    if session_state.get("validation_summary") is None:
        return
    ctx.files["validation_summary.json"] = _to_json_bytes(
        {"validation_summary": session_state.get("validation_summary")}
    )
    _mark_included(ctx, "validation")
    ctx.included_keys.update(_VALIDATION_META_KEYS)


def _load_validation_section(ctx: _BundleLoadCtx) -> None:
    validation_meta = _read_json_from_zip(ctx.zf, "validation_summary.json")
    if "validation_summary" in validation_meta:
        ctx.session_values["validation_summary"] = validation_meta["validation_summary"]


def _build_walk_forward_section(ctx: _BundleBuildCtx) -> None:
    session_state = ctx.session_state
    walk_forward_results = session_state.get("walk_forward_results")
    if not _is_dataframe(walk_forward_results):
        return
    ctx.files["walk_forward_results.parquet"] = _to_parquet_bytes(walk_forward_results)
    ctx.files["walk_forward_meta.json"] = _to_json_bytes(
        _copy_present_meta(session_state, _WFA_META_KEYS)
    )
    for key, filename in (
        ("walk_forward_oos_trades", "walk_forward_oos_trades.parquet"),
        (
            "walk_forward_stitched_equity",
            "walk_forward_stitched_equity.parquet",
        ),
        ("wfa_matrix", "wfa_matrix.parquet"),
    ):
        value = session_state.get(key)
        if _is_dataframe(value):
            ctx.files[filename] = _to_parquet_bytes(value)
            ctx.included_keys.add(key)
    _mark_included(ctx, "walk_forward")
    ctx.included_keys.add("walk_forward_results")
    ctx.included_keys.update(key for key in _WFA_META_KEYS if key in session_state)


def _load_walk_forward_section(ctx: _BundleLoadCtx) -> None:
    ctx.session_values["walk_forward_results"] = _read_parquet_from_zip(
        ctx.zf, "walk_forward_results.parquet"
    )
    walk_forward_meta = _read_json_from_zip(ctx.zf, "walk_forward_meta.json")
    _restore_present_meta(ctx.session_values, walk_forward_meta, _WFA_META_KEYS)
    for key, filename in (
        ("walk_forward_oos_trades", "walk_forward_oos_trades.parquet"),
        (
            "walk_forward_stitched_equity",
            "walk_forward_stitched_equity.parquet",
        ),
        ("wfa_matrix", "wfa_matrix.parquet"),
    ):
        if filename in ctx.names:
            ctx.session_values[key] = _read_parquet_from_zip(ctx.zf, filename)


def _build_excursion_section(ctx: _BundleBuildCtx) -> None:
    session_state = ctx.session_state
    if session_state.get("excursion_summary") is None:
        return
    ctx.files["excursion_summary.json"] = _to_json_bytes(
        {key: session_state.get(key) for key in _EXCURSION_META_KEYS}
    )
    excursion_grouped = session_state.get("excursion_grouped_summary")
    if _is_dataframe(excursion_grouped):
        ctx.files["excursion_grouped_summary.parquet"] = _to_parquet_bytes(excursion_grouped)
        ctx.included_keys.add("excursion_grouped_summary")
    excursion_calibration = session_state.get("excursion_calibration_grid")
    if _is_dataframe(excursion_calibration):
        ctx.files["excursion_calibration_grid.parquet"] = _to_parquet_bytes(excursion_calibration)
        ctx.included_keys.add("excursion_calibration_grid")
    excursion_quadrants = session_state.get("excursion_quadrant_summary")
    if _is_dataframe(excursion_quadrants):
        ctx.files["excursion_quadrant_summary.parquet"] = _to_parquet_bytes(excursion_quadrants)
        ctx.included_keys.add("excursion_quadrant_summary")
    _mark_included(ctx, "excursion")
    ctx.included_keys.update(_EXCURSION_META_KEYS)


def _load_excursion_section(ctx: _BundleLoadCtx) -> None:
    excursion_meta = _read_json_from_zip(ctx.zf, "excursion_summary.json")
    _restore_present_meta(ctx.session_values, excursion_meta, _EXCURSION_META_KEYS)
    if "excursion_grouped_summary.parquet" in ctx.names:
        ctx.session_values["excursion_grouped_summary"] = _read_parquet_from_zip(
            ctx.zf, "excursion_grouped_summary.parquet"
        )
    if "excursion_calibration_grid.parquet" in ctx.names:
        ctx.session_values["excursion_calibration_grid"] = _read_parquet_from_zip(
            ctx.zf, "excursion_calibration_grid.parquet"
        )
    if "excursion_quadrant_summary.parquet" in ctx.names:
        ctx.session_values["excursion_quadrant_summary"] = _read_parquet_from_zip(
            ctx.zf, "excursion_quadrant_summary.parquet"
        )


def _build_json_summary_section(
    ctx: _BundleBuildCtx,
    section: str,
    summary_key: str,
    filename: str,
    meta_keys: tuple[str, ...],
) -> None:
    if ctx.session_state.get(summary_key) is None:
        return
    ctx.files[filename] = _to_json_bytes({key: ctx.session_state.get(key) for key in meta_keys})
    _mark_included(ctx, section)
    ctx.included_keys.update(meta_keys)


def _load_json_summary_section(
    ctx: _BundleLoadCtx, filename: str, meta_keys: tuple[str, ...]
) -> None:
    meta = _read_json_from_zip(ctx.zf, filename)
    _restore_present_meta(ctx.session_values, meta, meta_keys)


def _build_monte_carlo_section(ctx: _BundleBuildCtx) -> None:
    _build_json_summary_section(
        ctx,
        "monte_carlo",
        "monte_carlo_summary",
        "monte_carlo_summary.json",
        _MONTE_CARLO_META_KEYS,
    )


def _load_monte_carlo_section(ctx: _BundleLoadCtx) -> None:
    _load_json_summary_section(ctx, "monte_carlo_summary.json", _MONTE_CARLO_META_KEYS)


def _build_noise_section(ctx: _BundleBuildCtx) -> None:
    _build_json_summary_section(
        ctx, "noise", "noise_summary", "noise_summary.json", _NOISE_META_KEYS
    )


def _load_noise_section(ctx: _BundleLoadCtx) -> None:
    _load_json_summary_section(ctx, "noise_summary.json", _NOISE_META_KEYS)


def _build_overfitting_section(ctx: _BundleBuildCtx) -> None:
    _build_json_summary_section(
        ctx,
        "overfitting",
        "overfitting_summary",
        "overfitting_summary.json",
        _OVERFITTING_META_KEYS,
    )


def _load_overfitting_section(ctx: _BundleLoadCtx) -> None:
    _load_json_summary_section(ctx, "overfitting_summary.json", _OVERFITTING_META_KEYS)


def _build_sensitivity_section(ctx: _BundleBuildCtx) -> None:
    _build_json_summary_section(
        ctx,
        "sensitivity",
        "sensitivity_summary",
        "sensitivity_summary.json",
        _SENSITIVITY_META_KEYS,
    )


def _load_sensitivity_section(ctx: _BundleLoadCtx) -> None:
    _load_json_summary_section(ctx, "sensitivity_summary.json", _SENSITIVITY_META_KEYS)


def _build_portfolio_section(ctx: _BundleBuildCtx) -> None:
    session_state = ctx.session_state
    if session_state.get("portfolio_summary") is None:
        return
    ctx.files["portfolio_summary.json"] = _to_json_bytes(
        {key: session_state.get(key) for key in _PORTFOLIO_META_KEYS}
    )
    for key in (
        "portfolio_trades",
        "portfolio_skipped_trades",
        "portfolio_equity_curve",
        "portfolio_correlation",
        "portfolio_drawdown_correlation",
        "portfolio_marginal_contribution",
    ):
        frame = session_state.get(key)
        if _is_dataframe(frame):
            ctx.files[f"{key}.parquet"] = _to_parquet_bytes(frame)
            ctx.included_keys.add(key)
    _mark_included(ctx, "portfolio")
    ctx.included_keys.update(_PORTFOLIO_META_KEYS)


def _load_portfolio_section(ctx: _BundleLoadCtx) -> None:
    portfolio_meta = _read_json_from_zip(ctx.zf, "portfolio_summary.json")
    _restore_present_meta(ctx.session_values, portfolio_meta, _PORTFOLIO_META_KEYS)
    for key in (
        "portfolio_trades",
        "portfolio_skipped_trades",
        "portfolio_equity_curve",
        "portfolio_correlation",
        "portfolio_drawdown_correlation",
        "portfolio_marginal_contribution",
    ):
        filename = f"{key}.parquet"
        if filename in ctx.names:
            ctx.session_values[key] = _read_parquet_from_zip(ctx.zf, filename)


def _build_confluence_combo_section(ctx: _BundleBuildCtx) -> None:
    # PR 5c: confluence combo is Backtest on-the-fly only — recompute on export
    # (no producer session key). Omit entirely when unavailable. Gate on the
    # backtest section so combo siblings are never orphaned without trades.parquet
    # (source of truth for later recompute).
    if not ctx.manifest["included"].get("backtest"):
        return
    confluence_artifacts = build_confluence_combo_bundle_artifacts(ctx.session_state)
    if not isinstance(confluence_artifacts, dict):
        return
    summary_payload = confluence_artifacts.get("summary")
    frames = confluence_artifacts.get("frames")
    if not (isinstance(summary_payload, Mapping) and summary_payload.get("available")):
        return
    ctx.files["confluence_combo_summary.json"] = _to_json_bytes(summary_payload)
    ctx.included_keys.add(_CONFLUENCE_COMBO_SUMMARY_KEY)
    if isinstance(frames, Mapping):
        for artifact_name, session_key in _CONFLUENCE_COMBO_FRAME_FROM_ARTIFACT.items():
            frame = frames.get(artifact_name)
            if _is_dataframe(frame) and not frame.empty:
                filename = _CONFLUENCE_COMBO_PARQUET_FILES[session_key]
                ctx.files[filename] = _to_parquet_bytes(_parquet_safe_frame(frame))
                ctx.included_keys.add(session_key)
    _mark_included(ctx, "confluence_combo")


def _load_confluence_combo_section(ctx: _BundleLoadCtx) -> None:
    # PR 5c: optional confluence combo siblings. Absent section → ignore
    # missing files (old bundles keep loading). Included → require JSON;
    # load parquet siblings only when present.
    ctx.session_values[_CONFLUENCE_COMBO_SUMMARY_KEY] = _read_json_from_zip(
        ctx.zf, "confluence_combo_summary.json"
    )
    for session_key, filename in _CONFLUENCE_COMBO_PARQUET_FILES.items():
        if filename in ctx.names:
            ctx.session_values[session_key] = _read_parquet_from_zip(ctx.zf, filename)


def _build_identity_member(ctx: _BundleBuildCtx) -> None:
    identity_payload = _identity_payload_from_state(ctx.session_state)
    if identity_payload is None:
        return
    ctx.files[IDENTITY_META_FILENAME] = _to_json_bytes(identity_payload)
    for key in ("data_identity", "levels_identity"):
        if key in identity_payload:
            ctx.included_keys.add(key)


def _load_identity_member(ctx: _BundleLoadCtx) -> None:
    if IDENTITY_META_FILENAME not in ctx.names:
        return
    identity_meta = _read_json_from_zip(ctx.zf, IDENTITY_META_FILENAME)
    for key in ("data_identity", "levels_identity"):
        if key in identity_meta:
            ctx.session_values[key] = identity_meta[key]
    # Older/odd identity members may nest data_identity only under
    # levels_identity; promote so session restore stays complete.
    if "data_identity" not in ctx.session_values:
        levels_identity = ctx.session_values.get("levels_identity")
        if isinstance(levels_identity, Mapping):
            nested = levels_identity.get("data_identity")
            if isinstance(nested, Mapping):
                ctx.session_values["data_identity"] = nested


def _promote_format_profile_from_identity(session_values: dict[str, Any]) -> None:
    # Older CAI-1 bundles may omit format_profile from dataset_meta while
    # still carrying it on data_identity (top-level or nested-promoted).
    if "format_profile" in session_values:
        return
    data_identity = session_values.get("data_identity")
    if isinstance(data_identity, Mapping) and data_identity.get("format_profile"):
        session_values["format_profile"] = str(data_identity["format_profile"])


def _require_included_section_files(included: Mapping[str, Any], names: set[str]) -> None:
    for section, required_files in _SECTION_REQUIRED_FILES.items():
        if not included.get(section):
            continue
        for filename in required_files:
            if filename not in names:
                raise ValueError(
                    f"Manifest includes '{section}' but bundle is missing '{filename}'."
                )


def _open_research_bundle_zip(uploaded_file: Any) -> zipfile.ZipFile:
    raw = _read_uploaded_bytes(uploaded_file)
    try:
        return zipfile.ZipFile(io.BytesIO(raw), mode="r")
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid research bundle zip file.") from exc


def _read_validated_manifest(
    zf: zipfile.ZipFile, names: set[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if MANIFEST_FILENAME not in names:
        raise ValueError("Bundle is missing manifest.json.")
    manifest = _read_json_from_zip(zf, MANIFEST_FILENAME)
    if manifest.get("kind") != BUNDLE_KIND:
        raise ValueError("Invalid bundle kind in manifest.")
    if manifest.get("bundle_schema_version") != BUNDLE_SCHEMA_VERSION:
        raise ValueError("Unsupported bundle schema version.")
    included = manifest.get("included")
    if not isinstance(included, dict):
        raise ValueError("Manifest 'included' must be an object.")
    _require_included_section_files(included, names)
    return manifest, included


def _pack_research_bundle_zip(files: Mapping[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            zf.writestr(name, files[name])
    return output.getvalue()


BUNDLE_SECTION_IO: tuple[BundleSectionIO, ...] = (
    BundleSectionIO("dataset", _build_dataset_section, _load_dataset_section),
    BundleSectionIO("levels", _build_levels_section, _load_levels_section),
    BundleSectionIO("signals", _build_signals_section, _load_signals_section),
    BundleSectionIO("backtest", _build_backtest_section, _load_backtest_section),
    BundleSectionIO("grid", _build_grid_section, _load_grid_section),
    BundleSectionIO("validation", _build_validation_section, _load_validation_section),
    BundleSectionIO("walk_forward", _build_walk_forward_section, _load_walk_forward_section),
    BundleSectionIO("excursion", _build_excursion_section, _load_excursion_section),
    BundleSectionIO("monte_carlo", _build_monte_carlo_section, _load_monte_carlo_section),
    BundleSectionIO("noise", _build_noise_section, _load_noise_section),
    BundleSectionIO("overfitting", _build_overfitting_section, _load_overfitting_section),
    BundleSectionIO("sensitivity", _build_sensitivity_section, _load_sensitivity_section),
    BundleSectionIO("portfolio", _build_portfolio_section, _load_portfolio_section),
    BundleSectionIO(
        "confluence_combo", _build_confluence_combo_section, _load_confluence_combo_section
    ),
)
BUNDLE_SECTION_IO_NAMES: tuple[str, ...] = tuple(spec.section for spec in BUNDLE_SECTION_IO)


def build_research_bundle(session_state: Mapping[str, Any]) -> bytes:
    """Build a zip bundle for supported research artifacts from session_state.

    Walks :data:`BUNDLE_SECTION_IO` (C-7 / QI-06-04). Identity is written after
    the section walk so omitted session identity maps still omit
    ``research_identity.json``.
    """
    ctx = _BundleBuildCtx(session_state)
    for spec in BUNDLE_SECTION_IO:
        spec.build(ctx)
    _build_identity_member(ctx)
    ctx.manifest["session_keys"] = sorted(ctx.included_keys)
    ctx.files[MANIFEST_FILENAME] = _to_json_bytes(ctx.manifest)
    return _pack_research_bundle_zip(ctx.files)


def _identity_payload_from_state(session_state: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build optional CAI-1 identity metadata; omit when no identity fields exist.

    ``experiment_identity`` stays on run state/provenance only for CAI-1: its
    RunSpec hash currently includes dataset path strings, which differ between
    relative API/CLI specs and absolute Assistant specs. Bundling it would break
    canonical-hash parity. Data/levels identities remain path-independent.

    Do not derive identities from live page frames here: legacy classic bundles
    without session identity maps must keep omitting ``research_identity.json``.
    CAI-8 badges use provenance stamps and/or ``peek_research_identity`` when
    the optional member is present.
    """
    data_identity = DataIdentity.from_dict(
        session_state.get("data_identity")
        if isinstance(session_state.get("data_identity"), Mapping)
        else None
    )
    levels_identity = LevelsIdentity.from_dict(
        session_state.get("levels_identity")
        if isinstance(session_state.get("levels_identity"), Mapping)
        else None
    )
    # levels_identity embeds data_identity; promote it so research_identity.json
    # always restores a top-level data_identity when levels identity is present.
    if data_identity is None and levels_identity is not None:
        data_identity = levels_identity.data_identity
    if data_identity is None and levels_identity is None:
        return None
    return build_identity_metadata(
        data_identity=data_identity,
        levels_identity=levels_identity,
    )


def peek_research_identity(bundle: Any) -> dict[str, Any] | None:
    """Read ``research_identity.json`` only — no parquet / full bundle load (CAI-8).

    Accepts bytes, a filesystem path, or a file-like object. Returns None when
    the member is absent or unreadable. Oversized uploads (QI-06-09) return
    None without reading path bytes or opening the zip.
    """
    try:
        if isinstance(bundle, (str, Path)):
            path = Path(bundle)
            if not path.is_file():
                return None
            try:
                _reject_declared_upload_size(path.stat().st_size)
                raw = _ensure_within_upload_cap(path.read_bytes())
            except OSError:
                return None
        else:
            raw = _read_uploaded_bytes(bundle)
    except ValueError:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(raw), mode="r") as zf:
            names = set(zf.namelist())
            if IDENTITY_META_FILENAME not in names:
                return None
            payload = _read_json_from_zip(zf, IDENTITY_META_FILENAME)
    except (OSError, zipfile.BadZipFile, ValueError, KeyError):
        return None
    return payload if isinstance(payload, dict) else None


def _upload_cap_error() -> ValueError:
    return ValueError(f"Research bundle exceeds the {MAX_BUNDLE_UPLOAD_BYTES} byte upload cap.")


def _reject_declared_upload_size(size_hint: Any) -> None:
    """Refuse a declared size over the upload cap before reading bytes."""
    if isinstance(size_hint, bool) or not isinstance(size_hint, int):
        return
    if size_hint > MAX_BUNDLE_UPLOAD_BYTES:
        raise _upload_cap_error()


def _ensure_within_upload_cap(data: Any) -> bytes:
    if not isinstance(data, bytes):
        raise ValueError("Uploaded bundle content must be bytes.")
    if len(data) > MAX_BUNDLE_UPLOAD_BYTES:
        raise _upload_cap_error()
    return data


def _read_uploaded_bytes(uploaded_file: Any) -> bytes:
    if isinstance(uploaded_file, bytes):
        return _ensure_within_upload_cap(uploaded_file)
    _reject_declared_upload_size(getattr(uploaded_file, "size", None))
    if hasattr(uploaded_file, "getvalue"):
        return _ensure_within_upload_cap(uploaded_file.getvalue())
    if hasattr(uploaded_file, "read"):
        return _ensure_within_upload_cap(uploaded_file.read())
    raise ValueError("Unsupported uploaded bundle object.")


def _declared_zip_member_size(info: zipfile.ZipInfo, filename: str) -> int:
    """Uncompressed size from the central directory; fail closed on junk."""
    try:
        file_size = int(info.file_size)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Bundle member '{filename}' has an invalid size.") from exc
    if file_size < 0:
        raise ValueError(f"Bundle member '{filename}' has an invalid size.")
    return file_size


def _read_zip_member_bytes(zf: zipfile.ZipFile, filename: str) -> bytes:
    """Read a named zip member after rejecting oversize ``ZipInfo.file_size``."""
    try:
        info = zf.getinfo(filename)
    except KeyError as exc:
        raise ValueError(f"Bundle is missing required file '{filename}'.") from exc
    if _declared_zip_member_size(info, filename) > MAX_BUNDLE_MEMBER_BYTES:
        raise ValueError(
            f"Bundle member '{filename}' exceeds the {MAX_BUNDLE_MEMBER_BYTES} byte size cap."
        )
    try:
        return zf.read(filename)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Bundle member '{filename}' is corrupt.") from exc


def _read_json_from_zip(zf: zipfile.ZipFile, filename: str) -> dict[str, Any]:
    raw = _read_zip_member_bytes(zf, filename)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Bundle JSON is invalid for '{filename}'.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Bundle JSON for '{filename}' must be an object.")
    return payload


def _read_parquet_from_zip(zf: zipfile.ZipFile, filename: str) -> pd.DataFrame:
    raw = _read_zip_member_bytes(zf, filename)
    try:
        return pd.read_parquet(io.BytesIO(raw))
    except Exception as exc:  # pragma: no cover - pandas/pyarrow exception types vary
        raise ValueError(f"Bundle parquet is invalid for '{filename}'.") from exc


def load_research_bundle(uploaded_file: Any) -> dict[str, Any]:
    """Load and validate a research bundle zip into an in-memory payload.

    Walks :data:`BUNDLE_SECTION_IO` for included sections (C-7 / QI-06-04).
    Identity loads first; ``format_profile`` promotion runs after the walk.
    """
    zf = _open_research_bundle_zip(uploaded_file)
    with zf:
        names = set(zf.namelist())
        manifest, included = _read_validated_manifest(zf, names)
        ctx = _BundleLoadCtx(zf, names, included)
        _load_identity_member(ctx)
        for spec in BUNDLE_SECTION_IO:
            if included.get(spec.section):
                spec.load(ctx)
        _promote_format_profile_from_identity(ctx.session_values)
        return {
            "manifest": manifest,
            "session_values": ctx.session_values,
            "known_files_in_bundle": sorted(name for name in names if name in _KNOWN_FILES),
        }


def apply_research_bundle_to_session(
    bundle: Mapping[str, Any], session_state: Any
) -> dict[str, Any]:
    """Apply loaded bundle values to Streamlit session state."""
    session_values = bundle.get("session_values")
    if not isinstance(session_values, dict):
        raise ValueError("Bundle payload is missing session values.")

    cleared_keys: list[str] = []
    for key in _MANAGED_RESEARCH_KEYS:
        if key in session_state:
            cleared_keys.append(key)
        session_state.pop(key, None)

    # Drop stale Admit widgets before restore so a prior session cannot keep
    # an enabled toggle when the imported bundle has no / disabled Admit.
    for key in _BACKTEST_ENTRY_WINDOW_WIDGET_KEYS:
        if key in session_state:
            cleared_keys.append(key)
        session_state.pop(key, None)

    restored_keys: list[str] = []
    for key, value in session_values.items():
        session_state[key] = value
        restored_keys.append(key)

    # Backtest Run reads Admit from sidebar widgets. Rehydrate widgets from the
    # restored ``entry_window`` so import round-trips the constrained window
    # (Promote writes the same mapping via backtest_widget_state_from_entry_window).
    entry_window = session_state.get("entry_window")
    if isinstance(entry_window, Mapping):
        from thesistester.analytics.entry_window import (
            backtest_widget_state_from_entry_window,
        )

        exchange_tz = session_state.get("exchange_timezone") or "America/New_York"
        try:
            widget_state = backtest_widget_state_from_entry_window(
                dict(entry_window),
                exchange_tz=str(exchange_tz),
            )
        except ValueError:
            widget_state = {"backtest_entry_window_enabled": False}
        for key, value in widget_state.items():
            session_state[key] = value
            if key not in restored_keys:
                restored_keys.append(key)
    else:
        session_state["backtest_entry_window_enabled"] = False
        if "backtest_entry_window_enabled" not in restored_keys:
            restored_keys.append("backtest_entry_window_enabled")

    # Data page Source defaults to Sample and may still hold a prior CSV in
    # the uploader. Ask that page to drop the leftover widget so navigation
    # cannot clobber this restore (sample auto-load is separately gated on
    # empty sessions only).
    session_state[DATA_PAGE_INVALIDATE_SOURCE_KEY] = True
    session_state[BUNDLE_IMPORT_OMITTED_DATA_KEY] = "data" not in session_values

    # QI-10-01 / A-8: leftover display TZ must not survive apply. Rebind to
    # the restored exchange TZ (or TIMEZONE_OPTIONS[0] when the zip omitted it).
    from thesistester.timezone_display import reset_display_timezone

    reset_display_timezone(
        session_state,
        exchange_timezone=session_state.get("exchange_timezone"),
    )

    return {
        "cleared_keys": sorted(set(cleared_keys)),
        "cleared_count": len(set(cleared_keys)),
        "restored_keys": restored_keys,
        "restored_count": len(restored_keys),
    }


def should_skip_dataset_bootstrap(session_state: Any) -> bool:
    """True after a dataset-less bundle apply (page-12 / Data auto-fill gate)."""
    return bool(session_state.get(BUNDLE_IMPORT_OMITTED_DATA_KEY))
