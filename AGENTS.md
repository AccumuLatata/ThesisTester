# AGENTS.md

## Cursor Cloud specific instructions

ThesisTester is a single, self-contained Python **Streamlit** app (no database, no external
services). Data comes from CSV uploads or the bundled `sample_data/ES_sample_1m.csv`; state
persists to a local `.thesistester_store/` directory on disk.

Standard commands are in `README.md` (`pip install -r requirements.txt`, `streamlit run app.py`,
`pytest -q`). Notes specific to this environment:

- Dependencies install to `~/.local` and their console scripts are **not on PATH**. Invoke tools
  via the module form: `python3 -m pytest -q`, `python3 -m streamlit run app.py`.
- Run the dev server headless on port 8501:
  `python3 -m streamlit run app.py --server.port 8501 --server.headless true`.
- There is **no lint tooling configured** (no ruff/flake8/black/pre-commit). "Lint" is limited to
  `python3 -m py_compile`. Do not assume a lint command exists.
- The full test suite (~1477 tests) runs fully offline in well under a minute; no fixtures or
  services need to be started first.
