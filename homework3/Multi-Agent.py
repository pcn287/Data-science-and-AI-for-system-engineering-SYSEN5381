"""
Homework 3: AI Report Validation System for GreenFeed methane reports.

This file matches the Homework 3 requirement from the course page:
1. Generate AI reports from multiple prompt variants.
2. Validate each report with a customized qualitative content analysis rubric.
3. Collect repeated validation scores.
4. Use ANOVA to compare prompt performance.

Only one report-writing agent is used: it interprets the thorough CH4 descriptive
statistics. The separate AI reviewer is the validation system required for the
homework, not another reporting agent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from scipy import stats


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CSV_PATH = SCRIPT_DIR / "emissions_visits_fid453_20260204_162120.csv"
OUTPUT_DIR = SCRIPT_DIR / "outputs"
CRITERIA_PATH = SCRIPT_DIR / "validation_criteria.json"

EXTRACT_COLS = ["FeederID", "AnimalName", "StartTime", "CH4GramsPerDay"]
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
REQUEST_PAUSE_SEC = float(os.environ.get("HOMEWORK3_REQUEST_PAUSE_SEC", "0.35"))

LOAD_DOTENV_PATHS = [
    REPO_ROOT / ".env",
    REPO_ROOT / "assignment_module01" / "lab_submission" / ".env",
]


VALIDATION_CRITERIA: dict[str, dict[str, str]] = {
    "statistical_accuracy": {
        "description": "Correctly uses the provided descriptive statistics without inventing values.",
        "scale": "0-10 integer; 0 = mostly incorrect, 10 = all key numbers are accurate.",
        "benchmark": "Report should cite mean, median, spread, and high-emitter evidence accurately.",
    },
    "emissions_interpretation": {
        "description": "Explains what the CH4 statistics mean for methane emissions and animal variation.",
        "scale": "0-10 integer; 0 = no interpretation, 10 = clear domain-specific interpretation.",
        "benchmark": "Report should explain central tendency, variability, skew/outliers, and animal heterogeneity.",
    },
    "decision_support_value": {
        "description": "Provides actionable insight for monitoring, management, or mitigation decisions.",
        "scale": "0-10 integer; 0 = no actionability, 10 = directly useful recommendations.",
        "benchmark": "Report should identify useful monitoring priorities, not just summarize numbers.",
    },
    "transparency": {
        "description": "Makes clear what data were used, what statistics mean, and what limitations exist.",
        "scale": "0-10 integer; 0 = opaque, 10 = transparent scope, evidence, and limitations.",
        "benchmark": "Report should mention local visit-level data, feeder scope, and uncertainty/limits.",
    },
}


PROMPT_VARIANTS: dict[str, str] = {
    "A_basic_summary": (
        "Write a concise methane emissions interpretation for a systems engineering homework report. "
        "Focus on the most important descriptive statistics and keep the report easy to read."
    ),
    "B_decision_support": (
        "Write a decision-support interpretation for a farm manager. Emphasize monitoring priorities, "
        "which animal patterns matter most, and how the descriptive statistics can guide action."
    ),
    "C_statistical_depth": (
        "Write a statistically detailed interpretation. Explain central tendency, variability, IQR, "
        "coefficient of variation, skewness, extremes, and per-animal heterogeneity using the numbers."
    ),
}


def load_env() -> None:
    """Load API keys from the repo root or assignment-specific .env file."""
    for path in LOAD_DOTENV_PATHS:
        if path.is_file():
            load_dotenv(path)
            return
    load_dotenv()


def get_client() -> OpenAI:
    """Create the OpenAI client."""
    load_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY must be set in .env")
    return OpenAI(api_key=api_key, timeout=120)


def load_local_csv(csv_path: Path = CSV_PATH) -> pd.DataFrame:
    """Load the locally saved C-Lock emissions CSV instead of calling the API."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Local CSV not found: {csv_path}")

    first_line = csv_path.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
    skiprows = 1 if first_line.startswith("Parameters:") else 0
    return pd.read_csv(csv_path, skiprows=skiprows, low_memory=False)


