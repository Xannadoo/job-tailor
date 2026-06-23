"""
Pipeline: fit analysis, draft profile paragraph, and fact-check.

Three LLM calls in sequence, each backed by its own prompt file under
prompts/. No LaTeX output yet, no cover letter generation yet, no
multi-step agent loop with branching or retries - each stage runs
once and passes its output to the next.
"""

import datetime
import os

import config
from src import date_facts, llm_client


def get_today() -> datetime.date:
    """Return today's date as a date object."""
    return datetime.date.today()


def build_date_facts_for_prompt(career_master_doc: str) -> str:
    """
    Pre-compute date status and durations for every parseable date
    range in the master document, so prompts can be given the answers
    directly rather than asking the model to do date arithmetic.

    This replaced an earlier approach of just passing today's date
    into the prompt and instructing the model to do the subtraction
    itself - that worked for simple tense judgements (finished vs
    ongoing) but the model remained unreliable at actual duration
    arithmetic (e.g. miscalculating Jan 2023-Jun 2025 as four years).
    """
    return date_facts.build_date_facts_block(career_master_doc, get_today())


def load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts/ directory."""
    path = os.path.join(config.PROMPTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_career_master_doc() -> str:
    """Load the applicant's career master document. Read-only input."""
    with open(config.CAREER_MASTER_DOC_PATH, "r", encoding="utf-8") as f:
        return f.read()


def run_fit_analysis(job_description: str, career_master_doc: str) -> str:
    """
    Stage 1: ask the model to map job requirements against the career
    master document, surface matches and gaps, and recommend what to
    lead with. This output feeds into the profile drafting stage.
    """
    template = load_prompt("extract_requirements.txt")
    prompt = template.format(
        job_description=job_description,
        career_master_doc=career_master_doc,
        today_date=get_today().isoformat(),
        date_facts=build_date_facts_for_prompt(career_master_doc),
    )
    return llm_client.complete(prompt)


def run_draft_profile(
    job_description: str, career_master_doc: str, fit_analysis: str
) -> str:
    """
    Stage 2: draft the CV profile paragraph, using the fit analysis
    to decide what to foreground, with the style rules enforced via
    the prompt itself.
    """
    template = load_prompt("draft_profile.txt")
    prompt = template.format(
        job_description=job_description,
        career_master_doc=career_master_doc,
        fit_analysis=fit_analysis,
    )
    return llm_client.complete(prompt)


def run_fact_check(career_master_doc: str, draft_profile: str) -> str:
    """
    Stage 3: check every factual claim in the draft profile against
    the career master document, independently of the drafting stage.

    Deliberately narrow in scope - this checks accuracy only, not
    style or quality, and deliberately does not see the job
    description. The job description is what tends to leak false
    claims into drafts (the model echoes the job ad's wishlist back
    as the applicant's own experience), so keeping it out of the
    fact-checker's context means the checker has no route to the
    same error: it can only compare the draft against what the
    master document actually says.
    """
    template = load_prompt("fact_check.txt")
    prompt = template.format(
        career_master_doc=career_master_doc,
        draft_profile=draft_profile,
        today_date=get_today().isoformat(),
        date_facts=build_date_facts_for_prompt(career_master_doc),
    )
    return llm_client.complete(prompt)


def run(job_description: str) -> dict:
    """
    Run the full pipeline for a single job description and return
    all intermediate and final outputs, so the caller can inspect or
    save the fit analysis, profile draft, and fact-check separately.
    """
    career_master_doc = load_career_master_doc()

    fit_analysis = run_fit_analysis(job_description, career_master_doc)
    profile_draft = run_draft_profile(
        job_description, career_master_doc, fit_analysis
    )
    fact_check = run_fact_check(career_master_doc, profile_draft)

    return {
        "fit_analysis": fit_analysis,
        "profile_draft": profile_draft,
        "fact_check": fact_check,
    }
