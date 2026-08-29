# Research Study Runner examples

Operator contract: [`docs/STUDY_RUNNER.md`](../../docs/STUDY_RUNNER.md)  
Level-as-anchor desk funnel (Program A; not these teaching cartesians; required
`dVWAP`, `min_valid: 1`, no `factors.otf`):
[`docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md`](../../docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md)  
Holistic combination concept (Program B):
[`docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md`](../../docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md)  
Program B bot packet (15s: 23 YAMLs / 944 cells; tick-gated VA: 4 YAMLs / 207 cells):
[`program_b/`](program_b/) · [`docs/PROGRAM_B_OPERATOR_RUNBOOK.md`](../../docs/PROGRAM_B_OPERATOR_RUNBOOK.md)  
Plan: [`docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md`](../../docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md)  
Study Viewer (SV1–SV5 shipped: catalog + `study list` + quality panes + overview charts + cell peek + trader briefing / grid / NY ToD): [`docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md`](../../docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md)  
External Grok routine pack (RS-D5): [`docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md`](../../docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md) · [`agents/`](agents/)

| File | Cells | Notes |
|---|---|---|
| `pRTH_open_ma.yaml` | **32** | Operator MNQ History Exporter **15s-primary** template (UTC naive stamps, one MA per partner row, touch/3c × 1m/5m × long/short, `workers: 1`). Build **Start from example** default. Replace `dataset.path` with the same 15s Quantower CSV used on Data. |
| `pdPOC_ma_confluence_battery.yaml` | **40** (active `stage.filter`) | Stage-first **15s-primary** teaching example (`ingestion_mode: 15s_primary_derive_1m`, Quantower 15s path, `subtimeframe_conservative`). Full cartesian **800** documented as phase-2 in file comments. |
| `dopen_ma_3c_mnq.yaml` | **8** | **Legacy 1m primary.** dOpen × EMA21/SMA50 (1m, 5m), 3c on 1m, MNQ. Grid on ($40 / $500 cap, $0.50/side). Will not match Data-page 15s-primary on the same dates. Replace `dataset.path` if the Quantower CSV moves. Time-of-day R is post-run (`run_time_analysis`), not a factor axis. |
| `agents/` | — | RS-D5 copy-ready prompts for external coworkers (CLI / optional STUDY.*) |

CI unit/golden tests continue to use the miniature `tests/fixtures/study/` (2×2×2), not this example.

```bash
python -m thesistester study expand examples/studies/pdPOC_ma_confluence_battery.yaml \
  --output-dir out/pdPOC_stage40
python -m thesistester study run examples/studies/pdPOC_ma_confluence_battery.yaml \
  --output-dir out/pdPOC_stage40 --confirm
python -m thesistester study report out/pdPOC_stage40
python -m thesistester study promote out/pdPOC_stage40 \
  --output drafts/pdPOC_survivors_draft.yaml --top-n 10
```

```bash
python -m thesistester study expand examples/studies/dopen_ma_3c_mnq.yaml \
  --output-dir out/dopen_ma_3c_mnq
python -m thesistester study run examples/studies/dopen_ma_3c_mnq.yaml \
  --output-dir out/dopen_ma_3c_mnq
python -m thesistester study report out/dopen_ma_3c_mnq
```

Replace `dataset.path` before `study run` (promote absolutizes relative paths when possible). For pdPOC, that path must be the same 15s Quantower export used on Data. Promote writes a **draft** only — edit and confirm before re-running; use `--force` to overwrite an existing draft. The phase-2 **800**-cell path is “remove/widen `stage` on this example,” not on a narrowed promote draft.

Both `pRTH_open_ma.yaml` and `dopen_ma_3c_mnq.yaml` may enable a **per-cell SL/TP grid** (`constants.grid`). That grid is **not** the factor cartesian shown as Ranked cells — Inspect **Study briefing** / Cell peek now project `best_grid_*` and `grid_results.parquet`. Time-of-day expectancy is **not** expanded as a factor: after a cell finishes, Inspect shows NY `entry_rth_segment` on that cell's trades (post-hoc). To constrain the next run, set `constants.entry_window` (Admit) rather than adding a 7-bucket factor axis.
