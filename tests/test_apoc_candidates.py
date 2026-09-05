"""AP1 candidate-profile tests; these do not route production APOC."""

from __future__ import annotations

import inspect
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from thesistester.levels.apoc import _compute_a_period_poc, compute_apoc_levels
from thesistester.levels.apoc_candidates import (
    BAR_CANDIDATES,
    BAR_RANGE_TPO_V1,
    BAR_RANGE_UNIFORM_VOLUME_V1,
    TICK_LAST_VOLUME_V1,
    TYPICAL_MVP_V1,
    VOLUME_CONSERVATION_ATOL,
    VOLUME_CONSERVATION_RTOL,
    VOLUME_PROFILE_CANDIDATES,
    APOCProfileInputError,
    compare_apoc_candidates,
    compute_bar_candidate_profile,
    compute_tick_last_volume_profile,
    select_a_period_rows,
)


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["high", "low", "close", "volume"])


def _assert_volume_conserved(result) -> None:
    assert result.candidate in VOLUME_PROFILE_CANDIDATES
    assert result.allocated_volume == pytest.approx(
        result.source_volume,
        rel=VOLUME_CONSERVATION_RTOL,
        abs=VOLUME_CONSERVATION_ATOL,
    )


def test_typical_candidate_matches_production_apoc_helper_without_routing():
    bars = _bars(
        [
            (100.50, 99.50, 100.00, 100.0),
            (101.00, 100.50, 100.75, 200.0),
        ]
    )
    candidate = compute_bar_candidate_profile(bars, candidate=TYPICAL_MVP_V1, tick_size=0.25)

    assert candidate.poc == pytest.approx(100.75)
    assert candidate.poc == pytest.approx(_compute_a_period_poc(bars, tick_size=0.25))
    assert candidate.source_volume == pytest.approx(300.0)
    _assert_volume_conserved(candidate)


def test_typical_candidate_matches_production_when_typical_price_is_off_grid():
    # H+L+C = 300.50 → typical 100.1666... snaps to 100.25 under shared np.round bins.
    bars = _bars([(100.50, 100.00, 100.00, 8.0)])
    candidate = compute_bar_candidate_profile(bars, candidate=TYPICAL_MVP_V1, tick_size=0.25)

    assert candidate.poc == pytest.approx(100.25)
    assert candidate.poc == pytest.approx(_compute_a_period_poc(bars, tick_size=0.25))
    _assert_volume_conserved(candidate)


def test_uniform_range_allocation_is_inclusive_and_conserves_volume():
    bars = _bars([(100.50, 100.00, 100.25, 9.0)])
    result = compute_bar_candidate_profile(
        bars, candidate=BAR_RANGE_UNIFORM_VOLUME_V1, tick_size=0.25
    )

    assert result.histogram.to_dict() == {100.0: 3.0, 100.25: 3.0, 100.5: 3.0}
    assert result.source_volume == pytest.approx(9.0)
    _assert_volume_conserved(result)
    assert result.poc == pytest.approx(100.0)  # Lowest bin wins equal-volume ties.


def test_uniform_overlapping_ranges_conserve_volume_and_select_modal_bin():
    bars = _bars(
        [
            (100.25, 100.00, 100.00, 4.0),
            (100.50, 100.25, 100.25, 2.0),
        ]
    )
    result = compute_bar_candidate_profile(
        bars, candidate=BAR_RANGE_UNIFORM_VOLUME_V1, tick_size=0.25
    )

    assert result.histogram.to_dict() == {100.0: 2.0, 100.25: 3.0, 100.5: 1.0}
    _assert_volume_conserved(result)
    assert result.poc == pytest.approx(100.25)


def test_uniform_awkward_split_still_conserves_volume():
    bars = _bars([(100.50, 100.00, 100.25, 10.0)])  # 10 / 3 bins
    result = compute_bar_candidate_profile(
        bars, candidate=BAR_RANGE_UNIFORM_VOLUME_V1, tick_size=0.25
    )

    _assert_volume_conserved(result)
    assert result.poc == pytest.approx(100.0)


def test_tpo_range_allocation_ignores_bar_volume_and_counts_each_touched_tick():
    bars = _bars(
        [
            (100.50, 100.00, 100.25, 9.0),
            (100.25, 100.25, 100.25, 1_000.0),
        ]
    )
    result = compute_bar_candidate_profile(bars, candidate=BAR_RANGE_TPO_V1, tick_size=0.25)

    assert result.histogram.to_dict() == {100.0: 1.0, 100.25: 2.0, 100.5: 1.0}
    assert result.source_volume == pytest.approx(1_009.0)
    assert result.allocated_volume == pytest.approx(4.0)
    assert result.poc == pytest.approx(100.25)


