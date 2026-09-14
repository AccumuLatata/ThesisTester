"""TJ7 CF payload/table helpers (C-25 / QI-08-04).

Bracket-summary JSON and row-to-frame only. Walk math (``_walk_15s`` /
``_walk_ticks`` / ``_replay_one`` / ``_gross_ticks``) stays on
``counterfactual.py``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import json
import math

import pandas as pd

from thesistester.journal.schema import (
    CF_HONESTY,
    COUNTERFACTUAL_OUTPUT_COLUMNS,
    ENTRY_EDGE_MIN_N,
    JOURNAL_STORE_SCHEMA,
    JournalIngestError,
)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def summarize_bracket_replay(frame: pd.DataFrame, trades: pd.DataFrame) -> dict[str, object]:
    """Per-bracket exit-rule delta and per-resolution entry-edge flag."""
    net_by_id = {}
    if "trade_id" in trades.columns and "net_ticks" in trades.columns:
        for raw in trades.to_dict(orient="records"):
            net = _optional_float(raw.get("net_ticks"))
            if net is not None:
                net_by_id[str(raw["trade_id"])] = net
    by_bracket: dict[str, dict[str, object]] = {}
    trades_by_resolution: dict[str, set[str]] = {}
    resolved_by_resolution: dict[str, set[str]] = {}
    if frame.empty:
        return {
            "brackets": {},
            "entry_edge_flag": {},
            "caption": "three brackets were looked at (not a single pre-registered test)",
        }
    for raw in frame.to_dict(orient="records"):
        cf_id = str(raw["cf_id"])
        resolution = str(raw["resolution"])
        trade_id = str(raw["trade_id"])
        cf_net = _optional_float(raw.get("cf_net_ticks"))
        key = f"{cf_id}@{resolution}"
        bucket = by_bracket.setdefault(
            key,
            {
                "cf_id": cf_id,
                "sl_ticks": raw["sl_ticks"],
                "tp_ticks": raw["tp_ticks"],
                "max_hold_seconds": raw["max_hold_seconds"],
                "resolution": resolution,
                "n": 0,
                "n_resolved": 0,
                "sum_cf_net_ticks": 0.0,
                "sum_paired_cf_net_ticks": 0.0,
                "sum_net_ticks": 0.0,
                "paired": 0,
            },
        )
        bucket["n"] = int(bucket["n"]) + 1
        trades_by_resolution.setdefault(resolution, set()).add(trade_id)
        if cf_net is None:
            continue
        bucket["n_resolved"] = int(bucket["n_resolved"]) + 1
        bucket["sum_cf_net_ticks"] = float(bucket["sum_cf_net_ticks"]) + cf_net
        resolved_by_resolution.setdefault(resolution, set()).add(trade_id)
        realized = net_by_id.get(trade_id)
        if realized is None:
            continue
        # Same-entry pair only: open / unresolved rows do not move the delta.
        bucket["sum_paired_cf_net_ticks"] = float(bucket["sum_paired_cf_net_ticks"]) + cf_net
        bucket["sum_net_ticks"] = float(bucket["sum_net_ticks"]) + realized
        bucket["paired"] = int(bucket["paired"]) + 1
    for bucket in by_bracket.values():
        n_resolved = int(bucket["n_resolved"])
        bucket["exit_rule_delta"] = float(bucket["sum_paired_cf_net_ticks"]) - float(
            bucket["sum_net_ticks"]
        )
        bucket["mean_cf_net_ticks"] = (
            (float(bucket["sum_cf_net_ticks"]) / n_resolved) if n_resolved else None
        )
    flags: dict[str, object] = {}
    for resolution, trade_ids in trades_by_resolution.items():
        means = [
            float(bucket["mean_cf_net_ticks"])
            for bucket in by_bracket.values()
            if bucket["resolution"] == resolution
            and bucket["mean_cf_net_ticks"] is not None
            and int(bucket["n_resolved"]) >= ENTRY_EDGE_MIN_N
        ]
        best = max(means) if means else None
        flags[resolution] = {
            "n": len(trade_ids),
            "n_resolved": len(resolved_by_resolution.get(resolution, set())),
            "best_mean_cf_net_ticks": best,
            "entry_edge_flag": bool(best is not None and best > 0),
        }
    n_brackets = len({str(bucket["cf_id"]) for bucket in by_bracket.values()})
    if n_brackets == 3:
        caption = "three brackets were looked at (not a single pre-registered test)"
    else:
        caption = f"{n_brackets} brackets were looked at (not a single pre-registered test)"
    return {
        "brackets": by_bracket,
        "entry_edge_flag": flags,
        "caption": caption,
    }


def _cf_frame(rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(COUNTERFACTUAL_OUTPUT_COLUMNS))
    keep = [column for column in COUNTERFACTUAL_OUTPUT_COLUMNS if column in rows[0]]
    extra = [column for column in ("cf_exit_ts",) if column in rows[0]]
    out = pd.DataFrame(index=range(len(rows)))
    object_cols = {
        "cf_exit_price",
        "cf_gross_ticks",
        "cf_net_ticks",
        "cf_exit_ts",
        "max_hold_seconds",
    }
    for column in keep + extra:
        values = [row.get(column) for row in rows]
        if column in object_cols:
            out[column] = pd.Series(values, dtype="object")
        else:
            out[column] = pd.Series(values)
    return out


def write_counterfactual_artifacts(
    output_dir: str | Path,
    frame: pd.DataFrame,
    *,
    seed: int,
    k: int,
    resolution: str,
    null: Mapping[str, object],
    brackets_summary: Mapping[str, object],
    rules_summary: Sequence[Mapping[str, object]] = (),
) -> dict[str, Path]:
    """Write ``journal_counterfactuals.parquet`` + ``counterfactual.json``."""
    out = _assert_output_dir(Path(output_dir))
    out.mkdir(parents=True, exist_ok=True)
    parquet_path = out / "journal_counterfactuals.parquet"
    json_path = out / "counterfactual.json"
    payload = {
        "schema_version": JOURNAL_STORE_SCHEMA,
        "resolution": resolution,
        "seed": int(seed),
        "k": int(k),
        "honesty": CF_HONESTY,
        "null": dict(null),
        "brackets": brackets_summary,
        "rules": [dict(row) for row in rules_summary],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    frame.to_parquet(parquet_path, index=False)
    return {
        "journal_counterfactuals.parquet": parquet_path,
        "counterfactual.json": json_path,
    }


def _assert_output_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = [part.lower() for part in resolved.parts]
    for index, part in enumerate(parts[:-1]):
        if part == "results" and parts[index + 1] == "studies":
            raise JournalIngestError("journal counterfactual must not write into results/studies/")
    return resolved
