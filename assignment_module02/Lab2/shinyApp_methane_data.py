"""
Shiny app for GreenFeed 453 methane emissions.
Uses data from emissions_visits_fid453 (downloaded GF files).
Integrates the API query code from my_api_query_lab.py to fetch data from C-lock.
- Select animal and date to view methane emissions (CH4 Grams/day).
- Plotly bar chart: average CH4 by animal; selected animal is highlighted.
"""

import os
import glob
import pandas as pd
from datetime import datetime
from urllib import request

from dotenv import load_dotenv

import plotly.graph_objects as go
from shiny import App, ui, render, reactive
from shinywidgets import output_widget, render_widget


# --- Data path: same dataset as my_api_query_lab.py output ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DATA_DIR = os.path.join(REPO_ROOT, "assignment_module01", "downloaded GF files")
DATA_FILE = "emissions_visits_fid453_20260204_162120.csv"
DATA_PATH = os.path.join(DATA_DIR, DATA_FILE)

# C-lock API (from my_api_query_lab.py)
FID = "453"
LOAD_DOTENV_PATHS = [
    os.path.join(REPO_ROOT, "assignment_module01", "lab_submission", ".env"),
    os.path.join(REPO_ROOT, ".env"),
]


def fetch_emissions_from_api():
    """
    API query code from my_api_query_lab.py:
    Authenticate to C-lock, fetch emissions visits for feeder 453, save to downloaded GF files.
    Returns path to saved file, or None if fetch failed (e.g. missing .env or network error).
    """
    for path in LOAD_DOTENV_PATHS:
        if os.path.isfile(path):
            load_dotenv(path)
            break
    else:
        load_dotenv()
    USER = os.getenv("CLOCK_USER")
    PASS = os.getenv("CLOCK_PASS")
    if not USER or not PASS:
        return None
    # First authenticate to receive token
    req = request.urlopen(
        "https://portal.c-lockinc.com/api/login",
        bytes("user=" + USER + "&pass=" + PASS, "ascii"),
    )
    TOK = req.read().decode("ascii").strip()
    # Get data using the login token
    URL = "https://portal.c-lockinc.com/api/getemissions?d=visits&fids=453&st=2025-08-01_00:00:00&et=2025-11-01_12:00:00"
    Headers = {
        "Header": (
            "(OwnerID,)FeederID,AnimalName,RFID,StartTime,EndTime,GoodDataDuration,"
            "CO2GramsPerDay,CH4GramsPerDay,O2GramsPerDay,H2GramsPerDay,H2SGramsPerDay,"
            "AirflowLitersPerSec,AirflowCf,WindSpeedMetersPerSec,WindDirDeg,WindCf,"
            "WasInterrupted,InterruptingTags,TempPipeDegreesCelsius,IsPreliminary,RunTime"
        )
    }
    req_obj = request.Request(
        URL,
        data=bytes("token=" + TOK, "ascii"),
        headers=Headers,
    )
    req = request.urlopen(req_obj)
    data = req.read()
    data_str = data.decode("ascii")
    # Create "downloaded GF files" folder and save raw response as-is
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"emissions_visits_fid{FID}_{timestamp}.csv"
    output_path = os.path.join(DATA_DIR, filename)
    with open(output_path, "w", encoding="ascii") as f:
        f.write(data_str)
    return output_path


def get_latest_emissions_path():
    """Path to the most recent emissions CSV in downloaded GF files, or default file."""
    pattern = os.path.join(DATA_DIR, "emissions_visits_fid453_*.csv")
    files = glob.glob(pattern)
    if not files:
        return DATA_PATH
    return max(files, key=os.path.getmtime)


def load_emissions_data(csv_path=None):
    """Load and prepare emissions CSV (skip first 'Parameters' line)."""
    path = csv_path or get_latest_emissions_path()
    if not os.path.isfile(path):
        return pd.DataFrame()
    df = pd.read_csv(path, skiprows=1)
    df["StartTime"] = pd.to_datetime(df["StartTime"], errors="coerce")
    df["Date"] = pd.to_datetime(df["StartTime"]).dt.date
    df["CH4GramsPerDay"] = pd.to_numeric(df["CH4GramsPerDay"], errors="coerce")
    df["AnimalName"] = df["AnimalName"].astype(str).str.strip('"').str.strip()
    return df.dropna(subset=["StartTime", "CH4GramsPerDay"])


