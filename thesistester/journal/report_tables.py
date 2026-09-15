"""TJ9 payload-to-table helpers (C-25 / QI-08-04).

Q3 zone/trigger tables plus Q4–Q8 JSON payload assembly. Classify tokens
live in ``match_classify.py`` (re-exported from ``match.py``). CF walk math
stays on ``counterfactual.py``. No Streamlit. ``build_journal_report``
stays on ``report.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
import math

import pandas as pd

from thesistester.journal.schema import (
    RECON_UNKNOWN,
    REPORT_MIN_N,
    RESOLUTION_MIXED,
    RESOLUTION_UNJOINED,
    TRIGGER_NONE,
    TRIGGER_RESOLUTION_1M,
    ZONE_COUNT_1,
    ZONE_COUNT_2,
    ZONE_COUNT_3,
    ZONE_COUNT_4_PLUS,
    ZONE_REL_NONE,
    ZONE_WIDTH_3_4,
    ZONE_WIDTH_GE_5,
    ZONE_WIDTH_LE_2,
    decode_trigger_labels,
)


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


def _json_float(value: object) -> float | None:
    return _optional_float(value)


def _mean(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    values = [_optional_float(item) for item in series.tolist()]
    finite = [item for item in values if item is not None]
    if not finite:
        return None
    return sum(finite) / len(finite)


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


def _is_attributed_zone(value: object) -> bool:
    if _is_missing(value):
        return False
    return str(value) != ZONE_REL_NONE


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


def _zone_groups(
    frame: pd.DataFrame,
    column: str,
    columns: list[str],
    *,
    include_small_n: bool,
) -> tuple[pd.DataFrame, int]:
    if column not in frame.columns or frame.empty:
        return pd.DataFrame(columns=columns), 0
    rows: list[dict[str, object]] = []
    hidden = 0
    grouped = frame.groupby([column, "zone_params_hash"], sort=True, dropna=False)
    for (value, digest), group in grouped:
        if _is_missing(value):
            continue
        n_value = int(len(group))
        if n_value < REPORT_MIN_N:
            hidden += 1
            if not include_small_n:
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
    return pd.DataFrame(rows, columns=columns), hidden


def _q3_zones(
    trades: pd.DataFrame,
    zones: pd.DataFrame | None,
    *,
    include_small_n: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, int]:
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
        return (*empty, 0)
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
    count, hidden_count = _zone_groups(
        attributed, "zone_level_count", count_cols, include_small_n=include_small_n
    )
    width, hidden_width = _zone_groups(
        attributed, "zone_width_bucket", width_cols, include_small_n=include_small_n
    )
    relation, hidden_relation = _zone_groups(
        work, "entry_zone_relation", relation_cols, include_small_n=include_small_n
    )
    names, hidden_names = _zone_groups(
        attributed, "zone_level_names", names_cols, include_small_n=include_small_n
    )
    return (
        count,
        width,
        relation,
        names,
        hidden_count + hidden_width + hidden_relation + hidden_names,
    )


def _q3_triggers(
    trades: pd.DataFrame,
    triggers: pd.DataFrame | None,
    *,
    include_small_n: bool,
) -> tuple[pd.DataFrame, int]:
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
        return pd.DataFrame(columns=columns), 0
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
    filter_zone_id = "zone_id" in work.columns
    for raw in work.to_dict(orient="records"):
        if filter_zone_id and _is_missing(raw.get("zone_id")):
            continue
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
        return pd.DataFrame(columns=columns), 0
    rows: list[dict[str, object]] = []
    hidden = 0
    grouped = exploded.groupby(
        ["inferred_trigger", "zone_params_hash", "trigger_resolution"],
        sort=True,
        dropna=False,
    )
    for (label, digest, trig_res), group in grouped:
        n_value = int(len(group))
        if n_value < REPORT_MIN_N:
            hidden += 1
            if not include_small_n:
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
    return pd.DataFrame(rows, columns=columns), hidden


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
