# Homework 3 - AI Report Validation System

This homework follows the Homework 3 instructions in the course repository:
customize an AI report validator, compare multiple prompts, collect repeated
validation scores, and run a statistical test to identify the best-performing
prompt.

## System Design

The script uses local GreenFeed methane data from
`emissions_visits_fid453_20260204_162120.csv`. It does not call the C-Lock API.

The workflow is:

1. `load_local_csv()` reads the local CSV.
2. `extract_columns()` keeps the four needed fields:
   `FeederID`, `AnimalName`, `StartTime`, and `CH4GramsPerDay`.
3. `compute_descriptive_stats()` calculates a thorough CH4 summary:
   mean, median, standard deviation, min/max, range, Q1/Q3, IQR, P05/P95,
   skewness, kurtosis, coefficient of variation, top visitors, and top emitters.
4. `interpretation_agent()` is the only report-writing agent. It creates a
   short methane report from the descriptive statistics.
5. `validate_report()` acts as the AI reviewer. It scores each generated report
   using the custom methane validation rubric in `validation_criteria.json`.
6. `run_anova()` compares composite validation scores across prompt variants.

## Customized Validation Framework

The validator does not reuse the Module 9 lab's generic Likert dimensions.
Instead, it uses a methane-report-specific 0-10 rubric:

| Dimension | What It Measures | Scale | Benchmark |
|---|---|---|---|
| `statistical_accuracy` | Correct use of descriptive statistics | 0-10 | Cites mean, median, spread, and high-emitter evidence accurately |
| `emissions_interpretation` | Methane-specific interpretation quality | 0-10 | Explains central tendency, variability, skew/outliers, and animal heterogeneity |
| `decision_support_value` | Usefulness for monitoring or mitigation | 0-10 | Identifies practical monitoring priorities |
| `transparency` | Clarity about data, evidence, and limits | 0-10 | Mentions local visit-level data, feeder scope, and limitations |

The criteria are saved separately in `validation_criteria.json` so they can be
linked directly in the homework submission.

## Experimental Design

The experiment compares three prompt variants:

- `A_basic_summary`: concise homework-style interpretation.
- `B_decision_support`: farm-manager decision support interpretation.
- `C_statistical_depth`: deeper statistical interpretation.

For each prompt, the script generates `N` AI reports and validates each report
with the custom AI reviewer. The default is `N=3`; for the final homework
evidence, use `N=5` or more if time/API budget allows.

## Statistical Analysis

The script runs a one-way ANOVA on composite validation scores across prompt
variants. It reports:

- F statistic
- p-value
- best prompt by mean composite score
- whether differences are significant at alpha = 0.05

Outputs are saved in `homework3/outputs/`.

## Technical Details

Main script:

```powershell
homework3/Multi-Agent.py
```

Dependencies:

- `pandas`
- `openai`
- `python-dotenv`
- `scipy`
- `matplotlib`

Environment variable:

```env
OPENAI_API_KEY=your_openai_key
```

Optional:

```env
OPENAI_MODEL=gpt-4o-mini
HOMEWORK3_REQUEST_PAUSE_SEC=0.35
```

## Usage

Install dependencies from the repository root:

```powershell
py -m pip install -r homework3/requirements.txt
```

Run a quick smoke test with one report per prompt:

```powershell
py homework3/Multi-Agent.py --iterations 1
```

Run a stronger homework experiment with five reports per prompt:

```powershell
py homework3/Multi-Agent.py --iterations 5
```

## Output Files

After a run, the script creates:

- `outputs/descriptive_statistics.json`
- `outputs/descriptive_statistics.md`
- `outputs/generated_reports.csv`
- `outputs/validation_scores.csv`
- `outputs/prompt_score_summary.csv`
- `outputs/anova_results.json`
- `outputs/prompt_comparison_boxplot.png`

These files support the Git links, screenshots, validation results, statistical
analysis, and prompt-comparison plot required for the single `.docx` homework
submission.
