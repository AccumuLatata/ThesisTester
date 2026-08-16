# Research Study Runner examples

Operator contract: [`docs/STUDY_RUNNER.md`](../../docs/STUDY_RUNNER.md)  
Plan: [`docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md`](../../docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md)  
Study Viewer (SV1–SV4 shipped: catalog + `study list` + quality panes + overview charts + cell peek): [`docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md`](../../docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md)  
External Grok routine pack (RS-D5): [`docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md`](../../docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md) · [`agents/`](agents/)

| File | Cells | Notes |
|---|---|---|
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

`dopen_ma_3c_mnq.yaml` enables `grid` (20 SL/TP cells per run, inside the $40 / $500 MNQ envelope). Time-of-day expectancy is **not** expanded as a factor: after a cell finishes, rank `entry_rth_segment` / `entry_hour_bucket` on that cell's trades via the Time Analysis page or `thesistester.api.run_time_analysis`.
