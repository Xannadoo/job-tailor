"""
Exposes date_facts.total_experience_from_doc() as a tool the critic or
fact-checker can call, rather than reasoning about total career length
itself.

Unlike gap_verifier.py, this tool makes no LLM call internally - the
computation is pure Python (interval merging in date_facts.py), so
correctness doesn't depend on model reliability at all. The model's
only job is deciding it needs this number and calling the tool; the
answer itself is guaranteed correct by construction. This is a purer
demonstration of the tool-use pattern than the gap verifier, where an
LLM still does the actual checking inside the tool.

Built directly in response to failure log entry 9: a model, given
correct individual role durations, still summed them into a career
length off by roughly a decade. The fix there was logged as
identified-not-fixed, pending this - giving the model a way to ask for
the correct total directly, rather than doing the arithmetic itself.
"""

from datetime import date

from src import date_facts


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_total_experience",
        "description": (
            "Get the applicant's total professional/academic experience, "
            "computed exactly from the career master document - use this "
            "any time a claim states or implies a total career length or "
            "years of experience (e.g. 'over the past seven years', "
            "'X years of experience'), instead of adding up individual "
            "role durations yourself. Overlapping roles (e.g. two "
            "activities running at the same time) are handled correctly "
            "here and will not be double-counted, which is easy to get "
            "wrong by hand."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}


def call_total_experience_tool(career_master_doc: str, today: date | None = None) -> dict:
    """
    Entry point for the agentic path. No arguments are needed from the
    model - the tool always computes against the real master document
    and today's actual date, both bound by the caller, not supplied by
    the model (which would reintroduce the exact "let the model guess
    today's date" problem this project already fixed once).
    """
    if today is None:
        today = date.today()
    return date_facts.total_experience_from_doc(career_master_doc, today)