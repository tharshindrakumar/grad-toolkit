"""Mark targets: what you need on the assessments left to reach an exemption threshold."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

COURSE_FIELDS = ["course", "assessment", "weight", "mark"]
EXEMPTION_FIELDS = ["exemption", "course"]


@dataclass
class Assessment:
    name: str
    weight: float  # percent of the course mark
    mark: float | None  # percent; None until it's marked


@dataclass
class Course:
    code: str
    assessments: list[Assessment] = field(default_factory=list)

    @property
    def remaining_weight(self) -> float:
        return sum(a.weight for a in self.assessments if a.mark is None)

    @property
    def done_weight(self) -> float:
        return 100 - self.remaining_weight

    @property
    def earned(self) -> float:
        """Course-mark points banked so far, out of 100."""
        return sum(a.weight * a.mark / 100 for a in self.assessments if a.mark is not None)

    @property
    def average_so_far(self) -> float | None:
        return self.earned / self.done_weight * 100 if self.done_weight else None

    def needed_for(self, target: float) -> float | None:
        """Average needed on the remaining assessments to finish on `target`; None once finished."""
        if not self.remaining_weight:
            return None
        return (target - self.earned) / self.remaining_weight * 100


def load_courses(path: Path) -> dict[str, Course]:
    courses: dict[str, Course] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for line, row in enumerate(csv.DictReader(f), start=2):
            code = row["course"].strip()
            mark_text = (row.get("mark") or "").strip()
            mark = float(mark_text) if mark_text else None
            if mark is not None and not 0 <= mark <= 100:
                raise ValueError(f"{path}:{line}: mark {mark} is outside 0-100")
            course = courses.setdefault(code, Course(code))
            course.assessments.append(Assessment(row["assessment"].strip(), float(row["weight"]), mark))
    for course in courses.values():
        total = sum(a.weight for a in course.assessments)
        if abs(total - 100) > 0.01:
            raise ValueError(f"{path}: weights for {course.code} add up to {total:g}, not 100")
    return courses


def load_exemptions(path: Path) -> dict[str, list[str]]:
    """Exemption name -> the courses its mark is averaged over, in file order."""
    groups: dict[str, list[str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            groups.setdefault(row["exemption"].strip(), []).append(row["course"].strip())
    return groups


@dataclass
class ExemptionTarget:
    exemption: str
    courses: list[str]
    status: str  # achieved, missed, secured, possible, out of reach
    needed: float | None = None  # average needed on every remaining assessment
    final_average: float | None = None  # set once every course is finished


def exemption_target(
    name: str, courses: list[Course], target: float = 65, minimum: float = 55
) -> ExemptionTarget:
    """What you need for an exemption averaged over `courses`, with `minimum` in each course.

    Courses are weighted equally, which matches UNSW's 6-UOC actuarial courses. The answer is
    the single average you'd need on every assessment you haven't sat yet across the group.
    """
    codes = [c.code for c in courses]
    remaining = sum(c.remaining_weight for c in courses)
    if not remaining:
        average = sum(c.earned for c in courses) / len(courses)
        ok = average >= target and min(c.earned for c in courses) >= minimum
        return ExemptionTarget(name, codes, "achieved" if ok else "missed", final_average=average)

    # Every remaining assessment scores x: the group average is (sum earned + x * remaining / 100) / n.
    needed = (target * len(courses) - sum(c.earned for c in courses)) / remaining * 100
    for c in courses:
        if c.remaining_weight:
            needed = max(needed, c.needed_for(minimum))
        elif c.earned < minimum:
            return ExemptionTarget(name, codes, "missed")

    if needed <= 0:
        status = "secured"
    elif needed > 100:
        status = "out of reach"
    else:
        status = "possible"
    return ExemptionTarget(name, codes, status, needed=max(needed, 0.0))
