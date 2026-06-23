"""
Tests for src/date_facts.py.

These test the one part of the pipeline with a single objectively
correct answer - date arithmetic - which is exactly why it was pulled
out of the LLM and into code in the first place. Everything else in
the pipeline (fit analysis, drafting, fact-checking judgement calls)
is not really unit-testable in this sense; this module is.
"""

from datetime import date

from src.date_facts import extract_date_facts, build_date_facts_block


SAMPLE_DOC = """
### MSc Data Science — ITU Copenhagen (2023–2025)
Some content here.

### Teaching Assistant — BSc & MSc Data Science, ITU Copenhagen (Jan 2023 – Jun 2025)
Some content here.

### Housekeeping & Admin Assistant — AC Bella Sky, Copenhagen (Sept 2025 – present)
Some content here.

### Admin / Cash Office Manager — Morrisons, Exeter, UK (Jul 2009 – Nov 2018)
Some content here.

### Breastfeeding Peer Supporter — voluntary (2018-2019)
Some content here.
"""

TODAY = date(2026, 6, 20)


def test_finds_all_parseable_ranges():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    titles = {f.title for f in facts}
    assert "MSc Data Science — ITU Copenhagen" in titles
    assert "Teaching Assistant — BSc & MSc Data Science, ITU Copenhagen" in titles
    assert "Housekeeping & Admin Assistant — AC Bella Sky, Copenhagen" in titles
    assert "Admin / Cash Office Manager — Morrisons, Exeter, UK" in titles
    assert "Breastfeeding Peer Supporter — voluntary" in titles
    assert len(facts) == 5


def test_finished_role_marked_correctly():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    msc = next(f for f in facts if "MSc Data Science" in f.title)
    assert msc.is_ongoing is False
    assert msc.end_year == 2025


def test_ongoing_role_marked_correctly():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    bella_sky = next(f for f in facts if "Bella Sky" in f.title)
    assert bella_sky.is_ongoing is True
    assert bella_sky.start_year == 2025
    assert bella_sky.start_month == 9


def test_duration_matches_known_correct_value():
    """
    This is the exact case that previously failed: the model claimed
    the TA role (Jan 2023 - Jun 2025) was "four years" when it is
    actually approximately 2.5 years.
    """
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    ta_role = next(f for f in facts if "Teaching Assistant" in f.title)
    assert ta_role.is_ongoing is False
    # Jan 2023 to Jun 2025 = 29 months = ~2.4 years
    assert 2.3 <= ta_role.duration_years <= 2.5


def test_long_duration_role_computed_correctly():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    morrisons = next(f for f in facts if "Morrisons" in f.title)
    # Jul 2009 to Nov 2018 = 9 years 4 months
    assert 9.2 <= morrisons.duration_years <= 9.4


def test_year_only_range_flagged_as_imprecise():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    msc = next(f for f in facts if "MSc Data Science" in f.title)
    assert msc.is_imprecise is True


def test_month_precise_range_not_flagged_as_imprecise():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    ta_role = next(f for f in facts if "Teaching Assistant" in f.title)
    assert ta_role.is_imprecise is False


def test_describe_for_finished_role_mentions_finished():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    msc = next(f for f in facts if "MSc Data Science" in f.title)
    description = msc.describe(TODAY)
    assert "FINISHED" in description
    assert "approximate" in description.lower()  # year-only caveat


def test_describe_for_ongoing_role_mentions_ongoing():
    facts = extract_date_facts(SAMPLE_DOC, TODAY)
    bella_sky = next(f for f in facts if "Bella Sky" in f.title)
    description = bella_sky.describe(TODAY)
    assert "ongoing" in description.lower()
    assert "FINISHED" not in description


def test_build_block_returns_one_line_per_fact():
    block = build_date_facts_block(SAMPLE_DOC, TODAY)
    lines = [l for l in block.split("\n") if l.strip()]
    assert len(lines) == 5


def test_empty_doc_returns_fallback_message():
    block = build_date_facts_block("no dates here at all", TODAY)
    assert "No parseable date ranges" in block


def test_irregular_entry_without_real_range_is_skipped():
    """
    Entries like "(2020, UK lockdown)" don't have a real start-end
    range and should be skipped rather than misparsed into a fake one.
    """
    doc_with_irregular = SAMPLE_DOC + (
        "\n### COVID Community Coordinator — voluntary (2020, UK lockdown)\n"
    )
    facts = extract_date_facts(doc_with_irregular, TODAY)
    titles = {f.title for f in facts}
    assert "COVID Community Coordinator — voluntary" not in titles
