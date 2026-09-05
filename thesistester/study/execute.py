"""Study-owned cell execution loop (RS3).

Uses ``run_experiment`` + ``build_research_bundle`` like ``cli._execute_run``,
but writes bundles/index/ledger incrementally and continues after per-cell
failures. Does **not** call ``run_batch``.
"""

from __future__ import annotations

import errno
import json
import math
import multiprocessing
import numbers
import os
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Callable, Iterator, Mapping

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows CPython
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]

import pandas as pd

from thesistester.analytics.metrics import direction_split_index_values
from thesistester.analytics.overfitting import vs_random_benchmark
from thesistester.api import run_experiment
from thesistester.config import INSTRUMENTS
from thesistester.entry_window_policy import normalize_entry_window
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.study.briefing import read_zip_parquet, resolve_cell_bundle
from thesistester.levels.tick_vap import (
    build_prior_profile_table_from_paths,
    compute_tick_source_id,
    resolve_tick_format_profile,
)
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from thesistester.study.expand import ExpansionResult, expand_study, write_expansion_artifacts
from thesistester.study.ledger import (
    cells_to_run,
    empty_ledger,
    load_ledger,
    mark_cell,
    record_confirmation,
    save_ledger,
)
from thesistester.study.schema import StudySpecError, load_study_spec

# Windows CRT lock contention + portable non-blocking "busy" codes.
_LOCK_CONTENTION_ERRNOS = frozenset(
    {
        errno.EACCES,
        errno.EAGAIN,
        getattr(errno, "EWOULDBLOCK", errno.EAGAIN),
        getattr(errno, "EDEADLK", errno.EACCES),
    }
)

# Metric keys produced by cli._execute_run (without bundle_path).
# RS-D7: profit_factor + win_rate sit with other trade-summary metrics.
R18_INDEX_METRIC_KEYS: tuple[str, ...] = (
    "run_name",
    "bundle_hash",
    "dataset_id",
    "instrument",
    "execution_origin",
    "cache_outcome",
    "trade_count",
    "expectancy_r",
    "total_r",
    "max_drawdown_r",
    "profit_factor",
    "win_rate",
    "best_grid_stop_loss_ticks",
    "best_grid_take_profit_ticks",
    "validation_trade_count_status",
    "wfa_fold_count",
    "wfa_valid_fold_count",
    "wfa_median_test_expectancy_r",
    "wfa_stitched_oos_total_r",
)

# Study-owned DA2 keys. Not on R18_INDEX_METRIC_KEYS (CLI RS-D7 ordered parity).
DA_DIRECTION_INDEX_KEYS: tuple[str, ...] = (
    "long_trade_count",
    "short_trade_count",
    "long_expectancy_r",
    "short_expectancy_r",
    "long_share",
    "directional_integrity",
    "collision_pairs",
    "collision_resolved_long",
)

# Study-owned DA5 keys. Not on R18_INDEX_METRIC_KEYS (CLI RS-D7 ordered parity).
DA_RANDOM_INDEX_KEYS: tuple[str, ...] = (
    "random_null_expectancy_r",
    "random_null_std_r",
    "random_p_value_ge",
    "expectancy_minus_null_r",
)

STUDY_INDEX_KEYS: tuple[str, ...] = (
    R18_INDEX_METRIC_KEYS
    + DA_DIRECTION_INDEX_KEYS
    + DA_RANDOM_INDEX_KEYS
    + ("bundle_path", "status")
)

# Injected onto the cell task spec only; stripped before run_experiment.
_DA5_RANDOM_BASELINE_KEY = "_da5_random_baseline"

# simulate_trades kwargs forwarded into vs_random_benchmark. Excludes SL/TP
# (passed as explicit args) and unknown backtest keys (ranking_metric, enabled).
_DA5_SIMULATION_KWARGS = frozenset(
    {
        "max_holding_bars",
        "allow_same_bar_exit",
        "commission_per_side",
        "slippage_ticks",
        "flat_by_session_close",
        "session_close_time",
        "session_timezone",
        "no_new_entries_after",
        "exposure_policy",
        "cooldown_bars_after_exit",
        "intrabar_model",
        "subtimeframe_data",
        "parent_interval",
        "sub_interval",
        "entry_window",
        "entry_window_exchange_tz",
        "breakeven_after_r",
        "trailing_after_r",
        "trailing_distance_ticks",
        "same_bar_opposite_direction",
    }
)
STUDY_PRIOR_PROFILE_PARQUET = "study.prior_profile.parquet"


