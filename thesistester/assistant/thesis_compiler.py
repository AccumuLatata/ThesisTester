"""Deterministic thesis drafting and ambiguity detection.

This module intentionally does not execute experiments or call a language model.
It turns explicit structured choices plus user prose into a reviewable draft.
"""

from __future__ import annotations

import re
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from thesistester.api import validate_run_spec

COMPILER_VERSION = "2"
RUN_SPEC_DRAFT_SCHEMA_VERSION = 1
_CANONICAL_CHOICE_KEYS = {
    "name",
    "dataset",
    "levels",
    "setup",
    "backtest",
    "grid",
    "validation",
    "walk_forward",
}


@dataclass(frozen=True)
class ThesisDraft:
    """A non-executable research-plan draft awaiting user confirmation."""

    prompt: str
    normalized_run_spec: dict[str, Any]
    unresolved_assumptions: tuple[str, ...]

    @property
    def ready_for_confirmation(self) -> bool:
        return not self.unresolved_assumptions


@dataclass(frozen=True)
class StructuredThesisChoices:
    """Typed executable choices; narrative-only fields are intentionally excluded."""

    schema_version: ClassVar[int] = RUN_SPEC_DRAFT_SCHEMA_VERSION
    dataset: dict[str, Any]
    levels: dict[str, Any]
    setup: dict[str, Any]
    backtest: dict[str, Any]
    grid: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    walk_forward: dict[str, Any] | None = None

    @classmethod
    def from_mapping(cls, choices: Mapping[str, Any]) -> StructuredThesisChoices:
        """Create typed choices, normalizing an omitted levels section to empty."""
        required = ("dataset", "setup", "backtest")
        missing = [key for key in required if not isinstance(choices.get(key), Mapping)]
        if missing:
            raise ValueError(f"Structured choices require objects: {', '.join(missing)}.")
        levels = choices.get("levels", {})
        if not isinstance(levels, Mapping):
            raise ValueError("Structured choices require objects: levels.")
        optional = {}
        for key in ("grid", "validation", "walk_forward"):
            value = choices.get(key)
            if value is not None and not isinstance(value, Mapping):
                raise ValueError(f"{key} must be an object when provided.")
            optional[key] = dict(value) if value is not None else None
        return cls(
            dataset=dict(choices["dataset"]),
            levels=dict(levels),
            setup=dict(choices["setup"]),
            backtest=dict(choices["backtest"]),
            **optional,
        )

    def to_mapping(self) -> dict[str, Any]:
        result = {
            "dataset": deepcopy(self.dataset),
            "levels": deepcopy(self.levels),
            "setup": deepcopy(self.setup),
            "backtest": deepcopy(self.backtest),
        }
        for key in ("grid", "validation", "walk_forward"):
            value = getattr(self, key)
            if value is not None:
                result[key] = deepcopy(value)
        return result

    def canonical_json(self) -> str:
        return json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"))


