"""
conftest.py — shared pytest fixtures.

All tests use a temporary in-memory Ladybug DB with Ollama probing and
embedding patched out so the suite runs without any external services.
Embedding calls return deterministic 768-dim zero vectors.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

# Point at a temp DB before any module-level code reads env
os.environ.setdefault("OLLAMA_EMBED_DIM", "768")
os.environ.setdefault("OLLAMA_EMBED_MODEL", "nomic-embed-text")


@pytest.fixture()
async def db(tmp_path):
    """Initialise a fresh Ladybug DB for each test, patch Ollama away."""
    db_path = str(tmp_path / "test.lbug")
    os.environ["LADYBUG_DB_PATH"] = db_path

    # Re-import to pick up the patched env var
    import importlib
    import syntx_mcp.db as db_mod

    importlib.reload(db_mod)

    fake_embed = AsyncMock(return_value=[0.0] * 768)

    with (
        patch.object(db_mod, "_probe_ollama", lambda: None),
        patch("syntx_mcp.tools.conversation.embed", fake_embed),
        patch("syntx_mcp.tools.memory.embed", fake_embed),
        patch("syntx_mcp.tools.projects.embed", fake_embed),
        patch("syntx_mcp.tools.tasks.embed", fake_embed),
        patch("syntx_mcp.tools.decisions.embed", fake_embed),
        patch("syntx_mcp.tools.notes.embed", fake_embed),
        patch("syntx_mcp.tools.violations.embed", fake_embed),
    ):
        db_mod.init_db()
        yield db_mod.get_conn()
        db_mod.close_db()
