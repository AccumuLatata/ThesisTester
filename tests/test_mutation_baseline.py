"""B-4 / QI-11-04: committed mutation recipe + gate."""

from __future__ import annotations

import json
from pathlib import Path

from tests.fixtures.mutation.mutate_sample import BASELINE_PATH, TARGETS


def test_walk_forward_sample_keeps_otf_integration() -> None:
    walk_tests = TARGETS["thesistester/analytics/walk_forward.py"]["tests"]
    assert "tests/test_walk_forward.py" in walk_tests
    assert "tests/test_otf_integration.py" in walk_tests
    backtest_tests = TARGETS["thesistester/engine/backtest.py"]["tests"]
    assert "tests/test_phase5_backtest.py" in backtest_tests


def test_committed_mutation_baseline_meets_c14_gate() -> None:
    baseline = json.loads(Path(BASELINE_PATH).read_text(encoding="utf-8"))
    assert baseline["gate"]["minimum_pct"] == 70.0
    assert baseline["gate"]["backtest_adjusted_pct"] >= 70.0
    assert baseline["gate"]["walk_forward_adjusted_pct"] >= 70.0
    walk = baseline["modules"]["thesistester/analytics/walk_forward.py"]
    assert "tests/test_otf_integration.py" in walk["tests"]
