"""F-10 / QI-14-02: CAI_BASELINE tables are the tick-gated ``--fixture both`` record.

QI-14-07 (dup): the small ``build_research_bundle`` row rides the same
re-record. Wall times are informational; this probe binds stage names,
the live realistic share order, and the CAI-10 no-second-cache decision.
Exact milliseconds are not a CI gate.

Positive claims bind to the live recorded H3s / CAI-10 H2. A later H2
(C-15 footnote, Interpretation) must not false-green the probe. Shares
must be ``stage_median / e2e_median`` (1 decimal), not a free-typed order.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.benchmarks.test_cai_cold_path import _EXPECTED_STAGES

REPO_ROOT = Path(__file__).resolve().parents[1]
CAI_BASELINE = REPO_ROOT / "docs" / "CAI_BASELINE.md"

RECORDED_HEADING = "## Recorded baseline"
SMALL_HEADING = "### Small fixture (60 bars, no rolling POC)"
REALISTIC_HEADING = "### Realistic fixture (780 bars; tick-gated `poc_windows=[]`)"
CAI10_HEADING = "## CAI-10 warm-path measurement and signal-cache decision"
CAI10_DECISION = "do **not** add a second signal-artifact cache layer yet"
FIXTURE_BOTH_CMD = (
    "python3 -m tests.benchmarks.cai_cold_path --fixture both --repeats 5"
)
STALE_F10_FUTURE = "F-10 re-records them"
E2E_STAGE = "run_experiment_end_to_end"

# Retired CAI-0 typical-price cells (QI-14-02 / QI-14-07). Must not remain
# in the live recorded section.
STALE_CAI0_CELLS = (
    "1293.267",
    "70.9%",
    "1824.623",
    "17.006",
)

_ROW = re.compile(
    r"^\|\s*`(?P<stage>[a-z_]+)`\s*\|\s*(?P<median>[0-9.]+)\s*\|\s*(?P<p95>[0-9.]+)"
    r"(?:\s*\|\s*(?P<share>[0-9.]+%))?\s*\|?\s*$",
    re.MULTILINE,
)

_SAMPLE_SMALL = """\
| Stage | Median ms | P95 ms |
|---|---:|---:|
| `load_dataset` | 7.124 | 7.580 |
| `compute_levels` | 108.453 | 108.673 |
| `generate_signals` | 25.848 | 25.888 |
| `run_backtest` | 18.720 | 19.017 |
| `build_research_bundle` | 56.811 | 56.959 |
| `run_experiment_end_to_end` | 167.811 | 167.834 |
"""

_SAMPLE_REALISTIC = """\
| Stage | Median ms | P95 ms | Share of e2e median |
|---|---:|---:|
| `load_dataset` | 12.768 | 12.802 | 1.7% |
| `compute_levels` | 196.582 | 197.351 | 26.1% |
| `generate_signals` | 344.582 | 362.596 | 45.7% |
| `run_backtest` | 167.712 | 184.815 | 22.3% |
| `build_research_bundle` | 75.566 | 76.358 | 10.0% |
| `run_experiment_end_to_end` | 753.330 | 757.082 | 100% |
"""


def _heading_section(text: str, heading: str) -> str:
    if text.startswith(heading):
        start = 0
    else:
        idx = text.find("\n" + heading)
        if idx < 0:
            raise AssertionError(f"missing heading: {heading}")
        start = idx + 1
    rest = text[start + len(heading) :]
    # H2 stops at the next H2 only (keep ### children). H3 stops at any ##/###.
    nxt = re.search(r"\n##" if heading.startswith("###") else r"\n## ", rest)
    return rest if nxt is None else rest[: nxt.start()]


def _parse_stage_table(section: str) -> list[dict[str, str]]:
    rows = [m.groupdict() for m in _ROW.finditer(section)]
    if not rows:
        raise AssertionError(f"no stage rows in section:\n{section[:200]}")
    return rows


def _recorded_baseline(text: str) -> str:
    return _heading_section(text, RECORDED_HEADING)


def _share_pct(row: dict[str, str]) -> float:
    share = row["share"]
    assert share is not None, f"{row['stage']} missing share of e2e median"
    return float(share.rstrip("%"))


def _assert_six_stages(rows: list[dict[str, str]]) -> None:
    assert [row["stage"] for row in rows] == list(_EXPECTED_STAGES)
    for row in rows:
        median = float(row["median"])
        p95 = float(row["p95"])
        assert median >= 0, f"{row['stage']} median {median}"
        assert p95 >= median, f"{row['stage']} p95 {p95} < median {median}"


def _assert_realistic_signal_dominated(rows: list[dict[str, str]]) -> None:
    """QI-14-02: live share order is generate_signals > compute_levels.

    Shares must be ``round(100 * stage_median / e2e_median, 1)``. A
    free-typed signal-dominated share column must not false-green.
    """
    _assert_six_stages(rows)
    by_stage = {row["stage"]: row for row in rows}
    e2e = float(by_stage[E2E_STAGE]["median"])
    assert e2e > 0
    assert _share_pct(by_stage[E2E_STAGE]) == 100.0
    for row in rows:
        if row["stage"] == E2E_STAGE:
            continue
        expected = round(100.0 * float(row["median"]) / e2e, 1)
        got = _share_pct(row)
        assert got == expected, (
            f"{row['stage']}: share {got} != {expected} from median/e2e"
        )
    sig = _share_pct(by_stage["generate_signals"])
    lvl = _share_pct(by_stage["compute_levels"])
    assert sig > lvl, f"expected signal-dominated live table; got {sig=} {lvl=}"


def _assert_live_recorded_tables(text: str) -> None:
    recorded = _recorded_baseline(text)
    small = _parse_stage_table(_heading_section(recorded, SMALL_HEADING))
    realistic = _parse_stage_table(_heading_section(recorded, REALISTIC_HEADING))
    _assert_six_stages(small)
    _assert_realistic_signal_dominated(realistic)
    assert any(row["stage"] == "build_research_bundle" for row in small)
    assert "--fixture both" in recorded
    assert "tick-gated" in recorded.lower()
    for stale in STALE_CAI0_CELLS:
        assert stale not in recorded, f"retired CAI-0 cell still in live tables: {stale}"
    assert STALE_F10_FUTURE not in text


def _assert_cai10_decision(text: str) -> None:
    section = _heading_section(text, CAI10_HEADING)
    assert CAI10_DECISION in section
    assert "second signal" in section.lower()


def _doc(
    *,
    realistic_table: str = _SAMPLE_REALISTIC,
    cai10_body: str = CAI10_DECISION + ".\nsecond signal cache stays deferred.\n",
    extra_after_recorded: str = "",
) -> str:
    return (
        "# CAI-0 Cold-Path Baseline\n\n"
        "## Fixtures and commands\n\n"
        f"```bash\n{FIXTURE_BOTH_CMD}\n```\n\n"
        f"{RECORDED_HEADING}\n\n"
        "Command: `--fixture both`. tick-gated snapshot.\n\n"
        f"{SMALL_HEADING}\n\n"
        f"{_SAMPLE_SMALL}\n"
        f"{REALISTIC_HEADING}\n\n"
        f"{realistic_table}\n"
        f"{extra_after_recorded}"
        f"{CAI10_HEADING}\n\n"
        f"{cai10_body}"
    )


def test_recorded_tables_match_fixture_both_stages() -> None:
    text = CAI_BASELINE.read_text(encoding="utf-8")
    recorded = _recorded_baseline(text)
    small = _parse_stage_table(_heading_section(recorded, SMALL_HEADING))
    realistic = _parse_stage_table(_heading_section(recorded, REALISTIC_HEADING))
    _assert_six_stages(small)
    _assert_six_stages(realistic)
    assert any(row["stage"] == "build_research_bundle" for row in small)
    assert "--fixture both" in recorded
    assert "tick-gated" in recorded.lower()


def test_realistic_live_table_is_signal_dominated() -> None:
    """QI-14-02: live realistic share is generate_signals > compute_levels."""
    _assert_live_recorded_tables(CAI_BASELINE.read_text(encoding="utf-8"))


def test_cai10_keeps_no_second_signal_cache() -> None:
    _assert_cai10_decision(CAI_BASELINE.read_text(encoding="utf-8"))


def test_fixture_both_command_is_documented() -> None:
    text = CAI_BASELINE.read_text(encoding="utf-8")
    commands = _heading_section(text, "## Fixtures and commands")
    assert FIXTURE_BOTH_CMD in commands
    assert STALE_F10_FUTURE not in text


def test_row_regex_parses_fixture_both_sample() -> None:
    """Positive control: a broken ``_ROW`` must not zero-hit its way to green."""
    small = _parse_stage_table(_SAMPLE_SMALL)
    realistic = _parse_stage_table(_SAMPLE_REALISTIC)
    _assert_six_stages(small)
    _assert_realistic_signal_dominated(realistic)
    bundle = next(row for row in small if row["stage"] == "build_research_bundle")
    assert bundle["median"] != "17.006"


def test_c15_footnote_table_does_not_bind_live_realistic() -> None:
    """C-15 two-column footnote must not satisfy the live share-order probe."""
    c15 = (
        "| Stage | Before | After |\n"
        "|---|---:|---:|\n"
        "| `generate_signals` | 331.765 | 352.338 |\n"
        "| `run_experiment_end_to_end` | 756.672 | 748.973 |\n"
    )
    fake = _doc(
        realistic_table=c15,
        extra_after_recorded=("## C-15 `iterrows` replacement (QI-14-05)\n\n" + c15),
    )
    try:
        _assert_live_recorded_tables(fake)
    except AssertionError:
        return
    raise AssertionError("C-15 footnote table must not bind the live realistic probe")


def test_later_h2_signal_share_does_not_bind_live_table() -> None:
    """Interpretation / later H2 signal-dominated shares must not bind."""
    levels_dominated = """\
