"""
End-to-end test of the completed agentic round trip: model decides
whether to call verify_genuine_gap, the tool actually runs against
the real career master document, the result goes back to the model,
and we see its final answer.

Runs two cases on purpose:
1. A genuine gap (SAS/cloud platforms - confirmed absent from the
   master doc in earlier testing) - expect verdict CONFIRMED_GAP.
2. A case that looks like a gap on the surface but has adjacent
   evidence in the master doc (e.g. random forests never named
   directly, but covered via ML coursework/TA'ing/oral exam topic per
   the README's entry 7 discussion) - expect verdict
   ACTUALLY_SUPPORTED, i.e. the verifier should catch the critic
   being wrong.

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
    print(f"Final model content: {result['final_content']}")
    print(f"Hit max rounds: {result['hit_max_rounds']}")


def main():
    career_master_doc = pipeline.load_career_master_doc()

    run_case(
        label="Genuine gap - SAS/cloud platforms",
        quoted_text="I have not used SAS or cloud platforms such as AWS, Azure, or GCP",
        job_ad_requirement="statistical programming languages (SAS, R, Python, Matlab), big data tools and platforms (Hadoop, Hive, etc.) and cloud platforms (AWS, Azure, GCP)",
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