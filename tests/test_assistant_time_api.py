import pandas as pd

from thesistester.api import run_time_analysis


def test_time_analysis_facade_returns_grouped_summary():
    trades = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(["2026-01-05 10:00", "2026-01-05 10:30"]),
            "r_multiple": [1.0, -1.0],
        }
    )
    result = run_time_analysis(trades)
    assert result["trade_count"].sum() == 2
