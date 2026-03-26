"""
tests/unit/test_conflict_detector.py
Unit tests for the Schedulo ConflictDetector.

Uses the real ConflictDetector(slots) API with SlotData objects.
Verifies room double-booking (HC-01), faculty double-booking (HC-02),
lunch elimination (HC-04), and lab consecutive (HC-03) detection.
"""

from __future__ import annotations

import importlib
import importlib.util
import pytest


# ── Helper: build SlotData objects ───────────────────────────────────────────

def make_slot_data(
    slot_id: int = 1,
    day: str = "Monday",
    period: int = 1,
    section_id: str = "2CSE1",
    faculty_id: str = "FAC-01",
    faculty_name: str = "Dr. Test",
    room_id: str = "CSE-101",
    room_type: str = "Theory",
    slot_type: str = "Theory",
    subject_name: str = "Math",
    timetable_id: int = 1,
    is_lab_pair: bool = False,
    elective_group: str = "",
) -> object:
    """Build a SlotData instance from the detector module."""
    from schedulo.conflict_detector.detector import SlotData
    return SlotData(
        slot_id=slot_id,
        timetable_id=timetable_id,
        section_id=section_id,
        day_name=day,
        period_number=period,
        period_label=f"Period {period}",
        slot_type=slot_type,
        subject_name=subject_name,
        faculty_id=faculty_id,
        faculty_name=faculty_name,
        room_id=room_id,
        room_type=room_type,
        is_lab_pair=is_lab_pair,
        elective_group=elective_group,
    )


# ── Import detector ───────────────────────────────────────────────────────────

try:
    from schedulo.conflict_detector.detector import ConflictDetector, ConflictType, ConflictSeverity
    _DETECTOR_AVAILABLE = True
except ImportError:
    _DETECTOR_AVAILABLE = False