def compile_run_spec(*, name: str, choices: Mapping[str, Any]) -> dict[str, Any]:
    """Build and validate an executable public experiment specification.

    The caller must provide explicit API sections; this function never infers
    execution assumptions from prose.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Run name must be a non-empty string.")
    if not isinstance(choices, Mapping):
        raise ValueError("Research choices must be an object.")
    required = ("dataset", "setup", "backtest")
    missing = [key for key in required if key not in choices]
    if missing:
        raise ValueError(f"Executable research choices require: {', '.join(missing)}.")
    spec = {
        "name": name.strip(),
        "dataset": deepcopy(choices["dataset"]),
        "levels": deepcopy(choices.get("levels", {})),
        "setup": deepcopy(choices["setup"]),
        "backtest": deepcopy(choices["backtest"]),
    }
    for optional in ("grid", "validation", "walk_forward"):
        if optional in choices:
            spec[optional] = deepcopy(choices[optional])
    validate_run_spec(spec)
    return spec


def compile_canonical_run_spec(*, name: str, choices: Mapping[str, Any]) -> dict[str, Any]:
    """Compile only fully explicit research assumptions into an executable spec."""
    typed_choices = StructuredThesisChoices.from_mapping(choices)
    spec = compile_run_spec(name=name, choices=typed_choices.to_mapping())
    dataset = spec["dataset"]
    backtest = spec["backtest"]
    setup = spec["setup"]
    missing: list[str] = []
    if not dataset.get("instrument"):
        missing.append("dataset.instrument")
    for key in (
        "commission_per_side",
        "slippage_ticks",
        "exposure_policy",
        "intrabar_model",
        "flat_by_session_close",
        "session_close_time",
        "session_timezone",
        "no_new_entries_after",
    ):
        if key not in backtest:
            missing.append(f"backtest.{key}")
    for key in ("trigger", "tolerance_ticks", "selected_levels"):
        if key not in setup:
            missing.append(f"setup.{key}")
    validation = spec.get("validation")
    if isinstance(validation, Mapping) and "random_state" not in validation:
        missing.append("validation.random_state")
    grid = spec.get("grid")
    if isinstance(grid, Mapping) and grid.get("enabled", True):
        for key in ("ranking_metric", "min_trades"):
            if key not in grid:
                missing.append(f"grid.{key}")
    walk_forward = spec.get("walk_forward")
    if isinstance(walk_forward, Mapping):
        for key in ("enabled", "fold_mode", "window_mode", "overlap_policy"):
            if key not in walk_forward:
                missing.append(f"walk_forward.{key}")
    if missing:
        raise ValueError(f"Canonical RunSpec requires explicit assumptions: {', '.join(missing)}.")
    return spec


def map_thesis_choices_to_run_spec(*, name: str, choices: Mapping[str, Any]) -> dict[str, Any]:
    """Compile supported structured choices into one canonical executable RunSpec.

    This boundary deliberately rejects narrative-only fields.  A value either
    maps to the public API schema or remains a clarification; it is never
    persisted as an executable-looking but ignored "ghost" assumption.
    """
    if not isinstance(choices, Mapping):
        raise ValueError("Research choices must be an object.")
    unknown = sorted(set(choices) - _CANONICAL_CHOICE_KEYS)
    if unknown:
        raise ValueError(
            "Unsupported non-executable research choices: "
            + ", ".join(unknown)
            + ". Use structured executable controls instead."
        )
    supplied_name = choices.get("name")
    if supplied_name is not None and supplied_name != name.strip():
        raise ValueError("Research choices name must match the selected thesis name.")
    canonical_choices = {
        key: deepcopy(choices[key])
        for key in ("dataset", "levels", "setup", "backtest", "grid", "validation", "walk_forward")
        if key in choices
    }
    setup = canonical_choices.get("setup")
    dataset = canonical_choices.get("dataset")
    if isinstance(setup, Mapping) and isinstance(dataset, Mapping):
        setup = dict(setup)
        if "instrument" not in setup and dataset.get("instrument"):
            # This is a deterministic consistency binding, not an instrument
            # default: the canonical validator verifies the values match.
            setup["instrument"] = dataset["instrument"]
        selected_levels = setup.get("selected_levels")
        if isinstance(selected_levels, str):
            setup["selected_levels"] = [selected_levels]
        canonical_choices["setup"] = setup
    return compile_canonical_run_spec(name=name, choices=canonical_choices)


def compile_thesis(prompt: str, *, choices: Mapping[str, Any] | None = None) -> ThesisDraft:
    """Create a deterministic draft and name missing executable definitions."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Thesis prompt must be a non-empty string.")
    selected = dict(choices or {})
    text = prompt.lower()

    def has_choice(key: str) -> bool:
        value = selected.get(key)
        if isinstance(value, str):
            return bool(value.strip())
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    unresolved: list[str] = []
    required = {
        "dataset": "Select a dataset and instrument.",
        "setup": "Define setup levels, trigger, direction, and tolerance.",
        "backtest": "Define costs, exposure, intrabar, and session assumptions.",
    }
    for key, question in required.items():
        if not isinstance(selected.get(key), Mapping):
            unresolved.append(question)
    if re.search(r"\bdvwap\b", text) and not has_choice("session_vwap_anchor"):
        levels = selected.get("levels")
        if not isinstance(levels, Mapping) or not levels.get("session_vwap_enabled"):
            unresolved.append("Enable developing RTH VWAP for the dVWAP thesis.")
    if (re.search(r"\bsma\b", text) or "moving average" in text) and not has_choice(
        "confluence_tolerance_ticks"
    ):
        setup = selected.get("setup")
        if not isinstance(setup, Mapping) or "tolerance_ticks" not in setup:
            unresolved.append("Define the SMA confluence tolerance in ticks.")
    return ThesisDraft(
        prompt=prompt.strip(),
        normalized_run_spec=selected,
        unresolved_assumptions=tuple(unresolved),
    )
