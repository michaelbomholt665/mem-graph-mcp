#!/usr/bin/env python3
# tests/test_parsers.py
"""
tests/test_parsers.py — Integration tests for Tree-sitter Parser Pipeline.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from mem_graph.tools.code.parser import index_code_symbols


@pytest.fixture(autouse=True)
def mock_ollama():
    """Mock Ollama probe to avoid network/service dependency."""
    with patch("mem_graph.db._probe_ollama", return_value=None):
        yield


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Provide a fresh temporary Ladybug database per test."""
    db_path = str(tmp_path / "test_parsers.lbug")
    import mem_graph.db as db_mod

    # Update the module-level constant that was set at import time
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)

    db_mod.db_init_engine()
    yield db_mod.db_get_connection()
    db_mod.db_close_engine()


def test_index_python_sample(db):
    """Verify Python symbol extraction and relationship persistence."""
    root = os.getcwd()
    path = os.path.join(root, "tests/fixtures/tree_sitter/python/sample.py")

    result = index_code_symbols(root=root, path=path)

    assert result["success"] is True
    assert result["files_written"] == 1
    assert result["symbols_written"] > 10
    assert result["batches_committed"] == 1
    assert result["batches_rolled_back"] == 0

    # Verify nodes
    conn = db
    res = conn.execute("MATCH (s:CodeSymbol) RETURN count(s)").get_all()
    assert res[0][0] == result["symbols_written"]

    # Verify Class 'Animal'
    res = conn.execute(
        "MATCH (s:CodeSymbol {name: 'Animal', kind: 'class'}) RETURN s.qualified_name"
    ).get_all()
    assert len(res) == 1
    assert res[0][0] == "Animal"

    # Verify Inheritance: Dog EXTENDS Animal
    res = conn.execute(
        """
        MATCH (d:CodeSymbol {name: 'Dog'})-[:EXTENDS]->(a:CodeSymbol {name: 'Animal'})
        RETURN count(*)
        """
    ).get_all()
    assert res[0][0] == 1

    # Verify Method: speak in Dog
    res = conn.execute(
        "MATCH (s:CodeSymbol {name: 'speak', parent_id: $pid}) RETURN s",
        {"pid": conn.execute("MATCH (s:CodeSymbol {name: 'Dog'}) RETURN s.id").get_all()[0][0]},
    ).get_all()
    assert len(res) == 1

    # Verify Calls: Repository.find_by_id CALLS db.query
    # Note: the resolver might only resolve to names if the target isn't in the same file,
    # but here 'query' is in DbProtocol in the same file.
    res = conn.execute(
        """
        MATCH (s:CodeSymbol {name: 'find_by_id'})-[:CALLS]->(target:CodeSymbol)
        RETURN target.name
        """
    ).get_all()
    names = [row[0] for row in res]
    assert "query" in names


def test_index_typescript_sample(db):
    """Verify TypeScript symbol extraction and relationship persistence."""
    root = os.getcwd()
    path = os.path.join(root, "tests/fixtures/tree_sitter/typescript/sample.ts")

    result = index_code_symbols(root=root, path=path)

    assert result["success"] is True
    assert result["files_written"] == 1
    assert result["symbols_written"] > 10

    conn = db

    # Verify Interface 'Animal'
    res = conn.execute(
        "MATCH (s:CodeSymbol {name: 'Animal', kind: 'interface'}) RETURN s"
    ).get_all()
    assert len(res) == 1

    # Verify Implementation: Dog IMPLEMENTS_SYMBOL Animal
    res = conn.execute(
        """
        MATCH (d:CodeSymbol {name: 'Dog'})-[:IMPLEMENTS_SYMBOL]->(a:CodeSymbol {name: 'Animal'})
        RETURN count(*)
        """
    ).get_all()
    assert res[0][0] == 1

    # Verify Imports
    # sample.ts imports readFile from node:fs/promises
    # The current extractor creates a CodeSymbol for the import itself
    res = conn.execute(
        "MATCH (s:CodeSymbol {kind: 'import'}) RETURN s.name"
    ).get_all()
    names = [row[0] for row in res]
    assert "readFile" in names


def test_transaction_rollback_on_failure(db, monkeypatch):
    """Verify that a failure in one part of the batch rolls back everything."""
    root = os.getcwd()
    path = os.path.join(root, "tests/fixtures/tree_sitter/python/sample.py")

    # Monkeypatch _ingest_edges to fail
    from mem_graph.app.parsers import ingest

    def mock_ingest_edges(*args, **kwargs):
        raise RuntimeError("Simulated edge ingest failure")

    monkeypatch.setattr(ingest, "_ingest_edges", mock_ingest_edges)

    result = index_code_symbols(root=root, path=path)

    assert result["success"] is False
    assert result["batches_rolled_back"] == 1
    assert any("Simulated edge ingest failure" in e for e in result["errors"])

    # Verify DB is empty (nothing should have been committed)
    conn = db
    res = conn.execute("MATCH (n:CodeFile) RETURN count(n)").get_all()
    assert res[0][0] == 0
    res = conn.execute("MATCH (n:CodeSymbol) RETURN count(n)").get_all()
    assert res[0][0] == 0
