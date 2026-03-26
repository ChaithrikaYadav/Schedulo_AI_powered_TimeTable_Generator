"""
tests/test_algorithmic_scheduler.py
Pytest suite verifying the 6-phase AlgorithmicSchedulerEngine.

All 10 tests are pure-Python unit tests — no database required.
They create minimal in-memory objects and call phase functions directly.

Run with:
    pytest tests/test_algorithmic_scheduler.py -v
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — lightweight mock objects (no SQLAlchemy required)
# ─────────────────────────────────────────────────────────────────────────────

def _subject(name, stype="Theory", credits=4.0, weekly_periods=4, dept_id=1):
    return SimpleNamespace(
        id=hash(name) % 1000 + 1,
        name=name,
        subject_type=stype,
        credits=credits,
        weekly_periods=weekly_periods,
        requires_consecutive_lab=(stype == "Lab"),
        lab_duration_periods=2 if stype == "Lab" else 1,
        department_id=dept_id,
        semester=None,
        department=None,
    )


def _section(section_id="3CSE1", dept_id=1, sem="Sem 3", strength=60):
    return SimpleNamespace(
        id=1, section_id=section_id, department_id=dept_id,
        semester=sem, strength=strength, department=None,
    )


def _faculty(name, dept_id=1, main_subj="Operating Systems",
             preferred="Any", can_labs=False, max_pw=18):
    from schedulo.scheduler_core.models import FacultySlot
    return FacultySlot(
        faculty_id=hash(name) % 1000 + 1,
        name=name,
        department_id=dept_id,
        main_subject=main_subj,
        backup_subject="",
        max_classes_per_week=max_pw,
        preferred_slots=preferred,
        can_take_labs=can_labs,
    )


def _room(room_id, rtype="Classroom", capacity=60):
    from schedulo.scheduler_core.models import RoomSlot
    return RoomSlot(
        room_pk=hash(room_id) % 1000 + 1,
        room_id_str=room_id,
        room_type=rtype,
        building="ENG",
        capacity=capacity,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Engine is deterministic (same input → identical output)
# ─────────────────────────────────────────────────────────────────────────────
def test_phase2_ordering_is_deterministic():
    """
    Phase 2 must produce the exact same order on two identical calls.
    (Full engine determinism tested via phase 2 since it's pure Python.)
    """
    from schedulo.scheduler_core.models import SubjectDemand
    from schedulo.scheduler_core.phase2_priority import order_demands

    demands = [
        SubjectDemand(1, "OS", "Theory", 4.0, 4, False, 1, 1, "CSE1", 1, "Sem 3"),
        SubjectDemand(2, "OS Lab", "Lab", 2.0, 2, True, 2, 1, "CSE1", 1, "Sem 3"),
        SubjectDemand(3, "Project", "Project", 1.0, 1, False, 1, 1, "CSE1", 1, "Sem 3"),
        SubjectDemand(4, "DBMS", "Theory", 4.0, 4, False, 1, 1, "CSE1", 1, "Sem 3"),
    ]

    result1 = [d.subject_name for d in order_demands(demands)]
    result2 = [d.subject_name for d in order_demands(demands)]
    assert result1 == result2, "Phase 2 is not deterministic"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — MLQ: Labs scheduled before Theory before Project
# ─────────────────────────────────────────────────────────────────────────────
def test_phase2_lab_before_theory_before_project():
    """Phase 2 MLQ: Queue 0 (Lab) > Queue 1 (Theory) > Queue 2 (Project)."""
    from schedulo.scheduler_core.models import SubjectDemand
    from schedulo.scheduler_core.phase2_priority import order_demands

    demands = [
        SubjectDemand(1, "Theory A", "Theory", 4.0, 4, False, 1, 1, "CSE1", 1, "Sem 3"),
        SubjectDemand(2, "Project B", "Project", 1.0, 1, False, 1, 1, "CSE1", 1, "Sem 3"),
        SubjectDemand(3, "Lab C", "Lab", 2.0, 2, True, 2, 1, "CSE1", 1, "Sem 3"),
    ]
    ordered = order_demands(demands)
    assert ordered[0].subject_type == "Lab", "Lab should be first (Queue 0)"
    assert ordered[-1].subject_type == "Project", "Project should be last (Queue 2)"


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — LJF: Higher credit subjects score higher within same queue
# ─────────────────────────────────────────────────────────────────────────────
def test_phase2_priority_score_higher_credits_first():
    """Within Theory queue: 5-credit subject must score higher than 2-credit."""
    from schedulo.scheduler_core.models import SubjectDemand
    from schedulo.scheduler_core.phase2_priority import compute_priority_score

    high_credit = SubjectDemand(1, "Advanced Algo", "Theory", 5.0, 5, False, 1, 1, "S", 1, "Sem 3")
    low_credit  = SubjectDemand(2, "Soft Skills",   "Theory", 2.0, 2, False, 1, 1, "S", 1, "Sem 3")

    assert compute_priority_score(high_credit) > compute_priority_score(low_credit), (
        "Higher-credit subject must have higher LJF priority score"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — Phase 3: Wrong-department faculty returns None
# ─────────────────────────────────────────────────────────────────────────────
def test_phase3_faculty_department_filter():
    """Faculty from dept=4 (HOS) must never be assigned to a CSE (dept=1) demand."""
    from schedulo.scheduler_core.models import SubjectDemand
    from schedulo.scheduler_core.phase3_faculty import assign_faculty

    hos_faculty = _faculty("Chef Ramsay", dept_id=4, main_subj="Gastronomy")
    cse_demand = SubjectDemand(1, "Operating Systems", "Theory", 4.0, 4, False, 1, 1, "CSE1", 1, "Sem 3")

    result = assign_faculty(cse_demand, [hos_faculty])
    assert result is None, "Cross-department faculty must not be assigned (Bug 2 enforcement)"


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — Phase 3: Exact subject match scores 100
# ─────────────────────────────────────────────────────────────────────────────
def test_phase3_exact_subject_match_scores_100():
    """Exact case-insensitive match between faculty.main_subject and demand must score 100."""
    from schedulo.scheduler_core.phase3_faculty import _subject_match_score

    fac = _faculty("Aditi Verma", main_subj="Operating Systems")
    score = _subject_match_score(fac, "Operating Systems")
    assert score == 100.0, f"Exact match must score 100, got {score}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 6 — Phase 4: Theory slots spread across different days
# ─────────────────────────────────────────────────────────────────────────────
def test_phase4_theory_slots_spread_across_days():
    """A 4-period/week theory subject must land on 4 different days (spread rule)."""
    from schedulo.scheduler_core.models import SubjectDemand
    from schedulo.scheduler_core.phase4_slots import find_theory_slots

    demand = SubjectDemand(1, "Networks", "Theory", 4.0, 4, False, 1, 1, "CSE1", 1, "Sem 3")
    fac    = _faculty("Dr. Singh", main_subj="Networks")
    rooms  = [_room(f"ENG-10{i}") for i in range(10)]

    slots = find_theory_slots(demand, fac, rooms, {})
    days  = [s[0] for s in slots]
    assert len(set(days)) == len(days), (
        f"Same subject placed on same day twice — spread rule violated. Days: {days}"
    )
    assert len(slots) == 4, f"Expected 4 slots, got {len(slots)}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 7 — Phase 4: Lab slot never starts at Period 4 (lunch straddle guard)
# ─────────────────────────────────────────────────────────────────────────────
def test_phase4_lab_not_straddling_p4_p5():
    """Lab must never start at period 4 (would occupy P4+P5, straddling lunch)."""
    from schedulo.scheduler_core.models import SubjectDemand
    from schedulo.scheduler_core.phase4_slots import find_best_lab_slot

    demand = SubjectDemand(1, "OS Lab", "Lab", 2.0, 2, True, 2, 1, "CSE1", 1, "Sem 3")
    fac    = _faculty("Lab Teacher", main_subj="OS Lab", can_labs=True)
    lab_rooms = [_room(f"LAB-{i}", rtype="Lab") for i in range(5)]

    result = find_best_lab_slot(demand, fac, lab_rooms, {})
    if result:
        _, period_start, _ = result
        assert period_start != 4, (
            f"Lab starts at period 4 — would straddle P4+P5 lunch boundary (HC-03 violation)"
        )
        assert period_start != 5, (
            f"Lab starts at period 5 — would straddle P5+P6 lunch boundary (HC-03 violation)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 8 — Phase 4: Lab slot assigned in a Lab-type room
# ─────────────────────────────────────────────────────────────────────────────
def test_phase4_lab_slot_in_lab_room():
    """Lab slots must be placed in Lab-type rooms (not Classrooms)."""
    from schedulo.scheduler_core.models import SubjectDemand
    from schedulo.scheduler_core.phase4_slots import find_best_lab_slot

    demand = SubjectDemand(1, "Networks Lab", "Lab", 2.0, 2, True, 2, 1, "CSE1", 1, "Sem 3")
    fac    = _faculty("Lab Dr.", main_subj="Networks Lab", can_labs=True)

    mixed_rooms = [
        _room("ENG-101", rtype="Classroom"),
        _room("ENG-102", rtype="Classroom"),
        _room("LAB-201", rtype="Lab"),
        _room("LAB-202", rtype="Lab"),
    ]

    result = find_best_lab_slot(demand, fac, mixed_rooms, {})
    assert result is not None, "No lab slot found despite Lab rooms being available"
    _, _, chosen_room = result
    assert chosen_room.room_type.lower() in ("lab", "computer lab"), (
        f"Lab slot assigned to non-Lab room: {chosen_room.room_id_str} ({chosen_room.room_type})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 9 — Phase 1: Semester-appropriate subject count
# ─────────────────────────────────────────────────────────────────────────────
def test_phase1_semester_appropriate_subject_count():
    """Sem 3 should produce 5T + 2L + 1P = 8 demands (or fewer if not enough subjects)."""
    from schedulo.scheduler_core.phase1_demand import build_demands

    sec = _section(sem="Sem 3", dept_id=1)

    # 6 theory subjects, 3 labs, 2 projects — all for dept=1
    subjects = (
        [_subject(f"Theory{i}", "Theory", 4.0, 4, dept_id=1) for i in range(6)]
        + [_subject(f"Lab{i}", "Lab", 2.0, 2, dept_id=1) for i in range(3)]
        + [_subject(f"Project{i}", "Project", 1.0, 1, dept_id=1) for i in range(2)]
    )

    demands = build_demands(sec, subjects)
    assert len(demands) == 8, f"Sem 3 should produce 8 demands (5+2+1), got {len(demands)}"

    theory_count  = sum(1 for d in demands if d.subject_type == "Theory")
    lab_count     = sum(1 for d in demands if d.subject_type == "Lab")
    project_count = sum(1 for d in demands if d.subject_type == "Project")

    assert theory_count  == 5, f"Expected 5 theory, got {theory_count}"
    assert lab_count     == 2, f"Expected 2 labs, got {lab_count}"
    assert project_count == 1, f"Expected 1 project, got {project_count}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 10 — Phase 6: Exactly one lunch slot per day
# ─────────────────────────────────────────────────────────────────────────────
def test_phase6_lunch_exactly_once_per_day():
    """assign_lunch_all_days() must place exactly 1 LUNCH slot per day (6 total)."""
    from schedulo.scheduler_core.models import SlotType, ScheduledSlot
    from schedulo.scheduler_core.phase6_balance import assign_lunch_all_days

    # Empty schedule (no pre-existing slots)
    schedule: dict[tuple[int, int], ScheduledSlot] = {}
    result = assign_lunch_all_days(schedule, section_id=1, section_str="CSE1")

    lunch_slots = [s for s in result.values() if s.slot_type == SlotType.LUNCH]
    assert len(lunch_slots) == 6, f"Expected 6 lunch slots (one per day), got {len(lunch_slots)}"

    # Each day should have exactly 1 lunch slot
    days_with_lunch = [s.day_of_week for s in lunch_slots]
    assert sorted(days_with_lunch) == [0, 1, 2, 3, 4, 5], (
        f"Not all 6 days have a lunch slot: {days_with_lunch}"
    )

    # Lunch must be at period 5 or 6
    for slot in lunch_slots:
        assert slot.period_number in (5, 6), (
            f"Lunch at invalid period {slot.period_number} on day {slot.day_of_week}"
        )
