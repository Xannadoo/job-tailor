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

8. **Correct number, wrong conclusion.** With the date facts module in
   place and working, a new and narrower bug appeared: the
   fact-checker had the right duration for the TA role (2.4 years,
   correctly pulled from the pre-computed date facts) and still
   flagged a true draft claim - "Teaching Assistant for over two
   years" - as INCORRECT, reasoning that the duration was "off by more
   than a year." 2.4 years is genuinely more than two years; there is
   no conflict between the draft's claim and the checker's own cited
   number. The checker had correct information and still drew an
   unsupported conclusion from it - not a recurrence of the original
   arithmetic bug (the number was right), but a comparison/reasoning
   failure sitting on top of an otherwise-correct fact.
   - Status: identified, not yet fixed. Same family as entry 5's
     "recently completed" overcorrection - a model that, having been
     told to scrutinise duration claims, applies that scrutiny even
     when the actual numbers do not disagree. Likely candidate fix:
     make explicit that an approximate verbal duration ("over two
     years," "a couple of years") is consistent with a precise figure
     as long as the precise figure is on the correct side of the
     verbal claim (e.g. "over two years" is satisfied by anything
     above 2.0, not just numbers close to 2.0) - the checker currently
     seems to be testing for closeness to a round number rather than
     logical consistency with the stated comparison.

9. **Career-length error, worse version of entry 8.** Testing against
   shorter, more conversational job ads (JOE & THE JUICE, KIME,
   Halfspace) rather than the original long, dense Management
   Solutions ad surfaced a more severe instance of entry 8's pattern.
   The fact-checker correctly enumerated every role and its actual
   date range from the master document, then concluded: "this aligns
   with the claim of a seven-year career." The applicant's career
   history runs back to 2009 - roughly seventeen years before today,
   not seven. The checker had every correct number in front of it,
   stated them accurately, and still endorsed a claim off by a
   decade. Same family as entry 8 (correct number, wrong conclusion),
   but shows the failure isn't bounded to "off by a year or so" - it
   can be arbitrarily large once the claim involves summing or
   reasoning across multiple date ranges rather than checking one.
   - Status: identified, not yet fixed. Reinforces that comparison and
     summation across multiple pre-computed date facts is still being
     left to the model's own reasoning, which has now failed at both
     small and large scale. Possibly needs `date_facts.py` to also
     compute and supply an aggregate (e.g. "total professional
     experience from earliest start date to today") rather than only
     per-role facts, so a career-length claim has a pre-computed
     number to check against directly, the same way single-role
     duration claims now do.

10. **Fabrication still slips through occasionally.** On the same JOE
    & THE JUICE test, the draft profile claimed the MSc "delved into
    labour analytics" - this does not appear anywhere in the master
    document and was not flagged by the fact-checker at all, unlike
    the XGBoost/Hadoop fabrications in entry 2, which were caught
    after the fix. This is a repeat of the original fabrication-echo
    failure mode (job-ad terminology - "labour analytics" is from the
    JOE & THE JUICE ad - being echoed back as the applicant's own
    experience), just with new vocabulary, and a reminder that the
    anti-fabrication instruction is not airtight even where it has
    been working on other ads.
    - Status: identified, not yet fixed. Worth tracking whether this
      recurs across more varied ads before deciding whether it's
      occasional model unreliability (acceptable at some rate, to be
      caught by a later stage like the critic loop) or a pattern with
      an identifiable trigger worth a targeted prompt fix.

11. **Forward-looking interest in the role misclassified as an
    unsupported factual claim.** On the KIME ad, the fact-checker
    flagged "I'm excited about the opportunity to bring my skills to
    KIME's core engineering team" as UNSUPPORTED, reasoning that
    "KIME's core engineering team" doesn't appear in the master
    document. But this is not a claim about past experience - it's a
    forward-looking statement of interest in the specific role being
    applied for, which by definition cannot and should not need to
    appear in a document describing the applicant's history. The
    checker treated normal cover-letter-style aspiration about the
    target role as if it were a falsifiable claim requiring source
    evidence, which no honest application could ever satisfy.
    - This is a different category from entries 2/10 (fabricated past
      experience) and from entries 6/7 (evidentiary standard for
      hard vs soft claims) - it's a tense/intent misclassification:
      the checker isn't distinguishing "I did X" from "I want to do X
      here," and is applying the wrong test to the latter.
    - Status: identified, not yet fixed. Likely fix: add an explicit
      instruction to recognise forward-looking statements of interest
      in the role/company being applied to as a distinct category
      that should not be fact-checked against the master document at
      all (similar to how `HONEST DISCLOSURE` is exempted) - the
      question for these is whether they are honest expressions of
      interest, not whether they are independently verifiable.

12. **Date-related scrutiny firing without a real inconsistency.** Also
    on the KIME ad: "Living in Copenhagen since 2020, I am fully
    committed to being an onsite contributor" was flagged INCORRECT,
    with reasoning that conflated living somewhere since 2020 with
    starting an unrelated job in 2025 - two facts that are not in
    tension at all. The "corrected version" produced didn't even
    address its own stated objection. This looks like the checker
    pattern-matching "sentence contains a date, my instructions say
    scrutinise dates" and firing regardless of whether an actual
    inconsistency exists - a new variant of the entries 5/8/9 family
    (scrutiny applied without a real trigger), this time on a
    residency claim rather than an employment duration or career
    length claim.
    - Status: identified, not yet fixed. Worth holding until enough
      examples of this "scrutiny fires without a real conflict"
      pattern accumulate across entries 5, 8, 9, and 12 to address
      with one more general fix, rather than patching each surface
      form separately.

13. **GENUINE_GAP/MISSING_EVIDENCE boundary unstable across identical
    reruns.** Testing the critic prompt in isolation (5 repeated runs,
    same job ad, same draft, gemma3:27b-cloud via Ollama) found that
    while JSON validity was reliable (5/5 valid, parseable output every
    time), one specific issue - lack of demonstrated scikit-learn/
    XGBoost/pandas skills - was classified MISSING_EVIDENCE in 3 runs
    and GENUINE_GAP in 2 runs, with essentially the same underlying
    reasoning each time. This matters more than ordinary
    classification noise because the loop control treats the two
    categories completely differently: MISSING_EVIDENCE is something
    the generator can revise its way out of; GENUINE_GAP forces an
    honest acknowledgement and can never receive a
    `suggested_direction`. Whether the loop tries to help or gives up
    on a real issue was, in this test, effectively a coin flip rather
    than something grounded in the actual evidence. A softer version
    of the same instability also showed up in `quoted_text` selection
    for one GENUINE_GAP flag, which pointed at the applicant's
    strongest self-description rather than the actual absent evidence
    - the nearest sentence to the gap, not the gap itself.
    One thing that did hold up perfectly across all 25 flags in the
    5-run test: not a single `GENUINE_GAP` flag was ever given a
    populated `suggested_direction`, despite that hard constraint only
    being enforced by the prompt instruction, not yet by code at this
    stage. Worth noting as a real positive result alongside the
    instability finding, not just a caveat to it.
    - Status: mitigation built, not yet integration-tested.
      `src/gap_verifier.py` re-checks any GENUINE_GAP flag against the
      master document using the same direct-or-adjacent evidentiary
      standard the fact-checker already uses for hard-skill claims,
      via a narrow prompt (`prompts/verify_gap.txt`) scoped to one flag
      at a time. If real evidence turns up that the critic missed, the
      verdict is `ACTUALLY_SUPPORTED` and the flag should be
      downgraded back to MISSING_EVIDENCE/WEAK_FRAMING rather than
      accepted as unaddressable. Built with two call paths: a
      deterministic one (the loop driver calls
      `verify_genuine_gap()` directly on every GENUINE_GAP flag,
      unconditionally) and an experimental agentic one (the critic
      itself could call this as a real OpenAI-style tool via
      `complete_with_tools()`, added to `llm_client.py` for this
      purpose) - only the deterministic path is expected to be
      reliable given everything else this project has found about
      model judgement calls; the agentic path is a genuine test of
      whether this backend supports real tool-calling through
      LiteLLM at all, ~~which is not yet confirmed either way~~ Confirmed.
      (`test_tool_calling.py` checks this in isolation, separate from
      whether the verification logic itself is correct).

14. **Gap verifier: compound requirement partial-match bug.** First
    end-to-end test of the completed agentic round trip (real tool
    call, real execution against the master doc, result fed back,
    final answer produced) worked mechanically without any failures,
    but one of two test verdicts was wrong. Given a job requirement
    bundling several distinct things together ("statistical
    programming languages (SAS, R, Python, Matlab), big data tools...
    and cloud platforms (AWS, Azure, GCP)") and a quoted draft claim
    that specifically discloses lacking SAS and cloud platforms, the
    verifier found real, true evidence elsewhere in the bundle (Python
    and R are genuinely in the master doc) and concluded the whole
    requirement was `ACTUALLY_SUPPORTED` - overturning an honest,
    correct disclosure. Same family as entries 8/9/12 (correct
    evidence retrieved, wrong conclusion drawn from it), now in the
    gap verifier rather than the fact-checker.
    - Status: **fixed and confirmed working.** `verify_gap.txt` now
      requires an explicit scoping step before checking anything -
      identify the specific item(s) the quoted text is actually about,
      not the requirement bundle as a whole - and surfaces that
      decision as a `scoped_items` field in the response, so the
      scoping is visible rather than assumed. Re-tested end to end
      using the exact bundled-requirement shape that caused the
      original bug: the verifier now correctly returns `CONFIRMED_GAP`
      with `scoped_items` naming "SAS, cloud platforms" specifically,
      correctly ignoring the R/Python evidence present elsewhere in
      the same bundle. A second case (random forests not named
      directly, but covered via Advanced Machine Learning coursework)
      was re-run alongside it and still correctly returns
      `ACTUALLY_SUPPORTED` - confirming the scoping fix didn't
      overcorrect into rejecting genuine adjacent evidence once
      checking became narrower. Regression-tested via
      `test_agentic_verification.py`, which should be re-run any time
      `verify_gap.txt` changes.


      
**Entry 13 is a new category: instability in the critic's own
structured categorisation, not the free-text reasoning failures
entries 1-12 were about.** The earlier entries were mostly about a
single model call getting one thing wrong in one direction. This is
about the same call producing genuinely different classifications on
identical input - which the loop's deterministic control logic
(entries in the critic loop roadmap section) assumed would be stable
enough to build hard rules on top of. The gap-verifier is the first
piece of this project built explicitly as a check on the critic
rather than a check on the generator's output, and the first piece
built with two deliberately different invocation paths (agentic vs
deterministic) as part of testing what "agentic" actually buys over
just calling the same logic directly in code.

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

**Entries 8, 9, and 12 are one family: scrutiny without a real
trigger.** Once the fact-checker was instructed to scrutinise dates
and durations carefully (to catch entries 3 and 5), it became prone to
firing that scrutiny reflexively - on a duration that was actually
correct (8), on a multi-role sum it then got wrong despite having the
right inputs (9), and on a residency claim with no real conflict at
all (12). The common shape: the checker can usually retrieve or
compute the right underlying numbers, but doesn't reliably check
whether those numbers actually contradict the draft before objecting.

**Entries 10 and 11 are a reminder that the fixes made so far are not
universal.** Entry 10 shows the original fabrication-echo bug (2) can
still occur on new vocabulary from a different ad. Entry 11 shows a
new failure shape entirely - confusing a future-tense statement of
interest with a falsifiable factual claim. Testing against a more
varied set of job ads, rather than repeatedly running the same one,
surfaced both - worth keeping a rotating set of test ads going forward
rather than over-indexing on any single one.

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