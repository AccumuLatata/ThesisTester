"""Normalized candidate-level adapter for strict 3c detection."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class CandidateLevel:
    source_mode: str
    zone_id: str | None
    level_id: str | None
    level_price: float
    zone_low: float | None
    zone_high: float | None
    direction: str
    source_label: str | None
    bar_index: int
    timestamp: Any
    metadata: dict[str, Any]


def _split_zone_levels(zone: pd.Series) -> list[tuple[str, float]]:
    names_raw = zone.get("level_names", "")
    prices_raw = zone.get("level_prices", "")
    names = str(names_raw).split("|") if pd.notna(names_raw) else []
    prices = str(prices_raw).split("|") if pd.notna(prices_raw) else []
    pairs: list[tuple[str, float]] = []
    for name, price_raw in zip(names, prices):
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            continue
        pairs.append((str(name).strip(), price))
    return pairs


def _mode_label(confluence_mode: str) -> str:
    return "user_anchor" if confluence_mode == "anchor_rules" else "global_cluster"


def from_global_cluster_zones(zones: pd.DataFrame, direction: str) -> list[CandidateLevel]:
    if zones is None or zones.empty:
        return []
    out: list[CandidateLevel] = []
    for row_idx, zone in zones.reset_index(drop=True).iterrows():
        bar_idx = int(zone["bar_index"])
        zone_id = f"global_cluster_bar{bar_idx}_{row_idx}"
        for level_name, level_price in _split_zone_levels(zone):
            out.append(
                CandidateLevel(
                    source_mode="global_cluster",
                    zone_id=zone_id,
                    level_id=level_name or None,
                    level_price=float(level_price),
                    zone_low=float(zone["zone_low"]) if pd.notna(zone.get("zone_low")) else None,
                    zone_high=float(zone["zone_high"]) if pd.notna(zone.get("zone_high")) else None,
                    direction=direction,
                    source_label=str(zone.get("level_names", "")) or None,
                    bar_index=bar_idx,
                    timestamp=zone.get("timestamp"),
                    metadata={
                        "level_count": zone.get("level_count"),
                        "confluence_mode": "global_cluster",
                    },
                )
            )
    return out


def from_anchor_zones(zones: pd.DataFrame, direction: str) -> list[CandidateLevel]:
    if zones is None or zones.empty:
        return []
    out: list[CandidateLevel] = []
    for row_idx, zone in zones.reset_index(drop=True).iterrows():
        bar_idx = int(zone["bar_index"])
        zone_id = f"anchor_rules_bar{bar_idx}_{row_idx}"
        anchor_level = zone.get("anchor_level")
        for level_name, level_price in _split_zone_levels(zone):
            out.append(
                CandidateLevel(
                    source_mode="user_anchor",
                    zone_id=zone_id,
                    level_id=level_name or None,
                    level_price=float(level_price),
                    zone_low=float(zone["zone_low"]) if pd.notna(zone.get("zone_low")) else None,
                    zone_high=float(zone["zone_high"]) if pd.notna(zone.get("zone_high")) else None,
                    direction=direction,
                    source_label=str(anchor_level) if pd.notna(anchor_level) else None,
                    bar_index=bar_idx,
                    timestamp=zone.get("timestamp"),
                    metadata={
                        "level_count": zone.get("level_count"),
                        "confluence_mode": _mode_label(str(zone.get("confluence_mode", "anchor_rules"))),
                        "anchor_level": anchor_level,
                        "anchor_price": zone.get("anchor_price"),
                        "valid_confluence_count": zone.get("valid_confluence_count"),
                    },
                )
            )
    return out


def with_metadata(candidate: CandidateLevel, **extra: Any) -> CandidateLevel:
    merged = dict(candidate.metadata)
    merged.update(extra)
    return replace(candidate, metadata=merged)
