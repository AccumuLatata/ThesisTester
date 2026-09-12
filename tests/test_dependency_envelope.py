"""QR G-2 / QI-12-02 — lock, cap, and named pandas-major axis stay consistent."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas
import streamlit

tomllib = importlib.import_module("tomllib" if sys.version_info >= (3, 11) else "tomli")

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def _streamlit_spec() -> str:
    deps = _pyproject()["project"]["dependencies"]
    return next(dep for dep in deps if dep.startswith("streamlit"))


def _pandas_specs() -> list[str]:
    deps = _pyproject()["project"]["dependencies"]
    return [dep for dep in deps if dep.startswith("pandas")]


def _constraint_pins(name: str) -> list[str]:
    prefix = f"{name}=="
    return [
        line.split(";", 1)[0].strip()
        for line in (ROOT / "constraints.txt").read_text().splitlines()
        if line.startswith(prefix)
    ]


def test_streamlit_pyproject_cap_is_164() -> None:
    assert _streamlit_spec() == "streamlit>=1.56,<1.64"


def test_streamlit_constraint_and_runtime_stay_inside_cap() -> None:
    pins = _constraint_pins("streamlit")
    assert pins == ["streamlit==1.63.0"]
    major, minor, *_ = streamlit.__version__.split(".")
    assert (int(major), int(minor)) < (1, 64)


def test_pandas_markers_name_the_major_axis() -> None:
    specs = _pandas_specs()
    assert "pandas>=2.2,<3; python_version < '3.11'" in specs
    assert "pandas>=3,<4; python_version >= '3.11'" in specs
    pins = _constraint_pins("pandas")
    assert "pandas==2.3.3" in pins
    assert "pandas==3.0.5" in pins


def test_runtime_pandas_major_matches_named_axis() -> None:
    major = int(pandas.__version__.split(".", 1)[0])
    import sys

    if sys.version_info < (3, 11):
        assert major == 2
    else:
        assert major == 3
