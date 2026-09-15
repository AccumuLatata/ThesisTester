"""Classic Validation sidebar settings (QR D-4 / QI-05-02).

Streamlit-free: callers pass ``st``. Widget labels and session keys unchanged.
"""

from __future__ import annotations

from typing import Any


def render_validation_sidebar(st: Any, *, grid_raw: Any) -> dict[str, Any]:
    """Render Validation sidebar widgets. Session keys unchanged."""
    st.header("Validation settings")

    n_bootstrap = int(
        st.number_input(
            "Bootstrap samples",
            min_value=500,
            max_value=50_000,
            value=2000,
            step=500,
            help="Number of bootstrap resamples for the CI estimate.",
        )
    )

    n_permutations = int(
        st.number_input(
            "Permutations",
            min_value=500,
            max_value=50_000,
            value=5000,
            step=500,
            help="Number of sign-flip permutations for the null distribution.",
        )
    )

    confidence = (
        st.selectbox(
            "Confidence level",
            options=[0.90, 0.95, 0.99],
            index=1,
            format_func=lambda v: f"{v:.0%}",
            help="Confidence level for the bootstrap CI.",
        )
        or 0.95
    )

    random_seed = int(
        st.number_input(
            "Random seed",
            min_value=0,
            max_value=99_999,
            value=42,
            step=1,
            help="Seed for reproducible bootstrap and permutation results.",
        )
    )

    min_trades_soft = int(
        st.number_input(
            "Min trades (soft)",
            min_value=1,
            max_value=10_000,
            value=30,
            step=1,
            help="Below this count results are flagged as insufficient.",
        )
    )

    min_trades_hard = int(
        st.number_input(
            "Min trades (hard)",
            min_value=1,
            max_value=10_000,
            value=100,
            step=1,
            help="At or above this count results are considered reasonable.",
        )
    )

    grid_metric_options = ["expectancy_r", "avg_r", "total_r", "win_rate"]
    if grid_raw is not None and not grid_raw.empty:
        # Use an explicit allowlist to avoid polluting the selector with
        # structural columns, trade counts, and every directional variant.
        _grid_metric_allowlist = [
            "expectancy_r",
            "avg_r",
            "total_r",
            "profit_factor",
            "win_rate",
            "max_drawdown_r",
            "long_expectancy_r",
            "short_expectancy_r",
            "long_profit_factor",
            "short_profit_factor",
            "min_direction_expectancy_r",
            "min_direction_profit_factor",
        ]
        _available = [c for c in _grid_metric_allowlist if c in grid_raw.columns]
        grid_metric_options = _available or grid_metric_options

    grid_metric = st.selectbox(
        "Grid metric",
        options=grid_metric_options,
        index=grid_metric_options.index("expectancy_r")
        if "expectancy_r" in grid_metric_options
        else 0,
        help="Metric used for grid overfit diagnostics.",
    )
    return {
        "n_bootstrap": n_bootstrap,
        "n_permutations": n_permutations,
        "confidence": confidence,
        "random_seed": random_seed,
        "min_trades_soft": min_trades_soft,
        "min_trades_hard": min_trades_hard,
        "grid_metric": grid_metric,
    }
