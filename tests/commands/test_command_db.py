from __future__ import annotations

import importlib

import pytest


def _reload_command_db():
    import mem_graph.services.commands.command_db as command_db

    return importlib.reload(command_db)


def _rows(result):
    return result if isinstance(result, list) else result.get_all()


@pytest.mark.asyncio
async def test_db_migrate_and_schema_templates_work_with_fresh_db(db):
    del db
    command_db = _reload_command_db()

    migrate = command_db.db_migrate()
    counts = command_db.db_query_template("schema.counts")
    inspect = command_db.db_inspect(inspect_set="schema")

    assert migrate["ok"] is True
    assert counts["ok"] is True
    assert counts["data"]["rows"][0]["projects"] == 0
    assert inspect["ok"] is True
    assert "bootstrap_status" in inspect["data"]["results"]


@pytest.mark.asyncio
async def test_db_query_template_validates_required_params(db):
    del db
    command_db = _reload_command_db()

    response = command_db.db_query_template("projects.detail", {})

    assert response["ok"] is False
    assert "Missing required param" in response["error"]


@pytest.mark.asyncio
async def test_db_cypher_requires_gate_by_default(db, monkeypatch):
    del db
    command_db = _reload_command_db()
    monkeypatch.delenv("MEM_GRAPH_COMMANDS_ALLOW_RAW_CYPHER", raising=False)

    response = command_db.db_cypher("MATCH (n) RETURN count(n)")

    assert response["ok"] is False
    assert "disabled by default" in response["error"]
