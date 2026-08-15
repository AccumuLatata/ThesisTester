# Research Study Runner — External Grok Bot routine pack (RS-D5)

**Status:** RS-D5 ✅  
**Depends on:** RS1–RS5 MVP, **RS-D7** (index `profit_factor` / `win_rate`), **RS6** (default-off `STUDY.*` + minimal confirm recipe), benefits from RS-D2 viewer + RS-D4 rollup + RS-D8 preview. RS-D9 may spawn the same CLI from Studies — not a second contract.  
**Operator contract:** [`STUDY_RUNNER.md`](STUDY_RUNNER.md)  
**Plan:** [`STUDY_RUNNER_IMPLEMENTATION_PLAN.md`](STUDY_RUNNER_IMPLEMENTATION_PLAN.md) §12.6  
**Copy-ready prompts:** [`examples/studies/agents/`](../examples/studies/agents/)

This pack is for an **external coworker** (e.g. Grok Bot) that shells the Study
Runner CLI — or optionally dispatches RS6 `STUDY.*` capabilities when
`[assistant.study_tools] enabled=true`. It **extends** the RS6 minimal confirm
recipe; it does not fork a second confirm contract.

ThesisTester does **not** embed Grok, host multi-agent queues, or ship an MCP
server for this surface.

---

## Non-goals (hard)

| Forbidden | Why |
|---|---|
| Invent factor axes / setups / level tokens | Closed StudySpec only; unknown axes fail validate |
| Bypass `--confirm` / bound approval | Large studies require human confirm |
| Auto-execute promote drafts | Promote writes a **draft** StudySpec; human must edit + reconfirm |
| Treat ranked cells / OTF Δ / rollup as proof of edge | Multiple-testing + descriptive screening |
| Enable `grid` / `validation` / `walk_forward` via bare `{}` | R18 default-on trap; always set `enabled: true\|false` |
| Rely on an in-product MCP server or RabbitMQ host | Out of scope for RS; CLI is the durable contract |
| Mutate classic Streamlit research session state | Studies viewer (RS-D2) is read-only; runner stays headless |

---

## Surfaces the bot may use

| Surface | When | Notes |
|---|---|---|
| CLI `python -m thesistester study …` | **Always preferred** | Works with `assistant.study_tools.enabled=false` |
| RS6 `STUDY.expand\|run\|report\|promote` | Opt-in only | Same APIs; handlers refuse when flag off |
| Studies viewer (RS-D2 / RS-D8) | Human inspect + preview | Artifacts-only inspect; YAML preview; no in-process execute |
| Studies CLI-launch (RS-D9) | Human convenience | Spawns the same `study run` argv; not a second runner; two-step confirm on the **pinned** hash |
| Studies Build (SB1–SB3) | Humans may author YAML via **Build StudySpec** | Coworkers still CLI; Apply to Preview then existing Validate / Preview → Run via CLI |
| `study rollup` (RS-D4) | After survivor batteries | Compose-only; `not_run` when batteries off |

RS6 confirm (over `confirm_above_runs`) remains:

1. First `STUDY.run` → `APPROVAL_REQUIRED` with  
   `payload.approval = {study_identity_hash, run_count, output_dir}`.
2. Retry with `confirmed=True` **and** the same approval echoed.
3. `confirmed=True` alone is **not** sufficient.

CLI equivalent: pass `--confirm` when `run_count >= confirm_above_runs`
(default 200). See `STUDY_RUNNER.md` §RS6 — do not invent a weaker gate here.

---

## End-to-end routine (stage-first → survivors → optional diagnostics)

Replace `DATASET` / paths with repo-local files. Prefer the stage-first example
(`examples/studies/pdPOC_ma_confluence_battery.yaml` → **40** cells). On a 15s
Quantower file, coworkers must set `dataset.ingestion_mode: 15s_primary_derive_1m`
(plus Quantower profile and `intrabar_model: subtimeframe_conservative`); omitted
mode is a different experiment. Do not run the phase-2 **800**-cell cartesian in
CI or as a first pass.

### 0) Preconditions

- Closed StudySpec YAML already authored (human or prior draft). Bot may
  **edit** YAML only inside declared factor domains / constants; never invent
  new axes.
- Dataset path valid; prefer non-zero `commission_per_side` /
  `slippage_ticks` before trusting ranks.
- If using assistant tools: set `[assistant.study_tools] enabled=true` only
  after operator opt-in. Otherwise shell CLI.

### 1) Expand (preview cell count)

```bash
python -m thesistester study expand \
  examples/studies/pdPOC_ma_confluence_battery.yaml \
  --output-dir out/pdPOC_stage40
```

Report `run_count` / identity hash from expansion artifacts. Stop if the count
is unexpected (wrong stage filter, missing dataset rewrite, etc.).

### 2) Confirm + run

```bash
# Required when run_count >= study.confirm_above_runs (example is 40 → usually no CLI --confirm;
# full 800 or confirm_above_runs≤40 needs --confirm).
python -m thesistester study run \
  examples/studies/pdPOC_ma_confluence_battery.yaml \
  --output-dir out/pdPOC_stage40 \
  --confirm
```

