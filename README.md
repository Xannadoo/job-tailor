# job-tailor

A small proof-of-concept pipeline that takes a job description and a
personal "career master document," and generates a tailored fit
analysis and draft CV profile paragraph.

Built deliberately small: this is the tailoring step on its own, not
a full job-search automation suite. Runs entirely against a local
model via Ollama and LiteLLM, no paid API required.

## Status

Step 1 of the project: a two-stage pipeline (fit analysis, then
profile drafting). No LaTeX output yet, no cover letter generation
yet, no self-critique/style-checking pass yet. See "Roadmap" below.

## How it works

1. You provide a job description as a text file.
2. The pipeline loads `data/career_master_doc.md` (your full
   background, kept separate from any single application).
3. Stage 1 (`extract_requirements.txt` prompt): the model identifies
   the key requirements in the job description and matches them
   against the master document, flagging genuine gaps rather than
   papering over them.
4. Stage 2 (`draft_profile.txt` prompt): using the fit analysis, the
   model drafts a CV profile paragraph, following a fixed style guide
   (UK English, no em-dashes, no corporate buzzwords, specific over
   vague).
5. Both outputs are printed and saved to `output/`.

## Setup

Requires a running LiteLLM proxy in front of an Ollama model
(qwen-coder:14b by default, but anything registered in your proxy
config works - just set `JOB_TAILOR_MODEL`).

```bash
pip install -r requirements.txt
cp .env.example .env   # only needed if your setup differs from the defaults
```

## Usage

```bash
python main.py path/to/job_description.txt
```

Output is printed to the terminal and saved to `output/<name>_<timestamp>.md`.

## Project structure

```
job-tailor/
├── CLAUDE.md                 # context for Claude Code when developing this repo
├── config.py                 # LiteLLM endpoint, model name, paths
├── main.py                   # CLI entry point
├── data/
│   └── career_master_doc.md  # read-only source material
├── src/
│   ├── llm_client.py          # wraps calls to the LiteLLM proxy
│   └── pipeline.py            # orchestrates the pipeline stages
├── prompts/
│   ├── extract_requirements.txt
│   └── draft_profile.txt
├── output/                    # generated drafts (gitignored)
└── tests/
```

## Roadmap

Each of these is a deliberate next step, not all needed for the
pipeline to be useful as-is:

- Cover letter drafting stage, following the same pattern as the
  profile stage
- Style-critique pass: a separate LLM call that checks generated text
  against the style rules and flags/fixes violations, rather than
  relying on the drafting prompt alone to get it right first time
- LaTeX integration: slot generated text into the existing modular
  `.tex` section files rather than just producing plain text
- Basic tests covering prompt loading and pipeline wiring (mocking
  the LLM call, not testing model output quality)

## Why this exists

A demo project showing a small, well-scoped agentic pipeline running
entirely on a free local model stack, rather than a large automation
project that's hard to reason about or demo end to end.


### Failure log

1. **Context window too small.** The model never saw the job advert — it returned a fit analysis of the master doc against itself, inventing section headings copied from the master doc's own style guide.
   - Solution: increase `num_ctx` in `litellm_config.yaml`. The master doc alone is ~12-15k tokens; the Ollama default (2048-4096) silently truncated it.

2. **Fabricated matches.** Once context was fixed, the model echoed tools and techniques from the job ad's wishlist (XGBoost, Hadoop, cloud platforms) back as if they were the applicant's own experience, despite none of them appearing in the master doc. These fabrications then propagated into the drafted profile, producing plausible-sounding but false claims. Funnily enough a similar failure to my thesis finding: the model acted on a signal (the job ad's requirements) without basing its output on the source it was supposed to be reasoning from.
   - Solution: rewrote `extract_requirements.txt` with explicit instructions not to treat job-ad terminology as evidence of the applicant's experience unless the master doc states it directly.

3. **Tense/timeline confusion.** Independently of the above, the model stated "the applicant is currently in their MSc program but will graduate by 2025" despite the master doc stating the MSc was completed in September 2025. This wasn't contamination from the job ad's "recent graduates" phrasing being echoed as a fact — it was a failure to check the date against today's date and do the timeline arithmetic.
   - Solution: added explicit date-checking instructions to `extract_requirements.txt`.

4. **Fact-checker negation blindness.** Once a dedicated fact-check stage was added, it misclassified an honest disclosure ("despite not having experience with SAS or cloud platforms...") as an UNSUPPORTED fabrication, apparently reading "X lacks Y" as "claims to have Y." Its "corrected" output then deleted the gap-disclosure entirely — the one sentence doing real honesty work in the draft.
   - Solution: added explicit negation-handling instructions to `fact_check.txt`, plus a requirement to quote the literal claim before classifying it, to stop the checker's stated reasoning drifting from the actual text it's checking.

   Design note: the fact-checker is deliberately not shown the job description, only the master doc and the draft. This is structural, not just a prompt instruction. It removes the contaminating signal that caused failure #2, rather than just asking the model not to be fooled by it.