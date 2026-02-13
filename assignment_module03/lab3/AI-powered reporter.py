"""
AI-Powered Data Reporter (Lab 3)
Queries C-Lock emissions API, processes methane data (extract, aggregate, rank, format),
and generates an interactive HTML Emissions Report with dropdowns and tables.
"""

import io
import json
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# --- Load .env from project root (where CLOCK credentials live) ---
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
load_dotenv(project_root / ".env")

# ---------------------------------------------------------------------------
# Step 1: Query data from C-Lock API (from my_api_query_lab.py)
# ---------------------------------------------------------------------------


def query_c_lock_emissions() -> str:
    """
    Authenticate to C-Lock portal and fetch emissions/visits data.
    Returns raw CSV string (no file download).
    """
    from urllib import request

    USER = os.getenv("CLOCK_USER")
    PASS = os.getenv("CLOCK_PASS")

    if not USER or not PASS:
        raise ValueError("CLOCK_USER and CLOCK_PASS must be set in .env")

    # Authenticate
    req = request.urlopen(
        "https://portal.c-lockinc.com/api/login",
        bytes("user=" + USER + "&pass=" + PASS, "ascii"),
    )
    TOK = req.read().decode("ascii").strip()

    # Fetch emissions data
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
    return data.decode("ascii")


# ---------------------------------------------------------------------------
# Step 2: EXTRACT, AGGREGATE, RANK (methane only)
# ---------------------------------------------------------------------------


def process_methane_data(csv_str: str) -> dict:
    """
    EXTRACT: Parse CSV, select FeederID, AnimalName, StartTime, CH4GramsPerDay.
    AGGREGATE: Per animal: total visits, mean CH4 (g), and per-date stats.
    RANK: Sort by total visits (high to low) and by avg CH4 for top/low.
    Returns dict with all data needed for HTML report.
    """
    lines = csv_str.strip().split("\n")
    if lines and lines[0].startswith("Parameters:"):
        csv_content = "\n".join(lines[1:])
    else:
        csv_content = csv_str

    df = pd.read_csv(io.StringIO(csv_content))
    df = df[["FeederID", "AnimalName", "StartTime", "CH4GramsPerDay"]].copy()

    # Parse date from StartTime
    df["Date"] = pd.to_datetime(df["StartTime"]).dt.date.astype(str)

    fid = int(df["FeederID"].iloc[0])

    # Per-animal stats (whole period)
    agg = (
        df.groupby(["FeederID", "AnimalName"])
        .agg(
            total_visits=("CH4GramsPerDay", "count"),
            avg_ch4_g=("CH4GramsPerDay", "mean"),
        )
        .reset_index()
    )

    # RANK: sort by total visits high to low
    agg = agg.sort_values("total_visits", ascending=False).reset_index(drop=True)
    agg["avg_ch4_g"] = agg["avg_ch4_g"].round(2)

    # Per-animal-per-date: average CH4 for each animal on each date
    daily = (
        df.groupby(["AnimalName", "Date"])
        .agg(avg_ch4_g=("CH4GramsPerDay", "mean"))
        .reset_index()
    )
    daily["avg_ch4_g"] = daily["avg_ch4_g"].round(2)

    # Build lookup: animal -> date -> avg CH4 (for specific date)
    animal_date_lookup = {}
    for _, row in daily.iterrows():
        animal = str(row["AnimalName"])
        date = row["Date"]
        if animal not in animal_date_lookup:
            animal_date_lookup[animal] = {}
        animal_date_lookup[animal][date] = float(row["avg_ch4_g"])

    # Overall avg CH4 per animal (whole period) for when no date selected
    animal_avg_lookup = dict(zip(agg["AnimalName"].astype(str), agg["avg_ch4_g"].round(2)))

    # Unique animals and dates for dropdowns
    animals = sorted(agg["AnimalName"].astype(str).tolist())
    dates = sorted(df["Date"].unique().tolist())

    # Top 3 and lowest 3 average methane emitters (by mean CH4 per visit)
    by_avg = agg.sort_values("avg_ch4_g", ascending=False).reset_index(drop=True)
    top3 = by_avg.head(3)[["AnimalName", "avg_ch4_g", "total_visits"]].to_dict("records")
    low3 = by_avg.tail(3)[["AnimalName", "avg_ch4_g", "total_visits"]].to_dict("records")

    return {
        "fid": fid,
        "animals": animals,
        "dates": dates,
        "animal_date_lookup": animal_date_lookup,
        "animal_avg_lookup": {k: float(v) for k, v in animal_avg_lookup.items()},
        "visits_table": agg[["AnimalName", "total_visits", "avg_ch4_g"]].to_dict("records"),
        "top3_avg_ch4": top3,
        "low3_avg_ch4": low3,
    }


# ---------------------------------------------------------------------------
# Step 3: Generate HTML report
# ---------------------------------------------------------------------------


