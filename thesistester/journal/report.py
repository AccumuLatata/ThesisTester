"""Read-only journal report (TJ9). Q1–Q8 over ingested artifacts.

Does not call ``simulate_trades`` or ``compute_all_levels``. Does not write
research bundles, ``results/studies/``, or a promotion registry. Readers
tolerate missing attribution / counterfactual / match files.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import json
import math

import pandas as pd

from thesistester.journal.triggers import decode_trigger_labels
from thesistester.journal.schema import (
    DAY_INTENSE,
    DAY_QUIET,
    HOLD_15_60S,
    HOLD_1_5MIN,
    HOLD_GT_5MIN,
    HOLD_LT_15S,
    JOURNAL_EXCHANGE_TZ,
    JOURNAL_POINT_VALUE,
    JOURNAL_STORE_SCHEMA,
    JOURNAL_TICK_SIZE,
    RECON_UNKNOWN,
    REPORT_HONESTY,
    REPORT_MIN_N,
    ZONE_COUNT_1,
    ZONE_COUNT_2,
    ZONE_COUNT_3,
    ZONE_COUNT_4_PLUS,
    ZONE_REL_NONE,
    ZONE_WIDTH_3_4,
    ZONE_WIDTH_GE_5,
    ZONE_WIDTH_LE_2,
    TRIGGER_NONE,
    TRIGGER_RESOLUTION_1M,
    TRIGGERS_HONESTY,
    ZONES_HONESTY,
    REPORT_SLICE_DAY_INTENSITY,
    REPORT_SLICE_DIRECTION,
    REPORT_SLICE_HOLD,
    REPORT_SLICE_NY_HOUR,
    RESOLUTION_MIXED,
    RESOLUTION_UNJOINED,
    STATUS_OPEN,
    JournalIngestError,
)
from thesistester.persistence.local_store import get_store_root

TRADES_PARQUET: str = "journal_trades.parquet"
ATTRIBUTION_PARQUET: str = "journal_attribution.parquet"
COUNTERFACTUAL_PARQUET: str = "journal_counterfactuals.parquet"
COUNTERFACTUAL_JSON: str = "counterfactual.json"
MATCHES_PARQUET: str = "journal_matches.parquet"
MATCH_JSON: str = "match.json"
ZONES_PARQUET: str = "journal_zones.parquet"
ZONES_JSON: str = "zones.json"
TRIGGERS_PARQUET: str = "journal_triggers.parquet"
TRIGGERS_JSON: str = "triggers.json"
REPORT_JSON: str = "report.json"

_DAY_INTENSITY_THRESHOLD: int = 60
_HOLD_15: float = 15.0
_HOLD_60: float = 60.0
_HOLD_300: float = 300.0


@dataclass(frozen=True)
class JournalArtifacts:
    """Optional ingested frames. Missing files stay ``None``."""

    journal_dir: Path
    trades: pd.DataFrame | None
    attribution: pd.DataFrame | None
    counterfactuals: pd.DataFrame | None
    counterfactual_payload: dict[str, object] | None
    matches: pd.DataFrame | None
    match_payload: dict[str, object] | None
    zones: pd.DataFrame | None = None
    zone_payload: dict[str, object] | None = None
    triggers: pd.DataFrame | None = None
    trigger_payload: dict[str, object] | None = None


@dataclass(frozen=True)
class JournalReport:
    """Q1–Q8 tables. Every table carries n, resolution, recon_status."""

    honesty: str
    include_small_n: bool
    hidden_slice_count: int
    present: dict[str, bool]
    q1_days: pd.DataFrame
    q2_slices: pd.DataFrame
    q3_levels: pd.DataFrame
    q3_context: pd.DataFrame
    q3_tags: pd.DataFrame
    q3_zones_count: pd.DataFrame
    q3_zones_width: pd.DataFrame
    q3_zones_relation: pd.DataFrame
    q3_zones_names: pd.DataFrame
    q3_triggers: pd.DataFrame
    q4_brackets: pd.DataFrame
    q5_null: dict[str, object]
    q6_rules: pd.DataFrame
    q7_matches: pd.DataFrame
    q8_ledger: pd.DataFrame
    captions: dict[str, str]


def journal_store_dir() -> Path:
    """``<store>/journal/v1`` — sibling of ``datasets/`` / ``setups/``.

    Not under ``execution_artifacts/`` (CAI-10 does not scan it). This helper
    does not create the directory.
    """
    return get_store_root() / "journal" / "v1"


def load_journal_artifacts(journal_dir: str | Path) -> JournalArtifacts:
    """Load ingested journal/v1 files. Missing optional files stay ``None``."""
    root = Path(journal_dir).expanduser()
    if not root.exists():
        raise JournalIngestError(f"journal directory not found: {root}")
    if not root.is_dir():
        raise JournalIngestError(f"journal path is not a directory: {root}")
    return JournalArtifacts(
        journal_dir=root.resolve(),
        trades=_optional_table(root / TRADES_PARQUET),
        attribution=_optional_table(root / ATTRIBUTION_PARQUET),
        counterfactuals=_optional_table(root / COUNTERFACTUAL_PARQUET),
        counterfactual_payload=_optional_json(root / COUNTERFACTUAL_JSON),
        matches=_optional_table(root / MATCHES_PARQUET),
        match_payload=_optional_json(root / MATCH_JSON),
        zones=_optional_table(root / ZONES_PARQUET),
        zone_payload=_optional_json(root / ZONES_JSON),
        triggers=_optional_table(root / TRIGGERS_PARQUET),
        trigger_payload=_optional_json(root / TRIGGERS_JSON),
    )


def build_journal_report(
    trades: pd.DataFrame | None,
    *,
    attribution: pd.DataFrame | None = None,
    counterfactuals: pd.DataFrame | None = None,
    counterfactual_payload: Mapping[str, object] | None = None,
    matches: pd.DataFrame | None = None,
    match_payload: Mapping[str, object] | None = None,
    zones: pd.DataFrame | None = None,
    zone_payload: Mapping[str, object] | None = None,
    triggers: pd.DataFrame | None = None,
    trigger_payload: Mapping[str, object] | None = None,
    include_small_n: bool = False,
) -> JournalReport:
    """Build Q1–Q8 tables. Keyword-only after ``trades``. Default hides n < 30."""
    if not isinstance(include_small_n, bool):
        raise JournalIngestError("include_small_n must be a bool")
    work = _coerce_trades(trades)
    q1 = _q1_days(work)
    slices, hidden = _q2_slices(work, include_small_n=include_small_n)
    q3_levels, q3_context, q3_tags = _q3_attribution(work, attribution)
    q3_count, q3_width, q3_relation, q3_names = _q3_zones(
        work, zones, include_small_n=include_small_n
    )
    q3_triggers = _q3_triggers(work, triggers, include_small_n=include_small_n)
    q4, q5, q6 = _q4_q6(counterfactual_payload, counterfactuals)
    q7, q8 = _q7_q8(matches, match_payload)
    captions = {
        "q1": "Per-trade dollar-ticks are qty-scaled. Break-even gross/trade is mean fee_ticks.",
        "q2": "Hold-time cuts are outcome-conditioned (losers cut fast). n < 30 hidden unless toggled.",
        "q3": "Tags are trader intent. Alignment is a distance check, not a trigger.",
        "q3_zones": ZONES_HONESTY,
        "q3_triggers": TRIGGERS_HONESTY,
        "q4": "three brackets were looked at (not a single pre-registered test); no slippage model.",
        "q5": "Direction-shuffle preserves per-session long/short counts. Seeded. Not a global sign flip.",
        "q6": "Rules are declared, never searched. in_sample and forward are never blended.",
        "q7": "Named-cell match only (no Observatory corpus). product_mismatch names the failing dimension.",
        "q8": (
            "Adherence = executed_cell / (executed_cell + systematic_unfilled). "
            "live_expectancy_ticks is mean live E; live_net_ticks is the session sum. "
            "Cell expectancy is 1-lot."
        ),
    }
    if isinstance(counterfactual_payload, Mapping):
        brackets = counterfactual_payload.get("brackets")
        if isinstance(brackets, Mapping):
            caption = brackets.get("caption")
            if isinstance(caption, str) and caption:
                captions["q4"] = caption
    return JournalReport(
        honesty=REPORT_HONESTY,
        include_small_n=include_small_n,
        hidden_slice_count=hidden,
        present={
            "trades": trades is not None,
            "attribution": attribution is not None,
            "counterfactual": counterfactual_payload is not None or counterfactuals is not None,
            "match": match_payload is not None or matches is not None,
            "zones": zones is not None or zone_payload is not None,
            "triggers": triggers is not None or trigger_payload is not None,
        },
        q1_days=q1,
        q2_slices=slices,
        q3_levels=q3_levels,
        q3_context=q3_context,
        q3_tags=q3_tags,
        q3_zones_count=q3_count,
        q3_zones_width=q3_width,
        q3_zones_relation=q3_relation,
        q3_zones_names=q3_names,
        q3_triggers=q3_triggers,
        q4_brackets=q4,
        q5_null=q5,
        q6_rules=q6,
        q7_matches=q7,
        q8_ledger=q8,
        captions=captions,
    )


def write_report_artifacts(output_dir: str | Path, report: JournalReport) -> dict[str, Path]:
    """Write ``report.json``. Refuses ``results/studies/``."""
    out = _assert_output_dir(Path(output_dir))
    out.mkdir(parents=True, exist_ok=True)
    path = out / REPORT_JSON
    path.write_text(json.dumps(_report_payload(report), indent=2) + "\n", encoding="utf-8")
    return {REPORT_JSON: path}


def report_files(
    *,
    journal_dir: str | Path,
    output_dir: str | Path,
    include_small_n: bool = False,
) -> dict[str, Path]:
    """Load ingested artifacts, build Q1–Q8, write ``report.json``."""
    artifacts = load_journal_artifacts(journal_dir)
    report = report_from_artifacts(artifacts, include_small_n=include_small_n)
    return write_report_artifacts(output_dir, report)


def report_from_artifacts(
    artifacts: JournalArtifacts,
    *,
    include_small_n: bool = False,
) -> JournalReport:
    """Rebuild Q1–Q8 from cached artifacts. Toggle does not reload files."""
    return build_journal_report(
        artifacts.trades,
        attribution=artifacts.attribution,
        counterfactuals=artifacts.counterfactuals,
        counterfactual_payload=artifacts.counterfactual_payload,
        matches=artifacts.matches,
        match_payload=artifacts.match_payload,
        zones=artifacts.zones,
        zone_payload=artifacts.zone_payload,
        triggers=artifacts.triggers,
        trigger_payload=artifacts.trigger_payload,
        include_small_n=include_small_n,
    )


def _coerce_trades(trades: pd.DataFrame | None) -> pd.DataFrame:
    if trades is None:
        return pd.DataFrame()
    if not isinstance(trades, pd.DataFrame):
        raise JournalIngestError("trades must be a DataFrame")
    if trades.empty:
        return trades.copy()
    required = {"trade_id", "instrument", "session_date", "direction"}
    missing = sorted(required - set(trades.columns))
    if missing:
        raise JournalIngestError("trades frame missing columns: " + ", ".join(missing))
    work = trades.copy()
    work["trade_id"] = work["trade_id"].map(str)
    work["instrument"] = work["instrument"].map(str)
    work["direction"] = work["direction"].map(str)
    work["session_date"] = work["session_date"].map(_as_date)
    if "resolution" in work.columns:
        work["resolution"] = work["resolution"].map(_as_resolution)
    else:
        work["resolution"] = RESOLUTION_UNJOINED
    if "recon_status" in work.columns:
        work["recon_status"] = work["recon_status"].map(_as_recon)
    else:
        work["recon_status"] = RECON_UNKNOWN
    work["net_ticks"] = (
        work["net_ticks"].map(_optional_float) if "net_ticks" in work.columns else None
    )
    work["fee_ticks"] = (
        work["fee_ticks"].map(_optional_float) if "fee_ticks" in work.columns else None
    )
    work["gross_ticks"] = _derive_gross_ticks(work)
    if "hold_seconds" in work.columns:
        work["hold_seconds"] = work["hold_seconds"].map(_optional_float)
    if "entry_timestamp" in work.columns:
        work["entry_timestamp"] = [_as_utc(value) for value in work["entry_timestamp"]]
    return work.reset_index(drop=True)


def _closed_for_pnl(trades: pd.DataFrame) -> pd.DataFrame:
    """Drop leftover open lots from Q1/Q2 P&L cuts."""
    if trades.empty or "status" not in trades.columns:
        return trades
    mask = trades["status"].map(lambda value: str(value) != STATUS_OPEN)
    return trades.loc[mask].copy()


def _q1_days(trades: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "instrument",
        "session_date",
        "n",
        "mean_gross_ticks",
        "mean_net_ticks",
        "mean_fee_ticks",
        "break_even_gross_ticks",
        "sum_net_ticks",
        "resolution",
        "recon_status",
    ]
    closed = _closed_for_pnl(trades)
    if closed.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    grouped = closed.groupby(["instrument", "session_date"], sort=True, dropna=False)
    for (instrument, session), group in grouped:
        fee = _mean(group.get("fee_ticks"))
        recon = _unique_or_mixed(group["recon_status"])
        rows.append(
            {
                "instrument": str(instrument),
                "session_date": session.isoformat() if isinstance(session, date) else str(session),
                "n": int(len(group)),
                "mean_gross_ticks": _mean(group.get("gross_ticks")),
                "mean_net_ticks": _mean(group.get("net_ticks")),
                "mean_fee_ticks": fee,
                "break_even_gross_ticks": fee,
                "sum_net_ticks": _sum(group.get("net_ticks")),
                "resolution": _unique_or_mixed(group["resolution"]),
                "recon_status": recon,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _q2_slices(trades: pd.DataFrame, *, include_small_n: bool) -> tuple[pd.DataFrame, int]:
    columns = [
        "slice_kind",
        "slice_value",
        "n",
        "mean_gross_ticks",
        "mean_net_ticks",
        "mean_fee_ticks",
        "resolution",
        "recon_status",
    ]
    closed = _closed_for_pnl(trades)
    if closed.empty:
        return pd.DataFrame(columns=columns), 0
    labeled = closed.copy()
    labeled["ny_hour"] = (
        labeled["entry_timestamp"].map(_ny_hour) if "entry_timestamp" in labeled.columns else None
    )
    labeled["hold_bucket"] = (
        labeled["hold_seconds"].map(_hold_bucket) if "hold_seconds" in labeled.columns else None
    )
    day_n = labeled.groupby("session_date").size()
    labeled["day_intensity"] = labeled["session_date"].map(
        lambda session: (
            DAY_INTENSE if int(day_n.get(session, 0)) >= _DAY_INTENSITY_THRESHOLD else DAY_QUIET
        )
    )
    specs = (
        (REPORT_SLICE_DIRECTION, "direction"),
        (REPORT_SLICE_NY_HOUR, "ny_hour"),
        (REPORT_SLICE_HOLD, "hold_bucket"),
        (REPORT_SLICE_DAY_INTENSITY, "day_intensity"),
    )
    rows: list[dict[str, object]] = []
    hidden = 0
    for kind, column in specs:
        if column not in labeled.columns:
            continue
        for value, group in labeled.groupby(column, sort=True, dropna=False):
            if _is_missing(value):
                continue
            n = int(len(group))
            if n < REPORT_MIN_N:
                hidden += 1
                if not include_small_n:
                    continue
            rows.append(
                {
                    "slice_kind": kind,
                    "slice_value": str(value),
                    "n": n,
                    "mean_gross_ticks": _mean(group.get("gross_ticks")),
                    "mean_net_ticks": _mean(group.get("net_ticks")),
                    "mean_fee_ticks": _mean(group.get("fee_ticks")),
                    "resolution": _unique_or_mixed(group["resolution"]),
                    "recon_status": _unique_or_mixed(group["recon_status"]),
                }
            )
    return pd.DataFrame(rows, columns=columns), hidden


def _q3_attribution(
    trades: pd.DataFrame,
    attribution: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    level_cols = ["nearest_level_token", "n", "resolution", "recon_status"]
    context_cols = ["level_context", "n", "resolution", "recon_status"]
    tag_cols = ["tag_alignment", "n", "intent_mismatch_n", "resolution", "recon_status"]
    empty = (
        pd.DataFrame(columns=level_cols),
        pd.DataFrame(columns=context_cols),
        pd.DataFrame(columns=tag_cols),
    )
    if attribution is None or not isinstance(attribution, pd.DataFrame) or attribution.empty:
        return empty
    work = attribution.copy()
    if "trade_id" in work.columns and not trades.empty and "trade_id" in trades.columns:
        meta = trades[["trade_id", "resolution", "recon_status"]].drop_duplicates("trade_id")
        work["trade_id"] = work["trade_id"].map(str)
        work = work.merge(meta, on="trade_id", how="left", suffixes=("", "_trade"))
        work["resolution"] = _coalesce_meta(work, "resolution", default=RESOLUTION_UNJOINED)
        work["recon_status"] = _coalesce_meta(work, "recon_status", default=RECON_UNKNOWN)
        work["resolution"] = work["resolution"].map(_as_resolution)
        work["recon_status"] = work["recon_status"].map(_as_recon)
    else:
        work["resolution"] = RESOLUTION_UNJOINED
        work["recon_status"] = RECON_UNKNOWN
    levels = _count_groups(work, "nearest_level_token", level_cols)
    context = _count_groups(work, "level_context", context_cols)
    tags = _tag_groups(work, tag_cols)
    return levels, context, tags


def _q3_zones(
    trades: pd.DataFrame,
    zones: pd.DataFrame | None,
    *,
    include_small_n: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta_cols = ["n", "mean_net_ticks", "resolution", "recon_status", "zone_params_hash"]
    count_cols = ["zone_level_count", *meta_cols]
    width_cols = ["zone_width_bucket", *meta_cols]
    relation_cols = ["entry_zone_relation", *meta_cols]
    names_cols = ["zone_level_names", *meta_cols]
    empty = (
        pd.DataFrame(columns=count_cols),
        pd.DataFrame(columns=width_cols),
        pd.DataFrame(columns=relation_cols),
        pd.DataFrame(columns=names_cols),
    )
    if zones is None or not isinstance(zones, pd.DataFrame) or zones.empty:
        return empty
    work = zones.copy()
    if "trade_id" in work.columns and not trades.empty and "trade_id" in trades.columns:
        keep = [
            column
            for column in ("trade_id", "resolution", "recon_status", "net_ticks")
            if column in trades.columns
        ]
        meta = trades[keep].drop_duplicates("trade_id")
        work["trade_id"] = work["trade_id"].map(str)
        work = work.merge(meta, on="trade_id", how="left", suffixes=("", "_trade"))
        work["resolution"] = _coalesce_meta(work, "resolution", default=RESOLUTION_UNJOINED)
        work["recon_status"] = _coalesce_meta(work, "recon_status", default=RECON_UNKNOWN)
        if "net_ticks" not in work.columns or work["net_ticks"].isna().all():
            if "net_ticks_trade" in work.columns:
                work["net_ticks"] = work["net_ticks_trade"]
    if "resolution" not in work.columns:
        work["resolution"] = RESOLUTION_UNJOINED
    if "recon_status" not in work.columns:
        work["recon_status"] = RECON_UNKNOWN
    work["resolution"] = work["resolution"].map(_as_resolution)
    work["recon_status"] = work["recon_status"].map(_as_recon)
    if "zone_params_hash" not in work.columns:
        work["zone_params_hash"] = ""
    if "net_ticks" not in work.columns:
        work["net_ticks"] = None
    work["net_ticks"] = work["net_ticks"].map(_optional_float)
    if "zone_width_ticks" in work.columns:
        work["zone_width_bucket"] = work["zone_width_ticks"].map(_zone_width_bucket)
    else:
        work["zone_width_bucket"] = None
    if "zone_level_count" in work.columns:
        work["zone_level_count"] = work["zone_level_count"].map(_zone_count_bucket)
    else:
        work["zone_level_count"] = None
    if "entry_zone_relation" not in work.columns:
        work["entry_zone_relation"] = None
    attributed = work.loc[work["entry_zone_relation"].map(_is_attributed_zone)].copy()
    count = _zone_groups(
        attributed, "zone_level_count", count_cols, include_small_n=include_small_n
    )
    width = _zone_groups(
        attributed, "zone_width_bucket", width_cols, include_small_n=include_small_n
    )
    relation = _zone_groups(
        work, "entry_zone_relation", relation_cols, include_small_n=include_small_n
    )
    names = _zone_groups(
        attributed, "zone_level_names", names_cols, include_small_n=include_small_n
    )
    return count, width, relation, names


def _q3_triggers(
    trades: pd.DataFrame,
    triggers: pd.DataFrame | None,
    *,
    include_small_n: bool,
) -> pd.DataFrame:
    """Distribution and net ticks per 1m label. Multi-label counted once per label."""
    columns = [
        "inferred_trigger",
        "n",
        "mean_net_ticks",
        "resolution",
        "recon_status",
        "zone_params_hash",
        "trigger_resolution",
    ]
    if triggers is None or not isinstance(triggers, pd.DataFrame) or triggers.empty:
        return pd.DataFrame(columns=columns)
    work = triggers.copy()
    if "trade_id" in work.columns and not trades.empty and "trade_id" in trades.columns:
        keep = [
            column
            for column in ("trade_id", "resolution", "recon_status", "net_ticks")
            if column in trades.columns
        ]
        meta = trades[keep].drop_duplicates("trade_id")
        work["trade_id"] = work["trade_id"].map(str)
        work = work.merge(meta, on="trade_id", how="left", suffixes=("", "_trade"))
        work["resolution"] = _coalesce_meta(work, "resolution", default=RESOLUTION_UNJOINED)
        work["recon_status"] = _coalesce_meta(work, "recon_status", default=RECON_UNKNOWN)
        if "net_ticks" not in work.columns or work["net_ticks"].isna().all():
            if "net_ticks_trade" in work.columns:
                work["net_ticks"] = work["net_ticks_trade"]
    if "resolution" not in work.columns:
        work["resolution"] = RESOLUTION_UNJOINED
    if "recon_status" not in work.columns:
        work["recon_status"] = RECON_UNKNOWN
    work["resolution"] = work["resolution"].map(_as_resolution)
    work["recon_status"] = work["recon_status"].map(_as_recon)
    if "zone_params_hash" not in work.columns:
        work["zone_params_hash"] = ""
    if "net_ticks" not in work.columns:
        work["net_ticks"] = None
    work["net_ticks"] = work["net_ticks"].map(_optional_float)
    exploded_rows: list[dict[str, object]] = []
    for raw in work.to_dict(orient="records"):
        labels = decode_trigger_labels(raw.get("inferred_triggers_1m"))
        names = labels if labels else (TRIGGER_NONE,)
        for label in names:
            exploded_rows.append(
                {
                    "inferred_trigger": label,
                    "net_ticks": raw.get("net_ticks"),
                    "resolution": raw.get("resolution"),
                    "recon_status": raw.get("recon_status"),
                    "zone_params_hash": raw.get("zone_params_hash") or "",
                    "trigger_resolution": TRIGGER_RESOLUTION_1M,
                }
            )
    exploded = pd.DataFrame(exploded_rows)
    if exploded.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    grouped = exploded.groupby(
        ["inferred_trigger", "zone_params_hash", "trigger_resolution"],
        sort=True,
        dropna=False,
    )
    for (label, digest, trig_res), group in grouped:
        n_value = int(len(group))
        if n_value < REPORT_MIN_N and not include_small_n:
            continue
        rows.append(
            {
                "inferred_trigger": str(label),
                "n": n_value,
                "mean_net_ticks": _mean(group.get("net_ticks")),
                "resolution": _unique_or_mixed(group["resolution"]),
                "recon_status": _unique_or_mixed(group["recon_status"]),
                "zone_params_hash": str(digest or ""),
                "trigger_resolution": str(trig_res),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _zone_groups(
    frame: pd.DataFrame,
    column: str,
    columns: list[str],
    *,
    include_small_n: bool,
) -> pd.DataFrame:
    if column not in frame.columns or frame.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    grouped = frame.groupby([column, "zone_params_hash"], sort=True, dropna=False)
    for (value, digest), group in grouped:
        if _is_missing(value):
            continue
        n_value = int(len(group))
        if n_value < REPORT_MIN_N and not include_small_n:
            continue
        rows.append(
            {
                column: str(value),
                "n": n_value,
                "mean_net_ticks": _mean(group.get("net_ticks")),
                "resolution": _unique_or_mixed(group["resolution"]),
                "recon_status": _unique_or_mixed(group["recon_status"]),
                "zone_params_hash": str(digest or ""),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _zone_width_bucket(value: object) -> str | None:
    width = _optional_float(value)
    if width is None:
        return None
    if width <= 2:
        return ZONE_WIDTH_LE_2
    if width <= 4:
        return ZONE_WIDTH_3_4
    return ZONE_WIDTH_GE_5


def _zone_count_bucket(value: object) -> str | None:
    if _is_missing(value):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    if count == 1:
        return ZONE_COUNT_1
    if count == 2:
        return ZONE_COUNT_2
    if count == 3:
        return ZONE_COUNT_3
    if count >= 4:
        return ZONE_COUNT_4_PLUS
    return None


def _is_attributed_zone(value: object) -> bool:
    if _is_missing(value):
        return False
    return str(value) != ZONE_REL_NONE


def _q4_q6(
    payload: Mapping[str, object] | None,
    frame: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    bracket_cols = [
        "cf_id",
        "sl_ticks",
        "tp_ticks",
        "n",
        "exit_rule_delta",
        "mean_cf_net_ticks",
        "entry_edge_flag",
        "best_mean_cf_net_ticks",
        "resolution",
        "recon_status",
    ]
    rule_cols = [
        "name",
        "declared_on",
        "split",
        "n",
        "n_kept",
        "trades_removed",
        "rule_delta_ticks",
        "resolution",
        "recon_status",
    ]
    empty_null: dict[str, object] = {
        "seed": None,
        "k": None,
        "n": 0,
        "direction_null_pct": None,
        "resolution": RESOLUTION_UNJOINED,
        "recon_status": RECON_UNKNOWN,
    }
    if payload is None and (frame is None or frame.empty):
        return pd.DataFrame(columns=bracket_cols), empty_null, pd.DataFrame(columns=rule_cols)
    resolution = RESOLUTION_UNJOINED
    recon = RECON_UNKNOWN
    if isinstance(payload, Mapping):
        raw_res = payload.get("resolution")
        if raw_res:
            resolution = str(raw_res)
    brackets_src: object = None
    edge_by_res: dict[str, Mapping[str, object]] = {}
    if isinstance(payload, Mapping):
        raw_brackets = payload.get("brackets")
        if isinstance(raw_brackets, Mapping) and "brackets" in raw_brackets:
            brackets_src = raw_brackets.get("brackets")
            raw_flags = raw_brackets.get("entry_edge_flag")
            if isinstance(raw_flags, Mapping):
                edge_by_res = {
                    str(key): value
                    for key, value in raw_flags.items()
                    if isinstance(value, Mapping)
                }
        else:
            brackets_src = raw_brackets
    rows: list[dict[str, object]] = []
    if isinstance(brackets_src, Mapping):
        for bucket in brackets_src.values():
            if not isinstance(bucket, Mapping):
                continue
            bucket_res = str(bucket.get("resolution") or resolution)
            flag_row = edge_by_res.get(bucket_res, {})
            rows.append(
                {
                    "cf_id": str(bucket.get("cf_id") or ""),
                    "sl_ticks": _optional_float(bucket.get("sl_ticks")),
                    "tp_ticks": _optional_float(bucket.get("tp_ticks")),
                    "n": int(bucket.get("n") or 0),
                    "exit_rule_delta": _optional_float(bucket.get("exit_rule_delta")),
                    "mean_cf_net_ticks": _optional_float(bucket.get("mean_cf_net_ticks")),
                    "entry_edge_flag": _optional_bool(
                        flag_row.get("entry_edge_flag") if isinstance(flag_row, Mapping) else None
                    ),
                    "best_mean_cf_net_ticks": (
                        _optional_float(flag_row.get("best_mean_cf_net_ticks"))
                        if isinstance(flag_row, Mapping)
                        else None
                    ),
                    "resolution": bucket_res,
                    "recon_status": recon,
                }
            )
    q4 = pd.DataFrame(rows, columns=bracket_cols)
    null = dict(empty_null)
    if isinstance(payload, Mapping):
        raw_null = payload.get("null")
        if isinstance(raw_null, Mapping):
            null = {
                "seed": raw_null.get("seed"),
                "k": raw_null.get("k"),
                "n": int(raw_null.get("n") or 0),
                "direction_null_pct": _json_float(raw_null.get("direction_null_pct")),
                "resolution": resolution,
                "recon_status": recon,
            }
    rule_rows: list[dict[str, object]] = []
    if isinstance(payload, Mapping):
        raw_rules = payload.get("rules")
        if isinstance(raw_rules, list):
            for item in raw_rules:
                if not isinstance(item, Mapping):
                    continue
                kept = item.get("n_kept")
                n_total = item.get("n_total")
                if n_total is not None:
                    n_value = int(n_total)
                elif item.get("n") is not None:
                    n_value = int(item.get("n") or 0)
                elif kept is not None:
                    n_value = int(kept)
                else:
                    n_value = 0
                rule_rows.append(
                    {
                        "name": str(item.get("name") or ""),
                        "declared_on": str(item.get("declared_on") or ""),
                        "split": str(item.get("split") or ""),
                        "n": n_value,
                        "n_kept": int(kept) if kept is not None else 0,
                        "trades_removed": int(item.get("trades_removed") or 0),
                        "rule_delta_ticks": _optional_float(item.get("rule_delta_ticks")),
                        "resolution": resolution,
                        "recon_status": recon,
                    }
                )
    return q4, null, pd.DataFrame(rule_rows, columns=rule_cols)


def _q7_q8(
    matches: pd.DataFrame | None,
    payload: Mapping[str, object] | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    class_cols = ["match_class", "n", "resolution", "recon_status"]
    ledger_cols = [
        "session_date",
        "n",
        "executed_cell",
        "systematic_unfilled",
        "product_mismatch",
        "adherence",
        "live_net_ticks",
        "live_expectancy_ticks",
        "cell_expectancy_ticks",
        "resolution",
        "recon_status",
    ]
    q7 = pd.DataFrame(columns=class_cols)
    if matches is not None and isinstance(matches, pd.DataFrame) and not matches.empty:
        work = matches.copy()
        work["resolution"] = (
            work["resolution"].map(_as_resolution)
            if "resolution" in work.columns
            else RESOLUTION_UNJOINED
        )
        work["recon_status"] = (
            work["recon_status"].map(_as_recon) if "recon_status" in work.columns else RECON_UNKNOWN
        )
        q7 = _count_groups(work, "match_class", class_cols)
    ledger_rows: list[dict[str, object]] = []
    if isinstance(payload, Mapping):
        raw_ledger = payload.get("ledger")
        if isinstance(raw_ledger, list):
            for item in raw_ledger:
                if not isinstance(item, Mapping):
                    continue
                executed = int(item.get("executed_cell") or 0)
                unfilled = int(item.get("systematic_unfilled") or 0)
                ledger_rows.append(
                    {
                        "session_date": str(item.get("session_date") or ""),
                        "n": executed + unfilled,
                        "executed_cell": executed,
                        "systematic_unfilled": unfilled,
                        "product_mismatch": int(item.get("product_mismatch") or 0),
                        "adherence": _json_float(item.get("adherence")),
                        "live_net_ticks": _optional_float(item.get("live_net_ticks")),
                        "live_expectancy_ticks": _optional_float(item.get("live_expectancy_ticks")),
                        "cell_expectancy_ticks": _optional_float(item.get("cell_expectancy_ticks")),
                        "resolution": RESOLUTION_UNJOINED,
                        "recon_status": RECON_UNKNOWN,
                    }
                )
    return q7, pd.DataFrame(ledger_rows, columns=ledger_cols)


def _count_groups(frame: pd.DataFrame, column: str, columns: list[str]) -> pd.DataFrame:
    if column not in frame.columns:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for value, group in frame.groupby(column, sort=True, dropna=False):
        if _is_missing(value):
            continue
        rows.append(
            {
                column: str(value),
                "n": int(len(group)),
                "resolution": _unique_or_mixed(group["resolution"]),
                "recon_status": _unique_or_mixed(group["recon_status"]),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _tag_groups(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if "tag_alignment" not in frame.columns:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for value, group in frame.groupby("tag_alignment", sort=True, dropna=False):
        if _is_missing(value):
            continue
        mismatch = 0
        if "intent_mismatch" in group.columns:
            mismatch = int(sum(bool(item) for item in group["intent_mismatch"]))
        rows.append(
            {
                "tag_alignment": str(value),
                "n": int(len(group)),
                "intent_mismatch_n": mismatch,
                "resolution": _unique_or_mixed(group["resolution"]),
                "recon_status": _unique_or_mixed(group["recon_status"]),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _report_payload(report: JournalReport) -> dict[str, object]:
    return {
        "schema_version": JOURNAL_STORE_SCHEMA,
        "honesty": report.honesty,
        "include_small_n": report.include_small_n,
        "hidden_slice_count": report.hidden_slice_count,
        "present": dict(report.present),
        "captions": dict(report.captions),
        "q1_days": _records(report.q1_days),
        "q2_slices": _records(report.q2_slices),
        "q3_levels": _records(report.q3_levels),
        "q3_context": _records(report.q3_context),
        "q3_tags": _records(report.q3_tags),
        "q3_zones_count": _records(report.q3_zones_count),
        "q3_zones_width": _records(report.q3_zones_width),
        "q3_zones_relation": _records(report.q3_zones_relation),
        "q3_zones_names": _records(report.q3_zones_names),
        "q3_triggers": _records(report.q3_triggers),
        "q4_brackets": _records(report.q4_brackets),
        "q5_null": {key: _jsonable(value) for key, value in report.q5_null.items()},
        "q6_rules": _records(report.q6_rules),
        "q7_matches": _records(report.q7_matches),
        "q8_ledger": _records(report.q8_ledger),
    }


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame is None or frame.empty:
        return []
    return [
        {key: _jsonable(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _optional_table(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise JournalIngestError(f"unsupported journal table: {path.name}")


def _optional_json(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise JournalIngestError(f"{path.name} must be a JSON object")
    return payload


def _assert_output_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = [part.lower() for part in resolved.parts]
    for index, part in enumerate(parts[:-1]):
        if part == "results" and parts[index + 1] == "studies":
            raise JournalIngestError("journal report must not write into results/studies/")
    return resolved


def _derive_gross_ticks(work: pd.DataFrame) -> list[float | None]:
    """Prefer ``gross_ticks``, else ``gross_pnl_currency``, else net+fee+day extra."""
    count = len(work)
    explicit = (
        [_optional_float(value) for value in work["gross_ticks"].tolist()]
        if "gross_ticks" in work.columns
        else [None] * count
    )
    currencies = (
        list(work["gross_pnl_currency"].tolist())
        if "gross_pnl_currency" in work.columns
        else [None] * count
    )
    extras = (
        list(work["day_fee_allocation"].tolist())
        if "day_fee_allocation" in work.columns
        else [None] * count
    )
    instruments = list(work["instrument"].tolist())
    nets = (
        [_optional_float(value) for value in work["net_ticks"].tolist()]
        if "net_ticks" in work.columns
        else [None] * count
    )
    fees = (
        [_optional_float(value) for value in work["fee_ticks"].tolist()]
        if "fee_ticks" in work.columns
        else [None] * count
    )
    derived: list[float | None] = []
    for index in range(count):
        if explicit[index] is not None:
            derived.append(explicit[index])
            continue
        from_currency = _currency_to_ticks(currencies[index], instruments[index])
        if from_currency is not None:
            derived.append(from_currency)
            continue
        net = nets[index]
        fee = fees[index]
        extra = _currency_to_ticks(extras[index], instruments[index]) or 0.0
        if net is not None and fee is not None:
            derived.append(net + fee + extra)
            continue
        derived.append(None)
    return derived


def _currency_to_ticks(currency: object, instrument: object) -> float | None:
    value = _optional_float(currency)
    if value is None:
        return None
    name = str(instrument)
    if name not in JOURNAL_POINT_VALUE:
        return None
    tick_value = JOURNAL_TICK_SIZE * JOURNAL_POINT_VALUE[name]
    if tick_value <= 0:
        return None
    return value / tick_value


def _hold_bucket(value: object) -> str | None:
    seconds = _optional_float(value)
    if seconds is None:
        return None
    if seconds < _HOLD_15:
        return HOLD_LT_15S
    if seconds < _HOLD_60:
        return HOLD_15_60S
    if seconds < _HOLD_300:
        return HOLD_1_5MIN
    return HOLD_GT_5MIN


def _ny_hour(value: object) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return int(stamp.tz_convert(JOURNAL_EXCHANGE_TZ).hour)


def _as_utc(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise JournalIngestError("entry_timestamp is missing")
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _as_date(value: object) -> date:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            raise JournalIngestError("session_date is missing")
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise JournalIngestError(f"invalid session_date {value!r}") from exc
    if pd.isna(stamp):
        raise JournalIngestError("session_date is missing")
    return stamp.date()


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _coalesce_meta(frame: pd.DataFrame, column: str, *, default: str) -> pd.Series:
    """Prefer ``column``, then ``column_trade``, then ``default`` (per row)."""
    own = frame[column] if column in frame.columns else None
    trade = frame[f"{column}_trade"] if f"{column}_trade" in frame.columns else None
    values: list[object] = []
    length = len(frame)
    for index in range(length):
        candidate = own.iloc[index] if own is not None else None
        if _is_missing(candidate):
            candidate = trade.iloc[index] if trade is not None else None
        values.append(default if _is_missing(candidate) else candidate)
    return pd.Series(values, index=frame.index)


def _as_resolution(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return RESOLUTION_UNJOINED
    text = str(value).strip()
    return text or RESOLUTION_UNJOINED


def _as_recon(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return RECON_UNKNOWN
    text = str(value).strip()
    return text or RECON_UNKNOWN


def _unique_or_mixed(series: pd.Series) -> str:
    values = sorted(
        {str(item) for item in series.tolist() if item is not None and not pd.isna(item)}
    )
    if not values:
        return RECON_UNKNOWN
    if len(values) == 1:
        return values[0]
    return RESOLUTION_MIXED


def _mean(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    values = [_optional_float(item) for item in series.tolist()]
    finite = [item for item in values if item is not None]
    if not finite:
        return None
    return sum(finite) / len(finite)


def _sum(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    values = [_optional_float(item) for item in series.tolist()]
    finite = [item for item in values if item is not None]
    if not finite:
        return None
    return sum(finite)


def _optional_bool(value: object) -> bool | None:
    if value is None or _is_missing(value):
        return None
    if isinstance(value, bool):
        return value
    item = getattr(value, "item", None)
    if callable(item) and type(value).__module__ == "numpy":
        try:
            value = item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, bool):
        return value
    return bool(value)


def _optional_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_float(value: object) -> float | None:
    return _optional_float(value)


def _jsonable(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (date, datetime, pd.Timestamp)):
        if isinstance(value, pd.Timestamp) and pd.isna(value):
            return None
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item) and type(value).__module__ == "numpy":
        try:
            value = item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value) if math.isfinite(value) else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
