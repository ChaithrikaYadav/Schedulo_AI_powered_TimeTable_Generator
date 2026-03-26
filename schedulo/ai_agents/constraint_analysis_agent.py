"""
schedulo/ai_agents/constraint_analysis_agent.py
ConstraintAnalysisAgent — LangGraph node that scans a generated timetable
for constraint violations and produces a structured violation report.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    total_violations: int
    critical_violations: int
    high_violations: int
    soft_violations: int
    violation_details: list[dict[str, Any]] = field(default_factory=list)
    overall_feasible: bool = True

    def to_state(self) -> dict[str, Any]:
        return {
            "analysis_total_violations": self.total_violations,
            "analysis_critical": self.critical_violations,
            "analysis_high": self.high_violations,
            "analysis_soft": self.soft_violations,
            "analysis_violations": self.violation_details,
            "timetable_feasible": self.overall_feasible,
        }


class ConstraintAnalysisAgent:
    """
    LangGraph node that runs the ConflictDetector on a timetable and
    summarises all hard and soft constraint violations.

    Wiring:
        builder.add_node("analyse_constraints", ConstraintAnalysisAgent(db).run)
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        State expects:
            timetable_id: int

        Returns:
            analysis_total_violations, analysis_critical, analysis_high,
            analysis_soft, analysis_violations, timetable_feasible
        """
        timetable_id: int = state.get("timetable_id", 0)
        logger.info(f"ConstraintAnalysisAgent: analysing timetable_id={timetable_id}")

        result = await self._analyse(timetable_id)
        logger.info(
            f"ConstraintAnalysisAgent: {result.critical_violations} critical, "
            f"{result.high_violations} high, {result.soft_violations} soft"
        )
        return {**state, **result.to_state()}

    async def _analyse(self, timetable_id: int) -> AnalysisResult:
        from schedulo.conflict_detector.detector import ConflictDetector, SlotData, ConflictSeverity
        from schedulo.models import TimetableSlot
        from sqlalchemy import select

        if not self._db:
            return AnalysisResult(0, 0, 0, 0, [], overall_feasible=True)

        # Load slots from DB
        result = await self._db.execute(
            select(TimetableSlot).where(TimetableSlot.timetable_id == timetable_id)
        )
        db_slots = result.scalars().all()

        slot_data = [
            SlotData(
                slot_id=s.id,
                timetable_id=s.timetable_id,
                section_id=str(s.section_id or ""),
                day_name=s.day_name or "",
                period_number=s.period_number or 0,
                period_label=s.period_label or "",
                slot_type=s.slot_type or "Theory",
                subject_name=s.cell_display_line1 or "",
                faculty_id=str(s.faculty_id or ""),
                faculty_name=s.cell_display_line2 or "",
                room_id=str(s.room_id or ""),
                room_type="",
                elective_group=s.extra_json.get("elective_group_code", "") if s.extra_json else "",
            )
            for s in db_slots
        ]

        detector = ConflictDetector(slot_data)
        reports = detector.scan_all()

        critical = sum(1 for r in reports if r.severity.value == "CRITICAL")
        high = sum(1 for r in reports if r.severity.value == "HIGH")
        soft = sum(1 for r in reports if r.severity.value in {"MEDIUM", "LOW", "INFO"})

        return AnalysisResult(
            total_violations=len(reports),
            critical_violations=critical,
            high_violations=high,
            soft_violations=soft,
            violation_details=[r.to_dict() for r in reports],
            overall_feasible=(critical == 0 and high == 0),
        )
