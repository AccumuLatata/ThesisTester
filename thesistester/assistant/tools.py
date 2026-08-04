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
    run_portfolio_analysis,
    run_time_analysis,
    validate_roll_assumptions,
)
from thesistester.api import _VALIDATION_DEFAULTS
from thesistester.api import run_experiment as _run_experiment
from thesistester.api import validate_run_spec
from thesistester.assistant.explainer import build_evidence_packet
from thesistester.persistence.local_store import (
    clear_backtest_defaults,
    clear_grid_defaults,
    get_backtest_defaults,
    get_grid_defaults,
    list_datasets,
    list_saved_setups,
    load_setup,
    load_dataset,
    save_backtest_defaults,
    save_grid_defaults,
    save_setup,
)
from thesistester.reporting import build_markdown_report, build_research_artifact, to_jsonable
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


def _resolved_paths(spec: Mapping[str, Any]) -> dict[str, str]:
    dataset = spec.get("dataset")
    if not isinstance(dataset, Mapping):
        return {}
    paths = {"dataset.path": str(dataset["path"])}
    if dataset.get("subtimeframe_path") is not None:
        paths["dataset.subtimeframe_path"] = str(dataset["subtimeframe_path"])
    return paths


def _seed_snapshot(spec: Mapping[str, Any]) -> dict[str, Any]:
    seeds: dict[str, Any] = {}
    validation = spec.get("validation")
    if isinstance(validation, Mapping):
        if "random_state" in validation:
            seeds["validation.random_state"] = validation["random_state"]
        for section in ("monte_carlo", "overfitting", "noise", "sensitivity"):
            nested = validation.get(section)
            if isinstance(nested, Mapping) and "random_state" in nested:
                seeds[f"validation.{section}.random_state"] = nested["random_state"]
    return seeds


def _require_expected_hash(expected_hash: Any) -> str:
    if not isinstance(expected_hash, str) or not expected_hash.strip():
        raise AssistantToolError("Bundle load requires a non-empty expected hash.")
    return expected_hash.strip()


def _read_verified_bundle(
    bundle_path: str | Path,
    roots: tuple[Path, ...],
    *,
    expected_hash: str | None = None,
    require_hash: bool = False,
) -> tuple[Path, bytes, dict[str, Any]]:
    path = _resolve_within(bundle_path, roots)
    raw = path.read_bytes()
    digest = canonical_bundle_hash(raw)
    if require_hash or expected_hash is not None:
        # Provenance-gated loads fail closed: a missing/blank hash must never
        # silently skip integrity verification.
        expected = _require_expected_hash(expected_hash)
        if digest != expected:
            raise AssistantToolError("Bundle hash does not match recorded run provenance.")
    payload = load_research_bundle(raw)
    session_values = payload.get("session_values")
    if not isinstance(session_values, dict):
        raise AssistantToolError("Bundle payload is missing session values.")
    return path, raw, session_values


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


def _assert_summary_has_no_dataframes(value: Any, *, path: str = "<root>") -> None:
    """Fail closed when a page summary embeds a DataFrame at any depth."""
    import pandas as pd

    if isinstance(value, pd.DataFrame):
        raise AssistantToolError(f"Page summary path {path!r} must not contain a DataFrame.")
    if isinstance(value, Mapping):
        for key, nested in value.items():
            child = f"{path}.{key}" if path != "<root>" else str(key)
            _assert_summary_has_no_dataframes(nested, path=child)
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_summary_has_no_dataframes(nested, path=f"{path}[{index}]")


