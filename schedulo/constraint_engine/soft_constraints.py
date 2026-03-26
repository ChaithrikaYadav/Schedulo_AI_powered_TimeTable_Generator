"""
schedulo/constraint_engine/soft_constraints.py
Implements all 8 Soft Constraints (SC-01 through SC-08) from the Schedulo spec.
Violations reduce the GA fitness score but do NOT make a timetable infeasible.
"""

from __future__ import annotations

from collections import Counter

from schedulo.constraint_engine.base import (
    BaseConstraint,
    ConstraintResult,
    ConstraintType,
    Severity,
    SlotCandidate,
)

AFTERNOON_PERIOD_INDICES = {4, 5, 6, 7, 8}   # Periods 5–9 (0-based: 4–8)
MORNING_PERIOD_INDICES = {0, 1, 2, 3}         # Periods 1–4 (0-based: 0–3)
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


# ─────────────────────────────────────────────────────────────────
# SC-01: FacultyPreferredDays
# ─────────────────────────────────────────────────────────────────
class SC01_FacultyPreferredDays(BaseConstraint):
    """Respect faculty's preferred teaching time slot preference."""

    constraint_id = "SC-01"
    constraint_type = ConstraintType.SOFT
    severity = Severity.LOW

    def __init__(self, faculty_prefs: dict[str, str]) -> None:
        """
        Args:
            faculty_prefs: faculty_id → preferred_slots (Morning|Afternoon|No 1st Period|Any)
        """
        self._prefs = faculty_prefs

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        pref = self._prefs.get(candidate.faculty_id, "Any")
        p = candidate.period_idx

        if pref == "Morning" and p in AFTERNOON_PERIOD_INDICES:
            return self._fail(
                f"Faculty {candidate.faculty_name} prefers morning slots but is assigned "
                f"to afternoon period {p + 1} on {candidate.day}.",
                penalty=5.0,
            )
        if pref == "Afternoon" and p in MORNING_PERIOD_INDICES:
            return self._fail(
                f"Faculty {candidate.faculty_name} prefers afternoon slots but is assigned "
                f"to morning period {p + 1} on {candidate.day}.",
                penalty=5.0,
            )
        if pref == "No 1st Period" and p == 0:
            return self._fail(
                f"Faculty {candidate.faculty_name} has 'No 1st Period' preference "
                f"but is assigned to Period 1 on {candidate.day}.",
                penalty=10.0,
            )
        return self._ok()

    def violation_message(self) -> str:
        return "SC-01: Faculty assigned outside preferred time slot"


# ─────────────────────────────────────────────────────────────────
# SC-02: RoomProximity
# ─────────────────────────────────────────────────────────────────
class SC02_RoomProximity(BaseConstraint):
    """
    Minimise room switches for the same section within a single day.
    A switch is penalised when the same section moves to a room in a different building.
    """

    constraint_id = "SC-02"
    constraint_type = ConstraintType.SOFT
    severity = Severity.LOW

    def _building(self, room_id: str) -> str:
        return room_id.split("-")[0] if "-" in room_id else room_id[:3]

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        same_day_rooms = [
            slot.room_id for slot in existing_slots
            if slot.section_id == candidate.section_id and slot.day == candidate.day
        ]
        if not same_day_rooms:
            return self._ok()

        candidate_building = self._building(candidate.room_id)
        switches = sum(
            1 for r in same_day_rooms
            if self._building(r) != candidate_building
        )
        if switches > 0:
            return self._fail(
                f"Section {candidate.section_id} would have to change buildings "
                f"{switches} time(s) on {candidate.day}.",
                penalty=float(switches) * 3.0,
            )
        return self._ok()

    def violation_message(self) -> str:
        return "SC-02: Section assigned to multiple buildings on the same day"


