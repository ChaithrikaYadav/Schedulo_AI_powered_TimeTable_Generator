"""
tests/conftest.py — Shared pytest fixtures for ChronoAI tests.

Fixtures:
    async_engine    — In-memory SQLite SQLAlchemy async engine
    async_session   — AsyncSession bound to the test engine
    test_client     — httpx AsyncClient wrapping the FastAPI app
    sample_timetable_dict — Minimal timetable dict for ML tests
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Async mode ────────────────────────────────────────────────────────────────
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy for tests."""
    return asyncio.DefaultEventLoopPolicy()


# ── In-memory SQLite engine ───────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create a fresh in-memory SQLite async engine for each test."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from chronoai.database import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator:
    """Provide an async SQLAlchemy session that rolls back after each test."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ── FastAPI test client ───────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="function")
async def test_client(async_engine):
    """httpx AsyncClient wrapping the FastAPI app, using the test DB engine."""
    import httpx
    from chronoai.main import app
    from chronoai import database as db_module

    # Patch the session factory to use our test engine
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    test_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    original_factory = db_module.AsyncSessionLocal
    db_module.AsyncSessionLocal = test_factory

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client

    db_module.AsyncSessionLocal = original_factory


# ── Sample data ───────────────────────────────────────────────────────────────
@pytest.fixture
def sample_timetable_dict() -> dict:
    """
    Minimal timetable dict for ML pipeline tests.
    Represents a 2-section CSE timetable with 108 slots (6 days × 9 periods × 2 sections).
    """
    slots = []
    DAYS = 6
    PERIODS = 9
    SECTIONS = 2
    slot_types = ["THEORY", "THEORY", "THEORY", "LAB", "LUNCH", "FREE", "THEORY", "THEORY", "FREE"]

    slot_id = 1
    for sec in range(SECTIONS):
        for day in range(DAYS):
            for period in range(1, PERIODS + 1):
                stype = slot_types[(period - 1) % len(slot_types)]
                slots.append({
                    "id": slot_id,
                    "day": day,
                    "period": period,
                    "slot_type": stype,
                    "faculty_id": ((slot_id % 5) + 1) if stype not in {"FREE", "LUNCH"} else None,
                    "room_id": ((slot_id % 10) + 1) if stype not in {"FREE", "LUNCH"} else None,
                    "is_lab_continuation": (stype == "LAB" and period % 2 == 0),
                    "notes": "lab-room" if stype == "LAB" else "",
                    "section_id": sec + 1,
                })
                slot_id += 1

    return {
        "slots": slots,
        "conflict_count": 2,
        "generation_time_ms": 3500,
        "ga_fitness_score": 78.5,
        "section_count": SECTIONS,
    }


@pytest.fixture
def clean_timetable_dict() -> dict:
    """A high-quality timetable dict (zero conflicts, full utilization)."""
    slots = []
    DAYS = 6
    PERIODS = 9
    slot_types_clean = ["THEORY", "THEORY", "THEORY", "LAB", "LUNCH", "THEORY", "THEORY", "THEORY", "THEORY"]

    for day in range(DAYS):
        for period in range(1, PERIODS + 1):
            stype = slot_types_clean[period - 1]
            slots.append({
                "id": day * 9 + period,
                "day": day,
                "period": period,
                "slot_type": stype,
                "faculty_id": (period % 5) + 1 if stype not in {"LUNCH"} else None,
                "room_id": (period % 10) + 1 if stype not in {"LUNCH"} else None,
                "is_lab_continuation": (stype == "LAB" and period % 2 == 0),
                "notes": "lab-room" if stype == "LAB" else "",
            })

    return {
        "slots": slots,
        "conflict_count": 0,
        "generation_time_ms": 1200,
        "ga_fitness_score": 92.0,
        "section_count": 1,
    }
