"""
schedulo/scheduler_core/phase6_balance.py
Phase 6 — Load Balancing (Round Robin Distribution + HC-04 Lunch Enforcement)

Two passes:
  6a. validate_and_rebalance_spread() — Round Robin: find same-day duplicates
      for a subject and swap to the lightest day. Up to 3 passes max.
  6b. assign_lunch_all_days() — deterministic HC-04 rule: assign exactly one
      LUNCH slot per (section, day). No randomization.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from schedulo.scheduler_core.models import ScheduledSlot, SlotType

logger = logging.getLogger(__name__)

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
_PERIOD_LABELS: dict[int, str] = {
    1: "9:00–9:55",   2: "9:55–10:50",  3: "10:50–11:45",
    4: "11:45–12:40", 5: "12:40–1:35",  6: "1:35–2:30",
    7: "2:30–3:25",   8: "3:25–4:20",   9: "4:20–5:15",
}
_LUNCH_PERIODS = {5, 6}


def _day_name(idx: int) -> str:
    return _DAY_NAMES[idx] if 0 <= idx < 6 else f"Day{idx}"


# ── 6a: Spread Rebalancing ────────────────────────────────────────────────────

def validate_and_rebalance_spread(
    schedule: dict[tuple[int, int], ScheduledSlot],
    max_passes: int = 3,
) -> dict[tuple[int, int], ScheduledSlot]:
    """
    Round-Robin spread rebalancing for a single section's schedule.

    For each pass:
      - Find (subject_name, day) pairs where the subject appears ≥2 times on same day
      - For each duplicate slot: move it to the day with the fewest slots that:
          (a) doesn't already have this subject
          (b) has a free non-lunch period
      - Repeat for up to max_passes

    Returns the rebalanced schedule.
    """
    for pass_num in range(max_passes):
        violations = _find_same_day_duplicates(schedule)
        if not violations:
            break

        logger.debug(f"Phase6-RR: pass {pass_num+1}, {len(violations)} violations")

        for subject_name, day in violations:
            dup_key = _get_duplicate_slot_key(schedule, subject_name, day)
            if dup_key is None:
                continue

            dup_slot = schedule[dup_key]

            # Find lightest day (fewest class slots) that doesn't have this subject
            target_day = _find_lightest_day(schedule, subject_name, exclude_day=day)
            if target_day is None:
                continue

            # Find a free non-lunch period on target_day
            occupied_on_target = {
                k[1] for k in schedule
                if k[0] == target_day
            }
            free_period = next(
                (p for p in range(1, 10)
                 if p not in _LUNCH_PERIODS and p not in occupied_on_target),
                None,
            )
            if free_period is None:
                continue

            # Move the duplicate slot
            del schedule[dup_key]
            dup_slot.day_of_week = target_day
            dup_slot.day_name = _day_name(target_day)
            dup_slot.period_number = free_period
            dup_slot.period_label = _PERIOD_LABELS.get(free_period, f"P{free_period}")
            dup_slot.algorithm_used = (dup_slot.algorithm_used or "") + "+Phase6-RR"
            schedule[(target_day, free_period)] = dup_slot

    return schedule


def _find_same_day_duplicates(
    schedule: dict[tuple[int, int], ScheduledSlot],
) -> list[tuple[str, int]]:
    """Return list of (subject_name, day) with ≥2 non-lunch slots on same day."""
    counts: dict[tuple[str, int], int] = defaultdict(int)
    for slot in schedule.values():
        if slot.slot_type not in (SlotType.LUNCH, SlotType.FREE) and slot.subject_name:
            counts[(slot.subject_name, slot.day_of_week)] += 1
    return [(name, day) for (name, day), cnt in counts.items() if cnt >= 2]


def _get_duplicate_slot_key(
    schedule: dict[tuple[int, int], ScheduledSlot],
    subject_name: str,
    day: int,
) -> tuple[int, int] | None:
    """Return the key of the second occurrence of subject_name on day (to be moved)."""
    found = False
    for key, slot in sorted(schedule.items()):
        if (slot.subject_name == subject_name
                and slot.day_of_week == day
                and slot.slot_type not in (SlotType.LUNCH, SlotType.FREE)
                and not slot.is_lab_continuation):
            if found:
                return key
            found = True
    return None


def _find_lightest_day(
    schedule: dict[tuple[int, int], ScheduledSlot],
    subject_name: str,
    exclude_day: int,
) -> int | None:
    """
    Return the day (0–5) with fewest class slots that does NOT already have subject_name
    and is not exclude_day.
    """
    day_counts: dict[int, int] = defaultdict(int)
    days_with_subject: set[int] = set()
    for slot in schedule.values():
        if slot.slot_type not in (SlotType.LUNCH, SlotType.FREE):
            day_counts[slot.day_of_week] += 1
        if slot.subject_name == subject_name:
            days_with_subject.add(slot.day_of_week)

    eligible_days = [
        d for d in range(6)
        if d != exclude_day and d not in days_with_subject
    ]
    if not eligible_days:
        return None

    # Round-robin: lightest (fewest classes) — tie-break by day index
    return min(eligible_days, key=lambda d: (day_counts[d], d))


# ── 6b: Per-Day Lunch Enforcement (HC-04) ────────────────────────────────────

def assign_lunch_all_days(
    schedule: dict[tuple[int, int], ScheduledSlot],
    section_id: int,
    section_str: str,
) -> dict[tuple[int, int], ScheduledSlot]:
    """
    Assign exactly one LUNCH slot per day for the section.

    HC-04 deterministic rule:
      - Period 4 (11:45–12:40) occupied → lunch = Period 5
      - Period 5 (12:40–1:35) occupied by a class → lunch = Period 6
      - Otherwise → Period 5 (default; earlier lunch preferred)

    If the chosen lunch period already has a class, log an HC-04 warning
    but still place lunch there (prevents infinite deferral).
    """
    for day in range(6):
        # Check period 4 occupancy
        p4_slot = schedule.get((day, 4))
        p4_occupied = (
            p4_slot is not None
            and p4_slot.slot_type not in (SlotType.FREE, SlotType.LUNCH)
        )

        # Check period 5 occupancy
        p5_slot = schedule.get((day, 5))
        p5_class = (
            p5_slot is not None
            and p5_slot.slot_type not in (SlotType.FREE, SlotType.LUNCH)
        )

        if p4_occupied:
            lunch_period = 5
        elif p5_class:
            lunch_period = 6
        else:
            lunch_period = 5   # default

        existing = schedule.get((day, lunch_period))
        if existing and existing.slot_type not in (SlotType.FREE, SlotType.LUNCH):
            logger.warning(
                f"HC-04: section={section_str} day={day} "
                f"period={lunch_period} already has a class — overwriting with LUNCH"
            )

        schedule[(day, lunch_period)] = ScheduledSlot(
            section_id=section_id,
            section_str=section_str,
            day_of_week=day,
            day_name=_day_name(day),
            period_number=lunch_period,
            period_label=_PERIOD_LABELS[lunch_period],
            slot_type=SlotType.LUNCH,
            subject_id=None,
            subject_name="Lunch Break",
            faculty_id=None,
            faculty_name="",
            room_pk=None,
            room_id_str="",
            algorithm_used="Phase6-LunchHC04",
        )

    return schedule
