"""
chronoai/ai_agents/scheduler_agent.py
SchedulerAgent — LangGraph node that runs the PrototypeScheduler and
persists generated timetable slots into the database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SchedulerResult:
    timetable_id: int
    sections_generated: list[str] = field(default_factory=list)
    total_slots: int = 0
    errors: list[str] = field(default_factory=list)
    success: bool = True

    def to_state(self) -> dict[str, Any]:
        return {
            "timetable_id": self.timetable_id,
            "scheduler_sections": self.sections_generated,
            "scheduler_total_slots": self.total_slots,
            "scheduler_errors": self.errors,
            "scheduler_success": self.success,
        }


class SchedulerAgent:
    """
    LangGraph node that:
      1. Runs PrototypeScheduler.build_all() for the requested department
      2. Persists the resulting DataFrames as TimetableSlot rows
      3. Creates a Timetable record in the DB

    Wiring:
        builder.add_node("generate_timetable", SchedulerAgent(db).run)
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        State expects:
            department: str          — full department name
            random_seed: int|None    — optional reproducibility seed
            academic_year: str       — e.g. "2024-25"

        Returns:
            timetable_id, scheduler_sections, scheduler_total_slots,
            scheduler_errors, scheduler_success
        """
        dept = state.get("department", "School of Computer Science & Engineering")
        seed = state.get("random_seed")
        academic_year = state.get("academic_year", "2024-25")

        logger.info(f"SchedulerAgent: generating for {dept}")
        result = await self._generate(dept, seed, academic_year)
        logger.info(
            f"SchedulerAgent: timetable_id={result.timetable_id}, "
            f"sections={len(result.sections_generated)}, slots={result.total_slots}"
        )
        return {**state, **result.to_state()}

    async def _generate(
        self,
        department: str,
        seed: int | None,
        academic_year: str,
    ) -> SchedulerResult:
        if not self._db:
            return SchedulerResult(
                timetable_id=0,
                success=False,
                errors=["No DB session provided to SchedulerAgent"],
            )

        from chronoai.scheduler_core.prototype_scheduler import PrototypeScheduler
        from chronoai.models import Timetable, TimetableSlot, Section
        from sqlalchemy import select

        try:
            # Create Timetable record
            timetable = Timetable(
                department=department,
                academic_year=academic_year,
                status="generating",
                generation_method="PrototypeScheduler_v1",
                created_at=datetime.utcnow(),
            )
            self._db.add(timetable)
            await self._db.flush()
            timetable_id = timetable.id

            # Run the scheduler
            scheduler = PrototypeScheduler(random_seed=seed)
            timetables_dict = scheduler.build_all(department=department)

            total_slots = 0
            sections_generated: list[str] = []

            for section_id, df in timetables_dict.items():
                # Lookup section DB record
                sec_result = await self._db.execute(
                    select(Section).where(Section.section_id == section_id)
                )
                section = sec_result.scalar_one_or_none()
                section_pk = section.id if section else None

                for day_name, row in df.iterrows():
                    for period_idx, (period_label, cell_text) in enumerate(row.items()):
                        if not cell_text or cell_text == "":
                            slot_type = "Free"
                            line1 = ""
                        elif cell_text == "LUNCH BREAK 🍴":
                            slot_type = "Lunch"
                            line1 = "Lunch Break"
                        else:
                            lines = str(cell_text).split("\n")
                            line1 = lines[0] if len(lines) > 0 else ""
                            slot_type = "Lab" if "(Lab)" in line1 else (
                                "Lab_Cont" if "(Lab cont.)" in line1 else "Theory"
                            )

                        lines = str(cell_text).split("\n") if cell_text else []
                        self._db.add(TimetableSlot(
                            timetable_id=timetable_id,
                            section_id=section_pk,
                            day_name=str(day_name),
                            period_number=period_idx + 1,
                            period_label=str(period_label),
                            slot_type=slot_type,
                            cell_display_line1=lines[0] if len(lines) > 0 else "",
                            cell_display_line2=lines[1] if len(lines) > 1 else "",
                            cell_display_line3=lines[2] if len(lines) > 2 else "",
                        ))
                        total_slots += 1

                sections_generated.append(section_id)

            # Update timetable status
            timetable.status = "draft"
            await self._db.commit()

            return SchedulerResult(
                timetable_id=timetable_id,
                sections_generated=sections_generated,
                total_slots=total_slots,
                success=True,
            )

        except Exception as exc:
            logger.exception("SchedulerAgent: generation failed")
            await self._db.rollback()
            return SchedulerResult(
                timetable_id=0,
                success=False,
                errors=[str(exc)],
            )
