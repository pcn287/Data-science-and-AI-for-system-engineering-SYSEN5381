"""
AI-Powered Data Reporter (Lab 3)
1. Queries C-Lock emissions API for data.
2. Uses OpenAI to analyze, summarize, and generate HTML + Markdown reports.
"""

import os
from pathlib import Path
from urllib import request

from dotenv import load_dotenv
from openai import OpenAI

script_dir = Path(__file__).resolve().parent
load_dotenv(script_dir.parent / ".env")

MAX_DATA_CHARS = 50000


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


def _strip_code_block(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0].strip()
    return text


def generate_reports_with_openai(csv_data: str) -> tuple[str, str]:
    """Use OpenAI to analyze data and generate HTML + Markdown reports. Returns (html, md)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY must be set in .env")

    data = csv_data[:MAX_DATA_CHARS] + ("\n... [truncated]" if len(csv_data) > MAX_DATA_CHARS else "")
    client = OpenAI(api_key=api_key, timeout=60)

    # HTML report
    r1 = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a data analyst. Analyze the emissions CSV, summarize key findings. Produce a complete HTML report with inline CSS, green theme (#1a5f2a). Output ONLY raw HTML, no markdown."},
            {"role": "user", "content": f"Analyze this C-Lock GreenFeeder emissions data and generate an HTML report:\n\n{data}"},
        ],
        temperature=0.3,
    )
    html = _strip_code_block(r1.choices[0].message.content.strip())

    # Markdown report (GitHub-friendly)
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


def main():
    print("1. Querying C-Lock API...")
    csv_data = query_c_lock()
    print("   Done.")

    print("2. Analyzing data and generating reports with OpenAI...")
    html, md = generate_reports_with_openai(csv_data)
    print("   Done.")

    html_path = script_dir / "emissions_report.html"
    md_path = script_dir / "emissions_report.md"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"3. Saved: {html_path}")
    print(f"   Saved: {md_path}")


if __name__ == "__main__":
    main()
