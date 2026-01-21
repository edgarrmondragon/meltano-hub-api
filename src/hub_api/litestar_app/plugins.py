"""Plugin endpoints."""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING, Annotated, ClassVar

import packaging.version
from litestar import Controller, Request, get
from litestar.di import Provide
from litestar.openapi.datastructures import ResponseSpec
from litestar.openapi.spec.example import Example
from litestar.params import Parameter
from litestar.response import Redirect

from hub_api import client, enums, ids
from hub_api.helpers import compatibility
from hub_api.schemas import api as api_schemas

from .dependencies import get_hub

if TYPE_CHECKING:
    from litestar.types.composite_types import Dependencies


BASE_API_URL = "http://127.0.0.1:8000"
PLUGIN_VARIANT_PATTERN = re.compile(r"^(?P<plugin_name>[A-Za-z0-9-]+)--(?P<variant>[A-Za-z0-9-]+)$")

EXAMPLE_PLUGIN_TYPE_INDEX = {
    "tap-github": {
        "default_variant": "singer-io",
        "variants": {
            "singer-io": {
                "ref": "https://hub.meltano.com/meltano/api/v1/plugins/extractors/tap-github--singer-io",
            },
        },
        "logo_url": "https://hub.meltano.com/assets/logos/extractors/github.png",
    },
}
EXAMPLE_PLUGIN_INDEX = {
    "extractors": EXAMPLE_PLUGIN_TYPE_INDEX,
}


def get_version_tuple(request: Request) -> compatibility.VersionTuple:  # type: ignore[type-arg]
    """Extract the Meltano version from the User-Agent header."""
    if (ua := request.headers.get("User-Agent")) and (match := compatibility.USER_AGENT_PATTERN.match(ua)):
        with contextlib.suppress(packaging.version.InvalidVersion):
            version = packaging.version.Version(match.group("version"))
            return (version.major, version.minor)

    return compatibility.LATEST


PluginTypeParam = Annotated[
    # str,
    enums.PluginTypeEnum,  # TODO: Schemathesis doesn't like constraints on path parameters
    Parameter(
        ...,
        description="The plugin type",
    ),
]


PluginNameParam = Annotated[
    str,
    Parameter(
        ...,
        description="The plugin name",
        # pattern=r"^[A-Za-z0-9-]+$",  # TODO: Schemathesis doesn't like constraints on path parameters
        examples=[
            Example(value="tap-github"),
            Example(value="tap-hubspot"),
        ],
    ),
]


PluginVariantParam = Annotated[
    str,
    Parameter(
        ...,
        description="The plugin variant",
        # pattern=r"^[A-Za-z0-9-]+$",  # TODO: Schemathesis doesn't like constraints on path parameters
        examples=[
            Example(value="meltanolabs"),
            Example(value="singer-io"),
        ],
    ),
]


class PluginsController(Controller):
    path = "/meltano/api/v1/plugins"

    dependencies: ClassVar[Dependencies] = {  # type: ignore[misc]
        "hub": Provide(get_hub),
    }

    @get(
        "/index",
        summary="Get plugin index",
        responses={
            200: ResponseSpec(
                data_container=api_schemas.PluginIndex,
                generate_examples=False,
                examples=[Example(value=EXAMPLE_PLUGIN_INDEX)],
            ),
        },
    )
    async def get_index(self, hub: client.MeltanoHub) -> api_schemas.PluginIndex:  # noqa: PLR6301
        """Retrieve global index of plugins."""
        return await hub.get_plugin_index()

    @get(
        "/{plugin_type:str}/index",
        summary="Get plugin type index",
        responses={
            200: ResponseSpec(
                data_container=api_schemas.PluginTypeIndex,
                generate_examples=False,
                examples=[Example(value=EXAMPLE_PLUGIN_TYPE_INDEX)],
            ),
        },
    )
    async def get_type_index(  # noqa: PLR6301
        self,
        hub: client.MeltanoHub,
        plugin_type: PluginTypeParam,
    ) -> api_schemas.PluginTypeIndex:
        """Retrieve index of plugins of a given type."""
        return await hub.get_plugin_type_index(plugin_type=plugin_type)

    @get(
        "/{plugin_type:str}/{plugin_name:str}",
        # status_code=http.HTTPStatus.FOUND,
        summary="Get available plugin variants",
    )
    async def get_variants(
        self,
        hub: client.MeltanoHub,
        plugin_type: PluginTypeParam,
        plugin_name: PluginNameParam,
    ) -> api_schemas.PluginRef:
        """Retrieve details of the default plugin variant."""
        if match := PLUGIN_VARIANT_PATTERN.match(plugin_name):
            plugin_name = match.group("plugin_name")
            variant = match.group("variant")
            return Redirect(path=f"{self.path}/{plugin_type.value}/{plugin_name}/{variant}")  # type: ignore[return-value]

        plugin_id = ids.PluginID.from_params(plugin_type=plugin_type, plugin_name=plugin_name)
        # return Redirect(path=await hub.get_default_variant_url(plugin_id))  # type: ignore[return-value]
        return await hub.get_plugin_variants(plugin_id=plugin_id)

    @get(
        "/{plugin_type:str}/{plugin_name:str}/{variant:str}",
        summary="Get plugin variant details",
        dependencies={
            "meltano_version": Provide(get_version_tuple, sync_to_thread=False),
        },
        responses={
            404: ResponseSpec(
                data_container=None,
                description="Plugin variant not found",
            ),
        },
    )
    async def get_variant_details(  # noqa: PLR6301
        self,
        hub: client.MeltanoHub,
        plugin_type: PluginTypeParam,
        plugin_name: PluginNameParam,
        variant: PluginVariantParam,
        meltano_version: compatibility.VersionTuple,
    ) -> (
        api_schemas.ExtractorResponse
        | api_schemas.LoaderResponse
        | api_schemas.UtilityResponse
        | api_schemas.OrchestratorResponse
        | api_schemas.TransformResponse
        | api_schemas.TransformerResponse
        | api_schemas.MapperResponse
        | api_schemas.FileResponse
    ):
        """Retrieve details of a plugin variant."""
        if variant == "default":
            plugin_id = ids.PluginID.from_params(plugin_type=plugin_type, plugin_name=plugin_name)
            return Redirect(  # type: ignore[return-value]
                path=await hub.get_default_variant_url(plugin_id),
                status_code=302,
            )

        variant_id = ids.VariantID.from_params(
            plugin_type=plugin_type,
            plugin_name=plugin_name,
            plugin_variant=variant,
        )
        return await hub.get_plugin_details(variant_id, meltano_version=meltano_version)

    @get("/made-with-sdk", summary="Get SDK plugins")
    async def sdk(  # noqa: PLR6301
        self,
        hub: client.MeltanoHub,
        *,
        limit: int = 25,
        plugin_type: api_schemas.PluginTypeOrAnyEnum = api_schemas.PluginTypeOrAnyEnum.any,
    ) -> list[api_schemas.PluginListElement]:
        """Retrieve plugins made with the Singer SDK."""
        return await hub.get_sdk_plugins(limit=limit, plugin_type=plugin_type)

    @get("/stats", summary="Hub statistics")
    async def stats(self, hub: client.MeltanoHub) -> dict[enums.PluginTypeEnum, int]:  # noqa: PLR6301
        """Retrieve Hub plugin statistics."""
        return await hub.get_plugin_stats()
