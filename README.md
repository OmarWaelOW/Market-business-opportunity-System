# EGY-CRETE Market Opportunity App

Standalone Streamlit workspace for recording regional demand gaps, competitor moves, and input-cost signals. Data persists in `market_opportunities.db`, with bcrypt-hashed accounts and audit attribution on every record.

## Run

```powershell
python -m pip install -r requirements.txt
streamlit run Market_Opportunity_app.py
```

Use **Data import** to load `EGY-CRETE_Market_Data_Synthetic.xlsx` or the tracker workbook. The importer detects the real header row, maps columns by name, skips duplicate records, and tags rows as synthetic or real. The UI recalculates the scoring rules when new records are entered.

On first startup, create the initial account. Later sessions require a username and password; the signed-in display name is recorded on new and edited rows.

## Phase 2 prerequisites

Install R and ensure `Rscript` is on `PATH`. Forecasting uses base R `stats::arima`; clustering uses base R `stats::kmeans`, so no extra R packages are required. The app continues to work without R and reports a friendly message when analysis is requested.