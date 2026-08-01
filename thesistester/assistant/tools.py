"""Bounded, JSON-safe adapters for ThesisTester's public headless API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from thesistester import __version__
from thesistester.api import run_experiment as _run_experiment
from thesistester.api import validate_run_spec
from thesistester.persistence.local_store import list_datasets, load_dataset
from thesistester.reporting import build_research_artifact, to_jsonable
from thesistester.research_bundle import canonical_bundle_hash, load_research_bundle


class AssistantToolError(ValueError):
    """Raised when an assistant adapter request exceeds its declared boundary."""


@dataclass(frozen=True)
class ToolLimits:
    """Upper bounds for assistant-originated experiment specifications."""

    max_grid_cells: int = 500
    max_simulations: int = 5000


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
    if isinstance(grid, Mapping):
        stops = grid.get("stop_loss_ticks_values", [])
        targets = grid.get("take_profit_ticks_values", [])
        if (
            isinstance(stops, list)
            and isinstance(targets, list)
            and len(stops) * len(targets) > limits.max_grid_cells
        ):
            raise AssistantToolError(f"Grid exceeds maximum of {limits.max_grid_cells} cells.")
    validation = copied.get("validation")
    if isinstance(validation, Mapping):
        for key in ("n_bootstrap", "n_permutations"):
            value = validation.get(key)
            if isinstance(value, int) and value > limits.max_simulations:
                raise AssistantToolError(
                    f"validation.{key} exceeds maximum of {limits.max_simulations}."
                )
    return copied


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
        dataset = bounded.get("dataset")
        if not isinstance(dataset, Mapping) or "path" not in dataset:
            raise AssistantToolError("Experiment dataset.path is required.")
        _resolve_within(dataset["path"], self.data_roots)
        validate_run_spec(bounded)
        return {"valid": True, "tool_version": __version__}

    def run_experiment(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Run a validated public experiment and return bounded result evidence."""
        bounded = _bounded_spec(spec, self.limits)
        dataset = bounded.get("dataset")
        if not isinstance(dataset, Mapping) or "path" not in dataset:
            raise AssistantToolError("Experiment dataset.path is required.")
        dataset_path = _resolve_within(dataset["path"], self.data_roots)
        normalized = dict(bounded)
        normalized["dataset"] = {**dataset, "path": str(dataset_path)}
        validate_run_spec(normalized)
        state = _run_experiment(normalized, base_directory=dataset_path.parent)
        return {"summary": _state_summary(state), "tool_version": __version__}

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
