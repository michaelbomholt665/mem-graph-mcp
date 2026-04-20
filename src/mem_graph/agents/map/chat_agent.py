#!/usr/bin/env python3
# src/mem_graph/agents/map/chat_agent.py
"""
Chat Agent — Memory Librarian for user-initiated graph exploration.

The Librarian. Serves as the user's window into the memory graph.
Retrieves, summarises, and explains project history, decisions, and violations
using hybrid vector + keyword search. Never modifies code or data.

Workflow:
  User question → hybrid recall → graph traversal → synthesised answer.
"""

from __future__ import annotations

################
#   IMPORTS
################
import logging
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits

from ...config import DEFER_AGENT_MODEL_CHECK, ModelTier, config_get_model_for_tier
from ...resources.personas import CHAT_PERSONA
from ...services.search import rrf_fuse
from ..tooling import require_choice, require_identifier

################
#   CONSTANTS
################

logger = logging.getLogger(__name__)

_CHAT_MODEL = config_get_model_for_tier(ModelTier.STANDARD)

################
#   MODELS
################


class ChatAnswer(BaseModel):
    """
    Complete response from the Chat Agent.

    Attributes:
        answer: Synthesised natural-language answer to the user's question.
        sources: Graph node IDs cited to support the answer.
        confidence: Agent's confidence in the answer (0.0–1.0).
        follow_up_hints: Suggested follow-up questions or traversal paths.
    """

    answer: str = Field(description="Synthesised answer to the user's question.")
    sources: list[str] = Field(
        default_factory=list,
        description="Graph node IDs (Memory, Violation, Decision, Task) cited.",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Agent's confidence that retrieved context supports the answer.",
    )
    follow_up_hints: list[str] = Field(
        default_factory=list,
        description="Suggested follow-up queries or relationship traversals.",
    )


class ChatTurnResult(BaseModel):
    """Structured result for a single chat turn plus persisted conversation state."""

    answer: ChatAnswer = Field(description="Structured answer produced for this turn.")
    message_history_json: str = Field(
        description="Serialized Pydantic AI message history to persist for the next turn."
    )
    message_count: int = Field(
        ge=0,
        description="Number of model messages present in the serialized history.",
    )
    requests: int = Field(
        default=0, ge=0, description="Total model requests for this turn."
    )
    input_tokens: int = Field(
        default=0,
        ge=0,
        description="Input tokens consumed during this turn.",
    )
    output_tokens: int = Field(
        default=0,
        ge=0,
        description="Output tokens consumed during this turn.",
    )


################
#   DEPS
################


@dataclass
class ChatDependencies:
    """
    Injectable dependencies for the Chat Agent.

    Attributes:
        project_id: Project to scope graph queries to (empty = global).
        budget_tokens: Maximum tokens of retrieved context per search.
        cross_scope: When True, search ignores project_id filter.
        extra_context: Optional caller-injected context string.
    """

    project_id: str = ""
    budget_tokens: int = 4000
    cross_scope: bool = False
    extra_context: str = ""


_CHAT_GRAPH_TOOLSET: FunctionToolset[ChatDependencies] = FunctionToolset(
    id="memory-graph-search",
    instructions=(
        "These tools are read-only graph retrieval helpers. Start broad with memory recall, "
        "then narrow to violations or decisions, and only traverse relationships once you have "
        "a grounded node identifier."
    ),
)


################
#   AGENT
################

chat_agent: Agent[ChatDependencies, ChatAnswer] = Agent(
    _CHAT_MODEL,
    name="chat-assistant",
    deps_type=ChatDependencies,
    output_type=ChatAnswer,
    toolsets=[_CHAT_GRAPH_TOOLSET],
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)


@chat_agent.instructions
async def chat_build_instructions(ctx: RunContext[ChatDependencies]) -> str:
    """
    Build the Chat Agent system prompt.

    Injects the Librarian persona with retrieval-first directives and
    the project scope context.

    Args:
        ctx: The run context with ChatDependencies.

    Returns:
        Complete system prompt string.
    """
    scope_note = (
        f"Project scope: {ctx.deps.project_id}"
        if ctx.deps.project_id
        else "Scope: global (all projects)"
    )
    return f"""{CHAT_PERSONA.get_system_instructions()}

## Your Role
You are the user's Memory Librarian. Answer questions about the project's
history, decisions, violations, and codebase by retrieving from the graph.

## Scope
{scope_note}

## Retrieval Strategy
1. Start with `chat_recall_memories` for general questions.
2. Use `chat_search_violations` when asked about bugs, issues, or code problems.
3. Use `chat_search_decisions` when asked about architectural choices.
4. Use `chat_traverse_relationship` to follow graph edges (e.g., "which decision
   caused this violation?").
5. Synthesise retrieved context into a clear answer. Cite node IDs.

## Hard Constraints
- Do NOT modify any graph data or code files.
- If context is insufficient, say so and suggest a more specific query.
- Prefer specific node IDs in citations over free-text claims.

{ctx.deps.extra_context}
"""


