"""
chronoai/ai_agents/chatbot_modification_agent.py
ChatbotModificationAgent — LangGraph node that applies validated
timetable modifications requested through ChronoBot.

Supported operations:
  F1: swap_slots         — swap two TimetableSlot records
  F2: move_slot          — move slot to different day/period
  F3: reassign_faculty   — change faculty for a slot
  F4: reassign_room      — change room for a slot
  F5: lock_slot          — mark slot as locked (prevent future changes)
  F6: unlock_slot        — remove lock from slot
  F7: bulk_update        — apply multiple changes atomically
  F8: undo_last_change   — revert the last applied modification
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ModificationResult:
    success: bool
    operation: str
    affected_slot_ids: list[int] = field(default_factory=list)
    error: str = ""
    before_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_state(self) -> dict[str, Any]:
        return {
            "modification_success": self.success,
            "modification_operation": self.operation,
            "modification_affected_slots": self.affected_slot_ids,
            "modification_error": self.error,
        }


class ChatbotModificationAgent:
    """
    LangGraph node that applies ChronoBot-requested timetable mutations
    after constraint validation passes.

    Wiring:
        builder.add_node("apply_modification", ChatbotModificationAgent(db).run)
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db
        self._undo_stack: list[dict[str, Any]] = []

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        State expects:
            modification_request: dict with keys:
                operation: str          — one of F1–F8 operation codes
                slot_id: int            — primary TimetableSlot id
                target_slot_id: int     — for swap operations
                new_day: str            — for move operations
                new_period: int         — for move operations
                new_faculty_id: int     — for reassign_faculty
                new_room_id: int        — for reassign_room
                changes: list[dict]     — for bulk_update
                confirmed: bool         — must be True to apply

        Returns:
            modification_success, modification_operation,
            modification_affected_slots, modification_error
        """
        req = state.get("modification_request", {})
        if not req:
            return {**state, **ModificationResult(
                success=False, operation="none", error="No modification_request in state"
            ).to_state()}

        if not req.get("confirmed", False):
            return {**state, **ModificationResult(
                success=False,
                operation=req.get("operation", ""),
                error="Modification not confirmed. Set confirmed=true to apply.",
            ).to_state()}

        op = req.get("operation", "")
        result = await self._dispatch(op, req)
        logger.info(f"ChatbotModificationAgent: {op} → success={result.success}")
        return {**state, **result.to_state()}

    async def _dispatch(self, operation: str, req: dict) -> ModificationResult:
        match operation:
            case "swap_slots":
                return await self._swap_slots(req["slot_id"], req["target_slot_id"])
            case "move_slot":
                return await self._move_slot(req["slot_id"], req["new_day"], req["new_period"])
            case "reassign_faculty":
                return await self._reassign_faculty(req["slot_id"], req["new_faculty_id"])
            case "reassign_room":
                return await self._reassign_room(req["slot_id"], req["new_room_id"])
            case "lock_slot":
                return await self._set_lock(req["slot_id"], locked=True)
            case "unlock_slot":
                return await self._set_lock(req["slot_id"], locked=False)
            case "bulk_update":
                return await self._bulk_update(req.get("changes", []))
            case "undo_last_change":
                return await self._undo()
            case _:
                return ModificationResult(
                    success=False,
                    operation=operation,
                    error=f"Unknown operation: {operation}",
                )

    async def _get_slot(self, slot_id: int) -> Any | None:
        from chronoai.models import TimetableSlot
        from sqlalchemy import select
        result = await self._db.execute(
            select(TimetableSlot).where(TimetableSlot.id == slot_id)
        )
        return result.scalar_one_or_none()

    def _snapshot(self, slot: Any) -> dict[str, Any]:
        """Capture a before-state snapshot for undo."""
        return {
            "slot_id": slot.id,
            "day_name": slot.day_name,
            "period_number": slot.period_number,
            "faculty_id": slot.faculty_id,
            "room_id": slot.room_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _swap_slots(self, slot_id_a: int, slot_id_b: int) -> ModificationResult:
        slot_a = await self._get_slot(slot_id_a)
        slot_b = await self._get_slot(slot_id_b)
        if not slot_a or not slot_b:
            return ModificationResult(success=False, operation="swap_slots",
                                      error="One or both slot IDs not found")

        snap = [self._snapshot(slot_a), self._snapshot(slot_b)]
        # Swap day + period
        slot_a.day_name, slot_b.day_name = slot_b.day_name, slot_a.day_name
        slot_a.period_number, slot_b.period_number = slot_b.period_number, slot_a.period_number
        slot_a.period_label, slot_b.period_label = slot_b.period_label, slot_a.period_label
        await self._db.commit()
        self._undo_stack.append({"op": "swap_slots", "snapshots": snap,
                                  "ids": [slot_id_a, slot_id_b]})
        return ModificationResult(success=True, operation="swap_slots",
                                  affected_slot_ids=[slot_id_a, slot_id_b],
                                  before_snapshot={"snapshots": snap})

    async def _move_slot(self, slot_id: int, new_day: str, new_period: int) -> ModificationResult:
        slot = await self._get_slot(slot_id)
        if not slot:
            return ModificationResult(success=False, operation="move_slot",
                                      error=f"Slot {slot_id} not found")

        snap = self._snapshot(slot)
        slot.day_name = new_day
        slot.period_number = new_period
        await self._db.commit()
        self._undo_stack.append({"op": "move_slot", "snapshot": snap, "id": slot_id})
        return ModificationResult(success=True, operation="move_slot",
                                  affected_slot_ids=[slot_id])

    async def _reassign_faculty(self, slot_id: int, new_faculty_id: int) -> ModificationResult:
        from chronoai.models import Faculty
        from sqlalchemy import select

        slot = await self._get_slot(slot_id)
        if not slot:
            return ModificationResult(success=False, operation="reassign_faculty",
                                      error=f"Slot {slot_id} not found")

        fac_result = await self._db.execute(select(Faculty).where(Faculty.id == new_faculty_id))
        faculty = fac_result.scalar_one_or_none()
        if not faculty:
            return ModificationResult(success=False, operation="reassign_faculty",
                                      error=f"Faculty ID {new_faculty_id} not found")

        snap = self._snapshot(slot)
        slot.faculty_id = faculty.id
        slot.cell_display_line2 = faculty.name
        await self._db.commit()
        self._undo_stack.append({"op": "reassign_faculty", "snapshot": snap, "id": slot_id})
        return ModificationResult(success=True, operation="reassign_faculty",
                                  affected_slot_ids=[slot_id])

    async def _reassign_room(self, slot_id: int, new_room_id: int) -> ModificationResult:
        from chronoai.models import Room
        from sqlalchemy import select

        slot = await self._get_slot(slot_id)
        if not slot:
            return ModificationResult(success=False, operation="reassign_room",
                                      error=f"Slot {slot_id} not found")

        room_result = await self._db.execute(select(Room).where(Room.id == new_room_id))
        room = room_result.scalar_one_or_none()
        if not room:
            return ModificationResult(success=False, operation="reassign_room",
                                      error=f"Room ID {new_room_id} not found")

        snap = self._snapshot(slot)
        slot.room_id = room.id
        slot.cell_display_line3 = room.room_id
        await self._db.commit()
        self._undo_stack.append({"op": "reassign_room", "snapshot": snap, "id": slot_id})
        return ModificationResult(success=True, operation="reassign_room",
                                  affected_slot_ids=[slot_id])

    async def _set_lock(self, slot_id: int, locked: bool) -> ModificationResult:
        slot = await self._get_slot(slot_id)
        if not slot:
            return ModificationResult(success=False,
                                      operation="lock_slot" if locked else "unlock_slot",
                                      error=f"Slot {slot_id} not found")
        extra = slot.extra_json or {}
        extra["locked"] = locked
        slot.extra_json = extra
        await self._db.commit()
        op = "lock_slot" if locked else "unlock_slot"
        return ModificationResult(success=True, operation=op, affected_slot_ids=[slot_id])

    async def _bulk_update(self, changes: list[dict]) -> ModificationResult:
        affected: list[int] = []
        for change in changes:
            op = change.get("operation", "")
            sid = change.get("slot_id", 0)
            sub_req = {**change, "confirmed": True}
            sub_result = await self._dispatch(op, sub_req)
            if sub_result.success:
                affected.extend(sub_result.affected_slot_ids)
        return ModificationResult(success=True, operation="bulk_update",
                                  affected_slot_ids=affected)

    async def _undo(self) -> ModificationResult:
        if not self._undo_stack:
            return ModificationResult(success=False, operation="undo",
                                      error="Nothing to undo")

        last = self._undo_stack.pop()
        op = last.get("op")
        affected: list[int] = []

        if op == "swap_slots":
            snaps = last.get("snapshots", [])
            for snap in snaps:
                slot = await self._get_slot(snap["slot_id"])
                if slot:
                    slot.day_name = snap["day_name"]
                    slot.period_number = snap["period_number"]
                    affected.append(snap["slot_id"])
        elif op in {"move_slot", "reassign_faculty", "reassign_room"}:
            snap = last.get("snapshot", {})
            slot_id = snap.get("slot_id")
            if slot_id:
                slot = await self._get_slot(slot_id)
                if slot:
                    slot.day_name = snap.get("day_name", slot.day_name)
                    slot.period_number = snap.get("period_number", slot.period_number)
                    slot.faculty_id = snap.get("faculty_id", slot.faculty_id)
                    slot.room_id = snap.get("room_id", slot.room_id)
                    affected.append(slot_id)

        await self._db.commit()
        return ModificationResult(success=True, operation="undo_last_change",
                                  affected_slot_ids=affected)
