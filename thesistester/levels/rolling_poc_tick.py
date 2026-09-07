"""Sliding Last×Volume rolling POC (RP2; desk default).

Production ``POC_rolling_*`` is Quantower Tick–Tick–Last Last×Volume on the
theoretical print window ``[now - W + 1min, now + 1min)``. This is ThesisTester
sliding tick VAP, not a Quantower rolling-widget parity claim (desk has no
such indicator). It is **not** A-period APOC, **not** prior-session VA, and
**not** typical ``_rolling_poc``.

Missing or empty ``tick_paths`` refuse with ``rolling POC requires ticks``
when windows are in play (product / ``compute_profile_levels``). Unreadable
files or a window with an unsound tick (off-grid / non-finite / non-positive
volume) emit ``NaN`` for that bar. There is no typical fallback.

Do not reuse ``PriorProfileTable`` or ``APeriodTickProfileTable``. Histogram
bins / lowest-price ties match ``compute_tick_last_volume_profile``; that
helper is not called per bar (two-pointer incremental histogram).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from thesistester.config import INSTRUMENTS
from thesistester.data.quantower_ticks import (
    TICK_FORMAT_PROFILE,
    TickIngestError,
    iter_tick_files,
)
from thesistester.levels.apoc_candidates import TICK_GRID_ATOL, TICK_LAST_VOLUME_V1
from thesistester.levels.common import normalized_window_label

ROLLING_POC_LOOKBACK_POLICY_ID: Final[str] = "rolling_lookback_v1"
ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1: Final[str] = TICK_LAST_VOLUME_V1
ROLLING_POC_PROFILE_SOURCES: Final[frozenset[str]] = frozenset(
    {ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1}
)
ROLLING_POC_ALLOCATION_LAST_TIMES_VOLUME: Final[str] = "last_times_volume"

LEVELS_ROLLING_POC_IDENTITY_KEYS: Final[tuple[str, ...]] = (
    "rolling_poc_algorithm_version",
    "rolling_poc_allocation",
    "rolling_poc_tick_source_id",
)

_DEFAULT_BAR_INTERVAL: Final[str] = "1min"


def resolve_rolling_poc_profile_source(value: object | None) -> str:
    """Return the only production rolling-POC source, or raise.

    Blank / omitted resolves to ``tick_last_volume_v1``. Typical and bar-proxy
    tokens are not production sources.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1
    source = str(value)
    if source not in ROLLING_POC_PROFILE_SOURCES:
        raise ValueError(
            f"Unsupported rolling_poc_profile_source: {source!r}. "
            f"Supported sources: {sorted(ROLLING_POC_PROFILE_SOURCES)}"
        )
    return source


def _resolve_tick_path_list(
    paths: Sequence[str | Path] | str | Path | None,
) -> list[Path]:
    if paths is None:
        return []
    if isinstance(paths, (str, Path)):
        text = str(paths).strip()
        return [Path(text)] if text else []
    return [Path(path) for path in paths if str(path).strip()]


def _canonical_poc_windows(windows: object | None) -> str:
    if windows is None:
        labels = ["30min"]
    elif isinstance(windows, (str, pd.Timedelta)):
        labels = [normalized_window_label(windows)]
    else:
        labels = [normalized_window_label(window) for window in windows]
        if not labels:
            labels = ["30min"]
    return ",".join(sorted(labels))


