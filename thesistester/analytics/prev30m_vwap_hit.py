"""Phase 2 analytics — R-multiple stats conditioned on prev30mVWAP early-window hits.

Pure post-trade helpers.  No fill / signal / level-engine changes.

Join contract (plan §3.8.2)
--------------------------
Attach **finalized** bracket ``hit_m1`` / ``hit_m5`` flags for each trade's
**entry** bracket (session-open 30m clock via ``entry_timestamp``).  In-window
``NaN`` rows on the levels frame are ignored; the bracket's finalized
``0.0``/``1.0`` is used once that window has completed in-sample.

Availability
------------
``prev30m_hit_r_summary`` reports ``available=True`` only when at least one
scoped trade receives a finalized (non-null) hit flag.  ``trade_count`` is the
number of such analyzable trades.  Grouped R stats and contingency tables use
the same trade universe: non-null flags **and** non-null ``r_multiple``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from thesistester.levels.prev30m_vwap import (
    COL_HIT_M1,
    COL_HIT_M5,
    COL_PREV30M_VWAP,
    session_bracket_keys,
)

HIT_M1_AT_ENTRY = "prev30mVWAP_hit_m1_at_entry"
HIT_M5_AT_ENTRY = "prev30mVWAP_hit_m5_at_entry"

_GROUP_METRIC_COLS: list[str] = [
    "trade_count",
    "avg_r",
    "median_r",
    "total_r",
    "win_rate",
]

_CONTINGENCY_COLS: list[str] = [
    HIT_M1_AT_ENTRY,
    HIT_M5_AT_ENTRY,
    "trade_count",
]


def _empty_group_frame(flag_col: str) -> pd.DataFrame:
    return pd.DataFrame(columns=[flag_col, *_GROUP_METRIC_COLS])


def _empty_contingency_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_CONTINGENCY_COLS)


def _trade_references_prev30m(level_names: Any) -> bool:
    if level_names is None or (isinstance(level_names, float) and np.isnan(level_names)):
        return False
    text = str(level_names)
    if not text or text.lower() == "nan":
        return False
    parts = [part.strip() for part in text.replace(",", "|").split("|")]
    # Phase 3 stack ages (_2…_N) are confluence price levels; hit R analytics
    # stay scoped to age-1 (`prev30mVWAP`) only — no per-age hit columns.
    return COL_PREV30M_VWAP in parts


def filter_prev30m_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Return trades whose ``level_names`` reference ``prev30mVWAP``.

    When ``level_names`` is absent (synthetic fixtures), return *trades* unchanged.
    """
    if trades is None or trades.empty:
        return trades.copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame()
    if "level_names" not in trades.columns:
        return trades.copy()
    mask = trades["level_names"].map(_trade_references_prev30m)
    return trades.loc[mask].copy()


def build_finalized_hit_lookup(
    levels: pd.DataFrame,
    *,
    instrument: str = "ES",
) -> pd.DataFrame:
    """Build one finalized ``hit_m1`` / ``hit_m5`` row per ``(session_date, bracket_idx)``.

    Uses the last non-NaN value observed in each bracket (bracket-constant after
    window completion).  Brackets that never finalize a window are omitted for
    that column (left as NaN on the lookup row if the other window finalized).
    """
    empty = pd.DataFrame(columns=["session_date", "bracket_idx", COL_HIT_M1, COL_HIT_M5])
    if levels is None or levels.empty or "timestamp" not in levels.columns:
        return empty
    if COL_HIT_M1 not in levels.columns and COL_HIT_M5 not in levels.columns:
        return empty

    work = levels.sort_values("timestamp").copy()
    try:
        keys = session_bracket_keys(work["timestamp"], instrument=instrument)
    except (ValueError, TypeError):
        return empty
    work = work.join(keys)
    work = work.dropna(subset=["bracket_idx"])
    if work.empty:
        return empty

    work["bracket_idx"] = work["bracket_idx"].astype("int64")
    rows: list[dict[str, Any]] = []
    for (sess, bidx), group in work.groupby(["session_date", "bracket_idx"], sort=True):
        row: dict[str, Any] = {"session_date": sess, "bracket_idx": int(bidx)}
        if COL_HIT_M1 in group.columns:
            m1 = group[COL_HIT_M1].dropna()
            row[COL_HIT_M1] = float(m1.iloc[-1]) if not m1.empty else np.nan
        else:
            row[COL_HIT_M1] = np.nan
        if COL_HIT_M5 in group.columns:
            m5 = group[COL_HIT_M5].dropna()
            row[COL_HIT_M5] = float(m5.iloc[-1]) if not m5.empty else np.nan
        else:
            row[COL_HIT_M5] = np.nan
        rows.append(row)
    if not rows:
        return empty
    return pd.DataFrame(rows)


