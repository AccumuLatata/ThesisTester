# Anchor-Based Confluence Guide

## Purpose

This guide explains the implemented anchor-confluence workflow in ThesisTester and how it differs from the original global-cluster workflow.

## When to use global cluster vs anchor rules

- **Use `global_cluster`** when you want one shared tolerance across selected levels and are configuring Signals manually.
- **Use `anchor_rules`** when you want one anchor level with per-rule tolerances and required/optional rule control.

## How anchor rules work

1. In Setup Builder, choose **Anchor-based rules**.
2. Select one **anchor level**.
3. Add one or more **confluence levels**.
4. Set each rule's `tolerance_ticks` and `required` flag.
5. Set `min_valid_confluences`.
6. Save the setup.
7. In Signals, choose **Use active setup** or **Use saved setup from library**
   to route to `detect_anchor_confluence_zones()`.

## Required vs optional confluences

- **Required** rules must be valid for a zone to be emitted.
- **Optional** rules can fail and still allow a zone if other checks pass.
- Optional invalid rules are still shown in diagnostics.

## Minimum valid confluences

`min_valid_confluences` is the minimum number of **valid** confluence rules on a bar (`valid_count` includes required rules). Every required rule must also be valid. The engine does **not** add `min_valid` on top of the required set. With all rules required, `min_valid: 1` is enough (Study expand also requires `min_valid <= len(rules)` per cell).

## Example setup

- Anchor: `pdHigh`
- Rules:
  - `VWAP_rolling_1h`, tolerance 4 ticks, required
  - `pdPOC`, tolerance 6 ticks, optional
  - `OR_High`, tolerance 2 ticks, optional
- `min_valid_confluences`: 2

## How signals are generated from anchor zones

When a saved setup uses `anchor_rules`, Signals detects zones with the anchor engine and then sends the resulting zone table into the standard signal-generation flow. Backtest uses the generated signals the same way as global-cluster signals.

## Reading diagnostics

Anchor-zone diagnostics on Signals include:

- anchor level and anchor price
- valid confluence count
- per-rule distance in ticks
- per-rule tolerance
- required/optional flag
- valid/invalid reason

`rule_results` is emitted as JSON by the anchor engine and expanded into a per-rule audit table on the Signals page.

## Research cautions

Per-rule tolerances add degrees of freedom. Excessive tuning can overfit historical data. Compare anchor-rule setups against a global-cluster baseline and prefer out-of-sample or walk-forward validation when optimizing hypotheses.

For systematically testing **locations as anchors** against MAs, rolling VWAPs,
and pivots (NQ/ES intra-day; `dVWAP` not a required partner), the concept is
[`docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md`](LEVEL_COMBINATION_RESEARCH_CONCEPT.md)
and the complete list is
[`docs/LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md`](LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md).
The executed desk funnel (required `dVWAP`) is
[`docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md`](LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md).
Combo attribution (`docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md`) is the retrospective companion.

