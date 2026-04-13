"""
auth.py — API key authentication skeleton.

When ``MEM_GRAPH_API_KEYS`` env var is set (comma-separated list of allowed
keys), the ``require_api_key`` middleware rejects requests with a 401 if the
``Authorization: Bearer <key>`` header is missing or invalid.

When ``MEM_GRAPH_API_KEYS`` is *unset*, all requests pass through unchanged —
preserving current local-only behaviour.

WARNING: This is transport-level only.  For production deployments beyond
localhost, network isolation (firewall, VPN) is still required.
"""

from __future__ import annotations

import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_RAW_KEYS = os.getenv("MEM_GRAPH_API_KEYS", "").strip()
_ALLOWED_KEYS: frozenset[str] = (
    frozenset(k.strip() for k in _RAW_KEYS.split(",") if k.strip())
    if _RAW_KEYS
    else frozenset()
)

AUTH_ENABLED: bool = bool(_ALLOWED_KEYS)


def verify_api_key(key: str) -> bool:
    """Return True if the key is in the allowed set (or auth is disabled)."""
    if not AUTH_ENABLED:
        return True
    return key in _ALLOWED_KEYS


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that enforces Bearer token authentication.

    Only wired into the app when ``MEM_GRAPH_API_KEYS`` is set.
    Health endpoint (``/health``) is exempted so monitoring tools don't
    need credentials.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Always allow health checks unauthenticated.
        if request.url.path == "/health":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Unauthorized — Bearer token required"},
                status_code=401,
            )
        key = auth_header.removeprefix("Bearer ").strip()
        if not verify_api_key(key):
            logger.warning("Rejected request with invalid API key from %s", request.client)
            return JSONResponse(
                {"error": "Unauthorized — invalid API key"},
                status_code=401,
            )
        return await call_next(request)