def _assert_bundle_compatible_with_run_spec(
    session_values: Mapping[str, Any],
    run_spec: Mapping[str, Any],
) -> None:
    """Fail closed when a verified bundle cannot serve the exported RunSpec lineage."""
    if not isinstance(run_spec, Mapping):
        raise AssistantToolError("run_spec must be an object.")
    dataset = run_spec.get("dataset")
    setup = run_spec.get("setup")
    backtest = run_spec.get("backtest")
    if not isinstance(dataset, Mapping) or not isinstance(setup, Mapping):
        raise AssistantToolError("run_spec requires dataset and setup objects.")
    if not isinstance(backtest, Mapping):
        raise AssistantToolError("run_spec requires a backtest object.")

    import pandas as pd

    for key in ("data", "levels", "session_levels", "trades", "equity_curve"):
        frame = session_values.get(key)
        if not isinstance(frame, pd.DataFrame):
            raise AssistantToolError(
                f"Classic registration bundle is missing required frame '{key}'."
            )
    levels_settings = session_values.get("levels_settings")
    if not isinstance(levels_settings, Mapping):
        raise AssistantToolError(
            "Classic registration bundle is missing levels_settings provenance."
        )
    page_setup = session_values.get("last_signal_setup")
    if not isinstance(page_setup, Mapping):
        page_setup = session_values.get("setup_config")
    if not isinstance(page_setup, Mapping):
        raise AssistantToolError("Classic registration bundle is missing setup provenance.")

    spec_instrument = dataset.get("instrument")
    page_instrument = session_values.get("instrument") or page_setup.get("instrument")
    if (
        isinstance(spec_instrument, str)
        and isinstance(page_instrument, str)
        and spec_instrument.strip()
        and page_instrument.strip()
        and spec_instrument != page_instrument
    ):
        raise AssistantToolError(
            "Bundle instrument does not match the exported RunSpec dataset.instrument."
        )
    spec_trigger = setup.get("trigger")
    page_trigger = page_setup.get("trigger")
    if (
        isinstance(spec_trigger, str)
        and isinstance(page_trigger, str)
        and spec_trigger.strip()
        and page_trigger.strip()
        and spec_trigger != page_trigger
    ):
        raise AssistantToolError(
            "Bundle setup trigger does not match the exported RunSpec setup.trigger."
        )


