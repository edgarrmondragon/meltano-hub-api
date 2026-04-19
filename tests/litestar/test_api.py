"""Test FastAPI app."""

from __future__ import annotations

import http
import unittest.mock
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from litestar.connection.request import Request
from litestar.datastructures import Headers
from litestar.testing import AsyncTestClient

from hub_api import enums
from hub_api.helpers import compatibility
from hub_api.litestar_app.app import app
from hub_api.litestar_app.plugins import get_version_tuple

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from litestar.app import Litestar

type API = AsyncTestClient[Litestar]


@pytest_asyncio.fixture
async def api() -> AsyncGenerator[API]:
    """Create app."""
    async with AsyncTestClient(app=app) as client:
        yield client


@pytest.mark.asyncio
async def test_method_not_allowed(api: API) -> None:
    """Test /meltano/api/v1/version."""
    response = await api.post("/meltano/api/v1/plugins/index")
    assert response.status_code == http.HTTPStatus.METHOD_NOT_ALLOWED
    assert response.json()["details"] == "405: Method Not Allowed"
    assert set(response.headers["Allow"].split(", ")) == {"GET", "OPTIONS"}


@pytest.mark.asyncio
async def test_plugin_index(api: API) -> None:
    """Test /meltano/api/v1/plugins/extractors/index."""
    response = await api.get("/meltano/api/v1/plugins/index")
    assert response.status_code == http.HTTPStatus.OK
    assert response.json()


@pytest.mark.asyncio
async def test_plugin_type_index(api: API) -> None:
    """Test /meltano/api/v1/plugins/extractors/index."""
    response = await api.get("/meltano/api/v1/plugins/extractors/index")
    assert response.status_code == http.HTTPStatus.OK
    assert response.json()


@pytest.mark.asyncio
async def test_plugin_variants(api: API) -> None:
    """Test /meltano/api/v1/plugins/extractors/tap-github."""
    response = await api.get("/meltano/api/v1/plugins/extractors/tap-github")
    assert response.status_code == http.HTTPStatus.OK
    data = response.json()
    assert "default_variant" in data
    assert "logo_url" in data
    assert "variants" in data
    assert len(data["variants"]) > 0
    assert all("ref" in data["variants"][variant] for variant in data["variants"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plugin", "plugin_type", "variant"),
    [
        ("tap-github", enums.PluginTypeEnum.extractors, "singer-io"),
        ("tap-adwords", enums.PluginTypeEnum.extractors, "meltano"),
        ("tap-mssql", enums.PluginTypeEnum.extractors, "wintersrd"),
        ("tap-mssql", enums.PluginTypeEnum.extractors, "airbyte"),
        ("target-postgres", enums.PluginTypeEnum.loaders, "meltanolabs"),
        ("dbt-postgres", enums.PluginTypeEnum.utilities, "dbt-labs"),
    ],
)
async def test_plugin_details(
    api: API,
    plugin: str,
    plugin_type: enums.PluginTypeEnum,
    variant: str,
) -> None:
    """Test /meltano/api/v1/plugins/extractors/<plugin>--<variant>."""
    path = f"/meltano/api/v1/plugins/{plugin_type}/{plugin}--{variant}"
    response = await api.get(path)
    assert response.status_code == http.HTTPStatus.OK

    details = response.json()
    assert details["name"] == plugin


@pytest.mark.asyncio
async def test_plugin_type_index_type_not_valid(api: API) -> None:
    """Test /meltano/api/v1/plugins/<invalid_type>/index."""
    response = await api.get("/meltano/api/v1/plugins/unknown/index")
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert response.json()["extra"][0] == {
        "message": "Invalid enum value 'unknown'",
        "key": "plugin_type",
        "source": "path",
    }


@pytest.mark.asyncio
async def test_plugin_variant_not_found(api: API) -> None:
    """Test /meltano/api/v1/plugins/extractors/<plugin>--<variant>."""
    response = await api.get("/meltano/api/v1/plugins/extractors/tap-github--unknown")
    assert response.status_code == http.HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_sdk_filter(api: API) -> None:
    """Test /meltano/api/v1/plugins/made-with-sdk."""
    response = await api.get("/meltano/api/v1/plugins/made-with-sdk")
    assert response.status_code == http.HTTPStatus.OK

    plugins = response.json()
    assert len(plugins) > 0


@pytest.mark.asyncio
async def test_hub_stats(api: API) -> None:
    """Test /meltano/api/v1/plugins/stats."""
    response = await api.get("/meltano/api/v1/plugins/stats")
    assert response.status_code == http.HTTPStatus.OK

    stats = response.json()
    assert isinstance(stats["extractors"], int)


@pytest.mark.asyncio
async def test_maintainers(api: API) -> None:
    """Test /meltano/api/v1/maintainers."""
    response = await api.get("/meltano/api/v1/maintainers")
    assert response.status_code == http.HTTPStatus.OK

    data = response.json()
    maintainer = next(filter(lambda m: m["id"] == "edgarrmondragon", data["maintainers"]))
    assert maintainer["id"] == "edgarrmondragon"
    assert maintainer["url"] == "https://github.com/edgarrmondragon"


@pytest.mark.asyncio
async def test_maintainer_details(api: API) -> None:
    """Test /meltano/api/v1/maintainers."""
    response = await api.get("/meltano/api/v1/maintainers/edgarrmondragon")
    assert response.status_code == http.HTTPStatus.OK

    maintainer = response.json()
    assert maintainer["id"] == "edgarrmondragon"
    assert maintainer["url"] == "https://github.com/edgarrmondragon"
    assert isinstance(maintainer["links"], dict)
    assert len(maintainer["links"]) > 0


@pytest.mark.asyncio
async def test_top_maintainers(api: API) -> None:
    """Test /meltano/api/v1/maintainers."""
    n = 3
    response = await api.get("/meltano/api/v1/maintainers/top", params={"count": n})
    assert response.status_code == http.HTTPStatus.OK

    maintainers = response.json()
    assert len(maintainers) == n


@pytest.mark.asyncio
async def test_default_plugin(api: API) -> None:
    """Test /meltano/api/v1/plugins/extractors/tap-github/default."""
    response = await api.get("/meltano/api/v1/plugins/extractors/tap-github/default")
    assert response.status_code == http.HTTPStatus.OK
    assert not response.is_redirect
    assert response.url.path.endswith("extractors/tap-github/meltanolabs")


@pytest.mark.asyncio
async def test_gzip_encoding(api: API) -> None:
    """Test GZIP encoding."""
    # Large response should be compressed
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == http.HTTPStatus.OK
    assert response.headers["Content-Encoding"] == "gzip"
    assert response.headers["Content-Type"] == "application/json"

    # Small response should not be compressed
    response = await api.get("/meltano/api/v1/plugins/orchestrators/index", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == http.HTTPStatus.OK
    assert "Content-Encoding" not in response.headers
    assert response.headers["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    ("ua_value", "version"),
    [
        pytest.param("Meltano/1.0.0", (1, 0), id="normal"),
        pytest.param("Meltano/1.0.0rc1", (1, 0), id="prerelease"),
        pytest.param("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", compatibility.LATEST, id="missing"),
        pytest.param("Meltano/NOT_A_VERSION", compatibility.LATEST, id="invalid"),
    ],
)
def test_get_client_version(ua_value: str, version: tuple[int, int]) -> None:
    """Test get_client_version."""
    mock_request = unittest.mock.Mock(spec=Request)
    mock_request.headers = Headers({"User-Agent": ua_value})
    assert get_version_tuple(mock_request) == version
