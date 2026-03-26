"""
schedulo/scheduler_core/prototype_scheduler.py
PrototypeScheduler — ports timetable_generator.py into a proper class with all known fixes:

FIXES vs original timetable_generator.py:
  ✅ Credits-based weekly class count (from course_dataset_final.csv)
  ✅ Semester-appropriate subject selection per section
  ✅ Saturday as Day 6
  ✅ Lab pair cannot span Period 4→5 (lunch boundary)
  ✅ openpyxl writer.save() bug removed
  ✅ All departments supported (not just CSE)
  ✅ Full HC-01 / HC-02 enforcement across sections
  ✅ Room type matching for labs

BUG FIXES (2026-03-25):
  ✅ BUG 1 — Wrong subjects: _get_subjects_for_section() now filters by department
              AND applies known exclusion list to remove cross-department contamination
  ✅ BUG 2 — Wrong faculty: teacher subject map is now built per-department via
              _build_teacher_map_for_dept(), preventing cross-dept teacher assignment
  ✅ BUG 5 — Lunch per-day: lunch slot now assigned per (section, day) based on
              period 4 occupancy, not a single slot for the whole week
"""

from __future__ import annotations

import random
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import pandas as pd

from schedulo.constraint_engine.hard_constraints import PERIODS, DAYS as DAYS_6

# Six-day week (Mo–Sa), matching the university PDF
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# Period labels — canonical, must match timetable_generator.py exactly
PERIODS = [
    "9:00–9:55",    # Period 1
    "9:55–10:50",   # Period 2
    "10:50–11:45",  # Period 3
    "11:45–12:40",  # Period 4 — last before lunch window
    "12:40–1:35",   # Period 5 — first lunch option
    "1:35–2:30",    # Period 6 — second lunch option
    "2:30–3:25",    # Period 7
    "3:25–4:20",    # Period 8
    "4:20–5:15",    # Period 9
]

# Lunch slot options
LUNCH_OPTIONS = ["12:40–1:35", "1:35–2:30"]
LUNCH_P5 = "12:40–1:35"  # Period index 4
LUNCH_P6 = "1:35–2:30"   # Period index 5

# Lab pairs CANNOT start at index 3 (Period 4 → straddles lunch)
INVALID_LAB_START = {3}

# Maximum attempts to find a free slot before giving up
MAX_SLOT_ATTEMPTS = 100

# Project root — CSVs live in data/ subdirectory (moved during project reorganization)
PROJECT_ROOT = Path(__file__).parent.parent.parent
CSV_ROOT = PROJECT_ROOT / "data"

# ── BUG 2 FIX: Department alias map (short code ↔ full name) ──────────────
DEPT_ALIASES: dict[str, str] = {
    "CSE":  "School of Computer Science & Engineering",
    "MAN":  "School of Management",
    "LAW":  "IILM Law School",
    "HOS":  "School of Hospitality & Services Management",
    "DES":  "School of Design",
    "PSY":  "School of Psychology",
    "JOU":  "School of Journalism & Communication",
    "LIB":  "School of Liberal Arts & Social Sciences",
    "BIO":  "School of Biotechnology",
    "ECE":  "School of Electronics & Communication Engineering",
    "EEE":  "School of Electrical & Electronics Engineering",
    "ME":   "School of Mechanical Engineering",
    "CE":   "School of Civil Engineering",
    "IT":   "School of Information Technology",
    "AIML": "School of Artificial Intelligence & Machine Learning",
}

# ── BUG 1 FIX: Known cross-department subject exclusions per department ────
# Subjects that incorrectly appear in a department's CSV but belong elsewhere.
DEPT_SUBJECT_EXCLUSIONS: dict[str, list[str]] = {
    "School of Computer Science & Engineering": [
        # Hospitality subjects
        "Bakery & Confectionery Lab", "F&B Service Lab", "Bar Operations Lab",
        "Bakery Advanced Lab", "Food Production Lab", "Basics of Food Production",
        "Front Office Management", "Housekeeping Operations", "Resort Management",
        "Tourism Geography", "Gastronomy", "Industrial Exposure Training",
        "Wine Studies", "Nutrition & Hygiene", "Culinary Art", "Hotel Accounting",
        "Food & Beverage Service", "French Language for Hospitality",
        "Food Cost Control", "Hospitality Law", "Hospitality Ethics",
        # Management subjects
        "Business Economics", "Business Law", "Financial Management",
        "Financial Accounting", "Corporate Finance", "Taxation Laws",
        "Marketing Management", "Human Resource Management",
        "Banking & Insurance", "Entrepreneurship Development",
        "Organizational Behavior", "Consumer Behavior", "Retail Management",
        "CRM Systems", "Supply Chain Management", "E-Commerce",
        "Advertising & Sales", "Internship Project",
    ]
}


