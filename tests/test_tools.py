"""
tests/test_tools.py — Round-trip tests for all tool modules.

Runs against a real Ladybug DB with embed() patched to return zero-vectors.
No Ollama or network required.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_VEC = [0.0] * 768
_EMBED_PATCH = AsyncMock(return_value=FAKE_VEC)

EMBED_TARGETS = [
    "syntx_mcp.tools.conversation.embed",
    "syntx_mcp.tools.memory.embed",
    "syntx_mcp.tools.projects.embed",
    "syntx_mcp.tools.tasks.embed",
    "syntx_mcp.tools.decisions.embed",
    "syntx_mcp.tools.notes.embed",
    "syntx_mcp.tools.violations.embed",
]


@pytest.fixture()
async def conn(tmp_path):
    """Fresh DB + all embed() calls patched out."""
    import importlib

    os.environ["LADYBUG_DB_PATH"] = str(tmp_path / "test.lbug")
    os.environ["OLLAMA_EMBED_DIM"] = "768"

    import syntx_mcp.db as db_mod

    importlib.reload(db_mod)

    fake_embed = AsyncMock(return_value=FAKE_VEC)
    patches = [patch(t, fake_embed) for t in EMBED_TARGETS]

    with patch.object(db_mod, "_probe_ollama", lambda: None):
        for p in patches:
            p.start()
        db_mod.init_db()
        yield db_mod.get_conn()
        db_mod.close_db()
        for p in patches:
            p.stop()


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_create_and_get(conn):
    from syntx_mcp.tools.projects import project_create, project_get, project_list

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
    from syntx_mcp.tools.projects import project_get

    result = await project_get(project_id="does-not-exist")
    assert "error" in result


# ---------------------------------------------------------------------------
# memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_store_and_list(conn):
    from syntx_mcp.tools.memory import memory_store, memory_list, memory_expire

    r = await memory_store(
        content="Python prefers explicit over implicit", kind="preference"
    )
    mid = r["memory_id"]
    assert mid

    listing = await memory_list()
    ids = [m["id"] for m in listing["memories"]]
    assert mid in ids

    # Expire it
    exp = await memory_expire(memory_id=mid)
    assert exp["status"] == "expired"

    # Should no longer appear in list
    listing2 = await memory_list()
    ids2 = [m["id"] for m in listing2["memories"]]
    assert mid not in ids2


@pytest.mark.asyncio
async def test_memory_store_with_project(conn):
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools.memory import memory_store, memory_list

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    await memory_store(content="fact", kind="fact", scope="project", project_id=pid)

    listing = await memory_list(project_id=pid)
    assert len(listing["memories"]) == 1
    assert listing["memories"][0]["scope"] == "project"


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_create_update_get(conn):
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools.tasks import task_create, task_update, task_get

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
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools.tasks import task_create, task_block, task_get

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
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools.tasks import task_create, task_update, task_get

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
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools.decisions import (
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
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools.notes import note_create, note_list

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
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools.violations import (
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
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools.violations import (
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
async def test_conversation_start_append_get(conn):
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools import conversation as conv_mod

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    started = await conv_mod.conversation_start(
        project_id=pid, agent_name="test-agent", model="claude-test"
    )
    cid = started["conversation_id"]
    assert cid

    m1 = await conv_mod.conversation_append(
        conversation_id=cid, role="user", content="Hello!"
    )
    m2 = await conv_mod.conversation_append(
        conversation_id=cid, role="assistant", content="Hi there!"
    )

    assert m1["position"] == 0
    assert m2["position"] == 1

    got = await conv_mod.conversation_get(conversation_id=cid)
    assert got["conversation"]["turn_count"] == 2
    assert len(got["messages"]) == 2
    assert got["messages"][0]["role"] == "user"
    assert got["messages"][1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_conversation_end_generates_summary(conn):
    """conversation_end must set summary and ended_at even when Ollama summariser fails."""
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools import conversation as conv_mod

    proj = await project_create(name="P", description="d")
    pid = proj["project_id"]

    started = await conv_mod.conversation_start(
        project_id=pid, agent_name="a", model="m"
    )
    cid = started["conversation_id"]
    await conv_mod.conversation_append(conversation_id=cid, role="user", content="test")

    # Patch _generate_summary to avoid real Ollama call
    with patch(
        "syntx_mcp.tools.conversation._generate_summary", return_value="Test summary"
    ):
        ended = await conv_mod.conversation_end(conversation_id=cid)

    assert ended["summary"] == "Test summary"

    got = await conv_mod.conversation_get(conversation_id=cid)
    assert got["conversation"]["summary"] == "Test summary"
    assert got["conversation"]["ended_at"] is not None


# ---------------------------------------------------------------------------
# cross-module: task links
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_link_decision_and_violation(conn):
    from syntx_mcp.tools.projects import project_create
    from syntx_mcp.tools.tasks import (
        task_create,
        task_link_decision,
        task_link_violation,
        task_get,
    )
    from syntx_mcp.tools.decisions import decision_record
    from syntx_mcp.tools.violations import violation_record

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
