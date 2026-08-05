"""Multi-turn grounded results Q&A over a hash-verified EvidencePacket (RQ-1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from thesistester.assistant.explainer import EvidenceClaim, EvidencePacket
from thesistester.assistant.llm import StructuredLLMClient
from thesistester.assistant.llm_explainer import (
    LLMEvidenceError,
    _path_exists,
    _path_get,
    assert_llm_explanation_grounded,
    merge_mandatory_packet_caveats,
)

RESULTS_QA_CHANNEL = "results_qa"

_RESULTS_QA_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "caveats", "claims", "followups"],
    "properties": {
        "summary": {"type": "string"},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "path"],
                "properties": {
                    "text": {"type": "string"},
                    "path": {"type": "string"},
                },
            },
        },
        "followups": {"type": "array", "items": {"type": "string"}},
    },
}

_SYSTEM_PROMPT = (
    "Answer only from the supplied evidence JSON using structured claims. "
    "Each claim.text that includes a number must cite claim.path to an existing "
    "packet field. claim.path must be an exact dotted key path already present "
    "in the supplied JSON; do not invent nested keys. Do not add calculations, "
    "forecasts, trade advice, tools, or facts absent from the packet. "
    "Distinguish in-sample observed results from robustness/OOS evidence. "
    "When answering best SL/TP or best entry-time questions, cite "
    "results.projections.* (or results.best_grid_result when projections are "
    "absent) and state the ranking metric, candidate set / eligible count, "
    "min_trades filter, and in-sample vs OOS status from the evidence. "
    "Do not invent rankings or choose a ranking metric. "
    "When evidence for the question is missing, say so in caveats and propose "
    "followups. Prefer number-free followups. Preserve uncertainty and caveats."
)


@dataclass(frozen=True)
class ResultsQAReply:
    """Grounded multi-turn results reply; claims carry server-resolved values."""

    summary: str
    caveats: tuple[str, ...]
    claims: tuple[EvidenceClaim, ...] = ()
    followups: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "caveats": list(self.caveats),
            "claims": [claim.to_dict() for claim in self.claims],
            "followups": list(self.followups),
        }


def format_results_qa_reply_content(reply: ResultsQAReply) -> str:
    """Build persisted assistant ``content`` for a results Q&A turn.

    Includes path-cited claims so Discuss results threads remain auditable in
    plain ``content`` (not only in structured message fields).
    """
    lines = [reply.summary.strip()]
    if reply.claims:
        lines.append("")
        lines.append("Claims:")
        for claim in reply.claims:
            lines.append(f"- `{claim.path}` = {claim.value} — {claim.text}")
    if reply.caveats:
        lines.append("")
        lines.append("Caveats:")
        lines.extend(f"- {item}" for item in reply.caveats)
    if reply.followups:
        lines.append("")
        lines.append("Follow-ups:")
        lines.extend(f"- {item}" for item in reply.followups)
    return "\n".join(lines).strip()


def filter_results_qa_history(
    messages: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    max_history_messages: int,
) -> tuple[dict[str, Any], ...]:
    """Return the last N results_qa messages for ``run_id`` (excluding tools)."""
    if not isinstance(max_history_messages, int) or max_history_messages < 0:
        raise ValueError("max_history_messages must be a non-negative integer.")
    selected: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        if message.get("channel") != RESULTS_QA_CHANNEL:
            continue
        if message.get("run_id") != run_id:
            continue
        role = str(message.get("role") or "").strip().lower()
        if role not in {"user", "human", "assistant", "ai"}:
            continue
        selected.append(dict(message))
    if max_history_messages == 0:
        return ()
    return tuple(selected[-max_history_messages:])


def propose_results_reply(
    client: StructuredLLMClient,
    *,
    packet: EvidencePacket,
    history: Sequence[Mapping[str, Any]],
    user_message: str,
    turn_context: Mapping[str, Any] | None = None,
) -> ResultsQAReply:
    """Request a grounded results reply from the ephemeral turn evidence context.

    ``turn_context`` may include ``results.projections.*`` (RQ-2). Path
    resolution and numeric grounding audit that same object. When omitted, the
    immutable packet dict is used (RQ-1 behavior).
    """
    if not isinstance(user_message, str) or not user_message.strip():
        raise LLMEvidenceError("Results Q&A user message must be a non-empty string.")
    if turn_context is None:
        evidence_context: dict[str, Any] = packet.to_dict()
    else:
        if not isinstance(turn_context, Mapping):
            raise LLMEvidenceError("Results Q&A turn_context must be a mapping.")
        evidence_context = dict(turn_context)
    history_lines = [
        {
            "role": message.get("role"),
            "content": message.get("content"),
        }
        for message in history
        if isinstance(message, Mapping)
    ]
    user_payload = {
        "evidence_packet": evidence_context,
        "history": history_lines,
        "user_message": user_message.strip(),
    }
    payload = client.complete_structured(
        system=_SYSTEM_PROMPT,
        user=json.dumps(user_payload, sort_keys=True),
        schema=_RESULTS_QA_SCHEMA,
    )
    if set(payload) != {"summary", "caveats", "claims", "followups"}:
        raise LLMEvidenceError(
            "Results Q&A reply must contain only summary, caveats, claims, and followups."
        )
    summary = payload["summary"]
    caveats = payload["caveats"]
    claims_raw = payload["claims"]
    followups_raw = payload["followups"]
    if (
        not isinstance(summary, str)
        or not summary.strip()
        or not isinstance(caveats, list)
        or not isinstance(claims_raw, list)
        or not isinstance(followups_raw, list)
    ):
        raise LLMEvidenceError("Results Q&A reply has invalid field types.")
    if any(not isinstance(caveat, str) or not caveat.strip() for caveat in caveats):
        raise LLMEvidenceError("Results Q&A caveats must be non-empty strings.")
    if any(not isinstance(followup, str) or not followup.strip() for followup in followups_raw):
        raise LLMEvidenceError("Results Q&A followups must be non-empty strings.")
    claims: list[EvidenceClaim] = []
    for item in claims_raw:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"text", "path"}
            or not isinstance(item.get("text"), str)
            or not item["text"].strip()
            or not isinstance(item.get("path"), str)
            or not item["path"].strip()
        ):
            raise LLMEvidenceError("Results Q&A claims must be non-empty text/path objects.")
        path = item["path"].strip()
        if not _path_exists(evidence_context, path):
            raise LLMEvidenceError(
                f"Results Q&A claim path {path!r} is missing from the evidence packet."
            )
        claims.append(
            EvidenceClaim(
                text=item["text"].strip(),
                path=path,
                value=_path_get(evidence_context, path),
            )
        )
    grounded = tuple(claims)
    summary_text = summary.strip()
    caveat_texts = merge_mandatory_packet_caveats(
        packet, tuple(caveat.strip() for caveat in caveats)
    )
    followup_texts = tuple(followup.strip() for followup in followups_raw)
    assert_llm_explanation_grounded(
        packet,
        summary=summary_text,
        caveats=caveat_texts,
        claims=grounded,
        followups=followup_texts,
    )
    return ResultsQAReply(
        summary=summary_text,
        caveats=caveat_texts,
        claims=grounded,
        followups=followup_texts,
    )
