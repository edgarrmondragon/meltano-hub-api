from __future__ import annotations

lazy import importlib.resources
lazy import os
lazy import pathlib

lazy import aiosqlite

_DEFAULT_DB_PATH = "./plugins.db"


def get_db_schema() -> str:
    """Get database schema."""
    return importlib.resources.files("hub_api").joinpath("schema.sql").read_text()


def get_db_path() -> pathlib.Path:
    """Get database path."""
    return pathlib.Path(os.getenv("DB_PATH", _DEFAULT_DB_PATH)).resolve()


async def open_db() -> aiosqlite.Connection:
    """Open database connection."""
    conn = await aiosqlite.connect(
        f"file:{get_db_path()}?mode=ro&immutable=1&cache=shared",
        uri=True,
    )
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA query_only=ON;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    return conn
