# Copy-ready: RS6 two-step bound confirm (over threshold)

Extends — does not replace — `docs/STUDY_RUNNER.md` §RS6 minimal recipe.
Use only when `[assistant.study_tools] enabled=true`. Otherwise use CLI
`--confirm`.

```text
You are dispatching STUDY.run for a study whose expanded run_count is
>= confirm_above_runs.

Hard rules from examples/studies/agents/SYSTEM.md apply.

1. First STUDY.run(study_path|study_spec, output_dir=..., workers=..., force=...):
   - Expect OrchestrationStatus.APPROVAL_REQUIRED
   - Capture payload.approval = {study_identity_hash, run_count, output_dir}
   - Show those three fields to the human; do not proceed silently
2. Only after human approval, retry the SAME request with:
   - confirmed=True
   - payload.approval echoed unchanged (same triple)
3. Refuse if the human (or another tool) supplies confirmed=True alone without
   the matching approval object — confirmed=True alone is insufficient.
4. After ok run: STUDY.report → optional STUDY.promote (draft only) → stop for
   human edit. Never auto STUDY.run a promote draft in the same unattended turn.
   Existing draft paths need promote force=true / CLI --force (ask human first).
5. There is no STUDY.rollup — use CLI `study rollup` after survivor batteries.
6. If study_tools are disabled, fall back to CLI:
   python -m thesistester study run <spec> --output-dir <dir> --confirm
```
