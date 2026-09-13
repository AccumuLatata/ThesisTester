"""B-4 / QI-11-04: committed mutation recipe + gate."""

from __future__ import annotations

import json
from pathlib import Path

from tests.fixtures.mutation.mutate_sample import (
    BASELINE_PATH,
    REPO_ROOT,
    TARGETS,
    _collect_sites,
)

_PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_walk_forward_sample_keeps_otf_integration() -> None:
    walk_tests = TARGETS["thesistester/analytics/walk_forward.py"]["tests"]
    assert "tests/test_walk_forward.py" in walk_tests
    assert "tests/test_otf_integration.py" in walk_tests
    backtest_tests = TARGETS["thesistester/engine/backtest.py"]["tests"]
    assert backtest_tests == [
        "tests/test_phase5_backtest.py",
        "tests/test_ah1_session_flatten.py",
        "tests/test_golden_master.py",
    ]


def test_recipe_sample_includes_named_b4_surfaces() -> None:
    """Priority needles stay inside the 12-site sample (fail closed if dropped)."""
    for relpath, spec in TARGETS.items():
        source = (REPO_ROOT / relpath).read_text(encoding="utf-8")
        sites = _collect_sites(
            source,
            priority_needles=tuple(spec["priority_needles"]),
            function_names=tuple(spec["function_names"]),
        )
        assert len(sites) == 12
        sampled = "\n".join(site.line for site in sites)
        for needle in spec["priority_needles"]:
            assert needle in sampled


def test_committed_mutation_baseline_meets_c14_gate() -> None:
    baseline = json.loads(Path(BASELINE_PATH).read_text(encoding="utf-8"))
    assert baseline["gate"]["minimum_pct"] == 70.0
    assert baseline["gate"]["target_pct"] == 80.0
    assert "[tool.mutmut]" not in _PYPROJECT.read_text(encoding="utf-8")
    for relpath, spec in TARGETS.items():
        module = baseline["modules"][relpath]
        assert module["tests"] == spec["tests"]
        scored = int(module["sites_scored"])
        killed = int(module["killed"])
        survived = int(module["survived"])
        assert scored == 12
        assert killed + survived == scored
        expected = round(killed / scored * 100.0, 1)
        assert module["adjusted_pct"] == expected
        assert (
            baseline["gate"][
                (
                    "backtest_adjusted_pct"
                    if relpath.endswith("backtest.py")
                    else "walk_forward_adjusted_pct"
                )
            ]
            == module["adjusted_pct"]
        )
        assert module["adjusted_pct"] >= 70.0
    assert baseline["gate"]["backtest_adjusted_pct"] >= 70.0
    assert baseline["gate"]["walk_forward_adjusted_pct"] >= 70.0
    walk = baseline["modules"]["thesistester/analytics/walk_forward.py"]
    assert "tests/test_otf_integration.py" in walk["tests"]
