"""
job-tailor CLI entry point.

Usage:
    python main.py path/to/job_description.txt

Reads a job description from a file, runs the pipeline (fit analysis,
draft profile, fact-check) against the career master document, prints
all three outputs to the terminal, and saves them to output/ named
after the input file.
"""

import argparse
import datetime
import os
import sys

import config
from src import pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Generate a fit analysis and draft CV profile for a job description."
    )
    parser.add_argument(
        "job_description_file",
        help="Path to a text file containing the job description.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.job_description_file):
        print(f"Error: file not found: {args.job_description_file}", file=sys.stderr)
        sys.exit(1)

    with open(args.job_description_file, "r", encoding="utf-8") as f:
        job_description = f.read()

    print("Running fit analysis, drafting profile, and fact-checking...\n")

    try:
        result = pipeline.run(job_description)
    except Exception as e:
        print(f"Error: pipeline failed - {e}", file=sys.stderr)
        print(
            "Check that the LiteLLM proxy is running and reachable at "
            f"{config.LITELLM_BASE_URL}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("=" * 60)
    print("FIT ANALYSIS")
    print("=" * 60)
    print(result["fit_analysis"])
    print()
    print("=" * 60)
    print("DRAFT PROFILE")
    print("=" * 60)
    print(result["profile_draft"])
    print()
    print("=" * 60)
    print("FACT CHECK")
    print("=" * 60)
    print(result["fact_check"])

    # Save to output/, named after the input file and timestamped so
    # repeated runs against the same job description don't overwrite
    # each other while iterating on prompts.
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(args.job_description_file))[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(config.OUTPUT_DIR, f"{base_name}_{timestamp}.md")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Fit analysis\n\n")
        f.write(result["fit_analysis"])
        f.write("\n\n# Draft profile\n\n")
        f.write(result["profile_draft"])
        f.write("\n\n# Fact check\n\n")
        f.write(result["fact_check"])
        f.write("\n")

    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
