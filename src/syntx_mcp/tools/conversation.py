"""
tools/conversation.py — Conversation capture tools.

Automatic capture path:
  1. Agent calls ``conversation_start`` at session open.
  2. Every turn calls ``conversation_append`` with role + content.
  3. Agent calls ``conversation_end`` at close — triggers Ollama summary generation.

``conversation_get`` returns the full ordered message list for replay.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, cast

import ollama
from fastmcp import FastMCP
from pydantic import Field

from ..db import get_conn
from ..embeddings import embed

mcp = FastMCP("conversation")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(tags={"namespace:conversation"})
async def conversation_start(
    project_id: Annotated[str, Field(description="ID of the owning project")],
    agent_name: Annotated[
        str, Field(description="Agent name, e.g. 'claude-sonnet-4-6'")
    ],
    model: Annotated[str, Field(description="Raw model string")],
) -> dict:
    """
    Start a new conversation session.

    Creates a Conversation node, an Agent node (if not existing), and links them.
    Returns the conversation_id that must be passed to all subsequent calls.
    """
    conn = get_conn()
    conv_id = _new_id()
    agent_id = agent_name  # use name as stable agent ID

    # Upsert agent
    conn.execute(
        """
        MERGE (a:Agent {id: $id})
        ON CREATE SET a.name = $name, a.model = $model, a.created_at = $ts
        """,
        {"id": agent_id, "name": agent_name, "model": model, "ts": _now()},
    )

    # Create conversation
    conn.execute(
        """
        CREATE (c:Conversation {
            id: $id,
            model: $model,
            turn_count: 0,
            started_at: $ts
        })
        """,
        {"id": conv_id, "model": model, "ts": _now()},
    )

    # Link agent → conversation
    conn.execute(
        """
        MATCH (a:Agent {id: $agent_id}), (c:Conversation {id: $conv_id})
        CREATE (a)-[:AGENT_CONVERSATION]->(c)
        """,
        {"agent_id": agent_id, "conv_id": conv_id},
    )

    # Link project → conversation
    conn.execute(
        """
        MATCH (p:Project {id: $project_id}), (c:Conversation {id: $conv_id})
        CREATE (p)-[:PROJECT_CONVERSATION]->(c)
        """,
        {"project_id": project_id, "conv_id": conv_id},
    )

    return {"conversation_id": conv_id}


@mcp.tool(tags={"namespace:conversation"})
async def conversation_append(
    conversation_id: Annotated[
        str, Field(description="Conversation ID from conversation_start")
    ],
    role: Annotated[
        str, Field(description="Message role: user | assistant | system | tool")
    ],
    content: Annotated[str, Field(description="Message content")],
    tool_name: Annotated[
        str | None, Field(description="Tool name if role=tool")
    ] = None,
) -> dict:
    """
    Append a message to a conversation.

    Embeds the content, creates a Message node, links it to the Conversation,
    and chains NEXT_MESSAGE from the previous message.
    Returns the new message_id.
    """
    conn = get_conn()
    msg_id = _new_id()
    vec = await embed(content)

    conn.execute(
        """
        CREATE (m:Message {
            id: $id,
            role: $role,
            content: $content,
            tool_name: $tool_name,
            embedding: $embedding,
            created_at: $ts
        })
        """,
        {
            "id": msg_id,
            "role": role,
            "content": content,
            "tool_name": tool_name or "",
            "embedding": vec,
            "ts": _now(),
        },
    )

    # Find current turn count + last message
    result = conn.execute(
        """
        MATCH (c:Conversation {id: $conv_id})
        RETURN c.turn_count
        """,
        {"conv_id": conversation_id},
    )
    rows = cast(list[list[Any]], result)
    turn_count = rows[0][0] if rows else 0
    position = turn_count  # 0-indexed

    # Link conversation → message with position
    conn.execute(
        """
        MATCH (c:Conversation {id: $conv_id}), (m:Message {id: $msg_id})
        CREATE (c)-[:CONVERSATION_MESSAGE {position: $pos}]->(m)
        """,
        {"conv_id": conversation_id, "msg_id": msg_id, "pos": position},
    )

    # Chain NEXT_MESSAGE from previous message (if any)
    if position > 0:
        conn.execute(
            """
            MATCH (c:Conversation {id: $conv_id})-[r:CONVERSATION_MESSAGE]->(prev:Message)
            WHERE r.position = $prev_pos
            MATCH (curr:Message {id: $msg_id})
            CREATE (prev)-[:NEXT_MESSAGE {turn_index: $pos}]->(curr)
            """,
            {
                "conv_id": conversation_id,
                "prev_pos": position - 1,
                "msg_id": msg_id,
                "pos": position,
            },
        )

    # Increment turn count
    conn.execute(
        """
        MATCH (c:Conversation {id: $conv_id})
        SET c.turn_count = c.turn_count + 1
        """,
        {"conv_id": conversation_id},
    )

    return {"message_id": msg_id, "position": position}


@mcp.tool(tags={"namespace:conversation"})
async def conversation_end(
    conversation_id: Annotated[str, Field(description="Conversation ID to close")],
) -> dict:
    """
    End a conversation and generate a summary via Ollama.

    Retrieves all messages, generates a short summary, embeds it, and stores
    it on the Conversation node.  Also sets ended_at.
    """
    conn = get_conn()

    # Fetch all messages in order
    result = conn.execute(
        """
        MATCH (c:Conversation {id: $conv_id})-[r:CONVERSATION_MESSAGE]->(m:Message)
        RETURN m.role, m.content
        ORDER BY r.position
        """,
        {"conv_id": conversation_id},
    )
    messages = cast(list[list[str]], result)

    # Build transcript for summarization
    transcript = "\n".join(f"{row[0].upper()}: {row[1]}" for row in messages)
    summary = _generate_summary(transcript)

    # Embed the summary
    vec = await embed(summary)

    # Workaround for Ladybug/Kuzu limitation: Cannot SET an indexed column.
    # We must drop the index, perform the SET, and recreate the index.
    conn.execute("CALL DROP_VECTOR_INDEX('Conversation', 'idx_conv_emb');")

    conn.execute(
        """
        MATCH (c:Conversation {id: $conv_id})
        SET c.summary = $summary,
            c.embedding = $embedding,
            c.ended_at = $ts
        """,
        {
            "conv_id": conversation_id,
            "summary": summary,
            "embedding": vec,
            "ts": _now(),
        },
    )

    conn.execute(
        "CALL CREATE_VECTOR_INDEX('Conversation', 'idx_conv_emb', 'embedding', metric := 'cosine');"
    )

    return {"conversation_id": conversation_id, "summary": summary}


@mcp.tool(tags={"namespace:conversation"})
async def conversation_get(
    conversation_id: Annotated[str, Field(description="Conversation ID to retrieve")],
) -> dict:
    """
    Return full conversation metadata and ordered message list.
    """
    conn = get_conn()

    # Get conversation node
    c_result = conn.execute(
        """
        MATCH (c:Conversation {id: $conv_id})
        RETURN c.id, c.model, c.summary, c.turn_count, c.started_at, c.ended_at
        """,
        {"conv_id": conversation_id},
    )
    c_rows = cast(list[list[Any]], c_result)
    if not c_rows:
        return {"error": f"Conversation {conversation_id!r} not found"}

    row = c_rows[0]
    conv: dict[str, Any] = {
        "id": row[0],
        "model": row[1],
        "summary": row[2],
        "turn_count": row[3],
        "started_at": str(row[4]),
        "ended_at": str(row[5]) if row[5] else None,
    }

    # Get messages in order
    m_result = conn.execute(
        """
        MATCH (c:Conversation {id: $conv_id})-[r:CONVERSATION_MESSAGE]->(m:Message)
        RETURN m.id, m.role, m.content, m.tool_name, m.created_at
        ORDER BY r.position
        """,
        {"conv_id": conversation_id},
    )
    messages = [
        {
            "id": r[0],
            "role": r[1],
            "content": r[2],
            "tool_name": r[3] or None,
            "created_at": str(r[4]),
        }
        for r in cast(list[list[Any]], m_result)
    ]

    return {"conversation": conv, "messages": messages}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _generate_summary(transcript: str) -> str:
    """Call Ollama to generate a short summary of the transcript."""
    try:
        resp = ollama.generate(
            model="llama3.2",  # lightweight summariser; override with env if desired
            prompt=(
                "Summarise the following conversation in 2-3 sentences, "
                "focusing on what was accomplished and any key decisions made.\n\n"
                f"{transcript[:8000]}"  # truncate to avoid context overflow
            ),
        )
        return resp.response.strip()
    except Exception:  # noqa: BLE001
        # Graceful degradation — store a placeholder if Ollama summarisation fails
        return f"[auto-summary unavailable] {len(transcript)} chars captured."
