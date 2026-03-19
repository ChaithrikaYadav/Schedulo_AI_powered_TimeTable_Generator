"""
chronoai/ml_pipeline/feature_engineering.py
Feature Engineering Pipeline for timetable quality prediction.

Extracts 20 numeric features from a timetable representation dict and
applies a scikit-learn StandardScaler + imputation pipeline.

Input format (timetable_dict):
    {
        "slots": [{"day": 0-5, "period": 1-9, "slot_type": "THEORY|LAB|LUNCH|FREE",
                   "faculty_id": int|None, "room_id": int|None, ...}],
        "conflict_count": int,
        "generation_time_ms": int,
        "ga_fitness_score": float|None,
        "section_count": int,
    }
"""

from __future__ import annotations

import numpy as np
from typing import Any

try:
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

# ── Feature names (canonical order — must not change after training) ────────
FEATURE_NAMES = [
    "slot_utilization_rate",       # F01: fraction of slots filled (non-FREE, non-LUNCH)
    "theory_ratio",                # F02: theory slots / total filled slots
    "lab_ratio",                   # F03: lab slots / total filled slots
    "conflict_count",              # F04: raw conflict count (normalised later)
    "conflict_rate",               # F05: conflicts / total slots
    "faculty_load_variance",       # F06: variance in per-faculty slot counts
    "section_count",               # F07: number of sections
    "saturday_utilization",        # F08: fraction of Saturday slots that are filled
    "avg_slots_per_day",           # F09: average filled slots per day
    "room_type_mismatch_rate",     # F10: fraction where room type doesn't match slot type
    "lunch_consistency_score",     # F11: 1 if same lunch slot for all days, else fraction
    "unique_faculty_count",        # F12: unique faculty assigned
    "avg_lab_pair_integrity",      # F13: fraction of lab slots paired with their continuation
    "free_slot_rate",              # F14: fraction of non-lunch slots that are FREE
    "generation_time_norm",        # F15: generation_time_ms / 60000 (normalized to minutes)
    "ga_fitness_score",            # F16: raw GA fitness score (0 if N/A)
    "consecutive_free_rate",       # F17: fraction of days with ≥3 consecutive free slots (idle risk)
    "faculty_utilization",         # F18: unique_faculty / section_count (coverage density)
    "slot_type_entropy",           # F19: Shannon entropy of slot type distribution
    "period_coverage_breadth",     # F20: fraction of 9 periods used across all days
]


def _safe_div(a: float, b: float, fallback: float = 0.0) -> float:
    return a / b if b > 0 else fallback


