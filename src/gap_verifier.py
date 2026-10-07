"""
Verifies GENUINE_GAP flags raised by the critic.

Why this exists: testing the critic in isolation found the
GENUINE_GAP/MISSING_EVIDENCE boundary is unstable across identical
reruns of the same input - the same underlying issue got classified
as GENUINE_GAP in some runs and MISSING_EVIDENCE in others. This
matters because the loop control treats the two completely
differently: MISSING_EVIDENCE can be revised, GENUINE_GAP forces an
honest acknowledgement and can never get a suggested_direction. A
coin-flip on the category decides whether the loop tries to help or
gives up, independent of the actual evidence.

This module re-checks any GENUINE_GAP flag against the master doc
before the loop treats it as settled, using the same direct-or-
adjacent evidentiary standard as the fact-checker's hard-skill claims.
If real evidence turns up that the critic missed, the flag is
downgraded rather than accepted as unaddressable.

Fix history: the first end-to-end test of this module found a second
bug, distinct from the instability above - when a job_ad_requirement
bundles several distinct tools/skills together (e.g. "SAS, R, Python,
Matlab"), and the quoted draft text is an honest disclosure about only
some of them (e.g. "I have not used SAS or cloud platforms"), the
verifier was checking whether ANY part of the bundle had support
rather than the specific part being disclosed as absent - finding
real evidence for Python/R and wrongly concluding the whole bundle,
including SAS specifically, was supported. verify_gap.txt now
requires an explicit scoping step first (surfaced as scoped_items in
the response) so the check runs against the specific item(s) the
quoted text is actually about, not the bundle as a whole. Not yet
re-tested end to end after this fix - the fix should be re-verified
once the full critic loop is built and running against real,
naturally-bundled job ad requirements, not just constructed test
cases.

Exposed three ways:
- verify_genuine_gap(): the check itself, called directly as a
  deterministic post-processing gate, independent of whether the
  model backend supports tool calling at all. This is the safe
  fallback and works regardless of the agentic path below.
- TOOL_SCHEMA + call_gap_verifier_tool(): the same check, wrapped for
  a model to invoke as a tool mid-reasoning. Confirmed working via
  Ollama cloud models through LiteLLM, but only when the model is
  registered with the ollama_chat/ provider prefix, not ollama/ - see
  llm_client.complete_with_tools() for why.
- run_agentic_verification(): the complete round trip using
  llm_client.run_agentic_loop() - gives the model the tool and lets
  it decide whether and how to call it, executes the call, and
  returns the model's final answer after seeing the result. This is
  the actual agentic path end to end, not just the request half.
"""

import json

from src import llm_client, pipeline


# OpenAI-style tool schema, usable if/when the backend supports real
# function-calling through LiteLLM. Kept here rather than inline in
# the critic loop driver so the schema and the function it describes
# stay next to each other.
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "verify_genuine_gap",
        "description": (
            "Check whether a job requirement flagged as a GENUINE_GAP "
            "(something the applicant's background has no basis for at "
            "all) is actually unsupported, by searching the career "
            "master document for direct or adjacent evidence. If the "
            "requirement bundles multiple tools/skills together, this "
            "checks only the specific item(s) the quoted draft text is "
            "actually about, not the bundle as a whole. Call this "
            "before finalising any GENUINE_GAP flag."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "quoted_text": {
                    "type": "string",
                    "description": "The literal text from the draft this flag is about.",
                },
                "job_ad_requirement": {
                    "type": "string",
                    "description": "The specific job requirement this flag claims is unaddressable.",
                },
            },
            "required": ["quoted_text", "job_ad_requirement"],
        },
    },
}


