"""Shared tick-input gates for VA / APOC / rolling POC.

Named-VA refuse stays ``VA requires ticks``. APOC and rolling POC use the same
fail-closed layer (study schema / ``run_experiment`` / product ``compute_levels``)
with ``requires ticks`` in the reason. A prior-VA parquet is not APOC or
rolling-POC input.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from thesistester.levels.catalog import (
    named_apoc_tokens,
    named_rolling_poc_tokens,
)

VA_REQUIRES_TICKS: Final[str] = "VA requires ticks"
APOC_REQUIRES_TICKS: Final[str] = "APOC requires ticks"
ROLLING_POC_REQUIRES_TICKS: Final[str] = "rolling POC requires ticks"


def dataset_has_tick_paths(dataset: Mapping[str, Any] | None) -> bool:
    """True when ``tick_paths`` lists at least one non-blank path.

    A ``prior_profile_table_path`` is not tick input for APOC or rolling POC.
    """
    if not dataset:
        return False
    paths = dataset.get("tick_paths")
    return isinstance(paths, list) and any(
        isinstance(item, (str, Path)) and str(item).strip() for item in paths
    )


def tick_paths_present(paths: Sequence[str | Path] | str | Path | None) -> bool:
    """True when a tick-path argument names at least one non-blank file."""
    if paths is None:
        return False
    if isinstance(paths, (str, Path)):
        return bool(str(paths).strip())
    return any(str(item).strip() for item in paths)


def _named_family_message(family: str, tokens: Sequence[str], *, prefix: str) -> str:
    return f"{family}: {prefix} is missing or empty (named {list(tokens)})"


def named_va_requires_ticks_message(tokens: Sequence[str], *, prefix: str) -> str:
    return _named_family_message(VA_REQUIRES_TICKS, tokens, prefix=prefix)


def named_apoc_requires_ticks_message(tokens: Sequence[str], *, prefix: str) -> str:
    return _named_family_message(APOC_REQUIRES_TICKS, tokens, prefix=prefix)


def named_rolling_poc_requires_ticks_message(tokens: Sequence[str], *, prefix: str) -> str:
    return _named_family_message(ROLLING_POC_REQUIRES_TICKS, tokens, prefix=prefix)


def settings_require_apoc_ticks(
    settings: Mapping[str, Any] | None,
    *,
    apoc_enabled: bool | None = None,
    apoc_profile_source: object | None = None,
) -> bool:
    """True when APOC is enabled (production tick family; no typical escape)."""
    # Lazy import: profile.py → this module must not import apoc_tick at load.
    from thesistester.levels.apoc_tick import resolve_apoc_profile_source

    payload = dict(settings or {})
    enabled = payload.get("apoc_enabled") if apoc_enabled is None else apoc_enabled
    if not enabled:
        return False
    source = (
        payload.get("apoc_profile_source") if apoc_profile_source is None else apoc_profile_source
    )
    resolve_apoc_profile_source(source)
    return True


def settings_require_rolling_poc_ticks(
    settings: Mapping[str, Any] | None,
    *,
    poc_windows: object | None = None,
) -> bool:
    """True when rolling POC windows are in play (including product default)."""
    if poc_windows is None:
        payload = dict(settings or {})
        poc_windows = payload.get("poc_windows")
    if poc_windows is None:
        return False
    if isinstance(poc_windows, (str, Path)):
        return bool(str(poc_windows).strip())
    return any(str(item).strip() for item in poc_windows)


def product_tick_family_message(*, apoc: bool, rolling: bool) -> str:
    """Reason text for product/library compute paths (no named-token list)."""
    families = [name for flag, name in ((apoc, "APOC"), (rolling, "rolling POC")) if flag]
    if not families:
        return ""
    if len(families) == 1:
        return f"{families[0]} requires ticks: tick_paths is missing or empty"
    return "APOC requires ticks and rolling POC requires ticks: tick_paths is missing or empty"


def disable_unneeded_tick_families(
    levels: Mapping[str, Any] | None,
    named_tokens: Sequence[object],
) -> dict[str, Any]:
    """Turn off unused tick families so 15s-only runs do not emit placeholders."""
    out = dict(levels or {})
    if not named_apoc_tokens(named_tokens):
        out["apoc_enabled"] = False
    if not named_rolling_poc_tokens(named_tokens):
        out["poc_windows"] = []
    return out
