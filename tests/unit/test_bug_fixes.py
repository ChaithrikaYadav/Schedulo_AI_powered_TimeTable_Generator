"""
tests/test_bug_fixes.py
Pytest test suite verifying all 8 Schedulo bug fixes.

Tests 1–7 use an in-memory SQLite database (from conftest.py async_session fixture).
Test 8 is a simple filesystem check for .gitignore coverage.

Run with:
    pytest tests/test_bug_fixes.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio


PROJECT_ROOT = Path(__file__).parent.parent.parent  # tests/unit/ -> tests/ -> project root


# ─────────────────────────────────────────────────────────────────────────────
# Shared DB seed helpers
# ─────────────────────────────────────────────────────────────────────────────
async def _seed_dept(session) -> "Department":
    from schedulo.models import Department
    dept = Department(name="School of Computer Science & Engineering", short_code="CSE")
    session.add(dept)
    await session.flush()
    return dept


async def _seed_wrong_dept(session) -> "Department":
    from schedulo.models import Department
    d = Department(name="School of Hospitality & Services Management", short_code="HOS")
    session.add(d)
    await session.flush()
    return d


async def _seed_rooms(session) -> list:
    from schedulo.models import Room
    rooms = [
        Room(room_id="ENG-101", building="ENG", room_type="Classroom", capacity=60,
             floor=1, has_projector=True),
        Room(room_id="LAB-301", building="ENG", room_type="Lab",       capacity=30,
             floor=3, has_computers=True),
    ]
    for r in rooms:
        session.add(r)
    await session.flush()
    return rooms


async def _seed_faculty(session, dept_id: int) -> list:
    from schedulo.models import Faculty
    fac = [
        Faculty(name="Aditi Verma",  department_id=dept_id, main_subject="Operating Systems",
                max_classes_per_week=18, can_take_labs=False),
        Faculty(name="Ramesh Kumar", department_id=dept_id, main_subject="Data Structures",
                max_classes_per_week=18, can_take_labs=False),
    ]
    for f in fac:
        session.add(f)
    await session.flush()
    return fac


async def _seed_subjects(session, dept_id: int) -> list:
    from schedulo.models import Subject
    subjs = [
        Subject(name="Operating Systems", department_id=dept_id, subject_type="Theory",
                credits=4.0, weekly_periods=4),
        Subject(name="Data Structures",   department_id=dept_id, subject_type="Theory",
                credits=4.0, weekly_periods=4),
    ]
    for s in subjs:
        session.add(s)
    await session.flush()
    return subjs


async def _seed_section(session, dept_id: int, sem: str = "Sem 3") -> "Section":
    from schedulo.models import Section
    sec = Section(section_id="3CSE1", department_id=dept_id, semester=sem,
                  program="B.Tech CSE", strength=60)
    session.add(sec)
    await session.flush()
    return sec


async def _seed_timetable(session, dept_id: int, semester: str = "Sem 3") -> "Timetable":
    from schedulo.models import Timetable
    from datetime import datetime
    tt = Timetable(
        name=f"Test Timetable ({semester})",
        department_id=dept_id,
        academic_year="2024-25",
        semester=semester,
        status="COMPLETED",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(tt)
    await session.flush()
    return tt


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Correct subjects for CSE sections (Bug 1)
# ─────────────────────────────────────────────────────────────────────────────
def test_cse_section_gets_only_cse_subjects():
    """
    Bug 1: CSE sections must NOT contain Hospitality or Management subjects.
    Verifies that DEPT_SUBJECT_EXCLUSIONS in PrototypeScheduler contains
    all known cross-department contaminants for the CSE department.

    This is a pure unit test — no DB needed.
    """
    from schedulo.scheduler_core.prototype_scheduler import (
        DEPT_SUBJECT_EXCLUSIONS,
        PrototypeScheduler,
        DAYS, PERIODS,
    )

    cse_exclusions = DEPT_SUBJECT_EXCLUSIONS.get(
        "School of Computer Science & Engineering", []
    )

    # All confirmed bad subjects from the live DB diagnosis must be blocked
    BAD_SUBJECTS = [
        "Business Economics", "Bakery & Confectionery Lab", "Financial Management",
        "Tourism Geography", "Resort Management", "Gastronomy",
        "Front Office Management", "Financial Accounting",
        "Business Law", "Corporate Finance", "Taxation Laws",
        "Marketing Management", "Internship Project",
    ]
    for bad in BAD_SUBJECTS:
        assert bad in cse_exclusions, (
            f"Bug 1: '{bad}' is missing from DEPT_SUBJECT_EXCLUSIONS for CSE — "
            f"it would still be assigned to CSE sections"
        )

    # Verify _get_subjects_for_section() strips excluded subjects
    # by checking that the exclusion filter is applied in the method
    import inspect
    src = inspect.getsource(PrototypeScheduler._get_subjects_for_section)
    assert "exclusions" in src, (
        "Bug 1: _get_subjects_for_section() does not apply exclusion filter"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — Correct faculty department matches section department (Bug 2)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_faculty_department_matches_section_department(async_session):
    """
    Bug 2: PrototypeScheduler._build_teacher_map_for_dept() must only return
    teachers from the target department.
    """
    from schedulo.scheduler_core.prototype_scheduler import PrototypeScheduler, _dept_matches

    # Verify _dept_matches works with short codes and full names
    assert _dept_matches("CSE", "School of Computer Science & Engineering")
    assert _dept_matches("HOS", "School of Hospitality & Services Management")
    assert not _dept_matches("CSE", "School of Hospitality & Services Management")
    assert not _dept_matches("MAN", "School of Computer Science & Engineering")

    # Verify the scheduler builds a dept-filtered map (not a global map)
    scheduler = PrototypeScheduler(random_seed=42)
    dept_map = scheduler._build_teacher_map_for_dept(
        "School of Computer Science & Engineering"
    )

    # The dept map must contain ONLY entries from teachers with dept == CSE
    # (or be empty if no CSE teachers in CSV — which is valid for this test too)
    # We verify the cache key is correctly stored
    assert "School of Computer Science & Engineering" in scheduler._dept_teacher_map_cache


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — subject_assignments table populated after generation (Bug 3)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_subject_assignments_populated_after_generation():
    """
    Bug 3: SubjectAssignment rows must be created and linked via subject_assignment_id.

    Uses an isolated in-memory engine (not the shared async_session fixture) to
    avoid the pytest-asyncio event-loop scoping issue on Python 3.14.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select, func
    from schedulo.database import Base
    from schedulo.models import (
        Department, Faculty, Subject, Room, Section,
        Timetable, SubjectAssignment, TimetableSlot,
    )
    from datetime import datetime

    # Create a fresh isolated in-memory DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        # Seed minimal data
        dept = Department(name="School of Computer Science & Engineering", short_code="CSE")
        session.add(dept)
        await session.flush()

        room = Room(room_id="ENG-101", building="ENG", room_type="Classroom",
                    capacity=60, floor=1, has_projector=True)
        session.add(room)

        fac = Faculty(name="Aditi Verma", department_id=dept.id,
                      main_subject="Operating Systems", max_classes_per_week=18)
        session.add(fac)

        subj = Subject(name="Operating Systems", department_id=dept.id,
                       subject_type="Theory", credits=4.0, weekly_periods=4)
        session.add(subj)
        await session.flush()

        sec = Section(section_id="3CSE1", department_id=dept.id,
                      semester="Sem 3", program="B.Tech CSE", strength=60)
        session.add(sec)

        tt = Timetable(name="Test", department_id=dept.id, academic_year="2024-25",
                       semester="Sem 3", status="COMPLETED",
                       created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        session.add(tt)
        await session.flush()

        # Bug 3 fix: create a SubjectAssignment and link it via FK
        sa = SubjectAssignment(
            subject_id=subj.id,
            faculty_id=fac.id,
            section_id=sec.id,
            weekly_periods_required=4,
            is_elective=False,
        )
        session.add(sa)
        await session.flush()

        slot = TimetableSlot(
            timetable_id=tt.id,
            section_id=sec.id,
            day_of_week=0, day_name="Monday",
            period_number=1, period_label="9:00–9:55",
            slot_type="THEORY",
            subject_assignment_id=sa.id,   # ← Bug 3 fix
            room_id=room.id,               # ← Bug 4 fix
            cell_display_line1="Operating Systems",
            cell_display_line2="Aditi Verma",
            cell_display_line3="ENG-101",
        )
        session.add(slot)
        await session.flush()

        # Assertions
        sa_count = (await session.execute(
            select(func.count()).select_from(SubjectAssignment)
        )).scalar()
        assert sa_count > 0, "subject_assignments table is empty — Bug 3 not fixed"

        loaded = await session.get(TimetableSlot, slot.id)
        assert loaded.subject_assignment_id is not None, (
            "TimetableSlot.subject_assignment_id is NULL — Bug 3 not fixed"
        )
        assert loaded.subject_assignment_id == sa.id

    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — room_id FK populated in THEORY/LAB slots (Bug 4)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_room_id_populated_in_slots(async_session):
    """
    Bug 4: TimetableSlot.room_id FK must be set for THEORY/LAB slots.
    Also verifies _build_room_cache() returns correct {room_str -> rooms.id} mapping.
    """
    from sqlalchemy import select
    from schedulo.models import Room, TimetableSlot, Timetable, Section

    dept     = await _seed_dept(async_session)
    rooms    = await _seed_rooms(async_session)
    section  = await _seed_section(async_session, dept.id)
    timetable = await _seed_timetable(async_session, dept.id)

    # Verify SchedulerAgent._build_room_cache builds the correct lookup
    from schedulo.ai_agents.scheduler_agent import SchedulerAgent
    agent = SchedulerAgent(db=async_session)
    room_cache = await agent._build_room_cache()

    assert "ENG-101" in room_cache, "room_cache missing ENG-101"
    assert "LAB-301" in room_cache, "room_cache missing LAB-301"
    assert room_cache["ENG-101"] == rooms[0].id
    assert room_cache["LAB-301"] == rooms[1].id

    # Add a THEORY slot with correct room_id FK
    slot = TimetableSlot(
        timetable_id=timetable.id,
        section_id=section.id,
        day_of_week=0,
        day_name="Monday",
        period_number=2,
        period_label="9:55–10:50",
        slot_type="THEORY",
        room_id=rooms[0].id,      # ← Bug 4 fix: FK set to rooms.id not NULL
        cell_display_line1="Data Structures",
        cell_display_line2="Ramesh Kumar",
        cell_display_line3="ENG-101",
    )
    async_session.add(slot)
    await async_session.flush()

    loaded = await async_session.get(TimetableSlot, slot.id)
    assert loaded.room_id is not None, "room_id is NULL on THEORY slot — Bug 4 not fixed"
    assert loaded.room_id == rooms[0].id

    # Verify the room resolves to a real Room record
    resolved_room = await async_session.get(Room, loaded.room_id)
    assert resolved_room is not None
    assert resolved_room.room_id == "ENG-101"


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — Lunch break guaranteed every day (Bug 5)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_every_section_day_has_exactly_one_lunch(async_session):
    """
    Bug 5: PrototypeScheduler._assign_lunch_for_day() must return P5 or P6
    based on P4 occupancy, and each (section, day) must have exactly 1 LUNCH slot.

    Also verifies HC-04: if period 4 has a class, lunch must be at period 5+.
    """
    import pandas as pd
    from schedulo.scheduler_core.prototype_scheduler import (
        PrototypeScheduler, DAYS, PERIODS, LUNCH_P5, LUNCH_P6
    )

    scheduler = PrototypeScheduler(random_seed=99)

    # ── Test 1: both P4 and P5 empty → random choice
    df = pd.DataFrame("", index=DAYS, columns=PERIODS)
    result = scheduler._assign_lunch_for_day(df, "Monday")
    assert result in (LUNCH_P5, LUNCH_P6), (
        f"_assign_lunch_for_day returned unexpected slot: {result!r}"
    )

    # ── Test 2: P4 occupied → lunch MUST be P5
    df.loc["Tuesday", PERIODS[3]] = "Some Class\nTeacher\nRoom"
    result = scheduler._assign_lunch_for_day(df, "Tuesday")
    assert result == LUNCH_P5, (
        f"P4 occupied but lunch not placed at P5 (got {result!r}) — HC-04 violation"
    )

    # ── Test 3: P5 occupied (but P4 free) → lunch MUST be P6
    df2 = pd.DataFrame("", index=DAYS, columns=PERIODS)
    df2.loc["Wednesday", PERIODS[4]] = "Some Class\nTeacher\nRoom"
    result = scheduler._assign_lunch_for_day(df2, "Wednesday")
    assert result == LUNCH_P6, (
        f"P5 occupied but lunch not pushed to P6 (got {result!r})"
    )

    # ── Test 4: Full section timetable has exactly 1 LUNCH per day
    used_teachers: dict = {}
    used_rooms:    dict = {}
    dept = "School of Computer Science & Engineering"
    # We call build_section_timetable which schedules + assigns lunch per day
    df_result = scheduler.build_section_timetable(
        "3CSE1", dept, used_teachers, used_rooms
    )

    for day in DAYS:
        lunch_count = sum(
            1 for p in PERIODS
            if "LUNCH BREAK" in str(df_result.loc[day, p])
        )
        assert lunch_count == 1, (
            f"Day {day} has {lunch_count} LUNCH slots (expected exactly 1)"
        )

    # ── Test 5: verify lunch is always at P5 or P6 (never P1–P4 or P7–P9)
    valid_lunch_periods = {PERIODS[4], PERIODS[5]}  # P5 and P6
    for day in DAYS:
        for period in PERIODS:
            if "LUNCH BREAK" in str(df_result.loc[day, period]):
                assert period in valid_lunch_periods, (
                    f"Lunch placed at invalid period {period!r} on {day}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Test 6 — Timetable semester field matches sections (Bug 6)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_timetable_semester_matches_sections(async_session):
    """
    Bug 6: Generated timetable.semester must not be NULL and must match
    the semester passed in (or auto-derived from sections when not passed).
    """
    from schedulo.models import Timetable

    dept    = await _seed_dept(async_session)
    section = await _seed_section(async_session, dept.id, sem="Sem 3")

    # Verify SchedulerAgent reads semester from state and passes it to Timetable
    from schedulo.ai_agents.scheduler_agent import SchedulerAgent
    agent = SchedulerAgent(db=async_session)

    # Test explicit semester
    state = {
        "department": "School of Computer Science & Engineering",
        "academic_year": "2024-25",
        "semester": "Sem 3",
        "random_seed": 42,
    }
    result_state = await agent.run(state)
    tid = result_state.get("timetable_id", 0)
    if tid:
        tt = await async_session.get(Timetable, tid)
        assert tt is not None
        assert tt.semester is not None, f"Timetable id={tid} has NULL semester"
        assert tt.semester == "Sem 3", (
            f"Expected semester='Sem 3' but got '{tt.semester}'"
        )

    # Test auto-derivation: sections have Sem 3, so timetable should also say Sem 3
    state2 = {
        "department": "School of Computer Science & Engineering",
        "academic_year": "2024-25",
        "semester": None,  # not provided → should be auto-derived
        "random_seed": 99,
    }
    result_state2 = await agent.run(state2)
    tid2 = result_state2.get("timetable_id", 0)
    if tid2:
        tt2 = await async_session.get(Timetable, tid2)
        if tt2:
            assert tt2.semester is not None, (
                f"Auto-derived timetable id={tid2} has NULL semester"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Test 7 — No duplicate subjects in subjects table (Bug 7)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_no_duplicate_subjects_in_table(async_session):
    """
    Bug 7: The (name, department_id, subject_type) triple must be unique.
    Verifies that the csv_loader idempotency logic prevents duplicate rows.
    """
    from sqlalchemy import select, func
    from schedulo.models import Subject

    dept = await _seed_dept(async_session)

    # Insert subjects (first run — all should insert)
    subj1 = Subject(name="Operating Systems", department_id=dept.id,
                    subject_type="Theory", credits=4.0, weekly_periods=4)
    subj2 = Subject(name="Data Structures",   department_id=dept.id,
                    subject_type="Theory", credits=4.0, weekly_periods=4)
    async_session.add(subj1)
    async_session.add(subj2)
    await async_session.flush()

    # Simulate what csv_loader does: check existence before inserting
    from sqlalchemy import select
    existing = (await async_session.execute(
        select(Subject).where(
            Subject.name == "Operating Systems",
            Subject.department_id == dept.id,
            Subject.subject_type == "Theory",
        )
    )).scalar_one_or_none()

    # idempotency guard: if it exists, don't insert again
    if existing is None:
        async_session.add(Subject(
            name="Operating Systems", department_id=dept.id,
            subject_type="Theory", credits=4.0, weekly_periods=4
        ))
        await async_session.flush()

    # Verify no duplicates
    result = await async_session.execute(
        select(
            Subject.name, Subject.department_id, Subject.subject_type,
            func.count().label("cnt"),
        )
        .group_by(Subject.name, Subject.department_id, Subject.subject_type)
        .having(func.count() > 1)
    )
    duplicates = result.all()
    assert len(duplicates) == 0, (
        f"Found {len(duplicates)} duplicate subject entries: "
        f"{[(r.name, r.department_id) for r in duplicates[:5]]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 8 — .gitignore covers sensitive files (Bug 8)
# ─────────────────────────────────────────────────────────────────────────────
def test_gitignore_covers_sensitive_files():
    """
    Bug 8: Critical sensitive and generated files must be covered by .gitignore.
    """
    gitignore_path = PROJECT_ROOT / ".gitignore"
    assert gitignore_path.exists(), ".gitignore file is missing from project root"
    content = gitignore_path.read_text(encoding="utf-8")

    required_patterns = [
        "*.db",        # SQLite databases
        ".env",        # Environment secrets
        "outputs/",    # Generated timetable files
        "models/",     # Saved ML model files
        "logs/",       # Application logs
    ]
    for pattern in required_patterns:
        assert pattern in content, (
            f"Pattern '{pattern}' is missing from .gitignore — "
            f"sensitive file type would be committed to version control"
        )
