# multi-agent.py
# C-Lock Emissions: Three-Agent Report Pipeline
# Agent 1: Extract methane data + metadata, organize in table for Agent 2.
# Agent 2: Analyze (feeder, top 5 visitors, CH4 stats) - Markdown report.
# Agent 3: Extract top mitigation priorities from the report.
# Uses OpenAI API (gpt-4o-mini).
# SYSTEM PROMPT vs USER PROMPT:
# System prompt: role="system" - defines the agent's role and behavior.
# User prompt: role="user" - the actual task/input (e.g., data to process).
# Both are in the messages list passed to client.chat.completions.create().

import io
import os
import pandas as pd
from urllib import request
from dotenv import load_dotenv
from openai import OpenAI

# --- Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # lab/ -> assignment_module06/ -> repo root
FID = "453"
# Agent 1: keep input small to avoid timeouts (80k chars causes read timeouts)
AGENT1_MAX_CHARS = 15000
LOAD_DOTENV_PATHS = [
    os.path.join(REPO_ROOT, ".env"),
    os.path.join(REPO_ROOT, "assignment_module01", "lab_submission", ".env"),
]


# 1. API Query - C-Lock emissions
def fetch_emissions_from_api():
    """Fetch emissions from C-Lock API. Returns (csv_raw_str, df) or (None, empty_df)."""
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
        )
    }
    req_obj = request.Request(URL, data=bytes("token=" + TOK, "ascii"), headers=Headers)
    req = request.urlopen(req_obj)
    csv_raw = req.read().decode("ascii")
    df = parse_csv_to_df(csv_raw)
    return csv_raw, df


def parse_csv_to_df(csv_raw: str) -> pd.DataFrame:
    """Parse raw CSV to DataFrame. Keeps FeederID if present."""
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
    if "FeederID" not in df.columns:
        df["FeederID"] = FID
    return df.dropna(subset=["StartTime", "CH4GramsPerDay"])


# 2. Three-Agent Pipeline (OpenAI)


def _strip_code_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0].strip()
    return text


def _get_client() -> OpenAI:
    for p in LOAD_DOTENV_PATHS:
        if os.path.isfile(p):
            load_dotenv(p)
            break
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY must be set in .env")
    return OpenAI(api_key=api_key, timeout=180)


def agent_1_create_table(csv_data: str, client: OpenAI) -> str:
    """Agent 1: Extract methane data and metadata, organize in table for Agent 2."""
    data = csv_data[:AGENT1_MAX_CHARS] + ("\n... [truncated]" if len(csv_data) > AGENT1_MAX_CHARS else "")
    system_prompt = (
        "You are a methane data analyst. Extract methane data and relevant metadata related to methane "
        "and organize the data in a table that can be used by Agent 2 for analysis. "
        "Include FeederID, Animal, Date, CH4 and any other methane-relevant columns. "
        "Show the first 50 rows. Output ONLY the markdown table, no code fences."
    )
    user_prompt = f"Extract and organize methane data from this CSV:\n{data}"
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return _strip_code_block(r.choices[0].message.content.strip())


def agent_2_analyze(table: str, client: OpenAI) -> str:
    """Agent 2: Analyzes the table and produces a Markdown report covering:
    1) Which feeder it is
    2) Top 5 animals by visit count
    3) CH4 emission descriptive statistics and variation"""
    system_prompt = (
        "You are an emissions data analyst. Analyze the feeder visit table and write a Markdown report with:\n"
        "1) **Feeder**: Which feeder the data is from.\n"
        "2) **Top 5 visitors**: Which animals visit the feeder most often and how many times. List the top 5.\n"
        "3) **CH4 emissions**: Descriptive statistics (mean, median, min, max, std) and whether there is big variation. Summarize the emission patterns.\n"
        "Use clear headers (# and ##), bullet points, and tables where helpful. Output ONLY raw Markdown, no code fences."
    )
    user_prompt = f"Analyze this table and write the report:\n\n{table}"
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return _strip_code_block(r.choices[0].message.content.strip())


def agent_3_mitigation(report_md: str, client: OpenAI) -> str:
    """Agent 3: Extract top mitigation priorities from the analysis report."""
    system_prompt = (
        "You are a methane mitigation advisor for livestock operations. Given an emissions analysis report, "
        "extract the most important information for reducing methane emissions. Produce a concise Markdown summary with:\n"
        "1) **Top 3–5 mitigation priorities** (e.g., high emitters to monitor, unusual patterns)\n"
        "2) **Actionable recommendations** (e.g., which animals to focus on, what to investigate)\n"
        "3) **Key metrics to track** (e.g., mean CH4, variation, visit patterns)\n"
        "Output ONLY raw Markdown, no code fences. Keep it brief and actionable."
    )
    user_prompt = f"Extract mitigation priorities from this report:\n\n{report_md}"
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return _strip_code_block(r.choices[0].message.content.strip())


# Main
if __name__ == "__main__":
    print("Fetching data from C-Lock API...")
    csv_raw, df = fetch_emissions_from_api()
    if csv_raw is None or df.empty:
        print("No data. Check CLOCK_USER and CLOCK_PASS in .env")
        exit(1)
    print(f"Fetched {len(df)} records, {len(df['AnimalName'].unique())} animals")

    client = _get_client()

    # Agent 1: Extract methane data, organize in table
    print("Agent 1: Extracting methane data and organizing table...")
    table = agent_1_create_table(csv_raw, client)
    print("=== Agent 1: Table ===")
    print(table)

    # Agent 2: Analyze table -> Markdown report
    print("Agent 2: Analyzing table...")
    report_md = agent_2_analyze(table, client)
    print("=== Agent 2: Report ===")
    print(report_md)

    # Agent 3: Mitigation priorities
    print("Agent 3: Extracting mitigation priorities...")
    priorities = agent_3_mitigation(report_md, client)
    print("=== Agent 3: Mitigation Priorities ===")
    print(priorities)
