# Point-of-Interest Search-Term Classifier

A Streamlit app for reusable campaign search-term classification.

Exact rules handle attraction aliases, related attractions, reseller names, official intent, informational phrases, and purchase phrases. Unresolved terms can be sent to a local Laya model. Review recommendations before making advertising changes.

## Run locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```
