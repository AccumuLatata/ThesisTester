"""F-10 / QI-14-02: CAI_BASELINE tables are the tick-gated ``--fixture both`` record.

QI-14-07 (dup): the small ``build_research_bundle`` row rides the same
re-record. Wall times are informational; this probe binds stage names,
the live realistic share order, and the CAI-10 no-second-cache decision.
Exact milliseconds are not a CI gate.
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

# Retired CAI-0 typical-price cells (QI-14-02). Must not remain in the live tables.
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


def test_recorded_tables_match_fixture_both_stages() -> None:
    text = CAI_BASELINE.read_text(encoding="utf-8")
    recorded = _recorded_baseline(text)
    small = _parse_stage_table(_heading_section(recorded, SMALL_HEADING))
    realistic = _parse_stage_table(_heading_section(recorded, REALISTIC_HEADING))
    assert [row["stage"] for row in small] == list(_EXPECTED_STAGES)
    assert [row["stage"] for row in realistic] == list(_EXPECTED_STAGES)
    assert any(row["stage"] == "build_research_bundle" for row in small)
    assert "--fixture both" in recorded
    assert "tick-gated" in recorded.lower()


def test_realistic_live_table_is_signal_dominated() -> None:
    """QI-14-02: live realistic share is generate_signals > compute_levels."""
    text = CAI_BASELINE.read_text(encoding="utf-8")
    recorded = _recorded_baseline(text)
    realistic = _parse_stage_table(_heading_section(recorded, REALISTIC_HEADING))
    shares = {row["stage"]: row["share"] for row in realistic}
    assert shares["generate_signals"] is not None
    assert shares["compute_levels"] is not None
    sig = float(shares["generate_signals"].rstrip("%"))
    lvl = float(shares["compute_levels"].rstrip("%"))
    assert sig > lvl, f"expected signal-dominated live table; got {sig=} {lvl=}"
    for stale in STALE_CAI0_CELLS:
        assert stale not in recorded, f"retired CAI-0 cell still in live tables: {stale}"


def test_cai10_keeps_no_second_signal_cache() -> None:
    text = CAI_BASELINE.read_text(encoding="utf-8")
    section = _heading_section(text, CAI10_HEADING)
    assert CAI10_DECISION in section
    assert "second signal" in section.lower()


def test_fixture_both_command_is_documented() -> None:
    text = CAI_BASELINE.read_text(encoding="utf-8")
    commands = _heading_section(text, "## Fixtures and commands")
    assert "python3 -m tests.benchmarks.cai_cold_path --fixture both --repeats 5" in commands
    assert "F-10 re-records them" not in text