################
#   TOOLS
################


@_CHAT_GRAPH_TOOLSET.tool
async def chat_recall_memories(
    ctx: RunContext[ChatDependencies],
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Search memories using hybrid vector + keyword retrieval with RRF fusion.

    Args:
        ctx: The run context with ChatDependencies.
        query: Natural-language search query.
        limit: Maximum number of memories to return.

    Returns:
        List of memory dicts with id, kind, scope, content, confidence.
    """
    try:
        from ...db import db_get_connection
        from ...embeddings import embeddings_query

        conn = db_get_connection()
        vec = await embeddings_query(query)
        candidate_size = limit * 3

        vector_raw = conn.execute(
            """
            CALL QUERY_VECTOR_INDEX('Memory', 'idx_memory_emb', $qvec, $candidate_size)
            WITH node AS m, distance
            WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
            OPTIONAL MATCH (m)<-[:PROJECT_MEMORY]-(p:Project)
            RETURN m.id, m.kind, m.scope, m.content, m.confidence,
                   p.id AS project_id, distance
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
            CALL QUERY_FTS_INDEX('Memory', 'fts_memory_content', $q)
            WITH node AS m, score
            WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
            OPTIONAL MATCH (m)<-[:PROJECT_MEMORY]-(p:Project)
            RETURN m.id, m.kind, m.scope, m.content, m.confidence,
                   p.id AS project_id, score
            ORDER BY score DESC
            LIMIT $candidate_size
            """,
            {"q": query, "candidate_size": candidate_size},
        )
        if isinstance(fts_raw, list):
            fts_raw = fts_raw[0]
        fts_rows = cast(list[list[Any]], fts_raw.get_all())

        vector_hits = [(row[0], float(row[6])) for row in vector_rows]
        fts_hits = [(row[0], float(rank)) for rank, row in enumerate(fts_rows, start=1)]
        ranks = dict(rrf_fuse(vector_hits, fts_hits))

        data_map: dict[str, list[Any]] = {row[0]: row for row in vector_rows}
        for row in fts_rows:
            data_map[row[0]] = row

        results: list[dict[str, Any]] = []
        for node_id, relevance in sorted(
            ranks.items(), key=lambda item: item[1], reverse=True
        ):
            if node_id not in data_map:
                continue
            row = data_map[node_id]
            if (
                not ctx.deps.cross_scope
                and ctx.deps.project_id
                and row[5] != ctx.deps.project_id
            ):
                continue
            results.append(
                {
                    "id": row[0],
                    "kind": row[1],
                    "scope": row[2],
                    "content": str(row[3]),
                    "confidence": float(row[4]),
                    "project_id": row[5],
                    "relevance": round(relevance, 4),
                }
            )
            if len(results) >= limit:
                break

        return results
    except Exception as exc:
        logger.warning("chat_recall_memories failed: %s", exc)
        return []


@_CHAT_GRAPH_TOOLSET.tool
async def chat_search_violations(
    ctx: RunContext[ChatDependencies],
    query: str,
    status_filter: str = "open",
    limit: int = 15,
) -> list[dict[str, Any]]:
    """
    Search for violations using hybrid vector + FTS retrieval.

    Args:
        ctx: The run context with ChatDependencies.
        query: Natural-language description of the violation to find.
        status_filter: Filter by status: open | recurrence | resolved | all.
        limit: Maximum results to return.

    Returns:
        List of violation dicts with id, rule, severity, file_path, description.
    """
    try:
        from ...db import db_get_connection
        from ...embeddings import embeddings_query

        conn = db_get_connection()
        vec = await embeddings_query(query)
        candidate_size = limit * 3

        vector_raw = conn.execute(
            """
            CALL QUERY_VECTOR_INDEX('Violation', 'idx_violation_emb', $qvec, $candidate_size)
            WITH node AS v, distance
            OPTIONAL MATCH (p:Project)-[:HAS_VIOLATION]->(v)
            WHERE ($status_filter = 'all' OR v.status = $status_filter)
            RETURN v.id, v.rule, v.severity, v.file_path, v.description,
                   v.status, p.id AS project_id, distance
            ORDER BY distance
            LIMIT $candidate_size
            """,
            {
                "qvec": vec,
                "status_filter": status_filter,
                "candidate_size": candidate_size,
            },
        )
        if isinstance(vector_raw, list):
            vector_raw = vector_raw[0]
        vector_rows = cast(list[list[Any]], vector_raw.get_all())

        fts_raw = conn.execute(
            """
            CALL QUERY_FTS_INDEX('Violation', 'fts_violation_desc', $q)
            WITH node AS v, score
            OPTIONAL MATCH (p:Project)-[:HAS_VIOLATION]->(v)
            WHERE ($status_filter = 'all' OR v.status = $status_filter)
            RETURN v.id, v.rule, v.severity, v.file_path, v.description,
                   v.status, p.id AS project_id, score
            ORDER BY score DESC
            LIMIT $candidate_size
            """,
            {
                "q": query,
                "status_filter": status_filter,
                "candidate_size": candidate_size,
            },
        )
        if isinstance(fts_raw, list):
            fts_raw = fts_raw[0]
        fts_rows = cast(list[list[Any]], fts_raw.get_all())

        vector_hits = [(row[0], float(row[6])) for row in vector_rows]
        fts_hits = [(row[0], float(rank)) for rank, row in enumerate(fts_rows, start=1)]
        ranks = dict(rrf_fuse(vector_hits, fts_hits))

        data_map: dict[str, list[Any]] = {row[0]: row for row in vector_rows}
        for row in fts_rows:
            data_map[row[0]] = row

        results: list[dict[str, Any]] = []
        for node_id, relevance in sorted(
            ranks.items(), key=lambda item: item[1], reverse=True
        ):
            if node_id not in data_map:
                continue
            row = data_map[node_id]
            if (
                ctx.deps.project_id
                and not ctx.deps.cross_scope
                and row[6] != ctx.deps.project_id
            ):
                continue
            results.append(
                {
                    "id": row[0],
                    "rule": row[1],
                    "severity": row[2],
                    "file_path": row[3],
                    "description": str(row[4]),
                    "status": row[5],
                    "project_id": row[6],
                    "relevance": round(relevance, 4),
                }
            )
            if len(results) >= limit:
                break

        return results
    except Exception as exc:
        logger.warning("chat_search_violations failed: %s", exc)
        return []


@_CHAT_GRAPH_TOOLSET.tool
async def chat_search_decisions(
    ctx: RunContext[ChatDependencies],
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Search for architectural decisions using hybrid vector + FTS retrieval.

    Args:
        ctx: The run context with ChatDependencies.
        query: Natural-language description of the decision topic.
        limit: Maximum results to return.

    Returns:
        List of decision dicts with id, title, rationale, status.
    """
    try:
        from ...db import db_get_connection
        from ...embeddings import embeddings_query

        conn = db_get_connection()
        vec = await embeddings_query(query)
        candidate_size = limit * 3

        vector_raw = conn.execute(  # nosemgrep
            """
            CALL QUERY_VECTOR_INDEX('Decision', 'idx_decision_emb', $qvec, $candidate_size)
            WITH node AS d, distance
            OPTIONAL MATCH (p:Project)-[:HAS_DECISION]->(d)
            RETURN d.id, d.title, d.rationale, d.status, d.impact,
                   p.id AS project_id, distance
            ORDER BY distance
            LIMIT $candidate_size
            """,
            {"qvec": vec, "candidate_size": candidate_size},
        )
        if isinstance(vector_raw, list):
            vector_raw = vector_raw[0]
        vector_rows = cast(list[list[Any]], vector_raw.get_all())

        fts_raw = conn.execute(  # nosemgrep
            """
            CALL QUERY_FTS_INDEX('Decision', 'fts_decision_rat', $q)
            WITH node AS d, score
            OPTIONAL MATCH (p:Project)-[:HAS_DECISION]->(d)
            RETURN d.id, d.title, d.rationale, d.status, d.impact,
                   p.id AS project_id, score
            ORDER BY score DESC
            LIMIT $candidate_size
            """,
            {"q": query, "candidate_size": candidate_size},
        )
        if isinstance(fts_raw, list):
            fts_raw = fts_raw[0]
        fts_rows = cast(list[list[Any]], fts_raw.get_all())

        vector_hits = [(row[0], float(row[6])) for row in vector_rows]
        fts_hits = [(row[0], float(rank)) for rank, row in enumerate(fts_rows, start=1)]
        ranks = dict(rrf_fuse(vector_hits, fts_hits))

        data_map: dict[str, list[Any]] = {row[0]: row for row in vector_rows}
        for row in fts_rows:
            data_map[row[0]] = row

        results: list[dict[str, Any]] = []
        for node_id, relevance in sorted(
            ranks.items(), key=lambda item: item[1], reverse=True
        ):
            if node_id not in data_map:
                continue
            row = data_map[node_id]
            if (
                ctx.deps.project_id
                and not ctx.deps.cross_scope
                and row[5] != ctx.deps.project_id
            ):
                continue
            results.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "rationale": str(row[2]),
                    "status": row[3],
                    "impact": row[4],
                    "project_id": row[5],
                    "relevance": round(relevance, 4),
                }
            )
            if len(results) >= limit:
                break

        return results
    except Exception as exc:
        logger.warning("chat_search_decisions failed: %s", exc)
        return []


