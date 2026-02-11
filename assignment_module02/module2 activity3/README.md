# Module 2 Activity 4 — GreenFeed Shiny App (Methane and CO₂)

This activity builds a **Shiny for Python** app that reads **C-Lock GreenFeed emissions/visits data** and presents it in **tables**, **figures**, and **summary statistics** for **all animals** in the dataset, focusing on **methane (CH₄)** and **carbon dioxide (CO₂)**.

---

## 1. Objectives

- **Visualize GreenFeed gas measurements** (CH₄ and CO₂) for all animals in the data file.
- Provide **interactive tables** so users can filter/sort visits by animal, date, and feeder.
- Show **meaningful plots** of gas emissions:
  - Distributions of CH₄ and CO₂ per animal.
  - Time trends of CH₄ and CO₂ for selected animals.
- Compute and display **summary statistics** (mean, median, min, max) for CH₄ and CO₂ by animal.
- Use a **card-based Shiny UI** with an **attractive theme** and a clear **take‑home message** about the overall trends.

---

## 2. Data Input

The app expects a **CSV file** exported from the C-Lock portal (e.g., from the `getemissions` API or portal UI) with at least these columns:

- `AnimalName` — animal identifier (name or ID).
- `StartTime` / `EndTime` — visit times.
- `CH4GramsPerDay` — methane emissions per day (g/day).
- `CO2GramsPerDay` — carbon dioxide emissions per day (g/day).
- Optional: other columns (O₂, H₂, airflow, etc.) can be used for extra context but are not required.

You can point the app at:

- A **sample CSV file** saved in this folder, or
- Any compatible CSV path you specify in the app configuration.

---

## 3. Environment Setup (Python)

Create/activate a Python environment (e.g., `venv` or conda), then install the required packages.  
Use `py -m pip` so it works reliably from Cursor on Windows:

```powershell
py -m pip install shiny shinyswatch pandas plotly
```

If you also need to **query the C-Lock API directly from Python**, install `requests`:

```powershell
py -m pip install requests
```

Remember to also update the **`requirements.txt`** for this activity (or reuse the one in `Lab2` and add these packages).

---

## 4. App Design

### 4.1 Overall layout

Use a **multi‑column card layout** with a modern theme, for example:

- A **top-level header**: “GreenFeed Gas Emissions Dashboard”.
- Left side: **input controls** (date range, animal selector, file selector).
- Right side: **cards** showing key statistics and plots.

Suggested Shiny for Python structure:

- `ui`:
  - A themed page (e.g., via `shinyswatch.theme.minty()` or similar).
  - A sidebar (or left column) for inputs:
    - File input or fixed data path.
    - Date range input (based on `StartTime`).
    - Animal selector (single or multiple animals).
  - A main area with **cards**:
    - Card 1: “Summary statistics by animal” (table).
    - Card 2: “Methane vs CO₂ overview” (scatter or bar plot).
    - Card 3: “Time trend for selected animal(s)” (line plot).
    - Card 4: “Take‑home message” (text/markdown).

- `server`:
  - Load the CSV into a **pandas DataFrame**.
  - Convert timestamps to `datetime`.
  - Filter rows by selected date range and animal(s).
  - Compute **grouped statistics** by `AnimalName`:
    - Mean, median, min, max for `CH4GramsPerDay`, `CO2GramsPerDay`.
  - Create **plotly** figures for:
    - CH₄ and CO₂ distributions per animal.
    - CH₄ and CO₂ over time (line plot) for selected animals.

---

## 5. Key Features to Implement

### 5.1 Tables

- **Animal summary table**:
  - Index/rows: `AnimalName`.
  - Columns: mean, median, min, max for CH₄ and CO₂.
  - Optionally include number of visits per animal.
- **Raw visits table** (optional but helpful):
  - Show filtered visit-level data (animal, time, CH₄, CO₂).
  - Allow sorting by time or emission level.

### 5.2 Figures

- **Per-animal bar or box plots**:
  - CH₄ and CO₂ side by side per animal.
  - Use color to distinguish gas type (e.g., blue for CO₂, green for CH₄).
- **Time series plots**:
  - For selected animals, plot CH₄ and/or CO₂ vs time.
  - One line per animal, or separate subplots for clarity.

### 5.3 Statistics

For each animal (and possibly overall):

- Mean CH₄ and CO₂.
- Median CH₄ and CO₂.
- Min and max CH₄ and CO₂.
- Number of visits (data points).

You can display a **few key numbers** in prominent cards, for example:

- “Overall mean CH₄ (g/day)”
- “Overall mean CO₂ (g/day)”
- “Animal with highest mean CH₄”
- “Animal with lowest mean CH₄”

---

## 6. Take‑Home Message (Interpretation)

Reserve one card or text area in the app UI for an **interpretation summary**, for example:

- Are some animals consistently higher emitters (CH₄ or CO₂) than others?
- Is there a clear **trend over time** (e.g., emissions increasing or decreasing)?
- Are there **outliers** (animals or visits with unusually high emissions)?
- Does the data suggest management or research questions (e.g., diet, housing, or measurement conditions)?

This text does **not** need to be long, but it should help a non‑expert understand the **overall pattern** in the data.

---

## 7. How to Run the App

1. Ensure your environment is activated and required packages are installed:

   ```powershell
   py -m pip install shiny shinyswatch pandas plotly requests
   ```

2. Place your **GreenFeed CSV file** in this folder (or update the path in the app code).
3. Save your Shiny for Python app script (e.g., `shinyApp_greenfeed.py`) in this folder.
4. From this folder, start the app:

   ```powershell
   py -m shiny run --reload shinyApp_greenfeed.py
   ```

5. Open the local URL shown in the terminal (typically `http://127.0.0.1:8000`) in your browser.

---

## 8. Suggested File Structure for This Activity

- `assignment_module02/`
  - `module2 activity4/`
    - `README.md`  ← this file
    - `shinyApp_greenfeed.py`  ← Shiny for Python app
    - `greenfeed_emissions_sample.csv`  ← example data (optional)
    - `requirements.txt`  ← Python dependencies for this activity

Keep your code **well commented** and your UI **clean and readable**, so that the figures, tables, and statistics clearly support your final **take‑home message** about methane and CO₂ trends across animals.

