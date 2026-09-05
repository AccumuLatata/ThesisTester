# Program B Run 2 StudySpecs

Bot runbook (normative): [`docs/PROGRAM_B_OPERATOR_RUNBOOK.md`](../../../docs/PROGRAM_B_OPERATOR_RUNBOOK.md) §1 Run 2 lock table.
Generator: [`generate_program_b_yaml.py`](../program_b/generate_program_b_yaml.py).

**15s packet:** 23 studies / **944** cells (`manifest.yaml`). Trigger `fade` @ 1min, `same_bar_opposite_direction: raise`, `report.random_baseline.n_replicas: 50`.
Study names are `progB_r2_*` so `output_dir` does not collide with Run 1.
Filenames stay `progB_*.yaml` so the validator Wave 0 / smoke stems still match.
Do not hand-edit token lists. Do not treat Run 1 vs Run 2 as a paired ΔE.

```bash
python3 examples/studies/program_b/generate_program_b_yaml.py \
  --trigger fade --output-dir examples/studies/program_b_run2
# fade defaults the rest of the Run 2 lock table: raise, baseline 50, packet 15s, prefix r2.
PYTHONPATH=. python3 examples/studies/program_b/validate_program_b_yaml.py \
  examples/studies/program_b_run2/manifest.yaml
```

Expect: `ok 23 studies / 944 cells`.
