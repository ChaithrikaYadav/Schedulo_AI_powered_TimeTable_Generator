"""
scripts/seed_from_csvs.py — Seeds the ChronoAI database from all six CSV files.

Run once after `alembic upgrade head` (PostgreSQL) or after `create_all_tables()` (SQLite):
    python scripts/seed_from_csvs.py

The script:
  1. Loads all 6 CSV files
  2. Normalizes department names via DEPT_CODE_MAP
  3. Fixes known data quality issues (wrong dept tags, duplicates, float credits)
  4. Inserts/upserts all entities into the database
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronoai.database import AsyncSessionLocal, create_all_tables
from chronoai.models import Department, Faculty, Room, Section, Subject

# ─────────────────────────────────────────────────────────────────
# Department name normalisation map
# ─────────────────────────────────────────────────────────────────
DEPT_CODE_MAP: dict[str, str] = {
    "CSE": "School of Computer Science & Engineering",
    "CSE ": "School of Computer Science & Engineering",      # trailing space variant
    "School of Computer Science & Engineering": "School of Computer Science & Engineering",
    "Law": "IILM Law School",
    "IILM Law School": "IILM Law School",
    "Design": "School of Design",
    "School of Design": "School of Design",
    "Psychology": "School of Psychology",
    "School of Psychology": "School of Psychology",
    "Journalism & Communication": "School of Journalism & Communication",
    "School of Journalism & Communication": "School of Journalism & Communication",
    "Liberal Arts & Social Sciences": "School of Liberal Arts & Social Sciences",
    "School of Liberal Arts & Social Sciences": "School of Liberal Arts & Social Sciences",
    "Biotechnology": "School of Biotechnology",
    "School of Biotechnology": "School of Biotechnology",
    "Management": "School of Management",
    "School of Management": "School of Management",
    "Hospitality": "School of Hospitality & Services Management",
    "School of Hospitality & Services Management": "School of Hospitality & Services Management",
    "General / Shared": "General",
    "General": "General",
    "Science": "Science Labs",
    "Electronics": "Electronics Labs",
    "Engineering": "Engineering Labs",
}

# Reverse map: short_code → full name
SHORT_CODE_MAP: dict[str, str] = {
    "CSE": "School of Computer Science & Engineering",
    "MAN": "School of Management",
    "LAW": "IILM Law School",
    "HOS": "School of Hospitality & Services Management",
    "DES": "School of Design",
    "PSY": "School of Psychology",
    "JOU": "School of Journalism & Communication",
    "LIB": "School of Liberal Arts & Social Sciences",
    "BIO": "School of Biotechnology",
    "GEN": "General",
}

# Teacher ID prefix → department full name
TEACHER_ID_DEPT_MAP: dict[str, str] = {
    "T-CSE": "School of Computer Science & Engineering",
    "T-MAN": "School of Management",
    "T-LAW": "IILM Law School",
    "T-HOS": "School of Hospitality & Services Management",
    "T-DES": "School of Design",
    "T-PSY": "School of Psychology",
    "T-JOU": "School of Journalism & Communication",
    "T-LIB": "School of Liberal Arts & Social Sciences",
    "T-BIO": "School of Biotechnology",
}

# Section ID prefix → department short code
SECTION_DEPT_PATTERN = re.compile(r"^\d+([A-Z]+)\d+$")

CSV_DIR = Path(__file__).parent.parent   # project root


def _s(x: object) -> str:
    """Safely convert any value to a stripped string."""
    if pd.isna(x):
        return ""
    return str(x).strip()


def _bool(x: object) -> bool:
    """Convert Yes/No/True/False/1/0 to Python bool."""
    return str(x).strip().lower() in {"yes", "y", "true", "1"}


def _normalise_dept(raw: str) -> str:
    """Return the canonical full department name for a raw CSV dept string."""
    raw = _s(raw)
    return DEPT_CODE_MAP.get(raw, raw)


def _dept_from_teacher_id(tid: str) -> str:
    """Derive department full name from a Teacher ID prefix (e.g. 'T-CSE-001')."""
    for prefix, dept in TEACHER_ID_DEPT_MAP.items():
        if tid.startswith(prefix):
            return dept
    return ""


# ─────────────────────────────────────────────────────────────────
# Subject department correction heuristics (fixes data quality bug)
# ─────────────────────────────────────────────────────────────────
LAW_KEYWORDS = {"law", "legal", "constitution", "moot", "judiciary", "contract", "tort",
                "property", "criminal", "jurisprudence", "evidence", "arbitration", "ipr"}
DESIGN_KEYWORDS = {"design", "fashion", "textile", "craft", "studio", "visual", "typography",
                   "color", "ergonomics", "illustration", "portfolio", "rendering"}
PSYCH_KEYWORDS = {"psychology", "psycho", "counseling", "behaviour", "cognitive", "emotion",
                  "therapy", "mental", "personality", "research methods"}
JOURN_KEYWORDS = {"journalism", "media", "communication", "broadcasting", "editing",
                  "reporting", "public relation", "advertising", "digital media"}
LIBERAL_KEYWORDS = {"sociology", "philosophy", "economics", "history", "political",
                    "gender studies", "culture", "international", "literature"}
BIO_KEYWORDS = {"biotechnology", "biochemistry", "microbiology", "genetics", "cell biology",
                "immunology", "bioinformatics", "molecular", "bioprocess", "pharmacology"}
HOSP_KEYWORDS = {"hospitality", "hotel", "culinary", "food", "beverage", "front office",
                 "housekeeping", "tourism", "catering"}
MGMT_KEYWORDS = {"management", "marketing", "finance", "accounting", "hrm", "economics",
                 "entrepreneurship", "business", "organisational", "mba", "bba"}


def _infer_dept_from_subject_name(name: str) -> str:
    """Heuristic: infer the correct department from subject name keywords."""
    lower = name.lower()
    for kw in LAW_KEYWORDS:
        if kw in lower:
            return "IILM Law School"
    for kw in BIO_KEYWORDS:
        if kw in lower:
            return "School of Biotechnology"
    for kw in DESIGN_KEYWORDS:
        if kw in lower:
            return "School of Design"
    for kw in PSYCH_KEYWORDS:
        if kw in lower:
            return "School of Psychology"
    for kw in JOURN_KEYWORDS:
        if kw in lower:
            return "School of Journalism & Communication"
    for kw in LIBERAL_KEYWORDS:
        if kw in lower:
            return "School of Liberal Arts & Social Sciences"
    for kw in HOSP_KEYWORDS:
        if kw in lower:
            return "School of Hospitality & Services Management"
    for kw in MGMT_KEYWORDS:
        if kw in lower:
            return "School of Management"
    return "School of Computer Science & Engineering"


# ─────────────────────────────────────────────────────────────────
# Department seeder (hardcoded canonical list)
# ─────────────────────────────────────────────────────────────────
CANONICAL_DEPARTMENTS = [
    ("School of Computer Science & Engineering", "CSE"),
    ("School of Management", "MAN"),
    ("IILM Law School", "LAW"),
    ("School of Hospitality & Services Management", "HOS"),
    ("School of Design", "DES"),
    ("School of Psychology", "PSY"),
    ("School of Journalism & Communication", "JOU"),
    ("School of Liberal Arts & Social Sciences", "LIB"),
    ("School of Biotechnology", "BIO"),
    ("General", "GEN"),
]


async def seed_departments(session: AsyncSession) -> dict[str, int]:
    """Insert canonical departments and return a name→id map."""
    dept_id_map: dict[str, int] = {}
    for name, code in CANONICAL_DEPARTMENTS:
        result = await session.execute(select(Department).where(Department.short_code == code))
        dept = result.scalar_one_or_none()
        if not dept:
            dept = Department(name=name, short_code=code)
            session.add(dept)
            await session.flush()
        dept_id_map[name] = dept.id
        dept_id_map[code] = dept.id        # also map by short code for convenience
    print(f"  ✅ {len(CANONICAL_DEPARTMENTS)} departments seeded")
    return dept_id_map


# ─────────────────────────────────────────────────────────────────
# Faculty seeder
# ─────────────────────────────────────────────────────────────────
async def seed_faculty(session: AsyncSession, dept_id_map: dict[str, int]) -> None:
    """Load Teachers_Dataset.csv → faculty table, then merge faculty_dataset_final.csv."""

    # ── Pass 1: Teachers_Dataset.csv ──────────────────────────────
    csv_path = CSV_DIR / "Teachers_Dataset.csv"
    if not csv_path.exists():
        print(f"  ⚠ {csv_path} not found — skipping")
        return

    df = pd.read_csv(csv_path)
    inserted = 0
    for _, row in df.iterrows():
        tid = _s(row.get("Teacher ID", ""))
        name = _s(row.get("Teacher Name", ""))
        if not name:
            continue

        # Fix: derive dept from Teacher ID prefix (CSV dept column is incorrect)
        dept_name = _dept_from_teacher_id(tid) or _normalise_dept(_s(row.get("Department", "")))
        dept_id = dept_id_map.get(dept_name)

        # Check for duplicate
        result = await session.execute(select(Faculty).where(Faculty.teacher_id == tid))
        existing = result.scalar_one_or_none()
        if existing:
            continue

        fac = Faculty(
            teacher_id=tid or None,
            name=name,
            department_id=dept_id,
            main_subject=_s(row.get("Main Subject", "")) or None,
            backup_subject=_s(row.get("Backup Subject", "")) or None,
            max_classes_per_week=int(row.get("Max Classes/Week", 16)) if _s(row.get("Max Classes/Week", "")) else 16,
            preferred_slots=_s(row.get("Preferred Slots", "Any")) or "Any",
            can_take_labs=_bool(row.get("Can Take Labs", "No")),
            can_be_coordinator=_bool(row.get("Can Be Class Coordinator", "No")),
        )
        session.add(fac)
        inserted += 1

    await session.flush()
    print(f"  ✅ {inserted} faculty records from Teachers_Dataset.csv")

    # ── Pass 2: faculty_dataset_final.csv (upsert by name) ────────
    csv2_path = CSV_DIR / "faculty_dataset_final.csv"
    if not csv2_path.exists():
        print(f"  ⚠ {csv2_path} not found — skipping extra merge")
        return

    df2 = pd.read_csv(csv2_path)
    merged = 0
    new_records = 0
    for _, row in df2.iterrows():
        fname = _s(row.get("Faculty_Name", ""))
        subj = _s(row.get("Subject_Handled", ""))
        dept_raw = _s(row.get("Department", ""))
        dept_name = _normalise_dept(dept_raw)
        dept_id = dept_id_map.get(dept_name)

        if not fname:
            continue

        # Try to find existing record by name match
        result = await session.execute(
            select(Faculty).where(Faculty.name.ilike(f"%{fname}%")).limit(1)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Merge extra info
            if not existing.faculty_name:
                existing.faculty_name = fname
            if subj and not existing.subject_handled:
                existing.subject_handled = subj
            merged += 1
        else:
            # New faculty not in Teachers_Dataset.csv
            new_fac = Faculty(
                name=fname,
                faculty_name=fname,
                department_id=dept_id,
                subject_handled=subj or None,
                max_classes_per_week=16,
                preferred_slots="Any",
                can_take_labs=False,
                can_be_coordinator=False,
            )
            session.add(new_fac)
            new_records += 1

    await session.flush()
    print(f"  ✅ faculty_dataset_final.csv: {merged} merged, {new_records} new")


# ─────────────────────────────────────────────────────────────────
# Subject seeder
# ─────────────────────────────────────────────────────────────────
async def seed_subjects(session: AsyncSession, dept_id_map: dict[str, int]) -> None:
    """Load Subjects_Dataset.csv + course_dataset_final.csv → subjects table."""

    seen_subjects: set[str] = set()
    inserted = 0

    # ── Subjects_Dataset.csv ──────────────────────────────────────
    csv1 = CSV_DIR / "Subjects_Dataset.csv"
    if csv1.exists():
        df1 = pd.read_csv(csv1)
        for _, row in df1.iterrows():
            name = _s(row.get("Subject Name", ""))
            if not name or name.lower() in seen_subjects:
                continue   # deduplicate (e.g. "Computer Networks" appears 4×)
            seen_subjects.add(name.lower())

            stype = _s(row.get("Subject Type", "Theory")) or "Theory"
            raw_dept = _s(row.get("Department", ""))
            credits_raw = row.get("Credits", 4)
            try:
                credits = float(credits_raw)
            except (ValueError, TypeError):
                credits = 4.0

            # Fix: many non-CSE subjects are wrongly tagged as CSE → re-infer
            dept_name = _normalise_dept(raw_dept)
            if dept_name == "School of Computer Science & Engineering":
                inferred = _infer_dept_from_subject_name(name)
                dept_name = inferred

            dept_id = dept_id_map.get(dept_name)

            # Derive weekly_periods from type + credits
            if stype == "Lab":
                weekly_periods = 2
                consecutive = True
                lab_dur = 2
            elif stype == "Project":
                weekly_periods = 1
                consecutive = False
                lab_dur = 1
            else:
                weekly_periods = int(credits)
                consecutive = False
                lab_dur = 1

            subj = Subject(
                name=name,
                department_id=dept_id,
                subject_type=stype,
                credits=credits,
                weekly_periods=weekly_periods,
                requires_consecutive_lab=consecutive,
                lab_duration_periods=lab_dur,
            )
            session.add(subj)
            inserted += 1

    await session.flush()
    print(f"  ✅ {inserted} subjects from Subjects_Dataset.csv (deduplicated)")

    # ── course_dataset_final.csv (CSE authoritative catalogue) ────
    csv2 = CSV_DIR / "course_dataset_final.csv"
    inserted2 = 0
    if csv2.exists():
        df2 = pd.read_csv(csv2)
        cse_dept_id = dept_id_map.get("CSE") or dept_id_map.get("School of Computer Science & Engineering")
        for _, row in df2.iterrows():
            name = _s(row.get("Subject", ""))
            if not name or name.lower() in seen_subjects:
                continue
            seen_subjects.add(name.lower())

            credits_raw = row.get("Credits", 4.0)
            try:
                credits = float(credits_raw)
            except (ValueError, TypeError):
                credits = 4.0
            weekly_periods = int(credits)

            subj = Subject(
                name=name,
                department_id=cse_dept_id,
                subject_type="Theory",
                credits=credits,
                weekly_periods=weekly_periods,
                requires_consecutive_lab=False,
                lab_duration_periods=1,
            )
            session.add(subj)
            inserted2 += 1

    await session.flush()
    print(f"  ✅ {inserted2} additional subjects from course_dataset_final.csv")


# ─────────────────────────────────────────────────────────────────
# Room seeder
# ─────────────────────────────────────────────────────────────────
async def seed_rooms(session: AsyncSession, dept_id_map: dict[str, int]) -> None:
    """Load Room_Dataset.csv → rooms table. Uses the newer file (not Room_Dataset__1_.csv)."""

    csv_path = CSV_DIR / "Room_Dataset.csv"
    if not csv_path.exists():
        print(f"  ⚠ {csv_path} not found — skipping")
        return

    df = pd.read_csv(csv_path)
    inserted = 0
    for _, row in df.iterrows():
        room_id = _s(row.get("Room ID", ""))
        if not room_id:
            continue

        result = await session.execute(select(Room).where(Room.room_id == room_id))
        if result.scalar_one_or_none():
            continue  # already exists

        rtype = _s(row.get("Type", "Classroom")) or "Classroom"
        floor_raw = row.get("Floor", None)
        try:
            floor = int(floor_raw) if floor_raw and not pd.isna(floor_raw) else None
        except (ValueError, TypeError):
            floor = None

        room = Room(
            room_id=room_id,
            building=_s(row.get("Building", "")) or "UNKNOWN",
            floor=floor,
            room_number=_s(row.get("Room Number", "")) or None,
            room_type=rtype,
            department=_normalise_dept(_s(row.get("Department", ""))) or None,
            capacity=60,
            has_projector=True,
            has_computers=(rtype.lower() in {"lab", "dell lab", "dell_lab", "special"}),
        )
        session.add(room)
        inserted += 1

    await session.flush()
    print(f"  ✅ {inserted} rooms from Room_Dataset.csv")


# ─────────────────────────────────────────────────────────────────
# Section seeder
# ─────────────────────────────────────────────────────────────────
async def seed_sections(session: AsyncSession, dept_id_map: dict[str, int]) -> None:
    """Load Student_Sections_DATASET.csv → sections table."""

    csv_path = CSV_DIR / "Student_Sections_DATASET.csv"
    if not csv_path.exists():
        print(f"  ⚠ {csv_path} not found — skipping")
        return

    df = pd.read_csv(csv_path)
    inserted = 0
    for _, row in df.iterrows():
        sec_id = _s(row.get("Section_ID", ""))
        if not sec_id:
            continue

        result = await session.execute(select(Section).where(Section.section_id == sec_id))
        if result.scalar_one_or_none():
            continue

        dept_raw = _s(row.get("Department", ""))
        dept_name = _normalise_dept(dept_raw)
        dept_id = dept_id_map.get(dept_name)

        strength_raw = row.get("Strength", 50)
        try:
            strength = int(strength_raw)
        except (ValueError, TypeError):
            strength = 50

        duration_raw = row.get("Duration (Years)", None)
        try:
            duration = int(duration_raw) if duration_raw and not pd.isna(duration_raw) else None
        except (ValueError, TypeError):
            duration = None

        ga = strength // 2
        gb = strength - ga

        sec = Section(
            section_id=sec_id,
            department_id=dept_id,
            duration_years=duration,
            semester=_s(row.get("Semester", "")) or None,
            strength=strength,
            program=_s(row.get("Program", "")) or None,
            group_a_count=ga,
            group_b_count=gb,
        )
        session.add(sec)
        inserted += 1

    await session.flush()
    print(f"  ✅ {inserted} sections from Student_Sections_DATASET.csv")


# ─────────────────────────────────────────────────────────────────
# Main entrypoint
# ─────────────────────────────────────────────────────────────────
async def main() -> None:
    """Run all seeders in dependency order."""
    print("\n🌱 ChronoAI — Seeding database from CSV files...\n")

    # Ensure tables exist (SQLite prototype mode)
    await create_all_tables()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            print("📂 Step 1/5: Departments")
            dept_id_map = await seed_departments(session)

            print("\n📂 Step 2/5: Faculty")
            await seed_faculty(session, dept_id_map)

            print("\n📂 Step 3/5: Subjects")
            await seed_subjects(session, dept_id_map)

            print("\n📂 Step 4/5: Rooms")
            await seed_rooms(session, dept_id_map)

            print("\n📂 Step 5/5: Sections")
            await seed_sections(session, dept_id_map)

    print("\n✅ Database seeded successfully!\n")
    print("Expected counts:")
    print("  Departments : 9 (+ 1 General)")
    print("  Faculty     : ~90 (Teachers_Dataset) + extra from faculty_dataset_final")
    print("  Subjects    : ~273 (Subjects_Dataset) + unique from course_dataset_final")
    print("  Rooms       : 132")
    print("  Sections    : 117")


if __name__ == "__main__":
    asyncio.run(main())
