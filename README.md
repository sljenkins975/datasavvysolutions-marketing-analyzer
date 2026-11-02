# Data Savvy Solutions | Marketing Performance Analyzer

An interactive Streamlit portfolio demonstration with **synthetic marketing data**.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On Windows, activate with `.venv\\Scripts\\activate`.

## Features

- KPIs: spend, impressions, clicks, CTR, conversions, conversion rate, CPC, CPA and ROAS
- Platform, campaign and date filters
- Trend and channel charts
- CSV upload, sample download, filtered export
- Deterministic synthetic data

CSV columns: `date,platform,campaign,spend,impressions,clicks,conversions,revenue`.

## Tests

```bash
python -m unittest discover -s tests
```

## Deployment

Deploy via [Streamlit Community Cloud](https://share.streamlit.io/) using this repository and `app.py` as the entrypoint. Do not upload private client data to a public demo.

## License

MIT.