class FeatureEngineer:
    """
    Extracts and normalizes features from a timetable dict.

    Usage:
        fe = FeatureEngineer()
        fe.fit(list_of_timetable_dicts)          # optional: fit scaler
        X = fe.transform(list_of_timetable_dicts) # numpy array shape (N, 20)
        # or single dict:
        x = fe.transform_one(timetable_dict)     # shape (20,)
    """

    def __init__(self) -> None:
        self._fitted = False
        if _SKLEARN_AVAILABLE:
            self._pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ])
        else:
            self._pipeline = None

    # ── Raw feature extraction ─────────────────────────────────────────────────
    def extract_raw(self, timetable_dict: dict[str, Any]) -> list[float]:
        """Return a list of 20 raw (unscaled) feature values."""
        slots = timetable_dict.get("slots", [])
        conflict_count = float(timetable_dict.get("conflict_count", 0))
        gen_time = float(timetable_dict.get("generation_time_ms", 0))
        ga_fitness = float(timetable_dict.get("ga_fitness_score") or 0.0)
        section_count = float(timetable_dict.get("section_count", 1))

        total = len(slots)
        if total == 0:
            return [0.0] * len(FEATURE_NAMES)

        # Count slot types
        type_counts: dict[str, int] = {}
        for s in slots:
            t = str(s.get("slot_type", "FREE")).upper()
            type_counts[t] = type_counts.get(t, 0) + 1

        lunch = type_counts.get("LUNCH", 0)
        theory = type_counts.get("THEORY", 0)
        lab = type_counts.get("LAB", 0)
        free = type_counts.get("FREE", 0)
        non_lunch = total - lunch
        filled = non_lunch - free

        # F01
        slot_utilization_rate = _safe_div(filled, non_lunch)
        # F02
        theory_ratio = _safe_div(theory, filled if filled else 1)
        # F03
        lab_ratio = _safe_div(lab, filled if filled else 1)
        # F04
        conflict_count_f = conflict_count
        # F05
        conflict_rate = _safe_div(conflict_count, total)

        # F06: faculty load variance
        faculty_slots: dict[int, int] = {}
        for s in slots:
            fid = s.get("faculty_id")
            if fid is not None:
                faculty_slots[fid] = faculty_slots.get(fid, 0) + 1
        fac_counts = list(faculty_slots.values())
        faculty_load_variance = float(np.var(fac_counts)) if fac_counts else 0.0

        # F08: Saturday utilization (day_of_week == 5)
        sat_slots = [s for s in slots if s.get("day", -1) == 5]
        sat_filled = sum(1 for s in sat_slots
                         if str(s.get("slot_type", "FREE")).upper()
                         not in {"FREE", "LUNCH"})
        saturday_utilization = _safe_div(sat_filled, len(sat_slots)) if sat_slots else 0.0

        # F09: avg filled slots / day
        day_filled: dict[int, int] = {}
        for s in slots:
            d = s.get("day", 0)
            t = str(s.get("slot_type", "FREE")).upper()
            if t not in {"FREE", "LUNCH"}:
                day_filled[d] = day_filled.get(d, 0) + 1
        avg_slots_per_day = _safe_div(sum(day_filled.values()), max(len(day_filled), 1))

        # F10: room type mismatch (lab slot without lab room — heuristic, slot_type=LAB, room info in notes)
        mismatch = sum(
            1 for s in slots
            if str(s.get("slot_type", "")).upper() == "LAB"
            and "lab" not in str(s.get("notes", "")).lower()
            and s.get("room_id") is None
        )
        room_type_mismatch_rate = _safe_div(mismatch, max(lab, 1))

        # F11: lunch consistency (same period across days)
        lunch_periods: set[int] = set()
        for s in slots:
            if str(s.get("slot_type", "")).upper() == "LUNCH":
                lunch_periods.add(s.get("period", -1))
        lunch_consistency_score = 1.0 if len(lunch_periods) <= 1 else _safe_div(1, len(lunch_periods))

        # F12: unique faculty
        unique_faculty_count = float(len(faculty_slots))

        # F13: lab pair integrity — lab continuation slots present
        lab_slots = [s for s in slots if str(s.get("slot_type", "")).upper() == "LAB"]
        cont_slots = [s for s in slots
                      if str(s.get("slot_type", "")).upper() == "LAB"
                      and s.get("is_lab_continuation", False)]
        avg_lab_pair_integrity = _safe_div(len(cont_slots), max(len(lab_slots), 1))

        # F14: free slot rate
        free_slot_rate = _safe_div(free, non_lunch)

        # F15
        generation_time_norm = gen_time / 60000.0

        # F16
        ga_fitness_score_f = ga_fitness

        # F17: consecutive free rate (days with ≥3 consecutive free periods)
        days_list: dict[int, list[str]] = {}
        for s in slots:
            d = s.get("day", 0)
            days_list.setdefault(d, []).append(str(s.get("slot_type", "FREE")).upper())
        consec_days = 0
        for d, types in days_list.items():
            max_consec = cur = 0
            for t in types:
                cur = cur + 1 if t == "FREE" else 0
                max_consec = max(max_consec, cur)
            if max_consec >= 3:
                consec_days += 1
        consecutive_free_rate = _safe_div(consec_days, max(len(days_list), 1))

        # F18
        faculty_utilization = _safe_div(unique_faculty_count, section_count)

        # F19: slot type entropy
        type_fracs = [
            _safe_div(type_counts.get(k, 0), total)
            for k in ["THEORY", "LAB", "PROJECT", "FREE", "LUNCH"]
        ]
        entropy = -sum(p * np.log2(p) for p in type_fracs if p > 0)
        slot_type_entropy = float(entropy)

        # F20: fraction of 9 periods that appear in at least one filled slot
        used_periods: set[int] = set()
        for s in slots:
            if str(s.get("slot_type", "FREE")).upper() not in {"FREE", "LUNCH"}:
                used_periods.add(s.get("period", 0))
        period_coverage_breadth = _safe_div(len(used_periods), 9)

        return [
            slot_utilization_rate,    # F01
            theory_ratio,             # F02
            lab_ratio,                # F03
            conflict_count_f,         # F04
            conflict_rate,            # F05
            faculty_load_variance,    # F06
            section_count,            # F07
            saturday_utilization,     # F08
            avg_slots_per_day,        # F09
            room_type_mismatch_rate,  # F10
            lunch_consistency_score,  # F11
            unique_faculty_count,     # F12
            avg_lab_pair_integrity,   # F13
            free_slot_rate,           # F14
            generation_time_norm,     # F15
            ga_fitness_score_f,       # F16
            consecutive_free_rate,    # F17
            faculty_utilization,      # F18
            slot_type_entropy,        # F19
            period_coverage_breadth,  # F20
        ]

    def transform_one(self, timetable_dict: dict[str, Any]) -> np.ndarray:
        """Extract and optionally scale features for a single timetable."""
        raw = self.extract_raw(timetable_dict)
        X = np.array([raw], dtype=float)
        if self._fitted and self._pipeline is not None:
            X = self._pipeline.transform(X)
        return X[0]

    def transform(self, timetable_dicts: list[dict[str, Any]]) -> np.ndarray:
        """Extract and optionally scale features for a list of timetables."""
        raw = [self.extract_raw(d) for d in timetable_dicts]
        X = np.array(raw, dtype=float)
        if self._fitted and self._pipeline is not None:
            X = self._pipeline.transform(X)
        return X

    def fit(self, timetable_dicts: list[dict[str, Any]]) -> "FeatureEngineer":
        """Fit the scaler on a list of timetable dicts."""
        if not _SKLEARN_AVAILABLE or self._pipeline is None:
            return self
        raw = [self.extract_raw(d) for d in timetable_dicts]
        X = np.array(raw, dtype=float)
        self._pipeline.fit(X)
        self._fitted = True
        return self

    def fit_transform(self, timetable_dicts: list[dict[str, Any]]) -> np.ndarray:
        """Fit scaler and return scaled features."""
        if not _SKLEARN_AVAILABLE or self._pipeline is None:
            raw = [self.extract_raw(d) for d in timetable_dicts]
            return np.array(raw, dtype=float)
        raw = [self.extract_raw(d) for d in timetable_dicts]
        X = np.array(raw, dtype=float)
        result = self._pipeline.fit_transform(X)
        self._fitted = True
        return result
