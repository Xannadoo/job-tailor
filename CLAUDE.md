# CLAUDE.md

Context for Claude Code when working on this project.

## What this project is

A small proof-of-concept agentic pipeline: takes a job description and a
personal "career master document," and produces tailored CV/cover letter
content. Built deliberately small in scope — not the full job-search
automation suite, just the tailoring step.

## Stack and constraints

- LLM backend: qwen-coder:14b via Ollama, routed through a local LiteLLM
  proxy. No paid Anthropic API access — do not suggest calling
  api.anthropic.com directly or assume a Claude API key is available.
- Python. Keep dependencies minimal; this is a POC, not production
  infrastructure.
- Prompts live in `prompts/` as plain text files, not inline strings in
  code — keep this separation when adding new pipeline steps.

## File conventions

- `data/career_master_doc.md` is read-only source material. Never edit
  its contents programmatically or suggest changes to it from within
  the pipeline.
- `output/` is gitignored and holds generated, per-application drafts.
  Nothing in there should be treated as a source of truth.
- Pipeline stages are split by responsibility (extract requirements →
  match experience → draft → style critique). Prefer adding a new
  module under `src/` over growing an existing one when a step does a
  genuinely different job.

## Style rules for any generated CV/cover letter text

These apply to LLM-generated output, not to code:

- UK English spelling throughout (organise, whilst, behaviour).
- No em-dashes used for stylistic effect.
- No "it's not X, it's Y" constructions.
- No "passionate about," "thrive in," "leveraging my expertise."
- Full sentences, not fragment lists, in profile/cover letter prose.
- Specific and evidence-based over asserted ("ran X experiment" beats
  "strong analytical skills").

## Code style

- Plain, direct, commented where the *why* isn't obvious. No clever
  one-liners for their own sake.
- Prefer explicit over magic — this is a demo project someone might
  read end to end.
