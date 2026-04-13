#!/usr/bin/env python3
# tests/test_tools.py
"""
tests/test_tools.py — Round-trip tests for all tool modules.

Runs against a real Ladybug DB with deterministic embeddings supplied by conftest.
No Ollama or network required.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest


@pytest.fixture()
async def conn(tmp_path):
    """Fresh DB with deterministic embeddings supplied by the global fixture."""
    import importlib

    os.environ["LADYBUG_DB_PATH"] = str(tmp_path / "test.lbug")
    os.environ["OLLAMA_EMBED_DIM"] = "768"

    import mem_graph.db as db_mod

    importlib.reload(db_mod)

    with patch.object(db_mod, "_probe_ollama", lambda: None):
        db_mod.db_init_engine()
        yield db_mod.db_get_connection()
        db_mod.db_close_engine()


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_create_and_get(conn):
    from mem_graph.tools.work.projects import project_create, project_get, project_list

    result = await project_create(name="Acme", description="Test project")
    pid = result["project_id"]
    assert pid

    got = await project_get(project_id=pid)
    assert got["project"]["name"] == "Acme"
    assert got["project"]["status"] == "active"

    listing = await project_list()
    ids = [p["id"] for p in listing["projects"]]
    assert pid in ids


@pytest.mark.asyncio
async def test_project_get_missing(conn):
    from mem_graph.tools.work.projects import project_get

    result = await project_get(project_id="does-not-exist")
    assert "error" in result


# ---------------------------------------------------------------------------
# memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_store_and_list(conn):
    from mem_graph.tools.memory.memory import memory_store, memory_manage

    r = await memory_store(
        content="Python prefers explicit over implicit", kind="preference", conn=conn
    )
    mid = r["memory_id"]
    assert mid

    listing = await memory_manage(action="list", scope="global", conn=conn)
    ids = [m["id"] for m in listing["memories"]]
    assert mid in ids

    # Expire it
    exp = await memory_manage(action="expire", memory_id=mid, conn=conn)
    assert exp["status"] == "expired"

    # Should no longer appear in list
    listing2 = await memory_manage(action="list", scope="global", conn=conn)
    ids2 = [m["id"] for m in listing2["memories"]]
    assert mid not in ids2


@pytest.mark.asyncio
async def test_memory_store_with_project(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.memory.memory import memory_store, memory_manage

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    await memory_store(content="fact", kind="fact", scope="project", project_id=pid, conn=conn)

    listing = await memory_manage(action="list", scope="project", project_id=pid, conn=conn)
    assert len(listing["memories"]) == 1
    assert listing["memories"][0]["scope"] == "project"


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_create_update_get(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.tasks import task_create, task_update, task_get

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    t = await task_create(project_id=pid, title="Fix bug", description="crash on null")
    tid = t["task_id"]
    assert tid

    await task_update(task_id=tid, status="in_progress", priority="high")

    got = await task_get(task_id=tid)
    assert got["task"]["status"] == "in_progress"
    assert got["task"]["priority"] == "high"


@pytest.mark.asyncio
async def test_task_block(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.tasks import task_create, task_block, task_get

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    t1 = await task_create(project_id=pid, title="Task A", description="first")
    t2 = await task_create(project_id=pid, title="Task B", description="second")

    await task_block(
        task_id=t2["task_id"], blocked_by_task_id=t1["task_id"], reason="Depends on A"
    )

    got = await task_get(task_id=t2["task_id"])
    blocker_ids = [b["id"] for b in got["task"]["blocked_by"]]
    assert t1["task_id"] in blocker_ids


@pytest.mark.asyncio
async def test_task_done_sets_completed_at(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.tasks import task_create, task_update, task_get

    proj = await project_create(name="P", description="d")
    t = await task_create(project_id=proj["project_id"], title="T", description="d")
    await task_update(task_id=t["task_id"], status="done")

    got = await task_get(task_id=t["task_id"])
    assert got["task"]["completed_at"] is not None


# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decision_record_and_supersede(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.decisions import (
        decision_record,
        decision_supersede,
        decision_get,
    )

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    old = await decision_record(project_id=pid, title="Use SQLite", rationale="simple")
    new = await decision_record(
        project_id=pid, title="Use Ladybug", rationale="graph native"
    )

    await decision_supersede(
        old_id=old["decision_id"], new_id=new["decision_id"], reason="better fit"
    )

    got_old = await decision_get(decision_id=old["decision_id"])
    assert got_old["decision"]["status"] == "superseded"

    got_new = await decision_get(decision_id=new["decision_id"])
    superseded_ids = [d["id"] for d in got_new["decision"]["supersedes"]]
    assert old["decision_id"] in superseded_ids


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_note_create_and_list(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.memory.notes import note_create, note_list

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    r = await note_create(
        content="Remember to add tests",
        kind="warning",
        project_id=pid,
        tags=["testing"],
    )
    nid = r["note_id"]
    assert nid

    listing = await note_list(project_id=pid)
    ids = [n["id"] for n in listing["notes"]]
    assert nid in ids

    # Filter by kind
    filtered = await note_list(project_id=pid, kind="warning")
    assert all(n["kind"] == "warning" for n in filtered["notes"])


# ---------------------------------------------------------------------------
# violations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_violation_record_and_resolve(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.violations import (
        violation_record,
        violation_resolve,
        violation_list,
    )

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    v = await violation_record(
        project_id=pid,
        audit_id="001A",
        rule="CWE-252",
        severity="major",
        file_path="src/main.py",
        description="Unchecked return value",
    )
    vid = v["violation_id"]
    assert vid

    await violation_resolve(violation_id=vid)

    listing = await violation_list(project_id=pid, status="resolved")
    ids = [v["id"] for v in listing["violations"]]
    assert vid in ids


@pytest.mark.asyncio
async def test_violation_recur(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.violations import (
        violation_record,
        violation_resolve,
        violation_recur,
        violation_list,
    )

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    orig = await violation_record(
        project_id=pid,
        audit_id="001A",
        rule="CWE-252",
        severity="minor",
        file_path="a.py",
        description="original",
    )
    await violation_resolve(violation_id=orig["violation_id"])

    recur = await violation_recur(
        original_id=orig["violation_id"],
        new_description="Same issue reappeared in refactor",
    )
    rid = recur["violation_id"]
    assert rid != orig["violation_id"]
    assert recur["original_id"] == orig["violation_id"]

    # New violation should be scoped to same project
    listing = await violation_list(project_id=pid, status="recurrence")
    ids = [v["id"] for v in listing["violations"]]
    assert rid in ids


# ---------------------------------------------------------------------------
# conversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_capture_session_and_recall(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools import conversation as conv_mod
    
    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    from mem_graph.models.conversation import ConversationMessage

    messages = [
        ConversationMessage(role="user", content="How do I build a graph?"),
        ConversationMessage(role="assistant", content="You use nodes and edges.")
    ]

    with patch("mem_graph.tools.memory.conversation.enqueue_summary") as mock_enqueue:
        res = await conv_mod.memory_capture_session(
            project_id=pid,
            messages=messages,
            agent_name="test-agent",
            model="test-model"
        )
        assert res.session_id is not None
        assert res.turn_count == 2
        mock_enqueue.assert_called_once()


# ---------------------------------------------------------------------------
# cross-module: task links
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_link_decision_and_violation(conn):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.work.tasks import (
        task_create,
        task_link_decision,
        task_link_violation,
        task_get,
    )
    from mem_graph.tools.work.decisions import decision_record
    from mem_graph.tools.work.violations import violation_record

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    t = await task_create(project_id=pid, title="T", description="d")
    d = await decision_record(project_id=pid, title="D", rationale="r")
    v = await violation_record(
        project_id=pid,
        audit_id="x",
        rule="r",
        severity="info",
        file_path="f.py",
        description="desc",
    )

    await task_link_decision(task_id=t["task_id"], decision_id=d["decision_id"])
    await task_link_violation(task_id=t["task_id"], violation_id=v["violation_id"])

    got = await task_get(task_id=t["task_id"])
    decision_ids = [x["id"] for x in got["task"]["decisions"]]
    violation_ids = [x["id"] for x in got["task"]["violations"]]

    assert d["decision_id"] in decision_ids
    assert v["violation_id"] in violation_ids

# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_package_tool(conn, tmp_path):
    from mem_graph.tools.work.projects import project_create
    from mem_graph.tools.agents.audit import audit_package
    from mem_graph.tools.background.task_status import get_task_status
    from mem_graph.models.audit import AuditReport, AuditStats

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    # Mock the _run_agent to avoid running the real AI model
    from unittest.mock import patch
    import mem_graph.tools.agents.audit as audit_tool_mod

    stats = AuditStats(
        total_files_analysed=1, total_files_skipped=0, total_findings=0,
        by_severity={}, by_category={}, blocker_count=0, critical_count=0
    )
    mock_report = AuditReport(
        package_path=str(tmp_path), summary="Clean.", file_results=[], stats=stats, rules_applied=["rule1"]
    )

    with patch.object(audit_tool_mod, "_run_agent", return_value=mock_report):
        # Ensure the package path exists so the audit worker proceeds.
        package_dir = tmp_path / "package"
        package_dir.mkdir()

        result = await audit_package(
            package_path=str(package_dir),
            project_id=pid,
            persist_violations=True,
        )

        assert result["status"] in {"queued", "running"}
        assert result["tool"] == "audit_package"

        async def wait_for_completion():
            while True:
                status = await get_task_status(result["task_id"])
                if status["status"] == "completed":
                    return status
                await asyncio.sleep(0.01)

        status = await asyncio.wait_for(wait_for_completion(), timeout=2.0)

    assert status["result"]["status"] == "completed"
    assert status["result"]["summary"] == "Clean."
    assert status["result"]["total_findings"] == 0

