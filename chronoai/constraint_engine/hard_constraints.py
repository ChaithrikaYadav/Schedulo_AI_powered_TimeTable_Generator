"""
chronoai/constraint_engine/hard_constraints.py
Implements all 8 Hard Constraints (HC-01 through HC-08) from the ChronoAI spec.
Each class inherits from BaseConstraint and implements check() to validate a candidate slot.

Hard constraints are NEVER allowed to be violated. A timetable with any HC violation
is considered infeasible and will not be accepted.
"""

from __future__ import annotations

from chronoai.constraint_engine.base import (
    BaseConstraint,
    ConstraintResult,
    ConstraintType,
    Severity,
    SlotCandidate,
)

# Canonical period labels — must match timetable_generator.py exactly
PERIODS = [
    "9:00–9:55",    # Period 1  (index 0)
    "9:55–10:50",   # Period 2  (index 1)
    "10:50–11:45",  # Period 3  (index 2)
    "11:45–12:40",  # Period 4  (index 3)
    "12:40–1:35",   # Period 5  (index 4) — first lunch option
    "1:35–2:30",    # Period 6  (index 5) — second lunch option
    "2:30–3:25",    # Period 7  (index 6)
    "3:25–4:20",    # Period 8  (index 7)
    "4:20–5:15",    # Period 9  (index 8)
]

# Periods 4→5 cannot form a consecutive lab pair (straddles lunch break)
INVALID_LAB_START_INDICES = {3}  # index 3 = "11:45–12:40"

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


# ─────────────────────────────────────────────────────────────────
# HC-01: RoomSingleOccupancy
# ─────────────────────────────────────────────────────────────────
class HC01_RoomSingleOccupancy(BaseConstraint):
    """
    No two different sections may be assigned the same room at the same day+period.
    Exception: same subject split across G1/G2 of the same section.
    """

    constraint_id = "HC-01"
    constraint_type = ConstraintType.HARD
    severity = Severity.CRITICAL

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        for slot in existing_slots:
            if (
                slot.day == candidate.day
                and slot.period_idx == candidate.period_idx
                and slot.room_id == candidate.room_id
                and slot.room_id != ""
                # Allow same-section G1/G2 splits to share slot row but not room
                and not (
                    slot.section_id == candidate.section_id
                    and slot.extra.get("lab_group") != candidate.extra.get("lab_group")
                )
            ):
                return self._fail(
                    f"Room {candidate.room_id} is already occupied by "
                    f"{slot.section_id} ({slot.subject_name}) on {candidate.day} "
                    f"period {candidate.period_idx + 1}.",
                    auto_fixable=True,
                )
        return self._ok()

    def violation_message(self) -> str:
        return "HC-01: Room double-booking detected"


# ─────────────────────────────────────────────────────────────────
# HC-02: FacultyNoDoubleBooking
# ─────────────────────────────────────────────────────────────────
class HC02_FacultyNoDoubleBooking(BaseConstraint):
    """
    A faculty member cannot be assigned to two different slots on the same day and period.
    Validated across ALL sections simultaneously.
    """

    constraint_id = "HC-02"
    constraint_type = ConstraintType.HARD
    severity = Severity.CRITICAL

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        if not candidate.faculty_id or candidate.faculty_id == "TBA":
            return self._ok()

        for slot in existing_slots:
            if (
                slot.day == candidate.day
                and slot.period_idx == candidate.period_idx
                and slot.faculty_id == candidate.faculty_id
                and slot.section_id != candidate.section_id
            ):
                return self._fail(
                    f"Faculty {candidate.faculty_name} ({candidate.faculty_id}) is already "
                    f"assigned to {slot.section_id} ({slot.subject_name}) on "
                    f"{candidate.day} period {candidate.period_idx + 1}.",
                    auto_fixable=True,
                )
        return self._ok()

    def violation_message(self) -> str:
        return "HC-02: Faculty double-booking detected"


# ─────────────────────────────────────────────────────────────────
# HC-03: LaboratoryConsecutiveSlots
# ─────────────────────────────────────────────────────────────────
class HC03_LaboratoryConsecutiveSlots(BaseConstraint):
    """
    Any LAB subject must occupy exactly two consecutive periods.
    The room must be identical for both periods.
    Periods 4→5 (index 3→4) are invalid for lab start (straddles lunch break).
    """

    constraint_id = "HC-03"
    constraint_type = ConstraintType.HARD
    severity = Severity.CRITICAL

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        if candidate.subject_type != "Lab":
            return self._ok()

        if not candidate.is_lab_pair:
            return self._fail(
                f"Lab subject '{candidate.subject_name}' assigned to a single period "
                f"(period {candidate.period_idx + 1}). Labs must be 2 consecutive periods.",
                auto_fixable=True,
            )

        p_idx = candidate.period_idx
        p_idx_next = candidate.lab_pair_idx

        # Must be consecutive
        if p_idx_next != p_idx + 1:
            return self._fail(
                f"Lab '{candidate.subject_name}' pair periods {p_idx + 1} and {p_idx_next + 1} "
                f"are not consecutive.",
                auto_fixable=True,
            )

        # Cannot straddle lunch break (period 4 → 5, i.e., index 3 → 4)
        if p_idx in INVALID_LAB_START_INDICES:
            return self._fail(
                f"Lab '{candidate.subject_name}' cannot start at period {p_idx + 1} "
                f"({PERIODS[p_idx]}) because the continuation would straddle the lunch break.",
                auto_fixable=True,
            )

        # Cannot start at last period (no continuation slot)
        if p_idx >= len(PERIODS) - 1:
            return self._fail(
                f"Lab '{candidate.subject_name}' cannot start at the last period of the day.",
                auto_fixable=True,
            )

        return self._ok()

    def violation_message(self) -> str:
        return "HC-03: Lab not assigned to two consecutive periods"


