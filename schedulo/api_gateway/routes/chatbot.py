"""
schedulo/api_gateway/routes/chatbot.py
FastAPI router — ScheduloBot REST + SSE endpoints.

/chat   → simple JSON response (used by the frontend)
/stream → SSE streaming (for future use)
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from schedulo.config import get_settings
from schedulo.database import get_db

router = APIRouter()
settings = get_settings()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    timetable_id: int | None = None
    faculty_id: int | None = None
    # Optional per-request API key overrides (from frontend localStorage)
    groq_api_key: str | None = None
    hf_api_token: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    source: str = "ai"          # "ai" | "db" | "fallback"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_hf_token_valid(token: str | None = None) -> bool:
    t = token or settings.hf_api_token
    return bool(t) and t != "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" and t.startswith("hf_")


def _is_groq_key_valid(key: str | None = None) -> bool:
    k = key or settings.groq_api_key
    return bool(k) and len(k) > 10


# ── Tier 1: Groq LLM (fast, free) ────────────────────────────────────────────

def _call_groq(system_prompt: str, history: list[dict], user_message: str, api_key: str | None = None) -> str:
    """Call Groq Cloud API (llama3-8b). Raises on failure."""
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("groq package not installed")

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-10:]:
        role = msg.get("role", "user")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_message})

    key = api_key or settings.groq_api_key
    client = Groq(api_key=key)
    completion = client.chat.completions.create(
        model=settings.groq_model,
        messages=messages,
        temperature=0.3,
        max_tokens=1024,
    )
    return completion.choices[0].message.content.strip()


# ── Tier 2: HuggingFace InferenceClient ──────────────────────────────────────

def _call_hf(system_prompt: str, history: list[dict], user_message: str, api_token: str | None = None) -> str:
    """Call HuggingFace Inference API. Raises on failure."""
    from schedulo.chatbot_service.llm_client import ScheduloBotLLMClient
    client = ScheduloBotLLMClient(token_override=api_token)
    prompt = client.format_prompt(system_prompt, history, user_message)
    return client.complete(prompt)


# ── Tier 3: Smart DB-query fallback ──────────────────────────────────────────

async def _db_smart_response(message: str, timetable_id: int | None, db: AsyncSession) -> str:
    """
    Rule-based fallback that queries the real database and returns structured answers.
    Gives useful real information even when no AI key is available.
    """
    from schedulo.models import TimetableSlot, Section, Timetable
    from sqlalchemy import select, func

    q = message.lower()

    # ── "show me classes on Monday / Tuesday / etc." ─────────────────────────
    DAYS = {
        "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday",
        "thursday": "Thursday", "friday": "Friday", "saturday": "Saturday",
    }
    matched_day = next((DAYS[d] for d in DAYS if d in q), None)
    if matched_day and timetable_id:
        stmt = (
            select(TimetableSlot)
            .where(
                TimetableSlot.timetable_id == timetable_id,
                TimetableSlot.day_name == matched_day,
                TimetableSlot.slot_type.in_(["THEORY", "LAB"]),
            )
            .order_by(TimetableSlot.section_id, TimetableSlot.period_number)
            .limit(30)
        )
        result = await db.execute(stmt)
        slots = result.scalars().all()
        if slots:
            lines = [f"📅 **{matched_day} timetable** (Timetable #{timetable_id})\n"]
            current_sec = None
            for s in slots:
                if s.section_id != current_sec:
                    current_sec = s.section_id
                    lines.append(f"\n**Section {s.section_id}**")
                subj = s.cell_display_line1 or "—"
                fac  = s.cell_display_line2 or "—"
                room = s.cell_display_line3 or "—"
                lines.append(f"  P{s.period_number}: {subj} | {fac} | 📍{room}")
            return "\n".join(lines)
        return f"📅 No classes found on {matched_day} for this timetable."

    # ── "who teaches <subject>" ───────────────────────────────────────────────
    teaches_match = re.search(r"who teaches (.+?)[\?]?$", q)
    if teaches_match and timetable_id:
        subject_query = teaches_match.group(1).strip()
        stmt = (
            select(TimetableSlot)
            .where(
                TimetableSlot.timetable_id == timetable_id,
                TimetableSlot.cell_display_line1.ilike(f"%{subject_query}%"),
            )
            .limit(10)
        )
        result = await db.execute(stmt)
        slots = result.scalars().all()
        if slots:
            faculty_seen: dict[str, list[str]] = {}
            for s in slots:
                fac = s.cell_display_line2 or "Unknown"
                subj = s.cell_display_line1 or subject_query
                if fac not in faculty_seen:
                    faculty_seen[fac] = []
                if subj not in faculty_seen[fac]:
                    faculty_seen[fac].append(subj)
            lines = [f"👨‍🏫 **Faculty for '{subject_query}':**\n"]
            for f, subjects in faculty_seen.items():
                lines.append(f"  • **{f}** — teaches: {', '.join(subjects)}")
            return "\n".join(lines)
        return f"👨‍🏫 No faculty found for subject matching **'{subject_query}'**."

    # ── "conflicts" ───────────────────────────────────────────────────────────
    if "conflict" in q and timetable_id:
        from schedulo.models import ConflictLog
        stmt = select(ConflictLog).where(ConflictLog.timetable_id == timetable_id).limit(20)
        result = await db.execute(stmt)
        conflicts = result.scalars().all()
        if not conflicts:
            return "✅ **No conflicts** detected in this timetable. All room and faculty bookings are clean!"
        lines = [f"⚠️ **{len(conflicts)} conflict(s)** found:\n"]
        for c in conflicts[:10]:
            sev = c.severity or "UNKNOWN"
            lines.append(f"  • [{sev}] {c.conflict_type}: {c.description}")
        return "\n".join(lines)

    # ── Stats / overview ──────────────────────────────────────────────────────
    if any(k in q for k in ("overview", "summary", "stats", "quality", "score", "how many")):
        if timetable_id:
            result = await db.execute(
                select(func.count(TimetableSlot.id)).where(TimetableSlot.timetable_id == timetable_id)
            )
            total = result.scalar() or 0
            dist_result = await db.execute(
                select(TimetableSlot.slot_type, func.count(TimetableSlot.id))
                .where(TimetableSlot.timetable_id == timetable_id)
                .group_by(TimetableSlot.slot_type)
            )
            dist = {row[0]: row[1] for row in dist_result.all()}
            lines = [f"📊 **Timetable #{timetable_id} Summary**\n",
                     f"  Total slots: **{total}**"]
            for st, cnt in dist.items():
                lines.append(f"  • {st}: {cnt}")
            return "\n".join(lines)

    # ── Sections list ─────────────────────────────────────────────────────────
    if any(k in q for k in ("section", "cse", "sections")):
        if timetable_id:
            from sqlalchemy import distinct
            result = await db.execute(
                select(distinct(TimetableSlot.section_id))
                .where(TimetableSlot.timetable_id == timetable_id)
            )
            sec_ids = [r[0] for r in result.all() if r[0] is not None]
            if sec_ids:
                sec_results = []
                for sid in sec_ids[:15]:
                    sr = await db.execute(select(Section).where(Section.id == sid))
                    sec = sr.scalar_one_or_none()
                    sec_results.append(sec.section_id if sec else f"Section {sid}")
                return f"📋 **Sections in Timetable #{timetable_id}:**\n" + "\n".join(f"  • {s}" for s in sec_results)

    # ── Generic capability description ───────────────────────────────────────
    return (
        "🤖 I'm **ScheduloBot**, your AI scheduling assistant!\n\n"
        "I can answer questions like:\n"
        "  • *Show me all CSE sections for Monday*\n"
        "  • *Who teaches Computer Networks?*\n"
        "  • *Are there any conflicts on Tuesday?*\n"
        "  • *What is the summary of this timetable?*\n\n"
        "Make sure a **timetable is selected** in the dropdown above, then ask me anything!"
    )


# ── System prompt builder ─────────────────────────────────────────────────────

def _build_system_prompt(timetable_id: int | None, faculty_name: str, current_date: str) -> str:
    return f"""You are ScheduloBot, an expert AI assistant for the Schedulo university timetable system.