| Stage | Median ms | P95 ms | Share of e2e median |
|---|---:|---:|
| `load_dataset` | 12.768 | 12.802 | 1.7% |
| `compute_levels` | 500.000 | 500.000 | 66.4% |
| `generate_signals` | 100.000 | 100.000 | 13.3% |
| `run_backtest` | 167.712 | 184.815 | 22.3% |
| `build_research_bundle` | 75.566 | 76.358 | 10.0% |
| `run_experiment_end_to_end` | 753.330 | 757.082 | 100% |
"""
    fake = _doc(
        realistic_table=levels_dominated,
        extra_after_recorded=(
            "## Interpretation for later milestones\n\n" + _SAMPLE_REALISTIC
        ),
    )
    try:
        _assert_live_recorded_tables(fake)
    except AssertionError:
        return
    raise AssertionError("later-H2 signal-dominated shares must not bind the live table")


def test_inconsistent_share_column_fails() -> None:
    """Free-typed signal-dominated shares must not ignore median/e2e identity."""
    inconsistent = """\
| Stage | Median ms | P95 ms | Share of e2e median |
|---|---:|---:|
| `load_dataset` | 12.768 | 12.802 | 1.7% |
| `compute_levels` | 500.000 | 500.000 | 26.1% |
| `generate_signals` | 100.000 | 100.000 | 45.7% |
| `run_backtest` | 167.712 | 184.815 | 22.3% |
| `build_research_bundle` | 75.566 | 76.358 | 10.0% |
| `run_experiment_end_to_end` | 753.330 | 757.082 | 100% |
"""
    fake = _doc(realistic_table=inconsistent)
    try:
        _assert_live_recorded_tables(fake)
    except AssertionError:
        return
    raise AssertionError("share column must match stage_median / e2e_median")


def test_stale_cai0_cell_in_recorded_fails() -> None:
    """Retired typical-price cells in the live recorded section must fail."""
    fake = _doc().replace("tick-gated snapshot.", "tick-gated snapshot. 1293.267")
    try:
        _assert_live_recorded_tables(fake)
    except AssertionError:
        return
    raise AssertionError("retired CAI-0 cell in the live recorded section must fail")


def test_cai10_later_h2_decision_does_not_bind() -> None:
    """CAI-10 decision in a later H2 must not satisfy the CAI-10 probe."""
    fake = _doc(
        cai10_body="Warm-path harness is informational.\n",
        extra_after_recorded="",
    )
    fake += "\n## Later heading\n\n" + CAI10_DECISION + "\nsecond signal\n"
    try:
        _assert_cai10_decision(fake)
    except AssertionError:
        return
    raise AssertionError("later-H2 CAI-10 decision must not bind the CAI-10 H2")
