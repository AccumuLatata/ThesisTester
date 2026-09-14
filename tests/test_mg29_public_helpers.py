"""C-6 / MG-29: promoted analytics and hash helpers stay public."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from thesistester.analytics import SIMULATION_KWARGS, directional_grid_metrics
from thesistester.analytics.grid import _directional_grid_metrics
from thesistester.analytics.overfitting import _SIMULATION_KWARGS
from thesistester.persistence.local_store import _hash_dataframe, hash_dataframe
from thesistester.reporting import _dash_if_none, dash_if_none
from thesistester.setup import _default_otf_filter_config, default_otf_filter_config

_REPO = Path(__file__).resolve().parents[1]
_C6_CONSUMERS = (
    _REPO / "thesistester" / "analytics" / "overfitting.py",
    _REPO / "thesistester" / "analytics" / "sensitivity.py",
    _REPO / "thesistester" / "analytics" / "otf_validation.py",
    _REPO / "thesistester" / "research_bundle.py",
    _REPO / "pages" / "11_Report_Export.py",
)
_PROMOTED_PRIVATE = frozenset(
    {
        "_directional_grid_metrics",
        "_SIMULATION_KWARGS",
        "_default_otf_filter_config",
        "_hash_dataframe",
        "_dash_if_none",
    }
)


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name)
    return names


def test_mg29_public_helpers_are_aliases_of_private_names():
    assert directional_grid_metrics is _directional_grid_metrics
    assert SIMULATION_KWARGS is _SIMULATION_KWARGS
    assert default_otf_filter_config is _default_otf_filter_config
    assert hash_dataframe is _hash_dataframe
    assert dash_if_none is _dash_if_none


def test_mg29_consumers_import_public_names_not_private():
    for path in _C6_CONSUMERS:
        imported = _imported_names(path)
        leaked = imported & _PROMOTED_PRIVATE
        assert not leaked, f"{path.relative_to(_REPO)} still imports {sorted(leaked)}"


def test_hash_dataframe_matches_private_alias():
    frame = pd.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
    assert hash_dataframe(frame) == _hash_dataframe(frame)


def test_dash_if_none_preserves_zero_and_false():
    assert dash_if_none(None) == "—"
    assert dash_if_none(0) == 0
    assert dash_if_none(False) is False


def test_otf_validation_keeps_empty_trades_qi4_handoff():
    imported = _imported_names(_REPO / "thesistester" / "analytics" / "otf_validation.py")
    assert "_empty_trades_df" in imported