def test_tpo_counts_zero_volume_bars_as_time():
    bars = _bars(
        [
            (100.50, 100.00, 100.25, 0.0),
            (100.25, 100.25, 100.25, 4.0),
        ]
    )
    tpo = compute_bar_candidate_profile(bars, candidate=BAR_RANGE_TPO_V1, tick_size=0.25)
    uniform = compute_bar_candidate_profile(
        bars, candidate=BAR_RANGE_UNIFORM_VOLUME_V1, tick_size=0.25
    )

    assert tpo.source_rows == 2
    assert tpo.histogram.to_dict() == {100.0: 1.0, 100.25: 2.0, 100.5: 1.0}
    assert tpo.poc == pytest.approx(100.25)
    assert uniform.source_rows == 1
    assert uniform.histogram.to_dict() == {100.25: 4.0}


def test_zero_range_bar_is_one_inclusive_bin_for_range_candidates():
    bars = _bars([(100.25, 100.25, 100.25, 7.0)])
    uniform = compute_bar_candidate_profile(
        bars, candidate=BAR_RANGE_UNIFORM_VOLUME_V1, tick_size=0.25
    )
    tpo = compute_bar_candidate_profile(bars, candidate=BAR_RANGE_TPO_V1, tick_size=0.25)

    assert uniform.histogram.to_dict() == {100.25: 7.0}
    assert tpo.histogram.to_dict() == {100.25: 1.0}


@pytest.mark.parametrize(
    ("bars", "message"),
    [
        (_bars([(100.50, 100.10, 100.25, 1.0)]), "bar low must lie on the 0.25 tick grid"),
        (_bars([(100.10, 100.00, 100.00, 1.0)]), "bar high must lie on the 0.25 tick grid"),
        (_bars([(100.50, 100.00, 100.10, 1.0)]), "bar close must lie on the 0.25 tick grid"),
        (_bars([(100.00, 100.50, 100.25, 1.0)]), "high below low"),
        (_bars([(100.50, 100.00, 101.00, 1.0)]), "close must be inside"),
        (_bars([(100.50, 100.00, 100.25, -1.0)]), "volume cannot be negative"),
        (_bars([(100.50, 100.00, 100.25, math.inf)]), "non-finite"),
        (_bars([(math.inf, 100.00, 100.00, 1.0)]), "non-finite"),
    ],
)
def test_bar_candidates_reject_invalid_profile_inputs(bars, message):
    with pytest.raises(APOCProfileInputError, match=message):
        compute_bar_candidate_profile(bars, candidate=BAR_RANGE_UNIFORM_VOLUME_V1, tick_size=0.25)


def test_bar_candidates_reject_boolean_tick_size():
    with pytest.raises(APOCProfileInputError, match="tick_size must be a finite positive"):
        compute_bar_candidate_profile(
            _bars([(100.25, 100.25, 100.25, 1.0)]),
            candidate=TYPICAL_MVP_V1,
            tick_size=True,
        )


def test_sparse_bars_are_eligible_and_zero_volume_bars_do_not_allocate_volume():
    bars = _bars(
        [
            (100.50, 100.00, 100.25, 0.0),
            (101.00, 100.50, 100.75, 4.0),
        ]
    )
    result = compute_bar_candidate_profile(
        bars, candidate=BAR_RANGE_UNIFORM_VOLUME_V1, tick_size=0.25
    )

    assert result.source_rows == 1
    assert result.source_volume == pytest.approx(4.0)
    _assert_volume_conserved(result)
    assert result.histogram.to_dict() == {
        100.5: pytest.approx(4.0 / 3.0),
        100.75: pytest.approx(4.0 / 3.0),
        101.0: pytest.approx(4.0 / 3.0),
    }


def test_empty_usable_volume_bars_return_nan_without_a_typical_fallback():
    result = compute_bar_candidate_profile(
        _bars([(100.25, 100.25, 100.25, 0.0)]),
        candidate=BAR_RANGE_UNIFORM_VOLUME_V1,
        tick_size=0.25,
    )

    assert math.isnan(result.poc)
    assert result.histogram.empty
    assert result.source_rows == 0


def test_tick_last_volume_conserves_volume_and_uses_lowest_bin_tie():
    ticks = pd.DataFrame({"price": [100.0, 100.25], "volume": [4.0, 4.0]})
    result = compute_tick_last_volume_profile(ticks, tick_size=0.25)

    assert result.candidate == TICK_LAST_VOLUME_V1
    assert result.histogram.to_dict() == {100.0: 4.0, 100.25: 4.0}
    assert result.source_volume == pytest.approx(8.0)
    _assert_volume_conserved(result)
    assert result.poc == pytest.approx(100.0)


def test_tick_candidate_rejects_off_grid_or_invalid_volume():
    with pytest.raises(APOCProfileInputError, match="tick price must lie"):
        compute_tick_last_volume_profile(
            pd.DataFrame({"price": [100.1], "volume": [1.0]}), tick_size=0.25
        )
    with pytest.raises(APOCProfileInputError, match="strictly positive"):
        compute_tick_last_volume_profile(
            pd.DataFrame({"price": [100.0], "volume": [0.0]}), tick_size=0.25
        )
    with pytest.raises(APOCProfileInputError, match="non-finite"):
        compute_tick_last_volume_profile(
            pd.DataFrame({"price": [100.0], "volume": [math.inf]}), tick_size=0.25
        )