@pytest.mark.skipif(not _DETECTOR_AVAILABLE, reason="conflict_detector not importable")
class TestConflictDetector:
    """Tests for ConflictDetector.scan_all() conflict identification."""

    # ── HC-01: Room double-booking ────────────────────────────────────────────
    def test_hc01_room_double_booking_detected(self):
        """Two sections in the same room at the same period → HC-01 CRITICAL."""
        slots = [
            make_slot_data(slot_id=1, day="Monday", period=1, section_id="2CSE1",
                           room_id="CSE-101", faculty_id="FAC-01"),
            make_slot_data(slot_id=2, day="Monday", period=1, section_id="2CSE2",
                           room_id="CSE-101", faculty_id="FAC-02"),
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        room_conflicts = [r for r in reports if r.conflict_type == ConflictType.ROOM_DOUBLE_BOOKING]
        assert len(room_conflicts) >= 1, f"Expected HC-01 room conflict, got reports: {[r.conflict_type for r in reports]}"
        assert room_conflicts[0].severity == ConflictSeverity.CRITICAL

    def test_hc01_no_conflict_different_rooms(self):
        """Same period, different rooms → no room double-booking."""
        slots = [
            make_slot_data(slot_id=1, day="Monday", period=1, section_id="2CSE1", room_id="CSE-101"),
            make_slot_data(slot_id=2, day="Monday", period=1, section_id="2CSE2", room_id="CSE-102"),
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        room_conflicts = [r for r in reports if r.conflict_type == ConflictType.ROOM_DOUBLE_BOOKING]
        assert len(room_conflicts) == 0

    def test_hc01_no_conflict_same_room_different_period(self):
        """Same room, different periods → no conflict."""
        slots = [
            make_slot_data(slot_id=1, day="Monday", period=1, section_id="2CSE1", room_id="CSE-101"),
            make_slot_data(slot_id=2, day="Monday", period=2, section_id="2CSE2", room_id="CSE-101"),
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        room_conflicts = [r for r in reports if r.conflict_type == ConflictType.ROOM_DOUBLE_BOOKING]
        assert len(room_conflicts) == 0

    # ── HC-02: Faculty double-booking ─────────────────────────────────────────
    def test_hc02_faculty_double_booking_detected(self):
        """Same faculty teaching two sections at the same period → HC-02 CRITICAL."""
        slots = [
            make_slot_data(slot_id=1, day="Tuesday", period=3, section_id="2CSE1",
                           faculty_id="FAC-10", room_id="CSE-101"),
            make_slot_data(slot_id=2, day="Tuesday", period=3, section_id="2CSE2",
                           faculty_id="FAC-10", room_id="CSE-102"),
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        faculty_conflicts = [r for r in reports if r.conflict_type == ConflictType.FACULTY_DOUBLE_BOOKING]
        assert len(faculty_conflicts) >= 1, \
            f"Expected HC-02 faculty conflict, got: {[r.conflict_type for r in reports]}"
        assert faculty_conflicts[0].severity == ConflictSeverity.CRITICAL

    def test_hc02_no_conflict_different_periods(self):
        """Same faculty, different periods → no conflict."""
        slots = [
            make_slot_data(slot_id=1, day="Monday", period=1, section_id="2CSE1",
                           faculty_id="FAC-07", room_id="CSE-101"),
            make_slot_data(slot_id=2, day="Monday", period=2, section_id="2CSE2",
                           faculty_id="FAC-07", room_id="CSE-102"),
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        faculty_conflicts = [r for r in reports if r.conflict_type == ConflictType.FACULTY_DOUBLE_BOOKING]
        assert len(faculty_conflicts) == 0

    def test_hc02_tba_faculty_not_flagged(self):
        """Faculty IDs starting with 'TBA' should not be flagged."""
        slots = [
            make_slot_data(slot_id=1, day="Monday", period=1, section_id="2CSE1",
                           faculty_id="TBA-01", room_id="CSE-101"),
            make_slot_data(slot_id=2, day="Monday", period=1, section_id="2CSE2",
                           faculty_id="TBA-01", room_id="CSE-102"),
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        faculty_conflicts = [r for r in reports if r.conflict_type == ConflictType.FACULTY_DOUBLE_BOOKING]
        assert len(faculty_conflicts) == 0

    # ── HC-03: Lab consecutive ─────────────────────────────────────────────────
    def test_hc03_lab_without_pair_is_violation(self):
        """A Lab slot with no Lab_Cont follower → HC-03 violation."""
        slots = [
            make_slot_data(slot_id=1, day="Wednesday", period=1, section_id="2CSE1",
                           slot_type="Lab", subject_name="OS Lab", room_type="Lab"),
            # Period 2 is Theory — not a Lab_Cont for OS Lab
            make_slot_data(slot_id=2, day="Wednesday", period=2, section_id="2CSE1",
                           slot_type="Theory", subject_name="Math", room_type="Theory"),
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        lab_conflicts = [r for r in reports if r.conflict_type == ConflictType.LAB_NOT_CONSECUTIVE]
        assert len(lab_conflicts) >= 1, \
            f"Expected HC-03 lab conflict, got: {[r.conflict_type for r in reports]}"

    def test_hc03_lab_straddles_lunch_is_violation(self):
        """Lab at period 4 (0-based index 3) straddles lunch → HC-03."""
        slots = [
            make_slot_data(slot_id=1, day="Monday", period=4, section_id="2CSE1",
                           slot_type="Lab", subject_name="Networks Lab", room_type="Lab"),
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        lab_conflicts = [r for r in reports if r.conflict_type == ConflictType.LAB_NOT_CONSECUTIVE]
        assert len(lab_conflicts) >= 1, "Lab at period 4 should flag as straddles-lunch"

    def test_hc03_paired_lab_no_violation(self):
        """Lab + Lab_Cont on consecutive periods → no lab conflict."""
        slots = [
            make_slot_data(slot_id=1, day="Friday", period=1, section_id="2CSE1",
                           slot_type="Lab", subject_name="OS Lab", room_type="Lab"),
            make_slot_data(slot_id=2, day="Friday", period=2, section_id="2CSE1",
                           slot_type="Lab_Cont", subject_name="OS Lab", room_type="Lab"),
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        lab_conflicts = [r for r in reports if r.conflict_type == ConflictType.LAB_NOT_CONSECUTIVE]
        assert len(lab_conflicts) == 0, \
            f"Paired lab should have no violation, got: {[r.description for r in lab_conflicts]}"

    # ── HC-04: Lunch eliminated ────────────────────────────────────────────────
    def test_hc04_lunch_eliminated_when_both_windows_occupied(self):
        """Both lunch window periods filled with non-lunch slots → HC-04."""
        # LUNCH_PERIOD_INDICES = {4, 5} (0-based), so periods 5 and 6 (1-based)
        slots = [
            make_slot_data(slot_id=i, day="Monday", period=i, section_id="2CSE1",
                           slot_type="Theory", subject_name=f"Sub{i}", room_id=f"R{i}")
            for i in range(1, 10)  # All 9 periods as Theory — periods 5 and 6 are the lunch window
        ]
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        lunch_conflicts = [r for r in reports if r.conflict_type == ConflictType.LUNCH_ELIMINATED]
        assert len(lunch_conflicts) >= 1, \
            f"Expected HC-04 lunch conflict when both window periods are occupied, got: {reports}"

    # ── Clean timetable: no critical violations ────────────────────────────────
    def test_no_critical_conflicts_in_clean_data(self):
        """A well-formed single-section timetable should have zero CRITICAL conflicts."""
        # periods 1-4: Theory, period 5: Lunch, periods 6-9: Theory
        slots = []
        for period in range(1, 10):
            stype = "Lunch" if period == 5 else "Theory"
            fac = f"FAC-{(period % 5) + 1:02d}" if stype != "Lunch" else ""
            rm = f"CSE-{100 + period}" if stype != "Lunch" else ""
            rm_type = "Theory" if stype == "Theory" else ""
            slots.append(make_slot_data(
                slot_id=period, day="Monday", period=period,
                section_id="2CSE1", faculty_id=fac, faculty_name=f"Prof {period}",
                room_id=rm, room_type=rm_type, slot_type=stype,
                subject_name=f"Subject_{period}" if stype != "Lunch" else "LUNCH",
            ))
        detector = ConflictDetector(slots)
        reports = detector.scan_all()
        critical = [r for r in reports if r.severity == ConflictSeverity.CRITICAL]
        assert len(critical) == 0, \
            f"Expected no CRITICAL violations in clean timetable, got: {[r.description for r in critical]}"

    # ── Summary returns dict ───────────────────────────────────────────────────
    def test_summary_returns_dict(self):
        """detector.summary() must return a plain dict of severity → count."""
        slots = [make_slot_data(slot_id=1, day="Monday", period=1, section_id="2CSE1")]
        detector = ConflictDetector(slots)
        result = detector.summary()
        assert isinstance(result, dict)

    # ── scan_hard_only filters to CRITICAL and HIGH ────────────────────────────
    def test_scan_hard_only_returns_only_hard_violations(self):
        """scan_hard_only() should return only CRITICAL/HIGH severity conflicts."""
        slots = [
            make_slot_data(slot_id=1, day="Monday", period=1, section_id="2CSE1",
                           room_id="CSE-101", faculty_id="FAC-01"),
            make_slot_data(slot_id=2, day="Monday", period=1, section_id="2CSE2",
                           room_id="CSE-101", faculty_id="FAC-02"),
        ]
        detector = ConflictDetector(slots)
        hard_only = detector.scan_hard_only()
        for report in hard_only:
            assert report.severity in {ConflictSeverity.CRITICAL, ConflictSeverity.HIGH}, \
                f"scan_hard_only returned {report.severity}: {report.description}"


# ── Import-only test (always runs) ────────────────────────────────────────────
class TestConflictDetectorImport:
    def test_module_importable(self):
        """conflict_detector.detector module should be importable."""
        spec = importlib.util.find_spec("schedulo.conflict_detector.detector")
        assert spec is not None, "schedulo.conflict_detector.detector not found on sys.path"

    def test_slot_data_fields(self):
        """SlotData dataclass must have all required fields."""
        from schedulo.conflict_detector.detector import SlotData
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(SlotData)}
        required = {"slot_id", "timetable_id", "section_id", "day_name",
                    "period_number", "slot_type", "faculty_id", "room_id"}
        assert required.issubset(field_names), \
            f"SlotData missing fields: {required - field_names}"

    def test_conflict_type_has_hc01(self):
        """ConflictType enum must expose ROOM_DOUBLE_BOOKING (HC-01)."""
        from schedulo.conflict_detector.detector import ConflictType
        assert ConflictType.ROOM_DOUBLE_BOOKING.value == "HC-01"
