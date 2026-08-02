"""Deterministic thesis drafting and ambiguity detection.

This module intentionally does not execute experiments or call a language model.
It turns explicit structured choices plus user prose into a reviewable draft.
"""

from __future__ import annotations

import re
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from thesistester.api import validate_run_spec

COMPILER_VERSION = "1"


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
    for key in ("commission_per_side", "slippage_ticks", "exposure_policy", "intrabar_model"):
        if key not in backtest:
            missing.append(f"backtest.{key}")
    for key in ("trigger", "tolerance_ticks", "selected_levels"):
        if key not in setup:
            missing.append(f"setup.{key}")
    validation = spec.get("validation")
    if isinstance(validation, Mapping) and "random_state" not in validation:
        missing.append("validation.random_state")
    if missing:
        raise ValueError(f"Canonical RunSpec requires explicit assumptions: {', '.join(missing)}.")
    return spec


def map_thesis_choices_to_run_spec(*, name: str, choices: Mapping[str, Any]) -> dict[str, Any]:
    """Map supported structured thesis fields into canonical public API sections."""
    if all(isinstance(choices.get(key), Mapping) for key in ("dataset", "setup", "backtest")):
        canonical_choices = dict(choices)
        canonical_choices.setdefault("levels", {})
        return compile_canonical_run_spec(name=name, choices=canonical_choices)
    required = ("dataset_path", "instrument", "selected_levels", "trigger", "tolerance_ticks")
    missing = [
        key
        for key in required
        if key not in choices
        or choices[key] is None
        or (isinstance(choices[key], str) and not choices[key].strip())
    ]
    if missing:
        raise ValueError(f"Thesis choices require: {', '.join(missing)}.")
    instrument = str(choices["instrument"])
    raw_levels = choices["selected_levels"]
    selected_levels = [raw_levels] if isinstance(raw_levels, str) else list(raw_levels)
    if not selected_levels or any(
        not isinstance(level, str) or not level.strip() for level in selected_levels
    ):
        raise ValueError("selected_levels must contain one or more non-empty level names.")
    setup = {
        "name": name,
        "description": str(choices.get("description", "")),
        "instrument": instrument,
        "selected_levels": selected_levels,
        "tolerance_ticks": choices["tolerance_ticks"],
        "min_confluences": choices.get("min_confluences", 1),
        "max_confluences": choices.get("max_confluences", max(1, len(selected_levels))),
        "naked_only": choices.get("naked_only", False),
        "naked_requirement": choices.get("naked_requirement", "any"),
        "trigger": choices["trigger"],
        "trigger_timeframe": choices.get("trigger_timeframe", "base"),
        "direction": choices.get("direction", "both"),
        "confluence_mode": choices.get("confluence_mode", "global_cluster"),
        "anchor_level": choices.get("anchor_level"),
        "confluence_rules": choices.get("confluence_rules", []),
        "min_valid_confluences": choices.get("min_valid_confluences", 1),
        "trigger_params": choices.get("trigger_params", {}),
        "otf_filter": choices.get("otf_filter"),
    }
    canonical = {
        "dataset": {"path": choices["dataset_path"], "instrument": instrument},
        "levels": dict(choices.get("levels", {})),
        "setup": setup,
        "backtest": dict(choices.get("backtest", {})),
    }
    for key in ("grid", "validation", "walk_forward"):
        if key in choices:
            canonical[key] = dict(choices[key])
    return compile_canonical_run_spec(name=name, choices=canonical)


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
        "trend_rule": "Define the measurable trend rule.",
        "trigger": "Define the entry trigger and tick tolerance.",
        "session_window": "Define the exact exchange-time session window.",
        "success_criteria": "Define performance, sample-size, and OOS success criteria.",
    }
    for key, question in required.items():
        if not has_choice(key):
            unresolved.append(question)
    if re.search(r"\bdvwap\b", text) and not has_choice("session_vwap_anchor"):
        unresolved.append("Confirm dVWAP_RTH and its RTH-only availability.")
    if (re.search(r"\bsma\b", text) or "moving average" in text) and not has_choice(
        "confluence_tolerance_ticks"
    ):
        unresolved.append("Define the SMA confluence tolerance in ticks.")
    if re.search(r"\b(?:stops?|targets?|sl|take[- ]profit)\b", text) and not has_choice(
        "selection_protocol"
    ):
        unresolved.append("Define SL/TP candidate grid and OOS selection protocol.")
    return ThesisDraft(
        prompt=prompt.strip(),
        normalized_run_spec=selected,
        unresolved_assumptions=tuple(unresolved),
    )
