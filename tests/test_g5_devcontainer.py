"""QR G-5 / QI-12-08 — Codespaces/devcontainer matches the CI envelope."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER = ROOT / ".devcontainer" / "devcontainer.json"
STREAMLIT_CONFIG = ROOT / ".streamlit" / "config.toml"

CI_PYTHON_IMAGE = "mcr.microsoft.com/devcontainers/python:1-3.12-bookworm"
IMAGE_PYTHON = "/usr/local/bin/python"
INSTALL_PREFIX = f"{IMAGE_PYTHON} -m pip install --user -e '.[dev]' -c constraints.txt"
POST_ATTACH = {"server": "streamlit run app.py"}

COMMAND_KEYS = (
    "initializeCommand",
    "onCreateCommand",
    "updateContentCommand",
    "postCreateCommand",
    "postStartCommand",
    "postAttachCommand",
)

# CLI flags plus Streamlit env aliases (case-insensitive).
XSRF_CORS_RE = re.compile(
    r"enablecors|enablexsrfprotection|"
    r"streamlit_server_enable_cors|"
    r"streamlit_server_enable_xsrf",
    re.IGNORECASE,
)
# Second uncapped Streamlit install (QI-12-08). `.[dev]` does not contain
# the token `streamlit`; `python -m pip install streamlit` must not slip past.
PIP_STREAMLIT_RE = re.compile(
    r"(?:python3?|pip3?)\s+(?:-m\s+pip\s+)?install\b[^\n;&|]*\bstreamlit\b",
    re.IGNORECASE,
)


def _strip_jsonc(raw: str) -> str:
    """Drop `//` line comments that are not inside JSON strings."""
    out: list[str] = []
    for line in raw.splitlines(keepends=True):
        in_str = False
        escape = False
        i = 0
        while i < len(line):
            ch = line[i]
            if in_str:
                out.append(ch)
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                i += 1
                continue
            if ch == '"':
                in_str = True
                out.append(ch)
                i += 1
                continue
            if ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                if line.endswith("\n"):
                    out.append("\n")
                break
            out.append(ch)
            i += 1
    return "".join(out)


def _load_devcontainer() -> dict:
    raw = DEVCONTAINER.read_text(encoding="utf-8")
    return json.loads(_strip_jsonc(raw))


def _flatten_commands(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_flatten_commands(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_flatten_commands(item))
        return out
    return [str(value)]


def _lifecycle_commands(data: dict) -> list[str]:
    out: list[str] = []
    for key in COMMAND_KEYS:
        out.extend(_flatten_commands(data.get(key)))
    return out


def _env_blobs(data: dict) -> list[str]:
    out: list[str] = []
    for key in ("containerEnv", "remoteEnv"):
        mapping = data.get(key) or {}
        if isinstance(mapping, dict):
            for name, value in mapping.items():
                out.append(f"{name}={value}")
    for arg in data.get("runArgs") or []:
        out.append(str(arg))
    return out


def test_jsonc_strip_keeps_urls_inside_strings() -> None:
    """Naive `//` strip would truncate `https://` and pass a wrong image."""
    raw = '{\n  "href": "https://example.com/python:3.11",\n  "image": "%s"\n}\n' % (
        CI_PYTHON_IMAGE,
    )
    data = json.loads(_strip_jsonc(raw))
    assert data["href"].startswith("https://")
    assert data["image"] == CI_PYTHON_IMAGE


def test_devcontainer_uses_one_ci_python_312() -> None:
    data = _load_devcontainer()
    assert data["image"] == CI_PYTHON_IMAGE
    assert "build" not in data
    features = data.get("features") or {}
    assert not any("python" in str(key).lower() for key in features)
    settings = data["customizations"]["vscode"]["settings"]
    assert settings["python.defaultInterpreterPath"] == IMAGE_PYTHON


def test_devcontainer_installs_editable_dev_extra_against_lock() -> None:
    data = _load_devcontainer()
    command = data["updateContentCommand"]
    assert isinstance(command, str)
    assert command.startswith(INSTALL_PREFIX)
    assert "-c constraints.txt" in command
    assert "requirements.txt" not in command
    assert "packages.txt" not in command
    joined = "\n".join(_lifecycle_commands(data))
    assert "requirements.txt" not in joined
    assert "packages.txt" not in joined
    assert not PIP_STREAMLIT_RE.search(joined)


def test_pip_streamlit_lock_catches_python_module_install() -> None:
    sneaky = "python3 -m pip install --user streamlit"
    assert PIP_STREAMLIT_RE.search(sneaky)
    assert not PIP_STREAMLIT_RE.search(INSTALL_PREFIX)


def test_devcontainer_does_not_disable_xsrf_or_cors() -> None:
    data = _load_devcontainer()
    assert data["postAttachCommand"] == POST_ATTACH
    blob = DEVCONTAINER.read_text(encoding="utf-8")
    assert XSRF_CORS_RE.search(blob) is None
    env_blob = "\n".join(_env_blobs(data))
    assert XSRF_CORS_RE.search(env_blob) is None


def test_xsrf_lock_catches_streamlit_env_aliases() -> None:
    """CLI camelCase lock must not miss STREAMLIT_SERVER_ENABLE_*."""
    assert XSRF_CORS_RE.search("STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false")
    assert XSRF_CORS_RE.search("STREAMLIT_SERVER_ENABLE_CORS=false")
    assert XSRF_CORS_RE.search("--server.enableXsrfProtection false")
    assert XSRF_CORS_RE.search(DEVCONTAINER.read_text(encoding="utf-8")) is None


def test_streamlit_product_config_untouched() -> None:
    """QI-10: G-5 must not rewrite transport caps."""
    text = STREAMLIT_CONFIG.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "[server]"
    assert "maxUploadSize = 350" in text
    assert "maxMessageSize = 400" in text
    assert XSRF_CORS_RE.search(text) is None
    assert "enableCORS" not in text
    assert "enableXsrfProtection" not in text
