"""
schedulo/ai_agents/scheduler_agent.py
SchedulerAgent — LangGraph node that runs the AlgorithmicSchedulerEngine and
persists generated timetable slots into the database.

Algorithms used (via AlgorithmicSchedulerEngine):
  Phase 1: Demand Builder (deterministic semester-appropriate subject selection)
  Phase 2: Multi-Level Queue + Longest Job First (Lab > Theory > Project)
  Phase 3: Greedy Weighted Faculty Matching (department filter + fuzzy subject match)
  Phase 4: Weighted Interval Scheduling DP (labs) + Round-Robin Spread (theory)
  Phase 5: First Fit Decreasing Bin Packing (rooms)
  Phase 6: Round-Robin Rebalance + HC-04 Lunch Enforcement

Bug fixes preserved:
  ✅ BUG 3 — SubjectAssignment rows created and linked via subject_assignment_id FK
  ✅ BUG 4 — room_id FK resolved via room_cache
  ✅ BUG 6 — semester threaded through from orchestrator state
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Day-name → integer for day_of_week column
_DAY_TO_INT: dict[str, int] = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2,
    "Thursday": 3, "Friday": 4, "Saturday": 5,
}


@dataclass
class SchedulerResult:
    timetable_id: int
    sections_generated: list[str] = field(default_factory=list)
    total_slots: int = 0
    errors: list[str] = field(default_factory=list)
    success: bool = True

    def to_state(self) -> dict[str, Any]:
        return {
            "timetable_id": self.timetable_id,
            "scheduler_sections": self.sections_generated,
            "scheduler_total_slots": self.total_slots,
            "scheduler_errors": self.errors,
            "scheduler_success": self.success,
        }


class SchedulerAgent:
    """
    LangGraph node that:
      1. Runs AlgorithmicSchedulerEngine.build_all() for the requested department
      2. Persists the resulting ScheduledSlot list as TimetableSlot rows
      3. Creates SubjectAssignment rows and links them (Bug 3 fix)
      4. Populates room_id FK on each slot (Bug 4 fix)
      5. Sets semester correctly on the Timetable record (Bug 6 fix)

    Wiring:
        builder.add_node("generate_timetable", SchedulerAgent(db).run)
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        State expects:
            department: str          — full department name
            random_seed: int|None    — kept for API compatibility (engine is deterministic)
            academic_year: str       — e.g. "2024-25"
            semester: str|None       — e.g. "Sem 3" (Bug 6 fix)
        """
        dept          = state.get("department", "School of Computer Science & Engineering")
        seed          = state.get("random_seed")   # retained for API compat; not used by engine
        academic_year = state.get("academic_year", "2024-25")
        semester      = state.get("semester")       # BUG 6 FIX: read from state

        logger.info(f"SchedulerAgent: generating for {dept} {semester or '(all semesters)'}")
        result = await self._generate(dept, seed, academic_year, semester)
        logger.info(
            f"SchedulerAgent: timetable_id={result.timetable_id}, "
            f"sections={len(result.sections_generated)}, slots={result.total_slots}"
        )
        return {**state, **result.to_state()}

    # ── Cache builders (Bug 3 + 4 helpers) ────────────────────────────────────
    async def _build_subject_cache(self, department_id: int) -> dict[str, Any]:
        """Returns {subject_name: Subject} for the given department, deduplicated."""
        from schedulo.models import Subject
        from sqlalchemy import select
        result = await self._db.execute(
            select(Subject).where(Subject.department_id == department_id)
        )
        cache: dict[str, Any] = {}
        for subj in result.scalars().all():
            if subj.name not in cache:
                cache[subj.name] = subj
        return cache

    async def _build_faculty_cache(self, department_id: int) -> dict[str, Any]:
        """Returns {faculty_name: Faculty} for the given department."""
        from schedulo.models import Faculty
        from sqlalchemy import select
        result = await self._db.execute(
            select(Faculty).where(Faculty.department_id == department_id)
        )
        return {f.name: f for f in result.scalars().all()}

    async def _build_room_cache(self) -> dict[str, int]:
        """Returns {room_id_string: rooms.id} for FK lookup."""
        from schedulo.models import Room
        from sqlalchemy import select
        result = await self._db.execute(select(Room))
        return {r.room_id: r.id for r in result.scalars().all()}

    # ── Core generation ────────────────────────────────────────────────────────
    async def _generate(
        self,
        department: str,
        seed: int | None,
        academic_year: str,
        semester: str | None = None,
    ) -> SchedulerResult:
        if not self._db:
            return SchedulerResult(
                timetable_id=0,
                success=False,
                errors=["No DB session provided to SchedulerAgent"],
            )

        from schedulo.models import (
            Department, Faculty, Room, Section, Subject,
            SubjectAssignment, Timetable, TimetableSlot,
        )
        from schedulo.scheduler_core.engine import AlgorithmicSchedulerEngine
        from schedulo.scheduler_core.models import SlotType
        from sqlalchemy import select

        try:
            # ── Resolve department_id ──────────────────────────────
            dept_result = await self._db.execute(
                select(Department).where(Department.name == department)
            )
            dept_obj = dept_result.scalar_one_or_none()
            dept_id: int | None = dept_obj.id if dept_obj else None

            # ── BUG 6 FIX: Derive semester from sections if not provided ──
            if not semester and dept_id:
                sem_result = await self._db.execute(
                    select(Section.semester)
                    .where(Section.department_id == dept_id)
                    .distinct()
                )
                semesters = [r[0] for r in sem_result.fetchall() if r[0]]
                if len(semesters) == 1:
                    semester = semesters[0]
                elif len(semesters) > 1:
                    semester = "Mixed"
                else:
                    semester = None

            # ── Create Timetable record ──────────────────────────
            timetable = Timetable(
                name=f"{department} — {academic_year} ({semester or 'All Sems'})",
                department_id=dept_id,
                academic_year=academic_year,
                semester=semester,              # BUG 6 FIX
                status="generating",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self._db.add(timetable)
            await self._db.flush()
            timetable_id = timetable.id

            # ── Load data for AlgorithmicSchedulerEngine ──────────
            sections_res = await self._db.execute(
                select(Section).where(Section.department_id == dept_id)
            )
            all_sections = sections_res.scalars().all()

            subjects_res = await self._db.execute(
                select(Subject).where(Subject.department_id == dept_id)
            )
            all_subjects = subjects_res.scalars().all()

            faculty_res = await self._db.execute(
                select(Faculty).where(Faculty.department_id == dept_id)
            )
            all_faculty = faculty_res.scalars().all()

            rooms_res = await self._db.execute(select(Room))
            all_rooms = rooms_res.scalars().all()

            # ── Run AlgorithmicSchedulerEngine (no random_seed — deterministic) ──
            engine = AlgorithmicSchedulerEngine(
                sections=all_sections,
                subjects=all_subjects,
                faculty=all_faculty,
                rooms=all_rooms,
            )
            timetables_dict = engine.build_all(department=department)
            # timetables_dict: {section_id_str: list[ScheduledSlot]}

            total_slots = 0
            sections_generated: list[str] = []

            # BUG 4 FIX: Build room cache once for the entire run
            room_cache = await self._build_room_cache()

            for section_id_str, slot_list in timetables_dict.items():
                # Lookup section DB record
                sec_result = await self._db.execute(
                    select(Section).where(Section.section_id == section_id_str)
                )
                section = sec_result.scalar_one_or_none()
                section_pk: int | None = section.id if section else None

                # BUG 3+4 FIX: Build subject and faculty name caches
                section_dept_id = section.department_id if section else dept_id
                subj_cache: dict[str, Any] = {}
                fac_cache: dict[str, Any] = {}
                if section_dept_id:
                    subj_cache = await self._build_subject_cache(section_dept_id)
                    fac_cache  = await self._build_faculty_cache(section_dept_id)

                # BUG 3 FIX: Track (subject_id, faculty_id, section_id) → SubjectAssignment.id
                assignment_cache: dict[tuple[int, int, int], int] = {}

                for slot in slot_list:
                    # ── BUG 3+4 FIX: Resolve SubjectAssignment and room_id ──
                    subj_assignment_id: int | None = None
                    room_pk: int | None = slot.room_pk  # already resolved by engine

                    # Fallback: resolve from room_cache string if room_pk is None
                    if room_pk is None and slot.room_id_str:
                        room_pk = room_cache.get(slot.room_id_str)

                    if slot.slot_type in (SlotType.THEORY, SlotType.LAB, SlotType.PROJECT):
                        subj_obj = subj_cache.get(slot.subject_name)
                        fac_obj  = fac_cache.get(slot.faculty_name)

                        if subj_obj and fac_obj and section_pk:
                            key = (subj_obj.id, fac_obj.id, section_pk)
                            if key not in assignment_cache:
                                sa = SubjectAssignment(
                                    subject_id=subj_obj.id,
                                    faculty_id=fac_obj.id,
                                    section_id=section_pk,
                                    weekly_periods_required=subj_obj.weekly_periods or 1,
                                    is_elective=False,
                                )
                                self._db.add(sa)
                                await self._db.flush()
                                assignment_cache[key] = sa.id
                            subj_assignment_id = assignment_cache[key]

                    self._db.add(TimetableSlot(
                        timetable_id=timetable_id,
                        section_id=section_pk,
                        day_of_week=slot.day_of_week,
                        day_name=slot.day_name,
                        period_number=slot.period_number,
                        period_label=slot.period_label,
                        slot_type=slot.slot_type.value,          # SlotType → str
                        subject_assignment_id=subj_assignment_id,  # BUG 3 FIX
                        room_id=room_pk,                           # BUG 4 FIX
                        is_lab_continuation=slot.is_lab_continuation,
                        cell_display_line1=slot.subject_name,
                        cell_display_line2=slot.faculty_name,
                        cell_display_line3=slot.room_id_str,
                    ))
                    total_slots += 1

                sections_generated.append(section_id_str)

            # Update timetable status
            timetable.status = "COMPLETED"
            timetable.updated_at = datetime.utcnow()
            await self._db.commit()

            return SchedulerResult(
                timetable_id=timetable_id,
                sections_generated=sections_generated,
                total_slots=total_slots,
                success=True,
            )

        except Exception as exc:
            logger.exception("SchedulerAgent: generation failed")
            await self._db.rollback()
            return SchedulerResult(
                timetable_id=0,
                success=False,
                errors=[str(exc)],
            )
