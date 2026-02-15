from __future__ import annotations

import collections
import json
import urllib.parse
from typing import TYPE_CHECKING, Any, assert_never

import pydantic

from hub_api import enums, exceptions, ids
from hub_api.helpers import compatibility
from hub_api.schemas import api as api_schemas
from hub_api.schemas import meltano

if TYPE_CHECKING:
    import aiosqlite

BASE_HUB_URL = "https://hub.meltano.com"


async def fetch_one_dict(db: aiosqlite.Connection, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch one row as a dictionary."""
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


async def fetch_all_dicts(db: aiosqlite.Connection, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch all rows as dictionaries."""
    cur = await db.execute(sql, params)
    rows = await cur.fetchall()
    await cur.close()
    return [dict(r) for r in rows]


def json_load_maybe(v: Any) -> Any:  # noqa: ANN401
    """Load JSON if value is a string, otherwise return as-is."""
    return json.loads(v) if isinstance(v, str) else v


class PluginNotFoundError(exceptions.NotFoundError):
    """Plugin not found error."""

    def __init__(
        self,
        *,
        plugin_name: str,
        plugin_type: enums.PluginTypeEnum | None = None,
        variant_name: str | None = None,
    ) -> None:
        if variant_name is not None and plugin_type is not None:
            msg = f"Variant '{variant_name}' of '{plugin_name}' was not found in {plugin_type}"
        elif variant_name is not None:
            msg = f"Variant '{variant_name}' of '{plugin_name}' was not found"
        elif plugin_type is not None:
            msg = f"Plugin '{plugin_name}' was not found in {plugin_type}"
        else:
            msg = f"Plugin '{plugin_name}' was not found"
        super().__init__(msg)


class PluginAmbiguityError(exceptions.BadParameterError):
    """Plugin ambiguity error."""

    def __init__(self, *, plugins: list[dict[str, Any]]) -> None:
        self.plugins = plugins
        plugin_names = [f"{p['name']} ({p['plugin_type']})" for p in plugins]
        super().__init__(f"More than one plugin found for the given criteria: {', '.join(plugin_names)}")


class MaintainerNotFoundError(exceptions.NotFoundError):
    """Maintainer not found error."""

    def __init__(self, *, maintainer_id: str) -> None:
        super().__init__(f"Maintainer '{maintainer_id}' not found")


def _build_variant_path(
    *,
    plugin_type: enums.PluginTypeEnum,
    plugin_name: str,
    plugin_variant: str,
    base_url: str,
) -> str:
    """Build variant URL.

    Args:
        base_url: Base API URL.
        plugin_type: Plugin type.
        plugin_name: Plugin name.
        plugin_variant: Plugin variant.

    Returns:
        Variant URL.
    """
    prefix = f"{base_url}meltano/api/v1/plugins"
    return f"{prefix}/{plugin_type.value}/{plugin_name}--{plugin_variant}"


def build_hub_url(
    *,
    base_url: str,
    plugin_type: enums.PluginTypeEnum,
    plugin_name: str,
    plugin_variant: str,
) -> pydantic.HttpUrl:
    """Build hub URL.

    Args:
        base_url: Base Hub URL.
        plugin_type: Plugin type.
        plugin_name: Plugin name.
        plugin_variant: Plugin variant

    Returns:
        Hub URL for the plugin.
    """
    return pydantic.HttpUrl(f"{base_url}/{plugin_type.value}/{plugin_name}--{plugin_variant}")


def _convert_decimal_to_integer(settings: list[meltano.PluginSetting]) -> list[meltano.PluginSetting]:
    """Convert decimal settings to integer settings."""
    new_settings: list[meltano.PluginSetting] = []
    for setting in settings:
        if isinstance(setting.root, meltano.DecimalSetting):
            dump = setting.root.model_dump()
            dump["kind"] = "integer"
            new_settings.append(meltano.PluginSetting(root=meltano.IntegerSetting.model_validate(dump)))
        else:
            new_settings.append(setting)
    return new_settings


class MeltanoHub:
    def __init__(
        self: MeltanoHub,
        *,
        db: aiosqlite.Connection,
        base_url: str,
        base_hub_url: str = BASE_HUB_URL,
    ) -> None:
        self.db: aiosqlite.Connection = db
        self.base_url = base_url
        self.base_hub_url: str = base_hub_url

    async def _variant_details(  # noqa: PLR0911, PLR0912, PLR0914, PLR0915, C901
        self: MeltanoHub,
        variant_id: str,
    ) -> api_schemas.PluginDetails:
        variant_sql = """
            SELECT pv.*, p.plugin_type, p.name AS plugin_name
            FROM plugin_variants pv
            JOIN plugins p ON p.id = pv.plugin_id
            WHERE pv.id = :variant_id
        """
        variant = await fetch_one_dict(self.db, variant_sql, {"variant_id": variant_id})

        if not variant:
            msg = "Variant not found"
            raise ValueError(msg)

        settings_sql = "SELECT * FROM settings WHERE variant_id = :variant_id"
        settings_rows = await fetch_all_dicts(self.db, settings_sql, {"variant_id": variant_id})

        setting_ids = [s["id"] for s in settings_rows]
        if setting_ids:
            placeholders = ",".join(f":sid{i}" for i in range(len(setting_ids)))
            aliases_sql = f"SELECT setting_id, name FROM setting_aliases WHERE setting_id IN ({placeholders})"  # noqa: S608
            aliases_params = {f"sid{i}": sid for i, sid in enumerate(setting_ids)}
            aliases_rows = await fetch_all_dicts(self.db, aliases_sql, aliases_params)

            aliases_by_setting: dict[str, list[str]] = collections.defaultdict(list)
            for alias in aliases_rows:
                aliases_by_setting[alias["setting_id"]].append(alias["name"])

            for setting in settings_rows:
                setting["value"] = json_load_maybe(setting["value"])
                setting["options"] = json_load_maybe(setting["options"])
                setting["aliases"] = aliases_by_setting.get(setting["id"]) or None
        else:
            aliases_by_setting = {}

        capabilities_sql = "SELECT name FROM capabilities WHERE variant_id = :variant_id"
        capabilities_rows = await fetch_all_dicts(self.db, capabilities_sql, {"variant_id": variant_id})
        capabilities = [row["name"] for row in capabilities_rows]

        commands_sql = "SELECT name, args, description, executable FROM commands WHERE variant_id = :variant_id"
        commands_rows = await fetch_all_dicts(self.db, commands_sql, {"variant_id": variant_id})
        commands = {cmd["name"]: cmd for cmd in commands_rows}

        selects_sql = "SELECT expression FROM selects WHERE variant_id = :variant_id"
        selects_rows = await fetch_all_dicts(self.db, selects_sql, {"variant_id": variant_id})
        select = [s["expression"] for s in selects_rows] if selects_rows else None

        metadata_sql = "SELECT key, value FROM metadata WHERE variant_id = :variant_id"
        metadata_rows = await fetch_all_dicts(self.db, metadata_sql, {"variant_id": variant_id})
        metadata = {m["key"]: json_load_maybe(m["value"]) for m in metadata_rows} if metadata_rows else None

        setting_groups_sql = "SELECT group_id, setting_name FROM setting_groups WHERE variant_id = :variant_id"
        setting_groups = await fetch_all_dicts(self.db, setting_groups_sql, {"variant_id": variant_id})
        settings_groups_dict: dict[int, list[str]] = collections.defaultdict(list)
        for sg in setting_groups:
            settings_groups_dict[sg["group_id"]].append(sg["setting_name"])
        settings_group_validation = list(settings_groups_dict.values())

        plugin_type = enums.PluginTypeEnum(variant["plugin_type"])

        result: dict[str, Any] = {
            "commands": commands,
            "description": variant["description"],
            "executable": variant["executable"],
            "docs": build_hub_url(
                base_url=self.base_hub_url,
                plugin_type=plugin_type,
                plugin_name=variant["plugin_name"],
                plugin_variant=variant["name"],
            ),
            "label": variant["label"],
            "logo_url": urllib.parse.urljoin(self.base_hub_url, variant["logo_url"]) if variant["logo_url"] else None,
            "name": variant["plugin_name"],
            "namespace": variant["namespace"],
            "pip_url": variant["pip_url"],
            "repo": variant["repo"],
            "ext_repo": variant["ext_repo"],
            "settings": [meltano.PluginSetting.model_validate(s) for s in settings_rows],
            "settings_group_validation": settings_group_validation,
            "variant": variant["name"],
            "supported_python_versions": json_load_maybe(variant["supported_python_versions"])
            if variant.get("supported_python_versions")
            else None,
        }

        match plugin_type:
            case enums.PluginTypeEnum.extractors:
                result["capabilities"] = capabilities
                result["select"] = select
                result["metadata"] = metadata
                return api_schemas.ExtractorResponse.model_validate(result)
            case enums.PluginTypeEnum.loaders:
                result["capabilities"] = capabilities
                return api_schemas.LoaderResponse.model_validate(result)
            case enums.PluginTypeEnum.utilities:
                return api_schemas.UtilityResponse.model_validate(result)
            case enums.PluginTypeEnum.orchestrators:
                return api_schemas.OrchestratorResponse.model_validate(result)
            case enums.PluginTypeEnum.transforms:
                return api_schemas.TransformResponse.model_validate(result)
            case enums.PluginTypeEnum.transformers:
                return api_schemas.TransformerResponse.model_validate(result)
            case enums.PluginTypeEnum.mappers:
                return api_schemas.MapperResponse.model_validate(result)
            case enums.PluginTypeEnum.files:
                return api_schemas.FileResponse.model_validate(result)
            case _:  # pragma: no cover
                assert_never(plugin_type)

    async def find_plugin(
        self,
        *,
        plugin_name: str,
        plugin_type: enums.PluginTypeEnum | None = None,
        variant_name: str | None = None,
    ) -> api_schemas.PluginDetails:
        """Find a plugin by name with optional type and variant filters.

        Args:
            plugin_name: Plugin name to search for.
            plugin_type: Optional plugin type filter.
            variant_name: Optional variant name filter. If not provided, uses default variant.

        Returns:
            Plugin details.

        Raises:
            PluginNotFoundError: If plugin not found.
        """
        sql = """
            SELECT
                pv.id,
                p.plugin_type,
                p.name
            FROM plugin_variants pv
            JOIN plugins p ON p.id = pv.plugin_id
            WHERE p.name = :plugin_name
        """
        params: dict[str, Any] = {"plugin_name": plugin_name}

        if plugin_type is not None:
            sql += " AND p.plugin_type = :plugin_type"
            params["plugin_type"] = plugin_type.value

        if variant_name is not None:
            sql += " AND pv.name = :variant_name"
            params["variant_name"] = variant_name
        else:
            sql += " AND pv.id = p.default_variant_id"

        results = await fetch_all_dicts(self.db, sql, params)
        if len(results) == 1:
            return await self._variant_details(results[0]["id"])

        if len(results) > 1:
            raise PluginAmbiguityError(plugins=results)

        raise PluginNotFoundError(plugin_name=plugin_name, plugin_type=plugin_type, variant_name=variant_name)

    async def get_plugin_details(
        self,
        variant_id: ids.VariantID,
        *,
        meltano_version: compatibility.VersionTuple = compatibility.LATEST,
    ) -> api_schemas.PluginDetails:
        try:
            details = await self._variant_details(variant_id.as_db_id())
        except ValueError:
            raise PluginNotFoundError(
                plugin_name=variant_id.plugin_name,
                plugin_type=variant_id.plugin_type,
                variant_name=variant_id.plugin_variant,
            ) from None

        if meltano_version < (3, 9):
            details.settings = _convert_decimal_to_integer(details.settings)

        if meltano_version < (3, 3):
            for setting in details.settings:
                setting.root.sensitive = None

        return details

    async def get_default_variant_url(self, plugin_id: ids.PluginID) -> str:
        sql = """
            SELECT p.plugin_type, p.name, v.name AS variant
            FROM plugins p
            JOIN plugin_variants v ON v.id = p.default_variant_id
            WHERE v.plugin_id = :plugin_id
            LIMIT 1
        """
        result = await fetch_one_dict(self.db, sql, {"plugin_id": plugin_id.as_db_id()})

        if result:
            return _build_variant_path(
                plugin_type=enums.PluginTypeEnum(result["plugin_type"]),
                plugin_name=result["name"],
                plugin_variant=result["variant"],
                base_url=self.base_url,
            )

        raise PluginNotFoundError(plugin_name=plugin_id.plugin_name, plugin_type=plugin_id.plugin_type)

    async def _get_all_plugins(
        self: MeltanoHub,
        *,
        plugin_type: enums.PluginTypeEnum | None,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT p.name, p.plugin_type, pv.name AS variant, pv.logo_url, dv.name AS default_variant
            FROM plugin_variants pv
            JOIN plugins p ON p.id = pv.plugin_id
            JOIN plugin_variants dv ON dv.id = p.default_variant_id AND dv.plugin_id = p.id
        """

        params: dict[str, Any] = {}
        if plugin_type:
            sql += " WHERE p.plugin_type = :plugin_type"
            params["plugin_type"] = plugin_type.value

        return await fetch_all_dicts(self.db, sql, params)

    async def get_plugin_index(self: MeltanoHub) -> api_schemas.PluginIndex:
        """Get all plugins.

        Returns:
            Mapping of plugin name to variants.
        """
        plugins: api_schemas.PluginIndex = {key: {} for key in enums.PluginTypeEnum}

        for row in await self._get_all_plugins(plugin_type=None):
            plugin_name = row["name"]
            plugin_type = enums.PluginTypeEnum(row["plugin_type"])
            variant_name = row["variant"]
            logo_url = row["logo_url"]
            default_variant = row["default_variant"]

            logo_http_url = pydantic.HttpUrl(f"{self.base_hub_url}{logo_url}") if logo_url else None
            if plugin_name not in plugins[plugin_type]:
                plugins[plugin_type][plugin_name] = api_schemas.PluginRef(
                    default_variant=default_variant,
                    logo_url=logo_http_url,
                    variants={},
                )

            plugins[plugin_type][plugin_name].variants[variant_name] = api_schemas.VariantReference(
                ref=_build_variant_path(
                    plugin_type=plugin_type,
                    plugin_name=plugin_name,
                    plugin_variant=variant_name,
                    base_url=self.base_url,
                ),
            )

        return plugins

    async def get_plugin_type_index(
        self: MeltanoHub,
        *,
        plugin_type: str,
    ) -> api_schemas.PluginTypeIndex:
        """Get all plugins of a given type.

        Args:
            plugin_type: Plugin type.

        Returns:
            Mapping of plugin name to variants.

        Raises:
            NotFoundError: If the plugin type is not valid.
        """
        try:
            plugin_type_enum = enums.PluginTypeEnum(plugin_type)
        except ValueError:
            raise ids.InvalidPluginTypeError(plugin_type=plugin_type) from None

        plugins: api_schemas.PluginTypeIndex = {}

        for row in await self._get_all_plugins(plugin_type=plugin_type_enum):
            plugin_name = row["name"]
            variant_name = row["variant"]
            logo_url = row["logo_url"]
            default_variant = row["default_variant"]

            logo_http_url = pydantic.HttpUrl(f"{self.base_hub_url}{logo_url}") if logo_url else None
            if plugin_name not in plugins:
                plugins[plugin_name] = api_schemas.PluginRef(
                    default_variant=default_variant,
                    logo_url=logo_http_url,
                    variants={},
                )

            plugins[plugin_name].variants[variant_name] = api_schemas.VariantReference(
                ref=_build_variant_path(
                    plugin_type=plugin_type_enum,
                    plugin_name=plugin_name,
                    plugin_variant=variant_name,
                    base_url=self.base_url,
                ),
            )

        return plugins

    async def get_plugin_variants(self: MeltanoHub, plugin_id: ids.PluginID) -> api_schemas.PluginRef:
        """Get plugin variants."""
        sql = """
            SELECT
                p.name AS plugin,
                p.plugin_type,
                pv.logo_url,
                pv.name AS variant
            FROM plugins p
            JOIN plugin_variants pv ON pv.plugin_id = p.id
            WHERE p.id = :plugin_id AND p.plugin_type = :plugin_type
        """
        ref = api_schemas.PluginRef(default_variant="", logo_url=None, variants={})
        params = {
            "plugin_id": plugin_id.as_db_id(),
            "plugin_type": plugin_id.plugin_type.value,
        }
        for row in await fetch_all_dicts(self.db, sql, params):
            if not ref.default_variant:
                ref.default_variant = row["variant"]
                # breakpoint()
                ref.logo_url = pydantic.HttpUrl(f"{self.base_hub_url}{row['logo_url']}") if row["logo_url"] else None
            ref.variants[row["variant"]] = api_schemas.VariantReference(
                ref=_build_variant_path(
                    plugin_type=plugin_id.plugin_type,
                    plugin_name=plugin_id.plugin_name,
                    plugin_variant=row["variant"],
                    base_url=self.base_url,
                ),
            )
        return ref

    async def get_sdk_plugins(
        self: MeltanoHub,
        *,
        limit: int,
        plugin_type: api_schemas.PluginTypeOrAnyEnum,
    ) -> list[api_schemas.PluginListElement]:
        """Get all plugins with the sdk keyword.

        Returns:
            List of plugins.
        """
        sql = """
            SELECT p.name AS plugin, p.plugin_type, pv.name AS variant
            FROM plugins p
            JOIN plugin_variants pv ON pv.plugin_id = p.id
            JOIN keywords k ON k.variant_id = pv.id AND k.name = 'meltano_sdk'
        """

        params: dict[str, Any] = {"limit": limit}
        if plugin_type != api_schemas.PluginTypeOrAnyEnum.any:
            sql += " WHERE p.plugin_type = :plugin_type"
            params["plugin_type"] = plugin_type.value

        sql += " LIMIT :limit"

        result = await fetch_all_dicts(self.db, sql, params)
        return [
            api_schemas.PluginListElement(
                plugin=row["plugin"],
                variant=row["variant"],
                plugin_type=enums.PluginTypeEnum(row["plugin_type"]),
                ref=_build_variant_path(
                    plugin_type=enums.PluginTypeEnum(row["plugin_type"]),
                    plugin_name=row["plugin"],
                    plugin_variant=row["variant"],
                    base_url=self.base_url,
                ),
            )
            for row in result
        ]

    async def get_plugin_stats(self: MeltanoHub) -> dict[enums.PluginTypeEnum, int]:
        """Get plugin statistics.

        Returns:
            Plugin statistics.
        """
        sql = "SELECT plugin_type, COUNT(id) AS c FROM plugins GROUP BY plugin_type"
        result = await fetch_all_dicts(self.db, sql, {})
        return {enums.PluginTypeEnum(row["plugin_type"]): row["c"] for row in result}

    async def get_maintainers(self: MeltanoHub) -> api_schemas.MaintainersList:
        """Get maintainers.

        Returns:
            List of maintainers.
        """
        sql = "SELECT id, name, label, url FROM maintainers"
        result = await fetch_all_dicts(self.db, sql, {})
        maintainers = []
        for row in result:
            maintainer_dict = dict(row)
            maintainer_dict["links"] = {"details": f"/meltano/v1/maintainers/{row['id']}"}
            maintainers.append(api_schemas.Maintainer.model_validate(maintainer_dict))
        return api_schemas.MaintainersList(maintainers=maintainers)

    async def get_maintainer(self: MeltanoHub, maintainer_id: str) -> api_schemas.MaintainerDetails:
        """Get maintainer, with links to plugins.

        Args:
            maintainer: Maintainer ID.

        Returns:
            Maintainer.
        """
        maintainer_sql = "SELECT id, label, url FROM maintainers WHERE id = :maintainer_id"
        maintainer = await fetch_one_dict(self.db, maintainer_sql, {"maintainer_id": maintainer_id})

        if not maintainer:
            raise MaintainerNotFoundError(maintainer_id=maintainer_id)

        variants_sql = """
            SELECT p.name AS plugin_name, p.plugin_type, pv.name AS variant
            FROM plugin_variants pv
            JOIN plugins p ON p.id = pv.plugin_id
            WHERE pv.name = :maintainer_id
        """
        variants = await fetch_all_dicts(self.db, variants_sql, {"maintainer_id": maintainer_id})

        return api_schemas.MaintainerDetails(
            id=maintainer["id"],
            label=maintainer["label"],
            url=pydantic.HttpUrl(maintainer["url"]) if maintainer["url"] else None,
            links={
                v["plugin_name"]: _build_variant_path(
                    plugin_type=enums.PluginTypeEnum(v["plugin_type"]),
                    plugin_name=v["plugin_name"],
                    plugin_variant=v["variant"],
                    base_url=self.base_url,
                )
                for v in variants
            },
        )

    async def get_top_maintainers(self: MeltanoHub, n: int) -> list[api_schemas.MaintainerPluginCount]:
        """Get top maintainers.

        Returns:
            List of top maintainers.
        """
        sql = """
            SELECT m.id, m.label, m.url, COUNT(pv.id) AS plugin_count
            FROM maintainers m
            JOIN plugin_variants pv ON pv.name = m.id
            GROUP BY m.id
            ORDER BY plugin_count DESC
            LIMIT :n
        """
        result = await fetch_all_dicts(self.db, sql, {"n": n})
        return [api_schemas.MaintainerPluginCount.model_validate(row) for row in result]
