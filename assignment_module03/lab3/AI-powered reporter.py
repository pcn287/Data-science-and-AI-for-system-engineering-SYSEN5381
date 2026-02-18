"""
AI-Powered Data Reporter (Lab 3)
1. Queries C-Lock emissions API for data.
2. Uses OpenAI to analyze, summarize, and generate an HTML report.
"""

import os
from pathlib import Path
from urllib import request

from dotenv import load_dotenv
from openai import OpenAI

script_dir = Path(__file__).resolve().parent
load_dotenv(script_dir.parent.parent / ".env")

MAX_DATA_CHARS = 50000  # Limit for API context; truncate if larger


def query_c_lock() -> str:
    """Fetch emissions data from C-Lock API. Returns raw CSV."""
    user, pw = os.getenv("CLOCK_USER"), os.getenv("CLOCK_PASS")
    if not user or not pw:
        raise ValueError("CLOCK_USER and CLOCK_PASS must be set in .env")

    req = request.urlopen(
        "https://portal.c-lockinc.com/api/login",
        bytes(f"user={user}&pass={pw}", "ascii"),
    )
    token = req.read().decode("ascii").strip()

    url = "https://portal.c-lockinc.com/api/getemissions?d=visits&fids=453&st=2025-08-01_00:00:00&et=2025-11-01_12:00:00"
    headers = {"Header": "(OwnerID,)FeederID,AnimalName,RFID,StartTime,EndTime,GoodDataDuration,CO2GramsPerDay,CH4GramsPerDay,O2GramsPerDay,H2GramsPerDay,H2SGramsPerDay,AirflowLitersPerSec,AirflowCf,WindSpeedMetersPerSec,WindDirDeg,WindCf,WasInterrupted,InterruptingTags,TempPipeDegreesCelsius,IsPreliminary,RunTime"}
    req_obj = request.Request(url, data=bytes(f"token={token}", "ascii"), headers=headers)
    return request.urlopen(req_obj).read().decode("ascii")


def generate_report_with_openai(csv_data: str) -> str:
    """Use OpenAI to analyze the data and generate an HTML report."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY must be set in .env")

    # Truncate if too large for context
    data = csv_data[:MAX_DATA_CHARS] + ("\n... [truncated]" if len(csv_data) > MAX_DATA_CHARS else "")

    client = OpenAI(api_key=api_key, timeout=60)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a data analyst. Analyze the emissions CSV data, summarize key findings (trends, top/low emitters, stats), and produce a complete HTML report. Use inline CSS, green theme (#1a5f2a). Output ONLY raw HTML, no markdown."},
            {"role": "user", "content": f"Analyze this C-Lock GreenFeeder emissions data and generate an HTML report:\n\n{data}"},
        ],
        temperature=0.3,
    )
    html = response.choices[0].message.content.strip()
    if html.startswith("```"):
        html = html.split("\n", 1)[1] if "\n" in html else html[3:]
        if html.endswith("```"):
            html = html.rsplit("```", 1)[0].strip()
    return html


def main():
    print("1. Querying C-Lock API...")
    csv_data = query_c_lock()
    print("   Done.")

    print("2. Analyzing data and generating report with OpenAI...")
    html = generate_report_with_openai(csv_data)
    print("   Done.")

    out_path = script_dir / "emissions_report.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"3. Saved: {out_path}")


if __name__ == "__main__":
    main()
