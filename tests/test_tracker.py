from datetime import date
from pathlib import Path

import pytest

from grad_toolkit import tracker

SAMPLE = Path(__file__).parent.parent / "sample_data"
TODAY = date(2027, 3, 10)


@pytest.fixture
def apps():
    return tracker.load_applications(SAMPLE / "applications.csv")


@pytest.fixture
def contacts():
    return tracker.load_contacts(SAMPLE / "contacts.csv")


def test_open_not_applied_sorted_by_close_date(apps):
    rows = tracker.open_not_applied(apps, TODAY)
    assert [a.employer for a in rows] == ["Bluewater Insurance", "Pacific Actuarial Partners"]


def test_open_not_applied_includes_closing_today(apps):
    rows = tracker.open_not_applied(apps, date(2027, 3, 14))
    assert "Bluewater Insurance" in [a.employer for a in rows]


def test_opening_soon_respects_window(apps):
    assert [a.employer for a in tracker.opening_soon(apps, TODAY, 14)] == ["Ironbark Life", "Tasman Re"]
    assert [a.employer for a in tracker.opening_soon(apps, TODAY, 5)] == ["Ironbark Life"]


def test_funnel_counts_only_decided_applications(apps):
    steps = {s.stage: s for s in tracker.funnel(apps)}
    applied = steps["applied"]
    assert (applied.reached, applied.passed, applied.failed, applied.pending) == (7, 5, 1, 1)
    assert applied.pass_rate == pytest.approx(5 / 6)
    assert steps["tests"].pass_rate == pytest.approx(3 / 4)
    assert steps["video_interview"].pass_rate == pytest.approx(1 / 2)
    assert steps["final"].pass_rate is None


def test_withdrawn_does_not_count_as_failure():
    app = tracker.Application("X", "Grad", "A", "applied", "withdrawn", None, None, None, "")
    step = tracker.funnel([app])[0]
    assert (step.failed, step.pending, step.pass_rate) == (0, 0, None)


def test_stale_contacts_longest_gap_first(contacts):
    assert [c.name for c in tracker.stale_contacts(contacts, TODAY)] == ["Mei L.", "Priya S."]


def test_referral_prompts_only_unasked_contacts_at_newly_opened_firms(contacts, apps):
    assert [c.name for c in tracker.referral_prompts(contacts, apps, TODAY)] == ["Priya S."]


def test_unknown_stage_names_the_line(tmp_path):
    path = tmp_path / "applications.csv"
    path.write_text(",".join(tracker.APPLICATION_FIELDS) + "\nX,Grad,A,interview,pending,,,,\n")
    with pytest.raises(ValueError, match=r"applications.csv:2: unknown stage 'interview'"):
        tracker.load_applications(path)


def test_merge_adds_updates_and_protects_progress(apps):
    scanned = tracker.load_applications(SAMPLE / "scan.csv")
    result = tracker.merge_scan(apps, scanned)
    assert [a.employer for a in result.added] == ["Wattle Health"]
    assert apps[-1].stage == "not_applied" and apps[-1].outcome == "pending"
    (bluewater, change), = result.updated
    assert bluewater.close_date == date(2027, 3, 21)
    assert change == "close_date 2027-03-14 -> 2027-03-21"
    # Harbour Mutual is at the final round: the scan's different close date must not touch it.
    harbour = next(a for a in apps if a.employer == "Harbour Mutual")
    assert harbour in result.skipped
    assert harbour.close_date == date(2027, 3, 2) and harbour.stage == "final"


def test_merge_matches_case_insensitively_and_twice_is_a_no_op(apps):
    scanned = tracker.load_applications(SAMPLE / "scan.csv")
    for s in scanned:
        s.employer = s.employer.upper()
    tracker.merge_scan(apps, scanned)
    again = tracker.merge_scan(apps, scanned)
    assert (again.added, again.updated) == ([], [])


def test_save_round_trips(apps, tmp_path):
    path = tmp_path / "applications.csv"
    tracker.save_applications(path, apps)
    assert tracker.load_applications(path) == apps
