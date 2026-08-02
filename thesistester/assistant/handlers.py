"""Typed capability handlers for the assistant orchestrator.

Every executable (or otherwise routed) registry capability must declare a
handler here. Capabilities without a handler must be marked unsupported in the
feature-parity registry so requests fail closed before execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from thesistester.assistant.contracts import AssistantRequest, Capability, ResourceEnvelope
from thesistester.assistant.tools import AssistantTools, ToolLimits


@dataclass(frozen=True)
class HandlerContext:
    """Bounded execution context supplied to one capability handler."""

    tools: AssistantTools
    capability: Capability
    limits: ToolLimits


CapabilityHandler = Callable[[AssistantRequest, HandlerContext], dict[str, Any]]


def tool_limits_from_envelope(
    envelope: ResourceEnvelope, *, base: ToolLimits | None = None
) -> ToolLimits:
    """Project a registry resource envelope onto assistant tool limits."""
    defaults = base or ToolLimits()
    return ToolLimits(
        max_grid_cells=envelope.max_grid_cells or defaults.max_grid_cells,
        max_simulations=envelope.max_simulations or defaults.max_simulations,
        max_walk_forward_matrix_cells=(
            envelope.max_walk_forward_folds or defaults.max_walk_forward_matrix_cells
        ),
    )


def _require_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object.")
    return value


def _handle_validate_run_spec(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    run_spec = _require_mapping(request.payload.get("run_spec"), field="run_spec")
    return context.tools.validate_experiment(run_spec)


def _handle_run_experiment(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    run_spec = _require_mapping(request.payload.get("run_spec"), field="run_spec")
    output_path = request.payload.get("output_path")
    if output_path is not None:
        return context.tools.run_experiment_to_bundle(run_spec, output_path=output_path)
    return context.tools.run_experiment(run_spec)


def _handle_backtest_defaults(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    action = request.payload.get("action", "save")
    if action == "get":
        return {"defaults": context.tools.get_execution_defaults()["backtest"]}
    if action == "clear":
        context.tools.clear_backtest_execution_defaults()
        return {"cleared": True}
    defaults = request.payload.get("defaults")
    if not isinstance(defaults, dict):
        raise ValueError("Backtest defaults request requires an object.")
    context.tools.save_backtest_execution_defaults(defaults)
    return {"saved": True}


def _handle_grid_defaults(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    action = request.payload.get("action", "save")
    if action == "get":
        return {"defaults": context.tools.get_execution_defaults()["grid"]}
    if action == "clear":
        context.tools.clear_grid_execution_defaults()
        return {"cleared": True}
    defaults = request.payload.get("defaults")
    if not isinstance(defaults, dict):
        raise ValueError("Grid defaults request requires an object.")
    context.tools.save_grid_execution_defaults(defaults)
    return {"saved": True}


def _handle_inspect_dataset(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    dataset_id = request.payload.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("dataset_id must be a non-empty string.")
    return context.tools.describe_local_dataset(dataset_id)


def _handle_manage_datasets(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    action = request.payload.get("action", "list")
    if action == "list":
        return {"datasets": context.tools.list_local_datasets()}
    if action == "describe":
        return _handle_inspect_dataset(request, context)
    raise ValueError(
        "DATA.manage_saved_datasets supports only list and describe in the assistant router."
    )


def _handle_manage_setups(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    action = request.payload.get("action", "list")
    if action == "list":
        dataset_id = request.payload.get("dataset_id")
        return {
            "setups": context.tools.list_saved_setup_summaries(
                dataset_id=dataset_id if isinstance(dataset_id, str) else None
            )
        }
    if action == "load":
        setup_id = request.payload.get("setup_id")
        if not isinstance(setup_id, str) or not setup_id.strip():
            raise ValueError("setup_id must be a non-empty string.")
        return {"setup": context.tools.load_saved_setup(setup_id)}
    if action == "save":
        setup = request.payload.get("setup")
        if not isinstance(setup, Mapping):
            raise ValueError("setup must be an object.")
        return {
            "setup": context.tools.save_saved_setup(
                dict(setup),
                instrument=request.payload.get("instrument"),
            )
        }
    raise ValueError(
        "SETUP.manage_saved_setups supports only list, load, and save in the assistant router."
    )


def _handle_preview_resample(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    bundle_path = request.payload.get("bundle_path")
    timeframe = request.payload.get("timeframe")
    if not isinstance(bundle_path, str) or not bundle_path.strip():
        raise ValueError("bundle_path must be a non-empty string.")
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("timeframe must be a non-empty string.")
    max_rows = request.payload.get("max_rows", 200)
    return {
        "rows": context.tools.preview_bundle_resample(
            bundle_path, timeframe=timeframe, max_rows=int(max_rows)
        )
    }


def _handle_roll_assumptions(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    bundle_path = request.payload.get("bundle_path")
    if not isinstance(bundle_path, str) or not bundle_path.strip():
        raise ValueError("bundle_path must be a non-empty string.")
    return context.tools.validate_bundle_roll_assumptions(
        bundle_path,
        contract_column=str(request.payload.get("contract_column", "contract")),
        roll_method=str(request.payload.get("roll_method", "single_contract")),
    )


def _handle_time_analyze(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    bundle_path = request.payload.get("bundle_path")
    if not isinstance(bundle_path, str) or not bundle_path.strip():
        raise ValueError("bundle_path must be a non-empty string.")
    return {
        "groups": context.tools.summarize_bundle_time_analysis(
            bundle_path,
            group_col=str(request.payload.get("group_col", "entry_rth_segment")),
            bucket_timezone=str(request.payload.get("bucket_timezone", "America/New_York")),
            min_trades=int(request.payload.get("min_trades", 10)),
        )
    }


def _handle_otf_matrix(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    bundle_path = request.payload.get("bundle_path")
    instrument = request.payload.get("instrument")
    if not isinstance(bundle_path, str) or not bundle_path.strip():
        raise ValueError("bundle_path must be a non-empty string.")
    if not isinstance(instrument, str) or not instrument.strip():
        raise ValueError("instrument must be a non-empty string.")
    return {
        "matrix": context.tools.run_bundle_otf_validation(
            bundle_path,
            instrument=instrument,
            stop_loss_ticks=request.payload["stop_loss_ticks"],
            take_profit_ticks=request.payload["take_profit_ticks"],
            train_fraction=float(request.payload.get("train_fraction", 0.7)),
        )
    }


def _handle_export_artifact(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    bundle_path = request.payload.get("bundle_path")
    if not isinstance(bundle_path, str) or not bundle_path.strip():
        raise ValueError("bundle_path must be a non-empty string.")
    expected_hash = request.payload.get("expected_hash")
    artifact = context.tools.build_bundle_research_artifact(
        bundle_path,
        expected_hash=expected_hash if isinstance(expected_hash, str) else None,
    )
    report = context.tools.render_bundle_markdown_report(
        bundle_path,
        expected_hash=expected_hash if isinstance(expected_hash, str) else None,
    )
    return {"artifact": artifact, "markdown_report": report}


def _handle_bundle_import(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    bundle_path = request.payload.get("bundle_path")
    if not isinstance(bundle_path, str) or not bundle_path.strip():
        raise ValueError("bundle_path must be a non-empty string.")
    expected_hash = request.payload.get("expected_hash")
    action = request.payload.get("action", "summary")
    if action == "evidence":
        provenance = request.payload.get("provenance")
        return {
            "evidence": context.tools.build_bundle_evidence_packet(
                bundle_path,
                expected_hash=expected_hash if isinstance(expected_hash, str) else None,
                provenance=provenance if isinstance(provenance, Mapping) else None,
            )
        }
    return context.tools.load_bundle_summary(
        bundle_path,
        expected_hash=expected_hash if isinstance(expected_hash, str) else None,
    )


def _handle_portfolio_analyze(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    bundle_paths = request.payload.get("bundle_paths")
    instrument = request.payload.get("instrument")
    expected_hashes = request.payload.get("expected_hashes")
    if not isinstance(bundle_paths, list) or not bundle_paths:
        raise ValueError("bundle_paths must be a non-empty list.")
    if not isinstance(instrument, str) or not instrument.strip():
        raise ValueError("instrument must be a non-empty string.")
    if (
        not isinstance(expected_hashes, list)
        or len(expected_hashes) != len(bundle_paths)
        or any(not isinstance(item, str) or not item.strip() for item in expected_hashes)
    ):
        raise ValueError("expected_hashes must be non-empty strings matching bundle_paths.")
    config = request.payload.get("config")
    return context.tools.analyze_bundle_portfolio(
        bundle_paths,
        instrument=instrument,
        config=config if isinstance(config, dict) else None,
        expected_hashes=expected_hashes,
    )


def _handle_home_guide(request: AssistantRequest, context: HandlerContext) -> dict[str, Any]:
    del request, context
    return {
        "guide": (
            "Draft explicit research assumptions, validate a RunSpec, confirm it, "
            "then execute through the assistant orchestrator."
        )
    }


HANDLER_REGISTRY: dict[str, CapabilityHandler] = {
    "HOME.workflow_guide": _handle_home_guide,
    "DATA.inspect_dataset": _handle_inspect_dataset,
    "DATA.manage_saved_datasets": _handle_manage_datasets,
    "DATA.preview_resampled_timeframes": _handle_preview_resample,
    "DATA.configure_roll_assumptions": _handle_roll_assumptions,
    "SETUP.manage_saved_setups": _handle_manage_setups,
    "BACKTEST.manage_execution_defaults": _handle_backtest_defaults,
    "GRID.manage_execution_defaults": _handle_grid_defaults,
    "TIME.analyze": _handle_time_analyze,
    "VALIDATION.run_otf_matrix": _handle_otf_matrix,
    "EXPORT.build_research_artifact": _handle_export_artifact,
    "BUNDLE.import": _handle_bundle_import,
    "PORTFOLIO.analyze": _handle_portfolio_analyze,
    "PIPELINE.validate_run_spec": _handle_validate_run_spec,
    "PIPELINE.run_experiment": _handle_run_experiment,
}


def get_handler(capability_id: str) -> CapabilityHandler | None:
    """Return the typed handler for one capability, if registered."""
    return HANDLER_REGISTRY.get(capability_id)
