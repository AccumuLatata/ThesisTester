"""Research Study Runner — additive StudySpec tooling (RS series).

This package expands closed factorial studies into R18 experiments. It does not
alter engine, pages, or ``run_batch`` semantics.
"""

from __future__ import annotations

from thesistester.study.execute import (
    R18_INDEX_METRIC_KEYS,
    STUDY_INDEX_KEYS,
    cost_hint_lines,
    execute_study_cell,
    prepare_study_expansion,
    run_study,
)
from thesistester.study.expand import (
    ExpansionResult,
    expand_study,
    expand_study_to_directory,
    study_identity_hash,
    write_expansion_artifacts,
)
from thesistester.study.naming import build_run_name, factor_cell_fingerprint
from thesistester.study.promote import (
    StudyPromoteError,
    StudyPromoteResult,
    promote_study,
)
from thesistester.study.report import (
    StudyReportError,
    StudyReportResult,
    otf_canonical_key,
    report_study,
)
from thesistester.study.schema import (
    RUN_NAME_RE,
    STUDY_SCHEMA_VERSION,
    StudySpecError,
    closed_level_token_set,
    load_study_spec,
    normalize_study_spec,
    validate_study_spec,
)
from thesistester.study.tools import (
    APPROVAL_PAYLOAD_KEY,
    StudyToolsDisabledError,
    StudyToolsSettings,
    ensure_study_tools_enabled,
    load_study_tools_settings,
)
from thesistester.study.rollup import (
    StudyRollupError,
    StudyRollupResult,
    rollup_study,
)
from thesistester.study.preview import (
    StudyPreview,
    preview_study_spec,
    preview_study_yaml,
)
from thesistester.study.viewer import (
    StudyViewerError,
    StudyViewerModel,
    load_study_view,
)

__all__ = [
    "APPROVAL_PAYLOAD_KEY",
    "StudyRollupError",
    "StudyRollupResult",
    "StudyToolsDisabledError",
    "StudyToolsSettings",
    "StudyViewerError",
    "StudyViewerModel",
    "ExpansionResult",
    "R18_INDEX_METRIC_KEYS",
    "RUN_NAME_RE",
    "STUDY_INDEX_KEYS",
    "STUDY_SCHEMA_VERSION",
    "StudyPreview",
    "StudyPromoteError",
    "StudyPromoteResult",
    "StudyReportError",
    "StudyReportResult",
    "StudySpecError",
    "build_run_name",
    "closed_level_token_set",
    "cost_hint_lines",
    "ensure_study_tools_enabled",
    "execute_study_cell",
    "expand_study",
    "expand_study_to_directory",
    "factor_cell_fingerprint",
    "load_study_spec",
    "load_study_tools_settings",
    "load_study_view",
    "normalize_study_spec",
    "otf_canonical_key",
    "prepare_study_expansion",
    "preview_study_spec",
    "preview_study_yaml",
    "promote_study",
    "report_study",
    "rollup_study",
    "run_study",
    "study_identity_hash",
    "validate_study_spec",
    "write_expansion_artifacts",
]
