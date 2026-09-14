# Mutation sample (QR-B B-4 / QI-11-04)

Own-file comparison-swap sample for `engine/backtest.py` and
`analytics/walk_forward.py`. This is the QI-11 §2.2 / §10 recipe, committed
so C-14 / C-17 / C-19 have a measurable ≥ 70 % killed gate (target 80 %).

`[tool.mutmut]` is **not** added to `pyproject.toml` (QI-12 owns packaging).

## Command

```bash
python -m tests.fixtures.mutation.mutate_sample
```

Write a fresh baseline after an intentional sample change:

```bash
python -m tests.fixtures.mutation.mutate_sample --write-baseline
```

Isolation matches QI-11 §10: copy `thesistester/` to a scratch package, run
pytest with `--import-mode=importlib` from a **neutral cwd** so `PYTHONPATH`
mutants are not silently ignored.

## Own-file suites

| Module | Tests |
|---|---|
| `engine/backtest.py` (+ `sim_core.walk_trade_exit`) | `test_phase5_backtest.py`, `test_ah1_session_flatten.py`, `test_golden_master.py`. C-19 moved P7/P4/P6 comparison sites out of `simulate_trades`; the named surface keeps `_validate_simulate_trades`, `_admit_entry_candidates`, `_exposure_skip_for_candidate`, `_finalize_exit_walk`, and `walk_trade_exit` so path-proximity / `next_bar_open` / P0 validation stay in the 12-site sample. |
| `analytics/walk_forward.py` | `test_walk_forward.py` **and** `test_otf_integration.py` (`fold_local` already lives there). Named surface includes C-17 P0/P5 helpers (`_validate_walk_forward_run`, `_stitch_walk_forward_oos`) so overlap-reject and fold-size comparisons stay in the 12-site sample. |

Timeouts count as killed. Comparison sites inside `raise` lines are excluded
from the adjusted rate (QI-11 equivalent-mutant / ValueError-string sites).

Baseline: `baseline.json`. B-4 recorded adjusted kill rates: `backtest.py`
100 % and `walk_forward.py` 100 % (12/12). Gate is not a required CI cell.
