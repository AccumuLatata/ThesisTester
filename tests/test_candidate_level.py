from __future__ import annotations

import pandas as pd

from thesistester.engine.candidate_level import from_anchor_zones, from_global_cluster_zones


def test_from_global_cluster_zones_creates_per_level_candidates():
    zones = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-01 09:30:00", tz="America/New_York"),
                "bar_index": 3,
                "zone_low": 100.0,
                "zone_high": 100.5,
                "level_count": 2,
                "level_names": "A|B",
                "level_prices": "100.0|100.5",
            }
        ]
    )
    candidates = from_global_cluster_zones(zones, direction="both")
    assert len(candidates) == 2
    assert {c.level_id for c in candidates} == {"A", "B"}
    assert all(c.source_mode == "global_cluster" for c in candidates)


def test_from_anchor_zones_maps_source_mode_to_user_anchor():
    zones = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-01 09:30:00", tz="America/New_York"),
                "bar_index": 1,
                "zone_low": 100.0,
                "zone_high": 101.0,
                "level_count": 2,
                "level_names": "anchor|rule_1",
                "level_prices": "100.0|101.0",
                "confluence_mode": "anchor_rules",
                "anchor_level": "anchor",
                "anchor_price": 100.0,
                "valid_confluence_count": 1,
            }
        ]
    )
    candidates = from_anchor_zones(zones, direction="long")
    assert len(candidates) == 2
    assert all(c.source_mode == "user_anchor" for c in candidates)
    assert all(c.direction == "long" for c in candidates)
