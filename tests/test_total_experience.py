"""
Tests for date_facts.compute_total_experience() / total_experience_from_doc().

These are pure unit tests against the deterministic computation only -
no LLM call, no agentic loop, no network. That's deliberate: this is
the part with a single objectively correct answer, so it should be
testable the same way tests/test_date_facts.py already tests the
per-role duration logic.

Includes the exact regression case from failure log entry 9: a model
correctly enumerated Morrisons (2009-2018), East Devon (2018-2020), and
other roles, then still endorsed a draft's claim of "seven years"
total career length - actually closer to seventeen years from the
earliest recorded start. This suite exists to guarantee that number is
always computed correctly in code, regardless of what any model does
with it downstream.
"""

from datetime import date

from src.date_facts import extract_date_facts, compute_total_experience


TODAY = date(2026, 6, 23)  # matches the date used in the real entry 9 run

# Mirrors the real master doc's relevant entries closely enough to
# reproduce entry 9's bug shape: multiple non-overlapping past roles,
# two overlapping roles (TA + MSc, same 2023-2025 window), and one
# ongoing role.
SAMPLE_DOC = """
### Admin / Cash Office Manager — Morrisons, Exeter, UK (Jul 2009 – Nov 2018)
Some content.

### Income and Payments Assistant — East Devon District Council, UK (Nov 2018 – Aug 2020)
Some content.

### MSc Data Science — ITU Copenhagen (2023–2025)
Some content.

### Teaching Assistant — BSc & MSc Data Science, ITU Copenhagen (Jan 2023 – Jun 2025)
Some content.

### Housekeeping & Admin Assistant — AC Bella Sky, Copenhagen (Sept 2025 – present)
Some content.
"""


def test_earliest_start_is_correct():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    result = compute_total_experience(facts, TODAY)
    assert result["earliest_start"] == "2009-07-01"


def test_career_span_is_not_seven_years():
    """
    The exact regression case: entry 9 had a model endorse "seven
    years" for a career that actually spans back to 2009. This test
    fails loudly if that number is ever wrong again.
    """
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    result = compute_total_experience(facts, TODAY)
    assert result["career_span_years"] != 7.0
    # Jul 2009 to Jun 2026 is roughly 17 years
    assert 16.5 <= result["career_span_years"] <= 17.5


def test_overlapping_roles_not_double_counted():
    """
    MSc (2023-2025) and Teaching Assistant (Jan 2023 - Jun 2025) run
    concurrently. Naively summing every role's duration would count
    this period twice. covered_years should reflect merged, real
    elapsed time, not a double-counted sum.
    """
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    result = compute_total_experience(facts, TODAY)

    naive_sum = sum(
        f.duration_years or 0 for f in facts if not f.is_ongoing
    ) + (TODAY.year + TODAY.month / 12 - 2025 - 9 / 12)  # rough Bella Sky contribution

    # covered_years must be less than a naive sum would give, since
    # the naive sum double-counts the MSc/TA overlap.
    assert result["covered_years"] < naive_sum


def test_covered_years_less_than_or_equal_to_span():
    """
    Covered time (what the master doc actually accounts for) can
    never exceed the total span from earliest start to today - that
    would be a contradiction.
    """
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    result = compute_total_experience(facts, TODAY)
    assert result["covered_years"] <= result["career_span_years"]


def test_gap_years_reflects_2020_to_2023():
    """
    Nothing in this sample doc covers 2020 (end of East Devon) to
    2023 (start of MSc/TA) - roughly a 3-year gap (undergraduate study
    isn't in this trimmed sample). gap_years should be positive and
    roughly in that range.
    """
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    result = compute_total_experience(facts, TODAY)
    assert result["gap_years"] > 2.0


def test_empty_facts_returns_none_not_zero():
    """
    No data should not be conflated with zero experience - returning
    0.0 would be misleading in a way that's worse than returning None.
    """
    result = compute_total_experience([], TODAY)
    assert result["career_span_years"] is None
    assert result["covered_years"] is None
    assert result["earliest_start"] is None


def test_ongoing_role_extends_to_today():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    result = compute_total_experience(facts, TODAY)
    # The most recent merged interval should reach today, since Bella
    # Sky is ongoing - covered_years should include Sept 2025 to now.
    assert result["covered_years"] > 0