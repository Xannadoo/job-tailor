# job-tailor

A small proof-of-concept pipeline that takes a job description and a
personal "career master document," and generates a tailored fit
analysis and draft CV profile paragraph.

Built deliberately small: this is the tailoring step on its own, not
a full job-search automation suite. Runs entirely against a local
model via Ollama and LiteLLM, no paid API required.

## Status

Three-stage pipeline working: fit analysis, draft CV profile, and an
independent fact-check pass that catches fabricated claims the
drafting stage introduces. Date and duration handling has been moved
out of the LLM entirely and into deterministic code
(`src/date_facts.py`), after repeated failures trying to get this
right via prompting alone.

Next planned step is an adversarial critic/fact-checker loop to make
the pipeline genuinely agentic rather than a fixed sequence of calls.
No LaTeX output yet, no cover letter generation yet, no style-critique
pass yet. See "Roadmap" below for the full plan and reasoning.

## How it works

1. You provide a job description as a text file.
2. The pipeline loads `data/career_master_doc.md` (your full
   background, kept separate from any single application) and
   pre-computes date/duration facts for every role, degree, and
   project in it (`src/date_facts.py`) - whether each is finished or
   ongoing, and how long it lasted, calculated in code rather than
   left to the model to work out.
3. Stage 1 (`extract_requirements.txt` prompt): the model identifies
   the key requirements in the job description and matches them
   against the master document, flagging genuine gaps rather than
   stretching something to fit, and using the pre-computed date facts
   for anything involving timing or duration.
4. Stage 2 (`draft_profile.txt` prompt): using the fit analysis, the
   model drafts a CV profile paragraph, following a fixed style guide
   (UK English, no em-dashes, no corporate buzzwords, specific over
   vague).
5. Stage 3 (`fact_check.txt` prompt): an independent pass checks every
   factual claim in the draft against the master document. Crucially,
   this stage never sees the job description - only the master doc and
   the draft - so it can't inherit the same fabrication risk that
   caused the drafting stage to echo job-ad terminology back as if it
   were the applicant's own experience.
6. All three outputs are printed and saved to `output/`.

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
├── litellm_config.yaml       # LiteLLM proxy config (points at Ollama)
├── main.py                   # CLI entry point
├── data/
│   └── career_master_doc.md  # read-only source material
├── src/
│   ├── llm_client.py          # wraps calls to the LiteLLM proxy
│   ├── date_facts.py          # deterministic date/duration computation
│   └── pipeline.py            # orchestrates the pipeline stages
├── prompts/
│   ├── extract_requirements.txt
│   ├── draft_profile.txt
│   └── fact_check.txt
├── output/                    # generated drafts (gitignored)
└── tests/
    └── test_date_facts.py     # tests for the deterministic date logic