def test_select_a_period_rows_uses_exchange_timezone_and_half_open_window():
    rows = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-09-04 13:29:59+00:00",
                    "2026-09-04 13:30:00+00:00",
                    "2026-09-04 13:59:59+00:00",
                    "2026-09-04 14:00:00+00:00",
                ]
            ),
            "volume": [1.0, 2.0, 3.0, 4.0],
        }
    )

    selected = select_a_period_rows(rows, session_date="2026-09-04", exchange_tz="America/New_York")

    assert selected["volume"].tolist() == [2.0, 3.0]
    assert selected["timestamp"].dt.tz_convert("America/New_York").dt.strftime(
        "%H:%M:%S"
    ).tolist() == [
        "09:30:00",
        "09:59:59",
    ]


def test_select_a_period_rows_keeps_sparse_observed_rows_without_imputing():
    rows = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-09-04 13:30:00+00:00", "2026-09-04 13:45:00+00:00"]
            ),
            "volume": [1.0, 2.0],
        }
    )

    selected = select_a_period_rows(rows, session_date="2026-09-04", exchange_tz="America/New_York")

    assert len(selected) == 2
    assert selected["volume"].tolist() == [1.0, 2.0]


def test_select_a_period_rows_rejects_naive_timestamps():
    with pytest.raises(APOCProfileInputError, match="timezone-aware"):
        select_a_period_rows(
            pd.DataFrame({"timestamp": pd.to_datetime(["2026-09-04 09:30:00"])}),
            session_date="2026-09-04",
            exchange_tz="America/New_York",
        )


def test_select_a_period_rows_is_stable_with_duplicate_index():
    rows = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-09-04 13:30:00+00:00", "2026-09-04 13:31:00+00:00"]
            ),
            "volume": [1.0, 2.0],
        },
        index=[7, 7],
    )

    selected = select_a_period_rows(rows, session_date="2026-09-04", exchange_tz="America/New_York")

    assert selected["volume"].tolist() == [1.0, 2.0]


def test_comparator_returns_all_bar_candidates_and_optional_tick_candidate():
    bars = _bars([(100.50, 100.00, 100.25, 3.0)])
    results = compare_apoc_candidates(
        bars,
        tick_size=0.25,
        a_period_ticks=pd.DataFrame({"price": [100.25], "volume": [5.0]}),
    )

    assert set(results) == {
        TYPICAL_MVP_V1,
        BAR_RANGE_UNIFORM_VOLUME_V1,
        BAR_RANGE_TPO_V1,
        TICK_LAST_VOLUME_V1,
    }
    assert results[TICK_LAST_VOLUME_V1].poc == pytest.approx(100.25)
    assert set(BAR_CANDIDATES).isdisjoint({TICK_LAST_VOLUME_V1})


def test_comparator_without_ticks_does_not_emit_tick_candidate():
    results = compare_apoc_candidates(_bars([(100.25, 100.25, 100.25, 1.0)]), tick_size=0.25)

    assert set(results) == set(BAR_CANDIDATES)
    assert TICK_LAST_VOLUME_V1 not in results


def test_production_apoc_module_does_not_import_harness():
    import thesistester.levels.all as all_levels
    import thesistester.levels.apoc as apoc

    assert "apoc_candidates" not in inspect.getsource(apoc)
    assert "apoc_candidates" not in inspect.getsource(all_levels)
    assert "apoc_candidates" not in apoc.__dict__
    assert "compute_bar_candidate_profile" not in apoc.__dict__


def test_disabled_production_apoc_remains_a_no_op():
    df = pd.DataFrame({"timestamp": pd.to_datetime(["2026-09-04 13:30:00+00:00"])})
    out = compute_apoc_levels(df, enabled=False)

    assert out.empty
    assert list(out.columns) == []


@pytest.mark.skipif(
    not os.environ.get("THESISTESTER_APOC_QT_BARS")
    or not os.environ.get("THESISTESTER_APOC_QT_EXPECTED"),
    reason="Set THESISTESTER_APOC_QT_BARS and THESISTESTER_APOC_QT_EXPECTED for desk oracle.",
)
def test_optional_desk_oracle_reports_named_candidate_error():
    """Run one externally supplied candidate comparison without committing desk data."""
    path = Path(os.environ["THESISTESTER_APOC_QT_BARS"])
    expected = float(os.environ["THESISTESTER_APOC_QT_EXPECTED"])
    candidate = os.environ.get("THESISTESTER_APOC_QT_CANDIDATE", BAR_RANGE_UNIFORM_VOLUME_V1)
    bars = pd.read_csv(path)
    result = compute_bar_candidate_profile(bars, candidate=candidate, tick_size=0.25)
    if result.candidate in VOLUME_PROFILE_CANDIDATES:
        _assert_volume_conserved(result)
    error_ticks = (result.poc - expected) / 0.25
    assert np.isfinite(error_ticks), f"{candidate} produced no POC for {path}"
    assert abs(error_ticks) <= 1.0, (
        f"{candidate}: POC={result.poc:.2f}, expected={expected:.2f}, error_ticks={error_ticks:.2f}"
    )
