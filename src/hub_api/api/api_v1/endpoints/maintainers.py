"""Maintainer endpoints."""

from __future__ import annotations

from typing import Annotated

import fastapi

from hub_api import dependencies  # ruff: ignore[typing-only-first-party-import]
from hub_api.schemas import api as api_schemas  # ruff: ignore[typing-only-first-party-import]

router = fastapi.APIRouter()


@router.get(
    "",
    summary="Get maintainers list",
    response_model_exclude_none=True,
    operation_id="get_all_maintainers",
)
async def get_maintainers(hub: dependencies.Hub) -> api_schemas.MaintainersList:
    """Retrieve global index of plugins."""
    return await hub.get_maintainers()


@router.get(
    "/top",
    summary="Get top plugin maintainers",
    response_model_exclude_none=True,
    operation_id="get_top_maintainers",
)
async def get_top_maintainers(
    hub: dependencies.Hub,
    count: Annotated[
        int,
        fastapi.Query(
            ...,
            ge=1,
            lt=50,
            description="The number of maintainers to return",
        ),
    ],
) -> list[api_schemas.MaintainerPluginCount]:
    """Retrieve top maintainers."""
    return await hub.get_top_maintainers(count)


@router.get(
    "/{maintainer}",
    summary="Get maintainer details",
    response_model_exclude_none=True,
    responses={
        404: {"description": "Maintainer not found"},
    },
    operation_id="get_maintainer",
)
async def get_maintainer(
    hub: dependencies.Hub,
    maintainer: Annotated[
        str,
        fastapi.Path(
            ...,
            description="The maintainer identifier",
            pattern=r"^[A-Za-z0-9-_]+$",
            examples=[
                "meltanolabs",
                "singer-io",
            ],
        ),
    ],
) -> api_schemas.MaintainerDetails:
    """Retrieve maintainer details."""
    return await hub.get_maintainer(maintainer)
