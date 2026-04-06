# Homework 2 - Multi-Agent RAG + Tool Calling

This project builds a two-agent workflow for GreenFeed emissions analysis. The script loads visit-level methane (CH4) and carbon dioxide (CO2) records, applies a retrieval filter, and generates a report with optional linear mixed model (LMM) output.

## 1) System Architecture

- **Agent 1 (Python orchestration)**:
  - Loads data from the C-Lock API (primary) or local CSV (fallback).
  - Cleans/standardizes fields and derives calendar date values.
  - Applies retrieval rule: keep only animal-days with at least `MIN_VISITS_PER_DAY` visits.
  - Builds `rag_payload` (summary stats, per-animal aggregates, retrieval metadata, sample rows).
  - Prepares `lmm_obs` rows for tool use (`animal`, `ch4`, `co2`).

- **Agent 2 (LLM analysis/reporting)**:
  - Receives compact RAG context from Agent 1.
  - In LMM mode, calls tool `fit_lmm_ch4_on_co2` exactly once.
  - Produces final Markdown report (scope, statistics, interpretation, model findings).

- **Fallback path**:
  - If API key is missing, LLM is skipped, or request fails, script returns a deterministic local Markdown report using `report_markdown_fallback`.

## 2) RAG Data Source

- **Primary source**: C-Lock API endpoint configured in `homework.py` (`API_URL`) with credentials from environment variables.
- **Fallback source**: local CSV file `emissions_visits_fid453_20260204_162120.csv`.
- **Retrieval/search function**:
  - Main retrieval filter: `filter_min_visits_per_day(df, min_visits)` for context reduction.
  - Optional helper search: `search_emissions(df, animal_query=..., fid=..., date_from=..., date_to=...)` for ad-hoc filtered lookups.

## 3) Tool Functions

| Tool name | Purpose | Inputs | Returns |
|---|---|---|---|
| `fit_lmm_ch4_on_co2` | Fit linear mixed model `CH4 ~ CO2` with random intercept by animal | `observations`: list of `{animal, ch4, co2}` (or omitted when preloaded on server side in the workflow) | Plain-text statsmodels summary (or error string) |
| `search_emissions` | Query records by animal name, feeder, and date range | `animal_query`, `fid`, `date_from`, `date_to` | JSON string of matched visit records |

## 4) Technical Details

- **Main script**: `homework.py`
- **Environment variables**:
  - `OPENAI_API_KEY` (required for Agent 2 LLM mode)
  - `OPENAI_MODEL` (optional; default in script)
  - `CLOCK_USER`, `CLOCK_PASS` (for C-Lock API access)
  - `HOMEWORK_PIPELINE_SECTIONS` (`1` for verbose pipeline blocks; default minimal output)
  - `LAB_RAG_SKIP_LLM` (`1` to force deterministic fallback)
  - `LAB_LMM_MAX_OBS` (cap rows used for LMM fitting)
- **Packages**:
  - `pandas`, `openai`, `python-dotenv`, `statsmodels`
- **Project structure (homework2)**:
  - `homework.py` - full workflow
  - `requirements.txt` - Python dependencies
  - optional CSV data file in same folder

## 5) Usage Instructions

### A. Install dependencies

From repo root or `homework2` folder:

```powershell
py -m pip install -r homework2/requirements.txt
```

### B. Configure credentials

Create/update `.env` (repo root) with:

```env
OPENAI_API_KEY=your_openai_key
CLOCK_USER=your_clock_username
CLOCK_PASS=your_clock_password
```

Optional:

```env
OPENAI_MODEL=gpt-4o-mini
HOMEWORK_PIPELINE_SECTIONS=0
LAB_LMM_MAX_OBS=1200
```

### C. Run the system

```powershell
cd homework2
py homework.py
```

### D. Expected output

- Agent 1 data load + retrieval summary lines
- RAG-filtered context generation
- Agent 2 call status
- LMM summary block (when tool is called)
- Final Markdown report in terminal

## Notes

- If C-Lock API access fails, script attempts local CSV fallback.
- If LLM call fails, script still produces a deterministic fallback report.
- Mixed model warnings may indicate boundary/singularity issues; treat estimates cautiously.
