"""
Data structures for the adversarial critic loop.

The critic and generator exchange structured data (flags, responses),
not free prose, because the loop control logic needs to parse and act
on individual fields - which flags are resolved, which are genuine
gaps, which have converged without agreement. That control lives in
code, not in the model's hands, by design (see README "Loop control
lives in code, not in the model's hands").

These are deliberately plain dataclasses with from_dict/to_dict
methods rather than a heavier schema library, since the LLM output
is JSON parsed by hand - keeping the shape simple here makes
validation and error messages easier to reason about when (not if)
the model produces malformed output.
"""

from dataclasses import dataclass, field
from enum import Enum


class FlagCategory(str, Enum):
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    WEAK_FRAMING = "WEAK_FRAMING"
    GENUINE_GAP = "GENUINE_GAP"
    MISMATCH = "MISMATCH"


class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FlagStatus(str, Enum):
    OPEN = "OPEN"                          # raised, not yet responded to this round
    RESOLVED = "RESOLVED"                  # generator revised, critic accepted
    ACKNOWLEDGED_GAP = "ACKNOWLEDGED_GAP"  # honest exit, closes unconditionally
    FLAGGED_FOR_REVIEW = "FLAGGED_FOR_REVIEW"  # converged without agreement, human decides
    UNRESOLVED_AT_CAP = "UNRESOLVED_AT_CAP"    # hit MAX_ROUNDS with no resolution


@dataclass
class CriticFlag:
    id: str
    quoted_text: str        # literal substring from the draft being critiqued
    category: FlagCategory
    job_ad_requirement: str # which requirement in the job ad this relates to
    severity: Severity
    suggested_direction: str | None  # must be None for GENUINE_GAP, enforced below
    status: FlagStatus = FlagStatus.OPEN
    round_raised: int = 1
    history: list[dict] = field(default_factory=list)  # prior round states, for convergence checks

    def __post_init__(self):
        if self.category == FlagCategory.GENUINE_GAP and self.suggested_direction:
            raise ValueError(
                f"Flag {self.id}: GENUINE_GAP flags must not have a "
                "suggested_direction - the critic must not fabricate "
                "phrasing to paper over something genuinely absent."
            )

    @classmethod
    def from_dict(cls, data: dict, round_number: int = 1) -> "CriticFlag":
        category = FlagCategory(data["category"])
        suggested_direction = data.get("suggested_direction") or None

        if category == FlagCategory.GENUINE_GAP:
            # Defensive: even if the model includes one, drop it rather
            # than raise - this is parsing model output, not validating
            # our own code. A hard crash on a recoverable model mistake
            # would kill the whole run unnecessarily.
            suggested_direction = None

        return cls(
            id=data["id"],
            quoted_text=data["quoted_text"],
            category=category,
            job_ad_requirement=data["job_ad_requirement"],
            severity=Severity(data["severity"]),
            suggested_direction=suggested_direction,
            round_raised=round_number,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "quoted_text": self.quoted_text,
            "category": self.category.value,
            "job_ad_requirement": self.job_ad_requirement,
            "severity": self.severity.value,
            "suggested_direction": self.suggested_direction,
            "status": self.status.value,
            "round_raised": self.round_raised,
        }


class GeneratorAction(str, Enum):
    REVISED = "revised"
    ACKNOWLEDGED_GAP = "acknowledged_gap"


@dataclass
class FlagResponse:
    flag_id: str
    action: GeneratorAction
    new_text: str | None = None           # required if action == REVISED
    acknowledgement: str | None = None    # required if action == ACKNOWLEDGED_GAP

    @classmethod
    def from_dict(cls, data: dict) -> "FlagResponse":
        action = GeneratorAction(data["action"])
        return cls(
            flag_id=data["flag_id"],
            action=action,
            new_text=data.get("new_text"),
            acknowledgement=data.get("acknowledgement"),
        )

    def to_dict(self) -> dict:
        return {
            "flag_id": self.flag_id,
            "action": self.action.value,
            "new_text": self.new_text,
            "acknowledgement": self.acknowledgement,
        }


@dataclass
class LoopResult:
    """Final output of the critic loop: the settled draft plus a full
    record of what happened to every flag, for logging and review."""

    final_draft: str
    rounds_run: int
    resolved_flags: list[CriticFlag]
    acknowledged_gaps: list[CriticFlag]
    flagged_for_review: list[CriticFlag]
    unresolved_at_cap: list[CriticFlag]

    def summary(self) -> str:
        lines = [
            f"Critic loop finished after {self.rounds_run} round(s).",
            f"  Resolved: {len(self.resolved_flags)}",
            f"  Acknowledged gaps (honest, closed): {len(self.acknowledged_gaps)}",
            f"  Flagged for human review (converged, no agreement): {len(self.flagged_for_review)}",
            f"  Unresolved at MAX_ROUNDS cap: {len(self.unresolved_at_cap)}",
        ]
        return "\n".join(lines)