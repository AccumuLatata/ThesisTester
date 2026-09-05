"""Study overview aggregator (RS4).

Joins ``results_index.csv`` ⟕ ``study.expansion.json`` on ``run_name``, resolves
``profit_factor`` / ``win_rate`` from bundle ``trade_summary`` when absent from
the index, and emits ranked / low-N / group / OTF-Δ views with honesty text.
DA2 also writes ``study.direction.csv`` from index direction-split keys when
present (nulls on older indexes). This module does not rewrite the index.

RS-D7 writers add additive index ``profit_factor`` / ``win_rate`` columns; this
module prefers those when present and keeps the bundle fallback for older
indexes. It does not change Experiment ``schema_version``.
"""

from __future__ import annotations

import json
import math
import numbers
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from thesistester.setup import normalize_otf_filter_config
from thesistester.study.schema import load_study_spec

OVERVIEW_CSV = "study.overview.csv"
OVERVIEW_MD = "study.overview.md"
OTF_DELTA_CSV = "study.otf_delta.csv"
DIRECTION_CSV = "study.direction.csv"
EXPANSION_JSON = "study.expansion.json"
SPEC_YAML = "study.spec.yaml"
RESULTS_INDEX = "results_index.csv"

# Mirrors execute.DA_DIRECTION_INDEX_KEYS — do not import execute (cycle via briefing).
_DIRECTION_COLUMNS: tuple[str, ...] = (
    "long_trade_count",
    "short_trade_count",
    "long_expectancy_r",
    "short_expectancy_r",
    "long_share",
    "directional_integrity",
    "collision_pairs",
    "collision_resolved_long",
)

_HIGHER_IS_BETTER = frozenset({"expectancy_r", "total_r", "profit_factor", "trade_count"})
_LOWER_IS_BETTER = frozenset({"max_drawdown_r"})

_HONESTY_PARAGRAPH = (
    "Descriptive study ranking is not a validated edge. Ranking many closed "
    "cells invites severe multiple-testing bias: the top cell is a sample "
    "extreme under the study design, not independent confirmation. Prefer "
    "held-out / walk-forward evaluation, stage-first expansion, and "
    "non-zero commission/slippage before trusting expectancy ranks. Cells "
    "below `min_trades` are excluded from the ranked section and listed "
    "under low-N only."
)


@dataclass(frozen=True)
class StudyReportResult:
    """Artifacts produced by ``report_study``."""

    overview: pd.DataFrame
    ranked: pd.DataFrame
    low_n: pd.DataFrame
    unresolved: pd.DataFrame
    group_summaries: dict[str, pd.DataFrame]
    otf_delta: pd.DataFrame
    markdown: str
    paths: dict[str, Path]
    primary_metric: str
    min_trades: int
    multiple_testing: str
    best_cell_suppressed: bool
    study_name: str


class StudyReportError(ValueError):
    """Raised when a study directory cannot be aggregated."""


def otf_canonical_key(raw: Any) -> str:
    """Stable JSON key for a (possibly aliased) OTF factor value."""
    normalized = normalize_otf_filter_config(dict(raw) if isinstance(raw, Mapping) else raw)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def format_partner_levels(partners: Any) -> str:
    """Deterministic display for partner-set factor values."""
    if not isinstance(partners, (list, tuple)):
        return str(partners)
    return "+".join(str(item) for item in partners)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudyReportError(f"Unable to read {path}: {exc}") from exc


