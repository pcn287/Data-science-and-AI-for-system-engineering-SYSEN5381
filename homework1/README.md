# Homework 1: AI-Powered Reporter Software

Integrated Shiny app: API query + Data & Charts + AI Report (whole dataset).

## Run

**From project root:**
```powershell
py -m shiny run homework1\main_app.py
```

**From homework1 folder:**
```powershell
cd homework1
py -m shiny run main_app.py
```

**If port 8000 is in use:**
```powershell
py -m shiny run homework1\main_app.py --port 8001
```
Then open http://127.0.0.1:8001

## Pages

- **Data & Charts**: Fetch from API, select animal/date, view tables and Plotly chart. Button "Generate AI Report" analyzes the whole dataset.
- **AI Report**: Standalone page with AI-generated summary (opens automatically after generation).