# ─────────────────────────────────────────────────────────────────
# HC-04: LunchBreakEnforcement
# ─────────────────────────────────────────────────────────────────
class HC04_LunchBreakEnforcement(BaseConstraint):
    """
    Each section must have at least one free period covering the lunch window.
    The lunch slot (either period 5="12:40–1:35" or period 6="1:35–2:30") must remain empty.
    Per section, ONE lunch slot is fixed for the entire week.
    """

    constraint_id = "HC-04"
    constraint_type = ConstraintType.HARD
    severity = Severity.HIGH

    LUNCH_PERIOD_INDICES = {4, 5}  # "12:40–1:35" and "1:35–2:30"

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        if candidate.period_idx not in self.LUNCH_PERIOD_INDICES:
            return self._ok()

        # Determine which lunch slot this section has already committed to
        section_lunch_slots = {
            slot.period_idx
            for slot in existing_slots
            if slot.section_id == candidate.section_id and slot.extra.get("is_lunch")
        }

        # If a lunch slot is already assigned to this period for this section, block it
        if candidate.period_idx in section_lunch_slots:
            return self._fail(
                f"Section {candidate.section_id} has period {candidate.period_idx + 1} "
                f"({PERIODS[candidate.period_idx]}) reserved as lunch break.",
                auto_fixable=False,
            )

        # Check if BOTH lunch periods are already occupied (no lunch would be possible)
        occupied_lunch = {
            slot.period_idx
            for slot in existing_slots
            if (
                slot.section_id == candidate.section_id
                and slot.day == candidate.day
                and slot.period_idx in self.LUNCH_PERIOD_INDICES
                and not slot.extra.get("is_lunch")
            )
        }
        if len(occupied_lunch) >= 1 and candidate.period_idx in occupied_lunch:
            return self._fail(
                f"Scheduling '{candidate.subject_name}' at period {candidate.period_idx + 1} "
                f"on {candidate.day} would eliminate section {candidate.section_id}'s lunch break.",
                auto_fixable=True,
            )

        return self._ok()

    def violation_message(self) -> str:
        return "HC-04: Lunch break eliminated for a section"


# ─────────────────────────────────────────────────────────────────
# HC-05: FacultyWeeklyHourLimit
# ─────────────────────────────────────────────────────────────────
class HC05_FacultyWeeklyHourLimit(BaseConstraint):
    """
    The total number of periods assigned to a faculty member per week must not exceed
    their max_classes_per_week value (range 12–18 in the dataset).
    Labs count as 2 periods = 2 hours.
    """

    constraint_id = "HC-05"
    constraint_type = ConstraintType.HARD
    severity = Severity.HIGH

    def __init__(self, faculty_limits: dict[str, int]) -> None:
        """
        Args:
            faculty_limits: Mapping of faculty_id → max_classes_per_week
        """
        self._limits = faculty_limits

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        fid = candidate.faculty_id
        max_hours = self._limits.get(fid, 18)  # default 18 if not found

        # Count existing assigned periods for this faculty this week
        assigned = sum(1 for slot in existing_slots if slot.faculty_id == fid)

        # Labs will add 2 periods
        cost = 2 if candidate.is_lab_pair else 1

        if assigned + cost > max_hours:
            return self._fail(
                f"Faculty {candidate.faculty_name} ({fid}) would exceed weekly limit: "
                f"{assigned} + {cost} = {assigned + cost} > {max_hours}.",
                auto_fixable=False,
            )
        return self._ok()

    def violation_message(self) -> str:
        return "HC-05: Faculty weekly hour limit exceeded"


