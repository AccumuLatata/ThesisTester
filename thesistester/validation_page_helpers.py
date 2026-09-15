"""Classic Validation persist/display helpers (QR D-4 / QI-05-02).

Kept out of ``pages/10_Validation.py`` so permutation / overlap copy can be
unit-tested without importing the Streamlit page. Formatters and parse
helpers move here unchanged. Helpers are Streamlit-free (C-8).
"""

from __future__ import annotations

from typing import Any

OVERLAP_HELP = (
    "Reject withholds stitched equity when OOS windows overlap. "
    "`aggregate_test_total_r` is a fold-sum of `test_total_r` and can "
    "double-count overlapping OOS trades. first/last assign overlapping "
    "stitch trades to one fold; they do not change the fold-sum."
)

PERMUTATION_H13_CAPTION = "Sign-flip assumes sign symmetry and ignores serial dependence (H13)."


def fmt_value(v: Any, fmt: str = ".4f", fallback: str = "—") -> str:
    if v is None:
        return fallback
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return fallback


def parse_positive_int_values(raw: str) -> list[int]:
    values = sorted(
        {
            int(token.strip())
            for token in str(raw).split(",")
            if token.strip() and int(token.strip()) > 0
        }
    )
    if not values:
        raise ValueError("Provide at least one positive integer.")
    return values


def parse_thresholds(text: str) -> list[float]:
    """Monte Carlo drawdown-threshold parse. Live path is the batteries helper."""
    thresholds: list[float] = []
    for part in str(text).split(","):
        try:
            value = float(part.strip())
        except ValueError:
            continue
        if value > 0:
            thresholds.append(value)
    return sorted(dict.fromkeys(thresholds)) or [3.0, 5.0, 10.0]


def assemble_overlap_help() -> str:
    """M9 overlap-selectbox help: fold-sum named; reject withholds stitch only."""
    return OVERLAP_HELP


def assemble_permutation_copy(p_val: float) -> dict[str, str | None]:
    """H13 permutation chrome: info + optional caption; never celebratory."""
    if p_val > 0.10:
        return {
            "info": (
                f"p = {p_val:.4f} — Observed mean R is not unusually high "
                "relative to a zero-expectancy null (sign-flip test)."
            ),
            "caption": None,
        }
    if p_val > 0.05:
        return {
            "info": (
                f"p = {p_val:.4f} — Marginal evidence against the zero-expectancy null. "
                "Interpret with caution."
            ),
            "caption": None,
        }
    return {
        "info": (
            f"p = {p_val:.4f} — Observed mean R is in the tail of the "
            "sign-flip null. Diagnostic only — not a significance test "
            "and not proof of edge."
        ),
        "caption": PERMUTATION_H13_CAPTION,
    }
