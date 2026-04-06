# lab_rag.py
# Custom RAG Workflow: C-Lock Emissions Data
# Lab assignment for 07_rag
# Uses 03_csv.py structure + C-Lock data retrieval from Multi-Agent.py

# This script demonstrates a RAG workflow that:
# 1. Retrieves emissions data from C-Lock API (or local CSV fallback)
# 2. Keeps only visit rows on (animal, calendar day) groups with >= MIN_VISITS_PER_DAY visits
# 3. Sends compact JSON (per-animal stats + small row sample) to OpenAI for a Markdown report

# 0. SETUP ###################################

## 0.1 Load Packages #################################

import io
import json
import os
import pandas as pd
from urllib import request as url_request
from dotenv import load_dotenv
from openai import OpenAI

## 0.2 Working Directory #################################

# Get the directory of the current script so paths work regardless of run location
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Repo/assignment root: parent of script folder (where .env lives)
# Works when script is in 07_rag/ or assignment_module07/lab/
REPO_ROOT = os.path.dirname(script_dir)
LOCAL_CSV = "emissions_visits_fid453_20260204_162120.csv"

## 0.3 Configuration (OpenAI) #################################

# Default matches other SYSEN 5381 scripts; override with env OPENAI_MODEL.
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_COMPLETION_TOKENS = 1500

# RAG retrieval filter: keep a row only if that animal had at least this many
# feeder visits on the same calendar day (each CSV row = one visit).
MIN_VISITS_PER_DAY = 3

LOAD_DOTENV_PATHS = [
    os.path.join(REPO_ROOT, ".env"),
    os.path.join(REPO_ROOT, "assignment_module01", "lab_submission", ".env"),
]


def _load_env():
    for path in LOAD_DOTENV_PATHS:
        if os.path.isfile(path):
            load_dotenv(path)
            return
    load_dotenv()


def get_openai_client():
    """Return OpenAI client or None if OPENAI_API_KEY is missing."""
    _load_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, timeout=120.0)


def call_openai(role, task, model=None, client=None):
    """Send system + user messages to OpenAI Chat Completions; return assistant text."""
    model = model or MODEL
    client = client or get_openai_client()
    if client is None:
        raise ValueError("OPENAI_API_KEY is not set in .env")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": role},
            {"role": "user", "content": task},
        ],
        temperature=0.2,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )
    msg = response.choices[0].message
    return (msg.content or "").strip()


def report_markdown_fallback(payload):
    """Same structure as the LLM prompt, without calling the API."""
    s = payload["summary"]
    st = s["CH4_descriptive_stats_this_subset"]
    ref = s["dataset_totals_for_reference"]
    lines = [
        "# Methane report (>= min visits per animal per day — deterministic, no LLM)",
        "",
        "## Scope",
        f"- **Visits in context:** {s['records_in_context']} ({s['unique_animals_in_context']} animals)",
        f"- **Full dataset:** {ref['all_visits']} visits, {ref['all_animals']} animals",
        f"- **Feeder ID(s):** {', '.join(map(str, s['feeder_ids']))}",
        f"- **Date range (context):** {s['date_range'][0]} to {s['date_range'][1]}",
        "",
        "## CH4 descriptive statistics (subset)",
        "| stat | g/day |",
        "|------|-------|",
        f"| count | {st.get('count', 0):.0f} |",
        f"| mean | {st.get('mean', float('nan')):.2f} |",
        f"| std | {st.get('std', float('nan')):.2f} |",
        f"| min | {st.get('min', float('nan')):.2f} |",
        f"| 50% | {st.get('50%', float('nan')):.2f} |",
        f"| max | {st.get('max', float('nan')):.2f} |",
        "",
        "## By animal (days with >= min visits per day)",
        "| Animal | Visits | Mean CH4 | Min | Max |",
        "|--------|--------|----------|-----|-----|",
    ]
    for row in payload.get("by_animal_filtered", []):
        lines.append(
            f"| {row['AnimalName']} | {row['visits']} | {row['mean_ch4_gpd']} | "
            f"{row['min_ch4_gpd']} | {row['max_ch4_gpd']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "- Summary is limited to visit days with enough trips to the feeder "
            "(retrieval filter: min visits per animal per day). "
            "Compare mean and spread to spot high-emitting animals among that group.",
        ]
    )
    return "\n".join(lines)


# 1. DATA RETRIEVAL (C-Lock API or Local CSV) ###################################


