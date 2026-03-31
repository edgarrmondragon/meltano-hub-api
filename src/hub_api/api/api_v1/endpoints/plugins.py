"""Plugin endpoints."""

from __future__ import annotations

from typing import Annotated

import fastapi
import fastapi.responses
from pydantic import BaseModel, ConfigDict, Field

from hub_api import dependencies, enums, ids
from hub_api.helpers import compatibility
from hub_api.schemas import api as api_schemas

router = fastapi.APIRouter()


PluginTypeParam = Annotated[
    str,
    # enums.PluginTypeEnum,  # TODO: Schemathesis doesn't like constraints on path parameters
    fastapi.Path(
        ...,
        description="The plugin type",
        examples=[
            enums.PluginTypeEnum.extractors,
        ],
    ),
]

PluginNameParam = Annotated[
    str,
    fastapi.Path(
        ...,
        description="The plugin name",
        # pattern=r"^[A-Za-z0-9-]+$",  # TODO: Schemathesis doesn't like constraints on path parameters
        examples=[
            "tap-github",
        ],
    ),
]

PluginVariantParam = Annotated[
    str,
    fastapi.Path(
        ...,
        description="The plugin variant",
        # pattern=r"^[A-Za-z0-9-]+$",  # TODO: Schemathesis doesn't like constraints on path parameters
        examples=[
            "meltanolabs",
        ],
    ),
]


MeltanoVersion = Annotated[
    tuple[int, int],
    fastapi.Depends(compatibility.get_version_tuple),
]


@router.get(
    "/index",
    summary="Get plugin index",
    response_model_exclude_none=True,
    operation_id="get_plugin_index",
)
async def get_index(hub: dependencies.Hub) -> api_schemas.PluginIndex:
    """Retrieve global index of plugins."""
    return await hub.get_plugin_index()


@router.get(
    "/{plugin_type}/index",
    summary="Get plugin type index",
    response_model_exclude_none=True,
    responses={
        400: {"description": "Not a valid plugin type"},
    },
    operation_id="get_plugin_type_index",
)
async def get_type_index(hub: dependencies.Hub, plugin_type: PluginTypeParam) -> api_schemas.PluginTypeIndex:
    """Retrieve index of plugins of a given type."""
    return await hub.get_plugin_type_index(plugin_type=plugin_type)


class FindParams(BaseModel):
    name: str = Field(
        description="The plugin name",
        examples=["tap-github"],
    )

    type: enums.PluginTypeEnum = Field(  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
        None,
        description="The plugin type",
        examples=[enums.PluginTypeEnum.extractors],
    )

    variant: str = Field(  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
        None,
        description="The optional variant name",
        examples=["meltanolabs"],
    )


@router.get(
    "/search",
    summary="Find a plugin",
    responses={
        400: {"description": "Not a valid plugin type"},
        404: {"description": "Plugin not found"},
    },
    operation_id="get_plugin",
)
async def find_plugin(
    hub: dependencies.Hub,
    params: Annotated[FindParams, fastapi.Query()],
) -> api_schemas.PluginDetails:
    return await hub.find_plugin(plugin_name=params.name, plugin_type=params.type, variant_name=params.variant)


@router.get(
    "/{plugin_type}/{plugin_name}/default",
    summary="Get the default plugin variant",
    responses={
        400: {"description": "Not a valid plugin type"},
        404: {"description": "Plugin not found"},
    },
    operation_id="get_default_plugin",
)
async def get_default_plugin(
    hub: dependencies.Hub,
    plugin_type: PluginTypeParam,
    plugin_name: PluginNameParam,
) -> fastapi.responses.RedirectResponse:
    """Retrieve details of the default plugin variant."""
    plugin_id = ids.PluginID.from_params(plugin_type=plugin_type, plugin_name=plugin_name)
    return fastapi.responses.RedirectResponse(url=await hub.get_default_variant_url(plugin_id))


@router.get(
    "/{plugin_type}/{plugin_name}--{plugin_variant}",
    response_model_exclude_none=True,
    summary="Get plugin variant",
    responses={
        400: {"description": "Not a valid plugin type"},
        404: {"description": "Plugin variant not found"},
    },
    operation_id="get_plugin_variant",
)
async def get_plugin_variant(
    hub: dependencies.Hub,
    plugin_type: PluginTypeParam,
    plugin_name: PluginNameParam,
    plugin_variant: PluginVariantParam,
    meltano_version: MeltanoVersion,
) -> api_schemas.PluginDetails:
    """Retrieve details of a specific plugin variant."""
    variant_id = ids.VariantID.from_params(
        plugin_type=plugin_type,
        plugin_name=plugin_name,
        plugin_variant=plugin_variant,
    )
    return await hub.get_plugin_details(variant_id, meltano_version=meltano_version)


class MadeWithSDKParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(
        25,
        ge=1,
        le=100,
        description="The number of plugins to return",
        examples=[
            10,
            25,
            100,
        ],
    )
    plugin_type: api_schemas.PluginTypeOrAnyEnum = Field(
        api_schemas.PluginTypeOrAnyEnum.any,
        description="The plugin type",
        examples=[
            api_schemas.PluginTypeOrAnyEnum.any,
            api_schemas.PluginTypeOrAnyEnum.extractors,
            api_schemas.PluginTypeOrAnyEnum.loaders,
        ],
    )


@router.get("/made-with-sdk", summary="Get SDK plugins", operation_id="get_sdk_plugins")
async def sdk(
    hub: dependencies.Hub,
    *,
    filter_query: Annotated[MadeWithSDKParams, fastapi.Query()],
) -> list[api_schemas.PluginListElement]:
    """Retrieve plugins made with the Singer SDK."""
    return await hub.get_sdk_plugins(limit=filter_query.limit, plugin_type=filter_query.plugin_type)


@router.get("/stats", summary="Hub statistics", operation_id="get_plugin_stats")
async def stats(hub: dependencies.Hub) -> dict[enums.PluginTypeEnum, int]:
    """Retrieve Hub plugin statistics."""
    return await hub.get_plugin_stats()


__all__ = ["router"]
