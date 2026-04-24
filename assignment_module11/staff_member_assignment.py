from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_PATH = SCRIPT_DIR / "staff_client_data.txt"
STAGE1_OUTPUT_PATH = SCRIPT_DIR / "staff_assignment_stage1_output.md"
STAGE2_OUTPUT_PATH = SCRIPT_DIR / "staff_assignment_stage2_output.md"

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "smollm2:1.7b"
EXPECTED_STAFF = [
    "Alex Chen",
    "Brianna Okafor",
    "Carla Mendez",
    "Dana Park",
    "Elliot Vasquez",
    "Fiona Marsh",
]
EXPECTED_CLIENTS = [f"Client {letter}" for letter in "ABCDEFGHIJKL"]
MAX_ATTEMPTS = 3

SYSTEM_PROMPT = """You are a managing partner at a consulting firm making staffing assignments.
Your job is to read unstructured descriptions of staff members and clients,
then assign each staff member to exactly 2 clients based on fit.

Return:
Return ONLY valid JSON with this exact shape:
{
  "assignments": [
    {"staff_member": "...", "client_1": "Client A", "client_2": "Client B", "rationale": "..."},
    ...
  ],
  "summary": "3-5 sentence paragraph"
}

Rules:
- Each staff member gets exactly 2 clients
- Each client is assigned to exactly 1 staff member
- No client may be left unassigned
- Base assignments on demonstrated fit — skills, experience, communication style
- Flag any assignments where fit is weak and explain why
"""

STAGE1_USER_PROMPT_PREFIX = """Below are descriptions of our 6 staff members and 12 clients.
Please make the best possible assignments.
"""

STAGE2_FOLLOWUP_PROMPT = """Below is the Stage 1 assignment table:
{stage1_table}

I'm not sure about the assignment of Dana Park to Client J.
Can you reconsider this pairing and either defend it or suggest an alternative?

Return only:
1) Decision: DEFEND or CHANGE
2) A 3-5 sentence explanation
3) If CHANGE, provide one replacement client and 1 sentence why that is stronger fit
"""


def load_staff_client_data(path: Path = DATA_PATH) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Data file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Data file is empty: {path}")
    return text


def load_stage1_output(path: Path = STAGE1_OUTPUT_PATH) -> str:
    if not path.is_file():
        raise FileNotFoundError(
            f"Stage 1 output not found: {path}. Run --stage 1 first."
        )
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Stage 1 output is empty: {path}")
    return text


def build_stage1_prompt(staff_client_data: str) -> str:
    return f"{STAGE1_USER_PROMPT_PREFIX}\n\n{staff_client_data}\n"


def _extract_json_blob(text: str) -> str:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in model response.")
    return match.group(0)


def parse_assignment_response(raw: str) -> dict:
    blob = _extract_json_blob(raw)
    data = json.loads(blob)
    if "assignments" not in data or "summary" not in data:
        raise ValueError("Response missing required keys: assignments/summary.")
    if not isinstance(data["assignments"], list):
        raise ValueError("assignments must be a list.")
    return data


def validate_assignments(data: dict) -> list[str]:
    errors: list[str] = []
    assignments = data.get("assignments", [])
    if len(assignments) != len(EXPECTED_STAFF):
        errors.append(
            f"Need exactly {len(EXPECTED_STAFF)} assignment rows; got {len(assignments)}."
        )

    staff_seen = []
    clients_seen = []
    for i, row in enumerate(assignments, start=1):
        if not isinstance(row, dict):
            errors.append(f"Row {i} is not an object.")
            continue
        staff = str(row.get("staff_member", "")).strip()
        c1 = str(row.get("client_1", "")).strip()
        c2 = str(row.get("client_2", "")).strip()
        rationale = str(row.get("rationale", "")).strip()
        if not staff:
            errors.append(f"Row {i} missing staff_member.")
        if c1 == c2:
            errors.append(f"Row {i} has duplicate client assignments ({c1}).")
        if not rationale:
            errors.append(f"Row {i} missing rationale.")
        staff_seen.append(staff)
        clients_seen.extend([c1, c2])

    if sorted(staff_seen) != sorted(EXPECTED_STAFF):
        errors.append(
            "Staff list mismatch. Must use each staff exactly once: "
            + ", ".join(EXPECTED_STAFF)
        )
    if sorted(clients_seen) != sorted(EXPECTED_CLIENTS):
        errors.append(
            "Client coverage mismatch. Must use each client exactly once: "
            + ", ".join(EXPECTED_CLIENTS)
        )
    return errors


def render_markdown(data: dict) -> str:
    lines = [
        "## Assignment Table",
        "",
        "| Staff Member | Client 1 | Client 2 | Rationale |",
        "| --- | --- | --- | --- |",
    ]
    for row in data["assignments"]:
        lines.append(
            f"| {row['staff_member']} | {row['client_1']} | {row['client_2']} | {row['rationale']} |"
        )
    lines.extend(["", "## Summary", "", str(data["summary"]).strip()])
    return "\n".join(lines).strip() + "\n"


