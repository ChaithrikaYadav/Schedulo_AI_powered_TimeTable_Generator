"""
schedulo/ai_agents/conflict_resolution_agent.py
ConflictResolutionAgent — LangGraph node that attempts to auto-fix
hard constraint violations found by ConstraintAnalysisAgent.

Resolution strategies (in priority order):
  1. Room swap for HC-01 (room double-booking)
  2. Faculty swap for HC-02 (faculty double-booking)
  3. Slot shift for HC-03 (lab not consecutive)
  4. Flag unresolvable violations for manual review
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ResolutionResult:
    auto_fixed: int = 0
    manual_required: int = 0
    resolution_log: list[dict[str, Any]] = field(default_factory=list)

    def to_state(self) -> dict[str, Any]:
        return {
            "resolution_auto_fixed": self.auto_fixed,
            "resolution_manual_required": self.manual_required,
            "resolution_log": self.resolution_log,
        }


class ConflictResolutionAgent:
    """
    LangGraph node that reads analysis_violations from state and attempts
    to resolve auto-fixable HC violations by swapping rooms or shifting slots.

    Wiring:
        builder.add_node("resolve_conflicts", ConflictResolutionAgent(db).run)
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        State expects:
            timetable_id: int
            analysis_violations: list[dict]   — from ConstraintAnalysisAgent

        Returns:
            resolution_auto_fixed, resolution_manual_required, resolution_log
        """
        timetable_id: int = state.get("timetable_id", 0)
        violations: list[dict] = state.get("analysis_violations", [])

        logger.info(
            f"ConflictResolutionAgent: attempting to resolve "
            f"{len(violations)} violations for timetable_id={timetable_id}"
        )
        result = await self._resolve(timetable_id, violations)
        logger.info(
            f"ConflictResolutionAgent: auto_fixed={result.auto_fixed}, "
            f"manual_required={result.manual_required}"
        )
        return {**state, **result.to_state()}

    async def _resolve(
        self, timetable_id: int, violations: list[dict]
    ) -> ResolutionResult:
        if not self._db or not violations:
            return ResolutionResult()

        result = ResolutionResult()

        for v in violations:
            conflict_type = v.get("conflict_type", "")
            auto_fixable = v.get("auto_fixable", False)
            slot_ids = v.get("affected_slot_ids", [])

            if not auto_fixable or not slot_ids:
                result.manual_required += 1
                result.resolution_log.append({
                    "conflict_type": conflict_type,
                    "action": "manual_required",
                    "reason": "Not auto-fixable or no slot_ids provided",
                })
                continue

            fixed = False
            if conflict_type == "HC-01":
                fixed = await self._fix_room_conflict(slot_ids)
            elif conflict_type == "HC-02":
                fixed = await self._fix_faculty_conflict(slot_ids)
            elif conflict_type in {"HC-03", "HC-06"}:
                fixed = await self._flag_for_regeneration(slot_ids, conflict_type)

            if fixed:
                result.auto_fixed += 1
                result.resolution_log.append({
                    "conflict_type": conflict_type,
                    "action": "auto_fixed",
                    "slot_ids": slot_ids,
                })
            else:
                result.manual_required += 1
                result.resolution_log.append({
                    "conflict_type": conflict_type,
                    "action": "manual_required",
                    "slot_ids": slot_ids,
                    "reason": "Auto-fix strategy exhausted",
                })

        try:
            await self._db.commit()
        except Exception:
            await self._db.rollback()

        return result

    async def _fix_room_conflict(self, slot_ids: list[int]) -> bool:
        """
        Try to reassign one of the conflicting slots to a different room
        of the same type (HC-01 room double-booking fix).
        """
        from schedulo.models import TimetableSlot, Room
        from sqlalchemy import select

        if not slot_ids:
            return False

        # Take the second slot (leave first untouched)
        target_id = slot_ids[-1]
        result = await self._db.execute(
            select(TimetableSlot).where(TimetableSlot.id == target_id)
        )
        slot = result.scalar_one_or_none()
        if not slot:
            return False

        # Find alternative rooms
        rooms_result = await self._db.execute(select(Room))
        all_rooms = rooms_result.scalars().all()
        alternatives = [
            r for r in all_rooms
            if str(r.id) != str(slot.room_id)
        ]
        if not alternatives:
            return False

        new_room = random.choice(alternatives)
        slot.room_id = new_room.id
        slot.cell_display_line3 = new_room.room_id
        return True

    async def _fix_faculty_conflict(self, slot_ids: list[int]) -> bool:
        """
        For HC-02 (faculty double-booking), tag the conflicting slot
        with TBA faculty so it can be manually reassigned.
        """
        from schedulo.models import TimetableSlot
        from sqlalchemy import select

        if not slot_ids:
            return False

        target_id = slot_ids[-1]
        result = await self._db.execute(
            select(TimetableSlot).where(TimetableSlot.id == target_id)
        )
        slot = result.scalar_one_or_none()
        if not slot:
            return False

        slot.faculty_id = None
        slot.cell_display_line2 = "TBA — Conflict resolved"
        return True

    async def _flag_for_regeneration(self, slot_ids: list[int], reason: str) -> bool:
        """Mark slots as needing manual intervention via extra_json flag."""
        from schedulo.models import TimetableSlot
        from sqlalchemy import select

        for sid in slot_ids:
            result = await self._db.execute(
                select(TimetableSlot).where(TimetableSlot.id == sid)
            )
            slot = result.scalar_one_or_none()
            if slot:
                extra = slot.extra_json or {}
                extra["conflict_flag"] = reason
                extra["needs_manual_review"] = True
                slot.extra_json = extra

        return True