```

## Failure log

Documented in build order. Each entry is a real bug hit while
building this pipeline, not a hypothetical - kept because the bugs
themselves are part of what this project demonstrates, particularly
where they echo patterns from LLM evaluation research more generally.

1. **Context window too small.** The model never saw the job advert -
   it returned a fit analysis of the master doc against itself,
   inventing section headings copied from the master doc's own style
   guide section.
   - Solution: increase `num_ctx` in `litellm_config.yaml`. The master
     doc alone is roughly 12-15k tokens; Ollama's default (2048-4096)
     silently truncated it, along with most of the actual prompt.

2. **Fabricated matches.** Once context was fixed, the model echoed
   tools and techniques from the job ad's wishlist (XGBoost, Hadoop,
   cloud platforms) back as if they were the applicant's own
   experience, despite none of them appearing in the master doc. These
   fabrications then propagated into the drafted profile, producing
   plausible-sounding but false claims - structurally similar to the
   thesis finding: the model acted on a signal (the job ad's
   requirements) without anchoring its output to the source it was
   meant to be reasoning from.
   - Solution: rewrote `extract_requirements.txt` with explicit
     instructions not to treat job-ad terminology as evidence of the
     applicant's experience unless the master doc states it directly.

3. **Tense/timeline confusion.** The model stated "the applicant is
   currently in their MSc program but will graduate by 2025" despite
   the master doc stating the MSc was completed in September 2025.
   This wasn't contamination from the job ad's "recent graduates"
   phrasing being echoed as fact - it was a failure to check the
   master doc's own dates against today's date.
   - First attempted solution: added explicit date-checking
     instructions to `extract_requirements.txt` and `fact_check.txt`,
     plus today's actual date injected into the prompt so the model
     didn't have to infer it.
   - This worked for simple finished-vs-ongoing tense judgements, but
     see entry 5 - the model remained unreliable at the arithmetic
     this approach still asked it to do.

4. **Fact-checker negation blindness.** Once a dedicated fact-check
   stage was added, it misclassified an honest disclosure ("despite
   not having experience with SAS or cloud platforms...") as an
   UNSUPPORTED fabrication, reading "X lacks Y" as "claims to have Y."
   Its "corrected" output then deleted the gap-disclosure entirely -
   the one sentence doing real honesty work in the draft.
   - Solution: added explicit negation-handling instructions to
     `fact_check.txt`, a `HONEST DISCLOSURE` classification that can
     never be flagged as unsupported or corrected away, and a
     requirement to quote the literal claim before classifying it, so
     the checker's stated reasoning couldn't drift from the actual
     text being checked.

5. **Duration arithmetic errors, and an overcorrection.** Even with
   tense-checking working, the model calculated a Jan 2023 - Jun 2025
   TA role as "four years" (actually ~2.5). Asking it to "write out
   the subtraction explicitly" as an extra instruction did not
   reliably fix this. Worse, fixing the tense bug too aggressively
   caused a new failure: the fact-checker flagged "I recently
   completed my MSc" - a true, past-tense statement - as INCORRECT,
   apparently pattern-matching "mentions MSc + date check required" to
   "flag it" without checking that "recently completed" and "currently
   completing" are different claims.
   - Solution: stopped asking the LLM to perform date arithmetic at
     all. Built `src/date_facts.py`, which parses every date range in
     the master doc with regex and computes finished/ongoing status
     and exact durations in Python. The pre-computed facts are
     injected into both prompts as given answers; the model's job
     became "use these facts," not "calculate them." Added
     `tests/test_date_facts.py` to cover this with actual unit tests,
     since date arithmetic has a single objectively correct answer
     and is properly testable in a way that LLM judgement calls are
     not. Also flagged year-only date ranges (e.g. "2023-2025" with no
     month) as approximate in the computed output, rather than
     presenting a falsely precise duration calculated from defaulted
     month boundaries.

6. **Narrow fact used to license a broader claim.** The draft stated
   "I am fluent in Danish, having passed PD3 in 2024." The fact-checker
   marked this SUPPORTED, citing only that PD3 was passed in 2024. But
   the master document itself describes Danish as "conversational,"
   notes it's "a particularly difficult language" for the applicant,
   and that her own children say her accent "remains a work in
   progress." Passing an exam is real and checkable; "fluent" is a
   stronger, different claim that the source material directly
   contradicts. The checker treated a true narrow fact as automatic
   licence for a broader adjective sitting on top of it, without
   checking whether the broader claim was itself supported.
   - Status: identified, not yet fixed. Likely fix: instruct the
     checker to identify the strongest specific claim embedded in a
     sentence (here, the descriptor "fluent," not the fact "passed
     PD3") and check that specific word/claim against the source,
     rather than checking the sentence's most easily-verified fragment
     and treating the rest as carried along by it.

7. **One evidentiary standard applied to two different claim types.**
   In the same draft, "I have demonstrated a get-up-and-go attitude,
   maturity, responsibility, and a strong work ethic" was marked
   UNSUPPORTED, on the grounds that the master document doesn't state
   this directly. But it's a reasonable synthesis of a real pattern in
   the document - running a cash office rollout unsupervised,
   advocating for a team against unreasonable demands, sustained
   compliance-handling roles - not a fabrication invented from
   nothing. The checker applied the same literal-quote standard here
   that correctly caught entries 2 and the XGBoost/Monte Carlo claims
   in this same run, where that standard was the right one.
   - The actual distinction: hard-skill/technical claims need a
     traceable basis, which can be direct (named explicitly) or
     adjacent-and-explainable (covered by something named closely
     enough to speak to it competently - e.g. random forests were
     never named, but ML coursework and TA'ing the ML course, plus
     having presented on random forests at an oral exam, is a real,
     checkable basis). They fail by having no basis at all, direct or
     adjacent. Soft-skill/character claims are different in kind -
     there is rarely a literal sentence to match against in the first
     place, so the question isn't "is this written down" but "is this
     a reasonable reading of the pattern of evidence." They fail by
     overreach (a synthesis no reasonable reader would draw), not by
     absence of a quote.
   - Status: fixed and confirmed working across two subsequent runs.
     `fact_check.txt` now explicitly distinguishes the two claim types
     and applies a different standard to each, with the output format
     also noting which standard was applied to each claim, for
     auditability. Both runs correctly applied the character-pattern
     standard to genuinely soft claims (e.g. "finding what doesn't add
     up," "meeting people where they are") without that looser
     standard leaking into hard-skill claims, which were still held to
     the stricter direct-or-adjacent-basis test. Confirmed generalising
     beyond the single case it was written against, not just fixing
     that one instance.

**Pattern across entries 2-5:** every one of these is a case of the
model producing fluent, confident, wrong output rather than visibly
failing - the harder failure mode to catch, and the more interesting
one. Entries 1 and 5 in particular show the same fix shape: rather
than writing yet another prompt instruction asking the model to try
harder at something it had already failed at twice, the more durable
fix was removing the task from the model entirely and doing it
deterministically in code. Worth treating "should this be a prompt
instruction or a function" as a real, recurring design question for
this project rather than a one-off lesson.

**Entries 6-7 are a different category from 1-5.** The earlier bugs
were about arithmetic and literal text-matching the model should have
gotten right by its own stated standard. Entries 6 and 7 are about
the standard itself being underspecified - the fact-checker has been
asked to apply one undifferentiated bar to claims that genuinely need
different bars depending on what kind of claim they are. This isn't
solvable by code the way date arithmetic was; "is this a reasonable
character synthesis" is a judgement call, not a calculation. The
useful move here is probably distinguishing claim types explicitly in
the prompt/schema, then accepting that the soft-skill category will
always need a fuzzier standard than the hard-skill one, by design
rather than as a remaining bug to eliminate.

8. **Correct number, wrong comparison.** With `date_facts.py` already
   supplying the right duration (~2.4 years for the TA role), the
   fact-checker still flagged the draft's "for over two years" as
   INCORRECT, citing its own correct figure as the reason - despite
   2.4 years genuinely being over two years. The pre-computed fact was
   used correctly as a number, but the comparison logic applied to it
   (does claimed duration X conflict with actual duration Y) was
   wrong. This is distinct from entry 5: the arithmetic problem there
   is solved by `date_facts.py`, but supplying a correct number doesn't
   automatically make every comparison drawn from that number correct.
   Removing arithmetic from the model's job removed one failure point,
   not the only one - comparing two correct numbers is itself a small
   reasoning step that can still go wrong.
   - Status: identified, not yet fixed. Likely a small, contained
     addition to `fact_check.txt`: an explicit rule that a vaguer
     duration claim ("over X years", "more than X years") is supported
     by any actual duration greater than X, and should only be flagged
     if the actual duration is at or below the stated threshold.
     Lower priority than entries 6-7 since it's narrow and the
     direction of the error (flagging a true claim as wrong) is safer
     than the reverse.



## Roadmap

### Shipped

- Stage 1: fit analysis (`extract_requirements.txt`) against the job ad
- Stage 2: draft CV profile paragraph (`draft_profile.txt`)
- Stage 3: independent fact-check (`fact_check.txt`), deliberately blind
  to the job ad to avoid inheriting its fabrication risk
- `src/date_facts.py`: deterministic date/duration computation,
  removing date arithmetic from the LLM's responsibilities entirely
- Unit tests for the deterministic parts (`tests/test_date_facts.py`)
- Structured failure log (see "Failure log" above) documenting bugs
  found and fixed at each stage

### Next: adversarial critic loop

This is the step that makes "agentic" an honest word for this
project — the critic decides what's wrong, the generator decides how
to respond (including pushing back), and the next round is shaped by
the last, within deterministic bounds set in code rather than left
to the model to decide when to stop.

- **Critic stage**: sighted on the job ad (unlike the fact-checker -
  the critic's entire job is "is this competitive for this role,"
  which is meaningless without it). Raises flags against the draft:
  `MISSING_EVIDENCE`, `WEAK_FRAMING`, `GENUINE_GAP`, `MISMATCH`, each
  with a quoted claim, the job ad requirement it relates to, severity,
  and (except for `GENUINE_GAP`, which must never get one) a
  suggested direction.
- **Generator response**: per flag, either a revision or an
  `acknowledged_gap` - an honest exit, mirroring the fact-checker's
  `HONEST DISCLOSURE` category.
- **Adversarial relationship between critic and fact-checker**: the
  critic pushes toward fit with the job ad; the fact-checker pushes
  back toward truth against the master doc. They are not supposed to
  fully agree. Where they conflict and the loop runs out of rounds
  without resolving it, the fact-checker's judgement wins by default -
  truth is the floor, competitiveness is negotiated on top of it. The
  critic's own suggestions also get fact-checked, not just the
  generator's final draft, since a sighted, fit-seeking critic has the
  same fabrication risk the original drafter had.
- **Loop control lives in code, not in the model's hands**:
  `GENUINE_GAP` + `acknowledged_gap` closes the flag unconditionally -
  the critic doesn't get to re-litigate an honest acknowledgement.
  `WEAK_FRAMING`/`MISMATCH` can keep being pushed on. `MAX_ROUNDS` is a
  backstop, not the primary stopping mechanism, and unresolved flags
  at the cap get logged, not silently dropped.
- **Convergence-based early stop, per flag, separate from severity.**
  Severity controls *which* disagreements are worth continuing to
  fight over; it says nothing about *how long* a given fight stays
  productive. A flag can be high-severity and still reach a point
  where successive rounds are just quibbling over wording rather than
  substance - that's a distinct signal from "this doesn't matter
  much," and needs its own check. Planned approach: compare a
  re-raised flag's category and severity to its previous round, not
  raw text diffing - if the critic re-raises essentially the same
  category/severity against a similar quoted span two rounds running,
  treat that as convergence-without-agreement and stop iterating on
  that flag specifically (other flags in the same round keep going
  independently). This needs a third resolution status alongside
  `resolved` and `acknowledged_gap` - something like
  `flagged_for_review` - so this outcome is visible in the output
  rather than silently merged into either of the other two. Mainly
  motivated by compute time on local hardware, but the secondary
  benefit is surfacing genuinely judgement-call disagreements for a
  human to look at directly, rather than letting the loop paper over
  them with a forced resolution either way.
- **Bounded ambition, not 100% coverage**: the critic shouldn't have
  to force-fit every requirement in the ad before it's satisfied -
  only the ones that matter most. Practically, this likely means
  reading the job ad's own signal of importance where it exists
  (e.g. "should desirably have..." vs a hard requirement), and not
  treating an unmet "nice to have" as something the loop needs to keep
  fighting over. The instinct behind this: there's a well-known
  pattern of people only applying when they meet most/all stated
  requirements, more common among women than men, and a critic that
  demands full coverage before being satisfied would quietly encode
  that same over-cautious standard into the tool. A bounded critic is
  a deliberate choice not to do that.

### After the critic loop

- Style-critique pass: a dedicated check against the CV style guide
  (UK English, no em-dashes, no buzzwords, tone), separate from the
  critic/fact-checker truth-and-fit loop, since style is a different
  axis entirely and mixing it in would make any one stage harder to
  reason about
- Cover letter drafting stage, following the same generator pattern
  as the profile stage, eligible for the same critic/fact-check loop
- LaTeX integration: slot finished, checked text into the existing
  modular `.tex` section files, rather than stopping at plain text
- Model comparison: qwen2.5-coder:32b / qwen3-coder:30b /
  qwen3.6:27b-35b against the current 14b, decided empirically
  (latency, GPU/CPU split, side-by-side critic output quality) rather
  than assumed - particularly interesting is whether a larger model's
  failure modes are different in kind, not just less frequent, which
  would be its own finding about whether to keep deterministic code
  paths like `date_facts.py` regardless of model size

### Deferred: gendered framing experiment

A genuinely interesting follow-on question, deliberately not part of
the core pipeline: does an LLM draft or frame identical underlying
experience differently depending on the perceived gender of the
applicant (name, pronouns)? This is a different kind of investigation
from the rest of this project - a controlled comparison (same master
doc, same job ad, only the name/pronoun changed, run systematically
rather than once) rather than a pipeline feature, and deserves its own
clean methodology rather than being folded into the critic loop. Once
the critic loop is stable, job-tailor's existing plumbing (the same
generator/fact-checker stages) becomes the infrastructure for running
that comparison, but the comparison itself is a separate piece of work
with its own write-up.

## Why this exists

A demo project showing a small, well-scoped agentic pipeline running
entirely on a free local model stack, rather than a large automation
project that's hard to reason about or demo end to end.