# Load at startup: try API first (saves to downloaded GF files), then load from that folder
_start_path = None
try:
    _start_path = fetch_emissions_from_api()  # Saves to DATA_DIR ("downloaded GF files")
except Exception:
    pass
if _start_path is None:
    _start_path = get_latest_emissions_path()  # Latest file already in "downloaded GF files"
EMISSIONS_DF = load_emissions_data(_start_path)  # App always uses data from that folder
INITIAL_DATA_SOURCE_PATH = _start_path
ANIMALS = sorted(EMISSIONS_DF["AnimalName"].unique().tolist()) if not EMISSIONS_DF.empty else []
DATES = sorted(EMISSIONS_DF["Date"].unique().tolist()) if not EMISSIONS_DF.empty else []


# Cool theme: Bootswatch Darkly (dark, modern)
THEME_CSS = "https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/darkly/bootstrap.min.css"

# --- UI ---
app_ui = ui.page_fluid(
    ui.tags.head(ui.tags.link(rel="stylesheet", href=THEME_CSS)),
    ui.panel_title("Methane emissions"),
    # Card: GreenFeed 453 + data source
    ui.card(
        ui.card_header(
            ui.tags.span("GreenFeed 453", class_="fw-bold fs-4"),
            ui.tags.span("Methane emissions · C-lock visits data", class_="text-body-secondary ms-2"),
        ),
        ui.card_body(
            ui.output_ui("header_data_source"),
            class_="py-2",
        ),
        class_="mb-3 border-0 shadow-sm",
    ),
    ui.layout_sidebar(
        ui.sidebar(
            ui.input_action_button("refresh_api", "Refresh from API", class_="btn-primary"),
            ui.tags.p("API saves to 'downloaded GF files'; app loads from that folder.", class_="text-body-secondary small"),
            ui.input_select(
                "animal",
                "Select animal",
                choices=ANIMALS,
                selected=ANIMALS[0] if ANIMALS else None,
            ),
            ui.input_select(
                "date",
                "Select date",
                choices=[d.isoformat() for d in DATES],
                selected=DATES[-1].isoformat() if DATES else None,
            ),
            width=280,
        ),
        ui.navset_card_pill(
            ui.nav_panel(
                "By date",
                ui.output_ui("average_card"),
                ui.output_ui("emissions_table"),
                ui.output_text_verbatim("emissions_summary", placeholder=True),
            ),
            ui.nav_panel(
                "Average by animal",
                output_widget("plot_avg_ch4", height="500px"),
            ),
        ),
    ),
)


