"""
Homework 1: AI-Powered Reporter Software
Integrated Shiny app combining:
1. API query (C-Lock emissions)
2. Shiny web interface (animal/date selection, Plotly charts)
3. AI reporting (OpenAI-generated HTML/Markdown summaries)
"""

import io
import os
import pandas as pd
from datetime import datetime
from urllib import request

from dotenv import load_dotenv
from openai import OpenAI

import plotly.graph_objects as go
from shiny import App, ui, render, reactive
from shinywidgets import output_widget, render_widget

# --- Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

FID = "453"
MAX_DATA_CHARS = 50000
LOAD_DOTENV_PATHS = [
    os.path.join(REPO_ROOT, ".env"),
    os.path.join(REPO_ROOT, "assignment_module01", "lab_submission", ".env"),
]


# ---------------------------------------------------------------------------
# 1. API Query (from my_api_query_lab.py)
# ---------------------------------------------------------------------------

def fetch_emissions_from_api():
    """Authenticate to C-lock, fetch emissions. Returns (csv_raw_str, df) or (None, empty_df) on failure."""
    for path in LOAD_DOTENV_PATHS:
        if os.path.isfile(path):
            load_dotenv(path)
            break
    else:
        load_dotenv()
    USER = os.getenv("CLOCK_USER")
    PASS = os.getenv("CLOCK_PASS")
    if not USER or not PASS:
        return None, pd.DataFrame()
    req = request.urlopen(
        "https://portal.c-lockinc.com/api/login",
        bytes("user=" + USER + "&pass=" + PASS, "ascii"),
    )
    TOK = req.read().decode("ascii").strip()
    URL = "https://portal.c-lockinc.com/api/getemissions?d=visits&fids=453&st=2025-08-01_00:00:00&et=2025-11-01_12:00:00"
    Headers = {
        "Header": (
            "(OwnerID,)FeederID,AnimalName,RFID,StartTime,EndTime,GoodDataDuration,"
            "CO2GramsPerDay,CH4GramsPerDay,O2GramsPerDay,H2GramsPerDay,H2SGramsPerDay,"
            "AirflowLitersPerSec,AirflowCf,WindSpeedMetersPerSec,WindDirDeg,WindCf,"
            "WasInterrupted,InterruptingTags,TempPipeDegreesCelsius,IsPreliminary,RunTime"
        )
    }
    req_obj = request.Request(URL, data=bytes("token=" + TOK, "ascii"), headers=Headers)
    req = request.urlopen(req_obj)
    csv_raw = req.read().decode("ascii")
    df = parse_csv_to_df(csv_raw)
    return csv_raw, df


def parse_csv_to_df(csv_raw: str) -> pd.DataFrame:
    """Parse raw CSV string to DataFrame (skip Parameters line if present)."""
    if not csv_raw or not csv_raw.strip():
        return pd.DataFrame()
    lines = csv_raw.strip().split("\n")
    if lines and lines[0].startswith("Parameters:"):
        csv_content = "\n".join(lines[1:])
    else:
        csv_content = csv_raw
    df = pd.read_csv(io.StringIO(csv_content))
    df["StartTime"] = pd.to_datetime(df["StartTime"], errors="coerce")
    df["Date"] = pd.to_datetime(df["StartTime"]).dt.date
    df["CH4GramsPerDay"] = pd.to_numeric(df["CH4GramsPerDay"], errors="coerce")
    df["AnimalName"] = df["AnimalName"].astype(str).str.strip('"').str.strip()
    return df.dropna(subset=["StartTime", "CH4GramsPerDay"])


# ---------------------------------------------------------------------------
# 2. AI Reporter (from AI-powered reporter.py)
# ---------------------------------------------------------------------------

def _strip_code_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0].strip()
    return text


