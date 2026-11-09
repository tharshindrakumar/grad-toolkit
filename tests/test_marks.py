from pathlib import Path

import pytest

from grad_toolkit import marks
from grad_toolkit.marks import Assessment, Course

SAMPLE = Path(__file__).parent.parent / "sample_data"


def course(code, *assessments):
    return Course(code, [Assessment(f"a{i}", w, m) for i, (w, m) in enumerate(assessments)])


def test_course_needed_for_target():
    c = course("X", (50, 70), (50, None))
    assert c.earned == pytest.approx(35)
    assert c.average_so_far == pytest.approx(70)
    assert c.needed_for(65) == pytest.approx(60)


def test_finished_course_needs_nothing():
    assert course("X", (100, 80)).needed_for(65) is None


def test_group_average_across_courses():
    t = marks.exemption_target("ACC", [course("A", (50, 60), (50, None)), course("B", (50, 70), (50, None))])
    # Banked 30 + 35 of the 130 needed; 100 weight left across both courses.
    assert t.status == "possible"
    assert t.needed == pytest.approx(65)


def test_minimum_per_course_can_bind():
    # The group average is easy, but course B still needs 55 on its own.
    t = marks.exemption_target("X", [course("A", (100, 95)), course("B", (50, 30), (50, None))])
    assert t.needed == pytest.approx(80)


def test_missed_by_one_mark():
    t = marks.exemption_target("CS2", [course("A", (100, 64))])
    assert t.status == "missed"
    assert t.final_average == pytest.approx(64)


def test_finished_course_below_minimum_is_missed_early():
    t = marks.exemption_target("X", [course("A", (100, 50)), course("B", (50, 90), (50, None))])
    assert t.status == "missed"


def test_secured_and_out_of_reach():
    assert marks.exemption_target("X", [course("A", (80, 90), (20, None))]).status == "secured"
    assert marks.exemption_target("X", [course("A", (80, 40), (20, None))]).status == "out of reach"


def test_sample_data_targets():
    courses = marks.load_courses(SAMPLE / "courses.csv")
    groups = marks.load_exemptions(SAMPLE / "exemptions.csv")
    acc = marks.exemption_target("ACC", [courses[c] for c in groups["Actuarial Control Cycle"]])
    assert acc.needed == pytest.approx(61.9)
    cs2 = marks.exemption_target("CS2", [courses[c] for c in groups["CS2 (example mapping)"]])
    assert cs2.needed == pytest.approx(70.8)


def test_weights_must_total_100(tmp_path):
    path = tmp_path / "courses.csv"
    path.write_text("course,assessment,weight,mark\nX,a,40,70\nX,b,50,\n")
    with pytest.raises(ValueError, match="add up to 90"):
        marks.load_courses(path)
