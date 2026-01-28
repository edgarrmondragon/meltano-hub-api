"""Test Hub data access."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import aiosqlite
import pytest
import pytest_asyncio
from faker import Faker

from hub_api import client, database, enums, ids
from hub_api.helpers import compatibility
from hub_api.schemas import api as api_schemas

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture(scope="session")
def base_url() -> str:
    """The base URL for the test server."""
    faker = Faker()
    return f"http://{faker.hostname()}"


@pytest_asyncio.fixture
async def hub(base_url: str) -> AsyncGenerator[client.MeltanoHub]:
    """Get a Meltano hub instance."""
    db = await database.open_db()
    try:
        yield client.MeltanoHub(db=db, base_url=base_url)
    finally:
        await db.close()


def test_plugin_id() -> None:
    """Test plugin ID."""
    plugin_id = ids.PluginID.from_params(plugin_type="extractors", plugin_name="tap-github")
    assert plugin_id.as_db_id() == "extractors.tap-github"


def test_plugin_id_invalid_type() -> None:
    """Test plugin ID."""
    with pytest.raises(ids.InvalidPluginTypeError):
        ids.PluginID.from_params(plugin_type="unknown", plugin_name="tap-github")


def test_variant_id() -> None:
    """Test variant ID."""
    variant_id = ids.VariantID.from_params(
        plugin_type="extractors",
        plugin_name="tap-github",
        plugin_variant="singer-io",
    )
    assert variant_id.as_db_id() == "extractors.tap-github.singer-io"


def test_variant_id_invalid_type() -> None:
    """Test variant ID."""
    with pytest.raises(ids.InvalidPluginTypeError):
        ids.VariantID.from_params(plugin_type="unknown", plugin_name="tap-github", plugin_variant="singer-io")


@pytest.mark.asyncio
async def test_find_plugin(hub: client.MeltanoHub) -> None:
    response = await hub.find_plugin(plugin_name="tap-github")
    assert isinstance(response, api_schemas.ExtractorResponse)


@pytest.mark.asyncio
async def test_find_plugin_name_not_found(hub: client.MeltanoHub) -> None:
    with pytest.raises(client.PluginNotFoundError, match=r"Plugin 'tap-unknown' was not found"):
        await hub.find_plugin(plugin_name="tap-unknown")


@pytest.mark.asyncio
async def test_find_plugin_of_type_not_found(hub: client.MeltanoHub) -> None:
    with pytest.raises(client.PluginNotFoundError, match=r"Plugin 'tap-github' was not found in loaders"):
        await hub.find_plugin(plugin_name="tap-github", plugin_type=enums.PluginTypeEnum.loaders)


@pytest.mark.asyncio
async def test_find_plugin_variant_not_found(hub: client.MeltanoHub) -> None:
    with pytest.raises(client.PluginNotFoundError, match=r"Variant 'acme' of 'tap-github' was not found"):
        await hub.find_plugin(plugin_name="tap-github", variant_name="acme")


@pytest.mark.asyncio
async def test_find_plugin_of_multiple_types(hub: client.MeltanoHub) -> None:
    airflow_utility = await hub.find_plugin(plugin_name="airflow", plugin_type=enums.PluginTypeEnum.utilities)
    assert isinstance(airflow_utility, api_schemas.UtilityResponse)

    airflow_orchestrator = await hub.find_plugin(plugin_name="airflow", plugin_type=enums.PluginTypeEnum.orchestrators)
    assert isinstance(airflow_orchestrator, api_schemas.OrchestratorResponse)


@pytest.mark.asyncio
async def test_find_plugin_ambiguous(hub: client.MeltanoHub) -> None:
    with pytest.raises(
        client.PluginAmbiguityError,
        match=r"More than one plugin found for the given criteria: airflow \(utilities\), airflow \(orchestrators\)",
    ):
        await hub.find_plugin(plugin_name="airflow")


@pytest.mark.asyncio
async def test_get_plugin_index(hub: client.MeltanoHub) -> None:
    """Test get_plugin_index."""
    plugins = await hub.get_plugin_index()
    assert plugins


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plugin_type",
    list(enums.PluginTypeEnum),
)
async def test_get_plugin_type_index(hub: client.MeltanoHub, plugin_type: enums.PluginTypeEnum) -> None:
    """Test get_plugin_type_index."""
    plugin_types = await hub.get_plugin_type_index(plugin_type=plugin_type)
    assert plugin_types


@pytest.mark.asyncio
async def test_get_plugin_type_index_type_not_valid(hub: client.MeltanoHub) -> None:
    """Test get_plugin_type_index."""
    with pytest.raises(ids.InvalidPluginTypeError):
        await hub.get_plugin_type_index(plugin_type="unknown")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plugin", "plugin_type", "variant"),
    [
        pytest.param("tap-github", enums.PluginTypeEnum.extractors, "singer-io"),
        pytest.param("tap-adwords", enums.PluginTypeEnum.extractors, "meltano"),
        pytest.param("tap-mssql", enums.PluginTypeEnum.extractors, "wintersrd"),
        pytest.param("tap-mssql", enums.PluginTypeEnum.extractors, "airbyte"),
        pytest.param("target-postgres", enums.PluginTypeEnum.loaders, "meltanolabs"),
        pytest.param("target-bigquery", enums.PluginTypeEnum.loaders, "z3z1ma"),
        pytest.param("dbt-postgres", enums.PluginTypeEnum.utilities, "dbt-labs"),
        pytest.param("dbt-postgres", enums.PluginTypeEnum.transformers, "dbt-labs"),
        pytest.param("tap-gitlab", enums.PluginTypeEnum.transforms, "meltano"),
        pytest.param("files-docker", enums.PluginTypeEnum.files, "meltano"),
        pytest.param("airflow", enums.PluginTypeEnum.orchestrators, "apache"),
        pytest.param("meltano-map-transformer", enums.PluginTypeEnum.mappers, "meltano"),
    ],
)
async def test_get_plugin_details(
    hub: client.MeltanoHub,
    plugin: str,
    plugin_type: str,
    variant: str,
) -> None:
    """Test get_plugin_details."""
    variant_id = ids.VariantID.from_params(plugin_type=plugin_type, plugin_name=plugin, plugin_variant=variant)
    details = await hub.get_plugin_details(variant_id=variant_id)
    assert details.name == plugin
    assert details.variant == variant


@pytest.mark.asyncio
async def test_get_plugin_variant_not_found(hub: client.MeltanoHub) -> None:
    """Test get_plugin_details."""
    with pytest.raises(client.PluginNotFoundError):
        await hub.get_plugin_details(
            variant_id=ids.VariantID.from_params(
                plugin_type="extractors",
                plugin_name="tap-github",
                plugin_variant="unknown",
            )
        )


@pytest.mark.asyncio
async def test_get_sdk_plugins(hub: client.MeltanoHub) -> None:
    """Test get_sdk_plugins."""
    n = 10
    plugins = await hub.get_sdk_plugins(limit=n, plugin_type=api_schemas.PluginTypeOrAnyEnum.any)
    assert len(plugins) == n

    extractors = await hub.get_sdk_plugins(limit=n, plugin_type=api_schemas.PluginTypeOrAnyEnum.extractors)
    assert len(extractors) == n


@pytest.mark.asyncio
async def test_get_plugin_stats(hub: client.MeltanoHub) -> None:
    """Test get_plugin_stats."""
    stats = await hub.get_plugin_stats()
    assert stats


@pytest.mark.asyncio
async def test_get_maintainers(hub: client.MeltanoHub) -> None:
    """Test get_maintainers."""
    data = await hub.get_maintainers()
    assert len(data.maintainers) > 0


@pytest.mark.asyncio
async def test_get_maintainer(hub: client.MeltanoHub) -> None:
    """Test get_maintainer."""
    maintainer = await hub.get_maintainer("meltano")
    assert maintainer.id == "meltano"
    assert maintainer.label == "Meltano"
    assert str(maintainer.url) == "https://meltano.com/"
    assert len(maintainer.links) > 0


@pytest.mark.asyncio
async def test_get_maintainer_not_found(hub: client.MeltanoHub) -> None:
    """Test get_maintainer."""
    with pytest.raises(client.MaintainerNotFoundError):
        await hub.get_maintainer("unknown")


@pytest.mark.asyncio
async def test_get_top_maintainers(hub: client.MeltanoHub) -> None:
    """Test get_top_maintainers."""
    n = 10
    maintainers = await hub.get_top_maintainers(n)
    assert len(maintainers) == n


@pytest.mark.asyncio
async def test_get_default_variant_url(hub: client.MeltanoHub) -> None:
    """Test get_variant_url."""
    good_plugin_id = ids.PluginID.from_params(plugin_type="extractors", plugin_name="tap-github")
    url = await hub.get_default_variant_url(good_plugin_id)
    assert str(url).endswith("extractors/tap-github--meltanolabs")

    bad_plugin_id = ids.PluginID.from_params(plugin_type="extractors", plugin_name="unknown")
    with pytest.raises(client.PluginNotFoundError):
        await hub.get_default_variant_url(bad_plugin_id)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[aiosqlite.Connection]:
    """Get a database session."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row

    schema_sql = database.get_db_schema()

    await conn.executescript(schema_sql)

    await conn.execute("""
        INSERT INTO plugins (id, plugin_type, name, default_variant_id)
        VALUES ('extractors.tap-mock', 'extractors', 'tap-mock', 'extractors.tap-mock.singer')
    """)
    await conn.execute("""
        INSERT INTO plugin_variants (id, plugin_id, name, namespace, repo)
        VALUES ('extractors.tap-mock.singer', 'extractors.tap-mock', 'singer', 'tap_mock',
                'https://github.com/singer-io/tap-mock')
    """)
    await conn.execute(
        """
        INSERT INTO settings (id, variant_id, name, kind, sensitive)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("extractors.tap-mock.singer.setting_mock_string", "extractors.tap-mock.singer", "mock_string", "string", 1),
    )
    await conn.execute(
        """
        INSERT INTO settings (id, variant_id, name, kind)
        VALUES (?, ?, ?, ?)
        """,
        ("extractors.tap-mock.singer.setting_mock_integer", "extractors.tap-mock.singer", "mock_integer", "integer"),
    )
    await conn.execute(
        """
        INSERT INTO settings (id, variant_id, name, kind)
        VALUES (?, ?, ?, ?)
        """,
        ("extractors.tap-mock.singer.setting_mock_decimal", "extractors.tap-mock.singer", "mock_decimal", "decimal"),
    )
    await conn.execute("""
        INSERT INTO setting_aliases (id, setting_id, name)
        VALUES ('extractors.tap-mock.singer.setting_mock_string.alias_mock_string_alias',
                'extractors.tap-mock.singer.setting_mock_string', 'mock_string_alias')
    """)

    await conn.commit()
    try:
        yield conn
    finally:
        await conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("meltano_version", "settings_dict"),
    [
        pytest.param(
            compatibility.LATEST,
            {
                "mock_string": {
                    "aliases": ["mock_string_alias"],
                    "name": "mock_string",
                    "sensitive": True,
                    "kind": "string",
                },
                "mock_integer": {
                    "name": "mock_integer",
                    "kind": "integer",
                },
                "mock_decimal": {
                    "name": "mock_decimal",
                    "kind": "decimal",
                },
            },
            id="latest",
        ),
        pytest.param(
            (3, 2),
            {
                "mock_string": {
                    "aliases": ["mock_string_alias"],
                    "name": "mock_string",
                    "kind": "string",
                },
                "mock_integer": {
                    "name": "mock_integer",
                    "kind": "integer",
                },
                "mock_decimal": {
                    "name": "mock_decimal",
                    "kind": "integer",
                },
            },
            id="<3.3",
        ),
        pytest.param(
            (3, 5),
            {
                "mock_string": {
                    "aliases": ["mock_string_alias"],
                    "name": "mock_string",
                    "sensitive": True,
                    "kind": "string",
                },
                "mock_integer": {
                    "name": "mock_integer",
                    "kind": "integer",
                },
                "mock_decimal": {
                    "name": "mock_decimal",
                    "kind": "integer",
                },
            },
            id=">=3.3,<3.9",
        ),
        pytest.param(
            (3, 9),
            {
                "mock_string": {
                    "aliases": ["mock_string_alias"],
                    "name": "mock_string",
                    "sensitive": True,
                    "kind": "string",
                },
                "mock_integer": {
                    "name": "mock_integer",
                    "kind": "integer",
                },
                "mock_decimal": {
                    "name": "mock_decimal",
                    "kind": "decimal",
                },
            },
            id=">=3.9",
        ),
    ],
)
async def test_get_plugin_details_meltano_version(
    base_url: str,
    db: aiosqlite.Connection,
    meltano_version: tuple[int, int],
    settings_dict: dict[str, dict[str, Any]],
) -> None:
    """Test get_plugin_details."""

    hub = client.MeltanoHub(db=db, base_url=base_url)
    details = await hub.get_plugin_details(
        variant_id=ids.VariantID.from_params(
            plugin_type="extractors",
            plugin_name="tap-mock",
            plugin_variant="singer",
        ),
        meltano_version=meltano_version,
    )
    settings = {s.root.name: s.model_dump(exclude_none=True) for s in details.settings}
    checks = [settings[name] == s for name, s in settings_dict.items()]
    assert all(checks)
