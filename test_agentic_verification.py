"""
End-to-end test of the completed agentic round trip: model decides
whether to call verify_genuine_gap, the tool actually runs against
the real career master document, the result goes back to the model,
and we see its final answer.

Runs two cases:
1. A genuine gap (SAS/cloud platforms - confirmed absent from the
   master doc). The job requirement is deliberately a bundle (SAS, R,
   Python, Matlab, Hadoop, Hive, AWS, Azure, GCP all together) while
   the quoted text only discloses lacking SAS/cloud specifically -
   this is the exact shape that previously caused a false
   ACTUALLY_SUPPORTED (found real evidence for Python/R elsewhere in
   the bundle, wrongly applied it to the SAS/cloud claim). Expect
   verdict CONFIRMED_GAP, scoped_items mentioning SAS/cloud
   specifically, not the whole bundle.
2. A case that looks like a gap on the surface but has adjacent
   evidence in the master doc (random forests never named directly,
   but covered via ML coursework). Expect verdict ACTUALLY_SUPPORTED.

Usage: python3 test_agentic_verification.py
"""

from src import pipeline
from src.gap_verifier import run_agentic_verification


def run_case(label: str, quoted_text: str, job_ad_requirement: str, career_master_doc: str):
    print(f"\n{'=' * 60}")
    print(f"CASE: {label}")
    print("=" * 60)
    print(f"Quoted text: {quoted_text!r}")
    print(f"Job requirement: {job_ad_requirement!r}")

    result = run_agentic_verification(quoted_text, job_ad_requirement, career_master_doc)

    print(f"\nModel called a tool: {bool(result['tool_calls_made'])}")
    for call in result["tool_calls_made"]:
        print(f"  Tool: {call['name']}")
        print(f"  Arguments sent: {call['arguments']}")
        print(f"  Result: {call['result']}")
    print(f"\nFinal verdict: {result['verdict']}")
    print(f"Scoped items (what it actually checked): {result['scoped_items']}")
    print(f"Final model content: {result['final_content']}")
    print(f"Hit max rounds: {result['hit_max_rounds']}")


def main():
    career_master_doc = pipeline.load_career_master_doc()

    run_case(
        label="Genuine gap - SAS/cloud platforms, requirement is a bundle "
        "(regression test for the compound-requirement bug)",
        quoted_text="I have not used SAS or cloud platforms such as AWS, Azure, or GCP",
        job_ad_requirement=(
            "statistical programming languages (SAS, R, Python, Matlab), "
            "big data tools and platforms (Hadoop, Hive, etc.) and cloud "
            "platforms (AWS, Azure, GCP)"
        ),
        career_master_doc=career_master_doc,
    )

    run_case(
        label="Looks like a gap but has adjacent evidence - random forests",
        quoted_text="my machine learning coursework and teaching experience",
        job_ad_requirement="Knowledge of Artificial Intelligence modeling techniques (logit, GLM, time series, random forests, clustering, XGBoost)",
        career_master_doc=career_master_doc,
    )


if __name__ == "__main__":
    main()