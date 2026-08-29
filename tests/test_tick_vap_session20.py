"""TV3 optional desk hook — plan §10.4.

Skips unless ``THESISTESTER_QT_TICK_FIXTURE`` points at the real
``b9bd9777`` session-20 Quantower tick-last export (≈91 MB). The tiny
filename stub under ``tests/fixtures/ticks/`` is not this file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from thesistester.levels.tick_vap import build_prior_profile_table_from_paths

_ENV = "THESISTESTER_QT_TICK_FIXTURE"
_MIN_BYTES = 1_000_000
_SESSION20_POC = 29366.75
_SESSION20_VAH = 29453.25
_SESSION20_VAL = 29266.75
_BAND = 5.0


def _fixture_path() -> Path | None:
    raw = os.environ.get(_ENV, "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        return None
    if "b9bd9777" not in path.name and "b9bd9777" not in str(path):
        return None
    if path.stat().st_size < _MIN_BYTES:
        return None
    return path


pytestmark = pytest.mark.skipif(
    _fixture_path() is None,
    reason=(
        f"{_ENV} is not the real b9bd9777 session-20 tick export "
        f"(must exist, contain b9bd9777, and be >{_MIN_BYTES} bytes)"
    ),
)


def test_session20_one_tick_vap_near_quantower_band():
    path = _fixture_path()
    assert path is not None
    table = build_prior_profile_table_from_paths(
        [path],
        instrument="MNQ",
        prior_day_aggregation_ticks=1,
        prior_week_aggregation_ticks=8,
        prior_month_aggregation_ticks=10,
    )
    pd_rows = table.family_rows("pd")
    assert not pd_rows.empty
    row = pd_rows.iloc[-1]
    assert row["VAH"] == pytest.approx(_SESSION20_VAH, abs=_BAND)
    assert row["VAL"] == pytest.approx(_SESSION20_VAL, abs=_BAND)
    assert row["POC"] == pytest.approx(_SESSION20_POC, abs=_BAND)


def test_session20_four_tick_stays_near_tick_vap_not_typical_mvp():
    path = _fixture_path()
    assert path is not None
    table = build_prior_profile_table_from_paths(
        [path],
        instrument="MNQ",
        prior_day_aggregation_ticks=4,
        prior_week_aggregation_ticks=8,
        prior_month_aggregation_ticks=10,
    )
    row = table.family_rows("pd").iloc[-1]
    assert row["VAH"] == pytest.approx(29455.0, abs=_BAND)
    assert row["VAL"] == pytest.approx(29264.0, abs=_BAND)
    assert row["POC"] == pytest.approx(29354.0, abs=_BAND)
    assert row["VAH"] != pytest.approx(29474.0, abs=1.0)
    assert row["VAL"] != pytest.approx(29275.0, abs=1.0)
