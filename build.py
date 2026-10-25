# ruff: file-ignore[hardcoded-sql-expression, print]
# pyrefly: ignore-errors[unused-call-result]

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any, assert_never
lazy import argparse
lazy import io
lazy import json
lazy import shutil
lazy import sqlite3
lazy import sys
lazy import tarfile
lazy import tempfile
lazy from http import HTTPStatus
lazy from pathlib import Path

lazy import platformdirs
lazy import pydantic
lazy import urllib3
lazy import yamlstar

lazy from hub_api import database, enums
lazy from hub_api.schemas import meltano, validation

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from pydantic_core import ErrorDetails


logger: logging.Logger = logging.getLogger(__name__)


def download_meltano_hub_archive(*, ref: str = "refs/heads/main", use_cache: bool = True) -> Path:
    """Download Meltano Hub archive."""
    cached_tree = platformdirs.user_cache_path("hub-api")
    cache_key_file = cached_tree / "key"

    url = f"https://codeload.github.com/meltano/hub/tar.gz/{ref}"
    headers: dict[str, str] = {}

    if use_cache and cache_key_file.is_file() and (cache_key := cache_key_file.read_text().strip()):
        headers["If-None-Match"] = cache_key

    response = urllib3.request("GET", url, timeout=10.0, retries=3, headers=headers)
    if response.status == HTTPStatus.NOT_MODIFIED:
        logger.info("Using cached directory %s", cached_tree)
        return cached_tree

    if response.status != HTTPStatus.OK:
        msg = f"Failed to download archive: HTTP {response.status}"
        raise RuntimeError(msg)

    logger.info("Downloaded archive")
    shutil.rmtree(cached_tree, ignore_errors=True)
    cached_tree.mkdir(parents=True)
    cache_key_file.write_text(response.headers["ETag"])

    with (
        tempfile.TemporaryDirectory() as extract_dir,
        tarfile.open(fileobj=io.BytesIO(response.data), mode="r:gz") as tar,
    ):
        tar.extractall(extract_dir, filter="data")
        extracted = tar.getnames()[0]

        # Move the `_data` directory in the extracted directory to the cache
        extracted_dir = Path(extract_dir) / extracted
        shutil.move(extracted_dir / "_data", cached_tree / "_data")

    return cached_tree


def load_yaml(ys: yamlstar.YAMLStar, path: Path) -> dict[str, dict[str, str]]:
    """Get default variants of a given plugin."""
    with path.open(encoding="utf-8") as f:
        return ys.load(f.read())  # type: ignore[no-any-return, no-untyped-call]


def get_plugin_variants(ys: yamlstar.YAMLStar, plugin_path: Path) -> Generator[tuple[str, dict[str, Any]]]:
    """Get plugin variants of a given type."""
    for plugin_file in plugin_path.glob("*.yml"):
        with plugin_file.open() as f:
            yield plugin_file.stem, ys.load(f.read())  # type: ignore[no-untyped-call]


