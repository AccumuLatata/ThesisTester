"""Non-invasive import-time hooks. Product code is never edited."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from .compat import CompatError, import_optional, patch_aliases, resolve_hook, restore_aliases

VS_RANDOM_ALIASES: tuple[tuple[str, str], ...] = (
    ("thesistester.analytics.overfitting", "vs_random_benchmark"),
    ("thesistester.study.execute", "vs_random_benchmark"),
    ("thesistester.analytics", "vs_random_benchmark"),
)

PREPARE_ALIASES: tuple[tuple[str, str], ...] = (
    ("thesistester.engine.intrabar", "prepare_subtimeframe_conservative_context"),
    ("thesistester.api", "prepare_subtimeframe_conservative_context"),
    ("thesistester.engine.backtest", "prepare_subtimeframe_conservative_context"),
)

LOAD_ALIASES: tuple[tuple[str, str], ...] = (
    ("thesistester.api", "_load_15s_primary_experiment_data"),
)

API_GENERATE_ALIASES: tuple[tuple[str, str], ...] = (("thesistester.api", "generate_signals"),)

BUNDLE_ALIASES: tuple[tuple[str, str], ...] = (
    ("thesistester.research_bundle", "build_research_bundle"),
    ("thesistester.study.execute", "build_research_bundle"),
)


class ReplicaSink:
    """Collect ordered ``replica_expectancies`` lists from ``vs_random_benchmark``."""

    def __init__(self) -> None:
        self.calls: list[list[float]] = []

    @property
    def last(self) -> list[float]:
        if not self.calls:
            return []
        return list(self.calls[-1])

    def record(self, values: Any) -> None:
        if values is None:
            self.calls.append([])
            return
        self.calls.append([float(item) for item in list(values)])


def empty_vs_random_result(*, n_replicas: int = 0) -> dict[str, Any]:
    return {
        "available": False,
        "n_replicas": int(n_replicas),
        "observed_expectancy_r": None,
        "null_expectancy_mean": None,
        "null_expectancy_std": None,
        "percentile": None,
        "p_value_greater_or_equal": None,
        "replica_expectancies": [],
    }


@contextmanager
def replica_expectancies_hook() -> Iterator[ReplicaSink]:
    """Wrap ``vs_random_benchmark`` at every known alias (59a4652 + main)."""
    original = resolve_hook("thesistester.analytics.overfitting", "vs_random_benchmark").value
    sink = ReplicaSink()

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        replicas = []
        if isinstance(result, dict):
            replicas = list(result.get("replica_expectancies") or [])
        sink.record(replicas)
        return result

    undo = patch_aliases(original=original, wrapper=wrapped, aliases=VS_RANDOM_ALIASES)
    execute_mod = import_optional("thesistester.study.execute")
    if execute_mod is not None and hasattr(execute_mod, "vs_random_benchmark"):
        patched = {id(module) for module, _attr, _prev in undo}
        if id(execute_mod) not in patched:
            restore_aliases(undo)
            raise CompatError(
                "STOP AND REPORT: thesistester.study.execute.vs_random_benchmark "
                "exists but was not wrapped (object identity differs from "
                "analytics.overfitting). replica_expectancies would be missed "
                "on 59a4652, whose bundles do not persist this list."
            )
    try:
        yield sink
    finally:
        restore_aliases(undo)


@contextmanager
def skip_replica_loop() -> Iterator[None]:
    """Return the null vs-random payload so the 50-replica loop never runs."""
    original = resolve_hook("thesistester.analytics.overfitting", "vs_random_benchmark").value

    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        n_replicas = int(kwargs.get("n_replicas", 0) or 0)
        return empty_vs_random_result(n_replicas=n_replicas)

    undo = patch_aliases(original=original, wrapper=wrapped, aliases=VS_RANDOM_ALIASES)
    try:
        yield
    finally:
        restore_aliases(undo)


def wrap_callable(
    aliases: tuple[tuple[str, str], ...],
    wrapper_factory: Callable[[Callable[..., Any]], Callable[..., Any]],
) -> list[tuple[Any, str, Callable[..., Any]]]:
    primary_module, primary_attr = aliases[0]
    original = resolve_hook(primary_module, primary_attr).value
    wrapper = wrapper_factory(original)
    return patch_aliases(original=original, wrapper=wrapper, aliases=aliases)
