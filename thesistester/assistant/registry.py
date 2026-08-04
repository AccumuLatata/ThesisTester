"""Feature-parity registry for the AI Research Assistant.

The registry is declarative. A row describes the present UI capability and its
current assistant support status; it does not grant execution authority.
"""

from __future__ import annotations

from collections.abc import Iterable

from thesistester.assistant.contracts import (
    AssistantContractError,
    AssistantRequest,
    Capability,
    CapabilityMode,
    ConfirmationLevel,
    ResourceEnvelope,
    UnknownCapabilityError,
)

_STANDARD_COMPUTE = ResourceEnvelope(max_grid_cells=500, max_simulations=5000)
_WALK_FORWARD_COMPUTE = ResourceEnvelope(
    max_grid_cells=500,
    max_simulations=5000,
    max_walk_forward_folds=100,
)


def _capability(
    capability_id: str,
    ui_location: str,
    user_action: str,
    public_symbol: str | None,
    mode: CapabilityMode,
    confirmation: ConfirmationLevel,
    *,
    resource_envelope: ResourceEnvelope = ResourceEnvelope(),
    limitation: str | None = None,
) -> Capability:
    return Capability(
        capability_id=capability_id,
        ui_location=ui_location,
        user_action=user_action,
        public_symbol=public_symbol,
        mode=mode,
        confirmation=confirmation,
        resource_envelope=resource_envelope,
        limitation=limitation,
    )


def _validate_registry(capabilities: Iterable[Capability]) -> tuple[Capability, ...]:
    rows = tuple(capabilities)
    ids = [capability.capability_id for capability in rows]
    duplicates = sorted({capability_id for capability_id in ids if ids.count(capability_id) > 1})
    if duplicates:
        raise AssistantContractError(f"Duplicate assistant capability IDs: {duplicates}")
    if not rows:
        raise AssistantContractError("Feature-parity registry must not be empty.")
    return rows


