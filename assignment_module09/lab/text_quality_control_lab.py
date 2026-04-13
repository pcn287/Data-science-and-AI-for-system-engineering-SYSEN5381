# text_quality_control_lab.py
# Module 09 lab: AI text quality control on agent-generated LMM narrative (data.txt).
# Inspired by dsai 02_ai_quality_control.py:
#   https://github.com/timothyfraser/dsai/blob/main/09_text_analysis/02_ai_quality_control.py
#
# - Criteria (1-5 Likert): formality, clarity, succinctness, relevance (scientific publication).
# - Compare mean AI scores (Ollama vs OpenAI) with Welch t-test after N repeated QC calls each (default N=3).
# - Speed: use --workers >1 for parallel iterations (esp. OpenAI), --parallel-providers to overlap Ollama+OpenAI,
#   smaller OLLAMA_MODEL, or --iterations 1 for a quick single-provider smoke test.
# - OpenAI: OPENAI_TEMPERATURE (default 0.55) avoids identical scores on every repeat; lower values can yield std=0.
# - Compare AI runs to manual scores in manual_qc_scores.json (fill after your own manual QC).

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from scipy import stats

# -----------------------------------------------------------------------------
# Paths (run from assignment_module09/lab or any cwd)
# -----------------------------------------------------------------------------
LAB_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAB_DIR.parent.parent
DATA_PATH = LAB_DIR / "data.txt"
MANUAL_PATH = LAB_DIR / "manual_qc_scores.json"

LOAD_DOTENV_PATHS = [
    REPO_ROOT / ".env",
    REPO_ROOT / "assignment_module01" / "lab_submission" / ".env",
]

CRITERIA = ("formality", "clarity", "succinctness", "relevance")

# Ollama
OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", f"http://127.0.0.1:{OLLAMA_PORT}")
# Default Ollama tag (override with env OLLAMA_MODEL). If missing locally: ollama pull <name>
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "smollm2:1.7b")
# Read timeout for POST /api/chat (large models on CPU often need several minutes).
OLLAMA_REQUEST_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "900"))

# OpenAI (REST, same pattern as upstream lab)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
# Slightly above deterministic sampling so repeated QC calls are not bitwise-identical
# (temperature 0.2–0.3 often yields std_openai = 0 across runs on the same prompt).
OPENAI_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.55"))

DEFAULT_ITERATIONS = 3
REQUEST_PAUSE_SEC = 0.35


_IO_LOCK = threading.Lock()


def _io_print(*args, **kwargs) -> None:
    """Thread-safe prints when running providers or iterations in parallel."""
    kwargs.setdefault("flush", True)
    with _IO_LOCK:
        print(*args, **kwargs)


def _ollama_base_url() -> str:
    return OLLAMA_HOST.rstrip("/")


def assert_ollama_reachable() -> list[str]:
    """Return installed model names; exit with a clear message if the daemon is down."""
    url = f"{_ollama_base_url()}/api/tags"
    try:
        r = requests.get(url, timeout=10)
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(
            f"[Ollama] Cannot connect to {url}\n"
            "  Start the Ollama app (or run `ollama serve`) and retry.\n"
            f"  Underlying error: {e}"
        ) from e
    if r.status_code != 200:
        raise SystemExit(
            f"[Ollama] GET /api/tags returned HTTP {r.status_code} at {_ollama_base_url()}\n"
            f"  Body (truncated): {r.text[:500]!r}"
        )
    payload = r.json() if r.content else {}
    return [
        m.get("name", "")
        for m in (payload.get("models") or [])
        if m.get("name")
    ]


def assert_ollama_model_installed(requested: str, installed: list[str]) -> None:
    """
    Ollama commonly responds with HTTP 404 on POST /api/chat when the model
    is not pulled or the name does not match any local tag.
    """
    if not installed:
        raise SystemExit(
            "[Ollama] No local models listed under /api/tags.\n"
            f"  Pull one that supports JSON, e.g.: ollama pull {requested}"
        )
    req_base = requested.split(":", 1)[0].lower()
    for name in installed:
        base = name.split(":", 1)[0].lower()
        if name == requested or name.startswith(requested + ":") or base == req_base:
            return
    raise SystemExit(
        f"[Ollama] Model {requested!r} is not available locally "
        "(this usually causes HTTP 404 on /api/chat).\n"
        f"  Installed models: {installed}\n"
        f"  Fix: ollama pull {requested}   OR   set OLLAMA_MODEL to one of the names above."
    )


def _load_env() -> None:
    for p in LOAD_DOTENV_PATHS:
        if p.is_file():
            load_dotenv(p)
            return
    load_dotenv()


def load_report_text(path: Path = DATA_PATH) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Report file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Report file is empty: {path}")
    return text


