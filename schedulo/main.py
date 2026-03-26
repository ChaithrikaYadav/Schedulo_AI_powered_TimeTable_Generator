"""
main.py — FastAPI application entry point for Schedulo.
Registers all routers, CORS middleware, and startup/shutdown lifecycle events.
"""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from starlette.exceptions import HTTPException as StarletteHTTPException

from schedulo.config import get_settings
from schedulo.database import create_all_tables

settings = get_settings()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: setup on startup, cleanup on shutdown."""
    logger.info("Schedulo starting", environment=settings.environment)

    # Ensure output/model/log directories exist
    for d in [settings.output_dir, settings.models_dir, settings.logs_dir]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Create DB tables (SQLite prototype auto-migration)
    if settings.db_engine == "sqlite":
        await create_all_tables()
        logger.info("SQLite tables created/verified")

    yield

    logger.info("Schedulo shutting down")


app = FastAPI(
    title="Schedulo — University Timetable Generator",
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
        "message": "Welcome to Schedulo API",
        "docs": "/docs",
        "version": settings.app_version,
    }


# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Return a consistent JSON envelope for all HTTP errors (404, 403, etc.)."""
    messages = {
        404: "The requested resource was not found.",
        403: "You don't have permission to access this resource.",
        401: "Authentication is required.",
        405: "HTTP method not allowed for this endpoint.",
    }
    user_message = messages.get(exc.status_code, str(exc.detail))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": f"HTTP {exc.status_code}",
            "message": user_message,
            "detail": exc.detail,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return friendly validation errors so the frontend can guide the user."""
    errors = []
    for e in exc.errors():
        loc = " → ".join(str(x) for x in e.get("loc", []))
        errors.append(f"{loc}: {e.get('msg', 'Invalid value')}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "message": "One or more fields have invalid values. Please check your input.",
            "errors": errors,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unexpected server errors — log them and return a friendly message."""
    logger.error(
        "Unhandled exception",
        path=str(request.url.path),
        method=request.method,
        error=str(exc),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": (
                "Something went wrong on our end. "
                "Please try again or contact support if the issue persists."
            ),
        },
    )


# ── Import and register routers ───────────────────────────────────
try:
    from schedulo.api_gateway.routes.timetable import router as timetable_router
    from schedulo.api_gateway.routes.faculty import router as faculty_router
    from schedulo.api_gateway.routes.chatbot import router as chatbot_router
    from schedulo.api_gateway.routes.placeholder_routes import (
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
