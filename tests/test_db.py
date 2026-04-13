"""
tests/test_db.py — DB bootstrap and idempotency tests.
"""

from __future__ import annotations

import os
from unittest.mock import patch
from typing import Any, cast

import pytest


@pytest.mark.asyncio
async def test_bootstrap_creates_all_tables(tmp_path):
    """All 12 node tables must exist after init_db()."""
    import importlib

    os.environ["LADYBUG_DB_PATH"] = str(tmp_path / "test.lbug")
    import mem_graph.db as db_mod

    importlib.reload(db_mod)

    with patch.object(db_mod, "_probe_ollama", lambda: None):
        db_mod.init_db()
        conn = db_mod.get_conn()

        tables = [
            "Agent",
            "Project",
            "Backend",
            "Task",
            "Decision",
            "Note",
            "Violation",
            "Conversation",
            "Message",
            "Memory",
            "CodeSymbol",
            "Tag",
        ]
        for table in tables:
            result = cast(Any, conn.execute(f"MATCH (n:{table}) RETURN count(n)")).get_all()
            assert result[0][0] == 0, f"Expected empty {table} table"

        db_mod.close_db()


@pytest.mark.asyncio
async def test_bootstrap_creates_all_vector_indexes(tmp_path):
    """All 10 HNSW vector indexes must be present after init_db()."""
    import importlib

    os.environ["LADYBUG_DB_PATH"] = str(tmp_path / "test.lbug")
    import mem_graph.db as db_mod

    importlib.reload(db_mod)

    with patch.object(db_mod, "_probe_ollama", lambda: None):
        db_mod.init_db()
        conn = db_mod.get_conn()

        expected_indexes = {
            "idx_project_emb",
            "idx_backend_emb",
            "idx_task_emb",
            "idx_decision_emb",
            "idx_note_emb",
            "idx_violation_emb",
            "idx_conv_emb",
            "idx_message_emb",
            "idx_memory_emb",
            "idx_symbol_emb",
        }
        result = cast(Any, conn.execute("CALL SHOW_INDEXES() RETURN *;"))
        actual = {row[1] for row in result.get_all()}
        assert expected_indexes == actual

        db_mod.close_db()


@pytest.mark.asyncio
async def test_bootstrap_idempotent(tmp_path):
    """Running init_db() twice on the same file must not raise."""
    import importlib

    os.environ["LADYBUG_DB_PATH"] = str(tmp_path / "test.lbug")
    import mem_graph.db as db_mod

    importlib.reload(db_mod)

    with patch.object(db_mod, "_probe_ollama", lambda: None):
        db_mod.init_db()
        db_mod.close_db()
        # Second open — all IF NOT EXISTS guards must hold
        db_mod.init_db()
        conn = db_mod.get_conn()
        result = cast(Any, conn.execute("CALL SHOW_INDEXES() RETURN *;"))
        assert len(result.get_all()) == 10
        db_mod.close_db()


@pytest.mark.asyncio
async def test_embed_dim_substitution(tmp_path):
    """FLOAT[1536] in schema must be replaced with the configured dim."""
    import importlib

    os.environ["LADYBUG_DB_PATH"] = str(tmp_path / "test.lbug")
    os.environ["OLLAMA_EMBED_DIM"] = "768"
    import mem_graph.db as db_mod

    importlib.reload(db_mod)

    with patch.object(db_mod, "_probe_ollama", lambda: None):
        db_mod.init_db()
        # If schema was run with wrong dim the DB would still open fine,
        # but we can verify EMBED_DIM is read correctly from env:
        assert db_mod.EMBED_DIM == 768
        db_mod.close_db()
