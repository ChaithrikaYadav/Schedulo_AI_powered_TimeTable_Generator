"""
schedulo/scheduler_core/engine.py
AlgorithmicSchedulerEngine — main entry-point replacing PrototypeScheduler.

Orchestrates all 6 phases:
  Phase 1: Demand Builder      (phase1_demand.py)
  Phase 2: MLQ + LJF Priority  (phase2_priority.py)
  Phase 3: Greedy Faculty      (phase3_faculty.py)
  Phase 4: Interval Slot Alloc (phase4_slots.py)
  Phase 5: FFD Room Assign     (phase5_rooms.py)
  Phase 6: RR Rebalance + HC-04 Lunch (phase6_balance.py)

Shared faculty_pool and room_pool are used across ALL sections so that
HC-01 (no room double-booking) and HC-02 (no faculty double-booking)
are enforced globally, not just per-section.

Usage (from SchedulerAgent._generate()):
    engine = AlgorithmicSchedulerEngine(sections, subjects, faculty, rooms)
    result = engine.build_all(department)
    # result: dict[section_id_str, list[ScheduledSlot]]
"""

from __future__ import annotations

import logging
from typing import Any

from schedulo.scheduler_core.models import (
    FacultySlot,
    RoomSlot,
    ScheduledSlot,
    SlotType,
)
from schedulo.scheduler_core.phase1_demand import build_demands
from schedulo.scheduler_core.phase2_priority import order_demands
from schedulo.scheduler_core.phase3_faculty import assign_faculty
from schedulo.scheduler_core.phase4_slots import (
    DAY_NAMES,
    PERIOD_LABELS,
    find_best_lab_slot,
    find_theory_slots,
)
from schedulo.scheduler_core.phase5_rooms import first_fit_room
from schedulo.scheduler_core.phase6_balance import (
    assign_lunch_all_days,
    validate_and_rebalance_spread,
)

logger = logging.getLogger(__name__)


