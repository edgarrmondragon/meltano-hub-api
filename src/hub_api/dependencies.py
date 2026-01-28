"""Generic FastAPI dependencies for the Meltano hub API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import fastapi

from hub_api import client, database

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


async def get_hub(request: fastapi.Request) -> AsyncGenerator[client.MeltanoHub]:
    """Get a Meltano hub instance."""
    db = await database.open_db()
    try:
        yield client.MeltanoHub(db=db, base_url=str(request.base_url))
    finally:
        await db.close()


Hub = Annotated[client.MeltanoHub, fastapi.Depends(get_hub)]
