# Security

ThesisTester is a research backtester. This file records the G-4 scan
envelope (QI-12-06 / QI-07-09). It is not a fill-correctness claim.

## CI scanners (warn-first)

- `bandit (warn-first)` — `bandit -ll` on `thesistester`. **High must stay 0**
  (`tests/test_g4_security_scans.py`). Medium `urlopen` (B310 in assistant
  LLM/voice) is warn-first. Blocking flip is a later PR.
- `pip-audit (warn-first)` — declared + transitive packages from
  `pip install -e . -c constraints.txt`, using the locked `pip-audit>=2.7,<3`
  spec. A missing advisory report (no "vulnerabilit" text) fails the job.
  Advisories emit `::warning`. Blocking flip is a later PR.

Neither job is one of the six G-1 required display names.

## Build / Actions

- `[build-system]` requires `setuptools>=83,<85` (clears PYSEC-2025-49 /
  2026-1918 / 2026-3447).
- GitHub Actions in `.github/workflows/ci.yml` are pinned to v7.x commit
  SHAs (`checkout`, `setup-python`, `upload-artifact`).

## Study run-name fingerprints

`thesistester.study.naming.factor_cell_fingerprint` is a 10-hex SHA-1 of
canonical factor JSON with `usedforsecurity=False`. It is a filesystem
disambiguator, not a credential hash. The digest is unchanged; RS2 golden
run names stay identical. Switching to SHA-256 is a dedicated identity PR.

## Reporting

Open a GitHub issue or security advisory on
[AccumuLatata/ThesisTester](https://github.com/AccumuLatata/ThesisTester).
Do not commit live API keys; `.env` / Streamlit secrets stay gitignored.
