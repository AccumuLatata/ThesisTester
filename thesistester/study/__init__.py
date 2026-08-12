"""Research Study Runner — additive StudySpec tooling (RS series).

This package expands closed factorial studies into R18 experiments. It does not
alter engine, pages, or ``run_batch`` semantics.
"""

from __future__ import annotations

from thesistester.study.schema import (
    RUN_NAME_RE,
    STUDY_SCHEMA_VERSION,
    StudySpecError,
    closed_level_token_set,
    load_study_spec,
    normalize_study_spec,
    validate_study_spec,
)

__all__ = [
    "RUN_NAME_RE",
    "STUDY_SCHEMA_VERSION",
    "StudySpecError",
    "closed_level_token_set",
    "load_study_spec",
    "normalize_study_spec",
    "validate_study_spec",
]
