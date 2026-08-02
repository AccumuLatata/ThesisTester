"""Bounded, JSON-safe adapters for ThesisTester's public headless API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from thesistester import __version__
from thesistester.api import (
    _GRID_DEFAULTS,
    preview_resampled_ohlcv,
    run_otf_validation,
    run_time_analysis,
)
from thesistester.api import _VALIDATION_DEFAULTS
from thesistester.api import run_experiment as _run_experiment
from thesistester.api import validate_run_spec
from thesistester.persistence.local_store import (
    clear_backtest_defaults,
    clear_grid_defaults,
    get_backtest_defaults,
    get_grid_defaults,
    list_datasets,
    load_dataset,
    save_backtest_defaults,
    save_grid_defaults,
)
from thesistester.reporting import build_research_artifact, to_jsonable
from thesistester.research_bundle import (
    build_research_bundle,
    canonical_bundle_hash,
    load_research_bundle,
)


class AssistantToolError(ValueError):
    """Raised when an assistant adapter request exceeds its declared boundary."""


@dataclass(frozen=True)
class ToolLimits:
    """Upper bounds for assistant-originated experiment specifications."""

    max_grid_cells: int = 500
    max_simulations: int = 5000
    max_walk_forward_matrix_cells: int = 100


def _resolve_within(path: str | Path, roots: tuple[Path, ...]) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not roots:
        raise AssistantToolError("At least one allowed local data root is required.")
    if not any(candidate.is_relative_to(root.resolve()) for root in roots):
        raise AssistantToolError("Path is outside the configured local data roots.")
    return candidate


def _bounded_spec(spec: Mapping[str, Any], limits: ToolLimits) -> dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise AssistantToolError("Experiment specification must be an object.")
    copied = dict(spec)
    grid = copied.get("grid")
    if isinstance(grid, Mapping) and grid.get("enabled", True):
        configured_cap = grid.get("max_grid_cells", limits.max_grid_cells)
        if not isinstance(configured_cap, int) or isinstance(configured_cap, bool):
            raise AssistantToolError("grid.max_grid_cells must be an integer.")
        if configured_cap > limits.max_grid_cells:
            raise AssistantToolError(f"Grid exceeds maximum of {limits.max_grid_cells} cells.")
        dimensions = (
            "stop_loss_ticks_values",
            "take_profit_ticks_values",
            "breakeven_after_r_values",
            "trailing_after_r_values",
            "trailing_distance_ticks_values",
        )
        cell_count = 1
        for key in dimensions:
            values = grid.get(key, _GRID_DEFAULTS[key])
            if isinstance(values, list):
                cell_count *= len(values)
        if cell_count > configured_cap:
            raise AssistantToolError(f"Grid exceeds maximum of {configured_cap} cells.")
    walk_forward = copied.get("walk_forward")
    if isinstance(walk_forward, Mapping) and walk_forward.get("enabled", True):
        matrix = walk_forward.get("matrix")
        if isinstance(matrix, Mapping) and matrix.get("enabled", False):
            configured_cap = matrix.get("max_matrix_cells", limits.max_walk_forward_matrix_cells)
            if not isinstance(configured_cap, int) or isinstance(configured_cap, bool):
                raise AssistantToolError("walk_forward.matrix.max_matrix_cells must be an integer.")
            if configured_cap > limits.max_walk_forward_matrix_cells:
                raise AssistantToolError(
                    "Walk-forward matrix exceeds maximum of "
                    f"{limits.max_walk_forward_matrix_cells} cells."
                )
            train = matrix.get("train_session_values", [])
            test = matrix.get("test_session_values", [])
            if (
                isinstance(train, list)
                and isinstance(test, list)
                and len(train) * len(test) > configured_cap
            ):
                raise AssistantToolError(
                    f"Walk-forward matrix exceeds maximum of {configured_cap} cells."
                )
    validation = copied.get("validation")
    if isinstance(validation, Mapping) and validation.get("enabled", True):
        for key in ("n_bootstrap", "n_permutations"):
            value = validation.get(key, _VALIDATION_DEFAULTS[key])
            if isinstance(value, int) and value > limits.max_simulations:
                raise AssistantToolError(
                    f"validation.{key} exceeds maximum of {limits.max_simulations}."
                )
        monte_carlo = validation.get("monte_carlo")
        if isinstance(monte_carlo, Mapping) and monte_carlo.get("enabled", True):
            simulations = monte_carlo.get("n_simulations", limits.max_simulations)
            if isinstance(simulations, int) and simulations > limits.max_simulations:
                raise AssistantToolError(
                    "validation.monte_carlo.n_simulations exceeds maximum of "
                    f"{limits.max_simulations}."
                )
    return copied


def _normalize_dataset_paths(spec: dict[str, Any], roots: tuple[Path, ...]) -> dict[str, Any]:
    dataset = spec.get("dataset")
    if not isinstance(dataset, Mapping) or "path" not in dataset:
        raise AssistantToolError("Experiment dataset.path is required.")
    normalized_dataset = dict(dataset)
    normalized_dataset["path"] = str(_resolve_within(dataset["path"], roots))
    if "subtimeframe_path" in dataset and dataset["subtimeframe_path"] is not None:
        normalized_dataset["subtimeframe_path"] = str(
            _resolve_within(dataset["subtimeframe_path"], roots)
        )
    return {**spec, "dataset": normalized_dataset}


def _state_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    artifact = build_research_artifact(state)
    return {
        "instrument": artifact["configuration"]["instrument"],
        "results": artifact["results"],
        "warnings": {
            "walk_forward": artifact["results"]["walk_forward_warnings"],
            "intrabar": artifact["results"]["backtest_intrabar_diagnostic"],
        },
    }


class AssistantTools:
    """Narrow tool surface; no arbitrary Python, shell, or filesystem access."""

    def __init__(self, *, data_roots: tuple[Path, ...], limits: ToolLimits = ToolLimits()) -> None:
        self.data_roots = tuple(root.resolve() for root in data_roots)
        self.limits = limits

    def list_local_datasets(self) -> list[dict[str, Any]]:
        """List persisted datasets without reading arbitrary filesystem paths."""
        return to_jsonable(list_datasets())

    def get_execution_defaults(self) -> dict[str, Any]:
        """Return persisted backtest/grid defaults without mutating them."""
        return {
            "backtest": to_jsonable(get_backtest_defaults()),
            "grid": to_jsonable(get_grid_defaults()),
        }

    def save_execution_defaults(self, *, backtest: dict[str, Any], grid: dict[str, Any]) -> None:
        """Persist explicit assistant-requested execution defaults."""
        save_backtest_defaults(backtest)
        save_grid_defaults(grid)

    def clear_execution_defaults(self) -> None:
        """Clear explicit assistant-requested execution defaults."""
        clear_backtest_defaults()
        clear_grid_defaults()

    def describe_local_dataset(self, dataset_id: str) -> dict[str, Any]:
        """Return bounded persisted-dataset metadata."""
        data, metadata = load_dataset(dataset_id)
        return {
            "metadata": to_jsonable(metadata),
            "columns": list(data.columns),
            "rows": int(len(data)),
        }

    def validate_experiment(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a bounded public experiment spec without executing it."""
        bounded = _bounded_spec(spec, self.limits)
        validate_run_spec(_normalize_dataset_paths(bounded, self.data_roots))
        return {"valid": True, "tool_version": __version__}

    def run_experiment(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Run a validated public experiment and return bounded result evidence."""
        bounded = _bounded_spec(spec, self.limits)
        normalized = _normalize_dataset_paths(bounded, self.data_roots)
        validate_run_spec(normalized)
        dataset_path = Path(normalized["dataset"]["path"])
        state = _run_experiment(normalized, base_directory=dataset_path.parent)
        return {"summary": _state_summary(state), "tool_version": __version__}

    def run_experiment_to_bundle(
        self, spec: Mapping[str, Any], *, output_path: str | Path
    ) -> dict[str, Any]:
        """Execute once, write a portable bundle, and return reproducible provenance."""
        bounded = _bounded_spec(spec, self.limits)
        normalized = _normalize_dataset_paths(bounded, self.data_roots)
        validate_run_spec(normalized)
        path = _resolve_within(output_path, self.data_roots)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = _run_experiment(
            normalized, base_directory=Path(normalized["dataset"]["path"]).parent
        )
        bundle = build_research_bundle(state)
        path.write_bytes(bundle)
        return {
            "summary": _state_summary(state),
            "bundle_path": str(path),
            "canonical_bundle_hash": canonical_bundle_hash(bundle),
            "dataset_fingerprint": to_jsonable(state.get("levels_data_fingerprint")),
            "tool_version": __version__,
        }

    def load_bundle_summary(self, bundle_path: str | Path) -> dict[str, Any]:
        """Load a bundle beneath an allowed root and return compact evidence."""
        path = _resolve_within(bundle_path, self.data_roots)
        raw = path.read_bytes()
        state = load_research_bundle(raw)
        return {
            "bundle_path": str(path),
            "canonical_bundle_hash": canonical_bundle_hash(raw),
            "summary": _state_summary(state),
        }

    def compare_bundle_summaries(self, bundle_paths: list[str | Path]) -> list[dict[str, Any]]:
        """Return independently grounded summaries for explicit bundle choices."""
        if len(bundle_paths) < 2:
            raise AssistantToolError("Select at least two bundles to compare.")
        return [self.load_bundle_summary(path) for path in bundle_paths]

    def summarize_bundle_time_analysis(
        self,
        bundle_path: str | Path,
        *,
        group_col: str = "entry_rth_segment",
        bucket_timezone: str = "America/New_York",
        min_trades: int = 10,
    ) -> list[dict[str, Any]]:
        """Return bounded descriptive time analysis for a selected research bundle."""
        path = _resolve_within(bundle_path, self.data_roots)
        state = load_research_bundle(path.read_bytes())
        trades = state.get("trades")
        if trades is None:
            raise AssistantToolError("Bundle does not include completed trades.")
        return to_jsonable(
            run_time_analysis(
                trades,
                group_col=group_col,
                bucket_timezone=bucket_timezone,
                min_trades=min_trades,
            ).to_dict("records")
        )

    def run_bundle_otf_validation(
        self,
        bundle_path: str | Path,
        *,
        instrument: str,
        stop_loss_ticks: int | float,
        take_profit_ticks: int | float,
        train_fraction: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Run the fixed OTF matrix from a selected bundle's dataset and signals."""
        path = _resolve_within(bundle_path, self.data_roots)
        state = load_research_bundle(path.read_bytes())["session_values"]
        data = state.get("data")
        signals = state.get("signals")
        if data is None or signals is None:
            raise AssistantToolError("Bundle requires dataset and signals for OTF validation.")
        return to_jsonable(
            run_otf_validation(
                data,
                signals,
                instrument=instrument,
                stop_loss_ticks=stop_loss_ticks,
                take_profit_ticks=take_profit_ticks,
                train_fraction=train_fraction,
                session_timezone=state.get("exchange_timezone"),
                eth_start=state.get("eth_start"),
                setup_config=state.get("setup_config"),
                signal_settings=state.get("signal_settings"),
            ).to_dict("records")
        )

    def preview_bundle_resample(
        self, bundle_path: str | Path, *, timeframe: str, max_rows: int = 200
    ) -> list[dict[str, Any]]:
        """Return a bounded resample preview for a selected bundle dataset."""
        path = _resolve_within(bundle_path, self.data_roots)
        data = load_research_bundle(path.read_bytes())["session_values"].get("data")
        if data is None:
            raise AssistantToolError("Bundle does not include a dataset.")
        return to_jsonable(
            preview_resampled_ohlcv(data, timeframe=timeframe, max_rows=max_rows).to_dict("records")
        )
