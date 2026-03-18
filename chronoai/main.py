"""
main.py — FastAPI application entry point for ChronoAI.
Registers all routers, CORS middleware, and startup/shutdown lifecycle events.
"""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from chronoai.config import get_settings
from chronoai.database import create_all_tables

settings = get_settings()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: setup on startup, cleanup on shutdown."""
    logger.info("ChronoAI starting", environment=settings.environment)

    # Ensure output/model/log directories exist
    for d in [settings.output_dir, settings.models_dir, settings.logs_dir]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Create DB tables (SQLite prototype auto-migration)
    if settings.db_engine == "sqlite":
        await create_all_tables()
        logger.info("SQLite tables created/verified")

    yield

    logger.info("ChronoAI shutting down")


app = FastAPI(
    title="ChronoAI — University Timetable Generator",
    description=(
        "AI-powered timetable generation system using CSP, Genetic Algorithms, "
        "Reinforcement Learning, and LLM-assisted conflict resolution."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static file serving (for generated timetable downloads) ───────
outputs_dir = Path(settings.output_dir)
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

# ── Health check endpoint ─────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe — returns 200 if the server is running."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "version": settings.app_version,
    }


# ── Root redirect ─────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root():
    """API root — points to OpenAPI docs."""
    return {
        "message": "Welcome to ChronoAI API",
        "docs": "/docs",
        "version": settings.app_version,
    }


# ── Import and register routers ───────────────────────────────────
try:
    from chronoai.api_gateway.routes.timetable import router as timetable_router
    from chronoai.api_gateway.routes.faculty import router as faculty_router
    from chronoai.api_gateway.routes.chatbot import router as chatbot_router
    from chronoai.api_gateway.routes.stubs import (
        router_rooms as rooms_router,
        router_sections as sections_router,
        router_subjects as subjects_router,
        router_conflicts as conflicts_router,
        router_export as export_router,
        router_analytics as analytics_router,
        router_auth as auth_router,
    )

    app.include_router(auth_router,       prefix="/api/auth",       tags=["Auth"])
    app.include_router(faculty_router,    prefix="/api/faculty",    tags=["Faculty"])
    app.include_router(subjects_router,   prefix="/api/subjects",   tags=["Subjects"])
    app.include_router(rooms_router,      prefix="/api/rooms",      tags=["Rooms"])
    app.include_router(sections_router,   prefix="/api/sections",   tags=["Sections"])
    app.include_router(timetable_router,  prefix="/api/timetables", tags=["Timetables"])
    app.include_router(conflicts_router,  prefix="/api/conflicts",  tags=["Conflicts"])
    app.include_router(export_router,     prefix="/api/export",     tags=["Export"])
    app.include_router(chatbot_router,    prefix="/api/chatbot",    tags=["Chatbot"])
    app.include_router(analytics_router,  prefix="/api/analytics",  tags=["Analytics"])
    logger.info("All API routers registered")
except ImportError as e:
    logger.warning("Some routers not yet available", error=str(e))
    pass
