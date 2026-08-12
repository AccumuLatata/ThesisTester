# Copy-ready: survivor second pass + optional rollup

After a human has edited a promote draft. Bot must not invent battery configs
beyond what the human requested. Never use bare `{}` for grid/validation/WFA.

```text
You are continuing a Research Study after human edit of a promote draft.
Follow docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md and SYSTEM.md hard rules.

Preconditions (ask human if unclear):
- Draft path (e.g. drafts/pdPOC_survivors_draft.yaml) already human-edited
- Human explicitly confirmed the second execute
- Optional: human asked to enable walk_forward and/or dense overfitting diagnostics
  with explicit enabled: true flags — for overfitting that means grid.enabled,
  parent validation.enabled, and validation.overfitting.enabled (never bare {})

Steps:
1. Expand draft → out/pdPOC_survivors
2. Run with --confirm when required (or RS6 two-step bound approval)
3. study report — honesty / min_trades / multiple-testing; prefer index PF/WR
4. If batteries were enabled on survivors:
   python -m thesistester study rollup out/pdPOC_survivors
   Explain compose-only semantics: missing batteries → not_run; no cross-cell PBO/DSR
5. Do not crown a “validated edge.” Point at ASSUMPTIONS_AND_LIMITATIONS.md.

If the human wants the phase-2 800-cell cartesian, remind them to widen/remove
stage on the unpromoted example (not the narrowed promote draft) and require a
fresh explicit confirm before expand/run.
```
