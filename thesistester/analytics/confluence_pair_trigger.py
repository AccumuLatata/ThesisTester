"""Pair / trigger-variant summarizers for confluence combo attribution.

C-13 (QI-05-03): extracted from ``confluence_attribution.py`` so pair/trigger
grouping stays apart from display-facing dataclass assembly
(``confluence_attribution_summary``, ``prepare_exact_combo_display``).
Public combo helpers remain importable from ``confluence_attribution``
(lazy re-exports; this module imports the facade for shared parse/summarize
helpers).
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

import pandas as pd

from thesistester.analytics import confluence_attribution as cca


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
    uniq = cca.parse_level_names(list(tokens))
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
    empty = cca._empty_group_frame(cca.PAIR_KEY_COL, [cca.PAIR_MODE_COL])
    if trades is None or not isinstance(trades, pd.DataFrame):
        return empty
    if trades.empty or "level_names" not in trades.columns:
        return empty
    if "r_multiple" not in trades.columns:
        return empty

    attached = cca.attach_combo_columns(trades)
    analyzable = attached.dropna(subset=["r_multiple"]).copy()
    if analyzable.empty:
        return empty

    analyzable = analyzable.loc[analyzable[cca.LEVEL_TOKEN_COUNT_COL] >= 2].copy()
    if analyzable.empty:
        return empty

    use_anchor = None
    if confluence_mode == "anchor_rules" and anchor_level is not None:
        candidate = str(anchor_level).strip()
        if candidate:
            use_anchor = candidate

    pair_rows: list[dict[str, Any]] = []
    for _, row in analyzable.iterrows():
        tokens = cca.parse_level_names(row.get("level_names"))
        if use_anchor and use_anchor in set(tokens):
            keys = pair_keys_for_tokens(tokens, anchor_level=use_anchor)
            mode = cca.PAIR_MODE_ANCHOR_PARTNER
        else:
            keys = pair_keys_for_tokens(tokens, anchor_level=None)
            mode = cca.PAIR_MODE_GENERIC
        if not keys:
            continue
        r_multiple = row.get("r_multiple")
        for key in keys:
            pair_rows.append(
                {
                    cca.PAIR_KEY_COL: key,
                    cca.PAIR_MODE_COL: mode,
                    "r_multiple": r_multiple,
                }
            )

    if not pair_rows:
        return empty

    exploded = pd.DataFrame(pair_rows)
    summarized = cca._summarize_r(exploded, cca.PAIR_KEY_COL, min_trades)
    if summarized.empty:
        return empty

    # pair_mode can mix if some trades lacked the anchor; prefer anchor_partner.
    mode_by_key = (
        exploded.groupby(cca.PAIR_KEY_COL, sort=False)[cca.PAIR_MODE_COL]
        .agg(
            lambda values: (
                cca.PAIR_MODE_ANCHOR_PARTNER
                if cca.PAIR_MODE_ANCHOR_PARTNER in set(values.astype(str))
                else cca.PAIR_MODE_GENERIC
            )
        )
        .reset_index()
    )
    merged = summarized.merge(mode_by_key, on=cca.PAIR_KEY_COL, how="left")
    return merged[[cca.PAIR_KEY_COL, cca.PAIR_MODE_COL, *cca._GROUP_METRIC_COLS]]


def summarize_by_exact_combo_and_trigger_variant(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame:
    """Group analyzable trades by ``exact_combo_key × direction × trigger_variant``.

    Returns all groups plus ``sample_warning``. Does not drop thin samples.
    Pre-filters null/empty (strip) ``trigger_variant`` and unusable ``direction``
    before grouping. Missing ``trigger_variant`` or ``direction`` column → empty
    frame.
    """
    empty = cca._empty_multi_group_frame(
        [cca.EXACT_COMBO_KEY_COL, cca.DIRECTION_COL, cca.TRIGGER_VARIANT_COL]
    )
    if trades is None or not isinstance(trades, pd.DataFrame):
        return empty
    if trades.empty or "level_names" not in trades.columns:
        return empty
    if "r_multiple" not in trades.columns:
        return empty
    if cca.TRIGGER_VARIANT_COL not in trades.columns:
        return empty
    if cca.DIRECTION_COL not in trades.columns:
        return empty

    attached = cca.attach_combo_columns(trades)
    analyzable = attached.dropna(subset=["r_multiple"]).copy()
    if analyzable.empty:
        return empty

    usable = cca._filter_usable_trigger_variant(analyzable)
    if usable.empty:
        return empty
    usable = cca._filter_usable_direction(usable)
    if usable.empty:
        return empty
    # Cross-view answers "which combination × variant"; empty-name sentinel rows
    # are not combinations (they remain visible on the Exact combo tab).
    usable = usable.loc[usable[cca.EXACT_COMBO_KEY_COL] != cca.EMPTY_LEVEL_NAMES_KEY].copy()
    if usable.empty:
        return empty

    return cca._summarize_r_multi(
        usable,
        [cca.EXACT_COMBO_KEY_COL, cca.DIRECTION_COL, cca.TRIGGER_VARIANT_COL],
        min_trades,
    )


def summarize_by_pair_and_trigger_variant(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
    anchor_level: str | None = None,
    confluence_mode: str | None = None,
) -> pd.DataFrame:
    """Soft pair_key × direction × trigger_variant attribution (PR 4 locks).

    Anchor-partner mode only when ``confluence_mode == "anchor_rules"`` with a
    known non-empty ``anchor_level``. Pre-filters null/empty variants and
    unusable ``direction`` before explode/groupby. Missing ``trigger_variant``
    or ``direction`` column → empty frame.
    """
    empty = pd.DataFrame(
        columns=[
            cca.PAIR_KEY_COL,
            cca.DIRECTION_COL,
            cca.TRIGGER_VARIANT_COL,
            cca.PAIR_MODE_COL,
            *cca._GROUP_METRIC_COLS,
        ]
    )
    if trades is None or not isinstance(trades, pd.DataFrame):
        return empty
    if trades.empty or "level_names" not in trades.columns:
        return empty
    if "r_multiple" not in trades.columns:
        return empty
    if cca.TRIGGER_VARIANT_COL not in trades.columns:
        return empty
    if cca.DIRECTION_COL not in trades.columns:
        return empty

    attached = cca.attach_combo_columns(trades)
    analyzable = attached.dropna(subset=["r_multiple"]).copy()
    if analyzable.empty:
        return empty

    usable = cca._filter_usable_trigger_variant(analyzable)
    if usable.empty:
        return empty
    usable = cca._filter_usable_direction(usable)
    if usable.empty:
        return empty

    usable = usable.loc[usable[cca.LEVEL_TOKEN_COUNT_COL] >= 2].copy()
    if usable.empty:
        return empty

    use_anchor = None
    if confluence_mode == "anchor_rules" and anchor_level is not None:
        candidate = str(anchor_level).strip()
        if candidate:
            use_anchor = candidate

    pair_rows: list[dict[str, Any]] = []
    for _, row in usable.iterrows():
        tokens = cca.parse_level_names(row.get("level_names"))
        if use_anchor and use_anchor in set(tokens):
            keys = pair_keys_for_tokens(tokens, anchor_level=use_anchor)
            mode = cca.PAIR_MODE_ANCHOR_PARTNER
        else:
            keys = pair_keys_for_tokens(tokens, anchor_level=None)
            mode = cca.PAIR_MODE_GENERIC
        if not keys:
            continue
        variant = str(row.get(cca.TRIGGER_VARIANT_COL)).strip()
        direction = str(row.get(cca.DIRECTION_COL)).strip().lower()
        r_multiple = row.get("r_multiple")
        for key in keys:
            pair_rows.append(
                {
                    cca.PAIR_KEY_COL: key,
                    cca.DIRECTION_COL: direction,
                    cca.TRIGGER_VARIANT_COL: variant,
                    cca.PAIR_MODE_COL: mode,
                    "r_multiple": r_multiple,
                }
            )

    if not pair_rows:
        return empty

    exploded = pd.DataFrame(pair_rows)
    summarized = cca._summarize_r_multi(
        exploded,
        [cca.PAIR_KEY_COL, cca.DIRECTION_COL, cca.TRIGGER_VARIANT_COL],
        min_trades,
    )
    if summarized.empty:
        return empty

    mode_by_key = (
        exploded.groupby(
            [cca.PAIR_KEY_COL, cca.DIRECTION_COL, cca.TRIGGER_VARIANT_COL],
            sort=False,
        )[cca.PAIR_MODE_COL]
        .agg(
            lambda values: (
                cca.PAIR_MODE_ANCHOR_PARTNER
                if cca.PAIR_MODE_ANCHOR_PARTNER in set(values.astype(str))
                else cca.PAIR_MODE_GENERIC
            )
        )
        .reset_index()
    )
    merged = summarized.merge(
        mode_by_key,
        on=[cca.PAIR_KEY_COL, cca.DIRECTION_COL, cca.TRIGGER_VARIANT_COL],
        how="left",
    )
    return merged[
        [
            cca.PAIR_KEY_COL,
            cca.DIRECTION_COL,
            cca.TRIGGER_VARIANT_COL,
            cca.PAIR_MODE_COL,
            *cca._GROUP_METRIC_COLS,
        ]
    ]
