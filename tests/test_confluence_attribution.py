"""Confluence combo attribution analytics (plan PR 1)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thesistester.analytics.confluence_attribution import (
    COMBO_TIME_ANALYSIS_GROUP_COLS,
    EMPTY_LEVEL_NAMES_KEY,
    EMPTY_LEVEL_NAMES_LABEL,
    EXACT_COMBO_KEY_COL,
    EXAMPLE_RAW_COL,
    LEVEL_COUNT_BUCKET_COL,
    LEVEL_NAME_COL,
    MEMBERSHIP_DOUBLE_COUNT_WARNING,
    PAIR_KEY_COL,
    PAIR_MODE_ANCHOR_PARTNER,
    PAIR_MODE_COL,
    PAIR_MODE_GENERIC,
    PAIRWISE_DOUBLE_COUNT_WARNING,
    TIME_ANALYSIS_COMBO_DIAGNOSTIC_CAPTION,
    TRIGGER_3C_LEVEL_NAMES_WARNING,
    UNKNOWN_LEVEL_COUNT_LABEL,
    append_confluence_time_analysis_group_options,
    apply_sample_warning_filter,
    attach_combo_columns,
    attach_level_count_bucket,
    confluence_attribution_summary,
    confluence_combo_grouping_available,
    exact_combo_key,
    format_display_combo,
    level_count_bucket_label,
    pair_keys_for_tokens,
    pairs_empty_info_message,
    parse_level_names,
    prepare_exact_combo_display,
    resolve_confluence_mode,
    resolve_signal_setup_for_attribution,
    summarize_by_exact_combo,
    summarize_by_level_count,
    summarize_by_level_membership,
    summarize_by_level_pairs,
    time_analysis_combo_group_caption,
)
from thesistester.analytics.entry_window import FOCUSABLE_GROUP_COLS


def _plan_fixture_trades() -> pd.DataFrame:
    """Appendix A fixture from the confluence combo attribution plan."""
    return pd.DataFrame(
        {
            "trade_id": [1, 2, 3, 4, 5],
            "entry_timestamp": pd.to_datetime(
                [
                    "2024-01-02 09:31",
                    "2024-01-02 09:40",
                    "2024-01-02 10:05",
                    "2024-01-02 10:20",
                    "2024-01-02 11:00",
                ]
            ),
            "r_multiple": [1.0, -1.0, 0.5, None, 0.25],
            "level_count": [2, 2, 3, 1, 3],  # trade 5 disagrees on purpose
            "level_names": [
                "pdHigh|VWAP_rolling_1h",
                "VWAP_rolling_1h|pdHigh",
                "pdHigh|VWAP_rolling_1h|pdPOC",
                "",
                "pdHigh",
            ],
            "direction": ["long", "long", "short", "long", "long"],
            "trigger": ["touch", "touch", "touch", "touch", "3c"],
        }
    )


# ---------------------------------------------------------------------------
# parse_level_names / exact_combo_key / format_display_combo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        (np.nan, []),
        (pd.NA, []),
        (pd.NaT, []),
        ("", []),
        ("nan", []),
        ("NaN", []),
        ("A|B", ["A", "B"]),
        ("A, B", ["A", "B"]),
        (" A|A|B ", ["A", "B"]),
        ("A,,B|,C", ["A", "B", "C"]),
        (["B", "A", "B"], ["B", "A"]),
        ([pd.NA, "A", None, "B"], ["A", "B"]),
    ],
)
def test_parse_level_names(raw, expected):
    assert parse_level_names(raw) == expected


def test_exact_combo_key_canonicalizes_and_empties():
    assert exact_combo_key("B|A") == exact_combo_key("A|B") == "A|B"
    assert exact_combo_key("") == EMPTY_LEVEL_NAMES_KEY
    assert exact_combo_key(None) == EMPTY_LEVEL_NAMES_KEY
    assert exact_combo_key(np.nan) == EMPTY_LEVEL_NAMES_KEY
    assert exact_combo_key(pd.NA) == EMPTY_LEVEL_NAMES_KEY
    assert exact_combo_key(pd.NaT) == EMPTY_LEVEL_NAMES_KEY


def test_nullable_string_pd_na_does_not_invent_combo_key():
    """dtype=string nulls must bucket __empty__, not a literal '<NA>' token."""
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0, -0.5],
            "level_names": pd.Series([pd.NA, pd.NA], dtype="string"),
        }
    )
    attached = attach_combo_columns(trades)
    assert list(attached[EXACT_COMBO_KEY_COL]) == [EMPTY_LEVEL_NAMES_KEY, EMPTY_LEVEL_NAMES_KEY]
    assert list(attached["level_token_count"]) == [0, 0]
    summary = confluence_attribution_summary(trades, min_trades=1)
    assert summary["available"] is False
    assert summary["empty_level_names_count"] == 2
    assert summary["nonempty_combo_trade_count"] == 0
    assert summary["by_exact_combo"].iloc[0][EXACT_COMBO_KEY_COL] == EMPTY_LEVEL_NAMES_KEY
    assert "<NA>" not in set(summary["by_exact_combo"][EXACT_COMBO_KEY_COL].astype(str))


def test_format_display_combo_uses_explicit_anchor_only():
    assert format_display_combo("VWAP|pdHigh", anchor_level="pdHigh") == "pdHigh|VWAP"
    assert format_display_combo("VWAP|pdHigh", anchor_level="OR_High") == "VWAP|pdHigh"
    assert format_display_combo("VWAP|pdHigh", anchor_level=None) == "VWAP|pdHigh"
    assert format_display_combo(["pdPOC", "pdHigh"], anchor_level="pdHigh") == "pdHigh|pdPOC"
    assert format_display_combo(EMPTY_LEVEL_NAMES_KEY) == EMPTY_LEVEL_NAMES_LABEL
    assert format_display_combo("") == EMPTY_LEVEL_NAMES_LABEL
    # Never invents an anchor from first/cheapest token.
    assert format_display_combo("A|B", anchor_level="") == "A|B"


# ---------------------------------------------------------------------------
# attach + summarize helpers
# ---------------------------------------------------------------------------


def test_attach_combo_columns_uses_parsed_count_not_stored_level_count():
    trades = _plan_fixture_trades()
    attached = attach_combo_columns(trades)
    assert attached.loc[4, "level_token_count"] == 1
    assert attached.loc[4, "level_count"] == 3
    assert attached.loc[0, EXACT_COMBO_KEY_COL] == "VWAP_rolling_1h|pdHigh"
    assert attached.loc[1, EXACT_COMBO_KEY_COL] == "VWAP_rolling_1h|pdHigh"
    assert attached.loc[3, EXACT_COMBO_KEY_COL] == EMPTY_LEVEL_NAMES_KEY


def test_attach_combo_columns_missing_level_names_safe():
    trades = pd.DataFrame({"r_multiple": [1.0]})
    attached = attach_combo_columns(trades)
    assert attached.loc[0, EXACT_COMBO_KEY_COL] == EMPTY_LEVEL_NAMES_KEY
    assert attached.loc[0, "level_token_count"] == 0


def test_summarize_by_exact_combo_merges_flipped_order_and_example_raw():
    trades = _plan_fixture_trades()
    summary = summarize_by_exact_combo(trades, min_trades=10)
    merged = summary[summary[EXACT_COMBO_KEY_COL] == "VWAP_rolling_1h|pdHigh"].iloc[0]
    assert merged["trade_count"] == 2
    assert merged["avg_r"] == pytest.approx(0.0)
    assert merged["total_r"] == pytest.approx(0.0)
    assert merged["win_rate"] == pytest.approx(0.5)
    assert bool(merged["sample_warning"]) is True
    # Earliest entry_timestamp / trade_id wins for example raw.
    assert merged[EXAMPLE_RAW_COL] == "pdHigh|VWAP_rolling_1h"


def test_exact_combo_partition_identity_unfiltered():
    trades = _plan_fixture_trades()
    summary = summarize_by_exact_combo(trades, min_trades=10)
    analyzable = trades.dropna(subset=["r_multiple"])
    assert summary["trade_count"].sum() == len(analyzable) == 4
    assert summary["total_r"].sum() == pytest.approx(float(analyzable["r_multiple"].sum()))
    # Thin groups remain present (not dropped by analytics).
    assert bool(summary["sample_warning"].all())


def test_membership_double_count_and_empty_names_emit_no_rows():
    trades = _plan_fixture_trades()
    membership = summarize_by_level_membership(trades, min_trades=1)
    by_level = membership.set_index(LEVEL_NAME_COL)["trade_count"].to_dict()
    # Analyzable nonempty trades containing pdHigh: ids 1,2,3,5.
    assert by_level["pdHigh"] == 4
    assert by_level["VWAP_rolling_1h"] == 3
    assert by_level["pdPOC"] == 1
    assert EMPTY_LEVEL_NAMES_KEY not in by_level
    assert "" not in by_level
    # Double-count: membership total_r exceeds book total_r.
    book_total = float(trades.dropna(subset=["r_multiple"])["r_multiple"].sum())
    assert membership["total_r"].sum() > book_total


def test_level_count_uses_parsed_token_count_when_stored_disagrees():
    trades = _plan_fixture_trades()
    by_count = summarize_by_level_count(trades, min_trades=1)
    counts = by_count.set_index(LEVEL_COUNT_BUCKET_COL)["trade_count"].to_dict()
    assert counts["2"] == 2
    assert counts["3"] == 1
    assert counts["1"] == 1
    # Trade 5 stored level_count=3 but parsed names count=1.
    assert "3" in counts
    assert counts["3"] == 1
    assert UNKNOWN_LEVEL_COUNT_LABEL not in counts  # null-R empty trade excluded


def test_level_count_unknown_bucket_for_empty_names():
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0, -0.5],
            "level_names": ["", "nan"],
            "level_count": [4, 4],
        }
    )
    by_count = summarize_by_level_count(trades, min_trades=1)
    assert list(by_count[LEVEL_COUNT_BUCKET_COL]) == [UNKNOWN_LEVEL_COUNT_LABEL]
    assert by_count.iloc[0]["trade_count"] == 2


def test_breakeven_counted_but_not_a_win():
    trades = pd.DataFrame(
        {
            "r_multiple": [0.0, 1.0],
            "level_names": ["A", "A"],
        }
    )
    summary = summarize_by_exact_combo(trades, min_trades=1)
    row = summary.iloc[0]
    assert row["trade_count"] == 2
    assert row["win_rate"] == pytest.approx(0.5)
    assert row["total_r"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# confluence_attribution_summary availability contract
# ---------------------------------------------------------------------------


def test_summary_missing_column_unavailable():
    trades = pd.DataFrame({"r_multiple": [1.0, 2.0]})
    summary = confluence_attribution_summary(trades)
    assert summary["available"] is False
    assert summary["trade_count"] == 0
    assert summary["by_exact_combo"].empty
    assert summary["warnings"] == []


def test_summary_none_and_empty_safe():
    assert confluence_attribution_summary(None)["available"] is False  # type: ignore[arg-type]
    assert confluence_attribution_summary(pd.DataFrame())["available"] is False


def test_summary_only_empty_names_unavailable_but_counts_empty():
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0, -1.0],
            "level_names": ["", None],
        }
    )
    summary = confluence_attribution_summary(trades, min_trades=1)
    assert summary["available"] is False
    assert summary["trade_count"] == 2
    assert summary["empty_level_names_count"] == 2
    assert summary["nonempty_combo_trade_count"] == 0
    assert not summary["by_exact_combo"].empty
    assert summary["by_exact_combo"].iloc[0][EXACT_COMBO_KEY_COL] == EMPTY_LEVEL_NAMES_KEY
    assert summary["by_membership"].empty


def test_summary_available_with_nonempty_and_warnings():
    trades = _plan_fixture_trades()
    summary = confluence_attribution_summary(trades, min_trades=10)
    assert summary["available"] is True
    assert summary["trade_count"] == 4
    assert summary["nonempty_combo_trade_count"] == 4  # null-R empty excluded
    assert summary["empty_level_names_count"] == 0
    assert MEMBERSHIP_DOUBLE_COUNT_WARNING in summary["warnings"]
    assert PAIRWISE_DOUBLE_COUNT_WARNING in summary["warnings"]
    assert TRIGGER_3C_LEVEL_NAMES_WARNING in summary["warnings"]
    assert not summary["by_exact_combo"].empty
    assert not summary["by_membership"].empty
    assert not summary["by_level_count"].empty
    assert "by_pairs" in summary
    assert summary["pair_mode"] == PAIR_MODE_GENERIC


def test_summary_3c_warning_scans_full_displayed_set():
    """Plan §5.4: 3c honesty when any displayed trade is 3c (even null-R)."""
    # 3c only on a null-R row; other nonempty R trades still make available=True.
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0, None],
            "level_names": ["A|B", "A"],
            "trigger": ["touch", "3c"],
        }
    )
    summary = confluence_attribution_summary(trades, min_trades=1)
    assert summary["available"] is True
    assert TRIGGER_3C_LEVEL_NAMES_WARNING in summary["warnings"]
    assert MEMBERSHIP_DOUBLE_COUNT_WARNING in summary["warnings"]
    assert PAIRWISE_DOUBLE_COUNT_WARNING in summary["warnings"]

    # Also emit when attribution is unavailable (only empty names).
    empty_only = pd.DataFrame(
        {
            "r_multiple": [1.0],
            "level_names": [""],
            "trigger": ["3c"],
        }
    )
    empty_summary = confluence_attribution_summary(empty_only, min_trades=1)
    assert empty_summary["available"] is False
    assert empty_summary["warnings"] == [TRIGGER_3C_LEVEL_NAMES_WARNING]


def test_example_raw_positional_fallback_ignores_index_named_column():
    """Positional fallback must not sort a data column named ``index``."""
    trades = pd.DataFrame(
        {
            "index": [99, 1],
            "r_multiple": [1.0, 2.0],
            "level_names": ["B|A", "A|B"],
        }
    )
    summary = summarize_by_exact_combo(trades, min_trades=1)
    # First row position wins (not the smaller ``index`` data value).
    assert summary.iloc[0][EXAMPLE_RAW_COL] == "B|A"


def test_summary_mixed_null_r_excluded_from_counts():
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0, None, 2.0],
            "level_names": ["A|B", "A|B", "B|A"],
        }
    )
    summary = confluence_attribution_summary(trades, min_trades=1)
    assert summary["available"] is True
    assert summary["trade_count"] == 2
    assert summary["nonempty_combo_trade_count"] == 2
    combo = summary["by_exact_combo"]
    assert len(combo) == 1
    assert combo.iloc[0]["trade_count"] == 2
    assert combo.iloc[0]["total_r"] == pytest.approx(3.0)


def test_example_raw_fallback_without_timestamps_uses_trade_id():
    trades = pd.DataFrame(
        {
            "trade_id": [20, 10],
            "r_multiple": [1.0, 2.0],
            "level_names": ["B|A", "A|B"],
        }
    )
    summary = summarize_by_exact_combo(trades, min_trades=1)
    assert summary.iloc[0][EXAMPLE_RAW_COL] == "A|B"  # lower trade_id


# ---------------------------------------------------------------------------
# PR 2 presentation helpers
# ---------------------------------------------------------------------------


def test_apply_sample_warning_filter_hides_thin_rows_only_when_requested():
    frame = pd.DataFrame(
        {
            EXACT_COMBO_KEY_COL: ["A", "B"],
            "trade_count": [12, 3],
            "sample_warning": [False, True],
        }
    )
    hidden = apply_sample_warning_filter(frame, hide_below_min=True)
    assert list(hidden[EXACT_COMBO_KEY_COL]) == ["A"]
    shown = apply_sample_warning_filter(frame, hide_below_min=False)
    assert len(shown) == 2


def test_resolve_confluence_mode_prefers_setup_config_then_trades():
    assert (
        resolve_confluence_mode({"confluence_mode": "anchor_rules"}, pd.DataFrame())
        == "anchor_rules"
    )
    trades = pd.DataFrame({"level_source_mode": ["global_cluster", "global_cluster", "other"]})
    assert resolve_confluence_mode(None, trades) == "global_cluster"
    assert resolve_confluence_mode({"confluence_mode": "nope"}, None) == "unknown"


def test_resolve_signal_setup_prefers_signal_settings_over_stale_setup_config():
    """Stale Setup Builder config must not override the signal-run mode/anchor."""
    stale_setup = {"confluence_mode": "anchor_rules", "anchor_level": "pdHigh"}
    signal_settings = {"confluence_mode": "global_cluster", "anchor_level": None}
    resolved = resolve_signal_setup_for_attribution(
        signal_settings=signal_settings,
        setup_config=stale_setup,
    )
    assert resolved["confluence_mode"] == "global_cluster"
    assert "anchor_level" not in resolved
    assert (
        resolve_confluence_mode(resolved, pd.DataFrame({"level_source_mode": ["anchor_rules"]}))
        == "global_cluster"
    )

    # Reverse: signal-run is anchor; stale setup_config is global.
    resolved_anchor = resolve_signal_setup_for_attribution(
        signal_settings={"confluence_mode": "anchor_rules", "anchor_level": "pdHigh"},
        setup_config={"confluence_mode": "global_cluster", "anchor_level": "OR_High"},
    )
    assert resolved_anchor == {
        "confluence_mode": "anchor_rules",
        "anchor_level": "pdHigh",
    }

    # last_signal_setup wins over setup_config when signal_settings absent.
    from_last = resolve_signal_setup_for_attribution(
        last_signal_setup={"confluence_mode": "anchor_rules", "anchor_level": "pdPOC"},
        setup_config={"confluence_mode": "global_cluster"},
        signal_context={"confluence_mode": "global_cluster"},
    )
    assert from_last["confluence_mode"] == "anchor_rules"
    assert from_last["anchor_level"] == "pdPOC"

    # setup_snapshot can supply anchor when top-level signal_settings omits it.
    from_snap = resolve_signal_setup_for_attribution(
        signal_settings={
            "confluence_mode": "anchor_rules",
            "setup_snapshot": {"confluence_mode": "anchor_rules", "anchor_level": "pdHigh"},
        },
        setup_config={"confluence_mode": "global_cluster", "anchor_level": "OR_High"},
    )
    assert from_snap == {"confluence_mode": "anchor_rules", "anchor_level": "pdHigh"}


def test_prepare_exact_combo_display_uses_anchor_only_in_anchor_mode():
    frame = pd.DataFrame(
        {
            EXACT_COMBO_KEY_COL: ["VWAP|pdHigh", EMPTY_LEVEL_NAMES_KEY],
            "trade_count": [2, 1],
        }
    )
    anchored = prepare_exact_combo_display(
        frame,
        anchor_level="pdHigh",
        confluence_mode="anchor_rules",
    )
    assert list(anchored["display_combo"]) == ["pdHigh|VWAP", EMPTY_LEVEL_NAMES_LABEL]

    global_view = prepare_exact_combo_display(
        frame,
        anchor_level="pdHigh",
        confluence_mode="global_cluster",
    )
    assert list(global_view["display_combo"]) == ["VWAP|pdHigh", EMPTY_LEVEL_NAMES_LABEL]


# ---------------------------------------------------------------------------
# PR 4 soft pairwise attribution
# ---------------------------------------------------------------------------


def test_pair_keys_generic_and_anchor_partner():
    assert pair_keys_for_tokens(["B", "A"]) == ["A|B"]
    assert pair_keys_for_tokens(["A", "B", "C"]) == ["A|B", "A|C", "B|C"]
    assert pair_keys_for_tokens(["A"]) == []
    assert pair_keys_for_tokens([]) == []
    # Anchor present → partner keys only (anchor first, partners sorted).
    assert pair_keys_for_tokens(
        ["VWAP", "pdHigh", "pdPOC"],
        anchor_level="pdHigh",
    ) == ["pdHigh|VWAP", "pdHigh|pdPOC"]
    # Anchor absent → generic fallback; never invents anchor.
    assert pair_keys_for_tokens(["VWAP", "pdPOC"], anchor_level="pdHigh") == ["VWAP|pdPOC"]


def test_summarize_by_level_pairs_generic_double_count():
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0, -0.5],
            "level_names": ["A|B|C", "A|B"],
        }
    )
    pairs = summarize_by_level_pairs(trades, min_trades=1)
    by_pair = pairs.set_index(PAIR_KEY_COL)
    assert by_pair.loc["A|B", "trade_count"] == 2
    assert by_pair.loc["A|C", "trade_count"] == 1
    assert by_pair.loc["B|C", "trade_count"] == 1
    assert set(by_pair[PAIR_MODE_COL]) == {PAIR_MODE_GENERIC}
    # Double-count: pair total_r exceeds book total_r.
    book_total = float(trades["r_multiple"].sum())
    assert pairs["total_r"].sum() > book_total


def test_summarize_by_level_pairs_anchor_partner_mode():
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0, 0.5, -1.0],
            "level_names": [
                "pdHigh|VWAP|pdPOC",
                "VWAP|pdHigh",
                "VWAP|pdPOC",  # missing anchor → generic fallback for this trade
            ],
        }
    )
    pairs = summarize_by_level_pairs(
        trades,
        min_trades=1,
        anchor_level="pdHigh",
        confluence_mode="anchor_rules",
    )
    by_pair = pairs.set_index(PAIR_KEY_COL)
    assert by_pair.loc["pdHigh|VWAP", "trade_count"] == 2
    assert by_pair.loc["pdHigh|pdPOC", "trade_count"] == 1
    assert by_pair.loc["pdHigh|VWAP", PAIR_MODE_COL] == PAIR_MODE_ANCHOR_PARTNER
    # Trade without anchor contributes generic pair.
    assert by_pair.loc["VWAP|pdPOC", "trade_count"] == 1
    assert by_pair.loc["VWAP|pdPOC", PAIR_MODE_COL] == PAIR_MODE_GENERIC


def test_summarize_by_level_pairs_ignores_anchor_outside_anchor_mode():
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0],
            "level_names": ["pdHigh|VWAP"],
        }
    )
    pairs = summarize_by_level_pairs(
        trades,
        min_trades=1,
        anchor_level="pdHigh",
        confluence_mode="global_cluster",
    )
    assert list(pairs[PAIR_KEY_COL]) == ["VWAP|pdHigh"]
    assert list(pairs[PAIR_MODE_COL]) == [PAIR_MODE_GENERIC]


def test_summary_includes_pairs_with_anchor_mode():
    trades = _plan_fixture_trades()
    summary = confluence_attribution_summary(
        trades,
        min_trades=1,
        anchor_level="pdHigh",
        confluence_mode="anchor_rules",
    )
    assert summary["available"] is True
    assert summary["pair_mode"] == PAIR_MODE_ANCHOR_PARTNER
    assert not summary["by_pairs"].empty
    assert PAIRWISE_DOUBLE_COUNT_WARNING in summary["warnings"]
    assert "pdHigh|VWAP_rolling_1h" in set(summary["by_pairs"][PAIR_KEY_COL])


def test_pairs_empty_info_message_distinguishes_filter_vs_missing_pairs():
    """Hide-below-min must not be described as missing multi-level trades."""
    raw = pd.DataFrame(
        {
            PAIR_KEY_COL: ["A|B", "A|C"],
            "trade_count": [3, 2],
            "sample_warning": [True, True],
        }
    )
    filtered = apply_sample_warning_filter(raw, hide_below_min=True)
    assert filtered.empty
    assert pairs_empty_info_message(raw) == "No pair rows to display under the current filter."
    assert "two distinct level names" not in pairs_empty_info_message(raw)

    assert "two distinct level names" in pairs_empty_info_message(pd.DataFrame())
    assert "two distinct level names" in pairs_empty_info_message(None)


# ---------------------------------------------------------------------------
# PR 5a — Time Analysis opt-in combo / level-count group helpers
# ---------------------------------------------------------------------------


def test_level_count_bucket_label_view_c_unknown():
    assert level_count_bucket_label(0) == UNKNOWN_LEVEL_COUNT_LABEL
    assert level_count_bucket_label(1) == "1"
    assert level_count_bucket_label(3) == "3"
    assert level_count_bucket_label("2") == "2"
    assert level_count_bucket_label(None) == UNKNOWN_LEVEL_COUNT_LABEL


def test_attach_level_count_bucket_matches_view_c_labels():
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0, -0.5, 0.5],
            "level_names": ["A|B", "", "B|A|C"],
            "level_count": [9, 9, 9],
        }
    )
    attached = attach_level_count_bucket(trades)
    assert EXACT_COMBO_KEY_COL in attached.columns
    assert list(attached[LEVEL_COUNT_BUCKET_COL]) == ["2", UNKNOWN_LEVEL_COUNT_LABEL, "3"]
    # Parsed grain, not stored level_count.
    assert list(attached["level_token_count"]) == [2, 0, 3]


def test_confluence_combo_grouping_available_matches_summary_gate():
    nonempty = _plan_fixture_trades()
    assert confluence_combo_grouping_available(nonempty) is True
    assert confluence_attribution_summary(nonempty, min_trades=1)["available"] is True

    empty_only = pd.DataFrame(
        {"r_multiple": [1.0, -0.5], "level_names": ["", "nan"]}
    )
    assert confluence_combo_grouping_available(empty_only) is False
    assert confluence_attribution_summary(empty_only, min_trades=1)["available"] is False

    no_names = pd.DataFrame({"r_multiple": [1.0]})
    assert confluence_combo_grouping_available(no_names) is False

    null_r_only = pd.DataFrame(
        {"r_multiple": [np.nan], "level_names": ["A|B"]}
    )
    assert confluence_combo_grouping_available(null_r_only) is False


def test_append_confluence_time_analysis_group_options_append_only_when_available():
    base = ["entry_rth_segment", "entry_hour_bucket", "trigger"]
    cols = {
        "entry_rth_segment",
        "entry_hour_bucket",
        "trigger",
        EXACT_COMBO_KEY_COL,
        LEVEL_COUNT_BUCKET_COL,
        "pair_key",
        "level_name",
    }

    unavailable = append_confluence_time_analysis_group_options(
        base, available=False, columns=cols
    )
    assert unavailable == base

    available = append_confluence_time_analysis_group_options(
        base, available=True, columns=cols
    )
    assert available[:3] == base
    assert available[-2:] == list(COMBO_TIME_ANALYSIS_GROUP_COLS)
    # Pairs / membership must never become Time Analysis dims.
    assert "pair_key" not in available
    assert "level_name" not in available
    # Default primary remains first time bucket.
    assert available[0] == "entry_rth_segment"


def test_time_analysis_combo_group_caption_only_when_combo_dim_selected():
    trades = pd.DataFrame(
        {
            "r_multiple": [1.0],
            "level_names": ["A|B"],
            "trigger": ["3c"],
        }
    )
    assert time_analysis_combo_group_caption(trades, ["entry_rth_segment"]) is None
    caption = time_analysis_combo_group_caption(trades, [EXACT_COMBO_KEY_COL])
    assert caption is not None
    assert TIME_ANALYSIS_COMBO_DIAGNOSTIC_CAPTION in caption
    assert TRIGGER_3C_LEVEL_NAMES_WARNING in caption

    count_caption = time_analysis_combo_group_caption(
        trades.drop(columns=["trigger"]), LEVEL_COUNT_BUCKET_COL
    )
    assert count_caption == TIME_ANALYSIS_COMBO_DIAGNOSTIC_CAPTION


def test_combo_time_analysis_dims_are_not_focusable():
    for col in COMBO_TIME_ANALYSIS_GROUP_COLS:
        assert col not in FOCUSABLE_GROUP_COLS