# ─────────────────────────────────────────────────────────────────
# SC-03: SubjectSpread
# ─────────────────────────────────────────────────────────────────
class SC03_SubjectSpread(BaseConstraint):
    """
    Occurrences of the same subject should be spread across different days
    rather than clustered (e.g. 3 classes of Math on Mon/Mon/Tue is bad).
    """

    constraint_id = "SC-03"
    constraint_type = ConstraintType.SOFT
    severity = Severity.INFO

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        same_subject_days = [
            slot.day for slot in existing_slots
            if slot.section_id == candidate.section_id
            and slot.subject_name == candidate.subject_name
            and not slot.extra.get("is_lab_continuation")
        ]

        if candidate.day in same_subject_days:
            existing_count_today = same_subject_days.count(candidate.day)
            return self._fail(
                f"Subject '{candidate.subject_name}' for {candidate.section_id} already "
                f"appears {existing_count_today}× on {candidate.day}. "
                f"Spread across different days.",
                penalty=8.0 * existing_count_today,
            )
        return self._ok()

    def violation_message(self) -> str:
        return "SC-03: Subject clustered on same day instead of spread across week"


# ─────────────────────────────────────────────────────────────────
# SC-04: LabAfternoonPreference
# ─────────────────────────────────────────────────────────────────
class SC04_LabAfternoonPreference(BaseConstraint):
    """
    Lab sessions are preferably scheduled in periods 5–9 (post-lunch, 0-based indices 4–8).
    Morning labs are allowed but penalised.
    """

    constraint_id = "SC-04"
    constraint_type = ConstraintType.SOFT
    severity = Severity.INFO

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        if candidate.subject_type != "Lab":
            return self._ok()
        if candidate.period_idx in MORNING_PERIOD_INDICES:
            return self._fail(
                f"Lab '{candidate.subject_name}' scheduled in morning (period {candidate.period_idx + 1}). "
                f"Labs are preferred in afternoon (periods 5–9).",
                penalty=4.0,
            )
        return self._ok()

    def violation_message(self) -> str:
        return "SC-04: Lab scheduled in morning instead of afternoon"


# ─────────────────────────────────────────────────────────────────
# SC-05: FacultyWorkloadBalance
# ─────────────────────────────────────────────────────────────────
class SC05_FacultyWorkloadBalance(BaseConstraint):
    """
    Distribute a faculty's classes evenly across the week rather than
    front-loading Monday–Wednesday. Each day should have at most
    ceil(total_weekly / num_teaching_days) classes.
    """

    constraint_id = "SC-05"
    constraint_type = ConstraintType.SOFT
    severity = Severity.INFO

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        fid = candidate.faculty_id
        day_counts: Counter[str] = Counter(
            slot.day for slot in existing_slots if slot.faculty_id == fid
        )
        current_day_load = day_counts.get(candidate.day, 0)
        total_load = sum(day_counts.values())

        # Allow at most 3 classes per day before flagging imbalance
        if current_day_load >= 3 and total_load > 6:
            return self._fail(
                f"Faculty {candidate.faculty_name} already has {current_day_load} classes "
                f"on {candidate.day}. Consider spreading across other days.",
                penalty=6.0,
            )
        return self._ok()

    def violation_message(self) -> str:
        return "SC-05: Faculty workload front-loaded on specific days"


# ─────────────────────────────────────────────────────────────────
# SC-06: SeniorFacultySlotPreference
# ─────────────────────────────────────────────────────────────────
class SC06_SeniorFacultySlotPreference(BaseConstraint):
    """
    Faculty with designation PROFESSOR or ASSOCIATE_PROFESSOR should get
    lighter morning loads where possible (prefer not to have more than
    2 morning classes per week).
    """

    constraint_id = "SC-06"
    constraint_type = ConstraintType.SOFT
    severity = Severity.INFO

    def __init__(self, senior_faculty_ids: set[str]) -> None:
        self._seniors = senior_faculty_ids

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        if candidate.faculty_id not in self._seniors:
            return self._ok()

        morning_count = sum(
            1 for slot in existing_slots
            if slot.faculty_id == candidate.faculty_id
            and slot.period_idx in MORNING_PERIOD_INDICES
        )

        if candidate.period_idx in MORNING_PERIOD_INDICES and morning_count >= 2:
            return self._fail(
                f"Senior faculty {candidate.faculty_name} already has {morning_count} morning "
                f"classes this week. Prefer afternoon slots.",
                penalty=3.0,
            )
        return self._ok()

    def violation_message(self) -> str:
        return "SC-06: Senior faculty given excess morning load"


