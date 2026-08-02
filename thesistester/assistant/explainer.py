"""Grounded, deterministic research-result explanation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from thesistester.reporting import build_research_artifact, to_jsonable


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class EvidencePacket:
    """Immutable JSON-safe evidence allowed to support an assistant explanation."""

    provenance: Mapping[str, Any]
    assumptions: Mapping[str, Any]
    results: Mapping[str, Any]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        object.__setattr__(self, "assumptions", _freeze(self.assumptions))
        object.__setattr__(self, "results", _freeze(self.results))

    def to_dict(self) -> dict[str, Any]:
        return {
            "provenance": _thaw(self.provenance),
            "assumptions": _thaw(self.assumptions),
            "results": _thaw(self.results),
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
    trade_count = trade_summary.get("trade_count") if isinstance(trade_summary, Mapping) else None
    if isinstance(trade_count, (int, float)) and not isinstance(trade_count, bool):
        if trade_count < 30:
            warnings.append("Trade count is below the 30-trade screening threshold.")
    else:
        warnings.append("Trade count is unavailable; sample-size screening cannot be assessed.")
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
