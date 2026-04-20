"""
tools/memory/conversation.py — Intent-level conversation capture tools.

Three tools replace the previous four-tool CRUD surface:

  memory_capture_session  — hand over an entire session at close (1 call)
  memory_recall           — hybrid BM25 + vector search with token budget
  memory_annotate         — mid-session significance tagging

Old ``conversation_start / conversation_append / conversation_end / conversation_get``
are now private helpers used only internally.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from pydantic import Field

from ..markers import tier_1_tool, tier_2_tool

from ...db import db_get_connection
from ...embeddings import embeddings_generate, embeddings_query
from ...ids import id_generate_v7
from ...models.conversation import (
    AnnotateResult,
    ConversationMessage,
    MemoryItem,
    MemoryRecallResult,
    SessionCaptureResult,
)
from ...services.search import rrf_fuse
from ...services.summarizer import enqueue_summary

logger = logging.getLogger(__name__)
mcp = FastMCP("conversation")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def _create_conversation(
    conn: Any, project_id: str, agent_name: str, model: str
) -> str:
    """Create Agent (upsert), Conversation, and link edges. Returns conv_id."""
    conv_id = id_generate_v7()
    agent_id = agent_name

    conn.execute(
        """
        MERGE (a:Agent {id: $id})
        ON CREATE SET a.name = $name, a.model = $model, a.created_at = $ts
        """,
        {"id": agent_id, "name": agent_name, "model": model, "ts": _now()},
    )

    conn.execute(
        """
        CREATE (c:Conversation {
            id: $id,
            model: $model,
            turn_count: 0,
            summary_status: 'pending',
            started_at: $ts
        })
        """,
        {"id": conv_id, "model": model, "ts": _now()},
    )

    conn.execute(
        """
        MATCH (a:Agent {id: $agent_id}), (c:Conversation {id: $conv_id})
        CREATE (a)-[:AGENT_CONVERSATION]->(c)
        """,
        {"agent_id": agent_id, "conv_id": conv_id},
    )

    conn.execute(
        """
        MATCH (p:Project {id: $project_id}), (c:Conversation {id: $conv_id})
        CREATE (p)-[:PROJECT_CONVERSATION]->(c)
        """,
        {"project_id": project_id, "conv_id": conv_id},
    )

    return conv_id


def _bulk_insert_messages(
    conn: Any, conv_id: str, messages: list[ConversationMessage]
) -> list[str]:
    """Create Message nodes, link them to the Conversation and chain NEXT_MESSAGE."""
    msg_ids: list[str] = []

    for position, msg in enumerate(messages):
        msg_id = id_generate_v7()
        msg_ids.append(msg_id)

        conn.execute(
            """
            CREATE (m:Message {
                id: $id,
                role: $role,
                content: $content,
                tool_name: $tool_name,
                created_at: $ts
            })
            """,
            {
                "id": msg_id,
                "role": msg.role,
                "content": msg.content,
                "tool_name": msg.tool_name or "",
                "ts": _now(),
            },
        )

        conn.execute(
            """
            MATCH (c:Conversation {id: $conv_id}), (m:Message {id: $msg_id})
            CREATE (c)-[:CONVERSATION_MESSAGE {position: $pos}]->(m)
            """,
            {"conv_id": conv_id, "msg_id": msg_id, "pos": position},
        )

        if position > 0:
            prev_id = msg_ids[position - 1]
            conn.execute(
                """
                MATCH (prev:Message {id: $prev_id}), (curr:Message {id: $curr_id})
                CREATE (prev)-[:NEXT_MESSAGE {turn_index: $pos}]->(curr)
                """,
                {"prev_id": prev_id, "curr_id": msg_id, "pos": position},
            )

    conn.execute(
        """
        MATCH (c:Conversation {id: $conv_id})
        SET c.turn_count = $count
        """,
        {"conv_id": conv_id, "count": len(messages)},
    )

    return msg_ids


@tier_1_tool
@mcp.tool(tags={"namespace:memory"})
async def memory_capture_session(
    project_id: Annotated[
        str, Field(description="ID of the project this session belongs to")
    ],
    agent_name: Annotated[
        str, Field(description="Your agent identifier, e.g. 'claude-sonnet-4-6'")
    ],
    messages: Annotated[
        list[ConversationMessage],
        Field(description="Ordered list of all messages in this session"),
    ],
    model: Annotated[
        str, Field(description="Model string used during this session")
    ] = "unknown",
    context: Annotated[
        str | None,
        Field(description="Optional extra context to attach to the session record"),
    ] = None,
) -> SessionCaptureResult:
    """Capture a conversation session for background summarization."""
    conn = db_get_connection()

    conv_id = _create_conversation(conn, project_id, agent_name, model)
    _bulk_insert_messages(conn, conv_id, messages)

    transcript = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
    if context:
        transcript = f"[Context: {context}]\n\n{transcript}"

    enqueue_summary(conv_id, transcript)

    logger.info(
        "Captured session %s (%d messages) for project %s; summary queued.",
        conv_id,
        len(messages),
        project_id,
    )

    return SessionCaptureResult(
        session_id=conv_id,
        turn_count=len(messages),
        summary_pending=True,
    )


@tier_1_tool
@mcp.tool(tags={"namespace:memory"})
async def memory_recall(
    query: Annotated[
        str, Field(description="What you want to remember — natural language")
    ],
    project_id: Annotated[
        str | None, Field(description="Limit recall to a specific project")
    ] = None,
    budget_tokens: Annotated[
        int, Field(description="Maximum tokens of content to return", ge=100, le=8000)
    ] = 2000,
    recency_bias: Annotated[
        float,
        Field(
            description="0 = pure semantic relevance, 1 = pure recency. Default 0.1.",
            ge=0.0,
            le=1.0,
        ),
    ] = 0.1,
    cross_scope: Annotated[
        bool,
        Field(
            description="Search across all scopes and projects (ignores project_id filter)"
        ),
    ] = False,
    limit: Annotated[
        int,
        Field(description="Candidate pool size before budget truncation", ge=5, le=50),
    ] = 20,
) -> MemoryRecallResult:
    """Recall relevant memories, decisions, violations, and session summaries."""
    conn = db_get_connection()
    vec = await embeddings_query(query)
    candidate_size = limit * 3

    vector_raw = conn.execute(
        """
        CALL QUERY_VECTOR_INDEX('Memory', 'idx_memory_emb', $qvec, $candidate_size)
        WITH node AS m, distance
        WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
        OPTIONAL MATCH (m)<-[:PROJECT_MEMORY]-(p:Project)
        RETURN m.id, m.kind, m.scope, m.content, m.confidence, p.id AS project, distance
        ORDER BY distance
        LIMIT $candidate_size
        """,
        {"qvec": vec, "candidate_size": candidate_size},
    )
    if isinstance(vector_raw, list):
        vector_raw = vector_raw[0]
    vector_rows = cast(list[list[Any]], vector_raw.get_all())

    keyword_raw = conn.execute(
        """
        CALL QUERY_FTS_INDEX('Memory', 'fts_memory_content', $q)
        WITH node AS m, score
        WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
        OPTIONAL MATCH (m)<-[:PROJECT_MEMORY]-(p:Project)
        RETURN m.id, m.kind, m.scope, m.content, m.confidence, p.id AS project, score
        ORDER BY score DESC
        LIMIT $candidate_size
        """,
        {"q": query, "candidate_size": candidate_size},
    )
    if isinstance(keyword_raw, list):
        keyword_raw = keyword_raw[0]
    keyword_rows = cast(list[list[Any]], keyword_raw.get_all())

    vector_hits: list[tuple[str, float]] = [
        (row[0], float(row[6])) for row in vector_rows
    ]
    fts_hits: list[tuple[str, float]] = [
        (row[0], float(rank)) for rank, row in enumerate(keyword_rows, start=1)
    ]
    ranks = dict(rrf_fuse(vector_hits, fts_hits))

    data_map: dict[str, list[Any]] = {row[0]: row for row in vector_rows}
    for row in keyword_rows:
        data_map[row[0]] = row

    items: list[MemoryItem] = []
    total_tokens = 0
    truncated = False

    for node_id, relevance in sorted(
        ranks.items(), key=lambda item: item[1], reverse=True
    ):
        if node_id not in data_map:
            continue
        row = data_map[node_id]

        mem_project: str | None = row[5]
        if not cross_scope and project_id and mem_project != project_id:
            continue

        content = str(row[3])
        tok = _estimate_tokens(content)

        if total_tokens + tok > budget_tokens:
            truncated = True
            break

        items.append(
            MemoryItem(
                id=str(row[0]),
                kind=str(row[1]),
                scope=str(row[2]),
                content=content,
                confidence=float(row[4]),
                project=mem_project,
                distance=1.0 - relevance,
            )
        )
        total_tokens += tok

    return MemoryRecallResult(
        memories=items,
        total_tokens=total_tokens,
        truncated=truncated,
        query=query,
    )


@tier_2_tool
@mcp.tool(tags={"namespace:memory"})
async def memory_annotate(
    conversation_id: Annotated[
        str, Field(description="Session ID to attach this annotation to")
    ],
    note: Annotated[
        str, Field(description="The insight, decision, or observation to preserve")
    ],
    significance: Annotated[
        str,
        Field(description="How important this is: low | normal | high | critical"),
    ] = "normal",
) -> AnnotateResult:
    """Save an in-session annotation as memory."""
    conn = db_get_connection()
    mem_id = id_generate_v7()
    vec = await embeddings_generate(note)

    conf_map = {"low": 0.5, "normal": 0.75, "high": 0.9, "critical": 1.0}

    conn.execute(
        """
        CREATE (m:Memory {
            id: $id,
            kind: 'annotation',
            scope: 'global',
            content: $content,
            confidence: $conf,
            embedding: $vec,
            created_at: $ts,
            updated_at: $ts
        })
        """,
        {
            "id": mem_id,
            "content": note,
            "conf": conf_map.get(significance, 0.75),
            "vec": vec,
            "ts": _now(),
        },
    )

    conn.execute(
        """
        MATCH (c:Conversation {id: $conv_id}), (m:Memory {id: $mem_id})
        CREATE (m)-[:MEMORY_SOURCE]->(c)
        """,
        {"conv_id": conversation_id, "mem_id": mem_id},
    )

    return AnnotateResult(
        memory_id=mem_id,
        linked_to_session=conversation_id,
    )