def fetch_emissions_from_api():
    """
    Fetch emissions from C-Lock API. Returns (csv_raw_str, df) or (None, empty_df).
    Uses CLOCK_USER and CLOCK_PASS from .env at repo root.
    """
    env_path = os.path.join(REPO_ROOT, ".env")
    if os.path.isfile(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()
    user = os.getenv("CLOCK_USER")
    passwd = os.getenv("CLOCK_PASS")
    if not user or not passwd:
        return None, pd.DataFrame()
    try:
        req = url_request.urlopen(
            "https://portal.c-lockinc.com/api/login",
            bytes("user=" + user + "&pass=" + passwd, "ascii"),
        )
        token = req.read().decode("ascii").strip()
        url = (
            "https://portal.c-lockinc.com/api/getemissions"
            "?d=visits&fids=453&st=2025-08-01_00:00:00&et=2025-11-01_12:00:00"
        )
        headers = {
            "Header": (
                "(OwnerID,)FeederID,AnimalName,RFID,StartTime,EndTime,GoodDataDuration,"
                "CO2GramsPerDay,CH4GramsPerDay,O2GramsPerDay,H2GramsPerDay,H2SGramsPerDay,"
            )
        }
        req_obj = url_request.Request(url, data=bytes("token=" + token, "ascii"), headers=headers)
        req = url_request.urlopen(req_obj)
        csv_raw = req.read().decode("ascii")
        return csv_raw, parse_csv_to_df(csv_raw)
    except Exception:
        return None, pd.DataFrame()


def parse_csv_to_df(csv_raw: str) -> pd.DataFrame:
    """Parse raw C-Lock CSV to DataFrame. Handles Parameters header line."""
    if not csv_raw or not csv_raw.strip():
        return pd.DataFrame()
    lines = csv_raw.strip().split("\n")
    if lines and lines[0].startswith("Parameters:"):
        csv_content = "\n".join(lines[1:])
    else:
        csv_content = csv_raw
    df = pd.read_csv(io.StringIO(csv_content))
    df["StartTime"] = pd.to_datetime(df["StartTime"], errors="coerce")
    df["Date"] = pd.to_datetime(df["StartTime"]).dt.date.astype(str)
    df["CH4GramsPerDay"] = pd.to_numeric(df["CH4GramsPerDay"], errors="coerce")
    df["AnimalName"] = df["AnimalName"].astype(str).str.strip('"').str.strip()
    if "FeederID" not in df.columns:
        df["FeederID"] = "453"
    return df.dropna(subset=["StartTime", "CH4GramsPerDay"])


def load_emissions_data():
    """
    Load emissions data: try C-Lock API first, fallback to local CSV.
    Returns DataFrame with FeederID, AnimalName, Date, CH4GramsPerDay, etc.
    """
    csv_raw, df = fetch_emissions_from_api()
    if csv_raw is not None and not df.empty:
        print("[OK] Data loaded from C-Lock API")
        return df
    # Fallback to local CSV: check parent folder first, then script folder
    for base in (REPO_ROOT, script_dir):
        csv_path = os.path.join(base, LOCAL_CSV)
        if os.path.isfile(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                csv_raw = f.read()
            df = parse_csv_to_df(csv_raw)
            print("[OK] Data loaded from local CSV (C-Lock API unavailable or keys missing)")
            return df
    raise FileNotFoundError(
        f"No data: C-Lock API failed and local file {LOCAL_CSV} not found. "
        "Set CLOCK_USER and CLOCK_PASS in .env, or ensure the CSV exists."
    )


# 2. VISIT-PER-DAY FILTER (retrieval / smaller context) ##################


def filter_min_visits_per_day(df: pd.DataFrame, min_visits: int = MIN_VISITS_PER_DAY):
    """
    Keep only visit rows where that animal had at least `min_visits` visits to the
    feeder on the same calendar day. Each row in the C-Lock export is one visit.

    Returns
    -------
    filtered_df : pd.DataFrame
        Subset of df: rows belonging to (AnimalName, Date) groups with enough visits.
    meta : dict
        Metadata for the RAG payload (transparent to the LLM).
    """
    empty_meta = {
        "filter": "min_visits_per_calendar_day",
        "min_visits_per_day": min_visits,
        "total_animals_in_dataset": 0,
        "animals_in_context": 0,
        "animal_days_passing": 0,
        "rows_before_filter": 0,
        "rows_after_filter": 0,
        "daily_counts_sample": [],
    }
    if df.empty or "AnimalName" not in df.columns or "Date" not in df.columns:
        return df.copy(), empty_meta

    counts = (
        df.groupby(["AnimalName", "Date"], observed=True)
        .size()
        .reset_index(name="visits_that_day")
    )
    passing = counts[counts["visits_that_day"] >= min_visits]
    if passing.empty:
        return df.iloc[0:0].copy(), {
            **empty_meta,
            "total_animals_in_dataset": int(df["AnimalName"].nunique()),
            "rows_before_filter": int(len(df)),
        }

    filtered = df.merge(
        passing[["AnimalName", "Date"]],
        on=["AnimalName", "Date"],
        how="inner",
    )
    meta = {
        "filter": "min_visits_per_calendar_day",
        "min_visits_per_day": min_visits,
        "total_animals_in_dataset": int(df["AnimalName"].nunique()),
        "animals_in_context": int(filtered["AnimalName"].nunique()),
        "animal_days_passing": int(len(passing)),
        "rows_before_filter": int(len(df)),
        "rows_after_filter": int(len(filtered)),
        "daily_counts_sample": passing.sort_values(
            "visits_that_day", ascending=False
        ).head(30)[["AnimalName", "Date", "visits_that_day"]].to_dict(orient="records"),
    }
    return filtered, meta


# 3. SEARCH FUNCTION ###################################


def search_emissions(df, animal_query=None, fid=None, date_from=None, date_to=None):
    """
    Search emissions DataFrame for methane, animal, FeederID, and date.
    Optionally filter by animal ID/name, FeederID, or date range.

    Parameters
    ----------
    df : pd.DataFrame
        Emissions DataFrame from load_emissions_data()
    animal_query : str, optional
        Filter rows where AnimalName contains this (case-insensitive)
    fid : str, optional
        Filter by FeederID
    date_from : str, optional
        Start date (YYYY-MM-DD)
    date_to : str, optional
        End date (YYYY-MM-DD)

    Returns
    -------
    str
        JSON string of relevant columns (FeederID, AnimalName, Date, CH4GramsPerDay)
    """
    # Select key columns for RAG: methane, animal, fid, date
    cols = ["FeederID", "AnimalName", "Date", "CH4GramsPerDay", "StartTime"]
    cols = [c for c in cols if c in df.columns]
    out = df[cols].copy()
    if animal_query:
        mask = out["AnimalName"].astype(str).str.contains(animal_query, case=False, na=False)
        out = out[mask]
    if fid:
        out = out[out["FeederID"].astype(str) == str(fid)]
    if date_from:
        out = out[out["Date"] >= date_from]
    if date_to:
        out = out[out["Date"] <= date_to]
    # Convert for JSON (Date/StartTime as strings)
    out["Date"] = out["Date"].astype(str)
    if "StartTime" in out.columns:
        out["StartTime"] = out["StartTime"].astype(str)
    result = out.to_dict(orient="records")
    return json.dumps(result, indent=2)


# 4. RAG WORKFLOW ###################################

# Load data once
print("Loading emissions data...")
emissions_df = load_emissions_data()
n_all = len(emissions_df)
n_anim_all = emissions_df["AnimalName"].nunique()
print(f"  Records: {n_all}, Animals: {n_anim_all}")

# Retrieval filter: only rows on days when that animal visited >= MIN_VISITS_PER_DAY times
rag_df, visit_meta = filter_min_visits_per_day(emissions_df, MIN_VISITS_PER_DAY)
print(
    f"  RAG context: >= {MIN_VISITS_PER_DAY} visits per (animal, day) — "
    f"{visit_meta['animals_in_context']} animals, {len(rag_df)} visit rows, "
    f"{visit_meta['animal_days_passing']} animal-days passing "
    f"(dataset: {n_anim_all} animals, {n_all} visits)"
)

# Compact per-animal stats for the LLM (no need to send hundreds of raw rows)
per_animal = (
    rag_df.groupby("AnimalName", observed=True)
    .agg(
        visits=("CH4GramsPerDay", "count"),
        mean_ch4_gpd=("CH4GramsPerDay", "mean"),
        min_ch4_gpd=("CH4GramsPerDay", "min"),
        max_ch4_gpd=("CH4GramsPerDay", "max"),
    )
    .reset_index()
    .sort_values("visits", ascending=False)
)
per_animal_rounded = per_animal.assign(
    mean_ch4_gpd=per_animal["mean_ch4_gpd"].round(2),
    min_ch4_gpd=per_animal["min_ch4_gpd"].round(2),
    max_ch4_gpd=per_animal["max_ch4_gpd"].round(2),
)

stats = rag_df["CH4GramsPerDay"].describe()
stats_dict = {k: float(v) for k, v in stats.items()}

# Small raw sample only if you need row-level examples (cap for token budget)
MAX_SAMPLE = 15
cols = ["FeederID", "AnimalName", "Date", "CH4GramsPerDay"]
sample_records = rag_df[cols].head(MAX_SAMPLE).to_dict(orient="records")

rag_payload = {
    "context_scope": (
        f"Only visit rows on calendar days where that animal had at least "
        f"{MIN_VISITS_PER_DAY} feeder visits that day. Sparse days are excluded."
    ),
    "retrieval": visit_meta,
    "summary": {
        "records_in_context": len(rag_df),
        "unique_animals_in_context": int(rag_df["AnimalName"].nunique()),
        "dataset_totals_for_reference": {
            "all_visits": n_all,
            "all_animals": int(n_anim_all),
        },
        "feeder_ids": rag_df["FeederID"].astype(str).unique().tolist(),
        "date_range": [str(rag_df["Date"].min()), str(rag_df["Date"].max())],
        "CH4_descriptive_stats_this_subset": stats_dict,
    },
    "by_animal_filtered": per_animal_rounded.to_dict(orient="records"),
    "sample_visit_rows": sample_records,
}
result1_json = json.dumps(rag_payload, indent=2)

# Task 2: System prompt — scoped to the filtered subset
role = (
    "You are a methane emissions data analyst. The JSON describes ONLY GreenFeed visits kept "
    "under a per-day rule: each row is a visit, and we only include days where that animal "
    f"had at least {MIN_VISITS_PER_DAY} visits that calendar day (see context_scope and retrieval). "
    "Produce short Markdown:\n"
    "1) **Scope**: State how many animals, visit rows, and animal-days are in context vs dataset totals.\n"
    "2) **CH4 stats**: One small table (mean, median, min, max, std) for this subset.\n"
    "3) **By animal**: Brief bullets or a tiny table from by_animal_filtered (visits + mean CH4).\n"
    "4) **Interpretation**: 2 sentences on patterns in this high-visit-day subset only.\n"
    "Output ONLY raw Markdown, no code fences."
)

# Call OpenAI, or skip for a fast deterministic report
print("\nSending JSON to OpenAI for analysis...", flush=True)
print(
    f"(Model: {MODEL}. Set OPENAI_API_KEY in repo .env. "
    "To skip the API: LAB_RAG_SKIP_LLM=1)",
    flush=True,
)
skip_llm = os.environ.get("LAB_RAG_SKIP_LLM", "").strip().lower() in ("1", "true", "yes")
if skip_llm:
    print("LAB_RAG_SKIP_LLM is set — generating Markdown without OpenAI.", flush=True)
    result2 = report_markdown_fallback(rag_payload)
else:
    _client = get_openai_client()
    if _client is None:
        print("OPENAI_API_KEY not set — using deterministic fallback report.", flush=True)
        result2 = report_markdown_fallback(rag_payload)
    else:
        try:
            result2 = call_openai(
                role=role, task=result1_json, model=MODEL, client=_client
            )
        except KeyboardInterrupt:
            print("\nInterrupted — printing deterministic fallback report.", flush=True)
            result2 = report_markdown_fallback(rag_payload)
        except Exception as exc:
            print(f"\nOpenAI request failed ({exc}). Using fallback report.", flush=True)
            result2 = report_markdown_fallback(rag_payload)

# View result
print("\n" + "=" * 60)
print("RAG Output: Descriptive Statistics & Summary Table")
print("=" * 60)
print(result2)
print()

# 5. OPTIONAL: Filtered Query Example ###################################
# Uncomment to test RAG with a specific animal or date range
# input_query = {"animal": "2749", "fid": "453"}
# filtered_json = search_emissions(
#     emissions_df,
#     animal_query=input_query.get("animal"),
#     fid=input_query.get("fid"),
# )
# role_filtered = "Summarize the methane emissions for the filtered records. Include mean CH4, min, max, and a brief table. Output Markdown only."
# result_filtered = call_openai(role=role_filtered, task=filtered_json, model=MODEL)
# print("Filtered Query Result:")
# print(result_filtered)
