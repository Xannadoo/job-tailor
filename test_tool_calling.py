"""
Isolated test: does the currently configured backend (see config.py /
litellm_config.yaml) actually support OpenAI-style tool calling
through LiteLLM?

Run this before wiring gap_verifier's agentic path into anything. If
the model never returns a populated tool_calls list here, the answer
is no for this backend, and gap_verifier.verify_genuine_gap() should
be called directly (deterministic path) instead of relying on the
model to decide to invoke the tool itself.

Usage: python3 test_tool_calling.py
"""

from src import llm_client
from src.gap_verifier import TOOL_SCHEMA


def main():
    prompt = (
        "A recruiter-critic flagged this as a GENUINE_GAP: the "
        "requirement 'Strong Python skills (pandas, scikit-learn, "
        "XGBoost)' is not addressed by the quoted draft text "
        "'applying one-proportion z-tests with Bonferroni correction "
        "to validate the results'. Use the verify_genuine_gap tool to "
        "check this before accepting it as a confirmed gap."
    )

    message = llm_client.complete_with_tools(prompt, tools=[TOOL_SCHEMA])

    print("--- response.content ---")
    print(message.content)
    print()
    print("--- response.tool_calls ---")
    print(message.tool_calls)

    if message.tool_calls:
        print()
        print("TOOL CALLING WORKS on this backend.")
        for call in message.tool_calls:
            print(f"  Model wants to call: {call.function.name}")
            print(f"  With arguments: {call.function.arguments}")
    else:
        print()
        print("TOOL CALLING DID NOT FIRE on this backend.")
        print("Use gap_verifier.verify_genuine_gap() directly (deterministic")
        print("path) instead of relying on the model to invoke the tool.")


if __name__ == "__main__":
    main()