def _load_report_config(study_dir: Path) -> dict[str, Any]:
    spec_path = study_dir / SPEC_YAML
    if not spec_path.is_file():
        raise StudyReportError(f"Missing {SPEC_YAML} under {study_dir}")
    try:
        normalized = load_study_spec(spec_path)
    except Exception as exc:
        # Written study.spec.yaml is already normalized; tolerate re-validate
        # failures by reading the report block directly.
        try:
            payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as load_exc:
            raise StudyReportError(f"Unable to load {spec_path}: {load_exc}") from load_exc
        if not isinstance(payload, Mapping):
            raise StudyReportError(f"{SPEC_YAML} must be a mapping") from exc
        study = payload.get("study")
        if not isinstance(study, Mapping):
            raise StudyReportError(f"{SPEC_YAML} missing study mapping") from exc
        report = study.get("report")
        if not isinstance(report, Mapping):
            raise StudyReportError(f"{SPEC_YAML} missing study.report") from exc
        return {
            "study_name": str(study.get("name") or study_dir.name),
            "report": dict(report),
        }
    study = normalized["study"]
    return {
        "study_name": str(study["name"]),
        "report": dict(study["report"]),
    }


def _load_factor_map(study_dir: Path) -> dict[str, dict[str, Any]]:
    path = study_dir / EXPANSION_JSON
    if not path.is_file():
        raise StudyReportError(f"Missing {EXPANSION_JSON} under {study_dir}")
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        raise StudyReportError(f"{EXPANSION_JSON} must be a JSON object")
    factor_map = payload.get("factor_map")
    if not isinstance(factor_map, Mapping) or not factor_map:
        raise StudyReportError(f"{EXPANSION_JSON} must contain a non-empty factor_map")
    out: dict[str, dict[str, Any]] = {}
    for name, factors in factor_map.items():
        if not isinstance(factors, Mapping):
            raise StudyReportError(f"factor_map[{name!r}] must be an object")
        out[str(name)] = dict(factors)
    return out


def _load_results_index(study_dir: Path) -> pd.DataFrame:
    path = study_dir / RESULTS_INDEX
    if not path.is_file():
        raise StudyReportError(f"Missing {RESULTS_INDEX} under {study_dir}")
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, ValueError) as exc:
        raise StudyReportError(f"Unable to read {path}: {exc}") from exc
    if "run_name" not in frame.columns:
        raise StudyReportError(f"{RESULTS_INDEX} must include a run_name column")
    if frame["run_name"].duplicated().any():
        dupes = sorted(
            {str(name) for name in frame.loc[frame["run_name"].duplicated(), "run_name"]}
        )
        preview = ", ".join(dupes[:8])
        suffix = " ..." if len(dupes) > 8 else ""
        raise StudyReportError(
            f"{RESULTS_INDEX} contains duplicate run_name values: {preview}{suffix}"
        )
    return frame


def _bundle_path_within_study(study_dir: Path, bundle_rel: str) -> Path | None:
    """Resolve ``bundle_path`` and refuse absolute / ``..`` escapes outside study_dir."""
    raw = Path(bundle_rel)
    candidate = raw.expanduser().resolve() if raw.is_absolute() else (study_dir / raw).resolve()
    root = study_dir.resolve()
    if not candidate.is_relative_to(root):
        return None
    return candidate


def _read_bundle_trade_summary(bundle_path: Path) -> dict[str, Any] | None:
    """Return ``trade_summary`` dict from a research zip, or None if unavailable."""
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
    # Real bundles nest under trade_summary; tolerate a flat summary dict.
    nested = raw.get("trade_summary")
    if isinstance(nested, Mapping):
        return dict(nested)
    if "profit_factor" in raw or "win_rate" in raw or "trade_count" in raw:
        return dict(raw)
    return None


def _coerce_float(value: Any) -> float | None:
    """Coerce scalars (incl. NumPy / pandas) to float; drop bool/NaN."""
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
            return float(text)
        except ValueError:
            return None
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _coerce_float(item())
        except (ValueError, TypeError, OverflowError, RecursionError):
            return None
    return None