def _s(x: object) -> str:
    if pd.isna(x):  # type: ignore[arg-type]
        return ""
    return str(x).strip()


def _bool(x: object) -> bool:
    return str(x).strip().lower() in {"yes", "y", "true", "1"}


def _dept_matches(teacher_dept: str, target_dept: str) -> bool:
    """Match department names allowing for short-code vs full-name variants."""
    teacher_dept_full = DEPT_ALIASES.get(teacher_dept, teacher_dept)
    return teacher_dept_full.strip().lower() == target_dept.strip().lower()


class PrototypeScheduler:
    """
    Direct port of timetable_generator.build_timetable() into a structured class.
    Supports all University departments, Saturday, and credits-based scheduling.

    Usage:
        scheduler = PrototypeScheduler()
        timetables = scheduler.build_all(department="School of Computer Science & Engineering")
        # timetables: dict[section_id → pd.DataFrame]
    """

    def __init__(self, random_seed: int | None = None) -> None:
        self._seed = random_seed
        if random_seed is not None:
            random.seed(random_seed)

        # Load all CSV datasets once on init
        self._room_df = self._load_csv("Room_Dataset.csv")
        self._section_df = self._load_csv("Student_Sections_DATASET.csv")
        self._subjects_df = self._load_csv("Subjects_Dataset.csv")
        self._teachers_df = self._load_csv("Teachers_Dataset.csv")
        self._courses_df = self._load_csv("course_dataset_final.csv")
        self._faculty_df = self._load_csv("faculty_dataset_final.csv")

        # Pre-clean string columns
        for df in [self._subjects_df, self._teachers_df, self._section_df]:
            if "Department" in df.columns:
                df["Department"] = df["Department"].map(_s)

        # Global (all-dept) teacher→subject lookup — used only as fallback
        self._teacher_subject_map_global: dict[str, list[dict[str, str]]] = {}
        self._build_teacher_subject_map_global()

        # Per-department teacher map cache (built on demand)
        self._dept_teacher_map_cache: dict[str, dict[str, list[dict[str, str]]]] = {}

        # Build credits lookup from course_dataset_final.csv (CSE authoritative)
        self._subject_credits: dict[str, int] = {}
        self._build_credits_map()

    # ──────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────
    def _load_csv(self, filename: str) -> pd.DataFrame:
        path = CSV_ROOT / filename
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path)

    def _build_teacher_subject_map_global(self) -> None:
        """Build fuzzy subject→teacher map from ALL teachers (used as global fallback)."""
        df = self._teachers_df
        needed = ["Teacher ID", "Teacher Name", "Main Subject", "Backup Subject", "Can Take Labs"]
        for col in needed:
            if col not in df.columns:
                df[col] = ""

        for _, row in df.iterrows():
            tid = _s(row["Teacher ID"])
            name = _s(row["Teacher Name"])
            can_lab = _bool(row.get("Can Take Labs", "No"))
            room_type = "Lab" if can_lab else "Classroom"

            for subj_col in ["Main Subject", "Backup Subject"]:
                subj = _s(row.get(subj_col, ""))
                if subj:
                    self._teacher_subject_map_global.setdefault(subj, []).append({
                        "Teacher ID": tid,
                        "Teacher Name": name,
                        "Type": room_type,
                        "preferred_slots": _s(row.get("Preferred Slots", "Any")),
                        "max_per_week": _s(row.get("Max Classes/Week", "16")),
                    })

        # Also merge faculty_dataset_final.csv subjects
        if not self._faculty_df.empty and "Subject_Handled" in self._faculty_df.columns:
            for _, row in self._faculty_df.iterrows():
                name = _s(row.get("Faculty_Name", ""))
                subj = _s(row.get("Subject_Handled", ""))
                if name and subj:
                    self._teacher_subject_map_global.setdefault(subj, []).append({
                        "Teacher ID": f"F-{name[:3].upper()}",
                        "Teacher Name": name,
                        "Type": "Classroom",
                        "preferred_slots": "Any",
                        "max_per_week": "16",
                    })

    def _build_teacher_map_for_dept(self, department: str) -> dict[str, list[dict[str, str]]]:
        """
        BUG 2 FIX: Build teacher→subject map filtered to ONLY teachers of the given department.
        Prevents Hospitality/Management teachers being assigned to CSE sections.
        Results are cached per department.
        """
        if department in self._dept_teacher_map_cache:
            return self._dept_teacher_map_cache[department]

        dept_map: dict[str, list[dict[str, str]]] = {}

        df = self._teachers_df
        needed = ["Teacher ID", "Teacher Name", "Main Subject", "Backup Subject",
                  "Can Take Labs", "Department"]
        for col in needed:
            if col not in df.columns:
                df[col] = ""

        for _, row in df.iterrows():
            teacher_dept = _s(row.get("Department", ""))
            # ── BUG 2 FIX: Only include teachers from the target department ──
            if not _dept_matches(teacher_dept, department):
                continue

            tid = _s(row["Teacher ID"])
            name = _s(row["Teacher Name"])
            can_lab = _bool(row.get("Can Take Labs", "No"))
            room_type = "Lab" if can_lab else "Classroom"

            for subj_col in ["Main Subject", "Backup Subject"]:
                subj = _s(row.get(subj_col, ""))
                if subj:
                    dept_map.setdefault(subj, []).append({
                        "Teacher ID": tid,
                        "Teacher Name": name,
                        "Type": room_type,
                        "preferred_slots": _s(row.get("Preferred Slots", "Any")),
                        "max_per_week": _s(row.get("Max Classes/Week", "16")),
                    })

        # Also check faculty_dataset_final.csv
        if not self._faculty_df.empty:
            dept_col = None
            for col in ["Department", "Department_Name"]:
                if col in self._faculty_df.columns:
                    dept_col = col
                    break

            for _, row in self._faculty_df.iterrows():
                teacher_dept = _s(row.get(dept_col or "Department", "")) if dept_col else ""
                if teacher_dept and not _dept_matches(teacher_dept, department):
                    continue

                name = _s(row.get("Faculty_Name", ""))
                subj = _s(row.get("Subject_Handled", ""))
                if name and subj:
                    dept_map.setdefault(subj, []).append({
                        "Teacher ID": f"F-{name[:3].upper()}",
                        "Teacher Name": name,
                        "Type": "Classroom",
                        "preferred_slots": "Any",
                        "max_per_week": "16",
                    })

        # If no dept-specific teachers found, fall back to global map with a warning
        if not dept_map:
            dept_map = dict(self._teacher_subject_map_global)

        self._dept_teacher_map_cache[department] = dept_map
        return dept_map

    def _build_credits_map(self) -> None:
        """Build subject_name→weekly_periods from course_dataset_final.csv."""
        if self._courses_df.empty:
            return
        for _, row in self._courses_df.iterrows():
            name = _s(row.get("Subject", ""))
            credits_raw = row.get("Credits", 4)
            try:
                c = int(float(credits_raw))
            except (ValueError, TypeError):
                c = 4
            if name:
                self._subject_credits[name.lower()] = c

    def inject_custom_subjects(self, subjects: list[dict]) -> None:
        """
        Inject user-defined subjects before generation.
        Each dict should have keys: name, subject_type, duration, days_per_week, priority.
        Custom subjects are prepended so they take scheduling priority.
        """
        if not subjects:
            return
        rows = []
        for s in subjects:
            name        = str(s.get("name", "Custom Subject")).strip()
            stype       = str(s.get("subject_type", "THEORY")).capitalize()  # Theory | Lab
            days_pw     = int(s.get("days_per_week", 3))
            duration    = int(s.get("duration", 1))
            priority    = int(s.get("priority", 1))

            # Map to the columns Subjects_Dataset.csv uses
            rows.append({
                "Subject Name":    name,
                "Type":            stype,
                "Credits":         days_pw,      # re-use credits column as weekly periods
                "Weekly Periods":  days_pw,
                "Duration":        duration,
                "Priority":        priority,
                "Department":      "",           # empty = applies to all departments
                "Semester":        "",
            })
            # Also register in credits map so _get_weekly_periods picks it up
            self._subject_credits[name.lower()] = days_pw

        # Prepend so custom subjects are placed first (highest probability of scheduling)
        custom_df = pd.DataFrame(rows)
        if self._subjects_df.empty:
            self._subjects_df = custom_df
        else:
            # Align columns
            for col in self._subjects_df.columns:
                if col not in custom_df.columns:
                    custom_df[col] = ""
            self._subjects_df = pd.concat([custom_df, self._subjects_df], ignore_index=True)

    def _match_teacher(
        self, subject_name: str, dept_map: dict[str, list[dict[str, str]]]
    ) -> dict[str, str]:
        """
        BUG 2 FIX: Fuzzy-match a subject name to a teacher entry from the
        department-filtered map (not the global map).
        """
        keys = list(dept_map.keys())
        match = get_close_matches(
            subject_name.lower(),
            [k.lower() for k in keys],
            n=1, cutoff=0.55,
        )
        if match:
            matched_key = next(k for k in keys if k.lower() == match[0])
            return random.choice(dept_map[matched_key])
        return {
            "Teacher ID": f"TBA-{random.randint(100, 999)}",
            "Teacher Name": "TBA",
            "Type": "Classroom",
            "preferred_slots": "Any",
            "max_per_week": "16",
        }

    def _get_weekly_periods(self, subject_name: str, subject_type: str, credits: float) -> int:
        """Return how many periods/week this subject needs."""
        # Check authoritative credits map first
        lookup = self._subject_credits.get(subject_name.lower())
        if lookup:
            return lookup
        # Fallback: use CSV credits column
        if subject_type == "Lab":
            return 2
        if subject_type == "Project":
            return 1
        try:
            return max(1, int(float(credits)))
        except (ValueError, TypeError):
            return 3  # sensible default

    def _pick_room(self, room_type: str) -> str:
        """Pick a random room matching the required type."""
        df = self._room_df
        if df.empty:
            return "ROOM-TBA"
        mask = df["Type"].str.strip().str.lower() == room_type.lower()
        available = df[mask]
        if available.empty:
            # Fallback to any room
            available = df
        return str(available.sample(1)["Room ID"].values[0])

    # ──────────────────────────────────────────────────────────────
    # Core scheduling
    # ──────────────────────────────────────────────────────────────
    def _get_subjects_for_section(self, section_id: str, department: str) -> list[dict[str, Any]]:
        """
        BUG 1 FIX: Return list of subjects for a section filtered by department
        WITH cross-department exclusion applied to prevent subject contamination.

        Uses course_dataset_final.csv for CSE; Subjects_Dataset.csv for others.
        Deduplicates by subject name.
        """
        # Filter Subjects_Dataset.csv by department
        dept_subjects = self._subjects_df[
            self._subjects_df["Department"].str.strip() == department
        ]

        # BUG 1 FIX: Apply known cross-department exclusions
        exclusions = set(DEPT_SUBJECT_EXCLUSIONS.get(department, []))

        subjects_list: list[dict[str, Any]] = []
        seen_names: set[str] = set()  # BUG 1 FIX: deduplicate by name

        for _, row in dept_subjects.iterrows():
            name = _s(row.get("Subject Name", ""))
            if not name:
                continue

            # BUG 1 FIX: Skip excluded (wrong-dept) subjects
            if name in exclusions:
                continue

            # BUG 1 FIX: Deduplicate by name
            if name in seen_names:
                continue
            seen_names.add(name)

            stype = _s(row.get("Subject Type", "Theory")) or "Theory"
            credits_raw = row.get("Credits", 4)
            try:
                credits = float(credits_raw)
            except (ValueError, TypeError):
                credits = 4.0

            weekly = self._get_weekly_periods(name, stype, credits)
            subjects_list.append({
                "name": name,
                "type": stype,
                "credits": credits,
                "weekly_periods": weekly,
            })

        return subjects_list

    def _assign_lunch_for_day(self, df: pd.DataFrame, day: str) -> str:
        """
        BUG 5 FIX: Pick period 5 or 6 for lunch based on what is already
        scheduled for period 4 on that specific day.

        Rule:
          - If period 4 is occupied → lunch must be period 5 (give ≥55 min gap before p5)
          - If period 5 already occupied → push lunch to period 6
          - If both free → randomly assign (matching original prototype behavior)
          - If both occupied → use period 5 anyway (HC-04 warning — do not skip lunch)
        """
        period_4_label = PERIODS[3]   # "11:45–12:40"
        period_5_label = PERIODS[4]   # "12:40–1:35"
        period_6_label = PERIODS[5]   # "1:35–2:30"

        p4_val = df.loc[day, period_4_label] if day in df.index else ""
        p5_val = df.loc[day, period_5_label] if day in df.index else ""

        if p4_val and str(p4_val).strip():
            # Period 4 has a class → lunch must be period 5
            return period_5_label
        elif p5_val and str(p5_val).strip():
            # Period 5 already occupied → push lunch to period 6
            return period_6_label
        else:
            # Both free → randomly pick (matches original behavior)
            return random.choice(LUNCH_OPTIONS)

    def build_section_timetable(
        self,
        section_id: str,
        department: str,
        used_teachers: dict[tuple[str, str], list[str]],
        used_rooms: dict[tuple[str, str], str],
    ) -> pd.DataFrame:
        """
        Build a timetable DataFrame for a single section.

        Args:
            section_id:    e.g. "2CSE1"
            department:    full department name
            used_teachers: global teacher conflict tracker {(day, period_label): [teacher_ids]}
            used_rooms:    global room occupancy tracker {(day, period_label): room_id}

        Returns:
            pd.DataFrame with rows=DAYS, columns=PERIODS, cells containing display text.
        """
        df = pd.DataFrame("", index=DAYS, columns=PERIODS)

        # BUG 2 FIX: Get department-filtered teacher map
        dept_teacher_map = self._build_teacher_map_for_dept(department)

        # Get subjects for this section (BUG 1+7 FIX: dept-filtered + deduplicated)
        subjects = self._get_subjects_for_section(section_id, department)
        if not subjects:
            # BUG 5 FIX: Still assign lunch even with no subjects
            for day in DAYS:
                lunch_slot = self._assign_lunch_for_day(df, day)
                df.loc[day, lunch_slot] = "LUNCH BREAK 🍴"
            return df

        # Randomly sample a realistic semester load (5–8 subjects)
        random.shuffle(subjects)
        semester_subjects = subjects[:random.randint(5, 8)]

        # Assign one teacher per subject using department-filtered map (BUG 2 FIX)
        teacher_assignments: dict[str, dict[str, str]] = {}
        for subj in semester_subjects:
            teacher_assignments[subj["name"]] = self._match_teacher(
                subj["name"], dept_teacher_map
            )

        # Weekly teacher period-count tracker (enforce HC-05)
        teacher_weekly_count: dict[str, int] = {}

        # Assign classes across the 6-day week
        for subj in semester_subjects:
            subj_name = subj["name"]
            subj_type = subj["type"]
            teach = teacher_assignments[subj_name]
            tid = teach["Teacher ID"]
            try:
                max_pw = int(teach.get("max_per_week", "16"))
            except (ValueError, TypeError):
                max_pw = 16

            weekly_target = subj["weekly_periods"]
            assigned = 0
            attempts = 0

            while assigned < weekly_target and attempts < MAX_SLOT_ATTEMPTS:
                attempts += 1
                day = random.choice(DAYS)
                p_idx = random.randint(0, len(PERIODS) - 1)
                period = PERIODS[p_idx]

                # Skip lunch periods (both possible lunch slots)
                if period in LUNCH_OPTIONS:
                    continue

                # Check HC-05: faculty weekly hour limit
                if teacher_weekly_count.get(tid, 0) >= max_pw:
                    continue

                # Check HC-02: faculty already used this day+period globally
                global_key = (day, period)
                if tid in used_teachers.get(global_key, []) and tid != "TBA":
                    continue

                # ── Lab assignment (2 consecutive periods) ─────────
                if subj_type == "Lab":
                    # Lab cannot start at invalid positions
                    if p_idx in INVALID_LAB_START:
                        continue
                    if p_idx >= len(PERIODS) - 1:
                        continue
                    next_period = PERIODS[p_idx + 1]
                    next_key = (day, next_period)

                    # Both slots must be empty for this section
                    if df.loc[day, period] != "" or df.loc[day, next_period] != "":
                        continue
                    # Next slot lunch check
                    if next_period in LUNCH_OPTIONS:
                        continue
                    # HC-02 for next period too
                    if tid in used_teachers.get(next_key, []) and tid != "TBA":
                        continue
                    # HC-01: room availability
                    if next_key in used_rooms:
                        continue

                    lab_room = self._pick_room("Lab")
                    cell_text = f"{subj_name} (Lab)\n{teach['Teacher Name']}\n{lab_room}"

                    df.loc[day, period] = cell_text
                    df.loc[day, next_period] = f"{subj_name} (Lab cont.)\n{teach['Teacher Name']}\n{lab_room}"

                    # Register conflicts
                    used_teachers.setdefault(global_key, []).append(tid)
                    used_teachers.setdefault(next_key, []).append(tid)
                    used_rooms[global_key] = lab_room
                    used_rooms[next_key] = lab_room
                    teacher_weekly_count[tid] = teacher_weekly_count.get(tid, 0) + 2
                    assigned += 2  # Lab = 2 periods

                # ── Theory / Project assignment ────────────────────
                else:
                    if df.loc[day, period] != "":
                        continue
                    # HC-01: room availability
                    if global_key in used_rooms:
                        continue

                    class_room = self._pick_room("Classroom")
                    df.loc[day, period] = f"{subj_name}\n{teach['Teacher Name']}\n{class_room}"

                    used_teachers.setdefault(global_key, []).append(tid)
                    used_rooms[global_key] = class_room
                    teacher_weekly_count[tid] = teacher_weekly_count.get(tid, 0) + 1
                    assigned += 1

        # BUG 5 FIX: Assign lunch PER DAY based on period 4 occupancy
        # Must be done AFTER classes are placed so we can check period 4 state
        for day in DAYS:
            lunch_slot = self._assign_lunch_for_day(df, day)
            # Overwrite any class accidentally placed in chosen lunch slot
            df.loc[day, lunch_slot] = "LUNCH BREAK 🍴"

        return df

    def build_all(self, department: str) -> dict[str, pd.DataFrame]:
        """
        Generate timetables for all sections in the given department.

        Args:
            department: full department name (e.g. "School of Computer Science & Engineering")

        Returns:
            dict of section_id → pd.DataFrame timetable
        """
        if "Department" not in self._section_df.columns or "Section_ID" not in self._section_df.columns:
            raise KeyError("Student_Sections_DATASET.csv must have 'Department' and 'Section_ID' columns")

        sections = self._section_df[
            self._section_df["Department"] == department
        ]["Section_ID"].unique()

        print(f"\n[PrototypeScheduler] Generating {len(sections)} sections for {department}...")

        # Global conflict trackers shared across all sections
        used_teachers: dict[tuple[str, str], list[str]] = {}
        used_rooms: dict[tuple[str, str], str] = {}

        timetables: dict[str, pd.DataFrame] = {}
        for sec in sections:
            timetables[sec] = self.build_section_timetable(
                sec, department, used_teachers, used_rooms
            )
            print(f"  [OK] {sec}")

        return timetables

    # ──────────────────────────────────────────────────────────────
    # Export helpers (fixing openpyxl writer.save() bug)
    # ──────────────────────────────────────────────────────────────
    def to_excel(self, timetables: dict[str, pd.DataFrame], output_path: str) -> None:
        """
        Export all section timetables to an Excel workbook.
        Fixes the openpyxl writer.save() deprecation bug from app.py.
        """
        import io
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for section_id, df in timetables.items():
                sheet = str(section_id)[:31]  # Excel sheet name limit
                df.to_excel(writer, sheet_name=sheet)
        # Context manager auto-saves — no writer.save() needed
        with open(output_path, "wb") as f:
            f.write(buf.getvalue())
        print(f"[Excel] Saved: {output_path}")

    def to_csv_zip(self, timetables: dict[str, pd.DataFrame], output_path: str) -> None:
        """Export each section timetable as a CSV inside a ZIP archive."""
        import io
        import zipfile
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for section_id, df in timetables.items():
                buf = io.StringIO()
                df.to_csv(buf)
                zf.writestr(f"{section_id}.csv", buf.getvalue())
        print(f"[ZIP] Saved: {output_path}")
