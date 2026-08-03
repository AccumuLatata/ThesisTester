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

from thesistester.analytics.walk_forward import normalize_otf_history_policy
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
# These are the session-control defaults used by the public run API before
# canonical confirmations required every execution assumption to be persisted.
# Keep this snapshot immutable: it preserves the semantics of legacy confirmed
# records even if current API defaults evolve.
_LEGACY_BACKTEST_SESSION_DEFAULTS = {
    "flat_by_session_close": False,
    "session_close_time": None,
    "session_timezone": None,
    "no_new_entries_after": None,
}
_WALK_FORWARD_FOLD_MODES = frozenset({"bars", "sessions"})
_WALK_FORWARD_WINDOW_MODES = frozenset({"rolling", "anchored"})
_WALK_FORWARD_OVERLAP_POLICIES = frozenset({"reject", "first", "last"})


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
        if "enabled" not in walk_forward:
            missing.append("walk_forward.enabled")
        if walk_forward.get("enabled", True):
            for key in ("fold_mode", "window_mode", "overlap_policy"):
                if key not in walk_forward:
                    missing.append(f"walk_forward.{key}")
            # Fold sizes are mandatory when enabled: the public run API supplies
            # train/test defaults (e.g. 500/100 bars) that must never be inferred
            # for a confirmed assistant RunSpec.
            fold_mode = walk_forward.get("fold_mode")
            if fold_mode == "bars":
                for key in ("train_bars", "test_bars", "step_bars"):
                    if key not in walk_forward:
                        missing.append(f"walk_forward.{key}")
            elif fold_mode == "sessions":
                for key in ("train_sessions", "test_sessions", "step_sessions"):
                    if key not in walk_forward:
                        missing.append(f"walk_forward.{key}")
    if missing:
        raise ValueError(f"Canonical RunSpec requires explicit assumptions: {', '.join(missing)}.")
    return spec


