"""Post-trade confluence combo attribution analytics.

Pure helpers for Backtest research views:

- exact combo (canonical sorted ``level_names`` sets)
- level membership (double-counting participants)
- parsed level-count buckets
- soft pairwise attribution (generic pairs or anchor-partner pairs)

No zone / signal / fill engine changes. Summaries return **all** groups with
``sample_warning``; UI owns hide-below-``min_trades`` presentation filtering.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Mapping

import numpy as np
import pandas as pd


EMPTY_LEVEL_NAMES_KEY = "__empty__"
EMPTY_LEVEL_NAMES_LABEL = "(no level names)"
UNKNOWN_LEVEL_COUNT_LABEL = "(unknown)"

EXACT_COMBO_KEY_COL = "exact_combo_key"
EXAMPLE_RAW_COL = "example_raw_level_names"
LEVEL_NAME_COL = "level_name"
LEVEL_COUNT_BUCKET_COL = "level_count_bucket"
LEVEL_TOKEN_COUNT_COL = "level_token_count"
PAIR_KEY_COL = "pair_key"
PAIR_MODE_COL = "pair_mode"

# Opt-in Time Analysis group dims (PR 5a). Append-only; never Focus/Promote dims.
COMBO_TIME_ANALYSIS_GROUP_COLS: tuple[str, ...] = (
    EXACT_COMBO_KEY_COL,
    LEVEL_COUNT_BUCKET_COL,
)

TIME_ANALYSIS_COMBO_DIAGNOSTIC_CAPTION = (
    "Combo / level-count grouping is post-trade diagnostic only: observed traded "
    "combinations from recorded `level_names`, with selection effects. Not a new "
    "signal model."
)

PAIR_MODE_GENERIC = "generic"
PAIR_MODE_ANCHOR_PARTNER = "anchor_partner"

MEMBERSHIP_DOUBLE_COUNT_WARNING = (
    "Membership attribution double-counts trades across levels. "
    "Use it to find useful participants, not as an additive PnL decomposition."
)
PAIRWISE_DOUBLE_COUNT_WARNING = (
    "Pairwise attribution double-counts trades across pairs. "
    "A trade with three levels contributes to three generic pairs, so pair-view "
    "total_r can exceed book total_r. Diagnostic only — not an additive PnL "
    "decomposition."
)
TRIGGER_3C_LEVEL_NAMES_WARNING = (
    "For 3c, level_names may be the tested level only, not full zone membership."
)

_GROUP_METRIC_COLS: list[str] = [
    "trade_count",
    "win_rate",
    "avg_r",
    "median_r",
    "total_r",
    "sample_warning",
]

_EXAMPLE_RAW_POSITION_COL = "__cca_example_raw_position__"


def _is_nullish(value: Any) -> bool:
    """True for None / NaN / NaT / pd.NA (scalar nulls only)."""
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    # Guard array-like results from non-scalars.
    return bool(result) if isinstance(result, (bool, np.bool_)) else False


def parse_level_names(raw: Any) -> list[str]:
    """Normalize ``|`` / ``,`` delimiters, strip, drop empties, de-dupe in order."""
    if _is_nullish(raw):
        return []
    if isinstance(raw, (list, tuple, set)):
        tokens: list[str] = []
        seen: set[str] = set()
        for item in raw:
            if _is_nullish(item):
                continue
            text = str(item).strip()
            if not text or text.lower() == "nan":
                continue
            if text not in seen:
                seen.add(text)
                tokens.append(text)
        return tokens

    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return []

    parts = [part.strip() for part in text.replace(",", "|").split("|")]
    tokens = []
    seen = set()
    for part in parts:
        if not part:
            continue
        if part not in seen:
            seen.add(part)
            tokens.append(part)
    return tokens


def exact_combo_key(raw: Any) -> str:
    """Canonical sorted combo key; ``EMPTY_LEVEL_NAMES_KEY`` when none."""
    tokens = parse_level_names(raw)
    if not tokens:
        return EMPTY_LEVEL_NAMES_KEY
    return "|".join(sorted(tokens))


def format_display_combo(
    tokens_or_key: Any,
    *,
    anchor_level: str | None = None,
) -> str:
    """UI display helper for combo labels.

    If ``anchor_level`` is present in the token set, render
    ``anchor|sorted(rest)``. Otherwise render the canonical sorted key.
    Never invents an anchor from token order.
    """
    if _is_nullish(tokens_or_key):
        return EMPTY_LEVEL_NAMES_LABEL

    if isinstance(tokens_or_key, (list, tuple, set)):
        tokens = parse_level_names(list(tokens_or_key))
    else:
        text = str(tokens_or_key).strip()
        if not text or text.lower() == "nan" or text == EMPTY_LEVEL_NAMES_KEY:
            return EMPTY_LEVEL_NAMES_LABEL
        tokens = parse_level_names(text)

    if not tokens:
        return EMPTY_LEVEL_NAMES_LABEL

    if anchor_level is not None:
        anchor = str(anchor_level).strip()
        if anchor and anchor in set(tokens):
            rest = sorted(token for token in tokens if token != anchor)
            return "|".join([anchor, *rest])

    return "|".join(sorted(tokens))


def attach_combo_columns(trades: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with ``exact_combo_key`` and parsed ``level_token_count``.

    ``level_token_count`` is the distinct parsed-token count from
    ``level_names`` (View C grain). Stored ``level_count`` is ignored.
    """
    if trades is None or not isinstance(trades, pd.DataFrame):
        return pd.DataFrame(columns=[EXACT_COMBO_KEY_COL, LEVEL_TOKEN_COUNT_COL])

    out = trades.copy()
    if "level_names" not in out.columns:
        out[EXACT_COMBO_KEY_COL] = EMPTY_LEVEL_NAMES_KEY
        out[LEVEL_TOKEN_COUNT_COL] = 0
        return out

    parsed = out["level_names"].map(parse_level_names)
    out[EXACT_COMBO_KEY_COL] = parsed.map(
        lambda tokens: EMPTY_LEVEL_NAMES_KEY if not tokens else "|".join(sorted(tokens))
    )
    out[LEVEL_TOKEN_COUNT_COL] = parsed.map(len).astype("int64")
    return out