def generate_reports_with_openai(csv_data: str) -> tuple[str, str]:
    """Use OpenAI to analyze data and generate HTML + Markdown. Returns (html, md)."""
    for p in LOAD_DOTENV_PATHS:
        if os.path.isfile(p):
            load_dotenv(p)
            break
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY must be set in .env")
    data = csv_data[:MAX_DATA_CHARS] + ("\n... [truncated]" if len(csv_data) > MAX_DATA_CHARS else "")
    client = OpenAI(api_key=api_key, timeout=60)
    r1 = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a data analyst. Analyze the emissions CSV, summarize key findings. Produce a complete HTML report. Use green accents (#1a5f2a) for headers only. For tables: dark text (#333) on white/light gray backgrounds for readability. No light text on light backgrounds. Output ONLY raw HTML, no markdown."},
            {"role": "user", "content": f"Analyze this C-Lock GreenFeeder emissions data and generate an HTML report:\n\n{data}"},
        ],
        temperature=0.3,
    )
    html = _strip_code_block(r1.choices[0].message.content.strip())
    r2 = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a data analyst. Analyze the emissions CSV, summarize key findings. Produce a Markdown report for GitHub: use # headers, tables with |, bullet lists. Output ONLY raw Markdown, no code fences."},
            {"role": "user", "content": f"Analyze this C-Lock GreenFeeder emissions data and generate a Markdown report:\n\n{data}"},
        ],
        temperature=0.3,
    )
    md = _strip_code_block(r2.choices[0].message.content.strip())
    return html, md


# ---------------------------------------------------------------------------
# Startup: fetch data from API (no file)
# ---------------------------------------------------------------------------

_csv_raw, EMISSIONS_DF = None, pd.DataFrame()
try:
    _csv_raw, EMISSIONS_DF = fetch_emissions_from_api()
except Exception:
    pass
if _csv_raw is None:
    _csv_raw = ""
ANIMALS = sorted(EMISSIONS_DF["AnimalName"].unique().tolist()) if not EMISSIONS_DF.empty else []
DATES = sorted(EMISSIONS_DF["Date"].unique().tolist()) if not EMISSIONS_DF.empty else []

THEME_CSS = "https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/darkly/bootstrap.min.css"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

