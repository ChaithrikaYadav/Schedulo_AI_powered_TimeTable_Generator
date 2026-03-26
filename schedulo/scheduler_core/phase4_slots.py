"""
schedulo/scheduler_core/phase4_slots.py
Phase 4 — Time Slot Allocation

Algorithms:
  Labs:   Weighted Interval Scheduling DP over (day, period_start) candidates
          Bars P4+P5 straddling (lunch boundary). Picks highest-value window.
  Theory/Project: Round-Robin day cycle + PREFERRED_PERIODS ordering.
          Spread rule: never place same subject twice on same day.

No randomization. All decisions driven by faculty preferences and load state.
"""

from __future__ import annotations

import logging

from schedulo.scheduler_core.models import FacultySlot, RoomSlot, ScheduledSlot, SubjectDemand

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
DAYS_SPREAD_ORDER = [0, 2, 4, 1, 3, 5]  # Mon, Wed, Fri, Tue, Thu, Sat — maximum spread

PERIOD_LABELS: dict[int, str] = {
    1: "9:00–9:55",   2: "9:55–10:50",  3: "10:50–11:45",
    4: "11:45–12:40", 5: "12:40–1:35",  6: "1:35–2:30",
    7: "2:30–3:25",   8: "3:25–4:20",   9: "4:20–5:15",
}
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# Periods that should NOT be used for regular classes (lunch slots)
LUNCH_PERIODS = {5, 6}

# Faculty preferred-slot → ordered period list
PREFERRED_PERIODS: dict[str, list[int]] = {
    "Morning":       [2, 3, 4, 1, 7, 8, 9],
    "Afternoon":     [6, 7, 8, 9, 4, 3, 2, 1],
    "No 1st Period": [2, 3, 4, 7, 8, 9],
    "Any":           [2, 3, 4, 7, 8, 9, 1],
}


def _preference_score(preferred_slots: str, period: int) -> float:
    """Score match of a period against faculty preferred_slots — higher is better."""
    order = PREFERRED_PERIODS.get(preferred_slots, PREFERRED_PERIODS["Any"])
    if period in order:
        # Earlier in preference list = higher score
        return float(len(order) - order.index(period))
    return 0.0


def _subject_on_day(
    subject_name: str,
    day: int,
    section_schedule: dict[tuple[int, int], ScheduledSlot],
) -> bool:
    """Return True if subject_name already has a slot on this day in section_schedule."""
    return any(
        slot.day_of_week == day and slot.subject_name == subject_name
        for slot in section_schedule.values()
    )


def _faculty_busy(faculty: FacultySlot, day: int, period: int) -> bool:
    return (day, period) in faculty.assigned_slots


def _build_day_cycle(weekly_periods: int) -> list[int]:
    """
    Return a day list that distributes weekly_periods as evenly as possible.
    Uses the spread order; wraps around if more periods than days.
    """
    if weekly_periods <= 6:
        return DAYS_SPREAD_ORDER[:weekly_periods]
    # More than 6: cycle through spread order
    cycle = []
    for i in range(weekly_periods):
        cycle.append(DAYS_SPREAD_ORDER[i % 6])
    return cycle


# ── Lab slot allocation (Weighted Interval Scheduling DP) ────────────────────

