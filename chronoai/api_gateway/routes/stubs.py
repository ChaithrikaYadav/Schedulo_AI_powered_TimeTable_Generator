"""Stub routers for rooms, sections, subjects, conflicts, export, analytics, auth."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from chronoai.database import get_db

# ── Rooms ────────────────────────────────────────────────────────
router_rooms = APIRouter()

@router_rooms.get("/")
async def list_rooms(db: AsyncSession = Depends(get_db)):
    from chronoai.models import Room
    result = await db.execute(select(Room).limit(200))
    rooms = result.scalars().all()
    return [{"id": r.id, "room_id": r.room_id, "building": r.building,
             "type": r.room_type, "capacity": r.capacity} for r in rooms]

@router_rooms.get("/available")
async def available_rooms(day: str, period: int, timetable_id: int, db: AsyncSession = Depends(get_db)):
    from chronoai.models import Room, TimetableSlot
    all_rooms = (await db.execute(select(Room))).scalars().all()
    occupied_ids = set(
        r[0] for r in (await db.execute(
            select(TimetableSlot.room_id).where(
                TimetableSlot.timetable_id == timetable_id,
                TimetableSlot.day_name == day,
                TimetableSlot.period_number == period,
            )
        )).all() if r[0]
    )
    return [{"room_id": r.room_id, "type": r.room_type, "building": r.building}
            for r in all_rooms if r.id not in occupied_ids]

# Alias for router registration in main.py
router = router_rooms


# ── Sections ─────────────────────────────────────────────────────
from fastapi import APIRouter as _AR
router_sections = _AR()

@router_sections.get("/")
async def list_sections(db: AsyncSession = Depends(get_db)):
    from chronoai.models import Section
    result = await db.execute(select(Section).limit(200))
    sections = result.scalars().all()
    return [{"id": s.id, "section_id": s.section_id, "semester": s.semester,
             "strength": s.strength, "program": s.program} for s in sections]


# ── Subjects ─────────────────────────────────────────────────────
router_subjects = _AR()

@router_subjects.get("/")
async def list_subjects(db: AsyncSession = Depends(get_db)):
    from chronoai.models import Subject
    result = await db.execute(select(Subject).limit(300))
    subjects = result.scalars().all()
    return [{"id": s.id, "name": s.name, "type": s.subject_type,
             "credits": float(s.credits or 0), "weekly_periods": s.weekly_periods} for s in subjects]


# ── Conflicts ────────────────────────────────────────────────────
router_conflicts = _AR()

@router_conflicts.get("/")
async def list_conflicts(timetable_id: int, db: AsyncSession = Depends(get_db)):
    from chronoai.models import ConflictLog
    result = await db.execute(
        select(ConflictLog).where(ConflictLog.timetable_id == timetable_id).limit(100)
    )
    conflicts = result.scalars().all()
    return [{"id": c.id, "type": c.conflict_type, "severity": c.severity,
             "description": c.description, "resolved": c.resolved} for c in conflicts]


# ── Export ───────────────────────────────────────────────────────
router_export = _AR()

@router_export.post("/xlsx")
async def export_xlsx(timetable_id: int, db: AsyncSession = Depends(get_db)):
    """Generate Excel export of all sections in a timetable."""
    from chronoai.models import TimetableSlot
    from fastapi.responses import StreamingResponse
    import io, pandas as pd
    result = await db.execute(
        select(TimetableSlot).where(TimetableSlot.timetable_id == timetable_id)
    )
    slots = result.scalars().all()
    if not slots:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No slots found for this timetable")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        rows = [{"Day": s.day_name, "Period": s.period_label, "Type": s.slot_type,
                 "Subject": s.cell_display_line1, "Faculty": s.cell_display_line2,
                 "Room": s.cell_display_line3, "Section_ID": s.section_id} for s in slots]
        df = pd.DataFrame(rows)
        df.to_excel(writer, index=False, sheet_name="Timetable")

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=timetable_{timetable_id}.xlsx"},
    )


# ── Analytics ────────────────────────────────────────────────────
router_analytics = _AR()

@router_analytics.get("/summary/{timetable_id}")
async def analytics_summary(timetable_id: int, db: AsyncSession = Depends(get_db)):
    from chronoai.models import TimetableSlot, ConflictLog
    slots_r = await db.execute(
        select(TimetableSlot).where(TimetableSlot.timetable_id == timetable_id)
    )
    slots = slots_r.scalars().all()
    conflicts_r = await db.execute(
        select(ConflictLog).where(ConflictLog.timetable_id == timetable_id)
    )
    conflicts = conflicts_r.scalars().all()
    type_counts = {}
    for s in slots:
        type_counts[s.slot_type] = type_counts.get(s.slot_type, 0) + 1
    return {
        "timetable_id": timetable_id,
        "total_slots": len(slots),
        "slot_type_distribution": type_counts,
        "total_conflicts": len(conflicts),
        "unresolved_conflicts": sum(1 for c in conflicts if not c.resolved),
    }


# ── Auth ─────────────────────────────────────────────────────────
from fastapi.security import OAuth2PasswordRequestForm
router_auth = _AR()

@router_auth.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Placeholder auth endpoint — returns mock JWT for prototype."""
    import secrets
    if form_data.username and form_data.password:
        return {
            "access_token": secrets.token_urlsafe(32),
            "token_type": "bearer",
            "user": form_data.username,
        }
    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="Invalid credentials")

@router_auth.get("/me")
async def get_me():
    """Return current user (stub for prototype)."""
    return {"username": "admin", "role": "administrator", "department": "CSE"}
