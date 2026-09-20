# EGY-CRETE Market Opportunity App

An internal Streamlit application for turning market observations into a persistent, reviewable opportunity pipeline for EGY-CRETE.

The app brings together three types of signals:

- Regional demand and supplier-coverage gaps
- Competitor and project moves
- Cement, aggregate, and energy cost movements

Data is stored in SQLite so it survives application restarts. User passwords are stored as bcrypt hashes, and records retain the display name of the user who created or last edited them.

## Features

### Regional demand signals

Record a region, observed signal, source, date or quarter, demand-growth score, and supplier-coverage score.

The app calculates:

```text
Opportunity Gap = Demand Growth - Supplier Coverage
```

Priority is assigned from the thresholds in `config.py`:

- `High`: gap greater than or equal to `3`
- `Medium`: gap greater than or equal to `1` and below `3`
- `Low`: gap below `1`

The page includes region and priority filters, an average opportunity-gap chart, and edit/delete controls.

### Competitor and project moves

Record competitor or project activity, impact, implications, source, and action owner. The page provides filtering, a time-based activity chart, and edit/delete controls.

### Input cost signals

Record monthly prices for Cement, Aggregate, or Energy. The app compares a new price with the most recent earlier price for the same input and assigns `Rising`, `Falling`, or `Stable`.

The page includes:

- Historical price table
- One-line-per-input price chart
- CSV and Excel import
- Edit/delete controls

### Dashboard

The overview page shows:

- Number of high-priority regional gaps
- Most active competitor in the current quarter
- Latest cement price trend
- Average regional opportunity-gap chart

If synthetic test data is present, the dashboard and relevant data pages display a warning banner.

### Phase 2 analysis

The app contains two optional R-backed analyses:

- **ARIMA cost forecast:** forecasts the next 3-6 months for each input type and returns confidence bounds.
- **KMeans regional clustering:** groups regions using average demand growth, supplier coverage, and opportunity gap.

Both analyses run only after the user clicks their action button. The forecast requires at least the configured number of months of history, currently `12`.

## Project structure

| File | Purpose |
| --- | --- |
| `Market_Opportunity_app.py` | Streamlit UI, authentication, forms, charts, and page navigation |
| `db.py` | SQLite schema, migrations, imports, CRUD operations, and user persistence |
| `analysis.py` | Python-to-R subprocess bridge |
| `config.py` | Priority, forecast-history, and ARIMA settings |
| `forecasting.R` | Base R ARIMA forecasting script |
| `clustering.R` | Base R KMeans clustering script |
| `requirements.txt` | Python dependencies |
| `market_opportunities.db` | Local SQLite database created at runtime |
| `EGY-CRETE_Market_Data_Synthetic.xlsx` | Synthetic test workbook |
| `EGY-CRETE_Market_Opportunity_Tracker.xlsx` | Original tracker template workbook |

## Requirements

- Windows, macOS, or Linux
- Python 3.10 or newer recommended
- Python packages listed in `requirements.txt`
- R 4.x for Phase 2 analysis

The app can run without R. Only the forecasting and clustering actions require R.

## Installation

Open PowerShell in the project directory:

```powershell
cd "C:\Users\EGY-CRETE\OneDrive\Desktop\Projects\Market opertunities"
python -m pip install -r requirements.txt
```

For the current Windows setup, the Python interpreter may be located at:

```powershell
C:\Users\EGY-CRETE\AppData\Local\Programs\Python\Python314\python.exe
```

If the `python` command is not recognized, use that full path instead.

## R installation

Install R from the official Windows distribution:

<https://cran.r-project.org/bin/windows/base/>

Verify the installation:

```powershell
Rscript --version
```

The app first searches for `Rscript` on `PATH`. On Windows it also searches standard folders such as:

```text
C:\Program Files\R\R-4.6.1\bin\Rscript.exe
```

No additional R packages are required. The scripts use base R:

- `stats::arima` for forecasting
- `stats::kmeans` for clustering

## Start the app

Run Streamlit from the project directory:

```powershell
streamlit run Market_Opportunity_app.py
```