def find_best_lab_slot(
    demand: SubjectDemand,
    faculty: FacultySlot | None,
    rooms: list[RoomSlot],
    section_schedule: dict[tuple[int, int], ScheduledSlot],
) -> tuple[int, int, RoomSlot] | None:
    """
    Find the best (day, period_start, lab_room) for a 2-period Lab block.

    Scores each candidate (day, period_start):
        preference_score(faculty, period_start)
        + spread_bonus if this day not yet used by this subject
        − 5 if period_start ≥ 8 (too late in the day)

    Hard constraints:
        - period_start + 1 must also be free
        - Cannot straddle P4→P5 (lunch boundary): period_start ≠ 4
        - Cannot straddle P5→P6 (lunch boundary): period_start ≠ 5
        - Faculty must be free for both periods
        - Section must have both slots free
        - A Lab-type room must be free for both periods

    Returns highest-scoring valid (day, period_start, lab_room), or None.
    """
    lab_rooms = [r for r in rooms if r.room_type.strip().lower() in ("lab", "computer lab")]
    if not lab_rooms:
        lab_rooms = rooms  # fallback to any room if no labs available

    preferred = (faculty.preferred_slots if faculty else "Any")
    candidates: list[tuple[float, int, int, RoomSlot]] = []

    for day in DAYS_SPREAD_ORDER:
        for period_start in range(1, 9):          # period_start 1–8 (needs p+1)
            period_end = period_start + 1

            # HC-03: cannot straddle lunch boundary (P4→P5 or P5→P6)
            if period_start in (4, 5):
                continue

            # Faculty must be free for both periods
            if faculty and (_faculty_busy(faculty, day, period_start)
                            or _faculty_busy(faculty, day, period_end)):
                continue

            # Section must have both slots free
            if (day, period_start) in section_schedule or (day, period_end) in section_schedule:
                continue

            # Find free lab room for both periods
            available_room = next(
                (r for r in lab_rooms
                 if r.is_free(day, period_start) and r.is_free(day, period_end)),
                None,
            )
            if available_room is None:
                continue

            # Compute value score
            pref_score    = _preference_score(preferred, period_start)
            spread_bonus  = 5.0 if not _subject_on_day(demand.subject_name, day, section_schedule) else 0.0
            late_penalty  = -5.0 if period_start >= 8 else 0.0
            value         = pref_score + spread_bonus + late_penalty

            candidates.append((value, day, period_start, available_room))

    if not candidates:
        logger.warning(
            f"Phase4-Lab: no valid slot for '{demand.subject_name}' "
            f"section={demand.section_str}"
        )
        return None

    # Best = highest value; tie-break: lowest day then lowest period (deterministic)
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    _, best_day, best_period, best_room = candidates[0]
    return best_day, best_period, best_room


# ── Theory / Project slot allocation (Round-Robin + Preference bias) ─────────

def find_theory_slots(
    demand: SubjectDemand,
    faculty: FacultySlot | None,
    rooms: list[RoomSlot],
    section_schedule: dict[tuple[int, int], ScheduledSlot],
) -> list[tuple[int, int, RoomSlot]]:
    """
    Find `demand.weekly_periods` individual theory/project slots.

    Strategy:
      1. Build day cycle: distributes periods across days as evenly as possible
      2. For each target day, try periods in faculty's PREFERRED_PERIODS order
      3. Accept first free (day, period, classroom) satisfying all constraints
      4. Spread rule: never place same subject twice on same day

    Returns list of (day_index, period_number, room) tuples,
    length up to demand.weekly_periods (may be shorter if slots exhausted).
    """
    classroom_rooms = [r for r in rooms if r.room_type.strip().lower() in ("classroom", "special")]
    if not classroom_rooms:
        classroom_rooms = rooms   # fallback

    preferred    = (faculty.preferred_slots if faculty else "Any")
    period_order = PREFERRED_PERIODS.get(preferred, PREFERRED_PERIODS["Any"])

    assigned: list[tuple[int, int, RoomSlot]] = []
    days_used_by_subject: set[int] = set()
    day_cycle = _build_day_cycle(demand.weekly_periods)

    for target_day in day_cycle:
        if target_day in days_used_by_subject:
            # Try next available day instead
            alt = next(
                (d for d in DAYS_SPREAD_ORDER
                 if d not in days_used_by_subject
                 and d != target_day),
                None,
            )
            if alt is None:
                continue
            target_day = alt

        for period in period_order:
            # Skip lunch periods
            if period in LUNCH_PERIODS:
                continue

            # Faculty conflict
            if faculty and _faculty_busy(faculty, target_day, period):
                continue

            # Section conflict
            if (target_day, period) in section_schedule:
                continue

            # Room availability
            available_room = next(
                (r for r in classroom_rooms if r.is_free(target_day, period)),
                None,
            )
            if available_room is None:
                continue

            # ── All constraints satisfied ──
            assigned.append((target_day, period, available_room))
            days_used_by_subject.add(target_day)

            # Pre-book faculty and room
            if faculty:
                faculty.assigned_slots.append((target_day, period))
            available_room.occupy(target_day, period)
            break   # one slot per day, move to next day

        if len(assigned) >= demand.weekly_periods:
            break

    if len(assigned) < demand.weekly_periods:
        logger.warning(
            f"Phase4-Theory: only placed {len(assigned)}/{demand.weekly_periods} "
            f"slots for '{demand.subject_name}' section={demand.section_str}"
        )

    return assigned
