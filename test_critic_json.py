"""
Isolated test: can qwen2.5-coder:14b reliably return valid, parseable
JSON for the critic stage?

Deliberately not wired into pipeline.py yet. This script exists to
answer one question before any loop-driver code gets written: is
structured output viable at all on this model, or does the plain-text
+ parse-with-a-script bridge need to be used instead.

Run manually:
    python3 test_critic_json.py path/to/job_ad.txt path/to/draft.txt

Use --repeat N to call the model N times on the same input (default 3).
A single success or failure tells you little - JSON validity needs to
be observed across multiple calls.
"""

import argparse
import json

from src import pipeline, llm_client
from src.critic_types import CriticFlag


def run_critic(job_description: str, draft_profile: str) -> str:
    """Call the critic prompt and return the raw model response."""
    template = pipeline.load_prompt("critic.txt")
    prompt = template.format(
        job_description=job_description,
        draft_profile=draft_profile,
        today_date=pipeline.get_today().isoformat(),
    )
    return llm_client.complete(prompt)


def try_parse(raw_response: str) -> tuple[bool, str, list | None]:
    """
    Attempt to parse the model's raw response as the expected flag
    schema. Returns (success, message, parsed_flags_or_None).

    Tries a couple of common failure-recovery steps (stripping
    markdown code fences, since models often add them despite being
    told not to) before giving up - this mirrors what a real
    integration would need to tolerate.
    """
    text = raw_response.strip()

    # Common failure mode: wrapped in ```json ... ``` despite instructions.
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return False, f"JSON_DECODE_ERROR: {e}", None

    if not isinstance(data, list):
        return False, f"NOT_A_LIST: got {type(data).__name__}", None

    flags = []
    for i, item in enumerate(data):
        try:
            flag = CriticFlag.from_dict(item, round_number=1)
            flags.append(flag)
        except (KeyError, ValueError) as e:
            return False, f"SCHEMA_ERROR at index {i}: {e}", None

    return True, f"OK: {len(flags)} flag(s) parsed successfully", flags


def main():
    parser = argparse.ArgumentParser(
        description="Test whether the model returns valid JSON for the critic stage."
    )
    parser.add_argument("job_ad_file", help="Path to job ad text file")
    parser.add_argument("draft_file", help="Path to draft profile text file")
    parser.add_argument(
        "--repeat", type=int, default=3,
        help="Number of times to call the model (default 3)"
    )
    args = parser.parse_args()

    with open(args.job_ad_file, "r", encoding="utf-8") as f:
        job_description = f.read()
    with open(args.draft_file, "r", encoding="utf-8") as f:
        draft_profile = f.read()

    successes = 0
    failures = []

    for run_num in range(1, args.repeat + 1):
        print(f"\n{'=' * 60}")
        print(f"RUN {run_num}/{args.repeat}")
        print("=" * 60)

        raw = run_critic(job_description, draft_profile)
        print("--- RAW MODEL OUTPUT ---")
        print(raw)
        print("--- PARSE RESULT ---")

        success, message, flags = try_parse(raw)
        print(message)

        if success:
            successes += 1
            for flag in flags:
                print(f"  [{flag.severity.value}] {flag.category.value}: {flag.quoted_text!r}")
                print(f"    requirement: {flag.job_ad_requirement}")
                print(f"    suggested:   {flag.suggested_direction}")
        else:
            failures.append((run_num, message))

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {successes}/{args.repeat} runs produced valid, parseable JSON")
    if failures:
        print("Failures:")
        for run_num, msg in failures:
            print(f"  Run {run_num}: {msg}")
    print("=" * 60)


if __name__ == "__main__":
    main()