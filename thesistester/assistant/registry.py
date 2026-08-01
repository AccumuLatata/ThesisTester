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
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "DATA.load_ohlcv",
            "Data",
            "Load sample or user-provided OHLCV using a vendor profile",
            "thesistester.api.load_dataset",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.USER_REQUEST,
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
            "thesistester.data.resample.resample_ohlcv",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.NONE,
            limitation="No bounded JSON-safe headless preview adapter exists.",
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
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "DATA.download_intrabar_compatibility",
            "Data",
            "Export lower-timeframe compatibility diagnostics",
            None,
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "DATA.configure_roll_assumptions",
            "Data",
            "Configure and validate futures roll metadata",
            "thesistester.data.rolls",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.NONE,
            limitation="Roll controls are not exposed by the current headless facade.",
        ),
        _capability(
            "SETUP.configure",
            "Setup Builder",
            "Define identity, confluence, trigger, naked, anchor, and OTF rules",
            "thesistester.api.build_setup",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.USER_REQUEST,
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
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "LEVELS.configure_and_compute",
            "Levels",
            "Configure and calculate session, profile, indicator, and opt-in levels",
            "thesistester.api.compute_levels",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "LEVELS.manage_saved_snapshots",
            "Levels",
            "Save, load, list, or delete computed level snapshots",
            "thesistester.persistence.local_store",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "LEVELS.inspect_and_chart",
            "Levels",
            "Inspect level tables and render a levels chart",
            "thesistester.visualization.build_levels_chart",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "SIGNALS.generate",
            "Signals",
            "Generate confluence zones, naked flags, and candidate signals",
            "thesistester.api.generate_signals",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "SIGNALS.manage_saved_runs",
            "Signals",
            "Save, load, list, or delete signal runs",
            "thesistester.persistence.local_store",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "SIGNALS.inspect_and_chart",
            "Signals",
            "Inspect signal diagnostics, tables, and charts",
            "thesistester.visualization.build_signals_chart",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "BACKTEST.configure_and_run",
            "Backtest",
            "Configure execution assumptions and run the backtest",
            "thesistester.api.run_backtest",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "BACKTEST.manage_execution_defaults",
            "Backtest",
            "Save, restore, or reset execution defaults",
            "thesistester.persistence.local_store",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.NONE,
            limitation="Execution-default persistence has no assistant repository contract yet.",
        ),
        _capability(
            "BACKTEST.inspect_results",
            "Backtest",
            "Inspect KPIs, equity, skipped signals, OTF rejections, and trade charts",
            "thesistester.api.run_backtest",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "BACKTEST.export_trade_review",
            "Backtest",
            "Export worst-loser trade review images",
            "thesistester.visualization.export_worst_loser_review_pngs",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "GRID.configure_and_run",
            "Grid Search",
            "Configure and run an SL/TP grid search",
            "thesistester.api.run_grid",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "GRID.inspect_results",
            "Grid Search",
            "Inspect best cells, directional rankings, heatmaps, and grid tables",
            "thesistester.analytics.grid.best_grid_result",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
        ),
        _capability(
            "GRID.manage_execution_defaults",
            "Grid Search",
            "Save, restore, or reset grid execution defaults",
            "thesistester.persistence.local_store",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.NONE,
            limitation="Grid-default persistence has no assistant repository contract yet.",
        ),
        _capability(
            "TIME.analyze",
            "Time Analysis",
            "Bucket completed trades and inspect grouped time performance",
            "thesistester.analytics.time_analysis",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.NONE,
            limitation="Time-analysis functions are not yet exposed through the headless facade.",
        ),
        _capability(
            "VALIDATION.run_core",
            "Validation",
            "Run bootstrap, permutation, and grid-overfit diagnostics",
            "thesistester.api.run_validation",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "VALIDATION.run_excursion",
            "Validation",
            "Run MAE/MFE excursion and calibration diagnostics",
            "thesistester.api.run_validation",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "VALIDATION.run_monte_carlo",
            "Validation",
            "Run seeded trade-sequence Monte Carlo diagnostics",
            "thesistester.api.run_validation",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "VALIDATION.run_overfitting",
            "Validation",
            "Run CSCV/PBO, DSR, and versus-random diagnostics",
            "thesistester.api.run_validation",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "VALIDATION.run_noise",
            "Validation",
            "Run perturbed-OHLC noise tests",
            "thesistester.api.run_noise_test",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "VALIDATION.run_sensitivity",
            "Validation",
            "Run one-at-a-time sensitivity profiles",
            "thesistester.api.run_sensitivity_profile",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_STANDARD_COMPUTE,
        ),
        _capability(
            "VALIDATION.run_walk_forward",
            "Validation",
            "Run bar/session walk-forward and WFA matrix research",
            "thesistester.api.run_walk_forward",
            CapabilityMode.EXECUTABLE,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
            resource_envelope=_WALK_FORWARD_COMPUTE,
        ),
        _capability(
            "VALIDATION.run_otf_matrix",
            "Validation",
            "Run OTF configuration train/OOS matrix analysis",
            "thesistester.analytics.otf_validation.run_otf_validation_matrix",
            CapabilityMode.UNSUPPORTED,
            ConfirmationLevel.NONE,
            limitation="The OTF matrix has no headless facade adapter.",
        ),
        _capability(
            "VALIDATION.inspect_results",
            "Validation",
            "Inspect validation diagnostics, folds, distributions, and result tables",
            "thesistester.api.run_validation",
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
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
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
        ),
        _capability(
            "EXPORT.inspect_uploaded_artifact",
            "Report / Export",
            "Read a previously exported research artifact",
            "thesistester.reporting",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.USER_REQUEST,
        ),
        _capability(
            "BUNDLE.export",
            "Research Bundles",
            "Export a portable research bundle",
            "thesistester.research_bundle.build_research_bundle",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
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
            "PORTFOLIO.import_trades",
            "Portfolio",
            "Add current or imported completed-trade series",
            "pages/13_Portfolio.py",
            CapabilityMode.IMPORT_EXPORT,
            ConfirmationLevel.EXPLICIT_CONFIRMATION,
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
            CapabilityMode.INSPECT_ONLY,
            ConfirmationLevel.NONE,
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
