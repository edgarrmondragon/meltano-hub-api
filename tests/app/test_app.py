"""Test FastAPI app."""

from __future__ import annotations

import http
import unittest.mock
from typing import TYPE_CHECKING, Any

import fastapi
import httpx
import pytest
from faker import Faker
from starlette.datastructures import Headers
from starlette.requests import Request
from syrupy.extensions.json import JSONSnapshotExtension

from hub_api import enums, main
from hub_api.helpers import compatibility, etag

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


@pytest.fixture(scope="session")
def base_url() -> str:
    """The base URL for the test server."""
    faker = Faker()
    return f"http://{faker.hostname()}"


@pytest.fixture(scope="session")
def api(base_url: str) -> httpx.AsyncClient:
    """Create app."""
    return httpx.AsyncClient(base_url=base_url, transport=httpx.ASGITransport(app=main.app))


@pytest.mark.asyncio
async def test_plugin_index(base_url: str, api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/plugins/extractors/index."""
    response = await api.get("/meltano/api/v1/plugins/index")
    assert response.status_code == http.HTTPStatus.OK
    assert response.json()

    data: dict[str, Any] = response.json()
    plugin_type_info = next(iter(data.values()))
    plugin_info = next(iter(plugin_type_info.values()))

    default_variant_name = plugin_info["default_variant"]
    default_variant = plugin_info["variants"][default_variant_name]
    assert default_variant["ref"].startswith(base_url)


@pytest.mark.asyncio
async def test_plugin_type_index(base_url: str, api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/plugins/extractors/index."""
    response = await api.get("/meltano/api/v1/plugins/extractors/index")
    assert response.status_code == http.HTTPStatus.OK

    data: dict[str, Any] = response.json()
    plugin_info = next(iter(data.values()))

    default_variant_name = plugin_info["default_variant"]
    default_variant = plugin_info["variants"][default_variant_name]
    assert default_variant["ref"].startswith(base_url)


@pytest.mark.asyncio
async def test_plugin_search(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/plugins/search."""
    response = await api.get("/meltano/api/v1/plugins/search")
    assert response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {
        "detail": [
            {
                "type": "missing",
                "loc": ["query", "name"],
                "msg": "Field required",
                "input": {},
            },
        ]
    }

    response = await api.get(
        "/meltano/api/v1/plugins/search",
        params={"name": "tap-github"},
        follow_redirects=True,
    )
    assert response.status_code == http.HTTPStatus.OK
    assert response.json()["name"] == "tap-github"

    response = await api.get(
        "/meltano/api/v1/plugins/search",
        params={"name": "tap-unknown"},
        follow_redirects=True,
    )
    assert response.status_code == http.HTTPStatus.NOT_FOUND
    assert response.json() == {"detail": "Plugin 'tap-unknown' was not found"}

    response = await api.get(
        "/meltano/api/v1/plugins/search",
        params={"name": "tap-github", "variant": "unknown"},
        follow_redirects=True,
    )
    assert response.status_code == http.HTTPStatus.NOT_FOUND
    assert response.json() == {"detail": "Variant 'unknown' of 'tap-github' was not found"}

    response = await api.get(
        "/meltano/api/v1/plugins/search",
        params={"name": "tap-github", "type": "loaders"},
        follow_redirects=True,
    )
    assert response.status_code == http.HTTPStatus.NOT_FOUND
    assert response.json() == {"detail": "Plugin 'tap-github' was not found in loaders"}


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
    api: httpx.AsyncClient,
    plugin: str,
    plugin_type: enums.PluginTypeEnum,
    variant: str,
    snapshot: SnapshotAssertion,
) -> None:
    """Test /meltano/api/v1/plugins/extractors/<plugin>--<variant>."""
    path = f"/meltano/api/v1/plugins/{plugin_type}/{plugin}--{variant}"
    response = await api.get(path)
    assert response.status_code == http.HTTPStatus.OK

    details = response.json()
    assert details["name"] == plugin

    snapshot_json = snapshot.with_defaults(extension_class=JSONSnapshotExtension)
    assert snapshot_json(name=plugin) == details


@pytest.mark.parametrize(
    ("headers", "etag"),
    [
        ({}, etag.ETAGS[compatibility.Compatibility.LATEST]),
        ({"User-Agent": "Meltano/3.2.0"}, etag.ETAGS[compatibility.Compatibility.PRE_3_3]),
        ({"User-Agent": "Meltano/3.8.0"}, etag.ETAGS[compatibility.Compatibility.PRE_3_9]),
        ({"User-Agent": "Meltano/3.9.0"}, etag.ETAGS[compatibility.Compatibility.LATEST]),
    ],
)
@pytest.mark.asyncio
async def test_plugin_index_etag_match(api: httpx.AsyncClient, headers: dict[str, str], etag: str) -> None:
    """Test /meltano/api/v1/plugins/stats."""
    response = await api.get("/meltano/api/v1/plugins/index", headers=headers)
    assert response.status_code == http.HTTPStatus.OK
    assert response.headers["ETag"] == etag
    assert "extractors" in response.json()

    response = await api.get(
        "/meltano/api/v1/plugins/index",
        headers={"If-None-Match": etag, **headers},
    )
    assert response.status_code == http.HTTPStatus.NOT_MODIFIED
    assert not response.content


@pytest.mark.asyncio
async def test_plugin_type_index_type_not_valid(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/plugins/<invalid_type>/index."""
    response = await api.get("/meltano/api/v1/plugins/unknown/index")
    assert response.status_code == http.HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "'unknown' is not a valid plugin type"


@pytest.mark.asyncio
async def test_invalid_etag(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/plugins/stats."""
    response = await api.get(
        "/meltano/api/v1/plugins/index",
        headers={"If-None-Match": "not-a-valid-etag"},
    )
    assert response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_plugin_variant_not_found(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/plugins/extractors/<plugin>--<variant>."""
    response = await api.get("/meltano/api/v1/plugins/extractors/tap-github--unknown")
    assert response.status_code == http.HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_sdk_filter(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/plugins/made-with-sdk."""
    response = await api.get("/meltano/api/v1/plugins/made-with-sdk")
    assert response.status_code == http.HTTPStatus.OK

    plugins = response.json()
    assert len(plugins) > 0


@pytest.mark.asyncio
async def test_hub_stats(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/plugins/stats."""
    response = await api.get("/meltano/api/v1/plugins/stats")
    assert response.status_code == http.HTTPStatus.OK

    stats = response.json()
    assert isinstance(stats["extractors"], int)


@pytest.mark.asyncio
async def test_maintainers(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/maintainers."""
    response = await api.get("/meltano/api/v1/maintainers", follow_redirects=True)
    assert response.status_code == http.HTTPStatus.OK

    data = response.json()
    maintainer = next(filter(lambda m: m["id"] == "edgarrmondragon", data["maintainers"]))
    assert maintainer["id"] == "edgarrmondragon"
    assert maintainer["url"] == "https://github.com/edgarrmondragon"


@pytest.mark.asyncio
async def test_maintainer_details(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/maintainers."""
    response = await api.get("/meltano/api/v1/maintainers/edgarrmondragon")
    assert response.status_code == http.HTTPStatus.OK

    maintainer = response.json()
    assert maintainer["id"] == "edgarrmondragon"
    assert maintainer["url"] == "https://github.com/edgarrmondragon"
    assert isinstance(maintainer["links"], dict)
    assert len(maintainer["links"]) > 0


@pytest.mark.asyncio
async def test_top_maintainers(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/maintainers."""
    n = 3
    response = await api.get("/meltano/api/v1/maintainers/top", params={"count": n})
    assert response.status_code == http.HTTPStatus.OK

    maintainers = response.json()
    assert len(maintainers) == n


@pytest.mark.asyncio
async def test_default_plugin(api: httpx.AsyncClient) -> None:
    """Test /meltano/api/v1/plugins/extractors/tap-github/default."""
    response = await api.get("/meltano/api/v1/plugins/extractors/tap-github/default")
    assert response.status_code == http.HTTPStatus.TEMPORARY_REDIRECT
    assert response.is_redirect
    assert response.headers["Location"].endswith("extractors/tap-github--meltanolabs")


@pytest.mark.asyncio
async def test_gzip_encoding(api: httpx.AsyncClient) -> None:
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


@pytest.mark.asyncio
async def test_zstd_encoding(api: httpx.AsyncClient) -> None:
    """Test ZSTD encoding."""
    # Large response should be compressed with zstd
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "zstd"})
    assert response.status_code == http.HTTPStatus.OK
    assert response.headers["Content-Encoding"] == "zstd"
    assert response.headers["Content-Type"] == "application/json"
    assert "Vary" in response.headers
    assert "Accept-Encoding" in response.headers["Vary"]

    # Small response should not be compressed
    response = await api.get("/meltano/api/v1/plugins/orchestrators/index", headers={"Accept-Encoding": "zstd"})
    assert response.status_code == http.HTTPStatus.OK
    assert "Content-Encoding" not in response.headers
    assert response.headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_compression_negotiation(api: httpx.AsyncClient) -> None:
    """Test compression algorithm negotiation."""
    # Client accepts both gzip and zstd - should prefer zstd
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "gzip, zstd"})
    assert response.status_code == http.HTTPStatus.OK
    assert response.headers["Content-Encoding"] == "zstd"

    # Client accepts both with different order - should still prefer zstd
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "zstd, gzip"})
    assert response.status_code == http.HTTPStatus.OK
    assert response.headers["Content-Encoding"] == "zstd"

    # Client only accepts gzip
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == http.HTTPStatus.OK
    assert response.headers["Content-Encoding"] == "gzip"

    # Client only accepts zstd
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "zstd"})
    assert response.status_code == http.HTTPStatus.OK
    assert response.headers["Content-Encoding"] == "zstd"


@pytest.mark.asyncio
async def test_no_compression_when_not_accepted(api: httpx.AsyncClient) -> None:
    """Test that no compression is applied when client doesn't support gzip or zstd."""
    # Client accepts only deflate (not supported)
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "deflate"})
    assert response.status_code == http.HTTPStatus.OK
    assert "Content-Encoding" not in response.headers

    # Client accepts only br (not supported)
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "br"})
    assert response.status_code == http.HTTPStatus.OK
    assert "Content-Encoding" not in response.headers

    # Client explicitly disables compression with identity
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "identity"})
    assert response.status_code == http.HTTPStatus.OK
    assert "Content-Encoding" not in response.headers


