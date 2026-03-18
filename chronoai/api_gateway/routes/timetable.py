"""
chronoai/api_gateway/routes/timetable.py
FastAPI router for timetable generation and retrieval endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from chronoai.database import get_db

router = APIRouter()


class GenerateRequest(BaseModel):
    department: str
    academic_year: str = "2025-26"
    semester: str | None = None
    random_seed: int | None = None
    ga_enabled: bool = False


class GenerateResponse(BaseModel):
    timetable_id: int
    status: str
    message: str


@router.post("/generate", response_model=GenerateResponse)
async def generate_timetable(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger timetable generation for a department.
    Uses PrototypeScheduler for immediate results or Celery task for full ML pipeline.
    """
    from chronoai.scheduler_core.prototype_scheduler import PrototypeScheduler
    from chronoai.models import Timetable, TimetableSlot
    import json, time

    start = time.time()
    scheduler = PrototypeScheduler(random_seed=req.random_seed)

    try:
        timetables = scheduler.build_all(req.department)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scheduling failed: {e}")

    # Persist timetable record
    from chronoai.models import Department
    from sqlalchemy import select
    dept_result = await db.execute(select(Department).where(Department.name == req.department))
    dept = dept_result.scalar_one_or_none()

    tt = Timetable(
        name=f"{req.department} — {req.academic_year}",
        department_id=dept.id if dept else None,
        academic_year=req.academic_year,
        semester=req.semester,
        status="COMPLETED",
        generation_params=json.dumps({"random_seed": req.random_seed, "department": req.department}),
        conflict_count=0,
        generation_time_ms=int((time.time() - start) * 1000),
    )
    db.add(tt)
    await db.flush()

    # Persist timetable slots
    from chronoai.scheduler_core.prototype_scheduler import PERIODS, DAYS
    from chronoai.models import Section
    from sqlalchemy import select as sa_select

    for section_id, df in timetables.items():
        sec_result = await db.execute(sa_select(Section).where(Section.section_id == section_id))
        sec = sec_result.scalar_one_or_none()

        for day_idx, day in enumerate(df.index):
            for p_idx, period in enumerate(df.columns):
                cell = str(df.loc[day, period]).strip()
                if not cell:
                    continue

                slot_type = "FREE"
                if "LUNCH" in cell.upper():
                    slot_type = "LUNCH"
                elif "(Lab" in cell:
                    slot_type = "LAB"
                elif "cont." in cell:
                    slot_type = "LAB"
                else:
                    slot_type = "THEORY"

                lines = cell.split("\n")
                slot = TimetableSlot(
                    timetable_id=tt.id,
                    section_id=sec.id if sec else None,
                    day_of_week=day_idx,
                    day_name=str(day),
                    period_number=p_idx + 1,
                    period_label=str(period),
                    slot_type=slot_type,
                    is_lab_continuation="cont." in cell,
                    cell_display_line1=lines[0] if len(lines) > 0 else None,
                    cell_display_line2=lines[1] if len(lines) > 1 else None,
                    cell_display_line3=lines[2] if len(lines) > 2 else None,
                )
                db.add(slot)

    await db.flush()
    return GenerateResponse(
        timetable_id=tt.id,
        status="COMPLETED",
        message=f"Generated {len(timetables)} section timetables in {tt.generation_time_ms}ms",
    )


@router.get("/{timetable_id}")
async def get_timetable(timetable_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve a timetable record by ID."""
    from chronoai.models import Timetable
    from sqlalchemy import select
    result = await db.execute(select(Timetable).where(Timetable.id == timetable_id))
    tt = result.scalar_one_or_none()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")
    return {"id": tt.id, "name": tt.name, "status": tt.status, "conflict_count": tt.conflict_count}


@router.get("/{timetable_id}/sections")
async def get_timetable_sections(timetable_id: int, db: AsyncSession = Depends(get_db)):
    """Return all section IDs that have slots in a timetable."""
    from chronoai.models import TimetableSlot, Section
    from sqlalchemy import select, distinct
    result = await db.execute(
        select(distinct(TimetableSlot.section_id)).where(TimetableSlot.timetable_id == timetable_id)
    )
    section_ids = [r[0] for r in result.all() if r[0] is not None]
    return {"timetable_id": timetable_id, "section_ids": section_ids}


@router.delete("/{timetable_id}")
async def delete_timetable(timetable_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a timetable and all its slots."""
    from chronoai.models import Timetable
    from sqlalchemy import select
    result = await db.execute(select(Timetable).where(Timetable.id == timetable_id))
    tt = result.scalar_one_or_none()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")
    await db.delete(tt)
    return {"message": f"Timetable {timetable_id} deleted"}
