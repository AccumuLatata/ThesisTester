"""Read-only voice tool schemas and allowlisted executor (VA-3).

Exact v1 tools: get_run_overview, get_metric, list_caveats, compare_two_runs.
Never executes compute, search, mcp, or save_comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from thesistester.assistant.explainer import (
    EvidencePacket,
    compare_evidence,
    explain_evidence_report,
)
from thesistester.assistant.repository import AssistantRepositoryError
from thesistester.assistant.tools import AssistantToolError
from thesistester.assistant.voice.contracts import VoiceToolInvocation
from thesistester.assistant.voice.session import VoiceSessionError, VoiceSessionService
from thesistester.assistant.workspace import require_run_bundle_hash
from thesistester.reporting import to_jsonable

_ALLOWED_METRIC_ROOTS = frozenset({"results", "assumptions", "provenance"})
_VOICE_TOOL_NAMES = frozenset(
    {
        "get_run_overview",
        "get_metric",
        "list_caveats",
        "compare_two_runs",
    }
)

VOICE_TOOL_SCHEMAS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "name": "get_run_overview",
        "description": (
            "Return a deterministic overview and caveats from the bound "
            "hash-verified evidence packet for this results voice session."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_metric",
        "description": (
            "Return one typed metric value from the bound evidence packet by "
            "dot-path under results, assumptions, or provenance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Dot-path such as results.trade_summary.win_rate",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_caveats",
        "description": "List honesty caveats from the bound evidence packet.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "compare_two_runs",
        "description": (
            "Compare the bound run to another completed thesis run via pure "
            "compare_evidence. Does not persist a comparison record."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "other_run_id": {
                    "type": "string",
                    "description": "run_… id of the other completed run on this thesis",
                }
            },
            "required": ["other_run_id"],
            "additionalProperties": False,
        },
    },
)


class VoiceToolError(ValueError):
    """Raised when a voice tool name/args/path is rejected fail-closed."""


@dataclass(frozen=True)
class VoiceToolSession:
    """Bound handle for allowlisted voice tool execution."""

    service: VoiceSessionService
    thesis_id: str
    session_id: str


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path_exists(root: Mapping[str, Any], path: str) -> bool:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _path_get(root: Mapping[str, Any], path: str) -> Any:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _safe_jsonable(value: Any) -> Any:
    try:
        return to_jsonable(value)
    except Exception:
        return str(value)


def _validate_metric_path(path: Any) -> str:
    if not isinstance(path, str) or not path.strip():
        raise VoiceToolError("get_metric requires a non-empty path string.")
    normalized = path.strip()
    if "/" in normalized or "\\" in normalized:
        raise VoiceToolError("get_metric path must not contain filesystem separators.")
    if ".." in normalized:
        raise VoiceToolError("get_metric rejects path traversal.")
    parts = normalized.split(".")
    if any(not part or part.strip() != part for part in parts):
        raise VoiceToolError("get_metric path segments must be non-empty.")
    if parts[0] not in _ALLOWED_METRIC_ROOTS:
        raise VoiceToolError("get_metric path must start with results, assumptions, or provenance.")
    return normalized


def _require_results_packet(session: VoiceToolSession) -> tuple[Any, EvidencePacket]:
    record = session.service.repository.get_voice_session(session.thesis_id, session.session_id)
    if record.channel != "results_qa":
        raise VoiceToolError("Voice tools that read evidence require a results_qa session.")
    if record.status != "active":
        raise VoiceToolError("Cannot execute voice tools on an ended session.")
    packet = session.service.get_bound_packet(session.session_id)
    if packet is None:
        raise VoiceToolError("Results voice session has no bound evidence packet.")
    return record, packet


def _tool_get_run_overview(session: VoiceToolSession, args: Mapping[str, Any]) -> dict[str, Any]:
    if args:
        raise VoiceToolError("get_run_overview accepts no arguments.")
    _record, packet = _require_results_packet(session)
    report = explain_evidence_report(packet)
    return {
        "overview": report.get("narrative"),
        "claims": report.get("claims") or [],
        "caveats": [caveat.to_dict() for caveat in packet.caveats],
        "limitations": list(packet.limitations),
        "next_experiments": report.get("next_experiments") or list(packet.next_experiments),
        "run_id": _record.run_id,
        "canonical_bundle_hash": _record.expected_canonical_bundle_hash,
    }


def _tool_get_metric(session: VoiceToolSession, args: Mapping[str, Any]) -> dict[str, Any]:
    path = _validate_metric_path(args.get("path"))
    unknown = sorted(set(args) - {"path"})
    if unknown:
        raise VoiceToolError(f"get_metric unknown arguments: {unknown}")
    _record, packet = _require_results_packet(session)
    root = packet.to_dict()
    if not _path_exists(root, path):
        raise VoiceToolError(f"Unknown metric path: {path}")
    value = _path_get(root, path)
    if value is None or value == "":
        raise VoiceToolError(f"Metric path is empty: {path}")
    if isinstance(value, (dict, list)):
        value_type = "object" if isinstance(value, dict) else "array"
    elif isinstance(value, bool):
        value_type = "boolean"
    elif isinstance(value, int) and not isinstance(value, bool):
        value_type = "integer"
    elif isinstance(value, float):
        value_type = "number"
    elif isinstance(value, str):
        value_type = "string"
    else:
        value_type = type(value).__name__
    return {
        "path": path,
        "value": _safe_jsonable(value),
        "value_type": value_type,
        "run_id": _record.run_id,
    }


def _tool_list_caveats(session: VoiceToolSession, args: Mapping[str, Any]) -> dict[str, Any]:
    if args:
        raise VoiceToolError("list_caveats accepts no arguments.")
    _record, packet = _require_results_packet(session)
    return {
        "caveats": [caveat.to_dict() for caveat in packet.caveats],
        "warnings": list(packet.warnings),
        "run_id": _record.run_id,
    }


def _load_other_run_packet(
    session: VoiceToolSession, *, other_run_id: str
) -> tuple[str, str, EvidencePacket]:
    service = session.service
    if service.tools is None:
        raise VoiceToolError("AssistantTools is required for compare_two_runs.")
    try:
        other = service.repository.get_run(session.thesis_id, other_run_id)
    except AssistantRepositoryError as exc:
        raise VoiceToolError("Other research run does not exist.") from exc
    if other.status != "completed":
        raise VoiceToolError("compare_two_runs requires a completed other run.")
    if not isinstance(other.provenance, Mapping):
        raise VoiceToolError("Other run is missing provenance.")
    try:
        expected_hash = require_run_bundle_hash(other.provenance).lower()
    except ValueError as exc:
        raise VoiceToolError(str(exc)) from exc
    bundle_path = other.provenance.get("bundle_path")
    if not isinstance(bundle_path, str) or not bundle_path.strip():
        raise VoiceToolError("Other run is missing bundle_path provenance.")
    try:
        resolved = Path(bundle_path.strip()).expanduser().resolve()
    except OSError as exc:
        raise VoiceToolError("Other run bundle path is invalid.") from exc
    if not any(resolved.is_relative_to(root.resolve()) for root in service.tools.data_roots):
        raise VoiceToolError("Other run bundle path is outside assistant data roots.")
    if not resolved.is_file():
        raise VoiceToolError("Other run bundle file is missing.")
    try:
        payload = service.tools.build_bundle_evidence_packet(
            str(resolved),
            expected_hash=expected_hash,
            provenance=dict(other.provenance),
        )
    except (AssistantToolError, OSError, ValueError) as exc:
        raise VoiceToolError(str(exc)) from exc
    except Exception as exc:
        # Corrupt / non-zip bytes must fail closed (hash verify / load path).
        raise VoiceToolError("Other run bundle could not be hash-verified for comparison.") from exc
    return other.run_id, expected_hash, EvidencePacket.from_dict(payload)


def _tool_compare_two_runs(session: VoiceToolSession, args: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(args) - {"other_run_id"})
    if unknown:
        raise VoiceToolError(f"compare_two_runs unknown arguments: {unknown}")
    other_run_id = args.get("other_run_id")
    if not isinstance(other_run_id, str) or not other_run_id.strip():
        raise VoiceToolError("compare_two_runs requires a non-empty other_run_id.")
    record, left_packet = _require_results_packet(session)
    if record.run_id is None:
        raise VoiceToolError("Bound results session is missing run_id.")
    if other_run_id.strip() == record.run_id:
        raise VoiceToolError("compare_two_runs other_run_id must differ from the bound run.")
    other_id, other_hash, right_packet = _load_other_run_packet(
        session, other_run_id=other_run_id.strip()
    )
    comparison = compare_evidence(left_packet, right_packet)
    # Pure compare only — never call repository.save_comparison.
    return {
        "left_run_id": record.run_id,
        "right_run_id": other_id,
        "left_canonical_bundle_hash": record.expected_canonical_bundle_hash,
        "right_canonical_bundle_hash": other_hash,
        "comparison": comparison,
        "persisted": False,
    }


_TOOL_IMPLS = {
    "get_run_overview": _tool_get_run_overview,
    "get_metric": _tool_get_metric,
    "list_caveats": _tool_list_caveats,
    "compare_two_runs": _tool_compare_two_runs,
}


def _audit_invocation(
    session: VoiceToolSession,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    ok: bool,
    result: dict[str, Any],
    error: str | None,
) -> VoiceToolInvocation:
    invocation = VoiceToolInvocation(
        tool_name=tool_name,
        arguments=arguments,
        ok=ok,
        result=result,
        created_at=_utcnow(),
        error=error,
    )
    try:
        session.service.append_tool_invocation(session.thesis_id, session.session_id, invocation)
    except (VoiceSessionError, AssistantRepositoryError):
        # Still return the in-memory audit row to the caller even if persist fails.
        pass
    return invocation


def execute_voice_tool(
    name: str,
    args: Mapping[str, Any] | None,
    *,
    session: VoiceToolSession,
) -> dict[str, Any]:
    """Execute one allowlisted voice tool and record exactly one audit row.

    Unknown / denied names fail closed with no tool side effects beyond the
    single audit invocation row.
    """
    arguments = dict(args or {})
    tool_name = name.strip() if isinstance(name, str) else ""
    if tool_name not in _VOICE_TOOL_NAMES:
        invocation = _audit_invocation(
            session,
            tool_name=tool_name or str(name),
            arguments=arguments,
            ok=False,
            result={},
            error=f"Unknown or denied voice tool: {name!r}",
        )
        return {
            "ok": False,
            "tool_name": invocation.tool_name,
            "result": {},
            "error": invocation.error,
            "audit": invocation.to_dict(),
        }

    impl = _TOOL_IMPLS[tool_name]
    try:
        result = impl(session, arguments)
        invocation = _audit_invocation(
            session,
            tool_name=tool_name,
            arguments=arguments,
            ok=True,
            result=result if isinstance(result, dict) else {"value": result},
            error=None,
        )
        return {
            "ok": True,
            "tool_name": tool_name,
            "result": invocation.result,
            "error": None,
            "audit": invocation.to_dict(),
        }
    except (VoiceToolError, VoiceSessionError, AssistantRepositoryError, AssistantToolError) as exc:
        invocation = _audit_invocation(
            session,
            tool_name=tool_name,
            arguments=arguments,
            ok=False,
            result={},
            error=str(exc),
        )
        return {
            "ok": False,
            "tool_name": tool_name,
            "result": {},
            "error": invocation.error,
            "audit": invocation.to_dict(),
        }
