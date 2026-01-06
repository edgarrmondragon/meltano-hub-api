"""Maintainer endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, ClassVar

from litestar import Controller, get
from litestar.di import Provide
from litestar.openapi.spec.example import Example
from litestar.params import Parameter

from hub_api import client  # noqa: TC001
from hub_api.schemas import api as api_schemas  # noqa: TC001

from .dependencies import get_hub

if TYPE_CHECKING:
    from litestar.types.composite_types import Dependencies


class MaintainersController(Controller):
    path = "/meltano/api/v1/maintainers"

    dependencies: ClassVar[Dependencies] = {  # type: ignore[misc]
        "hub": Provide(get_hub),
    }

    @get("/", summary="Get maintainers list")
    async def get_maintainers(self, hub: client.MeltanoHub) -> api_schemas.MaintainersList:  # noqa: PLR6301
        """Retrieve global index of plugins."""
        return await hub.get_maintainers()

    @get("/top", summary="Get top plugin maintainers")
    async def get_top_maintainers(  # noqa: PLR6301
        self,
        hub: client.MeltanoHub,
        count: Annotated[
            int,
            Parameter(
                ...,
                ge=1,
                lt=50,
                description="The number of maintainers to return",
            ),
        ] = 10,
    ) -> list[api_schemas.MaintainerPluginCount]:
        """Retrieve top maintainers."""
        return await hub.get_top_maintainers(count)

    @get("/{maintainer:str}", summary="Get maintainer details")
    async def get_maintainer(  # noqa: PLR6301
        self,
        hub: client.MeltanoHub,
        maintainer: Annotated[
            str,
            Parameter(
                ...,
                description="The maintainer identifier",
                pattern=r"^[A-Za-z0-9-_]+$",
                examples=[
                    Example(value="meltanolabs"),
                    Example(value="singer-io"),
                ],
            ),
        ],
    ) -> api_schemas.MaintainerDetails:
        """Retrieve maintainer details."""
        return await hub.get_maintainer(maintainer)
