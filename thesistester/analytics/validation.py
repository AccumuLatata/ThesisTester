"""Phase 8 analytics — statistical validation and robustness diagnostics.

All functions operate on completed trades from Phase 5.  No trade
re-simulation is performed; this module is purely diagnostic.

Caveats
-------
- Bootstrap assumes the observed sample is representative of the trade
  distribution.  Results are unreliable for very small samples.
- The sign-flip permutation test assumes sign symmetry around zero and
  ignores serial dependence between trades.
- Grid-search overfit warnings are heuristic and descriptive only.
- None of these diagnostics prove edge.  They surface evidence and warnings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# A. bootstrap_expectancy_ci
# ---------------------------------------------------------------------------

def bootstrap_expectancy_ci(
    trades: pd.DataFrame,
    n_bootstrap: int = 2000,
    confidence: float = 0.95,
    random_state: int | None = 42,
) -> dict:
    """Estimate a bootstrap confidence interval for mean R.

    Parameters
    ----------
    trades:
        Trade DataFrame with a ``r_multiple`` column.
    n_bootstrap:
        Number of bootstrap resamples.
    confidence:
        Confidence level, e.g. ``0.95`` for 95 % CI.
    random_state:
        Seed for :func:`numpy.random.default_rng` to ensure determinism.
        Pass ``None`` for a random seed.

    Returns
    -------
    dict
        Keys: ``trade_count``, ``observed_avg_r``, ``ci_lower``,
        ``ci_upper``, ``confidence``, ``n_bootstrap``,
        ``probability_positive``, ``bootstrap_means``.
        ``observed_avg_r``, ``ci_lower``, ``ci_upper`` and
        ``probability_positive`` are ``None`` when there are no valid trades.
    """
    empty: dict = {
        "trade_count": 0,
        "observed_avg_r": None,
        "ci_lower": None,
        "ci_upper": None,
        "confidence": confidence,
        "n_bootstrap": n_bootstrap,
        "probability_positive": None,
        "bootstrap_means": [],
    }

    if trades is None or trades.empty:
        return empty

    r = trades["r_multiple"].dropna().to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return empty

    observed_avg_r = float(r.mean())

    rng = np.random.default_rng(random_state)
    bootstrap_means: list[float] = []
    for _ in range(n_bootstrap):
        sample = rng.choice(r, size=n, replace=True)
        bootstrap_means.append(float(sample.mean()))

    means_arr = np.array(bootstrap_means)
    alpha = 1.0 - confidence
    ci_lower = float(np.percentile(means_arr, 100 * alpha / 2))
    ci_upper = float(np.percentile(means_arr, 100 * (1 - alpha / 2)))
    probability_positive = float((means_arr > 0).mean())

    return {
        "trade_count": n,
        "observed_avg_r": observed_avg_r,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "confidence": confidence,
        "n_bootstrap": n_bootstrap,
        "probability_positive": probability_positive,
        "bootstrap_means": bootstrap_means,
    }


# ---------------------------------------------------------------------------
# B. permutation_test_expectancy
# ---------------------------------------------------------------------------

def permutation_test_expectancy(
    trades: pd.DataFrame,
    n_permutations: int = 5000,
    random_state: int | None = 42,
) -> dict:
    """Sign-flip permutation test for positive expectancy.

    Null hypothesis: trade signs are random around zero.  For each
    permutation each R value is multiplied by a random ``+1`` / ``-1`` sign.
    The one-sided p-value is the fraction of permuted means >= observed mean R.

    .. note::
        This is a simplified diagnostic.  It assumes sign symmetry around
        zero and ignores serial dependence between trades.

    Parameters
    ----------
    trades:
        Trade DataFrame with a ``r_multiple`` column.
    n_permutations:
        Number of sign-flip permutations.
    random_state:
        Seed for :func:`numpy.random.default_rng`.

    Returns
    -------
    dict
        Keys: ``trade_count``, ``observed_avg_r``, ``p_value_positive``,
        ``n_permutations``, ``permuted_means``.
        ``observed_avg_r`` and ``p_value_positive`` are ``None`` when there
        are no valid trades.
    """
    empty: dict = {
        "trade_count": 0,
        "observed_avg_r": None,
        "p_value_positive": None,
        "n_permutations": n_permutations,
        "permuted_means": [],
    }

    if trades is None or trades.empty:
        return empty

    r = trades["r_multiple"].dropna().to_numpy(dtype=float)
    n = len(r)
    if n == 0:
        return empty

    observed_avg_r = float(r.mean())

    rng = np.random.default_rng(random_state)
    permuted_means: list[float] = []
    for _ in range(n_permutations):
        signs = rng.choice([-1.0, 1.0], size=n, replace=True)
        permuted_means.append(float((r * signs).mean()))

    means_arr = np.array(permuted_means)
    p_value_positive = float((means_arr >= observed_avg_r).mean())

    return {
        "trade_count": n,
        "observed_avg_r": observed_avg_r,
        "p_value_positive": p_value_positive,
        "n_permutations": n_permutations,
        "permuted_means": permuted_means,
    }


# ---------------------------------------------------------------------------
# C. trade_count_diagnostics
# ---------------------------------------------------------------------------

def trade_count_diagnostics(
    trades: pd.DataFrame,
    min_trades_soft: int = 30,
    min_trades_hard: int = 100,
) -> dict:
    """Return a sample-size adequacy assessment.

    Parameters
    ----------
    trades:
        Trade DataFrame.  Only the row count is used.
    min_trades_soft:
        Below this count conclusions are unreliable.
    min_trades_hard:
        At or above this count results are reasonably interpretable.

    Returns
    -------
    dict
        Keys: ``trade_count``, ``min_trades_soft``, ``min_trades_hard``,
        ``status`` (one of ``insufficient``, ``limited``, ``reasonable``),
        ``message``.
    """
    if trades is None or trades.empty:
        count = 0
    else:
        count = int(trades["r_multiple"].dropna().shape[0])

    if count < min_trades_soft:
        status = "insufficient"
        message = (
            f"Only {count} trade(s) available. Results are unreliable with "
            f"fewer than {min_trades_soft} trades. Do not draw conclusions "
            "from this sample size."
        )
    elif count < min_trades_hard:
        status = "limited"
        message = (
            f"{count} trade(s) available. This sample is limited "
            f"({min_trades_soft}–{min_trades_hard - 1} trades). Treat "
            "all metrics with caution and seek more data before drawing "
            "conclusions."
        )
    else:
        status = "reasonable"
        message = (
            f"{count} trade(s) available. Sample size is reasonably large "
            "for exploratory analysis, though statistical uncertainty remains "
            "and results should be interpreted with care."
        )

    return {
        "trade_count": count,
        "min_trades_soft": min_trades_soft,
        "min_trades_hard": min_trades_hard,
        "status": status,
        "message": message,
    }


# ---------------------------------------------------------------------------
# D. grid_overfit_diagnostics
# ---------------------------------------------------------------------------

def grid_overfit_diagnostics(
    grid: pd.DataFrame,
    selected_metric: str = "expectancy_r",
    top_n: int = 10,
) -> dict:
    """Heuristic overfit-risk assessment for Phase 6 grid-search results.

    Heuristic rules (deterministic):

    - No grid or ≤ 1 valid cell            → risk ``none``
    - valid cells < 10                      → risk ``low``
    - valid cells 10–24                     → risk ``medium`` if
      ``best_vs_median_delta`` is material (> 0.5× median absolute value),
      else ``low``
    - valid cells 25–99                     → at least ``medium``
    - valid cells ≥ 100                     → ``high``

    Parameters
    ----------
    grid:
        Phase 6 grid DataFrame (one row per SL/TP cell).
    selected_metric:
        Metric column to evaluate.
    top_n:
        Number of top cells to average for ``top_n_mean_metric``.

    Returns
    -------
    dict
        Keys: ``grid_cell_count``, ``valid_cell_count``, ``best_metric``,
        ``median_metric``, ``mean_metric``, ``top_n_mean_metric``,
        ``best_vs_median_delta``, ``risk_level``, ``message``.
    """
    empty: dict = {
        "grid_cell_count": 0,
        "valid_cell_count": 0,
        "best_metric": None,
        "median_metric": None,
        "mean_metric": None,
        "top_n_mean_metric": None,
        "best_vs_median_delta": None,
        "risk_level": "none",
        "message": "No grid results available.",
    }

    if grid is None or grid.empty:
        return empty

    grid_cell_count = int(len(grid))

    if selected_metric not in grid.columns:
        result = dict(empty)
        result["grid_cell_count"] = grid_cell_count
        result["message"] = (
            f"Selected metric '{selected_metric}' not found in grid."
        )
        return result

    valid = grid[selected_metric].dropna()
    valid_cell_count = int(len(valid))

    if valid_cell_count <= 1:
        result = dict(empty)
        result["grid_cell_count"] = grid_cell_count
        result["valid_cell_count"] = valid_cell_count
        result["message"] = "Too few valid grid cells to assess overfitting."
        return result

    best_metric = float(valid.max())
    median_metric = float(valid.median())
    mean_metric = float(valid.mean())
    top_vals = valid.nlargest(min(top_n, valid_cell_count))
    top_n_mean_metric = float(top_vals.mean())
    best_vs_median_delta = best_metric - median_metric

    # Determine risk level
    if valid_cell_count >= 100:
        risk_level = "high"
        message = (
            f"{valid_cell_count} parameter combinations were tested. "
            "With this many cells the best result is very likely to be "
            "inflated by chance. Treat it as an upper bound, not a "
            "reliable estimate."
        )
    elif valid_cell_count >= 25:
        risk_level = "medium"
        message = (
            f"{valid_cell_count} parameter combinations were tested. "
            "The best result may be inflated by multiple comparisons. "
            "Validate on independent data before trusting this result."
        )
    elif valid_cell_count >= 10:
        # Assess whether the delta is material relative to spread
        median_abs = abs(median_metric) if median_metric != 0 else 1.0
        if best_vs_median_delta > 0.5 * median_abs:
            risk_level = "medium"
            message = (
                f"{valid_cell_count} parameter combinations were tested and "
                "the best result is notably above the median. Some degree of "
                "selection bias is possible."
            )
        else:
            risk_level = "low"
            message = (
                f"{valid_cell_count} parameter combinations were tested. "
                "Overfitting risk is low but cannot be ruled out."
            )
    else:
        risk_level = "low"
        message = (
            f"{valid_cell_count} parameter combinations were tested. "
            "Grid is small; overfitting risk is low."
        )

    return {
        "grid_cell_count": grid_cell_count,
        "valid_cell_count": valid_cell_count,
        "best_metric": best_metric,
        "median_metric": median_metric,
        "mean_metric": mean_metric,
        "top_n_mean_metric": top_n_mean_metric,
        "best_vs_median_delta": best_vs_median_delta,
        "risk_level": risk_level,
        "message": message,
    }


# ---------------------------------------------------------------------------
# E. validation_summary
# ---------------------------------------------------------------------------

def validation_summary(
    trades: pd.DataFrame,
    grid: pd.DataFrame | None = None,
    *,
    n_bootstrap: int = 2000,
    n_permutations: int = 5000,
    confidence: float = 0.95,
    random_state: int | None = 42,
    min_trades_soft: int = 30,
    min_trades_hard: int = 100,
    selected_grid_metric: str = "expectancy_r",
) -> dict:
    """Run all Phase 8 validation diagnostics and return a combined dict.

    Parameters
    ----------
    trades:
        Phase 5 trade DataFrame with ``r_multiple``.
    grid:
        Optional Phase 6 grid DataFrame for overfit diagnostics.
    n_bootstrap:
        Passed to :func:`bootstrap_expectancy_ci`.
    n_permutations:
        Passed to :func:`permutation_test_expectancy`.
    confidence:
        Passed to :func:`bootstrap_expectancy_ci`.
    random_state:
        Shared random seed for determinism.
    min_trades_soft:
        Passed to :func:`trade_count_diagnostics`.
    min_trades_hard:
        Passed to :func:`trade_count_diagnostics`.
    selected_grid_metric:
        Passed to :func:`grid_overfit_diagnostics`.

    Returns
    -------
    dict
        Keys: ``bootstrap``, ``permutation``, ``trade_count``,
        ``grid_overfit``.
    """
    return {
        "bootstrap": bootstrap_expectancy_ci(
            trades,
            n_bootstrap=n_bootstrap,
            confidence=confidence,
            random_state=random_state,
        ),
        "permutation": permutation_test_expectancy(
            trades,
            n_permutations=n_permutations,
            random_state=random_state,
        ),
        "trade_count": trade_count_diagnostics(
            trades,
            min_trades_soft=min_trades_soft,
            min_trades_hard=min_trades_hard,
        ),
        "grid_overfit": grid_overfit_diagnostics(
            grid if grid is not None else pd.DataFrame(),
            selected_metric=selected_grid_metric,
        ),
    }
