"""alembic/env.py — Async SQLAlchemy support for Schedulo migrations."""
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from environment variable if present
database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./schedulo.db")

# Alembic needs the sync driver for migrations — swap async prefix
sync_url = (
    database_url
    .replace("postgresql+asyncpg://", "postgresql://")
    .replace("sqlite+aiosqlite://", "sqlite://")
)
config.set_main_option("sqlalchemy.url", sync_url)

# Import metadata from models
try:
    from schedulo.models import Base
    target_metadata = Base.metadata
except ImportError:
    target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine
    connectable = create_async_engine(
        database_url,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
