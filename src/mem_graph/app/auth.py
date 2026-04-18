"""FastMCP authentication provider setup."""

from __future__ import annotations

import os

from fastmcp.server.auth import AccessToken, TokenVerifier


class StaticTokenVerifier(TokenVerifier):
    """Validate requests against a static set of bearer tokens."""

    def __init__(self, keys: frozenset[str]) -> None:
        super().__init__(required_scopes=["memory:read", "memory:write"])
        self._keys = keys

    async def verify_token(self, token: str) -> AccessToken | None:
        if token not in self._keys:
            return None
        return AccessToken(
            token=token,
            client_id="local",
            scopes=["memory:read", "memory:write"],
        )


def build_auth_provider() -> StaticTokenVerifier | None:
    raw_keys = os.getenv("MEM_GRAPH_API_KEYS", "").strip()
    if not raw_keys:
        return None
    allowed_keys = frozenset(key.strip() for key in raw_keys.split(",") if key.strip())
    return StaticTokenVerifier(allowed_keys) if allowed_keys else None

