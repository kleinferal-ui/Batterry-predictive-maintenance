# Battery Predictive Maintenance Console

A Streamlit dashboard for monitoring a battery bank: live overview, trend analysis,
threshold alerts, machine-learning anomaly screening and a maintenance log.

## Run
1. Install Python 3 (tick "Add Python to PATH").
2. Double-click `RUN_SYSTEM.bat` (it installs the packages the first time).
3. Open http://localhost:8501

Manual install: `python -m pip install -r requirements.txt`

## Use
- **Data & Maintenance Log** > upload a CSV (`timestamp, voltage, current, temperature`) and save it.
- **Settings** > set warning/critical limits (use the manufacturer's values for real systems).
- Keep `battery_history.db` to preserve saved readings, limits and the maintenance log.

## Files
`app.py` interface · `analytics.py` health score, trends, anomaly detection · `db.py` storage

Prototype only: the health indicator and projections are simple screening rules, not validated failure predictions.
