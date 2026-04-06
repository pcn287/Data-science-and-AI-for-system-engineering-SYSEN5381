# lab_tool_function.py
# C-Lock emissions: retrieval filter + Agent 2 with function calling (linear mixed model).
#
# Agent 1 (code): loads data, applies >= MIN_VISITS_PER_DAY filter, builds rag_payload + visit-level
#   observations (animal, ch4, co2) for modeling.
# Agent 2 (LLM + tool): must call fit_lmm_ch4_on_co2 (CH4 ~ CO2, random intercept for animal);
#   Python runs statsmodels MixedLM; tool output returns to the model for a Markdown report.

# 0. SETUP ###################################

## 0.1 Load Packages #################################

import io
import json
import os
import warnings
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

# Cap rows passed into the LMM tool (token limits); subsample with seed if larger.
MAX_LMM_OBSERVATIONS = int(os.environ.get("LAB_LMM_MAX_OBS", "1200"))

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


# --- Linear mixed model tool (Agent 2) + one tool round then final text ---

TOOL_LMM_CH4_CO2 = {
    "type": "function",
    "function": {
        "name": "fit_lmm_ch4_on_co2",
        "description": (
            "Fit a linear mixed model with CH4 (g/day) as response, CO2 (g/day) as fixed effect, "
            "and a random intercept for animal, on the server-preloaded filtered visit-level data. "
            "Call with an empty JSON object {} — do not paste observations (avoids huge slow payloads)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "observations": {
                    "type": "array",
                    "description": (
                        "Optional override rows {animal, ch4, co2}. Normally omit this key and call {} "
                        "so the server uses pre-loaded data."
                    ),
                    "items": {
                        "type": "object",
                        "required": ["animal", "ch4", "co2"],
                        "properties": {
                            "animal": {"type": "string"},
                            "ch4": {"type": "number"},
                            "co2": {"type": "number"},
                        },
                    },
                }
            },
        },
    },
}


def fit_lmm_ch4_on_co2(observations) -> str:
    """
    CH4 ~ CO2 with random intercept for animal (visit-level rows).
    Returns plain-text model summary for the LLM to interpret.
    """
    try:
        from statsmodels.regression.mixed_linear_model import MixedLM
    except ImportError:
        return (
            "Error: statsmodels is not installed. Run: py -m pip install statsmodels"
        )

    if isinstance(observations, str):
        observations = json.loads(observations)
    if not observations:
        return "Error: no observations provided."
    df = pd.DataFrame(observations)
    need = {"animal", "ch4", "co2"}
    if not need.issubset(set(df.columns)):
        return f"Error: observations need columns {need}, got {list(df.columns)}"
    df = df.dropna(subset=["animal", "ch4", "co2"]).copy()
    df["animal"] = df["animal"].astype(str)
    if len(df) < 10:
        return f"Error: need at least 10 valid rows, got {len(df)}"
    if df["animal"].nunique() < 2:
        return "Error: need at least 2 distinct animals for random intercept."
    try:
        model = MixedLM.from_formula("ch4 ~ co2", df, groups=df["animal"])
        with warnings.catch_warnings(record=True) as _lmm_warnings:
            warnings.simplefilter("always")
            res = model.fit(method="lbfgs", maxiter=500)
            text = res.summary().as_text()
        if _lmm_warnings:
            print(
                "[LMM] statsmodels reported numerical issues while fitting (e.g. singular random "
                "covariance, convergence on a boundary); use estimates cautiously.",
                flush=True,
            )
        if len(text) > 14000:
            text = text[:14000] + "\n... [truncated]"
        return text
    except Exception as exc:
        return f"LMM fit failed: {exc!r}"