def _resolve_bundle_metrics(
    study_dir: Path,
    row: Mapping[str, Any],
) -> tuple[float | None, float | None, str]:
    """Return (profit_factor, win_rate, profit_factor_source).

    PF and win_rate resolve independently: index value wins per field; bundle
    ``trade_summary`` fills only the missing field(s). ``profit_factor_source``
    tracks PF provenance only.
    """
    index_pf = _coerce_float(row.get("profit_factor"))
    index_wr = _coerce_float(row.get("win_rate"))

    summary: dict[str, Any] | None = None
    if index_pf is None or index_wr is None:
        bundle_rel = row.get("bundle_path")
        if isinstance(bundle_rel, str) and bundle_rel.strip():
            bundle_path = _bundle_path_within_study(study_dir, bundle_rel)
            if bundle_path is not None:
                summary = _read_bundle_trade_summary(bundle_path)

    if index_pf is not None:
        pf, source = index_pf, "index"
    elif summary is not None:
        pf = _coerce_float(summary.get("profit_factor"))
        source = "bundle" if pf is not None else "missing"
    else:
        pf, source = None, "missing"

    if index_wr is not None:
        wr = index_wr
    elif summary is not None:
        wr = _coerce_float(summary.get("win_rate"))
    else:
        wr = None

    return pf, wr, source