def _coerce_index_float(value: Any) -> float | None:
    """Coerce trade-summary floats for index write; NaN → null; keep ±inf."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if value is pd.NA or pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, numbers.Real):
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
            number = float(text)
        except ValueError:
            return None
        if math.isnan(number):
            return None
        return number
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _coerce_index_float(item())
        except (ValueError, TypeError, OverflowError, RecursionError):
            return None
    return None


def _metric_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


_INDEX_IDENTITY_KEYS: tuple[str, ...] = (
    "dataset_id",
    "instrument",
    "execution_origin",
    "cache_outcome",
    "best_grid_stop_loss_ticks",
    "best_grid_take_profit_ticks",
    "validation_trade_count_status",
    "wfa_fold_count",
    "wfa_valid_fold_count",
    "wfa_median_test_expectancy_r",
    "wfa_stitched_oos_total_r",
)


def build_index_row_from_state(
    *,
    name: str,
    state: Mapping[str, Any],
    bundle: bytes,
) -> dict[str, Any]:
    """Build the R18-parity index row (no bundle_path / status)."""
    summary = state.get("trade_summary") or {}
    best = state.get("best_grid_result") or {}
    validation = state.get("validation_summary") or {}
    walk_forward = state.get("walk_forward_summary") or {}
    cache_provenance = state.get("cache_provenance") or {}
    return {
        "run_name": name,
        "bundle_hash": canonical_bundle_hash(bundle),
        "dataset_id": state.get("dataset_id"),
        "instrument": state.get("instrument"),
        "execution_origin": state.get("execution_origin", "study"),
        "cache_outcome": cache_provenance.get("outcome"),
        "trade_count": summary.get("trade_count"),
        "expectancy_r": summary.get("expectancy_r"),
        "total_r": summary.get("total_r"),
        "max_drawdown_r": summary.get("max_drawdown_r"),
        "profit_factor": _coerce_index_float(summary.get("profit_factor")),
        "win_rate": _coerce_index_float(summary.get("win_rate")),
        "best_grid_stop_loss_ticks": best.get("stop_loss_ticks"),
        "best_grid_take_profit_ticks": best.get("take_profit_ticks"),
        "validation_trade_count_status": (validation.get("trade_count") or {}).get("status"),
        "wfa_fold_count": walk_forward.get("fold_count"),
        "wfa_valid_fold_count": walk_forward.get("valid_fold_count"),
        "wfa_median_test_expectancy_r": walk_forward.get("median_test_expectancy_r"),
        "wfa_stitched_oos_total_r": walk_forward.get("stitched_oos_total_r"),
    }


def _direction_n(trade_count: Any, *, long_n: int, short_n: int) -> int:
    """Accepted-trade N for DA2 share / class. Non-finite → long+short."""
    count = _coerce_index_float(trade_count)
    if count is None or not math.isfinite(count):
        count = float(int(long_n) + int(short_n))
    return int(count)


def classify_directional_integrity(
    *,
    trade_count: Any,
    long_trade_count: int,
    short_trade_count: int,
) -> str:
    """Label a cell from accepted-trade counts. Empty when ``trade_count == 0``."""
    n = _direction_n(trade_count, long_n=int(long_trade_count), short_n=int(short_trade_count))
    if n == 0:
        return "empty"
    if int(short_trade_count) == 0:
        return "long_only"
    if int(long_trade_count) == 0:
        return "short_only"
    return "mixed"


def direction_index_fields(
    trades: pd.DataFrame | None,
    *,
    trade_count: Any = None,
    collision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Study-index DA2 fields from trades (+ optional in-memory DA1 diagnostic).

    ``long_share`` is ``long_trade_count / trade_count`` and ``None`` when
    ``trade_count`` is 0. Collision keys stay ``None`` unless ``collision``
    is a mapping from ``direction_collision_diagnostic``.
    """
    split = direction_split_index_values(trades)
    long_n = int(split["long_trade_count"] or 0)
    short_n = int(split["short_trade_count"] or 0)
    n = _direction_n(trade_count, long_n=long_n, short_n=short_n)
    long_share = (long_n / n) if n else None
    pairs: Any = None
    resolved_long: Any = None
    if isinstance(collision, Mapping) and collision:
        if "candidate_pairs" in collision:
            pairs = collision.get("candidate_pairs")
        if "resolved_long" in collision:
            resolved_long = collision.get("resolved_long")
    return {
        "long_trade_count": long_n,
        "short_trade_count": short_n,
        "long_expectancy_r": split["long_expectancy_r"],
        "short_expectancy_r": split["short_expectancy_r"],
        "long_share": long_share,
        "directional_integrity": classify_directional_integrity(
            trade_count=n,
            long_trade_count=long_n,
            short_trade_count=short_n,
        ),
        "collision_pairs": pairs,
        "collision_resolved_long": resolved_long,
    }


def _empty_random_baseline_fields() -> dict[str, Any]:
    return {key: None for key in DA_RANDOM_INDEX_KEYS}


def _random_baseline_cfg(raw: Any) -> dict[str, Any]:
    """Execute-time defaults. Omitted / non-mapping → disabled (legacy)."""
    if not isinstance(raw, Mapping):
        return {"enabled": False, "n_replicas": 50, "random_state": 42}
    n_replicas = raw.get("n_replicas", 50)
    random_state = raw.get("random_state", 42)
    if isinstance(n_replicas, bool) or not isinstance(n_replicas, int) or n_replicas < 1:
        n_replicas = 50
    if isinstance(random_state, bool) or not isinstance(random_state, int):
        random_state = 42
    return {
        "enabled": bool(raw.get("enabled", False)),
        "n_replicas": n_replicas,
        "random_state": random_state,
    }


