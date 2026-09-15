"""F-9 / QI-13-06: AGENT_GUIDE + ARCHITECTURE path cites only (no file:line).

QI-13-06 rotting ``file:line`` anchors (``app.py:10-33``,
``validation.py:13``, …) drift across edits. ARCHITECTURE already forbids
line anchors on the session-key contract. Clock times (``09:30:00``,
``eth_start=18:00``) are not cites and must not match.

QI-09-05: AIA-0 must name the lazy ``st.secrets`` fallback (C-8 did not
extract a Streamlit-free secrets reader). Positive claims bind to the
opening paragraph. The stale Streamlit-free sentence is banned from the
whole AIA-0 H2 (a later paragraph must not false-green the probe).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
AGENT_GUIDE = DOCS / "AGENT_GUIDE.md"
ARCHITECTURE = DOCS / "ARCHITECTURE.md"

AIA0_HEADING = "## AI Research Assistant contract boundary (AIA-0)"
STALE_AIA0_STREAMLIT_FREE = "does not execute research, import streamlit"

# Path + line (optional range). Covers the QI-13-06 .py/.md cites plus other
# living-doc extensions used as path cites. Does not match clock times or
# ``eth_start=18:00``.
FILE_LINE = re.compile(r"[A-Za-z0-9_./-]+\.(?:py|md|yml|yaml|toml|txt|json|ini):\d+(?:-\d+)?")

CITED_DOCS = (AGENT_GUIDE, ARCHITECTURE)

# QI-13 §2 unique AGENT_GUIDE cites (plus the path-qualified forms that
# actually appeared in Repository conventions).
QI13_FILE_LINE_CITES = (
    "README.md:7-10",
    "README.md:12-16",
    "app.py:10-33",
    "validation.py:13",
    "thesistester/analytics/validation.py:13",
    "pages/10_Validation.py:18",
    "thesistester/reporting.py:13-19",
    "thesistester/engine/backtest.py:12-14",
)


def _file_line_cites(text: str) -> list[str]:
    return FILE_LINE.findall(text)


def _aia0_heading_index(text: str) -> int:
    if text.startswith(AIA0_HEADING):
        return 0
    idx = text.find("\n" + AIA0_HEADING)
    if idx < 0:
        raise AssertionError("AIA-0 heading missing from ARCHITECTURE.md")
    return idx + 1


def _aia0_section(text: str) -> str:
    start = _aia0_heading_index(text)
    rest = text[start + len(AIA0_HEADING) :]
    next_h2 = rest.find("\n## ")
    return rest if next_h2 < 0 else rest[:next_h2]


def _aia0_opening_paragraph(text: str) -> str:
    return _aia0_section(text).lstrip("\n").split("\n\n", 1)[0]


def _assert_aia0_opening_names_fallback(text: str) -> None:
    first_para = _aia0_opening_paragraph(text)
    lowered_para = first_para.lower()
    lowered_section = _aia0_section(text).lower()
    assert "st.secrets" in first_para, "AIA-0 opening paragraph must name st.secrets"
    assert "lazy" in lowered_para, "AIA-0 opening paragraph must say the import is lazy"
    assert "declared public" in lowered_para and "headless symbols" in lowered_para
    assert STALE_AIA0_STREAMLIT_FREE not in lowered_section, (
        "AIA-0 H2 must not keep the stale Streamlit-free sentence"
    )


@pytest.mark.parametrize("path", CITED_DOCS, ids=lambda p: p.name)
def test_agent_guide_and_architecture_have_zero_file_line_cites(path: Path) -> None:
    hits = _file_line_cites(path.read_text(encoding="utf-8"))
    assert hits == [], f"{path.name} still has file:line cites: {hits}"


def test_clock_strings_are_not_file_line_cites() -> None:
    """Negative control: session-clock prose must not trip the cite regex."""
    sample = (
        "RTH 09:30:00–16:00:00; ETH eth_start=18:00; see `app.py` and "
        "`docs/ARCHITECTURE.md` (path only)."
    )
    assert _file_line_cites(sample) == []


@pytest.mark.parametrize("cite", QI13_FILE_LINE_CITES)
def test_file_line_regex_matches_qi13_historical_cites(cite: str) -> None:
    """Positive control: a broken regex must not zero-hit its way to green."""
    hits = _file_line_cites(f"see `{cite}` in the ledger.")
    assert cite in hits, f"{cite!r} must match FILE_LINE; got {hits}"


def test_file_line_regex_matches_other_living_doc_extensions() -> None:
    sample = "CI in `.github/workflows/ci.yml:12`; ranges in `pyproject.toml:8`."
    assert _file_line_cites(sample) == [
        ".github/workflows/ci.yml:12",
        "pyproject.toml:8",
    ]


def test_aia0_names_lazy_st_secrets_fallback() -> None:
    """Bind QI-09-05 to the AIA-0 opening paragraph, not a later H2 body."""
    _assert_aia0_opening_names_fallback(ARCHITECTURE.read_text(encoding="utf-8"))


def test_aia0_later_h2_st_secrets_does_not_bind_opening() -> None:
    """Later-H2 st.secrets / lazy must not satisfy the opening-paragraph probe."""
    fake = (
        f"{AIA0_HEADING}\n\n"
        "Presentation-only metadata boundary.\n\n"
        "## Later heading\n\n"
        "The only Streamlit use is a lazy `st.secrets` fallback; "
        "dispatch uses declared public headless symbols.\n"
    )
    try:
        _assert_aia0_opening_names_fallback(fake)
    except AssertionError:
        return
    raise AssertionError("later-H2 st.secrets must not bind the AIA-0 opening paragraph")


def test_aia0_later_paragraph_st_secrets_does_not_bind_opening() -> None:
    """Same-H2 later paragraph must not satisfy the opening-paragraph probe."""
    fake = (
        f"{AIA0_HEADING}\n\n"
        "Shipped assistant boundary.\n\n"
        "The only Streamlit use is a lazy `st.secrets` fallback; "
        "dispatch uses declared public headless symbols.\n"
    )
    try:
        _assert_aia0_opening_names_fallback(fake)
    except AssertionError:
        return
    raise AssertionError("later AIA-0 paragraph st.secrets must not bind the opening paragraph")


def test_aia0_stale_streamlit_free_sentence_in_later_paragraph_fails() -> None:
    """Commit-2 narrowing must not let a later AIA-0 paragraph keep the stale claim."""
    fake = (
        f"{AIA0_HEADING}\n\n"
        "lazy `st.secrets` fallback; declared public headless symbols.\n\n"
        "It does not execute research, import Streamlit, or alter engine "
        "behavior.\n"
    )
    try:
        _assert_aia0_opening_names_fallback(fake)
    except AssertionError:
        return
    raise AssertionError("stale Streamlit-free sentence in a later AIA-0 paragraph must fail")
