"""
tools/tasks.py — Task management tools.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ..db import get_conn
from ..embeddings import embed

mcp = FastMCP("tasks")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


@mcp.tool(tags={"namespace:task"})
async def task_create(
    project_id: Annotated[str, Field(description="Owning project ID")],
    title: Annotated[str, Field(description="Short task title")],
    description: Annotated[str, Field(description="Full task description")],
    priority: Annotated[
        str,
        Field(description="Priority: low | normal | high | critical"),
    ] = "normal",
    backend_id: Annotated[
        str | None, Field(description="Optional backend ID to associate the task with")
    ] = None,
) -> dict:
    """
    Create a new task under a project.

    Embeds title + description for semantic search.
    Returns the new task_id.
    """
    conn = get_conn()
    task_id = _new_id()
    vec = await embed(f"{title}\n{description}")

    conn.execute(
        """
        CREATE (t:Task {
            id: $id,
            title: $title,
            description: $description,
            status: 'open',
            priority: $priority,
            embedding: $embedding,
            created_at: $ts,
            updated_at: $ts
        })
        """,
        {
            "id": task_id,
            "title": title,
            "description": description,
            "priority": priority,
            "embedding": vec,
            "ts": _now(),
        },
    )

    # Link project → task
    conn.execute(
        """
        MATCH (p:Project {id: $project_id}), (t:Task {id: $task_id})
        CREATE (p)-[:HAS_TASK]->(t)
        """,
        {"project_id": project_id, "task_id": task_id},
    )

    # Optionally link backend → task
    if backend_id:
        conn.execute(
            """
            MATCH (b:Backend {id: $backend_id}), (t:Task {id: $task_id})
            CREATE (b)-[:BACKEND_TASK]->(t)
            """,
            {"backend_id": backend_id, "task_id": task_id},
        )

    return {"task_id": task_id}


@mcp.tool()
async def task_update(
    task_id: Annotated[str, Field(description="Task ID to update")],
    status: Annotated[
        str | None,
        Field(
            description="New status: open | in_progress | blocked | done | cancelled"
        ),
    ] = None,
    phase: Annotated[
        str | None,
        Field(description="New phase: planning | red | green | refactor | audit"),
    ] = None,
    priority: Annotated[
        str | None,
        Field(description="New priority: low | normal | high | critical"),
    ] = None,
) -> dict:
    """
    Update task status, phase, and/or priority.

    Only provided fields are changed.  Sets updated_at and completed_at
    when status transitions to 'done'.
    """
    conn = get_conn()
    ts = _now()

    set_clauses: list[str] = ["t.updated_at = $ts"]
    params: dict = {"id": task_id, "ts": ts}

    if status is not None:
        set_clauses.append("t.status = $status")
        params["status"] = status
        if status == "done":
            set_clauses.append("t.completed_at = $ts")

    if phase is not None:
        set_clauses.append("t.phase = $phase")
        params["phase"] = phase

    if priority is not None:
        set_clauses.append("t.priority = $priority")
        params["priority"] = priority

    conn.execute(
        f"""
        MATCH (t:Task {{id: $id}})
        SET {", ".join(set_clauses)}
        """,
        params,
    )

    return {"task_id": task_id, "ok": True}


@mcp.tool(tags={"namespace:task"})
async def task_get(
    task_id: Annotated[str, Field(description="Task ID to retrieve")],
) -> dict:
    """Return a task node with its linked decisions and violations."""
    conn = get_conn()

    result = conn.execute(
        """
        MATCH (t:Task {id: $id})
        RETURN t.id, t.title, t.description, t.status, t.priority,
               t.phase, t.created_at, t.updated_at, t.completed_at
        """,
        {"id": task_id},
    )
    rows = cast(list[list[Any]], result)
    if not rows:
        return {"error": f"Task {task_id!r} not found"}

    r = rows[0]
    task: dict[str, Any] = {
        "id": r[0],
        "title": r[1],
        "description": r[2],
        "status": r[3],
        "priority": r[4],
        "phase": r[5],
        "created_at": str(r[6]),
        "updated_at": str(r[7]),
        "completed_at": str(r[8]) if r[8] else None,
    }

    # Linked decisions
    d_result = conn.execute(
        """
        MATCH (t:Task {id: $id})-[:TASK_DECISION]->(d:Decision)
        RETURN d.id, d.title
        """,
        {"id": task_id},
    )
    task["decisions"] = [{"id": r[0], "title": r[1]} for r in cast(list[list[Any]], d_result)]

    # Linked violations
    v_result = conn.execute(
        """
        MATCH (t:Task {id: $id})-[:TASK_VIOLATION]->(v:Violation)
        RETURN v.id, v.rule, v.severity
        """,
        {"id": task_id},
    )
    task["violations"] = [
        {"id": r[0], "rule": r[1], "severity": r[2]} for r in cast(list[list[Any]], v_result)
    ]

    # Blocking tasks
    b_result = conn.execute(
        """
        MATCH (blocker:Task)-[:TASK_BLOCKS]->(t:Task {id: $id})
        RETURN blocker.id, blocker.title
        """,
        {"id": task_id},
    )
    task["blocked_by"] = [{"id": r[0], "title": r[1]} for r in cast(list[list[Any]], b_result)]

    return {"task": task}


@mcp.tool()
async def task_search(
    query: Annotated[str, Field(description="Natural language search query")],
    project_id: Annotated[
        str | None, Field(description="Scope search to a project")
    ] = None,
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 10,
) -> dict:
    """Semantic search over tasks by title+description similarity."""
    conn = get_conn()
    vec = await embed(query)

    result = conn.execute(
        f"""
        CALL QUERY_VECTOR_INDEX('Task', 'idx_task_emb', $qvec, {limit * 3})
        WITH node AS t, distance
        OPTIONAL MATCH (p:Project)-[:HAS_TASK]->(t)
        RETURN t.id, t.title, t.status, t.priority, p.id AS project_id, distance
        ORDER BY distance
        LIMIT {limit * 3}
        """,
        {"qvec": vec},
    )

    tasks = []
    for r in cast(list[list[Any]], result):
        if project_id and r[4] != project_id:
            continue
        tasks.append(
            {
                "id": r[0],
                "title": r[1],
                "status": r[2],
                "priority": r[3],
                "project_id": r[4],
                "distance": r[5],
            }
        )
        if len(tasks) >= limit:
            break

    return {"tasks": tasks, "query": query}


@mcp.tool(tags={"namespace:task"})
async def task_link_decision(
    task_id: Annotated[str, Field(description="Task ID")],
    decision_id: Annotated[str, Field(description="Decision ID to link")],
) -> dict:
    """Link a task to a decision via TASK_DECISION relationship."""
    conn = get_conn()
    conn.execute(
        """
        MATCH (t:Task {id: $task_id}), (d:Decision {id: $decision_id})
        MERGE (t)-[:TASK_DECISION]->(d)
        """,
        {"task_id": task_id, "decision_id": decision_id},
    )
    return {"ok": True}


@mcp.tool(tags={"namespace:task"})
async def task_link_violation(
    task_id: Annotated[str, Field(description="Task ID")],
    violation_id: Annotated[str, Field(description="Violation ID to link")],
) -> dict:
    """Link a task to a violation via TASK_VIOLATION relationship."""
    conn = get_conn()
    conn.execute(
        """
        MATCH (t:Task {id: $task_id}), (v:Violation {id: $violation_id})
        MERGE (t)-[:TASK_VIOLATION]->(v)
        """,
        {"task_id": task_id, "violation_id": violation_id},
    )
    return {"ok": True}


@mcp.tool(tags={"namespace:task"})
async def task_block(
    task_id: Annotated[str, Field(description="Task ID that is being blocked")],
    blocked_by_task_id: Annotated[
        str, Field(description="Task ID that is doing the blocking")
    ],
    reason: Annotated[str, Field(description="Reason why the task is blocked")],
) -> dict:
    """Record a blocking dependency between two tasks."""
    conn = get_conn()
    conn.execute(
        """
        MATCH (blocker:Task {id: $blocker_id}), (blocked:Task {id: $blocked_id})
        MERGE (blocker)-[:TASK_BLOCKS {reason: $reason}]->(blocked)
        """,
        {
            "blocker_id": blocked_by_task_id,
            "blocked_id": task_id,
            "reason": reason,
        },
    )
    return {"ok": True}
