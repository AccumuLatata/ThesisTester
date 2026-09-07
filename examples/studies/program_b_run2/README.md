# Program B Run 2 StudySpecs

Bot runbook (normative): [`docs/PROGRAM_B_OPERATOR_RUNBOOK.md`](../../../docs/PROGRAM_B_OPERATOR_RUNBOOK.md) §1 Run 2 lock table.
Generator: [`generate_program_b_yaml.py`](../program_b/generate_program_b_yaml.py).

**15s packet:** 20 studies / **898** cells (`manifest.yaml`). Trigger `fade` @ 1min, `same_bar_opposite_direction: raise`, `report.random_baseline.n_replicas: 50`.
**Tick-gated packet:** 8 studies / **253** cells (`manifest_tick.yaml`) — Wave 0 VA + Wave 0 APOC solos + Wave 4 + Wave 7. Placeholder `tick_paths: [data/mnq_tick_last.csv]`; launch refuses until a real Tick–Tick–Last export is pinned.
Study names are `progB_r2_*` so `output_dir` does not collide with Run 1.
Filenames stay `progB_*.yaml` so the validator Wave 0 / smoke stems still match.
15s levels set `apoc_enabled: false` and `poc_windows: []` so product tick defaults cannot refuse a 15s-only launch. `POC_rolling_30min` is not a Program B core wave.
Do not hand-edit token lists. Do not treat Run 1 vs Run 2 as a paired ΔE.

```bash
python3 examples/studies/program_b/generate_program_b_yaml.py \
  --trigger fade --output-dir examples/studies/program_b_run2
# fade defaults the rest of the Run 2 lock table: raise, baseline 50, packet both, prefix r2.
PYTHONPATH=. python3 examples/studies/program_b/validate_program_b_yaml.py \
  examples/studies/program_b_run2/manifest.yaml
PYTHONPATH=. python3 examples/studies/program_b/validate_program_b_yaml.py \
  examples/studies/program_b_run2/manifest_tick.yaml
```

Expect: `ok 20 studies / 898 cells` and `ok 8 studies / 253 cells`.
