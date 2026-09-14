# mypy per-file ratchet (QR-B B-11 / QI-12-05)

Path-scoped `--strict --ignore-missing-imports` on `thesistester/engine` and
`thesistester/analytics` only. Not repo-wide. `api.py` later.

QI-12 §2.3 five-tree probe (engine + analytics + `api.py` + `data/` +
`levels/`) was **164** strict. This baseline ratchets `engine/` +
`analytics/` paths only. Import-pulled errors (`api.py` and others) are
logged, not ratcheted — those trees are later. B-11 recorded **97**
in-scope errors (17 files). `--no-site-packages` keeps numpy stubs from
aborting a 3.10-target run.

The CI job `mypy (informational)` is **not** a G-1 required check. Type
errors and ratchet increases emit `::warning` and stay green. Config/runtime
crashes still fail. Do not invoke mypy from required pytest cells. Schema
tests in `tests/test_mypy_ratchet.py` must collect on 3.10 (`tomli`
fallback; `tomllib` is 3.11+).

## Command

```bash
python -m tests.fixtures.mypy.check_ratchet
```

Write a fresh baseline after an intentional error-count drop:

```bash
python -m tests.fixtures.mypy.check_ratchet --write-baseline
```

Config SoT: `pyproject.toml` `[tool.mypy]`. Baseline: `baseline.json`.
Monotonically decreasing per release — do not raise the committed total.