def create_quality_control_prompt(report_text: str) -> str:
    """QC prompt: four Likerts for scientific-publication quality + JSON-only response."""
    criteria = """
Quality control criteria (each is an integer 1-5 Likert for a scientific publication):

1. **formality**: 1 = too casual or blog-like vs 5 = appropriate formal technical prose.
2. **clarity**: 1 = confusing or vague vs 5 = clear, precise, easy to follow.
3. **succinctness**: 1 = wordy or repetitive vs 5 = concise without losing needed content.
4. **relevance**: 1 = off-topic or filler vs 5 = tightly focused on the reported analysis.

Return ONLY valid JSON (no markdown fences) in exactly this shape:
{
  "formality": <int 1-5>,
  "clarity": <int 1-5>,
  "succinctness": <int 1-5>,
  "relevance": <int 1-5>,
  "details": "<= 80 words explaining the main strengths/weaknesses>"
}
"""
    instructions = (
        "You are an expert reviewer evaluating short text blocks from an emissions "
        "analysis report (scope, model, interpretation). Score the COMBINED report text below."
    )
    return f"{instructions}\n\n{criteria}\n\n--- Report text ---\n{report_text}\n"


def _extract_json_object(text: str) -> str:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"No JSON object found in model output: {text[:400]!r}...")
    return m.group(0)


def parse_quality_control_results(raw: str) -> dict:
    raw = (raw or "").strip()
    blob = _extract_json_object(raw)
    data = json.loads(blob)
    out = {}
    for k in CRITERIA:
        v = int(data[k])
        if v < 1 or v > 5:
            raise ValueError(f"{k} out of range: {v}")
        out[k] = v
    out["details"] = str(data.get("details", "")).strip()
    return out


def query_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    url = f"{_ollama_base_url()}/api/chat"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
    }
    # (connect seconds, read seconds) — long read for 20B+ models loading into RAM/VRAM.
    req_timeout = (30, OLLAMA_REQUEST_TIMEOUT)
    try:
        r = requests.post(url, json=body, timeout=req_timeout)
        r.raise_for_status()
    except requests.exceptions.ReadTimeout as e:
        raise RuntimeError(
            f"Ollama read timed out after {OLLAMA_REQUEST_TIMEOUT}s (host {url}).\n"
            "  Large local models (e.g. gpt-oss:20b) often need more time on first run or on CPU.\n"
            "  Fix: increase wait, e.g. PowerShell:\n"
            "    $env:OLLAMA_TIMEOUT=\"1800\"\n"
            "  Or use the lab default (smollm2:1.7b) or another small tag via OLLAMA_MODEL."
        ) from e
    except requests.exceptions.HTTPError as e:
        snippet = ""
        if e.response is not None:
            snippet = (e.response.text or "")[:800]
        hint = ""
        if e.response is not None and e.response.status_code == 404:
            hint = (
                f"\n  Hint: Ollama often uses HTTP 404 when the model is missing or misnamed. "
                f"Run: ollama pull {model}"
            )
        raise RuntimeError(
            f"Ollama /api/chat failed: {e!s}. URL={url}. Response (truncated): {snippet!r}{hint}"
        ) from e
    payload = r.json()
    msg = payload.get("message") or {}
    content = msg.get("content")
    if not content:
        raise RuntimeError(
            "Ollama returned no message.content. Full JSON (truncated): "
            f"{json.dumps(payload)[:1200]!r}"
        )
    return content


