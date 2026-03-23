# Module 07 lab — `lab_rag.py`

Loads C-Lock GreenFeed visits, keeps **animals in the top half by visit count**, sends compact JSON to **OpenAI**, prints Markdown (Python fallback if no key or API error).

## Run

```powershell
cd assignment_module07\lab
py -m pip install -r ..\requirements.txt
py lab_rag.py
```

**`.env`** (repo root or `assignment_module01/lab_submission/.env`): `OPENAI_API_KEY` (required unless `LAB_RAG_SKIP_LLM=1`). Optional: `OPENAI_MODEL`, `CLOCK_USER` / `CLOCK_PASS` for live API (else local CSV).

## Brief explanation (assignment)

**Data:** Visit-level CH₄, feeder, animal, date from the **C-Lock API** or a **local CSV** so the lab matches real data and works offline. **Retrieval:** rank animals by visit count, keep the **top half**, build JSON with subset stats, per-animal aggregates, and a small row sample; **`search_emissions`** optionally filters by animal, feeder, and dates. **System prompt:** methane analyst role, context is **only** those frequent visitors; output short Markdown (scope vs totals, CH₄ table, by-animal summary, two interpretation sentences), no code fences.