@pytest.mark.asyncio
async def test_vary_header(api: httpx.AsyncClient) -> None:
    """Test that Vary header is set correctly for caching."""
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "zstd"})
    assert response.status_code == http.HTTPStatus.OK
    assert "Vary" in response.headers
    assert "Accept-Encoding" in response.headers["Vary"]

    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == http.HTTPStatus.OK
    assert "Vary" in response.headers
    assert "Accept-Encoding" in response.headers["Vary"]


@pytest.mark.asyncio
async def test_parse_accept_encoding_edge_cases(api: httpx.AsyncClient) -> None:
    """Test edge cases in Accept-Encoding parsing."""
    # Test with quality factors and mixed encodings (gzip with semicolon in value)
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "gzip, deflate, br"})
    assert response.status_code == http.HTTPStatus.OK
    # Should use gzip since deflate and br are not supported
    assert response.headers.get("Content-Encoding") == "gzip"

    # Test with only zstd in a complex header
    response = await api.get("/meltano/api/v1/plugins/index", headers={"Accept-Encoding": "deflate, zstd, br"})
    assert response.status_code == http.HTTPStatus.OK
    assert response.headers.get("Content-Encoding") == "zstd"


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
    assert compatibility.get_version_tuple(mock_request) == version


def test_openapi_spec(snapshot: SnapshotAssertion) -> None:
    """Test OpenAPI spec."""
    snapshot_json = snapshot.with_defaults(extension_class=JSONSnapshotExtension)
    spec = fastapi.FastAPI.openapi(main.app)
    assert snapshot_json() == spec
