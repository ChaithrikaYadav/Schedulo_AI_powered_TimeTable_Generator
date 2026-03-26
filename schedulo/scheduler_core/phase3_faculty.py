"""
schedulo/scheduler_core/phase3_faculty.py
Phase 3 — Faculty Assignment (Greedy Weighted Matching)

For each SubjectDemand, selects the best eligible faculty using a deterministic
scoring function. No randomization — tie-break by alphabetical faculty name.

Scoring components:
  1. Subject name match quality (0–100): exact > substring > fuzzy (SequenceMatcher ≥0.55)
  2. Load headroom ratio × 30: prefers less-loaded faculty (distributes evenly)
  3. Lab capability bonus (+20): rewards lab-capable faculty for lab demands
  Hard filters: same department_id, lab-capable for labs, not at max load
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from schedulo.scheduler_core.models import FacultySlot, SubjectDemand

logger = logging.getLogger(__name__)

_IMPOSSIBLE = float("-inf")
_FUZZY_THRESHOLD = 0.55


def _subject_match_score(faculty: FacultySlot, subject_name: str) -> float:
    """
    Compare faculty.main_subject and backup_subject against the demanded subject.

    Returns:
        100.0 — exact match (case-insensitive)
         80.0 — substring containment in either direction
        1–79  — fuzzy SequenceMatcher ratio × 80 (if ratio ≥ 0.55)
          0.0 — no match
    """
    target = subject_name.lower().strip()
    for candidate in (faculty.main_subject or "", faculty.backup_subject or ""):
        if not candidate:
            continue
        cand = candidate.lower().strip()
        if cand == target:
            return 100.0
        if cand in target or target in cand:
            return 80.0
        ratio = SequenceMatcher(None, cand, target).ratio()
        if ratio >= _FUZZY_THRESHOLD:
            return ratio * 80.0
    return 0.0


def score_faculty_for_demand(faculty: FacultySlot, demand: SubjectDemand) -> float:
    """
    Compute how well a faculty member fits a SubjectDemand.
    Returns -inf if any hard constraint is violated.
    """
    # Hard filter 1: same department
    if faculty.department_id != demand.department_id:
        return _IMPOSSIBLE

    # Hard filter 2: lab demands need lab-capable faculty
    if demand.subject_type.strip().lower() == "lab" and not faculty.can_take_labs:
        return _IMPOSSIBLE

    # Hard filter 3: faculty at max weekly load
    if faculty.assigned_count >= faculty.max_classes_per_week:
        return _IMPOSSIBLE

    # Soft score 1: subject match
    match_score = _subject_match_score(faculty, demand.subject_name)
    if match_score == 0.0:
        return _IMPOSSIBLE  # cannot teach this subject at all

    # Soft score 2: load headroom (prefer faculty with more room to spare)
    headroom = (faculty.max_classes_per_week - faculty.assigned_count) / max(
        faculty.max_classes_per_week, 1
    )
    load_score = headroom * 30.0

    # Soft score 3: lab bonus
    lab_bonus = 20.0 if demand.subject_type.strip().lower() == "lab" else 0.0

    return match_score + load_score + lab_bonus


def assign_faculty(
    demand: SubjectDemand,
    faculty_pool: list[FacultySlot],
) -> FacultySlot | None:
    """
    Greedy: pick the highest-scoring eligible faculty for this demand.

    Pre-books the load on the returned faculty object (assigned_count +=
    demand.weekly_periods). The caller must register assigned_slots separately
    as slot positions are not yet known here.

    Returns None if no eligible faculty found (slot will be marked TBA).
    """
    scored = [
        (f, score_faculty_for_demand(f, demand))
        for f in faculty_pool
    ]
    eligible = [(f, s) for f, s in scored if s > _IMPOSSIBLE]

    if not eligible:
        logger.warning(
            f"Phase3: no eligible faculty for '{demand.subject_name}' "
            f"(section={demand.section_str}, dept_id={demand.department_id})"
        )
        return None

    # Sort DESC by score; tie-break: alphabetical name → fully deterministic
    eligible.sort(key=lambda x: (-x[1], x[0].name))
    chosen, best_score = eligible[0]
    chosen.assigned_count += demand.weekly_periods

    logger.debug(
        f"Phase3: '{demand.subject_name}' → '{chosen.name}' "
        f"(score={best_score:.1f}, load={chosen.assigned_count}/{chosen.max_classes_per_week})"
    )
    return chosen
