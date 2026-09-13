"""Direct tests for ``levels/common.py`` (QI-11-01 / B-7).

QI-11 §2.3: zero prior mentions of ``require_tz_aware_timestamp`` /
``normalized_window_label``. Missed: missing-``timestamp`` raise and the
entire ``Timedelta`` label branch.
"""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.levels.common import normalized_window_label, require_tz_aware_timestamp


def test_require_tz_aware_timestamp_rejects_missing_column():
    frame = pd.DataFrame({"close": [1.0]})
    with pytest.raises(ValueError, match="timestamp"):
        require_tz_aware_timestamp(frame)


def test_require_tz_aware_timestamp_rejects_naive_timestamp():
    frame = pd.DataFrame({"timestamp": pd.to_datetime(["2026-05-14 09:30:00"])})
    with pytest.raises(ValueError, match="timezone-aware"):
        require_tz_aware_timestamp(frame)


def test_require_tz_aware_timestamp_accepts_aware_timestamp():
    frame = pd.DataFrame({"timestamp": pd.to_datetime(["2026-05-14 09:30:00"], utc=True)})
    require_tz_aware_timestamp(frame)


@pytest.mark.parametrize(
    ("window", "expected"),
    [
        (" 2 H ", "2h"),
        ("30 min", "30min"),
        (pd.Timedelta(hours=2), "2h"),
        (pd.Timedelta(hours=1), "1h"),
        (pd.Timedelta(minutes=30), "30min"),
        (pd.Timedelta(minutes=90), "90min"),
    ],
)
def test_normalized_window_label_string_and_timedelta(window, expected):
    assert normalized_window_label(window) == expected
