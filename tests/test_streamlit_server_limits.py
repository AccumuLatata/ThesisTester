"""Gate Streamlit checkout-local server payload / upload caps."""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_CONFIG = REPO_ROOT / ".streamlit" / "config.toml"


def _server_section() -> dict:
    payload = tomllib.loads(STREAMLIT_CONFIG.read_text(encoding="utf-8"))
    server = payload.get("server")
    assert isinstance(server, dict), ".streamlit/config.toml must define [server]"
    return server


def test_streamlit_config_raises_websocket_message_size_to_400_mb():
    """MessageSizeError is server.maxMessageSize (MB), not host RAM."""
    server = _server_section()
    assert server.get("maxMessageSize") == 400
    assert server.get("maxUploadSize") == 350
