"""
chronoai/conflict_detector/detector.py
Real-time timetable conflict detection engine for ChronoAI.

Scans a list of TimetableSlot records and reports all HC/SC violations
without modifying the database. Returns structured ConflictReport objects
suitable for display in the UI and storage in ConflictLog.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ConflictSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ConflictType(str, Enum):
    ROOM_DOUBLE_BOOKING = "HC-01"
    FACULTY_DOUBLE_BOOKING = "HC-02"
    LAB_NOT_CONSECUTIVE = "HC-03"
    LUNCH_ELIMINATED = "HC-04"
    FACULTY_HOUR_LIMIT = "HC-05"
    LAB_ROOM_MISMATCH = "HC-06"
    ELECTIVE_MISALIGNED = "HC-07"
    SUBJECT_OVERCOUNT = "HC-08"
    FACULTY_PREF_VIOLATED = "SC-01"
    SUBJECT_CLUSTERED = "SC-03"
    CONSECUTIVE_OVERLOAD = "SC-07"


@dataclass
class SlotData:
    """Lightweight timetable slot for conflict analysis."""
    slot_id: int
    timetable_id: int
    section_id: str
    day_name: str
    period_number: int
    period_label: str
    slot_type: str          # Theory | Lab | Lab_Cont | Lunch | Free
    subject_name: str
    faculty_id: str
    faculty_name: str
    room_id: str
    room_type: str
    is_lab_pair: bool = False
    lab_pair_period: int = -1
    elective_group: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConflictReport:
    """A single detected conflict."""
    conflict_type: ConflictType
    severity: ConflictSeverity
    description: str
    affected_section_ids: list[str]
    affected_slot_ids: list[int]
    auto_fixable: bool
    penalty: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_type": self.conflict_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "affected_section_ids": self.affected_section_ids,
            "affected_slot_ids": self.affected_slot_ids,
            "auto_fixable": self.auto_fixable,
            "penalty": self.penalty,
        }


# Period indices that mark the valid lunch window
LUNCH_PERIOD_INDICES = {4, 5}          # 1-based periods 5 & 6 → 0-based 4 & 5
INVALID_LAB_START = {3}                # period index 3 → period 4 (straddles lunch)
LAB_ROOM_TYPES = {"Lab", "DELL_LAB", "DellLab", "lab"}


class ConflictDetector:
    """
    Full hard+soft constraint violation scanner.

    Usage:
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        hard_violations = [r for r in reports if r.severity == ConflictSeverity.CRITICAL]
    """

    def __init__(self, slots: list[SlotData]) -> None:
        self._slots = slots

    # ── Public API ────────────────────────────────────────────────
    def scan_all(self) -> list[ConflictReport]:
        """Run every detector and return all conflict reports."""
        reports: list[ConflictReport] = []
        reports.extend(self._check_hc01_room_double_booking())
        reports.extend(self._check_hc02_faculty_double_booking())
        reports.extend(self._check_hc03_lab_consecutive())
        reports.extend(self._check_hc04_lunch_break())
        reports.extend(self._check_hc06_lab_room_type())
        reports.extend(self._check_hc07_elective_alignment())
        reports.extend(self._check_sc03_subject_spread())
        reports.extend(self._check_sc07_consecutive_limit())
        logger.info(f"ConflictDetector: {len(reports)} conflicts found in {len(self._slots)} slots")
        return reports

    def scan_hard_only(self) -> list[ConflictReport]:
        """Return only CRITICAL/HIGH violations (hard constraints)."""
        return [r for r in self.scan_all() if r.severity in {ConflictSeverity.CRITICAL, ConflictSeverity.HIGH}]

    def summary(self) -> dict[str, int]:
        """Return count of conflicts by severity."""
        all_reports = self.scan_all()
        counts: dict[str, int] = {}
        for r in all_reports:
            counts[r.severity.value] = counts.get(r.severity.value, 0) + 1
        return counts

    # ── HC-01: Room double-booking ────────────────────────────────
    def _check_hc01_room_double_booking(self) -> list[ConflictReport]:
        reports: list[ConflictReport] = []
        seen: dict[tuple[str, str, int], SlotData] = {}

        for slot in self._slots:
            if not slot.room_id or slot.slot_type in {"Lunch", "Free"}:
                continue
            key = (slot.day_name, slot.room_id, slot.period_number)
            if key in seen:
                other = seen[key]
                if other.section_id != slot.section_id:
                    reports.append(ConflictReport(
                        conflict_type=ConflictType.ROOM_DOUBLE_BOOKING,
                        severity=ConflictSeverity.CRITICAL,
                        description=(
                            f"Room {slot.room_id} double-booked on {slot.day_name} "
                            f"Period {slot.period_number}: "
                            f"{slot.section_id} ({slot.subject_name}) vs "
                            f"{other.section_id} ({other.subject_name})"
                        ),
                        affected_section_ids=[slot.section_id, other.section_id],
                        affected_slot_ids=[slot.slot_id, other.slot_id],
                        auto_fixable=True,
                    ))
            else:
                seen[key] = slot

        return reports

    # ── HC-02: Faculty double-booking ─────────────────────────────
    def _check_hc02_faculty_double_booking(self) -> list[ConflictReport]:
        reports: list[ConflictReport] = []
        seen: dict[tuple[str, str, int], SlotData] = {}

        for slot in self._slots:
            if not slot.faculty_id or slot.faculty_id.startswith("TBA"):
                continue
            if slot.slot_type in {"Lunch", "Free"}:
                continue
            key = (slot.day_name, slot.faculty_id, slot.period_number)
            if key in seen:
                other = seen[key]
                if other.section_id != slot.section_id:
                    reports.append(ConflictReport(
                        conflict_type=ConflictType.FACULTY_DOUBLE_BOOKING,
                        severity=ConflictSeverity.CRITICAL,
                        description=(
                            f"Faculty {slot.faculty_name} ({slot.faculty_id}) double-booked "
                            f"on {slot.day_name} Period {slot.period_number}: "
                            f"{slot.section_id} vs {other.section_id}"
                        ),
                        affected_section_ids=[slot.section_id, other.section_id],
                        affected_slot_ids=[slot.slot_id, other.slot_id],
                        auto_fixable=True,
                    ))
            else:
                seen[key] = slot

        return reports

    # ── HC-03: Lab consecutive ────────────────────────────────────
    def _check_hc03_lab_consecutive(self) -> list[ConflictReport]:
        reports: list[ConflictReport] = []
        lab_slots = [s for s in self._slots if s.slot_type == "Lab"]

        for slot in lab_slots:
            p = slot.period_number - 1  # 0-based

            # Check invalid lab start (straddles lunch)
            if p in INVALID_LAB_START:
                reports.append(ConflictReport(
                    conflict_type=ConflictType.LAB_NOT_CONSECUTIVE,
                    severity=ConflictSeverity.CRITICAL,
                    description=(
                        f"Lab '{slot.subject_name}' for {slot.section_id} starts at Period "
                        f"{slot.period_number} on {slot.day_name}, which straddles the lunch break."
                    ),
                    affected_section_ids=[slot.section_id],
                    affected_slot_ids=[slot.slot_id],
                    auto_fixable=True,
                ))
                continue

            # Verify the continuation slot exists
            continuation = next(
                (s for s in self._slots
                 if s.section_id == slot.section_id
                 and s.day_name == slot.day_name
                 and s.period_number == slot.period_number + 1
                 and s.slot_type == "Lab_Cont"
                 and s.subject_name == slot.subject_name),
                None,
            )
            if continuation is None:
                reports.append(ConflictReport(
                    conflict_type=ConflictType.LAB_NOT_CONSECUTIVE,
                    severity=ConflictSeverity.CRITICAL,
                    description=(
                        f"Lab '{slot.subject_name}' for {slot.section_id} on {slot.day_name} "
                        f"Period {slot.period_number} has no consecutive continuation slot."
                    ),
                    affected_section_ids=[slot.section_id],
                    affected_slot_ids=[slot.slot_id],
                    auto_fixable=True,
                ))

        return reports

    # ── HC-04: Lunch break ────────────────────────────────────────
    def _check_hc04_lunch_break(self) -> list[ConflictReport]:
        reports: list[ConflictReport] = []

        # Group by section and day
        from collections import defaultdict
        section_day: dict[tuple[str, str], list[SlotData]] = defaultdict(list)
        for slot in self._slots:
            section_day[(slot.section_id, slot.day_name)].append(slot)

        for (section_id, day), day_slots in section_day.items():
            occupied_lunch = {
                s.period_number - 1  # 0-based
                for s in day_slots
                if (s.period_number - 1) in LUNCH_PERIOD_INDICES
                and s.slot_type not in {"Lunch", "Free"}
            }
            if occupied_lunch == LUNCH_PERIOD_INDICES:
                reports.append(ConflictReport(
                    conflict_type=ConflictType.LUNCH_ELIMINATED,
                    severity=ConflictSeverity.HIGH,
                    description=(
                        f"Section {section_id} has no lunch break on {day} — "
                        f"both lunch window periods are occupied."
                    ),
                    affected_section_ids=[section_id],
                    affected_slot_ids=[s.slot_id for s in day_slots if (s.period_number - 1) in occupied_lunch],
                    auto_fixable=False,
                ))

        return reports

    # ── HC-06: Lab room type ──────────────────────────────────────
    def _check_hc06_lab_room_type(self) -> list[ConflictReport]:
        reports: list[ConflictReport] = []
        for slot in self._slots:
            if slot.slot_type == "Lab" and slot.room_type not in LAB_ROOM_TYPES:
                reports.append(ConflictReport(
                    conflict_type=ConflictType.LAB_ROOM_MISMATCH,
                    severity=ConflictSeverity.HIGH,
                    description=(
                        f"Lab '{slot.subject_name}' for {slot.section_id} is scheduled in "
                        f"room '{slot.room_id}' (type: {slot.room_type}), which is not a lab room."
                    ),
                    affected_section_ids=[slot.section_id],
                    affected_slot_ids=[slot.slot_id],
                    auto_fixable=True,
                ))
        return reports

    # ── HC-07: Elective alignment ─────────────────────────────────
    def _check_hc07_elective_alignment(self) -> list[ConflictReport]:
        reports: list[ConflictReport] = []
        elective_slots = [s for s in self._slots if s.elective_group]

        # Group by elective_group
        from collections import defaultdict
        groups: dict[str, list[SlotData]] = defaultdict(list)
        for s in elective_slots:
            groups[s.elective_group].append(s)

        for group_code, slots in groups.items():
            # All sections in the group must share the same day+period
            anchors: set[tuple[str, int]] = {(s.day_name, s.period_number) for s in slots}
            if len(anchors) > 1:
                first = slots[0]
                reports.append(ConflictReport(
                    conflict_type=ConflictType.ELECTIVE_MISALIGNED,
                    severity=ConflictSeverity.CRITICAL,
                    description=(
                        f"Elective group {group_code} is split across "
                        f"{len(anchors)} different day+period combinations: {anchors}. "
                        f"All sections must share the same slot."
                    ),
                    affected_section_ids=list({s.section_id for s in slots}),
                    affected_slot_ids=[s.slot_id for s in slots],
                    auto_fixable=True,
                ))

        return reports

    # ── SC-03: Subject spread ─────────────────────────────────────
    def _check_sc03_subject_spread(self) -> list[ConflictReport]:
        reports: list[ConflictReport] = []
        from collections import defaultdict, Counter

        section_subj_day: dict[tuple[str, str], list[str]] = defaultdict(list)
        for s in self._slots:
            if s.slot_type in {"Lunch", "Free", "Lab_Cont"}:
                continue
            section_subj_day[(s.section_id, s.subject_name)].append(s.day_name)

        for (section_id, subject), days in section_subj_day.items():
            counts = Counter(days)
            for day, cnt in counts.items():
                if cnt >= 2:
                    reports.append(ConflictReport(
                        conflict_type=ConflictType.SUBJECT_CLUSTERED,
                        severity=ConflictSeverity.LOW,
                        description=(
                            f"Subject '{subject}' for {section_id} appears {cnt}× on {day}. "
                            f"Consider spreading across different days."
                        ),
                        affected_section_ids=[section_id],
                        affected_slot_ids=[],
                        auto_fixable=False,
                        penalty=8.0 * (cnt - 1),
                    ))

        return reports

    # ── SC-07: Consecutive class limit ────────────────────────────
    def _check_sc07_consecutive_limit(self) -> list[ConflictReport]:
        reports: list[ConflictReport] = []
        MAX_CONSECUTIVE = 4
        from collections import defaultdict

        # Build section+day → set of occupied period indices
        occ: dict[tuple[str, str], set[int]] = defaultdict(set)
        for s in self._slots:
            if s.slot_type in {"Lunch", "Free"}:
                continue
            occ[(s.section_id, s.day_name)].add(s.period_number - 1)  # 0-based

        for (section_id, day), periods in occ.items():
            if not periods:
                continue
            sorted_p = sorted(periods)
            run = 1
            max_run = 1
            for i in range(1, len(sorted_p)):
                if sorted_p[i] == sorted_p[i - 1] + 1:
                    run += 1
                    max_run = max(max_run, run)
                else:
                    run = 1

            if max_run > MAX_CONSECUTIVE:
                reports.append(ConflictReport(
                    conflict_type=ConflictType.CONSECUTIVE_OVERLOAD,
                    severity=ConflictSeverity.MEDIUM,
                    description=(
                        f"Section {section_id} has {max_run} consecutive classes on {day} "
                        f"(max recommended: {MAX_CONSECUTIVE})."
                    ),
                    affected_section_ids=[section_id],
                    affected_slot_ids=[],
                    auto_fixable=False,
                    penalty=7.0 * (max_run - MAX_CONSECUTIVE),
                ))

        return reports
