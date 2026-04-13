from __future__ import annotations

from starlette.testclient import TestClient
import pytest


@pytest.mark.asyncio
async def test_get_server_info_matches_runtime_metadata():
    from mem_graph import __version__
    from mem_graph import server as server_mod

    payload = await server_mod.get_server_info()

    assert payload == {
        "name": server_mod.SERVER_NAME,
        "version": __version__,
        "api_version": server_mod.SERVER_API_VERSION,
        "website": server_mod.SERVER_WEBSITE,
    }


def test_info_route_returns_server_metadata():
    from mem_graph import server as server_mod

    app = server_mod.build_http_app(with_lifespan=False)
    with TestClient(app) as client:
        response = client.get("/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": server_mod.SERVER_NAME,
        "version": server_mod.SERVER_VERSION,
        "api_version": server_mod.SERVER_API_VERSION,
        "website": server_mod.SERVER_WEBSITE,
    }