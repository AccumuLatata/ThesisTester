from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from thesistester.visualization import build_levels_chart


def _levels_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"timestamp": pd.Timestamp("2026-01-02 09:30:00"), "close": 100.0, "L1": 99.5, "L2": 101.0},
            {"timestamp": pd.Timestamp("2026-01-02 09:31:00"), "close": 100.5, "L1": 100.0, "L2": 101.5},
        ]
    )


def test_levels_chart_adds_close_and_selected_level_traces():
    fig = build_levels_chart(_levels_df(), ["L1", "L2"])

    assert [trace.name for trace in fig.data] == ["close", "L1", "L2"]


def test_levels_chart_ignores_missing_selected_levels():
    fig = build_levels_chart(_levels_df(), ["L1", "MISSING"])

    assert [trace.name for trace in fig.data] == ["close", "L1"]


def test_levels_chart_does_not_mutate_input_dataframe():
    levels_df = _levels_df().assign(timestamp=lambda df: df["timestamp"].astype(str))
    before = levels_df.copy(deep=True)

    build_levels_chart(levels_df, ["L1"])

    assert_frame_equal(levels_df, before)
