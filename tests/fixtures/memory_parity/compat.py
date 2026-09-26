"""Import-time feature detection for current main and farm commit 59a4652.

Hook points verified at ``59a4652`` (see ``HOOK_POINTS`` and the operator
README). The capture scripts import product symbols only through this module
so a renamed internal fails closed instead of silently skipping a field.

``python -m`` from the MW0 checkout puts that checkout at ``sys.path[0]``,
which would otherwise shadow a ``59a4652`` worktree listed first on
``PYTHONPATH``. The farm §9 pre-step requires that worktree to win, so this
module lifts the first ``PYTHONPATH`` tree that contains ``thesistester/``
ahead of cwd before any product import. A mismatch after import is
``STOP AND REPORT``, not a silent main-vs-main capture.
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
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


def pythonpath_thesistester_roots() -> list[Path]:
    """Return ``PYTHONPATH`` entries that contain a ``thesistester`` package."""
    raw = os.environ.get("PYTHONPATH") or ""
    roots: list[Path] = []
    seen: set[Path] = set()
    for part in raw.split(os.pathsep):
        item = part.strip()
        if not item:
            continue
        try:
            root = Path(item).expanduser().resolve()
        except OSError:
            continue
        if root in seen:
            continue
        if (root / "thesistester").is_dir() or (root / "thesistester.py").is_file():
            seen.add(root)
            roots.append(root)
    return roots


def prefer_pythonpath_thesistester() -> Path | None:
    """Put the first ``PYTHONPATH`` ``thesistester`` tree at ``sys.path[0]``.

    ``python -m tests.fixtures.memory_parity.capture_operator`` from the MW0
    checkout otherwise imports that checkout's ``thesistester`` (cwd wins)
    even when ``PYTHONPATH`` lists a ``59a4652`` worktree first.
    """
    roots = pythonpath_thesistester_roots()
    if not roots:
        return None
    chosen = roots[0]
    chosen_s = str(chosen)

    def _is_chosen(entry: str) -> bool:
        if not entry:
            return False
        try:
            return Path(entry).expanduser().resolve() == chosen
        except OSError:
            return False

    sys.path[:] = [path for path in sys.path if not _is_chosen(path)]
    sys.path.insert(0, chosen_s)
    return chosen


def imported_thesistester_root() -> Path | None:
    """Worktree root of the already-imported ``thesistester`` package, if any."""
    module = sys.modules.get("thesistester")
    if module is None:
        return None
    tes_file = getattr(module, "__file__", None)
    if not tes_file:
        return None
    tes_path = Path(tes_file).resolve()
    package_dir = tes_path.parent
    if tes_path.name == "__init__.py":
        return package_dir.parent
    return package_dir


def assert_imported_thesistester_follows_pythonpath() -> Path | None:
    """Fail closed if ``PYTHONPATH`` selected a tree that is not the import."""
    roots = pythonpath_thesistester_roots()
    if not roots:
        return None
    expected = roots[0]
    imported = imported_thesistester_root()
    if imported is None:
        return expected
    if imported != expected:
        raise CompatError(
            "STOP AND REPORT: PYTHONPATH selects "
            f"{expected} for import thesistester, but the imported package "
            f"resolved to {imported}. The farm §9 59a4652 capture must not "
            "silently use a different checkout (cwd shadows PYTHONPATH under "
            "python -m). Do not compare main to itself."
        )
    return expected


def ensure_thesistester_import_path() -> Path | None:
    """Lift PYTHONPATH, then refuse a shadowed ``thesistester`` import."""
    chosen = prefer_pythonpath_thesistester()
    assert_imported_thesistester_follows_pythonpath()
    return chosen


def import_optional(module_name: str) -> ModuleType | None:
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


def resolve_hook(module_name: str, attr: str) -> ResolvedHook:
    if module_name == "thesistester" or module_name.startswith("thesistester."):
        ensure_thesistester_import_path()
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
    ensure_thesistester_import_path()
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
        "thesistester_root": str(imported_thesistester_root() or ""),
        "pythonpath_thesistester_root": str(
            pythonpath_thesistester_roots()[0] if pythonpath_thesistester_roots() else ""
        ),
    }


# ``python -m`` from the MW0 checkout otherwise shadows PYTHONPATH. Run at
# import so capture_operator / stage_trace lift the farm worktree before
# ``import thesistester``.
prefer_pythonpath_thesistester()