def generate_html_report(data: dict) -> str:
    """Build interactive HTML report with dropdowns and tables."""
    fid = data["fid"]
    animals_json = json.dumps(data["animals"])
    dates_json = json.dumps(data["dates"])
    lookup_json = json.dumps(data["animal_date_lookup"])
    avg_lookup_json = json.dumps(data["animal_avg_lookup"])

    # Build visits table rows (high to low)
    visits_rows = ""
    for row in data["visits_table"]:
        visits_rows += f"""
        <tr>
            <td>{row['AnimalName']}</td>
            <td>{row['total_visits']}</td>
            <td>{row['avg_ch4_g']:.2f}</td>
        </tr>"""

    # Top 3 and lowest 3 summary
    top3_html = ""
    for r in data["top3_avg_ch4"]:
        top3_html += f"<li><strong>Animal {r['AnimalName']}</strong>: {r['avg_ch4_g']:.2f} g CH4/visit (avg), {r['total_visits']} visits</li>"

    low3_html = ""
    for r in data["low3_avg_ch4"]:
        low3_html += f"<li><strong>Animal {r['AnimalName']}</strong>: {r['avg_ch4_g']:.2f} g CH4/visit (avg), {r['total_visits']} visits</li>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Methane Emissions Report - GreenFeeder {fid}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #f5f5f5; }}
        h1 {{ color: #1a5f2a; border-bottom: 2px solid #1a5f2a; padding-bottom: 8px; }}
        h2 {{ color: #2d7a3e; margin-top: 28px; }}
        .fid-badge {{ display: inline-block; background: #1a5f2a; color: white; padding: 8px 16px; border-radius: 6px; font-weight: bold; margin-bottom: 20px; }}
        .filters {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 24px; }}
        .filters label {{ display: block; margin-bottom: 6px; font-weight: 600; color: #333; }}
        .filters select {{ padding: 8px 12px; font-size: 14px; min-width: 200px; border-radius: 4px; border: 1px solid #ccc; }}
        .result-box {{ background: #e8f5e9; padding: 16px; border-radius: 6px; margin-top: 12px; border-left: 4px solid #1a5f2a; }}
        .result-box strong {{ color: #1a5f2a; }}
        table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #1a5f2a; color: white; font-weight: 600; }}
        tr:hover {{ background: #f9f9f9; }}
        ul {{ line-height: 1.8; }}
        .summary-box {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-top: 20px; }}
    </style>
</head>
<body>
    <h1>Methane Emissions Report</h1>
    <div class="fid-badge">GreenFeeder (FID): {fid}</div>

    <div class="filters">
        <h2>Filter by Animal & Date</h2>
        <label for="animal-select">Select Animal:</label>
        <select id="animal-select">
            <option value="">-- Choose an animal --</option>
        </select>
        <label for="date-select" style="margin-top: 12px;">Select Date:</label>
        <select id="date-select">
            <option value="">-- Choose a date --</option>
        </select>
        <div id="avg-result" class="result-box" style="display: none;">
            <strong>Average methane emission:</strong> <span id="avg-value"></span> g
        </div>
    </div>

    <h2>Total Visits per Animal (High to Low)</h2>
    <table>
        <thead>
            <tr>
                <th>Animal</th>
                <th>Total Visits</th>
                <th>Avg CH4 (g/visit)</th>
            </tr>
        </thead>
        <tbody>
            {visits_rows}
        </tbody>
    </table>

    <div class="summary-box">
        <h2>Top 3 Average Methane Emitters (Whole Period)</h2>
        <p>Animals with highest average CH4 per visit (grams):</p>
        <ul>
            {top3_html}
        </ul>

        <h2>Lowest 3 Average Methane Emitters (Whole Period)</h2>
        <p>Animals with lowest average CH4 per visit (grams):</p>
        <ul>
            {low3_html}
        </ul>
    </div>

    <script>
        const animals = {animals_json};
        const dates = {dates_json};
        const animalDateLookup = {lookup_json};
        const animalAvgLookup = {avg_lookup_json};

        const animalSelect = document.getElementById('animal-select');
        const dateSelect = document.getElementById('date-select');
        const avgResult = document.getElementById('avg-result');
        const avgValue = document.getElementById('avg-value');

        animals.forEach(a => {{
            const opt = document.createElement('option');
            opt.value = a;
            opt.textContent = a;
            animalSelect.appendChild(opt);
        }});
        dates.forEach(d => {{
            const opt = document.createElement('option');
            opt.value = d;
            opt.textContent = d;
            dateSelect.appendChild(opt);
        }});

        function updateAvg() {{
            const animal = animalSelect.value;
            const date = dateSelect.value;
            avgResult.style.display = 'none';
            if (!animal) return;
            if (date) {{
                const val = animalDateLookup[animal]?.[date];
                if (val !== undefined) {{
                    avgValue.textContent = val.toFixed(2) + ' (on selected date)';
                    avgResult.style.display = 'block';
                }}
            }} else {{
                const val = animalAvgLookup[animal];
                if (val !== undefined) {{
                    avgValue.textContent = val.toFixed(2) + ' (avg per visit, whole period)';
                    avgResult.style.display = 'block';
                }}
            }}
        }}

        animalSelect.addEventListener('change', updateAvg);
        dateSelect.addEventListener('change', updateAvg);
    </script>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Step 4: Save report as HTML
# ---------------------------------------------------------------------------


def save_report_html(html_content: str, output_dir: Path) -> Path:
    """Save the report as an HTML file."""
    output_path = output_dir / "emissions_report.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return output_path


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def main():
    print("1. Querying C-Lock API...")
    csv_str = query_c_lock_emissions()
    print("   Done.")

    print("2. Processing methane data (EXTRACT -> AGGREGATE -> RANK)...")
    data = process_methane_data(csv_str)
    print("   Done.")

    print("3. Generating HTML report...")
    html = generate_html_report(data)
    print("   Done.")

    print("4. Saving report as HTML...")
    output_path = save_report_html(html, script_dir)
    print(f"   Saved: {output_path}")

    print("\nMethane emissions report generated successfully!")
    print("   Open the HTML file in a browser to view the interactive report.")


if __name__ == "__main__":
    main()