FEATURE_PARITY_REGISTRY = _validate_registry(
    (
        _capability(
            "HOME.workflow_guide",
            "Home",
            "Read the workflow guide and research caveats",
            None,
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "HOME.session_data_status",
            "Home",
            "Inspect current session data status",
            "st.session_state['data']",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.NONE,
            limitation="Session data inspection remains Streamlit-page local; use research-bundle import for assistant evidence.",
        ),
        _capability(
            "DATA.load_ohlcv",
            "Data",
            "Load sample or user-provided OHLCV using a vendor profile",
            "thesistester.api.load_dataset",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.USER_REQUEST,
            limitation="Standalone OHLCV loading is available only through the Data page or PIPELINE.run_experiment dataset.path.",
        ),
        _capability(
            "DATA.inspect_dataset",
            "Data",
            "Inspect dataset validation, rows, interval, sessions, and preview",
            "thesistester.api.load_dataset",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "DATA.preview_resampled_timeframes",
            "Data",
            "Preview resampled OHLCV timeframes",
            "thesistester.api.preview_resampled_ohlcv",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "DATA.manage_saved_datasets",
            "Data",
            "List, save, load, or delete local datasets",
            "thesistester.persistence.local_store",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "DATA.configure_subtimeframe",
            "Data",
            "Provide lower-timeframe data for intrabar replay",
            "thesistester.api.run_experiment",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
            limitation="Configure subtimeframe data through an explicit RunSpec dataset.subtimeframe_path.",
        ),
        _capability(
            "DATA.download_intrabar_compatibility",
            "Data",
            "Export lower-timeframe compatibility diagnostics",
            None,
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation="Intrabar compatibility export is not routed through the assistant orchestrator.",
        ),
        _capability(
            "DATA.configure_roll_assumptions",
            "Data",
            "Configure and validate futures roll metadata",
            "thesistester.api.validate_roll_assumptions",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "SETUP.configure",
            "Setup Builder",
            "Define identity, confluence, trigger, naked, anchor, and OTF rules",
            "thesistester.api.build_setup",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.USER_REQUEST,
            limitation="Configure setups with assistant structured controls and the canonical RunSpec compiler.",
        ),
        _capability(
            "SETUP.manage_saved_setups",
            "Setup Builder",
            "Save, load, duplicate, or delete local setup configurations",
            "thesistester.persistence.local_store",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "SETUP.inspect_active_setup",
            "Setup Builder",
            "Inspect the selected setup and OTF configuration",
            "thesistester.setup.get_effective_otf_filter_config",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.NONE,
            limitation="Active Streamlit setup inspection is page-local; load a saved setup through SETUP.manage_saved_setups.",
        ),
        _capability(
            "LEVELS.configure_and_compute",
            "Levels",
            "Configure and calculate session, profile, indicator, and opt-in levels",
            "thesistester.api.compute_levels",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation="Level computation is executed only through PIPELINE.run_experiment.",
        ),
        _capability(
            "LEVELS.manage_saved_snapshots",
            "Levels",
            "Save, load, list, or delete computed level snapshots",
            "thesistester.persistence.local_store",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation="Level snapshot persistence is not routed through the assistant orchestrator.",
        ),
        _capability(
            "LEVELS.inspect_and_chart",
            "Levels",
            "Inspect level configuration, identity, families, and columns from a verified bundle",
            "thesistester.assistant.page_summaries.summarize_levels_state",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
            limitation="Levels charts remain on the Levels page; Assistant returns bounded summary JSON only.",
        ),
        _capability(
            "SIGNALS.generate",
            "Signals",
            "Generate confluence zones, naked flags, and candidate signals",
            "thesistester.api.generate_signals",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation="Signal generation is executed only through PIPELINE.run_experiment.",
        ),
        _capability(
            "SIGNALS.manage_saved_runs",
            "Signals",
            "Save, load, list, or delete signal runs",
            "thesistester.persistence.local_store",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation="Signal-run persistence is not routed through the assistant orchestrator.",
        ),
        _capability(
            "SIGNALS.inspect_and_chart",
            "Signals",
            "Inspect signal counts, zones, and trigger/direction distributions from a verified bundle",
            "thesistester.assistant.page_summaries.summarize_signals_state",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
            limitation="Signal charts remain on the Signals page; Assistant returns bounded summary JSON only.",
        ),
        _capability(
            "BACKTEST.configure_and_run",
            "Backtest",
            "Configure execution assumptions and run the backtest",
            "thesistester.api.run_backtest",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
            limitation="Use PIPELINE.run_experiment for confirmation-gated backtests.",
        ),
        _capability(
            "BACKTEST.manage_execution_defaults",
            "Backtest",
            "Save, restore, or reset execution defaults",
            "thesistester.persistence.local_store",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "BACKTEST.inspect_results",
            "Backtest",
            "Inspect KPIs, costs, intrabar policy, and caveats from a verified bundle",
            "thesistester.assistant.page_summaries.summarize_backtest_state",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
            limitation="Equity/trade charts remain on the Backtest page; Assistant returns bounded summary JSON only.",
        ),
        _capability(
            "BACKTEST.export_trade_review",
            "Backtest",
            "Export worst-loser trade review images",
            "thesistester.visualization.export_worst_loser_review_pngs",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation="Trade-review image export is not routed through the assistant orchestrator.",
        ),
        _capability(
            "GRID.configure_and_run",
            "Grid Search",
            "Configure and run an SL/TP grid search",
            "thesistester.api.run_grid",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
            limitation="Use PIPELINE.run_experiment with an explicit grid section.",
        ),
        _capability(
            "GRID.inspect_results",
            "Grid Search",
            "Inspect best-cell selection evidence from a verified bundle",
            "thesistester.assistant.page_summaries.summarize_grid_state",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
            limitation="Grid heatmaps/tables remain on the Grid Search page; Assistant returns bounded summary JSON only.",
        ),
        _capability(
            "GRID.manage_execution_defaults",
            "Grid Search",
            "Save, restore, or reset grid execution defaults",
            "thesistester.persistence.local_store",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "TIME.analyze",
            "Time Analysis",
            "Bucket completed trades and inspect grouped time performance",
            "thesistester.api.run_time_analysis",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "VALIDATION.run_core",
            "Validation",
            "Run bootstrap, permutation, and grid-overfit diagnostics",
            "thesistester.api.run_validation",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
            limitation="Core validation runs through PIPELINE.run_experiment validation configuration.",
        ),
        _capability(
            "VALIDATION.run_excursion",
            "Validation",
            "Run MAE/MFE excursion and calibration diagnostics",
            "thesistester.api.run_validation",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
            limitation="Excursion diagnostics run through PIPELINE.run_experiment validation.excursion.",
        ),
        _capability(
            "VALIDATION.run_monte_carlo",
            "Validation",
            "Run seeded trade-sequence Monte Carlo diagnostics",
            "thesistester.api.run_validation",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
            limitation="Monte Carlo diagnostics run through PIPELINE.run_experiment validation.monte_carlo.",
        ),
        _capability(
            "VALIDATION.run_overfitting",
            "Validation",
            "Run CSCV/PBO, DSR, and versus-random diagnostics",
            "thesistester.api.run_validation",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
            limitation="Overfitting diagnostics run through PIPELINE.run_experiment validation.overfitting.",
        ),
        _capability(
            "VALIDATION.run_noise",
            "Validation",
            "Run perturbed-OHLC noise tests",
            "thesistester.api.run_noise_test",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
            limitation="Noise diagnostics run through PIPELINE.run_experiment validation.noise.",
        ),
        _capability(
            "VALIDATION.run_sensitivity",
            "Validation",
            "Run one-at-a-time sensitivity profiles",
            "thesistester.api.run_sensitivity_profile",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
            limitation="Sensitivity diagnostics run through PIPELINE.run_experiment validation.sensitivity.",
        ),
        _capability(
            "VALIDATION.run_walk_forward",
            "Validation",
            (
                "Run bar/session walk-forward and WFA matrix research "
                "(optional walk_forward.otf_history_policy: fold_local default, "
                "or causal_prefix for prior-bar OTF state)"
            ),
            "thesistester.api.run_walk_forward",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_WALK_FORWARD_COMPUTE,
            limitation="Walk-forward research runs through PIPELINE.run_experiment walk_forward.",
        ),
        _capability(
            "VALIDATION.run_otf_matrix",
            "Validation",
            "Run OTF configuration train/OOS matrix analysis",
            "thesistester.api.run_otf_validation",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "VALIDATION.inspect_results",
            "Validation",
            "Inspect validation and OOS evidence scalars from a verified bundle",
            "thesistester.assistant.page_summaries.summarize_validation_state",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
            limitation="Validation charts/tables remain on the Validation page; Assistant returns bounded summary JSON only.",
        ),
        _capability(
            "CLASSIC.propose_page_change",
            "Classic workspace",
            "Propose a draft change for classic-page review (user applies on the owning page)",
            "thesistester.classic_proposal.validate_classic_proposal",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.NONE,
            limitation=(
                "Proposals are draft-only. Classic settings mutate only when the user "
                "explicitly clicks Apply on the owning page."
            ),
        ),
        _capability(
            "CACHE.inspect_artifacts",
            "Execution cache",
            "Inspect internal execution artifacts (identity, size, age, hit/miss)",
            "thesistester.persistence.list_execution_artifacts",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
            limitation=(
                "Inspection covers internal execution_artifacts only; user snapshots, "
                "bundles, thesis records, and source datasets are never listed for deletion."
            ),
        ),
        _capability(
            "CACHE.delete_artifact",
            "Execution cache",
            "Safely delete one internal execution artifact (forces cold recompute)",
            "thesistester.persistence.delete_execution_artifact",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation=(
                "Deletes only execution_artifacts entries. Never deletes user-saved "
                "snapshots, research bundles, thesis records, or source datasets."
            ),
        ),
        _capability(
            "CACHE.evict_artifacts",
            "Execution cache",
            "Bounded retention/eviction for internal execution artifacts",
            "thesistester.persistence.evict_execution_artifacts",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation=(
                "Eviction is bounded to execution_artifacts/v1. Retained research bundles "
                "remain self-contained; cache miss triggers cold recompute."
            ),
        ),
        _capability(
            "CACHE.rebind_source_path",
            "Execution cache",
            "Rebind a missing source path after content-identity verification",
            "thesistester.persistence.rebind_source_path",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation=(
                "Rebind fails closed unless the new CSV matches the expected DataIdentity "
                "content hash; path-only rebinds are rejected."
            ),
        ),
        _capability(
            "EXPORT.build_research_artifact",
            "Report / Export",
            "Build and inspect research artifact and markdown report",
            "thesistester.reporting.build_research_artifact",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.USER_REQUEST,
        ),
        _capability(
            "EXPORT.download_tables",
            "Report / Export",
            "Export research tables as CSV",
            "thesistester.reporting.dataframe_to_csv_bytes",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation="CSV table export remains on the Report/Export page.",
        ),
        _capability(
            "EXPORT.inspect_uploaded_artifact",
            "Report / Export",
            "Read a previously exported research artifact",
            "thesistester.reporting",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.USER_REQUEST,
            limitation="Uploaded artifact inspection remains on the Report/Export page.",
        ),
        _capability(
            "BUNDLE.export",
            "Research Bundles",
            "Export a portable research bundle",
            "thesistester.research_bundle.build_research_bundle",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation="Bundle export is performed by PIPELINE.run_experiment via run_experiment_to_bundle.",
        ),
        _capability(
            "BUNDLE.import",
            "Research Bundles",
            "Import and inspect a portable research bundle",
            "thesistester.research_bundle.load_research_bundle",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "BUNDLE.register_external_run",
            "Research Bundles",
            "Register a verified classic research bundle as an immutable thesis run",
            "thesistester.assistant.orchestrator.AssistantOrchestrator.register_external_bundle_run",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "PORTFOLIO.import_trades",
            "Portfolio",
            "Add current or imported completed-trade series",
            "pages/13_Portfolio.py",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            limitation="Import completed-run bundles through BUNDLE.import, then analyze with PORTFOLIO.analyze.",
        ),
        _capability(
            "PORTFOLIO.analyze",
            "Portfolio",
            "Run portfolio exposure, correlation, and contribution analysis",
            "thesistester.api.run_portfolio_analysis",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "PORTFOLIO.inspect_results",
            "Portfolio",
            "Inspect portfolio metrics, equity, correlations, and skipped trades",
            "thesistester.api.run_portfolio_analysis",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.NONE,
            limitation="Inspect portfolio results from the PORTFOLIO.analyze response.",
        ),
        _capability(
            "PIPELINE.validate_run_spec",
            "Headless CLI",
            "Validate a complete versioned experiment specification",
            "thesistester.api.validate_run_spec",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "PIPELINE.run_experiment",
            "Headless CLI",
            "Run the end-to-end deterministic research pipeline",
            "thesistester.api.run_experiment",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_WALK_FORWARD_COMPUTE,
        ),
    )
)

_BY_ID = {capability.capability_id: capability for capability in FEATURE_PARITY_REGISTRY}


def get_capability(capability_id: str) -> Capability:
    """Return one declared capability or raise an actionable fail-closed error."""
    try:
        return _BY_ID[capability_id]
    except KeyError as exc:
        raise UnknownCapabilityError(f"Unknown assistant capability: {capability_id}") from exc


def validate_capability_request(request: AssistantRequest) -> Capability:
    """Validate a request target without executing its capability."""
    capability = get_capability(request.capability_id)
    if capability.mode is CapabilityMode.UNSUPPORTED:
        raise AssistantContractError(
            f"Assistant capability {capability.capability_id} is unsupported: {capability.limitation}"
        )
    return capability
