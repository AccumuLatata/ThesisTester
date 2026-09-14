"""QR G-5 / QI-12-08 — Codespaces/devcontainer matches the CI envelope."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER = ROOT / ".devcontainer" / "devcontainer.json"
STREAMLIT_CONFIG = ROOT / ".streamlit" / "config.toml"


def _load_devcontainer() -> dict:
    raw = DEVCONTAINER.read_text(encoding="utf-8")
    stripped = re.sub(r"//.*?$", "", raw, flags=re.MULTILINE)
    return json.loads(stripped)


def test_devcontainer_uses_one_ci_python_312() -> None:
    data = _load_devcontainer()
    assert data["image"] == "mcr.microsoft.com/devcontainers/python:1-3.12-bookworm"


def test_devcontainer_installs_editable_dev_extra_against_lock() -> None:
    data = _load_devcontainer()
    command = data["updateContentCommand"]
    assert "-e '.[dev]'" in command or '-e ".[dev]"' in command
    assert "-c constraints.txt" in command
    assert "requirements.txt" not in command
    assert "packages.txt" not in command
    # No second uncapped Streamlit install (QI-12-08).
    assert not re.search(r"pip3?\s+install\s+[^\n;]*\bstreamlit\b", command)


def test_devcontainer_does_not_disable_xsrf_or_cors() -> None:
    data = _load_devcontainer()
    attach = data["postAttachCommand"]
    assert attach == {"server": "streamlit run app.py"}
    blob = DEVCONTAINER.read_text(encoding="utf-8")
    assert "enableCORS" not in blob
    assert "enableXsrfProtection" not in blob


def test_streamlit_product_config_untouched() -> None:
    """QI-10: G-5 must not rewrite transport caps."""
    text = STREAMLIT_CONFIG.read_text(encoding="utf-8")
    assert "maxUploadSize = 350" in text
    assert "maxMessageSize = 400" in text
    assert "enableCORS" not in text
    assert "enableXsrfProtection" not in text