def attach_prev30m_hit_flags(
    trades: pd.DataFrame,
    levels: pd.DataFrame,
    *,
    instrument: str = "ES",
    timestamp_col: str = "entry_timestamp",
) -> pd.DataFrame:
    """Return a copy of *trades* with finalized entry-bracket hit flags attached.

    Preserves the input index.  Timezone-naive / unkeyable timestamps leave flags
    as NaN instead of raising (callers treat that as unavailable analytics).
    """
    if trades is None:
        return pd.DataFrame(columns=[HIT_M1_AT_ENTRY, HIT_M5_AT_ENTRY])
    out = trades.copy()
    out[HIT_M1_AT_ENTRY] = np.nan
    out[HIT_M5_AT_ENTRY] = np.nan
    if out.empty or timestamp_col not in out.columns:
        return out
    if levels is None or levels.empty:
        return out

    lookup = build_finalized_hit_lookup(levels, instrument=instrument)
    if lookup.empty:
        return out

    try:
        keys = session_bracket_keys(out[timestamp_col], instrument=instrument)
    except (ValueError, TypeError):
        return out

    work = out.drop(columns=[HIT_M1_AT_ENTRY, HIT_M5_AT_ENTRY], errors="ignore").copy()
    work["_session_date"] = keys["session_date"].to_numpy()
    work["_bracket_idx"] = keys["bracket_idx"].to_numpy()
    work["_orig_index"] = work.index

    # Align bracket_idx dtype for merge (lookup uses int64; keys may be float NaN).
    lookup_keyed = lookup.copy()
    lookup_keyed["bracket_idx"] = lookup_keyed["bracket_idx"].astype("float64")

    merged = work.merge(
        lookup_keyed.rename(
            columns={
                "session_date": "_session_date",
                "bracket_idx": "_bracket_idx",
                COL_HIT_M1: HIT_M1_AT_ENTRY,
                COL_HIT_M5: HIT_M5_AT_ENTRY,
            }
        ),
        on=["_session_date", "_bracket_idx"],
        how="left",
    )
    merged = merged.drop(columns=["_session_date", "_bracket_idx"], errors="ignore")
    if HIT_M1_AT_ENTRY not in merged.columns:
        merged[HIT_M1_AT_ENTRY] = np.nan
    if HIT_M5_AT_ENTRY not in merged.columns:
        merged[HIT_M5_AT_ENTRY] = np.nan
    merged = merged.set_index("_orig_index")
    merged.index.name = out.index.name
    return merged


def summarize_r_by_hit_flag(
    trades: pd.DataFrame,
    flag_col: str,
) -> pd.DataFrame:
    """Grouped mean / median / count of ``r_multiple`` by a hit flag column."""
    empty = _empty_group_frame(flag_col)
    if trades is None or trades.empty:
        return empty
    if flag_col not in trades.columns or "r_multiple" not in trades.columns:
        return empty

    work = trades.dropna(subset=[flag_col]).copy()
    if work.empty:
        return empty

    rows: list[dict[str, Any]] = []
    for flag_val, group in work.groupby(flag_col, sort=True):
        r = group["r_multiple"].dropna()
        n = len(r)
        if n == 0:
            continue
        wins = r[r > 0]
        rows.append(
            {
                flag_col: float(flag_val),
                "trade_count": n,
                "avg_r": float(r.mean()),
                "median_r": float(r.median()),
                "total_r": float(r.sum()),
                "win_rate": float(len(wins) / n),
            }
        )
    if not rows:
        return empty
    return pd.DataFrame(rows)[[flag_col, *_GROUP_METRIC_COLS]]


def prev30m_hit_contingency(trades: pd.DataFrame) -> pd.DataFrame:
    """Joint ``(hit_m1, hit_m5)`` trade counts when both flags and R are present.

    Uses the same universe as ``summarize_r_by_hit_flag``: both finalized flags
    non-null and ``r_multiple`` non-null (when the column exists).
    """
    empty = _empty_contingency_frame()
    if trades is None or trades.empty:
        return empty
    if HIT_M1_AT_ENTRY not in trades.columns or HIT_M5_AT_ENTRY not in trades.columns:
        return empty
    required = [HIT_M1_AT_ENTRY, HIT_M5_AT_ENTRY]
    if "r_multiple" in trades.columns:
        required.append("r_multiple")
    both = trades.dropna(subset=required)
    if both.empty:
        return empty
    grouped = (
        both.groupby([HIT_M1_AT_ENTRY, HIT_M5_AT_ENTRY], sort=True)
        .size()
        .reset_index(name="trade_count")
    )
    return grouped[_CONTINGENCY_COLS]


def prev30m_hit_r_summary(
    trades: pd.DataFrame,
    levels: pd.DataFrame,
    *,
    instrument: str = "ES",
    timestamp_col: str = "entry_timestamp",
) -> dict[str, Any]:
    """Full Phase 2 summary: attach flags, group by m1/m5, joint contingency.

    Empty-trade / missing-column / timezone-naive safe.  Filters to trades that
    reference ``prev30mVWAP`` when ``level_names`` is present.  ``available`` is
    true only when at least one scoped trade has a finalized hit flag;
    ``trade_count`` counts those analyzable trades.
    """
    result: dict[str, Any] = {
        "available": False,
        "trade_count": 0,
        "by_hit_m1": _empty_group_frame(HIT_M1_AT_ENTRY),
        "by_hit_m5": _empty_group_frame(HIT_M5_AT_ENTRY),
        "contingency": _empty_contingency_frame(),
        "trades_with_flags": pd.DataFrame(),
    }
    if trades is None or not isinstance(trades, pd.DataFrame):
        return result
    if levels is None or not isinstance(levels, pd.DataFrame) or levels.empty:
        return result
    if COL_HIT_M1 not in levels.columns and COL_HIT_M5 not in levels.columns:
        return result

    scoped = filter_prev30m_trades(trades)
    if scoped.empty:
        return result

    flagged = attach_prev30m_hit_flags(
        scoped,
        levels,
        instrument=instrument,
        timestamp_col=timestamp_col,
    )
    analyzable = flagged.dropna(subset=[HIT_M1_AT_ENTRY, HIT_M5_AT_ENTRY], how="all")
    if analyzable.empty:
        result["trades_with_flags"] = flagged
        return result

    result["available"] = True
    result["trade_count"] = int(len(analyzable))
    result["trades_with_flags"] = flagged
    result["by_hit_m1"] = summarize_r_by_hit_flag(flagged, HIT_M1_AT_ENTRY)
    result["by_hit_m5"] = summarize_r_by_hit_flag(flagged, HIT_M5_AT_ENTRY)
    result["contingency"] = prev30m_hit_contingency(flagged)
    return result