def query_openai(prompt: str, api_key: str, model: str = OPENAI_MODEL) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a quality control validator. Reply with valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": OPENAI_TEMPERATURE,
    }
    r = requests.post(OPENAI_URL, headers=headers, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _run_one_iteration(
    prompt: str,
    provider: str,
    iteration: int,
    api_key: str | None,
) -> tuple[int, str, dict]:
    if provider == "ollama":
        raw = query_ollama(prompt)
    elif provider == "openai":
        if not api_key:
            raise ValueError("OPENAI_API_KEY missing for OpenAI provider.")
        raw = query_openai(prompt, api_key)
    else:
        raise ValueError("provider must be 'ollama' or 'openai'")
    parsed = parse_quality_control_results(raw)
    return iteration, raw, parsed


def run_iterations(
    prompt: str,
    provider: str,
    *,
    n: int,
    api_key: str | None,
    max_workers: int = 1,
    show_sample_raw: bool = True,
) -> pd.DataFrame:
    """
    Run n QC calls. With max_workers>1, iterations run in parallel (best for OpenAI;
    local Ollama often runs fastest at max_workers=1 unless you have spare VRAM).
    """
    max_workers = max(1, min(max_workers, n))
    rows: list[dict] = []
    first_raw: str | None = None

    if max_workers == 1:
        for i in range(1, n + 1):
            _io_print(f"  [{provider}] iteration {i}/{n} ...")
            _it, raw, parsed = _run_one_iteration(prompt, provider, i, api_key)
            if first_raw is None:
                first_raw = raw
            rows.append({"iteration": i, "provider": provider, **parsed})
            if i < n:
                time.sleep(REQUEST_PAUSE_SEC)
    else:
        _io_print(
            f"  [{provider}] {n} iterations with max_workers={max_workers} (parallel) ..."
        )
        futures = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for i in range(1, n + 1):
                fut = ex.submit(_run_one_iteration, prompt, provider, i, api_key)
                futures[fut] = i
            for fut in as_completed(futures):
                it, raw, parsed = fut.result()
                if first_raw is None:
                    first_raw = raw
                rows.append({"iteration": it, "provider": provider, **parsed})
        rows.sort(key=lambda r: r["iteration"])

    df = pd.DataFrame(rows)

    if show_sample_raw and first_raw is not None:
        _io_print(f"\n📥 [{provider}] AI response (raw, first completed iteration):")
        _io_print(first_raw.strip())
        _io_print()

    return df


def load_manual_scores(path: Path = MANUAL_PATH) -> dict | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    scores = {k: data.get(k) for k in CRITERIA}
    if any(v is None for v in scores.values()):
        return None
    for k, v in scores.items():
        scores[k] = int(v)
        if scores[k] < 1 or scores[k] > 5:
            raise ValueError(f"Manual {k} must be 1-5, got {scores[k]}")
    return scores


def welch_ttests(
    df_ollama: pd.DataFrame, df_openai: pd.DataFrame
) -> pd.DataFrame:
    """Independent two-sample Welch t-test per criterion (Ollama vs OpenAI runs)."""
    rows = []
    # SciPy can emit repeated RuntimeWarning when a sample has ~zero variance (identical
    # repeats); "once" limits console noise to a single message for this process.
    with warnings.catch_warnings():
        warnings.simplefilter("once", RuntimeWarning)
        for c in CRITERIA:
            a = df_ollama[c].astype(float).values
            b = df_openai[c].astype(float).values
            res = stats.ttest_ind(a, b, equal_var=False)
            std_o = float(a.std(ddof=1))
            std_g = float(b.std(ddof=1))
            rows.append(
                {
                    "criterion": c,
                    "mean_ollama": a.mean(),
                    "mean_openai": b.mean(),
                    "std_ollama": std_o,
                    "std_openai": std_g,
                    "t_statistic": float(res.statistic),
                    "p_value": float(res.pvalue),
                }
            )
    return pd.DataFrame(rows)


def summarize_vs_manual(df_ai: pd.DataFrame, manual: dict, label: str) -> pd.DataFrame:
    rows = []
    for c in CRITERIA:
        m = df_ai[c].mean()
        rows.append(
            {
                "criterion": c,
                "manual": manual[c],
                f"mean_{label}": m,
                f"delta_{label}_minus_manual": m - manual[c],
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI text QC lab: Ollama vs OpenAI + manual compare.")
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help="Repeated QC calls per provider (default 3).",
    )
    parser.add_argument(
        "--ollama-only",
        action="store_true",
        help="Only run Ollama (skip OpenAI and t-tests).",
    )
    parser.add_argument(
        "--openai-only",
        action="store_true",
        help="Only run OpenAI (skip Ollama and t-tests).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("QC_WORKERS", "1")),
        help=(
            "Parallel QC calls per provider (default 1). Values >1 speed up OpenAI; "
            "local Ollama is often fastest at 1 unless the machine has spare VRAM. "
            "Override with env QC_WORKERS."
        ),
    )
    parser.add_argument(
        "--parallel-providers",
        action="store_true",
        help=(
            "Run Ollama and OpenAI batches at the same time (wall-clock savings when "
            "both are enabled and OPENAI_API_KEY is set). Ignored if only one provider runs."
        ),
    )
    args = parser.parse_args()
    if args.ollama_only and args.openai_only:
        raise SystemExit("Choose at most one of --ollama-only / --openai-only.")

    _load_env()
    api_key = os.environ.get("OPENAI_API_KEY")

    report = load_report_text()
    prompt = create_quality_control_prompt(report)

    print("📝 Report for quality control (from data.txt):\n")
    print("---")
    print(report)
    print("---\n")

    n = max(1, args.iterations)
    workers = max(1, args.workers)
    both_providers = not args.ollama_only and not args.openai_only and bool(api_key)
    run_parallel_providers = both_providers and args.parallel_providers

    if both_providers and n < 2:
        print(
            "Note: Welch t-tests need at least 2 iterations per provider; "
            "raising --iterations to 2 for model comparison.\n"
        )
        n = 2

    print(
        f"\nRunning {n} QC iteration(s) per enabled provider (workers={workers})",
        end="",
        flush=True,
    )
    if run_parallel_providers:
        print(" — Ollama and OpenAI will run concurrently.\n", flush=True)
    else:
        print(".\n", flush=True)

    df_o = df_g = None

    def _save_results_csv(label: str, df: pd.DataFrame, csv_path: Path) -> None:
        df.to_csv(csv_path, index=False)
        print(f"[{label}] Saved iteration results: {csv_path}", flush=True)

    if run_parallel_providers:
        installed = assert_ollama_reachable()
        assert_ollama_model_installed(OLLAMA_MODEL, installed)
        print(
            f"[Ollama] Using model {OLLAMA_MODEL!r} at {_ollama_base_url()} "
            f"({len(installed)} local model(s) reported).",
            flush=True,
        )
        print(
            f"[Ollama] Read timeout: {OLLAMA_REQUEST_TIMEOUT}s "
            "(raise with $env:OLLAMA_TIMEOUT='1800' if needed).",
            flush=True,
        )
        print(f"[OpenAI] Using model {OPENAI_MODEL!r}.", flush=True)
        print("\n🤖 Querying AI for quality control (Ollama + OpenAI in parallel)...\n")
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_o = pool.submit(
                run_iterations,
                prompt,
                "ollama",
                n=n,
                api_key=None,
                max_workers=workers,
            )
            fut_g = pool.submit(
                run_iterations,
                prompt,
                "openai",
                n=n,
                api_key=api_key,
                max_workers=workers,
            )
            df_o = fut_o.result()
            df_g = fut_g.result()
        out_o = LAB_DIR / "qc_results_ollama.csv"
        out_g = LAB_DIR / "qc_results_openai.csv"
        _save_results_csv("Ollama", df_o, out_o)
        _save_results_csv("OpenAI", df_g, out_g)

    else:
        if not args.openai_only:
            installed = assert_ollama_reachable()
            assert_ollama_model_installed(OLLAMA_MODEL, installed)
            print(
                f"[Ollama] Using model {OLLAMA_MODEL!r} at {_ollama_base_url()} "
                f"({len(installed)} local model(s) reported).",
                flush=True,
            )
            print(
                f"[Ollama] Read timeout: {OLLAMA_REQUEST_TIMEOUT}s "
                "(raise with $env:OLLAMA_TIMEOUT='1800' if needed).",
                flush=True,
            )
            print("\n🤖 Querying AI for quality control (Ollama)...\n")
            df_o = run_iterations(
                prompt, "ollama", n=n, api_key=None, max_workers=workers
            )
            out_o = LAB_DIR / "qc_results_ollama.csv"
            _save_results_csv("Ollama", df_o, out_o)

        if not args.ollama_only:
            if not api_key:
                print(
                    "\n[OpenAI] OPENAI_API_KEY not set — skipping OpenAI runs and t-tests."
                )
            else:
                print(f"\n[OpenAI] Using model {OPENAI_MODEL!r}.", flush=True)
                print("\n🤖 Querying AI for quality control (OpenAI)...\n")
                df_g = run_iterations(
                    prompt, "openai", n=n, api_key=api_key, max_workers=workers
                )
                out_g = LAB_DIR / "qc_results_openai.csv"
                _save_results_csv("OpenAI", df_g, out_g)

    manual = load_manual_scores()
    if manual is None:
        print(
            "\n[Manual QC] Fill integer 1-5 for each key in manual_qc_scores.json "
            f"(template: {MANUAL_PATH.name}), then re-run to compare AI vs manual."
        )
    else:
        print("\n[Manual QC] Loaded scores:", manual)
        if df_o is not None:
            cmp_o = summarize_vs_manual(df_o, manual, "ollama")
            print("\nManual vs Ollama (mean over iterations):")
            print(cmp_o.to_string(index=False))
        if df_g is not None:
            cmp_g = summarize_vs_manual(df_g, manual, "openai")
            print("\nManual vs OpenAI (mean over iterations):")
            print(cmp_g.to_string(index=False))

    if df_o is not None and df_g is not None:
        if n < 2:
            print(
                "\nWelch t-test skipped: need at least --iterations 2 per provider "
                "for two-sample comparison."
            )
        else:
            tt = welch_ttests(df_o, df_g)
            print("\nWelch t-test (Ollama vs OpenAI), independent samples per criterion:")
            print(tt.to_string(index=False))
            out_t = LAB_DIR / "qc_model_comparison_ttests.csv"
            tt.to_csv(out_t, index=False)
            print(f"\nSaved: {out_t}")

    print("\nDone.")


if __name__ == "__main__":
    main()
