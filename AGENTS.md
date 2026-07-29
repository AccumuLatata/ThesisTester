# AGENTS.md

## Cursor Cloud specific instructions

ThesisTester is a single-service Streamlit app (Python) for intraday futures strategy
research. There is no database, no external API, and no other services — everything runs
locally and offline. Standard commands live in `README.md`.

### Environment
- Dependencies are installed into a project virtualenv at `.venv` (created by the startup
  update script). Always invoke tools through it, e.g. `.venv/bin/streamlit`,
  `.venv/bin/pytest`, `.venv/bin/python`.
- The venv relies on the system `python3.12-venv` package, which is preinstalled in the
  VM snapshot (not part of the update script).

### Run the app (dev)
- `.venv/bin/streamlit run app.py --server.headless true --server.port 8501`
- Serves on http://localhost:8501. Use the left sidebar to move through the workflow:
  `Data -> Levels -> Setup Builder -> Signals -> Backtest`.
- The `Data` page can load the bundled `sample_data/ES_sample_1m.csv` (via the "Sample
  data" radio option) or an uploaded CSV; no external data source is needed.

### Tests
- `.venv/bin/pytest -q` runs the full offline suite (~1500 tests, ~30s).

### Lint
- No linter is configured in this repo (no ruff/flake8/black config or lint dependency),
  so there is no separate lint step to run.

### Persistence gotcha
- App state (saved setups, saved runs, UI defaults) is written to `.thesistester_store/`
  in the repo root (gitignored). Override its location with the `THESISTESTER_STORE_DIR`
  env var if you need an isolated store.
