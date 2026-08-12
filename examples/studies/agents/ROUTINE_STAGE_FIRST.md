# Copy-ready: stage-first study pass (40 cells)

**Context for external agent:** run a stage-first Research Study on the shipped
example. Do not invent axes. Do not chain promote→run without human confirm.
Full pack: `docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md`.

```text
You are an external ThesisTester coworker. Follow docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md
and examples/studies/agents/SYSTEM.md hard rules.

Task: stage-first pass on examples/studies/pdPOC_ma_confluence_battery.yaml.

1. Ensure dataset.path in the StudySpec points at a real local CSV (ask human if missing).
2. Expand:
   python -m thesistester study expand \
     examples/studies/pdPOC_ma_confluence_battery.yaml \
     --output-dir out/pdPOC_stage40
   Report run_count (expect 40 with the active stage.filter).
3. Run (add --confirm if run_count >= confirm_above_runs):
   python -m thesistester study run \
     examples/studies/pdPOC_ma_confluence_battery.yaml \
     --output-dir out/pdPOC_stage40 --confirm
4. Report:
   python -m thesistester study report out/pdPOC_stage40
   Summarize ranked / low-N / unresolved with honesty + min_trades + multiple-testing.
   Prefer index profit_factor / win_rate when present (RS-D7).
5. Promote draft only:
   python -m thesistester study promote out/pdPOC_stage40 \
     --output drafts/pdPOC_survivors_draft.yaml --top-n 10
   If that draft path already exists, promote refuses unless you pass --force
   (ask the human first; never silent overwrite).
   STOP. Tell the human the draft path and that they must edit + confirm before
   any second expand/run. Do not auto-run the draft.
```
