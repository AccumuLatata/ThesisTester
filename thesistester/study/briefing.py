"""SV5 study briefing — trader headline + per-cell SL/TP grid + NY ToD.

Projects artifacts the runner already wrote (index row, ``best_grid_result.json``,
``grid_results.parquet``, ``trades.parquet``). Does not re-simulate, write the
study dir, or hydrate classic research session keys.

Time-of-day is a post-hoc grouping of completed trades (same family as
``thesistester.analytics.time_analysis``), not a StudySpec factor axis.
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from thesistester.analytics.time_analysis import add_time_buckets, summarize_by_group
from thesistester.study.report import (
    StudyReportResult,
    _bundle_path_within_study,
    _coerce_float,
    _factors_joined_mask,
    _fmt_num,
)

TOD_GROUP_COL = "entry_rth_segment"
TOD_BUCKET_TZ = "America/New_York"
TOD_MIN_TRADES_WARNING = 10
GRID_DISPLAY_LIMIT = 25
GRID_DISPLAY_COLS: tuple[str, ...] = (
    "stop_loss_ticks",
    "take_profit_ticks",
    "trade_count",
    "expectancy_r",
    "profit_factor",
    "win_rate",
)
TOD_DISPLAY_COLS: tuple[str, ...] = (
    TOD_GROUP_COL,
    "trade_count",
    "avg_r",
    "total_r",
    "profit_factor",
    "win_rate",
    "sample_warning",
)
FACTOR_HEADLINE_KEYS: tuple[str, ...] = (
    "factor_partner_levels",
    "factor_trigger",
    "factor_trigger_timeframe",
    "factor_direction",
    "factor_confluence_mode",
    "factor_core_level",
)

BRIEFING_HONESTY = (
    "Descriptive screen, not a validated edge. Ranking many closed cells "
    "invites multiple-testing bias. Time-of-day is a post-hoc subset of "
    "completed trades (no re-sim) — not a live schedule."
)


@dataclass(frozen=True)
class StudyMoneyBriefing:
    """Deterministic trader-facing study summary."""

    headline: str
    lines: tuple[str, ...]
    caveats: tuple[str, ...]
    source: str
    run_name: str | None
    below_min_trades: bool
    settings: dict[str, str]
    best_grid: dict[str, str]
    tod_best: dict[str, str]


def empty_briefing(*, reason: str = "No finished cells to summarize yet.") -> StudyMoneyBriefing:
    """Placeholder when Inspect has no ok cells or no index yet."""
    return StudyMoneyBriefing(
        headline=reason,
        lines=(),
        caveats=(BRIEFING_HONESTY,),
        source="none",
        run_name=None,
        below_min_trades=False,
        settings={},
        best_grid={},
        tod_best={},
    )


def read_zip_json(bundle_path: Path, member: str) -> dict[str, Any] | None:
    """Best-effort JSON object from one zip member. Missing / corrupt → None."""
    if not bundle_path.is_file():
        return None
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            if member not in archive.namelist():
                return None
            raw = json.loads(archive.read(member).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return dict(raw) if isinstance(raw, Mapping) else None


def read_zip_parquet(bundle_path: Path, member: str) -> pd.DataFrame | None:
    """Best-effort parquet frame from one zip member. Missing / corrupt → None."""
    if not bundle_path.is_file():
        return None
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            if member not in archive.namelist():
                return None
            frame = pd.read_parquet(io.BytesIO(archive.read(member)))
    except Exception:
        return None
    return frame if isinstance(frame, pd.DataFrame) else None


def resolve_cell_bundle(study_dir: Path, bundle_rel: str | None) -> Path | None:
    """Sandbox ``bundle_path`` inside ``study_dir``. Escapes / missing → None."""
    if not isinstance(bundle_rel, str) or not bundle_rel.strip():
        return None
    resolved = _bundle_path_within_study(Path(study_dir), bundle_rel.strip())
    if resolved is None or not resolved.is_file():
        return None
    return resolved


def bundle_missing_caption(study_dir: Path, bundle_rel: str | None) -> str | None:
    """Honest caption when ``resolve_cell_bundle`` returned None."""
    if not isinstance(bundle_rel, str) or not bundle_rel.strip():
        return None
    resolved = _bundle_path_within_study(Path(study_dir), bundle_rel.strip())
    if resolved is None:
        return "bundle_path is outside the study directory and was refused."
    if not resolved.is_file():
        return "bundle_path is not a file inside the study directory."
    return None


def spec_grid_enabled(study_dir: Path) -> bool | None:
    """``study.constants.grid.enabled`` when the written spec is readable."""
    spec_path = Path(study_dir) / "study.spec.yaml"
    if not spec_path.is_file():
        return None
    try:
        import yaml
    except ImportError:  # pragma: no cover - pyyaml is a runtime dep
        return None
    try:
        payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
        return None
    if not isinstance(payload, Mapping):
        return None
    study = payload.get("study")
    if not isinstance(study, Mapping):
        return None
    constants = study.get("constants")
    if not isinstance(constants, Mapping):
        return None
    grid = constants.get("grid")
    if not isinstance(grid, Mapping):
        return None
    enabled = grid.get("enabled")
    return bool(enabled) if isinstance(enabled, bool) else None


def settings_from_row(row: Mapping[str, Any]) -> dict[str, str]:
    """Stable factor tags for the briefing headline."""
    settings: dict[str, str] = {}
    for key in FACTOR_HEADLINE_KEYS:
        if key not in row:
            continue
        text = _display_text(row.get(key))
        if text != "—":
            settings[key.removeprefix("factor_")] = text
    return settings


def grid_from_index_row(row: Mapping[str, Any]) -> dict[str, str]:
    """Best SL/TP ticks from the study index (no zip required)."""
    out: dict[str, str] = {}
    sl = _fmt_num(row.get("best_grid_stop_loss_ticks"))
    tp = _fmt_num(row.get("best_grid_take_profit_ticks"))
    if sl != "—":
        out["stop_loss_ticks"] = sl
    if tp != "—":
        out["take_profit_ticks"] = tp
    return out


def extract_cell_grid(
    bundle_path: Path | None,
    *,
    missing_caption: str | None = None,
) -> tuple[dict[str, Any] | None, pd.DataFrame, str | None]:
    """Return ``(best_grid, ranked grid display, caption)`` from one zip."""
    if bundle_path is None:
        return (
            None,
            pd.DataFrame(columns=list(GRID_DISPLAY_COLS)),
            missing_caption or "No in-dir zip — SL/TP grid peek stays empty.",
        )
    best = read_zip_json(bundle_path, "best_grid_result.json")
    grid = read_zip_parquet(bundle_path, "grid_results.parquet")
    if grid is None or grid.empty:
        if best:
            return (
                best,
                pd.DataFrame(columns=list(GRID_DISPLAY_COLS)),
                ("best_grid_result.json is present; grid_results.parquet is missing."),
            )
        return (
            None,
            pd.DataFrame(columns=list(GRID_DISPLAY_COLS)),
            ("No SL/TP grid in this zip (grid disabled, or members missing)."),
        )
    display = _rank_grid_display(grid)
    caption = (
        f"{len(grid)} SL/TP cells in this zip. "
        "This is the per-cell grid — not the factor cartesian on Ranked cells."
    )
    return best, display, caption


def extract_cell_time_of_day(
    bundle_path: Path | None,
    *,
    min_trades: int = TOD_MIN_TRADES_WARNING,
    missing_caption: str | None = None,
    group_col: str = TOD_GROUP_COL,
) -> tuple[pd.DataFrame, dict[str, str] | None, str | None]:
    """ToD table + best bucket from ``trades.parquet`` (no re-sim).

    Default ``group_col`` is NY ``entry_rth_segment`` (SV5 Inspect). SAF3 CLI
    may pass ``entry_hour_bucket`` / ``entry_30min_bucket``.
    """
    col = str(group_col or TOD_GROUP_COL).strip() or TOD_GROUP_COL
    display_cols = (col,) + tuple(name for name in TOD_DISPLAY_COLS if name != TOD_GROUP_COL)
    empty = pd.DataFrame(columns=list(display_cols))
    if bundle_path is None:
        return (
            empty,
            None,
            missing_caption or "No in-dir zip — time-of-day peek stays empty.",
        )
    trades = read_zip_parquet(bundle_path, "trades.parquet")
    if trades is None or trades.empty:
        return (
            empty,
            None,
            (
                "trades.parquet is missing from this zip, so NY session buckets "
                "cannot be computed. Time-of-day is post-run, not a StudySpec factor."
            ),
        )
    if "entry_timestamp" not in trades.columns or "r_multiple" not in trades.columns:
        return empty, None, ("trades.parquet is missing entry_timestamp or r_multiple.")
    try:
        bucketed = add_time_buckets(trades, bucket_tz=TOD_BUCKET_TZ, session_tz=TOD_BUCKET_TZ)
        grouped = summarize_by_group(bucketed, col, min_trades=min_trades)
    except (TypeError, ValueError):
        return empty, None, "Time-of-day buckets could not be computed from this zip."
    if grouped is None or grouped.empty:
        return empty, None, "No time-of-day groups (empty R sample)."
    present = [name for name in display_cols if name in grouped.columns]
    display = grouped.loc[:, present].copy()
    best = _best_tod_bucket(display, group_col=col)
    caption = (
        "Post-hoc NY RTH segments (America/New_York) on completed trades. "
        "Not a re-simulation and not a live schedule. "
        f"sample_warning flags N < {min_trades}."
    )
    return display, best, caption


def build_study_briefing(
    report: StudyReportResult,
    *,
    study_dir: Path,
) -> StudyMoneyBriefing:
    """Headline the best descriptive cell, its settings, SL/TP, and NY bucket."""
    row, source, below_min = _pick_briefing_row(report)
    if row is None:
        if not getattr(report, "overview", pd.DataFrame()).empty:
            return empty_briefing(reason="No ok cells with a resolvable primary metric.")
        return empty_briefing()

    run_name = _display_text(row.get("run_name"))
    if run_name == "—":
        return empty_briefing()
    metric = str(report.primary_metric)
    metric_value = _fmt_num(row.get(metric))
    trade_count = _fmt_num(row.get("trade_count"))
    settings = settings_from_row(row)
    best_grid = grid_from_index_row(row)

    bundle_rel = _raw_bundle_rel(row.get("bundle_path"))
    bundle = resolve_cell_bundle(study_dir, bundle_rel)
    missing = None if bundle is not None else bundle_missing_caption(study_dir, bundle_rel)
    zip_best, _grid_display, grid_caption = extract_cell_grid(bundle, missing_caption=missing)
    if zip_best:
        sl = _fmt_num(zip_best.get("stop_loss_ticks"))
        tp = _fmt_num(zip_best.get("take_profit_ticks"))
        if sl != "—":
            best_grid["stop_loss_ticks"] = sl
        if tp != "—":
            best_grid["take_profit_ticks"] = tp
    _tod_display, tod_best, tod_caption = extract_cell_time_of_day(bundle, missing_caption=missing)

    headline = _headline(
        metric=metric,
        run_name=run_name,
        metric_value=metric_value,
        trade_count=trade_count,
        settings=settings,
        best_grid=best_grid,
        tod_best=tod_best,
        below_min_trades=below_min,
        min_trades=int(report.min_trades),
        source=source,
        suppressed=bool(report.best_cell_suppressed),
    )
    lines = _supporting_lines(
        source=source,
        settings=settings,
        best_grid=best_grid,
        tod_best=tod_best,
        grid_enabled=spec_grid_enabled(study_dir),
        grid_caption=grid_caption,
        tod_caption=tod_caption,
        below_min=below_min,
        min_trades=int(report.min_trades),
        suppressed=bool(report.best_cell_suppressed),
    )
    return StudyMoneyBriefing(
        headline=headline,
        lines=tuple(lines),
        caveats=(BRIEFING_HONESTY,),
        source=source,
        run_name=run_name,
        below_min_trades=below_min,
        settings=settings,
        best_grid=best_grid,
        tod_best=tod_best or {},
    )


def _pick_briefing_row(
    report: StudyReportResult,
) -> tuple[pd.Series | None, str, bool]:
    """Prefer ranked[0]; else best ok joined cell by primary (may be low-N)."""
    ranked = getattr(report, "ranked", None)
    if _frame_has_rows(ranked):
        return ranked.iloc[0], "ranked", False

    overview = getattr(report, "overview", None)
    if not _frame_has_rows(overview):
        return None, "none", False
    work = overview.copy()
    if "status" in work.columns:
        work = work.loc[work["status"].astype(str).eq("ok")].copy()
    if "factors_joined" in work.columns:
        work = work.loc[_factors_joined_mask(work)].copy()
    metric = str(report.primary_metric)
    if metric not in work.columns:
        return None, "none", False
    work[metric] = pd.to_numeric(work[metric], errors="coerce")
    work = work.loc[work[metric].notna()]
    if work.empty:
        return None, "none", False
    lower_is_better = metric == "max_drawdown_r"
    work = work.sort_values(
        [metric, "run_name"] if "run_name" in work.columns else [metric],
        ascending=[lower_is_better, True] if "run_name" in work.columns else [lower_is_better],
        kind="mergesort",
    )
    row = work.iloc[0]
    n = _coerce_float(row.get("trade_count"))
    below = n is None or n < float(report.min_trades)
    source = "low_n" if below else "overview"
    return row, source, below


def _headline(
    *,
    metric: str,
    run_name: str,
    metric_value: str,
    trade_count: str,
    settings: Mapping[str, str],
    best_grid: Mapping[str, str],
    tod_best: Mapping[str, str] | None,
    below_min_trades: bool,
    min_trades: int,
    source: str,
    suppressed: bool,
) -> str:
    n_note = f"N={trade_count}"
    if below_min_trades:
        n_note += f", below min_trades={min_trades}"
    setup = _settings_clause(settings)
    grid = _grid_clause(best_grid)
    tod = _tod_clause(tod_best)
    prefix = f"Highest `{metric}`"
    if suppressed:
        prefix = f"Highest `{metric}` (crowning suppressed)"
    elif source == "low_n":
        prefix = f"Highest `{metric}` among finished cells"
    return f"{prefix} is `{run_name}` = {metric_value} ({n_note}){setup}{grid}{tod}."


def _supporting_lines(
    *,
    source: str,
    settings: Mapping[str, str],
    best_grid: Mapping[str, str],
    tod_best: Mapping[str, str] | None,
    grid_enabled: bool | None,
    grid_caption: str | None,
    tod_caption: str | None,
    below_min: bool,
    min_trades: int,
    suppressed: bool,
) -> list[str]:
    lines: list[str] = []
    if source == "ranked":
        lines.append("Source: ranked cells (passed the `min_trades` gate).")
    elif source == "low_n":
        lines.append(
            f"No cell met `min_trades={min_trades}`. "
            "This is the best finished cell by the primary metric (low-N)."
        )
    elif source == "overview":
        lines.append("Source: finished overview cells (ranked table was empty).")
    if suppressed:
        lines.append("`multiple_testing: error` — do not treat this row as a crowned winner.")
    if below_min and source != "low_n":
        lines.append(f"Sample is below `min_trades={min_trades}` — treat as a thin screen.")
    if settings:
        pretty = ", ".join(f"{key}={value}" for key, value in settings.items())
        lines.append(f"Factor settings: {pretty}.")
    if best_grid:
        sl = best_grid.get("stop_loss_ticks", "—")
        tp = best_grid.get("take_profit_ticks", "—")
        lines.append(f"Best SL/TP on that cell: {sl}/{tp} ticks (per-cell grid winner).")
    elif grid_enabled is True:
        lines.append(
            "This study enabled an SL/TP grid, but no best SL/TP was recorded "
            "on the index or zip for this cell."
        )
    elif grid_enabled is False:
        lines.append(
            "This study did not enable an SL/TP grid. Ranked cells are the "
            "factor cartesian only (partner × trigger × timeframe × direction)."
        )
    if tod_best:
        segment = tod_best.get("segment", "—")
        avg_r = tod_best.get("avg_r", "—")
        n = tod_best.get("trade_count", "—")
        thin = " (thin bucket)" if _tod_is_thin(tod_best) else ""
        lines.append(
            f"Strongest NY RTH segment on that cell: `{segment}` (avg_r={avg_r}, N={n}){thin}."
        )
    elif tod_caption:
        lines.append(tod_caption)
    if grid_caption and best_grid:
        lines.append(grid_caption)
    lines.append(
        "To constrain the next run to one NY bucket, set `constants.entry_window` "
        "(Admit / session window) — do not treat ToD as a free search axis."
    )
    return lines


def _settings_clause(settings: Mapping[str, str]) -> str:
    if not settings:
        return ""
    parts = [f"{key}={value}" for key, value in settings.items()]
    return " with " + ", ".join(parts)


def _grid_clause(best_grid: Mapping[str, str]) -> str:
    if not best_grid:
        return ""
    sl = best_grid.get("stop_loss_ticks")
    tp = best_grid.get("take_profit_ticks")
    if not sl and not tp:
        return ""
    return f", best SL/TP {sl or '—'}/{tp or '—'} ticks"


def _tod_is_thin(tod_best: Mapping[str, str]) -> bool:
    warn = tod_best.get("sample_warning")
    return warn is True or str(warn).strip().lower() == "true"


def _tod_clause(tod_best: Mapping[str, str] | None) -> str:
    if not tod_best:
        return ""
    segment = tod_best.get("segment")
    if not segment:
        return ""
    avg_r = tod_best.get("avg_r", "—")
    n = tod_best.get("trade_count", "—")
    thin = ", thin bucket" if _tod_is_thin(tod_best) else ""
    return f" at NY `{segment}` (avg_r={avg_r}, N={n}{thin})"


def _rank_grid_display(grid: pd.DataFrame) -> pd.DataFrame:
    work = grid.copy()
    metric = "expectancy_r" if "expectancy_r" in work.columns else None
    sort_cols: list[str] = []
    ascending: list[bool] = []
    if metric:
        work[metric] = pd.to_numeric(work[metric], errors="coerce")
        sort_cols.append(metric)
        ascending.append(False)
    for col in ("stop_loss_ticks", "take_profit_ticks"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
            sort_cols.append(col)
            ascending.append(True)
    if sort_cols:
        work = work.sort_values(sort_cols, ascending=ascending, kind="mergesort")
    present = [col for col in GRID_DISPLAY_COLS if col in work.columns]
    if not present:
        return work.head(GRID_DISPLAY_LIMIT).reset_index(drop=True)
    return work.loc[:, present].head(GRID_DISPLAY_LIMIT).reset_index(drop=True)


def _best_tod_bucket(
    frame: pd.DataFrame,
    *,
    group_col: str = TOD_GROUP_COL,
) -> dict[str, str] | None:
    col = str(group_col or TOD_GROUP_COL).strip() or TOD_GROUP_COL
    if frame is None or frame.empty or "avg_r" not in frame.columns:
        return None
    if col not in frame.columns:
        return None
    work = frame.copy()
    work["avg_r"] = pd.to_numeric(work["avg_r"], errors="coerce")
    work = work.loc[work["avg_r"].notna()]
    if work.empty:
        return None
    # Prefer buckets that clear the sample-warning gate when any exist.
    if "sample_warning" in work.columns:
        solid = work.loc[~work["sample_warning"].fillna(True)]
        if not solid.empty:
            work = solid
    work = work.sort_values(
        ["avg_r", col],
        ascending=[False, True],
        kind="mergesort",
    )
    top = work.iloc[0]
    out = {
        "segment": _display_text(top.get(col)),
        "avg_r": _fmt_num(top.get("avg_r")),
        "trade_count": _fmt_num(top.get("trade_count")),
    }
    if "sample_warning" in top.index:
        out["sample_warning"] = "True" if bool(top.get("sample_warning")) else "False"
    if out["segment"] == "—":
        return None
    return out


def _raw_bundle_rel(value: Any) -> str | None:
    text = _display_text(value)
    return None if text == "—" else text


def _display_text(value: Any) -> str:
    if value is None:
        return "—"
    try:
        if value is pd.NA or pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and math.isnan(value):
        return "—"
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return "—"
    return text


def _frame_has_rows(frame: object) -> bool:
    return isinstance(frame, pd.DataFrame) and not frame.empty and "run_name" in frame.columns