def level_count_bucket_label(token_count: Any) -> int | str:
    """View-C level-count label: ``0 → "(unknown)"``, else the integer count.

    Matches Backtest Level count semantics (no raw ``0`` bucket). Time Analysis
    sorting of the resulting mixed int/str dim is handled by
    :func:`thesistester.analytics.time_analysis.summarize_by_group` / pivot
    helpers (numeric-aware keys), not by stringifying counts.
    """
    try:
        count = int(token_count)
    except (TypeError, ValueError):
        return UNKNOWN_LEVEL_COUNT_LABEL
    if count == 0:
        return UNKNOWN_LEVEL_COUNT_LABEL
    return count


def attach_level_count_bucket(trades: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with combo columns plus View-C ``level_count_bucket``.

    Used by Time Analysis opt-in count grouping so labels match Backtest
    Level count (never a raw integer ``0`` dim).
    """
    out = attach_combo_columns(trades)
    if out.empty and LEVEL_TOKEN_COUNT_COL not in out.columns:
        out[LEVEL_COUNT_BUCKET_COL] = pd.Series(dtype="object")
        return out
    out[LEVEL_COUNT_BUCKET_COL] = out[LEVEL_TOKEN_COUNT_COL].map(level_count_bucket_label)
    return out


def confluence_combo_grouping_available(trades: pd.DataFrame) -> bool:
    """True when Time Analysis may offer combo/count group dims.

    Equivalent to ``confluence_attribution_summary(...).available``: needs
    ``level_names``, non-null ``r_multiple``, and ≥1 nonempty parsed combo.
    Column presence alone is not enough.
    """
    if trades is None or not isinstance(trades, pd.DataFrame):
        return False
    if "level_names" not in trades.columns or "r_multiple" not in trades.columns:
        return False
    attached = attach_combo_columns(trades)
    analyzable = attached.dropna(subset=["r_multiple"])
    if analyzable.empty:
        return False
    return bool((analyzable[LEVEL_TOKEN_COUNT_COL] > 0).any())


def append_confluence_time_analysis_group_options(
    options: list[str],
    *,
    available: bool,
    columns: Any,
) -> list[str]:
    """Append combo/count dims after existing options when the available gate holds.

    Never prepends (preserves Time Analysis ``index=0`` time-bucket default).
    Does not add pairs or membership dims.
    """
    out = list(options)
    if not available:
        return out
    present = set(columns) if columns is not None else set()
    for col in COMBO_TIME_ANALYSIS_GROUP_COLS:
        if col in present and col not in out:
            out.append(col)
    return out


def time_analysis_combo_group_caption(
    trades: pd.DataFrame,
    selected_group_cols: list[str] | tuple[str, ...] | str | None,
) -> str | None:
    """Honesty caption when a combo/count Time Analysis dim is selected."""
    if selected_group_cols is None:
        return None
    if isinstance(selected_group_cols, str):
        selected = [selected_group_cols]
    else:
        selected = [str(col) for col in selected_group_cols if col]
    if not any(col in COMBO_TIME_ANALYSIS_GROUP_COLS for col in selected):
        return None

    parts = [TIME_ANALYSIS_COMBO_DIAGNOSTIC_CAPTION]
    if (
        trades is not None
        and isinstance(trades, pd.DataFrame)
        and not trades.empty
        and "trigger" in trades.columns
        and (trades["trigger"].astype(str) == "3c").any()
    ):
        parts.append(TRIGGER_3C_LEVEL_NAMES_WARNING)
    return " ".join(parts)


def _clamp_min_trades(min_trades: int) -> int:
    try:
        value = int(min_trades)
    except (TypeError, ValueError):
        value = 10
    return max(value, 1)


def _empty_group_frame(group_col: str, extra_cols: list[str] | None = None) -> pd.DataFrame:
    cols = [group_col, *(extra_cols or []), *_GROUP_METRIC_COLS]
    return pd.DataFrame(columns=cols)


def _summarize_r(
    trades: pd.DataFrame,
    group_col: str,
    min_trades: int,
    *,
    extra_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Lean grouped R metrics with ``sample_warning``; never drops thin groups."""
    empty = _empty_group_frame(group_col, extra_cols)
    if trades is None or not isinstance(trades, pd.DataFrame) or trades.empty:
        return empty
    if group_col not in trades.columns or "r_multiple" not in trades.columns:
        return empty

    work = trades.dropna(subset=["r_multiple"]).copy()
    if work.empty:
        return empty

    threshold = _clamp_min_trades(min_trades)
    rows: list[dict[str, Any]] = []
    for key, group in work.groupby(group_col, sort=False, dropna=False):
        r = group["r_multiple"]
        n = int(len(r))
        if n == 0:
            continue
        row: dict[str, Any] = {
            group_col: key,
            "trade_count": n,
            "win_rate": float((r > 0).mean()),
            "avg_r": float(r.mean()),
            "median_r": float(r.median()),
            "total_r": float(r.sum()),
            "sample_warning": bool(n < threshold),
        }
        if extra_cols:
            for col in extra_cols:
                if col in group.columns:
                    row[col] = group[col].iloc[0]
                else:
                    row[col] = None
        rows.append(row)

    if not rows:
        return empty

    out = pd.DataFrame(rows)
    out = out.sort_values(
        ["total_r", "trade_count"],
        ascending=[False, False],
        kind="mergesort",
    ).reset_index(drop=True)
    ordered = [group_col, *(extra_cols or []), *_GROUP_METRIC_COLS]
    return out[ordered]


def _sort_for_example_raw(trades: pd.DataFrame) -> pd.DataFrame:
    """Stable earliest-trade ordering for example raw ``level_names``.

    Prefer ``entry_timestamp`` then ``trade_id``. When both are absent, use a
    fresh positional column from ``reset_index(drop=True)`` — never sort a data
    column named ``index`` or a MultiIndex level.
    """
    work = trades.copy()
    sort_cols: list[str] = []
    if "entry_timestamp" in work.columns:
        sort_cols.append("entry_timestamp")
    if "trade_id" in work.columns:
        sort_cols.append("trade_id")
    if sort_cols:
        return work.sort_values(sort_cols, kind="mergesort", na_position="last")
    work = work.reset_index(drop=True)
    work[_EXAMPLE_RAW_POSITION_COL] = np.arange(len(work), dtype="int64")
    return work.sort_values([_EXAMPLE_RAW_POSITION_COL], kind="mergesort")


def summarize_by_exact_combo(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame:
    """Group analyzable trades by canonical exact combo key.

    Returns all groups plus ``sample_warning``. Does not drop thin samples.
    Includes ``example_raw_level_names`` from the earliest trade in each group.
    """
    empty = _empty_group_frame(EXACT_COMBO_KEY_COL, [EXAMPLE_RAW_COL])
    if trades is None or not isinstance(trades, pd.DataFrame):
        return empty
    if trades.empty or "level_names" not in trades.columns:
        return empty
    if "r_multiple" not in trades.columns:
        return empty

    attached = attach_combo_columns(trades)
    analyzable = attached.dropna(subset=["r_multiple"]).copy()
    if analyzable.empty:
        return empty

    ordered = _sort_for_example_raw(analyzable)
    example_raw = (
        ordered.groupby(EXACT_COMBO_KEY_COL, sort=False)["level_names"]
        .first()
        .rename(EXAMPLE_RAW_COL)
        .reset_index()
    )
    summarized = _summarize_r(analyzable, EXACT_COMBO_KEY_COL, min_trades)
    if summarized.empty:
        return empty
    merged = summarized.merge(example_raw, on=EXACT_COMBO_KEY_COL, how="left")
    return merged[[EXACT_COMBO_KEY_COL, EXAMPLE_RAW_COL, *_GROUP_METRIC_COLS]]


def summarize_by_level_membership(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame:
    """Group by distinct level token membership (double-counts trades).

    Empty-name trades contribute no membership rows.
    """
    empty = _empty_group_frame(LEVEL_NAME_COL)
    if trades is None or not isinstance(trades, pd.DataFrame):
        return empty
    if trades.empty or "level_names" not in trades.columns:
        return empty
    if "r_multiple" not in trades.columns:
        return empty

    attached = attach_combo_columns(trades)
    analyzable = attached.dropna(subset=["r_multiple"]).copy()
    if analyzable.empty:
        return empty

    analyzable = analyzable.loc[analyzable[LEVEL_TOKEN_COUNT_COL] > 0].copy()
    if analyzable.empty:
        return empty

    analyzable[LEVEL_NAME_COL] = analyzable["level_names"].map(parse_level_names)
    exploded = analyzable.explode(LEVEL_NAME_COL, ignore_index=True)
    exploded = exploded.dropna(subset=[LEVEL_NAME_COL])
    if exploded.empty:
        return empty
    return _summarize_r(exploded, LEVEL_NAME_COL, min_trades)


def summarize_by_level_count(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame:
    """Group by parsed distinct token count (not stored ``level_count``)."""
    empty = _empty_group_frame(LEVEL_COUNT_BUCKET_COL)
    if trades is None or not isinstance(trades, pd.DataFrame):
        return empty
    if trades.empty or "level_names" not in trades.columns:
        return empty
    if "r_multiple" not in trades.columns:
        return empty

    attached = attach_level_count_bucket(trades)
    analyzable = attached.dropna(subset=["r_multiple"]).copy()
    if analyzable.empty:
        return empty

    return _summarize_r(analyzable, LEVEL_COUNT_BUCKET_COL, min_trades)


def pair_keys_for_tokens(
    tokens: list[str] | tuple[str, ...] | set[str],
    *,
    anchor_level: str | None = None,
) -> list[str]:
    """Return soft pair keys for one trade's distinct level tokens.

    If ``anchor_level`` is present in the token set, emit anchor-partner keys
    ``anchor|support`` for each non-anchor support. Otherwise emit all unordered
    generic pairs as canonical sorted ``A|B`` keys. Never guesses an anchor.
    """
    uniq = parse_level_names(list(tokens))
    if len(uniq) < 2:
        return []

    anchor = str(anchor_level).strip() if anchor_level is not None else ""
    if anchor and anchor in set(uniq):
        partners = sorted(token for token in uniq if token != anchor)
        return [f"{anchor}|{partner}" for partner in partners]

    return ["|".join(pair) for pair in combinations(sorted(uniq), 2)]


def summarize_by_level_pairs(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
    anchor_level: str | None = None,
    confluence_mode: str | None = None,
) -> pd.DataFrame:
    """Soft pairwise R attribution (double-counts across pairs).

    Anchor-partner mode is used only when ``confluence_mode == "anchor_rules"``
    and ``anchor_level`` is a non-empty string. For each trade, if that anchor is
    present in the trade tokens, emit ``anchor|support`` pairs; otherwise fall
    back to generic unordered pairs for that trade. Global / unknown mode always
    uses generic pairs. Trades with fewer than two distinct tokens contribute no
    pair rows.
    """
    empty = _empty_group_frame(PAIR_KEY_COL, [PAIR_MODE_COL])
    if trades is None or not isinstance(trades, pd.DataFrame):
        return empty
    if trades.empty or "level_names" not in trades.columns:
        return empty
    if "r_multiple" not in trades.columns:
        return empty

    attached = attach_combo_columns(trades)
    analyzable = attached.dropna(subset=["r_multiple"]).copy()
    if analyzable.empty:
        return empty

    analyzable = analyzable.loc[analyzable[LEVEL_TOKEN_COUNT_COL] >= 2].copy()
    if analyzable.empty:
        return empty

    use_anchor = None
    if confluence_mode == "anchor_rules" and anchor_level is not None:
        candidate = str(anchor_level).strip()
        if candidate:
            use_anchor = candidate

    pair_rows: list[dict[str, Any]] = []
    for _, row in analyzable.iterrows():
        tokens = parse_level_names(row.get("level_names"))
        if use_anchor and use_anchor in set(tokens):
            keys = pair_keys_for_tokens(tokens, anchor_level=use_anchor)
            mode = PAIR_MODE_ANCHOR_PARTNER
        else:
            keys = pair_keys_for_tokens(tokens, anchor_level=None)
            mode = PAIR_MODE_GENERIC
        if not keys:
            continue
        r_multiple = row.get("r_multiple")
        for key in keys:
            pair_rows.append(
                {
                    PAIR_KEY_COL: key,
                    PAIR_MODE_COL: mode,
                    "r_multiple": r_multiple,
                }
            )

    if not pair_rows:
        return empty

    exploded = pd.DataFrame(pair_rows)
    summarized = _summarize_r(exploded, PAIR_KEY_COL, min_trades)
    if summarized.empty:
        return empty

    # pair_mode can mix if some trades lacked the anchor; prefer anchor_partner.
    mode_by_key = (
        exploded.groupby(PAIR_KEY_COL, sort=False)[PAIR_MODE_COL]
        .agg(
            lambda values: (
                PAIR_MODE_ANCHOR_PARTNER
                if PAIR_MODE_ANCHOR_PARTNER in set(values.astype(str))
                else PAIR_MODE_GENERIC
            )
        )
        .reset_index()
    )
    merged = summarized.merge(mode_by_key, on=PAIR_KEY_COL, how="left")
    return merged[[PAIR_KEY_COL, PAIR_MODE_COL, *_GROUP_METRIC_COLS]]


def _empty_summary(min_trades: int = 10) -> dict[str, Any]:
    _ = min_trades  # kept for signature symmetry / future defaults
    return {
        "available": False,
        "trade_count": 0,
        "nonempty_combo_trade_count": 0,
        "empty_level_names_count": 0,
        "by_exact_combo": _empty_group_frame(EXACT_COMBO_KEY_COL, [EXAMPLE_RAW_COL]),
        "by_membership": _empty_group_frame(LEVEL_NAME_COL),
        "by_level_count": _empty_group_frame(LEVEL_COUNT_BUCKET_COL),
        "by_pairs": _empty_group_frame(PAIR_KEY_COL, [PAIR_MODE_COL]),
        "pair_mode": PAIR_MODE_GENERIC,
        "warnings": [],
    }


def confluence_attribution_summary(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
    anchor_level: str | None = None,
    confluence_mode: str | None = None,
) -> dict[str, Any]:
    """Bundle availability plus unfiltered attribution frames (incl. pairs)."""
    result = _empty_summary(min_trades)
    pair_mode = (
        PAIR_MODE_ANCHOR_PARTNER
        if confluence_mode == "anchor_rules"
        and isinstance(anchor_level, str)
        and bool(anchor_level.strip())
        else PAIR_MODE_GENERIC
    )
    result["pair_mode"] = pair_mode

    if trades is None or not isinstance(trades, pd.DataFrame):
        return result
    if "level_names" not in trades.columns:
        return result
    if "r_multiple" not in trades.columns:
        return result

    attached = attach_combo_columns(trades)
    analyzable = attached.dropna(subset=["r_multiple"])
    trade_count = int(len(analyzable))

    def _displayed_trigger_warnings() -> list[str]:
        # Plan §5.4: warn when any trade in the *displayed* set is 3c,
        # independent of R analyzability / available.
        if "trigger" not in attached.columns or attached.empty:
            return []
        trigger_series = attached["trigger"].astype(str)
        if (trigger_series == "3c").any():
            return [TRIGGER_3C_LEVEL_NAMES_WARNING]
        return []

    def _pair_frame() -> pd.DataFrame:
        return summarize_by_level_pairs(
            trades,
            min_trades=min_trades,
            anchor_level=anchor_level,
            confluence_mode=confluence_mode,
        )

    if trade_count == 0:
        result["by_exact_combo"] = summarize_by_exact_combo(trades, min_trades=min_trades)
        result["by_membership"] = summarize_by_level_membership(trades, min_trades=min_trades)
        result["by_level_count"] = summarize_by_level_count(trades, min_trades=min_trades)
        result["by_pairs"] = _pair_frame()
        result["warnings"] = _displayed_trigger_warnings()
        return result

    empty_mask = analyzable[LEVEL_TOKEN_COUNT_COL] <= 0
    empty_count = int(empty_mask.sum())
    nonempty_count = int((~empty_mask).sum())

    result["trade_count"] = trade_count
    result["empty_level_names_count"] = empty_count
    result["nonempty_combo_trade_count"] = nonempty_count
    result["by_exact_combo"] = summarize_by_exact_combo(trades, min_trades=min_trades)
    result["by_membership"] = summarize_by_level_membership(trades, min_trades=min_trades)
    result["by_level_count"] = summarize_by_level_count(trades, min_trades=min_trades)
    result["by_pairs"] = _pair_frame()

    trigger_warnings = _displayed_trigger_warnings()
    if nonempty_count <= 0:
        result["warnings"] = trigger_warnings
        return result

    result["available"] = True
    warnings = [MEMBERSHIP_DOUBLE_COUNT_WARNING, PAIRWISE_DOUBLE_COUNT_WARNING, *trigger_warnings]
    result["warnings"] = warnings
    return result


def apply_sample_warning_filter(
    frame: pd.DataFrame,
    *,
    hide_below_min: bool,
) -> pd.DataFrame:
    """Presentation filter: optionally drop rows with ``sample_warning``.

    Analytics summaries always return thin groups; Backtest UI owns hiding.
    """
    if frame is None or not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    if frame.empty or not hide_below_min or "sample_warning" not in frame.columns:
        return frame.copy()
    mask = ~frame["sample_warning"].fillna(False).astype(bool)
    return frame.loc[mask].copy()


def pairs_empty_info_message(raw_pairs: pd.DataFrame | None) -> str:
    """Honest empty-state copy for the Backtest Pairs tab.

    When unfiltered ``by_pairs`` has rows, an empty display is from the
    hide-below-min presentation filter — not from missing multi-level trades.
    """
    if isinstance(raw_pairs, pd.DataFrame) and not raw_pairs.empty:
        return "No pair rows to display under the current filter."
    return "No pair rows to display (need trades with at least two distinct level names)."


def resolve_signal_setup_for_attribution(
    *,
    signal_settings: Any = None,
    last_signal_setup: Any = None,
    setup_config: Any = None,
    signal_context: Any = None,
) -> dict[str, Any]:
    """Pick signal-run setup identity for captions / anchor display.

    Prefer the settings that produced the current signals over a possibly stale
    Setup Builder ``setup_config`` (same identity order as OTF/Validation):

    1. ``signal_settings``
    2. ``signal_settings["setup_snapshot"]``
    3. ``last_signal_setup``
    4. ``setup_config``
    5. ``signal_context``

    Returns a thin dict with ``confluence_mode`` and optional ``anchor_level``.
    Empty when no source carries a known mode.
    """
    sources: list[Mapping[str, Any]] = []
    if isinstance(signal_settings, dict) and signal_settings:
        sources.append(signal_settings)
        snapshot = signal_settings.get("setup_snapshot")
        if isinstance(snapshot, dict) and snapshot:
            sources.append(snapshot)
    for candidate in (last_signal_setup, setup_config, signal_context):
        if isinstance(candidate, dict) and candidate:
            sources.append(candidate)

    for source in sources:
        mode = str(source.get("confluence_mode") or "").strip()
        if mode not in {"anchor_rules", "global_cluster"}:
            continue
        result: dict[str, Any] = {"confluence_mode": mode}
        anchor = source.get("anchor_level")
        if isinstance(anchor, str) and anchor.strip():
            result["anchor_level"] = anchor.strip()
        elif mode == "anchor_rules":
            # Borrow anchor from an identity-compatible source (never from a
            # conflicting global_cluster snapshot).
            for other in sources:
                other_mode = str(other.get("confluence_mode") or "").strip()
                if other_mode not in {"", "anchor_rules"}:
                    continue
                other_anchor = other.get("anchor_level")
                if isinstance(other_anchor, str) and other_anchor.strip():
                    result["anchor_level"] = other_anchor.strip()
                    break
        return result
    return {}


def resolve_confluence_mode(
    setup_config: Any = None,
    trades: pd.DataFrame | None = None,
) -> str:
    """Best-effort mode label for captions: anchor_rules / global_cluster / unknown.

    ``setup_config`` should be the signal-run identity dict from
    ``resolve_signal_setup_for_attribution`` when called from Backtest.
    """
    if isinstance(setup_config, dict):
        mode = str(setup_config.get("confluence_mode") or "").strip()
        if mode in {"anchor_rules", "global_cluster"}:
            return mode

    if isinstance(trades, pd.DataFrame) and not trades.empty:
        if "level_source_mode" in trades.columns:
            modes = (
                trades["level_source_mode"]
                .dropna()
                .astype(str)
                .str.strip()
                .replace("", pd.NA)
                .dropna()
            )
            if not modes.empty:
                dominant = str(modes.value_counts().index[0])
                if dominant in {"anchor_rules", "global_cluster"}:
                    return dominant
                # Signals/backtest may stamp 3c source labels such as user_anchor.
                if dominant in {"user_anchor", "anchor"}:
                    return "anchor_rules"
                if dominant in {"global_cluster", "cluster", "global"}:
                    return "global_cluster"
    return "unknown"


def prepare_exact_combo_display(
    frame: pd.DataFrame,
    *,
    anchor_level: str | None = None,
    confluence_mode: str | None = None,
) -> pd.DataFrame:
    """Add ``display_combo`` for UI; anchor formatting only in anchor_rules mode."""
    if frame is None or not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    out = frame.copy()
    if out.empty or EXACT_COMBO_KEY_COL not in out.columns:
        return out

    use_anchor = None
    if confluence_mode == "anchor_rules" and anchor_level:
        use_anchor = str(anchor_level).strip() or None

    out["display_combo"] = out[EXACT_COMBO_KEY_COL].map(
        lambda key: format_display_combo(key, anchor_level=use_anchor)
    )
    return out