def verify_genuine_gap(
    quoted_text: str, job_ad_requirement: str, career_master_doc: str
) -> dict:
    """
    The actual check. Runs a narrow verification prompt and returns a
    dict: {"verdict": "CONFIRMED_GAP" | "ACTUALLY_SUPPORTED",
    "basis_found": str | None, "scoped_items": str | None}.

    scoped_items records what the model identified as the specific
    thing it actually checked, distinct from the full (possibly
    bundled) job_ad_requirement - this is worth logging even when the
    verdict looks right, since it's the visible evidence that the
    scoping step actually happened rather than the model silently
    matching against the whole bundle again.

    Called directly (deterministic post-processing gate) or via
    call_gap_verifier_tool (agentic path). Both paths run this same
    function, so the verification logic is identical either way - only
    who decides to call it, and when, differs.
    """
    template = pipeline.load_prompt("verify_gap.txt")
    prompt = template.format(
        career_master_doc=career_master_doc,
        job_ad_requirement=job_ad_requirement,
        quoted_text=quoted_text,
    )
    raw = llm_client.complete(prompt)

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Fail closed: if verification itself is unparseable, don't
        # silently trust the critic's original GENUINE_GAP claim, but
        # don't crash the loop either - surface it as unverifiable so
        # the calling code can decide (e.g. treat as still-open rather
        # than either confirmed or downgraded).
        return {
            "verdict": "UNVERIFIABLE",
            "basis_found": None,
            "scoped_items": None,
            "raw_response": raw,
        }

    if result.get("verdict") not in ("CONFIRMED_GAP", "ACTUALLY_SUPPORTED"):
        return {
            "verdict": "UNVERIFIABLE",
            "basis_found": None,
            "scoped_items": None,
            "raw_response": raw,
        }

    result.setdefault("scoped_items", None)
    return result


def call_gap_verifier_tool(arguments: dict, career_master_doc: str) -> dict:
    """
    Entry point for the agentic path: called when a model produces a
    tool_call matching TOOL_SCHEMA's name and arguments. Unpacks the
    arguments the model provided and runs the same check.
    """
    return verify_genuine_gap(
        quoted_text=arguments["quoted_text"],
        job_ad_requirement=arguments["job_ad_requirement"],
        career_master_doc=career_master_doc,
    )


def run_agentic_verification(
    quoted_text: str, job_ad_requirement: str, career_master_doc: str
) -> dict:
    """
    The complete agentic round trip: present the model with the
    scenario and the verify_genuine_gap tool, let it decide to call
    the tool (it may not - that's a legitimate outcome worth noticing,
    not an error), actually execute the call against the real master
    doc, feed the result back, and return the model's final answer.

    Returns a dict with the loop's raw result (final_content,
    tool_calls_made, hit_max_rounds from llm_client.run_agentic_loop)
    plus convenience "verdict" and "scoped_items" fields pulled from
    the tool call's result if one was made, so callers that only care
    about the outcome don't have to dig through tool_calls_made
    themselves.

    This is one narrow, single-purpose use of tool calling - not a
    general-purpose agent. Kept deliberately small: one tool, one
    possible call, a tight max_tool_rounds.
    """
    prompt = (
        "A recruiter-critic reviewing a CV draft against a job advert "
        "flagged the following as a GENUINE_GAP - meaning it believes "
        "the applicant's background has no basis at all for this "
        "requirement, direct or indirect. Note the job requirement may "
        "bundle several distinct things together - the quoted text is "
        "usually only about a specific part of that bundle.\n\n"
        f"Job requirement: {job_ad_requirement}\n"
        f"Quoted draft text the flag is about: {quoted_text}\n\n"
        "Before this flag is accepted as a genuine, unaddressable gap, "
        "verify it against the applicant's actual career master "
        "document using the verify_genuine_gap tool."
    )

    def tool_executor(name: str, arguments: dict) -> dict:
        if name != "verify_genuine_gap":
            return {"error": f"unknown tool: {name}"}
        return call_gap_verifier_tool(arguments, career_master_doc)

    result = llm_client.run_agentic_loop(
        prompt=prompt,
        tools=[TOOL_SCHEMA],
        tool_executor=tool_executor,
    )

    verdict = None
    scoped_items = None
    if result["tool_calls_made"]:
        tool_result = result["tool_calls_made"][0]["result"]
        verdict = tool_result.get("verdict")
        scoped_items = tool_result.get("scoped_items")

    return {**result, "verdict": verdict, "scoped_items": scoped_items}