# Homework 1: AI-Powered Reporter Software

Integrated Shiny app: API query + Data & Charts + AI Report (whole dataset).

---

## Data Summary (C-Lock API columns)

| Column | Type | Description |
|--------|------|-------------|
| OwnerID | int | Owner identifier |
| FeederID | int | GreenFeed unit ID |
| AnimalName | string | Animal identifier |
| RFID | string | RFID tag |
| StartTime | datetime | Visit start |
| EndTime | datetime | Visit end |
| GoodDataDuration | float | Valid measurement duration (sec) |
| CO2GramsPerDay | float | CO2 emission rate |
| CH4GramsPerDay | float | Methane emission rate |
| O2GramsPerDay | float | O2 emission rate |
| H2GramsPerDay | float | H2 emission rate |
| H2SGramsPerDay | float | H2S emission rate |
| AirflowLitersPerSec | float | Airflow rate |
| AirflowCf | float | Airflow correction factor |
| WindSpeedMetersPerSec | float | Wind speed |
| WindDirDeg | float | Wind direction (degrees) |
| WindCf | float | Wind correction factor |
| WasInterrupted | int | 1 if visit was interrupted |
| InterruptingTags | string | Tags that interrupted |
| TempPipeDegreesCelsius | float | Pipe temperature |
| IsPreliminary | int | 1 if data is preliminary |
| RunTime | float | Run duration |

---

## Technical Details

**API keys (in `.env`):**
- `CLOCK_USER` — C-Lock portal username
- `CLOCK_PASS` — C-Lock portal password
- `OPENAI_API_KEY` — OpenAI API key for AI report

**Endpoints:**
- Login: `https://portal.c-lockinc.com/api/login`
- Emissions: `https://portal.c-lockinc.com/api/getemissions?d=visits&fids=453&st=...&et=...`

**Packages:** shiny, shinywidgets, pandas, plotly, python-dotenv, openai

**File structure:**
```
homework1/
  main_app.py          # Main app (API + UI + AI)
  my_api_query_lab.py  # Standalone API lab
  shinyApp_methane_data.py
  AI-powered reporter.py
  requirements.txt
  README.md
```

---

## Usage Instructions

**1. Install dependencies:**
```powershell
cd homework1
py -m pip install -r requirements.txt
```

**2. Set up `.env`** in project root with `CLOCK_USER`, `CLOCK_PASS`, `OPENAI_API_KEY`.

**3. Run:**
```powershell
cd homework1
python -m shiny run main_app.py
```
Or from project root: `python -m shiny run homework1\main_app.py`

**4. Open** http://127.0.0.1:8000 (or 8001 if 8000 is in use).

**Pages:** Data & Charts (fetch, filter, charts) | AI Report (generated summary)
