"""
schedulo/api_gateway/routes/timetable.py
FastAPI router for timetable generation and retrieval endpoints.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schedulo.config import get_settings
from schedulo.database import get_db

router = APIRouter()
_settings = get_settings()
_log = logging.getLogger(__name__)

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
_ABBREV_MAP: dict[str, str] = {
    "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
    "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday",
}


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CustomSubject(BaseModel):
    name: str
    subject_type: str = "THEORY"
    duration: int = 1
    days_per_week: int = 3
    priority: int = 1


class GenerateRequest(BaseModel):
    department: str
    academic_year: str = "2025-26"
    semester: Optional[str] = None
    random_seed: Optional[int] = None
    ga_enabled: bool = False
    algorithm: Optional[str] = None  # fcfs | priority | round_robin | prototype
    custom_subjects: Optional[List[CustomSubject]] = None


class GenerateResponse(BaseModel):
    timetable_id: int
    job_id: str          # B8: expose job_id for WebSocket progress subscription
    status: str
    message: str


# ── Helper ────────────────────────────────────────────────────────────────────

def _normalize_day(day_str: str) -> str:
    s = str(day_str).strip()
    if s in _DAY_NAMES:
        return s
    return _ABBREV_MAP.get(s, s)


def _make_name(department: str, academic_year: str, semester: Optional[str],
               custom_subjects: Optional[List[CustomSubject]]) -> str:
    """Create a human-readable, unique timetable name."""
    ts = datetime.now().strftime("%d %b %H:%M")
    parts = [department, f"— {academic_year}"]
    if semester:
        parts.append(f"({semester})")
    if custom_subjects:
        names = ", ".join(s.name for s in custom_subjects[:2])
        if len(custom_subjects) > 2:
            names += f" +{len(custom_subjects) - 2} more"
        parts.append(f"[Custom: {names}]")
    parts.append(f"@ {ts}")
    return " ".join(parts)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", summary="List all timetables")
async def list_timetables(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    from schedulo.models import Timetable, Department
    query = select(Timetable).order_by(Timetable.created_at.desc()).limit(limit)
    if status:
        query = query.where(Timetable.status == status.upper())
    result = await db.execute(query)
    timetables = result.scalars().all()

    # B2: resolve department names in one pass to avoid N+1 queries
    dept_ids = {tt.department_id for tt in timetables if tt.department_id}
    dept_map: dict[int, str] = {}
    if dept_ids:
        dept_result = await db.execute(
            select(Department).where(Department.id.in_(dept_ids))
        )
        dept_map = {d.id: d.name for d in dept_result.scalars().all()}

    return [
        {
            "id":                  tt.id,
            "name":               tt.name,
            "department":         dept_map.get(tt.department_id) if tt.department_id else None,
            "status":             tt.status,
            "academic_year":      tt.academic_year,
            "semester":           tt.semester,
            "ga_fitness_score":   tt.ga_fitness_score,
            "conflict_count":     tt.conflict_count or 0,
            "generation_time_ms": tt.generation_time_ms,
            "created_at":         str(tt.created_at),
        }
        for tt in timetables
    ]


@router.post("/generate", response_model=GenerateResponse)
async def generate_timetable(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from schedulo.scheduler_core.prototype_scheduler import PrototypeScheduler
    from schedulo.models import Timetable, TimetableSlot, Department, Section
    from sqlalchemy import select as sa_select

    t0 = time.time()

    # ── All algorithm choices map to the deterministic 6-phase PrototypeScheduler ──
    algo_key = req.algorithm or ("ga" if req.ga_enabled else "prototype")
    SchedulerClass = PrototypeScheduler
    scheduler = SchedulerClass(random_seed=req.random_seed)

    if req.custom_subjects:
        scheduler.inject_custom_subjects([
            {
                "name":          s.name,
                "subject_type":  s.subject_type,
                "duration":      s.duration,
                "days_per_week": s.days_per_week,
                "priority":      s.priority,
            }
            for s in req.custom_subjects
        ])

    try:
        timetables = scheduler.build_all(req.department)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scheduling failed: {exc}")

    dept_result = await db.execute(sa_select(Department).where(Department.name == req.department))
    dept = dept_result.scalar_one_or_none()

    # ── Build a descriptive, unique name ─────────────────────────────────────
    tt_name = _make_name(req.department, req.academic_year, req.semester, req.custom_subjects)

    tt = Timetable(
        name=tt_name,
        department_id=dept.id if dept else None,
        academic_year=req.academic_year,
        semester=req.semester,
        status="COMPLETED",
        generation_params=json.dumps({
            "random_seed": req.random_seed,
            "department": req.department,
            "algorithm": algo_key,
            "has_custom_subjects": bool(req.custom_subjects),
            "custom_subject_names": [s.name for s in req.custom_subjects] if req.custom_subjects else [],
        }),
        conflict_count=0,
        generation_time_ms=int((time.time() - t0) * 1000),
    )
    db.add(tt)
    await db.flush()

    # ── Persist ALL slots ─────────────────────────────────────────────────────
    for section_id_str, df in timetables.items():
        sec_result = await db.execute(sa_select(Section).where(Section.section_id == section_id_str))
        sec = sec_result.scalar_one_or_none()

        for day_idx, day in enumerate(df.index):
            full_day = _normalize_day(str(day))

            for col_idx, period in enumerate(df.columns):
                cell_raw = df.loc[day, period]
                cell = str(cell_raw).strip() if cell_raw is not None else ""
                cu = cell.upper()

                if not cell or cell in ("NAN", "NONE", ""):
                    slot_type, cell = "FREE", ""
                elif "LUNCH" in cu:
                    slot_type = "LUNCH"
                elif "(LAB" in cu:
                    slot_type = "LAB"
                elif "CONT." in cu or "CONTINUATION" in cu:
                    slot_type = "LAB_CONT"
                else:
                    slot_type = "THEORY"

                lines = [ln.strip() for ln in cell.split("\n") if ln.strip()] if cell else []

                if slot_type == "LUNCH":
                    line1, line2, line3 = "LUNCH", None, None
                elif slot_type == "FREE":
                    line1, line2, line3 = None, None, None
                else:
                    line1 = lines[0] if len(lines) > 0 else None
                    line2 = lines[1] if len(lines) > 1 else None
                    line3 = lines[2] if len(lines) > 2 else None

                db.add(TimetableSlot(
                    timetable_id=tt.id,
                    section_id=sec.id if sec else None,
                    day_of_week=day_idx,
                    day_name=full_day,
                    period_number=col_idx + 1,
                    period_label=str(period),
                    slot_type=slot_type,
                    is_lab_continuation=(slot_type == "LAB_CONT"),
                    cell_display_line1=line1,
                    cell_display_line2=line2,
                    cell_display_line3=line3,
                ))

    await db.flush()

    # ── Write output files ────────────────────────────────────────────────────
    try:
        out_dir = Path(_settings.output_dir) / str(tt.id)
        out_dir.mkdir(parents=True, exist_ok=True)
        xlsx_path = str(out_dir / "timetable.xlsx")
        zip_path  = str(out_dir / "timetable.zip")
        scheduler.to_excel(timetables, xlsx_path)
        scheduler.to_csv_zip(timetables, zip_path)
        params = json.loads(tt.generation_params or "{}")
        params.update({"output_xlsx": xlsx_path, "output_zip": zip_path, "section_count": len(timetables)})
        tt.generation_params = json.dumps(params)
    except Exception as exc:
        _log.warning("Failed to write output files: %s", exc)

    # B8: generate a job_id so the frontend WebSocket client can subscribe
    job_id = f"job-{tt.id}-{uuid.uuid4().hex[:8]}"

    return GenerateResponse(
        timetable_id=tt.id,
        job_id=job_id,
        status="COMPLETED",
        message=f"Generated {len(timetables)} section timetables in {tt.generation_time_ms}ms",
    )


@router.get("/{timetable_id}/slots", summary="Get all slots for a timetable")
async def get_timetable_slots(
    timetable_id: int,
    section_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    from schedulo.models import TimetableSlot

    query = (
        select(TimetableSlot)
        .where(TimetableSlot.timetable_id == timetable_id)
        .order_by(TimetableSlot.section_id, TimetableSlot.day_of_week, TimetableSlot.period_number)
    )
    if section_id is not None:
        query = query.where(TimetableSlot.section_id == section_id)

    result = await db.execute(query)
    slots = result.scalars().all()

    return [
        {
            "id":                  s.id,
            "day_name":            s.day_name,
            "period_number":       s.period_number,
            "period_label":        s.period_label or "",
            "slot_type":           s.slot_type,
            "cell_display_line1":  s.cell_display_line1,
            "cell_display_line2":  s.cell_display_line2,
            "cell_display_line3":  s.cell_display_line3,
            "is_lab_continuation": s.is_lab_continuation,
            "section_id":          s.section_id,
        }
        for s in slots
    ]


@router.get("/{timetable_id}/download/{file_format}", summary="Download timetable as Excel or CSV zip")
async def download_timetable(
    timetable_id: int,
    file_format: str,  # "xlsx" | "zip"
    db: AsyncSession = Depends(get_db),
):
    """
    Download a previously generated timetable file.
    Supported formats: xlsx (Excel), zip (CSV bundle).
    If the file doesn't exist yet, regenerate it on-the-fly.
    """
    from schedulo.models import Timetable

    result = await db.execute(select(Timetable).where(Timetable.id == timetable_id))
    tt = result.scalar_one_or_none()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")

    fmt = file_format.lower().strip(".")
    if fmt not in ("xlsx", "zip", "excel", "csv"):
        raise HTTPException(status_code=400, detail="Format must be xlsx or zip")
    if fmt in ("excel",):
        fmt = "xlsx"
    if fmt == "csv":
        fmt = "zip"

    out_dir = Path(_settings.output_dir) / str(timetable_id)
    file_path = out_dir / f"timetable.{fmt}"

    # If file doesn't exist, regenerate from DB slots
    if not file_path.exists():
        try:
            file_path = await _regenerate_file(tt, fmt, out_dir, db)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not generate file: {exc}")

    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if fmt == "xlsx"
        else "application/zip"
    )
    safe_name = (tt.name or f"timetable-{timetable_id}").replace(" ", "_").replace("/", "-")
    filename = f"{safe_name}.{fmt}"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )


async def _regenerate_file(tt, fmt: str, out_dir: Path, db) -> Path:
    """Regenerate Excel/ZIP from stored slots when the file is missing."""
    from schedulo.models import TimetableSlot, Section
    from sqlalchemy import select as sa_select
    import pandas as pd

    from schedulo.scheduler_core.prototype_scheduler import PERIODS, DAYS

    # Load all slots for this timetable
    result = await db.execute(
        sa_select(TimetableSlot)
        .where(TimetableSlot.timetable_id == tt.id)
        .order_by(TimetableSlot.section_id, TimetableSlot.day_of_week, TimetableSlot.period_number)
    )
    slots = result.scalars().all()

    # Group by section
    from collections import defaultdict
    section_slots: dict[int, list] = defaultdict(list)
    for s in slots:
        section_slots[s.section_id or 0].append(s)

    # Rebuild DataFrames per section
    timetables: dict[str, pd.DataFrame] = {}
    for sec_id, sec_slots in section_slots.items():
        # Fetch section name
        sec_result = await db.execute(sa_select(Section).where(Section.id == sec_id))
        sec = sec_result.scalar_one_or_none()
        sec_name = sec.section_id if sec else str(sec_id)

        df = pd.DataFrame("", index=DAYS, columns=PERIODS)
        for sl in sec_slots:
            if sl.day_name in df.index and sl.period_number >= 1:
                col_idx = sl.period_number - 1
                if col_idx < len(PERIODS):
                    col = PERIODS[col_idx]
                    parts = [p for p in [sl.cell_display_line1, sl.cell_display_line2, sl.cell_display_line3] if p]
                    df.loc[sl.day_name, col] = "\n".join(parts)
        timetables[sec_name] = df

    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"timetable.{fmt}"

    from schedulo.scheduler_core.prototype_scheduler import PrototypeScheduler
    dummy = PrototypeScheduler.__new__(PrototypeScheduler)

    if fmt == "xlsx":
        dummy.to_excel(timetables, str(file_path))
    else:
        dummy.to_csv_zip(timetables, str(file_path))

    return file_path


@router.get("/{timetable_id}", summary="Get a single timetable")
async def get_timetable(timetable_id: int, db: AsyncSession = Depends(get_db)):
    from schedulo.models import Timetable

    result = await db.execute(select(Timetable).where(Timetable.id == timetable_id))
    tt = result.scalar_one_or_none()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")
    params = json.loads(tt.generation_params or "{}")
    return {
        "id":                tt.id,
        "name":              tt.name,
        "status":            tt.status,
        "conflict_count":    tt.conflict_count,
        "academic_year":     tt.academic_year,
        "semester":          tt.semester,
        "created_at":        str(tt.created_at),
        "has_xlsx":          bool(params.get("output_xlsx")),
        "has_zip":           bool(params.get("output_zip")),
    }


@router.get("/{timetable_id}/sections", summary="Get sections in a timetable")
async def get_timetable_sections(timetable_id: int, db: AsyncSession = Depends(get_db)):
    from schedulo.models import TimetableSlot, Section
    from sqlalchemy import distinct

    # Get distinct section DB IDs + their section_id string labels
    result = await db.execute(
        select(distinct(TimetableSlot.section_id))
        .where(TimetableSlot.timetable_id == timetable_id)
    )
    section_db_ids = [r[0] for r in result.all() if r[0] is not None]

    # Resolve section labels
    sections = []
    for sid in section_db_ids:
        sec_result = await db.execute(select(Section).where(Section.id == sid))
        sec = sec_result.scalar_one_or_none()
        sections.append({"id": sid, "label": sec.section_id if sec else f"Section {sid}"})

    return {"timetable_id": timetable_id, "sections": sections}


@router.delete("/{timetable_id}", summary="Delete a timetable")
async def delete_timetable(timetable_id: int, db: AsyncSession = Depends(get_db)):
    from schedulo.models import Timetable

    result = await db.execute(select(Timetable).where(Timetable.id == timetable_id))
    tt = result.scalar_one_or_none()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")
    await db.delete(tt)
    await db.commit()   # B6: commit so the deletion is actually persisted
    return {"message": f"Timetable {timetable_id} deleted"}
