"""Import-time feature detection for current main and farm commit 59a4652.

Hook points verified at ``59a4652`` (see ``HOOK_POINTS`` and the operator
README). The capture scripts import product symbols only through this module
so a renamed internal fails closed instead of silently skipping a field.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable

# Farm production commit the §9 pre-step must also run against.
# Short SHA is the plan's pin; the full SHA is what a shallow CI clone can fetch.
FARM_PRODUCTION_COMMIT = "59a4652"
FARM_PRODUCTION_COMMIT_FULL = "59a4652cdb96ac86da6675633fd57f3e31f803e0"

# Every hook used by capture / stage-trace. Confirmed present at 59a4652
# via ``git show 59a4652:<path>`` (function names, not line numbers).
HOOK_POINTS: tuple[tuple[str, str], ...] = (
    ("thesistester.analytics.overfitting", "vs_random_benchmark"),
    ("thesistester.study.execute", "execute_study_cell"),
    ("thesistester.study.execute", "run_study"),
    ("thesistester.study.execute", "prepare_study_expansion"),
    ("thesistester.study.execute", "random_baseline_fields"),
    ("thesistester.study.schema", "load_study_spec"),
    ("thesistester.study.expand", "expand_study"),
    ("thesistester.api", "_load_15s_primary_experiment_data"),
    ("thesistester.api", "generate_signals"),
    ("thesistester.api", "run_experiment"),
    ("thesistester.engine.intrabar", "prepare_subtimeframe_conservative_context"),
    ("thesistester.engine.backtest", "simulate_trades"),
    ("thesistester.engine.signals", "generate_signals"),
    ("thesistester.research_bundle", "build_research_bundle"),
    ("thesistester.research_bundle", "canonical_bundle_hash"),
)


@dataclass(frozen=True)
class ResolvedHook:
    module_name: str
    attr: str
    module: ModuleType
    value: Any


class CompatError(RuntimeError):
    """A required hook is missing on the imported ``thesistester`` package."""


def import_optional(module_name: str) -> ModuleType | None:
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


def resolve_hook(module_name: str, attr: str) -> ResolvedHook:
    module = import_optional(module_name)
    if module is None:
        raise CompatError(
            f"cannot import {module_name!r} from the active thesistester package; "
            f"required for MW0 capture (also required at {FARM_PRODUCTION_COMMIT})"
        )
    if not hasattr(module, attr):
        raise CompatError(
            f"{module_name}.{attr} is missing on the active thesistester package; "
            f"required for MW0 capture (also required at {FARM_PRODUCTION_COMMIT})"
        )
    return ResolvedHook(
        module_name=module_name,
        attr=attr,
        module=module,
        value=getattr(module, attr),
    )


def resolve_all_hooks() -> dict[str, ResolvedHook]:
    resolved: dict[str, ResolvedHook] = {}
    missing: list[str] = []
    for module_name, attr in HOOK_POINTS:
        key = f"{module_name}.{attr}"
        try:
            resolved[key] = resolve_hook(module_name, attr)
        except CompatError as exc:
            missing.append(str(exc))
    if missing:
        raise CompatError("MW0 hook-point probe failed:\n- " + "\n- ".join(missing))
    return resolved


def patch_aliases(
    *,
    original: Callable[..., Any],
    wrapper: Callable[..., Any],
    aliases: tuple[tuple[str, str], ...],
) -> list[tuple[ModuleType, str, Callable[..., Any]]]:
    """Replace ``original`` at every listed alias. Returns undo records."""
    undo: list[tuple[ModuleType, str, Callable[..., Any]]] = []
    for module_name, attr in aliases:
        module = import_optional(module_name)
        if module is None or not hasattr(module, attr):
            continue
        current = getattr(module, attr)
        if current is original or current is wrapper:
            setattr(module, attr, wrapper)
            undo.append((module, attr, current))
    return undo


def restore_aliases(undo: list[tuple[ModuleType, str, Callable[..., Any]]]) -> None:
    for module, attr, original in undo:
        setattr(module, attr, original)


def package_identity() -> dict[str, str]:
    """Best-effort identity of the imported ``thesistester`` package."""
    module = import_optional("thesistester")
    version = getattr(module, "__version__", "unknown") if module is not None else "missing"
    path = getattr(module, "__file__", "") if module is not None else ""
    return {
        "thesistester_version": str(version),
        "thesistester_file": str(path),
        "farm_production_commit": FARM_PRODUCTION_COMMIT,
    }
