"""B-17 / QI-12-09: ruff ``B`` is the first widening family.

QI-12 §2.5: 44 hits at probe (19 B905 · 18 B009 · 4 B023). One family per
PR; never ``S`` on ``tests/``; never ``PLR2004`` first. Tests ignore noisy
``B`` codes; ``B023`` (C1 loop-variable) stays enforced.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

tomllib = importlib.import_module("tomllib" if sys.version_info >= (3, 11) else "tomli")

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SELECT = ["E4", "E7", "E9", "F", "W", "B"]
NOISY_TEST_B = ("B009", "B905", "B017", "B904")


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_ruff_select_is_r9_plus_b_only() -> None:
    select = _pyproject()["tool"]["ruff"]["lint"]["select"]
    assert select == REQUIRED_SELECT
    joined = ",".join(select)
    assert "S" not in select
    assert "PLR2004" not in joined
    assert "PL" not in select


def test_tests_ignore_noisy_b_but_keep_b023() -> None:
    ignores = _pyproject()["tool"]["ruff"]["lint"]["per-file-ignores"]["tests/**"]
    for code in NOISY_TEST_B:
        assert code in ignores, code
    assert "B023" not in ignores
    assert "S" not in ignores
    assert "S101" not in ignores