def build_lmm_observations(rag_df: pd.DataFrame) -> list:
    """Visit-level dicts for the tool: {animal, ch4, co2} from filtered GreenFeed rows."""
    if rag_df.empty or "CO2GramsPerDay" not in rag_df.columns:
        return []
    sub = rag_df[["AnimalName", "CH4GramsPerDay", "CO2GramsPerDay"]].dropna()
    if sub.empty:
        return []
    sub = sub.rename(
        columns={
            "AnimalName": "animal",
            "CH4GramsPerDay": "ch4",
            "CO2GramsPerDay": "co2",
        }
    )
    obs = sub.to_dict(orient="records")
    if len(obs) > MAX_LMM_OBSERVATIONS:
        obs = (
            sub.sample(n=MAX_LMM_OBSERVATIONS, random_state=42)
            .to_dict(orient="records")
        )
    return obs


def run_agent2_lmm_then_report(
    client: OpenAI,
    system_prompt: str,
    user_content: str,
    observations_preloaded: list,
    model: str | None = None,
    max_tokens: int = 2800,
) -> str:
    """
    One OpenAI turn with tools; execute fit_lmm_ch4_on_co2; second completion without tools
    for Markdown report.

    observations_preloaded is used when the model calls the tool with {} or omits observations
    (avoids sending ~1k rows through the model twice — that was the main slowdown).
    """
    model = model or MODEL
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    print("  [OpenAI] Request 1/2: tool call (small payload)...", flush=True)
    r1 = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=[TOOL_LMM_CH4_CO2],
        tool_choice="auto",
        temperature=0.2,
        max_completion_tokens=max_tokens,
    )
    msg = r1.choices[0].message
    if not msg.tool_calls:
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Call fit_lmm_ch4_on_co2 once with empty arguments: {} "
                    "(the server already has the visit-level observations)."
                ),
            }
        )
        print("  [OpenAI] Retrying tool call...", flush=True)
        r1 = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[TOOL_LMM_CH4_CO2],
            tool_choice="auto",
            temperature=0.2,
            max_completion_tokens=max_tokens,
        )
        msg = r1.choices[0].message

    if not msg.tool_calls:
        return (
            msg.content
            or "Model did not call fit_lmm_ch4_on_co2; cannot attach LMM output."
        )

    messages.append(
        {
            "role": "assistant",
            "content": msg.content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        }
    )
    for tc in msg.tool_calls:
        name = tc.function.name
        raw_args = tc.function.arguments or "{}"
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        if name == "fit_lmm_ch4_on_co2":
            obs_arg = args.get("observations")
            if obs_arg is None or (
                isinstance(obs_arg, list) and len(obs_arg) == 0
            ):
                out = fit_lmm_ch4_on_co2(observations_preloaded)
            else:
                out = fit_lmm_ch4_on_co2(obs_arg)
        else:
            out = f"Unknown tool: {name}"

        if name == "fit_lmm_ch4_on_co2":
            print("\n" + "=" * 60, flush=True)
            print(
                "[LMM] statsmodels MixedLM summary (formula: ch4 ~ co2; random intercept: animal)",
                flush=True,
            )
            print("=" * 60, flush=True)
            print(out, flush=True)
            print("=" * 60 + "\n", flush=True)

        messages.append(
            {"role": "tool", "tool_call_id": tc.id, "content": str(out)}
        )

    print("  [Python] MixedLM fit done. [OpenAI] Request 2/2: final report...", flush=True)
    r2 = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_completion_tokens=max_tokens,
    )
    return (r2.choices[0].message.content or "").strip()


def _stats_table_md(title: str, st: dict) -> list:
    """Markdown lines for one describe() dict (g/day)."""
    return [
        title,
        "| stat | g/day |",
        "|------|-------|",
        f"| count | {st.get('count', 0):.0f} |",
        f"| mean | {st.get('mean', float('nan')):.2f} |",
        f"| std | {st.get('std', float('nan')):.2f} |",
        f"| min | {st.get('min', float('nan')):.2f} |",
        f"| 50% | {st.get('50%', float('nan')):.2f} |",
        f"| max | {st.get('max', float('nan')):.2f} |",
        "",
    ]