# ─────────────────────────────────────────────────────────────────
# SC-07: ConsecutiveClassLimit
# ─────────────────────────────────────────────────────────────────
class SC07_ConsecutiveClassLimit(BaseConstraint):
    """
    No faculty or section should have more than 4 consecutive periods
    without a free/lunch period in between.
    """

    constraint_id = "SC-07"
    constraint_type = ConstraintType.SOFT
    severity = Severity.MEDIUM

    MAX_CONSECUTIVE = 4

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        # Build a set of occupied period indices for this section on this day
        occupied = {
            slot.period_idx for slot in existing_slots
            if slot.section_id == candidate.section_id
            and slot.day == candidate.day
            and not slot.extra.get("is_lunch")
        }
        occupied.add(candidate.period_idx)

        # Find the run length including the candidate
        run = 1
        # Look backward
        p = candidate.period_idx - 1
        while p >= 0 and p in occupied:
            run += 1
            p -= 1
        # Look forward
        p = candidate.period_idx + 1
        while p < 9 and p in occupied:
            run += 1
            p += 1

        if run > self.MAX_CONSECUTIVE:
            return self._fail(
                f"Section {candidate.section_id} would have {run} consecutive classes "
                f"on {candidate.day} (max allowed: {self.MAX_CONSECUTIVE}).",
                penalty=7.0 * (run - self.MAX_CONSECUTIVE),
            )
        return self._ok()

    def violation_message(self) -> str:
        return "SC-07: More than 4 consecutive classes without a break"


# ─────────────────────────────────────────────────────────────────
# SC-08: FirstPeriodPreference
# ─────────────────────────────────────────────────────────────────
class SC08_FirstPeriodPreference(BaseConstraint):
    """
    Core/mandatory subjects are preferably not scheduled in the last period
    of the day (Period 9, index 8) due to lower student engagement.
    """

    constraint_id = "SC-08"
    constraint_type = ConstraintType.SOFT
    severity = Severity.INFO

    LAST_PERIOD_IDX = 8  # Period 9: "4:20–5:15"

    # Subject names that are considered "core" and should avoid last period
    CORE_SUBJECT_KEYWORDS = {
        "mathematics", "physics", "data structures", "algorithms",
        "software engineering", "machine learning", "operating system",
        "networks", "database", "programming",
    }

    def _is_core(self, subject_name: str) -> bool:
        lower = subject_name.lower()
        return any(kw in lower for kw in self.CORE_SUBJECT_KEYWORDS)

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        if candidate.period_idx == self.LAST_PERIOD_IDX and self._is_core(candidate.subject_name):
            return self._fail(
                f"Core subject '{candidate.subject_name}' scheduled in last period "
                f"({candidate.period_idx + 1}) on {candidate.day}. "
                f"Prefer earlier periods for core subjects.",
                penalty=5.0,
            )
        return self._ok()

    def violation_message(self) -> str:
        return "SC-08: Core subject scheduled in last period of day"


# ─────────────────────────────────────────────────────────────────
# Factory: build default soft constraint set
# ─────────────────────────────────────────────────────────────────
def build_default_soft_constraints(
    faculty_prefs: dict[str, str] | None = None,
    senior_faculty_ids: set[str] | None = None,
) -> list[BaseConstraint]:
    """
    Build and return all 8 soft constraints.

    Args:
        faculty_prefs:      faculty_id → preferred_slots string
        senior_faculty_ids: set of faculty_ids with PROFESSOR/ASSOCIATE designation
    """
    return [
        SC01_FacultyPreferredDays(faculty_prefs or {}),
        SC02_RoomProximity(),
        SC03_SubjectSpread(),
        SC04_LabAfternoonPreference(),
        SC05_FacultyWorkloadBalance(),
        SC06_SeniorFacultySlotPreference(senior_faculty_ids or set()),
        SC07_ConsecutiveClassLimit(),
        SC08_FirstPeriodPreference(),
    ]
