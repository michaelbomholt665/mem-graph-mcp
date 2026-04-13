"""
providers/openapi.py — FastMCP OpenAPIProvider builder.

Fetches an OpenAPI spec from a URL, then constructs an OpenAPIProvider
that generates MCP tools from it — one tool per endpoint.

Security note: requires fastmcp>=3.2.3 (patched for CVE-2026-32871).
Do not ingest raw, unfiltered specs in production — strip admin and
DELETE routes from the spec file before pointing at it.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx
from fastmcp.server.providers.openapi import OpenAPIProvider  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


async def fetch_spec(spec_url: str) -> dict[str, Any]:
    """Download and return the OpenAPI spec JSON from ``spec_url``."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(spec_url)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())


async def build_openapi_provider(spec_url: str) -> OpenAPIProvider:
    """
    Fetch an OpenAPI spec and construct an OpenAPIProvider from it.

    Downloads the JSON spec at ``spec_url``, passes it to
    ``OpenAPIProvider``, and uses a shared ``httpx.AsyncClient`` for
    all generated tool calls (kept open for the provider's lifetime).

    Parameters
    ----------
    spec_url:
        Full URL to the OpenAPI JSON spec, e.g.
        ``https://api.example.com/openapi.json``.
    """
    logger.debug("Fetching OpenAPI spec from %s", spec_url)
    spec = await fetch_spec(spec_url)

    client = httpx.AsyncClient(timeout=30.0)
    logger.debug("Building OpenAPI provider from spec at %s", spec_url)
    return OpenAPIProvider(spec, client=client)