class AssistantTools:
    """Narrow tool surface; no arbitrary Python, shell, or filesystem access."""

    def __init__(self, *, data_roots: tuple[Path, ...], limits: ToolLimits = ToolLimits()) -> None:
        self.data_roots = tuple(root.resolve() for root in data_roots)
        self.limits = limits

    def list_local_datasets(self) -> list[dict[str, Any]]:
        """List persisted datasets without reading arbitrary filesystem paths."""
        return to_jsonable(list_datasets())

    def list_saved_setup_summaries(self, *, dataset_id: str | None = None) -> list[dict[str, Any]]:
        """List persisted setup metadata for assistant selection without mutation."""
        return to_jsonable(list_saved_setups(dataset_id=dataset_id))

    def load_saved_setup(self, setup_id: str) -> dict[str, Any]:
        """Load one persisted setup configuration for review or explicit reuse."""
        return to_jsonable(load_setup(setup_id))

    def save_saved_setup(
        self, setup: Mapping[str, Any], *, instrument: str | None = None
    ) -> dict[str, Any]:
        """Persist one validated setup configuration through the local store."""
        return to_jsonable(save_setup(dict(setup), instrument=instrument))

    def get_execution_defaults(self) -> dict[str, Any]:
        """Return persisted backtest/grid defaults without mutating them."""
        return {
            "backtest": to_jsonable(get_backtest_defaults()),
            "grid": to_jsonable(get_grid_defaults()),
        }

    def save_backtest_execution_defaults(self, defaults: dict[str, Any]) -> None:
        """Persist explicit backtest defaults without altering grid defaults."""
        save_backtest_defaults(defaults)

    def save_grid_execution_defaults(self, defaults: dict[str, Any]) -> None:
        """Persist explicit grid defaults without altering backtest defaults."""
        save_grid_defaults(defaults)

    def clear_backtest_execution_defaults(self) -> None:
        """Clear backtest defaults without altering grid defaults."""
        clear_backtest_defaults()

    def clear_grid_execution_defaults(self) -> None:
        """Clear grid defaults without altering backtest defaults."""
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
        state = _run_experiment(
            normalized,
            base_directory=dataset_path.parent,
            execution_origin="assistant",
            cache_policy="read_write",
        )
        return {
            "summary": _state_summary(state),
            "tool_version": __version__,
            "execution_origin": state.get("execution_origin", "assistant"),
            "cache_provenance": to_jsonable(state.get("cache_provenance")),
        }

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
            normalized,
            base_directory=Path(normalized["dataset"]["path"]).parent,
            execution_origin="assistant",
            cache_policy="read_write",
        )
        bundle = build_research_bundle(state)
        path.write_bytes(bundle)
        return {
            "summary": _state_summary(state),
            "bundle_path": str(path),
            "canonical_bundle_hash": canonical_bundle_hash(bundle),
            "dataset_fingerprint": to_jsonable(state.get("levels_data_fingerprint")),
            "data_identity": to_jsonable(state.get("data_identity")),
            "levels_identity": to_jsonable(state.get("levels_identity")),
            "execution_origin": state.get("execution_origin", "assistant"),
            "cache_provenance": to_jsonable(state.get("cache_provenance")),
            "tool_version": __version__,
            "effective_configuration": to_jsonable(normalized),
            "resolved_paths": _resolved_paths(normalized),
            "resource_limits": {
                "max_grid_cells": self.limits.max_grid_cells,
                "max_simulations": self.limits.max_simulations,
                "max_walk_forward_matrix_cells": self.limits.max_walk_forward_matrix_cells,
            },
            "seeds": _seed_snapshot(normalized),
        }

    def load_bundle_summary(self, bundle_path: str | Path, *, expected_hash: str) -> dict[str, Any]:
        """Load a bundle beneath an allowed root and return compact evidence."""
        path, raw, session_values = _read_verified_bundle(
            bundle_path,
            self.data_roots,
            expected_hash=expected_hash,
            require_hash=True,
        )
        return {
            "bundle_path": str(path),
            "canonical_bundle_hash": canonical_bundle_hash(raw),
            "summary": _state_summary(session_values),
        }

    def _page_summary_from_bundle(
        self,
        bundle_path: str | Path,
        *,
        expected_hash: str,
        summarizer,
        summary_key: str,
        summarizer_kwargs: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Hash-verified bundle load → bounded page summary (CAI-9).

        Summary keys match evidence-packet ``results.*`` paths so inspect and
        Explain share the same hierarchy for proposal evidence_paths.
        """
        path, raw, session_values = _read_verified_bundle(
            bundle_path,
            self.data_roots,
            expected_hash=expected_hash,
            require_hash=True,
        )
        kwargs: dict[str, Any] = dict(summarizer_kwargs or {})
        if (
            provenance is not None
            and summary_key == "backtest_page_summary"
            and "cost_assumptions" not in kwargs
        ):
            # Align backtest caveats with build_evidence_packet cost exposure.
            from thesistester.assistant.explainer import (
                _cost_exposure_assumptions,
                _effective_configuration,
            )

            config = _effective_configuration(dict(provenance), session_values)
            kwargs["cost_assumptions"] = _cost_exposure_assumptions(config, session_values)
        summary = summarizer(session_values, **kwargs)
        if not isinstance(summary, dict):
            raise AssistantToolError("Page summary must be a JSON object.")
        # Fail closed if a summarizer accidentally embeds a DataFrame at any depth.
        _assert_summary_has_no_dataframes(summary)
        return {
            "bundle_path": str(path),
            "canonical_bundle_hash": canonical_bundle_hash(raw),
            summary_key: to_jsonable(summary),
        }

    def summarize_bundle_levels(
        self, bundle_path: str | Path, *, expected_hash: str
    ) -> dict[str, Any]:
        """Bounded levels summary from one hash-verified research bundle."""
        from thesistester.assistant.page_summaries import summarize_levels_state

        return self._page_summary_from_bundle(
            bundle_path,
            expected_hash=expected_hash,
            summarizer=summarize_levels_state,
            summary_key="levels_summary",
        )

    def summarize_bundle_signals(
        self, bundle_path: str | Path, *, expected_hash: str
    ) -> dict[str, Any]:
        """Bounded signals summary from one hash-verified research bundle."""
        from thesistester.assistant.page_summaries import summarize_signals_state

        return self._page_summary_from_bundle(
            bundle_path,
            expected_hash=expected_hash,
            summarizer=summarize_signals_state,
            summary_key="signals_summary",
        )

    def summarize_bundle_backtest(
        self,
        bundle_path: str | Path,
        *,
        expected_hash: str,
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Bounded backtest KPI/cost/intrabar summary from one verified bundle."""
        from thesistester.assistant.page_summaries import summarize_backtest_state

        return self._page_summary_from_bundle(
            bundle_path,
            expected_hash=expected_hash,
            summarizer=summarize_backtest_state,
            # Match evidence packet results.backtest_page_summary path.
            summary_key="backtest_page_summary",
            provenance=provenance,
        )

    def summarize_bundle_grid(
        self, bundle_path: str | Path, *, expected_hash: str
    ) -> dict[str, Any]:
        """Bounded grid selection summary from one hash-verified research bundle."""
        from thesistester.assistant.page_summaries import summarize_grid_state

        return self._page_summary_from_bundle(
            bundle_path,
            expected_hash=expected_hash,
            summarizer=summarize_grid_state,
            summary_key="grid_summary",
        )

    def summarize_bundle_validation(
        self, bundle_path: str | Path, *, expected_hash: str
    ) -> dict[str, Any]:
        """Bounded validation/OOS summary from one hash-verified research bundle."""
        from thesistester.assistant.page_summaries import summarize_validation_state

        return self._page_summary_from_bundle(
            bundle_path,
            expected_hash=expected_hash,
            summarizer=summarize_validation_state,
            # Avoid colliding with classic analytics validation_summary key.
            summary_key="validation_page_summary",
        )

    def validate_classic_page_proposal(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a classic page proposal draft without applying it."""
        from thesistester.classic_proposal import validate_classic_proposal

        draft = payload.get("draft_patch")
        evidence_paths = payload.get("evidence_paths")
        return validate_classic_proposal(
            target_page=str(payload.get("target_page", "")),
            draft_patch=draft if isinstance(draft, Mapping) else {},
            note=str(payload.get("note", "")),
            evidence_paths=evidence_paths if isinstance(evidence_paths, (list, tuple)) else None,
        )

    def inspect_execution_cache(
        self,
        *,
        kind: str | None = None,
        limit: int = 200,
        store_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Return bounded execution-artifact inspection + store-level stats (CAI-10)."""
        from thesistester.persistence import (
            get_execution_cache_stats,
            list_execution_artifacts,
        )

        try:
            artifacts = list_execution_artifacts(store_root=store_root, kind=kind, limit=limit)
            stats = get_execution_cache_stats(store_root)
        except ValueError as exc:
            raise AssistantToolError(str(exc)) from exc
        return to_jsonable({"stats": stats, "artifacts": artifacts})

    def delete_execution_cache_artifact(
        self,
        *,
        kind: str,
        artifact_key: str,
        store_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Delete one internal execution artifact; next read is a cold miss."""
        from thesistester.persistence import delete_execution_artifact

        try:
            return to_jsonable(
                delete_execution_artifact(
                    kind=kind, artifact_key=artifact_key, store_root=store_root
                )
            )
        except ValueError as exc:
            raise AssistantToolError(str(exc)) from exc

    def evict_execution_cache(
        self,
        *,
        max_entries: int | None = None,
        max_total_bytes: int | None = None,
        max_age_seconds: int | None = None,
        store_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """Bounded eviction of internal execution artifacts only."""
        from thesistester.persistence import evict_execution_artifacts

        try:
            return to_jsonable(
                evict_execution_artifacts(
                    store_root=store_root,
                    max_entries=max_entries,
                    max_total_bytes=max_total_bytes,
                    max_age_seconds=max_age_seconds,
                )
            )
        except ValueError as exc:
            raise AssistantToolError(str(exc)) from exc

    def rebind_execution_source_path(
        self,
        *,
        new_source_path: str | Path,
        expected_identity: Mapping[str, Any],
        store_root: str | Path | None = None,
        instrument: str | None = None,
        source_timezone: str | None = None,
        exchange_timezone: str | None = None,
        format_profile: str | None = None,
    ) -> dict[str, Any]:
        """Rebind a source path after content-identity verification."""
        from thesistester.persistence import rebind_source_path
        from thesistester.research_identity import DataIdentity

        path = Path(new_source_path).expanduser().resolve()
        # Require the new source to live under an allowed data root.
        try:
            _resolve_within(path, self.data_roots)
        except Exception as exc:
            raise AssistantToolError(
                f"new_source_path must be inside assistant data roots: {exc}"
            ) from exc
        identity = DataIdentity.from_dict(expected_identity)
        if identity is None:
            raise AssistantToolError("expected_identity is invalid.")
        try:
            binding = rebind_source_path(
                new_source_path=path,
                expected_identity=identity,
                instrument=instrument,
                source_timezone=source_timezone,
                exchange_timezone=exchange_timezone,
                format_profile=format_profile,
                store_root=store_root,
            )
        except ValueError as exc:
            raise AssistantToolError(str(exc)) from exc
        return to_jsonable(
            {
                "binding_key": binding.binding_key,
                "source_content_hash": binding.source_content_hash,
                "data_artifact_key": binding.data_artifact_key,
                "identity": binding.identity.to_dict(),
                "new_source_path": str(path),
            }
        )

    def verify_external_research_bundle(
        self,
        bundle_path: str | Path,
        *,
        expected_hash: str | None = None,
        run_spec: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify a classic-origin bundle for thesis registration (CAI-6).

        Fail-closed on path containment, zip/schema load errors, hash mismatch,
        missing required research sections, or RunSpec incompatibility.
        Does not execute research or mutate thesis records.
        """
        path = _resolve_within(bundle_path, self.data_roots)
        if not path.is_file():
            raise AssistantToolError("Research bundle path does not exist.")
        raw = path.read_bytes()
        digest = canonical_bundle_hash(raw)
        if expected_hash is not None:
            expected = _require_expected_hash(expected_hash)
            if digest != expected:
                raise AssistantToolError("Bundle hash does not match recorded run provenance.")
        try:
            loaded = load_research_bundle(raw)
        except ValueError as exc:
            raise AssistantToolError(f"Research bundle is corrupt or invalid: {exc}") from exc
        session_values = loaded.get("session_values")
        if not isinstance(session_values, dict):
            raise AssistantToolError("Bundle payload is missing session values.")
        manifest = loaded.get("manifest")
        if not isinstance(manifest, Mapping):
            raise AssistantToolError("Bundle payload is missing a manifest.")
        included = manifest.get("included")
        if not isinstance(included, Mapping):
            raise AssistantToolError("Bundle manifest is missing included sections.")
        required_sections = ("dataset", "levels", "signals", "backtest")
        missing = [section for section in required_sections if not included.get(section)]
        if missing:
            raise AssistantToolError(
                "Classic registration requires bundle sections: "
                + ", ".join(required_sections)
                + f". Missing: {', '.join(missing)}."
            )
        if run_spec is not None:
            _assert_bundle_compatible_with_run_spec(session_values, run_spec)
        return {
            "bundle_path": str(path),
            "canonical_bundle_hash": digest,
            "summary": _state_summary(session_values),
            "included": {key: bool(included.get(key)) for key in included},
            "session_values": session_values,
        }

    def load_verified_bundle_session(
        self, bundle_path: str | Path, *, expected_hash: str
    ) -> dict[str, Any]:
        """Return hash-verified session values for research-page handoff."""
        path, raw, session_values = _read_verified_bundle(
            bundle_path,
            self.data_roots,
            expected_hash=expected_hash,
            require_hash=True,
        )
        return {
            "bundle_path": str(path),
            "canonical_bundle_hash": canonical_bundle_hash(raw),
            "session_values": session_values,
        }

    def render_bundle_markdown_report(self, bundle_path: str | Path, *, expected_hash: str) -> str:
        """Render the established report from a selected portable research bundle."""
        _path, _raw, session_values = _read_verified_bundle(
            bundle_path,
            self.data_roots,
            expected_hash=expected_hash,
            require_hash=True,
        )
        return build_markdown_report(build_research_artifact(session_values))

    def build_bundle_research_artifact(
        self, bundle_path: str | Path, *, expected_hash: str
    ) -> dict[str, Any]:
        """Build a JSON-safe research artifact from one verified portable bundle."""
        _path, _raw, session_values = _read_verified_bundle(
            bundle_path,
            self.data_roots,
            expected_hash=expected_hash,
            require_hash=True,
        )
        return to_jsonable(build_research_artifact(session_values))

    def build_bundle_evidence_packet(
        self,
        bundle_path: str | Path,
        *,
        expected_hash: str,
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build explanation evidence from one hash-verified research bundle."""
        path, raw, session_values = _read_verified_bundle(
            bundle_path,
            self.data_roots,
            expected_hash=expected_hash,
            require_hash=True,
        )
        packet = build_evidence_packet(
            session_values,
            provenance=dict(provenance or {})
            | {
                "bundle_path": str(path),
                "canonical_bundle_hash": canonical_bundle_hash(raw),
            },
        )
        return packet.to_dict()

    def compare_bundle_summaries(
        self,
        bundle_paths: list[str | Path],
        *,
        expected_hashes: list[str],
    ) -> list[dict[str, Any]]:
        """Return independently grounded summaries for explicit bundle choices."""
        if len(bundle_paths) < 2:
            raise AssistantToolError("Select at least two bundles to compare.")
        if len(expected_hashes) != len(bundle_paths):
            raise AssistantToolError("expected_hashes must match bundle_paths.")
        return [
            self.load_bundle_summary(path, expected_hash=expected_hash)
            for path, expected_hash in zip(bundle_paths, expected_hashes, strict=True)
        ]

    def summarize_bundle_time_analysis(
        self,
        bundle_path: str | Path,
        *,
        group_col: str = "entry_rth_segment",
        bucket_timezone: str = "America/New_York",
        min_trades: int = 10,
    ) -> list[dict[str, Any]]:
        """Return bounded descriptive time analysis for a selected research bundle."""
        _path, _raw, session_values = _read_verified_bundle(bundle_path, self.data_roots)
        trades = session_values.get("trades")
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
        _path, _raw, session_values = _read_verified_bundle(bundle_path, self.data_roots)
        data = session_values.get("data")
        signals = session_values.get("signals")
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
                session_timezone=session_values.get("exchange_timezone"),
                eth_start=session_values.get("eth_start"),
                setup_config=session_values.get("setup_config"),
                signal_settings=session_values.get("signal_settings"),
            ).to_dict("records")
        )

    def preview_bundle_resample(
        self, bundle_path: str | Path, *, timeframe: str, max_rows: int = 200
    ) -> list[dict[str, Any]]:
        """Return a bounded resample preview for a selected bundle dataset."""
        _path, _raw, session_values = _read_verified_bundle(bundle_path, self.data_roots)
        data = session_values.get("data")
        if data is None:
            raise AssistantToolError("Bundle does not include a dataset.")
        return to_jsonable(
            preview_resampled_ohlcv(data, timeframe=timeframe, max_rows=max_rows).to_dict("records")
        )

    def validate_bundle_roll_assumptions(
        self,
        bundle_path: str | Path,
        *,
        contract_column: str = "contract",
        roll_method: str = "single_contract",
    ) -> dict[str, Any]:
        """Return roll diagnostics for a selected bundle dataset."""
        _path, _raw, session_values = _read_verified_bundle(bundle_path, self.data_roots)
        data = session_values.get("data")
        if data is None:
            raise AssistantToolError("Bundle does not include a dataset.")
        return to_jsonable(
            validate_roll_assumptions(
                data, contract_column=contract_column, roll_method=roll_method
            )
        )

    def analyze_bundle_portfolio(
        self,
        bundle_paths: list[str | Path],
        *,
        instrument: str,
        expected_hashes: list[str],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze explicitly selected completed-run bundles as a portfolio.

        ``expected_hashes`` must align 1:1 with ``bundle_paths``. Each digest is
        checked against recorded provenance before trades are admitted into
        portfolio metrics.
        """
        if len(bundle_paths) < 2:
            raise AssistantToolError("Portfolio analysis requires at least two bundles.")
        if len(expected_hashes) != len(bundle_paths):
            raise AssistantToolError("expected_hashes must match bundle_paths.")
        setup_trades = {}
        for index, bundle_path in enumerate(bundle_paths, start=1):
            _path, _raw, session_values = _read_verified_bundle(
                bundle_path,
                self.data_roots,
                expected_hash=expected_hashes[index - 1],
                require_hash=True,
            )
            trades = session_values.get("trades")
            if trades is None or trades.empty:
                raise AssistantToolError("Each bundle requires completed trades.")
            setup_trades[f"run_{index}"] = trades
        return to_jsonable(
            run_portfolio_analysis(setup_trades, instrument=instrument, config=config)
        )
