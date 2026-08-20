# External agent routines (RS-D5)

Copy-ready prompts for an **external** coworker (e.g. Grok Bot) that shells the
Study Runner CLI or optionally uses default-off RS6 `STUDY.*` tools.

| File | Purpose |
|---|---|
| [`SYSTEM.md`](SYSTEM.md) | Hard rules / system prompt fragment |
| [`ROUTINE_STAGE_FIRST.md`](ROUTINE_STAGE_FIRST.md) | Stage-first 40-cell expand→run→report→promote |
| [`ROUTINE_CONFIRM_BOUND.md`](ROUTINE_CONFIRM_BOUND.md) | RS6 two-step bound approval (extends minimal recipe) |
| [`ROUTINE_SURVIVOR_DIAGNOSTICS.md`](ROUTINE_SURVIVOR_DIAGNOSTICS.md) | Human-edited draft → second pass → optional rollup |

**Desk contract switch (Notion *Process and roadmap*):** [`docs/LEVEL_ANCHOR_DESK_CONTRACT_SWITCH.md`](../../../docs/LEVEL_ANCHOR_DESK_CONTRACT_SWITCH.md) — keep the old page’s logging/roadmap; absorb protocol locks; do not paste the full plan. Holistic combination concept (Program B, not the desk page): [`docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md`](../../../docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md).

**Full pack (normative):** [`docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md`](../../../docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md)  
**Operator contract:** [`docs/STUDY_RUNNER.md`](../../../docs/STUDY_RUNNER.md)  
**Stage example:** [`../pdPOC_ma_confluence_battery.yaml`](../pdPOC_ma_confluence_battery.yaml)

## Non-goals

- No in-product Grok host, RabbitMQ, or MCP server
- No setup invention; no confirm bypass; no auto-run of promote drafts
- No silent promote overwrite (existing draft paths need `--force` / `force=true`)
- No runtime default changes (`assistant.study_tools` stays default-off)
- No `STUDY.rollup` tool — rollup stays CLI-only
