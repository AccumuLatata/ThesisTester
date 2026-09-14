"""C-6 / MG-29: promoted analytics and hash helpers stay public."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from thesistester.analytics import SIMULATION_KWARGS, directional_grid_metrics
from thesistester.analytics.grid import _directional_grid_metrics
from thesistester.analytics.overfitting import SIMULATION_KWARGS as OVERFIT_SIMULATION_KWARGS
from thesistester.analytics.overfitting import _SIMULATION_KWARGS
from thesistester.persistence.local_store import _hash_dataframe, hash_dataframe
from thesistester.reporting import _dash_if_none, dash_if_none
from thesistester.setup import (
    DEFAULT_OTF_FILTER_CONFIG,
    _default_otf_filter_config,
    default_otf_filter_config,
)

_REPO = Path(__file__).resolve().parents[1]
_PROD_ROOTS = (_REPO / "thesistester", _REPO / "pages")
# Cross-module importers named by QI-05-14 / QI-06-11 plus remaining
# production callers switched in C-6. Same-module owners define the
# public name and are not listed.
_C6_PUBLIC_IMPORTS = {
    "thesistester/analytics/overfitting.py": frozenset({"directional_grid_metrics"}),
    "thesistester/analytics/sensitivity.py": frozenset({"SIMULATION_KWARGS"}),
    "thesistester/analytics/otf_validation.py": frozenset({"default_otf_filter_config"}),
    "thesistester/research_bundle.py": frozenset({"hash_dataframe"}),
    "pages/11_Report_Export.py": frozenset({"dash_if_none"}),
    "thesistester/engine/otf_integration.py": frozenset({"default_otf_filter_config"}),
    "thesistester/research_identity.py": frozenset({"hash_dataframe"}),
    "thesistester/persistence/execution_artifacts.py": frozenset({"hash_dataframe"}),
}
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
    assert SIMULATION_KWARGS is OVERFIT_SIMULATION_KWARGS
    assert default_otf_filter_config is _default_otf_filter_config
    assert hash_dataframe is _hash_dataframe
    assert dash_if_none is _dash_if_none


def test_mg29_production_does_not_import_promoted_private_names():
    leaks: list[str] = []
    for root in _PROD_ROOTS:
        for path in root.rglob("*.py"):
            leaked = _imported_names(path) & _PROMOTED_PRIVATE
            if leaked:
                rel = path.relative_to(_REPO).as_posix()
                leaks.append(f"{rel}: {sorted(leaked)}")
    assert leaks == [], "C-6 private names still imported:\n" + "\n".join(leaks)


def test_mg29_consumers_import_public_names():
    for rel, required in _C6_PUBLIC_IMPORTS.items():
        imported = _imported_names(_REPO / rel)
        missing = required - imported
        assert not missing, f"{rel} missing public imports {sorted(missing)}"


def test_default_otf_filter_config_copies_canonical_constant():
    got = default_otf_filter_config()
    assert got == DEFAULT_OTF_FILTER_CONFIG
    assert got is not DEFAULT_OTF_FILTER_CONFIG
    got["timeframes"].append("5m")
    got["enabled"] = True
    assert DEFAULT_OTF_FILTER_CONFIG["timeframes"] == []
    assert DEFAULT_OTF_FILTER_CONFIG["enabled"] is False
    assert default_otf_filter_config()["timeframes"] == []


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
