"""QI-09-03 / D-10: sidecar URL + localhost helpers on the Assistant page.

Loads private helpers via AST so the Streamlit page body is never executed.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from thesistester.assistant.voice.sidecar import (
    DEFAULT_SIDECAR_HOST,
    DEFAULT_SIDECAR_PORT,
    SidecarError,
    assert_localhost_bind,
    sidecar_public_base_url,
)

_PAGE = Path("pages/14_Research_Assistant.py")
_HELPER_NAMES = (
    "_sidecar_host_port",
    "_sidecar_base_url",
    "_client_url_is_localhost",
)


def _load_sidecar_helpers():
    source = _PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    chunks: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _HELPER_NAMES:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            chunks.append(segment)
    assert {name for name in _HELPER_NAMES} <= {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    ns = {
        "DEFAULT_SIDECAR_HOST": DEFAULT_SIDECAR_HOST,
        "DEFAULT_SIDECAR_PORT": DEFAULT_SIDECAR_PORT,
        "SidecarError": SidecarError,
        "assert_localhost_bind": assert_localhost_bind,
        "sidecar_public_base_url": sidecar_public_base_url,
        "st": SimpleNamespace(session_state={}),
    }
    exec("\n\n".join(chunks), ns, ns)
    return ns


def test_page_defines_voice_sidecar_and_advanced_helpers():
    source = _PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    for name in (
        "_render_discuss_voice_sidecar",
        "_render_help_voice",
        "_render_advanced_block",
        "_sidecar_host_port",
        "_sidecar_base_url",
        "_client_url_is_localhost",
    ):
        assert name in defined
    assert source.index("def _render_advanced_block") < source.index("_render_advanced_block()")
    assert source.index("_render_advanced_block()") < source.index(
        'with st.expander("Debug: raw JSON & conversation audit"'
    )
    assert source.index(
        "_render_discuss_voice_sidecar(run, runs, results_qa_settings)"
    ) < source.index("_render_help_voice(runs, help_settings)")


def test_client_url_is_localhost_accepts_loopback_and_rejects_others():
    fn = _load_sidecar_helpers()["_client_url_is_localhost"]
    assert fn("http://127.0.0.1:8765/client") is True
    assert fn("https://127.0.0.1/client") is True
    assert fn("http://[::1]:8765/") is True
    assert fn("https://[::1]/client") is True
    assert fn("http://0.0.0.0:8765/client") is False
    assert fn("http://example.com/client") is False
    assert fn("http://localhost:8765/client") is False
    assert fn("127.0.0.1:8765/client") is False
    assert fn("") is False
    assert fn("ftp://127.0.0.1:8765/") is False


def test_sidecar_host_port_falls_back_on_bad_host_and_port():
    host_port = _load_sidecar_helpers()["_sidecar_host_port"]
    good = {
        "assistant_voice_sidecar_host": "127.0.0.1",
        "assistant_voice_sidecar_port": 9001,
    }
    assert host_port(good) == ("127.0.0.1", 9001)

    missing: dict = {}
    assert host_port(missing) == (DEFAULT_SIDECAR_HOST, DEFAULT_SIDECAR_PORT)

    bad_host = {"assistant_voice_sidecar_host": "0.0.0.0", "assistant_voice_sidecar_port": 8765}
    assert host_port(bad_host) == (DEFAULT_SIDECAR_HOST, 8765)
    assert bad_host["assistant_voice_sidecar_host"] == DEFAULT_SIDECAR_HOST

    for port in ("abc", 0, 65536, None):
        state = {
            "assistant_voice_sidecar_host": "127.0.0.1",
            "assistant_voice_sidecar_port": port,
        }
        assert host_port(state) == ("127.0.0.1", DEFAULT_SIDECAR_PORT)


def test_sidecar_base_url_uses_public_loopback_helper():
    base_url = _load_sidecar_helpers()["_sidecar_base_url"]
    state = {
        "assistant_voice_sidecar_host": "127.0.0.1",
        "assistant_voice_sidecar_port": 9002,
    }
    assert base_url(state) == sidecar_public_base_url("127.0.0.1", 9002)
    assert base_url(state) == "http://127.0.0.1:9002"

    fallback = {"assistant_voice_sidecar_host": "0.0.0.0", "assistant_voice_sidecar_port": 1}
    assert base_url(fallback) == f"http://{DEFAULT_SIDECAR_HOST}:1"