@_CHAT_GRAPH_TOOLSET.tool
async def chat_traverse_relationship(
    ctx: RunContext[ChatDependencies],
    node_id: str,
    node_type: str,
    relationship: str,
    direction: str = "outgoing",
) -> list[dict[str, Any]]:
    """
    Follow a graph relationship from a known node to discover connected context.

    Useful for questions like "What decision caused this violation?" or
    "Which tasks are related to this decision?".

    Args:
        ctx: The run context with ChatDependencies.
        node_id: The starting node's ID.
        node_type: Graph label of the starting node (e.g. Violation, Decision).
        relationship: Relationship type to traverse (e.g. TASK_VIOLATION, SUPERSEDES).
        direction: 'outgoing' (default) or 'incoming'.

    Returns:
        List of connected node dicts with id, labels, and key properties.
    """
    require_identifier("node_type", node_type)
    require_identifier("relationship", relationship)
    require_choice("direction", direction, allowed=("outgoing", "incoming"))

    try:
        from ...db import db_get_connection

        conn = db_get_connection()

        if direction == "incoming":
            pattern = f"(connected)-[:{relationship}]->(n:{node_type} {{id: $id}})"
        else:
            pattern = f"(n:{node_type} {{id: $id}})-[:{relationship}]->(connected)"

        raw = cast(
            list[list[Any]],
            conn.execute(  # nosemgrep
                f"""
                MATCH {pattern}
                RETURN connected
                LIMIT 20
                """,
                {"id": node_id},
            ),
        )

        return [{"node_id": node_id, "connected_node": str(r[0])} for r in raw]
    except Exception as exc:
        logger.warning("chat_traverse_relationship failed: %s", exc)
        return []


