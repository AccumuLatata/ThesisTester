"""Research Study Runner — additive StudySpec tooling (RS series).

This package expands closed factorial studies into R18 experiments. It does not
alter engine, pages, or ``run_batch`` semantics.
"""

from __future__ import annotations

from thesistester.study.expand import (
    ExpansionResult,
    expand_study,
    expand_study_to_directory,
    study_identity_hash,
    write_expansion_artifacts,
)
from thesistester.study.naming import build_run_name, factor_cell_fingerprint
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
    "ExpansionResult",
    "RUN_NAME_RE",
    "STUDY_SCHEMA_VERSION",
    "StudySpecError",
    "build_run_name",
    "closed_level_token_set",
    "expand_study",
    "expand_study_to_directory",
    "factor_cell_fingerprint",
    "load_study_spec",
    "normalize_study_spec",
    "study_identity_hash",
    "validate_study_spec",
    "write_expansion_artifacts",
]