Keep the terminal open while using the app. Streamlit prints the local URL, normally:

```text
http://localhost:8501
```

Open the exact `Local URL` shown in the terminal. If port `8501` is already occupied, Streamlit may select another port.

Do not double-click `Market_Opportunity_app.py`; it is a Streamlit entry point and must be launched with the `streamlit run` command.

## First login

On the first startup, the users table is empty and the app displays a **Create first account** form.

1. Enter a username.
2. Enter a display name.
3. Choose a password of at least 8 characters.
4. Confirm the password.
5. Create the account and sign in.

After the first account exists, the app displays a sign-in screen. Additional team members can use the **Create account** tab. The signed-in user is kept in the Streamlit session and is required again after the browser session ends.

Use **Sign out** in the sidebar to end the current session.

## Import data

### Excel workbook import

1. Open **Data import**.
2. Choose an `.xlsx` file.
3. Click **Import workbook**.
4. Review the inserted and skipped-duplicate counts.

The importer:

- Detects the actual header row in each recognized sheet
- Maps columns by header text rather than fixed column positions
- Supports the synthetic workbook and the original tracker template
- Skips duplicate records
- Stores `synthetic` or `real` in the `data_source` column
- Stores the signed-in display name in `created_by`

The synthetic workbook currently contains 240 regional rows, 150 competitor rows, and 135 input-cost rows before duplicate checks. The tracker workbook contains its populated example rows.

### CSV import

CSV import is available on the **Input costs** page. The CSV must contain columns equivalent to:

```text
Date, Input, Price (EGP)
```

Column names may use the normalized alternatives `price_date`, `input_type`, or `price_egp`.

## Editing and deleting records

Each data page shows an **Edit or delete a record** section below the main table.

1. Select a record by its ID.
2. Change the fields in the form.
3. Choose **Save changes** or **Delete record**.

Regional priority and opportunity gap are recalculated when a record is edited. Input-cost prior price and trend are recalculated from the updated date and input type.

## Database and migrations

The database file is `market_opportunities.db` in the project directory. It is created automatically on startup.

The application applies lightweight schema migrations for existing databases. The current tables are:

- `regional_signals`
- `competitor_moves`
- `input_cost_signals`
- `users`

To preserve data, do not delete or replace `market_opportunities.db` unless you intentionally want a fresh workspace. For a clean test database, stop the app and make a backup before removing the file.

## Configuration

Edit `config.py` to tune the named application settings:

```python
PRIORITY_HIGH_MIN_GAP = 3
PRIORITY_MEDIUM_MIN_GAP = 1
MIN_FORECAST_MONTHS = 12
ARIMA_ORDER = (1, 1, 1)
```

The ARIMA order is passed from Python into `forecasting.R`; no modeling threshold needs to be changed inside the R script.

## Troubleshooting

### The browser closes immediately

Confirm that the terminal running Streamlit remains open. Start the app again and open the exact URL printed by Streamlit:

```powershell
streamlit run Market_Opportunity_app.py
```

You can also try:

```text
http://127.0.0.1:8501
```

If Brave closes while typing, try a private window or temporarily disable extensions and hardware acceleration. The Streamlit server should continue responding even if the browser has a problem.

### `Rscript` is not recognized

Confirm R is installed:

```powershell
Rscript --version
```

Restart VS Code after installing R so it receives the updated Windows PATH. The app also checks standard Windows R installation folders automatically.

### Import reports duplicates

This is expected when importing the same workbook more than once. Duplicate keys are:

- Regional: date plus region
- Competitor: date plus competitor plus move observed
- Input cost: date plus input type

### Port `8501` is busy

Run Streamlit on another port:

```powershell
streamlit run Market_Opportunity_app.py --server.port 8502
```

Then open `http://localhost:8502`.

## Security notes

This is a lightweight internal authentication layer, not enterprise identity management. Passwords are hashed with bcrypt, but there is currently no password reset, account administration, lockout policy, audit log viewer, HTTPS configuration, or external identity provider.

Do not expose the app directly to the public internet without adding those controls and placing it behind appropriate network security.