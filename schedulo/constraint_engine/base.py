"""
schedulo/constraint_engine/base.py — Abstract base class for all scheduling constraints.
All HC (Hard Constraint) and SC (Soft Constraint) classes inherit from BaseConstraint.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ConstraintType(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"


@dataclass
class SlotCandidate:
    """
    Represents a scheduling candidate being evaluated by the constraint engine.
    Passed to `check()` along with the list of already-committed slots.
    """
    section_id: str
    day: str                  # "Monday" … "Saturday"
    period_idx: int           # 0-based period index (0="9:00–9:55")
    period_label: str         # "9:00–9:55"
    subject_name: str
    subject_type: str         # Theory | Lab | Project
    faculty_id: str
    faculty_name: str
    room_id: str
    room_type: str            # Classroom | Lab | Special
    is_lab_pair: bool = False # True if this is the START of a 2-period lab block
    lab_pair_idx: int = -1    # Period index of the continuation slot (is_lab_pair=True only)
    credits: int = 4
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstraintResult:
    """Result returned by any constraint's check() method."""
    passed: bool
    constraint_id: str        # e.g. "HC-01"
    severity: Severity = Severity.CRITICAL
    message: str = ""
    penalty: float = 0.0      # Penalty deducted from fitness score (soft constraints)
    auto_fixable: bool = False
    conflict_type: str = ""   # CF-01 … CF-09

    def __bool__(self) -> bool:
        return self.passed


class BaseConstraint(ABC):
    """Abstract base for all scheduling constraints."""

    constraint_id: str = "UNKNOWN"
    constraint_type: ConstraintType = ConstraintType.HARD
    severity: Severity = Severity.CRITICAL

    @abstractmethod
    def check(
        self,
        candidate: SlotCandidate,
        existing_slots: list[SlotCandidate],
    ) -> ConstraintResult:
        """
        Validate a candidate slot against already assigned slots.

        Args:
            candidate:      The slot being evaluated.
            existing_slots: All slots already committed in the current timetable.

        Returns:
            ConstraintResult with passed=True if constraint is satisfied.
        """
        ...

    def violation_message(self) -> str:
        """Human-readable description of what this constraint checks."""
        return f"{self.constraint_id}: constraint violated"

    def _ok(self) -> ConstraintResult:
        return ConstraintResult(passed=True, constraint_id=self.constraint_id)

    def _fail(self, message: str, penalty: float = 0.0, auto_fixable: bool = False) -> ConstraintResult:
        return ConstraintResult(
            passed=False,
            constraint_id=self.constraint_id,
            severity=self.severity,
            message=message,
            penalty=penalty,
            auto_fixable=auto_fixable,
            conflict_type=f"CF-{self.constraint_id.replace('HC-', '').replace('SC-', '')}",
        )


class ConstraintEngine:
    """
    Composite engine that runs all registered constraints and aggregates results.
    Separates hard and soft constraints for fitness calculation.
    """

    def __init__(self) -> None:
        self._hard: list[BaseConstraint] = []
        self._soft: list[BaseConstraint] = []

    def register(self, constraint: BaseConstraint) -> None:
        """Register a constraint with the engine."""
        if constraint.constraint_type == ConstraintType.HARD:
            self._hard.append(constraint)
        else:
            self._soft.append(constraint)

    def check_hard(
        self,
        candidate: SlotCandidate,
        existing_slots: list[SlotCandidate],
    ) -> list[ConstraintResult]:
        """Run all hard constraints. Returns list of violations (empty = no violations)."""
        violations: list[ConstraintResult] = []
        for c in self._hard:
            result = c.check(candidate, existing_slots)
            if not result.passed:
                violations.append(result)
        return violations

    def check_soft(
        self,
        candidate: SlotCandidate,
        existing_slots: list[SlotCandidate],
    ) -> list[ConstraintResult]:
        """Run all soft constraints. Returns list of violations."""
        violations: list[ConstraintResult] = []
        for c in self._soft:
            result = c.check(candidate, existing_slots)
            if not result.passed:
                violations.append(result)
        return violations

    def is_feasible(
        self,
        candidate: SlotCandidate,
        existing_slots: list[SlotCandidate],
    ) -> bool:
        """Returns True only when zero hard constraints are violated."""
        return len(self.check_hard(candidate, existing_slots)) == 0

    def soft_penalty(
        self,
        candidate: SlotCandidate,
        existing_slots: list[SlotCandidate],
    ) -> float:
        """Sum of penalties from all violated soft constraints (used in GA fitness)."""
        return sum(r.penalty for r in self.check_soft(candidate, existing_slots))
