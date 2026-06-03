# ThesisTester

Simple Streamlit app for intraday strategy research on futures data.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Run tests

```bash
pytest -q
```

## Phase 1 status

Phase 1 data layer supports CSV OHLCV ingestion, timezone normalization, validation,
base-interval inference, RTH/ETH session tagging, and OHLCV resampling (1min, 5min,
15min, 30min, 1h, 4h, 1D).