def report_markdown_fallback(payload):
    """Same structure as the LLM prompt, without calling the API."""
    s = payload["summary"]
    st = s["CH4_descriptive_stats_this_subset"]
    st_co2 = s.get("CO2_descriptive_stats_this_subset")
    ref = s["dataset_totals_for_reference"]
    lines = [
        "# Emissions report CH4 + CO2 (>= min visits per animal per day — deterministic, no LLM)",
        "",
        "## Scope",
        f"- **Visits in context:** {s['records_in_context']} ({s['unique_animals_in_context']} animals)",
        f"- **Full dataset:** {ref['all_visits']} visits, {ref['all_animals']} animals",
        f"- **Feeder ID(s):** {', '.join(map(str, s['feeder_ids']))}",
        f"- **Date range (context):** {s['date_range'][0]} to {s['date_range'][1]}",
        "",
    ]
    lines.extend(_stats_table_md("## CH4 descriptive statistics (subset)", st))
    if st_co2:
        lines.extend(_stats_table_md("## CO2 descriptive statistics (subset)", st_co2))

    by_anim = payload.get("by_animal_filtered", [])
    has_co2 = by_anim and "mean_co2_gpd" in by_anim[0]
    lines.append("## By animal (days with >= min visits per day)")
    if has_co2:
        lines.extend(
            [
                "| Animal | Visits | Mean CH4 | Min CH4 | Max CH4 | Mean CO2 | Min CO2 | Max CO2 |",
                "|--------|--------|----------|---------|---------|----------|---------|---------|",
            ]
        )
        for row in by_anim:
            lines.append(
                f"| {row['AnimalName']} | {row['visits']} | {row['mean_ch4_gpd']} | "
                f"{row['min_ch4_gpd']} | {row['max_ch4_gpd']} | {row['mean_co2_gpd']} | "
                f"{row['min_co2_gpd']} | {row['max_co2_gpd']} |"
            )
    else:
        lines.extend(
            [
                "| Animal | Visits | Mean CH4 | Min | Max |",
                "|--------|--------|----------|-----|-----|",
            ]
        )
        for row in by_anim:
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
            "Compare CH4 and CO2 means and spread among animals in this subset.",
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
    if "CO2GramsPerDay" in df.columns:
        df["CO2GramsPerDay"] = pd.to_numeric(df["CO2GramsPerDay"], errors="coerce")
    df["AnimalName"] = df["AnimalName"].astype(str).str.strip('"').str.strip()
    if "FeederID" not in df.columns:
        df["FeederID"] = "453"
    return df.dropna(subset=["StartTime", "CH4GramsPerDay"])


def load_emissions_data():
    """
    Load emissions data: try C-Lock API first, fallback to local CSV.
    Returns DataFrame with FeederID, AnimalName, Date, CH4GramsPerDay, CO2GramsPerDay (if present), etc.
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
    Search emissions DataFrame for CH4/CO2, animal, FeederID, and date.
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
        JSON string of relevant columns (FeederID, AnimalName, Date, CH4GramsPerDay, CO2 if present)
    """
    # Select key columns for RAG: gases, animal, fid, date
    cols = ["FeederID", "AnimalName", "Date", "CH4GramsPerDay", "CO2GramsPerDay", "StartTime"]
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


# 4. RAG WORKFLOW + AGENT 2 (LMM TOOL OR DESCRIPTIVE FALLBACK) ##################


