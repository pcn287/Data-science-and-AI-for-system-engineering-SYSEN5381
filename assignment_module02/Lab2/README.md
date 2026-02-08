# GreenFeed 453 — Methane Emissions Shiny App

## Overview

This Shiny for Python app visualizes **methane (CH₄) emissions** from **GreenFeed 453** (Feeder ID 453) using C-lock visit data. It integrates the same API query logic as `my_api_query_lab.py`: the app can fetch data from the C-lock portal, save it to the `downloaded GF files` folder, and load it for exploration.

**What the app does:**

- **By date:** Select an animal and a date to see that animal’s visit-level CH₄ (Gram/day), a **prominent average CH₄** for that animal and date, and a table of all visits.
- **Average by animal:** View a Plotly bar chart of average methane emission per animal for the selected date; the selected animal is highlighted.
- **Refresh from API:** Re-fetch data from the C-lock API and save a new CSV in `downloaded GF files`; the app then loads from that folder.

The UI uses a dark theme (Bootswatch Darkly) and a header card showing GreenFeed 453 and the current data source file.

---

## Installation

1. **Clone or open the project** so the repo root is your working directory.

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies** from the Lab2 folder:
   ```bash
   pip install -r assignment_module02\Lab2\requirements.txt
   ```
   Or from inside `Lab2`:
   ```bash
   pip install -r requirements.txt
   ```

   Required packages: `shiny`, `shinywidgets`, `pandas`, `plotly`, `python-dotenv`, `jinja2`.

---

## How to Run the App

From the **project root**:

```bash
py -m shiny run assignment_module02\Lab2\shinyApp_methane_data.py
```

Or from inside `assignment_module02\Lab2`:

```bash
py -m shiny run shinyApp_methane_data.py
```

Then open a browser to **http://127.0.0.1:8000**. Stop the server with **Ctrl+C** in the terminal.

---

## API Requirements

The app uses the **C-lock Inc. portal API** to fetch emissions visit data. To use **Refresh from API** (and optional startup fetch), you must provide credentials via environment variables.

### API key / credential setup

1. **Create a `.env` file** in one of these locations (the app checks in this order):
   - `assignment_module01/lab_submission/.env`
   - Project root: `.env`

2. **Add your C-lock credentials** (no quotes around values):
   ```env
   CLOCK_USER=your_username
   CLOCK_PASS=your_password
   ```

3. **Keep `.env` private** — do not commit it to version control. Add `.env` to `.gitignore` if it isn’t already.

**Without a valid `.env`:** The app still runs and loads from the latest CSV already present in `assignment_module01/downloaded GF files/`. Use **Refresh from API** only when credentials are configured.

---

## Screenshots of the App in Action

*Add your own screenshots below to show the app in use.*

### Main view — By date (average card and table)

![By date tab: average CH4 card and visit table](screenshots/by_date.png)

*Replace the path above with your screenshot (e.g. `screenshots/by_date.png`).*

### Average by animal (Plotly chart)

![Average by animal: bar chart with selected animal highlighted](screenshots/average_by_animal.png)

*Replace with your screenshot path.*

### Header card and sidebar

![GreenFeed 453 card and sidebar controls](screenshots/header_sidebar.png)

*Replace with your screenshot path.*

---

## Usage Instructions

1. **Start the app** (see [How to Run the App](#how-to-run-the-app)).
2. **Sidebar**
   - **Refresh from API:** Fetches new data from C-lock, saves to `downloaded GF files`, and reloads the app data. Requires `.env` with `CLOCK_USER` and `CLOCK_PASS`.
   - **Select animal:** Choose an animal ID (e.g. 2260, 2749). The list comes from the loaded data.
   - **Select date:** Choose a date. The list comes from the loaded data.
3. **By date tab**
   - **Average card:** Shows the **average CH₄ (Gram/day)** for the selected animal and date, or “No records” if none.
   - **Table:** All visits for that animal and date (StartTime, CH₄ Gram/day).
   - **Summary line:** Number of records and mean CH₄.
4. **Average by animal tab**
   - **Bar chart:** One bar per animal = average CH₄ for the selected date. The selected animal is highlighted (e.g. orange/red); others are gray.
5. **Data source:** The header card shows which file in `downloaded GF files` is currently loaded (e.g. `emissions_visits_fid453_20260204_162120.csv`).

---

## File Structure (Lab2)

| File / folder      | Purpose |
|--------------------|--------|
| `shinyApp_methane_data.py` | Main Shiny app (UI, server, API fetch, data load). |
| `requirements.txt`         | Python dependencies for the app. |
| `README.md`                | This documentation. |

Data is read from:  
`assignment_module01/downloaded GF files/emissions_visits_fid453_*.csv`  
(created by this app’s API fetch or by `my_api_query_lab.py`).