def _cell_execution_kwargs(
    run_spec: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    instrument: str,
) -> dict[str, Any]:
    """Lock-fidelity simulate_trades kwargs from the cell backtest + state."""
    backtest = dict(run_spec.get("backtest") or {})
    kwargs: dict[str, Any] = {}
    for key in _DA5_SIMULATION_KWARGS:
        if key in backtest:
            kwargs[key] = backtest[key]
    inst = INSTRUMENTS.get(instrument)
    raw_window = backtest.get("entry_window")
    if raw_window is not None and inst is not None:
        try:
            entry_window = normalize_entry_window(raw_window, exchange_tz=inst.exchange_tz)
        except (TypeError, ValueError):
            kwargs.pop("entry_window", None)
        else:
            kwargs["entry_window"] = entry_window if entry_window.get("enabled") else None
            kwargs["entry_window_exchange_tz"] = inst.exchange_tz
    if bool(kwargs.get("flat_by_session_close")) and inst is not None:
        kwargs["session_timezone"] = backtest.get("session_timezone") or inst.exchange_tz
    if state.get("subtimeframe_data") is not None:
        kwargs["subtimeframe_data"] = state["subtimeframe_data"]
    provenance = state.get("ingestion_provenance")
    if isinstance(provenance, Mapping):
        if provenance.get("derived_parent_interval") is not None:
            kwargs["parent_interval"] = provenance.get("derived_parent_interval")
        if provenance.get("source_interval") is not None:
            kwargs["sub_interval"] = provenance.get("source_interval")
    return {key: value for key, value in kwargs.items() if key in _DA5_SIMULATION_KWARGS}


def random_baseline_fields(
    *,
    cfg: Mapping[str, Any],
    state: Mapping[str, Any],
    run_spec: Mapping[str, Any],
    expectancy_r: Any,
) -> dict[str, Any]:
    """Study-index DA5 fields from ``vs_random_benchmark``. Failures → nulls.

    Computed after the research bundle is written and hashed. Never persists
    ``replica_expectancies``. Soft-resume / ``--rebuild-direction`` leave these
    keys ``None`` (the null needs OHLCV + execution kwargs, not just trades).
    """
    parsed = _random_baseline_cfg(cfg)
    empty = _empty_random_baseline_fields()
    if not parsed["enabled"]:
        return empty
    trades = state.get("trades")
    levels = state.get("levels")
    if not isinstance(trades, pd.DataFrame) or trades.empty:
        return empty
    if not isinstance(levels, pd.DataFrame) or len(levels) < 2:
        return empty
    instrument = str(state.get("instrument") or "")
    inst = INSTRUMENTS.get(instrument)
    if inst is None:
        return empty
    backtest = dict(run_spec.get("backtest") or {})
    sl = backtest.get("stop_loss_ticks")
    tp = backtest.get("take_profit_ticks")
    if sl is None or tp is None:
        return empty
    try:
        result = vs_random_benchmark(
            levels,
            trades,
            tick_size=inst.tick_size,
            point_value=inst.point_value,
            stop_loss_ticks=float(sl),
            take_profit_ticks=float(tp),
            execution_kwargs=_cell_execution_kwargs(run_spec, state, instrument=instrument),
            n_replicas=int(parsed["n_replicas"]),
            random_state=int(parsed["random_state"]),
        )
    except Exception:  # noqa: BLE001 — null must not fail a successful cell
        return empty
    if not isinstance(result, Mapping) or not result.get("available"):
        return empty
    null_mean = _coerce_index_float(result.get("null_expectancy_mean"))
    observed = _coerce_index_float(expectancy_r)
    minus = None if null_mean is None or observed is None else observed - null_mean
    return {
        "random_null_expectancy_r": null_mean,
        "random_null_std_r": _coerce_index_float(result.get("null_expectancy_std")),
        "random_p_value_ge": _coerce_index_float(result.get("p_value_greater_or_equal")),
        "expectancy_minus_null_r": minus,
    }


def _failed_index_row(name: str) -> dict[str, Any]:
    row = {key: None for key in R18_INDEX_METRIC_KEYS}
    row.update({key: None for key in DA_DIRECTION_INDEX_KEYS})
    row.update({key: None for key in DA_RANDOM_INDEX_KEYS})
    row["run_name"] = name
    row["execution_origin"] = "study"
    return row


def _read_bundle_trades(bundle_path: Path) -> pd.DataFrame | None:
    """Best-effort ``trades.parquet`` from a research zip. Missing → None."""
    return read_zip_parquet(Path(bundle_path), "trades.parquet")


def rebuild_direction_index(study_dir: str | Path) -> Path:
    """Fill DA2 keys on ``results_index.csv`` from bundle ``trades.parquet``.

    Never rewrites existing metric values. Collision fields stay ``None``
    (DA1 diagnostic is not persisted in bundles). DA5 random-baseline keys
    are left as-is (not recomputed). Idempotent. Atomic replace.
    """
    root = Path(study_dir)
    path = root / "results_index.csv"
    if not path.is_file():
        raise StudySpecError(f"Missing results_index.csv under {root}")
    frame = pd.read_csv(path)
    if "run_name" not in frame.columns:
        raise StudySpecError(f"{path} must include a run_name column")
    existing_columns = list(frame.columns)
    filled: dict[str, list[Any]] = {key: [] for key in DA_DIRECTION_INDEX_KEYS}
    none_fields = {key: None for key in DA_DIRECTION_INDEX_KEYS}
    for idx in frame.index:
        bundle_rel = frame.at[idx, "bundle_path"] if "bundle_path" in frame.columns else None
        if _metric_missing(bundle_rel):
            for key, value in none_fields.items():
                filled[key].append(value)
            continue
        resolved = resolve_cell_bundle(root, str(bundle_rel).strip())
        trades = _read_bundle_trades(resolved) if resolved is not None else None
        if trades is None:
            for key, value in none_fields.items():
                filled[key].append(value)
            continue
        trade_count = frame.at[idx, "trade_count"] if "trade_count" in frame.columns else None
        fields = direction_index_fields(trades, trade_count=trade_count, collision=None)
        fields["collision_pairs"] = None
        fields["collision_resolved_long"] = None
        for key in DA_DIRECTION_INDEX_KEYS:
            filled[key].append(fields[key])
    for key, values in filled.items():
        frame[key] = values
    extras = [column for column in existing_columns if column not in STUDY_INDEX_KEYS]
    ordered = [column for column in STUDY_INDEX_KEYS if column in frame.columns] + extras
    frame = frame.loc[:, ordered]
    tmp = path.with_name(".results_index.csv.tmp")
    frame.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return path


