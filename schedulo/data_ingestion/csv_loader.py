"""
schedulo/data_ingestion/csv_loader.py
CSV → SQLAlchemy async ingestion pipeline for Schedulo.

Loads all 6 CSVs into the database, handling deduplication and FK relationships.
Column mapping is driven by DEPT_CODE_MAP and canonical column aliases.

BUG 7 FIX: Added idempotency guard (skip duplicate inserts on re-run) and
           department correction logic to prevent cross-department subject pollution.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

logger = logging.getLogger(__name__)

# ── Department name → code mapping ──────────────────────────────────
DEPT_CODE_MAP: dict[str, str] = {
    "School of Computer Science & Engineering": "CSE",
    "School of Computer Science and Engineering": "CSE",
    "School of Electronics & Communication Engineering": "ECE",
    "School of Electronics and Communication Engineering": "ECE",
    "School of Electrical & Electronics Engineering": "EEE",
    "School of Electrical and Electronics Engineering": "EEE",
    "School of Mechanical Engineering": "ME",
    "School of Civil Engineering": "CE",
    "School of Information Technology": "IT",
    "School of Artificial Intelligence & Machine Learning": "AIML",
    "School of Artificial Intelligence and Machine Learning": "AIML",
    "School of Management": "MAN",
    "School of Hospitality & Services Management": "HOS",
    "School of Hospitality and Services Management": "HOS",
    "IILM Law School": "LAW",
    "School of Design": "DES",
    "School of Psychology": "PSY",
    "School of Journalism & Communication": "JOU",
    "School of Liberal Arts & Social Sciences": "LIB",
    "School of Biotechnology": "BIO",
}

# ── Reverse map: code → full department name ─────────────────────────
_CODE_TO_DEPT: dict[str, str] = {v: k for k, v in DEPT_CODE_MAP.items()}

CSV_ROOT = Path(__file__).parent.parent.parent


def _s(x: object) -> str:
    """Safe string conversion — returns '' for NaN/None."""
    if pd.isna(x):  # type: ignore[arg-type]
        return ""
    return str(x).strip()


def _f(x: object, default: float = 0.0) -> float:
    """Safe float conversion."""
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _i(x: object, default: int = 0) -> int:
    """Safe int conversion."""
    try:
        return int(float(x))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ── BUG 7 FIX: Subject name → real department keyword lists ─────────────
# Used by _correct_subject_department() to fix CSV mislabelling.

_HOSPITALITY_KEYWORDS = [
    "bakery", "confectionery", "f&b", "food production", "housekeeping",
    "front office", "hotel", "hospitality", "culinary", "gastronomy",
    "nutrition", "hygiene", "bar operations", "wine", "tourism geography",
    "industrial exposure training", "resort", "food cost",
    "food & beverage", "food and beverage", "french language for hospitality",
    "hospitality law", "hospitality ethics",
]

_MANAGEMENT_KEYWORDS = [
    "business economics", "business law", "financial management",
    "financial accounting", "corporate finance", "taxation laws",
    "marketing management", "human resource management",
    "banking & insurance", "banking and insurance",
    "entrepreneurship", "organizational behavior", "organisational behavior",
    "consumer behavior", "retail management", "crm systems",
    "supply chain", "e-commerce", "advertising & sales",
    "advertising and sales",
]

_LAW_KEYWORDS = [
    "constitutional law", "criminal law", "law of contracts",
    "family law", "legal methods", "moot court", "jurisprudence",
    "property law", "administrative law", "cyber law",
    "intellectual property", "competition law",
]

_BIOTECH_KEYWORDS = [
    "cell biology", "genetics", "microbiology", "immunology",
    "molecular biology", "bioprocess", "fermentation", "tissue culture",
    "proteomics", "enzyme technology", "bioremediation", "virology",
]


def _correct_subject_department(subject_name: str, raw_dept: str) -> str:
    """
    BUG 7 FIX: Apply department correction for subjects wrongly tagged in CSVs.
    Uses keyword matching on subject name to determine the true department.
    Falls back to the raw_dept value when no keywords match.
    """
    name_lower = subject_name.lower()

    if any(kw in name_lower for kw in _HOSPITALITY_KEYWORDS):
        return "School of Hospitality & Services Management"
    if any(kw in name_lower for kw in _MANAGEMENT_KEYWORDS):
        return "School of Management"
    if any(kw in name_lower for kw in _LAW_KEYWORDS):
        return "IILM Law School"
    if any(kw in name_lower for kw in _BIOTECH_KEYWORDS):
        return "School of Biotechnology"

    # Normalize short codes like "CSE" -> full name
    return _CODE_TO_DEPT.get(raw_dept, raw_dept)


class CSVIngestionPipeline:
    """
    Loads all 6 CSV datasets into the Schedulo database.

    Order matters (FK dependencies):
        1. Rooms
        2. Faculty / Teachers
        3. Subjects / Courses
        4. Sections
        5. (TimetableSlot rows come from scheduler, not CSV)
    """

    def __init__(self, session: AsyncSession, csv_root: Path | None = None) -> None:
        self._db = session
        self._root = csv_root or CSV_ROOT

    # ── Public entry point ────────────────────────────────────────
    async def run_all(self) -> dict[str, int]:
        """
        Execute all loaders in dependency order.

        Returns:
            dict mapping table_name → rows_inserted
        """
        counts: dict[str, int] = {}
        counts["rooms"] = await self._load_rooms()
        counts["faculty"] = await self._load_faculty()
        counts["subjects"] = await self._load_subjects()
        counts["sections"] = await self._load_sections()
        await self._db.commit()
        logger.info("CSV ingestion complete", extra={"counts": counts})
        return counts

    # ── Room loader ───────────────────────────────────────────────
    async def _load_rooms(self) -> int:
        from schedulo.models import Room

        files = ["Room_Dataset.csv", "Room_Dataset (1).csv"]
        frame = self._read_first(files)
        if frame is None:
            logger.warning("No room CSV found")
            return 0

        inserted = 0
        seen: set[str] = set()

        for _, row in frame.iterrows():
            room_id = _s(row.get("Room ID") or row.get("room_id") or "")
            if not room_id or room_id in seen:
                continue
            seen.add(room_id)

            exists = (await self._db.execute(
                select(Room).where(Room.room_id == room_id)
            )).scalar_one_or_none()
            if exists:
                continue

            room_type_raw = _s(row.get("Type") or row.get("room_type") or "Classroom")
            building = _s(row.get("Building") or row.get("block") or "Main Block")
            capacity = _i(row.get("Capacity") or row.get("capacity") or 60)

            self._db.add(Room(
                room_id=room_id,
                room_type=room_type_raw,
                building=building,
                capacity=capacity,
                floor=_i(row.get("Floor") or 0),
                projector=str(row.get("Projector", "No")).strip().lower() in {"yes", "y", "1"},
                ac=str(row.get("AC", "No")).strip().lower() in {"yes", "y", "1"},
            ))
            inserted += 1

        await self._db.flush()
        logger.info(f"Rooms: {inserted} inserted")
        return inserted

    # ── Faculty loader ─────────────────────────────────────────────
    async def _load_faculty(self) -> int:
        from schedulo.models import Faculty

        files = ["Teachers_Dataset.csv", "faculty_dataset_final.csv"]
        inserted = 0

        for fname in files:
            path = self._root / fname
            if not path.exists():
                continue
            frame = pd.read_csv(path)

            for _, row in frame.iterrows():
                # Handle both CSV column schemas
                tid = _s(row.get("Teacher ID") or row.get("Faculty_ID") or "")
                name = _s(row.get("Teacher Name") or row.get("Faculty_Name") or "")
                if not name:
                    continue

                exists = (await self._db.execute(
                    select(Faculty).where(Faculty.name == name)
                )).scalar_one_or_none()
                if exists:
                    continue

                dept_raw = _s(row.get("Department") or row.get("Department_Name") or "")
                designation = _s(row.get("Designation") or row.get("designation") or "Assistant Professor")
                max_cls = _i(row.get("Max Classes/Week") or row.get("max_classes") or 16)
                pref_slots = _s(row.get("Preferred Slots") or "Any")
                can_lab = str(row.get("Can Take Labs", "No")).strip().lower() in {"yes", "y", "1"}
                subject_handled = _s(row.get("Main Subject") or row.get("Subject_Handled") or "")

                self._db.add(Faculty(
                    teacher_id=tid or f"TCH-{name[:3].upper()}-{inserted:04d}",
                    name=name,
                    department=dept_raw,
                    department_code=DEPT_CODE_MAP.get(dept_raw, "GEN"),
                    designation=designation,
                    email=_s(row.get("Email") or "").lower() or f"{name.lower().replace(' ', '.')}@university.edu",
                    max_classes_per_week=max_cls,
                    preferred_slots=pref_slots,
                    can_take_labs=can_lab,
                    subject_specialisation=subject_handled,
                ))
                inserted += 1

        await self._db.flush()
        logger.info(f"Faculty: {inserted} inserted")
        return inserted

    # ── Subject loader (BUG 7 FIX) ───────────────────────────────
    async def _load_subjects(self) -> int:
        """
        BUG 7 FIX:
        1. Applies department correction to prevent cross-dept pollution.
        2. Idempotency: skips rows that already exist (name + dept + type).
        3. Uses (name, dept_id, subject_type) as the unique key — not just name.
        """
        from schedulo.models import Subject, Department

        # Build dept_name → dept_id cache
        dept_result = await self._db.execute(select(Department))
        dept_name_to_id: dict[str, int] = {}
        for dept in dept_result.scalars().all():
            dept_name_to_id[dept.name] = dept.id

        files = ["Subjects_Dataset.csv", "course_dataset_final.csv"]
        inserted = 0

        for fname in files:
            path = self._root / fname
            if not path.exists():
                continue
            frame = pd.read_csv(path)

            for _, row in frame.iterrows():
                name = _s(
                    row.get("Subject Name") or row.get("Subject") or
                    row.get("course_name") or ""
                )
                if not name:
                    continue

                s_type = _s(row.get("Subject Type") or row.get("type") or "Theory")
                credits = _f(row.get("Credits") or row.get("credits") or 4)
                raw_dept = _s(row.get("Department") or row.get("department") or "")

                # ── BUG 7 FIX: correct mislabelled departments ──────────────
                corrected_dept = _correct_subject_department(name, raw_dept)
                dept_id = dept_name_to_id.get(corrected_dept)
                # Fall back to looking up the raw dept if correction finds nothing
                if dept_id is None and raw_dept:
                    dept_id = dept_name_to_id.get(raw_dept)

                # ── BUG 7 FIX: idempotency — check (name, dept_id, type) ───
                exists = (await self._db.execute(
                    select(Subject).where(
                        Subject.name == name,
                        Subject.department_id == dept_id if dept_id else Subject.name == name,
                        Subject.subject_type == s_type,
                    )
                )).scalar_one_or_none()
                if exists:
                    continue

                semester_raw = row.get("Semester") or row.get("semester") or None
                semester_str: str | None = None
                if semester_raw is not None and str(semester_raw).strip() not in ("", "nan", "0"):
                    try:
                        sem_int = int(float(semester_raw))
                        semester_str = f"Sem {sem_int}" if sem_int > 0 else None
                    except (ValueError, TypeError):
                        semester_str = str(semester_raw).strip() or None

                # Derive weekly_periods: Lab=2, Project=1, else credits
                if s_type == "Lab":
                    weekly = 2
                elif s_type == "Project":
                    weekly = 1
                else:
                    weekly = max(1, int(credits))

                is_elective = str(row.get("Elective", "No")).strip().lower() in {"yes", "y", "1"}

                self._db.add(Subject(
                    name=name,
                    subject_code=_s(row.get("Subject Code") or row.get("code") or ""),
                    subject_type=s_type,
                    credits=credits,
                    weekly_periods=weekly,
                    department=corrected_dept if corrected_dept else raw_dept,
                    department_id=dept_id,
                    department_code=DEPT_CODE_MAP.get(corrected_dept, DEPT_CODE_MAP.get(raw_dept, "GEN")),
                    semester=semester_str,
                    is_elective=is_elective,
                    elective_group_code=_s(row.get("Elective Group") or ""),
                ))
                inserted += 1

        await self._db.flush()
        logger.info(f"Subjects: {inserted} inserted")
        return inserted

    # ── Section loader ────────────────────────────────────────────
    async def _load_sections(self) -> int:
        from schedulo.models import Section

        path = self._root / "Student_Sections_DATASET.csv"
        if not path.exists():
            logger.warning("Student_Sections_DATASET.csv not found")
            return 0

        frame = pd.read_csv(path)
        inserted = 0

        for _, row in frame.iterrows():
            section_id = _s(row.get("Section_ID") or row.get("section_id") or "")
            if not section_id:
                continue

            exists = (await self._db.execute(
                select(Section).where(Section.section_id == section_id)
            )).scalar_one_or_none()
            if exists:
                continue

            dept = _s(row.get("Department") or "")
            self._db.add(Section(
                section_id=section_id,
                department=dept,
                department_code=DEPT_CODE_MAP.get(dept, "GEN"),
                semester=_i(row.get("Semester") or 0),
                program=_s(row.get("Program") or row.get("program") or "B.Tech"),
                strength=_i(row.get("Strength") or row.get("strength") or 60),
                academic_year=_s(row.get("Academic_Year") or "2024-25"),
                batch=_s(row.get("Batch") or ""),
            ))
            inserted += 1

        await self._db.flush()
        logger.info(f"Sections: {inserted} inserted")
        return inserted

    # ── Helpers ───────────────────────────────────────────────────
    def _read_first(self, filenames: list[str]) -> pd.DataFrame | None:
        """Return the first readable DataFrame from a list of filenames."""
        for fname in filenames:
            path = self._root / fname
            if path.exists():
                return pd.read_csv(path)
        return None
