"""
schedulo/tasks.py
Celery task definitions for async background jobs.

In local SQLite mode (CELERY_TASK_ALWAYS_EAGER=true in .env),
tasks run synchronously in the same process — no Celery worker needed.
"""
from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# Lazy import so the module loads cleanly even without celery installed
try:
    from celery import Celery
    from schedulo.config import get_settings

    settings = get_settings()

    app = Celery(
        "schedulo",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_always_eager=settings.celery_task_always_eager,
        task_eager_propagates=True,
    )

    @app.task(name="schedulo.tasks.generate_timetable_async")
    def generate_timetable_async(
        department: str,
        semester: str | None = None,
        algorithm: str = "prototype",
        random_seed: int | None = None,
    ) -> dict:
        """Background task: generate a timetable and return its ID."""
        try:
            import asyncio
            from schedulo.scheduler_core.prototype_scheduler import PrototypeScheduler

            scheduler = PrototypeScheduler(random_seed=random_seed)
            timetables = scheduler.build_all(department)
            _log.info(
                "Async generation complete",
                department=department,
                sections=len(timetables),
            )
            return {"status": "completed", "section_count": len(timetables)}
        except Exception as exc:
            _log.error("Async generation failed: %s", exc)
            return {"status": "failed", "error": str(exc)}

except ImportError:
    # Celery not installed — provide stub so imports don't break
    _log.warning("Celery not installed — async task queue disabled (OK for local SQLite mode)")
    app = None  # type: ignore[assignment]
