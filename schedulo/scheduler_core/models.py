"""
schedulo/scheduler_core/models.py
Internal dataclasses shared across all 6 scheduling phases.
These are pure-Python working objects — not SQLAlchemy models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SlotType(str, Enum):
    THEORY  = "THEORY"
    LAB     = "LAB"
    LUNCH   = "LUNCH"
    FREE    = "FREE"
    PROJECT = "PROJECT"


@dataclass
class SubjectDemand:
    """One subject that needs to be scheduled for one section."""
    subject_id:           int
    subject_name:         str
    subject_type:         str          # "Theory" | "Lab" | "Project"
    credits:              float
    weekly_periods:       int          # slots needed per week
    requires_consecutive: bool         # True for all Labs
    burst_length:         int          # 2 for Lab, 1 for Theory/Project
    section_id:           int          # sections.id (integer PK)
    section_str:          str          # e.g. "2CSE1"
    department_id:        int
    semester:             str

    # Computed by Phase 2
    priority_score:     float = 0.0
    scheduled_periods:  int   = 0     # periods placed so far


@dataclass
class FacultySlot:
    """One faculty member with scheduling constraints and mutable state."""
    faculty_id:            int
    name:                  str
    department_id:         int
    main_subject:          str
    backup_subject:        str
    max_classes_per_week:  int
    preferred_slots:       str         # "Morning"|"Afternoon"|"No 1st Period"|"Any"
    can_take_labs:         bool

    # Mutable state — updated during scheduling
    assigned_count: int = 0
    # (day_index 0–5, period_number 1–9)
    assigned_slots: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class RoomSlot:
    """One room with its per-(day,period) availability map."""
    room_pk:      int            # rooms.id integer FK
    room_id_str:  str            # e.g. "SVH-111"
    room_type:    str            # "Classroom" | "Lab" | "Special"
    building:     str
    capacity:     int
    # availability[day][period] = True if free
    availability: dict[int, dict[int, bool]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.availability:
            self.availability = {
                day: {p: True for p in range(1, 10)}
                for day in range(6)
            }

    def is_free(self, day: int, period: int) -> bool:
        return self.availability.get(day, {}).get(period, True)

    def occupy(self, day: int, period: int) -> None:
        self.availability.setdefault(day, {})[period] = False


@dataclass
class ScheduledSlot:
    """One fully resolved slot, ready to be written to timetable_slots table."""
    section_id:          int
    section_str:         str
    day_of_week:         int           # 0=Monday … 5=Saturday
    day_name:            str
    period_number:       int           # 1–9
    period_label:        str           # "9:00–9:55" etc.
    slot_type:           SlotType
    subject_id:          int | None
    subject_name:        str
    faculty_id:          int | None
    faculty_name:        str
    room_pk:             int | None    # FK to rooms.id
    room_id_str:         str
    is_lab_continuation: bool = False
    algorithm_used:      str  = ""    # audit trail
