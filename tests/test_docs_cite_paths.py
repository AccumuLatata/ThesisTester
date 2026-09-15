"""F-9 / QI-13-06: AGENT_GUIDE + ARCHITECTURE path cites only (no file:line).

QI-13-06 rotting ``file:line`` anchors (``app.py:10-33``,
``validation.py:13``, …) drift across edits. ARCHITECTURE already forbids
line anchors on the session-key contract. Clock times (``09:30:00``,
``eth_start=18:00``) are not cites and must not match.

QI-09-05: AIA-0 must name the lazy ``st.secrets`` fallback (C-8 did not
extract a Streamlit-free secrets reader).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
AGENT_GUIDE = DOCS / "AGENT_GUIDE.md"
ARCHITECTURE = DOCS / "ARCHITECTURE.md"

# Path + line (optional range). Does not match clock times or ``eth_start=18:00``.
FILE_LINE = re.compile(r"[A-Za-z0-9_./-]+\.(?:py|md):\d+(?:-\d+)?")

CITED_DOCS = (AGENT_GUIDE, ARCHITECTURE)


@pytest.mark.parametrize("path", CITED_DOCS, ids=lambda p: p.name)
def test_agent_guide_and_architecture_have_zero_file_line_cites(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    hits = FILE_LINE.findall(text)
    assert hits == [], f"{path.name} still has file:line cites: {hits}"


def test_clock_strings_are_not_file_line_cites() -> None:
    """Negative control: session-clock prose must not trip the cite regex."""
    sample = (
        "RTH 09:30:00–16:00:00; ETH eth_start=18:00; see `app.py` and "
        "`docs/ARCHITECTURE.md` (path only)."
    )
    assert FILE_LINE.findall(sample) == []


def test_aia0_names_lazy_st_secrets_fallback() -> None:
    """Bind QI-09-05 to the AIA-0 opening paragraph, not a later H2 body."""
    text = ARCHITECTURE.read_text(encoding="utf-8")
    heading = "## AI Research Assistant contract boundary (AIA-0)"
    start = text.find(heading)
    assert start >= 0, "AIA-0 heading missing from ARCHITECTURE.md"
    rest = text[start + len(heading) :].lstrip("\n")
    first_para = rest.split("\n\n", 1)[0]
    lowered = first_para.lower()
    assert "st.secrets" in first_para, "AIA-0 opening paragraph must name st.secrets"
    assert "lazy" in lowered, "AIA-0 opening paragraph must say the import is lazy"
    assert "declared public" in lowered and "headless symbols" in lowered
    assert "does not execute research, import streamlit" not in lowered
