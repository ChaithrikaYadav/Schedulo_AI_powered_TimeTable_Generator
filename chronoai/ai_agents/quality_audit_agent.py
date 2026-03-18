"""
chronoai/ai_agents/quality_audit_agent.py
QualityAuditAgent — LangGraph node that scores the timetable quality
using TimetableMetrics and stores results in the Timetable record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AuditResult:
    timetable_id: int
    quality_score: float
    metrics: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_state(self) -> dict[str, Any]:
        return {
            "quality_score": self.quality_score,
            "quality_metrics": self.metrics,
            "quality_recommendations": self.recommendations,
            "audit_timetable_id": self.timetable_id,
        }


class QualityAuditAgent:
    """
    LangGraph node that:
      1. Computes TimetableMetrics analytics report
      2. Generates human-readable improvement recommendations
      3. Stores the quality_score back to the Timetable DB record

    Wiring:
        builder.add_node("audit_quality", QualityAuditAgent(db).run)
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        State expects:
            timetable_id: int

        Returns:
            quality_score, quality_metrics, quality_recommendations
        """
        timetable_id: int = state.get("timetable_id", 0)
        logger.info(f"QualityAuditAgent: auditing timetable_id={timetable_id}")
        result = await self._audit(timetable_id)
        logger.info(f"QualityAuditAgent: quality_score={result.quality_score:.1f}")
        return {**state, **result.to_state()}

    async def _audit(self, timetable_id: int) -> AuditResult:
        if not self._db:
            return AuditResult(timetable_id=0, quality_score=0.0)

        from chronoai.analytics_dashboard.metrics import TimetableMetrics
        from chronoai.models import Timetable
        from sqlalchemy import select

        try:
            metrics_engine = await TimetableMetrics.from_db(timetable_id, self._db)
            analytics = metrics_engine.compute()
            recommendations = self._generate_recommendations(analytics)

            # Persist quality_score to Timetable record
            tt_result = await self._db.execute(
                select(Timetable).where(Timetable.id == timetable_id)
            )
            timetable = tt_result.scalar_one_or_none()
            if timetable:
                timetable.quality_score = analytics.quality_score
                timetable.status = "published"
                await self._db.commit()

            return AuditResult(
                timetable_id=timetable_id,
                quality_score=analytics.quality_score,
                metrics=analytics.to_dict(),
                recommendations=recommendations,
            )

        except Exception as exc:
            logger.exception("QualityAuditAgent: audit failed")
            return AuditResult(
                timetable_id=timetable_id,
                quality_score=0.0,
                metrics={"error": str(exc)},
            )

    def _generate_recommendations(self, analytics: Any) -> list[str]:
        """Generate human-readable improvement suggestions."""
        recs: list[str] = []

        if analytics.room_utilisation_pct < 50:
            recs.append(
                f"Room utilisation is low ({analytics.room_utilisation_pct:.1f}%). "
                "Consider reducing the number of rooms or consolidating sections."
            )
        if analytics.room_utilisation_pct > 90:
            recs.append(
                f"Room utilisation is very high ({analytics.room_utilisation_pct:.1f}%). "
                "Consider adding additional rooms or staggering class times."
            )
        if analytics.faculty_utilisation_pct < 40:
            recs.append(
                "Faculty utilisation is low. Review faculty workload assignments."
            )
        if analytics.avg_daily_load_per_section < 3:
            recs.append(
                f"Average daily section load is low ({analytics.avg_daily_load_per_section:.1f} periods). "
                "Consider increasing subjects or adding elective options."
            )
        if analytics.avg_daily_load_per_section > 7:
            recs.append(
                f"Average daily load ({analytics.avg_daily_load_per_section:.1f}) is high. "
                "Students may experience fatigue — redistribute across more days."
            )
        if analytics.busiest_day and analytics.lightest_day:
            recs.append(
                f"Day load imbalance detected: {analytics.busiest_day} is the busiest, "
                f"{analytics.lightest_day} is lightest. Evening spread would improve balance."
            )
        if analytics.quality_score >= 85:
            recs.append("✅ Timetable quality is excellent. Minimal improvements needed.")
        elif analytics.quality_score < 60:
            recs.append(
                "⚠️ Quality score is below 60. Consider re-running the generator with a "
                "different seed or adjusting subject-to-faculty assignments."
            )

        return recs