# Data & Charts page (sidebar + tabs)
data_page = ui.page_fluid(
    ui.tags.head(ui.tags.link(rel="stylesheet", href=THEME_CSS)),
    ui.panel_title("AI-Powered Methane Emissions Reporter"),
    ui.card(
        ui.card_header(
            ui.tags.span("GreenFeed 453", class_="fw-bold fs-4"),
            ui.tags.span("Methane emissions · C-lock visits · AI reporting", class_="text-body-secondary ms-2"),
        ),
        ui.card_body(
            ui.output_ui("header_data_source"),
            class_="py-2",
        ),
        class_="mb-3 border-0 shadow-sm",
    ),
    ui.layout_sidebar(
        ui.sidebar(
            ui.input_action_button("refresh_api", "Fetch from API", class_="btn-primary"),
            ui.tags.p("Data is fetched directly from C-Lock API (no file).", class_="text-body-secondary small"),
            ui.input_select("animal", "Select animal", choices=ANIMALS, selected=ANIMALS[0] if ANIMALS else None),
            ui.input_select("date", "Select date", choices=[d.isoformat() for d in DATES], selected=DATES[-1].isoformat() if DATES else None),
            ui.tags.hr(),
            ui.tags.p("AI Report (whole dataset):", class_="fw-bold small"),
            ui.input_action_button("generate_ai_report", "Generate AI Report", class_="btn-success"),
            ui.tags.p("Opens on a separate page.", class_="text-body-secondary small mt-1"),
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

# CSS overrides for AI report: ensure dark text on light backgrounds for readability
AI_REPORT_CSS = """
.ai-report-content table td, .ai-report-content table th { color: #333 !important; }
.ai-report-content table tr { background: #fff !important; }
.ai-report-content table tr:nth-child(even) { background: #f5f5f5 !important; }
.ai-report-content table thead tr { background: #1a5f2a !important; color: #fff !important; }
.ai-report-content table thead th { color: #fff !important; }
.ai-report-content, .ai-report-content p, .ai-report-content li { color: #333 !important; }
"""

# AI Report page (standalone, whole dataset as text — no sidebar, no other elements)
ai_report_page = ui.page_fluid(
    ui.tags.head(
        ui.tags.link(rel="stylesheet", href=THEME_CSS),
        ui.tags.style(AI_REPORT_CSS),
    ),
    ui.panel_title("AI Report — Whole Dataset"),
    ui.tags.p("AI-generated summary of the full emissions dataset. Generate from Data & Charts page.", class_="text-body-secondary mb-3"),
    ui.output_ui("ai_report_status"),
    ui.output_ui("ai_report_content"),
)

app_ui = ui.page_navbar(
    ui.nav_panel("Data & Charts", data_page, value="data"),
    ui.nav_panel("AI Report", ai_report_page, value="ai_report"),
    title="AI-Powered Methane Emissions Reporter",
    id="main_navbar",
)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def server(input, output, session):
    emissions_data = reactive.Value(EMISSIONS_DF)
    csv_raw_data = reactive.Value(_csv_raw or "")
    data_fetched_at = reactive.Value(datetime.now().strftime("%Y-%m-%d %H:%M") if not EMISSIONS_DF.empty else None)
    ai_report_html = reactive.Value(None)
    ai_status_text = reactive.Value("")

    @reactive.Effect
    @reactive.event(input.refresh_api)
    def _refresh_from_api():
        try:
            csv_raw, df = fetch_emissions_from_api()
            if csv_raw is not None and not df.empty:
                emissions_data.set(df)
                csv_raw_data.set(csv_raw)
                data_fetched_at.set(datetime.now().strftime("%Y-%m-%d %H:%M"))
                animals = sorted(df["AnimalName"].unique().tolist())
                dates = sorted(df["Date"].unique().tolist())
                ui.update_select("animal", choices=animals, selected=animals[0] if animals else None, session=session)
                ui.update_select("date", choices=[d.isoformat() for d in dates], selected=dates[-1].isoformat() if dates else None, session=session)
        except Exception:
            pass

    @reactive.Effect
    @reactive.event(input.generate_ai_report)
    def _generate_ai_report():
        ai_status_text.set("Generating AI report (30–60 seconds)...")
        ai_report_html.set(None)
        try:
            csv_text = csv_raw_data.get() or ""
            if not csv_text.strip():
                ai_status_text.set("No data. Use Fetch from API first.")
                return
            html, _ = generate_reports_with_openai(csv_text)
            ai_report_html.set(html)
            ai_status_text.set("AI report generated successfully (whole dataset).")
            ui.update_navset("main_navbar", selected="ai_report")
        except Exception as e:
            ai_status_text.set(f"Error: {str(e)}")

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
        t = data_fetched_at.get()
        if t:
            return ui.tags.small("Data: ", ui.tags.code("Live from API"), f" (fetched {t})", class_="text-body-secondary")
        return ui.tags.small("Data: ", ui.tags.code("None — click Fetch from API"), class_="text-body-secondary")

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
        mask = (df_dates == date_val) & (df["AnimalName"].astype(str).str.strip() == animal_str)
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
        date_val = selected_date() or df["Date"].max()
        df_date = df[df["Date"] == date_val]
        if df_date.empty:
            df_date = df
        avg = df_date.groupby("AnimalName", as_index=False)["CH4GramsPerDay"].mean().sort_values("AnimalName")
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

    @render.ui
    def ai_report_status():
        s = ai_status_text.get()
        if not s:
            return None
        return ui.tags.p(s, class_="text-body-secondary mb-2")

    @render.ui
    def ai_report_content():
        html = ai_report_html.get()
        if html is None:
            return None
        return ui.div(
            ui.HTML(html),
            class_="ai-report-content",
            style="max-height: 70vh; overflow-y: auto; padding: 1rem; background: #fff; border-radius: 8px; color: #333;",
        )


app = App(app_ui, server)

if __name__ == "__main__":
    from shiny import run_app
    run_app(app, host="127.0.0.1", port=8000, launch_browser=True)
