"""Capability audit for the AI Research Assistant release gate.

Every registry row must be either routed (handler present) or explicitly
unsupported with a user-visible limitation. This module is the machine-readable
audit used by tests and final documentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from thesistester.assistant.handlers import HANDLER_REGISTRY
from thesistester.assistant.registry import FEATURE_PARITY_REGISTRY

AuditStatus = Literal["routed", "unsupported", "invalid"]


@dataclass(frozen=True)
class CapabilityAuditRow:
    capability_id: str
    mode: str
    confirmation: str
    has_handler: bool
    limitation: str | None
    status: AuditStatus

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "capability_id": self.capability_id,
            "mode": self.mode,
            "confirmation": self.confirmation,
            "has_handler": self.has_handler,
            "limitation": self.limitation,
            "status": self.status,
        }


def audit_capability_registry() -> tuple[CapabilityAuditRow, ...]:
    """Return one audit row per FEATURE_PARITY_REGISTRY capability."""
    rows: list[CapabilityAuditRow] = []
    for capability in FEATURE_PARITY_REGISTRY:
        has_handler = capability.capability_id in HANDLER_REGISTRY
        limitation = capability.limitation
        mode = capability.mode.value
        if mode == "unsupported":
            status: AuditStatus = (
                "unsupported"
                if isinstance(limitation, str) and limitation.strip() and not has_handler
                else "invalid"
            )
        else:
            status = "routed" if has_handler else "invalid"
        rows.append(
            CapabilityAuditRow(
                capability_id=capability.capability_id,
                mode=mode,
                confirmation=capability.confirmation.value,
                has_handler=has_handler,
                limitation=limitation,
                status=status,
            )
        )
    return tuple(rows)


def capability_audit_summary(
    rows: tuple[CapabilityAuditRow, ...] | None = None,
) -> dict[str, int]:
    """Return aggregate counts for documentation and release gates."""
    audited = rows or audit_capability_registry()
    summary = {
        "total": len(audited),
        "routed": 0,
        "unsupported": 0,
        "invalid": 0,
        "mode_executable": 0,
        "mode_inspect_only": 0,
        "mode_import_export": 0,
        "mode_unsupported": 0,
    }
    mode_key = {
        "executable": "mode_executable",
        "inspect_only": "mode_inspect_only",
        "import_export": "mode_import_export",
        "unsupported": "mode_unsupported",
    }
    for row in audited:
        summary[row.status] += 1
        keyed = mode_key.get(row.mode)
        if keyed is not None:
            summary[keyed] += 1
    return summary


def render_capability_audit_markdown(
    rows: tuple[CapabilityAuditRow, ...] | None = None,
) -> str:
    """Render a compact markdown audit table for roadmap/docs sync."""
    audited = rows or audit_capability_registry()
    summary = capability_audit_summary(audited)
    lines = [
        "# Assistant capability audit",
        "",
        (
            f"Total {summary['total']}: routed {summary['routed']}, "
            f"unsupported {summary['unsupported']}, invalid {summary['invalid']}."
        ),
        "",
        "| Capability | Mode | Confirmation | Status | Limitation |",
        "|---|---|---|---|---|",
    ]
    for row in audited:
        limitation = (row.limitation or "").replace("|", "\\|")
        lines.append(
            f"| `{row.capability_id}` | {row.mode} | {row.confirmation} | "
            f"{row.status} | {limitation} |"
        )
    return "\n".join(lines) + "\n"