def build_fallback_assignment() -> dict:
    """Guaranteed-valid 6x2 assignment if the model cannot satisfy constraints."""
    return {
        "assignments": [
            {
                "staff_member": "Alex Chen",
                "client_1": "Client B",
                "client_2": "Client L",
                "rationale": "Strong fit on regulation, detail-heavy documentation, and methodical stakeholders.",
            },
            {
                "staff_member": "Brianna Okafor",
                "client_1": "Client A",
                "client_2": "Client H",
                "rationale": "Best fit for public/nonprofit contexts with heavy facilitation and stakeholder engagement.",
            },
            {
                "staff_member": "Carla Mendez",
                "client_1": "Client D",
                "client_2": "Client I",
                "rationale": "Healthcare + technical analytics alignment makes this a high-confidence pairing.",
            },
            {
                "staff_member": "Dana Park",
                "client_1": "Client F",
                "client_2": "Client J",
                "rationale": "Creative, research-friendly deliverables suit her level; Client J is a slightly weaker fit due to strategy depth.",
            },
            {
                "staff_member": "Elliot Vasquez",
                "client_1": "Client C",
                "client_2": "Client G",
                "rationale": "High-stakes org design and fast PE work match partner-level strategy experience and existing relationship.",
            },
            {
                "staff_member": "Fiona Marsh",
                "client_1": "Client E",
                "client_2": "Client K",
                "rationale": "Strong writing and trust-building communication support politically sensitive and skeptical stakeholders.",
            },
        ],
        "summary": (
            "Assignments prioritize domain fit first (regulatory/financial, healthcare/data, public-sector engagement), "
            "then communication style and project tempo. High-stakes and fast-moving work is concentrated with Elliot, "
            "while structured compliance/data workflows are allocated to Alex and Carla. Brianna takes the most "
            "stakeholder-heavy public/nonprofit projects. Dana receives creative but bounded scopes, with Client J flagged "
            "as a moderate stretch; Fiona covers relationship-sensitive and deliverable-heavy work."
        ),
    }


def query_ollama(system_prompt: str, user_prompt: str) -> str:
    load_dotenv()
    model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    api_key = os.getenv("OLLAMA_API_KEY")

    url = f"{base_url}/api/chat"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(url, json=body, headers=headers, timeout=(20, 360))
    response.raise_for_status()

    payload = response.json()
    message = payload.get("message") or {}
    content = str(message.get("content", "")).strip()
    if not content:
        raise RuntimeError(f"Ollama response missing content: {payload}")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="AI staff-client assignment activity.")
    parser.add_argument(
        "--stage",
        choices=["1", "2"],
        default="1",
        help="Run stage 1 initial assignment or stage 2 stress test.",
    )
    args = parser.parse_args()

    if args.stage == "2":
        print("Running Stage 2: stress-test selected pairing...\n")
        stage1_table = load_stage1_output()
        stage2_prompt = STAGE2_FOLLOWUP_PROMPT.format(stage1_table=stage1_table)
        stage2_result = query_ollama(SYSTEM_PROMPT, stage2_prompt)
        print("=== Stage 2 Output ===\n")
        print(stage2_result)
        print("\n======================")
        STAGE2_OUTPUT_PATH.write_text(stage2_result.strip() + "\n", encoding="utf-8")
        print(f"\nSaved Stage 2 output to: {STAGE2_OUTPUT_PATH}")
        return

    print("Running Stage 1: staff-client assignment...\n")
    data = load_staff_client_data()
    user_prompt = build_stage1_prompt(data)
    validation_notes = ""
    parsed = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"Attempt {attempt}/{MAX_ATTEMPTS}...", flush=True)
        raw = query_ollama(SYSTEM_PROMPT, user_prompt + validation_notes)
        try:
            candidate = parse_assignment_response(raw)
            errors = validate_assignments(candidate)
        except Exception as exc:
            errors = [f"Invalid format: {exc}"]

        if not errors:
            parsed = candidate
            break

        validation_notes = (
            "\n\nYour previous response did not satisfy constraints.\n"
            "Fix and return corrected JSON only.\n"
            "Validation errors:\n- " + "\n- ".join(errors) + "\n"
        )

    if parsed is None:
        print(
            "Model did not satisfy hard constraints after retries; using validated fallback assignment.",
            flush=True,
        )
        parsed = build_fallback_assignment()

    result_md = render_markdown(parsed)
    print("=== Stage 1 Output ===\n")
    print(result_md)
    print("======================")

    STAGE1_OUTPUT_PATH.write_text(result_md, encoding="utf-8")
    print(f"\nSaved Stage 1 output to: {STAGE1_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
