"""
tools/work/tasks.py — Task tracking tools.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Any, cast

import anyio
from fastmcp import FastMCP
from pydantic import Field

from ...agents.document.task_agent import TaskDependencies, task_agent
from ...db import db_get_connection
from ...embeddings import embeddings_generate
from ...ids import id_generate_v7
from ...services.search import rrf_fuse

logger = logging.getLogger(__name__)

mcp = FastMCP("tasks")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@mcp.tool(tags={"namespace:work"})
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
    Track and create a new unit of work under a project.

    Provide a title, description, and optional priority to create and index the task.
    Returns a task_id you can update, block, and link to decisions or violations.
    """
    conn = db_get_connection()
    task_id = id_generate_v7()
    vec = await embeddings_generate(f"{title}\n{description}")

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

    conn.execute(
        """
        MATCH (p:Project {id: $project_id}), (t:Task {id: $task_id})
        CREATE (p)-[:HAS_TASK]->(t)
        """,
        {"project_id": project_id, "task_id": task_id},
    )

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
    Change and update the status, phase, or priority of an existing task.

    Provide the task ID and only the fields you want to update.
    Returns confirmation — set status='done' to mark the task complete.
    """
    conn = db_get_connection()
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

    set_statement = ", ".join(set_clauses)
    conn.execute(  # nosemgrep
        f"""
        MATCH (t:Task {{id: $id}})
        SET {set_statement}
        """,
        params,
    )

    return {"task_id": task_id, "ok": True}


@mcp.tool(tags={"namespace:work"})
async def task_get(
    task_id: Annotated[str, Field(description="Task ID to retrieve")],
) -> dict:
    """Retrieve and inspect full details for a task including linked decisions, violations, and blockers."""
    conn = db_get_connection()

    result = conn.execute(
        """
        MATCH (t:Task {id: $id})
        RETURN t.id, t.title, t.description, t.status, t.priority,
               t.phase, t.created_at, t.updated_at, t.completed_at
        """,
        {"id": task_id},
    )
    if isinstance(result, list):
        result = result[0]
    rows = cast(list[list[Any]], result.get_all())
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

    task["decisions"] = _query_linked(
        conn, task_id, "TASK_DECISION", "Decision", ["id", "title"]
    )
    task["violations"] = _query_linked(
        conn, task_id, "TASK_VIOLATION", "Violation", ["id", "rule", "severity"]
    )
    task["blocked_by"] = _query_blockers(conn, task_id)

    return {"task": task}


def _query_linked(
    conn: Any, task_id: str, rel: str, label: str, fields: list[str]
) -> list[dict]:
    import re

    # Validate identifiers to prevent injection
    identifier_pattern = r"^[a-zA-Z_][\w]*$"
    if not re.match(identifier_pattern, rel):
        raise ValueError(f"Invalid relation: {rel}")
    if not re.match(identifier_pattern, label):
        raise ValueError(f"Invalid label: {label}")
    for f in fields:
        if not re.match(identifier_pattern, f):
            raise ValueError(f"Invalid field: {f}")

    cypher_fields = ", ".join(f"x.{f}" for f in fields)
    result = conn.execute(  # nosemgrep
        f"""
        MATCH (t:Task {{id: $id}})-[:{rel}]->(x:{label})
        RETURN {cypher_fields}
        """,
        {"id": task_id},
    )
    if isinstance(result, list):
        result = result[0]
    return [dict(zip(fields, row)) for row in cast(list[list[Any]], result.get_all())]


def _query_blockers(conn: Any, task_id: str) -> list[dict]:
    result = conn.execute(
        """
        MATCH (blocker:Task)-[:TASK_BLOCKS]->(t:Task {id: $id})
        RETURN blocker.id, blocker.title
        """,
        {"id": task_id},
    )
    if isinstance(result, list):
        result = result[0]
    return [
        {"id": row[0], "title": row[1]}
        for row in cast(list[list[Any]], result.get_all())
    ]


@mcp.tool()
async def task_search(
    query: Annotated[str, Field(description="Natural language search query")],
    project_id: Annotated[
        str | None, Field(description="Scope search to a project")
    ] = None,
    limit: Annotated[int, Field(description="Maximum results", ge=1, le=20)] = 10,
) -> dict:
    """Find and retrieve tasks relevant to a goal or topic using semantic search. Provide a natural language query and optionally scope to a project. Returns ranked tasks."""
    conn = db_get_connection()
    vec = await embeddings_generate(query)
    candidate_size = limit * 3

    vector_raw = conn.execute(
        """
        CALL QUERY_VECTOR_INDEX('Task', 'idx_task_emb', $qvec, $candidate_size)
        WITH node AS t, distance
        OPTIONAL MATCH (p:Project)-[:HAS_TASK]->(t)
        RETURN t.id, t.title, t.status, t.priority, p.id AS project_id, distance
        ORDER BY distance
        LIMIT $candidate_size
        """,
        {"qvec": vec, "candidate_size": candidate_size},
    )
    if isinstance(vector_raw, list):
        vector_raw = vector_raw[0]
    vector_rows = cast(list[list[Any]], vector_raw.get_all())

    fts_raw = conn.execute(
        """
        CALL QUERY_FTS_INDEX('Task', 'fts_task_desc', $q)
        WITH node AS t, score
        OPTIONAL MATCH (p:Project)-[:HAS_TASK]->(t)
        RETURN t.id, t.title, t.status, t.priority, p.id AS project_id, score
        ORDER BY score DESC
        LIMIT $candidate_size
        """,
        {"q": query, "candidate_size": candidate_size},
    )
    if isinstance(fts_raw, list):
        fts_raw = fts_raw[0]
    fts_rows = cast(list[list[Any]], fts_raw.get_all())

    vector_hits = [(row[0], float(row[5])) for row in vector_rows]
    fts_hits = [(row[0], float(rank)) for rank, row in enumerate(fts_rows, start=1)]
    ranks = dict(rrf_fuse(vector_hits, fts_hits))

    data_map: dict[str, list[Any]] = {row[0]: row for row in vector_rows}
    for row in fts_rows:
        data_map[row[0]] = row

    tasks = []
    for node_id, _ in sorted(ranks.items(), key=lambda item: item[1], reverse=True):
        if node_id not in data_map:
            continue
        r = data_map[node_id]
        if project_id and r[4] != project_id:
            continue
        tasks.append(
            {
                "id": r[0],
                "title": r[1],
                "status": r[2],
                "priority": r[3],
                "project_id": r[4],
                "distance": 1.0 - ranks[node_id],
            }
        )
        if len(tasks) >= limit:
            break

    return {"tasks": tasks, "query": query}


@mcp.tool(tags={"namespace:work"})
async def task_link_decision(
    task_id: Annotated[str, Field(description="Task ID")],
    decision_id: Annotated[str, Field(description="Decision ID to link")],
) -> dict:
    """Record that a task is governed by a specific architectural decision. Provide both IDs and the relationship is created for traceability."""
    conn = db_get_connection()
    conn.execute(
        """
        MATCH (t:Task {id: $task_id}), (d:Decision {id: $decision_id})
        MERGE (t)-[:TASK_DECISION]->(d)
        """,
        {"task_id": task_id, "decision_id": decision_id},
    )
    return {"ok": True}


@mcp.tool(tags={"namespace:work"})
async def task_link_violation(
    task_id: Annotated[str, Field(description="Task ID")],
    violation_id: Annotated[str, Field(description="Violation ID to link")],
) -> dict:
    """Associate and link a task with a specific code violation to track remediation. Provide both IDs and the link is stored."""
    conn = db_get_connection()
    conn.execute(
        """
        MATCH (t:Task {id: $task_id}), (v:Violation {id: $violation_id})
        MERGE (t)-[:TASK_VIOLATION]->(v)
        """,
        {"task_id": task_id, "violation_id": violation_id},
    )
    return {"ok": True}


@mcp.tool(tags={"namespace:work"})
async def task_block(
    task_id: Annotated[str, Field(description="Task ID that is being blocked")],
    blocked_by_task_id: Annotated[
        str, Field(description="Task ID that is doing the blocking")
    ],
    reason: Annotated[str, Field(description="Reason why the task is blocked")],
) -> dict:
    """Mark and record one task as blocked by another and explain why. Provide both task IDs and a reason so blockers are visible in task retrieval."""
    conn = db_get_connection()
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


async def _load_task_skills() -> str:
    path = os.path.join(os.getcwd(), "skills", "task_agent", "SKILL.md")
    if not os.path.exists(path):
        return ""
    try:
        async with await anyio.open_file(path, "r", encoding="utf-8") as f:
            return await f.read()
    except Exception as exc:
        logger.warning("Failed to load skills: %s", exc)
        return ""


def _fetch_active_decisions(conn: Any, project_id: str) -> list[dict]:
    dec_result = conn.execute(
        """
        MATCH (p:Project {id: $project_id})-[:HAS_DECISION]->(d:Decision)
        WHERE d.status = 'active'
        RETURN d.id, d.title, d.rationale
        """,
        {"project_id": project_id},
    )
    if isinstance(dec_result, list):
        dec_result = dec_result[0]
    return [
        {"id": r[0], "title": r[1], "rationale": r[2]}
        for r in cast(list[list[Any]], dec_result.get_all())
    ]


def _fetch_open_violations(conn: Any, project_id: str) -> list[dict]:
    v_result = conn.execute(
        """
        MATCH (p:Project {id: $project_id})-[:HAS_VIOLATION]->(v:Violation)
        WHERE v.status = 'open'
        RETURN v.id, v.rule, v.file_path, v.severity, v.description
        """,
        {"project_id": project_id},
    )
    if isinstance(v_result, list):
        v_result = v_result[0]
    return [
        {
            "id": r[0],
            "rule": r[1],
            "file_path": r[2],
            "severity": r[3],
            "description": r[4],
        }
        for r in cast(list[list[Any]], v_result.get_all())
    ]


@mcp.tool(tags={"namespace:work"})
async def task_decompose_feature(
    project_id: Annotated[str, Field(description="Project ID")],
    feature_description: Annotated[
        str, Field(description="Detailed description of the feature to build")
    ],
) -> dict:
    """
    Decompose and break down a complex feature request into sequenced tasks using an AI agent.

    Reads prior decisions, open violations, and codebase context to generate tasks.
    Returns a structured list of tasks with complexity estimates and blockers identified.
    """
    conn = db_get_connection()
    prior_decisions = _fetch_active_decisions(conn, project_id)
    open_violations = _fetch_open_violations(conn, project_id)

    skills_content = await _load_task_skills()
    deps = TaskDependencies(
        feature_description=feature_description,
        project_id=project_id,
        prior_decisions=prior_decisions,
        open_violations=open_violations,
        codebase_map=[],
        skills_content=skills_content,
    )

    try:
        async with task_agent.run_stream(
            "Decompose feature into tasks by calling process_batch iteratively.",
            deps=deps,
        ) as run_result:
            report = await run_result.get_output()
    except Exception as exc:
        logger.error("Task agent execution failed: %s", exc)
        return {"error": f"Agent failed: {exc}"}

    return {
        "status": "completed" if not report.partial_failure else "partial",
        "summary": report.summary,
        "complexity": report.estimated_complexity,
        "tasks_generated": len(report.tasks),
        "blockers_identified": report.identified_blockers,
    }
