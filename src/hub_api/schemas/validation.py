"""Pydantic models used to validate input data."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, HttpUrl, StringConstraints

from hub_api import enums  # ruff: ignore[typing-only-first-party-import]
from hub_api.schemas import meltano


class HubPluginMetadata(BaseModel):
    definition: str | None = Field(
        None,
        description="A brief description of the plugin.",
    )
    domain_url: HttpUrl | None = Field(
        None,
        description="Links to the website representing the database, api, etc.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="A list of keywords for the plugin",
    )
    maintenance_status: enums.MaintenanceStatusEnum | None = Field(
        None,
        description="The maintenance status of the plugin",
    )
    next_steps: str | None = Field(
        None,
        description=(
            "A markdown string that gets added after the auto generated installation "
            "section. Commonly used for next steps following "
            "installation/configuration i.e. how to turn on a service or init a system "
            "database."
        ),
    )
    prereq: str | None = Field(
        None,
        description=(
            "A markdown string that included at the end of the auto generated "
            "`Prerequisites` section on the plugin page. Can be used to include custom "
            "prerequisites other than the default set."
        ),
    )
    quality: enums.QualityEnum | None = Field(
        None,
        description="The quality of the plugin",
    )
    settings_preamble: str | None = Field(
        None,
        description=(
            "A markdown string that gets added to the beginning of the setting section "
            "on the plugin pages. Commonly used for adding notes on advanced settings."
        ),
    )
    usage: str | None = Field(
        None,
        description=(
            "A markdown string that gets appended to the bottom of the plugin pages. "
            "Commonly used for troubleshooting notes or additional setup instructions."
        ),
    )


class HubPluginDefinition(meltano.Plugin, HubPluginMetadata):
    logo_url: Annotated[str | None, StringConstraints(pattern=r"^(\/[^\/]+)+$")] = None


class ExtractorDefinition(HubPluginDefinition, meltano.Extractor):
    pass


class LoaderDefinition(HubPluginDefinition, meltano.Loader):
    pass


class UtilityDefinition(HubPluginDefinition, meltano.Utility):
    pass


class OrchestratorDefinition(HubPluginDefinition, meltano.Orchestrator):
    pass


class TransformDefinition(HubPluginDefinition, meltano.Transform):
    pass


class TransformerDefinition(HubPluginDefinition, meltano.Transformer):
    pass


class MapperDefinition(HubPluginDefinition, meltano.Mapper):
    pass


class FileDefinition(HubPluginDefinition, meltano.File):
    pass


type PluginDefinition = (
    ExtractorDefinition
    | LoaderDefinition
    | UtilityDefinition
    | OrchestratorDefinition
    | TransformDefinition
    | TransformerDefinition
    | MapperDefinition
    | FileDefinition
)
