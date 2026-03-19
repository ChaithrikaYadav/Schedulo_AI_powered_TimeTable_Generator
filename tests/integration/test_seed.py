"""
tests/integration/test_seed.py
Integration test for seed_from_csvs.py.

Verifies that the CSV seeder correctly loads data into an in-memory
SQLite database and produces the expected counts.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# Check CSV availability
_CSVS_EXIST = all([
    (ROOT / "Room_Dataset.csv").exists(),
    (ROOT / "Student_Sections_DATASET.csv").exists(),
    (ROOT / "Subjects_Dataset.csv").exists(),
    (ROOT / "Teachers_Dataset.csv").exists(),
])


@pytest.mark.asyncio
@pytest.mark.skipif(not _CSVS_EXIST, reason="Required CSV files not found in project root")
class TestSeedFromCSVs:
    """Integration tests running the full seed pipeline against the test DB."""

    async def test_departments_seeded_correctly(self, async_session):
        """Should have exactly 10 canonical departments after seeding."""
        from sqlalchemy import select, func
        from chronoai.models import Department
        from scripts.seed_from_csvs import seed_departments

        dept_map = await seed_departments(async_session)

        result = await async_session.execute(select(func.count()).select_from(Department))
        count = result.scalar()
        assert count == 10, f"Expected 10 departments, got {count}"
        # Verify CSE is present
        assert "School of Computer Science & Engineering" in dept_map

    async def test_rooms_seeded(self, async_session):
        """Should seed ≥ 100 rooms from Room_Dataset.csv."""
        from sqlalchemy import select, func
        from chronoai.models import Department, Room
        from scripts.seed_from_csvs import seed_departments, seed_rooms

        dept_map = await seed_departments(async_session)
        await seed_rooms(async_session, dept_map)

        result = await async_session.execute(select(func.count()).select_from(Room))
        count = result.scalar()
        assert count >= 100, f"Expected ≥100 rooms, got {count}"

    async def test_sections_seeded(self, async_session):
        """Should seed ≥ 100 sections from Student_Sections_DATASET.csv."""
        from sqlalchemy import select, func
        from chronoai.models import Department, Section
        from scripts.seed_from_csvs import seed_departments, seed_sections

        dept_map = await seed_departments(async_session)
        await seed_sections(async_session, dept_map)

        result = await async_session.execute(select(func.count()).select_from(Section))
        count = result.scalar()
        assert count >= 100, f"Expected ≥100 sections, got {count}"

    async def test_faculty_seeded(self, async_session):
        """Should seed ≥ 50 faculty records."""
        from sqlalchemy import select, func
        from chronoai.models import Department, Faculty
        from scripts.seed_from_csvs import seed_departments, seed_faculty

        dept_map = await seed_departments(async_session)
        await seed_faculty(async_session, dept_map)

        result = await async_session.execute(select(func.count()).select_from(Faculty))
        count = result.scalar()
        assert count >= 50, f"Expected ≥50 faculty, got {count}"

    async def test_subjects_seeded(self, async_session):
        """Should seed ≥ 100 unique subjects."""
        from sqlalchemy import select, func
        from chronoai.models import Department, Subject
        from scripts.seed_from_csvs import seed_departments, seed_subjects

        dept_map = await seed_departments(async_session)
        await seed_subjects(async_session, dept_map)

        result = await async_session.execute(select(func.count()).select_from(Subject))
        count = result.scalar()
        assert count >= 100, f"Expected ≥100 subjects, got {count}"

    async def test_idempotency(self, async_session):
        """Running seed twice should not create duplicate records."""
        from sqlalchemy import select, func
        from chronoai.models import Department
        from scripts.seed_from_csvs import seed_departments

        # Seed twice
        await seed_departments(async_session)
        await seed_departments(async_session)

        result = await async_session.execute(select(func.count()).select_from(Department))
        count = result.scalar()
        # Must still be exactly 10 (no duplicates)
        assert count == 10, f"Idempotency broken: {count} departments found"


@pytest.mark.asyncio
class TestSeedWithoutCSVs:
    """Basic seeding tests that work without CSVs."""

    async def test_departments_seeded_standalone(self, async_session):
        """seed_departments() should always succeed (hardcoded list, no CSV needed)."""
        from chronoai.models import Department
        from sqlalchemy import select, func
        from scripts.seed_from_csvs import seed_departments

        dept_map = await seed_departments(async_session)
        assert isinstance(dept_map, dict)
        assert len(dept_map) >= 10  # 10 full names + short codes

        result = await async_session.execute(select(func.count()).select_from(Department))
        count = result.scalar()
        assert count == 10

    async def test_dept_map_contains_short_codes(self, async_session):
        """dept_id_map should have both full names and short codes as keys."""
        from scripts.seed_from_csvs import seed_departments
        dept_map = await seed_departments(async_session)
        # Short codes
        assert "CSE" in dept_map
        assert "MAN" in dept_map
        assert "LAW" in dept_map