def map_thesis_choices_to_run_spec(*, name: str, choices: Mapping[str, Any]) -> dict[str, Any]:
    """Compile supported structured choices into one canonical executable RunSpec.

    This boundary deliberately rejects narrative-only fields.  A value either
    maps to the public API schema or remains a clarification; it is never
    persisted as an executable-looking but ignored "ghost" assumption.  The
    explicit ``name`` argument is authoritative so a previously confirmed
    RunSpec can be safely recompiled after its thesis is renamed.
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


def map_persisted_confirmed_run_spec(*, name: str, choices: Mapping[str, Any]) -> dict[str, Any]:
    """Compile a confirmed record, preserving historical session defaults.

    Confirmations written before the canonical session-control contract were
    executable because the public run API supplied these defaults at execution
    time. Hydrate only those historical omissions before applying the current
    canonical validator; all other incomplete or unsupported choices still
    fail closed.
    """
    if not isinstance(choices, Mapping):
        raise ValueError("Research choices must be an object.")
    persisted_choices = deepcopy(dict(choices))
    backtest = persisted_choices.get("backtest")
    if isinstance(backtest, Mapping):
        persisted_choices["backtest"] = {
            **_LEGACY_BACKTEST_SESSION_DEFAULTS,
            **deepcopy(dict(backtest)),
        }
    return map_thesis_choices_to_run_spec(name=name, choices=persisted_choices)


def normalize_setup_level_selection(
    selected_levels: Any,
    *,
    previous_min: Any = 1,
    previous_max: Any = None,
) -> tuple[list[str], int, int]:
    """Normalize confluence columns and clamp confluence bounds to their count.

    An empty selection fails closed: confluence bounds must never claim one or
    more levels when no executable level columns were provided.
    """
    if isinstance(selected_levels, str):
        levels = [item.strip() for item in selected_levels.split(",") if item.strip()]
    elif isinstance(selected_levels, list):
        levels = [str(item).strip() for item in selected_levels if str(item).strip()]
    else:
        raise ValueError("Confluence levels must be a comma-separated string or list.")
    if not levels:
        raise ValueError("Confluence levels must include at least one level column.")
    level_count = len(levels)
    try:
        prior_min = int(previous_min)
        prior_max = int(previous_max if previous_max is not None else level_count)
    except (TypeError, ValueError):
        prior_min, prior_max = 1, level_count
    min_confluences = min(max(1, prior_min), level_count)
    max_confluences = min(max(min_confluences, prior_max), level_count)
    return levels, min_confluences, max_confluences


def normalize_walk_forward_controls(
    *,
    enabled: bool,
    train_sessions: Any = 20,
    test_sessions: Any = 5,
    step_sessions: Any = 5,
    train_bars: Any = 500,
    test_bars: Any = 100,
    step_bars: Any = 100,
    fold_mode: str = "sessions",
    window_mode: str = "rolling",
    overlap_policy: str = "reject",
    otf_history_policy: str | None = None,
    ranking_metric: str | None = None,
    min_train_trades: Any = None,
    stop_loss_ticks_values: list[float] | None = None,
    take_profit_ticks_values: list[float] | None = None,
) -> dict[str, Any]:
    """Build an explicit walk-forward draft section for assistant controls.

    Disabled walk-forward persists only the opt-out flag. Enabled walk-forward
    requires every canonical assumption field so UI drafts remain confirmation-
    eligible without silent API defaults. Fold sizes follow ``fold_mode``.
    Missing ``otf_history_policy`` resolves to ``fold_local``; unsupported
    values raise and are never silently replaced.
    """
    if not enabled:
        return {"enabled": False}
    if fold_mode not in _WALK_FORWARD_FOLD_MODES:
        raise ValueError("walk_forward.fold_mode must be 'bars' or 'sessions'.")
    if window_mode not in _WALK_FORWARD_WINDOW_MODES:
        raise ValueError("walk_forward.window_mode must be 'rolling' or 'anchored'.")
    if overlap_policy not in _WALK_FORWARD_OVERLAP_POLICIES:
        raise ValueError("walk_forward.overlap_policy must be 'reject', 'first', or 'last'.")
    try:
        resolved_otf_history_policy = normalize_otf_history_policy(otf_history_policy)
    except ValueError as exc:
        raise ValueError(
            "walk_forward.otf_history_policy must be 'fold_local' or 'causal_prefix'."
        ) from exc
    payload: dict[str, Any] = {
        "enabled": True,
        "fold_mode": fold_mode,
        "window_mode": window_mode,
        "overlap_policy": overlap_policy,
        "otf_history_policy": resolved_otf_history_policy,
    }
    size_label = "session counts" if fold_mode == "sessions" else "bar counts"
    try:
        if fold_mode == "sessions":
            train = int(train_sessions)
            test = int(test_sessions)
            step = int(step_sessions)
            payload.update(
                {
                    "train_sessions": train,
                    "test_sessions": test,
                    "step_sessions": step,
                }
            )
        else:
            train = int(train_bars)
            test = int(test_bars)
            step = int(step_bars)
            payload.update(
                {
                    "train_bars": train,
                    "test_bars": test,
                    "step_bars": step,
                }
            )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Walk-forward {size_label} must be positive integers.") from exc
    if min(train, test, step) < 1:
        raise ValueError(f"Walk-forward {size_label} must be positive integers.")
    if ranking_metric is not None:
        payload["ranking_metric"] = ranking_metric
    if min_train_trades is not None:
        try:
            min_trades = int(min_train_trades)
        except (TypeError, ValueError) as exc:
            raise ValueError("walk_forward.min_train_trades must be a positive integer.") from exc
        if min_trades < 1:
            raise ValueError("walk_forward.min_train_trades must be a positive integer.")
        payload["min_train_trades"] = min_trades
    if stop_loss_ticks_values is not None:
        payload["stop_loss_ticks_values"] = list(stop_loss_ticks_values)
    if take_profit_ticks_values is not None:
        payload["take_profit_ticks_values"] = list(take_profit_ticks_values)
    return payload


def compile_thesis(prompt: str, *, choices: Mapping[str, Any] | None = None) -> ThesisDraft:
    """Create a deterministic draft and name missing executable definitions.

    A required section must be a non-empty mapping so a confirmation-ready
    draft is eligible for canonical RunSpec mapping. Narrative LLM hints remain
    available only while deriving clarifications; they are never staged as
    executable choices and never suppress structured-section clarifications.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Thesis prompt must be a non-empty string.")
    selected = dict(choices or {})
    text = prompt.lower()

    unresolved: list[str] = []
    required = {
        "dataset": "Select a dataset and instrument.",
        "setup": "Define setup levels, trigger, direction, and tolerance.",
        "backtest": "Define costs, exposure, intrabar, and session assumptions.",
    }
    for key, question in required.items():
        if not isinstance(selected.get(key), Mapping) or not selected[key]:
            unresolved.append(question)
    # Clarifications consult only staged executable sections. Legacy flat keys
    # such as session_vwap_anchor / confluence_tolerance_ticks are ignored.
    if re.search(r"\bdvwap\b", text):
        levels = selected.get("levels")
        if not isinstance(levels, Mapping) or not levels.get("session_vwap_enabled"):
            unresolved.append("Enable developing RTH VWAP for the dVWAP thesis.")
    if re.search(r"\bsma\b", text) or "moving average" in text:
        setup = selected.get("setup")
        if not isinstance(setup, Mapping) or "tolerance_ticks" not in setup:
            unresolved.append("Define the SMA confluence tolerance in ticks.")
    return ThesisDraft(
        prompt=prompt.strip(),
        normalized_run_spec={
            key: deepcopy(selected[key]) for key in _CANONICAL_CHOICE_KEYS if key in selected
        },
        unresolved_assumptions=tuple(unresolved),
    )
