"""
database.py — Async SQLAlchemy engine + session factory.
Supports both SQLite (local prototype) and PostgreSQL (server/cloud) via config.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from schedulo.config import get_settings

settings = get_settings()

# Create engine — engine choice driven by DATABASE_URL prefix
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables() -> None:
    """Create all tables (used for SQLite prototype mode only). For PostgreSQL use Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