def extract_columns(df: pd.DataFrame, cols: list[str] = EXTRACT_COLS) -> pd.DataFrame:
    """Extract and clean the four columns needed for methane descriptive statistics."""
    missing = [col for col in cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in CSV: {missing}")

    out = df[cols].copy()
    out["AnimalName"] = out["AnimalName"].astype(str).str.strip('"').str.strip()
    out["StartTime"] = pd.to_datetime(out["StartTime"], errors="coerce")
    out["Date"] = out["StartTime"].dt.date
    out["CH4GramsPerDay"] = pd.to_numeric(out["CH4GramsPerDay"], errors="coerce")
    return out.dropna(subset=["StartTime", "CH4GramsPerDay"]).reset_index(drop=True)


def round_values(values: dict[str, Any], digits: int = 4) -> dict[str, Any]:
    """Round float values for compact prompts and reproducible saved outputs."""
    return {
        key: round(value, digits) if isinstance(value, float) else value
        for key, value in values.items()
    }


def compute_descriptive_stats(df: pd.DataFrame, target: str = "CH4GramsPerDay") -> dict[str, Any]:
    """Compute thorough CH4 descriptive statistics for the interpretation agent."""
    if target not in df.columns:
        raise ValueError(f"Target column '{target}' not in DataFrame")

    series = df[target].astype(float)
    overall = {
        "count": int(series.count()),
        "mean": float(series.mean()),
        "median": float(series.median()),
        "std": float(series.std(ddof=1)),
        "min": float(series.min()),
        "max": float(series.max()),
        "range": float(series.max() - series.min()),
        "q1": float(series.quantile(0.25)),
        "q3": float(series.quantile(0.75)),
        "iqr": float(series.quantile(0.75) - series.quantile(0.25)),
        "p05": float(series.quantile(0.05)),
        "p95": float(series.quantile(0.95)),
        "skewness": float(series.skew()),
        "kurtosis": float(series.kurt()),
        "cv_percent": float(series.std(ddof=1) / series.mean() * 100) if series.mean() else None,
    }

    top_visitors = (
        df.groupby("AnimalName", dropna=False)
        .size()
        .sort_values(ascending=False)
        .head(10)
        .to_dict()
    )
    top_emitters = (
        df.groupby("AnimalName", dropna=False)[target]
        .agg(["count", "mean", "std", "min", "max"])
        .sort_values("mean", ascending=False)
        .head(10)
        .round(2)
        .reset_index()
        .to_dict(orient="records")
    )

    return {
        "feeder_ids": sorted(df["FeederID"].dropna().unique().tolist()),
        "n_animals": int(df["AnimalName"].nunique()),
        "date_range": {
            "start": str(df["StartTime"].min()),
            "end": str(df["StartTime"].max()),
        },
        "ch4_overall": round_values(overall),
        "top_visitors": top_visitors,
        "top_emitters_by_mean": top_emitters,
    }


def stats_to_markdown(descriptive_stats: dict[str, Any]) -> str:
    """Render descriptive statistics as Markdown for output files and screenshots."""
    overall = descriptive_stats["ch4_overall"]
    lines = [
        f"- Feeder(s): {descriptive_stats['feeder_ids']}",
        f"- Unique animals: {descriptive_stats['n_animals']}",
        f"- Date range: {descriptive_stats['date_range']['start']} to {descriptive_stats['date_range']['end']}",
        "",
        "**CH4 grams/day overall:**",
        f"- count={overall['count']}, mean={overall['mean']}, median={overall['median']}, std={overall['std']}",
        f"- min={overall['min']}, max={overall['max']}, range={overall['range']}",
        f"- Q1={overall['q1']}, Q3={overall['q3']}, IQR={overall['iqr']}",
        f"- P05={overall['p05']}, P95={overall['p95']}",
        f"- skewness={overall['skewness']}, kurtosis={overall['kurtosis']}, CV%={overall['cv_percent']}",
        "",
        "**Top visitors:**",
    ]
    for animal, visits in descriptive_stats["top_visitors"].items():
        lines.append(f"- {animal}: {visits} visits")

    lines.append("")
    lines.append("**Top emitters by mean CH4:**")
    for row in descriptive_stats["top_emitters_by_mean"]:
        lines.append(
            f"- {row['AnimalName']}: mean={row['mean']}, std={row['std']}, "
            f"min={row['min']}, max={row['max']}, n={row['count']}"
        )
    return "\n".join(lines)


def strip_code_block(text: str) -> str:
    """Remove accidental Markdown fences from model outputs."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0].strip()
    return text


def call_openai(client: OpenAI, system_prompt: str, user_prompt: str, temperature: float) -> str:
    """Call the selected OpenAI model."""
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    return strip_code_block(response.choices[0].message.content or "")


def interpretation_agent(
    client: OpenAI,
    descriptive_stats: dict[str, Any],
    prompt_variant_name: str,
    prompt_variant_instruction: str,
) -> str:
    """The only report-writing agent: interpret the descriptive statistics."""
    system_prompt = (
        "You are the single AI interpretation agent for a methane emissions report. "
        "Interpret the provided descriptive statistics only. Do not invent data, methods, "
        "or p-values. Output raw Markdown."
    )
    user_prompt = (
        f"Prompt variant: {prompt_variant_name}\n"
        f"Instruction style: {prompt_variant_instruction}\n\n"
        "Descriptive statistics for local GreenFeed visit-level CH4 data:\n"
        f"{json.dumps(descriptive_stats, indent=2)}\n\n"
        "Write a short report with: scope, key statistics, interpretation, and practical implication."
    )
    return call_openai(client, system_prompt, user_prompt, temperature=0.45)


def write_validation_criteria(path: Path = CRITERIA_PATH) -> None:
    """Save the custom rubric required by the homework."""
    payload = {
        "scale_note": "Each criterion is scored 0-10, not the Module 9 lab's generic Likert scale.",
        "criteria": VALIDATION_CRITERIA,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def make_validation_prompt(report_text: str) -> str:
    """Create the custom qualitative content analysis prompt."""
    return (
        "Evaluate this AI-generated methane emissions report using the custom validation rubric below. "
        "The rubric is tailored to GreenFeed methane report validation and uses 0-10 scores, "
        "not the lab's generic Likert criteria.\n\n"
        f"Rubric:\n{json.dumps(VALIDATION_CRITERIA, indent=2)}\n\n"
        "Return ONLY valid JSON in this exact shape:\n"
        "{\n"
        '  "statistical_accuracy": <integer 0-10>,\n'
        '  "emissions_interpretation": <integer 0-10>,\n'
        '  "decision_support_value": <integer 0-10>,\n'
        '  "transparency": <integer 0-10>,\n'
        '  "justification": "<= 80 words explaining the scores>"\n'
        "}\n\n"
        f"Report to validate:\n{report_text}"
    )


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """Parse the first JSON object from a model response."""
    match = re.search(r"\{[\s\S]*\}", raw_text or "")
    if not match:
        raise ValueError(f"No JSON object found in validator output: {raw_text[:300]!r}")
    return json.loads(match.group(0))


def validate_report(client: OpenAI, report_text: str) -> dict[str, Any]:
    """Use an AI reviewer to score one generated report against the custom rubric."""
    system_prompt = (
        "You are a strict qualitative content analysis reviewer. "
        "Score only what is present in the report. Return JSON only."
    )
    raw = call_openai(client, system_prompt, make_validation_prompt(report_text), temperature=0.15)
    parsed = extract_json_object(raw)

    result: dict[str, Any] = {}
    for key in VALIDATION_CRITERIA:
        score = int(parsed[key])
        if score < 0 or score > 10:
            raise ValueError(f"{key} score out of range: {score}")
        result[key] = score
    result["composite_score"] = round(
        sum(result[key] for key in VALIDATION_CRITERIA) / len(VALIDATION_CRITERIA),
        3,
    )
    result["justification"] = str(parsed.get("justification", "")).strip()
    return result


def run_prompt_experiment(
    client: OpenAI,
    descriptive_stats: dict[str, Any],
    iterations_per_prompt: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate reports with prompt variants and validate each output."""
    report_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []

    for prompt_name, prompt_instruction in PROMPT_VARIANTS.items():
        for run_id in range(1, iterations_per_prompt + 1):
            print(f"Generating report: {prompt_name}, run {run_id}/{iterations_per_prompt}")
            report = interpretation_agent(client, descriptive_stats, prompt_name, prompt_instruction)
            report_rows.append(
                {
                    "prompt_variant": prompt_name,
                    "run_id": run_id,
                    "report_text": report,
                }
            )

            print(f"Validating report: {prompt_name}, run {run_id}/{iterations_per_prompt}")
            scores = validate_report(client, report)
            validation_rows.append(
                {
                    "prompt_variant": prompt_name,
                    "run_id": run_id,
                    **scores,
                }
            )
            time.sleep(REQUEST_PAUSE_SEC)

    return pd.DataFrame(report_rows), pd.DataFrame(validation_rows)


def run_anova(validation_df: pd.DataFrame) -> dict[str, Any]:
    """Run one-way ANOVA comparing composite validation scores across prompt variants."""
    groups = [
        group["composite_score"].astype(float).to_numpy()
        for _, group in validation_df.groupby("prompt_variant")
    ]
    if len(groups) < 2 or any(len(group) < 2 for group in groups):
        return {
            "test": "one-way ANOVA",
            "f_statistic": None,
            "p_value": None,
            "interpretation": "Need at least two scores per prompt variant to run ANOVA.",
        }

    f_statistic, p_value = stats.f_oneway(*groups)
    best_prompt = (
        validation_df.groupby("prompt_variant")["composite_score"]
        .mean()
        .sort_values(ascending=False)
        .index[0]
    )
    return {
        "test": "one-way ANOVA",
        "f_statistic": round(float(f_statistic), 4),
        "p_value": round(float(p_value), 6),
        "best_prompt_by_mean_score": best_prompt,
        "significant_at_0.05": bool(p_value < 0.05),
        "interpretation": (
            f"{best_prompt} had the highest mean validation score. "
            f"The prompt differences are {'statistically significant' if p_value < 0.05 else 'not statistically significant'} "
            "at alpha = 0.05."
        ),
    }


def save_boxplot(validation_df: pd.DataFrame, output_path: Path) -> None:
    """Save a comparison plot for the screenshots/outputs requirement."""
    plt.figure(figsize=(9, 5))
    validation_df.boxplot(column="composite_score", by="prompt_variant", grid=False)
    plt.title("Composite Validation Scores by Prompt Variant")
    plt.suptitle("")
    plt.xlabel("Prompt Variant")
    plt.ylabel("Composite Score (0-10)")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def save_outputs(
    descriptive_stats: dict[str, Any],
    reports_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    anova_results: dict[str, Any],
) -> None:
    """Save files needed for Git links, screenshots, and homework documentation."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    write_validation_criteria()

    (OUTPUT_DIR / "descriptive_statistics.json").write_text(
        json.dumps(descriptive_stats, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "descriptive_statistics.md").write_text(
        stats_to_markdown(descriptive_stats),
        encoding="utf-8",
    )
    reports_df.to_csv(OUTPUT_DIR / "generated_reports.csv", index=False)
    validation_df.to_csv(OUTPUT_DIR / "validation_scores.csv", index=False)

    summary = validation_df.groupby("prompt_variant")["composite_score"].agg(
        ["count", "mean", "std", "min", "max"]
    )
    summary.to_csv(OUTPUT_DIR / "prompt_score_summary.csv")
    (OUTPUT_DIR / "anova_results.json").write_text(
        json.dumps(anova_results, indent=2),
        encoding="utf-8",
    )
    save_boxplot(validation_df, OUTPUT_DIR / "prompt_comparison_boxplot.png")


def print_run_summary(validation_df: pd.DataFrame, anova_results: dict[str, Any]) -> None:
    """Print compact console output for screenshots."""
    print("\n=== Validation Score Summary ===")
    print(
        validation_df.groupby("prompt_variant")["composite_score"]
        .agg(["count", "mean", "std", "min", "max"])
        .round(3)
    )
    print("\n=== ANOVA Results ===")
    print(json.dumps(anova_results, indent=2))
    print(f"\nOutputs saved in: {OUTPUT_DIR}")


def parse_args() -> argparse.Namespace:
    """Command-line arguments for quick tests or final runs."""
    parser = argparse.ArgumentParser(
        description="Homework 3 AI report validation system for GreenFeed methane reports."
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Reports/validation scores per prompt variant. Use 5+ for final homework evidence.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the full homework validation experiment."""
    args = parse_args()
    if args.iterations < 1:
        raise ValueError("--iterations must be at least 1")

    print("Loading local emissions data...")
    raw_df = load_local_csv()
    methane_df = extract_columns(raw_df)
    descriptive_stats = compute_descriptive_stats(methane_df)
    print(f"Loaded {len(methane_df)} cleaned rows for {descriptive_stats['n_animals']} animals.")
    print("\n=== Descriptive Statistics ===")
    print(stats_to_markdown(descriptive_stats))

    client = get_client()
    reports_df, validation_df = run_prompt_experiment(
        client,
        descriptive_stats,
        iterations_per_prompt=args.iterations,
    )
    anova_results = run_anova(validation_df)
    save_outputs(descriptive_stats, reports_df, validation_df, anova_results)
    print_run_summary(validation_df, anova_results)


if __name__ == "__main__":
    main()
