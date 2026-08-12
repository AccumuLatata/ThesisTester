# Research Study Runner examples

Operator contract: [`docs/STUDY_RUNNER.md`](../../docs/STUDY_RUNNER.md)  
Plan: [`docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md`](../../docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md)

| File | Cells | Notes |
|---|---|---|
| `pdPOC_ma_confluence_battery.yaml` | **40** (active `stage.filter`) | Stage-first default. Full cartesian **800** documented as phase-2 in file comments. |

CI unit/golden tests continue to use the miniature `tests/fixtures/study/` (2×2×2), not this example.

```bash
python -m thesistester study expand examples/studies/pdPOC_ma_confluence_battery.yaml \
  --output-dir out/pdPOC_stage40
python -m thesistester study run examples/studies/pdPOC_ma_confluence_battery.yaml \
  --output-dir out/pdPOC_stage40 --confirm
python -m thesistester study report out/pdPOC_stage40
python -m thesistester study promote out/pdPOC_stage40 \
  --output examples/studies/pdPOC_survivors_draft.yaml --top-n 10
```

Replace `dataset.path` before `study run`. Promote writes a **draft** only — edit and confirm before re-running.
