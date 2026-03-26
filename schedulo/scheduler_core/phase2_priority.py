"""
schedulo/scheduler_core/phase2_priority.py
Phase 2 — Priority Queue Ordering (CPU Scheduling Algorithms)

Implements Multi-Level Queue (MLQ) + Longest Job First (LJF) ordering.
Labs → Queue 0 (highest priority, scarce Lab rooms)
Theory → Queue 1
Project → Queue 2 (lowest priority, most flexible)

Within each queue: LJF — most total-slots-needed first (inverted SJF).
This prevents high-credit subjects being starved of valid spread slots.
"""

from __future__ import annotations

import logging

from schedulo.scheduler_core.models import SubjectDemand

logger = logging.getLogger(__name__)

# Multi-Level Queue assignment
QUEUE_ASSIGNMENTS: dict[str, int] = {
    "Lab":     0,   # Highest — Lab rooms are scarce (only ~15 in DB)
    "Theory":  1,   # Medium
    "Project": 2,   # Lowest — single period, any room
}

# Credit weight used in LJF priority score
CREDIT_WEIGHT: dict[float, float] = {
    5.0: 5.0,
    4.0: 4.0,
    3.0: 3.0,
    2.0: 2.0,
    1.0: 1.0,
}
_DEFAULT_CREDIT_WEIGHT = 1.0


def compute_priority_score(demand: SubjectDemand) -> float:
    """
    Compute a LJF priority score within a queue.
    Higher score = schedule first.

    Components:
        total_slots × credit_weight  — demands needing more slots scheduled first
        +10 bonus for Labs           — Lab room scarcity premium
    """
    total_slots   = demand.weekly_periods * demand.burst_length
    credit_weight = CREDIT_WEIGHT.get(demand.credits, _DEFAULT_CREDIT_WEIGHT)
    lab_bonus     = 10.0 if demand.subject_type.strip().lower() == "lab" else 0.0
    return float(total_slots * credit_weight) + lab_bonus


def order_demands(demands: list[SubjectDemand]) -> list[SubjectDemand]:
    """
    Sort all SubjectDemand items using Multi-Level Queue + LJF within each queue.

    Returns a flat list:  [all Queue-0 items (Labs, LJF)] + [Queue-1 (Theory)] + [Queue-2 (Project)]
    """
    for d in demands:
        d.priority_score = compute_priority_score(d)

    queues: dict[int, list[SubjectDemand]] = {0: [], 1: [], 2: []}
    for d in demands:
        level = QUEUE_ASSIGNMENTS.get(d.subject_type.strip().capitalize(), 2)
        queues[level].append(d)

    ordered: list[SubjectDemand] = []
    for level in (0, 1, 2):
        # LJF: highest priority_score first; tie-break: subject_name alphabetically
        sorted_q = sorted(queues[level], key=lambda d: (-d.priority_score, d.subject_name))
        ordered.extend(sorted_q)

    logger.debug(
        f"Phase2: ordered {len(ordered)} demands — "
        f"Lab={len(queues[0])} Theory={len(queues[1])} Project={len(queues[2])}"
    )
    return ordered