Optional RS6 path: two-step bound approval (see above). Soft-resume is default;
use `--force` only when the operator explicitly requests a wipe.

### 3) Report (honesty required)

```bash
python -m thesistester study report out/pdPOC_stage40
```

When summarizing to humans, **always** surface:

- Overview honesty / `multiple_testing` posture
- `min_trades` low-N exclusions (sample-size filter ≠ significance)
- Ranked vs low-N vs unresolved primary
- **RS-D7:** prefer index `profit_factor` / `win_rate` when present
  (`profit_factor_source=index`); else bundle fallback
- OTF Δ is descriptive under the same multiple-testing caveats

Optional human inspect: Streamlit **Studies** page (read-only) on the same
`output_dir`.

### 4) Promote draft (never auto-run)

```bash
python -m thesistester study promote out/pdPOC_stage40 \
  --output drafts/pdPOC_survivors_draft.yaml \
  --top-n 10
# Existing draft path → add --force only after explicit human approval
```

Stop. Tell the human: draft only; edit constants/dataset/stage; confirm before
any second execute. Refuse to chain `study run` on the draft in the same
unattended turn unless the human explicitly confirmed that draft. Refuse silent
overwrite of an existing draft (CLI `--force` / promote `force=true` only when
asked).

### 5) Human edit → second pass

Typical human edits on the draft:

- Keep `stage.mode: explicit_cells` survivors, or carefully restore selected axes
- Absolutized dataset paths from promote — verify before run
- Optional survivor diagnostics (docs-only; never auto-applied by the bot):

```yaml
# Explicit flags only — never bare {}
walk_forward:
  enabled: true
  # …fold sizes…
grid:
  enabled: true
validation:
  enabled: true
  overfitting:
    enabled: true
```

Then:

```bash
python -m thesistester study expand drafts/pdPOC_survivors_draft.yaml \
  --output-dir out/pdPOC_survivors
python -m thesistester study run drafts/pdPOC_survivors_draft.yaml \
  --output-dir out/pdPOC_survivors --confirm
python -m thesistester study report out/pdPOC_survivors
```

### 6) Optional RS-D4 rollup (compose-only)

```bash
python -m thesistester study rollup out/pdPOC_survivors
```

Expect `not_run` / null batteries when WFA/grid/validation stayed off. Never
claim cross-cell PBO/DSR. See `ASSUMPTIONS_AND_LIMITATIONS.md` (diagnostic
rollup) and `STUDY_RUNNER.md` §RS-D4.

### 7) Phase-2 full cartesian (human-gated only)

Removing/widening `stage` on the **unpromoted** example yields **800** cells —
not on a narrowed promote draft. Require explicit human confirm before expand /
run at that scale. Prefer costs + stage-first survivors first.

---

## Operating rules (checklist)

Copy into the external agent’s system prompt (also in
`examples/studies/agents/SYSTEM.md`):

1. Closed StudySpec only — never invent factor axes, triggers, or level tokens.
2. Prefer CLI; RS6 tools are default-off and refuse when disabled.
3. Never bypass confirm (`--confirm` / bound `payload.approval`).
4. Never auto-run promote drafts; human edit + confirm first; draft overwrite
   needs `--force` / `force=true` only when the human asks.
5. Always mention honesty, `min_trades`, and multiple-testing when ranking.
6. Prefer RS-D7 index `profit_factor` / `win_rate` when present.
7. Do not enable batteries with bare `{}`; dense overfitting needs
   `grid.enabled: true` + parent `validation.enabled: true` +
   `validation.overfitting.enabled: true`; do not invent cross-cell PBO.
   `study rollup` is CLI-only (no `STUDY.rollup`).
8. No MCP server / no product-host embedding assumptions.
9. Studies inspect is read-only; RS-D9 may spawn CLI `study run`
   from Preview — same argv / confirm contract, not a second runner. Agents
   still prefer typing the CLI.
10. Soft-resume by default; run `--force` wipe only on explicit human request
    (distinct from promote overwrite `--force`).

---

## Optional STUDY.* dispatch sketch

When tools are enabled, mirror CLI steps with the same paths. Over threshold:

```text
# 1) STUDY.run(...) → APPROVAL_REQUIRED + payload.approval
# 2) human reviews study_identity_hash, run_count, output_dir
# 3) STUDY.run(..., confirmed=True, payload.approval=<echo>)
# 4) STUDY.report / STUDY.promote as needed
# Promote still produces a draft — do not auto STUDY.run the draft
```

Below threshold, `STUDY.run` matches CLI (no orchestrator gate). Inputs:
`study_path` **or** validated `study_spec` dict; required `output_dir`;
`workers` / `force` parity with CLI. Tools never call `run_batch`.

---

## Related docs

| Doc | Role |
|---|---|
| `STUDY_RUNNER.md` | Living operator contract (RS6 minimal recipe stays there) |
| `ASSUMPTIONS_AND_LIMITATIONS.md` | Ranking + rollup honesty |
| `AGENT_GUIDE.md` | Headless pointers + `study_tools` flag |
| `examples/studies/README.md` | Stage-first example commands |
| `examples/studies/agents/` | Copy-ready prompts for external hosts |