def compute_rolling_poc_tick_source_id(
    paths: Sequence[str | Path] | str | Path | None,
    *,
    poc_windows: object | None = None,
    format_profile: str = TICK_FORMAT_PROFILE,
) -> str:
    """Content identity for rolling-POC tick inputs.

    Mixes VA file identity with ``rolling_lookback_v1`` and canonical
    ``poc_windows`` so the id cannot equal VA or APOC tick ids.
    """
    from thesistester.levels.tick_vap import TICK_SOURCE_NONE, compute_tick_source_id

    resolved = _resolve_tick_path_list(paths)
    if not resolved:
        return TICK_SOURCE_NONE
    try:
        base = compute_tick_source_id(resolved, format_profile=format_profile)
    except OSError:
        return TICK_SOURCE_NONE
    if base == TICK_SOURCE_NONE:
        return TICK_SOURCE_NONE
    hasher = sha256()
    hasher.update(b"rolling_poc_tick\0")
    hasher.update(base.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(ROLLING_POC_LOOKBACK_POLICY_ID.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(_canonical_poc_windows(poc_windows).encode("utf-8"))
    return hasher.hexdigest()


def attach_rolling_poc_identity(
    settings: dict[str, Any],
    *,
    tick_paths: Sequence[str | Path] | str | Path | None = None,
    rolling_poc_tick_source_id: str | None = None,
    format_profile: str = TICK_FORMAT_PROFILE,
) -> dict[str, Any]:
    """Stamp rolling-POC tick identity into the hashed settings dict.

    Always attaches. Implicit omitted source is tick Last×Volume (desk default),
    not typical. Identity keys are stripped before ``compute_all_levels``.
    """
    attached = dict(settings)
    if "rolling_poc_profile_source" in attached:
        source = resolve_rolling_poc_profile_source(attached.get("rolling_poc_profile_source"))
    else:
        source = ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1
    attached["rolling_poc_algorithm_version"] = source
    attached["rolling_poc_allocation"] = ROLLING_POC_ALLOCATION_LAST_TIMES_VOLUME
    attached["rolling_poc_tick_source_id"] = (
        rolling_poc_tick_source_id
        if rolling_poc_tick_source_id
        else compute_rolling_poc_tick_source_id(
            tick_paths,
            poc_windows=attached.get("poc_windows"),
            format_profile=format_profile,
        )
    )
    return attached


def compute_rolling_poc_tick_levels(
    bars: pd.DataFrame,
    *,
    tick_paths: Sequence[str | Path] | str | Path | None,
    windows: Sequence[str | pd.Timedelta],
    instrument: str,
    source_tz: str = "UTC",
    format_profile: str = TICK_FORMAT_PROFILE,
    bar_interval: str = _DEFAULT_BAR_INTERVAL,
) -> pd.DataFrame:
    """Return ``POC_rolling_*`` columns from ``tick_paths`` (fail-closed)."""
    labels = [normalized_window_label(window) for window in windows]
    empty = pd.DataFrame(
        {f"POC_rolling_{label}": np.nan for label in labels},
        index=bars.index,
        dtype="float64",
    )
    if instrument not in INSTRUMENTS:
        raise ValueError(f"Unsupported instrument: {instrument}")
    resolved = _resolve_tick_path_list(tick_paths)
    if not resolved:
        return empty
    try:
        chunks = list(iter_tick_files(resolved, instrument=instrument, source_tz=source_tz))
    except (TickIngestError, OSError, ValueError):
        return empty
    frames = [
        chunk.ticks[["timestamp", "price", "volume"]]
        for chunk in chunks
        if chunk.ticks is not None and not chunk.ticks.empty
    ]
    if not frames:
        return empty
    ticks = pd.concat(frames, ignore_index=True)
    result, _stats = compute_rolling_poc_from_ticks(
        bars,
        ticks,
        windows=windows,
        tick_size=INSTRUMENTS[instrument].tick_size,
        bar_interval=bar_interval,
    )
    return result


def compute_rolling_poc_from_ticks(
    bars: pd.DataFrame,
    ticks: pd.DataFrame,
    *,
    windows: Sequence[str | pd.Timedelta],
    tick_size: float,
    bar_interval: str = _DEFAULT_BAR_INTERVAL,
) -> tuple[pd.DataFrame, Mapping[str, Mapping[str, int]]]:
    """Two-pointer Last×Volume POC per requested window.

    Returns ``(levels_frame, pointer_stats)``. Stats record monotonic add/remove
    counts so tests can prove each tick is visited at most once per pointer.
    """
    timestamps = pd.to_datetime(bars["timestamp"], errors="coerce")
    prepared = _prepare_ticks(ticks, tick_size=tick_size)
    interval = pd.to_timedelta(bar_interval)
    levels = pd.DataFrame(index=bars.index)
    stats: dict[str, dict[str, int]] = {}
    for window in windows:
        label = normalized_window_label(window)
        series, window_stats = _two_pointer_poc(
            timestamps.to_numpy(),
            prepared,
            window=pd.to_timedelta(window),
            interval=interval,
        )
        levels[f"POC_rolling_{label}"] = pd.Series(series, index=bars.index, dtype="float64")
        stats[label] = window_stats
    return levels, stats


def _prepare_ticks(ticks: pd.DataFrame, *, tick_size: float) -> pd.DataFrame:
    work = ticks.copy()
    if (
        "timestamp" not in work.columns
        or "price" not in work.columns
        or "volume" not in work.columns
    ):
        return pd.DataFrame(
            {
                "timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
                "bin": pd.Series(dtype="float64"),
                "volume": pd.Series(dtype="float64"),
                "unsound": pd.Series(dtype="bool"),
            }
        )
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
    work["price"] = pd.to_numeric(work["price"], errors="coerce")
    work["volume"] = pd.to_numeric(work["volume"], errors="coerce")
    work = work.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    price = work["price"].to_numpy(dtype="float64")
    volume = work["volume"].to_numpy(dtype="float64")
    ticks_per = price / tick_size
    on_grid = np.isclose(ticks_per, np.round(ticks_per), rtol=0.0, atol=TICK_GRID_ATOL)
    unsound = (
        work["timestamp"].isna().to_numpy()
        | ~np.isfinite(price)
        | ~np.isfinite(volume)
        | (volume <= 0)
        | ~on_grid
    )
    bins = (np.round(price / tick_size) * tick_size).round(10)
    return pd.DataFrame(
        {
            "timestamp": work["timestamp"],
            "bin": bins,
            "volume": volume,
            "unsound": unsound,
        }
    )


def _two_pointer_poc(
    bar_timestamps: np.ndarray,
    ticks: pd.DataFrame,
    *,
    window: pd.Timedelta,
    interval: pd.Timedelta,
) -> tuple[np.ndarray, dict[str, int]]:
    n_bars = len(bar_timestamps)
    out = np.full(n_bars, np.nan, dtype="float64")
    if ticks.empty:
        return out, {"adds": 0, "removes": 0, "n_ticks": 0, "n_bars": n_bars}

    tick_ts = ticks["timestamp"].to_numpy()
    tick_bin = ticks["bin"].to_numpy(dtype="float64")
    tick_vol = ticks["volume"].to_numpy(dtype="float64")
    tick_unsound = ticks["unsound"].to_numpy(dtype="bool")
    n_ticks = len(ticks)
    left = 0
    right = 0
    hist: dict[float, float] = {}
    unsound = 0
    adds = 0
    removes = 0

    for i, now in enumerate(bar_timestamps):
        if pd.isna(now):
            continue
        now_ts = pd.Timestamp(now)
        start = now_ts - window + interval
        end = now_ts + interval
        while right < n_ticks and pd.Timestamp(tick_ts[right]) < end:
            if tick_unsound[right]:
                unsound += 1
            else:
                _add_bin(hist, float(tick_bin[right]), float(tick_vol[right]))
            right += 1
            adds += 1
        while left < right and pd.Timestamp(tick_ts[left]) < start:
            if tick_unsound[left]:
                unsound -= 1
            else:
                _remove_bin(hist, float(tick_bin[left]), float(tick_vol[left]))
            left += 1
            removes += 1
        if unsound == 0 and hist:
            out[i] = _poc_from_hist(hist)

    return out, {"adds": adds, "removes": removes, "n_ticks": n_ticks, "n_bars": n_bars}


def _add_bin(hist: dict[float, float], price: float, volume: float) -> None:
    hist[price] = hist.get(price, 0.0) + volume


def _remove_bin(hist: dict[float, float], price: float, volume: float) -> None:
    remaining = hist.get(price, 0.0) - volume
    if remaining <= 0.0:
        hist.pop(price, None)
    else:
        hist[price] = remaining


def _poc_from_hist(hist: Mapping[float, float]) -> float:
    max_volume = max(hist.values())
    return float(min(price for price, volume in hist.items() if volume == max_volume))
