from __future__ import annotations

import argparse
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
VENUE_DATA_PATH = SCRIPT_DIR / "venue_data.txt"
STAGE1_OUTPUT_PATH = SCRIPT_DIR / "stage1_output.md"
STAGE2_OUTPUT_PATH = SCRIPT_DIR / "stage2_output.md"

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "smollm2:1.7b"

SYSTEM_PROMPT = """You are a structured data extractor and decision analyst.
Your job is to extract key attributes from unstructured venue descriptions,
build a comparison table, and recommend the top 3 venues based on the client's priorities.

Always return:
1. A markdown table with columns: Venue, Capacity, Approx. Price/Night, Catering, Outdoor, Parking, Vibe (1 word)
2. A ranked shortlist of top 3 venues with 1-sentence justification each
3. One sentence noting any venues you had to exclude due to missing information

Be concise. Do not invent data that is not in the descriptions."""

STAGE1_PRIORITIES = """Here are the couple's priorities:
- Budget: under $8,000 for venue rental
- Guest count: ~120 people
- Vibe: romantic, not too corporate
- Must have outdoor ceremony option
- Catering must be in-house or on an approved vendor list
"""

STAGE2_PRIORITIES = """Here are the couple's priorities:
- Budget: flexible, up to $15,000
- Guest count: ~200 people
- Vibe: elegant, grand
- Outdoor is a nice-to-have but not required
- No catering constraint
"""


def load_venue_data(path: Path = VENUE_DATA_PATH) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Venue data file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Venue data file is empty: {path}")
    return text


def build_stage1_user_prompt(venue_data: str) -> str:
    return (
        f"{STAGE1_PRIORITIES}\n"
        "Here are descriptions of 16 venues. Please analyze and recommend.\n\n"
        f"{venue_data}\n"
    )


def build_stage2_user_prompt(venue_data: str) -> str:
    return (
        f"{STAGE2_PRIORITIES}\n"
        "Here are descriptions of 16 venues. Please analyze and recommend.\n\n"
        f"{venue_data}\n"
    )


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

    response = requests.post(url, json=body, headers=headers, timeout=(15, 300))
    response.raise_for_status()

    payload = response.json()
    message = payload.get("message") or {}
    content = message.get("content", "").strip()
    if not content:
        raise RuntimeError(f"Ollama response missing content: {payload}")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="Wedding venue decider (Stage 1 or Stage 2).")
    parser.add_argument(
        "--stage",
        choices=["1", "2"],
        default="1",
        help="Choose which activity stage priorities to run.",
    )
    args = parser.parse_args()

    venue_data = load_venue_data()
    if args.stage == "1":
        print("Running Stage 1: wedding venue AI decider...\n")
        user_prompt = build_stage1_user_prompt(venue_data)
        output_path = STAGE1_OUTPUT_PATH
        stage_label = "Stage 1"
    else:
        print("Running Stage 2: wedding venue AI decider...\n")
        user_prompt = build_stage2_user_prompt(venue_data)
        output_path = STAGE2_OUTPUT_PATH
        stage_label = "Stage 2"

    result = query_ollama(SYSTEM_PROMPT, user_prompt)

    print(f"=== {stage_label} Output ===\n")
    print(result)
    print("\n======================")

    output_path.write_text(result + "\n", encoding="utf-8")
    print(f"\nSaved {stage_label} output to: {output_path}")


if __name__ == "__main__":
    main()
