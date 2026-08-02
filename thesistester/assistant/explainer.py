"""Grounded, deterministic research-result explanation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from thesistester.reporting import build_research_artifact, to_jsonable


@dataclass(frozen=True)
class EvidencePacket:
    """Immutable JSON-safe evidence allowed to support an assistant explanation."""

    provenance: dict[str, Any]
    assumptions: dict[str, Any]
    results: dict[str, Any]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provenance": self.provenance,
            "assumptions": self.assumptions,
            "results": self.results,
            "warnings": list(self.warnings),
        }


def build_evidence_packet(
    state: Mapping[str, Any], *, provenance: Mapping[str, Any]
) -> EvidencePacket:
    """Build bounded explanation evidence from an existing research result only."""
    artifact = build_research_artifact(state)
    results = artifact["results"]
    warnings: list[str] = ["Research results are diagnostics, not proof of edge or trading advice."]
    trade_summary = results.get("trade_summary") or {}
    if isinstance(trade_summary, Mapping) and trade_summary.get("trade_count", 0) < 30:
        warnings.append("Trade count is below the 30-trade screening threshold.")
    if results.get("backtest_intrabar_diagnostic"):
        warnings.append("Intrabar ordering remains model-dependent.")
    return EvidencePacket(
        provenance=to_jsonable(dict(provenance)),
        assumptions={
            "setup_config": artifact["configuration"]["setup_config"],
            "instrument": artifact["configuration"]["instrument"],
            "intrabar": artifact["intrabar"]["backtest_policy"],
            "otf_filter": artifact["otf_filter"],
        },
        results=to_jsonable(results),
        warnings=tuple(warnings),
    )


def explain_evidence(packet: EvidencePacket) -> str:
    """Render a concise explanation containing only packet-backed claims."""
    summary = packet.results.get("trade_summary") or {}
    trades = summary.get("trade_count", "unknown") if isinstance(summary, Mapping) else "unknown"
    expectancy = (
        summary.get("expectancy_r", "unavailable")
        if isinstance(summary, Mapping)
        else "unavailable"
    )
    lines = [
        f"Historical sample: {trades} trades; expectancy R: {expectancy}.",
        "This describes the recorded sample, not a forecast.",
    ]
    lines.extend(f"Caveat: {warning}" for warning in packet.warnings)
    return "\n".join(lines)
