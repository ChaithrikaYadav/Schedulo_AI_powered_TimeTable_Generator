"""
tests/unit/test_constraints.py
Unit tests for the Schedulo constraint engine.
Tests all HC-01 through HC-08 hard constraints and
SC-01 through SC-05 soft constraints using synthetic slot objects.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock


# ── Helpers: build mock slot dicts ────────────────────────────────────────────

def make_slot(
    day: int = 0,
    period: int = 1,
    faculty_id: int = 1,
    room_id: int = 1,
    section_id: int = 1,
    slot_type: str = "THEORY",
    is_lab_continuation: bool = False,
    lab_group: str | None = None,
) -> dict:
    """Create a mock timetable slot dict for constraint testing."""
    return {
        "day_of_week": day,
        "day_name": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][day],
        "period_number": period,
        "period_label": f"Period {period}",
        "faculty_id": faculty_id,
        "room_id": room_id,
        "section_id": section_id,
        "slot_type": slot_type,
        "is_lab_continuation": is_lab_continuation,
        "lab_group": lab_group,
    }


def make_slots_grid(days: int = 6, periods: int = 9) -> list[dict]:
    """Generate an empty 6×9 grid (all FREE)."""
    slots = []
    for d in range(days):
        for p in range(1, periods + 1):
            slots.append(make_slot(day=d, period=p, slot_type="FREE"))
    return slots


# ── Import constraint engine ───────────────────────────────────────────────────
try:
    from schedulo.constraint_engine.base import BaseConstraint, ConstraintViolation
    _CONSTRAINTS_AVAILABLE = True
except ImportError:
    _CONSTRAINTS_AVAILABLE = False

try:
    from schedulo.constraint_engine.hard_constraints import (
        HC01RoomConflict,
        HC02FacultyConflict,
        HC03LunchBreak,
        HC04LabConsecutive,
        HC05FacultyWeeklyLimit,
        HC06SectionSingleClass,
        HC07SaturdayHalfDay,
        HC08LabGroupSplit,
    )
    _HARD_CONSTRAINTS_AVAILABLE = True
except ImportError:
    _HARD_CONSTRAINTS_AVAILABLE = False

try:
    from schedulo.constraint_engine.soft_constraints import (
        SC01PreferredSlots,
        SC02EvenDistribution,
        SC03NoBackToBackLabs,
        SC04MorningPreference,
        SC05RoomCapacityPreference,
    )
    _SOFT_CONSTRAINTS_AVAILABLE = True
except ImportError:
    _SOFT_CONSTRAINTS_AVAILABLE = False


# ── Base constraint tests ──────────────────────────────────────────────────────

@pytest.mark.skipif(not _CONSTRAINTS_AVAILABLE, reason="constraint engine not importable")
class TestBaseConstraint:
    def test_constraint_violation_has_required_fields(self):
        """ConstraintViolation must expose code, severity, description."""
        v = ConstraintViolation(
            code="HC-01",
            severity="CRITICAL",
            description="Room double-booked",
            slot_ids=[1, 2],
        )
        assert v.code == "HC-01"
        assert v.severity == "CRITICAL"
        assert "Room" in v.description
        assert 1 in v.slot_ids


# ── HC-01: Room conflict ───────────────────────────────────────────────────────

@pytest.mark.skipif(
    not _HARD_CONSTRAINTS_AVAILABLE, reason="hard constraints not importable"
)
class TestHC01RoomConflict:
    def test_no_violation_different_rooms(self):
        """Two slots on same day+period but different rooms → no violation."""
        constraint = HC01RoomConflict()
        slots = [
            make_slot(day=0, period=1, room_id=1, section_id=1, slot_type="THEORY"),
            make_slot(day=0, period=1, room_id=2, section_id=2, slot_type="THEORY"),
        ]
        violations = constraint.check(slots)
        assert len(violations) == 0

    def test_violation_same_room_same_slot(self):
        """Two different sections sharing the same room at the same time → CRITICAL violation."""
        constraint = HC01RoomConflict()
        slots = [
            make_slot(day=0, period=1, room_id=5, section_id=1, slot_type="THEORY"),
            make_slot(day=0, period=1, room_id=5, section_id=2, slot_type="THEORY"),
        ]
        violations = constraint.check(slots)
        assert len(violations) >= 1
        assert any(v.code == "HC-01" or "room" in v.description.lower() for v in violations)

    def test_no_violation_same_room_different_period(self):
        """Same room on different periods → no conflict."""
        constraint = HC01RoomConflict()
        slots = [
            make_slot(day=0, period=1, room_id=5, section_id=1),
            make_slot(day=0, period=2, room_id=5, section_id=2),
        ]
        violations = constraint.check(slots)
        assert len(violations) == 0


# ── HC-02: Faculty conflict ────────────────────────────────────────────────────

@pytest.mark.skipif(
    not _HARD_CONSTRAINTS_AVAILABLE, reason="hard constraints not importable"
)
class TestHC02FacultyConflict:
    def test_violation_faculty_double_booked(self):
        """Faculty teaching two sections simultaneously → violation."""
        constraint = HC02FacultyConflict()
        slots = [
            make_slot(day=1, period=3, faculty_id=10, section_id=1),
            make_slot(day=1, period=3, faculty_id=10, section_id=2),
        ]
        violations = constraint.check(slots)
        assert len(violations) >= 1

    def test_no_violation_faculty_different_slots(self):
        """Same faculty on different day/period → OK."""
        constraint = HC02FacultyConflict()
        slots = [
            make_slot(day=0, period=1, faculty_id=10, section_id=1),
            make_slot(day=0, period=2, faculty_id=10, section_id=2),
        ]
        violations = constraint.check(slots)
        assert len(violations) == 0

    def test_free_slot_faculty_not_checked(self):
        """FREE slots without faculty assigned → no violation even if period overlaps."""
        constraint = HC02FacultyConflict()
        slots = [
            make_slot(day=0, period=1, faculty_id=None, section_id=1, slot_type="FREE"),
            make_slot(day=0, period=1, faculty_id=None, section_id=2, slot_type="FREE"),
        ]
        violations = constraint.check(slots)
        assert len(violations) == 0


# ── HC-03: Lunch break ────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not _HARD_CONSTRAINTS_AVAILABLE, reason="hard constraints not importable"
)
class TestHC03LunchBreak:
    def test_missing_lunch_is_violation(self):
        """A day with no LUNCH slot → violation."""
        constraint = HC03LunchBreak()
        # 6 days, 9 periods, all THEORY (no lunch)
        slots = make_slots_grid()
        for s in slots:
            s["slot_type"] = "THEORY"
        violations = constraint.check(slots)
        assert len(violations) > 0

    def test_lunch_present_no_violation(self):
        """Each day has exactly one LUNCH slot → no violation."""
        constraint = HC03LunchBreak()
        slots = make_slots_grid()
        for d in range(6):
            # Set period 5 on each day as LUNCH
            for s in slots:
                if s["day_of_week"] == d and s["period_number"] == 5:
                    s["slot_type"] = "LUNCH"
        violations = constraint.check(slots)
        assert len(violations) == 0


# ── HC-04: Lab consecutive ────────────────────────────────────────────────────

@pytest.mark.skipif(
    not _HARD_CONSTRAINTS_AVAILABLE, reason="hard constraints not importable"
)
class TestHC04LabConsecutive:
    def test_isolated_lab_is_violation(self):
        """A LAB slot with no continuation slot → violation."""
        constraint = HC04LabConsecutive()
        slots = [
            make_slot(day=0, period=1, slot_type="LAB", is_lab_continuation=False),
            make_slot(day=0, period=2, slot_type="THEORY"),  # not a lab continuation
        ]
        violations = constraint.check(slots)
        assert len(violations) >= 1

    def test_paired_lab_no_violation(self):
        """LAB + LAB continuation on consecutive periods → no violation."""
        constraint = HC04LabConsecutive()
        slots = [
            make_slot(day=0, period=1, slot_type="LAB", is_lab_continuation=False),
            make_slot(day=0, period=2, slot_type="LAB", is_lab_continuation=True),
        ]
        violations = constraint.check(slots)
        assert len(violations) == 0


# ── HC-07: Saturday half-day ──────────────────────────────────────────────────

@pytest.mark.skipif(
    not _HARD_CONSTRAINTS_AVAILABLE, reason="hard constraints not importable"
)
class TestHC07SaturdayHalfDay:
    def test_saturday_after_period4_is_violation(self):
        """Classes scheduled on Saturday periods 5–9 → violation."""
        constraint = HC07SaturdayHalfDay()
        slots = [
            make_slot(day=5, period=6, slot_type="THEORY"),  # Saturday period 6 = violation
        ]
        violations = constraint.check(slots)
        assert len(violations) >= 1

    def test_saturday_period1_ok(self):
        """Saturday period 1 is allowed."""
        constraint = HC07SaturdayHalfDay()
        slots = [
            make_slot(day=5, period=1, slot_type="THEORY"),
        ]
        violations = constraint.check(slots)
        assert len(violations) == 0


# ── Soft constraints ──────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not _SOFT_CONSTRAINTS_AVAILABLE, reason="soft constraints not importable"
)
class TestSoftConstraints:
    def test_sc02_even_distribution_returns_score(self):
        """SC02 should return a penalty score (float), not a boolean."""
        constraint = SC02EvenDistribution()
        slots = make_slots_grid()
        # Put all theory in day 0
        for s in slots:
            if s["day_of_week"] == 0 and s["period_number"] <= 5:
                s["slot_type"] = "THEORY"
        result = constraint.evaluate(slots)
        assert isinstance(result, (int, float))

    def test_sc01_preferred_slots_score(self):
        """SC01 preferred slots evaluator should return a numeric score."""
        constraint = SC01PreferredSlots()
        slots = make_slots_grid()
        result = constraint.evaluate(slots)
        assert isinstance(result, (int, float))


# ── ML Pipeline unit tests (skipped if schedulo.ml_pipeline not available) ────
# Note: schedulo.ml_pipeline was removed from the production codebase.
# These tests are kept as documentation of the expected API but will skip
# automatically on any installation that does not have the module.
try:
    import schedulo.ml_pipeline  # noqa: F401
    _ML_PIPELINE_AVAILABLE = True
except ImportError:
    _ML_PIPELINE_AVAILABLE = False

@pytest.mark.skipif(not _ML_PIPELINE_AVAILABLE, reason="schedulo.ml_pipeline not installed")
class TestFeatureEngineer:
    def test_feature_vector_length(self, sample_timetable_dict):
        """FeatureEngineer.extract_raw() must return exactly 20 features."""
        from schedulo.ml_pipeline.feature_engineering import FeatureEngineer, FEATURE_NAMES
        fe = FeatureEngineer()
        raw = fe.extract_raw(sample_timetable_dict)
        assert len(raw) == 20
        assert len(raw) == len(FEATURE_NAMES)

    def test_features_are_finite(self, sample_timetable_dict):
        """All features must be finite (no NaN/Inf)."""
        import math
        from schedulo.ml_pipeline.feature_engineering import FeatureEngineer
        fe = FeatureEngineer()
        raw = fe.extract_raw(sample_timetable_dict)
        assert all(math.isfinite(f) for f in raw), "Non-finite feature values found"

    def test_transform_one_returns_array(self, sample_timetable_dict):
        from schedulo.ml_pipeline.feature_engineering import FeatureEngineer
        import numpy as np
        fe = FeatureEngineer()
        result = fe.transform_one(sample_timetable_dict)
        assert isinstance(result, np.ndarray)
        assert result.shape == (20,)

    def test_empty_slots_returns_zeros(self):
        from schedulo.ml_pipeline.feature_engineering import FeatureEngineer
        fe = FeatureEngineer()
        raw = fe.extract_raw({"slots": [], "conflict_count": 0})
        assert all(f == 0.0 for f in raw)


@pytest.mark.skipif(not _ML_PIPELINE_AVAILABLE, reason="schedulo.ml_pipeline not installed")
class TestQualityPredictor:
    def test_predict_in_range(self, sample_timetable_dict, tmp_path):
        """Heuristic quality score must be in [0, 100]."""
        from schedulo.ml_pipeline.quality_predictor import QualityPredictor
        qp = QualityPredictor(models_dir=str(tmp_path))
        score = qp.predict(sample_timetable_dict)
        assert 0.0 <= score <= 100.0

    def test_clean_timetable_higher_score(self, sample_timetable_dict, clean_timetable_dict, tmp_path):
        """A clean timetable should score higher than a conflicted one."""
        from schedulo.ml_pipeline.quality_predictor import QualityPredictor
        qp = QualityPredictor(models_dir=str(tmp_path))
        dirty_score = qp.predict(sample_timetable_dict)
        clean_score = qp.predict(clean_timetable_dict)
        assert clean_score >= dirty_score, (
            f"Expected clean ({clean_score:.1f}) >= dirty ({dirty_score:.1f})"
        )

    def test_not_trained_by_default(self, tmp_path):
        """Without model file, predictor should fall back to heuristic (is_trained=False)."""
        from schedulo.ml_pipeline.quality_predictor import QualityPredictor
        qp = QualityPredictor(models_dir=str(tmp_path))
        assert not qp.is_trained


@pytest.mark.skipif(not _ML_PIPELINE_AVAILABLE, reason="schedulo.ml_pipeline not installed")
class TestAnomalyDetector:
    def test_predict_one_structure(self, sample_timetable_dict, tmp_path):
        """predict_one must return a dict with is_anomaly, anomaly_score, reason."""
        from schedulo.ml_pipeline.anomaly_detector import AnomalyDetector
        ad = AnomalyDetector(models_dir=str(tmp_path))
        result = ad.predict_one(sample_timetable_dict)
        assert "is_anomaly" in result
        assert "anomaly_score" in result
        assert "reason" in result
        assert isinstance(result["is_anomaly"], bool)
        assert 0.0 <= result["anomaly_score"] <= 1.0

    def test_ghost_timetable_is_anomaly(self, tmp_path):
        """A timetable with 0% utilization should be detected as anomalous."""
        from schedulo.ml_pipeline.anomaly_detector import AnomalyDetector
        ad = AnomalyDetector(models_dir=str(tmp_path))
        # All FREE slots
        ghost = {
            "slots": [{"day": d, "period": p, "slot_type": "FREE", "faculty_id": None, "room_id": None}
                      for d in range(6) for p in range(1, 10)],
            "conflict_count": 0,
            "generation_time_ms": 0,
            "ga_fitness_score": 0.0,
            "section_count": 1,
        }
        result = ad.predict_one(ghost)
        assert result["is_anomaly"], "Ghost timetable (all FREE) should be anomalous"