def main():
    # --- Agent 1 (code): load, filter, build tables / JSON context ---
    print("Loading emissions data...")
    emissions_df = load_emissions_data()
    n_all = len(emissions_df)
    n_anim_all = emissions_df["AnimalName"].nunique()
    print(f"  Records: {n_all}, Animals: {n_anim_all}")

    rag_df, visit_meta = filter_min_visits_per_day(emissions_df, MIN_VISITS_PER_DAY)
    print(
        f"  RAG context: >= {MIN_VISITS_PER_DAY} visits per (animal, day) — "
        f"{visit_meta['animals_in_context']} animals, {len(rag_df)} visit rows, "
        f"{visit_meta['animal_days_passing']} animal-days passing "
        f"(dataset: {n_anim_all} animals, {n_all} visits)"
    )

    _agg = {
        "visits": ("CH4GramsPerDay", "count"),
        "mean_ch4_gpd": ("CH4GramsPerDay", "mean"),
        "min_ch4_gpd": ("CH4GramsPerDay", "min"),
        "max_ch4_gpd": ("CH4GramsPerDay", "max"),
    }
    if "CO2GramsPerDay" in rag_df.columns:
        _agg["mean_co2_gpd"] = ("CO2GramsPerDay", "mean")
        _agg["min_co2_gpd"] = ("CO2GramsPerDay", "min")
        _agg["max_co2_gpd"] = ("CO2GramsPerDay", "max")

    per_animal = (
        rag_df.groupby("AnimalName", observed=True)
        .agg(**_agg)
        .reset_index()
        .sort_values("visits", ascending=False)
    )
    per_animal_rounded = per_animal.assign(
        mean_ch4_gpd=per_animal["mean_ch4_gpd"].round(2),
        min_ch4_gpd=per_animal["min_ch4_gpd"].round(2),
        max_ch4_gpd=per_animal["max_ch4_gpd"].round(2),
    )
    if "mean_co2_gpd" in per_animal.columns:
        per_animal_rounded = per_animal_rounded.assign(
            mean_co2_gpd=per_animal["mean_co2_gpd"].round(2),
            min_co2_gpd=per_animal["min_co2_gpd"].round(2),
            max_co2_gpd=per_animal["max_co2_gpd"].round(2),
        )

    stats = rag_df["CH4GramsPerDay"].describe()
    stats_dict = {k: float(v) for k, v in stats.items()}

    summary_block = {
        "records_in_context": len(rag_df),
        "unique_animals_in_context": int(rag_df["AnimalName"].nunique()),
        "dataset_totals_for_reference": {
            "all_visits": n_all,
            "all_animals": int(n_anim_all),
        },
        "feeder_ids": rag_df["FeederID"].astype(str).unique().tolist(),
        "date_range": [str(rag_df["Date"].min()), str(rag_df["Date"].max())],
        "CH4_descriptive_stats_this_subset": stats_dict,
    }
    if "CO2GramsPerDay" in rag_df.columns:
        co2_stats = rag_df["CO2GramsPerDay"].describe()
        summary_block["CO2_descriptive_stats_this_subset"] = {
            k: float(v) for k, v in co2_stats.items()
        }

    MAX_SAMPLE = 15
    cols = ["FeederID", "AnimalName", "Date", "CH4GramsPerDay"]
    if "CO2GramsPerDay" in rag_df.columns:
        cols.append("CO2GramsPerDay")
    sample_records = rag_df[cols].head(MAX_SAMPLE).to_dict(orient="records")

    rag_payload = {
        "context_scope": (
            f"Only visit rows on calendar days where that animal had at least "
            f"{MIN_VISITS_PER_DAY} feeder visits that day. Sparse days are excluded."
        ),
        "retrieval": visit_meta,
        "summary": summary_block,
        "by_animal_filtered": per_animal_rounded.to_dict(orient="records"),
        "sample_visit_rows": sample_records,
    }
    result1_json = json.dumps(rag_payload, indent=2)

    lmm_obs = build_lmm_observations(rag_df)

    role_descriptive = (
        "You are a GreenFeed emissions analyst (CH4 and CO2 in g/day). The JSON describes ONLY visits kept "
        "under a per-day rule: each row is a visit, and we only include days where that animal "
        f"had at least {MIN_VISITS_PER_DAY} visits that calendar day (see context_scope and retrieval). "
        "Produce short Markdown:\n"
        "1) **Scope**: State how many animals, visit rows, and animal-days are in context vs dataset totals.\n"
        "2) **CH4 stats**: One small table (mean, median, min, max, std) from summary.\n"
        "3) **CO2 stats**: If CO2_descriptive_stats_this_subset is present, same table for CO2; else note CO2 missing.\n"
        "4) **By animal**: Brief bullets or a tiny table from by_animal_filtered (visits, mean CH4, mean CO2 if present).\n"
        "5) **Interpretation**: 2 sentences on CH4/CO2 patterns in this high-visit-day subset only.\n"
        "Output ONLY raw Markdown, no code fences."
    )

    role_lmm = (
        "You are a systems / data analyst for GreenFeed visit-level emissions (CH4 and CO2, g/day). "
        f"Data were filtered: only days with at least {MIN_VISITS_PER_DAY} visits per animal per day.\n"
        "The user JSON includes context (summary tables and metadata) and how many visit rows were "
        "pre-loaded on the server for the mixed model.\n"
        "You MUST call the tool fit_lmm_ch4_on_co2 exactly once with empty arguments: {} "
        "(do not pass observations — the server uses pre-loaded data; passing large arrays is slow and unnecessary).\n"
        "After you receive the tool output (statsmodels LMM summary), write Markdown only:\n"
        "1) **Scope**: Briefly state n visits, n animals, and the retrieval rule.\n"
        "2) **Model**: State the model as CH4 ~ CO2 with random intercept for animal; summarize fixed effects "
        "(intercept, CO2 slope) and any reported random-effect variance from the tool text.\n"
        "3) **Interpretation**: 2–3 cautious sentences (correlation vs causation; animals as repeated measures).\n"
        "Output ONLY raw Markdown, no code fences."
    )

    use_lmm = bool(lmm_obs)
    agent2_user = json.dumps(
        {
            "context": rag_payload,
            "lmm_visit_rows_preloaded": len(lmm_obs),
            "lmm_max_rows_cap": MAX_LMM_OBSERVATIONS,
            "instruction": (
                "Call fit_lmm_ch4_on_co2 with {} only. Observations are already on the server."
            ),
        },
        separators=(",", ":"),
    )

    skip_llm = os.environ.get("LAB_RAG_SKIP_LLM", "").strip().lower() in ("1", "true", "yes")
    print("\nSending to OpenAI (Agent 2)...", flush=True)
    if skip_llm:
        print("  LAB_RAG_SKIP_LLM: deterministic markdown only (no LMM tool call).", flush=True)
    elif use_lmm:
        print("  Mode: function calling + linear mixed model (CH4 ~ CO2, random intercept animal).", flush=True)
    else:
        print("  Mode: descriptive only (no CO2 or no rows for LMM).", flush=True)
    print(
        f"(Model: {MODEL}. Set OPENAI_API_KEY in repo .env. "
        "To skip the API: LAB_RAG_SKIP_LLM=1)",
        flush=True,
    )

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
                if use_lmm:
                    result2 = run_agent2_lmm_then_report(
                        _client,
                        role_lmm,
                        agent2_user,
                        observations_preloaded=lmm_obs,
                        model=MODEL,
                    )
                else:
                    result2 = call_openai(
                        role=role_descriptive,
                        task=result1_json,
                        model=MODEL,
                        client=_client,
                    )
            except KeyboardInterrupt:
                print("\nInterrupted — printing deterministic fallback report.", flush=True)
                result2 = report_markdown_fallback(rag_payload)
            except Exception as exc:
                print(f"\nOpenAI request failed ({exc}). Using fallback report.", flush=True)
                result2 = report_markdown_fallback(rag_payload)

    print("\n" + "=" * 60)
    out_label = "Output: CH4 + CO2 summary"
    if use_lmm and not skip_llm:
        out_label += " (Agent 2: LMM tool + narrative)"
    elif use_lmm and skip_llm:
        out_label += " (deterministic; rerun without LAB_RAG_SKIP_LLM for LMM tool)"
    print(out_label)
    print("=" * 60)
    print(result2)
    print()


if __name__ == "__main__":
    main()

# 5. OPTIONAL: Filtered Query Example ###################################
# Uncomment inside main() or a notebook to test search_emissions + call_openai.