def _build_setting(variant_id: str, setting: meltano.PluginSetting) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build setting object."""
    setting_id = f"{variant_id}.setting_{setting.root.name}"
    setting_data: dict[str, Any] = {
        "id": setting_id,
        "variant_id": variant_id,
        "name": setting.root.name,
        "label": setting.root.label,
        "documentation": setting.root.documentation,
        "description": setting.root.description,
        "placeholder": setting.root.placeholder,
        "env": setting.root.env,
        "kind": setting.root.kind,
        "value": None if setting.root.value is None else json.dumps(setting.root.value),
        "sensitive": setting.root.sensitive,
        "options": None,
    }

    match setting.root:
        case meltano.OptionsSetting():
            setting_data["options"] = [opt.model_dump() for opt in setting.root.options]
        case _:
            pass

    aliases_data: list[dict[str, Any]] = []
    if setting.root.aliases:
        aliases_data.extend(
            {
                "id": f"{setting_id}.alias_{alias}",
                "setting_id": setting_id,
                "name": alias,
            }
            for alias in setting.root.aliases
        )

    return setting_data, aliases_data


@dataclasses.dataclass
class LoadError:
    plugin_name: str
    variant: str
    link: str
    error: ErrorDetails


@dataclasses.dataclass
class LoadResult:
    errors: list[LoadError]

    def to_markdown(self) -> str:
        """Convert errors to a markdown table."""
        result = "## Build Errors\n\n| Plugin | Error | Value | Location |\n"
        result += "|--------|---------|------|----------|\n"
        result += "\n".join([
            (
                f"| [{error.variant}/{error.plugin_name}]({error.link}) "
                f"| {error.error['msg']} | {error.error['input']} "
                f"| {error.error['loc']} |"
            )
            for error in self.errors
        ])
        return result


def _insert_row(connection: sqlite3.Connection, table: str, row: dict[str, Any]) -> tuple[Any, ...]:
    """Insert a row into the specified table."""
    column_names = row.keys()
    columns = ", ".join(column_names)
    placeholders = ", ".join(f":{col}" for col in column_names)
    query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *"
    cursor = connection.execute(query, row)
    return cursor.fetchone()  # type: ignore[no-any-return]


def _insert_rows(connection: sqlite3.Connection, table: str, rows: Sequence[dict[str, Any]]) -> None:
    """Insert multiple rows into the specified table."""
    if not rows:
        return

    column_names = rows[0].keys()
    columns = ", ".join(column_names)
    placeholders = ", ".join(f":{col}" for col in column_names)
    query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
    connection.executemany(query, rows)


def _match_plugin(
    plugin_type: enums.PluginTypeEnum,
    definition: dict[str, Any],
) -> validation.HubPluginDefinition:
    plugin: validation.HubPluginDefinition
    match plugin_type:
        case enums.PluginTypeEnum.extractors:
            plugin = validation.ExtractorDefinition.model_validate(definition)
        case enums.PluginTypeEnum.loaders:
            plugin = validation.LoaderDefinition.model_validate(definition)
        case enums.PluginTypeEnum.utilities:
            plugin = validation.UtilityDefinition.model_validate(definition)
        case enums.PluginTypeEnum.transformers:
            plugin = validation.TransformerDefinition.model_validate(definition)
        case enums.PluginTypeEnum.transforms:
            plugin = validation.TransformDefinition.model_validate(definition)
        case enums.PluginTypeEnum.orchestrators:
            plugin = validation.OrchestratorDefinition.model_validate(definition)
        case enums.PluginTypeEnum.mappers:
            plugin = validation.MapperDefinition.model_validate(definition)
        case enums.PluginTypeEnum.files:
            plugin = validation.FileDefinition.model_validate(definition)
        case _:
            assert_never(plugin_type)

    return plugin


def _insert_variant(  # ruff: ignore[too-many-arguments]
    *,
    connection: sqlite3.Connection,
    variant: str,
    plugin_id: str,
    plugin_type: enums.PluginTypeEnum,
    plugin_name: str,
    definition: dict[str, Any],
) -> Generator[LoadError]:
    """Insert a variant into the database."""
    try:
        plugin = _match_plugin(plugin_type, definition)
    except pydantic.ValidationError as exc:
        logger.error("Error validating plugin %s", plugin_id)
        for error in exc.errors():
            yield LoadError(
                plugin_name=plugin_name,
                variant=variant,
                link=f"https://github.com/meltano/hub/blob/main/_data/meltano/{plugin_type}/{plugin_name}/{variant}.yml",
                error=error,
            )
        return

    variant_id = f"{plugin_id}.{variant}"
    inserted = _insert_row(
        connection,
        "plugin_variants",
        {
            "plugin_id": plugin_id,
            "id": variant_id,
            "description": plugin.description,
            "executable": plugin.executable,
            "docs": str(plugin.docs) if plugin.docs else None,
            "name": variant,
            "label": plugin.label,
            "logo_url": plugin.logo_url,
            "pip_url": plugin.pip_url,
            "repo": str(plugin.repo),
            "ext_repo": str(plugin.ext_repo) if plugin.ext_repo else None,
            "namespace": plugin.namespace,
            "hidden": plugin.hidden,
            "maintenance_status": plugin.maintenance_status.value if plugin.maintenance_status else None,
            "quality": plugin.quality.value if plugin.quality else None,
            "domain_url": str(plugin.domain_url) if plugin.domain_url else None,
            "definition": plugin.definition,
            "next_steps": plugin.next_steps,
            "settings_preamble": plugin.settings_preamble,
            "usage": plugin.usage,
            "prereq": plugin.prereq,
            "supported_python_versions": json.dumps(plugin.supported_python_versions)
            if plugin.supported_python_versions
            else None,
        },
    )
    logger.debug("Inserted variant %s", inserted[0])

    for setting in plugin.settings:
        setting_data, aliases_data = _build_setting(variant_id, setting)
        inserted = _insert_row(connection, "settings", setting_data)
        logger.debug("Inserted setting %s", inserted[0])

        _insert_rows(connection, "setting_aliases", aliases_data)

    _insert_rows(
        connection,
        "setting_groups",
        [
            {
                "variant_id": variant_id,
                "setting_id": f"{variant_id}.setting_{setting_name}",
                "setting_name": setting_name,
                "group_id": group_idx,
            }
            for group_idx, setting_group in enumerate(definition.get("settings_group_validation", []))
            for setting_name in setting_group
        ],
    )

    _insert_rows(
        connection,
        "capabilities",
        [
            {
                "id": f"{variant_id}.capability_{capability}",
                "variant_id": variant_id,
                "name": capability,
            }
            for capability in definition.get("capabilities", [])
        ],
    )

    _insert_rows(
        connection,
        "keywords",
        [
            {
                "id": f"{variant_id}.keyword_{keyword}",
                "variant_id": variant_id,
                "name": keyword,
            }
            for keyword in definition.get("keywords", [])
        ],
    )

    _insert_rows(
        connection,
        "selects",
        [
            {
                "id": f"{variant_id}.select_{i}",
                "variant_id": variant_id,
                "expression": select,
            }
            for i, select in enumerate(definition.get("select", []))
        ],
    )

    _insert_rows(
        connection,
        "metadata",
        [
            {
                "id": f"{variant_id}.metadata_{i}",
                "variant_id": variant_id,
                "key": key,
                "value": metadata,
            }
            for i, (key, metadata) in enumerate(definition.get("metadata", {}).items())
        ],
    )

    for command_name, command in definition.get("commands", {}).items():
        command_id = f"{variant_id}.command_{command_name}"
        if isinstance(command, str):
            command_details = {
                "id": command_id,
                "variant_id": variant_id,
                "name": command_name,
                "args": command,
            }
        else:
            command_details = {
                "id": command_id,
                "variant_id": variant_id,
                "name": command_name,
                "args": command.get("args"),
                "description": command.get("description"),
                "executable": command.get("executable"),
            }
        inserted = _insert_row(connection, "commands", command_details)
        logger.debug("Inserted command %s", inserted[0])


def load_db(path: Path, connection: sqlite3.Connection) -> LoadResult:
    """Load database."""
    ys = yamlstar.YAMLStar()  # type: ignore[no-untyped-call]
    result = LoadResult(errors=[])
    default_variants = load_yaml(ys, path.joinpath("default_variants.yml"))
    maintainers = load_yaml(ys, path.joinpath("maintainers.yml"))

    _insert_rows(
        connection,
        "maintainers",
        [
            {
                "id": maintainer_id,
                "name": maintainer_data.get("name"),
                "label": maintainer_data.get("label"),
                "url": maintainer_data.get("url"),
            }
            for maintainer_id, maintainer_data in maintainers.items()
        ],
    )

    for plugin_type in enums.PluginTypeEnum:
        variant_count = 0  # Counter for processed plugin variants
        plugin_count = 0  # Counter for processed plugins
        for plugin_path in path.joinpath("meltano", plugin_type).glob("*"):
            plugin_name = plugin_path.name
            default_variant = default_variants[plugin_type].get(plugin_name)
            plugin_id = f"{plugin_type}.{plugin_name}"
            default_variant_id = f"{plugin_id}.{default_variant}"

            for variant, definition in get_plugin_variants(ys, plugin_path):
                result.errors.extend(
                    _insert_variant(
                        connection=connection,
                        variant=variant,
                        plugin_id=plugin_id,
                        plugin_type=plugin_type,
                        plugin_name=plugin_name,
                        definition=definition,
                    )
                )
                variant_count += 1

            inserted = _insert_row(
                connection,
                "plugins",
                {
                    "id": plugin_id,
                    "default_variant_id": default_variant_id,
                    "plugin_type": plugin_type.value,
                    "name": plugin_name,
                },
            )
            logger.debug("Inserted plugin %s", inserted[0])
            plugin_count += 1

        logger.info(
            "Processed %d variants for %d unique %s",
            variant_count,
            plugin_count,
            plugin_type.value,
        )

    connection.commit()
    return result


def main() -> int:
    @dataclasses.dataclass(init=False)
    class CLINamespace:
        git_ref: str
        cache: bool
        exit_zero: bool
        verbose: bool

    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--git-ref", default="refs/heads/main", help="e.g. refs/head/main")
    parser.add_argument("--no-cache", action="store_false", dest="cache", help="disable the cache")
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        dest="exit_zero",
        help="exit with code 0 even when an error occurs",
    )
    parser.add_argument("--verbose", action="store_true", help="print debug output")

    args = parser.parse_args(namespace=CLINamespace())

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s - %(message)s")
    sqlite3.register_adapter(list, json.dumps)
    sqlite3.register_adapter(dict, json.dumps)

    hub_dir = download_meltano_hub_archive(ref=args.git_ref, use_cache=args.cache)
    schema_sql = database.get_db_schema()

    db_path = database.get_db_path()
    with (
        tempfile.NamedTemporaryFile(suffix=".db", dir=db_path.parent) as tmp_file,
        sqlite3.connect(tmp_file.name) as connection,
    ):
        connection.executescript(schema_sql)

        result = load_db(hub_dir / "_data", connection)
        print(result.to_markdown())

        Path(tmp_file.name).replace(db_path)

    return 0 if args.exit_zero else 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