You help users understand, query, and manage timetables.

Today is {current_date}. The active timetable ID is {timetable_id or 'not selected'}.
Requesting user: {faculty_name}.

CAPABILITIES:
- Answer questions about timetable slots, faculty, rooms, and sections
- Explain schedule structures and conflicts
- Compare sections and find patterns
- Provide scheduling recommendations

RESPONSE STYLE:
- Be concise and use markdown formatting (bold, bullet points, tables)
- Format timetable data as clean structured lists
- Respond in English and be helpful and friendly
- If asked about data you cannot access, be honest and suggest alternatives

IMPORTANT: You have access to real timetable database data. Answer factually and helpfully."""


# ── Main /chat endpoint ───────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Main chat endpoint used by the ScheduloBot frontend.
    Tries AI tiers in order: Groq → HuggingFace → smart DB fallback.
    Always returns a helpful response.
    """
    from schedulo.models import ChatbotConversation, Faculty
    from sqlalchemy import select

    session_id = req.session_id or str(uuid.uuid4())

    # ── Load / create conversation record ─────────────────────────────────────
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

    history: list[dict] = json.loads(conv.messages or "[]")

    # ── Build context ─────────────────────────────────────────────────────────
    faculty_name = "User"
    if req.faculty_id:
        fac_result = await db.execute(select(Faculty).where(Faculty.id == req.faculty_id))
        fac = fac_result.scalar_one_or_none()
        if fac:
            faculty_name = fac.name

    system_prompt = _build_system_prompt(
        timetable_id=req.timetable_id,
        faculty_name=faculty_name,
        current_date=datetime.now().strftime("%Y-%m-%d"),
    )

    # ── Try AI tiers ──────────────────────────────────────────────────────────
    response_text = ""
    source = "fallback"

    # Tier 1: Groq (preferred — fast, free)
    if _is_groq_key_valid(req.groq_api_key):
        try:
            response_text = _call_groq(system_prompt, history, req.message, req.groq_api_key)
            source = "ai:groq"
        except Exception:
            pass

    # Tier 2: HuggingFace
    if not response_text and _is_hf_token_valid(req.hf_api_token):
        try:
            response_text = _call_hf(system_prompt, history, req.message, req.hf_api_token)
            source = "ai:hf"
        except Exception:
            pass

    # Tier 3: Smart DB fallback (always works — queries real data)
    if not response_text:
        response_text = await _db_smart_response(req.message, req.timetable_id, db)
        source = "db"

    # ── Persist conversation ───────────────────────────────────────────────────
    history.append({"role": "user", "content": req.message, "timestamp": datetime.now().isoformat()})
    history.append({"role": "assistant", "content": response_text, "timestamp": datetime.now().isoformat()})
    conv.messages = json.dumps(history[-60:])
    await db.commit()

    return ChatResponse(session_id=session_id, response=response_text, source=source)


