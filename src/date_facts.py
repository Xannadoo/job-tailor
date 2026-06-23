"""
Deterministic date and duration handling for the career master document.

Why this exists: the LLM was repeatedly unreliable at two related but
distinct tasks - judging whether a role/degree described in the
master document is finished or ongoing relative to today, and
computing how long a role/degree lasted. Both are pure arithmetic on
dates, not judgement calls, so they belong in code, not in a prompt.
This module extracts every date range from the master document,
computes status and duration for each, and produces a short block of
plain-English facts to inject into prompts. The model's job becomes
"use these facts," not "do this arithmetic."

This is deliberately narrow: it parses heading-style date ranges
(e.g. "(Jan 2023 - Jun 2025)", "(2023-2025)", "(Sept 2025 - present)")
and entries with only a single year are treated as informational only
(no clear range to compute a duration from), not skipped silently.
"""

import re
from dataclasses import dataclass
from datetime import date


MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Matches a heading line like:
#   ### Teaching Assistant — BSc & MSc Data Science, ITU Copenhagen (Jan 2023 – Jun 2025)
#   ### MSc Data Science — ITU Copenhagen (2023–2025)
#   ### Housekeeping & Admin Assistant — AC Bella Sky, Copenhagen (Sept 2025 – present)
# Captures: the heading title, and the raw date range text inside the
# final parentheses on the line.
HEADING_WITH_DATE_RANGE = re.compile(
    r"^#{1,4}\s*(?P<title>.+?)\s*\((?P<range>[^()]*\d{4}[^()]*)\)\s*$",
    re.MULTILINE,
)

# Matches one side of a range: an optional month name followed by a
# 4-digit year, OR the literal word "present".
DATE_PART = re.compile(
    r"(?P<month>[A-Za-z]+)?\s*(?P<year>\d{4})|(?P<present>present)",
    re.IGNORECASE,
)


@dataclass
class DateRangeFact:
    title: str
    raw_range: str
    start_year: int
    start_month: int | None
    end_year: int | None  # None means "present"
    end_month: int | None
    is_ongoing: bool
    duration_years: float | None  # None if ongoing or unparseable

    @property
    def is_imprecise(self) -> bool:
        """
        True if either side of the range is year-only. Duration
        computed from a year-only range defaults to a full calendar
        year span (Jan-Dec) and can overstate or understate the real
        duration - this should be flagged rather than presented as
        exact.
        """
        return self.start_month is None or (
            not self.is_ongoing and self.end_month is None
        )

    def describe(self, today: date) -> str:
        """Render this fact as a plain-English line for prompt injection."""
        if self.is_ongoing:
            start_str = _format_month_year(self.start_month, self.start_year)
            return (
                f'"{self.title}": started {start_str}, ongoing as of '
                f"{today.isoformat()}."
            )

        start_str = _format_month_year(self.start_month, self.start_year)
        end_str = _format_month_year(self.end_month, self.end_year)

        if self.duration_years is None:
            duration_str = "duration unclear from available dates"
        elif self.is_imprecise:
            duration_str = (
                f"approximately {self.duration_years:.1f} years "
                "(only year given, not exact month - treat as approximate)"
            )
        else:
            duration_str = f"{self.duration_years:.1f} years"

        return (
            f'"{self.title}": {start_str} to {end_str}. FINISHED '
            f"(end date is before today, {today.isoformat()}). "
            f"Duration: {duration_str}."
        )


def _format_month_year(month: int | None, year: int) -> str:
    if month is None:
        return str(year)
    month_name = [k for k, v in MONTH_NAMES.items() if v == month][0]
    return f"{month_name.capitalize()} {year}"


def _parse_date_part(text: str):
    """
    Parse one side of a range (e.g. "Jan 2023", "2025", "present") into
    (year, month) or signal "present" via a special marker. Returns
    None if it cannot be parsed at all.
    """
    text = text.strip()
    if text.lower() == "present":
        return "present"

    match = DATE_PART.search(text)
    if not match or not match.group("year"):
        return None

    year = int(match.group("year"))
    month_str = match.group("month")
    month = MONTH_NAMES.get(month_str.lower()) if month_str else None
    return (year, month)


def extract_date_facts(career_master_doc: str, today: date) -> list[DateRangeFact]:
    """
    Find every heading-style date range in the master document and
    compute status (finished/ongoing) and duration for each.

    Entries where a range genuinely cannot be parsed (e.g. only a
    single bare year, or unusual phrasing) are skipped rather than
    guessed at - silently wrong structured facts would be worse than
    no fact at all for that entry.
    """
    facts = []

    for match in HEADING_WITH_DATE_RANGE.finditer(career_master_doc):
        title = match.group("title").strip()
        raw_range = match.group("range").strip()

        # Split on the dash-like separator between start and end.
        # Master doc uses both en-dash (–) and hyphen (-).
        parts = re.split(r"\s*[–—-]\s*", raw_range)
        if len(parts) != 2:
            continue

        start_parsed = _parse_date_part(parts[0])
        end_parsed = _parse_date_part(parts[1])

        if start_parsed is None or start_parsed == "present" or end_parsed is None:
            # A range needs a real start date; skip anything else
            # rather than fabricate a guess.
            continue

        start_year, start_month = start_parsed

        if end_parsed == "present":
            facts.append(
                DateRangeFact(
                    title=title,
                    raw_range=raw_range,
                    start_year=start_year,
                    start_month=start_month,
                    end_year=None,
                    end_month=None,
                    is_ongoing=True,
                    duration_years=None,
                )
            )
            continue

        end_year, end_month = end_parsed

        end_date = date(end_year, end_month or 12, 1)
        is_ongoing = end_date > today

        duration_years = None
        if not is_ongoing:
            start_m = start_month or 1
            end_m = end_month or 12
            total_months = (end_year - start_year) * 12 + (end_m - start_m)
            duration_years = round(total_months / 12, 1)

        facts.append(
            DateRangeFact(
                title=title,
                raw_range=raw_range,
                start_year=start_year,
                start_month=start_month,
                end_year=end_year,
                end_month=end_month,
                is_ongoing=is_ongoing,
                duration_years=duration_years,
            )
        )

    return facts


def build_date_facts_block(career_master_doc: str, today: date) -> str:
    """
    Produce the plain-English block of pre-computed date facts to
    inject into prompts, so the model never has to do this arithmetic
    itself - it only has to use the answers given here.
    """
    facts = extract_date_facts(career_master_doc, today)

    if not facts:
        return "(No parseable date ranges found in the career master document.)"

    lines = [f.describe(today) for f in facts]
    return "\n".join(f"- {line}" for line in lines)
