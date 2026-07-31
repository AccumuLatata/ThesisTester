"""R16 price-series perturbation robustness diagnostics.

The noise test perturbs copied OHLC bars, reruns a caller-supplied canonical
research pipeline for each replica, and summarizes the resulting trade
outcomes. It is diagnostic-only: it tests local input sensitivity, not future
performance or an out-of-sample edge.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
import pandas as pd

from thesistester.analytics.metrics import summarize_trades

_DEFAULT_PERCENTILES = (5.0, 25.0, 50.0, 75.0, 95.0)
_SCALE_BASES = {"atr", "range"}
_OHLC_COLUMNS = ("open", "high", "low", "close")


def _percentile_key(percentile: float) -> str:
    return f"p{int(percentile):02d}" if float(percentile).is_integer() else f"p{percentile:g}"


def _coerce_percentiles(percentiles: Iterable[float]) -> tuple[float, ...]:
    values = tuple(sorted({float(value) for value in percentiles}))
    if not values or any(not 0 <= value <= 100 for value in values):
        raise ValueError("percentiles must contain values between 0 and 100.")
    return values


def _validate_noise_config(
    *,
    n_replicas: int,
    noise_fraction: float,
    scale_basis: str,
    atr_period: int,
    random_state: int,
) -> None:
    if int(n_replicas) < 1:
        raise ValueError("n_replicas must be a positive integer.")
    if not np.isfinite(noise_fraction) or not 0 < float(noise_fraction) <= 1:
        raise ValueError("noise_fraction must be finite and in (0, 1].")
    if scale_basis not in _SCALE_BASES:
        raise ValueError(f"scale_basis must be one of {sorted(_SCALE_BASES)}.")
    if int(atr_period) < 1:
        raise ValueError("atr_period must be a positive integer.")
    if isinstance(random_state, bool) or not isinstance(random_state, (int, np.integer)):
        raise ValueError("random_state must be an integer.")


def assert_valid_ohlc(data: pd.DataFrame) -> None:
    """Raise when a frame does not satisfy the canonical OHLC bar invariants."""
    missing = [column for column in _OHLC_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"OHLC data is missing columns: {missing}.")
    values = data.loc[:, _OHLC_COLUMNS].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("OHLC data must contain finite numeric values.")
    high = values["high"]
    low = values["low"]
    if (high < values[["open", "close", "low"]].max(axis=1)).any() or (
        low > values[["open", "close", "high"]].min(axis=1)
    ).any():
        raise ValueError("OHLC bar invariants are violated.")


def rolling_atr(data: pd.DataFrame, *, period: int = 14) -> pd.Series:
    """Return a deterministic rolling true-range scale with finite warm-up."""
    if int(period) < 1:
        raise ValueError("period must be a positive integer.")
    assert_valid_ohlc(data)
    high = pd.to_numeric(data["high"], errors="raise")
    low = pd.to_numeric(data["low"], errors="raise")
    prior_close = pd.to_numeric(data["close"], errors="raise").shift(1)
    true_range = pd.concat(
        [high - low, (high - prior_close).abs(), (low - prior_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(int(period), min_periods=1).mean().astype(float)


def _range_scale(data: pd.DataFrame) -> pd.Series:
    return (
        pd.to_numeric(data["high"], errors="raise") - pd.to_numeric(data["low"], errors="raise")
    ).astype(float)


def perturb_ohlc(
    data: pd.DataFrame,
    *,
    noise_fraction: float,
    scale_basis: str = "atr",
    atr_period: int = 14,
    random_state: int = 42,
) -> pd.DataFrame:
    """Return a seeded, invariant-preserving perturbation of a copied OHLC frame."""
    _validate_noise_config(
        n_replicas=1,
        noise_fraction=noise_fraction,
        scale_basis=scale_basis,
        atr_period=atr_period,
        random_state=random_state,
    )
    assert_valid_ohlc(data)
    result = data.copy(deep=True)
    scale = rolling_atr(result, period=atr_period) if scale_basis == "atr" else _range_scale(result)
    rng = np.random.default_rng(random_state)
    noise = (
        rng.uniform(
            low=-float(noise_fraction),
            high=float(noise_fraction),
            size=(len(result), len(_OHLC_COLUMNS)),
        )
        * scale.to_numpy(dtype=float)[:, None]
    )
    perturbed = result.loc[:, _OHLC_COLUMNS].to_numpy(dtype=float) + noise
    result.loc[:, _OHLC_COLUMNS] = perturbed
    result["high"] = result.loc[:, ["open", "high", "low", "close"]].max(axis=1)
    result["low"] = result.loc[:, ["open", "high", "low", "close"]].min(axis=1)
    assert_valid_ohlc(result)
    return result


def trade_persistence_rate(
    baseline_trades: pd.DataFrame | None,
    replica_trades: pd.DataFrame | None,
) -> float | None:
    """Return the baseline-trade fraction retaining the same signal identity.

    Signal identifiers are preferred because a rerun can change entry prices.
    If unavailable, identity falls back to direction plus entry timestamp.
    """
    if baseline_trades is None or baseline_trades.empty:
        return None
    replica = replica_trades if replica_trades is not None else pd.DataFrame()
    if "signal_id" in baseline_trades.columns and "signal_id" in replica.columns:
        baseline_keys = set(baseline_trades["signal_id"].dropna().tolist())
        replica_keys = set(replica["signal_id"].dropna().tolist())
    elif {"direction", "entry_timestamp"} <= set(baseline_trades.columns) and {
        "direction",
        "entry_timestamp",
    } <= set(replica.columns):
        baseline_keys = set(
            zip(
                baseline_trades["direction"],
                pd.to_datetime(baseline_trades["entry_timestamp"], utc=True),
                strict=True,
            )
        )
        replica_keys = set(
            zip(
                replica["direction"],
                pd.to_datetime(replica["entry_timestamp"], utc=True),
                strict=True,
            )
        )
    else:
        raise ValueError("Trade persistence requires signal_id or direction plus entry_timestamp.")
    if not baseline_keys:
        return None
    return float(len(baseline_keys & replica_keys) / len(baseline_keys))


def _percentile_summary(values: list[float], percentiles: tuple[float, ...]) -> dict[str, float]:
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    return {
        _percentile_key(percentile): float(np.percentile(finite, percentile))
        for percentile in percentiles
        if finite.size
    }


def noise_summary(
    data: pd.DataFrame,
    baseline_trades: pd.DataFrame,
    *,
    replica_runner: Callable[[pd.DataFrame], pd.DataFrame],
    n_replicas: int = 1000,
    noise_fraction: float = 0.05,
    scale_basis: str = "atr",
    atr_period: int = 14,
    random_state: int = 42,
    percentiles: Iterable[float] = _DEFAULT_PERCENTILES,
    include_rows: bool = False,
) -> dict[str, Any]:
    """Run seeded full-pipeline replicas through ``replica_runner``.

    ``replica_runner`` must only consume its supplied perturbed data and return
    the completed-trades frame from the canonical pipeline.
    """
    _validate_noise_config(
        n_replicas=n_replicas,
        noise_fraction=noise_fraction,
        scale_basis=scale_basis,
        atr_period=atr_period,
        random_state=random_state,
    )
    pct = _coerce_percentiles(percentiles)
    config = {
        "n_replicas": int(n_replicas),
        "noise_fraction": float(noise_fraction),
        "scale_basis": scale_basis,
        "atr_period": int(atr_period),
        "random_state": int(random_state),
        "percentiles": [float(value) for value in pct],
        "persistence_match": "signal_id_or_direction_entry_timestamp",
        "subtimeframe_policy": "pinned_unperturbed",
    }
    if baseline_trades is None or baseline_trades.empty:
        return {
            "schema_version": 1,
            "available": False,
            "config": config,
            "baseline": {"trade_count": 0, "expectancy_r": None, "profit_factor": None},
            "replicas": {
                "n_completed": 0,
                "expectancy_r": {},
                "profit_factor": {},
                "trade_persistence_rate": {},
            },
            "caveat": "Noise diagnostics require baseline completed trades.",
        }
    baseline_metrics = summarize_trades(baseline_trades)

    seed_stream = np.random.default_rng(random_state)
    rows: list[dict[str, Any]] = []
    for replica_id in range(int(n_replicas)):
        replica_seed = int(seed_stream.integers(0, np.iinfo(np.uint32).max, endpoint=True))
        perturbed = perturb_ohlc(
            data,
            noise_fraction=noise_fraction,
            scale_basis=scale_basis,
            atr_period=atr_period,
            random_state=replica_seed,
        )
        replica_trades = replica_runner(perturbed)
        metrics = summarize_trades(replica_trades)
        rows.append(
            {
                "replica_id": replica_id,
                "trade_count": int(len(replica_trades)),
                "expectancy_r": metrics.get("expectancy_r"),
                "profit_factor": metrics.get("profit_factor"),
                "trade_persistence_rate": trade_persistence_rate(baseline_trades, replica_trades),
            }
        )
    replica_frame = pd.DataFrame(rows)
    result: dict[str, Any] = {
        "schema_version": 1,
        "available": True,
        "config": config,
        "baseline": {
            "trade_count": int(len(baseline_trades)),
            "expectancy_r": baseline_metrics.get("expectancy_r"),
            "profit_factor": baseline_metrics.get("profit_factor"),
        },
        "replicas": {
            "n_completed": int(len(rows)),
            "expectancy_r": _percentile_summary(
                replica_frame["expectancy_r"].dropna().tolist(), pct
            ),
            "profit_factor": _percentile_summary(
                replica_frame["profit_factor"].dropna().tolist(), pct
            ),
            "trade_persistence_rate": _percentile_summary(
                replica_frame["trade_persistence_rate"].dropna().tolist(), pct
            ),
        },
        "caveat": (
            "Noise results are local sensitivity diagnostics on a declared perturbation model. "
            "They do not establish future performance or an out-of-sample edge."
        ),
    }
    if include_rows:
        result["replicas"]["rows"] = rows
    return result
