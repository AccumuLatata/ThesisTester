"""B-12 / QI-11-03 AppTest helpers (MG-26 / #478).

Public widget attributes and named session keys only. Never read ``proto.*``.
``set_value`` is allowed only on enabled widgets — Streamlit 1.63 raises
``AppTestError`` on a disabled ``chat_input`` (QUALITY_INVESTIGATION_PLAN.md
§4.3). Missing ``.disabled`` fails closed (do not treat it as enabled).
"""

from __future__ import annotations

from typing import Any

__all__ = ["set_enabled_value", "widget_disabled"]


def widget_disabled(widget: Any) -> bool:
    """Return the public ``.disabled`` flag. Do not read ``proto.*``.

    A widget without ``.disabled`` is not treated as enabled — the helper
    refuses so ``set_value`` cannot run fail-open.
    """
    kind = getattr(widget, "type", type(widget).__name__)
    try:
        disabled = widget.disabled
    except AttributeError as exc:
        raise AssertionError(f"set_value requires public .disabled on {kind}") from exc
    return bool(disabled)


def set_enabled_value(widget: Any, value: Any) -> Any:
    """Call ``set_value`` only after asserting the widget is enabled."""
    kind = getattr(widget, "type", type(widget).__name__)
    key = getattr(widget, "key", None)
    assert widget_disabled(widget) is False, f"set_value on disabled {kind}" + (
        f" (key={key!r})" if key else ""
    )
    return widget.set_value(value)