class AlgorithmicSchedulerEngine:
    """
    Deterministic, attribute-driven timetable generator.
    Replaces PrototypeScheduler. Zero randomization.
    """

    def __init__(
        self,
        sections:  list[Any],   # SQLAlchemy Section ORM objects
        subjects:  list[Any],   # SQLAlchemy Subject ORM objects
        faculty:   list[Any],   # SQLAlchemy Faculty ORM objects
        rooms:     list[Any],   # SQLAlchemy Room ORM objects
    ) -> None:
        self.sections    = sections
        self.subjects    = subjects
        self.raw_faculty = faculty
        self.raw_rooms   = rooms

    # ── Public entry-point ────────────────────────────────────────────────────

    def build_all(self, department: str) -> dict[str, list[ScheduledSlot]]:
        """
        Generate timetables for all sections in the given department.

        Returns:
            {section_id_str: [ScheduledSlot, ...]} — one list per section.
            Slots include THEORY, LAB, LUNCH, and FREE types.
        """
        # Build shared pools — one instance per run, shared across all sections
        # so HC-01 (room single occupancy) and HC-02 (faculty no double-booking)
        # are enforced globally.
        faculty_pool = self._build_faculty_pool()
        room_pool    = self._build_room_pool()

        # Determine department_id from the first matching section
        dept_id = self._resolve_dept_id(department)

        dept_sections = sorted(
            [s for s in self.sections
             if s.department_id == dept_id
             or (dept_id is None)],   # fallback: include all if dept_id can't be resolved
            key=lambda s: s.section_id,
        )

        if not dept_sections:
            logger.warning(f"AlgorithmicSchedulerEngine: no sections found for '{department}'")
            return {}

        logger.info(
            f"AlgorithmicSchedulerEngine: {len(dept_sections)} sections for '{department}'"
        )

        results: dict[str, list[ScheduledSlot]] = {}

        for section in dept_sections:
            logger.info(f"  Scheduling {section.section_id}...")
            section_slots = self._schedule_section(
                section, faculty_pool, room_pool
            )
            results[section.section_id] = section_slots
            logger.info(f"  [{section.section_id}] → {len(section_slots)} slots")

        return results

    # ── Per-section scheduling ─────────────────────────────────────────────────

    def _schedule_section(
        self,
        section: Any,
        faculty_pool: list[FacultySlot],
        room_pool: list[RoomSlot],
    ) -> list[ScheduledSlot]:
        """Run all 6 phases for one section. Returns list of ScheduledSlot."""

        # Phase 1: Build subject demands for this section
        dept_subjects = [
            s for s in self.subjects
            if s.department_id == section.department_id
        ]
        demands = build_demands(section, dept_subjects)
        if not demands:
            return []

        # Phase 2: Order demands (MLQ + LJF)
        ordered_demands = order_demands(demands)

        # Section-level schedule: (day, period) → ScheduledSlot
        section_schedule: dict[tuple[int, int], ScheduledSlot] = {}

        section_strength = int(getattr(section, "strength", 60) or 60)

        for demand in ordered_demands:
            # Phase 3: Assign faculty (greedy matching)
            faculty = assign_faculty(demand, faculty_pool)
            faculty_name = faculty.name if faculty else "TBA"
            faculty_id   = faculty.faculty_id if faculty else None
            algo_prefix  = (
                f"Phase2-MLQ[{demand.subject_type},p={demand.priority_score:.0f}]"
                f"+Phase3-Greedy"
            )

            if demand.subject_type.strip().lower() == "lab":
                # Phase 4a: Lab slot (2 consecutive periods in a Lab room)
                lab_result = find_best_lab_slot(
                    demand, faculty, room_pool, section_schedule
                )
                if lab_result:
                    day, period_start, lab_room = lab_result
                    for i, period in enumerate([period_start, period_start + 1]):
                        is_cont = (i == 1)
                        slot = ScheduledSlot(
                            section_id=section.id,
                            section_str=section.section_id,
                            day_of_week=day,
                            day_name=DAY_NAMES[day],
                            period_number=period,
                            period_label=PERIOD_LABELS.get(period, f"P{period}"),
                            slot_type=SlotType.LAB,
                            subject_id=demand.subject_id,
                            subject_name=demand.subject_name,
                            faculty_id=faculty_id,
                            faculty_name=faculty_name,
                            room_pk=lab_room.room_pk,
                            room_id_str=lab_room.room_id_str,
                            is_lab_continuation=is_cont,
                            algorithm_used=algo_prefix + "+Phase4-LabDP+Phase5-FFD",
                        )
                        section_schedule[(day, period)] = slot
                        lab_room.occupy(day, period)
                        if faculty:
                            faculty.assigned_slots.append((day, period))
                else:
                    logger.warning(
                        f"  Could not place lab '{demand.subject_name}' "
                        f"for section {section.section_id}"
                    )

            else:
                # Phase 4b: Theory / Project (round-robin spread)
                slot_type = (
                    SlotType.THEORY if demand.subject_type.strip().lower() == "theory"
                    else SlotType.PROJECT
                )
                theory_slots = find_theory_slots(
                    demand, faculty, room_pool, section_schedule
                )
                for day, period, room in theory_slots:
                    slot = ScheduledSlot(
                        section_id=section.id,
                        section_str=section.section_id,
                        day_of_week=day,
                        day_name=DAY_NAMES[day],
                        period_number=period,
                        period_label=PERIOD_LABELS.get(period, f"P{period}"),
                        slot_type=slot_type,
                        subject_id=demand.subject_id,
                        subject_name=demand.subject_name,
                        faculty_id=faculty_id,
                        faculty_name=faculty_name,
                        room_pk=room.room_pk,
                        room_id_str=room.room_id_str,
                        algorithm_used=algo_prefix + "+Phase4-Theory+Phase6-RR",
                    )
                    section_schedule[(day, period)] = slot

        # Phase 6a: Round-Robin spread rebalancing
        section_schedule = validate_and_rebalance_spread(section_schedule)

        # Phase 6b: Deterministic HC-04 lunch per day
        section_schedule = assign_lunch_all_days(
            section_schedule, section.id, section.section_id
        )

        return list(section_schedule.values())

    # ── Pool builders ─────────────────────────────────────────────────────────

    def _build_faculty_pool(self) -> list[FacultySlot]:
        return [
            FacultySlot(
                faculty_id=f.id,
                name=str(f.name or ""),
                department_id=int(f.department_id or 0),
                main_subject=str(f.main_subject or ""),
                backup_subject=str(f.backup_subject or f.subject_handled or ""),
                max_classes_per_week=int(f.max_classes_per_week or 18),
                preferred_slots=str(f.preferred_slots or "Any"),
                can_take_labs=bool(f.can_take_labs),
            )
            for f in self.raw_faculty
        ]

    def _build_room_pool(self) -> list[RoomSlot]:
        return [
            RoomSlot(
                room_pk=r.id,
                room_id_str=str(r.room_id),
                room_type=str(r.room_type or "Classroom"),
                building=str(r.building or ""),
                capacity=int(r.capacity or 60),
            )
            for r in self.raw_rooms
        ]

    def _resolve_dept_id(self, department_name: str) -> int | None:
        """Find department_id by matching department name against sections."""
        # Try to find a section whose department relationship has this name
        for section in self.sections:
            dept = getattr(section, "department", None)
            if dept and getattr(dept, "name", None) == department_name:
                return section.department_id
        # Fallback: return the first section's dept_id (single-dept runs)
        if self.sections:
            return self.sections[0].department_id
        return None