# ─────────────────────────────────────────────────────────────────
# HC-06: LabRoomTypeMatch
# ─────────────────────────────────────────────────────────────────
class HC06_LabRoomTypeMatch(BaseConstraint):
    """
    LAB subjects must be assigned to rooms with room_type = 'Lab'.
    Theory subjects should not occupy lab rooms (soft warning if they do,
    but enforced here as hard constraint since lab rooms have equipment requirements).
    """

    constraint_id = "HC-06"
    constraint_type = ConstraintType.HARD
    severity = Severity.LOW

    LAB_ROOM_TYPES = {"Lab", "DELL_LAB", "DellLab"}

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        if candidate.subject_type == "Lab":
            if candidate.room_type not in self.LAB_ROOM_TYPES:
                return self._fail(
                    f"Lab subject '{candidate.subject_name}' assigned to non-lab room "
                    f"'{candidate.room_id}' (type: {candidate.room_type}). "
                    f"Must use a Lab or Dell Lab room.",
                    auto_fixable=True,
                )
        return self._ok()

    def violation_message(self) -> str:
        return "HC-06: Lab subject assigned to non-lab room"


# ─────────────────────────────────────────────────────────────────
# HC-07: ElectiveSameSlotEnforcement
# ─────────────────────────────────────────────────────────────────
class HC07_ElectiveSameSlotEnforcement(BaseConstraint):
    """
    All sections sharing the same elective group (e.g. E-2: COA, IOT) must schedule
    that elective in the SAME day+period combination, so students can attend their
    chosen elective regardless of section.
    """

    constraint_id = "HC-07"
    constraint_type = ConstraintType.HARD
    severity = Severity.CRITICAL

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        elective_group = candidate.extra.get("elective_group_code")
        if not elective_group or not candidate.extra.get("is_elective"):
            return self._ok()

        for slot in existing_slots:
            if (
                slot.extra.get("elective_group_code") == elective_group
                and slot.extra.get("is_elective")
                and slot.section_id != candidate.section_id
            ):
                # Elective already placed for another section — must match day+period
                if slot.day != candidate.day or slot.period_idx != candidate.period_idx:
                    return self._fail(
                        f"Elective group {elective_group} for section {candidate.section_id} "
                        f"is at {candidate.day} P{candidate.period_idx + 1} but section "
                        f"{slot.section_id} has it at {slot.day} P{slot.period_idx + 1}. "
                        f"All sections in the same elective group must share the same slot.",
                        auto_fixable=True,
                    )
        return self._ok()

    def violation_message(self) -> str:
        return "HC-07: Elective sections not aligned at same day+period"


# ─────────────────────────────────────────────────────────────────
# HC-08: SubjectWeeklyFrequency
# ─────────────────────────────────────────────────────────────────
class HC08_SubjectWeeklyFrequency(BaseConstraint):
    """
    Each subject must appear exactly the number of times per week defined by
    its weekly_periods_required. This constraint is checked at timetable finalisation,
    not per-slot assignment (flags are raised when generation is complete).
    """

    constraint_id = "HC-08"
    constraint_type = ConstraintType.HARD
    severity = Severity.MEDIUM

    def __init__(self, required_weekly: dict[tuple[str, str], int]) -> None:
        """
        Args:
            required_weekly: Mapping of (section_id, subject_name) → required weekly periods
        """
        self._required = required_weekly

    def check(self, candidate: SlotCandidate, existing_slots: list[SlotCandidate]) -> ConstraintResult:
        key = (candidate.section_id, candidate.subject_name)
        required = self._required.get(key)
        if required is None:
            return self._ok()  # No requirement defined — skip

        # Count how many times this subject already appears for this section
        current_count = sum(
            1 for slot in existing_slots
            if slot.section_id == candidate.section_id
            and slot.subject_name == candidate.subject_name
            and not slot.extra.get("is_lab_continuation")
        )

        if current_count >= required:
            return self._fail(
                f"Subject '{candidate.subject_name}' for section {candidate.section_id} "
                f"has already been assigned {current_count}/{required} times this week. "
                f"Adding another slot would exceed the weekly frequency.",
                auto_fixable=False,
            )
        return self._ok()

    def violation_message(self) -> str:
        return "HC-08: Subject scheduled more times than weekly_periods_required"


# ─────────────────────────────────────────────────────────────────
# Factory: build default hard constraint set
# ─────────────────────────────────────────────────────────────────
def build_default_hard_constraints(
    faculty_limits: dict[str, int] | None = None,
    required_weekly: dict[tuple[str, str], int] | None = None,
) -> list[BaseConstraint]:
    """
    Build and return all 8 hard constraints with sensible defaults.

    Args:
        faculty_limits:  dict of faculty_id → max_classes_per_week (from DB)
        required_weekly: dict of (section_id, subject_name) → weekly periods required

    Returns:
        List of instantiated hard constraints ready to register with ConstraintEngine.
    """
    return [
        HC01_RoomSingleOccupancy(),
        HC02_FacultyNoDoubleBooking(),
        HC03_LaboratoryConsecutiveSlots(),
        HC04_LunchBreakEnforcement(),
        HC05_FacultyWeeklyHourLimit(faculty_limits or {}),
        HC06_LabRoomTypeMatch(),
        HC07_ElectiveSameSlotEnforcement(),
        HC08_SubjectWeeklyFrequency(required_weekly or {}),
    ]
