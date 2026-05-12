"""Alembic migration environment — async SQLite via aiosqlite."""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migrations are written by hand; autogenerate is not used.
target_metadata = None

_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./norag.db")
# Normalise libsql/raw sqlite: URLs to the aiosqlite driver format.
if _DATABASE_URL.startswith("file:"):
    _db_path = _DATABASE_URL[len("file:"):]
    _DATABASE_URL = f"sqlite+aiosqlite:///{_db_path}"
elif not _DATABASE_URL.startswith("sqlite+aiosqlite"):
    _DATABASE_URL = "sqlite+aiosqlite:///./norag.db"


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _DATABASE_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


run_migrations_online()