def _flatten_factors(factors: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in factors.items():
        col = f"factor_{key}"
        if key == "partner_levels":
            flat[col] = format_partner_levels(value)
        elif key == "otf":
            flat[col] = otf_canonical_key(value)
            flat["factor_otf_enabled"] = bool(
                normalize_otf_filter_config(
                    dict(value) if isinstance(value, Mapping) else value
                ).get("enabled", False)
            )
        else:
            flat[col] = value
    return flat


def _direction_frame(overview: pd.DataFrame) -> pd.DataFrame:
    """``run_name`` plus DA2 keys. Missing keys stay null (older indexes)."""
    cols = ["run_name", *_DIRECTION_COLUMNS]
    if overview.empty:
        return pd.DataFrame(columns=list(cols))
    frame = overview.copy()
    for column in cols:
        if column not in frame.columns:
            frame[column] = None
    return frame.loc[:, list(cols)].reset_index(drop=True)


def build_overview_frame(
    *,
    study_dir: Path,
    index: pd.DataFrame,
    factor_map: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    """Left-join index rows to factor tags; resolve PF/win_rate."""
    rows: list[dict[str, Any]] = []
    # Deterministic: walk factor_map order first, then any orphan index rows.
    seen: set[str] = set()
    ordered_names = list(factor_map.keys())
    index_by_name = {
        str(name): record
        for name, record in index.set_index("run_name", drop=False).to_dict(orient="index").items()
    }
    for name in ordered_names:
        seen.add(name)
        base = dict(index_by_name.get(name) or {"run_name": name})
        base["run_name"] = name
        flat = _flatten_factors(factor_map[name])
        pf, wr, source = _resolve_bundle_metrics(study_dir, base)
        base["profit_factor"] = pf
        base["win_rate"] = wr
        base["profit_factor_source"] = source
        # Expansion join completeness flag.
        base["factors_joined"] = True
        rows.append({**base, **flat})

    for name, record in sorted(index_by_name.items()):
        if name in seen:
            continue
        base = dict(record)
        base["run_name"] = name
        pf, wr, source = _resolve_bundle_metrics(study_dir, base)
        base["profit_factor"] = pf
        base["win_rate"] = wr
        base["profit_factor_source"] = source
        base["factors_joined"] = False
        rows.append(base)

    if not rows:
        return pd.DataFrame(columns=["run_name", "profit_factor", "profit_factor_source"])

    frame = pd.DataFrame(rows)
    # Stable column order: identity / status / metrics / factors.
    lead = [
        "run_name",
        "status",
        "trade_count",
        "long_trade_count",
        "short_trade_count",
        "long_expectancy_r",
        "short_expectancy_r",
        "long_share",
        "directional_integrity",
        "collision_pairs",
        "collision_resolved_long",
        "expectancy_r",
        "total_r",
        "max_drawdown_r",
        "profit_factor",
        "win_rate",
        "profit_factor_source",
        "bundle_hash",
        "bundle_path",
        "execution_origin",
        "factors_joined",
    ]
    factor_cols = sorted(c for c in frame.columns if c.startswith("factor_"))
    other = [c for c in frame.columns if c not in lead and c not in factor_cols]
    ordered = [c for c in lead if c in frame.columns] + factor_cols + sorted(other)
    return frame.loc[:, ordered].sort_values("run_name", kind="mergesort").reset_index(drop=True)


def _metric_sort_ascending(primary_metric: str) -> bool:
    if primary_metric in _LOWER_IS_BETTER:
        return True
    # Unknown primaries default to higher-is-better (same as expectancy/total_r).
    if primary_metric in _HIGHER_IS_BETTER:
        return False
    return False


def _factors_joined_mask(work: pd.DataFrame) -> pd.Series:
    """True for expansion-joined cells only (orphans stay in overview CSV)."""
    if "factors_joined" not in work.columns:
        return pd.Series(True, index=work.index)
    joined = work["factors_joined"]
    if pd.api.types.is_bool_dtype(joined):
        return joined.fillna(False)

    # Tolerate object/CSV round-trips without treating "False" as truthy.
    def _as_bool(value: Any) -> bool:
        if value is True:
            return True
        if value is False or value is None:
            return False
        try:
            if pd.isna(value):
                return False
        except (TypeError, ValueError):
            pass
        if isinstance(value, numbers.Integral) and not isinstance(value, bool):
            return int(value) == 1
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes"}
        return False

    return joined.map(_as_bool)


def split_ranked_and_low_n(
    overview: pd.DataFrame,
    *,
    primary_metric: str,
    min_trades: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Partition overview into ranked, low-N, and unresolved-primary sections."""
    if overview.empty:
        empty = overview.copy()
        return empty, empty, empty

    work = overview.copy()
    work["trade_count"] = pd.to_numeric(work.get("trade_count"), errors="coerce")
    work[primary_metric] = pd.to_numeric(work.get(primary_metric), errors="coerce")

    eligible_status = work["status"].astype(str).eq("ok") if "status" in work.columns else True
    joined = _factors_joined_mask(work)
    has_n = work["trade_count"].fillna(-1) >= float(min_trades)
    has_metric = work[primary_metric].notna()
    # Index-only orphans (factors_joined=False) remain in overview CSV but must
    # not enter ranked/low-N/unresolved or be crowned as top descriptive cells.
    ranked_mask = eligible_status & joined & has_n & has_metric
    low_mask = eligible_status & joined & ~has_n
    # High-N ok cells with a null primary (e.g. PF missing) must not vanish from MD.
    unresolved_mask = eligible_status & joined & has_n & ~has_metric

    ascending = _metric_sort_ascending(primary_metric)
    ranked = (
        work.loc[ranked_mask]
        .sort_values(
            [primary_metric, "run_name"],
            ascending=[ascending, True],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )
    low_n = work.loc[low_mask].sort_values("run_name", kind="mergesort").reset_index(drop=True)
    unresolved = (
        work.loc[unresolved_mask].sort_values("run_name", kind="mergesort").reset_index(drop=True)
    )
    return ranked, low_n, unresolved


def build_group_summaries(
    overview: pd.DataFrame,
    *,
    group_by: Sequence[str],
    primary_metric: str,
    min_trades: int,
) -> dict[str, pd.DataFrame]:
    """Median/mean primary metric and cell counts per group_by axis."""
    summaries: dict[str, pd.DataFrame] = {}
    if overview.empty:
        return summaries

    work = overview.copy()
    if "status" in work.columns:
        work = work.loc[work["status"].astype(str).eq("ok")].copy()
    work = work.loc[_factors_joined_mask(work)].copy()
    work["trade_count"] = pd.to_numeric(work.get("trade_count"), errors="coerce")
    work[primary_metric] = pd.to_numeric(work.get(primary_metric), errors="coerce")
    # Match ranked-eligible contract: N gate + non-null primary (counts == averages).
    work = work.loc[
        (work["trade_count"].fillna(-1) >= float(min_trades)) & work[primary_metric].notna()
    ].copy()

    for axis in group_by:
        col = f"factor_{axis}"
        if col not in work.columns:
            continue
        grouped = (
            work.groupby(col, dropna=False, sort=True)
            .agg(
                cell_count=("run_name", "count"),
                mean_metric=(primary_metric, "mean"),
                median_metric=(primary_metric, "median"),
                mean_trade_count=("trade_count", "mean"),
            )
            .reset_index()
            .rename(
                columns={
                    col: axis,
                    "mean_metric": f"mean_{primary_metric}",
                    "median_metric": f"median_{primary_metric}",
                }
            )
        )
        summaries[str(axis)] = grouped
    return summaries


def build_otf_delta(
    overview: pd.DataFrame,
    *,
    factor_map: Mapping[str, Mapping[str, Any]],
    otf_baseline: Mapping[str, Any],
    primary_metric: str,
    min_trades: int,
) -> pd.DataFrame:
    """Compute metric(OTF variant) − metric(baseline) for each non-OTF tuple."""
    columns = [
        "non_otf_key",
        "run_name_variant",
        "run_name_baseline",
        "factor_otf_variant",
        "factor_otf_baseline",
        f"{primary_metric}_variant",
        f"{primary_metric}_baseline",
        f"delta_{primary_metric}",
        "trade_count_variant",
        "trade_count_baseline",
    ]
    if overview.empty or "factor_otf" not in overview.columns:
        return pd.DataFrame(columns=columns)

    baseline_key = otf_canonical_key(otf_baseline)
    # Non-OTF axes from any factor_map entry that includes otf.
    sample = next(iter(factor_map.values()), {})
    non_otf_axes = [key for key in sample if key != "otf"]

    def _non_otf_key(factors: Mapping[str, Any]) -> str:
        payload: dict[str, Any] = {}
        for axis in non_otf_axes:
            value = factors.get(axis)
            if axis == "partner_levels":
                payload[axis] = list(value) if isinstance(value, (list, tuple)) else value
            else:
                payload[axis] = value
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    work = overview.copy()
    if "status" in work.columns:
        work = work.loc[work["status"].astype(str).eq("ok")].copy()
    work["trade_count"] = pd.to_numeric(work.get("trade_count"), errors="coerce")
    work[primary_metric] = pd.to_numeric(work.get(primary_metric), errors="coerce")

    by_name = {str(r["run_name"]): r for _, r in work.iterrows()}
    groups: dict[str, list[str]] = {}
    for name, factors in factor_map.items():
        if "otf" not in factors:
            continue
        groups.setdefault(_non_otf_key(factors), []).append(name)

    rows: list[dict[str, Any]] = []
    for non_otf_key, names in sorted(groups.items()):
        baseline_name = None
        for name in names:
            factors = factor_map[name]
            if otf_canonical_key(factors["otf"]) == baseline_key:
                baseline_name = name
                break
        if baseline_name is None or baseline_name not in by_name:
            continue
        baseline_row = by_name[baseline_name]
        baseline_metric = _coerce_float(baseline_row.get(primary_metric))
        baseline_n = _coerce_float(baseline_row.get("trade_count"))
        if baseline_metric is None:
            continue
        for name in sorted(names):
            if name == baseline_name:
                continue
            if name not in by_name:
                continue
            variant = by_name[name]
            variant_metric = _coerce_float(variant.get(primary_metric))
            if variant_metric is None:
                continue
            # Still emit deltas for low-N cells; consumers can filter. Ranked
            # overview already separates low-N. Keep delta rows when either
            # side meets min_trades OR always — plan: compute for each non-OTF
            # tuple. Emit all numeric pairs; include trade counts for honesty.
            rows.append(
                {
                    "non_otf_key": non_otf_key,
                    "run_name_variant": name,
                    "run_name_baseline": baseline_name,
                    "factor_otf_variant": otf_canonical_key(factor_map[name]["otf"]),
                    "factor_otf_baseline": baseline_key,
                    f"{primary_metric}_variant": variant_metric,
                    f"{primary_metric}_baseline": baseline_metric,
                    f"delta_{primary_metric}": variant_metric - baseline_metric,
                    "trade_count_variant": _coerce_float(variant.get("trade_count")),
                    "trade_count_baseline": baseline_n,
                    "meets_min_trades": (
                        (baseline_n is not None and baseline_n >= min_trades)
                        and (
                            _coerce_float(variant.get("trade_count")) is not None
                            and _coerce_float(variant.get("trade_count")) >= min_trades
                        )
                    ),
                }
            )

    if not rows:
        return pd.DataFrame(columns=columns + ["meets_min_trades"])
    frame = pd.DataFrame(rows)
    return frame.sort_values(
        ["non_otf_key", "run_name_variant"],
        kind="mergesort",
    ).reset_index(drop=True)


def _briefing_settings_suffix(row: Mapping[str, Any] | pd.Series) -> str:
    """Compact factor + best-grid clause for the overview top-cell sentence."""
    parts: list[str] = []
    for key, label in (
        ("factor_partner_levels", "partner"),
        ("factor_trigger", "trigger"),
        ("factor_trigger_timeframe", "tf"),
        ("factor_direction", "direction"),
    ):
        if key not in row:
            continue
        val = row.get(key)
        if val is None:
            continue
        try:
            if pd.isna(val):
                continue
        except (TypeError, ValueError):
            pass
        text = str(val).strip()
        if text:
            parts.append(f"{label}={text}")
    sl = row.get("best_grid_stop_loss_ticks") if "best_grid_stop_loss_ticks" in row else None
    tp = row.get("best_grid_take_profit_ticks") if "best_grid_take_profit_ticks" in row else None
    sl_txt = _fmt_num(sl) if sl is not None else "—"
    tp_txt = _fmt_num(tp) if tp is not None else "—"
    if sl_txt != "—" or tp_txt != "—":
        parts.append(f"best SL/TP {sl_txt}/{tp_txt}")
    if not parts:
        return ""
    return " with " + ", ".join(parts)


def _fmt_num(value: Any) -> str:
    number = _coerce_float(value)
    if number is None:
        return "—"
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    return f"{number:.6g}"


def _md_table(frame: pd.DataFrame, columns: list[str], *, limit: int = 50) -> list[str]:
    cols = [c for c in columns if c in frame.columns]
    if not cols or frame.empty:
        return ["_(none)_", ""]
    head = frame.loc[:, cols].head(limit)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for _, row in head.iterrows():
        cells: list[str] = []
        for col in cols:
            val = row[col]
            if (
                col.endswith("_r")
                or col
                in {
                    "profit_factor",
                    "win_rate",
                    "trade_count",
                }
                or col.startswith("mean_")
                or col.startswith("median_")
                or col.startswith("delta_")
            ):
                cells.append(_fmt_num(val))
            else:
                text = "—" if pd.isna(val) else str(val)
                cells.append(text.replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")
    if len(frame) > limit:
        lines.append(f"_… {len(frame) - limit} more row(s)_")
    lines.append("")
    return lines


def render_overview_markdown(
    *,
    study_name: str,
    report: Mapping[str, Any],
    overview: pd.DataFrame,
    ranked: pd.DataFrame,
    low_n: pd.DataFrame,
    unresolved: pd.DataFrame,
    group_summaries: Mapping[str, pd.DataFrame],
    otf_delta: pd.DataFrame,
    best_cell_suppressed: bool,
) -> str:
    """Human/agent summary with honesty caveats (deterministic)."""
    primary = str(report["primary_metric"])
    min_trades = int(report["min_trades"])
    multiple_testing = str(report["multiple_testing"])
    lines: list[str] = [
        f"# Study overview: {study_name}",
        "",
        "## Honesty",
        "",
        _HONESTY_PARAGRAPH,
        "",
        f"- `min_trades` filter: **{min_trades}**",
        f"- `multiple_testing` mode: **{multiple_testing}**",
        (
            f"- Cells in overview: **{len(overview)}**; ranked: **{len(ranked)}**; "
            f"low-N: **{len(low_n)}**; unresolved primary: **{len(unresolved)}**"
        ),
        "",
    ]

    lines.extend(["## Ranked cells", ""])
    if best_cell_suppressed:
        lines.append(
            "`multiple_testing: error` — best-cell crowning suppressed. "
            "Ranked table below is descriptive only; do not treat row 1 as a winner."
        )
        lines.append("")
    elif not ranked.empty:
        top = ranked.iloc[0]
        lines.append(
            f"Top descriptive cell by `{primary}` (not a validated edge): "
            f"`{top['run_name']}` = {_fmt_num(top.get(primary))} "
            f"(N={_fmt_num(top.get('trade_count'))})"
            f"{_briefing_settings_suffix(top)}."
        )
        lines.append("")
        lines.append(
            "Time-of-day is not a StudySpec factor. After `study run`, Inspect "
            "projects NY RTH segments from that cell's `trades.parquet` "
            "(post-hoc; no re-sim). The SL/TP grid is per-cell "
            "(`best_grid_*` / zip `grid_results.parquet`), not the factor "
            "cartesian in the ranked table."
        )
        lines.append("")
    else:
        lines.append("No cells met the ranked criteria.")
        lines.append("")

    rank_cols = [
        "run_name",
        "trade_count",
        primary,
        "profit_factor",
        "max_drawdown_r",
        "total_r",
        "best_grid_stop_loss_ticks",
        "best_grid_take_profit_ticks",
        "profit_factor_source",
    ]
    lines.extend(_md_table(ranked, rank_cols))

    lines.extend(["## Low-N cells", ""])
    lines.append(f"Cells with `trade_count < {min_trades}` (excluded from ranked winners).")
    lines.append("")
    lines.extend(_md_table(low_n, ["run_name", "trade_count", primary, "profit_factor"]))

    lines.extend(["## Unresolved primary metric", ""])
    lines.append(
        f"Ok cells with `trade_count >= {min_trades}` but null `{primary}` "
        "(e.g. missing profit factor); excluded from ranked and group summaries."
    )
    lines.append("")
    lines.extend(
        _md_table(
            unresolved,
            ["run_name", "trade_count", primary, "profit_factor", "profit_factor_source"],
        )
    )

    lines.extend(["## Group summaries", ""])
    if not group_summaries:
        lines.append("_(no group_by axes available)_")
        lines.append("")
    for axis, summary in group_summaries.items():
        lines.append(f"### `{axis}`")
        lines.append("")
        lines.extend(
            _md_table(
                summary,
                [
                    axis,
                    "cell_count",
                    f"mean_{primary}",
                    f"median_{primary}",
                    "mean_trade_count",
                ],
            )
        )

    lines.extend(["## OTF delta", ""])
    if otf_delta.empty:
        lines.append(
            "No OTF Δ rows (missing `otf` factor, missing baseline match, or no variants)."
        )
        lines.append("")
    else:
        baseline = report.get("otf_baseline") or {"enabled": False}
        lines.append(
            f"Δ = metric(OTF variant) − metric(baseline `{otf_canonical_key(baseline)}`). "
            "Interpret with multiple-testing caution."
        )
        lines.append("")
        lines.extend(
            _md_table(
                otf_delta,
                [
                    "run_name_variant",
                    "run_name_baseline",
                    f"delta_{primary}",
                    f"{primary}_variant",
                    f"{primary}_baseline",
                    "trade_count_variant",
                    "trade_count_baseline",
                    "meets_min_trades",
                ],
            )
        )

    lines.extend(
        [
            "## Metric sources",
            "",
            "- Index columns: `trade_count`, `expectancy_r`, `total_r`, `max_drawdown_r`, "
            "`profit_factor`, `win_rate`, `best_grid_stop_loss_ticks`, "
            "`best_grid_take_profit_ticks`, `bundle_hash`, `bundle_path`, `status` "
            "(PF/WR additive since RS-D7; older indexes may omit them).",
            "- `profit_factor` / `win_rate`: each field prefers the study index when "
            "present, else bundle `trade_summary.json` "
            "(`profit_factor_source` tracks PF only: `index` | `bundle` | `missing`).",
            "- Ranked / low-N / unresolved / group summaries require `factors_joined=True` "
            "(index-only orphans stay in the overview CSV).",
            "- Group summaries use the same ranked-eligible gate (min_trades + "
            "non-null primary) so `cell_count` matches the mean/median population.",
            "",
        ]
    )
    return "\n".join(lines)


def report_study(
    study_dir: str | Path,
    *,
    write_artifacts: bool = True,
) -> StudyReportResult:
    """Aggregate a completed study directory into overview CSV/MD (+ OTF Δ).

    When ``write_artifacts`` is false (RS-D2 viewer), compute the same in-memory
    result without rewriting ``study.overview.*`` / ``study.otf_delta.csv`` /
    ``study.direction.csv``. Does not rewrite ``results_index.csv``.
    """
    root = Path(study_dir)
    if not root.is_dir():
        raise StudyReportError(f"Study directory does not exist: {root}")

    cfg = _load_report_config(root)
    report = cfg["report"]
    primary = str(report["primary_metric"])
    min_trades = int(report["min_trades"])
    multiple_testing = str(report.get("multiple_testing", "warn"))
    group_by = list(report.get("group_by") or [])
    otf_baseline = report.get("otf_baseline") or {"enabled": False}
    if not isinstance(otf_baseline, Mapping):
        raise StudyReportError("study.report.otf_baseline must be a mapping")

    factor_map = _load_factor_map(root)
    index = _load_results_index(root)
    overview = build_overview_frame(study_dir=root, index=index, factor_map=factor_map)
    ranked, low_n, unresolved = split_ranked_and_low_n(
        overview, primary_metric=primary, min_trades=min_trades
    )
    group_summaries = build_group_summaries(
        overview,
        group_by=group_by,
        primary_metric=primary,
        min_trades=min_trades,
    )
    otf_delta = build_otf_delta(
        overview,
        factor_map=factor_map,
        otf_baseline=otf_baseline,
        primary_metric=primary,
        min_trades=min_trades,
    )

    best_cell_suppressed = multiple_testing == "error"
    markdown = render_overview_markdown(
        study_name=cfg["study_name"],
        report=report,
        overview=overview,
        ranked=ranked,
        low_n=low_n,
        unresolved=unresolved,
        group_summaries=group_summaries,
        otf_delta=otf_delta,
        best_cell_suppressed=best_cell_suppressed,
    )

    overview_path = root / OVERVIEW_CSV
    md_path = root / OVERVIEW_MD
    otf_path = root / OTF_DELTA_CSV
    direction_path = root / DIRECTION_CSV
    direction = _direction_frame(overview)

    if write_artifacts:
        overview.to_csv(overview_path, index=False)
        md_path.write_text(
            markdown if markdown.endswith("\n") else markdown + "\n",
            encoding="utf-8",
        )
        otf_delta.to_csv(otf_path, index=False)
        direction.to_csv(direction_path, index=False)

    return StudyReportResult(
        overview=overview,
        ranked=ranked,
        low_n=low_n,
        unresolved=unresolved,
        group_summaries=group_summaries,
        otf_delta=otf_delta,
        markdown=markdown,
        paths={
            OVERVIEW_CSV: overview_path,
            OVERVIEW_MD: md_path,
            OTF_DELTA_CSV: otf_path,
            DIRECTION_CSV: direction_path,
        },
        primary_metric=primary,
        min_trades=min_trades,
        multiple_testing=multiple_testing,
        best_cell_suppressed=best_cell_suppressed,
        study_name=cfg["study_name"],
    )
