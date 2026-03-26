"""
schedulo/analytics_dashboard/metrics.py
Timetable quality metrics and analytics engine for Schedulo.

Computes utilisation rates, balance scores, and quality KPIs
from a set of TimetableSlot records without touching the database.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

PERIODS_PER_DAY = 9
TEACHING_PERIODS_PER_DAY = 7   # 9 periods - 1 lunch - 1 free allowance
DAYS_PER_WEEK = 6               # Mon–Sat


@dataclass
class SlotRow:
    """Minimal slot representation for analytics (no ORM dependency)."""
    section_id: str
    day_name: str
    period_number: int      # 1-based
    slot_type: str          # Theory | Lab | Lab_Cont | Lunch | Free
    subject_name: str
    faculty_id: str
    faculty_name: str
    room_id: str
    room_type: str
    room_capacity: int = 60


@dataclass
class TimetableAnalytics:
    """Structured analytics report for a timetable."""
    timetable_id: int
    total_sections: int
    total_slots: int
    teaching_slots: int
    free_slots: int
    lunch_slots: int
    slot_type_distribution: dict[str, int] = field(default_factory=dict)
    room_utilisation_pct: float = 0.0
    faculty_utilisation_pct: float = 0.0
    avg_daily_load_per_section: float = 0.0
    subject_distribution: dict[str, int] = field(default_factory=dict)
    busiest_day: str = ""
    lightest_day: str = ""
    quality_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timetable_id": self.timetable_id,
            "total_sections": self.total_sections,
            "total_slots": self.total_slots,
            "teaching_slots": self.teaching_slots,
            "free_slots": self.free_slots,
            "lunch_slots": self.lunch_slots,
            "slot_type_distribution": self.slot_type_distribution,
            "room_utilisation_pct": round(self.room_utilisation_pct, 2),
            "faculty_utilisation_pct": round(self.faculty_utilisation_pct, 2),
            "avg_daily_load_per_section": round(self.avg_daily_load_per_section, 2),
            "subject_distribution": self.subject_distribution,
            "busiest_day": self.busiest_day,
            "lightest_day": self.lightest_day,
            "quality_score": round(self.quality_score, 2),
        }


class TimetableMetrics:
    """
    Analytics engine that computes KPIs from a list of SlotRow records.

    Usage:
        metrics = TimetableMetrics(timetable_id=1, slots=slot_rows)
        report = metrics.compute()
        print(report.to_dict())
    """

    def __init__(self, timetable_id: int, slots: list[SlotRow]) -> None:
        self._id = timetable_id
        self._slots = slots

    def compute(self) -> TimetableAnalytics:
        """Compute and return the full analytics report."""
        if not self._slots:
            return TimetableAnalytics(timetable_id=self._id, total_sections=0, total_slots=0,
                                       teaching_slots=0, free_slots=0, lunch_slots=0)

        section_ids = {s.section_id for s in self._slots}
        teaching_slots = [s for s in self._slots if s.slot_type in {"Theory", "Lab", "Lab_Cont", "Project"}]
        free_slots = [s for s in self._slots if s.slot_type == "Free"]
        lunch_slots = [s for s in self._slots if s.slot_type == "Lunch"]

        type_counts = Counter(s.slot_type for s in self._slots)

        # Room utilisation: unique (day, room, period) combos used / total possible
        total_room_slots = len({s.room_id for s in self._slots if s.room_id}) * DAYS_PER_WEEK * TEACHING_PERIODS_PER_DAY
        used_room_slots = len({(s.day_name, s.room_id, s.period_number) for s in teaching_slots if s.room_id})
        room_util = (used_room_slots / total_room_slots * 100) if total_room_slots else 0.0

        # Faculty utilisation
        faculty_ids = {s.faculty_id for s in self._slots if s.faculty_id and not s.faculty_id.startswith("TBA")}
        total_fac_slots = len(faculty_ids) * DAYS_PER_WEEK * TEACHING_PERIODS_PER_DAY
        used_fac_slots = len({(s.day_name, s.faculty_id, s.period_number) for s in teaching_slots if s.faculty_id})
        fac_util = (used_fac_slots / total_fac_slots * 100) if total_fac_slots else 0.0

        # Average daily load per section
        section_day_loads: dict[str, list[int]] = defaultdict(list)
        sec_day_slots: dict[tuple[str, str], int] = Counter(
            (s.section_id, s.day_name) for s in teaching_slots
        )
        for (sec, day), cnt in sec_day_slots.items():
            section_day_loads[sec].append(cnt)
        avg_load = (
            sum(sum(v) / len(v) for v in section_day_loads.values()) / len(section_day_loads)
            if section_day_loads else 0.0
        )

        # Subject distribution
        subj_dist = Counter(s.subject_name for s in teaching_slots if s.subject_name)

        # Busiest / lightest day
        day_loads = Counter(s.day_name for s in teaching_slots)
        busiest = max(day_loads, key=day_loads.get, default="")
        lightest = min(day_loads, key=day_loads.get, default="")

        # Quality score (0–100): penalise low utilisation and imbalanced loads
        quality = self._compute_quality_score(room_util, fac_util, avg_load, day_loads)

        return TimetableAnalytics(
            timetable_id=self._id,
            total_sections=len(section_ids),
            total_slots=len(self._slots),
            teaching_slots=len(teaching_slots),
            free_slots=len(free_slots),
            lunch_slots=len(lunch_slots),
            slot_type_distribution=dict(type_counts),
            room_utilisation_pct=room_util,
            faculty_utilisation_pct=fac_util,
            avg_daily_load_per_section=avg_load,
            subject_distribution=dict(subj_dist.most_common(20)),
            busiest_day=busiest,
            lightest_day=lightest,
            quality_score=quality,
        )

    def _compute_quality_score(
        self,
        room_util: float,
        fac_util: float,
        avg_load: float,
        day_loads: Counter,
    ) -> float:
        """
        Heuristic quality score 0–100.
        Rewards: high utilisation, balanced day loads, appropriate avg load (4–6).
        Penalises: extremely lopsided days, very low/high avg load.
        """
        score = 100.0

        # Utilisation bonus/penalty (target 60–85%)
        if room_util < 40:
            score -= 10
        elif room_util > 90:
            score -= 5  # over-packed

        # Day balance: coefficient of variation of day loads
        if day_loads:
            vals = list(day_loads.values())
            mean_load = sum(vals) / len(vals)
            if mean_load > 0:
                cv = (sum((v - mean_load) ** 2 for v in vals) / len(vals)) ** 0.5 / mean_load
                score -= min(20, cv * 30)  # penalty up to 20 pts for imbalanced days

        # Average section daily load (ideal 4–6)
        if avg_load < 3:
            score -= 15
        elif avg_load > 7:
            score -= 10

        return max(0.0, min(100.0, score))

    # ── Async helper for DB-backed slots ─────────────────────────
    @classmethod
    async def from_db(cls, timetable_id: int, db: Any) -> "TimetableMetrics":
        """
        Build a TimetableMetrics from the database.

        Args:
            timetable_id: Primary key of the Timetable record.
            db:           AsyncSession instance.
        """
        from sqlalchemy import select
        from schedulo.models import TimetableSlot, Room

        result = await db.execute(
            select(TimetableSlot).where(TimetableSlot.timetable_id == timetable_id)
        )
        db_slots = result.scalars().all()

        slot_rows: list[SlotRow] = []
        for s in db_slots:
            # Fetch room capacity
            room_cap = 60
            if s.room_id:
                r_res = await db.execute(select(Room).where(Room.id == s.room_id))
                room = r_res.scalar_one_or_none()
                if room:
                    room_cap = room.capacity or 60

            slot_rows.append(SlotRow(
                section_id=str(s.section_id or ""),
                day_name=s.day_name or "",
                period_number=s.period_number or 0,
                slot_type=s.slot_type or "Theory",
                subject_name=s.cell_display_line1 or "",
                faculty_id=str(s.faculty_id or ""),
                faculty_name=s.cell_display_line2 or "",
                room_id=str(s.room_id or ""),
                room_type=s.cell_display_line3 or "",
                room_capacity=room_cap,
            ))

        return cls(timetable_id=timetable_id, slots=slot_rows)
