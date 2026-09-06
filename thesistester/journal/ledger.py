"""Forward ledger for a promoted named cell (TJ8).

Read-only over ingested match artifacts. Never writes a promotion registry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
import json

import pandas as pd
import yaml

from thesistester.journal.schema import (
    MATCH_DISCRETIONARY_ONLY,
    MATCH_EXECUTED_CELL,
    MATCH_NEAR_LEVEL,
    MATCH_PRODUCT_MISMATCH,
    MATCH_SIDE_JOURNAL,
    MATCH_SYSTEMATIC_UNFILLED,
    JournalIngestError,
)

_CLASS_KEYS = (
    MATCH_EXECUTED_CELL,
    MATCH_NEAR_LEVEL,
    MATCH_DISCRETIONARY_ONLY,
    MATCH_SYSTEMATIC_UNFILLED,
    MATCH_PRODUCT_MISMATCH,
)


def load_live_declarations(path: str | Path | None) -> dict[str, date]:
    """Read ``live_since`` declarations. Never writes the source file."""
    if path is None:
        return {}
    source = Path(path)
    if not source.is_file():
        raise JournalIngestError(f"live declarations not found: {source}")
    text = source.read_text(encoding="utf-8")
    suffix = source.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(text)
    elif suffix == ".json":
        payload = json.loads(text)
    else:
        raise JournalIngestError("live declarations must be .yaml, .yml, or .json")
    rows: Sequence[object]
    if isinstance(payload, Mapping):
        raw = payload.get("cells", payload.get("rules", payload))
        if isinstance(raw, Mapping) and "run_name" in raw:
            rows = [raw]
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            rows = raw
        else:
            raise JournalIngestError("live declarations must be a list of cells")
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        rows = payload
    else:
        raise JournalIngestError("live declarations must be a list or mapping")
    out: dict[str, date] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            raise JournalIngestError("each live declaration must be a mapping")
        name = str(item.get("run_name") or item.get("cell_id") or "").strip()
        if not name:
            raise JournalIngestError("live declaration run_name is required")
        if "live_since" not in item or item.get("live_since") in (None, ""):
            raise JournalIngestError(f"live declaration {name!r} is missing live_since")
        out[name] = _as_date(item["live_since"])
    return out


def build_forward_ledger(
    matches: pd.DataFrame,
    *,
    live_since: date | None,
    cell_expectancy_ticks: float | None,
) -> list[dict[str, object]]:
    """Per-session adherence and live vs backtest expectancy. Keyword-only.

    ``adherence`` = ``executed_cell / (executed_cell + systematic_unfilled)``.
    Sessions before ``live_since`` are omitted. ``live_since`` None → all sessions.
    """
    if matches is None or not isinstance(matches, pd.DataFrame) or matches.empty:
        return []
    work = matches.copy()
    work["session_date"] = work["session_date"].map(_as_date)
    if live_since is not None:
        work = work.loc[work["session_date"] >= live_since]
    if work.empty:
        return []
    rows: list[dict[str, object]] = []
    cumulative_n = 0
    cumulative_live = 0.0
    cumulative_live_n = 0
    for session, group in work.groupby("session_date", sort=True):
        counts = {key: 0 for key in _CLASS_KEYS}
        for klass, count in group["match_class"].value_counts().items():
            if klass in counts:
                counts[str(klass)] = int(count)
        executed = counts[MATCH_EXECUTED_CELL]
        unfilled = counts[MATCH_SYSTEMATIC_UNFILLED]
        denom = executed + unfilled
        adherence = (executed / denom) if denom else None
        journal = group.loc[
            (group["side"] == MATCH_SIDE_JOURNAL) & (group["match_class"] == MATCH_EXECUTED_CELL)
        ]
        live_values: list[float] = []
        for raw in journal.to_dict(orient="records"):
            net = _optional_float(raw.get("net_ticks"))
            if net is None:
                continue
            live_values.append(net)
        live_sum = sum(live_values) if live_values else None
        live_mean = (sum(live_values) / len(live_values)) if live_values else None
        cumulative_n += executed
        if live_values:
            cumulative_live += sum(live_values)
            cumulative_live_n += len(live_values)
        rows.append(
            {
                "session_date": session.isoformat(),
                "systematic_signals": unfilled + executed,
                "executed_cell": executed,
                "near_level": counts[MATCH_NEAR_LEVEL],
                "discretionary_only": counts[MATCH_DISCRETIONARY_ONLY],
                "systematic_unfilled": unfilled,
                "product_mismatch": counts[MATCH_PRODUCT_MISMATCH],
                "adherence": adherence,
                "live_net_ticks": live_sum,
                "live_expectancy_ticks": live_mean,
                "cell_expectancy_ticks": cell_expectancy_ticks,
                "cumulative_n": cumulative_n,
                "cumulative_live_expectancy_ticks": (
                    (cumulative_live / cumulative_live_n) if cumulative_live_n else None
                ),
            }
        )
    return rows


def _as_date(value: object) -> date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    return date.fromisoformat(str(value)[:10])


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
    return number
