"""
schedulo/scheduler_core/phase1_demand.py
Phase 1 — Subject-Section Demand Builder

Replaces random subject sampling with deterministic, semester-appropriate selection.
No randomization. All choices are driven by subject attributes.
"""

from __future__ import annotations

import logging
from typing import Any

from schedulo.scheduler_core.models import SubjectDemand

logger = logging.getLogger(__name__)

# How many subjects of each type to schedule per semester
# (theory_count, lab_count, project_count)
SUBJECT_LOAD_PER_SEMESTER: dict[str, tuple[int, int, int]] = {
    "Sem 1": (5, 1, 0),
    "Sem 2": (5, 1, 0),
    "Sem 3": (5, 2, 1),
    "Sem 4": (5, 2, 1),
    "Sem 5": (4, 2, 1),
    "Sem 6": (4, 2, 1),
    "Sem 7": (3, 1, 2),
    "Sem 8": (3, 1, 2),
}

# Cross-department subject exclusion list — must not appear in CSE sections
# (same list used by prototype_scheduler.py Bug 1 fix)
DEPT_SUBJECT_EXCLUSIONS: dict[str, list[str]] = {
    "School of Computer Science & Engineering": [
        # Hospitality
        "Bakery & Confectionery Lab", "F&B Service Lab", "Bar Operations Lab",
        "Bakery Advanced Lab", "Food Production Lab", "Basics of Food Production",
        "Front Office Management", "Housekeeping Operations", "Resort Management",
        "Tourism Geography", "Gastronomy", "Industrial Exposure Training",
        "Wine Studies", "Nutrition & Hygiene", "Culinary Art", "Hotel Accounting",
        "Food & Beverage Service", "French Language for Hospitality",
        "Food Cost Control", "Hospitality Law", "Hospitality Ethics",
        # Management
        "Business Economics", "Business Law", "Financial Management",
        "Financial Accounting", "Corporate Finance", "Taxation Laws",
        "Marketing Management", "Human Resource Management",
        "Banking & Insurance", "Entrepreneurship Development",
        "Organizational Behavior", "Consumer Behavior", "Retail Management",
        "CRM Systems", "Supply Chain Management", "E-Commerce",
        "Advertising & Sales", "Internship Project",
    ],
}


def build_demands(section: Any, subjects: list[Any]) -> list[SubjectDemand]:
    """
    Build the list of SubjectDemand for one section.

    Args:
        section:  SQLAlchemy Section ORM object
        subjects: list of SQLAlchemy Subject ORM objects for this department

    Returns:
        Ordered list of SubjectDemand objects (all types interleaved in priority order).

    Selection is fully deterministic:
      - Theory:  sorted by (-credits, name)   — highest-value subjects first
      - Lab:     sorted by name ASC            — alphabetical, stable
      - Project: sorted by credits ASC         — lightest projects first
    """
    semester = getattr(section, "semester", None) or "Sem 1"
    theory_target, lab_target, project_target = SUBJECT_LOAD_PER_SEMESTER.get(
        semester, (5, 1, 0)
    )

    dept_id = getattr(section, "department_id", None)

    # Get exclusion list for this department (looked up by dept name if available)
    # We look it up via the subjects list for simplicity
    exclusions: set[str] = set()
    # Try to find dept name from any subject
    for s in subjects:
        dept_name = getattr(getattr(s, "department", None), "name", None)
        if dept_name and dept_name in DEPT_SUBJECT_EXCLUSIONS:
            exclusions = set(DEPT_SUBJECT_EXCLUSIONS[dept_name])
            break

    # Filter subjects: must match section's department and not be excluded
    eligible = [
        s for s in subjects
        if s.department_id == dept_id
        and s.name not in exclusions
    ]

    # Separate by type
    theory_subs = sorted(
        [s for s in eligible if (s.subject_type or "").strip().lower() == "theory"],
        key=lambda s: (-(float(s.credits or 0)), (s.name or "").lower()),
    )
    lab_subs = sorted(
        [s for s in eligible if (s.subject_type or "").strip().lower() == "lab"],
        key=lambda s: (s.name or "").lower(),
    )
    project_subs = sorted(
        [s for s in eligible if (s.subject_type or "").strip().lower() == "project"],
        key=lambda s: float(s.credits or 0),
    )

    chosen = (
        theory_subs[:theory_target]
        + lab_subs[:lab_target]
        + project_subs[:project_target]
    )

    if not chosen:
        logger.warning(
            f"Phase1: no eligible subjects for section={section.section_id} "
            f"(dept_id={dept_id}, semester={semester})"
        )
        return []

    logger.debug(
        f"Phase1: section={section.section_id} semester={semester} "
        f"→ {len(chosen)} demands "
        f"({len(theory_subs[:theory_target])}T "
        f"{len(lab_subs[:lab_target])}L "
        f"{len(project_subs[:project_target])}P)"
    )

    return [
        SubjectDemand(
            subject_id=s.id,
            subject_name=s.name,
            subject_type=(s.subject_type or "Theory"),
            credits=float(s.credits or 0),
            weekly_periods=int(s.weekly_periods or 1),
            requires_consecutive=(s.subject_type or "").strip().lower() == "lab",
            burst_length=2 if (s.subject_type or "").strip().lower() == "lab" else 1,
            section_id=section.id,
            section_str=section.section_id,
            department_id=section.department_id,
            semester=semester,
        )
        for s in chosen
    ]
