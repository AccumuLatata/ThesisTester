"""Data layer: loading, validation, session tagging, resampling."""

from .rolls import (
    ROLL_METHODS,
    compute_roll_gaps,
    detect_contract_column,
    detect_contract_segments,
    validate_roll_metadata,
)

__all__ = [
    "ROLL_METHODS",
    "compute_roll_gaps",
    "detect_contract_column",
    "detect_contract_segments",
    "validate_roll_metadata",
]
