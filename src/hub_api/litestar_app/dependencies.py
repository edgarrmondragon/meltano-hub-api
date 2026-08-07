"""Litestar app dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hub_api import client, database

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from litestar.connection import Request


async def get_hub(request: Request) -> AsyncGenerator[client.MeltanoHub]:  # type: ignore[type-arg]
    """Get a Meltano hub instance."""
    db = await database.open_db()
    try:
        yield client.MeltanoHub(db=db, base_url=str(request.base_url))
    finally:
        await db.close()