# --- Server ---
def server(input, output, session):
    # Reactive data so "Refresh from API" reloads the dataset from downloaded GF files
    emissions_data = reactive.Value(EMISSIONS_DF)
    data_source_path = reactive.Value(INITIAL_DATA_SOURCE_PATH)

    @reactive.Effect
    @reactive.event(input.refresh_api)
    def _refresh_from_api():
        try:
            path = fetch_emissions_from_api()
            if path is not None:
                df = load_emissions_data(path)  # Load from file just saved in "downloaded GF files"
                if not df.empty:
                    emissions_data.set(df)
                    data_source_path.set(path)
                    animals = sorted(df["AnimalName"].unique().tolist())
                    dates = sorted(df["Date"].unique().tolist())
                    ui.update_select("animal", choices=animals, selected=animals[0] if animals else None, session=session)
                    ui.update_select("date", choices=[d.isoformat() for d in dates], selected=dates[-1].isoformat() if dates else None, session=session)
        except Exception:
            pass

    @reactive.Calc
    def selected_date():
        s = input.date()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            return None

    @render.ui
    def header_data_source():
        p = data_source_path.get()
        name = os.path.basename(p) if p else "(none)"
        return ui.tags.small("Data from: ", ui.tags.code(name), class_="text-body-secondary")

    @reactive.Calc
    def df_current():
        return emissions_data.get()

    @reactive.Calc
    def filtered_emissions():
        animal = input.animal()
        date_val = selected_date()
        df = df_current()
        if df.empty or animal is None or date_val is None:
            return pd.DataFrame()
        animal_str = str(animal).strip()
        df_dates = pd.to_datetime(df["StartTime"]).dt.date
        date_ok = df_dates == date_val
        animal_ok = df["AnimalName"].astype(str).str.strip() == animal_str
        mask = animal_ok & date_ok
        return df.loc[mask, ["StartTime", "CH4GramsPerDay"]].copy()

    @render.ui
    def average_card():
        df = filtered_emissions()
        animal = input.animal() or "—"
        date_s = input.date() or "—"
        if df.empty:
            return ui.card(
                ui.card_header("Average CH4 for selected animal and date"),
                ui.card_body(
                    ui.tags.p("No records for this animal and date.", class_="text-body-secondary mb-0"),
                    ui.tags.p(ui.tags.small(f"Animal: {animal}  ·  Date: {date_s}"), class_="text-muted small mb-0"),
                ),
                class_="mb-3 border-warning",
            )
        n = len(df)
        mean_ch4 = float(df["CH4GramsPerDay"].mean())
        return ui.card(
            ui.card_header("Average CH4 for selected animal and date"),
            ui.card_body(
                ui.tags.p(
                    ui.tags.span(f"{mean_ch4:.2f}", class_="fw-bold fs-3 text-primary"),
                    " Gram/day",
                    class_="mb-1",
                ),
                ui.tags.p(ui.tags.small(f"Animal {animal}  ·  {date_s}  ·  {n} visit(s)"), class_="text-body-secondary mb-0"),
            ),
            class_="mb-3 border-primary",
        )

    @render.ui
    def emissions_table():
        df = filtered_emissions()
        if df.empty:
            return ui.tags.p("No records for selected animal and date.", class_="text-muted")
        out = df.rename(columns={"CH4GramsPerDay": "CH4 (Gram/day)"}).copy()
        out["StartTime"] = out["StartTime"].dt.strftime("%Y-%m-%d %H:%M")
        # Use plain to_html() so we don't need jinja2 (DataFrame.style is only used by render.table)
        html = out.to_html(index=False, classes="table table-bordered table-striped", border=0)
        return ui.HTML(html)

    @render.text
    def emissions_summary():
        df = filtered_emissions()
        if df.empty:
            return "No visit records for this selection."
        n = len(df)
        mean_ch4 = df["CH4GramsPerDay"].mean()
        return f"Records: {n}  |  Mean CH4: {mean_ch4:.2f} Gram/day"

    @render_widget
    def plot_avg_ch4():
        df = df_current()
        if df.empty:
            fig = go.Figure()
            fig.update_layout(title="No data. Use Refresh from API or check .env.")
            return fig
        date_val = selected_date()
        if date_val is None:
            date_val = df["Date"].max()
        df_date = df[df["Date"] == date_val]
        if df_date.empty:
            df_date = df
        avg = (
            df_date.groupby("AnimalName", as_index=False)["CH4GramsPerDay"]
            .mean()
            .sort_values("AnimalName")
        )
        selected_animal = input.animal()
        avg["highlight"] = avg["AnimalName"] == selected_animal
        colors = avg["highlight"].map({True: "orangered", False: "lightgray"})
        fig = go.Figure(
            data=[
                go.Bar(
                    x=avg["AnimalName"],
                    y=avg["CH4GramsPerDay"],
                    marker_color=colors,
                    text=avg["CH4GramsPerDay"].round(2),
                    textposition="outside",
                )
            ]
        )
        fig.update_layout(
            title=f"Average methane emission by animal (Gram/day){' — date: ' + str(date_val) if date_val else ''}",
            xaxis_title="Animal",
            yaxis_title="CH4 (Gram/day)",
            showlegend=False,
            margin=dict(b=80),
        )
        return fig


app = App(app_ui, server)
