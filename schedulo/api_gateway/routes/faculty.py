"""
schedulo/api_gateway/routes/faculty.py — Faculty CRUD endpoints.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from schedulo.database import get_db
from schedulo.models import Faculty

router = APIRouter()


class FacultyOut(BaseModel):
    id: int
    teacher_id: str | None
    name: str
    main_subject: str | None
    preferred_slots: str | None
    max_classes_per_week: int | None
    can_take_labs: bool | None
    model_config = {"from_attributes": True}


@router.get("/", response_model=list[FacultyOut])
async def list_faculty(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Faculty).limit(200))
    return result.scalars().all()


@router.get("/{faculty_id}", response_model=FacultyOut)
async def get_faculty(faculty_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Faculty).where(Faculty.id == faculty_id))
    fac = result.scalar_one_or_none()
    if not fac:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return fac


@router.get("/{faculty_id}/schedule")
async def get_faculty_schedule(faculty_id: int, timetable_id: int, db: AsyncSession = Depends(get_db)):
    """Return all timetable slots for a faculty member."""
    from schedulo.models import TimetableSlot
    result = await db.execute(
        select(TimetableSlot).where(TimetableSlot.timetable_id == timetable_id).limit(200)
    )
    slots = result.scalars().all()
    return [{"day": s.day_name, "period": s.period_number, "subject": s.cell_display_line1,
             "room": s.cell_display_line3, "type": s.slot_type} for s in slots]
