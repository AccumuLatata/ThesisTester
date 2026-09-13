"""Shared secret-key scrub for persist and log surfaces (QI-09-06).

``sidecar.redact_for_logs`` re-exports this function so voice logs and
assistant audit persist share one forbidden-key set. Do not fork the list.
"""

from __future__ import annotations

from typing import Any, Mapping

_FORBIDDEN_LOG_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "xai_api_key",
        "client_secret",
        "token",
        "value",
        "secret",
    }
)


def redact_for_logs(payload: Any) -> Any:
    """Return a JSON-safe structure with secret-bearing keys replaced.

    Keys whose lower-cased name is in ``_FORBIDDEN_LOG_KEYS`` become
    ``[redacted]``. Containers are copied; other values are returned as-is.
    """
    if isinstance(payload, Mapping):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if key_text.lower() in _FORBIDDEN_LOG_KEYS:
                out[key_text] = "[redacted]"
                continue
            out[key_text] = redact_for_logs(value)
        return out
    if isinstance(payload, list):
        return [redact_for_logs(item) for item in payload]
    if isinstance(payload, tuple):
        return [redact_for_logs(item) for item in payload]
    return payload