# ── Streaming SSE /stream endpoint (advanced) ─────────────────────────────────

@router.post("/stream")
async def chatbot_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """SSE streaming endpoint — streams tokens as they arrive from the LLM."""
    from schedulo.models import ChatbotConversation
    from sqlalchemy import select

    session_id = req.session_id or str(uuid.uuid4())
    result = await db.execute(
        select(ChatbotConversation).where(ChatbotConversation.session_id == session_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        conv = ChatbotConversation(
            session_id=session_id,
            timetable_id=req.timetable_id,
            messages=json.dumps([]),
        )
        db.add(conv)
        await db.flush()

    history: list[dict] = json.loads(conv.messages or "[]")
    system_prompt = _build_system_prompt(req.timetable_id, "User", datetime.now().strftime("%Y-%m-%d"))

    async def event_stream():
        full_response = ""
        source = "fallback"

        if _is_groq_key_valid():
            try:
                text = _call_groq(system_prompt, history, req.message)
                source = "ai:groq"
                # Simulate streaming by yielding words
                for word in text.split():
                    full_response += word + " "
                    yield f"data: {json.dumps({'type': 'token', 'content': word + ' '})}\n\n"
                    await asyncio.sleep(0.03)
            except Exception:
                full_response = ""

        if not full_response and _is_hf_token_valid():
            try:
                from schedulo.chatbot_service.llm_client import ScheduloBotLLMClient
                client = ScheduloBotLLMClient()
                prompt = client.format_prompt(system_prompt, history, req.message)
                source = "ai:hf"
                for token in client.stream_response(prompt):
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                    await asyncio.sleep(0)
            except Exception:
                full_response = ""

        if not full_response:
            full_response = await _db_smart_response(req.message, req.timetable_id, db)
            source = "db"
            for word in full_response.split():
                yield f"data: {json.dumps({'type': 'token', 'content': word + ' '})}\n\n"
                await asyncio.sleep(0.02)

        # Persist
        history.append({"role": "user", "content": req.message, "timestamp": datetime.now().isoformat()})
        history.append({"role": "assistant", "content": full_response, "timestamp": datetime.now().isoformat()})
        conv.messages = json.dumps(history[-60:])
        await db.commit()

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'source': source})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Access-Control-Allow-Origin": "*"},
    )


# ── History endpoints ─────────────────────────────────────────────────────────

@router.get("/history/{session_id}")
async def get_history(session_id: str, db: AsyncSession = Depends(get_db)):
    from schedulo.models import ChatbotConversation
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
    from schedulo.models import ChatbotConversation
    from sqlalchemy import select
    result = await db.execute(
        select(ChatbotConversation).where(ChatbotConversation.session_id == session_id)
    )
    conv = result.scalar_one_or_none()
    if conv:
        conv.messages = json.dumps([])
        await db.commit()
    return {"message": "History cleared"}
