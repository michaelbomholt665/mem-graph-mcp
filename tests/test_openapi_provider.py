"""
tests/test_openapi_provider.py — Unit tests for the OpenAPI provider builder.

build_openapi_provider is async (it fetches the spec over HTTP), so tests
mock fetch_spec rather than OpenAPIProvider directly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mem_graph.providers.openapi import build_openapi_provider


_FAKE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0"},
    "paths": {},
}


@pytest.mark.asyncio
async def test_build_openapi_provider_calls_provider_with_spec():
    mock_provider = MagicMock()
    with (
        patch("mem_graph.providers.openapi.fetch_spec", new=AsyncMock(return_value=_FAKE_SPEC)),
        patch("mem_graph.providers.openapi.OpenAPIProvider", return_value=mock_provider) as mock_cls,
    ):
        result = await build_openapi_provider("https://api.example.com/openapi.json")

    mock_cls.assert_called_once()
    call_args = mock_cls.call_args
    # First positional arg must be the spec dict
    assert call_args[0][0] == _FAKE_SPEC
    assert result is mock_provider


@pytest.mark.asyncio
async def test_build_openapi_provider_passes_client():
    """An httpx.AsyncClient is wired as the `client` kwarg."""
    mock_provider = MagicMock()
    with (
        patch("mem_graph.providers.openapi.fetch_spec", new=AsyncMock(return_value=_FAKE_SPEC)),
        patch("mem_graph.providers.openapi.OpenAPIProvider", return_value=mock_provider) as mock_cls,
    ):
        await build_openapi_provider("https://api.example.com/openapi.json")

    call_kwargs = mock_cls.call_args[1]
    assert "client" in call_kwargs
    assert call_kwargs["client"] is not None


@pytest.mark.asyncio
async def test_build_openapi_provider_fetches_correct_url():
    """fetch_spec is called with the URL as-is."""
    fetch_mock = AsyncMock(return_value=_FAKE_SPEC)
    with (
        patch("mem_graph.providers.openapi.fetch_spec", new=fetch_mock),
        patch("mem_graph.providers.openapi.OpenAPIProvider", return_value=MagicMock()),
    ):
        await build_openapi_provider("https://api.example.com/v2/spec.json")

    fetch_mock.assert_awaited_once_with("https://api.example.com/v2/spec.json")