def _read_bundle_trade_summary(bundle_path: Path) -> dict[str, Any] | None:
    """Best-effort ``trade_summary`` dict from a research zip (nested or flat)."""
    if not bundle_path.is_file():
        return None
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            if "trade_summary.json" not in archive.namelist():
                return None
            raw = json.loads(archive.read("trade_summary.json").decode("utf-8"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, Mapping):
        return None
    nested = raw.get("trade_summary")
    if isinstance(nested, Mapping):
        return dict(nested)
    # Flat summary dict (tests / older shapes).
    if any(key in raw for key in ("trade_count", "expectancy_r", "profit_factor")):
        return dict(raw)
    return None


def _read_bundle_dataset_identity(bundle_path: Path) -> dict[str, Any]:
    """Best-effort ``dataset_id`` / ``instrument`` from bundle ``dataset_meta.json``."""
    if not bundle_path.is_file():
        return {}
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            if "dataset_meta.json" not in archive.namelist():
                return {}
            raw = json.loads(archive.read("dataset_meta.json").decode("utf-8"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key in ("dataset_id", "instrument"):
        value = raw.get(key)
        if not _metric_missing(value):
            out[key] = value
    return out


def _index_row_from_existing_bundle(
    name: str,
    *,
    output_dir: Path,
    bundle_rel: str,
    prior_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild an ok index row from a soft-resumed bundle (metrics + hash).

    Soft resume previously synthesized ``status=ok`` via ``_failed_index_row``,
    leaving R18 metrics null forever when ``results_index.csv`` lost the row.
    Rehydrate core trade metrics from ``trade_summary.json`` so report ranking
    stays honest without re-running the cell. Preserve non-null identity fields
    from ``prior_row`` / ``dataset_meta.json`` so soft-resume does not wipe
    ``dataset_id`` / ``instrument``. DA2 keys come from ``trades.parquet`` when
    present; collision copies stay ``None`` (DA1 diagnostic is in-memory only).
    DA5 random-baseline keys stay ``None`` (null needs OHLCV + execution kwargs).
    """
    row = _failed_index_row(name)
    if prior_row is not None:
        for key in _INDEX_IDENTITY_KEYS:
            value = prior_row.get(key)
            if not _metric_missing(value):
                row[key] = value
    row["status"] = "ok"
    row["bundle_path"] = bundle_rel
    bundle_path = output_dir / bundle_rel
    try:
        row["bundle_hash"] = canonical_bundle_hash(bundle_path.read_bytes())
    except OSError:
        row["bundle_hash"] = None
    identity = _read_bundle_dataset_identity(bundle_path)
    for key, value in identity.items():
        if _metric_missing(row.get(key)):
            row[key] = value
    summary = _read_bundle_trade_summary(bundle_path) or {}
    for key in ("trade_count", "expectancy_r", "total_r", "max_drawdown_r"):
        if key in summary:
            row[key] = summary.get(key)
    row["profit_factor"] = _coerce_index_float(summary.get("profit_factor"))
    row["win_rate"] = _coerce_index_float(summary.get("win_rate"))
    trades = _read_bundle_trades(bundle_path)
    if trades is not None:
        row.update(
            direction_index_fields(
                trades,
                trade_count=row.get("trade_count"),
                collision=None,
            )
        )
    return row


def _backfill_pf_wr_from_bundle(
    row: Mapping[str, Any],
    *,
    output_dir: Path,
    bundle_rel: str,
) -> dict[str, Any]:
    """Fill missing PF/WR on an ok row from bundle without wiping other columns."""
    out = dict(row)
    need_pf = _metric_missing(out.get("profit_factor"))
    need_wr = _metric_missing(out.get("win_rate"))
    if not need_pf and not need_wr:
        return out
    summary = _read_bundle_trade_summary(output_dir / bundle_rel) or {}
    if need_pf:
        out["profit_factor"] = _coerce_index_float(summary.get("profit_factor"))
    if need_wr:
        out["win_rate"] = _coerce_index_float(summary.get("win_rate"))
    return out


def _prepare_study_prior_profile(
    spec: Mapping[str, Any],
    expansion: ExpansionResult,
    *,
    output_dir: Path,
    base_directory: Path,
) -> None:
    """Build PriorProfileTable once; inject parquet path onto every cell dataset."""
    study = spec.get("study")
    if not isinstance(study, Mapping):
        return
    dataset = study.get("dataset")
    if not isinstance(dataset, Mapping):
        return
    raw_paths = dataset.get("tick_paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return
    resolved: list[Path] = []
    for index, item in enumerate(raw_paths):
        path = Path(item)
        if not path.is_absolute():
            path = (Path(base_directory) / path).resolve()
        else:
            path = path.resolve()
        if not path.is_file():
            raise StudySpecError(
                f"study.dataset.tick_paths[{index}] is not an existing file: {path}"
            )
        resolved.append(path)
    instrument = str(dataset.get("instrument") or "ES")
    levels = {**DEFAULT_LEVELS_SETTINGS, **dict(study.get("levels") or {})}
    format_profile = resolve_tick_format_profile(dataset.get("tick_format_profile"))
    table = build_prior_profile_table_from_paths(
        resolved,
        instrument=instrument,
        value_area_pct=float(levels["value_area_pct"]),
        prior_day_aggregation_ticks=int(levels["prior_day_profile_aggregation_ticks"]),
        prior_week_aggregation_ticks=int(levels["prior_week_profile_aggregation_ticks"]),
        prior_month_aggregation_ticks=int(levels["prior_month_profile_aggregation_ticks"]),
        format_profile=format_profile,
    )
    parquet = output_dir / STUDY_PRIOR_PROFILE_PARQUET
    table.to_parquet(parquet)
    source_id = compute_tick_source_id(resolved, format_profile=format_profile)
    for run in expansion.experiment.get("runs") or []:
        if not isinstance(run, dict):
            continue
        run_ds = dict(run.get("dataset") or {})
        run_ds["prior_profile_table_path"] = str(parquet)
        run_ds["tick_source_id"] = source_id
        run["dataset"] = run_ds


def execute_study_cell(
    task: tuple[dict[str, Any], str],
) -> dict[str, Any]:
    """Execute one cell; always return ok/failed payload (never raise to pool)."""
    run_spec, base_directory = task
    name = str(run_spec["name"])
    baseline_cfg = _random_baseline_cfg(run_spec.get(_DA5_RANDOM_BASELINE_KEY))
    engine_spec = {key: value for key, value in run_spec.items() if key != _DA5_RANDOM_BASELINE_KEY}
    try:
        state = run_experiment(
            engine_spec,
            base_directory=base_directory,
            execution_origin="study",
            cache_policy="read_write",
        )
        bundle = build_research_bundle(state)
        index_row = build_index_row_from_state(name=name, state=state, bundle=bundle)
        trades = state.get("trades")
        index_row.update(
            direction_index_fields(
                trades if isinstance(trades, pd.DataFrame) else None,
                trade_count=index_row.get("trade_count"),
                collision=state.get("direction_collision_diagnostic"),
            )
        )
        try:
            index_row.update(
                random_baseline_fields(
                    cfg=baseline_cfg,
                    state=state,
                    run_spec=engine_spec,
                    expectancy_r=index_row.get("expectancy_r"),
                )
            )
        except Exception:  # noqa: BLE001 — null must not fail a successful cell
            index_row.update(_empty_random_baseline_fields())
        return {
            "status": "ok",
            "name": name,
            "bundle": bundle,
            "index_row": index_row,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — study layer must continue
        return {
            "status": "failed",
            "name": name,
            "bundle": None,
            "index_row": _failed_index_row(name),
            "error": f"{type(exc).__name__}: {exc}",
        }


def cost_hint_lines(
    expansion: ExpansionResult,
    *,
    workers: int,
) -> list[str]:
    """Human/agent cost hints for expand/run previews."""
    lines = [
        f"run_count={expansion.run_count}",
        f"workers={workers}",
    ]
    armed: list[str] = []
    for run in expansion.experiment.get("runs") or []:
        for section in ("grid", "validation", "walk_forward"):
            cfg = run.get(section) or {}
            if isinstance(cfg, Mapping) and cfg.get("enabled") is True:
                armed.append(f"{run.get('name')}.{section}")
    if armed:
        preview = ", ".join(armed[:12])
        suffix = " ..." if len(armed) > 12 else ""
        lines.append(
            f"WARNING: enabled grid/validation/walk_forward dominates runtime: {preview}{suffix}"
        )
    else:
        lines.append("batteries: grid/validation/walk_forward disabled on all cells")
    return lines


def _write_results_index(
    output_dir: Path,
    rows_by_name: Mapping[str, Mapping[str, Any]],
    run_names: list[str],
) -> Path:
    ordered: list[dict[str, Any]] = []
    for name in run_names:
        if name in rows_by_name:
            ordered.append(dict(rows_by_name[name]))
        else:
            ordered.append({**_failed_index_row(name), "status": "pending", "bundle_path": None})
    frame = pd.DataFrame(ordered)
    for key in STUDY_INDEX_KEYS:
        if key not in frame.columns:
            frame[key] = None
    frame = frame.loc[:, list(STUDY_INDEX_KEYS)]
    path = output_dir / "results_index.csv"
    tmp = path.with_name(".results_index.csv.tmp")
    frame.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return path


def _load_existing_index_rows(output_dir: Path) -> dict[str, dict[str, Any]]:
    path = output_dir / "results_index.csv"
    if not path.is_file():
        return {}
    frame = pd.read_csv(path)
    if frame.empty or "run_name" not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for record in frame.to_dict(orient="records"):
        name = record.get("run_name")
        if isinstance(name, str):
            rows[name] = dict(record)
    return rows


def _resolve_study_output_dir(
    study_path: Path,
    spec: Mapping[str, Any],
    output_dir: str | Path | None,
) -> Path:
    study = spec["study"]
    configured = output_dir or study.get("output_dir") or f"results/studies/{study['name']}"
    out = Path(configured)
    if not out.is_absolute():
        out = (study_path.parent / out).resolve()
    else:
        out = out.resolve()
    return out


_LOCK_REGION_BYTES = 1


def _lock_held_error(output_dir: Path) -> StudySpecError:
    return StudySpecError(
        f"Another study run holds the lock on {output_dir}; wait or use a different --output-dir"
    )


def _lock_acquire_error(output_dir: Path, exc: BaseException) -> StudySpecError:
    return StudySpecError(f"Unable to acquire exclusive study lock on {output_dir}: {exc}")


def _prepare_lock_region(handle: IO[bytes]) -> None:
    """Ensure a lockable byte exists (required by Windows ``msvcrt.locking``)."""
    handle.seek(0, os.SEEK_END)
    if handle.tell() < _LOCK_REGION_BYTES:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)


def _is_lock_contention(exc: BaseException) -> bool:
    """True only for non-blocking 'already held' failures (not ENOSYS/EINVAL/…)."""
    if isinstance(exc, BlockingIOError):
        return True
    if isinstance(exc, OSError):
        return int(getattr(exc, "errno", -1) or -1) in _LOCK_CONTENTION_ERRNOS
    return False


def _acquire_exclusive_lock(handle: IO[bytes], *, output_dir: Path) -> None:
    """Non-blocking exclusive lock via POSIX ``fcntl`` or Windows ``msvcrt``.

    Contention → ``Another study run holds the lock…``. Other OS failures
    (unsupported flock, bad handle, I/O) keep a distinct error so operators
    are not told a phantom concurrent run exists.
    """
    _prepare_lock_region(handle)
    fd = handle.fileno()
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if _is_lock_contention(exc):
                raise _lock_held_error(output_dir) from exc
            raise _lock_acquire_error(output_dir, exc) from exc
    if msvcrt is not None:
        try:
            # ``msvcrt.locking`` locks from the current file position.
            handle.seek(0)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, _LOCK_REGION_BYTES)
            return
        except OSError as exc:
            if _is_lock_contention(exc):
                raise _lock_held_error(output_dir) from exc
            raise _lock_acquire_error(output_dir, exc) from exc
    raise StudySpecError(
        "Exclusive study directory lock is unavailable on this Python runtime "
        "(need POSIX fcntl or Windows msvcrt)"
    )


def _release_exclusive_lock(handle: IO[bytes]) -> None:
    fd = handle.fileno()
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    if msvcrt is not None:
        # Unlock the same byte region that acquire locked (position-sensitive).
        handle.seek(0)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, _LOCK_REGION_BYTES)


@contextmanager
def _study_dir_lock(output_dir: Path) -> Iterator[None]:
    """Fail-closed exclusive lock so concurrent study runs cannot clobber ledgers.

    POSIX uses ``fcntl.flock``; Windows uses ``msvcrt.locking``. Both are
    released on process exit, so a crashed run cannot leave a stale lock.
    Importing this module must not require POSIX-only ``fcntl`` — the Studies
    viewer loads ``thesistester.study`` on Windows.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / ".study.lock"
    fh = open(lock_path, "ab+")
    locked = False
    try:
        _acquire_exclusive_lock(fh, output_dir=output_dir)
        locked = True
        yield
    finally:
        try:
            if locked:
                _release_exclusive_lock(fh)
        finally:
            fh.close()


def prepare_study_expansion(
    study_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    write_artifacts: bool = True,
) -> tuple[dict[str, Any], ExpansionResult, Path, Path]:
    """Load StudySpec, expand, optionally write artifacts.

    Relative dataset paths that exist under the StudySpec parent are pinned
    absolute on the expansion (identity hash stays on the unpinned spec).

    Returns ``(spec, expansion, output_dir, base_directory)``.
    """
    study_path = Path(study_path).resolve()
    spec = load_study_spec(study_path)
    out = _resolve_study_output_dir(study_path, spec, output_dir)
    spec_parent = study_path.parent
    expansion = expand_study(spec, source_spec_parent=spec_parent)
    if write_artifacts:
        write_expansion_artifacts(
            out,
            normalized_spec=spec,
            expansion=expansion,
            source_spec_parent=spec_parent,
        )
    return spec, expansion, out, spec_parent


def _apply_cell_result(
    output_dir: Path,
    *,
    run_names: list[str],
    index_by_name: dict[str, dict[str, Any]],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one cell result into ledger + index; return updated ledger."""
    ledger = load_ledger(output_dir)
    if ledger is None:
        raise StudySpecError(f"Missing study ledger under {output_dir}")
    name = str(payload["name"])
    status = str(payload["status"])
    bundle_name = f"{name}.research.zip"

    if status == "ok":
        bundle = payload.get("bundle")
        if not isinstance(bundle, (bytes, bytearray)):
            ledger = mark_cell(
                ledger,
                name,
                status="failed",
                error="ok payload missing bundle bytes",
                bundle_path=None,
                finished=True,
            )
            row = dict(payload.get("index_row") or _failed_index_row(name))
            row["status"] = "failed"
            row["bundle_path"] = None
            index_by_name[name] = row
        else:
            (output_dir / bundle_name).write_bytes(bundle)
            ledger = mark_cell(
                ledger,
                name,
                status="ok",
                error=None,
                bundle_path=bundle_name,
                finished=True,
            )
            row = dict(payload["index_row"])
            row["bundle_path"] = bundle_name
            row["status"] = "ok"
            index_by_name[name] = row
    else:
        # Drop stale zip from a prior ok if this cell is being re-run after force.
        stale = output_dir / bundle_name
        if stale.is_file():
            try:
                stale.unlink()
            except OSError:
                pass
        ledger = mark_cell(
            ledger,
            name,
            status="failed",
            error=str(payload.get("error") or "unknown error"),
            bundle_path=None,
            finished=True,
        )
        row = dict(payload.get("index_row") or _failed_index_row(name))
        row["status"] = "failed"
        row["bundle_path"] = None
        index_by_name[name] = row

    save_ledger(output_dir, ledger)
    _write_results_index(output_dir, index_by_name, run_names)
    return ledger


def _finalize_running_cells(
    output_dir: Path,
    *,
    todo: list[str],
    run_names: list[str],
    index_by_name: dict[str, dict[str, Any]],
    error: str,
) -> None:
    """Mark any cells still ``running`` as failed (pool death / interrupt)."""
    ledger = load_ledger(output_dir)
    if ledger is None:
        return
    cells = ledger.get("cells") or {}
    dirty = False
    for name in todo:
        cell = cells.get(name) or {}
        if cell.get("status") == "running":
            ledger = mark_cell(
                ledger,
                name,
                status="failed",
                error=error,
                bundle_path=None,
                finished=True,
            )
            row = _failed_index_row(name)
            row["status"] = "failed"
            row["bundle_path"] = None
            index_by_name[name] = row
            dirty = True
    if dirty:
        save_ledger(output_dir, ledger)
        _write_results_index(output_dir, index_by_name, run_names)


def run_study(
    study_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    workers: int | None = None,
    confirm: bool = False,
    force: bool = False,
    cell_executor: Callable[[tuple[dict[str, Any], str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Expand, enforce confirm/identity gates, then execute cells with ledger/resume.

    Gates run **before** writing expansion artifacts so refuse paths cannot drift
    on-disk ``study.spec.yaml`` / factor maps relative to an existing ledger.
    """
    # Expand in memory first — no artifact writes until gates pass.
    spec, expansion, out, base_directory = prepare_study_expansion(
        study_path,
        output_dir=output_dir,
        write_artifacts=False,
    )
    study = spec["study"]
    workers_n = int(workers if workers is not None else study.get("workers", 1))
    if workers_n < 1:
        raise StudySpecError("workers must be >= 1")

    confirm_above = int(study.get("confirm_above_runs", 200))
    if expansion.run_count >= confirm_above and not confirm:
        raise StudySpecError(
            f"Expansion has {expansion.run_count} run(s) >= confirm_above_runs="
            f"{confirm_above}; re-run with --confirm"
        )

    run_names = [str(run["name"]) for run in expansion.experiment["runs"]]
    existing = load_ledger(out)
    prior_hash = existing.get("study_identity_hash") if existing is not None else None
    if existing is not None:
        if prior_hash != expansion.study_identity_hash and not force:
            raise StudySpecError(
                "Existing study.ledger.json identity hash does not match this "
                "StudySpec expansion; pass --force to re-run, or use a new output_dir"
            )

    with _study_dir_lock(out):
        # Re-check identity under the lock (another process may have written).
        existing = load_ledger(out)
        prior_hash = existing.get("study_identity_hash") if existing is not None else None
        if existing is not None:
            if prior_hash != expansion.study_identity_hash and not force:
                raise StudySpecError(
                    "Existing study.ledger.json identity hash does not match this "
                    "StudySpec expansion; pass --force to re-run, or use a new output_dir"
                )

        # Gates passed — build the prior-profile table once, then persist
        # expansion artifacts so workers receive the parquet path.
        out.mkdir(parents=True, exist_ok=True)
        _prepare_study_prior_profile(
            spec,
            expansion,
            output_dir=out,
            base_directory=Path(base_directory),
        )
        write_expansion_artifacts(
            out,
            normalized_spec=spec,
            expansion=expansion,
            source_spec_parent=base_directory,
        )

        identity_changed = existing is not None and prior_hash != expansion.study_identity_hash
        if existing is None or (force and identity_changed):
            # Fresh ledger, or forced identity swap → drop orphan cells.
            ledger = empty_ledger(
                study_identity_hash=expansion.study_identity_hash,
                run_names=run_names,
            )
        else:
            ledger = dict(existing)
            ledger["study_identity_hash"] = expansion.study_identity_hash
            prior_cells = dict(ledger.get("cells") or {})
            cells: dict[str, Any] = {}
            for name in run_names:
                cell = dict(
                    prior_cells.get(name)
                    or {
                        "status": "pending",
                        "started_at": None,
                        "finished_at": None,
                        "error": None,
                        "bundle_path": None,
                    }
                )
                if force:
                    cell.update(
                        {
                            "status": "pending",
                            "started_at": None,
                            "finished_at": None,
                            "error": None,
                            "bundle_path": None,
                        }
                    )
                cells[name] = cell
            ledger["cells"] = cells

        if confirm:
            ledger = record_confirmation(ledger, run_count=expansion.run_count)
        save_ledger(out, ledger)

        index_by_name = _load_existing_index_rows(out)
        # Scope index to current expansion names only (drop orphans).
        index_by_name = {name: row for name, row in index_by_name.items() if name in set(run_names)}
        if force:
            for name in run_names:
                index_by_name.pop(name, None)

        todo = cells_to_run(
            load_ledger(out) or ledger,
            run_names,
            force=force,
            output_dir=out,
        )
        runs_by_name = {str(run["name"]): dict(run) for run in expansion.experiment["runs"]}
        executor_fn = cell_executor or execute_study_cell
        report_cfg = (
            spec.get("study", {}).get("report") if isinstance(spec.get("study"), Mapping) else None
        )
        baseline_cfg = _random_baseline_cfg(
            report_cfg.get("random_baseline") if isinstance(report_cfg, Mapping) else None
        )
        tasks = []
        for name in todo:
            task_spec = dict(runs_by_name[name])
            task_spec[_DA5_RANDOM_BASELINE_KEY] = baseline_cfg
            tasks.append((task_spec, str(base_directory)))

        # Mark running before dispatch.
        ledger = load_ledger(out) or ledger
        for name in todo:
            ledger = mark_cell(ledger, name, status="running", started=True)
        save_ledger(out, ledger)

        # Pool only the picklable module-level default executor. Injected
        # cell_executor callables (tests) always run in-process.
        use_pool = (
            workers_n > 1
            and len(tasks) > 1
            and cell_executor is None
            and executor_fn is execute_study_cell
        )
        try:
            if not use_pool:
                for task in tasks:
                    payload = executor_fn(task)
                    _apply_cell_result(
                        out,
                        run_names=run_names,
                        index_by_name=index_by_name,
                        payload=payload,
                    )
            else:
                with ProcessPoolExecutor(
                    max_workers=min(workers_n, len(tasks)),
                    mp_context=multiprocessing.get_context("spawn"),
                ) as pool:
                    future_to_name = {
                        pool.submit(execute_study_cell, task): todo[index]
                        for index, task in enumerate(tasks)
                    }
                    for future in as_completed(future_to_name):
                        name = future_to_name[future]
                        try:
                            payload = future.result()
                        except Exception as exc:  # noqa: BLE001 — keep study loop alive
                            payload = {
                                "status": "failed",
                                "name": name,
                                "bundle": None,
                                "index_row": _failed_index_row(name),
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        _apply_cell_result(
                            out,
                            run_names=run_names,
                            index_by_name=index_by_name,
                            payload=payload,
                        )
        finally:
            _finalize_running_cells(
                out,
                todo=todo,
                run_names=run_names,
                index_by_name=index_by_name,
                error="WorkerInterrupted: cell left running after study loop exit",
            )

        # Final ordered index (includes soft-resumed ok rows).
        ledger = load_ledger(out) or ledger
        cells = ledger.get("cells") or {}

        for name in run_names:
            cell = cells.get(name) or {}
            status = cell.get("status", "pending")
            bundle_rel = cell.get("bundle_path")
            if name not in index_by_name:
                if status == "ok" and isinstance(bundle_rel, str) and bundle_rel:
                    index_by_name[name] = _index_row_from_existing_bundle(
                        name, output_dir=out, bundle_rel=bundle_rel
                    )
                else:
                    row = _failed_index_row(name)
                    row["status"] = status
                    row["bundle_path"] = bundle_rel
                    # Failed/pending must never carry PF/WR (RS-D7).
                    row["profit_factor"] = None
                    row["win_rate"] = None
                    index_by_name[name] = row
                continue

            row = dict(index_by_name[name])
            row["status"] = status
            bundle_rel = cell.get("bundle_path") or row.get("bundle_path")
            if status == "ok" and isinstance(bundle_rel, str) and bundle_rel:
                # Repair historically poisoned soft-resume rows (ok + zip, null metrics).
                if _metric_missing(row.get("trade_count")) and _metric_missing(
                    row.get("expectancy_r")
                ):
                    index_by_name[name] = _index_row_from_existing_bundle(
                        name,
                        output_dir=out,
                        bundle_rel=bundle_rel,
                        prior_row=row,
                    )
                elif _metric_missing(row.get("profit_factor")) or _metric_missing(
                    row.get("win_rate")
                ):
                    # Pre-D7 ok rows often have trade metrics but lack PF/WR columns.
                    index_by_name[name] = _backfill_pf_wr_from_bundle(
                        row, output_dir=out, bundle_rel=bundle_rel
                    )
                else:
                    index_by_name[name] = row
            else:
                # Status sync to failed/pending must not retain stale ok PF/WR.
                row["profit_factor"] = None
                row["win_rate"] = None
                if "bundle_path" in cell:
                    row["bundle_path"] = cell.get("bundle_path")
                index_by_name[name] = row

        index_path = _write_results_index(out, index_by_name, run_names)
        final_ledger = load_ledger(out)
        return {
            "output_dir": str(out),
            "run_count": expansion.run_count,
            "executed": len(todo),
            "workers": workers_n,
            "ledger_path": str(out / "study.ledger.json"),
            "results_index_path": str(index_path),
            "study_identity_hash": expansion.study_identity_hash,
            "ledger": final_ledger,
            "run_names": list(run_names),
            "cost_hints": cost_hint_lines(expansion, workers=workers_n),
        }
