"""Application tracker: what's open, stage pass rates, and who to follow up."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# Stages in the order a grad process runs. "not_applied" rows track programs you plan to apply to.
STAGES = ["not_applied", "applied", "tests", "video_interview", "final", "offer"]
OUTCOMES = {"pending", "rejected", "offer", "withdrawn"}

APPLICATION_FIELDS = [
    "employer", "role", "route", "stage", "outcome",
    "open_date", "close_date", "applied_date", "notes",
]
CONTACT_FIELDS = ["name", "employer", "role", "last_contact", "referral_asked", "notes"]


def parse_date(value: str | None) -> date | None:
    value = (value or "").strip()
    return date.fromisoformat(value) if value else None


@dataclass
class Application:
    employer: str
    role: str
    route: str
    stage: str
    outcome: str
    open_date: date | None
    close_date: date | None
    applied_date: date | None
    notes: str

    @property
    def stage_index(self) -> int:
        return STAGES.index(self.stage)


@dataclass
class Contact:
    name: str
    employer: str
    role: str
    last_contact: date | None
    referral_asked: bool
    notes: str


def _read_rows(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        # Line 1 is the header, so data rows start at line 2.
        yield from enumerate(csv.DictReader(f), start=2)


def load_applications(path: Path) -> list[Application]:
    apps = []
    for line, row in _read_rows(path):
        # A scan file lists programs without a stage; they're ones you haven't applied to yet.
        stage = (row.get("stage") or "not_applied").strip()
        if stage not in STAGES:
            raise ValueError(f"{path}:{line}: unknown stage {stage!r}; use one of {', '.join(STAGES)}")
        outcome = (row.get("outcome") or "pending").strip()
        if outcome not in OUTCOMES:
            raise ValueError(f"{path}:{line}: unknown outcome {outcome!r}; use one of {', '.join(sorted(OUTCOMES))}")
        apps.append(Application(
            employer=row["employer"].strip(),
            role=row["role"].strip(),
            route=(row.get("route") or "").strip(),
            stage=stage,
            outcome=outcome,
            open_date=parse_date(row.get("open_date")),
            close_date=parse_date(row.get("close_date")),
            applied_date=parse_date(row.get("applied_date")),
            notes=(row.get("notes") or "").strip(),
        ))
    return apps


def save_applications(path: Path, apps: list[Application]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(APPLICATION_FIELDS)
        for a in apps:
            writer.writerow([
                a.employer, a.role, a.route, a.stage, a.outcome,
                *(d.isoformat() if d else "" for d in (a.open_date, a.close_date, a.applied_date)),
                a.notes,
            ])


@dataclass
class MergeResult:
    added: list[Application]
    updated: list[tuple[Application, str]]  # the tracker row and what changed
    skipped: list[Application]  # already applied, so left alone


def merge_scan(apps: list[Application], scanned: list[Application]) -> MergeResult:
    """Fold a scan of open programs into the tracker, in place.

    New employer + role pairs are added as not applied. For programs you haven't applied to yet,
    open and close dates are updated when the scan has them. Anything you've applied to is
    never changed, so the scan can't overwrite your progress.
    """
    key = lambda a: (a.employer.strip().lower(), a.role.strip().lower())
    existing = {key(a): a for a in apps}
    result = MergeResult([], [], [])
    for s in scanned:
        current = existing.get(key(s))
        if current is None:
            new = Application(s.employer, s.role, s.route, "not_applied", "pending",
                              s.open_date, s.close_date, None, s.notes)
            apps.append(new)
            existing[key(new)] = new
            result.added.append(new)
        elif current.stage != "not_applied":
            result.skipped.append(current)
        else:
            changes = []
            for name in ("open_date", "close_date"):
                old, new = getattr(current, name), getattr(s, name)
                if new is not None and new != old:
                    setattr(current, name, new)
                    changes.append(f"{name} {old or '-'} -> {new}")
            if changes:
                result.updated.append((current, "; ".join(changes)))
    return result


def load_contacts(path: Path) -> list[Contact]:
    return [
        Contact(
            name=row["name"].strip(),
            employer=row["employer"].strip(),
            role=(row.get("role") or "").strip(),
            last_contact=parse_date(row.get("last_contact")),
            referral_asked=(row.get("referral_asked") or "").strip().lower() in {"yes", "y", "true"},
            notes=(row.get("notes") or "").strip(),
        )
        for _, row in _read_rows(path)
    ]


def open_not_applied(apps: list[Application], today: date) -> list[Application]:
    """Programs that are open now and that you haven't applied to, soonest closing first."""
    rows = [
        a for a in apps
        if a.stage == "not_applied"
        and a.outcome == "pending"
        and a.open_date is not None and a.open_date <= today
        and (a.close_date is None or a.close_date >= today)
    ]
    return sorted(rows, key=lambda a: a.close_date or date.max)


def opening_soon(apps: list[Application], today: date, days: int) -> list[Application]:
    """Programs that open within the next `days` days."""
    horizon = today + timedelta(days=days)
    rows = [
        a for a in apps
        if a.stage == "not_applied"
        and a.open_date is not None and today < a.open_date <= horizon
    ]
    return sorted(rows, key=lambda a: a.open_date)


@dataclass
class FunnelStep:
    stage: str
    next_stage: str
    reached: int
    passed: int
    failed: int
    pending: int

    @property
    def pass_rate(self) -> float | None:
        decided = self.passed + self.failed
        return self.passed / decided if decided else None


def funnel(apps: list[Application]) -> list[FunnelStep]:
    """Pass rate at each stage, counting only applications that have been decided there.

    A pending application hasn't passed or failed yet, and a withdrawn one says nothing
    about your chances, so neither counts towards the rate.
    """
    applied = [a for a in apps if a.stage != "not_applied"]
    steps = []
    for i in range(1, len(STAGES) - 1):
        reached = [a for a in applied if a.stage_index >= i]
        passed = sum(a.stage_index > i for a in reached)
        stuck = [a for a in reached if a.stage_index == i]
        steps.append(FunnelStep(
            stage=STAGES[i],
            next_stage=STAGES[i + 1],
            reached=len(reached),
            passed=passed,
            failed=sum(a.outcome == "rejected" for a in stuck),
            pending=sum(a.outcome == "pending" for a in stuck),
        ))
    return steps


def stale_contacts(contacts: list[Contact], today: date, after_days: int = 21) -> list[Contact]:
    """Contacts you haven't spoken to in `after_days` days, longest gap first."""
    rows = [c for c in contacts if c.last_contact is None or (today - c.last_contact).days >= after_days]
    return sorted(rows, key=lambda c: c.last_contact or date.min)


def referral_prompts(
    contacts: list[Contact], apps: list[Application], today: date, opened_within: int = 7
) -> list[Contact]:
    """Contacts whose firm's program opened in the last `opened_within` days and who you haven't asked yet."""
    just_opened = {
        a.employer.lower() for a in apps
        if a.open_date is not None and 0 <= (today - a.open_date).days <= opened_within
    }
    return [c for c in contacts if c.employer.lower() in just_opened and not c.referral_asked]
