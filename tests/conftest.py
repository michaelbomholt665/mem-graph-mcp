#!/usr/bin/env python3
# tests/conftest.py
"""Shared pytest fixtures for deterministic, offline test runs."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# Point at a temp DB before any module-level code reads env
os.environ.setdefault("OLLAMA_EMBED_DIM", "768")
os.environ.setdefault("OLLAMA_EMBED_MODEL", "nomic-embed-text")

import mem_graph.embeddings as emb


@pytest.fixture()
async def db(tmp_path):
    """Initialise a fresh Ladybug DB for each test, patch Ollama away."""
    db_path = str(tmp_path / "test.lbug")
    os.environ["LADYBUG_DB_PATH"] = db_path

    # Re-import to pick up the patched env var
    import importlib
    import mem_graph.db as db_mod

    importlib.reload(db_mod)

    with patch.object(db_mod, "_probe_ollama", lambda: None):
        db_mod.db_init_engine()
        yield db_mod.db_get_connection()
        db_mod.db_close_engine()


@pytest.fixture(autouse=True)
def deterministic_embeddings():
    """Replace embedding generation with a deterministic in-process test hook."""
    emb._embed_override = lambda text: [0.0] * emb.EMBED_DIM
    yield
    emb._embed_override = None
    emb.clear_cache()