def chat_load_message_history(
    message_history_json: str | bytes | None,
) -> list[ModelMessage] | None:
    """Deserialize persisted message history for a continued chat session."""
    if not message_history_json:
        return None
    payload = (
        message_history_json.encode("utf-8")
        if isinstance(message_history_json, str)
        else message_history_json
    )
    return cast(list[ModelMessage], ModelMessagesTypeAdapter.validate_json(payload))


def chat_dump_message_history(messages: list[ModelMessage]) -> str:
    """Serialize chat history so callers can persist and resume sessions."""
    return ModelMessagesTypeAdapter.dump_json(messages).decode("utf-8")


async def run_chat_turn(
    prompt: str,
    deps: ChatDependencies,
    *,
    message_history_json: str | bytes | None = None,
    usage_limits: UsageLimits | None = None,
) -> ChatTurnResult:
    """Run one chat turn and return both the answer and resumable message history."""
    history = chat_load_message_history(message_history_json)
    result = await chat_agent.run(
        prompt,
        deps=deps,
        message_history=history,
        usage_limits=usage_limits,
    )
    all_messages = list(result.all_messages())
    usage = result.usage()
    return ChatTurnResult(
        answer=result.output,
        message_history_json=chat_dump_message_history(all_messages),
        message_count=len(all_messages),
        requests=usage.requests,
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
    )
