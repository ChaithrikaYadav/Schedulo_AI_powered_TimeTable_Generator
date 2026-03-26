"""
schedulo/scheduler_core/phase5_rooms.py
Phase 5 — Room Assignment (First Fit Decreasing Bin Packing)

Used as a post-pass to fill in any slots that Phase 4 could not assign a room to,
and to provide the FFD room-selection helper used by Phase 4 internally.

Algorithm: First Fit Decreasing (FFD)
  - Sort slots by constraint complexity DESC (Labs > Theory > Project)
  - For each slot, find the first eligible free room of the correct type
  - Fallback: any free room of the correct type (ignoring capacity)
  - Tie-break: alphabetical room_id_str

Complexity: O(n log n) sort + O(n × r) first-fit scan, acceptable for our scale.
"""

from __future__ import annotations

import logging

from schedulo.scheduler_core.models import RoomSlot, SubjectDemand

logger = logging.getLogger(__name__)


def compute_room_constraint_score(
    subject_type: str,
    section_strength: int = 60,
) -> float:
    """
    Assign a constraint complexity score for FFD ordering.
    Higher score = more constrained = assign room first.
    """
    type_scores: dict[str, float] = {
        "lab":     100.0,
        "theory":   50.0,
        "project":  10.0,
    }
    base = type_scores.get(subject_type.strip().lower(), 10.0)
    size = min(section_strength, 60) / 60.0 * 20.0   # 0–20 bonus for larger sections
    return base + size


def first_fit_room(
    subject_type: str,
    section_strength: int,
    day: int,
    period: int,
    rooms: list[RoomSlot],
) -> RoomSlot | None:
    """
    First Fit Decreasing room selection for a single slot.

    Preferred room type:
        Lab → "lab" or "computer lab"
        Theory/Project → "classroom" or "special"

    Tries:
      1. Correct type + sufficient capacity + free
      2. Correct type + free (ignores capacity)
      3. Any room that is free (last resort)

    Returns the chosen RoomSlot (already occupied) or None if no room available.
    """
    is_lab = subject_type.strip().lower() == "lab"
    preferred_types = {"lab", "computer lab"} if is_lab else {"classroom", "special"}

    # Sort rooms to ensure deterministic first-fit selection
    sorted_rooms = sorted(rooms, key=lambda r: r.room_id_str)

    # Attempt 1: correct type + capacity + free
    for room in sorted_rooms:
        if (
            room.room_type.strip().lower() in preferred_types
            and room.capacity >= section_strength
            and room.is_free(day, period)
        ):
            room.occupy(day, period)
            return room

    # Attempt 2: correct type (ignore capacity)
    for room in sorted_rooms:
        if room.room_type.strip().lower() in preferred_types and room.is_free(day, period):
            room.occupy(day, period)
            return room

    # Attempt 3: any free room
    for room in sorted_rooms:
        if room.is_free(day, period):
            room.occupy(day, period)
            return room

    logger.warning(
        f"Phase5: no room available for {subject_type} "
        f"day={day} period={period}"
    )
    return None


def ffd_assign_rooms(
    pending: list[tuple[SubjectDemand, int, int]],  # (demand, day, period)
    rooms: list[RoomSlot],
    section_strengths: dict[int, int],               # section_id → strength
) -> dict[tuple[int, int, int], RoomSlot]:            # (section_id, day, period) → RoomSlot
    """
    First Fit Decreasing room assignment for a batch of pending slots.

    Used as a post-pass to fill NULL-room slots produced by Phase 4.

    Returns dict mapping (section_id, day, period) → RoomSlot.
    """
    # FFD Step 1: sort by constraint complexity DESC
    scored = [
        (d, day, period, compute_room_constraint_score(
            d.subject_type,
            section_strengths.get(d.section_id, 60),
        ))
        for d, day, period in pending
    ]
    scored.sort(key=lambda x: -x[3])

    assignments: dict[tuple[int, int, int], RoomSlot] = {}
    for demand, day, period, _ in scored:
        strength = section_strengths.get(demand.section_id, 60)
        chosen = first_fit_room(demand.subject_type, strength, day, period, rooms)
        if chosen:
            assignments[(demand.section_id, day, period)] = chosen

    return assignments
