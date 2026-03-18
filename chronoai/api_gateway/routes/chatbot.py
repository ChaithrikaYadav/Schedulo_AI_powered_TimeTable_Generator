"""
chronoai/api_gateway/routes/chatbot.py
FastAPI router — ChronoBot streaming SSE endpoint.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from chronoai.database import get_db

router = APIRouter()


class ChatbotRequest(BaseModel):
    message: str
    session_id: str | None = None
    timetable_id: int | None = None
    faculty_id: int | None = None


class ChatbotResponse(BaseModel):
    session_id: str
    response: str


@router.post("/stream")
async def chatbot_stream(req: ChatbotRequest, db: AsyncSession = Depends(get_db)):
    """
    Streaming SSE endpoint for ChronoBot.
    Yields Server-Sent Events: token | tool_call | tool_result | done
    """
    from chronoai.chatbot_service.llm_client import ChronoBotLLMClient, build_system_prompt
    from chronoai.models import ChatbotConversation, Faculty
    from sqlalchemy import select

    session_id = req.session_id or str(uuid.uuid4())

    # Load or create conversation
    result = await db.execute(
        select(ChatbotConversation).where(ChatbotConversation.session_id == session_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        conv = ChatbotConversation(
            session_id=session_id,
            timetable_id=req.timetable_id,
            faculty_id=req.faculty_id,
            messages=json.dumps([]),
        )
        db.add(conv)
        await db.flush()

    # Load message history
    history: list[dict] = json.loads(conv.messages or "[]")

    # Build faculty context
    faculty_name, faculty_id_str, sections_list = "Unknown", "N/A", []
    if req.faculty_id:
        fac_result = await db.execute(select(Faculty).where(Faculty.id == req.faculty_id))
        fac = fac_result.scalar_one_or_none()
        if fac:
            faculty_name = fac.name
            faculty_id_str = fac.teacher_id or str(fac.id)

    system_prompt = build_system_prompt(
        timetable_id=req.timetable_id or 0,
        faculty_name=faculty_name,
        faculty_id=faculty_id_str,
        sections_list=sections_list,
        current_date=datetime.now().strftime("%Y-%m-%d"),
    )

    async def event_stream():
        client = ChronoBotLLMClient()
        prompt = client.format_prompt(system_prompt, history, req.message)
        full_response = ""

        try:
            # Stream tokens
            for token in client.stream_response(prompt):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                await asyncio.sleep(0)  # yield control

            # Parse tool calls from accumulated response
            tool_calls = client.parse_tool_calls(full_response)
            for tc in tool_calls:
                yield f"data: {json.dumps({'type': 'tool_call', 'name': tc.get('name'), 'input': tc.get('arguments', {})})}\n\n"
                result = await _execute_tool(tc.get("name", ""), tc.get("arguments", {}), db)
                yield f"data: {json.dumps({'type': 'tool_result', 'content': result})}\n\n"

            # Persist updated conversation
            history.append({"role": "user", "content": req.message, "timestamp": datetime.now().isoformat()})
            history.append({"role": "assistant", "content": full_response, "timestamp": datetime.now().isoformat()})
            conv.messages = json.dumps(history[-50:])  # Keep last 50 messages
            await db.commit()

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str, db: AsyncSession = Depends(get_db)):
    """Return the message history for a given chatbot session."""
    from chronoai.models import ChatbotConversation
    from sqlalchemy import select
    result = await db.execute(
        select(ChatbotConversation).where(ChatbotConversation.session_id == session_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": json.loads(conv.messages or "[]")}


@router.delete("/history/{session_id}")
async def clear_history(session_id: str, db: AsyncSession = Depends(get_db)):
    """Clear conversation history for a session."""
    from chronoai.models import ChatbotConversation
    from sqlalchemy import select
    result = await db.execute(
        select(ChatbotConversation).where(ChatbotConversation.session_id == session_id)
    )
    conv = result.scalar_one_or_none()
    if conv:
        conv.messages = json.dumps([])
        await db.flush()
    return {"message": "History cleared"}


async def _execute_tool(tool_name: str, arguments: dict, db: AsyncSession) -> dict:
    """Dispatch tool calls from ChronoBot to the appropriate handler."""
    match tool_name:
        case "query_timetable":
            return await _tool_query_timetable(arguments, db)
        case "check_constraint_violation":
            return {"result": "Constraint validation not yet connected to live timetable"}
        case "check_room_availability":
            return await _tool_room_availability(arguments, db)
        case "check_faculty_slots":
            return await _tool_faculty_slots(arguments, db)
        case "apply_slot_swap":
            return {"result": "Slot swap requires user confirmation — send confirmed=true to apply"}
        case "undo_last_change":
            return {"result": "Undo functionality requires an active session with recorded changes"}
        case _:
            return {"error": f"Unknown tool: {tool_name}"}


async def _tool_query_timetable(args: dict, db: AsyncSession) -> dict:
    from chronoai.models import TimetableSlot
    from sqlalchemy import select
    q = select(TimetableSlot)
    if "section_id" in args:
        q = q.where(TimetableSlot.section_id == args["section_id"])
    if "day" in args:
        q = q.where(TimetableSlot.day_name == args["day"])
    if "period" in args:
        q = q.where(TimetableSlot.period_number == args["period"])
    result = await db.execute(q.limit(20))
    slots = result.scalars().all()
    return {"slots": [{"day": s.day_name, "period": s.period_number, "type": s.slot_type,
                       "subject": s.cell_display_line1, "faculty": s.cell_display_line2} for s in slots]}


async def _tool_room_availability(args: dict, db: AsyncSession) -> dict:
    from chronoai.models import TimetableSlot
    from sqlalchemy import select
    room_id = args.get("room_id")
    day = args.get("day")
    period = args.get("period")
    result = await db.execute(
        select(TimetableSlot).where(
            TimetableSlot.cell_display_line3.contains(room_id or ""),
            TimetableSlot.day_name == day,
            TimetableSlot.period_number == period,
        ).limit(1)
    )
    occupied = result.scalar_one_or_none()
    return {"room_id": room_id, "day": day, "period": period, "available": occupied is None}


async def _tool_faculty_slots(args: dict, db: AsyncSession) -> dict:
    from chronoai.models import TimetableSlot
    from sqlalchemy import select
    fac_id = args.get("faculty_id")
    day = args.get("day")
    result = await db.execute(
        select(TimetableSlot).where(
            TimetableSlot.cell_display_line2.contains(str(fac_id) if fac_id else ""),
            TimetableSlot.day_name == day,
        ).limit(20)
    )
    slots = result.scalars().all()
    return {"faculty_id": fac_id, "day": day,
            "slots": [{"period": s.period_number, "subject": s.cell_display_line1, "room": s.cell_display_line3} for s in slots]}
