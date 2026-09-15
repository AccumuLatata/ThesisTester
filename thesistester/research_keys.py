"""Research-key registry (QR D-1 / QI-10-03).

One table of session keys with dataset-clear / apply-clear / thesis-clear /
widget flags. Generated tuples are the pop lists consumed by Data-page
dataset switch, bundle apply, and thesis-scoped staging.

Additive-only: do not drop a key a page still reads. Managed (apply-clear)
keys that must survive dataset switch are listed on ``_STICKY_APPLY_SOURCE``
(identity + A-7 residuals and other apply-only members). Sticky is never
derived from “apply and not dataset-clear” — an unlabeled apply-clear key
fails closed at import. Execution-clear stays local on the Data page
(D-1 does not own that list). D-2 (QI-03-12) adds
``SETUP_MUTATION_SIGNAL_KEYS`` / ``pop_setup_mutation_signal_keys`` for
setup-save invalidation; that subset is not a new registry flag.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import NamedTuple


class ResearchKeySpec(NamedTuple):
    """One research session key and the invalidation flags that own it."""

    key: str
    dataset_clear: bool = False
    apply_clear: bool = False
    thesis_clear: bool = False
    widget: bool = False
    sticky: bool = False


_DATASET_CLEAR_SOURCE: tuple[str, ...] = (
    # Current pages/1_Data.py dataset-switch pop list (resolved).
    "levels",
    "subtimeframe_data",
    "subtimeframe_interval",
    "subtimeframe_format_profile",
    "ingestion_provenance",
    "derived_parent_diagnostics",
    "subtimeframe_fallback_parent_bars",
    "_subtimeframe_compatibility_report",
    "_subtimeframe_compatibility_signature",
    "_subtimeframe_duplicate_report",
    "_subtimeframe_duplicate_signature",
    "_subtimeframe_duplicate_source",
    "subtimeframe_duplicate_resolution",
    "_subtimeframe_diagnostic_data",
    "_subtimeframe_upload_signature",
    "_subtimeframe_uploader_nonce",
    "raw_data",
    "raw_interval",
    "format_profile",
    "session_levels",
    "levels_settings",
    "levels_data_fingerprint",
    "confluence_zones",
    "naked_flags",
    "last_signal_setup",
    "signal_context",
    "signals",
    "trades",
    "trade_summary",
    "equity_curve",
    "backtest_intrabar_policy",
    "backtest_intrabar_diagnostic",
    "backtest_exit_management_policy",
    "backtest_exit_management_diagnostic",
    "grid_results",
    "best_grid_result",
    "grid_intrabar_policy",
    "grid_exit_management_policy",
    "time_bucketed_trades",
    "time_grouped_summary",
    "validation_summary",
    "walk_forward_results",
    "walk_forward_summary",
    "walk_forward_config",
    "walk_forward_otf_filter",
    "walk_forward_oos_trades",
    "walk_forward_stitched_equity",
    "walk_forward_warnings",
    "wfa_matrix",
    "wfa_matrix_config",
    "excursion_summary",
    "excursion_config",
    "excursion_grouped_summary",
    "excursion_calibration_grid",
    "excursion_quadrant_summary",
    "monte_carlo_summary",
    "monte_carlo_config",
    "noise_summary",
    "noise_config",
    "overfitting_summary",
    "overfitting_config",
    "sensitivity_summary",
    "sensitivity_config",
    "trade_review_trade_id",
    "trade_review_buffer_rows",
    "trade_review_export_zip",
    "trade_review_export_signature",
    "portfolio_setup_inputs",
    "portfolio_config",
    "portfolio_summary",
    "portfolio_trades",
    "portfolio_skipped_trades",
    "portfolio_equity_curve",
    "portfolio_correlation",
    "portfolio_drawdown_correlation",
    "portfolio_marginal_contribution",
    "roll_policy",
    "roll_validation",
    "roll_method_selector",
    "roll_contract_column_input",
    "roll_adjustment_method_selector",
    "roll_rule_selector",
    "tick_paths",
    "_tick_upload_signature",
    "tick_row_count",
    "tick_session_count",
    "tick_attach_warnings",
    "focused_trades",
    "focused_equity_curve",
    "focus_entry_window",
    "focused_trade_summary",
    "focus_provenance",
    "focused_direction_summary",
    "otf_filter_summary",
    "otf_filter_result",
    "backtest_otf_filter",
    "grid_otf_filter",
    "otf_rejected_signals",
    "otf_candidate_signals",
    "otf_accepted_signals",
    "signal_settings",
    "signal_settings_hash",
    "setup_config",
    "_setup_builder_editor_config",
    "display_timezone",
)

_APPLY_CLEAR_SOURCE: tuple[str, ...] = (
    # C-7 managed / AH4 apply-clear set (105). Frozen by tests/test_research_bundle.py.
    "backtest_config",
    "backtest_execution_costs",
    "backtest_exit_management_diagnostic",
    "backtest_exit_management_policy",
    "backtest_intrabar_diagnostic",
    "backtest_intrabar_policy",
    "backtest_otf_filter",
    "backtest_session_exit_policy",
    "base_interval",
    "best_grid_result",
    "cache_provenance",
    "confluence_by_exact_combo",
    "confluence_by_level_count",
    "confluence_by_membership",
    "confluence_by_pairs",
    "confluence_combo_summary",
    "confluence_zones",
    "data",
    "data_identity",
    "dataset_id",
    "direction_collision_diagnostic",
    "display_timezone",
    "entry_window",
    "entry_window_armed",
    "entry_window_promote_provenance",
    "equity_curve",
    "exchange_timezone",
    "excursion_calibration_grid",
    "excursion_config",
    "excursion_grouped_summary",
    "excursion_quadrant_summary",
    "excursion_summary",
    "execution_origin",
    "experiment_identity",
    "exposure_policy",
    "focus_entry_window",
    "focus_provenance",
    "focused_equity_curve",
    "focused_trade_summary",
    "focused_trades",
    "format_profile",
    "grid_entry_window",
    "grid_exit_management_policy",
    "grid_intrabar_policy",
    "grid_otf_filter",
    "grid_results",
    "ingestion_provenance",
    "instrument",
    "last_signal_setup",
    "levels",
    "levels_data_fingerprint",
    "levels_identity",
    "levels_settings",
    "monte_carlo_config",
    "monte_carlo_summary",
    "naked_flags",
    "noise_config",
    "noise_summary",
    "otf_accepted_signals",
    "otf_candidate_signals",
    "otf_filter_result",
    "otf_filter_summary",
    "otf_rejected_signals",
    "otf_validation_config",
    "otf_validation_matrix",
    "otf_validation_summary",
    "overfitting_config",
    "overfitting_summary",
    "portfolio_config",
    "portfolio_correlation",
    "portfolio_drawdown_correlation",
    "portfolio_equity_curve",
    "portfolio_marginal_contribution",
    "portfolio_setup_inputs",
    "portfolio_skipped_trades",
    "portfolio_summary",
    "portfolio_trades",
    "sensitivity_config",
    "sensitivity_summary",
    "session_levels",
    "setup_config",
    "signal_context",
    "signal_settings",
    "signal_settings_hash",
    "signals",
    "skipped_signals",
    "source_timezone",
    "subtimeframe_data",
    "subtimeframe_fallback_parent_bars",
    "subtimeframe_format_profile",
    "subtimeframe_interval",
    "time_bucketed_trades",
    "time_grouped_summary",
    "trade_summary",
    "trades",
    "validation_summary",
    "walk_forward_config",
    "walk_forward_oos_trades",
    "walk_forward_otf_filter",
    "walk_forward_results",
    "walk_forward_stitched_equity",
    "walk_forward_summary",
    "walk_forward_warnings",
    "wfa_matrix",
    "wfa_matrix_config",
)

_THESIS_CLEAR_SOURCE: tuple[str, ...] = (
    # Assistant thesis-scoped staging (workspace.THESIS_SCOPED_STAGING_KEYS).
    "assistant_draft_prompt",
    "assistant_draft_choices",
    "assistant_hydrated_conversation_id",
    "assistant_validated_run_spec",
    "assistant_focused_run_id",
    "assistant_results_qa_deep_link",
    "assistant_results_qa_force_expand",
    "assistant_bundle_handoff",
    "assistant_flash",
    "assistant_voice_results_sessions",
    "assistant_voice_help_session_id",
    "assistant_voice_last_turn",
    "assistant_voice_playback",
    "assistant_ux_mode",
    "assistant_discuss_run_picker",
)

_WIDGET_SOURCE: tuple[str, ...] = (
    # Uploader nonces, tick-path textarea, roll selectors, Admit widgets.
    "_primary_csv_uploader_nonce",
    "_subtimeframe_uploader_nonce",
    "_tick_uploader_nonce",
    "_tick_paths_text",
    "roll_method_selector",
    "roll_contract_column_input",
    "roll_adjustment_method_selector",
    "roll_rule_selector",
    "backtest_entry_window_enabled",
    "backtest_entry_window_mode",
    "backtest_entry_window_rth_segments",
    "backtest_entry_window_start_time",
    "backtest_entry_window_end_time",
    "backtest_entry_window_timezone",
)

# Explicit apply-only members. A new apply-clear key must be added here or
# to ``_DATASET_CLEAR_SOURCE`` — omitting both fails closed at import.
_STICKY_APPLY_SOURCE: tuple[str, ...] = (
    "backtest_config",
    "backtest_execution_costs",
    "backtest_session_exit_policy",
    "base_interval",
    "cache_provenance",
    "confluence_by_exact_combo",
    "confluence_by_level_count",
    "confluence_by_membership",
    "confluence_by_pairs",
    "confluence_combo_summary",
    "data",
    "data_identity",
    "dataset_id",
    "direction_collision_diagnostic",
    "entry_window",
    "entry_window_armed",
    "entry_window_promote_provenance",
    "exchange_timezone",
    "execution_origin",
    "experiment_identity",
    "exposure_policy",
    "grid_entry_window",
    "instrument",
    "levels_identity",
    "otf_validation_config",
    "otf_validation_matrix",
    "otf_validation_summary",
    "skipped_signals",
    "source_timezone",
)


def _require_unique(keys: tuple[str, ...], name: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for key in keys:
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        raise ValueError(f"{name} has duplicate keys: {duplicates}")


def validate_apply_sticky(
    apply_set: set[str],
    dataset_set: set[str],
    sticky_set: set[str],
) -> None:
    """Fail closed: every apply-clear key is dataset-clear XOR explicitly sticky."""
    overlap = sorted(sticky_set & dataset_set)
    if overlap:
        raise ValueError(f"sticky keys cannot also be dataset-clear: {overlap}")
    missing_apply = sorted(sticky_set - apply_set)
    if missing_apply:
        raise ValueError(f"sticky keys must be apply-clear: {missing_apply}")
    unlabeled = sorted(apply_set - dataset_set - sticky_set)
    if unlabeled:
        raise ValueError(
            f"apply-clear keys must be dataset-clear or explicitly sticky: {unlabeled}"
        )


def _build_registry() -> tuple[ResearchKeySpec, ...]:
    for source, name in (
        (_DATASET_CLEAR_SOURCE, "_DATASET_CLEAR_SOURCE"),
        (_APPLY_CLEAR_SOURCE, "_APPLY_CLEAR_SOURCE"),
        (_THESIS_CLEAR_SOURCE, "_THESIS_CLEAR_SOURCE"),
        (_WIDGET_SOURCE, "_WIDGET_SOURCE"),
        (_STICKY_APPLY_SOURCE, "_STICKY_APPLY_SOURCE"),
    ):
        _require_unique(source, name)
    apply_set = set(_APPLY_CLEAR_SOURCE)
    dataset_set = set(_DATASET_CLEAR_SOURCE)
    thesis_set = set(_THESIS_CLEAR_SOURCE)
    widget_set = set(_WIDGET_SOURCE)
    sticky_set = set(_STICKY_APPLY_SOURCE)
    validate_apply_sticky(apply_set, dataset_set, sticky_set)
    ordered: list[str] = []
    seen: set[str] = set()
    for key in _DATASET_CLEAR_SOURCE + _APPLY_CLEAR_SOURCE + _THESIS_CLEAR_SOURCE + _WIDGET_SOURCE:
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    specs: list[ResearchKeySpec] = []
    for key in ordered:
        apply_clear = key in apply_set
        dataset_clear = key in dataset_set
        specs.append(
            ResearchKeySpec(
                key=key,
                dataset_clear=dataset_clear,
                apply_clear=apply_clear,
                thesis_clear=key in thesis_set,
                widget=key in widget_set,
                sticky=key in sticky_set,
            )
        )
    return tuple(specs)


RESEARCH_KEY_REGISTRY: tuple[ResearchKeySpec, ...] = _build_registry()
RESEARCH_KEY_BY_NAME: dict[str, ResearchKeySpec] = {
    spec.key: spec for spec in RESEARCH_KEY_REGISTRY
}

# Generated pop lists. Order follows first-seen in the source tuples above.
DATASET_CLEAR_KEYS: tuple[str, ...] = tuple(
    spec.key for spec in RESEARCH_KEY_REGISTRY if spec.dataset_clear
)
APPLY_CLEAR_KEYS: tuple[str, ...] = tuple(
    spec.key for spec in RESEARCH_KEY_REGISTRY if spec.apply_clear
)
THESIS_CLEAR_KEYS: tuple[str, ...] = tuple(
    spec.key for spec in RESEARCH_KEY_REGISTRY if spec.thesis_clear
)
WIDGET_KEYS: tuple[str, ...] = tuple(spec.key for spec in RESEARCH_KEY_REGISTRY if spec.widget)
STICKY_APPLY_KEYS: tuple[str, ...] = tuple(
    spec.key for spec in RESEARCH_KEY_REGISTRY if spec.sticky
)
BACKTEST_ENTRY_WINDOW_WIDGET_KEYS: tuple[str, ...] = tuple(
    key for key in WIDGET_KEYS if key.startswith("backtest_entry_window_")
)

# QI-03-12 / D-2: setup save / set-active / clear / delete-active / copy-to-builder
# pop the in-session candidate cluster the way dataset-clear pops ``signals``.
# Identity siblings go too so a leftover hash cannot look like a match.
# Zones stay; regenerate rebuilds candidates. Artifact-identity keys are
# page-6 session fields (not registry rows).
SETUP_MUTATION_SIGNAL_KEYS: tuple[str, ...] = (
    "signals",
    "signal_settings",
    "signal_settings_hash",
    "signal_artifact_identity_status",
    "signal_artifact_identity_error",
    "last_signal_setup",
    "signal_context",
)


def pop_setup_mutation_signal_keys(session_state: MutableMapping[str, object]) -> None:
    """Pop leftover candidates after a setup_config mutation (QI-03-12)."""
    for key in SETUP_MUTATION_SIGNAL_KEYS:
        session_state.pop(key, None)
