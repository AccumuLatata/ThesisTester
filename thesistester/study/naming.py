"""Deterministic filesystem-safe run names for Study Runner expansions (RS2)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from thesistester.study.schema import RUN_NAME_RE

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")
_MAX_RUN_NAME_LEN = 120


def _slug_token(value: Any) -> str:
    if isinstance(value, Mapping):
        # Compact OTF / mapping encoding for readable names.
        enabled = bool(value.get("enabled", False))
        if not enabled:
            return "otfOff"
        tfs = value.get("timeframes") or []
        tf_part = "-".join(str(tf) for tf in tfs) if tfs else "none"
        return f"otf_{tf_part}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "empty"
        return "-".join(_slug_token(item) for item in value)
    text = str(value).strip()
    text = text.replace(" ", "")
    text = _UNSAFE_RE.sub("_", text)
    return text or "x"


def factor_cell_fingerprint(factors: Mapping[str, Any]) -> str:
    """Stable short fingerprint of one factor cell (canonical JSON)."""
    payload = json.dumps(factors, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def build_run_name(
    study_name: str,
    *,
    index: int,
    factors: Mapping[str, Any],
) -> str:
    """Build a unique RUN_NAME_RE-safe run name for one expansion cell."""
    if not isinstance(study_name, str) or not RUN_NAME_RE.fullmatch(study_name):
        raise ValueError(f"study_name must match {RUN_NAME_RE.pattern!r}; got {study_name!r}")

    parts = [
        study_name,
        f"c{index:04d}",
        _slug_token(factors.get("confluence_mode", "mode")),
        _slug_token(factors.get("trigger", "trig")),
        _slug_token(factors.get("trigger_timeframe", "ttf")),
        _slug_token(factors.get("partner_levels", [])),
        _slug_token(factors.get("otf", {"enabled": False})),
        factor_cell_fingerprint(factors),
    ]
    name = "_".join(parts)
    name = _UNSAFE_RE.sub("_", name)
    if len(name) > _MAX_RUN_NAME_LEN:
        digest = factor_cell_fingerprint(factors)
        prefix = f"{study_name}_c{index:04d}_"
        budget = _MAX_RUN_NAME_LEN - len(prefix) - 1 - len(digest)
        mid = _slug_token(factors.get("partner_levels", []))[: max(budget, 1)]
        name = f"{prefix}{mid}_{digest}"
    if not RUN_NAME_RE.fullmatch(name):
        # Last-resort safe name.
        name = f"{study_name}_c{index:04d}_{factor_cell_fingerprint(factors)}"
    if not RUN_NAME_RE.fullmatch(name):
        raise ValueError(f"Failed to build valid run name for cell {index}: {name!r}")
    return name
